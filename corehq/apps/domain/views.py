import sys, datetime, uuid
from django import forms
from django.conf import settings
#from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.core.mail import EmailMultiAlternatives, SMTPConnection
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.db import transaction
from django.http import HttpResponseRedirect

from django_tables import tables

from corehq.apps.domain.decorators import REDIRECT_FIELD_NAME, login_required_late_eval_of_LOGIN_URL, login_and_domain_required, domain_admin_required
from corehq.apps.domain.forms import DomainSelectionForm, RegistrationRequestForm, ResendConfirmEmailForm, clean_password, UpdateSelfForm, UpdateSelfTable
from corehq.apps.domain.models import Domain, RegistrationRequest
from corehq.apps.domain.user_registration_backend.forms import AdminRegistersUserForm
from django_user_registration.models import RegistrationProfile
from corehq.apps.users.models import CouchUser

from dimagi.utils.web import render_to_response
from corehq.apps.users.util import couch_user_from_django_user
from corehq.apps.users.views import require_domain_admin
from dimagi.utils.django.email import send_HTML_email

# Domain not required here - we could be selecting it for the first time. See notes domain.decorators
# about why we need this custom login_required decorator
@login_required_late_eval_of_LOGIN_URL
def select( request, 
            redirect_field_name = REDIRECT_FIELD_NAME,
            domain_select_template = 'domain/select.html' ):
    
    domains_for_user = Domain.active_for_user(request.user)
    if len(domains_for_user) == 0:
        vals = dict( error_msg = "You are not a member of any existing domains - please contact your system administrator",
                     show_homepage_link = False   )
        return render_to_response(request, 'error.html', vals)
    
    redirect_to = request.REQUEST.get(redirect_field_name, '')    
    if request.method == 'POST': # If the form has been submitted...        
        form = DomainSelectionForm(domain_list=domains_for_user,
                                   data=request.POST) # A form bound to the POST data
                     
        if form.is_valid():
            # We've just checked the submitted data against a freshly-retrieved set of domains
            # associated with the user. It's safe to set the domain in the sesssion (and we'll
            # check again on views validated with the domain-checking decorator)
            form.save(request) # Needs request because it saves domain in session
    
            #  Weak attempt to give user a good UX - make sure redirect_to isn't garbage.
            domain = form.cleaned_data['domain_list'].name
            if not redirect_to or '//' in redirect_to or ' ' in redirect_to:
                redirect_to = reverse('domain_homepage', args=[domain])
            return HttpResponseRedirect(redirect_to) # Redirect after POST
    else:
        # An unbound form
        form = DomainSelectionForm( domain_list=domains_for_user ) 

    vals = dict( next = redirect_to,
                 form = form )

    return render_to_response(request, domain_select_template, vals)

########################################################################################################
# 
# Raises exception on error - returns nothing
#

def _send_domain_registration_email(recipient, domain_name, guid, username):
        
    DNS_name = Site.objects.get(id = settings.SITE_ID).domain
    link = 'http://' + DNS_name + reverse('domain_registration_confirm') + guid + '/'    
    
    text_content = """
You requested the new HQ domain "{domain}". To activate this domain, navigate to the following link
{link}
Thereafter, you'll be able to log on to your new domain with username "{user}".
"""

    html_content = """
<p>You requested the new CommCare HQ domain "{domain}".</p>
<p>To activate this domain, click on <a href="{link}">this link</a>.</p>
<p>If your email viewer won't permit you to click on that link, cut and paste the following link into your web browser:</p>
<p>{link}</p>
<p>Thereafter, you'll be able to log on to your new domain with username "{user}".</p>
"""
    params = {"domain": domain_name, "link": link, "user": username}
    text_content = text_content.format(**params)
    html_content = html_content.format(**params)
     
    # http://blog.elsdoerfer.name/2009/11/09/properly-sending-contact-form-emails-and-how-to-do-it-in-django/
    #
    # "From" header is the author
    # "Return-Path" header is the sender; the "envelope"
    #
    # Need to get this right so that SMTP servers that do "SPF" testing won't stop our email.
    # See http://en.wikipedia.org/wiki/Sender_Policy_Framework
            
    subject = 'CommCare HQ Domain Request ({domain_name})'.format(**locals())
    
    send_HTML_email(subject, recipient, text_content, html_content)

########################################################################################################

########################################################################################################

