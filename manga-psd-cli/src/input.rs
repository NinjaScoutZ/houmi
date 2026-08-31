//! Self-contained input types for the PSD export.
//!
//! `houzi-app` constructs a `PsdDocument` by walking the scene, resolves its
//! blobs, and hands the result to `export_document`. The PSD crate does not
//! depend on `houzi-core`.

use std::collections::HashMap;

use image::DynamicImage;

/// Content-addressed blob reference used as a key for resolved images.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PsdBlobRef(pub String);

impl PsdBlobRef {
    pub fn new(hash: impl Into<String>) -> Self {
        Self(hash.into())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PsdTextDirection {
    Horizontal,
    Vertical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PsdTextAlign {
    #[default]
    Left,
    Center,
    Right,
}

#[derive(Debug, Clone, Copy, Default)]
pub struct PsdShaderEffect {
    pub italic: bool,
    pub bold: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PsdAntiAlias {
    None,
    Sharp,
    Crisp,
    Strong,
    #[default]
    Smooth,
}

impl PsdAntiAlias {
    pub fn photoshop_name(self) -> &'static str {
        match self {
            Self::None => "antiAliasNone",
            Self::Sharp => "antiAliasSharp",
            Self::Crisp => "antiAliasCrisp",
            Self::Strong => "antiAliasStrong",
            Self::Smooth => "antiAliasSmooth",
        }
    }

    pub fn engine_value(self) -> i32 {
        match self {
            Self::None => 0,
            Self::Sharp => 1,
            Self::Crisp => 2,
            Self::Strong => 3,
            Self::Smooth => 4,
        }
    }
}

/// Insets inside the Photoshop paragraph/area-text box. These values mirror
/// `TypesettingSpec.padding` and are deliberately kept in document pixels.
#[derive(Debug, Clone, Copy, Default)]
pub struct PsdPadding {
    pub top: f32,
    pub right: f32,
    pub bottom: f32,
    pub left: f32,
}

#[derive(Debug, Clone, Default)]
pub struct PsdTextStyle {
    pub font_families: Vec<String>,
    pub font_size: Option<f32>,
    pub color: [u8; 4],
    pub anti_alias: Option<PsdAntiAlias>,
    pub effect: Option<PsdShaderEffect>,
    pub text_align: Option<PsdTextAlign>,
    /// Vertical paragraph alignment used by the browser/PNG renderer.
    pub vertical_align: Option<String>,
    /// Outline width in px (from TypesettingSpec.stroke_width)
    pub stroke_width: Option<f32>,
    /// Outline color RGBA (from TypesettingSpec.stroke_color)
    pub stroke_color: Option<[u8; 4]>,
    /// Absolute line height in px (from TypesettingSpec.line_height)
    pub line_height: Option<f32>,
    /// Tracking in thousandths of an em (Fabric/Photoshop convention)
    pub tracking: Option<f32>,
    pub padding: PsdPadding,
    pub is_point_text: Option<bool>,
}

#[derive(Debug, Clone)]
pub struct PsdNamedFontPrediction {
    pub name: String,
}

#[derive(Debug, Clone, Default)]
pub struct PsdFontPrediction {
    pub named_fonts: Vec<PsdNamedFontPrediction>,
    pub text_color: [u8; 3],
    pub font_size_px: f32,
    pub angle_deg: f32,
}

#[derive(Debug, Clone, Default)]
pub struct PsdTextBlock {
    pub id: String,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub translation: Option<String>,
    pub style: Option<PsdTextStyle>,
    pub rendered: Option<PsdBlobRef>,
    /// Document-space origin of the cached browser-rendered pixels. This may
    /// extend outside the paragraph box when glyphs overflow it. TySh geometry
    /// remains canonical; only Photoshop's initial pixel cache uses this box.
    pub rendered_x: Option<f32>,
    pub rendered_y: Option<f32>,
    pub rotation_deg: Option<f32>,
    pub font_prediction: Option<PsdFontPrediction>,
    pub source_direction: Option<PsdTextDirection>,
    pub rendered_direction: Option<PsdTextDirection>,
    pub detected_font_size_px: Option<f32>,
}

#[derive(Debug, Clone, Default)]
pub struct PsdDocument {
    pub width: u32,
    pub height: u32,
    pub export_id: Option<String>,
    pub text_blocks: Vec<PsdTextBlock>,
}

/// A document with all blob refs resolved to in-memory images.
pub struct ResolvedDocument<'a> {
    pub document: &'a PsdDocument,
    pub source: &'a DynamicImage,
    pub segment: Option<&'a DynamicImage>,
    pub inpainted: Option<&'a DynamicImage>,
    pub rendered: Option<&'a DynamicImage>,
    pub brush_layer: Option<&'a DynamicImage>,
    /// Resolved pre-rendered text-block images, keyed by `PsdTextBlock.rendered`.
    pub block_images: &'a HashMap<PsdBlobRef, DynamicImage>,
}
