import os
import math
import logging
from pathlib import Path
from typing import Any, Optional
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageChops
from sqlalchemy.orm import Session
from app.models.all_models import Page, TextBlock
from app.services.typesetting.tracking import (
    iter_tracked_graphemes,
    measure_text_with_tracking,
)

logger = logging.getLogger("houmi-renderer")

# Default Windows/Local font files paths fallback
FONT_FALLBACKS = [
    "tahoma.ttf",
    "arial.ttf",
    "calibri.ttf",
    "msunicod.ttf"
]


def _apply_synthetic_italic(layer: Image.Image, angle_degrees: float = 12.0) -> Image.Image:
    """Apply a centered faux-italic shear without changing the layer bounds."""
    shear = math.tan(math.radians(angle_degrees))
    center_y = layer.height / 2.0
    try:
        affine = Image.Transform.AFFINE
        resample = Image.Resampling.BICUBIC
    except AttributeError:  # Pillow < 9 compatibility
        affine = Image.AFFINE
        resample = Image.BICUBIC
    return layer.transform(
        layer.size,
        affine,
        (1.0, shear, -shear * center_y, 0.0, 1.0, 0.0),
        resample=resample,
    )


def _apply_drop_shadow(layer: Image.Image, spec: Any) -> Image.Image:
    """Composite a Photoshop-accurate drop shadow behind an RGBA text layer."""
    if not spec or not getattr(spec, "enabled", False):
        return layer
    size = max(0.5, float(getattr(spec, "size", 5.0) or 5.0))
    opacity = max(0.0, min(1.0, float(getattr(spec, "opacity", 0.75) or 0.75)))
    distance = float(getattr(spec, "distance", 5.0) or 5.0)
    angle_deg = float(getattr(spec, "angle_deg", 120.0) or 120.0)
    color = str(getattr(spec, "color", "#000000") or "#000000")

    try:
        red, green, blue = ImageColor.getrgb(color)[:3]
    except Exception:
        red, green, blue = (0, 0, 0)

    rad = math.radians(angle_deg)
    # Photoshop light source angle: light at angle, shadow falls in opposite direction (angle + 180 or cos/sin)
    dx = int(round(-distance * math.cos(rad)))
    dy = int(round(distance * math.sin(rad)))

    # Get alpha mask of text
    alpha = layer.getchannel("A")
    blurred_alpha = alpha.filter(ImageFilter.GaussianBlur(radius=size))
    blurred_alpha = blurred_alpha.point(lambda a: min(255, round(a * opacity)))

    shadow = Image.new("RGBA", layer.size, (red, green, blue, 0))
    # Offset shadow
    shadow_alpha = Image.new("L", layer.size, 0)
    shadow_alpha.paste(blurred_alpha, (dx, dy))
    shadow.putalpha(shadow_alpha)

    return Image.alpha_composite(shadow, layer)


def _apply_inner_shadow(layer: Image.Image, spec: Any) -> Image.Image:
    """Composite a Photoshop-accurate inner shadow inside an RGBA text layer."""
    if not spec or not getattr(spec, "enabled", False):
        return layer
    size = max(0.5, float(getattr(spec, "size", 5.0) or 5.0))
    opacity = max(0.0, min(1.0, float(getattr(spec, "opacity", 0.75) or 0.75)))
    distance = float(getattr(spec, "distance", 5.0) or 5.0)
    angle_deg = float(getattr(spec, "angle_deg", 120.0) or 120.0)
    color = str(getattr(spec, "color", "#000000") or "#000000")

    try:
        red, green, blue = ImageColor.getrgb(color)[:3]
    except Exception:
        red, green, blue = (0, 0, 0)

    rad = math.radians(angle_deg)
    dx = int(round(-distance * math.cos(rad)))
    dy = int(round(distance * math.sin(rad)))

    alpha = layer.getchannel("A")
    inv_alpha = ImageOps.invert(alpha)
    # Offset inverted alpha
    offset_inv = Image.new("L", layer.size, 255)
    offset_inv.paste(inv_alpha, (dx, dy))
    blurred_inv = offset_inv.filter(ImageFilter.GaussianBlur(radius=size))

    # Mask inner shadow to only exist inside the text glyphs
    inner_alpha = ImageChops.multiply(alpha, blurred_inv)
    inner_alpha = inner_alpha.point(lambda a: min(255, round(a * opacity)))

    inner_layer = Image.new("RGBA", layer.size, (red, green, blue, 0))
    inner_layer.putalpha(inner_alpha)

    return Image.alpha_composite(layer, inner_layer)


