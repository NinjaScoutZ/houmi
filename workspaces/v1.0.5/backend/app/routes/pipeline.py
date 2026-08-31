from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode
import logging
import base64
import binascii
import cv2
import numpy as np
from typing import Optional, Any
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Form, Body, Query
from sqlalchemy.orm import Session
from app.database import SessionLocal, get_db
from app.models.all_models import Page, TextBlock, Project


class DetectPipelineRequest(BaseModel):
    page_id: Optional[str] = None
    min_confidence: Optional[float] = None
    force: Optional[bool] = False
    backend: Optional[str] = None
    balloon_model: Optional[str] = None
    promote_with_ocr: Optional[bool] = False


class OcrPipelineRequest(BaseModel):
    page_id: Optional[str] = None
    backend: Optional[str] = None
    force: Optional[bool] = False
    block_ids: Optional[Any] = None
    source_lang: Optional[str] = None


class MaskPipelineRequest(BaseModel):
    page_id: Optional[str] = None


class InpaintPipelineRequest(BaseModel):
    page_id: Optional[str] = None
from app.security.dependencies import get_current_user_or_local, ensure_project_access
from app.services.detector import balloon_detector
from app.services.ocr import (
    _get_gemini_api_key,
    crop_and_ocr_block,
    crop_and_ocr_blocks_parallel,
)
from app.services.memory_cache import page_image_cache
from app.services.inpainter import (
    build_automatic_page_mask,
    build_effective_page_mask,
    clean_page_text,
    fast_telea_preview,
    generate_inpaint_preview,
    get_automatic_block_mask,
    get_or_build_effective_page_mask,
    get_adaptive_text_mask,
    invalidate_clean_assets,
    is_clean_asset_current,
    mark_clean_assets_stale,
    reclean_page_block,
    should_use_smart_mask,
    _mask_asset_path,
)
from app.services.text_mask import (
    generate_high_quality_text_mask_isolated,
    high_quality_text_mask_allowed,
)
from app.services.renderer import render_page_text
from app.services.trainer import model_trainer
from app.services.layout_region import analyze_layout_region
from app.ws_manager import ws_manager
from app.services.text_templates import apply_default_text_template
from app.services.browser_render import (
    BrowserRenderError,
    MAX_BROWSER_RENDER_BYTES,
    StaleBrowserRenderError,
    page_render_revision,
    save_browser_render,
)
from app.services.typesetting.style_judge import judge_style, judge_page_styles_batch_ai, apply_style_descriptor_to_block
from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
from app.config import (
    OCR_HOST,
    OCR_PORT,
    get_execution_provider_setting,
    get_inpaint_engine,
    get_ocr_engine,
)
from app.security.dependencies import require_admin, require_pipeline_access, require_resource_access
import shutil
import requests

router = APIRouter(
    tags=["Pipeline"],
    dependencies=[Depends(require_pipeline_access), Depends(require_resource_access)],
)
logger = logging.getLogger("houmi-pipeline-router")

# In-memory batch job tracking
# project_id -> status dict
batch_jobs = {}
# page_id -> status for the single-page resumable workflow
page_jobs = {}


@router.get("/pipeline/ocr/engines")
def get_ocr_engines():
    """
    Returns available and disabled OCR engines with categorization and detailed status.
    Supported engines: gemini, glm, deepseek, paddleocr.
    Categories: cloud, local_vlm, local_offline.
    """
    # 1. DOBKLE OCR (Gemini 3.6 Flash REST / Proxy / AGY AI)
    gemini_cli = shutil.which("agy")
    gemini_api_configured = bool(_get_gemini_api_key())
    gemini_available = True  # DOBKLE OCR is always available in Houmi
    gemini_reason = None

    # 2. Local VLM Server (port 2322)
    vlm_server_alive = False
    vlm_last_error = None
    try:
        url = f"http://{OCR_HOST}:{OCR_PORT}/health"
        res = requests.get(url, timeout=1.5)
        if res.status_code == 200:
            data = res.json()
            vlm_server_alive = data.get("status") == "ok"
            vlm_last_error = data.get("last_error")
    except Exception:
        vlm_server_alive = False

    # GLM (Local VLM)
    glm_available = vlm_server_alive
    glm_reason = None if glm_available else "Local VLM server (port 2322) unavailable or initializing"

    # DeepSeek (Local VLM)
    deepseek_available = vlm_server_alive
    deepseek_reason = None
    if not vlm_server_alive:
        deepseek_available = False
        deepseek_reason = "Local VLM server (port 2322) unavailable or initializing"
    elif vlm_last_error and any(err_kw in str(vlm_last_error).lower() for err_kw in ["cuda", "vram", "moe", "out of memory"]):
        deepseek_available = False
        deepseek_reason = f"DeepSeek VLM degraded: {vlm_last_error}"

    engines = [
        {
            "id": "dobkle_cloud",
            "name": "☁️ DOBKLE Cloud OCR (AGY Server)",
            "category": "cloud",
            "status": "available",
            "available": True,
            "reason": None,
        },
        {
            "id": "gemini",
            "name": "DOBKLE OCR (Gemini 3.6 Flash)",
            "category": "cloud",
            "status": "available",
            "available": True,
            "reason": None,
        },
        {
            "id": "glm",
            "name": "GLM-OCR (VLM)",
            "category": "local_vlm",
            "status": "available" if glm_available else "disabled",
            "available": glm_available,
            "reason": glm_reason,
        },
        {
            "id": "deepseek",
            "name": "DeepSeek-OCR (VLM)",
            "category": "local_vlm",
            "status": "available" if deepseek_available else "disabled",
            "available": deepseek_available,
            "reason": deepseek_reason,
        },
        {
            "id": "rapidocr",
            "name": "RapidOCR (DirectML GPU / PP-OCRv5)",
            "category": "local_offline",
            "status": "available",
            "available": True,
            "reason": None,
        },
        {
            "id": "ppocrv5",
            "name": "RapidOCR (Local PP-OCRv5 Engine)",
            "category": "local_offline",
            "status": "available",
            "available": True,
            "reason": None,
        },
        {
            "id": "paddleocr",
            "name": "PaddleOCR (Local ONNX Engine)",
            "category": "local_offline",
            "status": "available",
            "available": True,
            "reason": None,
        },
    ]

    return {"engines": engines}


@router.get("/vlm-server/status")
def get_vlm_server_status():
    """Get detailed status of the local GLM / DeepSeek VLM PyTorch server (port 2322)."""
    from app.config import OCR_SERVER_DIR, OCR_HOST, OCR_PORT
    venv_py = OCR_SERVER_DIR / "venv" / "Scripts" / "python.exe"
    is_installed = venv_py.exists()
    
    is_running = False
    model_id = None
    try:
        res = requests.get(f"http://{OCR_HOST}:{OCR_PORT}/health", timeout=1.5)
        if res.status_code == 200:
            is_running = True
            data = res.json()
            model_id = data.get("model")
    except Exception:
        is_running = False

    return {
        "installed": is_installed,
        "running": is_running,
        "port": OCR_PORT,
        "model": model_id,
        "installer_script": str(OCR_SERVER_DIR / "install_vlm_server.bat"),
    }


@router.post("/vlm-server/install")
def launch_vlm_server_installer():
    """Launches the VLM Server setup CMD terminal for PyTorch GLM-4V / DeepSeek installation."""
    import subprocess
    import os
    from app.config import OCR_SERVER_DIR
    bat_file = OCR_SERVER_DIR / "install_vlm_server.bat"
    if not bat_file.exists():
        raise HTTPException(status_code=404, detail="install_vlm_server.bat not found.")
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", str(bat_file)],
            cwd=str(OCR_SERVER_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
        )
        return {"success": True, "message": "VLM Server installer window opened in CMD."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch installer: {e}")


@router.post("/vlm-server/start")
def start_vlm_server():
    """Starts the local VLM server background process."""
    from app.ocr_manager import ocr_manager
    ocr_manager.start_server()
    return {"success": True, "message": "VLM Server start initiated."}


@router.post("/pipeline/train")
def run_train(epochs: int = 10, _admin=Depends(require_admin)):
    if model_trainer.is_training:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Training is already in progress."
        )
    try:
        model_trainer.start_training(epochs=epochs)
        return {"status": "success", "message": f"Training started in background ({epochs} epochs)."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training: {e}"
        )

@router.get("/pipeline/train/status")
def get_train_status(_admin=Depends(require_admin)):
    return model_trainer.get_status()

@router.post("/pipeline/detect")
def run_detect(
    payload: Optional[DetectPipelineRequest] = Body(None),
    page_id: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None),
    force: bool = Query(False),
    backend: Optional[str] = Query(None),
    balloon_model: Optional[str] = Query(None),
    promote_with_ocr: bool = Query(False),
    db: Session = Depends(get_db),
):
    pid = (payload.page_id if payload and payload.page_id else None) or page_id
    if not pid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_id is required")
    min_conf = (payload.min_confidence if payload and payload.min_confidence is not None else None) or min_confidence
    force_val = (payload.force if payload and payload.force is not None else False) or force
    backend_val = (payload.backend if payload and payload.backend else None) or backend
    balloon_model_val = (payload.balloon_model if payload and payload.balloon_model else None) or balloon_model
    promote_val = (payload.promote_with_ocr if payload and payload.promote_with_ocr is not None else False) or promote_with_ocr

    page = db.query(Page).filter(Page.id == pid).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
        
    try:
        has_imported_text = any((block.translation or "").strip() for block in page.text_blocks)
        if has_imported_text and not force_val:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Detection blocked because this page contains imported translations. Use force=true only if replacing them is intentional.",
            )
        gpu_ep = get_execution_provider_setting(page.project.settings if page.project else None)
        selected_model = balloon_model_val or (page.project.settings.get("balloon_model") if page.project and page.project.settings else None)
        def check_cancel() -> bool:
            return bool(page_jobs.get(pid, {}).get("cancel_requested")) or bool(batch_jobs.get(page.project_id, {}).get("cancel_requested"))
        blocks_data = balloon_detector.detect(page.source_image_path, min_confidence=min_conf, execution_provider=gpu_ep, model_name=selected_model, cancel_check=check_cancel)
        if check_cancel():
            logger.info("Detection cancelled for page %s", pid)
            return {"status": "cancelled", "message": "Detection cancelled by user"}

        from app.utils.image_utils import cv2_imread_unicode
        detection_image = cv2_imread_unicode(page.source_image_path)
        if detection_image is None:
            raise ValueError(f"Could not load detection image: {page.source_image_path}")

        # Replace only after inference succeeds. This makes repeated detection
        # idempotent and avoids destroying the current page on model failure.
        db.query(TextBlock).filter(TextBlock.page_id == pid).delete(
            synchronize_session=False
        )

        from app.services.detector import compute_smart_balloon_bounds
        from app.config import get_enable_smart_balloon, get_smart_balloon_inset_ratio

        proj_settings = page.project.settings or {}
        enable_smart = get_enable_smart_balloon(proj_settings)
        inset_ratio = get_smart_balloon_inset_ratio(proj_settings)

        for idx, block in enumerate(blocks_data):
            if check_cancel():
                logger.info("Detection block processing cancelled for page %s", page_id)
                break
            text_bbox = {
                "x": block["x"],
                "y": block["y"],
                "width": block["width"],
                "height": block["height"],
            }
            layout_region = analyze_layout_region(detection_image, block)

            final_x = float(block["x"])
            final_y = float(block["y"])
            final_w = float(block["width"])
            final_h = float(block["height"])

            smart_x = None
            smart_y = None
            smart_w = None
            smart_h = None
            smart_res = {}

            if enable_smart:
                rival_boxes = [b for j, b in enumerate(blocks_data) if j != idx]
                smart_res = compute_smart_balloon_bounds(
                    detection_image, block, rival_boxes=rival_boxes, inset_ratio=inset_ratio,
                    settings=proj_settings,
                )
                smart_x = smart_res.get("smart_x")
                smart_y = smart_res.get("smart_y")
                smart_w = smart_res.get("smart_width")
                smart_h = smart_res["smart_height"] if "smart_height" in smart_res else None

            if enable_smart and smart_res.get("success") and smart_x is not None and smart_w is not None and smart_w > 10.0:
                final_x = float(smart_x)
                final_y = float(smart_y)
                final_w = float(smart_w)
                final_h = float(smart_h)
                layout_region = {
                    "x": float(smart_x),
                    "y": float(smart_y),
                    "width": float(smart_w),
                    "height": float(smart_h),
                    "shape": str(smart_res.get("archetype", "bubble")).lower(),
                    "source": "smart_balloon_v15",
                    "confidence": 0.95,
                    "version": "1.0.0",
                }

            block_metadata = {
                "text_bbox": text_bbox,
                "layout_region": layout_region,
                "detection_class": block.get("detection_class", "text"),
                "detected_balloon_type": block["balloon_type"],
                "layer_origin": "auto_detection",
                "text_evidence_state": "pending",
            }
            if enable_smart and smart_res.get("success"):
                block_metadata["smart_balloon"] = {
                    "archetype": smart_res.get("archetype", "UNKNOWN"),
                    "method": smart_res.get("method", "smart_balloon_v15"),
                    "safe_bbox": smart_res.get("safe_bbox"),
                    "raw_bbox": smart_res.get("raw_bbox"),
                    "center": smart_res.get("center"),
                    "contour_points": smart_res.get("contour_points"),
                    "raw_contour_points": smart_res.get("raw_contour_points"),
                    "row_width_constraints": smart_res.get("row_width_constraints"),
                    "metadata": smart_res.get("metadata", {}),
                }

            # Extract text color and stroke style directly from original source image crop
            extracted_color_hex = block.get("color_hex")
            try:
                from app.services.smart_balloon import extract_balloon_text_style
                tb_x = int(round(final_x))
                tb_y = int(round(final_y))
                tb_w = int(round(final_w))
                tb_h = int(round(final_h))
                style_info = extract_balloon_text_style(detection_image, (tb_x, tb_y, tb_w, tb_h))
                detected_fg = style_info.get("text_color")
                if detected_fg and detected_fg.startswith("#"):
                    extracted_color_hex = detected_fg
                    block_metadata["detected_color_hex"] = detected_fg
                if style_info.get("stroke_color"):
                    block_metadata["stroke_color"] = style_info.get("stroke_color")
                    block_metadata["stroke_width"] = style_info.get("stroke_width", 0)
            except Exception as exc:
                logger.debug("Color extraction error: %s", exc)

            db_block = TextBlock(
                page_id=page_id,
                block_index=idx,
                x=final_x,
                y=final_y,
                width=final_w,
                height=final_h,
                smart_x=smart_x,
                smart_y=smart_y,
                smart_width=smart_w,
                smart_height=smart_h,
                rotation_deg=block["rotation_deg"],
                font_family=block.get("font_family"),
                font_size=block.get("font_size"),
                color_hex=extracted_color_hex or "#000000",
                text_align=block.get("text_align"),
                bold=block.get("bold"),
                italic=block.get("italic"),
                balloon_type=block["balloon_type"],
                confidence=block["confidence"],
                source_text=block.get("text") or "",
                translation="",
                extra_metadata=block_metadata,
            )
            apply_default_text_template(db_block, page.project.settings or {})
            db.add(db_block)

            # Save smart mask asset if crop_mask exists
            if enable_smart and "crop_mask" in smart_res and smart_res["crop_mask"] is not None:
                page_dir = Path(page.source_image_path).parent
                masks_dir = page_dir / "masks"
                masks_dir.mkdir(parents=True, exist_ok=True)
                mask_file = masks_dir / f"smart_balloon_{db_block.id}.png"
                
                # Create full page mask from crop mask
                full_mask = np.zeros(detection_image.shape[:2], dtype=np.uint8)
                sx0, sy0 = smart_res["crop_offset"]
                cm = smart_res["crop_mask"]
                full_mask[sy0:sy0+cm.shape[0], sx0:sx0+cm.shape[1]] = cm
                
                cv2_imwrite_unicode(str(mask_file), full_mask)
                db_block.smart_mask_path = str(mask_file)
                layout_region = dict(layout_region)
                layout_region["mask_path"] = str(mask_file)
                layout_region["mask_area"] = int(np.count_nonzero(full_mask))
                layout_region["contour_version"] = "1.0.0"
                block_metadata = dict(db_block.extra_metadata or {})
                block_metadata["layout_region"] = layout_region
                db_block.extra_metadata = block_metadata

        db.commit()

        if promote_with_ocr:
            evidence = run_ocr(page_id, backend=backend, force=True, db=db)
            return {
                "status": "success",
                "detected_blocks_count": len(blocks_data),
                "promoted_blocks_count": evidence["ocr_updated_blocks_count"],
                "pruned_blocks_count": evidence["pruned_blocks_count"],
                "review_blocks_count": evidence["review_blocks_count"],
            }
        else:
            return {
                "status": "success",
                "detected_blocks_count": len(blocks_data),
                "promoted_blocks_count": len(blocks_data),
                "pruned_blocks_count": 0,
                "review_blocks_count": 0,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Detection failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Detection failed: {e}"
        )

