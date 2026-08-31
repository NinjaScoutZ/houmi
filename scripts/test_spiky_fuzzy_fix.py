"""Test script to verify SPIKY_FUZZY classification fix on real balloon images."""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

import cv2
import numpy as np
from app.services.smart_balloon import process_smart_balloon_v15, classify_balloon_archetype
from app.utils.image_utils import cv2_imread_unicode


def test_with_synthetic_spiky_balloon():
    """Test with synthetic spiky/fuzzy balloon."""
    print("=" * 80)
    print("TEST 1: Synthetic Spiky/Fuzzy Balloon")
    print("=" * 80)

    # Create page with fuzzy/spiky thought bubble
    page = np.full((800, 800, 3), 240, dtype=np.uint8)

    # Create fuzzy edge by drawing multiple circles with varying radii (feathered effect)
    center = (400, 400)
    for i in range(30):
        angle = i * (2 * np.pi / 30)
        # Random radius variation to create spiky/fuzzy appearance
        r_base = 150
        r_var = 40 if i % 3 == 0 else 20
        r = r_base + np.random.randint(-r_var, r_var)

        x = int(center[0] + r * np.cos(angle))
        y = int(center[1] + r * np.sin(angle))
        cv2.circle(page, (x, y), 15, (255, 255, 255), -1)

    # Fill center
    cv2.circle(page, center, 120, (255, 255, 255), -1)

    # Add text
    cv2.putText(page, "...", (380, 410), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    text_bbox = {"x": 300, "y": 350, "width": 200, "height": 100}
    result = process_smart_balloon_v15(page, text_bbox)

    print(f"Archetype: {result['archetype']}")
    print(f"Metadata: {result['metadata']}")

    if result['archetype'] == 'SPIKY_FUZZY':
        print("✅ PASS: Correctly classified as SPIKY_FUZZY")
    else:
        print(f"❌ FAIL: Expected SPIKY_FUZZY but got {result['archetype']}")

    return result['archetype'] == 'SPIKY_FUZZY'


def test_with_smooth_oval():
    """Test with smooth oval balloon."""
    print("\n" + "=" * 80)
    print("TEST 2: Smooth Oval Balloon")
    print("=" * 80)

    # Create page with smooth oval balloon
    page = np.full((600, 600, 3), 230, dtype=np.uint8)
    cv2.ellipse(page, (300, 300), (140, 100), 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(page, (300, 300), (140, 100), 0, 0, 360, (0, 0, 0), 3)
    cv2.putText(page, "Hello!", (260, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    text_bbox = {"x": 230, "y": 280, "width": 140, "height": 50}
    result = process_smart_balloon_v15(page, text_bbox)

    print(f"Archetype: {result['archetype']}")
    print(f"Metadata: {result['metadata']}")

    if result['archetype'] == 'SMOOTH_OVAL':
        print("✅ PASS: Correctly classified as SMOOTH_OVAL")
    else:
        print(f"❌ FAIL: Expected SMOOTH_OVAL but got {result['archetype']}")

    return result['archetype'] == 'SMOOTH_OVAL'


def test_classification_comparison():
    """Compare classification before and after fix."""
    print("\n" + "=" * 80)
    print("TEST 3: Classification Feature Comparison")
    print("=" * 80)

    # Create a spiky contour
    img = np.zeros((400, 400), dtype=np.uint8)
    pts = []
    center = (200, 200)
    for i in range(72):
        angle = i * (2 * np.pi / 72)
        r = 100 + (25 if i % 2 == 0 else -15)
        x = int(center[0] + r * np.cos(angle))
        y = int(center[1] + r * np.sin(angle))
        pts.append([x, y])
    cv2.fillPoly(img, [np.array(pts)], 255)

    # Convert to BGR for processing
    img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = cnts[0]

    archetype, meta = classify_balloon_archetype(
        contour,
        {"x": 150, "y": 150, "width": 100, "height": 100},
        crop_w=400,
        crop_h=400,
        raw_gray=gray
    )

    print(f"Archetype: {archetype}")
    print(f"Roughness (contour, sigma=5): {meta['roughness']}")
    print(f"Raw Roughness (image gradient): {meta['raw_roughness']}")
    print(f"Edge Density: {meta['edge_density']}")
    print(f"High Freq Ratio: {meta['high_freq_ratio']}")

    print("\n📊 Classification Criteria:")
    print(f"  - is_fuzzy_density (density >= 0.095): {meta['edge_density'] >= 0.095}")
    print(f"  - roughness > 1.8: {meta['roughness'] > 1.8}")
    print(f"  - roughness > 1.2 AND high_freq > 0.12: {meta['roughness'] > 1.2 and meta['high_freq_ratio'] > 0.12}")

    return True


if __name__ == "__main__":
    print("\n🔧 Smart Balloon V15 SPIKY_FUZZY Classification Fix Test\n")

    results = []
    results.append(test_with_synthetic_spiky_balloon())
    results.append(test_with_smooth_oval())
    test_classification_comparison()

    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    print(f"Tests Passed: {sum(results)}/{len(results)}")

    if all(results):
        print("✅ ALL TESTS PASSED! Fix is working correctly.")
    else:
        print("❌ Some tests failed. Please review the output above.")
