import os
import zipfile
import tempfile
import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.all_models import Project, Page
import logging

logger = logging.getLogger("houmi-yolo-export")

def export_yolo_dataset(project_ids: list[str], db: Session) -> Path:
    """
    Compiles selected projects into a standard YOLO dataset ZIP.
    Contains 'images/' and 'labels/' directories.
    All text boxes are mapped to class 0 (general text box).
    """
    temp_dir = Path(tempfile.mkdtemp())
    images_dir = temp_dir / "images"
    labels_dir = temp_dir / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()
    
    try:
        for pid in project_ids:
            project = db.query(Project).filter(Project.id == pid).first()
            if not project:
                continue
            
            for page in project.pages:
                source_path = Path(page.source_image_path)
                if not source_path.exists():
                    continue
                
                ext = source_path.suffix.lower()
                dest_image_name = f"{page.id}{ext}"
                dest_image_path = images_dir / dest_image_name
                
                # Copy the original page image
                shutil.copy(source_path, dest_image_path)
                
                # Write YOLO format labels
                dest_label_path = labels_dir / f"{page.id}.txt"
                with open(dest_label_path, "w", encoding="utf-8") as f:
                    for block in page.text_blocks:
                        if page.width <= 0 or page.height <= 0:
                            continue
                        
                        # YOLO format: <class> <x_center> <y_center> <width> <height>
                        w_norm = block.width / page.width
                        h_norm = block.height / page.height
                        x_center_norm = (block.x + block.width / 2) / page.width
                        y_center_norm = (block.y + block.height / 2) / page.height
                        
                        # Clamp coordinates to [0.0, 1.0]
                        x_center_norm = max(0.0, min(1.0, x_center_norm))
                        y_center_norm = max(0.0, min(1.0, y_center_norm))
                        w_norm = max(0.0, min(1.0, w_norm))
                        h_norm = max(0.0, min(1.0, h_norm))
                        
                        # Class 0: general text bubble
                        f.write(f"0 {x_center_norm:.6f} {y_center_norm:.6f} {w_norm:.6f} {h_norm:.6f}\n")
                        
        # Create ZIP file
        zip_fd, zip_path_str = tempfile.mkstemp(suffix=".zip")
        os.close(zip_fd)
        zip_path = Path(zip_path_str)
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for img_file in images_dir.iterdir():
                zip_file.write(img_file, arcname=f"images/{img_file.name}")
            for lbl_file in labels_dir.iterdir():
                zip_file.write(lbl_file, arcname=f"labels/{lbl_file.name}")
                
        logger.info(f"YOLO dataset ZIP generated successfully: {zip_path.name}")
        return zip_path
        
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass
