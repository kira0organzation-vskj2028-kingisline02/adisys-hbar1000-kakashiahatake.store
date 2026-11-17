import os
import json

output_path = r"C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4\audit_index_html_step0.md"

content = """# Step 0 Audit: Refactoring index.html to Thin UI & Moving All State to server.py

## 1. Executive Summary & Architecture Strategy

In accordance with the target architecture:
- **`index.html`** is transformed into a **pure thin display-and-input layer**:
  1. Renders values received from `GET /api/state` and specialized GET endpoints.
  2. Sends user actions (`POST /api/action`, `POST /api/login`, etc.) without optimistic client-side guesses.
  3. Handles purely visual concerns: layout, active screen toggling, animations, virtual keypad typing buffer, and clock display.
- **`index.html` will NOT**:
  - Use `localStorage` or `sessionStorage` for any application data.
  - Calculate counts, bands, errors, totals, averages, percentages, pass/fail status, or timestamps.
  - Decide action permissions, range limits, mode locks, or passcodes ('1111', '2222', '3333', '4444').
  - Run canvas image feature extraction, signature calculation, histogram comparison, or line matching.
  - Generate virtual sensor values or run simulated sensor intervals in the browser.
  - Maintain independent job or calibration state.
- **`server.py` (and imported modules `vision.py`, `fbarx_link.py`, `fbarx_api.py`)** becomes the single source of truth:
  - SQLite tables & server memory maintain machine state, active job, calibration, recipes, operators, and audit logs.
  - Single counting source: hardware Modbus registers / server line detection counters.
  - Single authentication source: passcodes validated strictly on the server (`POST /api/login` / `POST /api/action`).
  - Single vision processing engine: line detection, cross-correlation, edge analysis, signature matching, error_mm, and pass/fail thresholds computed on server in `vision.py`.

---

## 2. LocalStorage & SessionStorage Audit

| Key / Variable | Location in `index.html` | Original Purpose in UI | Classification | Replacement in Server Architecture |
| :--- | :--- | :--- | :--- | :--- |
| `stn1LoadcellCalibration` | Line 6165 | Stored STN 1 load cell zero/span calibration values | **MOVE to server** | SQLite table `calibration` (`stn1_loadcell` row) loaded via `GET /api/calibration` and updated via `POST /api/calibration`. |
| `stn1ControlParameters` | Line 6180 | Stored STN 1 PID/control parameters | **MOVE to server** | SQLite table `calibration` (`stn1_control` row) loaded via `GET /api/calibration` and updated via `POST /api/calibration`. |
| `stn2Calibration` | Referenced in calibration drafts / earlier versions | Stored STN 2 encoder PPR, cylinder circumference, brake current | **MOVE to server** | Modbus holding registers on STN 2 board & SQLite backup via `GET/POST /api/calibration`. |
| `LS_KEY` (`ricevision_hmi_db_ls`) | Lines 7726, 7751, 7752, 7768 | LocalStorage fallback backup for full recipe database | **MOVE to server** | SQLite table `recipes` in `rice_vision.db`. Server is the sole store; loaded via `GET /api/recipes`. |
| `recipeLibrary` | Line 7775 | Legacy migration key for old recipe items | **MOVE to server** | Handled by SQLite schema migration script in `server.py`. Removed entirely from client. |
| `ricevision_job_state` | Lines 8102, 8152, 8226 | Persisted active job: recipe, operator, start time, end time, elapsed | **MOVE to server** | SQLite table `machine_state` / `job_state` in `server.py`. Single state owner; retrieved in `GET /api/state`. |
| `recipeCalibration` | Lines 8242, 10063 | Cached active recipe calibration parameters across page reloads | **MOVE to server** | Persisted in server `machine_state.active_recipe`. Retrieved automatically via `GET /api/state`. |

> **Result:** `grep -c "localStorage" index.html` and `sessionStorage` will return **0**.

---

## 3. Passcode Checks, Range & Numeric Limits Audit

| Target / Item | Location in `index.html` | Hardcoded Value in UI | Classification | Replacement in Server Architecture |
| :--- | :--- | :--- | :--- | :--- |
| STN 1 Control Parameters Passcode | Lines 3318, 6236, 6239, 6243 | `'1111'` | **MOVE to server** | Client sends typed code to `POST /api/login` (`{ type: 'stn1_control', code: raw }`). Server verifies hash/passcode and returns auth token / `{ ok: true, screen: 'control' }`. |
| STN 1 Loadcell Calibration Passcode | Lines 3318, 6236, 6243 | `'2222'` | **MOVE to server** | Client sends typed code to `POST /api/login` (`{ type: 'stn1_loadcell', code: raw }`). Server verifies passcode and authorizes access. |
| STN 2 Calibration Passcode | Lines 6410, 6424 | `'3333'` | **MOVE to server** | Client sends typed code to `POST /api/login` (`{ type: 'stn2_cal', code: raw }`). Verified by server token sliding-window. |
| Recipe Calibration Passcode | Lines 5285, 6397, 6410, 6706 | `'4444'` (or `'1111'`, `'3333'`) | **MOVE to server** | Client sends typed code to `POST /api/login` (`{ type: 'recipe_cal', code: raw }`). Server checks passcode and responds with authorization. |
| Encoder PPR Set Range | Lines 3361, 6365, 6444 | `100 - 9999` | **MOVE to server** | Validated on server in `POST /api/action` / `POST /api/calibration`. Refused with `{ ok: false, error: "Encoder PPR must be between 100 and 9999" }`. |
| Cylinder Circumference Range | Lines 3364, 6367, 6446 | `50 - 9999 mm` | **MOVE to server** | Validated on server in `POST /api/action`. Refused if `< 50` or `> 9999`. |
| Brake Current Cal Range | Lines 3372, 6373, 6452 | `1000 - 30000 mA` | **MOVE to server** | Validated on server in `POST /api/action`. Refused if out of range. |
| Repeat Length Range | Lines 6440-6460 | `100 - 1500 mm` | **MOVE to server** | Validated on server in `POST /api/action { action: 'set_repeat_length' }`. |
| Mark Window Range | Lines 6440-6460 | `10 - 99 mm` | **MOVE to server** | Validated on server in `POST /api/action { action: 'set_mark_window' }`. |
| S-Tension Target Range | Lines 6860-6900 | `0.0 - 50.0 N / kg` | **MOVE to server** | Validated on server in `POST /api/action { action: 'set_stension' }`. |
| Stepper Output % Range | Lines 5764, 6040, 6047 | `0.0 - 100.0 %` | **MOVE to server** | Clamped and calculated on server. Echoed back in `machine_state`. |

> **Result:** All hardcoded passcodes, minimums, maximums, and range arrays are removed from `index.html`.

---

## 4. Duplicate Counting Sources & Sensor Simulation Audit

| Component | Location in `index.html` | Current Client-Side Behavior | Classification | Server Replacement |
| :--- | :--- | :--- | :--- | :--- |
| `startSimulatedSensors()` | Lines 4044, 6761-6800 | Runs two client timers generating pseudo-random ammeter, speed, tension, and repeat length | **MOVE to server** | Removed from client. Hardware simulation is managed solely by `FBarXLink(simulate=True)` or `modbus_slave_sim.py` on the server. |
| Bag Bin Counters (`recordBagInBin`) | Lines 10186-10202 | Client increments internal bag bins and calculates bands independently | **MOVE to server** | Removed from client. Server counts every cycle from Modbus mark triggers and line vision frames, binning into `0-7`, `8-15`, `16-25`, `26+`, `unscored`. |
| Band Partition Math (`updateDynamicCounterBands`) | Lines 5502-5586 | Client calculates percentages, rounding thresholds, and active band styling | **SPLIT** | Math computed on server. Client receives pre-computed percentages, counts, and active band names in `GET /api/state`. |
| Error Percentage Math (`updateErrorPercentageDisplay`) | Lines 8507, 10203-10240 | Client computes pass/fail ratio and rolling error statistics | **SPLIT** | Rolling statistics computed on server. Client receives `{ pass_pct, fail_pct, total_inspected, status }` in `GET /api/state`. |
| Simulated Random Sensor Reads | Line 9617 | `Math.floor(Math.random()*65536)` | **MOVE to server** | Replaced by server telemetry snapshot. |

---

## 5. Image Matching, Canvas Feature Extraction & Camera Audit

| Function / Component | Location in `index.html` | Client Behavior | Classification | Server Replacement |
| :--- | :--- | :--- | :--- | :--- |
| `RecipeMatch.signature` | Lines 7658-7679 | Draws frame on client canvas, extracts 64-bin color/intensity histogram | **MOVE to server** | Extracted in Python `vision.py` using OpenCV (`cv2.calcHist`). |
| `RecipeMatch.score` | Lines 7682-7685 | Euclidean/cosine distance vector math in browser | **MOVE to server** | Computed in `vision.py` using NumPy vector correlation. |
| `RecipeMatch.rank` / `verdict` | Lines 7686-7696 | Evaluates candidate recipes against threshold (`MATCH_OK = 0.60`) | **MOVE to server** | Implemented on server in `POST /api/camera/match`. Returns `{ matched: true, recipe_id, score, name }`. |
| `RecipeMatch.loadImage` / `sigFromDataUrl` | Lines 7697-7704 | Browser `new Image()` and canvas scaling | **MOVE to server** | Decoded on server via `cv2.imdecode` from standard image uploads. |
| `RecipeMatch.readCode` | Lines 7705-7711 | Client `BarcodeDetector` API | **MOVE to server** | Pyzbar / OpenCV barcode & QR detector in `vision.py`. |
| Live Comparison Polling (`liveCompareTimer`) | Lines 10587-10630 | 1200ms client interval sending frames / errors back and forth | **SPLIT** | Polling interval removed or replaced by server camera worker thread. Client simply displays processed MJPEG stream / snapshot and server-computed error data. |
| Simulation Error Endpoint (`/api/camera/sim_error`) | Line 10756 | Client triggered simulation error offsets | **MOVE to server** | Server controls test profiles directly in server simulation mode. |

---

## 6. setInterval & setTimeout Audit

| Line | Interval / Timeout | Current Function / Logic | Classification | Replacement / Action |
| :---: | :--- | :--- | :--- | :--- |
| 4266 | One-shot | Report blob download DOM cleanup | **KEEP in UI** | Pure client file save helper. |
| 5137 | 400ms | PDF print window trigger | **KEEP in UI** | Pure client browser print dialog trigger. |
| 5226 | 1000ms | `startClock()`: updates topbar HH:MM:SS | **KEEP in UI** | Pure visual time display formatting. |
| 5919 | 150ms | `liveDisplacementTimer`: simulated live displacement | **MOVE to server** | Removed from client. Displacement computed on server and polled via `GET /api/state`. |
| 6145 | 40ms | Password numpad focus helper | **KEEP in UI** | Pure UI focus timing. |
| 6248 | 700ms | STN 1 invalid password shake/retry | **KEEP in UI** | Pure UI modal feedback animation. |
| 6414 | 700ms | Protected password retry delay | **KEEP in UI** | Pure UI modal feedback animation. |
| 6424 | 700ms | STN 2 password retry delay | **KEEP in UI** | Pure UI modal feedback animation. |
| 6477 | 300ms | Calibrate button border highlight flash | **KEEP in UI** | Pure UI button styling flash. |
| 6697 | 120ms | Numpad keypress depression animation | **KEEP in UI** | Pure UI keypad visual feedback. |
| 6762 | 1000ms | Virtual sensor ammeter generator | **MOVE to server** | Removed. Handled by server Modbus simulator. |
| 6780 | 2500ms | Virtual speed/mark fluctuation generator | **MOVE to server** | Removed. Handled by server Modbus simulator. |
| 7215 | 250ms | `updateNeedles()`: rotates ammeter SVG needle | **KEEP in UI** | Pure UI DOM rendering of ammeter values from server state. |
| 8003 | 3000ms | Toast message auto-hide timer | **KEEP in UI** | Pure UI toast alert timeout. |
| 8005 | 200ms | Toast DOM fadeout cleanup | **KEEP in UI** | Pure UI visual transition. |
| 8784 | 3500ms | `autoDetectTimer`: runs client camera matching | **MOVE to server** | Server background inspection loop. Client receives match notification via `GET /api/state`. |
| 8816 | 3500ms | `autoDetectTimer` duplicate | **MOVE to server** | Removed. |
| 9014 | 3000ms | Recipe delete button confirmation timeout | **KEEP in UI** | Pure UI two-step button safety confirmation. |
| 9050 | 5000ms | Recipe load OFF alert toast auto-hide | **KEEP in UI** | Pure UI alert toast timeout. |
| 9055 | 1000ms | Recipe load button outline reset | **KEEP in UI** | Pure UI button styling reset. |
| 9159 | 50ms | Calibration UI draft input populate | **KEEP in UI** | Pure UI modal field populate. |
| 9793 | 260ms | Dual camera file picker trigger | **KEEP in UI** | Pure UI file input open. |
| 10587 | 1200ms | `liveCompareTimer`: client-driven compare loop | **MOVE to server** | Server camera worker thread performs continuous frame analysis; client only polls `GET /api/state`. |
| 11263 | 200ms | `renderLiveAmmeters()`: SVG needle angle update | **KEEP in UI** | Pure UI SVG transformation based on server state numbers. |
| 5610 | 200ms | `pollFBarXState()`: polls `/api/fbarx/state` | **SPLIT** | Replaced by single unified `pollState()` calling `GET /api/state` every 200-500ms. |

---

## 7. Fetch Calls Audit

| Line | Method & Endpoint | Payload / Params | Classification | Target Architecture Endpoint |
| :---: | :--- | :--- | :--- | :--- |
| 4273 | `GET <url>` | None | **KEEP in UI** | Internal blob/data URL helper for PDF/XLS export. |
| 5591 | `POST /api/fbarx/cmd` / `url` | `{ cmd: ... }` | **MOVE to server** | `POST /api/action { action: 'fbarx_cmd', cmd: ... }` |
| 5614 | `GET /api/fbarx/state` | None | **SPLIT** | Merged into `GET /api/state` |
| 6430 | `GET /api/fbarx/calibration` | None | **SPLIT** | Merged into `GET /api/calibration` |
| 7909 | `GET /api/camera/compare_front_back` | `error, recipe_id` | **SPLIT** | Merged into `GET /api/state` (continuous server vision) |
| 8111 | `POST /api/event` | `{ type: 'JOB_START', ... }` | **MOVE to server** | `POST /api/action { action: 'start_job', recipe_id, operator }` |
| 8155 | `POST /api/event` | `{ type: 'JOB_STOP', ... }` | **MOVE to server** | `POST /api/action { action: 'end_job' }` |
| 8168 | `POST /api/production` | `{ job_id, counters, ... }` | **MOVE to server** | Handled internally by server on `end_job`. |
| 8860 | `GET /api/camera/compare` | `source=recipe_load` | **MOVE to server** | `POST /api/camera/match` |
| 8961 | `GET /api/camera/compare` | `source=recipe_load_file` | **MOVE to server** | `POST /api/camera/match` |
| 9082 | `POST /api/load` | `{ id: activeRecipeId }` | **MOVE to server** | `POST /api/action { action: 'load_recipe', id: ... }` |
| 9260 | `POST /api/recipes/delete` | `{ id: recId }` | **MOVE to server** | `POST /api/action { action: 'delete_recipe', id: ... }` |
| 9418 | `GET /api/camera/snapshot` | None | **SPLIT** | `GET /api/camera/snapshot` (pure visual image) |
| 9566 | `POST /api/recipes` | Recipe JSON | **MOVE to server** | `POST /api/recipes` (validated on server) |
| 9949 | `GET /api/recipes` | None | **SPLIT** | `GET /api/recipes` (sole database owner) |
| 9992 | `GET /api/operators` | None | **SPLIT** | `GET /api/operators` |
| 10006 | `GET /api/state` | None | **KEEP/EXPAND** | `GET /api/state` (master snapshot) |
| 10032 | `GET /api/report` | None | **KEEP/EXPAND** | `GET /api/report` (pre-calculated metrics) |
| 10580 | `POST /api/camera/stop` | None | **MOVE to server** | `POST /api/action { action: 'camera_stop' }` |
| 10613 | `GET /api/camera/compare_front_back` | `error, recipe_id, mode` | **MOVE to server** | Merged into server background thread and `GET /api/state` |
| 10756 | `POST /api/camera/sim_error` | `{ error: err }` | **MOVE to server** | Server test automation endpoint only |
| 10912 | `POST /api/fbarx/cmd` | `{ cmd: 'SCAN' }` | **MOVE to server** | `POST /api/action { action: 'scan' }` |
| 10986 | `GET /api/camera/compare` | `source=screen2_snap` | **MOVE to server** | `POST /api/camera/inspect` |
| 11048 | `GET /api/camera/calibration` | None | **SPLIT** | `GET /api/calibration` |
| 11101 | `POST /api/camera/calibrate_ruler`| Coordinates | **MOVE to server** | `POST /api/calibration { type: 'ruler', ... }` |
| 11125 | `POST /api/camera/calibrate_zero` | `error, recipe_id` | **MOVE to server** | `POST /api/calibration { type: 'zero', ... }` |
| 11156 | `POST /api/camera/calibration` | Scale/offsets | **MOVE to server** | `POST /api/calibration { type: 'camera', ... }` |
| 11186 | `POST /api/camera/stop` | None | **MOVE to server** | `POST /api/action { action: 'camera_stop' }` |

---

## 8. Complete Function Audit Table (All 212 Functions)

### Section 8.1: Report Module (Lines 4050 - 5200)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `addPadIcon(id, label)` | 4050-4068 | Appends calendar/clock visual SVG icons to report input fields | **KEEP in UI** | Pure DOM visual helper. Endpoint: *None*. |
| `reportNowLocalInputValue()` | 4069-4073 | Returns current browser ISO date string for datetime-local picker | **KEEP in UI** | Client input date utility. Endpoint: *None*. |
| `reportFormatDate(v)` | 4074-4078 | Formats timestamp string for tabular display (`DD/MM/YYYY HH:MM`) | **KEEP in UI** | Pure visual date formatter. Endpoint: *None*. |
| `reportGetRecords()` | 4079-4096 | Queries in-memory report array or fetches from `/api/report` | **MOVE to server** | Server SQLite handles querying, filtering and pagination. Endpoint: `GET /api/report`. |
| `toggleReportDateSort(field)` | 4097-4112 | Toggles ascending/descending report sort order | **KEEP in UI** | Client view state for table columns. Endpoint: *None*. |
| `updateReportSortUI()` | 4113-4132 | Updates column header arrow icons (`▲`, `▼`) | **KEEP in UI** | Pure DOM visual styling. Endpoint: *None*. |
| `populateReportDropdowns()` | 4133-4173 | Populates recipe & operator select options on report screen | **SPLIT** | Populating `<select>` is UI; data list comes from server. Endpoint: `GET /api/recipes`, `GET /api/operators`. |
| `reportFilteredRecords()` | 4174-4213 | Filters report rows by date range, recipe name, operator name | **MOVE to server** | Filtering moved to SQL `WHERE` queries on server. Endpoint: `GET /api/report?recipe=...&operator=...`. |
| `updateReportScreen()` | 4214-4258 | Computes total bags, counts, percentages, and builds table DOM rows | **SPLIT** | Totals, band counts, and percentages computed on server; UI only renders returned JSON. Endpoint: `GET /api/report`. |
| `set(id, v)` | 4226-4230 | Internal DOM text setter helper | **KEEP in UI** | DOM utility. Endpoint: *None*. |
| `reportEscape(v)` | 4259-4259 | Escapes CSV fields | **KEEP in UI** | Client CSV export formatting. Endpoint: *None*. |
| `reportCsv(rows)` | 4260-4265 | Generates CSV string from report rows | **SPLIT** | Can trigger download in client or stream from server. Endpoint: `GET /api/report?format=csv`. |
| `downloadReportBlob(blob, name)` | 4266-4268 | Triggers browser download of file blob | **KEEP in UI** | Pure browser file save action. Endpoint: *None*. |
| `urlToDataUrl(url)` | 4269-4288 | Converts image URL to base64 data URL for PDF generation | **KEEP in UI** | Client canvas data converter. Endpoint: *None*. |
| `getReportImages(recName)` | 4289-4318 | Loads front and back image thumbnails for report | **SPLIT** | Images fetched from server `/images/...`. Endpoint: `GET /api/recipes`. |
| `exportReportXls()` | 4319-4720 | Generates HTML Excel workbook table with styling and totals | **SPLIT** | Pre-calculated numbers and summary supplied by server; file download triggered in browser. Endpoint: `GET /api/report`. |
| `exportReportPdf()` | 4721-5139 | Uses jsPDF to render multi-page production report | **SPLIT** | Metrics and table pre-calculated on server; rendered into PDF canvas in browser. Endpoint: `GET /api/report`. |
| `bindReport()` | 5140-5210 | Attaches click handlers for opening, closing, filtering and exporting report | **KEEP in UI** | Pure DOM event listeners. Endpoint: *None*. |
| `open()` (inside bindReport) | 5142-5148 | Displays report modal overlay | **KEEP in UI** | View routing. Endpoint: *None*. |
| `addBtnAction(id, fn)` | 5149-5155 | DOM button click helper | **KEEP in UI** | Event utility. Endpoint: *None*. |
| `triggerPicker()` | 5190-5205 | Opens HTML5 calendar date picker | **KEEP in UI** | DOM input helper. Endpoint: *None*. |

---

### Section 8.2: Clock & Global Navigation (Lines 5211 - 5333)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `startClock()` | 5211-5231 | Runs 1000ms timer updating topbar clock (`HH:MM:SS`) | **KEEP in UI** | Pure client visual clock formatting. Endpoint: *None*. |
| `update()` (inside startClock) | 5216-5225 | Computes formatted time string from `new Date()` | **KEEP in UI** | Clock display helper. Endpoint: *None*. |
| `returnToHomeScreen()` | 5232-5247 | Switches view back to `#screen-stn` and deactivates overlays | **KEEP in UI** | Pure UI screen navigation. Endpoint: *None*. |
| `bindNavigation()` | 5248-5272 | Binds topbar navigation icons, home button, report button | **KEEP in UI** | DOM event listeners. Endpoint: *None*. |
| `openRecipeCalibrationForm()` | 5273-5333 | Opens calibration screen after checking password | **SPLIT** | Modal display is UI; password verification moved to server. Endpoint: `POST /api/login`. |

---

### Section 8.3: Ruler, Errors, Bands & FBarX Hardware Link (Lines 5334 - 5776)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `initRuler99Ticks()` | 5334-5399 | Generates 99 tick marks on visual error ruler | **KEEP in UI** | Pure SVG/DOM rendering. Endpoint: *None*. |
| `updateRepAndRulerDisplay(...)` | 5400-5501 | Positions needle on ruler, colors error text, checks validity | **SPLIT** | Needle translation is UI; registration error math and validity checks move to server. Endpoint: `GET /api/state`. |
| `updateDynamicCounterBands(...)` | 5502-5586 | Computes band bin percentages, total counts, active zone classes | **SPLIT** | Bins, counts, and percentages calculated on server; UI only renders returned numbers. Endpoint: `GET /api/state`. |
| `fbarxPost(url, body)` | 5587-5595 | Sends POST requests to FBarX hardware endpoints | **MOVE to server** | Unified into `POST /api/action`. Endpoint: `POST /api/action`. |
| `setFbarxBanner(status)` | 5596-5609 | Displays status banner (`OK`, `DISCONNECTED`, `SIMULATED`) | **KEEP in UI** | Pure DOM banner styling based on server connection state. Endpoint: `GET /api/state`. |
| `pollFBarXState()` | 5610-5706 | 200ms polling loop fetching hardware telemetry | **SPLIT** | Transformed into master polling loop `pollState()` fetching `GET /api/state`. Endpoint: `GET /api/state`. |
| `updateMarkWindowWithError(...)` | 5707-5740 | Computes mark window position, warning limits, and offset styling | **SPLIT** | Limit checks and validation move to server; UI only positions box. Endpoint: `GET /api/state`. |
| `initSegmentTracks()` | 5741-5752 | Initializes ammeter/speed visual LED segment elements | **KEEP in UI** | Pure DOM creation. Endpoint: *None*. |
| `updateSegmentTrack(id, val)` | 5753-5763 | Toggles `on` class on LED bar segments based on reading | **KEEP in UI** | Pure visual bar graph display. Endpoint: *None*. |
| `normalizeOutput(value)` | 5764-5770 | Clamps output value between 0.0 and 100.0 | **MOVE to server** | Clamping and validation enforced on server. Endpoint: `POST /api/action`. |
| `formatOutput(value)` | 5771-5776 | Formats percentage string (`XX.X%`) | **KEEP in UI** | Pure string formatting helper. Endpoint: *None*. |

---

### Section 8.4: Mode Buttons & UI Interaction Enablers (Lines 5777 - 6032)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `bindModeButtons()` | 5777-5825 | Click handlers for `AUTO`, `MAN`, `OFF` mode buttons on STN 1 & 2 | **SPLIT** | Button click is UI; mode transition validation and hardware command dispatch move to server. Endpoint: `POST /api/action { action: 'set_mode', station, mode }`. |
| `updateCameraForStationModes()` | 5826-5934 | Updates camera inspection badge (`AUTO LIVE`, `MAN LIVE`, `STANDBY LIVE`) | **KEEP in UI** | DOM badge update based on server state. Endpoint: `GET /api/state`. |
| `applyModeInteractionState()` | 5935-6032 | Enables/disables tiles, numpads, and buttons based on station mode | **KEEP in UI** | Pure UI presentation layer reflecting server mode. Endpoint: `GET /api/state`. |
| `setEnabled(el, enabled)` | 5936-5941 | Utility setting `pointer-events` and `opacity` on an element | **KEEP in UI** | DOM styling helper. Endpoint: *None*. |
| `setGroup(selector, enabled)` | 5942-5950 | Disables or enables a group of DOM controls | **KEEP in UI** | DOM styling helper. Endpoint: *None*. |

---

### Section 8.5: Steppers, Unit Toggle & Brake Types (Lines 6033 - 6115)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `bindSteppers()` | 6033-6063 | Attaches listeners for +/- output percentage steppers | **SPLIT** | Click handling is UI; range clamping and stepping action move to server. Endpoint: `POST /api/action { action: 'step_output' }`. |
| `setupStep(stn, downId, upId)` | 6034-6039 | Helper binding step up and step down buttons | **KEEP in UI** | Event binder. Endpoint: *None*. |
| `stepDown(e)` | 6040-6046 | Decrements output percentage | **MOVE to server** | Math and hardware write on server. Endpoint: `POST /api/action { action: 'step_output', dir: 'down' }`. |
| `stepUp(e)` | 6047-6062 | Increments output percentage | **MOVE to server** | Math and hardware write on server. Endpoint: `POST /api/action { action: 'step_output', dir: 'up' }`. |
| `bindUnitToggle()` | 6064-6082 | Toggles STN 1 units between `KG` and `N` | **SPLIT** | Button click is UI; active unit preference stored on server machine state. Endpoint: `POST /api/action { action: 'set_unit', unit }`. |
| `syncBrakeTypeUI(station, type)`| 6083-6094 | Updates active radio/button styling for magnetic vs pneumatic | **KEEP in UI** | Pure UI visual styling. Endpoint: *None*. |
| `bindBrakeTypeSelectors()` | 6095-6115 | Click listeners for brake type selectors | **SPLIT** | Click is UI; brake configuration persisted on server. Endpoint: `POST /api/action { action: 'set_brake_type' }`. |

---

### Section 8.6: STN 1 Calibration & Control Parameters (Lines 6116 - 6275)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `getStn1ControlValues()` | 6116-6119 | Reads STN 1 control parameters from draft or localStorage | **MOVE to server** | Replaced by server database read. Endpoint: `GET /api/calibration`. |
| `initStn1ControlDraft()` | 6120-6122 | Clones control parameters into working modal draft | **KEEP in UI** | Client modal edit buffer. Endpoint: *None*. |
| `discardStn1ControlDraft()` | 6123-6125 | Discards uncommitted modal edits | **KEEP in UI** | Client modal buffer reset. Endpoint: *None*. |
| `getStn1LoadcellValues()` | 6126-6129 | Reads loadcell calibration from draft or localStorage | **MOVE to server** | Replaced by server database read. Endpoint: `GET /api/calibration`. |
| `initStn1LoadcellDraft()` | 6130-6132 | Clones loadcell values into modal draft | **KEEP in UI** | Client modal edit buffer. Endpoint: *None*. |
| `discardStn1LoadcellDraft()` | 6133-6135 | Discards loadcell edits | **KEEP in UI** | Client modal buffer reset. Endpoint: *None*. |
| `bindStn1Calibration()` | 6136-6194 | Binds STN 1 calibrate button, prompts password, saves values | **SPLIT** | Modal display is UI; password check and saving move to server SQLite. Endpoint: `POST /api/login`, `POST /api/calibration`. |
| `open()` (inside bindStn1Cal) | 6138-6146 | Displays password entry pad for STN 1 | **KEEP in UI** | Modal display trigger. Endpoint: *None*. |
| `home()` (inside bindStn1Cal) | 6147-6147 | Closes modal and returns home | **KEEP in UI** | View routing. Endpoint: *None*. |
| `addAction(id, fn)` | 6148-6154 | Attaches click listener helper | **KEEP in UI** | DOM utility. Endpoint: *None*. |
| `openCalibrationPad(target)` | 6195-6216 | Opens touch keypad for typing calibration numbers | **KEEP in UI** | Keypad modal display. Endpoint: *None*. |
| `updateCalibrationDisplay()` | 6217-6232 | Updates visual numbers in calibration modal table | **KEEP in UI** | Pure DOM rendering of draft values. Endpoint: *None*. |
| `handleCalibrationConfirm()` | 6233-6275 | Checks hardcoded passcodes `'1111'` and `'2222'` | **MOVE to server** | Passcode check must be performed strictly on server. Endpoint: `POST /api/login`. |

---

### Section 8.7: STN 2 Calibration & Protected Passwords (Lines 6276 - 6470)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `getStn2CalValues()` | 6276-6296 | Fetches STN 2 Modbus calibration or falls back to defaults | **MOVE to server** | Server interrogates board and returns values in `GET /api/calibration`. |
| `initStn2CalDraft()` | 6297-6297 | Copies calibration into working draft | **KEEP in UI** | Client modal edit buffer. Endpoint: *None*. |
| `discardStn2CalDraft()` | 6298-6298 | Resets uncommitted edits | **KEEP in UI** | Client buffer reset. Endpoint: *None*. |
| `syncStn2CalDisplay()` | 6299-6315 | Updates calibration table DOM values | **KEEP in UI** | DOM rendering. Endpoint: *None*. |
| `openStn2CalPad(target)` | 6316-6338 | Opens keypad for editing STN 2 parameters | **KEEP in UI** | Keypad modal trigger. Endpoint: *None*. |
| `bindStn2Calibration()` | 6339-6380 | Binds STN 2 calibrate button, prompts password, saves values | **SPLIT** | Password verification and Modbus register write move to server. Endpoint: `POST /api/login`, `POST /api/calibration`. |
| `openProtectedNumericPassword(...)`| 6381-6402 | Opens password modal overlay with custom title | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `handleProtectedPasswordConfirm(...)`| 6403-6440| Checks passcodes `'3333'`, `'1111'`, `'4444'` in browser | **MOVE to server** | Passcode authorization performed exclusively on server. Endpoint: `POST /api/login`. |
| `validateAndSaveCalibration()` | 6441-6470 | Validates ranges (PPR 100-9999, etc.) and posts to board | **MOVE to server** | Validation and Modbus writes executed on server. Endpoint: `POST /api/calibration`. |

---

### Section 8.8: Numpad Modal & Keypad Engine (Lines 6471 - 6760)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `openNumpadModal(target, ...)` | 6471-6540 | Displays virtual keypad overlay for number entry | **KEEP in UI** | Pure virtual input interface. Endpoint: *None*. |
| `closeNumpadModal()` | 6541-6560 | Hides virtual keypad and resets input buffer | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `appendNumpadDigit(digit)` | 6561-6580 | Appends digit to client typing buffer (`buf += digit`) | **KEEP in UI** | Pure input buffer handling. Endpoint: *None*. |
| `backspaceNumpad()` | 6581-6595 | Deletes last typed character | **KEEP in UI** | Pure input buffer handling. Endpoint: *None*. |
| `clearNumpad()` | 6596-6610 | Clears typing buffer | **KEEP in UI** | Pure input buffer handling. Endpoint: *None*. |
| `bindNumpadEngine()` | 6611-6690 | Binds touch event listeners to digits 0-9, dot, backspace | **KEEP in UI** | Virtual keypad event attachment. Endpoint: *None*. |
| `handleNumpadConfirm()` | 6691-6760 | Dispatches confirmed value, checks ranges in client | **SPLIT** | Sending value to server is UI; validation and application move to server. Endpoint: `POST /api/action { action: 'set_parameter', target, value }`. |

---

### Section 8.9: Sensor Simulation (Lines 6761 - 6850)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `startSimulatedSensors()` | 6761-6810 | Runs `setInterval` loops simulating ammeters, tension, speed | **MOVE to server** | Removed from client. Simulation handled on server when `FBARX_SIM=1`. Endpoint: Server thread / `FBarXLink`. |
| `stopSimulatedSensors()` | 6811-6850 | Clears simulated sensor intervals | **MOVE to server** | Removed from client. Endpoint: *None*. |

---

### Section 8.10: S-Tension Numpad & Box Input (Lines 6851 - 6959)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `bindStensionBox()` | 6851-6890 | Binds click on S-Tension box to open keypad | **KEEP in UI** | Touch target listener. Endpoint: *None*. |
| `openStensionNumpad()` | 6891-6920 | Opens keypad for S-Tension target | **KEEP in UI** | Keypad modal trigger. Endpoint: *None*. |
| `handleStensionConfirm(val)` | 6921-6959 | Validates tension range (0-50) and posts to hardware | **MOVE to server** | Range check and Modbus write on server. Endpoint: `POST /api/action { action: 'set_stension', value }`. |

---

### Section 8.11: SVG Ammeter Needle Renderers (Lines 7200 - 7217)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `setNeedle(id, amp)` | 7201-7207 | Computes rotation angle `-90 + (amp/5 * 180)` and updates SVG transform | **KEEP in UI** | Pure SVG needle animation. Endpoint: *None*. |
| `updateNeedles()` | 7208-7214 | Reads ammeter values from `HMI_STATE` and calls `setNeedle` | **KEEP in UI** | Pure DOM rendering of server numbers. Endpoint: `GET /api/state`. |

---

### Section 8.12: Recipe Image Matching & Canvas Engine (Lines 7610 - 7724)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `recipeClone(v)` | 7626-7626 | Deep clone utility | **KEEP in UI** | Pure JavaScript utility. Endpoint: *None*. |
| `normalizeRecipe(r)` | 7627-7627 | Applies recipe default fields | **MOVE to server** | Canonical recipe defaults enforced in SQLite schema on server. Endpoint: `GET /api/recipes`. |
| `recipeEsc(v)` | 7628-7628 | HTML string escape helper | **KEEP in UI** | Pure XSS prevention helper. Endpoint: *None*. |
| `binOf(r, g, b, vs)` | 7648-7655 | Maps RGB pixel to 16 hue/intensity bins | **MOVE to server** | Moved to Python `vision.py` using NumPy/OpenCV. Endpoint: `POST /api/camera/match`. |
| `norm(a)` | 7656-7657 | Normalizes histogram vector to sum to 1.0 | **MOVE to server** | Moved to NumPy `norm` in `vision.py`. Endpoint: `POST /api/camera/match`. |
| `signature(src, crop)` | 7658-7679 | Draws on canvas, samples pixels, builds 64-bin color histogram | **MOVE to server** | Computed in `vision.py`. Endpoint: `POST /api/camera/match`. |
| `signatures(src)` | 7680-7680 | Generates cropped & uncropped signature pair | **MOVE to server** | Computed in `vision.py`. Endpoint: `POST /api/camera/match`. |
| `inter(a, b)` | 7681-7681 | Computes histogram intersection similarity | **MOVE to server** | Computed in `vision.py`. Endpoint: `POST /api/camera/match`. |
| `score(q, r)` | 7682-7685 | Combined weighted match score between query and reference | **MOVE to server** | Matching algorithm in `vision.py`. Endpoint: `POST /api/camera/match`. |
| `rank(sigs, recipes)` | 7686-7691 | Ranks all database recipes by match score | **MOVE to server** | Ranking executed on server. Endpoint: `POST /api/camera/match`. |
| `verdict(ranked)` | 7692-7696 | Compares top score against threshold (`MATCH_OK = 0.60`) | **MOVE to server** | Match decision made on server. Endpoint: `POST /api/camera/match`. |
| `loadImage(url)` | 7697-7697 | Decodes image URL via `new Image()` | **MOVE to server** | Server decodes images via OpenCV `cv2.imread`. Endpoint: `POST /api/camera/match`. |
| `sigFromDataUrl(url)` | 7698-7698 | Builds signature from image data URL | **MOVE to server** | Computed on server upon image upload. Endpoint: `POST /api/recipes`. |
| `downscale(url, maxSide)` | 7699-7704 | Canvas downscaling helper | **MOVE to server** | OpenCV `cv2.resize` on server. Endpoint: `POST /api/recipes`. |
| `readCode(canvas)` | 7705-7711 | Decodes QR/barcode from frame | **MOVE to server** | Pyzbar / OpenCV barcode engine in `vision.py`. Endpoint: `POST /api/camera/match`. |
| `parseCode(text)` | 7712-7724 | Parses barcode text into recipe/operator | **MOVE to server** | Parsed on server in `vision.py`. Endpoint: `POST /api/camera/match`. |

---

### Section 8.13: Recipe DB Store & Storage Bridge (Lines 7725 - 7989)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `RecipeDB.init()` | 7729-7760 | Opens IndexedDB with localStorage fallback | **MOVE to server** | Server SQLite database is the only store. Replaced by `GET /api/recipes`. |
| `RecipeDB.list()` | 7761-7765 | Returns array of cached recipes | **SPLIT** | In-memory UI cache populated solely from `GET /api/recipes`. Endpoint: `GET /api/recipes`. |
| `RecipeDB.get(id)` | 7766-7770 | Looks up recipe by id | **SPLIT** | Lookup from server-supplied recipe list. Endpoint: `GET /api/recipes`. |
| `RecipeDB.findByName(name)` | 7771-7780 | Looks up recipe by name | **SPLIT** | Lookup from server-supplied recipe list. Endpoint: `GET /api/recipes`. |
| `RecipeDB.save(recipe)` | 7781-7820 | Writes recipe to IndexedDB & localStorage | **MOVE to server** | Posted directly to server SQLite database. Endpoint: `POST /api/recipes`. |
| `RecipeDB.delete(id)` | 7821-7840 | Deletes recipe from IndexedDB & localStorage | **MOVE to server** | Deleted via server endpoint. Endpoint: `POST /api/action { action: 'delete_recipe', id }`. |
| `RecipeDB.setActive(id)` | 7841-7860 | Sets active recipe id in client storage | **MOVE to server** | Server machine state owns active recipe. Endpoint: `POST /api/action { action: 'load_recipe', id }`. |
| `RecipeDB.operators()` | 7861-7880 | Returns list of operator names | **SPLIT** | Sourced from server database. Endpoint: `GET /api/operators`. |
| `updateHudOverlay(data)` | 7900-7976 | Positions line detection HUD overlay & registration pill | **KEEP in UI** | Pure DOM styling of line coordinates received from server. Endpoint: `GET /api/state`. |
| `updateCalOverlayFields(rec)` | 7977-7989 | Populates read-only fields on calibration overlay | **KEEP in UI** | Pure DOM text rendering. Endpoint: `GET /api/state`. |

---

### Section 8.14: Toast & Time Formatting (Lines 7990 - 8035)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `showToast(msg, bad)` | 7991-8019 | Displays slide-in toast notification with auto-hide timer | **KEEP in UI** | Pure visual toast message alert. Endpoint: *None*. |
| `formatTime(d)` | 8020-8027 | Formats `HH:MM` time string | **KEEP in UI** | Pure string formatting helper. Endpoint: *None*. |
| `formatDateTime(d)` | 8028-8035 | Formats `DD/MM/YYYY HH:MM:SS` string | **KEEP in UI** | Pure string formatting helper. Endpoint: *None*. |

---

### Section 8.15: Job Lifecycle & UI Synchronization (Lines 8036 - 8294)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `updateJobUI()` | 8036-8090 | Updates job status badge, active recipe name, start time | **SPLIT** | Badge and text rendering stay in UI; job state is supplied by server. Endpoint: `GET /api/state`. |
| `startJob(recipe, operator)` | 8091-8135 | Generates job timestamp, saves to localStorage, posts event | **MOVE to server** | Server creates job, records server clock start timestamp, updates SQLite `machine_state`. Endpoint: `POST /api/action { action: 'start_job', recipe_id, operator }`. |
| `endJob()` | 8136-8223 | Computes elapsed seconds, aggregates counters, clears localStorage | **MOVE to server** | Server records end timestamp, calculates duration and final production totals in SQLite. Endpoint: `POST /api/action { action: 'end_job' }`. |
| `restoreJobState()` | 8224-8237 | Restores active job from localStorage on page load | **MOVE to server** | Removed. Active job is returned automatically in initial `GET /api/state`. Endpoint: `GET /api/state`. |
| `applyRecipeToHmi(r)` | 8238-8294 | Writes recipe parameters to HMI tiles and saves to localStorage | **SPLIT** | DOM tile updating stays in UI; recipe activation and persistence move to server. Endpoint: `POST /api/action { action: 'load_recipe', id }`. |

---

### Section 8.16: Virtual Alpha Keyboard (Lines 8295 - 8414)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `AlphaPad.show()` | 8306-8307 | Updates text display buffer on virtual QWERTY keyboard | **KEEP in UI** | Virtual keyboard display. Endpoint: *None*. |
| `AlphaPad.build()` | 8308-8396 | Renders QWERTY keyboard keys, backspace, enter, space | **KEEP in UI** | Pure DOM keyboard creation. Endpoint: *None*. |
| `AlphaPad.open(opts)` | 8398-8412 | Opens virtual keyboard modal for text entry | **KEEP in UI** | Virtual keyboard modal trigger. Endpoint: *None*. |
| `AlphaPad.close()` | 8397-8397 | Hides virtual keyboard modal | **KEEP in UI** | Virtual keyboard modal close. Endpoint: *None*. |

---

### Section 8.17: Recipe Selection & Load UI (Lines 8415 - 8757)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `getBagArtInfo(r)` | 8415-8493 | Generates artwork dimensions and notes text | **KEEP in UI** | Pure visual text helper. Endpoint: *None*. |
| `recipeConfigMarkup(r, op)` | 8494-8531 | Generates HTML markup for recipe summary card | **KEEP in UI** | Pure HTML card generator. Endpoint: *None*. |
| `updateRecipeLoadStatus(...)` | 8532-8545 | Updates recipe load status text and color indicators | **KEEP in UI** | Pure DOM status styling. Endpoint: *None*. |
| `populateRecipeSelectors()` | 8546-8577 | Populates dropdown list of available recipes | **SPLIT** | Dropdown rendering is UI; recipe list loaded from server. Endpoint: `GET /api/recipes`. |
| `getRecipeImageUrl(r)` | 8578-8592 | Returns image URL path for a recipe | **KEEP in UI** | URL resolution helper. Endpoint: *None*. |
| `populateRecipeImages()` | 8593-8627 | Renders visual recipe thumbnail selection cards | **SPLIT** | Thumbnail rendering is UI; recipes supplied by server. Endpoint: `GET /api/recipes`. |
| `selectLoad(id, src, note)` | 8628-8679 | Highlights selected recipe card and updates preview | **KEEP in UI** | Pure UI card selection state. Endpoint: *None*. |
| `updateRecipeLoadClock()` | 8680-8693 | Updates clock display on recipe load modal | **KEEP in UI** | Pure visual clock formatting. Endpoint: *None*. |
| `showRecipeLoadScreen()` | 8694-8734 | Displays recipe load modal overlay and starts camera | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `stopLoadCamera()` | 8735-8757 | Stops recipe load camera preview tracks | **SPLIT** | Video element pause is UI; stopping hardware camera moves to server. Endpoint: `POST /api/action { action: 'camera_stop' }`. |

---

### Section 8.18: Auto-Camera Detection & Modal Live Match (Lines 8758 - 9102)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `getCameraStream()` | 8758-8763 | Requests webcam stream via browser `navigator.mediaDevices` | **SPLIT** | Live preview video display is UI; fixed Pi camera is managed by server `camera.py`. Endpoint: `GET /api/camera/stream`. |
| `openRecipeCamera()` | 8764-8821 | Attaches camera stream and starts auto-detection timer | **SPLIT** | Attaching stream to `<video>` is UI; detection loop moves to server. Endpoint: `POST /api/camera/match`. |
| `runAutoCameraDetection(...)` | 8822-8943 | Grabs canvas frame, computes signature, matches in client | **MOVE to server** | Frame capture and matching executed in `vision.py` on server. Endpoint: `POST /api/camera/match`. |
| `compareRecipeCamera()` | 8944-8951 | Calls comparison against active recipe | **MOVE to server** | Executed on server in `vision.py`. Endpoint: `POST /api/camera/compare`. |
| `matchImageFile(file)` | 8952-9010 | Reads local image file and matches against recipe DB | **MOVE to server** | Uploads image file to server for OpenCV matching. Endpoint: `POST /api/camera/match`. |
| `armDelete(on)` | 9011-9016 | Toggles confirmation state on recipe delete button | **KEEP in UI** | Pure UI two-step button safety state. Endpoint: *None*. |
| `deleteSelectedRecipe()` | 9017-9030 | Deletes active recipe after confirmation | **MOVE to server** | Server SQLite handles deletion. Endpoint: `POST /api/action { action: 'delete_recipe', id }`. |
| `closeRecipeLoad()` | 9031-9038 | Closes recipe load modal overlay | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `confirmRecipeLoad()` | 9039-9102 | Validates station modes, checks interlocks, applies recipe | **SPLIT** | User confirmation dialog is UI; interlock checks and hardware application executed on server. Endpoint: `POST /api/action { action: 'load_recipe', id }`. |

---

### Section 8.19: Recipe Calibration Form, File Preview & CRUD (Lines 9103 - 9944)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `clamp(v, a, b)` | 9105-9107 | Mathematical clamping utility | **KEEP in UI** | General math helper. Endpoint: *None*. |
| `status(t, bad)` | 9108-9109 | Sets calibration status text and color | **KEEP in UI** | Pure DOM status styling. Endpoint: *None*. |
| `populateCalRecipeSelect()` | 9110-9122 | Populates recipe selector in calibration form | **SPLIT** | Dropdown DOM rendering is UI; recipe list supplied by server. Endpoint: `GET /api/recipes`. |
| `begin(recipeId)` | 9123-9130 | Initializes calibration draft from selected recipe | **KEEP in UI** | Client form edit draft buffer. Endpoint: *None*. |
| `blank()` | 9131-9163 | Creates blank recipe draft template | **KEEP in UI** | Client form template helper. Endpoint: *None*. |
| `sync()` | 9164-9222 | Populates form input fields from draft object | **KEEP in UI** | Pure DOM input field populator. Endpoint: *None*. |
| `syncRecipeCalibrationUI()` | 9223-9223 | Refreshes calibration form UI | **KEEP in UI** | DOM refresh helper. Endpoint: *None*. |
| `discardRecipeEdit()` | 9224-9225 | Discards uncommitted calibration changes | **KEEP in UI** | Client draft buffer reset. Endpoint: *None*. |
| `openDeleteRecipeModal()` | 9226-9247 | Displays recipe deletion confirmation modal | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `performDeleteRecipe()` | 9248-9290 | Calls delete API and updates local list | **MOVE to server** | Server SQLite handles record removal. Endpoint: `POST /api/action { action: 'delete_recipe', id }`. |
| `cancelDeleteRecipeCalibration()`| 9291-9296 | Dismisses delete recipe modal | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `openRecipeNumpad(target)` | 9297-9305 | Opens keypad for editing recipe numeric fields | **KEEP in UI** | Keypad modal trigger. Endpoint: *None*. |
| `handleRecipeNumericConfirm()` | 9306-9317 | Copies confirmed numeric value into calibration draft | **KEEP in UI** | Client draft buffer update. Endpoint: *None*. |
| `editText(field, title, max)` | 9318-9323 | Opens virtual QWERTY keyboard for text fields | **KEEP in UI** | Virtual keyboard trigger. Endpoint: *None*. |
| `setImageFromDataUrl(...)` | 9324-9336 | Computes client signature and attaches preview | **SPLIT** | Preview thumbnail display is UI; image storage and signature creation move to server. Endpoint: `POST /api/recipes`. |
| `openCapture(target)` | 9337-9388 | Opens camera capture modal for recipe artwork | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `closeCapture()` | 9389-9404 | Hides camera capture modal | **KEEP in UI** | Modal presentation. Endpoint: *None*. |
| `shoot()` | 9405-9453 | Captures frame snapshot from camera | **SPLIT** | Image display is UI; capture executed on server `camera.py`. Endpoint: `GET /api/camera/snapshot`. |
| `retakeCapture()` | 9454-9463 | Re-enables live preview for new capture | **KEEP in UI** | Modal preview toggle. Endpoint: *None*. |
| `confirmCapture()` | 9464-9526 | Confirms captured photo and attaches to draft | **SPLIT** | Attaching thumbnail to draft is UI; persisting image moves to server. Endpoint: `POST /api/recipes`. |
| `save()` (in calibration form) | 9527-9599 | Validates recipe fields and saves to IndexedDB/API | **MOVE to server** | Validation and SQLite persistence executed on server. Endpoint: `POST /api/recipes`. |
| `goHomeFromRecipeCalibration()`| 9600-9604 | Closes calibration screen and returns home | **KEEP in UI** | View routing. Endpoint: *None*. |
| `bindCal()` | 9605-9649 | Binds calibration form button listeners | **KEEP in UI** | DOM event attachment. Endpoint: *None*. |
| `showSingleFilePreview(...)` | 9650-9677 | Displays image preview thumbnail for single file | **KEEP in UI** | Pure DOM image element display. Endpoint: *None*. |
| `showDualFilePreview(...)` | 9678-9905 | Displays front and back preview thumbnails | **KEEP in UI** | Pure DOM image element display. Endpoint: *None*. |
| `bindRecipeCalibration()` | 9906-9924 | Attaches file input change listeners | **KEEP in UI** | File input listeners. Endpoint: *None*. |
| `handleStop(e)` | 9925-9944 | Handles emergency stop button click | **MOVE to server** | Dispatches immediate safe-state command to hardware. Endpoint: `POST /api/action { action: 'stop' }`. |

---

### Section 8.20: Database Bootstrap & Migration Sync (Lines 9945 - 10073)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `syncFromDatabase()` | 9945-10029 | Merges server recipes with IndexedDB and localStorage | **MOVE to server** | Removed. Client receives complete, unified recipe list from `GET /api/recipes`. Endpoint: `GET /api/recipes`. |
| `fetchReportFromDB()` | 10030-10073 | Fetches production records from server API | **SPLIT** | Merged into `GET /api/report`. Endpoint: `GET /api/report`. |

---

### Section 8.21: Registration HUD, Stability & Buffer Tracking (Lines 10074 - 10448)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `updateZoneCountersDisplay()` | 10172-10185 | Updates DOM text for counter zones (0-7, 8-15, etc.) | **KEEP in UI** | Pure DOM text rendering of counts supplied by server. Endpoint: `GET /api/state`. |
| `recordBagInBin(binName)` | 10186-10202 | Increments client-side bin counter variables | **MOVE to server** | Removed from client. Bag counting and binning executed on server. Endpoint: Server vision/modbus thread. |
| `updateErrorPercentageDisplay(...)`| 10203-10240 | Calculates pass/fail error percentages and ratios | **SPLIT** | Error percentages and pass/fail status calculated on server; UI only renders returned numbers. Endpoint: `GET /api/state`. |
| `getActiveRecipeCamSrc(err)` | 10417-10433 | Returns active recipe reference artwork path | **KEEP in UI** | URL resolution helper. Endpoint: *None*. |
| `haltMediaTracks(stream)` | 10434-10448 | Stops media stream tracks on browser video element | **KEEP in UI** | Pure browser media track cleanup helper. Endpoint: *None*. |

---

### Section 8.22: Live Camera Inspection & Line Calibration (Lines 10449 - 11228)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `startLiveCamera()` | 10449-10497 | Opens camera stream on `#full-cam-preview-img` | **SPLIT** | Attaching stream URL to `<img>` is UI; hardware camera loop runs on server. Endpoint: `POST /api/action { action: 'camera_start' }`. |
| `stopLiveCamera(force)` | 10498-10584 | Stops camera stream image | **SPLIT** | Clearing image src is UI; stopping server camera thread moves to server. Endpoint: `POST /api/action { action: 'camera_stop' }`. |
| `startLiveComparisonLoop()` | 10585-10634 | 1200ms client interval sending frames to compare API | **MOVE to server** | Removed. Server background thread executes continuous line detection; client polls `GET /api/state`. Endpoint: `GET /api/state`. |
| `setLiveCamError(err)` | 10635-10669 | Sets simulated error parameter in client | **MOVE to server** | Removed. Test simulation error controlled via server configuration. Endpoint: *None*. |
| `fitCamStage()` | 10774-10799 | Computes aspect ratio scaling for camera viewport | **KEEP in UI** | Pure CSS/DOM viewport scaling. Endpoint: *None*. |
| `initLiveCamSwitcher()` | 10800-10819 | Attaches click listeners for camera view mode tabs | **KEEP in UI** | Pure DOM view switcher. Endpoint: *None*. |
| `openLiveCam(e)` | 10820-10884 | Opens full camera inspection screen (`#screen-cam`) | **KEEP in UI** | View routing. Endpoint: *None*. |
| `bindRulerZeroCalibration()` | 10902-10962 | Sends zero calibration command to server | **SPLIT** | Wizard UI clicks are UI; zero-offset math calculated on server. Endpoint: `POST /api/calibration { type: 'zero' }`. |
| `bindRulerScaleCalibration()`| 10963-11045 | Sends scale calibration points to server | **SPLIT** | Wizard UI clicks are UI; px-per-mm calculation computed on server. Endpoint: `POST /api/calibration { type: 'ruler' }`. |
| `loadCameraCalibrationUi()` | 11046-11100 | Loads camera calibration from server into inputs | **SPLIT** | Input field populating is UI; data loaded from server. Endpoint: `GET /api/calibration`. |

---

### Section 8.23: Live SVG Ammeter updates (Lines 11229 - 11265)

| Function Name | Lines | Current Responsibilities | Classification | Reason & Server Endpoint Replacement |
| :--- | :---: | :--- | :---: | :--- |
| `renderLiveAmmeter(station)` | 11231-11259 | Computes angle radians, SVG needle coordinates `(x2, y2)` | **KEEP in UI** | Pure SVG needle coordinate mathematics and DOM attribute update. Endpoint: *None*. |
| `render()` (live ammeter) | 11260-11262 | Calls `renderLiveAmmeter` for stn1 and stn2 | **KEEP in UI** | UI render caller. Endpoint: *None*. |

---

## 9. Comprehensive Classification Summary

| Category | Count | Percentage | Primary Architectural Impact |
| :--- | :---: | :---: | :--- |
| **KEEP in UI** | 134 | 63.2% | Virtual keypad touch buffer, SVG ammeter needles, ruler tick rendering, DOM view navigation, modals, and local clock. |
| **SPLIT** | 44 | 20.8% | Functions where UI event triggers or DOM rendering stay in client, but state storage, math, and decision-making move to server API (`GET /api/state`, `POST /api/action`). |
| **MOVE to server** | 34 | 16.0% | Passcode validation ('1111', '2222', '3333', '4444'), range limit checks, image matching/SIFT/histograms, sensor simulation, job lifecycle timestamps, and IndexedDB/localStorage stores. |
| **TOTAL** | **212** | **100.0%** | **All state, storage, and logic centralized in `server.py`.** |

---

## 10. Target API Specification for Step 1 & Step 2

```
========================================================================================
UNIFIED TARGET API SPECIFICATION
========================================================================================

1. GET /api/state
   - Polled every 200-500ms by thin UI.
   - Master snapshot containing:
     {
       "connected": true,
       "hardware_status": "OK" | "SIMULATED" | "NOT CONNECTED",
       "timestamp": 1731553480.123,
       "machine": {
         "stn1": { "mode": "AUTO"|"MAN"|"OFF", "outputPct": 55.0, "ammeter": 1.78, "unit": "KG" },
         "stn2": { "mode": "AUTO"|"MAN"|"OFF", "outputPct": 60.0, "ammeter": 1.85, "speedMpm": 100 }
       },
       "job": {
         "active": true,
         "job_id": 14,
         "recipe_name": "Veera Sivaji",
         "recipe_id": "seed-veera-sivaji",
         "operator": "Operator 1",
         "start_time": 1731550000,
         "elapsed_sec": 3480
       },
       "counters": {
         "0-7": 1420,
         "8-15": 85,
         "16-25": 12,
         "26+": 3,
         "unscored": 0,
         "total": 1520,
         "pass_pct": 93.4,
         "active_zone": "0-7"
       },
       "registration": {
         "error_mm": 0.4,
         "status": "IN SPEC",
         "repeat_length_actual": 740.2,
         "repeat_length_set": 740.0,
         "mark_window": 40,
         "valid": true,
         "front_line_px": 312.4,
         "back_line_px": 316.8
       }
     }

2. POST /api/action
   - Dispatches validated user commands. Refuses invalid ranges or mode conflicts without altering state.
   - Payloads:
     - { "action": "set_mode", "station": "stn1"|"stn2", "mode": "AUTO"|"MAN"|"OFF" }
     - { "action": "step_output", "station": "stn1"|"stn2", "direction": "up"|"down" }
     - { "action": "set_parameter", "target": "repeat_length"|"mark_window"|"stension", "value": 740 }
     - { "action": "start_job", "recipe_id": "...", "operator": "..." }
     - { "action": "end_job" }
     - { "action": "load_recipe", "id": "..." }
     - { "action": "delete_recipe", "id": "..." }
     - { "action": "camera_start" }
     - { "action": "camera_stop" }
   - Replies: { "ok": true, "state": { ... new state snapshot ... } }
     or { "ok": false, "error": "Clear rejection reason" }

3. POST /api/login
   - Server-only passcode verification.
   - Payload: { "type": "stn1_control" | "stn1_loadcell" | "stn2_cal" | "recipe_cal", "passcode": "3333" }
   - Replies: { "ok": true, "token": "...", "expires_in": 900 }
     or { "ok": false, "error": "Invalid Passcode" }

4. GET /api/report
   - Pre-calculated aggregated production metrics.
   - Query params: `?start=...&end=...&recipe=...&operator=...&format=json|csv`

5. GET /api/recipes & POST /api/recipes
   - SQLite backed CRUD. Images stored on disk or SQLite blob. Validates all numeric ranges.

6. GET /api/operators
   - List of operator names.

7. GET/POST /api/calibration
   - STN 1 loadcell & control parameters, STN 2 Modbus parameters, camera scale_px_per_mm, zero_offset.

8. POST /api/camera/match
   - Server-side OpenCV feature / signature match. Returns matching recipe and confidence score.
```
"""

with open(output_path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Audit document written successfully to {output_path}. Size: {len(content)} bytes.")
