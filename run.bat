@echo off
chcp 65001 >nul
title AutoProxy - Tool Lay Proxy Tu Dong
cd /d "%~dp0"

echo ========================================================
echo         TOOL TU DONG LAY PROXY TU WEBSHARE
echo ========================================================
echo.

:: Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python tren may tinh cua ban!
    echo Vui long cai dat Python tai https://www.python.org/ va tich chon "Add Python to PATH".
    echo.
    pause
    exit /b
)

:: Chay tool chinh ngay lap tuc
echo [*] Dang khoi dong tool...
echo.
python main.py

echo.
echo ========================================================
echo [HOAN TAT] Nhan phim bat ky de thoat...
echo ========================================================
pause >nul
