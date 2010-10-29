from django.conf.urls.defaults import *
from django.conf import settings

urlpatterns = patterns('corehq.apps.hqwebapp.views',
    url(r'^homepage$', 'redirect_to_default', name='homepage'),
    (r'^serverup.txt$', 'server_up'),
    (r'^change_password/?$', 'password_change'),
    
    (r'^no_permissions/?$', 'no_permissions'),
    
    url(r'^accounts/login/$', 'login', name="login"),
    url(r'^accounts/logout/$', 'logout', name="logout"),
    (r'^$', 'redirect_to_default'),
)

domain_specific = patterns('corehq.apps.hqwebapp.views',
    (r'messages/$', 'messages'),
 url(r'^$', 'redirect_to_default', name='domain_homepage'),
)