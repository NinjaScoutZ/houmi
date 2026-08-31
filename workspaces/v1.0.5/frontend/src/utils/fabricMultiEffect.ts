import * as fabric from 'fabric';

export interface DropShadowEffectProps {
  color: string;
  blur: number;
  offsetX: number;
  offsetY: number;
  opacity?: number;
}

export interface OuterGlowEffectProps {
  color: string;
  blur: number;
  opacity?: number;
}

export interface MangaTextEffects {
  dropShadow?: DropShadowEffectProps | null;
  outerGlow?: OuterGlowEffectProps | null;
}

function rgbaColor(hex: string, opacity: number): string {
  const clean = String(hex || '#000000').replace('#', '');
  const expanded = clean.length === 3
    ? clean.split('').map(char => char + char).join('')
    : clean.slice(0, 6).padEnd(6, '0');
  const parseChannel = (value: string) => {
    const parsed = Number.parseInt(value, 16);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const red = parseChannel(expanded.slice(0, 2));
  const green = parseChannel(expanded.slice(2, 4));
  const blue = parseChannel(expanded.slice(4, 6));
  return 'rgba(' + red + ', ' + green + ', ' + blue + ', ' + Math.max(0, Math.min(1, opacity)) + ')';
}

export function buildMangaEffects(
  spec: any,
  extraMetadata?: Record<string, any> | null,
): MangaTextEffects {
  const effects: MangaTextEffects = {
    dropShadow: null,
    outerGlow: null,
  };

  const ds = spec?.drop_shadow || extraMetadata?.detected_drop_shadow || extraMetadata?.drop_shadow;
  if (ds && ds.enabled !== false && (Number(ds.size ?? ds.blur ?? 0) > 0 || Number(ds.distance ?? 0) > 0)) {
    const blur = Math.max(0, Number(ds.size ?? ds.blur ?? 4));
    const distance = Number(ds.distance ?? 4);
    const angleDeg = Number(ds.angle_deg ?? ds.angle ?? 135);
    const rad = (angleDeg * Math.PI) / 180;
    const offsetX = Math.round(Math.cos(rad) * distance * 10) / 10;
    const offsetY = Math.round(Math.sin(rad) * distance * 10) / 10;
    const opacity = Number(ds.opacity ?? 0.85);
    const colorHex = String(ds.color ?? ds.color_hex ?? '#000000');

    effects.dropShadow = {
      color: rgbaColor(colorHex, opacity),
      blur,
      offsetX,
      offsetY,
      opacity,
    };
  }

  const og = spec?.outer_glow || extraMetadata?.detected_outer_glow || extraMetadata?.outer_glow;
  if (og && og.enabled !== false && Number(og.size ?? og.blur ?? og.radius ?? 0) > 0) {
    const blur = Math.max(0, Number(og.size ?? og.blur ?? og.radius ?? 6));
    const opacity = Number(og.opacity ?? 0.9);
    const colorHex = String(og.color ?? og.color_hex ?? '#ffffff');

    effects.outerGlow = {
      color: rgbaColor(colorHex, opacity),
      blur,
      opacity,
    };
  } else {
    const legacyRadius = Number(spec?.outline_glow_radius ?? extraMetadata?.outline_glow_radius ?? 0);
    const legacyOpacity = Number(spec?.outline_glow_opacity ?? extraMetadata?.outline_glow_opacity ?? 0);
    if (legacyRadius > 0.05 && legacyOpacity > 0) {
      const legacyColor = String(spec?.outline_glow_color ?? extraMetadata?.outline_glow_color ?? '#ffffff');
      effects.outerGlow = {
        color: rgbaColor(legacyColor, legacyOpacity),
        blur: legacyRadius,
        opacity: legacyOpacity,
      };
    }
  }

  return effects;
}

export function multiEffectNeedsUpdate(
  current: MangaTextEffects | null | undefined,
  next: MangaTextEffects | null | undefined,
): boolean {
  if (!current && !next) return false;
  if (!current || !next) return true;

  if (Boolean(current.dropShadow) !== Boolean(next.dropShadow)) return true;
  if (current.dropShadow && next.dropShadow) {
    if (
      current.dropShadow.color !== next.dropShadow.color ||
      current.dropShadow.blur !== next.dropShadow.blur ||
      current.dropShadow.offsetX !== next.dropShadow.offsetX ||
      current.dropShadow.offsetY !== next.dropShadow.offsetY
    ) {
      return true;
    }
  }

  if (Boolean(current.outerGlow) !== Boolean(next.outerGlow)) return true;
  if (current.outerGlow && next.outerGlow) {
    if (
      current.outerGlow.color !== next.outerGlow.color ||
      current.outerGlow.blur !== next.outerGlow.blur
    ) {
      return true;
    }
  }

  return false;
}

export function multiEffectSignature(effects?: MangaTextEffects | null): string {
  if (!effects) return 'none';
  const ds = effects.dropShadow
    ? 'ds:' + effects.dropShadow.color + ':' + effects.dropShadow.blur + ':' + effects.dropShadow.offsetX + ':' + effects.dropShadow.offsetY
    : 'ds:none';
  const og = effects.outerGlow
    ? 'og:' + effects.outerGlow.color + ':' + effects.outerGlow.blur
    : 'og:none';
  return ds + '|' + og;
}

export function applyMultiEffectTextRenderer(textbox: fabric.Textbox): void {
  const customTb = textbox as any;
  if (customTb.__multiEffectApplied) return;
  customTb.__multiEffectApplied = true;

  const originalRenderText = customTb._renderText || fabric.Textbox.prototype._renderText;
  customTb.__originalRenderText = originalRenderText;

  customTb._renderText = function (this: fabric.Textbox, ctx: CanvasRenderingContext2D) {
    const effects = (this as any).mangaEffects as MangaTextEffects | undefined;

    if (!effects || (!effects.outerGlow && !effects.dropShadow)) {
      return originalRenderText.call(this, ctx);
    }

    const hasStroke = Boolean(this.stroke && (this.strokeWidth || 0) > 0);
    const strokeW = this.strokeWidth || 0;

    const clearShadow = () => {
      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;
    };

    // Pass 1: Drop Shadow
    if (effects.dropShadow && (effects.dropShadow.blur > 0 || effects.dropShadow.offsetX !== 0 || effects.dropShadow.offsetY !== 0)) {
      ctx.save();
      ctx.shadowColor = effects.dropShadow.color;
      ctx.shadowBlur = effects.dropShadow.blur;
      ctx.shadowOffsetX = effects.dropShadow.offsetX;
      ctx.shadowOffsetY = effects.dropShadow.offsetY;

      if (hasStroke) {
        ctx.lineWidth = strokeW;
        ctx.strokeStyle = effects.dropShadow.color;
        ctx.lineJoin = this.strokeLineJoin || 'round';
        (this as any)._renderTextCommon(ctx, 'strokeText');
      } else {
        ctx.fillStyle = effects.dropShadow.color;
        (this as any)._renderTextCommon(ctx, 'fillText');
      }
      ctx.restore();
    }

    // Pass 2: Outer Glow
    if (effects.outerGlow && effects.outerGlow.blur > 0) {
      ctx.save();
      ctx.shadowColor = effects.outerGlow.color;
      ctx.shadowBlur = effects.outerGlow.blur;
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;

      if (hasStroke) {
        ctx.lineWidth = strokeW;
        ctx.strokeStyle = effects.outerGlow.color;
        ctx.lineJoin = this.strokeLineJoin || 'round';
        (this as any)._renderTextCommon(ctx, 'strokeText');
      } else {
        ctx.fillStyle = effects.outerGlow.color;
        (this as any)._renderTextCommon(ctx, 'fillText');
      }
      ctx.restore();
    }

    // Pass 3: Main Stroke Outline
    if (hasStroke) {
      ctx.save();
      clearShadow();
      ctx.lineWidth = strokeW;
      ctx.strokeStyle = this.stroke as string;
      ctx.lineJoin = this.strokeLineJoin || 'round';
      ctx.miterLimit = this.strokeMiterLimit || 4;
      (this as any)._renderTextCommon(ctx, 'strokeText');
      ctx.restore();
    }

    // Pass 4: Main Fill
    if (this.fill) {
      ctx.save();
      clearShadow();
      if (typeof this.fill === 'object' && (this.fill as any).toLive) {
        ctx.fillStyle = (this.fill as any).toLive(ctx);
      } else {
        ctx.fillStyle = this.fill as string;
      }
      (this as any)._renderTextCommon(ctx, 'fillText');
      ctx.restore();
    }
  };
}

export function removeMultiEffectTextRenderer(textbox: fabric.Textbox): void {
  const customTb = textbox as any;
  if (!customTb.__multiEffectApplied) return;
  if (customTb.__originalRenderText) {
    customTb._renderText = customTb.__originalRenderText;
    delete customTb.__originalRenderText;
  }
  delete customTb.__multiEffectApplied;
  delete customTb.mangaEffects;
}
