from __future__ import absolute_import

from collections import OrderedDict
from datetime import datetime

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrule, MONTHLY
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.generic.base import View

from corehq.apps.domain.decorators import login_and_domain_required
from custom.champ.sqldata import TargetsDataSource, UICFromEPMDataSource, UICFromCCDataSource, HivStatusDataSource, \
    FormCompletionDataSource, FirstArtDataSource, LastVLTestDataSource, ChampFilter
from custom.champ.utils import PREVENTION_XMLNS, POST_TEST_XMLNS, ACCOMPAGNEMENT_XMLNS, SUIVI_MEDICAL_XMLNS, \
    ENHANCED_PEER_MOBILIZATION, CHAMP_CAMEROON, TARGET_XMLNS

@method_decorator([login_and_domain_required], name='dispatch')
class PrevisionVsAchievementsView(View):

    def get_target_data(self, domain, request):
        config = {
            'domain': domain,
            'district': request.POST.get('target_district', None),
            'cbo': request.POST.get('target_cbo', None),
            'clienttype': request.POST.get('target_clienttype', None),
            'userpl': request.POST.get('target_userpl', None),
            'fiscal_year': request.POST.get('target_fiscal_year', None),
        }
        target_data = TargetsDataSource(config=config).data
        return target_data

    def get_kp_prev_achievement(self, domain, request):
        config = {
            'domain': domain,
            'age': request.POST.get('kp_prev_age', None),
            'district': request.POST.get('kp_prev_district', None),
            'visit_date_start': request.POST.get('kp_prev_visit_date_start', None),
            'visit_date_end': request.POST.get('kp_prev_visit_date_end', None),
            'activity_type': request.POST.get('kp_prev_activity_type', None),
            'type_visit': request.POST.get('kp_prev_visit_type', None),
            'client_type': request.POST.get('kp_prev_client_type', None),
            'mobile_user_group': request.POST.get('kp_prev_mobile_user_group', None),
        }
        achievement = UICFromEPMDataSource(config=config).data
        return achievement.get(PREVENTION_XMLNS, {}).get('uic', 0)

    def get_htc_tst_achievement(self, domain, request):
        config = {
            'domain': domain,
            'posttest_date_start': request.POST.get('htc_tst_posttest_date_start', None),
            'posttest_date_end': request.POST.get('htc_tst_posttest_date_end', None),
            'hiv_test_date_start': request.POST.get('htc_tst_hiv_test_date_start', None),
            'hiv_test_date_end': request.POST.get('htc_tst_hiv_test_date_end', None),
            'age_range': request.POST.get('htc_tst_age_range', None),
            'district': request.POST.get('htc_tst_district', None),
            'mobile_user_group': request.POST.get('htc_tst_mobile_user_group', None),
        }
        achievement = UICFromCCDataSource(config=config).data
        return achievement.get(POST_TEST_XMLNS, {}).get('uic', 0)

    def get_htc_pos_achievement(self, domain, request):
        config = {
            'domain': domain,
            'posttest_date_start': request.POST.get('htc_pos_posttest_date_start', None),
            'posttest_date_end': request.POST.get('htc_pos_posttest_date_end', None),
            'hiv_test_date_start': request.POST.get('htc_pos_hiv_test_date_start', None),
            'hiv_test_date_end': request.POST.get('htc_pos_hiv_test_date_end', None),
            'age_range': request.POST.get('htc_pos_age_range', None),
            'district': request.POST.get('htc_pos_district', None),
            'client_type': request.POST.get('htc_pos_client_type', None),
            'mobile_user_group': request.POST.get('htc_pos_mobile_user_group', None),
        }
        achievement = HivStatusDataSource(config=config).data
        return achievement.get(POST_TEST_XMLNS, {}).get('uic', 0)

    def get_care_new_achivement(self, domain, request):
        config = {
            'domain': domain,
            'hiv_status': request.POST.get('care_new_hiv_status', None),
            'client_type': request.POST.get('care_new_client_type', None),
            'age_range': request.POST.get('care_new_age_range', None),
            'district': request.POST.get('care_new_district', None),
            'date_handshake_start': request.POST.get('care_new_date_handshake_start', None),
            'date_handshake_end': request.POST.get('care_new_date_handshake_end', None),
            'mobile_user_group': request.POST.get('care_new_mobile_user_group', None),
        }
        achievement = FormCompletionDataSource(config=config).data
        return achievement.get(ACCOMPAGNEMENT_XMLNS, {}).get('uic', 0)

    def get_tx_new_achivement(self, domain, request):
        config = {
            'domain': domain,
            'hiv_status': request.POST.get('tx_new_hiv_status', None),
            'client_type': request.POST.get('tx_new_client_type', None),
            'age_range': request.POST.get('tx_new_age_range', None),
            'district': request.POST.get('tx_new_district', None),
            'first_art_date_start': request.POST.get('tx_new_first_art_date_start', None),
            'first_art_date_end': request.POST.get('tx_new_first_art_date_end', None),
            'mobile_user_group': request.POST.get('tx_new_mobile_user_group', None),
        }
        achievement = FirstArtDataSource(config=config).data
        return achievement.get(SUIVI_MEDICAL_XMLNS, {}).get('uic', 0)

    def get_tx_undetect_achivement(self, domain, request):
        config = {
            'domain': domain,
            'hiv_status': request.POST.get('tx_undetect_hiv_status', None),
            'client_type': request.POST.get('tx_undetect_client_type', None),
            'age_range': request.POST.get('tx_undetect_age_range', None),
            'district': request.POST.get('tx_undetect_district', None),
            'date_last_vl_test_start': request.POST.get('tx_undetect_date_last_vl_test_start', None),
            'date_last_vl_test_end': request.POST.get('tx_undetect_date_last_vl_test_end', None),
            'undetect_vl': request.POST.get('tx_undetect_undetect_vl', None),
            'mobile_user_group': request.POST.get('tx_undetect_mobile_user_group', None),
        }
        achievement = LastVLTestDataSource(config=config).data
        return achievement.get(SUIVI_MEDICAL_XMLNS, {}).get('uic', 0)

    def generate_data(self, domain, request):
        targets = self.get_target_data(domain, request)
        return {
            'chart': [
                {
                    'key': 'Target',
                    'color': 'blue',
                    'values': [
                        {'x': 'KP_PREV', 'y': targets.get('target_kp_prev', 0)},
                        {'x': 'HTC_TST', 'y': targets.get('target_htc_tst', 0)},
                        {'x': 'HTC_POS', 'y': targets.get('target_htc_pos', 0)},
                        {'x': 'CARE_NEW', 'y': targets.get('target_care_new', 0)},
                        {'x': 'TX_NEW', 'y': targets.get('target_tx_new', 0)},
                        {'x': 'TX_UNDETECT', 'y': targets.get('target_tx_undetect', 0)}
                    ]
                },
                {
                    'key': 'Achievements',
                    'color': 'orange',
                    'values': [
                        {'x': 'KP_PREV', 'y': self.get_kp_prev_achievement(domain, request)},
                        {'x': 'HTC_TST', 'y': self.get_htc_tst_achievement(domain, request)},
                        {'x': 'HTC_POS', 'y': self.get_htc_pos_achievement(domain, request)},
                        {'x': 'CARE_NEW', 'y': self.get_care_new_achivement(domain, request)},
                        {'x': 'TX_NEW', 'y': self.get_tx_new_achivement(domain, request)},
                        {'x': 'TX_UNDETECT', 'y': self.get_tx_undetect_achivement(domain, request)}
                    ]
                }
            ]
        }

    def post(self, request, *args, **kwargs):
        domain = self.kwargs['domain']
        return JsonResponse(data=self.generate_data(domain, request))


