# Smart Balloon Shape-Adaptive Text Wrapping

## Overview

This feature makes text inside Smart Balloon regions wrap naturally to follow the balloon's actual shape instead of using a simple rectangular box. Text now flows with Short-Long-Short patterns for star shapes, or follows the natural curves of oval balloons.

## Architecture

### Backend Changes

**File: `backend/app/services/smart_balloon.py`**

Added `_compute_row_width_constraints()` function that:
- Rasterizes the Smart Balloon polygon contour into a local mask
- Computes the available width at each vertical row (y-coordinate)
- Applies Gaussian smoothing to avoid jitter
- Returns row-wise width array with 85% safety margin

The `process_smart_balloon_v15()` function now includes `row_width_constraints` in its output:
```python
{
  "enabled": True,
  "row_widths": [120.5, 145.2, 180.0, ...],  # width in pixels for each row
  "height": 250  # total height
}
```

**File: `backend/app/services/smart_balloon_typesetting.py`**

Updated `TypesettingSpec.metrics` to include `row_width_constraints` so the frontend can access shape data.

### Frontend Changes

**File: `frontend/src/utils/smartBalloonCanvas.ts`** (NEW)

Created dedicated utilities for Smart Balloon canvas features:

1. **`createPolygonControls()`**: Replaces rectangular selection handles with polygon-based handles that follow the balloon contour
2. **`applyShapeAdaptiveWrapping()`**: Overrides Fabric.js `_wrapLine()` to constrain each line's width based on the balloon shape at that vertical position
3. **`positionAtCentroid()`**: Centers text at the visual centroid instead of the bounding box center

**File: `frontend/src/components/Canvas.tsx`**

Updated textbox rendering to apply Smart Balloon features when `block.extra_metadata.smart_balloon` exists:
- Polygon controls for selection handles
- Shape-adaptive line wrapping
- Centroid-based positioning

## User-Visible Changes

### Before
- Text used uniform rectangular width for all lines
- Text could overflow past jagged star points or narrow waists
- Selection handles showed a rectangular box around the balloon

### After
- **Polygon Selection Handles**: Selection border follows the actual balloon contour with corner handles at convex hull points
- **Shape-Adaptive Line Wrapping**: Text lines are automatically constrained by the balloon shape at each vertical position
  - Star balloons: Short top line → Long middle line → Short bottom line
  - Oval balloons: Text naturally fits the curved interior
- **Centroid Alignment**: Text is centered at the visual center of mass, not just the geometric bbox center

## Technical Details

### Row-Width Constraint Mapping

For a textbox at position `(x, y)` with a line at vertical offset `lineY`:
1. Calculate relative Y position: `relativeY = lineY - bbox.y`
2. Look up maximum width: `maxWidth = row_widths[Math.floor(relativeY)]`
3. Apply to Fabric.js line wrapping: `_wrapLine(..., maxWidth)`

### Polygon Control Rendering

Custom `_renderControls()` override:
- Draws polygon stroke along contour points
- Computes convex hull for corner handle placement
- Limits to 8 handles for performance (most prominent vertices)

### Performance Considerations

- Row width constraints are pre-computed on the backend (one-time cost)
- Frontend only performs array lookups during text layout
- Polygon rendering uses canvas 2D API (hardware accelerated)

## Compatibility

- **Backward Compatible**: Blocks without Smart Balloon metadata use standard rectangular wrapping
- **Graceful Degradation**: If `row_width_constraints` is missing, falls back to uniform width
- **Editor Modes**: Polygon controls automatically restore to standard when not in Smart Balloon mode

## Testing

Run backend tests:
```bash
cd backend
pytest tests/test_smart_balloon_v15.py -xvs
```

Test shape-adaptive wrapping in the app:
1. Open a page with detected Smart Balloons
2. Enter Typesetting mode
3. Select a Smart Balloon text block
4. Observe:
   - Selection handles follow the balloon contour
   - Text lines are shorter near narrow regions
   - Text is visually centered in the balloon body

## Future Enhancements

- [ ] Add visual debug overlay showing row-width constraints
- [ ] Support rotation-aware row width calculation
- [ ] Optimize convex hull computation for complex polygons
- [ ] Add user control for shape-adaptive strength (0-100%)
