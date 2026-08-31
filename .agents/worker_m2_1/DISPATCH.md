## 2026-08-03T16:14:50Z
You are worker_m2_1 for Houmi.
Working directory: e:\houmi\.agents\worker_m2_1
Original request path: e:\houmi\.agents\ORIGINAL_REQUEST.md

Task (Milestone 2 & 3: OCR Engine Capabilities API & Backend Settings Consolidation):
Read e:\houmi\.agents\ORIGINAL_REQUEST.md, e:\houmi\.agents\spec_miner_m0_1\analysis.md, and e:\houmi\.agents\explorer_m0_2\analysis.md.

Implement backend and frontend updates:
1. Create backend endpoint `GET /api/pipeline/ocr/engines` in `backend/app/routes/pipeline.py` returning engine status (`available` | `disabled`), group category (`cloud`, `local_vlm`, `local_offline`), and detailed reason if disabled for supported engines (`gemini`, `glm`, `deepseek`, `paddleocr`).
2. Consolidate backend settings access in `backend/app/routes/service.py`, `blocks.py`, `pipeline.py`, `services/ocr.py`, `services/inpainter.py`, `services/typesetting/service.py`:
   - Use canonical keys (`ocr_engine`, `inpaint_engine`, `execution_provider`, `project_dictionary`) with unified fallback helper for legacy stored project keys (`ocr_model`, `active_inpaint_engine`, `default_image_inpaint_method`, `gpu_execution_provider`, `thai_dictionary`).
3. Update Pydantic v2 schemas in `backend/app/schemas/all_schemas.py` to use `model_config = ConfigDict(from_attributes=True)` and fix FastAPI startup/shutdown deprecations in `backend/app/main.py`.
4. Connect frontend `PipelineToolbar.tsx` and `SettingsModal.tsx` to fetch `GET /api/pipeline/ocr/engines` so options are dynamically disabled/marked with status tooltips.
5. MANDATORY Verification:
   - Run backend pytest: `e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/` (MUST pass 100%, 196+ tests).
   - Run frontend tsc: `npx tsc --noEmit -p tsconfig.app.json` (MUST exit 0, 0 errors).
   - Run frontend vitest: `npx vitest run` (MUST pass 100%).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write your report to e:\houmi\.agents\worker_m2_1\changes.md and create a handoff.md. Send a message when complete.
