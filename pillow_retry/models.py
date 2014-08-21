import json
import traceback
from datetime import datetime, timedelta
from django.conf import settings
import math
from django.db import models
from django.db.models.aggregates import Count

ERROR_MESSAGE_LENGTH = 512

def _get_extra_args(limit, reduce, skip):
    extra_args = dict()
    if not reduce and limit is not None:
            extra_args.update(
                limit=limit,
                skip=skip
            )
    return extra_args

def path_from_object(obj):
    path = "{0}.{1}".format(obj.__class__.__module__, obj.__class__.__name__)
    return path


class PillowError(models.Model):
    doc_id = models.CharField(max_length=255, null=False, db_index=True)
    pillow = models.CharField(max_length=255, null=False)
    date_created = models.DateTimeField()
    date_last_attempt = models.DateTimeField()
    date_next_attempt = models.DateTimeField(db_index=True, null=True)
    total_attempts = models.IntegerField(default=0)
    current_attempt = models.IntegerField(default=0, db_index=True)
    error_type = models.CharField(max_length=255, null=True)
    error_traceback = models.TextField(null=True)
    change = models.TextField(null=True)

    @property
    def change_dict(self):
        return json.loads(self.change) if self.change else {'id': self.doc_id}

    class Meta:
        unique_together = ('doc_id', 'pillow',)

    def add_attempt(self, exception, traceb, date=None):
        self.current_attempt += 1
        self.total_attempts += 1
        self.date_last_attempt = date or datetime.utcnow()
        self.error_type = path_from_object(exception)

        self.error_traceback = "{}\n\n{}".format(exception.message, "".join(traceback.format_tb(traceb)))

        if self.current_attempt <= settings.PILLOW_RETRY_QUEUE_MAX_PROCESSING_ATTEMPTS:
            time_till_next = settings.PILLOW_RETRY_REPROCESS_INTERVAL * math.pow(self.current_attempt, settings.PILLOW_RETRY_BACKOFF_FACTOR)
            self.date_next_attempt = self.date_last_attempt + timedelta(minutes=time_till_next)
        else:
            self.date_next_attempt = None

    def reset_attempts(self):
        self.current_attempt = 0
        self.date_next_attempt = datetime.utcnow()

    @classmethod
    def get_or_create(cls, change, pillow):
        pillow_path = path_from_object(pillow)

        change.pop('doc', None)
        doc_id = change['id']
        try:
            error = cls.objects.get(doc_id=doc_id, pillow=pillow_path)
        except cls.DoesNotExist:
            now = datetime.utcnow()
            error = PillowError(
                doc_id=doc_id,
                pillow=pillow_path,
                date_created=now,
                date_last_attempt=now,
                date_next_attempt=now,
                change=json.dumps(change)
            )

        return error

    @classmethod
    def get_errors_to_process(cls, utcnow, limit=None, skip=0, fetch_full=False):
        query = PillowError.objects \
            .filter(date_next_attempt__lte=utcnow) \
            .filter(current_attempt__lte=settings.PILLOW_RETRY_QUEUE_MAX_PROCESSING_ATTEMPTS)

        if not fetch_full:
            query = query.values('id', 'date_next_attempt')
        if limit is not None:
            return query[skip:skip+limit]
        else:
            return query

    @classmethod
    def get_pillows(cls):
        results = PillowError.objects.values('pillow').annotate(count=Count('pillow'))
        return (p['pillow'] for p in results)

    @classmethod
    def get_error_types(cls):
        results = PillowError.objects.values('error_type').annotate(count=Count('error_type'))
        return (e['error_type'] for e in results)


# Stub models file, also used in tests
from couchdbkit.ext.django.schema import Document


class Stub(Document):
    pass
