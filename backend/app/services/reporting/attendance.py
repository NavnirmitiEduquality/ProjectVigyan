from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import (
    AcademicYear,
    ClassDivision,
    School,
    SessionAttendance,
    Student,
    TeachingSession,
)


@dataclass(frozen=True)
class AttendanceFilter:
    authorized_school_ids: set[UUID] | None
    academic_year_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    school_id: UUID | None = None
    class_division_id: UUID | None = None
    student_id: UUID | None = None
    student_ids: set[UUID] | None = None


def _base_query(db: Session, filters: AttendanceFilter):
    query = (
        db.query(
            SessionAttendance.status,
            TeachingSession.session_date,
            TeachingSession.class_division_id,
            ClassDivision.class_level,
            ClassDivision.division,
            ClassDivision.school_id,
            School.school_code,
            School.school_name,
            SessionAttendance.student_id,
            Student.student_code,
            Student.full_name,
        )
        .join(
            TeachingSession,
            TeachingSession.id == SessionAttendance.teaching_session_id,
        )
        .join(
            ClassDivision,
            ClassDivision.id == TeachingSession.class_division_id,
        )
        .join(School, School.id == ClassDivision.school_id)
        .join(Student, Student.id == SessionAttendance.student_id)
        .filter(
            SessionAttendance.data_origin == "PRODUCTION",
            TeachingSession.data_origin == "PRODUCTION",
            ClassDivision.data_origin == "PRODUCTION",
            School.data_origin == "PRODUCTION",
            Student.data_origin == "PRODUCTION",
        )
    )

    if filters.authorized_school_ids is not None:
        query = query.filter(
            ClassDivision.school_id.in_(filters.authorized_school_ids)
        )
    if filters.school_id is not None:
        query = query.filter(ClassDivision.school_id == filters.school_id)
    if filters.class_division_id is not None:
        query = query.filter(
            TeachingSession.class_division_id == filters.class_division_id
        )
    if filters.student_id is not None:
        query = query.filter(SessionAttendance.student_id == filters.student_id)
    if filters.student_ids is not None:
        query = query.filter(SessionAttendance.student_id.in_(filters.student_ids))
    if filters.start_date is not None:
        query = query.filter(TeachingSession.session_date >= filters.start_date)
    if filters.end_date is not None:
        query = query.filter(TeachingSession.session_date <= filters.end_date)
    if filters.academic_year_id is not None:
        academic_year = (
            db.query(AcademicYear)
            .filter(AcademicYear.id == filters.academic_year_id)
            .one_or_none()
        )
        if academic_year is None:
            raise ValueError("Academic year not found.")
        query = query.filter(
            TeachingSession.session_date >= academic_year.start_date,
            TeachingSession.session_date <= academic_year.end_date,
        )

    return query


def _summary_query(query):
    eligible = func.count()
    present = func.sum(
        case((SessionAttendance.status == "PRESENT", 1), else_=0)
    )
    absent = func.sum(
        case((SessionAttendance.status == "ABSENT", 1), else_=0)
    )
    return query.with_entities(
        eligible.label("eligible_record_count"),
        present.label("present_record_count"),
        absent.label("absent_record_count"),
    )


def _summary(row) -> dict[str, int | float]:
    eligible = int(row.eligible_record_count or 0)
    present = int(row.present_record_count or 0)
    absent = int(row.absent_record_count or 0)
    percentage = round((present / eligible) * 100, 2) if eligible else 0.0
    return {
        "eligible_record_count": eligible,
        "present_record_count": present,
        "absent_record_count": absent,
        "attendance_percentage": percentage,
    }


def get_attendance_summary(
    db: Session,
    filters: AttendanceFilter,
) -> dict[str, int | float]:
    """Calculate one record-weighted attendance summary."""
    row = _summary_query(_base_query(db, filters)).one()
    return _summary(row)


def get_attendance_groups(
    db: Session,
    filters: AttendanceFilter,
    group_by: str,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[dict], int]:
    """Calculate record-weighted attendance for one supported dimension."""
    query = _base_query(db, filters)
    if group_by == "project":
        return [_group_item("PROJECT", None, get_attendance_summary(db, filters))], 1

    if group_by == "school":
        group_columns = (
            ClassDivision.school_id.label("school_id"),
            School.school_code.label("school_code"),
            School.school_name.label("school_name"),
        )
    elif group_by == "class_division":
        group_columns = (
            ClassDivision.id.label("class_division_id"),
            ClassDivision.school_id.label("school_id"),
            ClassDivision.class_level.label("class_level"),
            ClassDivision.division.label("division"),
        )
    elif group_by == "student":
        group_columns = (
            Student.id.label("student_id"),
            Student.student_code.label("student_code"),
            Student.full_name.label("student_name"),
            ClassDivision.id.label("class_division_id"),
            ClassDivision.school_id.label("school_id"),
            ClassDivision.class_level.label("class_level"),
            ClassDivision.division.label("division"),
        )
    else:
        raise ValueError("Unsupported attendance grouping.")

    aggregate = (
        query.with_entities(
            *group_columns,
            func.count().label("eligible_record_count"),
            func.sum(
                case((SessionAttendance.status == "PRESENT", 1), else_=0)
            ).label("present_record_count"),
            func.sum(
                case((SessionAttendance.status == "ABSENT", 1), else_=0)
            ).label("absent_record_count"),
        )
        .group_by(*group_columns)
    )
    total = aggregate.count()
    rows = aggregate.order_by(*group_columns).offset(offset).limit(limit).all()

    items = []
    for row in rows:
        values = row._mapping
        metric = _summary(row)
        if group_by == "school":
            item = {
                "group_id": values["school_id"],
                "school_id": values["school_id"],
                "school_code": values["school_code"],
                "school_name": values["school_name"],
            }
        elif group_by == "class_division":
            item = {
                "group_id": values["class_division_id"],
                "school_id": values["school_id"],
                "class_division_id": values["class_division_id"],
                "class_level": values["class_level"],
                "division": values["division"],
            }
        else:
            item = {
                "group_id": values["student_id"],
                "student_id": values["student_id"],
                "student_code": values["student_code"],
                "student_name": values["student_name"],
                "school_id": values["school_id"],
                "class_division_id": values["class_division_id"],
                "class_level": values["class_level"],
                "division": values["division"],
            }
        item.update(metric)
        items.append(item)
    return items, total


def _group_item(group_type: str, group_id, metric: dict) -> dict:
    return {"group_type": group_type, "group_id": group_id, **metric}
