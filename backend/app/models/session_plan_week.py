import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionPlanWeek(Base):
    __tablename__ = "session_plan_weeks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    para_teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    week_start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    week_end_date: Mapped[date] = mapped_column(
        Date,
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
            "para_teacher_id",
            "week_start_date",
            name="uq_session_plan_week_teacher_start",
        ),
        CheckConstraint(
            "EXTRACT(ISODOW FROM week_start_date) = 1",
            name="ck_session_plan_week_monday_start",
        ),
        CheckConstraint(
            "week_end_date = week_start_date + 6",
            name="ck_session_plan_week_seven_days",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_plan_week_data_origin",
        ),
    )

    para_teacher = relationship(
        "User",
        back_populates="session_plan_weeks",
    )

    # session_plan_week.py
    items = relationship(
        "SessionPlanItem",
        back_populates="session_plan_week",
        cascade="all, delete-orphan",
    )