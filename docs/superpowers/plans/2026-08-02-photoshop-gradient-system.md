# Photoshop-Compatible Gradient System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a complete Photoshop-style Gradient system across Houmi's Backend Renderer, Schema, Exporter, and Frontend Template/Properties UI.

**Architecture:** Extend `GradientSpec` and `gradient_image()` to support all 5 Photoshop gradient types (`linear`, `radial`, `angle`, `reflected`, `diamond`), scale, and reverse stops. Provide a full Photoshop-style Gradient control panel in Frontend (`App.tsx`) and export gradient specs in PSD manifest.

**Tech Stack:** Python (PIL, NumPy, Pydantic), FastAPI, React, TypeScript, Tailwind CSS.

## Global Constraints

- Preserve all existing `GradientSpec` defaults and schema compatibility.
- Ensure fallback to solid color when `gradient.enabled` is False.

---

### Task 1: Complete Backend Gradient Service (`gradient.py` & `schemas.py`)

**Files:**
- Modify: `backend/app/services/typesetting/schemas.py`
- Modify: `backend/app/services/typesetting/gradient.py`
- Create: `backend/tests/test_photoshop_gradient.py`

**Interfaces:**
- Consumes: `GradientSpec`
- Produces: `gradient_image(width, height, spec) -> Image.Image` for `linear`, `radial`, `angle`, `reflected`, `diamond`

- [ ] **Step 1: Write test for all 5 gradient types in `test_photoshop_gradient.py`**

```python
import pytest
from PIL import Image
from app.services.typesetting.schemas import GradientSpec, GradientStop
from app.services.typesetting.gradient import gradient_image

def test_all_gradient_types_render():
    for gtype in ["linear", "radial", "angle", "reflected", "diamond"]:
        spec = GradientSpec(
            enabled=True,
            type=gtype,
            stops=[GradientStop(position=0.0, color="#ff0000"), GradientStop(position=1.0, color="#0000ff")],
            angle_deg=45.0,
            scale=100.0,
            reverse=False,
        )
        img = gradient_image(100, 100, spec)
        assert isinstance(img, Image.Image)
        assert img.size == (100, 100)
```

- [ ] **Step 2: Run test to verify it passes or fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_photoshop_gradient.py`

- [ ] **Step 3: Refine `gradient.py` for numpy/math parity**

Ensure `gradient.py` properly calculates all 5 modes (`linear`, `radial`, `angle`, `reflected`, `diamond`), `scale`, `reverse`, and `stops` interpolation without crashes.

- [ ] **Step 4: Re-run test to verify 100% pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_photoshop_gradient.py`
Expected: PASS.

- [ ] **Step 5: Commit backend gradient changes**

`git add backend/app/services/typesetting/gradient.py backend/tests/test_photoshop_gradient.py`
`git commit -m "feat: complete 5 Photoshop gradient types in backend gradient generator"`

---

### Task 2: Frontend Photoshop Gradient Control Panel (`App.tsx`)

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GradientSpec`
- Produces: Full Photoshop Gradient controls (Type, Angle Slider, Scale Slider, Reverse Checkbox, Multi-Stop Color controls)

- [ ] **Step 1: Enhance Template & Properties Panel Gradient controls in `App.tsx`**

Add Angle Slider (`-180°` to `180°`), Scale Slider (`10%` to `500%`), Reverse Checkbox, and Type Selector (`linear`, `radial`, `angle`, `reflected`, `diamond`).

- [ ] **Step 2: Update CSS Gradient Preview function**

Generate accurate CSS gradients (`linear-gradient`, `radial-gradient`, `conic-gradient`) matching angle, stops, and type.

- [ ] **Step 3: Test frontend build**

Run: `npm --prefix frontend run build`
Expected: PASS (`✓ built`).

- [ ] **Step 4: Commit frontend changes**

`git add frontend/src/App.tsx`
`git commit -m "feat: add full Photoshop Gradient controls & CSS preview to frontend"`
