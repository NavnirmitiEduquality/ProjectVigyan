from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    get_current_user,
    require_permission,
    require_school_access,
)
from app.models import ClassDivision, School, User


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


class ClassDivisionCreate(BaseModel):
    school_id: UUID
    class_level: int = Field(..., description="Supported classes: 5, 6, or 7")
    division: str = Field(..., min_length=1, max_length=20)
    status: str = "ACTIVE"

    @field_validator("class_level")
    @classmethod
    def validate_class_level(cls, value: int) -> int:
        if value not in {5, 6, 7}:
            raise ValueError("class_level must be 5, 6, or 7.")
        return value

    @field_validator("division")
    @classmethod
    def validate_division(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("division must not be empty.")

        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.upper()

        if value not in {"ACTIVE", "INACTIVE"}:
            raise ValueError(
                "status must be ACTIVE or INACTIVE."
            )

        return value


class ClassDivisionUpdate(BaseModel):
    division: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
    )
    status: str | None = None

    @field_validator("division")
    @classmethod
    def validate_division(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("division must not be empty.")

        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.upper()

        if value not in {"ACTIVE", "INACTIVE"}:
            raise ValueError(
                "status must be ACTIVE or INACTIVE."
            )

        return value


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


@router.post(
    "",
    response_model=ClassDivisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_class_division(
    payload: ClassDivisionCreate,
    current_user: User = Depends(
        require_permission("class.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Create a class/division under an accessible school.

    Data origin is controlled by the server and is always
    PRODUCTION for this API.
    """

    require_school_access(
        payload.school_id,
        current_user,
        db,
    )

    school = (
        db.query(School)
        .filter(School.id == payload.school_id)
        .first()
    )

    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found.",
        )

    class_division = ClassDivision(
        school_id=payload.school_id,
        class_level=payload.class_level,
        division=payload.division,
        status=payload.status,
        data_origin="PRODUCTION",
    )

    db.add(class_division)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A class division with the same school, "
                "class level, and division already exists."
            ),
        )

    db.refresh(class_division)

    return class_division


@router.patch(
    "/{class_division_id}",
    response_model=ClassDivisionResponse,
)
def update_class_division(
    class_division_id: UUID,
    payload: ClassDivisionUpdate,
    current_user: User = Depends(
        require_permission("class.update")
    ),
    db: Session = Depends(get_db),
):
    """
    Update mutable class/division fields.

    school_id, class_level, and data_origin are immutable
    through this endpoint.
    """

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

    updates = payload.model_dump(
        exclude_unset=True,
    )

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update.",
        )

    for field, value in updates.items():
        setattr(class_division, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A class division with the same school, "
                "class level, and division already exists."
            ),
        )

    db.refresh(class_division)

    return class_division
