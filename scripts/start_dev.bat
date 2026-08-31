@echo off
title Houmi Dev Server Launcher
echo ===================================================
echo             Houmi - Manga Translator Studio
echo ===================================================
echo.
echo  [1] Start Backend + [MAIN FRONTEND] (Port 5173)
echo  [2] Start Backend + [OLD BACKUP FRONTEND] (Port 5175)
echo  [3] Start Backend + BOTH Frontends (Main :5173 + Old :5175)
echo.
set /p choice="Select option (1-3): "

if "%choice%"=="1" goto MAIN_ONLY
if "%choice%"=="2" goto OLD_ONLY
if "%choice%"=="3" goto BOTH
goto MAIN_ONLY

:MAIN_ONLY
echo [INFO] Starting Backend and Main Frontend...
start "Houmi Backend" cmd /k "cd /d %~dp0..\backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 4000"
start "Houmi Main Frontend" cmd /k "cd /d %~dp0..\frontend && npm.cmd run dev -- --port 5173"
goto DONE

:OLD_ONLY
echo [INFO] Starting Backend and Old Backup Frontend...
start "Houmi Backend" cmd /k "cd /d %~dp0..\backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 4000"
start "Houmi Old Backup Frontend" cmd /k "cd /d %~dp0..\frontend_old && npm.cmd run dev -- --port 5175"
goto DONE

:BOTH
echo [INFO] Starting Backend and Both Frontends...
start "Houmi Backend" cmd /k "cd /d %~dp0..\backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 4000"
start "Houmi Main Frontend" cmd /k "cd /d %~dp0..\frontend && npm.cmd run dev -- --port 5173"
start "Houmi Old Backup Frontend" cmd /k "cd /d %~dp0..\frontend_old && npm.cmd run dev -- --port 5175"
goto DONE

:DONE
echo.
echo [SUCCESS] Servers launched!
echo - Backend: http://127.0.0.1:4000
echo - Main Frontend: http://localhost:5173
echo - Old Backup Frontend: http://localhost:5175
echo.
pause
