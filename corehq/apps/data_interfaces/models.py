import jsonfield
import pytz
import re
from collections import defaultdict

from casexml.apps.case.models import CommCareCase
from corehq.apps.es.cases import CaseES
from corehq.form_processor.abstract_models import DEFAULT_PARENT_IDENTIFIER
from corehq.form_processor.exceptions import CaseNotFound
from couchdbkit.exceptions import ResourceNotFound
from datetime import date, datetime, time, timedelta
from dateutil.parser import parse
from dimagi.utils.couch import CriticalSection
from dimagi.utils.decorators.memoized import memoized
from django.db import models, transaction
from corehq.apps.hqcase.utils import update_case
from corehq.form_processor.models import CommCareCaseSQL
from django.utils.translation import ugettext_lazy
from jsonobject.api import JsonObject
from jsonobject.properties import StringProperty

ALLOWED_DATE_REGEX = re.compile('^\d{4}-\d{2}-\d{2}')
AUTO_UPDATE_XMLNS = 'http://commcarehq.org/hq_case_update_rule'


class AutomaticUpdateRule(models.Model):
    domain = models.CharField(max_length=126, db_index=True)
    name = models.CharField(max_length=126)
    case_type = models.CharField(max_length=126)
    active = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    last_run = models.DateTimeField(null=True)
    filter_on_server_modified = models.BooleanField(default=True)

    # For performance reasons, the server_modified_boundary is a
    # required part of the criteria and should be set to the minimum
    # number of days old that a case's server_modified_on date must be
    # before we run the rule against it.
    server_modified_boundary = models.IntegerField(null=True)
    migrated = models.BooleanField(default=False)

    class Meta:
        app_label = "data_interfaces"

    class MigrationError(Exception):
        pass

    class RuleError(Exception):
        pass

    def migrate(self):
        if not self.pk:
            raise ValueError("Expected model to be saved first")

        with CriticalSection(['migrate-rule-%s' % self.pk]):
            rule = AutomaticUpdateRule.objects.get(pk=self.pk)
            if not rule.migrated:
                with transaction.atomic():
                    # Migrate Criteria
                    for old_criteria in rule.automaticupdaterulecriteria_set.all():
                        new_criteria_definition = MatchPropertyDefinition(
                            property_name=old_criteria.property_name,
                            property_value=old_criteria.property_value,
                            match_type=old_criteria.match_type,
                        )
                        new_criteria_definition.save()

                        new_criteria = CaseRuleCriteria(rule=rule)
                        new_criteria.definition = new_criteria_definition
                        new_criteria.save()

                    # Migrate Actions
                    properties_to_update = []
                    close_case = False
                    for old_action in rule.automaticupdateaction_set.all():
                        if old_action.action == AutomaticUpdateAction.ACTION_UPDATE:
                            properties_to_update.append(
                                UpdateCaseDefinition.PropertyDefinition(
                                    name=old_action.property_name,
                                    value_type=old_action.property_value_type,
                                    value=old_action.property_value,
                                )
                            )
                        elif old_action.action == AutomaticUpdateAction.ACTION_CLOSE:
                            close_case = True
                        else:
                            raise ValueError("Unexpected action found: %s" % old_action.action)

                    new_action_definition = UpdateCaseDefinition(close_case=close_case)
                    new_action_definition.set_properties_to_update(properties_to_update)
                    new_action_definition.save()

                    new_action = CaseRuleAction(rule=rule)
                    new_action.definition = new_action_definition
                    new_action.save()

                    rule.migrated = True
                    rule.save()

            return rule

    @classmethod
    def by_domain(cls, domain, active_only=True):
        filters = {'domain': domain}
        if active_only:
            filters['active'] = True
        return AutomaticUpdateRule.objects.filter(deleted=False, **filters)

    @classmethod
    def organize_rules_by_case_type(cls, rules):
        rules_by_case_type = {}
        for rule in rules:
            if rule.case_type not in rules_by_case_type:
                rules_by_case_type[rule.case_type] = [rule]
            else:
                rules_by_case_type[rule.case_type].append(rule)
        return rules_by_case_type

    # returns None if any of the rules do not filter on server modified
    @classmethod
    def get_boundary_date(cls, rules, now):
        min_boundary = None
        for rule in rules:
            if not rule.filter_on_server_modified:
                return None
            elif not min_boundary:
                min_boundary = rule.server_modified_boundary
            elif rule.server_modified_boundary < min_boundary:
                min_boundary = rule.server_modified_boundary
        date = now - timedelta(days=min_boundary)
        return date

    @classmethod
    def get_case_ids(cls, domain, case_type, boundary_date=None):
        """
        Retrieves the case ids in chunks, yielding a list of case ids each time
        until there are none left.
        """
        chunk_size = 100

        query = (CaseES()
                 .domain(domain)
                 .case_type(case_type)
                 .is_closed(closed=False)
                 .exclude_source()
                 .size(chunk_size))

        if boundary_date:
            query = query.server_modified_range(lte=boundary_date)

        result = []

        for case_id in query.scroll():
            if not isinstance(case_id, basestring):
                raise ValueError("Something is wrong with the query, expected ids only")

            result.append(case_id)
            if len(result) >= chunk_size:
                yield result
                result = []

        if result:
            yield result

    def rule_matches_case(self, case, now):
        if self.migrated:
            raise self.MigrationError("Attempted to call old method on migrated model.")

        try:
            return self._rule_matches_case(case, now)
        except (CaseNotFound, ResourceNotFound):
            # This might happen if the rule references a parent case and the
            # parent case is not found
            return False

    def _rule_matches_case(self, case, now):
        if self.migrated:
            raise self.MigrationError("Attempted to call old method on migrated model.")

        if case.type != self.case_type:
            return False

        if self.filter_on_server_modified and \
                (case.server_modified_on > (now - timedelta(days=self.server_modified_boundary))):
            return False

        return all([criterion.matches(case, now)
                   for criterion in self.automaticupdaterulecriteria_set.all()])

    def apply_actions(self, case):
        if self.migrated:
            raise self.MigrationError("Attempted to call old method on migrated model.")

        cases_to_update = defaultdict(dict)
        close = False

        def _get_case_property_value(current_case, name):
            result = current_case.resolve_case_property(name)
            if result:
                return result[0].value

            return None

        def _add_update_property(name, value, current_case):
            while name.startswith('parent/'):
                name = name[7:]
                # uses first parent if there are multiple
                parent_cases = current_case.get_parent(identifier=DEFAULT_PARENT_IDENTIFIER)
                if parent_cases:
                    current_case = parent_cases[0]
                else:
                    return
            cases_to_update[current_case.case_id][name] = value

        for action in self.automaticupdateaction_set.all():
            if action.action == AutomaticUpdateAction.ACTION_UPDATE:
                if action.property_value_type == AutomaticUpdateAction.CASE_PROPERTY:
                    value = _get_case_property_value(case, action.property_value)
                    if value is None:
                        continue
                else:
                    value = action.property_value

                if value != _get_case_property_value(case, action.property_name):
                    _add_update_property(action.property_name, value, case)
            elif action.action == AutomaticUpdateAction.ACTION_CLOSE:
                close = True

        # Update any referenced parent cases
        for id, properties in cases_to_update.items():
            if id == case.case_id:
                continue
            update_case(case.domain, id, case_properties=properties, close=False,
                xmlns=AUTO_UPDATE_XMLNS)

        # Update / close the case
        properties = cases_to_update[case.case_id]
        if close or properties:
            update_case(case.domain, case.case_id, case_properties=properties, close=close,
                xmlns=AUTO_UPDATE_XMLNS)

        return close

    def apply_rule(self, case, now):
        """
        :return: True to stop processing further rules on the case (e.g., the
        case is closed or deleted), False otherwise
        """
        if self.migrated:
            raise self.MigrationError("Attempted to call old method on migrated model.")

        if self.deleted:
            raise Exception("Attempted to call apply_rule on a deleted rule")

        if not self.active:
            raise Exception("Attempted to call apply_rule on an inactive rule")

        if not isinstance(case, (CommCareCase, CommCareCaseSQL)):
            raise ValueError("Invalid case given")

        if not case.doc_type.startswith('CommCareCase'):
            raise ValueError("Invalid case given")

        if case.domain != self.domain:
            raise ValueError("Invalid case given")

        if case.is_deleted or case.closed:
            return True

        if self.rule_matches_case(case, now):
            return self.apply_actions(case)
        return False

    def activate(self, active=True):
        self.active = active
        self.save()

    def soft_delete(self):
        self.deleted = True
        self.save()

    @property
    @memoized
    def memoized_criteria(self):
        return self.caserulecriteria_set.all().select_related(
            'match_property_definition',
            'custom_match_definition',
            'closed_parent_definition',
        )

    @property
    @memoized
    def memoized_actions(self):
        return self.caseruleaction_set.all().select_related(
            'update_case_definition',
            'custom_action_definition',
        )

    def run_rule(self, case, now):
        """
        :return: CaseRuleActionResult object aggregating the results from all actions.
        """
        if not self.migrated:
            raise self.MigrationError("Attempted to call new method on non-migrated model.")

        if self.deleted:
            raise self.RuleError("Attempted to call run_rule on a deleted rule")

        if not self.active:
            raise self.RuleError("Attempted to call run_rule on an inactive rule")

        if not isinstance(case, (CommCareCase, CommCareCaseSQL)) or case.domain != self.domain:
            raise self.RuleError("Invalid case given")

        if case.is_deleted or case.closed:
            return CaseRuleActionResult()

        if self.criteria_match(case, now):
            return self.apply_actions(case)

        return CaseRuleActionResult()

    def criteria_match(self, case, now):
        if not self.migrated:
            raise self.MigrationError("Attempted to call new method on non-migrated model.")

        if case.type != self.case_type:
            return False

        if self.filter_on_server_modified and \
                (case.server_modified_on > (now - timedelta(days=self.server_modified_boundary))):
            return False

        for criteria in self.memoized_criteria:
            try:
                result = criteria.definition.matches(case, now)
            except (CaseNotFound, ResourceNotFound):
                # This might happen if the criteria references a parent case and the
                # parent case is not found
                result = False

            if not result:
                return False

        return True

    def run_actions(self, case):
        if not self.migrated:
            raise self.MigrationError("Attempted to call new method on non-migrated model.")

        aggregated_result = CaseRuleActionResult()

        for action in self.memoized_actions:
            result = action.definition.run(case)
            if not isinstance(result, CaseRuleActionResult):
                raise TypeError("Expected CaseRuleActionResult")

            aggregated_result.add_result(result)

        return aggregated_result


