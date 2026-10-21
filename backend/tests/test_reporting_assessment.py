from tests.test_reporting_domains import domain_fixture
from datetime import date

from app.models import (
    Assessment,
    AssessmentImport,
    AssessmentImportRow,
    AssessmentResult,
    User,
    AssessmentClassDivision,
)
from app.services.reporting.assessment import (
    get_assessment_report,
    get_longitudinal_report,
)

def test_assessment_baseline_endline_uses_matched_students(domain_fixture):
    fixture = domain_fixture
    report = get_longitudinal_report(
        fixture["db"],
        fixture["assessments"][1].id,
        None,
    )
    assert report["matched_students"] == 2
    assert report["baseline_only_students"] == 0
    assert report["endline_only_students"] == 0
    assert report["average_percentage_point_change"] == 14.0

def test_assessment_longitudinal_surfaces_multiple_midlines(domain_fixture):
    fixture = domain_fixture
    db = fixture["db"]
    baseline = fixture["assessments"][0]
    endline = fixture["assessments"][1]

    midline_one = Assessment(
        academic_year_id=baseline.academic_year_id,
        school_id=baseline.school_id,
        assessment_type="MIDLINE",
        sequence_no=1,
        name="Reporting Midline 1",
        assessment_date=date(2026, 9, 10),
        maximum_marks=25,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    midline_two = Assessment(
        academic_year_id=baseline.academic_year_id,
        school_id=baseline.school_id,
        assessment_type="MIDLINE",
        sequence_no=2,
        name="Reporting Midline 2",
        assessment_date=date(2026, 12, 10),
        maximum_marks=30,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )

    db.add_all([midline_one, midline_two])
    db.flush()

    students = [
        fixture["student_one"],
        db.query(type(fixture["student_one"]))
        .filter(
            type(fixture["student_one"]).class_division_id
            == fixture["division_one"].id
        )
        .filter(
            type(fixture["student_one"]).id
            != fixture["student_one"].id
        )
        .order_by(type(fixture["student_one"]).roll_no)
        .first(),
    ]

    db.add_all(
        [
            AssessmentResult(
                assessment_id=midline_one.id,
                student_id=students[0].id,
                student_business_id=students[0].student_code,
                aggregate_marks=15,
            ),
            AssessmentResult(
                assessment_id=midline_one.id,
                student_id=students[1].id,
                student_business_id=students[1].student_code,
                aggregate_marks=20,
            ),
            AssessmentResult(
                assessment_id=midline_two.id,
                student_id=students[0].id,
                student_business_id=students[0].student_code,
                aggregate_marks=24,
            ),
        ]
    )
    db.flush()

    try:
        report = get_longitudinal_report(
            db,
            endline.id,
            None,
        )

        assert report["baseline_assessment_id"] == baseline.id
        assert report["endline_assessment_id"] == endline.id

        midlines = report["midline_assessments"]

        assert len(midlines) == 2
        assert [item["sequence_no"] for item in midlines] == [1, 2]
        assert [item["name"] for item in midlines] == [
            "Reporting Midline 1",
            "Reporting Midline 2",
        ]

        assert midlines[0]["assessment_id"] == midline_one.id
        assert midlines[1]["assessment_id"] == midline_two.id
        assert midlines[0]["valid_submitted_results"] == 2
        assert midlines[0]["average_marks"] == 17.5
        assert midlines[0]["average_percentage"] == 70.0

        assert midlines[1]["valid_submitted_results"] == 1
        assert midlines[1]["average_marks"] == 24.0
        assert midlines[1]["average_percentage"] == 80.0

        # Existing Baseline → Endline longitudinal calculation is unchanged.
        assert report["matched_students"] == 2
        assert report["average_baseline_percentage"] == 56.0
        assert report["average_endline_percentage"] == 70.0
        assert report["average_percentage_point_change"] == 14.0
    finally:
        db.rollback()


def test_assessment_report_reports_latest_import_data_quality(domain_fixture):
    fixture = domain_fixture
    db = fixture["db"]

    assessment = fixture["assessments"][0]

    para_teacher = (
        db.query(User).filter(User.user_code.like("RP-PT-%")).one()
    )

    assessment_import = AssessmentImport(
        assessment_id=assessment.id,
        created_by_user_id=para_teacher.id,
        status="SUBMITTED",
        total_rows=4,
    )
    db.add(assessment_import)
    db.flush()

    missing_row = AssessmentImportRow(
        assessment_import_id=assessment_import.id,
        row_number=1,
        student_business_id="MISSING001",
        source_student_name="Missing Student",
        aggregate_marks=None,
        validation_status="WARNING",
        validation_message="Student is missing from the import.",
        is_mapped=False,
        warning_acknowledged=False,
    )

    unmatched_row = AssessmentImportRow(
        assessment_import_id=assessment_import.id,
        row_number=2,
        student_business_id="UNKNOWN001",
        source_student_name="Unknown Student",
        aggregate_marks=20,
        validation_status="WARNING",
        validation_message=(
            "Student could not be matched; manual mapping is required."
        ),
        is_mapped=False,
        warning_acknowledged=False,
    )

    error_row = AssessmentImportRow(
        assessment_import_id=assessment_import.id,
        row_number=3,
        student_business_id="ERROR001",
        source_student_name="Error Student",
        aggregate_marks=None,
        validation_status="ERROR",
        validation_message="Duplicate student business ID.",
        is_mapped=False,
        warning_acknowledged=False,
    )

    mapped_row = AssessmentImportRow(
        assessment_import_id=assessment_import.id,
        row_number=4,
        student_business_id=fixture["student_one"].student_code,
        source_student_name=fixture["student_one"].full_name,
        aggregate_marks=10,
        student_id=fixture["student_one"].id,
        class_division_id=fixture["division_one"].id,
        validation_status="MAPPED",
        validation_message=None,
        is_mapped=True,
        warning_acknowledged=True,
    )

    db.add_all(
        [
            missing_row,
            unmatched_row,
            error_row,
            mapped_row,
        ]
    )
    db.flush()

    report = get_assessment_report(
        db,
        assessment.id,
        [fixture["school_one"].id],
    )

    assert report["imported_rows"] == 4
    assert report["mapped_rows"] == 1
    assert report["valid_submitted_results"] == 2

    assert report["warning_rows"] == 2
    assert report["error_rows"] == 1
    assert report["unresolved_warning_rows"] == 2

    assert report["missing_import_students"] == 1
    assert report["unmatched_student_rows"] == 1

    assert report["eligible_students"] is None
    assert report["missing_students"] is None
    assert report["participation_percentage"] is None

    assert "unmatched_rows" not in report

def test_assessment_endpoint_allows_authorized_school(
    domain_fixture,
):
    from fastapi.testclient import TestClient
    from app.main import app

    fixture = domain_fixture
    client = TestClient(app)
    response = client.get(
        f"/api/v1/reporting/assessments/{fixture['assessments'][0].id}",
        headers={
            "Authorization": f"Bearer {fixture['viewer_token']}",
        },
    )

    assert response.status_code == 200


def test_assessment_endpoint_blocks_other_school(
    domain_fixture,
):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import Assessment

    fixture = domain_fixture
    db = fixture["db"]

    other_assessment = Assessment(
        academic_year_id=fixture["year"].id,
        school_id=fixture["school_two"].id,
        assessment_type="BASELINE",
        sequence_no=1,
        name="Other School Reporting Baseline",
        assessment_date=date(2026, 6, 10),
        maximum_marks=25,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    db.add(other_assessment)
    db.commit()

    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/reporting/assessments/{other_assessment.id}",
            headers={
                "Authorization": f"Bearer {fixture['viewer_token']}",
            },
        )

        assert response.status_code == 404
    finally:
        db.delete(other_assessment)
        db.commit()


def test_longitudinal_endpoint_blocks_other_school(
    domain_fixture,
):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import Assessment

    fixture = domain_fixture
    db = fixture["db"]

    other_assessment = Assessment(
        academic_year_id=fixture["year"].id,
        school_id=fixture["school_two"].id,
        assessment_type="ENDLINE",
        sequence_no=1,
        name="Other School Reporting Endline",
        assessment_date=date(2027, 2, 10),
        maximum_marks=25,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    db.add(other_assessment)
    db.commit()

    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/reporting/assessments/{other_assessment.id}/longitudinal",
            headers={
                "Authorization": f"Bearer {fixture['viewer_token']}",
            },
        )

        assert response.status_code == 404
    finally:
        db.delete(other_assessment)
        db.commit()

def test_assessment_report_calculates_participation_from_saved_scope(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]
    assessment = fixture["assessments"][0]
    division = fixture["division_one"]

    db.add(
        AssessmentClassDivision(
            assessment_id=assessment.id,
            class_division_id=division.id,
        )
    )
    db.flush()

    report = get_assessment_report(
        db,
        assessment.id,
        [fixture["school_one"].id],
    )

    assert report["eligible_students"] == 2
    assert report["missing_students"] == 0
    assert report["participation_percentage"] == 100.0