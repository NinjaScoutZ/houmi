"""
Generate 30 real balloon preview images using Smart Balloon V16 with actual project data.

Uses real images from database projects and applies both V15 and V16 smart balloon detection,
creating side-by-side comparison visualizations.
"""

import sys
sys.path.insert(0, '.')

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
import json
import time

from app.database import SessionLocal
from app.models import Project, Page, TextBlock
from app.services.smart_balloon import process_smart_balloon_v15
from app.services.smart_balloon_adaptive import process_smart_balloon_v16_adaptive
from app.config import get_smart_balloon_adaptive_enabled

def load_real_project_data(db, limit_balloons: int = 30) -> List[Dict[str, Any]]:
    """Load real project data with images and balloons."""
    print("🔍 Scanning projects for balloons with images...")

    projects = db.query(Project).all()
    balloon_data = []

    for proj in projects:
        proj_dir = Path(f'../data/projects/{proj.id}')
        if not proj_dir.exists():
            continue

        pages = db.query(Page).filter(Page.project_id == proj.id).all()
        for page in pages:
            page_dir = proj_dir / str(page.id)
            if not page_dir.exists():
                continue

            # Find source image
            source_files = list(page_dir.glob('source.*'))
            if not source_files:
                continue

            blocks = db.query(TextBlock).filter(TextBlock.page_id == page.id).all()
            for block in blocks:
                balloon_data.append({
                    'project_name': proj.name,
                    'project_id': proj.id,
                    'page_id': page.id,
                    'page_number': page.page_number,
                    'block_id': block.id,
                    'bbox': (block.x, block.y, block.width, block.height),
                    'image_path': source_files[0]
                })

                if len(balloon_data) >= limit_balloons:
                    return balloon_data

    return balloon_data

def process_balloon(image_path: Path, bbox: tuple, idx: int) -> Dict[str, Any]:
    """Process one balloon with both V15 and V16."""
    x, y, w, h = bbox

    # Ensure integers
    x, y, w, h = int(x), int(y), int(w), int(h)

    # Load image
    img = cv2.imread(str(image_path))
    if img is None:
        return None

    h_img, w_img = img.shape[:2]

    # Validate bbox
    if y + h > h_img or x + w > w_img or x < 0 or y < 0 or w <= 0 or h <= 0:
        return None

    # Extract crop
    crop = img[y:y+h, x:x+w].copy()

    # Create text_bbox dict for V15/V16 (they expect full image + text_bbox)
    text_bbox = {"x": x, "y": y, "width": w, "height": h}

    # Run V15
    start_v15 = time.time()
    result_v15 = process_smart_balloon_v15(img, text_bbox)
    time_v15 = (time.time() - start_v15) * 1000

    # Run V16
    start_v16 = time.time()
    result_v16 = process_smart_balloon_v16_adaptive(img, text_bbox)
    time_v16 = (time.time() - start_v16) * 1000

    return {
        'idx': idx,
        'bbox': bbox,
        'crop': crop,
        'v15_success': result_v15 is not None and result_v15.get('success', False),
        'v16_success': result_v16 is not None and result_v16.get('success', False) and result_v16.get('version') == 'v16_adaptive',
        'v15_time': round(time_v15, 2),
        'v16_time': round(time_v16, 2),
        'result_v15': result_v15,
        'result_v16': result_v16,
    }

