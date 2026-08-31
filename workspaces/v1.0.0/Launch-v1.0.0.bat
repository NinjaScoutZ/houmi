@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.0 (Classic Stable)
color 07

echo ===============================================================================
echo              HOUMI STUDIO v1.0.0 - CLASSIC STABLE (Python Desktop)
echo ===============================================================================
echo.

cd /d "%~dp0..\.."
echo [*] Deploying v1.0.0 frontend bundle...
xcopy /E /Y /I "%~dp0frontend\dist\*" "frontend\dist\" >nul

echo [*] Starting Houmi v1.0.0 Desktop Window...
if exist "%~dp0backend\.venv\Scripts\python.exe" (
    start "Houmi v1.0.0" "%~dp0backend\.venv\Scripts\python.exe" run_desktop.py
) else if exist "backend\.venv\Scripts\python.exe" (
    start "Houmi v1.0.0" "backend\.venv\Scripts\python.exe" run_desktop.py
) else (
    start "Houmi v1.0.0" python.exe run_desktop.py
)

echo [*] v1.0.0 Launched!
timeout /t 3 >nul
exit /b 0
