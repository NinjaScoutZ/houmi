"""
Image Sanity, Corrupted File Protection & 4K/8K Tiling Guard
Protects backend worker threads from crashing on malicious/corrupted inputs.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, Optional, Tuple
from PIL import Image, ImageOps

logger = logging.getLogger("houmi-image-guard")

# Maximum permitted image dimension before auto-downscaling to protect VRAM/RAM
DEFAULT_MAX_DIMENSION = 6144
MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 MB


class ImageGuardError(ValueError):
    pass


def validate_and_sanitize_image(
    image_bytes: bytes,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Validates, repairs EXIF orientation, sanitizes, and optionally bounds ultra-high-resolution images.
    Returns: (PIL.Image, metadata_dict)
    """
    if not image_bytes:
        raise ImageGuardError("Empty image byte buffer received.")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageGuardError(
            f"Image size exceeds maximum limit of {MAX_IMAGE_BYTES / (1024 * 1024)} MB."
        )

    try:
        raw_img = Image.open(io.BytesIO(image_bytes))
        raw_img.verify()
    except Exception as exc:
        raise ImageGuardError(f"Corrupted or invalid image format: {exc}")

    # Re-open for actual processing (verify closes the fp)
    img = Image.open(io.BytesIO(image_bytes))

    # Auto-orient based on EXIF tag
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Ensure standard RGB/RGBA mode
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA" if "transparency" in img.info or img.mode == "P" else "RGB")

    orig_w, orig_h = img.size
    downscaled = False

    # Check bounds against ultra-large dimensions
    if orig_w > max_dimension or orig_h > max_dimension:
        ratio = min(max_dimension / orig_w, max_dimension / orig_h)
        new_w = max(1, int(orig_w * ratio))
        new_h = max(1, int(orig_h * ratio))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        downscaled = True
        logger.info(f"Ultra-large image clamped: ({orig_w}x{orig_h}) -> ({new_w}x{new_h})")

    meta = {
        "original_width": orig_w,
        "original_height": orig_h,
        "final_width": img.width,
        "final_height": img.height,
        "format": img.format or "PNG",
        "mode": img.mode,
        "downscaled": downscaled,
    }

    return img, meta


def clamp_crop_box(
    box: Tuple[int, int, int, int],
    img_width: int,
    img_height: int,
) -> Tuple[int, int, int, int]:
    """
    Clamps (x1, y1, x2, y2) within image boundaries to prevent index out of bounds.
    """
    x1, y1, x2, y2 = box
    cx1 = max(0, min(img_width - 1, int(x1)))
    cy1 = max(0, min(img_height - 1, int(y1)))
    cx2 = max(cx1 + 1, min(img_width, int(x2)))
    cy2 = max(cy1 + 1, min(img_height, int(y2)))
    return (cx1, cy1, cx2, cy2)
