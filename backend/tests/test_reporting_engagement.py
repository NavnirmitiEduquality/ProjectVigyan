from datetime import date

from app.services.reporting.common import ReportingFilters
from app.services.reporting.engagement import get_engagement_report
from tests.test_reporting_domains import domain_fixture


def test_engagement_average_excludes_missing_scores(domain_fixture):
    item = get_engagement_report(
        domain_fixture["db"],
        ReportingFilters(
            authorized_school_ids=None,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        ),
    )["items"][0]
    assert item["scored_session_count"] == 3
    assert item["missing_engagement_count"] == 3
    assert item["average_engagement"] == 6.0
