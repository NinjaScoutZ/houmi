"""
Comprehensive Subsystem Health Checker
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from typing import Any, Dict

from app.config import DATA_DIR, RUNTIME_MODE
from app.telemetry.gpu_monitor import get_gpu_memory_status
from app.telemetry.pipeline_queue import pipeline_tracker


def get_system_health() -> Dict[str, Any]:
    """
    Assembles real-time diagnostics across:
    - GPU/CUDA VRAM status
    - System disk space
    - Pipeline queue metrics
    - Database connectivity
    """
    # Disk Space Check
    disk_total_gb = 0.0
    disk_free_gb = 0.0
    try:
        usage = shutil.disk_usage(DATA_DIR)
        disk_total_gb = round(usage.total / (1024 ** 3), 2)
        disk_free_gb = round(usage.free / (1024 ** 3), 2)
    except Exception:
        pass

    # Database ping
    db_status = "ok"
    try:
        from app.core.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    gpu_info = get_gpu_memory_status()
    queue_info = pipeline_tracker.get_metrics().model_dump()

    is_healthy = (db_status == "ok") and (disk_free_gb > 0.5)

    return {
        "status": "healthy" if is_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "runtime_mode": RUNTIME_MODE,
        "database": db_status,
        "disk": {
            "total_gb": disk_total_gb,
            "free_gb": disk_free_gb,
            "low_disk_warning": disk_free_gb < 1.0,
        },
        "hardware": gpu_info,
        "queue": queue_info,
    }
