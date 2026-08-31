from app.services.typesetting.schemas import (
    TypesettingSpec,
    StructuredWarning,
    TYPESETTING_SCHEMA_VERSION,
)
from app.services.typesetting.service import (
    compute_block_typesetting,
    get_effective_typesetting_spec,
    mark_typesetting_stale,
    validate_typesetting_spec,
    persist_typesetting_spec,
    compute_block_signature,
    LAYOUT_ENGINE_VERSION,
    DECISION_AUTO_APPLIED,
    DECISION_DEFAULTED,
    DECISION_NEEDS_REVIEW,
)
from app.services.typesetting.feedback import (
    log_typesetting_decision,
    log_decision_from_spec,
    build_typesetting_decision_event,
)
from app.services.typesetting.style_judge import (
    judge_style,
    apply_style_descriptor_to_block,
    StyleDescriptor,
)
from app.services.typesetting.stroke import (
    stroke_draw_kwargs,
    draw_text_with_spec_stroke,
    parse_hex_rgba,
)
from app.services.typesetting.segmentation import (
    segment_text,
    normalize_project_dictionary,
)
