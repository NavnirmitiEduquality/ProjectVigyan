import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path

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
    DuplicateSessionEvidenceError,
    PhotoInput,
    SessionEvidenceNotFoundError,
    SessionEvidenceService,
    SessionNotEditableError,
    TeachingSessionNotFoundError,
)


@pytest.fixture
def photo_service(tmp_path: Path) -> PhotoService:
    storage = LocalPrivatePhotoStorage(
        tmp_path / "photos"
    )

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


def make_jpeg(
    *,
    width: int = 800,
    height: int = 600,
    quality: int = 85,
) -> bytes:
    image = Image.new(
        "RGB",
        (width, height),
        "white",
    )

    output = BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=quality,
    )

    return output.getvalue()


def create_photo_input() -> PhotoInput:
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


def create_test_data(db):
    school = School(
        school_code=f"TEST-{uuid.uuid4().hex[:8]}",
        school_name=f"Evidence Service School {uuid.uuid4().hex[:8]}",
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
        full_name="Test Para Teacher",
        email=(
            f"evidence-{uuid.uuid4().hex[:8]}"
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

    return school, class_division, user, session


def create_completed_session(db):
    _, _, _, session = create_test_data(db)

    session.status = "COMPLETED"
    db.flush()

    return session


def create_existing_photo(db, *, category="SESSION_EVIDENCE"):
    photo = Photo(
        photo_category=category,
        storage_key=f"test/{uuid.uuid4()}.jpg",
        original_filename="existing.jpg",
        content_type="image/jpeg",
        file_size_bytes=1000,
        width=100,
        height=100,
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
        data_origin="TEST",
    )

    db.add(photo)
    db.flush()

    return photo


def test_create_session_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        operation = service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        evidence = operation.session_evidence

        assert evidence.id is not None
        assert evidence.teaching_session_id == session.id
        assert evidence.photo_id is not None

        assert len(operation.new_storage_keys) == 1
        assert operation.obsolete_storage_keys == ()

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_create_requires_existing_session(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        with pytest.raises(
            TeachingSessionNotFoundError,
        ):
            service.create(
                db,
                teaching_session_id=uuid.uuid4(),
                photo=create_photo_input(),
                data_origin="TEST",
            )

    finally:
        db.rollback()
        db.close()


def test_completed_session_cannot_create_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        session = create_completed_session(db)

        with pytest.raises(
            SessionNotEditableError,
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                photo=create_photo_input(),
                data_origin="TEST",
            )

    finally:
        db.rollback()
        db.close()


def test_duplicate_evidence_is_rejected(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        first = service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.commit()

        with pytest.raises(
            DuplicateSessionEvidenceError,
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                photo=create_photo_input(),
                data_origin="TEST",
            )

        assert first.session_evidence.id is not None

    finally:
        db.rollback()
        db.close()


def test_service_does_not_commit(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.rollback()

        count = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == session.id
            )
            .count()
        )

        assert count == 0

    finally:
        db.close()


def test_get_existing_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.commit()

        result = service.get(
            db,
            teaching_session_id=session.id,
        )

        assert result.id == created.session_evidence.id

    finally:
        db.rollback()
        db.close()


def test_get_missing_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        with pytest.raises(
            SessionEvidenceNotFoundError,
        ):
            service.get(
                db,
                teaching_session_id=session.id,
            )

    finally:
        db.rollback()
        db.close()


def test_replace_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        first = service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.commit()

        old_photo_id = first.session_evidence.photo_id

        replacement = service.replace(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
        )

        assert (
            replacement.session_evidence.photo_id
            != old_photo_id
        )

        assert len(replacement.new_storage_keys) == 1
        assert len(replacement.obsolete_storage_keys) == 1

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_replace_missing_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        with pytest.raises(
            SessionEvidenceNotFoundError,
        ):
            service.replace(
                db,
                teaching_session_id=session.id,
                photo=create_photo_input(),
            )

    finally:
        db.rollback()
        db.close()


def test_replace_completed_session_is_rejected(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.commit()

        session.status = "COMPLETED"
        db.commit()

        with pytest.raises(
            SessionNotEditableError,
        ):
            service.replace(
                db,
                teaching_session_id=session.id,
                photo=create_photo_input(),
            )

    finally:
        db.rollback()
        db.close()


def test_delete_evidence(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.commit()

        operation = service.delete(
            db,
            teaching_session_id=session.id,
        )

        assert (
            operation.session_evidence.id
            == created.session_evidence.id
        )

        assert len(operation.obsolete_storage_keys) == 1

        db.commit()

        count = (
            db.query(SessionEvidence)
            .filter(
                SessionEvidence.teaching_session_id
                == session.id
            )
            .count()
        )

        assert count == 0

    finally:
        db.rollback()
        db.close()


def test_delete_completed_session_is_rejected(
    service: SessionEvidenceService,
):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        service.create(
            db,
            teaching_session_id=session.id,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        db.commit()

        session.status = "COMPLETED"
        db.commit()

        with pytest.raises(
            SessionNotEditableError,
        ):
            service.delete(
                db,
                teaching_session_id=session.id,
            )

    finally:
        db.rollback()
        db.close()