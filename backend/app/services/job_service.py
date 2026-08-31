from __future__ import annotations

import datetime
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.all_models import JobEvent, Project, RemoteJob


JOB_STATUSES = {"queued", "processing", "completed", "failed", "cancelled"}
JOB_TYPES = {"detect", "inpaint", "ocr", "full_pipeline"}


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def create_job(
    db: Session,
    *,
    user_id: str,
    project_id: str,
    job_type: str,
    input_manifest: dict,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> RemoteJob:
    if job_type not in JOB_TYPES:
        raise ValueError("Unsupported job type")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None or project.owner_id != user_id:
        raise LookupError("Project not found")

    if idempotency_key:
        existing = (
            db.query(RemoteJob)
            .filter(RemoteJob.user_id == user_id, RemoteJob.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return existing

    job = RemoteJob(
        user_id=user_id,
        project_id=project_id,
        job_type=job_type,
        status="queued",
        input_manifest=input_manifest,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next_job(db: Session, *, worker_id: str, lease_seconds: int = 60) -> RemoteJob | None:
    now = utcnow()
    job = (
        db.query(RemoteJob)
        .filter(RemoteJob.status == "queued")
        .order_by(RemoteJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None

    job.status = "processing"
    job.worker_id = worker_id
    job.lease_token = str(uuid.uuid4())
    job.lease_expires_at = now + datetime.timedelta(seconds=lease_seconds)
    job.heartbeat_at = now
    job.started_at = job.started_at or now
    job.attempt_count += 1
    db.commit()
    db.refresh(job)
    return job


def heartbeat_job(
    db: Session,
    *,
    job_id: str,
    worker_id: str,
    lease_token: str,
    lease_seconds: int = 60,
) -> bool:
    now = utcnow()
    updated = (
        db.query(RemoteJob)
        .filter(
            RemoteJob.id == job_id,
            RemoteJob.status == "processing",
            RemoteJob.worker_id == worker_id,
            RemoteJob.lease_token == lease_token,
        )
        .update(
            {
                RemoteJob.heartbeat_at: now,
                RemoteJob.lease_expires_at: now + datetime.timedelta(seconds=lease_seconds),
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return updated == 1


def recover_expired_jobs(db: Session) -> list[str]:
    now = utcnow()
    stale_before = now - datetime.timedelta(seconds=45)
    jobs = (
        db.query(RemoteJob)
        .filter(
            RemoteJob.status == "processing",
            RemoteJob.lease_expires_at < now,
            (RemoteJob.heartbeat_at.is_(None) | (RemoteJob.heartbeat_at < stale_before)),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    recovered: list[str] = []
    for job in jobs:
        if job.attempt_count >= job.max_attempts:
            job.status = "failed"
            job.error_code = "worker_lost"
            job.error_message = "Worker lease expired too many times"
            job.finished_at = now
        else:
            job.status = "queued"
            job.worker_id = None
            job.lease_token = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            recovered.append(job.id)
    db.commit()
    return recovered


def append_job_event(db: Session, *, job_id: str, event_type: str, payload: dict) -> JobEvent:
    job = db.query(RemoteJob).filter(RemoteJob.id == job_id).with_for_update().first()
    if job is None:
        raise LookupError("Job not found")
    sequence = (
        db.query(func.max(JobEvent.sequence_num))
        .filter(JobEvent.job_id == job_id)
        .scalar()
    )
    event = JobEvent(
        job_id=job_id,
        sequence_num=(sequence + 1) if sequence is not None else 0,
        event_type=event_type,
        payload_json=payload,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def request_job_cancel(db: Session, *, job_id: str, user_id: str) -> RemoteJob:
    job = db.query(RemoteJob).filter(RemoteJob.id == job_id, RemoteJob.user_id == user_id).first()
    if job is None:
        raise LookupError("Job not found")
    if job.status == "queued":
        job.status = "cancelled"
        job.cancelled_at = utcnow()
    elif job.status == "processing":
        job.cancel_requested = True
    db.commit()
    db.refresh(job)
    return job
