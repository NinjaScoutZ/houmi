@echo off
title HOUMI STUDIO — Local GLM / DeepSeek VLM Server Setup
cd /d "%~dp0"

echo ==========================================================================
echo  HOUMI STUDIO — Local VLM Server Setup (GLM-4V & DeepSeek-OCR PyTorch)
echo ==========================================================================
echo.
echo  This script will set up the Python virtual environment and dependencies
echo  required to run the real PyTorch GLM-4V / DeepSeek-OCR VLM Server locally.
echo.
echo  Requirements:
echo   - Windows 10/11 64-bit
echo   - NVIDIA CUDA GPU (8GB+ VRAM recommended)
echo   - Python 3.9 - 3.11 installed
echo.
echo ==========================================================================
echo.

set PYTHON_EXE=python

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH!
    echo Please install Python 3.10 from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/3] Creating Python virtual environment in %CD%\venv ...
if not exist venv (
    %PYTHON_EXE% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment folder already exists.
)

set VENV_PYTHON=venv\Scripts\python.exe
set VENV_PIP=venv\Scripts\pip.exe

echo.
echo [2/3] Installing PyTorch with CUDA support and dependencies...
%VENV_PYTHON% -m pip install --upgrade pip
%VENV_PIP% install torch torchvision --index-url https://download.pytorch.org/whl/cu121
%VENV_PIP% install -r requirements.txt

if errorlevel 1 (
    echo [WARNING] PyTorch CUDA installation encountered issues. Retrying CPU/Standard wheels...
    %VENV_PIP% install -r requirements.txt
)

echo.
echo ==========================================================================
echo  [3/3] Launching Local VLM Server on port 2322...
echo ==========================================================================
echo.

%VENV_PYTHON% server.py

pause
