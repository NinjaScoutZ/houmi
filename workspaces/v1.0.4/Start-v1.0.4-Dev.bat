@echo off
chcp 65001 >nul
title v1.0.4 - Fullstack Dev (Backend :4000 + Frontend :5173)
color 0B

echo ===============================================================================
echo      v1.0.4 FULLSTACK DEV: BACKEND (PORT 4000) + FRONTEND (PORT 5173)
echo ===============================================================================
echo.

echo [*] Starting Backend Server on http://127.0.0.1:4000 ...
start "Houmi v1.0.4 Backend API" cmd /k "cd /d %~dp0backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 4000"

echo [*] Starting Vite Hot-Reload UI on http://127.0.0.1:5173 ...
cd /d "%~dp0frontend"
call npm run dev -- --host 127.0.0.1 --port 5173
pause
