"""
A quick and dirty script to dump IDs for forms, visits, and child cases as CSV

Recommended usage:
    $ ./manage.py export_visit_child | gzip > export_visit_child.csv.gz

"""
import sys

from django.core.management import BaseCommand

from casexml.apps.case.models import CommCareCase
from couchforms.dbaccessors import get_forms_by_id, iter_form_ids_by_xmlns
from dimagi.utils.chunked import chunked

from custom.rec.collections import dicts_or

DOMAIN = "rec"
CLASSIFICATION_FORMS = {
    "http://openrosa.org/formdesigner/36862832d549d2018b520362b307ec9d52712c1e": "Newborn Classification",
    "http://openrosa.org/formdesigner/bae8adfcd6dd54cf9512856c095ef7155fd64b1e": "Infant Classification",
    "http://openrosa.org/formdesigner/2f934e7b72944d72fd925e870030ecdc2e5e2ea6": "Child Classification",
}
TREATMENT_FORMS = {
    "http://openrosa.org/formdesigner/208ea1a776585606b3c57d958c00d2aa538436ba": "Newborn Treatment",
    "http://openrosa.org/formdesigner/2363c4595259f41930352fe574bc55ffd8f7fe22": "Infant Treatment",
    "http://openrosa.org/formdesigner/8a439e01cccb27cd0097f309bef1633263c20275": "Child Treatment",
}
ENROLLMENT_FORM = {
    "http://openrosa.org/formdesigner/10753F54-3ABA-45BA-B2B4-3AFE7F558682": "Child Enrollment",
}
PRESCRIPTION_FORM = {
    "http://openrosa.org/formdesigner/796C928A-7451-486B-8346-3316DB3816E4": "Prescription/Ordonnance",
},
FORMS_XMLNS = dicts_or(
    CLASSIFICATION_FORMS,
    TREATMENT_FORMS,
    ENROLLMENT_FORM,
    PRESCRIPTION_FORM,
)


class Command(BaseCommand):
    help = 'Dump IDs for forms, visits, and child cases as CSV'

    def handle(self, *args, **options):
        main()


def main():
    header = ("form_id", "xmlns", "imci_visit_id", "rec_child_id", "created_at")
    print(",".join(header))
    for xmlns, form_name in FORMS_XMLNS.items():
        print(f'Processing "{form_name}" form.', file=sys.stderr)
        form_ids = iter_form_ids_by_xmlns(DOMAIN, xmlns)
        for form_ids_chunk in chunked(form_ids, 500):
            couch_forms = get_forms_by_id(form_ids_chunk)
            visit_id_to_child_id, visit_ids_missing_child_ids = map_visit_to_child_from_forms(couch_forms, xmlns)
            visit_id_to_child_id.update(
                map_visit_to_child_from_visit_cases(visit_ids_missing_child_ids)
            )
            for couch_form in couch_forms:
                imci_visit_id = get_imci_visit_id(couch_form.form, xmlns)
                row = (
                    couch_form.form_id,
                    xmlns,
                    imci_visit_id,
                    visit_id_to_child_id[imci_visit_id],
                    couch_form.received_on.isoformat(),
                )
                print(",".join(row))


def get_imci_visit_id(form_json, xmlns):
    if xmlns in CLASSIFICATION_FORMS:
        assert "subcase_0" in form_json, "Form missing visit subcase"
        if form_json["subcase_0"]["case"].get("create"):
            case_type = form_json["subcase_0"]["case"]["create"]["case_type"]
            assert case_type == "imci_visit", "Bad visit case type"
        return form_json["subcase_0"]["case"]["@case_id"]
    elif xmlns in TREATMENT_FORMS:
        return form_json["case_case_visit"]["case"]["@case_id"]
    else:
        raise NotImplementedError


def map_visit_to_child_from_forms(couch_forms, xmlns):
    visit_id_to_child_id = {}
    visit_ids_without_child_ids = set()
    for couch_form in couch_forms:
        visit_id = get_imci_visit_id(couch_form.form, xmlns)
        child_id = get_rec_child_id_from_form(couch_form.form, xmlns)
        if child_id:
            visit_id_to_child_id[visit_id] = child_id
        else:
            visit_ids_without_child_ids.add(visit_id)
    return visit_id_to_child_id, list(visit_ids_without_child_ids)


def get_rec_child_id_from_form(form_json, xmlns):
    if xmlns in CLASSIFICATION_FORMS:
        return form_json["case"]["@case_id"]
    elif xmlns in TREATMENT_FORMS:
        if "case_case_child" in form_json:
            return form_json["case_case_child"]["case"]["@case_id"]
    else:
        raise NotImplementedError


def map_visit_to_child_from_visit_cases(visit_ids):
    visits = CommCareCase.view('_all_docs', keys=visit_ids, include_docs=True)
    return {v.case_id: get_rec_child_id_from_visit(v) for v in visits}


def get_rec_child_id_from_visit(visit_case):
    for index in visit_case.indices:
        if index.identifier == "parent" and index.referenced_type == "rec_child":
            return index.referenced_id
    else:
        message = f"imci_visit {visit_case.case_id!r} missing rec_child index"
        print(message, file=sys.stderr)
        return f"[{message}]"
