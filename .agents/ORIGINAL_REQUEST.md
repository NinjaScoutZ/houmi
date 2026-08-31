# Original User Request

## 2026-08-03T15:51:53Z

Refactor, consolidate, and polish Houmi's UI/UX layout and Backend settings configuration. Eliminate duplicate or redundant settings across the UI (Sub-toolbar, Canvas controls, Global Settings modal) and Backend API schemas. Group options into clean, intuitive categories, hide/clarify unsupported OCR engines, and ensure full test suite parity.

Working directory: e:\houmi
Integrity mode: benchmark

## Requirements

### R1. UI/UX & Sub-toolbar Consolidation
Consolidate settings between the Sub-toolbar, Canvas control overlays, and Global Settings modal. Remove duplicate inputs for Font Templates, Min/Max font sizes, Line Height, and Padding. Ensure the Sub-toolbar is compact, visually clean, and intuitive.

### R2. OCR Engine & Pipeline Organization
Categorize and clarify OCR Engine selections (e.g., Local Engines vs AI Cloud vs Local VLM API). Automatically hide or clearly mark unusable engines when external dependencies or local API servers are absent, preventing confusing non-responsive UI actions.

### R3. Backend Configuration Cleanup
Audit backend settings schemas (`service.py`, `blocks.py`, `settings.py`, `schemas.py`) to remove deprecated or duplicate configuration keys in the database and API payloads while maintaining backward compatibility for stored project files.

### R4. Test Suite Parity & Regression Verification
Ensure all automated tests for both backend (`pytest`) and frontend (`vitest`) continue to pass without regressions, validating that setting changes persist and compute properly.

## Verification & Acceptance Criteria

### Automated Verification
- [ ] Backend test suite passes cleanly: `e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/`
- [ ] Frontend test suite passes cleanly: `npx vitest run`
- [ ] Frontend TypeScript typecheck passes: `npx tsc --noEmit`

### UI & UX Quality Criteria
- [ ] No duplicate setting controls appear simultaneously in Sub-toolbar and Settings Modal for the same scope.
- [ ] OCR Engine dropdown separates local offline engines (e.g. PaddleOCR) from cloud/API engines, and disables or hides unconfigured choices.
- [ ] Text block typesetting settings (font family, size, line height, padding, stroke) behave consistently between canvas live preview and final PNG/PSD export.
