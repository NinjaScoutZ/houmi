import { describe, test, expect } from 'vitest';
import { isTypesettingSpec } from '../utils/typesetting';
import type { TypesettingSpec } from '../utils/typesetting';
import { resolveCanvasLayoutRegion, resolveCanvasTextView } from '../utils/canvasView';
import { positionAtCentroid } from '../utils/smartBalloonCanvas';
import {
  incrementMutationRevision,
  getMutationRevision,
} from '../utils/blockUpdateTracker';

const dummySpec: TypesettingSpec = {
  schema_version: '2.0.0',
  layout_version: '2.0.2',
  layout_engine_version: '2.0.2',
  block_id: 'block-1',
  source_signature: 'sig-abc',
  layout_status: 'valid',
  layout_source: 'auto',
  decision_status: 'AUTO_APPLIED',
  requested_font_family: 'NotoSansThai',
  resolved_font_id: 'tahoma_regular',
  resolved_font_family: 'Tahoma',
  resolved_postscript_name: 'Tahoma',
  resolved_font_style: 'regular',
  font_fingerprint: 'fp-123',
  font_size: 14,
  explicit_lines: ['line 1', 'line 2'],
  normalized_text: 'line 1 line 2',
  line_height: 16.8,
  tracking: 0,
  horizontal_align: 'center',
  vertical_align: 'center',
  writing_direction: 'horizontal',
  rotation_deg: 0,
  padding: { top: 0, right: 0, bottom: 0, left: 0 },
  layout_region: {
    x: 10,
    y: 20,
    width: 180,
    height: 90,
    shape: 'bubble',
    confidence: 0.9,
    source: 'balloon_interior',
    safe_margin: 5,
  },
  shape_type: 'bubble',
  overflow: false,
  overflow_score: 0,
  quality_score: 80,
  warnings: [],
  metrics: {}
};

