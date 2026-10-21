from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    ClassDivision,
    ClassroomObservation,
    ClassroomObservationReport,
    ObservationReportCorrection,
    PendingReportNotification,
    SchoolTeacher,
    SchoolTeacherSubject,
    STEMInspection,
    STEMInspectionReport,
    User,
    UserAssignment,
)
from app.services.photo import LocalPrivatePhotoStorage, PhotoProcessingService, PhotoService


MAX_REPORT_BYTES = 5 * 1_048_576
REPORT_EXTENSIONS = {".pdf", ".docx", ".txt"}
REPORT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


class ObservationError(Exception):
    pass


class NotFoundError(ObservationError):
    pass


class ValidationError(ObservationError):
    pass


class NotAuthorizedError(ObservationError):
    pass


class AlreadySubmittedError(ObservationError):
    pass


@dataclass(frozen=True)
class PhotoInput:
    image_bytes: bytes
    captured_at: datetime
    latitude: Decimal
    longitude: Decimal
    original_filename: str | None
    data_origin: str = "PRODUCTION"


@dataclass(frozen=True)
class ObservationOperation:
    """Result of creating an observation or inspection.

    The caller owns the database transaction and must remove
    new storage objects if that transaction fails.
    """

    record: ClassroomObservation | STEMInspection
    new_storage_keys: tuple[str, ...] = ()

    def __getattr__(self, name: str):
        return getattr(self.record, name)


class DocumentStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("storage") / "reports"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, extension: str, area: str) -> str:
        if not data:
            raise ValidationError("Report file cannot be empty.")
        key = f"{area}/{secrets.token_urlsafe(32)}{extension}"
        destination = (self.root / key).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return key

    def delete(self, key: str) -> None:
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError("Invalid report storage key.") from exc
        if path.is_file():
            path.unlink()

    def open(self, key: str) -> BinaryIO:
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError("Invalid report storage key.") from exc
        return path.open("rb")


