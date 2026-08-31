use std::io::Write;

use image::{DynamicImage, GrayImage, Rgba, RgbaImage, imageops::overlay};

use crate::{
    descriptor::{
        DescriptorObject, DescriptorValue, bounds_descriptor, lfx2_body, write_versioned_descriptor,
    },
    engine_data::{TextEngineSpec, TextJustification, TextOrientation, encode_engine_data},
    error::PsdExportError,
    input::{
        PsdAntiAlias, PsdBlobRef, PsdDocument, PsdFontPrediction, PsdTextAlign, PsdTextBlock,
        PsdTextDirection, ResolvedDocument,
    },
    packbits::{ChannelId, encode_image_rle},
    writer::PsdWriter,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TextLayerMode {
    Rasterized,
    Editable,
}

#[derive(Debug, Clone)]
pub struct PsdExportOptions {
    pub include_original: bool,
    pub include_inpainted: bool,
    pub include_segment_mask: bool,
    pub include_brush_layer: bool,
    pub text_layer_mode: TextLayerMode,
}

impl Default for PsdExportOptions {
    fn default() -> Self {
        Self {
            include_original: true,
            include_inpainted: true,
            include_segment_mask: true,
            include_brush_layer: true,
            text_layer_mode: TextLayerMode::Rasterized,
        }
    }
}

#[derive(Debug, Clone)]
struct ExportLayer {
    name: String,
    left: i32,
    top: i32,
    pixels: RgbaImage,
    hidden: bool,
    text: Option<TextLayerMetadata>,
}

#[derive(Debug, Clone)]
struct TextLayerMetadata {
    index: i32,
    text: String,
    bounds: [f64; 4],
    bounding_box: [f64; 4],
    transform: [f64; 6],
    orientation: TextOrientation,
    justification: TextJustification,
    font_name: String,
    font_size: f64,
    color: [u8; 4],
    faux_bold: bool,
    faux_italic: bool,
    anti_alias: PsdAntiAlias,
    stroke_width: f64,
    stroke_color: [u8; 4],
    glow_enabled: bool,
    glow_radius: f64,
    glow_color: [u8; 4],
    leading: f64,
    tracking: i32,
    is_point_text: bool,
}

pub fn export_document(
    resolved: &ResolvedDocument,
    options: &PsdExportOptions,
) -> Result<Vec<u8>, PsdExportError> {
    let mut bytes = Vec::new();
    write_document(&mut bytes, resolved, options)?;
    Ok(bytes)
}

pub fn write_document<W: Write>(
    mut writer: W,
    resolved: &ResolvedDocument,
    options: &PsdExportOptions,
) -> Result<(), PsdExportError> {
    let document = resolved.document;
    let (width, height) = document_dimensions(document)?;
    let layers_bottom_to_top = collect_layers(resolved, options)?;
    let composite = merged_composite(resolved, &layers_bottom_to_top, width, height);
    // PSD layer records are displayed by Photoshop in reverse record order.
    // Supplying the compositing order here keeps editable Type layers above
    // Original/Inpainted in the Layers panel instead of burying them below.
    let layers_top_to_bottom: Vec<&ExportLayer> = layers_bottom_to_top.iter().collect();

    let mut psd = PsdWriter::new();
    write_header(&mut psd, width, height);
    psd.write_u32(0);
    let image_resources = resolution_info_resource();
    psd.write_u32(image_resources.len() as u32);
    psd.write_bytes(&image_resources);

    let layer_mask_info = build_layer_and_mask_info(&layers_top_to_bottom)?;
    psd.write_u32(layer_mask_info.len() as u32);
    psd.write_bytes(&layer_mask_info);

    write_image_data(&mut psd, &composite, "Merged Composite")?;

    writer.write_all(&psd.into_inner())?;
    Ok(())
}

/// Keep Photoshop's point-size coordinate system identical to document pixels.
/// The editor and renderer operate at 72 CSS/document pixels per inch, so a
/// 20px font must remain a 20pt Photoshop type layer after opening the PSD.
fn resolution_info_resource() -> Vec<u8> {
    let mut resource = PsdWriter::new();
    resource.write_signature("8BIM");
    resource.write_u16(1005);
    resource.write_pascal_string("", 2);
    resource.write_u32(16);
    resource.write_u32(72 << 16);
    resource.write_u16(1);
    resource.write_u16(1);
    resource.write_u32(72 << 16);
    resource.write_u16(1);
    resource.write_u16(1);
    resource.into_inner()
}

fn document_dimensions(document: &PsdDocument) -> Result<(u32, u32), PsdExportError> {
    let width = document.width;
    let height = document.height;

    if width == 0 || height == 0 {
        return Err(PsdExportError::MissingBaseImage);
    }

    if width > 30_000 || height > 30_000 {
        return Err(PsdExportError::UnsupportedDimensions { width, height });
    }

    Ok((width, height))
}

fn write_header(writer: &mut PsdWriter, width: u32, height: u32) {
    writer.write_signature("8BPS");
    writer.write_u16(1);
    writer.write_zeroes(6);
    writer.write_u16(4);
    writer.write_u32(height);
    writer.write_u32(width);
    writer.write_u16(8);
    writer.write_u16(3);
}

fn collect_layers(
    resolved: &ResolvedDocument,
    options: &PsdExportOptions,
) -> Result<Vec<ExportLayer>, PsdExportError> {
    let document = resolved.document;
    let mut layers = Vec::new();
    let include_inpainted = options.include_inpainted && resolved.inpainted.is_some();

    if options.include_original {
        let pixels = dynamic_to_rgba(resolved.source);
        validate_layer_pixels("Original Image", &pixels)?;
        layers.push(ExportLayer {
            name: "Original Image".to_string(),
            left: 0,
            top: 0,
            pixels,
            hidden: include_inpainted,
            text: None,
        });
    }

    if let Some(image) = resolved.inpainted.filter(|_| options.include_inpainted) {
        let pixels = dynamic_to_rgba(image);
        validate_layer_pixels("Inpainted", &pixels)?;
        layers.push(ExportLayer {
            name: "Inpainted".to_string(),
            left: 0,
            top: 0,
            pixels,
            hidden: false,
            text: None,
        });
    }

    if let Some(mask) = resolved.segment.filter(|_| options.include_segment_mask) {
        let pixels = grayscale_mask_rgba(mask);
        validate_layer_pixels("Segmentation Mask", &pixels)?;
        layers.push(ExportLayer {
            name: "Segmentation Mask".to_string(),
            left: 0,
            top: 0,
            pixels,
            hidden: true,
            text: None,
        });
    }

    if let Some(brush) = resolved.brush_layer.filter(|_| options.include_brush_layer) {
        let pixels = dynamic_to_rgba(brush);
        validate_layer_pixels("Brush Layer", &pixels)?;
        layers.push(ExportLayer {
            name: "Brush Layer".to_string(),
            left: 0,
            top: 0,
            pixels,
            hidden: false,
            text: None,
        });
    }

    let mut text_index = 1i32;
    for block in &document.text_blocks {
        if let Some(layer) = text_layer(
            block,
            text_index,
            options.text_layer_mode,
            resolved.block_images,
            document.export_id.as_deref(),
        )? {
            layers.push(layer);
            text_index += 1;
        }
    }

    // Append last because this list is bottom-to-top. Keep the reference hidden:
    // the editable Type layers already carry exact cached pixels, and a visible
    // opaque reference would make Photoshop edits appear to do nothing.
    if let Some(image) = resolved.rendered {
        let pixels = dynamic_to_rgba(image);
        validate_layer_pixels("Houmi Exact Preview", &pixels)?;
        layers.push(ExportLayer {
            // Keep the legacy PSD layer name ASCII-only. Photoshop's Pascal
            // layer-name fallback cannot represent an em dash and showed a
            // literal question mark even though the Unicode name was valid.
            name: "Houmi Exact Preview - REFERENCE (hidden)".to_string(),
            left: 0,
            top: 0,
            pixels,
            hidden: true,
            text: None,
        });
    }

    Ok(layers)
}

fn text_layer(
    block: &PsdTextBlock,
    index: i32,
    mode: TextLayerMode,
    block_images: &std::collections::HashMap<PsdBlobRef, DynamicImage>,
    export_id: Option<&str>,
) -> Result<Option<ExportLayer>, PsdExportError> {
    let text = block.translation.clone().unwrap_or_default();
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }

    let mut left = block.x.floor() as i32;
    let mut top = block.y.floor() as i32;

    let expected_width = block.width.ceil().max(1.0) as u32;
    let expected_height = block.height.ceil().max(1.0) as u32;
    let raw_pixels = block
        .rendered
        .as_ref()
        .and_then(|r| block_images.get(r))
        .map(dynamic_to_rgba)
        .unwrap_or_else(|| {
            RgbaImage::from_pixel(expected_width, expected_height, Rgba([0, 0, 0, 0]))
        });

    // Photoshop compares the cached layer rectangle with the paragraph
    // BoxBounds when a Type layer is transformed or edited.  Trimming the
    // browser-rendered glyphs down to their alpha bbox makes the channel
    // rectangle smaller than that paragraph box and causes the "Rerendering
    // the text layer will cause its layout to change" dialog.  Keep the
    // browser preview on editable layers, but normalize it to the exact
    // canonical text-box canvas so both records describe the same geometry.
    // Rasterized layers can still use the compact glyph crop.
    let (pixels, pixel_offset_x, pixel_offset_y, bounding_box) = match mode {
        TextLayerMode::Editable if block.rendered_x.is_some() && block.rendered_y.is_some() => {
            let offset_x = block.rendered_x.unwrap().floor() as i32 - block.x.floor() as i32;
            let offset_y = block.rendered_y.unwrap().floor() as i32 - block.y.floor() as i32;
            let width = raw_pixels.width() as f64;
            let height = raw_pixels.height() as f64;
            (
                raw_pixels,
                offset_x,
                offset_y,
                [
                    offset_x as f64,
                    offset_y as f64,
                    offset_x as f64 + width,
                    offset_y as f64 + height,
                ],
            )
        }
        TextLayerMode::Editable
            if block
                .style
                .as_ref()
                .and_then(|s| s.is_point_text)
                .unwrap_or(true) =>
        {
            trim_transparent_text_pixels(raw_pixels)
        }
        TextLayerMode::Editable => (
            place_on_canvas(&raw_pixels, expected_width, expected_height),
            0,
            0,
            [0.0, 0.0, expected_width as f64, expected_height as f64],
        ),
        TextLayerMode::Rasterized => trim_transparent_text_pixels(raw_pixels),
    };
    left += pixel_offset_x;
    top += pixel_offset_y;
    validate_layer_pixels(&block.id, &pixels)?;

    let text = match mode {
        TextLayerMode::Rasterized => None,
        TextLayerMode::Editable => {
            let orientation = infer_orientation(block);
            let justification = infer_justification(block, trimmed, orientation);
            let font_name = infer_font_name(block);
            let font_size = infer_font_size(block);
            let color = infer_color(block);
            let faux_bold = block
                .style
                .as_ref()
                .and_then(|style| style.effect)
                .map(|effect| effect.bold)
                .unwrap_or(false);
            let faux_italic = block
                .style
                .as_ref()
                .and_then(|style| style.effect)
                .map(|effect| effect.italic)
                .unwrap_or(false);
            let anti_alias = block
                .style
                .as_ref()
                .and_then(|style| style.anti_alias)
                .unwrap_or_default();
            let rotation_deg = block
                .rotation_deg
                .or_else(|| {
                    block
                        .font_prediction
                        .as_ref()
                        .map(|prediction| prediction.angle_deg)
                })
                .unwrap_or(0.0) as f64;
            let rotation_rad = rotation_deg.to_radians();
            // Balloon copy must be native Photoshop paragraph text. Point text
            // uses a baseline anchor and Photoshop converts/reflows it on first
            // edit or Transform. The manifest already carries the canonical
            // TypesettingSpec layout_region, so place that exact local box at
            // the document-space origin.
            let padding = block.style.as_ref().map(|s| s.padding).unwrap_or_default();
            let left = padding.left.max(0.0).min(block.width.max(1.0));
            let top = padding.top.max(0.0).min(block.height.max(1.0));
            let right = padding.right.max(0.0).min((block.width - left).max(0.0));
            let bottom = padding.bottom.max(0.0).min((block.height - top).max(0.0));
            let inner_width = (block.width - left - right).max(1.0);
            let inner_height = (block.height - top - bottom).max(1.0);
            let stroke_width = block
                .style
                .as_ref()
                .and_then(|s| s.stroke_width)
                .unwrap_or(0.0) as f64;
            let stroke_color = block
                .style
                .as_ref()
                .and_then(|s| s.stroke_color)
                .unwrap_or([255, 255, 255, 255]);
            let glow_enabled = block
                .style
                .as_ref()
                .and_then(|s| s.glow_enabled)
                .unwrap_or(false);
            let glow_radius = block
                .style
                .as_ref()
                .and_then(|s| s.glow_radius)
                .unwrap_or(0.0) as f64;
            let glow_color = block
                .style
                .as_ref()
                .and_then(|s| s.glow_color)
                .unwrap_or([255, 255, 255, 255]);
            let is_thai = contains_thai(trimmed);
            let raw_leading = block
                .style
                .as_ref()
                .and_then(|s| s.line_height)
                .map(|v| v as f64)
                .unwrap_or(0.0);
            let leading = if raw_leading > 0.0 && raw_leading <= 3.0 {
                raw_leading * font_size
            } else {
                raw_leading
            };
            let effective_leading = if leading > 0.0 {
                leading
            } else if is_thai {
                font_size * 1.25
            } else {
                font_size * 1.2
            };
            let line_count = trimmed.lines().count().max(1) as f64;
            let total_text_height = effective_leading * line_count;
            let signed_free_height = inner_height as f64 - total_text_height;
            let free_height = signed_free_height.max(0.0);
            let vertical_align = block
                .style
                .as_ref()
                .and_then(|s| s.vertical_align.as_deref())
                .unwrap_or("center");
            let vertical_offset = match vertical_align {
                "top" => 0.0,
                "bottom" => free_height,
                _ => free_height / 2.0,
            };
            // Point text has no paragraph box to clip/reflow against. Preserve
            // the requested vertical alignment even when the text is taller
            // than the canonical region by allowing a negative origin. The
            // previous max(0) anchored overflow at the top and pushed the last
            // lines below the balloon/page.
            let point_vertical_offset = match vertical_align {
                "top" => 0.0,
                "bottom" => signed_free_height,
                _ => signed_free_height / 2.0,
            };
            let is_point_text = block
                .style
                .as_ref()
                .and_then(|s| s.is_point_text)
                .unwrap_or(false);
            // Thai vowels & diacritics buffer:
            // Add a vertical margin to paragraph bounds for Thai text to prevent
            // Photoshop's text renderer from clipping top/bottom accents or wrapping lines.
            let (top_thai_margin, bottom_thai_margin) = if is_thai && !is_point_text {
                (font_size * 0.10, font_size * 0.20)
            } else {
                (0.0, 0.0)
            };

            let bounds = [
                left as f64,
                (top as f64 + vertical_offset - top_thai_margin).max(0.0),
                (left + inner_width) as f64,
                (top + inner_height) as f64 + bottom_thai_margin,
            ];
            let bounding_box = [0.0, 0.0, inner_width as f64, inner_height as f64];

            let center_x = block.x as f64 + block.width as f64 / 2.0;
            let center_y = block.y as f64 + block.height as f64 / 2.0;

            let (final_tx, final_ty) = if is_point_text {
                let anchor_x = match justification {
                    TextJustification::Left => block.x as f64 + left as f64,
                    TextJustification::Right => block.x as f64 + (left + inner_width) as f64,
                    TextJustification::Center => {
                        block.x as f64 + left as f64 + (inner_width as f64) / 2.0
                    }
                };
                let anchor_y =
                    block.y as f64 + top as f64 + point_vertical_offset + (font_size * 0.82);

                let rel_x = anchor_x - center_x;
                let rel_y = anchor_y - center_y;

                let rot_x = center_x + rel_x * rotation_rad.cos() - rel_y * rotation_rad.sin();
                let rot_y = center_y + rel_x * rotation_rad.sin() + rel_y * rotation_rad.cos();
                (rot_x, rot_y)
            } else {
                let tx = block.x as f64 + block.width as f64 / 2.0
                    - rotation_rad.cos() * block.width as f64 / 2.0
                    + rotation_rad.sin() * block.height as f64 / 2.0;
                let ty = block.y as f64 + block.height as f64 / 2.0
                    - rotation_rad.sin() * block.width as f64 / 2.0
                    - rotation_rad.cos() * block.height as f64 / 2.0;
                (tx, ty)
            };

            let transform = [
                rotation_rad.cos(),
                rotation_rad.sin(),
                -rotation_rad.sin(),
                rotation_rad.cos(),
                final_tx,
                final_ty,
            ];
            let tracking = block
                .style
                .as_ref()
                .and_then(|s| s.tracking)
                .map(|v| v.round() as i32)
                .unwrap_or(0);

            Some(TextLayerMetadata {
                index,
                text: trimmed.to_string(),
                bounds,
                bounding_box,
                transform,
                orientation,
                justification,
                font_name,
                font_size,
                color,
                faux_bold,
                faux_italic,
                anti_alias,
                stroke_width,
                stroke_color,
                glow_enabled,
                glow_radius,
                glow_color,
                leading: if raw_leading > 0.0 { effective_leading } else { 0.0 },
                tracking,
                is_point_text: block
                    .style
                    .as_ref()
                    .and_then(|s| s.is_point_text)
                    .unwrap_or(false),
            })
        }
    };

    let clean_text = block
        .translation
        .as_deref()
        .unwrap_or("")
        .lines()
        .next()
        .unwrap_or("")
        .trim();
    let text_preview = if clean_text.is_empty() {
        "".to_string()
    } else if clean_text.chars().count() > 25 {
        format!("{}... ", clean_text.chars().take(25).collect::<String>())
    } else {
        format!("{} ", clean_text)
    };

    let layer_name = if let Some(exp_id) = export_id {
        format!(
            "TL {:03} {}{} exp_v1:{}",
            index, text_preview, block.id, exp_id
        )
    } else {
        format!("TL {:03} {}{}", index, text_preview, block.id)
    };

    Ok(Some(ExportLayer {
        name: layer_name,
        left,
        top,
        pixels,
        hidden: false,
        text,
    }))
}

