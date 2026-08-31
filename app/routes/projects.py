from fastapi import APIRouter, Body, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
import datetime
import logging
import sys
import time
from pathlib import Path
from app.database import get_db
from app.config import RUNTIME_MODE
from app.models.all_models import Project, User
from app.schemas.all_schemas import ProjectCreate, ProjectResponse
from app.security.dependencies import ensure_project_access, get_current_user_or_local
from app.services.layout_region import (
    TRANSLATION_LAYOUT_POLICY_VERSION,
    migrate_project_translation_layout_policy,
)

router = APIRouter(tags=["Projects"])


def _default_project_settings() -> Dict[str, Any]:
    """Defaults shared by blank and folder-backed projects.

    Client preset settings are layered on top by the caller.  Keeping this in one
    place prevents the two creation flows from silently drifting apart.
    """
    return {
        "remove_spaces": True,
        "auto_ocr": True,
        "auto_remove_line_breaks": True,
        "cleanup_pipeline_profile": "smart_lama",
        "cleanup_mask_strategy": "smart",
        "process_by_text_areas": True,
        "force_lama_inpaint": True,
        "ocr_engine": "ppocrv5",
        "inpaint_engine": "LamaInpaint",
        "execution_provider": "DirectML",
        "project_dictionary": [],
        "default_image_inpaint_method": "LamaInpaint",
        "lock_translation_to_detected_box": False,
        # Experimental contour-aware line fitting stays opt-in until a
        # story-separated benchmark confirms it beats the ellipse fallback.
        "enable_contour_layout": False,
        "enable_smart_balloon": False,
        "expand_after_balloon_detection": False,
        "translation_layout_policy_version": TRANSLATION_LAYOUT_POLICY_VERSION,
    }


def _matches_folder_workspace(project: Project, folder_path: str) -> bool:
    """Reuse existing project if local_folder matches the selected folder."""
    settings = project.settings or {}
    stored_folder = settings.get("local_folder")
    if not stored_folder:
        return False
    try:
        same_folder = Path(str(stored_folder)).resolve() == Path(folder_path).resolve()
    except OSError:
        same_folder = str(stored_folder) == folder_path
    if same_folder:
        return True

    manifest = Path(folder_path) / "project.json"
    if manifest.is_file():
        try:
            import json
            saved_id = str(json.loads(manifest.read_text(encoding="utf-8")).get("id") or "")
            if saved_id and saved_id == str(project.id):
                return True
        except (OSError, ValueError, TypeError):
            pass
    return False

@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_project = Project(
        name=project.name,
        source_lang=project.source_lang,
        target_lang=project.target_lang,
        owner_id=current_user.id if current_user else None,
        settings={**_default_project_settings(), **(project.settings or {})}
    )
    db.add(db_project)
    import time
    for _retry in range(5):
        try:
            db.commit()
            break
        except Exception as _db_err:
            if "locked" in str(_db_err).lower() and _retry < 4:
                time.sleep(0.3)
            else:
                raise
    db.refresh(db_project)
    return db_project

def _ask_folder_dialog(title: str = "เลือกโฟลเดอร์", initialdir: Optional[str] = None) -> Optional[str]:
    # 1. Native Modern Windows Explorer Dialog (IFileOpenDialog) / Tkinter
    try:
        from app.services.folder_dialog import ask_modern_folder_dialog
        res = ask_modern_folder_dialog(title=title, initialdir=initialdir)
        if res and Path(res).is_dir():
            return res
    except Exception as exc:
        logging.getLogger("houmi-projects").warning("Modern folder dialog failed: %s", exc)

    # 2. Try PyWebView native dialog if running inside desktop webview
    try:
        import webview
        if webview.windows and len(webview.windows) > 0:
            res = webview.windows[0].create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=initialdir or ""
            )
            if res and len(res) > 0:
                return res[0]
            if res is not None:
                return None
    except Exception as exc:
        logging.getLogger("houmi-projects").debug("PyWebView dialog unavailable: %s", exc)

    # 3. Fallback to Tkinter native dialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder_path = filedialog.askdirectory(
            title=title,
            initialdir=initialdir if initialdir else None
        )
        root.destroy()
        if folder_path:
            return folder_path
    except Exception as exc:
        logging.getLogger("houmi-projects").error("Tkinter dialog failed: %s", exc)

    return None

