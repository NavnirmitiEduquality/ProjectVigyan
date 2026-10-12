from datetime import date

from app.services.reporting.common import ReportingFilters
from app.services.reporting.delivery import get_delivery_report
from tests.test_reporting_domains import domain_fixture


def test_delivery_hours_and_missing_duration(domain_fixture):
    item = get_delivery_report(
        domain_fixture["db"],
        ReportingFilters(
            authorized_school_ids=None,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        ),
    )["items"][0]
    assert item["completed_duration_minutes"] == 180
    assert item["teaching_hours"] == 3.0
    assert item["completed_sessions_with_duration"] == 3
    assert item["average_completed_duration_minutes"] == 60.0
    assert item["completion_percentage"] is None
