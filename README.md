# RiceVision HMI & FBAR 1000 Dual-Station System

Dual-station industrial control and automated optical inspection (AOI) Human-Machine Interface for woven sack, poly-bag, and flexible rice bag conversion lines.

---

## 📁 Project Directory Structure

```text
├── server.py                   # Main HTTP/WebSocket HMI backend server (port 11111)
├── fbarx_link.py               # Modbus RS-485 serial communication layer
├── fbarx_api.py                # HTTP API endpoints for /api/fbarx/*
├── camera.py                   # Camera acquisition driver (Laptop webcam / Picamera2)
├── vision.py                   # AOI computer vision & SIFT pattern matching
├── modbus_slave_sim.py         # Standalone Modbus RTU/TCP slave simulator (port 5020)
├── rice_vision.db              # Active SQLite database (WAL mode)
├── schema.sql                  # Database schema definitions
├── requirements.txt            # Python dependencies
│
├── static/                     # Industrial Touchscreen Single-Page Application (SPA)
│   └── index.html              # Clean HMI interface (0 localStorage references)
├── images/                     # Reference bag templates and operator photos
├── captures/                   # Inspection camera captures & verify frames
│
├── tests/                      # Dedicated test suites (16 test suites, 87+ tests)
│   ├── test_tension_and_security.py       # STN 1 Tension sync, Kp gain, HTTP basic auth
│   ├── test_stn2_calibrate_requirements.py# STN 2 Calibration parameters 1-16
│   ├── test_m1_m19_requirements.py        # Main screen requirements M1-M19
│   ├── test_turn12_requirements.py        # Repeat length 100-2000, 200ms polling
│   ├── test_stream_no_flicker.py          # Zero-flicker camera stream tests
│   ├── test_bag_accuracy.py               # Bag dimension & optical working distance
│   └── ...
│
├── deploy/                     # Deployment configurations & templates
│   ├── nginx_site.conf         # TLS 1.3 reverse proxy (443 -> 11111, 80 -> 443)
│   ├── ricevision.service      # Systemd service unit (port 11111)
│   ├── setup_ubuntu.sh         # Automated Ubuntu setup script
│   └── ecosystem.config.js     # PM2 process configuration
│
├── docs/                       # Comprehensive documentation
│   ├── installation.md         # Full installation & troubleshooting guide
│   ├── funtional.md            # Complete functional specification
│   ├── new_changes.md          # Architectural changes & register mapping log
│   ├── deploy_ubuntu_cloudflare.md # Cloudflare tunnel & Nginx deployment guide
│   └── screenshots/            # Verification captures & test artifacts
│
├── scripts/                    # Database inspection & maintenance utilities
│   ├── inspect_db.py
│   ├── update_db_bag_specs.py
│   └── verify_fixes.py
│
└── archive/                    # Archived legacy database files
```

---

## 🚀 Separate Run Commands: Test Mode vs Production Mode

### 1. Windows

| Mode | Command (Batch) | Command (PowerShell) | Description |
| :--- | :--- | :--- | :--- |
| **TEST MODE** (Simulation) | `.\run_test_mode.bat` | `.\run_test_mode.ps1` | Sets `FBARX_SIM=1`, runs virtual board on port 11111, launches Touchscreen App mode. |
| **PRODUCTION MODE** (Hardware) | `.\run_production_mode.bat` | `.\run_production_mode.ps1` | Sets `FBARX_SIM=0`, connects to physical RS-485 serial hardware (`COM9`), port 11111. |

*Or via PowerShell one-liner:*
```powershell
# Test Mode (Simulation)
$env:FBARX_SIM="1"; python server.py --port 11111

# Production Mode (Physical Hardware)
$env:FBARX_SIM="0"; python server.py --port 11111
```

---

### 2. Ubuntu / Linux

| Mode | One-Click Script | PM2 Unified Command | Description |
| :--- | :--- | :--- | :--- |
| **TEST MODE** (Simulation) | `./run_test_mode.sh` | `./run_ubuntu.sh test` | Launches Modbus Slave Simulator (port 5020) + Server (port 11111, `FBARX_SIM=1`). |
| **PRODUCTION MODE** (Hardware) | `./run_production_mode.sh` | `./run_ubuntu.sh prod` | Launches Server (port 11111, `FBARX_SIM=0`) connected to RS-485 (`/dev/ttyUSB0`). |

#### Management Commands:
```bash
./run_ubuntu.sh status     # Check PM2 service health
./run_ubuntu.sh logs       # Stream real-time logs
./run_ubuntu.sh restart    # Restart services
./run_ubuntu.sh stop       # Stop all running services
```

---

## 🔒 Nginx Reverse Proxy (Port 443 $\to$ 11111)

In production, Nginx handles TLS 1.3 encryption on port 443 and reverse-proxies directly to the RiceVision application running on port 11111:

```nginx
# HTTP Port 80 -> Redirects to HTTPS Port 443
server {
    listen 80;
    server_name kakashihatake.store adisys.kakashihatake.store;
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS Port 443 -> Forwards to Backend Port 11111
server {
    listen 443 ssl http2;
    server_name kakashihatake.store adisys.kakashihatake.store;

    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_certificate /etc/letsencrypt/live/adisys.kakashihatake.store/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/adisys.kakashihatake.store/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:11111;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 86400s;
    }
}
```

*Deploying Nginx config on Ubuntu:*
```bash
sudo cp nginx_site.conf /etc/nginx/sites-available/ricevision
sudo ln -sf /etc/nginx/sites-available/ricevision /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 🧪 Running Automated Tests

Run the master test runner from the project root:
```bash
# Run core requirement test suites (87 tests)
python run_tests.py

# Run all test suites including browser integration
python run_tests.py --all

# Run a specific test suite
python run_tests.py test_m1_m19_requirements
```

Or using standard `unittest`:
```bash
python -m unittest discover -s tests
```

---

## 📖 Detailed Documentation

- **[Installation Guide](file:///docs/installation.md)**: Hardware wiring, camera configuration, and operating systems.
- **[Functional Specification](file:///docs/funtional.md)**: Complete system design, Modbus register map, PID formulas.
- **[Cloudflare & Deployment Guide](file:///docs/deploy_ubuntu_cloudflare.md)**: Zero Trust tunnel setup and automated Let's Encrypt certificate renewals.
- **[Architectural Changes Log](file:///docs/new_changes.md)**: Complete register validation and security verification log.
