from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.photo import Photo
from app.models.session_tlm import SessionTLM
from app.models.teaching_session import TeachingSession
from app.models.tlm import TLM
from app.services.photo.service import PhotoService


NA_TLM_NAME = "NA - No TLM Used"
EDITABLE_SESSION_STATUS = "IN_PROGRESS"
TLM_ACTIVITY_PHOTO_CATEGORY = "TLM_ACTIVITY"


class SessionTLMError(Exception):
    """Base exception for SessionTLM business errors."""


class SessionTLMNotFoundError(SessionTLMError):
    """Raised when a SessionTLM does not exist."""


class TeachingSessionNotFoundError(SessionTLMError):
    """Raised when the teaching session does not exist."""


class SessionNotEditableError(SessionTLMError):
    """Raised when the teaching session cannot be modified."""


class TLMNotFoundError(SessionTLMError):
    """Raised when the requested TLM does not exist."""


class InactiveTLMError(SessionTLMError):
    """Raised when an inactive TLM is selected."""


class InvalidQuantityError(SessionTLMError):
    """Raised when a TLM quantity is invalid."""


class DuplicateTLMError(SessionTLMError):
    """Raised when a TLM already exists in the session."""


class NAConflictError(SessionTLMError):
    """Raised when NA - No TLM Used conflicts with another TLM."""


class InvalidTLMPhotoError(SessionTLMError):
    """Raised when a TLM activity photo is invalid."""


class SessionTLMIntegrityError(SessionTLMError):
    """Raised when a database integrity constraint is violated."""


@dataclass(frozen=True)
class PhotoInput:
    """Input required for a TLM activity photo."""

    image_bytes: bytes
    captured_at: datetime
    latitude: Decimal
    longitude: Decimal
    original_filename: str | None = None
    data_origin: str = "PRODUCTION"


@dataclass(frozen=True)
class SessionTLMOperation:
    """
    Result of a SessionTLM mutation.

    The database transaction remains owned by the caller.

    `new_storage_keys` must only be retained if the caller commits.

    `obsolete_storage_keys` must only be physically deleted after
    the caller successfully commits.
    """

    session_tlm: SessionTLM
    new_storage_keys: tuple[str, ...] = ()
    obsolete_storage_keys: tuple[str, ...] = ()


