"""Build a visual audit of OCR-gated UNet masks for the Color Hard corpus."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from app.services.text_mask import detect_text_lines, generate_manga_unet_text_mask
from app.services.inpainter import _get_lama


SOURCE = Path(r"C:\Users\dansa\Desktop\Chapter40_Balloons\Color Hard")
OUTPUT = Path(
    r"C:\Users\dansa\.codex\visualizations\2026\08\06"
    r"\019fd8b9-c677-7b21-b351-54d23a09c1e2"
)


def proposal_gate(shape: tuple[int, int], polygons: list[np.ndarray], padding: int = 5) -> np.ndarray:
    gate = np.zeros(shape, dtype=np.uint8)
    for polygon in polygons:
        cv2.fillPoly(gate, [polygon.astype(np.int32)], 255)
    if polygons and padding > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (padding * 2 + 1, padding * 2 + 1))
        gate = cv2.dilate(gate, kernel, iterations=1)
    return gate


def overlay(image: np.ndarray, mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    result = image.copy()
    selected = mask > 0
    blended = image.astype(np.float32) * 0.35 + np.asarray(color, dtype=np.float32) * 0.65
    result[selected] = np.clip(blended[selected], 0, 255).astype(np.uint8)
    return result


def fit_panel(image: np.ndarray, width: int = 320, height: int = 300) -> np.ndarray:
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    panel = np.full((height, width, 3), 245, dtype=np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    panel[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return panel


def title(panel: np.ndarray, label: str) -> np.ndarray:
    bar = np.full((34, panel.shape[1], 3), 24, dtype=np.uint8)
    cv2.putText(bar, label, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (245, 245, 245), 1, cv2.LINE_AA)
    return np.vstack([bar, panel])


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows: list[np.ndarray] = []
    metrics: list[dict[str, object]] = []
    lama = _get_lama()

    for path in sorted(SOURCE.glob("*.png")):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue

        current = generate_manga_unet_text_mask(image, dilation_kernel=2, threshold=0.35)
        sensitive = generate_manga_unet_text_mask(image, dilation_kernel=2, threshold=0.25)
        current = current if current is not None else np.zeros(image.shape[:2], dtype=np.uint8)
        sensitive = sensitive if sensitive is not None else np.zeros(image.shape[:2], dtype=np.uint8)

        detections = detect_text_lines(image)
        gate = proposal_gate(image.shape[:2], [item.polygon for item in detections], padding=5)
        proposed = cv2.bitwise_and(sensitive, gate)

        proposal_view = image.copy()
        for detection in detections:
            cv2.polylines(proposal_view, [detection.polygon.astype(np.int32)], True, (30, 210, 255), 2, cv2.LINE_AA)

        current_view = overlay(image, current, (30, 30, 235))
        proposed_view = overlay(image, proposed, (40, 190, 40))
        clean_preview = cv2.inpaint(image, proposed, 3, cv2.INPAINT_TELEA)
        lama_preview = lama.inpaint(image, proposed) if lama is not None else clean_preview

        panels = [
            title(fit_panel(image), "Original"),
            title(fit_panel(current_view), "Current UNet 0.35"),
            title(fit_panel(proposal_view), f"Paddle proposals ({len(detections)})"),
            title(fit_panel(proposed_view), "Dual-Branch gated 0.25"),
            title(fit_panel(clean_preview), "Telea preview"),
            title(fit_panel(lama_preview), "LaMa preview"),
        ]
        label = np.full((28, sum(panel.shape[1] for panel in panels), 3), 8, dtype=np.uint8)
        cv2.putText(label, path.name, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)
        rows.append(np.vstack([label, np.hstack(panels)]))

        edge_band = np.zeros(image.shape[:2], dtype=np.uint8)
        edge_band[:5, :] = edge_band[-5:, :] = 255
        edge_band[:, :5] = edge_band[:, -5:] = 255
        metrics.append(
            {
                "file": path.name,
                "proposal_count": len(detections),
                "proposal_confidences": [item.confidence for item in detections],
                "current_coverage": round(float(np.count_nonzero(current)) / current.size, 6),
                "proposed_coverage": round(float(np.count_nonzero(proposed)) / proposed.size, 6),
                "current_edge_pixels": int(np.count_nonzero(cv2.bitwise_and(current, edge_band))),
                "proposed_edge_pixels": int(np.count_nonzero(cv2.bitwise_and(proposed, edge_band))),
            }
        )

    board_path = OUTPUT / "color-hard-dual-branch-comparison.jpg"
    metrics_path = OUTPUT / "color-hard-dual-branch-metrics.json"
    cv2.imwrite(str(board_path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(board_path)
    print(metrics_path)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
