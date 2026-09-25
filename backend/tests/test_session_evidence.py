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
    SessionEvidence,
    TeachingSession,
    User,
)


def create_test_data(db):
    """Create the minimum related records required for SessionEvidence."""

    school = School(
        school_code=f"TEST-{uuid.uuid4().hex[:8]}",
        school_name=f"Evidence Test School {uuid.uuid4().hex[:8]}",
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
        email=f"evidence-{uuid.uuid4().hex[:8]}@example.com",
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


def create_photo(db, category="SESSION_EVIDENCE"):
    photo = Photo(
        photo_category=category,
        storage_key=f"test/{uuid.uuid4()}.jpg",
        original_filename="evidence.jpg",
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


def test_create_valid_session_evidence():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence)
        db.flush()

        assert evidence.id is not None
        assert evidence.teaching_session_id == session.id
        assert evidence.photo_id == photo.id
        assert evidence.data_origin == "TEST"

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_teaching_session_can_have_only_one_evidence():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        photo1 = create_photo(db)
        photo2 = create_photo(db)

        evidence1 = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo1.id,
            data_origin="TEST",
        )

        db.add(evidence1)
        db.flush()

        evidence2 = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo2.id,
            data_origin="TEST",
        )

        db.add(evidence2)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    finally:
        db.close()


def test_photo_cannot_be_reused_for_two_evidence_records():
    db = SessionLocal()

    try:
        _, class_division, user, session1 = create_test_data(db)

        session2 = TeachingSession(
            class_division_id=class_division.id,
            para_teacher_id=user.id,
            session_date=date(2026, 9, 25),
            status="IN_PROGRESS",
            data_origin="TEST",
        )
        db.add(session2)
        db.flush()

        photo = create_photo(db)

        evidence1 = SessionEvidence(
            teaching_session_id=session1.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence1)
        db.flush()

        evidence2 = SessionEvidence(
            teaching_session_id=session2.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence2)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    finally:
        db.close()


@pytest.mark.parametrize(
    "data_origin",
    ["PRODUCTION", "DEMO", "TEST"],
)
def test_valid_data_origin_values(data_origin):
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin=data_origin,
        )

        db.add(evidence)
        db.flush()

        assert evidence.data_origin == data_origin

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_invalid_data_origin_rejected():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin="INVALID",
        )

        db.add(evidence)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    finally:
        db.close()


def test_missing_teaching_session_rejected():
    db = SessionLocal()

    try:
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=uuid.uuid4(),
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    finally:
        db.close()


def test_missing_photo_rejected():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=uuid.uuid4(),
            data_origin="TEST",
        )

        db.add(evidence)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()

    finally:
        db.close()


def test_teaching_session_relationship():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence)
        db.flush()

        assert evidence.teaching_session is session

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_photo_relationship():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence)
        db.flush()

        assert evidence.photo is photo

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_reverse_teaching_session_relationship():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence)
        db.flush()

        assert session.session_evidence is evidence

        db.commit()

    finally:
        db.rollback()
        db.close()


def test_reverse_photo_relationship():
    db = SessionLocal()

    try:
        _, _, _, session = create_test_data(db)
        photo = create_photo(db)

        evidence = SessionEvidence(
            teaching_session_id=session.id,
            photo_id=photo.id,
            data_origin="TEST",
        )

        db.add(evidence)
        db.flush()

        assert photo.session_evidence is evidence

        db.commit()

    finally:
        db.rollback()
        db.close()