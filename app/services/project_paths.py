"""Canonical paths for portable Houmi project assets and exports."""

from __future__ import annotations

from pathlib import Path

from app.config import PROJECTS_DIR


def _existing_local_folder(project) -> Path | None:
    settings = getattr(project, "settings", None) or {}
    raw = settings.get("local_folder")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.exists() and path.is_dir() else None


def uses_external_workspace(project) -> bool:
    return _existing_local_folder(project) is not None


def project_workspace_dir(project) -> Path:
    """Visible project folder for folder-backed projects, internal storage otherwise."""
    local = _existing_local_folder(project)
    root = local if local is not None else PROJECTS_DIR / str(project.id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def page_asset_key(page) -> str:
    """Stable human-facing key based on the actual page number.

    Source filenames are not authoritative: imported chapters often contain
    arbitrary names, duplicate stems, or cover labels.  All generated assets
    therefore follow the page order shown in Houmi (01, 02, ...).
    """
    page_number = max(0, int(getattr(page, "page_number", 0) or 0))
    return f"{page_number:02d}"


def page_asset_dir(page, category: str) -> Path:
    """Category directory; folder-backed projects use flat, page-numbered files."""
    project = page.project
    local = _existing_local_folder(project)
    if local is None:
        root = Path(page.source_image_path).parent / category
    else:
        root = local / category
    root.mkdir(parents=True, exist_ok=True)
    return root


def mask_asset_path(page, logical_name: str) -> Path:
    directory = page_asset_dir(page, "masks")
    if not uses_external_workspace(page.project):
        return directory / logical_name
    key = page_asset_key(page)
    if logical_name == "effective_mask.png":
        return directory / f"{key}_mask.png"
    if logical_name == "manual_mask.png":
        return directory / f"{key}_manual_mask.png"
    return directory / f"{key}_{logical_name}"


def inpainted_asset_path(page) -> Path:
    directory = page_asset_dir(page, "clean")
    name = f"{page_asset_key(page)}_inpaint.png" if uses_external_workspace(page.project) else "inpainted.png"
    return directory / name


def inpaint_preview_asset_path(page) -> Path:
    directory = page_asset_dir(page, "previews")
    name = f"{page_asset_key(page)}_inpaint_preview.jpg" if uses_external_workspace(page.project) else "preview_inpainted.jpg"
    return directory / name


def rendered_asset_path(page) -> Path:
    directory = page_asset_dir(page, "rendered")
    name = f"{page_asset_key(page)}.png" if uses_external_workspace(page.project) else "rendered.png"
    return directory / name


def preview_asset_path(page) -> Path:
    directory = page_asset_dir(page, "previews")
    name = f"{page_asset_key(page)}_preview.jpg" if uses_external_workspace(page.project) else "preview.jpg"
    return directory / name


def thumbnail_asset_path(page) -> Path:
    directory = page_asset_dir(page, "previews")
    name = f"{page_asset_key(page)}_thumbnail.jpg" if uses_external_workspace(page.project) else "thumbnail.jpg"
    return directory / name


def project_export_path(project, filename: str) -> Path:
    return project_workspace_dir(project) / filename


def save_project_json(project) -> Path:
    """Serialize project metadata, pages, and text blocks to project.json inside the project folder."""
    import json
    work_dir = project_workspace_dir(project)
    json_path = work_dir / "project.json"

    pages_data = []
    for page in getattr(project, "pages", []):
        blocks_data = []
        for block in getattr(page, "text_blocks", []):
            blocks_data.append({
                "id": str(block.id),
                "x": float(block.x),
                "y": float(block.y),
                "width": float(block.width),
                "height": float(block.height),
                "rotation_deg": float(block.rotation_deg or 0.0),
                "source_text": block.source_text or "",
                "translation": block.translation or "",
                "text_direction": block.text_direction or "horizontal",
                "font_family": block.font_family or "",
                "font_size": float(block.font_size or 14.0),
                "color_hex": block.color_hex or "#000000",
                "extra_metadata": block.extra_metadata or {},
            })

        pages_data.append({
            "id": str(page.id),
            "page_number": int(page.page_number),
            "source_image_path": str(page.source_image_path or ""),
            "width": int(page.width or 0),
            "height": int(page.height or 0),
            "status": str(page.status or "raw"),
            "text_blocks": blocks_data,
        })

    data = {
        "id": str(project.id),
        "name": str(project.name or ""),
        "source_language": str(project.source_language or ""),
        "target_language": str(project.target_language or ""),
        "settings": project.settings or {},
        "pages": pages_data,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return json_path


def load_project_json(project_dir: Path) -> dict | None:
    """Load project.json from a project directory if it exists."""
    import json
    json_path = Path(project_dir) / "project.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
