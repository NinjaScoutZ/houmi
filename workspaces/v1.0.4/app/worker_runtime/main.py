from __future__ import annotations

import logging
import os
import sys
import time
import uuid

from app.database import SessionLocal
from app.services.job_service import claim_next_job, heartbeat_job, recover_expired_jobs, append_job_event
from app.worker_runtime.executor import execute_job

# Configure Logging for Worker Process
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker-%(process)d] %(name)s: %(message)s"
)
logger = logging.getLogger("houmi-worker")

WORKER_ID = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"

def run_worker_loop():
    """Main execution loop for GPU/OCR Worker Runtime."""
    logger.info("Starting Houmi Worker Runtime (ID: %s)...", WORKER_ID)
    
    poll_interval = 2.0
    last_watchdog_time = 0.0

    while True:
        try:
            db = SessionLocal()
            try:
                # Watchdog check every 30 seconds to recover expired jobs
                now_time = time.time()
                if now_time - last_watchdog_time > 30.0:
                    recovered = recover_expired_jobs(db)
                    if recovered:
                        logger.info("Watchdog recovered %d expired jobs: %s", len(recovered), recovered)
                    last_watchdog_time = now_time

                # Claim next queued job
                job = claim_next_job(db, worker_id=WORKER_ID, lease_seconds=60)
                if job:
                    logger.info("Claimed job %s (type: %s)", job.id, job.job_type)
                    try:
                        result = execute_job(db, job, WORKER_ID)
                        job.status = "completed"
                        job.progress_percent = 100
                        job.progress_step = "Completed"
                        job.finished_at = job.updated_at
                        db.commit()
                        logger.info("Job %s completed successfully.", job.id)
                    except Exception as exc:
                        logger.error("Job %s failed with exception: %s", job.id, exc, exc_info=True)
                        job.status = "failed"
                        job.error_code = "execution_error"
                        job.error_message = str(exc)
                        job.finished_at = job.updated_at
                        db.commit()
                        append_job_event(
                            db,
                            job_id=job.id,
                            event_type="job_failed",
                            payload={"error": str(exc)}
                        )
                else:
                    time.sleep(poll_interval)
            finally:
                db.close()
        except KeyboardInterrupt:
            logger.info("Worker process shutting down cleanly...")
            break
        except Exception as e:
            logger.error("Unexpected worker loop error: %s", e, exc_info=True)
            time.sleep(5.0)

if __name__ == "__main__":
    run_worker_loop()
