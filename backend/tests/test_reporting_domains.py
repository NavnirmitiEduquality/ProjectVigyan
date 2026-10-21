from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import delete
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Assessment,
    AssessmentImport,
    AssessmentImportRow,
    ClassDivision,
    AssessmentResult,
    Photo,
    ClassroomObservation,
    ClassroomObservationReport,
    STEMInspection,
    STEMInspectionReport,
    SessionEngagement,
    SessionEvidence,
    SessionTLM,
    TeachingSession,
    TLM,
    User,
)
from app.models.student import Student
from app.services.reporting.monitoring import (
    get_class_monitoring,
    get_para_teacher_monitoring,
    get_school_monitoring,
    get_student_monitoring,
)
from app.services.reporting.assessment import (
    get_assessment_report,
    get_longitudinal_report,
)
from app.services.reporting.common import ReportingFilters
from app.services.reporting.delivery import (
    get_delivery_report,
    get_delivery_trend,
)
from app.services.reporting.engagement import get_engagement_report
from app.services.reporting.exports import metadata, report_bytes
from app.services.reporting.tlm import get_tlm_report
from app.services.session_tlm.service import NA_TLM_NAME

from tests.test_reporting_attendance import reporting_fixture


@pytest.fixture
def domain_fixture(reporting_fixture):
    fixture = reporting_fixture
    db = fixture["db"]
    para_teacher = (
        db.query(User).filter(User.user_code.like("RP-PT-%")).one()
    )
    para_teacher.data_origin = "PRODUCTION"
    division = fixture["division_one"]
    rows = []
    for session_date, status, duration in (
        (date(2026, 6, 1), "COMPLETED", 60),
        (date(2026, 6, 2), "COMPLETED", 90),
        (date(2026, 6, 3), "COMPLETED", 30),
        (date(2026, 6, 4), "COMPLETED", None),
        (date(2026, 12, 1), "PLANNED", None),
        (date(2026, 6, 5), "IN_PROGRESS", None),
        (date(2026, 6, 6), "CANCELLED", None),
    ):
        session = TeachingSession(
            class_division_id=division.id,
            para_teacher_id=para_teacher.id,
            session_date=session_date,
            status=status,
            duration_minutes=duration,
            data_origin="PRODUCTION",
        )
        db.add(session)
        db.flush()
        rows.append(session)

    db.add_all(
        [
            SessionEngagement(
                teaching_session_id=rows[0].id,
                score=4,
                data_origin="PRODUCTION",
            ),
            SessionEngagement(
                teaching_session_id=rows[1].id,
                score=6,
                data_origin="PRODUCTION",
            ),
            SessionEngagement(
                teaching_session_id=rows[2].id,
                score=8,
                data_origin="PRODUCTION",
            ),
        ]
    )
    normal_tlm = TLM(
        name=f"Reporting TLM {division.id}",
        description="Synthetic reporting TLM",
        is_active=True,
        data_origin="PRODUCTION",
    )
    na_tlm = db.query(TLM).filter(TLM.name == NA_TLM_NAME).one_or_none()
    if na_tlm is None:
        na_tlm = TLM(
            name=NA_TLM_NAME,
            description="Explicit no TLM",
            is_active=True,
            data_origin="PRODUCTION",
        )
        db.add(na_tlm)
    db.add(normal_tlm)
    db.flush()
    db.add_all(
        [
            SessionTLM(
                teaching_session_id=rows[0].id,
                tlm_id=normal_tlm.id,
                quantity=2,
                data_origin="PRODUCTION",
            ),
            SessionTLM(
                teaching_session_id=rows[0].id,
                tlm_id=na_tlm.id,
                quantity=0,
                data_origin="TEST",
            ),
            SessionTLM(
                teaching_session_id=rows[1].id,
                tlm_id=na_tlm.id,
                quantity=0,
                data_origin="PRODUCTION",
            ),
        ]
    )
    baseline = Assessment(
        academic_year_id=fixture["year"].id,
        school_id=fixture["school_one"].id,
        assessment_type="BASELINE",
        sequence_no=1,
        name="Reporting Baseline",
        assessment_date=date(2026, 6, 10),
        maximum_marks=25,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    endline = Assessment(
        academic_year_id=fixture["year"].id,
        school_id=fixture["school_one"].id,
        assessment_type="ENDLINE",
        sequence_no=1,
        name="Reporting Endline",
        assessment_date=date(2027, 2, 10),
        maximum_marks=25,
        status="SUBMITTED",
        data_origin="PRODUCTION",
    )
    db.add_all([baseline, endline])
    db.flush()
    students = (
        db.query(User)
        .filter(User.id == para_teacher.id)
        .one()
    )
    del students
    school_students = [
        fixture["student_one"],
        db.query(type(fixture["student_one"]))
        .filter(type(fixture["student_one"]).class_division_id == division.id)
        .filter(type(fixture["student_one"]).id != fixture["student_one"].id)
        .order_by(type(fixture["student_one"]).roll_no)
        .first(),
    ]
    db.add_all(
        [
            AssessmentResult(
                assessment_id=baseline.id,
                student_id=school_students[0].id,
                student_business_id=school_students[0].student_code,
                aggregate_marks=10,
            ),
            AssessmentResult(
                assessment_id=baseline.id,
                student_id=school_students[1].id,
                student_business_id=school_students[1].student_code,
                aggregate_marks=18,
            ),
            AssessmentResult(
                assessment_id=endline.id,
                student_id=school_students[0].id,
                student_business_id=school_students[0].student_code,
                aggregate_marks=20,
            ),
            AssessmentResult(
                assessment_id=endline.id,
                student_id=school_students[1].id,
                student_business_id=school_students[1].student_code,
                aggregate_marks=15,
            ),
        ]
    )
    db.commit()
    yield {**fixture, "sessions": rows, "normal_tlm": normal_tlm, "assessments": [baseline, endline]}
    db.rollback()
    db.execute(
        delete(SessionEvidence).where(
            SessionEvidence.teaching_session_id.in_([row.id for row in rows])
        )
    )
    db.execute(
        delete(SessionEngagement).where(
            SessionEngagement.teaching_session_id.in_([row.id for row in rows])
        )
    )
    db.execute(
        delete(SessionTLM).where(
            SessionTLM.teaching_session_id.in_([row.id for row in rows])
        )
    )
    db.execute(
        delete(AssessmentResult).where(
            AssessmentResult.assessment_id.in_([baseline.id, endline.id])
        )
    )
    db.execute(delete(Assessment).where(Assessment.id.in_([baseline.id, endline.id])))
    db.delete(normal_tlm)
    db.query(TeachingSession).filter(
        TeachingSession.id.in_([row.id for row in rows])
    ).delete(synchronize_session=False)
    db.commit()


client = TestClient(app)


def test_para_teacher_filter_respects_school_scope(domain_fixture):
    fixture = domain_fixture
    db = fixture["db"]

    own_para_teacher = (
        db.query(User)
        .filter(User.user_code.like("RP-PT-%"))
        .one()
    )

    other_para_teacher = User(
        user_code=f"RP-PT-OTHER-{fixture['school_two'].id.hex[:8]}",
        full_name="Other School Para Teacher",
        email=f"rp-pt-other-{fixture['school_two'].id.hex[:8]}@example.com",
        password_hash=own_para_teacher.password_hash,
        status="ACTIVE",
        data_origin="PRODUCTION",
    )
    db.add(other_para_teacher)
    db.flush()

    other_school_session = TeachingSession(
        class_division_id=fixture["student_other_school"].class_division_id,
        para_teacher_id=other_para_teacher.id,
        session_date=date(2026, 6, 15),
        status="COMPLETED",
        duration_minutes=45,
        data_origin="PRODUCTION",
    )
    db.add(other_school_session)
    db.commit()

    try:
        own_school_response = client.get(
            "/api/v1/reporting/delivery",
            params={"group_by": "para_teacher", "para_teacher_id": str(own_para_teacher.id)},
            headers={
                "Authorization": f"Bearer {fixture['viewer_token']}"
            },
        )

        assert own_school_response.status_code == 200
        assert own_school_response.json()["items"]

        cross_school_response = client.get(
            "/api/v1/reporting/delivery",
            params={"group_by": "para_teacher", "para_teacher_id": str(other_para_teacher.id)},
            headers={
                "Authorization": f"Bearer {fixture['viewer_token']}"
            },
        )

        assert cross_school_response.status_code == 200
        assert cross_school_response.json()["items"] == []

        project_wide_response = client.get(
            "/api/v1/reporting/delivery",
            params={"para_teacher_id": str(other_para_teacher.id)},
            headers={
                "Authorization": f"Bearer {fixture['platform_owner_token']}"
            },
        )

        assert project_wide_response.status_code == 200
        assert project_wide_response.json()["items"]

    finally:
        db.rollback()
        db.delete(other_school_session)
        db.delete(other_para_teacher)
        db.commit()


def test_r2_delivery_metrics_and_groupings(domain_fixture):
    fixture = domain_fixture
    filters = ReportingFilters(
        authorized_school_ids=None,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 6),
    )
    item = get_delivery_report(fixture["db"], filters)["items"][0]
    assert item["planned_sessions"] == 0
    assert item["upcoming_sessions"] == 0
    assert item["in_progress_sessions"] == 1
    assert item["completed_sessions"] == 4
    assert item["cancelled_sessions"] == 1
    assert item["completed_sessions_with_duration"] == 3
    assert item["completed_duration_minutes"] == 180
    assert item["teaching_hours"] == 3.0
    assert item["average_completed_duration_minutes"] == 60.0
    assert item["completion_percentage"] is None
    assert len(get_delivery_report(fixture["db"], filters, group_by="school")["items"]) == 1
    assert get_delivery_report(fixture["db"], filters, group_by="class_division")["items"]
    assert get_delivery_report(fixture["db"], filters, group_by="para_teacher")["items"]


