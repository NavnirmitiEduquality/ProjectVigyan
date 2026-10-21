from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Assessment, AssessmentImport, AssessmentImportRow, AssessmentResult
from app.models.assessment import AssessmentClassDivision
from app.models.student import Student

def get_assessment_report(db: Session, assessment_id, authorized_school_ids) -> dict:
    query = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.data_origin == "PRODUCTION",
    )
    if authorized_school_ids is not None:
        query = query.filter(Assessment.school_id.in_(authorized_school_ids))
    assessment = query.one_or_none()
    if assessment is None:
        raise LookupError("Assessment not found.")
    results = (
        db.query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == assessment.id)
        .order_by(AssessmentResult.student_business_id)
        .all()
    )
    latest_import = (
        db.query(AssessmentImport)
        .filter(AssessmentImport.assessment_id == assessment.id)
        .order_by(
            AssessmentImport.created_at.desc(),
            AssessmentImport.id.desc(),
        )
        .first()
    )

    imported = latest_import.total_rows if latest_import else 0

    if latest_import:
        latest_import_rows = (
            db.query(AssessmentImportRow)
            .filter(AssessmentImportRow.assessment_import_id == latest_import.id)
            .all()
        )
    else:
        latest_import_rows = []

    mapped = sum(1 for row in latest_import_rows if row.is_mapped)

    warning_rows = sum(
        1
        for row in latest_import_rows
        if row.validation_status == "WARNING"
    )

    error_rows = sum(
        1
        for row in latest_import_rows
        if row.validation_status == "ERROR"
    )

    unresolved_warning_rows = sum(
        1
        for row in latest_import_rows
        if row.validation_status in {"WARNING", "MAPPED"}
        and not row.warning_acknowledged
    )

    missing_import_students = sum(
        1
        for row in latest_import_rows
        if row.validation_message == "Student is missing from the import."
    )

    unmatched_student_rows = sum(
        1
        for row in latest_import_rows
        if row.validation_message
        and "Student could not be matched" in row.validation_message
    )

    valid = len(results)
    average_marks = (
        sum((result.aggregate_marks for result in results), Decimal("0")) / valid
        if valid else None
    )
    average_percentage = (
        float(average_marks / assessment.maximum_marks * 100)
        if average_marks is not None else None
    )

    scope_division_ids = [
        row[0]
        for row in (
            db.query(AssessmentClassDivision.class_division_id)
            .filter(
                AssessmentClassDivision.assessment_id == assessment.id
            )
            .all()
        )
    ]

    eligible_students = None
    missing_students = None
    participation_percentage = None

    # Historical assessments without recorded scope remain unknown.
    if scope_division_ids:
        eligible_student_ids = {
            row[0]
            for row in (
                db.query(Student.id)
                .filter(
                    Student.class_division_id.in_(scope_division_ids),
                    Student.status == "ACTIVE",
                    Student.data_origin == "PRODUCTION",
                )
                .all()
            )
        }

        eligible_students = len(eligible_student_ids)
        submitted_student_ids = {
            result.student_id
            for result in results
            if result.student_id in eligible_student_ids
        }
        missing_students = len(eligible_student_ids - submitted_student_ids)

        if eligible_students:
            participation_percentage = round(
                len(submitted_student_ids) / eligible_students * 100,
                2,
            )
    return {
        "assessment_id": assessment.id,
        "academic_year_id": assessment.academic_year_id,
        "school_id": assessment.school_id,
        "assessment_type": assessment.assessment_type,
        "sequence_no": assessment.sequence_no,
        "name": assessment.name,
        "assessment_date": assessment.assessment_date,
        "maximum_marks": assessment.maximum_marks,
        "status": assessment.status,
        "imported_rows": imported,
        "mapped_rows": mapped,
        "valid_submitted_results": valid,
        "warning_rows": warning_rows,
        "error_rows": error_rows,
        "unresolved_warning_rows": unresolved_warning_rows,
        "missing_import_students": missing_import_students,
        "unmatched_student_rows": unmatched_student_rows,
        "eligible_students": eligible_students,
        "missing_students": missing_students,
        "participation_percentage": participation_percentage,
        "average_marks": average_marks,
        "average_percentage": round(average_percentage, 2) if average_percentage is not None else None,
        "results": [
            {
                "student_id": result.student_id,
                "student_business_id": result.student_business_id,
                "aggregate_marks": result.aggregate_marks,
                "maximum_marks": assessment.maximum_marks,
                "percentage": round(float(result.aggregate_marks / assessment.maximum_marks * 100), 2),
            }
            for result in results
        ],
    }


