from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    require_permission,
    require_school_access,
)
from app.models import Assessment, AssessmentImport, AssessmentImportRow, AssessmentResult, User
from app.services.assessment.service import (
    AssessmentDomainError,
    AssessmentLockedError,
    AssessmentNotFoundError,
    AssessmentService,
)


router = APIRouter(prefix="/api/v1/assessments", tags=["Assessments"])


class AssessmentCreate(BaseModel):
    academic_year_id: UUID
    school_id: UUID
    assessment_type: str
    sequence_no: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    assessment_date: date | None = None
    maximum_marks: Decimal = Field(gt=0)
    data_origin: str = "PRODUCTION"

    @field_validator("assessment_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("data_origin")
    @classmethod
    def normalize_data_origin(cls, value: str) -> str:
        return value.strip().upper()


class ImportRowInput(BaseModel):
    student_business_id: str | None = Field(default=None, max_length=30)
    student_name: str = Field(min_length=1, max_length=150)
    class_: str = Field(alias="class", min_length=1, max_length=20)
    division: str = Field(min_length=1, max_length=20)
    aggregate_marks: Decimal | None = None

    model_config = ConfigDict(populate_by_name=True)


class AssessmentImportInput(BaseModel):
    rows: list[ImportRowInput] = Field(min_length=1)


class RowMappingInput(BaseModel):
    student_id: UUID
    acknowledge_warning: bool = False


class RowMarksInput(BaseModel):
    aggregate_marks: Decimal = Field(ge=0)


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    academic_year_id: UUID
    school_id: UUID
    assessment_type: str
    sequence_no: int
    name: str
    assessment_date: date | None
    maximum_marks: Decimal
    status: str


class ImportRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    row_number: int
    student_business_id: str | None
    source_student_name: str
    source_class: str | None
    source_division: str | None
    aggregate_marks: Decimal | None
    student_id: UUID | None
    validation_status: str
    validation_message: str | None
    is_mapped: bool
    warning_acknowledged: bool


class AssessmentImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    status: str
    total_rows: int
    warning_count: int
    error_count: int
    rows: list[ImportRowResponse]


class AssessmentResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    student_id: UUID
    student_business_id: str
    aggregate_marks: Decimal


def _raise_domain_error(error: AssessmentDomainError) -> None:
    if isinstance(error, AssessmentNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, AssessmentLockedError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def _get_assessment_or_404(db: Session, assessment_id: UUID) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found.")
    return assessment


@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: AssessmentCreate,
    current_user: User = Depends(require_permission("assessment.import")),
    db: Session = Depends(get_db),
):
    require_school_access(payload.school_id, current_user, db)
    try:
        assessment = AssessmentService(db).create_assessment(**payload.model_dump())
        db.commit()
        db.refresh(assessment)
        return assessment
    except AssessmentDomainError as error:
        db.rollback()
        _raise_domain_error(error)

@router.get("", response_model=list[AssessmentResponse])
def list_assessments(
    school_id: UUID | None = None,
    current_user: User = Depends(require_permission("assessment.view")),
    db: Session = Depends(get_db),
):
    query = db.query(Assessment)
    authorized_school_ids = get_authorized_school_ids(current_user, db)
    if authorized_school_ids is not None:
        query = query.filter(Assessment.school_id.in_(authorized_school_ids))
    if school_id is not None:
        require_school_access(school_id, current_user, db)
        query = query.filter(Assessment.school_id == school_id)
    return query.order_by(Assessment.assessment_date, Assessment.name).all()


@router.get("/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(
    assessment_id: UUID,
    current_user: User = Depends(require_permission("assessment.view")),
    db: Session = Depends(get_db),
):
    assessment = _get_assessment_or_404(db, assessment_id)
    require_school_access(assessment.school_id, current_user, db)
    return assessment


@router.post("/{assessment_id}/imports", response_model=AssessmentImportResponse, status_code=status.HTTP_201_CREATED)
def import_assessment_rows(
    assessment_id: UUID,
    payload: AssessmentImportInput,
    current_user: User = Depends(require_permission("assessment.import")),
    db: Session = Depends(get_db),
):
    assessment = _get_assessment_or_404(db, assessment_id)
    require_school_access(assessment.school_id, current_user, db)
    try:
        import_record = AssessmentService(db).import_rows(
            assessment_id=assessment_id,
            created_by_user_id=current_user.id,
            rows=[row.model_dump(by_alias=True) for row in payload.rows],
        )
        db.commit()
        db.refresh(import_record)
        return import_record
    except AssessmentDomainError as error:
        db.rollback()
        _raise_domain_error(error)


@router.patch("/imports/rows/{row_id}/mapping", response_model=ImportRowResponse)
def map_import_row(
    row_id: UUID,
    payload: RowMappingInput,
    current_user: User = Depends(require_permission("assessment.update")),
    db: Session = Depends(get_db),
):
    row = db.get(AssessmentImportRow, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import row not found.")
    require_school_access(row.assessment_import.assessment.school_id, current_user, db)
    try:
        result = AssessmentService(db).map_row(
            import_row_id=row_id,
            student_id=payload.student_id,
            acknowledge_warning=payload.acknowledge_warning,
        )
        db.commit()
        db.refresh(result)
        return result
    except AssessmentDomainError as error:
        db.rollback()
        _raise_domain_error(error)


@router.patch("/imports/rows/{row_id}/acknowledge", response_model=ImportRowResponse)
def acknowledge_import_warning(
    row_id: UUID,
    current_user: User = Depends(require_permission("assessment.update")),
    db: Session = Depends(get_db),
):
    row = db.get(AssessmentImportRow, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import row not found.")
    require_school_access(row.assessment_import.assessment.school_id, current_user, db)
    try:
        result = AssessmentService(db).acknowledge_warning(import_row_id=row_id)
        db.commit()
        db.refresh(result)
        return result
    except AssessmentDomainError as error:
        db.rollback()
        _raise_domain_error(error)


@router.patch("/imports/rows/{row_id}/marks", response_model=ImportRowResponse)
def update_import_row_marks(
    row_id: UUID,
    payload: RowMarksInput,
    current_user: User = Depends(require_permission("assessment.update")),
    db: Session = Depends(get_db),
):
    row = db.get(AssessmentImportRow, row_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import row not found.")
    require_school_access(row.assessment_import.assessment.school_id, current_user, db)
    try:
        result = AssessmentService(db).update_row_marks(
            import_row_id=row_id,
            aggregate_marks=payload.aggregate_marks,
        )
        db.commit()
        db.refresh(result)
        return result
    except AssessmentDomainError as error:
        db.rollback()
        _raise_domain_error(error)


@router.post("/{assessment_id}/submit", response_model=AssessmentResponse)
def submit_assessment(
    assessment_id: UUID,
    current_user: User = Depends(require_permission("assessment.submit")),
    db: Session = Depends(get_db),
):
    assessment = _get_assessment_or_404(db, assessment_id)
    require_school_access(assessment.school_id, current_user, db)
    try:
        result = AssessmentService(db).submit(assessment_id=assessment_id)
        db.commit()
        db.refresh(result)
        return result
    except AssessmentDomainError as error:
        db.rollback()
        _raise_domain_error(error)


@router.get("/{assessment_id}/results", response_model=list[AssessmentResultResponse])
def list_results(
    assessment_id: UUID,
    current_user: User = Depends(require_permission("assessment.view")),
    db: Session = Depends(get_db),
):
    assessment = _get_assessment_or_404(db, assessment_id)
    require_school_access(assessment.school_id, current_user, db)
    return db.query(AssessmentResult).filter(AssessmentResult.assessment_id == assessment_id).all()
