"""
ImageTrans-Style Standalone Photoshop JSX Script Generator Service.

Generates self-contained ExtendScript (.jsx) files that can be run directly inside
Adobe Photoshop to create 100% native Photoshop text layers, eliminating binary format
incompatibilities and ensuring perfect Thai typography rendering for single pages or whole projects.
"""
import json
import logging
import re
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.all_models import Page, TextBlock, Project
from app.services.typesetting import get_effective_typesetting_spec
from app.services.project_paths import project_workspace_dir, inpainted_asset_path

logger = logging.getLogger("houmi-jsx-export")


def extract_page_blocks_data(page: Page, text_mode: str = "paragraph") -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """
    Extracts background image path, source image path, target PSD path, and parsed text blocks for a page.
    """
    bg_path = inpainted_asset_path(page)
    if not bg_path.exists() and page.inpainted_image_path:
        bg_path = Path(page.inpainted_image_path)
    if not bg_path.exists():
        bg_path = Path(page.source_image_path)

    bg_path_str = str(bg_path).replace("\\", "/")

    src_path_str = ""
    if page.source_image_path and Path(page.source_image_path).exists():
        src_path_str = str(Path(page.source_image_path).resolve()).replace("\\", "/")

    project = getattr(page, "project", None)
    if project is not None:
        psd_dir = project_workspace_dir(project) / "psd"
        psd_dir.mkdir(parents=True, exist_ok=True)
        psd_target = psd_dir / f"page_{page.page_number:03d}.psd"
    else:
        psd_target = Path(page.source_image_path).parent / f"page_{page.page_number:03d}.psd"

    psd_target_str = str(psd_target).replace("\\", "/")
    text_mode = str(text_mode or "paragraph").strip().lower()

    blocks_data = []
    for block in page.text_blocks:
        raw_text = (block.translation or block.source_text or "").strip()
        if not raw_text:
            continue

        spec = get_effective_typesetting_spec(block)

        # 1. Prefer explicit_lines computed by Houmi TypesettingSpec (auto-wraps lines per balloon bounds)
        non_empty_explicit = [l.strip() for l in (getattr(spec, "explicit_lines", None) or []) if l and l.strip()]
        if non_empty_explicit:
            raw_lines = non_empty_explicit
        else:
            raw_lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        # 2. Clean zero-width spaces, control chars, soft hyphens, and trailing spaces per line
        lines = []
        for line in raw_lines:
            cleaned_line = re.sub(r'[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u200b-\u200f\u202a-\u202e\u2060\ufeff]', '', line)
            cleaned_line = cleaned_line.replace('\u00a0', ' ').strip()
            if cleaned_line:
                lines.append(cleaned_line)

        if not lines:
            continue

        # Photoshop ExtendScript requires \r (carriage return) for native paragraph/line breaks
        final_text = "\r".join(lines)

        c_hex = str(getattr(spec, "resolved_color", None) or getattr(spec, "color", None) or "#000000")
        if not c_hex.startswith("#") or len(c_hex) < 7:
            c_hex = "#000000"

        try:
            r = int(c_hex[1:3], 16)
            g = int(c_hex[3:5], 16)
            b = int(c_hex[5:7], 16)
        except ValueError:
            r, g, b = 0, 0, 0

        postscript_font = spec.resolved_postscript_name or spec.resolved_font_family or getattr(spec, "font_family", None) or getattr(block, "font_family", None) or "THSarabunNew"
        font_size = float(spec.font_size or 32.0)
        align_mode = str(spec.text_align or "center").lower()

        block_meta = getattr(block, "extra_metadata", None) or {}
        is_bold = bool(
            getattr(spec, "bold", False) is True
            or getattr(block, "bold", False) is True
            or getattr(block, "font_weight", None) == "bold"
            or block_meta.get("font_weight") == "bold"
            or block_meta.get("bold") is True
        )
        is_italic = bool(
            getattr(spec, "italic", False) is True
            or getattr(block, "italic", False) is True
            or getattr(block, "font_style", None) == "italic"
            or block_meta.get("font_style") == "italic"
            or block_meta.get("italic") is True
        )

        bx = float(block.x)
        by = float(block.y)
        bw = float(block.width)
        bh = float(block.height)

        estimated_line_height = font_size * 1.22
        total_text_h = len(lines) * estimated_line_height
        v_offset = max(0.0, (bh - total_text_h) / 2.0)
        center_y = by + v_offset

        if align_mode == "center":
            anchor_x = bx + (bw / 2.0)
        elif align_mode == "right":
            anchor_x = bx + bw
        else:
            anchor_x = bx

        blocks_data.append({
            "id": block.id,
            "text": final_text,
            "font": postscript_font,
            "size": font_size,
            "color": [r, g, b],
            "x": bx,
            "y": by,
            "w": bw,
            "h": bh,
            "anchor_x": anchor_x,
            "center_y": center_y,
            "align": align_mode,
            "is_bold": is_bold,
            "is_italic": is_italic,
            "stroke_enabled": bool(getattr(spec, "stroke_enabled", False)),
            "stroke_width": float(getattr(spec, "stroke_width", 0.0) or 0.0),
        })

    return bg_path_str, src_path_str, psd_target_str, blocks_data


