"""
DOBKLE Cloud AI Hub Service Orchestrator
Processes multi-crop OCR via AGY (Gemini VLM) and GPU Inpainting (LaMa / Telea)
on the host machine for remote Dobkle / Houmi desktop clients.
"""

import asyncio
import base64
import io
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.config import (
    HOUMI_CLOUD_API_KEYS,
    HOUMI_CLOUD_ENABLED,
    HOUMI_CLOUD_MAX_CLEAN_CONCURRENCY,
    HOUMI_CLOUD_MAX_OCR_CONCURRENCY,
    HOUMI_CLOUD_MAX_PAYLOAD_MB,
)
from app.services.ocr import (
    _gemini_prompt_image_path,
    _parse_gemini_grid_response,
    _run_gemini_command,
)

logger = logging.getLogger("houmi-cloud-service")

# Concurrency Semaphores to protect host resources
_ocr_semaphore: Optional[asyncio.Semaphore] = None
_clean_semaphore: Optional[asyncio.Semaphore] = None


def get_ocr_semaphore() -> asyncio.Semaphore:
    global _ocr_semaphore
    if _ocr_semaphore is None:
        _ocr_semaphore = asyncio.Semaphore(max(1, HOUMI_CLOUD_MAX_OCR_CONCURRENCY))
    return _ocr_semaphore


def get_clean_semaphore() -> asyncio.Semaphore:
    global _clean_semaphore
    if _clean_semaphore is None:
        _clean_semaphore = asyncio.Semaphore(max(1, HOUMI_CLOUD_MAX_CLEAN_CONCURRENCY))
    return _clean_semaphore


def verify_api_key(api_key: Optional[str]) -> bool:
    """Validate incoming client API key against configured allowed keys."""
    if not HOUMI_CLOUD_ENABLED:
        return False
    if not HOUMI_CLOUD_API_KEYS:
        # If no keys are specified in configuration, allow open access
        return True
    if not api_key:
        return False
    clean_key = str(api_key).strip()
    return clean_key in HOUMI_CLOUD_API_KEYS


def get_cloud_hub_status() -> Dict[str, Any]:
    """Return diagnostic telemetry and capabilities of this Cloud Hub host."""
    agy_path = shutil.which("agy")
    
    # Check GPU availability
    gpu_available = False
    gpu_name = "CPU"
    try:
        import torch
        if torch.cuda.is_available():
            gpu_available = True
            gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        pass

    # Check LaMa model availability
    lama_ready = False
    try:
        from app.services.inpainter import _get_lama
        lama = _get_lama()
        lama_ready = lama is not None
    except Exception:
        lama_ready = False

    return {
        "status": "online" if HOUMI_CLOUD_ENABLED else "disabled",
        "service": "DOBKLE Cloud AI Hub",
        "version": "1.0.0",
        "timestamp": time.time(),
        "agy": {
            "available": bool(agy_path),
            "executable": str(agy_path) if agy_path else None,
            "default_model": "gemini-3.7-flash",
        },
        "gpu": {
            "available": gpu_available,
            "device": gpu_name,
            "lama_inpainter_ready": lama_ready,
        },
        "limits": {
            "max_ocr_concurrency": HOUMI_CLOUD_MAX_OCR_CONCURRENCY,
            "max_clean_concurrency": HOUMI_CLOUD_MAX_CLEAN_CONCURRENCY,
            "max_payload_mb": HOUMI_CLOUD_MAX_PAYLOAD_MB,
        },
        "capabilities": {
            "ocr": ["gemini-3.7-flash", "gemini-3.6-flash", "claude-sonnet-4.6", "flash_lite"],
            "clean": ["lama", "telea", "subregion_patch"],
            "typography_styling": True,
            "pdf_grid_packing": True,
        },
    }


