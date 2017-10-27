import csv

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from auditcare.utils.export import write_log_events
from corehq.apps.domain.models import Domain
from corehq.apps.users.models import WebUser


class Command(BaseCommand):
    help = """Generate request report"""

    def add_arguments(self, parser):
        parser.add_argument('filename')
        parser.add_argument(
            '--domain',
            help="Limit logs to only this domain"
        )
        parser.add_argument(
            '--user',
            help="Limit logs to only this user"
        )
        parser.add_argument(
            '--display-superuser',
            action='store_true',
            dest='display_superuser',
            default=False,
            help="Include superusers in report, otherwise 'Dimagi User'",
        )

    def handle(self, filename, **options):
        domain = options["domain"]
        user = options["user"]
        display_superuser = options["display_superuser"]

        dimagi_username = ""
        if not display_superuser:
            dimagi_username = "Dimagi Support"

        if not domain and not user:
            raise CommandError("Please provide one of 'domain' or 'user'")

        if user:
            users = [user]
            super_users = []
        else:
            domain_object = Domain.get_by_name(domain)
            if not domain_object:
                raise CommandError("Domain not found")

            users = {u.username for u in WebUser.by_domain(domain)}
            super_users = {u['username'] for u in User.objects.filter(is_superuser=True).values('username')}
            super_users = super_users - users

        with open(filename, 'wb') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Date', 'User', 'Domain', 'IP Address', 'Request Path'])
            for user in users:
                write_log_events(writer, user, domain)

            for user in super_users:
                write_log_events(writer, user, domain, dimagi_username)
