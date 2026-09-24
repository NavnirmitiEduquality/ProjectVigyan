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
    SessionTLM,
    TeachingSession,
    TLM,
    User,
)
from app.services.photo import (
    LocalPrivatePhotoStorage,
    PhotoProcessingService,
    PhotoService,
)
from app.services.session_tlm.service import (
    DuplicateTLMError,
    InactiveTLMError,
    InvalidQuantityError,
    InvalidTLMPhotoError,
    NAConflictError,
    PhotoInput,
    SessionNotEditableError,
    SessionTLMService,
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
def service(photo_service: PhotoService) -> SessionTLMService:
    return SessionTLMService(
        photo_service=photo_service
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

def get_na_tlm(db):
    return (
        db.query(TLM)
        .filter(
            TLM.name == "NA - No TLM Used",
        )
        .one()
    )

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
    return (
        Decimal("19.076000"),
        Decimal("72.877700"),
    )


def create_test_data(db):
    school = School(
        school_code=f"TEST-{uuid.uuid4().hex[:8]}",
        school_name=f"Test School {uuid.uuid4()}",
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
            f"test-{uuid.uuid4().hex[:8]}"
            "@example.com"
        ),
        password_hash="test-password-hash",
        status="ACTIVE",
        data_origin="TEST",
    )
    db.add(user)
    db.flush()

    tlm = TLM(
        name=f"Test TLM {uuid.uuid4()}",
        description="Test teaching-learning material",
        is_active=True,
        data_origin="TEST",
    )
    db.add(tlm)
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

    return (
        school,
        class_division,
        user,
        tlm,
        session,
    )


def create_photo_input() -> PhotoInput:
    latitude, longitude = valid_gps()

    return PhotoInput(
        image_bytes=make_jpeg(),
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
        original_filename="tlm_activity.jpg",
        data_origin="TEST",
    )


def test_create_session_tlm(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        result = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=2,
            usage="Students used the model during the activity.",
            data_origin="TEST",
        )

        assert result.session_tlm.id is not None
        assert (
            result.session_tlm.teaching_session_id
            == session.id
        )
        assert result.session_tlm.tlm_id == tlm.id
        assert result.session_tlm.quantity == 2
        assert (
            result.session_tlm.usage
            == "Students used the model during the activity."
        )
        assert result.new_storage_keys == ()

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_service_does_not_commit(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
        )

        db.rollback()

        count = (
            db.query(SessionTLM)
            .filter(
                SessionTLM.teaching_session_id == session.id
            )
            .count()
        )

        assert count == 0

    finally:
        db.close()


def test_normal_tlm_requires_positive_quantity(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        with pytest.raises(
            InvalidQuantityError,
            match="at least 1",
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=tlm.id,
                quantity=0,
            )

    finally:
        db.rollback()
        db.close()


def test_negative_quantity_is_rejected_by_service(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        with pytest.raises(InvalidQuantityError):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=tlm.id,
                quantity=-1,
            )

    finally:
        db.rollback()
        db.close()


def test_na_tlm_requires_zero_quantity(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, _, session = create_test_data(db)

        na_tlm = get_na_tlm(db)

        result = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=na_tlm.id,
            quantity=0,
            data_origin="TEST",
        )

        assert result.session_tlm.quantity == 0

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_na_tlm_rejects_positive_quantity(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, _, session = create_test_data(db)

        na_tlm = get_na_tlm(db)

        with pytest.raises(
            InvalidQuantityError,
            match="must be 0",
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=na_tlm.id,
                quantity=1,
            )

    finally:
        db.rollback()
        db.close()


def test_duplicate_tlm_is_rejected_by_service(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
        )

        with pytest.raises(DuplicateTLMError):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=tlm.id,
                quantity=2,
            )

    finally:
        db.rollback()
        db.close()


def test_inactive_tlm_is_rejected(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        tlm.is_active = False
        db.flush()

        with pytest.raises(
            InactiveTLMError,
            match="Inactive TLMs",
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=tlm.id,
                quantity=1,
            )

    finally:
        db.rollback()
        db.close()


@pytest.mark.parametrize(
    "status",
    [
        "PLANNED",
        "COMPLETED",
        "CANCELLED",
    ],
)
def test_non_in_progress_session_is_locked(
    service: SessionTLMService,
    status: str,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        session.status = status
        db.flush()

        with pytest.raises(
            SessionNotEditableError,
            match="IN_PROGRESS",
        ):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=tlm.id,
                quantity=1,
            )

    finally:
        db.rollback()
        db.close()


def test_na_cannot_be_combined_with_normal_tlm(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, normal_tlm, session = create_test_data(db)

        na_tlm = get_na_tlm(db)

        service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=normal_tlm.id,
            quantity=1,
        )

        with pytest.raises(NAConflictError):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=na_tlm.id,
                quantity=0,
            )

    finally:
        db.rollback()
        db.close()


def test_normal_tlm_cannot_be_added_when_na_exists(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, normal_tlm, session = create_test_data(db)

        na_tlm = get_na_tlm(db)

        service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=na_tlm.id,
            quantity=0,
        )

        with pytest.raises(NAConflictError):
            service.create(
                db,
                teaching_session_id=session.id,
                tlm_id=normal_tlm.id,
                quantity=1,
            )

    finally:
        db.rollback()
        db.close()


def test_multiple_normal_tlms_are_allowed(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, first_tlm, session = create_test_data(db)

        second_tlm = TLM(
            name=f"Second Test TLM {uuid.uuid4()}",
            description="Second test teaching-learning material.",
            is_active=True,
            data_origin="TEST",
        )
        db.add(second_tlm)
        db.flush()

        first = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=first_tlm.id,
            quantity=1,
        )

        second = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=second_tlm.id,
            quantity=2,
        )

        assert first.session_tlm.id != second.session_tlm.id

        db.commit()

    finally:
        db.rollback()
        db.close()

def test_create_session_tlm_with_photo(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        result = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            usage="Students used the TLM.",
            photo=create_photo_input(),
            data_origin="TEST",
        )

        session_tlm = result.session_tlm

        assert session_tlm.photo_id is not None
        assert len(result.new_storage_keys) == 1

        photo = (
            db.query(Photo)
            .filter(Photo.id == session_tlm.photo_id)
            .one()
        )

        assert photo.photo_category == "TLM_ACTIVITY"
        assert photo.content_type == "image/jpeg"
        assert photo.file_size_bytes <= 1_048_576
        assert photo.latitude == Decimal("19.076000")
        assert photo.longitude == Decimal("72.877700")

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_photo_storage_can_be_compensated_after_rollback(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        result = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        assert len(result.new_storage_keys) == 1

        storage_key = result.new_storage_keys[0]

        assert service.photo_service.storage.exists(
            storage_key
        )

        db.rollback()

        service.compensate_new_storage(
            result.new_storage_keys
        )

        assert not service.photo_service.storage.exists(
            storage_key
        )

    finally:
        db.rollback()
        db.close()


def test_update_session_tlm_replaces_photo(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        old_photo_id = created.session_tlm.photo_id
        old_storage_key = created.new_storage_keys[0]

        db.flush()

        updated = service.update(
            db,
            session_tlm_id=created.session_tlm.id,
            photo=create_photo_input(),
        )

        db.flush()
        db.refresh(updated.session_tlm)

        assert updated.session_tlm.photo_id is not None
        assert (
            updated.session_tlm.photo_id
            != old_photo_id
        )
        assert updated.new_storage_keys
        assert updated.obsolete_storage_keys == (
            old_storage_key,
        )

        new_storage_key = updated.new_storage_keys[0]

        assert service.photo_service.storage.exists(
            new_storage_key
        )

        assert (
            db.query(Photo)
            .filter(Photo.id == old_photo_id)
            .count()
            == 0
        )

        db.commit()

        service.cleanup_storage(
            updated.obsolete_storage_keys
        )

        assert not service.photo_service.storage.exists(
            old_storage_key
        )
    finally:
        db.rollback()
        db.close()


def test_update_session_tlm_removes_photo(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        photo_id = created.session_tlm.photo_id
        storage_key = created.new_storage_keys[0]

        updated = service.update(
            db,
            session_tlm_id=created.session_tlm.id,
            remove_photo=True,
        )

        assert updated.session_tlm.photo_id is None
        assert updated.obsolete_storage_keys == (
            storage_key,
        )

        assert (
            db.query(Photo)
            .filter(Photo.id == photo_id)
            .count()
            == 0
        )

        db.commit()

        service.cleanup_storage(
            updated.obsolete_storage_keys
        )

        assert not service.photo_service.storage.exists(
            storage_key
        )

    finally:
        db.rollback()
        db.close()


def test_update_rejects_photo_and_remove_photo_together(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
        )

        with pytest.raises(
            InvalidTLMPhotoError,
            match="replacement photo and photo removal",
        ):
            service.update(
                db,
                session_tlm_id=created.session_tlm.id,
                photo=create_photo_input(),
                remove_photo=True,
            )

    finally:
        db.rollback()
        db.close()


def test_delete_session_tlm_with_photo(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            photo=create_photo_input(),
            data_origin="TEST",
        )

        session_tlm_id = created.session_tlm.id
        photo_id = created.session_tlm.photo_id
        storage_key = created.new_storage_keys[0]

        result = service.delete(
            db,
            session_tlm_id=session_tlm_id,
        )

        assert result.obsolete_storage_keys == (
            storage_key,
        )

        assert (
            db.query(SessionTLM)
            .filter(SessionTLM.id == session_tlm_id)
            .count()
            == 0
        )

        assert (
            db.query(Photo)
            .filter(Photo.id == photo_id)
            .count()
            == 0
        )

        db.commit()

        service.cleanup_storage(
            result.obsolete_storage_keys
        )

        assert not service.photo_service.storage.exists(
            storage_key
        )

    finally:
        db.rollback()
        db.close()


def test_update_is_locked_after_session_completion(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
        )

        session.status = "COMPLETED"
        db.flush()

        with pytest.raises(SessionNotEditableError):
            service.update(
                db,
                session_tlm_id=created.session_tlm.id,
                quantity=2,
            )

    finally:
        db.rollback()
        db.close()


def test_delete_is_locked_after_session_completion(
    service: SessionTLMService,
):
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        created = service.create(
            db,
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
        )

        session.status = "COMPLETED"
        db.flush()

        with pytest.raises(SessionNotEditableError):
            service.delete(
                db,
                session_tlm_id=created.session_tlm.id,
            )

    finally:
        db.rollback()
        db.close()