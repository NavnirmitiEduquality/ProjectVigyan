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

    # Enforce the user's school scope at database-query level.
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
