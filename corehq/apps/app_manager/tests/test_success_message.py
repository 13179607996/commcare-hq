#from StringIO import StringIO
#import re
#from django.test.client import Client
#from corehq.apps.app_manager.models import Application
#from corehq.apps.app_manager.util import SuccessMessage, format_time
#from corehq.apps.phone.xml import get_response
#from corehq.apps.users.models import create_hq_user_from_commcare_registration_info
#from lib.django_digest.tests import TestCase
#from datetime import datetime, timedelta
#
#submission_template = """<?xml version='1.0' ?>
#<data xmlns="%(xmlns)s">
#	<meta>
#		<timeStart></timeStart>
#		<timeEnd></timeEnd>
#		<username>%(username)s</username>
#		<userID>%(userID)s</userID>
#	</meta>
#</data>
#"""
#
#class SuccessMessageTest(TestCase):
#    message = "Thanks {first_name} ({name})! You have submitted {num_forms_today} forms today and {num_forms_this_week} forms since Monday."
#    domain = "test"
#    username = "danny"
#    first_name = "Danny"
#    last_name = "Roberts"
#    password = "123"
#    xmlns = "http://dimagi.com/does_not_matter"
#    tz = timedelta(hours=0)
#    def setUp(self):
#        couch_user = create_hq_user_from_commcare_registration_info(self.domain, self.username, self.password)
#        userID = couch_user.default_commcare_account.login_id
#        couch_user.first_name = self.first_name
#        couch_user.last_name = self.last_name
#        couch_user.save()
#        self.sm = SuccessMessage(self.message, userID, tz=self.tz)
#
#        c = Client()
#
#        app = Application.new_app(self.domain, "Test App", "en")
#        app.new_module("Test Module", "en")
#        form = app.new_form(0, "Test Form", "en")
#        form.xmlns = self.xmlns
#        app.success_message = {"en": self.message}
#        app.save()
#
#        def fake_form_submission(userID=userID, username=self.username, xmlns=self.xmlns, time=None):
#            submission = submission_template % {
#                "userID": userID,
#                "username": username,
#                "xmlns": xmlns
#            }
#            f = StringIO(submission.encode('utf-8'))
#            f.name = "tempfile.xml"
#            kwargs = dict(HTTP_X_SUBMIT_TIME=format_time(time)) if time else {}
#            response = c.post("/a/{self.domain}/receiver/".format(self=self), {
#                'xml_submission_file': f,
#            }, **kwargs)
#            return response
#
#
#        self.num_forms_today = 0
#        self.num_forms_this_week = 0
#        now = datetime.utcnow()
#        tznow = now + self.tz
#        week_start = tznow - timedelta(days=tznow.weekday())
#        week_start = datetime(week_start.year, week_start.month, week_start.day) - self.tz
#        day_start = datetime(tznow.year, tznow.month, tznow.day) - self.tz
#        spacing = 6
#        for h in xrange((24/spacing)*8):
#            time = now-timedelta(hours=spacing*h)
#            response = fake_form_submission(time=time)
#            if time > week_start:
#                self.num_forms_this_week += 1
#            if time > day_start:
#                self.num_forms_today += 1
#            self.failUnlessEqual(
#                response.content,
#                get_response(("Thanks {self.first_name} ({self.first_name} {self.last_name})! "
#                "You have submitted {self.num_forms_today} forms today "
#                "and {self.num_forms_this_week} forms since Monday.").format(self=self))
#            )
#
#    def testRender(self):
#        self.failUnlessEqual(
#            self.sm.render(),
#            ("Thanks {self.first_name} ({self.first_name} {self.last_name})! "
#            "You have submitted {self.num_forms_today} forms today "
#            "and {self.num_forms_this_week} forms since Monday.").format(self=self)
#        )