fn validate_layer_pixels(layer: &str, pixels: &RgbaImage) -> Result<(), PsdExportError> {
    let width = pixels.width() as i32;
    let height = pixels.height() as i32;
    if width <= 0 || height <= 0 {
        return Err(PsdExportError::InvalidLayerBounds {
            layer: layer.to_string(),
            width,
            height,
        });
    }
    Ok(())
}

fn dynamic_to_rgba(image: &DynamicImage) -> RgbaImage {
    image.to_rgba8()
}

fn grayscale_mask_rgba(image: &DynamicImage) -> RgbaImage {
    let mask: GrayImage = image.to_luma8();
    let mut rgba = RgbaImage::new(mask.width(), mask.height());
    for (x, y, pixel) in mask.enumerate_pixels() {
        rgba.put_pixel(x, y, Rgba([pixel[0], pixel[0], pixel[0], 255]));
    }
    rgba
}

fn merged_composite(
    resolved: &ResolvedDocument,
    layers_bottom_to_top: &[ExportLayer],
    width: u32,
    height: u32,
) -> RgbaImage {
    if let Some(rendered) = resolved.rendered {
        return place_on_canvas(&rendered.to_rgba8(), width, height);
    }

    let mut canvas = RgbaImage::from_pixel(width, height, Rgba([0, 0, 0, 0]));
    for layer in layers_bottom_to_top.iter().filter(|layer| !layer.hidden) {
        overlay(
            &mut canvas,
            &layer.pixels,
            i64::from(layer.left),
            i64::from(layer.top),
        );
    }
    canvas
}