class CaseRuleCriteria(models.Model):
    rule = models.ForeignKey('AutomaticUpdateRule', on_delete=models.PROTECT)
    match_property_definition = models.ForeignKey('MatchPropertyDefinition', on_delete=models.CASCADE, null=True)
    custom_match_definition = models.ForeignKey('CustomMatchDefinition', on_delete=models.CASCADE, null=True)
    closed_parent_definition = models.ForeignKey('ClosedParentDefinition', on_delete=models.CASCADE, null=True)

    @property
    def definition(self):
        if self.match_property_definition_id:
            return self.match_property_definition
        elif self.custom_match_definition_id:
            return self.custom_match_definition
        elif self.closed_parent_definition_id:
            return self.closed_parent_definition
        else:
            raise ValueError("No available definition found")

    @definition.setter
    def definition(self, value):
        self.match_property_definition = None
        self.custom_match_definition = None
        self.closed_parent_definition = None

        if isinstance(value, MatchPropertyDefinition):
            self.match_property_definition = value
        elif isinstance(value, CustomMatchDefinition):
            self.custom_match_definition = value
        elif isinstance(value, ClosedParentDefinition):
            self.closed_parent_definition = value
        else:
            raise ValueError("Unexpected type found: %s" % type(value))


class CaseRuleCriteriaDefinition(models.Model):

    class Meta:
        abstract = True

    def matches(self, case, now):
        raise NotImplementedError()


