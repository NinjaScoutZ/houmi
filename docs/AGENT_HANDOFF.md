# Houmi Studio Agent Handoff

This is the working manual for the next Agent or developer taking over the
repository. Read this before changing packaging, networking, or offline
behavior.

## Current product shape

- React/Vite frontend: `frontend/`
- FastAPI backend: `backend/`
- Public/remote Host runtime: port `4000`; keep Host secrets out of the client
- Desktop app: Tauri 2 in `frontend/src-tauri/`
- Desktop local API: loopback only at `127.0.0.1:4317`
- Release data: SQLite and files under the frozen app data directory, not the
  installer directory
- Current customer version: `0.1.2`

The desktop app starts a Python `houmi-local` sidecar. The sidecar is not a
public server. Never change its bind address to `0.0.0.0`.

## Version and Patch workflow

The visible version is injected from `frontend/package.json` by
`frontend/vite.config.ts`. Use the helper to keep the other package metadata
aligned:

```powershell
.\deploy\set-version.ps1 -Version <new-version>
```

The updater integration is in `frontend/src/desktop/updater.ts` and
`frontend/src/components/PatchUpdateButton.tsx`. It is intentionally disabled
in the normal build until a real Tauri public key, HTTPS endpoint, and private
signing key are supplied. Follow [release-patch.md](release-patch.md) for a
signed release. Never commit the private key or paste it into a response.

Important distinction: the updater installs a signed full package. It is a
Patch release by SemVer, not a byte-level binary diff. The update manifest's
signature must be the contents of the generated `.sig` file.

## Gemini OCR

Image OCR uses the direct Gemini REST path in
`backend/app/services/ocr.py` when `GOOGLE_API_KEY` (or one of the documented
aliases) is present. The image is sent as base64 `inline_data`; the key never
goes to the frontend or into the EXE. Text-only prompts retain the `agy` CLI
path. If Gemini fails, the default backend fallback is disabled. Interactive OCR
failures are surfaced to the user and require an explicit retry, a switch to an
available local OCR engine (PaddleOCR, GLM-OCR, or DeepSeek-OCR), or cancel; do
not restore a silent fallback. The base frozen sidecar currently excludes Paddle
model packages, so verify the package flavor before claiming Paddle works
offline. Full details are in
[gemini-ocr.md](gemini-ocr.md).

## Local development

```powershell
cd E:\houmi\frontend
npm install
npm run dev
```

For a Tauri debug run, ensure `backend/.venv/Scripts/python.exe` exists; the
Rust debug app starts `backend/desktop_local.py` on loopback. For a packaged
sidecar:

```powershell
.\deploy\build-local-sidecar.ps1
.\deploy\build-desktop.ps1 -SkipSidecar
```

`-IncludeModels` creates a much larger offline model package. The base frozen
client currently does not start the DeepSeek OCR subprocess; do not claim
offline DeepSeek OCR is complete until that separate model/runtime package is
implemented and tested.

## Verification baseline

Run the smallest relevant checks first, then the packaging check:

```powershell
cd E:\houmi\frontend
npm.cmd run test -- --run
npm.cmd run build
cd E:\houmi
cargo fmt --check --manifest-path frontend\src-tauri\Cargo.toml
cargo check --manifest-path frontend\src-tauri\Cargo.toml
$env:PYTHONPATH='backend'
& 'backend\.venv\Scripts\python.exe' -m pytest -q backend\tests\test_resource_dependency.py backend\tests\test_remote_routes.py backend\tests\test_security_tokens.py backend\tests\test_auth_routes.py backend\tests\test_job_and_asset_services.py backend\tests\test_ownership_access.py --basetemp='E:\houmi\_tmp_pytest\handoff'
```

The last known baseline was 118 frontend tests and 13 focused backend tests
passing. Re-run the actual commands after any change; this number is not a
permanent guarantee.

## What is complete vs pending

Complete foundations:

- Local loopback engine and Tauri sidecar packaging
- Offline local project boundary and IndexedDB mutation outbox foundation
- Visible runtime status (`LOCAL`, `CLOUD`, `OFFLINE`)
- Version display and signed-updater integration point
- Release scripts and ADRs for version/Patch handling

Still pending before customer-facing claims:

- Real update endpoint/manifest hosting and signing-key custody
- Authenticated/resumable cloud sync with conflict resolution
- Frozen offline DeepSeek OCR/model package
- Code signing certificate for Windows SmartScreen reputation
- Security/dependency review; `npm install` currently reports 2 high-severity
  audit findings and they must be triaged before a public release

## Safety and handoff rules

- Preserve unrelated dirty worktree changes; do not reset or clean the repo.
- Never put router passwords, JWT secrets, worker keys, or signing private keys
  in source, docs, logs, screenshots, or chat.
- Public Host traffic should use HTTPS/WSS behind the reverse proxy. The raw
  private `192.168.x.x` address is not a customer endpoint.
- Do not bind the desktop sidecar publicly.
- Before saying “offline supported”, specify which capability and whether
  models are included.
- Before saying “Patch supported”, verify signature generation, manifest
  hosting, upgrade from the previous installed version, and restart behavior.
