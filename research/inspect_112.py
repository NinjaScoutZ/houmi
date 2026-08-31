import json
from pathlib import Path

proj_path = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112 [stitched]\project.json")
data = json.load(open(proj_path, encoding="utf-8"))

print(f"Project: {proj_path.parent}")
print(f"Total pages: {len(data.get('pages', []))}")

for page in data.get("pages", []):
    blocks = page.get("text_blocks", [])
    print(f"\n--- Page {page.get('page_number')} ({page.get('image_file', '')}): {len(blocks)} text blocks ---")
    for i, b in enumerate(blocks):
        print(f"  [{i+1}] ID={b.get('id')} Pos=({b.get('x')}, {b.get('y')}, {b.get('width')}x{b.get('height')}) Text: {b.get('text', '')[:30]}")
