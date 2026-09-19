from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    get_current_user,
    require_permission,
    require_school_access,
)
from app.models import School, User


router = APIRouter(
    prefix="/api/v1/schools",
    tags=["Schools"],
)


class SchoolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_code: str
    school_name: str
    status: str
    data_origin: str


@router.get(
    "",
    response_model=list[SchoolResponse],
)
def list_schools(
    current_user: User = Depends(
        require_permission("school.view")
    ),
    db: Session = Depends(get_db),
):
    """
    List schools visible to the current user.
    """

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    query = db.query(School)

    if authorized_school_ids is not None:
        query = query.filter(
            School.id.in_(authorized_school_ids)
        )

    return (
        query
        .order_by(School.school_name)
        .all()
    )


@router.get(
    "/{school_id}",
    response_model=SchoolResponse,
)
def get_school(
    school_id: UUID,
    current_user: User = Depends(
        require_permission("school.view")
    ),
    db: Session = Depends(get_db),
):
    """
    Get one school after verifying resource access.
    """

    require_school_access(
        school_id,
        current_user,
        db,
    )

    school = (
        db.query(School)
        .filter(School.id == school_id)
        .first()
    )

    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )

    return school
