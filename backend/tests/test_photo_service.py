from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from io import BytesIO

import pytest
from PIL import Image

from app.services.photo import (
    LocalPrivatePhotoStorage,
    PhotoProcessingService,
    PhotoService,
)
from app.database import SessionLocal


@pytest.fixture
def photo_service(tmp_path: Path) -> PhotoService:
    storage = LocalPrivatePhotoStorage(tmp_path / "photos")

    return PhotoService(
        processing_service=PhotoProcessingService(),
        storage=storage,
    )


def make_jpeg(
    *,
    width: int = 800,
    height: int = 600,
    quality: int = 85,
) -> bytes:
    image = Image.new("RGB", (width, height), "white")

    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
    )

    return output.getvalue()


def capture_time() -> datetime:
    return datetime(
        2026,
        9,
        24,
        10,
        0,
        tzinfo=timezone.utc,
    )


def valid_gps() -> tuple[Decimal, Decimal]:
    return Decimal("19.076000"), Decimal("72.877700")


def test_process_and_store_processes_and_stores_photo(
    photo_service: PhotoService,
):
    image_bytes = make_jpeg()
    latitude, longitude = valid_gps()

    result = photo_service.process_and_store(
        image_bytes,
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    assert result.storage_key
    assert result.storage_key.endswith(".jpg")

    processed = result.processed_photo

    assert processed.content_type == "image/jpeg"
    assert processed.file_size_bytes <= 1_048_576
    assert processed.width == 800
    assert processed.height == 600
    assert processed.latitude == latitude
    assert processed.longitude == longitude

    assert photo_service.storage.exists(result.storage_key)


def test_stored_file_contains_processed_jpeg(
    photo_service: PhotoService,
):
    image_bytes = make_jpeg()
    latitude, longitude = valid_gps()

    result = photo_service.process_and_store(
        image_bytes,
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    stored_path = (
        photo_service.storage.root_directory
        / result.storage_key
    )

    with Image.open(stored_path) as image:
        assert image.format == "JPEG"
        assert image.size == (800, 600)


def test_invalid_photo_is_not_stored(
    photo_service: PhotoService,
):
    latitude, longitude = valid_gps()

    with pytest.raises(ValueError):
        photo_service.process_and_store(
            b"not-an-image",
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )

    files = list(
        photo_service.storage.root_directory.iterdir()
    )

    assert files == []


def test_invalid_gps_is_not_stored(
    photo_service: PhotoService,
):
    with pytest.raises(ValueError, match="Latitude"):
        photo_service.process_and_store(
            make_jpeg(),
            captured_at=capture_time(),
            latitude=Decimal("91"),
            longitude=Decimal("72.877700"),
        )

    files = list(
        photo_service.storage.root_directory.iterdir()
    )

    assert files == []


def test_delete_removes_stored_photo(
    photo_service: PhotoService,
):
    latitude, longitude = valid_gps()

    result = photo_service.process_and_store(
        make_jpeg(),
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    assert photo_service.storage.exists(result.storage_key)

    photo_service.delete(result.storage_key)

    assert not photo_service.storage.exists(result.storage_key)


def test_processing_metadata_is_preserved(
    photo_service: PhotoService,
):
    latitude, longitude = valid_gps()
    captured_at = capture_time()

    result = photo_service.process_and_store(
        make_jpeg(),
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
    )

    assert result.processed_photo.captured_at == captured_at
    assert result.processed_photo.latitude == latitude
    assert result.processed_photo.longitude == longitude


def test_create_photo_persists_metadata(
    photo_service: PhotoService,
):
    db = SessionLocal()

    try:
        latitude, longitude = valid_gps()

        photo = photo_service.create_photo(
            db,
            make_jpeg(),
            photo_category="SESSION_EVIDENCE",
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
            original_filename="IMG_20260924_103522.jpg",
        )

        db.commit()

        assert photo.id is not None
        assert photo.photo_category == "SESSION_EVIDENCE"
        assert photo.content_type == "image/jpeg"
        assert photo.file_size_bytes <= 1_048_576
        assert photo.width == 800
        assert photo.height == 600
        assert photo.latitude == latitude
        assert photo.longitude == longitude
        assert photo.original_filename == "IMG_20260924_103522.jpg"

        assert photo_service.storage.exists(
            photo.storage_key
        )

    finally:
        db.close()


def test_create_photo_does_not_commit_transaction(
    photo_service: PhotoService,
):
    db = SessionLocal()

    try:
        latitude, longitude = valid_gps()

        photo_service.create_photo(
            db,
            make_jpeg(),
            photo_category="SESSION_EVIDENCE",
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )

        # The PhotoService only flushes.
        # The caller owns the transaction.
        db.rollback()

    finally:
        db.close()


def test_create_photo_deletes_storage_when_db_flush_fails(
    photo_service: PhotoService,
    monkeypatch,
):
    db = SessionLocal()

    try:
        latitude, longitude = valid_gps()

        def failing_flush(*args, **kwargs):
            raise RuntimeError(
                "simulated database failure"
            )

        monkeypatch.setattr(
            db,
            "flush",
            failing_flush,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated database failure",
        ):
            photo_service.create_photo(
                db,
                make_jpeg(),
                photo_category="SESSION_EVIDENCE",
                captured_at=capture_time(),
                latitude=latitude,
                longitude=longitude,
            )

        files = list(
            photo_service.storage.root_directory.iterdir()
        )

        assert files == []

        db.rollback()

    finally:
        db.close()


def test_invalid_photo_never_reaches_storage(
    photo_service: PhotoService,
):
    db = SessionLocal()

    try:
        latitude, longitude = valid_gps()

        with pytest.raises(ValueError):
            photo_service.create_photo(
                db,
                b"not-a-jpeg",
                photo_category="SESSION_EVIDENCE",
                captured_at=capture_time(),
                latitude=latitude,
                longitude=longitude,
            )

        files = list(
            photo_service.storage.root_directory.iterdir()
        )

        assert files == []

    finally:
        db.close()