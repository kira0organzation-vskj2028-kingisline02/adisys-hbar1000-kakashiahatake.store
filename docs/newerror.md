# Print Registration Error (mm) – Calculation Technique

Specification for measuring the front/back print mis-registration of rice bags (example: "Veera Shivaji" 26 kg bag) with a Raspberry Pi camera, for the RiceVision HMI in `index.html`.

> **Section numbers are fixed.** `index.html` has code comments that refer to "error.md Section 9, 10, 13 and 15". Keep these numbers if you edit this file.

---

## 1. Goal and architecture

For every bag, measure how far the **BACK** panel print is shifted from the **FRONT** panel print, in **millimetres**, in real time.

```
Pi camera ──► BACKEND (Python/OpenCV, SQLite)  ──JSON──►  index.html (HMI)
              - grabs frames                                - shows error, needle, chips
              - measures dy / dx / confidence               - counts bags into bins
              - classifies bin / status                     - job start / stop, report
              - (optional) correction output                - posts events / production
```

- **The image processing is done in the backend**, not in the browser. `index.html` only sends a frame (or asks for the latest snapshot), receives JSON, and displays, counts and logs it (Section 13).
- The HMI also works without a Pi: error presets (`live`, `0mm`, `-10mm`, `+10mm`) select test images and the backend returns the matching error (Section 13.4).

## 2. Input image layout

One camera frame contains both panels:

```
+----------------------------------------------+
|  FRONT panel (left)      BACK panel (right)  |
|                                              |
|  [pink mark]             [pink mark]         |   <- registration mark, bottom-right corner of each panel
+----------------------------------------------+
```

- FRONT on the **left**, BACK on the **right**.
- Each panel has a **magenta/pink bar** (registration mark) at its bottom-right corner, about **72 x 9 px** in a 1600 px wide frame (aspect ratio about 8:1).
- Camera fixed and square to the bag, fixed exposure / gain / white balance, steady lighting.
- The HTML camera stage uses an aspect ratio of **860 x 630**; the HMI sends frames at most **860 px wide** (JPEG, quality 0.85).

## 3. Sign convention

```
error_mm  > 0  -> BACK panel is LOWER than FRONT   (back is "late")
error_mm  < 0  -> BACK panel is HIGHER than FRONT  (back is "early")
error_mm  = 0  -> aligned
```

The HTML uses the signed value for the ruler needle (positive moves the needle to the right) and for M1 / M2 (Section 14): **negative error is shown in M1, positive error in M2**.

## 4. Reference data (measured from the supplied test images)

Frame width 1600 px. `dy_px = back_y - front_y` (image y grows downward).

| Test image | Real shift | Mark method: front y / back y | dy_px (mark) | Artwork method dy_px |
|---|---|---|---|---|
| `_10mm_1.jpeg` (`+10mm`) | +10 mm | 970 / 990 | **+20** | +19.2 |
| `0mm_1.jpeg` (`0mm`) | 0 mm | 891 / 893 | **+2** | +1.9 |
| `-10mm_1.jpeg` (`-10mm`) | -10 mm | 970 / 952 | **-18** | -17.5 |
| `after_calibration.jpeg` | 0 mm | identical to the 0 mm image | +2 | +1.9 |

Derived constants (at 1600 px frame width):

- **Zero offset** `zero_px = +2 px` (dy of a correctly aligned bag; learned by the ZERO action, Section 8).
- **Scale** `px_per_mm = 1.9` (mark method: `(20 - (-18)) / 20`) or `1.835` (artwork method: `(19.2 - (-17.5)) / 20`).
- If the real printed width of the mark is known: `px_per_mm = mark_width_px / mark_width_mm`.
- Accuracy on these samples: about ±1 mm.

## 5. Core formula

