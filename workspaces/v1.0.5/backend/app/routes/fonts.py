import os
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Response
from fastapi.responses import FileResponse
from app.services.font_registry import font_registry

router = APIRouter(tags=["Fonts"])

@router.get("/fonts/list")
def list_fonts():
    """
    Returns full list of available fonts, detailed styles, and rich family structures.
    Preserves backward compatibility for frontend state while adding rich categorization.
    """
    raw_details = {}
    for entry in font_registry.registry.values():
        fam = entry.family
        if fam not in raw_details:
            raw_details[fam] = set()
        formatted_style = entry.style.replace("_", " ").title()
        raw_details[fam].add(formatted_style)

    details = {}
    standard_styles = ["Regular", "Italic", "Bold", "Bold Italic"]
    for fam, styles in raw_details.items():
        all_styles = sorted(list(set(list(styles) + standard_styles)))
        details[fam] = all_styles
        details[fam.lower()] = all_styles

    for alias, (fam, _) in font_registry.aliases.items():
        if fam in details:
            details[alias] = details[fam]
            details[alias.lower()] = details[fam]

    return {
        "fonts": font_registry.list_families(),
        "details": details,
        "families": font_registry.get_family_details()
    }

@router.get("/fonts/css")
def get_fonts_css():
    """
    Dynamically generates a CSS stylesheet with @font-face rules for all registered fonts and their aliases.
    This allows Fabric.js canvas and browser CSS to render authentic font faces accurately regardless of casing/spelling differences.
    """
    css_rules = []
    seen_variants = set()

    for entry in font_registry.registry.values():
        if not entry.file_path or not entry.file_path.exists():
            continue

        font_format = "truetype"
        ext = entry.file_path.suffix.lower()
        if ext == ".otf":
            font_format = "opentype"
        elif ext == ".woff2":
            font_format = "woff2"
        elif ext == ".woff":
            font_format = "woff"
        elif ext == ".ttc":
            font_format = "collection"

        url_path = f"/api/fonts/file/{entry.stable_id}"

        # Collect all font-family alias names that should resolve to this font binary
        family_aliases = {entry.family}
        if entry.postscript_name:
            family_aliases.add(entry.postscript_name)
        if entry.file_path:
            family_aliases.add(entry.file_path.stem)
        
        # Add common spelling & template aliases
        fam_lower = entry.family.lower()
        stem_lower = entry.file_path.stem.lower()
        if "phethai" in fam_lower or "phetai" in fam_lower or "phetai" in stem_lower:
            family_aliases.update(["TF PHETAI", "TF_PHETAI", "TF PHENTAI", "TF Phethai", "TF Phetai", "TF_Phetai"])
        if "tamaitine" in fam_lower or "tarminetine" in fam_lower or "tarminetine" in stem_lower or "tamaitine" in stem_lower:
            family_aliases.update(["Layiji_TarMineTine1", "Layiji TarMineTine1", "Layiji TaMaiTine1", "layiji_TarMineTine1"])
        if "baijam" in fam_lower or "baijam" in stem_lower:
            family_aliases.update(["TH Baijam Bold", "Baijam Bold", "TH Baijam", "Baijam"])
        if "jarakefadhang" in fam_lower or "jarakefadhang" in stem_lower:
            family_aliases.update(["Layiji JaRaKeFadHang v1.0 Regular", "Layiji JaRaKeFadHang", "Layiji JaRaKeFadHangV1", "Layiji JaRaKeFadHang v1.0"])
        if "muffin" in fam_lower or "muffin" in stem_lower:
            family_aliases.update(["FC Muffin", "Fc muffin", "FC Muffin Regular"])
        if "tiger" in fam_lower or "tiger" in stem_lower:
            family_aliases.update(["iannnnn TIGER Black", "iannnnn-TIGER-Black", "iannnnn TIGER", "iannnnn-TIGER-Regular"])

        for fam_name in family_aliases:
            variant_key = f"{fam_name}_{entry.weight}_{entry.css_style}"
            if variant_key in seen_variants:
                continue
            seen_variants.add(variant_key)

            rule = f"""@font-face {{
  font-family: '{fam_name}';
  font-weight: {entry.weight};
  font-style: {entry.css_style};
  src: url('{url_path}') format('{font_format}');
  font-display: swap;
}}"""
            css_rules.append(rule)

    css_content = "\n\n".join(css_rules)
    return Response(
        content=css_content,
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=3600"}
    )

@router.get("/fonts/file/{variant_id}")
def get_font_file(variant_id: str):
    """
    Streams the requested font binary file with appropriate MIME type and caching headers.
    """
    entry = font_registry.get_variant_by_id(variant_id)
    if not entry or not entry.file_path or not entry.file_path.exists():
        raise HTTPException(status_code=404, detail="Font file not found")

    ext = entry.file_path.suffix.lower()
    media_type_map = {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".ttc": "font/collection",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(entry.file_path),
        media_type=media_type,
        filename=entry.file_path.name,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Access-Control-Allow-Origin": "*",
        }
    )

