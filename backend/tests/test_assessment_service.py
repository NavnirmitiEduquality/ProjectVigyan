from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.database import SessionLocal
from app.models import (
    AcademicYear,
    Assessment,
    AssessmentImport,
    AssessmentResult,
    ClassDivision,
    School,
    Student,
    User,
)
from app.services.assessment.service import (
    AssessmentLockedError,
    AssessmentService,
    AssessmentValidationError,
)


@pytest.fixture
def assessment_context():
    db = SessionLocal()
    suffix = uuid4().hex[:10]
    school = School(
        school_code=f"AT-S-{suffix}",
        school_name="Assessment Test School",
        status="ACTIVE",
        data_origin="TEST",
    )
    other_school = School(
        school_code=f"AT-O-{suffix}",
        school_name="Assessment Other School",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([school, other_school])
    db.flush()
    division = ClassDivision(
        school_id=school.id,
        class_level=5,
        division="A",
        status="ACTIVE",
        data_origin="TEST",
    )
    other_division = ClassDivision(
        school_id=other_school.id,
        class_level=5,
        division="A",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([division, other_division])
    db.flush()
    students = [
        Student(
            student_code=f"AT-ST-{suffix}-{index}",
            full_name=f"Assessment Student {index}",
            gender="OTHER",
            roll_no=index,
            class_division_id=division.id,
            status="ACTIVE",
            data_origin="TEST",
        )
        for index in (1, 2)
    ]
    other_student = Student(
        student_code=f"AT-OS-{suffix}",
        full_name="Other School Student",
        gender="OTHER",
        roll_no=1,
        class_division_id=other_division.id,
        status="ACTIVE",
        data_origin="TEST",
    )
    year = AcademicYear(
        name=f"AT-{suffix}",
        start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31),
        data_origin="TEST",
    )
    user = User(
        user_code=f"AT-U-{suffix}",
        full_name="Assessment Test User",
        email=f"assessment-service-{suffix}@example.com",
        password_hash="not-used-by-service-tests",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add_all([*students, other_student, year, user])
    db.commit()
    context = {
        "db": db,
        "school": school,
        "other_school": other_school,
        "division": division,
        "other_division": other_division,
        "students": students,
        "other_student": other_student,
        "year": year,
        "user": user,
    }
    try:
        yield context
    finally:
        db.rollback()
        assessment_ids = [
            item.id for item in db.query(Assessment).filter(
                Assessment.academic_year_id == year.id
            ).all()
        ]
        if assessment_ids:
            db.query(AssessmentResult).filter(
                AssessmentResult.assessment_id.in_(assessment_ids)
            ).delete(synchronize_session=False)
            db.query(AssessmentImport).filter(
                AssessmentImport.assessment_id.in_(assessment_ids)
            ).delete(synchronize_session=False)
            db.query(Assessment).filter(
                Assessment.id.in_(assessment_ids)
            ).delete(synchronize_session=False)
        db.delete(year)
        db.delete(user)
        db.delete(students[0])
        db.delete(students[1])
        db.delete(other_student)
        db.delete(division)
        db.delete(other_division)
        db.delete(school)
        db.delete(other_school)
        db.commit()
        db.close()


def create_assessment(context, assessment_type="BASELINE", sequence_no=None, maximum_marks=20):
    return AssessmentService(context["db"]).create_assessment(
        academic_year_id=context["year"].id,
        school_id=context["school"].id,
        assessment_type=assessment_type,
        sequence_no=sequence_no,
        name=None,
        assessment_date=date(2026, 5, 1),
        maximum_marks=Decimal(maximum_marks),
        data_origin="TEST",
    )


@pytest.mark.parametrize("assessment_type", ["BASELINE", "MIDLINE", "ENDLINE"])
def test_create_valid_assessment_types(assessment_context, assessment_type):
    assessment = create_assessment(
        assessment_context,
        assessment_type,
        2 if assessment_type == "MIDLINE" else None,
    )
    assert assessment.assessment_type == assessment_type
    assert assessment.sequence_no == (2 if assessment_type == "MIDLINE" else 1)


def test_multiple_midlines_and_duplicate_event_rejection(assessment_context):
    create_assessment(assessment_context, "MIDLINE", 1)
    create_assessment(assessment_context, "MIDLINE", 2)
    with pytest.raises(AssessmentValidationError):
        create_assessment(assessment_context, "MIDLINE", 1)


@pytest.mark.parametrize(
    ("assessment_type", "sequence_no"),
    [("BASELINE", 2), ("ENDLINE", 2), ("MIDLINE", 0)],
)
def test_invalid_sequences_rejected(assessment_context, assessment_type, sequence_no):
    with pytest.raises(AssessmentValidationError):
        create_assessment(assessment_context, assessment_type, sequence_no)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"assessment_type": "INVALID"},
        {"maximum_marks": 0},
        {"maximum_marks": -1},
    ],
)
def test_invalid_assessment_metadata_rejected(assessment_context, kwargs):
    with pytest.raises(AssessmentValidationError):
        create_assessment(assessment_context, **kwargs)


