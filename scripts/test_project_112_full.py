"""Test Smart Balloon on all pages of project 112."""
import cv2
import json
from pathlib import Path
import sys
sys.path.insert(0, 'backend')

from app.services.smart_balloon import process_smart_balloon_v15
from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape
from app.services.typesetting.service import segment_text

# Load project from database
import sqlite3
conn = sqlite3.connect('data/houmi.db')
cursor = conn.cursor()
cursor.execute('SELECT id FROM projects WHERE name = "112" AND id NOT LIKE "%stitched%" LIMIT 1')
row = cursor.fetchone()
project_id = row[0] if row else None
conn.close()

if not project_id:
    print('❌ Project 112 not found')
    exit(1)

project_path = Path('data/projects') / project_id
with open(project_path / 'project.json', 'r', encoding='utf-8') as f:
    project = json.load(f)

# Get font
font_path = Path('C:/Windows/Fonts/msyh.ttc')
if not font_path.exists():
    font_path = Path('C:/Windows/Fonts/simhei.ttf')

print('🔍 Scanning Project 112 for text blocks...\n')

stats = {
    'total_blocks': 0,
    'blocks_with_text': 0,
    'smart_balloon_detected': 0,
    'successful_typesetting': 0,
    'archetypes': {},
}

for page_idx, page in enumerate(project.get('pages', []), 1):
    page_file = f"{page_idx:02d}.png"
    img_path = project_path / page_file

    if not img_path.exists():
        continue

    img = cv2.imread(str(img_path))
    if img is None:
        continue

    blocks = page.get('blocks', [])
    print(f'📄 Page {page_idx}: {len(blocks)} blocks')

    for block_idx, block in enumerate(blocks):
        stats['total_blocks'] += 1

        text = block.get('text', '').strip()
        if not text:
            continue

        stats['blocks_with_text'] += 1

        # Get block region
        x, y, w, h = block['x'], block['y'], block['width'], block['height']

        # Detect Smart Balloon
        text_bbox = {'x': x, 'y': y, 'width': w, 'height': h}
        sb_result = process_smart_balloon_v15(img, text_bbox, inset_ratio=0.10)

        if not sb_result or 'error' in sb_result:
            continue

        stats['smart_balloon_detected'] += 1
        archetype = sb_result['archetype']
        stats['archetypes'][archetype] = stats['archetypes'].get(archetype, 0) + 1

        # Try typesetting
        tokens = segment_text(text)
        result = fit_text_to_smart_balloon_shape(
            block=block,
            sb=sb_result,
            tokens=tokens,
            font_path=str(font_path),
        )

        if result:
            stats['successful_typesetting'] += 1
            lines = result.get('lines') or result.get('explicit_lines') or []
            font_size = result.get('font_size')
            safe_h = sb_result['safe_bbox']['height']
            total_h = result.get('total_height', 0)

            print(f'   ✅ Block {block_idx}: {archetype}')
            print(f'      Text: "{text[:30]}{"..." if len(text) > 30 else ""}"')
            print(f'      Font: {font_size}px ({font_size/safe_h*100:.1f}% of height)')
            print(f'      Lines: {len(lines)}, Fill: {total_h/safe_h*100:.1f}%, Breathing: {100-total_h/safe_h*100:.1f}%')

print(f'\n📊 Summary:')
print(f'   Total blocks: {stats["total_blocks"]}')
print(f'   Blocks with text: {stats["blocks_with_text"]}')
print(f'   Smart Balloon detected: {stats["smart_balloon_detected"]}')
print(f'   Successful typesetting: {stats["successful_typesetting"]}')
print(f'\n🎨 Archetypes:')
for arch, count in stats['archetypes'].items():
    print(f'   {arch}: {count}')
