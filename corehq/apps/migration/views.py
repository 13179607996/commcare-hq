import re
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from corehq.apps.migration.add_user_id import add_user_id
from corehq.apps.migration.models import MigrationUser
from corehq.apps.migration.post import post_data
from corehq.apps.receiverwrapper.views import post as receiver_post
from dimagi.utils.couch.database import get_db
from django.conf import settings


class UserMap(object):
    def __init__(self, domain, *args, **kwargs):
        #dict.__init__(self, *args, **kwargs)
        self.domain = domain
        self._cache = {}

    def __contains__(self, username):
        if username in self._cache:
            return True
        r = get_db().view('migration/user_id_by_username', key=[self.domain, username]).one()
        if r:
            user_id = r['value']
            self._cache[username] = user_id
            return True
        else:
            return False

    def __getitem__(self, username):
        if username in self._cache:
            return self._cache[username]
        r = get_db().view('migration/user_id_by_username', key=[self.domain, username]).one()
        if r:
            user_id = r['value']
            self._cache[username] = user_id
            return user_id
        else:
            raise KeyError()

    def __setitem__(self, username, user_id):
        u = MigrationUser()
        u.username = username
        u.domain = self.domain
        u.user_id = user_id
        u.save()
        self._cache[username] = user_id

    def get(self, k, d=None):
        return self[k] if k in self else d

def is_user_registration(xml):
    return re.search(r'openrosa.org/user-registration', xml)


def update_migration_users(xml, user_map):
    """Updates the database of users and returns whether it made an addition or not
    (It doesn't make an addition if the username/domain was already taken)"""
    def get_username(reg):
        return re.search(r'<username>(.*)</username>', reg).group(1).replace(' ', '_').lower()

    def get_user_id(reg):
        return re.search(r'<uuid>(.*)</uuid>', reg).group(1)

    username = get_username(xml)
    submit = username not in user_map
    if submit:
        user_id = get_user_id(xml)
        user_map[username] = user_id
    print "Username: %s" % username
    return submit

def post(request, domain):
    """expects same posts as receiver but munges the forms before passing them on"""

    xml = request.raw_post_data
    user_map = UserMap(domain)
    submit = True
    if is_user_registration(xml):
        submit = update_migration_users(xml, user_map)
    else:
        xml = add_user_id(xml, user_map)
    if submit:
        url = "http://%s%s" % (settings.REFLEXIVE_URL_BASE, reverse(receiver_post, args=[domain]))
        results, errors = post_data(xml, url, submit_time=request.META.get('HTTP_X_SUBMIT_TIME', None))
        if errors:
            raise Exception(errors)
        return HttpResponse(results)
    else:
        return HttpResponse("user already exists")