# Photoshop-Compatible Gradient System — Design Spec

**Date:** 2026-08-02  
**Status:** Approved  
**Approach:** Approach 1 (Full Photoshop Gradient Settings & Multi-Renderer Parity)

---

## 1. Overview
This design implements a complete Photoshop-compatible Gradient system in Houmi. It provides parity across the Font Template Editor, Text Block Properties Panel, Pillow Backend Renderer, and Rust PSD CLI Manifest.

---

## 2. Architectural Data Model

### `GradientSpec` (Pydantic & TypeScript)
```json
{
  "enabled": true,
  "type": "linear", 
  "stops": [
    { "position": 0.0, "color": "#ffcc00", "opacity": 1.0 },
    { "position": 1.0, "color": "#ff5500", "opacity": 1.0 }
  ],
  "angle_deg": 90.0,
  "scale": 100.0,
  "reverse": false,
  "dither": true,
  "align_with_layer": true,
  "opacity": 1.0,
  "blend_mode": "normal"
}
```

---

## 3. Subsystem Changes

### A. Backend Gradient Generator (`backend/app/services/typesetting/gradient.py`)
- Implement multi-type gradient rendering:
  - **`linear`**: Directional gradient based on `angle_deg` and `scale`.
  - **`radial`**: Circular/elliptical gradient centered on text box.
  - **`angle`**: Sweep/conic gradient around center point.
  - **`reflected`**: Symmetric mirrored linear gradient from center.
  - **`diamond`**: Rhombus shape gradient centered on box.
- Support `reverse` stops, multi-stop color interpolation, and `scale` factor.

### B. Backend Renderer & Export (`renderer.py` & `psd_export.py`)
- Apply `gradient_image()` mask to text fill in `render_page_text()`.
- Export `gradient` spec in `psd_export.py` manifest for PSD CLI compatibility.

### C. Frontend Interface (`frontend/src/App.tsx`)
- Render Photoshop-style Gradient Control Panel:
  - Type Selector (`Linear`, `Radial`, `Angle`, `Reflected`, `Diamond`)
  - Angle Control Slider (`-180°` to `180°`)
  - Scale Control Slider (`10%` to `500%`)
  - Multi-Stop Color Pickers (Start/End + intermediate stops)
  - Reverse Stops Checkbox
- Update Canvas & Template Cards preview CSS to render matching `linear-gradient` / `radial-gradient` / `conic-gradient`.

---

## 4. Verification Plan
- **Backend Tests**: Verify `gradient_image()` generates valid RGBA PIL Images for all 5 gradient types.
- **Frontend Build**: Verify TypeScript compilation and Vite build with no type errors.