fn place_on_canvas(image: &RgbaImage, width: u32, height: u32) -> RgbaImage {
    if image.width() == width && image.height() == height {
        return image.clone();
    }

    let mut canvas = RgbaImage::from_pixel(width, height, Rgba([0, 0, 0, 0]));
    overlay(&mut canvas, image, 0, 0);
    canvas
}

fn build_layer_and_mask_info(layers: &[&ExportLayer]) -> Result<Vec<u8>, PsdExportError> {
    let mut layer_info = PsdWriter::new();
    if layers.is_empty() {
        layer_info.write_i16(0);
    } else {
        layer_info.write_i16(-(layers.len() as i16));
    }

    let mut encoded_layers = Vec::with_capacity(layers.len());
    let mut extra_data = Vec::with_capacity(layers.len());

    for layer in layers {
        let channels = encode_image_rle(
            &layer.pixels,
            &[
                ChannelId::Red,
                ChannelId::Green,
                ChannelId::Blue,
                ChannelId::Alpha,
            ],
            &layer.name,
        )?;
        let extra = build_extra_data(layer)?;
        encoded_layers.push(channels);
        extra_data.push(extra);
    }

    for ((layer, channels), extra) in layers.iter().zip(&encoded_layers).zip(&extra_data) {
        let width = i32::try_from(layer.pixels.width()).map_err(|_| {
            PsdExportError::InvalidLayerBounds {
                layer: layer.name.clone(),
                width: i32::MAX,
                height: layer.pixels.height() as i32,
            }
        })?;
        let height = i32::try_from(layer.pixels.height()).map_err(|_| {
            PsdExportError::InvalidLayerBounds {
                layer: layer.name.clone(),
                width,
                height: i32::MAX,
            }
        })?;
        let right =
            layer
                .left
                .checked_add(width)
                .ok_or_else(|| PsdExportError::InvalidLayerBounds {
                    layer: layer.name.clone(),
                    width,
                    height,
                })?;
        let bottom =
            layer
                .top
                .checked_add(height)
                .ok_or_else(|| PsdExportError::InvalidLayerBounds {
                    layer: layer.name.clone(),
                    width,
                    height,
                })?;

        layer_info.write_i32(layer.top);
        layer_info.write_i32(layer.left);
        layer_info.write_i32(bottom);
        layer_info.write_i32(right);
        layer_info.write_u16(channels.len() as u16);

        for channel in channels {
            layer_info.write_i16(channel.channel_id);
            layer_info.write_u32((2 + channel.data.len()) as u32);
        }

        layer_info.write_signature("8BIM");
        layer_info.write_signature("norm");
        layer_info.write_u8(255);
        layer_info.write_u8(0);
        layer_info.write_u8(if layer.hidden { 0x0A } else { 0x08 });
        layer_info.write_u8(0);
        layer_info.write_u32(extra.len() as u32);
        layer_info.write_bytes(extra);
    }

    for channels in &encoded_layers {
        for channel in channels {
            layer_info.write_u16(1);
            layer_info.write_bytes(&channel.data);
        }
    }
    layer_info.pad_to_multiple(4);

    let mut full = PsdWriter::new();
    full.write_u32(layer_info.len() as u32);
    full.write_bytes(&layer_info.into_inner());
    full.write_u32(0);
    Ok(full.into_inner())
}

