"""Deep Analysis and True Geometric Symmetry Reconstruction.

Located and executed exclusively inside e:\\houmi\\research\\
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUT_DIR = RESEARCH_DIR / "true_symmetry_previews"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_image(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image(path: Path, img: np.ndarray) -> None:
    ext = path.suffix or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(str(path))


def main():
    print("=== DEEP GEOMETRIC SYMMETRY ANALYSIS ===")
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]
    blk15 = blocks[2]
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    # Let's crop around Balloon 14 specifically with generous padding
    pad = 80
    c14_x0 = max(0, bx14 - pad)
    c14_y0 = max(0, by14 - pad)
    c14_x1 = min(page_img.shape[1], bx14 + bw14 + pad + 100)
    c14_y1 = min(page_img.shape[0], by14 + bh14 + pad + 150)
    
    crop14 = page_img[c14_y0:c14_y1, c14_x0:c14_x1].copy()
    gray14 = cv2.cvtColor(crop14, cv2.COLOR_BGR2GRAY)
    
    # Save raw crop for inspection
    save_image(OUT_DIR / "crop14_raw.png", crop14)
    print(f"Crop 14 size: {crop14.shape[1]}x{crop14.shape[0]}")
    
    # Let's find the black border of Balloon 14
    # The black border is dark pixels (gray < 80) surrounding the white interior
    black_border = (gray14 < 80).astype(np.uint8) * 255
    white_interior = (gray14 >= 200).astype(np.uint8) * 255
    
    save_image(OUT_DIR / "crop14_black_border.png", black_border)
    save_image(OUT_DIR / "crop14_white_interior.png", white_interior)
    
    print("Exported inspection masks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
