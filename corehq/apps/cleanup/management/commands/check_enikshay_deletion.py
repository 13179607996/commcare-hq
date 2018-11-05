from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import itertools

from django.core.management import BaseCommand

from corehq.apps.domain.models import Domain
from corehq.apps.es import AppES, CaseES, CaseSearchES, DomainES, FormES, GroupES, LedgerES, UserES
from corehq.form_processor.backends.sql.dbaccessors import CaseAccessorSQL, doc_type_to_state, FormAccessorSQL
from corehq.form_processor.interfaces.dbaccessors import CaseAccessors, FormAccessors

DOMAINS_IN_SETTINGS = (
    'enikshay-test',
    'enikshay',
    'enikshay-test-2',
    'enikshay-test-3',
    'enikshay-nikshay-migration-test',
    'enikshay-domain-copy-test',
    'enikshay-aks-audit',
    'np-migration-3',
    'enikshay-uatbc-migration-test-1',
    'enikshay-uatbc-migration-test-2',
    'enikshay-uatbc-migration-test-3',
    'enikshay-uatbc-migration-test-4',
    'enikshay-uatbc-migration-test-5',
    'enikshay-uatbc-migration-test-6',
    'enikshay-uatbc-migration-test-7',
    'enikshay-uatbc-migration-test-8',
    'enikshay-uatbc-migration-test-9',
    'enikshay-uatbc-migration-test-10',
    'enikshay-uatbc-migration-test-11',
    'enikshay-uatbc-migration-test-12',
    'enikshay-uatbc-migration-test-13',
    'enikshay-uatbc-migration-test-14',
    'enikshay-uatbc-migration-test-15',
    'enikshay-uatbc-migration-test-16',
    'enikshay-uatbc-migration-test-17',
    'enikshay-uatbc-migration-test-18',
    'enikshay-uatbc-migration-test-19',
    'sheel-enikshay',
    'enikshay-reports-qa',
    'enikshay-performance-test',
)

DOMAINS_FROM_SOFTLAYER = (
    'cz-migration-1',
    'cz-migration-2',
    'cz-migration-3',
    'migration-01-05',
    'migration-1-2',
    'nikshay-speedup',
    'nikshay-speedup-2',
    'np-migration-1',
    'np-migration-1-22',
    'np-migration-1-22-full',
    'np-migration-10',
    'np-migration-12-26',
    'np-migration-12-26-2',
    'np-migration-12-26-3',
    'np-migration-12_24.2',
    'np-migration-2',
    'np-migration-2-7-1',
    'np-migration-4',
    'np-migration-5',
    'np-migration-6',
    'np-migration-7',
    'np-migration-8',
    'np-migration-9',
    'np-migration-no-tests',
    'np-migration-np-tests',
    'np-no-dirtiness',
    'np-test-migration-03-10',
    'enikshay-drtb-migration',
    'derek-enikshay',
    'enikshay-test-migration-test',
    'enikshay-test-test',
)

DOMAINS_FROM_STAGING = (
    'np-migration3',
)

DOMAINS = sorted(DOMAINS_IN_SETTINGS + DOMAINS_FROM_SOFTLAYER + DOMAINS_FROM_STAGING)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            default=False,
            help='Run all checks for each domain, instead of short-circuiting.',
        ),

    def handle(self, all=False, **options):
        domains = list(DOMAINS)

        for domain_name in Domain.get_all_names():
            if 'uatbc' in domain_name or 'nikshay' in domain_name:
                if domain_name not in domains:
                    domains.append(domain_name)

        for domain_name in domains:
            checks = (check(domain_name) for check in [
                _check_domain_exists,
                _check_cases,
                _check_soft_deleted_sql_cases,
                _check_forms,
                _check_soft_deleted_sql_forms,
                _check_elasticsearch,
            ])
            if all:
                checks = list(checks)

            if not any(checks):
                print('No remaining data for domain "%s"' % domain_name)


def _check_domain_exists(domain_name):
    domain = Domain.get_by_name(domain_name)
    if domain:
        print('Domain "%s" still exists. Creator: %s' % (domain_name, domain.creating_user))
        return True


def _check_cases(domain_name):
    case_accessor = CaseAccessors(domain_name)
    case_ids = case_accessor.get_case_ids_in_domain()
    if case_ids:
        print('Domain "%s" contains %s cases.' % (domain_name, len(case_ids)))
        return True


def _check_soft_deleted_sql_cases(domain_name):
    soft_deleted_case_ids = CaseAccessorSQL.get_deleted_case_ids_in_domain(domain_name)
    if soft_deleted_case_ids:
        print('Domain "%s" contains %s soft-deleted SQL cases.' % (domain_name, len(soft_deleted_case_ids)))
        return True


def _check_forms(domain_name):
    form_accessor = FormAccessors(domain_name)
    form_ids = list(itertools.chain(*[
        form_accessor.get_all_form_ids_in_domain(doc_type=doc_type)
        for doc_type in doc_type_to_state
    ]))
    if form_ids:
        print('Domain "%s" contains %s forms.' % (domain_name, len(form_ids)))
        return True


def _check_soft_deleted_sql_forms(domain_name):
    soft_deleted_form_ids = FormAccessorSQL.get_deleted_form_ids_in_domain(domain_name)
    if soft_deleted_form_ids:
        print('Domain "%s" contains %s soft-deleted SQL forms.' % (domain_name, len(soft_deleted_form_ids)))
        return True


def _check_elasticsearch(domain_name):
    def _check_index(hqESQuery):
        if hqESQuery().domain(domain_name).count() != 0:
            print('Domain "%s" contains data in ES index "%s"' % (domain_name, hqESQuery.index))
            return True

    return any(_check_index(hqESQuery) for hqESQuery in [
        AppES, CaseES, CaseSearchES, DomainES, FormES, GroupES, LedgerES, UserES
    ])
