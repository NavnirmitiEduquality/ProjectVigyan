from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import (
    get_authorized_school_ids,
    get_current_user,
    get_user_role_codes,
    require_permission,
    require_school_access,
)
from app.models import (
    ClassroomObservation,
    ObservationReportCorrection,
    PendingReportNotification,
    SchoolTeacher,
    SchoolTeacherSubject,
    STEMInspection,
    UserAssignment,
    User,
    Photo,
)
from app.services.observation_service import (
    AlreadySubmittedError,
    DocumentStorage,
    NotAuthorizedError,
    NotFoundError,
    ObservationError,
    ObservationService,
    PhotoInput,
    ValidationError,
)
from app.services.photo.processing import (
    MAX_FILE_SIZE_BYTES,
    PhotoProcessingError,
)


router = APIRouter(prefix="/api/v1", tags=["Observations and Inspections"])


class TeacherCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    school_id: UUID
    data_origin: str = "PRODUCTION"


class SubjectInput(BaseModel):
    subject: str


class TeacherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    full_name: str
    school_id: UUID
    status: str
    subjects: list[str] = []


class LinkInput(BaseModel):
    external_url: str
    sharing_confirmed: bool


class RecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    school_id: UUID
    class_division_id: UUID | None
    topic: str | None
    observed_at: datetime | None = None
    inspected_at: datetime | None = None
    report_status: str


def _service() -> ObservationService:
    return ObservationService()


def _compensate_failed_transaction(
    db: Session,
    service: ObservationService,
    operation,
    *,
    committed: bool = False,
) -> None:
    db.rollback()
    if committed or operation is None:
        return

    for storage_key in operation.new_storage_keys:
        try:
            service.photo_service.delete(storage_key)
        except Exception:
            # Cleanup failure must not mask the original error.
            pass


def _photo_storage_key(db: Session, record) -> str | None:
    photo = db.get(Photo, record.photo_id)
    return photo.storage_key if photo else None


def _photo_input(
    photo: UploadFile | None,
    captured_at: datetime | None,
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> PhotoInput:
    if (
        photo is None
        or captured_at is None
        or latitude is None
        or longitude is None
    ):
        raise HTTPException(
            status_code=400,
            detail="Photo, captured_at, latitude, and longitude are required.",
        )

    try:
        data = photo.file.read(MAX_FILE_SIZE_BYTES + 1)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read photo.",
        ) from exc

    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Photo upload exceeds the 1 MiB limit.",
        )

    return PhotoInput(
        data,
        captured_at,
        latitude,
        longitude,
        photo.filename,
    )


def _report_file_bytes(report_file: UploadFile) -> bytes:
    max_report_bytes = 5 * 1_048_576

    try:
        data = report_file.file.read(max_report_bytes + 1)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail="Unable to read report file.",
        ) from exc

    if len(data) > max_report_bytes:
        raise HTTPException(
            status_code=413,
            detail="Report upload exceeds the 5 MiB limit.",
        )

    return data


def _error(exc: ObservationError) -> None:
    code = 403 if isinstance(exc, NotAuthorizedError) else 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, AlreadySubmittedError) else 422
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _is_platform_owner(current_user: User, db: Session) -> bool:
    return "PLATFORM_OWNER" in get_user_role_codes(current_user, db)


def _explicit_school_ids(current_user: User, db: Session) -> set[UUID]:
    if _is_platform_owner(current_user, db):
        return set()
    today = datetime.now().date()
    return {
        assignment.school_id
        for assignment in db.query(UserAssignment).filter(
            UserAssignment.user_id == current_user.id,
            UserAssignment.scope_type == "SCHOOL",
            UserAssignment.school_id.is_not(None),
            UserAssignment.is_active.is_(True),
            UserAssignment.start_date <= today,
            (UserAssignment.end_date.is_(None) | (UserAssignment.end_date >= today)),
        ).all()
        if assignment.school_id
    }


def _require_school_teacher_scope(
    school_id: UUID,
    current_user: User,
    db: Session,
) -> None:
    roles = get_user_role_codes(current_user, db)

    # Preserve project-wide access for administrative roles.
    if roles.intersection(
        {"PLATFORM_OWNER", "SYSTEM_ADMIN", "DATA_MANAGER", "MANAGEMENT"}
    ):
        return

    # All other users must have an explicit, active school assignment.
    if school_id not in _explicit_school_ids(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage School Teachers for this school.",
        )


