#!/usr/bin/env python3
"""Visualize Smart Balloon typesetting result on debug_crop_112.png"""

import cv2
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, "backend")

from app.services.smart_balloon import process_smart_balloon_v15
from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape
from app.services.typesetting.service import segment_text
from PIL import Image, ImageDraw, ImageFont

# Load the debug image
img = cv2.imread("debug_crop_112.png")
h, w = img.shape[:2]

text_bbox = {"x": 0, "y": 0, "width": w, "height": h}
sb_result = process_smart_balloon_v15(img, text_bbox, inset_ratio=0.10)

chinese_text = "我、我们的全力一击！！"

# Use proper tokenization
tokens = segment_text(chinese_text)
print(f"Tokens: {tokens} ({len(tokens)} tokens)")

block = {
    "x": text_bbox["x"],
    "y": text_bbox["y"],
    "width": text_bbox["width"],
    "height": text_bbox["height"],
    "text": chinese_text,
}

font_path = Path("C:/Windows/Fonts/msyh.ttc")
if not font_path.exists():
    font_path = Path("C:/Windows/Fonts/simhei.ttf")

result = fit_text_to_smart_balloon_shape(
    block=block,
    sb=sb_result,
    tokens=tokens,  # Use segmented tokens
    font_path=str(font_path),
)

if not result:
    print("❌ Typesetting failed")
    exit(1)

# Create visualization
vis_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
pil_img = Image.fromarray(vis_img)
draw = ImageDraw.Draw(pil_img)

# Draw Smart Balloon contour
contour_pts = sb_result.get("contour_points", [])
if contour_pts:
    pts_tuple = [(int(p[0]), int(p[1])) for p in contour_pts]
    draw.polygon(pts_tuple, outline=(255, 140, 0), width=3)  # Orange border

# Draw safe bbox
safe_bbox = sb_result["safe_bbox"]
sx, sy, sw, sh = safe_bbox["x"], safe_bbox["y"], safe_bbox["width"], safe_bbox["height"]
draw.rectangle([sx, sy, sx + sw, sy + sh], outline=(0, 200, 0), width=2)  # Green safe bbox

# Draw centroid
cx, cy = sb_result["center"]["x"], sb_result["center"]["y"]
r = 10
draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 0, 0))  # Red centroid

# Draw text at calculated position
font_size = int(result["font_size"])
try:
    font = ImageFont.truetype(str(font_path), font_size)
except:
    font = ImageFont.load_default()

lines = result.get("lines") or result.get("explicit_lines") or []
line_height = font_size * 1.25

# Center text at centroid
total_text_height = len(lines) * line_height
text_y = cy - total_text_height / 2

for i, line in enumerate(lines):
    bbox = draw.textbbox((0, 0), line, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = cx - text_width / 2
    y_pos = text_y + i * line_height

    # Draw text with black outline for visibility
    for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
        draw.text((text_x + dx, y_pos + dy), line, font=font, fill=(0, 0, 0))
    draw.text((text_x, y_pos), line, font=font, fill=(0, 0, 0))

# Add info overlay
info_y = 10
draw.text((10, info_y), f"Smart Balloon: {sb_result['archetype']}", font=None, fill=(255, 255, 0))
info_y += 20
draw.text((10, info_y), f"Font: {font_size}px ({font_size/sh*100:.1f}% of height)", font=None, fill=(255, 255, 0))
info_y += 20
draw.text((10, info_y), f"Lines: {len(lines)}", font=None, fill=(255, 255, 0))
info_y += 20
vertical_fill = result['total_height']/sh*100
draw.text((10, info_y), f"Vertical fill: {vertical_fill:.1f}%", font=None, fill=(0, 255, 0))
info_y += 20
draw.text((10, info_y), f"Breathing room: {100-vertical_fill:.1f}%", font=None, fill=(0, 255, 0))

# Save result
output = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
cv2.imwrite("debug_crop_112_with_typesetting.png", output)

print("✅ Saved visualization to: debug_crop_112_with_typesetting.png")
print(f"\n📊 Summary:")
print(f"   Archetype: {sb_result['archetype']}")
print(f"   Font size: {font_size}px")
print(f"   Lines: {len(lines)}")
print(f"   Vertical fill: {result['total_height']/sh*100:.1f}%")
print(f"   Breathing room: {100-result['total_height']/sh*100:.1f}%")
