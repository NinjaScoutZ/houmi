@echo off
chcp 65001 >nul
title HOUMI STUDIO - MASTER WORKSPACE SELECTOR
cls
echo ===============================================================================
echo            HOUMI TRANSLATION STUDIO - MASTER WORKSPACE SELECTOR
echo ===============================================================================
echo.
echo   [1] 🌟 v1.0.5     - Tauri v2 Native Studio + Action Debug Mode (Latest)
echo   [2] ⚡ v1.0.5     - Fullstack Dev Server (Backend :4000 + Frontend :5173)
echo   [3] 🚀 v2.0.0-dev  - Next-Gen Studio (Tauri v2 + Balloon Workflow)
echo   [4] 📦 v1.0.4     - Staging Reference
echo   [5] 🏛️ v1.0.0     - Classic Stable (Python pywebview)
echo   [6] 🛠️ Build OTA  - Build Customer Patch (houmi.click OTA)
echo.
set /p choice="Select option (1-6): "

if "%choice%"=="1" call "%~dp0workspaces\v1.0.5\Launch-v1.0.5.bat" & exit
if "%choice%"=="2" call "%~dp0workspaces\v1.0.5\Start-v1.0.5-Dev.bat" & exit
if "%choice%"=="3" call "%~dp0workspaces\v2.0.0-dev\Launch-v2.0.0-dev.bat" & exit
if "%choice%"=="4" call "%~dp0workspaces\v1.0.4\Launch-v1.0.4.bat" & exit
if "%choice%"=="5" call "%~dp0workspaces\v1.0.0\Launch-v1.0.0.bat" & exit
if "%choice%"=="6" cd /d %~dp0backend && .venv\Scripts\python.exe scripts\build_patch.py & pause & exit
echo [ERROR] Invalid selection.
pause