class MatchPropertyDefinition(CaseRuleCriteriaDefinition):
    # True when today < (the date in property_name - property_value days)
    MATCH_DAYS_BEFORE = 'DAYS_BEFORE'

    # True when today >= (the date in property_name + property_value days)
    MATCH_DAYS_AFTER = 'DAYS'

    MATCH_EQUAL = 'EQUAL'
    MATCH_NOT_EQUAL = 'NOT_EQUAL'
    MATCH_HAS_VALUE = 'HAS_VALUE'

    property_name = models.CharField(max_length=126)
    property_value = models.CharField(max_length=126, null=True)
    match_type = models.CharField(max_length=15)

    def get_case_values(self, case):
        values = case.resolve_case_property(self.property_name)
        return [element.value for element in values]

    def _try_date_conversion(self, date_or_string):
        if (
            not isinstance(date_or_string, date) and
            isinstance(date_or_string, basestring) and
            ALLOWED_DATE_REGEX.match(date_or_string)
        ):
            date_or_string = parse(date_or_string)

        return date_or_string

    def clean_datetime(self, timestamp):
        if not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, time(0, 0))

        if timestamp.tzinfo:
            # Convert to UTC and make it a naive datetime for comparison to datetime.utcnow()
            timestamp = timestamp.astimezone(pytz.utc).replace(tzinfo=None)

        return timestamp

    def check_days_before(self, case, now):
        values = self.get_case_values(case)
        for date_to_check in values:
            date_to_check = self._try_date_conversion(date_to_check)

            if not isinstance(date_to_check, date):
                continue

            date_to_check = self.clean_datetime(date_to_check)

            days = int(self.property_value)
            if now < (date_to_check - timedelta(days=days)):
                return True

        return False

    def check_days_after(self, case, now):
        values = self.get_case_values(case)
        for date_to_check in values:
            date_to_check = self._try_date_conversion(date_to_check)

            if not isinstance(date_to_check, date):
                continue

            date_to_check = self.clean_datetime(date_to_check)

            days = int(self.property_value)
            if now >= (date_to_check + timedelta(days=days)):
                return True

        return False

    def check_equal(self, case, now):
        return any([
            value == self.property_value for value in self.get_case_values(case)
        ])

    def check_not_equal(self, case, now):
        return any([
            value != self.property_value for value in self.get_case_values(case)
        ])

    def check_has_value(self, case, now):
        values = self.get_case_values(case)
        for value in values:
            if value is None:
                continue
            if isinstance(value, basestring) and not value.strip():
                continue
            return True

        return False

    def matches(self, case, now):
        return {
            self.MATCH_DAYS_BEFORE: self.check_days_before,
            self.MATCH_DAYS_AFTER: self.check_days_after,
            self.MATCH_EQUAL: self.check_equal,
            self.MATCH_NOT_EQUAL: self.check_not_equal,
            self.MATCH_HAS_VALUE: self.check_has_value,
        }.get(self.match_type)(case, now)