fn build_extra_data(layer: &ExportLayer) -> Result<Vec<u8>, PsdExportError> {
    let mut extra = PsdWriter::new();
    extra.write_u32(0);
    extra.write_u32(0);
    extra.write_pascal_string(&layer.name, 4);

    if let Some(text) = layer.text.as_ref() {
        write_additional_info_block(&mut extra, "luni", &luni_body(&layer.name), 4);
        write_additional_info_block(&mut extra, "TySh", &tysh_body(text)?, 2);

        let stroke_effective_width = if text.stroke_color != text.color {
            text.stroke_width
        } else {
            0.0
        };
        if stroke_effective_width != 0.0 || (text.glow_enabled && text.glow_radius > 0.0) {
            let stroke_rgb = [
                text.stroke_color[0],
                text.stroke_color[1],
                text.stroke_color[2],
            ];
            let glow_rgb = [
                text.glow_color[0],
                text.glow_color[1],
                text.glow_color[2],
            ];
            if let Ok(lfx2_bytes) = lfx2_body(
                stroke_effective_width,
                stroke_rgb,
                text.glow_enabled,
                text.glow_radius,
                glow_rgb,
            ) {
                write_additional_info_block(&mut extra, "lfx2", &lfx2_bytes, 4);
            }
        }
    }

    Ok(extra.into_inner())
}

