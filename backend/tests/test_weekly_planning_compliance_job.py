
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import run_weekly_planning_compliance as job


def test_saturday_execution_date_maps_to_following_monday():
    saturday = date(2026, 11, 21)

    assert job.get_execution_date(saturday) == saturday
    assert job.get_target_week_start(saturday) == date(2026, 11, 23)


def test_execution_date_rejects_non_saturday():
    with pytest.raises(ValueError, match="must be a Saturday"):
        job.get_execution_date(date(2026, 11, 20))


def test_target_week_rejects_non_saturday():
    with pytest.raises(ValueError, match="must be a Saturday"):
        job.get_target_week_start(date(2026, 11, 20))


def test_dry_run_rolls_back_and_does_not_commit(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True

    notifications = [object(), object()]

    service = Mock()
    service.generate_weekly_noncompliance.return_value = notifications
    monkeypatch.setattr(
        job,
        "PlanningNotificationService",
        lambda: service,
    )

    result = job.run_compliance_job(
        db,
        execution_date=date(2026, 11, 21),
        dry_run=True,
    )

    assert result == 2
    service.generate_weekly_noncompliance.assert_called_once_with(
        db,
        week_start_date=date(2026, 11, 23),
    )
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_successful_job_commits(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True

    service = Mock()
    service.generate_weekly_noncompliance.return_value = [object()]
    monkeypatch.setattr(
        job,
        "PlanningNotificationService",
        lambda: service,
    )

    result = job.run_compliance_job(
        db,
        execution_date=date(2026, 11, 21),
    )

    assert result == 1
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_job_skips_when_advisory_lock_is_unavailable(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = False

    service = Mock()
    monkeypatch.setattr(
        job,
        "PlanningNotificationService",
        lambda: service,
    )

    result = job.run_compliance_job(
        db,
        execution_date=date(2026, 11, 21),
    )

    assert result == 0
    service.generate_weekly_noncompliance.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_job_rolls_back_and_reraises_service_exception(monkeypatch):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = True

    service = Mock()
    service.generate_weekly_noncompliance.side_effect = RuntimeError(
        "simulated service failure"
    )
    monkeypatch.setattr(
        job,
        "PlanningNotificationService",
        lambda: service,
    )

    with pytest.raises(RuntimeError, match="simulated service failure"):
        job.run_compliance_job(
            db,
            execution_date=date(2026, 11, 21),
        )

    db.commit.assert_not_called()
    db.rollback.assert_called_once()
