from django.core.management.base import BaseCommand, CommandError
from datetime import datetime, timedelta
from corehq.elastic import get_es_new
from elasticsearch.client import SnapshotClient, IndicesClient
from django.conf import settings

class Command(BaseCommand):
    help = ("Restores full ES cluster or specific index from snapshot. "
            "Index arguments are optional and it will default to a full "
            "cluster restore if none are specified")
    args = "days_ago <index_1> <index_2> ..."

    def handle(self, *args, **options):
        print "Restoring ES indices from snapshot"
        if len(args) < 1:
            raise CommandError('Usage is restore_es_snapshot %s' % self.args)
        date = self.get_date(args)
        indices = self.get_indices(args)
        es = get_es_new()
        client = self.get_client_and_close_indices(es, indices)
        self.restore_snapshot(es, date, indices)
        client.open(indices)

    @staticmethod
    def get_date(args):
        days_ago = int(args[0])
        restore_date = (datetime.utcnow() - timedelta(days=days_ago))
        return restore_date

    @staticmethod
    def get_indices(args):
        if len(args) > 1:
            indices = ','.join(args[1:])
        else:
            indices = '_all'
        return indices

    @staticmethod
    def get_client_and_close_indices(es, indices):
        indices_client = IndicesClient(es)
        indices_client.close(indices)
        return indices_client

    @staticmethod
    def restore_snapshot(es, date, indices):
        snapshot_client = SnapshotClient(es)
        env = settings.SERVER_ENVIRONMENT
        repo_name = '{}_es_snapshot'.format(env)
        snapshot_client.restore(repo_name,
                                '{repo_name}_{year}_{month}_{day}'.format(
                                    repo_name=repo_name, year=date.year,
                                    month=date.month, day=date.day
                                ),
                                body={'indices': indices}
        )
