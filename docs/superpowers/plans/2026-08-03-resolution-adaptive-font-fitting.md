# Resolution-Adaptive & Zero-Click Font Fitting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement resolution-adaptive font scaling (`page_height / 1400.0`) in `backend/app/services/typesetting/service.py` so that text font size automatically scales to match page resolution without manual clicks.

**Architecture:** Calculate `resolution_scale` from page height and scale template default font size bounds during auto-fit layout computation.

**Tech Stack:** Python, pytest.

---

### Task 1: Resolution-Adaptive Scaling in `service.py` & Test Suite

**Files:**
- Modify: `backend/app/services/typesetting/service.py`
- Modify: `backend/tests/test_typesetting.py`

- [ ] **Step 1: Write test for resolution adaptive scaling in `test_typesetting.py`**

```python
def test_resolution_adaptive_font_scaling(self):
    # Test that high resolution pages scale font size proportionally
    pass
```

- [ ] **Step 2: Implement `resolution_scale` calculation in `service.py`**

In `compute_block_typesetting`:
```python
page_height = float(block.page.height) if (block.page and block.page.height) else 1400.0
resolution_scale = max(0.25, min(4.0, page_height / 1400.0))
```

- [ ] **Step 3: Run pytest**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_typesetting.py`

- [ ] **Step 4: Verify frontend build**

Run: `npm --prefix frontend run build`