class CustomMatchDefinition(CaseRuleCriteriaDefinition):
    name = models.CharField(max_length=126)


class ClosedParentDefinition(CaseRuleCriteriaDefinition):
    pass


class AutomaticUpdateRuleCriteria(models.Model):
    # True when today < (the date in property_name - property_value days)
    MATCH_DAYS_BEFORE = 'DAYS_BEFORE'
    # True when today >= (the date in property_name + property_value days)
    MATCH_DAYS_AFTER = 'DAYS'
    MATCH_EQUAL = 'EQUAL'
    MATCH_NOT_EQUAL = 'NOT_EQUAL'
    MATCH_HAS_VALUE = 'HAS_VALUE'

    MATCH_TYPE_CHOICES = (
        (MATCH_DAYS_BEFORE, MATCH_DAYS_BEFORE),
        (MATCH_DAYS_AFTER, MATCH_DAYS_AFTER),
        (MATCH_EQUAL, MATCH_EQUAL),
        (MATCH_NOT_EQUAL, MATCH_NOT_EQUAL),
        (MATCH_HAS_VALUE, MATCH_HAS_VALUE),
    )

    rule = models.ForeignKey('AutomaticUpdateRule', on_delete=models.PROTECT)
    property_name = models.CharField(max_length=126)
    property_value = models.CharField(max_length=126, null=True)
    match_type = models.CharField(max_length=15)

    class Meta:
        app_label = "data_interfaces"

    def get_case_values(self, case):
        values = case.resolve_case_property(self.property_name)
        return [element.value for element in values]

    def _try_date_conversion(self, date_or_string):
        if (
            not isinstance(date_or_string, date) and
            isinstance(date_or_string, basestring) and
            ALLOWED_DATE_REGEX.match(date_or_string)
        ):
            date_or_string = parse(date_or_string)

        return date_or_string

    def clean_datetime(self, timestamp):
        if not isinstance(timestamp, datetime):
            timestamp = datetime.combine(timestamp, time(0, 0))

        if timestamp.tzinfo:
            # Convert to UTC and make it a naive datetime for comparison to datetime.utcnow()
            timestamp = timestamp.astimezone(pytz.utc).replace(tzinfo=None)

        return timestamp

    def check_days_before(self, case, now):
        values = self.get_case_values(case)
        for date_to_check in values:
            date_to_check = self._try_date_conversion(date_to_check)

            if not isinstance(date_to_check, date):
                continue

            date_to_check = self.clean_datetime(date_to_check)

            days = int(self.property_value)
            if now < (date_to_check - timedelta(days=days)):
                return True

        return False

    def check_days_after(self, case, now):
        values = self.get_case_values(case)
        for date_to_check in values:
            date_to_check = self._try_date_conversion(date_to_check)

            if not isinstance(date_to_check, date):
                continue

            date_to_check = self.clean_datetime(date_to_check)

            days = int(self.property_value)
            if now >= (date_to_check + timedelta(days=days)):
                return True

        return False

    def check_equal(self, case, now):
        return any([
            value == self.property_value for value in self.get_case_values(case)
        ])

    def check_not_equal(self, case, now):
        return any([
            value != self.property_value for value in self.get_case_values(case)
        ])

    def check_has_value(self, case, now):
        values = self.get_case_values(case)
        for value in values:
            if value is None:
                continue
            if isinstance(value, basestring) and not value.strip():
                continue
            return True

        return False

    def matches(self, case, now):
        return {
            self.MATCH_DAYS_BEFORE: self.check_days_before,
            self.MATCH_DAYS_AFTER: self.check_days_after,
            self.MATCH_EQUAL: self.check_equal,
            self.MATCH_NOT_EQUAL: self.check_not_equal,
            self.MATCH_HAS_VALUE: self.check_has_value,
        }.get(self.match_type)(case, now)


