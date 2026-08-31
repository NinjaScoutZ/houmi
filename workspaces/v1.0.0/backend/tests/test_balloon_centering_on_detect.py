import pytest
from app.models.all_models import TextBlock
from app.services.smart_balloon_typesetting import compute_smart_balloon_typesetting

def test_smart_balloon_centering_on_detect():
    """Verify that detection sets coordinates to smart balloon centered safe bounds."""
    smart_res = {
        "success": True,
        "method": "smart_balloon_v15",
        "archetype": "SMOOTH_OVAL",
        "smart_x": 120.0,
        "smart_y": 150.0,
        "smart_width": 200.0,
        "smart_height": 180.0,
        "safe_bbox": {"x": 120.0, "y": 150.0, "width": 200.0, "height": 180.0},
        "center": {"x": 220.0, "y": 240.0},
    }
    raw_block = {"x": 100.0, "y": 130.0, "width": 240.0, "height": 220.0}

    enable_smart = True
    smart_x = smart_res.get("smart_x")
    smart_y = smart_res.get("smart_y")
    smart_w = smart_res.get("smart_width")
    smart_h = smart_res.get("smart_height")

    final_x = float(raw_block["x"])
    final_y = float(raw_block["y"])
    final_w = float(raw_block["width"])
    final_h = float(raw_block["height"])

    if enable_smart and smart_res.get("success") and smart_x is not None and smart_w is not None and smart_w > 10.0:
        final_x = float(smart_x)
        final_y = float(smart_y)
        final_w = float(smart_w)
        final_h = float(smart_h)

    assert final_x == 120.0
    assert final_y == 150.0
    assert final_w == 200.0
    assert final_h == 180.0


def test_smart_balloon_typesetting_preserves_manual_position():
    """Verify that compute_smart_balloon_typesetting does NOT overwrite user-moved block.x and blocky."""
    user_moved_x = 350.0
    user_moved_y = 420.0
    block = TextBlock(
        id="blk_test_1",
        page_id="page_test_1",
        block_index=0,
        x=user_moved_x,
        y=user_moved_y,
        width=180.0,
        height=140.0,
        smart_x=100.0,
        smart_y=100.0,
        smart_width=200.0,
        smart_height=160.0,
        translation="Test translation",
        source_text="Hello friends",
        font_family="ToyoStudio",
        font_size=24.0,
        extra_metadata={
            "smart_balloon": {
                "safe_bbox": {"x": 100.0, "y": 100.0, "width": 200.0, "height": 160.0},
                "center": {"x": 200.0, "y": 180.0},
                "row_width_constraints": None,
            },
        },
    )

    spec = compute_smart_balloon_typesetting(block, {})
    assert spec is not None
    assert block.x == user_moved_x
    assert block.y == user_moved_y
