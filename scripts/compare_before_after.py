"""Compare before/after Smart Balloon typesetting adjustments."""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import sys
sys.path.insert(0, 'backend')

from app.services.smart_balloon import process_smart_balloon_v15
from app.services.typesetting.service import segment_text

# Load the debug image
img = cv2.imread('debug_crop_112.png')
h, w = img.shape[:2]

# Detect Smart Balloon
text_bbox = {'x': 0, 'y': 0, 'width': w, 'height': h}
sb_result = process_smart_balloon_v15(img, text_bbox, inset_ratio=0.10)

chinese_text = '我、我们的全力一击！！'
tokens = segment_text(chinese_text)

# Get font
from pathlib import Path
font_path = Path('C:/Windows/Fonts/msyh.ttc')
if not font_path.exists():
    font_path = Path('C:/Windows/Fonts/simhei.ttf')

# Create side-by-side comparison
pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
canvas_width = w * 2 + 60  # gap between images
canvas = Image.new('RGB', (canvas_width, h + 100), (20, 20, 20))
draw = ImageDraw.Draw(canvas)

# LEFT: OLD version (154px, 74% fill)
left_img = pil_img.copy()
left_draw = ImageDraw.Draw(left_img)

# Draw contour
contour_pts = sb_result['contour_points']
left_draw.polygon([(p[0], p[1]) for p in contour_pts], outline=(255, 165, 0), width=2)

# Draw OLD text (154px, single pass)
safe_bbox = sb_result['safe_bbox']
cx = safe_bbox['x'] + safe_bbox['width'] / 2
cy = safe_bbox['y'] + safe_bbox['height'] / 2

old_font = ImageFont.truetype(str(font_path), 154)
old_lines = ['我、我们的', '全力一击！！']
old_line_h = 154 * 1.25
old_total_h = len(old_lines) * old_line_h
old_y = cy - old_total_h / 2

for line in old_lines:
    bbox = left_draw.textbbox((0, 0), line, font=old_font)
    line_w = bbox[2] - bbox[0]
    left_draw.text((cx - line_w/2, old_y), line, font=old_font, fill=(0, 0, 0))
    old_y += old_line_h

# Add OLD label
left_draw.rectangle([(0, 0), (200, 35)], fill=(200, 50, 50))
left_draw.text((10, 5), 'BEFORE (OLD)', font=None, fill=(255, 255, 255))
left_draw.text((10, 20), '154px, 74% fill', font=None, fill=(255, 255, 255))

canvas.paste(left_img, (0, 50))

# RIGHT: NEW version (124px, 59.6% fill)
right_img = pil_img.copy()
right_draw = ImageDraw.Draw(right_img)

# Draw contour
right_draw.polygon([(p[0], p[1]) for p in contour_pts], outline=(255, 165, 0), width=2)

# Draw NEW text (124px)
new_font = ImageFont.truetype(str(font_path), 124)
new_lines = ['我、我们的', '全力一击！！']
new_line_h = 124 * 1.25
new_total_h = len(new_lines) * new_line_h
new_y = cy - new_total_h / 2

for line in new_lines:
    bbox = right_draw.textbbox((0, 0), line, font=new_font)
    line_w = bbox[2] - bbox[0]
    right_draw.text((cx - line_w/2, new_y), line, font=new_font, fill=(0, 0, 0))
    new_y += new_line_h

# Add NEW label
right_draw.rectangle([(0, 0), (200, 35)], fill=(50, 200, 50))
right_draw.text((10, 5), 'AFTER (NEW)', font=None, fill=(255, 255, 255))
right_draw.text((10, 20), '124px, 59.6% fill', font=None, fill=(255, 255, 255))

canvas.paste(right_img, (w + 60, 50))

# Add title and metrics
title_font = None
draw.text((canvas_width//2 - 150, 10), 'Smart Balloon Typesetting Comparison', font=title_font, fill=(255, 255, 0))

# Add comparison metrics at bottom
metrics_y = h + 55
draw.text((10, metrics_y), '📊 Improvements:', font=title_font, fill=(100, 255, 100))
draw.text((10, metrics_y + 15), '   • Font size: 154px → 124px (-19.5%)', font=title_font, fill=(200, 200, 200))
draw.text((10, metrics_y + 30), '   • Vertical fill: 74.0% → 59.6% (-14.4%)', font=title_font, fill=(200, 200, 200))
draw.text((canvas_width//2, metrics_y + 15), '   • Breathing room: 26.0% → 40.4% (+14.4%)', font=title_font, fill=(200, 200, 200))
draw.text((canvas_width//2, metrics_y + 30), '   • Lines: 2 → 2 (same)', font=title_font, fill=(200, 200, 200))

output_path = 'debug_before_after_comparison.png'
canvas.save(output_path)
print(f'✅ Saved comparison to: {output_path}')
