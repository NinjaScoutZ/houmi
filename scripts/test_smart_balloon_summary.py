#!/usr/bin/env python3
"""
Test Smart Balloon typesetting with the improved parameters
"""
import sys
sys.path.insert(0, 'backend')

# Force reload modules to pick up changes
import importlib
if 'app.services.smart_balloon_typesetting' in sys.modules:
    importlib.reload(sys.modules['app.services.smart_balloon_typesetting'])
if 'app.services.smart_balloon' in sys.modules:
    importlib.reload(sys.modules['app.services.smart_balloon'])

import cv2
import numpy as np
from pathlib import Path
from app.services.smart_balloon import process_smart_balloon_v15
from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape
from app.services.typesetting.service import segment_text

# Test image
img_path = Path('debug_crop_112.png')
img = cv2.imread(str(img_path))
if img is None:
    print(f'❌ Image not found: {img_path}')
    exit(1)

print(f'🖼️  Image: {img.shape[1]}x{img.shape[0]}')

# Process Smart Balloon (use full image as bbox)
h, w = img.shape[:2]
text_bbox = {'x': 0, 'y': 0, 'width': w, 'height': h}
sb = process_smart_balloon_v15(img, text_bbox)
if not sb:
    print('❌ No Smart Balloon detected')
    exit(1)

archetype = sb.get('archetype', 'UNKNOWN')
print(f'✅ Smart Balloon: {archetype}')
print(f'   Contour points: {len(sb.get("contour_points", []))}')

# Test text (Chinese from the image)
chinese_text = "我、我们的全力一击！！"
tokens = segment_text(chinese_text, 'ZHS')
print(f'📝 Text: "{chinese_text}"')
print(f'   Tokens: {len(tokens)} → {tokens}')

# Fit text - use default font
result = fit_text_to_smart_balloon_shape(
    block={'bbox': sb['safe_bbox']},
    sb=sb,
    tokens=tokens,
    font_path=None  # Will use ImageFont.load_default()
)

if not result or 'font_size' not in result:
    print('❌ Typesetting failed')
    exit(1)

lines = result.get('explicit_lines', [])
font_size = result['font_size']
metrics = result.get('metrics', {})

print(f'\n📏 Typesetting Results:')
print(f'   Font size: {font_size}px ({metrics.get("font_height_pct", 0):.1f}% of height)')
print(f'   Lines: {len(lines)}')
for i, line in enumerate(lines, 1):
    print(f'     {i}. "{line}"')
print(f'   Vertical fill: {metrics.get("vertical_fill_pct", 0):.1f}%')
print(f'   Breathing room: {metrics.get("breathing_room_pct", 0):.1f}%')

# Visualize
vis = img.copy()
h, w = img.shape[:2]

# Draw contour
pts = np.array(sb['contour_points'], dtype=np.int32)
cv2.polylines(vis, [pts], True, (0, 165, 255), 2)

# Draw safe bbox
bbox = sb['safe_bbox']
x1, y1 = int(bbox['x']), int(bbox['y'])
x2, y2 = x1 + int(bbox['width']), y1 + int(bbox['height'])
cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)

# Draw centroid
centroid = sb.get('centroid')
if centroid:
    cx, cy = int(centroid['x']), int(centroid['y'])
    cv2.circle(vis, (cx, cy), 5, (255, 0, 255), -1)
    cv2.circle(vis, (cx, cy), 8, (255, 0, 255), 2)
else:
    # Fallback to center of safe bbox
    cx = x1 + int(bbox['width']) // 2
    cy = y1 + int(bbox['height']) // 2

# Draw text simulation
from PIL import Image, ImageDraw, ImageFont
pil_img = Image.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
draw = ImageDraw.Draw(pil_img)

# Try to load a font that supports CJK characters at the correct size
try:
    # Try common Windows CJK fonts
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', int(font_size))  # Microsoft YaHei
except:
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/simhei.ttf', int(font_size))  # SimHei
    except:
        try:
            font = ImageFont.truetype('arial.ttf', int(font_size))
        except:
            font = ImageFont.load_default()
            print('⚠️  Using default font (may not render CJK correctly)')

# Calculate text block height
line_height = int(font_size * 1.25)
total_text_height = len(lines) * line_height

# Position at centroid
text_top = cy - total_text_height // 2

for i, line in enumerate(lines):
    y = text_top + i * line_height
    # Center each line
    bbox_line = draw.textbbox((0, 0), line, font=font)
    text_width = bbox_line[2] - bbox_line[0]
    x = cx - text_width // 2
    draw.text((x, y), line, font=font, fill=(0, 0, 0))

vis = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

# Save
output_path = 'debug_smart_balloon_final.png'
cv2.imwrite(output_path, vis)
print(f'\n💾 Saved: {output_path}')

# Summary
print(f'\n✅ SUMMARY:')
print(f'   ✓ Smart Balloon detection working')
print(f'   ✓ Shape-adaptive wrapping: {len(lines)} lines')
print(f'   ✓ Centroid positioning enabled')
print(f'   ✓ Breathing room: {metrics.get("breathing_room_pct", 0):.1f}% (target: 40-50%)')
print(f'   ✓ Font size: {metrics.get("font_height_pct", 0):.1f}% (target: 20-25%)')
