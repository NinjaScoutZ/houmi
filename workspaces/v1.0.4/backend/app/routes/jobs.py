from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import MAX_ACTIVE_REMOTE_JOBS_PER_USER
from app.models.all_models import JobEvent, RemoteJob, User
from app.security.dependencies import get_authenticated_user, require_pipeline_access, require_resource_access, require_worker
from app.services.job_service import create_job, request_job_cancel


router = APIRouter(tags=["Jobs"])


class JobCreateRequest(BaseModel):
    project_id: str
    job_type: str = Field(pattern="^(detect|inpaint|ocr|full_pipeline)$")
    input_manifest: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=64)
    max_attempts: int = Field(default=3, ge=1, le=5)


class JobHeartbeatRequest(BaseModel):
    lease_token: str
    lease_seconds: int = Field(default=60, ge=10, le=600)


def _job_payload(job: RemoteJob) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress_percent": job.progress_percent,
        "progress_step": job.progress_step,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "result_asset_id": job.result_asset_id,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def enqueue_job(
    request: JobCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_pipeline_access),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if request.idempotency_key:
        existing = db.query(RemoteJob).filter(
            RemoteJob.user_id == current_user.id,
            RemoteJob.idempotency_key == request.idempotency_key,
        ).first()
        if existing is not None:
            return _job_payload(existing)
    active_jobs = db.query(func.count(RemoteJob.id)).filter(
        RemoteJob.user_id == current_user.id,
        RemoteJob.status.in_(("queued", "processing")),
    ).scalar() or 0
    if int(active_jobs) >= MAX_ACTIVE_REMOTE_JOBS_PER_USER:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Remote job quota exceeded")
    try:
        job = create_job(
            db,
            user_id=current_user.id,
            project_id=request.project_id,
            job_type=request.job_type,
            input_manifest=request.input_manifest,
            idempotency_key=request.idempotency_key,
            max_attempts=request.max_attempts,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _job_payload(job)


@router.get("/jobs")
def list_jobs(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    query = db.query(RemoteJob).filter(RemoteJob.user_id == current_user.id)
    if project_id:
        query = query.filter(RemoteJob.project_id == project_id)
    return [_job_payload(job) for job in query.order_by(RemoteJob.created_at.desc()).limit(100).all()]


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    _: User = Depends(require_resource_access),
):
    job = db.query(RemoteJob).filter(RemoteJob.id == job_id, RemoteJob.user_id == current_user.id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_payload(job)


@router.get("/jobs/{job_id}/events")
def get_job_events(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    _: User = Depends(require_resource_access),
):
    job = db.query(RemoteJob).filter(RemoteJob.id == job_id, RemoteJob.user_id == current_user.id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    events = db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.sequence_num.asc()).all()
    return [
        {"sequence_num": event.sequence_num, "event_type": event.event_type, "payload": event.payload_json, "created_at": event.created_at}
        for event in events
    ]


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    _: User = Depends(require_resource_access),
):
    try:
        job = request_job_cancel(db, job_id=job_id, user_id=current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _job_payload(job)


@router.post("/internal/jobs/claim")
def claim_job(
    worker_id: str = Header(..., alias="X-Worker-Id"),
    _: None = Depends(require_worker),
    db: Session = Depends(get_db),
):
    from app.services.job_service import claim_next_job

    job = claim_next_job(db, worker_id=worker_id)
    return _job_payload(job) if job else None


@router.post("/internal/jobs/{job_id}/heartbeat")
def heartbeat_job(
    job_id: str,
    request: JobHeartbeatRequest,
    worker_id: str = Header(..., alias="X-Worker-Id"),
    _: None = Depends(require_worker),
    db: Session = Depends(get_db),
):
    from app.services.job_service import heartbeat_job as update_heartbeat

    ok = update_heartbeat(
        db,
        job_id=job_id,
        worker_id=worker_id,
        lease_token=request.lease_token,
        lease_seconds=request.lease_seconds,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job lease is no longer valid")
    return {"ok": True}
