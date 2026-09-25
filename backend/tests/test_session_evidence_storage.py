from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import uuid

import pytest
from PIL import Image

from app.database import SessionLocal
from app.models import (
    ClassDivision,
    Photo,
    School,
    SessionEvidence,
    TeachingSession,
    User,
)
from app.services.photo import (
    LocalPrivatePhotoStorage,
    PhotoProcessingService,
    PhotoService,
)
from app.services.session_evidence.service import (
    PhotoInput,
    SessionEvidenceService,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def photo_service(tmp_path: Path) -> PhotoService:
    storage = LocalPrivatePhotoStorage(tmp_path / "photos")

    return PhotoService(
        processing_service=PhotoProcessingService(),
        storage=storage,
    )


@pytest.fixture
def service(
    photo_service: PhotoService,
) -> SessionEvidenceService:
    return SessionEvidenceService(
        photo_service=photo_service,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def make_jpeg() -> bytes:
    image = Image.new(
        "RGB",
        (800, 600),
        "white",
    )

    output = BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=85,
    )

    return output.getvalue()


def photo_input() -> PhotoInput:
    return PhotoInput(
        image_bytes=make_jpeg(),
        captured_at=datetime(
            2026,
            9,
            24,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        latitude=Decimal("19.076000"),
        longitude=Decimal("72.877700"),
        original_filename="evidence.jpg",
        data_origin="TEST",
    )


def create_test_session(db):
    school = School(
        school_code=f"STORAGE-{uuid.uuid4().hex[:8]}",
        school_name=(
            f"Storage Test School "
            f"{uuid.uuid4().hex[:8]}"
        ),
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(school)
    db.flush()

    class_division = ClassDivision(
        school_id=school.id,
        class_level=5,
        division="A",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(class_division)
    db.flush()

    user = User(
        user_code=f"PT-{uuid.uuid4().hex[:8]}",
        full_name="Storage Test Teacher",
        email=(
            f"storage-{uuid.uuid4().hex[:8]}"
            "@example.com"
        ),
        password_hash="test-password-hash",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(user)
    db.flush()

    session = TeachingSession(
        class_division_id=class_division.id,
        para_teacher_id=user.id,
        session_date=date(2026, 9, 24),
        status="IN_PROGRESS",
        data_origin="TEST",
    )
    db.add(session)
    db.flush()

    return session


# ------------------------------------------------------------------
# CREATE
# ------------------------------------------------------------------


def test_successful_create_leaves_physical_photo(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        session = create_test_session(db)

        operation = service.create(
            db,
            teaching_session_id=session.id,
            photo=photo_input(),
            data_origin="TEST",
        )

        storage_key = operation.new_storage_keys[0]

        assert service.photo_service.storage.exists(
            storage_key
        )

        db.commit()

        assert service.photo_service.storage.exists(
            storage_key
        )

    finally:
        db.rollback()
        db.close()


def test_failed_create_cleans_new_physical_photo(
    service: SessionEvidenceService,
    monkeypatch,
):
    db = SessionLocal()

    try:
        session = create_test_session(db)

        original_flush = db.flush
        flush_count = 0

        def failing_flush(*args, **kwargs):
            nonlocal flush_count
            flush_count += 1

            # PhotoService.create_photo calls flush first.
            # SessionEvidenceService.create then flushes
            # the SessionEvidence row.
            if flush_count == 2:
                raise RuntimeError(
                    "simulated evidence database failure"
                )

            return original_flush(*args, **kwargs)

        monkeypatch.setattr(
            db,
            "flush",
            failing_flush,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated evidence database failure",
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                photo=photo_input(),
                data_origin="TEST",
            )

        files = list(
            service.photo_service.storage.root_directory.iterdir()
        )

        assert files == []

        db.rollback()

    finally:
        db.close()


# ------------------------------------------------------------------
# REPLACE
# ------------------------------------------------------------------


def test_successful_replace_deletes_old_photo_after_commit(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        session = create_test_session(db)

        first = service.create(
            db,
            teaching_session_id=session.id,
            photo=photo_input(),
            data_origin="TEST",
        )

        db.commit()

        old_storage_key = (
            first.session_evidence
            and db.query(Photo)
            .filter(
                Photo.id
                == first.session_evidence.photo_id
            )
            .one()
            .storage_key
        )

        assert service.photo_service.storage.exists(
            old_storage_key
        )

        replacement = service.replace(
            db,
            teaching_session_id=session.id,
            photo=photo_input(),
        )

        new_storage_key = replacement.new_storage_keys[0]

        assert replacement.obsolete_storage_keys == (
            old_storage_key,
        )

        assert service.photo_service.storage.exists(
            new_storage_key
        )

        # Before commit, old physical storage must still exist.
        assert service.photo_service.storage.exists(
            old_storage_key
        )

        db.commit()

        service.delete_obsolete_storage(
            replacement.obsolete_storage_keys
        )

        assert not service.photo_service.storage.exists(
            old_storage_key
        )

        assert service.photo_service.storage.exists(
            new_storage_key
        )

    finally:
        db.rollback()
        db.close()


def test_failed_replace_preserves_old_photo_and_cleans_new_photo(
    service: SessionEvidenceService,
    monkeypatch,
):
    db = SessionLocal()

    try:
        session = create_test_session(db)

        first = service.create(
            db,
            teaching_session_id=session.id,
            photo=photo_input(),
            data_origin="TEST",
        )

        db.commit()

        old_storage_key = (
            db.query(Photo)
            .filter(
                Photo.id
                == first.session_evidence.photo_id
            )
            .one()
            .storage_key
        )

        assert service.photo_service.storage.exists(
            old_storage_key
        )

        original_flush = db.flush
        flush_count = 0

        def failing_flush(*args, **kwargs):
            nonlocal flush_count
            flush_count += 1

            # The replacement photo is created and flushed
            # first. The next flush is the SessionEvidence
            # update and is deliberately failed.
            if flush_count == 2:
                raise RuntimeError(
                    "simulated replacement database failure"
                )

            return original_flush(*args, **kwargs)

        monkeypatch.setattr(
            db,
            "flush",
            failing_flush,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated replacement database failure",
        ):
            service.replace(
                db,
                teaching_session_id=session.id,
                photo=photo_input(),
            )

        files = list(
            service.photo_service.storage.root_directory.iterdir()
        )

        assert len(files) == 1

        assert service.photo_service.storage.exists(
            old_storage_key
        )

        db.rollback()

        # The database still points at the original photo.
        evidence = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == session.id
            )
            .one()
        )

        assert evidence.photo_id == (
            first.session_evidence.photo_id
        )

    finally:
        db.close()


# ------------------------------------------------------------------
# DELETE
# ------------------------------------------------------------------


def test_successful_delete_removes_physical_photo_after_commit(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        session = create_test_session(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            photo=photo_input(),
            data_origin="TEST",
        )

        db.commit()

        photo = (
            db.query(Photo)
            .filter(
                Photo.id
                == created.session_evidence.photo_id
            )
            .one()
        )

        storage_key = photo.storage_key

        assert service.photo_service.storage.exists(
            storage_key
        )

        operation = service.delete(
            db,
            teaching_session_id=session.id,
        )

        assert operation.obsolete_storage_keys == (
            storage_key,
        )

        # Physical storage is still present before commit.
        assert service.photo_service.storage.exists(
            storage_key
        )

        db.commit()

        service.delete_obsolete_storage(
            operation.obsolete_storage_keys
        )

        assert not service.photo_service.storage.exists(
            storage_key
        )

    finally:
        db.rollback()
        db.close()


def test_failed_delete_preserves_physical_photo(
    service: SessionEvidenceService,
    monkeypatch,
):
    db = SessionLocal()

    try:
        session = create_test_session(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            photo=photo_input(),
            data_origin="TEST",
        )

        db.commit()

        photo = (
            db.query(Photo)
            .filter(
                Photo.id
                == created.session_evidence.photo_id
            )
            .one()
        )

        storage_key = photo.storage_key

        assert service.photo_service.storage.exists(
            storage_key
        )

        original_commit = db.commit

        def failing_commit():
            raise RuntimeError(
                "simulated transaction commit failure"
            )

        monkeypatch.setattr(
            db,
            "commit",
            failing_commit,
        )

        operation = service.delete(
            db,
            teaching_session_id=session.id,
        )

        assert operation.obsolete_storage_keys == (
            storage_key,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated transaction commit failure",
        ):
            db.commit()

        db.rollback()

        # Because commit failed, obsolete physical storage
        # must NOT be deleted.
        assert service.photo_service.storage.exists(
            storage_key
        )

        # The database record must still exist after rollback.
        evidence = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == session.id
            )
            .one()
        )

        assert evidence.photo_id == photo.id

        monkeypatch.setattr(
            db,
            "commit",
            original_commit,
        )

    finally:
        db.rollback()
        db.close()