def test_r2_filters_and_monthly_trend(domain_fixture):
    fixture = domain_fixture
    filters = ReportingFilters(
        authorized_school_ids={fixture["school_one"].id},
        academic_year_id=fixture["year"].id,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 6),
        school_id=fixture["school_one"].id,
        class_division_id=fixture["division_one"].id,
    )
    item = get_delivery_report(fixture["db"], filters)["items"][0]
    assert item["total_sessions"] == 6
    trend = get_delivery_trend(fixture["db"], filters)["items"]
    assert len(trend) == 1
    assert trend[0]["completed_sessions"] == 4


def test_r4_engagement_is_session_weighted_and_missing_is_not_zero(domain_fixture):
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
    assert item["distribution"]["4"] == 1
    assert item["distribution"]["6"] == 1
    assert item["distribution"]["8"] == 1


def test_r5_tlm_states_and_formula(domain_fixture):
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
    assert item["sessions_with_tlm"] + item["explicit_na_sessions"] + item["missing_tlm_sessions"] == item["eligible_sessions"]
    assert item["usage_coverage_percentage"] == pytest.approx(100 / 6, abs=0.01)
    assert item["recording_completeness_percentage"] == pytest.approx(200 / 6, abs=0.01)
    assert item["distinct_tlms_used"] == 1