def _restore_project_from_manifest(manifest: dict, db_project: Project, folder: Path, db: Session) -> bool:
    """Restore pages, text blocks, and settings from project.json manifest when opening a portable project folder."""
    import uuid
    from PIL import Image
    from app.models.all_models import Page, TextBlock
    from app.routes.pages import create_preview_image, create_page_thumbnail
    from app.services.project_paths import preview_asset_path, thumbnail_asset_path

    manifest_pages = manifest.get("pages") or []
    if not manifest_pages:
        return False

    if manifest.get("settings") and isinstance(manifest["settings"], dict):
        merged_settings = {**db_project.settings, **manifest["settings"], "local_folder": str(folder)}
        db_project.settings = merged_settings

    if manifest.get("name"):
        db_project.name = manifest["name"]
    if manifest.get("source_lang"):
        db_project.source_lang = manifest["source_lang"]
    if manifest.get("target_lang"):
        db_project.target_lang = manifest["target_lang"]

    for idx, page_data in enumerate(manifest_pages):
        page_name = page_data.get("name")
        img_file = (folder / page_name) if page_name else None
        if not img_file or not img_file.is_file():
            img_files = sorted(
                [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}],
                key=lambda f: f.name
            )
            if idx < len(img_files):
                img_file = img_files[idx]
            else:
                continue

        raw_page_id = page_data.get("id")
        page_id = str(raw_page_id) if (raw_page_id and not db.query(Page).filter(Page.id == str(raw_page_id)).first()) else str(uuid.uuid4())
        w = page_data.get("width")
        h = page_data.get("height")
        if not w or not h:
            try:
                with Image.open(img_file) as img:
                    w, h = img.size
            except Exception:
                w, h = 800, 600

        inpainted_path = page_data.get("inpainted_image_path")
        if inpainted_path and not Path(inpainted_path).is_file():
            rel_clean = folder / "clean" / f"{idx+1:02d}_inpaint.png"
            inpainted_path = str(rel_clean) if rel_clean.is_file() else None

        db_page = Page(
            id=page_id,
            project_id=db_project.id,
            page_number=page_data.get("page_number", idx + 1),
            name=img_file.name,
            width=w,
            height=h,
            source_image_path=str(img_file),
            inpainted_image_path=inpainted_path,
            rendered_image_path=page_data.get("rendered_image_path"),
            status=page_data.get("status", "pending")
        )
        db.add(db_page)
        db.flush()

        try:
            create_preview_image(img_file, output_path=preview_asset_path(db_page))
            create_page_thumbnail(img_file, output_path=thumbnail_asset_path(db_page))
        except Exception:
            pass

        for block_data in page_data.get("text_blocks") or []:
            raw_block_id = block_data.get("id")
            block_id = str(raw_block_id) if (raw_block_id and not db.query(TextBlock).filter(TextBlock.id == str(raw_block_id)).first()) else str(uuid.uuid4())
            db_block = TextBlock(
                id=block_id,
                page_id=db_page.id,
                block_index=block_data.get("block_index", 1),
                x=float(block_data.get("x", 0)),
                y=float(block_data.get("y", 0)),
                width=float(block_data.get("width", 100)),
                height=float(block_data.get("height", 50)),
                rotation_deg=float(block_data.get("rotation_deg", 0)),
                source_text=str(block_data.get("source_text", "")),
                translation=str(block_data.get("translation", "")),
                font_family=str(block_data.get("font_family", "NotoSansThai")),
                font_size=float(block_data.get("font_size", 20.0)),
                color_hex=str(block_data.get("color_hex", "#000000")),
                bold=bool(block_data.get("bold", False)),
                italic=bool(block_data.get("italic", False)),
                text_direction=str(block_data.get("text_direction", "horizontal")),
                text_align=str(block_data.get("text_align", "center")),
                balloon_type=str(block_data.get("balloon_type", "bubble")),
                confidence=float(block_data.get("confidence", 1.0)),
                extra_metadata=block_data.get("extra_metadata") or {},
                smart_x=block_data.get("smart_x"),
                smart_y=block_data.get("smart_y"),
                smart_width=block_data.get("smart_width"),
                smart_height=block_data.get("smart_height"),
            )
            db.add(db_block)

    db.commit()
    db.refresh(db_project)
    return True


