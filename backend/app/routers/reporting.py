from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    require_permission,
    require_school_access,
)
from app.models import (
    ClassDivision,
    SessionEvidence,
    Student,
    TeachingSession,
    User,
)
from app.models.academic_year import AcademicYear
from app.models.assessment import Assessment
from app.models.school import School
from app.services.reporting.attendance import (
    AttendanceFilter,
    get_attendance_groups,
    get_attendance_summary,
)
from app.services.reporting.assessment import (
    get_assessment_report,
    get_longitudinal_report,
)
from app.services.reporting.common import (
    ReportingFilters,
    production_session_query,
    validate_date_range,
    apply_session_filters,
)
from app.services.reporting.delivery import (
    get_delivery_report,
    get_delivery_trend,
)
from app.services.reporting.engagement import get_engagement_report
from app.services.reporting.exports import metadata, report_bytes
from app.services.reporting.monitoring import (
    get_para_teacher_monitoring,
    get_class_monitoring,
    get_school_monitoring,
    get_student_monitoring,
)
from app.services.reporting.tlm import get_tlm_report


router = APIRouter(
    prefix="/api/v1/reporting",
    tags=["Reporting"],
)


def _session_export_rows(db: Session, filters: ReportingFilters) -> list[dict]:
    query = apply_session_filters(
        db,
        production_session_query(db),
        filters,
    )
    return [
        {
            "session_id": session.id,
            "class_division_id": session.class_division_id,
            "para_teacher_id": session.para_teacher_id,
            "session_date": session.session_date,
            "status": session.status,
            "duration_minutes": session.duration_minutes,
        }
        for session in query.order_by(
            TeachingSession.session_date,
            TeachingSession.id,
        ).all()
    ]


def _evidence_export_rows(db: Session, filters: ReportingFilters) -> list[dict]:
    query = (
        db.query(SessionEvidence, TeachingSession, ClassDivision)
        .join(
            TeachingSession,
            TeachingSession.id == SessionEvidence.teaching_session_id,
        )
        .join(
            ClassDivision,
            ClassDivision.id == TeachingSession.class_division_id,
        )
        .join(School, School.id == ClassDivision.school_id)
        .filter(
            SessionEvidence.data_origin == "PRODUCTION",
            TeachingSession.data_origin == "PRODUCTION",
            ClassDivision.data_origin == "PRODUCTION",
            School.data_origin == "PRODUCTION",
        )
    )

    # Reuse the same school, division, teacher, date and academic-year
    # rules used by session reporting.
    session_query = apply_session_filters(
        db,
        production_session_query(db),
        filters,
    )
    filtered_session_ids = session_query.with_entities(TeachingSession.id)
    query = query.filter(
        TeachingSession.id.in_(filtered_session_ids)
    )

    return [
        {
            "evidence_id": evidence.id,
            "session_id": session.id,
            "school_id": division.school_id,
            "created_at": evidence.created_at,
            "photo_id": evidence.photo_id,
        }
        for evidence, session, division in query.order_by(
            SessionEvidence.created_at,
            SessionEvidence.id,
        ).all()
    ]


class AttendanceGroupItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    group_id: UUID | None = None
    group_type: str | None = None
    school_id: UUID | None = None
    school_code: str | None = None
    school_name: str | None = None
    class_division_id: UUID | None = None
    class_level: int | None = None
    division: str | None = None
    student_id: UUID | None = None
    student_code: str | None = None
    student_name: str | None = None
    eligible_record_count: int
    present_record_count: int
    absent_record_count: int
    attendance_percentage: float


class AttendanceReportResponse(BaseModel):
    group_by: Literal["project", "school", "class_division", "student"]
    items: list[AttendanceGroupItem]
    total_groups: int
    offset: int
    limit: int


