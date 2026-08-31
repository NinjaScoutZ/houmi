# Houmi Architecture & Security Rules

## 1. Storage & Runtime Mode Isolation
- **Bundled Assets vs User Data:** Read-only assets (ONNX models, static fonts, dist HTML) must be resolved from PyInstaller `_MEIPASS` or Tauri resource bundle. Writable user data (SQLite `houmi.db`, project files, export caches) must strictly resolve to the app data directory or next to the executable (`Path(sys.executable).parent / "data"`).
- **Frozen Subprocess Guard:** Subprocess launchers (`trainer.py`, `ocr_manager.py`) must check `sys.frozen` or `RUNTIME_MODE` before spawning to avoid recursive EXE process creation.

## 2. Security & Multi-tenant Authorization
- **Resource Ownership Resolution:** Every project, page, and block route must enforce `Project.owner_id == current_user.id` or `user.role == "admin"`.
- **WebSocket One-Time Ticket:** WebSockets must authenticate via single-use tickets (`POST /api/auth/ws-ticket`), never exposing raw Access Tokens in WS URL query strings.
- **Worker Runtime Isolation:** GPU worker loops run in `app.worker_runtime` as isolated processes, communicating via DB/Redis queues with lease heartbeats (`heartbeat_at`, `lease_expires_at`).

## 3. Network & Dynamic Origin Binding
- **No Hardcoded Loopback Ports:** Frontend API client (`apiFetch`, `LocalApiClient`) must bind to `window.location.origin` or runtime injected config (`window.__HOUMI_RUNTIME_CONFIG__`), never hardcoding `4000` or `4317`.
- **Host Endpoint Security:** Public host endpoints use Reverse Proxy (Caddy/Nginx) with automatic HTTPS for domain `houmi.sytes.net` or Cloudflare Tunnel.

## 4. Tauri 2 Desktop Updater & Versioning
- **Versioning:** Use `.\deploy\set-version.ps1 -Version X.Y.Z` to keep `package.json`, `Cargo.toml`, and Tauri app manifests in sync.
- **Signed Patches:** Auto-updater patches require digital signatures (`.sig` manifest) and HTTPS release endpoints. Never disable signature verification in production builds.

## 5. Development & Build Policy
- **Strict No-Auto-Build Rule:** DO NOT run `build_exe.py`, PyInstaller, or Tauri release build commands unless the user explicitly requests a build. Active development and testing must be performed directly via Python scripts (`run_desktop.py`, `pytest`, `npm run dev`, `vitest`).

