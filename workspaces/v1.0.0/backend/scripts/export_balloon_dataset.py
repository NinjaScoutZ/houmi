import os
import sys
import json
import shutil
import random
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import cv2
import numpy as np
from app.database import SessionLocal
from app.models.all_models import Page, TextBlock, Project
from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

def export_all_historical_balloon_dataset():
    desktop_path = Path(os.path.expanduser("~/Desktop"))
    output_dir = desktop_path / "Houmi_Balloon_Training_Dataset"
    
    # Subdirectories
    full_pages_dir = output_dir / "01_Full_Pages_With_Boxes"
    crops_dir = output_dir / "02_Individual_Balloon_Crops"
    yolo_dir = output_dir / "03_YOLO_Dataset_Format"
    yolo_img_train = yolo_dir / "images" / "train"
    yolo_lbl_train = yolo_dir / "labels" / "train"
    yolo_img_val = yolo_dir / "images" / "val"
    yolo_lbl_val = yolo_dir / "labels" / "val"
    yolo_vis_dir = yolo_dir / "visualized_tiles"
    
    # Reset / Create directories
    if output_dir.exists():
        shutil.rmtree(output_dir)
        
    full_pages_dir.mkdir(parents=True, exist_ok=True)
    crops_dir.mkdir(parents=True, exist_ok=True)
    yolo_img_train.mkdir(parents=True, exist_ok=True)
    yolo_lbl_train.mkdir(parents=True, exist_ok=True)
    yolo_img_val.mkdir(parents=True, exist_ok=True)
    yolo_lbl_val.mkdir(parents=True, exist_ok=True)
    yolo_vis_dir.mkdir(parents=True, exist_ok=True)
    
    projects_dir = BASE_DIR.parent / "data" / "projects"
    json_files = list(projects_dir.glob("*/training/balloons.json"))
    print(f"Found {len(json_files)} project dataset JSON files in data/projects")
    
    # Collect all pages with balloons across all historical projects
    all_dataset_pages = []
    
    for jf in json_files:
        try:
            content = json.loads(jf.read_text(encoding="utf-8"))
            project_id = content.get("project_id", jf.parent.parent.name)
            
            pages_list = content.get("pages", [])
            for pg in pages_list:
                img_path_str = pg.get("image")
                balloons = pg.get("balloons", [])
                
                if not img_path_str or not balloons:
                    continue
                    
                img_path = Path(img_path_str)
                if not img_path.exists():
                    # Try fallback path within project dir
                    img_name = img_path.name
                    fallback = jf.parent.parent / pg.get("page_id", "") / img_name
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
            print(f"Error parsing {jf}: {e}")
            
    print(f"Total Valid Pages with Balloons found across ALL projects: {len(all_dataset_pages)}")
    
    # Deduplicate pages by image_path
    unique_pages = {}
    for p in all_dataset_pages:
        unique_pages[p["image_path"]] = p
    all_pages = list(unique_pages.values())
    
    print(f"Unique Pages to Export: {len(all_pages)}")
    
    # Train / Val split (85% / 15%)
    random.seed(42)
    random.shuffle(all_pages)
    val_count = int(len(all_pages) * 0.15)
    val_image_paths = set(p["image_path"] for p in all_pages[:val_count])
    
    total_exported_pages = 0
    total_exported_balloons = 0
    dataset_summary = []
    
    for page_idx, page_info in enumerate(all_pages, 1):
        img_path = Path(page_info["image_path"])
        img = cv2_imread_unicode(str(img_path))
        if img is None:
            continue
            
        img_h, img_w = img.shape[:2]
        proj_id_short = page_info["project_id"][:8]
        page_prefix = f"p{page_idx:04d}_{proj_id_short}"
        
        # 1. Export Full Page with Drawn Bounding Boxes
        annotated_img = img.copy()
        page_blocks_info = []
        
        for b_idx, b in enumerate(page_info["balloons"], 1):
            bbox = b.get("bbox", [])
            if len(bbox) < 4:
                continue
                
            bx = max(0, int(bbox[0]))
            by = max(0, int(bbox[1]))
            bw = min(img_w - bx, max(1, int(bbox[2])))
            bh = min(img_h - by, max(1, int(bbox[3])))
            bx1 = bx + bw
            by1 = by + bh
            
            # Draw bright green box
            cv2.rectangle(annotated_img, (bx, by), (bx1, by1), (0, 230, 115), 3)
            
            # Draw Label Pill Above Box
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
            
            # 2. Export Individual Crop of this Balloon
            pad_x = int(bw * 0.05)
            pad_y = int(bh * 0.05)
            crop_x0 = max(0, bx - pad_x)
            crop_y0 = max(0, by - pad_y)
            crop_x1 = min(img_w, bx1 + pad_x)
            crop_y1 = min(img_h, by1 + pad_y)
            
            crop_img = img[crop_y0:crop_y1, crop_x0:crop_x1]
            crop_filename = f"{page_prefix}_b{b_idx:02d}_x{bx}_y{by}_w{bw}_h{bh}.png"
            cv2_imwrite_unicode(str(crops_dir / crop_filename), crop_img)
            
            page_blocks_info.append({
                "block_index": b_idx,
                "block_id": b.get("block_id", f"b_{b_idx}"),
                "x": bx,
                "y": by,
                "width": bw,
                "height": bh,
                "type": b.get("type", "bubble"),
                "confidence": b.get("confidence", 1.0),
                "crop_filename": crop_filename
            })
            total_exported_balloons += 1
            
        full_page_filename = f"{page_prefix}_annotated.png"
        cv2_imwrite_unicode(str(full_pages_dir / full_page_filename), annotated_img)
        total_exported_pages += 1
        
        # 3. Export YOLO Dataset Tiles & Labels
        is_val = page_info["image_path"] in val_image_paths
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
                bbox = b.get("bbox", [])
                if len(bbox) < 4:
                    continue
                by0, by1 = bbox[1], bbox[1] + bbox[3]
                if by0 >= ty and by1 <= ty + tile_h:
                    tile_blocks.append(b)
                else:
                    overlap_h = max(0, min(by1, ty + tile_h) - max(by0, ty))
                    if overlap_h >= (bbox[3] * 0.5):
                        tile_blocks.append(b)
                        
            if not tile_blocks:
                continue
                
            crop_tile = img[ty:ty+tile_h, 0:img_w]
            tile_name = f"{page_prefix}_t{tile_idx:02d}"
            tile_img_file = target_img_dir / f"{tile_name}.png"
            tile_lbl_file = target_lbl_dir / f"{tile_name}.txt"
            
            cv2_imwrite_unicode(str(tile_img_file), crop_tile)
            
            # Draw visualization for YOLO tile
            tile_vis = crop_tile.copy()
            tile_th, tile_tw = crop_tile.shape[:2]
            
            with tile_lbl_file.open("w", encoding="utf-8") as f:
                for block in tile_blocks:
                    bbox = block.get("bbox", [])
                    rel_b_y = bbox[1] - ty
                    x_center = max(0.0, min(1.0, (bbox[0] + bbox[2] / 2.0) / img_w))
                    y_center = max(0.0, min(1.0, (rel_b_y + bbox[3] / 2.0) / tile_h))
                    w_rel = max(0.0, min(1.0, bbox[2] / img_w))
                    h_rel = max(0.0, min(1.0, bbox[3] / tile_h))
                    
                    class_idx = 0 if block.get("type", "bubble") == "bubble" else 1
                    f.write(f"{class_idx} {x_center:.6f} {y_center:.6f} {w_rel:.6f} {h_rel:.6f}\n")
                    
                    # Draw on tile vis
                    vx0 = int((x_center - w_rel/2) * tile_tw)
                    vy0 = int((y_center - h_rel/2) * tile_th)
                    vx1 = int((x_center + w_rel/2) * tile_tw)
                    vy1 = int((y_center + h_rel/2) * tile_th)
                    cv2.rectangle(tile_vis, (vx0, vy0), (vx1, vy1), (0, 220, 255), 2)
                    
            cv2_imwrite_unicode(str(yolo_vis_dir / f"{tile_name}_yolo_bbox.png"), tile_vis)
            
        dataset_summary.append({
            "page_prefix": page_prefix,
            "project_id": page_info["project_id"],
            "image_width": img_w,
            "image_height": img_h,
            "full_page_annotated": full_page_filename,
            "balloon_count": len(page_info["balloons"]),
            "balloons": page_blocks_info
        })
        
        if page_idx % 25 == 0 or page_idx == len(all_pages):
            print(f"Processed {page_idx}/{len(all_pages)} pages... (Exported {total_exported_balloons} balloons)")

    # Save dataset.yaml
    yaml_content = f"""# Houmi Balloon Detection YOLO Dataset (Complete All Projects Historical Dataset)
path: {yolo_dir.absolute().as_posix()}
train: images/train
val: images/val

names:
  0: bubble
  1: narrative
"""
    with (yolo_dir / "dataset.yaml").open("w", encoding="utf-8") as f:
        f.write(yaml_content)
        
    # Save JSON Summary
    with (output_dir / "DATASET_INDEX.json").open("w", encoding="utf-8") as f:
        json.dump({
            "total_projects": len(json_files),
            "total_pages": total_exported_pages,
            "total_balloons": total_exported_balloons,
            "export_directory": str(output_dir),
            "pages": dataset_summary
        }, f, ensure_ascii=False, indent=2)
        
    # Write README guide for user
    readme_content = f"""====================================================================
  🎈 Houmi Studio - Complete Historical Balloon Dataset Export
====================================================================

โฟลเดอร์นี้รวบรวมข้อมูลบอลลูนและรูปหน้าการ์ตูนทั้งหมดจาก "ทุกโปรเจกต์เดิมย้อนหลังทั้งหมด" ({len(json_files)} โปรเจกต์)
จำนวนรวมทั้งหมด: {total_exported_pages} หน้า, รวม {total_exported_balloons} บอลลูน

โครงสร้างโฟลเดอร์สำหรับตรวจสอบและเลือกเทรน:
--------------------------------------------------------------------
1. 01_Full_Pages_With_Boxes/
   - รวมรูปภาพหน้าการ์ตูนเต็มหน้า พร้อมวาดกรอบสี่เหลี่ยมสีเขียวและลำดับเลข #
   - เปิดโฟลเดอร์นี้เพื่อดูภาพรวมแต่ละหน้าว่ากรอบบอลลูนตรงตำแหน่งหรือไม่

2. 02_Individual_Balloon_Crops/
   - รูปครอบตัดเฉพาะบอลลูนแต่ละลูกทีละรูป ({total_exported_balloons} รูป มีขนาด x, y, w, h ในชื่อไฟล์)
   - เปิดคัดดูรูปเฉพาะบอลลูนที่สวยงาม ชัดเจน และลบรูปที่ไม่สมบูรณ์ออกได้ง่าย

3. 03_YOLO_Dataset_Format/
   - โครงสร้างชุดข้อมูลมาตรฐาน YOLO (images/ และ labels/)
   - มีโฟลเดอร์ visualized_tiles/ สำหรับดูพิกัดสเกลจริงที่พร้อมนำไปเข้าเทรนโมเดล YOLO

4. DATASET_INDEX.json
   - ไฟล์ดัชนีระบุพิกัด ขนาด และโปรเจกต์ของบอลลูนทุกตัวในรูปแบบ JSON
====================================================================
"""
    with (output_dir / "README_GUIDE.txt").open("w", encoding="utf-8") as f:
        f.write(readme_content)

    print("\n============================================================")
    print("✅ Complete Historical Balloon Dataset Export Finished!")
    print(f"📦 Total Historical Projects Processed: {len(json_files)}")
    print(f"📄 Total Pages Exported: {total_exported_pages}")
    print(f"🎈 Total Balloons Exported: {total_exported_balloons}")
    print(f"📍 Location: {output_dir}")
    print("============================================================\n")

if __name__ == "__main__":
    export_all_historical_balloon_dataset()
