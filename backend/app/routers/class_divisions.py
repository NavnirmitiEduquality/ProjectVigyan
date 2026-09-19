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
from app.models import ClassDivision, User


router = APIRouter(
    prefix="/api/v1/class-divisions",
    tags=["Class Divisions"],
)


class ClassDivisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    class_level: int
    division: str
    status: str
    data_origin: str


@router.get(
    "",
    response_model=list[ClassDivisionResponse],
)
def list_class_divisions(
    school_id: UUID | None = None,
    current_user: User = Depends(
        require_permission("class.view")
    ),
    db: Session = Depends(get_db),
):
    """
    List class divisions visible to the current user.
    """

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    query = db.query(ClassDivision)

    if authorized_school_ids is not None:
        query = query.filter(
            ClassDivision.school_id.in_(
                authorized_school_ids
            )
        )

    if school_id is not None:
        require_school_access(
            school_id,
            current_user,
            db,
        )

        query = query.filter(
            ClassDivision.school_id == school_id
        )

    return (
        query
        .order_by(
            ClassDivision.school_id,
            ClassDivision.class_level,
            ClassDivision.division,
        )
        .all()
    )


@router.get(
    "/{class_division_id}",
    response_model=ClassDivisionResponse,
)
def get_class_division(
    class_division_id: UUID,
    current_user: User = Depends(
        require_permission("class.view")
    ),
    db: Session = Depends(get_db),
):
    class_division = (
        db.query(ClassDivision)
        .filter(ClassDivision.id == class_division_id)
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

    return class_division
