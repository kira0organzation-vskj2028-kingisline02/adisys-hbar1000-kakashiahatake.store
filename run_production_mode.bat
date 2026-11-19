@echo off
title RiceVision HMI - PRODUCTION MODE (Physical Hardware)
echo ========================================================
echo   Starting RiceVision HMI in PRODUCTION MODE
echo   Port: 11111  ^|  FBARX_SIM=0 (Physical RMV14_1 Board)
echo ========================================================
cd /d "%~dp0"

:: Activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    echo Activating Python virtual environment...
    call venv\Scripts\activate.bat
)

:: Set environment variables for production mode (SIMULATION STRICTLY OFF)
set FBARX_SIM=0
set PORT=11111
if "%HMI_AUTH%"=="" set HMI_AUTH=admin:admin123

:: If serial port not specified in environment, default to auto-detect / COM9
if "%FBARX_PORT%"=="" (
    set FBARX_PORT=COM9
)

echo RS-485 Hardware Port: %FBARX_PORT%
echo Launching RiceVision server on port 11111...
start "RiceVision Server [PRODUCTION]" python server.py --port 11111

:: Wait 2 seconds for server socket to initialize
timeout /t 2 /nobreak >nul

:: Launch Edge or Chrome in 800x480 HMI Touchscreen App Mode
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