def decode_base64_image(data_str: str) -> np.ndarray:
    """Safely decode base64 string (with or without data URI prefix) to OpenCV BGR numpy array."""
    if not data_str:
        raise ValueError("Empty image data")
    if "," in data_str:
        data_str = data_str.split(",", 1)[1]
    image_bytes = base64.b64decode(data_str)
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Failed to decode base64 image data")
    return img


def decode_base64_pil(data_str: str) -> Image.Image:
    """Decode base64 string to PIL Image in RGB format."""
    if not data_str:
        raise ValueError("Empty image data")
    if "," in data_str:
        data_str = data_str.split(",", 1)[1]
    image_bytes = base64.b64decode(data_str)
    img = Image.open(io.BytesIO(image_bytes))
    return img.convert("RGB")


def encode_image_base64(img_bgr: np.ndarray, format_ext: str = ".webp", quality: int = 92) -> str:
    """Encode OpenCV image to base64 string."""
    if format_ext.lower() in [".webp", "webp"]:
        encode_params = [cv2.IMWRITE_WEBP_QUALITY, quality]
        success, encoded_img = cv2.imencode(".webp", img_bgr, encode_params)
        mime = "image/webp"
    elif format_ext.lower() in [".jpg", ".jpeg", "jpeg", "jpg"]:
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success, encoded_img = cv2.imencode(".jpg", img_bgr, encode_params)
        mime = "image/jpeg"
    else:
        success, encoded_img = cv2.imencode(".png", img_bgr)
        mime = "image/png"

    if not success:
        raise ValueError("Failed to encode image to base64")
    b64_bytes = base64.b64encode(encoded_img).decode("utf-8")
    return f"data:{mime};base64,{b64_bytes}"


def pack_crops_to_pdf(
    crops: List[Tuple[str, Image.Image]],
    project_label: str = "DOBKLE_CLOUD",
) -> Tuple[str, Dict[str, str]]:
    """
    Packs a list of (client_box_id, PIL_Image) into a multi-page PDF grid sheet.
    Returns (temp_pdf_path, mapping of stable_id -> client_box_id).
    """
    page_width = 1600
    page_height = 2400
    num_cols = 3
    col_width = (page_width - 60) // num_cols
    banner_h = 30

    font_banner = None
    try:
        font_banner = ImageFont.truetype("arialbd.ttf", 18)
    except Exception:
        font_banner = ImageFont.load_default()

    id_map = {}
    cards = []

    for idx, (client_id, crop_img) in enumerate(crops, start=1):
        clean_cid = str(client_id).replace("-", "")[:8]
        stable_id = f"BOX_{idx:03d}_{clean_cid}"
        id_map[stable_id] = client_id

        # Resize if crop is too small or too wide
        crop = crop_img
        if crop.height < 60 or crop.width < 60:
            scale = max(1.5, 80.0 / max(1, crop.height))
            crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)

        max_crop_w = col_width - 16
        if crop.width > max_crop_w:
            scale = max_crop_w / float(crop.width)
            crop = crop.resize((max_crop_w, int(crop.height * scale)), Image.Resampling.LANCZOS)

        card_w = col_width
        card_h = crop.height + banner_h + 12
        card = Image.new("RGB", (card_w, card_h), (255, 255, 255))
        draw_card = ImageDraw.Draw(card)
        draw_card.rectangle([0, 0, card_w, banner_h], fill=(30, 41, 59))
        draw_card.text((10, 4), f"HOUMI_BOX:{stable_id}", fill=(255, 255, 255), font=font_banner)
        draw_card.rectangle([0, 0, card_w - 1, card_h - 1], outline=(203, 213, 225), width=1)

        paste_x = (card_w - crop.width) // 2
        card.paste(crop, (paste_x, banner_h + 6))
        cards.append((stable_id, card))

    pdf_pages = []
    current_page_img = Image.new("RGB", (page_width, page_height), (241, 245, 249))
    draw_pg = ImageDraw.Draw(current_page_img)
    draw_pg.rectangle([0, 0, page_width, 45], fill=(15, 23, 42))
    draw_pg.text((20, 10), f"DOBKLE CLOUD OCR GRID — {project_label} (PAGE 1)", fill=(250, 204, 21), font=font_banner)

    col_idx = 0
    curr_x = 20 + col_idx * (col_width + 10)
    curr_y = 60

    for _, card in cards:
        card_h = card.height
        if curr_y + card_h > page_height - 20:
            col_idx += 1
            if col_idx >= num_cols:
                pdf_pages.append(current_page_img)
                current_page_img = Image.new("RGB", (page_width, page_height), (241, 245, 249))
                draw_pg = ImageDraw.Draw(current_page_img)
                draw_pg.rectangle([0, 0, page_width, 45], fill=(15, 23, 42))
                draw_pg.text((20, 10), f"DOBKLE CLOUD OCR GRID — {project_label} (PAGE {len(pdf_pages)+1})", fill=(250, 204, 21), font=font_banner)
                col_idx = 0
            curr_x = 20 + col_idx * (col_width + 10)
            curr_y = 60

        current_page_img.paste(card, (curr_x, curr_y))
        curr_y += card_h + 10

    pdf_pages.append(current_page_img)

    temp_pdf = tempfile.mktemp(suffix=".pdf")
    pdf_pages[0].save(temp_pdf, "PDF", resolution=100.0, save_all=True, append_images=pdf_pages[1:])
    return temp_pdf, id_map


