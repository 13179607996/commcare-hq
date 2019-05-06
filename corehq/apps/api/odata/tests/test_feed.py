from __future__ import absolute_import
from __future__ import unicode_literals

from django.test import Client, TestCase
from django.urls import reverse

from elasticsearch.exceptions import ConnectionError
from tastypie.models import ApiKey

from corehq.apps.accounting.models import (
    BillingAccount,
    DefaultProductPlan,
    SoftwarePlanEdition,
    Subscription,
    SubscriptionAdjustment,
)
from corehq.apps.api.odata.tests.utils import OdataTestMixin
from corehq.apps.api.resources.v0_5 import ODataCommCareCaseResource
from corehq.apps.domain.models import Domain
from corehq.apps.users.models import WebUser
from corehq.elastic import get_es_new
from corehq.pillows.mappings.case_mapping import CASE_INDEX_INFO
from corehq.util.elastic import ensure_index_deleted
from corehq.util.test_utils import flag_enabled, trap_extra_setup
from pillowtop.es_utils import initialize_index_and_mapping


class TestOdataFeed(TestCase, OdataTestMixin):

    @classmethod
    def setUpClass(cls):
        super(TestOdataFeed, cls).setUpClass()

        cls.client = Client()
        cls.domain = Domain(name='test_domain')
        cls.domain.save()
        cls.web_user = WebUser.create(cls.domain.name, 'test_user', 'my_password')

        cls.account, _ = BillingAccount.get_or_create_account_by_domain(cls.domain.name, created_by='')
        plan_version = DefaultProductPlan.get_default_plan_version(SoftwarePlanEdition.STANDARD)
        cls.subscription = Subscription.new_domain_subscription(cls.account, cls.domain.name, plan_version)

    @classmethod
    def tearDownClass(cls):
        cls.domain.delete()
        cls.web_user.delete()

        SubscriptionAdjustment.objects.all().delete()
        cls.subscription.delete()
        cls.account.delete()
        super(TestOdataFeed, cls).tearDownClass()

    def test_no_credentials(self):
        response = self.client.get(self.view_url)
        self.assertEqual(response.status_code, 404)

    def test_wrong_password(self):
        wrong_credentials = self._get_basic_credentials(self.web_user.username, 'wrong_password')
        response = self._execute_query(wrong_credentials)
        self.assertEqual(response.status_code, 404)

    def test_wrong_domain(self):
        other_domain = Domain(name='other_domain')
        other_domain.save()
        self.addCleanup(other_domain.delete)

        correct_credentials = self._get_correct_credentials()
        response = self.client.get(
            self._odata_feed_url_by_domain(other_domain.name),
            HTTP_AUTHORIZATION='Basic ' + correct_credentials,
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_feature_flag(self):
        correct_credentials = self._get_correct_credentials()
        response = self._execute_query(correct_credentials)
        self.assertEqual(response.status_code, 404)

    @flag_enabled('ODATA')
    def test_request_succeeded(self):
        with trap_extra_setup(ConnectionError):
            elasticsearch_instance = get_es_new()
            initialize_index_and_mapping(elasticsearch_instance, CASE_INDEX_INFO)
        self.addCleanup(self._ensure_case_index_deleted)

        self.web_user.set_role(self.domain.name, 'admin')
        self.web_user.save()

        correct_credentials = self._get_correct_credentials()
        response = self._execute_query(correct_credentials)
        self.assertEqual(response.status_code, 200)

    @property
    def view_url(self):
        return self._odata_feed_url_by_domain(self.domain.name)

    @staticmethod
    def _odata_feed_url_by_domain(domain_name):
        return reverse(
            'api_dispatch_detail',
            kwargs={
                'domain': domain_name,
                'api_name': 'v0.5',
                'resource_name': ODataCommCareCaseResource._meta.resource_name,
                'pk': 'my_case_type',
            }
        )

    @staticmethod
    def _ensure_case_index_deleted():
        ensure_index_deleted(CASE_INDEX_INFO.index)


class TestOdataFeedUsingApiKey(TestOdataFeed):

    @classmethod
    def setUpClass(cls):
        super(TestOdataFeedUsingApiKey, cls).setUpClass()
        cls.api_key = ApiKey.objects.get_or_create(user=cls.web_user.get_django_user())[0]
        cls.api_key.key = cls.api_key.generate_key()
        cls.api_key.save()

    @classmethod
    def _get_correct_credentials(cls):
        return TestOdataFeedUsingApiKey._get_basic_credentials('test_user', cls.api_key.key)
