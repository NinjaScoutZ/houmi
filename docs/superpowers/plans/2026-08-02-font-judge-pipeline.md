# Font Judge System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a page-level Font Judge endpoint and Pipeline Toolbar button to automatically analyze text blocks and assign matching Font Templates.

**Architecture:** A new POST `/api/pipeline/style-judge` backend route calls `judge_style` and `apply_style_descriptor_to_block` on each text block of a page, recomputes typesetting specs, and persists changes. The frontend `PipelineToolbar` adds a **✒️ Font Judge** button that invokes this endpoint.

**Tech Stack:** FastAPI, Python (SQLAlchemy, `app.services.typesetting.style_judge`), React, TypeScript.

## Global Constraints

- Preserve all existing API responses and database models.
- Python imports must use proper package modules.

---

### Task 1: Backend API Endpoint `/api/pipeline/style-judge`

**Files:**
- Modify: `backend/app/routes/pipeline.py`
- Test: `backend/tests/test_style_judge_pipeline.py` (or pytest check)

**Interfaces:**
- Consumes: `app.services.typesetting.style_judge.judge_style`, `app.services.typesetting.style_judge.apply_style_descriptor_to_block`
- Produces: `POST /api/pipeline/style-judge?page_id={page_id}`

- [ ] **Step 1: Write test for style-judge pipeline endpoint**

Create `backend/tests/test_style_judge_pipeline.py` with test verifying `/api/pipeline/style-judge` returns `200 OK` and updates text block metadata.

- [ ] **Step 2: Run test to verify it fails**

Run `pytest backend/tests/test_style_judge_pipeline.py`
Expected: 404 or endpoint missing.

- [ ] **Step 3: Implement `POST /api/pipeline/style-judge` in `pipeline.py`**

Add endpoint:
```python
@router.post("/pipeline/style-judge")
def run_style_judge(page_id: str, db: Session = Depends(get_db)):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    project_settings = page.project.settings if page.project else {}
    evaluated = 0
    applied = 0
    for block in page.text_blocks:
        text_val = (block.translation or block.source_text or "").strip()
        if not text_val:
            continue
        desc = judge_style(block, project_settings=project_settings, page_height=page.height)
        res = apply_style_descriptor_to_block(block, desc, project_settings=project_settings, apply_template=True, confidence_auto_threshold=0.0)
        evaluated += 1
        if res.get("applied"):
            applied += 1
        spec = compute_block_typesetting(block)
        persist_typesetting_spec(block, spec)
    
    db.commit()
    return {"status": "ok", "page_id": page_id, "evaluated_blocks": evaluated, "applied_blocks": applied}
```

- [ ] **Step 4: Run test to verify it passes**

Run `pytest backend/tests/test_style_judge_pipeline.py`
Expected: PASS.

- [ ] **Step 5: Commit backend changes**

`git add backend/app/routes/pipeline.py backend/tests/test_style_judge_pipeline.py`
`git commit -m "feat: add /api/pipeline/style-judge endpoint"`

---

### Task 2: Frontend Pipeline Toolbar Button & Action

**Files:**
- Modify: `frontend/src/components/PipelineToolbar.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `POST /api/pipeline/style-judge?page_id={id}`
- Produces: UI button `Font Judge` in Pipeline Toolbar

- [ ] **Step 1: Update `PipelineToolbarProps` and button UI in `PipelineToolbar.tsx`**

Update `onRunStep` signature to include `'font_judge'` step. Add button:
```tsx
<button
  disabled={isProcessing}
  onClick={() => onRunStep('font_judge')}
  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 active:bg-slate-600 disabled:opacity-50 text-slate-200 border border-slate-700/80 rounded-lg font-medium transition-all flex items-center gap-1.5 shadow-sm"
  title="Analyze and judge font styles for text blocks"
>
  <span>✒️</span>
  <span>Font Judge</span>
</button>
```

- [ ] **Step 2: Add handler in `App.tsx`**

In `runPipelineStep`:
```typescript
else if (step === 'font_judge') {
  url = `/api/pipeline/style-judge?page_id=${activePage.id}`;
}
```
Show toast on completion: `"Font Judge completed for page"`. Refresh page text blocks.

- [ ] **Step 3: Test frontend build**

Run `npm --prefix frontend run build` or typecheck.

- [ ] **Step 4: Commit frontend changes**

`git add frontend/src/components/PipelineToolbar.tsx frontend/src/App.tsx`
`git commit -m "feat: add Font Judge button to Pipeline Toolbar"`
