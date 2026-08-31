# Milestone 2 & 3 Changes Report: OCR Engine Capabilities API & Backend Settings Consolidation

**Worker Agent**: `worker_m2_1`  
**Date**: 2026-08-03  
**Status**: COMPLETED & VERIFIED (pytest: 201/201 passed, tsc: exit 0, vitest: 114/114 passed)

---

## 1. Summary of Changes

### A. OCR Engine Capabilities API (`GET /api/pipeline/ocr/engines`)
- **Backend (`backend/app/routes/pipeline.py`)**:
  - Implemented `@router.get("/pipeline/ocr/engines")` endpoint.
  - Dynamically inspects status (`available` | `disabled`), group category (`cloud`, `local_vlm`, `local_offline`), and detailed failure reason if disabled.
  - Supports engines: `gemini` (Cloud AI CLI check via `agy`/`gemini` in PATH), `glm` (Local VLM API check via port 2322 `/health`), `deepseek` (Local VLM API check with VRAM/MoE error detection), and `paddleocr` (Local Offline Python import check).

### B. Unified Settings Access Consolidation
- **Config & Helpers (`backend/app/config.py`)**:
  - Added `get_project_setting`, `get_ocr_engine`, `get_inpaint_engine`, `get_execution_provider_setting`, and `get_project_dictionary`.
  - Maps canonical keys to legacy stored project keys:
    - `ocr_engine` -> fallback: `ocr_model`
    - `inpaint_engine` -> fallback: `active_inpaint_engine`, `default_image_inpaint_method`
    - `execution_provider` -> fallback: `gpu_execution_provider`
    - `project_dictionary` -> fallback: `thai_dictionary`
- **Backend Routes & Services Updated**:
  - `backend/app/routes/projects.py`: Updated `_default_project_settings()` to initialize canonical keys (`ocr_engine`, `inpaint_engine`, `execution_provider`, `project_dictionary`).
  - `backend/app/routes/blocks.py`: Used `get_ocr_engine` for auto-OCR resolution.
  - `backend/app/routes/pipeline.py`: Replaced chained `.get()` calls with `get_execution_provider_setting` and `get_inpaint_engine`.
  - `backend/app/services/inpainter.py`: Updated `resolve_inpaint_engine_name` and GPU provider lookups to use unified helpers.
  - `backend/app/services/typesetting/service.py`: Used `get_project_dictionary` for dictionary tokenization and signature computation.

### C. Pydantic v2 & FastAPI Modernization
- **Schemas (`backend/app/schemas/all_schemas.py`)**:
  - Replaced legacy `class Config: from_attributes = True` with Pydantic v2 `model_config = ConfigDict(from_attributes=True)` across `TextBlockResponse`, `PageResponse`, and `ProjectResponse`.
- **FastAPI Lifespan (`backend/app/main.py`)**:
  - Replaced deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")` handlers with `@asynccontextmanager async def lifespan(app: FastAPI):`.

### D. Frontend UI Integration
- **`frontend/src/components/SettingsModal.tsx`**:
  - Connected to fetch `GET /api/pipeline/ocr/engines` on modal open.
  - Grouped options into `AI Cloud Models`, `Local VLM APIs`, `Local Offline Engines`.
  - Removed stray/unimplemented options (`manga_ocr`, `rapid_ocr`).
  - Dynamically disabled unavailable choices and displayed status warning badges with backend reasons.
- **`frontend/src/components/PipelineToolbar.tsx`**:
  - Enhanced categorized engine selector dropdown with status tooltips and disabled state handling for unusable engines.
- **`frontend/src/App.tsx`**:
  - Added background fetch of `/api/pipeline/ocr/engines` on startup.
  - Passed `ocrEngineStatuses={ocrEngineStatuses}` prop to `SettingsModal`.

### E. Automated Test Coverage
- Created `backend/tests/test_ocr_engines_api.py` testing the new `GET /api/pipeline/ocr/engines` endpoint and settings consolidation helpers.

---

## 2. Modified Files

1. `backend/app/config.py` - Added setting consolidation helpers and `from typing import Any` import.
2. `backend/app/routes/pipeline.py` - Created `GET /api/pipeline/ocr/engines` and updated settings access.
3. `backend/app/routes/blocks.py` - Updated OCR engine setting resolution.
4. `backend/app/routes/projects.py` - Updated `_default_project_settings()` with canonical keys.
5. `backend/app/services/inpainter.py` - Updated inpaint engine and execution provider resolution.
6. `backend/app/services/typesetting/service.py` - Updated dictionary setting access.
7. `backend/app/schemas/all_schemas.py` - Updated Pydantic v2 `model_config = ConfigDict(from_attributes=True)`.
8. `backend/app/main.py` - Migrated startup/shutdown events to `@asynccontextmanager lifespan`.
9. `backend/tests/test_ocr_engines_api.py` - Created unit test suite for OCR capabilities API and settings helpers.
10. `frontend/src/components/SettingsModal.tsx` - Connected engine fetching, grouped categories, removed stray options.
11. `frontend/src/components/PipelineToolbar.tsx` - Updated categorized engine selector and disabled state tooltips.
12. `frontend/src/App.tsx` - Added capability status fetching and passed `ocrEngineStatuses` to `SettingsModal`.

---

## 3. Verification Results

- **Backend Pytest**: `201 passed in 49.60s` (100% pass rate). Deprecation warnings eliminated.
- **Frontend TypeScript (`tsc`)**: `Exit 0`, 0 errors (`npx tsc --noEmit -p tsconfig.app.json`).
- **Frontend Vitest**: `16 passed (16 test files, 114 tests passed)` (`npx vitest run`).
