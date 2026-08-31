#!/usr/bin/env python3
"""Test Smart Balloon detection and typesetting on Project 112"""

import json
import sys
from pathlib import Path
import cv2
import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.services.smart_balloon import process_smart_balloon_v15
from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape

PROJECT_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112 [stitched]")
PROJECT_FILE = PROJECT_DIR / "project.json"

def main():
    print("=== Testing Smart Balloon on Project 112 ===\n")

    # Load project
    with open(PROJECT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    # Find the page with the image we saw (wavy balloon with Chinese text)
    # Based on the research files, let's look at page 4 (index 3)
    page_idx = 3  # Page 4
    page = data["pages"][page_idx]

    print(f"Page {page_idx + 1}: {page.get('image_file', 'N/A')}")
    print(f"Blocks: {len(page.get('text_blocks', []))}\n")

    # Load page image - try direct file name
    img_filename = f"{page_idx + 1:02d}.png"
    img_file = PROJECT_DIR / img_filename
    if not img_file.exists():
        print(f"❌ Image not found: {img_file}")
        return

    img = cv2.imread(str(img_file))
    if img is None:
        print(f"❌ Failed to load image: {img_file}")
        return

    print(f"✅ Loaded image: {img.shape[1]}×{img.shape[0]}\n")

    # Test first 3 blocks
    for i, block in enumerate(page["text_blocks"][:3]):
        print(f"\n{'='*60}")
        print(f"Block {i+1}: ID={block['id'][:8]}...")
        print(f"Position: ({block['x']:.0f}, {block['y']:.0f}, {block['width']:.0f}×{block['height']:.0f})")
        print(f"Text: {block.get('text', '')[:50]}")

        # Run Smart Balloon detection
        text_bbox = {
            "x": block["x"],
            "y": block["y"],
            "width": block["width"],
            "height": block["height"],
        }

        sb_result = process_smart_balloon_v15(img, text_bbox, inset_ratio=0.10)

        print(f"\n📊 Smart Balloon Result:")
        print(f"  Success: {sb_result['success']}")
        print(f"  Method: {sb_result['method']}")
        print(f"  Archetype: {sb_result['archetype']}")

        if sb_result["success"]:
            safe_bbox = sb_result["safe_bbox"]
            print(f"  Safe bbox: ({safe_bbox['x']:.0f}, {safe_bbox['y']:.0f}, {safe_bbox['width']:.0f}×{safe_bbox['height']:.0f})")
            print(f"  Centroid: ({sb_result['center']['x']:.0f}, {sb_result['center']['y']:.0f})")

            # Check row width constraints
            rwc = sb_result.get("row_width_constraints", {})
            if rwc.get("enabled"):
                widths = rwc.get("row_widths", [])
                if widths:
                    import numpy as np
                    print(f"  Row constraints: ✅ enabled")
                    print(f"    Min width: {min(widths):.1f}px")
                    print(f"    Max width: {max(widths):.1f}px")
                    print(f"    Avg width: {np.mean(widths):.1f}px")
            else:
                print(f"  Row constraints: ❌ disabled")

            # Try typesetting with Smart Balloon
            if block.get("text"):
                print(f"\n🔤 Testing Typesetting:")
                font_path = Path("C:/Windows/Fonts/msyh.ttc")  # Microsoft YaHei for Chinese
                if not font_path.exists():
                    font_path = Path("C:/Windows/Fonts/simhei.ttf")  # SimHei fallback

                if font_path.exists():
                    try:
                        result = fit_text_to_smart_balloon_shape(
                            block=block,
                            sb=sb_result,
                            tokens=[block["text"]],
                            font_path=str(font_path),
                            target_lang="zh",
                        )

                        print(f"  Fitted font size: {result.get('font_size', 'N/A')}px")
                        lines = result.get("lines", [])
                        print(f"  Lines: {len(lines)}")
                        for j, line in enumerate(lines[:3]):
                            print(f"    L{j+1}: {line[:40]}")
                    except Exception as e:
                        print(f"  ❌ Typesetting error: {e}")
                else:
                    print(f"  ⚠️  No Chinese font found, skipping typesetting test")
        else:
            print(f"  ⚠️  Fallback reason: {sb_result.get('metadata', {}).get('fallback_reason', 'unknown')}")

if __name__ == "__main__":
    main()
