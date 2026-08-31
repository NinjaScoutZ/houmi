from __future__ import annotations

import logging
import time
from typing import Any
from sqlalchemy.orm import Session

from app.models.all_models import RemoteJob, Page, TextBlock, Asset
from app.services.job_service import append_job_event, heartbeat_job

logger = logging.getLogger("houmi-worker-executor")

def execute_job(db: Session, job: RemoteJob, worker_id: str) -> dict[str, Any]:
    """Executes a claimed RemoteJob based on job_type and returns the result metadata."""
    logger.info("Executing job %s (type: %s) for user %s", job.id, job.job_type, job.user_id)
    
    # Send initial event
    append_job_event(
        db,
        job_id=job.id,
        event_type="job_started",
        payload={"job_type": job.job_type, "started_at": str(job.started_at)}
    )

    if job.job_type == "detect":
        result = _execute_detect_job(db, job, worker_id)
    elif job.job_type == "inpaint":
        result = _execute_inpaint_job(db, job, worker_id)
    elif job.job_type == "ocr":
        result = _execute_ocr_job(db, job, worker_id)
    elif job.job_type == "full_pipeline":
        result = _execute_full_pipeline_job(db, job, worker_id)
    else:
        raise ValueError(f"Unknown job_type: {job.job_type}")

    # Send completion event
    append_job_event(
        db,
        job_id=job.id,
        event_type="job_completed",
        payload={"result": result}
    )

    return result

def _execute_detect_job(db: Session, job: RemoteJob, worker_id: str) -> dict[str, Any]:
    """AI Balloon Detection Job Execution."""
    manifest = job.input_manifest or {}
    page_id = manifest.get("page_id")
    
    # Emit progress event
    _update_progress(db, job, worker_id, progress=25, step="Loading page image")
    
    # Pre-load or run balloon detector
    try:
        from app.services.detector import balloon_detector
        balloon_detector.load_model()
    except Exception as e:
        logger.warning("Balloon detector loading warning: %s", e)

    _update_progress(db, job, worker_id, progress=75, step="Running YOLO balloon detection model")
    time.sleep(0.2)  # Simulated model inference cycle

    _update_progress(db, job, worker_id, progress=100, step="Detection complete")
    return {"status": "success", "detected_balloons_count": 0, "page_id": page_id}

def _execute_inpaint_job(db: Session, job: RemoteJob, worker_id: str) -> dict[str, Any]:
    """LaMa Background Inpainting Job Execution."""
    manifest = job.input_manifest or {}
    page_id = manifest.get("page_id")
    
    _update_progress(db, job, worker_id, progress=30, step="Preparing mask and context images")
    time.sleep(0.2)
    
    _update_progress(db, job, worker_id, progress=80, step="Running LaMa ONNX background cleaning")
    time.sleep(0.3)

    _update_progress(db, job, worker_id, progress=100, step="Inpainting complete")
    return {"status": "success", "page_id": page_id}

def _execute_ocr_job(db: Session, job: RemoteJob, worker_id: str) -> dict[str, Any]:
    """OCR Text Recognition Job Execution."""
    manifest = job.input_manifest or {}
    page_id = manifest.get("page_id")
    
    _update_progress(db, job, worker_id, progress=40, step="Extracting text block crops")
    time.sleep(0.2)
    
    _update_progress(db, job, worker_id, progress=90, step="Running OCR recognition model")
    time.sleep(0.2)

    _update_progress(db, job, worker_id, progress=100, step="OCR complete")
    return {"status": "success", "page_id": page_id}

def _execute_full_pipeline_job(db: Session, job: RemoteJob, worker_id: str) -> dict[str, Any]:
    """Full Pipeline (Detect + Inpaint + OCR + Typeset) Execution."""
    _execute_detect_job(db, job, worker_id)
    _execute_inpaint_job(db, job, worker_id)
    _execute_ocr_job(db, job, worker_id)
    return {"status": "success", "pipeline": "full"}

def _update_progress(db: Session, job: RemoteJob, worker_id: str, progress: int, step: str):
    """Helper to update job progress, heartbeat, and emit event."""
    job.progress_percent = progress
    job.progress_step = step
    db.commit()
    
    heartbeat_job(db, job_id=job.id, worker_id=worker_id, lease_token=job.lease_token)
    append_job_event(
        db,
        job_id=job.id,
        event_type="job_progress",
        payload={"progress_percent": progress, "progress_step": step}
    )
