from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import (
    Assessment,
    AssessmentImport,
    AssessmentImportRow,
    AssessmentResult,
    ClassroomObservation,
    ClassroomObservationReport,
    ClassDivision,
    School,
    STEMInspection,
    STEMInspectionReport,
    SessionEvidence,
    Student,
    TeachingSession,
    User,
    UserAssignment,
)
from app.models.assessment import AssessmentClassDivision
from app.services.reporting.assessment import (
    get_assessment_report,
    get_longitudinal_report,
)
from app.services.reporting.attendance import AttendanceFilter, get_attendance_groups
from app.services.reporting.common import (
    ReportingFilters,
    apply_session_filters,
    production_session_query,
)
from app.services.reporting.delivery import (
    get_delivery_report,
    get_delivery_trend,
)
from app.services.reporting.engagement import get_engagement_report
from app.services.reporting.tlm import get_tlm_report

def get_school_monitoring(db: Session, filters: ReportingFilters) -> dict:
    query = db.query(School).filter(School.data_origin == "PRODUCTION")
    if filters.authorized_school_ids is not None:
        query = query.filter(School.id.in_(filters.authorized_school_ids))
    if filters.school_id is not None:
        query = query.filter(School.id == filters.school_id)
    schools = query.order_by(School.school_code).all()
    school_ids = {school.id for school in schools}
    scoped = ReportingFilters(
        authorized_school_ids=school_ids,
        academic_year_id=filters.academic_year_id,
        start_date=filters.start_date,
        end_date=filters.end_date,
    )
    delivery = {
        item["school_id"]: item
        for item in get_delivery_report(db, scoped, group_by="school")["items"]
    }
    attendance_items, _ = get_attendance_groups(
        db,
        AttendanceFilter(
            authorized_school_ids=school_ids,
            academic_year_id=filters.academic_year_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
        ),
        "school",
    )
    attendance = {item["school_id"]: item for item in attendance_items}
    engagement = {
        item["school_id"]: item
        for item in get_engagement_report(db, scoped, group_by="school")["items"]
    }
    tlm = {
        item["school_id"]: item
        for item in get_tlm_report(db, scoped, group_by="school")["items"]
    }
    population = dict(
        db.query(ClassDivision.school_id, func.count(Student.id))
        .join(Student, Student.class_division_id == ClassDivision.id)
        .filter(
            ClassDivision.school_id.in_(school_ids),
            ClassDivision.data_origin == "PRODUCTION",
            Student.data_origin == "PRODUCTION",
            Student.status == "ACTIVE",
        )
        .group_by(ClassDivision.school_id)
        .all()
    )
    divisions = dict(
        db.query(ClassDivision.school_id, func.count(ClassDivision.id))
        .filter(
            ClassDivision.school_id.in_(school_ids),
            ClassDivision.data_origin == "PRODUCTION",
        )
        .group_by(ClassDivision.school_id)
        .all()
    )
    items = []
    para_teachers = dict(
        db.query(
            ClassDivision.school_id,
            func.count(func.distinct(TeachingSession.para_teacher_id)),
        )
        .join(
            TeachingSession,
            TeachingSession.class_division_id == ClassDivision.id,
        )
        .filter(
            ClassDivision.school_id.in_(school_ids),
            ClassDivision.data_origin == "PRODUCTION",
            TeachingSession.data_origin == "PRODUCTION",
            *(
                [TeachingSession.session_date >= filters.start_date]
                if filters.start_date
                else []
            ),
            *(
                [TeachingSession.session_date <= filters.end_date]
                if filters.end_date
                else []
            ),
        )
        .group_by(ClassDivision.school_id)
        .all()
    )

    completed_sessions = dict(
        db.query(
            ClassDivision.school_id,
            func.count(TeachingSession.id),
        )
        .join(
            TeachingSession,
            TeachingSession.class_division_id == ClassDivision.id,
        )
        .filter(
            ClassDivision.school_id.in_(school_ids),
            ClassDivision.data_origin == "PRODUCTION",
            TeachingSession.data_origin == "PRODUCTION",
            TeachingSession.status == "COMPLETED",
            *(
                [TeachingSession.session_date >= filters.start_date]
                if filters.start_date
                else []
            ),
            *(
                [TeachingSession.session_date <= filters.end_date]
                if filters.end_date
                else []
            ),
        )
        .group_by(ClassDivision.school_id)
        .all()
    )

    completed_with_evidence = dict(
        db.query(
            ClassDivision.school_id,
            func.count(func.distinct(TeachingSession.id)),
        )
        .join(
            TeachingSession,
            TeachingSession.class_division_id == ClassDivision.id,
        )
        .join(
            SessionEvidence,
            SessionEvidence.teaching_session_id == TeachingSession.id,
        )
        .filter(
            ClassDivision.school_id.in_(school_ids),
            ClassDivision.data_origin == "PRODUCTION",
            TeachingSession.data_origin == "PRODUCTION",
            TeachingSession.status == "COMPLETED",
            SessionEvidence.data_origin == "PRODUCTION",
            *(
                [TeachingSession.session_date >= filters.start_date]
                if filters.start_date
                else []
            ),
            *(
                [TeachingSession.session_date <= filters.end_date]
                if filters.end_date
                else []
            ),
        )
        .group_by(ClassDivision.school_id)
        .all()
    )


    classroom_observations = {}
    stem_inspections = {}

    if school_ids:
        classroom_rows = (
            db.query(
                ClassroomObservation.school_id,
                func.count(ClassroomObservation.id),
                func.count(
                    case(
                        (
                            ClassroomObservationReport.status == "PENDING",
                            ClassroomObservationReport.id,
                        ),
                        else_=None,
                    )
                ),
                func.count(
                    case(
                        (
                            ClassroomObservationReport.status == "COMPLETE",
                            ClassroomObservationReport.id,
                        ),
                        else_=None,
                    )
                ),
            )
            .outerjoin(
                ClassroomObservationReport,
                (
                    ClassroomObservationReport.observation_id
                    == ClassroomObservation.id
                )
                & (
                    ClassroomObservationReport.data_origin == "PRODUCTION"
                ),
            )
            .filter(
                ClassroomObservation.school_id.in_(school_ids),
                ClassroomObservation.data_origin == "PRODUCTION",
                *(
                    [ClassroomObservation.observed_at >= filters.start_date]
                    if filters.start_date
                    else []
                ),
                *(
                    [
                        ClassroomObservation.observed_at
                        < filters.end_date + timedelta(days=1)
                    ]
                    if filters.end_date
                    else []
                ),
            )
            .group_by(ClassroomObservation.school_id)
            .all()
        )
        classroom_observations = {
            school_id: {
                "classroom_observations": int(total or 0),
                "classroom_reports_pending": int(pending or 0),
                "classroom_reports_complete": int(complete or 0),
            }
            for school_id, total, pending, complete in classroom_rows
        }

        inspection_rows = (
            db.query(
                STEMInspection.school_id,
                func.count(STEMInspection.id),
                func.count(
                    case(
                        (
                            STEMInspectionReport.status == "PENDING",
                            STEMInspectionReport.id,
                        ),
                        else_=None,
                    )
                ),
                func.count(
                    case(
                        (
                            STEMInspectionReport.status == "COMPLETE",
                            STEMInspectionReport.id,
                        ),
                        else_=None,
                    )
                ),
            )
            .outerjoin(
                STEMInspectionReport,
                (
                    STEMInspectionReport.inspection_id == STEMInspection.id
                )
                & (STEMInspectionReport.data_origin == "PRODUCTION"),
            )
            .filter(
                STEMInspection.school_id.in_(school_ids),
                STEMInspection.data_origin == "PRODUCTION",
                *(
                    [STEMInspection.inspected_at >= filters.start_date]
                    if filters.start_date
                    else []
                ),
                *(
                    [
                        STEMInspection.inspected_at
                        < filters.end_date + timedelta(days=1)
                    ]
                    if filters.end_date
                    else []
                ),
            )
            .group_by(STEMInspection.school_id)
            .all()
        )
        stem_inspections = {
            school_id: {
                "stem_inspections": int(total or 0),
                "stem_reports_pending": int(pending or 0),
                "stem_reports_complete": int(complete or 0),
            }
            for school_id, total, pending, complete in inspection_rows
        }

    latest_assessments = {}

    if filters.academic_year_id is not None and school_ids:
        assessment_rows = (
            db.query(Assessment)
            .filter(
                Assessment.school_id.in_(school_ids),
                Assessment.academic_year_id == filters.academic_year_id,
                Assessment.data_origin == "PRODUCTION",
            )
            .order_by(
                Assessment.school_id,
                Assessment.assessment_date.desc(),
                Assessment.sequence_no.desc(),
                Assessment.id.desc(),
            )
            .all()
        )

        for assessment in assessment_rows:
            latest_assessments.setdefault(assessment.school_id, assessment)

    baseline_assessments = {
        assessment.school_id: assessment
        for assessment in (
            db.query(Assessment)
            .filter(
                Assessment.school_id.in_(school_ids),
                Assessment.assessment_type == "BASELINE",
                Assessment.data_origin == "PRODUCTION",
                *(
                    [Assessment.academic_year_id == filters.academic_year_id]
                    if filters.academic_year_id is not None
                    else []
                ),
            )
            .order_by(Assessment.school_id, Assessment.assessment_date.desc())
            .all()
        )
    }

    endline_assessments = {
        assessment.school_id: assessment
        for assessment in (
            db.query(Assessment)
            .filter(
                Assessment.school_id.in_(school_ids),
                Assessment.assessment_type == "ENDLINE",
                Assessment.data_origin == "PRODUCTION",
                *(
                    [Assessment.academic_year_id == filters.academic_year_id]
                    if filters.academic_year_id is not None
                    else []
                ),
            )
            .order_by(Assessment.school_id, Assessment.assessment_date.desc())
            .all()
        )
    }
    for school in schools:
        empty_attendance = {
            "eligible_record_count": 0,
            "present_record_count": 0,
            "absent_record_count": 0,
            "attendance_percentage": 0.0,
        }
        latest_assessment = latest_assessments.get(school.id)
        baseline_assessment = baseline_assessments.get(school.id)
        endline_assessment = endline_assessments.get(school.id)

        assessment_summary = {
            "latest": None,
            "baseline": None,
            "endline": None,
            "longitudinal": None,
        }

        if latest_assessment is not None:
            assessment_summary["latest"] = {
                "assessment_id": latest_assessment.id,
                "assessment_type": latest_assessment.assessment_type,
                "sequence_no": latest_assessment.sequence_no,
                "name": latest_assessment.name,
                "assessment_date": latest_assessment.assessment_date,
                "maximum_marks": latest_assessment.maximum_marks,
                "status": latest_assessment.status,
            }

        if baseline_assessment is not None:
            assessment_summary["baseline"] = get_assessment_report(
                db,
                baseline_assessment.id,
                school_ids,
            )

        if endline_assessment is not None:
            assessment_summary["endline"] = get_assessment_report(
                db,
                endline_assessment.id,
                school_ids,
            )

            assessment_summary["longitudinal"] = get_longitudinal_report(
                db,
                endline_assessment.id,
                school_ids,
            )
        items.append({
            "school_id": school.id,
            "school_code": school.school_code,
            "school_name": school.school_name,
            "active_students": int(population.get(school.id, 0)),
            "class_divisions": int(divisions.get(school.id, 0)),
            "delivery": delivery.get(school.id, {"school_id": school.id}),
            "attendance": attendance.get(school.id, empty_attendance),
            "engagement": engagement.get(school.id, {"school_id": school.id}),
            "tlm": tlm.get(school.id, {"school_id": school.id}),
            "assessment": assessment_summary,
            "observations": {
                "classroom_observations": 0,
                "classroom_reports_pending": 0,
                "classroom_reports_complete": 0,
                "stem_inspections": 0,
                "stem_reports_pending": 0,
                "stem_reports_complete": 0,
                **classroom_observations.get(school.id, {}),
                **stem_inspections.get(school.id, {}),
            },
            "para_teachers": int(para_teachers.get(school.id, 0)),
            "evidence": {
                "eligible_completed_sessions": int(
                    completed_sessions.get(school.id, 0)
                ),
                "sessions_with_evidence": int(
                    completed_with_evidence.get(school.id, 0)
                ),
                "completeness_percentage": (
                    round(
                        completed_with_evidence.get(school.id, 0)
                        / completed_sessions.get(school.id, 0)
                        * 100,
                        2,
                    )
                    if completed_sessions.get(school.id, 0)
                    else None
                ),
            },
        })
    return {"items": items, "total_schools": len(items)}



