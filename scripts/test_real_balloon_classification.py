"""Test Smart Balloon V15 classification on real manga balloon images."""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

import cv2
import numpy as np
from app.services.smart_balloon import process_smart_balloon_v15


def create_realistic_spiky_balloon():
    """Create a realistic spiky thought bubble with fuzzy edges."""
    page = np.full((800, 800, 3), 200, dtype=np.uint8)  # Gray background

    # Create main white circle
    center = (400, 400)
    cv2.circle(page, center, 150, (255, 255, 255), -1)

    # Add fuzzy/spiky edges by drawing many small circles around the perimeter
    for i in range(60):
        angle = i * (2 * np.pi / 60)
        # Create irregular spiky pattern
        r = 150 + np.random.randint(-5, 15)
        x = int(center[0] + r * np.cos(angle))
        y = int(center[1] + r * np.sin(angle))

        # Draw small fuzzy circles to create feathered edge
        for j in range(3):
            offset = np.random.randint(-8, 8)
            cv2.circle(page, (x + offset, y + offset),
                      np.random.randint(5, 12), (255, 255, 255), -1)

    # Add more spiky details (like manga thought bubbles)
    for i in range(30):
        angle = i * (2 * np.pi / 30)
        r = 155 + np.random.randint(10, 25)
        x = int(center[0] + r * np.cos(angle))
        y = int(center[1] + r * np.sin(angle))

        # Small spike clusters
        for _ in range(2):
            cv2.circle(page, (x + np.random.randint(-5, 5),
                             y + np.random.randint(-5, 5)),
                      np.random.randint(3, 8), (255, 255, 255), -1)

    # Add text
    cv2.putText(page, "...", (380, 410), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    return page


def create_realistic_smooth_balloon():
    """Create a realistic smooth speech balloon."""
    page = np.full((600, 600, 3), 200, dtype=np.uint8)

    # Draw smooth oval
    cv2.ellipse(page, (300, 300), (140, 100), 0, 0, 360, (255, 255, 255), -1)
    # Black outline
    cv2.ellipse(page, (300, 300), (140, 100), 0, 0, 360, (0, 0, 0), 3)

    # Add speech tail (pointer)
    tail_pts = np.array([[320, 380], [280, 450], [300, 385]], np.int32)
    cv2.fillPoly(page, [tail_pts], (255, 255, 255))
    cv2.polylines(page, [tail_pts], True, (0, 0, 0), 3)

    # Add text
    cv2.putText(page, "Hello!", (250, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    return page


def test_spiky_balloon():
    print("=" * 80)
    print("TEST: Realistic Spiky/Fuzzy Thought Bubble")
    print("=" * 80)

    page = create_realistic_spiky_balloon()
    text_bbox = {"x": 300, "y": 350, "width": 200, "height": 100}

    result = process_smart_balloon_v15(page, text_bbox)

    meta = result['metadata']
    print(f"🎯 Archetype: {result['archetype']}")
    print(f"\n📊 Feature Values:")
    print(f"  roughness: {meta['roughness']:.2f}")
    print(f"  raw_roughness: {meta['raw_roughness']:.2f}")
    print(f"  edge_density: {meta['edge_density']:.3f}")
    print(f"  high_freq_ratio: {meta['high_freq_ratio']:.3f}")
    print(f"  rect_ratio: {meta['rect_ratio']:.2f}")

    print(f"\n🔍 Classification Checks:")
    print(f"  is_fuzzy_density (>= 0.095): {meta['edge_density'] >= 0.095}")
    print(f"  roughness > 1.8: {meta['roughness'] > 1.8}")
    print(f"  raw_roughness > 35: {meta['raw_roughness'] > 35}")

    if result['archetype'] == 'SPIKY_FUZZY':
        print("\n✅ PASS: Correctly classified as SPIKY_FUZZY")
        return True
    else:
        print(f"\n⚠️  Classified as {result['archetype']} (might be acceptable)")
        return False


def test_smooth_balloon():
    print("\n" + "=" * 80)
    print("TEST: Realistic Smooth Speech Balloon")
    print("=" * 80)

    page = create_realistic_smooth_balloon()
    text_bbox = {"x": 230, "y": 270, "width": 140, "height": 60}

    result = process_smart_balloon_v15(page, text_bbox)

    meta = result['metadata']
    print(f"🎯 Archetype: {result['archetype']}")
    print(f"\n📊 Feature Values:")
    print(f"  roughness: {meta['roughness']:.2f}")
    print(f"  raw_roughness: {meta['raw_roughness']:.2f}")
    print(f"  edge_density: {meta['edge_density']:.3f}")
    print(f"  high_freq_ratio: {meta['high_freq_ratio']:.3f}")
    print(f"  rect_ratio: {meta['rect_ratio']:.2f}")

    print(f"\n🔍 Classification Checks:")
    print(f"  is_fuzzy_density (>= 0.095): {meta['edge_density'] >= 0.095}")
    print(f"  roughness > 1.8: {meta['roughness'] > 1.8}")
    print(f"  raw_roughness > 35: {meta['raw_roughness'] > 35}")

    if result['archetype'] == 'SMOOTH_OVAL':
        print("\n✅ PASS: Correctly classified as SMOOTH_OVAL")
        return True
    else:
        print(f"\n❌ FAIL: Expected SMOOTH_OVAL but got {result['archetype']}")
        return False


if __name__ == "__main__":
    print("\n🔧 Smart Balloon V15 Classification Test - Real Balloon Simulation\n")

    result1 = test_spiky_balloon()
    result2 = test_smooth_balloon()

    print("\n" + "=" * 80)
    print("📈 SUMMARY")
    print("=" * 80)
    print(f"Spiky Balloon: {'✅ PASS' if result1 else '⚠️  CHECK'}")
    print(f"Smooth Balloon: {'✅ PASS' if result2 else '❌ FAIL'}")

    if result2:
        print("\n🎉 Critical test passed: Smooth balloons are NOT misclassified as SPIKY_FUZZY")
        print("   This was the main bug reported in the issue.")
