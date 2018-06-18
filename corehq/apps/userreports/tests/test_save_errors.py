from __future__ import absolute_import
from __future__ import unicode_literals
import uuid

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from django.test import TestCase, override_settings

from corehq.apps.userreports.app_manager.helpers import clean_table_name
from corehq.apps.userreports.const import UCR_ES_BACKEND
from corehq.apps.userreports.exceptions import TableNotFoundWarning, MissingColumnWarning
from corehq.apps.userreports.models import DataSourceConfiguration
from corehq.apps.userreports.util import get_indicator_adapter, get_table_name
from six.moves import range


def get_sample_config(domain=None):
    return DataSourceConfiguration(
        domain=domain or 'domain',
        display_name='foo',
        referenced_doc_type='CommCareCase',
        table_id=clean_table_name('domain', str(uuid.uuid4().hex)),
        configured_indicators=[{
            "type": "expression",
            "expression": {
                "type": "property_name",
                "property_name": 'name'
            },
            "column_id": 'name',
            "display_name": 'name',
            "datatype": "string"
        }],
    )


class SaveErrorsTest(TestCase):

    def setUp(self):
        self.config = get_sample_config()

    def test_raise_error_for_missing_table(self):
        adapter = get_indicator_adapter(self.config, raise_errors=True)
        adapter.drop_table()

        doc = {
            "_id": '123',
            "domain": "domain",
            "doc_type": "CommCareCase",
            "name": 'bob'
        }
        with self.assertRaises(TableNotFoundWarning):
            adapter.best_effort_save(doc)

    def test_missing_column(self):
        adapter = get_indicator_adapter(self.config, raise_errors=True)
        adapter.build_table()
        with adapter.engine.begin() as connection:
            context = MigrationContext.configure(connection)
            op = Operations(context)
            op.drop_column(adapter.get_table().name, 'name')

        doc = {
            "_id": '123',
            "domain": "domain",
            "doc_type": "CommCareCase",
            "name": 'bob'
        }
        with self.assertRaises(MissingColumnWarning):
            adapter.best_effort_save(doc)


class AdapterBulkSaveTest(TestCase):

    def setUp(self):
        self.domain = 'adapter_bulk_save'
        self.config = get_sample_config(domain=self.domain)
        self.config.save()
        self.adapter = get_indicator_adapter(self.config, raise_errors=True)

    def tearDown(self):
        self.config.delete()
        self.adapter.clear_table()

    def test_bulk_save(self):
        docs = []
        for i in range(10):
            docs.append({
                "_id": str(i),
                "domain": self.domain,
                "doc_type": "CommCareCase",
                "name": 'doc_name_' + str(i)
            })

        self.adapter.build_table()
        self.adapter.bulk_save(docs)
        self.adapter.refresh_table()
        self.assertEqual(self.adapter.get_query_object().count(), 10)

        self.adapter.bulk_delete([doc['_id'] for doc in docs])
        self.adapter.refresh_table()
        self.assertEqual(self.adapter.get_query_object().count(), 0)


@override_settings(OVERRIDE_UCR_BACKEND=UCR_ES_BACKEND)
class AdapterBulkSaveESTest(AdapterBulkSaveTest):
    pass
