import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    require_permission,
    require_school_access,
)
from app.models import SessionAttendance, Student, TeachingSession, User


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Attendance"],
)


class AttendanceRecordInput(BaseModel):
    student_id: uuid.UUID
    status: Literal["PRESENT", "ABSENT"]


class AttendanceSheetInput(BaseModel):
    records: list[AttendanceRecordInput] = Field(default_factory=list)


class AttendanceRecordResponse(BaseModel):
    student_id: uuid.UUID
    status: Literal["PRESENT", "ABSENT"]


class AttendanceSummary(BaseModel):
    total_students: int
    present: int
    absent: int
    attendance_percentage: float


class AttendanceResponse(BaseModel):
    session_id: uuid.UUID
    records: list[AttendanceRecordResponse]
    summary: AttendanceSummary


def _get_session(
    session_id: uuid.UUID,
    current_user: User,
    db: Session,
) -> TeachingSession:
    teaching_session = (
        db.query(TeachingSession)
        .filter(TeachingSession.id == session_id)
        .first()
    )

    if not teaching_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teaching session not found.",
        )

    school_id = teaching_session.class_division.school_id

    require_school_access(
        school_id,
        current_user,
        db,
    )

    return teaching_session


def _build_response(
    teaching_session: TeachingSession,
    db: Session,
) -> AttendanceResponse:
    students = (
        db.query(Student)
        .filter(
            Student.class_division_id
            == teaching_session.class_division_id,
            Student.status == "ACTIVE",
        )
        .order_by(Student.roll_no)
        .all()
    )

    attendance_records = (
        db.query(SessionAttendance)
        .filter(
            SessionAttendance.teaching_session_id
            == teaching_session.id
        )
        .all()
    )

    attendance_by_student = {
        record.student_id: record.status
        for record in attendance_records
    }

    records = [
        AttendanceRecordResponse(
            student_id=student.id,
            status=attendance_by_student[student.id],
        )
        for student in students
        if student.id in attendance_by_student
    ]

    present = sum(
        1 for record in records if record.status == "PRESENT"
    )
    absent = sum(
        1 for record in records if record.status == "ABSENT"
    )
    total_students = len(students)

    percentage = (
        round((present / total_students) * 100, 2)
        if total_students
        else 0.0
    )

    return AttendanceResponse(
        session_id=teaching_session.id,
        records=records,
        summary=AttendanceSummary(
            total_students=total_students,
            present=present,
            absent=absent,
            attendance_percentage=percentage,
        ),
    )


@router.get(
    "/{session_id}/attendance",
    response_model=AttendanceResponse,
)
def get_attendance(
    session_id: uuid.UUID,
    current_user: User = Depends(
        require_permission("attendance.view")
    ),
    db: Session = Depends(get_db),
):
    teaching_session = _get_session(
        session_id,
        current_user,
        db,
    )

    return _build_response(
        teaching_session,
        db,
    )


@router.post(
    "/{session_id}/attendance",
    response_model=AttendanceResponse,
)
def save_attendance(
    session_id: uuid.UUID,
    payload: AttendanceSheetInput,
    current_user: User = Depends(
        require_permission("attendance.create")
    ),
    db: Session = Depends(get_db),
):
    teaching_session = _get_session(
        session_id,
        current_user,
        db,
    )

    if teaching_session.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Attendance can only be submitted while "
                "the session is IN_PROGRESS."
            ),
        )

    students = (
        db.query(Student)
        .filter(
            Student.class_division_id
            == teaching_session.class_division_id,
            Student.status == "ACTIVE",
        )
        .order_by(Student.roll_no)
        .all()
    )

    expected_student_ids = {
        student.id
        for student in students
    }

    submitted_student_ids = [
        record.student_id
        for record in payload.records
    ]

    submitted_student_id_set = set(submitted_student_ids)

    # Duplicate student IDs.
    if len(submitted_student_ids) != len(
        submitted_student_id_set
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate student IDs are not allowed.",
        )

    # Missing students.
    missing_student_ids = (
        expected_student_ids - submitted_student_id_set
    )

    if missing_student_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Attendance must be submitted for every "
                "active student in the class."
            ),
        )

    # Extra / wrong-class / inactive students.
    extra_student_ids = (
        submitted_student_id_set - expected_student_ids
    )

    if extra_student_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Attendance contains students who are not "
                "active students of this session's class."
            ),
        )

    # Replace the current attendance sheet atomically.
    db.query(SessionAttendance).filter(
        SessionAttendance.teaching_session_id
        == teaching_session.id
    ).delete(
        synchronize_session=False
    )

    for record in payload.records:
        db.add(
            SessionAttendance(
                teaching_session_id=teaching_session.id,
                student_id=record.student_id,
                status=record.status,
                data_origin="PRODUCTION",
            )
        )

    db.commit()

    return _build_response(
        teaching_session,
        db,
    )
