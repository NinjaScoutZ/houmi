import { describe, it, expect } from 'vitest';
import { fabricFillFromSpec, gradientSignature } from '../utils/fabricGradient';

describe('fabricGradient Utility', () => {
  it('returns solid color fallback when gradient is disabled or absent', () => {
    const fill1 = fabricFillFromSpec( { color_hex: '#112233' }, 100, 50);
    expect(fill1).toBe('#112233');

    const fill2 = fabricFillFromSpec({
      color_hex: '#112233',
      gradient: { enabled: false, stops: [{ position: 0, color: '#ff0000' }, { position: 1, color: '#0000ff' }] } as any,
    }, 100, 50);
    expect(fill2).toBe('#112233');
  });

  it('creates linear fabric.Gradient with correct coordinates and color stops', () => {
    const spec = {
      color_hex: '#000000',
      gradient: {
        enabled: true,
        type: 'linear' as const,
        angle_deg: 90,
        stops: [
          { position: 0, color: '#ff0000', opacity: 1 },
          { position: 1, color: '#0000ff', opacity: 1 },
        ],
      } as any,
    };

    const gradient = fabricFillFromSpec(spec, 200, 100);
    expect(typeof gradient).toBe('object');
    expect((gradient as any).type).toBe('linear');
    expect((gradient as any).colorStops).toHaveLength(2);
    expect((gradient as any).colorStops[0].color).toBe('#ff0000');
    expect((gradient as any).colorStops[1].color).toBe('#0000ff');
  });

  it('creates radial fabric.Gradient correctly', () => {
    const spec = {
      color_hex: '#000000',
      gradient: {
        enabled: true,
        type: 'radial' as const,
        stops: [
          { position: 0, color: '#ffffff' },
          { position: 1, color: '#000000' },
        ],
      } as any,
    };

    const gradient = fabricFillFromSpec(spec, 100, 100);
    expect(typeof gradient).toBe('object');
    expect((gradient as any).type).toBe('radial');
    expect((gradient as any).coords?.r2).toBeGreaterThan(0);
  });

  it('generates distinct gradient signatures', () => {
    const g1 = { enabled: true, angle_deg: 90, stops: [{ position: 0, color: '#ff0000' }, { position: 1, color: '#00ff00' }] } as any;
    const g2 = { enabled: true, angle_deg: 180, stops: [{ position: 0, color: '#ff0000' }, { position: 1, color: '#00ff00' }] } as any;

    const sig1 = gradientSignature(g1);
    const sig2 = gradientSignature(g2);
    expect(sig1).not.toBe(sig2);
    expect(gradientSignature(null as any)).toBe('{"enabled":false}');
  });
});