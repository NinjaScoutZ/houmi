import cv2
import numpy as np
from pathlib import Path

img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786756784912.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Seed point from text box (inside the balloon, e.g. (380, 360))
seed_x, seed_y = 380, 360

# -------------------------------------------------------------------------
# Method 1: Edge-Barrier FloodFill (Dark Stroke Barrier)
# -------------------------------------------------------------------------
# 1. Detect dark boundary strokes (black line art)
dark_stroke = (gray < 85).astype(np.uint8) * 255

# 2. Build floodfill mask where dark strokes act as hard barriers (255)
# In OpenCV floodFill, mask must be (h+2, w+2)
flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
flood_mask[1:-1, 1:-1] = (dark_stroke > 0).astype(np.uint8) * 1

# Flood fill from seed point on the gray image with fixed range
# Stops as soon as pixel drops significantly or hits dark stroke
filled_img = gray.copy()
cv2.floodFill(filled_img, flood_mask, (seed_x, seed_y), 255, loDiff=35, upDiff=35, flags=4 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))

# The flooded region is where mask has value 255
balloon_mask = (flood_mask[1:-1, 1:-1] == 255).astype(np.uint8) * 255

# Morphological close ONLY INSIDE the balloon (small 5x5 kernel to fill text holes without jumping borders)
fill_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
balloon_mask = cv2.morphologyEx(balloon_mask, cv2.MORPH_CLOSE, fill_k)
# Fill text holes
cnts, _ = cv2.findContours(balloon_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
main_balloon_cnt = max(cnts, key=cv2.contourArea)
solid_mask = np.zeros_like(balloon_mask)
cv2.fillPoly(solid_mask, [main_balloon_cnt], 255)

# Visualize result
vis_fixed = image.copy()
vis_overlay = np.zeros_like(vis_fixed)
vis_overlay[solid_mask > 0] = (40, 165, 255) # Warm Amber / Orange (Smooth Oval)
vis_result = cv2.addWeighted(vis_fixed, 0.60, vis_overlay, 0.40, 0)
cv2.polylines(vis_result, [main_balloon_cnt], True, (0, 140, 255), 3)

out_path = Path(r"e:\houmi\research\v15_fuzzy_edge_research\test_stroke_protected_fixed.png")
cv2.imwrite(str(out_path), vis_result)
print(f"Fixed balloon extraction saved to: {out_path}")
print(f"Main contour area: {cv2.contourArea(main_balloon_cnt):.1f} px, Bounding Box: {cv2.boundingRect(main_balloon_cnt)}")
