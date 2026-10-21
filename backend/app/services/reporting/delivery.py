from __future__ import annotations

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import ClassDivision, School, TeachingSession, User
from app.services.reporting.common import (
    ReportingFilters,
    apply_session_filters,
    production_session_query,
)


def get_delivery_report(
    db: Session,
    filters: ReportingFilters,
    *,
    group_by: str = "project",
) -> dict:
    query = apply_session_filters(db, production_session_query(db), filters)
    completed_duration = func.sum(
        case(
            (
                TeachingSession.status == "COMPLETED",
                TeachingSession.duration_minutes,
            ),
            else_=None,
        )
    )
    valid_duration_count = func.count(
        case(
            (
                (TeachingSession.status == "COMPLETED")
                & TeachingSession.duration_minutes.is_not(None),
                TeachingSession.id,
            )
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
        group_columns = (
            TeachingSession.para_teacher_id.label("para_teacher_id"),
            User.user_code.label("para_teacher_code"),
            User.full_name.label("para_teacher_name"),
        )
        query = query.join(User, User.id == TeachingSession.para_teacher_id).filter(
            User.data_origin == "PRODUCTION"
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
        raise ValueError("Unsupported delivery grouping.")
    aggregate = query.with_entities(
        *group_columns,
        func.count(TeachingSession.id).label("total_sessions"),
        func.sum(case((TeachingSession.status == "PLANNED", 1), else_=0)).label(
            "planned_sessions"
        ),
        func.sum(
            case(
                (
                    (TeachingSession.status == "PLANNED")
                    & (TeachingSession.session_date >= func.current_date()),
                    1,
                ),
                else_=0,
            )
        ).label("upcoming_sessions"),
        func.sum(case((TeachingSession.status == "IN_PROGRESS", 1), else_=0)).label(
            "in_progress_sessions"
        ),
        func.sum(case((TeachingSession.status == "COMPLETED", 1), else_=0)).label(
            "completed_sessions"
        ),
        func.sum(case((TeachingSession.status == "CANCELLED", 1), else_=0)).label(
            "cancelled_sessions"
        ),
        completed_duration.label("completed_duration_minutes"),
        valid_duration_count.label("completed_sessions_with_duration"),
    )
    if group_columns:
        aggregate = aggregate.group_by(*group_columns).order_by(*group_columns)
        rows = aggregate.all()
    else:
        rows = [aggregate.one()]
    items = []
    for row in rows:
        values = row._mapping
        completed = int(values["completed_sessions"] or 0)
        planned = int(values["planned_sessions"] or 0)
        duration = values["completed_duration_minutes"]
        item = {
            "total_sessions": int(values["total_sessions"] or 0),
            "planned_sessions": planned,
            "upcoming_sessions": int(values["upcoming_sessions"] or 0),
            "in_progress_sessions": int(values["in_progress_sessions"] or 0),
            "completed_sessions": completed,
            "cancelled_sessions": int(values["cancelled_sessions"] or 0),
            "completed_duration_minutes": int(duration or 0),
            "teaching_hours": round(float(duration or 0) / 60, 2),
            "completed_sessions_with_duration": int(
                values["completed_sessions_with_duration"] or 0
            ),
            "average_completed_duration_minutes": (
                round(float(duration) / int(values["completed_sessions_with_duration"]), 2)
                if duration is not None and values["completed_sessions_with_duration"]
                else None
            ),
            "completion_percentage": None,
        }
        for key in (
            "school_id",
            "school_code",
            "school_name",
            "class_division_id",
            "class_level",
            "division",
            "para_teacher_id",
            "para_teacher_code",
            "para_teacher_name",
        ):
            if key in values:
                item[key] = values[key]
        items.append(item)
    return {"group_by": group_by, "items": items}


def get_delivery_trend(
    db: Session,
    filters: ReportingFilters,
    *,
    group_by: str = "project",
) -> dict:
    query = apply_session_filters(db, production_session_query(db), filters)
    month = func.date_trunc("month", TeachingSession.session_date).label("month")
    groups = [month]
    if group_by == "school":
        groups.extend(
            [
                ClassDivision.school_id.label("school_id"),
                School.school_code.label("school_code"),
                School.school_name.label("school_name"),
            ]
        )
    elif group_by == "class_division":
        groups.extend(
            [
                ClassDivision.id.label("class_division_id"),
                ClassDivision.class_level.label("class_level"),
                ClassDivision.division.label("division"),
            ]
        )
    elif group_by == "para_teacher":
        query = query.join(User, User.id == TeachingSession.para_teacher_id).filter(
            User.data_origin == "PRODUCTION"
        )
        groups.extend(
            [
                TeachingSession.para_teacher_id.label("para_teacher_id"),
                User.user_code.label("para_teacher_code"),
                User.full_name.label("para_teacher_name"),
            ]
        )
    elif group_by != "project":
        raise ValueError("Unsupported delivery grouping.")
    aggregate = (
        query.with_entities(
            *groups,
            func.count(TeachingSession.id).label("session_count"),
            func.sum(
                case((TeachingSession.status == "COMPLETED", 1), else_=0)
            ).label("completed_sessions"),
            func.sum(
                case(
                    (
                        (TeachingSession.status == "COMPLETED")
                        & TeachingSession.duration_minutes.is_not(None),
                        TeachingSession.duration_minutes,
                    ),
                    else_=0,
                )
            ).label("completed_duration_minutes"),
        )
        .group_by(*groups)
        .order_by(*groups)
        .all()
    )
    return {
        "group_by": group_by,
        "items": [
            {
                **{
                    key: row._mapping[key]
                    for key in row._mapping
                    if key not in {"completed_duration_minutes"}
                },
                "completed_duration_minutes": int(
                    row._mapping["completed_duration_minutes"] or 0
                ),
            }
            for row in aggregate
        ],
    }
