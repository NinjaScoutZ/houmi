@echo off
chcp 65001 >nul
title HOUMI STUDIO v1.0.5 (Tauri v2 - Interactive Debug Mode)
color 0E

echo ===============================================================================
echo        HOUMI STUDIO v1.0.5 - TAURI v2 NATIVE DEBUG CONSOLE + DEVTOOLS
echo ===============================================================================
echo.

cd /d "%~dp0"

echo [*] Freeing ports 4000, 4001, 5173 and clearing WebView2 cache...
powershell -Command "Get-NetTCPConnection -LocalPort 4000, 4001, 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Remove-Item \"$HOME\.houmi\webview_*\" -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item \"$env:LOCALAPPDATA\com.houmi.studio\" -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item \"$env:LOCALAPPDATA\EBWebView\" -Recurse -Force -ErrorAction SilentlyContinue" >nul 2>&1

set "HOUMI_APP_DIR=%~dp0"
set "HOUMI_WORKSPACE_DIR=%~dp0"
set "HOUMI_FRONTEND_DIST=%~dp0frontend\dist"
set "HOUMI_DATA_DIR=%~dp0data"
set "HOUMI_HOST=127.0.0.1"
set "HOUMI_PORT=4000"
set "HOUMI_DEBUG=1"
set "PRODUCTION_MODE=0"
set "RUST_LOG=debug"
set "RUST_BACKTRACE=1"

echo [*] Launching Native Tauri v2 Debug Binary with DevTools attached...
echo [*] Streaming Real-Time Rust Host + Python AI Engine Logs below:
echo.

"%~dp0frontend\src-tauri\target\debug\houmi-studio.exe"

echo.
echo [*] Tauri Studio window closed.
pause
