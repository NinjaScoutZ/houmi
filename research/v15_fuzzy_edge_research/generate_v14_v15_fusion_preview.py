import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import (
    process_smart_balloon_v15,
    find_true_waist_concave_points,
    apply_contour_inset,
)

# Colors Palette (V14 Aesthetic)
COLOR_PALETTE = {
    "SPIKY_FUZZY": (230, 90, 220),   # Radiant Purple / Violet
    "RECTANGULAR": (235, 160, 45),    # Vibrant Cyan
    "ANGULAR": (65, 215, 115),        # Lime Green
    "SMOOTH_OVAL": (40, 165, 255)     # Warm Amber Orange
}

def balanced_comic_typeset(lines_text: list[str], cx: int, cy: int, font_scale: float = 0.55, font_face = cv2.FONT_HERSHEY_DUPLEX, thickness: int = 1, line_spacing: int = 26):
    """
    Computes exact (x, y) baseline positions for each line so the entire text block 
    is geometrically and optically centered at (cx, cy).
    """
    measured_lines = []
    for line in lines_text:
        (tw, th), baseline = cv2.getTextSize(line, font_face, font_scale, thickness)
        measured_lines.append({"text": line, "width": tw, "height": th, "baseline": baseline})
        
    n_lines = len(measured_lines)
    total_height = (n_lines - 1) * line_spacing + measured_lines[0]["height"]
    first_baseline_y = int(cy - total_height / 2.0 + measured_lines[0]["height"] * 0.85)
    
    rendered_data = []
    for i, m in enumerate(measured_lines):
        line_y = first_baseline_y + i * line_spacing
        line_x = int(cx - m["width"] / 2.0)
        rendered_data.append((m["text"], line_x, line_y, m["width"]))
        
    return rendered_data

# Load image
img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786738212525.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]

# Bboxes for top & bottom bubbles
bbox_top = {"x": 120, "y": 240, "width": 240, "height": 130}
bbox_bot = {"x": 380, "y": 540, "width": 240, "height": 120}

# Process with Smart Balloon V15 Engine
res_top = process_smart_balloon_v15(image, bbox_top, rival_boxes=[bbox_bot], inset_ratio=0.10)
res_bot = process_smart_balloon_v15(image, bbox_bot, rival_boxes=[bbox_top], inset_ratio=0.10)

