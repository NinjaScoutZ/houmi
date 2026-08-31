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
import onnxruntime as ort

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

def compute_box_iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]
    
    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou

class NeuralBalloonCleaner:
    def __init__(self):
        unet_path = BASE_DIR / "models" / "manga_text_segmentation" / "manga_unet.onnx"
        if not unet_path.exists():
            raise FileNotFoundError(f"UNet model not found at {unet_path}")
        
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        self.sess = ort.InferenceSession(str(unet_path), sess_options=opts, providers=["CPUExecutionProvider"])
        print(f"Loaded Manga UNet Neural Cleaner from {unet_path}", flush=True)

    def evaluate_crop_batch(self, crop_images: list[np.ndarray]) -> list[tuple[bool, str]]:
        """
        Evaluates a batch of cropped images.
        Returns list of (is_valid, reason).
        """
        results = []
        if not crop_images:
            return results
            
        batch_tensors = []
        valid_indices = []
        
        for idx, img in enumerate(crop_images):
            if img is None or img.size == 0:
                results.append((False, "empty_image"))
                continue
            h, w = img.shape[:2]
            if w < 18 or h < 18:
                results.append((False, "too_small"))
                continue
                
            ar = float(w) / max(1.0, float(h))
            if ar > 8.0 or ar < 0.12:
                results.append((False, f"extreme_aspect_ratio_{ar:.2f}"))
                continue
                
            # Prepare for UNet
            resized = cv2.resize(img, (128, 128))
            inp = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)
            batch_tensors.append(inp)
            valid_indices.append((idx, img))
            results.append((None, "")) # placeholder
            
        if not batch_tensors:
            return results
            
        batch_arr = np.stack(batch_tensors, axis=0)
        out = self.sess.run(None, {"input": batch_arr})[0]
        # out shape: (N, 1, 128, 128)
        probs = 1.0 / (1.0 + np.exp(-out[:, 0]))
        
        for i, (orig_idx, img) in enumerate(valid_indices):
            h, w = img.shape[:2]
            prob = probs[i]
            max_prob = float(np.max(prob))
            text_pixels = int(np.sum(prob > 0.35))
            
            # Rule 1: High text probability -> Real speech balloon with text!
            if max_prob >= 0.25 and text_pixels >= 12:
                results[orig_idx] = (True, "valid_text_balloon")
                continue
                
            # Rule 2: Large clean comic bubble (empty thought cloud / speech bubble without text)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            mean_lum = np.mean(gray)
            std_lum = np.std(gray)
            
            if w >= 70 and h >= 70 and mean_lum > 215 and std_lum < 45:
                # Must not be pure solid white with no border
                edges = cv2.Canny(gray, 50, 150)
                if np.sum(edges == 255) >= 40:
                    results[orig_idx] = (True, "valid_textless_bubble")
                    continue
                    
            # Rule 3: Speed lines, sweat marks, blush marks, action strokes, background details -> PURGE!
            if max_prob < 0.25 or text_pixels < 12:
                reason = "speed_or_sweat_lines" if (w < 180 and h < 180) else "no_manga_text_structure"
                results[orig_idx] = (False, f"{reason}_prob_{max_prob:.3f}")
                continue
                
            results[orig_idx] = (False, "unclassified_noise")
            
        return results

