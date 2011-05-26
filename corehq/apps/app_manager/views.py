from django.http import HttpResponse, Http404, HttpResponseBadRequest
from corehq.apps.app_manager.xform import XFormError, XFormValidationError, CaseError
from corehq.apps.sms.views import get_sms_autocomplete_context
from corehq.apps.users.models import DomainMembership, require_permission
from dimagi.utils.web import render_to_response

from corehq.apps.app_manager.forms import NewXFormForm, NewAppForm, NewModuleForm

from corehq.apps.domain.decorators import login_and_domain_required

from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse, resolve
from corehq.apps.app_manager.models import RemoteApp, Application, VersionedDoc, get_app, DetailColumn, Form, FormAction, FormActionCondition, FormActions,\
    BuildErrors, AppError, load_case_reserved_words

from corehq.apps.app_manager.models import DETAIL_TYPES
from django.utils.http import urlencode

from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from dimagi.utils.web import get_url_base
from BeautifulSoup import BeautifulStoneSoup
import json
from dimagi.utils.make_uuid import random_hex
from utilities.profile import profile
import urllib
import urlparse
from collections import defaultdict
import random
from dimagi.utils.couch.database import get_db
from couchdbkit.resource import ResourceNotFound
import logging
from corehq.apps.app_manager.decorators import safe_download
try:
    from lxml.etree import XMLSyntaxError
except ImportError:
    import logging
    logging.error("lxml not installed! apps won't work properly!!")
from django.contrib import messages

_str_to_cls = {"Application":Application, "RemoteApp":RemoteApp}

class TemplateFunctions(object):
    @classmethod
    def make_uuid(cls):
        return random_hex()


def _encode_if_unicode(s):
    return s.encode('utf-8') if isinstance(s, unicode) else s
@login_and_domain_required
def back_to_main(req, domain, app_id='', module_id='', form_id='', edit=True, error='', **kwargs):
    """
    returns an HttpResponseRedirect back to the main page for the App Manager app
    with the correct GET parameters.

    This is meant to be used by views that process a POST request, which then redirect to the
    main page. The idiom for calling back_to_main used in this file is
        return back_to_main(**locals())
    which harvests the values for req, domain, app_id, module_id form_id, edit, and error from
    the local namespace.

    """
    params = {'m': module_id, 'f': form_id}
    if edit:
        params['edit'] = 'true'
    if error:
        params['error'] = error

    args = [domain]
    if app_id:
        args.append(app_id)
    view_name = 'default' if len(args) == 1 else 'view_app'
    return HttpResponseRedirect("%s%s" % (
        reverse('corehq.apps.app_manager.views.%s' % view_name, args=args),
        "?%s" % urlencode(params) if params else ""
    ))


def xform_display(req, domain, form_unique_id):
    form, app = Form.get_form(form_unique_id, and_app=True)
    if domain != app.domain: raise Http404
    langs = [req.GET.get('lang')] + app.langs

    questions = form.get_questions(langs)

    return HttpResponse(json.dumps(questions))

@login_and_domain_required
def form_casexml(req, domain, form_unique_id):
    form, app = Form.get_form(form_unique_id, and_app=True)
    if domain != app.domain: raise Http404
    return HttpResponse(form.create_casexml())

@login_and_domain_required
def app_source(req, domain, app_id):
    app = get_app(domain, app_id)
    return HttpResponse(json.dumps(app.export_json()))

@login_and_domain_required
def import_app(req, domain, template="app_manager/import_app.html"):
    if req.method == "POST":
        source = req.POST.get('source')
        name = req.POST.get('name')
        source = json.loads(source)
        try: del source['_attachments']
        except: pass
        if name:
            source['name'] = name
        cls = _str_to_cls[source['doc_type']]
        app = cls.from_source(source, domain)
        app.save()
        app_id = app._id
        return back_to_main(**locals())
    else:
        return render_to_response(req, template, {'domain': domain})