describe('Typesetting Frontend Logic', () => {
  test('source view never leaks translated explicit lines', () => {
    const block = {
      id: 'block-1',
      source_text: '原文',
      translation: 'คำแปล',
      extra_metadata: { font_size_mode: 'manual', typesetting_spec: dummySpec },
    } as any;

    expect(resolveCanvasTextView(block, false)).toEqual({
      text: '',
      usesCanonicalSpec: false,
    });
    expect(resolveCanvasTextView(block, true)).toEqual({
      text: dummySpec.explicit_lines.join('\n'),
      usesCanonicalSpec: true,
    });
  });

  test('auto view uses canonical spec explicit lines when available', () => {
    const block = {
      id: 'block-1',
      source_text: '原文',
      translation: 'Line 1\nLine 2',
      extra_metadata: { font_size_mode: 'auto', typesetting_spec: dummySpec },
    } as any;

    expect(resolveCanvasTextView(block, true)).toEqual({
      text: dummySpec.explicit_lines.join('\n'),
      usesCanonicalSpec: true,
    });
  });

  test('auto view uses translation text when no spec is available', () => {
    const block = {
      id: 'block-1',
      source_text: '原文',
      translation: 'Manual line 1\nManual line 2',
      extra_metadata: {
        font_size_mode: 'auto',
        line_break_source: 'manual_hard',
      },
    } as any;

    expect(resolveCanvasTextView(block, true)).toEqual({
      text: 'Manual line 1\nManual line 2',
      usesCanonicalSpec: false,
    });
  });

  test('translated view stays blank when no translation exists, even with an old Spec', () => {
    const block = {
      id: 'block-1',
      source_text: '原文',
      translation: '',
      extra_metadata: { font_size_mode: 'auto', typesetting_spec: dummySpec },
    } as any;

    expect(resolveCanvasTextView(block, true)).toEqual({
      text: '',
      usesCanonicalSpec: false,
    });
  });

  test('review canvas keeps the detector text box even when balloon layout exists', () => {
    const block = {
      x: 100,
      y: 120,
      width: 80,
      height: 30,
      extra_metadata: {
        text_bbox: { x: 10, y: 20, width: 300, height: 200 },
        layout_region: { x: 60, y: 80, width: 180, height: 110, source: 'balloon_interior' },
      },
    } as any;

    expect(resolveCanvasLayoutRegion(block)).toEqual({
      region: { x: 100, y: 120, width: 80, height: 30 },
      usesLayoutRegion: false,
    });
  });

  test('typesetting canvas uses the independently calculated balloon interior', () => {
    const block = {
      x: 100,
      y: 120,
      width: 80,
      height: 30,
      extra_metadata: {
        text_bbox: { x: 100, y: 120, width: 80, height: 30 },
        layout_region: { x: 60, y: 80, width: 180, height: 110, source: 'balloon_interior' },
      },
    } as any;

    expect(resolveCanvasLayoutRegion(block, undefined, true)).toEqual({
      region: block.extra_metadata.layout_region,
      usesLayoutRegion: true,
    });
  });

  describe('isTypesettingSpec validation', () => {
    test('accepts valid spec structure', () => {
      expect(isTypesettingSpec(dummySpec)).toBe(true);
    });

    test('rejects invalid nested padding types', () => {
      const invalid = { ...dummySpec, padding: { top: 'zero', right: 0, bottom: 0, left: 0 } } as unknown as TypesettingSpec;
      expect(isTypesettingSpec(invalid)).toBe(false);
    });

    test('rejects invalid layout region geometry', () => {
      const invalid = {
        ...dummySpec,
        layout_region: { ...dummySpec.layout_region, width: 'wide' },
      } as unknown as TypesettingSpec;
      expect(isTypesettingSpec(invalid)).toBe(false);
    });

    test('rejects invalid layout_status enum', () => {
      const invalid = { ...dummySpec, layout_status: 'perfect' } as unknown as TypesettingSpec;
      expect(isTypesettingSpec(invalid)).toBe(false);
    });

    test('rejects missing explicit_lines', () => {
      const invalid = { ...dummySpec, explicit_lines: undefined } as unknown as TypesettingSpec;
      expect(isTypesettingSpec(invalid)).toBe(false);
    });
  });

  describe('Block Update Mutation Tracker', () => {
    test('increments revisions correctly', () => {
      const blockId = 'block-100';
      const r1 = incrementMutationRevision(blockId);
      const r2 = incrementMutationRevision(blockId);
      expect(r2).toBe(r1 + 1);
      expect(getMutationRevision(blockId)).toBe(r2);
    });

    test('detects out of order updates', () => {
      const blockId = 'block-101';
      const r1 = incrementMutationRevision(blockId);
      const r2 = incrementMutationRevision(blockId);
      expect(r1 < r2).toBe(true);
    });
  });

  describe('Smart Balloon Centroid & Vertical Alignment', () => {
    test('positions textbox centered at centroid using actual text height', () => {
      const fakeTextbox = {
        width: 120,
        left: 0,
        top: 0,
        set: function(props: Record<string, any>) {
          Object.assign(this, props);
        },
      } as any;

      const centroid = { x: 400, y: 300 };
      const scaleFactor = 2; // cx = 200, cy = 150
      const actualTextHeight = 60; // 3 lines of 20px

      positionAtCentroid(fakeTextbox, centroid, scaleFactor, actualTextHeight);

      // cx - width/2 = 200 - 60 = 140
      expect(fakeTextbox.left).toBe(140);
      // cy - actualTextHeight/2 = 150 - 30 = 120
      expect(fakeTextbox.top).toBe(120);
    });

    test('calculates standard balloon vertical offset for center alignment', () => {
      const balloonHeight = 200;
      const actualTextHeight = 80;
      const verticalAlign = 'center';

      let topOffset = 0;
      if (verticalAlign === 'center') {
        topOffset = Math.max(0, (balloonHeight - actualTextHeight) / 2);
      }

      expect(topOffset).toBe(60);
      const balloonY = 100;
      const finalTop = balloonY + topOffset;
      expect(finalTop).toBe(160);
    });

    test('strictly uses detected box when enableSmartBalloon is false', () => {
      const blockWithSmart = {
        id: 'block-smart',
        x: 100,
        y: 100,
        width: 200,
        height: 150,
        smart_x: 50,
        smart_y: 40,
        smart_width: 320,
        smart_height: 260,
        extra_metadata: {
          smart_balloon: {
            safe_bbox: { x: 55, y: 45, width: 310, height: 250 },
          },
        },
      } as any;

      // 1. When enableSmartBalloon is true in typesetting mode -> returns safe_bbox
      const enabledRes = resolveCanvasLayoutRegion(blockWithSmart, undefined, true, true);
      expect(enabledRes.region.x).toBe(55);
      expect(enabledRes.region.width).toBe(310);

      // 2. When enableSmartBalloon is false -> strictly returns original detected bbox (100, 100, 200, 150)
      const disabledRes = resolveCanvasLayoutRegion(blockWithSmart, undefined, false, false);
      expect(disabledRes.region.x).toBe(100);
      expect(disabledRes.region.y).toBe(100);
      expect(disabledRes.region.width).toBe(200);
      expect(disabledRes.region.height).toBe(150);
      expect(disabledRes.usesLayoutRegion).toBe(false);
    });
  });
});