@router.post("/projects/browse-folder")
def browse_folder_project(
    default_load_path: Optional[str] = None,
    folder_path: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    if RUNTIME_MODE != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Native folder browsing is available only in Local Mode",
        )
    import uuid
    from PIL import Image
    from app.models.all_models import Page, Project
    from app.routes.pages import create_preview_image
    from app.services.project_paths import preview_asset_path, thumbnail_asset_path, load_project_json
    # 1. Obtain folder path (from explicit parameter or native GUI dialog)
    if not folder_path:
        folder_path = _ask_folder_dialog(
            title="เลือกโฟลเดอร์รูปภาพของโปรเจกต์",
            initialdir=default_load_path
        )

    if not folder_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No folder selected"
        )

    folder_path_normalized = str(Path(folder_path).resolve())
    folder = Path(folder_path_normalized)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"โฟลเดอร์ไม่ถูกต้องหรือหาไม่พบ: {folder_path_normalized}"
        )

    # 2. Check if project already exists for this folder (unless force_fresh is requested)
    force_fresh = bool(settings and settings.get("force_fresh"))
    projects_query = db.query(Project)
    if current_user is not None and hasattr(current_user, "id"):
        projects_query = projects_query.filter(Project.owner_id == current_user.id)
    projects = projects_query.all()
    matching_projects = [
        project for project in projects
        if _matches_folder_workspace(project, folder_path_normalized)
    ]

    if matching_projects:
        if not force_fresh:
            p = min(
                matching_projects,
                key=lambda project: project.created_at.timestamp() if project.created_at else float("inf"),
            )
            return ProjectResponse.model_validate(p).model_dump()
        else:
            # Clean up old project entities before force fresh re-import
            for old_p in matching_projects:
                db.delete(old_p)
            db.commit()
    valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    img_files = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith(".")],
        key=lambda f: f.name
    )

    if not img_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="โฟลเดอร์นี้ไม่มีรูปภาพที่รองรับ (.png, .jpg, .jpeg, .webp, .bmp)"
        )

    # Check for oversize images (> 20,000 px) before committing to DB
    allow_oversize = bool(settings and (settings.get("allow_oversize") or settings.get("confirm_oversize")))
    if not allow_oversize:
        manifest_check = load_project_json(folder)
        has_established_manifest = manifest_check and bool(manifest_check.get("pages"))
        if not has_established_manifest:
            from app.services.smart_stitch import scan_folder_for_oversize
            scan = scan_folder_for_oversize(folder, threshold_height=20000)
            if scan["has_oversize"]:
                return {
                    "status": "oversize_warning",
                    "folder_path": folder_path_normalized,
                    "scan_report": scan,
                }

    # 4. Create new Project
    project_name = folder.name
    base_name = project_name
    counter = 1
    while db.query(Project).filter(Project.name == project_name).first() is not None:
        project_name = f"{base_name} ({counter})"
        counter += 1

    chosen_source_lang = str((settings.get("source_lang") if settings else None) or "ko").strip() or "ko"
    db_project = Project(
        name=project_name,
        source_lang=chosen_source_lang,
        target_lang="th",
        owner_id=current_user.id if current_user else None,
        settings={
            **_default_project_settings(),
            "local_folder": folder_path_normalized,
            "source_lang": chosen_source_lang,
            **(settings or {}),
        }
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)

    # Check for existing portable project.json manifest and restore pages + text blocks
    manifest = load_project_json(folder)
    if manifest and manifest.get("pages"):
        has_blocks = any(p.get("text_blocks") for p in manifest.get("pages", []))
        if has_blocks or not force_fresh:
            if _restore_project_from_manifest(manifest, db_project, folder, db):
                from app.services.project_serializer import save_project_json
                save_project_json(str(db_project.id))
                return ProjectResponse.model_validate(db_project).model_dump()

    # 5. Import all pages (fresh project fallback)
    for idx, img_file in enumerate(img_files):
        page_id = str(uuid.uuid4())
        try:
            # Get dimensions
            with Image.open(img_file) as img:
                w, h = img.size

            # Save Page to DB
            db_page = Page(
                id=page_id,
                project_id=db_project.id,
                page_number=idx + 1,
                name=img_file.name,
                width=w,
                height=h,
                source_image_path=str(img_file),
                status="pending"
            )
            db.add(db_page)
            db.flush()
            create_preview_image(img_file, output_path=preview_asset_path(db_page))
            from app.routes.pages import create_page_thumbnail
            create_page_thumbnail(img_file, output_path=thumbnail_asset_path(db_page))
        except Exception as e:
            db.delete(db_project)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"ล้มเหลวขณะนำเข้ารูปภาพ {img_file.name}: {e}"
            )

    db.commit()
    db.refresh(db_project)
    from app.services.project_serializer import save_project_json
    save_project_json(str(db_project.id))

    # Do not run auto batch pipeline automatically on import folder
    pass

    return ProjectResponse.model_validate(db_project).model_dump()