def test_nonexistent_parent_rejected(assessment_context):
    service = AssessmentService(assessment_context["db"])
    with pytest.raises(AssessmentValidationError):
        service.create_assessment(
            academic_year_id=uuid4(),
            school_id=assessment_context["school"].id,
            assessment_type="BASELINE",
            sequence_no=1,
            name=None,
            assessment_date=None,
            maximum_marks=Decimal("10"),
        )
    with pytest.raises(AssessmentValidationError):
        service.create_assessment(
            academic_year_id=assessment_context["year"].id,
            school_id=uuid4(),
            assessment_type="BASELINE",
            sequence_no=1,
            name=None,
            assessment_date=None,
            maximum_marks=Decimal("10"),
        )


def test_import_validation_and_counts(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])
    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": "Different Source Name",
                "class": "5",
                "division": "A",
                "aggregate_marks": "19",
            },
            {
                "student_business_id": "UNKNOWN",
                "student_name": "Unmatched Student",
                "class": "5",
                "division": "A",
                "aggregate_marks": "21",
            },
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": "Duplicate Student",
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
            {
                "student_business_id": None,
                "student_name": "No Business ID",
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )
    assert imported.error_count == 2
    assert imported.warning_count >= 2
    assert any(row.validation_status == "VALID" for row in imported.rows)
    assert any(row.validation_status == "WARNING" for row in imported.rows)


def test_manual_mapping_and_warning_acknowledgement(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])
    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[{
            "student_business_id": "UNKNOWN",
            "student_name": "Needs Mapping",
            "class": "5",
            "division": "A",
            "aggregate_marks": "10",
        }],
    )
    row = imported.rows[0]
    mapped = service.map_row(
        import_row_id=row.id,
        student_id=assessment_context["students"][1].id,
        acknowledge_warning=True,
    )
    assert mapped.is_mapped is True
    assert mapped.validation_status == "MAPPED"
    assert mapped.warning_acknowledged is True

    with pytest.raises(AssessmentValidationError):
        service.map_row(
            import_row_id=row.id,
            student_id=assessment_context["other_student"].id,
            acknowledge_warning=True,
        )


def test_marks_and_submission_locking(assessment_context):
    assessment = create_assessment(assessment_context, maximum_marks=10)
    service = AssessmentService(assessment_context["db"])
    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[{
            "student_business_id": assessment_context["students"][0].student_code,
            "student_name": "Student",
            "class": "5",
            "division": "A",
            "aggregate_marks": "5",
        }],
    )
    row = imported.rows[0]
    corrected = service.update_row_marks(
        import_row_id=row.id,
        aggregate_marks=Decimal("10"),
    )
    assert corrected.aggregate_marks == Decimal("10")
    with pytest.raises(AssessmentValidationError):
        service.update_row_marks(import_row_id=row.id, aggregate_marks=Decimal("11"))

    with pytest.raises(AssessmentValidationError):
        service.submit(assessment_id=assessment.id)
    service.acknowledge_warning(
        import_row_id=next(
            item.id for item in imported.rows
            if item.validation_message == "Student is missing from the import."
        )
    )
    assert [
        (item.validation_status, item.warning_acknowledged, item.validation_message, item.is_mapped)
        for item in imported.rows
    ] == [
        ("VALID", False, None, True),
        ("WARNING", True, "Student is missing from the import.", False),
    ]
    submitted = service.submit(assessment_id=assessment.id)
    assessment_context["db"].commit()
    assert submitted.status == "SUBMITTED"
    assert assessment_context["db"].query(AssessmentResult).filter(
        AssessmentResult.assessment_id == assessment.id
    ).count() == 1
    with pytest.raises(AssessmentLockedError):
        service.import_rows(
            assessment_id=assessment.id,
            created_by_user_id=assessment_context["user"].id,
            rows=[{
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": "Student",
                "class": "5",
                "division": "A",
                "aggregate_marks": "1",
            }],
        )
    with pytest.raises(AssessmentLockedError):
        service.submit(assessment_id=assessment.id)


