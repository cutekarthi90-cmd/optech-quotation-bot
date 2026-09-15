@echo off
title Setup Optech 30-Min Auto Sync Task Scheduler
cd /d "%~dp0"
echo ========================================================
echo   SETTING UP OPTECH AUTO-SYNC TASK SCHEDULER (30 MINS)
echo ========================================================
echo.

schtasks /create /tn "OptechAutoSync30Min" /tr "\"C:\Users\WIN\AppData\Local\Python\bin\python.exe\" \"%~dp0auto_sync_30min.py\"" /sc minute /mo 30 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo  [SUCCESS] Task Scheduler successfully configured!
    echo  Sync will run automatically every 30 minutes.
    echo ========================================================
) else (
    echo.
    echo  [ERROR] Please right-click this file and select 'Run as administrator'.
)
echo.
pause
