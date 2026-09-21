from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
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


class SchoolCreate(BaseModel):
    school_code: str = Field(
        min_length=1,
        max_length=20,
    )
    school_name: str = Field(
        min_length=1,
        max_length=200,
    )
    status: str = Field(
        default="ACTIVE",
        pattern="^(ACTIVE|INACTIVE)$",
    )


class SchoolUpdate(BaseModel):
    school_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    status: str | None = Field(
        default=None,
        pattern="^(ACTIVE|INACTIVE)$",
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


@router.post(
    "",
    response_model=SchoolResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_school(
    payload: SchoolCreate,
    current_user: User = Depends(
        require_permission("school.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Create a production school.

    data_origin is controlled by the server and cannot be
    supplied or modified by the API client.
    """

    existing_school = (
        db.query(School)
        .filter(School.school_code == payload.school_code)
        .first()
    )

    if existing_school:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A school with this school code already exists.",
        )

    school = School(
        school_code=payload.school_code,
        school_name=payload.school_name,
        status=payload.status,
        data_origin="PRODUCTION",
    )

    db.add(school)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A school with this school code already exists.",
        )

    db.refresh(school)

    return school


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


@router.patch(
    "/{school_id}",
    response_model=SchoolResponse,
)
def update_school(
    school_id: UUID,
    payload: SchoolUpdate,
    current_user: User = Depends(
        require_permission("school.update")
    ),
    db: Session = Depends(get_db),
):
    """
    Update mutable school fields.

    school_code and data_origin are intentionally immutable
    through this endpoint.
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

    update_data = payload.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    for field, value in update_data.items():
        setattr(school, field, value)

    db.commit()
    db.refresh(school)

    return school
