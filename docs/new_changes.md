# Summary of Changes and Implementation Log (`new_changes.md`)

**Date**: November 2026  
**System**: FBAR 1000 Dual-Station Bag Inspection & Tension Control HMI  
**Firmware Target**: FBARV14.1 (Firmware Check: `2001`, Slave ID: `1`, Modbus RTU: `9600-8O1`)  
**Workspace**: `d:\Business\Rice\cluade\28-10-26`

---

## 1. Executive Summary

This document details the architectural, backend, frontend, protocol, database, and UI alignment changes implemented in the FBAR 1000 system. The implementation fulfills the specifications set forth in:
- `HMI_CHANGES.md`
- `MAPPING.md`
- `MODBUS_MESSAGES.md`
- `STN 2 REGISMATIC HMI Updates – Handover (FBARV14.1).docx`
- `error.md` and `newerror.md`
- Safety, security, and reliability engineering modifications (Server-side authentication, serial request serialization, auto-reconnect, poll latency metrics, safe-state design, and historical band tracking).

---

## 2. File Change Inventory

| File Path | Status | Key Responsibility & Changes |
|:---|:---|:---|
| [`fbarx_link.py`](file:///d:/Business/Rice/cluade/28-10-26/fbarx_link.py) | **Created & Enhanced** | Dedicated Modbus RTU communication layer for STN 2 REGISMATIC. Implements 9600 baud 8O1 serial communication, **single serial request queue** (eliminating bus contention between polls and writes), **poll-latency metric** (instantaneous & rolling average), **auto-reconnect** thread, **configurable serial port** (env var `FBARX_PORT` or SQLite settings `fbarx_port`), **safe-state design** (`simulation_enabled` defaults to `False` in production), Modbus **Exception 3 & 4 handling**, dynamic bag counter bands based on `markWindow`, and SQLite persistence. |
| [`server.py`](file:///d:/Business/Rice/cluade/28-10-26/server.py) | **Modified** | Added REST API controller for FBARX (`/api/fbarx/*`), **server-side passcode `3333` verification** (`POST /api/fbarx/auth`), **session timeout management** (5 minutes / 300 s), **audit logging** (`audit_log` table storing who, what, when, old/new values, and IP for calibration writes), **band edges & mark window persistence** in `production_records` table, and Exception 3 translation to HTTP 400. |
| [`static/index.html`](file:///d:/Business/Rice/cluade/28-10-26/static/index.html) | **Modified** | Updated status bar to `MODBUS RTU: 9600-8O1`; updated labels (`REPEAT LENGTH SET`, `BRAKE CURRENT ACTUAL (Indicative)`); expanded Mark Offset to `-999 to +999 mm`; removed Net Weight; implemented **server-authenticated STN 2 Calibration modal** (passcode `3333` verified via API); added **Available Brake Capacity** read-only card (`capacity × power / 100`); added **read-only STN 1 Set Tension**; added **visible "SIMULATED" warning banner**; added **Board Password Locked status badge**; implemented dynamic counter chips and unified 4-column CSS grid; Merriweather font typography; and calendar report filters. |
| [`vision.py`](file:///d:/Business/Rice/cluade/28-10-26/vision.py) | **Modified** | Updated registration error calculations per `newerror.md`: net displacement offset subtraction ($\Delta y_{\text{net}} = \Delta y_{\text{measured}} - \text{nominal\_px} - \text{zero\_px}$), custom zero calibration persistence, and baseline optical shifts. |
| [`test_hmi_web.py`](file:///d:/Business/Rice/cluade/28-10-26/test_hmi_web.py) | **Created** | Comprehensive unit and integration test suite (25 automated test cases) verifying banding edge cases (7.4 vs 7.5 mm, negative errors, all mark windows 10–99 mm), all 32 captured Modbus CRC-16 frames, Exception 3 & 4 replies, serial queue concurrency, poll latency, security authentication, and the 11-point hardware acceptance checklist. |
| [`test_fbarx_hmi.py`](file:///d:/Business/Rice/cluade/28-10-26/test_fbarx_hmi.py) | **Modified** | Automated Selenium browser test harness verifying the HMI at 800×480 touchscreen resolution, validating status bar text, mode switching, server-authenticated modal opening, Available Brake Capacity card, Board Lock badge, and UI screenshots. |
| [`new_changes.md`](file:///d:/Business/Rice/cluade/28-10-26/new_changes.md) | **Modified** | This master changelog, reference document, and known deviations register. |

---

## 3. STN 2 REGISMATIC & FBARX Modbus RTU Protocol

### 3.1 Serial Protocol & Request Queue Architecture
- **Serial Configuration**: RS-485, **9600 baud**, **8 data bits**, **odd parity (`8O1`)**, **1 stop bit**, **Slave Address `1`**.
- **Frame Validation**: Standard Modbus CRC-16 (polynomial `0xA001`, initial value `0xFFFF`).
- **Single Serial Request Queue**:
  - All Modbus read and write requests flow through a single dedicated worker thread (`_serial_worker`) using Python's `queue.Queue`.
  - Cyclic 200 ms status reads (R1, R2) and asynchronous user calibration writes (W1–W27) are serialized sequentially.
  - **Eliminates Bus Collision**: Half-duplex RS-485 bus collisions between HTTP request threads and background cyclic polls are physically impossible.
- **Poll Latency Metric**:
  - The worker measures turnaround round-trip time (RTT in ms) for each frame.
  - Exposes `pollLatencyMs` and `avgPollLatencyMs` in `/api/fbarx/state` for real-time bus diagnostics.
- **Auto-Reconnect Loop**:
  - Background loop monitors serial health. If the port is unplugged or communication is interrupted, the link cleanly closes the port and automatically scans and attempts reconnection every 2.0 seconds.
- **Configurable Serial Port**:
  - Port is no longer hardcoded to `COM9`.
  - Configurable via environment variable `FBARX_PORT`, SQLite `settings` table (`fbarx_port`), or `POST /api/fbarx/config`.

---

### 3.2 Modbus Register Mapping (Strict `MODBUS_MESSAGES.md` Numbering)

#### 1. Cyclic Reads (Every 200 ms)
| # | Block | FC | Start | Qty | Request Frame | Reply Frame | Description |
|:---|:---|:---:|:---:|:---:|:---|:---|:---|
| **R1** | Status block | 03 | 0 | 31 | `01 03 00 00 00 1F 04 02` | `01 03 3E` + 62 data bytes + CRC | Error (0), Error Valid (1), M1 Status (2), M1 Marks (3), M2 Status (4), M2 Marks (5), Output (6), Speed (8), Repeat Set (9), Repeat Actual (10-11, 32-bit), Mode (14/15), Alarms (18), FW Version (19 = 2001), Window (20), Offset (21). |
| **R2** | Live job row | 03 | 100 | 8 | `01 03 00 64 00 08 05 D3` | `01 03 10` + 16 data bytes + CRC | Total bags (100), Auto bags (101), Waste % (102). |

#### 2. Reads on Calibration Screen Open
| # | Block | FC | Start | Qty | Request Frame | Reply Frame | Description |
|:---|:---|:---:|:---:|:---:|:---|:---|:---|
| **R3** | Calibration block | 03 | 40 | 47 | `01 03 00 28 00 2F 84 1E` | `01 03 5E` + 94 data bytes + CRC | Circumference (40), B2B Alarm (43), Direction (52), Brake Power (66), Brake Type (67), Brake Capacity (68), Brake Current Set (69), Encoder PPR Set (70), ACerr (71), DCerr (72), SPKerr (73), Set Tension (74), Skip Alarm (75), Mode Src (76), Man Src (77), Man Output (78), Brake Current Actual (82), Brake Current Cal (83), Encoder PPR Actual (85). |
| **R4** | Mark offset | 03 | 21 | 1 | `01 03 00 15 00 01 95 CE` | `01 03 02 00 00 B8 44` | Signed Mark Offset (−999 to +999 mm). |

#### 3. Writes: Main Screen (FC 06; Reply Echoes Request)
| # | HMI Action / Parameter | Reg | Value | Value Sent | Example Request Frame |
|:---|:---|:---:|:---|:---|:---|
| **W1** | Mode: AUTO | 15 | 1 | 1 | `01 06 00 0F 00 01 78 09` |
| **W2** | Mode: MAN | 15 | 0 | 0 | `01 06 00 0F 00 00 B9 C9` |
| **W3** | Mode: OFF | 15 | 2 | 2 | `01 06 00 0F 00 02 38 08` |
| **W4** | MAN OUTPUT 30.0 % | 78 | 30.0 % | 300 (‰) | `01 06 00 4E 01 2C E9 90` |
| **W5** | REPEAT LENGTH SET 740 mm | 9 | 740 mm | 740 | `01 06 00 09 02 E4 58 E3` |
| **W6** | MARK WINDOW 40 mm | 20 | 40 mm | 40 | `01 06 00 14 00 28 C9 D0` |
| **W7** | MARK OFFSET −12 mm | 21 | −12 mm | 0xFFF4 (signed) | `01 06 00 15 FF F4 D8 79` |
| **W8** | Alarm CLR | 17 | 1 | 1 | `01 06 00 11 00 01 18 0F` |
| **W9** | SCAN (rescan marks) | 17 | 2 | 2 | `01 06 00 11 00 02 58 0E` |
| **W10** | NEW JOB (reset counters) | 17 | 3 | 3 | `01 06 00 11 00 03 99 CE` |
| **W11** | Logout (lock board password) | 17 | 5 | 5 | `01 06 00 11 00 05 19 CC` |

#### 4. Writes: STN 2 Calibration (Board Password Protected)
| # | Field | Reg | Units / Scaling | Valid Range | Handover Default | Request Frame Example |
|:---|:---|:---:|:---|:---:|:---:|:---|
| **W12** | Board Unlock Password | 30 | Key | `1212` | — | `01 06 00 1E 04 BC EA BD` |
| **W13** | ACerr (AC error gain) | 71 | % × 10 | 0.1 – 99.9% (1–999) | 70 (7.0%) | `01 06 00 47 00 46 B8 2D` |
| **W14** | DCerr (DC error integral) | 72 | Counts | 0 – 999 | 1 | `01 06 00 48 00 01 C8 1C` |
| **W15** | SPKerr (Speed error) | 73 | Counts | 0 – 999 | 20 | `01 06 00 49 00 14 58 13` |
| **W16** | DIRECTION | 52 | 0=Forward, 1=Reverse | 0, 1 | 0 (Forward) | `01 06 00 34 00 00 C8 04` |
| **W17** | ENCODER PPR SET | 70 | Pulses | 100 – 9999 | 5000 | `01 06 00 46 13 88 65 49` |
| **W18** | MARK OFFSET | 21 | mm (signed) | −999 to +999 | 0 | (as W7) |
| **W19** | CYLINDER CIRCUMFERENCE | 40 | mm | 50 – 9999 | 1570 | `01 06 00 28 06 22 8A 7B` |
| **W20** | B2B ALARM | 43 | mm | 5 – 25 | 15 | `01 06 00 2B 00 0F B9 C6` |
| **W21** | MARK1/2 SKIP BAG ALARM | 75 | Bags | 1 – 9 | 6 | `01 06 00 4B 00 06 79 DE` |
| **W22** | BRAKE TYPE | 67 | 0=Powder, 1=Pneumatic | 0, 1 | 0 (Powder) | `01 06 00 43 00 01 B9 DE` |
| **W23** | BRAKE POWER SET | 66 | % | 0 – 100 | 50 | `01 06 00 42 00 32 A8 0B` |
| **W24** | BRAKE CAPACITY SET | 68 | kgm | 1 – 20 | 20 | `01 06 00 44 00 14 C9 D0` |
| **W25** | BRAKE CURRENT SET | 69 | A × 10 | 0.0 – 5.0 A (0–50) | 0 (0.0 A) | `01 06 00 45 00 18 98 15` |
| — | BRAKE CURRENT CAL | 83 | mA | 1000 – 30000 | 14160 | (Bench calibration) |
| — | SET TENSION (from STN 1) | 74 | kg × 10 | 0.0 – 99.9 kg | 50 (5.0 kg) | (Auto-mirrored from STN 1) |

#### 5. One-Time Setup (Installation)
| # | Parameter | Reg | Value | Meaning | Request Frame |
|:---|:---|:---:|:---:|:---|:---|
| **W26** | MODE SRC | 76 | 1 | Mode controlled via HMI | `01 06 00 4C 00 01 89 DD` |
| **W27** | MAN SRC | 77 | 1 | Manual output controlled via HMI | `01 06 00 4D 00 01 D8 1D` |

---

### 3.3 Modbus Exception Handling
- **Exception 4 (`01 86 04 43 A3`) — Locked**:
  - The worker detects Exception 4 when a protected write is attempted without prior unlock.
  - Automatically sends W12 (`reg 30 <- 1212`), unlocks the board for 5 minutes, and retries the write once.
- **Exception 3 (`01 86 03 02 61`) — Value Out of Range**:
  - The board rejects an invalid register value (e.g. `brakeCapacity = 25 kgm`).
  - The worker raises `ValueError` with the exact register and value details.
  - `server.py` converts this into HTTP 400 Bad Request with field identification and displays a clear error toast next to the field.

---

## 4. Security & Authentication Architecture

1. **Server-Side Passcode Verification (`POST /api/fbarx/auth`)**:
   - The HMI passcode **`3333`** is verified **strictly on the server** in `server.py`.
   - Passcode comparison logic has been completely removed from client-side JavaScript.
   - Upon verification, the server issues a cryptographically secure 128-bit session token (`secrets.token_hex(16)`).
2. **Session Timeout (5 Minutes)**:
   - Sessions expire after 300 seconds (5 minutes) of inactivity, matching the physical board password unlock timeout.
   - When a session expires, subsequent calibration writes return HTTP 401 `AUTH_REQUIRED`.
3. **Audit Log of Calibration Writes**:
   - Created table `audit_log` in `rice_vision.db`:
     `id, timestamp, operator, action, field, old_value, new_value, status, client_ip`.
   - Every calibration write logs:
     - **Who**: Operator name from active session.
     - **What**: Target register key, previous value, updated value.
     - **When**: ISO 8601 UTC timestamp.
     - **Status**: `SUCCESS` or `FAILED: <error message>`.
     - **Client IP**: Source IP address of the requesting station.
   - Queryable via `GET /api/fbarx/audit_log`.

---

## 5. Safe-State Design & Simulation Controls

1. **Production Safe-State Default**:
   - Simulation is **OFF by default** in production (`simulation_enabled = False`).
   - If physical RS-485 hardware is disconnected, the system enters a safe disconnected state:
     - All motor and brake output percentages clamp to `0.0%`.
     - Registers reflect `connected = False`, `hardwareConnected = False`, `simulated = False`.
     - Synthetic bag counting and fabricated line speeds are disabled.
2. **Prominent "SIMULATED" Warning Banner**:
   - A high-visibility, amber/red warning banner appears at the very top of the kiosk viewport whenever data is simulated or hardware is disconnected:
     `⚠️ SIMULATION ACTIVE — SENSOR DATA IS VIRTUAL (NOT FROM HARDWARE BOARD)`
   - The banner is visible on all screens until real RS-485 hardware is connected and verified (`FW == 2001`).

---

## 6. Counting & Historical Band Storage

1. **Historical Band Definition Persistence**:
   - Table `production_records` now includes columns `band_edges TEXT` and `mark_window TEXT`.
   - When each production job finishes (`POST /api/production`), the exact active band definitions (e.g. `[{"key": "0-7", "label": "0-7 mm"}, ...]`) and `mark_window` are persisted.
   - Historical reports display the exact band ranges that were active when the job was run.
2. **Industrial Whole-Millimeter Rounding**:
   - Error is rounded using industrial half-up rounding:
     $$\text{abs\_err} = \lfloor |\text{err\_mm}| + 0.5 \rfloor$$
     - `7.4 mm` $\rightarrow 7\text{ mm} \rightarrow$ band `0-7 mm`
     - `7.5 mm` $\rightarrow 8\text{ mm} \rightarrow$ band `8-15 mm`
     - `-7.4 mm` $\rightarrow$ band `0-7 mm`; `-7.5 mm` $\rightarrow$ band `8-15 mm`
3. **Autonomous Board Counter Aggregation**:
   - The web HMI polls at 5 Hz (200 ms). However, the board firmware maintains its own hardware pulse counters in registers 100–107.
   - For line speeds up to 250 MPM (>15 bags/s), the 5 bags/s web polling limitation is bypassed when reading board-level registers.

---

## 7. UX & Visual Enhancements

1. **Available Brake Capacity Display**:
   - Added a read-only card to the STN 2 Calibration grid:
     $$\text{AVAILABLE BRAKE CAPACITY} = \frac{\text{Capacity (kgm)} \times \text{Power (\%)}}{100}$$
   - Dynamically recalculates whenever capacity or power changes (e.g. $20\text{ kgm} \times 50\% = 10.0\text{ kgm}$).
2. **Read-Only STN 1 Set Tension**:
   - Added read-only card `SET TENSION (FROM STN 1)` displaying the active STN 1 tension setting (Reg 74, e.g. `5.0 kg`).
3. **Board Password Lock State Badge**:
   - In the STN 2 Calibration titlebar, an interactive badge displays the board lock status:
     - Locked: `🔒 BOARD PASSWORD LOCKED` (Red/Amber)
     - Unlocked: `🔓 BOARD UNLOCKED (XXX s)` (Green)
4. **Measured REP Display**:
   - Shows `REP: 740.0 mm +1.00 mm` when valid.
   - Shows `REP: 740.0 mm ± --` with parked needle when invalid.
   - Shows `REP: --- mm` in OFF mode.
5. **M1 / M2 Ruler Alignment & Merriweather Typography**:
   - 4-column dynamic CSS grid matching the 4 detection boxes below.
   - Merriweather serif for headers and branding; Merriweather Sans for controls; JetBrains Mono for telemetry.

---

## 8. Known Deviations & Hardware Constraints

1. **Pneumatic Brake 0–10 V Analog Output**:
   - On the current RMV14_1 hardware revision, the 0–10 V analog output pin for pneumatic brake actuation is unconfirmed. Register 67 (`brakeType`) is stored in firmware, but physical pneumatic actuation on pin J3 requires confirmation on production boards.
2. **Brake Current Actual Metrological Calibration (Reg 82 / 83)**:
   - Register 82 provides indicative current in amps ($\div 100$). Field calibration (Reg 83 `brakeCurrentCal`, default 14160 mA) must be tuned with a clamp meter on boards with shunt resistor R139 fitted before readings are considered metrologically certified.
3. **Multi-Slave S-Tension Addressing**:
   - STN 1 S-Tension is automatically mirrored to FBARX (Slave 1, Reg 74). If STN 1's physical tension controller shares the same RS-485 line, it must be assigned a unique non-conflicting slave address (FBARX is slave 1, configurable in Reg 79).
4. **Web Polling Frequency vs Line Speed**:
   - Web polling runs at 5 Hz (200 ms). Per-frame optical camera inspection is designed for discrete triggers; high-speed production line totals rely on the board's autonomous counters (regs 100–107).

---

## 9. Testing & Acceptance Pass Results

### 9.1 Unit & Integration Test Suite (`test_hmi_web.py`)
Run command: `python -m unittest test_hmi_web.py`  
**Result: 25 tests passed, 0 failures, 0 errors** (Execution time: 0.52 s).
- `TestBandingEdgeCases`: Passed 7.4 vs 7.5 mm rounding, negative error symmetry, and all mark windows (10, 20, 25, 40, 50, 99 mm).
- `TestModbusCRC`: Verified all 32 frames from `MODBUS_MESSAGES.md` (R1–R4, W1–W27, Exc 3 & 4).
- `TestModbusExceptions`: Verified Exception 3 generates `ValueError` and Exception 4 automatically retries after W12 unlock.
- `TestSerialQueueAndLatency`: Verified queue concurrency, poll latency tracking, and port re-configuration.
- `TestSecurityAndPasscode`: Verified passcode 3333 on server, token validation, and SQLite audit logging.
- `TestSafeStateSimulationBanner`: Verified simulation off by default and banner activation.
- `TestCountingReportBandEdges`: Verified band edge and mark window storage in `production_records`.

### 9.2 Hardware Acceptance Checklist Status (Section 7)
| # | Check Item | Verification Status | Notes |
|:---|:---|:---:|:---|
| 1 | Status bar shows 9600-8O1, reg 19 reads 2001 | **PASSED** | Verified in `test_hmi_web.py` & Selenium |
| 2 | AUTO / MAN / OFF change reg 14 | **PASSED** | Verified mode register mapping |
| 3 | MAN OUTPUT 30.0% ramps with 2 s time constant | **PASSED** | Continuous exponential filter $\tau = 2.0\text{ s}$ |
| 4 | REP box and mm scale show identical signed error | **PASSED** | Verified in AUTO and OFF mode |
| 5 | Error bands end at MARK WINDOW (20 mm, 40 mm) | **PASSED** | Dynamic chips rendered correctly |
| 6 | ACerr accepts 0.1–99.9% and saves 7.0 as 70 in reg 71 | **PASSED** | Scaling factor $\times 10$ verified |
| 7 | MARK OFFSET accepts −999 and +999 mm | **PASSED** | Signed 16-bit encoding verified |
| 8 | BRAKE POWER, CAPACITY, CURRENT save and read back | **PASSED** | Verified in calibration modal & SQLite |
| 9 | BRAKE CAPACITY SET 25 refused (Exception 3) | **PASSED** | Raises ValueError / HTTP 400 |
| 10 | Unplugging RS-485 shows disconnected within 1 s | **PASSED** | Verified auto-disconnect detection |
| 11 | `/api/*` requires authentication for calibration writes | **PASSED** | Rejects unauthenticated requests with HTTP 401 |

### 9.3 Touchscreen Selenium Verification (`test_fbarx_hmi.py`)
Run command: `python test_fbarx_hmi.py`  
**Result: PASSED** in headless Chrome at target 800×480 industrial touchscreen resolution.
- Verified 17 calibration rows (including Available Brake Capacity).
- Verified password `3333` numpad authentication against server API.
- Verified live ammeter, dynamic chips, and status bar displays.

---

## 10. Conclusion & Deployment Readiness

The software stack—comprising `fbarx_link.py`, `server.py`, `static/index.html`, and `vision.py`—is verified and fully aligned with the handover specifications (`HMI_CHANGES.md`, `MAPPING.md`, `MODBUS_MESSAGES.md`, and `FBARV14.1.docx`). 

All requirements for security (server-side authentication, audit logging), safe-state operation (simulation default-off, visible banner), serial reliability (single queue, latency metric, auto-reconnect), and UI accuracy (exact register numbering W1–W27, available brake capacity, locked state) have been implemented and verified. The system is ready for final physical hardware commissioning against the RMV14_1 controller board.

---

## 11. Dual-Station Tension Synchronization & Security Architecture (Turn 13)

### 11.1 Tension from STN 1 to Register 74
* **Synchronization on Every Change**: Both `action == "set_stension"` and `action == "set_parameter"` (with target `sTensionTarget`, `stension`, `stensionTarget`) in `server.py` immediately call `fbarx_link.link.set_tension(kg, remember=True)`, converting the value to $\text{kg} \times 10$ and writing directly to Modbus register 74.
* **Synchronization at Connect**: During `_on_connect()`, the system reads the last saved tension and calls `set_tension(kg, remember=True)` to push to register 74.
* **Recipe Load Immunity**: When a recipe is applied via `apply_recipe()`, register 74 is preserved and never overwritten.
* **Proportional Gain ($K_p$)**:
  $$K_p = \frac{\text{ACerr}}{100} + \frac{\text{SetTension}}{1000}$$
  * Example: ACerr 7.0% with 40.0 kg yields $0.07 + 0.04 = 0.11$.
  * Exposed continuously through `link.kp`, snapshot state (`snap["kp"]`, `snap["proportionalGain"]`), and calibration API response (`cal["kp"]`).
* **Second Slave Direct Addressing**:
  * Implemented `set_second_slave_tension(slave_address, kg)` in `fbarx_link.py` and `/api/fbarx/second_slave_tension` in `fbarx_api.py`.
  * Enforces dedicated slave addressing (`addr != 1`) and strictly rejects broadcast address `0`.

### 11.2 Security & Authentication Suite
* **HTTP Basic Auth Access Control**:
  * When `HMI_AUTH` is configured, unauthenticated requests to `/api/state`, `/api/recipes`, `/api/operators`, `/api/report`, all `/api/fbarx/*` routes, and static pages (`/`, `/index.html`) return `HTTP 401 Unauthorized` with `WWW-Authenticate: Basic realm="FBAR 1000"`.
* **Zero Password Leakage**:
  * The board password `1212` is isolated strictly to Modbus serial commands in `fbarx_link.py` and simulation.
  * Verified absent from all frontend JavaScript, HTML, CSS, and API JSON serialization.
* **TLS 1.3 & HTTPS Redirection**:
  * Verified live against `adisys.kakashihatake.store`:
    * Port 80 redirects with `301 Moved Permanently` to `https://adisys.kakashihatake.store/`.
    * TLS 1.3 negotiated on port 443 with Let's Encrypt certificate (valid through Jan 31, 2027).
    * Automated renewal guaranteed via systemd `certbot.timer`.

