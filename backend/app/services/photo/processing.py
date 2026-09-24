from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAX_FILE_SIZE_BYTES = 1_048_576
JPEG_CONTENT_TYPE = "image/jpeg"

MIN_LATITUDE = Decimal("-90")
MAX_LATITUDE = Decimal("90")
MIN_LONGITUDE = Decimal("-180")
MAX_LONGITUDE = Decimal("180")

# Start with a conservative quality and reduce it only when necessary.
INITIAL_JPEG_QUALITY = 85
MIN_JPEG_QUALITY = 40
JPEG_QUALITY_STEP = 5


class PhotoProcessingError(ValueError):
    """Raised when a photo fails processing or validation."""


@dataclass(frozen=True)
class ProcessedPhoto:
    image_bytes: bytes
    content_type: str
    file_size_bytes: int
    width: int
    height: int
    captured_at: datetime
    latitude: Decimal
    longitude: Decimal


class PhotoProcessingService:
    """Validate and normalize uploaded project photos."""

    def process(
        self,
        image_bytes: bytes,
        *,
        captured_at: datetime,
        latitude: Decimal,
        longitude: Decimal,
    ) -> ProcessedPhoto:
        self._validate_gps(latitude, longitude)

        if not image_bytes:
            raise PhotoProcessingError("Photo file is empty.")

        image = self._open_jpeg(image_bytes)

        normalized_image = self._normalize_image(image)

        processed_bytes = self._compress_to_limit(normalized_image)

        with Image.open(BytesIO(processed_bytes)) as processed_image:
            width, height = processed_image.size
        return ProcessedPhoto(
            image_bytes=processed_bytes,
            content_type=JPEG_CONTENT_TYPE,
            file_size_bytes=len(processed_bytes),
            width=width,
            height=height,
            captured_at=captured_at,
            latitude=latitude,
            longitude=longitude,
        )

    @staticmethod
    def _validate_gps(
        latitude: Decimal,
        longitude: Decimal,
    ) -> None:
        try:
            latitude = Decimal(str(latitude))
            longitude = Decimal(str(longitude))
        except Exception as exc:
            raise PhotoProcessingError(
                "Latitude and longitude must be valid numbers."
            ) from exc

        if not MIN_LATITUDE <= latitude <= MAX_LATITUDE:
            raise PhotoProcessingError(
                "Latitude must be between -90 and 90."
            )

        if not MIN_LONGITUDE <= longitude <= MAX_LONGITUDE:
            raise PhotoProcessingError(
                "Longitude must be between -180 and 180."
            )

    @staticmethod
    def _open_jpeg(image_bytes: bytes) -> Image.Image:
        try:
            image = Image.open(BytesIO(image_bytes))

            if image.format != "JPEG":
                raise PhotoProcessingError(
                    "Only JPEG photos are accepted."
                )

            image.verify()

            # Re-open after verify because verify() invalidates the image.
            image = Image.open(BytesIO(image_bytes))
            image.load()

            return image

        except PhotoProcessingError:
            raise
        except (UnidentifiedImageError, OSError) as exc:
            raise PhotoProcessingError(
                "The uploaded file is not a valid JPEG image."
            ) from exc

    @staticmethod
    def _normalize_image(image: Image.Image) -> Image.Image:
        # JPEG does not support transparency. Convert unusual modes safely.
        if image.mode not in ("RGB", "L"):
            return image.convert("RGB")

        return image.copy()

    @staticmethod
    def _compress_to_limit(image: Image.Image) -> bytes:
        current_image = image

        while True:
            for quality in range(
                INITIAL_JPEG_QUALITY,
                MIN_JPEG_QUALITY - 1,
                -JPEG_QUALITY_STEP,
            ):
                output = BytesIO()

                current_image.save(
                    output,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                )

                result = output.getvalue()

                if len(result) <= MAX_FILE_SIZE_BYTES:
                    return result

            width, height = current_image.size

            # Reduce dimensions by 20% and try compression again.
            new_width = max(1, int(width * 0.8))
            new_height = max(1, int(height * 0.8))

            # Nothing more can reasonably be reduced.
            if new_width == width and new_height == height:
                raise PhotoProcessingError(
                    "Photo cannot be compressed to 1 MB or less."
                )

            current_image = current_image.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS,
            )