def clean_ocr_text(text: str, source_lang: str, settings: dict) -> str:
    import re
    cleaned = text

    # 1. Strip furigana (parenthesized readings following kanji/kana)
    if settings.get("strip_furigana", False):
        cleaned = re.sub(r'(?<=[\u4e00-\u9fff])(?:（[ぁ-んァ-ヶ]+）|\([ぁ-んァ-ヶ]+\))', '', cleaned)
        
    # 2. Auto remove line breaks
    if settings.get("auto_remove_line_breaks", True):
        if source_lang in ["ja", "zh", "ko"]:
            cleaned = cleaned.replace("\r", "").replace("\n", "")
        else:
            cleaned = cleaned.replace("\r", "").replace("\n", " ")
            cleaned = " ".join(cleaned.split())
            
    # 3. Remove spaces (CJK)
    if settings.get("remove_spaces", True):
        if source_lang in ["ja", "zh", "ko"]:
            cleaned = "".join(cleaned.split())
            
    # 4. Use Chinese punctuation
    if settings.get("use_chinese_punctuation", False):
        punct_map = {
            ',': '，', '.': '。', '?': '？', '!': '！',
            ':': '：', ';': '；', '(': '（', ')': '）'
        }
        cleaned = "".join(punct_map.get(c, c) for c in cleaned)
        
    return cleaned


def classify_ocr_text_evidence(ocr_text: str, success: bool) -> tuple[str, str]:
    """Return (state, reason) for promotion of an auto-detected candidate."""
    if not success:
        return "needs_review", "ocr_failed"
    compact = "".join((ocr_text or "").split())
    if not compact:
        return "reject", "empty_ocr"
    # Ellipsis, dots, bars, decorative punctuation and other non-alphanumeric
    # output are not enough evidence to create a Text Layer.
    if not any(char.isalnum() for char in compact):
        return "reject", "punctuation_only"
    return "confirmed", "valid_text"


def _auto_candidate_can_be_pruned(block: TextBlock) -> bool:
    metadata = dict(block.extra_metadata or {})
    region = metadata.get("layout_region") if isinstance(metadata.get("layout_region"), dict) else {}
    is_auto = (
        metadata.get("layer_origin") == "auto_detection"
        or bool(metadata.get("detected_balloon_type"))
    )
    return bool(
        is_auto
        and region.get("source") != "manual"
        and not (block.translation or "").strip()
        and not (block.source_text or "").strip()
    )


def _apply_source_font_estimate(block: TextBlock, ocr_text: str, source_lang: str) -> None:
    meta = block.extra_metadata or {}
    # Do NOT mutate font_size if user explicitly set font_size or disabled auto_font_size
    if meta.get("font_size_mode") in ("manual", "fixed") or meta.get("auto_font_size") is False:
        return
    if block.font_size and block.font_size > 0 and meta.get("font_size_user_set", False):
        return

    raw_lines = [line.strip() for line in ocr_text.split("\n") if line.strip()]
    num_lines = len(raw_lines)
    total_chars = len(ocr_text.replace("\n", "").strip())
    if num_lines <= 0 or total_chars <= 0:
        return
    is_source_cjk = source_lang in ("ja", "zh", "ko")
    avg_chars = max(1.0, total_chars / num_lines)
    if is_source_cjk:
        estimated_size = min(
            (block.width / num_lines) * 0.85,
            (block.height / avg_chars) * 0.95,
        )
    else:
        estimated_size = min(
            (block.height / num_lines) * 0.85,
            (block.width / avg_chars) * 0.95,
        )
    if not block.font_size or block.font_size <= 0:
        block.font_size = max(12.0, min(120.0, estimated_size))


def _process_ocr_evidence_results(
    results: list,
    project: Project,
    db: Session,
) -> dict[str, int]:
    settings = project.settings or {}
    vertical_to_horizontal = bool(settings.get("vertical_to_horizontal", False))
    updated_count = 0
    pruned_count = 0
    review_count = 0

    for block, ocr_text, success in results:
        state, reason = classify_ocr_text_evidence(ocr_text, success)
        metadata = dict(block.extra_metadata or {})
        metadata["text_evidence_state"] = state
        metadata["text_evidence_reason"] = reason

        if state == "reject" or state == "needs_review":
            metadata["text_evidence_state"] = state
            metadata["text_evidence_reason"] = reason
            block.extra_metadata = metadata
            review_count += 1
            continue

        cleaned = clean_ocr_text(ocr_text or "", project.source_lang, settings)
        if cleaned:
            block.source_text = cleaned
            _apply_source_font_estimate(block, ocr_text, project.source_lang)
            if vertical_to_horizontal:
                block.text_direction = "horizontal"
            
            # Map balloon_type to Client Font Template (AI Font Judge)
            text_templates = settings.get("text_templates") or {}
            b_type = (block.balloon_type or "bubble").lower()
            if b_type == "narration":
                b_type = "narrative"
            template = text_templates.get(b_type) or text_templates.get("bubble")
            if template and isinstance(template, dict):
                font_stack = template.get("font_stack") or []
                if font_stack and font_stack[0]:
                    block.font_family = str(font_stack[0]).strip()
                elif template.get("font_family"):
                    block.font_family = str(template.get("font_family")).strip()
            
            updated_count += 1
        block.extra_metadata = metadata

    return {
        "updated": updated_count,
        "pruned": pruned_count,
        "review": review_count,
    }


def _reindex_page_blocks(page_id: str, db: Session) -> None:
    remaining = (
        db.query(TextBlock)
        .filter(TextBlock.page_id == page_id)
        .order_by(TextBlock.block_index)
        .all()
    )
    for index, block in enumerate(remaining):
        block.block_index = index

@router.post("/pipeline/ocr")
def run_ocr(
    payload: Optional[OcrPipelineRequest] = Body(None),
    page_id: Optional[str] = Query(None),
    backend: Optional[str] = Query(None),
    force: bool = Query(False),
    block_ids: Optional[Any] = Query(None),
    source_lang: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    cancel_check: Any = None,
):
    pid = (payload.page_id if payload and payload.page_id else None) or page_id
    if not pid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_id is required")
    backend_val = (payload.backend if payload and payload.backend else None) or backend
    force_val = (payload.force if payload and payload.force is not None else False) or force
    
    raw_bids = (payload.block_ids if payload and payload.block_ids is not None else None) or block_ids
    if isinstance(raw_bids, list):
        bids_str = ",".join(str(x) for x in raw_bids)
    elif isinstance(raw_bids, str):
        bids_str = raw_bids
    else:
        bids_str = None
    lang_val = (payload.source_lang if payload and payload.source_lang else None) or source_lang

    page = db.query(Page).filter(Page.id == pid).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
        
    try:
        project = page.project
        effective_lang = str(
            lang_val
            or getattr(project, "source_lang", None)
            or (project.settings or {}).get("source_lang")
            or "zh"
        ).strip().lower()
        
        # Parallel OCR execution (only targets empty blocks unless force is True, or specific block_ids are provided)
        if bids_str:
            target_ids = [bid.strip() for bid in bids_str.split(",") if bid.strip()]
            ocr_targets = [b for b in page.text_blocks if b.id in target_ids]
        else:
            ocr_targets = list(page.text_blocks) if force_val else ([b for b in page.text_blocks if not b.source_text] or list(page.text_blocks))
            
        if ocr_targets:
            from app.services.gemini_quota import get_quota_status
            from app.services.performance import resolve_performance_settings
            
            if backend_val and any(b in str(backend_val).lower() for b in ("gemini", "ai", "agy")):
                quota_st = get_quota_status()
                if quota_st.get("quota_exceeded"):
                    reason = quota_st.get("reason") or "HTTP 429 Rate Limit Exceeded"
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"❌ โควตา Gemini API Key เต็ม/หมดชั่วคราว ({reason}) - ยกเลิกการทำ OCR ทันทีเพื่อป้องกันระบบค้าง"
                    )
            
            performance = resolve_performance_settings(page.project.settings or {})
            if bids_str and len(ocr_targets) == 1:
                # Explicit single-layer OCR is intentionally the lightweight
                # normal path. Composite grid OCR is reserved for page/pipeline
                # work where all detected balloons are already persisted.
                target = ocr_targets[0]
                # Re-read block from DB to pick up any geometry changes that
                # may have been committed by the frontend just before this
                # request (e.g. the user resized the balloon then clicked OCR).
                db.refresh(target)
                import logging
                logging.getLogger(__name__).info(
                    "OCR crop block %s: x=%.1f y=%.1f w=%.1f h=%.1f",
                    target.id, target.x, target.y, target.width, target.height,
                )
                ocr_text, ocr_success = crop_and_ocr_block(
                    page.source_image_path,
                    target,
                    backend=backend_val,
                    source_lang=effective_lang,
                )
                results = [(target, ocr_text, ocr_success)]
            else:
                # Refresh all targets to pick up latest geometry from DB
                for t in ocr_targets:
                    db.refresh(t)
                results = crop_and_ocr_blocks_parallel(
                    page.source_image_path,
                    ocr_targets,
                    max_workers=performance.ocr_workers,
                    backend=backend_val,
                    source_lang=effective_lang,
                    cancel_check=cancel_check,
                )
        else:
            results = []
        
        evidence = _process_ocr_evidence_results(results, project, db)
            
        db.flush()
        
        # Re-index remaining blocks sequentially
        _reindex_page_blocks(pid, db)
            
        db.commit()

        failed_block_ids = [str(block.id) for block, _text, success in results if not success]
        return {
            "status": "success", 
            "ocr_updated_blocks_count": evidence["updated"],
            "pruned_blocks_count": evidence["pruned"],
            "review_blocks_count": evidence["review"],
            "ocr_failed_blocks_count": len(failed_block_ids),
            "ocr_failed_block_ids": failed_block_ids,
            "ocr_backend": backend_val or get_ocr_engine(project.settings or {}),
        }
    except Exception as e:
        logger.exception("OCR failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR step failed: {e}"
        )


