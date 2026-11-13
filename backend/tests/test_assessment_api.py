from datetime import date
from decimal import Decimal
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
    Student,
    User,
    UserAssignment,
    UserRole,
)
from app.services.auth_service import hash_password


client = TestClient(app)
TEST_PASSWORD = "AssessmentTestPassword!2026"


@pytest.fixture
def assessment_api_setup():
    db = SessionLocal()
    suffix = uuid4().hex[:10]
    school = School(
        school_code=f"AA-S-{suffix}",
        school_name="Assessment API School",
        status="ACTIVE",
        data_origin="TEST",
    )
    other_school = School(
        school_code=f"AA-O-{suffix}",
        school_name="Assessment API Other School",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([school, other_school])
    db.flush()
    division = ClassDivision(
        school_id=school.id,
        class_level=5,
        division="A",
        status="ACTIVE",
        data_origin="TEST",
    )
    other_division = ClassDivision(
        school_id=other_school.id,
        class_level=5,
        division="A",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([division, other_division])
    db.flush()
    student = Student(
        student_code=f"AA-ST-{suffix}",
        full_name="Assessment API Student",
        gender="OTHER",
        roll_no=1,
        class_division_id=division.id,
        status="ACTIVE",
        data_origin="PRODUCTION",
    )
    second_student = Student(
        student_code=f"AA-S2-{suffix}",
        full_name="Assessment API Second Student",
        gender="OTHER",
        roll_no=2,
        class_division_id=division.id,
        status="ACTIVE",
        data_origin="PRODUCTION",
    )
    other_student = Student(
        student_code=f"AA-OS-{suffix}",
        full_name="Assessment API Other Student",
        gender="OTHER",
        roll_no=1,
        class_division_id=other_division.id,
        status="ACTIVE",
        data_origin="TEST",
    )
    year = AcademicYear(
        name=f"AA-{suffix}",
        start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31),
        data_origin="TEST",
    )
    manager_role = Role(
        name=f"Assessment Manager {suffix}",
        code=f"ASSESSMENT_MANAGER_{suffix.upper()}",
        description="Synthetic assessment API test role.",
        is_system_role=False,
    )
    viewer_role = Role(
        name=f"Assessment Viewer {suffix}",
        code=f"ASSESSMENT_VIEWER_{suffix.upper()}",
        description="Synthetic assessment API test role.",
        is_system_role=False,
    )
    manager = User(
        user_code=f"AA-M-{suffix}",
        full_name="Assessment API Manager",
        email=f"assessment-manager-{suffix}@example.com",
        password_hash=hash_password(TEST_PASSWORD),
        status="ACTIVE",
        data_origin="TEST",
    )
    viewer = User(
        user_code=f"AA-V-{suffix}",
        full_name="Assessment API Viewer",
        email=f"assessment-viewer-{suffix}@example.com",
        password_hash=hash_password(TEST_PASSWORD),
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([
        student,
        second_student,
        other_student,
        year,
        manager_role,
        viewer_role,
        manager,
        viewer,
    ])
    db.flush()

    required_codes = {
        "assessment.view": "View Assessments",
        "assessment.import": "Import Assessments",
        "assessment.update": "Update Assessments",
        "assessment.submit": "Submit Assessments",
    }
    permissions = {}
    for code, name in required_codes.items():
        permission = db.query(Permission).filter(Permission.code == code).first()
        if permission is None:
            permission = Permission(name=name, code=code, module="assessment")
            db.add(permission)
            db.flush()
        permissions[code] = permission
    db.add_all([
        *[
            RolePermission(role_id=manager_role.id, permission_id=permission.id)
            for permission in permissions.values()
        ],
        RolePermission(
            role_id=viewer_role.id,
            permission_id=permissions["assessment.view"].id,
        ),
        UserRole(user_id=manager.id, role_id=manager_role.id, is_active=True),
        UserRole(user_id=viewer.id, role_id=viewer_role.id, is_active=True),
        UserAssignment(
            user_id=manager.id,
            scope_type="SCHOOL",
            school_id=school.id,
            start_date=date(2026, 1, 1),
            is_active=True,
        ),
        UserAssignment(
            user_id=viewer.id,
            scope_type="SCHOOL",
            school_id=school.id,
            start_date=date(2026, 1, 1),
            is_active=True,
        ),
    ])
    db.commit()
    context = {
        "db": db,
        "school": school,
        "other_school": other_school,
        "division": division,
        "other_division": other_division,
        "student": student,
        "student_code": student.student_code,
        "second_student": second_student,
        "other_student": other_student,
        "year": year,
        "manager": manager,
        "viewer": viewer,
        "manager_role": manager_role,
        "viewer_role": viewer_role,
    }
    try:
        yield context
    finally:
        db.rollback()
        assessment_ids = [
            item.id for item in db.query(Assessment).filter(
                Assessment.academic_year_id == year.id
            ).all()
        ]
        if assessment_ids:
            db.query(AssessmentResult).filter(
                AssessmentResult.assessment_id.in_(assessment_ids)
            ).delete(synchronize_session=False)
            db.query(AssessmentImport).filter(
                AssessmentImport.assessment_id.in_(assessment_ids)
            ).delete(synchronize_session=False)
            db.query(Assessment).filter(
                Assessment.id.in_(assessment_ids)
            ).delete(synchronize_session=False)
        db.query(AuthSession).filter(
            AuthSession.user_id.in_([manager.id, viewer.id])
        ).delete(synchronize_session=False)
        db.query(UserRole).filter(
            UserRole.user_id.in_([manager.id, viewer.id])
        ).delete(synchronize_session=False)
        db.query(RolePermission).filter(
            RolePermission.role_id.in_([manager_role.id, viewer_role.id])
        ).delete(synchronize_session=False)
        db.delete(manager)
        db.delete(viewer)
        db.delete(manager_role)
        db.delete(viewer_role)
        db.delete(year)
        db.query(Student).filter(
            Student.class_division_id == division.id,
            Student.data_origin == "PRODUCTION",
            Student.student_code.like("AA-PROD-%"),
        ).delete(synchronize_session=False)
        db.delete(student)
        db.delete(second_student)
        db.delete(other_student)
        db.delete(division)
        db.delete(other_division)
        db.delete(school)
        db.delete(other_school)
        db.commit()
        db.close()


def login(user: User) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_assessment(context, token: str, school_id=None, *, configure_scope=True):
    response = client.post(
        "/api/v1/assessments",
        headers=headers(token),
        json={
            "academic_year_id": str(context["year"].id),
            "school_id": str(school_id or context["school"].id),
            "assessment_type": "BASELINE",
            "maximum_marks": "20",
        },
    )
    if (
        configure_scope
        and response.status_code == 201
        and (school_id is None or school_id == context["school"].id)
    ):
        scope_response = set_assessment_scope(context, token, response.json()["id"])
        assert scope_response.status_code == 200, scope_response.text
    return response


def set_assessment_scope(context, token, assessment_id, division_ids=None):
    response = client.put(
        f"/api/v1/assessments/{assessment_id}/scope",
        headers=headers(token),
        json={
            "class_division_ids": [
                str(item)
                for item in (
                    division_ids
                    if division_ids is not None
                    else [context["division"].id]
                )
            ]
        },
    )
    return response


def import_rows(context, token, assessment_id, rows):
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/imports",
        headers=headers(token),
        json={"rows": rows},
    )
    return response


def standard_row(context, student, marks="10"):
    return {
        "student_business_id": student.student_code,
        "class": "5",
        "division": "A",
        "aggregate_marks": marks,
    }


def add_production_roster_student(context):
    student = Student(
        student_code=f"AA-PROD-{uuid4().hex[:10]}",
        full_name="Production Roster Student",
        gender="OTHER",
        roll_no=3,
        class_division_id=context["division"].id,
        status="ACTIVE",
        data_origin="PRODUCTION",
    )
    context["db"].add(student)
    context["db"].flush()
    return student


def test_unauthenticated_and_read_only_access(assessment_api_setup):
    context = assessment_api_setup
    assert client.get("/api/v1/assessments").status_code == 401
    viewer_token = login(context["viewer"])
    assert client.get(
        "/api/v1/assessments",
        headers=headers(viewer_token),
    ).status_code == 200
    assert create_assessment(context, viewer_token).status_code == 403


def test_manager_workflow_corrects_missing_student_and_locks(
    assessment_api_setup,
):
    context = assessment_api_setup
    production_student = add_production_roster_student(context)
    context["db"].commit()
    token = login(context["manager"])
    viewer_token = login(context["viewer"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    assert client.get(
        "/api/v1/assessments",
        headers=headers(viewer_token),
    ).status_code == 200

    assert client.get(
        f"/api/v1/assessments/{assessment_id}",
        headers=headers(viewer_token),
    ).status_code == 200

    duplicate = create_assessment(context, token)
    assert duplicate.status_code == 400

    imported = import_rows(
        context,
        token,
        assessment_id,
        [
            standard_row(context, context["student"], "15"),
            standard_row(context, context["second_student"], "14"),
            {
                "student_business_id": "UNKNOWN-MISSING-STUDENT",
                "class": "5",
                "division": "A",
                "aggregate_marks": "12",
            },
        ],
    )
    assert imported.status_code == 201, imported.text

    assert client.post(
        f"/api/v1/assessments/{assessment_id}/imports",
        headers=headers(viewer_token),
        json={"rows": []},
    ).status_code == 403

    missing_row = next(
        row for row in imported.json()["rows"]
        if row["student_business_id"] == production_student.student_code
    )
    assert missing_row["validation_status"] == "ERROR"
    assert missing_row["is_mapped"] is False

    correction_row = next(
        row for row in imported.json()["rows"]
        if row["student_business_id"] == "UNKNOWN-MISSING-STUDENT"
    )
    assert correction_row["validation_status"] == "WARNING"

    blocked = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )
    assert blocked.status_code == 400

    acknowledge = client.patch(
        f"/api/v1/assessments/imports/rows/{missing_row['id']}/acknowledge",
        headers=headers(token),
    )
    assert acknowledge.status_code == 400

    corrected = client.patch(
        f"/api/v1/assessments/imports/rows/{correction_row['id']}/business-id",
        headers=headers(token),
        json={"student_business_id": production_student.student_code},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["student_id"] == str(production_student.id)
    assert corrected.json()["is_mapped"] is True

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"

    results = client.get(
        f"/api/v1/assessments/{assessment_id}/results",
        headers=headers(viewer_token),
    )
    assert results.status_code == 200
    assert len(results.json()) == 3

    locked_import = client.post(
        f"/api/v1/assessments/{assessment_id}/imports",
        headers=headers(token),
        json={"rows": [{
            "student_business_id": context["student_code"],
            "class": "5",
            "division": "A",
            "aggregate_marks": "1",
        }]},
    )
    assert locked_import.status_code == 409



def test_permissions_and_school_scope(assessment_api_setup):
    context = assessment_api_setup
    viewer_token = login(context["viewer"])
    manager_token = login(context["manager"])
    assert client.post(
        "/api/v1/assessments/00000000-0000-0000-0000-000000000000/submit",
        headers=headers(viewer_token),
    ).status_code == 403
    assert create_assessment(
        context,
        manager_token,
        context["other_school"].id,
    ).status_code == 403


def test_complete_roster_has_no_missing_student_warning(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [
            standard_row(context, context["student"], "10"),
            standard_row(context, context["second_student"], "12"),
        ],
    )

    assert imported.status_code == 201, imported.text

    body = imported.json()

    assert body["warning_count"] == 0
    assert body["error_count"] == 0

    assert not any(
        row["validation_message"] == "Student is missing from the import."
        for row in body["rows"]
    )


def test_partial_roster_generates_missing_student_error(assessment_api_setup):
    context = assessment_api_setup
    production_student = add_production_roster_student(context)
    context["db"].commit()
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [standard_row(context, context["student"], "10")],
    )

    assert imported.status_code == 201, imported.text

    body = imported.json()

    missing_rows = [
        row
        for row in body["rows"]
        if row["student_business_id"] == production_student.student_code
    ]

    assert len(missing_rows) == 1

    missing_row = missing_rows[0]

    assert missing_row["student_id"] is None
    assert missing_row["is_mapped"] is False
    assert missing_row["validation_status"] == "ERROR"
    assert missing_row["warning_acknowledged"] is False
    assert body["error_count"] >= 1

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )
    assert submitted.status_code == 400



def test_missing_student_error_cannot_be_acknowledged_or_submitted(
    assessment_api_setup,
):
    context = assessment_api_setup
    production_student = add_production_roster_student(context)
    context["db"].commit()
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [standard_row(context, context["student"], "10")],
    )

    assert imported.status_code == 201, imported.text

    missing_row = next(
        row
        for row in imported.json()["rows"]
        if row["student_business_id"] == production_student.student_code
    )

    assert missing_row["validation_status"] == "ERROR"

    acknowledged = client.patch(
        f"/api/v1/assessments/imports/rows/{missing_row['id']}/acknowledge",
        headers=headers(token),
    )

    assert acknowledged.status_code == 400, acknowledged.text

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )

    assert submitted.status_code == 400, submitted.text

    results = client.get(
        f"/api/v1/assessments/{assessment_id}/results",
        headers=headers(token),
    )

    assert results.status_code == 200, results.text
    assert results.json() == []