```
dy_px      = y_back  - y_front
dx_px      = x_back  - x_front
offset_y_mm = (dy_px - zero_px)   / px_per_mm     # signed vertical registration error  (main value)
offset_x_mm = (dx_px - zero_x_px) / px_per_mm     # signed horizontal error (optional)
reg_err_mm  = abs(offset_y_mm)                     # magnitude used for the bins
```

Express pixel values at a **reference width of 1600 px**: `ref_px = measured_px * 1600 / frame_width`. Then the constants stay valid when the camera resolution changes.

## 6. Method A – registration-mark detection (preferred, fastest)

1. Capture a frame (Picamera2, e.g. 1280x720, fixed exposure / gain / AWB).
2. Cut two small ROIs: the bottom-right corner of the FRONT panel and of the BACK panel.
3. In each ROI:
   - convert to HSV and threshold magenta. Reference RGB of the mark: `R>200, G<90, 100<B<200`; OpenCV HSV starting range `H 140-175, S 80-255, V 120-255` (re-tune on the real camera);
   - clean with a 3x3 morphological open;
   - connected components; keep the blob with area > 150 px and width/height between 5 and 12;
   - take its **centroid** `(x, y)` (sub-pixel, about 0.1 px, about 0.05 mm).
4. Convert ROI coordinates to frame coordinates, then apply Section 5.
5. Return `ok=false` if either mark is missing or its area differs by more than about 25% from the expected area.

```python
import cv2, numpy as np

PX_PER_MM = 1.9          # at 1600 px width; calibrate on the real setup
ZERO_PX   = 2.0          # dy of an aligned bag; set by ZERO
LO, HI = (140, 80, 120), (175, 255, 255)

def mark_centroid(roi):
    m = cv2.inRange(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), LO, HI)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, st, cen = cv2.connectedComponentsWithStats(m)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a > 150 and 5 < w / max(h, 1) < 12:
            return cen[i]
    return None

def measure(frame):
    H, W = frame.shape[:2]
    k = 1600.0 / W
    f = mark_centroid(frame[FRONT_Y0:FRONT_Y1, FRONT_X0:FRONT_X1])
    b = mark_centroid(frame[BACK_Y0:BACK_Y1,  BACK_X0:BACK_X1])
    if f is None or b is None:
        return {"ok": False, "status": "NO MATCH", "confidence": 0.0}
    dy = ((b[1] + BACK_Y0) - (f[1] + FRONT_Y0)) * k
    dx = ((b[0] + BACK_X0) - (f[0] + FRONT_X0)) * k
    return {"ok": True,
            "offset_y_mm": (dy - ZERO_PX) / PX_PER_MM,
            "offset_x_mm": (dx - ZERO_X_PX) / PX_PER_MM,
            "confidence": 1.0}
```

`FRONT_*` / `BACK_*` are the ROI bounds, which depend on the camera framing.

## 7. Method B – artwork matching (fallback, no mark needed)

Use when the mark is missing, damaged or hidden. The HTML's "SIFT / ORB CONF." tile shows the confidence of this method.

**B1. Template matching (validated).**

1. Work on a grayscale frame, **800 px wide**.
2. Take a template from the FRONT centre artwork: x from 12.5% to 34.0% of the frame width, y from 25% to 67% of the frame height.
3. **Coarse search**: downscale by 4, normalised cross-correlation (NCC) over the right part of the frame (x from 40% of the width to the right edge, full height).
4. **Fine search**: +/-7 px around the coarse hit at 800 px width (template sampled with stride 2), in x and y.
5. **Sub-pixel**: parabola fit through the NCC scores at y-1, y, y+1 (same for x).
6. `dyRef = (match_y - template_y) * 1600 / 800`, same for x. NCC score = `confidence`.
7. Apply Section 5 with `px_per_mm = 1.835`, `zero_px = 1.9`.

Validated results (same algorithm, 800 px working width):

