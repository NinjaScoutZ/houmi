import type { Project, TextBlock } from '../stores/projectStore';
import type { GradientSpec } from './typesetting';

export type WorkspaceMode = 'ocr' | 'typeset';

export interface TextTemplate {
  id: string;
  name: string;
  semantic_tag: string;
  font_stack: string[];
  font_size: number;
  auto_font_size?: boolean;
  min_font_size: number;
  max_font_size: number;
  color_hex: string;
  stroke_color: string;
  stroke_width: number;
  stroke_enabled?: boolean;
  outline_glow_color?: string;
  outline_glow_radius?: number;
  outline_glow_opacity?: number;
  outline_glow_enabled?: boolean;
  fill_type?: 'solid' | 'gradient';
  gradient_color_start?: string;
  gradient_color_end?: string;
  gradient_angle_deg?: number;
  gradient?: GradientSpec;
  drop_shadow_enabled?: boolean;
  drop_shadow_color?: string;
  drop_shadow_blur?: number;
  drop_shadow_offset_x?: number;
  drop_shadow_offset_y?: number;
  drop_shadow_opacity?: number;
  bold: boolean;
  italic: boolean;
  text_align: TextBlock['text_align'];
  text_direction: TextBlock['text_direction'];
  balloon_type: TextBlock['balloon_type'];
  line_height_ratio: number;
  letter_spacing: number;
  anti_alias?: 'smooth' | 'crisp' | 'strong' | 'sharp' | 'none';
  padding: { top: number; right: number; bottom: number; left: number };
}

export const DEFAULT_FONT_STACK = ['NotoSansThai'];

const disabledGradient = (color: string): GradientSpec => ({
  enabled: false,
  type: 'linear',
  stops: [{ position: 0, color }, { position: 1, color }],
  angle_deg: 0,
  scale: 100,
  reverse: false,
  dither: true,
  opacity: 1,
  blend_mode: 'normal',
});

