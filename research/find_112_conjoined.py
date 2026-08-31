import json
from pathlib import Path

proj_path = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112\project.json")
data = json.load(open(proj_path, encoding="utf-8"))

print(f"Total pages: {len(data.get('pages', []))}")

conjoined_candidates = []

for page in data.get("pages", []):
    pnum = page.get("page_number")
    img_file = page.get("image_file", f"{pnum:02d}.jpg")
    blocks = page.get("text_blocks", [])
    
    # Check for adjacent blocks that are vertically/horizontally close
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            b1 = blocks[i]
            b2 = blocks[j]
            x1, y1, w1, h1 = b1["x"], b1["y"], b1["width"], b1["height"]
            x2, y2, w2, h2 = b2["x"], b2["y"], b2["width"], b2["height"]
            
            c1 = (x1 + w1/2, y1 + h1/2)
            c2 = (x2 + w2/2, y2 + h2/2)
            dist = ((c1[0]-c2[0])**2 + (c1[1]-c2[1])**2)**0.5
            
            # If distance between centers is within 500px and bounding boxes are nearby
            if dist < 650 and abs(c1[1] - c2[1]) < 500:
                conjoined_candidates.append({
                    "page": pnum,
                    "img": img_file,
                    "pair": (i+1, j+1),
                    "dist": dist,
                    "b1": (x1, y1, w1, h1, b1.get("text", "")[:20]),
                    "b2": (x2, y2, w2, h2, b2.get("text", "")[:20])
                })

print(f"Found {len(conjoined_candidates)} conjoined candidate pairs:")
for c in conjoined_candidates:
    print(f"Page {c['page']} ({c['img']}) Pair #{c['pair'][0]} & #{c['pair'][1]} (Dist={c['dist']:.1f}):")
    print(f"   B1: Pos=({c['b1'][0]:.0f}, {c['b1'][1]:.0f}, {c['b1'][2]:.0f}x{c['b1'][3]:.0f}) Text='{c['b1'][4]}'")
    print(f"   B2: Pos=({c['b2'][0]:.0f}, {c['b2'][1]:.0f}, {c['b2'][2]:.0f}x{c['b2'][3]:.0f}) Text='{c['b2'][4]}'")