class SessionTLMService:
    """
    Business service for SessionTLM operations.

    Transaction ownership remains with the caller. This service never
    commits or rolls back the caller's SQLAlchemy transaction.
    """

    def __init__(self, photo_service: PhotoService) -> None:
        self.photo_service = photo_service

    @staticmethod
    def _ensure_tlm_not_already_added(
        db: Session,
        *,
        teaching_session_id: UUID,
        tlm_id: UUID,
    ) -> None:
        existing = (
            db.query(SessionTLM)
            .filter(
                SessionTLM.teaching_session_id == teaching_session_id,
                SessionTLM.tlm_id == tlm_id,
            )
            .first()
        )

        if existing is not None:
            raise DuplicateTLMError(
                "This TLM has already been added to the teaching session."
            )
    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(
        self,
        db: Session,
        *,
        teaching_session_id: UUID,
        tlm_id: UUID,
        quantity: int,
        usage: str | None = None,
        photo: PhotoInput | None = None,
        data_origin: str = "PRODUCTION",
    ) -> SessionTLMOperation:
        """
        Create a SessionTLM.

        The caller must commit the transaction after successful return.

        If the caller rolls back, any newly-created physical photo must
        be removed using the returned `new_storage_keys`.
        """

        teaching_session = self._get_teaching_session(
            db,
            teaching_session_id,
        )
        self._ensure_session_editable(teaching_session)

        tlm = self._get_tlm(db, tlm_id)
        self._ensure_tlm_active(tlm)
        self._ensure_tlm_not_already_added(
            db,
            teaching_session_id=teaching_session_id,
            tlm_id=tlm_id,
        )

        self._validate_quantity(
            tlm=tlm,
            quantity=quantity,
        )

        self._validate_na_rules_for_create(
            db,
            teaching_session_id=teaching_session_id,
            tlm=tlm,
        )

        
        created_photo: Photo | None = None

        try:
            if photo is not None:
                created_photo = self._create_photo(
                    db,
                    photo,
                )

            session_tlm = SessionTLM(
                teaching_session_id=teaching_session_id,
                tlm_id=tlm_id,
                quantity=quantity,
                usage=usage,
                photo_id=(
                    created_photo.id
                    if created_photo is not None
                    else None
                ),
                data_origin=data_origin,
            )

            db.add(session_tlm)
            db.flush()

        except IntegrityError as exc:
            self._remove_failed_photo(
                db,
                created_photo,
            )

            raise SessionTLMIntegrityError(
                "Unable to create SessionTLM because a "
                "database integrity constraint was violated."
            ) from exc

        except Exception:
            self._remove_failed_photo(
                db,
                created_photo,
            )
            raise

        new_storage_keys = (
            (created_photo.storage_key,)
            if created_photo is not None
            else ()
        )

        return SessionTLMOperation(
            session_tlm=session_tlm,
            new_storage_keys=new_storage_keys,
        )

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(
        self,
        db: Session,
        *,
        session_tlm_id: UUID,
        tlm_id: UUID | None = None,
        quantity: int | None = None,
        usage: str | None = None,
        photo: PhotoInput | None = None,
        remove_photo: bool = False,
    ) -> SessionTLMOperation:
        """
        Update a SessionTLM.

        Existing physical storage is never deleted before the caller's
        transaction commits successfully.
        """

        session_tlm = self._get_session_tlm(
            db,
            session_tlm_id,
        )

        teaching_session = session_tlm.teaching_session
        self._ensure_session_editable(teaching_session)

        current_tlm = session_tlm.tlm
        target_tlm = current_tlm

        if tlm_id is not None and tlm_id != current_tlm.id:
            target_tlm = self._get_tlm(
                db,
                tlm_id,
            )
            self._ensure_tlm_active(target_tlm)

        target_quantity = (
            quantity
            if quantity is not None
            else session_tlm.quantity
        )

        self._validate_quantity(
            tlm=target_tlm,
            quantity=target_quantity,
        )

        self._validate_na_rules_for_update(
            db,
            session_tlm=session_tlm,
            target_tlm=target_tlm,
        )

        if photo is not None and remove_photo:
            raise InvalidTLMPhotoError(
                "A replacement photo and photo removal "
                "cannot be requested together."
            )

        old_photo = session_tlm.photo
        old_storage_key = (
            old_photo.storage_key
            if old_photo is not None
            else None
        )

        if old_photo is not None:
            self._validate_existing_photo(old_photo)

        new_photo = None

        try:
            if photo is not None:
                new_photo = self._create_photo(db, photo)

                # Replace the relationship explicitly.
                session_tlm.photo = new_photo

            elif remove_photo:
                # Remove the relationship explicitly.
                session_tlm.photo = None

            session_tlm.tlm_id = target_tlm.id
            session_tlm.quantity = target_quantity
            session_tlm.usage = usage

            if old_photo is not None and (
                photo is not None or remove_photo
            ):
                db.delete(old_photo)

            db.flush()

        except IntegrityError as exc:
            self._remove_failed_photo(
                db,
                new_photo,
            )

            raise SessionTLMIntegrityError(
                "Unable to update SessionTLM because a "
                "database integrity constraint was violated."
            ) from exc

        except Exception:
            self._remove_failed_photo(
                db,
                new_photo,
            )
            raise

        obsolete_storage_keys: tuple[str, ...] = ()

        if old_photo is not None and (
            photo is not None or remove_photo
        ):
            obsolete_storage_keys = (
                (old_storage_key,)
                if old_storage_key is not None
                and (photo is not None or remove_photo)
                else ()
            )

        new_storage_keys = (
            (new_photo.storage_key,)
            if new_photo is not None
            else ()
        )

        return SessionTLMOperation(
            session_tlm=session_tlm,
            new_storage_keys=new_storage_keys,
            obsolete_storage_keys=obsolete_storage_keys,
        )

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(
        self,
        db: Session,
        *,
        session_tlm_id: UUID,
    ) -> SessionTLMOperation:
        """
        Delete a SessionTLM.

        Physical photo storage is not deleted until the caller has
        successfully committed the database transaction.
        """

        session_tlm = self._get_session_tlm(
            db,
            session_tlm_id,
        )

        self._ensure_session_editable(
            session_tlm.teaching_session,
        )

        photo = session_tlm.photo

        if photo is not None:
            self._validate_existing_photo(photo)

        try:
            db.delete(session_tlm)
            db.flush()

            if photo is not None:
                db.delete(photo)
                db.flush()

        except IntegrityError as exc:
            raise SessionTLMIntegrityError(
                "Unable to delete SessionTLM because a "
                "database integrity constraint was violated."
            ) from exc

        obsolete_storage_keys = (
            (photo.storage_key,)
            if photo is not None
            else ()
        )

        return SessionTLMOperation(
            session_tlm=session_tlm,
            obsolete_storage_keys=obsolete_storage_keys,
        )

    # ------------------------------------------------------------------
    # PHOTO STORAGE CLEANUP
    # ------------------------------------------------------------------

    def cleanup_storage(
        self,
        storage_keys: tuple[str, ...],
    ) -> None:
        """
        Delete physical photo objects.

        This should only be called after the owning database transaction
        has successfully committed.
        """

        for storage_key in storage_keys:
            try:
                self.photo_service.delete(storage_key)
            except Exception:
                # Physical cleanup must not turn a successful database
                # transaction into a failed API response.
                #
                # A future durable cleanup/retry mechanism can process
                # failed storage deletions.
                continue

    def compensate_new_storage(
        self,
        storage_keys: tuple[str, ...],
    ) -> None:
        """
        Remove newly-created physical objects after transaction failure.

        This should be called after the caller rolls back the database
        transaction.
        """

        self.cleanup_storage(storage_keys)

    # ------------------------------------------------------------------
    # RETRIEVAL
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
                "Teaching session not found."
            )

        return teaching_session

    @staticmethod
    def _get_session_tlm(
        db: Session,
        session_tlm_id: UUID,
    ) -> SessionTLM:
        session_tlm = (
            db.query(SessionTLM)
            .filter(
                SessionTLM.id == session_tlm_id,
            )
            .first()
        )

        if session_tlm is None:
            raise SessionTLMNotFoundError(
                "SessionTLM not found."
            )

        return session_tlm

    @staticmethod
    def _get_tlm(
        db: Session,
        tlm_id: UUID,
    ) -> TLM:
        tlm = (
            db.query(TLM)
            .filter(
                TLM.id == tlm_id,
            )
            .first()
        )

        if tlm is None:
            raise TLMNotFoundError(
                "TLM not found."
            )

        return tlm

    # ------------------------------------------------------------------
    # BUSINESS VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_session_editable(
        teaching_session: TeachingSession,
    ) -> None:
        if teaching_session.status != EDITABLE_SESSION_STATUS:
            raise SessionNotEditableError(
                "SessionTLM records can only be modified while "
                "the teaching session is IN_PROGRESS."
            )

    @staticmethod
    def _ensure_tlm_active(
        tlm: TLM,
    ) -> None:
        if not tlm.is_active:
            raise InactiveTLMError(
                "Inactive TLMs cannot be selected for new or "
                "changed SessionTLM records."
            )

    @staticmethod
    def _validate_quantity(
        *,
        tlm: TLM,
        quantity: int,
    ) -> None:
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise InvalidQuantityError(
                "Quantity must be an integer."
            )

        if tlm.name == NA_TLM_NAME:
            if quantity != 0:
                raise InvalidQuantityError(
                    'Quantity for "NA - No TLM Used" must be 0.'
                )
            return

        if quantity < 1:
            raise InvalidQuantityError(
                "Quantity for a normal TLM must be at least 1."
            )

    @staticmethod
    def _validate_photo(
        photo: PhotoInput | None,
    ) -> None:
        if photo is None:
            return

        if not photo.image_bytes:
            raise InvalidTLMPhotoError(
                "TLM activity photo cannot be empty."
            )

    @staticmethod
    def _validate_existing_photo(
        photo: Photo,
    ) -> None:
        if photo.photo_category != TLM_ACTIVITY_PHOTO_CATEGORY:
            raise InvalidTLMPhotoError(
                "SessionTLM photos must use the TLM_ACTIVITY category."
            )

    # ------------------------------------------------------------------
    # NA RULES
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_na_rules_for_create(
        db: Session,
        *,
        teaching_session_id: UUID,
        tlm: TLM,
    ) -> None:
        existing = (
            db.query(SessionTLM)
            .filter(
                SessionTLM.teaching_session_id
                == teaching_session_id,
            )
            .all()
        )

        if tlm.name == NA_TLM_NAME:
            if existing:
                raise NAConflictError(
                    '"NA - No TLM Used" must be the only '
                    "TLM record in a session."
                )
            return

        if any(
            item.tlm.name == NA_TLM_NAME
            for item in existing
        ):
            raise NAConflictError(
                '"NA - No TLM Used" cannot be combined '
                "with another TLM."
            )

    @staticmethod
    def _validate_na_rules_for_update(
        db: Session,
        *,
        session_tlm: SessionTLM,
        target_tlm: TLM,
    ) -> None:
        existing = (
            db.query(SessionTLM)
            .filter(
                SessionTLM.teaching_session_id
                == session_tlm.teaching_session_id,
                SessionTLM.id != session_tlm.id,
            )
            .all()
        )

        if target_tlm.name == NA_TLM_NAME:
            if existing:
                raise NAConflictError(
                    '"NA - No TLM Used" must be the only '
                    "TLM record in a session."
                )
            return

        if any(
            item.tlm.name == NA_TLM_NAME
            for item in existing
        ):
            raise NAConflictError(
                '"NA - No TLM Used" cannot be combined '
                "with another TLM."
            )

    # ------------------------------------------------------------------
    # PHOTO CREATION / FAILURE COMPENSATION
    # ------------------------------------------------------------------

    def _create_photo(
        self,
        db: Session,
        photo: PhotoInput,
    ) -> Photo:
        self._validate_photo(photo)

        created_photo = self.photo_service.create_photo(
            db,
            photo.image_bytes,
            photo_category=TLM_ACTIVITY_PHOTO_CATEGORY,
            captured_at=photo.captured_at,
            latitude=photo.latitude,
            longitude=photo.longitude,
            original_filename=photo.original_filename,
            data_origin=photo.data_origin,
        )

        return created_photo

    def _remove_failed_photo(
        self,
        db: Session,
        photo: Photo | None,
    ) -> None:
        """
        Compensate for a newly-created photo when the SessionTLM
        operation fails before the transaction can be committed.

        This does not rollback the caller's transaction.
        """

        if photo is None:
            return

        storage_key = photo.storage_key

        try:
            db.expunge(photo)
        except Exception:
            pass

        try:
            self.photo_service.delete(storage_key)
        except Exception:
            # Cleanup failure must remain observable to a future
            # durable cleanup mechanism rather than causing an
            # additional database rollback.
            pass
