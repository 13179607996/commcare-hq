from __future__ import absolute_import
from __future__ import unicode_literals

import json

from django.test import Client, TestCase
from django.urls import reverse

from mock import patch

from corehq.apps.api.odata.tests.utils import OdataTestMixin
from corehq.apps.domain.models import Domain
from corehq.apps.users.models import WebUser
from corehq.util.test_utils import flag_enabled


class TestServiceDocument(TestCase, OdataTestMixin):

    view_urlname = 'odata_service'

    @classmethod
    def setUpClass(cls):
        super(TestServiceDocument, cls).setUpClass()
        cls.client = Client()
        cls.domain = Domain(name='test_domain')
        cls.domain.save()
        cls.web_user = WebUser.create(cls.domain.name, 'test_user', 'my_password')

    @classmethod
    def tearDownClass(cls):
        cls.domain.delete()
        cls.web_user.delete()
        super(TestServiceDocument, cls).tearDownClass()

    def test_no_credentials(self):
        response = self.client.get(self.view_url)
        self.assertEqual(response.status_code, 401)

    def test_wrong_password(self):
        wrong_credentials = self._get_basic_credentials(self.web_user.username, 'wrong_password')
        response = self._execute_query(wrong_credentials)
        self.assertEqual(response.status_code, 401)

    def test_wrong_domain(self):
        other_domain = Domain(name='other_domain')
        other_domain.save()
        self.addCleanup(other_domain.delete)
        correct_credentials = self._get_correct_credentials()
        response = self.client.get(
            reverse(self.view_urlname, kwargs={'domain': other_domain.name}),
            HTTP_AUTHORIZATION='Basic ' + correct_credentials,
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_feature_flag(self):
        correct_credentials = self._get_correct_credentials()
        response = self._execute_query(correct_credentials)
        self.assertEqual(response.status_code, 404)

    @flag_enabled('ODATA')
    def test_no_case_types(self):
        correct_credentials = self._get_correct_credentials()
        with patch('corehq.apps.api.odata.views.get_case_types_for_domain_es', return_value=set()):
            response = self._execute_query(correct_credentials)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode('utf-8')),
            {"@odata.context": "http://localhost:8000/a/test_domain/api/v0.5/odata/Cases/$metadata", "value": []}
        )

    @flag_enabled('ODATA')
    def test_with_case_types(self):
        correct_credentials = self._get_correct_credentials()
        with patch(
            'corehq.apps.api.odata.views.get_case_types_for_domain_es',
            return_value=['case_type_1', 'case_type_2'],  # return ordered iterable for deterministic test
        ):
            response = self._execute_query(correct_credentials)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content.decode('utf-8')),
            {
                "@odata.context": "http://localhost:8000/a/test_domain/api/v0.5/odata/Cases/$metadata",
                "value": [
                    {'kind': 'EntitySet', 'name': 'case_type_1', 'url': 'case_type_1'},
                    {'kind': 'EntitySet', 'name': 'case_type_2', 'url': 'case_type_2'},
                ],
            }
        )
