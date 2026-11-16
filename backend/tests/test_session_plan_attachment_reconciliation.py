
from datetime import datetime, timedelta, timezone
import os

import pytest

from app.services.session_plan.attachment_reconciliation import (
    build_attachment_reconciliation_report,
)
from app.services.session_plan.attachment_storage import (
    SessionPlanAttachmentStorage,
)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, storage_keys):
        self.storage_keys = storage_keys

    def query(self, *args, **kwargs):
        return FakeQuery([(key,) for key in self.storage_keys])


@pytest.fixture
def storage(tmp_path):
    return SessionPlanAttachmentStorage(
        root=tmp_path / "attachments"
    )


@pytest.fixture
def fixed_now():
    return datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc)


def make_storage_key():
    return "A" * 43 + ".pdf"


def create_file(storage, filename, content=b"test"):
    path = storage.root / filename
    path.write_bytes(content)
    return path


def set_file_age(path, age, now):
    modified_at = (now - age).timestamp()
    os.utime(path, (modified_at, modified_at))


def test_referenced_attachment_is_not_orphan(
    storage,
    fixed_now,
):
    key = make_storage_key()
    create_file(storage, key)

    db = FakeDB([key])

    report = build_attachment_reconciliation_report(
        db,
        storage=storage,
        now=fixed_now,
    )

    assert report.scanned_files == 1
    assert report.referenced_files == 1
    assert report.orphan_candidates == ()
    assert report.missing_files == ()


def test_old_unreferenced_file_is_reported_as_orphan(
    storage,
    fixed_now,
):
    key = make_storage_key()
    path = create_file(storage, key)
    set_file_age(path, timedelta(hours=48), fixed_now)

    db = FakeDB([])

    report = build_attachment_reconciliation_report(
        db,
        storage=storage,
        now=fixed_now,
    )

    assert len(report.orphan_candidates) == 1

    candidate = report.orphan_candidates[0]

    assert candidate.storage_key == key
    assert candidate.file_size_bytes == 4

    # Report-only: physical file must remain untouched.
    assert path.is_file()


def test_recent_unreferenced_file_is_ignored(
    storage,
    fixed_now,
):
    key = make_storage_key()
    path = create_file(storage, key)
    set_file_age(path, timedelta(hours=2), fixed_now)

    report = build_attachment_reconciliation_report(
        FakeDB([]),
        storage=storage,
        now=fixed_now,
    )

    assert report.orphan_candidates == ()
    assert report.ignored_files == 1
    assert path.is_file()


def test_invalid_storage_filename_is_ignored(
    storage,
    fixed_now,
):
    path = create_file(
        storage,
        "unrelated-report.pdf",
    )

    report = build_attachment_reconciliation_report(
        FakeDB([]),
        storage=storage,
        now=fixed_now,
    )

    assert report.scanned_files == 0
    assert report.orphan_candidates == ()
    assert report.ignored_files == 1
    assert path.is_file()


def test_missing_physical_file_is_reported(
    storage,
    fixed_now,
):
    missing_key = make_storage_key()

    report = build_attachment_reconciliation_report(
        FakeDB([missing_key]),
        storage=storage,
        now=fixed_now,
    )

    assert report.referenced_files == 1
    assert report.missing_files == (missing_key,)


def test_reconciliation_does_not_delete_orphan_files(
    storage,
    fixed_now,
):
    key = make_storage_key()
    path = create_file(storage, key)
    set_file_age(path, timedelta(days=2), fixed_now)

    report = build_attachment_reconciliation_report(
        FakeDB([]),
        storage=storage,
        now=fixed_now,
    )

    assert len(report.orphan_candidates) == 1
    assert path.exists()
    assert path.read_bytes() == b"test"


def test_negative_grace_period_is_rejected(
    storage,
    fixed_now,
):
    with pytest.raises(ValueError):
        build_attachment_reconciliation_report(
            FakeDB([]),
            storage=storage,
            grace_period=timedelta(hours=-1),
            now=fixed_now,
        )


def test_naive_current_time_is_rejected(storage):
    with pytest.raises(ValueError):
        build_attachment_reconciliation_report(
            FakeDB([]),
            storage=storage,
            now=datetime(2026, 11, 14, 10, 0),
        )
