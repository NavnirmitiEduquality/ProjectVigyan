import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assessment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sequence_no: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    maximum_marks: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", server_default="DRAFT")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    imports = relationship("AssessmentImport", back_populates="assessment", cascade="all, delete-orphan")
    results = relationship("AssessmentResult", back_populates="assessment")

    __table_args__ = (
        UniqueConstraint(
            "academic_year_id", "school_id", "assessment_type", "sequence_no",
            name="uq_assessment_event",
        ),
        CheckConstraint(
            "assessment_type IN ('BASELINE', 'MIDLINE', 'ENDLINE')",
            name="ck_assessment_type",
        ),
        CheckConstraint("sequence_no >= 1", name="ck_assessment_sequence"),
        CheckConstraint("maximum_marks > 0", name="ck_assessment_maximum_marks"),
        CheckConstraint(
            "assessment_type = 'MIDLINE' OR sequence_no = 1",
            name="ck_assessment_non_midline_sequence",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'READY_FOR_SUBMISSION', 'SUBMITTED')",
            name="ck_assessment_status",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_assessment_data_origin",
        ),
    )


class AssessmentImport(Base):
    __tablename__ = "assessment_imports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", server_default="DRAFT")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    assessment = relationship("Assessment", back_populates="imports")
    rows = relationship("AssessmentImportRow", back_populates="assessment_import", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'VALIDATED', 'SUBMITTED')",
            name="ck_assessment_import_status",
        ),
        CheckConstraint("total_rows >= 0 AND warning_count >= 0 AND error_count >= 0", name="ck_assessment_import_counts"),
    )


class AssessmentImportRow(Base):
    __tablename__ = "assessment_import_rows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    student_business_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_student_name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_division: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aggregate_marks: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    class_division_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("class_divisions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ERROR", server_default="ERROR")
    validation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    warning_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    assessment_import = relationship("AssessmentImport", back_populates="rows")

    __table_args__ = (
        UniqueConstraint("assessment_import_id", "row_number", name="uq_assessment_import_row_number"),
        CheckConstraint(
            "validation_status IN ('VALID', 'WARNING', 'ERROR', 'MAPPED')",
            name="ck_assessment_import_row_status",
        ),
        CheckConstraint("aggregate_marks IS NULL OR aggregate_marks >= 0", name="ck_assessment_import_row_marks"),
    )


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_business_id: Mapped[str] = mapped_column(String(30), nullable=False)
    aggregate_marks: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    assessment = relationship("Assessment", back_populates="results")

    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", name="uq_assessment_result_student"),
        CheckConstraint("aggregate_marks >= 0", name="ck_assessment_result_marks"),
    )
