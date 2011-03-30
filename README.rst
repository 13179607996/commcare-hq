==========
Dimagi Auditcare
==========

A set of simple auditing tools for Dimagi's CommCareHQ and its related technologies.

All audits events inherit from the AuditEvent model which contains some basic audit information.

What It does
============
- Log Views (NavigationEventAudit)
   - Directly with a view decorator
   - Centrally with a middelware and a settings parameter listing the fully qualified view names
- Centrally log model saves (ModelActionAudit) via attaching signals from a settings parameter
- Uses threadlocals for accessing the user in said signals
- Login/Logout and failed login attempts (AccessAudit)

Requirements
===========
Auditcare relies on dimagi-utils

Usage
=====
To turn on auditing, you'll need to add a few settings to your settings.py file.

To your INSTALLED_APPS, add the 'auditcare' app.
To setup couchdb, you need to use dimagi's convention for connecting to CouchDB.  Specifically:
settings.COUCH_SERVER_ROOT='127.0.0.1:5984'
COUCH_USERNAME = 'foo'
COUCH_PASSWORD = 'bar'
COUCH_DATABASE_NAME = 'foobardb'
COUCHDB_APPS = ['auditcare', ...]

View Audits
===========
To your MIDDLEWARE_CLASSES, add 'auditcare.middleware.AuditMiddleware', to the END of the list.

Add an array, AUDIT_VIEWS = [].  The elements of this list should be the fully qualified viewnames of the views you want to log and audit.

Login/Logout Events
===================

By default the django standard login/logout views will be audited.  Custom login/logout views are a work in progress
####### Couch Forms & Couch DB Kit Settings #######
def get_server_url(server_root, username, password):
    if username and password:
        return "http://%(user)s:%(pass)s@%(server)s" % \
            {"user": username,
             "pass": password,
             "server": server_root }
    else:
        return "http://%(server)s" % {"server": server_root }
COUCH_SERVER = get_server_url(COUCH_SERVER_ROOT, COUCH_USERNAME, COUCH_PASSWORD)
COUCH_DATABASE = "%(server)s/%(database)s" % {"server": COUCH_SERVER, "database": COUCH_DATABASE_NAME }

Model Saves
===========

By default, the setting AUDIT_DJANGO_USER is set to True, you will need to explicitly set it to false.

For django models you want to audit the save event of, add the fully qualified model name to the AUDIT_MODEL_SAVE array.

You can also audit the admin views by specifying specific AUDIT_ADMIN_VIEWS = [].  If this setting is not in the settings variable, it'll default to auditing ALL admin views.

Finally, to get it all working, be sure to add the auditcare app to your couchdbkit setup for django.



Adding your own AuditEvent
==========================
#. Make a new model that inherits from AuditEvent
#. Make a classmethod for generating the audit event
#. Attach the auditevent to the AuditEvent manager (this will allow simple access to the audit methods without needing to import your namespaces)


