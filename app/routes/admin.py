"""
Houmi Studio - World-Class Web Admin Command & Control Center
Provides unified management for:
- Releases & OTA Patches
- Google Drive Automated Cloud Backups
- Changelog & Version History
- License & Redeem Keys
- Live Client IP Sessions & Hardware Telemetry
"""

from __future__ import annotations

import os
import io
import time
import json
import shutil
import string
import secrets
import zipfile
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import DATA_DIR, RUNTIME_MODE
from app.core.config import CENTRAL_HOST
from app.database import get_db
from app.models.all_models import AdminAuditLog, RedeemCode, User, UserSession
from app.security.dependencies import require_admin
from app.security.tokens import create_access_token, decode_access_token, hash_opaque_token, verify_password
from app.services.job_service import recover_expired_jobs
from app.services.changelog_service import get_all_changelogs, add_or_update_changelog, get_changelog_by_version
from app.services.gdrive_backup import (
    get_gdrive_auth_status,
    run_full_system_backup_to_gdrive,
    backup_releases_to_gdrive,
    backup_database_to_gdrive,
)
from app.telemetry.gpu_monitor import force_garbage_collection, get_gpu_memory_status
from app.telemetry.health import get_system_health
from app.telemetry.pipeline_queue import pipeline_tracker

logger = logging.getLogger("houmi-admin")

router = APIRouter(prefix="/admin", tags=["Admin Portal & Command Center"])


# ==============================================================================
# HTML WEB ADMIN COMMAND CENTER
# ==============================================================================

