from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    AcademicYear,
    Assessment,
    AssessmentClassDivision,
    AssessmentImport,
    AssessmentImportRow,
    AssessmentResult,
    ClassDivision,
    School,
    Student,
)
from datetime import datetime, timezone


class AssessmentDomainError(Exception):
    pass


class AssessmentNotFoundError(AssessmentDomainError):
    pass


class AssessmentLockedError(AssessmentDomainError):
    pass


class AssessmentValidationError(AssessmentDomainError):
    pass


class AssessmentService:
    REQUIRED_IMPORT_COLUMNS = {
        "student_business_id",
        "class",
        "division",
        "aggregate_marks",
    }

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Assessment creation
    # ------------------------------------------------------------------

    def create_assessment(
        self,
        *,
        academic_year_id: UUID,
        school_id: UUID,
        assessment_type: str,
        sequence_no: int | None,
        name: str | None,
        assessment_date,
        maximum_marks: Decimal,
        data_origin: str = "PRODUCTION",
    ) -> Assessment:
        if not isinstance(assessment_type, str):
            raise AssessmentValidationError(
                "assessment_type must be BASELINE, MIDLINE, or ENDLINE."
            )

        assessment_type = assessment_type.strip().upper()
        sequence_no = 1 if sequence_no is None else sequence_no

        if assessment_type not in {"BASELINE", "MIDLINE", "ENDLINE"}:
            raise AssessmentValidationError(
                "assessment_type must be BASELINE, MIDLINE, or ENDLINE."
            )

        if not isinstance(sequence_no, int) or isinstance(sequence_no, bool):
            raise AssessmentValidationError(
                "sequence_no must be an integer."
            )

        if assessment_type == "MIDLINE":
            if sequence_no < 1:
                raise AssessmentValidationError(
                    "MIDLINE sequence_no must be at least 1."
                )
        elif sequence_no != 1:
            raise AssessmentValidationError(
                "BASELINE and ENDLINE sequence_no must be 1."
            )

        try:
            maximum_marks = Decimal(str(maximum_marks))
        except (InvalidOperation, ValueError, TypeError):
            raise AssessmentValidationError(
                "maximum_marks must be numeric."
            )

        if maximum_marks <= 0:
            raise AssessmentValidationError(
                "maximum_marks must be greater than zero."
            )

        data_origin = str(data_origin).strip().upper()

        if data_origin not in {"PRODUCTION", "DEMO", "TEST"}:
            raise AssessmentValidationError(
                "data_origin must be PRODUCTION, DEMO, or TEST."
            )

        if not self.db.get(AcademicYear, academic_year_id):
            raise AssessmentValidationError(
                "Academic year not found."
            )

        if not self.db.get(School, school_id):
            raise AssessmentValidationError(
                "School not found."
            )

        duplicate = (
            self.db.query(Assessment)
            .filter(
                Assessment.academic_year_id == academic_year_id,
                Assessment.school_id == school_id,
                Assessment.assessment_type == assessment_type,
                Assessment.sequence_no == sequence_no,
            )
            .first()
        )

        if duplicate:
            raise AssessmentValidationError(
                "This assessment event already exists."
            )

        generated_name = name or (
            "Baseline"
            if assessment_type == "BASELINE"
            else "Endline"
            if assessment_type == "ENDLINE"
            else f"Midline Assessment {sequence_no}"
        )

        assessment = Assessment(
            academic_year_id=academic_year_id,
            school_id=school_id,
            assessment_type=assessment_type,
            sequence_no=sequence_no,
            name=generated_name,
            assessment_date=assessment_date,
            maximum_marks=maximum_marks,
            data_origin=data_origin,
        )

        # Transaction-neutral:
        # service adds + flushes, but NEVER commits.
        self.db.add(assessment)
        self.db.flush()

        return assessment

    def set_scope(
        self,
        *,
        assessment_id: UUID,
        class_division_ids: list[UUID],
    ) -> Assessment:
        assessment = self._get_assessment(assessment_id)
        self._ensure_editable(assessment)

        if not class_division_ids:
            raise AssessmentValidationError(
                "At least one class/division must be selected."
            )

        if len(class_division_ids) != len(set(class_division_ids)):
            raise AssessmentValidationError(
                "Duplicate class/division IDs are not allowed."
            )

        divisions = (
            self.db.query(ClassDivision)
            .filter(
                ClassDivision.id.in_(class_division_ids),
                ClassDivision.school_id == assessment.school_id,
                ClassDivision.status == "ACTIVE",
            )
            .all()
        )

        if len(divisions) != len(class_division_ids):
            raise AssessmentValidationError(
                "Every selected class/division must be active and belong "
                "to the assessment's school."
            )

        existing_scopes = (
            self.db.query(AssessmentClassDivision)
            .filter(
                AssessmentClassDivision.assessment_id == assessment.id
            )
            .all()
        )
        existing_ids = {
            scope.class_division_id for scope in existing_scopes
        }
        requested_ids = set(class_division_ids)

        if existing_ids == requested_ids:
            return assessment

        # A changed scope invalidates every previous draft import.
        # Keep the rows for traceability, but make them unsubmitable.
        draft_imports = (
            self.db.query(AssessmentImport)
            .filter(AssessmentImport.assessment_id == assessment.id)
            .all()
        )

        for import_record in draft_imports:
            if import_record.status == "SUBMITTED":
                raise AssessmentLockedError(
                    "Submitted assessment imports cannot be re-scoped."
                )

            for row in import_record.rows:
                row.validation_status = "ERROR"
                row.validation_message = (
                    "Assessment scope changed; re-import and validate "
                    "the results under the new scope."
                )
                row.warning_acknowledged = False

            import_record.error_count = len(import_record.rows)
            import_record.warning_count = 0
            import_record.status = "DRAFT"

        for scope in existing_scopes:
            self.db.delete(scope)

        self.db.flush()

        for class_division_id in class_division_ids:
            self.db.add(
                AssessmentClassDivision(
                    assessment_id=assessment.id,
                    class_division_id=class_division_id,
                )
            )

        assessment.status = "DRAFT"
        self.db.flush()
        return assessment

    # ------------------------------------------------------------------
    # Import / validation
    # ------------------------------------------------------------------

    def import_rows(
        self,
        *,
        assessment_id: UUID,
        created_by_user_id: UUID,
        rows: list[dict],
    ) -> AssessmentImport:
        assessment = self._get_assessment(assessment_id)
        self._ensure_editable(assessment)

        if not assessment.class_division_scopes:
            raise AssessmentValidationError(
                "Set the assessment class/division scope before importing."
            )
        scoped_division_ids = {
            scope.class_division_id
            for scope in assessment.class_division_scopes
        }
        if not rows:
            raise AssessmentValidationError(
                "At least one import row is required."
            )

        import_record = AssessmentImport(
            assessment_id=assessment.id,
            created_by_user_id=created_by_user_id,
            total_rows=len(rows),
        )

        self.db.add(import_record)
        self.db.flush()

        seen_codes: set[str] = set()

        for row_number, raw_row in enumerate(rows, start=1):
            if not isinstance(raw_row, dict):
                raise AssessmentValidationError(
                    f"Import row {row_number} is invalid."
                )

            student_code = self._clean_optional(
                raw_row.get("student_business_id")
            )
            source_class = self._clean_optional(
                raw_row.get("class")
            )
            source_division = self._clean_optional(
                raw_row.get("division")
            )

            marks, marks_error = self._parse_marks(
                raw_row.get("aggregate_marks")
            )

            student = None
            message = None
            validation_status = "ERROR"
            is_mapped = False

            # Determine the class/division represented by the row.
            class_division = None
            if source_class and source_division and source_class.isdigit():
                class_division = (
                    self.db.query(ClassDivision)
                    .filter(
                        ClassDivision.school_id == assessment.school_id,
                        ClassDivision.class_level == int(source_class),
                        ClassDivision.division.ilike(source_division),
                    )
                    .first()
                )

            # Validate the Student Business ID.
            if not student_code:
                message = "student_business_id is required."
                validation_status = "ERROR"

            elif student_code in seen_codes:
                message = "Duplicate student_business_id in import."
                validation_status = "ERROR"

            else:
                seen_codes.add(student_code)

                student = (
                    self.db.query(Student)
                    .filter(Student.student_code == student_code)
                    .first()
                )

                if not student:
                    message = (
                        "Student Business ID could not be matched. "
                        "Correct the ID before mapping."
                    )
                    validation_status = "WARNING"

                elif (
                    student.status != "ACTIVE"
                    or student.data_origin != "PRODUCTION"
                ):
                    message = (
                        "Student is not an active production student."
                    )
                    validation_status = "ERROR"
                    student = None

                elif student.class_division.school_id != assessment.school_id:
                    message = "Student is not enrolled in the selected school."
                    validation_status = "ERROR"
                    student = None

                elif (
                    source_class
                    and source_class != str(student.class_division.class_level)
                ) or (
                    source_division
                    and source_division.upper()
                    != student.class_division.division.upper()
                ):
                    message = (
                        "Student class or division does not match the import row."
                    )
                    validation_status = "ERROR"

                elif marks_error:
                    message = marks_error
                    validation_status = "ERROR"

                elif marks is not None and marks > assessment.maximum_marks:
                    message = "aggregate_marks cannot exceed maximum_marks."
                    validation_status = "ERROR"

                else:
                    validation_status = "VALID"
                    is_mapped = True

            # Validate marks independently of identity.
            if marks_error:
                message = marks_error
                validation_status = "ERROR"
            elif marks is not None and marks > assessment.maximum_marks:
                message = "aggregate_marks cannot exceed maximum_marks."
                validation_status = "ERROR"

            resolved_division_id = (
                student.class_division_id
                if student is not None and is_mapped
                else (
                    class_division.id
                    if class_division is not None
                    else None
                )
            )

            if (
                resolved_division_id is not None
                and resolved_division_id not in scoped_division_ids
            ):
                message = "Import row is outside the selected assessment scope."
                validation_status = "ERROR"
                is_mapped = False

            import_row = AssessmentImportRow(
                assessment_import_id=import_record.id,
                row_number=row_number,
                student_business_id=student_code,
                source_class=source_class,
                source_division=source_division,
                aggregate_marks=marks,
                student_id=(
                    student.id if student is not None and is_mapped else None
                ),
                class_division_id=resolved_division_id,
                validation_status=validation_status,
                validation_message=message,
                is_mapped=is_mapped,
                warning_acknowledged=False,
            )

            import_record.rows.append(import_row)

            if validation_status == "ERROR":
                import_record.error_count += 1
            elif validation_status == "WARNING":
                import_record.warning_count += 1

        self.db.flush()

        # --------------------------------------------------------------
        # Missing-student reconciliation
        #
        # IMPORTANT:
        # Reconcile every selected division, including divisions with
        # zero imported rows. The explicit assessment scope defines
        # the expected active-student roster.
        # --------------------------------------------------------------

        next_row_number = len(import_record.rows) + 1

        for class_division_id in scoped_division_ids:
            imported_student_ids = {
                row.student_id
                for row in import_record.rows
                if (
                    row.student_id is not None
                    and row.class_division_id == class_division_id
                )
            }

            query = (
                self.db.query(Student)
                .filter(
                    Student.class_division_id == class_division_id,
                    Student.status == "ACTIVE",
                    Student.data_origin == "PRODUCTION",
                )
            )

            if imported_student_ids:
                query = query.filter(
                    ~Student.id.in_(imported_student_ids)
                )

            missing_students = query.all()

            for missing_student in missing_students:
                import_record.rows.append(
                    AssessmentImportRow(
                        assessment_import_id=import_record.id,
                        row_number=next_row_number,
                        student_business_id=missing_student.student_code,
                        source_class=str(
                            missing_student.class_division.class_level
                        ),
                        source_division=(
                            missing_student.class_division.division
                        ),
                        aggregate_marks=None,
                        student_id=None,
                        class_division_id=class_division_id,
                        validation_status="ERROR",
                        validation_message=(
                            "Student is missing from the import. "
                            "Include this student's Business ID and marks."
                        ),
                        is_mapped=False,
                        warning_acknowledged=False,
                    )
                )

                next_row_number += 1
                import_record.error_count += 1
        import_record.total_rows = len(import_record.rows)

        self.db.flush()

        import_record.status = "VALIDATED"

        assessment.status = (
            "READY_FOR_SUBMISSION"
            if not self._has_blocking_rows(import_record)
            else "DRAFT"
        )

        self.db.flush()

        return import_record

    # ------------------------------------------------------------------
    # Manual mapping
    # ------------------------------------------------------------------

    def update_row_student_business_id(
        self,
        *,
        import_row_id: UUID,
        student_business_id: str,
    ) -> AssessmentImportRow:
        row = self.db.get(
            AssessmentImportRow,
            import_row_id,
        )

        if not row:
            raise AssessmentNotFoundError(
                "Import row not found."
            )

        assessment = row.assessment_import.assessment
        import_record = row.assessment_import

        self._ensure_editable(assessment)

        if import_record.status != "VALIDATED":
            raise AssessmentValidationError(
                "This import is no longer editable. Re-import and validate "
                "the results under the current assessment scope."
            )

        student_business_id = self._clean_optional(
            student_business_id
        )

        if not student_business_id:
            raise AssessmentValidationError(
                "Student Business ID is required."
            )

        # Find another row carrying the corrected Business ID.
        duplicate_code = (
            self.db.query(AssessmentImportRow)
            .filter(
                AssessmentImportRow.assessment_import_id
                == import_record.id,
                AssessmentImportRow.student_business_id
                == student_business_id,
                AssessmentImportRow.id != row.id,
            )
            .first()
        )

        reconciliation_placeholder = None

        if duplicate_code:
            is_reconciliation_placeholder = (
                duplicate_code.aggregate_marks is None
                and duplicate_code.student_id is None
                and duplicate_code.is_mapped is False
                and duplicate_code.validation_status == "ERROR"
                and duplicate_code.validation_message
                == (
                    "Student is missing from the import. "
                    "Include this student's Business ID and marks."
                )
            )

            if not is_reconciliation_placeholder:
                raise AssessmentValidationError(
                    "Duplicate Student Business ID in import."
                )

            reconciliation_placeholder = duplicate_code

        # Resolve the exact production student.
        student = (
            self.db.query(Student)
            .filter(
                Student.student_code == student_business_id
            )
            .first()
        )

        if not student:
            row.student_business_id = student_business_id
            row.student_id = None
            row.is_mapped = False
            row.validation_status = "WARNING"
            row.validation_message = (
                "Student Business ID could not be matched. "
                "Correct the ID before mapping."
            )
            row.warning_acknowledged = False

            self._refresh_import_counts(import_record)
            self.db.flush()
            return row

        if (
            student.status != "ACTIVE"
            or student.data_origin != "PRODUCTION"
        ):
            raise AssessmentValidationError(
                "Only active production students can be mapped."
            )

        if student.class_division.school_id != assessment.school_id:
            raise AssessmentValidationError(
                "Student is not enrolled in the assessment school."
            )

        if (
            row.source_class
            and row.source_class
            != str(student.class_division.class_level)
        ) or (
            row.source_division
            and row.source_division.upper()
            != student.class_division.division.upper()
        ):
            raise AssessmentValidationError(
                "Student class or division does not match "
                "the import row."
            )

        scoped_division_ids = {
            scope.class_division_id
            for scope in assessment.class_division_scopes
        }

        if student.class_division_id not in scoped_division_ids:
            raise AssessmentValidationError(
                "Student is outside the selected assessment scope."
            )

        if (
            row.aggregate_marks is None
            or row.aggregate_marks < 0
            or row.aggregate_marks > assessment.maximum_marks
        ):
            raise AssessmentValidationError(
                "Import row has an invalid aggregate_marks value."
            )

        # Prevent duplicate mapping across imports for this assessment.
        duplicate_mapping = (
            self.db.query(AssessmentImportRow)
            .join(AssessmentImport)
            .filter(
                AssessmentImport.assessment_id == assessment.id,
                AssessmentImportRow.student_id == student.id,
                AssessmentImportRow.id != row.id,
            )
            .first()
        )

        if duplicate_mapping and (
            reconciliation_placeholder is None
            or duplicate_mapping.id != reconciliation_placeholder.id
        ):
            raise AssessmentValidationError(
                "Each student may have only one result per assessment."
            )

        # All validations have passed. Remove only the generated
        # reconciliation placeholder, retaining the original uploaded row.
        if reconciliation_placeholder is not None:
            self.db.delete(reconciliation_placeholder)
            self.db.flush()

        row.student_business_id = student_business_id
        row.student_id = student.id
        row.class_division_id = student.class_division_id
        row.is_mapped = True
        row.validation_status = "VALID"
        row.validation_message = None
        row.warning_acknowledged = False

        self._refresh_import_counts(import_record)
        self.db.flush()

        return row


    def map_row(
        self,
        *,
        import_row_id: UUID,
        student_id: UUID,
        acknowledge_warning: bool,
    ) -> AssessmentImportRow:
        row = self.db.get(
            AssessmentImportRow,
            import_row_id,
        )

        if not row:
            raise AssessmentNotFoundError(
                "Import row not found."
            )

        assessment = row.assessment_import.assessment
        self._ensure_editable(assessment)
        if row.assessment_import.status != "VALIDATED":
            raise AssessmentValidationError(
                "This import is no longer editable. Re-import and validate "
                "the results under the current assessment scope."
            )

        student = self.db.get(Student, student_id)

        if not student:
            raise AssessmentValidationError(
                "Student not found."
            )
        if not row.student_business_id:
            raise AssessmentValidationError(
                "The import row must contain a Student Business ID."
            )

        if row.student_business_id != student.student_code:
            raise AssessmentValidationError(
                "The imported Student Business ID does not match "
                "the selected student."
            )

        if (
            student.status != "ACTIVE"
            or student.data_origin != "PRODUCTION"
        ):
            raise AssessmentValidationError(
                "Only active production students can be mapped."
            )

        if student.class_division.school_id != assessment.school_id:
            raise AssessmentValidationError(
                "Student is not enrolled in the assessment school."
            )
        scoped_division_ids = {
            scope.class_division_id
            for scope in assessment.class_division_scopes
        }

        if not scoped_division_ids:
            raise AssessmentValidationError(
                "Set the assessment class/division scope before mapping."
            )

        if student.class_division_id not in scoped_division_ids:
            raise AssessmentValidationError(
                "Student is outside the selected assessment scope."
            )

        if (
            row.source_class
            and row.source_class
            != str(student.class_division.class_level)
        ) or (
            row.source_division
            and row.source_division.upper()
            != student.class_division.division.upper()
        ):
            raise AssessmentValidationError(
                "Student class or division does not match "
                "the import row."
            )

        if (
            row.aggregate_marks is None
            or row.aggregate_marks < 0
            or row.aggregate_marks > assessment.maximum_marks
        ):
            raise AssessmentValidationError(
                "Import row has an invalid aggregate_marks value."
            )

        # Prevent the same student from being mapped to multiple rows
        # in the same assessment.
        duplicate_mapping = (
            self.db.query(AssessmentImportRow)
            .join(AssessmentImport)
            .filter(
                AssessmentImport.assessment_id == assessment.id,
                AssessmentImportRow.student_id == student.id,
                AssessmentImportRow.id != row.id,
            )
            .first()
        )

        if duplicate_mapping:
            raise AssessmentValidationError(
                "Each student may have only one result per assessment."
            )

        row.student_id = student.id
        row.class_division_id = student.class_division_id
        row.is_mapped = True

        # A manually mapped row remains MAPPED so that the explicit
        # warning acknowledgement decision is preserved.
        row.validation_status = "MAPPED"
        row.validation_message = None
        row.warning_acknowledged = acknowledge_warning

        self._refresh_import_counts(
            row.assessment_import
        )

        self.db.flush()

        return row

    # ------------------------------------------------------------------
    # Warning acknowledgement
    # ------------------------------------------------------------------

    def acknowledge_warning(
        self,
        *,
        import_row_id: UUID,
    ) -> AssessmentImportRow:
        row = self.db.get(
            AssessmentImportRow,
            import_row_id,
        )

        if not row:
            raise AssessmentNotFoundError(
                "Import row not found."
            )

        self._ensure_editable(
            row.assessment_import.assessment
        )

        if row.assessment_import.status != "VALIDATED":
            raise AssessmentValidationError(
                "This import is no longer editable. Re-import and validate "
                "the results under the current assessment scope."
            )
        if row.validation_status != "WARNING":
            raise AssessmentValidationError(
                "Only warning rows can be acknowledged."
            )

        row.warning_acknowledged = True

        self._refresh_import_counts(
            row.assessment_import
        )

        self.db.flush()

        return row

    # ------------------------------------------------------------------
    # Mark correction
    # ------------------------------------------------------------------

    def update_row_marks(
        self,
        *,
        import_row_id: UUID,
        aggregate_marks: Decimal,
    ) -> AssessmentImportRow:
        row = self.db.get(
            AssessmentImportRow,
            import_row_id,
        )

        if not row:
            raise AssessmentNotFoundError(
                "Import row not found."
            )

        assessment = row.assessment_import.assessment
        self._ensure_editable(assessment)

        if row.assessment_import.status != "VALIDATED":
            raise AssessmentValidationError(
                "This import is no longer editable. Re-import and validate "
                "the results under the current assessment scope."
            )

        try:
            aggregate_marks = Decimal(str(aggregate_marks))
        except (InvalidOperation, ValueError, TypeError):
            raise AssessmentValidationError(
                "aggregate_marks must be numeric."
            )

        if aggregate_marks < 0:
            raise AssessmentValidationError(
                "aggregate_marks must not be negative."
            )

        if aggregate_marks > assessment.maximum_marks:
            raise AssessmentValidationError(
                "aggregate_marks cannot exceed maximum_marks."
            )

        row.aggregate_marks = aggregate_marks

        # Preserve the existing acknowledgement workflow for
        # previously manually mapped rows.
        previous_status = row.validation_status
        previous_acknowledgement = row.warning_acknowledged

        # Resolve the exact Student Business ID.
        student = None

        if row.student_business_id:
            student = (
                self.db.query(Student)
                .filter(
                    Student.student_code == row.student_business_id
                )
                .first()
            )

        # An unknown ID cannot be mapped through mark correction.
        if not student:
            row.student_id = None
            row.is_mapped = False
            row.validation_status = "WARNING"
            row.validation_message = (
                "Student Business ID could not be matched. "
                "Correct the ID before mapping."
            )
            row.warning_acknowledged = False

        else:
            # Validate the matched student.
            validation_error = None

            if (
                student.status != "ACTIVE"
                or student.data_origin != "PRODUCTION"
            ):
                validation_error = (
                    "Student is not an active production student."
                )

            elif student.class_division.school_id != assessment.school_id:
                validation_error = (
                    "Student is not enrolled in the selected school."
                )

            elif (
                row.source_class
                and row.source_class
                != str(student.class_division.class_level)
            ) or (
                row.source_division
                and row.source_division.upper()
                != student.class_division.division.upper()
            ):
                validation_error = (
                    "Student class or division does not match "
                    "the import row."
                )

            else:
                scoped_division_ids = {
                    scope.class_division_id
                    for scope in assessment.class_division_scopes
                }

                if student.class_division_id not in scoped_division_ids:
                    validation_error = (
                        "Student is outside the selected assessment scope."
                    )

            if validation_error:
                row.student_id = None
                row.is_mapped = False
                row.validation_status = "ERROR"
                row.validation_message = validation_error
                row.warning_acknowledged = False

            else:
                duplicate_mapping = (
                    self.db.query(AssessmentImportRow)
                    .join(AssessmentImport)
                    .filter(
                        AssessmentImport.assessment_id == assessment.id,
                        AssessmentImportRow.student_id == student.id,
                        AssessmentImportRow.id != row.id,
                    )
                    .first()
                )

                if duplicate_mapping:
                    row.student_id = None
                    row.is_mapped = False
                    row.validation_status = "ERROR"
                    row.validation_message = (
                        "Each student may have only one result per assessment."
                    )
                    row.warning_acknowledged = False

                else:
                    row.student_id = student.id
                    row.class_division_id = student.class_division_id
                    row.is_mapped = True
                    row.validation_message = None

                    if previous_status == "MAPPED":
                        row.validation_status = "MAPPED"
                        row.warning_acknowledged = (
                            previous_acknowledgement
                        )
                    else:
                        row.validation_status = "VALID"
                        row.warning_acknowledged = False

        self._refresh_import_counts(
            row.assessment_import
        )

        self.db.flush()

        return row
    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(
        self,
        *,
        assessment_id: UUID,
        submitted_by_user_id: UUID,
    ) -> Assessment:
        assessment = self._get_assessment(assessment_id)
        self._ensure_editable(assessment)
        if not assessment.class_division_scopes:
            raise AssessmentValidationError(
                "Set the assessment class/division scope before submission."
            )
        import_record = (
            self.db.query(AssessmentImport)
            .filter(AssessmentImport.assessment_id == assessment.id)
            .order_by(
                AssessmentImport.created_at.desc(),
                AssessmentImport.id.desc(),
            )
            .first()
        )

        if not import_record:
            raise AssessmentValidationError(
                "An import is required before submission."
            )
        if import_record.status != "VALIDATED":
            raise AssessmentValidationError(
                "The latest import must be validated before submission."
            )
        self._refresh_import_counts(import_record)
        scoped_division_ids = {
            scope.class_division_id
            for scope in assessment.class_division_scopes
        }

        if not scoped_division_ids:
            raise AssessmentValidationError(
                "Set the assessment class/division scope before submission."
            )

        # --------------------------------------------------------------
        # 1. Validate blocking import rows
        # --------------------------------------------------------------
        blocking = []

        for row in import_record.rows:
            # Any validation error always blocks submission.
            if row.validation_status == "ERROR":
                blocking.append(row)
                continue

            if row.class_division_id not in scoped_division_ids:
                raise AssessmentValidationError(
                    "Import rows must belong to the selected "
                    "assessment scope."
                )

            # Every row must be mapped before submission.
            # Acknowledgement cannot bypass missing students.
            if not row.is_mapped or row.student_id is None:
                blocking.append(row)
                continue

            # Warnings/MAPPED rows must be explicitly acknowledged.
            if (
                row.validation_status in {"WARNING", "MAPPED"}
                and not row.warning_acknowledged
            ):
                blocking.append(row)
                continue

        if blocking:
            raise AssessmentValidationError(
                "Resolve all blocking import rows before submission."
            )
        # --------------------------------------------------------------
        # 2. Validate every mapped row's marks
        # --------------------------------------------------------------
        mapped_rows = [
            row
            for row in import_record.rows
            if row.is_mapped
        ]

        # --------------------------------------------------------------
        # 2. Reconcile against the current eligible student roster
        # --------------------------------------------------------------
        current_roster = {
            (student_id, class_division_id)
            for student_id, class_division_id in (
                self.db.query(
                    Student.id,
                    Student.class_division_id,
                )
                .filter(
                    Student.class_division_id.in_(scoped_division_ids),
                    Student.status == "ACTIVE",
                    Student.data_origin == "PRODUCTION",
                )
                .all()
            )
        }

        imported_roster = {
            (row.student_id, row.class_division_id)
            for row in mapped_rows
        }

        if imported_roster != current_roster:
            raise AssessmentValidationError(
                "The active production student roster has changed since "
                "import validation. Re-import and validate the assessment "
                "against the current roster before submission."
            )

        for row in import_record.rows:
            if not row.is_mapped:
                continue

            if row.student_id is None:
                raise AssessmentValidationError(
                    "Mapped import rows must have a student."
                )

            if row.aggregate_marks is None:
                raise AssessmentValidationError(
                    "Mapped import rows must have aggregate_marks."
                )

            if row.aggregate_marks < 0:
                raise AssessmentValidationError(
                    "Mapped import rows cannot have negative aggregate_marks."
                )

            if row.aggregate_marks > assessment.maximum_marks:
                raise AssessmentValidationError(
                    "Mapped import rows cannot exceed maximum_marks."
                )
        # --------------------------------------------------------------
        # 3. Ensure one student can only occur once
        # --------------------------------------------------------------
        mapped_student_ids = [
            row.student_id
            for row in mapped_rows
        ]

        if len(mapped_student_ids) != len(set(mapped_student_ids)):
            raise AssessmentValidationError(
                "Each student may have only one result per assessment."
            )

        # --------------------------------------------------------------
        # 4. Do not allow submission if results already exist
        # --------------------------------------------------------------
        existing_result = (
            self.db.query(AssessmentResult)
            .filter(
                AssessmentResult.assessment_id == assessment.id
            )
            .first()
        )

        if existing_result:
            raise AssessmentValidationError(
                "Assessment results already exist for this assessment."
            )

        # --------------------------------------------------------------
        # 5. Create results only after complete roster reconciliation.
        # Every eligible student must have exactly one mapped result.
        # --------------------------------------------------------------
        for row in mapped_rows:
            mapped_student = self.db.get(Student, row.student_id)

            if not mapped_student:
                raise AssessmentValidationError(
                    "Mapped student could not be found."
                )

            self.db.add(
                AssessmentResult(
                    assessment_id=assessment.id,
                    student_id=row.student_id,
                    student_business_id=(
                        row.student_business_id
                        or mapped_student.student_code
                    ),
                    aggregate_marks=row.aggregate_marks,
                )
            )

        assessment.submitted_by_user_id = submitted_by_user_id
        assessment.submitted_at = datetime.now(timezone.utc)
        assessment.status = "SUBMITTED"
        import_record.status = "SUBMITTED"

        self.db.flush()

        return assessment
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_assessment(
        self,
        assessment_id: UUID,
    ) -> Assessment:
        assessment = self.db.get(
            Assessment,
            assessment_id,
        )

        if not assessment:
            raise AssessmentNotFoundError(
                "Assessment not found."
            )

        return assessment

    @staticmethod
    def _ensure_editable(
        assessment: Assessment,
    ) -> None:
        if assessment.status == "SUBMITTED":
            raise AssessmentLockedError(
                "Submitted assessments cannot be edited."
            )

    def _refresh_import_counts(
        self,
        import_record: AssessmentImport,
    ) -> None:
        import_record.error_count = sum(
            row.validation_status == "ERROR"
            for row in import_record.rows
        )

        import_record.warning_count = sum(
            (
                row.validation_status in {"WARNING", "MAPPED"}
                and not row.warning_acknowledged
            )
            for row in import_record.rows
        )

        import_record.status = "VALIDATED"
        import_record.total_rows = len(import_record.rows)

        import_record.assessment.status = (
            "READY_FOR_SUBMISSION"
            if not self._has_blocking_rows(import_record)
            else "DRAFT"
        )

    @staticmethod
    def _has_blocking_rows(import_record: AssessmentImport) -> bool:
        for row in import_record.rows:
            if row.validation_status == "ERROR":
                return True

            if not row.is_mapped or row.student_id is None:
                return True

            if (
                row.validation_status in {"WARNING", "MAPPED"}
                and not row.warning_acknowledged
            ):
                return True

        return False

    @staticmethod
    def _clean_optional(
        value,
    ) -> str | None:
        if value is None:
            return None

        value = str(value).strip()

        return value or None

    @staticmethod
    def _clean_required(
        value,
    ) -> str:
        if value is None:
            return ""

        return str(value).strip()

    @staticmethod
    def _parse_marks(
        value,
    ) -> tuple[Decimal | None, str | None]:
        if value is None or str(value).strip() == "":
            return None, "aggregate_marks is required."

        try:
            marks = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None, "aggregate_marks must be numeric."

        if marks < 0:
            return None, "aggregate_marks cannot be negative."

        return marks, None