def test_r6_assessment_percentage_and_longitudinal(domain_fixture):
    fixture = domain_fixture
    report = get_assessment_report(
        fixture["db"],
        fixture["assessments"][0].id,
        None,
    )
    assert report["valid_submitted_results"] == 2
    assert report["average_marks"] == Decimal("14")
    assert report["average_percentage"] == 56.0
    assert report["results"][0]["percentage"] in {40.0, 72.0}
    longitudinal = get_longitudinal_report(
        fixture["db"],
        fixture["assessments"][1].id,
        None,
    )
    assert longitudinal["matched_students"] == 2
    assert longitudinal["average_baseline_percentage"] == 56.0
    assert longitudinal["average_endline_percentage"] == 70.0
    assert longitudinal["average_percentage_point_change"] == 14.0


def test_r7_school_monitoring_includes_assessment_evidence_and_para_teacher(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]

    completed_sessions = fixture["sessions"][:4]

    photos = [
        Photo(
            photo_category="SESSION_EVIDENCE",
            storage_key=f"reporting-r7-{session.id}.jpg",
            original_filename="reporting-r7.jpg",
            content_type="image/jpeg",
            file_size_bytes=1024,
            width=100,
            height=100,
            captured_at=session.session_date,
            latitude=Decimal("19.076000"),
            longitude=Decimal("72.877700"),
            data_origin="PRODUCTION",
        )
        for session in completed_sessions[:2]
    ]
    db.add_all(photos)
    db.flush()

    db.add_all(
        [
            SessionEvidence(
                teaching_session_id=session.id,
                photo_id=photo.id,
                data_origin="PRODUCTION",
            )
            for session, photo in zip(completed_sessions[:2], photos)
        ]
    )

    db.commit()

    result = get_school_monitoring(
        db,
        ReportingFilters(
            authorized_school_ids={fixture["school_one"].id},
            academic_year_id=fixture["year"].id,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        ),
    )

    assert result["total_schools"] == 1

    item = result["items"][0]

    assert item["school_id"] == fixture["school_one"].id
    assert item["para_teachers"] == 1

    assert item["evidence"]["eligible_completed_sessions"] == 4
    assert item["evidence"]["sessions_with_evidence"] == 2
    assert item["evidence"]["completeness_percentage"] == 50.0

    assert item["assessment"]["latest"]["assessment_type"] == "ENDLINE"
    assert item["assessment"]["baseline"]["average_percentage"] == 56.0
    assert item["assessment"]["endline"]["average_percentage"] == 70.0

    longitudinal = item["assessment"]["longitudinal"]
    assert longitudinal["matched_students"] == 2
    assert longitudinal["average_percentage_point_change"] == 14.0

    db.rollback()
    db.query(SessionEvidence).filter(
        SessionEvidence.teaching_session_id.in_(
            [session.id for session in completed_sessions[:2]]
        )
    ).delete(synchronize_session=False)
    db.query(Photo).filter(
        Photo.id.in_([photo.id for photo in photos])
    ).delete(synchronize_session=False)
    db.commit()