| Image | NCC score | dyRef (px) | error_mm |
|---|---|---|---|
| `+10mm` | 0.945 | 19.2 | +9.5 |
| `0mm` | 0.996 | 1.88 | 0.0 |
| `-10mm` | 0.967 | -17.5 | -10.6 |
| `after_calibration` | 0.996 | 1.88 | 0.0 |

**B2. Feature matching (SIFT / ORB).** Detect keypoints on the FRONT panel, match them on the BACK panel (ratio test 0.75, RANSAC), and take the **median vertical displacement of the inlier matches** as `dy_px`. `confidence = inliers / matches` (or the HTML rule `inliers >= 15 and confidence >= 0.60`). This also handles small scale and rotation differences.

## 8. Calibration

1. **Scale**: from the known printed width of the mark (mm), or by photographing a ruler. Store `px_per_mm`.
2. **ZERO**: present a correctly aligned bag, measure `dy_px`, store it as `zero_px`, set the correction to 0. After ZERO the same bag reads 0.0 mm (this is the "after_calibration" state).
3. Re-check the scale if the camera height, lens or zoom changes.
4. Store these values in the backend (SQLite), not in the browser.

## 9. Error bins (for counting)

Used by the backend (`bin` field) and by the HTML (fallback calculation when `bin` is missing). Uses the **unrounded** magnitude `reg_err_mm`:

```
reg_err_mm <=  7.0   -> bin "0-7"    PASS  (green)
reg_err_mm <= 15.0   -> bin "8-15"   FAIL  (amber)
reg_err_mm <= 25.0   -> bin "16-25"  FAIL  (red)
reg_err_mm  > 25.0   -> bin "over"   FAIL  (red, counted only in TOTAL)
```

Status text: `PASS (IN SPEC)` when `reg_err_mm <= 7.0`, otherwise `FAIL (OUT OF SPEC)`. Ruler / HUD colour: green `<= 7`, amber `<= 15`, red above.

## 10. Counting bags (60 bags per minute)

**Requirement: the system must check every bag at a rate of 60 bags per minute (1 bag per second).** After one minute of running, `total` must be 60 and every bag must have exactly one measurement.

**Count per trigger (required at this speed).**

1. A photo-sensor or encoder pulse marks each bag. One pulse = one bag = one frame = one measurement.
2. The backend gives each measurement a running number `bag_id` (1, 2, 3, ...) and returns it with the result (Section 13.1).
3. The HMI counts a result **once per new `bag_id`**: `recordBagInBin(bin)`. Results with `ok=false`, `status="NO MATCH"` or `confidence < 0.60` are not counted in a bin, but the missed bag is still logged (`missed` count) so that `bins + over + missed = bags passed`.
4. A bag with the same error as the previous bag is still a new bag.

**Why the old free-running rule cannot be used at 60 bags/min.** The HMI's stability rule (3 stable readings within 1.5 mm, a bag is "new" only if the value changes by more than 4.0 mm or 2 frames show no match) assumes a gap between bags. With bags every 1.0 s and polling every 350 ms, consecutive bags with similar errors would be counted **once**, and `total` would stay far below 60. Keep that rule only as a fallback when no trigger exists (static test images, browser camera).

Fallback rule (no trigger): keep the last 3 readings; stable when `max - min <= 1.5 mm`; new bag when nothing was counted yet or the median differs from the last counted value by more than 4.0 mm; after 2 consecutive no-match frames reset the buffer.

## 11. Reducing the error (closed loop)

`index.html` only **displays** the error; it has no correction loop. To reduce the error count, add one in the backend or PLC:

```
corr_mm   = 0                                  # persisted, signed
residual  = measured_error_mm                  # camera already includes the effect of the actuator

after each counted bag, if AUTO is on and abs(residual) > 1.0:        # dead-band +/-1 mm
    avg      = mean of the last 3-5 counted bags
    corr_mm  = clamp(corr_mm - gain * avg, -25, +25)                  # gain 0.5 - 0.8
    send corr_mm to the register motor / servo (limit each step)
```

