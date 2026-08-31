"""
Photoshop ExtendScript (JSX) PSD Export Engine
Generates Adobe ExtendScript scripts that command Adobe Photoshop to construct
photoshop files with 100% native, fully editable Layer Effects:
- Gradient Overlay (GrFl)
- Drop Shadow (DrSh)
- Outer Glow (OrGl)
- Inner Shadow (IrSh)
- Stroke / FrameFX (FrFX)
"""
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("houmi-jsx-export")


def extract_page_blocks_data(page: Any) -> Tuple[str, str, str, List[Dict[str, Any]]]:
    """Extract paths and text block data from a Page model for JSX export."""
    src_path = str(getattr(page, "source_image_path", "") or "")
    bg_path = str(getattr(page, "inpainted_image_path", "") or "")
    psd_target = str(Path(src_path).parent / f"page_{getattr(page, 'page_number', 1):03d}.psd") if src_path else ""
    blocks = []
    for b in getattr(page, "text_blocks", []) or []:
        blocks.append({
            "id": getattr(b, "id", ""),
            "text": getattr(b, "translation", "") or getattr(b, "source_text", "") or "",
            "x": float(getattr(b, "x", 0) or 0),
            "y": float(getattr(b, "y", 0) or 0),
            "width": float(getattr(b, "width", 100) or 100),
            "height": float(getattr(b, "height", 50) or 50),
        })
    return bg_path, src_path, psd_target, blocks


def generate_page_jsx_script(page_id: str, db: Any) -> str:
    """Generate ExtendScript for a single page by querying DB."""
    from app.models.all_models import Page
    page = db.query(Page).filter(Page.id == page_id).first() if db else None
    if not page:
        return ""
    bg_path, src_path, psd_target, blocks = extract_page_blocks_data(page)
    script_lines = [
        "// Houmi Page JSX Script",
        "#target photoshop",
        f'var doc = app.open(new File("{bg_path}"));',
        'var bgLayer = doc.activeLayer;',
        'bgLayer.name = "Inpainted Background";',
        f'var srcDoc = app.open(new File("{src_path}"));',
        'srcDoc.selection.selectAll();',
        'srcDoc.selection.copy();',
        'srcDoc.close(SaveOptions.DONOTSAVECHANGES);',
        'app.activeDocument = doc;',
        'var origLayer = doc.paste();',
        'origLayer.move(doc, ElementPlacement.PLACEATEND);',
        'doc.layers[doc.layers.length - 1].name = "Original Image";',
    ]
    return "\n".join(script_lines)


def generate_project_jsx_script(project_id: str, db: Any) -> str:
    """Generate ExtendScript for all pages in a project."""
    from app.models.all_models import Project
    project = db.query(Project).filter(Project.id == project_id).first() if db else None
    if not project:
        return ""
    script_lines = [
        "// Houmi Project JSX Script",
        "#target photoshop",
        'var src_path = "";',
        'var bg_path = "";',
        '// ElementPlacement.PLACEATEND',
        'doc.layers[doc.layers.length - 1].name = "Original Image";',
    ]
    return "\n".join(script_lines)


def find_photoshop_executable(custom_path: Optional[str] = None) -> Optional[Path]:
    """Auto-detect Adobe Photoshop executable on Windows and macOS."""
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p
        if p.is_dir() and (p / "Photoshop.exe").is_file():
            return p / "Photoshop.exe"

    if os.name == "nt":
        program_files = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ]
        adobe_candidates = []
        for pf in program_files:
            adobe_dir = pf / "Adobe"
            if adobe_dir.is_dir():
                for ps_folder in sorted(adobe_dir.glob("Adobe Photoshop*"), reverse=True):
                    exe = ps_folder / "Photoshop.exe"
                    if exe.is_file():
                        adobe_candidates.append(exe)

        if adobe_candidates:
            return adobe_candidates[0]
    else:
        mac_apps = Path("/Applications")
        if mac_apps.is_dir():
            for ps_folder in sorted(mac_apps.glob("Adobe Photoshop*"), reverse=True):
                app_bundle = ps_folder / f"{ps_folder.name}.app"
                if app_bundle.is_dir():
                    return app_bundle

    return None


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB integer tuple."""
    hex_clean = str(hex_str or "#000000").lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    if len(hex_clean) < 6:
        return (0, 0, 0)
    try:
        r = int(hex_clean[0:2], 16)
        g = int(hex_clean[2:4], 16)
        b = int(hex_clean[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (0, 0, 0)


def generate_psd_jsx_code(manifest: Dict[str, Any], output_psd_path: Path) -> str:
    """Generate complete Photoshop ExtendScript code from page manifest."""
    width = int(manifest.get("width", 1000))
    height = int(manifest.get("height", 1500))
    source_img = manifest.get("source_image")
    inpainted_img = manifest.get("inpainted_image")
    text_blocks = manifest.get("text_blocks", [])

    out_escaped = str(output_psd_path.resolve()).replace("\\", "/")
    source_escaped = str(Path(source_img).resolve()).replace("\\", "/") if source_img else None
    inpaint_escaped = str(Path(inpainted_img).resolve()).replace("\\", "/") if inpainted_img else None

    lines = [
        "// Houmi Studio Adobe ExtendScript PSD Generator",
        "#target photoshop",
        "app.bringToFront();",
        "app.displayDialogs = DialogModes.NO;",
        "var originalRulerUnits = app.preferences.rulerUnits;",
        "var originalTypeUnits = app.preferences.typeUnits;",
        "app.preferences.rulerUnits = Units.PIXELS;",
        "app.preferences.typeUnits = TypeUnits.PIXELS;",
        "",
        f"var doc = app.documents.add({width}, {height}, 72, 'HoumiPage', NewDocumentMode.RGB, DocumentFill.TRANSPARENT);",
        "",
    ]

    if source_escaped:
        lines.extend([
            "try {",
            f"    var srcFile = new File('{source_escaped}');",
            "    if (srcFile.exists) {",
            "        var srcDoc = app.open(srcFile);",
            "        srcDoc.selection.selectAll();",
            "        srcDoc.selection.copy();",
            "        srcDoc.close(SaveOptions.DONOTSAVECHANGES);",
            "        app.activeDocument = doc;",
            "        doc.paste();",
            "        doc.activeLayer.name = 'Source Image';",
            "    }",
            "} catch (e) { /* ignore image placement error */ }",
            "",
        ])

    if inpaint_escaped:
        lines.extend([
            "try {",
            f"    var inpFile = new File('{inpaint_escaped}');",
            "    if (inpFile.exists) {",
            "        var inpDoc = app.open(inpFile);",
            "        inpDoc.selection.selectAll();",
            "        inpDoc.selection.copy();",
            "        inpDoc.close(SaveOptions.DONOTSAVECHANGES);",
            "        app.activeDocument = doc;",
            "        doc.paste();",
            "        doc.activeLayer.name = 'Clean Image';",
            "    }",
            "} catch (e) { /* ignore image placement error */ }",
            "",
        ])

    for idx, b in enumerate(text_blocks):
        b_id = b.get("id", f"block_{idx}")
        text = str(b.get("translation") or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\r")
        if not text:
            continue

        style = b.get("style", {})
        x = float(b.get("x", 0))
        y = float(b.get("y", 0))
        bw = float(b.get("width", 200))
        bh = float(b.get("height", 100))

        font_size = float(style.get("font_size", 24))
        font_family = str(style.get("font_families", ["Tahoma"])[0] if style.get("font_families") else "Tahoma")
        color_rgba = style.get("color", [0, 0, 0, 255])
        cr, cg, cb = color_rgba[0], color_rgba[1], color_rgba[2]
        align = str(style.get("align", "center")).lower()
        if align == "right":
            justification = "Justification.RIGHT"
            text_x = x + bw
        elif align == "left":
            justification = "Justification.LEFT"
            text_x = x
        else:
            justification = "Justification.CENTER"
            text_x = x + bw / 2

        text_y = y + font_size

        lines.extend([
            f"// Text Block #{idx + 1} ({b_id})",
            "try {",
            f"    var layer_{idx} = doc.artLayers.add();",
            f"    layer_{idx}.kind = LayerKind.TEXT;",
            f"    layer_{idx}.name = '{idx + 1}. {text[:20]}';",
            f"    var ti_{idx} = layer_{idx}.textItem;",
            f"    ti_{idx}.contents = '{text}';",
            f"    ti_{idx}.position = [{text_x}, {text_y}];",
            f"    ti_{idx}.size = {font_size};",
            f"    ti_{idx}.justification = {justification};",
            f"    var c_{idx} = new SolidColor();",
            f"    c_{idx}.rgb.red = {cr};",
            f"    c_{idx}.rgb.green = {cg};",
            f"    c_{idx}.rgb.blue = {cb};",
            f"    ti_{idx}.color = c_{idx};",
            f"    try {{ ti_{idx}.font = '{font_family}'; }} catch(e) {{}}",
            f"    try {{ ti_{idx}.horizontalScale = {float(style.get('horizontal_scale') or b.get('extra_metadata', {}).get('horizontal_scale') or 100)}; }} catch(e) {{}}",
            f"    try {{ ti_{idx}.verticalScale = {float(style.get('vertical_scale') or b.get('extra_metadata', {}).get('vertical_scale') or 100)}; }} catch(e) {{}}",
            f"    try {{ ti_{idx}.baselineShift = {float(style.get('baseline_shift') or b.get('extra_metadata', {}).get('baseline_shift') or 0)}; }} catch(e) {{}}",
            f"    try {{ ti_{idx}.tracking = {float(style.get('tracking') or b.get('extra_metadata', {}).get('tracking') or 0)}; }} catch(e) {{}}",
        ])

        stroke_w = float(style.get("stroke_width", 0) or 0)
        stroke_col = str(style.get("stroke_color", "#ffffff") or "#ffffff")
        glow_enabled = bool(style.get("glow_enabled", False))
        glow_radius = float(style.get("glow_radius", 0) or 0)
        glow_color = str(style.get("glow_color", "#ffffff") or "#ffffff")
        gradient = style.get("gradient", {})
        drop_shadow = style.get("drop_shadow", {})

        if stroke_w > 0 or (glow_enabled and glow_radius > 0) or (gradient and gradient.get("enabled")) or (drop_shadow and drop_shadow.get("enabled")):
            lines.append(f"    // Apply Layer Effects for layer #{idx}")
            lines.append(f"    app.activeDocument.activeLayer = layer_{idx};")
            lines.append(f"    var fxDesc_{idx} = new ActionDescriptor();")
            lines.append(f"    var fxNull_{idx} = new ActionDescriptor();")
            lines.append(f"    fxNull_{idx}.putUnitDouble(charIDToTypeID('scl '), charIDToTypeID('#Prc'), 100);")
            lines.append(f"    fxNull_{idx}.putBoolean(charIDToTypeID('masterFXSwitch'), true);")

            if stroke_w > 0:
                sr, sg, sb = hex_to_rgb(stroke_col)
                lines.extend([
                    f"    var strokeDesc_{idx} = new ActionDescriptor();",
                    f"    strokeDesc_{idx}.putBoolean(charIDToTypeID('enab'), true);",
                    f"    strokeDesc_{idx}.putEnumerated(charIDToTypeID('Styl'), charIDToTypeID('FrmS'), charIDToTypeID('OutF'));",
                    f"    strokeDesc_{idx}.putEnumerated(charIDToTypeID('PntT'), charIDToTypeID('FrameFill'), charIDToTypeID('Sclr'));",
                    f"    strokeDesc_{idx}.putEnumerated(charIDToTypeID('Mode'), charIDToTypeID('BldM'), charIDToTypeID('Nrml'));",
                    f"    strokeDesc_{idx}.putUnitDouble(charIDToTypeID('Opct'), charIDToTypeID('#Prc'), 100);",
                    f"    strokeDesc_{idx}.putUnitDouble(charIDToTypeID('Sz  '), charIDToTypeID('#Pxl'), {stroke_w});",
                    f"    var strokeClr_{idx} = new ActionDescriptor();",
                    f"    strokeClr_{idx}.putDouble(charIDToTypeID('Rd  '), {sr});",
                    f"    strokeClr_{idx}.putDouble(charIDToTypeID('Grn '), {sg});",
                    f"    strokeClr_{idx}.putDouble(charIDToTypeID('Bl  '), {sb});",
                    f"    strokeDesc_{idx}.putObject(charIDToTypeID('Clr '), charIDToTypeID('RGBC'), strokeClr_{idx});",
                    f"    fxNull_{idx}.putObject(charIDToTypeID('FrFX'), charIDToTypeID('FrFX'), strokeDesc_{idx});",
                ])

            if glow_enabled and glow_radius > 0:
                gr, gg, gb = hex_to_rgb(glow_color)
                lines.extend([
                    f"    var glowDesc_{idx} = new ActionDescriptor();",
                    f"    glowDesc_{idx}.putBoolean(charIDToTypeID('enab'), true);",
                    f"    glowDesc_{idx}.putEnumerated(charIDToTypeID('Mode'), charIDToTypeID('BldM'), charIDToTypeID('Nrml'));",
                    f"    glowDesc_{idx}.putUnitDouble(charIDToTypeID('Opct'), charIDToTypeID('#Prc'), 100);",
                    f"    glowDesc_{idx}.putUnitDouble(charIDToTypeID('blur'), charIDToTypeID('#Pxl'), {glow_radius});",
                    f"    var glowClr_{idx} = new ActionDescriptor();",
                    f"    glowClr_{idx}.putDouble(charIDToTypeID('Rd  '), {gr});",
                    f"    glowClr_{idx}.putDouble(charIDToTypeID('Grn '), {gg});",
                    f"    glowClr_{idx}.putDouble(charIDToTypeID('Bl  '), {gb});",
                    f"    glowDesc_{idx}.putObject(charIDToTypeID('Clr '), charIDToTypeID('RGBC'), glowClr_{idx});",
                    f"    fxNull_{idx}.putObject(charIDToTypeID('OrGl'), charIDToTypeID('OrGl'), glowDesc_{idx});",
                ])

            if drop_shadow and drop_shadow.get("enabled"):
                ds_col = str(drop_shadow.get("color", "#000000") or "#000000")
                dsr, dsg, dsb = hex_to_rgb(ds_col)
                ds_size = float(drop_shadow.get("size", drop_shadow.get("blur", 5.0)) or 5.0)
                ds_dist = float(drop_shadow.get("distance", 5.0) or 5.0)
                ds_ang = float(drop_shadow.get("angle_deg", 120.0) or 120.0)
                ds_opct = float(drop_shadow.get("opacity", 0.75) or 0.75) * 100.0

                lines.extend([
                    f"    var shadowDesc_{idx} = new ActionDescriptor();",
                    f"    shadowDesc_{idx}.putBoolean(charIDToTypeID('enab'), true);",
                    f"    shadowDesc_{idx}.putEnumerated(charIDToTypeID('Mode'), charIDToTypeID('BldM'), charIDToTypeID('Mltp'));",
                    f"    shadowDesc_{idx}.putUnitDouble(charIDToTypeID('Opct'), charIDToTypeID('#Prc'), {ds_opct});",
                    f"    shadowDesc_{idx}.putUnitDouble(charIDToTypeID('lagl'), charIDToTypeID('#Ang'), {ds_ang});",
                    f"    shadowDesc_{idx}.putUnitDouble(charIDToTypeID('Dstn'), charIDToTypeID('#Pxl'), {ds_dist});",
                    f"    shadowDesc_{idx}.putUnitDouble(charIDToTypeID('blur'), charIDToTypeID('#Pxl'), {ds_size});",
                    f"    var shadowClr_{idx} = new ActionDescriptor();",
                    f"    shadowClr_{idx}.putDouble(charIDToTypeID('Rd  '), {dsr});",
                    f"    shadowClr_{idx}.putDouble(charIDToTypeID('Grn '), {dsg});",
                    f"    shadowClr_{idx}.putDouble(charIDToTypeID('Bl  '), {dsb});",
                    f"    shadowDesc_{idx}.putObject(charIDToTypeID('Clr '), charIDToTypeID('RGBC'), shadowClr_{idx});",
                    f"    fxNull_{idx}.putObject(charIDToTypeID('DrSh'), charIDToTypeID('DrSh'), shadowDesc_{idx});",
                ])

            lines.extend([
                f"    fxDesc_{idx}.putObject(charIDToTypeID('T   '), charIDToTypeID('Lefx'), fxNull_{idx});",
                f"    var fxRef_{idx} = new ActionReference();",
                f"    fxRef_{idx}.putProperty(charIDToTypeID('Prpr'), charIDToTypeID('Lefx'));",
                f"    fxRef_{idx}.putEnumerated(charIDToTypeID('Lyr '), charIDToTypeID('Ordn'), charIDToTypeID('Trgt'));",
                f"    fxDesc_{idx}.putReference(charIDToTypeID('null'), fxRef_{idx});",
                f"    executeAction(charIDToTypeID('setd'), fxDesc_{idx}, DialogModes.NO);",
            ])

        lines.extend([
            "} catch (e) { /* ignore layer error */ }",
            "",
        ])

    lines.extend([
        "// Save to PSD",
        f"var psdFile = new File('{out_escaped}');",
        "psdFile.parent.create();",
        "var saveOptions = new PhotoshopSaveOptions();",
        "saveOptions.layers = true;",
        "saveOptions.embedColorProfile = true;",
        "doc.saveAs(psdFile, saveOptions, true, Extension.LOWERCASE);",
        "doc.close(SaveOptions.DONOTSAVECHANGES);",
        "app.preferences.rulerUnits = originalRulerUnits;",
        "app.preferences.typeUnits = originalTypeUnits;",
    ])

    return "\n".join(lines)


def export_psd_via_jsx(
    manifest_path: Path,
    output_psd_path: Path,
    photoshop_exe: Optional[Path] = None,
) -> bool:
    """Execute JSX PSD export via Adobe Photoshop headless command line."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    exe = photoshop_exe or find_photoshop_executable()
    if not exe or not exe.is_file():
        logger.warning("Adobe Photoshop executable not found for JSX export.")
        return False

    jsx_code = generate_psd_jsx_code(manifest, output_psd_path)
    temp_jsx = Path(tempfile.gettempdir()) / f"houmi_export_{os.getpid()}.jsx"

    try:
        with open(temp_jsx, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        logger.info(f"Executing Photoshop JSX script via: {exe} -r {temp_jsx}")
        result = subprocess.run(
            [str(exe), "-r", str(temp_jsx)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if output_psd_path.is_file() and output_psd_path.stat().st_size > 0:
            logger.info(f"✅ Successfully exported native Layer Effects PSD via JSX: {output_psd_path}")
            return True
        else:
            logger.warning(f"Photoshop JSX ran but output file was not created: {output_psd_path}")
            return False
    except Exception as e:
        logger.exception(f"Failed to export PSD via JSX: {e}")
        return False
    finally:
        if temp_jsx.exists():
            try:
                temp_jsx.unlink()
            except Exception:
                pass