# Houmi Host Runbook

## Process layout

Run database migration before starting the API:

```powershell
$env:HOUMI_RUNTIME_MODE = "host"
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 4000
```

Run the GPU/OCR process separately on the machine that owns the accelerator:

```powershell
$env:HOUMI_RUNTIME_MODE = "worker"
python -m app.worker_runtime
```

The Host API must not receive the worker secret through browser-exposed
configuration. Put it in the service environment or a secret manager. The
reverse proxy should terminate TLS and forward `/api`, `/ws`, and static paths
to the API process.

## Recovery

Workers claim jobs with a lease. A worker restart leaves expired jobs eligible
for recovery; an administrator can call `POST /api/admin/jobs/recover` after
confirming the worker outage. The endpoint records the action in the audit log.

## Backup minimum

Back up PostgreSQL with point-in-time/WAL retention and back up
`DATA_DIR/assets` (or its object-storage equivalent) with the same project/job
retention policy. Restoring only the database or only the asset files produces
incomplete jobs, so restore tests must verify both sides and a sample download.
