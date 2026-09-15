@echo off
title Optech Database Auto-Sync (Every 30 Mins)
cd /d "%~dp0"
echo ========================================================
echo   OPTECH DATABASE AUTO-SYNC TO CLOUD (EVERY 30 MINS)
echo ========================================================
echo.
echo Running automatic sync loop...
python auto_sync_30min.py --loop
pause
