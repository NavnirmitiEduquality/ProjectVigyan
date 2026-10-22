import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanningNotification(Base):
    __tablename__ = "planning_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    para_teacher_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("session_plan_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    week_start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    message: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
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
            """
            (
                notification_type = 'WEEKLY_PLANNING_NONCOMPLIANCE'
                AND session_plan_item_id IS NULL
                AND week_start_date IS NOT NULL
                AND EXTRACT(ISODOW FROM week_start_date) = 1
            )
            OR
            (
                notification_type = 'SESSION_RESCHEDULE_REQUIRED'
                AND session_plan_item_id IS NOT NULL
                AND week_start_date IS NULL
            )
            """,
            name="ck_planning_notification_event_reference",
        ),
        Index(
            "uq_planning_notification_weekly",
            "recipient_id",
            "para_teacher_id",
            "week_start_date",
            "notification_type",
            unique=True,
            postgresql_where=(
                notification_type == "WEEKLY_PLANNING_NONCOMPLIANCE"
            ),
        ),
        Index(
            "uq_planning_notification_reschedule",
            "recipient_id",
            "session_plan_item_id",
            "notification_type",
            unique=True,
            postgresql_where=(
                notification_type == "SESSION_RESCHEDULE_REQUIRED"
            ),
        ),
    )