def create_visualization(data: Dict[str, Any], balloon_info: Dict[str, Any]) -> np.ndarray:
    """Create side-by-side comparison visualization."""
    crop = data['crop']
    h, w = crop.shape[:2]

    # Create canvas
    canvas = np.full((h + 80, w * 2 + 40, 3), 245, dtype=np.uint8)

    # V15 side (left)
    left_img = crop.copy()
    if data['v15_success'] and data['result_v15'] and 'contour' in data['result_v15']:
        contour = data['result_v15']['contour']
        if contour is not None and len(contour) > 0:
            cv2.drawContours(left_img, [contour], -1, (0, 255, 0), 2)
    canvas[60:60+h, 10:10+w] = left_img

    # V16 side (right)
    right_img = crop.copy()
    if data['v16_success'] and data['result_v16'] and 'contour' in data['result_v16']:
        contour = data['result_v16']['contour']
        if contour is not None and len(contour) > 0:
            cv2.drawContours(right_img, [contour], -1, (0, 0, 255), 2)

        # Show adaptive params
        if 'bg_mean' in data['result_v16']:
            bg_mean = data['result_v16']['bg_mean']
            white_thresh = data['result_v16'].get('white_threshold', 255)
            cv2.putText(right_img, f"bg={int(bg_mean)}, th={int(white_thresh)}",
                       (5, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

    canvas[60:60+h, w+30:w+30+w] = right_img

    # Labels
    cv2.putText(canvas, "V15 Baseline", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2)
    status_v15 = "Success" if data['v15_success'] else "Failed"
    cv2.putText(canvas, status_v15, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
               (0, 255, 0) if data['v15_success'] else (0, 0, 255), 1)

    cv2.putText(canvas, "V16 Adaptive", (w+30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 200), 2)
    status_v16 = "Success" if data['v16_success'] else "Failed"
    cv2.putText(canvas, status_v16, (w+30, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
               (0, 0, 255) if data['v16_success'] else (128, 128, 128), 1)

    # Bottom info
    info_text = f"Project: {balloon_info['project_name']} | Page {balloon_info['page_number']}"
    cv2.putText(canvas, info_text, (10, h+75), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)

    return canvas

def main():
    print("🎨 Smart Balloon V16 Real Data Preview Generation")
    print("=" * 80)

    db = SessionLocal()
    output_dir = Path("../test_outputs/smart_balloon_real_previews")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Load real balloon data
        balloon_data = load_real_project_data(db, limit_balloons=30)
        print(f"✅ Found {len(balloon_data)} balloons with images")
        print()

        if not balloon_data:
            print("❌ No balloons with images found!")
            return

        results = []
        successful_vis = 0

        print(f"🔬 Processing {len(balloon_data)} balloons...")
        print()

        for i, balloon_info in enumerate(balloon_data, 1):
            print(f"   [{i:2d}/{len(balloon_data)}] ", end="")

            result = process_balloon(
                balloon_info['image_path'],
                balloon_info['bbox'],
                i
            )

            if result is None:
                print("⚠️  Skipped (invalid image/bbox)")
                continue

            # Create visualization
            vis = create_visualization(result, balloon_info)

            # Save
            filename = f"balloon_{i:03d}_comparison.png"
            output_path = output_dir / filename
            cv2.imwrite(str(output_path), vis)

            v15_status = "✅" if result['v15_success'] else "❌"
            v16_status = "✅" if result['v16_success'] else "❌"
            print(f"{v15_status} V15, {v16_status} V16 | {result['v15_time']:.1f}ms, {result['v16_time']:.1f}ms")

            results.append({
                'balloon_id': i,
                'project': balloon_info['project_name'],
                'page': balloon_info['page_number'],
                'v15_success': result['v15_success'],
                'v16_success': result['v16_success'],
                'v15_time_ms': result['v15_time'],
                'v16_time_ms': result['v16_time'],
                'filename': filename
            })

            successful_vis += 1

        # Save summary
        summary = {
            'total_balloons': len(balloon_data),
            'processed': len(results),
            'v15_success_count': sum(1 for r in results if r['v15_success']),
            'v16_success_count': sum(1 for r in results if r['v16_success']),
            'avg_v15_time_ms': round(np.mean([r['v15_time_ms'] for r in results]), 2),
            'avg_v16_time_ms': round(np.mean([r['v16_time_ms'] for r in results]), 2),
            'results': results
        }

        summary_path = output_dir / 'test_summary.json'
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print()
        print("=" * 80)
        print("✅ PREVIEW GENERATION COMPLETE!")
        print("=" * 80)
        print(f"Output folder: {output_dir.absolute()}")
        print(f"Files generated: {successful_vis} comparison images")
        print()
        print(f"Summary:")
        print(f"  Balloons processed: {len(results)}")
        print(f"  V15 Success: {summary['v15_success_count']}/{len(results)}")
        print(f"  V16 Success: {summary['v16_success_count']}/{len(results)}")
        print(f"  Avg V15 Time: {summary['avg_v15_time_ms']}ms")
        print(f"  Avg V16 Time: {summary['avg_v16_time_ms']}ms")
        print()
        print("✅ Done!")

    finally:
        db.close()

if __name__ == "__main__":
    main()
