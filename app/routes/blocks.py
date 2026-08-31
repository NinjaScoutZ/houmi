from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import TextBlock, Page, User, Project
from app.schemas.all_schemas import TextBlockCreate, TextBlockUpdate, TextBlockResponse
from app.security.dependencies import ensure_project_access, get_current_user_or_local
from pydantic import BaseModel
from typing import List, Optional

logger = logging.getLogger("houmi-blocks-router")
router = APIRouter(tags=["Text Blocks"])


class BulkBlockUpdateItem(BaseModel):
    block_id: str
    data: TextBlockUpdate


class BulkBlockUpdateRequest(BaseModel):
    updates: List[BulkBlockUpdateItem]


class BalloonLayoutSegmentRequest(BaseModel):
    x0: int
    y0: int
    x1: int
    y1: int


def _apply_block_update(db_block: TextBlock, block_update: TextBlockUpdate) -> None:
    update_data = block_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_block, key, value)

    # TextBlock geometry is the canonical editable text area. Keep the
    # provenance copy synchronized so a later page refresh cannot resurrect an
    # older detector rectangle after the user moves or resizes the layer.
    geometry_fields = {"x", "y", "width", "height"}
    if geometry_fields.intersection(update_data):
        metadata = dict(db_block.extra_metadata or {})
        metadata["text_bbox"] = {
            "x": float(db_block.x),
            "y": float(db_block.y),
            "width": float(db_block.width),
            "height": float(db_block.height),
        }
        layout_region = metadata.get("layout_region")
        if not isinstance(layout_region, dict) or layout_region.get("source") != "manual":
            metadata.pop("layout_region", None)
        db_block.extra_metadata = metadata

    # A direct font-size edit is an explicit user decision. Preserve that
    # intent before rebuilding TypesettingSpec, unless the caller explicitly
    # asked for auto sizing (for example when applying a template or Auto-Fit).
    # This also repairs old UI paths that only sent ``font_size``.
    if "font_size" in update_data:
        incoming_metadata = update_data.get("extra_metadata")
        requested_mode = (
            incoming_metadata.get("font_size_mode")
            if isinstance(incoming_metadata, dict)
            else None
        )
        requested_auto = requested_mode == "auto" or (
            isinstance(incoming_metadata, dict)
            and incoming_metadata.get("auto_font_size") is True
            and requested_mode not in {"manual", "fixed"}
        )
        if not requested_auto:
            metadata = dict(db_block.extra_metadata or {})
            metadata["manual_font_size"] = float(update_data["font_size"])
            metadata["font_size_mode"] = "manual"
            db_block.extra_metadata = metadata

    # When translation is updated, parse semantic tags and apply matching template
    if "translation" in update_data:
        from app.services.semantic_tags import build_tag_map, parse_translation_annotation
        project_settings = db_block.page.project.settings or {} if db_block.page else {}
        tag_map = build_tag_map(project_settings.get("text_templates") or None)
        raw_translation = update_data["translation"] or ""
        annotation = parse_translation_annotation(raw_translation, tag_map)
        metadata = dict(db_block.extra_metadata or {})
        incoming_metadata = update_data.get("extra_metadata")
        if not isinstance(incoming_metadata, dict) or incoming_metadata.get("line_break_source") != "ai_preferred":
            metadata["line_break_source"] = "manual_hard" if "\n" in annotation.text else "manual"
            for ai_key in ("ai_preferred_lines", "ai_layout_hint", "ai_layout_text"):
                metadata.pop(ai_key, None)
            db_block.extra_metadata = metadata
        if annotation.semantic_role:
            db_block.translation = annotation.text  # strip tag from stored text
            metadata = dict(db_block.extra_metadata or {})
            metadata.update({
                "semantic_role": annotation.semantic_role,
                "semantic_role_label": annotation.semantic_label,
                "semantic_role_source": "inline_edit_tag",
                "semantic_role_tag": annotation.semantic_tag,
                "semantic_role_confidence": 1.0,
                "semantic_role_raw_translation": raw_translation,
            })
            db_block.extra_metadata = metadata
            # Apply matching font template
            from app.services.txt_exchange import _apply_semantic_template
            applied_template = _apply_semantic_template(
                db_block, annotation.semantic_role, project_settings
            )
            metadata = dict(db_block.extra_metadata or {})
            metadata["semantic_role_template_id"] = applied_template
            db_block.extra_metadata = metadata

    layout_affecting = {"translation", "source_text", "width", "height", "font_family", "bold", "italic", "balloon_type", "text_direction", "text_align", "font_size", "extra_metadata"}
    if any(key in update_data for key in layout_affecting):
        from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
        try:
            if geometry_fields.intersection(update_data):
                from app.services.layout_region import refresh_block_layout_region
                current_region = (db_block.extra_metadata or {}).get("layout_region")
                if not isinstance(current_region, dict) or current_region.get("source") != "manual":
                    refresh_block_layout_region(db_block)
            spec = compute_block_typesetting(db_block)
            persist_typesetting_spec(db_block, spec)
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(db_block, "extra_metadata")
        except Exception as exc:
            import logging
            logging.getLogger("houmi-blocks").error("Failed to compute typesetting spec on update: %s", exc)

