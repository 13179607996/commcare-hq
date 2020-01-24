from corehq.apps.cleanup.management.commands.populate_sql_model_from_couch_model import PopulateSQLCommand

from corehq.apps.app_manager.models import LATEST_APK_VALUE, LATEST_APP_VALUE


class Command(PopulateSQLCommand):
    help = """
        Adds a SQLGlobalAppConfig for any GlobalAppConfig doc that doesn't yet have one.
    """

    @classmethod
    def couch_db_slug(cls):
        return 'apps'

    @classmethod
    def couch_doc_type(cls):
        return 'GlobalAppConfig'

    @classmethod
    def couch_key(cls):
        return set(['domain', 'app_id'])

    @classmethod
    def sql_class(cls):
        from corehq.apps.app_manager.models import SQLGlobalAppConfig
        return SQLGlobalAppConfig

    @classmethod
    def command_name(cls):
        return __name__.split('.')[-1]

    def update_or_create_sql_object(self, doc):
        model, created = self.sql_class().objects.get_or_create(
            domain=doc['domain'],
            app_id=doc['app_id'],
            defaults={
                "apk_prompt": doc['apk_prompt'],
                "app_prompt": doc['app_prompt'],
                "apk_version": doc.get('apk_version', LATEST_APK_VALUE),
                "app_version": doc.get('app_version', LATEST_APP_VALUE),
            })
        return (model, created)
