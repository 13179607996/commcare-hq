from celery.task import task
from celery.utils.log import get_task_logger
from django.core.cache import cache
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _

from corehq.apps.data_interfaces.utils import add_cases_to_case_group, archive_forms_old, archive_or_restore_forms
from .interfaces import FormManagementMode, BulkArchiveFormInterface
from .dispatcher import EditDataInterfaceDispatcher
from dimagi.utils.django.email import send_HTML_email

logger = get_task_logger('data_interfaces')
ONE_HOUR = 60 * 60


@task(ignore_result=True)
def bulk_upload_cases_to_group(download_id, domain, case_group_id, cases):
    results = add_cases_to_case_group(domain, case_group_id, cases)
    cache.set(download_id, results, ONE_HOUR)


@task(ignore_result=True)
def bulk_archive_forms(domain, user, uploaded_data):
    # archive using Excel-data
    response = archive_forms_old(domain, user, uploaded_data)

    for msg in response['success']:
        logger.info("[Data interfaces] %s", msg)
    for msg in response['errors']:
        logger.info("[Data interfaces] %s", msg)

    html_content = render_to_string('data_interfaces/archive_email.html', response)
    send_HTML_email(_('Your archived forms'), user.email, html_content)


@task
def bulk_form_management_async(archive_or_restore, domain, couch_user, form_ids_or_filter_url):
    # bulk archive/restore
    # form_ids_or_filter_url - can either be list of formids or a BulkFormManagement query url
    def get_ids_from_url(url, domain, couch_user):
        from django.http import HttpRequest, QueryDict

        _request = HttpRequest()
        _request.couch_user = couch_user
        _request.user = couch_user.get_django_user()
        _request.domain = domain
        _request.couch_user.current_domain = domain

        _request.GET = QueryDict(url)
        dispatcher = EditDataInterfaceDispatcher()
        return dispatcher.dispatch(
            _request,
            render_as='form_ids',
            domain=domain,
            report_slug=BulkArchiveFormInterface.slug,
            skip_permissions_check=True,
        )

    task = bulk_form_management_async
    mode = FormManagementMode(archive_or_restore, validate=True)

    if type(form_ids_or_filter_url) == list:
        xform_ids = form_ids_or_filter_url
    elif isinstance(form_ids_or_filter_url, basestring):
        xform_ids = get_ids_from_url(form_ids_or_filter_url, domain, couch_user)

    if not xform_ids:
        # should never be the case
        raise Exception("No formids supplied")
    response = archive_or_restore_forms(domain, couch_user, xform_ids, mode, task)
    return response
