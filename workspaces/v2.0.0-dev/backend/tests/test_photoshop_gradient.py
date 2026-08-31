import pytest
from PIL import Image
from app.services.typesetting.schemas import GradientSpec, GradientStop
from app.services.typesetting.gradient import gradient_image


def test_all_gradient_types_render():
    for gtype in ["linear", "radial", "angle", "reflected", "diamond"]:
        spec = GradientSpec(
            enabled=True,
            type=gtype,
            stops=[GradientStop(position=0.0, color="#ff0000"), GradientStop(position=1.0, color="#0000ff")],
            angle_deg=45.0,
            scale=100.0,
            reverse=False,
        )
        img = gradient_image(100, 100, spec)
        assert isinstance(img, Image.Image)
        assert img.size == (100, 100)


def test_gradient_reverse_stops():
    spec = GradientSpec(
        enabled=True,
        type="linear",
        stops=[GradientStop(position=0.0, color="#ff0000"), GradientStop(position=1.0, color="#0000ff")],
        reverse=True,
    )
    img = gradient_image(50, 50, spec)
    assert isinstance(img, Image.Image)
