import os
import sys
import json
import shutil
import zipfile
from pathlib import Path

# Correct project root directory: e:\houmi (3 levels up from e:\houmi\backend\scripts\build_patch.py)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
BACKEND_APP = ROOT_DIR / "backend" / "app"

# Add virtualenv site-packages to sys.path to resolve rapidocr_onnxruntime if needed
venv_site = ROOT_DIR / "backend" / ".venv" / "Lib" / "site-packages"
if venv_site.exists() and str(venv_site) not in sys.path:
    sys.path.insert(0, str(venv_site))

# Output patch destinations
OUTPUT_DIR = ROOT_DIR / "backend" / "data" / "patches"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ZIP_DEST = OUTPUT_DIR / "latest_patch.zip"
ROOT_ZIP = ROOT_DIR / "houmi_latest_patch.zip"

print(f"Project Root: {ROOT_DIR}")
print(f"Frontend Directory: {FRONTEND_DIR.name}")

# 0. Auto-build frontend dist if frontend/src has updates
frontend_src = FRONTEND_DIR / "src"
dist_html = FRONTEND_DIST / "index.html"
needs_build = False

if not dist_html.exists():
    needs_build = True
else:
    dist_mtime = dist_html.stat().st_mtime
    for root, _, files in os.walk(frontend_src):
        for f in files:
            if (Path(root) / f).stat().st_mtime > dist_mtime:
                needs_build = True
                break
        if needs_build:
            break

if needs_build:
    print(f"[0/3] Auto-building frontend dist via Vite ({FRONTEND_DIR.name}/src has updates)...")
    import subprocess
    cmd = ["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"]
    subprocess.run(cmd, cwd=str(FRONTEND_DIR), check=True)
    print("✓ Frontend auto-build complete.")

print("[1/3] Packaging latest frontend dist & backend code...")

entries_count = 0

