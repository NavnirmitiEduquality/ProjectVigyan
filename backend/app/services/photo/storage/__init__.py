from app.services.photo.storage.base import PhotoStorage
from app.services.photo.storage.local import LocalPrivatePhotoStorage

__all__ = [
    "PhotoStorage",
    "LocalPrivatePhotoStorage",
]
