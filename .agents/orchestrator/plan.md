# Execution Plan — Houmi Layout & Settings Refactoring

## Objectives
Consolidate UI/UX Sub-toolbar & settings controls, organize OCR engine options, clean backend configuration schemas while maintaining backward compatibility, and ensure all tests pass cleanly without regression.

## Milestones
- **Phase 0: Survey & Exploration (COMPLETED)**
  - Explorers `explorer_m0_1`, `explorer_m0_2`, `spec_miner_m0_1` audited codebase.
  - Baseline status: Pytest 196/196 pass, Vitest 113/113 pass, tsc 0 errors.

- **Milestone 1 (R1): UI/UX & Sub-toolbar Consolidation**
  - Modularize `App.tsx` inline UI into `SettingsModal.tsx`, `PipelineToolbar.tsx`, `SidebarInspector.tsx`.
  - Remove duplicate font template, min/max font size, line height, and padding controls across sub-toolbar and modal.
  - Ensure typesetting preview and PNG/PSD export parity.
  - Verification: Vitest (`npx vitest run`) and TypeScript check (`npx tsc --noEmit`).

- **Milestone 2 (R2): OCR Engine & Pipeline Organization**
  - Implement `GET /api/pipeline/ocr/engines` capabilities endpoint in backend.
  - Create unified `<OcrEngineSelector />` component with categorized optgroups (`Local Engines`, `Local VLM API`, `AI Cloud`).
  - Disable unusable engines with tooltips and handle auto fallback.
  - Remove legacy static entries (`manga_ocr`, `rapid_ocr`).
  - Verification: Pytest and Vitest.

- **Milestone 3 (R3): Backend Configuration Cleanup**
  - Create backend settings helper module for canonical key access (`ocr_engine`, `inpaint_engine`, `execution_provider`, `project_dictionary`).
  - Update `service.py`, `blocks.py`, `settings.py`, `schemas.py` to use canonical keys while preserving legacy fallbacks.
  - Fix Pydantic v2 `ConfigDict` and FastAPI `lifespan` deprecation warnings.
  - Verification: Pytest suite (196+ tests).

- **Milestone 4 (R4): Test Suite Parity, Regression Verification & Audit**
  - Verify Pytest backend test suite passes: `backend\.venv\Scripts\python.exe -m pytest tests/`
  - Verify Vitest frontend test suite passes: `npx vitest run`
  - Verify TypeScript typecheck passes: `npx tsc --noEmit`
  - Forensic Auditor (`teamwork_preview_auditor`) integrity verification.
