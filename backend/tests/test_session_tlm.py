import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

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


def create_test_data(db):
    """Create the minimum related records required for SessionTLM."""

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
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
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

    return school, class_division, user, tlm, session


def create_photo(db):
    photo = Photo(
        photo_category="TLM_ACTIVITY",
        storage_key=f"test/{uuid.uuid4()}.jpg",
        original_filename="test.jpg",
        content_type="image/jpeg",
        file_size_bytes=1000,
        width=100,
        height=100,
        captured_at=datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc),
        latitude=Decimal("19.076000"),
        longitude=Decimal("72.877700"),
        data_origin="TEST",
    )
    db.add(photo)
    db.flush()
    return photo


def test_create_valid_session_tlm():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=2,
            usage="Used by students during the activity.",
            data_origin="TEST",
        )

        db.add(session_tlm)
        db.commit()

        assert session_tlm.id is not None
        assert session_tlm.teaching_session_id == session.id
        assert session_tlm.tlm_id == tlm.id
        assert session_tlm.quantity == 2
        assert session_tlm.usage == "Used by students during the activity."

    finally:
        db.rollback()
        db.close()


def test_zero_quantity_is_allowed_at_database_level():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=0,
            data_origin="TEST",
        )

        db.add(session_tlm)
        db.commit()

        assert session_tlm.quantity == 0

    finally:
        db.rollback()
        db.close()


def test_negative_quantity_is_rejected():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=-1,
            data_origin="TEST",
        )

        db.add(session_tlm)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        db.close()


def test_duplicate_tlm_in_same_session_is_rejected():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        first = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            data_origin="TEST",
        )
        db.add(first)
        db.commit()

        second = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=2,
            data_origin="TEST",
        )
        db.add(second)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        db.close()


def test_same_photo_cannot_be_reused():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)
        photo = create_photo(db)

        first = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            photo_id=photo.id,
            data_origin="TEST",
        )
        db.add(first)
        db.commit()

        second_tlm = TLM(
            name=f"Second Test TLM {uuid.uuid4()}",
            description="Second test TLM",
            is_active=True,
            data_origin="TEST",
        )
        db.add(second_tlm)
        db.commit()

        second = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=second_tlm.id,
            quantity=1,
            photo_id=photo.id,
            data_origin="TEST",
        )
        db.add(second)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        db.close()


def test_photo_is_optional():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            photo_id=None,
            data_origin="TEST",
        )

        db.add(session_tlm)
        db.commit()

        assert session_tlm.photo_id is None

    finally:
        db.rollback()
        db.close()


def test_invalid_teaching_session_foreign_key_is_rejected():
    db = SessionLocal()

    try:
        _, _, _, tlm, _ = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=uuid.uuid4(),
            tlm_id=tlm.id,
            quantity=1,
            data_origin="TEST",
        )

        db.add(session_tlm)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        db.close()


def test_invalid_tlm_foreign_key_is_rejected():
    db = SessionLocal()

    try:
        _, _, _, _, session = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=uuid.uuid4(),
            quantity=1,
            data_origin="TEST",
        )

        db.add(session_tlm)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        db.close()


def test_invalid_data_origin_is_rejected():
    db = SessionLocal()

    try:
        _, _, _, tlm, session = create_test_data(db)

        session_tlm = SessionTLM(
            teaching_session_id=session.id,
            tlm_id=tlm.id,
            quantity=1,
            data_origin="INVALID",
        )

        db.add(session_tlm)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        db.close()