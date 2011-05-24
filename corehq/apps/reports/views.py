from collections import defaultdict
from datetime import datetime, timedelta
import json
from couchdbkit.ext.django.schema import Document
import dateutil.parser
from corehq.apps.users.models import CouchUser
from corehq.apps.users.util import raw_username, format_username
from couchforms.models import XFormInstance
from dimagi.utils.couch.loosechange import parse_date
from dimagi.utils.web import json_response, json_request, render_to_response
from dimagi.utils.couch.database import get_db
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseBadRequest
from django.core.urlresolvers import reverse
from .googlecharts import get_punchcard_url
from .calc import punchcard
from corehq.apps.domain.decorators import login_and_domain_required
from dimagi.utils.couch.pagination import CouchPaginator, ReportBase
import couchforms.views as couchforms_views
from couchexport.export import export, Format
from StringIO import StringIO
from django.contrib import messages
from dimagi.utils.parsing import json_format_datetime

#def report_list(request, domain):
#    template = "reports/report_list.html"
#    return render_to_response(request, template, {'domain': domain})

def user_id_to_username(user_id):
    if not user_id:
        return user_id
    try:
        login = get_db().get(user_id)
    except:
        return user_id
    return raw_username(login['django_user']['username'])

def xmlns_to_name(xmlns, domain, html=False):
    try:
        form = get_db().view('reports/forms_by_xmlns', key=[domain, xmlns], group=True).one()['value']
        langs = ['en'] + form['app']['langs']
    except:
        form = None

    if form:
        module_name = form_name = None
        for lang in langs:
            module_name = module_name if module_name is not None else form['module']['name'].get(lang)
            form_name = form_name if form_name is not None else form['form']['name'].get(lang)
        if module_name is None:
            module_name = "None"
        if form_name is None:
            form_name = "None"
        if html:
            name = "<a href='%s'>%s &gt; %s &gt; %s</a>" % (
                reverse("corehq.apps.app_manager.views.view_app", args=[domain, form['app']['id']])
                + "?m=%s&f=%s" % (form['module']['id'], form['form']['id']),
                form['app']['name'],
                module_name,
                form_name
            )
        else:
            name = "%s > %s > %s" % (form['app']['name'], module_name, form_name)
    else:
        name = xmlns
    return name

@login_and_domain_required
def default(request, domain):
    return HttpResponseRedirect(reverse("submission_log_report", args=[domain]))

