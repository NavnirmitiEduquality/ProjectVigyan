from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.photo import Photo
from app.services.photo.processing import (
    PhotoProcessingService,
    ProcessedPhoto,
)
from app.services.photo.storage import PhotoStorage


@dataclass(frozen=True)
class StoredPhoto:
    """Processed photo together with its private storage key."""

    storage_key: str
    processed_photo: ProcessedPhoto


class PhotoService:
    """Application-level coordinator for photo processing, storage and persistence."""

    def __init__(
        self,
        processing_service: PhotoProcessingService,
        storage: PhotoStorage,
    ) -> None:
        self.processing_service = processing_service
        self.storage = storage

    def process_and_store(
        self,
        image_bytes: bytes,
        *,
        captured_at: datetime,
        latitude: Decimal,
        longitude: Decimal,
    ) -> StoredPhoto:
        """Process a photo and store the resulting JPEG."""

        processed_photo = self.processing_service.process(
            image_bytes,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
        )

        storage_key = self.storage.save(
            processed_photo.image_bytes,
            extension=".jpg",
        )

        return StoredPhoto(
            storage_key=storage_key,
            processed_photo=processed_photo,
        )

    def create_photo(
        self,
        db: Session,
        image_bytes: bytes,
        *,
        photo_category: str,
        captured_at: datetime,
        latitude: Decimal,
        longitude: Decimal,
        original_filename: str | None = None,
        data_origin: str = "PRODUCTION",
    ) -> Photo:
        """
        Process, store and persist a Photo.

        If database persistence fails, the newly-created storage
        object is deleted to prevent an orphaned file.
        """

        stored_photo = self.process_and_store(
            image_bytes,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
        )

        processed = stored_photo.processed_photo

        photo = Photo(
            photo_category=photo_category,
            storage_key=stored_photo.storage_key,
            original_filename=original_filename,
            content_type=processed.content_type,
            file_size_bytes=processed.file_size_bytes,
            width=processed.width,
            height=processed.height,
            captured_at=processed.captured_at,
            latitude=processed.latitude,
            longitude=processed.longitude,
            data_origin=data_origin,
        )

        try:
            db.add(photo)
            db.flush()
        except Exception:
            self.storage.delete(stored_photo.storage_key)
            raise

        return photo

    def delete(
        self,
        storage_key: str,
    ) -> None:
        """Delete a stored photo by its private storage key."""

        self.storage.delete(storage_key)
