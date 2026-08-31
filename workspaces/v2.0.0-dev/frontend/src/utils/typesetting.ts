import { apiFetch, getApiBaseUrl } from '../api/runtime';

export interface PaddingSpec {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export type GradientType = 'linear' | 'radial' | 'angle' | 'reflected' | 'diamond';
export interface GradientStop {
  position: number;
  color: string;
  opacity?: number;
}
export interface GradientSpec {
  enabled: boolean;
  type: GradientType;
  stops: GradientStop[];
  angle_deg: number;
  scale: number;
  reverse: boolean;
  dither: boolean;
  opacity: number;
  blend_mode?: string;
}

export interface LayoutRegionSpec {
  x: number;
  y: number;
  width: number;
  height: number;
  shape: string;
  confidence: number;
  source: string;
  safe_margin: number;
}

export interface StructuredWarning {
  code: string;
  severity: 'warning' | 'error';
  message: string;
  block_id: string;
  details: Record<string, unknown>;
}

export type DecisionStatus = 'AUTO_APPLIED' | 'DEFAULTED' | 'NEEDS_REVIEW';
export type TextAntiAlias = 'none' | 'sharp' | 'crisp' | 'strong' | 'smooth';

export interface TypesettingSpec {
  schema_version: string;
  layout_version: string;
  layout_engine_version?: string;
  spec_id?: string;
  revision?: number;
  block_id: string;
  source_signature: string;
  render_fingerprint?: string;
  layout_status: 'valid' | 'stale' | 'warning' | 'overflow';
  layout_source: 'auto' | 'manual' | 'imported';
  decision_status?: DecisionStatus;
  template_id?: string | null;
  style_confidence?: number;
  layout_confidence?: number;
  reason_codes?: string[];
  requested_font_family: string;
  resolved_font_id: string;
  resolved_font_family: string;
  resolved_postscript_name: string;
  font_postscript_name?: string;
  resolved_font_style: string;
  font_fingerprint: string;
  font_size: number;
  bold?: boolean;
  italic?: boolean;
  anti_alias?: TextAntiAlias;
  color_hex?: string;
  stroke_width?: number;
  stroke_color?: string;
  outline_glow_radius?: number;
  outline_glow_color?: string;
  outline_glow_opacity?: number;
  gradient?: GradientSpec;
  explicit_lines: string[];
  normalized_text: string;
  line_height: number;
  tracking: number;
  horizontal_align: 'left' | 'center' | 'right';
  text_align?: 'left' | 'center' | 'right';
  vertical_align: string;
  writing_direction: 'horizontal' | 'vertical';
  rotation_deg: number;
  padding: PaddingSpec;
  layout_region: LayoutRegionSpec;
  shape_type: 'bubble' | 'narrative' | 'sfx';
  overflow: boolean;
  overflow_score: number;
  quality_score: number;
  warnings: StructuredWarning[];
  metrics: Record<string, unknown>;
}

export function isTypesettingSpec(obj: unknown): obj is TypesettingSpec {
  if (!obj || typeof obj !== 'object') {
    return false;
  }
  const o = obj as Record<string, unknown>;
  
  // Validate enums and string fields
  if (
    typeof o.schema_version !== 'string' ||
    typeof o.layout_version !== 'string' ||
    typeof o.block_id !== 'string' ||
    typeof o.source_signature !== 'string' ||
    typeof o.requested_font_family !== 'string' ||
    typeof o.resolved_font_id !== 'string' ||
    typeof o.resolved_font_family !== 'string' ||
    typeof o.resolved_postscript_name !== 'string' ||
    typeof o.resolved_font_style !== 'string' ||
    typeof o.font_fingerprint !== 'string' ||
    typeof o.normalized_text !== 'string' ||
    typeof o.vertical_align !== 'string'
  ) {
    return false;
  }

  // Validate Enums
  const layoutStatusValues = ['valid', 'stale', 'warning', 'overflow'];
  if (typeof o.layout_status !== 'string' || !layoutStatusValues.includes(o.layout_status)) {
    return false;
  }
  const layoutSourceValues = ['auto', 'manual', 'imported'];
  if (typeof o.layout_source !== 'string' || !layoutSourceValues.includes(o.layout_source)) {
    return false;
  }
  const horizontalAlignValues = ['left', 'center', 'right'];
  if (typeof o.horizontal_align !== 'string' || !horizontalAlignValues.includes(o.horizontal_align)) {
    return false;
  }
  const writingDirectionValues = ['horizontal', 'vertical'];
  if (typeof o.writing_direction !== 'string' || !writingDirectionValues.includes(o.writing_direction)) {
    return false;
  }
  const shapeTypeValues = ['bubble', 'narrative', 'sfx'];
  if (typeof o.shape_type !== 'string' || !shapeTypeValues.includes(o.shape_type)) {
    return false;
  }

  // Validate numeric and boolean values
  if (
    typeof o.font_size !== 'number' ||
    typeof o.line_height !== 'number' ||
    typeof o.tracking !== 'number' ||
    typeof o.rotation_deg !== 'number' ||
    typeof o.overflow_score !== 'number' ||
    typeof o.quality_score !== 'number' ||
    typeof o.overflow !== 'boolean'
  ) {
    return false;
  }

  // Validate explicit_lines
  if (!Array.isArray(o.explicit_lines)) {
    return false;
  }
  for (const line of o.explicit_lines) {
    if (typeof line !== 'string') {
      return false;
    }
  }

  // Validate PaddingSpec
  const p = o.padding as Record<string, unknown> | undefined;
  if (!p || typeof p !== 'object') {
    return false;
  }
  if (
    typeof p.top !== 'number' ||
    typeof p.right !== 'number' ||
    typeof p.bottom !== 'number' ||
    typeof p.left !== 'number'
  ) {
    return false;
  }

  const region = o.layout_region as Record<string, unknown> | undefined;
  if (!region || typeof region !== 'object') {
    return false;
  }
  if (
    typeof region.x !== 'number' ||
    typeof region.y !== 'number' ||
    typeof region.width !== 'number' ||
    typeof region.height !== 'number' ||
    typeof region.shape !== 'string' ||
    typeof region.confidence !== 'number' ||
    typeof region.source !== 'string' ||
    typeof region.safe_margin !== 'number'
  ) {
    return false;
  }

  // Validate Warnings
  if (!Array.isArray(o.warnings)) {
    return false;
  }
  const severityValues = ['warning', 'error'];
  for (const w of o.warnings) {
    if (!w || typeof w !== 'object') {
      return false;
    }
    const wObj = w as Record<string, unknown>;
    if (
      typeof wObj.code !== 'string' ||
      typeof wObj.message !== 'string' ||
      typeof wObj.block_id !== 'string' ||
      typeof wObj.severity !== 'string' ||
      !severityValues.includes(wObj.severity) ||
      !wObj.details ||
      typeof wObj.details !== 'object'
    ) {
      return false;
    }
  }

  // Validate Metrics
  if (!o.metrics || typeof o.metrics !== 'object') {
    return false;
  }

  return true;
}

const API_BASE = getApiBaseUrl();
export const CURRENT_LAYOUT_ENGINE_VERSION = '2.0.2';
export const CURRENT_SCHEMA_VERSION = '2.0.0';

/**
 * Triggers backend typesetting recomputation for a single block.
 */
export async function recomputeBlockTypesetting(blockId: string): Promise<TypesettingSpec> {
  const response = await apiFetch(`${API_BASE}/typesetting/recompute/block/${blockId}`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to recompute block typesetting: ${response.statusText}`);
  }
  return response.json() as Promise<TypesettingSpec>;
}

/**
 * Preflights typesetting layout parameters without database mutation.
 */
export async function preflightTypesetting(params: {
  block_id: string;
  translation?: string;
  font_family?: string;
  bold?: boolean;
  italic?: boolean;
  text_align?: string;
  text_direction?: string;
  balloon_type?: string;
  width?: number;
  height?: number;
}): Promise<TypesettingSpec> {
  const response = await apiFetch(`${API_BASE}/typesetting/preflight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    throw new Error(`Preflight typesetting request failed: ${response.statusText}`);
  }
  return response.json() as Promise<TypesettingSpec>;
}

export function isValidCanonicalSpec(spec: unknown): spec is TypesettingSpec {
  if (!isTypesettingSpec(spec) || spec.layout_status === 'stale') {
    return false;
  }
  const engine =
    spec.layout_engine_version || spec.layout_version;
  return (
    spec.schema_version === CURRENT_SCHEMA_VERSION &&
    engine === CURRENT_LAYOUT_ENGINE_VERSION
  );
}

/**
 * Style Judge v1 — batch or page-level multi-signal template suggestion.
 */
export async function runStyleJudge(params: {
  page_id?: string;
  block_ids?: string[];
  apply_template?: boolean;
  confidence_auto_threshold?: number;
  recompute_layout?: boolean;
}): Promise<{ count: number; results: unknown[] }> {
  const response = await apiFetch(`${API_BASE}/typesetting/style-judge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    throw new Error(`Style judge failed: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Record user accept/reject for feedback instrumentation.
 */
export async function recordTypesettingFeedback(params: {
  block_id: string;
  change_reason: 'accepted' | 'system_wrong' | 'user_preference';
  selected_template?: string;
  final_lines?: string[];
  suggested_template?: string;
  suggested_lines?: string[];
}): Promise<{ ok: boolean; event: unknown }> {
  const response = await apiFetch(`${API_BASE}/typesetting/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    throw new Error(`Feedback record failed: ${response.statusText}`);
  }
  return response.json();
}
