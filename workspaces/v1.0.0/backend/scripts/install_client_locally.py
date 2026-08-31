"""
Houmi Studio - Client Local Installer Script
Installs a clean, isolated client version of Houmi Studio to C:\\HoumiStudio
with zero developer files and sets up a Desktop shortcut.
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

# Paths
SOURCE_PATCH = Path(r"E:\houmi\backend\data\patches\latest_patch.zip")
INSTALL_DIR = Path(r"C:\HoumiStudio")
DESKTOP_DIR = Path(os.environ.get("USERPROFILE", r"C:\Users\dansa")) / "Desktop"

print("==========================================================")
print("  HOUMI STUDIO — CLIENT LOCAL INSTALLER")
print(f"  Target Destination: {INSTALL_DIR}")
print(f"  Source Patch: {SOURCE_PATCH}")
print("==========================================================")

if not SOURCE_PATCH.exists():
    print(f"❌ Error: {SOURCE_PATCH} not found!")
    sys.exit(1)

# 1. Create clean client installation directory
INSTALL_DIR.mkdir(parents=True, exist_ok=True)
(INSTALL_DIR / "data" / "projects").mkdir(parents=True, exist_ok=True)
(INSTALL_DIR / "data" / "fonts").mkdir(parents=True, exist_ok=True)
(INSTALL_DIR / "data" / "cache").mkdir(parents=True, exist_ok=True)

# 2. Extract client files from patch archive
print("\n[1/4] Extracting clean production client files...")
with zipfile.ZipFile(SOURCE_PATCH, "r") as zf:
    zf.extractall(INSTALL_DIR)
print("✓ Extracted frontend/dist, backend/app, ocr_server, and bin successfully.")

# 3. Create client entry-point run script (run_client.py)
run_client_code = '''import sys
import os
import time
import socket
import threading
import webbrowser
from pathlib import Path

# Client root directory
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Automatically find available local port
HOUMI_PORT_VAL = 4000
for p in range(4000, 4100):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", p))
            HOUMI_PORT_VAL = p
            break
        except OSError:
            continue

# Environment configuration for client desktop mode
os.environ["HOUMI_HOST"] = "127.0.0.1"
os.environ["HOUMI_PORT"] = str(HOUMI_PORT_VAL)
os.environ["PRODUCTION_MODE"] = "1"
os.environ["HOUMI_RUNTIME_MODE"] = "local"
os.environ["HOUMI_CENTRAL_SERVER_URL"] = "https://houmi.click"

import uvicorn

try:
    import webview
except ImportError:
    webview = None

class FastAPIThread(threading.Thread):
    def __init__(self, port: int):
        super().__init__()
        self.daemon = True
        self.port = port
        self.server = None

    def run(self):
        config = uvicorn.Config(
            "app.main:app",
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            reload=False
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def shutdown(self):
        if self.server:
            self.server.should_exit = True

def main():
    port = HOUMI_PORT_VAL
    client_url = f"http://127.0.0.1:{port}/"

    print("==================================================")
    print("  HOUMI MANGA & WEBTOON TRANSLATION STUDIO")
    print(f"  Official Client Application (v1.0.4) — Port {port}")
    print("==================================================")
    print("⚡ Starting background local API server...")
    server_thread = FastAPIThread(port)
    server_thread.start()

    # Wait for server port
    import urllib.request
    server_ready = False
    for _ in range(30):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/system/check-update")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.4)

    if webview is not None:
        print("🖥️ Launching Studio Native Desktop Window...")
        try:
            webview.create_window(
                title="Houmi Studio — Manga & Webtoon Translation",
                url=client_url,
                width=1366,
                height=860,
                min_size=(1024, 768),
                resizable=True
            )
            webview.start(private_mode=False)
        except Exception as e:
            print(f"ℹ️ Native Webview fallback: {e}")
            print(f"🌐 Opening default web browser at {client_url}...")
            webbrowser.open(client_url)
            print("\\nโปรแกรมกำลังทำงานอยู่ กด Ctrl+C ในหน้าต่างนี้เมื่อต้องการปิดโปรแกรม")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        print(f"🌐 Opening Houmi Studio in your web browser: {client_url}...")
        webbrowser.open(client_url)
        print("\\nโปรแกรมกำลังทำงานอยู่ กด Ctrl+C ในหน้าต่างนี้เมื่อต้องการปิดโปรแกรม")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    server_thread.shutdown()
    sys.exit(0)

if __name__ == "__main__":
    main()
'''

with open(INSTALL_DIR / "run_client.py", "w", encoding="utf-8") as f:
    f.write(run_client_code)

# 4. Create launcher batch file (Start-Houmi-Studio.bat)
launcher_bat = r'''@echo off
title Houmi Studio Client Launcher
cd /d "%~dp0"

echo ===================================================
echo   HOUMI STUDIO — CLIENT LAUNCHER
echo ===================================================

:: 1. Check dedicated virtual environment paths
set "PY_EXE="

if exist "E:\houmi\backend\.venv\Scripts\python.exe" (
    set "PY_EXE=E:\houmi\backend\.venv\Scripts\python.exe"
    goto :RUN_APP
)

if exist "%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
    goto :RUN_APP
)

if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
    goto :RUN_APP
)

:: 2. Fallback to system python
set "PY_EXE=python"

:RUN_APP
echo Using Python: %PY_EXE%
echo.
"%PY_EXE%" run_client.py
if %errorlevel% neq 0 (
    echo.
    echo ❌ Program exited with error code %errorlevel%
    pause
)
'''
title Houmi Studio
cd /d "%~dp0"
echo ===================================================
echo   Starting Houmi Studio Client Application...
echo ===================================================
python run_client.py
pause
'''

with open(INSTALL_DIR / "Start-Houmi-Studio.bat", "w", encoding="utf-8") as f:
    f.write(launcher_bat)

print("✓ Created run_client.py and Start-Houmi-Studio.bat")

# 5. Create Desktop Shortcut using PowerShell
print("\n[3/4] Creating Windows Desktop Shortcut...")
shortcut_path = DESKTOP_DIR / "Houmi Studio.lnk"
ps_cmd = f'''
$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')
$Shortcut.TargetPath = '{INSTALL_DIR / "Start-Houmi-Studio.bat"}'
$Shortcut.WorkingDirectory = '{INSTALL_DIR}'
$Shortcut.Description = 'Houmi Manga & Webtoon Translation Studio'
$Shortcut.Save()
'''

import subprocess
subprocess.run(["powershell", "-Command", ps_cmd], check=True)
print(f"✓ Desktop shortcut created: {shortcut_path}")

print("\n==========================================================")
print("🎉 [SUCCESS] Houmi Studio Client installed successfully!")
print(f"📁 Location: {INSTALL_DIR}")
print("🚀 Launch by double-clicking 'Houmi Studio' on your Desktop!")
print("==========================================================")
