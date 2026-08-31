## 2026-07-27T09:56:26Z
You are Worker 3 implementing Milestone 3 (R3: Advanced Settings & GPU/Model Management) for Houmi Manga Translator.
Your working directory is e:\houmi\.agents\worker_m3_1.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Requirements for R3:
1. GPU Execution Provider Selection:
   - In `frontend/src/components/SettingsModal.tsx` (and `App.tsx` settings), add dropdown/radio controls for GPU Execution Providers (`CUDA`, `DirectML`, `CPU`).
2. OCR & Inpaint Model Management & Batch Size:
   - Add selectors for Active OCR Model (`manga_ocr`, `rapid_ocr`, `paddle_ocr`, `gemini`), Active Inpaint Engine (`lama_onnx`, `telea`), Batch Size (`1`, `2`, `4`, `8`), and Automated Pipeline Triggers (`auto_ocr`, `auto_inpaint`, `auto_translate`).
3. Backend Config & Execution Provider Support:
   - In `backend/app/config.py` and ONNX service initializers (`backend/app/services/detector.py`, `backend/app/services/inpainter.py`), handle execution provider configuration mapping (`CUDAExecutionProvider`, `DmlExecutionProvider`, `CPUExecutionProvider`).

Verification required:
1. Run `npm --prefix frontend run build` (verify 0 errors).
2. Run `npm --prefix frontend test -- --run` (verify frontend unit tests pass).
3. Run `e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/` (verify backend unit tests pass).

Write report to `e:\houmi\.agents\worker_m3_1\changes.md` and handoff to `e:\houmi\.agents\worker_m3_1\handoff.md`. Communicate completed status via send_message.
