from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Assessment
from tests.test_reporting_attendance import _headers
from tests.test_reporting_domains import domain_fixture


client = TestClient(app)


def test_monthly_report_includes_only_assessments_in_selected_month(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]
    baseline = fixture["assessments"][0]

    september = Assessment(
        academic_year_id=baseline.academic_year_id,
        school_id=baseline.school_id,
        assessment_type="MIDLINE",
        sequence_no=1,
        name="September Midline",
        assessment_date=date(2026, 9, 10),
        maximum_marks=25,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    december = Assessment(
        academic_year_id=baseline.academic_year_id,
        school_id=baseline.school_id,
        assessment_type="MIDLINE",
        sequence_no=2,
        name="December Midline",
        assessment_date=date(2026, 12, 10),
        maximum_marks=30,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    db.add_all([september, december])
    db.commit()

    try:
        response = client.get(
            "/api/v1/reporting/monthly-management",
            params={
                "year": 2026,
                "month": 9,
                "academic_year_id": str(baseline.academic_year_id),
            },
            headers=_headers(fixture["viewer_token"]),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["period"]["start_date"] == "2026-09-01"
        assert body["period"]["end_date"] == "2026-09-30"
        assert [
            event["name"] for event in body["assessments"]["events"]
        ] == ["September Midline"]
        assert body["assessments"]["message"] is None
    finally:
        db.query(Assessment).filter(
            Assessment.id.in_([september.id, december.id])
        ).delete(synchronize_session=False)
        db.commit()


def test_monthly_report_returns_exact_message_when_no_assessment_events(
    domain_fixture,
):
    fixture = domain_fixture
    baseline = fixture["assessments"][0]

    response = client.get(
        "/api/v1/reporting/monthly-management",
        params={
            "year": 2026,
            "month": 7,
            "academic_year_id": str(baseline.academic_year_id),
        },
        headers=_headers(fixture["viewer_token"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["assessments"] == {
        "message": "No assessment event in selected period.",
        "events": [],
    }


def test_monthly_report_rejects_month_outside_academic_year(domain_fixture):
    fixture = domain_fixture
    baseline = fixture["assessments"][0]

    response = client.get(
        "/api/v1/reporting/monthly-management",
        params={
            "year": 2027,
            "month": 4,
            "academic_year_id": str(baseline.academic_year_id),
        },
        headers=_headers(fixture["viewer_token"]),
    )

    assert response.status_code == 422


def test_monthly_report_rejects_invalid_month(domain_fixture):
    fixture = domain_fixture
    baseline = fixture["assessments"][0]

    response = client.get(
        "/api/v1/reporting/monthly-management",
        params={
            "year": 2026,
            "month": 13,
            "academic_year_id": str(baseline.academic_year_id),
        },
        headers=_headers(fixture["viewer_token"]),
    )

    assert response.status_code == 422
