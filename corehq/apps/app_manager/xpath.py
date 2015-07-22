import re
from corehq.apps.app_manager.const import USERCASE_TYPE, SCHEDULE_PHASE, SCHEDULE_LAST_VISIT
from corehq.apps.app_manager.exceptions import LocationXpathValidationError, ScheduleError
from django.utils.translation import ugettext as _


def dot_interpolate(string, replacement):
    """
    Replaces non-decimal dots in `string` with `replacement`
    """
    pattern = r'(\D|^)\.(\D|$)'
    repl = '\g<1>%s\g<2>' % replacement
    return re.sub(pattern, repl, string)


def interpolate_xpath(string, case_xpath=None):
    """
    Replace xpath shortcuts with full value.
    """
    replacements = {
        '#user': UserCaseXPath().case(),
        '#session/': session_var('', path=''),
    }
    if case_xpath:
        replacements['#case'] = case_xpath

    for pattern, repl in replacements.items():
        string = string.replace(pattern, repl)

    if case_xpath:
        return dot_interpolate(string, case_xpath)

    return string


def session_var(var, path=u'data'):
    session = XPath(u"instance('commcaresession')/session")
    if path:
        session = session.slash(path)

    return session.slash(var)


class XPath(unicode):

    def __new__(cls, string=u'', compound=False):
        return super(XPath, cls).__new__(cls, string)

    def __init__(self, string=u'', compound=False):
        self.compound = compound

    def paren(self, force=False):
        return unicode(self) if not (force or self.compound) else u'({})'.format(self)

    def slash(self, xpath):
        if self:
            return XPath(u'%s/%s' % (self, xpath))
        else:
            return XPath(xpath)

    def select_raw(self, expression):
        return XPath(u"{self}[{expression}]".format(self=self, expression=expression))

    def select(self, ref, value, quote=None):
        if quote is None:
            quote = not isinstance(value, XPath)
        if quote:
            value = XPath.string(value)
        return XPath(u"{self}[{ref}={value}]".format(self=self, ref=ref, value=value))

    def count(self):
        return XPath(u'count({self})'.format(self=self))

    def eq(self, b):
        return XPath(u'{} = {}'.format(self, b))

    def neq(self, b):
        return XPath(u'{} != {}'.format(self, b))

    @staticmethod
    def expr(template, args, chainable=False):
        if chainable:
            template = template.join(['{}'] * len(args))

        def check_type(arg):
            return arg if isinstance(arg, XPath) else XPath(arg)

        args = [check_type(arg) for arg in args]

        return XPath(template.format(*[x.paren() for x in args]), compound=True)

    @staticmethod
    def if_(a, b, c):
        return XPath(u"if({}, {}, {})".format(a, b, c))

    @staticmethod
    def string(a):
        # todo: escape text
        return XPath(u"'{}'".format(a))

    @staticmethod
    def and_(*args):
        return XPath.expr(u' and ', args, chainable=True)

    @staticmethod
    def or_(*args):
        return XPath.expr(u' or ', args, chainable=True)

    @staticmethod
    def not_(a):
        return XPath.expr(u"not {}", [a])

    @staticmethod
    def date(a):
        return XPath(u'date({})'.format(a))

    @staticmethod
    def int(a):
        return XPath(u'int({})'.format(a))

    @staticmethod
    def empty_string():
        return XPath(u"''")


class CaseSelectionXPath(XPath):
    selector = ''

    def case(self):
        return CaseXPath(u"instance('casedb')/casedb/case[%s=%s]" % (self.selector, self))


class CaseIDXPath(CaseSelectionXPath):
    selector = '@case_id'


class CaseTypeXpath(CaseSelectionXPath):
    selector = '@case_type'

    def case(self):
        return CaseXPath(u"instance('casedb')/casedb/case[%s='%s']" % (self.selector, self))


class UserCaseXPath(XPath):
    def case(self):
        user_id = session_var(var='userid', path='context')
        return CaseTypeXpath(USERCASE_TYPE).case().select('hq_user_id', user_id).select_raw(1)


class CaseXPath(XPath):

    def index_id(self, name):
        return CaseIDXPath(self.slash(u'index').slash(name))

    def parent_id(self):
        return self.index_id('parent')

    def property(self, property):
        return self.slash(property)

    def status_open(self):
        return self.select('@status', 'open')


