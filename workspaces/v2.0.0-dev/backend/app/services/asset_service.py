from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError


MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_IMAGE_PIXELS = 120_000_000
ALLOWED_MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
    "image/vnd.adobe.photoshop",
}


@dataclass(frozen=True)
class ValidatedAsset:
    media_type: str
    byte_size: int
    width: int | None
    height: int | None


def _detect_media_type(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    if payload.startswith(b"BM"):
        return "image/bmp"
    if payload.startswith(b"8BPS"):
        return "image/vnd.adobe.photoshop"
    return None


def validate_asset_payload(
    payload: bytes,
    *,
    declared_media_type: str | None = None,
    filename: str | None = None,
) -> ValidatedAsset:
    """Validate an uploaded asset before it enters Host storage.

    Extension and client-provided MIME values are treated as hints only. The
    payload signature is authoritative, and raster images are opened with a
    strict pixel budget to reduce decompression-bomb risk.
    """
    if not payload:
        raise ValueError("Asset payload is empty")
    if len(payload) > MAX_ASSET_BYTES:
        raise ValueError(f"Asset exceeds the {MAX_ASSET_BYTES} byte limit")

    media_type = _detect_media_type(payload)
    if media_type is None or media_type not in ALLOWED_MEDIA_TYPES:
        raise ValueError("Unsupported or invalid asset signature")
    if declared_media_type and declared_media_type != media_type:
        # Accept the common browser alias for JPEG, but reject mismatches that
        # could hide an unsafe payload behind a trusted MIME type.
        if not (declared_media_type == "image/jpg" and media_type == "image/jpeg"):
            raise ValueError("Declared media type does not match asset bytes")

    width = height = None
    if media_type != "image/vnd.adobe.photoshop":
        try:
            with Image.open(io.BytesIO(payload)) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image exceeds the maximum pixel budget")
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Image payload could not be decoded safely") from exc

    return ValidatedAsset(
        media_type=media_type,
        byte_size=len(payload),
        width=width,
        height=height,
    )
