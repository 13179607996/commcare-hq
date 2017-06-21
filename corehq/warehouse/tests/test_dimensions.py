from datetime import datetime, timedelta
from django.test import TestCase

from corehq.apps.users.util import SYSTEM_USER_ID, DEMO_USER_ID
from corehq.apps.commtrack.const import COMMTRACK_USERNAME
from corehq.pillows.utils import (
    SYSTEM_USER_TYPE,
    DEMO_USER_TYPE,
    COMMCARE_SUPPLY_USER_TYPE,
    WEB_USER_TYPE,
    MOBILE_USER_TYPE,
)
from corehq.warehouse.tests.utils import (
    create_user_staging_record,
    create_location_records_from_tree,
)
from corehq.warehouse.models import (
    UserStagingTable,
    UserDim,
    LocationDim,
    LocationStagingTable,
    LocationTypeStagingTable,
)


class TestUserDim(TestCase):

    domain = 'user-dim-test'

    @classmethod
    def setUpClass(cls):
        super(TestUserDim, cls).setUpClass()
        cls.records = [
            create_user_staging_record(
                cls.domain,
                user_id=SYSTEM_USER_ID,
                username='system_bob',
            ),
            create_user_staging_record(
                cls.domain,
                user_id=DEMO_USER_ID,
                username='demo_sally',
            ),
            create_user_staging_record(
                cls.domain,
                user_id=COMMTRACK_USERNAME,
                username='commtrack_billy',
            ),
            create_user_staging_record(
                cls.domain,
                user_id='beeboobop',
                username='web',
                doc_type='WebUser'
            ),
            create_user_staging_record(
                cls.domain,
                user_id='greengoblin',
                username='mobile',
            ),
        ]

    @classmethod
    def tearDownClass(cls):
        for record in cls.records:
            record.delete()
        UserDim.clear_records()
        UserStagingTable.clear_records()
        super(TestUserDim, cls).tearDownClass()

    def test_user_types(self):
        start = datetime.utcnow() - timedelta(days=3)
        end = datetime.utcnow() + timedelta(days=3)

        UserDim.commit(start, end)

        self.assertEqual(UserDim.objects.count(), 5)
        self.assertEqual(
            UserDim.objects.filter(user_type=SYSTEM_USER_TYPE).first().user_id,
            SYSTEM_USER_ID,
        )
        self.assertEqual(
            UserDim.objects.filter(user_type=DEMO_USER_TYPE).first().user_id,
            DEMO_USER_ID,
        )
        self.assertEqual(
            UserDim.objects.filter(user_type=COMMCARE_SUPPLY_USER_TYPE).first().user_id,
            COMMTRACK_USERNAME,
        )
        self.assertEqual(
            UserDim.objects.filter(user_type=MOBILE_USER_TYPE).first().user_id,
            'greengoblin',
        )
        self.assertEqual(
            UserDim.objects.filter(user_type=WEB_USER_TYPE).first().user_id,
            'beeboobop',
        )


class TestLocationDim(TestCase):

    domain = 'location-dim-test'

    @classmethod
    def teardDownClass(cls):
        LocationStagingTable.clear_records()
        LocationTypeStagingTable.clear_records()
        LocationDim.clear_records()
        super(TestLocationDim, cls).teardDownClass()

    def test_location_dim(self):
        start = datetime.utcnow() - timedelta(days=3)
        end = datetime.utcnow() + timedelta(days=3)
        tree = {
            ('Illinois', 'state'): {
                ('Naperville', 'city'): {
                    ('Home', 'home'): {}
                },
                ('Chicago', 'city'): {},
            }
        }
        create_location_records_from_tree(self.domain, tree)

        self.assertEqual(LocationStagingTable.objects.count(), 4)
        self.assertEqual(LocationTypeStagingTable.objects.count(), 3)

        LocationDim.commit(start, end)
        self.assertEqual(LocationDim.objects.count(), 4)
        home_location = LocationDim.objects.filter(name='Home').first()

        self.assertIsNotNone(home_location.location_level_0)
        self.assertIsNotNone(home_location.location_level_1)
        self.assertEqual(home_location.location_level_2, home_location.sql_location_id)

        self.assertEqual(home_location.level, 2)
        self.assertEqual(home_location.location_type_name, 'home')
        self.assertEqual(home_location.location_type_code, 'home')

        root_location = LocationDim.objects.filter(name='Illinois').first()
        self.assertEqual(root_location.location_level_0, root_location.sql_location_id)
        self.assertEqual(root_location.level, 0)
