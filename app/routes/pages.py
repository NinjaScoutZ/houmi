import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from PIL import Image, ImageOps

from app.database import get_db
from app.config import PROJECTS_DIR
from app.models.all_models import Page, Project, User
from app.schemas.all_schemas import PageResponse
from app.services.inpainter import invalidate_clean_assets, is_clean_asset_current, mark_clean_assets_stale
from app.services.project_paths import inpainted_asset_path, preview_asset_path, thumbnail_asset_path
from app.security.dependencies import ensure_project_access, get_current_user_or_local
from app.services.asset_service import MAX_ASSET_BYTES, validate_asset_payload

router = APIRouter(tags=["Pages"])


def _existing_clean_base_path(page: Page) -> Path | None:
    """Resolve a persisted clean image without requiring fresh provenance."""
    if page.inpainted_image_path:
        persisted = Path(page.inpainted_image_path)
        if persisted.is_file():
            return persisted
    canonical = inpainted_asset_path(page)
    return canonical if canonical.is_file() else None

def get_preview_image_path(source_path: Path) -> Path:
    return source_path.parent / "preview.jpg"

def get_thumbnail_image_path(source_path: Path) -> Path:
    return source_path.parent / "thumbnail.jpg"

def create_page_thumbnail(source_path: Path, width: int = 96, height: int = 128, output_path: Path | None = None) -> Path:
    """Create a tiny, fixed-size navigator thumbnail.

    Canvas previews for long webtoons can decode to tens of millions of pixels;
    reusing them in the page list wastes hundreds of MB per project.
    """
    with Image.open(source_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        thumbnail = ImageOps.fit(
            img,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        thumbnail_path = output_path or get_thumbnail_image_path(source_path)
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail.save(thumbnail_path, "JPEG", quality=76, optimize=True)
        return thumbnail_path

def create_preview_image(source_path: Path, max_width: int = 1200, max_height: int = 100000, output_path: Path | None = None):
    """Downsamples original image for smooth canvas rendering.
    
    For standard manga pages, scales to fit max_width preserving aspect ratio.
    For extremely tall webtoon strips, scales width to max_width and keeps
    the full height (up to max_height) for scrollable canvas rendering.
    """
    with Image.open(source_path) as img:
        # Convert to RGB if palette image (P) or RGBA to avoid issues
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
            
        w, h = img.size
        
        # Scale based on width (preserves readability for both manga and webtoon)
        if w > max_width:
            ratio = max_width / w
            new_w = max_width
            new_h = int(h * ratio)
        else:
            new_w, new_h = w, h
        
        # JPEG limit is 65535. Capping to 60000 for safety, but virtually no webtoon is this tall.
        if new_h > 60000:
            scale_ratio = 60000 / new_h
            new_w = int(new_w * scale_ratio)
            new_h = 60000
            
        if (new_w, new_h) != (w, h):
            preview_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            preview_img = img.copy()
            
        preview_path = output_path or get_preview_image_path(source_path)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_img.save(preview_path, "JPEG", quality=80)
        return preview_path

@router.post("/projects/{project_id}/pages", response_model=PageResponse, status_code=status.HTTP_201_CREATED)
async def upload_page(
    project_id: str,
    page_number: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    # 1. Validate project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found"
        )
    ensure_project_access(project, current_user)
    
    # Generate Page ID
    page_id = str(uuid.uuid4())
    
    # 2. File storage setup
    page_dir = PROJECTS_DIR / project_id / page_id
    page_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine extension and save original
    ext = Path(file.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File extension not supported"
        )
        
    source_file_path = page_dir / f"source{ext}"
    
    try:
        # Read with a hard upper bound, then validate magic bytes and image
        # dimensions before writing untrusted content into project storage.
        payload = await file.read(MAX_ASSET_BYTES + 1)
        validated = validate_asset_payload(
            payload,
            declared_media_type=file.content_type,
            filename=file.filename,
        )
        if len(payload) > MAX_ASSET_BYTES:
            raise ValueError("Uploaded file exceeds the maximum size")
        source_file_path.write_bytes(payload)

        # Get dimensions from the validated payload. PSD is not accepted by
        # this legacy image endpoint, but the shared validator supports it for
        # the future Asset upload API.
        if validated.width is None or validated.height is None:
            with Image.open(source_file_path) as img:
                width, height = img.size
        else:
            width, height = validated.width, validated.height
            
        # Create downsampled preview
        create_preview_image(source_file_path)
        create_page_thumbnail(source_file_path)
        
    except Exception as e:
        # Cleanup folder if save failed
        if page_dir.exists():
            shutil.rmtree(page_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and save image: {e}"
        )
    
    # 3. Write database record
    db_page = Page(
        id=page_id,
        project_id=project_id,
        page_number=page_number,
        name=file.filename,
        width=width,
        height=height,
        source_image_path=str(source_file_path),
        status="pending"
    )
    
    db.add(db_page)
    db.commit()
    db.refresh(db_page)
    return db_page

@router.get("/projects/{project_id}/pages", response_model=List[PageResponse])
def get_project_pages(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    ensure_project_access(project, current_user)
    pages = db.query(Page).filter(Page.project_id == project_id).order_by(Page.page_number).all()
    results = []
    for p in pages:
        p_dump = PageResponse.model_validate(p).model_dump()
        cb = _existing_clean_base_path(p)
        p_dump["inpainted_image_path"] = str(cb) if cb is not None else None
        results.append(p_dump)
    return results

@router.get("/pages/{page_id}", response_model=PageResponse)
def get_page(
    page_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_id} not found"
        )
    ensure_project_access(page.project, current_user)
    payload = PageResponse.model_validate(page).model_dump()
    clean_base = _existing_clean_base_path(page)
    payload["inpainted_image_path"] = str(clean_base) if clean_base is not None else None
    return payload


@router.get("/pages/{page_id}/clean-status")
def get_page_clean_status(
    page_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Check clean readiness without deleting a temporarily stale base image."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Page {page_id} not found")
    ensure_project_access(page.project, current_user)
    clean_base = _existing_clean_base_path(page)
    return {
        "page_id": str(page.id),
        "current": bool(clean_base is not None and is_clean_asset_current(page)),
        "has_clean_base": clean_base is not None,
        "clean_path": str(clean_base) if clean_base is not None else None,
    }


@router.get("/pages/{page_id}/image")
def get_page_image(
    page_id: str,
    clean: bool = False,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Serve a full-resolution image only when the editor explicitly requests it."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Page {page_id} not found")
    ensure_project_access(page.project, current_user)
    if clean:
        path = _existing_clean_base_path(page)
        if path is None or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clean image is unavailable")
    else:
        path = Path(page.source_image_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page image is unavailable")
    return FileResponse(path, media_type="image/png" if path.suffix.lower() == ".png" else None)


@router.get("/pages/{page_id}/preview")
def get_page_preview(
    page_id: str,
    thumbnail: bool = False,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    ensure_project_access(page.project, current_user)
    path = thumbnail_asset_path(page) if thumbnail else preview_asset_path(page)
    if not path.is_file():
        source = Path(page.source_image_path)
        path = get_thumbnail_image_path(source) if thumbnail else get_preview_image_path(source)
    if not path.is_file():
        source = Path(page.source_image_path)
        if source.is_file():
            path = source
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page preview is unavailable")
    return FileResponse(path, media_type="image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png")

@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(
    page_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_id} not found"
        )
    ensure_project_access(page.project, current_user)
        
    # Delete folder and its contents
    page_dir = Path(page.source_image_path).parent
    if page_dir.exists():
        shutil.rmtree(page_dir)
        
    db.delete(page)
    db.commit()
    return None

import base64
from pydantic import BaseModel

class MaskPayload(BaseModel):
    mask_image_base64: str

@router.post("/pages/{page_id}/mask")
def save_page_mask(
    page_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_id} not found"
        )
    ensure_project_access(page.project, current_user)
        
    try:
        # Resolve target manual mask path
        from app.services.project_paths import mask_asset_path
        mask_path = mask_asset_path(page, "manual_mask.png")
        
        img_bytes = file.file.read()
        
        with open(mask_path, "wb") as f:
            f.write(img_bytes)

        mark_clean_assets_stale(page)
        db.commit()
        return {"status": "success", "message": "Manual mask saved; clean output marked stale"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save manual mask: {e}"
        )