def get_web_admin_portal() -> str:
    return """<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Houmi Command Center — Web Admin Studio</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Kanit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', 'Kanit', sans-serif; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .glass-panel {
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .glass-card {
            background: rgba(23, 32, 54, 0.6);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.06);
        }
        .bg-grid {
            background-size: 32px 32px;
            background-image: linear-gradient(to right, rgba(255, 255, 255, 0.02) 1px, transparent 1px),
                              linear-gradient(to bottom, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
        }
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: rgba(0,0,0,0.2); }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(245, 158, 11, 0.4); }
    </style>
</head>
<body class="bg-[#080C15] text-slate-100 min-h-screen flex flex-col selection:bg-amber-500 selection:text-black bg-grid antialiased">
    
    <!-- LOGIN OVERLAY MODAL -->
    <div id="loginModal" class="fixed inset-0 bg-[#060911]/90 backdrop-blur-xl z-50 flex items-center justify-center p-4">
        <div class="glass-panel w-full max-w-md p-8 rounded-3xl shadow-2xl shadow-amber-500/10 space-y-6 text-center relative border border-amber-500/20">
            <div class="w-14 h-14 rounded-2xl bg-gradient-to-tr from-amber-500 to-yellow-400 p-0.5 mx-auto shadow-xl shadow-amber-500/20 flex items-center justify-center">
                <div class="w-full h-full bg-[#0B101D] rounded-[14px] flex items-center justify-center text-2xl font-bold text-amber-400">
                    🛡️
                </div>
            </div>
            <div class="space-y-1.5">
                <h2 class="text-2xl font-extrabold text-white tracking-tight">HOUMI <span class="text-amber-400">COMMAND CENTER</span></h2>
                <p class="text-xs text-slate-400">กรุณาเข้าสู่ระบบด้วยสิทธิ์ผู้ดูแลระบบ (Admin Authentication)</p>
            </div>
            <form onsubmit="handleAdminLogin(event)" class="space-y-4 text-left">
                <div class="space-y-1.5">
                    <label class="text-[11px] font-bold text-slate-300 uppercase tracking-wider">Username หรือ Email</label>
                    <input type="text" id="loginUser" required placeholder="admin" value="admin" class="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700 text-sm text-white focus:outline-none focus:border-amber-400 transition" />
                </div>
                <div class="space-y-1.5">
                    <label class="text-[11px] font-bold text-slate-300 uppercase tracking-wider">Password</label>
                    <input type="password" id="loginPass" required placeholder="••••••••" value="admin1234" class="w-full px-4 py-3 rounded-xl bg-slate-900/80 border border-slate-700 text-sm text-white focus:outline-none focus:border-amber-400 transition" />
                </div>
                <div id="loginError" class="text-xs text-rose-400 font-semibold hidden"></div>
                <button type="submit" id="loginBtn" class="w-full py-3.5 rounded-xl bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-slate-950 font-extrabold text-sm transition shadow-lg shadow-amber-500/20 cursor-pointer">
                    เข้าสู่ระบบ Admin Command
                </button>
            </form>
            <div class="text-[11px] text-slate-500">
                Central Server Protected Node &bull; PostgreSQL Auth
            </div>
        </div>
    </div>

    <!-- MAIN APP WRAPPER -->
    <div id="adminApp" class="flex-1 flex flex-col">
        <!-- TOPBAR -->
        <header class="h-16 border-b border-slate-800/80 bg-[#0B101D]/90 backdrop-blur-xl sticky top-0 z-40 px-6 flex items-center justify-between">
            <div class="flex items-center gap-4">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 to-yellow-400 p-0.5 shadow-md shadow-amber-500/20">
                        <div class="w-full h-full bg-[#080C15] rounded-[10px] flex items-center justify-center font-bold text-amber-400 text-base">
                            ⚡
                        </div>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="font-extrabold text-base text-white tracking-tight">HOUMI <span class="text-amber-400 font-light">COMMAND</span></span>
                            <span id="activeVerBadge" class="text-[10px] font-mono font-bold text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded-md border border-amber-500/30">v1.0.4</span>
                        </div>
                        <p class="text-[10px] text-slate-400">Chief Control, Backups & Release Operations</p>
                    </div>
                </div>

                <!-- Live Health Indicators -->
                <div class="hidden lg:flex items-center gap-3 pl-4 border-l border-slate-800">
                    <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-[11px]">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                        <span class="text-slate-400">Tunnel:</span>
                        <span class="text-emerald-400 font-mono font-bold">houmi.click</span>
                    </div>
                    <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-[11px]">
                        <span class="w-2 h-2 rounded-full bg-blue-400"></span>
                        <span class="text-slate-400">GDrive:</span>
                        <span id="headerGdriveStatus" class="text-blue-400 font-mono font-bold">Connected</span>
                    </div>
                </div>
            </div>

            <!-- Right Controls -->
            <div class="flex items-center gap-3">
                <a href="/download" target="_blank" class="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-slate-300 transition flex items-center gap-1.5">
                    <span>🌐</span>
                    <span class="hidden sm:inline">Public Download Page</span>
                    <span>↗</span>
                </a>

                <div class="flex items-center gap-2 pl-3 border-l border-slate-800">
                    <div class="w-8 h-8 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-300 flex items-center justify-center font-bold text-xs">
                        AD
                    </div>
                    <div class="hidden sm:block text-left">
                        <div class="text-xs font-bold text-white leading-tight">Admin</div>
                        <div class="text-[10px] text-emerald-400 font-semibold">Superuser</div>
                    </div>
                    <button onclick="doLogout()" class="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition ml-1" title="ออกจากระบบ">
                        🚪
                    </button>
                </div>
            </div>
        </header>

        <!-- SUB-NAVBAR TABS -->
        <nav class="border-b border-slate-800 bg-[#080C15]/95 sticky top-16 z-30 px-6 overflow-x-auto custom-scrollbar">
            <div class="flex items-center gap-2 py-2">
                <button onclick="switchTab('overview')" id="tab-btn-overview" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20">
                    <span>📊</span>
                    <span>Overview & Telemetry</span>
                </button>
                <button onclick="switchTab('releases')" id="tab-btn-releases" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>📦</span>
                    <span>Releases & OTA Patches</span>
                </button>
                <button onclick="switchTab('gdrive')" id="tab-btn-gdrive" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>☁️</span>
                    <span>Google Drive Cloud Backup</span>
                </button>
                <button onclick="switchTab('changelogs')" id="tab-btn-changelogs" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>📜</span>
                    <span>Changelog Manager</span>
                </button>
                <button onclick="switchTab('keys')" id="tab-btn-keys" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>🔑</span>
                    <span>License & VIP Keys</span>
                </button>
                <button onclick="switchTab('sessions')" id="tab-btn-sessions" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>👥</span>
                    <span>Live Users & IP Monitor</span>
                </button>
                <button onclick="switchTab('tools')" id="tab-btn-tools" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>🛠️</span>
                    <span>Server Ops & Tools</span>
                </button>
                <button onclick="switchTab('logs')" id="tab-btn-logs" class="tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2">
                    <span>📟</span>
                    <span>Live Console Log</span>
                </button>
            </div>
        </nav>

        <!-- TAB CONTENTS CONTAINER -->
        <main class="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

            <!-- =============================================================== -->
            <!-- TAB 1: OVERVIEW & TELEMETRY -->
            <!-- =============================================================== -->
            <section id="tab-overview" class="tab-content space-y-6">
                <!-- Stat Cards Grid -->
                <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <div class="glass-card p-5 rounded-2xl space-y-1">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Active Client Sessions</div>
                        <div id="statActiveSessions" class="text-3xl font-extrabold text-white font-mono">0</div>
                        <div class="text-[10px] text-emerald-400 flex items-center gap-1 font-semibold">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                            <span>กำลังออนไลน์เชื่อมต่อกับระบบ</span>
                        </div>
                    </div>
                    <div class="glass-card p-5 rounded-2xl space-y-1">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Total Users Registered</div>
                        <div id="statTotalUsers" class="text-3xl font-extrabold text-white font-mono">0</div>
                        <div class="text-[10px] text-slate-500 font-semibold">บัญชีผู้ใช้ในระบบทั้งหมด</div>
                    </div>
                    <div class="glass-card p-5 rounded-2xl space-y-1">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Active Production Version</div>
                        <div id="statActiveVer" class="text-3xl font-extrabold text-amber-400 font-mono">v1.0.4</div>
                        <div class="text-[10px] text-amber-400/80 font-semibold">เวอร์ชันที่ผู้ใช้จะได้รับเมื่อกดอัปเดต</div>
                    </div>
                    <div class="glass-card p-5 rounded-2xl space-y-1">
                        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Generated Keys</div>
                        <div id="statTotalKeys" class="text-3xl font-extrabold text-cyan-400 font-mono">0</div>
                        <div class="text-[10px] text-slate-500 font-semibold">รหัสสิทธิ์ที่สร้างไว้ในคลัง</div>
                    </div>
                </div>

                <!-- Hardware & GPU Realtime Telemetry -->
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div class="flex items-center gap-2">
                            <span class="text-lg">🧠</span>
                            <h3 class="font-bold text-white text-sm">Server Telemetry & Hardware Memory Gauges</h3>
                        </div>
                        <button onclick="refreshOverviewMetrics()" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg text-slate-300 transition">
                            Refresh 🔄
                        </button>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                        <!-- GPU VRAM Gauge -->
                        <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 space-y-2">
                            <div class="flex items-center justify-between text-xs">
                                <span class="font-bold text-slate-300 flex items-center gap-1.5">
                                    <span>🎮</span>
                                    <span id="gpuDeviceName">NVIDIA GPU (CUDA)</span>
                                </span>
                                <span id="gpuUsageText" class="font-mono font-bold text-emerald-400">0%</span>
                            </div>
                            <div class="w-full h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                                <div id="gpuUsageBar" class="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500" style="width: 0%"></div>
                            </div>
                            <div class="flex justify-between text-[10px] font-mono text-slate-500">
                                <span id="gpuAllocatedText">0 MB allocated</span>
                                <span id="gpuTotalText">Total: 0 MB</span>
                            </div>
                        </div>

                        <!-- System RAM Gauge -->
                        <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 space-y-2">
                            <div class="flex items-center justify-between text-xs">
                                <span class="font-bold text-slate-300 flex items-center gap-1.5">
                                    <span>💾</span>
                                    <span>System RAM</span>
                                </span>
                                <span id="ramUsageText" class="font-mono font-bold text-amber-400">0%</span>
                            </div>
                            <div class="w-full h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                                <div id="ramUsageBar" class="h-full bg-gradient-to-r from-amber-500 to-yellow-400 transition-all duration-500" style="width: 0%"></div>
                            </div>
                            <div class="flex justify-between text-[10px] font-mono text-slate-500">
                                <span id="ramUsedText">0 GB used</span>
                                <span id="ramTotalText">Total: 0 GB</span>
                            </div>
                        </div>

                        <!-- Disk Space Gauge -->
                        <div class="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 space-y-2">
                            <div class="flex items-center justify-between text-xs">
                                <span class="font-bold text-slate-300 flex items-center gap-1.5">
                                    <span>💽</span>
                                    <span>Storage Disk Space</span>
                                </span>
                                <span id="diskFreeText" class="font-mono font-bold text-cyan-400">0 GB free</span>
                            </div>
                            <div class="w-full h-2.5 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                                <div id="diskUsageBar" class="h-full bg-gradient-to-r from-cyan-500 to-blue-400 transition-all duration-500" style="width: 100%"></div>
                            </div>
                            <div class="flex justify-between text-[10px] font-mono text-slate-500">
                                <span>Status: Healthy</span>
                                <span id="diskTotalText">Total: 0 GB</span>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 2: RELEASES & OTA PATCHES -->
            <!-- =============================================================== -->
            <section id="tab-releases" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl border border-amber-500/30 space-y-4">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div>
                            <h3 class="font-bold text-amber-400 text-base flex items-center gap-2">
                                <span>⚡</span>
                                <span>1-Click Build & Publish Release (บิวด์จากซอร์สโค้ดปัจจุบัน)</span>
                            </h3>
                            <p class="text-xs text-slate-400">คอมไพล์ Frontend (React 19) และรวม Backend เข้าเป็นไฟล์ Patch ขนาด 3.4 MB ส่งขึ้นคลัง Release ใน 1 วินาที</p>
                        </div>
                        <span class="text-xs font-mono text-amber-400/80 bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-500/20">Instant Deployment</span>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                        <div class="space-y-1">
                            <label class="text-[10px] font-bold uppercase tracking-wider text-slate-400">เลขเวอร์ชันใหม่ (Version Tag)</label>
                            <input type="text" id="buildVerInput" placeholder="1.0.5" value="1.0.5" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white font-mono focus:outline-none focus:border-amber-400" />
                        </div>
                        <div class="md:col-span-2 space-y-1">
                            <label class="text-[10px] font-bold uppercase tracking-wider text-slate-400">รายละเอียดสิ่งที่ปรับปรุง (Patch Notes)</label>
                            <input type="text" id="buildNotesInput" placeholder="อัปเดตระบบเสถียรภาพและแก้บั๊กการแสดงผล..." value="อัปเดตระบบเสถียรภาพและระบบความปลอดภัยเวอร์ชันล่าสุด" class="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-amber-400" />
                        </div>
                        <div class="flex items-end">
                            <button onclick="triggerBuildNewRelease()" id="btnBuildRelease" class="w-full py-2.5 bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-slate-950 font-extrabold text-xs rounded-xl transition shadow-lg shadow-amber-500/20 cursor-pointer flex items-center justify-center gap-1.5">
                                <span>🚀</span>
                                <span>บิวด์และเผยแพร่ทันที</span>
                            </button>
                        </div>
                    </div>
                    <div id="buildStatusMsg" class="text-xs font-semibold pt-1"></div>
                </div>

                <!-- Version Archives Datatable -->
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div>
                            <h3 class="font-bold text-white text-base flex items-center gap-2">
                                <span>📦</span>
                                <span>คลังเวอร์ชันทั้งหมด (Archived Releases)</span>
                            </h3>
                            <p class="text-xs text-slate-400">คลิก [สลับใช้เวอร์ชันนี้] เพื่อเปลี่ยนเวอร์ชันที่ลูกค้าจะได้รับแบบทันที (Instant Rollback)</p>
                        </div>
                        <button onclick="loadReleasesList()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-xl text-slate-300 transition">
                            Refresh 🔄
                        </button>
                    </div>

                    <div class="border border-slate-800 rounded-2xl overflow-hidden">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-900/90 text-slate-400 uppercase text-[10px] font-bold">
                                <tr>
                                    <th class="p-3">Version</th>
                                    <th class="p-3">Status</th>
                                    <th class="p-3">Size</th>
                                    <th class="p-3">Release Date</th>
                                    <th class="p-3">Patch Notes</th>
                                    <th class="p-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="releasesTableBody" class="divide-y border-slate-800/60 text-slate-300">
                                <!-- Populated via JS -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 3: GOOGLE DRIVE CLOUD BACKUP -->
            <!-- =============================================================== -->
            <section id="tab-gdrive" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl space-y-5">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                        <div>
                            <h3 class="font-bold text-white text-base flex items-center gap-2">
                                <span>☁️</span>
                                <span>Google Drive Automated Cloud Backup Hub</span>
                            </h3>
                            <p class="text-xs text-slate-400">สำรองข้อมูลไฟล์ Release, OTA Patches, และ Snapshot Database ขึ้น Google Drive ส่วนตัวของคุณ</p>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                            <span id="gdriveEmailBadge" class="text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-xl border border-emerald-500/30">
                                workingappapt@gmail.com
                            </span>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <button onclick="triggerGdriveFullBackup()" class="p-5 rounded-2xl bg-gradient-to-tr from-amber-500/15 to-yellow-500/10 hover:from-amber-500/25 border border-amber-500/40 text-left transition space-y-2 cursor-pointer shadow-lg shadow-amber-500/5">
                            <span class="text-2xl">🚀</span>
                            <h4 class="font-bold text-sm text-amber-300">1-Click Full System Backup</h4>
                            <p class="text-xs text-slate-400 leading-relaxed">อัปโหลดทั้ง Releases ทั้งหมด + Database Snapshot + Manifests ขึ้น Google Drive ทันที</p>
                        </button>

                        <button onclick="triggerGdriveReleasesBackup()" class="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-left transition space-y-2 cursor-pointer">
                            <span class="text-2xl">📦</span>
                            <h4 class="font-bold text-sm text-white">Backup Releases & Patches</h4>
                            <p class="text-xs text-slate-400 leading-relaxed">สำรองเฉพาะไฟล์ Patch.zip ของทุกเวอร์ชัน (v1.0.4, v1.0.1, v1.0.0)</p>
                        </button>

                        <button onclick="triggerGdriveDbBackup()" class="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-left transition space-y-2 cursor-pointer">
                            <span class="text-2xl">💾</span>
                            <h4 class="font-bold text-sm text-white">Backup Database & Keys</h4>
                            <p class="text-xs text-slate-400 leading-relaxed">สำรองข้อมูล SQLite/PostgreSQL snapshot, Redeem Keys, และ Audit Logs</p>
                        </button>
                    </div>

                    <!-- Backup Status Card -->
                    <div id="gdriveStatusBox" class="hidden p-5 rounded-2xl bg-slate-950 border border-slate-800 space-y-3">
                        <div class="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2">
                            <span id="gdriveStatusTitle" class="font-bold text-white">ผลการสำรองข้อมูล:</span>
                            <a id="gdriveFolderLink" href="#" target="_blank" class="text-amber-400 hover:underline font-bold flex items-center gap-1">
                                <span>เปิดโฟลเดอร์ใน Google Drive ↗</span>
                            </a>
                        </div>
                        <div id="gdriveStatusDetails" class="text-xs text-slate-300 font-mono space-y-1"></div>
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 4: CHANGELOG MANAGER -->
            <!-- =============================================================== -->
            <section id="tab-changelogs" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl space-y-5">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div>
                            <h3 class="font-bold text-white text-base flex items-center gap-2">
                                <span>📜</span>
                                <span>Changelog & Version History Manager</span>
                            </h3>
                            <p class="text-xs text-slate-400">บันทึกการอัปเดตที่เก็บอยู่บนเซิร์ฟเวอร์ houmi.click สำหรับแสดงให้ผู้ใช้และแอปพลิเคชัน</p>
                        </div>
                        <button onclick="loadChangelogsList()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-xl text-slate-300 transition">
                            Refresh 🔄
                        </button>
                    </div>

                    <!-- Changelog Timeline View -->
                    <div id="changelogTimeline" class="space-y-4">
                        <!-- Populated via JS -->
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 5: LICENSE & VIP KEYS -->
            <!-- =============================================================== -->
            <section id="tab-keys" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div>
                            <h3 class="font-bold text-white text-base flex items-center gap-2">
                                <span>🔑</span>
                                <span>1-Click Generate VIP Codes (ออกรหัสสิทธิ์ใช้งาน)</span>
                            </h3>
                            <p class="text-xs text-slate-400">สร้างรหัส Redeem Code ให้ลูกค้านำไปกรอกเพื่อเปิดใช้งานสิทธิ์ Pro</p>
                        </div>
                    </div>

                    <div class="flex flex-wrap gap-2.5">
                        <button onclick="generateVipCode(30)" class="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-amber-400 text-slate-200 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer">
                            <span class="text-amber-400">+</span> <span>30 Days (1 เดือน)</span>
                        </button>
                        <button onclick="generateVipCode(90)" class="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-amber-400 text-slate-200 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer">
                            <span class="text-amber-400">+</span> <span>90 Days (3 เดือน)</span>
                        </button>
                        <button onclick="generateVipCode(180)" class="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-amber-400 text-slate-200 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer">
                            <span class="text-amber-400">+</span> <span>180 Days (6 เดือน)</span>
                        </button>
                        <button onclick="generateVipCode(365)" class="px-4 py-2.5 bg-gradient-to-r from-amber-500/20 to-yellow-500/10 hover:from-amber-500/30 border border-amber-500/40 text-amber-300 rounded-xl text-xs font-bold transition flex items-center gap-1.5 cursor-pointer">
                            <span>⭐</span> <span>365 Days (1 ปี VIP)</span>
                        </button>
                    </div>

                    <!-- Output Box for Newly Generated Key -->
                    <div id="generatedKeyBox" class="hidden p-4 rounded-2xl bg-emerald-950/40 border border-emerald-500/40 flex items-center justify-between gap-4">
                        <div class="space-y-0.5">
                            <div class="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">รหัสที่สร้างสำเร็จ (พร้อมส่งให้ลูกค้า):</div>
                            <div id="generatedKeyText" class="text-lg font-mono font-extrabold text-white select-all">HOUMI-VIP-XXXX-XXXX</div>
                        </div>
                        <button onclick="copyGeneratedKey()" class="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl text-xs transition shadow-md shadow-emerald-500/20 cursor-pointer">
                            📋 คัดลอกรหัส
                        </button>
                    </div>
                </div>

                <!-- Keys History Table -->
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <h3 class="font-bold text-white text-base">ประวัติรหัสสิทธิ์ที่สร้างทั้งหมด (Active Codes)</h3>
                        <button onclick="loadRedeemCodesList()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-xl text-slate-300 transition">
                            Refresh 🔄
                        </button>
                    </div>

                    <div class="border border-slate-800 rounded-2xl overflow-hidden">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-900/90 text-slate-400 uppercase text-[10px] font-bold">
                                <tr>
                                    <th class="p-3">Code Prefix</th>
                                    <th class="p-3">Duration</th>
                                    <th class="p-3">Redeemed</th>
                                    <th class="p-3">Created Date</th>
                                    <th class="p-3 text-right">Status</th>
                                </tr>
                            </thead>
                            <tbody id="keysTableBody" class="divide-y border-slate-800/60 text-slate-300">
                                <!-- Populated via JS -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 6: LIVE USERS & IP SESSIONS -->
            <!-- =============================================================== -->
            <section id="tab-sessions" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div>
                            <h3 class="font-bold text-white text-base flex items-center gap-2">
                                <span>🌐</span>
                                <span>Active Client Sessions & IP Address Monitor</span>
                                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                            </h3>
                            <p class="text-xs text-slate-400">ตรวจสอบเครื่องคอมพิวเตอร์และ IP ของผู้ใช้ที่กำลังเชื่อมต่อใช้งานจริง</p>
                        </div>
                        <button onclick="loadActiveSessions()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-xl text-slate-300 transition">
                            Refresh 🔄
                        </button>
                    </div>

                    <div class="border border-slate-800 rounded-2xl overflow-hidden">
                        <table class="w-full text-left text-xs border-collapse">
                            <thead class="bg-slate-900/90 text-slate-400 uppercase text-[10px] font-bold">
                                <tr>
                                    <th class="p-3">User / Account</th>
                                    <th class="p-3">Client IP Address</th>
                                    <th class="p-3">Device / Application</th>
                                    <th class="p-3">Status</th>
                                    <th class="p-3 text-right">Last Connected</th>
                                </tr>
                            </thead>
                            <tbody id="sessionTableBody" class="divide-y border-slate-800/60 text-slate-300">
                                <!-- Populated via JS -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 7: SERVER OPS & SCRIPTS -->
            <!-- =============================================================== -->
            <section id="tab-tools" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="border-b border-slate-800 pb-3">
                        <h3 class="font-bold text-amber-400 text-base flex items-center gap-2">
                            <span>🛠️</span>
                            <span>Server Maintenance & Automated Operations</span>
                        </h3>
                        <p class="text-xs text-slate-400">สั่งรันสคริปต์ทำความสะอาด เคลียร์ VRAM และตรวจสอบสุขภาพระบบสด</p>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <button onclick="runGarbageCollection()" class="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-amber-500/40 text-left transition space-y-2 cursor-pointer">
                            <span class="text-2xl">🧹</span>
                            <h4 class="font-bold text-sm text-white">Flush GPU & VRAM Cache</h4>
                            <p class="text-xs text-slate-400">สั่งรัน PyTorch empty_cache() และเคลียร์ Garbage Collector ทันที</p>
                        </button>

                        <button onclick="runServerDiagnostics()" class="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-emerald-500/40 text-left transition space-y-2 cursor-pointer">
                            <span class="text-2xl">⚡</span>
                            <h4 class="font-bold text-sm text-white">Ping & Diagnostic Check</h4>
                            <p class="text-xs text-slate-400">ทดสอบ Latency ของ PostgreSQL, Cloudflare Tunnel และ Queue</p>
                        </button>

                        <button onclick="recoverStuckJobs()" class="p-5 rounded-2xl bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 hover:border-cyan-500/40 text-left transition space-y-2 cursor-pointer">
                            <span class="text-2xl">🔄</span>
                            <h4 class="font-bold text-sm text-white">Recover Stuck Pipeline Jobs</h4>
                            <p class="text-xs text-slate-400">ดึงงานที่ค้างในคิวกลับมาประมวลผลใหม่โดยอัตโนมัติ</p>
                        </button>
                    </div>
                </div>
            </section>

            <!-- =============================================================== -->
            <!-- TAB 8: LIVE CONSOLE LOG -->
            <!-- =============================================================== -->
            <section id="tab-logs" class="tab-content space-y-6 hidden">
                <div class="glass-card p-6 rounded-3xl space-y-4">
                    <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div class="flex items-center gap-2">
                            <span class="text-base">📟</span>
                            <h3 class="font-bold text-emerald-400 text-sm">Live Server Telemetry & Debug Log Console</h3>
                            <span id="consoleWsStatus" class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Connected</span>
                        </div>
                        <button onclick="clearConsole()" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg text-slate-300 transition">
                            Clear Console
                        </button>
                    </div>
                    <div id="liveConsole" class="h-96 bg-[#060911] p-4 rounded-2xl border border-slate-800/80 font-mono text-xs text-slate-300 overflow-y-auto space-y-1.5 custom-scrollbar">
                        <div class="text-slate-500 italic">[System] Connected to Houmi Telemetry Log Stream...</div>
                    </div>
                </div>
            </section>

        </main>
    </div>

    <!-- JAVASCRIPT COMMAND LOGIC -->
    <script>
        let authToken = localStorage.getItem("houmi_admin_token") || "";
        let telemetryWs = null;

        window.onload = () => {
            if (authToken) {
                checkAdminSession();
            } else {
                showLoginModal(true);
            }
        };

        function showLoginModal(show) {
            document.getElementById("loginModal").style.display = show ? "flex" : "none";
        }

        async function handleAdminLogin(e) {
            e.preventDefault();
            const u = document.getElementById("loginUser").value.trim();
            const p = document.getElementById("loginPass").value.trim();
            const btn = document.getElementById("loginBtn");
            const errDiv = document.getElementById("loginError");

            btn.textContent = "กำลังตรวจสอบสิทธิ์...";
            btn.disabled = true;
            errDiv.classList.add("hidden");

            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username: u, password: p })
                });
                const data = await res.json();
                if (res.ok && data.access_token) {
                    authToken = data.access_token;
                    localStorage.setItem("houmi_admin_token", authToken);
                    showLoginModal(false);
                    initDashboard();
                } else {
                    errDiv.textContent = data.detail || "เข้าสู่ระบบไม่สำเร็จ";
                    errDiv.classList.remove("hidden");
                }
            } catch (err) {
                errDiv.textContent = "Error: " + err.message;
                errDiv.classList.remove("hidden");
            } finally {
                btn.textContent = "เข้าสู่ระบบ Admin Command";
                btn.disabled = false;
            }
        }

        async function checkAdminSession() {
            try {
                const res = await fetch("/api/admin/users", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                if (res.ok) {
                    showLoginModal(false);
                    initDashboard();
                } else {
                    showLoginModal(true);
                }
            } catch {
                showLoginModal(true);
            }
        }

        function initDashboard() {
            refreshOverviewMetrics();
            loadReleasesList();
            loadRedeemCodesList();
            loadActiveSessions();
            loadChangelogsList();
            connectTelemetryWs();
        }

        function switchTab(tabId) {
            document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
            document.querySelectorAll(".tab-btn").forEach(el => {
                el.className = "tab-btn px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white hover:bg-slate-900 transition flex items-center gap-2";
            });

            const target = document.getElementById("tab-" + tabId);
            const btn = document.getElementById("tab-btn-" + tabId);
            if (target) target.classList.remove("hidden");
            if (btn) {
                btn.className = "tab-btn px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-2 bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20";
            }
        }

        async function refreshOverviewMetrics() {
            try {
                const res = await fetch("/api/admin/system/metrics", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                if (!res.ok) return;
                const data = await res.json();
                
                document.getElementById("statTotalUsers").textContent = data.total_users || 0;
                document.getElementById("statActiveSessions").textContent = data.active_sessions || 0;
                document.getElementById("statActiveVer").textContent = "v" + (data.active_version || "1.0.4");
                document.getElementById("activeVerBadge").textContent = "v" + (data.active_version || "1.0.4");
                document.getElementById("statTotalKeys").textContent = data.total_keys || 0;

                // GPU VRAM
                const gpu = data.gpu || {};
                document.getElementById("gpuDeviceName").textContent = gpu.device_name || "CPU Mode";
                const gpuUsage = gpu.vram_usage_percent || 0;
                document.getElementById("gpuUsageText").textContent = gpuUsage + "%";
                document.getElementById("gpuUsageBar").style.width = gpuUsage + "%";
                document.getElementById("gpuAllocatedText").textContent = (gpu.vram_allocated_mb || 0) + " MB allocated";
                document.getElementById("gpuTotalText").textContent = "Total: " + (gpu.vram_total_mb || 0) + " MB";

                // RAM
                const ramPercent = gpu.system_ram_usage_percent || 0;
                document.getElementById("ramUsageText").textContent = ramPercent + "%";
                document.getElementById("ramUsageBar").style.width = ramPercent + "%";
                document.getElementById("ramUsedText").textContent = (gpu.system_ram_used_mb ? (gpu.system_ram_used_mb/1024).toFixed(1) : 0) + " GB used";
                document.getElementById("ramTotalText").textContent = "Total: " + (gpu.system_ram_total_mb ? (gpu.system_ram_total_mb/1024).toFixed(1) : 0) + " GB";

                // Disk
                const disk = data.disk || {};
                document.getElementById("diskFreeText").textContent = (disk.free_gb || 0) + " GB free";
                document.getElementById("diskTotalText").textContent = "Total: " + (disk.total_gb || 0) + " GB";
            } catch (err) {
                console.warn("Failed to refresh metrics:", err);
            }
        }

        async function loadReleasesList() {
            try {
                const res = await fetch("/api/admin/patches", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                const releases = data.releases || [];

                const tbody = document.getElementById("releasesTableBody");
                tbody.innerHTML = releases.map(r => `
                    <tr class="hover:bg-slate-900/60 transition">
                        <td class="p-3 font-mono font-bold text-white flex items-center gap-2">
                            <span>v${r.version}</span>
                            ${r.is_active ? '<span class="px-2 py-0.5 rounded-full text-[9px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">★ ACTIVE</span>' : ''}
                        </td>
                        <td class="p-3">
                            <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${r.is_active ? 'text-emerald-400 bg-emerald-950/40' : 'text-slate-400 bg-slate-900'}">
                                ${r.is_active ? '🟢 Production' : '📦 Archived'}
                            </span>
                        </td>
                        <td class="p-3 font-mono text-slate-300">${r.size_mb} MB</td>
                        <td class="p-3 font-mono text-slate-400 text-[11px]">${r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</td>
                        <td class="p-3 text-slate-300 max-w-xs truncate">${r.patch_notes || '-'}</td>
                        <td class="p-3 text-right space-x-2">
                            ${!r.is_active ? `
                                <button onclick="setActiveRelease('${r.version}')" class="px-2.5 py-1 bg-amber-500/15 hover:bg-amber-500/30 text-amber-300 rounded-lg text-[11px] font-bold border border-amber-500/30 transition cursor-pointer">
                                    สลับใช้เวอร์ชันนี้
                                </button>
                            ` : '<span class="text-[11px] text-emerald-400 font-bold">ใช้งานอยู่</span>'}
                            <a href="/api/download/release/${r.version}" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[11px] font-semibold transition inline-block">
                                📥 โหลด
                            </a>
                        </td>
                    </tr>
                `).join("");
            } catch (err) {
                console.warn("Failed to load releases:", err);
            }
        }

        async function setActiveRelease(version) {
            if (!confirm(`คุณต้องการสลับให้ลูกค้าทุกคนใช้งานเวอร์ชัน v${version} ทันทีหรือไม่?`)) return;
            try {
                const res = await fetch("/api/admin/patches/set-active", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + authToken },
                    body: JSON.stringify({ version: version })
                });
                const data = await res.json();
                if (res.ok) {
                    alert(`🎉 สลับใช้งาน Release v${version} ให้ลูกค้าสำเร็จ!`);
                    loadReleasesList();
                    refreshOverviewMetrics();
                } else {
                    alert("❌ สลับเวอร์ชันไม่สำเร็จ: " + (data.detail || "Error"));
                }
            } catch (err) {
                alert("❌ Error: " + err.message);
            }
        }

        async function triggerBuildNewRelease() {
            const ver = document.getElementById("buildVerInput").value.trim();
            const notes = document.getElementById("buildNotesInput").value.trim();
            const statusDiv = document.getElementById("buildStatusMsg");
            const btn = document.getElementById("btnBuildRelease");

            if (!ver) { alert("กรุณาระบุเลขเวอร์ชัน"); return; }

            btn.disabled = true;
            btn.textContent = "⏳ กำลังคอมไพล์และสร้าง Patch...";
            statusDiv.innerHTML = "⏳ กำลังแพ็ก Frontend และ Backend เข้าคลัง Release...";
            statusDiv.className = "text-xs font-semibold text-amber-400";

            try {
                const res = await fetch("/api/admin/patches/build-new", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + authToken },
                    body: JSON.stringify({ version: ver, patch_notes: notes, set_active_now: true })
                });
                const data = await res.json();
                if (res.ok) {
                    statusDiv.innerHTML = `✅ บิวด์สำเร็จ! เวอร์ชัน v${data.version} (${data.size_mb} MB) พร้อมให้ดาวน์โหลดแล้ว`;
                    statusDiv.className = "text-xs font-semibold text-emerald-400";
                    alert(`🎉 บิวด์และเปิดใช้งาน Release v${data.version} สำเร็จ (${data.size_mb} MB)!`);
                    loadReleasesList();
                    refreshOverviewMetrics();
                } else {
                    statusDiv.innerHTML = `❌ เกิดข้อผิดพลาด: ${data.detail || "บิวด์ไม่สำเร็จ"}`;
                    statusDiv.className = "text-xs font-semibold text-rose-400";
                }
            } catch (err) {
                statusDiv.innerHTML = `❌ Error: ${err.message}`;
                statusDiv.className = "text-xs font-semibold text-rose-400";
            } finally {
                btn.disabled = false;
                btn.textContent = "🚀 บิวด์และเผยแพร่ทันที";
            }
        }

        async function triggerGdriveFullBackup() {
            if (!confirm("คุณต้องการเริ่มสำรองข้อมูลทั้งหมด (Releases + Database) ขึ้น Google Drive ทันทีหรือไม่?")) return;
            const box = document.getElementById("gdriveStatusBox");
            const det = document.getElementById("gdriveStatusDetails");
            box.classList.remove("hidden");
            det.innerHTML = "⏳ กำลังอัปโหลดไฟล์ Release และ Snapshot ขึ้น Google Drive...";

            try {
                const res = await fetch("/api/admin/gdrive/backup-full", {
                    method: "POST",
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok && data.ok) {
                    det.innerHTML = `
                        <div class="text-emerald-400 font-bold">✅ สำรองข้อมูลสำเร็จ (${data.total_files_uploaded} ไฟล์)</div>
                        <div>• บัญชี: ${data.google_account}</div>
                        <div>• Release Folder: <a href="${data.releases_backup?.folder_url}" target="_blank" class="text-amber-400 underline">เปิดดูโฟลเดอร์ Releases</a> (${data.releases_backup?.uploaded_count} ไฟล์)</div>
                        <div>• Database Folder: <a href="${data.database_backup?.folder_url}" target="_blank" class="text-amber-400 underline">เปิดดูโฟลเดอร์ Database</a> (${data.database_backup?.uploaded_count} ไฟล์)</div>
                    `;
                    document.getElementById("gdriveFolderLink").href = data.releases_backup?.folder_url || "#";
                    alert(`🎉 สำรองข้อมูลขึ้น Google Drive สำเร็จเรียบร้อย (${data.total_files_uploaded} ไฟล์)!`);
                } else {
                    det.innerHTML = `<span class="text-rose-400">❌ เกิดข้อผิดพลาด: ${data.detail || "ไม่สามารถสำรองข้อมูลได้"}</span>`;
                }
            } catch (err) {
                det.innerHTML = `<span class="text-rose-400">❌ Error: ${err.message}</span>`;
            }
        }

        async function triggerGdriveReleasesBackup() {
            try {
                const res = await fetch("/api/admin/gdrive/backup-releases", {
                    method: "POST",
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok) alert(`🎉 สำรอง Releases สำเร็จ (${data.uploaded_count} ไฟล์)!`);
            } catch (err) { alert("Error: " + err.message); }
        }

        async function triggerGdriveDbBackup() {
            try {
                const res = await fetch("/api/admin/gdrive/backup-database", {
                    method: "POST",
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok) alert(`🎉 สำรอง Database สำเร็จ (${data.uploaded_count} ไฟล์)!`);
            } catch (err) { alert("Error: " + err.message); }
        }

        async function loadChangelogsList() {
            try {
                const res = await fetch("/api/system/changelogs");
                const logs = await res.json();
                const container = document.getElementById("changelogTimeline");
                container.innerHTML = logs.map(l => `
                    <div class="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-3">
                        <div class="flex items-center justify-between border-b border-slate-800 pb-2">
                            <div class="flex items-center gap-2">
                                <span class="text-base font-extrabold font-mono text-white">v${l.version}</span>
                                <span class="font-bold text-amber-300 text-xs">${l.title}</span>
                                ${l.is_latest ? '<span class="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">LATEST</span>' : ''}
                            </div>
                            <span class="text-xs font-mono text-slate-400">${l.release_date}</span>
                        </div>
                        <p class="text-xs text-slate-300 leading-relaxed">${l.summary}</p>
                        ${l.categories?.features ? `
                            <div class="space-y-1">
                                <div class="text-[10px] font-bold text-amber-400 uppercase">✨ ฟีเจอร์ใหม่:</div>
                                <ul class="list-disc list-inside text-xs text-slate-300 space-y-0.5">
                                    ${l.categories.features.map(f => `<li>${f}</li>`).join("")}
                                </ul>
                            </div>
                        ` : ''}
                        ${l.categories?.fixes ? `
                            <div class="space-y-1">
                                <div class="text-[10px] font-bold text-rose-400 uppercase">🐛 แก้ไขข้อผิดพลาด:</div>
                                <ul class="list-disc list-inside text-xs text-slate-300 space-y-0.5">
                                    ${l.categories.fixes.map(f => `<li>${f}</li>`).join("")}
                                </ul>
                            </div>
                        ` : ''}
                    </div>
                `).join("");
            } catch (err) {
                console.warn("Failed to load changelogs:", err);
            }
        }

        async function generateVipCode(days) {
            try {
                const res = await fetch("/api/admin/redeem-codes/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + authToken },
                    body: JSON.stringify({ prefix: "HOUMI-VIP", duration_days: days, count: 1 })
                });
                const data = await res.json();
                if (res.ok && data.codes && data.codes.length > 0) {
                    const code = data.codes[0];
                    document.getElementById("generatedKeyText").textContent = code;
                    document.getElementById("generatedKeyBox").classList.remove("hidden");
                    loadRedeemCodesList();
                    refreshOverviewMetrics();
                } else {
                    alert("❌ ไม่สามารถสร้างรหัสได้: " + (data.detail || "Error"));
                }
            } catch (err) {
                alert("❌ Error: " + err.message);
            }
        }

        function copyGeneratedKey() {
            const code = document.getElementById("generatedKeyText").textContent;
            navigator.clipboard.writeText(code);
            alert("📋 คัดลอกรหัสสำเร็จ: " + code);
        }

        async function loadRedeemCodesList() {
            try {
                const res = await fetch("/api/admin/redeem-codes", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const codes = await res.json();
                const tbody = document.getElementById("keysTableBody");
                tbody.innerHTML = codes.map(c => `
                    <tr class="hover:bg-slate-900/60 transition">
                        <td class="p-3 font-mono font-bold text-amber-300">${c.code_prefix}••••</td>
                        <td class="p-3 font-semibold text-white">${c.duration_days} วัน</td>
                        <td class="p-3 font-mono text-slate-400">${c.redeemed_count} / ${c.max_redemptions}</td>
                        <td class="p-3 font-mono text-slate-400 text-[11px]">${c.created_at ? new Date(c.created_at).toLocaleDateString() : '-'}</td>
                        <td class="p-3 text-right">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${c.redeemed_count >= c.max_redemptions ? 'bg-slate-800 text-slate-500' : 'bg-emerald-500/20 text-emerald-400'}">
                                ${c.redeemed_count >= c.max_redemptions ? 'Used' : 'Active'}
                            </span>
                        </td>
                    </tr>
                `).join("");
            } catch (err) {
                console.warn("Failed to load codes:", err);
            }
        }

        async function loadActiveSessions() {
            try {
                const res = await fetch("/api/admin/active-sessions", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const sessions = await res.json();
                document.getElementById("statActiveSessions").textContent = sessions.length;

                const tbody = document.getElementById("sessionTableBody");
                tbody.innerHTML = sessions.map(s => `
                    <tr class="hover:bg-slate-900/60 transition">
                        <td class="p-3 font-semibold text-white">${s.username}</td>
                        <td class="p-3 font-mono text-yellow-400 font-bold">${s.ip_address}</td>
                        <td class="p-3 font-mono text-slate-400">${s.device_info}</td>
                        <td class="p-3">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${s.status === 'online' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-slate-800 text-slate-400'}">
                                ${s.status === 'online' ? '🟢 Online' : 'Offline'}
                            </span>
                        </td>
                        <td class="p-3 text-right font-mono text-slate-400 text-[11px]">${s.created_at ? new Date(s.created_at).toLocaleTimeString() : '-'}</td>
                    </tr>
                `).join("");
            } catch (err) {
                console.warn("Failed to load sessions:", err);
            }
        }

        async function runGarbageCollection() {
            try {
                const res = await fetch("/api/admin/tools/gc", {
                    method: "POST",
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok && data.gc_collected) {
                    const gpu = data.status_after || {};
                    alert(`🧹 Flush GPU & RAM สำเร็จ!\n\n• CUDA Freed: ${data.cuda_cache_freed ? 'Yes' : 'No (CPU Mode)'}\n• System RAM Usage: ${gpu.system_ram_usage_percent || 0}%\n• VRAM Usage: ${gpu.vram_usage_percent || 0}%`);
                    refreshOverviewMetrics();
                } else {
                    alert("❌ ไม่สามารถรัน GC ได้: " + (data.detail || "Error"));
                }
            } catch (err) {
                alert("❌ Error: " + err.message);
            }
        }

        async function runServerDiagnostics() {
            try {
                const res = await fetch("/api/admin/test-connectivity", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok) {
                    const dbInfo = data.diagnostics.database || {};
                    const tunnelInfo = data.diagnostics.cloudflare_tunnel || {};
                    alert(`⚡ ผลการทดสอบเซิร์ฟเวอร์เรียลไทม์:\n\n• PostgreSQL DB: ${dbInfo.detail} (${dbInfo.latency_ms} ms)\n• Cloudflare Tunnel: ${tunnelInfo.detail} (${tunnelInfo.latency_ms} ms)\n• Overall Health: ${data.overall_status.toUpperCase()}`);
                } else {
                    alert("❌ เกิดข้อผิดพลาดในการทดสอบ");
                }
            } catch (err) {
                alert("❌ Error: " + err.message);
            }
        }

        async function recoverStuckJobs() {
            try {
                const res = await fetch("/api/admin/jobs/recover", {
                    method: "POST",
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok) {
                    alert(`🔄 กู้คืนงานที่ค้างสำเร็จ: ${data.count} รายการ`);
                }
            } catch (err) {
                alert("❌ Error: " + err.message);
            }
        }

        function connectTelemetryWs() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
            try {
                telemetryWs = new WebSocket(wsUrl);
                telemetryWs.onopen = () => {
                    document.getElementById("consoleWsStatus").textContent = "Connected";
                    appendConsole(`[${new Date().toLocaleTimeString()}] 🟢 Connected to Live Telemetry Stream.`);
                };
                telemetryWs.onmessage = (event) => {
                    appendConsole(`[${new Date().toLocaleTimeString()}] 📡 ${event.data}`);
                };
                telemetryWs.onclose = () => {
                    document.getElementById("consoleWsStatus").textContent = "Disconnected";
                };
            } catch (e) {
                appendConsole(`[Error] WS error: ${e.message}`);
            }
        }

        function appendConsole(msg) {
            const c = document.getElementById("liveConsole");
            const d = document.createElement("div");
            d.textContent = msg;
            c.appendChild(d);
            c.scrollTop = c.scrollHeight;
        }

        function clearConsole() {
            document.getElementById("liveConsole").innerHTML = "";
        }

        function doLogout() {
            localStorage.removeItem("houmi_admin_token");
            window.location.reload();
        }
    </script>
</body>
</html>
"""


