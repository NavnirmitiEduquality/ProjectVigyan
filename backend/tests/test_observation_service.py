from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile
from unittest.mock import Mock

from app.routers.observations import _compensate_failed_transaction
import pytest
from PIL import Image

from app.database import SessionLocal
from app.models import ClassDivision, School, User, UserAssignment
from app.services.observation_service import (
    DocumentStorage,
    ObservationService,
    PhotoInput,
    ValidationError,
    ObservationOperation,
)
from app.services.photo import LocalPrivatePhotoStorage, PhotoProcessingService, PhotoService


def jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="JPEG")
    return output.getvalue()


def photo_input() -> PhotoInput:
    return PhotoInput(
        image_bytes=jpeg(),
        captured_at=datetime.now(timezone.utc),
        latitude=Decimal("19.076"),
        longitude=Decimal("72.8777"),
        original_filename="evidence.jpg",
        data_origin="TEST",
    )


def test_external_links_require_https_and_confirmation():
    with pytest.raises(ValidationError):
        ObservationService.validate_link("https://example.com/report", False)
    with pytest.raises(ValidationError):
        ObservationService.validate_link("http://example.com/report", True)
    with pytest.raises(ValidationError):
        ObservationService.validate_link("https://user:pass@example.com/report", True)
    assert ObservationService.validate_link("https://example.com/report", True) == "https://example.com/report"


def test_document_validation_checks_content_and_size():
    with pytest.raises(ValidationError):
        ObservationService.validate_document("report.pdf", "application/pdf", b"not-pdf")
    with pytest.raises(ValidationError):
        ObservationService.validate_document("report.exe", "application/octet-stream", b"x")
    with pytest.raises(ValidationError):
        ObservationService.validate_document("report.txt", "text/plain", b"x" * (5 * 1_048_576 + 1))
    suffix, media_type = ObservationService.validate_document("report.txt", "text/plain", b"valid")
    assert suffix == ".txt"
    assert media_type == "text/plain"



def test_document_validation_rejects_invalid_docx():
    with pytest.raises(ValidationError, match="Invalid DOCX"):
        ObservationService.validate_document(
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK-not-a-real-zip-file",
        )


def test_document_validation_rejects_zip_without_word_document():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")

    with pytest.raises(ValidationError, match="Invalid DOCX"):
        ObservationService.validate_document(
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer.getvalue(),
        )


def test_document_validation_rejects_invalid_utf8_txt():
    with pytest.raises(ValidationError, match="UTF-8"):
        ObservationService.validate_document(
            "report.txt",
            "text/plain",
            b"\xff\xfe\xfa",
        )


def test_document_validation_accepts_valid_docx_structure():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")

    suffix, media_type = ObservationService.validate_document(
        "report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer.getvalue(),
    )

    assert suffix == ".docx"
    assert media_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_document_storage_uses_private_random_keys(tmp_path: Path):
    storage = DocumentStorage(tmp_path)
    key = storage.save(b"report", ".txt", "classroom-observations")
    assert key.startswith("classroom-observations/")
    assert storage.open(key).read() == b"report"


