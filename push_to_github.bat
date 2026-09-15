@echo off
title Push Optech Bot to GitHub
cd /d "%~dp0"
echo ========================================================
echo        PUSHING CODE TO GITHUB REPOSITORY
echo ========================================================
echo.
git push -u origin main
echo.
if %ERRORLEVEL% EQU 0 (
    echo ========================================================
    echo  [SUCCESS] All files uploaded to GitHub successfully!
    echo ========================================================
) else (
    echo ========================================================
    echo  [NOTE] If GitHub asks to sign in, click 'Sign in with your browser'.
    echo ========================================================
)
echo.
pause