export const DEFAULT_TEXT_TEMPLATES: Record<string, TextTemplate> = {
  bubble: {
    id: 'bubble', name: 'บทพูดทั่วไป', semantic_tag: 'ตัวละครพูด', font_stack: ['Baijam', 'TH Baijam', 'Baijam Bold', ...DEFAULT_FONT_STACK],
    font_size: 60, auto_font_size: true, min_font_size: 6, max_font_size: 96,
    color_hex: '#111111', stroke_color: '#ffffff', stroke_width: 0,
    gradient: disabledGradient('#111111'),
    bold: false, italic: false, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'bubble', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 12, right: 18, bottom: 12, left: 18 },
  },
  narration: {
    id: 'narration', name: 'คำบรรยาย', semantic_tag: 'คำบรรยาย', font_stack: ['TF PHETAI', 'TF Phetai', 'TF Phentai', ...DEFAULT_FONT_STACK],
    font_size: 52, auto_font_size: true, min_font_size: 6, max_font_size: 84,
    color_hex: '#111111', stroke_color: '#ffffff', stroke_width: 0,
    gradient: disabledGradient('#111111'),
    bold: false, italic: false, text_align: 'left', text_direction: 'horizontal',
    balloon_type: 'narrative', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 16, right: 20, bottom: 16, left: 20 },
  },
  emphasis: {
    id: 'emphasis', name: 'ตะโกน / เน้นเสียง', semantic_tag: 'ตะโกน', font_stack: ['TF PHETAI', 'TF Phetai', 'TF Phentai', 'Layiji_TarMineTine1', ...DEFAULT_FONT_STACK],
    font_size: 72, auto_font_size: true, min_font_size: 6, max_font_size: 120,
    color_hex: '#111111', stroke_color: '#ffffff', stroke_width: 2,
    gradient: disabledGradient('#111111'),
    bold: true, italic: true, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'bubble', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 10, right: 14, bottom: 10, left: 14 },
  },
  shout: {
    id: 'shout', name: 'ตะโกน / เสียงดัง', semantic_tag: 'ตะโกน', font_stack: ['TF PHETAI', 'TF Phetai', 'TF Phentai', 'Layiji_TarMineTine1', ...DEFAULT_FONT_STACK],
    font_size: 72, auto_font_size: true, min_font_size: 6, max_font_size: 120,
    color_hex: '#111111', stroke_color: '#ffffff', stroke_width: 2,
    gradient: disabledGradient('#111111'),
    bold: true, italic: true, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'bubble', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 10, right: 14, bottom: 10, left: 14 },
  },
  narrative: {
    id: 'narrative', name: 'คำบรรยาย', semantic_tag: 'คำบรรยาย', font_stack: ['TF PHETAI', 'TF Phetai', 'TF Phentai', ...DEFAULT_FONT_STACK],
    font_size: 52, auto_font_size: true, min_font_size: 6, max_font_size: 84,
    color_hex: '#111111', stroke_color: '#ffffff', stroke_width: 0,
    gradient: disabledGradient('#111111'),
    bold: false, italic: false, text_align: 'left', text_direction: 'horizontal',
    balloon_type: 'narrative', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 16, right: 20, bottom: 16, left: 20 },
  },
  sfx: {
    id: 'sfx', name: 'เสียงเอฟเฟกต์', semantic_tag: 'เสียงเอฟเฟกต์', font_stack: ['iannnnn TIGER Black', 'iannnnn TIGER', 'Tahoma', 'Impact'],
    font_size: 84, auto_font_size: true, min_font_size: 6, max_font_size: 152,
    color_hex: '#ffffff', stroke_color: '#111111', stroke_width: 3,
    gradient: disabledGradient('#ffffff'),
    bold: true, italic: true, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'sfx', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 4, right: 4, bottom: 4, left: 4 },
  },
  thought: {
    id: 'thought', name: 'คิดในใจ', semantic_tag: 'คิดในใจ', font_stack: ['TF PHETAI', 'TF Phetai', 'TF Phentai', ...DEFAULT_FONT_STACK],
    font_size: 52, auto_font_size: true, min_font_size: 6, max_font_size: 84,
    color_hex: '#444444', stroke_color: '#ffffff', stroke_width: 0,
    gradient: disabledGradient('#444444'),
    bold: false, italic: false, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'bubble', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 12, right: 18, bottom: 12, left: 18 },
  },
  whisper: {
    id: 'whisper', name: 'กระซิบ / แผ่วเบา', semantic_tag: 'กระซิบ', font_stack: ['TF PHETAI', 'TF Phetai', 'TF Phentai', 'FC Muffin', ...DEFAULT_FONT_STACK],
    font_size: 46, auto_font_size: true, min_font_size: 6, max_font_size: 72,
    color_hex: '#555555', stroke_color: '#ffffff', stroke_width: 0,
    gradient: disabledGradient('#555555'),
    bold: false, italic: false, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'bubble', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 12, right: 18, bottom: 12, left: 18 },
  },
  system: {
    id: 'system', name: 'ระบบพูด', semantic_tag: 'ระบบพูด', font_stack: ['IrisUPC', 'IrisPC', 'IrisUPC BOLD', 'IrisUPC-Bold', ...DEFAULT_FONT_STACK],
    font_size: 48, auto_font_size: true, min_font_size: 6, max_font_size: 72,
    color_hex: '#ffffff', stroke_color: '#000000', stroke_width: 3,
    gradient: disabledGradient('#ffffff'),
    bold: true, italic: false, text_align: 'center', text_direction: 'horizontal',
    balloon_type: 'narrative', line_height_ratio: 1.2, letter_spacing: 0, anti_alias: 'sharp',
    padding: { top: 10, right: 14, bottom: 10, left: 14 },
  },
};

