import numpy as np
import cv2
import pytest
from app.services.text_mask import (
    generate_monochrome_flat_text_mask,
    generate_routed_text_mask,
)
from app.services.inpainter import _clip_auto_mask_to_balloon


def create_synthetic_spiky_balloon_dark_bg(width=300, height=200):
    """
    Creates a synthetic image with dark manga panel background (60%),
    a white speech balloon (40%), and black text inside.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8) # Dark background (0,0,0)
    
    # White balloon interior (centered)
    bx0, by0, bx1, by1 = 40, 30, 260, 170
    cv2.rectangle(img, (bx0, by0), (bx1, by1), (255, 255, 255), -1)
    
    # Black text inside balloon
    cv2.putText(
        img,
        "TEXT",
        (80, 110),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )
    return img, (bx0, by0, bx1, by1)


def test_monochrome_flat_mask_on_dark_background_crop():
    """
    Tests that a crop where dark background covers > 50% does NOT cause
    polarity inversion and does NOT drop the text mask to 0.
    """
    img, _ = create_synthetic_spiky_balloon_dark_bg()
    
    mask = generate_monochrome_flat_text_mask(img, dilation_kernel=3)
    
    # Text mask must be detected and non-zero
    mask_pixels = np.count_nonzero(mask)
    assert mask_pixels > 50, f"Expected text mask to be detected, but got {mask_pixels} pixels (empty mask)"
    
    # Mask must NOT cover the white balloon interior or black background completely
    total_pixels = img.shape[0] * img.shape[1]
    coverage = mask_pixels / total_pixels
    assert coverage < 0.25, f"Mask coverage {coverage:.2f} is too large (likely whole balloon was masked)"


def test_mask_does_not_overflow_balloon_border():
    """
    Tests that dilated text mask does not spill over the balloon's black outer border.
    """
    H, W = 200, 200
    img = np.full((H, W, 3), 200, dtype=np.uint8) # Outside artwork
    
    # Draw black balloon stroke (thickness 8)
    cv2.circle(img, (100, 100), 70, (0, 0, 0), 8)
    # Fill interior with white
    cv2.circle(img, (100, 100), 62, (255, 255, 255), -1)
    
    # Draw black text very close to the right inner border (at x=145)
    cv2.putText(img, "!", (140, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)
    
    # Balloon interior mask (ground truth barrier)
    interior_barrier = np.zeros((H, W), dtype=np.uint8)
    cv2.circle(interior_barrier, (100, 100), 62, 255, -1)
    
    # Generate mask with heavy dilation (dilation_kernel = 5)
    mask = generate_monochrome_flat_text_mask(img, dilation_kernel=5)
    
    # The mask must NOT leak into the area outside the balloon interior
    leak_pixels = np.count_nonzero(cv2.bitwise_and(mask, cv2.bitwise_not(interior_barrier)))
    assert leak_pixels == 0, f"Mask leaked {leak_pixels} pixels outside the balloon interior border"


def test_clip_auto_mask_to_balloon_does_not_erase_spiky_corners():
    """
    Tests that _clip_auto_mask_to_balloon does not erase text placed in corners
    of rectangular or spiky balloons by applying a rigid ellipse.
    """
    class MockBlock:
        x = 20.0
        y = 20.0
        width = 160.0
        height = 160.0
        balloon_type = "shout" # spiky / shout balloon
        extra_metadata = {
            "layout_region": {
                "x": 10,
                "y": 10,
                "width": 180,
                "height": 180,
                "shape": "shout",
                "source": "smart_balloon",
            }
        }
    
    block = MockBlock()
    H, W = 200, 200
    
    # Mask with text in the corner (x=30, y=30)
    input_mask = np.zeros((H, W), dtype=np.uint8)
    cv2.circle(input_mask, (30, 30), 10, 255, -1)
    
    output_mask = _clip_auto_mask_to_balloon(block, input_mask, W, H)
    
    # Corner text should NOT be clipped to 0
    assert np.count_nonzero(output_mask) > 0, "Text in balloon corner was improperly clipped by ellipse"