def run_deep_clean():
    print("==================================================================", flush=True)
    print("  🧠 HOUMI BALLOON DATASET: NEURAL AUDIT & COMPLETE CLEANING", flush=True)
    print("==================================================================", flush=True)
    t0 = time.time()
    
    cleaner = NeuralBalloonCleaner()
    dataset_root = Path(r"C:\Users\dansa\Desktop\Houmi_Balloon_Training_Dataset")
    if not dataset_root.exists():
        print(f"Error: {dataset_root} does not exist!")
        return
        
    full_pages_dir = dataset_root / "01_Full_Pages_With_Boxes"
    crops_dir = dataset_root / "02_Individual_Balloon_Crops"
    yolo_dir = dataset_root / "03_YOLO_Dataset_Format"
    
    # Clean all 3 folders completely
    print("\n--- Resetting and Rebuilding All 3 Dataset Folders ---", flush=True)
    for d in [full_pages_dir, crops_dir, yolo_dir]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        
    yolo_img_train = yolo_dir / "images" / "train"
    yolo_lbl_train = yolo_dir / "labels" / "train"
    yolo_img_val = yolo_dir / "images" / "val"
    yolo_lbl_val = yolo_dir / "labels" / "val"
    for d in [yolo_img_train, yolo_lbl_train, yolo_img_val, yolo_lbl_val]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Load project data
    projects_dir = BASE_DIR.parent / "data" / "projects"
    json_files = list(projects_dir.glob("*/training/balloons.json"))
    
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
            
    unique_pages = {}
    for p in all_dataset_pages:
        unique_pages[p["image_path"]] = p
    all_pages = list(unique_pages.values())
    print(f"Found {len(all_pages)} unique historical pages to audit.", flush=True)
    
    # 2. Audit and Neural-Clean each page
    cleaned_pages = []
    total_raw_balloons = 0
    purged_boxes = 0
    duplicate_merged = 0
    purge_reasons = Counter()
    
    print("\n--- PHASE 1: Neural Scanning & Filtering All Balloon Boxes ---", flush=True)
    
    for p_idx, p in enumerate(all_pages, 1):
        img_path = Path(p["image_path"])
        img = cv2_imread_unicode(str(img_path))
        if img is None:
            continue
            
        img_h, img_w = img.shape[:2]
        raw_balloons = p.get("balloons", [])
        total_raw_balloons += len(raw_balloons)
        
        # Deduplicate
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
                
            is_dup = False
            for existing in non_dup_balloons:
                if compute_box_iou([bx, by, bw, bh], existing) >= 0.82:
                    is_dup = True
                    duplicate_merged += 1
                    break
            if not is_dup:
                non_dup_balloons.append([bx, by, bw, bh])
                
        # Extract crops for neural evaluation
        page_crops = []
        for (bx, by, bw, bh) in non_dup_balloons:
            pad_x = int(bw * 0.05)
            pad_y = int(bh * 0.05)
            c_x0 = max(0, bx - pad_x)
            c_y0 = max(0, by - pad_y)
            c_x1 = min(img_w, bx + bw + pad_x)
            c_y1 = min(img_h, by + bh + pad_y)
            crop_img = img[c_y0:c_y1, c_x0:c_x1]
            page_crops.append(crop_img)
            
        eval_results = cleaner.evaluate_crop_batch(page_crops)
        
        valid_page_balloons = []
        for b_idx, (bx, by, bw, bh) in enumerate(non_dup_balloons):
            is_valid, reason = eval_results[b_idx]
            if is_valid:
                valid_page_balloons.append((bx, by, bw, bh))
            else:
                purged_boxes += 1
                main_reason = reason.split("_prob_")[0]
                purge_reasons[main_reason] += 1
                
        cleaned_pages.append({
            "project_id": p["project_id"],
            "page_id": p["page_id"],
            "image_path": p["image_path"],
            "width": img_w,
            "height": img_h,
            "balloons": valid_page_balloons
        })
        
        if p_idx % 100 == 0 or p_idx == len(all_pages):
            print(f"Audited {p_idx}/{len(all_pages)} pages... (Raw: {total_raw_balloons}, Valid Clean: {sum(len(x['balloons']) for x in cleaned_pages)}, Purged: {purged_boxes})", flush=True)

    print(f"\nAudit Summary:")
    print(f"  Total Raw Balloons Checked: {total_raw_balloons}")
    print(f"  Duplicate Boxes Merged: {duplicate_merged}")
    print(f"  Purged Junk / Speed Lines / Sweat Marks: {purged_boxes}")
    print(f"  Purge Breakdown: {dict(purge_reasons)}")
    print(f"  Clean Real Balloons Retained: {sum(len(x['balloons']) for x in cleaned_pages)}")

    # 3. Export Clean 01_Full_Pages_With_Boxes and 02_Individual_Balloon_Crops
    print("\n--- PHASE 2: Exporting Clean 01_Full_Pages & 02_Individual_Crops ---", flush=True)
    
    # Train / Val split (85% / 15%)
    random.seed(42)
    shuffled_pages = list(cleaned_pages)
    random.shuffle(shuffled_pages)
    val_page_count = int(len(shuffled_pages) * 0.15)
    val_image_set = set(p["image_path"] for p in shuffled_pages[:val_page_count])
    
    dataset_summary = []
    total_clean_crops = 0
    
    candidate_negatives_train = []
    candidate_negatives_val = []
    total_positive_tiles_train = 0
    total_positive_tiles_val = 0
    total_boxes_train = 0
    total_boxes_val = 0
    
    for page_idx, page_info in enumerate(shuffled_pages, 1):
        img_path = Path(page_info["image_path"])
        img = cv2_imread_unicode(str(img_path))
        if img is None:
            continue
            
        img_h, img_w = img.shape[:2]
        proj_id_short = page_info["project_id"][:8]
        page_prefix = f"p{page_idx:04d}_{proj_id_short}"
        is_val = page_info["image_path"] in val_image_set
        
        # 1. Annotated Full Page
        annotated_img = img.copy()
        page_balloons_info = []
        
        for b_idx, (bx, by, bw, bh) in enumerate(page_info["balloons"], 1):
            bx1, by1 = bx + bw, by + bh
            cv2.rectangle(annotated_img, (bx, by), (bx1, by1), (0, 230, 115), 3)
            
            label_str = f"#{b_idx} [{bw}x{bh}]"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 1
            (text_w, text_h), _ = cv2.getTextSize(label_str, font, font_scale, thickness)
            lbl_bg_y1 = max(0, by - 4)
            lbl_bg_y0 = max(0, lbl_bg_y1 - text_h - 6)
            lbl_bg_x0 = bx
            lbl_bg_x1 = min(img_w, bx + text_w + 10)
            cv2.rectangle(annotated_img, (lbl_bg_x0, lbl_bg_y0), (lbl_bg_x1, lbl_bg_y1), (0, 180, 90), -1)
            cv2.putText(annotated_img, label_str, (bx + 5, lbl_bg_y1 - 3), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
            
            # 2. Individual Clean Crop
            pad_x = int(bw * 0.05)
            pad_y = int(bh * 0.05)
            crop_x0 = max(0, bx - pad_x)
            crop_y0 = max(0, by - pad_y)
            crop_x1 = min(img_w, bx1 + pad_x)
            crop_y1 = min(img_h, by1 + pad_y)
            crop_img = img[crop_y0:crop_y1, crop_x0:crop_x1]
            crop_filename = f"{page_prefix}_b{b_idx:02d}_x{bx}_y{by}_w{bw}_h{bh}.png"
            cv2_imwrite_unicode(str(crops_dir / crop_filename), crop_img)
            total_clean_crops += 1
            
            page_balloons_info.append({
                "balloon_index": b_idx,
                "x": bx, "y": by, "width": bw, "height": bh,
                "crop_filename": crop_filename
            })
            
        full_page_filename = f"{page_prefix}_annotated.png"
        cv2_imwrite_unicode(str(full_pages_dir / full_page_filename), annotated_img)
        
        # 3. YOLO Tiles
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
            tile_crop = img[ty:ty+tile_h, 0:img_w]
            tile_th, tile_tw = tile_crop.shape[:2]
            
            tile_boxes = []
            for (bx, by, bw, bh) in page_info["balloons"]:
                by0, by1 = by, by + bh
                if by0 >= ty and by1 <= ty + tile_h:
                    tile_boxes.append((bx, by - ty, bw, bh))
                else:
                    overlap_h = max(0, min(by1, ty + tile_h) - max(by0, ty))
                    if overlap_h >= (bh * 0.5):
                        clamped_y = max(0, by - ty)
                        clamped_h = min(tile_h - clamped_y, bh)
                        if clamped_h >= 15:
                            tile_boxes.append((bx, clamped_y, bw, clamped_h))
                            
            tile_name = f"{page_prefix}_t{tile_idx:02d}"
            
            if tile_boxes:
                tile_img_file = target_img_dir / f"{tile_name}.png"
                tile_lbl_file = target_lbl_dir / f"{tile_name}.txt"
                cv2_imwrite_unicode(str(tile_img_file), tile_crop)
                
                with tile_lbl_file.open("w", encoding="utf-8") as f:
                    for (bx, by_rel, bw, bh_rel) in tile_boxes:
                        xc = max(0.001, min(0.999, (bx + bw / 2.0) / tile_tw))
                        yc = max(0.001, min(0.999, (by_rel + bh_rel / 2.0) / tile_th))
                        w_rel = max(0.001, min(0.999, bw / tile_tw))
                        h_rel = max(0.001, min(0.999, bh_rel / tile_th))
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
                gray_tile = cv2.cvtColor(tile_crop, cv2.COLOR_BGR2GRAY)
                if np.std(gray_tile) > 15:
                    neg_data = (tile_crop, tile_name, is_val)
                    if is_val:
                        candidate_negatives_val.append(neg_data)
                    else:
                        candidate_negatives_train.append(neg_data)

        dataset_summary.append({
            "page_prefix": page_prefix,
            "project_id": page_info["project_id"],
            "image_width": img_w,
            "image_height": img_h,
            "full_page_annotated": full_page_filename,
            "balloon_count": len(page_info["balloons"]),
            "balloons": page_balloons_info
        })
        
        if page_idx % 200 == 0 or page_idx == len(shuffled_pages):
            print(f"Exported {page_idx}/{len(shuffled_pages)} clean pages... (Total Clean Crops: {total_clean_crops})", flush=True)

    # 4. Inject Negative Background Samples
    print(f"Injecting Negative Background Samples...", flush=True)
    random.seed(42)
    random.shuffle(candidate_negatives_train)
    random.shuffle(candidate_negatives_val)
    
    target_neg_train = min(len(candidate_negatives_train), 360)
    target_neg_val = min(len(candidate_negatives_val), 65)
    total_negative_tiles_train = 0
    total_negative_tiles_val = 0
    
    for tile_crop, tile_name, _ in candidate_negatives_train[:target_neg_train]:
        neg_img_file = yolo_img_train / f"{tile_name}_bg.png"
        neg_lbl_file = yolo_lbl_train / f"{tile_name}_bg.txt"
        cv2_imwrite_unicode(str(neg_img_file), tile_crop)
        neg_lbl_file.write_text("", encoding="utf-8")
        total_negative_tiles_train += 1
        
    for tile_crop, tile_name, _ in candidate_negatives_val[:target_neg_val]:
        neg_img_file = yolo_img_val / f"{tile_name}_bg.png"
        neg_lbl_file = yolo_lbl_val / f"{tile_name}_bg.txt"
        cv2_imwrite_unicode(str(neg_img_file), tile_crop)
        neg_lbl_file.write_text("", encoding="utf-8")
        total_negative_tiles_val += 1

    # 5. Save updated YAML and INDEX.json
    yaml_content = f"""# Houmi Balloon Detection YOLO Dataset (100% Neural Cleaned & Verified)
path: {yolo_dir.absolute().as_posix()}
train: images/train
val: images/val

names:
  0: balloon
"""
    with (yolo_dir / "dataset.yaml").open("w", encoding="utf-8") as f:
        f.write(yaml_content)

    with (dataset_root / "DATASET_INDEX.json").open("w", encoding="utf-8") as f:
        json.dump({
            "total_projects": len(json_files),
            "total_pages": len(shuffled_pages),
            "total_clean_balloons": total_clean_crops,
            "export_directory": str(dataset_root),
            "pages": dataset_summary
        }, f, ensure_ascii=False, indent=2)

    # 6. Cleaning Report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "execution_time_seconds": round(time.time() - t0, 2),
        "total_historical_pages_audited": len(all_pages),
        "total_raw_balloons_audited": total_raw_balloons,
        "duplicate_boxes_merged": duplicate_merged,
        "purged_junk_and_speed_lines": purged_boxes,
        "purge_breakdown": dict(purge_reasons),
        "clean_verified_balloons_retained": total_clean_crops,
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
        "crops_folder": str(crops_dir),
        "annotated_pages_folder": str(full_pages_dir),
        "yolo_folder": str(yolo_dir)
    }
    
    with (dataset_root / "CLEANING_REPORT.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n==================================================================", flush=True)
    print("  ✅ 100% NEURAL DATASET CLEANING COMPLETED!", flush=True)
    print(f"  ⏱️ Time Elapsed: {time.time() - t0:.2f}s")
    print(f"  🗑️ Purged Junk / Speed Lines / Sweat: {purged_boxes} boxes")
    print(f"  🎈 Clean Verified Balloon Crops: {total_clean_crops}")
    print(f"  📦 Clean YOLO Tiles: {report['final_dataset_stats']['total_tiles_all']}")
    print(f"  🏷️ Total Clean YOLO Boxes: {report['final_dataset_stats']['total_boxes_all']}")
    print("==================================================================\n", flush=True)

if __name__ == "__main__":
    run_deep_clean()
