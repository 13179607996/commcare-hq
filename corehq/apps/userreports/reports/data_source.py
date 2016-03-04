from collections import OrderedDict

from sqlalchemy.exc import ProgrammingError

from dimagi.utils.decorators.memoized import memoized
from sqlagg import (
    ColumnNotFoundException,
    TableNotFoundException,
)
from sqlagg.columns import SimpleColumn
from sqlagg.sorting import OrderBy

from corehq.apps.reports.sqlreport import SqlData, DatabaseColumn
from corehq.apps.userreports.exceptions import (
    UserReportsError, TableNotFoundWarning,
)
from corehq.apps.userreports.models import DataSourceConfiguration, get_datasource_config
from corehq.apps.userreports.reports.sorting import ASCENDING
from corehq.apps.userreports.sql import get_table_name
from corehq.apps.userreports.sql.connection import get_engine_id


class ConfigurableReportDataSource(SqlData):

    def __init__(self, domain, config_or_config_id, filters, aggregation_columns, columns, order_by):
        self.lang = None
        self.domain = domain
        if isinstance(config_or_config_id, DataSourceConfiguration):
            self._config = config_or_config_id
            self._config_id = self._config._id
        else:
            assert isinstance(config_or_config_id, basestring)
            self._config = None
            self._config_id = config_or_config_id

        self._filters = {f.slug: f for f in filters}
        self._filter_values = {}
        self._deferred_filters = {}
        self._order_by = order_by
        self._aggregation_columns = aggregation_columns
        self._column_configs = OrderedDict()
        for column in columns:
            # should be caught in validation prior to reaching this
            assert column.column_id not in self._column_configs, \
                'Report {} in domain {} has more than one {} column defined!'.format(
                    self._config_id, self.domain, column.column_id,
                )
            self._column_configs[column.column_id] = column

    @property
    def aggregation_columns(self):
        return self._aggregation_columns + [
            deferred_filter.field for deferred_filter in self._deferred_filters.values()
            if deferred_filter.field not in self._aggregation_columns]

    @property
    def config(self):
        if self._config is None:
            self._config, _ = get_datasource_config(self._config_id, self.domain)
        return self._config

    @property
    def engine_id(self):
        return get_engine_id(self.config)

    @property
    def column_configs(self):
        return self._column_configs.values()

    @property
    def table_name(self):
        return get_table_name(self.domain, self.config.table_id)

    @property
    def filters(self):
        return filter(None, [fv.to_sql_filter() for fv in self._filter_values.values()])

    def set_filter_values(self, filter_values):
        for filter_slug, value in filter_values.items():
            self._filter_values[filter_slug] = self._filters[filter_slug].create_filter_value(value)

    def defer_filters(self, filter_slugs):
        self._deferred_filters.update({
            filter_slug: self._filters[filter_slug] for filter_slug in filter_slugs})

    def set_order_by(self, columns):
        self._order_by = columns

    @property
    def filter_values(self):
        return {k: v for fv in self._filter_values.values() for k, v in fv.to_sql_values().items()}

    @property
    def group_by(self):
        def _contributions(column_id):
            # ask each column for its group_by contribution and combine to a single list
            # if the column isn't found just treat it as a normal field
            if column_id in self._column_configs:
                return self._column_configs[column_id].get_group_by_columns()
            else:
                return [column_id]

        return [
            group_by for col_id in self.aggregation_columns
            for group_by in _contributions(col_id)
        ]

    @property
    def order_by(self):
        if self._order_by:
            return [
                OrderBy(sort_column_id, order == ASCENDING)
                for sort_column_id, order in self._order_by
                if self._column_configs[sort_column_id].type != 'percent'
            ]
        return [
            OrderBy(self.column_configs[0].column_id, is_ascending=True)
        ] if self.column_configs[0].type != 'percent' else []

    @property
    def columns(self):
        db_columns = [c for sql_conf in self.sql_column_configs for c in sql_conf.columns]
        fields = {c.slug for c in db_columns}

        return db_columns + [
            DatabaseColumn('', SimpleColumn(deferred_filter.field))
            for deferred_filter in self._deferred_filters.values()
            if deferred_filter.field not in fields]

    @property
    def sql_column_configs(self):
        return [col.get_sql_column_config(self.config, self.lang) for col in self.column_configs]

    @property
    def column_warnings(self):
        return [w for sql_conf in self.sql_column_configs for w in sql_conf.warnings]

    @memoized
    def get_data(self, start=None, limit=None):
        try:
            ret = super(ConfigurableReportDataSource, self).get_data(start=start, limit=limit)
        except (
            ColumnNotFoundException,
            ProgrammingError,
        ) as e:
            raise UserReportsError(unicode(e))
        except TableNotFoundException:
            raise TableNotFoundWarning

        for report_column in self.column_configs:
            report_column.format_data(ret)
        return ret

    @property
    def has_total_row(self):
        return any(column_config.calculate_total for column_config in self.column_configs)

    def get_total_records(self):
        # TODO - actually use sqlagg to get a count of rows
        return len(self.get_data())