def test_unknown_student_business_id_can_be_corrected_via_api(
    assessment_api_setup,
):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [{
            "student_business_id": "UNKNOWN-API-STUDENT",
            "class": "5",
            "division": "A",
            "aggregate_marks": "10",
        }],
    )

    assert imported.status_code == 201, imported.text

    row = next(
        row for row in imported.json()["rows"]
        if row["student_business_id"] == "UNKNOWN-API-STUDENT"
    )

    assert row["is_mapped"] is False
    assert row["validation_status"] == "WARNING"

    corrected = client.patch(
        f"/api/v1/assessments/imports/rows/{row['id']}/business-id",
        headers=headers(token),
        json={"student_business_id": context["student_code"]},
    )

    assert corrected.status_code == 200, corrected.text

    body = corrected.json()
    assert body["student_business_id"] == context["student_code"]
    assert body["student_id"] == str(context["student"].id)
    assert body["is_mapped"] is True
    assert body["validation_status"] == "VALID"
    assert body["validation_message"] is None


def test_manual_mapping_rejects_business_id_mismatch(
    assessment_api_setup,
):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [{
            "student_business_id": "UNKNOWN-API-STUDENT",
            "class": "5",
            "division": "A",
            "aggregate_marks": "10",
        }],
    )

    assert imported.status_code == 201, imported.text

    row = next(
        row for row in imported.json()["rows"]
        if row["student_business_id"] == "UNKNOWN-API-STUDENT"
    )

    mapped = client.patch(
        f"/api/v1/assessments/imports/rows/{row['id']}/mapping",
        headers=headers(token),
        json={
            "student_id": str(context["student"].id),
            "acknowledge_warning": True,
        },
    )

    assert mapped.status_code == 400
    assert "does not match" in mapped.json()["detail"]



