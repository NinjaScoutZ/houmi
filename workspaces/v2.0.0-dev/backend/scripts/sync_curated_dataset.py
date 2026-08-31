import os
import sys
import json
import shutil
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import cv2
from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

def sync_curated_dataset():
    desktop_path = Path(os.path.expanduser("~/Desktop"))
    output_dir = desktop_path / "Houmi_Balloon_Training_Dataset"
    
    crops_dir = output_dir / "02_Individual_Balloon_Crops"
    yolo_dir = output_dir / "03_YOLO_Dataset_Format"
    index_file = output_dir / "DATASET_INDEX.json"
    
    if not crops_dir.exists() or not index_file.exists():
        print("Error: Dataset directory or DATASET_INDEX.json not found on Desktop.")
        return
        
    print("Reading DATASET_INDEX.json...")
    index_data = json.loads(index_file.read_text(encoding="utf-8"))
    
    # 1. Get set of remaining balloon crop filenames in 02_Individual_Balloon_Crops
    remaining_crop_files = set(f.name for f in crops_dir.glob("*.png"))
    remaining_crop_files.update(f.name for f in crops_dir.glob("*.jpg"))
    
    print(f"Total remaining balloon crop images in folder: {len(remaining_crop_files)}")
    
    # 2. Filter index pages & balloons based on user deletions
    cleaned_pages = []
    total_kept_balloons = 0
    total_kept_pages = 0
    
    for page in index_data.get("pages", []):
        page_prefix = page["page_prefix"]
        kept_balloons = []
        
        for b in page.get("balloons", []):
            crop_name = b.get("crop_filename")
            if crop_name in remaining_crop_files:
                kept_balloons.append(b)
                total_kept_balloons += 1
                
        if kept_balloons:
            page_copy = dict(page)
            page_copy["balloon_count"] = len(kept_balloons)
            page_copy["balloons"] = kept_balloons
            cleaned_pages.append(page_copy)
            total_kept_pages += 1
            
    print(f"Kept Balloons: {total_kept_balloons} across {total_kept_pages} pages")
    
    # 3. Rebuild 03_YOLO_Dataset_Format with ONLY kept balloons
    yolo_img_train = yolo_dir / "images" / "train"
    yolo_lbl_train = yolo_dir / "labels" / "train"
    yolo_img_val = yolo_dir / "images" / "val"
    yolo_lbl_val = yolo_dir / "labels" / "val"
    
    # Clean old YOLO dirs
    shutil.rmtree(yolo_dir, ignore_errors=True)
    yolo_img_train.mkdir(parents=True, exist_ok=True)
    yolo_lbl_train.mkdir(parents=True, exist_ok=True)
    yolo_img_val.mkdir(parents=True, exist_ok=True)
    yolo_lbl_val.mkdir(parents=True, exist_ok=True)
    
    # Random split
    random.seed(42)
    cleaned_pages_list = list(cleaned_pages)
    random.shuffle(cleaned_pages_list)
    val_count = int(len(cleaned_pages_list) * 0.15)
    val_prefixes = set(p["page_prefix"] for p in cleaned_pages_list[:val_count])
    
    total_yolo_tiles = 0
    
    for page_info in cleaned_pages:
        page_prefix = page_info["page_prefix"]
        
        # Load annotated image path or source image
        annotated_path = output_dir / "01_Full_Pages_With_Boxes" / page_info["full_page_annotated"]
        if not annotated_path.exists():
            continue
            
        img = cv2_imread_unicode(str(annotated_path))
        if img is None:
            continue
            
        img_h, img_w = img.shape[:2]
        is_val = page_prefix in val_prefixes
        target_img_dir = yolo_img_val if is_val else yolo_img_train
        target_lbl_dir = yolo_lbl_val if is_val else yolo_lbl_train
        
        tile_h = min(img_h, img_w)
        stride = max(1, int(tile_h * 0.8))
        
        ys = []
        y = 0
        while True:
            ys.append(y)
            if y + tile_h >= img_h:
                break
            y = min(img_h - tile_h, y + stride)
            
        for tile_idx, ty in enumerate(ys):
            tile_blocks = []
            for b in page_info["balloons"]:
                by0, by1 = b["y"], b["y"] + b["height"]
                if by0 >= ty and by1 <= ty + tile_h:
                    tile_blocks.append(b)
                else:
                    overlap_h = max(0, min(by1, ty + tile_h) - max(by0, ty))
                    if overlap_h >= (b["height"] * 0.5):
                        tile_blocks.append(b)
                        
            if not tile_blocks:
                continue
                
            crop_tile = img[ty:ty+tile_h, 0:img_w]
            tile_name = f"{page_prefix}_t{tile_idx:02d}"
            tile_img_file = target_img_dir / f"{tile_name}.png"
            tile_lbl_file = target_lbl_dir / f"{tile_name}.txt"
            
            cv2_imwrite_unicode(str(tile_img_file), crop_tile)
            
            with tile_lbl_file.open("w", encoding="utf-8") as f:
                for b in tile_blocks:
                    rel_b_y = b["y"] - ty
                    x_center = max(0.0, min(1.0, (b["x"] + b["width"] / 2.0) / img_w))
                    y_center = max(0.0, min(1.0, (rel_b_y + b["height"] / 2.0) / tile_h))
                    w_rel = max(0.0, min(1.0, b["width"] / img_w))
                    h_rel = max(0.0, min(1.0, b["height"] / tile_h))
                    
                    class_idx = 0 if b.get("type", "bubble") == "bubble" else 1
                    f.write(f"{class_idx} {x_center:.6f} {y_center:.6f} {w_rel:.6f} {h_rel:.6f}\n")
                    
            total_yolo_tiles += 1

    # Save dataset.yaml
    yaml_content = f"""# Houmi Curated Balloon Detection YOLO Dataset
path: {yolo_dir.absolute().as_posix()}
train: images/train
val: images/val

names:
  0: bubble
  1: narrative
"""
    with (yolo_dir / "dataset.yaml").open("w", encoding="utf-8") as f:
        f.write(yaml_content)
        
    # Update DATASET_INDEX.json
    curated_summary = {
        "total_pages": total_kept_pages,
        "total_balloons": total_kept_balloons,
        "total_yolo_tiles": total_yolo_tiles,
        "export_directory": str(output_dir),
        "pages": cleaned_pages
    }
    with index_file.open("w", encoding="utf-8") as f:
        json.dump(curated_summary, f, ensure_ascii=False, indent=2)

    print("\n============================================================")
    print("✅ Curated Dataset Sync Completed Successfully!")
    print(f"🎈 Total Kept Balloons: {total_kept_balloons}")
    print(f"📄 Total Kept Pages: {total_kept_pages}")
    print(f"🧩 Total YOLO Tiles Generated: {total_yolo_tiles}")
    print(f"📍 Location: {yolo_dir}")
    print("============================================================\n")

if __name__ == "__main__":
    sync_curated_dataset()
