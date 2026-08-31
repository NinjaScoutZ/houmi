import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import cv2
import numpy as np
from PIL import Image

from app.services.smart_stitch import (
    scan_folder_for_oversize,
    detect_safe_slice_points,
    smart_split_image,
    smart_split_project_folder,
    smart_stitch_project_folder,
)


def test_scan_folder_for_oversize_detects_long_image():
    with TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        # Create normal image
        normal_img = np.zeros((2000, 720, 3), dtype=np.uint8)
        cv2.imwrite(str(folder / "01.png"), normal_img)

        # Create oversize image (15,000 px height)
        long_img = np.zeros((15000, 720, 3), dtype=np.uint8)
        cv2.imwrite(str(folder / "02.png"), long_img)

        report = scan_folder_for_oversize(folder, threshold_height=10000)

        assert report["has_oversize"] is True
        assert report["total_images"] == 2
        assert report["oversize_count"] == 1
        assert report["max_height"] == 15000
        assert report["oversize_files"][0]["filename"] == "02.png"
        assert report["suggested_split_height"] == 5000
        assert report["suggested_enforce_width"] == 720


def test_detect_safe_slice_points_finds_white_gutter():
    # Build a 12,000 px height image with artwork and a solid white gutter at y=4900..5100
    canvas = np.full((12000, 720, 3), 120, dtype=np.uint8)
    
    # Add high-frequency noise / pattern everywhere
    noise = np.random.randint(0, 255, (12000, 720, 3), dtype=np.uint8)
    canvas = cv2.addWeighted(canvas, 0.5, noise, 0.5, 0)

    # Place a clean pure white background gutter at y=4950..5050
    canvas[4950:5050, :] = (255, 255, 255)

    # Place another clean pure black background gutter at y=9900..10100
    canvas[9900:10100, :] = (0, 0, 0)

    cuts = detect_safe_slice_points(canvas, target_height=5000, search_window=1000)
    
    assert len(cuts) >= 2
    # The first cut should fall precisely in the clean white gutter [4950, 5050]
    assert 4950 <= cuts[0] <= 5050
    # The final cut is always the end of the canvas
    assert cuts[-1] == 12000


def test_smart_split_image_generates_correct_sub_images():
    with TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        source_file = folder / "long_strip.png"
        out_dir = folder / "output"

        # Create 11,000 px strip
        strip = np.full((11000, 720, 3), 240, dtype=np.uint8)
        # Put clean gutter at y=5000..5100
        strip[5000:5100, :] = 255
        cv2.imwrite(str(source_file), strip)

        created_files = smart_split_image(
            image_path=source_file,
            output_dir=out_dir,
            base_prefix="page",
            target_height=5000,
            enforce_width=720,
        )

        assert len(created_files) >= 2
        for f in created_files:
            assert f.exists()
            with Image.open(f) as img:
                w, h = img.size
                assert w == 720
                assert 500 <= h <= 7000


def test_smart_split_project_folder_full_flow():
    with TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        
        # 1. Normal image
        img1 = np.full((3000, 720, 3), 200, dtype=np.uint8)
        cv2.imwrite(str(folder / "01.png"), img1)

        # 2. Oversize image (12,000 px)
        img2 = np.full((12000, 720, 3), 220, dtype=np.uint8)
        img2[4950:5050, :] = 255
        cv2.imwrite(str(folder / "02.png"), img2)

        result = smart_split_project_folder(
            folder_path=folder,
            split_height=5000,
            enforce_width=720,
            backup_original=True,
            threshold_height=10000,
        )

        assert result["status"] == "success"
        assert result["total_original_files"] == 2
        assert result["total_pages"] >= 3

        # Verify backup directory
        raw_dir = folder / "_original_raw"
        assert raw_dir.is_dir()
        assert (raw_dir / "01.png").exists()
        assert (raw_dir / "02.png").exists()

        # Verify main folder now contains sequentially numbered pages
        main_files = sorted([f.name for f in folder.iterdir() if f.is_file() and f.suffix == ".png"])
        assert len(main_files) >= 3
        assert "01.png" in main_files
        assert "02.png" in main_files
        assert "03.png" in main_files


def test_smart_stitch_project_folder_full_flow():
    with TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        
        # Create 6 short images of 3,000 px height each
        for i in range(1, 7):
            img = np.full((3000, 720, 3), 150 + i * 10, dtype=np.uint8)
            # Add white gutter near top and bottom
            img[:50, :] = 255
            img[-50:, :] = 255
            cv2.imwrite(str(folder / f"{i:02d}.jpg"), img)

        result = smart_stitch_project_folder(
            folder_path=folder,
            target_height=9000,
            enforce_width=720,
            backup_original=True,
        )

        assert result["status"] == "success"
        assert result["total_original_files"] == 6
        # 6 images x 3000 = 18,000 px total. With target_height=9000, should produce ~2 stitched pages
        assert result["total_pages"] == 2

        # Verify backup directory
        raw_dir = folder / "_original_raw"
        assert raw_dir.is_dir()
        assert (raw_dir / "01.jpg").exists()
        assert (raw_dir / "06.jpg").exists()

        # Verify main folder now contains stitched images
        main_files = sorted([f.name for f in folder.iterdir() if f.is_file() and f.suffix in [".jpg", ".png"]])
        assert len(main_files) == 2
        assert "01.jpg" in main_files
        assert "02.jpg" in main_files