def _create_new_domain_request( request, kind, form, now ):
            
    dom_req = RegistrationRequest()
    dom_req.tos_confirmed = form.cleaned_data['tos_confirmed']
    dom_req.request_time = now
    dom_req.request_ip = request.META['REMOTE_ADDR']                
    dom_req.activation_guid = uuid.uuid1().hex         
 
    dom_is_active = False
    if kind == 'existing_user':
        dom_req.confirm_time = datetime.datetime.now()
        dom_req.confirm_ip = request.META['REMOTE_ADDR']     
        dom_is_active = True  
     
    # Req copies domain_id at initial assignment of Domain to req; does NOT get the ID from the 
    # copied Domain object just prior to Req save. Thus, we need to save the new domain before copying 
    # it over to the req, so the Domain will have a valid id 
    d = Domain(name = form.cleaned_data['domain_name'], is_active=dom_is_active)
    d.save()                                
    dom_req.domain = d                
                     
    ############# User     
    if kind == 'existing_user':   
        new_user = request.user
    else:        
        new_user = User()
        new_user.first_name = form.cleaned_data['first_name']
        new_user.last_name  = form.cleaned_data['last_name']
        new_user.username = form.cleaned_data['email']
        new_user.email = form.cleaned_data['email']
        assert(form.cleaned_data['password_1'] == form.cleaned_data['password_2'])
        new_user.set_password(form.cleaned_data['password_1'])                                                        
        new_user.is_staff = False # Can't log in to admin site
        new_user.is_active = False # Activated upon receipt of confirmation
        new_user.is_superuser = False           
        new_user.last_login = datetime.datetime(1970,1,1)
        new_user.date_joined = now
        # As above, must save to get id from db before giving to request
        new_user.save()
   
    dom_req.new_user = new_user

    ############# Couch Domain Membership
    if kind == "new_user":
        couch_user = CouchUser.from_web_user(new_user)
    else:
        couch_user = couch_user_from_django_user(new_user)
    couch_user.add_domain_membership(d.name, is_admin=True)
    couch_user.save()
    # Django docs say "use is_authenticated() to see if you have a valid user"
    # request.user is an AnonymousUser if not, and that always returns False                
    if request.user.is_authenticated():
        dom_req.requesting_user = request.user
                     
    dom_req.save()        
    return dom_req

########################################################################################################

# Neither login nor domain required here - outside users, not registered on our site, can request a domain
# Manual transaction because we want to update multiple objects atomically

