import StringIO
from datetime import datetime, timedelta
import time
import uuid
import os
import hashlib

from django.test import TestCase, RequestFactory
import lxml
from django.core.files.uploadedfile import UploadedFile
import simplejson

from casexml.apps.case.models import CommCareCase
from casexml.apps.case.xml import V2
from couchforms.models import XFormInstance
from corehq.apps.receiverwrapper import views as rcv_views

TEST_CASE_ID = "EOL9FIAKIQWOFXFOH0QAMWU64"
CREATE_XFORM_ID = "6RGAZTETE3Z2QC0PE2DKM88MO"
media_path = os.path.join(os.path.dirname(__file__), "data", "attachments")

MEDIA_FILES = {
    "fruity": os.path.join(media_path, "fruity.jpg"), #first

    "dimagi_logo": os.path.join(media_path, "dimagi_logo.jpg"),
    "commcare_logo": os.path.join(media_path, "commcare-logo.png"),
    "globe": os.path.join(media_path, "globe.pdf"),
    "house": os.path.join(media_path, "house.jpg"),

}

TEST_DOMAIN = "test-domain"

class BaseCaseMultimediaTest(TestCase):
    def setUp(self):

        for item in CommCareCase.view("case/by_user", include_docs=True, reduce=False).all():
            item.delete()
        for item in XFormInstance.view("couchforms/by_xmlns", include_docs=True, reduce=False).all():
            item.delete()

    def _getXFormString(self, filename):
        file_path = os.path.join(os.path.dirname(__file__), "data", "multimedia", filename)
        with open(file_path, "rb") as f:
            xml_data = f.read()
        return xml_data

    def _formatXForm(self, doc_id, raw_xml, attachment_block):
        final_xml = raw_xml % ({
                                   "attachments": attachment_block,
                                   "time_start": (
                                       datetime.utcnow() - timedelta(minutes=4)).strftime(
                                       '%Y-%m-%dT%H:%M:%SZ'),
                                   "time_end": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                                   "date_modified": datetime.utcnow().strftime(
                                       '%Y-%m-%dT%H:%M:%SZ'),
                                   "doc_id": doc_id
                               })
        return final_xml

    def _prepAttachments(self, new_attachments, removes=[]):
        attachment_block = ''.join([self._singleAttachBlock(x) for x in new_attachments] + [self._singleAttachRemoveBlock(x) for x in removes])
        dict_attachments = dict((attach_name, self._attachmentFileStream(attach_name)) for attach_name in new_attachments)
        return attachment_block, dict_attachments

    def _singleAttachBlock(self, key):
        return '<n0:%s src="%s" from="local"/>' % (key, MEDIA_FILES[key])

    def _singleAttachRemoveBlock(self, key):
        return '<n0:%s />' % key

    def _attachmentFileStream(self, key):
        attachment_path = MEDIA_FILES[key]
        attachment = open(attachment_path, 'rb')
        uf = UploadedFile(attachment, key)
        return uf

    def _calc_file_hash(self, key):
        with open(MEDIA_FILES[key], 'rb') as attach:
            return hashlib.md5(attach.read()).hexdigest()


    def _submit_rf(self, xml_data, dict_attachments):
        """
        RequestFactory submitter
        """
        rf = RequestFactory()
        f = StringIO.StringIO(xml_data.encode('utf-8'))
        f.name = 'form.xml'
        data_dict = {'xml_submission_file': f}
        for k,v in dict_attachments.items():
            data_dict[k] = v

        req = rf.post('/a/%s/receiver' % TEST_DOMAIN,
                      data=data_dict) #, content_type='multipart/form-data')
        return rcv_views.post(req, 'tester')

    def _submit_and_verify(self, doc_id, xml_data, dict_attachments):
    # form = post_xform_to_couch(xml_data, attachments=dict_attachments)
        self._submit_rf(xml_data, dict_attachments)

        time.sleep(2)
        form = XFormInstance.get(doc_id)

        self.assertEqual(len(dict_attachments), len(form.attachments))
        for k, vstream in dict_attachments.items():
            fileback = form.fetch_attachment(k)
            # rewind the pointer before comparing
            orig_attachment = vstream
            orig_attachment.seek(0)
            self.assertEqual(hashlib.md5(fileback).hexdigest(), hashlib.md5(orig_attachment.read()).hexdigest())
        #process_cases(sender="testharness", xform=form) #use with post_xform_to_couch
        return form

    def _doCreateCaseWithMultimedia(self, attachments=['fruity']):
        xml_data = self._getXFormString('multimedia_create.xml')
        attachment_block, dict_attachments = self._prepAttachments(attachments)
        final_xml = self._formatXForm(CREATE_XFORM_ID, xml_data, attachment_block)
        form = self._submit_and_verify(CREATE_XFORM_ID, final_xml, dict_attachments)

    def _doSubmitUpdateWithMultimedia(self, new_attachments=['commcare_logo', 'dimagi_logo'],
                                      removes=['fruity']):
        attachment_block, dict_attachments = self._prepAttachments(new_attachments, removes=removes)

        raw_xform = self._getXFormString('multimedia_update.xml')
        doc_id = uuid.uuid4().hex
        final_xform = self._formatXForm(doc_id, raw_xform, attachment_block)
        form = self._submit_and_verify(doc_id, final_xform, dict_attachments)



