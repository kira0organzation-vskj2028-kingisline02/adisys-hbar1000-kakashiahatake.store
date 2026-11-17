# Ubuntu Deployment & Cloudflare Guide for RiceVision HMI
**Domain**: `kakashihatake.store`  
**Application Port**: `11111` (HTTP)


## Overview

To make your RiceVision HMI application publicly accessible under your domain **`https://kakashihatake.store`** so anyone can test it with zero friction, we have prepared two methods:

* **Method 1: Cloudflare Tunnel (⭐️ Recommended - 5 Minutes, Zero Open Ports)**
  * Requires **no port forwarding**, no static public IP, and no firewall openings.
  * Free automatic SSL certificate managed directly by Cloudflare.
  * Extremely secure: runs via a lightweight outbound daemon (`cloudflared`).

* **Method 2: Nginx Reverse Proxy (Traditional Static Public IP Setup)**
  * For VPS instances (DigitalOcean, AWS, Hetzner, etc.) that have a dedicated public IPv4 address.

---

## Step 1: Copy Code to Your Ubuntu Server

From your local machine (Windows PowerShell), copy the project folder to your Ubuntu server:

```powershell
# Example using scp (run from the directory containing your project folder):
scp -r ./new username@YOUR_UBUNTU_IP:/home/username/ricevision
```

*(Alternatively, push your code to GitHub / GitLab and run `git clone <repo-url> /home/username/ricevision` on Ubuntu).*

---

## Step 2: Run the Automated Setup on Ubuntu

Connect to your Ubuntu server via SSH:
```bash
ssh username@YOUR_UBUNTU_IP
cd /home/username/ricevision
```

Make the automated setup script executable and run it:
```bash
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

### What this script does automatically:
1. Installs `python3-pip`, `python3-venv`, and headless vision dependencies (`libgl1`, `libglib2.0-0`).
2. Creates the isolated Python virtual environment (`venv`).
3. Installs `numpy`, `opencv-python-headless`, `pillow`, and `pilkit`.
4. Creates and activates the **`ricevision.service`** systemd unit file.
5. Starts the app in the background on port `11111` with auto-restart on reboot or crash.

---

## Step 3: Connect to Cloudflare (`kakashihatake.store`)

### Option A: Cloudflare Tunnel (⭐️ Recommended)

1. Open your browser and log into your **[Cloudflare Dashboard](https://dash.cloudflare.com/)**.
2. Go to **Zero Trust** (on the left menu) > **Networks** > **Tunnels**.
3. Click **Add a tunnel** > Choose **Cloudflared** > Name it (e.g. `ricevision-tunnel`) > Click **Save tunnel**.
4. In the **Install and run a connector** step:
   * Select **Debian 64-bit** (Ubuntu).
   * Copy the generated command that looks like:
     ```bash
     curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i cloudflared.deb && sudo cloudflared service install <YOUR_TOKEN>
     ```
   * Paste and run this command inside your Ubuntu terminal.
5. Once connected, click **Next** in the Cloudflare dashboard to go to the **Public Hostnames** tab:
   * **Domain**: Select `kakashihatake.store`
   * **Subdomain**: (Leave blank for root `kakashihatake.store`, or type `hmi` / `app` if you want `hmi.kakashihatake.store`)
   * **Service Type**: `HTTP`
   * **URL**: `localhost:11111`
6. Click **Save Hostname**.

🎉 **Done!** Open `https://kakashihatake.store` in your browser. Cloudflare terminates SSL automatically and routes all traffic safely to your Ubuntu server.

---

### Option B: Nginx Reverse Proxy (Alternative)

If you have a public static IP on your Ubuntu server:

1. **In Cloudflare DNS**:
   * Add an **A Record**:
     * **Name**: `@` (or `kakashihatake.store`)
     * **IPv4 Address**: `YOUR_UBUNTU_SERVER_PUBLIC_IP`
     * **Proxy status**: **Proxied** (Orange cloud icon enabled)
   * *(Optional)* Add a **CNAME Record**:
     * **Name**: `www`
     * **Target**: `kakashihatake.store`
     * **Proxy status**: **Proxied**

2. **In Cloudflare SSL/TLS Settings**:
   * Set SSL/TLS encryption mode to **Full** or **Flexible**.

3. **On Your Ubuntu Server**:
   * Install Nginx and Certbot:
     ```bash
     sudo apt install -y nginx certbot python3-certbot-nginx
     ```
   * Copy the included Nginx config:
     ```bash
     sudo cp nginx_site.conf /etc/nginx/sites-available/kakashihatake.store
     sudo ln -s /etc/nginx/sites-available/kakashihatake.store /etc/nginx/sites-enabled/
     sudo rm -f /etc/nginx/sites-enabled/default
     sudo nginx -t
     sudo systemctl reload nginx
     ```
   * Let's Encrypt Certificate & Automated Renewal:
     ```bash
     # Obtain certificate with TLS 1.3 support
     sudo certbot --nginx -d kakashihatake.store -d www.kakashihatake.store -d adisys.kakashihatake.store
     # Verify automated renewal timer (runs twice daily automatically via systemd timer)
     sudo systemctl status certbot.timer
     # Test renewal dry-run
     sudo certbot renew --dry-run
     ```

---

## Step 4: Maintenance & Commands Reference

| Action | Command |
| :--- | :--- |
| **Check service status** | `sudo systemctl status ricevision` |
| **Restart application** | `sudo systemctl restart ricevision` |
| **Stop application** | `sudo systemctl stop ricevision` |
| **View live logs** | `sudo journalctl -u ricevision -f` |
| **Update code** | `git pull` (or scp new files) && `sudo systemctl restart ricevision` |

---

## Step 5: Verification Checklist for Remote Reviewers

When sharing the URL `https://kakashihatake.store` with your reviewer, they can test:
1. **Screen 1 (STN 2 REGISMATIC)**:
   * 99-tick Mark Window ruler.
   * `0mm`, `-10mm`, and `+10mm` simulation switchers.
   * Dynamic needle position, live status tag, and millimeter error readouts (`ERR: -10.0mm`, `A-REP: 730mm (-10.0mm)`).
   * Mark Window numpad calibration.
2. **Screen 2 (Camera Inspection)**:
   * Front $\leftrightarrow$ Back dual bag inspection.
   * Millimeter error displays (`FRONT ⟷ BACK ERROR (mm)`).
   * **Single Frame Capture** button visible and clickable in all modes.
3. **Screen 3 (Recipe Calibration)**:
   * Recipe editing, parameters, and delete workflows.
