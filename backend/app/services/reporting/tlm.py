from __future__ import annotations

from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from app.models import ClassDivision, School, SessionTLM, TeachingSession, TLM, User
from app.services.reporting.common import ReportingFilters, apply_session_filters, production_session_query
from app.services.session_tlm.service import NA_TLM_NAME


def get_tlm_report(db: Session, filters: ReportingFilters, *, group_by: str = "project") -> dict:
    query = (
        apply_session_filters(db, production_session_query(db), filters)
        .outerjoin(SessionTLM, SessionTLM.teaching_session_id == TeachingSession.id)
        .outerjoin(TLM, TLM.id == SessionTLM.tlm_id)
        .filter(
            (SessionTLM.id.is_(None))
            | (
                (SessionTLM.data_origin == "PRODUCTION")
                & (TLM.data_origin == "PRODUCTION")
            )
        )
    )
    group_columns = ()
    if group_by == "school":
        group_columns = (ClassDivision.school_id.label("school_id"), School.school_code.label("school_code"), School.school_name.label("school_name"))
    elif group_by == "class_division":
        group_columns = (ClassDivision.id.label("class_division_id"), ClassDivision.school_id.label("school_id"), ClassDivision.class_level.label("class_level"), ClassDivision.division.label("division"))
    elif group_by == "para_teacher":
        query = query.join(User, User.id == TeachingSession.para_teacher_id).filter(User.data_origin == "PRODUCTION")
        group_columns = (TeachingSession.para_teacher_id.label("para_teacher_id"), User.user_code.label("para_teacher_code"), User.full_name.label("para_teacher_name"))
    elif group_by == "para_teacher_school":
        query = query.join(
            User, User.id == TeachingSession.para_teacher_id
        ).filter(User.data_origin == "PRODUCTION")
        group_columns = (
            TeachingSession.para_teacher_id.label("para_teacher_id"),
            User.user_code.label("para_teacher_code"),
            User.full_name.label("para_teacher_name"),
            ClassDivision.school_id.label("school_id"),
            School.school_code.label("school_code"),
            School.school_name.label("school_name"),
        )
    elif group_by != "project":
        raise ValueError("Unsupported TLM grouping.")
    normal_record = SessionTLM.id.is_not(None) & (TLM.name != NA_TLM_NAME)
    explicit_na = SessionTLM.id.is_not(None) & (TLM.name == NA_TLM_NAME)
    aggregate = query.with_entities(
        *group_columns,
        func.count(distinct(TeachingSession.id)).label("eligible_sessions"),
        func.count(distinct(case((normal_record, TeachingSession.id)))).label("sessions_with_tlm"),
        func.count(distinct(case((explicit_na, TeachingSession.id)))).label("explicit_na_sessions"),
        func.count(distinct(case((SessionTLM.id.is_(None), TeachingSession.id)))).label("missing_tlm_sessions"),
        func.count(distinct(case((normal_record, SessionTLM.tlm_id)))).label("distinct_tlms_used"),
        func.count(
            distinct(
                case(
                    (
                        normal_record & SessionTLM.photo_id.is_not(None),
                        TeachingSession.id,
                    )
                )
            )
        ).label("sessions_with_tlm_evidence"),
    )
    if group_columns:
        aggregate = aggregate.group_by(*group_columns).order_by(*group_columns)
        rows = aggregate.all()
    else:
        rows = [aggregate.one()]
    items = []
    for row in rows:
        values = row._mapping
        eligible = int(values["eligible_sessions"] or 0)
        used = int(values["sessions_with_tlm"] or 0)
        na = int(values["explicit_na_sessions"] or 0)
        item = {
            "eligible_sessions": eligible,
            "sessions_with_tlm": used,
            "explicit_na_sessions": na,
            "missing_tlm_sessions": max(eligible - used - na, 0),
            "distinct_tlms_used": int(values["distinct_tlms_used"] or 0),
            "sessions_with_tlm_evidence": int(values["sessions_with_tlm_evidence"] or 0),
            "usage_coverage_percentage": round(used / eligible * 100, 2) if eligible else 0.0,
            "recording_completeness_percentage": round((used + na) / eligible * 100, 2) if eligible else 0.0,
        }
        for key in ("school_id", "school_code", "school_name", "class_division_id", "class_level", "division", "para_teacher_id", "para_teacher_code", "para_teacher_name"):
            if key in values:
                item[key] = values[key]
        items.append(item)
    return {"group_by": group_by, "items": items}
