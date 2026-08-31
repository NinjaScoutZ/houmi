from __future__ import annotations

from typing import Any


# Built-in packs when project settings omit text_templates (parity with frontend defaults)
_BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "bubble": {
        "font_stack": ["NotoSansThai"],
        "font_size": 60,
        "auto_font_size": True,
        "min_font_size": 6,
        "max_font_size": 96,
        "color_hex": "#111111",
        "stroke_color": "#ffffff",
        "stroke_width": 0,
        "bold": False,
        "italic": False,
        "text_align": "center",
        "text_direction": "horizontal",
        "balloon_type": "bubble",
        "line_height_ratio": 1.2,
        "letter_spacing": 0,
        "padding": {"top": 12, "right": 18, "bottom": 12, "left": 18},
        # semantic_tag = AI brace label; template id IS the semantic role
        "semantic_tag": "ตัวละครพูด",
        "name": "บทพูดทั่วไป",
    },
    "narration": {
        "font_stack": ["NotoSansThai"],
        "font_size": 52,
        "auto_font_size": True,
        "min_font_size": 6,
        "max_font_size": 84,
        "color_hex": "#111111",
        "stroke_color": "#ffffff",
        "stroke_width": 0,
        "bold": False,
        "italic": False,
        "text_align": "left",
        "text_direction": "horizontal",
        "balloon_type": "narrative",
        "line_height_ratio": 1.2,
        "letter_spacing": 0,
        "padding": {"top": 16, "right": 20, "bottom": 16, "left": 20},
        "semantic_tag": "คำบรรยาย",
        "name": "คำบรรยาย",
    },
    "emphasis": {
        "font_stack": ["NotoSansThai"],
        "font_size": 72,
        "auto_font_size": True,
        "min_font_size": 6,
        "max_font_size": 120,
        "color_hex": "#111111",
        "stroke_color": "#ffffff",
        "stroke_width": 1,
        "bold": True,
        "italic": False,
        "text_align": "center",
        "text_direction": "horizontal",
        "balloon_type": "bubble",
        "line_height_ratio": 1.2,
        "letter_spacing": 0,
        "padding": {"top": 10, "right": 14, "bottom": 10, "left": 14},
        "semantic_tag": "ตะโกน",
        "name": "ตะโกน / เน้นเสียง",
    },
    "sfx": {
        "font_stack": ["Tahoma"],
        "font_size": 84,
        "auto_font_size": True,
        "min_font_size": 6,
        "max_font_size": 152,
        "color_hex": "#ffffff",
        "stroke_color": "#111111",
        "stroke_width": 3,
        "bold": True,
        "italic": True,
        "text_align": "center",
        "text_direction": "horizontal",
        "balloon_type": "sfx",
        "line_height_ratio": 1.2,
        "letter_spacing": 0,
        "padding": {"top": 4, "right": 4, "bottom": 4, "left": 4},
        "semantic_tag": "เสียงเอฟเฟกต์",
        "name": "เสียงเอฟเฟกต์",
    },
    "thought": {
        "font_stack": ["NotoSansThai"],
        "font_size": 52,
        "auto_font_size": True,
        "min_font_size": 6,
        "max_font_size": 84,
        "color_hex": "#444444",
        "stroke_color": "#ffffff",
        "stroke_width": 0,
        "bold": False,
        "italic": False,
        "text_align": "center",
        "text_direction": "horizontal",
        "balloon_type": "bubble",
        "line_height_ratio": 1.2,
        "letter_spacing": 0,
        "padding": {"top": 12, "right": 18, "bottom": 12, "left": 18},
        "semantic_tag": "คิดในใจ",
        "name": "คิดในใจ",
    },
    "system": {
        "font_stack": ["NotoSansThai"],
        "font_size": 48,
        "auto_font_size": True,
        "min_font_size": 6,
        "max_font_size": 72,
        "color_hex": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": 1,
        "bold": True,
        "italic": False,
        "text_align": "center",
        "text_direction": "horizontal",
        "balloon_type": "narrative",
        "line_height_ratio": 1.2,
        "letter_spacing": 0,
        "padding": {"top": 10, "right": 14, "bottom": 10, "left": 14},
        "semantic_tag": "ระบบพูด",
        "name": "ระบบพูด",
    },
}