@router.get(
    "/attendance",
    response_model=AttendanceReportResponse,
)
def get_attendance_report(
    group_by: Literal["project", "school", "class_division", "student"] = Query(
        "project"
    ),
    academic_year_id: UUID | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    school_id: UUID | None = Query(None),
    class_division_id: UUID | None = Query(None),
    student_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date.",
        )

    authorized_school_ids = get_authorized_school_ids(current_user, db)
    if school_id is not None:
        require_school_access(school_id, current_user, db)

    if class_division_id is not None:
        division = (
            db.query(ClassDivision)
            .filter(ClassDivision.id == class_division_id)
            .one_or_none()
        )
        if division is None:
            raise HTTPException(status_code=404, detail="Class division not found.")
        require_school_access(division.school_id, current_user, db)
        if school_id is not None and division.school_id != school_id:
            raise HTTPException(
                status_code=422,
                detail="class_division_id does not belong to school_id.",
            )

    if student_id is not None:
        student = (
            db.query(Student)
            .filter(Student.id == student_id)
            .one_or_none()
        )
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found.")
        division = (
            db.query(ClassDivision)
            .filter(ClassDivision.id == student.class_division_id)
            .one()
        )
        require_school_access(division.school_id, current_user, db)
        if class_division_id is not None and student.class_division_id != class_division_id:
            raise HTTPException(
                status_code=422,
                detail="student_id does not belong to class_division_id.",
            )

    filters = AttendanceFilter(
        authorized_school_ids=authorized_school_ids,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        student_id=student_id,
    )
    try:
        items, total_groups = get_attendance_groups(
            db,
            filters,
            group_by,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AttendanceReportResponse(
        group_by=group_by,
        items=items,
        total_groups=total_groups,
        offset=offset,
        limit=limit,
    )


def _reporting_filters(
    db: Session,
    current_user: User,
    *,
    academic_year_id: UUID | None,
    start_date: date | None,
    end_date: date | None,
    school_id: UUID | None,
    class_division_id: UUID | None,
    para_teacher_id: UUID | None,
) -> ReportingFilters:
    validate_date_range(start_date, end_date)
    authorized_school_ids = get_authorized_school_ids(current_user, db)
    if school_id is not None:
        require_school_access(school_id, current_user, db)
    if class_division_id is not None:
        division = db.get(ClassDivision, class_division_id)
        if division is None:
            raise HTTPException(status_code=404, detail="Class division not found.")
        require_school_access(division.school_id, current_user, db)
        if school_id is not None and division.school_id != school_id:
            raise HTTPException(
                status_code=422,
                detail="class_division_id does not belong to school_id.",
            )
    return ReportingFilters(
        authorized_school_ids=authorized_school_ids,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=para_teacher_id,
    )


def _run_domain_report(
    report_type: str,
    db: Session,
    filters: ReportingFilters,
    group_by: str,
) -> dict:
    try:
        if report_type == "delivery":
            return get_delivery_report(db, filters, group_by=group_by)
        if report_type == "engagement":
            return get_engagement_report(db, filters, group_by=group_by)
        if report_type == "tlm":
            return get_tlm_report(db, filters, group_by=group_by)
        raise HTTPException(status_code=422, detail="Unsupported report type.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/delivery")
def get_delivery(
    group_by: Literal["project", "school", "class_division", "para_teacher"] = "project",
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    para_teacher_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=para_teacher_id,
    )
    return _run_domain_report("delivery", db, filters, group_by)


@router.get("/engagement")
def get_engagement(
    group_by: Literal["project", "school", "class_division", "para_teacher"] = "project",
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    para_teacher_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=para_teacher_id,
    )
    return _run_domain_report("engagement", db, filters, group_by)


@router.get("/tlm")
def get_tlm(
    group_by: Literal["project", "school", "class_division", "para_teacher"] = "project",
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    para_teacher_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=para_teacher_id,
    )
    return _run_domain_report("tlm", db, filters, group_by)


@router.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: UUID,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    authorized_school_ids = get_authorized_school_ids(current_user, db)
    try:
        return get_assessment_report(db, assessment_id, authorized_school_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/assessments/{assessment_id}/longitudinal")
def get_assessment_longitudinal(
    assessment_id: UUID,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    try:
        return get_longitudinal_report(
            db,
            assessment_id,
            get_authorized_school_ids(current_user, db),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/schools")
def get_school_report(
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=None,
        para_teacher_id=None,
    )
    return get_school_monitoring(db, filters)


@router.get("/classes")
def get_classes_report(
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=None,
    )
    return get_class_monitoring(db, filters)


@router.get("/trends/delivery")
def get_delivery_trends(
    group_by: Literal["project", "school", "class_division", "para_teacher"] = "project",
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    para_teacher_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=para_teacher_id,
    )
    return get_delivery_trend(db, filters, group_by=group_by)


@router.get("/students")
def get_students_report(
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    search: str | None = Query(None, max_length=150),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=None,
    )
    return get_student_monitoring(
        db,
        filters,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/students/{student_id}")
def get_student_report(
    student_id: UUID,
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    division = db.get(ClassDivision, student.class_division_id)
    if division is None:
        raise HTTPException(status_code=404, detail="Class division not found.")
    require_school_access(division.school_id, current_user, db)
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=division.school_id,
        class_division_id=division.id,
        para_teacher_id=None,
    )
    return get_student_monitoring(db, filters, student_id=student_id)


@router.get("/para-teachers")
def get_para_teachers_report(
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=None,
        para_teacher_id=None,
    )
    return get_para_teacher_monitoring(db, filters)


@router.get("/exports/{report_type}")
def export_report(
    report_type: Literal[
        "sessions",
        "attendance",
        "assessment",
        "tlm",
        "evidence",
        "schools",
        "classes",
        "students",
        "para_teachers",
        "delivery",
        "engagement",
    ],
    group_by: Literal["project", "school", "class_division", "student", "para_teacher"] = "project",
    file_format: Literal["csv", "xlsx", "pdf"] = "csv",
    assessment_id: UUID | None = None,
    academic_year_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    para_teacher_id: UUID | None = None,
    current_user: User = Depends(require_permission("report.export")),
    db: Session = Depends(get_db),
):
    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=class_division_id,
        para_teacher_id=para_teacher_id,
    )
    if report_type == "assessment":
        if assessment_id is None:
            raise HTTPException(status_code=422, detail="assessment_id is required.")
        report = get_assessment_report(
            db,
            assessment_id,
            filters.authorized_school_ids,
        )
        items = report["results"]
    elif report_type == "attendance":
        items, _ = get_attendance_groups(
            db,
            AttendanceFilter(
                authorized_school_ids=filters.authorized_school_ids,
                academic_year_id=filters.academic_year_id,
                start_date=filters.start_date,
                end_date=filters.end_date,
                school_id=filters.school_id,
                class_division_id=filters.class_division_id,
            ),
            group_by,
        )
    elif report_type == "schools":
        items = get_school_monitoring(db, filters)["items"]
    elif report_type == "classes":
        items = get_class_monitoring(db, filters)["items"]
    elif report_type == "students":
        items = get_student_monitoring(db, filters)["items"]
    elif report_type == "para_teachers":
        items = get_para_teacher_monitoring(db, filters)["items"]
    elif report_type == "sessions":
        items = _session_export_rows(db, filters)
    elif report_type == "evidence":
        items = _evidence_export_rows(db, filters)
    else:
        items = _run_domain_report(report_type, db, filters, group_by)["items"]
    applied_filters = {
        "academic_year_id": (
            str(academic_year_id) if academic_year_id else None
        ),
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "school_id": str(school_id) if school_id else None,
        "class_division_id": (
            str(class_division_id) if class_division_id else None
        ),
        "para_teacher_id": (
            str(para_teacher_id) if para_teacher_id else None
        ),
        "assessment_id": str(assessment_id) if assessment_id else None,
        "group_by": group_by,
        "file_format": file_format,
    }

    if report_type == "assessment":
        applied_filters["assessment"] = (
            report.get("name")
            or str(assessment_id)
        )

    payload, media_type, extension = report_bytes(
        report_type,
        items,
        metadata(
            report_type,
            current_user.user_code,
            applied_filters,
        ),
        file_format,
    )
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{report_type}-report.{extension}"'
            )
        },
    )


@router.get("/monthly-management")
def get_monthly_management_report(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    academic_year_id: UUID = Query(...),
    school_id: UUID | None = Query(None),
    current_user: User = Depends(require_permission("report.view")),
    db: Session = Depends(get_db),
):
    # Derive calendar-month boundaries.
    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    academic_year = (
        db.query(AcademicYear)
        .filter(
            AcademicYear.id == academic_year_id,
            AcademicYear.data_origin == "PRODUCTION",
        )
        .one_or_none()
    )
    if academic_year is None:
        raise HTTPException(
            status_code=404,
            detail="Academic year not found.",
        )

    if (
        start_date < academic_year.start_date
        or end_date > academic_year.end_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Selected month must fall entirely within the academic year.",
        )

    filters = _reporting_filters(
        db,
        current_user,
        academic_year_id=academic_year_id,
        start_date=start_date,
        end_date=end_date,
        school_id=school_id,
        class_division_id=None,
        para_teacher_id=None,
    )

    attendance = get_attendance_summary(
        db,
        AttendanceFilter(
            authorized_school_ids=filters.authorized_school_ids,
            academic_year_id=academic_year_id,
            start_date=start_date,
            end_date=end_date,
            school_id=school_id,
        ),
    )
    delivery = get_delivery_report(db, filters)
    engagement = get_engagement_report(db, filters)
    tlm = get_tlm_report(db, filters)
    monitoring = get_school_monitoring(db, filters)

    assessment_query = db.query(Assessment).filter(
        Assessment.academic_year_id == academic_year_id,
        Assessment.assessment_date >= start_date,
        Assessment.assessment_date <= end_date,
        Assessment.data_origin == "PRODUCTION",
    )
    if filters.authorized_school_ids is not None:
        assessment_query = assessment_query.filter(
            Assessment.school_id.in_(filters.authorized_school_ids)
        )
    if school_id is not None:
        assessment_query = assessment_query.filter(
            Assessment.school_id == school_id
        )

    assessments = (
        assessment_query.order_by(
            Assessment.assessment_date,
            Assessment.school_id,
            Assessment.assessment_type,
            Assessment.sequence_no,
        ).all()
    )

    assessment_events = [
        get_assessment_report(
            db,
            assessment.id,
            filters.authorized_school_ids,
        )
        for assessment in assessments
    ]

    return {
        "period": {
            "year": year,
            "month": month,
            "start_date": start_date,
            "end_date": end_date,
            "academic_year_id": academic_year.id,
            "academic_year_name": academic_year.name,
        },
        "delivery": delivery,
        "attendance": attendance,
        "engagement": engagement,
        "tlm": tlm,
        "evidence": {
            "eligible_completed_sessions": sum(
                item["evidence"]["eligible_completed_sessions"]
                for item in monitoring["items"]
            ),
            "sessions_with_evidence": sum(
                item["evidence"]["sessions_with_evidence"]
                for item in monitoring["items"]
            ),
        },
        "schools": monitoring,
        "assessments": {
            "message": (
                None
                if assessment_events
                else "No assessment event in selected period."
            ),
            "events": assessment_events,
        },
    }
