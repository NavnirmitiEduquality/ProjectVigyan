from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_current_user,
    require_permission,
    require_school_access,
)
from app.models import SessionEngagement, TeachingSession, User


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Engagement"],
)


class EngagementInput(BaseModel):
    score: int = Field(
        ge=1,
        le=5,
    )


class EngagementResponse(BaseModel):
    id: UUID
    teaching_session_id: UUID
    score: int
    data_origin: Literal["PRODUCTION", "DEMO", "TEST"]

    model_config = ConfigDict(
        from_attributes=True
    )


def _get_session(
    session_id: UUID,
    current_user: User,
    db: Session,
) -> TeachingSession:
    teaching_session = (
        db.query(TeachingSession)
        .filter(TeachingSession.id == session_id)
        .first()
    )

    if not teaching_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teaching session not found.",
        )

    school_id = teaching_session.class_division.school_id

    require_school_access(
        school_id=school_id,
        current_user=current_user,
        db=db,
    )

    return teaching_session


@router.get(
    "/{session_id}/engagement",
    response_model=EngagementResponse | None,
)
def get_engagement(
    session_id: UUID,
    current_user=Depends(
        require_permission("engagement.view")
    ),
    db: Session = Depends(get_db),
):
    teaching_session = _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    engagement = (
        db.query(SessionEngagement)
        .filter(
            SessionEngagement.teaching_session_id
            == teaching_session.id
        )
        .first()
    )

    return engagement


@router.post(
    "/{session_id}/engagement",
    response_model=EngagementResponse,
)
def save_engagement(
    session_id: UUID,
    payload: EngagementInput,
    current_user=Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    teaching_session = _get_session(
        session_id=session_id,
        current_user=current_user,
        db=db,
    )

    existing_engagement = (
        db.query(SessionEngagement)
        .filter(
            SessionEngagement.teaching_session_id
            == teaching_session.id
        )
        .first()
    )

    if existing_engagement:
        # Updating an existing engagement record.
        require_permission(
            "engagement.update"
        )(
            current_user=current_user,
            db=db,
        )

        if teaching_session.status != "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Engagement can only be updated "
                    "while the session is in progress."
                ),
            )

        existing_engagement.score = payload.score

        db.commit()
        db.refresh(existing_engagement)

        return existing_engagement

    # Creating the first engagement record.
    require_permission(
        "engagement.create"
    )(
        current_user=current_user,
        db=db,
    )

    if teaching_session.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Engagement can only be recorded "
                "while the session is in progress."
            ),
        )

    engagement = SessionEngagement(
        teaching_session_id=teaching_session.id,
        score=payload.score,
        data_origin="PRODUCTION",
    )

    db.add(engagement)
    db.commit()
    db.refresh(engagement)

    return engagement