class ObservationService:
    def __init__(self, photo_service: PhotoService | None = None, document_storage: DocumentStorage | None = None) -> None:
        self.photo_service = photo_service or PhotoService(
            PhotoProcessingService(),
            LocalPrivatePhotoStorage(Path("storage") / "photos"),
        )
        self.documents = document_storage or DocumentStorage()


    @staticmethod
    def active_assignment(db: Session, user_id: UUID, school_id: UUID):
        today = date.today()
        return db.query(UserAssignment).filter(
            UserAssignment.user_id == user_id,
            UserAssignment.is_active.is_(True),
            UserAssignment.start_date <= today,
            (
                UserAssignment.end_date.is_(None)
                | (UserAssignment.end_date >= today)
            ),
            (
                (UserAssignment.scope_type == "PROJECT")
                | (
                    (UserAssignment.scope_type == "SCHOOL")
                    & (UserAssignment.school_id == school_id)
                )
            ),
        ).first()


    @staticmethod
    def teacher_school(db: Session, teacher_id: UUID) -> UUID:
        assignment = db.query(UserAssignment).filter(
            UserAssignment.user_id == teacher_id,
            UserAssignment.scope_type == "SCHOOL",
            UserAssignment.school_id.is_not(None),
            UserAssignment.is_active.is_(True),
            UserAssignment.start_date <= date.today(),
            (UserAssignment.end_date.is_(None) | (UserAssignment.end_date >= date.today())),
        ).order_by(UserAssignment.start_date.desc()).first()
        if not assignment or not assignment.school_id:
            raise NotFoundError("Target para teacher has no active school assignment.")
        return assignment.school_id

    @staticmethod
    def division(db: Session, school_id: UUID, class_division_id: UUID, class_level: int) -> ClassDivision:
        division = db.get(ClassDivision, class_division_id)
        if not division or division.school_id != school_id or division.class_level != class_level or division.status != "ACTIVE":
            raise ValidationError("Class division does not match the target school and class.")
        return division

    def create_photo(self, db: Session, photo: PhotoInput, category: str):
        if not photo.captured_at or photo.latitude is None or photo.longitude is None:
            raise ValidationError("Photo timestamp and GPS metadata are required.")
        return self.photo_service.create_photo(
            db,
            photo.image_bytes,
            photo_category=category,
            captured_at=photo.captured_at,
            latitude=photo.latitude,
            longitude=photo.longitude,
            original_filename=photo.original_filename,
            data_origin=photo.data_origin,
        )

    def create_para_observation(self, db: Session, *, observer: User, target_teacher_id: UUID, class_level: int, class_division_id: UUID, topic: str, photo: PhotoInput, data_origin: str = "PRODUCTION") -> ObservationOperation:
        if target_teacher_id == observer.id:
            raise ValidationError("A para teacher cannot observe themselves.")
        if class_level not in {5, 6, 7} or not topic.strip():
            raise ValidationError("Class must be 5, 6, or 7 and topic is required.")
        school_id = self.teacher_school(db, target_teacher_id)
        self.division(db, school_id, class_division_id, class_level)
        created_photo = None
        try:
            created_photo = self.create_photo(db, photo, "CLASSROOM_OBSERVATION")
            record = ClassroomObservation(
                observer_id=observer.id,
                school_id=school_id,
                target_para_teacher_id=target_teacher_id,
                class_division_id=class_division_id,
                subject="SCIENCE",
                topic=topic.strip(),
                photo_id=created_photo.id,
                observed_at=datetime.now(timezone.utc),
                data_origin=data_origin,
            )
            db.add(record)
            db.flush()
            db.add(ClassroomObservationReport(observation_id=record.id, data_origin=data_origin))
            self.create_notification(
                db,
                recipient_id=observer.id,
                observation_id=record.id,
                message="Your classroom observation report is pending.",
            )
            db.flush()
            return ObservationOperation(
                record=record,
                new_storage_keys=(created_photo.storage_key,),
            )
        except Exception:
            if created_photo:
                try:
                    self.photo_service.delete(created_photo.storage_key)
                except Exception:
                    # Preserve the original database or service exception.
                    pass
            raise

    def create_school_teacher_observation(self, db: Session, *, observer: User, school_teacher_id: UUID, class_level: int, class_division_id: UUID, subject: str, topic: str, photo: PhotoInput, data_origin: str = "PRODUCTION") -> ObservationOperation:
        teacher = db.get(SchoolTeacher, school_teacher_id)
        subject = subject.strip().upper()
        if not teacher or teacher.status != "ACTIVE":
            raise NotFoundError("Active school teacher not found.")
        if class_level not in {5, 6, 7} or not topic.strip():
            raise ValidationError("Class must be 5, 6, or 7 and topic is required.")
        configured = db.query(SchoolTeacherSubject).filter_by(
            school_teacher_id=school_teacher_id, subject=subject, is_active=True,
        ).first()
        if not configured:
            raise ValidationError("Subject is not actively configured for this teacher.")
        self.division(db, teacher.school_id, class_division_id, class_level)
        created_photo = None
        try:
            created_photo = self.create_photo(db, photo, "CLASSROOM_OBSERVATION")
            record = ClassroomObservation(
                observer_id=observer.id, school_id=teacher.school_id,
                school_teacher_id=school_teacher_id, class_division_id=class_division_id,
                subject=subject, topic=topic.strip(), photo_id=created_photo.id,
                observed_at=datetime.now(timezone.utc), data_origin=data_origin,
            )
            db.add(record)
            db.flush()
            db.add(ClassroomObservationReport(observation_id=record.id, data_origin=data_origin))
            self.create_notification(
                db,
                recipient_id=observer.id,
                observation_id=record.id,
                message="Your classroom observation report is pending.",
            )
            db.flush()
            return ObservationOperation(
                record=record,
                new_storage_keys=(created_photo.storage_key,),
            )
        except Exception:
            if created_photo:
                try:
                    self.photo_service.delete(created_photo.storage_key)
                except Exception:
                    # Preserve the original database or service exception.
                    pass
            raise

    def create_inspection(self, db: Session, *, inspector: User, para_teacher_id: UUID, class_division_id: UUID | None, topic: str | None, photo: PhotoInput, data_origin: str = "PRODUCTION") -> ObservationOperation:
        school_id = self.teacher_school(db, para_teacher_id)
        if not self.active_assignment(db, inspector.id, school_id):
            raise NotAuthorizedError("STEM Coordinator is not authorized for this school.")
        if class_division_id:
            division = db.get(ClassDivision, class_division_id)
            if not division or division.school_id != school_id or division.status != "ACTIVE":
                raise ValidationError("Inspection class division does not match the target school.")
        created_photo = None
        try:
            created_photo = self.create_photo(db, photo, "STEM_INSPECTION")
            record = STEMInspection(
                inspector_id=inspector.id, para_teacher_id=para_teacher_id,
                school_id=school_id, class_division_id=class_division_id,
                topic=topic.strip() if topic else None, photo_id=created_photo.id,
                inspected_at=datetime.now(timezone.utc), data_origin=data_origin,
            )
            db.add(record)
            db.flush()
            db.add(STEMInspectionReport(inspection_id=record.id, data_origin=data_origin))
            self.create_notification(
                db,
                recipient_id=inspector.id,
                inspection_id=record.id,
                message="Your STEM inspection report is pending.",
            )
            db.flush()
            return ObservationOperation(
                record=record,
                new_storage_keys=(created_photo.storage_key,),
            )
        except Exception:
            if created_photo:
                try:
                    self.photo_service.delete(created_photo.storage_key)
                except Exception:
                    # Preserve the original database or service exception.
                    pass
            raise

    @staticmethod
    def validate_link(url: str, confirmed: bool) -> str:
        if not confirmed:
            raise ValidationError("Sharing confirmation is required.")
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or len(url) > 2048:
            raise ValidationError("A valid absolute HTTPS URL without credentials is required.")
        return url.strip()

    @staticmethod
    def validate_document(
        filename: str | None,
        content_type: str | None,
        data: bytes,
    ) -> tuple[str, str]:
        suffix = Path(filename or "").suffix.lower()

        if suffix not in REPORT_EXTENSIONS:
            raise ValidationError("Only DOCX, PDF, and TXT reports are supported.")

        if not data or len(data) > MAX_REPORT_BYTES:
            raise ValidationError("Report must be non-empty and no larger than 5 MiB.")

        if suffix == ".pdf" and not data.startswith(b"%PDF-"):
            raise ValidationError("Invalid PDF content.")

        if suffix == ".docx":
            try:
                with ZipFile(BytesIO(data)) as archive:
                    names = set(archive.namelist())
                    if (
                        "[Content_Types].xml" not in names
                        or "word/document.xml" not in names
                    ):
                        raise ValidationError("Invalid DOCX content.")
            except (BadZipFile, OSError):
                raise ValidationError("Invalid DOCX content.") from None

        if suffix == ".txt":
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValidationError("TXT reports must contain valid UTF-8 text.") from None

        return suffix, REPORT_TYPES[suffix]


    def submit_report(
        self,
        db: Session,
        report,
        *,
        user_id: UUID,
        link: str | None = None,
        sharing_confirmed: bool = False,
        filename: str | None = None,
        content_type: str | None = None,
        data: bytes | None = None,
        area: str,
    ) -> tuple[object, str | None]:
        if report.status != "PENDING":
            raise AlreadySubmittedError("Report has already been submitted.")

        storage_key = None

        if link is not None:
            link = self.validate_link(link, sharing_confirmed)
            mode, media_type = "LINK", None
        else:
            suffix, media_type = self.validate_document(
                filename, content_type, data or b""
            )
            storage_key = self.documents.save(data or b"", suffix, area)
            mode = "UPLOAD"

        try:
            report.status = "COMPLETE"
            report.mode = mode
            report.external_url = link
            report.storage_key = storage_key
            report.original_filename = filename
            report.media_type = media_type
            report.file_size_bytes = len(data) if data is not None else None
            report.submitted_by_id = user_id
            report.submitted_at = datetime.now(timezone.utc)
            report.version = report.version + 1

            db.flush()
            return report, storage_key
        except Exception:
            if storage_key is not None:
                try:
                    self.documents.delete(storage_key)
                except Exception:
                    # Preserve the original database or flush exception.
                    pass
            raise


    def create_notification(self, db: Session, *, recipient_id: UUID, observation_id: UUID | None = None, inspection_id: UUID | None = None, message: str) -> PendingReportNotification:
        notification = db.query(PendingReportNotification).filter_by(
            recipient_id=recipient_id, observation_id=observation_id, inspection_id=inspection_id,
            notification_type="REPORT_PENDING",
        ).first()
        if notification:
            notification.is_read = False
            return notification
        notification = PendingReportNotification(
            recipient_id=recipient_id, observation_id=observation_id,
            inspection_id=inspection_id, notification_type="REPORT_PENDING", message=message,
        )
        db.add(notification)
        db.flush()
        return notification
