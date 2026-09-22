import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionAttendance(Base):
    __tablename__ = "session_attendance"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    teaching_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "teaching_sessions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "students.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
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
        UniqueConstraint(
            "teaching_session_id",
            "student_id",
            name="uq_session_attendance_session_student",
        ),
        CheckConstraint(
            "status IN ('PRESENT', 'ABSENT')",
            name="ck_session_attendance_status",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_attendance_data_origin",
        ),
    )

    teaching_session = relationship(
        "TeachingSession",
        back_populates="attendance_records",
    )

    student = relationship(
        "Student",
        back_populates="attendance_records",
    )
