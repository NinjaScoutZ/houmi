"""
Houmi Studio - Release & Patch Manager Service
Manages version archives (v1.0.0, v1.0.1, v1.0.4...), active release promotion,
hot delta patch building, and rollback operations.
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import APP_DIR, BASE_DIR, DATA_DIR

ROOT_DIR = APP_DIR

logger = logging.getLogger("houmi-patch-manager")

RELEASES_DIR = DATA_DIR / "releases"
RELEASES_DIR.mkdir(parents=True, exist_ok=True)

PATCHES_DIR = DATA_DIR / "patches"
PATCHES_DIR.mkdir(parents=True, exist_ok=True)

LATEST_PATCH_ZIP = PATCHES_DIR / "latest_patch.zip"
UPDATE_MANIFEST_PATH = DATA_DIR / "update_manifest.json"


def _normalize_version_tag(version: str) -> str:
    """Normalize '1.0.4' or 'v1.0.4' to 'v1.0.4'."""
    v = version.strip()
    if not v.startswith("v") and not v.startswith("V"):
        return f"v{v}"
    return f"v{v[1:]}"


def _get_active_version() -> str:
    """Read the currently active broadcast version from update_manifest.json."""
    if UPDATE_MANIFEST_PATH.exists():
        try:
            with open(UPDATE_MANIFEST_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                return str(data.get("latest_version", "1.0.4"))
        except Exception:
            pass
    return "1.0.4"


def list_all_releases() -> List[Dict[str, Any]]:
    """Scan RELEASES_DIR and return a list of all archived versions."""
    active_ver = _get_active_version().lstrip("vV")
    releases: List[Dict[str, Any]] = []

    # Ensure current latest_patch is archived as active if not exists
    if LATEST_PATCH_ZIP.exists():
        cur_tag = f"v{active_ver}"
        cur_dir = RELEASES_DIR / cur_tag
        if not cur_dir.exists():
            cur_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(LATEST_PATCH_ZIP, cur_dir / "patch.zip")
            manifest_content = {
                "version": active_ver,
                "created_at": datetime.utcnow().isoformat(),
                "patch_notes": "v1.0.4 Active Production Release: Dobkle Cloud Hub, Export Studio & Photoshop Controls",
                "size_mb": round(os.path.getsize(LATEST_PATCH_ZIP) / (1024 * 1024), 2),
            }
            with open(cur_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest_content, f, indent=2, ensure_ascii=False)

    # Scan all directories in RELEASES_DIR
    for folder in sorted(RELEASES_DIR.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        tag = folder.name
        ver = tag.lstrip("vV")
        patch_file = folder / "patch.zip"
        manifest_file = folder / "manifest.json"

        notes = "No patch notes provided"
        created_at = datetime.fromtimestamp(folder.stat().st_mtime).isoformat()
        size_mb = round(os.path.getsize(patch_file) / (1024 * 1024), 2) if patch_file.exists() else 0.0

        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8-sig") as mf:
                    mdata = json.load(mf)
                    notes = mdata.get("patch_notes", notes)
                    created_at = mdata.get("created_at", created_at)
                    if "size_mb" in mdata:
                        size_mb = mdata["size_mb"]
            except Exception as e_m:
                logger.warning("Failed to parse manifest for %s: %s", tag, e_m)

        releases.append({
            "version": ver,
            "tag": tag,
            "is_active": ver == active_ver,
            "patch_notes": notes,
            "size_mb": size_mb,
            "created_at": created_at,
            "has_zip": patch_file.exists(),
            "path": str(folder),
        })

    return releases


def set_active_release(version: str, patch_notes: Optional[str] = None) -> Dict[str, Any]:
    """Promote a specific archived version to be the active broadcast version."""
    clean_ver = version.strip().lstrip("vV")
    tag = _normalize_version_tag(version)
    target_dir = RELEASES_DIR / tag
    target_zip = target_dir / "patch.zip"

    if not target_dir.exists() or not target_zip.exists():
        # If not archived, check if latest_patch matches this version
        if not LATEST_PATCH_ZIP.exists():
            raise FileNotFoundError(f"Release version {tag} not found in {RELEASES_DIR}")
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(LATEST_PATCH_ZIP, target_zip)

    # Read notes from release manifest if not provided
    notes = patch_notes
    if not notes:
        manifest_file = target_dir / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8-sig") as mf:
                    mdata = json.load(mf)
                    notes = mdata.get("patch_notes")
            except Exception:
                pass
    if not notes:
        notes = f"Release {tag}: Updated to version {clean_ver}"

    file_size_mb = round(os.path.getsize(target_zip) / (1024 * 1024), 2)

    # Copy release zip to active latest_patch destinations
    shutil.copy(target_zip, LATEST_PATCH_ZIP)
    for dest in [
        ROOT_DIR / "houmi_latest_patch.zip",
        BASE_DIR / "houmi_latest_patch.zip",
        BASE_DIR / "data" / "patches" / "latest_patch.zip",
    ]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy(target_zip, dest)
        except Exception:
            pass

    # Update update_manifest.json
    manifest_data = {
        "latest_version": clean_ver,
        "target_username": "",
        "update_available": True,
        "patch_notes": notes,
        "download_size_mb": file_size_mb,
        "download_url": "/api/system/download-update",
        "updated_at": datetime.utcnow().isoformat(),
    }

    for m_path in [
        UPDATE_MANIFEST_PATH,
        BASE_DIR / "data" / "update_manifest.json",
        ROOT_DIR / "update_manifest.json",
    ]:
        m_path.parent.mkdir(parents=True, exist_ok=True)
        with open(m_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    logger.info("Active release promoted to %s (size: %s MB)", clean_ver, file_size_mb)
    return {
        "ok": True,
        "active_version": clean_ver,
        "tag": tag,
        "patch_notes": notes,
        "download_size_mb": file_size_mb,
    }


def build_and_archive_release(
    version: str,
    patch_notes: str,
    set_active_now: bool = True,
) -> Dict[str, Any]:
    """Package the current frontend & backend code into a new archived version."""
    clean_ver = version.strip().lstrip("vV")
    tag = _normalize_version_tag(version)
    target_dir = RELEASES_DIR / tag
    target_dir.mkdir(parents=True, exist_ok=True)
    target_zip = target_dir / "patch.zip"

    # 1. Ensure frontend is built
    frontend_dir = ROOT_DIR / "frontend"
    frontend_dist = frontend_dir / "dist"
    backend_app = ROOT_DIR / "backend" / "app"

    if not frontend_dist.exists() or not (frontend_dist / "index.html").exists():
        import subprocess
        cmd = ["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"]
        subprocess.run(cmd, cwd=str(frontend_dir), check=True)

    # 2. Package into target_zip
    entries_count = 0
    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zip_f:
        # Frontend dist
        for root, _, files in os.walk(frontend_dist):
            for file in files:
                file_path = Path(root) / file
                arcname = Path("frontend") / "dist" / file_path.relative_to(frontend_dist)
                zip_f.write(file_path, arcname)
                entries_count += 1

        # Backend app
        for root, _, files in os.walk(backend_app):
            if "__pycache__" in root:
                continue
            for file in files:
                if file.endswith(".pyc"):
                    continue
                file_path = Path(root) / file
                rel = file_path.relative_to(backend_app)
                zip_f.write(file_path, Path("app") / rel)
                zip_f.write(file_path, Path("backend") / "app" / rel)
                entries_count += 2

        # Servers
        for srv in ["ocr_server", "inpaint_server"]:
            srv_dir = ROOT_DIR / "backend" / srv
            if srv_dir.exists():
                for root, _, files in os.walk(srv_dir):
                    if any(sk in root for sk in ("__pycache__", "venv", "logs")):
                        continue
                    for file in files:
                        if not file.endswith(".pyc"):
                            fp = Path(root) / file
                            zip_f.write(fp, Path("backend") / srv / fp.relative_to(srv_dir))
                            entries_count += 1

        # CLI binary
        cli_bin = ROOT_DIR / "houmi-psd-cli" / "target" / "release" / "houmi-psd-cli.exe"
        if cli_bin.exists():
            zip_f.write(cli_bin, Path("bin") / "houmi-psd-cli.exe")
            entries_count += 1

        # Patch Manifest
        p_manifest = json.dumps({"version": clean_ver, "notes": patch_notes}, indent=2)
        zip_f.writestr("data/patches/current/patch_manifest.json", p_manifest)
        zip_f.writestr("backend/data/patches/current/patch_manifest.json", p_manifest)

    size_mb = round(os.path.getsize(target_zip) / (1024 * 1024), 2)

    # Save release manifest
    release_manifest = {
        "version": clean_ver,
        "tag": tag,
        "patch_notes": patch_notes,
        "size_mb": size_mb,
        "entries_count": entries_count,
        "created_at": datetime.utcnow().isoformat(),
    }
    with open(target_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(release_manifest, f, indent=2, ensure_ascii=False)

    # If requested, set as active immediately
    if set_active_now:
        set_active_release(clean_ver, patch_notes)

    return {
        "ok": True,
        "version": clean_ver,
        "tag": tag,
        "size_mb": size_mb,
        "entries_count": entries_count,
        "is_active": set_active_now,
    }
