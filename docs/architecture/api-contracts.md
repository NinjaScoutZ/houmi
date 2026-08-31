# Remote API Contracts

All Remote calls use `Authorization: Bearer <access_token>`. The browser gets a
short-lived access token and rotates a refresh token through
`POST /api/auth/refresh`; WebSocket connections use a single-use ticket from
`POST /api/auth/ws-ticket` rather than putting a reusable JWT in the URL.

## Assets

- `POST /api/assets?project_id=<id>` — multipart field `file`; validates magic
  bytes, decoded dimensions, and the 100 MB/pixel budgets before storage.
- `GET /api/assets?project_id=<id>` — returns only the authenticated user's
  active assets.
- `GET /api/assets/{asset_id}` — metadata; foreign assets return 404.
- `GET /api/assets/{asset_id}/download` — content stream after the same owner
  check.
- `DELETE /api/assets/{asset_id}` — soft-delete metadata; content cleanup can
  be handled by retention tooling.

## Jobs

`POST /api/jobs` accepts:

```json
{
  "project_id": "<uuid>",
  "job_type": "ocr",
  "input_manifest": {"asset_ids": ["<uuid>"]},
  "idempotency_key": "client-request-123",
  "max_attempts": 3
}
```

The response is `202` with the job identifier and current state. Repeating the
same request for one user and idempotency key returns the existing job. Users
can query `/api/jobs/{id}`, `/api/jobs/{id}/events`, or
`POST /api/jobs/{id}/cancel`.

Worker-only endpoints use `X-Houmi-Worker-Key` plus `X-Worker-Id`; the shared
key is never sent to browser code. Every heartbeat is fenced by worker ID and
lease token.
