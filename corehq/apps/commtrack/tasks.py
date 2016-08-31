from celery.task import task
from corehq.apps.commtrack.consumption import recalculate_domain_consumption
from corehq.apps.locations.bulk import import_locations
from corehq.apps.locations.bulk_management import new_locations_import
from corehq.toggles import NEW_BULK_LOCATION_MANAGEMENT
from corehq.util.decorators import serial_task
from corehq.util.spreadsheets.excel_importer import MultiExcelImporter
from django.conf import settings
from soil import DownloadBase


@serial_task('{domain}', default_retry_delay=5 * 60, timeout=30 * 60,
    max_retries=12, queue=settings.CELERY_MAIN_QUEUE, ignore_result=False)
def import_locations_async(domain, file_ref_id):
    importer = MultiExcelImporter(import_locations_async, file_ref_id)
    task = import_locations_async
    DownloadBase.set_progress(task, 0, 100)
    if NEW_BULK_LOCATION_MANAGEMENT.enabled(domain):
        results = new_locations_import(domain, importer)
    else:
        results = list(import_locations(domain, importer))
    DownloadBase.set_progress(task, 100, 100)
    importer.mark_complete()

    return {
        'messages': results
    }


@task(ignore_result=True)
def recalculate_domain_consumption_task(domain):
    recalculate_domain_consumption(domain)
