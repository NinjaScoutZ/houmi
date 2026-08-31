@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.4 (Tauri v2 Dev Mode)
color 0B

echo ===============================================================================
echo           HOUMI STUDIO v1.0.4 - TAURI v2 DEV (CARGO + HOT-RELOAD)
echo ===============================================================================
echo.

echo [*] Starting Backend API in background...
start "Houmi Backend" cmd /c "cd /d %~dp0backend && .venv\Scripts\activate && uvicorn app.main:app --port 4000"

cd /d "%~dp0frontend"
echo [*] Starting Tauri v2 dev shell...
call npm run tauri dev
pause
