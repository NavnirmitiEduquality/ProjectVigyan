import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionPlanAttachment(Base):
    __tablename__ = "session_plan_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    session_plan_content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "session_plan_contents.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    storage_key: Mapped[str] = mapped_column(
        String(500),
        unique=True,
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
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
        CheckConstraint(
            "file_size_bytes > 0 AND file_size_bytes <= 5242880",
            name="ck_session_plan_attachment_file_size",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_plan_attachment_data_origin",
        ),
    )

    session_plan_content = relationship(
        "SessionPlanContent",
        back_populates="attachments",
    )