Simulation with a constant +10 mm bag and gain 0.8: residuals +9.4, +1.9, +0.4 mm; bag 1 lands in bin 8-15, the next bags in 0-7.

**Dead time at 60 bags/min.** If the camera is `N` bags downstream of the register actuator, a correction only shows up in the measurements `N` bags later. Do not correct again until that many bags have passed, otherwise the loop over-corrects and oscillates. Example: `N = 3` bags and averaging over 3 bags means one correction about every 6 seconds (6 bags); use gain 0.5 - 0.8 and the +/-1 mm dead-band.

Expose it to the HMI as `corr_mm` in the `compare_front_back` response (Section 13) and show it next to the error if wanted. Only run the loop when STN2 is in **AUTO** mode.

## 12. Real-time behaviour and speed (60 bags per minute)

Required throughput: **60 bags per minute = 1 bag per second = 1000 ms per bag.** Target: result available to the HMI within **200 ms** of the trigger, so the answer arrives before the next bag.

| Step | Typical time on Raspberry Pi 5 (estimate) |
|---|---|
| Trigger to start of exposure | under 5 ms |
| Exposure (short, see below) | 0.3 - 2 ms |
| Sensor read-out and capture | 15 - 40 ms |
| Mark detection (2 small regions) | under 5 ms |
| JSON to the HMI | under 10 ms |
| **Total** | **about 30 - 80 ms (3 - 8% of the 1000 ms budget)** |

- Detection is not the limit; capture and trigger timing are. The mark method on two small regions leaves more than 90% of each second free.
- The HMI polling interval (350 ms, `startLiveComparisonLoop`) is only a display refresh. Counting must not depend on it (Section 10).
- **Motion blur.** If the bags are made at 60/min from a 740 mm repeat, the web moves about **0.74 m/s** (assumption: confirm the real speed). The blur in mm is `speed x exposure`: 1 ms gives 0.74 mm, 0.3 ms gives 0.22 mm. Use an exposure of **0.3 ms or less** with strong or strobed LED light, preferably a **global-shutter camera** (Pi Global Shutter). If the bag stops under the camera, a normal exposure is fine.
- Keep one request in flight at a time; drop stale frames instead of queueing them.
- **STN2 mode gating:** when STN2 is `OFF` the HMI stops the camera and forces the error to 0.0 mm; scanning is only enabled in `AUTO` and `MAN`.

## 13. Backend API contract (what `index.html` calls)

### 13.1 Front/back error – the main endpoint

```
GET  /api/camera/compare_front_back?error=<live|0mm|-10mm|+10mm>&recipe_id=<numericId>
POST /api/camera/compare_front_back?error=live&recipe_id=<numericId>
     Content-Type: image/jpeg      body = camera frame (<= 860 px wide)
```

- `POST` with a frame: measure that frame (live camera in the browser).
- `GET` without a body: measure the backend's own latest frame / snapshot, or return the simulated value for the preset in `error`.

Response (JSON). Fields the HTML reads:

```json
{
  "ok": true,
  "offset_y_mm": 9.4,
  "offset_x_mm": 0.3,
  "error_mm": 9.4,
  "reg_err_mm": 9.4,
  "bin": "8-15",
  "status": "OUT OF SPEC",
  "confidence": 0.97,
  "bag_id": 1042,
  "latency_ms": 64,
  "corr_mm": 0.0
}
```