@router.post("/pipeline/mask")
def run_mask(
    payload: Optional[MaskPipelineRequest] = Body(None),
    page_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    pid = (payload.page_id if payload and payload.page_id else None) or page_id
    if not pid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_id is required")
    try:
        page = db.query(Page).filter(Page.id == pid).first()
        if page and len(page.text_blocks) == 0:
            run_detect(page_id=pid, db=db)
        from app.services.inpainter import generate_page_mask_only
        generate_page_mask_only(pid, db)
        return {"status": "success", "message": "Mask generation completed"}
    except Exception as e:
        logger.exception("Mask generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mask generation failed: {e}"
        )


@router.post("/pipeline/inpaint")
def run_inpaint(
    payload: Optional[InpaintPipelineRequest] = Body(None),
    page_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    pid = (payload.page_id if payload and payload.page_id else None) or page_id
    if not pid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_id is required")
    try:
        page = db.query(Page).filter(Page.id == pid).first()
        if page and len(page.text_blocks) == 0:
            run_detect(page_id=pid, db=db)
        clean_page_text(pid, db)
        return {"status": "success", "message": "Inpaint clean completed"}
    except Exception as e:
        logger.exception("Inpaint failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inpainting step failed: {e}"
        )


class SpotHealRequest(BaseModel):
    page_id: str
    mask_base64: Optional[str] = None
    bbox: Optional[list[int]] = None
    stroke_points: Optional[list[dict[str, float]]] = None
    brush_size: Optional[int] = 24


@router.post("/pipeline/spot-heal")
def run_spot_heal(req: SpotHealRequest, db: Session = Depends(get_db)):
    """
    Sub-region contextual spot healing on active canvas strokes.
    Applies high-speed patch inpainting only around the painted stroke area.
    """
    from app.services.inpainter import inpaint_subregion_patch
    from app.services.project_paths import inpainted_asset_path, page_asset_dir, page_asset_key

    page = db.query(Page).filter(Page.id == req.page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Resolve base image (prioritize existing cleaned image, fallback to source)
    clean_path = inpainted_asset_path(page)
    if clean_path.exists():
        img = cv2_imread_unicode(str(clean_path))
    else:
        img = cv2_imread_unicode(str(page.source_image_path))

    if img is None:
        raise HTTPException(status_code=500, detail="Failed to load page image")

    ih, iw = img.shape[:2]
    mask = np.zeros((ih, iw), dtype=np.uint8)

    # 1. Reconstruct mask from base64 or stroke_points
    if req.mask_base64:
        try:
            raw_b64 = req.mask_base64.split(",")[-1]
            mask_bytes = base64.b64decode(raw_b64)
            nparr = np.frombuffer(mask_bytes, np.uint8)
            decoded_mask = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if decoded_mask is not None:
                if decoded_mask.shape[:2] != (ih, iw):
                    decoded_mask = cv2.resize(decoded_mask, (iw, ih), interpolation=cv2.INTER_NEAREST)
                mask = decoded_mask
        except Exception as e:
            logger.warning("Failed to decode mask_base64: %s", e)

    elif req.stroke_points and len(req.stroke_points) >= 1:
        brush_r = max(4, int(req.brush_size or 24) // 2)
        pts = [(int(p["x"]), int(p["y"])) for p in req.stroke_points]
        for i in range(len(pts)):
            cv2.circle(mask, pts[i], brush_r, 255, -1)
            if i > 0:
                cv2.line(mask, pts[i - 1], pts[i], 255, brush_r * 2)

    elif req.bbox and len(req.bbox) == 4:
        bx, by, bw, bh = req.bbox
        mask[max(0, by):min(ih, by + bh), max(0, bx):min(iw, bx + bw)] = 255

    if np.count_nonzero(mask) == 0:
        return {"status": "noop", "message": "Empty mask provided"}

    # 2. Run high-speed contextual patch inpaint
    bbox_tuple = tuple(req.bbox) if req.bbox and len(req.bbox) == 4 else None
    patched_img, patch_bounds = inpaint_subregion_patch(img, mask, bbox=bbox_tuple, padding=48)

    # 3. Save patched output to clean asset path
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    cv2_imwrite_unicode(str(clean_path), patched_img)
    page.inpainted_image_path = str(clean_path)
    db.commit()

    # Clear memory cache for this page image
    try:
        page_image_cache.invalidate(str(page.id))
    except Exception:
        pass

    # Encode patched subregion as base64 for ultra-fast optimistic frontend update
    px0, py0, px1, py1 = patch_bounds
    patch_crop = patched_img[py0:py1, px0:px1]
    _, buf = cv2.imencode(".jpg", patch_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    patch_b64 = base64.b64encode(buf).decode("utf-8")

    return {
        "status": "success",
        "patch_bounds": {"x0": px0, "y0": py0, "x1": px1, "y1": py1},
        "patch_base64": f"data:image/jpeg;base64,{patch_b64}",
        "inpainted_image_path": str(clean_path),
    }


class ExtractStyleRequest(BaseModel):
    page_id: str
    bbox: list[int]
    block_id: Optional[str] = None


@router.post("/pipeline/extract-style")
def run_extract_style(req: ExtractStyleRequest, db: Session = Depends(get_db)):
    """
    Auto-extracts text color, background color, stroke width, and angle for a balloon.
    """
    from app.services.smart_balloon import extract_balloon_text_style

    page = db.query(Page).filter(Page.id == req.page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    img = cv2_imread_unicode(str(page.source_image_path))
    if img is None:
        raise HTTPException(status_code=500, detail="Failed to load page image")

    if len(req.bbox) != 4:
        raise HTTPException(status_code=400, detail="Invalid bbox, expected [x, y, w, h]")

    style = extract_balloon_text_style(img, tuple(req.bbox))

    # If block_id is provided, optionally persist to text block model
    if req.block_id:
        block = db.query(TextBlock).filter(TextBlock.id == req.block_id).first()
        if block:
            block.color_hex = style["text_color"]
            if style.get("has_stroke") and style.get("stroke_color"):
                block.stroke_color = style["stroke_color"]
                block.stroke_width = style["stroke_width"]
            db.commit()

    return {"status": "success", "style": style}


@router.delete("/pipeline/masks")
@router.delete("/projects/{project_id}/masks")
@router.delete("/pages/{page_id}/masks")
@router.delete("/pages/{page_id}/mask")
def reset_masks(page_id: str | None = None, project_id: str | None = None, db: Session = Depends(get_db)):
    """Remove custom masks and stale clean outputs for one page or a whole project."""
    if bool(page_id) == bool(project_id):
        raise HTTPException(status_code=400, detail="Provide exactly one of page_id or project_id")
    pages = (
        db.query(Page).filter(Page.id == page_id).all()
        if page_id else db.query(Page).filter(Page.project_id == project_id).all()
    )
    removed = 0
    for page in pages:
        page_dir = Path(page.source_image_path).parent
        from app.services.project_paths import page_asset_dir, page_asset_key
        external_masks = page_asset_dir(page, "masks")
        external_clean = page_asset_dir(page, "clean")
        asset_key = page_asset_key(page)
        asset_patterns = (
            (page_dir, "mask_*.png"),
            (page_dir, "manual_mask.png"),
            (page_dir, "inpainted.png"),
            (page_dir, "preview_inpainted.jpg"),
            (page_dir / "masks", "*.png"),
            (page_dir / "clean", "*.png"),
            (page_dir / "clean", "*.jpg"),
            (external_masks, f"{asset_key}_*.png"),
            (external_clean, f"{asset_key}_*.png"),
            (external_clean, f"{asset_key}_*.jpg"),
            (external_masks / asset_key, "*.png"),
            (external_clean / asset_key, "*.png"),
            (external_clean / asset_key, "*.jpg"),
        )
        seen_paths = set()
        for asset_dir, pattern in asset_patterns:
            if not asset_dir.exists():
                continue
            for path in asset_dir.glob(pattern):
                resolved = path.resolve()
                if path.is_file() and resolved not in seen_paths:
                    path.unlink()
                    seen_paths.add(resolved)
                    removed += 1
        invalidate_clean_assets(page)
    db.commit()
    return {"status": "success", "scope": "page" if page_id else "project", "removed": removed}

@router.post("/pipeline/render")
def run_render(page_id: str, db: Session = Depends(get_db)):
    try:
        render_page_text(page_id, db)
        return {"status": "success", "message": "Render text completed"}
    except Exception as e:
        logger.exception("Rendering failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text rendering step failed: {e}"
        )


@router.post("/pipeline/style-judge")
def run_style_judge(page_id: str, db: Session = Depends(get_db)):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Page not found"
        )

    project_settings = page.project.settings if page.project else {}
    evaluated = 0
    applied = 0
    descriptors_map = judge_page_styles_batch_ai(
        page.text_blocks, project_settings=project_settings, page_height=page.height, model="flash_3.6"
    )
    for block in page.text_blocks:
        b_id = str(block.id)
        if b_id not in descriptors_map:
            continue
        desc = descriptors_map[b_id]
        res = apply_style_descriptor_to_block(
            block,
            desc,
            project_settings=project_settings,
            apply_template=True,
            confidence_auto_threshold=0.0,
        )
        evaluated += 1
        if res.get("applied"):
            applied += 1
        spec = compute_block_typesetting(block)
        persist_typesetting_spec(block, spec)

    db.commit()
    return {
        "status": "success",
        "page_id": page_id,
        "evaluated_blocks": evaluated,
        "applied_blocks": applied,
    }



@router.get("/pages/{page_id}/render-contract")
def get_render_contract(
    page_id: str,
    background_kind: str = "clean",
    db: Session = Depends(get_db),
):
    """Return a short-lived contract for a Fabric/Chromium render capture."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    try:
        revision = page_render_revision(page, background_kind)
    except BrowserRenderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {
        "page_id": page.id,
        "width": page.width,
        "height": page.height,
        "background_kind": background_kind,
        "revision": revision,
        "engine": "fabric-browser-v1",
    }


@router.put("/pages/{page_id}/rendered-overlay")
async def upload_rendered_overlay(
    page_id: str,
    file: UploadFile = File(...),
    revision: str = Form(...),
    background_kind: str = Form("clean"),
    db: Session = Depends(get_db),
):
    """Validate and composite a transparent overlay produced by the live editor."""
    if file.content_type not in {"image/png", "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Render overlay must use image/png",
        )

    payload = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > MAX_BROWSER_RENDER_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Render overlay exceeds the 128 MiB upload limit",
            )

    try:
        output_path = save_browser_render(
            page_id=page_id,
            overlay_bytes=bytes(payload),
            revision=revision,
            background_kind=background_kind,
            db=db,
        )
        return {
            "status": "success",
            "page_id": page_id,
            "engine": "fabric-browser-v1",
            "path": str(output_path),
        }
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except StaleBrowserRenderError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except BrowserRenderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("Browser render upload failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Browser render upload failed: {exc}",
        )


@router.post("/pipeline/layout")
def run_layout(page_id: str, db: Session = Depends(get_db)):
    """Refresh balloon-safe regions and canonical typesetting specs for a page."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    try:
        from sqlalchemy.orm.attributes import flag_modified
        from app.services.layout_region import refresh_block_layout_regions

        blocks = list(page.text_blocks)
        refresh_block_layout_regions(blocks)
        needs_review = 0
        for block in blocks:
            spec = compute_block_typesetting(block)
            persist_typesetting_spec(block, spec)
            flag_modified(block, "extra_metadata")
            gate = spec.metrics.get("quality_gate", {})
            needs_review += int(bool(gate.get("needs_review")))
        db.commit()
        return {
            "status": "success",
            "updated_blocks_count": len(blocks),
            "needs_review_count": needs_review,
        }
    except Exception as e:
        db.rollback()
        logger.exception("Layout analysis failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Layout analysis failed: {e}",
        )

@router.post("/pipeline/sort")
def run_sort(page_id: str, db: Session = Depends(get_db)):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    try:
        sorted_blocks = sorted(page.text_blocks, key=lambda b: (b.y, b.x))
        for idx, block in enumerate(sorted_blocks):
            block.block_index = idx
        db.commit()
        return {"status": "success", "message": f"Sorted {len(sorted_blocks)} layers"}
    except Exception as e:
        logger.exception("Sorting failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sorting failed: {e}"
        )


@router.post("/pipeline/auto")
def run_auto(page_id: str, min_confidence: float = None, backend: Optional[str] = None, db: Session = Depends(get_db)):
    """
    One-Click Full Pipeline: runs detect -> OCR -> inpaint sequentially.
    """
    try:
        # 1. Detect
        detect_res = run_detect(
            page_id=page_id,
            min_confidence=min_confidence,
            backend=backend,
            promote_with_ocr=False,
            db=db,
        )
        # 2. OCR
        ocr_res = run_ocr(page_id=page_id, backend=backend, db=db)
        # 3. Inpaint
        inpaint_res = run_inpaint(page_id=page_id, db=db)
        
        return {
            "status": "success",
            "detected_blocks_count": detect_res["detected_blocks_count"],
            "ocr_updated_blocks_count": ocr_res["ocr_updated_blocks_count"],
            "pruned_blocks_count": ocr_res["pruned_blocks_count"]
        }
    except Exception as e:
        logger.exception("Auto pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto pipeline failed: {e}"
        )

def _plan_resumable_page_pipeline(
    page: Page,
    clean_current: bool,
    requested_steps: set[str] | None = None,
) -> list[str]:
    """Return only the stages needed to bring a page up to date."""
    blocks = list(page.text_blocks or [])
    stages: list[str] = []
    if not blocks:
        stages.append("detect")
        stages.append("ocr")
    elif any(not (block.source_text or "").strip() for block in blocks):
        stages.append("ocr")
    if not clean_current:
        stages.append("inpaint")
    if requested_steps is not None:
        stages = [stage for stage in stages if stage in requested_steps]
    return stages


def run_page_pipeline_task(
    page_id: str,
    project_id: str,
    min_confidence: float = None,
    backend: Optional[str] = None,
    requested_steps: set[str] | None = None,
    source_lang: Optional[str] = None,
    balloon_model: Optional[str] = None,
):
    """
    Background worker task for processing a single page (Timeout Prevention).
    """
    from app.ws_manager import ws_manager
    db_gen = get_db()
    db = next(db_gen)
    try:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise ValueError(f"Page not found: {page_id}")
        queued_job = page_jobs.get(page_id, {})
        page_jobs[page_id] = {
            "status": "running",
            "cancel_requested": bool(queued_job.get("cancel_requested")),
        }
        stages = _plan_resumable_page_pipeline(
            page,
            is_clean_asset_current(page),
            requested_steps=requested_steps,
        )
        for step in stages:
            if page_jobs.get(page_id, {}).get("cancel_requested"):
                page_jobs[page_id]["status"] = "cancelled"
                ws_manager.broadcast_sync(project_id, {
                    "type": "page_progress", "status": "cancelled", "page_id": page_id,
                    "stages": stages,
                })
                return
            ws_manager.broadcast_sync(project_id, {
                "type": "page_progress", "status": "running", "step": step,
                "page_id": page_id, "stages": stages,
            })
            if step == "detect":
                run_detect(
                    page_id=page_id,
                    min_confidence=min_confidence,
                    backend=backend,
                    balloon_model=balloon_model,
                    promote_with_ocr=False,
                    force=True,
                    db=db,
                )
            elif step == "ocr":
                def check_cancel_single():
                    return bool(page_jobs.get(page_id, {}).get("cancel_requested")) or bool(batch_jobs.get(project_id, {}).get("cancel_requested"))
                run_ocr(page_id=page_id, backend=backend, source_lang=source_lang, db=db, cancel_check=check_cancel_single)
            elif step == "inpaint":
                def check_cancel_single():
                    return bool(page_jobs.get(page_id, {}).get("cancel_requested")) or bool(batch_jobs.get(project_id, {}).get("cancel_requested"))
                clean_page_text(page_id, db, cancel_check=check_cancel_single)

            if page_jobs.get(page_id, {}).get("cancel_requested") or batch_jobs.get(project_id, {}).get("cancel_requested"):
                page_jobs[page_id]["status"] = "cancelled"
                ws_manager.broadcast_sync(project_id, {
                    "type": "page_progress", "status": "cancelled", "page_id": page_id,
                    "stages": stages,
                })
                return

        page_jobs[page_id]["status"] = "success"
        ws_manager.broadcast_sync(project_id, {
            "type": "page_progress", "status": "success", "page_id": page_id,
            "stages": stages, "already_current": not stages,
        })
    except Exception as e:
        if page_jobs.get(page_id, {}).get("cancel_requested") or batch_jobs.get(project_id, {}).get("cancel_requested"):
            logger.info("Single page pipeline task cancelled by user request: %s", e)
            page_jobs[page_id]["status"] = "cancelled"
            ws_manager.broadcast_sync(project_id, {
                "type": "page_progress", "status": "cancelled", "page_id": page_id,
            })
            return
        logger.exception("Single page pipeline failed")
        page_jobs[page_id] = {"status": "error", "error": str(e)}
        ws_manager.broadcast_sync(project_id, {"type": "page_progress", "status": "error", "error": str(e)})
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass

@router.post("/pipeline/auto/background")
def run_auto_background(
    page_id: str,
    project_id: str,
    background_tasks: BackgroundTasks,
    min_confidence: float = None,
    backend: Optional[str] = None,
    steps: Optional[str] = None,
    source_lang: Optional[str] = None,
    balloon_model: Optional[str] = None,
):
    requested_steps = None
    if steps is not None:
        aliases = {"mask": "inpaint", "clean": "inpaint", "balloon": "detect"}
        requested_steps = {
            aliases.get(token.strip().lower(), token.strip().lower())
            for token in steps.split(",")
            if token.strip()
        }
        unsupported = requested_steps - {"detect", "ocr", "inpaint"}
        if unsupported:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported workflow step(s): {', '.join(sorted(unsupported))}")
    for p_id, job in list(page_jobs.items()):
        if p_id != page_id and job.get("status") in {"queued", "running"}:
            job["cancel_requested"] = True
            job["status"] = "cancelled"
    page_jobs[page_id] = {"status": "queued", "cancel_requested": False, "project_id": project_id}
    background_tasks.add_task(run_page_pipeline_task, page_id, project_id, min_confidence, backend, requested_steps, source_lang, balloon_model)
    return {"status": "started"}


@router.post("/pipeline/auto/cancel")
def cancel_auto_background(page_id: Optional[str] = None):
    """
    Cancels active auto pipeline jobs for a page (or all running page jobs if page_id omitted).
    """
    cancelled_any = False
    if page_id:
        job = page_jobs.get(page_id)
        if job and job.get("status") in {"queued", "running"}:
            job["cancel_requested"] = True
            job["status"] = "cancelled"
            cancelled_any = True
            ws_manager.broadcast_sync(job.get("project_id", ""), {
                "type": "page_progress", "status": "cancelled", "page_id": page_id,
            })
    else:
        for p_id, job in page_jobs.items():
            if job.get("status") in {"queued", "running"}:
                job["cancel_requested"] = True
                job["status"] = "cancelled"
                cancelled_any = True
                ws_manager.broadcast_sync(job.get("project_id", ""), {
                    "type": "page_progress", "status": "cancelled", "page_id": p_id,
                })
    if cancelled_any:
        return {"status": "success", "message": "Auto pipeline cancelled successfully."}
    return {"status": "no_action", "message": "No active page workflow to cancel."}

@router.get("/pipeline/inpaint-preview")
def run_inpaint_preview(
    page_id: str,
    block_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns a base64 encoded inpaint preview without saving to disk.

    Supplying ``block_id`` isolates both processing and output to that block;
    this is the contract used by Text Mask Editor's Preview Remove action.
    """
    try:
        preview_img = generate_inpaint_preview(page_id, db, block_id=block_id)
        _, encoded_img = cv2.imencode(".png", preview_img)
        base64_str = base64.b64encode(encoded_img).decode("utf-8")
        return {"status": "success", "image": f"data:image/png;base64,{base64_str}"}
    except Exception as e:
        logger.exception("Inpaint preview failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inpaint preview failed: {e}"
        )


def run_batch_pipeline_task(
    project_id: str,
    steps_str: str = "detect,ocr,inpaint",
    min_confidence: float = None,
    backend: Optional[str] = None,
    source_lang: Optional[str] = None,
    balloon_model: Optional[str] = None,
):
    """
    Background worker task for batch processing of all pages.
    """
    from app.ws_manager import ws_manager
    # Fetch get_db generator inside background thread
    db_gen = get_db()
    db = next(db_gen)
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project or not project.pages:
            batch_jobs[project_id] = {
                "status": "failed", 
                "progress": 1.0, 
                "current_page": 0, 
                "total_pages": 0, 
                "error": "Project or pages not found"
            }
            ws_manager.broadcast_sync(project_id, {
                "type": "batch_progress",
                "status": "failed",
                "progress": 1.0,
                "current_page": 0,
                "total_pages": 0,
                "error": "Project or pages not found"
            })
            return

        effective_lang = str(
            source_lang
            or getattr(project, "source_lang", None)
            or (getattr(project, "settings", {}) or {}).get("source_lang")
            or "zh"
        ).strip().lower()
        selected_model = balloon_model or (getattr(project, "settings", {}) or {}).get("balloon_model")
        pages = project.pages
        total = len(pages)
        batch_jobs[project_id] = {
            "status": "running",
            "progress": 0.0,
            "current_page": 0,
            "total_pages": total,
            "error": None,
            "ocr_failed_targets": [],
        }
        ws_manager.broadcast_sync(project_id, {
            "type": "batch_progress",
            "status": "running",
            "progress": 0.0,
            "current_page": 0,
            "total_pages": total,
            "error": None
        })
        
        # Parse active steps
        active_steps = [s.strip().lower() for s in steps_str.split(",") if s.strip()]
        if not active_steps:
            active_steps = ["detect", "ocr", "inpaint"]
        resume_mode = active_steps == ["resume"]
        supported_steps_set = {
            "resume", "detect", "ocr", "layout", "sort", "mask", "inpaint", "render",
            "font_judge", "style_judge", "filter_empty", "merge_expand", "typeset"
        }
        unsupported_steps = sorted(set(active_steps) - supported_steps_set)
        if unsupported_steps:
            logger.warning(f"Ignored unknown batch pipeline step(s): {', '.join(unsupported_steps)}")
            active_steps = [s for s in active_steps if s in supported_steps_set]
        num_steps = max(1, len(active_steps))
        effective_lang = str(getattr(project, "source_lang", None) or (getattr(project, "settings", {}) or {}).get("source_lang") or "ja").strip().lower()

        # Sort pages by index or filename to process in sequence
        sorted_pages = sorted(pages, key=lambda p: p.page_number)
        
        # Whole-Chapter Multi-Page PDF Gemini OCR Optimization (1 single request for all blocks across all pages)
        is_gemini_backend = backend and any(token in str(backend).lower() for token in ("gemini", "ai", "dobkle", "agy"))
        project_ocr_done = False
        if "ocr" in active_steps and "detect" not in active_steps and is_gemini_backend:
            from app.services.ocr import batch_project_pdf_gemini_ocr
            all_ocr_targets = []
            for p in sorted_pages:
                unscanned = [b for b in p.text_blocks if not b.source_text]
                targets = unscanned if unscanned else list(p.text_blocks)
                for b in targets:
                    all_ocr_targets.append((p, b))
            
            if all_ocr_targets:
                logger.info("🚀 Running Whole-Chapter Multi-Page PDF Gemini OCR in 1 single request for %d blocks across %d pages...", len(all_ocr_targets), len(sorted_pages))
                
                def on_dobkle_stage(phase: str, phase_title: str, message: str, progress: float, completed: int = 0, total: int = 0):
                    ws_manager.broadcast_sync(project_id, {
                        "type": "dobkle_ocr_progress",
                        "status": "running",
                        "phase": phase,
                        "phase_title": phase_title,
                        "message": message,
                        "progress": progress,
                        "completed_blocks": completed,
                        "total_blocks": total or len(all_ocr_targets),
                        "total_pages": len(sorted_pages),
                    })
                    # Also update batch_progress so fallback indicators stay in sync
                    ws_manager.broadcast_sync(project_id, {
                        "type": "batch_progress",
                        "status": "running",
                        "current_page": 1,
                        "total_pages": len(sorted_pages),
                        "step": f"DOBKLE: {phase_title}",
                        "progress": progress,
                    })

                ocr_depth = ((project.settings or {}).get("ocr_depth") or "full").strip().lower()
                ocr_results_map = batch_project_pdf_gemini_ocr(
                    project_name=project.name,
                    all_targets=all_ocr_targets,
                    backend=backend,
                    source_lang=effective_lang,
                    stage_callback=on_dobkle_stage,
                    ocr_depth=ocr_depth,
                )
                if ocr_results_map:
                    proj_settings = project.settings or {}
                    text_templates = proj_settings.get("text_templates") or {}
                    for p, b in all_ocr_targets:
                        if b.id in ocr_results_map:
                            res_item = ocr_results_map[b.id]
                            text_val = res_item.get("text", "") if isinstance(res_item, dict) else str(res_item)
                            cleaned = clean_ocr_text(text_val or "", project.source_lang, proj_settings)
                            if cleaned:
                                b.source_text = cleaned
                                _apply_source_font_estimate(b, cleaned, project.source_lang)
                                if isinstance(res_item, dict):
                                    b_type = res_item.get("balloon_type")
                                    if b_type and str(b_type).lower() in {"bubble", "shout", "narrative", "narration", "sfx", "whisper", "system"}:
                                        b.balloon_type = str(b_type).lower()
                                    c_hex = res_item.get("color_hex")
                                    if c_hex and isinstance(c_hex, str) and c_hex.startswith("#"):
                                        b.color_hex = c_hex
                                    if "bold" in res_item:
                                        b.bold = bool(res_item["bold"])
                                    if "italic" in res_item:
                                        b.italic = bool(res_item["italic"])
                                    s_col = res_item.get("stroke_color_hex") or res_item.get("stroke_color")
                                    s_wid = res_item.get("stroke_width_px") or res_item.get("stroke_width")
                                    g_cols = res_item.get("gradient_colors")
                                    grad_obj = res_item.get("gradient")
                                    shadow_obj = res_item.get("drop_shadow")
                                    glow_obj = res_item.get("outer_glow")
                                    inner_obj = res_item.get("inner_shadow")

                                    meta = dict(b.extra_metadata or {})
                                    if c_hex and isinstance(c_hex, str) and c_hex.startswith("#"):
                                        meta["detected_color_hex"] = c_hex
                                    if "bold" in res_item:
                                        meta["bold"] = bool(res_item["bold"])
                                        meta["detected_bold"] = bool(res_item["bold"])
                                    if "italic" in res_item:
                                        meta["italic"] = bool(res_item["italic"])
                                        meta["detected_italic"] = bool(res_item["italic"])
                                    if s_col and isinstance(s_col, str) and s_col.startswith("#"):
                                        meta["stroke_color"] = s_col
                                    if s_wid is not None:
                                        try:
                                            meta["stroke_width"] = float(s_wid)
                                        except Exception:
                                            pass
                                    if g_cols and isinstance(g_cols, list):
                                        meta["gradient_colors"] = g_cols
                                    if grad_obj and isinstance(grad_obj, dict):
                                        meta["detected_gradient"] = grad_obj
                                    if shadow_obj and isinstance(shadow_obj, dict):
                                        meta["detected_drop_shadow"] = shadow_obj
                                    if glow_obj and isinstance(glow_obj, dict):
                                        meta["detected_outer_glow"] = glow_obj
                                    if inner_obj and isinstance(inner_obj, dict):
                                        meta["detected_inner_shadow"] = inner_obj
                                    b.extra_metadata = meta

                                    # Map balloon_type to Client Font Template (AI Font Judge)
                                    b_type_norm = (b.balloon_type or "bubble").lower()
                                    if b_type_norm == "narration":
                                        b_type_norm = "narrative"
                                    template = text_templates.get(b_type_norm) or text_templates.get("bubble")
                                    if template and isinstance(template, dict):
                                        font_stack = template.get("font_stack") or []
                                        if font_stack and font_stack[0]:
                                            b.font_family = str(font_stack[0]).strip()
                                        elif template.get("font_family"):
                                            b.font_family = str(template.get("font_family")).strip()
                    # Report missed blocks to user — NO auto-fallback to other OCR engines
                    missing_targets = [item for item in all_ocr_targets if not (getattr(item[1], "source_text", None) or "").strip()]
                    if missing_targets:
                        logger.warning("⚠️ %d/%d blocks missed in DOBKLE OCR — no fallback (user can re-run)", len(missing_targets), len(all_ocr_targets))
                        on_dobkle_stage(
                            phase="partial_complete",
                            phase_title="⚠️ บางกล่องไม่สำเร็จ",
                            message=f"สำเร็จ {len(all_ocr_targets) - len(missing_targets)}/{len(all_ocr_targets)} กล่อง — {len(missing_targets)} กล่องต้องรีรันใหม่",
                            progress=0.95,
                            completed=len(all_ocr_targets) - len(missing_targets),
                            total=len(all_ocr_targets),
                        )

                    for p in sorted_pages:
                        _reindex_page_blocks(p.id, db)
                    db.commit()
                    project_ocr_done = True
                    on_dobkle_stage(
                        phase="completed",
                        phase_title="✅ สำเร็จสมบูรณ์ 100%",
                        message=f"ถอดรหัสข้อความและจัดสไตล์สำเร็จครบทั้ง {len(all_ocr_targets)} บอลลูน!",
                        progress=1.0,
                        completed=len(all_ocr_targets),
                        total=len(all_ocr_targets),
                    )
                    logger.info("✅ Whole-Chapter Multi-Page PDF Gemini OCR completed successfully in 1 single request!")

        # Project-Wide AI Font Judge Optimization (1 single AI call for all blocks across all pages)
        project_font_judged = False
        if "font_judge" in active_steps or "style_judge" in active_steps:
            all_project_blocks = [
                b for p in sorted_pages for b in p.text_blocks
                if (getattr(b, "translation", None) or getattr(b, "source_text", None) or "").strip()
            ]
            if all_project_blocks:
                logger.info("Running Project-Wide AI Font Judge in 1 single request for %d blocks across %d pages...", len(all_project_blocks), len(sorted_pages))
                project_settings = project.settings or {}
                descriptors_map = judge_page_styles_batch_ai(
                    all_project_blocks, project_settings=project_settings, model="flash_3.6"
                )
                for block in all_project_blocks:
                    b_id = str(block.id)
                    if b_id in descriptors_map:
                        apply_style_descriptor_to_block(
                            block,
                            descriptors_map[b_id],
                            project_settings=project_settings,
                            apply_template=True,
                            confidence_auto_threshold=0.0,
                        )
                        spec = compute_block_typesetting(block)
                        persist_typesetting_spec(block, spec)
                db.commit()
                project_font_judged = True
                logger.info("Project-Wide AI Font Judge completed successfully in 1 single request!")

        for idx, page in enumerate(sorted_pages):
            if batch_jobs.get(project_id, {}).get("cancel_requested"):
                batch_jobs[project_id]["status"] = "cancelled"
                ws_manager.broadcast_sync(project_id, {
                    "type": "batch_progress",
                    "status": "cancelled",
                    "progress": batch_jobs[project_id].get("progress", 0.0),
                    "current_page": idx,
                    "total_pages": total,
                    "error": "Cancelled by user"
                })
                return

            # Resume computes the minimum safe set of stages per page. In
            # particular, detection is never repeated on pages with layers.
            page_steps = _plan_resumable_page_pipeline(page, is_clean_asset_current(page)) if resume_mode else active_steps
            page_num_steps = max(1, len(page_steps))

            # Update status
            batch_jobs[project_id]["current_page"] = idx + 1
            batch_jobs[project_id]["progress"] = float(idx) / total
            
            # Helper to broadcast step progress
            def broadcast_step(step_name: str, step_offset: float):
                page_progress = (float(idx) + step_offset / page_num_steps) / total
                ws_manager.broadcast_sync(project_id, {
                    "type": "batch_progress",
                    "status": "running",
                    "current_page": idx + 1,
                    "total_pages": total,
                    "step": step_name,
                    "progress": page_progress,
                    "page_id": page.id
                })

            def broadcast_ocr_progress(completed_blocks: int, total_blocks: int, batch_index: int = 0, total_batches: int = 0):
                """Publish sub-page OCR progress so long OCR pages do not appear frozen."""
                fraction = (float(completed_blocks) / float(total_blocks)) if total_blocks else 1.0
                page_progress = (float(idx) + (float(step_idx) + fraction) / page_num_steps) / total
                ws_manager.broadcast_sync(project_id, {
                    "type": "batch_progress",
                    "status": "running",
                    "current_page": idx + 1,
                    "total_pages": total,
                    "step": "ocr",
                    "progress": page_progress,
                    "page_id": page.id,
                    "completed_blocks": completed_blocks,
                    "total_blocks": total_blocks,
                    "batch_index": batch_index,
                    "total_batches": total_batches,
                    "batch_size": 12 if backend and any(token in str(backend).lower() for token in ("gemini", "ai", "agy")) else 1,
                })

            # Helper to check if user clicked cancel
            def check_cancel_requested() -> bool:
                if batch_jobs.get(project_id, {}).get("cancel_requested"):
                    batch_jobs[project_id]["status"] = "cancelled"
                    ws_manager.broadcast_sync(project_id, {
                        "type": "batch_progress",
                        "status": "cancelled",
                        "progress": batch_jobs[project_id].get("progress", 0.0),
                        "current_page": idx + 1,
                        "total_pages": total,
                        "error": "Cancelled by user"
                    })
                    return True
                return False

            if check_cancel_requested():
                return

            step_idx = 0

            # Step A: Detect
            if "detect" in page_steps:
                if check_cancel_requested():
                    return
                # A detector call is opaque (the model does not expose token or
                # scanline progress), so mark the phase as started with a small
                # truthful coarse increment instead of displaying a frozen 0%.
                broadcast_step("detect", float(step_idx) + 0.25)
                if any((block.translation or "").strip() for block in page.text_blocks):
                    raise ValueError(
                        f"Detection blocked on page {page.page_number}: imported translations would be deleted"
                    )
                gpu_ep = get_execution_provider_setting(project.settings if project else None)
                blocks_data = balloon_detector.detect(page.source_image_path, min_confidence=min_confidence, execution_provider=gpu_ep, model_name=selected_model, cancel_check=check_cancel_requested)
                if check_cancel_requested():
                    return
                # Detection itself is a single model call, so expose a coarse
                # midpoint once inference returns instead of leaving the batch
                # indicator at 0% for the entire detector latency.
                broadcast_step("detect", 0.5)

                from app.utils.image_utils import cv2_imread_unicode
                detection_image = cv2_imread_unicode(page.source_image_path)
                if detection_image is None:
                    raise ValueError(f"Could not load detection image: {page.source_image_path}")

                from app.services.detector import compute_smart_balloon_bounds
                from app.config import get_enable_smart_balloon, get_smart_balloon_inset_ratio

                proj_settings = project.settings or {}
                enable_smart = get_enable_smart_balloon(proj_settings)
                inset_ratio = get_smart_balloon_inset_ratio(proj_settings)

                # A batch may be retried or launched again. Always replace the
                # previous candidates instead of appending another identical set.
                db.query(TextBlock).filter(TextBlock.page_id == page.id).delete(
                    synchronize_session=False
                )
                for p_idx, block in enumerate(blocks_data):
                    layout_region = analyze_layout_region(detection_image, block)
                    text_bbox = {
                        "x": block["x"],
                        "y": block["y"],
                        "width": block["width"],
                        "height": block["height"],
                    }

                    final_x = float(block["x"])
                    final_y = float(block["y"])
                    final_w = float(block["width"])
                    final_h = float(block["height"])

                    smart_x = None
                    smart_y = None
                    smart_w = None
                    smart_h = None
                    smart_res = {}

                    if enable_smart:
                        rival_boxes = [b for j, b in enumerate(blocks_data) if j != p_idx]
                        smart_res = compute_smart_balloon_bounds(
                            detection_image, block, rival_boxes=rival_boxes, inset_ratio=inset_ratio,
                            settings=proj_settings,
                        )
                        smart_x = smart_res.get("smart_x")
                        smart_y = smart_res.get("smart_y")
                        smart_w = smart_res.get("smart_width")
                        smart_h = smart_res["smart_height"] if "smart_height" in smart_res else None

                    if enable_smart and smart_res.get("success") and smart_x is not None and smart_w is not None and smart_w > 10.0:
                        final_x = float(smart_x)
                        final_y = float(smart_y)
                        final_w = float(smart_w)
                        final_h = float(smart_h)
                        layout_region = {
                            "x": float(smart_x),
                            "y": float(smart_y),
                            "width": float(smart_w),
                            "height": float(smart_h),
                            "shape": str(smart_res.get("archetype", "bubble")).lower(),
                            "source": "smart_balloon_v15",
                            "confidence": 0.95,
                            "version": "1.0.0",
                        }

                    block_metadata = {
                        "text_bbox": text_bbox,
                        "layout_region": layout_region,
                        "detection_class": block.get("detection_class", "text"),
                        "detected_balloon_type": block["balloon_type"],
                        "layer_origin": "auto_detection",
                        "text_evidence_state": "pending",
                    }
                    if enable_smart and smart_res.get("success"):
                        block_metadata["smart_balloon"] = {
                            "archetype": smart_res.get("archetype", "UNKNOWN"),
                            "method": smart_res.get("method", "smart_balloon_v15"),
                            "safe_bbox": smart_res.get("safe_bbox"),
                            "raw_bbox": smart_res.get("raw_bbox"),
                            "center": smart_res.get("center"),
                            "contour_points": smart_res.get("contour_points"),
                            "raw_contour_points": smart_res.get("raw_contour_points"),
                            "row_width_constraints": smart_res.get("row_width_constraints"),
                            "metadata": smart_res.get("metadata", {}),
                        }

                    db_block = TextBlock(
                        page_id=page.id,
                        block_index=p_idx,
                        x=final_x,
                        y=final_y,
                        width=final_w,
                        height=final_h,
                        smart_x=smart_x,
                        smart_y=smart_y,
                        smart_width=smart_w,
                        smart_height=smart_h,
                        rotation_deg=block["rotation_deg"],
                        confidence=block["confidence"],
                        balloon_type=block["balloon_type"],
                        extra_metadata=block_metadata,
                    )
                    apply_default_text_template(db_block, project.settings or {})
                    db.add(db_block)
                db.commit()
                db.refresh(page)
                broadcast_step("detect", 1.0)
                step_idx += 1
            
            # Step B: OCR
            if "ocr" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("ocr", float(step_idx))
                if project_ocr_done:
                    # Completed in 1 single Project-Wide Multi-Page PDF request!
                    broadcast_step("ocr", float(step_idx) + 1.0)
                    step_idx += 1
                else:
                    # Parallel OCR execution (smart incremental: targets new/unscanned blocks first, or all blocks if forced/requested)
                    unscanned_blocks = [b for b in page.text_blocks if not b.source_text]
                    ocr_targets = unscanned_blocks if unscanned_blocks else list(page.text_blocks)
                    if ocr_targets:
                        from app.services.performance import resolve_performance_settings
                        performance = resolve_performance_settings(project.settings or {})
                        results = crop_and_ocr_blocks_parallel(
                            page.source_image_path,
                            ocr_targets,
                            max_workers=performance.ocr_workers,
                            backend=backend,
                            source_lang=effective_lang,
                            progress_callback=broadcast_ocr_progress,
                            cancel_check=check_cancel_requested,
                        )
                    else:
                        results = []
                    
                    _process_ocr_evidence_results(results, project, db)
                    failed_block_ids = [str(block.id) for block, _text, success in results if not success]
                    if failed_block_ids:
                        batch_jobs[project_id].setdefault("ocr_failed_targets", []).append({
                            "page_id": str(page.id),
                            "page_number": page.page_number,
                            "block_ids": failed_block_ids,
                        })
                    _reindex_page_blocks(page.id, db)
                    db.commit()
                    if check_cancel_requested():
                        return
                    step_idx += 1
            
            # Step: Layout analysis and quality gate
            if "layout" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("layout", float(step_idx))
                from sqlalchemy.orm.attributes import flag_modified
                from app.services.layout_region import refresh_block_layout_regions

                blocks = list(page.text_blocks)
                refresh_block_layout_regions(blocks)
                for block in blocks:
                    spec = compute_block_typesetting(block)
                    persist_typesetting_spec(block, spec)
                    flag_modified(block, "extra_metadata")
                db.commit()
                if check_cancel_requested():
                    return
                step_idx += 1

            # Step: Sort
            if "sort" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("sort", float(step_idx))
                sorted_blocks = sorted(page.text_blocks, key=lambda b: (b.y, b.x))
                for p_idx, block in enumerate(sorted_blocks):
                    block.block_index = p_idx
                db.commit()
                db.refresh(page)
                if check_cancel_requested():
                    return
                step_idx += 1
            
            # Step: Mask (Generate mask preview & assets only, no inpaint)
            if "mask" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("mask", float(step_idx))
                from app.services.inpainter import generate_page_mask_only
                generate_page_mask_only(page.id, db)
                if check_cancel_requested():
                    return
                step_idx += 1

            # Step C: Inpaint
            if "inpaint" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("inpaint", float(step_idx))
                logger.info(f"Starting clean_page_text for page {page.id}")
                clean_page_text(page.id, db, cancel_check=check_cancel_requested)
                logger.info(f"clean_page_text completed for page {page.id}, refreshing page from database")
                db.refresh(page)
                logger.info(f"Page refreshed, broadcasting completion")
                # Broadcast completion immediately after inpaint finishes
                ws_manager.broadcast_sync(project_id, {
                    "type": "page_inpaint_complete",
                    "page_id": page.id,
                    "status": "success",
                })
                logger.info(f"Inpaint completion broadcasted, checking for cancellation")
                if check_cancel_requested():
                    return
                logger.info(f"Inpaint step completed for page {page.id}")
                step_idx += 1

            # Step: Font Judge / Style Judge
            if "font_judge" in page_steps or "style_judge" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("font_judge", float(step_idx))
                if not project_font_judged:
                    project_settings = page.project.settings if page.project else {}
                    descriptors_map = judge_page_styles_batch_ai(
                        page.text_blocks, project_settings=project_settings, page_height=page.height, model="flash_3.6"
                    )
                    for block in page.text_blocks:
                        b_id = str(block.id)
                        if b_id not in descriptors_map:
                            continue
                        desc = descriptors_map[b_id]
                        apply_style_descriptor_to_block(
                            block,
                            desc,
                            project_settings=project_settings,
                            apply_template=True,
                            confidence_auto_threshold=0.0,
                        )
                        spec = compute_block_typesetting(block)
                        persist_typesetting_spec(block, spec)
                    db.commit()
                if check_cancel_requested():
                    return
                step_idx += 1

            # Step D: Render
            if "render" in page_steps:
                if check_cancel_requested():
                    return
                broadcast_step("render", float(step_idx))
                render_page_text(page.id, db)
                if check_cancel_requested():
                    return
                step_idx += 1
            
            if check_cancel_requested():
                return

            # Update progress
            batch_jobs[project_id]["progress"] = float(idx + 1) / total
            ws_manager.broadcast_sync(project_id, {
                "type": "batch_progress",
                "status": "running",
                "current_page": idx + 1,
                "total_pages": total,
                "step": "done",
                "progress": float(idx + 1) / total,
                "page_id": page.id
            })
            
        if check_cancel_requested():
            return

        batch_jobs[project_id]["status"] = "success"
        batch_jobs[project_id]["progress"] = 1.0
        ws_manager.broadcast_sync(project_id, {
            "type": "batch_progress",
            "status": "success",
            "progress": 1.0,
            "current_page": total,
            "total_pages": total,
            "error": None,
            "ocr_backend": backend,
            "ocr_failed_targets": batch_jobs[project_id].get("ocr_failed_targets", []),
        })
    except Exception as e:
        if batch_jobs.get(project_id, {}).get("cancel_requested"):
            logger.info("Batch task terminated due to cancel request: %s", e)
            batch_jobs[project_id]["status"] = "cancelled"
            ws_manager.broadcast_sync(project_id, {
                "type": "batch_progress",
                "status": "cancelled",
                "progress": batch_jobs.get(project_id, {}).get("progress", 0.0),
                "current_page": batch_jobs.get(project_id, {}).get("current_page", 0),
                "total_pages": batch_jobs.get(project_id, {}).get("total_pages", 0),
                "error": "Cancelled by user"
            })
            return
        logger.exception("Batch processing task failed")
        batch_jobs[project_id] = {
            "status": "failed",
            "progress": 1.0,
            "current_page": batch_jobs.get(project_id, {}).get("current_page", 0),
            "total_pages": batch_jobs.get(project_id, {}).get("total_pages", 0),
            "error": str(e)
        }
        ws_manager.broadcast_sync(project_id, {
            "type": "batch_progress",
            "status": "failed",
            "progress": 1.0,
            "current_page": batch_jobs[project_id]["current_page"],
            "total_pages": batch_jobs[project_id]["total_pages"],
            "error": str(e)
        })
    finally:
        db.close()


@router.post("/pipeline/batch")
def run_batch_pipeline(
    project_id: str,
    steps: str = "detect,ocr,inpaint",
    min_confidence: float = None,
    backend: Optional[str] = None,
    source_lang: Optional[str] = None,
    balloon_model: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
):
    """
    Triggers batch processing on all pages of a project as a background task.
    """
    if not background_tasks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="BackgroundTasks dependency missing")
    
    # Initialize job state
    batch_jobs[project_id] = {
        "status": "running",
        "progress": 0.0,
        "current_page": 0,
        "total_pages": 0,
        "error": None
    }
    
    background_tasks.add_task(run_batch_pipeline_task, project_id, steps, min_confidence, backend, source_lang, balloon_model)
    return {"status": "success", "message": "Batch processing started in background."}

@router.get("/pipeline/batch/status")
def get_batch_status(project_id: str):
    """
    Queries status of the batch job for a project.
    """
    job = batch_jobs.get(project_id)
    if not job:
        return {
            "status": "idle",
            "progress": 0.0,
            "current_page": 0,
            "total_pages": 0,
            "error": None
        }
    return job


@router.post("/pipeline/batch/cancel")
def cancel_batch_pipeline(project_id: Optional[str] = None):
    """
    Cancels active batch processing jobs for a project (or all running jobs if project_id omitted).
    """
    cancelled_any = False
    if project_id:
        if project_id in batch_jobs and batch_jobs[project_id].get("status") in {"running", "queued"}:
            batch_jobs[project_id]["cancel_requested"] = True
            batch_jobs[project_id]["status"] = "cancelled"
            cancelled_any = True
            ws_manager.broadcast_sync(project_id, {
                "type": "batch_progress",
                "status": "cancelled",
                "progress": batch_jobs[project_id].get("progress", 0.0),
                "current_page": batch_jobs[project_id].get("current_page", 0),
                "error": "Cancelled by user"
            })
        for p_id, job in list(page_jobs.items()):
            if job.get("project_id") == project_id and job.get("status") in {"queued", "running"}:
                job["cancel_requested"] = True
                job["status"] = "cancelled"
                cancelled_any = True
                ws_manager.broadcast_sync(project_id, {
                    "type": "page_progress", "status": "cancelled", "page_id": p_id,
                })
    else:
        for prj_id, job in list(batch_jobs.items()):
            if job.get("status") in {"running", "queued"}:
                job["cancel_requested"] = True
                job["status"] = "cancelled"
                cancelled_any = True
                ws_manager.broadcast_sync(prj_id, {
                    "type": "batch_progress",
                    "status": "cancelled",
                    "error": "Cancelled by user"
                })
        for p_id, job in list(page_jobs.items()):
            if job.get("status") in {"queued", "running"}:
                job["cancel_requested"] = True
                job["status"] = "cancelled"
                cancelled_any = True

    if cancelled_any:
        return {"status": "success", "message": "Batch pipeline cancelled successfully."}
    return {"status": "no_action", "message": "No active batch job to cancel."}

class BlockMaskPayload(BaseModel):
    mask_base64: str


def _canonicalize_uploaded_mask(img_bytes: bytes) -> np.ndarray:
    """Decode editor PNGs into a strict 0/255 single-channel mask.

    The editor may submit grayscale masks or a red RGBA overlay. Persisting the
    overlay verbatim made OpenCV interpret red as a weak gray mask and allowed
    opaque black canvas pixels to contaminate cleanup. Canonical assets keep
    preview, region reclean, and full-page clean on the same binary contract.
    """
    encoded = np.frombuffer(img_bytes, dtype=np.uint8)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if decoded is None or decoded.size == 0:
        raise ValueError("Uploaded mask is not a valid image")
    if decoded.ndim == 2:
        selected = decoded > 12
    elif decoded.ndim == 3 and decoded.shape[2] >= 3:
        color_selected = np.max(decoded[:, :, :3], axis=2) > 24
        if decoded.shape[2] >= 4:
            color_selected = np.logical_and(color_selected, decoded[:, :, 3] > 12)
        selected = color_selected
    else:
        raise ValueError("Uploaded mask has an unsupported pixel format")
    return np.where(selected, 255, 0).astype(np.uint8)


def _encode_page_mask_data_url(mask_img: np.ndarray, *, overlay: bool) -> str:
    """Encode a binary mask or a browser-ready transparent red overlay."""
    image_to_encode = mask_img
    if overlay:
        height, width = mask_img.shape[:2]
        image_to_encode = np.zeros((height, width, 4), dtype=np.uint8)
        selected = mask_img > 12
        image_to_encode[selected] = (68, 68, 239, 230)  # BGRA -> red in browser RGBA
    success, encoded = cv2.imencode(".png", image_to_encode, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    if not success:
        raise OSError("Failed to encode page mask")
    mask_b64 = base64.b64encode(encoded).decode("utf-8")
    return f"data:image/png;base64,{mask_b64}"


def get_padded_block_coords(block, img_w: int, img_h: int, pad_margin: int = 30):
    # Start with the raw YOLO detection bbox
    bx0 = float(block.x)
    by0 = float(block.y)
    bx1 = bx0 + float(block.width)
    by1 = by0 + float(block.height)

    # The Canvas may display blocks using layout_region (balloon interior)
    # which can be significantly larger than the OCR detection box.
    # Union both areas so the Mask Editor crop matches the Canvas bounding box.
    metadata = getattr(block, "extra_metadata", None) or {}
    layout = metadata.get("layout_region") if isinstance(metadata, dict) else None
    if isinstance(layout, dict):
        try:
            lx = float(layout["x"])
            ly = float(layout["y"])
            lw = float(layout["width"])
            lh = float(layout["height"])
            if lw >= 4 and lh >= 4:
                bx0 = min(bx0, lx)
                by0 = min(by0, ly)
                bx1 = max(bx1, lx + lw)
                by1 = max(by1, ly + lh)
        except (KeyError, TypeError, ValueError):
            pass

    effective_w = bx1 - bx0
    effective_h = by1 - by0
    pad = max(pad_margin, int(max(effective_w, effective_h) * 0.15))
    px0 = max(0, int(bx0 - pad))
    py0 = max(0, int(by0 - pad))
    px1 = min(img_w, int(bx1 + pad))
    py1 = min(img_h, int(by1 + pad))
    return px0, py0, px1, py1


@router.get("/pages/{page_id}/mask-status")
def get_page_mask_status(page_id: str, db: Session = Depends(get_db)):
    """Return the mask type (custom|adaptive|box) for each text block on a page.

    This allows the UI to display visual indicators showing which blocks use
    custom user-drawn masks vs automatically generated masks.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    settings = page.project.settings or {}
    use_smart_mask = should_use_smart_mask(settings)

    statuses = []
    for block in page.text_blocks:
        mask_path = _mask_asset_path(page, f"mask_{block.id}.png")

        if mask_path.exists():
            mask_type = "custom"
        elif use_smart_mask:
            mask_type = "adaptive"
        else:
            mask_type = "box"

        statuses.append({
            "block_id": str(block.id),
            "mask_type": mask_type,
        })

    # Check for manual mask that affects the whole page
    manual_mask_path = _mask_asset_path(page, "manual_mask.png")
    page_override_path = _mask_asset_path(page, "page_mask_override.png")
    has_manual_mask = manual_mask_path.exists() or page_override_path.exists()

    return {
        "page_id": page_id,
        "statuses": statuses,
        "has_manual_mask": has_manual_mask,
        "has_page_mask_override": page_override_path.exists(),
        "cleanup_strategy": settings.get("cleanup_mask_strategy", "legacy_adaptive"),
    }


@router.get("/pipeline/pages/{page_id}/effective-mask")
@router.get("/pages/{page_id}/effective-mask")
def get_page_effective_mask(
    page_id: str,
    overlay: bool = False,
    db: Session = Depends(get_db),
):
    """Retrieve full-page composite mask (effective_mask.png) for page-level editing."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    mask_img = get_or_build_effective_page_mask(page_id, db)

    h, w = mask_img.shape[:2]

    return {
        "page_id": page_id,
        "width": w,
        "height": h,
        "mask_data_url": _encode_page_mask_data_url(mask_img, overlay=overlay),
    }


@router.post("/pipeline/pages/{page_id}/effective-mask")
@router.post("/pages/{page_id}/effective-mask")
def save_page_effective_mask_route(
    page_id: str,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    mask: Optional[UploadFile] = File(None),
    reclean: bool = False,
    return_mask: bool = True,
    engine: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Save an authoritative full-page mask and optionally trigger inpainting."""
    upload_file = file or mask
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    from app.services.project_paths import mask_asset_path
    override_path = mask_asset_path(page, "page_mask_override.png")

    if upload_file is not None:
        img_bytes = upload_file.file.read()
        canonical_mask = _canonicalize_uploaded_mask(img_bytes)
        # Mark Mode may use a bounded working canvas to keep interaction and
        # PNG encoding responsive. Persist the canonical asset at source-page
        # dimensions so every cleaner/renderer consumes the same geometry.
        target_width = int(getattr(page, "width", 0) or 0)
        target_height = int(getattr(page, "height", 0) or 0)
        if target_width <= 0 or target_height <= 0:
            source_image_path = getattr(page, "source_image_path", None)
            if source_image_path:
                source = cv2_imread_unicode(str(source_image_path))
                if source is not None:
                    target_height, target_width = source.shape[:2]
        if target_width > 0 and target_height > 0 and canonical_mask.shape != (target_height, target_width):
            canonical_mask = cv2.resize(
                canonical_mask,
                (target_width, target_height),
                interpolation=cv2.INTER_NEAREST,
            )
            canonical_mask = np.where(canonical_mask > 12, 255, 0).astype(np.uint8)
        if np.any(canonical_mask):
            override_path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2_imwrite_unicode(str(override_path), canonical_mask):
                raise OSError(f"Failed to save page mask override: {override_path}")
        else:
            override_path.unlink(missing_ok=True)
    else:
        override_path.unlink(missing_ok=True)

    if reclean:
        background_tasks.add_task(
            _run_page_clean_background,
            str(page.id),
            engine,
        )
    else:
        mark_clean_assets_stale(page)
        db.commit()

    if not return_mask:
        return {
            "page_id": page_id,
            "status": "success",
            "clean_mode": "background" if reclean else "stale_base_preserved",
        }

    updated_img = build_effective_page_mask(page_id, db)
    h, w = updated_img.shape[:2]

    return {
        "page_id": page_id,
        "status": "success",
        "width": w,
        "height": h,
        "mask_data_url": _encode_page_mask_data_url(updated_img, overlay=False),
    }


def _run_page_clean_background(page_id: str, engine: Optional[str]) -> None:
    """Run page cleaning with a fresh session after the save response returns."""
    task_db = SessionLocal()
    project_id: str | None = None
    try:
        page = task_db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise ValueError(f"Page not found: {page_id}")
        project_id = str(page.project_id)
        from app.ws_manager import ws_manager
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "running", "page_id": page_id,
        })
        logger.info("Starting background page clean page=%s", page_id)
        clean_page_text(page_id, task_db, engine_override=engine)
        logger.info("Completed background page clean page=%s", page_id)
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "success", "page_id": page_id,
        })
    except Exception as exc:
        logger.exception("Background page clean failed page=%s", page_id)
        if project_id:
            ws_manager.broadcast_sync(project_id, {
                "type": "mask_progress", "status": "error", "page_id": page_id,
                "error": str(exc),
            })
    finally:
        task_db.close()


@router.post("/pipeline/pages/{page_id}/auto-mask")
@router.post("/pages/{page_id}/auto-mask")
def generate_page_auto_mask(
    page_id: str,
    overlay: bool = False,
    db: Session = Depends(get_db),
):
    """Preview fresh automatic text detection without mutating saved masks."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    updated_img = build_automatic_page_mask(page_id, db)
    h, w = updated_img.shape[:2]

    return {
        "page_id": page_id,
        "status": "success",
        "width": w,
        "height": h,
        "mask_data_url": _encode_page_mask_data_url(updated_img, overlay=overlay),
    }


@router.post("/pipeline/blocks/{block_id}/mask/text-detect")
def generate_text_detection_mask(
    block_id: str,
    kernel: int = 3,
    db: Session = Depends(get_db),
):
    """Generate a preview mask from line-level text detection.

    This intentionally does not save anything.  The mask editor remains the
    review point, so a user can inspect, paint, erase, then explicitly save it.
    """
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    page = block.page

    source_path = Path(page.source_image_path)
    image = cv2_imread_unicode(str(source_path))
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source image not found")
    height, width = image.shape[:2]
    px0, py0, px1, py1 = get_padded_block_coords(block, width, height)
    crop = image[py0:py1, px0:px1]
    if crop.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid block dimensions")

    # User-configured dilation kernel up to 56px
    applied_kernel = max(0, min(56, int(kernel)))
    settings = (page.project.settings if page and page.project else {}) or {}
    method = str(
        settings.get("mask_gen_method")
        or settings.get("default_mask_gen_method")
        or "hybrid"
    ).lower()

    from app.services.text_mask import (
        generate_routed_text_mask,
        generate_adaptive_sfx_mask,
        generate_imagetrans_text_mask,
        generate_contour_morphology_text_mask,
    )
    try:
        if method == "imagetrans":
            mask = generate_imagetrans_text_mask(crop, dilation_kernel=applied_kernel)
            selected_mode = "imagetrans"
            diagnostics = {}
        elif method in ("contour", "morphology", "adaptive"):
            mask = generate_contour_morphology_text_mask(crop, dilation_kernel=applied_kernel)
            selected_mode = "contour"
            diagnostics = {}
        elif method in ("sam", "segment"):
            from app.services.sam_segmenter import smart_segment_box
            ch, cw = crop.shape[:2]
            mask = smart_segment_box(crop, 0, 0, cw, ch)
            if mask is not None and applied_kernel > 0:
                kelem = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (applied_kernel * 2 + 1, applied_kernel * 2 + 1))
                mask = cv2.dilate(mask, kelem, iterations=1)
            selected_mode = "sam"
            diagnostics = {}
        elif method in ("balloon", "rectangle", "full_box", "box", "full"):
            mask = np.full(crop.shape[:2], 255, dtype=np.uint8)
            selected_mode = "balloon"
            diagnostics = {}
        else:
            mask, selected_mode, diagnostics = generate_routed_text_mask(
                crop, dilation_kernel=applied_kernel
            )
            if mask is None or not np.any(mask):
                mask = generate_adaptive_sfx_mask(crop, dilation_kernel=applied_kernel)
            selected_mode = selected_mode or "hybrid"

        regions = []
        warnings = [f"Selected mask mode: {selected_mode}."]

        # Apply project Magnetic Line Fill and hole filling if enabled for 100% parity with auto clean
        settings = (page.project.settings if page and page.project else {}) or {}
        magnetic_fill_enabled = bool(
            settings.get("mask_magnetic_line_fill")
            or settings.get("magnetic_mask_fill")
            or (isinstance(getattr(block, "extra_metadata", None), dict) and block.extra_metadata.get("mask_magnetic_line_fill"))
        )
        if magnetic_fill_enabled and mask is not None and np.any(mask):
            from app.services.mask.magnetic_mask import apply_magnetic_line_fill
            mask = apply_magnetic_line_fill(mask, image_bgr=crop)

        from app.services.inpainter import fill_mask_holes
        if mask is not None and np.any(mask):
            mask = fill_mask_holes(mask)
    except RuntimeError as exc:
        logger.warning("High quality text mask unavailable for block %s: %s", block_id, exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("High quality text mask failed for block %s", block_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text detection mask failed: {exc}",
        ) from exc

    _, encoded = cv2.imencode(".png", mask)
    mask_b64 = base64.b64encode(encoded).decode("utf-8")
    return {
        "status": "success",
        "safe": bool(regions) and bool(np.count_nonzero(mask)),
        "mask": f"data:image/png;base64,{mask_b64}",
        "regions": regions,
        "warnings": warnings,
        "detected_line_count": len(regions),
        "applied_kernel": applied_kernel,
        "mask_mode": selected_mode,
        "mask_diagnostics": diagnostics,
    }


class SmartSegmentRequest(BaseModel):
    x0: int
    y0: int
    x1: int
    y1: int
    kernel: int = 0


@router.post("/pipeline/blocks/{block_id}/mask/smart-segment")
def smart_segment_mask(
    block_id: str,
    body: SmartSegmentRequest,
    db: Session = Depends(get_db),
):
    """Generate a pixel-precise mask using SAM 2.1 box-prompt segmentation.

    The frontend draws a selection rectangle in the Mask Editor; this endpoint
    runs the SAM 2.1 encoder (cached) + decoder to produce a binary mask of
    the foreground object(s) inside that rectangle.
    """
    from app.services.sam_segmenter import smart_segment_box

    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    page = block.page
    source_path = Path(page.source_image_path)
    image = cv2_imread_unicode(str(source_path))
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source image not found")

    h, w = image.shape[:2]
    px0, py0, px1, py1 = get_padded_block_coords(block, w, h)
    crop = image[py0:py1, px0:px1]
    if crop.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid block dimensions")

    crop_h, crop_w = crop.shape[:2]
    # Clamp coordinates to crop bounds
    sx0 = max(0, min(body.x0, crop_w - 1))
    sy0 = max(0, min(body.y0, crop_h - 1))
    sx1 = max(sx0 + 1, min(body.x1, crop_w))
    sy1 = max(sy0 + 1, min(body.y1, crop_h))

    mask = smart_segment_box(crop, sx0, sy0, sx1, sy1)
    if mask is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAM 2.1 model not available.  Place encoder/decoder ONNX files in backend/models/sam/",
        )

    # Apply dilation kernel if specified
    if body.kernel > 0:
        ksize = max(3, body.kernel * 2 + 1)
        kernel_elem = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        mask = cv2.dilate(mask, kernel_elem, iterations=1)

    _, encoded = cv2.imencode(".png", mask)
    mask_b64 = base64.b64encode(encoded).decode("utf-8")
    return {
        "status": "success",
        "mask": f"data:image/png;base64,{mask_b64}",
    }


@router.get("/pipeline/blocks/{block_id}/mask")
def get_block_mask(
    block_id: str,
    force_auto: bool = False,
    kernel: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Returns original crop image and either custom saved mask or dynamically
    generated adaptive text mask for a specific text block.
    """
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
        
    page = block.page
    source_path = Path(page.source_image_path)
    if not source_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source image not found")
        
    img = cv2_imread_unicode(str(source_path))
    if img is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load image")
        
    h, w = img.shape[:2]
    px0, py0, px1, py1 = get_padded_block_coords(block, w, h)
    
    crop = img[py0:py1, px0:px1]
    if crop.size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid block dimensions")
        
    _, crop_encoded = cv2.imencode(".png", crop)
    crop_b64 = base64.b64encode(crop_encoded).decode("utf-8")
    
    settings = page.project.settings or {}
    dilation_kernel = int(kernel if kernel is not None else settings.get("mask_dilation_kernel", 3))

    # Load custom mask if it exists (only when force_auto=False), otherwise compute fresh Manga UNet++ mask
    from app.services.project_paths import mask_asset_path
    custom_mask_path = mask_asset_path(page, f"mask_{block.id}.png")
    legacy_mask_path = source_path.parent / f"mask_{block.id}.png"
    if not custom_mask_path.exists() and legacy_mask_path.exists():
        custom_mask_path = legacy_mask_path

    use_saved = False
    if not force_auto and custom_mask_path.exists():
        loaded_saved = cv2_imread_unicode(str(custom_mask_path), cv2.IMREAD_GRAYSCALE)
        if loaded_saved is not None:
            # The editor is allowed to save a large (even complete) crop mask.
            # It is the source of truth; never discard or silently replace it
            # while serving a read request.
            mask_img = loaded_saved
            use_saved = True
            if mask_img.shape[:2] != (py1 - py0, px1 - px0):
                if abs(mask_img.shape[0] - int(block.height)) <= 4 and abs(mask_img.shape[1] - int(block.width)) <= 4:
                    padded_mask = np.zeros((py1 - py0, px1 - px0), dtype=np.uint8)
                    ox = max(0, int(block.x - px0))
                    oy = max(0, int(block.y - py0))
                    padded_mask[oy:oy+mask_img.shape[0], ox:ox+mask_img.shape[1]] = mask_img
                    mask_img = padded_mask
                else:
                    mask_img = cv2.resize(mask_img, (px1 - px0, py1 - py0), interpolation=cv2.INTER_NEAREST)

    if not use_saved:
        full_mask = get_automatic_block_mask(
            img, block, settings, dilation_kernel=dilation_kernel
        )
        mask_img = full_mask[py0:py1, px0:px1]
        
    if mask_img is None:
        mask_img = np.zeros((py1-py0, px1-px0), dtype=np.uint8)
        
    _, mask_encoded = cv2.imencode(".png", mask_img)
    mask_b64 = base64.b64encode(mask_encoded).decode("utf-8")
    
    crop_data_url = f"data:image/png;base64,{crop_b64}"
    mask_data_url = f"data:image/png;base64,{mask_b64}"
    crop_h, crop_w = crop.shape[:2]

    return {
        "status": "success",
        "crop": crop_data_url,
        "mask": mask_data_url,
        "crop_data_url": crop_data_url,
        "mask_data_url": mask_data_url,
        "crop_width": crop_w,
        "crop_height": crop_h,
    }


@router.post("/pipeline/blocks/{block_id}/mask")
def save_block_mask(
    block_id: str,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    mask: Optional[UploadFile] = File(None),
    reclean: bool = False,
    allow_full_page: bool = True,
    engine: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Saves a custom manually drawn or adjusted binary mask for a text block using FormData.
    """
    upload_file = file or mask
    if upload_file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No mask file provided in request."
        )

    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
        
    page = block.page
    from app.services.project_paths import mask_asset_path, inpainted_asset_path
    mask_path = mask_asset_path(page, f"mask_{block.id}.png")
    
    try:
        # Check before replacing the file. An existing clean image can be patched directly
        # for this block, avoiding an expensive 70+ second full page re-clean.
        can_reclean_region = is_clean_asset_current(page) or inpainted_asset_path(page).is_file()
        img_bytes = upload_file.file.read()
        canonical_mask = _canonicalize_uploaded_mask(img_bytes)
        source_path = Path(page.source_image_path)
        if not source_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source image not found while validating mask geometry.",
            )
        source_w = int(getattr(page, "width", 0) or 0)
        source_h = int(getattr(page, "height", 0) or 0)
        if source_w <= 0 or source_h <= 0:
            # Legacy projects may not have dimensions persisted yet. Decode
            # only for that compatibility case; normal saves must not decode a
            # multi-megapixel stitched page just to validate mask geometry.
            source_img = cv2_imread_unicode(str(source_path))
            if source_img is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Source image dimensions are unavailable.",
                )
            source_h, source_w = source_img.shape[:2]
        px0, py0, px1, py1 = get_padded_block_coords(block, source_w, source_h)
        expected_shape = (py1 - py0, px1 - px0)
        if canonical_mask.shape != expected_shape:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Mask dimensions do not match the current editor crop "
                    f"(mask={canonical_mask.shape[1]}x{canonical_mask.shape[0]}, "
                    f"crop={expected_shape[1]}x{expected_shape[0]}). Reopen the Mask Editor and try again."
                ),
            )
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2_imwrite_unicode(str(mask_path), canonical_mask):
            raise OSError(f"Failed to save custom mask: {mask_path}")

        # A legacy/full-page Mask Mode edit is authoritative for the rest of
        # the page, but it must not make later block-editor edits invisible.
        # Replace only this editor crop in the existing page override so its
        # surrounding manual work is preserved while reclean sees this exact
        # newly saved block mask.
        page_override_path = mask_asset_path(page, "page_mask_override.png")
        if page_override_path.exists():
            page_override = cv2_imread_unicode(str(page_override_path), cv2.IMREAD_GRAYSCALE)
            if page_override is not None:
                if page_override.shape[:2] != (source_h, source_w):
                    page_override = cv2.resize(
                        page_override,
                        (source_w, source_h),
                        interpolation=cv2.INTER_NEAREST,
                    )
                page_override[py0:py1, px0:px1] = canonical_mask
                if not cv2_imwrite_unicode(str(page_override_path), page_override):
                    raise OSError(f"Failed to update page mask override: {page_override_path}")

        if can_reclean_region:
            # A saved block mask is immediately useful when a clean base exists.
            # Apply only its dirty region regardless of the legacy reclean flag.
            db.commit()
            background_tasks.add_task(
                _run_block_reclean_background,
                str(page.id),
                str(block.id),
                engine,
            )
            clean_mode = "region_background"
            invalidated = 0
        elif reclean:
            invalidated = mark_clean_assets_stale(page)
            db.commit()
            clean_mode = "needs_page_clean"
        else:
            db.commit()
            clean_mode = "stale_base_preserved"
            invalidated = 0
        return {
            "status": "success",
            "message": "Custom block mask saved",
            "invalidated_assets": invalidated,
            "clean_mode": clean_mode,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to save block mask")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save custom block mask: {e}"
        )


def _run_block_reclean_background(page_id: str, block_id: str, engine: Optional[str]) -> None:
    """Run block reclean with a fresh DB session after the save response returns."""
    import time
    task_db = SessionLocal()
    start_time = time.time()
    try:
        page = task_db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise ValueError(f"Page not found: {page_id}")
        project_id = str(page.project_id)
        from app.ws_manager import ws_manager
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "running", "page_id": page_id,
            "block_id": block_id,
        })
        logger.info("Starting background block reclean page=%s block=%s", page_id, block_id)
        reclean_page_block(page_id, block_id, task_db, engine_override=engine)
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info("Completed background block reclean page=%s block=%s in %dms", page_id, block_id, elapsed_ms)
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "success", "page_id": page_id,
            "block_id": block_id, "elapsed_ms": elapsed_ms,
        })
    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.exception("Background block reclean failed page=%s block=%s after %dms", page_id, block_id, elapsed_ms)
        if "project_id" in locals():
            ws_manager.broadcast_sync(project_id, {
                "type": "mask_progress", "status": "error", "page_id": page_id,
                "block_id": block_id, "error": str(exc), "elapsed_ms": elapsed_ms,
            })
    finally:
        task_db.close()


class InpaintPreviewRequest(BaseModel):
    mask_base64: str
    engine: Optional[str] = None


@router.post("/pipeline/blocks/{block_id}/inpaint-preview")
def generate_block_inpaint_preview(
    block_id: str,
    request: InpaintPreviewRequest,
    db: Session = Depends(get_db),
):
    """
    Generate a lightweight inpaint preview using a temporary mask.
    Returns a base64-encoded preview image without saving to disk.
    """
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    page = block.page
    project = page.project

    try:
        # Decode mask from base64
        try:
            mask_bytes = base64.b64decode(request.mask_base64.split(",")[-1])
        except (ValueError, binascii.Error) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 mask data: {str(e)}"
            )

        mask_array = np.frombuffer(mask_bytes, dtype=np.uint8)
        mask_img = cv2.imdecode(mask_array, cv2.IMREAD_GRAYSCALE)

        if mask_img is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mask image format"
            )

        # Load source image
        source_path = Path(page.source_image_path)
        if not source_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source image not found"
            )

        from app.utils.image_utils import cv2_imread_unicode
        source_img = cv2_imread_unicode(source_path)

        image_h, image_w = source_img.shape[:2]
        x0, y0, x1, y1 = get_padded_block_coords(block, image_w, image_h)

        # Crop image and mask to block region
        crop_img = source_img[y0:y1, x0:x1].copy()
        crop_h, crop_w = crop_img.shape[:2]
        if mask_img.shape != (crop_h, crop_w):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Mask dimensions do not match the current editor crop "
                    f"(mask={mask_img.shape[1]}x{mask_img.shape[0]}, "
                    f"crop={crop_w}x{crop_h}). Reopen the Mask Editor and try again."
                ),
            )
        mask_img = np.where(mask_img > 12, 255, 0).astype(np.uint8)

        # Inpaint the crop (lightweight preview - max 512px)
        max_dim = max(crop_h, crop_w)
        if max_dim > 512:
            scale = 512 / max_dim
            preview_h = int(crop_h * scale)
            preview_w = int(crop_w * scale)
            crop_preview = cv2.resize(crop_img, (preview_w, preview_h))
            mask_preview = cv2.resize(mask_img, (preview_w, preview_h), interpolation=cv2.INTER_NEAREST)
        else:
            crop_preview = crop_img
            mask_preview = mask_img

        # Resolve requested inpaint engine using resolve_inpaint_engine_name
        from app.services.inpainter import resolve_inpaint_engine_name, _get_lama, _get_mat
        engine_name = resolve_inpaint_engine_name(project.settings if project else None)
        if request.engine:
            engine_name = str(request.engine).strip().lower()

        gpu_ep = get_execution_provider_setting(project.settings if project else None)

        inpaint_service = None
        if engine_name in {"mat", "mat_onnx", "mask_aware_transformer"}:
            inpaint_service = _get_mat(execution_provider=gpu_ep) or _get_lama(execution_provider=gpu_ep)
        elif engine_name in {"lama", "lamainpaint", "lama_onnx", "local_lama"}:
            inpaint_service = _get_lama(execution_provider=gpu_ep)

        if inpaint_service is not None:
            inpainted = inpaint_service.inpaint(crop_preview, mask_preview)
        else:
            inpaint_flag = cv2.INPAINT_NS if engine_name in ("ns", "navierstokes") else cv2.INPAINT_TELEA
            inp_radius = int((project.settings or {}).get("image_inpainting_radius", 3))
            inpainted = cv2.inpaint(crop_preview, mask_preview, inp_radius, flags=inpaint_flag)

        # Encode result as base64
        _, buffer = cv2.imencode('.png', inpainted)
        result_b64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "status": "success",
            "preview": f"data:image/png;base64,{result_b64}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate inpaint preview")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate preview: {e}"
        )


@router.post("/pipeline/blocks/{block_id}/reclean")
def reclean_single_block(
    block_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Re-inpaint a single block after mask update (async, non-blocking).
    Returns immediately while inpainting runs in background.
    """
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    page = block.page

    def _reclean_task():
        try:
            logger.info(f"Starting async reclean for block {block_id}")
            reclean_page_block(page.id, block_id, db)
            logger.info(f"Completed async reclean for block {block_id}")
        except Exception as e:
            logger.exception(f"Failed to reclean block {block_id}: {e}")

    background_tasks.add_task(_reclean_task)

    return {
        "status": "success",
        "message": f"Reclean started for block {block_id}",
        "block_id": block_id
    }





def _run_block_reclean_background(page_id: str, block_id: str, engine: Optional[str]) -> None:
    """Run block reclean with a fresh DB session after the save response returns."""
    import time
    task_db = SessionLocal()
    start_time = time.time()
    try:
        page = task_db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise ValueError(f"Page not found: {page_id}")
        project_id = str(page.project_id)
        from app.ws_manager import ws_manager
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "running", "page_id": page_id,
            "block_id": block_id,
        })
        logger.info("Starting background block reclean page=%s block=%s", page_id, block_id)
        reclean_page_block(page_id, block_id, task_db, engine_override=engine)
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info("Completed background block reclean page=%s block=%s in %dms", page_id, block_id, elapsed_ms)
        ws_manager.broadcast_sync(project_id, {
            "type": "mask_progress", "status": "success", "page_id": page_id,
            "block_id": block_id, "elapsed_ms": elapsed_ms,
        })
    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.exception("Background block reclean failed page=%s block=%s after %dms", page_id, block_id, elapsed_ms)
        if "project_id" in locals():
            ws_manager.broadcast_sync(project_id, {
                "type": "mask_progress", "status": "error", "page_id": page_id,
                "block_id": block_id, "error": str(exc), "elapsed_ms": elapsed_ms,
            })
    finally:
        task_db.close()


@router.post("/pipeline/blocks/{block_id}/fast-preview")
def generate_block_fast_telea_preview(
    block_id: str,
    request: InpaintPreviewRequest,
    db: Session = Depends(get_db),
):
    """
    Generate an ultra-fast inpaint preview using OpenCV Telea.
    Designed for real-time live preview during custom mask drawing.
    """
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    page = block.page
    try:
        mask_bytes = base64.b64decode(request.mask_base64.split(",")[-1])
        mask_array = np.frombuffer(mask_bytes, dtype=np.uint8)
        mask_img = cv2.imdecode(mask_array, cv2.IMREAD_GRAYSCALE)
        if mask_img is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid mask image format")

        source_img = page_image_cache.get_source_image(str(page.id))
        if source_img is None:
            source_path = Path(page.source_image_path)
            if not source_path.exists():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source image not found")
            source_img = cv2_imread_unicode(str(source_path))
            if source_img is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to load image via OpenCV")
            page_image_cache.set_source_image(str(page.id), source_img)

        x0 = max(0, int(block.x) - 16)
        y0 = max(0, int(block.y) - 16)
        x1 = min(source_img.shape[1], int(block.x + block.width) + 16)
        y1 = min(source_img.shape[0], int(block.y + block.height) + 16)

        crop_img = source_img[y0:y1, x0:x1].copy()
        if mask_img.shape[:2] != crop_img.shape[:2]:
            mask_img = cv2.resize(mask_img, (crop_img.shape[1], crop_img.shape[0]), interpolation=cv2.INTER_NEAREST)

        result_crop = fast_telea_preview(crop_img, mask_img)

        _, encoded = cv2.imencode(".jpg", result_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        preview_base64 = base64.b64encode(encoded).decode("utf-8")

        return {
            "status": "success",
            "preview_url": f"data:image/jpeg;base64,{preview_base64}",
            "bounds": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Fast preview failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/projects/{project_id}/smart-balloon/recompute")
def recompute_project_smart_balloons(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[Any] = Depends(get_current_user_or_local),
):
    """
    1-Click Upgrade Endpoint: Batch converts any old or existing project to use
    Smart Balloon Segmentation, Contour Bounds, and Contour-Aware Typesetting across all pages.
    """
    from app.security.dependencies import ensure_project_access
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    ensure_project_access(project, current_user)

    # Enable Smart Balloon in project settings
    settings = dict(project.settings or {})
    settings["enable_smart_balloon"] = True
    project.settings = settings
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(project, "settings")

    from app.services.detector import compute_smart_balloon_bounds
    from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
    from app.config import get_smart_balloon_inset_ratio

    inset_ratio = get_smart_balloon_inset_ratio(project.settings or {})
    total_blocks_updated = 0
    pages_processed = 0

    for page in project.pages:
        img_path = page.source_image_path
        if not img_path or not Path(img_path).exists():
            continue

        page_img = cv2_imread_unicode(str(img_path))
        if page_img is None:
            continue

        pages_processed += 1
        page_blocks = list(page.text_blocks)
        for idx, block in enumerate(page_blocks):
            bbox = {"x": float(block.x), "y": float(block.y), "width": float(block.width), "height": float(block.height)}
            rivals = [
                {"x": float(b.x), "y": float(b.y), "width": float(b.width), "height": float(b.height)}
                for j, b in enumerate(page_blocks) if j != idx
            ]
            smart_res = compute_smart_balloon_bounds(page_img, bbox, rival_boxes=rivals, inset_ratio=inset_ratio, settings=project.settings or {})

            if "smart_x" in smart_res and smart_res["smart_x"] is not None:
                sx = float(smart_res["smart_x"])
                sy = float(smart_res["smart_y"])
                sw = float(smart_res["smart_width"])
                sh = float(smart_res["smart_height"])
                block.smart_x = sx
                block.smart_y = sy
                block.smart_width = sw
                block.smart_height = sh

                if smart_res.get("success") and sw > 10.0 and sh > 10.0:
                    block.x = sx
                    block.y = sy
                    block.width = sw
                    block.height = sh

                # Save mask crop asset if generated
                if "crop_mask" in smart_res and smart_res["crop_mask"] is not None:
                    masks_dir = Path(img_path).parent / "masks"
                    masks_dir.mkdir(parents=True, exist_ok=True)
                    mask_file = masks_dir / f"smart_balloon_{block.id}.png"
                    cv2_imwrite_unicode(str(mask_file), smart_res["crop_mask"])
                    block.smart_mask_path = str(mask_file)

            meta = dict(block.extra_metadata or {})
            if "text_bbox" not in meta:
                meta["text_bbox"] = bbox
            meta["manual_font_size"] = None
            meta["font_size_mode"] = "auto"
            meta["contour_layout"] = True
            meta.pop("typesetting_spec", None)
            if "smart_x" in smart_res and smart_res.get("success"):
                meta["layout_region"] = {
                    "x": float(smart_res["smart_x"]),
                    "y": float(smart_res["smart_y"]),
                    "width": float(smart_res["smart_width"]),
                    "height": float(smart_res["smart_height"]),
                    "shape": str(smart_res.get("archetype", "bubble")).lower(),
                    "source": "smart_balloon_v15",
                    "confidence": 0.95,
                    "version": "1.0.0",
                }
                meta["smart_balloon"] = {
                    "archetype": smart_res.get("archetype", "UNKNOWN"),
                    "method": smart_res.get("method", "smart_balloon_v15"),
                    "safe_bbox": smart_res.get("safe_bbox"),
                    "raw_bbox": smart_res.get("raw_bbox"),
                    "center": smart_res.get("center"),
                    "contour_points": smart_res.get("contour_points"),
                    "raw_contour_points": smart_res.get("raw_contour_points"),
                    "metadata": smart_res.get("metadata", {}),
                }
            block.extra_metadata = meta
            flag_modified(block, "extra_metadata")

            # Recompute Contour-Aware Typesetting & Auto Font Size
            try:
                spec = compute_block_typesetting(block)
                persist_typesetting_spec(block, spec)
                flag_modified(block, "extra_metadata")
            except Exception as exc:
                logger.warning(f"Typesetting recompute failed for block {block.id}: {exc}")

            total_blocks_updated += 1

    db.commit()

    # Keep project manifest on disk updated in sync
    try:
        from app.services.project_serializer import save_project_json
        save_project_json(project_id, db=db)
    except Exception as exc:
        logger.warning(f"Failed to update project manifest after smart balloon recompute: {exc}")

    return {
        "status": "success",
        "project_id": project_id,
        "pages_processed": pages_processed,
        "total_blocks_updated": total_blocks_updated,
        "message": f"Successfully upgraded {total_blocks_updated} blocks across {pages_processed} pages to Smart Balloon Contour Typesetting!",
    }


@router.post("/pipeline/blocks/{block_id}/smart-balloon/recompute")
def recompute_single_block_smart_balloon(
    block_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[Any] = Depends(get_current_user_or_local),
):
    """Recomputes Smart Balloon bounds and contour mask for a single text block."""
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")

    page = block.page
    img_path = page.source_image_path
    if not img_path or not Path(img_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source image not found")

    page_img = cv2_imread_unicode(str(img_path))
    if page_img is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load page image")

    bbox = {"x": float(block.x), "y": float(block.y), "width": float(block.width), "height": float(block.height)}
    from app.services.detector import compute_smart_balloon_bounds
    from app.config import get_smart_balloon_inset_ratio

    proj_settings = (page.project.settings or {}) if page and page.project else {}
    inset_ratio = get_smart_balloon_inset_ratio(proj_settings)
    rivals = [
        {"x": float(b.x), "y": float(b.y), "width": float(b.width), "height": float(b.height)}
        for b in page.text_blocks if b.id != block.id
    ]
    smart_res = compute_smart_balloon_bounds(page_img, bbox, rival_boxes=rivals, inset_ratio=inset_ratio, settings=proj_settings)

    if "smart_x" in smart_res and smart_res["smart_x"] is not None:
        sx = float(smart_res["smart_x"])
        sy = float(smart_res["smart_y"])
        sw = float(smart_res["smart_width"])
        sh = float(smart_res["smart_height"])
        block.smart_x = sx
        block.smart_y = sy
        block.smart_width = sw
        block.smart_height = sh

        if smart_res.get("success") and sw > 10.0 and sh > 10.0:
            block.x = sx
            block.y = sy
            block.width = sw
            block.height = sh

        if "crop_mask" in smart_res and smart_res["crop_mask"] is not None:
            masks_dir = Path(img_path).parent / "masks"
            masks_dir.mkdir(parents=True, exist_ok=True)
            mask_file = masks_dir / f"mask_{block.id}.png"
            cv2_imwrite_unicode(str(mask_file), smart_res["crop_mask"])
            block.smart_mask_path = str(mask_file)

    meta = dict(block.extra_metadata or {})
    meta["manual_font_size"] = None
    meta["font_size_mode"] = "auto"
    meta["contour_layout"] = True
    meta.pop("typesetting_spec", None)
    if "text_bbox" not in meta:
        meta["text_bbox"] = bbox
    if smart_res.get("success") and "smart_x" in smart_res:
        meta["layout_region"] = {
            "x": float(smart_res["smart_x"]),
            "y": float(smart_res["smart_y"]),
            "width": float(smart_res["smart_width"]),
            "height": float(smart_res["smart_height"]),
            "shape": str(smart_res.get("archetype", "bubble")).lower(),
            "source": "smart_balloon_v15",
            "confidence": 0.95,
            "version": "1.0.0",
        }
        meta["smart_balloon"] = {
            "archetype": smart_res.get("archetype", "UNKNOWN"),
            "method": smart_res.get("method", "smart_balloon_v15"),
            "safe_bbox": smart_res.get("safe_bbox"),
            "raw_bbox": smart_res.get("raw_bbox"),
            "center": smart_res.get("center"),
            "contour_points": smart_res.get("contour_points"),
            "raw_contour_points": smart_res.get("raw_contour_points"),
            "metadata": smart_res.get("metadata", {}),
        }
    block.extra_metadata = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(block, "extra_metadata")

    from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
    try:
        spec = compute_block_typesetting(block)
        persist_typesetting_spec(block, spec)
        flag_modified(block, "extra_metadata")
    except Exception as exc:
        logger.warning(f"Typesetting recompute failed for block {block.id}: {exc}")

    db.commit()
    db.refresh(block)

    try:
        from app.services.project_serializer import save_project_json
        if page and page.project:
            save_project_json(page.project.id, db=db)
    except Exception as exc:
        logger.warning(f"Failed to update project manifest after single smart balloon recompute: {exc}")

    return {
        "status": "success",
        "block_id": block.id,
        "smart_x": block.smart_x,
        "smart_y": block.smart_y,
        "smart_width": block.smart_width,
        "smart_height": block.smart_height,
        "smart_mask_path": block.smart_mask_path,
        "message": f"Successfully recomputed Smart Balloon bounds for block {block.id}!",
    }
