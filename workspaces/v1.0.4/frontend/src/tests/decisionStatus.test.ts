import { describe, test, expect } from 'vitest';
import { resolveDecisionBadge, countDecisions } from '../utils/decisionStatus';
import type { TypesettingSpec } from '../utils/typesetting';

const baseSpec = {
  schema_version: '2.0.0',
  layout_version: '2.0.2',
  layout_engine_version: '2.0.2',
  block_id: 'b1',
  source_signature: 'sig',
  layout_status: 'valid',
  layout_source: 'auto',
  decision_status: 'AUTO_APPLIED',
  requested_font_family: 'Tahoma',
  resolved_font_id: 'tahoma_regular',
  resolved_font_family: 'Tahoma',
  resolved_postscript_name: 'Tahoma',
  resolved_font_style: 'regular',
  font_fingerprint: 'fp',
  font_size: 14,
  explicit_lines: ['a'],
  normalized_text: 'a',
  line_height: 16,
  tracking: 0,
  horizontal_align: 'center',
  vertical_align: 'center',
  writing_direction: 'horizontal',
  rotation_deg: 0,
  padding: { top: 0, right: 0, bottom: 0, left: 0 },
  layout_region: {
    x: 0, y: 0, width: 100, height: 50,
    shape: 'bubble', confidence: 1, source: 'manual', safe_margin: 0,
  },
  shape_type: 'bubble',
  overflow: false,
  overflow_score: 0,
  quality_score: 80,
  warnings: [],
  metrics: {},
} as TypesettingSpec;

describe('decisionStatus', () => {
  test('AUTO_APPLIED badge', () => {
    const b = resolveDecisionBadge(baseSpec);
    expect(b.status).toBe('AUTO_APPLIED');
    expect(b.short).toBe('OK');
  });

  test('NEEDS_REVIEW badge', () => {
    const b = resolveDecisionBadge({ ...baseSpec, decision_status: 'NEEDS_REVIEW' });
    expect(b.status).toBe('NEEDS_REVIEW');
    expect(b.stroke).toMatch(/^#/);
  });

  test('stale when schema old', () => {
    const b = resolveDecisionBadge({ ...baseSpec, schema_version: '1.0.0', layout_version: '1.0.7' });
    expect(b.status).toBe('STALE');
  });

  test('countDecisions', () => {
    const counts = countDecisions([
      { translation: 'a', extra_metadata: { typesetting_spec: baseSpec } },
      {
        translation: 'b',
        extra_metadata: {
          typesetting_spec: { ...baseSpec, decision_status: 'NEEDS_REVIEW' },
        },
      },
      { translation: '', extra_metadata: {} },
    ]);
    expect(counts.with_text).toBe(2);
    expect(counts.AUTO_APPLIED).toBe(1);
    expect(counts.NEEDS_REVIEW).toBe(1);
  });
});