class LocationXpath(XPath):

    def location(self, ref, hierarchy):

        def gen_path(types):
            def _gen():
                for type in types:
                    yield '%ss' % type
                    yield type

            return '/'.join(_gen())

        def gen_expr(path):
            query = '[@id = current()/location_id]'
            if not path:
                return query
            else:
                return '[count({path}{query}) > 0]'.format(
                    path=gen_path(path),
                    query=query,
                )

        def ref_to_xpath(input, hierarchy):
            my_type, ref_type, property = self._parse_input(input)
            types = self._ordered_types(hierarchy)
            prefix_path = types[0:types.index(ref_type) + 1]
            prefix = gen_path(prefix_path)
            my_path = types[types.index(ref_type) + 1:types.index(my_type) + 1]
            my_expr = gen_expr(my_path)
            return '{prefix}{expr}/{property}'.format(prefix=prefix, expr=my_expr, property=property)

        self.validate(ref, hierarchy)
        return XPath(u"instance('{instance}')/{ref}").format(instance=self, ref=ref_to_xpath(ref, hierarchy))

    def validate(self, ref, hierarchy):
        my_type, ref_type, property = self._parse_input(ref)
        types = self._ordered_types(hierarchy)
        for type in [my_type, ref_type]:
            if type not in types:
                raise LocationXpathValidationError(
                    _('Type {type} must be in list of domain types: {list}').format(
                        type=type,
                        list=', '.join(types)
                    )
                )

        if types.index(ref_type) > types.index(my_type):
            raise LocationXpathValidationError(
                _('Reference type {ref} cannot be a child of primary type {main}.'.format(
                    ref=ref_type,
                    main=my_type,
                ))
            )

    def _parse_input(self, input):
        try:
            my_type, ref = input.split(':')
            ref_type, property = ref.split('/')
            return my_type, ref_type, property
        except ValueError:
            raise LocationXpathValidationError(_(
                'Property not correctly formatted. '
                'Must be formatted like: loacation:mytype:referencetype/property. '
                'For example: location:outlet:state/name'
            ))

    def _ordered_types(self, hierarchy):
        from corehq.apps.commtrack.util import unicode_slug

        def _gen(hierarchy):
            next_types = set([None])
            while next_types:
                next_type = next_types.pop()
                if next_type is not None:
                    yield next_type
                new_children = hierarchy.get(next_type, [])
                for child in new_children:
                    next_types.add(child)

        return [unicode_slug(t) for t in _gen(hierarchy)]


class LedgerdbXpath(XPath):

    def ledger(self):
        return LedgerXpath(u"instance('ledgerdb')/ledgerdb/ledger[@entity-id=instance('commcaresession')/session/data/%s]" % self)


class LedgerXpath(XPath):

    def section(self, section):
        return LedgerSectionXpath(self.slash(u'section').select(u'@section-id', section))


class LedgerSectionXpath(XPath):

    def entry(self, id):
        return XPath(self.slash(u'entry').select(u'@id', id, quote=False))


class InstanceXpath(XPath):
    id = ''
    path = ''

    def instance(self):
        return XPath(u"instance('{id}')/{path}".format(
            id=self.id,
            path=self.path)
        )


class SessionInstanceXpath(InstanceXpath):
    id = u'commcaresession'
    path = u'session/context'


class ItemListFixtureXpath(InstanceXpath):
    @property
    def id(self):
        return u'item-list:{}'.format(self)

    @property
    def path(self):
        return u'{0}_list/{0}'.format(self)


class ProductInstanceXpath(InstanceXpath):
    id = u'commtrack:products'
    path = u'products/product'


class IndicatorXpath(InstanceXpath):
    path = u'indicators/case[@id = current()/@case_id]'

    @property
    def id(self):
        return self


class CommCareSession(object):
    username = SessionInstanceXpath().instance().slash(u"username")
    userid = SessionInstanceXpath().instance().slash(u"userid")


class ScheduleFixtureInstance(XPath):

    def visit(self):
        return XPath(u"instance('{0}')/schedule/visit".format(self))

    def expires(self):
        return XPath(u"instance('{0}')/schedule/@expires".format(self))


