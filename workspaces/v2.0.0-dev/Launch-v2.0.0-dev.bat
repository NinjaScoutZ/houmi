@echo off
chcp 65001 >nul
title HOUMI STUDIO v2.0.0 (Next-Gen Production Desktop Studio)
color 0E

echo ===============================================================================
echo            HOUMI STUDIO v2.0.0 - NEXT-GEN STUDIO (Desktop Runtime)
echo    (Photoshop Balloon Workflow, 100%% True Center Rotation, 15 Snap, 0 Ghost)
echo ===============================================================================
echo.

cd /d "%~dp0..\.."

echo [*] Freeing ports 4000, 5173...
powershell -Command "Get-NetTCPConnection -LocalPort 4000, 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [*] Deploying v2.0.0 frontend bundle...
xcopy /E /Y /I "%~dp0frontend\dist\*" "frontend\dist\" >nul
xcopy /E /Y /I "%~dp0frontend\dist\*" "data\patches\current\frontend\dist\" >nul

echo [*] [1/2] Starting Python Local AI Engine & Real-Time Debug Console...
echo [*] [2/2] Launching Native GPU-Accelerated Desktop Studio Window...
echo.

if exist "%~dp0backend\.venv\Scripts\python.exe" (
    start "Houmi Studio v2.0.0" "%~dp0backend\.venv\Scripts\python.exe" run_desktop.py
) else if exist "backend\.venv\Scripts\python.exe" (
    start "Houmi Studio v2.0.0" "backend\.venv\Scripts\python.exe" run_desktop.py
) else (
    start "Houmi Studio v2.0.0" python.exe run_desktop.py
)

echo [*] Houmi Studio v2.0.0 Launched Successfully!
timeout /t 3 >nul
exit /b 0