def test_exact_business_id_with_missing_marks_cannot_submit(
    assessment_api_setup,
):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [{
            "student_business_id": context["student_code"],
            "class": "5",
            "division": "A",
        }],
    )

    assert imported.status_code == 201, imported.text

    row = next(
        row
        for row in imported.json()["rows"]
        if row["student_business_id"] == context["student_code"]
    )

    assert row["aggregate_marks"] is None
    assert row["validation_status"] == "ERROR"
    assert row["validation_message"] == "aggregate_marks is required."

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )

    assert submitted.status_code == 400



def test_marks_above_maximum_are_rejected_by_api(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [
            {
                "student_business_id": context["student_code"],
                "class": "5",
                "division": "A",
                "aggregate_marks": "21",
            },
        ],
    )

    assert imported.status_code == 201, imported.text

    body = imported.json()

    assert body["error_count"] >= 1

    row = body["rows"][0]

    assert row["validation_status"] == "ERROR"
    assert row["validation_message"] == (
        "aggregate_marks cannot exceed maximum_marks."
    )

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )

    assert submitted.status_code == 400


def test_duplicate_student_business_ids_are_rejected_by_api(
    assessment_api_setup,
):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [
            standard_row(context, context["student"], "10"),
            standard_row(context, context["student"], "12"),
            standard_row(context, context["second_student"], "11"),
        ],
    )

    assert imported.status_code == 201, imported.text

    body = imported.json()
    duplicate_rows = [
        row
        for row in body["rows"]
        if row["student_business_id"] == context["student_code"]
    ]

    assert len(duplicate_rows) == 2
    assert any(
        row["validation_status"] == "ERROR"
        for row in duplicate_rows
    )
    assert body["error_count"] >= 1

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )

    assert submitted.status_code == 400



