import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionPlanItem(Base):
    __tablename__ = "session_plan_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_plan_week_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "session_plan_weeks.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    class_division_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "class_divisions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    planned_date: Mapped[date] = mapped_column(
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

    sequence_no: Mapped[int] = mapped_column(
        SmallInteger,
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
            "session_plan_week_id",
            "sequence_no",
            name="uq_session_plan_item_week_sequence",
        ),
        CheckConstraint(
            "sequence_no > 0",
            name="ck_session_plan_item_sequence_positive",
        ),
        CheckConstraint(
            "(planned_start_time IS NULL "
            "AND planned_end_time IS NULL) "
            "OR "
            "(planned_start_time IS NOT NULL "
            "AND planned_end_time IS NOT NULL "
            "AND planned_end_time > planned_start_time)",
            name="ck_session_plan_item_planned_time_range",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_plan_item_data_origin",
        ),
    )

    session_plan_week = relationship(
        "SessionPlanWeek",
        back_populates="items",
    )

    content = relationship(
        "SessionPlanContent",
        back_populates="session_plan_item",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # session_plan_item.py
    teaching_session = relationship(
        "TeachingSession",
        back_populates="session_plan_item",
        uselist=False,
    )