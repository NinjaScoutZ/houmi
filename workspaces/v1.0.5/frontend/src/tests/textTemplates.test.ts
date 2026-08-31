import { describe, expect, test } from 'vitest';
import {
  DEFAULT_TEXT_TEMPLATES,
  buildTemplateReapplicationUpdates,
  listSemanticRolesFromTemplates,
  mergeDefaultTextTemplates,
  normalizeTextTemplates,
  resolveBlockTemplateRole,
  resolveGlobalTextTemplates,
  templateBlockFields,
} from '../utils/textTemplates';

describe('text templates', () => {
  test('falls back to production defaults for invalid project settings', () => {
    const t = normalizeTextTemplates(null);
    expect(Object.keys(t).sort()).toEqual(Object.keys(DEFAULT_TEXT_TEMPLATES).sort());
    expect(t.thought?.semantic_tag).toBe('คิดในใจ');
    expect(t.system?.semantic_tag).toBe('ระบบพูด');
  });

  test('merges missing built-in roles into legacy 4-template localStorage', () => {
    const legacy = {
      bubble: { ...DEFAULT_TEXT_TEMPLATES.bubble },
      narration: { ...DEFAULT_TEXT_TEMPLATES.narration },
      emphasis: { ...DEFAULT_TEXT_TEMPLATES.emphasis },
      sfx: { ...DEFAULT_TEXT_TEMPLATES.sfx },
    };
    const t = mergeDefaultTextTemplates(normalizeTextTemplates(legacy));
    expect(t.thought?.id).toBe('thought');
    expect(t.system?.id).toBe('system');
    expect(t.bubble.name).toBe(DEFAULT_TEXT_TEMPLATES.bubble.name);
  });

  test('keeps a valid font stack and merges padding defaults', () => {
    const templates = normalizeTextTemplates({
      custom: { id: 'custom', name: 'Custom', font_stack: ['Tahoma'], padding: { left: 30 } },
    });
    expect(templates.custom.font_stack).toEqual(['Tahoma']);
    expect(templates.custom.padding.left).toBe(30);
    expect(templates.custom.padding.top).toBe(DEFAULT_TEXT_TEMPLATES.bubble.padding.top);
  });

  test('normalizes legacy fallback stacks to one selected font', () => {
    const templates = normalizeTextTemplates({
      custom: { id: 'custom', name: 'Custom', font_stack: ['Calibri', 'Tahoma', 'Arial'] },
    });
    expect(templates.custom.font_stack).toEqual(['Calibri']);
  });

  test('keeps global templates instead of resetting from project defaults', () => {
    const globalTemplates = {
      custom: { ...DEFAULT_TEXT_TEMPLATES.bubble, id: 'custom', font_stack: ['Calibri'] },
    };
    const resolved = resolveGlobalTextTemplates(globalTemplates, DEFAULT_TEXT_TEMPLATES);
    expect(resolved.custom.font_stack).toEqual(['Calibri']);
    // Built-in roles are always merged in (legacy 4-template cache no longer hides thought/system)
    expect(resolved.bubble?.id).toBe('bubble');
    expect(resolved.thought?.id).toBe('thought');
  });

  test('applies only block fields and preserves existing metadata', () => {
    const fields = templateBlockFields(DEFAULT_TEXT_TEMPLATES.emphasis, { custom: true });
    expect(fields.bold).toBe(true);
    expect(fields.font_family).toBe(DEFAULT_TEXT_TEMPLATES.emphasis.font_stack[0]);
    expect(fields.extra_metadata).toMatchObject({ custom: true, text_template_id: 'emphasis' });
    expect(fields.extra_metadata).toMatchObject({ font_size_mode: 'auto', preferred_font_size: 72 });
    expect(fields.extra_metadata).toMatchObject({ tracking: 0, letter_spacing: 0 });
    // Font Template id == Semantic Role id
    expect(fields.extra_metadata).toMatchObject({
      semantic_role: 'emphasis',
      semantic_role_template_id: 'emphasis',
    });
  });

  test('keeps effect parameters while disabled and applies zero-width effects', () => {
    const template = normalizeTextTemplates({
      custom: {
        ...DEFAULT_TEXT_TEMPLATES.emphasis,
        id: 'custom',
        stroke_enabled: false,
        stroke_width: 6,
        outline_glow_enabled: false,
        outline_glow_radius: 14,
        outline_glow_opacity: 0.7,
      },
    }).custom;

    expect(template.stroke_width).toBe(6);
    expect(template.outline_glow_radius).toBe(14);
    const fields = templateBlockFields(template, {});
    expect(fields.extra_metadata).toMatchObject({
      stroke_width: 0,
      outline_glow_radius: 0,
      outline_glow_opacity: 0,
    });
  });

  test('semantic roles are the font template catalog', () => {
    const roles = listSemanticRolesFromTemplates(DEFAULT_TEXT_TEMPLATES);
    expect(roles.map((r) => r.id).sort()).toEqual(Object.keys(DEFAULT_TEXT_TEMPLATES).sort());
    expect(roles.find((r) => r.id === 'bubble')?.semantic_tag).toBe('ตัวละครพูด');
  });

  test('resolveBlockTemplateRole follows text_template_id after preset apply', () => {
    const before = resolveBlockTemplateRole(
      { font_family: 'Tahoma', font_size: 20, extra_metadata: {} },
      DEFAULT_TEXT_TEMPLATES,
    );
    expect(before.templateId).toBeNull();

    const fields = templateBlockFields(DEFAULT_TEXT_TEMPLATES.narration, {});
    const after = resolveBlockTemplateRole(
      {
        font_family: fields.font_family as string,
        font_size: fields.font_size as number,
        extra_metadata: fields.extra_metadata as Record<string, unknown>,
      },
      DEFAULT_TEXT_TEMPLATES,
    );
    expect(after.templateId).toBe('narration');
    expect(after.roleLabel).toBe('คำบรรยาย');
    expect(after.fontLabel).toContain(DEFAULT_TEXT_TEMPLATES.narration.font_stack[0]);
  });

  test('never includes source or translated text in a preset update', () => {
    const fields = templateBlockFields(DEFAULT_TEXT_TEMPLATES.narration, {
      custom: true,
      typesetting_spec: { explicit_lines: ['stale translated text'] },
    });

    expect(fields).not.toHaveProperty('source_text');
    expect(fields).not.toHaveProperty('translation');
    expect(fields.extra_metadata).not.toHaveProperty('typesetting_spec');
  });

  test('reapplies a saved template to existing layers on every project page', () => {
    const template = {
      ...DEFAULT_TEXT_TEMPLATES.bubble,
      min_font_size: 6,
      max_font_size: 80,
      color_hex: '#123456',
    };
    const block = (id: string, pageId: string, templateId?: string) => ({
      id,
      page_id: pageId,
      block_index: 0,
      x: 0,
      y: 0,
      width: 100,
      height: 50,
      rotation_deg: 0,
      source_text: '',
      translation: 'text',
      font_family: 'Tahoma',
      font_size: 36,
      color_hex: '#000000',
      bold: false,
      italic: false,
      text_direction: 'horizontal' as const,
      text_align: 'center' as const,
      balloon_type: 'bubble' as const,
      confidence: 1,
      extra_metadata: templateId ? { text_template_id: templateId, typesetting_spec: { font_size: 36 } } : {},
    });
    const updates = buildTemplateReapplicationUpdates({
      pages: [
        { text_blocks: [block('a', 'p1', 'bubble')] },
        { text_blocks: [block('b', 'p2', 'bubble'), block('c', 'p2')] },
      ],
    } as any, { bubble: template });

    expect(updates.map((update) => update.blockId)).toEqual(['a', 'b']);
    expect(updates[0].data.color_hex).toBe('#123456');
    expect(updates[0].data.extra_metadata).toMatchObject({
      min_font_size: 6,
      max_font_size: 80,
      font_size_mode: 'auto',
    });
    expect(updates[0].data.extra_metadata).not.toHaveProperty('typesetting_spec');
  });
});
