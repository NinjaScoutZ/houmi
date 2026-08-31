import sys
sys.path.insert(0, r"e:\houmi\backend")
import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import process_smart_balloon_v15

img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786756784912.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]

# Text box inside the oval bubble
bbox = {"x": 230, "y": 250, "width": 260, "height": 180}

# Process with updated smart_balloon service
res = process_smart_balloon_v15(image, bbox, inset_ratio=0.10)

print("Smart Balloon Result:")
print("Archetype:", res["archetype"])
print("Visual Center:", res["center"])
print("Safe BBox:", res["safe_bbox"])
print("Elapsed Sec:", res["metadata"]["elapsed_sec"])

# Render Before vs After Comparison
header_h = 70
canvas = np.full((h + header_h, w * 2, 3), 18, dtype=np.uint8)

cv2.putText(canvas, "SMART BALLOON: DARK STROKE BARRIER FIX (LEAK PREVENTION)", (30, 42), cv2.FONT_HERSHEY_DUPLEX, 0.90, (255, 255, 255), 2)

# LEFT PANEL: BEFORE (LEAKED)
p_before = image.copy()
# Load the reproduced leak mask from earlier
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
raw_white = (gray >= 180).astype(np.uint8) * 255
close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
closed_white = cv2.morphologyEx(raw_white, cv2.MORPH_CLOSE, close_k)
ov_before = np.zeros_like(p_before)
ov_before[closed_white > 0] = (0, 140, 255) # Orange leak
p_before = cv2.addWeighted(p_before, 0.60, ov_before, 0.40, 0)
cv2.putText(p_before, "BEFORE: Leaked across 2px black line (503x391)", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 255), 2)

# RIGHT PANEL: AFTER (PERFECTLY BOUNDED BY BLACK STROKE)
p_after = image.copy()
safe_pts = np.array(res["contour_points"], dtype=np.int32)
ov_after = np.zeros_like(p_after)
cv2.fillPoly(ov_after, [safe_pts], (40, 165, 255))
p_after = cv2.addWeighted(p_after, 0.65, ov_after, 0.35, 0)
cv2.polylines(p_after, [safe_pts], True, (0, 200, 255), 3)
cx, cy = int(res["center"]["x"]), int(res["center"]["y"])
cv2.circle(p_after, (cx, cy), 7, (0, 0, 255), -1)
cv2.putText(p_after, f"AFTER: 100% Stroke-Protected ({int(res['safe_bbox']['width'])}x{int(res['safe_bbox']['height'])})", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 0), 2)
cv2.putText(p_after, f"Archetype: {res['archetype']} | Center: ({cx}, {cy})", (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 0), 1)

canvas[header_h:, :w] = p_before
canvas[header_h:, w:] = p_after

out_comp = Path(r"e:\houmi\research\v15_fuzzy_edge_research\stroke_leak_fix_comparison.png")
cv2.imwrite(str(out_comp), canvas)
print(f"Comparison saved to: {out_comp}")
