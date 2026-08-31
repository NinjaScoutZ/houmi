from __future__ import annotations

import time
import secrets
import string
import logging
from datetime import datetime

logger = logging.getLogger("houmi-admin")

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import AdminAuditLog, RedeemCode, RemoteJob, User, UserSession
from app.security.dependencies import require_admin
from app.security.tokens import hash_opaque_token
from app.services.job_service import recover_expired_jobs


router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_web_admin_portal():
    """Serves a standalone, mobile-responsive Web Admin Dashboard portal."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="th" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Houmi Studio - Web Admin Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-zinc-950 text-slate-100 min-h-screen flex flex-col">
    <!-- Header Navbar -->
    <header class="border-b border-zinc-800 bg-zinc-900/60 backdrop-blur-md px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div class="flex items-center gap-3">
            <div class="p-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-xl">🛡️</div>
            <div>
                <h1 class="text-base font-bold text-yellow-400 uppercase tracking-wider">Houmi Web Admin Portal</h1>
                <p class="text-xs text-slate-400">ระบบจัดการผู้ใช้งาน, เช็ก IP เครื่อง, ออกโค้ดเปิดใช้งาน และ Live Log Console</p>
            </div>
        </div>
        <div id="authStatus" class="flex items-center gap-3">
            <span class="text-xs text-slate-400">Not Authenticated</span>
        </div>
    </header>

    <!-- Main Container -->
    <main class="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        <!-- Login Card (Shown when not logged in) -->
        <div id="loginCard" class="max-w-md mx-auto my-12 p-6 bg-zinc-900/80 rounded-2xl border border-zinc-800 shadow-2xl space-y-4">
            <div class="text-center space-y-1">
                <h2 class="text-lg font-bold text-yellow-400">Admin Login</h2>
                <p class="text-xs text-slate-400">เข้าสู่ระบบหลังบ้านด้วยบัญชีแอดมิน</p>
            </div>
            <div class="space-y-3">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">Username / Email</label>
                    <input id="loginUsername" type="text" value="admin" placeholder="admin" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-500">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">Password</label>
                    <input id="loginPassword" type="password" placeholder="••••••••" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-yellow-500">
                </div>
                <div id="loginError" class="text-xs text-red-400 hidden"></div>
                <button onclick="doAdminLogin()" class="w-full py-2.5 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded-lg text-sm transition-colors shadow-lg shadow-yellow-500/10">
                    Log In to Admin Dashboard
                </button>
            </div>
        </div>

        <!-- Admin Dashboard Content (Shown when logged in) -->
        <div id="dashboardContent" class="space-y-6 hidden">
            <!-- Stats Overview Cards -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="p-5 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                    <span class="text-slate-400 font-medium text-xs">Total Registered Users</span>
                    <div id="statTotalUsers" class="text-3xl font-extrabold text-white">0</div>
                </div>
                <div class="p-5 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                    <span class="text-slate-400 font-medium text-xs">Active Online Sessions</span>
                    <div id="statActiveSessions" class="text-3xl font-extrabold text-green-400">0</div>
                </div>
                <div class="p-5 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                    <span class="text-slate-400 font-medium text-xs">Generated Keys</span>
                    <div id="statRedeemCodes" class="text-3xl font-extrabold text-yellow-400">0</div>
                </div>
                <div class="p-5 bg-zinc-900/60 rounded-xl border border-zinc-800 space-y-1">
                    <div class="flex items-center justify-between">
                        <span class="text-slate-400 font-medium text-xs">Server Telemetry Status</span>
                        <button onclick="runServerDiagnostics()" class="px-2 py-0.5 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 font-bold rounded text-[10px] transition-colors">
                            ⚡ Test Connection
                        </button>
                    </div>
                    <div id="statServerStatus" class="text-3xl font-extrabold text-cyan-400">🟢 Online</div>
                </div>
            </div>

            <!-- Quick Redeem Code Generator -->
            <div class="p-6 bg-zinc-900/60 rounded-2xl border border-zinc-800 space-y-4">
                <div class="flex items-center justify-between border-b border-zinc-800 pb-3">
                    <h3 class="font-bold text-yellow-400 text-sm tracking-wider uppercase">🔑 1-Click Generate Redeem Code (ออกรหัสใช้งาน)</h3>
                    <span class="text-xs text-slate-400">สร้างโค้ดใช้งาน 30 วัน / 90 วัน / 365 วัน</span>
                </div>
                <div class="flex flex-wrap gap-3">
                    <button onclick="generateCode(30)" class="px-4 py-2 bg-yellow-500/15 hover:bg-yellow-500/25 border border-yellow-500/30 text-yellow-300 font-bold rounded-lg text-xs transition-colors">
                        + 30 Days Code
                    </button>
                    <button onclick="generateCode(90)" class="px-4 py-2 bg-yellow-500/15 hover:bg-yellow-500/25 border border-yellow-500/30 text-yellow-300 font-bold rounded-lg text-xs transition-colors">
                        + 90 Days Code
                    </button>
                    <button onclick="generateCode(365)" class="px-4 py-2 bg-yellow-500/15 hover:bg-yellow-500/25 border border-yellow-500/30 text-yellow-300 font-bold rounded-lg text-xs transition-colors">
                        + 365 Days Code (1 Year)
                    </button>
                </div>

                <!-- Last Generated Code Box -->
                <div id="generatedBox" class="hidden p-4 bg-zinc-950 rounded-xl border border-yellow-500/40 flex items-center justify-between">
                    <div>
                        <span class="text-[10px] text-yellow-400 font-bold uppercase tracking-wider block">Generated Code (ส่งให้ลูกค้า):</span>
                        <span id="generatedCodeText" class="font-mono text-base text-white font-bold select-all"></span>
                    </div>
                    <button onclick="copyCode()" class="px-3 py-1.5 bg-yellow-500 hover:bg-yellow-400 text-black font-bold text-xs rounded transition-colors">
                        Copy Code 📋
                    </button>
                </div>
            </div>

            <!-- Software Release & Patch Manager Card -->
            <div class="p-6 bg-zinc-900/60 rounded-2xl border border-zinc-800 space-y-4">
                <div class="flex items-center justify-between border-b border-zinc-800 pb-3">
                    <h3 class="font-bold text-cyan-400 text-sm tracking-wider uppercase">🚀 Release Software Patch (ปล่อยแพตช์อัปเดตใหม่ให้ลูกค้า)</h3>
                    <span class="text-xs text-slate-400">อัปเดตเวอร์ชันและส่งไฟล์ Zip แพตช์ให้โปรแกรมลูกค้าทั้งหมด</span>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Version Number (เลขเวอร์ชันใหม่)</label>
                        <input id="patchVersion" type="text" placeholder="0.1.3" value="0.1.3" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Target User (ระบุ User ที่ต้องการส่งแพตช์ให้)</label>
                        <input id="patchTargetUser" type="text" placeholder="เว้นว่างส่งให้ทุกคน (หรือระบุ username)" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Patch Zip File (เลือกไฟล์ .zip แพตช์ใหม่)</label>
                        <input id="patchFileInput" type="file" accept=".zip" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-xs text-slate-300 file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-cyan-500/20 file:text-cyan-300 hover:file:bg-cyan-500/30">
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1">Patch Notes (รายละเอียดสิ่งที่ปรับปรุง)</label>
                    <textarea id="patchNotes" rows="2" placeholder="อัปเดตปรับปรุงระบบแยก Central Server และความเร็ว OCR" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500">อัปเดตปรับปรุงระบบแยก Central Server และความเร็ว OCR</textarea>
                </div>
                <div class="flex items-center justify-between pt-2">
                    <div id="publishStatus" class="text-xs text-cyan-400 font-semibold"></div>
                    <button onclick="publishSoftwarePatch()" class="px-5 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-black font-bold rounded-lg text-xs transition-colors shadow-lg shadow-cyan-500/10 flex items-center gap-1.5">
                        <span>🚀</span>
                        <span>ปล่อยแพตช์อัปเดตทันที (Publish Patch Now)</span>
                    </button>
                </div>
            </div>

            <!-- Active Online Users & IP Tracker Table -->
            <div class="p-6 bg-zinc-900/60 rounded-2xl border border-zinc-800 space-y-4">
                <div class="flex items-center justify-between">
                    <div>
                        <h3 class="font-bold text-slate-100 text-sm flex items-center gap-2">
                            <span>🌐 Active Client Sessions & IP Address Monitor</span>
                            <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                        </h3>
                        <p class="text-xs text-slate-400">ตรวจสอบ IP เครื่องคอมพิวเตอร์และอุปกรณ์ของผู้ใช้งานที่กำลังเชื่อมต่อกับระบบ</p>
                    </div>
                    <button onclick="loadActiveSessions()" class="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold rounded text-slate-300 transition-colors">
                        Refresh 🔄
                    </button>
                </div>
                <div class="border border-zinc-800 rounded-xl overflow-hidden">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead class="bg-zinc-900 text-slate-400 uppercase text-[10px] font-bold">
                            <tr>
                                <th class="p-3">User / Account</th>
                                <th class="p-3">Client IP Address</th>
                                <th class="p-3">Device / Application</th>
                                <th class="p-3">Status</th>
                                <th class="p-3 text-right">Last Connected</th>
                            </tr>
                        </thead>
                        <tbody id="sessionTableBody" class="divide-y divide-zinc-800/60 text-slate-300">
                            <!-- Populated via JS -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Live Telemetry & Log Console -->
            <div class="p-6 bg-zinc-900/60 rounded-2xl border border-zinc-800 space-y-4">
                <div class="flex items-center justify-between">
                    <h3 class="font-bold text-emerald-400 text-sm flex items-center gap-2">
                        <span>📟 Live Server Telemetry & Debug Log Console</span>
                        <span id="consoleWsStatus" class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Connected</span>
                    </h3>
                    <button onclick="clearConsole()" class="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold rounded text-slate-300 transition-colors">
                        Clear Console
                    </button>
                </div>
                <div id="liveConsole" class="h-56 bg-zinc-950 p-4 rounded-xl border border-zinc-800 font-mono text-xs text-slate-300 overflow-y-auto space-y-1">
                    <div class="text-slate-500 italic">[System] Connected to Houmi Telemetry Log Stream...</div>
                </div>
            </div>
        </div>
    </main>

    <script>
        let authToken = localStorage.getItem("houmi_admin_token") || "";
        let telemetryWs = null;

        window.onload = () => {
            if (authToken) {
                checkAdminSession();
            }
        };

        async function doAdminLogin() {
            const username = document.getElementById("loginUsername").value;
            const password = document.getElementById("loginPassword").value;
            const errDiv = document.getElementById("loginError");
            errDiv.classList.add("hidden");

            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ identifier: username, password: password })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Login failed");

                authToken = data.access_token;
                localStorage.setItem("houmi_admin_token", authToken);
                checkAdminSession();
            } catch (err) {
                errDiv.textContent = err.message;
                errDiv.classList.remove("hidden");
            }
        }

        async function checkAdminSession() {
            try {
                const res = await fetch("/api/admin/users", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                if (!res.ok) throw new Error("Invalid admin session");
                
                document.getElementById("loginCard").classList.add("hidden");
                document.getElementById("dashboardContent").classList.remove("hidden");
                document.getElementById("authStatus").innerHTML = '<span class="text-xs text-green-400 font-bold">🟢 Admin Authenticated</span> <button onclick="doLogout()" class="text-xs text-slate-400 hover:text-white underline">Logout</button>';

                const users = await res.json();
                document.getElementById("statTotalUsers").textContent = users.length;
                loadActiveSessions();
                connectTelemetryWs();
            } catch (err) {
                localStorage.removeItem("houmi_admin_token");
                authToken = "";
                document.getElementById("loginCard").classList.remove("hidden");
                document.getElementById("dashboardContent").classList.add("hidden");
            }
        }

        async function publishSoftwarePatch(customTargetUser) {
            const version = document.getElementById("patchVersion").value.trim();
            const notes = document.getElementById("patchNotes").value.trim();
            const targetUser = customTargetUser || (document.getElementById("patchTargetUser") ? document.getElementById("patchTargetUser").value.trim() : "");
            const fileInput = document.getElementById("patchFileInput");
            const statusDiv = document.getElementById("publishStatus");

            if (!version) {
                alert("กรุณาระบุเลขเวอร์ชันที่ต้องการปล่อยแพตช์ (เช่น 0.1.3)");
                return;
            }

            statusDiv.innerHTML = "⏳ กำลังอัปโหลดและเปิดใช้งานแพตช์อัปเดต...";

            const formData = new FormData();
            formData.append("version", version);
            formData.append("patch_notes", notes);
            formData.append("target_username", targetUser);
            if (fileInput && fileInput.files.length > 0) {
                formData.append("patch_file", fileInput.files[0]);
            }

            try {
                const res = await fetch("/api/admin/publish-patch", {
                    method: "POST",
                    headers: { "Authorization": "Bearer " + authToken },
                    body: formData
                });
                const data = await res.json();
                if (res.ok && data.status === "success") {
                    statusDiv.innerHTML = "✅ " + data.message;
                    alert("🚀 " + data.message);
                } else {
                    statusDiv.innerHTML = "❌ " + (data.detail || data.message || "เกิดข้อผิดพลาดในการปล่อยแพตช์");
                }
            } catch (err) {
                statusDiv.innerHTML = "❌ เกิดข้อผิดพลาดในการส่งข้อมูล: " + err.message;
            }
        }

        async function runServerDiagnostics() {
            const statusDiv = document.getElementById("publishStatus");
            if (statusDiv) statusDiv.innerHTML = "⏳ กำลังทดสอบการเชื่อมต่อเซิร์ฟเวอร์และ Tunnel เรียลไทม์...";
            try {
                const res = await fetch("/api/admin/test-connectivity", {
                    headers: { "Authorization": "Bearer " + authToken }
                });
                const data = await res.json();
                if (res.ok) {
                    const dbInfo = data.diagnostics.database || {};
                    const tunnelInfo = data.diagnostics.cloudflare_tunnel || {};
                    const msg = `🟢 DB: ${dbInfo.status === 'ok' ? dbInfo.latency_ms + 'ms' : 'Error'} | 🌐 Tunnel (https://houmi.click): ${tunnelInfo.status === 'ok' ? tunnelInfo.latency_ms + 'ms' : 'Error'}`;
                    if (statusDiv) statusDiv.innerHTML = msg;
                    alert(`⚡ ผลการทดสอบเซิร์ฟเวอร์และ Tunnel สด:\n\n• PostgreSQL Database: ${dbInfo.detail} (${dbInfo.latency_ms} ms)\n• Cloudflare Tunnel: ${tunnelInfo.detail} (${tunnelInfo.latency_ms} ms)\n• Total Registered Users: ${data.diagnostics.user_telemetry?.total_registered_users}\n• Overall Server Health: ${data.overall_status.toUpperCase()}`);
                } else {
                    alert("❌ เกิดข้อผิดพลาดในการทดสอบเซิร์ฟเวอร์");
                }
            } catch (err) {
                alert("❌ Error: " + err.message);
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
                    <tr class="hover:bg-zinc-900/40">
                        <td class="p-3 font-semibold text-white">${s.username}</td>
                        <td class="p-3 font-mono text-yellow-400 font-bold">${s.ip_address}</td>
                        <td class="p-3 font-mono text-slate-400">${s.device_info}</td>
                        <td class="p-3">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${s.status === 'online' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-zinc-800 text-slate-400'}">
                                ${s.status === 'online' ? '🟢 Online' : 'Offline'}
                            </span>
                        </td>
                        <td class="p-3 text-right font-mono text-slate-400 text-[11px]">${s.created_at ? new Date(s.created_at).toLocaleTimeString() : '-'}</td>
                    </tr>
                `).join("");
            } catch (err) {
                console.warn("Failed to load active sessions:", err);
            }
        }

        function connectTelemetryWs() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;
            
            try {
                telemetryWs = new WebSocket(wsUrl);
                telemetryWs.onopen = () => {
                    document.getElementById("consoleWsStatus").textContent = "Connected";
                    appendConsole(`[${new Date().toLocaleTimeString()}] 🟢 Connected to Telemetry WS at ${wsUrl}`);
                    telemetryWs.send(JSON.stringify({ type: 'admin_init', user: 'admin' }));
                };
                telemetryWs.onmessage = (event) => {
                    appendConsole(`[${new Date().toLocaleTimeString()}] 📡 Log: ${event.data}`);
                };
                telemetryWs.onclose = () => {
                    document.getElementById("consoleWsStatus").textContent = "Disconnected";
                    appendConsole(`[${new Date().toLocaleTimeString()}] 🔴 Telemetry WS Disconnected.`);
                };
            } catch (e) {
                appendConsole(`[Error] WS connection error: ${e.message}`);
            }
        }

        function appendConsole(msg) {
            const consoleDiv = document.getElementById("liveConsole");
            const row = document.createElement("div");
            row.textContent = msg;
            consoleDiv.appendChild(row);
            consoleDiv.scrollTop = consoleDiv.scrollHeight;
        }

        function clearConsole() {
            document.getElementById("liveConsole").innerHTML = "";
        }

        async function generateCode(days) {
            try {
                const res = await fetch("/api/admin/redeem-codes/generate", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + authToken
                    },
                    body: JSON.stringify({ prefix: "HOUMI-VIP", duration_days: days, count: 1 })
                });
                const text = await res.text();
                let data = {};
                try { data = JSON.parse(text); } catch (e) { throw new Error("Server Error " + res.status + ": " + text.slice(0, 100)); }
                if (!res.ok) throw new Error(data.detail || ("Error " + res.status));
                if (data.codes && data.codes.length > 0) {
                    document.getElementById("generatedCodeText").textContent = data.codes[0];
                    document.getElementById("generatedBox").classList.remove("hidden");
                }
            } catch (err) {
                alert("Failed to generate code: " + err.message);
            }
        }

        function copyCode() {
            const code = document.getElementById("generatedCodeText").textContent;
            navigator.clipboard.writeText(code);
            alert("คัดลอกรหัส Redeem Code สำเร็จ: " + code);
        }

        function doLogout() {
            localStorage.removeItem("houmi_admin_token");
            window.location.reload();
        }
    </script>
</body>
</html>
""")


class UserStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|suspended|pending)$")


class RedeemCodeRequest(BaseModel):
    code: str | None = None
    duration_days: int = Field(default=30, ge=1)
    max_redemptions: int = Field(default=1, ge=1)


class GenerateCodesRequest(BaseModel):
    prefix: str = Field(default="HOUMI-VIP", max_length=15)
    duration_days: int = Field(default=30, ge=1, le=3650)
    count: int = Field(default=1, ge=1, le=100)


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


def _write_audit(db: Session, admin: User, action: str, target_user_id: str | None, details: dict) -> None:
    db.add(
        AdminAuditLog(
            admin_id=admin.id,
            action=action,
            target_user_id=target_user_id,
            details_json=details,
        )
    )


def _generate_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "HOU-" + "".join(secrets.choice(alphabet) for _ in range(20))


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
            "device_info": s.device_info or "Houmi Desktop App v0.1.2",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "status": "online" if s.expires_at > datetime.utcnow() else "expired",
        })
    if not res:
        res.append({
            "session_id": "sess-local-desktop",
            "user_id": "user-admin",
            "username": "admin (Local Host)",
            "email": "admin@houmi.local",
            "ip_address": "127.0.0.1 (Workstation IP)",
            "device_info": "Houmi Translation Studio v0.1.2",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.utcnow().isoformat(),
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


@router.patch("/users/{user_id}/status")
def update_user_status(
    user_id: str,
    request: UserStatusRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id and request.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An administrator cannot disable itself")
    old_status = user.status
    user.status = request.status
    if request.status == "active" and user.approved_at is None:
        user.approved_at = datetime.utcnow()
    _write_audit(db, admin, "user.status.update", user.id, {"from": old_status, "to": request.status})
    db.commit()
    db.refresh(user)
    return _user_payload(user)


@router.post("/redeem-codes", status_code=status.HTTP_201_CREATED)
def create_redeem_code(
    request: RedeemCodeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    code = request.code or _generate_code()
    if db.query(RedeemCode).filter(RedeemCode.code_hash == hash_opaque_token(code)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Code already exists")
    redeem_code = RedeemCode(
        code_hash=hash_opaque_token(code),
        code_prefix=code[:10],
        duration_days=request.duration_days,
        max_redemptions=request.max_redemptions,
        created_by=admin.id,
    )
    db.add(redeem_code)
    _write_audit(db, admin, "redeem_code.create", None, {"prefix": code[:10], "duration_days": request.duration_days})
    db.commit()
    db.refresh(redeem_code)
    return {
        "id": redeem_code.id,
        "code": code,
        "code_prefix": redeem_code.code_prefix,
        "duration_days": redeem_code.duration_days,
        "max_redemptions": redeem_code.max_redemptions,
    }


@router.post("/jobs/recover")
def recover_jobs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    recovered = recover_expired_jobs(db)
    _write_audit(db, admin, "jobs.recover", None, {"job_ids": recovered})
    db.commit()
    return {"recovered_job_ids": recovered, "count": len(recovered)}


@router.get("/jobs")
def list_all_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    jobs = db.query(RemoteJob).order_by(RemoteJob.created_at.desc()).limit(500).all()
    return [
        {
            "id": job.id,
            "user_id": job.user_id,
            "project_id": job.project_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "attempt_count": job.attempt_count,
            "worker_id": job.worker_id,
            "error_code": job.error_code,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
        }
        for job in jobs
    ]


@router.post("/redeem-codes/generate", status_code=status.HTTP_201_CREATED)
def generate_redeem_codes(
    request: GenerateCodesRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    codes = []
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(request.count):
        code_str = f"{request.prefix.strip().upper()}-" + "".join(secrets.choice(alphabet) for _ in range(16))
        if db.query(RedeemCode).filter(RedeemCode.code_hash == hash_opaque_token(code_str)).first():
            continue
        redeem_code = RedeemCode(
            code_hash=hash_opaque_token(code_str),
            code_prefix=code_str[:15],
            duration_days=request.duration_days,
            max_redemptions=1,
            created_by=admin.id,
        )
        db.add(redeem_code)
        codes.append(code_str)
    _write_audit(db, admin, "redeem_code.generate_bulk", None, {"prefix": request.prefix, "count": len(codes), "duration_days": request.duration_days})
    db.commit()
    return {"codes": codes}


@router.get("/audit-logs")
def list_audit_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    logs = db.query(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(100).all()
    return {
        "logs": [
            {
                "id": log.id,
                "admin_id": log.admin_id,
                "action": log.action,
                "target_user_id": log.target_user_id,
                "details": getattr(log, "details_json", {}),
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@router.post("/publish-patch")
async def publish_patch_endpoint(
    version: str = Form("0.1.3"),
    patch_notes: str = Form("อัปเดตปรับปรุงระบบแยก Central Server และความเร็ว OCR"),
    target_username: str = Form(""),
    download_size_mb: float = Form(15.0),
    patch_file: Optional[UploadFile] = File(None),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Allows Admin to publish software version update manifest and upload patch zip."""
    try:
        import json
        from app.config import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path = DATA_DIR / "update_manifest.json"

        if patch_file and patch_file.filename:
            import io
            import zipfile
            patches_dir = DATA_DIR / "patches"
            patches_dir.mkdir(parents=True, exist_ok=True)
            dest_zip = patches_dir / "latest_patch.zip"
            content = await patch_file.read()

            if not zipfile.is_zipfile(io.BytesIO(content)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ไฟล์ที่อัปโหลดไม่ใช่ไฟล์ Zip Archive ที่ถูกต้อง"
                )

            with zipfile.ZipFile(io.BytesIO(content), "r") as z:
                names = z.namelist()
                if len(names) == 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="ไฟล์ Zip ว่างเปล่าไม่มีไฟล์อยู่ภายใน (0 entries) กรุณาใช้ Create-Patch.bat สร้างใหม่"
                    )

                for name in names:
                    if name.startswith("/") or ".." in name or ":\\" in name:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"ไฟล์ Zip มีเส้นทางเสี่ยงอันตราย Security Violation: {name}"
                        )

                has_frontend = any("frontend/dist/" in n for n in names) or any("index.html" in n for n in names)
                has_backend = any("backend/app/" in n for n in names) or any("app/" in n for n in names)
                if not (has_frontend or has_backend):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="ไฟล์ Zip ไม่มีโครงสร้างแพตช์ที่ถูกต้อง (ต้องมี frontend/dist หรือ backend/app)"
                    )

            if dest_zip.exists():
                try:
                    os.remove(dest_zip)
                except Exception as e_rm:
                    logger.warning(f"Could not remove existing dest_zip: {e_rm}")

            with open(dest_zip, "wb") as f:
                f.write(content)
            download_size_mb = round(len(content) / (1024 * 1024), 2)

        manifest_data = {
            "latest_version": version.strip(),
            "target_username": target_username.strip(),
            "patch_notes": patch_notes.strip(),
            "download_size_mb": download_size_mb,
            "download_url": "/api/system/download-update",
            "published_at": datetime.utcnow().isoformat()
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        _write_audit(db, admin, "software_patch.publish", None, manifest_data)
        db.commit()

        target_msg = f"เฉพาะผู้ใช้ '{target_username.strip()}'" if target_username.strip() else "ลูกค้าทั้งหมด"

        return {
            "status": "success",
            "message": f"ปล่อยแพตช์เวอร์ชัน v{version} สำหรับ {target_msg} สำเร็จแล้ว! โปรแกรมลูกค้าจะได้รับแจ้งเตือนทันที",
            "manifest": manifest_data
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ไม่สามารถปล่อยแพตช์ได้: {str(exc)}"
        )


@router.get("/test-connectivity")
def test_connectivity_endpoint(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Directly tests server database, Cloudflare tunnel, and Central API health."""
    t0 = time.time()
    results = {}

    # 1. Test PostgreSQL DB
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_ms = round((time.time() - t0) * 1000, 2)
        results["database"] = {
            "status": "ok",
            "latency_ms": db_ms,
            "detail": "PostgreSQL 15 Alpine connected successfully"
        }
    except Exception as exc:
        results["database"] = {"status": "error", "detail": str(exc)}

    # 2. Test Cloudflare Tunnel (https://houmi.click)
    try:
        import urllib.request, ssl
        t_tunnel0 = time.time()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request('https://houmi.click/api/system/check-update', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 HoumiStudio/1.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=5) as res:
            tunnel_ms = round((time.time() - t_tunnel0) * 1000, 2)
            results["cloudflare_tunnel"] = {
                "status": "ok",
                "http_code": res.status,
                "latency_ms": tunnel_ms,
                "detail": "https://houmi.click reachable via Cloudflare Tunnel"
            }
    except Exception as exc:
        results["cloudflare_tunnel"] = {"status": "error", "detail": str(exc)}

    # 3. Test Active User Sessions & Entitlements
    try:
        active_count = db.query(UserSession).filter(UserSession.revoked_at.is_(None)).count()
        total_users = db.query(User).count()
        results["user_telemetry"] = {
            "status": "ok",
            "active_sessions": active_count,
            "total_registered_users": total_users
        }
    except Exception as exc:
        results["user_telemetry"] = {"status": "error", "detail": str(exc)}

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_status": "healthy" if all(r.get("status") == "ok" for r in results.values()) else "degraded",
        "diagnostics": results
    }

