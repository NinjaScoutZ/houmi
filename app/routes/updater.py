import os
import sys
import json
import logging
import shutil
import zipfile
import urllib.request
from pathlib import Path
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse

from app.config import APP_DIR, BASE_DIR, DATA_DIR, RUNTIME_MODE

CENTRAL_HOST = os.environ.get("HOUMI_CENTRAL_SERVER_URL", "https://houmi.click").rstrip("/")

router = APIRouter(tags=["Updater"])
logger = logging.getLogger("houmi-updater")

CURRENT_VERSION = "2.0.0"
UPDATE_MANIFEST_PATH = DATA_DIR / "update_manifest.json"
PATCHES_DIR = DATA_DIR / "patches"
PATCHES_DIR.mkdir(parents=True, exist_ok=True)
PATCH_MANIFEST_PATH = DATA_DIR / "patches" / "current" / "patch_manifest.json"

CHANGELOG_HISTORY = [
    {
        "version": "1.0.1",
        "date": "2026-08-18",
        "title": "v1.0.1 Release - Smart Stitch Toolbar Tool, ImageTrans Mask Engine & Pipeline Stability",
        "features": [
            "✂️ Smart Stitch & Image Splitter: เมนูตัดแบ่งและปรับขนาดภาพเว็บตูนขนาดยาวอัตโนมัติในเมนู File พร้อมระบบสแกนความยาว ตรวจจับร่องภาพขาว/ดำ และสำรองไฟล์เดิม 100%",
            "🎭 ImageTrans Mask Engine: เพิ่มตัวเลือกโมเดล Mask แบบ ImageTrans Binarization & Connected Components ในหน้าตั้งค่าโปรเจกต์และระบบ",
            "🛡️ Batch Pipeline & Single Block OCR Stability: แก้ไขปัญหา Timeout Toast รัวใน Batch Pipeline และคงสถานะการเลือกบล็อกเดิมไว้ ไม่หลุดหายหลัง OCR เสร็จ",
            "🎈 Smart Balloon V15 Zero Distortion: เพิ่มความแม่นยำในการแยกแยะบอลลูนบทสนทนาและคำนวณพื้นที่จัดวางฟอนต์ Safe Inset สมบูรณ์แบบ",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026-08-16",
        "title": "v1.0.0 Official Release - Complete SOTA Manga/Webtoon Translation & Inpainting Suite",
        "features": [
            "🧲 Magnetic Line Mask Engine: เชื่อมช่องว่างระหว่างคำในบรรทัดเดียวกันอัตโนมัติ ลบเต็มบรรทัดไม่แหว่งกลาง ป้องกันขอบบอลลูน 100%",
            "🔍 High-Range Mask Expansion Kernel: ขยายขีดจำกัด Dilation Kernel ถึง 56px ทั่วทั้งระบบ ครอบคลุมฟอนต์และขอบหมึกฟุ้งทุกขนาด",
            "🧠 Smart Phonetic Font Aliasing & Rescan: ระบบจับคู่ชื่อฟอนต์คอมมิคไทยที่สะกดต่างกันอัตโนมัติ (TF PHETAI <-> TF Phethai, Layiji) พร้อมปุ่มรีเฟรช Hot-Reload",
            "🧼 SOTA AnimeMangaInpainting Pipeline: LaMa-Manga ONNX (198MB) เทรนด้วยการ์ตูนกว่า 300,000 ภาพ คมชัดไร้รอยต่อทั้งมังงะขาวดำและเว็บตูนสี",
            "🎈 Adaptive Smart Balloon & Boundary Clamping: ตัดแบ่งบอลลูนติดกันด้วย Natural Contour & Waist Min-Cut ป้องกันขอบตัวอักษรและเส้นบอลลูนหลุด",
            "🎨 Photoshop SOTA Roundtrip: ส่งออก PSD Paragraph Box Text แท้ รองรับ Stroke/Glow/Shadow และ Multi-style layer ครบถ้วน",
        ],
    },
    {
        "version": "0.4.6",
        "date": "2026-08-13",
        "title": "v0.4.6 Release - Project-Wide AI Font Judge & Windows CLI Prompt Length Fix",
        "features": [
            "Project-Wide AI Font Judge: รวมตัดสินสไตล์ฟอนต์ทั้งโปรเจกต์ (100+ บล็อก) ใน 1 คำขอเดียว เร็วขึ้น 20-50 เท่า",
            "Windows CLI Command Length Fix: ใช้ระบบ Temporary Prompt File (@path) แก้ไขปัญหาความยาวบรรทัดคำสั่งเกินบน Windows 100%",
            "Async Mask Reclean Preview Fix: เพิ่มระบบดักจับ WebSocket mask_progress อัปเดตภาพ Clean ล่าสุดหลังลบข้อความเสร็จสมบูรณ์",
        ],
    },
    {
        "version": "0.4.5",
        "date": "2026-08-13",
        "title": "v0.4.5 Release - Dual-Slash (//) TXT Translation File Import Support",
        "features": [
            "📝 Dual // TXT Format Support - Full support for importing paired // English/Source & // Thai/Translation text files",
            "🔍 Smart Language & Block Pairing - Automatically matches double slash source lines with target language translation lines"
        ]
    },
    {
        "version": "0.4.4",
        "date": "2026-08-13",
        "title": "v0.4.4 Maintenance Release - Faux Style Resolution, Auto Leading Parity & UI Font Presets",
        "features": [
            "🔤 Font Registry & Faux Style Alignment - Fixed TF Phethai faux italic resolution and template font style mapping",
            "📏 Photoshop Auto Leading Parity - Set default Leading ratio to 1.20 (120% Photoshop Auto)",
            "🎛️ UI Font Style Picker Fixes - Case-insensitive font style selection and normalized dropdown values",
            "💾 SQLite Concurrency & Lock Protections - Optimized busy timeouts and removed write-locks on GET requests"
        ]
    },
    {
        "version": "0.4.3",
        "date": "2026-08-12",
        "title": "v0.4.3 Major Release - Automated Photoshop Batch Launch, Korean OCR Default & Project Pipeline Scope",
        "features": [
            "🚀 Automated Photoshop Batch Launch - Run 100% native Photoshop ExtendScript (JSX) for entire projects with automatic PSD creation & saving",
            "🇰🇷 Korean Default OCR Engine - Default OCR backend set to PP-OCRv5 with Korean (ko) source language",
            "⚡ Whole Project Pipeline Scope - Pipeline Controls panel now defaults to processing the entire project",
            "🔄 Reading Order Sort Button - Dedicated 1-Click Sort Reading Order button in Sub-Toolbar and Pipeline Stage 3",
            "🔤 ImageTrans ExtendScript Clean Line Wrapping - Auto line wrapping and zero-width character filtering for Thai & CJK typography"
        ]
    },
    {
        "version": "0.4.2",
        "date": "2026-08-11",
        "title": "v0.4.2 Hotfix Release - Resolved PSD export text style italic bug",
        "features": [
            "Fixed PSD export text style italic bug for thought template and database italic flags"
        ]
    },
    {
        "version": "0.4.1",
        "date": "2026-08-11",
        "title": "v0.4.1 Release - Font & Typesetting Spec Improvements",
        "features": [
            "Enhanced font resolution and PostScript name mapping"
        ]
    },
    {
        "version": "0.4.0",
        "date": "2026-08-11",
        "title": "v0.4.0 Release - Photoshop Text Engine Modes & Stroke Outlines",
        "features": [
            "Photoshop Anti-Aliasing (Sharp default), Layer Stroke & Outline presets, Paragraph vs Point Text Engine Mode selector"
        ]
    },
    {
        "version": "0.1.7",
        "date": "2026-08-10",
        "title": "v0.1.7 Major Release - Smart Balloon Contour Engine & Live Mini UI Customizer",
        "features": [
            "🎈 Smart Balloon Contour Engine - Full U-Net & OpenCV Pixel Mask Segmentation for organic speech bubbles",
            "🎯 Optical Centroid Alignment - Euclidean Distance Transform (EDT) positioning text at true visual center (C_opt)",
            "📏 Volume Density Font Fitting - Auto-scales Thai font size (34px-44px) filling 65%-75% of balloon interior",
            "⚙️ Live Mini UI Customizer & Quick Stock Outlines - Real-time Stroke Width slider (0-30px), Color Picker, Swatches, & Glow Radius/Color Effects",
            "🛡️ ONNX DirectML Fallback Safety - Automatic CPU session fallback preventing DirectML MatMul errors on dynamic crops",
            "⚡ 1-Click Project Upgrade API - Endpoint /api/projects/{project_id}/smart-balloon/recompute to batch convert legacy projects"
        ]
    },
    {
        "version": "0.1.6",
        "date": "2026-08-10",
        "title": "v0.1.6 Hotfix - User Session Reset & Auto Update Patch",
        "features": [
            "🔐 Security Hotfix - Cleared default developer admin session state on client startup",
            "👤 User Role Reset - Switched local client identity to clean user session",
            "🚀 Auto-Patch Broadcast - In-App 1-Click Update Popup for all active client users"
        ]
    },
    {
        "version": "0.1.5",
        "date": "2026-08-08",
        "title": "v0.1.5 Auto-Patch & RapidOCR ONNX Patch Release",
        "features": [
            "⚡ RapidOCR ONNX Engine - DirectML GPU (AMD/Intel/Nvidia) & CUDA Support",
            "🛠️ Auto Config Recovery - Auto-creates rapid_config.yaml if missing in frozen environment",
            "🔄 In-App Auto Update Modal - Auto pops up on app open with 1-click update button"
        ]
    },
    {
        "version": "0.1.4",
        "date": "2026-08-08",
        "title": "v0.1.4 Major Architecture & Hardware Acceleration Release",
        "features": [
            "⚡ RapidOCR ONNX Engine - DirectML GPU (AMD/Intel/Nvidia) & CUDA Support",
            "🛠️ Unicode Safe OpenCV Path - Thai folder name support (E:\\แอป\\)",
            "🖥️ PyInstaller Windows Native Desktop Window pythonnet fix",
            "🔄 In-App Delta Patching - Auto dynamic patch updates without downloading 3GB full installer"
        ]
    },
    {
        "version": "0.1.3",
        "date": "2026-08-06",
        "title": "v0.1.3 UI & Pipeline Rework",
        "features": [
            "Modular Pipeline Controls Panel",
            "Fast Auto Font Size Calculation",
            "Manga UNet++ Mask Generator"
        ]
    }
]


def parse_version_tuple(ver_str: str) -> tuple:
    import re
    cleaned = re.sub(r'^[vV]', '', str(ver_str or '')).split('-')[0].strip()
    parts = []
    for p in cleaned.split('.'):
        try:
            parts.append(int(re.sub(r'\D', '', p)))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

_FROZEN = getattr(sys, "frozen", False)
IS_DEV_ENV = not _FROZEN or os.environ.get("HOUMI_DISABLE_AUTO_UPDATE", "1") == "1" or RUNTIME_MODE == "dev"

def is_newer_version(remote_ver: str, current_ver: str) -> bool:
    return parse_version_tuple(remote_ver) > parse_version_tuple(current_ver)

def get_current_version() -> str:
    """Return the active software version, checking installed patches first."""
    if IS_DEV_ENV:
        return "Dev 1.0.1"
    if PATCH_MANIFEST_PATH.exists():
        try:
            with open(PATCH_MANIFEST_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                return data.get("version", CURRENT_VERSION)
        except Exception:
            pass
    return CURRENT_VERSION


def check_for_update(current_version: str | None = None) -> dict:
    current = current_version or get_current_version()

    # 0. If running on local development machine, permanently disable auto-updates & remote patch fetching!
    if IS_DEV_ENV and RUNTIME_MODE != "host":
        return {
            "current_version": "Dev 1.0.1",
            "latest_version": "Dev 1.0.1",
            "update_available": False,
            "patch_notes": "🔒 Dev Environment: Local development mode active (auto-updates and remote patches from houmi.click are permanently disabled).",
            "download_size_mb": 0.0,
            "target_username": "",
            "is_dev": True,
            "auto_update_disabled": True,
        }

    manifest = {
        "current_version": current,
        "latest_version": current,
        "update_available": False,
        "patch_notes": "คุณกำลังใช้งานเวอร์ชันล่าสุดของ Houmi Translation Studio",
        "download_size_mb": 0.0,
    }

    # 1. If running in local client mode, check Central Server first!
    if RUNTIME_MODE != "host":
        try:
            central_url = f"{CENTRAL_HOST}/api/system/check-update?current_version={current}"
            req = urllib.request.Request(
                central_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 HoumiStudio/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    central_manifest = json.loads(resp.read().decode("utf-8"))
                    latest = central_manifest.get("latest_version", current)
                    if is_newer_version(latest, current):
                        return {
                            "current_version": current,
                            "latest_version": latest,
                            "update_available": True,
                            "patch_notes": central_manifest.get("patch_notes", "ปรับปรุงประสิทธิภาพและแก้ไขข้อผิดพลาด"),
                            "download_size_mb": central_manifest.get("download_size_mb", 15.0),
                            "download_url": central_manifest.get("download_url", f"{CENTRAL_HOST}/api/system/download-update"),
                        }
        except Exception as err:
            logger.warning(f"Failed to check update from Central Server: {err}")

    # 2. Fallback to local update_manifest.json (or Central Server manifest file)
    if UPDATE_MANIFEST_PATH.exists():
        try:
            with open(UPDATE_MANIFEST_PATH, "r", encoding="utf-8-sig") as f:
                remote_manifest = json.load(f)
                latest = remote_manifest.get("latest_version", current)
                target_user = remote_manifest.get("target_username", "")
                manifest.update({
                    "latest_version": latest,
                    "target_username": target_user,
                    "update_available": is_newer_version(latest, current),
                    "patch_notes": remote_manifest.get("patch_notes", "ปรับปรุงประสิทธิภาพและแก้ไขข้อผิดพลาด"),
                    "download_size_mb": remote_manifest.get("download_size_mb", 15.0),
                    "download_url": remote_manifest.get("download_url", "/api/system/download-update"),
                })
        except Exception as exc:
            logger.warning(f"Failed to read update manifest: {exc}")

    return manifest


@router.get("/system/check-update")
def check_update(response: Response, current_version: str | None = None):
    """Check for new software version patches."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return check_for_update(current_version)


@router.post("/system/apply-patch")
@router.get("/system/apply-patch")
def apply_patch():
    """Download latest patch zip from Central Server and apply automatically."""
    logger.info("Patch application triggered by client.")

    if RUNTIME_MODE == "host" or IS_DEV_ENV:
        return {"status": "info", "message": "Development environment / Central Host: Remote patch auto-application is permanently disabled."}

    try:
        patch_url = f"{CENTRAL_HOST}/api/system/download-update"
        temp_zip_path = DATA_DIR / "temp_patch.zip"
        local_latest = DATA_DIR / "patches" / "latest_patch.zip"

        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 HoumiStudio/1.0"
        }
        
        download_success = False
        try:
            import requests
            resp = requests.get(patch_url, headers=browser_headers, timeout=15.0, stream=True)
            if resp.status_code == 200:
                with open(temp_zip_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                download_success = True
            else:
                logger.warning(f"Remote patch server returned HTTP {resp.status_code}")
        except Exception as e_req:
            logger.warning(f"Remote patch download via requests failed: {e_req}")

        if not download_success:
            try:
                req = urllib.request.Request(patch_url, headers=browser_headers)
                with urllib.request.urlopen(req, timeout=15) as resp, open(temp_zip_path, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                download_success = True
            except Exception as e_url:
                logger.warning(f"urllib patch download failed: {e_url}")

        if not download_success:
            if local_latest.exists() and zipfile.is_zipfile(local_latest):
                logger.info(f"Using local patch ZIP from {local_latest}...")
                shutil.copy(local_latest, temp_zip_path)
                download_success = True

        if not download_success or not temp_zip_path.exists():
            return {"status": "info", "message": "ระบบอยู่ที่เวอร์ชันล่าสุดแล้ว หรือยังไม่มีแพตช์ออนไลน์ในขณะนี้"}

        if zipfile.is_zipfile(temp_zip_path):
            # Fetch latest version number from Central Server check-update
            target_version = get_current_version()
            try:
                c_url = f"{CENTRAL_HOST}/api/system/check-update"
                c_req = urllib.request.Request(c_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 HoumiStudio/1.0"})
                with urllib.request.urlopen(c_req, timeout=4) as c_resp:
                    if c_resp.status == 200:
                        c_manifest = json.loads(c_resp.read().decode("utf-8"))
                        target_version = c_manifest.get("latest_version", target_version)
            except Exception:
                pass

            # 1. Extract to DATA_DIR / patches / current (works for PyInstaller executables & dev mode)
            dynamic_patch_dir = DATA_DIR / "patches" / "current"
            dynamic_patch_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                members = [info for info in zip_ref.infolist() if not info.is_dir()]
                if not members:
                    raise ValueError("ไฟล์แพตช์ว่าง ไม่มีไฟล์ให้ติดตั้ง")
                for info in members:
                    member_path = Path(info.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(f"ไฟล์แพตช์มี path ไม่ปลอดภัย: {info.filename}")
                zip_ref.extractall(dynamic_patch_dir)

            # Save active patch manifest
            try:
                import time
                with open(PATCH_MANIFEST_PATH, "w", encoding="utf-8") as pf:
                    json.dump({"version": target_version, "applied_at": time.time()}, pf, indent=2)
            except Exception as e_mf:
                logger.warning(f"Failed to write patch manifest: {e_mf}")

            # 2. Extract to _internal (in PyInstaller) or repo root (in Dev mode)
            try:
                if getattr(sys, "frozen", False):
                    target_extract_dir = Path(sys.executable).parent / "_internal"
                else:
                    target_extract_dir = APP_DIR.parent.parent

                logger.info(f"Extracting patch zip to target directory: {target_extract_dir}")
                with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                    zip_ref.extractall(target_extract_dir)
                logger.info("Patch zip extracted successfully to target directory.")
            except Exception as e_write:
                logger.warning(f"Extracting to target directory failed: {e_write}")

            temp_zip_path.unlink(missing_ok=True)
            return {
                "status": "success",
                "version": target_version,
                "message": f"ดาวน์โหลดและติดตั้งแพตช์ v{target_version} สำเร็จเรียบร้อย! ระบบกำลังจะรีโหลดเพื่อเปิดใช้งานเวอร์ชันใหม่"
            }
        else:
            return {"status": "error", "message": "ไฟล์แพตช์จากเซิร์ฟเวอร์ไม่ถูกต้อง (Invalid Zip archive)"}

    except Exception as exc:
        logger.error(f"Failed to apply patch: {exc}", exc_info=True)
        return {"status": "error", "message": f"ดาวน์โหลดหรือติดตั้งแพตช์ไม่สำเร็จ: {str(exc)}"}


@router.get("/system/download-update")
def download_update():
    """Download the latest patch zip file (Served by Central Server or Local Host)."""
    patch_file = PATCHES_DIR / "latest_patch.zip"
    if not patch_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No patch file available for download."
        )
    return FileResponse(
        path=patch_file,
        filename="houmi_patch.zip",
        media_type="application/zip"
    )


@router.get("/system/download-inpaint-server")
def download_inpaint_server():
    """Download the standalone GPU Inpaint Server zip package."""
    server_zip = PATCHES_DIR / "houmi_gpu_inpaint_server.zip"
    if not server_zip.exists():
        server_zip = BASE_DIR.parent / "houmi_gpu_inpaint_server.zip"
    if not server_zip.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GPU Inpaint server zip package not found."
        )
    return FileResponse(
        path=server_zip,
        filename="houmi_gpu_inpaint_server.zip",
        media_type="application/zip"
    )


@router.get("/system/download-installer")
@router.get("/system/download-full")
def download_installer():
    """Download the full standalone single-file EXE installer (HoumiStudio-v0.1.4-Setup.exe)."""
    search_paths = [
        DATA_DIR / "HoumiStudio-v0.1.4-Setup.exe",
        BASE_DIR.parent / "dist" / "HoumiStudio-v0.1.4-Setup.exe",
        BASE_DIR.parent / "HoumiStudio-v0.1.4-Setup.exe",
        DATA_DIR / "HoumiDesktop-dist.zip",
        BASE_DIR.parent / "HoumiDesktop-dist.zip",
    ]
    for installer_file in search_paths:
        if installer_file.exists():
            is_exe = installer_file.name.endswith(".exe")
            return FileResponse(
                path=installer_file,
                filename="HoumiStudio-v0.1.4-Setup.exe" if is_exe else "HoumiDesktop-v0.1.4-dist.zip",
                media_type="application/octet-stream" if is_exe else "application/zip"
            )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Full installer file (HoumiStudio-v0.1.4-Setup.exe) not found on host."
    )


@router.get("/system/changelog")
@router.get("/system/changelogs")
def get_changelog():
    """Return application version history and structured change logs."""
    from app.services.changelog_service import get_all_changelogs
    return {
        "status": "success",
        "current_version": get_current_version(),
        "changelog": CHANGELOG_HISTORY,
        "changelogs": get_all_changelogs(),
    }


@router.get("/download/release/{version}")
@router.get("/api/download/release/{version}")
def download_specific_release(version: str):
    """Download a specific archived version patch zip."""
    clean_ver = version.strip().lstrip("vV")
    tag = f"v{clean_ver}"
    target_zip = DATA_DIR / "releases" / tag / "patch.zip"

    if not target_zip.exists():
        # Fallback check
        target_zip = DATA_DIR / "patches" / "latest_patch.zip"

    if not target_zip.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release {tag} patch zip not found."
        )

    return FileResponse(
        path=target_zip,
        filename=f"HoumiStudio_Patch_{tag}.zip",
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="HoumiStudio_Patch_{tag}.zip"'}
    )


@router.get("/download/latest")
@router.get("/api/download/latest")
def download_latest_release():
    """Download the currently active latest version patch zip."""
    latest_zip = DATA_DIR / "patches" / "latest_patch.zip"
    if not latest_zip.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest patch zip file not available."
        )
    return FileResponse(
        path=latest_zip,
        filename="HoumiStudio_Latest_Patch.zip",
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="HoumiStudio_Latest_Patch.zip"'}
    )


@router.get("/api/system/tauri-update")
@router.get("/api/system/tauri-update/{target}/{arch}/{current_version}")
def tauri_update_endpoint(target: str = "windows", arch: str = "x86_64", current_version: str | None = None):
    """Tauri v2 Native Updater API endpoint returning JSON manifest."""
    latest_ver = get_current_version()
    if current_version and not is_newer_version(latest_ver, current_version):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    manifest_url = f"{CENTRAL_HOST}/api/download/latest"
    return {
        "version": latest_ver,
        "notes": f"Houmi Studio v{latest_ver} Native Update",
        "pub_date": "2026-08-30T14:00:00Z",
        "platforms": {
            f"{target}-{arch}": {
                "signature": "",
                "url": manifest_url
            },
            "windows-x86_64": {
                "signature": "",
                "url": manifest_url
            }
        }
    }


