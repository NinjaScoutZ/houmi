"""
Smart Stitch and Slicing Service for Houmi Studio.
Inspired by SmartStitch gutter detection algorithms.

Provides intelligent detection of safe horizontal slice lines in long webtoon strips,
avoiding speech balloons, text characters, and comic panels.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("houmi-smart-stitch")

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def scan_folder_for_oversize(
    folder_path: Union[str, Path],
    threshold_height: int = 20000,
) -> Dict[str, Any]:
    """
    Lightweight header scan of all images in a directory.
    Identifies if any images exceed the maximum recommended height threshold.
    """
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    img_files = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and not f.name.startswith(".")],
        key=lambda f: f.name
    )

    total_images = len(img_files)
    oversize_files: List[Dict[str, Any]] = []
    max_height = 0
    widths: List[int] = []

    for img_file in img_files:
        try:
            # Image.open only reads the file header (does not load uncompressed pixels)
            with Image.open(img_file) as img:
                w, h = img.size
                widths.append(w)
                if h > max_height:
                    max_height = h
                if h > threshold_height:
                    oversize_files.append({
                        "filename": img_file.name,
                        "path": str(img_file),
                        "width": w,
                        "height": h,
                    })
        except Exception as exc:
            logger.warning("Could not read image header for %s: %s", img_file.name, exc)

    has_oversize = len(oversize_files) > 0
    common_width = max(set(widths), key=widths.count) if widths else 720

    return {
        "has_oversize": has_oversize,
        "threshold_height": threshold_height,
        "total_images": total_images,
        "oversize_count": len(oversize_files),
        "max_height": max_height,
        "oversize_files": oversize_files,
        "suggested_split_height": min(5000, threshold_height),
        "suggested_enforce_width": common_width,
    }


def detect_safe_slice_points(
    image: np.ndarray,
    target_height: int = 5000,
    search_window: int = 1500,
    sensitivity: int = 90,
    scan_step: int = 5,
    ignorable_border: int = 5,
) -> List[int]:
    """
    Detect optimal horizontal slice points across a long image canvas.
    Finds clean background gutters (solid white, black, or uniform tone) near target_height intervals.
    """
    img_h, img_w = image.shape[:2]
    if img_h <= target_height:
        return [img_h]

    # Convert to grayscale or 3-channel for energy evaluation
    if len(image.shape) == 2:
        gray = image
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    slice_points: List[int] = []
    current_top = 0

    while current_top + target_height < img_h:
        nominal_cut = current_top + target_height
        search_start = max(current_top + 1000, nominal_cut - search_window // 2)
        search_end = min(img_h - 500, nominal_cut + search_window // 2)

        if search_start >= search_end:
            slice_points.append(min(nominal_cut, img_h))
            current_top = nominal_cut
            continue

        best_y = nominal_cut
        best_score = float("inf")

        # Evaluate gradient variance across candidate rows
        for candidate_y in range(search_start, search_end, scan_step):
            # Take a small horizontal strip (5px height)
            strip = gray[candidate_y : min(img_h, candidate_y + 5), ignorable_border : img_w - ignorable_border]
            if strip.size == 0:
                continue

            # Standard deviation measures pixel variance (edges/drawings/text)
            std_dev = float(np.std(strip))
            
            # Penalize distance from nominal target cut
            dist_penalty = abs(candidate_y - nominal_cut) / float(search_window) * 5.0
            score = std_dev + dist_penalty

            if score < best_score:
                best_score = score
                best_y = candidate_y

        slice_points.append(best_y)
        current_top = best_y

    # Append the final bottom if remaining chunk is non-trivial
    if current_top < img_h:
        slice_points.append(img_h)

    return slice_points


def smart_split_image(
    image_path: Union[str, Path],
    output_dir: Union[str, Path],
    start_index: Optional[int] = None,
    base_prefix: Optional[str] = None,
    target_height: int = 5000,
    search_window: int = 1500,
    sensitivity: int = 90,
    scan_step: int = 5,
    ignorable_border: int = 5,
    enforce_width: Optional[int] = None,
) -> List[Path]:
    """
    Splits a single oversize image file into multiple clean sub-images.
    """
    img_path = Path(image_path).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode
    img = cv2_imread_unicode(img_path)
    if img is None:
        raise ValueError(f"Could not load image: {img_path}")

    h, w = img.shape[:2]
    slice_points = detect_safe_slice_points(
        img,
        target_height=target_height,
        search_window=search_window,
        sensitivity=sensitivity,
        scan_step=scan_step,
        ignorable_border=ignorable_border,
    )

    created_files: List[Path] = []
    prev_y = 0

    for idx, cut_y in enumerate(slice_points):
        if cut_y <= prev_y:
            continue
        
        crop = img[prev_y:cut_y, :]
        prev_y = cut_y

        # Optionally enforce/standardize width
        if enforce_width is not None and enforce_width > 0 and enforce_width != w:
            crop_h, crop_w = crop.shape[:2]
            scale = enforce_width / float(crop_w)
            new_h = max(1, int(round(crop_h * scale)))
            crop = cv2.resize(crop, (enforce_width, new_h), interpolation=cv2.INTER_LANCZOS4)

        if start_index is not None:
            out_name = f"{start_index + idx:02d}.png"
        elif base_prefix is not None:
            out_name = f"{base_prefix}_{idx + 1:02d}.png"
        else:
            out_name = f"{img_path.stem}_{idx + 1:02d}.png"

        out_file = out_dir / out_name
        cv2_imwrite_unicode(out_file, crop)
        created_files.append(out_file)

    return created_files


def smart_split_project_folder(
    folder_path: Union[str, Path],
    split_height: int = 5000,
    enforce_width: Optional[int] = None,
    backup_original: bool = True,
    threshold_height: Optional[int] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Processes all images in a folder, safely backing up originals to _original_raw/
    and splitting oversize images into standard-sized pages permanently on disk and DB.
    """
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    effective_threshold = threshold_height if threshold_height is not None else split_height
    scan = scan_folder_for_oversize(folder, threshold_height=effective_threshold)

    img_files = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and not f.name.startswith(".")],
        key=lambda f: f.name
    )

    if not img_files:
        return {
            "status": "noop",
            "message": "No images found in folder",
            "folder": str(folder),
            "total_pages": 0,
            "output_images_count": 0,
        }

    raw_backup_dir = folder / "_original_raw"
    if backup_original:
        raw_backup_dir.mkdir(parents=True, exist_ok=True)

    temp_split_dir = folder / "_temp_split_staging"
    temp_split_dir.mkdir(parents=True, exist_ok=True)

    from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

    total_sliced_pages = 0
    page_counter = 1

    try:
        for f in img_files:
            with Image.open(f) as pil_img:
                w, h = pil_img.size

            if h > effective_threshold:
                # Slicing needed along gutters
                slices = smart_split_image(
                    image_path=f,
                    output_dir=temp_split_dir,
                    start_index=page_counter,
                    target_height=split_height,
                    enforce_width=enforce_width,
                )
                page_counter += len(slices)
                total_sliced_pages += len(slices)
            else:
                # Image does not need slicing, but may need width resizing
                ext = f.suffix.lower()
                target_name = f"{page_counter:02d}{ext}"
                target_file = temp_split_dir / target_name

                if enforce_width is not None and enforce_width > 0 and enforce_width != w:
                    cv_img = cv2_imread_unicode(f)
                    if cv_img is not None:
                        img_h, img_w = cv_img.shape[:2]
                        scale = enforce_width / float(img_w)
                        new_h = max(1, int(round(img_h * scale)))
                        resized = cv2.resize(cv_img, (enforce_width, new_h), interpolation=cv2.INTER_LANCZOS4)
                        cv2_imwrite_unicode(target_file, resized)
                    else:
                        shutil.copy2(f, target_file)
                else:
                    shutil.copy2(f, target_file)

                page_counter += 1
                total_sliced_pages += 1

            # Move or archive the original
            if backup_original:
                dest = raw_backup_dir / f.name
                shutil.move(str(f), str(dest))
            else:
                f.unlink(missing_ok=True)

        # Move all staged sliced images back to main folder permanently
        for staged in temp_split_dir.iterdir():
            if staged.is_file():
                shutil.move(str(staged), str(folder / staged.name))

        # Re-sync Houmi Studio Project in Database & project.json so changes are 100% permanent
        try:
            from app.database import SessionLocal
            from app.models.all_models import Project, Page, TextBlock
            from app.services.project_serializer import save_project_json
            db = SessionLocal()
            matching_projects = db.query(Project).all()
            for p in matching_projects:
                proj_folder = ""
                if p.settings and isinstance(p.settings, dict):
                    proj_folder = p.settings.get("local_folder", "")
                
                is_match = False
                if project_id and str(p.id) == str(project_id):
                    is_match = True
                elif proj_folder:
                    try:
                        is_match = Path(proj_folder).resolve() == folder.resolve()
                    except Exception:
                        is_match = str(proj_folder).strip().lower() == str(folder).strip().lower()

                if is_match:
                    # Delete obsolete text blocks and pages belonging to the old geometry
                    old_page_ids = [pg.id for pg in db.query(Page).filter(Page.project_id == p.id).all()]
                    if old_page_ids:
                        db.query(TextBlock).filter(TextBlock.page_id.in_(old_page_ids)).delete(synchronize_session=False)
                    db.query(Page).filter(Page.project_id == p.id).delete(synchronize_session=False)
                    db.commit()

                    # Clean stale assets on disk (previews, masks, clean)
                    for sub_dir_name in ("previews", "masks", "clean", "rendered"):
                        sub_dir = folder / sub_dir_name
                        if sub_dir.exists() and sub_dir.is_dir():
                            shutil.rmtree(sub_dir, ignore_errors=True)
                            sub_dir.mkdir(parents=True, exist_ok=True)

                    try:
                        from app.services.memory_cache import page_image_cache
                        page_image_cache.clear()
                    except Exception:
                        pass

                    from app.routes.pages import create_preview_image, create_page_thumbnail
                    from app.services.project_paths import preview_asset_path, thumbnail_asset_path

                    final_files = sorted(
                        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and not f.name.startswith(".")],
                        key=lambda f: f.name
                    )
                    for order_idx, f in enumerate(final_files, start=1):
                        pg_w, pg_h = 720, 1000
                        try:
                            with Image.open(f) as img_check:
                                pg_w, pg_h = img_check.size
                        except Exception:
                            pass
                        new_page = Page(
                            project_id=p.id,
                            page_number=order_idx,
                            name=f.name,
                            width=pg_w,
                            height=pg_h,
                            source_image_path=str(f.resolve()),
                        )
                        db.add(new_page)
                        db.flush()
                        try:
                            create_preview_image(f, output_path=preview_asset_path(new_page))
                            create_page_thumbnail(f, output_path=thumbnail_asset_path(new_page))
                        except Exception as e_prev:
                            logger.warning("Failed to generate preview for page %s: %s", f.name, e_prev)

                    db.commit()
                    save_project_json(p.id, db)
                    logger.info("Synchronized split pages to Project %s in DB and project.json", p.id)
            db.close()
        except Exception as e_sync:
            logger.warning("Project DB sync post-split note: %s", e_sync)

    finally:
        if temp_split_dir.exists():
            shutil.rmtree(temp_split_dir, ignore_errors=True)

    logger.info("Successfully smart-split folder %s into %d pages permanently", folder.name, total_sliced_pages)

    return {
        "status": "success",
        "message": f"Successfully split images into {total_sliced_pages} pages permanently",
        "folder": str(folder),
        "total_original_files": len(img_files),
        "total_pages": total_sliced_pages,
        "output_images_count": total_sliced_pages,
        "backup_directory": str(raw_backup_dir) if backup_original else None,
    }


