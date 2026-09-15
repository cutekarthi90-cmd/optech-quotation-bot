@echo off
title Optech Cloud Sync Utility
echo ========================================================
echo        OPTECH QUOTATION BOT - CLOUD SYNC
echo ========================================================
echo.
cd /d "%~dp0"
python sync_to_cloud.py
echo.
pause
