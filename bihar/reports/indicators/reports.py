from bihar.reports.supervisor import BiharNavReport, MockEmptyReport, \
    url_and_params, BiharSummaryReport, \
    ConvenientBaseMixIn, GroupReferenceMixIn, list_prompt, shared_bihar_context,\
    team_member_context
from copy import copy
from casexml.apps.case.models import CommCareCase
from corehq.apps.reports.generic import GenericTabularReport, summary_context
from corehq.apps.reports.standard import CustomProjectReport
from dimagi.utils.decorators.memoized import memoized
from dimagi.utils.html import format_html
from django.utils.translation import ugettext as _, ugettext_noop
from bihar.reports.indicators.mixins import IndicatorSetMixIn, IndicatorMixIn

DEFAULT_EMPTY = "?"


class IndicatorNav(GroupReferenceMixIn, BiharNavReport):
    name = ugettext_noop("Indicator Options")
    slug = "indicatornav"
    description = ugettext_noop("Indicator navigation")
    preserve_url_params = True
    report_template_path = "bihar/team_listing_tabular.html"
    
    extra_context_providers = [shared_bihar_context, summary_context, team_member_context]
    @property
    def reports(self):
        return [IndicatorClientSelectNav, IndicatorSummaryReport]

    @property
    def rendered_report_title(self):
        return self.group_display


class IndicatorSummaryReport(GroupReferenceMixIn, BiharSummaryReport,
                             IndicatorSetMixIn):
    
    name = ugettext_noop("Indicators")
    slug = "indicatorsummary"
    description = "Indicator details report"
    base_template_mobile = "bihar/indicator_summary.html"
    is_cacheable = True

    @property
    def rendered_report_title(self):
        return _(self.indicator_set.name)

    @property
    def summary_indicators(self):
        return [i for i in self.indicator_set.get_indicators() if i.show_in_indicators]
    
    @property
    def _headers(self):
        return [_("Team Name")] + [_(i.name) for i in self.summary_indicators]
    
    @property
    @memoized
    def data(self):
        def _nav_link(indicator):
            params = copy(self.request_params)
            params['indicator'] = indicator.slug
            del params['next_report']
            return format_html(u'{chart}<a href="{next}">{val}</a>',
                val=self.get_indicator_value(indicator),
                chart=self.get_chart(indicator),
                next=url_and_params(
                    IndicatorClientList.get_url(self.domain, 
                                                render_as=self.render_next),
                    params
            ))

        return [self.group_display] + \
               [_nav_link(i) for i in self.summary_indicators]

    def get_indicator_value(self, indicator):
        if indicator.fluff_calculator:
            results = (
                indicator.fluff_calculator.get_result(
                    [self.domain, owner_id]
                )
                for owner_id in self.all_owner_ids
            )
            num, denom = map(sum, zip(*[
                (r['numerator'], r['denominator'])
                for r in results
            ]))
            return "%s/%s" % (num, denom)
        else:
            return indicator.display(self.cases)

    def get_chart(self, indicator):
        # this is a serious hack for now
        pie_class = 'sparkpie'
        split = self.get_indicator_value(indicator).split("/")
        chart_template = (
            '<span data-numerator="{num}" '
            'data-denominator="{denom}" class="{pie_class}"></span>'
        )
        if len(split) == 2:
            return format_html(chart_template, num=split[0],
                               denom=int(split[1]) - int(split[0]),
                               pie_class=pie_class)
        return ''  # no chart


class IndicatorCharts(MockEmptyReport):
    name = ugettext_noop("Charts")
    slug = "indicatorcharts"


class IndicatorClientSelectNav(GroupReferenceMixIn, BiharSummaryReport,
                               IndicatorSetMixIn):
    name = ugettext_noop("Select Client List")
    slug = "clients"
    is_cacheable = True
    
    _indicator_type = "client_list"

    @property
    def rendered_report_title(self):
        return self.group_display

    @property
    def indicators(self):
        return [i for i in self.indicator_set.get_indicators() if i.show_in_client_list]
    
    @property
    def _headers(self):
        return [list_prompt(i, iset.name) for i, iset in enumerate(self.indicators)]

    @property
    def data(self):
        def _nav_link(indicator):
            params = copy(self.request_params)
            params["indicators"] = self.indicator_set.slug
            params["indicator"] = indicator.slug
            return format_html(u'<a href="{next}">{val}</a>',
                val=self.count(indicator),
                next=url_and_params(
                    IndicatorClientList.get_url(domain=self.domain,
                                                render_as=self.render_next),
                    params
                ))

        return [_nav_link(i) for i in self.indicators]

    def count(self, indicator):
        if indicator.fluff_calculator:
            return sum(
                indicator.fluff_calculator.get_result(
                    [self.domain, owner_id]
                )['total']
                for owner_id in self.all_owner_ids
            )
        else:
            return len([c for c in self.cases if indicator.filter(c)])


def name_context(report):
    return {'name': report._name}


class IndicatorClientList(GroupReferenceMixIn, ConvenientBaseMixIn,
                          GenericTabularReport, CustomProjectReport,
                          IndicatorMixIn):
    slug = "indicatorclientlist"
    name = ugettext_noop("Client List") 
    is_cacheable = True
    report_template_path = "bihar/client_listing.html"

    extra_context_providers = [name_context]

    @property
    def _name(self):
        # NOTE: this isn't currently used, but is how things should work
        # once we have a workaround for name needing to be available at
        # the class level.
        try:
            return self.indicator.name
        except AttributeError:
            return self.name

    @property
    def _headers(self):
        return [_(c) for c in self.indicator.get_columns()]

    @property
    def sorted_cases(self):
        return sorted(self.cases, key=self.indicator.sortkey)
        
    def _filter(self, case):
        if self.indicator:
            return self.indicator.filter(case)
        else:
            return True
    
    def _get_clients(self):
        for c in self.sorted_cases:
            if self._filter(c):
                yield c
        
    @property
    def rows(self):
        if self.indicator.fluff_calculator:
            case_ids = set()
            for owner_id in self.all_owner_ids:
                result = self.indicator.fluff_calculator.get_result(
                    [self.domain, owner_id],
                    reduce=False
                )
                case_ids.update(result[self.indicator.fluff_calculator.primary])
            cases = CommCareCase.view('_all_docs', keys=list(case_ids),
                                      include_docs=True)
            return map(self.indicator.as_row, cases)
        else:
            return [self.indicator.as_row(c) for c in self._get_clients()]