def _can_view_record(record, current_user: User, db: Session) -> bool:
    roles = get_user_role_codes(current_user, db)

    if _is_platform_owner(current_user, db) or roles.intersection(
        {"SYSTEM_ADMIN", "DATA_MANAGER", "MANAGEMENT"}
    ):
        return True

    if isinstance(record, ClassroomObservation):
        if "PARA_TEACHER" in roles:
            return record.observer_id == current_user.id
        if "STEM_COORDINATOR" in roles:
            return get_authorized_school_ids(current_user, db) is None

    if isinstance(record, STEMInspection):
        if "STEM_COORDINATOR" in roles:
            return get_authorized_school_ids(current_user, db) is None

    return False


@router.post("/school-teachers", response_model=TeacherResponse, status_code=201)
def create_school_teacher(payload: TeacherCreate, current_user: User = Depends(require_permission("school_teacher.manage")), db: Session = Depends(get_db)):
    _require_school_teacher_scope(payload.school_id, current_user, db)

    teacher = SchoolTeacher(**payload.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.get("/school-teachers", response_model=list[TeacherResponse])
def list_school_teachers(current_user: User = Depends(require_permission("school_teacher.manage")), db: Session = Depends(get_db)):
    query = db.query(SchoolTeacher)

    roles = get_user_role_codes(current_user, db)
    project_wide_roles = {
        "PLATFORM_OWNER",
        "SYSTEM_ADMIN",
        "DATA_MANAGER",
        "MANAGEMENT",
    }

    if not roles.intersection(project_wide_roles):
        ids = _explicit_school_ids(current_user, db)
        query = query.filter(SchoolTeacher.school_id.in_(ids))
    teachers = query.order_by(SchoolTeacher.full_name).all()
    return [
        TeacherResponse(
            id=t.id,
            full_name=t.full_name,
            school_id=t.school_id,
            status=t.status,
            subjects=[s.subject for s in t.subjects if s.is_active],
        )
        for t in teachers
    ]


@router.patch("/school-teachers/{teacher_id}/status", response_model=TeacherResponse)
def update_school_teacher_status(teacher_id: UUID, active: bool, current_user: User = Depends(require_permission("school_teacher.manage")), db: Session = Depends(get_db)):
    teacher = db.get(SchoolTeacher, teacher_id)
    if not teacher:
        raise HTTPException(404, "School teacher not found.")

    _require_school_teacher_scope(teacher.school_id, current_user, db)
    teacher.status = "ACTIVE" if active else "INACTIVE"
    db.commit()
    db.refresh(teacher)
    return TeacherResponse(id=teacher.id, full_name=teacher.full_name, school_id=teacher.school_id, status=teacher.status, subjects=[s.subject for s in teacher.subjects if s.is_active])


@router.post("/school-teachers/{teacher_id}/subjects", status_code=201)
def add_school_teacher_subject(teacher_id: UUID, payload: SubjectInput, current_user: User = Depends(require_permission("school_teacher.manage")), db: Session = Depends(get_db)):
    teacher = db.get(SchoolTeacher, teacher_id)
    if not teacher:
        raise HTTPException(404, "School teacher not found.")

    _require_school_teacher_scope(teacher.school_id, current_user, db)

    subject = payload.subject.strip().upper()
    if subject not in {"SCIENCE", "EVS"}:
        raise HTTPException(422, "Only Science and EVS are supported.")
    assignment = SchoolTeacherSubject(school_teacher_id=teacher_id, subject=subject)
    db.add(assignment)
    db.commit()
    return {"id": assignment.id, "subject": assignment.subject, "is_active": assignment.is_active}


@router.patch("/school-teachers/{teacher_id}/subjects/{subject_id}")
def update_school_teacher_subject(
    teacher_id: UUID,
    subject_id: UUID,
    active: bool,
    current_user: User = Depends(require_permission("school_teacher.manage")),
    db: Session = Depends(get_db),
):
    assignment = db.query(SchoolTeacherSubject).filter(
        SchoolTeacherSubject.id == subject_id,
        SchoolTeacherSubject.school_teacher_id == teacher_id,
    ).first()
    if not assignment:
        raise HTTPException(404, "School teacher subject assignment not found.")

    teacher = db.get(SchoolTeacher, teacher_id)
    if not teacher:
        raise HTTPException(404, "School teacher not found.")

    _require_school_teacher_scope(teacher.school_id, current_user, db)

    assignment.is_active = active
    db.commit()
    return {"id": assignment.id, "subject": assignment.subject, "is_active": assignment.is_active}


@router.post("/observations/para-teacher", response_model=RecordResponse, status_code=201)
def create_para_observation(
    target_teacher_id: UUID = Form(...),
    class_level: int = Form(...),
    class_division_id: UUID = Form(...),
    topic: str = Form(...),
    photo: UploadFile | None = File(None),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(require_permission("classroom_observation.create")),
    db: Session = Depends(get_db),
):
    service = _service()
    operation = None
    committed = False

    try:
        operation = service.create_para_observation(
            db,
            observer=current_user,
            target_teacher_id=target_teacher_id,
            class_level=class_level,
            class_division_id=class_division_id,
            topic=topic,
            photo=_photo_input(photo, captured_at, latitude, longitude),
        )
        record = operation.record
        db.commit()
        committed = True
        db.refresh(record)

        return RecordResponse(
            id=record.id,
            school_id=record.school_id,
            class_division_id=record.class_division_id,
            topic=record.topic,
            observed_at=record.observed_at,
            report_status=record.report.status,
        )

    except ObservationError as exc:
        _compensate_failed_transaction(
            db, service, operation, committed=committed
        )
        _error(exc)

    except PhotoProcessingError as exc:
        _compensate_failed_transaction(
            db, service, operation, committed=committed
        )
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        raise


@router.post("/observations/school-teacher", response_model=RecordResponse, status_code=201)
def create_school_teacher_observation(
    school_teacher_id: UUID = Form(...),
    class_level: int = Form(...),
    class_division_id: UUID = Form(...),
    subject: str = Form(...),
    topic: str = Form(...),
    photo: UploadFile | None = File(None),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(require_permission("classroom_observation.create")),
    db: Session = Depends(get_db),
):
    service = _service()
    operation = None

    committed = False
    try:
        operation = service.create_school_teacher_observation(
            db,
            observer=current_user,
            school_teacher_id=school_teacher_id,
            class_level=class_level,
            class_division_id=class_division_id,
            subject=subject,
            topic=topic,
            photo=_photo_input(photo, captured_at, latitude, longitude),
        )
        record = operation.record
        db.commit()
        committed = True
        db.refresh(record)

        return RecordResponse(
            id=record.id,
            school_id=record.school_id,
            class_division_id=record.class_division_id,
            topic=record.topic,
            observed_at=record.observed_at,
            report_status=record.report.status,
        )

    except ObservationError as exc:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        _error(exc)

    except PhotoProcessingError as exc:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        raise


@router.post("/inspections", response_model=RecordResponse, status_code=201)
def create_inspection(
    para_teacher_id: UUID = Form(...),
    class_division_id: UUID | None = Form(None),
    topic: str | None = Form(None),
    photo: UploadFile | None = File(None),
    captured_at: datetime | None = Form(None),
    latitude: Decimal | None = Form(None),
    longitude: Decimal | None = Form(None),
    current_user: User = Depends(require_permission("stem_inspection.create")),
    db: Session = Depends(get_db),
):
    service = _service()
    committed = False
    operation = None

    try:
        operation = service.create_inspection(
            db,
            inspector=current_user,
            para_teacher_id=para_teacher_id,
            class_division_id=class_division_id,
            topic=topic,
            photo=_photo_input(photo, captured_at, latitude, longitude),
        )
        record = operation.record
        db.commit()
        committed = True
        db.refresh(record)

        return RecordResponse(
            id=record.id,
            school_id=record.school_id,
            class_division_id=record.class_division_id,
            topic=record.topic,
            inspected_at=record.inspected_at,
            report_status=record.report.status,
        )

    except ObservationError as exc:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        _error(exc)

    except PhotoProcessingError as exc:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        _compensate_failed_transaction(db, service, operation, committed=committed)
        raise


@router.get("/observations", response_model=list[RecordResponse])
def list_observations(current_user: User = Depends(require_permission("classroom_observation.view")), db: Session = Depends(get_db)):
    records = db.query(ClassroomObservation).order_by(ClassroomObservation.observed_at.desc()).all()
    return [_observation_response(r) for r in records if _can_view_record(r, current_user, db)]


@router.get("/observations/{record_id}", response_model=RecordResponse)
def get_observation(record_id: UUID, current_user: User = Depends(require_permission("classroom_observation.view")), db: Session = Depends(get_db)):
    record = db.get(ClassroomObservation, record_id)
    if not record or not _can_view_record(record, current_user, db):
        raise HTTPException(404, "Observation not found.")
    return _observation_response(record)


@router.get("/inspections", response_model=list[RecordResponse])
def list_inspections(current_user: User = Depends(require_permission("stem_inspection.view")), db: Session = Depends(get_db)):
    records = db.query(STEMInspection).order_by(STEMInspection.inspected_at.desc()).all()
    return [_inspection_response(r) for r in records if _can_view_record(r, current_user, db)]


@router.get("/inspections/{record_id}", response_model=RecordResponse)
def get_inspection(record_id: UUID, current_user: User = Depends(require_permission("stem_inspection.view")), db: Session = Depends(get_db)):
    record = db.get(STEMInspection, record_id)
    if not record or not _can_view_record(record, current_user, db):
        raise HTTPException(404, "Inspection not found.")
    return _inspection_response(record)


def _observation_response(record: ClassroomObservation) -> RecordResponse:
    return RecordResponse(id=record.id, school_id=record.school_id, class_division_id=record.class_division_id, topic=record.topic, observed_at=record.observed_at, report_status=record.report.status)


def _inspection_response(record: STEMInspection) -> RecordResponse:
    return RecordResponse(id=record.id, school_id=record.school_id, class_division_id=record.class_division_id, topic=record.topic, inspected_at=record.inspected_at, report_status=record.report.status)


def _report_context(db: Session, kind: str, record_id: UUID):
    if kind == "observation":
        record = db.get(ClassroomObservation, record_id)
        return record, record.report if record else None
    record = db.get(STEMInspection, record_id)
    return record, record.report if record else None


def _can_submit(record, current_user: User, administrative: bool = False) -> bool:
    if administrative:
        return True
    if isinstance(record, ClassroomObservation):
        return record.observer_id == current_user.id
    return record.inspector_id == current_user.id


def _submit_report(
    kind: str,
    record_id: UUID,
    current_user: User,
    db: Session,
    *,
    link: str | None = None,
    sharing_confirmed: bool = False,
    filename: str | None = None,
    content_type: str | None = None,
    data: bytes | None = None,
    administrative: bool = False,
    reason: str | None = None,
):
    record, report = _report_context(db, kind, record_id)
    if not record or not report or not _can_view_record(record, current_user, db):
        raise HTTPException(404, "Record or report not found.")
    if not _can_submit(record, current_user, administrative):
        raise HTTPException(403, "You are not authorized to submit this report.")
    if administrative and (not reason or not reason.strip()):
        raise HTTPException(422, "A non-empty administrative correction reason is required.")
    service = _service()
    previous_reference = report.external_url or report.storage_key
    created_key = None
    committed = False
    try:
        if administrative and report.status == "COMPLETE":
            report.status = "PENDING"
        result, created_key = service.submit_report(
            db, report, user_id=current_user.id, link=link,
            sharing_confirmed=sharing_confirmed, filename=filename,
            content_type=content_type, data=data,
            area="classroom-observations" if kind == "observation" else "stem-inspections",
        )
        if administrative:
            db.add(ObservationReportCorrection(
                observation_report_id=report.id if kind == "observation" else None,
                inspection_report_id=report.id if kind == "inspection" else None,
                actor_id=current_user.id,
                previous_reference=previous_reference,
                replacement_reference=report.external_url or report.storage_key or "",
                reason=reason.strip(),
            ))
        db.commit()
        committed = True
        return {"status": result.status, "mode": result.mode, "externally_hosted": result.mode == "LINK", "external_url": result.external_url}
    except ObservationError as exc:
        try:
            db.rollback()
        finally:
            if created_key and not committed:
                try:
                    service.documents.delete(created_key)
                except Exception:
                    pass
        _error(exc)
    except Exception:
        try:
            db.rollback()
        finally:
            if created_key and not committed:
                try:
                    service.documents.delete(created_key)
                except Exception:
                    pass
        raise


@router.post("/observations/{record_id}/report/link")
def submit_observation_link(record_id: UUID, payload: LinkInput, current_user: User = Depends(require_permission("classroom_observation.report.submit")), db: Session = Depends(get_db)):
    return _submit_report("observation", record_id, current_user, db, link=payload.external_url, sharing_confirmed=payload.sharing_confirmed)


@router.post("/inspections/{record_id}/report/link")
def submit_inspection_link(record_id: UUID, payload: LinkInput, current_user: User = Depends(require_permission("stem_inspection.report.submit")), db: Session = Depends(get_db)):
    return _submit_report("inspection", record_id, current_user, db, link=payload.external_url, sharing_confirmed=payload.sharing_confirmed)


@router.post("/observations/{record_id}/report/upload")
def upload_observation_report(record_id: UUID, report_file: UploadFile = File(...), current_user: User = Depends(require_permission("classroom_observation.report.submit")), db: Session = Depends(get_db)):
    return _submit_report("observation", record_id, current_user, db, filename=report_file.filename, content_type=report_file.content_type, data=_report_file_bytes(report_file))


@router.post("/inspections/{record_id}/report/upload")
def upload_inspection_report(record_id: UUID, report_file: UploadFile = File(...), current_user: User = Depends(require_permission("stem_inspection.report.submit")), db: Session = Depends(get_db)):
    return _submit_report("inspection", record_id, current_user, db, filename=report_file.filename, content_type=report_file.content_type, data=_report_file_bytes(report_file))


@router.post("/observations/{record_id}/report/admin")
def admin_observation_report(record_id: UUID, report_file: UploadFile = File(...), reason: str = Form(...), current_user: User = Depends(require_permission("observation_report.admin_correction")), db: Session = Depends(get_db)):
    return _submit_report("observation", record_id, current_user, db, filename=report_file.filename, content_type=report_file.content_type, data=_report_file_bytes(report_file), administrative=True, reason=reason)


@router.post("/inspections/{record_id}/report/admin")
def admin_inspection_report(record_id: UUID, report_file: UploadFile = File(...), reason: str = Form(...), current_user: User = Depends(require_permission("observation_report.admin_correction")), db: Session = Depends(get_db)):
    return _submit_report("inspection", record_id, current_user, db, filename=report_file.filename, content_type=report_file.content_type, data=_report_file_bytes(report_file), administrative=True, reason=reason)


@router.get("/observations/{record_id}/report")
def get_observation_report(record_id: UUID, current_user: User = Depends(require_permission("classroom_observation.view")), db: Session = Depends(get_db)):
    return _report_response("observation", record_id, current_user, db)


@router.get("/inspections/{record_id}/report")
def get_inspection_report(record_id: UUID, current_user: User = Depends(require_permission("stem_inspection.view")), db: Session = Depends(get_db)):
    return _report_response("inspection", record_id, current_user, db)


def _report_response(kind: str, record_id: UUID, current_user: User, db: Session):
    record, report = _report_context(db, kind, record_id)
    if not record or not report or not _can_view_record(record, current_user, db):
        raise HTTPException(404, "Report not found.")
    if report.mode == "LINK":
        return {"status": report.status, "mode": report.mode, "externally_hosted": True, "external_url": report.external_url}
    if report.mode == "UPLOAD":
        service = _service()
        root = service.documents.root.resolve()
        path = (root / report.storage_key).resolve()

        try:
            path.relative_to(root)
        except ValueError as exc:
            raise HTTPException(
                status_code=500,
                detail="Invalid report storage reference.",
            ) from exc

        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Report file is unavailable.",
            )

        return FileResponse(
            path,
            media_type=report.media_type,
            filename=report.original_filename,
        )


@router.get("/notifications/pending")
def pending_notifications(current_user: User = Depends(require_permission("observation_notification.view")), db: Session = Depends(get_db)):
    items = db.query(PendingReportNotification).filter(PendingReportNotification.recipient_id == current_user.id).order_by(PendingReportNotification.created_at.desc()).all()
    result = []
    for item in items:
        if item.observation_id:
            record = db.get(ClassroomObservation, item.observation_id)
        else:
            record = db.get(STEMInspection, item.inspection_id)
        if record and record.report.status == "PENDING" and _can_view_record(record, current_user, db):
            result.append({"id": item.id, "message": item.message, "observation_id": item.observation_id, "inspection_id": item.inspection_id, "is_read": item.is_read})
    return result