@require_permission('edit-apps')
@require_POST
def import_factory_app(req, domain):
    factory_app = get_app('factory', req.POST['app_id'])
    source = factory_app.export_json()
    name = req.POST.get('name')
    if name:
        source['name'] = name
    cls = _str_to_cls[source['doc_type']]
    app = cls.from_source(source, domain)
    app.save()
    app_id = app._id
    return back_to_main(**locals())

@require_permission('edit-apps')
@require_POST
def import_factory_module(req, domain, app_id):
    fapp_id, fmodule_id = req.POST['app_module_id'].split('/')
    fapp = get_app('factory', fapp_id)
    fmodule = fapp.get_module(fmodule_id)
    app = get_app(domain, app_id)
    source = fmodule.export_json()
    app.new_module_from_source(source)
    app.save()
    return back_to_main(**locals())

@require_permission('edit-apps')
@require_POST
def import_factory_form(req, domain, app_id, module_id):
    fapp_id, fmodule_id, fform_id = req.POST['app_module_form_id'].split('/')
    fapp = get_app('factory', fapp_id)
    fform = fapp.get_module(fmodule_id).get_form(fform_id)
    source = fform.export_json()
    app = get_app(domain, app_id)
    app.new_form_from_source(module_id, source)
    app.save()
    return back_to_main(**locals())


#@profile("apps_context.prof")
def _apps_context(req, domain, app_id='', module_id='', form_id=''):
    """
    Does most of the processing for creating the template context for the App Manager.
    It's currently only used by view_app, and the distribution of labor is not really
    that clear; for that reason, this may soon be revisited and merged with view_app

    """
    edit = (req.GET.get('edit', '') == 'true') and req.couch_user.can_edit_apps(domain)
    lang = req.GET.get('lang',
       req.COOKIES.get('lang', '')
    )

    factory_apps = [app['value'] for app in get_db().view('app_manager/factory_apps')]

    applications = []
    for app in get_db().view('app_manager/applications_brief', startkey=[domain], endkey=[domain, {}]).all():
        app = app['value']
        applications.append(app)
    app = module = form = None
    if app_id:
        app = get_app(domain, app_id)
    if module_id:
        module = app.get_module(module_id)
    if form_id:
        form = module.get_form(form_id)
    xform = ""
    xform_contents = ""
    try:
        xform = form
    except:
        pass
    if xform:
        xform_contents = form.contents


    if app and 'use_commcare_sense' in app:
        # grandfather in people who set commcare sense earlier
        if app['use_commcare_sense']:
            if 'features' not in app.profile:
                app.profile['features'] = {}
            app.profile['features']['sense'] = 'true'
        del app['use_commcare_sense']
        app.save()

    if app:
        saved_apps = [x['value'] for x in get_db().view('app_manager/saved_app',
            startkey=[domain, app_id, {}],
            endkey=[domain, app_id],
            descending=True
        ).all()]
    else:
        saved_apps = []
    if app and not app.langs:
        # lots of things fail if the app doesn't have any languages.
        # the best we can do is add 'en' if there's nothing else.
        app.langs.append('en')
        app.save()
    if app and (not lang or lang not in app.langs):
        lang = app.langs[0]

    langs = [lang] + (app.langs if app else [])

    case_fields = set()
    if module:
        for _form in module.forms:
            case_fields.update(_form.actions.update_case.update.keys())
    case_fields = sorted(case_fields)

    try:
        xform_questions = json.dumps(form.get_questions(langs) if form else [])
        # this is just to validate that the case and meta blocks can be created
        xform_errors = None
    except XMLSyntaxError as e:
        xform_questions = []
