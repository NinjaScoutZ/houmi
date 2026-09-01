import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"E:\houmi\backend").resolve()))

import numpy as np
import cv2
import pytest
from unittest.mock import MagicMock
from app.services.inpainter import _clip_auto_mask_to_balloon

def test_clip_auto_mask_to_smart_balloon_contour():
    # 100x100 white canvas
    h, w = 100, 100
    img = np.ones((h, w, 3), dtype=np.uint8) * 255
    
    # Text block centered at 40,40 with size 20x20
    block = MagicMock()
    block.x = 40
    block.y = 40
    block.width = 20
    block.height = 20
    
    # Smart balloon polygon contour: diamond from (30,50), (50,30), (70,50), (50,70)
    contour = [[30, 50], [50, 30], [70, 50], [50, 70]]
    block.extra_metadata = {
        "smart_balloon": {
            "contour_points": contour
        }
    }
    
    # Mask with text inside AND bleeding outside the diamond to (10, 10)
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[45:55, 45:55] = 255  # Inside diamond
    mask[10:20, 10:20] = 255  # Outside diamond (bleeding)
    
    clipped = _clip_auto_mask_to_balloon(block, mask, w, h, image=img, dilation_margin=3)
    
    # Verify: outside pixel (15,15) MUST be zero (clamped)
    assert clipped[15, 15] == 0, "Bleeding mask outside contour must be strictly removed"
    # Verify: inside center pixel (50,50) MUST be preserved
    assert clipped[50, 50] == 255, "Inside text mask must be preserved"
    print("TEST PASSED: Balloon mask is strictly clamped to contour interior!")

if __name__ == "__main__":
    test_clip_auto_mask_to_smart_balloon_contour()
