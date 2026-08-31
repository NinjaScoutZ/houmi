# Investigation: Mask Kernel Failure on Dark / Spiky Speech Balloons with Outlined Text

## 1. Problem Description & Visual Evidence

We are investigating why the **Mask Kernel** pipeline in Houmi succeeds completely on standard dialogue balloons but fails to generate text masks on dark/screaming/spiky balloons with stylized fonts.

Attached Images in this folder:
- **`image_1_spiky_balloon_failed.png`**:
  - **Context**: A dark grey spiky shout balloon with radial speedlines and stylized Korean text.
  - **Text characteristics**: Pink/salmon interior fill with a thick, prominent solid white outer stroke (`#FFFFFF`).
  - **Result**: Inside the green text bounding box (block [1]), almost NO mask is generated on the text (only a tiny sliver at the baseline). Moreover, an unrelated rectangular red mask artifact appears at the top outside the balloon.
- **`image_2_normal_balloon_success.png`**:
  - **Context**: Standard white oval dialogue balloon with black Korean text.
  - **Result**: Complete, solid, clean red mask covering the text perfectly (Magnetic Line Fill + Boundary Clamping working as intended).

---

## 2. Codebase Architecture & Key Files

The mask generation and inpainting pipeline consists of:

1. **`backend/app/services/mask/border_clamper.py`**:
   - Function: `clamp_mask_to_balloon_interior(mask, image_bgr, margin_px=2)`
   - Current logic:
     ```python
     # Detect dark strokes
     _, dark_binary = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY_INV)
     # Identifies large or perimeter-touching strokes as border_binary
     # Applies distanceTransform on (255 - border_binary) and zeros out mask where dist <= margin_px
     ```
   - **Identified Flaw**: Assumes balloon interior is always light/white and outer border is dark (`gray < 110`). When the balloon interior itself is dark/spiky (`gray < 110`), `border_binary` classifies the entire dark background as a "border stroke", and `dist_map <= 2` erases almost 100% of the text mask!

2. **`backend/app/services/mask/classifier.py`**:
   - Function: `classify_text_mask_mode(image_bgr)`
   - Classifies crop into `monochrome_flat` vs `color_or_complex`.
   - On dark balloons with colored text, routes to `color_or_complex`.

3. **`backend/app/services/text_mask.py`**:
   - Function: `generate_routed_text_mask(image_bgr, dilation_kernel)`
   - Attempts `generate_manga_unet_text_mask`. If `mode == color_or_complex` and UNet does not detect the stylized stroked text, falls back to `generate_adaptive_sfx_mask`.
   - Both UNet and SFX generator pass through `clamp_mask_to_balloon_interior`, which deletes the mask if background is dark.

4. **`backend/app/services/mask/monochrome_engine.py`**:
   - Has light-text-on-dark-background branch (`clean_light_mask`), but is bypassed when `classify_text_mask_mode` returns `color_or_complex`.

5. **`backend/app/services/inpainter.py`**:
   - Function: `_clip_auto_mask_to_balloon` and `get_automatic_block_mask`.
   - Also calls `clamp_mask_to_balloon_interior`.

---

## 3. Consultation Questions for Claude

1. **Polary & Border Clamping Architecture**:
   - How should `clamp_mask_to_balloon_interior` be refactored to distinguish between a *true enclosing balloon border* vs *a dark balloon background / screentone / dark panel artwork*?
   - How should background polarity (light background vs dark background vs textured background) be sampled safely so border clamping never erases legitimate text on dark backgrounds?

2. **White-Stroked & Multi-Tone Font Segmentation**:
   - How should the segmentation pipeline in `text_mask.py` (UNet + SFX adaptive fallback + morphological fallback) reliably capture text with a **colored fill + white outline** on dark/spiky backgrounds, ensuring both the colored core AND the white outline are fully masked?

3. **Prevention of Stray Outer Masks**:
   - What is the best containment strategy to prevent stray rectangular mask artifacts (like the one visible above the balloon in `image_1_spiky_balloon_failed.png`) from appearing outside the detected balloon contour or text bounding box?

4. **Zero-Regression Strategy**:
   - What unit tests and test fixtures should be added to guarantee that standard white dialogue balloons (Image 2) and Smart Balloon polygons retain 100% of their existing quality and magnetic line fill behavior?
