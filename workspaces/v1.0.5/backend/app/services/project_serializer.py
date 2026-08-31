import json
import shutil
import time
import threading
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.all_models import Project
from app.config import PROJECTS_DIR
from app.services.project_paths import (
    inpaint_preview_asset_path,
    inpainted_asset_path,
    mask_asset_path,
    page_asset_key,
    project_workspace_dir,
    rendered_asset_path,
)
import logging

logger = logging.getLogger("houmi-project-serializer")
_project_serializer_lock = threading.Lock()


def _safe_atomic_json_write(target_path: Path, data: dict, max_retries: int = 6, base_delay: float = 0.05) -> None:
    """Safely writes JSON data to target_path with unique temp file and Windows WinError 32 retry."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f"{target_path.name}.tmp.{int(time.time() * 1000)}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as err:
        logger.error(f"Failed writing temp file {tmp_path}: {err}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    for attempt in range(max_retries):
        try:
            tmp_path.replace(target_path)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(base_delay * (attempt + 1))
            else:
                # Fallback: copy file over and remove temp
                try:
                    shutil.copyfile(str(tmp_path), str(target_path))
                    tmp_path.unlink(missing_ok=True)
                    return
                except Exception as copy_err:
                    logger.error(f"Failed atomic write to {target_path} after {max_retries} attempts: {copy_err}")
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except OSError:
                            pass
                    raise
        except Exception as err:
            logger.error(f"Failed atomic write to {target_path}: {err}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise


def save_project_json(project_id: str, db: Session = None, *, mirror_assets: bool = False) -> None:
    from app.database import SessionLocal
    # Always use an isolated fresh SessionLocal for metadata serialization
    # so caller transaction states (e.g. committed) never cause InvalidRequestError.
    local_db = SessionLocal()
    owns_session = True
    try:
        project = local_db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return
        
        # The selected folder is the project workspace for folder-backed
        # projects.  Keep the original images in place; only metadata and
        # generated assets belong to this workspace.
        project_dir = project_workspace_dir(project)
        
        # Serialize project
        data = {
            "id": project.id,
            "name": project.name,
            "source_lang": project.source_lang,
            "target_lang": project.target_lang,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "settings": project.settings or {},
            "pages": []
        }
        
        for page in project.pages:
            page_data = {
                "id": page.id,
                "page_number": page.page_number,
                "name": page.name,
                "width": page.width,
                "height": page.height,
                "source_image_path": page.source_image_path,
                "inpainted_image_path": page.inpainted_image_path,
                "rendered_image_path": page.rendered_image_path,
                "status": page.status,
                "text_blocks": []
            }
            
            for block in page.text_blocks:
                block_data = {
                    "id": block.id,
                    "block_index": block.block_index,
                    "x": block.x,
                    "y": block.y,
                    "width": block.width,
                    "height": block.height,
                    "rotation_deg": block.rotation_deg,
                    "source_text": block.source_text,
                    "translation": block.translation,
                    "font_family": block.font_family,
                    "font_size": block.font_size,
                    "color_hex": block.color_hex,
                    "bold": block.bold,
                    "italic": block.italic,
                    "text_direction": block.text_direction,
                    "text_align": block.text_align,
                    "balloon_type": block.balloon_type,
                    "confidence": block.confidence,
                    "extra_metadata": block.extra_metadata or {}
                }
                page_data["text_blocks"].append(block_data)
                
            data["pages"].append(page_data)
            
        with _project_serializer_lock:
            # Write to project.json atomically
            json_path = project_dir / "project.json"
            _safe_atomic_json_write(json_path, data)

            workspace_dir = project_workspace_dir(project)
            if workspace_dir.resolve() != project_dir.resolve():
                target_path = workspace_dir / "houmi_project.json"
                _safe_atomic_json_write(target_path, data)

            if mirror_assets:
                # Mirror legacy internal/nested assets into the flat visible layout.
                for page in project.pages:
                    internal_page_dir = Path(page.source_image_path).parent
                    key = page_asset_key(page)
                    old_external_root = workspace_dir
                    pairs = [
                        (internal_page_dir / "clean" / "inpainted.png", inpainted_asset_path(page)),
                        (internal_page_dir / "clean" / "preview_inpainted.jpg", inpaint_preview_asset_path(page)),
                        (internal_page_dir / "rendered" / "rendered.png", rendered_asset_path(page)),
                        (internal_page_dir / "rendered.png", rendered_asset_path(page)),
                        (old_external_root / "clean" / key / "inpainted.png", inpainted_asset_path(page)),
                        (old_external_root / "clean" / key / "preview_inpainted.jpg", inpaint_preview_asset_path(page)),
                        (old_external_root / "rendered" / key / "rendered.png", rendered_asset_path(page)),
                    ]
                    for source_dir in (internal_page_dir / "masks", old_external_root / "masks" / key):
                        if source_dir.exists():
                            for source_file in source_dir.glob("*.png"):
                                name = source_file.name
                                if name.count('_') > 3:
                                    continue
                                pairs.append((source_file, mask_asset_path(page, name)))

                    for source_file, target_file in pairs:
                        try:
                            if not source_file.is_file():
                                continue
                            if source_file.resolve() == target_file.resolve():
                                continue
                            target_file.parent.mkdir(parents=True, exist_ok=True)
                            if not target_file.exists() or source_file.stat().st_mtime > target_file.stat().st_mtime:
                                shutil.copy2(source_file, target_file)
                        except (OSError, FileNotFoundError, Exception) as e:
                            continue

        # Keep a portable annotation snapshot beside every story. It can be
        # converted to YOLO later without depending on the live database.
        training_dir = project_dir / "training"
        training_dir.mkdir(parents=True, exist_ok=True)
        annotations = {
            "schema_version": "1.0.0",
            "project_id": project.id,
            "classes": ["balloon"],
            "pages": [
                {
                    "page_id": page["id"],
                    "image": page["source_image_path"],
                    "width": page["width"],
                    "height": page["height"],
                    "balloons": [
                        {
                            "block_id": block["id"],
                            "bbox": [block["x"], block["y"], block["width"], block["height"]],
                            "type": block["balloon_type"],
                            "confidence": block["confidence"],
                        }
                        for block in page["text_blocks"]
                    ],
                }
                for page in data["pages"]
            ],
        }
        with open(training_dir / "balloons.json", "w", encoding="utf-8") as f:
            json.dump(annotations, f, ensure_ascii=False, indent=2)

        if workspace_dir.resolve() != project_dir.resolve():
            portable_training = workspace_dir / ".houmi" / "training"
            portable_training.mkdir(parents=True, exist_ok=True)
            with open(portable_training / "balloons.json", "w", encoding="utf-8") as f:
                json.dump(annotations, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Saved project metadata to {json_path}")
    except Exception as e:
        logger.exception(f"Failed to save project.json for project {project_id}: {e}")
    finally:
        if owns_session:
            local_db.close()