| Field | Meaning | Used for |
|---|---|---|
| `ok` | measurement valid | if false: no update, no count |
| `offset_y_mm` (or `error_mm`) | signed vertical error | main readout, ruler needle, M1/M2, counting |
| `offset_x_mm` | signed horizontal error | "ΔX / ΔY" tile |
| `reg_err_mm` | magnitude; default `abs(offset_y_mm)` | bin / status |
| `bin` | `0-7`, `8-15`, `16-25`, `over` | counting and active chip |
| `status` | `IN SPEC` / `OUT OF SPEC` / `NO MATCH` | HUD text |
| `confidence` | 0-1 | "SIFT / ORB CONF." tile; must be `>= 0.60` |
| `bag_id` | running bag number, one per trigger (Section 10) | count each new `bag_id` once (to be added in the HMI) |
| `latency_ms` | trigger-to-result time | diagnostics; must stay under 200 ms |
| `corr_mm` | optional correction output (Section 11) | not read yet |

No-match response (HMI shows `NO MATCH`, does not count):

```json
{ "ok": false, "status": "NO MATCH", "confidence": 0.12 }
```

The HTML treats `ok === false`, `status === "NO MATCH"` or `confidence < 0.60` as no match.

### 13.2 Other camera endpoints used by the HMI

| Endpoint | Purpose |
|---|---|
| `GET /api/camera/stream?error=live` | MJPEG stream, fallback when the browser has no camera (`getUserMedia`) |
| `GET /api/camera/snapshot?error=<preset>` | one JPEG frame (scan button, Screen 2 snapshot) |
| `POST /api/camera/compare?source=<recipe_load\|recipe_load_file\|hmi_scan\|screen2_snap>&recipe_id=..&error=..` (body `image/jpeg`) | recipe identification by SIFT. Reads `result`, `inliers`, `confidence`, `best`, `best_recipe_id`, `time_ms`. For `hmi_scan` it may also return `front_back` (same fields as 13.1) or `error_mm` |
| `POST /api/camera/sim_error` `{ "error": "0mm" }` | tell the backend which simulated preset is active |
| `POST /api/camera/stop` | release the camera when STN2 goes OFF |

### 13.3 Data the HMI stores through the backend

| Endpoint | Content |
|---|---|
| `POST /api/event` | `JOB_STARTED` / `JOB_ENDED` with operator and recipe |
| `POST /api/production` | on job end: `recipe, operator, start_time, end_time, c0_7, c8_15, c16_25, total` |
| `GET /api/report`, `/api/state`, `/api/recipes`, `/api/operators` | reload of reports, state and recipes |

### 13.4 Simulation presets (test without a camera)

The error buttons set `window.activeCamError` to `live`, `0mm`, `-10mm` or `+10mm`. The HMI loads `/images/<prefix>_front_back_<suffix>.jpg` with prefix `veerashivaji`, `thangamayil`, `indiagate`, `kohinoor` or `royal_bullet` (from the active recipe name) and suffix `0mm`, `plus10mm` or `minus10mm`. The backend must return for those images: `0mm` → about 0.0, `+10mm` → about +10, `-10mm` → about -10 (Section 15).

## 14. HMI integration points (`index.html`)

| Item | Where |
|---|---|
| Per-frame update | `updateErrorPercentageDisplay(data)` (reads the Section 13.1 fields, updates all displays, counts bags) |
| Ruler, needle, M1/M2, chips | `updateMarkWindowWithError(errorMm)`; needle x = `175 + error*3.5` (350 px = ±50 mm); `REP: <repeatLength + round(error)>mm`; M1 shows `abs(error)` when error < 0, M2 when error > 0 |
| Screen 2 tiles | `#cam-error-pct-val`, `#cam-error-status-badge`, `#cam-error-bar`, `#cam-error-offset-sub`, `#cam-error-win-sub`, `#cam-reg-offset-val`, `#cam-conf-val`, `#full-cam-reg-stat`, `#hud-error-pill`, `#hud-box-front`, `#hud-box-back` |
| Screen 1 | `#live-cam-err-badge`, `#recipe-live-cam-pct`, `#live-cam-err-val`, `#ruler-live-mark-tag` |
| Counters | `HMI_STATE.report.counters = {'0-7','8-15','16-25','over','total'}`; chips `#zone-0-7-count`, `#zone-8-15-count`, `#zone-16-25-count`, `#zone-total-count`; `recordBagInBin(bin)` |
| Job | `jobState`, `startJob()`, `endJob()`, button `#btn-job-stop`; counters are posted to `/api/production` on job end |
| Mark window | `HMI_STATE.recipe.markWindow` (default 40 mm → in-window when `abs(error) <= markWindow/2`) and `repeatLength` (default 740 mm) |
| Recipe id sent to the backend | `HMI_STATE.recipe.numericId` |

