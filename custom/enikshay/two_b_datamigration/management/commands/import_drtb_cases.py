import logging

from dateutil.parser import parse
from django.core.management import (
    BaseCommand,
)

from corehq.util.workbook_reading import open_any_workbook

logger = logging.getLogger('tow_b_datamigration')


# Map format is: MDR selection criteria value -> (rft_drtb_diagnosis value, rft_drtb_diagnosis_ext_dst value)
# TODO: Fill in these Nones
SELECTION_CRITERIA_MAP = {
    "MDR sus -Pre.Treat At diagnosis(Smear+ve/-ve)": ("mdr_at_diagnosis", None),
    "EP Presumptive": (None, None),
    "MDR sus -Follow up Sm+ve": ("follow_up_sm_ve_ip", None),
    "MDR sus -Contact of MDR/RR TB": ("contact_of_mdr_rr", None),
    "MDR sus -New At diagnosis(Smear+ve/-ve)": ("mdr_at_diagnosis", None),
    "Pre XDR-MDR/RR TB at Diagnosis": ("extended_dst", "mdr_rr_diagnosis"),
    "Other": (None, None),
    "Pre XDR >4 months culture positive": ("extended_dst", None),
    "Pre XDR -Failure of MDR/RR-TB regimen": ("extended_dst", "mdr_rr_failure"),
    "MDR sus-Private Referral": ("private_referral", None),
    "MDR sus -NSP/NSN At diagnosis": (None, None),
    "PLHIV Presumptive": (None, None),
    "Pre XDR -Recurrent case of second line treatment": ("extended_dst", "recurrent_second_line_treatment"),
    "Pre XDR -Culture reversion": ("extended_dst", "culture_reversion"),
    "Paediatric Presumptive": (None, None),
    "HIV -EP TB": (None, None),
    "HIV TB (Smear+ve)": (None, None),
    "HIV TB (Smear+ve at diagnosis)": (None, None),
}


def get_case_structures_from_row(row):
    person_case_properties = get_person_case_properties(row)
    occurrence_case_properties = get_occurrence_case_properties(row)
    episode_case_properties = get_episode_case_properties(row)
    test_case_properties = get_test_case_properties(row)
    drug_resistance_case_properties = get_drug_resistance_case_properties(row)
    # TODO: Add a get_followup_test_case_properties(row) function that returns one dict per followup
    # TODO: Create drug resistance cases!
    # TODO: convert all these case properties to the appropriate linked up case structures


def get_person_case_properties(row):
    person_name = Mehsana2016ColumnMapping.get_value("person_name", row)
    xlsx_district_name = Mehsana2016ColumnMapping.get_value("district_name", row)
    district_name, district_id = match_district(xlsx_district_name)
    properties = {
        # TODO: Do they want first_name or last_name?
        "name": person_name,  # TODO: Should this be `name` or `case_name`?
        "district_name": district_name,
        "district_id": district_id,
        "owner_id": "-",
        "current_episode_type": "confirmed_drtb"
    }
    return properties


def get_occurrence_case_properties(row):
    return {
        "current_episode_type": "confirmed_drtb"
    }


def get_episode_case_properties(row):

    report_sending_date = Mehsana2016ColumnMapping.get_value("report_sending_date", row)
    report_sending_date = clean_date(report_sending_date)

    treatment_initiation_date = Mehsana2016ColumnMapping.get_value("treatment_initiation_date", row)
    treatment_initiation_date = clean_date(treatment_initiation_date)

    treatment_card_completed_date = Mehsana2016ColumnMapping.get_value("registration_date", row)
    treatment_card_completed_date = clean_date(treatment_card_completed_date)

    properties = {
        "episode_type": "confirmed_drtb",
        "episode_pending_registration": "no",
        "is_active": "yes",
        "date_of_diagnosis": report_sending_date,
        "diagnosis_test_result_date": report_sending_date,
        "treatment_initiation_date": treatment_initiation_date,
        "treatment_card_completed_date": treatment_card_completed_date,
        "episode_regimen_change_history": get_episode_regimen_change_history(row, treatment_initiation_date)
    }
    properties.update(get_selection_criteria_properties(row))
    if treatment_initiation_date:
        properties["treatment_initiated"] = "yes_phi"

    return properties


