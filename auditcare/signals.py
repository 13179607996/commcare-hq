from django.db.models.signals import post_init, post_save, pre_save, pre_delete
from couchdbkit.ext.django.schema import Document
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
import logging
from datetime import datetime
from django.core import serializers
import json

import settings
try:
    from dimagi.utils.threadlocals import get_current_user
except:
    from auditcare.utils import get_current_user

from django.db import transaction
from models import *
from django.dispatch import Signal

user_login_failed = Signal(providing_args=['request', 'username'])


json_serializer = serializers.get_serializer("json")()

def django_audit_save(sender, instance, created, **kwargs):
    """
    Audit Save is a signal to attach post_save to any arbitrary django model
    """
    usr = get_current_user()

    # a silly wrap the instance in an array to serialize it, then pull it out of the array to get the json data standalone
    instance_json = json.loads(json_serializer.serialize([instance], ensure_ascii=False))[0]

    #really stupid sanity check for unit tests when threadlocals doesn't update and user model data is updated.
    if usr != None:
        try:
            User.objects.get(id=usr.id)
        except:
            usr = None
    from models.couchmodels import AuditEvent
    AuditEvent.audit_django_save(sender, instance, instance_json, usr)

def couch_audit_save(self, *args, **kwargs):
    from models.couchmodels import AuditEvent
    self.__orig_save(*args, **kwargs)
    instance_json = self.to_json()
    usr = get_current_user()
    if usr != None:
        try:
            User.objects.get(id=usr.id)
        except:
            usr = None
    AuditEvent.audit_couch_save(self.__class__, self, instance_json, usr)


if hasattr(settings, 'AUDIT_MODEL_SAVE'):
    for full_str in settings.AUDIT_MODEL_SAVE:
        comps = full_str.split('.')
        model_class = comps[-1]
        mod_str = '.'.join(comps[0:-1])
        mod = __import__(mod_str, {},{},[model_class])        
        if hasattr(mod, model_class):
            #ok so we have the model class itself.
            audit_model = getattr(mod, model_class)

            if issubclass(audit_model, models.Model):
                #it's a django model subclass.
                post_save.connect(django_audit_save, sender=audit_model, dispatch_uid="audit_save_" + str(model_class)) #note, you should add a unique dispatch_uid to this else you might get dupes
                #source; http://groups.google.com/group/django-users/browse_thread/thread/0f8db267a1fb036f
            elif issubclass(audit_model, Document):
                #it's a couchdbkit Document subclass
                audit_model.__orig_save = audit_model.save
                audit_model.save = couch_audit_save
                #audit_model.save = CouchSavePatch(orig_save, audit_model)
                pass
else:
    logging.warning("You do not have the AUDIT_MODEL_SAVE settings variable setup.  If you want to setup model save audit events, please add the property and populate it with fully qualified model names.")