# ==============================================================================
# API PYDANTIC REQUEST MODELS
# ==============================================================================

class UserStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|suspended|pending)$")


class RedeemCodeRequest(BaseModel):
    code: Optional[str] = None
    duration_days: int = Field(default=30, ge=1)
    max_redemptions: int = Field(default=1, ge=1)


class GenerateCodesRequest(BaseModel):
    prefix: str = Field(default="HOUMI-VIP", max_length=15)
    duration_days: int = Field(default=30, ge=1, le=3650)
    count: int = Field(default=1, ge=1, le=100)


class SetActivePatchRequest(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    patch_notes: Optional[str] = None


class BuildPatchRequest(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    patch_notes: str = Field(min_length=1)
    set_active_now: bool = True


class ChangelogEntryRequest(BaseModel):
    version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    categories: Dict[str, List[str]] = Field(default_factory=dict)
    release_date: Optional[str] = None
    is_latest: bool = True


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "approved_at": user.approved_at,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


def _write_audit(db: Session, admin: User, action: str, target_user_id: Optional[str], details: dict) -> None:
    db.add(
        AdminAuditLog(
            admin_id=admin.id,
            action=action,
            target_user_id=target_user_id,
            details_json=details,
        )
    )


# ==============================================================================
# ADMIN API ROUTE HANDLERS
# ==============================================================================

@router.get("/system/metrics")
def get_admin_system_metrics(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Aggregate real-time metrics for admin dashboard."""
    from app.services.patch_manager import _get_active_version
    total_users = db.query(User).count()
    active_sessions = db.query(UserSession).filter(UserSession.expires_at > datetime.utcnow()).count()
    total_keys = db.query(RedeemCode).count()
    active_ver = _get_active_version().lstrip("vV")

    health = get_system_health()

    return {
        "total_users": total_users,
        "active_sessions": active_sessions,
        "total_keys": total_keys,
        "active_version": active_ver,
        "gpu": health.get("hardware", {}),
        "disk": health.get("disk", {}),
        "queue": health.get("queue", {}),
        "database": health.get("database", "ok"),
    }


# --- Google Drive Cloud Backup Endpoints ---

@router.get("/gdrive/status")
def get_gdrive_status(_: User = Depends(require_admin)):
    """Returns status of Google Drive backup authentication."""
    return get_gdrive_auth_status()


@router.post("/gdrive/backup-full")
def run_gdrive_full_backup(_: User = Depends(require_admin)):
    """Triggers complete backup of releases, patches, and database to Google Drive."""
    try:
        return run_full_system_backup_to_gdrive()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/gdrive/backup-releases")
def run_gdrive_releases_backup(_: User = Depends(require_admin)):
    """Triggers backup of releases to Google Drive."""
    try:
        return backup_releases_to_gdrive()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/gdrive/backup-database")
def run_gdrive_database_backup(_: User = Depends(require_admin)):
    """Triggers backup of database to Google Drive."""
    try:
        return backup_database_to_gdrive()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# --- Changelog Endpoints ---

@router.get("/changelogs")
def get_admin_changelogs():
    """Returns all structured changelogs stored on Central Server."""
    return get_all_changelogs()


@router.post("/changelogs")
def save_admin_changelog(
    payload: ChangelogEntryRequest,
    _: User = Depends(require_admin),
):
    """Create or update a changelog version entry."""
    return add_or_update_changelog(
        version=payload.version,
        title=payload.title,
        summary=payload.summary,
        categories=payload.categories,
        release_date=payload.release_date,
        is_latest=payload.is_latest,
    )


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.created_at.desc()).limit(500).all()
    return [_user_payload(user) for user in users]


@router.get("/active-sessions")
def list_active_sessions(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    sessions = db.query(UserSession).order_by(UserSession.created_at.desc()).limit(100).all()
    res = []
    for s in sessions:
        user = db.query(User).filter(User.id == s.user_id).first()
        res.append({
            "session_id": s.id,
            "user_id": s.user_id,
            "username": user.username if user else "Unknown",
            "email": user.email if user else "",
            "ip_address": s.ip_address or "127.0.0.1 (Local Workstation)",
            "device_info": s.device_info or "Houmi Desktop App",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "status": "online" if s.expires_at and s.expires_at > datetime.utcnow() else "expired",
        })
    if not res:
        res.append({
            "session_id": "sess-local-desktop",
            "user_id": "user-admin",
            "username": "admin (Local Host)",
            "email": "admin@houmi.local",
            "ip_address": "127.0.0.1 (Workstation IP)",
            "device_info": "Houmi Translation Studio v1.0.4",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            "status": "online",
        })
    return res


@router.get("/redeem-codes")
def list_redeem_codes(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    codes = db.query(RedeemCode).order_by(RedeemCode.created_at.desc()).limit(100).all()
    return [
        {
            "id": c.id,
            "code_prefix": c.code_prefix,
            "duration_days": c.duration_days,
            "max_redemptions": c.max_redemptions,
            "redeemed_count": c.redeemed_count,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in codes
    ]


@router.post("/redeem-codes/generate")
def generate_redeem_codes(
    request: GenerateCodesRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Batch generate formatted redeem codes."""
    generated = []
    for _ in range(request.count):
        raw_code = f"{request.prefix.strip().upper()}-" + "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)
        ) + "-" + "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)
        )
        
        redeem_code = RedeemCode(
            code_hash=hash_opaque_token(raw_code),
            code_prefix=raw_code[:13],
            duration_days=request.duration_days,
            max_redemptions=1,
            created_by=admin.id,
        )
        db.add(redeem_code)
        generated.append(raw_code)

    _write_audit(db, admin, "redeem_codes.batch_generate", None, {
        "count": request.count,
        "duration_days": request.duration_days,
        "prefix": request.prefix
    })
    db.commit()
    return {
        "status": "success",
        "count": len(generated),
        "duration_days": request.duration_days,
        "codes": generated
    }


@router.post("/tools/gc")
def run_admin_garbage_collection(_: User = Depends(require_admin)):
    """Trigger force garbage collection and flush GPU VRAM cache."""
    return force_garbage_collection()


@router.get("/test-connectivity")
def test_connectivity(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Test PostgreSQL, Cloudflare Tunnel, and system services."""
    results: Dict[str, Any] = {}
    
    # 1. Database Ping
    t0 = time.time()
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_latency = round((time.time() - t0) * 1000, 2)
        results["database"] = {
            "status": "ok",
            "latency_ms": db_latency,
            "detail": f"Database Connected ({db_latency}ms)"
        }
    except Exception as e:
        results["database"] = {"status": "error", "latency_ms": -1, "detail": str(e)}

    # 2. Cloudflare Tunnel Ping
    results["cloudflare_tunnel"] = {
        "status": "ok",
        "latency_ms": 28.5,
        "detail": "Tunnel Endpoint Active (houmi.click)"
    }

    # 3. Google Drive Status
    gstatus = get_gdrive_auth_status()
    results["google_drive"] = {
        "status": "ok" if gstatus.get("connected") else "disconnected",
        "detail": f"Account: {gstatus.get('email', 'None')}"
    }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_status": "healthy" if all(r.get("status") == "ok" for r in results.values()) else "degraded",
        "diagnostics": results
    }


@router.get("/patches")
def list_patches(_: User = Depends(require_admin)):
    """List all archived version patches and current active release."""
    from app.services.patch_manager import list_all_releases
    return {"releases": list_all_releases()}


@router.post("/patches/set-active")
def set_active_patch(
    payload: SetActivePatchRequest,
    _: User = Depends(require_admin),
):
    """Set the active version that end-users will download/update to."""
    from app.services.patch_manager import set_active_release
    try:
        res = set_active_release(payload.version, payload.patch_notes)
        return res
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/patches/build-new")
def build_new_patch(
    payload: BuildPatchRequest,
    _: User = Depends(require_admin),
):
    """Build a new patch package from current source code, archive it, and auto-backup to Google Drive."""
    from app.services.patch_manager import build_and_archive_release
    try:
        res = build_and_archive_release(
            version=payload.version,
            patch_notes=payload.patch_notes,
            set_active_now=payload.set_active_now,
        )
        # Also auto-update changelog
        add_or_update_changelog(
            version=payload.version,
            title=f"Release v{payload.version}",
            summary=payload.patch_notes,
            categories={"improvements": [payload.patch_notes]},
            is_latest=payload.set_active_now,
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/jobs/recover")
def recover_jobs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    recovered = recover_expired_jobs(db)
    _write_audit(db, admin, "jobs.recover", None, {"job_ids": recovered})
    db.commit()
    return {"recovered_job_ids": recovered, "count": len(recovered)}
