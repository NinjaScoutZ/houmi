# Changes Report — Milestone 3 (R3: Advanced Settings & GPU/Model Management)

## Overview
Implemented Milestone 3 requirements for Advanced Settings & GPU/Model Management in Houmi Manga Translator, covering frontend controls, backend configuration, and ONNX Runtime execution provider mapping.

## Summary of Changes

### 1. Frontend Settings Controls (`frontend/src/components/SettingsModal.tsx` & `frontend/src/App.tsx`)
- **GPU Execution Provider Selection**: Added controls (`CUDA`, `DirectML`, `CPU`) in `SettingsModal.tsx` and in global settings within `App.tsx`.
- **Active OCR Model Management**: Added dropdown selector for `manga_ocr`, `rapid_ocr`, `paddle_ocr`, and `gemini`.
- **Active Inpaint Engine Management**: Added selector for `lama_onnx` (LaMa ONNX) and `telea` (OpenCV Fast).
- **Batch Size Configuration**: Added dropdown selector for batch sizes `1`, `2`, `4`, and `8`.
- **Automated Pipeline Triggers**: Added checkboxes for `auto_ocr`, `auto_inpaint`, and `auto_translate`.
- **Store Sync & State Integration**: Ensured all settings persist in `localStorage` (`houmi_g_*`) and sync bidirectionally with active project settings on the backend.
- **Frontend Test Coverage**: Added `frontend/src/tests/settingsModal.test.ts` to test R3 setting mutations.

### 2. Backend Config & Execution Provider Support (`backend/app/config.py`, `backend/app/services/detector.py`, `backend/app/services/inpainter.py`, `backend/app/routes/pipeline.py`)
- **Configuration & Provider Mapping (`backend/app/config.py`)**:
  - Added `EXECUTION_PROVIDER_MAP` mapping user-facing selections (`CUDA`, `DirectML`, `CPU`) to ONNX Runtime provider strings (`CUDAExecutionProvider`, `DmlExecutionProvider`, `CPUExecutionProvider`).
  - Added helper `get_execution_providers(provider_name)` which handles mapping with automatic CPU fallback.
- **YOLO Balloon Detector Provider Support (`backend/app/services/detector.py`)**:
  - Updated `BalloonDetector.load_model` and `BalloonDetector.detect` to accept and reload sessions using the configured `execution_provider`.
- **LaMa Inpainter Provider Support (`backend/app/services/inpainter.py`)**:
  - Updated `LamaONNXInpainter` and `_get_lama` to map execution providers (`CUDAExecutionProvider`, `DmlExecutionProvider`, `CPUExecutionProvider`).
  - Updated `should_use_lama_inpaint` to support `inpaint_engine` and `active_inpaint_engine` setting keys (`lama_onnx`).
  - Updated `clean_page_text`, `reclean_page_block`, and `generate_inpaint_preview` to pass the configured `gpu_execution_provider` to `_get_lama`.
- **Pipeline Route Wiring (`backend/app/routes/pipeline.py`)**:
  - Updated `run_detect` and `run_batch_pipeline_task` to pass the project's configured execution provider to `balloon_detector.detect`.
- **Backend Test Coverage**: Added `backend/tests/test_execution_provider.py` to test mapping resolution and ONNX session initialization.

## Verification
1. `npm --prefix frontend run build` — 0 errors.
2. `npm --prefix frontend test -- --run` — 13 test files passed (85 tests passed).
3. `python -m pytest tests/` — 162 passed tests.