def smart_stitch_project_folder(
    folder_path: Union[str, Path],
    target_height: int = 18000,
    enforce_width: Optional[int] = None,
    backup_original: bool = True,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stitches / merges multiple short webtoon images in a folder vertically into fewer,
    continuous long strips of `target_height` (e.g. 15,000 - 20,000 px) using gutter detection,
    safely backing up originals to _original_raw/ and synchronizing the project.
    """
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

    img_files = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and not f.name.startswith(".")],
        key=lambda f: f.name
    )

    if not img_files:
        return {
            "status": "noop",
            "message": "No images found in folder",
            "folder": str(folder),
            "total_pages": 0,
            "output_images_count": 0,
        }

    # Determine standard width (either enforced or most common)
    widths = []
    for f in img_files:
        try:
            with Image.open(f) as im:
                widths.append(im.width)
        except Exception:
            pass
    std_w = enforce_width if (enforce_width and enforce_width > 0) else (max(set(widths), key=widths.count) if widths else 720)

    # Load and standardize widths of all images
    loaded_chunks: List[np.ndarray] = []
    for f in img_files:
        cv_img = cv2_imread_unicode(f)
        if cv_img is None:
            continue
        ih, iw = cv_img.shape[:2]
        if iw != std_w:
            scale = std_w / float(iw)
            new_h = max(1, int(round(ih * scale)))
            cv_img = cv2.resize(cv_img, (std_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        loaded_chunks.append(cv_img)

    if not loaded_chunks:
        raise ValueError("Could not decode any images in folder")

    raw_backup_dir = folder / "_original_raw"
    if backup_original:
        raw_backup_dir.mkdir(parents=True, exist_ok=True)

    temp_stitch_dir = folder / "_temp_stitch_staging"
    temp_stitch_dir.mkdir(parents=True, exist_ok=True)

    stitched_page_count = 0

    try:
        # Concatenate in buffer until target height is met, then find safe gutter
        buffer_img: Optional[np.ndarray] = None
        chunk_idx = 0

        while chunk_idx < len(loaded_chunks) or buffer_img is not None:
            # Fill buffer until height reaches target_height
            while (buffer_img is None or buffer_img.shape[0] < target_height) and chunk_idx < len(loaded_chunks):
                next_chunk = loaded_chunks[chunk_idx]
                chunk_idx += 1
                if buffer_img is None:
                    buffer_img = next_chunk
                else:
                    buffer_img = np.vstack([buffer_img, next_chunk])

            if buffer_img is None or buffer_img.size == 0:
                break

            buf_h = buffer_img.shape[0]

            # If remaining buffer is the last piece and within reasonable range, save it as final
            if chunk_idx >= len(loaded_chunks) and buf_h <= target_height + 3000:
                stitched_page_count += 1
                out_name = f"{stitched_page_count:02d}.jpg"
                cv2_imwrite_unicode(temp_stitch_dir / out_name, buffer_img)
                buffer_img = None
                break

            # Find safe slice cut near target_height
            cuts = detect_safe_slice_points(buffer_img, target_height=target_height, search_window=2500)
            cut_y = cuts[0] if cuts else target_height
            cut_y = min(cut_y, buf_h)

            slice_img = buffer_img[:cut_y, :]
            remaining = buffer_img[cut_y:, :] if cut_y < buf_h else None

            stitched_page_count += 1
            out_name = f"{stitched_page_count:02d}.jpg"
            cv2_imwrite_unicode(temp_stitch_dir / out_name, slice_img)

            buffer_img = remaining

        # Backup original files
        for f in img_files:
            if backup_original:
                dest = raw_backup_dir / f.name
                shutil.move(str(f), str(dest))
            else:
                f.unlink(missing_ok=True)

        # Move staged stitched files to main folder
        for staged in temp_stitch_dir.iterdir():
            if staged.is_file():
                shutil.move(str(staged), str(folder / staged.name))

        # Re-sync Houmi Studio Project in Database & project.json
        try:
            from app.database import SessionLocal
            from app.models.all_models import Project, Page, TextBlock
            from app.services.project_serializer import save_project_json
            db = SessionLocal()
            matching_projects = db.query(Project).all()
            for p in matching_projects:
                proj_folder = ""
                if p.settings and isinstance(p.settings, dict):
                    proj_folder = p.settings.get("local_folder", "")

                is_match = False
                if project_id and str(p.id) == str(project_id):
                    is_match = True
                elif proj_folder:
                    try:
                        is_match = Path(proj_folder).resolve() == folder.resolve()
                    except Exception:
                        is_match = str(proj_folder).strip().lower() == str(folder).strip().lower()

                if is_match:
                    old_page_ids = [pg.id for pg in db.query(Page).filter(Page.project_id == p.id).all()]
                    if old_page_ids:
                        db.query(TextBlock).filter(TextBlock.page_id.in_(old_page_ids)).delete(synchronize_session=False)
                    db.query(Page).filter(Page.project_id == p.id).delete(synchronize_session=False)
                    db.commit()

                    # Clean stale assets on disk (previews, masks, clean)
                    for sub_dir_name in ("previews", "masks", "clean", "rendered"):
                        sub_dir = folder / sub_dir_name
                        if sub_dir.exists() and sub_dir.is_dir():
                            shutil.rmtree(sub_dir, ignore_errors=True)
                            sub_dir.mkdir(parents=True, exist_ok=True)

                    try:
                        from app.services.memory_cache import page_image_cache
                        page_image_cache.clear()
                    except Exception:
                        pass

                    from app.routes.pages import create_preview_image, create_page_thumbnail
                    from app.services.project_paths import preview_asset_path, thumbnail_asset_path

                    final_files = sorted(
                        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and not f.name.startswith(".")],
                        key=lambda f: f.name
                    )
                    for order_idx, f in enumerate(final_files, start=1):
                        pg_w, pg_h = std_w, 10000
                        try:
                            with Image.open(f) as img_check:
                                pg_w, pg_h = img_check.size
                        except Exception:
                            pass
                        new_page = Page(
                            project_id=p.id,
                            page_number=order_idx,
                            name=f.name,
                            width=pg_w,
                            height=pg_h,
                            source_image_path=str(f.resolve()),
                        )
                        db.add(new_page)
                        db.flush()
                        try:
                            create_preview_image(f, output_path=preview_asset_path(new_page))
                            create_page_thumbnail(f, output_path=thumbnail_asset_path(new_page))
                        except Exception as e_prev:
                            logger.warning("Failed to generate preview for page %s: %s", f.name, e_prev)

                    db.commit()
                    save_project_json(p.id, db)
                    logger.info("Synchronized stitched pages to Project %s in DB and project.json", p.id)
            db.close()
        except Exception as e_sync:
            logger.warning("Project DB sync post-stitch note: %s", e_sync)

    finally:
        if temp_stitch_dir.exists():
            shutil.rmtree(temp_stitch_dir, ignore_errors=True)

    logger.info("Successfully smart-stitched folder %s into %d pages permanently", folder.name, stitched_page_count)

    return {
        "status": "success",
        "message": f"Successfully stitched images into {stitched_page_count} pages permanently",
        "folder": str(folder),
        "total_original_files": len(img_files),
        "total_pages": stitched_page_count,
        "output_images_count": stitched_page_count,
        "backup_directory": str(raw_backup_dir) if backup_original else None,
    }
