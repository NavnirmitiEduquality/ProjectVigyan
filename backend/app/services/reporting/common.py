from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.models import AcademicYear, ClassDivision, School, TeachingSession


@dataclass(frozen=True)
class ReportingFilters:
    authorized_school_ids: set[UUID] | None
    academic_year_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    school_id: UUID | None = None
    class_division_id: UUID | None = None
    para_teacher_id: UUID | None = None


def apply_session_filters(
    db: Session,
    query: Query,
    filters: ReportingFilters,
    *,
    date_column=TeachingSession.session_date,
) -> Query:
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
    if filters.para_teacher_id is not None:
        query = query.filter(
            TeachingSession.para_teacher_id == filters.para_teacher_id
        )
    if filters.start_date is not None:
        query = query.filter(date_column >= filters.start_date)
    if filters.end_date is not None:
        query = query.filter(date_column <= filters.end_date)
    if filters.academic_year_id is not None:
        academic_year = db.get(AcademicYear, filters.academic_year_id)
        if academic_year is None:
            raise ValueError("Academic year not found.")
        query = query.filter(
            date_column >= academic_year.start_date,
            date_column <= academic_year.end_date,
        )
    return query


def production_session_query(db: Session):
    return (
        db.query(TeachingSession)
        .join(ClassDivision, ClassDivision.id == TeachingSession.class_division_id)
        .join(School, School.id == ClassDivision.school_id)
        .filter(
            TeachingSession.data_origin == "PRODUCTION",
            ClassDivision.data_origin == "PRODUCTION",
            School.data_origin == "PRODUCTION",
        )
    )


def validate_date_range(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
