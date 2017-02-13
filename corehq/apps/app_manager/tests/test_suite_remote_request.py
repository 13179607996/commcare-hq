# -*- coding: utf-8 -*-
from django.test import SimpleTestCase
from mock import patch

from corehq.apps.app_manager.const import CLAIM_DEFAULT_RELEVANT_CONDITION
from corehq.apps.app_manager.models import (
    Application,
    Module,
    CaseSearch,
    CaseSearchProperty,
    DefaultCaseSearchProperty,
    DetailColumn
)
from corehq.apps.app_manager.tests.util import TestXmlMixin, SuiteMixin, parse_normalize

DOMAIN = 'test_domain'


class RemoteRequestSuiteTest(SimpleTestCase, TestXmlMixin, SuiteMixin):
    file_path = ('data', 'suite')

    def setUp(self):
        self.app = Application.new_app(DOMAIN, "Untitled Application")
        self.module = self.app.add_module(Module.new_module("Untitled Module", None))
        self.app.new_form(0, "Untitled Form", None)
        self.module.case_type = 'case'
        # chosen xpath just used to reference more instances - not considered valid to use in apps
        self.module.case_details.short.columns.append(
            DetailColumn(header={"en": "report_name"}, model="case", field="whatever",
                         calc_xpath="instance('reports')/report[1]/name")
        )
        self.module.case_details.long.columns.append(
            DetailColumn(header={"en": "ledger_name"}, model="case", field="whatever",
                         calc_xpath="instance('ledgerdb')/ledgers/name/name")
        )
        self.module.search_config = CaseSearch(
            command_label={'en': 'Search Patients Nationally'},
            properties=[
                CaseSearchProperty(name='name', label={'en': 'Name'}),
                CaseSearchProperty(name='dob', label={'en': 'Date of birth'})
            ],
            relevant="{} and {}".format("instance('groups')/groups/group", CLAIM_DEFAULT_RELEVANT_CONDITION),
            default_properties=[
                DefaultCaseSearchProperty(
                    property=u'ɨŧsȺŧɍȺᵽ',
                    defaultValue=(
                        u"instance('casedb')/case"
                        u"[@case_id='instance('commcaresession')/session/data/case_id']"
                        u"/ɨŧsȺŧɍȺᵽ")
                ),
                DefaultCaseSearchProperty(
                    property='name',
                    defaultValue="instance('locations')/locations/location[@id=123]/@type",
                ),
            ],
        )

    def test_remote_request(self):
        """
        Suite should include remote-request if searching is configured
        """
        with patch('corehq.util.view_utils.get_url_base') as get_url_base_patch:
            get_url_base_patch.return_value = 'https://www.example.com'
            suite = self.app.create_suite()
        self.assertXmlPartialEqual(self.get_xml('remote_request'), suite, "./remote-request[1]")

    def test_case_search_action(self):
        """
        Case search action should be added to case list
        """
        suite = self.app.create_suite()
        self.assertXmlPartialEqual(self.get_xml('search_command_detail'), suite, "./detail[1]")

    def test_case_search_action_relevant_condition(self):
        condition = "'foo' = 'bar'"
        self.module.search_config.search_button_display_condition = condition
        suite = self.app.create_suite()
        suite = parse_normalize(suite, to_string=False)
        self.assertEqual(condition, suite.xpath('./detail[1]/action/@relevant')[0])
