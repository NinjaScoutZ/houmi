"""
Houmi Studio - Application Lifespan Events & Lifecycle Hooks
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

logger = logging.getLogger("houmi-core-events")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application startup and graceful shutdown lifecycle context.
    Executes hardware verification on boot and frees GPU resources on shutdown.
    """
    # ── Startup ──
    logger.info("🚀 Houmi Production Backend initializing...")
    try:
        from app.telemetry.gpu_monitor import get_gpu_memory_status
        status = get_gpu_memory_status()
        logger.info(f"Hardware Status: {status.get('device_name', 'CPU')} (CUDA: {status.get('cuda_available')})")
    except Exception as e:
        logger.warning(f"Initial GPU telemetry check skipped: {e}")

    yield

    # ── Shutdown ──
    logger.info("🛑 Houmi Production Backend shutting down...")
    try:
        from app.telemetry.gpu_monitor import force_garbage_collection
        force_garbage_collection()
        logger.info("GPU VRAM and system caches flushed cleanly.")
    except Exception as e:
        logger.warning(f"Shutdown cleanup skipped: {e}")
