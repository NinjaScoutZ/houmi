import cv2
import numpy as np
from pathlib import Path

img_path = Path(r"C:\Users\dansa\.gemini\antigravity\brain\ba78b3ed-7a47-4e3a-81c4-15af9fd1fe81\.user_uploaded\media_1786756784912.png")
image = cv2.imread(str(img_path))
h, w = image.shape[:2]
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

print(f"Image size: {w}x{h}")

# Seed point inside the speech balloon (e.g. center of the oval ~ (380, 360))
# Let's inspect what gray values look like
# Background below: light green / grey
# Black stroke around balloon: dark pixels ~ 0-60
# White interior of balloon: brightness ~ 240-255

# Let's test the current smart_balloon extraction vs dark boundary flood fill
white_thresh = 180
raw_white = (gray >= white_thresh).astype(np.uint8) * 255
close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
closed_white = cv2.morphologyEx(raw_white, cv2.MORPH_CLOSE, close_k)

# Save visualization of why closed_white leaked
vis_leak = np.zeros((h, w, 3), dtype=np.uint8)
vis_leak[closed_white > 0] = [0, 180, 255] # Orange leak
# Overlay image
vis_leak = cv2.addWeighted(image, 0.6, vis_leak, 0.4, 0)

out_leak = Path(r"e:\houmi\research\v15_fuzzy_edge_research\test_leak_reproduce.png")
cv2.imwrite(str(out_leak), vis_leak)
print(f"Reproduced leak visualization at: {out_leak}")
