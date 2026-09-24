from __future__ import annotations

import secrets
from pathlib import Path

from app.services.photo.storage.base import PhotoStorage


class LocalPrivatePhotoStorage(PhotoStorage):
    """Private filesystem-backed photo storage for development."""

    def __init__(self, root_directory: Path) -> None:
        self.root_directory = root_directory
        self.root_directory.mkdir(parents=True, exist_ok=True)

    def save(self, image_bytes: bytes, *, extension: str = ".jpg") -> str:
        if not image_bytes:
            raise ValueError("Cannot store empty photo.")

        if extension != ".jpg":
            raise ValueError("Only .jpg photos are supported.")

        filename = f"{secrets.token_urlsafe(32)}{extension}"
        storage_key = filename

        destination = self._resolve_safe_path(storage_key)

        destination.write_bytes(image_bytes)

        return storage_key

    def delete(self, storage_key: str) -> None:
        path = self._resolve_safe_path(storage_key)

        if path.exists():
            path.unlink()

    def exists(self, storage_key: str) -> bool:
        path = self._resolve_safe_path(storage_key)
        return path.is_file()

    def _resolve_safe_path(self, storage_key: str) -> Path:
        if not storage_key:
            raise ValueError("Storage key cannot be empty.")

        candidate = (self.root_directory / storage_key).resolve()
        root = self.root_directory.resolve()

        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("Invalid storage key.") from exc

        return candidate
