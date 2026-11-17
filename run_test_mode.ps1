# RiceVision HMI - Launch in TEST MODE (Simulated Hardware)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Starting RiceVision HMI in TEST MODE (Simulation)" -ForegroundColor Cyan
Write-Host "  Port: 11111 | FBARX_SIM=1 (Virtual Board Active)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# Activate venv if present
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Activating Python virtual environment..." -ForegroundColor Yellow
    . .\venv\Scripts\Activate.ps1
}

$env:FBARX_SIM = "1"
$env:PORT = "11111"

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
