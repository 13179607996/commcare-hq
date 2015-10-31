from datetime import datetime, timedelta
from corehq.apps.commtrack.models import StockState
from corehq.apps.locations.models import SQLLocation
from custom.ewsghana.alerts import ONGOING_NON_REPORTING
from custom.ewsghana.alerts.alert import WeeklyAlert


class OnGoingNonReporting(WeeklyAlert):

    message = ONGOING_NON_REPORTING

    def get_sql_locations(self):
        return SQLLocation.objects.filter(domain=self.domain, location_type__name='district')

    def program_clause(self, user_program, not_reported_programs):
        return not_reported_programs and (not user_program or user_program in not_reported_programs)

    def get_data(self, sql_location):
        data = {}
        date_until = datetime.utcnow() - timedelta(days=21)
        for child in sql_location.get_descendants().filter(location_type__administrative=False):
            location_products = set(child.products)
            location_programs = {p.program_id for p in child.products}
            data[child.name] = location_programs - set(StockState.objects.filter(
                case_id=child.supply_point_id,
                sql_product__in=location_products,
                last_modified_date__gte=date_until
            ).values_list('sql_product__program_id', flat=True))

        return data