def test_r7_school_monitoring_includes_observation_report_counts(domain_fixture):
    fixture = domain_fixture
    db = fixture["db"]
    school = fixture["school_one"]
    division = fixture["division_one"]
    observer = (
    db.query(User)
        .filter(User.user_code.like("RP-V-%"))
        .one()
    )
    para_teacher = (
        db.query(User).filter(User.user_code.like("RP-PT-%")).one()
    )

    # Use existing production fixture records, but keep the test data
    # uncommitted so the final rollback removes it.
    photos = [
        Photo(
            photo_category="TLM_ACTIVITY",
            storage_key=f"reporting-observation-{index}-{school.id}.jpg",
            original_filename="observation.jpg",
            content_type="image/jpeg",
            file_size_bytes=1024,
            width=100,
            height=100,
            captured_at=date(2026, 6, 3),
            latitude=Decimal("19.076000"),
            longitude=Decimal("72.877700"),
            data_origin="PRODUCTION",
        )
        for index in range(4)
    ]
    db.add_all(photos)
    db.flush()

    classroom_pending = ClassroomObservation(
        observer_id=observer.id,
        school_id=school.id,
        target_para_teacher_id=para_teacher.id,
        school_teacher_id=None,
        class_division_id=division.id,
        subject="SCIENCE",
        topic="Matter",
        photo_id=photos[0].id,
        observed_at=__import__("datetime").datetime(2026, 6, 3),
        data_origin="PRODUCTION",
    )
    classroom_complete = ClassroomObservation(
        observer_id=observer.id,
        school_id=school.id,
        target_para_teacher_id=para_teacher.id,
        school_teacher_id=None,
        class_division_id=division.id,
        subject="SCIENCE",
        topic="Energy",
        photo_id=photos[1].id,
        observed_at=__import__("datetime").datetime(2026, 6, 4),
        data_origin="PRODUCTION",
    )
    inspection_pending = STEMInspection(
        inspector_id=observer.id,
        para_teacher_id=para_teacher.id,
        school_id=school.id,
        class_division_id=division.id,
        topic="STEM activity",
        photo_id=photos[2].id,
        inspected_at=__import__("datetime").datetime(2026, 6, 3),
        data_origin="PRODUCTION",
    )
    inspection_complete = STEMInspection(
        inspector_id=observer.id,
        para_teacher_id=para_teacher.id,
        school_id=school.id,
        class_division_id=division.id,
        topic="STEM project",
        photo_id=photos[3].id,
        inspected_at=__import__("datetime").datetime(2026, 6, 4),
        data_origin="PRODUCTION",
    )
    db.add_all(
        [
            classroom_pending,
            classroom_complete,
            inspection_pending,
            inspection_complete,
        ]
    )
    db.flush()

    db.add_all(
        [
            ClassroomObservationReport(
                observation_id=classroom_pending.id,
                status="PENDING",
                data_origin="PRODUCTION",
            ),
            ClassroomObservationReport(
                observation_id=classroom_complete.id,
                status="COMPLETE",
                mode="LINK",
                external_url="https://example.com/classroom-report",
                data_origin="PRODUCTION",
            ),
            STEMInspectionReport(
                inspection_id=inspection_pending.id,
                status="PENDING",
                data_origin="PRODUCTION",
            ),
            STEMInspectionReport(
                inspection_id=inspection_complete.id,
                status="COMPLETE",
                mode="LINK",
                external_url="https://example.com/stem-report",
                data_origin="PRODUCTION",
            ),
        ]
    )
    db.flush()

    try:
        result = get_school_monitoring(
            db,
            ReportingFilters(
                authorized_school_ids={school.id, fixture["school_two"].id},
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 6),
            ),
        )

        assert result["total_schools"] == 2

        items_by_school = {
            item["school_id"]: item
            for item in result["items"]
        }

        assert items_by_school[school.id]["observations"] == {
            "classroom_observations": 2,
            "classroom_reports_pending": 1,
            "classroom_reports_complete": 1,
            "stem_inspections": 2,
            "stem_reports_pending": 1,
            "stem_reports_complete": 1,
        }

        assert items_by_school[fixture["school_two"].id]["observations"] == {
            "classroom_observations": 0,
            "classroom_reports_pending": 0,
            "classroom_reports_complete": 0,
            "stem_inspections": 0,
            "stem_reports_pending": 0,
            "stem_reports_complete": 0,
        }
    finally:
        db.rollback()


