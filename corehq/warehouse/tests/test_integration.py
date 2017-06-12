from datetime import datetime, timedelta

from django.test import TestCase

from corehq.apps.users.models import CommCareUser
from corehq.apps.domain.models import Domain
from corehq.form_processor.tests.utils import create_form_for_test, FormProcessorTestUtils

from corehq.warehouse.models import (
    UserStagingTable,
    DomainStagingTable,
    UserDim,
    DomainDim,
    FormStagingTable,
    FormFact,
)


class FormFactIntegrationTest(TestCase):
    '''
    Tests a full integration of loading the FormFact table from
    staging and dimension tables.
    '''
    domain = 'form-fact-integration-test'

    @classmethod
    def setUpClass(cls):
        cls.domain_records = [
            Domain(name=cls.domain, hr_name='One', creating_user_id='abc', is_active=True),
        ]

        for domain in cls.domain_records:
            domain.save()

        cls.user_records = [
            # TODO: Handle WebUsers who have multiple domains
            # WebUser.create(
            #     cls.domain,
            #     'web-user',
            #     '***',
            #     date_joined=datetime.utcnow(),
            #     first_name='A',
            #     last_name='B',
            #     email='b@a.com',
            #     is_active=True,
            #     is_staff=False,
            #     is_superuser=True,
            # ),
            CommCareUser.create(
                cls.domain,
                'commcare-user',
                '***',
                date_joined=datetime.utcnow(),
                email='a@a.com',
                is_active=True,
                is_staff=True,
                is_superuser=False,
            ),
        ]

        cls.form_records = [
            create_form_for_test(cls.domain, user_id=cls.user_records[0]._id),
            create_form_for_test(cls.domain, user_id=cls.user_records[0]._id),
            create_form_for_test(cls.domain, user_id=cls.user_records[0]._id),
        ]

    @classmethod
    def tearDownClass(cls):
        for user in cls.user_records:
            user.delete()

        for domain in cls.domain_records:
            domain.delete()

        FormProcessorTestUtils.delete_all_sql_forms(cls.domain)

        DomainStagingTable.clear_records()
        DomainDim.clear_records()
        UserStagingTable.clear_records()
        UserDim.clear_records()
        FormStagingTable.clear_records()
        FormFact.clear_records()

    def test_loading_form_fact(self):
        start = datetime.utcnow() - timedelta(days=3)
        end = datetime.utcnow() + timedelta(days=3)

        DomainStagingTable.commit(start, end)
        self.assertEqual(DomainStagingTable.objects.count(), len(self.domain_records))

        DomainDim.commit(start, end)
        self.assertEqual(DomainDim.objects.count(), len(self.domain_records))

        UserStagingTable.commit(start, end)
        self.assertEqual(UserStagingTable.objects.count(), len(self.user_records))

        UserDim.commit(start, end)
        self.assertEqual(UserDim.objects.count(), len(self.user_records))

        FormStagingTable.commit(start, end)
        self.assertEqual(FormStagingTable.objects.count(), len(self.form_records))

        FormFact.commit(start, end)
        self.assertEqual(FormFact.objects.count(), len(self.form_records))
