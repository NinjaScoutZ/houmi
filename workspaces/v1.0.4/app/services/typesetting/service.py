import hashlib
import logging
import math
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.models.all_models import TextBlock
from app.services.font_registry import font_registry
from app.services.typesetting.schemas import (
    TypesettingSpec,
    PaddingSpec,
    GradientSpec,
    GradientStop,
    DropShadowSpec,
    InnerShadowSpec,
    OuterGlowSpec,
    LayoutRegionSpec,
    StructuredWarning,
    TYPESETTING_SCHEMA_VERSION,
)
from app.services.typesetting.normalization import normalize_text
from app.services.typesetting.segmentation import has_thai_word_segmenter, segment_text
from app.services.typesetting.fitting import compute_best_layout
from app.services.typesetting.contour_fitting import profile_for_block, resolve_mask_path
from app.services.typesetting.feedback import log_decision_from_spec
from app.services.typesetting.style_judge import judge_style
from app.services.layout_region import get_effective_layout_region
from app.services.performance import resolve_performance_settings
from app.services.semantic_tags import strip_translation_semantic_tags
from app.config import get_project_dictionary

logger = logging.getLogger("houmi-typesetting-service")

# B+ Production Line Optimizer engine
LAYOUT_ENGINE_VERSION = "2.0.2"
PSD_ANTI_ALIAS_MODES = {"none", "sharp", "crisp", "strong", "smooth"}


def _normalize_anti_alias(value: Any) -> str:
    normalized = str(value or "sharp").strip().lower()
    return normalized if normalized in PSD_ANTI_ALIAS_MODES else "sharp"

# Decision status constants (product lock)
DECISION_AUTO_APPLIED = "AUTO_APPLIED"
DECISION_DEFAULTED = "DEFAULTED"
DECISION_NEEDS_REVIEW = "NEEDS_REVIEW"


@lru_cache(maxsize=128)
def _resolve_font_candidates(candidates: tuple[str, ...], bold: bool, italic: bool):
    fallback = None
    for candidate in candidates:
        resolved = font_registry.resolve_font(candidate, bold=bold, italic=italic)
        fallback = (candidate, resolved)
        if not resolved.is_fallback:
            return candidate, resolved
    if fallback is not None:
        return fallback
    requested = candidates[0] if candidates else "NotoSansThai"
    return requested, font_registry.resolve_font(requested, bold=bold, italic=italic)


def _resolve_block_font(block: TextBlock, bold: bool, italic: bool):
    requested = block.font_family or "NotoSansThai"
    metadata = block.extra_metadata or {}
    stack = metadata.get("font_stack")
    candidates = stack if isinstance(stack, list) and stack else [requested]
    normalized = tuple(
        dict.fromkeys(
            [str(font).strip() for font in candidates if str(font).strip()] + [requested]
        )
    )
    return _resolve_font_candidates(normalized, bold, italic)


def compute_block_signature(block: TextBlock) -> str:
    """
    Computes a deterministic SHA-256 signature from block fields that affect typesetting.
    """
    # OCR/source text is recognition data, never a typesetting fallback. A
    # translation layer remains empty until an authored translation exists.
    text_val = strip_translation_semantic_tags(block.translation or "")
    has_project_context = block.page is not None and block.page.project is not None
    project_settings = (block.page.project.settings or {}) if has_project_context else {}
    from app.config import get_enable_smart_balloon
    enable_smart_balloon = get_enable_smart_balloon(project_settings)

    layout_region = get_effective_layout_region(block, project_settings)
    mask_path = resolve_mask_path(block, layout_region) or ""
    mask_fingerprint = ""
    if mask_path:
        try:
            mask_stat = Path(str(mask_path)).stat()
            mask_fingerprint = f"{mask_stat.st_size}:{mask_stat.st_mtime_ns}"
        except OSError:
            mask_fingerprint = "missing"
    width = layout_region["width"]
    height = layout_region["height"]
    balloon_type = block.balloon_type or "bubble"
    font_family = block.font_family or "NotoSansThai"
    bold = block.bold if block.bold is not None else False
    italic = block.italic if block.italic is not None else False
    text_direction = block.text_direction or "horizontal"
    text_align = block.text_align or "center"
    requested_font_size = (
        block.font_size if (block.font_size is not None and block.font_size > 0) else 16.0
    )

    resolved_style_signature = "unknown"
    resolved_postscript_signature = "unknown"
    try:
        font_family, resolved = _resolve_block_font(block, bold, italic)
        fingerprint = resolved.fingerprint
        resolved_style_signature = resolved.style
        resolved_postscript_signature = resolved.postscript_name
    except Exception:
        fingerprint = "unknown"

    padding = block.extra_metadata.get("padding", {}) if block.extra_metadata else {}
    line_height_ratio = (
        block.extra_metadata.get("line_height_ratio", 1.20) if block.extra_metadata else 1.20
    )
    tracking = block.extra_metadata.get("tracking", 0.0) if block.extra_metadata else 0.0
    template_id = (block.extra_metadata or {}).get("text_template_id", "")
    color_hex = block.color_hex or "#000000"
    stroke_width = (block.extra_metadata or {}).get("stroke_width", 0.0)
    stroke_color = (block.extra_metadata or {}).get("stroke_color", "#ffffff")
    gradient = GradientSpec.model_validate((block.extra_metadata or {}).get("gradient") or {})

    inputs = [
        text_val or "",
        f"{width:.2f}",
        f"{height:.2f}",
        f"{layout_region['x']:.2f}",
        f"{layout_region['y']:.2f}",
        f"{layout_region.get('confidence', 0.0):.4f}",
        str(layout_region.get("source", "fallback_bbox")),
        str(enable_smart_balloon),
        balloon_type,
        font_family,
        "|".join(str(font) for font in ((block.extra_metadata or {}).get("font_stack") or [])),
        str((block.extra_metadata or {}).get("min_font_size", "")),
        str((block.extra_metadata or {}).get("max_font_size", "")),
        str((block.extra_metadata or {}).get("ai_font_size_scale", "")),
        str((block.extra_metadata or {}).get("ai_font_size_target", "")),
        str((block.extra_metadata or {}).get("ai_font_size_policy", "")),
        str((block.extra_metadata or {}).get("manual_font_size", "")),
        str((block.extra_metadata or {}).get("font_size_mode", "auto")),
        str((block.extra_metadata or {}).get("line_break_source", "")),
        str((block.extra_metadata or {}).get("ai_preferred_lines", "")),
        str((block.extra_metadata or {}).get("ai_layout_hint", "")),
        str((block.extra_metadata or {}).get("ai_layout_text", "")),
        str((block.extra_metadata or {}).get("contour_layout", "")),
        _normalize_anti_alias((block.extra_metadata or {}).get("anti_alias", "smooth")),
        str(project_settings.get("enable_contour_layout", False)),
        str(mask_path),
        mask_fingerprint,
        f"{requested_font_size:.2f}",
        "1" if bold else "0",
        "1" if italic else "0",
        fingerprint,
        resolved_style_signature,
        resolved_postscript_signature,
        text_direction,
        text_align,
        f"{padding.get('top', 0.0):.2f}",
        f"{padding.get('right', 0.0):.2f}",
        f"{padding.get('bottom', 0.0):.2f}",
        f"{padding.get('left', 0.0):.2f}",
        f"{line_height_ratio:.2f}",
        f"{tracking:.2f}",
        str(project_settings.get("match_source_font_size", has_project_context)),
        str(project_settings.get("source_font_scale", 1.10)),
        str(project_settings.get("min_font_size", "")),
        str(project_settings.get("max_font_size", "")),
        str(template_id),
        color_hex,
        str(stroke_width),
        str(stroke_color),
        str(gradient.model_dump()),
        str((block.extra_metadata or {}).get("outline_glow_radius", 0.0)),
        str((block.extra_metadata or {}).get("outline_glow_color", "#ffffff")),
        str((block.extra_metadata or {}).get("outline_glow_opacity", 0.0)),
        # Dictionary changes tokenization → must invalidate cached Specs
        "|".join(
            str(t).strip()
            for t in get_project_dictionary(project_settings)
            if str(t).strip()
        ),
        LAYOUT_ENGINE_VERSION,
        TYPESETTING_SCHEMA_VERSION,
    ]
    input_str = "|".join(inputs)
    return hashlib.sha256(input_str.encode("utf-8")).hexdigest()


