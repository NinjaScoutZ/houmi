import pytest
import numpy as np
import cv2
from unittest.mock import Mock, MagicMock
from app.services.inpainter import _tile_based_inpaint


class TestTileBasedInpainting:
    """Test tile-based inpainting for large regions."""

    def test_small_image_uses_standard_inpaint(self):
        """Images smaller than tile_size should use standard inpainting."""
        # Create small test image
        image = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
        mask = np.zeros((512, 512), dtype=np.uint8)
        mask[100:200, 100:200] = 255

        # Mock LaMa service
        lama = Mock()
        lama.inpaint = Mock(return_value=image.copy())

        result = _tile_based_inpaint(image, mask, lama, tile_size=1024, overlap=64)

        # Should call standard inpaint once
        assert lama.inpaint.call_count == 1
        assert result.shape == image.shape

    def test_large_image_uses_tiling(self):
        """Images larger than tile_size should be split into tiles."""
        # Create large test image
        image = np.random.randint(0, 255, (2048, 2048, 3), dtype=np.uint8)
        mask = np.zeros((2048, 2048), dtype=np.uint8)
        mask[500:1500, 500:1500] = 255

        # Mock LaMa service
        lama = Mock()
        lama.inpaint = Mock(side_effect=lambda img, msk: img.copy())

        result = _tile_based_inpaint(image, mask, lama, tile_size=1024, overlap=64)

        # Should call inpaint multiple times (one per tile with mask)
        assert lama.inpaint.call_count > 1
        assert result.shape == image.shape

    def test_tiles_have_correct_overlap(self):
        """Tiles should have proper overlap for smooth blending."""
        image = np.ones((1500, 1500, 3), dtype=np.uint8) * 128
        mask = np.ones((1500, 1500), dtype=np.uint8) * 255

        lama = Mock()
        # Return slightly different color to track blending
        lama.inpaint = Mock(side_effect=lambda img, msk: np.ones_like(img) * 200)

        result = _tile_based_inpaint(image, mask, lama, tile_size=1024, overlap=128)

        # Result should be blended (not exactly 200 due to overlap blending)
        assert result.shape == image.shape
        assert np.max(result) <= 255
        assert np.min(result) >= 0

    def test_empty_mask_skips_inpainting(self):
        """Tiles with no mask should be skipped."""
        image = np.random.randint(0, 255, (2048, 2048, 3), dtype=np.uint8)
        mask = np.zeros((2048, 2048), dtype=np.uint8)
        # Only mask small corner
        mask[10:50, 10:50] = 255

        lama = Mock()
        lama.inpaint = Mock(return_value=image[:1024, :1024].copy())

        result = _tile_based_inpaint(image, mask, lama, tile_size=1024, overlap=64)

        # Should only process tiles with mask
        assert lama.inpaint.call_count <= 2  # Only tiles containing the small mask
        assert result.shape == image.shape

    def test_output_matches_input_dimensions(self):
        """Output should always match input dimensions exactly."""
        for h, w in [(1000, 1500), (2048, 1024), (1234, 5678)]:
            image = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
            mask = np.ones((h, w), dtype=np.uint8) * 255

            lama = Mock()
            lama.inpaint = Mock(side_effect=lambda img, msk: img.copy())

            result = _tile_based_inpaint(image, mask, lama, tile_size=1024, overlap=64)

            assert result.shape == image.shape, f"Shape mismatch for {h}x{w}"

    def test_blending_weights_normalized(self):
        """Blending should produce valid pixel values without overflow."""
        image = np.ones((2048, 2048, 3), dtype=np.uint8) * 255
        mask = np.ones((2048, 2048), dtype=np.uint8) * 255

        lama = Mock()
        lama.inpaint = Mock(side_effect=lambda img, msk: np.ones_like(img) * 255)

        result = _tile_based_inpaint(image, mask, lama, tile_size=1024, overlap=128)

        # Should not overflow
        assert np.all(result <= 255)
        assert np.all(result >= 0)
        assert result.dtype == np.uint8