## 15. Acceptance tests

| Test | Expected |
|---|---|
| `0mm` / `after_calibration` | `offset_y_mm = 0.0 ± 1`, `confidence >= 0.9`, bin `0-7`, `IN SPEC` |
| `+10mm` | `+10 ± 1.5`, back panel LOW, bin `8-15`, `OUT OF SPEC` |
| `-10mm` | `-10 ± 1.5`, back panel HIGH, bin `8-15`, `OUT OF SPEC` |
| ZERO on any image | that image then reads 0.0 mm |
| Same +10 mm bag, closed loop on, three bags | residuals about +9.4, +1.9, +0.4 mm; counts `8-15` = 1, `0-7` = 2 |
| Blank frame / no marks | `ok=false`, `status="NO MATCH"`; HMI shows NO MATCH and counts nothing |
| 60 bags in 60 seconds (trigger every 1.0 s) | `total = 60` (bins + over + missed), no bag skipped or counted twice |
| Two consecutive bags with the same +3 mm error | counted as **two** bags (different `bag_id`) |
| Result time | `latency_ms <= 200` for at least 99% of bags |
| Same bag held in view (no trigger, fallback mode) | counted **once** (Section 10 fallback) |
| STN2 = OFF | error forced to 0.0 mm, camera stopped, no counting |
| Job ended | `/api/production` receives `c0_7, c8_15, c16_25, total` with start and end time |

## 16. Known limits and items to fix in `index.html`

Limits of the method:

- Accuracy was verified only on the supplied artwork images, not on a real Pi camera. Expect about ±0.5 to ±1.5 mm with a basic setup; re-tune the magenta HSV range, ROIs and `px_per_mm` on the real machine. A bag that is not flat (wrinkles) is the largest real-world error source.
- The scale (1.835 – 1.9 px/mm) depends on the camera distance; set it from the real mark width in mm.
- Lens distortion and perspective are not corrected; keep the camera square to the bag, or undistort once.
- The correction loop (Section 11) is not part of `index.html`; the output to the register actuator still has to be connected.

Items observed in the current `index.html` (worth fixing):

1. **Sign of the HUD back-box shift.** `updateErrorPercentageDisplay` moves the back box with `top = 4.0 - dy*0.25`, so a positive error moves the box **up**, while Section 3 defines positive as the back panel **lower**. Use `4.0 + dy*0.25` if the box should follow the real print direction.
2. **Counting while no job runs.** `recordBagInBin` increments the counters even when no job is active, and `endJob` flushes whatever was counted. Count only while `jobState.active` is true, and reset the counters in `startJob`.
3. **Two different tolerances in the display.** `#cam-error-win-sub` shows `±7.0mm` (pass limit), but the ruler uses the recipe window (`markWindow/2`, default ±20 mm). Label them separately, for example "PASS ±7 / WINDOW ±20".
4. **Zone chip label.** The HTML comment and the 16-25 chip use "15-25"/"16-25" inconsistently; the bin is `> 15 and <= 25`.
5. **No correction value is shown.** Display `corr_mm` once the loop in Section 11 exists.
6. **Counting must be per bag at 60 bags/min.** The current rule in `updateErrorPercentageDisplay` (stability buffer, +/-1.5 mm, 4.0 mm change) would count similar consecutive bags once. Change it to count each new `bag_id` (Section 10) and use the old rule only as a fallback.
