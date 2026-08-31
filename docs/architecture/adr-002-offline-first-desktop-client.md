# ADR-002: Offline-first desktop client with a local engine

## Status

Accepted

## Context

Houmi already has a React/Vite editor and a Python FastAPI runtime that uses
SQLite in `local` mode and PostgreSQL in `host` mode. Customers must be able
to open projects, edit pages, save work, and perform supported local operations
without an Internet connection. Heavy GPU work and cloud sync should remain
available when a connection exists.

## Decision

Ship a Tauri 2 desktop client with two local processes:

1. The Tauri UI bundles the React/Vite build and targets
   `http://127.0.0.1:4317` in the desktop runtime.
2. A `houmi-local` sidecar runs the existing FastAPI local runtime with
   SQLite, local asset storage, and local model access.
3. The local sidecar stores user data under the per-user AppData directory,
   not beside the installed executable.
4. The same API contract is used for the local engine and the remote Host.
5. Cloud synchronization is an explicit later layer with an outbox,
   idempotency keys, revisions, checksums, and conflict review; it must not
   silently overwrite local edits.

## Rationale

- Reuses the existing local runtime instead of duplicating persistence logic
  in the browser or Tauri Rust layer.
- Keeps offline data local and private while preserving the existing Host/GPU
  architecture for expensive jobs.
- Tauri can bundle the local Python executable as a sidecar, so customers do
  not need Python installed.
- Per-user AppData survives application upgrades and avoids write failures in
  protected installation directories.

## Trade-offs

- The offline installer is larger when local AI models are included.
- A sidecar adds process lifecycle and packaging work.
- Local and remote data synchronization still needs a deliberate conflict
  policy; it is not safe to invent a generic last-write-wins merge for pages.

## Revisit triggers

- Offline OCR/GPU requirements exceed acceptable installer size or local
  hardware capability.
- The product needs macOS/Linux distribution with platform-specific local
  model packaging.
- Multi-device simultaneous editing becomes a core workflow and requires
  structured document merge semantics.
