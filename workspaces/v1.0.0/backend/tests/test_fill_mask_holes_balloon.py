import numpy as np
import cv2
from app.services.inpainter import fill_mask_holes


def test_fill_mask_holes_preserves_balloon_interior():
    """
    Tests that a balloon containing text characters inside an enclosed border loop
    does not have its entire interior flood-filled into a solid mask.
    Only small glyph counter loops (like O, A, 口) should be filled.
    """
    # 300x300 canvas
    mask = np.zeros((300, 300), dtype=np.uint8)
    
    # Draw an angular/polygon balloon border loop
    pts = np.array([[40, 40], [260, 40], [280, 240], [50, 250]], np.int32)
    cv2.polylines(mask, [pts], isClosed=True, color=255, thickness=2)
    
    # Draw text with an 'O' (character counter hole) in the center
    cv2.circle(mask, (150, 150), 10, 255, thickness=2)  # Outer circle of 'O'
    # Inner hole at (150, 150) is 0
    assert mask[150, 150] == 0
    
    # Draw some hatching lines
    cv2.line(mask, (70, 70), (120, 120), 255, 1)
    cv2.line(mask, (180, 70), (230, 120), 255, 1)
    
    initial_pixels = np.count_nonzero(mask)
    
    # Run fill_mask_holes
    result = fill_mask_holes(mask)
    
    # 1. The small loop of the letter 'O' should be filled
    assert result[150, 150] == 255
    
    # 2. Points in the balloon whitespace must NOT be filled solid
    assert result[150, 100] == 0
    assert result[150, 200] == 0
    assert result[100, 180] == 0
    
    # 3. Total filled pixels must remain a small fraction (< 15%) of the total balloon area (~40,000 px)
    total_result_pixels = np.count_nonzero(result)
    assert total_result_pixels < initial_pixels + 500
    assert total_result_pixels < 4000
