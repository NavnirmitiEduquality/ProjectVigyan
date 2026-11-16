import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionPlanContent(Base):
    __tablename__ = "session_plan_contents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_plan_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "session_plan_items.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
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
            "session_plan_item_id",
            name="uq_session_plan_content_item",
        ),
    )

    session_plan_item = relationship(
        "SessionPlanItem",
        back_populates="content",
    )

    attachments = relationship(
        "SessionPlanAttachment",
        back_populates="session_plan_content",
        cascade="all, delete-orphan",
    )