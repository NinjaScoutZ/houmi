@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.5 - FULLSTACK DEV SERVER
color 0A

echo ===============================================================================
echo        HOUMI STUDIO v1.0.5 - 100%% WORKSPACE ISOLATED DEV SERVER
echo        (Backend :4000 + Vite :5173 with HMR)
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
echo [*] [1/2] Starting Python AI Backend (:4000)...
if exist "%~dp0backend\.venv\Scripts\activate.bat" (
    start "Houmi v1.0.5 Backend" cmd /c "cd /d "%~dp0" && set HOUMI_APP_DIR=%~dp0&& set HOUMI_WORKSPACE_DIR=%~dp0&& set HOUMI_DATA_DIR=%~dp0data&& set PYTHONPATH=%~dp0backend;%~dp0&& "%~dp0backend\.venv\Scripts\activate.bat" && uvicorn app.main:app --host 127.0.0.1 --port 4000 --reload"
) else (
    start "Houmi v1.0.5 Backend" cmd /c "cd /d "%~dp0" && set HOUMI_APP_DIR=%~dp0&& set HOUMI_WORKSPACE_DIR=%~dp0&& set HOUMI_DATA_DIR=%~dp0data&& set PYTHONPATH=%~dp0backend;%~dp0&& "%~dp0..\..\backend\.venv\Scripts\activate.bat" && uvicorn app.main:app --host 127.0.0.1 --port 4000 --reload"
)

echo [*] [2/2] Starting Vite Frontend Dev Server (:5173)...
cd /d "%~dp0frontend"
start "Houmi v1.0.5 Frontend" cmd /c "npm run dev"

echo [*] Fullstack dev servers starting...
echo [*] Frontend: http://127.0.0.1:5173
echo [*] Backend:  http://127.0.0.1:4000
timeout /t 5 >nul

start http://127.0.0.1:5173
exit /b 0
