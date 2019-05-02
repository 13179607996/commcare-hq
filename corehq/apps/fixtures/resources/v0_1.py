from __future__ import absolute_import, unicode_literals

from couchdbkit import ResourceNotFound
from tastypie import fields as tp_f
from tastypie.exceptions import BadRequest, ImmediateHttpResponse, NotFound
from tastypie.http import HttpAccepted
from tastypie.resources import Resource

from dimagi.utils.couch.bulk import CouchTransaction

from corehq.apps.api.resources import CouchResourceMixin, HqBaseResource
from corehq.apps.api.resources.auth import RequirePermissionAuthentication
from corehq.apps.api.resources.meta import CustomResourceMeta
from corehq.apps.api.util import get_object_or_not_exist
from corehq.apps.fixtures.models import (
    FixtureDataItem,
    FixtureDataType,
    FixtureTypeField,
)
from corehq.apps.users.models import Permissions


def convert_fdt(fdi):
    try:
        fdt = FixtureDataType.get(fdi.data_type_id)
        fdi.fixture_type = fdt.tag
        return fdi
    except ResourceNotFound:
        return fdi


class FixtureResource(CouchResourceMixin, HqBaseResource):
    type = "fixture"
    fields = tp_f.DictField(attribute='try_fields_without_attributes',
                            readonly=True, unique=True)
    # when null, that means the ref'd fixture type was not found
    fixture_type = tp_f.CharField(attribute='fixture_type', readonly=True,
                                  null=True)
    id = tp_f.CharField(attribute='_id', readonly=True, unique=True)

    def obj_get(self, bundle, **kwargs):
        return convert_fdt(get_object_or_not_exist(
            FixtureDataItem, kwargs['pk'], kwargs['domain']))

    def obj_get_list(self, bundle, **kwargs):
        domain = kwargs['domain']
        parent_id = bundle.request.GET.get("parent_id", None)
        parent_ref_name = bundle.request.GET.get("parent_ref_name", None)
        references = bundle.request.GET.get("references", None)
        child_type = bundle.request.GET.get("child_type", None)
        type_id = bundle.request.GET.get("fixture_type_id", None)
        type_tag = bundle.request.GET.get("fixture_type", None)

        if parent_id and parent_ref_name and child_type and references:
            parent_fdi = FixtureDataItem.get(parent_id)
            fdis = list(
                FixtureDataItem.by_field_value(
                    domain, child_type, parent_ref_name,
                    parent_fdi.fields_without_attributes[references])
            )
        elif type_id or type_tag:
            type_id = type_id or FixtureDataType.by_domain_tag(
                domain, type_tag).one()
            fdis = list(FixtureDataItem.by_data_type(domain, type_id))
        else:
            fdis = list(FixtureDataItem.by_domain(domain))

        return [convert_fdt(fdi) for fdi in fdis] or []

    class Meta(CustomResourceMeta):
        authentication = RequirePermissionAuthentication(Permissions.edit_apps)
        object_class = FixtureDataItem
        resource_name = 'fixture'
        limit = 0


class InternalFixtureResource(FixtureResource):

    # using the default resource dispatch function to bypass our authorization for internal use
    def dispatch(self, request_type, request, **kwargs):
        return Resource.dispatch(self, request_type, request, **kwargs)

    class Meta(CustomResourceMeta):
        authentication = RequirePermissionAuthentication(Permissions.edit_apps, allow_session_auth=True)
        object_class = FixtureDataItem
        resource_name = 'fixture_internal'
        limit = 0


class LookupTableResource(CouchResourceMixin, HqBaseResource):
    id = tp_f.CharField(attribute='get_id', readonly=True, unique=True)
    is_global = tp_f.BooleanField(attribute='is_global')
    tag = tp_f.CharField(attribute='tag')
    fields = tp_f.ListField(attribute='fields')

    # Intentionally leaving out item_attributes until I can figure out what they are
    # item_attributes = tp_f.ListField(attribute='item_attributes')

    def dehydrate_fields(self, bundle):
        return [
            {
                'field_name': field.field_name,
                'properties': field.properties,
            }
            for field in bundle.obj.fields
        ]

    def obj_get(self, bundle, **kwargs):
        return get_object_or_not_exist(FixtureDataType, kwargs['pk'], kwargs['domain'])

    def obj_get_list(self, bundle, domain, **kwargs):
        return list(FixtureDataType.by_domain(domain))

    def obj_delete(self, bundle, **kwargs):
        data_type = FixtureDataType.get(kwargs['pk'])
        with CouchTransaction() as transaction:
            data_type.recursive_delete(transaction)
        return ImmediateHttpResponse(response=HttpAccepted())

    def obj_create(self, bundle, request=None, **kwargs):
        if FixtureDataType.by_domain_tag(kwargs['domain'], bundle.data.get("tag")):
            raise AssertionError("A lookup table with name %s already exists" % bundle.data.get("tag"))

        bundle.obj = FixtureDataType(bundle.data)
        bundle.obj.domain = kwargs['domain']
        bundle.obj.save()
        return bundle

    def obj_update(self, bundle, **kwargs):
        if 'tag' not in bundle.data:
            raise BadRequest("tag must be specified")

        try:
            bundle.obj = FixtureDataType.get(kwargs['pk'])
        except ResourceNotFound:
            raise NotFound('Lookup table not found')

        if bundle.obj.domain != kwargs['domain']:
            raise NotFound('Lookup table not found')

        if bundle.obj.tag != bundle.data['tag']:
            raise BadRequest("Lookup table tag cannot be changed")

        save = False
        if 'is_global' in bundle.data:
            save = True
            bundle.obj.is_global = bundle.data['is_global']

        if 'fields' in bundle.data:
            save = True
            bundle.obj.fields = [
                FixtureTypeField.wrap(field)
                for field in bundle.data['fields']
            ]

        if save:
            bundle.obj.save()
        return bundle

    class Meta(CustomResourceMeta):
        object_class = FixtureDataType
        detail_allowed_methods = ['get', 'put', 'delete']
        list_allowed_methods = ['get', 'post']
        resource_name = 'lookup_table'
