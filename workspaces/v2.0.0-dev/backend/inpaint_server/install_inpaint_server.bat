@echo off
title "HOUMI STUDIO - GPU Inpaint Server Setup (PyTorch CUDA and Big-LaMa)"
cd /d "%~dp0"

echo ==========================================================================
echo  HOUMI STUDIO - GPU Inpaint Server Setup (PyTorch CUDA and Big-LaMa)
echo ==========================================================================
echo.
echo  This script sets up the dedicated GPU Inpaint Server for Houmi Studio.
echo  It will enable lightning-fast (0.3s/page) neural inpainting on NVIDIA GPUs.
echo.
echo  Requirements:
echo   - Windows 10/11 64-bit
echo   - NVIDIA GPU (GTX 1650, RTX 2060/3060/4060 or higher)
echo   - Python 3.9 - 3.13 installed
echo.
echo ==========================================================================
echo.

set PYTHON_EXE=python

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH!
    echo Please install Python from python.org and check "Add Python to PATH".
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
echo [2/3] Installing PyTorch CUDA and dependencies...
%VENV_PYTHON% -m pip install --upgrade pip

echo Installing PyTorch CUDA for Windows (cu124 / cu121 / PyPI)...
%VENV_PIP% install torch torchvision --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo Retrying PyTorch CUDA 12.1 install...
    %VENV_PIP% install torch torchvision --index-url https://download.pytorch.org/whl/cu121
)
if errorlevel 1 (
    echo Retrying PyTorch PyPI install...
    %VENV_PIP% install torch torchvision
)

%VENV_PIP% install bottle pillow numpy opencv-python-headless requests

echo.
echo ==========================================================================
echo  [3/3] Setup complete! Starting GPU Inpaint Server on port 2328...
echo ==========================================================================
echo.
%VENV_PYTHON% server.py
pause
