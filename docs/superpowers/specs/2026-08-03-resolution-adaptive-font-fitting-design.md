# Resolution-Adaptive & Zero-Click Font Fitting — Design Spec

**Date:** 2026-08-03  
**Status:** Approved  
**Approach:** Option A (Relative Resolution Scaling + Default Geometry Auto-Fit)

---

## 1. Overview
This design introduces an automatic, resolution-adaptive font scaling system in Houmi. Regardless of whether a manga page is 800px, 1400px, or 4000px in height, text font sizes automatically scale proportionally relative to page geometry without requiring manual button clicks or series-specific adjustments.

---

## 2. Core Architecture

### A. Relative Resolution Scaling Factor (`resolution_scale`)
- **Reference Height Baseline:** `1400.0px` (standard manga page height).
- **Formula:** `resolution_scale = page_height / 1400.0`
- **Application:**
  - Base template font sizes and min/max font size thresholds scale dynamically:
    `effective_requested_font_size = template_font_size * resolution_scale`
    `effective_min_font_size = min_font_size * resolution_scale`
    `effective_max_font_size = max_font_size * resolution_scale`

### B. Zero-Click Geometry Auto-Fitting
- `auto_font_resize` is `True` by default.
- When `compute_block_typesetting` runs during OCR/import/typesetting:
  - If font size is unconstrained (`manual_font_size` is null), `fitting.py` searches candidate sizes up to `effective_max_font_size`.
  - It picks the largest font size that fits 100% inside `block_w` and `block_h` without overflow.

---

## 3. Subsystem Changes

### `backend/app/services/typesetting/service.py`
- Retrieve `page_height` from `block.page.height` (fallback `1400.0` if unavailable).
- Compute `resolution_scale = max(0.5, page_height / 1400.0)`.
- Scale `requested_font_size`, `configured_min_font`, and `configured_max_font` by `resolution_scale` when fitting unconstrained text.

---

## 4. Verification Plan
- **Backend Tests**: Create test in `test_typesetting.py` verifying that a 2800px page produces double the font size of a 1400px page for the same text block, with 0 overflow.
- **Frontend Build**: Verify `npm --prefix frontend run build` passes.
