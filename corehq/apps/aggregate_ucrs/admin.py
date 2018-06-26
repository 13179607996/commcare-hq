from __future__ import absolute_import
from __future__ import unicode_literals
from django.contrib import admin
from . import models


class AggregateTableDefinitionAdmin(admin.ModelAdmin):
    list_display = ['table_id', 'display_name', 'domain', 'date_created', 'date_modified']
    list_filter = ['domain', 'date_created', 'date_modified']


class PrimaryColumnAdmin(admin.ModelAdmin):
    list_display = ['column_id', 'column_type', 'table_definition']
    list_filter = ['column_type', 'table_definition']


admin.site.register(models.AggregateTableDefinition, AggregateTableDefinitionAdmin)
admin.site.register(models.PrimaryColumn, PrimaryColumnAdmin)
admin.site.register(models.SecondaryTableDefinition)
admin.site.register(models.SecondaryColumn)

