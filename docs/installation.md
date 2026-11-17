# RiceVision HMI - Windows Installation & Run Guide

This guide describes how to install, configure, and run the **RiceVision HMI Phase 1** application on a **Windows 10 or Windows 11 (64-bit)** system.

---

## 1. System Requirements

* **Operating System**: Windows 10 or Windows 11 (64-bit)
* **Python**: Python 3.9, 3.10, 3.11, or 3.12 (Python 3.11+ recommended)
* **Web Browser**: Microsoft Edge, Google Chrome, or Mozilla Firefox
* **Hardware**:
  * Any modern laptop or desktop PC
  * Integrated webcam or external USB webcam (for camera bag verification)

---

## 2. Prerequisites

### Install Python (if not already installed)
1. Download Python from the official site: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
2. Run the installer.
3. **IMPORTANT**: On the first screen of the installer, check the box that says:
   `☑ Add python.exe to PATH` (or `Add Python to environment variables`).
4. Complete the installation and open a new terminal window to verify:
   ```powershell
   python --version
   ```

---

## 3. Installation Steps

### Step 1: Open PowerShell or Command Prompt
Open PowerShell or Command Prompt (`cmd.exe`) and navigate to the project directory:
```powershell
cd 
```
*(Replace the path with your actual project folder location if different).*

### Step 2: Create a Python Virtual Environment
Creating an isolated virtual environment keeps dependencies clean and prevents conflicts:
```powershell
python -m venv venv
```

### Step 3: Activate the Virtual Environment

* **In PowerShell**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  > **Note on PowerShell Security**: If you see an error saying `running scripts is disabled on this system`, allow script execution for the current process:
  > ```powershell
  > Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  > .\venv\Scripts\Activate.ps1
  > ```

* **In Command Prompt (cmd.exe)**:
  ```cmd
  venv\Scripts\activate.bat
  ```

Once activated, you will see `(venv)` at the beginning of your command prompt.

### Step 4: Upgrade Pip & Install Dependencies
Run the following command to install the required libraries:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The core libraries installed are:
* `opencv-python` (OpenCV SIFT feature detection and computer vision for bag verification)
* `numpy` (High-performance numeric array calculations for vision matrices)
* `pillow` & `pilkit` (Image format manipulation and thumbnail scaling)

### Step 5: Database Initialization
The SQLite database (`rice_vision.db`) automatically initializes itself from [schema.sql](file:///d:schema.sql) on first launch if it does not already exist. No manual database setup is required.

---

## 4. Running the Application

### Start the Server
With the virtual environment activated, run:
```powershell
python server.py
```

You should see console output similar to:
```text
RiceVision Phase 1 on http://0.0.0.0:8000   vision=on
```

### Run on a Custom Port (Optional)
If port `8000` is already in use by another application, specify `--port`:
```powershell
python server.py --port 8080
```

---

## 5. Opening the HMI

### Option A: Standard Browser Tab
Open any web browser and go to:
[http://localhost:8000/](http://localhost:8000/)

### Option B: Industrial Touchscreen App Mode (Recommended 800×480)
To run the HMI in clean, borderless standalone app mode matching the industrial 800×480 touchscreen interface (without browser tabs or URL address bar):

* **Using Microsoft Edge**:
  ```powershell
  start msedge --app=http://localhost:8000/ --window-size=800,480
  ```

* **Using Google Chrome**:
  ```powershell
  start chrome --app=http://localhost:8000/ --window-size=800,480
  ```

* **Full-Screen Kiosk Mode** (Edge):
  ```powershell
  start msedge --kiosk http://localhost:8000/ --edge-kiosk-type=fullscreen
  ```

---

## 6. Camera Configuration on Windows

1. **Browser Camera Permissions**:
   * Modern browsers (Chrome, Edge, Firefox) grant camera access to `http://localhost` by default.
   * When prompted: "Allow http://localhost:8000 to use your camera?", click **Allow**.
2. **Windows Camera Privacy Settings**:
   * If the camera displays a black screen or error:
     1. Open **Windows Settings** (`Win + I`).
     2. Go to **Privacy & security** > **Camera**.
     3. Ensure **Camera access** is set to **On**.
     4. Ensure **Let desktop apps access your camera** is set to **On**.
3. **Switching Between Webcams (Multiple Cameras)**:
   * To select a secondary USB camera for backend OpenCV processing, set the `PI_CAM_INDEX` environment variable before starting the server:
     ```powershell
     $env:PI_CAM_INDEX = "1"
     python server.py
     ```
     *(Index `0` is typically the built-in laptop camera; index `1` or `2` is an external USB camera).*

---

## 7. One-Click Launch Script for Windows

To launch both the server and the browser in one click, you can create a file named `run_windows.bat` in the project root:

```bat
@echo off
title RiceVision HMI Phase 1
echo Starting RiceVision HMI on Windows...
cd /d "%~dp0"

:: Activate virtual environment if present
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: Start server in background
start "RiceVision Server" python server.py --port 8000

:: Wait 2 seconds for server to start
timeout /t 2 /nobreak >nul

:: Launch Edge in 800x480 HMI App Mode
start msedge --app=http://localhost:8000/ --window-size=800,480
```

Double-clicking `run_windows.bat` will start the backend and open the interface immediately.

---

## 8. Network Access from Other Devices (Tablets / Mobile)

If accessing the HMI from a tablet or phone on the same local network:
1. Find your Windows PC's IP address:
   ```powershell
   ipconfig
   ```
   *(Look for `IPv4 Address`, e.g. `192.168.1.50`).*
2. Because mobile browsers require HTTPS for camera streaming when not on `localhost`, generate a local self-signed certificate:
   ```powershell
   openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=ricevision"
   ```
3. Run the server with SSL:
   ```powershell
   python server.py --cert cert.pem --key key.pem
   ```
4. On the tablet, open: `https://192.168.1.50:8000/` and accept the self-signed certificate warning.

---

## 9. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `'python' is not recognized as an internal or external command` | Python was not added to the Windows PATH. | Re-run Python installer, choose "Modify", and check "Add Python to PATH", or restart your terminal. |
| `running scripts is disabled on this system` | Windows PowerShell execution policy restriction. | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before activating the venv. |
| `OSError: [WinError 10048] Only one usage of each socket address is normally permitted` | Port 8000 is already held by an older Python process or another app. | Run `netstat -ano \| findstr :8000` to find the PID, and kill it with `Stop-Process -Id <PID> -Force` (PowerShell) or use a different port `python server.py --port 8080`. |
| Camera frame black or `getUserMedia unavailable` | Windows Camera Privacy or browser permissions blocking camera. | Enable desktop camera access in Windows Privacy Settings and allow camera in browser bar icon. |
| SIFT / Vision matching says `vision=OFF` | OpenCV is missing or failed to import. | Run `pip install --force-reinstall opencv-python`. |

---

## 10. Key Project Files Reference

* [server.py](file:///d:server.py): HTTP API backend, SQLite persistence, and camera streaming endpoints.
* [vision.py](file:///d:vision.py): Computer vision algorithms, SIFT bag artwork descriptor matching, and color histogram verification.
* [camera.py](file:///d:camera.py): Camera acquisition module (OpenCV fallback on Windows, picamera2 on Raspberry Pi).
* [static/index.html](file:///d:index.html): Industrial HMI 800×480 touchscreen interface.
* [schema.sql](file:///d:schema.sql): SQLite database schema for recipes, verification logs, and audit trail.
* [requirements.txt](file:///d:requirements.txt): Python package dependencies.
