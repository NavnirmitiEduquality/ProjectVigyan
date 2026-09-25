from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.photo import Photo
from app.models.session_evidence import SessionEvidence
from app.models.teaching_session import TeachingSession
from app.services.photo.service import PhotoService


EDITABLE_SESSION_STATUS = "IN_PROGRESS"
SESSION_EVIDENCE_PHOTO_CATEGORY = "SESSION_EVIDENCE"


class SessionEvidenceError(Exception):
    """Base exception for SessionEvidence business errors."""


class TeachingSessionNotFoundError(SessionEvidenceError):
    """Raised when the teaching session does not exist."""


class SessionEvidenceNotFoundError(SessionEvidenceError):
    """Raised when the session evidence does not exist."""


class SessionNotEditableError(SessionEvidenceError):
    """Raised when the teaching session cannot be modified."""


class PhotoNotFoundError(SessionEvidenceError):
    """Raised when the requested photo does not exist."""


class InvalidEvidencePhotoError(SessionEvidenceError):
    """Raised when the photo is not a session evidence photo."""


class DuplicateSessionEvidenceError(SessionEvidenceError):
    """Raised when evidence already exists for a session."""


@dataclass(frozen=True)
class PhotoInput:
    """Input required for a session evidence photo."""

    image_bytes: bytes
    captured_at: datetime
    latitude: Decimal
    longitude: Decimal
    original_filename: str | None = None
    data_origin: str = "PRODUCTION"


@dataclass(frozen=True)
class SessionEvidenceOperation:
    """
    Result of a SessionEvidence mutation.

    The database transaction remains owned by the caller.

    new_storage_keys:
        Physical photo objects created during this operation.
        They must be deleted if the caller rolls back.

    obsolete_storage_keys:
        Physical photo objects replaced by this operation.
        They must only be deleted after the caller successfully commits.
    """

    session_evidence: SessionEvidence
    new_storage_keys: tuple[str, ...] = ()
    obsolete_storage_keys: tuple[str, ...] = ()