def _class_assessment_report(
    db: Session,
    assessment: Assessment | None,
    school_ids: set,
    class_division_id,
) -> dict | None:
    if assessment is None:
        return None

    report = get_assessment_report(db, assessment.id, school_ids)
    scoped_divisions = (
        db.query(ClassDivision.id, ClassDivision.class_level, ClassDivision.division)
        .join(
            AssessmentClassDivision,
            AssessmentClassDivision.class_division_id == ClassDivision.id,
        )
        .filter(AssessmentClassDivision.assessment_id == assessment.id)
        .order_by(ClassDivision.class_level, ClassDivision.division)
        .all()
    )
    recorded_scope = bool(scoped_divisions)
    result_rows = report.get("results", [])
    result_student_ids = {
        row["student_id"] for row in result_rows
    }

    student_divisions = {}
    if result_student_ids:
        student_divisions = dict(
            db.query(Student.id, Student.class_division_id)
            .filter(
                Student.id.in_(result_student_ids),
                Student.data_origin == "PRODUCTION",
            )
            .all()
        )

    scoped_division_ids = {
        division.id for division in scoped_divisions
    }

    class_results = [
        row
        for row in result_rows
        if student_divisions.get(row["student_id"]) == class_division_id
        and (
            not recorded_scope
            or class_division_id in scoped_division_ids
        )
    ]

    def numeric_average(key):
        values = [
            float(row[key])
            for row in class_results
            if row.get(key) is not None
        ]
        return round(sum(values) / len(values), 2) if values else None

    return {
        "assessment_id": assessment.id,
        "academic_year_id": report["academic_year_id"],
        "assessment_type": assessment.assessment_type,
        "sequence_no": assessment.sequence_no,
        "name": assessment.name,
        "assessment_date": assessment.assessment_date,
        "maximum_marks": assessment.maximum_marks,
        "status": assessment.status,
        "result_scope": "students_currently_assigned_to_class_division",
        "result_count": len(class_results),
        "average_marks": numeric_average("aggregate_marks"),
        "average_percentage": numeric_average("percentage"),
        "results": class_results,
        "assessment_import_scope": (
            "selected_class_divisions"
            if recorded_scope
            else "unknown_historical_scope"
        ),
        "assessment_import_class_divisions": [
            {
                "class_division_id": division.id,
                "class_level": division.class_level,
                "division": division.division,
            }
            for division in scoped_divisions
        ],
        "assessment_import_quality": {
            "imported_rows": report.get("imported_rows"),
            "mapped_rows": report.get("mapped_rows"),
            "valid_submitted_results": report.get(
                "valid_submitted_results"
            ),
            "warning_rows": report.get("warning_rows"),
            "error_rows": report.get("error_rows"),
            "unresolved_warning_rows": report.get(
                "unresolved_warning_rows"
            ),
            "missing_import_students": report.get(
                "missing_import_students"
            ),
            "unmatched_student_rows": report.get(
                "unmatched_student_rows"
            ),
        },
    }


