from datetime import datetime
from django.conf import settings
from django.test import TestCase
from django.contrib.auth.models import User
from couchdbkit import Server
from corehq.apps.users.util import format_username
from couchforms.models import XFormInstance
from corehq.apps.users.signals import REGISTRATION_XMLNS, create_user_from_commcare_registration
from corehq.apps.users.models import CouchUser
from corehq.apps.users.signals import create_hq_user_from_commcare_registration_info
from lxml import etree as ET


class CreateTestCase(TestCase):
    
    def setUp(self):
        all_users = CouchUser.view("users/all_users")
        for user in all_users:
            user.delete()
        self.xform = XFormInstance()
        self.xform.form = {}
        self.xform.form['username'] = self.username = 'test_registration'
        self.xform.form['password'] = self.password = '1982'
        self.xform.form['uuid'] = self.uuid = 'BXPKZLP49P3DDTJH3W0BRM2HV'
        self.xform.form['date'] = self.date_string = '2010-03-23'
        self.xform.form['registering_phone_id'] = self.registering_device_id = '67QQ86GVH8CCDNSCL0VQVKF7A'
        self.xform.domain = self.domain = 'mockdomain'
        self.xform.xmlns = REGISTRATION_XMLNS
        
    def testCreateBasicWebUser(self):
        """ 
        test that a basic couch user gets created when calling CouchUser.from_web_user
        """
        username = "joe"
        email = "joe@domain.com"
        password = "password"
        # create django user
        new_user = User.objects.create_user(username, email, password)
        new_user.save()
        # verify that the default couch stuff was created
        couch_user = CouchUser.from_web_user(new_user)
        couch_user.save()
        self.assertEqual(couch_user.web_account.login.username, username)
        self.assertEqual(couch_user.web_account.login.email, email)

    def testCreateCompleteWebUser(self):
        """ 
        testing couch user internal functions
        """
        username = "joe"
        email = "joe@domain.com"
        password = "password"
        # create django user
        new_user = User.objects.create_user(username, email, password)
        new_user.save()
        # verify that the default couch stuff was created
        couch_user = CouchUser.from_web_user(new_user)
        self.assertEqual(couch_user.web_account.login.username, username)
        self.assertEqual(couch_user.web_account.login.email, email)
        couch_user.add_domain_membership('domain1')
        self.assertEqual(couch_user.web_account.domain_memberships[0].domain, 'domain1')
        couch_user.add_domain_membership('domain2')
        self.assertEqual(couch_user.web_account.domain_memberships[1].domain, 'domain2')

        ccu0 = create_hq_user_from_commcare_registration_info(
            'domain3', 'username3', 'password3', uuid="sdf", device_id='ewr')
        ccu0.save()
        couch_user.link_commcare_account("domain3", ccu0._id, ccu0.commcare_accounts[0].login_id)
        self.assertEqual(couch_user.commcare_accounts[0].login.username, 'username3')
        self.assertEqual(couch_user.commcare_accounts[0].domain, 'domain3')        
        self.assertEqual(couch_user.commcare_accounts[0].login_id, 'sdf')
        self.assertEqual(couch_user.commcare_accounts[0].registering_device_id, 'ewr')

        ccu1 = create_hq_user_from_commcare_registration_info(
                'domain4', 'username4', 'password4', uuid="oiu", device_id='wer', user_data={"extra_data": 'extra'})
        ccu1.save()
        couch_user.link_commcare_account('domain4', ccu1._id, ccu1.commcare_accounts[0].login_id)
        self.assertEqual(couch_user.commcare_accounts[1].login.username, 'username4')
        self.assertEqual(couch_user.commcare_accounts[1].domain, 'domain4')
        self.assertEqual(couch_user.commcare_accounts[1].login_id, 'oiu')
        self.assertEqual(couch_user.commcare_accounts[1].registering_device_id, 'wer')
        #TODO: fix
        #self.assertEqual(couch_user.commcare_accounts[1].user_data['extra_data'], 'extra')
        couch_user.add_device_id('IMEI')
        self.assertEqual(couch_user.device_ids[0], 'IMEI')
        couch_user.add_phone_number('1234567890')
        self.assertEqual(couch_user.phone_numbers[0], '1234567890')
        couch_user.save()

    def testCreateUserFromRegistration(self):
        """ 
        test creating of couch user from a registration xmlns
        this is more of an integration test than a unit test,
        since 
        """
        sender = "post"
        xml = create_user_from_commcare_registration(sender, self.xform).response
        uuid = ET.fromstring(xml).findtext(".//{http://openrosa.org/user/registration}uuid")
        couch_user = CouchUser.view('users/commcare_users_by_login_id', include_docs=True).one()
        # django_user = couch_user.get_django_user()
        # self.assertEqual(django_user.username, random_uuid)
        # self.assertEqual(couch_user.web_account.login.username, random_uuid)

        # registered commcare user gets an automatic domain account on server
        # this is no longer true; should it be?
        # self.assertEqual(couch_user.web_account.domain_memberships[0].domain, self.domain)
        # they also get an automatic commcare account
        self.assertEqual(couch_user.commcare_accounts[0].login.username, format_username(self.username, self.domain))
        #unpredictable, given arbitrary salt to hash
        #self.assertEqual(couch_user.commcare_accounts[0].login.password, 'sha1$29004$678636e813e7909f14b184a5063f80c94b991daf')
        self.assertEqual(couch_user.commcare_accounts[0].domain, self.domain)
        self.assertEqual(couch_user.commcare_accounts[0].login_id, self.uuid)
        date = datetime.date(datetime.strptime(self.date_string,'%Y-%m-%d'))
#        self.assertEqual(couch_user.commcare_accounts[0].date_registered, date)
        self.assertEqual(couch_user.device_ids[0], self.registering_device_id)
        
    def testCreateDuplicateUsersFromRegistration(self):
        """ 
        use case: chw on phone registers a username/password/domain triple somewhere 
        another chw somewhere else somehow registers the same username/password/domain triple 
        outcome: 2 distinct users on hq with the same info, with one marked 'is_duplicate'
        (BUT ota restore should return a 'too many duplicate users' error)
        
        ADDENDUM: this use case is deprecated. HQ should disallow creation of duplicate
        users, even if it means throwing an angry error to the mobile side on duplicate
        user registration. This test needs to be updated to demonstrate that error.
        """
#        sender = "post"
#        doc_id = create_user_from_commcare_registration(sender, self.xform)
#        first_user = CouchUser.get(doc_id)
#        # switch uuid so that we don't violate unique key constraints on django use creation
#        xform = self.xform
#        xform.form['uuid'] = 'AVNSDNVLDSFDESFSNSIDNFLDKN'
#        dupe_id = create_user_from_commcare_registration(sender, xform)
#        second_user = CouchUser.get(dupe_id)
#        self.assertFalse(hasattr(first_user, 'is_duplicate'))
#        self.assertTrue(second_user.is_duplicate)