def get_selection_criteria_properties(row):
    selection_criteria_value = Mehsana2016ColumnMapping.get_value("mdr_selection_criteria", row)
    rft_drtb_diagnosis, rft_drtb_diagnosis_ext_dst = SELECTION_CRITERIA_MAP[selection_criteria_value]

    properties = {
        "rft_general": "drtb_diagnosis",  # TODO: Should this only be included in some instances?
    }
    if rft_drtb_diagnosis:
        properties["rft_drtb_diagnosis"] = rft_drtb_diagnosis
    if rft_drtb_diagnosis_ext_dst:
        properties["rft_drtb_diagnosis_ext_dst"] = rft_drtb_diagnosis_ext_dst
    return properties


def get_resistance_properties(row):
    property_map = {
        "Rif-Resi": ("r", "R: Res"),
        "Rif Resi+Levo Resi": ("r lfx", "R: Res\nLFX: Res"),
        "Rif Resi+Levo Resi+K Resi": ("r lfx km", "R: Res\nLFX: Res\nKM: Res"),
        "Rif Resi+K Resi": ("r km", "R: Res\nKM: Res"),
    }
    dst_result_value = Mehsana2016ColumnMapping.get_value("dst_result", row)
    if dst_result_value:
        return {
            "drug_resistance_list": property_map[dst_result_value][0],
            "result_summary_display": property_map[dst_result_value][1]
        }
    else:
        return {}


def get_episode_regimen_change_history(row, episode_treatment_initiation_date):
    put_on_treatment = Mehsana2016ColumnMapping.get_value("date_put_on_mdr_treatment", row)
    put_on_treatment = clean_date(put_on_treatment)
    value = "{}: MDR/RR".format(episode_treatment_initiation_date)
    if put_on_treatment:
        value += "\n{}: {}".format(
            put_on_treatment,
            Mehsana2016ColumnMapping.get_value("type_of_treatment_initiated", row)
        )
    return value


def get_test_case_properties(row):
    facility_name, facility_id = match_facility(Mehsana2016ColumnMapping.get_value("testing_facility", row))
    properties = {
        "testing_facility_saved_name": facility_name,
        "testing_facility_id": facility_id,
        "date_reported": Mehsana2016ColumnMapping.get_value("report_sending_date", row),
    }
    properties.update(get_selection_criteria_properties(row))
    properties.update(get_resistance_properties(row))
    return properties


def get_drug_resistance_case_properties(row):
    resistant_drugs = get_drug_resistances(row)
    case_properties = []
    for drug in resistant_drugs:
        properties = {
            "name": drug,  # TODO: case_name?
            "owner_id": "-",
            "sensitivity": "resistant",
            "drug_id": drug,
        }
        case_properties.append(properties)
    return case_properties


def get_drug_resistances(row):
    drugs = get_resistance_properties(row).get("drug_resistance_list", "").split(" ")
    return drugs

def clean_date(messy_date_string):
    if messy_date_string:
        # TODO: Might be safer to assume a format and raise an exception if its in a different format
        # parse("") returns today, which we don't want.
        cleaned_datetime = parse(messy_date_string)
        return cleaned_datetime.date()


def match_district(xlsx_district_name):
    """
    Given district name taken from the spreadsheet, return the id name and id of the matching location in HQ.
    """
    # TODO: Query the locations
    pass

def match_facility(xlsx_facility_name):
    """
    Given facility name taken from the spreadsheet, return the id name and id of the matching location in HQ.
    """
    # TODO: This might be the same as match_district()
    # TODO: Query the locations
    pass


class ColumnMapping(object):
    pass


mehsana_2016_mapping = {
    "person_name": 3,
    "district_name": 5,
    "report_sending_date": 7,
    "treatment_initiation_date": 12,
    "registration_date": 13,
    "date_put_on_mdr_treatment": 19,
    "type_of_treatment_initiated": 47,
    "mdr_selection_criteria": 4,
    "testing_facility": 1,
    "dst_result": 6,
}


class Mehsana2016ColumnMapping(ColumnMapping):

    @staticmethod
    def get_value(normalized_column_name, row):
        # TODO: Confirm what this returns if cell is empty (we probably don't want None, do want "")
        column_index = mehsana_2016_mapping[normalized_column_name]
        return row[column_index]


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('domain')
        parser.add_argument('excel_file_path')

    def handle(self, domain, excel_file_path, **options):

        with open_any_workbook(excel_file_path) as workbook:
            for row in workbook.worksheets[0].iter_rows():
                case_structures = get_case_structures_from_row(row)
                # TODO: submit forms with case structures
