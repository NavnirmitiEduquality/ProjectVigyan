from datetime import date, time, datetime, timezone
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
    get_authorized_school_ids,
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


@router.get(
    "",
    response_model=list[TeachingSessionResponse],
)
def list_teaching_sessions(
    status_filter: str | None = None,
    session_date: date | None = None,
    class_division_id: UUID | None = None,
    current_user: User = Depends(
        require_permission("session.view")
    ),
    db: Session = Depends(get_db),
):
    """
    List teaching sessions within the current user's
    authorized data scope.

    Project-wide users can see sessions across all schools.
    School-scoped users can see sessions only for their
    authorized schools.
    """

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    query = (
        db.query(TeachingSession)
        .join(
            ClassDivision,
            TeachingSession.class_division_id
            == ClassDivision.id,
        )
    )

    # Apply school-level authorization.
    if authorized_school_ids is not None:
        if not authorized_school_ids:
            return []

        query = query.filter(
            ClassDivision.school_id.in_(
                authorized_school_ids
            )
        )

    # Optional filters.
    if status_filter is not None:
        query = query.filter(
            TeachingSession.status == status_filter
        )

    if session_date is not None:
        query = query.filter(
            TeachingSession.session_date == session_date
        )

    if class_division_id is not None:
        query = query.filter(
            TeachingSession.class_division_id
            == class_division_id
        )

    return (
        query
        .order_by(
            TeachingSession.session_date.desc(),
            TeachingSession.created_at.desc(),
        )
        .all()
    )


@router.get(
    "/{session_id}",
    response_model=TeachingSessionResponse,
)
def get_teaching_session(
    session_id: UUID,
    current_user: User = Depends(
        require_permission("session.view")
    ),
    db: Session = Depends(get_db),
):
    """
    Get a single teaching session within the current
    user's authorized data scope.
    """

    teaching_session = (
        db.query(TeachingSession)
        .join(
            ClassDivision,
            TeachingSession.class_division_id
            == ClassDivision.id,
        )
        .filter(
            TeachingSession.id == session_id
        )
        .first()
    )

    if not teaching_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teaching session not found.",
        )

    require_school_access(
        teaching_session.class_division.school_id,
        current_user,
        db,
    )

    return teaching_session


@router.post(
    "/{session_id}/start",
    response_model=TeachingSessionResponse,
)
def start_teaching_session(
    session_id: UUID,
    current_user: User = Depends(
        require_permission("session.update")
    ),
    db: Session = Depends(get_db),
):
    """
    Start a planned teaching session.

    The transition is server-controlled:
    PLANNED -> IN_PROGRESS
    """

    teaching_session = (
        db.query(TeachingSession)
        .join(
            ClassDivision,
            TeachingSession.class_division_id
            == ClassDivision.id,
        )
        .filter(
            TeachingSession.id == session_id
        )
        .first()
    )

    if not teaching_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teaching session not found.",
        )

    require_school_access(
        teaching_session.class_division.school_id,
        current_user,
        db,
    )

    if teaching_session.status != "PLANNED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only planned teaching sessions "
                "can be started."
            ),
        )

    teaching_session.status = "IN_PROGRESS"
    teaching_session.actual_start_time = datetime.now(timezone.utc)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to start teaching session.",
        )

    db.refresh(teaching_session)

    return teaching_session


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