@method_decorator([login_and_domain_required], name='dispatch')
class PrevisionVsAchievementsTableView(View):

    def generate_data(self, domain, request):
        config = {
            'domain': domain,
            'district': request.POST.get('district', None),
            'visit_type': request.POST.get('visit_type', None),
            'activity_type': request.POST.get('activity_type', None),
            'client_type': request.POST.get('client_type', None),
            'organization': request.POST.get('organization', None),
            'visit_date_start': request.POST.get('visit_date_start', None),
            'visit_date_end': request.POST.get('visit_date_end', None),
            'post_date_start': request.POST.get('post_date_start', None),
            'post_date_end': request.POST.get('post_date_end', None),
            'first_art_date_start': request.POST.get('first_art_date_start', None),
            'first_art_date_end': request.POST.get('first_art_date_end', None),
            'date_handshake_start': request.POST.get('date_handshake_start', None),
            'date_handshake_end': request.POST.get('date_handshake_end', None),
            'date_last_vl_test_start': request.POST.get('date_last_vl_test_start', None),
            'date_last_vl_test_end': request.POST.get('date_last_vl_test_end', None),
        }
        targets = TargetsDataSource(config=config).data
        kp_prev = UICFromEPMDataSource(config=config).data
        htc_tst = UICFromCCDataSource(config=config).data
        htc_pos = HivStatusDataSource(config=config).data
        care_new = FormCompletionDataSource(config=config).data
        tx_new = FirstArtDataSource(config=config).data
        tz_undetect = LastVLTestDataSource(config=config).data

        return {
            'target_kp_prev': targets.get('target_kp_prev', 0),
            'target_htc_tst': targets.get('target_htc_tst', 0),
            'target_htc_pos': targets.get('target_htc_pos', 0),
            'target_care_new': targets.get('target_care_new', 0),
            'target_tx_new': targets.get('target_tx_new', 0),
            'target_tx_undetect': targets.get('target_tx_undetect', 0),
            'kp_prev': kp_prev.get(PREVENTION_XMLNS, {}).get('uic', 0),
            'htc_tst': htc_tst.get(POST_TEST_XMLNS, {}).get('uic', 0),
            'htc_pos': htc_pos.get(POST_TEST_XMLNS, {}).get('uic', 0),
            'care_new': care_new.get(ACCOMPAGNEMENT_XMLNS, {}).get('uic', 0),
            'tx_new': tx_new.get(SUIVI_MEDICAL_XMLNS, {}).get('uic', 0),
            'tx_undetect': tz_undetect.get(SUIVI_MEDICAL_XMLNS, {}).get('uic', 0),
        }

    def post(self, request, *args, **kwargs):
        domain = self.kwargs['domain']
        return JsonResponse(data=self.generate_data(domain, request))