def run_cloud_ocr(
    crops: List[Tuple[str, Image.Image]],
    source_lang: str = "ja",
    ocr_depth: str = "full",
    model: str = "flash",
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """
    Synchronous worker executing AGY PDF-collage OCR on the host machine.
    """
    if not crops:
        return {"ok": True, "results": [], "total": 0, "mapped": 0}

    temp_pdf, id_map = pack_crops_to_pdf(crops)
    try:
        image_ref = _gemini_prompt_image_path(temp_pdf)
        language = {"ja": "Japanese", "zh": "Chinese", "ko": "Korean", "en": "English"}.get(
            str(source_lang).lower(), "the source language"
        )

        if ocr_depth == "text_only":
            prompt = (
                f"Read every labeled text crop across all pages in attached PDF {image_ref}. "
                f"The text language is {language}.\n"
                "Return ONLY a valid JSON array: "
                '[{"box_id":"BOX_001_xxxxxxxx","text":"exact transcription"}].\n'
                "Use the exact box_id from the banner. Preserve line breaks and punctuation. Do not translate."
            )
        else:
            prompt = (
                f"You are an expert manga/webtoon editor and OCR typographer. Read every labeled text crop across all pages in attached PDF {image_ref}. "
                f"The text language is {language}.\n"
                "Analyze both the VISUAL APPEARANCE (speech bubble contour, text boldness, italics, stroke, typography, gradient, shadows, glowing aura) and SEMANTIC CONTEXT of each card.\n"
                "Return ONLY a valid JSON array, with exactly one object per label in this schema:\n"
                '[{"box_id":"BOX_001_xxxxxxxx","text":"exact transcription","balloon_type":"bubble|shout|narrative|thought|whisper|system|sfx","color_hex":"#000000","stroke_color_hex":null,"stroke_width_px":0,"bold":false,"italic":false,"gradient":null,"drop_shadow":null,"outer_glow":null,"inner_shadow":null}].\n\n'
                "VISUAL CLASSIFICATION RULES:\n"
                "1. 'shout': Spiky/burst jagged bubble borders, OR extra-bold dramatic text.\n"
                "2. 'bubble': Standard smooth oval speech balloons with regular clean font weight.\n"
                "3. 'narrative': Rectangular boxes with straight edges, caption bars.\n"
                "4. 'thought': Cloud-like scalloped wavy borders, bubble-chain tails.\n"
                "5. 'whisper': Dashed/dotted borders, or small/faint text.\n"
                "6. 'system': RPG / game status windows, UI notification cards.\n"
                "7. 'sfx': Hand-drawn sound effects floating on artwork.\n\n"
                "Use the exact full box_id from the header banner. Preserve line breaks and punctuation. Do not translate."
            )

        start_t = time.perf_counter()
        raw_output, success = _run_gemini_command(
            prompt,
            model=model,
            image_path=temp_pdf,
            provider="agy",
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0

        if not success or not raw_output:
            logger.error("AGY Cloud OCR execution failed on host machine.")
            return {
                "ok": False,
                "error": "AGY execution failed or timed out on host server",
                "results": [],
                "timing_ms": elapsed_ms,
            }

        expected_ids = set(id_map.keys())
        parsed_boxes = _parse_gemini_grid_response(raw_output, expected_ids)

        results = []
        for stable_id, client_id in id_map.items():
            parsed_info = parsed_boxes.get(stable_id)
            if parsed_info:
                entry = {
                    "id": client_id,
                    "text": parsed_info.get("text", ""),
                    "balloon_type": parsed_info.get("balloon_type", "bubble"),
                    "color_hex": parsed_info.get("color_hex", "#000000"),
                    "stroke_color_hex": parsed_info.get("stroke_color_hex"),
                    "stroke_width_px": parsed_info.get("stroke_width_px", 0),
                    "bold": parsed_info.get("bold", False),
                    "italic": parsed_info.get("italic", False),
                    "gradient": parsed_info.get("gradient"),
                    "drop_shadow": parsed_info.get("drop_shadow"),
                    "outer_glow": parsed_info.get("outer_glow"),
                    "inner_shadow": parsed_info.get("inner_shadow"),
                    "success": True,
                }
            else:
                entry = {
                    "id": client_id,
                    "text": "",
                    "balloon_type": "bubble",
                    "color_hex": "#000000",
                    "success": False,
                }
            results.append(entry)

        return {
            "ok": True,
            "results": results,
            "total": len(crops),
            "mapped": len(parsed_boxes),
            "timing_ms": round(elapsed_ms, 2),
        }

    finally:
        if os.path.exists(temp_pdf):
            try:
                os.remove(temp_pdf)
            except Exception:
                pass


def run_cloud_clean(
    img: np.ndarray,
    mask: np.ndarray,
    engine: str = "lama",
    dilation: int = 4,
) -> Tuple[np.ndarray, float]:
    """
    Synchronous worker executing LaMa or OpenCV Inpainting on the host GPU/CPU.
    """
    start_t = time.perf_counter()

    if img is None or mask is None:
        raise ValueError("Invalid image or mask array")

    ih, iw = img.shape[:2]
    if mask.shape[:2] != (ih, iw):
        mask = cv2.resize(mask, (iw, ih), interpolation=cv2.INTER_NEAREST)

    # Ensure mask is single channel 8-bit
    if len(mask.shape) == 3:
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
    _, mask_bin = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # Apply dilation if requested
    if dilation > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation * 2 + 1, dilation * 2 + 1))
        mask_bin = cv2.dilate(mask_bin, kernel, iterations=1)

    if np.count_nonzero(mask_bin) == 0:
        # No mask to inpaint
        return img.copy(), 0.0

    # Execute inpainting
    engine_lower = str(engine).lower().strip()
    if engine_lower == "telea":
        cleaned = cv2.inpaint(img, mask_bin, 3, cv2.INPAINT_TELEA)
    else:
        # Prefer LaMa GPU inpainting with fallback
        from app.services.inpainter import _get_lama
        lama = _get_lama()
        if lama is not None:
            try:
                cleaned = lama.inpaint(img, mask_bin)
            except Exception as e:
                logger.warning(f"Host LaMa inpaint failed: {e}; falling back to Telea")
                cleaned = cv2.inpaint(img, mask_bin, 5, cv2.INPAINT_NS)
        else:
            cleaned = cv2.inpaint(img, mask_bin, 5, cv2.INPAINT_NS)

    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
    return cleaned, round(elapsed_ms, 2)
