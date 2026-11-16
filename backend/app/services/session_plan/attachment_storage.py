
from __future__ import annotations

import io
import secrets
import zipfile
from pathlib import Path
from typing import BinaryIO

import olefile
from PIL import Image, UnidentifiedImageError


MAX_ATTACHMENT_SIZE_BYTES = 5 * 1_048_576
MAX_ARCHIVE_MEMBERS = 500
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 25 * 1_048_576
MAX_ARCHIVE_MEMBER_BYTES = 10 * 1_048_576

_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")

_ALLOWED_FORMATS = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class AttachmentValidationError(ValueError):
    """Raised when an attachment is invalid or unsupported."""


def _validate_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise AttachmentValidationError("Invalid PDF structure.")


def _validate_image(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise AttachmentValidationError("Unsupported image format.")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise AttachmentValidationError("Invalid image file.") from exc


def _validate_ooxml(data: bytes, extension: str) -> None:
    required_entries = {
        ".docx": {
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
        },
        ".pptx": {
            "[Content_Types].xml",
            "_rels/.rels",
            "ppt/presentation.xml",
        },
    }[extension]

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]

            if len(entries) > MAX_ARCHIVE_MEMBERS:
                raise AttachmentValidationError("Office package contains too many files.")

            if len(names) != len(set(names)):
                raise AttachmentValidationError("Office package contains duplicate entries.")

            if not required_entries.issubset(set(names)):
                raise AttachmentValidationError("Invalid Office document package.")

            total_uncompressed = 0

            for entry in entries:
                if entry.flag_bits & 0x1:
                    raise AttachmentValidationError("Encrypted Office packages are not supported.")

                if entry.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise AttachmentValidationError("Office package member is too large.")

                total_uncompressed += entry.file_size

                if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise AttachmentValidationError("Office package is too large.")

                if entry.filename.startswith("/") or ".." in Path(entry.filename).parts:
                    raise AttachmentValidationError("Unsafe Office package entry.")

            # Read every member to detect corrupt compressed data and CRC errors.
            for entry in entries:
                with archive.open(entry) as member:
                    while member.read(64 * 1024):
                        pass

            content_types = archive.read("[Content_Types].xml")

            expected_type = (
                b"wordprocessingml.document.main+xml"
                if extension == ".docx"
                else b"presentationml.presentation.main+xml"
            )

            if expected_type not in content_types:
                raise AttachmentValidationError("Office package type does not match its extension.")

    except (zipfile.BadZipFile, RuntimeError, OSError, KeyError) as exc:
        if isinstance(exc, AttachmentValidationError):
            raise
        raise AttachmentValidationError("Invalid Office package.") from exc


def _validate_ole(data: bytes, extension: str) -> None:
    if not data.startswith(_OLE_SIGNATURE):
        raise AttachmentValidationError("Invalid Office document signature.")

    try:
        with olefile.OleFileIO(io.BytesIO(data)) as compound_file:
            streams = {
                "/".join(parts).lower()
                for parts in compound_file.listdir(streams=True, storages=False)
            }

            if extension == ".doc":
                valid = (
                    "worddocument" in streams
                    and any(name.endswith("table") for name in streams)
                )
            else:
                valid = "powerpoint document" in streams

            if not valid:
                raise AttachmentValidationError(
                    "OLE file does not contain the expected Office document streams."
                )

    except AttachmentValidationError:
        raise
    except Exception as exc:
        raise AttachmentValidationError("Invalid OLE Office document.") from exc


class SessionPlanAttachmentStorage:
    """Private filesystem storage for session-plan attachments."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (
            root or Path("storage") / "session_plan_attachments"
        ).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate(
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str]:
        if not filename or not filename.strip():
            raise AttachmentValidationError("A filename is required.")

        # Reject path components rather than trusting the supplied filename.
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            raise AttachmentValidationError("Invalid filename.")

        suffix = Path(filename).suffix.lower()

        if suffix not in _ALLOWED_FORMATS:
            raise AttachmentValidationError("Unsupported attachment format.")

        if not data:
            raise AttachmentValidationError("Attachment cannot be empty.")

        if len(data) > MAX_ATTACHMENT_SIZE_BYTES:
            raise AttachmentValidationError("Attachment exceeds the 5 MiB limit.")

        expected_type = _ALLOWED_FORMATS[suffix]

        if content_type != expected_type:
            raise AttachmentValidationError(
                "Attachment content type does not match its extension."
            )

        if suffix == ".pdf":
            _validate_pdf(data)
        elif suffix in {".docx", ".pptx"}:
            _validate_ooxml(data, suffix)
        elif suffix in {".doc", ".ppt"}:
            _validate_ole(data, suffix)
        elif suffix in {".jpg", ".jpeg", ".png"}:
            _validate_image(data)

        return suffix, expected_type

    def _resolve(self, storage_key: str) -> Path:
        if (
            not storage_key
            or Path(storage_key).name != storage_key
            or "/" in storage_key
            or "\\" in storage_key
        ):
            raise AttachmentValidationError("Invalid attachment storage key.")

        path = (self.root / storage_key).resolve()

        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise AttachmentValidationError("Invalid attachment storage key.") from exc

        return path

    def save(
        self,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> str:
        extension, _ = self.validate(filename, content_type, data)

        storage_key = f"{secrets.token_urlsafe(32)}{extension}"
        destination = self._resolve(storage_key)

        try:
            with destination.open("xb") as stored_file:
                stored_file.write(data)
        except FileExistsError as exc:
            raise AttachmentValidationError("Storage key collision.") from exc

        return storage_key

    def open(self, storage_key: str) -> BinaryIO:
        return self._resolve(storage_key).open("rb")

    def delete(self, storage_key: str) -> None:
        path = self._resolve(storage_key)

        if path.is_file():
            path.unlink()