export const normalizeTextTemplates = (value: unknown): Record<string, TextTemplate> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { ...DEFAULT_TEXT_TEMPLATES };
  }
  const templates: Record<string, TextTemplate> = {};
  for (const [key, raw] of Object.entries(value as Record<string, Partial<TextTemplate>>)) {
    if (!raw || typeof raw !== 'object') continue;
    const fallback = DEFAULT_TEXT_TEMPLATES[raw.id || key] || DEFAULT_TEXT_TEMPLATES.bubble;
    templates[key] = {
      ...fallback,
      ...raw,
      id: raw.id || key,
      name: raw.name || key,
      // A template deliberately owns exactly one installed font. Older projects
      // may still contain fallback stacks, so normalize them on read.
      font_stack: [(
        Array.isArray(raw.font_stack)
          ? raw.font_stack.find((font): font is string => typeof font === 'string' && font.trim().length > 0)
          : undefined
      ) || fallback.font_stack[0]],
      padding: { ...fallback.padding, ...(raw.padding || {}) },
      gradient: raw.gradient && typeof raw.gradient === 'object'
        ? {
          ...fallback.gradient,
          ...raw.gradient,
          stops: Array.isArray(raw.gradient.stops) && raw.gradient.stops.length >= 2
            ? raw.gradient.stops
            : (fallback.gradient?.stops || [{ position: 0, color: '#111111' }, { position: 1, color: '#ffffff' }]),
        }
        : fallback.gradient,
      semantic_tag: (raw.semantic_tag ?? fallback.semantic_tag ?? '').toString(),
      stroke_enabled: typeof raw.stroke_enabled === 'boolean'
        ? raw.stroke_enabled
        : Number(raw.stroke_width ?? fallback.stroke_width ?? 0) > 0,
      outline_glow_enabled: typeof raw.outline_glow_enabled === 'boolean'
        ? raw.outline_glow_enabled
        : Number(raw.outline_glow_radius ?? fallback.outline_glow_radius ?? 0) > 0
          && Number(raw.outline_glow_opacity ?? fallback.outline_glow_opacity ?? 0) > 0,
    };
  }
  if (Object.keys(templates).length === 0) {
    return { ...DEFAULT_TEXT_TEMPLATES };
  }
  return templates;
};

/** Ensure every DEFAULT_TEXT_TEMPLATES id exists; never drop user custom templates. */
export function mergeDefaultTextTemplates(
  stored: Record<string, TextTemplate>,
): Record<string, TextTemplate> {
  const merged: Record<string, TextTemplate> = { ...stored };
  for (const [id, def] of Object.entries(DEFAULT_TEXT_TEMPLATES)) {
    if (!merged[id]) {
      merged[id] = { ...def, padding: { ...def.padding }, font_stack: [...def.font_stack] };
    } else {
      // Backfill semantic_tag on old entries that lacked the field
      const cur = merged[id];
      if (!(cur.semantic_tag || '').trim() && (def.semantic_tag || '').trim()) {
        merged[id] = { ...cur, semantic_tag: def.semantic_tag };
      }
    }
  }
  return merged;
}

/** Semantic Role catalog = Font Templates (id is both). */
export function listSemanticRolesFromTemplates(
  templates: Record<string, TextTemplate>,
): Array<{ id: string; name: string; semantic_tag: string }> {
  return Object.values(templates).map((t) => ({
    id: t.id,
    name: t.name,
    semantic_tag: (t.semantic_tag || '').trim(),
  }));
}

/**
 * Resolve what the UI should show as the block's Role/Font Template.
 * Prefer text_template_id (what user applied); fall back to semantic_role / template name.
 */
export function resolveBlockTemplateRole(
  block: {
    font_family?: string;
    font_size?: number;
    extra_metadata?: Record<string, unknown> | null;
  },
  templates: Record<string, TextTemplate>,
): {
  templateId: string | null;
  roleLabel: string;
  fontLabel: string;
  semanticTag: string;
  template: TextTemplate | null;
} {
  const meta = block.extra_metadata || {};
  const templateId = String(
    meta.text_template_id
    || meta.semantic_role_template_id
    || meta.semantic_role
    || '',
  ).trim() || null;

  const template = templateId
    ? (templates[templateId]
      || Object.values(templates).find((t) => t.id === templateId)
      || null)
    : null;
  const roleLabel = template
    ? (template.semantic_tag || template.name || template.id)
    : String(meta.semantic_role_label || meta.semantic_role || '').trim() || '—';
  const fontLabel = template
    ? `${template.font_stack[0] || '?'} · ${template.font_size}px`
    : `${block.font_family || '?'} · ${block.font_size ?? '?'}px`;
  const semanticTag = template
    ? (template.semantic_tag || '').trim()
    : String(meta.semantic_role_label || '').trim();

  return { templateId, roleLabel, fontLabel, semanticTag, template };
}