class CaseRuleAction(models.Model):
    rule = models.ForeignKey('AutomaticUpdateRule', on_delete=models.PROTECT)
    update_case_definition = models.ForeignKey('UpdateCaseDefinition', on_delete=models.CASCADE, null=True)
    custom_action_definition = models.ForeignKey('CustomActionDefinition', on_delete=models.CASCADE, null=True)

    @property
    def definition(self):
        if self.update_case_definition_id:
            return self.update_case_definition
        elif self.custom_action_definition_id:
            return self.custom_action_definition
        else:
            raise ValueError("No available definition found")

    @definition.setter
    def definition(self, value):
        self.update_case_definition = None
        self.custom_action_definition = None

        if isinstance(value, UpdateCaseDefinition):
            self.update_case_definition = value
        elif isinstance(value, CustomActionDefinition):
            self.custom_action_definition = value
        else:
            raise ValueError("Unexpected type found: %s" % type(value))


class CaseRuleActionResult(object):

    def _validate_int(self, value):
        if not isinstance(value, int):
            raise ValueError("Expected int")

    def __init__(self, num_updates=0, num_closes=0, num_related_updates=0, num_related_closes=0):
        self._validate_int(num_updates)
        self._validate_int(num_closes)
        self._validate_int(num_related_updates)
        self._validate_int(num_related_closes)

        self.num_updates = num_updates
        self.num_closes = num_closes
        self.num_related_updates = num_related_updates
        self.num_related_closes = num_related_closes

    def add_result(self, result):
        self.num_updates += result.num_updates
        self.num_closes += result.num_closes
        self.num_related_updates += result.num_related_updates
        self.num_related_closes += result.num_related_closes


class CaseRuleActionDefinition(models.Model):

    class Meta:
        abstract = True

    def run(self, case):
        """
        Should return an instance of CaseRuleActionResult
        """
        raise NotImplementedError()


