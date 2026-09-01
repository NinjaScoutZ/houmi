# HOUMI AGENT LEDGER (FABLE5 DISCIPLINE)

## COMPLETED CARDS

### [x] BK-01: Patch Isolation & Safe Reversible Rollback Engine (backend/app/patches/)
- Scope: backend/app/patches/ (patch_engine.py, manifest.py, rollback.py)
- Evidence: 2/2 tests passed (pytest tests/test_patch_isolation.py)
- Features: SHA-256 Checksum, Staging extraction, Zip Slip protection, 1-Click Rollback.

### [x] BK-02: Stable Core Module Re-organization (backend/app/core/)
- Scope: backend/app/core/ (config.py, database.py, events.py, security.py)
- Evidence: 3/3 tests passed (pytest tests/test_core_architecture.py)
- Features: Centralized configs, connection pooling, lifespan lifecycle, non-breaking re-exports.

### [x] BK-03: Production Telemetry & GPU Memory Auto-GC (backend/app/telemetry/)
- Scope: backend/app/telemetry/ (gpu_monitor.py, pipeline_queue.py, health.py)
- Evidence: 5/5 tests passed (pytest tests/test_telemetry_gpu.py)
- Features: VRAM tracker, Auto-GC on 85% threshold, Pipeline Queue throughput/latency metrics.

### [x] BK-04: AI Key Pool Balancer & Corrupted Input Guard
- Scope: backend/app/services/ai_key_pool.py, backend/app/services/image_guard.py
- Evidence: 5/5 tests passed (pytest tests/test_ai_key_pool.py tests/test_image_guard.py)
- Features: Multi-key round robin, 429/503 circuit breaker, 50MB / 6K downscaling sanity guard.

### [x] BK-05: Adversarial Council 3-Way Debate & Final Production Verification
- Scope: Full multi-layer stack grill + 3-Way Debate Council
- Evidence: 26/26 tests passed in 3.24s across all backend core suites.

### [x] BK-06: Mask Engine Routing & Precision Persistence Fix (v1.0.5)
- Scope: backend/app/services/text_mask.py, backend/app/services/inpainter.py, backend/app/routes/pipeline.py, workspaces/v1.0.5/frontend/src/App.tsx, SettingsModal.tsx, MaskEditorModal.tsx
- Evidence: 10/10 tests passed in 0.72s (pytest backend/tests/test_text_mask.py) + Vite frontend production build passed in 797ms with 0 errors.
- Features: Real OpenCV Adaptive Morphology & Contours engine, 5-engine unified dispatch in pipeline and inpainter, unified single source of truth for mask_dilation_kernel (3px baseline, no preset overwrite).

### [x] TAURI-01: 100% Tauri v2 Native Desktop Migration (v1.0.5)
- Scope: workspaces/v1.0.5/frontend/src-tauri/ (Cargo.toml, tauri.conf.json, src/main.rs), Launch-v1.0.5.bat, run_desktop.py
- Evidence: `cargo build` completed in 34.77s with 0 errors -> `houmi-studio.exe` (26.3 MB) + `cargo check` in 1.27s + 5/5 backend tests passed.
- Features: 100% Native Rust Tauri v2 window host, embedded authentic Staging UI bundle, sidecar supervisor for Python AI backend (Port 4000) with zero-zombie process termination on exit, native dialog IPC for manga folder import.

### [x] UI-01: Antigravity Non-Blocking Batch Progress HUD (v1.0.5)
- Scope: workspaces/v1.0.5/frontend/src/components/BatchProgressModal.tsx, workspaces/v1.0.5/frontend/src/App.tsx
- Evidence: `npx vite build` succeeded in 815ms + 157/157 frontend tests passed (25 test suites).
- Features: Removed full-screen black backdrop lock, implemented floating weightless HUD Dock in bottom-right corner, dual-state morphing (Compact Island Pill ⇄ Expanded Spatial Stepper Card), live timer and stage badges, 100% background concurrency allowing uninterrupted drawing, panning, zooming, and text editing across pages.

### [x] BK-07: Workspace 1.0.5 Pipeline Fix & Dual Query/Body Binding
- Scope: `backend/app/routes/pipeline.py`, `workspaces/v1.0.5/backend/app/routes/pipeline.py`, `workspaces/v1.0.5/frontend/src/App.tsx`
- Evidence: 11/11 pytest passed (`test_ocr_engines_api.py`, `test_pipeline_endpoints.py`), `npx tsc --noEmit` 0 errors, 157/157 frontend vitest passed (25 test suites).
- Features: Eliminated FastAPI 422 Unprocessable Entity by fixing unannotated `cancel_check` parameter and using safe `_extract_param` across all pipeline endpoints, added route aliases for `/pipeline/font_judge`, `/pipeline/typeset`, `/pipeline/style_judge`, supported custom workflow steps (`filter_empty`, `merge_expand`), and synchronized frontend pipeline triggers to use `apiFetch`.

