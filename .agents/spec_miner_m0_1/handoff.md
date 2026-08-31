# Handoff Report — OCR Engines & Pipeline Organization Specification

**Agent**: `spec_miner_m0_1`  
**Working Directory**: `e:\houmi\.agents\spec_miner_m0_1`  
**Date**: 2026-08-03  

---

## 1. Observation

- **Backend OCR Engine Implementations**:
  - `backend/app/services/ocr.py`: `_run_gemini_cli_ocr()` line 110 invokes `agy`/`gemini` CLI (`gemini` AI engine); `batch_grid_crop_and_ocr_gemini()` line 288 implements 12-block composite grid OCR; `_get_paddle_ocr()` line 33 initializes in-process Korean PaddleOCR.
  - `backend/ocr_server/server.py`: Listens on HTTP port 2322. Implements `GLMBackend` (`zai-org/GLM-OCR`) line 417, `DeepSeekBackend` (`deepseek-ai/DeepSeek-OCR-2`) line 272, and `PaddleOCRBackend` line 521. Automatically switches DeepSeek -> GLM on CUDA MoE errors (line 636).
  - `backend/app/ocr_manager.py`: Manages background `server.py` process lifecycle and keeps it alive via `/health` pings (line 99).
  - `backend/app/routes/pipeline.py`: `@router.post("/pipeline/ocr")` line 308 accepts `backend` parameter.

- **Frontend UI Controls & Divergence**:
  - `frontend/src/App.tsx` (Lines 2856-2865): Sub-toolbar dropdown renders `gemini`, `glm`, `deepseek`, and `paddleocr`. Binds to state `ocrEngine` (default `'glm'`).
  - `frontend/src/components/SettingsModal.tsx` (Lines 68-79): Global Settings modal renders `manga_ocr`, `rapid_ocr`, `paddle_ocr`, and `gemini`. Binds to `settings.ocr_model` / `ocr_engine`.
  - **Divergence**: `SettingsModal.tsx` lacks `glm` and `deepseek`, while containing `manga_ocr` and `rapid_ocr` which do NOT exist in the backend.

- **Diagnostic Endpoints & Tests**:
  - `backend/app/routes/diagnostics.py`: `/diagnostics/health` (line 23) checks `ocr_manager.check_health()`.
  - Tests: `backend/tests/test_gemini_ocr.py`, `backend/tests/test_pipeline_text_evidence.py`, `backend/tests/test_diagnostics.py` pass cleanly with `pytest`. `frontend/src/tests/settingsModal.test.ts` and `frontend/src/tests/diagnosticsToolbar.test.ts` pass cleanly with `vitest`.

---

## 2. Logic Chain

1. **Analysis of Codebase Engine Coverage**:
   - Examining backend service files confirms 4 functional engines: Gemini (AI Cloud/CLI), GLM-OCR (Local VLM), DeepSeek-OCR (Local VLM), and PaddleOCR (Local Offline).
   - Grepping `manga_ocr` and `rapid_ocr` in `backend` returned 0 matches, establishing that they are legacy UI options without backend execution handlers.

2. **Analysis of UI Discrepancy & Non-Responsive Behavior**:
   - Users selecting `manga_ocr` or `rapid_ocr` in Settings Modal get no warning, but execution falls back to default `ocr_server` behavior.
   - UI dropdown options in both `App.tsx` and `SettingsModal.tsx` are hardcoded and lack capability/prerequisite checks (e.g. checking `agy`/`gemini` CLI binary existence or `ocr_server` port 2322 availability).

3. **Formulation of Dynamic Discovery Specification**:
   - To fix UI non-responsiveness and eliminate UI divergence, backend requires an engine capability endpoint (e.g. `GET /api/pipeline/ocr/engines` or enhanced `/api/diagnostics/health`) returning engine availability status and failure reasons.
   - Frontend requires a single consolidated `<OcrEngineSelector />` component with categorized headers and disabled option rendering for unavailable engines.

---

## 3. Caveats

- **External CLI Binary**: Gemini AI OCR depends on system installation of `agy` or `gemini` CLI tools. If neither is installed, Gemini OCR cannot run locally.
- **GPU Memory Constraints**: DeepSeek-OCR MoE requires significant CUDA VRAM. `ocr_server` contains a runtime fallback to GLM-OCR, but pre-checking VRAM before offering DeepSeek is recommended.

---

## 4. Conclusion

- Complete specification report written to `e:\houmi\.agents\spec_miner_m0_1\analysis.md`.
- All 4 prompt requirements fulfilled:
  1. Identified 4 functional engines (`gemini`, `glm`, `deepseek`, `paddleocr`) and 2 unimplemented UI stray entries (`manga_ocr`, `rapid_ocr`).
  2. Traced UI dropdowns, state bindings, API endpoints, backend handlers, and diagnostics checks.
  3. Formulated dynamic engine discovery API specification (`GET /api/pipeline/ocr/engines`) and dynamic UI component design (`<OcrEngineSelector />`).
  4. Documented all affected frontend/backend files and test suites.

---

## 5. Verification Method

To verify the findings and analysis report:
1. Inspect `e:\houmi\.agents\spec_miner_m0_1\analysis.md`.
2. Confirm backend test suite passes:
   `e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/`
3. Confirm frontend test suite passes:
   `npx vitest run`
4. Confirm TypeScript typecheck passes:
   `npx tsc --noEmit`
