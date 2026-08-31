import cv2
import numpy as np
import pytest
from app.services.inpainter import get_automatic_block_mask
from app.services.text_mask import generate_high_quality_text_mask


class DummyBlock:
    def __init__(self, x: float, y: float, width: float, height: float, balloon_type: str = "shout", extra_metadata: dict | None = None):
        self.id = "block_scream_test"
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.balloon_type = balloon_type
        self.extra_metadata = extra_metadata or {}


def test_spiky_scream_balloon_mask_containment_without_smart_balloon():
    """
    Tests that a spiky scream balloon (white interior with dense black radiating spikes)
    when processed with Smart Balloon OFF:
    1. Fully masks the text inside the detector text box.
    2. Does NOT leak mask pixels onto the radiating black spikes outside the text box.
    """
    # Create image: 500x500 canvas
    img = np.full((500, 500, 3), 200, dtype=np.uint8)

    # Central white balloon area (radius 120)
    cv2.circle(img, (250, 250), 120, (255, 255, 255), -1)

    # Draw dense black radiating spikes extending out to r=190
    spike_pixels_mask = np.zeros((500, 500), dtype=np.uint8)
    for angle_deg in range(0, 360, 6):
        rad = np.deg2rad(angle_deg)
        r_inner = 110
        r_outer = 175 + (angle_deg % 18)
        x0 = int(250 + r_inner * np.cos(rad))
        y0 = int(250 + r_inner * np.sin(rad))
        x1 = int(250 + r_outer * np.cos(rad))
        y1 = int(250 + r_outer * np.sin(rad))
        cv2.line(img, (x0, y0), (x1, y1), (0, 0, 0), 3)
        cv2.line(spike_pixels_mask, (x0, y0), (x1, y1), 255, 3)

    # Text inside central box: (200, 230) to (300, 270)
    cv2.putText(img, "TEST TEXT", (205, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)

    # Detector text box
    block = DummyBlock(x=200, y=230, width=100, height=40, balloon_type="shout")

    # Generate automatic block mask
    mask = get_automatic_block_mask(img, block, settings={"enable_smart_balloon": False})

    # 1. Text area must have non-empty mask
    text_crop_mask = mask[230:270, 200:300]
    assert np.count_nonzero(text_crop_mask) > 50

    # 2. Spikes outside the text box + 6px margin must have ZERO mask
    permitted_box = np.zeros((500, 500), dtype=bool)
    permitted_box[224:276, 194:306] = True

    outer_spikes = (spike_pixels_mask > 0) & (~permitted_box)
    spike_leak_count = np.count_nonzero(mask[outer_spikes])
    assert spike_leak_count == 0, f"Mask leaked onto {spike_leak_count} outer spike pixels!"


def test_mixed_color_text_mask_preserves_black_and_colored_words():
    """
    Tests that a text line containing both bold black text ("I CAN'T")
    and reddish-brown text ("MOVE... NOISE") captures BOTH words in the mask.
    """
    # Create white canvas 200x400
    img = np.full((120, 360, 3), 250, dtype=np.uint8)

    # Bold black text on the left
    cv2.putText(img, "I CAN'T", (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 10), 3)

    # Reddish-brown text on the right
    cv2.putText(img, "MOVE... NOISE", (140, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (40, 40, 180), 2)

    mask, regions, warnings = generate_high_quality_text_mask(img, dilation_kernel=2)

    # Check mask presence on left (black text) and right (colored text)
    left_mask = mask[:, 10:130]
    right_mask = mask[:, 135:350]

    assert np.count_nonzero(left_mask) > 100, "Bold black text 'I CAN'T' was dropped from the mask!"
    assert np.count_nonzero(right_mask) > 100, "Colored text 'MOVE... NOISE' was dropped from the mask!"


def test_outlined_text_dual_contrast_preserves_stroke_and_core():
    """
    Tests that text with a dark black core and a thick white stroke/outline on a midtone skin background
    captures BOTH the inner black core and the outer white stroke into the text mask.
    """
    # Create skin-tone image 120x320
    img = np.full((120, 320, 3), (160, 180, 220), dtype=np.uint8)

    # Allowed text area
    allowed = np.zeros((120, 320), dtype=np.uint8)
    allowed[20:90, 20:300] = 255

    # Draw white outer stroke (intensity > 230)
    img[35:75, 40:280] = (245, 245, 245)
    # Draw black core inside (intensity < 30)
    img[45:65, 55:265] = (15, 15, 15)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    from app.services.text_mask import _refine_line_mask
    mask, _ = _refine_line_mask(gray, allowed, dilation_kernel=1, color_crop=img)

    # Verify that white stroke pixels are masked
    white_stroke_mask = mask[36:44, 42:278]
    assert np.count_nonzero(white_stroke_mask) > 100, "White outer stroke was missed in dual-contrast outlined text!"

    # Verify that black core pixels are masked
    black_core_mask = mask[46:64, 56:264]
    assert np.count_nonzero(black_core_mask) > 100, "Black text core was missed in dual-contrast outlined text!"

