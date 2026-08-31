mod descriptor;
mod engine_data;
mod error;
mod export;
mod input;
mod packbits;
mod writer;

use clap::Parser;
use serde::Deserialize;
use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;
use std::path::Path;

use export::{PsdExportOptions, TextLayerMode, write_document};
use input::{
    PsdAntiAlias, PsdBlobRef, PsdDocument, PsdPadding, PsdShaderEffect, PsdTextAlign, PsdTextBlock,
    PsdTextDirection, PsdTextStyle, ResolvedDocument,
};

#[derive(Parser, Debug)]
#[command(author, version, about = "Houmi Manga PSD Creator CLI")]
struct Args {
    /// Path to the JSON manifest specifying layers and text blocks
    #[arg(short, long)]
    manifest: String,

    /// Path to the output PSD file
    #[arg(short, long)]
    output: String,
}

#[derive(Deserialize, Debug)]
struct JsonTextStyle {
    font_families: Vec<String>,
    font_size: Option<f32>,
    color: [u8; 4],
    #[serde(default)]
    anti_alias: Option<String>,
    bold: bool,
    italic: bool,
    align: Option<String>, // "left", "center", "right"
    #[serde(default)]
    vertical_align: Option<String>, // "top", "center", "bottom"
    #[serde(default)]
    stroke_width: Option<f32>,
    /// Hex "#rrggbb" or "#rrggbbaa" from Python export
    #[serde(default)]
    stroke_color: Option<String>,
    #[serde(default)]
    glow_enabled: Option<bool>,
    #[serde(default)]
    glow_radius: Option<f32>,
    #[serde(default)]
    glow_color: Option<String>,
    #[serde(default)]
    line_height: Option<f32>,
    #[serde(default)]
    tracking: Option<f32>,
    #[serde(default)]
    padding: JsonPadding,
    #[serde(default)]
    is_point_text: Option<bool>,
    #[serde(default)]
    text_type: Option<String>,
}

#[derive(Deserialize, Debug, Default)]
struct JsonPadding {
    #[serde(default)]
    top: f32,
    #[serde(default)]
    right: f32,
    #[serde(default)]
    bottom: f32,
    #[serde(default)]
    left: f32,
}

fn parse_hex_rgba(hex: &str) -> Option<[u8; 4]> {
    let h = hex.trim().trim_start_matches('#');
    if h.len() == 6 {
        let r = u8::from_str_radix(&h[0..2], 16).ok()?;
        let g = u8::from_str_radix(&h[2..4], 16).ok()?;
        let b = u8::from_str_radix(&h[4..6], 16).ok()?;
        Some([r, g, b, 255])
    } else if h.len() == 8 {
        let r = u8::from_str_radix(&h[0..2], 16).ok()?;
        let g = u8::from_str_radix(&h[2..4], 16).ok()?;
        let b = u8::from_str_radix(&h[4..6], 16).ok()?;
        let a = u8::from_str_radix(&h[6..8], 16).ok()?;
        Some([r, g, b, a])
    } else {
        None
    }
}

fn parse_anti_alias(value: Option<&str>) -> PsdAntiAlias {
    match value
        .unwrap_or("smooth")
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "none" => PsdAntiAlias::None,
        "sharp" => PsdAntiAlias::Sharp,
        "crisp" => PsdAntiAlias::Crisp,
        "strong" => PsdAntiAlias::Strong,
        _ => PsdAntiAlias::Smooth,
    }
}

#[derive(Deserialize, Debug)]
struct JsonTextBlock {
    id: String,
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    rotation_deg: Option<f32>,
    translation: Option<String>,
    direction: Option<String>, // "horizontal", "vertical"
    style: Option<JsonTextStyle>,
}

#[derive(Deserialize, Debug)]
struct JsonManifest {
    width: u32,
    height: u32,
    export_id: Option<String>,
    source_image: String,
    inpainted_image: Option<String>,
    rendered_image: Option<String>,
    rendered_overlay_image: Option<String>,
    text_blocks: Vec<JsonTextBlock>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();

    println!("[INFO] Reading manifest from: {}", args.manifest);
    let file = File::open(&args.manifest)?;
    let reader = BufReader::new(file);
    let manifest: JsonManifest = serde_json::from_reader(reader)?;

    println!("[INFO] Resolving input images...");
    let source_img = image::open(&manifest.source_image)?;

    let inpainted_img = match &manifest.inpainted_image {
        Some(path) if Path::new(path).exists() => Some(image::open(path)?),
        _ => None,
    };

    let rendered_img = match &manifest.rendered_image {
        Some(path) if Path::new(path).exists() => Some(image::open(path)?),
        _ => None,
    };

    let rendered_overlay_img = match &manifest.rendered_overlay_image {
        Some(path) if Path::new(path).exists() => Some(image::open(path)?),
        _ => None,
    };

