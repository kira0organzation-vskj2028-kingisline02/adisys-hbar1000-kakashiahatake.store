@echo off
title RiceVision HMI Launcher
echo ========================================================
echo   Starting RiceVision HMI on Windows (Port 11111)
echo ========================================================
cd /d "%~dp0"

:: Activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    echo Activating Python virtual environment...
    call venv\Scripts\activate.bat
)

:: Check for mode argument (%1): test (default) or prod
set MODE=%1
if "%MODE%"=="" set MODE=test

if /I "%MODE%"=="prod" (
    echo [MODE] Running in PRODUCTION MODE with physical hardware...
    set FBARX_SIM=0
) else (
    echo [MODE] Running in TEST MODE with virtual board simulation...
    set FBARX_SIM=1
)

set PORT=11111

:: Start server in background
echo Launching server on port 11111...
start "RiceVision Server [%MODE%]" python server.py --port 11111

:: Wait 2 seconds for server to start
timeout /t 2 /nobreak >nul

:: Launch Edge or Chrome in 800x480 HMI App Mode
echo Opening HMI at http://localhost:11111/ in App Mode...
where msedge >nul 2>&1
if %errorlevel% equ 0 (
    start msedge --app=http://localhost:11111/ --window-size=800,480
    exit /b
)

where chrome >nul 2>&1
if %errorlevel% equ 0 (
    start chrome --app=http://localhost:11111/ --window-size=800,480
    exit /b
)

start http://localhost:11111/
exit /b
