from celery.task import periodic_task
from celery.schedules import crontab

from custom.rch.models import RCHRecord, MOTHER_DATA_TYPE, CHILD_DATA_TYPE


@periodic_task(run_every=crontab(minute="0", hour="18"), queue='background_queue')
def fetch_rch_mother_beneficiaries():
    RCHRecord.update_beneficiaries(MOTHER_DATA_TYPE)


@periodic_task(run_every=crontab(minute="15", hour="18"), queue='background_queue')
def fetch_rch_child_beneficiaries():
    RCHRecord.update_beneficiaries(CHILD_DATA_TYPE)
