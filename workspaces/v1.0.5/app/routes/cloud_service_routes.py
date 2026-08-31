"""
DOBKLE Cloud Hub API Router
Exposes secure cloud endpoints for Remote Dobkle Desktop clients:
- GET  /api/cloud/dobkle/status
- POST /api/cloud/dobkle/ocr
- POST /api/cloud/dobkle/clean
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.cloud_dobkle_service import (
    decode_base64_image,
    decode_base64_pil,
    encode_image_base64,
    get_clean_semaphore,
    get_cloud_hub_status,
    get_ocr_semaphore,
    run_cloud_clean,
    run_cloud_ocr,
    verify_api_key,
)

logger = logging.getLogger("houmi-cloud-routes")
router = APIRouter(prefix="/cloud/dobkle", tags=["DOBKLE Cloud Hub"])


# ─── Pydantic Request & Response Schemas ──────────────────────────────────

class CloudOcrCropPayload(BaseModel):
    id: str = Field(..., description="Unique client-side block identifier")
    image_base64: str = Field(..., description="Base64 encoded cropped speech balloon image")


class CloudOcrRequest(BaseModel):
    crops: List[CloudOcrCropPayload] = Field(..., description="List of cropped balloon images to transcribe")
    source_lang: str = Field("ja", description="Source text language (ja, zh, ko, en)")
    ocr_depth: str = Field("full", description="OCR depth: 'full' (with styling/effects) or 'text_only'")
    model: str = Field("flash", description="AI model to target via AGY (e.g. flash, pro, sonnet)")
    timeout: float = Field(90.0, description="Max execution timeout in seconds")


class CloudCleanRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded full page or region image")
    mask_base64: str = Field(..., description="Base64 encoded binary mask image (white=inpainting area)")
    engine: str = Field("lama", description="Inpainting engine: 'lama' or 'telea'")
    dilation: int = Field(4, description="Mask dilation kernel radius in pixels")
    format: str = Field("webp", description="Output format: 'webp', 'png', or 'jpeg'")
    quality: int = Field(92, description="Compression quality (1-100) for lossy formats")


# ─── Auth Dependency Helper ───────────────────────────────────────────────

def require_api_key(
    x_dobkle_api_key: Optional[str] = Header(None, alias="X-Dobkle-Api-Key"),
    api_key: Optional[str] = Query(None),
) -> str:
    key_candidate = x_dobkle_api_key or api_key
    if not verify_api_key(key_candidate):
        logger.warning("Unauthorized Cloud Hub access attempt (invalid or missing API key)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Dobkle-Api-Key authentication header",
        )
    return key_candidate or ""


# ─── Route Endpoints ──────────────────────────────────────────────────────

@router.get("/status")
@router.get("/health")
def cloud_hub_status():
    """Return live status and capabilities of the host machine."""
    return get_cloud_hub_status()


@router.post("/ocr")
async def cloud_ocr_endpoint(
    payload: CloudOcrRequest,
    x_dobkle_api_key: Optional[str] = Header(None, alias="X-Dobkle-Api-Key"),
    api_key: Optional[str] = Query(None),
):
    """
    Receives speech balloon crops from remote client, builds a compact PDF grid sheet,
    and runs AGY Gemini VLM on the host PC to extract transcription and typography styling.
    """
    require_api_key(x_dobkle_api_key, api_key)

    if not payload.crops:
        return {"ok": True, "results": [], "total": 0, "mapped": 0, "timing_ms": 0}

    # Decode incoming base64 crops
    decoded_crops = []
    for crop_item in payload.crops:
        try:
            pil_img = decode_base64_pil(crop_item.image_base64)
            decoded_crops.append((crop_item.id, pil_img))
        except Exception as err:
            logger.warning(f"Failed to decode base64 crop {crop_item.id}: {err}")

    if not decoded_crops:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="None of the provided crop images could be decoded",
        )

    # Acquire concurrency semaphore to throttle concurrent AGY processes
    semaphore = get_ocr_semaphore()
    async with semaphore:
        result = await asyncio.to_thread(
            run_cloud_ocr,
            crops=decoded_crops,
            source_lang=payload.source_lang,
            ocr_depth=payload.ocr_depth,
            model=payload.model,
            timeout=payload.timeout,
        )

    return result


@router.post("/clean")
async def cloud_clean_endpoint(
    payload: CloudCleanRequest,
    x_dobkle_api_key: Optional[str] = Header(None, alias="X-Dobkle-Api-Key"),
    api_key: Optional[str] = Query(None),
):
    """
    Receives image and mask from remote client, runs high-quality LaMa GPU inpainting
    on the host machine, and returns the cleaned image base64 stream.
    """
    require_api_key(x_dobkle_api_key, api_key)

    try:
        img_bgr = decode_base64_image(payload.image_base64)
        mask = decode_base64_image(payload.mask_base64)
    except Exception as err:
        logger.error(f"Failed to decode image/mask for cloud clean: {err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid base64 image or mask: {err}",
        )

    # Acquire clean semaphore to throttle concurrent GPU/CPU inpainting tasks
    semaphore = get_clean_semaphore()
    async with semaphore:
        cleaned_bgr, timing_ms = await asyncio.to_thread(
            run_cloud_clean,
            img=img_bgr,
            mask=mask,
            engine=payload.engine,
            dilation=payload.dilation,
        )

    # Encode result to base64
    try:
        cleaned_b64 = encode_image_base64(
            cleaned_bgr,
            format_ext=payload.format,
            quality=payload.quality,
        )
    except Exception as err:
        logger.error(f"Failed to encode cleaned image: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to encode cleaned output: {err}",
        )

    return {
        "ok": True,
        "cleaned_image_base64": cleaned_b64,
        "timing_ms": timing_ms,
        "width": cleaned_bgr.shape[1],
        "height": cleaned_bgr.shape[0],
    }
