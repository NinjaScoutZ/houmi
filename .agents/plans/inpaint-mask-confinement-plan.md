# GODKILLER Blueprint: Inpaint Mask Confinement & Multi-Color Text Preservation

## 1. Goal
Eliminate inpaint mask bleeding outside text boxes (eating balloon spikes and panel art) and eliminate mixed-color text dropouts (e.g. bold black "I CAN'T" dropping while red "MOVE..." is masked).

## 2. Constraints
- When Smart Balloon is OFF, the inpaint mask must strictly remain within the text block bounding box (+ safe text margin <= 4px for ascenders/descenders).
- When Smart Balloon is ON, the inpaint mask must be clipped strictly to the Smart Balloon polygon without leaking into outer spikes.
- Both black ink and colored ink within the same text box must be captured without dropout.
- Zero regressions across existing OCR and Smart Balloon test suites.

## 3. Stakeholders
- Comic/Manga editors translating speech balloons with diverse styles, screams, SFX, and multi-colored dialogue.

## 4. Current State
- `_clip_auto_mask_to_balloon` has a shape bypass `if shape in {"sfx", "free", "shout", "spiky", ...}: return mask` that returns unclipped padded crops.
- `get_automatic_block_mask` expands crops by 30px padding, capturing radiating spikes into the thresholding pass.
- `detect_colored_text_lines` clusters only dominant colored text and creates line proposals that exclude black text components.

## 5. Options
- Option A: Only tighten bounding box padding (leaves color dropout unfixed).
- Option B: Only fix color detector (leaves spike eating unfixed).
- Option C (Chosen): Complete dual-pass architecture: (1) Hard container containment in `inpainter.py`, (2) Radial spike rejection in `monochrome_engine.py`, (3) Multi-ink union in `text_mask.py`.

## 6. Chosen Design
A robust 3-layer defense:
1. **Container Layer**: `_clip_auto_mask_to_balloon` enforces hard bounding box containment when Smart Balloon is OFF and contour polygon clipping when Smart Balloon is ON.
2. **Extraction Layer**: `monochrome_engine.py` rejects outer boundary spike components based on radial geometry.
3. **Multi-Ink Layer**: `text_mask.py` unions luminance thresholding with chroma clustering so both black and colored words in the same box are retained.

## 7. Blast Radius
- `backend/app/services/inpainter.py`: `_clip_auto_mask_to_balloon`, `_padded_block_coords`
- `backend/app/services/mask/monochrome_engine.py`: `generate_monochrome_flat_text_mask`
- `backend/app/services/text_mask.py`: `detect_colored_text_lines`, `_refine_line_mask`

## 8. Test Plan
- `backend/tests/test_inpaint_mask_containment.py`: Unit test with spiky scream balloon verifying zero mask on outer spikes.
- `backend/tests/test_mixed_color_text_mask.py`: Unit test with black word + colored sentence verifying 100% text coverage.
- Full regression test run across `test_smart_balloon_v15.py`, `test_gemini_ocr.py`, `test_multi_key_failover.py`.

## 9. Rollout & Verification
- Execute one Phase per turn via `/ultradeep`.
- Verify with disk test proof before claiming done.

---

## Phased Execution Plan

### Phase 1 — Strict Mask Bounding & Elimination of Unconstrained Shape Bypass
- **Target**: `backend/app/services/inpainter.py`
- **Changes**:
  - In `_clip_auto_mask_to_balloon`:
    - Remove the unconstrained `if shape in {"sfx", "free", "shout", "spiky", "jagged", "burst", "rectangle", "rect", "box"}: return mask` bypass.
    - When `source != "smart_balloon"` (or Smart Balloon is OFF), strictly enforce `clip_to_source_bbox()` with a tight, safe margin of <= 4px (just enough for glyph ascenders/descenders).
    - When Smart Balloon is ON (`source == "smart_balloon"` or `source == "smart_balloon_v15"`), mask is clipped to the exact Smart Balloon polygon (`cv2.fillPoly`).
  - In `_padded_block_coords`:
    - For automatic mask generation, reduce default `pad_margin` from 30px to 12px when `layout_region` is unconfirmed, preventing huge 50% over-crops that capture distant spikes and artwork.

### Phase 2 — Peripheral Spike & Border Line Rejection in Monochrome Engine
- **Target**: `backend/app/services/mask/monochrome_engine.py`
- **Changes**:
  - In `generate_monochrome_flat_text_mask`:
    - Improve component filtering in `clean_mask`:
      - Calculate the distance from each connected component centroid to the center of the crop.
      - Reject components that touch the outer boundary and exhibit radial/elongated spike geometry (`aspect_ratio > 3.0` or `extent < 0.25` touching the crop border).
      - Ensure glyph components located in the central text core are retained.

### Phase 3 — Dual-Pass Multi-Color Text Segmentation & Line Proposal Union
- **Target**: `backend/app/services/text_mask.py`
- **Changes**:
  - In `detect_colored_text_lines`:
    - Include dark ink clusters (`centers[k][0] <= 65`) alongside saturated color clusters in `selected_labels` so black words (like `"I CAN'T"`) in colored sentences are never omitted from the line detection bounding boxes.
  - In `_refine_line_mask`:
    - Always evaluate both Otsu dark-ink thresholding AND LAB color distance thresholding, combining them with `cv2.bitwise_or()`.
  - In `generate_manga_unet_text_mask`:
    - Ensure both dark bold text and colored text are preserved in the probability map before binarization.

### Phase 4 — Comprehensive Verification Suite & Test Evidence
- **Targets**: 
  - `backend/tests/test_inpaint_mask_containment.py`
  - `backend/tests/test_mixed_color_text_mask.py`
  - Full regression test run across `test_smart_balloon_v15.py`, `test_gemini_ocr.py`, `test_multi_key_failover.py`.
