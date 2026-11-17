# RiceVision HMI & FBAR 1000 Dual-Station System — Functional Specification

**Document Version**: 2.0  
**Target Hardware**: RMV14_1 REGISMATIC Board (Firmware `2001`, Modbus RTU `9600-8O1`), Raspberry Pi 5 / CSI Camera 3, USB UVC Camera, Loadcell & Powder/Pneumatic Brakes  
**Architecture**: Server-Authoritative Python Backend (`server.py`) & Ultra-Thin Responsive Touchscreen HMI (`static/index.html`)

---

## Table of Contents

1. [Executive Overview & System Architecture](#1-executive-overview--system-architecture)
2. [Station 1: Unwind Tension Controller (STN 1)](#2-station-1-unwind-tension-controller-stn-1)
   - [2.1 Operating Modes & Interlock Rules](#21-operating-modes--interlock-rules)
   - [2.2 S-Tension (Setpoint) & A-Tension (Feedback)](#22-s-tension-setpoint--a-tension-feedback)
   - [2.3 Unit Toggle (KG ↔ N)](#23-unit-toggle-kg--n)
   - [2.4 Manual Steppers & Output Power Regulation](#24-manual-steppers--output-power-regulation)
   - [2.5 Brake Selection: Powder Brake vs. Pneumatic Brake](#25-brake-selection-powder-brake-vs-pneumatic-brake)
   - [2.6 Calibration & Closed-Loop Control Parameters](#26-calibration--closed-loop-control-parameters)
3. [Station 2: REGISMATIC Registration Controller (STN 2 / FBARX)](#3-station-2-regismatic-registration-controller-stn-2--fbarx)
   - [3.1 Serial Architecture & Single-Queue Modbus RTU](#31-serial-architecture--single-queue-modbus-rtu)
   - [3.2 Operating Modes (AUTO / MAN / OFF)](#32-operating-modes-auto--man--off)
   - [3.3 Cylinder Repeat Length & Mark Window Dynamics](#33-cylinder-repeat-length--mark-window-dynamics)
   - [3.4 Mark Offset Adjustment (-999 mm to +999 mm)](#34-mark-offset-adjustment--999-mm-to-999-mm)
   - [3.5 Optical Sensors M1 & M2 (Status & Mark Counting)](#35-optical-sensors-m1--m2-status--mark-counting)
   - [3.6 Hardware Control Commands (CLR, SCAN, NEW JOB, LOGOUT)](#36-hardware-control-commands-clr-scan-new-job-logout)
   - [3.7 Indicative Ammeter & Motor Speed Telemetry](#37-indicative-ammeter--motor-speed-telemetry)
   - [3.8 Dynamic Bag Counter Bands & Industrial Half-Up Rounding](#38-dynamic-bag-counter-bands--industrial-half-up-rounding)
   - [3.9 STN 2 Deep Calibration & Board Password Protection](#39-stn-2-deep-calibration--board-password-protection)
4. [Computer Vision & Optical Inspection Engine (RiceVision)](#4-computer-vision--optical-inspection-engine-ricevision)
   - [4.1 Dual-Source Video Pipeline (Pi CSI & OpenCV USB)](#41-dual-source-video-pipeline-pi-csi--opencv-usb)
   - [4.2 Registration Line Edge Detection & Net Displacement](#42-registration-line-edge-detection--net-displacement)
   - [4.3 Dual-Bag Analysis (Front Bag vs. Back Bag)](#43-dual-bag-analysis-front-bag-vs-back-bag)
   - [4.4 SIFT & Template Matching Recipe Verification](#44-sift--template-matching-recipe-verification)
   - [4.5 Safe-State Video Streaming (`/api/camera/stream`)](#45-safe-state-video-streaming-apicamerastream)
5. [Recipe Management & Master Profile Store](#5-recipe-management--master-profile-store)
   - [5.1 Recipe Database Structure & Parameter Binding](#51-recipe-database-structure--parameter-binding)
   - [5.2 Master Reference Images (Front & Back Clarified JPEGs)](#52-master-reference-images-front--back-clarified-jpegs)
   - [5.3 Recipe Selection, Editing, and Hardware Synchronization](#53-recipe-selection-editing-and-hardware-synchronization)
6. [Operator Management & Verification](#6-operator-management--verification)
   - [6.1 Independent Operator Directory](#61-independent-operator-directory)
   - [6.2 Operator Selection & Visual Face Verification](#62-operator-selection--visual-face-verification)
7. [Production Reporting & Quality Intelligence](#7-production-reporting--quality-intelligence)
   - [7.1 Real-Time Job Tracking & Timestamps](#71-real-time-job-tracking--timestamps)
   - [7.2 Statistical Quality Metrics & Yield Calculations](#72-statistical-quality-metrics--yield-calculations)
   - [7.3 Historical Report Archives & Filtering](#73-historical-report-archives--filtering)
   - [7.4 CSV / Excel Export with Embedded Audit Metadata](#74-csv--excel-export-with-embedded-audit-metadata)
8. [Security, Safety, & Diagnostics](#8-security-safety--diagnostics)
   - [8.1 Multi-Tier Passcode Verification (`3333` / `4444`)](#81-multi-tier-passcode-verification-3333--4444)
   - [8.2 Session Tokens & 5-Minute Inactivity Timeout](#82-session-tokens--5-minute-inactivity-timeout)
   - [8.3 Calibration Audit Trail](#83-calibration-audit-trail)
   - [8.4 Safe-State Operation & Simulation Watermark](#84-safe-state-operation--simulation-watermark)
   - [8.5 Connection Watchdog & Instant Reconnect Loop](#85-connection-watchdog--instant-reconnect-loop)
9. [RESTful API Architecture & Endpoint Reference](#9-restful-api-architecture--endpoint-reference)
10. [Hardware Deployment & Operating Environments](#10-hardware-deployment--operating-environments)

---

## 1. Executive Overview & System Architecture

The **RiceVision HMI & FBAR 1000** is an industrial dual-station control and automated optical inspection (AOI) system designed for woven sack, poly-bag, and flexible rice bag printing and conversion lines. 

The application integrates two essential industrial automation disciplines into a single touchscreen kiosk:
1. **Physical Web Control**: Precision unwind tension regulation (Station 1) and line-registration mark tracking / motor advance-retard correction (Station 2).
2. **High-Speed Optical Quality Inspection**: Real-time camera acquisition, edge detection, printed line displacement measurement (sub-millimeter print registration), and recipe verification.

```
       +-------------------------------------------------------------+
       |                  800x480 TOUCHSCREEN HMI                    |
       |     (Thin Display & Input Layer - Zero Client Logic)        |
       +------------------------------+------------------------------+
                                      | HTTP REST / SSE / Stream
                                      v
       +-------------------------------------------------------------+
       |             PYTHON EMBEDDED SERVER (server.py)             |
       |  - Authoritative Machine State  - SQLite Store (DB)         |
       |  - Passcode Verification        - Report Generation         |
       |  - Modbus Register Sync         - Camera Service Thread     |
       +---------------+------------------------------+--------------+
                       |                              |
      Modbus RTU RS-485|                              | CSI / USB
       (9600-8O1 Serial)                              | Video Frames
                       v                              v
       +------------------------------+ +----------------------------+
       |    FBARX / REGISMATIC PCB    | |      RICEVISION AOI        |
       |  - Unwind Tension / Brakes   | |  - Sub-pixel Line Tracker  |
       |  - Registration Servos / Eyes| |  - Front vs. Back Skew     |
       |  - Hardware Pulse Counters   | |  - Recipe SIFT Matcher     |
       +------------------------------+ +----------------------------+
```

### Server-Authoritative Architecture
All application state, business logic, calculations, passcode checks, hardware communication, and image analysis reside strictly in the Python backend (`server.py`, `fbarx_link.py`, `camera.py`, `vision.py`). 
* **Zero Browser State**: `index.html` holds no application variables in `localStorage`, cookies, or JS closures.
* **Synchronized Multi-Client Viewing**: Refreshing the browser or connecting a second tablet/terminal displays the exact authoritative machine state instantly.
* **Deterministic Verification**: No client-side optimistic UI spoofing—changes are displayed only after confirmation by the backend and physical controller.

---

## 2. Station 1: Unwind Tension Controller (STN 1)

Station 1 manages the unwind reel of the bag conversion machine, ensuring the web enters the printing and cutting rollers under constant, jitter-free tension.

### 2.1 Operating Modes & Interlock Rules
Station 1 operates in three distinct, mutually exclusive modes:
* **AUTO**: Closed-loop PID tension regulation. The controller continuously reads the analog loadcell tension feedback and modulates the brake output to maintain the tension setpoint.
* **MAN (Manual)**: Open-loop fixed output. The closed-loop algorithm is bypassed, and the operator manually steps or enters the brake output percentage ($0.0\%$ to $100.0\%$).
* **OFF**: Complete system shutdown. Brake output is clamped to $0.0\%$. Tension alarms and steppers are interlocked and disabled.

### 2.2 S-Tension (Setpoint) & A-Tension (Feedback)
* **S-Tension (Set Tension)**: The target web tension defined by the operator or active recipe. Valid range: `0.0` to `50.0` (in selected units).
* **A-Tension (Actual Tension)**: Live filtered tension feedback measured from dual strain-gauge loadcells. Displayed with a tolerance band (e.g. $\pm 0.2\text{ kg}$). If the actual tension deviates outside acceptable process thresholds, visual warnings are displayed on the ammeter and status chips.

### 2.3 Unit Toggle (KG ↔ N)
The operator can switch engineering units between **Kilograms-force (KG)** and **Newtons (N)** with a single touch:
* **Internal Conversion**: The server stores tension in metric kilograms and dynamically scales display values:
  $$\text{Value (N)} = \text{Value (KG)} \times 9.80665$$
* **Authoritative Persistence**: The selected unit (`KG` or `N`) is stored in the database `machine_state` table and echoed across all client screens.

### 2.4 Manual Steppers & Output Power Regulation
When Station 1 is in **MAN** mode, fine output adjustments can be executed via on-screen incremental stepper buttons:
* **Up Button (`▲`)**: Steps the output power up by $+1.0\%$.
* **Down Button (`▼`)**: Steps the output power down by $-1.0\%$.
* **Interlock Protection**: Attempting to click steppers while in `AUTO` or `OFF` mode is rejected by the server (`HTTP 400: STN 1 output can only be stepped in MAN mode`).

### 2.5 Brake Selection: Powder Brake vs. Pneumatic Brake
The HMI supports two industrial brake actuation systems via a radio-style selector:
1. **Magnetic Particle / Powder Brake**:
   * Uses an electromagnetic coil with magnetic powder to generate torque proportional to DC coil current.
   * Enables the **Brake Current Set** parameter ($0.0\text{ to }5.0\text{ A}$) and **Brake Power Set** ($0\text{ to }100\%$).
2. **Pneumatic Brake**:
   * Uses compressed air modulated through an electro-pneumatic transducer ($0-10\text{ V} \rightarrow 0-6\text{ bar}$).
   * Automatically locks powder-specific current adjustments, maintaining the last configured baseline while preventing conflicting electrical commands.

### 2.6 Calibration & Closed-Loop Control Parameters
Accessing STN 1 Calibration allows qualified technicians to tune PID closed-loop dynamics:
* **Proportional Band ($P$)**: Controls the immediate proportional braking response ($1.0\text{ to }100.0\%$).
* **Reset Time ($I$)**: Eliminates steady-state tension offset error ($0.1\text{ to }99.9\text{ s}$).
* **Rate Time ($D$)**: Dampens high-speed web tension oscillation during reel splices ($0.0\text{ to }10.0\text{ s}$).
* **Loadcell Zero & Span Calibration**: Two-point calibration (Zero tare with empty web, Span weight calibration using certified test weights) stored in `calibration_store`.

---

## 3. Station 2: REGISMATIC Registration Controller (STN 2 / FBARX)

Station 2 synchronizes the longitudinal registration of the printed rice sack with the cross-cutting and perforation knife. It interfaces directly with the proprietary **FBARX REGISMATIC (RMV14_1)** controller over Modbus RTU.

### 3.1 Serial Architecture & Single-Queue Modbus RTU
To guarantee deterministic execution on half-duplex RS-485 lines, the backend implements a **single serial request queue** (`queue.Queue`):
* **Baud & Framing**: `9600 baud`, `8 data bits`, `Odd Parity (8O1)`, `1 stop bit`, `Slave Address 1`.
* **Zero Bus Contention**: Cyclic status reads (R1 every 200 ms, R2 live job counters) and operator writes (W1–W27) execute sequentially through a dedicated worker thread, completely preventing collided frames.
* **Poll Latency Diagnostics**: Instantaneous round-trip time (`pollLatencyMs`) and rolling averages are calculated continuously to detect RS-485 bus noise or wiring degradation.

```
       +--------------------------------------------------------+
       |           CYCLIC MODBUS RTU READ POOL (5 Hz)           |
       +--------------------------------------------------------+
       | R1: Status Block (Regs 0-30, FC 03)                    |
       |     - Error (0), Error Valid (1), M1/M2 Marks (2-5)    |
       |     - Output (6), Speed (8), Repeat Set/Actual (9-11)  |
       |     - Mode (14/15), Alarms (18), FW Version (19)       |
       |     - Mark Window (20), Mark Offset (21)               |
       | R2: Live Job Row (Regs 100-107, FC 03)                 |
       |     - Total Bags (100), Auto Bags (101), Waste % (102) |
       +--------------------------------------------------------+
```

### 3.2 Operating Modes (AUTO / MAN / OFF)
* **AUTO (Reg 15 = 1)**: Autonomous optical registration. The board reads eye sensors M1 and M2, calculates error relative to the mark window, and pulses advance/retard servo motors to center the print mark.
* **MAN (Reg 15 = 0)**: Manual jog mode. Automatic correction is disabled; operators can jog output power or run manual tests.
* **OFF (Reg 15 = 2)**: All registration motor outputs and optical scanning are deactivated. Registration error shows `REP: --- mm`.

### 3.3 Cylinder Repeat Length & Mark Window Dynamics
* **Repeat Length Set (Reg 9)**: Nominal bag cut length in millimeters. Valid range: `100` to `1500 mm`. Standard rice bags default to `740 mm`.
* **Repeat Length Actual (Regs 10–11, 32-bit)**: Physical web travel between registration marks measured by the high-resolution encoder pulses (e.g., `740.6 mm`).
* **Mark Window (Reg 20)**: The optical acceptance gate around the expected mark position (`10` to `99 mm`, typically `40 mm`). Any mark detected outside this window is rejected as spurious background noise.

### 3.4 Mark Offset Adjustment (-999 mm to +999 mm)
* **Register 21**: Signed 16-bit two's complement integer representing physical print shift compensation.
* Allows operators to compensate for cylinder plate mounting offsets without physically repositioning the optical eye brackets:
  $$\text{Example: } -12\text{ mm} \rightarrow \mathtt{0xFFF4}$$

### 3.5 Optical Sensors M1 & M2 (Status & Mark Counting)
* **M1 (Front Eye) & M2 (Back Eye)**: Dual high-speed optical contrast sensors (typically white/blue LED or laser).
* **Live Telemetry**: The HMI displays sensor health (`OK` vs. `ERR`) and the exact number of marks captured within each cylinder revolution (`marks = 1`). A count $\ne 1$ immediately flags missing mark or double-mark alarms.

### 3.6 Hardware Control Commands (CLR, SCAN, NEW JOB, LOGOUT)
Writes to Command Register 17 trigger specialized board subroutines:
* **CLR (Val 1)**: Clears latching hardware alarms (B2B, Skip Bag, Encoder error).
* **SCAN (Val 2)**: Re-scans optical mark thresholds across one cylinder revolution.
* **NEW JOB (Val 3)**: Zeroes hardware bag counters (Regs 100–102) and resets server-side job statistics.
* **LOGOUT (Val 5)**: Immediately re-locks the physical board password and expires HMI calibration session tokens.

### 3.7 Indicative Ammeter & Motor Speed Telemetry
* **Ammeter Display**: Read-only display of drive motor load (Reg 82, scaled $\div 100\text{ A}$, e.g. `2.45 A`).
* **Line Speed**: Real-time production velocity calculated from encoder pulse frequency (Reg 8, expressed in meters per minute, `MPM`).

### 3.8 Dynamic Bag Counter Bands & Industrial Half-Up Rounding
Every manufactured bag is graded into precise registration quality bins based on its absolute error $|e|$:
1. **0 to 7 mm**: Premium Pass. Excellent registration alignment.
2. **8 to 15 mm**: Acceptable Pass. Minor drift within commercial tolerances.
3. **16 to 25 mm**: Warning / Borderline. Web tension or slip correction required.
4. **26+ mm to Mark Window**: Out of Spec / Waste. Mark displaced beyond allowable limits.
5. **Unscored**: Sensor miss, double-mark, or invalid detection window.

#### Industrial Half-Up Rounding Rule
To prevent floating-point flicker on bin boundaries:
$$\text{Rounded Error} = \lfloor |e| + 0.5 \rfloor$$
* `7.4 mm` rounds to `7 mm` $\rightarrow$ classified into **0–7 mm band**.
* `7.5 mm` rounds to `8 mm` $\rightarrow$ classified into **8–15 mm band**.

### 3.9 STN 2 Deep Calibration & Board Password Protection
Protected by hardware key (Reg 30 `1212`) and server passcode (`3333`):
* **ACerr (Reg 71)**: Proportional error correction gain ($0.1\text{ to }99.9\%$, scaled $\times 10$).
* **DCerr (Reg 72)**: Integral correction gain ($0\text{ to }999\text{ counts}$).
* **SPKerr (Reg 73)**: Velocity feedforward damping ($0\text{ to }999\text{ counts}$).
* **Encoder PPR Set (Reg 70)**: Encoder pulses per cylinder revolution ($100\text{ to }9999\text{ pulses}$, default `5000`).
* **Cylinder Circumference (Reg 40)**: Printing cylinder outer circumference ($50\text{ to }9999\text{ mm}$, default `1570 mm`).
* **B2B Alarm (Reg 43)**: Bag-to-bag registration jump alarm threshold ($5\text{ to }25\text{ mm}$).
* **Skip Bag Alarm (Reg 75)**: Consecutive missing marks before machine emergency stop ($1\text{ to }9\text{ bags}$).
* **Available Brake Capacity**: Real-time dynamic calculation:
  $$\text{Available Capacity (kgm)} = \frac{\text{Capacity (kgm)} \times \text{Power (\%)}}{100}$$

---

## 4. Computer Vision & Optical Inspection Engine (RiceVision)

The RiceVision module provides independent, camera-based optical verification to measure registration accuracy and detect bag skew.

```
+-------------------------------------------------------------------------+
|                  RICEVISION OPTICAL PIPELINE (vision.py)                |
+-------------------------------------------------------------------------+
| [Full Frame 1600x1200]                                                  |
|       |                                                                 |
|       v                                                                 |
| [ROI Cropping: Front Line Window & Back Line Window]                    |
|       |                                                                 |
|       v                                                                 |
| [Adaptive Contrast / Edge Profiler]                                    |
|   - Sobel Gradients across Y-axis                                       |
|   - Sub-pixel Gaussian Centroid Peak Detection                          |
|       |                                                                 |
|       v                                                                 |
| [Net Displacement Calculation]                                          |
|   Δy_net = (y_back - y_front) - nominal_px - zero_offset                |
|   error_mm = Δy_net / scale_px_per_mm                                   |
|       |                                                                 |
|       v                                                                 |
| [Quality Assessment: PASS (≤ 7.0 mm) | SKEW ANGLE | RECIPE SIFT MATCH]  |
+-------------------------------------------------------------------------+
```

### 4.1 Dual-Source Video Pipeline (Pi CSI & OpenCV USB)
The backend (`camera.py`) dynamically binds to the optimal video backend:
1. **Raspberry Pi Camera (CSI)**: Direct hardware capture via `libcamera` / `picamera2` at up to 25 FPS with microsecond exposure tuning.
2. **Industrial USB (UVC)**: Automated fallback to OpenCV `VideoCapture` utilizing hardware `MJPG` fourcc decompression for low latency and zero frame drops.
3. **Condition Synchronization (`threading.Condition`)**: Thread-safe frame delivery. Consumers block on `wait_new(last_id)` and wake up instantaneously upon sensor frame capture.

### 4.2 Registration Line Edge Detection & Net Displacement
1. **Regions of Interest (ROIs)**: Front line and back line inspection regions are isolated.
2. **Contrast Inversion (Dark vs. Light)**: Configurable polarity handles black registration marks on white bags or transparent/metallic printed markers.
3. **Centroid Peak Extraction**: Computes vertical sub-pixel gradient centroids:
   $$y_{\text{peak}} = \frac{\sum y \cdot I(y)}{\sum I(y)}$$
4. **Net Displacement & Zero Offset**:
   $$\Delta y_{\text{net}} = (y_{\text{back}} - y_{\text{front}}) - \text{nominal\_px} - \text{zero\_offset}$$
   $$\text{Registration Error (mm)} = \frac{\Delta y_{\text{net}}}{\text{scale\_px\_per\_mm}}$$

### 4.3 Dual-Bag Analysis (Front Bag vs. Back Bag)
* Measures relative skew across the bag width (Top-Left, Top-Right, Bottom-Left, Bottom-Right tracking points).
* Identifies printing cylinder taper, uneven nip-roller pressure, or diagonal web wandering.

### 4.4 SIFT & Template Matching Recipe Verification
* Extracts scale-invariant feature transform (SIFT) keypoints and descriptors from captured bag images.
* Matches descriptors against pre-registered database recipe templates using FLANN-based nearest neighbor matching.
* Verifies that the correct rice brand bag is threaded on the machine before high-speed printing starts, preventing catastrophic packaging mix-ups.

### 4.5 Safe-State Video Streaming (`/api/camera/stream`)
* Streams multipart MJPEG (`multipart/x-mixed-replace`) over HTTP.
* **No Phantom Frames**: If the camera is unplugged or fails initialization, the server returns `HTTP 503 Service Unavailable` instead of generating misleading fake frames.
* **Explicit Simulation Watermark**: When `FBARX_SIM=1` is deliberately enabled for bench testing, all served video frames are stamped with a high-contrast **"SIMULATED"** warning banner.

---

## 5. Recipe Management & Master Profile Store

The Recipe Management system enables rapid job changeovers with single-touch loading of mechanical, tension, and optical parameters.

```
       +-------------------------------------------------------------+
       |                  RECIPE DATA MODEL (recipes)                |
       +-------------------------------------------------------------+
       | - Name / Brand Tamil Text (e.g. "Veera Sivaji", "Ponni")    |
       | - Repeat Length (100 - 1500 mm)                             |
       | - Width (100 - 1000 mm)                                     |
       | - Mark Window (10 - 99 mm) & Mark Offset (-999 to +999 mm)  |
       | - S-Tension Target (0.0 - 50.0 kg)                          |
       | - Bag Net Weight (1 - 100 kg, e.g. 25 kg, 50 kg)            |
       | - Material (BOPP, HDPE, PP, Woven Sack)                     |
       | - Front / Back Sensor Thresholds                            |
       | - High-Resolution Master Reference Images (Front & Back)   |
       +-------------------------------------------------------------+
```

### 5.1 Recipe Database Structure & Parameter Binding
Stored in SQLite table `recipes` with unique identifiers and revision timestamps. Modifying or loading a recipe triggers automatic parameter validation in `server.py` before hardware registers are synchronized.

### 5.2 Master Reference Images (Front & Back Clarified JPEGs)
* Each recipe stores two full-clarity JPEG master images: **Front Bag Face** and **Back Bag Face**.
* Displayed in thumbnail preview boxes on the main screen and expanded during recipe calibration.
* Used as baseline templates by `vision.py` for automated optical alignment and defect comparison.

### 5.3 Recipe Selection, Editing, and Hardware Synchronization
* **Recipe Modal**: Operators browse recipes via carousel cards, alphabetical dropdowns, or thumbnail visual grids.
* **Confirm & Load Flow**:
  1. Operator taps **Confirm & Load**.
  2. Server updates `machine_state` active recipe pointer.
  3. Server commands `fbarx_link` to write new repeat length (Reg 9), mark window (Reg 20), mark offset (Reg 21), and tension (Reg 74).
  4. Camera service swaps reference template images.
  5. Current job auto-closes and a new production batch begins.

---

## 6. Operator Management & Verification

### 6.1 Independent Operator Directory
Operators are maintained in a dedicated SQLite table `operators`, separate from recipe configurations:
* **Operator Fields**: ID, Operator Name, Badge ID, Skill Tier, Profile Photo Path, Active Flag.
* Eliminates the need to re-enter personnel information when defining new recipes.

### 6.2 Operator Selection & Visual Face Verification
During shift changes or job start, operators can authenticate via three flexible workflows:
1. **Dropdown / List Selection**: Direct selection from the authorized personnel roster.
2. **Photo Carousel**: Touchscreen browsing of operator profile photographs.
3. **Live Camera Match**: Real-time snapshot captured by the camera and compared against the operator's stored profile photo for identity verification.

---

## 7. Production Reporting & Quality Intelligence

The reporting engine continuously aggregates production metrics and archives quality records into SQLite table `reports` (`production_records`).

```
+-------------------------------------------------------------------------+
|                  PRODUCTION REPORT DASHBOARD & EXPORT                   |
+-------------------------------------------------------------------------+
|  Active Job: "Veera Sivaji 25kg"  | Operator: Ramesh M.                 |
|  Start: 2026-11-14 06:00:00       | Duration: 04h 22m 18s               |
+-------------------------------------------------------------------------+
|  TOTAL BAGS: 18,450               | AUTO RUN BAGS: 18,120               |
|  WASTE BAGS: 330 (1.79%)          | PASS RATE: 98.21%                   |
+-------------------------------------------------------------------------+
|  QUALITY DISTRIBUTION BANDS:                                            |
|   [0 - 7 mm]   : 17,210 bags (93.28%) -> Optimal Alignment              |
|   [8 - 15 mm]  :    910 bags  (4.93%) -> Minor Acceptable Drift         |
|   [16 - 25 mm] :    190 bags  (1.03%) -> Borderline Warning             |
|   [26+ mm]     :    140 bags  (0.76%) -> Out of Spec Cut                |
+-------------------------------------------------------------------------+
```

### 7.1 Real-Time Job Tracking & Timestamps
* **Start Time**: Timestamped automatically when a recipe is loaded or **NEW JOB** is clicked.
* **End Time**: Closed automatically upon shift logout or when the next recipe batch loads.
* **Elapsed Duration**: Displayed in `HH:MM:SS` format, counting only active machine run hours.

### 7.2 Statistical Quality Metrics & Yield Calculations
* **Total Bags ($N_{\text{total}}$)**: Cumulative cut count read from board Reg 100.
* **Auto Bags ($N_{\text{auto}}$)**: Count of bags manufactured while in active `AUTO` registration (Reg 101).
* **Waste Percentage**: Real-time scrap yield metric:
  $$\text{Waste \%} = \frac{N_{\text{total}} - N_{\text{auto}}}{N_{\text{total}}} \times 100\%$$
* **Pass Percentage**: Bags conforming within $\le 7.0\text{ mm}$ registration tolerance.

### 7.3 Historical Report Archives & Filtering
* Operators and plant managers can filter archived jobs by **Date Range (Calendar Pickers)**, **Recipe Name**, or **Operator Name**.
* Historical records store the exact dynamic band edges and mark window active at the time of manufacturing, ensuring compliance reporting integrity.

### 7.4 CSV / Excel Export with Embedded Audit Metadata
* **One-Click Export**: Downloads standard `.csv` or formatted spreadsheet files.
* **Audit Metadata**: Includes Job ID, Recipe Name, Bag Weight, Material, Operator Name, Machine Speed, Cumulative Band Totals, Waste %, and referenced master image filenames.

---

## 8. Security, Safety, & Diagnostics

### 8.1 Multi-Tier Passcode Verification (`3333` / `4444`)
To prevent unauthorized modification of critical servo and PID settings:
* **STN 2 Deep Calibration**: Requires Passcode **`3333`**.
* **Recipe Master Database Calibration**: Requires Passcode **`4444`**.
* **Zero Client Passcode Exposure**: All passcode verification occurs on `server.py` via `POST /api/login`. No passcode hashes or strings exist in frontend JavaScript.

### 8.2 Session Tokens & 5-Minute Inactivity Timeout
* Upon valid passcode entry, the server returns an ephemeral cryptographically secure 128-bit session token (`secrets.token_hex(16)`).
* Tokens automatically expire after **300 seconds (5 minutes)** of inactivity, synchronizing with physical Modbus board timeout rules.

### 8.3 Calibration Audit Trail
Every parameter change is logged into database table `audit_log`:
* **Columns**: `id`, `timestamp`, `operator`, `station`, `field`, `old_value`, `new_value`, `status`, `client_ip`.
* Provides complete traceability during plant quality audits.

### 8.4 Safe-State Operation & Simulation Watermark
* **Production Safe Default**: Simulation defaults to `OFF`. If the physical RS-485 link is disconnected, all outputs clamp to zero power, preventing runaway roller conditions.
* **Visible Watermark**: If simulation is explicitly enabled (`FBARX_SIM=1`), an amber/red top banner states:
  `⚠️ SIMULATION ACTIVE — SENSOR DATA IS VIRTUAL (NOT FROM HARDWARE BOARD)`

### 8.5 Connection Watchdog & Instant Reconnect Loop
* **Client Watchdog**: Frontend polls `/api/state` every 250 ms. If the server fails to reply within 2.0 seconds, a full-viewport red warning banner appears:
  `SERVER NOT CONNECTED`
* **Auto-Reconnect Daemon**: If serial communications drop, `fbarx_link` auto-closes the socket/COM port and initiates an non-blocking reconnection attempt every 2.0 seconds.

---

## 9. RESTful API Architecture & Endpoint Reference

The entire system communicates via standard JSON REST endpoints hosted on `server.py`:

| Method | Endpoint | Description | Request Payload / Query | Response Structure |
|---|---|---|---|---|
| `GET` | `/api/state` | Full authoritative machine snapshot | *None* | `{ok: true, state_version: 142, server_start_id: "...", stn1: {...}, stn2: {...}, job: {...}, counters: {...}, camera: {...}}` |
| `POST` | `/api/action` | Central action dispatcher for machine control | `{action: "...", params...}` | `{ok: true, state: <updated_full_state>}` |
| `POST` | `/api/login` | Authenticate calibration access | `{type: "stn2_cal"|"recipe_cal", passcode: "3333"}` | `{ok: true, token: "d8f3a..."}` |
| `GET` | `/api/calibration` | Read stored station & camera calibrations | *None* | `{ok: true, calibration: {stn1_control: {...}, stn2: {...}, camera: {...}}}` |
| `POST` | `/api/calibration` | Save calibrated engineering parameters | `{category: "...", data: {...}}` | `{ok: true, calibration: {...}}` |
| `GET` | `/api/recipes` | List all available bag recipes | *None* | `{ok: true, recipes: [...]}` |
| `POST` | `/api/recipes` | Save or update recipe definition | `{name: "...", repeatLength: 740, ...}` | `{ok: true, recipe_id: 12}` |
| `POST` | `/api/recipes/delete` | Remove recipe profile | `{recipe_id: 12}` | `{ok: true}` |
| `GET` | `/api/operators` | List personnel directory | *None* | `{ok: true, operators: [...]}` |
| `GET` | `/api/report` | Fetch pre-aggregated quality report | `?start=...&end=...` | `{ok: true, summary: {total_bags: 18450, pass_pct: 98.2, ...}, records: [...]}` |
| `GET` | `/api/camera/stream` | Live multipart/x-mixed-replace MJPEG stream | *None* | Binary image stream (`image/jpeg`) |
| `GET` | `/api/camera/snapshot`| Capture single full-resolution frame | *None* | Binary image (`image/jpeg`) |
| `POST` | `/api/camera/match` | Perform SIFT/Template matching | `{}` | `{ok: true, result: "MATCH_CONFIRMED", recipe_id: 4}` |

---

## 10. Hardware Deployment & Operating Environments

### 10.1 Raspberry Pi 5 Embedded Deployment
* **OS**: 64-bit Raspberry Pi OS (Debian Bookworm).
* **Display**: 7-inch or 10.1-inch industrial capacitive touchscreen (800×480 or 1280×800) in Chromium Kiosk Mode.
* **Camera**: Raspberry Pi Camera Module 3 (Sony IMX708, autofocus, wide-angle lens).
* **Systemd Service (`/etc/systemd/system/ricevision.service`)**: Automatically boots and recovers on power-cycling.

### 10.2 Ubuntu Server & Cloud / Cloudflare Tunnel
* For remote plant monitoring and diagnostics:
  ```bash
  # Start both Modbus Simulator (port 5020) and Server (port 11111) via PM2:
  chmod +x run_ubuntu.sh
  ./run_ubuntu.sh start
  ```
* Seamless remote connectivity via Cloudflare Tunnel (`cloudflared`) with zero router port forwarding required.

### 10.3 Windows Desktop & Bench Testing
* Pure standard Python virtual environment (`python -m venv venv`).
* Simulated Modbus bridge enabled via `$env:FBARX_SIM="1"`, allowing full UI development, testing, and recipe management without physical board connectivity.
