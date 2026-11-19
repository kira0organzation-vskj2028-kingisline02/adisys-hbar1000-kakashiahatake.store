#!/usr/bin/env bash
# ==============================================================================
# RiceVision HMI - Ubuntu Deployment Script with Modbus Slave Simulator & PM2
# ==============================================================================
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

ACTION="${1:-start}"

log()  { printf '\n\033[1;34m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\n\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

ensure_venv_and_interpreter() {
    log "Checking Python virtual environment and dependencies..."
    if [[ ! -d "$APP_DIR/venv" ]]; then
        log "Virtual environment not found. Creating ./venv with python3..."
        python3 -m venv "$APP_DIR/venv" || die "Failed to create venv. Run: sudo apt-get install -y python3-venv"
    fi

    # Ensure ./venv/bin/python3.11 exists (symlink if venv python has another name e.g. python3)
    if [[ ! -x "$APP_DIR/venv/bin/python3.11" ]]; then
        if [[ -x "$APP_DIR/venv/bin/python3" ]]; then
            ln -sf python3 "$APP_DIR/venv/bin/python3.11"
        elif [[ -x "$APP_DIR/venv/bin/python" ]]; then
            ln -sf python "$APP_DIR/venv/bin/python3.11"
        else
            die "No python binary found in ./venv/bin!"
        fi
        log "Linked ./venv/bin/python3.11 -> $(readlink "$APP_DIR/venv/bin/python3.11")"
    fi

    # Check dependencies if needed
    if ! "$APP_DIR/venv/bin/python3.11" -c "import cv2, PIL, serial" >/dev/null 2>&1; then
        log "Installing missing requirements into venv..."
        "$APP_DIR/venv/bin/python3.11" -m pip install --upgrade pip
        "$APP_DIR/venv/bin/python3.11" -m pip install -r "$APP_DIR/requirements.txt"
    fi
}

ensure_pm2() {
    if ! command -v pm2 >/dev/null 2>&1; then
        log "pm2 is not installed. Attempting installation via npm..."
        if command -v npm >/dev/null 2>&1; then
            sudo npm install -g pm2 || npm install -g pm2 || die "Failed to install pm2."
        else
            die "pm2 is required. Please install Node.js and pm2: sudo apt-get install -y nodejs npm && sudo npm install -g pm2"
        fi
    fi
}

kill_ports_and_processes() {
    log "Releasing TCP ports 5020 and 11111..."
    fuser -k 5020/tcp 2>/dev/null || true
    fuser -k 11111/tcp 2>/dev/null || true
    pkill -f "modbus_slave_sim.py" 2>/dev/null || true
    sleep 0.5
}

start_test_services() {
    ensure_venv_and_interpreter
    ensure_pm2

    log "Cleaning up any old PM2 processes..."
    pm2 delete ricevision 2>/dev/null || true
    pm2 delete fbarx-slave-sim 2>/dev/null || true
    kill_ports_and_processes

    log "1. Starting Modbus Slave Test Simulator (fbarx-slave-sim) on TCP port 5020..."
    pm2 start modbus_slave_sim.py \
        --name "fbarx-slave-sim" \
        --restart-delay 1000 \
        --interpreter ./venv/bin/python3.11 \
        -- --port 5020

    sleep 1

    log "2. Starting RiceVision Server in TEST MODE on HTTP port 11111 (socket://127.0.0.1:5020)..."
    FBARX_PORT="socket://127.0.0.1:5020" FBARX_SIM=1 HMI_AUTH="${HMI_AUTH:-admin:admin123}" pm2 start server.py \
        --name "ricevision" \
        --restart-delay 1000 \
        --interpreter ./venv/bin/python3.11 \
        -- --port 11111

    log "Saving PM2 process list for auto-restart across reboots..."
    pm2 save || true

    log "Status:"
    pm2 status

    echo "======================================================================"
    echo " SUCCESS! TEST MODE running under PM2:"
    echo "   - Test Simulator : fbarx-slave-sim (Modbus TCP socket://127.0.0.1:5020)"
    echo "   - App Server     : ricevision (HTTP port 11111, FBARX_SIM=1)"
    echo
    echo " Local URL  : http://localhost:11111"
    echo " PM2 Logs   : pm2 logs"
    echo " PM2 Status : pm2 status"
    echo " Stop       : ./run_ubuntu.sh stop"
    echo " Restart    : ./run_ubuntu.sh restart"
    echo "======================================================================"
}

start_prod_services() {
    ensure_venv_and_interpreter
    ensure_pm2

    log "Cleaning up any old PM2 processes..."
    pm2 delete ricevision 2>/dev/null || true
    pm2 delete fbarx-slave-sim 2>/dev/null || true
    kill_ports_and_processes

    log "Starting RiceVision Server in PRODUCTION MODE on HTTP port 11111 (FBARX_SIM=0, Physical Hardware)..."
    FBARX_SIM=0 HMI_AUTH="${HMI_AUTH:-admin:admin123}" pm2 start server.py \
        --name "ricevision" \
        --restart-delay 1000 \
        --interpreter ./venv/bin/python3.11 \
        -- --port 11111

    log "Saving PM2 process list for auto-restart across reboots..."
    pm2 save || true

    log "Status:"
    pm2 status

    echo "======================================================================"
    echo " SUCCESS! PRODUCTION MODE running under PM2:"
    echo "   - App Server     : ricevision (HTTP port 11111, FBARX_SIM=0)"
    echo "   - Hardware Serial: Direct RS-485 (/dev/ttyUSB0 or auto-detected)"
    echo
    echo " Local URL  : http://localhost:11111"
    echo " PM2 Logs   : pm2 logs"
    echo " PM2 Status : pm2 status"
    echo " Stop       : ./run_ubuntu.sh stop"
    echo " Restart    : ./run_ubuntu.sh restart"
    echo "======================================================================"
}

start_services() {
    start_test_services
}

stop_services() {
    log "Stopping RiceVision & Test Simulator in PM2..."
    pm2 stop ricevision fbarx-slave-sim 2>/dev/null || true
    kill_ports_and_processes
    pm2 status
}

restart_services() {
    log "Restarting RiceVision & Test Simulator in PM2..."
    pm2 stop fbarx-slave-sim ricevision 2>/dev/null || true
    kill_ports_and_processes
    pm2 restart fbarx-slave-sim ricevision 2>/dev/null || start_services
    pm2 status
}

show_status() {
    pm2 status
}

show_logs() {
    pm2 logs --lines 50
}

case "$ACTION" in
    test|start)
        start_test_services
        ;;
    prod|production)
        start_prod_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "Usage: $0 {test|prod|start|stop|restart|status|logs}"
        echo "  - test : Start in TEST MODE (Simulated Modbus Slave on port 5020 + App on port 11111)"
        echo "  - prod : Start in PRODUCTION MODE (Physical RS-485 Hardware + App on port 11111)"
        echo "  - stop : Stop all PM2 services"
        echo "  - logs : View live service logs"
        exit 1
        ;;
esac

