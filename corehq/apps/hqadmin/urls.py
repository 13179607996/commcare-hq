from django.conf.urls.defaults import *

urlpatterns = patterns('corehq.apps.hqadmin.views',
    (r'^$', 'default'),
    url(r'^domains/$', 'domain_list', name="domain_list"),
)