import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    __table_args__ = (
        Index(
            "ix_audit_events_actor_created",
            "actor_id",
            "created_at",
        ),
        Index(
            "ix_audit_events_target_created",
            "target_type",
            "target_id",
            "created_at",
        ),
        Index(
            "ix_audit_events_action_created",
            "action",
            "created_at",
        ),
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    action: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    target_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    target_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    outcome: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    actor = relationship("User", foreign_keys=[actor_id])