def test_r7_class_monitoring_includes_empty_division_and_population(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]

    db.add_all(
        [
            Student(
                student_code=f"RP-INACTIVE-{fixture['division_one'].id.hex[:8]}",
                full_name="Inactive Reporting Student",
                gender="OTHER",
                roll_no=90,
                class_division_id=fixture["division_one"].id,
                status="INACTIVE",
                data_origin="PRODUCTION",
            ),
            Student(
                student_code=f"RP-TEST-{fixture['division_one'].id.hex[:8]}",
                full_name="Test-Origin Reporting Student",
                gender="OTHER",
                roll_no=91,
                class_division_id=fixture["division_one"].id,
                status="ACTIVE",
                data_origin="TEST",
            ),
        ]
    )
    db.flush()

    completed_sessions = fixture["sessions"][:4]
    photos = [
        Photo(
            photo_category="SESSION_EVIDENCE",
            storage_key=f"reporting-class-{session.id}.jpg",
            original_filename="reporting-class.jpg",
            content_type="image/jpeg",
            file_size_bytes=1024,
            width=100,
            height=100,
            captured_at=session.session_date,
            latitude=Decimal("19.076000"),
            longitude=Decimal("72.877700"),
            data_origin="PRODUCTION",
        )
        for session in completed_sessions[:2]
    ]
    db.add_all(photos)
    db.flush()
    db.add_all(
        [
            SessionEvidence(
                teaching_session_id=session.id,
                photo_id=photo.id,
                data_origin="PRODUCTION",
            )
            for session, photo in zip(completed_sessions[:2], photos)
        ]
    )

    db.flush()
    result = get_class_monitoring(
        db,
        ReportingFilters(
            authorized_school_ids={fixture["school_one"].id},
            academic_year_id=fixture["year"].id,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        ),
    )

    items = result["items"]
    by_id = {item["class_division_id"]: item for item in items}

    assert result["total_class_divisions"] == 2
    assert fixture["division_one"].id in by_id
    assert fixture["division_two"].id in by_id

    populated = by_id[fixture["division_one"].id]
    empty = by_id[fixture["division_two"].id]

    assert populated["active_students"] == 2
    assert empty["active_students"] == 2

    assert populated["para_teachers"] == 1
    assert populated["evidence"]["eligible_completed_sessions"] == 4
    assert populated["evidence"]["sessions_with_evidence"] == 2
    assert populated["evidence"]["completeness_percentage"] == 50.0

    assessment = populated["assessment"]

    assert assessment["latest"]["assessment_type"] == "ENDLINE"
    assert assessment["latest"]["result_count"] == 2
    assert assessment["baseline"]["result_count"] == 2
    assert assessment["baseline"]["average_percentage"] == 56.0
    assert assessment["endline"]["result_count"] == 2
    assert assessment["endline"]["average_percentage"] == 70.0

    longitudinal = assessment["longitudinal"]
    assert longitudinal["matched_students"] == 2
    assert longitudinal["average_baseline_percentage"] == 56.0
    assert longitudinal["average_endline_percentage"] == 70.0
    assert longitudinal["average_percentage_point_change"] == 14.0
    assert (
        longitudinal["result_scope"]
        == "matched_students_currently_assigned_to_class_division"
    )

    attention_by_code = {
        item["code"]: item
        for item in populated["attention"]
    }

    assert attention_by_code["COMPLETED_SESSION_MISSING_EVIDENCE"] == {
        "code": "COMPLETED_SESSION_MISSING_EVIDENCE",
        "scope": "class_division",
        "count": 2,
    }

    assert attention_by_code["SESSION_MISSING_TLM_RECORD"]["scope"] == (
        "class_division"
    )
    assert attention_by_code["SESSION_MISSING_TLM_RECORD"]["count"] == (
        populated["tlm"]["missing_tlm_sessions"]
    )
    assert populated["tlm"]["missing_tlm_sessions"] > 0

    assert populated["tlm"]["explicit_na_sessions"] == 1
    assert populated["tlm"]["sessions_with_tlm"] == 1

    # Four sessions have no TLM record; the explicit NA session is recorded.
    assert populated["tlm"]["missing_tlm_sessions"] == 4

    assert attention_by_code["SESSION_MISSING_TLM_RECORD"]["count"] == 4

    assert empty["attention"] == []

    assert empty["assessment"]["latest"]["result_count"] == 0
    assert empty["assessment"]["baseline"]["result_count"] == 0
    assert empty["assessment"]["endline"]["result_count"] == 0
    assert empty["assessment"]["baseline"]["average_percentage"] is None
    assert empty["assessment"]["endline"]["average_percentage"] is None
    assert empty["assessment"]["longitudinal"]["matched_students"] == 0

    trend = populated["delivery_trend"]
    assert len(trend) == 1
    assert trend[0]["completed_sessions"] == 4
    assert trend[0]["session_count"] == 6

    assert empty["delivery"] is None
    assert empty["attendance"] is None
    assert empty["engagement"] is None
    assert empty["tlm"] is None
    assert empty["delivery_trend"] == []
    assert empty["para_teachers"] == 0
    assert empty["evidence"]["eligible_completed_sessions"] == 0
    assert empty["evidence"]["sessions_with_evidence"] == 0
    assert empty["evidence"]["completeness_percentage"] is None


def test_r7_student_monitoring_includes_assessment_summary(domain_fixture):
    fixture = domain_fixture
    db = fixture["db"]
    student = fixture["student_one"]

    result = get_student_monitoring(
        db,
        ReportingFilters(
            authorized_school_ids={fixture["school_one"].id},
            academic_year_id=fixture["year"].id,
            school_id=fixture["school_one"].id,
        ),
        student_id=student.id,
        offset=0,
        limit=1,
    )

    assert result["total_students"] == 1
    assert len(result["items"]) == 1

    item = result["items"][0]
    assert item["student_id"] == student.id

    assessment = item["assessment"]
    assert assessment["latest"]["assessment_type"] == "ENDLINE"
    assert assessment["baseline"]["percentage"] == 40.0
    assert assessment["endline"]["percentage"] == 80.0
    assert assessment["percentage_point_change"] == 40.0