# ---------------------------------------------------------------------------
# Checkpoint 4.1–4.3 audit tests
# ---------------------------------------------------------------------------


def test_complete_roster_has_no_missing_student_warnings(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
            {
                "student_business_id": assessment_context["students"][1].student_code,
                "student_name": assessment_context["students"][1].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "12",
            },
        ],
    )

    missing_rows = [
        row
        for row in imported.rows
        if row.validation_message == "Student is missing from the import."
    ]

    assert missing_rows == []
    assert imported.warning_count == 0
    assert imported.error_count == 0
    assert len(imported.rows) == 2
    assert all(row.is_mapped for row in imported.rows)
    assert all(row.validation_status == "VALID" for row in imported.rows)


def test_partial_roster_generates_missing_student_warnings(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    missing_rows = [
        row
        for row in imported.rows
        if row.validation_message == "Student is missing from the import."
    ]

    assert len(missing_rows) == 1

    missing_row = missing_rows[0]

    assert missing_row.validation_status == "WARNING"
    assert missing_row.warning_acknowledged is False
    assert missing_row.is_mapped is False
    assert missing_row.student_id is None
    assert missing_row.student_business_id == assessment_context["students"][1].student_code
    assert missing_row.source_student_name == assessment_context["students"][1].full_name
    assert imported.warning_count == 1


def test_unacknowledged_missing_warning_blocks_submission(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    missing_row = next(
        row
        for row in imported.rows
        if row.validation_message == "Student is missing from the import."
    )

    assert missing_row.warning_acknowledged is False

    with pytest.raises(AssessmentValidationError):
        service.submit(assessment_id=assessment.id)

    assert assessment.status != "SUBMITTED"

    result_count = (
        assessment_context["db"]
        .query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == assessment.id)
        .count()
    )
    assert result_count == 0


def test_acknowledged_missing_warning_allows_submission(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    missing_row = next(
        row
        for row in imported.rows
        if row.validation_message == "Student is missing from the import."
    )

    service.acknowledge_warning(import_row_id=missing_row.id)

    assert missing_row.warning_acknowledged is True

    submitted = service.submit(assessment_id=assessment.id)

    assert submitted.status == "SUBMITTED"


def test_acknowledged_missing_student_does_not_create_result(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": assessment_context["students"][0].student_code,
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    missing_student = assessment_context["students"][1]

    missing_row = next(
        row
        for row in imported.rows
        if row.validation_message == "Student is missing from the import."
    )

    assert missing_row.student_id is None
    assert missing_row.is_mapped is False

    service.acknowledge_warning(import_row_id=missing_row.id)

    service.submit(assessment_id=assessment.id)

    results = (
        assessment_context["db"]
        .query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == assessment.id)
        .all()
    )

    assert len(results) == 1
    assert results[0].student_id == assessment_context["students"][0].id
    assert results[0].student_id != missing_student.id

    assert (
        assessment_context["db"]
        .query(AssessmentResult)
        .filter(
            AssessmentResult.assessment_id == assessment.id,
            AssessmentResult.student_id == missing_student.id,
        )
        .count()
        == 0
    )


def test_manual_mapping_of_unknown_student_becomes_mapped(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": "UNKNOWN-STUDENT",
                "student_name": "Assessment Student 1",
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    row = next(
        row
        for row in imported.rows
        if row.student_business_id == "UNKNOWN-STUDENT"
    )

    assert row.validation_status == "WARNING"
    assert row.is_mapped is False
    assert row.student_id is None

    mapped = service.map_row(
        import_row_id=row.id,
        student_id=assessment_context["students"][0].id,
        acknowledge_warning=True,
    )

    assert mapped.student_id == assessment_context["students"][0].id
    assert mapped.class_division_id == assessment_context["division"].id
    assert mapped.is_mapped is True
    assert mapped.validation_status == "MAPPED"
    assert mapped.validation_message is None
    assert mapped.warning_acknowledged is True


def test_mapped_student_with_missing_marks_cannot_submit(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": "UNKNOWN-MISSING-MARKS",
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    row = imported.rows[0]

    service.map_row(
        import_row_id=row.id,
        student_id=assessment_context["students"][0].id,
        acknowledge_warning=True,
    )

    # Deliberately create an invalid staged state so submit()'s
    # defense-in-depth validation is exercised directly.
    row.aggregate_marks = None
    assessment_context["db"].flush()

    with pytest.raises(AssessmentValidationError):
        service.submit(assessment_id=assessment.id)

    assert assessment.status != "SUBMITTED"

    assert (
        assessment_context["db"]
        .query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == assessment.id)
        .count()
        == 0
    )


def test_mapped_student_with_marks_above_maximum_cannot_submit(
    assessment_context,
):
    assessment = create_assessment(
        assessment_context,
        maximum_marks=20,
    )
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": "UNKNOWN-OVER-MAX",
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
        ],
    )

    row = imported.rows[0]

    service.map_row(
        import_row_id=row.id,
        student_id=assessment_context["students"][0].id,
        acknowledge_warning=True,
    )

    # Deliberately create an invalid staged state so submit()'s
    # defense-in-depth validation is exercised directly.
    row.aggregate_marks = Decimal("21")
    assessment_context["db"].flush()

    with pytest.raises(AssessmentValidationError):
        service.submit(assessment_id=assessment.id)

    assert assessment.status != "SUBMITTED"

    assert (
        assessment_context["db"]
        .query(AssessmentResult)
        .filter(AssessmentResult.assessment_id == assessment.id)
        .count()
        == 0
    )


def test_duplicate_mapped_student_cannot_submit(assessment_context):
    assessment = create_assessment(assessment_context)
    service = AssessmentService(assessment_context["db"])

    imported = service.import_rows(
        assessment_id=assessment.id,
        created_by_user_id=assessment_context["user"].id,
        rows=[
            {
                "student_business_id": "UNKNOWN-DUP-1",
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "10",
            },
            {
                "student_business_id": "UNKNOWN-DUP-2",
                "student_name": assessment_context["students"][0].full_name,
                "class": "5",
                "division": "A",
                "aggregate_marks": "12",
            },
        ],
    )

    first_row = next(
        row
        for row in imported.rows
        if row.student_business_id == "UNKNOWN-DUP-1"
    )
    second_row = next(
        row
        for row in imported.rows
        if row.student_business_id == "UNKNOWN-DUP-2"
    )

    service.map_row(
        import_row_id=first_row.id,
        student_id=assessment_context["students"][0].id,
        acknowledge_warning=True,
    )

    with pytest.raises(AssessmentValidationError, match="only one result"):
        service.map_row(
            import_row_id=second_row.id,
            student_id=assessment_context["students"][0].id,
            acknowledge_warning=True,
        )

    assert first_row.is_mapped is True
    assert second_row.is_mapped is False
    assert second_row.student_id is None

    with pytest.raises(AssessmentValidationError):
        service.submit(assessment_id=assessment.id)

    assert assessment.status != "SUBMITTED"

    assert (
        assessment_context["db"]
        .query(AssessmentResult)
        .filter(
            AssessmentResult.assessment_id == assessment.id
        )
        .count()
        == 0
    )