class SessionEvidenceService:
    """
    Business service for SessionEvidence operations.

    This service never commits or rolls back the caller's transaction.
    """

    def __init__(self, photo_service: PhotoService) -> None:
        self.photo_service = photo_service

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(
        self,
        db: Session,
        *,
        teaching_session_id: UUID,
        photo: PhotoInput,
        data_origin: str = "PRODUCTION",
    ) -> SessionEvidenceOperation:
        """
        Create session evidence for an in-progress teaching session.

        The caller owns the database transaction.

        If the transaction is rolled back, the returned new_storage_keys
        must be physically deleted.
        """

        teaching_session = self._get_teaching_session(
            db,
            teaching_session_id,
        )

        self._ensure_session_editable(teaching_session)

        existing = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == teaching_session_id
            )
            .first()
        )

        if existing is not None:
            raise DuplicateSessionEvidenceError(
                "Session evidence already exists for this teaching session."
            )

        created_photo: Photo | None = None

        try:
            created_photo = self._create_photo(
                db,
                photo,
            )

            evidence = SessionEvidence(
                teaching_session_id=teaching_session_id,
                photo_id=created_photo.id,
                data_origin=data_origin,
            )

            db.add(evidence)
            db.flush()

            return SessionEvidenceOperation(
                session_evidence=evidence,
                new_storage_keys=(created_photo.storage_key,),
            )

        except Exception:
            if created_photo is not None:
                self._delete_storage_safely(
                    created_photo.storage_key,
                )
            raise

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(
        self,
        db: Session,
        *,
        teaching_session_id: UUID,
    ) -> SessionEvidence:
        """Get the evidence belonging to a teaching session."""

        self._get_teaching_session(
            db,
            teaching_session_id,
        )

        evidence = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == teaching_session_id
            )
            .first()
        )

        if evidence is None:
            raise SessionEvidenceNotFoundError(
                "Session evidence does not exist."
            )

        return evidence

    # ------------------------------------------------------------------
    # REPLACE / RETAKE
    # ------------------------------------------------------------------

    def replace(
        self,
        db: Session,
        *,
        teaching_session_id: UUID,
        photo: PhotoInput,
    ) -> SessionEvidenceOperation:
        """
        Replace existing session evidence while the session is IN_PROGRESS.

        The old physical photo is NOT deleted here.

        Its storage key is returned in obsolete_storage_keys and must only
        be deleted after the caller successfully commits.
        """

        teaching_session = self._get_teaching_session(
            db,
            teaching_session_id,
        )

        self._ensure_session_editable(teaching_session)

        evidence = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == teaching_session_id
            )
            .first()
        )

        if evidence is None:
            raise SessionEvidenceNotFoundError(
                "Session evidence does not exist."
            )

        old_photo = (
            db.query(Photo)
            .filter(Photo.id == evidence.photo_id)
            .first()
        )

        if old_photo is None:
            raise PhotoNotFoundError(
                "The existing evidence photo does not exist."
            )

        new_photo: Photo | None = None

        try:
            new_photo = self._create_photo(
                db,
                photo,
            )

            evidence.photo_id = new_photo.id
            db.flush()

            return SessionEvidenceOperation(
                session_evidence=evidence,
                new_storage_keys=(new_photo.storage_key,),
                obsolete_storage_keys=(old_photo.storage_key,),
            )

        except Exception:
            if new_photo is not None:
                self._delete_storage_safely(
                    new_photo.storage_key,
                )
            raise

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(
        self,
        db: Session,
        *,
        teaching_session_id: UUID,
    ) -> SessionEvidenceOperation:
        """
        Delete session evidence while the session is IN_PROGRESS.

        The physical photo is returned as obsolete_storage_keys and must
        only be deleted after successful transaction commit.
        """

        teaching_session = self._get_teaching_session(
            db,
            teaching_session_id,
        )

        self._ensure_session_editable(teaching_session)

        evidence = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == teaching_session_id
            )
            .first()
        )

        if evidence is None:
            raise SessionEvidenceNotFoundError(
                "Session evidence does not exist."
            )

        photo = (
            db.query(Photo)
            .filter(Photo.id == evidence.photo_id)
            .first()
        )

        obsolete_storage_keys: tuple[str, ...] = ()

        if photo is not None:
            obsolete_storage_keys = (
                photo.storage_key,
            )

        db.delete(evidence)
        db.flush()

        if photo is not None:
            db.delete(photo)
            db.flush()

        return SessionEvidenceOperation(
            session_evidence=evidence,
            obsolete_storage_keys=obsolete_storage_keys,
        )

    # ------------------------------------------------------------------
    # STORAGE COMPENSATION
    # ------------------------------------------------------------------

    def compensate_new_storage(
        self,
        storage_keys: tuple[str, ...],
    ) -> None:
        """
        Delete physical objects created by a failed transaction.
        """

        for storage_key in storage_keys:
            self._delete_storage_safely(storage_key)

    def delete_obsolete_storage(
        self,
        storage_keys: tuple[str, ...],
    ) -> None:
        """
        Delete physical objects that became obsolete after commit.
        """

        for storage_key in storage_keys:
            self._delete_storage_safely(storage_key)

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_teaching_session(
        db: Session,
        teaching_session_id: UUID,
    ) -> TeachingSession:
        teaching_session = (
            db.query(TeachingSession)
            .filter(
                TeachingSession.id == teaching_session_id,
            )
            .first()
        )

        if teaching_session is None:
            raise TeachingSessionNotFoundError(
                "Teaching session does not exist."
            )

        return teaching_session

    @staticmethod
    def _ensure_session_editable(
        teaching_session: TeachingSession,
    ) -> None:
        if teaching_session.status != EDITABLE_SESSION_STATUS:
            raise SessionNotEditableError(
                "Teaching session can only be modified while IN_PROGRESS."
            )

    def _create_photo(
        self,
        db: Session,
        photo_input: PhotoInput,
    ) -> Photo:
        return self.photo_service.create_photo(
            db,
            photo_input.image_bytes,
            photo_category=SESSION_EVIDENCE_PHOTO_CATEGORY,
            captured_at=photo_input.captured_at,
            latitude=photo_input.latitude,
            longitude=photo_input.longitude,
            original_filename=photo_input.original_filename,
            data_origin=photo_input.data_origin,
        )

    def _delete_storage_safely(
        self,
        storage_key: str,
    ) -> None:
        try:
            self.photo_service.storage.delete(storage_key)
        except Exception:
            # Storage cleanup must not hide the original business/
            # transaction exception.
            pass