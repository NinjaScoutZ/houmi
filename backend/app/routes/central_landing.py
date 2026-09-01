"""
Houmi Studio - Premium Public Download & Landing Page
Serves on https://houmi.click/ and https://houmi.click/download
Includes dynamic Version Selector, Changelog viewer, and 1-Click Fast Downloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
try:
    from app.services.patch_manager import list_all_releases, _get_active_version
except Exception:
    def list_all_releases():
        return [{"version": "1.0.5", "size_mb": 3.5, "is_active": True, "release_date": "2026-09-01"}]
    def _get_active_version():
        return "1.0.5"

from app.config import DATA_DIR

router = APIRouter(tags=["Landing & Download"])


def get_central_landing_html() -> str:
    releases = list_all_releases()
    active_ver = str(_get_active_version()).lstrip("vV")
    active_rel = next((r for r in releases if r.get("is_active")), releases[0] if releases else None)
    
    releases_json = json.dumps(releases, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Houmi Studio — AI Manga & Webtoon Translation Studio</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Kanit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Plus Jakarta Sans', 'Kanit', sans-serif; }}
        .bg-grid {{
            background-size: 40px 40px;
            background-image: linear-gradient(to right, rgba(255, 255, 255, 0.03) 1px, transparent 1px),
                              linear-gradient(to bottom, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
        }}
    </style>
</head>
<body class="bg-[#090D16] text-slate-100 min-h-screen flex flex-col selection:bg-amber-500 selection:text-black bg-grid">
    <!-- Navbar -->
    <header class="border-b border-slate-800/80 bg-[#0B111E]/80 backdrop-blur-xl sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 to-yellow-400 p-0.5 shadow-lg shadow-amber-500/20">
                    <div class="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center font-bold text-amber-400 text-base">
                        ⚡
                    </div>
                </div>
                <div>
                    <span class="font-extrabold text-lg text-white tracking-tight">HOUMI <span class="text-amber-400 font-light">STUDIO</span></span>
                    <span class="text-[10px] font-mono font-bold text-amber-400/90 bg-amber-400/10 px-2 py-0.5 rounded-full border border-amber-400/20 ml-2">EARLY ACCESS</span>
                </div>
            </div>
            <div class="flex items-center gap-4">
                <a href="#features" class="text-xs font-semibold text-slate-400 hover:text-white transition">ฟีเจอร์เด่น</a>
                <a href="#versions" class="text-xs font-semibold text-slate-400 hover:text-white transition">คลังเวอร์ชัน</a>
                <a href="/app" class="px-3.5 py-1.5 rounded-lg border border-amber-500/50 bg-amber-500/20 hover:bg-amber-500/30 text-xs font-bold text-amber-300 transition flex items-center gap-1.5 shadow-md shadow-amber-500/10">
                    <span>✨</span>
                    <span>เปิด Web Studio</span>
                </a>
                <a href="/admin" class="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-xs font-bold text-slate-200 transition flex items-center gap-1.5">
                    <span>🛡️</span>
                    <span>Admin Portal</span>
                </a>
            </div>
        </div>
    </header>

    <!-- Hero Section -->
    <main class="flex-1 max-w-6xl w-full mx-auto px-6 py-12 space-y-16">
        <div class="text-center space-y-5 max-w-3xl mx-auto pt-6">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>Production Release พร้อมให้บริการแล้ว</span>
            </div>
            <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-tight">
                สตูดิโอแปลมังงะ & เว็บตูน <br>
                <span class="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-yellow-300 to-amber-500">
                    ด้วย AI ระดับโปรและ Photoshop
                </span>
            </h1>
            <p class="text-slate-400 text-sm sm:text-base leading-relaxed">
                แปลภาษา, สแกนอักษร VLM OCR ภาษาไทยเป๊ะ 100%, คลีนภาพอัตโนมัติด้วย LaMa GPU, 
                และส่งออกเลเยอร์ข้อความแท้ไปยัง Adobe Photoshop ในคลิกเดียว
            </p>

            <!-- Main CTA Buttons Box -->
            <div class="p-6 rounded-3xl bg-gradient-to-b from-slate-800/60 to-slate-900/80 border border-amber-500/30 shadow-2xl shadow-amber-500/5 max-w-xl mx-auto space-y-4">
                <div class="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800 pb-3">
                    <span class="flex items-center gap-1.5 font-bold text-white">
                        <span>📦</span>
                        <span>เวอร์ชันแนะนำ: <strong class="text-amber-400 font-mono">v{active_ver}</strong></span>
                    </span>
                    <span class="font-mono text-slate-400">{active_rel.get('size_mb', '3.44') if active_rel else '3.44'} MB • Windows 64-bit</span>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <a href="/app" class="w-full py-3.5 rounded-2xl bg-gradient-to-r from-amber-500 via-yellow-400 to-amber-500 hover:from-amber-400 hover:to-yellow-300 text-slate-950 font-extrabold text-sm transition-all shadow-xl shadow-amber-500/25 flex items-center justify-center gap-2 group cursor-pointer">
                        <span>✨</span>
                        <span>เปิดใช้งาน Web Studio</span>
                        <span class="group-hover:translate-x-1 transition-transform">➔</span>
                    </a>
                    <a id="mainDownloadBtn" href="/api/system/download-update" class="w-full py-3.5 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 font-bold text-sm transition-all flex items-center justify-center gap-2 cursor-pointer">
                        <span>📥</span>
                        <span>ดาวน์โหลดแอป PC</span>
                    </a>
                </div>
                <p class="text-[11px] text-slate-500 text-center">
                    ใช้งานผ่านเว็บได้ทันที หรือติดตั้งแอปรองรับระบบ Fast OTA Delta Patch อัตโนมัติ
                </p>
            </div>
        </div>

        <!-- Interactive Version Selector Archive Hub -->
        <section id="versions" class="space-y-6 pt-6">
            <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-4">
                <div>
                    <h2 class="text-xl font-bold text-white flex items-center gap-2">
                        <span>📦</span>
                        <span>คลังเวอร์ชันทั้งหมด (Version Archive & Changelogs)</span>
                    </h2>
                    <p class="text-xs text-slate-400">เลือกดาวน์โหลดเวอร์ชันเฉพาะ หรือย้อนเวอร์ชันตามที่คุณต้องการ</p>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-xs text-slate-400">เลือกดูเวอร์ชัน:</span>
                    <select id="versionSelectDropdown" onchange="onVersionSelected(this.value)" class="bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-amber-400">
                    </select>
                </div>
            </div>

            <!-- Selected Version Detail Card -->
            <div id="selectedVersionCard" class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div class="space-y-1">
                        <div class="flex items-center gap-2">
                            <span id="cardVerTag" class="text-lg font-extrabold font-mono text-white">v{active_ver}</span>
                            <span id="cardStatusBadge" class="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">🟢 Active Production</span>
                        </div>
                        <p id="cardReleaseDate" class="text-xs font-mono text-slate-400">Release Date: -</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <a id="cardDownloadZipBtn" href="/api/system/download-update" class="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs transition shadow-lg shadow-amber-500/10 flex items-center gap-1.5">
                            <span>📥</span>
                            <span id="cardDownloadBtnText">ดาวน์โหลด Patch (.zip)</span>
                        </a>
                    </div>
                </div>

                <div class="space-y-2 pt-2 border-t border-slate-800/80">
                    <span class="text-xs font-bold text-slate-300 uppercase tracking-wider text-[10px]">บันทึกการปรับปรุง (Changelog & Patch Notes):</span>
                    <div id="cardPatchNotes" class="p-4 rounded-xl bg-slate-950/80 border border-slate-800/80 text-xs text-slate-300 leading-relaxed font-sans">
                        -
                    </div>
                </div>
            </div>
        </section>

        <!-- Interactive Changelog History Hub -->
        <section id="changelog" class="space-y-6 pt-6">
            <div class="border-b border-slate-800 pb-4">
                <h2 class="text-xl font-bold text-white flex items-center gap-2">
                    <span>📜</span>
                    <span>บันทึกการอัปเดตเวอร์ชันทั้งหมด (Full Changelog History)</span>
                </h2>
                <p class="text-xs text-slate-400">ประวัติการพัฒนา ฟีเจอร์ใหม่ และการแก้ไขข้อผิดพลาดในแต่ละเวอร์ชัน</p>
            </div>

            <div id="changelogContainer" class="space-y-4">
                <!-- Populated dynamically via JS from /api/system/changelogs -->
            </div>
        </section>

        <!-- Feature Grid -->
        <section id="features" class="space-y-6 pt-6">
            <div class="text-center space-y-1">
                <h2 class="text-2xl font-extrabold text-white">ฟีเจอร์เด่นระดับ Studio</h2>
                <p class="text-xs text-slate-400">ออกแบบมาเพื่อนักแปลมังงะและทีมงานแปลมืออาชีพโดยเฉพาะ</p>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div class="p-5 rounded-2xl bg-slate-900/50 border border-slate-800 space-y-2 hover:border-slate-700 transition">
                    <span class="text-2xl">🤖</span>
                    <h3 class="font-bold text-white text-sm">DOBKLE Cloud Hub OCR</h3>
                    <p class="text-xs text-slate-400 leading-relaxed">
                        รวมหลายภาพส่ง OCR VLM Gemini 3.7 / DeepSeek ในรอบเดียว สแกนฟอนต์ไทยและจัดวรรคตอนแม่นยำ 100%
                    </p>
                </div>
                <div class="p-5 rounded-2xl bg-slate-900/50 border border-slate-800 space-y-2 hover:border-slate-700 transition">
                    <span class="text-2xl">⚡</span>
                    <h3 class="font-bold text-white text-sm">Photoshop PSD แท้</h3>
                    <p class="text-xs text-slate-400 leading-relaxed">
                        ส่งออกเป็น Paragraph Text Box พร้อม Effect Glow, Shadow, Stroke ตรงตามสเปก Photoshop ทุกประการ
                    </p>
                </div>
                <div class="p-5 rounded-2xl bg-slate-900/50 border border-slate-800 space-y-2 hover:border-slate-700 transition">
                    <span class="text-2xl">🔑</span>
                    <h3 class="font-bold text-white text-sm">30-Day Offline Grace</h3>
                    <p class="text-xs text-slate-400 leading-relaxed">
                        ระบบ Redeem License Key พร้อมโทเคนออฟไลน์ ทำงานได้ต่อเนื่อง 30 วันแม้ไม่มีสัญญาณอินเทอร์เน็ต
                    </p>
                </div>
            </div>
        </section>

        <!-- Quick Start & Install Steps -->
        <section id="quickstart" class="p-8 rounded-3xl bg-slate-900/60 border border-slate-800 space-y-6">
            <h2 class="text-xl font-bold text-white flex items-center gap-2">
                <span>🛠️</span>
                <span>ขั้นตอนการเริ่มใช้งานครั้งแรก (Quick Start Guide)</span>
            </h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 text-xs text-slate-300">
                <div class="space-y-2">
                    <div class="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-400 font-bold flex items-center justify-center border border-amber-500/30">1</div>
                    <h4 class="font-bold text-white">ดาวน์โหลดไฟล์</h4>
                    <p class="text-slate-400">กดปุ่มดาวน์โหลดด้านบนเพื่อรับแพ็กเกจ Houmi Studio เวอร์ชันล่าสุด</p>
                </div>
                <div class="space-y-2">
                    <div class="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-400 font-bold flex items-center justify-center border border-amber-500/30">2</div>
                    <h4 class="font-bold text-white">แตกไฟล์ Zip</h4>
                    <p class="text-slate-400">แตกไฟล์ Zip ลงในโฟลเดอร์ที่คุณต้องการ (เช่น `C:\\Houmi` หรือ `E:\\Houmi`)</p>
                </div>
                <div class="space-y-2">
                    <div class="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-400 font-bold flex items-center justify-center border border-amber-500/30">3</div>
                    <h4 class="font-bold text-white">เปิดโปรแกรม</h4>
                    <p class="text-slate-400">ดับเบิลคลิก `Start-Dev-Studio.bat` หรือ `HoumiStudio.exe` เพื่อเริ่มใช้งานได้ทันที</p>
                </div>
            </div>
        </section>
    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-800/80 py-8 text-center text-xs text-slate-500">
        <p>Houmi Manga & Webtoon Translation Studio &bull; Cloudflare Tunnel Protected &bull; Official Portal</p>
    </footer>

    <script>
        const allReleases = {releases_json};

        function initDropdown() {{
            const select = document.getElementById("versionSelectDropdown");
            if (!select) return;
            select.innerHTML = allReleases.map(r => `
                <option value="${{r.version}}">v${{r.version}} ${{r.is_active ? '(Active ★)' : ''}}</option>
            `).join("");

            if (allReleases.length > 0) {{
                const active = allReleases.find(r => r.is_active) || allReleases[0];
                select.value = active.version;
                onVersionSelected(active.version);
            }}
        }}

        function onVersionSelected(version) {{
            const rel = allReleases.find(r => r.version === version);
            if (!rel) return;

            document.getElementById("cardVerTag").textContent = "v" + rel.version;
            document.getElementById("cardReleaseDate").textContent = "Release Date: " + (rel.created_at ? new Date(rel.created_at).toLocaleDateString() : "-") + " (" + rel.size_mb + " MB)";
            document.getElementById("cardPatchNotes").textContent = rel.patch_notes || "ไม่มีบันทึกรายละเอียด";
            
            const badge = document.getElementById("cardStatusBadge");
            if (rel.is_active) {{
                badge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
                badge.textContent = "🟢 Active Production";
            }} else {{
                badge.className = "px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700";
                badge.textContent = "📦 Archived Release";
            }}

            const dlBtn = document.getElementById("cardDownloadZipBtn");
            dlBtn.href = "/api/download/release/" + rel.version;
            document.getElementById("cardDownloadBtnText").textContent = "ดาวน์โหลด v" + rel.version + " (" + rel.size_mb + " MB)";
        }}

        async function loadChangelogs() {{
            try {{
                const res = await fetch("/api/system/changelogs");
                const data = await res.json();
                const logs = data.changelogs || data || [];
                const container = document.getElementById("changelogContainer");
                if (!container) return;

                container.innerHTML = logs.map(l => `
                    <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-3">
                        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                            <div class="flex items-center gap-2">
                                <span class="text-lg font-extrabold font-mono text-white">v${{l.version}}</span>
                                <span class="font-bold text-amber-300 text-sm">${{l.title}}</span>
                                ${{l.is_latest ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">LATEST</span>' : ''}}
                            </div>
                            <span class="text-xs font-mono text-slate-400">${{l.release_date}}</span>
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">${{l.summary}}</p>
                        ${{l.categories?.features ? `
                            <div class="space-y-1">
                                <div class="text-[10px] font-bold text-amber-400 uppercase">✨ ฟีเจอร์ใหม่:</div>
                                <ul class="list-disc list-inside text-xs text-slate-300 space-y-0.5">
                                    ${{l.categories.features.map(f => `<li>${{f}}</li>`).join("")}}
                                </ul>
                            </div>
                        ` : ''}}
                        ${{l.categories?.fixes ? `
                            <div class="space-y-1">
                                <div class="text-[10px] font-bold text-rose-400 uppercase">🐛 การแก้ไข:</div>
                                <ul class="list-disc list-inside text-xs text-slate-300 space-y-0.5">
                                    ${{l.categories.fixes.map(f => `<li>${{f}}</li>`).join("")}}
                                </ul>
                            </div>
                        ` : ''}}
                    </div>
                `).join("");
            }} catch (err) {{
                console.warn("Failed to load changelogs:", err);
            }}
        }}

        window.addEventListener("DOMContentLoaded", () => {{
            initDropdown();
            loadChangelogs();
        }});
    </script>
</body>
</html>
"""
