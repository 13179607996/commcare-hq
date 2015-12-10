from casexml.apps.stock.const import COMMTRACK_REPORT_XMLNS
from corehq.util.couch import stale_ok
from corehq.util.test_utils import unit_testing_only
from couchforms.const import DEVICE_LOG_XMLNS
from couchforms.models import XFormInstance, doc_types


def get_form_ids_by_type(domain, type_, start=None, end=None):
    assert type_ in doc_types()
    startkey = [domain, type_]
    if end:
        endkey = startkey + end.isoformat()
    else:
        endkey = startkey + [{}]

    if start:
        startkey.append(start.isoformat())

    return [row['id'] for row in XFormInstance.get_db().view(
        "couchforms/all_submissions_by_domain",
        startkey=startkey,
        endkey=endkey,
        reduce=False,
    )]


def get_forms_by_type(domain, type_, recent_first=False,
                      limit=None):
    assert type_ in doc_types()
    # no production code should be pulling all forms in one go!
    assert limit is not None
    startkey = [domain, type_]
    endkey = startkey + [{}]
    if recent_first:
        startkey, endkey = endkey, startkey
    return XFormInstance.view(
        "couchforms/all_submissions_by_domain",
        startkey=startkey,
        endkey=endkey,
        reduce=False,
        descending=recent_first,
        include_docs=True,
        limit=limit,
        classes=doc_types(),
    ).all()


@unit_testing_only
def get_forms_of_all_types(domain):
    startkey = [domain]
    endkey = startkey + [{}]
    return XFormInstance.view(
        "couchforms/all_submissions_by_domain",
        startkey=startkey,
        endkey=endkey,
        reduce=False,
        include_docs=True,
        classes=doc_types(),
    ).all()


def get_number_of_forms_all_domains_in_couch():
    """
    Return number of non-error, non-log forms total across all domains
    specifically as stored in couch.

    (Can't rewrite to pull from ES or SQL; this function is used as a point
    of comparison between row counts in other stores.)

    """
    all_forms = (
        XFormInstance.get_db().view('couchforms/by_xmlns').one()
        or {'value': 0}
    )['value']
    device_logs = (
        XFormInstance.get_db().view('couchforms/by_xmlns',
                                    key=DEVICE_LOG_XMLNS).one()
        or {'value': 0}
    )['value']
    return all_forms - device_logs


@unit_testing_only
def get_commtrack_forms(domain):
    key = ['submission xmlns', domain, COMMTRACK_REPORT_XMLNS]
    return XFormInstance.view(
        'reports_forms/all_forms',
        startkey=key,
        endkey=key + [{}],
        reduce=False,
        include_docs=True
    )


def get_exports_by_form(domain):
    return XFormInstance.get_db().view(
        'exports_forms/by_xmlns',
        startkey=[domain],
        endkey=[domain, {}],
        group=True,
        stale=stale_ok()
    )
