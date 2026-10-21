from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import ClassDivision, School, SessionEngagement, TeachingSession, User
from app.services.reporting.common import ReportingFilters, apply_session_filters, production_session_query


def get_engagement_report(db: Session, filters: ReportingFilters, *, group_by: str = "project") -> dict:
    query = (
        apply_session_filters(db, production_session_query(db), filters)
        .outerjoin(SessionEngagement, SessionEngagement.teaching_session_id == TeachingSession.id)
        .filter(
            (SessionEngagement.id.is_(None))
            | (SessionEngagement.data_origin == "PRODUCTION")
        )
    )
    group_columns = ()
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
    elif group_by == "para_teacher":
        query = query.join(User, User.id == TeachingSession.para_teacher_id).filter(
            User.data_origin == "PRODUCTION"
        )
        group_columns = (
            TeachingSession.para_teacher_id.label("para_teacher_id"),
            User.user_code.label("para_teacher_code"),
            User.full_name.label("para_teacher_name"),
        )
    elif group_by == "para_teacher_school":
        group_columns = (
            TeachingSession.para_teacher_id.label("para_teacher_id"),
            User.user_code.label("para_teacher_code"),
            User.full_name.label("para_teacher_name"),
            ClassDivision.school_id.label("school_id"),
            School.school_code.label("school_code"),
            School.school_name.label("school_name"),
        )
        query = query.join(
            User, User.id == TeachingSession.para_teacher_id
        ).filter(User.data_origin == "PRODUCTION")
    elif group_by != "project":
        raise ValueError("Unsupported engagement grouping.")
    aggregate = query.with_entities(
        *group_columns,
        func.count(TeachingSession.id).label("session_count"),
        func.count(SessionEngagement.id).label("scored_session_count"),
        func.sum(case((SessionEngagement.id.is_(None), 1), else_=0)).label(
            "missing_engagement_count"
        ),
        func.sum(SessionEngagement.score).label("score_sum"),
    )
    distribution = [
        func.sum(case((SessionEngagement.score == score, 1), else_=0)).label(
            f"score_{score}_count"
        )
        for score in range(1, 11)
    ]
    aggregate = aggregate.add_columns(*distribution)
    if group_columns:
        aggregate = aggregate.group_by(*group_columns).order_by(*group_columns)
        rows = aggregate.all()
    else:
        rows = [aggregate.one()]
    items = []
    for row in rows:
        values = row._mapping
        scored = int(values["scored_session_count"] or 0)
        item = {
            "session_count": int(values["session_count"] or 0),
            "scored_session_count": scored,
            "missing_engagement_count": int(values["missing_engagement_count"] or 0),
            "average_engagement": round(float(values["score_sum"]) / scored, 2)
            if scored else None,
            "distribution": {
                str(score): int(values[f"score_{score}_count"] or 0)
                for score in range(1, 11)
            },
        }
        for key in (
            "school_id", "school_code", "school_name", "class_division_id",
            "class_level", "division", "para_teacher_id", "para_teacher_code",
            "para_teacher_name",
        ):
            if key in values:
                item[key] = values[key]
        items.append(item)
    return {"group_by": group_by, "items": items}
