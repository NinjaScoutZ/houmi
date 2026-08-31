import os
import sys
import json
import shutil
import random
import time
from pathlib import Path
from collections import Counter
import cv2
import numpy as np

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

def is_valid_balloon_crop(img_crop) -> tuple[bool, str]:
    """
    Evaluates if a cropped image contains a real speech balloon or text block.
    Returns (is_valid, reason).
    """
    if img_crop is None or img_crop.size == 0:
        return False, "empty_image"
        
    h, w = img_crop.shape[:2]
    # Small noise or extreme slivers
    if w < 18 or h < 18:
        return False, "too_small"
        
    aspect_ratio = float(w) / max(1.0, float(h))
    if aspect_ratio > 8.0 or aspect_ratio < 0.12:
        return False, f"extreme_aspect_ratio_{aspect_ratio:.2f}"
        
    gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
    min_val, max_val, _, _ = cv2.minMaxLoc(gray)
    contrast = max_val - min_val
    if contrast < 35:
        return False, f"low_contrast_{contrast}"
        
    # Edge density
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges == 255) / float(h * w)
    if edge_density < 0.002:
        return False, f"low_edge_density_{edge_density:.5f}"
        
    # Adaptive thresholding for text structures
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 3
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    text_like_elements = 0
    for cnt in contours:
        x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
        if w_c < 2 or h_c < 4:
            continue
        if w_c > w * 0.92 or h_c > h * 0.92:
            continue
        elem_ar = float(w_c) / max(1.0, float(h_c))
        if elem_ar > 7.0 or elem_ar < 0.12:
            continue
        text_like_elements += 1
        
    min_elements = 3 if w > 55 else 1
    if text_like_elements < min_elements:
        return False, f"insufficient_text_elements_{text_like_elements}"
        
    return True, "valid"

def compute_box_iou(boxA, boxB):
    # box: [x, y, w, h] in absolute coords
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]
    
    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou

def clean_and_prepare_dataset():
    print("==================================================================", flush=True)
    print("  🚀 HOUMI BALLOON DATASET: FULL AUDIT, CLEANING & PREPARATION", flush=True)
    print("==================================================================", flush=True)
    t0 = time.time()
    
    dataset_root = Path(r"C:\Users\dansa\Desktop\Houmi_Balloon_Training_Dataset")
    if not dataset_root.exists():
        print(f"Error: {dataset_root} does not exist!")
        return
        
    yolo_dir = dataset_root / "03_YOLO_Dataset_Format"
    full_pages_dir = dataset_root / "01_Full_Pages_With_Boxes"
    crops_dir = dataset_root / "02_Individual_Balloon_Crops"
    
    # 1. Load project data to get original full pages for accurate clean-up & negative sampling
    projects_dir = BASE_DIR.parent / "data" / "projects"
    json_files = list(projects_dir.glob("*/training/balloons.json"))
    print(f"Found {len(json_files)} project datasets to cross-check.", flush=True)
    
    all_dataset_pages = []
    for jf in json_files:
        try:
            content = json.loads(jf.read_text(encoding="utf-8"))
            project_id = content.get("project_id", jf.parent.parent.name)
            for pg in content.get("pages", []):
                img_path_str = pg.get("image")
                balloons = pg.get("balloons", [])
                if not img_path_str or not balloons:
                    continue
                img_path = Path(img_path_str)
                if not img_path.exists():
                    fallback = jf.parent.parent / pg.get("page_id", "") / img_path.name
                    if fallback.exists():
                        img_path = fallback
                    else:
                        continue
                all_dataset_pages.append({
                    "project_id": project_id,
                    "page_id": pg.get("page_id", img_path.stem),
                    "image_path": str(img_path),
                    "width": pg.get("width", 0),
                    "height": pg.get("height", 0),
                    "balloons": balloons
                })
        except Exception as e:
            print(f"Error reading {jf}: {e}", flush=True)
            
    # Deduplicate pages
    unique_pages = {}
    for p in all_dataset_pages:
        unique_pages[p["image_path"]] = p
    all_pages = list(unique_pages.values())
    print(f"Total Unique Historical Pages: {len(all_pages)}", flush=True)
    
    # 2. Process and Clean every single balloon box across all pages
    total_raw_balloons = 0
    purged_boxes = 0
    duplicate_merged = 0
    cleaned_pages = []
    purge_reasons = Counter()
    
    print("\n--- PHASE 1: Auditing & Cleaning 100% of Balloon Boxes ---", flush=True)
    
    for p_idx, p in enumerate(all_pages, 1):
        img_path = Path(p["image_path"])
        img = cv2_imread_unicode(str(img_path))
        if img is None:
            continue
            
        img_h, img_w = img.shape[:2]
        raw_balloons = p.get("balloons", [])
        total_raw_balloons += len(raw_balloons)
        
        # Deduplicate overlapping boxes within same page
        non_dup_balloons = []
        for b in raw_balloons:
            bbox = b.get("bbox", [])
            if len(bbox) < 4:
                purged_boxes += 1
                purge_reasons["malformed_bbox"] += 1
                continue
                
            bx, by, bw, bh = max(0, int(bbox[0])), max(0, int(bbox[1])), int(bbox[2]), int(bbox[3])
            bw = min(img_w - bx, bw)
            bh = min(img_h - by, bh)
            
            if bw <= 0 or bh <= 0:
                purged_boxes += 1
                purge_reasons["zero_area"] += 1
                continue
                
            # Check duplicate against already accepted boxes
            is_dup = False
            for existing in non_dup_balloons:
                e_box = existing["clean_bbox"]
                if compute_box_iou([bx, by, bw, bh], e_box) >= 0.82:
                    is_dup = True
                    duplicate_merged += 1
                    break
                    
            if not is_dup:
                non_dup_balloons.append({
                    "raw": b,
                    "clean_bbox": [bx, by, bw, bh]
                })
                
        # Validate balloon content (text / bubble structure / noise / panel lines)
        valid_page_balloons = []
        for b_item in non_dup_balloons:
            bx, by, bw, bh = b_item["clean_bbox"]
            
            # Check 1: Size & Aspect ratio
            if bw < 18 or bh < 18:
                purged_boxes += 1
                purge_reasons["too_small"] += 1
                continue
                
            if bw > 0.97 * img_w and bh > 0.97 * img_h:
                purged_boxes += 1
                purge_reasons["entire_page_box"] += 1
                continue
                
            # Crop image for CV validation
            crop = img[by:by+bh, bx:bx+bw]
            is_valid, reason = is_valid_balloon_crop(crop)
            
            # High-confidence fallback: if box was labeled as bubble with confidence 1.0 and reasonable size, keep unless extreme
            if not is_valid:
                # If reason is extreme aspect ratio, definitely purge
                if "extreme_aspect_ratio" in reason or "empty_image" in reason or "too_small" in reason:
                    purged_boxes += 1
                    purge_reasons[reason] += 1
                    continue
                # For very large speech bubbles or clean textless comic clouds, retain if size is substantial
                if bw >= 50 and bh >= 50 and reason.startswith("insufficient_text_elements"):
                    # Check if standard deviation of brightness indicates a drawn shape (balloon border)
                    gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    if np.std(gray_crop) > 20:
                        valid_page_balloons.append(b_item["clean_bbox"])
                        continue
                        
                purged_boxes += 1
                purge_reasons[reason] += 1
            else:
                valid_page_balloons.append(b_item["clean_bbox"])
                
        if valid_page_balloons or len(raw_balloons) > 0:
            cleaned_pages.append({
                "project_id": p["project_id"],
                "page_id": p["page_id"],
                "image_path": p["image_path"],
                "width": img_w,
                "height": img_h,
                "balloons": valid_page_balloons
            })
            
        if p_idx % 100 == 0 or p_idx == len(all_pages):
            print(f"Audited {p_idx}/{len(all_pages)} pages... (Raw: {total_raw_balloons}, Valid: {sum(len(x['balloons']) for x in cleaned_pages)}, Purged: {purged_boxes})", flush=True)

    print(f"\nAudit Summary:")
    print(f"  Total Raw Balloons Checked: {total_raw_balloons}")
    print(f"  Duplicate Boxes Merged: {duplicate_merged}")
    print(f"  Purged Faulty Boxes: {purged_boxes}")
    print(f"  Purge Breakdown: {dict(purge_reasons)}")
    print(f"  Clean Balloons Retained: {sum(len(x['balloons']) for x in cleaned_pages)}")

    # 3. Rebuild 03_YOLO_Dataset_Format cleanly with unified Class 0 and Negative Background Samples
    print("\n--- PHASE 2: Rebuilding YOLO Dataset & Injecting Negative Samples ---", flush=True)
    
    yolo_img_train = yolo_dir / "images" / "train"
    yolo_lbl_train = yolo_dir / "labels" / "train"
    yolo_img_val = yolo_dir / "images" / "val"
    yolo_lbl_val = yolo_dir / "labels" / "val"
    
    # Clean previous yolo folders
    for d in [yolo_img_train, yolo_lbl_train, yolo_img_val, yolo_lbl_val]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        
    # Split train/val by page (85% / 15%)
    random.seed(42)
    shuffled_pages = list(cleaned_pages)
    random.shuffle(shuffled_pages)
    val_page_count = int(len(shuffled_pages) * 0.15)
    val_image_set = set(p["image_path"] for p in shuffled_pages[:val_page_count])
    
    total_positive_tiles_train = 0
    total_positive_tiles_val = 0
    total_negative_tiles_train = 0
    total_negative_tiles_val = 0
    total_boxes_train = 0
    total_boxes_val = 0
    
    # Store candidate negative tiles to sample from
    candidate_negatives_train = []
    candidate_negatives_val = []
    
    for page_idx, page_info in enumerate(shuffled_pages, 1):
        img_path = Path(page_info["image_path"])
        img = cv2_imread_unicode(str(img_path))
        if img is None:
            continue
            
        img_h, img_w = img.shape[:2]
        is_val = page_info["image_path"] in val_image_set
        target_img_dir = yolo_img_val if is_val else yolo_img_train
        target_lbl_dir = yolo_lbl_val if is_val else yolo_lbl_train
        proj_id_short = page_info["project_id"][:8]
        page_prefix = f"p{page_idx:04d}_{proj_id_short}"
        
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
            tile_crop = img[ty:ty+tile_h, 0:img_w]
            tile_th, tile_tw = tile_crop.shape[:2]
            
            # Find balloons inside this tile
            tile_boxes = []
            for bbox in page_info["balloons"]:
                bx, by, bw, bh = bbox
                by0, by1 = by, by + bh
                
                # Check intersection with tile
                if by0 >= ty and by1 <= ty + tile_h:
                    tile_boxes.append((bx, by - ty, bw, bh))
                else:
                    overlap_h = max(0, min(by1, ty + tile_h) - max(by0, ty))
                    if overlap_h >= (bh * 0.5):
                        # Clamped relative coordinates
                        clamped_y = max(0, by - ty)
                        clamped_h = min(tile_h - clamped_y, bh)
                        if clamped_h >= 15:
                            tile_boxes.append((bx, clamped_y, bw, clamped_h))
                            
            tile_name = f"{page_prefix}_t{tile_idx:02d}"
            
            if tile_boxes:
                # Positive Tile with Balloons
                tile_img_file = target_img_dir / f"{tile_name}.png"
                tile_lbl_file = target_lbl_dir / f"{tile_name}.txt"
                
                cv2_imwrite_unicode(str(tile_img_file), tile_crop)
                
                with tile_lbl_file.open("w", encoding="utf-8") as f:
                    for (bx, by_rel, bw, bh_rel) in tile_boxes:
                        # Normalized coordinates strictly [0.0, 1.0]
                        xc = max(0.001, min(0.999, (bx + bw / 2.0) / tile_tw))
                        yc = max(0.001, min(0.999, (by_rel + bh_rel / 2.0) / tile_th))
                        w_rel = max(0.001, min(0.999, bw / tile_tw))
                        h_rel = max(0.001, min(0.999, bh_rel / tile_th))
                        
                        # Unified Single Class 0: balloon
                        f.write(f"0 {xc:.6f} {yc:.6f} {w_rel:.6f} {h_rel:.6f}\n")
                        
                        if is_val:
                            total_boxes_val += 1
                        else:
                            total_boxes_train += 1
                            
                if is_val:
                    total_positive_tiles_val += 1
                else:
                    total_positive_tiles_train += 1
            else:
                # Negative Tile without balloons (Candidate for negative background sampling)
                # Check if it has visual content (not pure solid color)
                gray_tile = cv2.cvtColor(tile_crop, cv2.COLOR_BGR2GRAY)
                if np.std(gray_tile) > 15:
                    neg_data = (tile_crop, tile_name, is_val)
                    if is_val:
                        candidate_negatives_val.append(neg_data)
                    else:
                        candidate_negatives_train.append(neg_data)

    print(f"Positive Tiles Created -> Train: {total_positive_tiles_train} ({total_boxes_train} boxes), Val: {total_positive_tiles_val} ({total_boxes_val} boxes)", flush=True)

    # 4. Inject Negative Samples (~5% ratio: ~360 train, ~65 val)
    print(f"Injecting Negative Background Samples...", flush=True)
    random.seed(42)
    random.shuffle(candidate_negatives_train)
    random.shuffle(candidate_negatives_val)
    
    target_neg_train = min(len(candidate_negatives_train), 360)
    target_neg_val = min(len(candidate_negatives_val), 65)
    
    for tile_crop, tile_name, _ in candidate_negatives_train[:target_neg_train]:
        neg_img_file = yolo_img_train / f"{tile_name}_bg.png"
        neg_lbl_file = yolo_lbl_train / f"{tile_name}_bg.txt"
        cv2_imwrite_unicode(str(neg_img_file), tile_crop)
        neg_lbl_file.write_text("", encoding="utf-8") # Empty label for negative background
        total_negative_tiles_train += 1
        
    for tile_crop, tile_name, _ in candidate_negatives_val[:target_neg_val]:
        neg_img_file = yolo_img_val / f"{tile_name}_bg.png"
        neg_lbl_file = yolo_lbl_val / f"{tile_name}_bg.txt"
        cv2_imwrite_unicode(str(neg_img_file), tile_crop)
        neg_lbl_file.write_text("", encoding="utf-8") # Empty label for negative background
        total_negative_tiles_val += 1
        
    print(f"Negative Tiles Injected -> Train: {total_negative_tiles_train}, Val: {total_negative_tiles_val}", flush=True)

    # 5. Write Updated dataset.yaml
    yaml_content = f"""# Houmi Balloon Detection YOLO Dataset (Cleaned & Optimized)
path: {yolo_dir.absolute().as_posix()}
train: images/train
val: images/val

names:
  0: balloon
"""
    with (yolo_dir / "dataset.yaml").open("w", encoding="utf-8") as f:
        f.write(yaml_content)

    # 6. Create One-Click Training & ONNX Export Script
    training_script_content = f'''"""
====================================================================
  🎈 Houmi Balloon Detector - One-Click YOLO Training & ONNX Export
====================================================================
This script trains a high-precision balloon detector on the cleaned dataset
and automatically exports the best checkpoint to ONNX format.
"""
import os
import sys
import time
from pathlib import Path
import torch

# Prevent OpenMP and multiprocessing crashes on Windows
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
torch.set_num_threads(1)

# PyTorch 2.6+ safe checkpoint unpickling patch
try:
    import ultralytics.nn.tasks
    torch.serialization.add_safe_globals([ultralytics.nn.tasks.DetectionModel])
except Exception:
    pass

orig_load = torch.load
def patched_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return orig_load(*args, **kwargs)
torch.load = patched_load

from ultralytics import YOLO

def main():
    dataset_yaml = Path(r"{yolo_dir.absolute().as_posix()}/dataset.yaml")
    output_dir = Path(__file__).resolve().parent / "runs"
    
    device = "0" if torch.cuda.is_available() else "cpu"
    print("=" * 60)
    print(f"🚀 Training Houmi Balloon Detector on {{device}}")
    print(f"📁 Dataset Config: {{dataset_yaml}}")
    print(f"🖥️ CUDA Available: {{torch.cuda.is_available()}} ({{torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}})")
    print("=" * 60)

    # Model selection: yolo11s.pt or yolov8s.pt
    # imgsz=1024 provides maximum resolution parity with comic-speech-bubble
    base_model = "yolo11s.pt" if Path("yolo11s.pt").exists() else "yolov8s.pt"
    print(f"Loading Base Weights: {{base_model}}")
    model = YOLO(base_model)

    print("\nStarting Training (50 Epochs, imgsz=1024, batch=8)...")
    results = model.train(
        data=str(dataset_yaml),
        epochs=50,
        imgsz=1024,
        batch=8,
        device=device,
        workers=0,  # Required on Windows
        project=str(output_dir),
        name="balloon_yolo",
        exist_ok=True,
        plots=True,
        save=True,
        mosaic=1.0,
        mixup=0.1,
        patience=12
    )

    # Find best.pt and export to ONNX
    print("\n" + "=" * 60)
    print("📦 Exporting Best Checkpoint to ONNX...")
    best_pt = output_dir / "balloon_yolo" / "weights" / "best.pt"
    if best_pt.exists():
        best_model = YOLO(str(best_pt))
        onnx_path = best_model.export(
            format="onnx",
            imgsz=1024,
            dynamic=False,
            simplify=True,
            opset=17
        )
        print(f"✅ ONNX Model successfully exported to: {{onnx_path}}")
        print("You can copy this ONNX model directly to:")
        print("  e:\\\\houmi\\\\backend\\\\models\\\\sao_balloon_beta\\\\model.onnx")
    else:
        print(f"⚠️ best.pt not found at {{best_pt}}")

if __name__ == "__main__":
    main()
'''
    train_script_file = dataset_root / "train_balloon_model.py"
    with train_script_file.open("w", encoding="utf-8") as f:
        f.write(training_script_content)

    # 7. Write Cleaning Report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "execution_time_seconds": round(time.time() - t0, 2),
        "total_historical_pages_audited": len(all_pages),
        "total_raw_balloons_audited": total_raw_balloons,
        "duplicate_boxes_merged": duplicate_merged,
        "purged_faulty_boxes": purged_boxes,
        "purge_breakdown": dict(purge_reasons),
        "clean_balloons_retained": sum(len(x['balloons']) for x in cleaned_pages),
        "final_dataset_stats": {
            "train_positive_tiles": total_positive_tiles_train,
            "train_negative_tiles": total_negative_tiles_train,
            "train_total_tiles": total_positive_tiles_train + total_negative_tiles_train,
            "train_total_boxes": total_boxes_train,
            "val_positive_tiles": total_positive_tiles_val,
            "val_negative_tiles": total_negative_tiles_val,
            "val_total_tiles": total_positive_tiles_val + total_negative_tiles_val,
            "val_total_boxes": total_boxes_val,
            "total_tiles_all": total_positive_tiles_train + total_negative_tiles_train + total_positive_tiles_val + total_negative_tiles_val,
            "total_boxes_all": total_boxes_train + total_boxes_val,
            "negative_sample_ratio": f"{((total_negative_tiles_train + total_negative_tiles_val) / (total_positive_tiles_train + total_negative_tiles_train + total_positive_tiles_val + total_negative_tiles_val)) * 100:.2f}%"
        },
        "training_script_location": str(train_script_file),
        "dataset_yaml_location": str(yolo_dir / "dataset.yaml")
    }
    
    report_json_path = dataset_root / "CLEANING_REPORT.json"
    with report_json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n==================================================================", flush=True)
    print("  ✅ DATASET CLEANING & PREPARATION COMPLETED SUCCESSFULLY!", flush=True)
    print(f"  ⏱️ Time Elapsed: {time.time() - t0:.2f}s")
    print(f"  📦 Total Clean Tiles: {report['final_dataset_stats']['total_tiles_all']}")
    print(f"  🎈 Total Clean Bounding Boxes: {report['final_dataset_stats']['total_boxes_all']} (Class: 0 balloon)")
    print(f"  🖼️ Negative Samples Added: {total_negative_tiles_train + total_negative_tiles_val} ({report['final_dataset_stats']['negative_sample_ratio']})")
    print(f"  📜 Training Script: {train_script_file}")
    print("==================================================================\n", flush=True)

if __name__ == "__main__":
    clean_and_prepare_dataset()