def _apply_outline_glow(
    layer: Image.Image,
    radius: float,
    color: str,
    opacity: float,
) -> Image.Image:
    """Composite a centered, diffuse outline glow behind an RGBA text layer."""
    radius = max(0.0, float(radius or 0.0))
    opacity = max(0.0, min(1.0, float(opacity or 0.0)))
    if radius <= 0.05 or opacity <= 0:
        return layer

    try:
        red, green, blue = ImageColor.getrgb(str(color or "#ffffff"))[:3]
    except (TypeError, ValueError):
        red, green, blue = (255, 255, 255)

    blurred_alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(radius=radius))
    # Boost alpha curve proportionally to radius so diffuse glows remain visible
    boost = max(1.0, min(4.0, (radius / 6.0) ** 0.5))
    blurred_alpha = blurred_alpha.point(lambda alpha: min(255, round(alpha * boost * opacity)))
    glow = Image.new("RGBA", layer.size, (red, green, blue, 0))
    glow.putalpha(blurred_alpha)
    return Image.alpha_composite(glow, layer)

def get_font_handle(font_name: str, size: float, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Tries to load requested font using FontRegistry, falls back deterministically if not found."""
    from app.services.font_registry import font_registry
    
    # Resolve requested font family and style from the Font Registry
    entry = font_registry.resolve_font(font_name, bold=bold, italic=italic)
    
    try:
        return ImageFont.truetype(str(entry.file_path), int(size))
    except Exception as e:
        logger.error(f"Failed to load font from path '{entry.file_path}': {e}")
        if os.environ.get("PRODUCTION_MODE", "0") == "1":
            raise ValueError(f"Production Font Error: Failed to load font file '{entry.file_path}': {e}")
        return ImageFont.load_default()

import unicodedata

def tokenize_text(text: str) -> list:
    """Splits text into chunks, separating CJK characters individually,
    using Zero-Width Space (\u200B) for Thai word segments,
    while keeping Latin words intact."""
    chunks = []
    current_latin = []
    
    # If the text already has zero-width spaces (e.g. segmented Thai),
    # we can tokenize using \u200B as a delimiter.
    has_zwsp = "\u200B" in text
    
    for char in text:
        val = ord(char)
        category = unicodedata.category(char)
        is_combining = category.startswith("M")
        
        if is_combining:
            if current_latin:
                current_latin.append(char)
            elif chunks:
                chunks[-1] = chunks[-1] + char
            else:
                chunks.append(char)
            continue
            
        if char == "\u200B":
            if current_latin:
                chunks.append("".join(current_latin))
                current_latin = []
            chunks.append("\u200B")
            continue

        # CJK range
        is_cjk = (
            (0x3000 <= val <= 0x9FFF) or
            (0xFF00 <= val <= 0xFFEF) or
            (0xAC00 <= val <= 0xD7AF)
        )
        
        # Thai range
        is_thai = (0x0E00 <= val <= 0x0E7F)
        
        if is_cjk or (is_thai and not has_zwsp):
            # If CJK, or Thai without zero-width spaces, split character-by-character
            if current_latin:
                chunks.append("".join(current_latin))
                current_latin = []
            chunks.append(char)
        elif char.isspace():
            if current_latin:
                chunks.append("".join(current_latin))
                current_latin = []
            chunks.append(" ")
        else:
            current_latin.append(char)
            
    if current_latin:
        chunks.append("".join(current_latin))
        
    return chunks

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list:
    """Wraps text lines by calculating accumulating width to avoid spilling outside balloons, supporting CJK/Thai."""
    lines = []
    paragraphs = text.split('\n')
    
    for para in paragraphs:
        chunks = tokenize_text(para)
        current_line = []
        
        for chunk in chunks:
            if chunk == " ":
                if not current_line:
                    continue
                test_line = "".join(current_line) + " "
            elif chunk == "\u200B":
                # Zero-width space has no width and doesn't render characters,
                # but serves as a wrap boundary.
                test_line = "".join(current_line)
            else:
                test_line = "".join(current_line) + chunk
                
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
            
            if w <= max_width or not current_line:
                if chunk == " ":
                    current_line.append(" ")
                elif chunk == "\u200B":
                    current_line.append("\u200B")
                else:
                    current_line.append(chunk)
            else:
                # Wrap line
                line_str = "".join(current_line).replace("\u200B", "").rstrip()
                if line_str:
                    lines.append(line_str)
                if chunk != " " and chunk != "\u200B":
                    current_line = [chunk]
                else:
                    current_line = []
                    
        if current_line:
            line_str = "".join(current_line).replace("\u200B", "").rstrip()
            if line_str:
                lines.append(line_str)
                
    return lines

def find_fitting_font_size(text_val: str, font_name: str, bold: bool, block_w: float, block_h: float, balloon_type: str = "bubble", italic: bool = False) -> tuple:
    """Finds the largest font size that fits the text inside the block dimensions using binary search, with elliptical constraints for bubbles."""
    import math
    from app.services.font_registry import font_registry
    
    block_w = max(10.0, block_w)
    block_h = max(10.0, block_h)
    
    # Resolve the font family and style ONCE per layout operation to prevent duplicate warnings in binary search loop
    resolved_entry = font_registry.resolve_font(font_name, bold=bold, italic=italic)
    
    low = 10
    high = 100
    best_size = low
    best_font = None
    
    ellipse_safety_factor = 0.88
    rect_safety_factor = 0.95
    max_allowed_height = block_h * 0.95
    
    while low <= high:
        mid = (low + high) // 2
        try:
            font = ImageFont.truetype(str(resolved_entry.file_path), int(mid))
        except Exception as e:
            if os.environ.get("PRODUCTION_MODE", "0") == "1":
                raise ValueError(f"Production Font Error: Failed to load font file '{resolved_entry.file_path}': {e}")
            font = ImageFont.load_default()
            
        wrapped_lines = wrap_text(text_val, font, block_w)
        
        line_heights = []
        for line in wrapped_lines:
            bbox = font.getbbox(line)
            line_heights.append(bbox[3] - bbox[1])
            
        total_text_height = sum(line_heights) + (len(wrapped_lines) - 1) * 4
        
        fits = True
        if total_text_height > max_allowed_height:
            fits = False
        else:
            for i, line in enumerate(wrapped_lines):
                # Calculate text width
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                
                if balloon_type == "bubble":
                    # Vertical center of this line
                    line_center_from_text_top = sum(line_heights[:i]) + line_heights[i] / 2 + i * 4
                    # Vertical position relative to block center
                    y = line_center_from_text_top - total_text_height / 2
                    
                    half_h = block_h / 2
                    normalized_y = abs(y) / half_h
                    
                    if normalized_y >= 1.0:
                        fits = False
                        break
                        
                    allowed_width = block_w * math.sqrt(1 - normalized_y**2) * ellipse_safety_factor
                    if line_width > allowed_width:
                        fits = False
                        break
                else:
                    if line_width > block_w * rect_safety_factor:
                        fits = False
                        break
                        
        if fits:
            best_size = mid
            best_font = font
            low = mid + 1
        else:
            high = mid - 1
            
    if best_font is None:
        best_size = 12
        try:
            best_font = ImageFont.truetype(str(resolved_entry.file_path), int(best_size))
        except Exception as e:
            if os.environ.get("PRODUCTION_MODE", "0") == "1":
                raise ValueError(f"Production Font Error: Failed to load font file '{resolved_entry.file_path}': {e}")
            best_font = ImageFont.load_default()
        
    return best_font, best_size

def render_page_text(page_id: str, db: Session, persist: bool = True) -> Path:
    """
    Renders text translations onto the cleaned/inpainted manga page image.
    Uses PIL to draw text with proper wrapper scaling.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    # Use inpainted image if available, fallback to original source image
    base_image_path = Path(page.inpainted_image_path) if page.inpainted_image_path else Path(page.source_image_path)
    
    if not base_image_path.exists():
        # Double fallback to source path
        base_image_path = Path(page.source_image_path)
        if not base_image_path.exists():
            raise FileNotFoundError(f"Base image not found at {base_image_path}")

    logger.info(f"Rendering text on base image: {base_image_path.name}")
    img = Image.open(base_image_path).convert("RGBA")
    txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    for block in page.text_blocks:
        # Rendered output contains authored translations only, never OCR.
        text_val = block.translation or ""
        if not text_val.strip():
            continue

        # Emit preflight warning if vertical text direction is requested but not fully supported in layout renderer
        if getattr(block, "text_direction", "horizontal") == "vertical":
            logger.warning(
                f"[PREFLIGHT WARNING] Block {block.id} requests vertical text direction, "
                f"which is not fully supported by standard horizontal layout renderer. Rendering horizontally."
            )

        # Use backend authoritative typesetting spec
        from app.services.typesetting import get_effective_typesetting_spec
        spec = get_effective_typesetting_spec(block)
        
        try:
            from app.services.font_registry import font_registry
            requested_bold = bool(getattr(spec, "bold", False))
            requested_italic = bool(getattr(spec, "italic", False))
            resolved_entry = font_registry.resolve_font(
                spec.resolved_font_family,
                bold=requested_bold,
                italic=requested_italic,
            )
            synthetic_italic = requested_italic and "italic" not in resolved_entry.style.lower()
            if resolved_entry.fingerprint != spec.font_fingerprint:
                logger.warning(
                    f"Font fingerprint mismatch for block {block.id}. "
                    f"Spec fingerprint: {spec.font_fingerprint}, loaded font fingerprint: {resolved_entry.fingerprint}"
                )
            font = ImageFont.truetype(str(resolved_entry.file_path), int(spec.font_size))
        except Exception as e:
            if os.environ.get("PRODUCTION_MODE", "0") == "1":
                raise e
            font = ImageFont.load_default()
            synthetic_italic = bool(getattr(spec, "italic", False))

        wrapped_lines = spec.explicit_lines
        
        # Match Fabric's fixed line boxes. Pillow's default text origin is an
        # ascender/baseline origin, so drawing directly at current_y shifts Thai
        # glyphs and combining marks compared with the editor preview.
        line_height = float(spec.line_height)
        total_text_height = len(wrapped_lines) * line_height
        
        # Semantic parity: color comes from Spec v2, not live block fields
        try:
            raw_hex = getattr(spec, "color_hex", None) or block.color_hex or "#000000"
            hex_color = str(raw_hex).lstrip('#')
            if len(hex_color) == 3:
                hex_color = "".join(c * 2 for c in hex_color)
            r = int(hex_color[0:2], 16) if len(hex_color) >= 2 else 0
            g = int(hex_color[2:4], 16) if len(hex_color) >= 4 else 0
            b = int(hex_color[4:6], 16) if len(hex_color) >= 6 else 0
            color_tuple = (r, g, b, 255)
        except (ValueError, IndexError, TypeError):
            color_tuple = (0, 0, 0, 255)  # Fallback to black on invalid hex

        # Render translations inside the authoritative balloon layout region.
        region = spec.layout_region
        b_w = max(1, int(round(region.width)))
        b_h = max(1, int(round(region.height)))

        # Expand the text layer to accommodate overflow so text is never
        # silently clipped.  The actual text height may exceed the box when
        # the typesetter deliberately allows overflow (e.g. locked font size).
        render_h = max(b_h, int(round(total_text_height)) + 4)
        # Vertical offset applied when pasting: negative means the layer
        # starts *above* the box origin so that centered text is still
        # centered relative to the original box position.
        overflow_offset_y = 0
        if render_h > b_h:
            overflow_offset_y = -int(round((render_h - b_h) / 2))

        block_txt = Image.new("RGBA", (b_w, render_h), (255, 255, 255, 0))
        block_draw = ImageDraw.Draw(block_txt)
        gradient_spec = getattr(spec, "gradient", None)
        gradient_enabled = bool(gradient_spec and getattr(gradient_spec, "enabled", False))
        gradient_mask = Image.new("L", (b_w, render_h), 0) if gradient_enabled else None
        gradient_mask_draw = ImageDraw.Draw(gradient_mask) if gradient_mask is not None else None

        # Padding extraction
        padding = spec.padding
        inner_w = b_w - padding.left - padding.right
        inner_h = render_h - padding.top - padding.bottom

        # Vertical alignment
        valign = spec.vertical_align or "center"
        if valign == "top":
            current_y = padding.top
        elif valign == "bottom":
            current_y = render_h - padding.bottom - total_text_height
        else: # center
            current_y = padding.top + (inner_h - total_text_height) / 2

        for line in wrapped_lines:
            try:
                bbox = font.getbbox(line)
                line_w = measure_text_with_tracking(
                    font,
                    line,
                    float(spec.font_size),
                    float(getattr(spec, "tracking", 0) or 0),
                )
                glyph_h = bbox[3] - bbox[1]
            except Exception:
                bbox = (0, 0, 0, int(spec.font_size))
                line_w = measure_text_with_tracking(
                    font,
                    line,
                    float(spec.font_size),
                    float(getattr(spec, "tracking", 0) or 0),
                )
                glyph_h = spec.font_size
                
            # Align the visible glyph bounds, not Pillow's font origin.
            align = getattr(spec, "text_align", None) or spec.horizontal_align or "center"
            if align == "center":
                visible_x = padding.left + (inner_w - line_w) / 2
            elif align == "right":
                visible_x = b_w - padding.right - line_w
            else: # left
                visible_x = padding.left

            visible_y = current_y + (line_height - glyph_h) / 2
            draw_x = visible_x - bbox[0]
            draw_y = visible_y - bbox[1]

            # Draw text line on local block layer — stroke + tracking from Spec v2
            from app.services.typesetting.stroke import draw_text_with_spec_stroke

            tracking = float(getattr(spec, "tracking", 0) or 0)
            tracked_clusters = list(
                iter_tracked_graphemes(font, line, float(spec.font_size), tracking)
            )
            if tracking and len(tracked_clusters) > 1:
                for cluster, offset_x in tracked_clusters:
                    draw_text_with_spec_stroke(
                        block_draw,
                        (float(draw_x) + offset_x, draw_y),
                        cluster,
                        font=font,
                        fill=(0, 0, 0, 0) if gradient_enabled else color_tuple,
                        stroke_width=getattr(spec, "stroke_width", 0) or 0,
                        stroke_color=getattr(spec, "stroke_color", None) or "#ffffff",
                    )
                    if gradient_mask_draw is not None:
                        gradient_mask_draw.text((float(draw_x) + offset_x, draw_y), cluster, font=font, fill=255)
            else:
                draw_text_with_spec_stroke(
                    block_draw,
                    (draw_x, draw_y),
                    line,
                    font=font,
                    fill=(0, 0, 0, 0) if gradient_enabled else color_tuple,
                    stroke_width=getattr(spec, "stroke_width", 0) or 0,
                    stroke_color=getattr(spec, "stroke_color", None) or "#ffffff",
                )
                if gradient_mask_draw is not None:
                    gradient_mask_draw.text((draw_x, draw_y), line, font=font, fill=255)
            current_y += line_height

        if gradient_enabled and gradient_mask is not None:
            from app.services.typesetting.gradient import gradient_image
            block_txt.paste(gradient_image(b_w, render_h, gradient_spec), (0, 0), gradient_mask)

        if synthetic_italic:
            block_txt = _apply_synthetic_italic(block_txt)

        # 1. Inner Shadow (drawn inside text glyphs)
        inner_shadow_spec = getattr(spec, "inner_shadow", None)
        if inner_shadow_spec and getattr(inner_shadow_spec, "enabled", False):
            block_txt = _apply_inner_shadow(block_txt, inner_shadow_spec)

        # 2. Outer Glow (drawn diffuse around text)
        outer_glow_spec = getattr(spec, "outer_glow", None)
        if outer_glow_spec and getattr(outer_glow_spec, "enabled", False):
            block_txt = _apply_outline_glow(
                block_txt,
                getattr(outer_glow_spec, "size", 0) or 0,
                getattr(outer_glow_spec, "color", None) or "#ffffff",
                getattr(outer_glow_spec, "opacity", 0) or 0,
            )
        else:
            block_txt = _apply_outline_glow(
                block_txt,
                getattr(spec, "outline_glow_radius", 0) or 0,
                getattr(spec, "outline_glow_color", None) or "#ffffff",
                getattr(spec, "outline_glow_opacity", 0) or 0,
            )

        # 3. Drop Shadow (drawn behind text and glow)
        drop_shadow_spec = getattr(spec, "drop_shadow", None)
        if drop_shadow_spec and getattr(drop_shadow_spec, "enabled", False):
            block_txt = _apply_drop_shadow(block_txt, drop_shadow_spec)

        # Rotate and paste the block layer onto the page text layer
        rotation = spec.rotation_deg
        paste_x_base = int(round(region.x))
        paste_y_base = int(round(region.y)) + overflow_offset_y
        if abs(rotation) > 0.1:
            try:
                resample_filter = Image.Resampling.BICUBIC
            except AttributeError:
                resample_filter = Image.BICUBIC
                
            # Rotate by negative angle because PIL rotate is CCW, whereas screen/YOLO angle is CW
            rotated_txt = block_txt.rotate(-rotation, resample=resample_filter, expand=True)
            
            # Keep center aligned
            cx = region.x + region.width / 2
            cy = region.y + region.height / 2
            paste_x = cx - rotated_txt.width / 2
            paste_y = cy - rotated_txt.height / 2
            
            txt_layer.paste(rotated_txt, (int(round(paste_x)), int(round(paste_y))), rotated_txt)
        else:
            txt_layer.paste(block_txt, (paste_x_base, paste_y_base), block_txt)


    # Composite layers
    result_img = Image.alpha_composite(img, txt_layer).convert("RGB")
    
    # Save output
    from app.services.project_paths import rendered_asset_path
    output_path = rendered_asset_path(page)
    result_img.save(output_path, "PNG")
    
    # Update Page record
    if persist:
        page.rendered_image_path = str(output_path)
        page.status = "processed"
        db.commit()

    logger.info(f"Rendered image saved successfully: {output_path}")
    return output_path