#        xform_errors = e.msg
        messages.error(req, "%s" % e)
    except AppError, e:
        #logging.exception(e)
        xform_questions = []
        messages.error(req, "Error in application: %s" % e)
    except XFormValidationError, e:
        #logging.exception(e)
        xform_questions = []
        message = unicode(e)
        # Don't display the first two lines which say "Parsing form..." and 'Title: "{form_name}"'
        for msg in message.split("\n")[2:]:
            messages.error(req, "%s" % msg)
    except XFormError, e:
        #logging.exception(e)
        xform_questions = []
        messages.error(req, "Error in form: %s" % e)
    # any other kind of error should fail hard, but for now there are too many for that to be practical
    except Exception, e:
        if settings.DEBUG:
            raise
        logging.exception(e)
        xform_questions = []
        messages.error(req, "Unexpected System Error: %s" % e)

    try:
        if form_id:
            app.fetch_xform(module_id, form_id)
    except CaseError, e:
        messages.error(req, "Error in Case Management: %s" % e)
    except Exception, e:
        logging.exception(e)
        messages.error(req, "Unexpected Error: %s" % e)

    build_errors_id = req.GET.get('build_errors', "")
    build_errors = []
    if build_errors_id:
        try:
            error_doc = BuildErrors.get(build_errors_id)
            build_errors = error_doc.errors
            error_doc.delete()
        except ResourceNotFound:
            pass
    context = {
        'domain': domain,
        'applications': applications,

        'app': app,
        'module': module,
        'form': form,

        'xform': xform,
        #'xform_contents': xform_contents,
        #'form_err': err if form and has_err else None,
        "xform_questions": xform_questions,
        #"xform_errors": xform_errors,
        'form_actions': json.dumps(form.actions.to_json()) if form else None,
        'case_fields': json.dumps(case_fields),

        'new_module_form': NewModuleForm(),
        'new_xform_form': NewXFormForm(),
        'edit': edit,
        'langs': langs,
        'lang': lang,

        'saved_apps': saved_apps,
        'factory_apps': factory_apps,
        'editor_url': settings.EDITOR_URL,
        'URL_BASE': get_url_base(),
        'XFORMPLAYER_URL': settings.XFORMPLAYER_URL,

        'build_errors': build_errors,

        'util': TemplateFunctions,
    }
    context.update(get_sms_autocomplete_context(req, domain))
    if form:
        context.update({'case_reserved_words_json': json.dumps(load_case_reserved_words())})
    return context

def default(req, domain):
    """
    Handles a url that does not include an app_id.
    Currently the logic is taken care of by view_app,
    but this view exists so that there's something to
    reverse() to. (I guess I should use url(..., name="default")
    in url.py instead?)


    """
    return view_app(req, domain, app_id='')

@login_and_domain_required
def view_app(req, domain, app_id=''):
    """
    This is the main view for the app. All other views redirect to here.

    """
    def bail():
        module_id=''
        form_id=''
        messages.error(req, 'Oops! We could not complete your request. Please try again')
        return back_to_main(req, domain, app_id)

    module_id = req.GET.get('m', '')
    form_id = req.GET.get('f', '')

    if form_id and not module_id:
        return bail()


    try:
        context = _apps_context(req, domain, app_id, module_id, form_id)
    except IndexError:
        return bail()

    if form_id:
        template="app_manager/form_view.html"
        try:
            languages = json.dumps(context['form'].wrapped_xform().get_languages())
        except:
            languages = []
        context.update({
            'xform_languages': languages
        })
    elif module_id:
        template="app_manager/module_view.html"
    else:
        template="app_manager/app_view.html"
    error = req.GET.get('error', '')



    app = context['app']
    if not app and context['applications']:
        app_id = context['applications'][0]['id']
        return back_to_main(edit=False, **locals())
    if app and app.copy_of:
        # don't fail hard.
        #raise Http404
        return HttpResponseRedirect(reverse("corehq.apps.app_manager.views.view_app", args=[domain,app.copy_of]))
    force_edit = False
    if (not context['applications']) or (app and app.doc_type == "Application" and not app.modules):
        edit = True
        force_edit = True
    context.update({
        'force_edit': force_edit,
        'error':error,
        'app': app,
    })
    response = render_to_response(req, template, context)
    response.set_cookie('lang', _encode_if_unicode(context['lang']))
    return response

