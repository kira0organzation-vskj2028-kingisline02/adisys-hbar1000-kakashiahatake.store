#!/usr/bin/env bash
# ==============================================================================
# RiceVision HMI - Ubuntu 20.04 / 22.04 / 24.04 Setup Script
# Cloudflare Tunnel-friendly: the app listens on localhost:11111; Nginx is optional.
# ==============================================================================
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="${SUDO_USER:-$(id -un)}"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="ricevision"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log()  { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\nWARNING: %s\n' "$*" >&2; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Avoid installing packages unnecessarily. On systems with an already-broken
# unrelated Nginx package configuration, apt-get install can fail even when
# all dependencies required by RiceVision are already installed.
required_commands=(python3 curl)
missing_commands=()
for cmd in "${required_commands[@]}"; do
    command -v "$cmd" >/dev/null 2>&1 || missing_commands+=("$cmd")
done

package_installed() {
    local pkg status
    for pkg in "$@"; do
        status="$(dpkg-query -W -f='${db:Status-Status}' "$pkg" 2>/dev/null || true)"
        [[ "$status" == "installed" ]] && return 0
    done
    return 1
}

required_package_groups=(
    "python3-pip"
    "python3-venv"
    "libgl1"
    "curl"
    "libglib2.0-0 libglib2.0-0t64"
)
missing_packages=()
for group in "${required_package_groups[@]}"; do
    # Each group is a space-separated list of equivalent package names.
    read -r -a alternatives <<< "$group"
    package_installed "${alternatives[@]}" || missing_packages+=("$group")
done

log "[1/5] Updating package lists and checking system dependencies"
if ! sudo apt-get update -y; then
    warn "apt-get update failed. Continuing only if all required dependencies are already installed."
fi

if ((${#missing_packages[@]} > 0)) || ((${#missing_commands[@]} > 0)); then
    log "Installing missing RiceVision dependencies: ${missing_packages[*]:-(command check)}"
    if ! sudo apt-get install -y python3 python3-pip python3-venv libgl1 libglib2.0-0 curl; then
        # Ubuntu 24.04 may use the t64 package name. Check actual availability
        # instead of treating an unrelated package post-install failure as success.
        missing_after=()
        for cmd in python3 curl; do
            command -v "$cmd" >/dev/null 2>&1 || missing_after+=("$cmd")
        done
        for group in "python3-pip" "python3-venv" "libgl1" "libglib2.0-0 libglib2.0-0t64"; do
            read -r -a alternatives <<< "$group"
            package_installed "${alternatives[@]}" || missing_after+=("$group")
        done
        if ((${#missing_after[@]} > 0)); then
            die "Dependency installation failed and required components are missing: ${missing_after[*]}. Resolve the package-manager error, then rerun this script."
        fi
        warn "apt reported an error, likely from an unrelated package's post-install step (for example, an existing Nginx configuration). RiceVision dependencies are present, so continuing."
    fi
else
    log "All required system dependencies are already installed; skipping apt-get install."
fi

command -v python3 >/dev/null 2>&1 || die "python3 is not available."
[[ -f "$APP_DIR/requirements.txt" ]] || die "Missing requirements.txt in $APP_DIR."
[[ -f "$APP_DIR/server.py" ]] || die "Missing server.py in $APP_DIR."

log "[2/5] Creating Python virtual environment"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR" || die "Could not create the virtual environment. Ensure python3-venv is installed."
fi

log "[3/5] Installing Python requirements"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

log "[4/5] Configuring systemd service"
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=RiceVision HMI Server
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/python $APP_DIR/server.py --port 11111
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

log "[5/5] Checking service status"
sleep 2
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "======================================================================"
    echo " SUCCESS! RiceVision service is active on port 11111."
    echo " Status: sudo systemctl status ricevision"
    echo " Logs:   sudo journalctl -u ricevision -f"
    echo
    echo "App URL (Nginx/Direct): http://localhost:11111"
    echo "Nginx Reverse Proxy:    https://adisys.kakashihatake.store (Port 443 -> 11111)"
    echo "======================================================================"
else
    echo "RiceVision failed to start. Recent logs:"
    sudo journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
    exit 1
fi

# Report (but do not modify) any existing Nginx problem. Other hosted sites may
# depend on those configurations, so this script deliberately doesn't disable
# or rewrite their virtual hosts or TLS certificates.
if command -v nginx >/dev/null 2>&1; then
    if ! sudo nginx -t; then
        warn "RiceVision is configured, but the existing Nginx configuration is invalid."
        warn "This script did not alter Nginx virtual hosts or certificates."
        warn "Inspect with: sudo grep -RInE 'kakashihatake\\.store|/etc/letsencrypt/live' /etc/nginx"
        warn "For Cloudflare Tunnel, route the hostname directly to http://localhost:11111 if no Nginx proxy is needed."
    fi
fi
