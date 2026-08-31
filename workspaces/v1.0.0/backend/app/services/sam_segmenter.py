"""SAM 2.1 Hiera-Base+ segmentation service using ONNX Runtime.

Provides interactive box-prompt segmentation for the Mask Editor's
Smart Segment feature.  The encoder runs once per crop image and
caches the embeddings; the lightweight decoder runs on every user
drag to produce a pixel-precise mask almost instantly.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Tuple

import cv2
import numpy as np
try:
    import onnxruntime as ort
except ImportError:
    ort = None

from app.config import SAM_ENCODER_PATH, SAM_DECODER_PATH

logger = logging.getLogger("houmi-sam")

# ---------------------------------------------------------------------------
# Image preprocessing helpers
# ---------------------------------------------------------------------------

_SAM_INPUT_SIZE = 1024

# ImageNet normalisation constants used by SAM
_PIXEL_MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
_PIXEL_STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)


def _preprocess_image(image_bgr: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
    """Resize, pad, and normalise an image for the SAM 2.1 encoder.

    Returns (input_tensor, scale, pad_h, pad_w) so the caller can
    map decoder outputs back to the original coordinate space.
    """
    h, w = image_bgr.shape[:2]
    scale = _SAM_INPUT_SIZE / max(h, w)
    new_h, new_w = int(h * scale + 0.5), int(w * scale + 0.5)
    resized = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Convert BGR → RGB and normalise
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - _PIXEL_MEAN) / _PIXEL_STD

    # Pad to 1024×1024
    pad_h = _SAM_INPUT_SIZE - new_h
    pad_w = _SAM_INPUT_SIZE - new_w
    if pad_h > 0 or pad_w > 0:
        rgb = np.pad(rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="constant")

    # HWC → NCHW
    tensor = rgb.transpose(2, 0, 1)[np.newaxis]
    return tensor, scale, pad_h, pad_w


# ---------------------------------------------------------------------------
# SAM 2.1 Segmenter
# ---------------------------------------------------------------------------

class SAM2Segmenter:
    """Wraps SAM 2.1 Hiera-Base+ encoder + decoder ONNX sessions."""

    def __init__(
        self,
        encoder_path: str,
        decoder_path: str,
        providers: list[str] | None = None,
    ):
        if providers is None:
            providers = ["CPUExecutionProvider"]
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        logger.info("Loading SAM 2.1 encoder: %s", encoder_path)
        self.encoder = ort.InferenceSession(
            encoder_path, sess_options=sess_options, providers=providers,
        )
        logger.info("Loading SAM 2.1 decoder: %s", decoder_path)
        self.decoder = ort.InferenceSession(
            decoder_path, sess_options=sess_options, providers=providers,
        )
        self.current_providers = self.encoder.get_providers()
        logger.info(
            "SAM 2.1 Hiera-Base+ ready on providers: %s",
            self.current_providers,
        )

        # Embedding cache (one crop at a time is sufficient for the mask editor)
        self._cache_key: str | None = None
        self._cached_embeddings: dict | None = None
        self._cached_scale: float = 1.0
        self._cached_orig_hw: Tuple[int, int] = (0, 0)
        self._lock = threading.Lock()

    # ----- Encoder -----

    def _image_hash(self, image_bgr: np.ndarray) -> str:
        """Fast hash to detect whether the crop changed."""
        small = cv2.resize(image_bgr, (64, 64), interpolation=cv2.INTER_AREA)
        return hashlib.md5(small.tobytes()).hexdigest()

    def encode(self, image_bgr: np.ndarray) -> dict:
        """Return cached or freshly computed image embeddings."""
        key = self._image_hash(image_bgr)
        with self._lock:
            if self._cache_key == key and self._cached_embeddings is not None:
                return self._cached_embeddings

        tensor, scale, _pad_h, _pad_w = _preprocess_image(image_bgr)
        outputs = self.encoder.run(None, {"image": tensor})
        # Outputs: high_res_feats_0, high_res_feats_1, image_embed
        embeddings = {
            "image_embed": outputs[2],
            "high_res_feats_0": outputs[0],
            "high_res_feats_1": outputs[1],
        }
        with self._lock:
            self._cache_key = key
            self._cached_embeddings = embeddings
            self._cached_scale = scale
            self._cached_orig_hw = image_bgr.shape[:2]
        return embeddings

    # ----- Decoder -----

    def segment_box(
        self,
        image_bgr: np.ndarray,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> np.ndarray:
        """Segment the region inside the given box and return a binary mask.

        The returned mask has the same spatial dimensions as *image_bgr*
        with 255 for foreground and 0 for background.
        """
        embeddings = self.encode(image_bgr)
        h, w = image_bgr.shape[:2]
        scale = self._cached_scale

        # Scale box coordinates to the encoder's input space
        point_coords = np.array(
            [[[x0 * scale, y0 * scale], [x1 * scale, y1 * scale]]],
            dtype=np.float32,
        )
        # Labels: 2 = top-left box corner, 3 = bottom-right box corner
        point_labels = np.array([[2, 3]], dtype=np.float32)

        # No prior mask
        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask_input = np.array([0.0], dtype=np.float32)

        outputs = self.decoder.run(
            None,
            {
                "image_embed": embeddings["image_embed"],
                "high_res_feats_0": embeddings["high_res_feats_0"],
                "high_res_feats_1": embeddings["high_res_feats_1"],
                "point_coords": point_coords,
                "point_labels": point_labels,
                "mask_input": mask_input,
                "has_mask_input": has_mask_input,
            },
        )

        masks = outputs[0]          # shape: (1, num_masks, H_out, W_out)
        iou_scores = outputs[1]     # shape: (1, 3)

        # Pick the mask with the highest IoU score
        best_idx = int(np.argmax(iou_scores[0]))
        mask_logits = masks[0, best_idx]  # (H_out, W_out)

        # Threshold logits → binary – but we must upscale the *continuous*
        # logits FIRST so the boundary stays smooth, then threshold.

        # Resize back to original image dimensions
        # The decoder output covers the full 1024×1024 input; crop the valid
        # region before resizing.
        out_h, out_w = mask_logits.shape[:2]
        valid_h = int(h * scale / _SAM_INPUT_SIZE * out_h + 0.5)
        valid_w = int(w * scale / _SAM_INPUT_SIZE * out_w + 0.5)
        valid_h = min(valid_h, out_h)
        valid_w = min(valid_w, out_w)
        cropped_logits = mask_logits[:valid_h, :valid_w].astype(np.float32)

        # Upscale continuous logits with bilinear interpolation (smooth edges)
        upscaled_logits = cv2.resize(
            cropped_logits, (w, h), interpolation=cv2.INTER_LINEAR,
        )

        # NOW threshold the smooth high-res logits to binary
        result = (upscaled_logits > 0.0).astype(np.uint8) * 255
        return result

    def segment_points(
        self,
        image_bgr: np.ndarray,
        points: list[tuple[int, int]],
    ) -> np.ndarray:
        """Segment the region based on a list of positive point prompts.

        The returned mask has the same spatial dimensions as *image_bgr*
        with 255 for foreground and 0 for background.
        """
        embeddings = self.encode(image_bgr)
        h, w = image_bgr.shape[:2]
        scale = self._cached_scale

        coords = []
        labels = []
        for x, y in points:
            coords.append([x * scale, y * scale])
            labels.append(1)  # 1 = positive point

        point_coords = np.array([coords], dtype=np.float32)
        point_labels = np.array([labels], dtype=np.float32)

        mask_input = np.zeros((1, 1, 256, 256), dtype=np.float32)
        has_mask_input = np.array([0.0], dtype=np.float32)

        outputs = self.decoder.run(
            None,
            {
                "image_embed": embeddings["image_embed"],
                "high_res_feats_0": embeddings["high_res_feats_0"],
                "high_res_feats_1": embeddings["high_res_feats_1"],
                "point_coords": point_coords,
                "point_labels": point_labels,
                "mask_input": mask_input,
                "has_mask_input": has_mask_input,
            },
        )

        masks = outputs[0]
        iou_scores = outputs[1]
        best_idx = int(np.argmax(iou_scores[0]))
        mask_logits = masks[0, best_idx]

        out_h, out_w = mask_logits.shape[:2]
        valid_h = int(h * scale / _SAM_INPUT_SIZE * out_h + 0.5)
        valid_w = int(w * scale / _SAM_INPUT_SIZE * out_w + 0.5)
        valid_h = min(valid_h, out_h)
        valid_w = min(valid_w, out_w)
        cropped_logits = mask_logits[:valid_h, :valid_w].astype(np.float32)

        upscaled_logits = cv2.resize(
            cropped_logits, (w, h), interpolation=cv2.INTER_LINEAR,
        )
        return (upscaled_logits > 0.0).astype(np.uint8) * 255



# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_sam: SAM2Segmenter | None = None
_sam_checked = False
_sam_lock = threading.Lock()


def _get_sam() -> SAM2Segmenter | None:
    """Return the singleton SAM 2.1 segmenter (lazy-loaded, thread-safe)."""
    global _sam, _sam_checked
    if _sam is not None:
        return _sam
    with _sam_lock:
        if _sam is not None:
            return _sam
        if _sam_checked:
            return None
        if SAM_ENCODER_PATH.exists() and SAM_DECODER_PATH.exists():
            try:
                _sam = SAM2Segmenter(
                    str(SAM_ENCODER_PATH),
                    str(SAM_DECODER_PATH),
                )
            except Exception as e:
                logger.warning("SAM 2.1 failed to load: %s", e)
                _sam = None
        else:
            logger.info(
                "SAM 2.1 models not found at %s (Smart Segment unavailable)",
                SAM_ENCODER_PATH.parent,
            )
        _sam_checked = True
    return _sam


def smart_segment_box(
    image_bgr: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> np.ndarray | None:
    """Public API: segment a box region using SAM 2.1.

    Returns a binary mask (H, W) with 255 for foreground, or None if SAM
    is not available.
    """
    segmenter = _get_sam()
    if segmenter is None:
        return None
    return segmenter.segment_box(image_bgr, x0, y0, x1, y1)


def smart_segment_points(
    image_bgr: np.ndarray,
    points: list[tuple[int, int]],
) -> np.ndarray | None:
    """Public API: segment a region using SAM 2.1 with point prompts.

    Returns a binary mask (H, W) with 255 for foreground, or None if SAM
    is not available.
    """
    segmenter = _get_sam()
    if segmenter is None:
        return None
    return segmenter.segment_points(image_bgr, points)