@router.post("/pages/{page_id}/blocks", response_model=TextBlockResponse, status_code=status.HTTP_201_CREATED)
def create_block(
    page_id: str,
    block: TextBlockCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    # 1. Verify page exists
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_id} not found"
        )
    ensure_project_access(page.project, current_user)
        
    # Get last block index to increment
    last_block = db.query(TextBlock).filter(TextBlock.page_id == page_id).order_by(TextBlock.block_index.desc()).first()
    next_index = (last_block.block_index + 1) if last_block else 0
    
    # 2. Create Block
    db_block = TextBlock(
        page_id=page_id,
        block_index=next_index,
        x=block.x,
        y=block.y,
        width=block.width,
        height=block.height,
        rotation_deg=block.rotation_deg,
        source_text=block.source_text,
        translation=block.translation,
        font_family=block.font_family,
        font_size=block.font_size,
        color_hex=block.color_hex,
        bold=block.bold,
        italic=block.italic,
        text_direction=block.text_direction,
        text_align=block.text_align,
        balloon_type=block.balloon_type,
        confidence=1.0,
        extra_metadata={}
    )
    
    db.add(db_block)
    db.flush() # Persist db_block to obtain id for logging
    
    # 3. Auto OCR if enabled in project settings
    project_settings = page.project.settings or {}
    if project_settings.get("auto_ocr", True) and not db_block.source_text:
        try:
            from app.services.ocr import crop_and_ocr_block
            from app.routes.pipeline import clean_ocr_text
            from app.config import get_ocr_engine
            ocr_backend = get_ocr_engine(project_settings)
            ocr_text, success = crop_and_ocr_block(
                page.source_image_path,
                db_block,
                backend=ocr_backend,
                source_lang=page.project.source_lang,
            )
            if success and ocr_text:
                cleaned = clean_ocr_text(ocr_text, page.project.source_lang, project_settings)
                db_block.source_text = cleaned
                if project_settings.get("vertical_to_horizontal", False):
                    db_block.text_direction = "horizontal"
                    
        except Exception as e:
            import logging
            logging.getLogger("houmi-blocks").error(f"Auto OCR failed: {e}")
            
    # Auto-fit font size and compute TypesettingSpec based on final text on create
    from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
    from app.services.layout_region import refresh_block_layout_region
    try:
        refresh_block_layout_region(db_block)
        spec = compute_block_typesetting(db_block)
        persist_typesetting_spec(db_block, spec)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(db_block, "extra_metadata")
    except Exception as e:
        import logging
        logging.getLogger("houmi-blocks").error(f"Failed to compute typesetting spec on create: {e}")

    db.commit()
    db.refresh(db_block)
    return db_block