fn luni_body(name: &str) -> Vec<u8> {
    let mut body = PsdWriter::new();
    body.write_unicode_string(name);
    body.into_inner()
}

fn tysh_body(text: &TextLayerMetadata) -> Result<Vec<u8>, PsdExportError> {
    let engine_data = encode_engine_data(&TextEngineSpec {
        text: text.text.clone(),
        font_name: text.font_name.clone(),
        font_size: text.font_size,
        color: text.color,
        faux_bold: text.faux_bold,
        faux_italic: text.faux_italic,
        anti_alias: text.anti_alias,
        orientation: text.orientation,
        justification: text.justification,
        stroke_width: text.stroke_width,
        stroke_color: text.stroke_color,
        leading: text.leading,
        tracking: text.tracking,
        box_bounds: if text.is_point_text {
            None
        } else {
            Some(text.bounds)
        },
    });

    let bounds = bounds_descriptor(
        "bounds",
        text.bounds[0],
        text.bounds[1],
        text.bounds[2],
        text.bounds[3],
    );
    let bounding_box = bounds_descriptor(
        "boundingBox",
        text.bounding_box[0],
        text.bounding_box[1],
        text.bounding_box[2],
        text.bounding_box[3],
    );

    let text_descriptor = DescriptorObject::new("", "TxLr")
        .with_item("Txt ", DescriptorValue::Text(text.text.clone()))
        .with_item(
            "textGridding",
            DescriptorValue::Enum {
                type_id: "textGridding".to_string(),
                value: "None".to_string(),
            },
        )
        .with_item(
            "Ornt",
            DescriptorValue::Enum {
                type_id: "Ornt".to_string(),
                value: match text.orientation {
                    TextOrientation::Horizontal => "Hrzn".to_string(),
                    TextOrientation::Vertical => "Vrtc".to_string(),
                },
            },
        )
        .with_item(
            "AntA",
            DescriptorValue::Enum {
                type_id: "Annt".to_string(),
                value: text.anti_alias.photoshop_name().to_string(),
            },
        )
        .with_item("bounds", DescriptorValue::Object(bounds))
        .with_item("boundingBox", DescriptorValue::Object(bounding_box))
        .with_item("TextIndex", DescriptorValue::Integer(text.index))
        .with_item("EngineData", DescriptorValue::Raw(engine_data));

    let warp_descriptor = DescriptorObject::new("", "warp")
        .with_item(
            "warpStyle",
            DescriptorValue::Enum {
                type_id: "warpStyle".to_string(),
                value: "warpNone".to_string(),
            },
        )
        .with_item("warpValue", DescriptorValue::Double(0.0))
        .with_item("warpPerspective", DescriptorValue::Double(0.0))
        .with_item("warpPerspectiveOther", DescriptorValue::Double(0.0))
        .with_item(
            "warpRotate",
            DescriptorValue::Enum {
                type_id: "Ornt".to_string(),
                value: match text.orientation {
                    TextOrientation::Horizontal => "Hrzn".to_string(),
                    TextOrientation::Vertical => "Vrtc".to_string(),
                },
            },
        )
        .with_item(
            "bounds",
            DescriptorValue::Object(bounds_descriptor(
                "bounds",
                text.bounds[0],
                text.bounds[1],
                text.bounds[2],
                text.bounds[3],
            )),
        );

    let mut body = PsdWriter::new();
    body.write_i16(1);
    for value in text.transform {
        body.write_f64(value);
    }
    body.write_i16(50);
    write_versioned_descriptor(&mut body, &text_descriptor)?;
    body.write_i16(1);
    write_versioned_descriptor(&mut body, &warp_descriptor)?;
    // This final TySh rectangle is four signed 32-bit integers. The previous
    // float encoding produced large IEEE-754 bit-pattern coordinates (for
    // example 184.68 became 1127788287), corrupting Photoshop's text geometry.
    // Photoshop itself writes zeros here and stores the meaningful local box
    // in the text descriptor and EngineData BoxBounds.
    for _ in 0..4 {
        body.write_i32(0);
    }
    Ok(body.into_inner())
}

fn trim_transparent_text_pixels(pixels: RgbaImage) -> (RgbaImage, i32, i32, [f64; 4]) {
    let mut min_x = pixels.width();
    let mut min_y = pixels.height();
    let mut max_x = 0u32;
    let mut max_y = 0u32;
    let mut found = false;
    for (x, y, pixel) in pixels.enumerate_pixels() {
        if pixel[3] == 0 {
            continue;
        }
        found = true;
        min_x = min_x.min(x);
        min_y = min_y.min(y);
        max_x = max_x.max(x + 1);
        max_y = max_y.max(y + 1);
    }
    if !found {
        let bounds = [0.0, 0.0, pixels.width() as f64, pixels.height() as f64];
        return (pixels, 0, 0, bounds);
    }
    let cropped =
        image::imageops::crop_imm(&pixels, min_x, min_y, max_x - min_x, max_y - min_y).to_image();
    (
        cropped,
        min_x as i32,
        min_y as i32,
        [min_x as f64, min_y as f64, max_x as f64, max_y as f64],
    )
}

fn write_additional_info_block(writer: &mut PsdWriter, key: &str, body: &[u8], alignment: usize) {
    let padding = (alignment - (body.len() % alignment)) % alignment;

    writer.write_signature("8BIM");
    writer.write_signature(key);
    writer.write_u32((body.len() + padding) as u32);
    writer.write_bytes(body);
    writer.write_zeroes(padding);
}