def test_r8_exports_are_real_and_use_same_rows(domain_fixture):
    rows = [{"metric": "teaching_hours", "value": 3.0}]
    report_metadata = metadata("delivery", "tester", {"school_id": None})
    csv_payload, csv_type, _ = report_bytes("delivery", rows, report_metadata, "csv")
    xlsx_payload, xlsx_type, _ = report_bytes("delivery", rows, report_metadata, "xlsx")
    pdf_payload, pdf_type, _ = report_bytes("delivery", rows, report_metadata, "pdf")
    assert csv_type == "text/csv"
    assert b"teaching_hours" in csv_payload
    assert xlsx_type.endswith("spreadsheetml.sheet")
    workbook = load_workbook(__import__("io").BytesIO(xlsx_payload))
    assert workbook.active["A1"].value == "Project Vigyan"
    assert pdf_type == "application/pdf"
    assert pdf_payload.startswith(b"%PDF")


def test_r7_class_monitoring_includes_observation_report_counts(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]
    school = fixture["school_one"]
    division = fixture["division_one"]
    empty_division = fixture["division_two"]
    try:
        observer = db.query(User).filter(User.user_code.like("RP-V-%")).one()
        para_teacher = db.query(User).filter(
            User.user_code.like("RP-PT-%")
        ).one()

        photos = [
            Photo(
                photo_category="STEM_INSPECTION",
                storage_key=f"class-monitoring-observation-{i}-{division.id}.jpg",
                original_filename="observation.jpg",
                content_type="image/jpeg",
                file_size_bytes=1024,
                width=100,
                height=100,
                captured_at=date(2026, 6, 3),
                latitude=Decimal("19.076000"),
                longitude=Decimal("72.877700"),
                data_origin="PRODUCTION",
            )
            for i in range(8)
        ]
        db.add_all(photos)
        db.flush()
        classroom_pending = ClassroomObservation(
            observer_id=observer.id,
            school_id=school.id,
            target_para_teacher_id=para_teacher.id,
            school_teacher_id=None,
            class_division_id=division.id,
            subject="SCIENCE",
            topic="Matter",
            photo_id=photos[0].id,
            observed_at=datetime(2026, 6, 3),
            data_origin="PRODUCTION",
        )
        classroom_complete = ClassroomObservation(
            observer_id=observer.id,
            school_id=school.id,
            target_para_teacher_id=para_teacher.id,
            school_teacher_id=None,
            class_division_id=division.id,
            subject="SCIENCE",
            topic="Energy",
            photo_id=photos[1].id,
            observed_at=datetime(2026, 6, 4),
            data_origin="PRODUCTION",
        )
        inspection_pending = STEMInspection(
            inspector_id=observer.id,
            para_teacher_id=para_teacher.id,
            school_id=school.id,
            class_division_id=division.id,
            topic="STEM activity",
            photo_id=photos[2].id,
            inspected_at=datetime(2026, 6, 3),
            data_origin="PRODUCTION",
        )
        inspection_complete = STEMInspection(
            inspector_id=observer.id,
            para_teacher_id=para_teacher.id,
            school_id=school.id,
            class_division_id=division.id,
            topic="STEM project",
            photo_id=photos[3].id,
            inspected_at=datetime(2026, 6, 4),
            data_origin="PRODUCTION",
        )
        inspection_without_division = STEMInspection(
            inspector_id=observer.id,
            para_teacher_id=para_teacher.id,
            school_id=school.id,
            class_division_id=None,
            topic="School-level STEM inspection",
            photo_id=photos[4].id,
            inspected_at=datetime(2026, 6, 4),
            data_origin="PRODUCTION",
        )
        test_origin_observation = ClassroomObservation(
            observer_id=observer.id,
            school_id=school.id,
            target_para_teacher_id=para_teacher.id,
            school_teacher_id=None,
            class_division_id=division.id,
            subject="SCIENCE",
            topic="Should not count",
            photo_id=photos[5].id,
            observed_at=datetime(2026, 6, 4),
            data_origin="TEST",
        )
        out_of_range_observation = ClassroomObservation(
            observer_id=observer.id,
            school_id=school.id,
            target_para_teacher_id=para_teacher.id,
            school_teacher_id=None,
            class_division_id=division.id,
            subject="SCIENCE",
            topic="Outside reporting period",
            photo_id=photos[6].id,
            observed_at=datetime(2026, 6, 7),
            data_origin="PRODUCTION",
        )
        out_of_range_inspection = STEMInspection(
            inspector_id=observer.id,
            para_teacher_id=para_teacher.id,
            school_id=school.id,
            class_division_id=division.id,
            topic="Outside reporting period",
            photo_id=photos[7].id,
            inspected_at=datetime(2026, 6, 7),
            data_origin="PRODUCTION",
        )
        db.add_all([
            classroom_pending,
            classroom_complete,
            inspection_pending,
            inspection_complete,
            inspection_without_division,
            test_origin_observation,
            out_of_range_observation,
            out_of_range_inspection,
        ])
        db.flush()

        db.add_all([
            ClassroomObservationReport(
                observation_id=classroom_pending.id,
                status="PENDING",
                data_origin="PRODUCTION",
            ),
            ClassroomObservationReport(
                observation_id=classroom_complete.id,
                status="COMPLETE",
                mode="LINK",
                external_url="https://example.com/classroom-report",
                data_origin="PRODUCTION",
            ),
            STEMInspectionReport(
                inspection_id=inspection_pending.id,
                status="PENDING",
                data_origin="PRODUCTION",
            ),
            STEMInspectionReport(
                inspection_id=inspection_complete.id,
                status="COMPLETE",
                mode="LINK",
                external_url="https://example.com/stem-report",
                data_origin="PRODUCTION",
            ),
            STEMInspectionReport(
                inspection_id=inspection_without_division.id,
                status="PENDING",
                data_origin="PRODUCTION",
            ),
        ])
        db.flush()

        result = get_class_monitoring(
            db,
            ReportingFilters(
                authorized_school_ids={school.id},
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 6),
            ),
        )
        by_id = {item["class_division_id"]: item for item in result["items"]}

        assert by_id[division.id]["observations"] == {
            "classroom_observations": 2,
            "classroom_reports_pending": 1,
            "classroom_reports_complete": 1,
            "stem_inspections": 2,
            "stem_reports_pending": 1,
            "stem_reports_complete": 1,
        }
        assert by_id[empty_division.id]["observations"] == {
            "classroom_observations": 0,
            "classroom_reports_pending": 0,
            "classroom_reports_complete": 0,
            "stem_inspections": 0,
            "stem_reports_pending": 0,
            "stem_reports_complete": 0,
        }
    finally:
        db.rollback()