class ScheduleFormXPath(object):
    """
    XPath queries for scheduled forms
    """
    def __init__(self, form, phase, module, include_casedb=False):
        self.form = form
        self.phase = phase
        self.module = module

        try:
            self.anchor = self.phase.anchor
        except AttributeError:
            raise ScheduleError("Phase needs an Anchor")

        if include_casedb:
            self.case_id_xpath = CaseIDXPath(session_var('case_id')).case()

    @property
    def fixture(self):
        from corehq.apps.app_manager import id_strings
        fixture_id = id_strings.schedule_fixture(self.module, self.phase, self.form)
        return ScheduleFixtureInstance(fixture_id)

    @property
    def xpath_phase_set(self):
        """returns the due date if there are valid upcoming schedules"""
        return XPath.if_(self.next_valid_schedules(), self.due_date(), 0)

    @property
    def first_visit_phase_set(self):
        """
        returns the first due date if the case hasn't been visited yet
        otherwise, returns the next due date of valid upcoming schedules
        """
        zeroth_phase = XPath(SCHEDULE_PHASE).eq(XPath.string(''))  # No visits yet
        return XPath.if_(zeroth_phase, self.first_due_date(), self.xpath_phase_set)

    @property
    def filter_condition(self):
        """returns the `relevant` condition on whether to show this form in the list"""
        next_valid_schedules = self.next_valid_schedules()
        num_upcoming_visits = XPath.count(self.upcoming_scheduled_visits())
        num_upcoming_visits_gt_0 = XPath('{} > 0'.format(num_upcoming_visits))
        return XPath.and_(next_valid_schedules, num_upcoming_visits_gt_0)

    def next_valid_schedules(self):
        """
         current_schedule_phase = phase.id and (
           instance(...)/schedule/@expires = ''
           or
           today() < (date(anchor) + instance(...)/schedule/@expires)
         )
        """
        try:
            anchor = self.case_id_xpath.slash(self.anchor)
        except AttributeError:
            anchor = self.anchor

        try:
            current_schedule_phase = self.case_id_xpath.slash(SCHEDULE_PHASE)
        except AttributeError:
            current_schedule_phase = SCHEDULE_PHASE

        expires = self.fixture.expires()

        valid_not_expired = XPath.and_(
            XPath(current_schedule_phase).eq(self.phase.id),
            XPath(anchor).neq(XPath.string('')),
            XPath.or_(
                XPath(expires).eq(XPath.string('')),
                "today() < ({} + {})".format(XPath.date(anchor), expires)
            ))
        return valid_not_expired

    def within_window(self):
        """@late_window = '' or today() <= (date(edd) + int(@due) + int(@late_window))"""
        try:
            anchor = self.case_id_xpath.slash(self.anchor)
        except AttributeError:
            anchor = self.anchor

        return XPath.or_(
            XPath('@late_window').eq(XPath.string('')),
            XPath('today() <= ({} + {} + {})'.format(
                XPath.date(anchor),
                XPath.int('@due'),
                XPath.int('@late_window'))
            )
        )

    def due_first(self):
        """instance(...)/schedule/visit[within_window][1]/@due"""
        return self.fixture.visit().select_raw(self.within_window()).select_raw("1").slash("@due")

    def next_visits(self):
        """@id > last_visit_num_{form_unique_id}"""
        try:
            last_visit = self.case_id_xpath.slash(SCHEDULE_LAST_VISIT.format(self.form.schedule_form_id))
        except AttributeError:
            last_visit = SCHEDULE_LAST_VISIT.format(self.form.schedule_form_id)

        return XPath('@id > {}'.format(last_visit))

    def upcoming_scheduled_visits(self):
        """instance(...)/schedule/visit/[next_visits][within_window]"""
        return (self.fixture.
                visit().
                select_raw(self.next_visits()).
                select_raw(self.within_window()))

    def due_later(self):
        """instance(...)/schedule/visit/[next_visits][within_window][1]/@due"""
        return (self.upcoming_scheduled_visits().
                select_raw("1").
                slash("@due"))

    def first_due_date(self):
        return "{} + {}".format(XPath.date(self.phase.anchor), XPath.int(self.due_first()))

    def due_date(self):
        return "{} + {}".format(XPath.date(self.phase.anchor), XPath.int(self.due_later()))
