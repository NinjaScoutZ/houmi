@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.5 - TAURI v2 DEV MODE
color 0D

echo ===============================================================================
echo        HOUMI STUDIO v1.0.5 - 100%% WORKSPACE ISOLATED TAURI v2 DEV
echo        (Rust Native Window + Vite HMR + Python AI Backend)
echo ===============================================================================
echo.

cd /d "%~dp0"

echo [*] Freeing ports 4000, 5173...
powershell -Command "Get-NetTCPConnection -LocalPort 4000, 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

REM ── Set workspace-isolated environment variables ──
set "HOUMI_APP_DIR=%~dp0"
set "HOUMI_WORKSPACE_DIR=%~dp0"
set "HOUMI_FRONTEND_DIST=%~dp0frontend\dist"
set "HOUMI_DATA_DIR=%~dp0data"
set "HOUMI_HOST=127.0.0.1"
set "HOUMI_PORT=4000"

echo [*] Workspace Root:  %~dp0
echo [*] Backend Engine:  %~dp0backend
echo [*] Data & DB Path:  %~dp0data
echo.
echo [*] Starting Python AI Backend (:4000)...
if exist "%~dp0backend\.venv\Scripts\activate.bat" (
    start "Houmi v1.0.5 Backend" cmd /c "cd /d "%~dp0" && set HOUMI_APP_DIR=%~dp0&& set HOUMI_WORKSPACE_DIR=%~dp0&& set HOUMI_DATA_DIR=%~dp0data&& set PYTHONPATH=%~dp0backend;%~dp0&& "%~dp0backend\.venv\Scripts\activate.bat" && uvicorn app.main:app --host 127.0.0.1 --port 4000 --reload"
) else (
    start "Houmi v1.0.5 Backend" cmd /c "cd /d "%~dp0" && set HOUMI_APP_DIR=%~dp0&& set HOUMI_WORKSPACE_DIR=%~dp0&& set HOUMI_DATA_DIR=%~dp0data&& set PYTHONPATH=%~dp0backend;%~dp0&& "%~dp0..\..\backend\.venv\Scripts\activate.bat" && uvicorn app.main:app --host 127.0.0.1 --port 4000 --reload"
)

echo [*] Launching Tauri v2 Dev Window (Vite :5173 + Rust WebView)...
cd /d "%~dp0frontend"
call npm run tauri dev

exit /b 0
