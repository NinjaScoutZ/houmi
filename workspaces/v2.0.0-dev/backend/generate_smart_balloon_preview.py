"""
Smart Balloon V16 Visual Testing & Preview Generation
Generates side-by-side comparison images of V15 vs V16 balloon detection
"""
import sys
import os
import json
import cv2
import numpy as np
from pathlib import Path

sys.path.insert(0, '.')

from app.database import SessionLocal
from app.models import Project, Page, TextBlock
from app.services.smart_balloon import process_smart_balloon_v15

print("🎨 Smart Balloon V16 Visual Testing & Preview Generation")
print("=" * 80)

# Create output folder
output_dir = Path("../test_outputs/smart_balloon_v16_preview")
output_dir.mkdir(parents=True, exist_ok=True)

db = SessionLocal()
try:
    # Find a project with good balloons - try "ก๊อบลิน" (10 balloons)
    project = db.query(Project).filter(Project.name == 'ก๊อบลิน').first()

    if not project:
        print('⚠️  ก๊อบลิน project not found, trying others...')
        # Try other projects
        for name in ['Test', '138', 'Chapter 49 (제49화)', '11', '15']:
            project = db.query(Project).filter(Project.name == name).first()
            if project:
                break

    if not project:
        print('❌ No suitable project found')
        sys.exit(1)

    print(f"✅ Using project: \"{project.name}\"")
    print(f"   Project ID: {project.id}")

    # Get first page with balloons
    pages = db.query(Page).filter(Page.project_id == project.id).order_by(Page.page_number).all()

    test_page = None
    test_blocks = []
    for page in pages[:3]:  # Check first 3 pages
        blocks = db.query(TextBlock).filter(TextBlock.page_id == page.id).all()
        if len(blocks) >= 3:  # Need at least 3 balloons
            test_page = page
            test_blocks = blocks
            break

    if not test_page or not test_blocks:
        print('❌ No pages with enough balloons found')
        sys.exit(1)

    print(f"\n📄 Testing with Page {test_page.page_number}")
    print(f"   Balloons available: {len(test_blocks)}")

    # Create a realistic test image that matches actual balloon coordinates
    # Balloons are at y ~3897, 6712, 7363, so need image height > 8000
    print("   Creating synthetic manga page (webtoon format)...")
    base_image = np.full((10000, 800, 3), 240, dtype=np.uint8)  # Webtoon format

    # Add some texture/noise for realism
    noise = np.random.normal(0, 8, base_image.shape).astype(np.int16)
    base_image = np.clip(base_image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Add some manga panel lines
    for y in range(0, 10000, 2000):
        cv2.line(base_image, (0, y), (800, y), (100, 100, 100), 2)

    # Draw actual balloons with proper manga styling
    for idx, block in enumerate(test_blocks[:5], 1):
        x, y, w_b, h_b = int(block.x), int(block.y), int(block.width), int(block.height)
        if y + h_b <= 10000 and x + w_b <= 800:
            # Draw white balloon background
            cv2.ellipse(base_image, (x + w_b//2, y + h_b//2), (w_b//2 - 10, h_b//2 - 10),
                       0, 0, 360, (255, 255, 255), -1)
            # Draw balloon border (manga style)
            cv2.ellipse(base_image, (x + w_b//2, y + h_b//2), (w_b//2 - 10, h_b//2 - 10),
                       0, 0, 360, (0, 0, 0), 3)
            # Draw speech tail (simple triangle)
            if idx % 2 == 0:  # Alternate tail positions
                pts = np.array([[x + w_b//2, y + h_b],
                               [x + w_b//2 - 20, y + h_b + 40],
                               [x + w_b//2 + 20, y + h_b + 30]], np.int32)
            else:
                pts = np.array([[x + 20, y + h_b//2],
                               [x - 30, y + h_b//2 - 20],
                               [x - 20, y + h_b//2 + 20]], np.int32)
            cv2.fillPoly(base_image, [pts], (255, 255, 255))
            cv2.polylines(base_image, [pts], True, (0, 0, 0), 3)

    h, w = base_image.shape[:2]
    print(f"   Image size: {w}x{h}px")

    # Test first 5 balloons only
    test_blocks = test_blocks[:5]

    print(f"\n🔬 Testing {len(test_blocks)} balloons...\n")

    results = []
    valid_results = []

    for idx, block in enumerate(test_blocks, 1):
        text_bbox = {
            'x': float(block.x),
            'y': float(block.y),
            'width': float(block.width),
            'height': float(block.height),
            'balloon_type': 'speech'
        }

        # Check if bbox is within image bounds
        if (text_bbox['y'] + text_bbox['height'] > h or
            text_bbox['x'] + text_bbox['width'] > w or
            text_bbox['y'] < 0 or text_bbox['x'] < 0):
            print(f"   [{idx}] ⚠️  Balloon outside image bounds, skipping")
            continue

        # Test V15 (baseline)
        result_v15 = process_smart_balloon_v15(
            base_image, text_bbox,
            use_adaptive=False
        )

        # Test V16 (adaptive)
        result_v16 = process_smart_balloon_v15(
            base_image, text_bbox,
            use_adaptive=True
        )

        v15_success = result_v15.get('success', False)
        v16_success = result_v16.get('success', False)
        v16_version = result_v16.get('version', 'unknown')

        status = "✅" if v16_success else "❌"
        print(f"   [{idx}] {status} V15: {v15_success}, V16: {v16_success} ({v16_version})")

        if 'bg_stats' in result_v16:
            stats = result_v16['bg_stats']
            print(f"        bg_mean={stats.get('bg_mean', 0):.1f}, white_thresh={stats.get('white_thresh', 0)}")

        result_data = {
            'balloon_id': idx,
            'bbox': text_bbox,
            'v15_success': v15_success,
            'v16_success': v16_success,
            'v16_version': v16_version,
            'v15_result': result_v15,
            'v16_result': result_v16
        }

        results.append(result_data)

        if v16_success or v15_success:
            valid_results.append(result_data)

    if not valid_results:
        print("\n⚠️  No successful balloon detections to visualize")
        print("   This is expected with synthetic images")
        sys.exit(0)

    print(f"\n🎨 Generating visual comparison images for {len(valid_results)} balloons...")

    # Generate comparison images for each successful balloon
    for result in valid_results:
        balloon_id = result['balloon_id']
        bbox = result['bbox']

        # Extract balloon region with padding
        x, y, w_box, h_box = int(bbox['x']), int(bbox['y']), int(bbox['width']), int(bbox['height'])

        pad = 50
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + w_box + pad)
        y2 = min(h, y + h_box + pad)

        crop = base_image[y1:y2, x1:x2].copy()

        # Draw bbox
        cv2.rectangle(crop, (x - x1, y - y1), (x + w_box - x1, y + h_box - y1), (255, 0, 0), 2)

        # Draw V15 result
        crop_v15 = crop.copy()
        if result['v15_success'] and 'contour' in result['v15_result']:
            v15_contour = result['v15_result']['contour']
            if isinstance(v15_contour, list) and len(v15_contour) > 0:
                v15_contour = np.array(v15_contour, dtype=np.int32)
                v15_contour[:, 0] -= x1
                v15_contour[:, 1] -= y1
                cv2.drawContours(crop_v15, [v15_contour], -1, (0, 255, 0), 2)

        # Draw V16 result
        crop_v16 = crop.copy()
        if result['v16_success'] and 'contour' in result['v16_result']:
            v16_contour = result['v16_result']['contour']
            if isinstance(v16_contour, list) and len(v16_contour) > 0:
                v16_contour = np.array(v16_contour, dtype=np.int32)
                v16_contour[:, 0] -= x1
                v16_contour[:, 1] -= y1
                cv2.drawContours(crop_v16, [v16_contour], -1, (0, 0, 255), 2)

        # Create side-by-side comparison
        comparison = np.hstack([crop_v15, crop_v16])

        # Add labels
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(comparison, "V15 Baseline", (10, 30), font, 0.8, (0, 255, 0), 2)
        cv2.putText(comparison, "V16 Adaptive", (crop.shape[1] + 10, 30), font, 0.8, (0, 0, 255), 2)

        # Add status
        v15_status = "Success" if result['v15_success'] else "Failed"
        v16_status = "Success" if result['v16_success'] else "Failed"
        cv2.putText(comparison, v15_status, (10, 60), font, 0.6, (0, 255, 0), 2)
        cv2.putText(comparison, v16_status, (crop.shape[1] + 10, 60), font, 0.6, (0, 0, 255), 2)

        output_comp = output_dir / f"balloon_{balloon_id:02d}_comparison.png"
        cv2.imwrite(str(output_comp), comparison)

        print(f"   ✅ Saved: balloon_{balloon_id:02d}_comparison.png")

    # Generate summary
    print(f"\n📊 Generating summary report...")

    summary = {
        'project_name': project.name,
        'page_number': test_page.page_number,
        'total_tested': len(results),
        'v15_success': sum(1 for r in results if r['v15_success']),
        'v16_success': sum(1 for r in results if r['v16_success']),
        'visualizations_generated': len(valid_results)
    }

    summary_path = output_dir / "test_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n" + "=" * 80)
    print(f"✅ PREVIEW GENERATION COMPLETE!")
    print(f"=" * 80)
    print(f"Output folder: {output_dir.absolute()}")
    print(f"Files generated:")
    generated_images = list(output_dir.glob('*_comparison.png'))
    print(f"  - {len(generated_images)} comparison images")
    print(f"  - test_summary.json")
    print(f"\nSummary:")
    print(f"  Balloons tested: {summary['total_tested']}")
    print(f"  V15 Success: {summary['v15_success']}/{summary['total_tested']}")
    print(f"  V16 Success: {summary['v16_success']}/{summary['total_tested']}")
    print(f"  Visualizations: {summary['visualizations_generated']}")

finally:
    db.close()

print("\n✅ Done!")
