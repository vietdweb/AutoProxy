@echo off
chcp 65001 >nul
title AutoProxy - Web Dashboard Local Test
cd /d "%~dp0"

echo ========================================================
echo         AUTOPROXY - WEB DASHBOARD LOCAL TEST
echo ========================================================
echo.
echo [*] Dang khoi dong Web Server tai: http://localhost:8000
echo [*] Mo trinh duyet tu dong...
echo.

start "" http://localhost:8000
python web_server.py

pause >nul
