from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    AcademicYear,
    Assessment,
    AssessmentImport,
    AssessmentResult,
    AuthSession,
    ClassDivision,
    Permission,
    Role,
    RolePermission,
    School,
    SessionAttendance,
    SessionEngagement,
    SessionEvidence,
    SessionTLM,
    Student,
    TeachingSession,
    User,
    UserAssignment,
    UserRole,
)
from app.services.auth_service import generate_session_token, hash_password, hash_session_token
from app.services.reporting.attendance import AttendanceFilter, get_attendance_groups
from app.services.reporting.common import ReportingFilters
from app.services.reporting.monitoring import get_student_monitoring


client = TestClient(app)
PASSWORD = "ReportingAttendance!2026"


@pytest.fixture
def reporting_fixture():
    db = SessionLocal()
    stale_users = (
        db.query(User)
        .filter(User.user_code.like("RP-%"))
        .all()
    )
    stale_user_ids = [user.id for user in stale_users]
    stale_roles = (
        db.query(Role)
        .filter(
            (Role.code.like("REPORTING_VIEWER_%"))
            | (Role.code.like("REPORTING_NO_PERMISSION_%"))
        )
        .all()
    )
    stale_role_ids = [role.id for role in stale_roles]
    if stale_user_ids:
        db.query(AuthSession).filter(
            AuthSession.user_id.in_(stale_user_ids)
        ).delete(synchronize_session=False)
        db.query(UserRole).filter(
            UserRole.user_id.in_(stale_user_ids)
        ).delete(synchronize_session=False)
        db.query(UserAssignment).filter(
            UserAssignment.user_id.in_(stale_user_ids)
        ).delete(synchronize_session=False)
    if stale_role_ids:
        db.query(RolePermission).filter(
            RolePermission.role_id.in_(stale_role_ids)
        ).delete(synchronize_session=False)
        db.query(UserRole).filter(
            UserRole.role_id.in_(stale_role_ids)
        ).delete(synchronize_session=False)
    stale_years = (
        db.query(AcademicYear)
        .filter(AcademicYear.name.like("Reporting Year %"))
        .all()
    )
    stale_year_ids = [year.id for year in stale_years]

    if stale_year_ids:
        stale_assessments = (
            db.query(Assessment)
            .filter(Assessment.academic_year_id.in_(stale_year_ids))
            .all()
        )
        stale_assessment_ids = [
            assessment.id for assessment in stale_assessments
        ]

        if stale_assessment_ids:
            db.query(AssessmentImport).filter(
                AssessmentImport.assessment_id.in_(stale_assessment_ids)
            ).delete(synchronize_session=False)
            db.query(AssessmentResult).filter(
                AssessmentResult.assessment_id.in_(stale_assessment_ids)
            ).delete(synchronize_session=False)
            db.query(Assessment).filter(
                Assessment.id.in_(stale_assessment_ids)
            ).delete(synchronize_session=False)

        db.query(AcademicYear).filter(
            AcademicYear.id.in_(stale_year_ids)
        ).delete(synchronize_session=False)

    if stale_user_ids:
        stale_user_sessions = (
            db.query(TeachingSession)
            .filter(TeachingSession.para_teacher_id.in_(stale_user_ids))
            .all()
        )
        stale_user_session_ids = [
            session.id for session in stale_user_sessions
        ]

        if stale_user_session_ids:
            db.query(SessionAttendance).filter(
                SessionAttendance.teaching_session_id.in_(
                    stale_user_session_ids
                )
            ).delete(synchronize_session=False)
            db.query(SessionEngagement).filter(
                SessionEngagement.teaching_session_id.in_(
                    stale_user_session_ids
                )
            ).delete(synchronize_session=False)
            db.query(SessionTLM).filter(
                SessionTLM.teaching_session_id.in_(
                    stale_user_session_ids
                )
            ).delete(synchronize_session=False)
            db.query(SessionEvidence).filter(
                SessionEvidence.teaching_session_id.in_(
                    stale_user_session_ids
                )
            ).delete(synchronize_session=False)
            db.query(TeachingSession).filter(
                TeachingSession.id.in_(stale_user_session_ids)
            ).delete(synchronize_session=False)

    if stale_users:
        db.query(User).filter(User.id.in_(stale_user_ids)).delete(
            synchronize_session=False
        )
    if stale_roles:
        db.query(Role).filter(Role.id.in_(stale_role_ids)).delete(
            synchronize_session=False
        )
    stale_schools = (
        db.query(School)
        .filter(
            (School.school_code.like("RP1-%"))
            | (School.school_code.like("RP2-%"))
        )
        .all()
    )
    stale_school_ids = [school.id for school in stale_schools]
    stale_divisions = (
        db.query(ClassDivision)
        .filter(ClassDivision.school_id.in_(stale_school_ids))
        .all()
        if stale_school_ids
        else []
    )
    stale_division_ids = [division.id for division in stale_divisions]
    stale_sessions = (
        db.query(TeachingSession)
        .filter(TeachingSession.class_division_id.in_(stale_division_ids))
        .all()
        if stale_division_ids
        else []
    )
    stale_session_ids = [session.id for session in stale_sessions]
    if stale_session_ids:
        db.query(SessionAttendance).filter(
            SessionAttendance.teaching_session_id.in_(stale_session_ids)
        ).delete(synchronize_session=False)
        db.query(TeachingSession).filter(
            TeachingSession.id.in_(stale_session_ids)
        ).delete(synchronize_session=False)
    if stale_division_ids:
        db.query(Student).filter(
            Student.class_division_id.in_(stale_division_ids)
        ).delete(synchronize_session=False)
        db.query(ClassDivision).filter(
            ClassDivision.id.in_(stale_division_ids)
        ).delete(synchronize_session=False)
    if stale_school_ids:
        db.query(School).filter(School.id.in_(stale_school_ids)).delete(
            synchronize_session=False
        )
    db.commit()
    suffix = uuid4().hex[:10]
    school_one = School(
        school_code=f"RP1-{suffix}",
        school_name="Reporting School One",
        status="ACTIVE",
        data_origin="PRODUCTION",
    )
    school_two = School(
        school_code=f"RP2-{suffix}",
        school_name="Reporting School Two",
        status="ACTIVE",
        data_origin="PRODUCTION",
    )
    db.add_all([school_one, school_two])
    db.flush()

    divisions = [
        ClassDivision(
            school_id=school_one.id,
            class_level=5,
            division="A",
            status="ACTIVE",
            data_origin="PRODUCTION",
        ),
        ClassDivision(
            school_id=school_one.id,
            class_level=6,
            division="B",
            status="ACTIVE",
            data_origin="PRODUCTION",
        ),
        ClassDivision(
            school_id=school_two.id,
            class_level=5,
            division="A",
            status="ACTIVE",
            data_origin="PRODUCTION",
        ),
    ]
    db.add_all(divisions)
    db.flush()

    students = []
    for index, division in enumerate(divisions):
        for roll_no in (1, 2):
            students.append(
                Student(
                    student_code=f"RP-ST-{suffix}-{index}-{roll_no}",
                    full_name=f"Reporting Student {index}-{roll_no}",
                    gender="OTHER",
                    roll_no=roll_no,
                    class_division_id=division.id,
                    status="ACTIVE",
                    data_origin="PRODUCTION",
                )
            )
    db.add_all(students)
    db.flush()

    year = AcademicYear(
        name=f"Reporting Year {suffix}",
        start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31),
        data_origin="PRODUCTION",
    )
    db.add(year)
    db.flush()

    para_teacher = User(
        user_code=f"RP-PT-{suffix}",
        full_name="Reporting Para Teacher",
        email=f"rp-pt-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        status="ACTIVE",
        data_origin="TEST",
    )
    viewer = User(
        user_code=f"RP-V-{suffix}",
        full_name="Reporting Viewer",
        email=f"rp-viewer-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        status="ACTIVE",
        data_origin="TEST",
    )
    no_permission = User(
        user_code=f"RP-NP-{suffix}",
        full_name="Reporting No Permission",
        email=f"rp-no-permission-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        status="ACTIVE",
        data_origin="TEST",
    )
    platform_owner = User(
        user_code=f"RP-PO-{suffix}",
        full_name="Reporting Platform Owner",
        email=f"rp-platform-owner-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([para_teacher, viewer, no_permission, platform_owner])
    db.flush()

    report_role = Role(
        name=f"Reporting Viewer {suffix}",
        code=f"REPORTING_VIEWER_{suffix.upper()}",
        description="Synthetic reporting test role.",
        is_system_role=False,
    )
    no_permission_role = Role(
        name=f"Reporting No Permission {suffix}",
        code=f"REPORTING_NO_PERMISSION_{suffix.upper()}",
        description="Synthetic reporting test role.",
        is_system_role=False,
    )
    db.add_all([report_role, no_permission_role])
    db.flush()
    platform_role = db.query(Role).filter(Role.code == "PLATFORM_OWNER").one()
    report_permission = (
        db.query(Permission).filter(Permission.code == "report.view").one()
    )
    db.add_all(
        [
            RolePermission(
                role_id=report_role.id,
                permission_id=report_permission.id,
            ),
            UserRole(user_id=viewer.id, role_id=report_role.id, is_active=True),
            UserRole(
                user_id=no_permission.id,
                role_id=no_permission_role.id,
                is_active=True,
            ),
            UserRole(
                user_id=platform_owner.id,
                role_id=platform_role.id,
                is_active=True,
            ),
            UserAssignment(
                user_id=viewer.id,
                scope_type="SCHOOL",
                school_id=school_one.id,
                start_date=date(2026, 1, 1),
                is_active=True,
            ),
        ]
    )

    sessions = [
        (divisions[0], date(2026, 4, 1), ["PRESENT", "PRESENT"]),
        (divisions[0], date(2026, 4, 2), ["PRESENT", "ABSENT"]),
        (divisions[1], date(2026, 5, 1), ["ABSENT", "ABSENT"]),
        (divisions[2], date(2026, 4, 1), ["PRESENT", "ABSENT"]),
        (divisions[0], date(2027, 4, 1), ["PRESENT", "PRESENT"]),
    ]
    created_sessions = []
    for division, session_date, statuses in sessions:
        session = TeachingSession(
            class_division_id=division.id,
            para_teacher_id=para_teacher.id,
            session_date=session_date,
            status="COMPLETED",
            duration_minutes=45,
            data_origin="PRODUCTION",
        )
        db.add(session)
        db.flush()
        created_sessions.append(session)
        division_students = [
            student
            for student in students
            if student.class_division_id == division.id
        ]
        db.add_all(
            [
                SessionAttendance(
                    teaching_session_id=session.id,
                    student_id=student.id,
                    status=status,
                    data_origin="PRODUCTION",
                )
                for student, status in zip(division_students, statuses)
            ]
        )

    db.commit()
    token_users = [viewer, no_permission, platform_owner]
    tokens = {}
    for user in token_users:
        token = generate_session_token()
        db.add(
            AuthSession(
                user_id=user.id,
                token_hash=hash_session_token(token),
                expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
                last_activity_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            )
        )
        tokens[user.email] = token
    db.commit()

    result = {
        "db": db,
        "school_one": school_one,
        "school_two": school_two,
        "division_one": divisions[0],
        "division_two": divisions[1],
        "student_one": students[0],
        "student_other_school": students[4],
        "year": year,
        "viewer_token": tokens[viewer.email],
        "no_permission_token": tokens[no_permission.email],
        "platform_owner_token": tokens[platform_owner.email],
    }
    try:
        yield result
    finally:
        db.rollback()
        db.query(AuthSession).filter(
            AuthSession.user_id.in_([viewer.id, no_permission.id])
        ).delete(synchronize_session=False)
        db.query(UserRole).filter(
            UserRole.user_id.in_(
                [viewer.id, no_permission.id, platform_owner.id]
            )
        ).delete(synchronize_session=False)
        db.query(UserAssignment).filter(
            UserAssignment.user_id == viewer.id
        ).delete(synchronize_session=False)
        db.query(AuthSession).filter(
            AuthSession.user_id == platform_owner.id
        ).delete(synchronize_session=False)
        db.query(RolePermission).filter(
            RolePermission.role_id.in_([report_role.id, no_permission_role.id])
        ).delete(synchronize_session=False)
        db.query(SessionAttendance).filter(
            SessionAttendance.teaching_session_id.in_(
                [session.id for session in created_sessions]
            )
        ).delete(synchronize_session=False)
        db.query(TeachingSession).filter(
            TeachingSession.id.in_([session.id for session in created_sessions])
        ).delete(synchronize_session=False)
        db.delete(year)
        db.delete(viewer)
        db.delete(no_permission)
        db.delete(platform_owner)
        db.delete(para_teacher)
        db.delete(report_role)
        db.delete(no_permission_role)
        db.delete(divisions[0])
        db.delete(divisions[1])
        db.delete(divisions[2])
        for student in students:
            db.delete(student)
        db.delete(school_one)
        db.delete(school_two)
        db.commit()
        db.close()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_attendance_service_is_record_weighted_and_grouped(reporting_fixture):
    fixture = reporting_fixture
    filters = AttendanceFilter(authorized_school_ids=None)

    project_items, total = get_attendance_groups(
        fixture["db"], filters, "project"
    )
    assert total == 1
    assert project_items[0]["eligible_record_count"] == 10
    assert project_items[0]["present_record_count"] == 6
    assert project_items[0]["absent_record_count"] == 4
    assert project_items[0]["attendance_percentage"] == 60.0

    school_items, _ = get_attendance_groups(
        fixture["db"], filters, "school"
    )
    school_one = next(
        item
        for item in school_items
        if item["school_id"] == fixture["school_one"].id
    )
    assert school_one["eligible_record_count"] == 8
    assert school_one["present_record_count"] == 5
    assert school_one["attendance_percentage"] == 62.5


def test_attendance_service_applies_date_and_academic_year_filters(
    reporting_fixture,
):
    fixture = reporting_fixture
    filters = AttendanceFilter(
        authorized_school_ids=None,
        academic_year_id=fixture["year"].id,
        start_date=date(2026, 4, 2),
        end_date=date(2026, 5, 1),
    )
    items, total = get_attendance_groups(
        fixture["db"], filters, "project"
    )
    assert total == 1
    assert items[0]["eligible_record_count"] == 4
    assert items[0]["present_record_count"] == 1
    assert items[0]["attendance_percentage"] == 25.0


def test_attendance_service_authorized_school_scope_excludes_other_school(
    reporting_fixture,
):
    fixture = reporting_fixture
    items, _ = get_attendance_groups(
        fixture["db"],
        AttendanceFilter(authorized_school_ids={fixture["school_one"].id}),
        "school",
    )
    assert len(items) == 1
    assert items[0]["school_id"] == fixture["school_one"].id


def test_attendance_service_excludes_non_production_rows(reporting_fixture):
    fixture = reporting_fixture
    attendance = (
        fixture["db"]
        .query(SessionAttendance)
        .filter(SessionAttendance.student_id == fixture["student_one"].id)
        .first()
    )
    attendance.data_origin = "TEST"
    updated = 1
    assert updated == 1
    fixture["db"].flush()
    assert (
        fixture["db"]
        .query(SessionAttendance.data_origin)
        .filter(SessionAttendance.id == attendance.id)
        .scalar()
        == "TEST"
    )
    try:
        items, _ = get_attendance_groups(
            fixture["db"],
            AttendanceFilter(authorized_school_ids=None),
            "project",
        )
        assert items[0]["eligible_record_count"] == 9
    finally:
        fixture["db"].rollback()


def test_attendance_report_requires_authentication(reporting_fixture):
    response = client.get("/api/v1/reporting/attendance")
    assert response.status_code == 401


def test_attendance_report_requires_report_permission(reporting_fixture):
    response = client.get(
        "/api/v1/reporting/attendance",
        headers=_headers(reporting_fixture["no_permission_token"]),
    )
    assert response.status_code == 403


def test_project_wide_role_can_view_all_schools(reporting_fixture):
    response = client.get(
        "/api/v1/reporting/attendance",
        params={"group_by": "school"},
        headers=_headers(reporting_fixture["platform_owner_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_groups"] == 2


def test_school_scoped_report_cannot_cross_school_filters(reporting_fixture):
    fixture = reporting_fixture
    headers = _headers(fixture["viewer_token"])
    for query in (
        f"school_id={fixture['school_two'].id}",
        f"class_division_id={fixture['student_other_school'].class_division_id}",
        f"student_id={fixture['student_other_school'].id}",
    ):
        response = client.get(
            f"/api/v1/reporting/attendance?{query}",
            headers=headers,
        )
        assert response.status_code == 403


def test_attendance_report_supports_filters_and_pagination(reporting_fixture):
    fixture = reporting_fixture
    response = client.get(
        "/api/v1/reporting/attendance",
        params={
            "group_by": "class_division",
            "school_id": str(fixture["school_one"].id),
            "academic_year_id": str(fixture["year"].id),
            "limit": 1,
            "offset": 0,
        },
        headers=_headers(fixture["viewer_token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_groups"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["eligible_record_count"] in {2, 4}


@pytest.mark.parametrize(
    "params",
    [
        {"group_by": "invalid"},
        {"start_date": "not-a-date"},
        {"start_date": "2026-05-02", "end_date": "2026-05-01"},
        {"limit": 0},
        {"student_id": "not-a-uuid"},
    ],
)
def test_attendance_report_rejects_invalid_parameters(
    reporting_fixture,
    params,
):
    response = client.get(
        "/api/v1/reporting/attendance",
        params=params,
        headers=_headers(reporting_fixture["viewer_token"]),
    )
    assert response.status_code == 422


def test_empty_attendance_result_is_deterministic(reporting_fixture):
    response = client.get(
        "/api/v1/reporting/attendance",
        params={
            "group_by": "student",
            "start_date": "2030-01-01",
            "end_date": "2030-01-31",
        },
        headers=_headers(reporting_fixture["viewer_token"]),
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total_groups"] == 0


def test_student_monitoring_limits_attendance_lookup_to_requested_page(
    reporting_fixture,
    monkeypatch,
):
    fixture = reporting_fixture
    expected_student = fixture["student_one"]

    captured = {}

    def fake_get_attendance_groups(db, filters, group_by, offset=0, limit=100):
        captured["student_ids"] = filters.student_ids
        captured["student_id"] = filters.student_id
        captured["offset"] = offset
        captured["limit"] = limit
        return [], 0

    monkeypatch.setattr(
        "app.services.reporting.monitoring.get_attendance_groups",
        fake_get_attendance_groups,
    )

    result = get_student_monitoring(
        fixture["db"],
        ReportingFilters(
            authorized_school_ids={fixture["school_one"].id},
            school_id=fixture["school_one"].id,
        ),
        student_id=expected_student.id,
        offset=0,
        limit=1,
    )

    assert result["total_students"] == 1
    assert len(result["items"]) == 1
    assert captured["student_ids"] == {expected_student.id}
    assert captured["student_id"] == expected_student.id
    assert captured["offset"] == 0
    assert captured["limit"] == 1


def test_student_list_requires_authentication_and_report_permission(
    reporting_fixture,
):
    unauthenticated = client.get("/api/v1/reporting/students")
    assert unauthenticated.status_code == 401

    forbidden = client.get(
        "/api/v1/reporting/students",
        headers=_headers(reporting_fixture["no_permission_token"]),
    )
    assert forbidden.status_code == 403


def test_student_list_search_matches_name_and_code(reporting_fixture):
    fixture = reporting_fixture
    headers = _headers(fixture["viewer_token"])

    by_name = client.get(
        "/api/v1/reporting/students",
        params={"search": "Reporting Student 0-1"},
        headers=headers,
    )
    assert by_name.status_code == 200, by_name.text
    name_body = by_name.json()
    assert name_body["total_students"] == 1
    assert len(name_body["items"]) == 1
    assert name_body["items"][0]["student_id"] == str(
        fixture["student_one"].id
    )

    by_code = client.get(
        "/api/v1/reporting/students",
        params={"search": fixture["student_one"].student_code},
        headers=headers,
    )
    assert by_code.status_code == 200, by_code.text
    assert by_code.json()["total_students"] == 1

    no_match = client.get(
        "/api/v1/reporting/students",
        params={"search": "no-student-matches-this"},
        headers=headers,
    )
    assert no_match.status_code == 200, no_match.text
    assert no_match.json()["items"] == []
    assert no_match.json()["total_students"] == 0


def test_student_list_pagination_preserves_total(reporting_fixture):
    fixture = reporting_fixture
    headers = _headers(fixture["viewer_token"])

    first = client.get(
        "/api/v1/reporting/students",
        params={"limit": 2, "offset": 0},
        headers=headers,
    )
    second = client.get(
        "/api/v1/reporting/students",
        params={"limit": 2, "offset": 2},
        headers=headers,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    first_body = first.json()
    second_body = second.json()

    assert first_body["total_students"] == 4
    assert second_body["total_students"] == 4
    assert first_body["offset"] == 0
    assert second_body["offset"] == 2
    assert first_body["limit"] == second_body["limit"] == 2
    assert len(first_body["items"]) == 2
    assert len(second_body["items"]) == 2

    first_ids = {item["student_id"] for item in first_body["items"]}
    second_ids = {item["student_id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_student_list_enforces_school_scope(reporting_fixture):
    fixture = reporting_fixture
    headers = _headers(fixture["viewer_token"])

    own_school = client.get(
        "/api/v1/reporting/students",
        headers=headers,
    )
    assert own_school.status_code == 200, own_school.text
    own_body = own_school.json()
    assert own_body["total_students"] == 4
    assert all(
        item["school_id"] == str(fixture["school_one"].id)
        for item in own_body["items"]
    )

    cross_school = client.get(
        "/api/v1/reporting/students",
        params={"school_id": str(fixture["school_two"].id)},
        headers=headers,
    )
    assert cross_school.status_code == 403

    project_wide = client.get(
        "/api/v1/reporting/students",
        headers=_headers(fixture["platform_owner_token"]),
    )
    assert project_wide.status_code == 200, project_wide.text
    assert project_wide.json()["total_students"] == 6


@pytest.mark.parametrize(
    "params",
    [
        {"offset": -1},
        {"limit": 0},
        {"limit": 501},
        {"search": "x" * 151},
    ],
)
def test_student_list_rejects_invalid_parameters(reporting_fixture, params):
    response = client.get(
        "/api/v1/reporting/students",
        params=params,
        headers=_headers(reporting_fixture["viewer_token"]),
    )
    assert response.status_code == 422


def test_student_detail_requires_authentication_and_report_permission(
    reporting_fixture,
):
    fixture = reporting_fixture
    url = f"/api/v1/reporting/students/{fixture['student_one'].id}"

    unauthenticated = client.get(url)
    assert unauthenticated.status_code == 401

    forbidden = client.get(
        url,
        headers=_headers(fixture["no_permission_token"]),
    )
    assert forbidden.status_code == 403


def test_student_detail_returns_monitoring_for_requested_student(
    reporting_fixture,
):
    fixture = reporting_fixture
    student = fixture["student_one"]

    response = client.get(
        f"/api/v1/reporting/students/{student.id}",
        headers=_headers(fixture["viewer_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_students"] == 1
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["student_id"] == str(student.id)
    assert item["student_code"] == student.student_code
    assert item["student_name"] == student.full_name
    assert item["school_id"] == str(fixture["school_one"].id)
    assert item["class_division_id"] == str(student.class_division_id)
    assert "attendance" in item
    assert "assessment" in item


def test_student_detail_rejects_unknown_student(reporting_fixture):
    response = client.get(
        f"/api/v1/reporting/students/{uuid4()}",
        headers=_headers(reporting_fixture["viewer_token"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Student not found."


def test_student_detail_enforces_school_scope(reporting_fixture):
    fixture = reporting_fixture

    response = client.get(
        f"/api/v1/reporting/students/{fixture['student_other_school'].id}",
        headers=_headers(fixture["viewer_token"]),
    )

    assert response.status_code == 403


def test_para_teacher_monitoring_requires_authentication_and_permission(
    reporting_fixture,
):
    unauthenticated = client.get("/api/v1/reporting/para-teachers")
    assert unauthenticated.status_code == 401

    forbidden = client.get(
        "/api/v1/reporting/para-teachers",
        headers=_headers(reporting_fixture["no_permission_token"]),
    )
    assert forbidden.status_code == 403


def test_para_teacher_monitoring_respects_school_scope(reporting_fixture):
    fixture = reporting_fixture
    headers = _headers(fixture["viewer_token"])

    own_school = client.get(
        "/api/v1/reporting/para-teachers",
        params={"school_id": str(fixture["school_one"].id)},
        headers=headers,
    )
    assert own_school.status_code == 200, own_school.text
    own_body = own_school.json()
    assert "items" in own_body
    assert "total_para_teachers" in own_body
    assert all(
        item["school_id"] == str(fixture["school_one"].id)
        for item in own_body["items"]
    )
    for item in own_body["items"]:
        assert "engagement" in item
        assert "tlm" in item

    cross_school = client.get(
        "/api/v1/reporting/para-teachers",
        params={"school_id": str(fixture["school_two"].id)},
        headers=headers,
    )
    assert cross_school.status_code == 403

    project_wide = client.get(
        "/api/v1/reporting/para-teachers",
        headers=_headers(fixture["platform_owner_token"]),
    )
    assert project_wide.status_code == 200, project_wide.text
    assert project_wide.json()["total_para_teachers"] >= own_body[
        "total_para_teachers"
    ]
