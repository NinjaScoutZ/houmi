# Parallel Inpainting Implementation
# backend/app/services/parallel_inpaint.py

"""
Parallel inpainting to speed up cleaning process by processing multiple regions concurrently.
Uses ThreadPoolExecutor to leverage multi-core CPUs.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
import numpy as np
import cv2

logger = logging.getLogger("houmi-parallel-inpaint")


def get_optimal_worker_count(settings: dict) -> int:
    """
    Calculate optimal number of workers based on settings and hardware.
    Syncs with Global Settings auto-optimization (CUDA/DirectML/CPU detection).
    """
    # User-configured worker count (from project settings or performance preset)
    configured = settings.get("parallel_inpaint_workers", 0)
    if configured > 0:
        return min(configured, 8)  # Cap at 8 to avoid memory issues

    # Load global hardware optimization settings
    try:
        from app.config import get_execution_providers
        from app.services.ai_provider_settings import _load_raw_settings

        global_settings = _load_raw_settings()
        optimal_thread_count = global_settings.get("optimal_thread_count")
        execution_provider = global_settings.get("execution_provider", "DirectML")

        # Get active ONNX providers to detect hardware
        active_providers = get_execution_providers()
        primary_provider = active_providers[0] if active_providers else "CPUExecutionProvider"

        # Adjust worker count based on acceleration type
        cpu_count = os.cpu_count() or 2

        # CUDA/DirectML: GPU-accelerated inpainting can handle more parallel workers
        if primary_provider in ("CUDAExecutionProvider", "DmlExecutionProvider"):
            # GPU handles heavy lifting, so we can spawn more workers
            base_workers = max(3, min(6, cpu_count // 2))
            logger.info(f"GPU acceleration detected ({primary_provider}), using {base_workers} workers")
            return base_workers

        # CPU-only: Conservative worker count to prevent 100% CPU lockup
        else:
            # Use global optimal_thread_count if available, otherwise fallback
            if optimal_thread_count and isinstance(optimal_thread_count, int):
                base_workers = max(2, min(4, optimal_thread_count // 2))
            else:
                base_workers = max(2, min(3, cpu_count // 3))
            logger.info(f"CPU-only mode detected, using conservative {base_workers} workers")
            return base_workers

    except Exception as e:
        logger.warning(f"Failed to load global hardware settings, using fallback: {e}")
        # Fallback: Conservative default
        cpu_count = os.cpu_count() or 2
        return max(2, min(3, cpu_count // 2))


def inpaint_regions_parallel(
    img: np.ndarray,
    mask: np.ndarray,
    regions: list[tuple[int, int, int, int]],
    inpaint_service: Any,
    settings: dict,
    cancel_check: Callable[[], bool] | None = None,
) -> np.ndarray:
    """
    Inpaint multiple regions in parallel using ThreadPoolExecutor.

    Automatically syncs with Global Settings hardware optimization:
    - Detects CUDA/DirectML/CPU execution providers
    - Adjusts worker count based on available hardware
    - Prevents 100% CPU lockup on CPU-only systems

    Args:
        img: Source image (will be copied)
        mask: Full-page mask
        regions: List of (x, y, w, h) tuples
        inpaint_service: Inpainting service (LaMa, MAT, or None for Telea)
        settings: Project settings
        cancel_check: Optional function to check if operation should be cancelled

    Returns:
        Cleaned image with all regions inpainted
    """
    if not settings.get("parallel_inpaint_enabled", True):
        # Fallback to sequential processing
        logger.info("Parallel inpainting disabled in project settings, using sequential mode")
        return _inpaint_regions_sequential(img, mask, regions, inpaint_service, settings, cancel_check)

    img_cleaned = img.copy()
    h, w = img.shape[:2]

    max_workers = get_optimal_worker_count(settings)
    context_padding = max(0, min(512, int(settings.get("inpaint_context_padding", 96))))
    tile_threshold = settings.get("inpaint_tile_size", 1024)

    # Log hardware configuration for debugging
    try:
        from app.config import get_execution_providers
        active_providers = get_execution_providers()
        primary_provider = active_providers[0] if active_providers else "Unknown"
        logger.info(
            f"Starting parallel inpainting: {len(regions)} regions, "
            f"{max_workers} workers, Provider: {primary_provider}"
        )
    except Exception:
        logger.info(f"Starting parallel inpainting with {max_workers} workers for {len(regions)} regions")

    # Prepare tasks
    tasks = []
    for idx, (cx, cy, cw, ch) in enumerate(regions):
        task = {
            "idx": idx,
            "region": (cx, cy, cw, ch),
            "cx": cx,
            "cy": cy,
            "cw": cw,
            "ch": ch,
        }
        tasks.append(task)

    # Process regions in parallel
    completed_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {}
        for task in tasks:
            if cancel_check and cancel_check():
                logger.info("Parallel inpainting cancelled before submission")
                raise RuntimeError("Inpainting cancelled by user")

            future = executor.submit(
                _inpaint_single_region,
                img,
                mask,
                task,
                inpaint_service,
                context_padding,
                tile_threshold,
                h,
                w,
            )
            future_to_task[future] = task

        # Collect results as they complete
        for future in as_completed(future_to_task):
            if cancel_check and cancel_check():
                logger.info("Parallel inpainting cancelled during processing")
                # Cancel remaining futures
                for f in future_to_task:
                    f.cancel()
                raise RuntimeError("Inpainting cancelled by user")

            task = future_to_task[future]
            try:
                result = future.result()
                if result is not None:
                    # Composite result back into main image
                    bx0, by0, bx1, by1, inpainted_crop = result
                    img_cleaned[by0:by1, bx0:bx1] = inpainted_crop
                    completed_count += 1

                    if completed_count % 5 == 0:
                        logger.info(f"Completed {completed_count}/{len(regions)} regions")

            except Exception as e:
                logger.error(f"Failed to inpaint region {task['idx']}: {e}")
                # Continue with other regions

    logger.info(f"Parallel inpainting completed: {completed_count}/{len(regions)} regions")
    return img_cleaned


def _inpaint_single_region(
    img: np.ndarray,
    mask: np.ndarray,
    task: dict,
    inpaint_service: Any,
    context_padding: int,
    tile_threshold: int,
    h: int,
    w: int,
) -> tuple[int, int, int, int, np.ndarray] | None:
    """
    Inpaint a single region (executed in worker thread).

    Returns:
        Tuple of (bx0, by0, bx1, by1, inpainted_crop) or None if skipped
    """
    from app.services.inpainter import (
        _effective_inpaint_context_padding,
        _detect_uniform_fill_color,
        _tile_based_inpaint,
    )

    cx, cy, cw, ch = task["cx"], task["cy"], task["cw"], task["ch"]
    cx1, cy1 = cx + cw, cy + ch

    # Calculate padded crop bounds
    pad = _effective_inpaint_context_padding(context_padding, cw, ch)
    bx0 = max(0, cx - pad)
    by0 = max(0, cy - pad)
    bx1 = min(w, cx1 + pad)
    by1 = min(h, cy1 + pad)

    crop_w = bx1 - bx0
    crop_h = by1 - by0

    if crop_w <= 0 or crop_h <= 0:
        return None

    # Make crop square for deep learning models
    diff = abs(crop_w - crop_h)
    pad_half = diff // 2
    if crop_w > crop_h:
        by0 = max(0, by0 - pad_half)
        by1 = min(h, by1 + (diff - pad_half))
    else:
        bx0 = max(0, bx0 - pad_half)
        bx1 = min(w, bx1 + (diff - pad_half))

    # Extract crop (thread-safe read)
    crop_img = img[by0:by1, bx0:bx1].copy()
    crop_mask = mask[by0:by1, bx0:bx1].copy()

    if np.count_nonzero(crop_mask) == 0:
        return None

    # Inpaint with neural AI model (LaMa / MAT) or Telea fallback
    try:
        if inpaint_service is not None:
            crop_h, crop_w = crop_img.shape[:2]

            if max(crop_h, crop_w) > tile_threshold:
                inpainted_crop = _tile_based_inpaint(
                    crop_img,
                    crop_mask,
                    inpaint_service,
                    tile_size=tile_threshold,
                    overlap=64
                )
            else:
                inpainted_crop = inpaint_service.inpaint(crop_img, crop_mask)

            if inpainted_crop is not None:
                mask_indices = crop_mask > 0
                if np.any(mask_indices):
                    crop_img[mask_indices] = inpainted_crop[mask_indices]
        else:
            # Telea fallback
            inpainted_crop = cv2.inpaint(
                crop_img,
                crop_mask,
                inpaintRadius=4,
                flags=cv2.INPAINT_TELEA,
            )
            mask_indices = crop_mask > 0
            if np.any(mask_indices):
                crop_img[mask_indices] = inpainted_crop[mask_indices]

    except Exception as e:
        logger.error(f"Inpainting failed for region at ({cx}, {cy}): {e}")
        # Telea fallback
        try:
            inpainted_crop = cv2.inpaint(
                crop_img,
                crop_mask,
                inpaintRadius=4,
                flags=cv2.INPAINT_TELEA,
            )
            mask_indices = crop_mask > 0
            if np.any(mask_indices):
                crop_img[mask_indices] = inpainted_crop[mask_indices]
        except Exception as e2:
            logger.error(f"Telea fallback also failed: {e2}")
            return None

    return (bx0, by0, bx1, by1, crop_img)


def _inpaint_regions_sequential(
    img: np.ndarray,
    mask: np.ndarray,
    regions: list[tuple[int, int, int, int]],
    inpaint_service: Any,
    settings: dict,
    cancel_check: Callable[[], bool] | None = None,
) -> np.ndarray:
    """
    Sequential inpainting (original implementation).
    Used as fallback when parallel is disabled.
    """
    from app.services.inpainter import (
        _effective_inpaint_context_padding,
        _detect_uniform_fill_color,
        _tile_based_inpaint,
    )

    img_cleaned = img.copy()
    h, w = img.shape[:2]
    context_padding = max(0, min(512, int(settings.get("inpaint_context_padding", 96))))
    tile_threshold = settings.get("inpaint_tile_size", 1024)

    for cx, cy, cw, ch in regions:
        if cancel_check and cancel_check():
            raise RuntimeError("Inpainting cancelled by user")

        result = _inpaint_single_region(
            img_cleaned,
            mask,
            {"cx": cx, "cy": cy, "cw": cw, "ch": ch},
            inpaint_service,
            context_padding,
            tile_threshold,
            h,
            w,
        )

        if result is not None:
            bx0, by0, bx1, by1, inpainted_crop = result
            img_cleaned[by0:by1, bx0:bx1] = inpainted_crop

    return img_cleaned
