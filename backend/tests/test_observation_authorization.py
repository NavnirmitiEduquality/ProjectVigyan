from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import ClassroomObservation, STEMInspection
from app.models.user import UserAssignment
from app.routers import observations as router


def test_para_teacher_cannot_view_another_users_observation(monkeypatch):
    current_user = Mock()
    current_user.id = uuid4()

    record = Mock(spec=ClassroomObservation)
    record.observer_id = uuid4()
    record.school_id = uuid4()

    db = Mock()
    monkeypatch.setattr(
        router,
        "get_user_role_codes",
        lambda user, session: {"PARA_TEACHER"},
    )

    assert router._can_view_record(record, current_user, db) is False



def test_stem_coordinator_can_view_observation_across_schools(monkeypatch):
    current_user = Mock()
    current_user.id = uuid4()

    record = Mock(spec=ClassroomObservation)
    record.school_id = uuid4()

    db = Mock()
    monkeypatch.setattr(
        router,
        "get_user_role_codes",
        lambda user, session: {"STEM_COORDINATOR"},
    )
    monkeypatch.setattr(
        router,
        "get_authorized_school_ids",
        lambda user, session: None,
    )

    assert router._can_view_record(record, current_user, db) is True


def test_stem_coordinator_can_view_inspection_across_schools(monkeypatch):
    current_user = Mock()
    current_user.id = uuid4()

    record = Mock(spec=STEMInspection)
    record.school_id = uuid4()

    db = Mock()
    monkeypatch.setattr(
        router,
        "get_user_role_codes",
        lambda user, session: {"STEM_COORDINATOR"},
    )
    monkeypatch.setattr(
        router,
        "get_authorized_school_ids",
        lambda user, session: None,
    )

    assert router._can_view_record(record, current_user, db) is True


def test_user_cannot_submit_another_users_observation_report(monkeypatch):
    record_id = uuid4()
    current_user = Mock()
    current_user.id = uuid4()

    record = Mock(spec=ClassroomObservation)
    record.observer_id = uuid4()
    record.report = Mock()

    db = Mock()
    monkeypatch.setattr(
        router,
        "_report_context",
        lambda session, kind, requested_id: (record, record.report),
    )
    monkeypatch.setattr(
        router,
        "_can_view_record",
        lambda record, user, session: True,
    )

    with pytest.raises(HTTPException) as exc_info:
        router._submit_report(
            "observation",
            record_id,
            current_user,
            db,
            link="https://example.com/report",
            sharing_confirmed=True,
        )

    assert exc_info.value.status_code == 403
    assert "not authorized to submit" in exc_info.value.detail
    db.commit.assert_not_called()


def test_user_cannot_submit_another_users_inspection_report(monkeypatch):
    record_id = uuid4()
    current_user = Mock()
    current_user.id = uuid4()

    record = Mock(spec=STEMInspection)
    record.inspector_id = uuid4()
    record.report = Mock()

    db = Mock()
    monkeypatch.setattr(
        router,
        "_report_context",
        lambda session, kind, requested_id: (record, record.report),
    )
    monkeypatch.setattr(
        router,
        "_can_view_record",
        lambda record, user, session: True,
    )

    with pytest.raises(HTTPException) as exc_info:
        router._submit_report(
            "inspection",
            record_id,
            current_user,
            db,
            link="https://example.com/report",
            sharing_confirmed=True,
        )

    assert exc_info.value.status_code == 403
    assert "not authorized to submit" in exc_info.value.detail
    db.commit.assert_not_called()


def test_pending_notifications_excludes_completed_reports(monkeypatch):
    current_user = Mock()
    current_user.id = uuid4()

    record_id = uuid4()
    notification = Mock()
    notification.id = uuid4()
    notification.observation_id = record_id
    notification.inspection_id = None
    notification.message = "Report pending"
    notification.is_read = False

    record = Mock(spec=ClassroomObservation)
    record.report.status = "COMPLETE"

    db = Mock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        notification
    ]
    db.get.return_value = record

    monkeypatch.setattr(
        router,
        "_can_view_record",
        lambda record, user, session: True,
    )

    result = router.pending_notifications(current_user, db)

    assert result == []


def test_pending_notifications_excludes_unauthorized_records(monkeypatch):
    current_user = Mock()
    current_user.id = uuid4()

    record_id = uuid4()
    notification = Mock()
    notification.id = uuid4()
    notification.observation_id = record_id
    notification.inspection_id = None
    notification.message = "Report pending"
    notification.is_read = False

    record = Mock(spec=ClassroomObservation)
    record.report.status = "PENDING"

    db = Mock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        notification
    ]
    db.get.return_value = record

    monkeypatch.setattr(
        router,
        "_can_view_record",
        lambda record, user, session: False,
    )

    result = router.pending_notifications(current_user, db)

    assert result == []
