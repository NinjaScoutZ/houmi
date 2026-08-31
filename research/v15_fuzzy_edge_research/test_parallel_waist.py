import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import find_true_waist_concave_points

img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786738212525.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
raw_white = (gray >= 180).astype(np.uint8) * 255
cnts, _ = cv2.findContours(raw_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
main_cnt = max(cnts, key=cv2.contourArea)

# Waist points
bbox_top = {"x": 120, "y": 240, "width": 240, "height": 130}
bbox_bot = {"x": 380, "y": 540, "width": 240, "height": 120}
c1 = (int(bbox_top["x"] + bbox_top["width"] / 2), int(bbox_top["y"] + bbox_top["height"] / 2))
c2 = (int(bbox_bot["x"] + bbox_bot["width"] / 2), int(bbox_bot["y"] + bbox_bot["height"] / 2))
left_w, right_w = find_true_waist_concave_points(main_cnt, c1, c2)

print(f"Left Waist: {left_w}, Right Waist: {right_w}")

# Top sub-segment (the top ridge of the top bubble)
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
# Method: Natural Parallel Curve (ขนานกับแนวโค้งด้านบน)
# -------------------------------------------------------------------------
# The top ridge goes from left_w to right_w passing through the top peak.
# To make the bottom waist line PARALLEL to the top ridge:
# Vector connecting left_w to right_w:
p_start = left_w.astype(np.float32)
p_end = right_w.astype(np.float32)

# Calculate the tilt angle of the top bubble
chord = p_end - p_start
chord_len = np.linalg.norm(chord)
chord_dir = chord / (chord_len + 1e-6)
# Normal vector pointing downwards into the bottom bubble
normal_down = np.array([-chord_dir[1], chord_dir[0]], dtype=np.float32)
if normal_down[1] < 0:
    normal_down = -normal_down

# Parallel curvature control point:
# Control point is positioned in direction of normal_down, tilted parallel to the top bubble's ellipse
# Midpoint of chord
mid_pt = (p_start + p_end) / 2.0
# The curvature depth (sagitta) is proportional to the chord length and matches top curvature
sagitta = chord_len * 0.22 # Natural rounded sagitta
ctrl_pt_parallel = mid_pt + normal_down * sagitta

# Generate smooth parallel Bézier arc
t_vals = np.linspace(0, 1, 60)
parallel_arc = []
for t in t_vals:
    pt = (1 - t)**2 * p_start + 2 * (1 - t) * t * ctrl_pt_parallel + t**2 * p_end
    parallel_arc.append([int(round(pt[0])), int(round(pt[1]))])
parallel_arc = np.array(parallel_arc)

# Closed top balloon using parallel arc
top_closed_poly = np.vstack([top_seg, parallel_arc[::-1]]).reshape(-1, 1, 2)

# Closed bottom balloon using the exact same overlapping parallel arc (Foreground / Background overlap)
bot_closed_poly = np.vstack([bot_seg, parallel_arc]).reshape(-1, 1, 2)

# Test visualization
vis = image.copy()
cv2.polylines(vis, [top_closed_poly], True, (0, 255, 0), 2)
cv2.polylines(vis, [bot_closed_poly], True, (255, 0, 255), 2)
cv2.polylines(vis, [parallel_arc], False, (0, 0, 255), 3) # Red = Parallel dividing curve

out_test = Path(r"e:\houmi\research\v15_fuzzy_edge_research\test_parallel_curve.png")
cv2.imwrite(str(out_test), vis)
print(f"Parallel curve test saved to: {out_test}")
