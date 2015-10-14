from __future__ import absolute_import
from collections import defaultdict, namedtuple
from datetime import datetime, date, time
import re
from lxml import etree
import os
from django.conf import settings
from corehq.apps.app_manager.util import all_apps_by_domain
from corehq.util.quickcache import quickcache
from couchforms.models import XFormDeprecated


class OpenClinicaIntegrationError(Exception):
    pass


Item = namedtuple('Item', ('study_event_oid', 'form_oid', 'item_group_oid', 'item_oid'))
AdminDataUser = namedtuple('AdminDataUser', ('user_id', 'first_name', 'last_name'))
OpenClinicaUser = namedtuple('OpenClinicaUser', ('user_id', 'first_name', 'last_name', 'username', 'full_name'))


# CDISC OMD XML namespace map
odm_nsmap = {
    'odm': "http://www.cdisc.org/ns/odm/v1.3",
    'OpenClinica': "http://www.openclinica.org/ns/odm_ext_v130/v3.1",
    'OpenClinicaRules': "http://www.openclinica.org/ns/rules/v3.1",
    'xsi': "http://www.w3.org/2001/XMLSchema-instance",
}


def simplify(fancy):
    """
    Replace dict-like data types with dicts, and list-like data types with lists

    >>> from collections import defaultdict
    >>> simplify(defaultdict(list, {'bacon': ['spam']}))
    {'bacon': ['spam']}
    >>> simplify(('ham',))
    ['ham']
    >>> simplify({'spam'})
    ['spam']

    """
    if hasattr(fancy, 'keys'):
        return {simplify(k): simplify(fancy[k]) for k in fancy.keys()}
    elif isinstance(fancy, unicode):
        return fancy.encode('utf8')
    elif isinstance(fancy, str):
        return fancy
    elif hasattr(fancy, '__iter__'):
        return [simplify(i) for i in fancy]
    else:
        return fancy


@quickcache(['domain'])
def get_question_items(domain):
    """
    Return a map of CommCare form questions to OpenClinica form items
    """

    def get_item_prefix(form_oid, ig_oid):
        """
        OpenClinica item OIDs are prefixed with "I_<prefix>_" where <prefix> is derived from the item's form OID

        (Dropping "I_<prefix>_" will give us the CommCare question name in upper case)
        """
        form_name = form_oid[2:]  # Drop "F_"
        ig_name = ig_oid[3:]  # Drop "IG_"
        prefix = os.path.commonprefix((form_name, ig_name))
        if prefix.endswith('_'):
            prefix = prefix[:-1]
        return prefix

    def read_question_item_map(odm):
        """
        Return a dictionary of {question: (study_event_oid, form_oid, item_group_oid, item_oid)}
        """
        question_item_map = {}  # A dictionary of question: (study_event_oid, form_oid, item_group_oid, item_oid)

        meta_e = odm.xpath('./odm:Study/odm:MetaDataVersion', namespaces=odm_nsmap)[0]

        for se_ref in meta_e.xpath('./odm:Protocol/odm:StudyEventRef', namespaces=odm_nsmap):
            se_oid = se_ref.get('StudyEventOID')
            for form_ref in meta_e.xpath('./odm:StudyEventDef[@OID="{}"]/odm:FormRef'.format(se_oid),
                                         namespaces=odm_nsmap):
                form_oid = form_ref.get('FormOID')
                for ig_ref in meta_e.xpath('./odm:FormDef[@OID="{}"]/odm:ItemGroupRef'.format(form_oid),
                                           namespaces=odm_nsmap):
                    ig_oid = ig_ref.get('ItemGroupOID')
                    prefix = get_item_prefix(form_oid, ig_oid)
                    prefix_len = len(prefix) + 3  # len of "I_<prefix>_"
                    for item_ref in meta_e.xpath('./odm:ItemGroupDef[@OID="{}"]/odm:ItemRef'.format(ig_oid),
                                                 namespaces=odm_nsmap):
                        item_oid = item_ref.get('ItemOID')
                        question = item_oid[prefix_len:].lower()
                        question_item_map[question] = Item(se_oid, form_oid, ig_oid, item_oid)
        return question_item_map

    def read_forms(question_item_map):
        data = defaultdict(dict)
        for domain_, pymodule in settings.DOMAIN_MODULE_MAP.iteritems():
            if pymodule == 'custom.openclinica':
                for app in all_apps_by_domain(domain_):
                    for ccmodule in app.get_modules():
                        for ccform in ccmodule.get_forms():
                            form = data[ccform.xmlns]
                            form['app'] = app.name
                            form['module'] = ccmodule.name['en']
                            form['name'] = ccform.name['en']
                            form['questions'] = {}
                            for question in ccform.get_questions(['en']):
                                name = question['value'].split('/')[-1]
                                form['questions'][name] = question_item_map.get(name)
        return data

    metadata_xml = get_study_metadata(domain)
    map_ = read_question_item_map(metadata_xml)
    question_items = read_forms(map_)
    return question_items


