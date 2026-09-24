from pathlib import Path

import pytest

from app.services.photo.storage import (
    LocalPrivatePhotoStorage,
    PhotoStorage,
)


@pytest.fixture
def storage(tmp_path: Path) -> LocalPrivatePhotoStorage:
    return LocalPrivatePhotoStorage(tmp_path / "photos")


def test_local_storage_implements_photo_storage(storage):
    assert isinstance(storage, PhotoStorage)


def test_save_stores_photo_and_returns_private_key(storage):
    image_bytes = b"fake-jpeg-data"

    storage_key = storage.save(image_bytes)

    assert storage_key
    assert storage_key.endswith(".jpg")
    assert "/" not in storage_key
    assert "\\" not in storage_key
    assert storage.exists(storage_key)


def test_saved_file_contains_exact_bytes(storage):
    image_bytes = b"fake-jpeg-data"

    storage_key = storage.save(image_bytes)

    stored_path = storage.root_directory / storage_key

    assert stored_path.read_bytes() == image_bytes


def test_original_filename_is_not_used(storage):
    image_bytes = b"fake-jpeg-data"

    storage_key = storage.save(
        image_bytes,
        extension=".jpg",
    )

    assert "fake" not in storage_key
    assert "jpeg" not in storage_key


def test_each_save_generates_different_key(storage):
    image_bytes = b"fake-jpeg-data"

    first_key = storage.save(image_bytes)
    second_key = storage.save(image_bytes)

    assert first_key != second_key


def test_exists_returns_false_for_missing_photo(storage):
    assert storage.exists("does-not-exist.jpg") is False


def test_delete_removes_photo(storage):
    storage_key = storage.save(b"fake-jpeg-data")

    assert storage.exists(storage_key)

    storage.delete(storage_key)

    assert storage.exists(storage_key) is False


def test_delete_missing_photo_is_safe(storage):
    storage.delete("does-not-exist.jpg")


def test_empty_photo_is_rejected(storage):
    with pytest.raises(ValueError, match="empty"):
        storage.save(b"")


def test_only_jpg_extension_is_allowed(storage):
    with pytest.raises(ValueError, match="Only .jpg"):
        storage.save(
            b"fake-jpeg-data",
            extension=".png",
        )


def test_path_traversal_is_rejected(storage):
    with pytest.raises(ValueError, match="Invalid storage key"):
        storage.exists("../../outside.jpg")


def test_path_traversal_is_rejected_for_delete(storage):
    with pytest.raises(ValueError, match="Invalid storage key"):
        storage.delete("../../outside.jpg")


def test_storage_directory_is_private_filesystem_path(storage):
    storage_key = storage.save(b"fake-jpeg-data")

    stored_path = storage.root_directory / storage_key

    assert stored_path.is_file()
    assert stored_path.parent == storage.root_directory
