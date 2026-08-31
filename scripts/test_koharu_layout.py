"""
Test script for koharu-layout-rfdetr-seg-2xl-1152 model
on Houmi manga pages.

Detects: text (0), onomatopoeia/SFX (1), bubble (2), panel (3)
Outputs annotated images with bounding boxes + masks.
"""

import os
import sys
import time
import json
import warnings
import numpy as np
from PIL import Image
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────
MODEL_ID = "mayocream/koharu-layout-rfdetr-seg-2xl-1152"
INPUT_DIR = r"C:\Users\dansa\Desktop\Houmi_Balloon_Training_Dataset\01_Full_Pages_With_Boxes"
OUTPUT_DIR = r"C:\Users\dansa\Desktop\Houmi_Balloon_Training_Dataset\koharu_test_output"
NUM_PAGES = 5  # number of pages to test (set to None for all)

CLASS_NAMES = {0: "text", 1: "onomatopoeia", 2: "bubble", 3: "panel"}
CLASS_COLORS = {
    0: (255, 100, 100, 128),   # text - red
    1: (100, 255, 100, 128),   # onomatopoeia/SFX - green
    2: (100, 100, 255, 128),   # bubble - blue
    3: (255, 200, 50, 80),     # panel - yellow (more transparent)
}
CLASS_BOX_COLORS = {
    0: (255, 50, 50),
    1: (50, 200, 50),
    2: (50, 50, 255),
    3: (200, 180, 30),
}
CLASS_THRESHOLDS = {0: 0.25, 1: 0.20, 2: 0.50, 3: 0.50}


def load_koharu_model():
    """Load the koharu layout model from HuggingFace."""
    from huggingface_hub import hf_hub_download
    from rfdetr import RFDETRSeg2XLarge
    from rfdetr.config import PretrainWeightsCompatibilityWarning
    from safetensors.torch import load_file

    # Download weights from HuggingFace
    print("  Downloading weights from HuggingFace...")
    weights_path = hf_hub_download(MODEL_ID, "model.safetensors")
    print(f"  Weights at: {weights_path}")

    # Initialize model without pretrained weights
    class_names_list = ["text", "onomatopoeia", "bubble", "panel"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PretrainWeightsCompatibilityWarning)
        model = RFDETRSeg2XLarge(
            pretrain_weights=None,
            resolution=1152,
            num_select=160,
            num_classes=len(class_names_list),
        )

    # Load safetensors weights
    print("  Loading weights into model...")
    incompatible = model.model.model.load_state_dict(
        load_file(str(weights_path), device="cpu"), strict=True
    )
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise RuntimeError(f"Incompatible weights: {incompatible}")
    model.model.class_names = class_names_list.copy()

    return model


def draw_results(image: Image.Image, detections) -> Image.Image:
    """Draw bounding boxes + semi-transparent masks on the image."""
    from PIL import ImageDraw, ImageFont

    img = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    draw_img = ImageDraw.Draw(img)

    # Draw masks first (bottom layer)
    if detections.mask is not None:
        for i, (mask, class_id) in enumerate(zip(detections.mask, detections.class_id)):
            color = CLASS_COLORS.get(int(class_id), (200, 200, 200, 80))
            # mask is a boolean numpy array
            mask_resized = Image.fromarray(mask.astype(np.uint8) * 255).resize(
                img.size, Image.NEAREST
            )
            mask_np = np.array(mask_resized) > 127
            mask_rgba = np.zeros((*img.size[::-1], 4), dtype=np.uint8)
            mask_rgba[mask_np] = color
            mask_img = Image.fromarray(mask_rgba, "RGBA")
            overlay = Image.alpha_composite(overlay, mask_img)

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Draw bounding boxes + labels on top
    for i in range(len(detections.xyxy)):
        x1, y1, x2, y2 = detections.xyxy[i]
        class_id = int(detections.class_id[i])
        confidence = float(detections.confidence[i])
        color = CLASS_BOX_COLORS.get(class_id, (200, 200, 200))
        label = f"{CLASS_NAMES.get(class_id, '?')} {confidence:.2f}"

        # Draw box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

        # Draw label background
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except:
            font = ImageFont.load_default()
        bbox = font.getbbox(label)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.rectangle([x1, y1 - text_h - 4, x1 + text_w + 4, y1], fill=color)
        draw.text((x1 + 2, y1 - text_h - 3), label, fill=(255, 255, 255), font=font)

    return img.convert("RGB")