export const resolveGlobalTextTemplates = (
  locallyStored: unknown,
  projectStored: unknown,
): Record<string, TextTemplate> => {
  // Prefer local global presets, else project, else defaults — always merge builtins.
  if (locallyStored && typeof locallyStored === 'object' && !Array.isArray(locallyStored)
    && Object.keys(locallyStored as object).length > 0) {
    return mergeDefaultTextTemplates(normalizeTextTemplates(locallyStored));
  }
  if (projectStored && typeof projectStored === 'object' && !Array.isArray(projectStored)
    && Object.keys(projectStored as object).length > 0) {
    return mergeDefaultTextTemplates(normalizeTextTemplates(projectStored));
  }
  return { ...DEFAULT_TEXT_TEMPLATES };
};

export const templateBlockFields = (
  template: TextTemplate,
  currentMetadata: Record<string, unknown> = {},
): Partial<TextBlock> => {
  const templateMetadata = { ...currentMetadata };
  delete templateMetadata.manual_font_size;
  delete templateMetadata.typesetting_spec;
  const isAuto = Boolean(template.auto_font_size || template.font_size === 0 || !template.font_size);
  const resolvedFontSize = isAuto
    ? (template.font_size || Number(currentMetadata.source_font_size) || 18)
    : template.font_size;
  return {
    font_family: template.font_stack[0],
    font_size: resolvedFontSize,
    color_hex: template.color_hex,
    bold: template.bold,
    italic: template.italic,
    text_align: template.text_align,
    text_direction: template.text_direction,
    extra_metadata: {
      ...templateMetadata,
      text_template_id: template.id,
      // Font Template id == Semantic Role id
      semantic_role: template.id,
      semantic_role_label: (template.semantic_tag || template.name || template.id).trim(),
      semantic_role_template_id: template.id,
      // Preset geometry hint only — not detector evidence for Style Judge
      template_balloon_type: template.balloon_type,
      font_size_mode: isAuto ? 'auto' : 'fixed',
      preferred_font_size: template.font_size || null,
      auto_font_size: isAuto,
      font_stack: template.font_stack,
      min_font_size: template.min_font_size || 6,
      max_font_size: template.max_font_size || 120,
      stroke_color: template.stroke_color,
      stroke_width: template.stroke_enabled === false ? 0 : template.stroke_width,
      outline_glow_color: template.outline_glow_color || template.stroke_color,
      outline_glow_radius: template.outline_glow_enabled === false
        ? 0
        : Number(template.outline_glow_radius || 0),
      outline_glow_opacity: template.outline_glow_enabled === false
        ? 0
        : Number(template.outline_glow_opacity || 0),
      line_height_ratio: template.line_height_ratio,
      letter_spacing: template.letter_spacing,
      tracking: template.letter_spacing,
      padding: template.padding,
      gradient: template.gradient,
    },
  };
};

export const buildTemplateReapplicationUpdates = (
  project: Pick<Project, 'pages'>,
  templates: Record<string, TextTemplate>,
): Array<{ blockId: string; data: Partial<TextBlock> }> => (
  project.pages.flatMap((page) => page.text_blocks.flatMap((block) => {
    const templateId = String(
      block.extra_metadata?.text_template_id
      || block.extra_metadata?.semantic_role_template_id
      || '',
    );
    const template = templates[templateId];
    if (!template) return [];
    return [{
      blockId: block.id,
      data: templateBlockFields(template, {
        ...(block.extra_metadata || {}),
        source_font_size: block.extra_metadata?.source_font_size ?? block.font_size,
      }),
    }];
  }))
);