def get_question_item(domain, form_xmlns, question):
    """
    Returns an Item namedtuple given a CommCare form and question name
    """
    question_items = get_question_items(domain)
    try:
        se_oid, form_oid, ig_oid, item_oid = question_items[form_xmlns]['questions'][question]
        return Item(se_oid, form_oid, ig_oid, item_oid)
    except KeyError:
        raise OpenClinicaIntegrationError('Unknown CommCare question "{}". Please run `./manage.py '
                                          'map_questions_to_openclinica`'.format(question))
    except TypeError:
        # CommCare question does not match an OpenClinica item. This happens with CommCare-only forms
        return None


@quickcache(['domain'])
def get_study_metadata_string(domain):
    """
    Return the study metadata for the given domain as a string

    Metadata is fetched from the OpenClinica web service
    """
    from custom.openclinica.models import OpenClinicaAPI

    oc_settings = settings.OPENCLINICA[domain]
    api = OpenClinicaAPI(oc_settings['URL'], oc_settings['USER'], oc_settings['PASSWORD'])
    study_client = api.get_client('study')
    reply = study_client.service.listAll()
    try:
        study = [s for s in reply.studies.study if s.name == oc_settings['STUDY']][0]
    except IndexError:
        raise OpenClinicaIntegrationError('Study "{}" not found on OpenClinica.'.format(oc_settings['STUDY']))
    study_client.set_options(retxml=True)  # Don't parse the study metadata; just give us the raw XML
    reply = study_client.service.getMetadata(study)
    soap_env = etree.fromstring(reply)
    nsmap = {
        'SOAP-ENV': "http://schemas.xmlsoap.org/soap/envelope/",
        'OC': "http://openclinica.org/ws/study/v1"
    }
    odm = soap_env.xpath('./SOAP-ENV:Body/OC:createResponse/OC:odm', namespaces=nsmap)[0]
    return odm.text


def get_study_metadata(domain):
    """
    Return the study metadata for the given domain as an XML element
    """
    return etree.fromstring(get_study_metadata_string(domain))


def get_study_constant(domain, name):
    """
    Return the study metadata of the given name for the given domain
    """
    xpath_text = lambda xml, xpath: xml.xpath(xpath, namespaces=odm_nsmap)[0].text
    xpath_xml = lambda xml, xpath: etree.tostring(xml.xpath(xpath, namespaces=odm_nsmap)[0])
    func = {
        'study_oid': lambda xml: xml.xpath('./odm:Study', namespaces=odm_nsmap)[0].get('OID'),
        'study_name': lambda xml: xpath_text(xml, './odm:Study/odm:GlobalVariables/odm:StudyName'),
        'study_description': lambda xml: xpath_text(xml, './odm:Study/odm:GlobalVariables/odm:StudyDescription'),
        'protocol_name': lambda xml: xpath_text(xml, './odm:Study/odm:GlobalVariables/odm:ProtocolName'),
        'study_xml': lambda xml: xpath_xml(xml, './odm:Study'),
        'admin_data_xml': lambda xml: xpath_xml(xml, './odm:AdminData'),
    }[name]
    metadata_xml = get_study_metadata(domain)
    return func(metadata_xml)


