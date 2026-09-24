from __future__ import annotations

from abc import ABC, abstractmethod


class PhotoStorage(ABC):
    """Abstract interface for private photo storage."""

    @abstractmethod
    def save(self, image_bytes: bytes, *, extension: str = ".jpg") -> str:
        """Save photo bytes and return a private storage key."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Delete a stored photo."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Return whether a stored photo exists."""
        raise NotImplementedError
