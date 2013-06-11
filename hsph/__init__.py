from hsph.reports import data_summary, field_management
from hsph.reports.old import (field_management as old_field_management,
        data_summary as old_data_summary, call_center as old_call_center,
        project_management as old_project_management) 

new_reports = (
    ('Field Management', (
        field_management.FIDAPerformanceReport,
        field_management.FacilityRegistrationsReport,
        # Facility-Wise Follow Up
        field_management.CaseReport,
    )),
    ('Call Center', (
        # CATI Performance
        # CATI Team Leaders
    )),
    ('Data Summary', (
        data_summary.PrimaryOutcomeReport,
        data_summary.SecondaryOutcomeReport,
        data_summary.FADAObservationsReport,
    )),
)

old_reports = (
    ('Field Management Reports', (
        old_field_management.DCOActivityReport,
        old_field_management.FieldDataCollectionActivityReport,
        old_field_management.HVFollowUpStatusReport,
        old_field_management.HVFollowUpStatusSummaryReport,
        old_call_center.CaseReport,
        old_field_management.DCOProcessDataReport
    )),
    ('Project Management Reports', (
        old_project_management.ProjectStatusDashboardReport,
        old_project_management.ImplementationStatusDashboardReport
    )),
    ('Call Center Reports', (
        old_call_center.CATIPerformanceReport,
        old_call_center.CallCenterFollowUpSummaryReport
    )),
    ('Data Summary Reports', (
        old_data_summary.PrimaryOutcomeReport,
        old_data_summary.SecondaryOutcomeReport,
    )),
)

CUSTOM_REPORTS = {
    'hsph': old_reports,
    'hsph-dev': new_reports,
    'hsph-betterbirth-pilot-2': new_reports
}
