import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionTLM(Base):
    __tablename__ = "session_tlms"

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

    tlm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "tlm.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    usage: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    photo_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "photos.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        unique=True,
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
            "tlm_id",
            name="uq_session_tlm_session_tlm",
        ),
        CheckConstraint(
            "quantity >= 0",
            name="ck_session_tlm_quantity_nonnegative",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_tlm_data_origin",
        ),
    )

    teaching_session = relationship(
        "TeachingSession",
        back_populates="session_tlms",
    )

    tlm = relationship(
        "TLM",
        back_populates="session_tlms",
    )

    photo = relationship(
        "Photo",
        back_populates="session_tlm",
        uselist=False,
    )
