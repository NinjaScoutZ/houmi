import io
import pytest
from PIL import Image
from app.services.image_guard import validate_and_sanitize_image, clamp_crop_box, ImageGuardError

def test_valid_image_sanitization():
    # Create test in-memory PNG
    img = Image.new("RGB", (200, 300), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    sanitized, meta = validate_and_sanitize_image(buf.getvalue(), max_dimension=1000)
    assert sanitized.size == (200, 300)
    assert meta["downscaled"] is False

def test_ultra_large_image_auto_downscaled():
    img = Image.new("RGB", (8000, 4000), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    sanitized, meta = validate_and_sanitize_image(buf.getvalue(), max_dimension=2000)
    assert sanitized.width <= 2000
    assert meta["downscaled"] is True

def test_corrupted_image_raises_guard_error():
    corrupted = b"NOT_A_VALID_IMAGE_DATA_HEADER"
    with pytest.raises(ImageGuardError):
        validate_and_sanitize_image(corrupted)

def test_clamp_crop_box():
    # Box exceeding boundaries
    box = (-10, -5, 500, 600)
    clamped = clamp_crop_box(box, img_width=100, img_height=200)
    assert clamped[0] == 0
    assert clamped[1] == 0
    assert clamped[2] == 100
    assert clamped[3] == 200
