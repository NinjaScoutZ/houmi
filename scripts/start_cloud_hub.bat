@echo off
title DOBKLE Cloud AI Hub - Host Server
cd /d "%~dp0\.."

echo ======================================================================
echo    Starting DOBKLE Cloud Hub Server on your PC...
echo ======================================================================

set "PATH=%LOCALAPPDATA%\agy\bin;%PATH%"

python scripts\start_cloud_hub.py --host 0.0.0.0 --port 4000 --tunnel

pause