@method_decorator([login_and_domain_required], name='dispatch')
class ServiceUptakeView(View):

    def generate_data(self, domain, request):
        month_start = request.POST.get('month_start', 1)
        year_start = request.POST.get('year_start', datetime.now().year)
        month_end = request.POST.get('month_start', datetime.now().month)
        year_end = request.POST.get('year_start', datetime.now().year)

        start_date = datetime(year_start, month_start, 1)
        end_date = datetime(year_end, month_end + 1, 1) - relativedelta(days=1)

        config = {
            'domain': domain,
            'district': request.POST.get('district', None),
            'visit_type': request.POST.get('visit_type', None),
            'activity_type': request.POST.get('activity_type', None),
            'client_type': request.POST.get('client_type', None),
            'organization': request.POST.get('organization', None),
            'visit_date_start': start_date,
            'visit_date_end': end_date,
            'posttest_date_start': start_date,
            'posttest_date_end': end_date,
            'date_handshake_start': start_date,
            'date_handshake_end': end_date,
        }

        kp_prev = UICFromEPMDataSource(config=config, replace_group_by='kp_prev_month').data
        htc_tst = UICFromCCDataSource(config=config, replace_group_by='htc_month').data
        htc_pos = HivStatusDataSource(config=config, replace_group_by='htc_month').data
        care_new = FormCompletionDataSource(config=config, replace_group_by='care_new_month').data

        htc_uptake_chart_data = OrderedDict()
        htc_yield_chart_data = OrderedDict()
        link_chart_data = OrderedDict()

        rrule_dates = [rrule_date for rrule_date in rrule(MONTHLY, dtstart=start_date, until=end_date)]
        for rrule_dt in rrule_dates:
            date_in_milliseconds = int(rrule_dt.date().strftime("%s")) * 1000
            htc_uptake_chart_data.update({date_in_milliseconds: 0})
            htc_yield_chart_data.update({date_in_milliseconds: 0})
            link_chart_data.update({date_in_milliseconds: 0})

        for row in htc_tst.values():
            date = row['htc_month']
            date_in_milliseconds = int(date.strftime("%s")) * 1000
            nom = (row['uic'] or 0)
            denom = (kp_prev[date]['uic'] or 1) if date in kp_prev else 1
            htc_uptake_chart_data[date_in_milliseconds] = nom / float(denom)

        for row in htc_pos.values():
            date = row['htc_month']
            date_in_milliseconds = int(date.strftime("%s")) * 1000
            nom = (row['uic'] or 0)
            denom = (htc_tst[date]['uic'] or 1) if date in htc_tst else 1
            htc_yield_chart_data[date_in_milliseconds] = nom / float(denom)

        for row in care_new.values():
            date = row['care_new_month']
            date_in_milliseconds = int(date.strftime("%s")) * 1000
            nom = (row['uic'] or 0)
            denom = (htc_pos[date]['uic'] or 1) if date in htc_pos else 1
            link_chart_data[date_in_milliseconds] = nom / float(denom)

        return {
            'chart': [
                {
                    "values": [
                        {'x': key, 'y': value} for key, value in htc_uptake_chart_data.items()
                    ],
                    "key": "HTC_uptake",
                    "strokeWidth": 2,
                    "classed": "dashed",
                    "color": "blue"
                },
                {
                    "values": [
                        {'x': key, 'y': value} for key, value in htc_yield_chart_data.items()
                    ],
                    "key": "HTC_yield",
                    "strokeWidth": 2,
                    "classed": "dashed",
                    "color": "orange"
                },
                {
                    "values": [
                        {'x': key, 'y': value} for key, value in link_chart_data.items()
                    ],
                    "key": "Link to care",
                    "strokeWidth": 2,
                    "classed": "dashed",
                    "color": "gray"
                }
            ]
        }

    def post(self, request, *args, **kwargs):
        domain = self.kwargs['domain']
        return JsonResponse(data=self.generate_data(domain, request))


@method_decorator([login_and_domain_required], name='dispatch')
class ChampFilterView(View):
    xmlns = None
    table_name = None
    column_name = None

    def get(self, request, *args, **kwargs):
        domain = self.kwargs['domain']
        return JsonResponse(data={
            'options': ChampFilter(domain, self.xmlns, self.table_name, self.column_name).data
        })


class PreventionPropertiesFilter(ChampFilterView):
    xmlns = PREVENTION_XMLNS
    table_name = ENHANCED_PEER_MOBILIZATION


class PostTestFilter(ChampFilterView):
    xmlns = POST_TEST_XMLNS
    table_name = CHAMP_CAMEROON


class TargetFilter(ChampFilterView):
    xmlns = TARGET_XMLNS
    table_name = ENHANCED_PEER_MOBILIZATION


class DistrictFilterPrevView(PreventionPropertiesFilter):
    column_name = 'district'


class CBOFilterView(TargetFilter):
    column_name = 'cbo'


class UserPLFilterView(TargetFilter):
    column_name = 'userpl'