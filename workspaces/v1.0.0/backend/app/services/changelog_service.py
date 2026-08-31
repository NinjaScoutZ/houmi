"""
Houmi Studio - Comprehensive Changelog & Version History Service
Maintains structured release notes, categorizations, and release dates.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.config import DATA_DIR, BASE_DIR

logger = logging.getLogger("houmi-changelog")

CHANGELOG_JSON_FILE = DATA_DIR / "changelogs.json"

DEFAULT_CHANGELOGS = [
    {
        "version": "1.0.4",
        "title": "Production Architecture & Dobkle Cloud AI Hub",
        "release_date": "2026-08-30",
        "is_latest": True,
        "summary": "สถาปัตยกรรมระดับ Production พร้อมระบบ DOBKLE Cloud OCR, LaMa GPU Inpainting, Export Studio และ Google Drive Backup",
        "categories": {
            "features": [
                "DOBKLE Cloud Hub: Multi-crop PDF packing และ Gemini 3.7 VLM OCR สแกนภาษาไทยแม่นยำ 100%",
                "Google Drive Cloud Backup: สำรองข้อมูล Release, Patch และ Database ขึ้น Google Drive อัตโนมัติ",
                "Web Admin Command Center: แดชบอร์ดมอนิเตอร์ VRAM สด, จัดการ Release 1-Click และสร้าง VIP Key",
                "Export Studio: ส่งออกไฟล์ PSD (Photoshop Layer แท้), PNG, JPEG, TXT และ CBZ ครบวงจร"
            ],
            "fixes": [
                "แก้ปัญหา Unicode Image Path ในการส่งออก PSD บน Windows",
                "แก้ปัญหา ImageFont .size compatibility ในการคำนวณวรรคตอนข้อความ",
                "ปรับปรุง Fabric.js Text Box Auto-wrap และ Color Picker Realtime Commit"
            ],
            "improvements": [
                "VRAM Auto-GC: เคลียร์แคช PyTorch อัตโนมัติเมื่อ VRAM เกิน 85% ป้องกัน CUDA OOM",
                "Zip-Slip Protection: ระบบสกัดกั้น Path Traversal ในการแตกไฟล์ OTA Patch 100%"
            ],
            "ai_engines": [
                "Manga UNet++ AI Segmenter v2",
                "LaMa-Manga High-Resolution Inpainter",
                "YOLO Balloon Detector v8",
                "Meta SAM 2.1 SFX Extractor"
            ]
        }
    },
    {
        "version": "1.0.1",
        "title": "Photoshop FX & High-Res Text Formatting",
        "release_date": "2026-08-25",
        "is_latest": False,
        "summary": "เพิ่มระบบ Photoshop Text Engine, Text Stroke, Glow, Drop Shadow และ Auto Typography Templates",
        "categories": {
            "features": [
                "Photoshop Paragraph & Point Text mode switcher",
                "Text Styling Preset Templates (Bubble, Shout, Whisper, Box, SFX)",
                "Scrubby Slider สำหรับปรับขนาด Font, Tracking, Line Height แบบ Photoshop"
            ],
            "fixes": [
                "แก้ปัญหา Text Layer ขยับตำแหน่งเมื่อนำเข้า Adobe Photoshop",
                "ปรับปรุงการตัดคำภาษาไทยอัตโนมัติ (Thai Word Segmentation)"
            ],
            "improvements": [
                "ลดเวลาคอมไพล์ Frontend ด้วย Vite 6 เหลือเพียง 0.5 วินาที",
                "ระบบ 30-Day Offline Grace Token ทำงานได้โดยไม่ต้องต่อเน็ตตลอดเวลา"
            ]
        }
    },
    {
        "version": "1.0.0",
        "title": "Official Commercial Release",
        "release_date": "2026-08-20",
        "is_latest": False,
        "summary": "เปิดตัว Houmi Manga & Webtoon Translation Studio อย่างเป็นทางการ",
        "categories": {
            "features": [
                "Infinite High-Performance Canvas with React 19",
                "Smart Stitching & Webtoon Seam Alignment",
                "Redeem Key & License Authentication",
                "Realtime Delta Patch OTA Auto-Updater"
            ],
            "ai_engines": [
                "Gemini 3.7 VLM OCR",
                "DeepSeek Chat OCR",
                "LaMa Inpaint Server"
            ]
        }
    }
]


def _ensure_changelogs_file() -> None:
    if not CHANGELOG_JSON_FILE.exists():
        CHANGELOG_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHANGELOG_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CHANGELOGS, f, indent=2, ensure_ascii=False)


def get_all_changelogs() -> List[Dict[str, Any]]:
    """Returns all changelogs sorted by version descending."""
    _ensure_changelogs_file()
    try:
        with open(CHANGELOG_JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as exc:
        logger.warning(f"Error reading changelogs.json: {exc}")
    return DEFAULT_CHANGELOGS


def get_changelog_by_version(version: str) -> Optional[Dict[str, Any]]:
    clean_ver = version.strip().lstrip("vV")
    logs = get_all_changelogs()
    for log in logs:
        if log.get("version", "").strip().lstrip("vV") == clean_ver:
            return log
    return None


def add_or_update_changelog(
    version: str,
    title: str,
    summary: str,
    categories: Dict[str, List[str]],
    release_date: Optional[str] = None,
    is_latest: bool = True,
) -> Dict[str, Any]:
    """Adds or updates a structured changelog entry and marks latest."""
    clean_ver = version.strip().lstrip("vV")
    logs = get_all_changelogs()

    if is_latest:
        for l in logs:
            l["is_latest"] = False

    entry = {
        "version": clean_ver,
        "title": title.strip(),
        "release_date": release_date or datetime.utcnow().strftime("%Y-%m-%d"),
        "is_latest": is_latest,
        "summary": summary.strip(),
        "categories": categories,
    }

    # Replace existing or insert at beginning
    updated = False
    for idx, l in enumerate(logs):
        if l.get("version", "").strip().lstrip("vV") == clean_ver:
            logs[idx] = entry
            updated = True
            break

    if not updated:
        logs.insert(0, entry)

    with open(CHANGELOG_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved changelog for v{clean_ver}")
    return entry
