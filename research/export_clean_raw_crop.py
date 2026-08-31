"""Export clean, raw original manga crop of the Sample 14 & 15 scene without any overlays, boxes, or effects.

Located and executed exclusively inside e:\\houmi\\research\\
"""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUT_FILE = RESEARCH_DIR / "raw_sample_14_15_clean.png"


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
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    if page_img is None:
        print("Error: Could not load 03.jpg")
        return 1

    # Crop the exact region containing both Balloon 14 and 15 with full context
    # Balloon 14: y ~ 5744, Balloon 15: y ~ 6271, bottom character ~ 6700
    y0 = 5600
    y1 = 6750
    x0 = 0
    x1 = page_img.shape[1]

    raw_crop = page_img[y0:y1, x0:x1].copy()
    save_image(OUT_FILE, raw_crop)
    print(f"Clean raw crop saved -> {OUT_FILE} (size: {raw_crop.shape[1]}x{raw_crop.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