@require_POST
@require_permission('edit-apps')
def new_app(req, domain):
    "Adds an app to the database"
    lang = req.COOKIES.get('lang', "en")
    type = req.POST["type"]
    cls = _str_to_cls[type]
    app = cls.new_app(domain, "Untitled Application", lang)
    if cls == Application:
        app.new_module("Untitled Module", lang)
        app.new_form(0, "Untitled Form", lang)
        module_id = 0
        form_id = 0
    app.save()
    app_id = app.id

    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def new_module(req, domain, app_id):
    "Adds a module to an app"
    app = get_app(domain, app_id)
    lang = req.COOKIES.get('lang', app.langs[0])
    name = req.POST.get('name')
    module = app.new_module(name, lang)
    module_id = module.id
    app.new_form(module_id, "Untitled Form", lang)
    app.save()
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def new_form(req, domain, app_id, module_id):
    "Adds a form to an app (under a module)"
    app = get_app(domain, app_id)
    lang = req.COOKIES.get('lang', app.langs[0])
    name = req.POST.get('name')
    form = app.new_form(module_id, name, lang)
    app.save()
    # add form_id to locals()
    form_id = form.id
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def delete_app(req, domain, app_id):
    "Deletes an app from the database"
    get_app(domain, app_id).delete()
    del app_id
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def delete_module(req, domain, app_id, module_id):
    "Deletes a module from an app"
    app = get_app(domain, app_id)
    app.delete_module(module_id)
    app.save()
    del module_id
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def delete_form(req, domain, app_id, module_id, form_id):
    "Deletes a form from an app"
    app = get_app(domain, app_id)
    app.delete_form(module_id, form_id)
    app.save()
    del form_id
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def edit_module_attr(req, domain, app_id, module_id, attr):
    """
    Called to edit any (supported) module attribute, given by attr
    """
    app = get_app(domain, app_id)
    module = app.get_module(module_id)
    lang = req.COOKIES.get('lang', app.langs[0])
    resp = {'update': {}}
    if   "case_type" == attr:
        module[attr] = req.POST.get(attr, None)
    elif "put_in_root" == attr:
        module[attr] = json.loads(req.POST.get(attr))
    elif "name" == attr:
        name = req.POST.get(attr, None)
        module[attr][lang] = name
        if attr == "name":
            resp['update'].update({'.variable-module_name': module.name[lang]})
    app.save(resp)
    return HttpResponse(json.dumps(resp))

