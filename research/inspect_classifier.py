import json
import cv2
import numpy as np
from pathlib import Path
from smart_balloon_v14_universal_pipeline import load_image, classify_balloon_shape

proj_path = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112\project.json")
proj = json.load(open(proj_path, encoding="utf-8"))

test_specs = [
    {"page_num": 10, "b": (0, 1), "name": "page10_spiky"},
    {"page_num": 11, "b": (0, 1), "name": "page11_rect"},
    {"page_num": 15, "b": (0, 1), "name": "page15_concave"},
    {"page_num": 20, "b": (0, 1), "name": "page20_angular"},
]

for spec in test_specs:
    p_num = spec["page_num"]
    p_data = [p for p in proj["pages"] if p["page_number"] == p_num][0]
    img = load_image(Path(rf"E:\Chapter Download\Kuaikanmanhua\ดาว\112\{p_num:02d}.jpg"))
    b1 = p_data["text_blocks"][spec["b"][0]]
    b2 = p_data["text_blocks"][spec["b"][1]]
    
    x1, y1, w1, h1 = int(b1["x"]), int(b1["y"]), int(b1["width"]), int(b1["height"])
    x2, y2, w2, h2 = int(b2["x"]), int(b2["y"]), int(b2["width"]), int(b2["height"])
    
    pad = 120
    min_x, min_y = max(0, min(x1, x2) - pad), max(0, min(y1, y2) - pad)
    max_x, max_y = min(img.shape[1], max(x1+w1, x2+w2) + pad), min(img.shape[0], max(y1+h1, y2+h2) + pad)
    
    crop = img[min_y:max_y, min_x:max_x]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # 1. White interior
    # Note: On page 10, the spiky aura has gradient grey spikes (150-240)
    pure_white = (gray >= 180).astype(np.uint8) * 255
    c1 = (int(x1 - min_x + w1/2), int(y1 - min_y + h1/2))
    seed = np.zeros((crop.shape[0]+2, crop.shape[1]+2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, c1, 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    mask = seed[1:-1, 1:-1] * 255
    
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if cnts:
        cnt = max(cnts, key=cv2.contourArea)
        b_type, meta = classify_balloon_shape(cnt)
        print(f"[{spec['name']}]: Classified as {b_type}")
        print(f"   rect_ratio = {meta['rect_ratio']:.3f}")
        print(f"   roughness  = {meta['roughness']:.3f}")
        print(f"   poly_pts   = {meta['poly_pts']}")