def get_longitudinal_report(db: Session, assessment_id, authorized_school_ids) -> dict:
    current = db.get(Assessment, assessment_id)
    if current is None or current.data_origin != "PRODUCTION":
        raise LookupError("Assessment not found.")
    if (
        authorized_school_ids is not None
        and current.school_id not in authorized_school_ids
    ):
        raise LookupError("Assessment not found.")
    baseline = (
        db.query(Assessment)
        .filter(
            Assessment.school_id == current.school_id,
            Assessment.academic_year_id == current.academic_year_id,
            Assessment.assessment_type == "BASELINE",
            Assessment.data_origin == "PRODUCTION",
        )
        .one_or_none()
    )
    endline = (
        db.query(Assessment)
        .filter(
            Assessment.school_id == current.school_id,
            Assessment.academic_year_id == current.academic_year_id,
            Assessment.assessment_type == "ENDLINE",
            Assessment.data_origin == "PRODUCTION",
        )
        .one_or_none()
    )
    midline_assessments = (
        db.query(Assessment)
        .filter(
            Assessment.school_id == current.school_id,
            Assessment.academic_year_id == current.academic_year_id,
            Assessment.assessment_type == "MIDLINE",
            Assessment.data_origin == "PRODUCTION",
        )
        .order_by(Assessment.sequence_no, Assessment.assessment_date, Assessment.id)
        .all()
    )

    def summarize_midline(assessment):
        results = (
            db.query(AssessmentResult)
            .filter(AssessmentResult.assessment_id == assessment.id)
            .all()
        )
        count = len(results)
        average_marks = (
            sum(
                (result.aggregate_marks for result in results),
                Decimal("0"),
            ) / count
            if count else None
        )
        average_percentage = (
            float(average_marks / assessment.maximum_marks * 100)
            if average_marks is not None else None
        )

        return {
            "assessment_id": assessment.id,
            "sequence_no": assessment.sequence_no,
            "name": assessment.name,
            "assessment_date": assessment.assessment_date,
            "maximum_marks": assessment.maximum_marks,
            "status": assessment.status,
            "valid_submitted_results": count,
            "average_marks": (
                round(float(average_marks), 2)
                if average_marks is not None else None
            ),
            "average_percentage": (
                round(average_percentage, 2)
                if average_percentage is not None else None
            ),
        }

    if baseline is None or endline is None:
        return {
            "baseline_assessment_id": baseline.id if baseline else None,
            "endline_assessment_id": endline.id if endline else None,
            "midline_assessments": [
                summarize_midline(assessment)
                for assessment in midline_assessments
            ],
            "matched_students": 0,
            "baseline_only_students": 0,
            "endline_only_students": 0,
            "average_baseline_percentage": None,
            "average_endline_percentage": None,
            "average_percentage_point_change": None,
            "results": [],
        }
    baseline_results = {
        result.student_id: result
        for result in db.query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == baseline.id)
        .all()
    }
    endline_results = {
        result.student_id: result
        for result in db.query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == endline.id)
        .all()
    }
    matched_ids = sorted(baseline_results.keys() & endline_results.keys(), key=str)
    rows = []
    for student_id in matched_ids:
        before = baseline_results[student_id]
        after = endline_results[student_id]
        baseline_pct = Decimal(before.aggregate_marks) / baseline.maximum_marks * 100
        endline_pct = Decimal(after.aggregate_marks) / endline.maximum_marks * 100
        rows.append(
            {
                "student_id": student_id,
                "baseline_percentage": round(float(baseline_pct), 2),
                "endline_percentage": round(float(endline_pct), 2),
                "percentage_point_change": round(
                    float(endline_pct - baseline_pct), 2
                ),
            }
        )
    average_before = (
        sum(row["baseline_percentage"] for row in rows) / len(rows)
        if rows else None
    )
    average_after = (
        sum(row["endline_percentage"] for row in rows) / len(rows)
        if rows else None
    )
    return {
        "baseline_assessment_id": baseline.id,
        "endline_assessment_id": endline.id,
        "midline_assessments": [
            summarize_midline(assessment)
            for assessment in midline_assessments
        ],
        "matched_students": len(rows),
        "baseline_only_students": len(set(baseline_results) - set(endline_results)),
        "endline_only_students": len(set(endline_results) - set(baseline_results)),
        "average_baseline_percentage": round(average_before, 2)
        if average_before is not None
        else None,
        "average_endline_percentage": round(average_after, 2)
        if average_after is not None
        else None,
        "average_percentage_point_change": round(average_after - average_before, 2)
        if average_before is not None and average_after is not None
        else None,
        "results": rows,
    }