fn write_image_data(
    writer: &mut PsdWriter,
    image: &RgbaImage,
    name: &str,
) -> Result<(), PsdExportError> {
    writer.write_u16(1);
    let channels = encode_image_rle(
        image,
        &[
            ChannelId::Red,
            ChannelId::Green,
            ChannelId::Blue,
            ChannelId::Alpha,
        ],
        name,
    )?;

    let row_lengths_len = image.height() as usize * 2;
    for channel in &channels {
        writer.write_bytes(&channel.data[..row_lengths_len]);
    }
    for channel in &channels {
        writer.write_bytes(&channel.data[row_lengths_len..]);
    }
    Ok(())
}

fn infer_orientation(block: &PsdTextBlock) -> TextOrientation {
    match block.rendered_direction.or(block.source_direction) {
        Some(PsdTextDirection::Vertical) => TextOrientation::Vertical,
        _ => TextOrientation::Horizontal,
    }
}

fn infer_justification(
    block: &PsdTextBlock,
    text: &str,
    orientation: TextOrientation,
) -> TextJustification {
    if let Some(alignment) = block.style.as_ref().and_then(|style| style.text_align) {
        return match alignment {
            PsdTextAlign::Left => TextJustification::Left,
            PsdTextAlign::Center => TextJustification::Center,
            PsdTextAlign::Right => TextJustification::Right,
        };
    }

    if orientation == TextOrientation::Horizontal && is_probably_latin(text) {
        TextJustification::Center
    } else {
        TextJustification::Left
    }
}

fn infer_font_name(block: &PsdTextBlock) -> String {
    if let Some(style_font) = block.style.as_ref().and_then(|style| {
        style
            .font_families
            .iter()
            .find(|font| !font.trim().is_empty())
    }) {
        return style_font.trim().to_string();
    }

    if let Some(predicted_font) = block.font_prediction.as_ref().and_then(|prediction| {
        prediction
            .named_fonts
            .iter()
            .find(|font| !font.name.trim().is_empty())
    }) {
        return predicted_font.name.trim().to_string();
    }

    "ArialMT".to_string()
}

fn infer_font_size(block: &PsdTextBlock) -> f64 {
    if let Some(size) = block.style.as_ref().and_then(|style| style.font_size)
        && size.is_finite()
        && size > 0.0
    {
        return size as f64;
    }

    if let Some(prediction) = block.font_prediction.as_ref()
        && prediction.font_size_px.is_finite()
        && prediction.font_size_px > 0.0
    {
        return prediction.font_size_px as f64;
    }

    if let Some(size) = block.detected_font_size_px
        && size.is_finite()
        && size > 0.0
    {
        return size as f64;
    }

    f64::max(6.0, f64::from(block.width.min(block.height)) * 0.7)
}

fn infer_color(block: &PsdTextBlock) -> [u8; 4] {
    if let Some(style) = block.style.as_ref() {
        return style.color;
    }

    if let Some(PsdFontPrediction { text_color, .. }) = block.font_prediction.as_ref() {
        return [text_color[0], text_color[1], text_color[2], 255];
    }

    [0, 0, 0, 255]
}

fn contains_cjk(text: &str) -> bool {
    text.chars().any(|ch| {
        matches!(
            ch as u32,
            0x3040..=0x30FF
                | 0x3400..=0x4DBF
                | 0x4E00..=0x9FFF
                | 0xAC00..=0xD7AF
                | 0xF900..=0xFAFF
                | 0xFF66..=0xFF9D
        )
    })
}

fn contains_thai(text: &str) -> bool {
    text.chars().any(|ch| matches!(ch as u32, 0x0E00..=0x0E7F))
}