with zipfile.ZipFile(ZIP_DEST, "w", zipfile.ZIP_DEFLATED) as zip_f:
    # 1. Add compiled frontend dist files
    #    In PyInstaller _internal: frontend/dist/...
    #    In dev repo:              frontend/dist/...
    if FRONTEND_DIST.exists():
        for root, _, files in os.walk(FRONTEND_DIST):
            for file in files:
                file_path = Path(root) / file
                arcname = Path("frontend") / "dist" / file_path.relative_to(FRONTEND_DIST)
                zip_f.write(file_path, arcname)
                entries_count += 1
    else:
        print(f"⚠️ Warning: Frontend dist path not found at {FRONTEND_DIST}")

    # 2. Add backend app Python files
    #    CRITICAL: In PyInstaller frozen mode, sys._MEIPASS == _internal/
    #    and Python imports from "app.services.ocr" → _internal/app/services/ocr.py
    #    So the zip arcname MUST be "app/..." (no "backend/" prefix).
    #
    #    In dev mode, updater.py extracts to the repo root (e:\houmi),
    #    so we also need entries with "backend/app/..." prefix.
    if BACKEND_APP.exists():
        for root, _, files in os.walk(BACKEND_APP):
            if "__pycache__" in root:
                continue
            for file in files:
                if file.endswith(".pyc"):
                    continue
                file_path = Path(root) / file
                rel = file_path.relative_to(BACKEND_APP)

                # Path for PyInstaller frozen mode: app/services/ocr.py
                arcname_frozen = Path("app") / rel
                zip_f.write(file_path, arcname_frozen)
                entries_count += 1

                # Path for dev mode: backend/app/services/ocr.py
                arcname_dev = Path("backend") / "app" / rel
                zip_f.write(file_path, arcname_dev)
                entries_count += 1
    else:
        print(f"⚠️ Warning: Backend app path not found at {BACKEND_APP}")

    # 3. Add rapidocr_onnxruntime package assets if requested
    include_ocr = os.environ.get("INCLUDE_OCR_MODELS", "0") == "1"
    if include_ocr:
        try:
            import rapidocr_onnxruntime
            rapid_pkg_dir = Path(rapidocr_onnxruntime.__file__).parent
            if rapid_pkg_dir.exists():
                print(f"[3/5] Packaging rapidocr_onnxruntime models from {rapid_pkg_dir}...")
                for root, _, files in os.walk(rapid_pkg_dir):
                    if "__pycache__" in root:
                        continue
                    for file in files:
                        if file.endswith(".pyc"):
                            continue
                        file_path = Path(root) / file
                        rel = file_path.relative_to(rapid_pkg_dir)
                        arcname = Path("rapidocr_onnxruntime") / rel
                        zip_f.write(file_path, arcname)
        except Exception as e_rapid:
            print(f"⚠️ Warning: Could not package rapidocr_onnxruntime assets: {e_rapid}")

    # 4. Add backend ocr_server scripts
    OCR_SERVER_DIR = ROOT_DIR / "backend" / "ocr_server"
    if OCR_SERVER_DIR.exists():
        print(f"[4/6] Packaging ocr_server from {OCR_SERVER_DIR}...")
        for root, _, files in os.walk(OCR_SERVER_DIR):
            if any(skip in root for skip in ("__pycache__", "venv", "logs", "uploaded", "tests")):
                continue
            for file in files:
                if file.endswith((".pyc", ".log")) or file.startswith(("test_", "debug_")):
                    continue
                file_path = Path(root) / file
                rel = file_path.relative_to(OCR_SERVER_DIR)
                arcname = Path("backend") / "ocr_server" / rel
                zip_f.write(file_path, arcname)
                entries_count += 1

    # 4.1 Add backend inpaint_server scripts
    INPAINT_SERVER_DIR = ROOT_DIR / "backend" / "inpaint_server"
    if INPAINT_SERVER_DIR.exists():
        print(f"[4.1/6] Packaging inpaint_server from {INPAINT_SERVER_DIR}...")
        for root, _, files in os.walk(INPAINT_SERVER_DIR):
            if any(skip in root for skip in ("__pycache__", "venv", "logs", "tests")):
                continue
            for file in files:
                if file.endswith((".pyc", ".log")) or file.startswith(("test_", "debug_")):
                    continue
                file_path = Path(root) / file
                rel = file_path.relative_to(INPAINT_SERVER_DIR)
                arcname = Path("backend") / "inpaint_server" / rel
                zip_f.write(file_path, arcname)
                entries_count += 1

    # 5. Add language-specific OCR models if requested
    if include_ocr:
        OCR_MODELS_DIR = ROOT_DIR / "backend" / "ocr_models"
        if OCR_MODELS_DIR.exists():
            model_count = 0
            print(f"[5/5] Packaging language OCR models from {OCR_MODELS_DIR}...")
            for root, _, files in os.walk(OCR_MODELS_DIR):
                for file in files:
                    if file.endswith((".onnx", ".txt")):
                        file_path = Path(root) / file
                        rel = file_path.relative_to(OCR_MODELS_DIR)

                        arcname_frozen = Path("ocr_models") / rel
                        zip_f.write(file_path, arcname_frozen)
                        entries_count += 1
                        model_count += 1

                        arcname_dev = Path("backend") / "ocr_models" / rel
                        zip_f.write(file_path, arcname_dev)
                        entries_count += 1
            print(f"    → Packaged {model_count} model files")

    # 5.1 Add AI models (Manga UNet++, LaMa, SAM, YOLO) if requested
    include_ai_models = os.environ.get("INCLUDE_AI_MODELS", "0") == "1"
    if include_ai_models:
        MODELS_DIR = ROOT_DIR / "backend" / "models"
        if MODELS_DIR.exists():
            model_cnt = 0
            print(f"[5.1/6] Packaging AI models from {MODELS_DIR}...")
            for root, _, files in os.walk(MODELS_DIR):
                for file in files:
                    if file.endswith((".onnx", ".pth", ".json", ".pt")):
                        file_path = Path(root) / file
                        rel = file_path.relative_to(MODELS_DIR)

                        arcname_frozen = Path("models") / rel
                        zip_f.write(file_path, arcname_frozen)
                        entries_count += 1
                        model_cnt += 1

                        arcname_dev = Path("backend") / "models" / rel
                        zip_f.write(file_path, arcname_dev)
                        entries_count += 1
            print(f"    → Packaged {model_cnt} AI model files")

    # 6. Add houmi-psd-cli.exe & manga-psd-cli.exe binaries
    CLI_BIN = ROOT_DIR / "houmi-psd-cli" / "target" / "release" / "houmi-psd-cli.exe"
    if not CLI_BIN.exists():
        CLI_BIN = ROOT_DIR / "manga-psd-cli" / "target" / "release" / "manga-psd-cli.exe"
    if CLI_BIN.exists():
        print(f"[6/6] Packaging PSD CLI from {CLI_BIN}...")
        zip_f.write(CLI_BIN, Path("bin") / "houmi-psd-cli.exe")
        zip_f.write(CLI_BIN, Path("bin") / "manga-psd-cli.exe")
        entries_count += 2
    else:
        print(f"⚠️ Warning: PSD CLI binary not found at {CLI_BIN}")

    # 7. Write and package patch_manifest.json
    patch_version = "1.1.0"
    patch_notes = "v1.1.0 Stable Rollback: คืนค่าเวอร์ชันเสถียร (Stable Release) ปรับปรุงความเสถียรและประสิทธิภาพระบบ 100%"
    patch_manifest_data = json.dumps({"version": patch_version, "notes": patch_notes}, indent=2)
    zip_f.writestr("data/patches/current/patch_manifest.json", patch_manifest_data)
    zip_f.writestr("backend/data/patches/current/patch_manifest.json", patch_manifest_data)
    entries_count += 2

if entries_count == 0:
    raise RuntimeError("❌ BUILD FAILED: No files were added to the patch ZIP archive! Check paths.")

file_size_mb = round(os.path.getsize(ZIP_DEST) / 1024 / 1024, 2)

# Copy zip to all standard patch directories and root
extra_destinations = [
    ROOT_ZIP,
    ROOT_DIR / "backend" / "houmi_latest_patch.zip",
    ROOT_DIR / "data" / "patches" / "latest_patch.zip",
    ROOT_DIR / "release" / "patches" / "latest_patch.zip",
]
for dest in extra_destinations:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ZIP_DEST, dest)

# Update update_manifest.json in all relevant locations
manifest_data = {
    "latest_version": patch_version,
    "target_username": "",
    "update_available": True,
    "patch_notes": patch_notes,
    "download_size_mb": file_size_mb,
    "download_url": "/api/system/download-update"
}

for m_path in [
    ROOT_DIR / "data" / "update_manifest.json",
    ROOT_DIR / "backend" / "data" / "update_manifest.json",
    ROOT_DIR / "update_manifest.json",
]:
    m_path.parent.mkdir(parents=True, exist_ok=True)
    with open(m_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

print("=" * 60)
print(f"✅ Patch Zip created successfully! (Version: v{patch_version})")
print(f"📦 Total files packaged: {entries_count} files ({file_size_mb} MB)")
print(f"📍 Main Patch: {ZIP_DEST}")
print(f"📍 Desktop Root Zip: {ROOT_ZIP}")
print(f"📍 Data Patches Zip: {ROOT_DIR / 'data' / 'patches' / 'latest_patch.zip'}")
print("=" * 60)
