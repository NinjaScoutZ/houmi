"""
Worker & Pipeline Job Queue Telemetry Tracker
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PipelineMetrics(BaseModel):
    active_jobs: int = 0
    pending_jobs: int = 0
    completed_jobs_total: int = 0
    failed_jobs_total: int = 0
    avg_latency_ms: float = 0.0
    throughput_per_min: float = 0.0
    recent_errors: List[Dict[str, Any]] = Field(default_factory=list)


class PipelineQueueTracker:
    """In-memory telemetry tracker for AI worker jobs and translation pipeline."""

    def __init__(self, max_history: int = 100):
        self._pending = 0
        self._active = 0
        self._completed_total = 0
        self._failed_total = 0
        self._latencies = deque(maxlen=50)
        self._completed_timestamps = deque(maxlen=max_history)
        self._errors = deque(maxlen=20)

    def job_submitted(self) -> None:
        self._pending += 1

    def job_started(self) -> None:
        if self._pending > 0:
            self._pending -= 1
        self._active += 1

    def job_completed(self, latency_ms: float) -> None:
        if self._active > 0:
            self._active -= 1
        self._completed_total += 1
        self._latencies.append(latency_ms)
        self._completed_timestamps.append(time.time())

    def job_failed(self, error_message: str, stage: str = "pipeline") -> None:
        if self._active > 0:
            self._active -= 1
        self._failed_total += 1
        self._errors.append({
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "error": str(error_message)[:200],
        })

    def get_metrics(self) -> PipelineMetrics:
        now = time.time()
        # Compute throughput in last 60 seconds
        recent_count = sum(1 for ts in self._completed_timestamps if now - ts <= 60.0)
        avg_lat = round(sum(self._latencies) / len(self._latencies), 2) if self._latencies else 0.0

        return PipelineMetrics(
            active_jobs=self._active,
            pending_jobs=self._pending,
            completed_jobs_total=self._completed_total,
            failed_jobs_total=self._failed_total,
            avg_latency_ms=avg_lat,
            throughput_per_min=float(recent_count),
            recent_errors=list(self._errors),
        )


pipeline_tracker = PipelineQueueTracker()
