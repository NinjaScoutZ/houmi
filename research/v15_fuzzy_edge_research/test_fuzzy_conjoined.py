import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import (
    process_smart_balloon_v15,
    detect_fuzzy_edge_density,
    compute_edge_roughness,
    classify_balloon_archetype,
)

img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786734138732.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]
print(f"Image loaded: {w}x{h}")

# Let's define text bboxes for the 2 bubbles
# 1. Top-Left Bubble Text Box (located in the upper fuzzy oval)
bbox_top = {"x": 120, "y": 240, "width": 240, "height": 120}
# 2. Bottom-Right Bubble Text Box (located in the lower fuzzy oval)
bbox_bot = {"x": 380, "y": 550, "width": 220, "height": 110}

rival_for_top = [{"x": bbox_bot["x"], "y": bbox_bot["y"], "width": bbox_bot["width"], "height": bbox_bot["height"]}]
rival_for_bot = [{"x": bbox_top["x"], "y": bbox_top["y"], "width": bbox_top["width"], "height": bbox_top["height"]}]

print("\n--- Running Smart Balloon V15 on Top Bubble ---")
res_top = process_smart_balloon_v15(image, bbox_top, rival_boxes=rival_for_top, inset_ratio=0.10)
print("Top Result:")
print("Success:", res_top["success"])
print("Archetype:", res_top["archetype"])
print("Metadata:", res_top["metadata"])
print("Raw BBox:", res_top["raw_bbox"])
print("Safe BBox:", res_top["safe_bbox"])
print("Center:", res_top["center"])

print("\n--- Running Smart Balloon V15 on Bottom Bubble ---")
res_bot = process_smart_balloon_v15(image, bbox_bot, rival_boxes=rival_for_bot, inset_ratio=0.10)
print("Bottom Result:")
print("Success:", res_bot["success"])
print("Archetype:", res_bot["archetype"])
print("Metadata:", res_bot["metadata"])
print("Raw BBox:", res_bot["raw_bbox"])
print("Safe BBox:", res_bot["safe_bbox"])
print("Center:", res_bot["center"])

# Create visualization output
vis = image.copy()

# Draw Top Bubble
if res_top["success"]:
    raw_pts = np.array(res_top["raw_contour_points"], dtype=np.int32)
    safe_pts = np.array(res_top["contour_points"], dtype=np.int32)
    cv2.polylines(vis, [raw_pts], True, (0, 255, 0), 2)   # Green = Raw contour
    cv2.polylines(vis, [safe_pts], True, (0, 255, 255), 2) # Yellow = 10% Inset Safe contour
    cx, cy = int(res_top["center"]["x"]), int(res_top["center"]["y"])
    cv2.circle(vis, (cx, cy), 6, (0, 0, 255), -1)          # Red = Centroid
    cv2.putText(vis, f"TOP: {res_top['archetype']} (EdgeDens: {res_top['metadata'].get('edge_density', 0):.2f})", 
                (int(res_top['safe_bbox']['x']), int(res_top['safe_bbox']['y']) - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

# Draw Bottom Bubble
if res_bot["success"]:
    raw_pts_b = np.array(res_bot["raw_contour_points"], dtype=np.int32)
    safe_pts_b = np.array(res_bot["contour_points"], dtype=np.int32)
    cv2.polylines(vis, [raw_pts_b], True, (255, 100, 0), 2) # Blue = Raw contour
    cv2.polylines(vis, [safe_pts_b], True, (255, 0, 255), 2) # Magenta = 10% Inset Safe contour
    cxb, cyb = int(res_bot["center"]["x"]), int(res_bot["center"]["y"])
    cv2.circle(vis, (cxb, cyb), 6, (0, 0, 255), -1)
    cv2.putText(vis, f"BOT: {res_bot['archetype']} (EdgeDens: {res_bot['metadata'].get('edge_density', 0):.2f})", 
                (int(res_bot['safe_bbox']['x']), int(res_bot['safe_bbox']['y']) - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2)

# Draw text bboxes
cv2.rectangle(vis, (bbox_top["x"], bbox_top["y"]), (bbox_top["x"]+bbox_top["width"], bbox_top["y"]+bbox_top["height"]), (255, 255, 255), 1)
cv2.rectangle(vis, (bbox_bot["x"], bbox_bot["y"]), (bbox_bot["x"]+bbox_bot["width"], bbox_bot["y"]+bbox_bot["height"]), (255, 255, 255), 1)

out_vis_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\debug_fuzzy_test_result.png")
cv2.imwrite(str(out_vis_path), vis)
print(f"\nVisualization saved to: {out_vis_path}")
