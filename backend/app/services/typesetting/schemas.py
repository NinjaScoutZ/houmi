from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal


# Canonical schema for B+ TypesettingSpec (immutable artifact contract)
TYPESETTING_SCHEMA_VERSION = "2.0.0"


class PaddingSpec(BaseModel):
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0


class GradientStop(BaseModel):
    position: float = 0.0
    color: str = "#000000"
    opacity: float = 1.0


class GradientSpec(BaseModel):
    """Photoshop-compatible gradient overlay settings shared by all renderers."""
    enabled: bool = False
    type: Literal["linear", "radial", "angle", "reflected", "diamond"] = "linear"
    stops: List[GradientStop] = Field(default_factory=lambda: [
        GradientStop(position=0.0, color="#111111"),
        GradientStop(position=1.0, color="#ffffff"),
    ])
    angle_deg: float = 0.0
    scale: float = 100.0
    reverse: bool = False
    dither: bool = True
    opacity: float = 1.0
    blend_mode: str = "normal"


class DropShadowSpec(BaseModel):
    """Photoshop-compatible drop shadow effect."""
    enabled: bool = False
    color: str = "#000000"
    opacity: float = 0.75
    angle_deg: float = 120.0
    distance: float = 5.0
    spread: float = 0.0
    size: float = 5.0  # Blur radius in px
    blend_mode: str = "multiply"


class InnerShadowSpec(BaseModel):
    """Photoshop-compatible inner shadow effect."""
    enabled: bool = False
    color: str = "#000000"
    opacity: float = 0.75
    angle_deg: float = 120.0
    distance: float = 5.0
    choke: float = 0.0
    size: float = 5.0  # Blur radius in px
    blend_mode: str = "multiply"


class OuterGlowSpec(BaseModel):
    """Photoshop-compatible outer glow effect."""
    enabled: bool = False
    color: str = "#ffffff"
    opacity: float = 0.75
    spread: float = 0.0
    size: float = 10.0  # Blur radius in px
    blend_mode: str = "screen"


class LayoutRegionSpec(BaseModel):
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    shape: str = "bubble"
    confidence: float = 0.0
    source: str = "fallback_bbox"
    safe_margin: float = 0.0
    # Optional persisted segmentation mask used by the experimental contour
    # fitter.  Older specs omit these fields and remain fully compatible.
    mask_path: Optional[str] = None
    mask_area: int = 0
    contour_version: Optional[str] = None


class StructuredWarning(BaseModel):
    code: str
    severity: str  # warning | error
    message: str
    block_id: str
    details: Dict[str, Any] = Field(default_factory=dict)


class TypesettingSpec(BaseModel):
    """
    Canonical TypesettingSpec v3 — versioned immutable layout artifact.
    Renderers must read this and must not re-fit lines or mutate fields.
    """

    schema_version: str = TYPESETTING_SCHEMA_VERSION
    # layout_engine_version is the canonical name; layout_version kept for compatibility
    layout_engine_version: str = "3.0.0"
    layout_version: str = "3.0.0"  # mirror of layout_engine_version for legacy readers
    spec_id: str = ""
    revision: int = 1
    block_id: str
    source_signature: str
    render_fingerprint: str = ""

    # Decision / lifecycle
    layout_status: str  # valid | stale | warning | overflow
    layout_source: str  # auto | manual | imported
    decision_status: str = "AUTO_APPLIED"  # AUTO_APPLIED | DEFAULTED | NEEDS_REVIEW
    template_id: Optional[str] = None
    style_confidence: float = 1.0
    layout_confidence: float = 1.0
    reason_codes: List[str] = Field(default_factory=list)

    # Font (resolved)
    requested_font_family: str
    resolved_font_id: str
    resolved_font_family: str
    resolved_postscript_name: str
    resolved_font_style: str
    font_postscript_name: str = ""  # alias of resolved_postscript_name for export parity
    font_fingerprint: str
    font_size: float
    bold: bool = False
    italic: bool = False
    faux_bold: bool = False
    faux_italic: bool = False
    anti_alias: Literal["none", "sharp", "crisp", "strong", "smooth"] = "sharp"

    # Color / stroke / effects
    color_hex: str = "#000000"
    stroke_width: float = 0.0
    stroke_color: str = "#ffffff"
    outline_glow_radius: float = 0.0
    outline_glow_color: str = "#ffffff"
    outline_glow_opacity: float = 0.0
    gradient: GradientSpec = Field(default_factory=GradientSpec)
    drop_shadow: DropShadowSpec = Field(default_factory=DropShadowSpec)
    inner_shadow: InnerShadowSpec = Field(default_factory=InnerShadowSpec)
    outer_glow: OuterGlowSpec = Field(default_factory=OuterGlowSpec)

    # Lines & spacing
    explicit_lines: List[str]
    normalized_text: str
    line_height: float
    tracking: float = 0.0

    # Alignment & direction
    horizontal_align: str = "center"
    text_align: str = "center"  # alias of horizontal_align
    vertical_align: str = "center"
    writing_direction: str = "horizontal"
    rotation_deg: float = 0.0
    padding: PaddingSpec = Field(default_factory=PaddingSpec)
    layout_region: LayoutRegionSpec = Field(default_factory=LayoutRegionSpec)
    shape_type: str  # bubble | narrative | sfx

    # Quality
    overflow: bool = False
    overflow_score: float = 0.0
    quality_score: float = 0.0
    warnings: List[StructuredWarning] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class PsdExportSnapshot(BaseModel):
    export_id: str
    export_timestamp: str
    original_authored_text: str
    normalized_text: str
    exported_text: str
    explicit_lines: List[str]
    auto_break_offsets: List[int]
    authored_newline_offsets: List[int]
    source_signature: str
    schema_version: str
    layout_version: str
    export_version: str = "1.0.0"
    resolved_font_family: str
    resolved_font_style: str
    font_fingerprint: str
    psd_file_hash: Optional[str] = None
    break_provenance: Optional[List[Dict[str, Any]]] = None
    # The PSD export must retain the same inset rectangle used by the canonical
    # renderer; older snapshots may omit it and therefore default to zero.
    padding: PaddingSpec = Field(default_factory=PaddingSpec)