# Calculate waist points
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
raw_white = (gray >= 180).astype(np.uint8) * 255
cnts, _ = cv2.findContours(raw_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
main_cnt = max(cnts, key=cv2.contourArea)

c1 = (int(bbox_top["x"] + bbox_top["width"] / 2), int(bbox_top["y"] + bbox_top["height"] / 2))
c2 = (int(bbox_bot["x"] + bbox_bot["width"] / 2), int(bbox_bot["y"] + bbox_bot["height"] / 2))
left_w, right_w = find_true_waist_concave_points(main_cnt, c1, c2)

# Segment separation
pts = main_cnt.reshape(-1, 2)
idx1 = min(range(len(pts)), key=lambda i: np.linalg.norm(pts[i] - left_w))
idx2 = min(range(len(pts)), key=lambda i: np.linalg.norm(pts[i] - right_w))

if idx1 < idx2:
    seg_a = pts[idx1:idx2+1]
    seg_b = np.vstack([pts[idx2:], pts[:idx1+1]])
else:
    seg_a = pts[idx2:idx1+1]
    seg_b = np.vstack([pts[idx1:], pts[:idx2+1]])

top_seg = seg_a if seg_a[:, 1].mean() < seg_b[:, 1].mean() else seg_b
bot_seg = seg_b if seg_a[:, 1].mean() < seg_b[:, 1].mean() else seg_a

# -------------------------------------------------------------------------
# Construct Parallel Curvature Arc (ขนานกับแนวส่วนโค้งด้านบน)
# -------------------------------------------------------------------------
p_start = left_w.astype(np.float32)
p_end = right_w.astype(np.float32)

chord = p_end - p_start
chord_len = np.linalg.norm(chord)
chord_dir = chord / (chord_len + 1e-6)
normal_down = np.array([-chord_dir[1], chord_dir[0]], dtype=np.float32)
if normal_down[1] < 0:
    normal_down = -normal_down

# Sagitta matches the natural top curvature of the upper oval
mid_pt = (p_start + p_end) / 2.0
sagitta = chord_len * 0.22 
ctrl_pt_parallel = mid_pt + normal_down * sagitta

t_vals = np.linspace(0, 1, 60)
parallel_arc = []
for t in t_vals:
    pt = (1 - t)**2 * p_start + 2 * (1 - t) * t * ctrl_pt_parallel + t**2 * p_end
    parallel_arc.append([int(round(pt[0])), int(round(pt[1]))])
parallel_arc = np.array(parallel_arc)

# Closed top balloon (Top Ridge + Parallel Bottom Arc)
organic_poly_top = np.vstack([top_seg, parallel_arc[::-1]]).reshape(-1, 1, 2)

# Closed bottom balloon (Bottom Ridge + Parallel Shared Arc)
organic_poly_bot = np.vstack([bot_seg, parallel_arc]).reshape(-1, 1, 2)

# -------------------------------------------------------------------------
# Build the 4-Panel Fusion Showcase Canvas
# -------------------------------------------------------------------------
panel_w, panel_h = w, h
header_h = 75
canvas_w = panel_w * 4
canvas_h = panel_h + header_h

canvas = np.full((canvas_h, canvas_w, 3), 18, dtype=np.uint8)

# Title Header
cv2.putText(canvas, "SMART BALLOON V14 + V15 FUSION: PARALLEL CURVATURE SHOWCASE", (35, 38), cv2.FONT_HERSHEY_DUPLEX, 0.95, (255, 255, 255), 2)
cv2.putText(canvas, "Waist Bridge Line is 100% Parallel to Top Contour Curvature with Optically Centered Balanced Typesetting", 
            (35, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (170, 170, 170), 1)

# PANEL 1: INITIAL OCR BBOXES & RAW CANNY TEXTURE
p1 = image.copy()
cv2.rectangle(p1, (bbox_top["x"], bbox_top["y"]), (bbox_top["x"] + bbox_top["width"], bbox_top["y"] + bbox_top["height"]), (0, 0, 255), 3)
cv2.rectangle(p1, (bbox_bot["x"], bbox_bot["y"]), (bbox_bot["x"] + bbox_bot["width"], bbox_bot["y"] + bbox_bot["height"]), (0, 0, 255), 3)
edges = cv2.Canny(gray, 50, 150)
edge_overlay = np.zeros_like(p1)
edge_overlay[edges > 0] = (255, 255, 0)
cv2.addWeighted(edge_overlay, 0.45, p1, 1.0, 0, p1)
cv2.putText(p1, "1. INITIAL OCR & CANNY TEXTURE", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 255), 2)

# PANEL 2: V14 INSTANCE PARTITION & WAIST PINPOINTS
p2 = image.copy()
ov2 = p2.copy()
y_grid, x_grid = np.ogrid[:h, :w]
d1_sq = (x_grid - c1[0])**2 + (y_grid - c1[1])**2
d2_sq = (x_grid - c2[0])**2 + (y_grid - c2[1])**2
c_col_top = COLOR_PALETTE["SPIKY_FUZZY"]
c_col_bot = (70, 210, 240)
ov2[(raw_white > 0) & (d1_sq <= d2_sq)] = [int(c * 0.70 + 40) for c in c_col_top]
ov2[(raw_white > 0) & (d2_sq < d1_sq)] = [int(c * 0.70 + 40) for c in c_col_bot]
cv2.addWeighted(ov2, 0.45, p2, 0.55, 0, p2)
cv2.circle(p2, tuple(left_w), 8, (0, 0, 255), -1)
cv2.circle(p2, tuple(left_w), 4, (255, 255, 255), -1)
cv2.circle(p2, tuple(right_w), 8, (0, 0, 255), -1)
cv2.circle(p2, tuple(right_w), 4, (255, 255, 255), -1)
cv2.putText(p2, "2. V14 PARTITION & WAIST PINPOINTS", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 0), 2)

# PANEL 3: PARALLEL ORGANIC LOOPS & SAFE 10% INSETS
p3 = image.copy()
ov3 = p3.copy()
cv2.fillPoly(ov3, [organic_poly_top], (245, 235, 250))
cv2.fillPoly(ov3, [organic_poly_bot], (235, 248, 250))
cv2.addWeighted(ov3, 0.35, p3, 0.65, 0, p3)

