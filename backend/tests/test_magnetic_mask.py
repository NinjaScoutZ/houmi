import cv2
import numpy as np
import pytest
from app.services.mask.magnetic_mask import apply_magnetic_line_fill


def test_magnetic_line_fill_bridges_horizontal_gaps():
    """Verify that gaps between words on the same horizontal line are bridged into a solid stripe."""
    img = np.full((120, 160, 3), 255, dtype=np.uint8)
    # Draw an oval balloon border
    cv2.ellipse(img, (80, 60), (70, 50), 0, 0, 360, (0, 0, 0), 2)

    # Create raw glyph mask with gaps (like multi-word Korean text)
    raw_mask = np.zeros((120, 160), dtype=np.uint8)
    # Line 1: Word A (x=30..45) gap (x=45..55) Word B (x=55..70) gap (x=70..80) Word C (x=80..130) at y=20..35
    raw_mask[20:35, 30:45] = 255
    raw_mask[20:35, 55:70] = 255
    raw_mask[20:35, 80:130] = 255

    # Line 2: Word D (x=25..55) gap (x=55..65) Word E (x=65..135) at y=45..60
    raw_mask[45:60, 25:55] = 255
    raw_mask[45:60, 65:135] = 255

    # Check that in raw mask, gaps are 0
    assert raw_mask[25, 50] == 0
    assert raw_mask[50, 60] == 0

    # Apply magnetic line fill
    magnetic = apply_magnetic_line_fill(raw_mask, image_bgr=img)

    # Gaps between words on the same line must now be filled (255)
    assert magnetic[25, 50] == 255
    assert magnetic[50, 60] == 255

    # Vertical space between Line 1 and Line 2 (y=38..42) must NOT be filled together
    assert magnetic[40, 80] == 0

    # Balloon border (at x=80, y=10) must remain protected (0)
    assert magnetic[10, 80] == 0


def test_magnetic_line_fill_empty_mask():
    """Verify safe handling of empty or None masks."""
    empty = np.zeros((50, 50), dtype=np.uint8)
    result = apply_magnetic_line_fill(empty)
    assert result is not None
    assert np.count_nonzero(result) == 0

    none_res = apply_magnetic_line_fill(None)
    assert none_res is None


def test_magnetic_line_fill_single_word():
    """Verify single word retains its mask without errors."""
    mask = np.zeros((60, 60), dtype=np.uint8)
    mask[20:40, 20:40] = 255
    res = apply_magnetic_line_fill(mask)
    assert np.count_nonzero(res[20:40, 20:40]) == 20 * 20
