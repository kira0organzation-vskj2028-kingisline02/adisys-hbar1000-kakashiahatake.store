#!/usr/bin/env bash
# ==============================================================================
# RiceVision HMI - PRODUCTION MODE Launcher (Physical Hardware)
# Runs without simulation (FBARX_SIM=0) connected to RS-485 serial hardware
# ==============================================================================
set -Eeuo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "========================================================"
echo "  Starting RiceVision HMI in PRODUCTION MODE"
echo "  Server Port: 11111 | FBARX_SIM=0 (Physical RMV14_1)"
echo "========================================================"

# Check venv
if [[ -f "$APP_DIR/venv/bin/activate" ]]; then
    source "$APP_DIR/venv/bin/activate"
fi

export HMI_AUTH="${HMI_AUTH:-admin:admin123}"

export FBARX_SIM=0
export PORT=11111

# Release port 11111 and 5020 if already bound
fuser -k 11111/tcp 2>/dev/null || true
fuser -k 5020/tcp 2>/dev/null || true
pkill -f "modbus_slave_sim.py" 2>/dev/null || true
sleep 0.5

# Run via PM2 if available, else direct execution
if command -v pm2 >/dev/null 2>&1; then
    pm2 delete fbarx-slave-sim 2>/dev/null || true
    pm2 delete ricevision 2>/dev/null || true
    echo "Starting RiceVision Server under PM2 on port 11111 (FBARX_SIM=0)..."
    FBARX_SIM=0 pm2 start server.py --name "ricevision" --restart-delay 1000 --interpreter python3 -- --port 11111
    pm2 status
else
    echo "Starting RiceVision Server on port 11111 (FBARX_SIM=0)..."
    python3 server.py --port 11111
fi
