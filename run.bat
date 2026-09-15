@echo off
title Optech WhatsApp Quotation System
echo ========================================================
echo        OPTECH WHATSAPP QUOTATION AUTOMATION SYSTEM
echo ========================================================
echo.
cd /d "%~dp0"

echo [1/2] Checking and installing required Python packages...
pip install -r requirements.txt

echo.
echo [2/2] Starting Web Server & Quotation Bot on http://localhost:8000 ...
echo.
echo Open your browser and visit: http://localhost:8000
echo Press Ctrl+C in this window to stop the server anytime.
echo ========================================================
echo.

python app.py
pause
