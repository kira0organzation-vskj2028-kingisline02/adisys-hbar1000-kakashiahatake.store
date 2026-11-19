@echo off
title RiceVision HMI - TEST MODE (Simulation)
echo ========================================================
echo   Starting RiceVision HMI in TEST MODE (Simulated Hardware)
echo   Port: 11111  ^|  FBARX_SIM=1 (Virtual Modbus Board)
echo ========================================================
cd /d "%~dp0"

:: Activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    echo Activating Python virtual environment...
    call venv\Scripts\activate.bat
)

:: Set environment variables for test/simulation mode
set FBARX_SIM=1
set PORT=11111
if "%HMI_AUTH%"=="" set HMI_AUTH=admin:admin123

:: Start server in background
echo Launching RiceVision server in TEST MODE on port 11111...
start "RiceVision Server [TEST MODE]" python server.py --port 11111

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
