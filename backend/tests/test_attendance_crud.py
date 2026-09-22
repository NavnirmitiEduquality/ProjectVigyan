import os
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Student

load_dotenv()

DEMO_PASSWORD = os.getenv("DEMO_USER_PASSWORD")

if not DEMO_PASSWORD:
    raise RuntimeError(
        "DEMO_USER_PASSWORD must be configured in .env "
        "before running attendance CRUD tests."
    )

client = TestClient(app)


PARA_TEACHERS = {
    "PT001": {
        "email": "pt001@demo.vigyan.com",
        "school_code": "PVS",
    },
    "PT002": {
        "email": "pt002@demo.vigyan.com",
        "school_code": "NLS",
    },
    "PT003": {
        "email": "pt003@demo.vigyan.com",
        "school_code": "SHY",
    },
    "PT004": {
        "email": "pt004@demo.vigyan.com",
        "school_code": "UECL",
    },
}


DATA_MANAGER = "dm001@demo.vigyan.com"


def login(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": DEMO_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text

    return response.json()["session_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def get_first_class_division(token: str) -> dict:
    response = client.get(
        "/api/v1/class-divisions",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    divisions = response.json()

    assert divisions

    return divisions[0]


def get_active_students(class_division_id: str):
    db = SessionLocal()

    try:
        students = (
            db.query(Student)
            .filter(
                Student.class_division_id
                == class_division_id,
                Student.status == "ACTIVE",
            )
            .order_by(Student.roll_no)
            .all()
        )

        return [
            {
                "id": str(student.id),
                "roll_no": student.roll_no,
                "full_name": student.full_name,
            }
            for student in students
        ]

    finally:
        db.close()


def create_in_progress_session(token: str) -> tuple[str, str]:
    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
        },
    )

    assert create_response.status_code == 201, (
        create_response.text
    )

    session_id = create_response.json()["id"]

    start_response = client.post(
        f"/api/v1/sessions/{session_id}/start",
        headers=auth_headers(token),
    )

    assert start_response.status_code == 200, (
        start_response.text
    )

    assert start_response.json()["status"] == "IN_PROGRESS"

    return session_id, class_division["id"]


def test_get_attendance_requires_authentication():
    response = client.get(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000/"
        "attendance"
    )

    assert response.status_code == 401


def test_post_attendance_requires_authentication():
    response = client.post(
        "/api/v1/sessions/"
        "00000000-0000-0000-0000-000000000000/"
        "attendance",
        json={
            "records": [],
        },
    )

    assert response.status_code == 401


def test_para_teacher_can_submit_complete_attendance_sheet():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert students, (
        "Demo class division must contain active students."
    )

    records = [
        {
            "student_id": student["id"],
            "status": (
                "PRESENT"
                if index % 2 == 0
                else "ABSENT"
            ),
        }
        for index, student in enumerate(students)
    ]

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={
            "records": records,
        },
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["session_id"] == session_id

    assert len(data["records"]) == len(students)

    total_students = len(students)
    present = sum(
        1
        for record in records
        if record["status"] == "PRESENT"
    )
    absent = total_students - present

    assert data["summary"]["total_students"] == total_students
    assert data["summary"]["present"] == present
    assert data["summary"]["absent"] == absent

    expected_percentage = round(
        (present / total_students) * 100,
        2,
    )

    assert (
        data["summary"]["attendance_percentage"]
        == expected_percentage
    )


def test_para_teacher_can_get_submitted_attendance():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert students

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    post_response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={
            "records": records,
        },
    )

    assert post_response.status_code == 200, (
        post_response.text
    )

    response = client.get(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["session_id"] == session_id
    assert len(data["records"]) == len(students)

    assert data["summary"] == {
        "total_students": len(students),
        "present": len(students),
        "absent": 0,
        "attendance_percentage": 100.0,
    }

def test_attendance_rejects_missing_student():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert len(students) >= 2

    records = [
        {
            "student_id": students[0]["id"],
            "status": "PRESENT",
        }
    ]

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": records},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Attendance must be submitted for every "
        "active student in the class."
    )


def test_attendance_rejects_extra_student():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert students

    fake_student_id = (
        "00000000-0000-0000-0000-000000000001"
    )

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    records.append(
        {
            "student_id": fake_student_id,
            "status": "ABSENT",
        }
    )

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": records},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Attendance contains students who are not "
        "active students of this session's class."
    )


def test_attendance_rejects_duplicate_student():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert len(students) >= 2

    records = [
        {
            "student_id": students[0]["id"],
            "status": "PRESENT",
        },
        {
            "student_id": students[0]["id"],
            "status": "ABSENT",
        },
    ]

    for student in students[1:]:
        records.append(
            {
                "student_id": student["id"],
                "status": "PRESENT",
            }
        )

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": records},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Duplicate student IDs are not allowed."
    )