@login_and_domain_required
def export_data(req, domain):
    """
    Download all data for a couchdbkit model
    """
    try:
        export_tag = json.loads(req.GET.get("export_tag", "null") or "null")
    except ValueError:
        return HttpResponseBadRequest()

    format = req.GET.get("format", Format.XLS_2007)
    next = req.GET.get("next", "")
    if not next:
        next = reverse('excel_export_data_report', args=[domain])
    tmp = StringIO()
    if export([domain, export_tag], tmp, format=format):
        response = HttpResponse(mimetype='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename=%s.%s' % (export_tag, format)
        response.write(tmp.getvalue())
        tmp.close()
        return response
    else:
        messages.error(req, "Sorry, there was no data found for the tag '%s'." % export_tag)
        return HttpResponseRedirect(next)


class SubmitHistory(ReportBase):
    def __init__(self, request, domain, individual, show_unregistered="false"):
        self.request = request
        self.domain = domain
        self.individual = individual
        self.show_unregistered = True #json.loads(show_unregistered)

    @classmethod
    def view(cls, request, domain, template="reports/partials/couch_report_partial.html"):

        individual = request.GET.get('individual', '')
        show_unregistered = request.GET.get('show_unregistered', 'false')
        rows = []

        headings = ["View Form", "Username", "Submit Time", "Form"]
        return render_to_response(request, template, {
            'headings': headings,
            'rows': rows,
            'ajax_source': reverse('paging_submit_history', args=[domain, individual, show_unregistered]),
        })
    def rows(self, skip, limit):
        def format_time(time):
            "time is an ISO timestamp"
            return time.replace('T', ' ').replace('Z', '')
        def form_data_link(instance_id):
            return "<a class='ajax_dialog' href='%s'>View Form</a>" % reverse('render_form_data', args=[self.domain, instance_id])
        if self.individual:
            rows = get_db().view('reports/submit_history',
                endkey=[self.domain, self.individual],
                startkey=[self.domain, self.individual, {}],
                descending=True,
                reduce=False,
                skip=skip,
                limit=limit,
            )
            def view_to_table(row):
                time = row['value'].get('time')
                xmlns = row['value'].get('xmlns')
                username = user_id_to_username(self.individual)

                time = format_time(time)
                xmlns = xmlns_to_name(xmlns, html=True)
                return [form_data_link(row['id']), username, time, xmlns]

        else:
            rows = get_db().view('reports/all_submissions',
                endkey=[self.domain],
                startkey=[self.domain, {}],
                descending=True,
                reduce=False,
                skip=skip,
                limit=limit,
            )
            def view_to_table(row):
                time = row['value'].get('time')
                xmlns = row['value'].get('xmlns')
                user_id = row['value'].get('user_id')
                fake_name = row['value'].get('username')

                time = format_time(time)
                xmlns = xmlns_to_name(xmlns, html=True)
                username = user_id_to_username(user_id)
                if username:
                    return [form_data_link(row['id']), username, time, xmlns]
                elif self.show_unregistered:
                    username = '"%s" (unregistered)' % fake_name if fake_name else "(unregistered)"
                    return [form_data_link(row['id']), username, time, xmlns]

        return [view_to_table(row) for row in rows]
    def count(self):
        try:
            if self.individual:
                return get_db().view('reports/submit_history',
                    startkey=[self.domain, self.individual],
                    endkey=[self.domain, self.individual, {}],
                    group=True,
                    group_level=2
                ).one()['value']
            else:
                return get_db().view('reports/all_submissions',
                    startkey=[self.domain],
                    endkey=[self.domain, {}],
                    group=True,
                    group_level=1
                ).one()['value']
        except TypeError:
            return 0

@login_and_domain_required
def active_cases(request, domain):

    rows = []

    headings = ["Username", "Active/Open Cases (%)", "Late Cases", "Average Days Late", "Visits Last Week"
        #"Open Referrals", "Active Referrals"
    ]

    return render_to_response(request, "reports/generic_report.html", {
        "domain": domain,
        "report": {
            "name": "Case Activity",
            "headers": headings,
            "rows": rows,
        },
        "ajax_source": reverse('paging_active_cases', args=[domain]),
    })

@login_and_domain_required
def paging_active_cases(request, domain):

    days = 31
    def get_active_cases(userid, days=days):
        since_date = datetime.utcnow() - timedelta(days=days)
        r = get_db().view('case/by_last_date',
            startkey=[domain, userid, json_format_datetime(since_date)],
            endkey=[domain, userid, {}],
            group=True,
            group_level=0
        ).one()
        return r['value']['count'] if r else 0
    def get_late_cases(userid, days=days):
        EPOCH = datetime(1970, 1, 1)
        since_date = datetime.utcnow() - timedelta(days=days)
        DAYS = (since_date - EPOCH).days
        r = get_db().view('case/by_last_date',
            startkey=[domain, userid],
            endkey=[domain, userid, json_format_datetime(since_date)],
            group=True,
            group_level=0
        ).one()

        return (r['value']['count']*DAYS-r['value']['sum'], r['value']['count']) if r else (0,0)
    def get_forms_completed(userid, days=7):
        since_date = datetime.utcnow() - timedelta(days=days)
        r = get_db().view('reports/submit_history',
            startkey=[domain, userid, json_format_datetime(since_date)],
            endkey=[domain, userid, {}],
            group=True,
            group_level=0
        ).one()
        return r['value'] if r else 0

    def view_to_table(row):
        keys = row['value']

        open_cases = get_db().view('case/open_cases', keys=[[domain, key] for key in keys], group=True)
        open_cases = sum(map(lambda x: x['value'], open_cases))

        active_cases = sum(map(get_active_cases, keys))

        days_late, cases_late = map(sum, zip(*map(get_late_cases, keys)))

        visits = sum(map(get_forms_completed, keys))

        assert(open_cases-active_cases == cases_late)
        return [
            user_id_to_username(keys[0]),
            "%s/%s (%d%%)" % (active_cases, open_cases,  (active_cases*100/open_cases)) if open_cases else "--",
            "%s cases" % cases_late if cases_late else "--",
            "%.1f" % (days_late/cases_late) if cases_late > 1 else "%d" % (days_late/cases_late) if cases_late \
            else "--",
            visits
        ]

    paginator = CouchPaginator(
        "users/collated_commcare_users",
        view_to_table,
        search=False,
        view_args=dict(
            startkey=[domain],
            endkey=[domain, {}],
            descending=False
        )
    )
    return paginator.get_ajax_response(request)


@login_and_domain_required
def submit_time_punchcard(request, domain):
    individual = request.GET.get("individual", '')
    data = punchcard.get_data(domain, individual)
    url = get_punchcard_url(data)
    #user_data = punchcard.get_users(domain)
#    if individual:
#        selected_user = [user for user, _ in user_data if user["_id"] == user_id][0]
#        name = "Punchcard Report for %s at %s" % (render_user_inline(selected_user))
    return render_to_response(request, "reports/punchcard.html", {
        "chart_url": url,
        #"user_data": user_data,
        #"clinic_id": clinic_id,
        #"user_id": user_id
    })

@login_and_domain_required
def user_summary(request, domain, template="reports/user_summary.html"):
    report_name = "User Summary Report (number of forms filled in by person)"

    return render_to_response(request, template, {
        "domain": domain,
        "show_dates": False,
        "report": {
            "name": report_name
        },
        "ajax_source": reverse('paging_user_summary', args=[domain]),
    })

@login_and_domain_required
def paging_user_summary(request, domain):

    def view_to_table(row):
        row['last_submission_date'] = dateutil.parser.parse(row['last_submission_date'])
        return row
    paginator = CouchPaginator(
        "reports/user_summary",
        view_to_table,
        search=False,
        view_args=dict(
            group=True,
            startkey=[domain],
            endkey=[domain, {}],
        )
    )
    return paginator.get_ajax_response(request)

@login_and_domain_required
def submission_log(request, domain):
    individual = request.GET.get('individual', '')
    show_unregistered = request.GET.get('show_unregistered', 'false')
    if individual:
        pass

    user_ids = get_db().view('reports/all_users', startkey=[domain], endkey=[domain, {}], group=True)
    user_ids = [result['key'][1] for result in user_ids]
    users = []
    for user_id in user_ids:
        username = user_id_to_username(user_id)
        if username:
            users.append({'id': user_id, 'username': username})

    return render_to_response(request, "reports/submission_log.html", {
        "domain": domain,
        "show_users": True,
        "report": {
            "name": "Submission Log",
            "header": [],
            "rows": [],
        },
        "users": users,
        "individual": individual,
        "show_unregistered": show_unregistered,
    })

@login_and_domain_required
def daily_submissions(request, domain, view_name, title):
    start_date = request.GET.get('startdate')
    end_date = request.GET.get('enddate')
    if end_date:
        end_date = date(*map(int, end_date.split('-')))
    else:
        end_date = datetime.utcnow().date()

    if start_date:
        start_date = date(*map(int, start_date.split('-')))
    else:
        start_date = (end_date- timedelta(days=6))
    results = get_db().view(
        view_name,
        group=True,
        startkey=[domain, start_date.isoformat()],
        endkey=[domain, end_date.isoformat(), {}]
    ).all()
    all_users_results = get_db().view("reports/all_users", startkey=[domain], endkey=[domain, {}], group=True).all()
    user_ids = [result['key'][1] for result in all_users_results]
    dates = [start_date]
    while dates[-1] < end_date:
        dates.append(dates[-1] + timedelta(days=1))
    date_map = dict([(date.isoformat(), i+1) for (i,date) in enumerate(dates)])
    user_map = dict([(user_id, i) for (i, user_id) in enumerate(user_ids)])
    rows = [[0]*(1+len(date_map)) for i in range(len(user_ids) + 1)]
    for result in results:
        _, date, user_id = result['key']
        val = result['value']
        if user_id in user_map:
            rows[user_map[user_id]][date_map[date]] = val
        else:
            rows[-1][date_map[date]] = val # use the last row for unknown data
            rows[-1][0] = "UNKNOWN USER" # use the last row for unknown data
    for i,user_id in enumerate(user_ids):
        rows[i][0] = user_id_to_username(user_id)

    valid_rows = []
    for row in rows:
        # include submissions from unknown/empty users that have them
        if row[0] or sum(row[1:]):
            valid_rows.append(row)
    rows = valid_rows
    headers = ["Username"] + dates
    return render_to_response(request, "reports/generic_report.html", {
        "domain": domain,
        "show_dates": True,
        "start_date": start_date,
        "end_date": end_date,
        "report": {
            "name": title,
            "headers": headers,
            "rows": rows,
        }
    })

@login_and_domain_required
def excel_export_data(request, domain, template="reports/excel_export_data.html"):
    forms = get_db().view('reports/forms_by_xmlns', startkey=[domain], endkey=[domain, {}], group=True)
    forms = [x['value'] for x in forms]

    forms = sorted(forms, key=lambda form: \
        (0, form['app']['name'], form['module']['id'], form['form']['id']) \
        if 'app' in form else \
        (1, form['xmlns'])
    )

    apps = []
    unknown_forms = []

    # organize forms into apps, modules, forms:
    #        apps = [
    #            {
    #                "name": "App",
    #                "modules": [
    #                    {
    #                        "name": "Module 1",
    #                        "id": 1,
    #                        "forms": [
    #                            {...}
    #                        ]
    #                    }
    #                ]
    #
    #            }
    #        ]

    for f in forms:
        if 'app' in f:
            if apps and f['app']['name'] == apps[-1]['name']:
                if f['module']['id'] == apps[-1]['modules'][-1]['id']:
                    apps[-1]['modules'][-1]['forms'].append(f)
                else:
                    module = f['module'].copy()
                    module.update(forms=[f])
                    apps[-1]['modules'].append(module)
            else:
                app = f['app'].copy()
                module = f['module'].copy()
                module.update(forms=[f])
                app.update(modules=[module])
                apps.append(app)

        else:
            unknown_forms.append(f)


    return render_to_response(request, template, {
        "domain": domain,
        "forms": forms,
        "forms_by_app": apps,
        "unknown_forms": unknown_forms,
        "report": {
            "name": "Export Data to Excel"
        }
    })

@login_and_domain_required
def form_data(request, domain, instance_id):
    instance = XFormInstance.get(instance_id)
    assert(domain == instance.domain)
    return render_to_response(request, "reports/form_data.html", dict(domain=domain,instance=instance))

@login_and_domain_required
def download_form(request, domain, instance_id):
    instance = XFormInstance.get(instance_id)
    assert(domain == instance.domain)
    return couchforms_views.download_form(request, instance_id)


# Weekly submissions by xmlns

def mk_date_range(start=None, end=None, ago=timedelta(days=7), iso=False):
    if isinstance(end, basestring):
        end = parse_date(end)
    if isinstance(start, basestring):
        start = parse_date(start)
    if not end:
        end = datetime.utcnow()
    if not start:
        start = end - ago
    if iso:
        return json_format_datetime(start), json_format_datetime(end)
    else:
        return start, end

#Document.__repr__ = lambda self: repr(self.to_json())

@login_and_domain_required
def submissions_by_form(request, domain):
    users = CouchUser.commcare_users_by_domain(domain)
    userIDs = [user.userID for user in users]
    counts = submissions_by_form_json(domain=domain, userIDs=userIDs, **json_request(request.GET))
    form_types = _relevant_form_types(domain=domain, userIDs=userIDs, **json_request(request.GET))
    form_names = [xmlns_to_name(xmlns, domain) for xmlns in form_types]
    form_names = [name.replace("/", " / ") for name in form_names]

    form_names, form_types = zip(*sorted(zip(form_names, form_types)))

    rows = []
    totals_by_form = defaultdict(int)

    for user in users:
        row = []
        for form_type in form_types:
            userID = user.userID
            try:
                count = counts[userID][form_type]
                row.append(count)
                totals_by_form[form_type] += count
            except:
                row.append(0)
        rows.append([user.raw_username] + row + ["* %s" % sum(row)])

    totals_by_form = [totals_by_form[form_type] for form_type in form_types]
    
    rows.append(["* All Users"] + ["* %s" % t for t in totals_by_form] + ["* %s" % sum(totals_by_form)])
    report = {
        "name": "Case Activity",
        "headers": ['User'] + list(form_names) + ['All Forms'],
        "rows": rows,
    }
    return render_to_response(request, 'reports/generic_report.html', {
        "domain": domain,
        "report": report,
    })


def _relevant_form_types(domain, userIDs=None, start=None, end=None):
    start, end = mk_date_range(start, end, iso=True)
    submissions = XFormInstance.view('reports/all_submissions',
        startkey=[domain, start],
        endkey=[domain, end],
        include_docs=True,
        reduce=False
    )
    form_types = set()
    for submission in submissions:
        try:
            xmlns = submission['xmlns']
        except KeyError:
            xmlns = None
        if userIDs is not None:
            try:
                userID = submission['form']['meta']['userID']
                if userID in userIDs:
                    form_types.add(xmlns)
            except:
                pass
        else:
            form_types.add(xmlns)

    return sorted(form_types)

def submissions_by_form_json(domain, start=None, end=None, userIDs=None):
    start, end = mk_date_range(start, end, iso=True)
    submissions = XFormInstance.view('reports/all_submissions',
        startkey=[domain, start],
        endkey=[domain, end],
        include_docs=True,
        reduce=False
    )
    print userIDs
    counts = defaultdict(lambda: defaultdict(int))
    for sub in submissions:
        try:
            userID = sub['form']['meta']['userID']
            if (userIDs is None) or (userID in userIDs):
                print userID
                counts[userID][sub['xmlns']] += 1
        except:
            # if a form don't even have a userID, don't even bother tryin'
            pass
    return counts