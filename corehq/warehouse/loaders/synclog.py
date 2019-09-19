from corehq.warehouse.const import SYNCLOG_STAGING_SLUG, SYNCLOG_FACT_SLUG, USER_DIM_SLUG, DOMAIN_DIM_SLUG
from corehq.warehouse.dbaccessors import get_synclogs_by_date
from corehq.warehouse.etl import HQToWarehouseETLMixin, CustomSQLETLMixin, slug_to_table_map
from corehq.warehouse.loaders.base import BaseStagingLoader, BaseLoader
from corehq.warehouse.models import SyncLogStagingTable, SyncLogFact


class SyncLogStagingLoader(HQToWarehouseETLMixin, BaseStagingLoader):
    """
    Represents the staging table to dump data before loading into the SyncLogFact

    Grain: sync_log_id
    """
    slug = SYNCLOG_STAGING_SLUG
    model_cls = SyncLogStagingTable

    def field_mapping(self):
        return [
            ('synclog_id', 'sync_log_id'),
            ('date', 'sync_date'),
            ('domain', 'domain'),
            ('user_id', 'user_id'),
            ('build_id', 'build_id'),
            ('duration', 'duration'),
        ]

    def record_iter(self, start_datetime, end_datetime):
        return get_synclogs_by_date(start_datetime, end_datetime)


class SyncLogFactLoader(CustomSQLETLMixin, BaseLoader):
    """
    SyncLog Fact Table
    Grain: sync_log_id
    """
    slug = SYNCLOG_FACT_SLUG
    model_cls = SyncLogFact

    def dependant_slugs(self):
        return [
            USER_DIM_SLUG,
            DOMAIN_DIM_SLUG,
            SYNCLOG_STAGING_SLUG,
        ]