@router.post("/fonts/upload")
async def upload_font(file: UploadFile = File(...)):
    """
    Uploads a custom font (.ttf, .otf, .woff2) to data/fonts/ and registers it into FontRegistry immediately.
    """
    filename = file.filename or "uploaded_font.ttf"
    ext = Path(filename).suffix.lower()
    if ext not in (".ttf", ".otf", ".woff2", ".ttc"):
        raise HTTPException(status_code=400, detail="Only .ttf, .otf, .woff2, and .ttc font files are supported.")

    data_fonts_dir = Path("data/fonts")
    data_fonts_dir.mkdir(parents=True, exist_ok=True)
    
    target_path = data_fonts_dir / filename
    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        registered_entries = font_registry.register_font_file(target_path, category="custom")
        if not registered_entries:
            raise HTTPException(status_code=400, detail="Failed to parse font headers from uploaded file.")
        
        family_name = registered_entries[0].family
        return {
            "success": True,
            "message": f"Font '{family_name}' uploaded and registered successfully.",
            "family": family_name,
            "variants_count": len(registered_entries)
        }
    except Exception as e:
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to process font file: {str(e)}")


@router.post("/fonts/rescan")
@router.get("/fonts/rescan")
def rescan_fonts():
    """
    Rescans Windows system font folders, custom data/fonts/, and project fonts dynamically.
    Returns the refreshed list of available font families and variants.
    """
    families = font_registry.rescan()
    details = {}
    for entry in font_registry.registry.values():
        if entry.family not in details:
            details[entry.family] = []
        if entry.style not in details[entry.family]:
            details[entry.family].append(entry.style)
    
    return {
        "success": True,
        "fonts": families,
        "details": {fam: sorted(styles) for fam, styles in details.items()},
        "families": font_registry.get_family_details(),
        "count": len(families)
    }


ESSENTIAL_FONTS = [
    {"name": "Baijam", "match_keys": ["baijam", "th baijam"]},
    {"name": "TF PHETAI", "match_keys": ["phetai", "phentai", "phethai", "tf phetai", "tf phentai"]},
    {"name": "IrisUPC", "match_keys": ["irisupc", "irispc", "iris upc"]},
]

@router.get("/fonts/check-essential")
def check_essential_fonts():
    """Checks presence of core comic fonts in the system or data/fonts/."""
    available_families = [f.lower() for f in font_registry.families.keys()]
    available_aliases = [a.lower() for a in font_registry.aliases.keys()]
    all_known = set(available_families + available_aliases)
    
    missing = []
    installed = []
    
    for font_spec in ESSENTIAL_FONTS:
        name = font_spec["name"]
        keys = font_spec["match_keys"]
        found = any(any(k in entry for k in keys) for entry in all_known)
        if found:
            installed.append(name)
        else:
            missing.append(name)
            
    return {
        "all_present": len(missing) == 0,
        "missing_fonts": missing,
        "installed_fonts": installed,
    }


@router.post("/fonts/download-essential-bundle")
def download_essential_fonts_bundle():
    """
    Downloads essential manga fonts bundle from Central Server or Cloudflare CDN
    and extracts them directly to data/fonts/, then rescans registry.
    """
    import urllib.request
    import zipfile
    import io
    
    data_fonts_dir = Path("data/fonts")
    data_fonts_dir.mkdir(parents=True, exist_ok=True)
    
    central_host = os.environ.get("HOUMI_CENTRAL_SERVER_URL", "https://houmi.click").rstrip("/")
    bundle_url = f"{central_host}/api/fonts/download-essential-bundle"
    
    try:
        req = urllib.request.Request(
            bundle_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            zip_bytes = response.read()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                z.extractall(data_fonts_dir)
                
        font_registry.rescan()
        return {
            "success": True,
            "message": "ดาวน์โหลดและติดตั้งฟอนต์มาตรฐานเรียบร้อยแล้ว!",
            "fonts": font_registry.list_families()
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"ไม่สามารถดาวน์โหลดชุดฟอนต์จากเซิร์ฟเวอร์ได้: {str(e)}"
        }

@router.get("/fonts/download-essential-bundle")
def serve_essential_fonts_bundle():
    """Serves the essential manga fonts bundle zip file."""
    for loc in [
        Path("data/fonts_bundle.zip"),
        Path("data/patches/fonts_bundle.zip"),
        Path("backend/data/fonts_bundle.zip"),
        Path("data/fonts/essential_fonts.zip"),
    ]:
        if loc.exists():
            return FileResponse(
                path=str(loc),
                filename="essential_fonts_bundle.zip",
                media_type="application/zip",
            )
    raise HTTPException(status_code=404, detail="Font bundle archive not found on server")



