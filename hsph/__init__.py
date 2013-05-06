from hsph.reports import (field_management, call_center, project_management,
    data_summary)
from hsph.reports.old import data_summary as old_data_summary

CUSTOM_REPORTS = (
    ('Field Management Reports', (
        field_management.DCOActivityReport,
        field_management.FieldDataCollectionActivityReport,
        field_management.HVFollowUpStatusReport,
        field_management.HVFollowUpStatusSummaryReport,
        call_center.CaseReport,
        field_management.DCOProcessDataReport
    )),
    ('Project Management Reports', (
        project_management.ProjectStatusDashboardReport,
        project_management.ImplementationStatusDashboardReport
    )),
    ('Call Center Reports', (
        call_center.CATIPerformanceReport,
        call_center.CallCenterFollowUpSummaryReport
    )),
    ('Data Summary Reports', (
        data_summary.PrimaryOutcomeReport,
        data_summary.SecondaryOutcomeReport,
        data_summary.FADAObservationsReport
    )),
    ('Old Reports', (
        old_data_summary.PrimaryOutcomeReport,
        old_data_summary.SecondaryOutcomeReport
    ))
)
