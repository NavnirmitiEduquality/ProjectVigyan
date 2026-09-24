from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image

from app.services.photo.processing import (
    JPEG_CONTENT_TYPE,
    MAX_FILE_SIZE_BYTES,
    PhotoProcessingError,
    PhotoProcessingService,
)


@pytest.fixture
def service():
    return PhotoProcessingService()


def make_jpeg(
    *,
    width: int = 800,
    height: int = 600,
    quality: int = 85,
) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality)
    return output.getvalue()


def capture_time():
    return datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)


def valid_gps():
    return Decimal("19.076000"), Decimal("72.877700")


def test_valid_jpeg_is_processed(service):
    image_bytes = make_jpeg()
    latitude, longitude = valid_gps()

    result = service.process(
        image_bytes,
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    assert result.content_type == JPEG_CONTENT_TYPE
    assert result.file_size_bytes <= MAX_FILE_SIZE_BYTES
    assert result.file_size_bytes == len(result.image_bytes)
    assert result.width == 800
    assert result.height == 600
    assert result.latitude == latitude
    assert result.longitude == longitude


def test_png_is_rejected(service):
    image = Image.new("RGB", (800, 600), "white")
    output = BytesIO()
    image.save(output, format="PNG")

    latitude, longitude = valid_gps()

    with pytest.raises(PhotoProcessingError, match="Only JPEG"):
        service.process(
            output.getvalue(),
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )


def test_empty_file_is_rejected(service):
    latitude, longitude = valid_gps()

    with pytest.raises(PhotoProcessingError, match="empty"):
        service.process(
            b"",
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )


def test_corrupt_jpeg_is_rejected(service):
    latitude, longitude = valid_gps()

    with pytest.raises(
        PhotoProcessingError,
        match="valid JPEG",
    ):
        service.process(
            b"\xff\xd8\xff\x00corrupt",
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "latitude",
    [
        Decimal("-90.000001"),
        Decimal("90.000001"),
    ],
)
def test_invalid_latitude_is_rejected(service, latitude):
    _, longitude = valid_gps()

    with pytest.raises(PhotoProcessingError, match="Latitude"):
        service.process(
            make_jpeg(),
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "longitude",
    [
        Decimal("-180.000001"),
        Decimal("180.000001"),
    ],
)
def test_invalid_longitude_is_rejected(service, longitude):
    latitude, _ = valid_gps()

    with pytest.raises(PhotoProcessingError, match="Longitude"):
        service.process(
            make_jpeg(),
            captured_at=capture_time(),
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "latitude",
    [
        Decimal("-90"),
        Decimal("90"),
    ],
)
def test_boundary_latitudes_are_accepted(service, latitude):
    _, longitude = valid_gps()

    result = service.process(
        make_jpeg(),
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    assert result.latitude == latitude


@pytest.mark.parametrize(
    "longitude",
    [
        Decimal("-180"),
        Decimal("180"),
    ],
)
def test_boundary_longitudes_are_accepted(service, longitude):
    latitude, _ = valid_gps()

    result = service.process(
        make_jpeg(),
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    assert result.longitude == longitude


def test_processed_output_is_valid_jpeg(service):
    latitude, longitude = valid_gps()

    result = service.process(
        make_jpeg(),
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    with Image.open(BytesIO(result.image_bytes)) as image:
        assert image.format == "JPEG"
        assert image.size == (800, 600)


def test_large_photo_is_compressed_to_size_limit(service):
    # A large noisy image is more difficult to compress than a solid-color image.
    image = Image.effect_noise((3000, 3000), 100)
    output = BytesIO()
    image.save(output, format="JPEG", quality=100)

    original_size = len(output.getvalue())
    assert original_size > MAX_FILE_SIZE_BYTES

    latitude, longitude = valid_gps()

    result = service.process(
        output.getvalue(),
        captured_at=capture_time(),
        latitude=latitude,
        longitude=longitude,
    )

    assert result.file_size_bytes <= MAX_FILE_SIZE_BYTES
    assert result.file_size_bytes == len(result.image_bytes)