@router.put("/blocks/bulk", response_model=List[TextBlockResponse])
def update_blocks_bulk(
    request: BulkBlockUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    if not request.updates:
        return []
    ids = [item.block_id for item in request.updates]
    blocks = db.query(TextBlock).filter(TextBlock.id.in_(ids)).all()
    by_id = {block.id: block for block in blocks}
    missing = [block_id for block_id in ids if block_id not in by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"TextBlocks not found: {', '.join(missing)}")
    for block in blocks:
        ensure_project_access(block.page.project if block.page else None, current_user)
    for item in request.updates:
        _apply_block_update(by_id[item.block_id], item.data)
    db.commit()
    ordered = [by_id[item.block_id] for item in request.updates]
    for block in ordered:
        db.refresh(block)
    return ordered


@router.put("/blocks/{block_id}", response_model=TextBlockResponse)
def update_block(
    block_id: str,
    block_update: TextBlockUpdate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not db_block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TextBlock {block_id} not found"
        )
    ensure_project_access(db_block.page.project if db_block.page else None, current_user)
        
    _apply_block_update(db_block, block_update)

    db.commit()
    db.refresh(db_block)

    return db_block


@router.post("/blocks/{block_id}/layout/segment")
def segment_block_balloon_layout(
    block_id: str,
    body: BalloonLayoutSegmentRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Apply an interactive SAM balloon selection as this block's text region."""
    from pathlib import Path

    import cv2
    from sqlalchemy.orm.attributes import flag_modified

    from app.services.balloon_layout import BalloonSegmenterUnavailable, segment_balloon_layout
    from app.services.project_serializer import save_project_json
    from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec

    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text block not found")
    ensure_project_access(block.page.project if block.page else None, current_user)

    source_path = Path(block.page.source_image_path)
    image = cv2_imread_unicode(str(source_path))
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source image not found")
    try:
        region, _mask, _crop_bounds = segment_balloon_layout(
            image, (body.x0, body.y0, body.x1, body.y1), block
        )
    except BalloonSegmenterUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    metadata = dict(block.extra_metadata or {})
    metadata["layout_region"] = region
    metadata["font_size_mode"] = "auto"
    metadata["auto_font_size"] = True
    metadata.pop("manual_font_size", None)
    metadata.pop("typesetting_spec", None)
    block.x = float(region["x"])
    block.y = float(region["y"])
    block.width = float(region["width"])
    block.height = float(region["height"])
    block.extra_metadata = metadata
    spec = compute_block_typesetting(block)
    persist_typesetting_spec(block, spec)
    flag_modified(block, "extra_metadata")
    db.commit()
    db.refresh(block)
    save_project_json(block.page.project_id, db)
    return {
        "status": "success",
        "block_id": str(block.id),
        "layout_region": region,
        "font_size": float(block.font_size),
        "typesetting_spec": (block.extra_metadata or {}).get("typesetting_spec"),
    }

@router.delete("/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(
    block_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not db_block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TextBlock {block_id} not found"
        )
    ensure_project_access(db_block.page.project if db_block.page else None, current_user)
        
    db.delete(db_block)
    db.commit()
    return None


@router.post("/pages/{page_id}/reorder", response_model=List[TextBlockResponse])
def reorder_page_blocks(
    page_id: str,
    direction: str = "rtl",
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Reorder page blocks based on Reading Order (Right-to-Left for Manga or Left-to-Right)."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    ensure_project_access(page.project, current_user)
    
    blocks = page.text_blocks
    if not blocks:
        return []
        
    from app.services.layout_region import sort_blocks_reading_order
    sorted_blocks = sort_blocks_reading_order(blocks, direction=direction)
    
    for idx, db_block in enumerate(sorted_blocks):
        db_block.block_index = idx + 1
        
    db.commit()
    db.refresh(page)
    return page.text_blocks


@router.post("/projects/{project_id}/reorder")
def reorder_project_blocks(
    project_id: str,
    direction: str = "rtl",
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """Reorder blocks based on Reading Order for ALL pages in the project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(project, current_user)
    
    from app.services.layout_region import sort_blocks_reading_order
    
    updated_pages = 0
    total_blocks = 0
    for page in project.pages:
        blocks = page.text_blocks
        if not blocks:
            continue
        sorted_blocks = sort_blocks_reading_order(blocks, direction=direction)
        for idx, db_block in enumerate(sorted_blocks):
            db_block.block_index = idx + 1
        updated_pages += 1
        total_blocks += len(blocks)
        
    db.commit()
    return {
        "status": "success",
        "updated_pages_count": updated_pages,
        "total_blocks_count": total_blocks,
    }


@router.get("/blocks/{block_id}/mask-crop")
@router.get("/blocks/{block_id}/mask")
def get_block_mask_alias(
    block_id: str,
    force_auto: bool = False,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    ensure_project_access(db_block.page.project if db_block and db_block.page else None, current_user)
    from app.routes.pipeline import get_block_mask
    return get_block_mask(block_id=block_id, force_auto=force_auto, db=db)


@router.post("/blocks/{block_id}/mask")
def save_block_mask_alias(
    block_id: str,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    mask: Optional[UploadFile] = File(None),
    reclean: bool = False,
    allow_full_page: bool = True,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    db_block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    ensure_project_access(db_block.page.project if db_block and db_block.page else None, current_user)
    from app.routes.pipeline import save_block_mask
    return save_block_mask(
        block_id=block_id,
        file=file,
        mask=mask,
        reclean=reclean,
        allow_full_page=allow_full_page,
        background_tasks=background_tasks,
        db=db,
    )


@router.post("/blocks/clear-translation")
def clear_blocks_translation(
    page_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    if not page_id and not project_id:
        raise HTTPException(status_code=400, detail="Either page_id or project_id must be provided")

    query = db.query(TextBlock)
    if page_id:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        ensure_project_access(page.project, current_user)
        query = query.filter(TextBlock.page_id == page_id)
    elif project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        ensure_project_access(project, current_user)
        query = query.join(Page).filter(Page.project_id == project_id)

    from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
    for block in query.all():
        block.translation = ""
        if isinstance(block.extra_metadata, dict):
            metadata = dict(block.extra_metadata)
            metadata.pop("typesetting_spec", None)
            metadata.pop("line_break_source", None)
            metadata.pop("ai_preferred_lines", None)
            block.extra_metadata = metadata
        try:
            spec = compute_block_typesetting(block)
            persist_typesetting_spec(block, spec)
        except Exception as e:
            logger.warning(f"Failed to recompute typesetting for block {block.id}: {e}")
    db.commit()
    return {"message": "Successfully cleared translation"}


@router.post("/blocks/clear-all-text")
def clear_blocks_all_text(
    page_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    if not page_id and not project_id:
        raise HTTPException(status_code=400, detail="Either page_id or project_id must be provided")

    query = db.query(TextBlock)
    if page_id:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise HTTPException(status_code=404, detail="Page not found")
        ensure_project_access(page.project, current_user)
        query = query.filter(TextBlock.page_id == page_id)
    elif project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        ensure_project_access(project, current_user)
        query = query.join(Page).filter(Page.project_id == project_id)

    from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec
    for block in query.all():
        block.source_text = ""
        block.translation = ""
        if isinstance(block.extra_metadata, dict):
            metadata = dict(block.extra_metadata)
            metadata.pop("typesetting_spec", None)
            metadata.pop("line_break_source", None)
            metadata.pop("ai_preferred_lines", None)
            block.extra_metadata = metadata
        try:
            spec = compute_block_typesetting(block)
            persist_typesetting_spec(block, spec)
        except Exception as e:
            logger.warning(f"Failed to recompute typesetting for block {block.id}: {e}")
    db.commit()
    return {"message": "Successfully cleared source text and translation"}


@router.delete("/projects/{project_id}/blocks", status_code=status.HTTP_200_OK)
def delete_project_blocks(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    ensure_project_access(project, current_user)
    blocks = db.query(TextBlock).join(Page).filter(Page.project_id == project_id).all()
    count = len(blocks)
    if blocks:
        block_ids = [b.id for b in blocks]
        db.query(TextBlock).filter(TextBlock.id.in_(block_ids)).delete(synchronize_session=False)
        from app.services.project_paths import rendered_asset_path
        for page in project.pages:
            page.rendered_image_path = None
            rendered = rendered_asset_path(page)
            if rendered.exists():
                try:
                    rendered.unlink()
                except Exception as e:
                    logger.warning(f"Failed to unlink rendered asset {rendered}: {e}")
        db.commit()
        from app.services.project_serializer import save_project_json
        save_project_json(project_id, db)
    return {"message": f"Successfully deleted {count} blocks"}


@router.delete("/pages/{page_id}/blocks", status_code=status.HTTP_200_OK)
def delete_page_blocks(
    page_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    ensure_project_access(page.project, current_user)
    count = db.query(TextBlock).filter(TextBlock.page_id == page_id).count()
    db.query(TextBlock).filter(TextBlock.page_id == page_id).delete(synchronize_session=False)
    page.rendered_image_path = None
    from app.services.project_paths import rendered_asset_path
    rendered = rendered_asset_path(page)
    if rendered.exists():
        try:
            rendered.unlink()
        except Exception as e:
            logger.warning(f"Failed to unlink rendered asset {rendered}: {e}")
    db.commit()
    from app.services.project_serializer import save_project_json
    save_project_json(page.project_id, db)
    return {"message": f"Successfully deleted {count} blocks"}

