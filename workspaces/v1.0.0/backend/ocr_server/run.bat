@echo off
cd /d "%~dp0"

echo ========================================
echo Hybrid OCR Direct Server
echo ========================================
echo.

REM Set CUDA device (use GPU 0 by default)
set CUDA_VISIBLE_DEVICES=0

REM Check if Python is available (prefer venv)
if exist venv\Scripts\python.exe (
    set PYTHON_EXE=venv\Scripts\python.exe
    echo [INFO] Using virtual environment Python.
) else (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found! Please install Python 3.9 or higher or setup venv.
        pause
        exit /b 1
    )
    set PYTHON_EXE=python
    echo [INFO] Using global system Python.
)

echo [INFO] Starting hybrid OCR direct server...
echo [INFO] Server will be available at: http://127.0.0.1:2322
echo [INFO] Auto mode prefers GLM on this Windows CUDA machine for stability.
echo [INFO] Set OCR_BACKEND=deepseek if you want to force DeepSeek again.
echo [INFO] Press Ctrl+C to stop the server
echo.

REM Enable pre-loading model at startup
set PRELOAD_MODEL=true
set DEEPSEEK_OCR_MODEL=deepseek-ai/DeepSeek-OCR-2
set GLM_OCR_MODEL=zai-org/GLM-OCR
set LOAD_IN_4BIT=true
if "%OCR_BACKEND%"=="" set OCR_BACKEND=auto

%PYTHON_EXE% server.py

pause
