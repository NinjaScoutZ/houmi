import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import process_smart_balloon_v15

img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786734138732.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

bbox_top = {"x": 120, "y": 240, "width": 240, "height": 120}
bbox_bot = {"x": 380, "y": 550, "width": 220, "height": 110}

rival_for_top = [bbox_bot]
rival_for_bot = [bbox_top]

res_top = process_smart_balloon_v15(image, bbox_top, rival_boxes=rival_for_top, inset_ratio=0.10)
res_bot = process_smart_balloon_v15(image, bbox_bot, rival_boxes=rival_for_bot, inset_ratio=0.10)

# Panel 1: Canny Edge Analysis
edges = cv2.Canny(gray, 50, 150)
edge_vis = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

# Panel 2: Contours & Inset
contour_vis = image.copy()
if res_top["success"]:
    raw_pts = np.array(res_top["raw_contour_points"], dtype=np.int32)
    safe_pts = np.array(res_top["contour_points"], dtype=np.int32)
    cv2.polylines(contour_vis, [raw_pts], True, (0, 255, 0), 2)
    cv2.polylines(contour_vis, [safe_pts], True, (0, 255, 255), 2)
    cx, cy = int(res_top["center"]["x"]), int(res_top["center"]["y"])
    cv2.circle(contour_vis, (cx, cy), 6, (0, 0, 255), -1)

if res_bot["success"]:
    raw_pts_b = np.array(res_bot["raw_contour_points"], dtype=np.int32)
    safe_pts_b = np.array(res_bot["contour_points"], dtype=np.int32)
    cv2.polylines(contour_vis, [raw_pts_b], True, (255, 120, 0), 2)
    cv2.polylines(contour_vis, [safe_pts_b], True, (255, 0, 255), 2)
    cxb, cyb = int(res_bot["center"]["x"]), int(res_bot["center"]["y"])
    cv2.circle(contour_vis, (cxb, cyb), 6, (0, 0, 255), -1)

# Panel 3: Typesetting preview text demo inside the safe contour
typeset_vis = image.copy()
# Draw semi-transparent safe bounds
overlay = typeset_vis.copy()
if res_top["success"]:
    cv2.fillPoly(overlay, [np.array(res_top["contour_points"], dtype=np.int32)], (240, 240, 240))
if res_bot["success"]:
    cv2.fillPoly(overlay, [np.array(res_bot["contour_points"], dtype=np.int32)], (240, 240, 240))
cv2.addWeighted(overlay, 0.4, typeset_vis, 0.6, 0, typeset_vis)

# Put mock text
cv2.putText(typeset_vis, "TOP BUBBLE TEXT", (160, 340), cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 0, 0), 2)
cv2.putText(typeset_vis, "(SPIKY FUZZY)", (175, 380), cv2.FONT_HERSHEY_DUPLEX, 0.6, (50, 50, 50), 1)

cv2.putText(typeset_vis, "BOTTOM BUBBLE", (380, 490), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 0, 0), 2)
cv2.putText(typeset_vis, "(SPIKY FUZZY)", (390, 525), cv2.FONT_HERSHEY_DUPLEX, 0.55, (50, 50, 50), 1)

# Combine 3 panels horizontally
h_p, w_p = h, w
header_h = 50
canvas_all = np.zeros((h_p + header_h, w_p * 3, 3), dtype=np.uint8)

# Titles
cv2.putText(canvas_all, "1. RAW CANNY EDGES (DENSE FUZZ)", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
cv2.putText(canvas_all, "2. SMART BALLOON V15 CONTOURS", (w_p + 20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
cv2.putText(canvas_all, "3. TYPESETTING & CENTROID FIT", (w_p * 2 + 20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 255), 2)

canvas_all[header_h:, 0:w_p] = edge_vis
canvas_all[header_h:, w_p:w_p*2] = contour_vis
canvas_all[header_h:, w_p*2:] = typeset_vis

out_diag = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\fuzzy_conjoined_comparison.png")
cv2.imwrite(str(out_diag), canvas_all)
print("Diagnostic side-by-side saved to:", out_diag)
