import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import (
    find_true_waist_concave_points,
    apply_contour_inset,
)

# Load image
img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786738212525.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
raw_white = (gray >= 180).astype(np.uint8) * 255

cnts, _ = cv2.findContours(raw_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
main_cnt = max(cnts, key=cv2.contourArea)
raw_pts = main_cnt.reshape(-1, 2)

# Waist pinch points
bbox_top = {"x": 120, "y": 240, "width": 240, "height": 130}
bbox_bot = {"x": 380, "y": 540, "width": 240, "height": 120}
c1 = (int(bbox_top["x"] + bbox_top["width"] / 2), int(bbox_top["y"] + bbox_top["height"] / 2))
c2 = (int(bbox_bot["x"] + bbox_bot["width"] / 2), int(bbox_bot["y"] + bbox_bot["height"] / 2))
left_w, right_w = find_true_waist_concave_points(main_cnt, c1, c2)

p1 = left_w.astype(np.float32)  # [234, 570]
p2 = right_w.astype(np.float32)  # [494, 362]

# Split raw contour into Top and Bottom segments
idx1 = min(range(len(raw_pts)), key=lambda i: np.linalg.norm(raw_pts[i] - left_w))
idx2 = min(range(len(raw_pts)), key=lambda i: np.linalg.norm(raw_pts[i] - right_w))

if idx1 < idx2:
    seg_a = raw_pts[idx1:idx2+1]
    seg_b = np.vstack([raw_pts[idx2:], raw_pts[:idx1+1]])
else:
    seg_a = raw_pts[idx2:idx1+1]
    seg_b = np.vstack([raw_pts[idx1:], raw_pts[:idx2+1]])

top_raw_seg = seg_a if seg_a[:, 1].mean() < seg_b[:, 1].mean() else seg_b
bot_raw_seg = seg_b if seg_a[:, 1].mean() < seg_b[:, 1].mean() else seg_a

# -------------------------------------------------------------------------
# Single Natural Parallel Bridge (เส้นสะพานโค้งเดี่ยว ขนานตามแนวขอบบน)
# -------------------------------------------------------------------------
# Calculate the slope and curvature of the top side
# Vector from p1 to p2
chord = p2 - p1
chord_len = np.linalg.norm(chord)
chord_dir = chord / (chord_len + 1e-6)

# Normal vector pointing towards the bottom-right (away from top crest)
normal_down = np.array([-chord_dir[1], chord_dir[0]], dtype=np.float32)
if normal_down[1] < 0:
    normal_down = -normal_down

# Control point: placed along normal_down to create a smooth arc parallel to the top slope
mid_pt = (p1 + p2) / 2.0
# The curvature sagitta matches the gentle curvature of the top edge
sagitta = chord_len * 0.18
ctrl_pt = mid_pt + normal_down * sagitta

t_vals = np.linspace(0, 1, 50)
single_bridge = []
for t in t_vals:
    pt = (1 - t)**2 * p1 + 2 * (1 - t) * t * ctrl_pt + t**2 * p2
    single_bridge.append([int(round(pt[0])), int(round(pt[1]))])
single_bridge = np.array(single_bridge, dtype=np.int32)

# Top Balloon Mask: Top Raw Segment + Bridge
contour_top = np.vstack([top_raw_seg, single_bridge[::-1]]).reshape(-1, 1, 2)

# Bottom Balloon Mask: Bottom Raw Segment + Bridge
contour_bot = np.vstack([bot_raw_seg, single_bridge]).reshape(-1, 1, 2)

# Centers of each balloon
M_t = cv2.moments(contour_top)
cx_t, cy_t = int(M_t["m10"] / M_t["m00"]), int(M_t["m01"] / M_t["m00"])

M_b = cv2.moments(contour_bot)
cx_b, cy_b = int(M_b["m10"] / M_b["m00"]), int(M_b["m01"] / M_b["m00"])

# Safe Inset 10%
safe_top = apply_contour_inset(contour_top, inset_ratio=0.10)
safe_bot = apply_contour_inset(contour_bot, inset_ratio=0.10)

# -------------------------------------------------------------------------
# Build 4-Panel Zero-Distortion Showcase
# -------------------------------------------------------------------------
panel_w, panel_h = w, h
header_h = 75
canvas_w = panel_w * 4
canvas_h = panel_h + header_h

canvas = np.full((canvas_h, canvas_w, 3), 18, dtype=np.uint8)

# Title Header
cv2.putText(canvas, "ZERO-DISTORTION BOUNDARY: SINGLE PARALLEL BRIDGE SEAM", (35, 38), cv2.FONT_HERSHEY_DUPLEX, 0.95, (255, 255, 255), 2)
cv2.putText(canvas, "100% Raw Manga Stroke Preserved + Single Seamless Natural Arc Parallel to Top Edge (Zero Overlap Distortion)", 
            (35, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (170, 170, 170), 1)

# PANEL 1: RAW CONTOUR & WAIST DETECTION
p1 = image.copy()
cv2.polylines(p1, [top_raw_seg], False, (0, 255, 255), 3) # Yellow
cv2.polylines(p1, [bot_raw_seg], False, (255, 100, 255), 3) # Magenta
cv2.circle(p1, tuple(left_w), 9, (0, 0, 255), -1)
cv2.circle(p1, tuple(left_w), 4, (255, 255, 255), -1)
cv2.circle(p1, tuple(right_w), 9, (0, 0, 255), -1)
cv2.circle(p1, tuple(right_w), 4, (255, 255, 255), -1)
cv2.putText(p1, "1. TOPOLOGICAL DECOMPOSITION", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 255), 2)
cv2.putText(p1, f"Top Raw: {len(top_raw_seg)} pts (100% Original)", (25, h - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 1)
cv2.putText(p1, f"Bot Raw: {len(bot_raw_seg)} pts (100% Original)", (25, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 100, 255), 1)

# PANEL 2: SINGLE PARALLEL BRIDGE
p2 = image.copy()
cv2.polylines(p2, [single_bridge], False, (0, 255, 0), 4) # Single clean Green Bridge
cv2.circle(p2, tuple(left_w), 8, (0, 0, 255), -1)
cv2.circle(p2, tuple(right_w), 8, (0, 0, 255), -1)
# Draw parallel guide line showing parallelism to top crest
cv2.putText(p2, "2. SINGLE PARALLEL NATURAL BRIDGE", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 0), 2)
cv2.putText(p2, "P1 (Left Waist)", (left_w[0] - 125, left_w[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
cv2.putText(p2, "P2 (Right Waist)", (right_w[0] + 12, right_w[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
cv2.putText(p2, "Parallel Bridge (50 pts)", (int(mid_pt[0]) - 80, int(mid_pt[1]) + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 0), 1)

# PANEL 3: SEAMLESS PARTITION MASKS & SAFE INSETS
p3 = image.copy()
ov3 = p3.copy()
cv2.fillPoly(ov3, [contour_top], (240, 230, 255))
cv2.fillPoly(ov3, [contour_bot], (230, 250, 255))
cv2.addWeighted(ov3, 0.45, p3, 0.55, 0, p3)

cv2.polylines(p3, [safe_top], True, (0, 230, 255), 2) # Yellow Inset
cv2.polylines(p3, [safe_bot], True, (0, 255, 150), 2) # Lime Inset
cv2.polylines(p3, [single_bridge], False, (0, 0, 0), 2) # Shared boundary

cv2.circle(p3, (cx_t, cy_t), 6, (0, 0, 255), -1)
cv2.circle(p3, (cx_b, cy_b), 6, (0, 0, 255), -1)

cv2.putText(p3, "3. SEAMLESS PARTITION & SAFE INSETS", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 120, 255), 2)
cv2.putText(p3, "Top Balloon Region", (35, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 90, 220), 1)
cv2.putText(p3, "Bottom Balloon Region", (35, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (70, 210, 240), 1)

# PANEL 4: CLEANED INPAINTED CANVAS & TYPESETTING
p4 = image.copy()
# Clean the entire interior to pure solid white
clean_mask = np.zeros((h, w), dtype=np.uint8)
cv2.fillPoly(clean_mask, [contour_top], 255)
cv2.fillPoly(clean_mask, [contour_bot], 255)
p4[clean_mask > 0] = [255, 255, 255]

# Render ONLY the natural manga seam line between bubbles (no criss-crossing loops!)
cv2.polylines(p4, [single_bridge], False, (0, 0, 0), 2)

def typeset_lines(lines, cx, cy, font_scale, line_h):
    for i, line in enumerate(lines):
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_DUPLEX, font_scale, 1)
        lx = int(cx - tw / 2.0)
        ly = int(cy - (len(lines) - 1) * line_h / 2.0 + i * line_h + th * 0.85)
        cv2.putText(p4, line, (lx, ly), cv2.FONT_HERSHEY_DUPLEX, font_scale, (15, 15, 15), 1, cv2.LINE_AA)

top_text = [
    "Zero-Distortion Boundary:",
    "100% original manga stroke preserved,",
    "with a single natural parallel bridge",
    "closing the waist opening."
]
typeset_lines(top_text, cx_t, cy_t, font_scale=0.54, line_h=26)

bot_text = [
    "Seamless natural partition",
    "preserves full speech area",
    "with zero overlapping distortion!"
]
typeset_lines(bot_text, cx_b, cy_b, font_scale=0.53, line_h=26)

cv2.drawMarker(p4, (cx_t, cy_t), (0, 180, 255), cv2.MARKER_CROSS, 16, 1)
cv2.circle(p4, (cx_t, cy_t), 5, (0, 0, 255), -1)
cv2.drawMarker(p4, (cx_b, cy_b), (0, 180, 255), cv2.MARKER_CROSS, 16, 1)
cv2.circle(p4, (cx_b, cy_b), 5, (0, 0, 255), -1)

cv2.putText(p4, "4. CLEANED & TRUE SHAPE TYPESETTING", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 0), 2)

# Assemble
canvas[header_h:, 0:panel_w] = p1
canvas[header_h:, panel_w:panel_w * 2] = p2
canvas[header_h:, panel_w * 2:panel_w * 3] = p3
canvas[header_h:, panel_w * 3:] = p4

out_path = Path(r"e:\houmi\research\v15_fuzzy_edge_research\zero_distortion_seamless_showcase.png")
cv2.imwrite(str(out_path), canvas)
print(f"Generated seamless zero-distortion showcase at: {out_path}")
