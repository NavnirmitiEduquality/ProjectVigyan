import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Uuid,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ClassDivision(Base):
    __tablename__ = "class_divisions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    school_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    class_level: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    division: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
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
            "school_id",
            "class_level",
            "division",
            name="uq_class_division_school_level_division",
        ),
        CheckConstraint(
            "class_level IN (5, 6, 7)",
            name="ck_class_division_class_level",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name="ck_class_division_status",
        ),
    )

    school = relationship(
        "School",
        back_populates="class_divisions",
    )

    students = relationship(
        "Student",
        back_populates="class_division",
    )