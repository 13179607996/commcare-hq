from __future__ import absolute_import

import uuid
from xml.etree import ElementTree
from couchdbkit.schema.properties import LazyDict
#
#with open(os.path.join(os.path.dirname(__file__), "data", "close.xml")) as f:
#    _close_case_template = f.read()

#
#with open(os.path.join(os.path.dirname(__file__), "data", "close_referral.xml")) as f:
#    _close_referral_template = f.read()
from django.template.loader import render_to_string
from casexml.apps.case.signals import process_cases
from couchforms.models import XFormInstance
from couchforms.util import post_xform_to_couch
from dimagi.utils.parsing import json_format_datetime

def get_close_case_xml(time, case_id, uid=None):
    if not uid:
        uid = uuid.uuid4().hex
    time = json_format_datetime(time)
    return render_to_string("case/data/close.xml", locals())

def get_close_referral_xml(time, case_id, referral_id, referral_type, uid=None):
    if not uid:
        uid = uuid.uuid4().hex
    time = json_format_datetime(time)
    return render_to_string("case/data/close_referral.xml", locals())

def couchable_property(prop):
    """
    Sometimes properties that come from couch can't be put back in
    without some modification.
    """
    if isinstance(prop, LazyDict):
        return dict(prop)
    return prop

def post_case_blocks(case_blocks, form_extras={}):
    """
    Post case blocks.
    
    Extras is used to add runtime attributes to the form before
    sending it off to the case (current use case is sync-token pairing)
    """
    form = ElementTree.Element("data")
    form.attrib['xmlns'] = "https://www.commcarehq.org/test/casexml-wrapper"
    form.attrib['xmlns:jrm'] ="http://openrosa.org/jr/xforms"
    for block in case_blocks:
        form.append(block)

    xform = post_xform_to_couch(ElementTree.tostring(form))
    for k, v in form_extras.items():
        setattr(xform, k, v)
    process_cases(sender="testharness", xform=xform)
    return xform

def get_case_xform_ids(case_id):
    results = XFormInstance.get_db().view('case/form_case_index',
                                          reduce=False,
                                          startkey=[case_id],
                                          endkey=[case_id, {}])
    return list(set([row['key'][1] for row in results]))