def test_para_teacher_monitoring_keeps_observations_with_recorded_school(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]
    teacher = db.query(User).filter(
        User.user_code.like("RP-PT-%")
    ).one()
    observer = db.query(User).filter(
        User.user_code.like("RP-V-%")
    ).one()
    school = fixture["school_two"]
    division = fixture["student_other_school"].class_division_id

    try:
        photo = Photo(
            photo_category="STEM_INSPECTION",
            storage_key=f"para-monitoring-history-{school.id}.jpg",
            original_filename="observation.jpg",
            content_type="image/jpeg",
            file_size_bytes=1024,
            width=100,
            height=100,
            captured_at=date(2026, 6, 3),
            latitude=Decimal("19.076000"),
            longitude=Decimal("72.877700"),
            data_origin="PRODUCTION",
        )
        db.add(photo)
        db.flush()

        observation = ClassroomObservation(
            observer_id=observer.id,
            school_id=school.id,
            target_para_teacher_id=teacher.id,
            school_teacher_id=None,
            class_division_id=division,
            subject="SCIENCE",
            topic="Historical school attribution",
            photo_id=photo.id,
            observed_at=datetime(2026, 6, 3),
            data_origin="PRODUCTION",
        )
        db.add(observation)
        db.flush()

        db.add(
            ClassroomObservationReport(
                observation_id=observation.id,
                status="PENDING",
                data_origin="PRODUCTION",
            )
        )
        db.flush()

        project_wide = ReportingFilters(
            authorized_school_ids=None,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        )
        result = get_para_teacher_monitoring(db, project_wide)
        historical_rows = [
            item
            for item in result["items"]
            if item["para_teacher_id"] == teacher.id
            and item["school_id"] == school.id
        ]

        assert len(historical_rows) == 1
        assert historical_rows[0]["observations"][
            "classroom_observations"
        ] == 1
        assert historical_rows[0]["observations"][
            "classroom_reports_pending"
        ] == 1

        own_school_result = get_para_teacher_monitoring(
            db,
            ReportingFilters(
                authorized_school_ids={fixture["school_one"].id},
                school_id=fixture["school_one"].id,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 6),
            ),
        )
        assert all(
            item["school_id"] == fixture["school_one"].id
            for item in own_school_result["items"]
        )
        assert not any(
            item["school_id"] == school.id
            for item in own_school_result["items"]
        )
    finally:
        db.rollback()


