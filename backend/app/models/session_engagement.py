import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionEngagement(Base):
    __tablename__ = "session_engagement"

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

    score: Mapped[int] = mapped_column(
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
            "teaching_session_id",
            name="uq_session_engagement_teaching_session",
        ),
        CheckConstraint(
            "score >= 1 AND score <= 10",
            name="ck_session_engagement_score",
        ),
        CheckConstraint(
            "data_origin IN ('PRODUCTION', 'DEMO', 'TEST')",
            name="ck_session_engagement_data_origin",
        ),
    )

    teaching_session = relationship(
        "TeachingSession",
        back_populates="engagement",
    )
