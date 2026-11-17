# RiceVision HMI - Launch in PRODUCTION MODE (Physical Hardware)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Starting RiceVision HMI in PRODUCTION MODE" -ForegroundColor Green
Write-Host "  Port: 11111 | FBARX_SIM=0 (Physical RMV14_1 Active)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

# Activate venv if present
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Activating Python virtual environment..." -ForegroundColor Yellow
    . .\venv\Scripts\Activate.ps1
}

$env:FBARX_SIM = "0"
$env:PORT = "11111"
if (-not $env:FBARX_PORT) {
    $env:FBARX_PORT = "COM9"
}

Write-Host "RS-485 Hardware Port: $env:FBARX_PORT" -ForegroundColor Cyan
Write-Host "Starting server on http://localhost:11111 ..." -ForegroundColor Green
Start-Process python -ArgumentList "server.py --port 11111"

Start-Sleep -Seconds 2

# Open browser
if (Get-Command msedge -ErrorAction SilentlyContinue) {
    Start-Process msedge -ArgumentList "--app=http://localhost:11111/ --window-size=800,480"
} elseif (Get-Command chrome -ErrorAction SilentlyContinue) {
    Start-Process chrome -ArgumentList "--app=http://localhost:11111/ --window-size=800,480"
} else {
    Start-Process "http://localhost:11111/"
}