    println!("[INFO] Mapping JSON blocks to PSD structures...");
    let mut psd_blocks = Vec::new();
    let mut block_images = HashMap::new();
    for block in manifest.text_blocks {
        let direction = match block.direction.as_deref() {
            Some("vertical") => Some(PsdTextDirection::Vertical),
            _ => Some(PsdTextDirection::Horizontal),
        };

        let style = block.style.map(|s| {
            let text_align = match s.align.as_deref() {
                Some("left") => Some(PsdTextAlign::Left),
                Some("right") => Some(PsdTextAlign::Right),
                _ => Some(PsdTextAlign::Center),
            };

            let anti_alias = parse_anti_alias(s.anti_alias.as_deref());
            PsdTextStyle {
                font_families: s.font_families,
                font_size: s.font_size,
                color: s.color,
                anti_alias: Some(anti_alias),
                effect: Some(PsdShaderEffect {
                    bold: s.bold,
                    italic: s.italic,
                }),
                text_align,
                vertical_align: s.vertical_align,
                stroke_width: s.stroke_width,
                stroke_color: s.stroke_color.as_deref().and_then(parse_hex_rgba),
                glow_enabled: s.glow_enabled,
                glow_radius: s.glow_radius,
                glow_color: s.glow_color.as_deref().and_then(parse_hex_rgba),
                line_height: s.line_height,
                tracking: s.tracking,
                padding: PsdPadding {
                    top: s.padding.top.max(0.0),
                    right: s.padding.right.max(0.0),
                    bottom: s.padding.bottom.max(0.0),
                    left: s.padding.left.max(0.0),
                },
                is_point_text: s
                    .is_point_text
                    .or_else(|| s.text_type.as_deref().map(|t| t == "point"))
                    .or(Some(true)),
            }
        });

        let fallback_img = rendered_overlay_img.as_ref().or(rendered_img.as_ref());
        let fallback = fallback_img.and_then(|overlay| {
            crop_text_fallback(
                overlay,
                block.x,
                block.y,
                block.width,
                block.height,
                block.translation.as_deref(),
                style.as_ref(),
            )
            .map(|(crop, rendered_x, rendered_y)| {
                let blob_ref = PsdBlobRef::new(format!("text-fallback:{}", block.id));
                block_images.insert(blob_ref.clone(), crop);
                (blob_ref, rendered_x, rendered_y)
            })
        });

        psd_blocks.push(PsdTextBlock {
            id: block.id,
            x: block.x,
            y: block.y,
            width: block.width,
            height: block.height,
            translation: block.translation,
            style,
            // Photoshop may retain pixel data while warning that editable text
            // needs recomposition. Keep a WYSIWYG crop so that fallback is never blank.
            rendered: fallback.as_ref().map(|(blob_ref, _, _)| blob_ref.clone()),
            rendered_x: fallback.as_ref().map(|(_, x, _)| *x),
            rendered_y: fallback.as_ref().map(|(_, _, y)| *y),
            rotation_deg: block.rotation_deg,
            font_prediction: None,
            source_direction: direction,
            rendered_direction: direction,
            detected_font_size_px: None,
        });
    }

    let psd_doc = PsdDocument {
        width: manifest.width,
        height: manifest.height,
        export_id: manifest.export_id,
        text_blocks: psd_blocks,
    };

    let resolved = ResolvedDocument {
        document: &psd_doc,
        source: &source_img,
        segment: None,
        inpainted: inpainted_img.as_ref(),
        rendered: rendered_img.as_ref(),
        brush_layer: None,
        block_images: &block_images,
    };

    let options = PsdExportOptions {
        include_original: true,
        include_inpainted: true,
        include_segment_mask: false,
        include_brush_layer: false,
        text_layer_mode: TextLayerMode::Editable, // Enable editable text layers!
    };

    println!("[INFO] Generating PSD at: {}", args.output);
    let output_path = Path::new(&args.output);
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let out_file = File::create(output_path)?;
    write_document(out_file, &resolved, &options)?;

    println!("[SUCCESS] PSD export completed successfully.");
    Ok(())
}

