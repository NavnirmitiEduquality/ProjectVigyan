from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SessionEvidence(Base):
    __tablename__ = "session_evidence"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    teaching_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "teaching_sessions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    photo_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "photos.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    data_origin = Column(
        String(20),
        nullable=False,
        server_default=text("'PRODUCTION'"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "teaching_session_id",
            name="uq_session_evidence_teaching_session",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_evidence_data_origin",
        ),
    )

    teaching_session = relationship(
        "TeachingSession",
        back_populates="session_evidence",
    )

    photo = relationship(
        "Photo",
        back_populates="session_evidence",
        uselist=False,
    )