class UpdateCaseDefinition(CaseRuleActionDefinition):
    # Expected to be a list of PropertyDefinition objects representing the
    # case properties to update
    properties_to_update = jsonfield.JSONField(default=list)

    # True to close the case, otherwise False
    close_case = models.BooleanField()

    VALUE_TYPE_EXACT = "EXACT"
    VALUE_TYPE_CASE_PROPERTY = "CASE_PROPERTY"

    class PropertyDefinition(JsonObject):
        # The case property name
        name = StringProperty()

        # The type of the value property:
        #   VALUE_TYPE_EXACT means `value` is the exact value to set to the case property referred to by `name`.
        #   VALUE_TYPE_CASE_PROPERTY means `value` is a case property to resolve first and then set to the case
        #   property referred to by `name`.
        value_type = StringProperty()

        # Meaning depends on value_type, see above
        value = StringProperty()

    def get_properties_to_update(self):
        return [self.PropertyDefinition(**fields) for fields in self.properties_to_update]

    def set_properties_to_update(self, properties):
        if not isinstance(properties, (list, tuple)):
            raise ValueError("Expected list or tuple")

        result = []
        for p in properties:
            if not isinstance(p, self.PropertyDefinition):
                raise ValueError("Expected UpdateCaseDefinition.PropertyDefinition")

            result.append(p.to_json())

        self.properties_to_update = result

    def run(self, case):
        cases_to_update = defaultdict(dict)

        def _get_case_property_value(current_case, name):
            result = current_case.resolve_case_property(name)
            if result:
                return result[0].value

            return None

        def _add_update_property(name, value, current_case):
            while name.startswith('parent/'):
                name = name[7:]
                # uses first parent if there are multiple
                parent_cases = current_case.get_parent(identifier=DEFAULT_PARENT_IDENTIFIER)
                if parent_cases:
                    current_case = parent_cases[0]
                else:
                    return
            cases_to_update[current_case.case_id][name] = value

        for prop in self.get_properties_to_update():
            if prop.value_type == self.VALUE_TYPE_CASE_PROPERTY:
                value = _get_case_property_value(case, prop.value)
                if value is None:
                    continue
            elif prop.value_type == self.VALUE_TYPE_EXACT:
                value = prop.value
            else:
                raise ValueError("Unexpected value_type found: %s" % prop.value_type)

            if value != _get_case_property_value(case, prop.name):
                _add_update_property(prop.name, value, case)

        num_updates = 0
        num_closes = 0
        num_related_updates = 0

        # Update any referenced parent cases
        for case_id, properties in cases_to_update.items():
            if case_id == case.case_id:
                continue
            update_case(case.domain, case_id, case_properties=properties, close=False,
                xmlns=AUTO_UPDATE_XMLNS)
            num_related_updates += 1

        # Update / close the case
        properties = cases_to_update[case.case_id]
        if self.close_case or properties:
            update_case(case.domain, case.case_id, case_properties=properties, close=self.close_case,
                xmlns=AUTO_UPDATE_XMLNS)

            if properties:
                num_updates += 1

            if self.close_case:
                num_closes += 1

        return CaseRuleActionResult(
            num_updates=num_updates,
            num_closes=num_closes,
            num_related_updates=num_related_updates,
        )


class CustomActionDefinition(CaseRuleActionDefinition):
    name = models.CharField(max_length=126)


class AutomaticUpdateAction(models.Model):
    ACTION_UPDATE = 'UPDATE'
    ACTION_CLOSE = 'CLOSE'

    ACTION_CHOICES = (
        (ACTION_UPDATE, ACTION_UPDATE),
        (ACTION_CLOSE, ACTION_CLOSE),
    )

    EXACT = "EXACT"
    CASE_PROPERTY = "CASE_PROPERTY"

    PROPERTY_TYPE_CHOICES = (
        (EXACT, ugettext_lazy("Exact value")),
        (CASE_PROPERTY, ugettext_lazy("Case property")),
    )


    rule = models.ForeignKey('AutomaticUpdateRule', on_delete=models.PROTECT)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)

    # property_name and property_value are ignored unless action is UPDATE
    property_name = models.CharField(max_length=126, null=True)
    property_value = models.CharField(max_length=126, null=True)

    property_value_type = models.CharField(max_length=15,
                                           default=EXACT)

    class Meta:
        app_label = "data_interfaces"
