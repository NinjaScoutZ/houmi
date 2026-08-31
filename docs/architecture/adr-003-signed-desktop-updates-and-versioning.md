# ADR-003: Signed desktop updates and one visible version

- Status: Accepted
- Date: 2026-08-04

## Context

Houmi Studio is distributed as a Windows Tauri installer, while the local
engine is packaged as a sidecar. Customers need offline operation and a safe
way to receive fixes without downloading an arbitrary executable. The UI also
needs to tell support staff exactly which build is running.

## Decision

Use Tauri's updater plugin for signed full-package update artifacts. Use
SemVer (`MAJOR.MINOR.PATCH`) for the customer-facing release version. Vite
injects the version from `frontend/package.json`, and
`deploy/set-version.ps1` synchronizes the package lock, Tauri config, and Rust
crate metadata before a release.

The normal development/installer configuration leaves updater artifacts off.
`deploy/build-patch.ps1` enables them only when the release environment
contains a public key, HTTPS endpoint, and private signing key. The private
key never enters the repository or the generated temporary config.

## Consequences

- A Patch is authenticated and can be installed from the UI after a check.
- Update delivery is a signed package, not a binary-delta patch; this is safer
  and simpler for the Tauri sidecar/installer boundary.
- A real release endpoint and durable signing-key storage are operational
  requirements before enabling auto-update for customers.
- Offline mode remains usable when no update endpoint is reachable; the
  updater is simply skipped or reports that no check was possible.
