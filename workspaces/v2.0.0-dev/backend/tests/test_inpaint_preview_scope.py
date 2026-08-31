from types import SimpleNamespace

import pytest

from app.services.inpainter import _select_inpaint_preview_blocks


def _block(block_id: str, x: float, y: float, width: float, height: float):
    return SimpleNamespace(id=block_id, x=x, y=y, width=width, height=height)


def test_block_preview_isolates_selected_block_and_clamps_crop():
    selected = _block("selected", -5, 10, 30, 40)
    other = _block("other", 50, 60, 20, 20)
    page = SimpleNamespace(text_blocks=[selected, other])

    blocks, bounds = _select_inpaint_preview_blocks(page, "selected", 100, 100)

    assert blocks == [selected]
    # Bounds are now padded to match the Mask Editor's padded crop view
    # pad = max(30, int(max(30, 40) * 0.15)) = 30
    # px0=max(0,-5-30)=0, py0=max(0,10-30)=0, px1=min(100,-5+30+30)=55, py1=min(100,10+40+30)=80
    assert bounds == (0, 0, 55, 80)


def test_page_preview_keeps_all_blocks_and_has_no_crop():
    blocks = [_block("one", 0, 0, 10, 10), _block("two", 20, 20, 10, 10)]
    selected, bounds = _select_inpaint_preview_blocks(
        SimpleNamespace(text_blocks=blocks), None, 100, 100
    )

    assert selected == blocks
    assert bounds is None


def test_block_preview_rejects_foreign_block():
    page = SimpleNamespace(text_blocks=[_block("one", 0, 0, 10, 10)])

    with pytest.raises(ValueError, match="does not belong"):
        _select_inpaint_preview_blocks(page, "foreign", 100, 100)