def get_class_monitoring(db: Session, filters: ReportingFilters) -> dict:
    divisions_query = (
        db.query(ClassDivision, School)
        .join(School, School.id == ClassDivision.school_id)
        .filter(
            ClassDivision.data_origin == "PRODUCTION",
            School.data_origin == "PRODUCTION",
        )
    )

    if filters.authorized_school_ids is not None:
        divisions_query = divisions_query.filter(
            School.id.in_(filters.authorized_school_ids)
        )
    if filters.school_id is not None:
        divisions_query = divisions_query.filter(
            School.id == filters.school_id
        )
    if filters.class_division_id is not None:
        divisions_query = divisions_query.filter(
            ClassDivision.id == filters.class_division_id
        )

    divisions = divisions_query.order_by(
        School.school_code,
        ClassDivision.class_level,
        ClassDivision.division,
    ).all()

    division_ids = {division.id for division, _ in divisions}

    if not division_ids:
        return {"items": [], "total_class_divisions": 0}

    school_ids = {school.id for _, school in divisions}
    latest_assessments = {}
    baseline_assessments = {}
    endline_assessments = {}

    if filters.academic_year_id is not None:
        assessment_rows = (
            db.query(Assessment)
            .filter(
                Assessment.school_id.in_(school_ids),
                Assessment.academic_year_id == filters.academic_year_id,
                Assessment.data_origin == "PRODUCTION",
            )
            .order_by(
                Assessment.school_id,
                Assessment.assessment_date.desc(),
                Assessment.sequence_no.desc(),
                Assessment.id.desc(),
            )
            .all()
        )
        for assessment in assessment_rows:
            latest_assessments.setdefault(
                assessment.school_id, assessment
            )

    for assessment in (
        db.query(Assessment)
        .filter(
            Assessment.school_id.in_(school_ids),
            Assessment.assessment_type == "BASELINE",
            Assessment.data_origin == "PRODUCTION",
            *(
                [Assessment.academic_year_id == filters.academic_year_id]
                if filters.academic_year_id is not None
                else []
            ),
        )
        .order_by(
            Assessment.school_id,
            Assessment.assessment_date.desc(),
            Assessment.id.desc(),
        )
        .all()
    ):
        baseline_assessments.setdefault(assessment.school_id, assessment)

    for assessment in (
        db.query(Assessment)
        .filter(
            Assessment.school_id.in_(school_ids),
            Assessment.assessment_type == "ENDLINE",
            Assessment.data_origin == "PRODUCTION",
            *(
                [Assessment.academic_year_id == filters.academic_year_id]
                if filters.academic_year_id is not None
                else []
            ),
        )
        .order_by(
            Assessment.school_id,
            Assessment.assessment_date.desc(),
            Assessment.id.desc(),
        )
        .all()
    ):
        endline_assessments.setdefault(assessment.school_id, assessment)

    scoped = ReportingFilters(
        authorized_school_ids={
            school.id for _, school in divisions
        },
        academic_year_id=filters.academic_year_id,
        start_date=filters.start_date,
        end_date=filters.end_date,
        school_id=filters.school_id,
        class_division_id=filters.class_division_id,
        para_teacher_id=filters.para_teacher_id,
    )

    delivery = {
        item["class_division_id"]: item
        for item in get_delivery_report(
            db, scoped, group_by="class_division"
        )["items"]
    }

    delivery_trend = {}
    for item in get_delivery_trend(
        db, scoped, group_by="class_division"
    )["items"]:
        delivery_trend.setdefault(item["class_division_id"], []).append(item)

    attendance, _ = get_attendance_groups(
        db,
        AttendanceFilter(
            authorized_school_ids=scoped.authorized_school_ids,
            academic_year_id=filters.academic_year_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            school_id=filters.school_id,
            class_division_id=filters.class_division_id,
        ),
        "class_division",
    )
    attendance_by_class = {
        item["class_division_id"]: item for item in attendance
    }

    engagement = {
        item["class_division_id"]: item
        for item in get_engagement_report(
            db, scoped, group_by="class_division"
        )["items"]
    }
    tlm = {
        item["class_division_id"]: item
        for item in get_tlm_report(
            db, scoped, group_by="class_division"
        )["items"]
    }

    active_students = dict(
        db.query(
            Student.class_division_id,
            func.count(Student.id),
        )
        .filter(
            Student.class_division_id.in_(division_ids),
            Student.data_origin == "PRODUCTION",
            Student.status == "ACTIVE",
        )
        .group_by(Student.class_division_id)
        .all()
    )


    para_teachers = dict(
        apply_session_filters(db, production_session_query(db), scoped)
        .with_entities(
            TeachingSession.class_division_id,
            func.count(func.distinct(TeachingSession.para_teacher_id)),
        )
        .filter(TeachingSession.para_teacher_id.isnot(None))
        .group_by(TeachingSession.class_division_id)
        .all()
    )

    completed_sessions = dict(
        apply_session_filters(db, production_session_query(db), scoped)
        .with_entities(
            TeachingSession.class_division_id,
            func.count(TeachingSession.id),
        )
        .filter(TeachingSession.status == "COMPLETED")
        .group_by(TeachingSession.class_division_id)
        .all()
    )

    completed_with_evidence = dict(
        apply_session_filters(db, production_session_query(db), scoped)
        .join(
            SessionEvidence,
            SessionEvidence.teaching_session_id == TeachingSession.id,
        )
        .with_entities(
            TeachingSession.class_division_id,
            func.count(func.distinct(TeachingSession.id)),
        )
        .filter(
            TeachingSession.status == "COMPLETED",
            SessionEvidence.data_origin == "PRODUCTION",
        )
        .group_by(TeachingSession.class_division_id)
        .all()
    )

    classroom_observations = {}
    stem_inspections = {}

    classroom_rows = (
        db.query(
            ClassroomObservation.class_division_id,
            func.count(ClassroomObservation.id),
            func.count(
                case(
                    (
                        ClassroomObservationReport.status == "PENDING",
                        ClassroomObservationReport.id,
                    ),
                    else_=None,
                )
            ),
            func.count(
                case(
                    (
                        ClassroomObservationReport.status == "COMPLETE",
                        ClassroomObservationReport.id,
                    ),
                    else_=None,
                )
            ),
        )
        .join(
            ClassDivision,
            ClassDivision.id == ClassroomObservation.class_division_id,
        )
        .outerjoin(
            ClassroomObservationReport,
            (
                ClassroomObservationReport.observation_id
                == ClassroomObservation.id
            )
            & (ClassroomObservationReport.data_origin == "PRODUCTION"),
        )
        .filter(
            ClassroomObservation.class_division_id.in_(division_ids),
            ClassroomObservation.data_origin == "PRODUCTION",
            ClassDivision.data_origin == "PRODUCTION",
            *(
                [ClassroomObservation.observed_at >= filters.start_date]
                if filters.start_date
                else []
            ),
            *(
                [
                    ClassroomObservation.observed_at
                    < filters.end_date + timedelta(days=1)
                ]
                if filters.end_date
                else []
            ),
        )
        .group_by(ClassroomObservation.class_division_id)
        .all()
    )

    classroom_observations = {
        division_id: {
            "classroom_observations": int(total or 0),
            "classroom_reports_pending": int(pending or 0),
            "classroom_reports_complete": int(complete or 0),
        }
        for division_id, total, pending, complete in classroom_rows
    }

    inspection_rows = (
        db.query(
            STEMInspection.class_division_id,
            func.count(STEMInspection.id),
            func.count(
                case(
                    (
                        STEMInspectionReport.status == "PENDING",
                        STEMInspectionReport.id,
                    ),
                    else_=None,
                )
            ),
            func.count(
                case(
                    (
                        STEMInspectionReport.status == "COMPLETE",
                        STEMInspectionReport.id,
                    ),
                    else_=None,
                )
            ),
        )
        .join(
            ClassDivision,
            ClassDivision.id == STEMInspection.class_division_id,
        )
        .outerjoin(
            STEMInspectionReport,
            (
                STEMInspectionReport.inspection_id == STEMInspection.id
            )
            & (STEMInspectionReport.data_origin == "PRODUCTION"),
        )
        .filter(
            STEMInspection.class_division_id.in_(division_ids),
            STEMInspection.data_origin == "PRODUCTION",
            ClassDivision.data_origin == "PRODUCTION",
            *(
                [STEMInspection.inspected_at >= filters.start_date]
                if filters.start_date
                else []
            ),
            *(
                [
                    STEMInspection.inspected_at
                    < filters.end_date + timedelta(days=1)
                ]
                if filters.end_date
                else []
            ),
        )
        .group_by(STEMInspection.class_division_id)
        .all()
    )

    stem_inspections = {
        division_id: {
            "stem_inspections": int(total or 0),
            "stem_reports_pending": int(pending or 0),
            "stem_reports_complete": int(complete or 0),
        }
        for division_id, total, pending, complete in inspection_rows
    }

    items = []

    for division, school in divisions:
        eligible_completed = int(completed_sessions.get(division.id, 0))
        sessions_with_evidence = int(
            completed_with_evidence.get(division.id, 0)
        )

        latest = latest_assessments.get(school.id)
        baseline = baseline_assessments.get(school.id)
        endline = endline_assessments.get(school.id)

        assessment_summary = {
            "latest": _class_assessment_report(
                db, latest, {school.id}, division.id
            ),
            "baseline": _class_assessment_report(
                db, baseline, {school.id}, division.id
            ),
            "endline": _class_assessment_report(
                db, endline, {school.id}, division.id
            ),
            "longitudinal": None,
        }

        if endline is not None:
            longitudinal = get_longitudinal_report(
                db, endline.id, {school.id}
            )
            matched_rows = longitudinal.get("results", [])
            matched_ids = {row["student_id"] for row in matched_rows}

            current_divisions = {}
            if matched_ids:
                current_divisions = dict(
                    db.query(Student.id, Student.class_division_id)
                    .filter(
                        Student.id.in_(matched_ids),
                        Student.data_origin == "PRODUCTION",
                    )
                    .all()
                )

            class_matched = [
                row for row in matched_rows
                if current_divisions.get(row["student_id"]) == division.id
            ]

            def longitudinal_average(key):
                values = [row[key] for row in class_matched]
                return (
                    round(sum(values) / len(values), 2)
                    if values else None
                )

            assessment_summary["longitudinal"] = {
                "baseline_assessment_id": longitudinal[
                    "baseline_assessment_id"
                ],
                "endline_assessment_id": longitudinal[
                    "endline_assessment_id"
                ],
                "matched_students": len(class_matched),
                "average_baseline_percentage": longitudinal_average(
                    "baseline_percentage"
                ),
                "average_endline_percentage": longitudinal_average(
                    "endline_percentage"
                ),
                "average_percentage_point_change": longitudinal_average(
                    "percentage_point_change"
                ),
                "results": class_matched,
                "result_scope": (
                    "matched_students_currently_assigned_to_class_division"
                ),
            }

        attention = []

        if eligible_completed > sessions_with_evidence:
            attention.append({
                "code": "COMPLETED_SESSION_MISSING_EVIDENCE",
                "scope": "class_division",
                "count": eligible_completed - sessions_with_evidence,
            })

        class_tlm = tlm.get(division.id)
        if class_tlm is not None:
            missing_tlm = int(class_tlm.get("missing_tlm_sessions") or 0)
            if missing_tlm > 0:
                attention.append({
                    "code": "SESSION_MISSING_TLM_RECORD",
                    "scope": "class_division",
                    "count": missing_tlm,
                })

        items.append({
            "class_division_id": division.id,
            "school_id": school.id,
            "school_code": school.school_code,
            "school_name": school.school_name,
            "class_level": division.class_level,
            "division": division.division,
            "status": division.status,
            "active_students": int(active_students.get(division.id, 0)),
            "para_teachers": int(para_teachers.get(division.id, 0)),
            "evidence": {
                "eligible_completed_sessions": eligible_completed,
                "sessions_with_evidence": sessions_with_evidence,
                "completeness_percentage": (
                    round(
                        sessions_with_evidence / eligible_completed * 100,
                        2,
                    )
                    if eligible_completed else None
                ),
            },
            "delivery": delivery.get(division.id),
            "delivery_trend": delivery_trend.get(division.id, []),
            "attendance": attendance_by_class.get(division.id),
            "engagement": engagement.get(division.id),
            "tlm": tlm.get(division.id),
            "assessment": assessment_summary,
            "observations": {
                "classroom_observations": 0,
                "classroom_reports_pending": 0,
                "classroom_reports_complete": 0,
                "stem_inspections": 0,
                "stem_reports_pending": 0,
                "stem_reports_complete": 0,
                **classroom_observations.get(division.id, {}),
                **stem_inspections.get(division.id, {}),
            },
            "attention": attention,
        })

    return {
        "items": items,
        "total_class_divisions": len(items),
    }


