from __future__ import absolute_import
from __future__ import unicode_literals
import os
import yaml

from corehq.apps.aggregate_ucrs.parser import AggregationSpec
from corehq.util.test_utils import TestFileMixin


class AggregationBaseTestMixin(TestFileMixin):
    file_path = ('data', 'table_definitions')
    root = os.path.dirname(__file__)

    @classmethod
    def get_config_json(cls):
        config_yml = cls.get_file('monthly_aggregate_definition', 'yml')
        return yaml.load(config_yml)

    @classmethod
    def get_config_spec(cls):
        return AggregationSpec.wrap(cls.get_config_json())
