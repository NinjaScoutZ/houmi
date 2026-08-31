@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.5 (Desktop Studio - 100% Workspace Isolated)
color 0B

echo ===============================================================================
echo        HOUMI STUDIO v1.0.5 - 100%% WORKSPACE ISOLATED RUNTIME + AI ENGINE
echo ===============================================================================
echo.

cd /d "%~dp0"

echo [*] Freeing ports 4000, 4001, 5173...
powershell -Command "Get-NetTCPConnection -LocalPort 4000, 4001, 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

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
echo [*] PSD CLI Path:    %~dp0bin\houmi-psd-cli.exe
REM ── Guard: Ensure authentic UI bundle is locked and preserved ──
if not exist "%~dp0frontend\dist\index.html" (
    if exist "%~dp0frontend\dist_golden_backup" (
        xcopy /E /Y /I "%~dp0frontend\dist_golden_backup\*" "%~dp0frontend\dist\" >nul 2>&1
    )
)

echo [*] [1/2] Starting Python Local AI Engine & Real-Time Debug Console...
echo [*] [2/2] Launching Native GPU-Accelerated Desktop Studio Window...
echo.

if exist "%~dp0backend\.venv\Scripts\python.exe" (
    start "Houmi Studio v1.0.5" /D "%~dp0" "%~dp0backend\.venv\Scripts\python.exe" "%~dp0run_desktop.py"
) else if exist "%~dp0..\..\backend\.venv\Scripts\python.exe" (
    start "Houmi Studio v1.0.5" /D "%~dp0" "%~dp0..\..\backend\.venv\Scripts\python.exe" "%~dp0run_desktop.py"
) else (
    start "Houmi Studio v1.0.5" /D "%~dp0" python.exe "%~dp0run_desktop.py"
)

echo [*] Houmi Studio v1.0.5 Launched Successfully from %~dp0!
timeout /t 3 >nul
exit /b 0