fn is_probably_latin(text: &str) -> bool {
    text.chars().any(|ch| ch.is_ascii_alphabetic()) && !contains_cjk(text)
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use image::{DynamicImage, Rgba, RgbaImage};

    use crate::writer::PsdWriter;

    use crate::input::{
        PsdDocument, PsdTextBlock, PsdTextDirection, PsdTextStyle, ResolvedDocument,
    };

    use super::{
        PsdExportOptions, TextLayerMode, TextOrientation, collect_layers, contains_cjk,
        contains_thai, infer_font_name, infer_orientation, is_probably_latin, place_on_canvas,
        resolution_info_resource, text_layer, tysh_body, write_image_data,
    };

    #[test]
    fn place_on_canvas_keeps_size_stable() {
        let image = RgbaImage::new(4, 4);
        let canvas = place_on_canvas(&image, 8, 6);
        assert_eq!(canvas.width(), 8);
        assert_eq!(canvas.height(), 6);
    }

    #[test]
    fn resolution_resource_pins_document_to_72_dpi() {
        let resource = resolution_info_resource();
        assert_eq!(&resource[0..4], b"8BIM");
        assert_eq!(u16::from_be_bytes([resource[4], resource[5]]), 1005);
        assert_eq!(
            u32::from_be_bytes([resource[8], resource[9], resource[10], resource[11]]),
            16
        );
        assert_eq!(&resource[12..16], &[0, 72, 0, 0]);
        assert_eq!(&resource[20..24], &[0, 72, 0, 0]);
    }

    #[test]
    fn language_heuristics_detect_cjk_vs_latin() {
        assert!(contains_cjk("縦書き"));
        assert!(contains_thai("สวัสดีชาวโลก"));
        assert!(!contains_thai("HELLO"));
        assert!(is_probably_latin("HELLO"));
        assert!(!is_probably_latin("縦書き"));
    }

    #[test]
    fn orientation_uses_rendered_direction_not_geometry() {
        let tall_english_block = PsdTextBlock {
            width: 40.0,
            height: 120.0,
            translation: Some("HELLO".to_string()),
            ..Default::default()
        };
        assert_eq!(
            infer_orientation(&tall_english_block),
            TextOrientation::Horizontal
        );

        let vertical_block = PsdTextBlock {
            rendered_direction: Some(PsdTextDirection::Vertical),
            ..Default::default()
        };
        assert_eq!(
            infer_orientation(&vertical_block),
            TextOrientation::Vertical
        );
    }

    #[test]
    fn composite_image_data_groups_row_tables_before_channel_payloads() {
        let mut image = RgbaImage::new(1, 1);
        image.put_pixel(0, 0, Rgba([1, 2, 3, 4]));

        let mut writer = PsdWriter::new();
        write_image_data(&mut writer, &image, "Merged Composite").expect("write image data");

        assert_eq!(
            writer.into_inner(),
            vec![
                0, 1, // compression
                0, 2, 0, 2, 0, 2, 0, 2, // row lengths
                0, 1, // red
                0, 2, // green
                0, 3, // blue
                0, 4, // alpha
            ]
        );
    }

    #[test]
    fn style_font_name_is_used_for_editable_export() {
        let block = PsdTextBlock {
            style: Some(PsdTextStyle {
                font_families: vec!["ArialMT".to_string()],
                font_size: None,
                color: [0, 0, 0, 255],
                anti_alias: None,
                effect: None,
                text_align: None,
                vertical_align: None,
                stroke_width: None,
                stroke_color: None,
                glow_enabled: None,
                glow_radius: None,
                glow_color: None,
                line_height: None,
                tracking: None,
                padding: Default::default(),
                is_point_text: None,
            }),
            ..Default::default()
        };

        assert_eq!(infer_font_name(&block), "ArialMT");
    }

    #[test]
    fn editable_text_layer_embeds_versioned_export_identity() {
        let block = PsdTextBlock {
            id: "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d".to_string(),
            width: 100.0,
            height: 50.0,
            translation: Some("Hello".to_string()),
            ..Default::default()
        };
        let images = HashMap::new();

        let identified = text_layer(
            &block,
            1,
            TextLayerMode::Editable,
            &images,
            Some("11111111-2222-3333-4444-555555555555"),
        )
        .expect("text layer")
        .expect("non-empty text layer");
        assert_eq!(
            identified.name,
            "TL 001 Hello a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d exp_v1:11111111-2222-3333-4444-555555555555"
        );

        let legacy = text_layer(&block, 1, TextLayerMode::Editable, &images, None)
            .expect("text layer")
            .expect("non-empty text layer");
        assert_eq!(
            legacy.name,
            "TL 001 Hello a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
        );
    }

    #[test]
    fn editable_text_geometry_uses_canonical_engine_canvas() {
        let fallback_ref = crate::input::PsdBlobRef::new("fallback");
        let block = PsdTextBlock {
            id: "block-with-fallback".to_string(),
            x: 184.5,
            y: 9767.25,
            width: 252.0,
            height: 120.0,
            translation: Some("พี่สาว".to_string()),
            rendered: Some(fallback_ref.clone()),
            style: Some(PsdTextStyle {
                font_size: Some(20.0),
                line_height: Some(24.0),
                vertical_align: Some("center".to_string()),
                ..Default::default()
            }),
            ..Default::default()
        };
        let mut images = HashMap::new();
        images.insert(
            fallback_ref,
            DynamicImage::ImageRgba8(RgbaImage::from_pixel(252, 120, Rgba([1, 2, 3, 255]))),
        );

        let layer = text_layer(&block, 1, TextLayerMode::Editable, &images, None)
            .expect("text layer")
            .expect("non-empty text layer");
        let metadata = layer.text.expect("editable metadata");

        assert_eq!(metadata.bounds, [0.0, 46.0, 252.0, 124.0]);
        assert_eq!(metadata.transform[4], 184.5);
        assert_eq!(metadata.transform[5], 9767.25);
        assert_eq!(layer.pixels.dimensions(), (252, 120));
        assert_eq!(layer.pixels.get_pixel(0, 0), &Rgba([1, 2, 3, 255]));
    }

    #[test]
    fn rasterized_text_geometry_keeps_exact_fallback() {
        let fallback_ref = crate::input::PsdBlobRef::new("fallback-rasterized");
        let block = PsdTextBlock {
            id: "block-rasterized".to_string(),
            width: 40.0,
            height: 20.0,
            translation: Some("พี่สาว".to_string()),
            rendered: Some(fallback_ref.clone()),
            ..Default::default()
        };
        let mut images = HashMap::new();
        images.insert(
            fallback_ref,
            DynamicImage::ImageRgba8(RgbaImage::from_pixel(40, 20, Rgba([1, 2, 3, 255]))),
        );

        let layer = text_layer(&block, 1, TextLayerMode::Rasterized, &images, None)
            .expect("text layer")
            .expect("non-empty text layer");
        assert!(layer.text.is_none());
        assert_eq!(layer.pixels.get_pixel(0, 0), &Rgba([1, 2, 3, 255]));
    }

    #[test]
    fn editable_text_fallback_does_not_trim_glyph_margins() {
        let fallback_ref = crate::input::PsdBlobRef::new("fallback-margin");
        let block = PsdTextBlock {
            id: "block-margin".to_string(),
            x: 12.0,
            y: 24.0,
            width: 12.0,
            height: 8.0,
            translation: Some("ข้อความ".to_string()),
            rendered: Some(fallback_ref.clone()),
            style: Some(crate::input::PsdTextStyle {
                is_point_text: Some(false),
                ..Default::default()
            }),
            ..Default::default()
        };
        let mut overlay = RgbaImage::new(12, 8);
        overlay.put_pixel(3, 2, Rgba([9, 8, 7, 255]));
        let mut images = HashMap::new();
        images.insert(fallback_ref, DynamicImage::ImageRgba8(overlay));

        let layer = text_layer(&block, 1, TextLayerMode::Editable, &images, None)
            .expect("text layer")
            .expect("non-empty text layer");
        assert_eq!((layer.left, layer.top), (12, 24));
        assert_eq!(layer.pixels.dimensions(), (12, 8));
        assert_eq!(layer.pixels.get_pixel(3, 2), &Rgba([9, 8, 7, 255]));
        assert_eq!(
            layer.text.expect("editable metadata").bounding_box,
            [0.0, 0.0, 12.0, 8.0]
        );
    }

    #[test]
    fn editable_text_fallback_preserves_expanded_cache_origin() {
        let fallback_ref = crate::input::PsdBlobRef::new("fallback-overflow");
        let block = PsdTextBlock {
            id: "block-overflow".to_string(),
            x: 20.0,
            y: 80.0,
            width: 100.0,
            height: 50.0,
            translation: Some("หนึ่ง\nสอง\nสาม".to_string()),
            rendered: Some(fallback_ref.clone()),
            rendered_x: Some(20.0),
            rendered_y: Some(65.0),
            ..Default::default()
        };
        let mut images = HashMap::new();
        images.insert(
            fallback_ref,
            DynamicImage::ImageRgba8(RgbaImage::from_pixel(100, 80, Rgba([1, 2, 3, 255]))),
        );

        let layer = text_layer(&block, 1, TextLayerMode::Editable, &images, None)
            .expect("text layer")
            .expect("non-empty text layer");
        assert_eq!((layer.left, layer.top), (20, 65));
        assert_eq!(layer.pixels.dimensions(), (100, 80));
        assert_eq!(
            layer.text.expect("editable metadata").bounds,
            [0.0, 0.0, 100.0, 57.0]
        );
    }

    #[test]
    fn point_text_centers_vertical_overflow_instead_of_pushing_it_down() {
        let block = PsdTextBlock {
            id: "point-overflow".to_string(),
            x: 20.0,
            y: 80.0,
            width: 100.0,
            height: 50.0,
            translation: Some("หนึ่ง\nสอง\nสาม".to_string()),
            style: Some(crate::input::PsdTextStyle {
                font_size: Some(20.0),
                line_height: Some(25.0),
                vertical_align: Some("center".to_string()),
                is_point_text: Some(true),
                ..Default::default()
            }),
            ..Default::default()
        };

        let layer = text_layer(&block, 1, TextLayerMode::Editable, &HashMap::new(), None)
            .expect("text layer")
            .expect("non-empty text layer");
        let metadata = layer.text.expect("editable metadata");
        // 50px region - 75px text => -12.5px centered overflow, then the
        // Photoshop baseline approximation at 0.82 * 20px.
        assert!((metadata.transform[5] - 83.9).abs() < 0.001);
    }

    #[test]
    fn editable_text_requests_smooth_photoshop_antialiasing() {
        let block = PsdTextBlock {
            width: 100.0,
            height: 50.0,
            translation: Some("ข้อความ".to_string()),
            ..Default::default()
        };
        let layer = text_layer(&block, 1, TextLayerMode::Editable, &HashMap::new(), None)
            .expect("text layer")
            .expect("non-empty text layer");
        let tysh =
            tysh_body(layer.text.as_ref().expect("editable metadata")).expect("TySh metadata");
        assert!(
            tysh.windows(b"antiAliasSmooth".len())
                .any(|window| window == b"antiAliasSmooth")
        );
    }

    #[test]
    fn editable_text_keeps_selected_antialias_in_descriptor_and_engine_data() {
        let block = PsdTextBlock {
            width: 100.0,
            height: 50.0,
            translation: Some("ข้อความ".to_string()),
            style: Some(PsdTextStyle {
                anti_alias: Some(crate::input::PsdAntiAlias::Sharp),
                ..Default::default()
            }),
            ..Default::default()
        };
        let layer = text_layer(&block, 1, TextLayerMode::Editable, &HashMap::new(), None)
            .expect("text layer")
            .expect("non-empty text layer");
        let tysh =
            tysh_body(layer.text.as_ref().expect("editable metadata")).expect("TySh metadata");
        assert!(
            tysh.windows(b"antiAliasSharp".len())
                .any(|window| window == b"antiAliasSharp")
        );
        assert!(
            tysh.windows(b"/AntiAlias 1".len())
                .any(|window| window == b"/AntiAlias 1")
        );
    }

    #[test]
    fn editable_text_bounds_apply_canonical_padding() {
        let block = PsdTextBlock {
            width: 200.0,
            height: 100.0,
            translation: Some("พี่สาว".to_string()),
            style: Some(PsdTextStyle {
                padding: crate::input::PsdPadding {
                    top: 10.0,
                    right: 20.0,
                    bottom: 15.0,
                    left: 12.0,
                },
                ..Default::default()
            }),
            ..Default::default()
        };
        let layer = text_layer(&block, 1, TextLayerMode::Editable, &HashMap::new(), None)
            .expect("text layer")
            .expect("non-empty text layer");

        assert_eq!(
            layer.text.expect("editable metadata").bounds,
            [12.0, 3.0, 180.0, 99.0]
        );
    }

    #[test]
    fn exact_preview_covers_enabled_editable_text_until_hidden() {
        let source = DynamicImage::ImageRgba8(RgbaImage::new(8, 6));
        let rendered =
            DynamicImage::ImageRgba8(RgbaImage::from_pixel(8, 6, Rgba([11, 22, 33, 255])));
        let document = PsdDocument {
            width: 8,
            height: 6,
            export_id: None,
            text_blocks: vec![PsdTextBlock {
                id: "block-1".to_string(),
                width: 4.0,
                height: 3.0,
                translation: Some("พี่สาว".to_string()),
                ..Default::default()
            }],
        };
        let images = HashMap::new();
        let resolved = ResolvedDocument {
            document: &document,
            source: &source,
            segment: None,
            inpainted: None,
            rendered: Some(&rendered),
            brush_layer: None,
            block_images: &images,
        };
        let options = PsdExportOptions {
            include_original: true,
            include_inpainted: false,
            include_segment_mask: false,
            include_brush_layer: false,
            text_layer_mode: TextLayerMode::Editable,
        };

        let layers = collect_layers(&resolved, &options).expect("collect layers");
        let exact = layers
            .iter()
            .find(|layer| layer.name.starts_with("Houmi Exact Preview"))
            .expect("exact preview layer");
        let editable = layers
            .iter()
            .find(|layer| layer.text.is_some())
            .expect("editable text layer");

        assert!(exact.hidden);
        assert!(!editable.hidden);
        assert!(
            layers
                .iter()
                .position(|layer| layer.name.starts_with("Houmi Exact Preview"))
                > layers.iter().position(|layer| layer.text.is_some())
        );
    }
}
