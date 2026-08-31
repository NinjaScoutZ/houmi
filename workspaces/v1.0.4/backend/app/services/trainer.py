from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode
import os
import shutil
import subprocess
import threading
import logging
import time
from pathlib import Path
from sqlalchemy.orm import Session
from app.config import BASE_DIR, DATA_DIR, BALLOON_MODEL_PATH, ACTIVE_LEARNED_MODEL_PATH, PROJECTS_DIR
from app.database import SessionLocal
from app.models.all_models import Page, TextBlock
from app.services.detector import balloon_detector

logger = logging.getLogger("houmi-trainer")

def safe_rmtree(path: Path):
    """Safely delete directories created for training/dataset, preventing path traversal."""
    resolved = path.resolve()
    if resolved.is_relative_to(BASE_DIR.parent) and resolved.name in ["runs", "houmi_training", "dataset"]:
        if resolved.exists():
            logger.info(f"Removing directory safely: {resolved}")
            import stat, time
            def on_error(func, path, exc_info):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    time.sleep(0.1)
                    try:
                        func(path)
                    except Exception:
                        pass
            shutil.rmtree(resolved, onerror=on_error)
    else:
        logger.warning(f"Unsafe directory deletion prevented: {path} (resolved: {resolved})")

class ModelTrainer:
    def __init__(self):
        self.is_training = False
        self.progress_log = []
        self.epoch_total = 10
        self.epoch_current = 0
        self.loss_current = 0.0
        self.eta_seconds = 0
        self.thread = None

    def get_status(self) -> dict:
        return {
            "is_training": self.is_training,
            "epoch_current": self.epoch_current,
            "epoch_total": self.epoch_total,
            "loss_current": self.loss_current,
            "eta_seconds": self.eta_seconds,
            "log": self.progress_log[-5:] if self.progress_log else []
        }

    def _broadcast_status(self):
        try:
            from app.ws_manager import ws_manager
            ws_manager.broadcast_global_sync({
                "type": "train_status",
                "status": self.get_status()
            })
        except Exception as e:
            logger.debug(f"Failed to broadcast training status: {e}")

    def _log_and_broadcast(self, msg: str):
        self.progress_log.append(msg)
        self._broadcast_status()

    def prepare_yolo_dataset(self, db: Session, val_split: float = 0.15) -> Path:
        """Generates YOLO dataset from all pages containing text blocks with train/val split."""
        import random
        dataset_dir = DATA_DIR / "dataset"
        img_train_dir = dataset_dir / "images" / "train"
        lbl_train_dir = dataset_dir / "labels" / "train"
        img_val_dir = dataset_dir / "images" / "val"
        lbl_val_dir = dataset_dir / "labels" / "val"
        
        # Cleanup old dataset
        safe_rmtree(dataset_dir)
            
        img_train_dir.mkdir(parents=True, exist_ok=True)
        lbl_train_dir.mkdir(parents=True, exist_ok=True)
        img_val_dir.mkdir(parents=True, exist_ok=True)
        lbl_val_dir.mkdir(parents=True, exist_ok=True)

        pages = db.query(Page).all()
        logger.info(f"Preparing dataset from {len(pages)} pages...")
        
        # Filter valid pages with text blocks and existing source images
        valid_pages = []
        for page in pages:
            if not page.text_blocks:
                continue
            src_img_path = Path(page.source_image_path)
            if src_img_path.exists():
                valid_pages.append(page)

        # Shuffle deterministically for repeatable split
        random.seed(42)
        random.shuffle(valid_pages)
        
        val_count = int(len(valid_pages) * val_split)
        val_set = set(p.id for p in valid_pages[:val_count])

        import cv2
        for page in valid_pages:
            src_img_path = Path(page.source_image_path)
            is_val = page.id in val_set
            
            target_img_dir = img_val_dir if is_val else img_train_dir
            target_lbl_dir = lbl_val_dir if is_val else lbl_train_dir

            img = cv2_imread_unicode(str(src_img_path))
            if img is None:
                continue

            h, w = img.shape[:2]
            tile_h = min(h, w)
            stride = max(1, int(tile_h * 0.8))

            ys = []
            y = 0
            while True:
                ys.append(y)
                if y + tile_h >= h:
                    break
                y = min(h - tile_h, y + stride)

            for tile_idx, ty in enumerate(ys):
                # Filter blocks that fall inside this tile
                tile_blocks = []
                for b in page.text_blocks:
                    by0, by1 = b.y, b.y + b.height
                    if by0 >= ty and by1 <= ty + tile_h:
                        tile_blocks.append(b)
                    else:
                        overlap_h = max(0, min(by1, ty + tile_h) - max(by0, ty))
                        if overlap_h >= (b.height * 0.5):
                            tile_blocks.append(b)

                if not tile_blocks:
                    continue

                crop_tile = img[ty:ty+tile_h, 0:w]
                tile_filename = f"page_{page.id}_t{tile_idx}{src_img_path.suffix}"
                cv2_imwrite_unicode(str(target_img_dir / tile_filename), crop_tile)

                label_file_path = target_lbl_dir / f"page_{page.id}_t{tile_idx}.txt"
                with label_file_path.open("w", encoding="utf-8") as f:
                    for block in tile_blocks:
                        # Coordinates relative to the crop tile
                        rel_b_y = block.y - ty
                        x_center = max(0.0, min(1.0, (block.x + block.width / 2.0) / w))
                        y_center = max(0.0, min(1.0, (rel_b_y + block.height / 2.0) / tile_h))
                        w_rel = max(0.0, min(1.0, block.width / w))
                        h_rel = max(0.0, min(1.0, block.height / tile_h))

                        class_idx = 0 if block.balloon_type == "bubble" else 1
                        f.write(f"{class_idx} {x_center:.6f} {y_center:.6f} {w_rel:.6f} {h_rel:.6f}\n")

        # Write dataset.yaml configuration file
        yaml_content = f"""
path: {dataset_dir.absolute().as_posix()}
train: images/train
val: images/val

names:
  0: bubble
  1: narrative
"""
        yaml_path = dataset_dir / "dataset.yaml"
        with yaml_path.open("w", encoding="utf-8") as f:
            f.write(yaml_content)

        logger.info(f"Dataset prepared: {len(valid_pages) - len(val_set)} train, {len(val_set)} val pages.")
        return yaml_path

    def _run_training_process(self, yaml_path: Path):
        self.is_training = True
        self.progress_log = ["[INFO] Initiating training workflow..."]
        self.epoch_current = 0
        self.loss_current = 0.0
        self.eta_seconds = 0
        self._broadcast_status()

        # 1. Unload Balloon ONNX model to free up VRAM
        logger.info("Unloading current models from GPU to prevent VRAM allocation conflicts...")
        self._log_and_broadcast("[INFO] Unloading detector models from VRAM...")
        balloon_detector.unload_model()
        time.sleep(3.0)  # Delay recovery to ensure CUDA cache flush

        import sys
        bootstrap_script = DATA_DIR / "yolo_train_bootstrap.py"

        try:
            # 2. Write the bootstrap script to handle PyTorch 2.6+ compatibility and device fallback
            script_content = f"""
import sys
import torch
import os

# Set environment variables to prevent OpenMP duplication crashes and Access Violation on Windows
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
torch.set_num_threads(1)

# PyTorch 2.6+ compatibility for Ultralytics checkpoints
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

# Check device availability
device = "0" if torch.cuda.is_available() else "cpu"
print(f"[BOOTSTRAP] PyTorch CUDA available: {{torch.cuda.is_available()}}. Using device={{device}}", flush=True)

# Run YOLO training
from ultralytics import YOLO
model = YOLO({repr((BASE_DIR.parent / "yolov8n.pt").absolute().as_posix())})
model.train(
    data={repr(yaml_path.absolute().as_posix())},
    epochs={self.epoch_total},
    imgsz=320,
    batch=4,
    device=device,
    workers=0,  # Required on Windows to prevent Access Violation
    project={repr((BASE_DIR / "houmi_training").absolute().as_posix())},
    name="run",
    exist_ok=True,
    plots=False,
    save=True
)

# Export best weights to ONNX format
print("[BOOTSTRAP] Exporting best weights to ONNX format...", flush=True)
from pathlib import Path
best_pt_path = None
train_dir = Path({repr((BASE_DIR / "houmi_training").absolute().as_posix())})
if train_dir.exists():
    for pt in train_dir.rglob("best.pt"):
        best_pt_path = pt
        break

if best_pt_path is None:
    runs_dir = Path({repr((BASE_DIR / "runs").absolute().as_posix())})
    if runs_dir.exists():
        for pt in runs_dir.rglob("best.pt"):
            best_pt_path = pt
            break

if best_pt_path is not None and best_pt_path.exists():
    best_model = YOLO(str(best_pt_path))
    exported_onnx = best_model.export(format="onnx", imgsz=320, opset=18)
    print(f"[BOOTSTRAP] Exported ONNX to: {{exported_onnx}}", flush=True)
    import shutil
    target_path = Path({repr(ACTIVE_LEARNED_MODEL_PATH.absolute().as_posix())})
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(exported_onnx, target_path)
    marker = target_path.with_name("model_train_success.marker")
    marker.write_text("success", encoding="utf-8")
    print(f"[BOOTSTRAP] Successfully copied weights to {{target_path}}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
else:
    print("[BOOTSTRAP] ERROR: best.pt weights not found!", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)
"""
            with open(bootstrap_script, "w", encoding="utf-8") as f:
                f.write(script_content)

            cmd = [
                sys.executable,
                str(bootstrap_script)
            ]
            
            logger.info(f"Executing: {' '.join(cmd)}")
            self._log_and_broadcast("[INFO] Launching PyTorch Training Loop...")
 
            # Run and track logs live
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
 
            # Simple output parser to update UI progress bar
            start_time = time.time()
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                
                line_str = line.strip()
                if not line_str:
                    continue
                    
                self.progress_log.append(line_str)
                # Parse progress e.g., "1/10" (Epoch progress) or "Loss"
                if "epoch" in line_str.lower():
                  # Estimate epoch numbers
                  for part in line_str.split():
                      if "/" in part and len(part) >= 3:
                          try:
                              sub = part.split("/")
                              self.epoch_current = int(sub[0])
                              # Calculate simple linear ETA
                              elapsed = time.time() - start_time
                              progress = self.epoch_current / self.epoch_total
                              if progress > 0:
                                  self.eta_seconds = int((elapsed / progress) - elapsed)
                          except Exception:
                              pass
                if "loss" in line_str.lower():
                    # Parse loss details
                    for part in line_str.split():
                        if part.replace('.', '', 1).isdigit():
                            self.loss_current = float(part)
                
                self._broadcast_status()
 
            process.wait()

            marker_path = ACTIVE_LEARNED_MODEL_PATH.with_name("model_train_success.marker")
            if marker_path.exists():
                try:
                    marker_path.unlink()
                except Exception:
                    pass
                logger.info(f"Model updated successfully at {ACTIVE_LEARNED_MODEL_PATH}")
                self._log_and_broadcast("[SUCCESS] Active learning complete! Model weights saved as Active Learned Model.")
            else:
                raise RuntimeError(f"YOLO Training process failed (exit code: {process.returncode}) and no updated weights were saved.")
 
        except Exception as e:
            logger.error(f"Training workflow failed: {e}")
            self._log_and_broadcast(f"[ERROR] Training failed: {e}")
        finally:
            self.is_training = False
            self._broadcast_status()
            # Clean temporary training folders and bootstrap script
            if bootstrap_script.exists():
                try:
                    bootstrap_script.unlink()
                except Exception:
                    pass
            for temp_run_dir in ["houmi_training", "runs"]:
                safe_rmtree(BASE_DIR / temp_run_dir)

    def start_training(self, epochs: int = 10):
        import sys
        if getattr(sys, "frozen", False):
            logger.error("Fine-tuning is not available in Desktop (.exe) mode.")
            self._log_and_broadcast("[ERROR] Fine-tuning is not available in Desktop (.exe) mode. Please use the development server instead.")
            return
        if self.is_training:
            return
        self.epoch_total = epochs
            
        db = SessionLocal()
        try:
            yaml_path = self.prepare_yolo_dataset(db)
            
            # Start in a daemon thread so it runs in background
            self.thread = threading.Thread(
                target=self._run_training_process,
                args=(yaml_path,),
                daemon=True
            )
            self.thread.start()
        except Exception as e:
            logger.error(f"Failed to start training thread: {e}")
            self.is_training = False
        finally:
            db.close()

# Global trainer instance
model_trainer = ModelTrainer()