@require_POST
@require_permission('edit-apps')
def edit_module_detail(req, domain, app_id, module_id):
    """
    Called to add a new module detail column or edit an existing one

    """
    column_id = int(req.POST.get('index', -1))
    detail_type = req.POST.get('detail_type', '')
    assert(detail_type in DETAIL_TYPES)

    column = dict((key, req.POST.get(key)) for key in (
        'header', 'model', 'field', 'format',
        'enum', 'late_flag', 'advanced'
    ))
    app = get_app(domain, app_id)
    module = app.get_module(module_id)
    lang = req.COOKIES.get('lang', app.langs[0])
    ajax = (column_id != -1) # edits are ajax, adds are not

    resp = {}

    def _enum_to_dict(enum):
        if not enum:
            return {}
        answ = {}
        for s in enum.split(','):
            key, val = (x.strip() for x in s.strip().split('='))
            answ[key] = {}
            answ[key][lang] = val
        return answ

    column['enum'] = _enum_to_dict(column['enum'])
    column['header'] = {lang: column['header']}
    column = DetailColumn.wrap(column)
    detail = app.get_module(module_id).get_detail(detail_type)

    if(column_id == -1):
        detail.append_column(column)
    else:
        detail.update_column(column_id, column)
    app.save(resp)
    column = detail.get_column(column_id)
    if(ajax):
        return HttpResponse(json.dumps(resp))
    else:
        return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def delete_module_detail(req, domain, app_id, module_id):
    """
    Called when a module detail column is to be deleted

    """
    column_id = int(req.POST['index'])
    detail_type = req.POST['detail_type']
    app = get_app(domain, app_id)
    module = app.get_module(module_id)
    module.get_detail(detail_type).delete_column(column_id)
    resp = {}
    app.save(resp)
    return HttpResponse(json.dumps(resp))
    #return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def edit_form_attr(req, domain, app_id, module_id, form_id, attr):
    """
    Called to edit any (supported) form attribute, given by attr

    """
    app = get_app(domain, app_id)
    form = app.get_module(module_id).get_form(form_id)
    lang = req.COOKIES.get('lang', app.langs[0])
    ajax = json.loads(req.POST.get('ajax', 'true'))

    resp = {}

    if   "requires" == attr:
        requires = req.POST['requires']
        form.requires = requires
    elif "name" == attr:
        name = req.POST['name']
        form.name[lang] = name
        resp['update'] = {'.variable-form_name': form.name[lang]}
    elif "xform" == attr:
        xform = req.FILES.get('xform')
        if xform:
            xform = xform.read()
            try:
                form.contents = unicode(xform, encoding="utf-8")
                form.refresh()
            except:
                messages.error(req, "Error uploading form: Please make sure your form is encoded in UTF-8")
        else:
            messages.error(req, "You didn't select a form to upload")
    elif "show_count" == attr:
        show_count = req.POST['show_count']
        form.show_count = True if show_count == "True" else False
    elif "put_in_root" == attr:
        put_in_root = req.POST['put_in_root']
        form.put_in_root = True if put_in_root == "True" else False
    app.save(resp)
    if ajax:
        return HttpResponse(json.dumps(resp))
    else:
        return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def rename_language(req, domain, form_unique_id):
    old_code = req.POST.get('oldCode')
    new_code = req.POST.get('newCode')
    form, app = Form.get_form(form_unique_id, and_app=True)
    if app.domain != domain:
        raise Http404
    form.rename_xform_language(old_code, new_code)
    app.save()
    return HttpResponse(json.dumps({"status": "ok"}))

@require_POST
@require_permission('edit-apps')
def edit_form_actions(req, domain, app_id, module_id, form_id):
    app = get_app(domain, app_id)
    form = app.get_module(module_id).get_form(form_id)
    form.actions = FormActions.wrap(json.loads(req.POST['actions']))
    app.save()
    return back_to_main(**locals())


@require_GET
@login_and_domain_required
def commcare_profile(req, domain, app_id):
    app = get_app(domain, app_id)
    return HttpResponse(json.dumps(app.profile))

@require_POST
@require_permission('edit-apps')
def edit_commcare_profile(req, domain, app_id):
    try:
        profile = json.loads(req.POST.get('profile'))
    except TypeError:
        return HttpResponseBadRequest(json.dumps({
            'reason': "Must have a param called profile set to: {\"properites\": {...}, \"features\": {...}}"
        }))
    app = get_app(domain, app_id)
    changed = defaultdict(dict)
    for type in ["features", "properties"]:
        for name, value in profile.get(type, {}).items():
            if type not in app.profile:
                app.profile[type] = {}
            app.profile[type][name] = value
            changed[type][name] = value
    app.save()
    return HttpResponse(json.dumps({"status": "ok", "changed": changed}))

@require_POST
@require_permission('edit-apps')
def edit_app_lang(req, domain, app_id):
    """
    Called when an existing language (such as 'zh') is changed (e.g. to 'zh-cn')
    or when a language is to be added.

    """
    lang = req.POST['lang']
    lang_id = int(req.POST.get('index', -1))
    app = get_app(domain, app_id)
    if lang_id == -1:
        if lang in app.langs:
            messages.error(req, "Language %s already exists")
        else:
            app.langs.append(lang)
            app.save()
    else:
        try:
            app.rename_lang(app.langs[lang_id], lang)
        except AppError as e:
            messages.error(req, unicode(e))
        else:
            app.save()

    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def delete_app_lang(req, domain, app_id):
    """
    Called when a language (such as 'zh') is to be deleted from app.langs

    """
    lang_id = int(req.POST['index'])
    app = get_app(domain, app_id)
    del app.langs[lang_id]
    app.save()
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def edit_app_attr(req, domain, app_id, attr):
    """
    Called to edit any (supported) app attribute, given by attr

    """
    app = get_app(domain, app_id)
    lang = req.COOKIES.get('lang', app.langs[0])

    resp = {"update": {}}
    # For either type of app
    if   "recipients" == attr:
        recipients = req.POST['recipients']
        app.recipients = recipients
    elif "name" == attr:
        name = req.POST["name"]
        app.name = name
        resp['update'].update({'.variable-app_name': name})
    elif "success_message" == attr:
        success_message = req.POST['success_message']
        app.success_message[lang] = success_message
    elif "use_commcare_sense" == attr:
        use_commcare_sense = json.loads(req.POST.get('use_commcare_sense', 'false'))
        app.use_commcare_sense = use_commcare_sense
    elif "native_input" == attr:
        native_input = json.loads(req.POST['native_input'])
        app.native_input = native_input
    # For RemoteApp
    elif "profile_url" == attr:
        if app.doc_type not in ("RemoteApp",):
            raise Exception("App type %s does not support profile url" % app.doc_type)
        app['profile_url'] = req.POST['profile_url']
    else:
        raise Http404
    app.save(resp)
    return HttpResponse(json.dumps(resp))


@require_POST
@require_permission('edit-apps')
def rearrange(req, domain, app_id, key):
    """
    This function handels any request to switch two items in a list.
    Key tells us the list in question and must be one of
    'forms', 'modules', 'detail', or 'langs'. The two POST params
    'to' and 'from' give us the indicies of the items to be rearranged.

    """
    app = get_app(domain, app_id)
    ajax = json.loads(req.POST.get('ajax', 'false'))
    i, j = (int(x) for x in (req.POST['to'], req.POST['from']))
    resp = {}


    if   "forms" == key:
        module_id = int(req.POST['module_id'])
        app.rearrange_forms(module_id, i, j)
    elif "modules" == key:
        app.rearrange_modules(i, j)
    elif "detail" == key:
        module_id = int(req.POST['module_id'])
        app.rearrange_detail_columns(module_id, req.POST['detail_type'], i, j)
    elif "langs" == key:
        app.rearrange_langs(i, j)
    app.save(resp)
    if ajax:
        return HttpResponse(json.dumps(resp))
    else:
        return back_to_main(**locals())


# The following three functions deal with
# Saving multiple versions of the same app

@require_POST
@require_permission('edit-apps')
def save_copy(req, domain, app_id):
    """
    Saves a copy of the app to a new doc.
    See VersionedDoc.save_copy

    """
    next = req.POST.get('next')
    app = get_app(domain, app_id)
    errors = app.validate_app()
    def replace_params(next, **kwargs):
        """this is a more general function that should be moved"""
        url = urlparse.urlparse(next)
        q = urlparse.parse_qs(url.query)
        for param in kwargs:
            if isinstance(kwargs[param], basestring):
                q[param] = [kwargs[param]]
            else:
                q[param] = kwargs[param]
        url = url._replace(query=urllib.urlencode(q, doseq=True))
        next = urlparse.urlunparse(url)
        return next
    if not errors:
        app.save_copy()
    else:
        errors = BuildErrors(errors=errors)
        errors.save()
        next = replace_params(next, build_errors=errors.get_id)
    return HttpResponseRedirect(next)

@require_POST
@require_permission('edit-apps')
def revert_to_copy(req, domain, app_id):
    """
    Copies a saved doc back to the original.
    See VersionedDoc.revert_to_copy

    """
    app = get_app(domain, app_id)
    copy = get_app(domain, req.POST['saved_app'])
    app = app.revert_to_copy(copy)
    return back_to_main(**locals())

@require_POST
@require_permission('edit-apps')
def delete_copy(req, domain, app_id):
    """
    Deletes a saved copy permanently from the database.
    See VersionedDoc.delete_copy

    """
    next = req.POST.get('next')
    app = get_app(domain, app_id)
    copy = get_app(domain, req.POST['saved_app'])
    app.delete_copy(copy)
    return HttpResponseRedirect(next)

