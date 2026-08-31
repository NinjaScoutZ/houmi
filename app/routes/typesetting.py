from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.database import get_db
from app.models.all_models import TextBlock, Page
from app.services.typesetting import (
    compute_block_typesetting,
    persist_typesetting_spec,
    get_effective_typesetting_spec,
    validate_typesetting_spec,
    log_typesetting_decision,
    build_typesetting_decision_event,
    LAYOUT_ENGINE_VERSION,
    judge_style,
    apply_style_descriptor_to_block,
)
from app.services.typesetting.schemas import TypesettingSpec
from app.services.project_serializer import save_project_json
from app.services.layout_region import refresh_block_layout_regions
from sqlalchemy.orm.attributes import flag_modified
from app.security.dependencies import get_current_user_or_local, require_resource_access

router = APIRouter(
    prefix="/typesetting",
    tags=["Typesetting"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)

class RecomputeBlocksRequest(BaseModel):
    block_ids: List[str]

class PreflightRequest(BaseModel):
    block_id: str
    translation: Optional[str] = None
    font_family: Optional[str] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    text_align: Optional[str] = None
    text_direction: Optional[str] = None
    balloon_type: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None
    font_size: Optional[float] = None

class FeedbackEventRequest(BaseModel):
    """User correction / accept event (Phase 0 instrumentation)."""
    block_id: str
    suggested_template: Optional[str] = None
    selected_template: Optional[str] = None
    suggested_lines: Optional[List[str]] = None
    final_lines: Optional[List[str]] = None
    change_reason: str = "user_preference"  # accepted | system_wrong | user_preference
    decision_status: Optional[str] = None
    font_fingerprint: Optional[str] = None
    spec_revision: Optional[int] = None
    project_id: Optional[str] = None
    page_id: Optional[str] = None


class StyleJudgeRequest(BaseModel):
    block_ids: Optional[List[str]] = None
    page_id: Optional[str] = None
    # Default suggest-only until Gate 2 calibration / held-out precision is proven
    apply_template: bool = False
    confidence_auto_threshold: float = 0.90
    recompute_layout: bool = True

def _sync_manual_font_size(block: TextBlock) -> None:
    """Repair legacy rows that retained an auto-fitted size beside a manual size."""
    manual_font_size = (block.extra_metadata or {}).get("manual_font_size")
    if manual_font_size is not None:
        block.font_size = max(6.0, float(manual_font_size))

@router.post("/recompute/block/{block_id}", response_model=TypesettingSpec)
def recompute_single_block(block_id: str, db: Session = Depends(get_db)):
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Block {block_id} not found")
        
    _sync_manual_font_size(block)
    refresh_block_layout_regions([block])
    spec = compute_block_typesetting(block)
    
    # Save to extra_metadata
    persist_typesetting_spec(block, spec)
    
    # SQLAlchemy JSON column mutation tracking helper
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(block, "extra_metadata")
    
    db.commit()
    
    # Trigger project.json serialization
    save_project_json(block.page.project_id, db)
    
    return spec

@router.post("/recompute/blocks", response_model=List[TypesettingSpec])
def recompute_multiple_blocks(req: RecomputeBlocksRequest, db: Session = Depends(get_db)):
    specs = []
    affected_projects = set()
    for bid in req.block_ids:
        block = db.query(TextBlock).filter(TextBlock.id == bid).first()
        if not block:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Block {bid} not found")
        if block.page and block.page.project_id:
            affected_projects.add(block.page.project_id)
        _sync_manual_font_size(block)
        refresh_block_layout_regions([block])
        spec = compute_block_typesetting(block)
        persist_typesetting_spec(block, spec)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(block, "extra_metadata")
        specs.append(spec)
        
    if specs:
        db.commit()
        for pid in affected_projects:
            save_project_json(pid, db)
            
    return specs

@router.post("/recompute/page/{page_id}", response_model=List[TypesettingSpec])
def recompute_page_blocks(page_id: str, db: Session = Depends(get_db)):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Page {page_id} not found")
        
    # Refresh the safe balloon interior as well. Old specs may have been built
    # from an oversized OCR box rather than the actual balloon bounds.
    refresh_block_layout_regions(list(page.text_blocks))
    specs = []
    for block in page.text_blocks:
        _sync_manual_font_size(block)
        spec = compute_block_typesetting(block)
        persist_typesetting_spec(block, spec)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(block, "extra_metadata")
        specs.append(spec)
        
    db.commit()
    save_project_json(page.project_id, db)
    return specs

@router.post("/preflight", response_model=TypesettingSpec)
def preflight_layout(req: PreflightRequest, db: Session = Depends(get_db)):
    block = db.query(TextBlock).filter(TextBlock.id == req.block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Block {req.block_id} not found")
        
    # Create a transient block copy to compute without mutating database.
    # Width/height preflight overrides target the translated layout region.
    temp_metadata = dict(block.extra_metadata) if block.extra_metadata else {}
    if isinstance(temp_metadata.get("layout_region"), dict) and (req.width is not None or req.height is not None):
        temp_metadata["layout_region"] = {
            **temp_metadata["layout_region"],
            "width": req.width if req.width is not None else temp_metadata["layout_region"].get("width", block.width),
            "height": req.height if req.height is not None else temp_metadata["layout_region"].get("height", block.height),
            "source": "manual",
            "confidence": 1.0,
        }
    temp_block = TextBlock(
        id=block.id,
        page_id=block.page_id,
        block_index=block.block_index,
        x=block.x,
        y=block.y,
        width=req.width if req.width is not None else block.width,
        height=req.height if req.height is not None else block.height,
        rotation_deg=block.rotation_deg,
        source_text=block.source_text,
        translation=req.translation if req.translation is not None else block.translation,
        font_family=req.font_family if req.font_family is not None else block.font_family,
        font_size=req.font_size if req.font_size is not None else block.font_size,
        color_hex=block.color_hex,
        bold=req.bold if req.bold is not None else block.bold,
        italic=req.italic if req.italic is not None else block.italic,
        text_direction=req.text_direction if req.text_direction is not None else block.text_direction,
        text_align=req.text_align if req.text_align is not None else block.text_align,
        balloon_type=req.balloon_type if req.balloon_type is not None else block.balloon_type,
        extra_metadata=temp_metadata
    )
    # Temporary bind block relations if needed by registry
    temp_block.page = block.page
    
    # Preflight must not pollute feedback logs
    spec = compute_block_typesetting(temp_block, log_feedback=False)
    # Mark preflight spec as manual or imported if requested fields are present, else auto
    spec.layout_source = "auto"
    return spec


@router.post("/style-judge")
def run_style_judge(req: StyleJudgeRequest, db: Session = Depends(get_db)):
    """
    Style Judge v1 (rule-based): multi-signal descriptor → optional template apply.
    High-confidence only auto-applies template; low-confidence stays suggested_only.
    """
    blocks: List[TextBlock] = []
    if req.page_id:
        page = db.query(Page).filter(Page.id == req.page_id).first()
        if not page:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Page {req.page_id} not found")
        blocks = list(page.text_blocks)
    elif req.block_ids:
        for bid in req.block_ids:
            block = db.query(TextBlock).filter(TextBlock.id == bid).first()
            if not block:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Block {bid} not found")
            blocks.append(block)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="page_id or block_ids required")

    results = []
    affected_projects = set()
    for block in blocks:
        project_settings = {}
        page_h = None
        if block.page is not None:
            page_h = float(block.page.height or 0) or None
            if block.page.project is not None:
                project_settings = block.page.project.settings or {}
                affected_projects.add(block.page.project_id)

        descriptor = judge_style(block, project_settings=project_settings, page_height=page_h)
        summary = apply_style_descriptor_to_block(
            block,
            descriptor,
            project_settings=project_settings,
            apply_template=req.apply_template,
            confidence_auto_threshold=req.confidence_auto_threshold,
        )
        flag_modified(block, "extra_metadata")

        spec_dump = None
        if req.recompute_layout:
            _sync_manual_font_size(block)
            spec = compute_block_typesetting(block)
            persist_typesetting_spec(block, spec)
            flag_modified(block, "extra_metadata")
            spec_dump = spec.model_dump()

        results.append(
            {
                "block_id": block.id,
                "style": summary,
                "typesetting_spec": spec_dump,
            }
        )

    if results:
        db.commit()
        for pid in affected_projects:
            if pid:
                save_project_json(pid, db)
    return {"count": len(results), "results": results}


@router.post("/feedback")
def record_typesetting_feedback(req: FeedbackEventRequest, db: Session = Depends(get_db)):
    """
    Persist a user accept/reject/override event for training & KPI.
    change_reason must distinguish system_wrong vs user_preference vs accepted.
    """
    block = db.query(TextBlock).filter(TextBlock.id == req.block_id).first()
    suggested_template = req.suggested_template
    suggested_lines = req.suggested_lines
    font_fp = req.font_fingerprint or ""
    revision = req.spec_revision or 1
    decision_status = req.decision_status
    project_id = req.project_id
    page_id = req.page_id
    suggested_spec_id = None
    current_spec_id = None

    if block:
        page_id = page_id or block.page_id
        if block.page is not None:
            project_id = project_id or block.page.project_id
        meta = block.extra_metadata or {}
        spec_data = meta.get("typesetting_spec") or {}
        if isinstance(spec_data, dict):
            metrics = spec_data.get("metrics") or {}
            descriptor = metrics.get("style_descriptor") if isinstance(metrics, dict) else {}
            if not isinstance(descriptor, dict):
                descriptor = {}
            suggested_template = (
                suggested_template
                or meta.get("suggested_template_id")
                or descriptor.get("suggested_template")
                or spec_data.get("template_id")
            )
            suggested_lines = (
                suggested_lines
                or meta.get("suggested_explicit_lines")
                or spec_data.get("explicit_lines")
            )
            font_fp = font_fp or spec_data.get("font_fingerprint") or ""
            revision = req.spec_revision or int(spec_data.get("revision", 1) or 1)
            decision_status = decision_status or spec_data.get("decision_status")
            suggested_spec_id = meta.get("suggested_spec_id")
            current_spec_id = spec_data.get("spec_id")

    event = build_typesetting_decision_event(
        block_id=req.block_id,
        suggested_template=suggested_template,
        selected_template=req.selected_template,
        suggested_lines=suggested_lines,
        final_lines=req.final_lines,
        change_reason=req.change_reason,
        decision_status=decision_status,
        engine_version=LAYOUT_ENGINE_VERSION,
        font_fingerprint=font_fp,
        spec_revision=revision,
        suggested_spec_id=suggested_spec_id,
        current_spec_id=current_spec_id,
        project_id=project_id,
        page_id=page_id,
    )
    ok = log_typesetting_decision(event)
    return {"ok": ok, "event": event}


# ==========================================
# Typesetting Linguistic Rules API Endpoints
# ==========================================

from app.services.typesetting.rules_manager import (
    TypesettingRulesModel,
    RuleTestRequest,
    RuleTestResponse,
    get_typesetting_rules,
    save_typesetting_rules,
    reset_typesetting_rules_to_default,
    simulate_rules_evaluation,
)

@router.get("/rules", response_model=TypesettingRulesModel)
def get_rules():
    """Returns active typesetting and segmentation rules."""
    return get_typesetting_rules()

@router.post("/rules", response_model=Dict[str, Any])
def update_rules(rules: TypesettingRulesModel):
    """Updates and saves global typesetting rules."""
    success = save_typesetting_rules(rules.dict())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save typesetting rules"
        )
    return {"success": True, "rules": rules.dict()}

@router.post("/rules/reset", response_model=TypesettingRulesModel)
def reset_rules():
    """Resets global typesetting rules to factory defaults."""
    return reset_typesetting_rules_to_default()

@router.post("/rules/test", response_model=RuleTestResponse)
def test_rules(req: RuleTestRequest):
    """Simulates segmentation and line splitting on sample text."""
    custom_dict = req.custom_rules.dict() if req.custom_rules else None
    return simulate_rules_evaluation(
        sample_text=req.sample_text,
        target_lines=req.target_lines,
        rules_dict=custom_dict
    )

