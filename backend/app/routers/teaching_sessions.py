from datetime import date, time, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
    field_validator,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    require_permission,
    require_school_access,
)
from app.models import ClassDivision, TeachingSession, User


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Teaching Sessions"],
)

class TeachingSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    class_division_id: UUID
    para_teacher_id: UUID
    session_date: date
    planned_start_time: time | None
    planned_end_time: time | None
    actual_start_time: datetime | None
    actual_end_time: datetime | None
    duration_minutes: int | None
    status: str
    remarks: str | None
    feedback_submitted: bool
    submitted_at: datetime | None
    data_origin: str


class TeachingSessionCreate(BaseModel):
    class_division_id: UUID
    session_date: date

    planned_start_time: time | None = None
    planned_end_time: time | None = None

    remarks: str | None = Field(
        default=None,
        max_length=2000,
    )

    @field_validator("remarks")
    @classmethod
    def validate_remarks(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_planned_time_pair(self):
        start_time = self.planned_start_time
        end_time = self.planned_end_time

        if start_time is None and end_time is not None:
            raise ValueError(
                "planned_start_time is required when "
                "planned_end_time is provided."
            )

        if start_time is not None and end_time is None:
            raise ValueError(
                "planned_end_time is required when "
                "planned_start_time is provided."
            )

        if (
            start_time is not None
            and end_time is not None
            and end_time <= start_time
        ):
            raise ValueError(
                "planned_end_time must be later than "
                "planned_start_time."
            )

        return self


@router.post(
    "",
    response_model=TeachingSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_teaching_session(
    payload: TeachingSessionCreate,
    current_user: User = Depends(
        require_permission("session.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Create a planned teaching session.

    The para-teacher is taken from the authenticated user.
    Clients cannot assign a session to another para-teacher.
    """

    class_division = (
        db.query(ClassDivision)
        .filter(
            ClassDivision.id == payload.class_division_id
        )
        .first()
    )

    if not class_division:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class division not found.",
        )

    require_school_access(
        class_division.school_id,
        current_user,
        db,
    )

    teaching_session = TeachingSession(
        class_division_id=class_division.id,
        para_teacher_id=current_user.id,
        session_date=payload.session_date,
        planned_start_time=payload.planned_start_time,
        planned_end_time=payload.planned_end_time,
        remarks=payload.remarks,
        status="PLANNED",
        data_origin="PRODUCTION",
    )

    db.add(teaching_session)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create teaching session.",
        )

    db.refresh(teaching_session)

    return teaching_session
