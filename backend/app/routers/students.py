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
from app.models import ClassDivision, Student, User


router = APIRouter(
    prefix="/api/v1/students",
    tags=["Students"],
)


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_code: str
    full_name: str
    gender: str
    roll_no: int
    class_division_id: UUID
    status: str
    data_origin: str


class StudentCreate(BaseModel):
    student_code: str = Field(
        ...,
        min_length=1,
        max_length=30,
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )
    gender: str = Field(
        ...,
        min_length=1,
        max_length=20,
    )
    roll_no: int = Field(
        ...,
        ge=1,
        le=999,
    )
    class_division_id: UUID
    status: str = "ACTIVE"

    @field_validator(
        "student_code",
        "full_name",
        "gender",
    )
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Field must not be empty.")

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


class StudentUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    gender: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
    )
    roll_no: int | None = Field(
        default=None,
        ge=1,
        le=999,
    )
    status: str | None = None

    @field_validator(
        "full_name",
        "gender",
    )
    @classmethod
    def validate_text_fields(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Field must not be empty.")

        return value

    @field_validator("status")
    @classmethod
    def validate_status(
        cls,
        value: str | None,
    ) -> str | None:
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
    response_model=list[StudentResponse],
)
def list_students(
    school_id: UUID | None = None,
    class_division_id: UUID | None = None,
    current_user: User = Depends(
        require_permission("student.view")
    ),
    db: Session = Depends(get_db),
):
    """
    List students visible to the current user.
    """

    authorized_school_ids = get_authorized_school_ids(
        current_user,
        db,
    )

    query = (
        db.query(Student)
        .join(
            ClassDivision,
            Student.class_division_id == ClassDivision.id,
        )
    )

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

    if class_division_id is not None:
        class_division = (
            db.query(ClassDivision)
            .filter(
                ClassDivision.id == class_division_id
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

        query = query.filter(
            Student.class_division_id == class_division_id
        )

    return (
        query
        .order_by(
            ClassDivision.school_id,
            ClassDivision.class_level,
            ClassDivision.division,
            Student.roll_no,
        )
        .all()
    )


@router.get(
    "/{student_id}",
    response_model=StudentResponse,
)
def get_student(
    student_id: UUID,
    current_user: User = Depends(
        require_permission("student.view")
    ),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .join(
            ClassDivision,
            Student.class_division_id == ClassDivision.id,
        )
        .filter(Student.id == student_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found.",
        )

    require_school_access(
        student.class_division.school_id,
        current_user,
        db,
    )

    return student


@router.post(
    "",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_student(
    payload: StudentCreate,
    current_user: User = Depends(
        require_permission("student.create")
    ),
    db: Session = Depends(get_db),
):
    """
    Create a student under an accessible class division.

    Data origin is controlled by the server and is always
    PRODUCTION for this API.
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

    student = Student(
        student_code=payload.student_code,
        full_name=payload.full_name,
        gender=payload.gender,
        roll_no=payload.roll_no,
        class_division_id=payload.class_division_id,
        status=payload.status,
        data_origin="PRODUCTION",
    )

    db.add(student)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        existing_code = (
            db.query(Student)
            .filter(
                Student.student_code
                == payload.student_code
            )
            .first()
        )

        if existing_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A student with this student_code already exists.",
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A student with the same roll number "
                "already exists in this class division."
            ),
        )

    db.refresh(student)

    return student


@router.patch(
    "/{student_id}",
    response_model=StudentResponse,
)
def update_student(
    student_id: UUID,
    payload: StudentUpdate,
    current_user: User = Depends(
        require_permission("student.update")
    ),
    db: Session = Depends(get_db),
):
    """
    Update mutable student fields.

    student_code, class_division_id, and data_origin
    are immutable through this endpoint.
    """

    student = (
        db.query(Student)
        .join(
            ClassDivision,
            Student.class_division_id == ClassDivision.id,
        )
        .filter(Student.id == student_id)
        .first()
    )

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found.",
        )

    require_school_access(
        student.class_division.school_id,
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
        setattr(student, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A student with the same roll number "
                "already exists in this class division."
            ),
        )

    db.refresh(student)

    return student