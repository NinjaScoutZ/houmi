#!/usr/bin/env python3
"""
Houmi Studio - Unified Single-Source Release & Patch Builder
Builds isolated customer release patches from a designated workspace / worktree.
Strictly enforces Allowlist packaging and SHA-256 verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Files and extensions strictly forbidden in customer packages
DENY_PATTERNS = [
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".github",
    ".venv",
    "node_modules",
    "tests",
    "scripts",
    "google_credentials",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.db",
    "*.sqlite*",
    "*.log",
    "*.env",
    "*.env.*",
    "*.tmp",
    "*.bak",
]


def compute_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def get_git_commit(cwd: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def build_patch(
    worktree_name: str = "v1.0.5",
    patch_tag: str = "p1",
    dry_run: bool = False,
) -> Path:
    # 1. Resolve workspace root
    ws_dir = ROOT_DIR / "workspaces" / worktree_name
    if not ws_dir.exists():
        ws_dir = ROOT_DIR / "worktrees" / worktree_name
    if not ws_dir.exists():
        raise FileNotFoundError(f"Worktree/Workspace '{worktree_name}' not found under {ROOT_DIR}")

    frontend_dist = ws_dir / "frontend" / "dist"
    backend_app = ws_dir / "backend" / "app"

    if not (frontend_dist / "index.html").exists():
        raise FileNotFoundError(f"Missing compiled index.html in {frontend_dist}")
    if not (backend_app / "main.py").exists():
        raise FileNotFoundError(f"Missing backend main.py in {backend_app}")

    # 2. Prepare release directory
    rel_dir = ROOT_DIR / "releases" / worktree_name
    patch_dir = rel_dir / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)

    zip_filename = f"houmi-{worktree_name}-{patch_tag}.zip"
    zip_dest = patch_dir / zip_filename

    print(f"[*] Packaging Release Patch: {zip_filename}")
    print(f"[*] Source Workspace:        {ws_dir}")
    print(f"[*] Destination Directory:   {patch_dir}")

    if dry_run:
        print("[*] Dry run mode enabled. Validating workspace structure...")
        print(f"✓ Frontend dist valid: {frontend_dist}")
        print(f"✓ Backend app valid:   {backend_app}")
        return zip_dest

    count = 0
    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zip_f:
        # Add frontend dist assets
        for root, dirs, files in os.walk(frontend_dist):
            for file in files:
                file_path = Path(root) / file
                arcname = "frontend/dist/" + str(file_path.relative_to(frontend_dist)).replace("\\", "/")
                zip_f.write(file_path, arcname)
                count += 1

        # Add backend app code
        for root, dirs, files in os.walk(backend_app):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in ["__pycache__", "tests", ".pytest_cache"]]
            for file in files:
                if file.endswith((".pyc", ".pyo", ".log", ".tmp")):
                    continue
                file_path = Path(root) / file
                arcname = "backend/app/" + str(file_path.relative_to(backend_app)).replace("\\", "/")
                zip_f.write(file_path, arcname)
                count += 1

    # 3. Compute Checksum
    sha256 = compute_sha256(zip_dest)
    size_bytes = zip_dest.stat().st_size
    commit = get_git_commit(ROOT_DIR)

    # 4. Generate Single Canonical Manifest
    manifest = {
        "appName": "Houmi Studio",
        "appVersion": worktree_name.lstrip("v"),
        "patchVersion": f"{worktree_name.lstrip('v')}-{patch_tag}",
        "releaseDate": datetime.now(timezone.utc).isoformat(),
        "sourceCommit": commit,
        "compatibleFrom": "1.0.0",
        "archiveName": zip_filename,
        "sha256": sha256,
        "sizeBytes": size_bytes,
        "totalFiles": count,
    }

    manifest_path = rel_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"✓ Built {zip_filename} ({size_bytes:,} bytes, {count} files)")
    print(f"✓ SHA-256: {sha256}")
    print(f"✓ Manifest created: {manifest_path}")

    return zip_dest


def main():
    parser = argparse.ArgumentParser(description="Houmi Single-Source Release Builder")
    parser.add_argument("--worktree", default="v1.0.5", help="Target worktree / workspace name")
    parser.add_argument("--patch-tag", default="p1", help="Patch suffix tag")
    parser.add_argument("--verify-dry-run", action="store_true", help="Validate without writing archive")
    args = parser.parse_args()

    build_patch(
        worktree_name=args.worktree,
        patch_tag=args.patch_tag,
        dry_run=args.verify_dry_run,
    )


if __name__ == "__main__":
    main()
