@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.4 (Desktop Studio Launcher)
color 03

echo ===============================================================================
echo              HOUMI STUDIO v1.0.4 - DESKTOP STUDIO
echo   (100%% Identical Engine to Desktop Shortcut: AI Backend + Native GPU Window)
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
set "PRODUCTION_MODE=1"
set "HOUMI_DISABLE_AUTO_PATCH=1"

echo [*] Workspace Root:  %~dp0
echo [*] Backend Engine:  %~dp0backend
echo [*] Data & DB Path:  %~dp0data
echo [*] Frontend Dist:   %~dp0frontend\dist
echo.
echo [*] [1/2] Starting Python Local AI Engine & Real-Time Debug Console...
echo [*] [2/2] Launching Native GPU-Accelerated Desktop Studio Window...
echo.

if exist "%~dp0backend\.venv\Scripts\python.exe" (
    start "Houmi Studio v1.0.4" /D "%~dp0" "%~dp0backend\.venv\Scripts\python.exe" "%~dp0run_desktop.py"
) else if exist "%~dp0..\..\backend\.venv\Scripts\python.exe" (
    start "Houmi Studio v1.0.4" /D "%~dp0" "%~dp0..\..\backend\.venv\Scripts\python.exe" "%~dp0run_desktop.py"
) else (
    start "Houmi Studio v1.0.4" /D "%~dp0" python.exe "%~dp0run_desktop.py"
)

echo [*] Houmi Studio v1.0.4 Launched Successfully from %~dp0!
timeout /t 3 >nul
exit /b 0