def test_viewer_cannot_acknowledge_update_or_map(
    assessment_api_setup,
):
    context = assessment_api_setup
    manager_token = login(context["manager"])
    viewer_token = login(context["viewer"])

    created = create_assessment(context, manager_token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        manager_token,
        assessment_id,
        [
            {
                "student_business_id": "UNKNOWN-VIEWER-TEST",
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    assert imported.status_code == 201, imported.text

    row = imported.json()["rows"][0]

    acknowledge = client.patch(
        f"/api/v1/assessments/imports/rows/{row['id']}/acknowledge",
        headers=headers(viewer_token),
    )
    assert acknowledge.status_code == 403

    marks = client.patch(
        f"/api/v1/assessments/imports/rows/{row['id']}/marks",
        headers=headers(viewer_token),
        json={"aggregate_marks": "5"},
    )
    assert marks.status_code == 403

    mapping = client.patch(
        f"/api/v1/assessments/imports/rows/{row['id']}/mapping",
        headers=headers(viewer_token),
        json={
            "student_id": str(context["student"].id),
            "acknowledge_warning": True,
        },
    )
    assert mapping.status_code == 403


def test_results_are_school_scoped(
    assessment_api_setup,
):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [
            standard_row(context, context["student"], "10"),
            standard_row(context, context["second_student"], "12"),
        ],
    )

    assert imported.status_code == 201, imported.text

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )

    assert submitted.status_code == 200, submitted.text

    results = client.get(
        f"/api/v1/assessments/{assessment_id}/results",
        headers=headers(token),
    )

    assert results.status_code == 200

    result_student_ids = {
        result["student_id"]
        for result in results.json()
    }

    assert result_student_ids == {
        str(context["student"].id),
        str(context["second_student"].id),
    }


def test_import_with_missing_marks_cannot_submit(
    assessment_api_setup,
):
    context = assessment_api_setup
    token = login(context["manager"])

    created = create_assessment(context, token)
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    imported = import_rows(
        context,
        token,
        assessment_id,
        [
            {
                "student_business_id": context["student_code"],
                "class": "5",
                "division": "A",
                # Deliberately omitted.
            },
        ],
    )

    assert imported.status_code == 201, imported.text

    body = imported.json()

    row = next(
        row
        for row in body["rows"]
        if row["student_business_id"] == context["student_code"]
    )

    assert row["aggregate_marks"] is None
    assert row["validation_status"] == "ERROR"
    assert row["validation_message"] == "aggregate_marks is required."

    submitted = client.post(
        f"/api/v1/assessments/{assessment_id}/submit",
        headers=headers(token),
    )

    assert submitted.status_code == 400


def test_user_cannot_read_other_school_assessment(assessment_api_setup):
    context = assessment_api_setup
    manager_token = login(context["manager"])

    # Create assessment in authorized school.
    created = create_assessment(context, manager_token)
    assert created.status_code == 201, created.text

    assessment_id = created.json()["id"]

    # The manager is not assigned to other_school.
    #
    # We need an actual assessment in other_school, so temporarily create
    # it directly at DB level for the authorization test.
    other_assessment = Assessment(
        academic_year_id=context["year"].id,
        school_id=context["other_school"].id,
        assessment_type="BASELINE",
        sequence_no=1,
        name="Other School Assessment",
        assessment_date=date(2026, 4, 1),
        maximum_marks=20,
        data_origin="TEST",
    )

    context["db"].add(other_assessment)
    context["db"].commit()
    context["db"].refresh(other_assessment)

    response = client.get(
        f"/api/v1/assessments/{other_assessment.id}",
        headers=headers(manager_token),
    )

    assert response.status_code == 403


def test_import_requires_explicit_assessment_scope(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token, configure_scope=False)
    assert created.status_code == 201, created.text
    imported = import_rows(
        context,
        token,
        created.json()["id"],
        [standard_row(context, context["student"], "10")],
    )
    assert imported.status_code == 400, imported.text


def test_csv_import_accepts_utf8_and_bom(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token)
    assert created.status_code == 201, created.text

    csv_content = (
        "\ufeffstudent_business_id,class,division,aggregate_marks\n"
        f"{context['student_code']},5,A,10\n"
        f"{context['second_student'].student_code},5,A,12\n"
    )

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(token),
        files={"file": ("assessment.csv", csv_content.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total_rows"] == 2
    assert body["error_count"] == 0
    assert body["warning_count"] == 0
    assert {row["student_business_id"] for row in body["rows"]} == {
        context["student_code"],
        context["second_student"].student_code,
    }


@pytest.mark.parametrize(
    ("csv_content", "expected_detail"),
    [
        (
            "student_business_id,student_business_id,class,division,aggregate_marks\n"
            "A,A,5,A,10\n",
            "Duplicate CSV headers",
        ),
        (
            "student_business_id,class,aggregate_marks\n"
            "A,5,10\n",
            "Missing required headers",
        ),
        (
            "student_business_id,class,division,aggregate_marks,student_name\n"
            "A,5,A,10,Name\n",
            "Unexpected headers",
        ),
    ],
)
def test_csv_import_rejects_invalid_headers(
    assessment_api_setup, csv_content, expected_detail
):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token)
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(token),
        files={"file": ("assessment.csv", csv_content.encode(), "text/csv")},
    )

    assert response.status_code == 400
    assert expected_detail in response.json()["detail"]


def test_csv_import_rejects_malformed_row_width(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token)
    assert created.status_code == 201, created.text

    csv_content = (
        "student_business_id,class,division,aggregate_marks\n"
        f"{context['student_code']},5,A\n"
    )

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(token),
        files={"file": ("assessment.csv", csv_content.encode(), "text/csv")},
    )

    assert response.status_code == 400
    assert "Malformed CSV row at line 2" in response.json()["detail"]