def main():
    print("=" * 60)
    print("Koharu Layout RF-DETR Seg 2XL Test")
    print("=" * 60)

    # Load model
    print("\n[1/4] Loading model...")
    t0 = time.time()
    model = load_koharu_model()
    print(f"  Model loaded in {time.time() - t0:.1f}s")

    # Gather input files
    print(f"\n[2/4] Scanning input directory...")
    input_path = Path(INPUT_DIR)
    files = sorted(input_path.glob("*.png"))
    print(f"  Found {len(files)} PNG files")

    if NUM_PAGES is not None:
        files = files[:NUM_PAGES]
        print(f"  Testing on first {NUM_PAGES} pages")

    # Create output dir
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Run predictions
    print(f"\n[3/4] Running predictions...")
    all_results = []

    for idx, filepath in enumerate(files):
        print(f"\n  [{idx+1}/{len(files)}] Processing {filepath.name}...")
        t1 = time.time()

        # Load image
        image = Image.open(filepath).convert("RGB")
        w, h = image.size
        print(f"    Image size: {w}x{h}")

        # Predict
        detections = model.predict(
            image,
            threshold=0.20,
            shape=(1152, 1152),
            include_source_image=False,
        )

        # Apply class-specific thresholds
        keep = np.asarray([
            score >= CLASS_THRESHOLDS[int(class_id)]
            for class_id, score in zip(detections.class_id, detections.confidence)
        ])
        detections = detections[keep]

        elapsed = time.time() - t1
        n_det = len(detections.xyxy)

        # Count per class
        counts = {}
        for cid in detections.class_id:
            name = CLASS_NAMES.get(int(cid), "unknown")
            counts[name] = counts.get(name, 0) + 1

        print(f"    Detections: {n_det} total ({elapsed:.2f}s)")
        for name, cnt in sorted(counts.items()):
            print(f"      {name}: {cnt}")

        # Draw and save
        annotated = draw_results(image, detections)
        out_name = filepath.stem.replace("_annotated", "") + "_koharu.png"
        out_path = os.path.join(OUTPUT_DIR, out_name)
        annotated.save(out_path)
        print(f"    Saved: {out_name}")

        # Collect stats
        page_results = {
            "file": filepath.name,
            "width": w,
            "height": h,
            "num_detections": n_det,
            "per_class": counts,
            "inference_time_s": round(elapsed, 3),
            "detections": []
        }
        for i in range(n_det):
            page_results["detections"].append({
                "class": CLASS_NAMES.get(int(detections.class_id[i]), "unknown"),
                "class_id": int(detections.class_id[i]),
                "confidence": round(float(detections.confidence[i]), 4),
                "bbox": [round(float(v), 1) for v in detections.xyxy[i]],
            })
        all_results.append(page_results)

    # Save summary
    print(f"\n[4/4] Saving summary...")
    summary_path = os.path.join(OUTPUT_DIR, "detection_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  Summary saved to: {summary_path}")

    # Print overall stats
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total_det = sum(r["num_detections"] for r in all_results)
    avg_time = np.mean([r["inference_time_s"] for r in all_results])
    total_counts = {}
    for r in all_results:
        for name, cnt in r["per_class"].items():
            total_counts[name] = total_counts.get(name, 0) + cnt

    print(f"  Pages processed: {len(all_results)}")
    print(f"  Total detections: {total_det}")
    print(f"  Avg inference time: {avg_time:.2f}s")
    print(f"  Per-class totals:")
    for name, cnt in sorted(total_counts.items()):
        print(f"    {name}: {cnt}")
    print(f"\n  Output directory: {OUTPUT_DIR}")
    print("Done!")


if __name__ == "__main__":
    main()
