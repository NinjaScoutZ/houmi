import cv2
import numpy as np
import pytest

from app.services.mask.border_clamper import clamp_mask_to_balloon_interior
from app.services.text_mask import generate_adaptive_sfx_mask, generate_routed_text_mask
from app.services.inpainter import _clip_auto_mask_to_balloon


def create_synthetic_dark_spiky_balloon_with_outlined_text():
    """Generates a synthetic image resembling user uploaded Image 1:
    Dark grey background (L~45) with radial speedlines,
    and text with white outer stroke (RGB=255,255,255) and pink interior (RGB=250,150,150).
    """
    h, w = 160, 240
    # Dark grey background with radial texture
    img = np.ones((h, w, 3), dtype=np.uint8) * 45
    # Add subtle radial lines
    center = (w // 2, h // 2)
    for angle in range(0, 360, 15):
        rad = np.radians(angle)
        pt2 = (int(center[0] + 110 * np.cos(rad)), int(center[1] + 70 * np.sin(rad)))
        cv2.line(img, center, pt2, (60, 60, 60), 1)

    # Draw Korean/Asian glyphs or stylized text with thick white outline + pink fill
    # Line 1:
    cv2.putText(img, "TEXT LINE 1", (30, 60), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 6, cv2.LINE_AA)
    cv2.putText(img, "TEXT LINE 1", (30, 60), cv2.FONT_HERSHEY_DUPLEX, 0.9, (150, 150, 250), 2, cv2.LINE_AA)

    # Line 2:
    cv2.putText(img, "TEXT LINE 2", (40, 110), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 6, cv2.LINE_AA)
    cv2.putText(img, "TEXT LINE 2", (40, 110), cv2.FONT_HERSHEY_DUPLEX, 0.9, (150, 150, 250), 2, cv2.LINE_AA)

    return img


def test_dark_spiky_balloon_mask_generation():
    """Verify that the mask kernel generates non-empty, solid masks for white-outlined text on dark backgrounds."""
    crop = create_synthetic_dark_spiky_balloon_with_outlined_text()

    # Generate mask via adaptive routing / SFX
    mask = generate_adaptive_sfx_mask(crop, dilation_kernel=2)

    assert mask is not None
    assert np.any(mask), "Mask must not be empty on dark spiky balloons with white-outlined text"
    
    # Check that text locations have mask coverage
    assert mask[60, 60] == 255 or np.count_nonzero(mask[45:75, 25:180]) > 200
    assert mask[110, 70] == 255 or np.count_nonzero(mask[95:125, 35:190]) > 200

    # Ensure border clamper does NOT zero out this text mask
    clamped = clamp_mask_to_balloon_interior(mask, crop, margin_px=2)
    assert np.count_nonzero(clamped) >= np.count_nonzero(mask) * 0.85


def test_inpainter_clipping_preserves_dark_balloon_mask_and_removes_outliers():
    """Verify that _clip_auto_mask_to_balloon preserves text mask and discards distant outlier artifacts."""
    h, w = 200, 300
    full_img = np.ones((h, w, 3), dtype=np.uint8) * 45
    
    # Text block in center
    class DummyBlock:
        x = 50.0
        y = 50.0
        width = 200.0
        height = 100.0
        balloon_type = "shout"
        extra_metadata = {}

    block = DummyBlock()

    # Raw mask containing valid text mask + stray artifact at the top outside padding
    raw_mask = np.zeros((h, w), dtype=np.uint8)
    # Valid text mask inside core box
    cv2.rectangle(raw_mask, (70, 70), (230, 130), 255, -1)
    # Stray rectangular artifact at top (y=5..15) far away from text box
    cv2.rectangle(raw_mask, (60, 5), (240, 15), 255, -1)

    clipped = _clip_auto_mask_to_balloon(block, raw_mask, w, h, image=full_img, dilation_margin=4)

    # Core text mask must be preserved
    assert np.count_nonzero(clipped[60:140, 60:240]) > 0

    # Stray top artifact at y < 20 must be completely cleared
    assert np.count_nonzero(clipped[0:20, :]) == 0