def generate_page_jsx_script(
    page_id: str,
    db: Session,
    text_mode: str = "paragraph",
    auto_save_psd: bool = True,
) -> str:
    """
    Generates an ExtendScript (.jsx) script for a single page.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    text_mode = str(text_mode or "paragraph").strip().lower()
    bg_path_str, src_path_str, psd_target_str, blocks_data = extract_page_blocks_data(page, text_mode=text_mode)
    blocks_json_str = json.dumps(blocks_data, ensure_ascii=False, indent=2)

    script_content = f"""/*
  ===========================================================================
  Houmi ImageTrans-Style Photoshop ExtendScript (JSX)
  Page: {page.page_number} | Mode: {text_mode}
  ===========================================================================
  รันสคริปต์นี้ใน Photoshop (File > Scripts > Browse...)
  เพื่อสร้างไฟล์ PSD และเลเยอร์ข้อความภาษาไทย Native แบบ 100%
*/

#target photoshop

(function main() {{
    app.displayDialogs = DialogModes.NO;

    function applyFontByName(textItem, fontName) {{
        if (!fontName) return;
        try {{ textItem.font = fontName; return; }} catch(e) {{}}
        var clean = fontName.replace(/\\s+/g, '');
        try {{ textItem.font = clean; return; }} catch(e) {{}}
        try {{
            for (var i = 0; i < app.fonts.length; i++) {{
                var f = app.fonts[i];
                if (f.name == fontName || f.postScriptName == fontName || f.family == fontName || f.name == clean || f.postScriptName == clean) {{
                    textItem.font = f.postScriptName;
                    return;
                }}
            }}
        }} catch(e) {{}}
    }}

    var bgFile = new File("{bg_path_str}");
    var doc = null;
    if (bgFile.exists) {
        doc = app.open(bgFile);
    } else {
        try {
            var scriptFolder = (new File($.fileName)).parent;
            var candidates = [
                "{Path(bg_path_str).name}",
                "page_{page.page_number:03d}_clean.png",
                "page_{page.page_number:03d}.png",
                "page_{page.page_number:03d}.jpg",
                "page_{page.page_number}.png",
                "clean_page.png",
                "{page.name or 'image.png'}"
            ];
            for (var c = 0; c < candidates.length; c++) {
                var candidate = new File(scriptFolder + "/" + candidates[c]);
                if (candidate.exists) {
                    doc = app.open(candidate);
                    break;
                }
            }
        } catch(e) {}
        if (!doc && app.documents.length > 0) {
            doc = app.activeDocument;
        }
    }

    if (!doc) {
        alert("ไม่พบไฟล์ภาพมังงะ กรุณาเปิดไฟล์ภาพใน Photoshop ก่อนรันสคริปต์นี้");
        return;
    }
    try {{
        doc.resizeImage(doc.width, doc.height, 72, ResampleMethod.NONE);
    }} catch(e) {{}}
    var bgLayer = doc.activeLayer;
    bgLayer.name = "Inpainted Background";

    var src_path = "{src_path_str}";
    if (src_path) {{
        try {{
            var srcFile = new File(src_path);
            if (srcFile.exists && srcFile.fsName !== bgFile.fsName) {{
                var srcDoc = app.open(srcFile);
                srcDoc.selection.selectAll();
                srcDoc.selection.copy();
                srcDoc.close(SaveOptions.DONOTSAVECHANGES);
                app.activeDocument = doc;
                var origLayer = doc.paste();
                try {{ origLayer.move(doc, ElementPlacement.PLACEATEND); }} catch(e) {{}}
                doc.layers[doc.layers.length - 1].name = "Original Image";
            }}
        }} catch(e) {{}}
    }}

    var blocks = {blocks_json_str};
    var textMode = "{text_mode}";

    function createLayers() {{
        for (var i = 0; i < blocks.length; i++) {{
            var b = blocks[i];
            var textLayer = doc.artLayers.add();
            textLayer.kind = LayerKind.TEXT;
            textLayer.name = "TL " + (i + 1) + " " + b.text.split("\\r")[0].substring(0, 30);

            var textItem = textLayer.textItem;

            applyFontByName(textItem, b.font);
            textItem.size = new UnitValue(b.size, "pt");

            var c = new SolidColor();
            c.rgb.red = b.color[0];
            c.rgb.green = b.color[1];
            c.rgb.blue = b.color[2];
            textItem.color = c;

            if (b.align === "left") {{
                textItem.justification = Justification.LEFT;
            }} else if (b.align === "right") {{
                textItem.justification = Justification.RIGHT;
            }} else {{
                textItem.justification = Justification.CENTER;
            }}

            try {{ textItem.syntheticBold = b.is_bold ? true : false; }} catch(e){{}}
            try {{ textItem.syntheticItalic = b.is_italic ? true : false; }} catch(e){{}}
            try {{ textItem.fauxBold = b.is_bold ? true : false; }} catch(e){{}}
            try {{ textItem.fauxItalic = b.is_italic ? true : false; }} catch(e){{}}

            if (textMode === "paragraph") {{
                textItem.kind = TextType.PARAGRAPHTEXT;
                textItem.width = new UnitValue(b.w, "px");
                textItem.height = new UnitValue(b.h, "px");
                textItem.position = [new UnitValue(b.x, "px"), new UnitValue(b.y, "px")];
            }} else {{
                textItem.kind = TextType.POINTTEXT;
                textItem.position = [new UnitValue(b.anchor_x, "px"), new UnitValue(b.center_y + (b.size * 0.85), "px")];
            }}

            textItem.contents = b.text;
            textItem.autoLeading = true;
            textItem.useFractionalLineWidths = true;

            try {{
                doc.activeLayer = textLayer;
                var idsetd = charIDToTypeID("setd");
                var desc1 = new ActionDescriptor();
                var ref1 = new ActionReference();
                ref1.putEnumerated(charIDToTypeID("TxLr"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
                desc1.putReference(charIDToTypeID("null"), ref1);
                var descText = new ActionDescriptor();
                descText.putInteger(stringIDToTypeID("composer"), 2);
                desc1.putObject(charIDToTypeID("to  "), charIDToTypeID("TxLr"), descText);
                executeAction(idsetd, desc1, DialogModes.NO);
            }} catch(e) {{}}
        }}
    }}

    doc.suspendHistory("Create Houmi Text Layers", "createLayers()");

    if ({str(auto_save_psd).lower()}) {{
        var psdOutFile = new File("{psd_target_str}");
        if (!psdOutFile.parent.exists) {{
            psdOutFile.parent.create();
        }}
        var psdOptions = new PhotoshopSaveOptions();
        psdOptions.layers = true;
        psdOptions.embedColorProfile = true;
        doc.saveAs(psdOutFile, psdOptions, true, Extension.LOWERCASE);
    }}
}})();
"""
    return script_content


def export_page_jsx(page_id: str, db: Session, text_mode: str = "paragraph") -> Path:
    """Exports a single page as a .jsx ExtendScript file on disk."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    script_code = generate_page_jsx_script(page_id, db, text_mode=text_mode)

    project = getattr(page, "project", None)
    if project is not None:
        psd_dir = project_workspace_dir(project) / "psd"
        psd_dir.mkdir(parents=True, exist_ok=True)
        jsx_path = psd_dir / f"page_{page.page_number:03d}.jsx"
    else:
        jsx_path = Path(page.source_image_path).parent / f"page_{page.page_number:03d}.jsx"

    jsx_path.write_text(script_code, encoding="utf-8")
    return jsx_path


def generate_project_jsx_script(
    project_id: str,
    db: Session,
    text_mode: str = "paragraph",
    auto_save_psd: bool = True,
) -> str:
    """
    Generates a master ExtendScript (.jsx) script for an ENTIRE project.
    When executed inside Photoshop, it loops through every page in the project,
    opens each clean image, creates text layers with native Photoshop settings,
    enables Adobe World-Ready Composer, and saves each PSD file automatically.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    pages = sorted(project.pages, key=lambda p: p.page_number)
    if not pages:
        raise ValueError("Project has no pages")

    text_mode = str(text_mode or "paragraph").strip().lower()

    pages_data = []
    for page in pages:
        bg_path_str, src_path_str, psd_target_str, blocks_data = extract_page_blocks_data(page, text_mode=text_mode)
        pages_data.append({
            "page_number": page.page_number,
            "bg_path": bg_path_str,
            "src_path": src_path_str,
            "psd_target": psd_target_str,
            "blocks": blocks_data
        })

    pages_json_str = json.dumps(pages_data, ensure_ascii=False, indent=2)

    script_content = f"""/*
  ===========================================================================
  Houmi ImageTrans-Style Photoshop Master Project ExtendScript (JSX)
  Project: {project.name} | Total Pages: {len(pages)} | Mode: {text_mode}
  ===========================================================================
  รันสคริปต์นี้ใน Photoshop เพื่อสร้างไฟล์ PSD และ Text Layers สำหรับทุกหน้าทั้งโปรเจกต์
*/

#target photoshop

(function main() {{
    app.displayDialogs = DialogModes.NO;

    function applyFontByName(textItem, fontName) {{
        if (!fontName) return;
        try {{ textItem.font = fontName; return; }} catch(e) {{}}
        var clean = fontName.replace(/\\s+/g, '');
        try {{ textItem.font = clean; return; }} catch(e) {{}}
        try {{
            for (var i = 0; i < app.fonts.length; i++) {{
                var f = app.fonts[i];
                if (f.name == fontName || f.postScriptName == fontName || f.family == fontName || f.name == clean || f.postScriptName == clean) {{
                    textItem.font = f.postScriptName;
                    return;
                }}
            }}
        }} catch(e) {{}}
    }}

    var pages = {pages_json_str};
    var textMode = "{text_mode}";
    var autoSavePsd = {str(auto_save_psd).lower()};

    var totalCreated = 0;

    for (var p = 0; p < pages.length; p++) {{
        var pageData = pages[p];
        var bgFile = new File(pageData.bg_path);

        if (!bgFile.exists) {{
            continue;
        }}

        var doc = app.open(bgFile);
        try {{
            doc.resizeImage(doc.width, doc.height, 72, ResampleMethod.NONE);
        }} catch(e) {{}}

        var bgLayer = doc.activeLayer;
        bgLayer.name = "Inpainted Background";

        if (pageData.src_path) {{
            try {{
                var srcFile = new File(pageData.src_path);
                if (srcFile.exists && srcFile.fsName !== bgFile.fsName) {{
                    var srcDoc = app.open(srcFile);
                    srcDoc.selection.selectAll();
                    srcDoc.selection.copy();
                    srcDoc.close(SaveOptions.DONOTSAVECHANGES);
                    app.activeDocument = doc;
                    var origLayer = doc.paste();
                    try {{ origLayer.move(doc, ElementPlacement.PLACEATEND); }} catch(e) {{}}
                    doc.layers[doc.layers.length - 1].name = "Original Image";
                }}
            }} catch(e) {{}}
        }}

        var blocks = pageData.blocks;

        (function(currentDoc, currentBlocks) {{
            function createPageLayers() {{
                for (var i = 0; i < currentBlocks.length; i++) {{
                    var b = currentBlocks[i];
                    var textLayer = currentDoc.artLayers.add();
                    textLayer.kind = LayerKind.TEXT;
                    textLayer.name = "TL " + (i + 1) + " " + b.text.split("\\r")[0].substring(0, 30);

                    var textItem = textLayer.textItem;

                    applyFontByName(textItem, b.font);
                    textItem.size = new UnitValue(b.size, "pt");

                    var c = new SolidColor();
                    c.rgb.red = b.color[0];
                    c.rgb.green = b.color[1];
                    c.rgb.blue = b.color[2];
                    textItem.color = c;

                    if (b.align === "left") {{
                        textItem.justification = Justification.LEFT;
                    }} else if (b.align === "right") {{
                        textItem.justification = Justification.RIGHT;
                    }} else {{
                        textItem.justification = Justification.CENTER;
                    }}

                    try {{ textItem.syntheticBold = b.is_bold ? true : false; }} catch(e){{}}
                    try {{ textItem.syntheticItalic = b.is_italic ? true : false; }} catch(e){{}}
                    try {{ textItem.fauxBold = b.is_bold ? true : false; }} catch(e){{}}
                    try {{ textItem.fauxItalic = b.is_italic ? true : false; }} catch(e){{}}

                    if (textMode === "paragraph") {{
                        textItem.kind = TextType.PARAGRAPHTEXT;
                        textItem.width = new UnitValue(b.w, "px");
                        textItem.height = new UnitValue(b.h, "px");
                        textItem.position = [new UnitValue(b.x, "px"), new UnitValue(b.y, "px")];
                    }} else {{
                        textItem.kind = TextType.POINTTEXT;
                        textItem.position = [new UnitValue(b.anchor_x, "px"), new UnitValue(b.center_y + (b.size * 0.85), "px")];
                    }}

                    textItem.contents = b.text;
                    textItem.autoLeading = true;
                    textItem.useFractionalLineWidths = true;

                    try {{
                        currentDoc.activeLayer = textLayer;
                        var idsetd = charIDToTypeID("setd");
                        var desc1 = new ActionDescriptor();
                        var ref1 = new ActionReference();
                        ref1.putEnumerated(charIDToTypeID("TxLr"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
                        desc1.putReference(charIDToTypeID("null"), ref1);
                        var descText = new ActionDescriptor();
                        descText.putInteger(stringIDToTypeID("composer"), 2);
                        desc1.putObject(charIDToTypeID("to  "), charIDToTypeID("TxLr"), descText);
                        executeAction(idsetd, desc1, DialogModes.NO);
                    }} catch(e) {{}}
                }}
            }}

            currentDoc.suspendHistory("Create Houmi Text Layers", "createPageLayers()");
        }})(doc, blocks);

        if (autoSavePsd) {{
            var psdOutFile = new File(pageData.psd_target);
            if (!psdOutFile.parent.exists) {{
                psdOutFile.parent.create();
            }}
            var psdOptions = new PhotoshopSaveOptions();
            psdOptions.layers = true;
            psdOptions.embedColorProfile = true;
            doc.saveAs(psdOutFile, psdOptions, true, Extension.LOWERCASE);
        }}
        totalCreated++;
    }}
    alert("ส่งออกเรียบร้อยแล้ว! สร้างและรันไฟล์ PSD ภาษาไทยทั้งหมด " + totalCreated + " หน้าใน Photoshop");
}})();
"""
    return script_content


def export_project_jsx(project_id: str, db: Session, text_mode: str = "paragraph") -> Path:
    """Exports a master .jsx ExtendScript file for an ENTIRE project on disk."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    script_code = generate_project_jsx_script(project_id, db, text_mode=text_mode)

    psd_dir = project_workspace_dir(project) / "psd"
    psd_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in (project.name or "project")])
    jsx_path = psd_dir / f"{safe_title}_master_batch.jsx"

    jsx_path.write_text(script_code, encoding="utf-8")
    return jsx_path