@transaction.commit_on_success
def registration_request(request, kind=None):
    
    # Logic to decide whehter or not we're creating a new user to go with the new domain, or reusing the 
    # logged-in user's account. First we normalize kind, so it's a recognized value, and then we decide
    # what to do based in part on whether the user is logged in.    
    if not (kind=='new_user' or kind=='existing_user'):
        kind = None

    if request.user.is_authenticated():
        if kind is None:
            # Redirect to a page which lets user choose whether or not to create a new account
            vals = {}
            return render_to_response(request, 'domain/registration_reuse_account_p.html', vals)   
    else: # not authenticated
        kind = 'new_user' 
    assert(kind == 'existing_user' or kind == 'new_user')
    
    if request.method == 'POST': # If the form has been submitted...
        form = RegistrationRequestForm(kind, request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass                    
            
            # Make sure we haven't violated the max reqs per day. This is defined as "same calendar date, in UTC," 
            # NOT as "trailing 24 hours"            
            now = datetime.datetime.utcnow()
            reqs_today = RegistrationRequest.objects.filter(request_time__gte = now.date()).count()
            max_req = settings.DOMAIN_MAX_REGISTRATION_REQUESTS_PER_DAY            
            if reqs_today >= max_req:
                vals = {'error_msg':'Number of domains requested today exceeds limit ('+str(max_req)+') - contact Dimagi',
                        'show_homepage_link': 1 }
                return render_to_response(request, 'error.html', vals)   
            
            dom_req = _create_new_domain_request( request, kind, form, now )
            if kind == 'new_user': # existing_users are automatically activated; no confirmation email
                _send_domain_registration_email( dom_req.new_user.email, dom_req.domain.name,
                                          dom_req.activation_guid, dom_req.new_user.username )
  
    
            # Only gets here if the database-insert try block's else clause executed
            if kind == 'existing_user':
                vals = {'domain_name':dom_req.domain.name, 'username':request.user.email}
                return render_to_response(request, 'domain/registration_confirmed.html', vals)
            else: # new_user
                vals = dict(email=form.cleaned_data['email'])
                return render_to_response(request, 'domain/registration_received.html', vals)
    else:
        form = RegistrationRequestForm(kind) # An unbound form

    vals = dict(form = form, kind=kind)
    return render_to_response(request, 'domain/registration_form.html', vals)
    
########################################################################################################

# Neither login nor domain required here - outside users, not registered on our site, can request a domain
# Manual transaction because we want to update multiple objects atomically
@transaction.commit_manually
def registration_confirm(request, guid=None):
    
    # Did we get a guid?
    vals = {'show_homepage_link': 1 }    
    if guid is None:
        vals['error_msg'] = 'No domain activation key submitted - nothing to activate'                    
        return render_to_response(request, 'error.html', vals)
    
    # Does guid exist in the system?
    reqs = RegistrationRequest.objects.filter(activation_guid=guid) 
    if len(reqs) != 1:
        vals['error_msg'] = 'Submitted link is invalid - no domain with the activation key "' + guid + '" was requested'                     
        return render_to_response(request, 'error.html', vals)
    
    # Has guid already been confirmed?
    req = reqs[0]
    if req.domain.is_active:
        assert(req.confirm_time is not None and req.confirm_ip is not None)
        vals['error_msg'] = 'Domain "' +  req.domain.name + '" has already been activated - no further validation required'
        return render_to_response(request, 'error.html', vals)
    
    # Set confirm time and IP; activate domain and new user who is in the 
    try:
        req.confirm_time = datetime.datetime.now()
        req.confirm_ip = request.META['REMOTE_ADDR']     
        req.domain.is_active = True
        req.domain.save()
        req.new_user.is_active = True
        req.new_user.save() 
        req.save()
    except:
        transaction.rollback()                
        vals = {'error_msg':'There was a problem with your request',
                'error_details':sys.exc_info(),
                'show_homepage_link': 1 }
        return render_to_response(request, 'error.html', vals)
    else:
        transaction.commit()
        
    vals = {'domain_name':req.domain.name,            
            'username':req.new_user.username }
    return render_to_response(request, 'domain/registration_confirmed.html', vals)

########################################################################################################
#
# No login or domain test needed - this can be called by anonymous users
#

def registration_resend_confirm_email(request):  
    if request.method == 'POST': # If the form has been submitted...
        form = ResendConfirmEmailForm(request.POST) # A form bound to the POST data
        if form.is_valid():               
            dom_req = form.retrieved_domain.registrationrequest            
            try:
                _send_domain_registration_email( dom_req.new_user.email, dom_req.domain.name, dom_req.activation_guid, dom_req.new_user.username )
            except: 
                vals = {'error_msg':'There was a problem with your request',
                        'error_details':sys.exc_info(),
                        'show_homepage_link': 1 }
                return render_to_response(request, 'error.html', vals)
            else:        
                vals = dict(email=dom_req.new_user.email)
                return render_to_response(request, 'domain/registration_received.html', vals)
    else:
        form = ResendConfirmEmailForm()

    vals = dict(form=form)
    return render_to_response(request, 'domain/registration_resend_confirm_email.html', vals)

########################################################################################################
        
class UserTable(tables.Table):
    id = tables.Column(verbose_name="Id")
    username = tables.Column(verbose_name="Username")
    first_name = tables.Column(verbose_name="First name")
    last_name = tables.Column(verbose_name="Last name")
    is_active_auth = tables.Column(verbose_name="Active in system")
    is_active_member = tables.Column(verbose_name="Active in domain")
    is_domain_admin = tables.Column(verbose_name="Domain admin")
    last_login = tables.Column(verbose_name="Most recent login")
    invite_status = tables.Column(verbose_name="Invite status")    
        
########################################################################################################        

########################################################################################################

def _bool_to_yes_no( b ):
    return 'Yes' if b else 'No'

########################################################################################################

def _dict_for_one_user( user, domain ):
    retval = dict( id = user.id,
                   username = user.username,
                   first_name = user.first_name,
                   last_name = user.last_name,
                   is_active_auth = _bool_to_yes_no(user.is_active),          
                   last_login = user.last_login )                   
    
    is_active_member = user.domain_membership.filter(domain = domain)[0].is_active
    retval['is_active_member'] = _bool_to_yes_no(is_active_member)

    # TODO: update this to use new couch user permissions scheme 
    # ct = ContentType.objects.get_for_model(Domain) 
    # is_domain_admin = user.permission_set.filter(content_type = ct, 
    #                                             object_id = domain.id, 
    #                                             name=Permissions.ADMINISTRATOR)
    # retval['is_domain_admin'] = _bool_to_yes_no(is_domain_admin)
    retval['is_domain_admin'] = False
    
    # user is a unique get in the registrationprofile table; there can be at most
    # one invite per user, so if there is any invite at all, it's safe to just grab
    # the zero-th one
    invite_status = user.registrationprofile_set.all()
    if invite_status:
        if invite_status[0].activation_key == RegistrationProfile.ACTIVATED:
            val = 'Activated'
        else:
            val = 'Not activated'
    else:
        val = 'Admin added'
    retval['invite_status'] = val

    return retval                     
           
@require_domain_admin
def manage_domain(request, domain):
    return render_to_response(request, "domain/manage_domain.html", {})