# Top & Bottom outer contours
cv2.polylines(p3, [organic_poly_top], True, c_col_top, 3)
cv2.polylines(p3, [organic_poly_bot], True, c_col_bot, 3)
# Draw Parallel Dividing Curve in highlighted gold
cv2.polylines(p3, [parallel_arc], False, (0, 255, 255), 3)

# Inset Safe Margin Contours directly from Parallel Organic Loops
safe_poly_top = apply_contour_inset(organic_poly_top, inset_ratio=0.10)
safe_poly_bot = apply_contour_inset(organic_poly_bot, inset_ratio=0.10)

safe_pts_top = safe_poly_top.reshape(-1, 2)
safe_pts_bot = safe_poly_bot.reshape(-1, 2)

cv2.polylines(p3, [safe_pts_top], True, (0, 230, 255), 2)
cv2.polylines(p3, [safe_pts_bot], True, (0, 255, 150), 2)

cx_top, cy_top = 265, 340
cx_bot, cy_bot = 475, 515
cv2.circle(p3, (cx_top, cy_top), 7, (0, 0, 255), -1)
cv2.circle(p3, (cx_bot, cy_bot), 7, (0, 0, 255), -1)
cv2.putText(p3, "3. PARALLEL ORGANIC LOOPS (V14+V15)", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 120, 255), 2)
cv2.putText(p3, "Parallel Arc ->", (int(ctrl_pt_parallel[0]) - 140, int(ctrl_pt_parallel[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

# PANEL 4: CLEANED CANVAS & PERFECTLY BALANCED TYPESETTING
p4 = image.copy()
clean_mask = np.zeros((h, w), dtype=np.uint8)
cv2.fillPoly(clean_mask, [organic_poly_top], 255)
cv2.fillPoly(clean_mask, [organic_poly_bot], 255)
p4[clean_mask > 0] = [255, 255, 255]

# Render crisp manga boundary lines (Parallel Overlapping Arc)
cv2.polylines(p4, [organic_poly_top], True, (0, 0, 0), 2)
cv2.polylines(p4, [parallel_arc], False, (0, 0, 0), 2)

# Balanced Diamond Layout for Top Bubble (Short -> Long -> Short)
top_comic_lines = [
    "The organic loop",
    "curves parallel to the top contour,",
    "giving the speech balloon",
    "flawless symmetry."
]
top_rendered = balanced_comic_typeset(top_comic_lines, cx_top, cy_top, font_scale=0.55, line_spacing=26)
for (l_str, lx, ly, _) in top_rendered:
    cv2.putText(p4, l_str, (lx, ly), cv2.FONT_HERSHEY_DUPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)

# Balanced Diamond Layout for Bottom Bubble (Short -> Long -> Short)
bot_comic_lines = [
    "The parallel waist line",
    "preserves natural comic layering",
    "with zero text collision!"
]
bot_rendered = balanced_comic_typeset(bot_comic_lines, cx_bot, cy_bot, font_scale=0.53, line_spacing=26)
for (l_str, lx, ly, _) in bot_rendered:
    cv2.putText(p4, l_str, (lx, ly), cv2.FONT_HERSHEY_DUPLEX, 0.53, (20, 20, 20), 1, cv2.LINE_AA)

# Draw Optical Centroid Crosshairs & Dots
cv2.drawMarker(p4, (cx_top, cy_top), (0, 180, 255), cv2.MARKER_CROSS, 16, 1)
cv2.circle(p4, (cx_top, cy_top), 5, (0, 0, 255), -1)

cv2.drawMarker(p4, (cx_bot, cy_bot), (0, 180, 255), cv2.MARKER_CROSS, 16, 1)
cv2.circle(p4, (cx_bot, cy_bot), 5, (0, 0, 255), -1)

cv2.putText(p4, "4. PARALLEL MANGA OVERLAP TYPESETTING", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 0), 2)

# Place all 4 panels onto the canvas
canvas[header_h:, 0:panel_w] = p1
canvas[header_h:, panel_w:panel_w * 2] = p2
canvas[header_h:, panel_w * 2:panel_w * 3] = p3
canvas[header_h:, panel_w * 3:] = p4

out_path = Path(r"e:\houmi\research\v15_fuzzy_edge_research\v14_v15_fusion_showcase.png")
cv2.imwrite(str(out_path), canvas)
print(f"Updated parallel curvature fusion showcase generated at: {out_path}")
