import pytest
from PIL import Image, ImageDraw
from app.services.renderer import _apply_synthetic_italic, _apply_drop_shadow

def test_synthetic_italic_transform():
    # Create test RGBA text image
    img = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 10, 70, 40], fill=(255, 0, 0, 255))

    italic_img = _apply_synthetic_italic(img, angle_degrees=12.0)
    assert italic_img.size == (100, 50)
    assert italic_img.mode == "RGBA"

def test_drop_shadow_composite():
    class DummyDropShadowSpec:
        enabled = True
        size = 8.0
        opacity = 0.8
        distance = 6.0
        angle_deg = 120.0
        color = "#000000"

    img = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 20, 80, 40], fill=(255, 255, 255, 255))

    shadow_img = _apply_drop_shadow(img, DummyDropShadowSpec())
    assert shadow_img.size == (120, 60)
    # Check that shadow layer has alpha values behind the white rectangle
    alpha = shadow_img.getchannel("A")
    assert alpha.getpixel((35, 25)) > 0
