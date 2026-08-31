"""
GPU & System Memory Monitor with Automatic Garbage Collection & OOM Prevention
"""

from __future__ import annotations

import gc
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("houmi-gpu-monitor")

try:
    import psutil
except ImportError:
    psutil = None


def get_gpu_memory_status() -> Dict[str, Any]:
    """
    Returns live memory metrics for CUDA GPU (if available) and system RAM.
    """
    status: Dict[str, Any] = {
        "cuda_available": False,
        "device_name": "CPU",
        "device_count": 0,
        "vram_total_mb": 0.0,
        "vram_allocated_mb": 0.0,
        "vram_reserved_mb": 0.0,
        "vram_free_mb": 0.0,
        "vram_usage_percent": 0.0,
        "system_ram_total_mb": 0.0,
        "system_ram_used_mb": 0.0,
        "system_ram_usage_percent": 0.0,
    }

    # System RAM
    if psutil:
        mem = psutil.virtual_memory()
        status["system_ram_total_mb"] = round(mem.total / (1024 * 1024), 2)
        status["system_ram_used_mb"] = round(mem.used / (1024 * 1024), 2)
        status["system_ram_usage_percent"] = mem.percent

    # CUDA GPU Telemetry
    try:
        import torch
        if torch.cuda.is_available():
            status["cuda_available"] = True
            status["device_count"] = torch.cuda.device_count()
            status["device_name"] = torch.cuda.get_device_name(0)

            total = torch.cuda.get_device_properties(0).total_memory
            allocated = torch.cuda.memory_allocated(0)
            reserved = torch.cuda.memory_reserved(0)
            free = total - reserved

            status["vram_total_mb"] = round(total / (1024 * 1024), 2)
            status["vram_allocated_mb"] = round(allocated / (1024 * 1024), 2)
            status["vram_reserved_mb"] = round(reserved / (1024 * 1024), 2)
            status["vram_free_mb"] = round(free / (1024 * 1024), 2)
            status["vram_usage_percent"] = round((reserved / total) * 100, 2) if total > 0 else 0.0
    except Exception as exc:
        logger.debug(f"PyTorch CUDA query failed: {exc}")

    return status


def force_garbage_collection() -> Dict[str, Any]:
    """Force Python garbage collection and release all PyTorch CUDA cached memory."""
    gc.collect()
    cuda_freed = False

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
            cuda_freed = True
    except Exception as e:
        logger.debug(f"PyTorch empty_cache error: {e}")

    logger.info("Executed force garbage collection and memory cache flush.")
    return {
        "gc_collected": True,
        "cuda_cache_freed": cuda_freed,
        "status_after": get_gpu_memory_status(),
    }


def check_vram_and_auto_gc(threshold_ratio: float = 0.85) -> bool:
    """
    Checks if VRAM utilization exceeds threshold_ratio.
    If true, automatically flushes cache to prevent Out-Of-Memory (OOM) errors.
    Returns True if auto-GC was triggered.
    """
    status = get_gpu_memory_status()
    if not status.get("cuda_available"):
        return False

    usage_percent = status.get("vram_usage_percent", 0.0)
    if usage_percent >= (threshold_ratio * 100):
        logger.warning(
            f"⚠️ High VRAM usage detected ({usage_percent}% >= {threshold_ratio * 100}%). Triggering auto-GC..."
        )
        force_garbage_collection()
        return True
    return False