def get_item_measurement_unit(domain, item):
    """
    Return the measurement unit OID for the given Item, or None
    """
    xml = get_study_metadata(domain)
    mu_ref = xml.xpath(
        './odm:Study/odm:MetaDataVersion/odm:ItemDef[@OID="{}"]/odm:MeasurementUnitRef'.format(item.item_oid),
        namespaces=odm_nsmap)
    return mu_ref[0].get('MeasurementUnitOID') if mu_ref else None


def get_study_event_name(domain, oid):
    xml = get_study_metadata(domain)
    return xml.xpath('./odm:Study/odm:MetaDataVersion/odm:StudyEventDef[@OID="{}"]'.format(oid),
                     namespaces=odm_nsmap)[0].get('Name')


def is_study_event_repeating(domain, oid):
    xml = get_study_metadata(domain)
    return xml.xpath('./odm:Study/odm:MetaDataVersion/odm:StudyEventDef[@OID="{}"]'.format(oid),
                     namespaces=odm_nsmap)[0].get('Repeating') == 'Yes'


def is_item_group_repeating(domain, oid):
    xml = get_study_metadata(domain)
    return xml.xpath('./odm:Study/odm:MetaDataVersion/odm:ItemGroupDef[@OID="{}"]'.format(oid),
                     namespaces=odm_nsmap)[0].get('Repeating') == 'Yes'


def mk_oc_username(cc_username):
    """
    Makes a username that meets OpenClinica requirements from a CommCare username.

    Strips off "@domain.name", replaces non-alphanumerics, and pads with "_" if less than 5 characters

    >>> mk_oc_username('eric.idle@montypython.com')
    'eric_idle'
    >>> mk_oc_username('eric')
    'eric_'
    >>> mk_oc_username('I3#')
    'I3___'

    """
    username = cc_username.split('@')[0]
    username = re.sub(r'[^\w]', '_', username)
    if len(username) < 5:
        username += '_' * (5 - len(username))
    return username


@quickcache(['domain'])
def get_oc_users_by_name(domain):
    # We have to look up OpenClinica users by name because usernames are excluded from study metadata
    oc_users_by_name = {}
    xml = get_study_metadata(domain)
    admin = xml.xpath('./odm:AdminData', namespaces=odm_nsmap)[0]
    for user_e in admin:
        try:
            first_name = user_e.xpath('./odm:FirstName', namespaces=odm_nsmap)[0].text
        except IndexError:
            first_name = None
        try:
            last_name = user_e.xpath('./odm:LastName', namespaces=odm_nsmap)[0].text
        except IndexError:
            last_name = None
        user_id = user_e.get('OID')
        oc_users_by_name[(first_name, last_name)] = AdminDataUser(user_id, first_name, last_name)
    return oc_users_by_name


def get_oc_user(domain, cc_user):
    """
    Returns OpenClinica user details for corresponding CommCare user (CouchUser)
    """
    oc_users_by_name = get_oc_users_by_name(domain)
    oc_user = oc_users_by_name.get((cc_user.first_name, cc_user.last_name))
    return OpenClinicaUser(
        user_id=oc_user.user_id,
        username=mk_oc_username(cc_user.username),
        first_name=oc_user.first_name,
        last_name=oc_user.last_name,
        full_name=' '.join((oc_user.first_name, oc_user.last_name)),
    ) if oc_user else None


def oc_format_date(answer):
    """
    Format CommCare datetime answers for OpenClinica

    >>> from datetime import datetime
    >>> answer = datetime(2015, 8, 19, 19, 8, 15)
    >>> oc_format_date(answer)
    '2015-08-19 19:08:15'

    """
    if isinstance(answer, datetime):
        return answer.isoformat(sep=' ')
    if isinstance(answer, date) or isinstance(answer, time):
        return answer.isoformat()
    return answer


def originals_first(forms):
    """
    Return original (deprecated) forms before edited versions
    """
    def get_previous_versions(form_id):
        form_ = XFormDeprecated.get(form_id)
        if getattr(form_, 'deprecated_form_id', None):
            return get_previous_versions(form_.deprecated_form_id) + [form_]
        else:
            return [form_]

    for form in forms:
        if getattr(form, 'deprecated_form_id', None):
            for previous in get_previous_versions(form.deprecated_form_id):
                yield previous
        yield form
