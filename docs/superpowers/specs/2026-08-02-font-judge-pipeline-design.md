# Font Judge System & Pipeline Toolbar Integration — Design Spec

**Date:** 2026-08-02  
**Status:** Approved  
**Approach:** Approach 1 (Dedicated "Font Judge" Pipeline Toolbar Button & API Endpoint)

---

## Executive Summary
The Font Judge system analyzes text blocks on a manga page to evaluate semantic role (dialogue, emphasis/shout, narration, thought, sfx, system) and automatically assigns or suggests the appropriate Font Template. This feature adds a dedicated **✒️ Font Judge** button in the Pipeline Toolbar and a corresponding backend endpoint to trigger page-level style evaluation.

---

## Architectural Changes

### 1. Frontend Integration
- **`PipelineToolbar.tsx`**:
  - Add `font_judge` to `onRunStep` callback interface: `onRunStep: (step: 'detect' | 'ocr' | 'inpaint' | 'render' | 'font_judge' | 'auto') => void;`
  - Render **✒️ Font Judge** button between `Inpaint` and `Typeset` (or adjacent to `Typeset`).
  - Button state disabled during `isProcessing`.
- **`App.tsx`**:
  - Handle `step === 'font_judge'` in `runPipelineStep`.
  - Endpoint target: `POST /api/pipeline/style-judge?page_id={activePage.id}`.
  - On success, display Toast notification (`"Evaluated font styles for X blocks"`) and reload the page text blocks to reflect newly assigned font templates on the canvas.

### 2. Backend Integration
- **`backend/app/routes/pipeline.py`**:
  - Add `POST /api/pipeline/style-judge`:
    - Accept `page_id: str`, optional `force_apply: bool = True`.
    - Retrieve all non-empty `TextBlock` items for `page_id`.
    - Fetch project settings and font templates.
    - Invoke `judge_style(block, project_settings=project_settings)` from `app.services.typesetting.style_judge`.
    - Apply suggested font templates via `apply_style_descriptor_to_block`.
    - Recompute effective typesetting specs using `compute_block_typesetting(block)` and persist specs.
    - Commit changes to the database.
    - Return JSON result summary: `{"status": "ok", "page_id": page_id, "evaluated_blocks": count, "applied_blocks": count}`.

### 3. Verification Plan
- **Backend Tests**: Run unit tests / API test for `/api/pipeline/style-judge`.
- **Frontend Verification**: Build / test button triggering font evaluation step cleanly.
