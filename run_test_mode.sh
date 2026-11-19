#!/usr/bin/env bash
# ==============================================================================
# RiceVision HMI - TEST MODE Launcher (Simulation)
# Launches Modbus Slave Simulator (port 5020) and Server (port 11111, FBARX_SIM=1)
# ==============================================================================
set -Eeuo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "========================================================"
echo "  Starting RiceVision HMI in TEST MODE (Simulation)"
echo "  Server Port: 11111 | Slave Simulator: Port 5020"
echo "========================================================"

# Check venv
if [[ -f "$APP_DIR/venv/bin/activate" ]]; then
    source "$APP_DIR/venv/bin/activate"
fi

export HMI_AUTH="${HMI_AUTH:-admin:admin123}"

# Release ports 5020 and 11111 if already in use
fuser -k 5020/tcp 2>/dev/null || true
fuser -k 11111/tcp 2>/dev/null || true
pkill -f "modbus_slave_sim.py" 2>/dev/null || true
sleep 0.5

# Run via PM2 if available, else direct background processes
if command -v pm2 >/dev/null 2>&1; then
    pm2 delete fbarx-slave-sim ricevision 2>/dev/null || true
    echo "1. Starting Modbus Slave Simulator on TCP port 5020..."
    pm2 start modbus_slave_sim.py --name "fbarx-slave-sim" --restart-delay 1000 --interpreter python3 -- --port 5020
    sleep 1
    echo "2. Starting RiceVision Server on port 11111 (FBARX_SIM=1)..."
    FBARX_PORT="socket://127.0.0.1:5020" FBARX_SIM=1 pm2 start server.py --name "ricevision" --restart-delay 1000 --interpreter python3 -- --port 11111
    pm2 status
else
    echo "Starting RiceVision Server on port 11111 (FBARX_SIM=1)..."
    export FBARX_SIM=1
    python3 server.py --port 11111
fi