def test_attendance_rejects_wrong_class_student():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(pt001_token)
    )

    pt001_students = get_active_students(
        class_division_id
    )

    pt002_division = get_first_class_division(
        pt002_token
    )

    pt002_students = get_active_students(
        pt002_division["id"]
    )

    assert pt001_students
    assert pt002_students

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in pt001_students
    ]

    # Replace one valid student with a student
    # from another school/class.
    records[0] = {
        "student_id": pt002_students[0]["id"],
        "status": "PRESENT",
    }

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(pt001_token),
        json={"records": records},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Attendance must be submitted for every "
        "active student in the class."
    )


def test_attendance_rejects_inactive_student():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert students

    db = SessionLocal()

    try:
        student = (
            db.query(Student)
            .filter(
                Student.id == students[0]["id"]
            )
            .first()
        )

        assert student is not None

        student.status = "INACTIVE"
        db.commit()

    finally:
        db.close()

    try:
        records = [
            {
                "student_id": student_data["id"],
                "status": "PRESENT",
            }
            for student_data in students
        ]

        response = client.post(
            f"/api/v1/sessions/{session_id}/attendance",
            headers=auth_headers(token),
            json={"records": records},
        )

        assert response.status_code == 400

        assert response.json()["detail"] == (
            "Attendance contains students who are not "
            "active students of this session's class."
        )

    finally:
        db = SessionLocal()

        try:
            student = (
                db.query(Student)
                .filter(
                    Student.id == students[0]["id"]
                )
                .first()
            )

            if student:
                student.status = "ACTIVE"
                db.commit()

        finally:
            db.close()

def test_attendance_rejected_for_planned_session():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    students = get_active_students(
        class_division["id"]
    )

    assert students

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": records},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Attendance can only be submitted while "
        "the session is IN_PROGRESS."
    )


def test_attendance_rejected_for_completed_session():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    complete_response = client.post(
        f"/api/v1/sessions/{session_id}/complete",
        headers=auth_headers(token),
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "COMPLETED"

    students = get_active_students(class_division_id)

    assert students

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": records},
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "Attendance can only be submitted while "
        "the session is IN_PROGRESS."
    )


def test_attendance_rejected_for_cancelled_session():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    class_division = get_first_class_division(token)

    create_response = client.post(
        "/api/v1/sessions",
        headers=auth_headers(token),
        json={
            "class_division_id": class_division["id"],
            "session_date": "2026-09-22",
        },
    )

    assert create_response.status_code == 201

    session_id = create_response.json()["id"]

    # Cancellation endpoint is not implemented yet.
    # This test will be enabled when the session cancellation
    # workflow is added.
    pytest.skip(
        "Session cancellation endpoint is not implemented yet."
    )

def test_para_teacher_cannot_view_another_school_attendance():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    session_id, _ = create_in_progress_session(
        pt002_token
    )

    response = client.get(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(pt001_token),
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_para_teacher_cannot_submit_attendance_for_another_school():
    pt001_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    pt002_token = login(
        PARA_TEACHERS["PT002"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(pt002_token)
    )

    students = get_active_students(class_division_id)

    assert students

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(pt001_token),
        json={"records": records},
    )

    assert response.status_code == 403

    assert response.json()["detail"] == (
        "You are not authorized to access this school."
    )


def test_data_manager_can_view_project_attendance():
    para_teacher_token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(
            para_teacher_token
        )
    )

    students = get_active_students(class_division_id)

    assert students

    records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    post_response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(para_teacher_token),
        json={"records": records},
    )

    assert post_response.status_code == 200

    data_manager_token = login(DATA_MANAGER)

    response = client.get(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(data_manager_token),
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["session_id"] == session_id
    assert data["summary"]["total_students"] == len(
        students
    )


def test_attendance_submission_replaces_existing_sheet():
    token = login(
        PARA_TEACHERS["PT001"]["email"]
    )

    session_id, class_division_id = (
        create_in_progress_session(token)
    )

    students = get_active_students(class_division_id)

    assert len(students) >= 2

    first_records = [
        {
            "student_id": student["id"],
            "status": "PRESENT",
        }
        for student in students
    ]

    first_response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": first_records},
    )

    assert first_response.status_code == 200

    second_records = [
        {
            "student_id": student["id"],
            "status": (
                "ABSENT"
                if index == 0
                else "PRESENT"
            ),
        }
        for index, student in enumerate(students)
    ]

    second_response = client.post(
        f"/api/v1/sessions/{session_id}/attendance",
        headers=auth_headers(token),
        json={"records": second_records},
    )

    assert second_response.status_code == 200

    data = second_response.json()

    assert len(data["records"]) == len(students)
    assert data["summary"]["total_students"] == len(
        students
    )
    assert data["summary"]["present"] == len(students) - 1
    assert data["summary"]["absent"] == 1

    first_student_record = next(
        record
        for record in data["records"]
        if record["student_id"] == students[0]["id"]
    )

    assert first_student_record["status"] == "ABSENT"