# download_* views are for downloading the files that the application generates
# (such as CommCare.jad, suite.xml, profile.xml, etc.

BAD_BUILD_MESSAGE = "Sorry: this build is invalid. Try deleting it and rebuilding. If error persists, please contact us at commcarehq-support@dimagi.com"

@safe_download
def download_index(req, domain, app_id, template="app_manager/download_index.html"):
    """
    A landing page, mostly for debugging, that has links the jad and jar as well as
    all the resource files that will end up zipped into the jar.

    """
    app = get_app(domain, app_id)
    return render_to_response(req, template, {
        'app': app,
        'files': sorted(app.create_all_files().items()),
    })

@safe_download
def download_profile(req, domain, app_id):
    """
    See ApplicationBase.create_profile

    """
    return HttpResponse(
        get_app(domain, app_id).create_profile()
    )

def odk_install(req, domain, app_id):
    return render_to_response(req, "app_manager/odk_install.html",
                              {"domain": domain, "app": get_app(domain, app_id)})

def odk_qr_code(req, domain, app_id):
    qr_code = get_app(domain, app_id).get_odk_qr_code()
    return HttpResponse(qr_code, mimetype="image/png")

@safe_download
def download_odk_profile(req, domain, app_id):
    """
    See ApplicationBase.create_profile

    """
    return HttpResponse(
        get_app(domain, app_id).create_profile(is_odk=True),
        mimetype="commcare/profile"
    )

@safe_download
def download_suite(req, domain, app_id):
    """
    See Application.create_suite

    """
    return HttpResponse(
        get_app(domain, app_id).create_suite()
    )

@safe_download
def download_app_strings(req, domain, app_id, lang):
    """
    See Application.create_app_strings

    """
    return HttpResponse(
        get_app(domain, app_id).create_app_strings(lang)
    )

@safe_download
def download_xform(req, domain, app_id, module_id, form_id):
    """
    See Application.fetch_xform

    """
    return HttpResponse(
        get_app(domain, app_id).fetch_xform(module_id, form_id)
    )

@safe_download
def download_jad(req, domain, app_id):
    """
    See ApplicationBase.create_jadjar

    """
    app = get_app(domain, app_id)
    jad, _ = app.create_jadjar()
    try:
        response = HttpResponse(jad)
    except:
        messages.error(req, BAD_BUILD_MESSAGE)
        return back_to_main(**locals())
    response["Content-Disposition"] = "filename=%s.jad" % "CommCare"
    response["Content-Type"] = "text/vnd.sun.j2me.app-descriptor"
    return response

@safe_download
def download_jar(req, domain, app_id):
    """
    See ApplicationBase.create_jadjar

    This is the only view that will actually be called
    in the process of downloading a commplete CommCare.jar
    build (i.e. over the air to a phone).

    """
    response = HttpResponse(mimetype="application/java-archive")
    app = get_app(domain, app_id)
    response['Content-Disposition'] = "filename=%s.jar" % "CommCare"
    _, jar = app.create_jadjar()
    try:
        response.write(jar)
    except:
        messages.error(req, BAD_BUILD_MESSAGE)
        return back_to_main(**locals())
    return response

@safe_download
def download_raw_jar(req, domain, app_id):
    """
    See ApplicationBase.fetch_jar

    """
    response = HttpResponse(
        get_app(domain, app_id).fetch_jar()
    )
    response['Content-Type'] = "application/java-archive"
    return response

def emulator(req, domain, app_id, template="app_manager/emulator.html"):
    app = get_app(domain, app_id)
    if app.copy_of:
        app = get_app(domain, app.copy_of)
    return render_to_response(req, template, {
        'domain': domain,
        'app': app,
        'build_path': "/builds/1.2.dev/7106/Generic/WebDemo/",
    })

def emulator_commcare_jar(req, domain, app_id):
    response = HttpResponse(
        get_app(domain, app_id).fetch_emulator_commcare_jar()
    )
    response['Content-Type'] = "application/java-archive"
    return response
