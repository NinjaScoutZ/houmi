# Project: Houmi UI/UX Consolidation & Settings Refactoring

## Architecture
- Frontend: React / Vite TypeScript app (`e:\houmi\frontend`)
- Backend: FastAPI Python application (`e:\houmi\backend`)
- Verification: pytest for backend (`e:\houmi\backend\.venv\Scripts\python.exe -m pytest tests/`), vitest (`npx vitest run`) + tsc (`npx tsc --noEmit -p tsconfig.app.json`) for frontend

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Component modularization | Extract Sub-toolbar, Settings Modal, Sidebar Inspectors from inline App.tsx | M1 | R1 |
| 2 | Sub-toolbar consolidation | Eliminate duplicate font templates, font size, line height, padding controls | M1 | R1 |
| 3 | Canvas & Settings sync | Single canonical source of truth for text block typesetting settings | M1 | R1 |
| 4 | Typesetting export parity | Ensure font size/line height/padding match preview in PNG/PSD export | M1 | R1 |
| 5 | OCR Engine Capabilities API | `GET /api/pipeline/ocr/engines` endpoint for availability status | M2 | R2 |
| 6 | OCR Engine UI Categorization | Group Local Engines, Local VLM API, AI Cloud in sub-toolbar & modal | M2 | R2 |
| 7 | Dynamic Engine Availability | Auto-disable/hide unusable OCR engines with tooltips & auto fallback | M2 | R2 |
| 8 | Legacy Engine Cleanup | Remove unimplemented legacy options (manga_ocr, rapid_ocr) | M2 | R2 |
| 9 | Backend Settings Consolidation | Standardize ocr_engine, inpaint_engine, execution_provider, project_dictionary | M3 | R3 |
| 10 | Schema & Pydantic Polish | Fix Pydantic v2 ConfigDict warnings and FastAPI lifespan deprecations | M3 | R3 |
| 11 | Backward Compatibility | Support legacy project JSON keys during load/deserialization | M3 | R3 |
| 12 | Test Parity Verification | Ensure 100% pass rate for pytest (201/201), vitest (114/114), and tsc --noEmit | M4 | R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | UI/UX & Sub-toolbar Consolidation | Refactor App.tsx inline UI, remove duplicate controls, ensure canvas export parity | None | DONE |
| M2 | OCR Engine & Pipeline Organization | Add OCR engine status API, create unified OcrEngineSelector, remove legacy options | M1 | DONE |
| M3 | Backend Configuration Cleanup | Unified settings helper, canonical keys cleanup, Pydantic v2 polish, backward compat | None | DONE |
| M4 | Test Parity & Forensic Audit | Run pytest, vitest, tsc --noEmit and conduct Forensic Auditor verification | M1, M2, M3 | DONE |

## Code Layout
- Frontend source: `frontend/src/` (`App.tsx`, `components/`, `stores/`, `utils/`)
- Backend source: `backend/app/` (`routes/`, `services/`, `schemas/`, `main.py`)
- Test suites: `backend/tests/`, `frontend/src/` (`*.test.ts`, `*.test.tsx`)
