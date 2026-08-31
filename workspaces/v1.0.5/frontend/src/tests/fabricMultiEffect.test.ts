import { describe, it, expect, vi } from 'vitest';
import {
  buildMangaEffects,
  multiEffectNeedsUpdate,
  multiEffectSignature,
  applyMultiEffectTextRenderer,
  removeMultiEffectTextRenderer,
} from '../utils/fabricMultiEffect';

describe('fabricMultiEffect Utility', () => {
  it('builds drop shadow and outer glow from spec', () => {
    const spec = {
      drop_shadow: {
        enabled: true,
        color: '#ff0000',
        size: 8,
        distance: 6,
        angle_deg: 90,
        opacity: 0.8,
      },
      outer_glow: {
        enabled: true,
        color: '#ffff00',
        size: 10,
        opacity: 0.9,
      },
    };

    const effects = buildMangaEffects(spec);
    expect(effects.dropShadow).not.toBeNull();
    expect(effects.dropShadow?.blur).toBe(8);
    expect(effects.dropShadow?.offsetY).toBe(6);
    expect(effects.dropShadow?.color).toContain('255, 0, 0');

    expect(effects.outerGlow).not.toBeNull();
    expect(effects.outerGlow?.blur).toBe(10);
    expect(effects.outerGlow?.color).toContain('255, 255, 0');
  });

  it('falls back to legacy outline_glow fields when outer_glow is absent', () => {
    const spec = {
      outline_glow_radius: 5,
      outline_glow_color: '#00ff00',
      outline_glow_opacity: 0.7,
    };

    const effects = buildMangaEffects(spec);
    expect(effects.outerGlow).not.toBeNull();
    expect(effects.outerGlow?.blur).toBe(5);
    expect(effects.outerGlow?.color).toContain('0, 255, 0');
  });

  it('detects when effects need an update', () => {
    const eff1 = {
      dropShadow: { color: 'rgba(0,0,0,0.5)', blur: 4, offsetX: 2, offsetY: 2 },
      outerGlow: null,
    };
    const eff2 = {
      dropShadow: { color: 'rgba(0,0,0,0.5)', blur: 6, offsetX: 2, offsetY: 2 },
      outerGlow: null,
    };
    expect(multiEffectNeedsUpdate(eff1, eff2)).toBe(true);
    expect(multiEffectNeedsUpdate(eff1, eff1)).toBe(false);
  });

  it('generates stable signatures', () => {
    const eff = {
      dropShadow: { color: 'rgba(0,0,0,1)', blur: 4, offsetX: 2, offsetY: 2 },
      outerGlow: { color: 'rgba(255,255,255,1)', blur: 6 },
    };
    const sig1 = multiEffectSignature(eff);
    const sig2 = multiEffectSignature(eff);
    expect(sig1).toBe(sig2);
    expect(sig1).toContain('ds:rgba(0,0,0,1):4:2:2');
    expect(sig1).toContain('og:rgba(255,255,255,1):6');
  });

  it('attaches and detaches multi-effect renderer on a Textbox', () => {
    const dummyTextbox: any = {
      stroke: '#000000',
      strokeWidth: 2,
      fill: '#ffffff',
      _renderText: vi.fn(),
      _renderTextCommon: vi.fn(),
    };

    applyMultiEffectTextRenderer(dummyTextbox);
    expect(dummyTextbox.__multiEffectApplied).toBe(true);

    removeMultiEffectTextRenderer(dummyTextbox);
    expect(dummyTextbox.__multiEffectApplied).toBeUndefined();
  });
});