def get_student_monitoring(
    db: Session,
    filters: ReportingFilters,
    *,
    student_id=None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict:
    query = (
        db.query(Student, ClassDivision, School)
        .join(ClassDivision, ClassDivision.id == Student.class_division_id)
        .join(School, School.id == ClassDivision.school_id)
        .filter(
            Student.data_origin == "PRODUCTION",
            ClassDivision.data_origin == "PRODUCTION",
            School.data_origin == "PRODUCTION",
        )
    )
    if filters.authorized_school_ids is not None:
        query = query.filter(ClassDivision.school_id.in_(filters.authorized_school_ids))
    if filters.school_id is not None:
        query = query.filter(ClassDivision.school_id == filters.school_id)
    if filters.class_division_id is not None:
        query = query.filter(Student.class_division_id == filters.class_division_id)
    if student_id is not None:
        query = query.filter(Student.id == student_id)
    if search:
        search_value = f"%{search.strip()}%"
        query = query.filter(
            Student.full_name.ilike(search_value)
            | Student.student_code.ilike(search_value)
        )
    total = query.count()
    rows = query.order_by(Student.student_code).offset(offset).limit(limit).all()
    page_student_ids = {student.id for student, _, _ in rows}
    attendance_items, _ = get_attendance_groups(
        db,
        AttendanceFilter(
            authorized_school_ids=filters.authorized_school_ids,
            academic_year_id=filters.academic_year_id,
            start_date=filters.start_date,
            end_date=filters.end_date,
            school_id=filters.school_id,
            class_division_id=filters.class_division_id,
            student_id=student_id,
            student_ids=page_student_ids,
        ),
        "student",
        offset=0,
        limit=max(len(page_student_ids), 1),
    )
    attendance_by_student = {
        item["student_id"]: item for item in attendance_items
    }

    # Build assessment summaries for only the students on this page.
    page_school_ids = {school.id for _, _, school in rows}
    assessment_by_school = {}

    if filters.academic_year_id is not None and page_school_ids:
        assessment_rows = (
            db.query(Assessment)
            .filter(
                Assessment.school_id.in_(page_school_ids),
                Assessment.academic_year_id == filters.academic_year_id,
                Assessment.data_origin == "PRODUCTION",
            )
            .order_by(
                Assessment.school_id,
                Assessment.assessment_date.desc(),
                Assessment.sequence_no.desc(),
                Assessment.id.desc(),
            )
            .all()
        )

        for assessment_row in assessment_rows:
            school_assessments = assessment_by_school.setdefault(
                assessment_row.school_id,
                {"latest": None, "baseline": None, "endline": None},
            )
            if school_assessments["latest"] is None:
                school_assessments["latest"] = assessment_row
            if (
                assessment_row.assessment_type == "BASELINE"
                and school_assessments["baseline"] is None
            ):
                school_assessments["baseline"] = assessment_row
            if (
                assessment_row.assessment_type == "ENDLINE"
                and school_assessments["endline"] is None
            ):
                school_assessments["endline"] = assessment_row

    page_assessment_ids = {
        assessment.id
        for school_assessments in assessment_by_school.values()
        for assessment in school_assessments.values()
        if assessment is not None
    }
    student_assessment_results = {}

    if page_assessment_ids and page_student_ids:
        result_rows = (
            db.query(AssessmentResult)
            .filter(
                AssessmentResult.assessment_id.in_(page_assessment_ids),
                AssessmentResult.student_id.in_(page_student_ids),
            )
            .all()
        )
        student_assessment_results = {
            (result.assessment_id, result.student_id): result
            for result in result_rows
        }

    def student_assessment_summary(assessment_row, student):
        if assessment_row is None:
            return None

        result_row = student_assessment_results.get(
            (assessment_row.id, student.id)
        )
        if result_row is None:
            return None

        percentage = (
            round(
                float(
                    result_row.aggregate_marks
                    / assessment_row.maximum_marks
                    * 100
                ),
                2,
            )
            if assessment_row.maximum_marks
            else None
        )
        return {
            "assessment_id": assessment_row.id,
            "assessment_type": assessment_row.assessment_type,
            "sequence_no": assessment_row.sequence_no,
            "name": assessment_row.name,
            "assessment_date": assessment_row.assessment_date,
            "aggregate_marks": result_row.aggregate_marks,
            "maximum_marks": assessment_row.maximum_marks,
            "percentage": percentage,
        }

    items = []
    for student, division, school in rows:
        attendance = attendance_by_student.get(student.id, {
            "eligible_record_count": 0,
            "present_record_count": 0,
            "absent_record_count": 0,
            "attendance_percentage": 0.0,
        })
        items.append({
            "student_id": student.id,
            "student_code": student.student_code,
            "student_name": student.full_name,
            "status": student.status,
            "school_id": school.id,
            "school_code": school.school_code,
            "school_name": school.school_name,
            "class_division_id": division.id,
            "class_level": division.class_level,
            "division": division.division,
            "assessment": {
                "latest": student_assessment_summary(
                    assessment_by_school.get(school.id, {}).get("latest"),
                    student,
                ),
                "baseline": student_assessment_summary(
                    assessment_by_school.get(school.id, {}).get("baseline"),
                    student,
                ),
                "endline": student_assessment_summary(
                    assessment_by_school.get(school.id, {}).get("endline"),
                    student,
                ),
                "percentage_point_change": (
                    round(
                        student_assessment_summary(
                            assessment_by_school.get(school.id, {}).get("endline"),
                            student,
                        )["percentage"]
                        - student_assessment_summary(
                            assessment_by_school.get(school.id, {}).get("baseline"),
                            student,
                        )["percentage"],
                        2,
                    )
                    if (
                        student_assessment_summary(
                            assessment_by_school.get(school.id, {}).get("baseline"),
                            student,
                        ) is not None
                        and student_assessment_summary(
                            assessment_by_school.get(school.id, {}).get("endline"),
                            student,
                        ) is not None
                    )
                    else None
                ),
            },
            "attendance": attendance,
        })
    return {"items": items, "total_students": total, "offset": offset, "limit": limit}


def get_para_teacher_monitoring(db: Session, filters: ReportingFilters) -> dict:
    delivery_items = get_delivery_report(
        db, filters, group_by="para_teacher_school"
    )["items"]
    engagement_items = get_engagement_report(
        db, filters, group_by="para_teacher_school"
    )["items"]
    tlm_items = get_tlm_report(
        db, filters, group_by="para_teacher_school"
    )["items"]

    def pair_key(item):
        return (item["para_teacher_id"], item["school_id"])

    delivery_by_pair = {pair_key(item): item for item in delivery_items}
    engagement_by_pair = {pair_key(item): item for item in engagement_items}
    tlm_by_pair = {pair_key(item): item for item in tlm_items}
    observation_counts = {}

    classroom_query = (
        db.query(
            ClassroomObservation.target_para_teacher_id.label("para_teacher_id"),
            ClassroomObservation.school_id.label("school_id"),
            func.count(ClassroomObservation.id).label("total"),
            func.count(
                case(
                    (
                        ClassroomObservationReport.status == "PENDING",
                        ClassroomObservationReport.id,
                    ),
                    else_=None,
                )
            ).label("pending"),
            func.count(
                case(
                    (
                        ClassroomObservationReport.status == "COMPLETE",
                        ClassroomObservationReport.id,
                    ),
                    else_=None,
                )
            ).label("complete"),
        )
        .join(
            User,
            User.id == ClassroomObservation.target_para_teacher_id,
        )
        .outerjoin(
            ClassroomObservationReport,
            (
                ClassroomObservationReport.observation_id
                == ClassroomObservation.id
            )
            & (ClassroomObservationReport.data_origin == "PRODUCTION"),
        )
        .filter(
            ClassroomObservation.target_para_teacher_id.isnot(None),
            ClassroomObservation.data_origin == "PRODUCTION",
            User.data_origin == "PRODUCTION",
        )
    )

    if filters.authorized_school_ids is not None:
        classroom_query = classroom_query.filter(
            ClassroomObservation.school_id.in_(filters.authorized_school_ids)
        )
    if filters.school_id is not None:
        classroom_query = classroom_query.filter(
            ClassroomObservation.school_id == filters.school_id
        )
    if filters.start_date is not None:
        classroom_query = classroom_query.filter(
            ClassroomObservation.observed_at >= filters.start_date
        )
    if filters.end_date is not None:
        classroom_query = classroom_query.filter(
            ClassroomObservation.observed_at
            < filters.end_date + timedelta(days=1)
        )

    for teacher_id, school_id, total, pending, complete in classroom_query.group_by(
        ClassroomObservation.target_para_teacher_id,
        ClassroomObservation.school_id,
    ).all():
        observation_counts.setdefault((teacher_id, school_id), {}).update(
            {
                "classroom_observations": int(total or 0),
                "classroom_reports_pending": int(pending or 0),
                "classroom_reports_complete": int(complete or 0),
            }
        )

    inspection_query = (
        db.query(
            STEMInspection.para_teacher_id.label("para_teacher_id"),
            STEMInspection.school_id.label("school_id"),
            func.count(STEMInspection.id).label("total"),
            func.count(
                case(
                    (
                        STEMInspectionReport.status == "PENDING",
                        STEMInspectionReport.id,
                    ),
                    else_=None,
                )
            ).label("pending"),
            func.count(
                case(
                    (
                        STEMInspectionReport.status == "COMPLETE",
                        STEMInspectionReport.id,
                    ),
                    else_=None,
                )
            ).label("complete"),
        )
        .join(User, User.id == STEMInspection.para_teacher_id)
        .outerjoin(
            STEMInspectionReport,
            (
                STEMInspectionReport.inspection_id == STEMInspection.id
            )
            & (STEMInspectionReport.data_origin == "PRODUCTION"),
        )
        .filter(
            STEMInspection.data_origin == "PRODUCTION",
            User.data_origin == "PRODUCTION",
        )
    )

    if filters.authorized_school_ids is not None:
        inspection_query = inspection_query.filter(
            STEMInspection.school_id.in_(filters.authorized_school_ids)
        )
    if filters.school_id is not None:
        inspection_query = inspection_query.filter(
            STEMInspection.school_id == filters.school_id
        )
    if filters.start_date is not None:
        inspection_query = inspection_query.filter(
            STEMInspection.inspected_at >= filters.start_date
        )
    if filters.end_date is not None:
        inspection_query = inspection_query.filter(
            STEMInspection.inspected_at < filters.end_date + timedelta(days=1)
        )

    for teacher_id, school_id, total, pending, complete in inspection_query.group_by(
        STEMInspection.para_teacher_id,
        STEMInspection.school_id,
    ).all():
        observation_counts.setdefault((teacher_id, school_id), {}).update(
            {
                "stem_inspections": int(total or 0),
                "stem_reports_pending": int(pending or 0),
                "stem_reports_complete": int(complete or 0),
            }
        )

    teacher_ids = (
        {teacher_id for teacher_id, _school_id in observation_counts}
        | {item["para_teacher_id"] for item in delivery_items}
    )

    # Resolve each teacher's most recent active school assignment.
    today = date.today()
    assignment_rows = (
        db.query(
            UserAssignment.user_id,
            UserAssignment.school_id,
            UserAssignment.start_date,
        )
        .join(User, User.id == UserAssignment.user_id)
        .filter(
            UserAssignment.user_id.in_(teacher_ids),
            UserAssignment.scope_type == "SCHOOL",
            UserAssignment.school_id.is_not(None),
            UserAssignment.is_active.is_(True),
            UserAssignment.start_date <= today,
            (
                UserAssignment.end_date.is_(None)
                | (UserAssignment.end_date >= today)
            ),
            User.data_origin == "PRODUCTION",
        )
        .order_by(
            UserAssignment.user_id,
            UserAssignment.start_date.desc(),
        )
        .all()
    )
    teacher_school_ids = {}
    for user_id, school_id, _start_date in assignment_rows:
        teacher_school_ids.setdefault(user_id, school_id)

    # Include both current assignment schools and schools recorded on
    # authorized observation/inspection records.
    school_ids = (
        set(teacher_school_ids.values())
        | {school_id for _teacher_id, school_id in observation_counts}
        | {item["school_id"] for item in delivery_items}
    )
    if filters.authorized_school_ids is not None:
        school_ids &= filters.authorized_school_ids
    if filters.school_id is not None:
        school_ids &= {filters.school_id}
    schools = {
        school.id: school
        for school in db.query(School)
        .filter(
            School.id.in_(school_ids),
            School.data_origin == "PRODUCTION",
        )
        .all()
    }

    # Each output row represents a teacher-school pair. Session metrics
    # are grouped by the school of each session; observation counts remain
    # attributed to the school recorded on each observation.
    teacher_school_pairs = (
        set(delivery_by_pair)
        | set(engagement_by_pair)
        | set(tlm_by_pair)
        | set(observation_counts)
    )

    # Include schools represented by production sessions in the filtered period.
    session_pair_query = apply_session_filters(
        db,
        production_session_query(db),
        filters,
    ).with_entities(
        TeachingSession.para_teacher_id,
        ClassDivision.school_id,
    ).distinct()

    teacher_school_pairs.update(
        (teacher_id, school_id)
        for teacher_id, school_id in session_pair_query.all()
        if teacher_id is not None
    )
    teacher_school_pairs.update(
        (teacher_id, school_id)
        for teacher_id, school_id in teacher_school_ids.items()
        if school_id in schools
    )
    session_school_ids = {
        school_id for _teacher_id, school_id in teacher_school_pairs
    }
    missing_school_ids = session_school_ids - set(schools)

    if missing_school_ids:
        additional_schools = (
            db.query(School)
            .filter(
                School.id.in_(missing_school_ids),
                School.data_origin == "PRODUCTION",
            )
            .all()
        )
        schools.update({
            school.id: school for school in additional_schools
        })
    items = []
    for teacher_id, school_id in teacher_school_pairs:
        school = schools.get(school_id)
        if school is None:
            continue

        pair = (teacher_id, school_id)
        base = delivery_by_pair.get(pair, {})
        engagement_item = engagement_by_pair.get(pair)
        tlm_item = tlm_by_pair.get(pair)
        teacher = None
        if not base.get("para_teacher_code") or not base.get("para_teacher_name"):
            teacher = db.get(User, teacher_id)

        observations = {
            "classroom_observations": 0,
            "classroom_reports_pending": 0,
            "classroom_reports_complete": 0,
            "stem_inspections": 0,
            "stem_reports_pending": 0,
            "stem_reports_complete": 0,
            **observation_counts.get((teacher_id, school_id), {}),
        }

        item = {
            **base,
            "para_teacher_id": teacher_id,
            "para_teacher_code": (
                base.get("para_teacher_code")
                or (teacher.user_code if teacher is not None else None)
            ),
            "para_teacher_name": (
                base.get("para_teacher_name")
                or (teacher.full_name if teacher is not None else None)
            ),
            "school_id": school.id,
            "school_code": school.school_code,
            "school_name": school.school_name,
            "engagement": engagement_item,
            "tlm": tlm_item,
            "observations": observations,
        }
        items.append(item)

    items.sort(
        key=lambda item: (
            item["school_code"],
            item["para_teacher_code"] or "",
        )
    )
    return {
        "items": items,
        "total_para_teachers": len({item["para_teacher_id"] for item in items}),
    }