class CaseMultimediaTest(BaseCaseMultimediaTest):
    """
    Tests new attachments for cases and case properties
    Spec: https://bitbucket.org/commcare/commcare/wiki/CaseAttachmentAPI
    """
    def testAttachInCreate(self):
        print "testAttachInCreate"
        self.assertEqual(0, len(CommCareCase.view("case/by_user", reduce=False).all()))

        single_attach = 'fruity'
        self._doCreateCaseWithMultimedia(attachments=[single_attach])

        case = CommCareCase.get(TEST_CASE_ID)
        print simplejson.dumps(case.to_json(), indent=4)
        self.assertEqual(1, len(case.case_attachments))
        self.assertTrue(single_attach in case.case_attachments)
        #ipdb.set_trace()
        self.assertEqual(1, len(filter(lambda x: x['action_type'] == 'attachment', case.actions)))
        self.assertEqual(self._calc_file_hash(single_attach), hashlib.md5(case.get_attachment(single_attach)).hexdigest())

    def testAttachRemoveSingle(self):
        self.testAttachInCreate()
        new_attachments = []
        removes = ['fruity']
        self._doSubmitUpdateWithMultimedia(new_attachments=new_attachments, removes=removes)
        case = CommCareCase.get(TEST_CASE_ID)

        #1 plus the 2 we had
        self.assertEqual(0, len(case.case_attachments))
        self.assertIsNone(case._attachments)
        attach_actions = filter(lambda x: x['action_type'] == 'attachment', case.actions)
        self.assertEqual(2, len(attach_actions))
        last_action = attach_actions[-1]
        self.assertEqual(sorted(removes), sorted(last_action['attachments'].keys()))

    def testAttachRemoveMultiple(self):
        self.testAttachInCreate()

        new_attachments = ['commcare_logo', 'dimagi_logo']
        removes = ['fruity']
        self._doSubmitUpdateWithMultimedia(new_attachments=new_attachments, removes=removes)

        case = CommCareCase.get(TEST_CASE_ID)
        #1 plus the 2 we had
        self.assertEqual(2, len(case.case_attachments))
        self.assertEqual(2, len(case._attachments))
        attach_actions = filter(lambda x: x['action_type'] == 'attachment', case.actions)
        self.assertEqual(2, len(attach_actions))
        last_action = attach_actions[-1]
        self.assertEqual(sorted(new_attachments), sorted(case._attachments.keys()))

    def testOTARestoreSingle(self):
        self.testAttachInCreate()
        print "testOTARestoreSingle"
        restore_attachments = ['fruity']
        self._validateOTARestore(TEST_CASE_ID, restore_attachments)

    def testOTARestoreMultiple(self):
        self.testAttachRemoveMultiple()
        print "testOTARestoreMultiple"
        restore_attachments = ['commcare_logo', 'dimagi_logo']
        self._validateOTARestore(TEST_CASE_ID, restore_attachments)

    def _validateOTARestore(self, case_id, restore_attachments):
        case = CommCareCase.get(TEST_CASE_ID)
        case_xml = case.to_xml(V2)
        root_node = lxml.etree.fromstring(case_xml)
        output = lxml.etree.tostring(root_node, pretty_print=True)
        attaches = root_node.find('{http://commcarehq.org/case/transaction/v2}attachment')
        self.assertEqual(len(restore_attachments), len(attaches))
        for attach in attaches:
            url = attach.values()[1]
            case_id = url.split('/')[-2]
            name = url.split('/')[-1]
            tag = attach.tag
            clean_tag = tag.replace('{http://commcarehq.org/case/transaction/v2}', '')
            self.assertEqual(clean_tag, name)
            self.assertEqual(case_id, TEST_CASE_ID)
            self.assertIn(name, restore_attachments)
            restore_attachments.remove(clean_tag)
        self.assertEqual(0, len(restore_attachments))
        print output

    def testAttachInUpdate(self, new_attachments=['commcare_logo', 'dimagi_logo']):
        self.testAttachInCreate()
        removes = []
        self._doSubmitUpdateWithMultimedia(new_attachments=new_attachments, removes=removes)

        case = CommCareCase.get(TEST_CASE_ID)
        #1 plus the 2 we had
        self.assertEqual(len(new_attachments)+1, len(case.case_attachments))
        attach_actions = filter(lambda x: x['action_type'] == 'attachment', case.actions)
        self.assertEqual(2, len(attach_actions))
        last_action = attach_actions[-1]
        self.assertEqual(sorted(new_attachments), sorted(last_action['attachments'].keys()))

        for attach_name in new_attachments:
            self.assertTrue(attach_name in case.case_attachments)
            self.assertEqual(self._calc_file_hash(attach_name), hashlib.md5(case.get_attachment(attach_name)).hexdigest())


    def testMultiSizeImages(self):
        self.testAttachInUpdate(new_attachments=['dimagi_logo'])
        #dimagi_logo = 2550x1200
        #filesize: 484.9 kB (484,915 bytes)

        case = CommCareCase.get(TEST_CASE_ID)