def test_csv_import_rejects_file_over_5_mib(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token)
    assert created.status_code == 201, created.text

    oversized_content = b"x" * (5 * 1024 * 1024 + 1)

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(token),
        files={"file": ("assessment.csv", oversized_content, "text/csv")},
    )

    assert response.status_code == 413
    assert "5 MiB" in response.json()["detail"]


def test_viewer_cannot_upload_assessment_csv(assessment_api_setup):
    context = assessment_api_setup
    manager_token = login(context["manager"])
    viewer_token = login(context["viewer"])
    created = create_assessment(context, manager_token)
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(viewer_token),
        files={
            "file": (
                "assessment.csv",
                b"student_business_id,class,division,aggregate_marks\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("csv_content", "expected_detail"),
    [
        (b"\xff\xfe\xfa", "CSV must use UTF-8 encoding."),
        (b"", "CSV file is empty or has no header row."),
        (
            b"student_business_id,class,division,aggregate_marks\n",
            "CSV contains no data rows.",
        ),
    ],
)
def test_csv_import_rejects_invalid_encoding_or_empty_content(
    assessment_api_setup, csv_content, expected_detail
):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token)
    assert created.status_code == 201, created.text

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(token),
        files={"file": ("assessment.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


def test_csv_import_flags_duplicate_student_business_ids(assessment_api_setup):
    context = assessment_api_setup
    token = login(context["manager"])
    created = create_assessment(context, token)
    assert created.status_code == 201, created.text

    csv_content = (
        "student_business_id,class,division,aggregate_marks\n"
        f"{context['student_code']},5,A,10\n"
        f"{context['student_code']},5,A,12\n"
        f"{context['second_student'].student_code},5,A,11\n"
    )

    response = client.post(
        f"/api/v1/assessments/{created.json()['id']}/imports/csv",
        headers=headers(token),
        files={"file": ("assessment.csv", csv_content.encode(), "text/csv")},
    )

    assert response.status_code == 201, response.text
    body = response.json()

    duplicate_rows = [
        row for row in body["rows"]
        if row["student_business_id"] == context["student_code"]
    ]

    assert len(duplicate_rows) == 2
    assert any(row["validation_status"] == "ERROR" for row in duplicate_rows)
    assert body["error_count"] >= 1
