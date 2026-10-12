from datetime import date

import pytest

from app.services.reporting.common import ReportingFilters
from app.services.reporting.tlm import get_tlm_report
from tests.test_reporting_domains import domain_fixture


def test_tlm_coverage_and_completeness_are_session_weighted(domain_fixture):
    item = get_tlm_report(
        domain_fixture["db"],
        ReportingFilters(
            authorized_school_ids=None,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        ),
    )["items"][0]
    assert item["eligible_sessions"] == 6
    assert item["sessions_with_tlm"] == 1
    assert item["explicit_na_sessions"] == 1
    assert item["missing_tlm_sessions"] == 4
    assert item["usage_coverage_percentage"] == pytest.approx(16.67, abs=0.01)
    assert item["recording_completeness_percentage"] == pytest.approx(33.33, abs=0.01)
