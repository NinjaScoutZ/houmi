@echo off
title HOUMI STUDIO — GPU Inpaint Server
cd /d "%~dp0"

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe server.py
) else (
    python server.py
)