def test_para_observation_derives_target_school_and_creates_pending_report(tmp_path: Path):
    db = SessionLocal()
    try:
        school = School(
            school_code=f"OBS-{uuid4().hex[:8]}",
            school_name="Observation School",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add(school)
        db.flush()
        division = ClassDivision(
            school_id=school.id,
            class_level=5,
            division="A",
            status="ACTIVE",
            data_origin="TEST",
        )
        observer = User(
            user_code=f"OBS-{uuid4().hex[:8]}",
            full_name="Observer",
            email=f"{uuid4().hex}@example.com",
            password_hash="hash",
            status="ACTIVE",
            data_origin="TEST",
        )
        target = User(
            user_code=f"PT-{uuid4().hex[:8]}",
            full_name="Target",
            email=f"{uuid4().hex}@example.com",
            password_hash="hash",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add_all([division, observer, target])
        db.flush()
        db.add(UserAssignment(
            user_id=target.id,
            scope_type="SCHOOL",
            school_id=school.id,
            start_date=date.today(),
            is_active=True,
        ))
        db.flush()
        service = ObservationService(
            PhotoService(PhotoProcessingService(), LocalPrivatePhotoStorage(tmp_path / "photos")),
            DocumentStorage(tmp_path / "reports"),
        )
        record = service.create_para_observation(
            db,
            observer=observer,
            target_teacher_id=target.id,
            class_level=5,
            class_division_id=division.id,
            topic="Matter",
            photo=photo_input(),
            data_origin="TEST",
        )
        assert record.school_id == school.id
        assert record.report.status == "PENDING"
        assert record.report.observation_id == record.id
        db.rollback()
    finally:
        db.close()


def test_inspection_rejects_inspector_without_active_school_assignment(tmp_path: Path):
    db = SessionLocal()
    try:
        school = School(
            school_code=f"INSP-{uuid4().hex[:8]}",
            school_name="Inspection School",
            status="ACTIVE",
            data_origin="TEST",
        )
        inspector = User(
            user_code=f"INSP-{uuid4().hex[:8]}",
            full_name="Inspector",
            email=f"{uuid4().hex}@example.com",
            password_hash="hash",
            status="ACTIVE",
            data_origin="TEST",
        )
        target = User(
            user_code=f"PT-{uuid4().hex[:8]}",
            full_name="Target Para Teacher",
            email=f"{uuid4().hex}@example.com",
            password_hash="hash",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add_all([school, inspector, target])
        db.flush()

        db.add(
            UserAssignment(
                user_id=target.id,
                scope_type="SCHOOL",
                school_id=school.id,
                start_date=date.today(),
                is_active=True,
            )
        )
        db.flush()

        service = ObservationService(
            PhotoService(
                PhotoProcessingService(),
                LocalPrivatePhotoStorage(tmp_path / "photos"),
            ),
            DocumentStorage(tmp_path / "reports"),
        )

        with pytest.raises(Exception, match="not authorized for this school"):
            service.create_inspection(
                db,
                inspector=inspector,
                para_teacher_id=target.id,
                class_division_id=None,
                topic=None,
                photo=photo_input(),
                data_origin="TEST",
            )
    finally:
        db.rollback()
        db.close()


def test_inspection_rejects_division_from_another_school(tmp_path: Path):
    db = SessionLocal()
    try:
        school_a = School(
            school_code=f"INSA-{uuid4().hex[:8]}",
            school_name="Target School",
            status="ACTIVE",
            data_origin="TEST",
        )
        school_b = School(
            school_code=f"INSB-{uuid4().hex[:8]}",
            school_name="Other School",
            status="ACTIVE",
            data_origin="TEST",
        )
        inspector = User(
            user_code=f"INSP-{uuid4().hex[:8]}",
            full_name="Inspector",
            email=f"{uuid4().hex}@example.com",
            password_hash="hash",
            status="ACTIVE",
            data_origin="TEST",
        )
        target = User(
            user_code=f"PT-{uuid4().hex[:8]}",
            full_name="Target Para Teacher",
            email=f"{uuid4().hex}@example.com",
            password_hash="hash",
            status="ACTIVE",
            data_origin="TEST",
        )
        other_division = ClassDivision(
            school_id=school_b.id,
            class_level=5,
            division="A",
            status="ACTIVE",
            data_origin="TEST",
        )
        db.add_all([school_a, school_b, inspector, target])
        db.flush()

        other_division.school_id = school_b.id
        db.add(other_division)
        db.add_all([
            UserAssignment(
                user_id=target.id,
                scope_type="SCHOOL",
                school_id=school_a.id,
                start_date=date.today(),
                is_active=True,
            ),
            UserAssignment(
                user_id=inspector.id,
                scope_type="SCHOOL",
                school_id=school_a.id,
                start_date=date.today(),
                is_active=True,
            ),
        ])
        db.flush()

        service = ObservationService(
            PhotoService(
                PhotoProcessingService(),
                LocalPrivatePhotoStorage(tmp_path / "photos"),
            ),
            DocumentStorage(tmp_path / "reports"),
        )

        with pytest.raises(ValidationError, match="does not match the target school"):
            service.create_inspection(
                db,
                inspector=inspector,
                para_teacher_id=target.id,
                class_division_id=other_division.id,
                topic=None,
                photo=photo_input(),
                data_origin="TEST",
            )
    finally:
        db.rollback()
        db.close()


def test_failed_transaction_rolls_back_and_deletes_new_photo():
    db = Mock()
    service = Mock()
    operation = ObservationOperation(
        record=Mock(),
        new_storage_keys=("observations/new-photo.jpg",),
    )

    _compensate_failed_transaction(db, service, operation)

    db.rollback.assert_called_once_with()
    service.photo_service.delete.assert_called_once_with(
        "observations/new-photo.jpg"
    )


def test_cleanup_failure_does_not_escape_compensation():
    db = Mock()
    service = Mock()
    service.photo_service.delete.side_effect = OSError("storage unavailable")
    operation = ObservationOperation(
        record=Mock(),
        new_storage_keys=("observations/new-photo.jpg",),
    )

    _compensate_failed_transaction(db, service, operation)

    db.rollback.assert_called_once_with()
    service.photo_service.delete.assert_called_once_with(
        "observations/new-photo.jpg"
    )


def test_para_observation_commit_failure_cleans_up_photo(monkeypatch):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from unittest.mock import Mock

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.dependencies import require_permission
    from app.main import app
    from app.routers import observations as observations_router
    from app.services.observation_service import ObservationOperation

    storage_key = "observations/test-new-photo.jpg"
    record_id = uuid4()
    school_id = uuid4()
    division_id = uuid4()

    record = Mock()
    record.id = record_id
    record.school_id = school_id
    record.class_division_id = division_id
    record.topic = "Matter"
    record.observed_at = datetime.now(timezone.utc)
    record.report.status = "PENDING"

    operation = ObservationOperation(
        record=record,
        new_storage_keys=(storage_key,),
    )

    service = Mock()
    service.create_para_observation.return_value = operation

    db = Mock()
    db.commit.side_effect = RuntimeError("simulated commit failure")

    user = Mock()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(observations_router, "_service", lambda: service)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/observations/para-teacher",
                data={
                    "target_teacher_id": str(uuid4()),
                    "class_level": "5",
                    "class_division_id": str(division_id),
                    "topic": "Matter",
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "latitude": "19.076",
                    "longitude": "72.8777",
                },
                files={"photo": ("evidence.jpg", jpeg(), "image/jpeg")},
            )

        assert response.status_code == 500
        db.rollback.assert_called_once_with()
        service.photo_service.delete.assert_called_once_with(storage_key)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_admin_report_correction_commit_failure_cleans_new_file(monkeypatch):
    from fastapi import HTTPException
    from app.routers import observations as observations_router

    record_id = uuid4()
    report = Mock()
    report.id = uuid4()
    report.status = "COMPLETE"
    report.mode = "UPLOAD"
    report.external_url = None
    report.storage_key = "classroom-observations/existing.pdf"

    record = Mock()
    record.report = report
    record.observer_id = uuid4()

    db = Mock()
    db.commit.side_effect = RuntimeError("simulated commit failure")

    service = Mock()

    def simulate_report_submission(*args, **kwargs):
        report.status = "COMPLETE"
        report.storage_key = "classroom-observations/new.pdf"
        return report, "classroom-observations/new.pdf"

    service.submit_report.side_effect = simulate_report_submission

    monkeypatch.setattr(
        observations_router,
        "_service",
        lambda: service,
    )
    monkeypatch.setattr(
        observations_router,
        "_report_context",
        lambda *args: (record, report),
    )
    monkeypatch.setattr(
        observations_router,
        "_can_view_record",
        lambda *args: True,
    )

    user = Mock()
    user.id = uuid4()

    with pytest.raises(RuntimeError, match="simulated commit failure"):
        observations_router._submit_report(
            "observation",
            record_id,
            user,
            db,
            filename="replacement.pdf",
            content_type="application/pdf",
            data=b"%PDF-1.7 test",
            administrative=True,
            reason="Correcting an inaccurate report",
        )

    db.rollback.assert_called_once_with()
    service.documents.delete.assert_called_once_with(
        "classroom-observations/new.pdf"
    )


def test_admin_report_correction_records_history_and_increments_version(monkeypatch):
    from app.routers import observations as observations_router

    record_id = uuid4()
    actor_id = uuid4()
    report_id = uuid4()

    report = Mock()
    report.id = report_id
    report.status = "COMPLETE"
    report.mode = "UPLOAD"
    report.external_url = None
    report.storage_key = "classroom-observations/previous.pdf"
    report.version = 2

    record = Mock()
    record.report = report
    record.observer_id = uuid4()

    db = Mock()
    service = Mock()

    def simulate_report_submission(*args, **kwargs):
        report.status = "COMPLETE"
        report.mode = "UPLOAD"
        report.storage_key = "classroom-observations/replacement.pdf"
        report.external_url = None
        report.version += 1
        return report, report.storage_key

    service.submit_report.side_effect = simulate_report_submission

    monkeypatch.setattr(observations_router, "_service", lambda: service)
    monkeypatch.setattr(
        observations_router,
        "_report_context",
        lambda *args: (record, report),
    )
    monkeypatch.setattr(
        observations_router,
        "_can_view_record",
        lambda *args: True,
    )

    user = Mock()
    user.id = actor_id

    result = observations_router._submit_report(
        "observation",
        record_id,
        user,
        db,
        filename="replacement.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.7 test",
        administrative=True,
        reason="Correcting an inaccurate report",
    )

    assert result["status"] == "COMPLETE"
    assert report.version == 3
    db.add.assert_called_once()

    correction = db.add.call_args.args[0]
    assert isinstance(correction, observations_router.ObservationReportCorrection)
    assert correction.observation_report_id == report_id
    assert correction.inspection_report_id is None
    assert correction.actor_id == actor_id
    assert correction.previous_reference == "classroom-observations/previous.pdf"
    assert correction.replacement_reference == "classroom-observations/replacement.pdf"
    assert correction.reason == "Correcting an inaccurate report"
    db.commit.assert_called_once_with()


def test_admin_report_correction_validation_failure_rolls_back_without_history(
    monkeypatch,
):
    from app.routers import observations as observations_router
    from app.services.observation_service import ValidationError
    from fastapi import HTTPException

    record_id = uuid4()
    report = Mock()
    report.id = uuid4()
    report.status = "COMPLETE"
    report.mode = "UPLOAD"
    report.external_url = None
    report.storage_key = "classroom-observations/existing.pdf"
    report.version = 2

    record = Mock()
    record.report = report
    record.observer_id = uuid4()

    db = Mock()
    service = Mock()
    service.submit_report.side_effect = ValidationError(
        "Invalid replacement report."
    )

    monkeypatch.setattr(observations_router, "_service", lambda: service)
    monkeypatch.setattr(
        observations_router,
        "_report_context",
        lambda *args: (record, report),
    )
    monkeypatch.setattr(
        observations_router,
        "_can_view_record",
        lambda *args: True,
    )

    user = Mock()
    user.id = uuid4()

    with pytest.raises(HTTPException, match="Invalid replacement report") as exc_info:
        observations_router._submit_report(
            "observation",
            record_id,
            user,
            db,
            filename="replacement.pdf",
            content_type="application/pdf",
            data=b"invalid PDF",
            administrative=True,
            reason="Correcting an inaccurate report",
        )
    assert exc_info.value.status_code == 422
    assert report.mode == "UPLOAD"
    assert report.storage_key == "classroom-observations/existing.pdf"
    assert report.version == 2
    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()
    db.add.assert_not_called()
    service.documents.delete.assert_not_called()


def test_submit_report_flush_failure_deletes_new_file(tmp_path: Path):
    from app.services.observation_service import DocumentStorage

    storage = DocumentStorage(tmp_path / "reports")
    service = ObservationService(document_storage=storage)

    report = Mock()
    report.status = "PENDING"
    report.version = 1

    db = Mock()
    db.flush.side_effect = RuntimeError("simulated flush failure")

    with pytest.raises(RuntimeError, match="simulated flush failure"):
        service.submit_report(
            db,
            report,
            user_id=uuid4(),
            filename="report.txt",
            content_type="text/plain",
            data=b"Valid report text",
            area="classroom-observations",
        )

    saved_files = list((tmp_path / "reports").rglob("*"))
    saved_files = [path for path in saved_files if path.is_file()]

    assert saved_files == []


def test_submit_report_cleanup_failure_preserves_flush_exception(
    tmp_path: Path,
    monkeypatch,
):
    from app.services.observation_service import DocumentStorage

    storage = DocumentStorage(tmp_path / "reports")
    service = ObservationService(document_storage=storage)

    report = Mock()
    report.status = "PENDING"
    report.version = 1

    db = Mock()
    db.flush.side_effect = RuntimeError("simulated flush failure")

    def fail_delete(key):
        raise OSError("simulated storage cleanup failure")

    monkeypatch.setattr(storage, "delete", fail_delete)

    with pytest.raises(RuntimeError, match="simulated flush failure"):
        service.submit_report(
            db,
            report,
            user_id=uuid4(),
            filename="report.txt",
            content_type="text/plain",
            data=b"Valid report text",
            area="classroom-observations",
        )


def test_para_observation_notification_flush_failure_cleans_photo(
    monkeypatch,
):
    from app.services.observation_service import PhotoInput

    db = Mock()
    service = Mock(spec=ObservationService)
    photo = Mock()
    photo.id = uuid4()
    photo.storage_key = "observations/new-photo.jpg"
    service.create_photo.return_value = photo
    service.teacher_school.return_value = uuid4()
    service.division.return_value = Mock()

    # Fail when the service flushes the notification after creating
    # the observation and report.
    db.flush.side_effect = [None, RuntimeError("notification flush failed")]

    real_service = ObservationService()
    real_service.photo_service = Mock()
    real_service.create_photo = service.create_photo
    real_service.teacher_school = service.teacher_school
    real_service.division = service.division
    real_service.create_notification = Mock()

    real_service.create_notification.side_effect = lambda *args, **kwargs: (
        db.flush()
    )

    observer = Mock()
    observer.id = uuid4()

    with pytest.raises(RuntimeError, match="notification flush failed"):
        real_service.create_para_observation(
            db,
            observer=observer,
            target_teacher_id=uuid4(),
            class_level=5,
            class_division_id=uuid4(),
            topic="Matter",
            photo=PhotoInput(
                image_bytes=b"unused",
                captured_at=datetime.now(timezone.utc),
                latitude=Decimal("19.076"),
                longitude=Decimal("72.8777"),
                original_filename="evidence.jpg",
            ),
        )

    real_service.photo_service.delete.assert_called_once_with(
        "observations/new-photo.jpg"
    )


def test_para_observation_refresh_failure_preserves_committed_photo(monkeypatch):
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.routers import observations as observations_router
    from app.services.observation_service import ObservationOperation

    storage_key = "observations/committed-photo.jpg"

    record = Mock()
    record.id = uuid4()
    record.school_id = uuid4()
    record.class_division_id = uuid4()
    record.topic = "Matter"
    record.observed_at = datetime.now(timezone.utc)
    record.report.status = "PENDING"

    operation = ObservationOperation(
        record=record,
        new_storage_keys=(storage_key,),
    )

    service = Mock()
    service.create_para_observation.return_value = operation

    db = Mock()
    db.refresh.side_effect = RuntimeError("simulated refresh failure")

    user = Mock()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(observations_router, "_service", lambda: service)

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/observations/para-teacher",
                data={
                    "target_teacher_id": str(uuid4()),
                    "class_level": "5",
                    "class_division_id": str(record.class_division_id),
                    "topic": "Matter",
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "latitude": "19.076",
                    "longitude": "72.8777",
                },
                files={"photo": ("evidence.jpg", jpeg(), "image/jpeg")},
            )

        assert response.status_code == 500
        db.commit.assert_called_once_with()
        db.rollback.assert_called_once_with()
        service.photo_service.delete.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_para_observation_cleanup_failure_preserves_notification_error():
    db = Mock()
    real_service = ObservationService()
    photo = Mock()
    photo.id = uuid4()
    photo.storage_key = "observations/new-photo.jpg"

    real_service.photo_service = Mock()
    real_service.photo_service.delete.side_effect = OSError(
        "simulated photo cleanup failure"
    )
    real_service.create_photo = Mock(return_value=photo)
    real_service.teacher_school = Mock(return_value=uuid4())
    real_service.division = Mock(return_value=Mock())
    real_service.create_notification = Mock(
        side_effect=RuntimeError("notification flush failed")
    )

    observer = Mock()
    observer.id = uuid4()

    with pytest.raises(RuntimeError, match="notification flush failed"):
        real_service.create_para_observation(
            db,
            observer=observer,
            target_teacher_id=uuid4(),
            class_level=5,
            class_division_id=uuid4(),
            topic="Matter",
            photo=PhotoInput(
                image_bytes=b"unused",
                captured_at=datetime.now(timezone.utc),
                latitude=Decimal("19.076"),
                longitude=Decimal("72.8777"),
                original_filename="evidence.jpg",
            ),
        )

    real_service.photo_service.delete.assert_called_once_with(
        "observations/new-photo.jpg"
    )