def test_class_assessment_report_respects_recorded_scope(domain_fixture):
    from app.models.assessment import AssessmentClassDivision
    from app.services.reporting.monitoring import _class_assessment_report

    fixture = domain_fixture
    db = fixture["db"]
    assessment = fixture["assessments"][1]  # Endline
    division_one = fixture["division_one"]
    division_two = fixture["division_two"]

    try:
        # The fixture's two endline results belong to division_one.
        # Record division_two as the assessment's only in-scope division.
        db.add(
            AssessmentClassDivision(
                assessment_id=assessment.id,
                class_division_id=division_two.id,
            )
        )
        db.flush()

        report = _class_assessment_report(
            db,
            assessment,
            {fixture["school_one"].id},
            division_one.id,
        )

        assert report["assessment_import_scope"] == "selected_class_divisions"
        assert report["assessment_import_class_divisions"] == [
            {
                "class_division_id": division_two.id,
                "class_level": division_two.class_level,
                "division": division_two.division,
            }
        ]
        assert report["result_count"] == 0
        assert report["results"] == []

        # A historical assessment with no recorded scope remains explicitly unknown.
        historical = fixture["assessments"][0]
        historical_report = _class_assessment_report(
            db,
            historical,
            {fixture["school_one"].id},
            division_one.id,
        )
        assert (
            historical_report["assessment_import_scope"]
            == "unknown_historical_scope"
        )
        assert historical_report["assessment_import_class_divisions"] == []
    finally:
        db.rollback()


def test_para_teacher_monitoring_keeps_session_metrics_attributed_by_school(
    domain_fixture,
):
    fixture = domain_fixture
    db = fixture["db"]
    teacher = db.query(User).filter(
        User.user_code.like("RP-PT-%")
    ).one()
    school_one = fixture["school_one"]
    school_two = fixture["school_two"]
    division_two = (
        db.query(ClassDivision)
        .filter(
            ClassDivision.id
            == fixture["student_other_school"].class_division_id
        )
        .one()
    )

    try:
        def report(school_id=None):
            return get_para_teacher_monitoring(
                db,
                ReportingFilters(
                    authorized_school_ids=None,
                    school_id=school_id,
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 6),
                ),
            )

        def teacher_row(result, school_id):
            matches = [
                item
                for item in result["items"]
                if str(item["para_teacher_id"]) == str(teacher.id)
                and str(item["school_id"]) == str(school_id)
            ]
            assert len(matches) <= 1, (
                f"Expected at most one row for teacher {teacher.id} "
                f"at school {school_id}; got {matches!r}"
            )
            return matches[0] if matches else None

        baseline_one = teacher_row(report(school_one.id), school_one.id)
        baseline_two = teacher_row(report(school_two.id), school_two.id)
        session = TeachingSession(
            class_division_id=division_two.id,
            para_teacher_id=teacher.id,
            session_date=date(2026, 6, 3),
            status="COMPLETED",
            duration_minutes=120,
            data_origin="PRODUCTION",
        )
        db.add(session)
        db.flush()

        db.add(
            SessionEngagement(
                teaching_session_id=session.id,
                score=10,
                data_origin="PRODUCTION",
            )
        )
        db.add(
            SessionTLM(
                teaching_session_id=session.id,
                tlm_id=fixture["normal_tlm"].id,
                quantity=1,
                data_origin="PRODUCTION",
            )
        )
        db.flush()


        school_one_filters = ReportingFilters(
            authorized_school_ids=None,
            school_id=school_one.id,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        )
        raw_delivery = get_delivery_report(
            db, school_one_filters, group_by="para_teacher"
        )
        assert raw_delivery["items"], (
            f"No delivery rows for school_one={school_one.id}; "
            f"raw delivery result={raw_delivery}"
        )
        school_one_row = teacher_row(report(school_one.id), school_one.id)
        school_two_row = teacher_row(report(school_two.id), school_two.id)
        project_result = report()
        project_one_row = teacher_row(project_result, school_one.id)
        project_two_row = teacher_row(project_result, school_two.id)

        # The new completed session belongs to School Two only.
        assert school_two_row["completed_sessions"] == (
            (baseline_two or {}).get("completed_sessions", 0) + 1
        )
        assert school_one_row["completed_sessions"] == (
            (baseline_one or {}).get("completed_sessions", 0)
        )

        assert school_two_row["completed_duration_minutes"] == (
            (baseline_two or {}).get("completed_duration_minutes", 0) + 120
        )
        assert school_one_row["completed_duration_minutes"] == (
            (baseline_one or {}).get("completed_duration_minutes", 0)
        )

        delivery_keys = (
            "total_sessions",
            "planned_sessions",
            "upcoming_sessions",
            "in_progress_sessions",
            "completed_sessions",
            "cancelled_sessions",
            "completed_duration_minutes",
            "completed_sessions_with_duration",
            "teaching_hours",
            "average_completed_duration_minutes",
            "completion_percentage",
        )

        for key in delivery_keys:
            assert project_one_row.get(key) == school_one_row.get(key)
            assert project_two_row.get(key) == school_two_row.get(key)

        assert project_one_row["engagement"] == school_one_row["engagement"]
        assert project_two_row["engagement"] == school_two_row["engagement"]
        assert project_one_row["tlm"] == school_one_row["tlm"]
        assert project_two_row["tlm"] == school_two_row["tlm"]
    finally:
        db.rollback()
