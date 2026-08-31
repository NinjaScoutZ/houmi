import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from app.routes.pipeline import generate_block_inpaint_preview, InpaintPreviewRequest
import base64
import numpy as np
import cv2


class TestInpaintPreview:
    """Test suite for the inpaint preview endpoint."""

    def test_valid_mask_generates_preview(self):
        """Valid mask should generate preview successfully."""
        # Create test image and mask
        test_img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        # block (50,50,100,100) on a 100x100 image yields an 80x80 padded crop
        test_mask = np.zeros((80, 80), dtype=np.uint8)
        test_mask[20:60, 20:60] = 255

        # Encode mask to base64
        _, mask_buffer = cv2.imencode('.png', test_mask)
        mask_b64 = f"data:image/png;base64,{base64.b64encode(mask_buffer).decode('utf-8')}"

        # Mock dependencies
        mock_block = Mock()
        mock_block.id = "block_1"
        mock_block.x = 50
        mock_block.y = 50
        mock_block.width = 100
        mock_block.height = 100
        mock_block.page = Mock()
        mock_block.page.source_image_path = "/fake/path.png"
        mock_block.page.project = Mock()
        mock_block.page.project.settings = {}

        mock_db = Mock()
        mock_db.query().filter().first.return_value = mock_block

        request = InpaintPreviewRequest(mask_base64=mask_b64)

        with patch('app.routes.pipeline.Path.exists', return_value=True):
            with patch('app.routes.pipeline.np.fromfile', return_value=test_img.tobytes()):
                with patch('app.routes.pipeline.cv2.imdecode', side_effect=[test_mask, test_img]):
                    with patch('app.services.inpainter._get_lama') as mock_lama:
                        mock_lama_instance = Mock()
                        mock_lama_instance.inpaint = Mock(return_value=test_img.copy())
                        mock_lama.return_value = mock_lama_instance

                        result = generate_block_inpaint_preview("block_1", request, mock_db)

        assert result["status"] == "success"
        assert "preview" in result
        assert result["preview"].startswith("data:image/png;base64,")

    def test_invalid_mask_format_raises_400(self):
        """Invalid base64 mask should raise 400 error."""
        mock_db = Mock()
        mock_block = Mock()
        mock_block.page = Mock()
        mock_block.page.source_image_path = "/fake/path.png"
        mock_db.query().filter().first.return_value = mock_block

        request = InpaintPreviewRequest(mask_base64="invalid_base64")

        with pytest.raises(HTTPException) as exc_info:
            generate_block_inpaint_preview("block_1", request, mock_db)

        assert exc_info.value.status_code == 400

    def test_missing_block_raises_404(self):
        """Non-existent block should raise 404."""
        mock_db = Mock()
        mock_db.query().filter().first.return_value = None

        request = InpaintPreviewRequest(mask_base64="data:image/png;base64,iVBORw0KGgo=")

        with pytest.raises(HTTPException) as exc_info:
            generate_block_inpaint_preview("nonexistent", request, mock_db)

        assert exc_info.value.status_code == 404

    def test_large_image_downscales_to_512px(self):
        """Images larger than 512px should be downscaled for preview."""
        # Create large test image
        large_img = np.random.randint(0, 255, (2048, 2048, 3), dtype=np.uint8)
        mask = np.zeros((2048, 2048), dtype=np.uint8)
        mask[500:1500, 500:1500] = 255

        _, mask_buffer = cv2.imencode('.png', mask)
        mask_b64 = f"data:image/png;base64,{base64.b64encode(mask_buffer).decode('utf-8')}"

        mock_block = Mock()
        mock_block.x = 0
        mock_block.y = 0
        mock_block.width = 2048
        mock_block.height = 2048
        mock_block.page = Mock()
        mock_block.page.source_image_path = "/fake/large.png"
        mock_block.page.project = Mock()
        mock_block.page.project.settings = {"inpaint_engine": "lama_onnx"}

        mock_db = Mock()
        mock_db.query().filter().first.return_value = mock_block

        request = InpaintPreviewRequest(mask_base64=mask_b64)

        inpaint_calls = []

        def mock_inpaint(img, msk):
            inpaint_calls.append((img.shape, msk.shape))
            return img.copy()

        with patch('app.routes.pipeline.Path.exists', return_value=True):
            with patch('app.routes.pipeline.np.fromfile', return_value=large_img.tobytes()):
                with patch('app.routes.pipeline.cv2.imdecode', side_effect=[mask, large_img]):
                    with patch('app.services.inpainter._get_lama') as mock_lama:
                        mock_lama_instance = Mock()
                        mock_lama_instance.inpaint = Mock(side_effect=mock_inpaint)
                        mock_lama.return_value = mock_lama_instance

                        result = generate_block_inpaint_preview("block_1", request, mock_db)

        # Verify downscaling happened
        assert len(inpaint_calls) == 1
        img_shape, mask_shape = inpaint_calls[0]
        assert max(img_shape[:2]) == 512
        assert result["status"] == "success"

    def test_preview_uses_block_bounds_with_padding(self):
        """Preview should crop to block bounds with padding."""
        test_img = np.random.randint(0, 255, (500, 500, 3), dtype=np.uint8)
        # block (100,100,50,50) with 30px padding yields 110x110
        test_mask = np.zeros((110, 110), dtype=np.uint8)

        _, mask_buffer = cv2.imencode('.png', test_mask)
        mask_b64 = f"data:image/png;base64,{base64.b64encode(mask_buffer).decode('utf-8')}"

        mock_block = Mock()
        mock_block.x = 100
        mock_block.y = 100
        mock_block.width = 50
        mock_block.height = 50
        mock_block.page = Mock()
        mock_block.page.source_image_path = "/fake/path.png"
        mock_block.page.project = Mock()
        mock_block.page.project.settings = {"inpaint_engine": "lama_onnx"}

        mock_db = Mock()
        mock_db.query().filter().first.return_value = mock_block

        request = InpaintPreviewRequest(mask_base64=mask_b64)

        crop_shapes = []

        def mock_inpaint(img, msk):
            crop_shapes.append(img.shape)
            return img.copy()

        with patch('app.routes.pipeline.Path.exists', return_value=True):
            with patch('app.routes.pipeline.np.fromfile', return_value=test_img.tobytes()):
                with patch('app.routes.pipeline.cv2.imdecode', side_effect=[test_mask, test_img]):
                    with patch('app.services.inpainter._get_lama') as mock_lama:
                        mock_lama_instance = Mock()
                        mock_lama_instance.inpaint = Mock(side_effect=mock_inpaint)
                        mock_lama.return_value = mock_lama_instance

                        generate_block_inpaint_preview("block_1", request, mock_db)

        # Verify crop includes padding (32px each side = 64px total)
        # Block: 50x50, with padding: ~114x114
        assert len(crop_shapes) == 1
        crop_h, crop_w = crop_shapes[0][:2]
        assert 100 <= crop_h <= 130  # Approximate due to padding
        assert 100 <= crop_w <= 130

    def test_preview_rejects_mask_with_wrong_crop_geometry(self):
        """Preview must never resize a mask into a different coordinate space."""
        image = np.zeros((200, 200, 3), dtype=np.uint8)
        wrong_mask = np.zeros((50, 50), dtype=np.uint8)
        _, mask_buffer = cv2.imencode('.png', wrong_mask)
        request = InpaintPreviewRequest(
            mask_base64=f"data:image/png;base64,{base64.b64encode(mask_buffer).decode('utf-8')}"
        )

        block = Mock()
        block.id = "block_1"
        block.x, block.y, block.width, block.height = 80, 80, 40, 40
        block.page = Mock()
        block.page.source_image_path = "/fake/path.png"
        block.page.project = Mock(settings={})
        db = Mock()
        db.query().filter().first.return_value = block

        with patch('app.routes.pipeline.Path.exists', return_value=True):
            with patch('app.routes.pipeline.np.fromfile', return_value=image.tobytes()):
                with patch('app.routes.pipeline.cv2.imdecode', side_effect=[wrong_mask, image]):
                    with pytest.raises(HTTPException) as exc_info:
                        generate_block_inpaint_preview("block_1", request, db)

        assert exc_info.value.status_code == 422
        assert "dimensions" in str(exc_info.value.detail)
