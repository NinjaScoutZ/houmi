import { describe, test, expect } from 'vitest';
import { fabricStrokeFromSpec, fabricStrokeNeedsUpdate } from '../utils/fabricStroke';
import { fabricGlowFromSpec, fabricGlowNeedsUpdate } from '../utils/fabricGlow';
import {
  captureAutoStyleSnapshot,
  snapshotToBulkUpdates,
} from '../utils/autoStyleSnapshot';
import { filterBlocksByDecision } from '../utils/decisionStatus';
import type { TypesettingSpec } from '../utils/typesetting';
import { DEFAULT_TEXT_TEMPLATES, templateBlockFields } from '../utils/textTemplates';

const okSpec = {
  schema_version: '2.0.0',
  layout_version: '2.0.2',
  layout_engine_version: '2.0.2',
  block_id: 'b1',
  source_signature: 's',
  layout_status: 'valid',
  layout_source: 'auto',
  decision_status: 'AUTO_APPLIED',
  requested_font_family: 'Tahoma',
  resolved_font_id: 't',
  resolved_font_family: 'Tahoma',
  resolved_postscript_name: 'Tahoma',
  resolved_font_style: 'regular',
  font_fingerprint: 'fp',
  font_size: 14,
  explicit_lines: ['x'],
  normalized_text: 'x',
  line_height: 16,
  tracking: 0,
  horizontal_align: 'center',
  vertical_align: 'center',
  writing_direction: 'horizontal',
  rotation_deg: 0,
  padding: { top: 0, right: 0, bottom: 0, left: 0 },
  layout_region: {
    x: 0, y: 0, width: 10, height: 10,
    shape: 'bubble', confidence: 1, source: 'm', safe_margin: 0,
  },
  shape_type: 'bubble',
  overflow: false,
  overflow_score: 0,
  quality_score: 1,
  warnings: [],
  metrics: {},
} as TypesettingSpec;

describe('fabricStrokeFromSpec', () => {
  test('off when zero', () => {
    expect(fabricStrokeFromSpec({ stroke_width: 0, stroke_color: '#fff' }).strokeWidth).toBe(0);
  });
  test('on when positive', () => {
    const p = fabricStrokeFromSpec({ stroke_width: 2, stroke_color: '#111111' });
    expect(p.strokeWidth).toBe(2);
    expect(p.stroke).toBe('#111111');
    expect(p.paintFirst).toBe('stroke');
  });
});

describe('fabricStrokeNeedsUpdate (Canvas hasChanged stroke path)', () => {
  test('stroke-only Spec change is dirty when existing textbox has no stroke', () => {
    const existing = { stroke: undefined, strokeWidth: 0, paintFirst: undefined };
    const next = fabricStrokeFromSpec({ stroke_width: 3, stroke_color: '#ffffff' });
    expect(fabricStrokeNeedsUpdate(existing, next)).toBe(true);
  });

  test('identical stroke is not dirty', () => {
    const next = fabricStrokeFromSpec({ stroke_width: 2, stroke_color: '#abcdef' });
    const existing = {
      stroke: next.stroke,
      strokeWidth: next.strokeWidth,
      paintFirst: next.paintFirst,
    };
    expect(fabricStrokeNeedsUpdate(existing, next)).toBe(false);
  });

  test('color-only stroke change is dirty', () => {
    const existing = { stroke: '#ffffff', strokeWidth: 2, paintFirst: 'stroke' as const };
    const next = fabricStrokeFromSpec({ stroke_width: 2, stroke_color: '#000000' });
    expect(fabricStrokeNeedsUpdate(existing, next)).toBe(true);
  });

  test('clearing stroke is dirty', () => {
    const existing = { stroke: '#ffffff', strokeWidth: 2, paintFirst: 'stroke' as const };
    const next = fabricStrokeFromSpec({ stroke_width: 0, stroke_color: '#ffffff' });
    expect(fabricStrokeNeedsUpdate(existing, next)).toBe(true);
  });
});

describe('fabricGlowFromSpec', () => {
  test('creates a centered diffuse shadow and preserves black channels', () => {
    const glow = fabricGlowFromSpec({
      outline_glow_radius: 8,
      outline_glow_color: '#000000',
      outline_glow_opacity: 0.4,
    });
    expect(glow).toMatchObject({
      color: 'rgba(0, 0, 0, 0.4)',
      blur: 8,
      offsetX: 0,
      offsetY: 0,
    });
  });

  test('is disabled when radius or opacity is zero', () => {
    expect(fabricGlowFromSpec({ outline_glow_radius: 0, outline_glow_opacity: 1 })).toBeNull();
    expect(fabricGlowFromSpec({ outline_glow_radius: 8, outline_glow_opacity: 0 })).toBeNull();
  });

  test('detects glow-only changes and clearing', () => {
    const glow = fabricGlowFromSpec({
      outline_glow_radius: 6,
      outline_glow_color: '#ffffff',
      outline_glow_opacity: 0.5,
    });
    expect(fabricGlowNeedsUpdate(null, glow)).toBe(true);
    expect(fabricGlowNeedsUpdate(glow, glow)).toBe(false);
    expect(fabricGlowNeedsUpdate(glow, null)).toBe(true);
  });
});

describe('autoStyleSnapshot', () => {
  test('round-trips bulk updates', () => {
    const blocks = [
      {
        id: 'a',
        font_family: 'Tahoma',
        font_size: 20,
        color_hex: '#000',
        bold: true,
        italic: false,
        text_align: 'center' as const,
        text_direction: 'horizontal' as const,
        balloon_type: 'bubble' as const,
        extra_metadata: { text_template_id: 'bubble', typesetting_spec: { x: 1 } },
      },
    ] as any[];
    const snap = captureAutoStyleSnapshot('page-1', blocks);
    expect(snap.pageId).toBe('page-1');
    expect(snap.blocks).toHaveLength(1);
    const updates = snapshotToBulkUpdates(snap);
    expect(updates[0].blockId).toBe('a');
    expect(updates[0].data.font_size).toBe(20);
    expect((updates[0].data.extra_metadata as any).text_template_id).toBe('bubble');
    // Mutating original must not mutate snapshot
    blocks[0].font_size = 99;
    expect(snap.blocks[0].font_size).toBe(20);
  });
});

describe('filterBlocksByDecision review queue', () => {
  test('filters NEEDS_REVIEW only', () => {
    const blocks = [
      {
        translation: 'a',
        extra_metadata: { typesetting_spec: { ...okSpec, decision_status: 'NEEDS_REVIEW' } },
      },
      {
        translation: 'b',
        extra_metadata: { typesetting_spec: { ...okSpec, decision_status: 'AUTO_APPLIED' } },
      },
      { translation: '', extra_metadata: {} },
    ];
    const q = filterBlocksByDecision(blocks as any, 'NEEDS_REVIEW');
    expect(q).toHaveLength(1);
    expect(q[0].translation).toBe('a');
  });
});

describe('template evidence isolation', () => {
  test('applying a preset does not overwrite the semantic balloon class', () => {
    const fields = templateBlockFields(DEFAULT_TEXT_TEMPLATES.narration, {
      detected_balloon_type: 'bubble',
    });

    expect(fields).not.toHaveProperty('balloon_type');
    expect(fields.extra_metadata).toMatchObject({
      detected_balloon_type: 'bubble',
      template_balloon_type: 'narrative',
    });
  });
});