@router.get("/projects", response_model=List[ProjectResponse])
def get_projects(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    from app.services.project_paths import project_workspace_dir, uses_external_workspace
    query = db.query(Project)
    if current_user is not None and current_user.role != "admin":
        query = query.filter(Project.owner_id == current_user.id)
    projects = query.order_by(Project.updated_at.desc()).all()

    valid_projects = []
    for p in projects:
        p_dir = project_workspace_dir(p)
        workspace_state_removed = (
            uses_external_workspace(p) and not (p_dir / "project.json").is_file()
        )
        if not p_dir.exists() or workspace_state_removed:
            logging.getLogger("houmi-projects").info(
                "Project workspace state removed: %s (%s). Purging stale DB record...",
                p.name,
                p.id,
            )
            try:
                db.delete(p)
                db.commit()
            except Exception:
                db.rollback()
        else:
            valid_projects.append(p)

    return valid_projects

@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_project = db.query(Project).filter(Project.id == project_id).first()
    ensure_project_access(db_project, current_user)
    migrated_blocks = migrate_project_translation_layout_policy(db_project)
    if migrated_blocks:
        from app.services.project_serializer import save_project_json

        db.flush()
        logger_message = (
            f"Migrated {migrated_blocks} translated layouts to balloon interiors "
            f"for project {project_id}"
        )
        import logging
        logging.getLogger("houmi-projects").info(logger_message)
        db_project.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(db_project)
        save_project_json(project_id, db)
    return db_project

@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    import shutil
    from pathlib import Path
    from app.config import PROJECTS_DIR
    from app.models.all_models import Page

    db_project = db.query(Project).filter(Project.id == project_id).first()
    ensure_project_access(db_project, current_user)

    from app.services.memory_cache import page_image_cache
    from app.services.project_paths import project_workspace_dir, uses_external_workspace
    page_image_cache.clear()
    try:
        from app.services.inpainter import _adaptive_mask_cache
        _adaptive_mask_cache.clear()
    except Exception:
        pass
    try:
        import cv2
        cv2.destroyAllWindows()
    except Exception:
        pass

    dirs_to_remove: set[Path] = set()

    # 1. Canonical internal storage.  Folder-backed projects own generated
    # artifacts inside the user-selected source folder, never the source images.
    canonical_dir = PROJECTS_DIR / project_id
    if canonical_dir.exists():
        dirs_to_remove.add(canonical_dir)
    ws_dir = project_workspace_dir(db_project)
    is_folder_backed = uses_external_workspace(db_project)
    if not is_folder_backed and ws_dir.exists():
        dirs_to_remove.add(ws_dir)

    # 2. Per-page source_image_path parent directories
    #    (pages may have been stored in a different base dir historically)
    pages = db.query(Page).filter(Page.project_id == project_id).all()
    for page in pages:
        if page.source_image_path and not is_folder_backed:
            page_dir = Path(page.source_image_path).parent
            # Walk up to the project-level dir (parent of page UUID dir)
            if page_dir.parent.name == project_id:
                dirs_to_remove.add(page_dir.parent)
            elif page_dir.exists():
                dirs_to_remove.add(page_dir)

    # 3. Delete DB records (cascade removes pages + text_blocks)
    db.delete(db_project)
    db.commit()

    # 4. Remove generated artifacts only for folder-backed projects.  Original
    # images remain in place so deleting a Houmi project cannot destroy work.
    if is_folder_backed:
        for name in ("masks", "clean", "rendered", "previews", "training", ".houmi"):
            generated_dir = ws_dir / name
            if generated_dir.exists():
                dirs_to_remove.add(generated_dir)
        try:
            (ws_dir / "project.json").unlink(missing_ok=True)
        except OSError:
            pass

    # 5. Remove disk folders
    for folder in dirs_to_remove:
        try:
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            pass  # Best-effort cleanup; don't fail the API call

    return None


@router.post("/projects/garbage-collect")
def garbage_collect_projects(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Remove orphaned project folders from disk that no longer have DB records."""
    import shutil
    from pathlib import Path
    from app.config import PROJECTS_DIR

    if current_user is not None and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator permission required")

    # Get all valid project IDs
    valid_ids = {row[0] for row in db.execute(
        db.query(Project.id).statement
    ).fetchall()}

    removed_count = 0
    removed_bytes = 0

    if not PROJECTS_DIR.exists():
        return {"removed_count": 0, "removed_bytes": 0, "removed_mb": 0.0}

    for folder in PROJECTS_DIR.iterdir():
        if not folder.is_dir():
            continue
        if folder.name not in valid_ids:
            try:
                folder_size = sum(
                    f.stat().st_size for f in folder.rglob("*") if f.is_file()
                )
                shutil.rmtree(folder, ignore_errors=True)
                removed_count += 1
                removed_bytes += folder_size
            except Exception:
                pass

    return {
        "removed_count": removed_count,
        "removed_bytes": removed_bytes,
        "removed_mb": round(removed_bytes / (1024 * 1024), 1),
    }

from pydantic import BaseModel
from typing import Dict, Any, Optional

class ProjectUpdate(BaseModel):
    settings: Dict[str, Any]
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None

@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_project = db.query(Project).filter(Project.id == project_id).first()
    ensure_project_access(db_project, current_user)
    # Merge existing settings with new ones
    current_settings = db_project.settings or {}
    merged_settings = {**current_settings, **project_update.settings}
    if "lock_translation_to_detected_box" in project_update.settings:
        merged_settings["translation_layout_policy_version"] = TRANSLATION_LAYOUT_POLICY_VERSION
    db_project.settings = merged_settings
    if project_update.source_lang is not None:
        db_project.source_lang = project_update.source_lang
    if project_update.target_lang is not None:
        db_project.target_lang = project_update.target_lang
    db.commit()
    db.refresh(db_project)
    try:
        from app.services.project_serializer import save_project_json
        save_project_json(db_project.id, db=db)
    except Exception as exc:
        print(f"Failed to save project metadata to project.json: {exc}")
    return db_project

class BrowseFolderResponse(BaseModel):
    success: bool
    path: Optional[str] = None
    error: Optional[str] = None

@router.post("/utils/browse-folder", response_model=BrowseFolderResponse)
def browse_folder(
    default_directory: Optional[str] = None,
    current_user: User | None = Depends(get_current_user_or_local),
):
    if RUNTIME_MODE != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Native folder browsing is available only in Local Mode",
        )
    folder_path = _ask_folder_dialog(title="เลือกโฟลเดอร์", initialdir=default_directory)
    if not folder_path:
        return {"success": False, "error": "No folder selected"}
    return {"success": True, "path": str(Path(folder_path).resolve())}


@router.post("/projects/check-oversize")
def check_folder_oversize_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Scan a local directory for oversize webtoon images without importing."""
    folder_path = payload.get("folder_path")
    if not folder_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing folder_path")
    threshold = int(payload.get("threshold_height", 20000))
    from app.services.smart_stitch import scan_folder_for_oversize
    try:
        report = scan_folder_for_oversize(folder_path, threshold_height=threshold)
        return report
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/projects/smart-split")
def smart_split_folder_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Execute smart webtoon splitting with gutter detection on a folder."""
    folder_path = payload.get("folder_path")
    if not folder_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing folder_path")
    project_id = payload.get("project_id")
    split_height = int(payload.get("split_height", 5000))
    enforce_width = payload.get("enforce_width")
    if enforce_width is not None and str(enforce_width).strip() and str(enforce_width) != "0":
        enforce_width = int(enforce_width)
    else:
        enforce_width = None
    backup_original = bool(payload.get("backup_original", True))
    threshold_height = payload.get("threshold_height")
    if threshold_height is not None and str(threshold_height).strip():
        threshold_height = int(threshold_height)
    else:
        threshold_height = None

    from app.services.smart_stitch import smart_split_project_folder
    try:
        result = smart_split_project_folder(
            folder_path=folder_path,
            split_height=split_height,
            enforce_width=enforce_width,
            backup_original=backup_original,
            threshold_height=threshold_height,
            project_id=project_id,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/projects/smart-stitch")
def smart_stitch_folder_endpoint(
    payload: Dict[str, Any] = Body(...),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Execute smart webtoon stitching / vertical merging with gutter detection on a folder."""
    folder_path = payload.get("folder_path")
    if not folder_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing folder_path")
    project_id = payload.get("project_id")
    target_height = int(payload.get("target_height", payload.get("split_height", 18000)))
    enforce_width = payload.get("enforce_width")
    if enforce_width is not None and str(enforce_width).strip() and str(enforce_width) != "0":
        enforce_width = int(enforce_width)
    else:
        enforce_width = None
    backup_original = bool(payload.get("backup_original", True))

    from app.services.smart_stitch import smart_stitch_project_folder
    try:
        result = smart_stitch_project_folder(
            folder_path=folder_path,
            target_height=target_height,
            enforce_width=enforce_width,
            backup_original=backup_original,
            project_id=project_id,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