def _compute_render_fingerprint(spec_fields: dict) -> str:
    """Stable hash of fields that affect pixels / export semantics."""
    parts = [
        str(spec_fields.get("font_postscript_name", "")),
        str(spec_fields.get("font_fingerprint", "")),
        f"{float(spec_fields.get('font_size', 0)):.4f}",
        "|".join(spec_fields.get("explicit_lines") or []),
        f"{float(spec_fields.get('line_height', 0)):.4f}",
        f"{float(spec_fields.get('tracking', 0)):.4f}",
        str(spec_fields.get("bold")),
        str(spec_fields.get("italic")),
        str(spec_fields.get("color_hex", "")),
        str(spec_fields.get("stroke_width", 0)),
        str(spec_fields.get("stroke_color", "")),
        str(spec_fields.get("outline_glow_radius", 0)),
        str(spec_fields.get("outline_glow_color", "")),
        str(spec_fields.get("outline_glow_opacity", 0)),
        str(spec_fields.get("gradient", {})),
        str(spec_fields.get("text_align", "")),
        str(spec_fields.get("vertical_align", "")),
        str(spec_fields.get("writing_direction", "")),
        f"{float(spec_fields.get('rotation_deg', 0)):.4f}",
        str(spec_fields.get("layout_region")),
        str(spec_fields.get("padding")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def validate_typesetting_spec(block: TextBlock, spec: TypesettingSpec) -> bool:
    """
    Returns True if the spec matches the block's current layout-affecting parameters.
    """
    if not spec:
        return False
    if spec.layout_status == "stale":
        return False
    if spec.schema_version != TYPESETTING_SCHEMA_VERSION:
        return False
    engine_ver = getattr(spec, "layout_engine_version", None) or spec.layout_version
    if engine_ver != LAYOUT_ENGINE_VERSION:
        return False
    expected_sig = compute_block_signature(block)
    return spec.source_signature == expected_sig


def persist_typesetting_spec(
    block: TextBlock,
    spec: TypesettingSpec,
    *,
    reset_suggestion: bool = False,
) -> dict:
    """
    Attach a canonical Spec while preserving the first system suggestion.

    Feedback needs the original line/template proposal after the user edits and
    the live Spec is recomputed. Import workflows pass ``reset_suggestion=True``
    because a newly imported translation starts a new decision lifecycle.
    """
    spec_dump = spec.model_dump()
    # The fitted value is canonical for both rendering and editing. Keeping the
    # scalar column synchronized prevents the Inspector from showing the old
    # requested/template size while exporters read the fitted Spec size. Some
    # import adapters/tests provide a minimal model_dump-compatible object, so
    # only synchronize fields that are actually present.
    fitted_font_size = getattr(spec, "font_size", None)
    if fitted_font_size is None and isinstance(spec_dump, dict):
        fitted_font_size = spec_dump.get("font_size")
    if fitted_font_size is not None:
        block.font_size = float(fitted_font_size)
        source_signature = compute_block_signature(block)
        if hasattr(spec, "source_signature"):
            spec.source_signature = source_signature
        if isinstance(spec_dump, dict):
            spec_dump["source_signature"] = source_signature

    metadata = dict(block.extra_metadata or {})
    metrics = getattr(spec, "metrics", None)
    if not isinstance(metrics, dict) and isinstance(spec_dump, dict):
        metrics = spec_dump.get("metrics")
    descriptor = metrics.get("style_descriptor") if isinstance(metrics, dict) else None
    spec_id = getattr(spec, "spec_id", None) or (
        spec_dump.get("spec_id") if isinstance(spec_dump, dict) else None
    )
    revision = getattr(spec, "revision", None) or (
        spec_dump.get("revision") if isinstance(spec_dump, dict) else None
    )
    explicit_lines = getattr(spec, "explicit_lines", None) or (
        spec_dump.get("explicit_lines") if isinstance(spec_dump, dict) else None
    )

    if (reset_suggestion or not metadata.get("suggested_spec_id")) and spec_id:
        metadata["suggested_spec_id"] = spec_id
        metadata["suggested_spec_revision"] = int(revision or 1)
        metadata["suggested_explicit_lines"] = list(explicit_lines or [])
        metadata["suggested_template_id"] = (
            descriptor.get("suggested_template")
            if isinstance(descriptor, dict)
            else None
        )
    metadata["typesetting_spec"] = spec_dump

    # Sync Smart Balloon row_width_constraints to smart_balloon metadata for frontend access
    if isinstance(metrics, dict) and metrics.get("is_smart_balloon"):
        row_width_constraints = metrics.get("row_width_constraints")
        if row_width_constraints is not None and "smart_balloon" in metadata:
            smart_balloon_meta = dict(metadata.get("smart_balloon") or {})
            smart_balloon_meta["row_width_constraints"] = row_width_constraints
            metadata["smart_balloon"] = smart_balloon_meta

    block.extra_metadata = metadata
    return metadata


def _derive_decision_status(
    *,
    overflow: bool,
    gate_issues: list[str],
    warnings: list[StructuredWarning],
    style_confidence: float,
    layout_confidence: float,
    font_fallback: bool,
) -> tuple[str, list[str]]:
    """
    Product lock: AUTO_APPLIED | DEFAULTED | NEEDS_REVIEW
    Never silently apply low-confidence or risky layouts.
    """
    reason_codes: list[str] = []
    needs_review_codes = {
        "TEXT_OVERFLOW",
        "FONT_TOO_SMALL",
        "FONT_BELOW_PROJECT_MINIMUM",
        "UNBALANCED_LINES",
        "LAYOUT_REGION_FALLBACK",
        "FONT_UNAVAILABLE",
        "FONT_FALLBACK",
    }

    if overflow or "TEXT_OVERFLOW" in gate_issues:
        reason_codes.append("TEXT_OVERFLOW")
        return DECISION_NEEDS_REVIEW, reason_codes

    if font_fallback:
        reason_codes.append("FONT_FALLBACK")
        return DECISION_NEEDS_REVIEW, reason_codes

    for issue in gate_issues:
        if issue in needs_review_codes:
            reason_codes.append(issue)

    conf_floor = 0.90
    # Layout confidence gates auto-apply of the line engine result.
    if layout_confidence < conf_floor:
        reason_codes.append("LOW_LAYOUT_CONFIDENCE")
        return DECISION_NEEDS_REVIEW, reason_codes

    if reason_codes:
        # Hard gate issues already collected above
        hard = [c for c in reason_codes if c not in {"LOW_STYLE_CONFIDENCE"}]
        if hard:
            return DECISION_NEEDS_REVIEW, reason_codes

    # Soft warnings alone → still auto if no hard gate issues
    error_warnings = [w for w in warnings if w.severity == "error"]
    if error_warnings:
        reason_codes.extend(w.code for w in error_warnings)
        return DECISION_NEEDS_REVIEW, reason_codes

    # Layout is safe but style is uncertain → DEFAULTED (safe default path)
    if style_confidence < conf_floor:
        reason_codes.append("LOW_STYLE_CONFIDENCE")
        return DECISION_DEFAULTED, reason_codes

    reason_codes.append("CONSTRAINTS_OK")
    return DECISION_AUTO_APPLIED, reason_codes


def compute_block_typesetting(
    block: TextBlock,
    *,
    log_feedback: bool = True,
    previous_revision: int | None = None,
) -> TypesettingSpec:
    """
    Computes and returns a fresh TypesettingSpec v2 for a TextBlock.
    Does not save to the database; callers should save if desired.
    Spec is treated as an immutable artifact once persisted — mutate by new revision.
    """
    # Do not turn OCR into a provisional translated layer. That made empty
    # balloons generate a source-text Spec and auto-fit against the wrong text.
    text_val = strip_translation_semantic_tags(block.translation or "")
    project_settings = {}
    has_project_context = block.page is not None and block.page.project is not None
    if has_project_context:
        project_settings = block.page.project.settings or {}

    layout_region = get_effective_layout_region(block, project_settings)
    width = layout_region["width"]
    height = layout_region["height"]
    balloon_type = block.balloon_type or "bubble"
    font_family = block.font_family or "NotoSansThai"
    bold = block.bold if block.bold is not None else False
    italic = block.italic if block.italic is not None else False
    text_direction = block.text_direction or "horizontal"
    text_align = block.text_align or "center"
    rotation_deg = block.rotation_deg if block.rotation_deg is not None else 0.0
    color_hex = block.color_hex or "#000000"
    meta = block.extra_metadata or {}
    anti_alias = _normalize_anti_alias(meta.get("anti_alias", "sharp"))
    stroke_width = float(meta.get("stroke_width", 0.0) or 0.0)
    stroke_color = str(meta.get("stroke_color", "#ffffff") or "#ffffff")
    outline_glow_radius = max(0.0, float(meta.get("outline_glow_radius", 0.0) or 0.0))
    outline_glow_color = str(meta.get("outline_glow_color", stroke_color) or stroke_color)
    outline_glow_opacity = max(
        0.0, min(1.0, float(meta.get("outline_glow_opacity", 0.0) or 0.0))
    )
    template_id = meta.get("text_template_id")
    style_confidence = float(meta.get("style_confidence", 1.0) or 1.0)
    style_reason_codes: list[str] = []
    style_descriptor_snapshot = None

    # Style Judge v1 — multi-signal descriptor (does not force template swap here;
    # callers may apply via apply_style_to_block / batch API).
    try:
        page_h = None
        if block.page is not None and getattr(block.page, "height", None):
            page_h = float(block.page.height)
        proj_settings = {}
        if block.page is not None and block.page.project is not None:
            proj_settings = block.page.project.settings or {}
        descriptor = judge_style(block, project_settings=proj_settings, page_height=page_h)
        style_confidence = float(descriptor.confidence)
        style_reason_codes = list(descriptor.reason_codes)
        # Keep descriptor on local meta for this compute only — do not mutate
        # block.extra_metadata here (export/preflight must stay side-effect free).
        # Callers that want persistence use style-judge API or merge after save.
        meta = dict(meta)
        meta["style_descriptor"] = descriptor.to_dict()
        meta["style_confidence"] = style_confidence
        meta["suggested_template_id"] = descriptor.suggested_template
        style_descriptor_snapshot = descriptor.to_dict()
    except Exception as exc:
        logger.warning("style judge skipped for block %s: %s", getattr(block, "id", "?"), exc)
        style_descriptor_snapshot = None

    preferred_lines: list[str] | None = None
    layout_text = text_val
    if meta.get("line_break_source") == "ai_preferred":
        stored_lines = meta.get("ai_preferred_lines")
        if isinstance(stored_lines, list):
            preferred_lines = [str(line) for line in stored_lines if str(line).strip()]
        if not preferred_lines:
            preferred_lines = [line for line in str(text_val or "").splitlines() if line.strip()]
        # Imported AI breaks are suggestions. The canonical pre-break text is
        # persisted at import time so spaces between Latin words/clauses are not
        # guessed from line boundaries.
        candidate_ai_text = str(meta.get("ai_layout_text") or "".join(preferred_lines))
        # Ensure stale AI suggestions never truncate user-edited translations
        if text_val and re.sub(r"\s+", "", candidate_ai_text) == re.sub(r"\s+", "", text_val):
            layout_text = candidate_ai_text
        else:
            layout_text = text_val
            preferred_lines = None

    ai_layout_hint = meta.get("ai_layout_hint") if isinstance(meta.get("ai_layout_hint"), dict) else {}
    target_line_count = ai_layout_hint.get("target_lines") if ai_layout_hint else None
    if target_line_count is None and preferred_lines:
        target_line_count = len(preferred_lines)
    try:
        target_line_count = max(1, int(target_line_count)) if target_line_count is not None else None
    except (TypeError, ValueError):
        target_line_count = len(preferred_lines) if preferred_lines else None
    maximum_line_count = ai_layout_hint.get("max_lines") if ai_layout_hint else None
    try:
        maximum_line_count = max(1, int(maximum_line_count)) if maximum_line_count is not None else None
    except (TypeError, ValueError):
        maximum_line_count = None
    if target_line_count is not None and maximum_line_count is not None:
        target_line_count = min(target_line_count, maximum_line_count)

    normalized = normalize_text(layout_text)
    # Project dictionary (proper names) — canonical key: project_dictionary | legacy: thai_dictionary
    proj_dict_raw = []
    if block.page is not None and block.page.project is not None:
        proj_dict_raw = get_project_dictionary(block.page.project.settings)
    tokens = segment_text(normalized, project_dictionary=list(proj_dict_raw))

    font_was_fallback = False
    try:
        font_family, resolved = _resolve_block_font(block, bold, italic)
        fingerprint = resolved.fingerprint
        resolved_font_id = resolved.family.lower() + "_" + resolved.style
        resolved_font_family = resolved.family
        resolved_postscript_name = resolved.postscript_name
        resolved_font_style = resolved.style
        font_was_fallback = bool(getattr(resolved, "is_fallback", False))
    except Exception as e:
        logger.error(f"Failed to resolve font for typesetting block {block.id}: {e}")
        fingerprint = "unknown"
        resolved_font_id = "tahoma_regular"
        resolved_font_family = "Tahoma"
        resolved_postscript_name = "Tahoma"
        resolved_font_style = "regular"
        font_was_fallback = True

    has_explicit_lh = "line_height_ratio" in meta and meta["line_height_ratio"] is not None
    if has_explicit_lh:
        line_height_ratio = float(meta["line_height_ratio"])
    else:
        # Hybrid Photoshop-Houmi Leading Engine:
        # Thai text needs 1.25x for tone mark / vowel spacing; Latin/CJK uses Photoshop default 1.20x ratio.
        is_thai = bool(re.search(r"[\u0e00-\u0e7f]", text_val or ""))
        line_height_ratio = 1.25 if is_thai else 1.20
    tracking = float(meta.get("tracking", 0.0) or 0.0)
    
    # Resolve Gradient: manual > AI Vision detected
    gradient_data = meta.get("gradient") or meta.get("detected_gradient") or {}
    if isinstance(gradient_data, dict) and "colors" in gradient_data and "stops" not in gradient_data:
        # Convert simple colors list ["#hex1", "#hex2"] to GradientStops
        raw_colors = gradient_data.get("colors") or []
        stops = []
        if len(raw_colors) == 1:
            stops = [GradientStop(position=0.0, color=raw_colors[0]), GradientStop(position=1.0, color=raw_colors[0])]
        elif len(raw_colors) > 1:
            for idx, c in enumerate(raw_colors):
                pos = float(idx) / float(len(raw_colors) - 1)
                stops.append(GradientStop(position=pos, color=str(c)))
        gradient_dict = dict(gradient_data)
        gradient_dict["stops"] = stops
        gradient = GradientSpec.model_validate(gradient_dict)
    else:
        gradient = GradientSpec.model_validate(gradient_data if isinstance(gradient_data, dict) else {})

    # Resolve Drop Shadow: manual > AI Vision detected
    shadow_data = meta.get("drop_shadow") or meta.get("detected_drop_shadow") or {}
    drop_shadow = DropShadowSpec.model_validate(shadow_data if isinstance(shadow_data, dict) else {})
    if shadow_data and isinstance(shadow_data, dict) and shadow_data.get("blur") and not shadow_data.get("size"):
        drop_shadow.size = float(shadow_data["blur"])

    # Resolve Inner Shadow: manual > AI Vision detected
    inner_data = meta.get("inner_shadow") or meta.get("detected_inner_shadow") or {}
    inner_shadow = InnerShadowSpec.model_validate(inner_data if isinstance(inner_data, dict) else {})

    # Resolve Outer Glow: manual > AI Vision detected > legacy outline_glow fields
    glow_data = meta.get("outer_glow") or meta.get("detected_outer_glow") or {}
    outer_glow = OuterGlowSpec.model_validate(glow_data if isinstance(glow_data, dict) else {})
    if not outer_glow.enabled and outline_glow_radius > 0 and outline_glow_opacity > 0:
        outer_glow = OuterGlowSpec(
            enabled=True,
            color=outline_glow_color,
            size=outline_glow_radius,
            opacity=outline_glow_opacity,
        )

    padding_dict = meta.get("padding", {}) if meta else {}
    padding = PaddingSpec(
        top=float(padding_dict.get("top", 0.0)),
        right=float(padding_dict.get("right", 0.0)),
        bottom=float(padding_dict.get("bottom", 0.0)),
        left=float(padding_dict.get("left", 0.0)),
    )

    inner_w = max(10.0, width - padding.left - padding.right)
    inner_h = max(10.0, height - padding.top - padding.bottom)

    from app.config import get_enable_smart_balloon
    enable_smart = get_enable_smart_balloon(project_settings)

    # -------------------------------------------------------------
    # Dedicated Smart Balloon Shape Typesetting Engine
    # -------------------------------------------------------------
    sb_meta = meta.get("smart_balloon") if meta else None
    if enable_smart and sb_meta and sb_meta.get("safe_bbox"):
        try:
            from app.services.smart_balloon_typesetting import compute_smart_balloon_typesetting
            sb_spec = compute_smart_balloon_typesetting(block, project_settings)
            if sb_spec is not None:
                return sb_spec
        except Exception as exc:
            logger.warning("Dedicated Smart Balloon typesetting encountered error: %s, falling back", exc)

    has_smart_balloon = enable_smart and bool(
        getattr(block, "smart_x", None) is not None
        or getattr(block, "smart_mask_path", None) is not None
        or (meta and meta.get("smart_balloon"))
    )
    contour_layout_requested = bool(
        meta.get("contour_layout", project_settings.get("enable_contour_layout", True if has_smart_balloon else False))
    )
    contour_profile = None
    if contour_layout_requested and balloon_type in {"bubble", "narrative"}:
        try:
            # When contour layout is active, the mask defines the actual text
            # boundaries (the balloon's curved shape). We should use the full
            # block bbox as the working area, not the narrow layout_region,
            # because the mask contour itself constrains per-line widths.
            smart_w = float(getattr(block, "smart_width", 0) or 0)
            smart_h = float(getattr(block, "smart_height", 0) or 0)
            block_bbox_w = smart_w if smart_w > 0 else float(getattr(block, "width", 0) or 0)
            block_bbox_h = smart_h if smart_h > 0 else float(getattr(block, "height", 0) or 0)
            if block_bbox_w > 20.0 and block_bbox_h > 20.0:
                contour_w = max(10.0, block_bbox_w - padding.left - padding.right)
                contour_h = max(10.0, block_bbox_h - padding.top - padding.bottom)
            else:
                contour_w = inner_w
                contour_h = inner_h

            # Erode mask inward by ~2% (capped at 8px) to keep text comfortably inside balloon edges
            contour_padding = max(4.0, min(contour_w * 0.02, contour_h * 0.02, 8.0))
            contour_profile = profile_for_block(
                block,
                layout_region,
                target_width=contour_w,
                target_height=contour_h,
                padding=contour_padding,
            )
            if contour_profile is not None:
                # Expand the working area to the full balloon shape
                inner_w = contour_w
                inner_h = contour_h
        except (OSError, TypeError, ValueError):
            logger.warning("Contour mask could not be loaded for block %s", getattr(block, "id", "?"))
    performance_settings = resolve_performance_settings(project_settings)
    auto_font_resize = bool(project_settings.get("auto_font_resize", True))
    configured_min_font = project_settings.get("min_font_size") if auto_font_resize else None
    configured_max_font = project_settings.get("max_font_size") if auto_font_resize else None
    if auto_font_resize and meta:
        configured_min_font = meta.get("min_font_size", configured_min_font)
        configured_max_font = meta.get("max_font_size", configured_max_font)
    manual_font_size = meta.get("manual_font_size")
    # ``font_size_mode=manual`` is also a valid lock for projects created by
    # earlier clients that saved the number on the block but not in metadata.
    # Without this, a valid manual edit could be immediately replaced by the
    # previous auto-fit Spec during the next render/export.
    # Page resolution scaling is based on Page Width (standard baseline: 1000px width),
    # which is constant for webtoon strips regardless of infinite strip height.
    page_width = float(block.page.width) if (block.page and getattr(block.page, "width", None)) else 1000.0
    resolution_scale = max(0.5, min(3.0, page_width / 1000.0))

    font_size_mode = meta.get("font_size_mode")
    manual_font_locked = manual_font_size is not None or font_size_mode in {"manual", "fixed"}
    requested_font_size = float(block.font_size or 16.0)
    explicit_auto_mode = font_size_mode == "auto" or (
        font_size_mode not in {"manual", "fixed"} and meta.get("auto_font_size") is True
    )
    is_auto_mode = explicit_auto_mode or (
        has_project_context and auto_font_resize and not manual_font_locked
    )

    if manual_font_locked and not is_auto_mode:
        # Respect user's explicit font size setting 100% without modification
        requested_font_size = max(6.0, float(manual_font_size if manual_font_size is not None else requested_font_size))
    else:
        # For auto-fit mode, allow font size to scale up to max_font_size or box height cap,
        # and shrink down to min_font_size (default 6.0) to fit inside the balloon bounds!
        if is_auto_mode:
            balloon_dim_cap = min(inner_h * 0.45, inner_w * 0.35)
            default_max = max(140.0 * resolution_scale, balloon_dim_cap)
            requested_font_size = default_max
            if configured_max_font is not None:
                requested_font_size = min(requested_font_size, float(configured_max_font) * resolution_scale)
            
            ai_font_size_target = meta.get("ai_font_size_target")
            try:
                ai_font_size_target = float(ai_font_size_target)
            except (TypeError, ValueError):
                ai_font_size_target = None
            if ai_font_size_target is not None and math.isfinite(ai_font_size_target) and ai_font_size_target > 0:
                # AI chooses a semantic/style ceiling. Glyph measurement and
                # balloon overflow constraints still determine the final size.
                requested_font_size = min(requested_font_size, ai_font_size_target * resolution_scale)
            if configured_min_font is None:
                configured_min_font = 6.0
        else:
            requested_font_size = requested_font_size * resolution_scale
            if auto_font_resize and configured_max_font is not None:
                requested_font_size = max(6.0 * resolution_scale, float(configured_max_font) * resolution_scale)
            if configured_min_font is not None:
                requested_font_size = max(requested_font_size, float(configured_min_font) * resolution_scale)
            if configured_max_font is not None:
                requested_font_size = min(requested_font_size, float(configured_max_font) * resolution_scale)

    layout = compute_best_layout(
        tokens=tokens,
        font_name=font_family,
        bold=bold,
        italic=italic,
        block_w=inner_w,
        block_h=inner_h,
        balloon_type=balloon_type,
        requested_font_size=requested_font_size,
        minimum_font_size=float(configured_min_font) if configured_min_font is not None else None,
        candidate_budget=performance_settings.typesetting_candidates,
        line_height_ratio=line_height_ratio,
        normalized_text=normalized,
        lock_font_size=manual_font_locked,
        tracking=tracking,
        preferred_lines=preferred_lines,
        target_line_count=target_line_count,
        maximum_line_count=maximum_line_count,
        line_width_provider=contour_profile.provider() if contour_profile else None,
    )

    if preferred_lines and contour_profile:
        free_layout = compute_best_layout(
            tokens=tokens,
            font_name=font_family,
            bold=bold,
            italic=italic,
            block_w=inner_w,
            block_h=inner_h,
            balloon_type=balloon_type,
            requested_font_size=requested_font_size,
            minimum_font_size=float(configured_min_font) if configured_min_font is not None else None,
            candidate_budget=performance_settings.typesetting_candidates,
            line_height_ratio=line_height_ratio,
            normalized_text=normalized,
            lock_font_size=manual_font_locked,
            tracking=tracking,
            preferred_lines=None,
            target_line_count=None,
            maximum_line_count=maximum_line_count,
            line_width_provider=contour_profile.provider(),
        )
        if free_layout.get("font_size", 0) > layout.get("font_size", 0) + 3.0:
            layout = free_layout

    sig = compute_block_signature(block)
    warningsList: List[StructuredWarning] = []

    original_requested_font_size = (
        block.font_size if (block.font_size is not None and block.font_size > 0) else 16.0
    )
    if original_requested_font_size < 6.0:
        warningsList.append(
            StructuredWarning(
                code="FONT_SIZE_CLAMPED_TO_MINIMUM",
                severity="warning",
                message=(
                    f"Requested font size ({original_requested_font_size}) is below "
                    "the minimum supported size (6.0) and was clamped."
                ),
                block_id=block.id,
                details={"requested_size": original_requested_font_size, "clamped_size": 6.0},
            )
        )

    if font_family and resolved_font_family.lower() != font_family.lower():
        font_was_fallback = True
        warningsList.append(
            StructuredWarning(
                code="FONT_FALLBACK",
                severity="warning",
                message=f"Font family '{font_family}' fell back to '{resolved_font_family}'.",
                block_id=block.id,
                details={"requested": font_family, "resolved": resolved_font_family},
            )
        )

    req_style = "regular"
    if bold and italic:
        req_style = "bold_italic"
    elif bold:
        req_style = "bold"
    elif italic:
        req_style = "italic"

    if req_style != resolved_font_style:
        warningsList.append(
            StructuredWarning(
                code="FONT_STYLE_FALLBACK",
                severity="warning",
                message=f"Font style '{req_style}' fell back to '{resolved_font_style}'.",
                block_id=block.id,
                details={"requested": req_style, "resolved": resolved_font_style},
            )
        )

    has_thai = any("\u0e00" <= char <= "\u0e7f" for char in (text_val or ""))
    if has_thai and not has_thai_word_segmenter():
        warningsList.append(
            StructuredWarning(
                code="THAI_DICTIONARY_MISSING",
                severity="warning",
                message="Thai dictionary segmenter is missing, falling back to character-cluster wrapping.",
                block_id=block.id,
                details={},
            )
        )

    if layout["overflow"]:
        warningsList.append(
            StructuredWarning(
                code="TEXT_OVERFLOW",
                severity="error",
                message="Text layout overflows balloon boundaries.",
                block_id=block.id,
                details={"overflow_score": layout["overflow_score"]},
            )
        )

    if maximum_line_count and int(layout.get("line_count_excess", 0)) > 0:
        warningsList.append(
            StructuredWarning(
                code="AI_MAX_LINES_EXCEEDED",
                severity="error",
                message="Text cannot fit within the AI layout maximum line count.",
                block_id=block.id,
                details={
                    "maximum_lines": maximum_line_count,
                    "fitted_lines": len(layout["explicit_lines"]),
                },
            )
        )

    if preferred_lines and [line.strip() for line in layout["explicit_lines"]] != preferred_lines:
        warningsList.append(
            StructuredWarning(
                code="AI_LINEBREAK_ADJUSTED",
                severity="warning",
                message="AI line breaks were adjusted to fit the balloon geometry and font minimum.",
                block_id=block.id,
                details={
                    "preferred_lines": preferred_lines,
                    "fitted_lines": layout["explicit_lines"],
                },
            )
        )

    if layout["font_size"] < 12.0:
        warningsList.append(
            StructuredWarning(
                code="FONT_TOO_SMALL",
                severity="warning",
                message=f"Fitted font size ({layout['font_size']}) is smaller than 12.",
                block_id=block.id,
                details={"fitted_size": layout["font_size"]},
            )
        )


    if text_direction == "vertical":
        warningsList.append(
            StructuredWarning(
                code="VERTICAL_DIRECTION_UNSUPPORTED",
                severity="warning",
                message="Vertical text direction is not fully supported by standard horizontal layout renderer.",
                block_id=block.id,
                details={"writing_direction": text_direction},
            )
        )

    if text_val and layout_region.get("source") == "fallback_bbox":
        warningsList.append(
            StructuredWarning(
                code="LAYOUT_REGION_FALLBACK",
                severity="warning",
                message="Balloon interior was not detected; source text bounds are used as a safe fallback.",
                block_id=block.id,
                details={"reason": layout_region.get("reason", "unknown")},
            )
        )

    line_widths = layout.get("line_widths", [])
    average_width = (sum(line_widths) / len(line_widths)) if line_widths else 0.0
    balance_cv = 0.0
    if average_width > 0 and len(line_widths) > 1:
        variance = sum((line_width - average_width) ** 2 for line_width in line_widths) / len(
            line_widths
        )
        balance_cv = (variance**0.5) / average_width
    width_occupancy = (max(line_widths) / inner_w) if line_widths and inner_w > 0 else 0.0
    height_occupancy = (layout.get("total_height", 0.0) / inner_h) if inner_h > 0 else 0.0
    gate_issues = []
    if layout["overflow"]:
        gate_issues.append("TEXT_OVERFLOW")
    if layout["font_size"] < 10.0:
        gate_issues.append("FONT_TOO_SMALL")
    if is_auto_mode and configured_min_font is not None and layout["font_size"] < float(configured_min_font):
        gate_issues.append("FONT_BELOW_PROJECT_MINIMUM")
    if len(normalized) >= 20 and height_occupancy < 0.15:
        gate_issues.append("TEXT_UNDERSIZED_FOR_REGION")
    if layout_region.get("source") == "fallback_bbox":
        gate_issues.append("LAYOUT_REGION_FALLBACK")
    if len(line_widths) >= 3 and balance_cv > 0.48:
        gate_issues.append("UNBALANCED_LINES")
    if font_was_fallback:
        gate_issues.append("FONT_FALLBACK")

    quality_gate_score = 100.0
    quality_gate_score -= min(55.0, float(layout.get("overflow_score", 0.0)) * 2.0)
    quality_gate_score -= min(18.0, balance_cv * 22.0)
    quality_gate_score -= 15.0 if layout_region.get("source") == "fallback_bbox" else 0.0
    quality_gate_score -= 20.0 if layout["font_size"] < 10.0 else 0.0
    quality_gate_score -= 25.0 if "TEXT_UNDERSIZED_FOR_REGION" in gate_issues else 0.0
    quality_gate_score = max(0.0, min(100.0, quality_gate_score))

    # Layout confidence from quality gate (0–1)
    layout_confidence = round(quality_gate_score / 100.0, 4)

    decision_status, reason_codes = _derive_decision_status(
        overflow=bool(layout["overflow"]),
        gate_issues=gate_issues,
        warnings=warningsList,
        style_confidence=style_confidence,
        layout_confidence=layout_confidence,
        font_fallback=font_was_fallback,
        )

    if contour_layout_requested and contour_profile is None:
        warningsList.append(
            StructuredWarning(
                code="CONTOUR_MASK_UNAVAILABLE",
                severity="warning",
                message="Contour layout was requested but no usable balloon mask was available; ellipse/rectangle fitting was used.",
                block_id=block.id,
                details={"mask_path": layout_region.get("mask_path")},
            )
        )
    # Merge style evidence codes (dedupe, style first for explainability)
    merged_reasons: list[str] = []
    for code in style_reason_codes + reason_codes:
        if code not in merged_reasons:
            merged_reasons.append(code)
    reason_codes = merged_reasons

    layout_status = "valid"
    if layout["overflow"]:
        layout_status = "overflow"
    elif warningsList or decision_status == DECISION_NEEDS_REVIEW:
        layout_status = "warning"
    elif decision_status == DECISION_DEFAULTED:
        layout_status = "warning"

    # Revision: bump if prior spec exists
    revision = 1
    if previous_revision is not None:
        revision = int(previous_revision) + 1
    elif isinstance(meta.get("typesetting_spec"), dict):
        prev = meta["typesetting_spec"]
        revision = int(prev.get("revision", 0) or 0) + 1

    region_spec = LayoutRegionSpec(
        x=layout_region["x"],
        y=layout_region["y"],
        width=layout_region["width"],
        height=layout_region["height"],
        shape=layout_region.get("shape", balloon_type),
        confidence=layout_region.get("confidence", 0.0),
        source=layout_region.get("source", "fallback_bbox"),
        safe_margin=layout_region.get("safe_margin", 0.0),
        mask_path=layout_region.get("mask_path"),
        mask_area=int(layout_region.get("mask_area", 0) or 0),
        contour_version="1.0.0" if contour_profile is not None else None,
    )

    render_fp = _compute_render_fingerprint(
        {
            "font_postscript_name": resolved_postscript_name,
            "font_fingerprint": fingerprint,
            "font_size": layout["font_size"],
            "explicit_lines": layout["explicit_lines"],
            "line_height": layout["font_size"] * line_height_ratio,
            "tracking": tracking,
            "bold": bold,
            "italic": italic,
            "anti_alias": anti_alias,
            "color_hex": color_hex,
            "stroke_width": stroke_width,
            "stroke_color": stroke_color,
            "outline_glow_radius": outline_glow_radius,
            "outline_glow_color": outline_glow_color,
            "outline_glow_opacity": outline_glow_opacity,
            "gradient": gradient.model_dump(),
            "drop_shadow": drop_shadow.model_dump(),
            "inner_shadow": inner_shadow.model_dump(),
            "outer_glow": outer_glow.model_dump(),
            "text_align": text_align,
            "vertical_align": "center",
            "writing_direction": text_direction,
            "rotation_deg": rotation_deg,
            "layout_region": region_spec.model_dump(),
            "padding": padding.model_dump(),
        }
    )

    spec_id = f"spec_{block.id}_{revision}_{render_fp[:12]}"

    spec = TypesettingSpec(
        schema_version=TYPESETTING_SCHEMA_VERSION,
        layout_engine_version=LAYOUT_ENGINE_VERSION,
        layout_version=LAYOUT_ENGINE_VERSION,
        spec_id=spec_id,
        revision=revision,
        block_id=block.id,
        source_signature=sig,
        render_fingerprint=render_fp,
        layout_status=layout_status,
        layout_source="auto",
        decision_status=decision_status,
        template_id=str(template_id) if template_id else None,
        style_confidence=style_confidence,
        layout_confidence=layout_confidence,
        reason_codes=reason_codes,
        requested_font_family=font_family,
        resolved_font_id=resolved_font_id,
        resolved_font_family=resolved_font_family,
        resolved_postscript_name=resolved_postscript_name,
        font_postscript_name=resolved_postscript_name,
        resolved_font_style=resolved_font_style,
        font_fingerprint=fingerprint,
        font_size=layout["font_size"],
        bold=bool(bold),
        italic=bool(italic),
        anti_alias=anti_alias,
        color_hex=color_hex,
        stroke_width=stroke_width,
        stroke_color=stroke_color,
        outline_glow_radius=outline_glow_radius,
        outline_glow_color=outline_glow_color,
        outline_glow_opacity=outline_glow_opacity,
        gradient=gradient,
        drop_shadow=drop_shadow,
        inner_shadow=inner_shadow,
        outer_glow=outer_glow,
        explicit_lines=layout["explicit_lines"],
        normalized_text=normalized,
        line_height=layout["font_size"] * line_height_ratio,
        tracking=tracking,
        horizontal_align=text_align,
        text_align=text_align,
        vertical_align="center",
        writing_direction=text_direction,
        rotation_deg=rotation_deg,
        padding=padding,
        layout_region=region_spec,
        shape_type=balloon_type,
        overflow=layout["overflow"],
        overflow_score=layout["overflow_score"],
        quality_score=layout["quality_score"],
        warnings=warningsList,
        metrics={
            "break_provenance": layout.get("break_provenance", []),
            "candidate_count": int(layout.get("candidate_count", 1)),
            "line_candidate_count": int(layout.get("line_candidate_count", 0)),
            "line_candidates_evaluated": int(layout.get("line_candidates_evaluated", 0)),
            "line_generator": layout.get("line_generator", "beam"),
            "width_occupancy": round(width_occupancy, 4),
            "height_occupancy": round(height_occupancy, 4),
            "line_balance_cv": round(balance_cv, 4),
            "quality_gate": {
                "score": round(quality_gate_score, 2),
                "status": "needs_review"
                if decision_status == DECISION_NEEDS_REVIEW
                else ("defaulted" if decision_status == DECISION_DEFAULTED else "passed"),
                "needs_review": decision_status == DECISION_NEEDS_REVIEW,
                "issues": gate_issues,
            },
            "style_descriptor": style_descriptor_snapshot,
            "contour_layout": {
                "requested": contour_layout_requested,
                "applied": contour_profile is not None,
                "usable_row_ratio": round(contour_profile.usable_row_ratio, 4)
                if contour_profile
                else 0.0,
                "mask_area_ratio": round(contour_profile.area_ratio, 4)
                if contour_profile
                else 0.0,
            },
        },
    )

    if log_feedback:
        try:
            project_id = None
            page_id = getattr(block, "page_id", None)
            if block.page is not None:
                project_id = getattr(block.page, "project_id", None)
            change = "suggested"
            if decision_status == DECISION_AUTO_APPLIED:
                change = "auto_applied"
            elif decision_status == DECISION_DEFAULTED:
                change = "defaulted"
            elif decision_status == DECISION_NEEDS_REVIEW:
                change = "needs_review"
            log_decision_from_spec(
                spec,
                change_reason=change,
                project_id=project_id,
                page_id=page_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("feedback log skipped: %s", exc)

    return spec


def get_effective_typesetting_spec(block: TextBlock) -> TypesettingSpec:
    """
    Returns the valid TypesettingSpec from block's metadata if present and valid.
    If missing or stale, computes a new one dynamically (marked as stale/auto).
    """
    meta = block.extra_metadata if block.extra_metadata else {}
    spec_data = meta.get("typesetting_spec")

    if spec_data:
        try:
            spec = TypesettingSpec.model_validate(spec_data)
            if validate_typesetting_spec(block, spec):
                return spec
        except Exception:
            pass

    spec = compute_block_typesetting(block, log_feedback=False)
    spec.layout_status = "stale"
    return spec


def mark_typesetting_stale(block: TextBlock) -> None:
    """
    Modifies the block's typesetting spec status in extra_metadata to 'stale'.
    Does not commit to DB.
    """
    if not block.extra_metadata:
        block.extra_metadata = {}
    spec_data = block.extra_metadata.get("typesetting_spec")
    if spec_data:
        try:
            spec_data["layout_status"] = "stale"
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(block, "extra_metadata")
        except Exception:
            pass
