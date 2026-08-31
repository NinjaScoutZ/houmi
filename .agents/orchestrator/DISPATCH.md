# Original Dispatch Request

## 2026-08-03T22:52:00Z

Refactor, consolidate, and polish Houmi's UI/UX layout and Backend settings configuration. Eliminate duplicate or redundant settings across the UI (Sub-toolbar, Canvas controls, Global Settings modal) and Backend API schemas. Group options into clean, intuitive categories, hide/clarify unsupported OCR engines, and ensure full test suite parity.

Requirements:
- R1. UI/UX & Sub-toolbar Consolidation (Font Templates, Min/Max font sizes, Line Height, Padding duplicates removal, compact/visually clean sub-toolbar).
- R2. OCR Engine & Pipeline Organization (Local Engines vs AI Cloud vs Local VLM API, auto hide/mark unusable engines).
- R3. Backend Configuration Cleanup (audit service.py, blocks.py, settings.py, schemas.py, backward compatibility maintained).
- R4. Test Suite Parity & Regression Verification (backend pytest passes: e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/, frontend vitest passes: npx vitest run, frontend tsc passes: npx tsc --noEmit).
