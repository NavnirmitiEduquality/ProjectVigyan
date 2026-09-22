import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TeachingSession(Base):
    __tablename__ = "teaching_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    class_division_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "class_divisions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    para_teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    session_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    planned_start_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    planned_end_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    actual_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actual_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    duration_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PLANNED",
        server_default="PLANNED",
    )

    remarks: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    feedback_submitted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    data_origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PRODUCTION",
        server_default="PRODUCTION",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="ck_teaching_session_status",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes >= 0",
            name="ck_teaching_session_duration",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_teaching_session_data_origin",
        ),
        CheckConstraint(
            "(planned_start_time IS NULL AND planned_end_time IS NULL) "
            "OR "
            "(planned_start_time IS NOT NULL "
            "AND planned_end_time IS NOT NULL "
            "AND planned_end_time > planned_start_time)",
            name="ck_teaching_session_planned_time_range",
        ),
    )

    class_division = relationship(
        "ClassDivision",
        back_populates="teaching_sessions",
    )

    para_teacher = relationship(
        "User",
        back_populates="teaching_sessions",
    )