fn crop_text_fallback(
    overlay: &image::DynamicImage,
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    text: Option<&str>,
    style: Option<&PsdTextStyle>,
) -> Option<(image::DynamicImage, f32, f32)> {
    if !x.is_finite() || !y.is_finite() || !width.is_finite() || !height.is_finite() {
        return None;
    }
    // Photoshop initially shows cached channel pixels and only recomposes the
    // editable EngineData after the user edits the layer. A strict paragraph-
    // box crop therefore hides overflow lines on first open. Expand only the
    // cache; the editable TySh paragraph geometry remains unchanged.
    let line_count = text
        .map(|value| value.lines().count().max(1) as f32)
        .unwrap_or(1.0);
    let longest_line_chars = text
        .map(|value| {
            value
                .lines()
                .map(|line| line.chars().count())
                .max()
                .unwrap_or(0) as f32
        })
        .unwrap_or(0.0);
    let (required_height, vertical_align) = style
        .map(|value| {
            let font_size = value.font_size.unwrap_or(12.0).max(1.0);
            let leading = value.line_height.unwrap_or(font_size * 1.2);
            let leading = if leading > 0.0 && leading <= 3.0 {
                leading * font_size
            } else {
                leading.max(font_size)
            };
            let stroke_guard = value.stroke_width.unwrap_or(0.0).max(0.0) * 2.0 + 4.0;
            (
                value.padding.top.max(0.0)
                    + value.padding.bottom.max(0.0)
                    + line_count * leading
                    + stroke_guard,
                value.vertical_align.as_deref().unwrap_or("center"),
            )
        })
        .unwrap_or((height, "center"));
    let overflow = (required_height - height).max(0.0);
    let expanded_y = match vertical_align {
        "top" => y,
        "bottom" => y - overflow,
        _ => y - overflow / 2.0,
    };
    let expanded_height = height + overflow;

    // Point text is not constrained by a paragraph width. Its cached pixels
    // must therefore accommodate the longest authored line as well as all
    // lines vertically; otherwise Photoshop shows a truncated layer until it
    // performs the first recomposition. Paragraph text keeps its exact box.
    let (expanded_x, expanded_width) = style
        .map(|value| {
            if !value.is_point_text.unwrap_or(false) {
                return (x, width);
            }
            let font_size = value.font_size.unwrap_or(12.0).max(1.0);
            let stroke_guard = value.stroke_width.unwrap_or(0.0).max(0.0) * 2.0 + 4.0;
            let required_width = (value.padding.left.max(0.0)
                + value.padding.right.max(0.0)
                + longest_line_chars * font_size
                + stroke_guard)
                .max(width);
            let horizontal_overflow = required_width - width;
            let expanded_x = match value.text_align.unwrap_or(PsdTextAlign::Center) {
                PsdTextAlign::Left => x,
                PsdTextAlign::Right => x - horizontal_overflow,
                PsdTextAlign::Center => x - horizontal_overflow / 2.0,
            };
            (expanded_x, required_width)
        })
        .unwrap_or((x, width));

    let left = expanded_x.floor().max(0.0) as u32;
    let top = expanded_y.floor().max(0.0) as u32;
    let right = (expanded_x + expanded_width)
        .ceil()
        .max(0.0)
        .min(overlay.width() as f32) as u32;
    let bottom = (expanded_y + expanded_height)
        .ceil()
        .max(0.0)
        .min(overlay.height() as f32) as u32;
    if right <= left || bottom <= top {
        return None;
    }
    Some((
        overlay.crop_imm(left, top, right - left, bottom - top),
        left as f32,
        top as f32,
    ))
}

#[cfg(test)]
mod style_tests {
    use super::parse_hex_rgba;

    #[test]
    fn parses_psd_stroke_colors_from_manifest() {
        assert_eq!(parse_hex_rgba("#112233"), Some([0x11, 0x22, 0x33, 0xff]));
        assert_eq!(parse_hex_rgba("aabbcc80"), Some([0xaa, 0xbb, 0xcc, 0x80]));
        assert_eq!(parse_hex_rgba("#fff"), None);
    }
}

#[cfg(test)]
mod tests {
    use image::{DynamicImage, Rgba, RgbaImage};

    use super::crop_text_fallback;

    #[test]
    fn crops_browser_overlay_to_text_box_pixels() {
        let mut pixels = RgbaImage::new(20, 20);
        pixels.put_pixel(7, 8, Rgba([10, 20, 30, 255]));
        let overlay = DynamicImage::ImageRgba8(pixels);

        let (crop, rendered_x, rendered_y) =
            crop_text_fallback(&overlay, 5.2, 6.7, 5.0, 4.0, None, None).expect("crop");
        assert_eq!((crop.width(), crop.height()), (6, 5));
        assert_eq!(crop.to_rgba8().get_pixel(2, 2), &Rgba([10, 20, 30, 255]));
        assert_eq!((rendered_x, rendered_y), (5.0, 6.0));
    }

    #[test]
    fn cached_fallback_expands_for_multiline_text_overflow() {
        let overlay = DynamicImage::new_rgba8(200, 200);
        let style = super::PsdTextStyle {
            font_size: Some(20.0),
            line_height: Some(25.0),
            vertical_align: Some("center".to_string()),
            ..Default::default()
        };
        let (crop, _, rendered_y) = crop_text_fallback(
            &overlay,
            20.0,
            80.0,
            100.0,
            50.0,
            Some("หนึ่ง\nสอง\nสาม"),
            Some(&style),
        )
        .expect("expanded crop");
        assert_eq!(crop.height(), 80); // fractional centering rounds outward
        assert_eq!(rendered_y, 65.0);
    }

    #[test]
    fn cached_fallback_expands_point_text_longest_line() {
        let overlay = DynamicImage::new_rgba8(400, 200);
        let style = super::PsdTextStyle {
            font_size: Some(20.0),
            text_align: Some(super::PsdTextAlign::Center),
            is_point_text: Some(true),
            ..Default::default()
        };
        let (crop, rendered_x, _) = crop_text_fallback(
            &overlay,
            150.0,
            50.0,
            60.0,
            40.0,
            Some("abcdefghij"),
            Some(&style),
        )
        .expect("wide point-text crop");
        assert_eq!(crop.width(), 204); // 10 * 20px + 4px safety guard
        assert_eq!(rendered_x, 78.0);
    }
}
