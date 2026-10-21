import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SchoolTeacher(Base):
    __tablename__ = "school_teachers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    subjects = relationship("SchoolTeacherSubject", back_populates="teacher", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_school_teacher_status"),
        CheckConstraint("data_origin IN ('PRODUCTION', 'DEMO', 'TEST')", name="ck_school_teacher_data_origin"),
    )


class SchoolTeacherSubject(Base):
    __tablename__ = "school_teacher_subjects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("school_teachers.id", ondelete="RESTRICT"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    teacher = relationship("SchoolTeacher", back_populates="subjects")

    __table_args__ = (
        UniqueConstraint("school_teacher_id", "subject", name="uq_school_teacher_subject"),
        CheckConstraint("subject IN ('SCIENCE', 'EVS')", name="ck_school_teacher_subject"),
    )


class ClassroomObservation(Base):
    __tablename__ = "classroom_observations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_para_teacher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    school_teacher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("school_teachers.id", ondelete="RESTRICT"), nullable=True, index=True)
    class_division_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("class_divisions.id", ondelete="RESTRICT"), nullable=False)
    subject: Mapped[str] = mapped_column(String(30), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="RESTRICT"), nullable=False, unique=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    report = relationship("ClassroomObservationReport", back_populates="observation", uselist=False, cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("(target_para_teacher_id IS NOT NULL AND school_teacher_id IS NULL) OR (target_para_teacher_id IS NULL AND school_teacher_id IS NOT NULL)", name="ck_observation_one_target"),
        CheckConstraint("(target_para_teacher_id IS NOT NULL AND subject = 'SCIENCE') OR (target_para_teacher_id IS NULL AND subject IN ('SCIENCE', 'EVS'))", name="ck_observation_subject"),
        CheckConstraint("data_origin IN ('PRODUCTION', 'DEMO', 'TEST')", name="ck_observation_data_origin"),
    )


class STEMInspection(Base):
    __tablename__ = "stem_inspections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    para_teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True)
    class_division_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("class_divisions.id", ondelete="RESTRICT"), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="RESTRICT"), nullable=False, unique=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    report = relationship("STEMInspectionReport", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("data_origin IN ('PRODUCTION', 'DEMO', 'TEST')", name="ck_stem_inspection_data_origin"),)


class ClassroomObservationReport(Base):
    __tablename__ = "classroom_observation_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classroom_observations.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    observation = relationship("ClassroomObservation", back_populates="report")
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'COMPLETE')", name="ck_classroom_report_status"),
        CheckConstraint("mode IS NULL OR mode IN ('UPLOAD', 'LINK')", name="ck_classroom_report_mode"),
        CheckConstraint(
            """
            (status = 'PENDING'
                AND mode IS NULL
                AND storage_key IS NULL
                AND external_url IS NULL)
            OR
            (status = 'COMPLETE' AND mode = 'UPLOAD'
                AND storage_key IS NOT NULL
                AND external_url IS NULL)
            OR
            (status = 'COMPLETE' AND mode = 'LINK'
                AND storage_key IS NULL
                AND external_url IS NOT NULL)
            """,
            name="ck_classroom_report_payload",
        ),
    )


class STEMInspectionReport(Base):
    __tablename__ = "stem_inspection_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stem_inspections.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    data_origin: Mapped[str] = mapped_column(String(20), nullable=False, default="PRODUCTION", server_default="PRODUCTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    inspection = relationship("STEMInspection", back_populates="report")
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'COMPLETE')", name="ck_stem_report_status"),
        CheckConstraint("mode IS NULL OR mode IN ('UPLOAD', 'LINK')", name="ck_stem_report_mode"),
        CheckConstraint(
            """
            (status = 'PENDING'
                AND mode IS NULL
                AND storage_key IS NULL
                AND external_url IS NULL)
            OR
            (status = 'COMPLETE' AND mode = 'UPLOAD'
                AND storage_key IS NOT NULL
                AND external_url IS NULL)
            OR
            (status = 'COMPLETE' AND mode = 'LINK'
                AND storage_key IS NULL
                AND external_url IS NOT NULL)
            """,
            name="ck_stem_report_payload",
        ),
    )


class ObservationReportCorrection(Base):
    __tablename__ = "observation_report_corrections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observation_report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("classroom_observation_reports.id", ondelete="SET NULL"), nullable=True)
    inspection_report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stem_inspection_reports.id", ondelete="SET NULL"), nullable=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    previous_reference: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    replacement_reference: Mapped[str] = mapped_column(String(2048), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_observation_correction_reason",
        ),
        CheckConstraint(
            """
            (observation_report_id IS NOT NULL
                AND inspection_report_id IS NULL)
            OR
            (observation_report_id IS NULL
                AND inspection_report_id IS NOT NULL)
            """,
            name="ck_observation_correction_one_report",
        ),
    )


class PendingReportNotification(Base):
    __tablename__ = "pending_report_notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("classroom_observations.id", ondelete="CASCADE"), nullable=True)
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stem_inspections.id", ondelete="CASCADE"), nullable=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "(observation_id IS NOT NULL AND inspection_id IS NULL) "
            "OR (observation_id IS NULL AND inspection_id IS NOT NULL)",
            name="ck_pending_notification_one_record",
        ),
        Index(
            "uq_pending_notification_observation",
            "recipient_id",
            "observation_id",
            "notification_type",
            unique=True,
            postgresql_where=text("observation_id IS NOT NULL"),
        ),
        Index(
            "uq_pending_notification_inspection",
            "recipient_id",
            "inspection_id",
            "notification_type",
            unique=True,
            postgresql_where=text("inspection_id IS NOT NULL"),
        ),
    )