def list_semantic_roles(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every Font Template is a Semantic Role. Add template ⇒ add role."""
    templates = resolve_text_templates(settings)
    roles: list[dict[str, Any]] = []
    for tid, tmpl in templates.items():
        if not isinstance(tmpl, dict):
            continue
        roles.append({
            "id": str(tid),
            "template_id": str(tid),
            "name": str(tmpl.get("name") or tid),
            "semantic_tag": str(tmpl.get("semantic_tag") or "").strip(),
            "balloon_type": str(tmpl.get("balloon_type") or "bubble"),
        })
    return roles


def resolve_text_templates(settings: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    settings = settings or {}
    templates = settings.get("text_templates")
    if isinstance(templates, dict) and templates:
        out: dict[str, dict[str, Any]] = {}
        for key, value in templates.items():
            if isinstance(value, dict):
                out[str(key)] = value
        if out:
            return out
    return dict(_BUILTIN_TEMPLATES)


def get_default_text_template(settings: dict[str, Any] | None) -> tuple[str | None, dict[str, Any] | None]:
    """
    Resolve default template from project settings only.
    Does not inject built-in packs — callers that need builtins use resolve_text_templates().
    """
    settings = settings or {}
    templates = settings.get("text_templates")
    if not isinstance(templates, dict) or not templates:
        return None, None
    template_id = str(settings.get("default_text_template_id") or "bubble")
    template = templates.get(template_id)
    if not isinstance(template, dict):
        template_id, template = next(
            ((str(key), value) for key, value in templates.items() if isinstance(value, dict)),
            (None, None),
        )
    return template_id, template


def apply_template_by_id(
    block: Any,
    template_id: str | None,
    settings: dict[str, Any] | None,
) -> bool:
    """Apply a named template onto the block. Returns True if template was found."""
    if not template_id:
        return False
    templates = resolve_text_templates(settings)
    template = templates.get(str(template_id))
    if not isinstance(template, dict):
        return False
    return _apply_template_fields(block, str(template_id), template)


def _apply_template_fields(block: Any, template_id: str, template: dict[str, Any]) -> bool:
    raw_font_stack = template.get("font_stack") or [template.get("font_family")]
    if isinstance(raw_font_stack, str):
        raw_font_stack = [raw_font_stack]
    font_stack = list(dict.fromkeys(
        str(value).strip() for value in (raw_font_stack or []) if str(value).strip() and str(value) != "None"
    ))
    font = font_stack[0] if font_stack else "Tahoma"
    block.font_family = font
    metadata = dict(getattr(block, "extra_metadata", None) or {})
    effect_sources: dict[str, str] = dict(metadata.get("effect_sources") or {})

    # 1. Color: Priority AI Vision > Font Template
    extracted_color = getattr(block, "color_hex", None) or metadata.get("detected_color_hex")
    if extracted_color and str(extracted_color).startswith("#") and str(extracted_color).lower() not in {"#000000", "#111111", ""}:
        block.color_hex = str(extracted_color)
        effect_sources["color"] = "ai_vision"
    else:
        block.color_hex = str(template.get("color_hex", getattr(block, "color_hex", "#000000")))
        effect_sources["color"] = "template"

    # 2. Bold / Italic: Priority AI Vision > Font Template
    if metadata.get("detected_bold") is not None:
        block.bold = bool(metadata["detected_bold"])
        effect_sources["bold"] = "ai_vision"
    else:
        block.bold = bool(template.get("bold", False))
        effect_sources["bold"] = "template"

    if metadata.get("detected_italic") is not None:
        block.italic = bool(metadata["detected_italic"])
        effect_sources["italic"] = "ai_vision"
    else:
        block.italic = bool(template.get("italic", False))
        effect_sources["italic"] = "template"

    block.text_align = str(template.get("text_align", "center"))
    block.text_direction = str(template.get("text_direction", "horizontal"))
    if template.get("font_size") is not None:
        block.font_size = float(template["font_size"])
    metadata.pop("manual_font_size", None)
    semantic_tag = str(template.get("semantic_tag") or "").strip()
    semantic_label = semantic_tag or str(template.get("name") or template_id)

    # 3. Stroke: Priority AI Vision > Font Template
    detected_stroke = metadata.get("stroke_color")
    detected_stroke_w = metadata.get("stroke_width")
    if detected_stroke and str(detected_stroke).startswith("#") and str(detected_stroke).lower() not in {"#000000", ""}:
        stroke_color = detected_stroke
        stroke_width = detected_stroke_w if (detected_stroke_w and detected_stroke_w > 0) else 2.0
        effect_sources["stroke"] = "ai_vision"
    else:
        stroke_color = template.get("stroke_color", "#ffffff")
        stroke_width = template.get("stroke_width", 0) if template.get("stroke_enabled", True) else 0
        effect_sources["stroke"] = "template"

    # 4. Glow / Shadows / Gradients: Priority AI Vision > Template
    glow_enabled = template.get("outline_glow_enabled", True)
    if metadata.get("detected_gradient"):
        effect_sources["gradient"] = "ai_vision"
    if metadata.get("detected_drop_shadow"):
        effect_sources["drop_shadow"] = "ai_vision"
    if metadata.get("detected_outer_glow"):
        effect_sources["outer_glow"] = "ai_vision"
    if metadata.get("detected_inner_shadow"):
        effect_sources["inner_shadow"] = "ai_vision"

    # Legacy project templates predate the flag and were always auto-sized.
    # An explicit false is the only way to opt into a fixed template size.
    auto_font_size = bool(template.get("auto_font_size", True))
    metadata.update({
        "text_template_id": template_id,
        # Font Template id == Semantic Role id
        "semantic_role": template_id,
        "semantic_role_label": semantic_label,
        "semantic_role_template_id": template_id,
        # Preset geometry hint only — not detector evidence for Style Judge
        "template_balloon_type": str(template.get("balloon_type", "bubble")),
        "font_size_mode": "auto" if auto_font_size else "fixed",
        "auto_font_size": auto_font_size,
        "preferred_font_size": block.font_size,
        # Preserve every client-preset fallback. The typesetter resolves the
        # first installed family while the block keeps the customer's order.
        "font_stack": font_stack or [font],
        "stroke_color": stroke_color,
        "stroke_width": stroke_width,
        "outline_glow_color": template.get("outline_glow_color", template.get("stroke_color", "#ffffff")),
        "outline_glow_radius": template.get("outline_glow_radius", 0) if glow_enabled else 0,
        "outline_glow_opacity": template.get("outline_glow_opacity", 0) if glow_enabled else 0,
        "line_height_ratio": template.get("line_height_ratio", 1.2),
        "letter_spacing": template.get("letter_spacing", 0),
        "tracking": template.get("letter_spacing", 0),
        "padding": template.get("padding") or {},
        "effect_sources": effect_sources,
        "color_source": effect_sources.get("color", "template"),
    })
    if template.get("min_font_size") is not None:
        metadata["min_font_size"] = template["min_font_size"]
    if template.get("max_font_size") is not None:
        metadata["max_font_size"] = template["max_font_size"]
    block.extra_metadata = metadata
    return True


def apply_default_text_template(block: Any, settings: dict[str, Any] | None) -> bool:
    template_id, template = get_default_text_template(settings)
    if not template:
        fallback_font = str((settings or {}).get("default_font_family") or "Tahoma")
        block.font_family = fallback_font
        metadata = dict(getattr(block, "extra_metadata", None) or {})
        metadata["font_stack"] = [fallback_font]
        block.extra_metadata = metadata
        return False
    return _apply_template_fields(block, str(template_id), template)
