"""RiceVision Phase 1 server - Python standard library only (+ optional cv2/Pillow/picamera2).
  python3 server.py                      -> http://0.0.0.0:8000
  python3 server.py --cert c.pem --key k.pem   -> https (needed for the LAPTOP camera when the UI is opened by IP)
Env: PORT, CAMERA_SOURCE (laptop|pi) overrides the saved setting at startup.
"""
import argparse, base64, hashlib, json, mimetypes, os, re, secrets, sqlite3, ssl, struct, sys, time, threading
for _p in [
    "/usr/lib/python3/dist-packages",
    "/usr/local/lib/python3/dist-packages",
    f"/usr/lib/python3.{sys.version_info.minor}/dist-packages"
]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import vision
from camera import camera
import fbarx_link
import fbarx_api
from fbarx_link import FieldError, BoardError
import config
try:
    import cv2
except Exception:
    cv2 = None
try:
    import numpy as np
except Exception:
    np = None

HERE = Path(__file__).resolve().parent
DB, IMG, CAP, STATIC = HERE / "rice_vision.db", HERE / "images", HERE / "captures", HERE / "static"
MAX_UPLOAD = 12 * 1024 * 1024
WLOCK = threading.RLock()                    # serialise writes (SQLite single writer, re-entrant)

AUTH_SESSIONS = {}                           # session_token -> dict(role, created_at, last_active, operator)
SESSION_TIMEOUT_SEC = 300.0                  # 5 minutes session timeout matching board unlock

def now(): return time.strftime("%Y-%m-%dT%H:%M:%S")
def conn():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA journal_mode=WAL"); return c
def rows(c, sql, a=()): return [dict(r) for r in c.execute(sql, a).fetchall()]
def one(c, sql, a=()): r = c.execute(sql, a).fetchone(); return dict(r) if r else None
def setting(c, k, d=None): r = c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone(); return r[0] if r else d
def log_event(c, event, detail="", operator=None, recipe=None):
    c.execute("INSERT INTO event_log(operator,recipe_name,event,detail) VALUES(?,?,?,?)", (operator, recipe, event, detail))

def log_audit(field, old_val, new_val, status="SUCCESS", operator=None, client_ip=None, action="CALIBRATION_WRITE"):
    with WLOCK:
        c = conn()
        try:
            c.execute("""INSERT INTO audit_log (timestamp, operator, action, field, old_value, new_value, status, client_ip)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (now(), operator or "Operator", action, str(field), str(old_val), str(new_val), status, client_ip or "127.0.0.1"))
            c.commit()
        finally:
            c.close()

def create_session(role="calibrator", operator="Operator"):
    tok = secrets.token_hex(16)
    now_t = time.time()
    with WLOCK:
        AUTH_SESSIONS[tok] = {
            "role": role,
            "created_at": now_t,
            "last_active": now_t,
            "operator": operator or "Operator"
        }
    return tok

def verify_token(req_handler):
    auth_h = req_handler.headers.get("Authorization", "")
    tok = None
    if auth_h.startswith("Bearer "):
        tok = auth_h[7:].strip()
    if not tok:
        tok = req_handler.headers.get("X-Auth-Token") or req_handler.headers.get("X-Cal-Token")
    if not tok:
        return None
    # Check unified token store
    info = fbarx_api.get_token_info(tok)
    if info:
        return {
            "role": info["role"],
            "operator": "Operator",
            "last_active": time.time(),
            "expires_in": info["expires_in"]
        }
    now_t = time.time()
    with WLOCK:
        s = AUTH_SESSIONS.get(tok)
        if not s:
            return None
        if now_t - s["last_active"] > SESSION_TIMEOUT_SEC:
            del AUTH_SESSIONS[tok]
            return None
        s["last_active"] = now_t
        s["expires_in"] = int(SESSION_TIMEOUT_SEC - (now_t - s["last_active"]))
        return s

def init_db():
    c = sqlite3.connect(DB)
    c.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        operator TEXT,
        action TEXT NOT NULL,
        field TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        status TEXT NOT NULL,
        client_ip TEXT
    )""")
    for col in ('front_image_path', 'back_image_path', 'front_image_name', 'back_image_name'):
        try: c.execute(f"ALTER TABLE recipes ADD COLUMN {col} TEXT")
        except Exception: pass
    for col in ('start_time', 'end_time', 'band_edges', 'mark_window'):
        try: c.execute(f"ALTER TABLE production_records ADD COLUMN {col} TEXT")
        except Exception: pass
    for col, typ in (('c_26_w', 'INTEGER DEFAULT 0'), ('unscored', 'INTEGER DEFAULT 0'), ('window_mm', 'INTEGER')):
        try: c.execute(f"ALTER TABLE production_records ADD COLUMN {col} {typ}")
        except Exception: pass
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('camera_sim_error','live')")
    # Camera Line-Distance Calibration Settings (11-11-26.md Section 3 & 4)
    for k, v in (
        ('scale_px_per_mm', '1.0'),
        ('scale_px_per_mm_x', '1.0'),
        ('scale_px_per_mm_y', '1.0'),
        ('zero_offset_mm', '0.0'),
        ('camera_nominal_mm', '0.0'),
        ('camera_tolerance_mm', '7.0'),
        ('line_orientation', 'vertical'),
        ('line_dark', '1'),
        ('front_roi', '[0.0, 0.40, 0.50, 0.60]'),
        ('back_roi', '[0.50, 0.40, 0.50, 0.60]'),
        ('working_distance_m', '1.5'),
        ('bag_length_mm', '1860.0'),
        ('bag_width_mm', '535.0'),
        ('between_bags_mm', '50.0'),
        ('nominal_length_mm', '1860.0'),
        ('nominal_skew_top_mm', '0.0'),
        ('nominal_skew_bottom_mm', '0.0'),
        ('roi_top_left', '[0.0, 0.0, 0.28, 0.25]'),
        ('roi_top_right', '[0.72, 0.0, 0.28, 0.25]'),
        ('roi_bottom_left', '[0.0, 0.75, 0.28, 0.25]'),
        ('roi_bottom_right', '[0.72, 0.75, 0.28, 0.25]'),
        ('calibrated_width', '1600'),
        ('calibrated_height', '1200'),
    ):
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    c.execute("""CREATE TABLE IF NOT EXISTS machine_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        stn1_mode TEXT NOT NULL DEFAULT 'OFF',
        stn1_output_pct REAL NOT NULL DEFAULT 0.0,
        stn1_ammeter REAL NOT NULL DEFAULT 0.0,
        stn1_unit TEXT NOT NULL DEFAULT 'KG',
        stn1_brake_type TEXT NOT NULL DEFAULT 'magnetic',
        stn1_stension REAL NOT NULL DEFAULT 5.0,
        stn1_atension REAL NOT NULL DEFAULT 0.0,
        stn2_mode TEXT NOT NULL DEFAULT 'OFF',
        stn2_output_pct REAL NOT NULL DEFAULT 0.0,
        stn2_ammeter REAL NOT NULL DEFAULT 0.0,
        stn2_speed_mpm INTEGER NOT NULL DEFAULT 0,
        stn2_brake_type TEXT NOT NULL DEFAULT 'magnetic',
        stn2_repeat_length_actual REAL NOT NULL DEFAULT 740.0,
        stn2_repeat_length_set REAL NOT NULL DEFAULT 740.0,
        stn2_mark_window INTEGER NOT NULL DEFAULT 40,
        stn2_mark_offset INTEGER NOT NULL DEFAULT 0,
        job_active INTEGER NOT NULL DEFAULT 0,
        job_id INTEGER,
        job_recipe_id INTEGER,
        job_recipe_name TEXT,
        job_operator TEXT,
        job_start_time TEXT,
        job_end_time TEXT,
        cnt_0_7 INTEGER NOT NULL DEFAULT 0,
        cnt_8_15 INTEGER NOT NULL DEFAULT 0,
        cnt_16_25 INTEGER NOT NULL DEFAULT 0,
        cnt_26_w INTEGER NOT NULL DEFAULT 0,
        cnt_unscored INTEGER NOT NULL DEFAULT 0,
        cnt_total INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    )""")
    c.execute("INSERT OR IGNORE INTO machine_state(id) VALUES(1)")

    c.execute("""CREATE TABLE IF NOT EXISTS calibration_store (
        category TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        updated_at TEXT,
        PRIMARY KEY (category, key)
    )""")
    default_cal = [
        ('stn1_control', 'propBand', '20.0'),
        ('stn1_control', 'integTime', '15.0'),
        ('stn1_control', 'derivTime', '2.0'),
        ('stn1_control', 'minOutput', '0.0'),
        ('stn1_control', 'maxOutput', '100.0'),
        ('stn1_loadcell', 'zeroRaw', '1024'),
        ('stn1_loadcell', 'calWeight', '25.0'),
        ('stn1_loadcell', 'spanRaw', '16384'),
        ('stn2', 'encoderPprSet', '1024'),
        ('stn2', 'cylinderCircumference', '740'),
        ('stn2', 'brakeCurrentCal', '2500'),
        ('stn2', 'acErr', '7.0'),
        ('stn2', 'dcErr', '15.0'),
        ('stn2', 'spkErr', '25.0'),
    ]
    for cat, k, v in default_cal:
        c.execute("INSERT OR IGNORE INTO calibration_store(category, key, value) VALUES(?,?,?)", (cat, k, v))

    if os.environ.get("CAMERA_SOURCE") in ("laptop", "pi"):
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('camera_source',?)", (os.environ["CAMERA_SOURCE"],))
    c.commit(); c.close(); IMG.mkdir(exist_ok=True); CAP.mkdir(exist_ok=True)

def load_camera_calibration_from_db(c):
    """Load calibration parameters from database settings and sync into vision module."""
    cal = dict(vision.DEFAULT_CALIBRATION)
    try:
        scale = setting(c, "scale_px_per_mm")
        if scale: cal["scale_px_per_mm"] = float(scale)
        scale_x = setting(c, "scale_px_per_mm_x")
        if scale_x: cal["scale_px_per_mm_x"] = float(scale_x)
        scale_y = setting(c, "scale_px_per_mm_y")
        if scale_y: cal["scale_px_per_mm_y"] = float(scale_y)
        zero = setting(c, "zero_offset_mm")
        if zero is not None: cal["zero_offset_mm"] = float(zero)
        nom = setting(c, "camera_nominal_mm")
        if nom is not None: cal["nominal_mm"] = float(nom)
        tol = setting(c, "camera_tolerance_mm")
        if tol: cal["tolerance_mm"] = float(tol)
        orient = setting(c, "line_orientation")
        if orient: cal["orientation"] = orient
        dark = setting(c, "line_dark")
        if dark is not None: cal["dark_line"] = (str(dark).lower() in ("1", "true", "yes"))
        froi = setting(c, "front_roi")
        if froi:
            cal["front_roi"] = json.loads(froi) if isinstance(froi, str) and froi.startswith("[") else cal["front_roi"]
        broi = setting(c, "back_roi")
        if broi:
            cal["back_roi"] = json.loads(broi) if isinstance(broi, str) and broi.startswith("[") else cal["back_roi"]
        nom_len = setting(c, "nominal_length_mm")
        if nom_len is not None: cal["nominal_length_mm"] = float(nom_len)
        wd = setting(c, "working_distance_m")
        if wd: cal["working_distance_m"] = float(wd)
        bl = setting(c, "bag_length_mm")
        if bl: cal["bag_length_mm"] = float(bl)
        bw = setting(c, "bag_width_mm")
        if bw: cal["bag_width_mm"] = float(bw)
        bb = setting(c, "between_bags_mm")
        if bb: cal["between_bags_mm"] = float(bb)
        skew_t = setting(c, "nominal_skew_top_mm")
        if skew_t is not None: cal["nominal_skew_top_mm"] = float(skew_t)
        skew_b = setting(c, "nominal_skew_bottom_mm")
        if skew_b is not None: cal["nominal_skew_bottom_mm"] = float(skew_b)
        for roi_k in ("roi_top_left", "roi_top_right", "roi_bottom_left", "roi_bottom_right"):
            roi_v = setting(c, roi_k)
            if roi_v:
                cal[roi_k] = json.loads(roi_v) if isinstance(roi_v, str) and roi_v.startswith("[") else cal[roi_k]
        w_cal = setting(c, "calibrated_width")
        if w_cal: cal["calibrated_width"] = int(w_cal)
        h_cal = setting(c, "calibrated_height")
        if h_cal: cal["calibrated_height"] = int(h_cal)
    except Exception:
        pass
    vision.set_camera_calibration(cal)
    return cal

SERVER_START_ID = secrets.token_hex(4)
STATE_VERSION = 1

def calibration_for_active_recipe():
    with WLOCK:
        c = conn()
        try:
            cal = load_camera_calibration_from_db(c)
            m = one(c, "SELECT job_recipe_id FROM machine_state WHERE id=1")
            rid = m["job_recipe_id"] if m else None
            cal_rows = rows(c, "SELECT key, value FROM calibration_store WHERE category='camera'")
            for r in cal_rows:
                k, v = r["key"], r["value"]
                try:
                    if k in ("scale_px_per_mm", "zero_offset_mm", "nominal_distance_mm"):
                        cal[k] = float(v)
                    elif k in ("calibrated_width", "calibrated_height", "nominal_distance_px"):
                        cal[k] = int(float(v))
                    else:
                        cal[k] = v
                except Exception:
                    cal[k] = v
            if rid:
                rec = one(c, "SELECT repeat_length_mm, width_mm FROM recipes WHERE recipe_id=?", (rid,))
                if rec and rec.get("repeat_length_mm"):
                    cal["repeat_length_mm"] = float(rec["repeat_length_mm"])
                if rec and rec.get("width_mm"):
                    cal["bag_width_mm"] = float(rec["width_mm"])
            return cal
        finally:
            c.close()

class CameraService(threading.Thread):
    daemon = True
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.latest = {
            "ok": False,
            "status": "NO FRAME",
            "error_mm": 0.0,
            "error_px": 0.0,
            "band": "unscored",
            "confidence": 0.0,
            "frame_id": 0,
            "t": 0.0
        }

    def run(self):
        last = -1
        while True:
            try:
                frame, fid = camera.wait_new(last, 1.0)
                if frame is None:
                    self._set({
                        "ok": False,
                        "status": "NO FRAME",
                        "camera": camera.info(),
                        "error_mm": 0.0,
                        "band": "unscored",
                        "confidence": 0.0,
                        "frame_id": last,
                        "t": time.time()
                    })
                    time.sleep(0.05)
                    continue
                last = fid
                cal = calibration_for_active_recipe()
                try:
                    res = vision.compare_front_back(frame, calibration=cal)
                except Exception as e:
                    res = {"ok": False, "status": "ERROR", "reason": str(e), "error_mm": 0.0, "band": "unscored", "confidence": 0.0}
                res.update(frame_id=fid, t=getattr(camera, "frame_time", time.time()))
                if res.get("ok"):
                    err_val = float(res.get("error_mm", 0.0))
                    fb_snap = fbarx_link.link.state()
                    s2_mode = fb_snap.get("mode", "OFF")
                    if s2_mode != "OFF":
                        fbarx_link.link.set_live_sim_error(err_val, valid=True)
                        if s2_mode == "AUTO":
                            corr = update_closed_loop_correction(err_val, is_auto=True, is_sim=fbarx_link.SIMULATED)
                            res["corr_mm"] = corr
                self._set(res)
            except Exception:
                time.sleep(0.1)

    def _set(self, r):
        with self.lock:
            self.latest = r

camera_service = CameraService()
STREAM_TOKEN = 0


# ---------- closed loop error reduction (error.md Section 11) & bag_id tracking ----------
GLOBAL_BAG_ID = 1000
CLOSED_LOOP_CORR_MM = 0.0
CLOSED_LOOP_RECENT = []
SIM_ACTUATOR_CORR_MM = 0.0

def reset_closed_loop():
    global CLOSED_LOOP_CORR_MM, CLOSED_LOOP_RECENT, SIM_ACTUATOR_CORR_MM
    CLOSED_LOOP_CORR_MM = 0.0
    CLOSED_LOOP_RECENT.clear()
    SIM_ACTUATOR_CORR_MM = 0.0

def update_closed_loop_correction(error_mm, is_auto=True, is_sim=False):
    global CLOSED_LOOP_CORR_MM, CLOSED_LOOP_RECENT, SIM_ACTUATOR_CORR_MM
    if not is_auto:
        return round(CLOSED_LOOP_CORR_MM, 1)
    if abs(error_mm) > 1.0:  # Dead-band +/- 1.0 mm per Section 11
        CLOSED_LOOP_RECENT.append(error_mm)
        if len(CLOSED_LOOP_RECENT) > 5:
            CLOSED_LOOP_RECENT.pop(0)
        gain = 0.8  # Gain 0.5 - 0.8 per Section 11
        corr_delta = -(gain * error_mm)
        CLOSED_LOOP_CORR_MM = max(-25.0, min(25.0, CLOSED_LOOP_CORR_MM + corr_delta))
        if is_sim:
            SIM_ACTUATOR_CORR_MM = CLOSED_LOOP_CORR_MM
    else:
        CLOSED_LOOP_RECENT.clear()
    return round(CLOSED_LOOP_CORR_MM, 1)

# ---------- images ----------
def slug(s): return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "img"
def img_size(data, mime):
    try:
        from PIL import Image; import io; return Image.open(io.BytesIO(data)).size
    except Exception: pass
    try:
        if mime == "image/png": return struct.unpack(">II", data[16:24])
        if mime == "image/jpeg":
            i = 2
            while i < len(data):
                if data[i] != 0xFF: i += 1; continue
                m = data[i + 1]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9]); return w, h
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except Exception: pass
    return None, None

def decode_data_url(u):
    m = re.match(r"data:([\w/+.-]+);base64,(.*)", u or "", re.S)
    if not m: raise ValueError("bad data URL")
    mime, b = m.group(1), base64.b64decode(m.group(2))
    if len(b) > MAX_UPLOAD: raise ValueError("file too large (max 12 MB)")
    if mime not in ("image/jpeg", "image/png", "application/pdf"): raise ValueError("only JPG/PNG/PDF allowed")
    return mime, b

def save_image(c, recipe_id, recipe_name, name, data_url):
    mime, data = decode_data_url(data_url)
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}[mime]
    fname = f"{slug(recipe_name)}_{time.strftime('%Y%m%d%H%M%S')}{ext}"
    (IMG / fname).write_bytes(data); w, h = img_size(data, mime)
    sha = hashlib.sha256(data).hexdigest()
    cur = c.execute("""INSERT INTO recipe_images(recipe_id,image_name,image_path,mime_type,width_px,height_px,size_bytes,sha256,is_active)
                       VALUES(?,?,?,?,?,?,?,?,0)""", (recipe_id, name or fname, f"images/{fname}", mime, w, h, len(data), sha))
    c.execute("UPDATE recipe_images SET is_active=1 WHERE image_id=?", (cur.lastrowid,))   # trigger deactivates older ones
    return cur.lastrowid

# ---------- recipe <-> UI mapping ----------
RECIPE_COLS = {  # UI key : DB column
    "repeatLength": "repeat_length_mm", "width": "width_mm", "material": "material", "markWindow": "mark_window_mm",
    "markOffset": "mark_offset_mm", "sTensionTarget": "s_tension_kg", "frontSensor": "front_sensor", "frontMark": "front_mark",
    "frontBackground": "front_background", "backSensor": "back_sensor", "backMark": "back_mark", "backBackground": "back_background",
    "brandTamil": "brand_tamil", "product": "product", "netWeight": "bag_weight_kg"}
SQL_RECIPES = """SELECT r.*, i.image_id, i.image_name, i.image_path, i.mime_type AS image_type
                 FROM recipes r
                 LEFT JOIN (
                     SELECT recipe_id, image_id, image_name, image_path, mime_type
                     FROM recipe_images
                     WHERE is_active = 1
                     GROUP BY recipe_id
                 ) i ON i.recipe_id=r.recipe_id"""
_SIM_FRAME_CACHE = {}

def get_sim_frame(err="0mm", recipe_name=""):
    cache_key = (str(err or "").lower().strip(), str(recipe_name or "").lower().strip())
    if cache_key in _SIM_FRAME_CACHE:
        return _SIM_FRAME_CACHE[cache_key]

    err_norm = str(err or "").lower().replace(" ", "").replace("_", "")
    rec_norm = str(recipe_name or "").lower()
    prefix = "veerashivaji"
    if "thangamayil" in rec_norm:
        prefix = "thangamayil"
    elif "india" in rec_norm:
        prefix = "indiagate"
    elif "kohinoor" in rec_norm:
        prefix = "kohinoor"
    elif "royal" in rec_norm:
        prefix = "royal_bullet"

    if "plus" in err_norm or "+10" in err_norm or "p10" in err_norm or err_norm in ("10mm", "+10", "10"):
        fn = f"{prefix}_front_back_plus10mm.jpg"
    elif "minus" in err_norm or "-10" in err_norm or "m10" in err_norm:
        fn = f"{prefix}_front_back_minus10mm.jpg"
    else:
        fn = f"{prefix}_front_back_0mm.jpg"
    p = IMG / fn
    raw = None
    if p.is_file(): raw = p.read_bytes()
    elif (IMG / "veerashivaji_front_back_0mm.jpg").is_file(): raw = (IMG / "veerashivaji_front_back_0mm.jpg").read_bytes()
    elif (IMG / "veera_shivaji_26kg.jpg").is_file(): raw = (IMG / "veera_shivaji_26kg.jpg").read_bytes()
    if not raw: return b""

    out_jpg = raw
    if cv2 is not None and np is not None:
        try:
            arr = np.frombuffer(raw, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                cv2.rectangle(img, (0, 0), (w, 42), (0, 0, 180), -1)
                cv2.putText(img, "SIMULATED CAMERA - NO HARDWARE ATTACHED", (15, 29),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)
                out_jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
        except Exception:
            pass
    _SIM_FRAME_CACHE[cache_key] = out_jpg
    return out_jpg

def to_ui(r):
    name = r["name"]
    img_path = r.get("image_path") or ""
    front_path = r.get("front_image_path") or ""
    back_path = r.get("back_image_path") or ""

    main_url = ("/" + img_path) if img_path else (("/" + front_path) if front_path else "")
    f_url = ("/" + front_path) if front_path else main_url
    b_url = ("/" + back_path) if back_path else ""

    u = {
        "recipeId": r["recipe_id"],
        "name": name,
        "brandTamil": r.get("brand_tamil") or "",
        "product": r.get("product") or "",
        "netWeight": float(r.get("bag_weight_kg") or 25),
        "imageId": r.get("image_id"),
        "imageName": r.get("image_name") or r.get("front_image_name") or (name + " Bag"),
        "imageType": r.get("image_type") or "image/jpeg",
        "imageUrl": main_url,
        "frontImageUrl": f_url,
        "backImageUrl": b_url,
        "frontImageName": r.get("front_image_name") or (name + " Front"),
        "backImageName": r.get("back_image_name") or ""
    }
    for k, col in RECIPE_COLS.items():
        if col in r.keys():
            u[k] = r[col]
    return u

def validate_recipe_params(p):
    """Validate recipe parameters strictly within engineering bounds.
    Refuses out-of-range values with FieldError (HTTP 400 naming field) instead of silently clamping.
    """
    o = {}
    # Repeat length (mm): 100 - 2000
    if "repeatLength" in p:
        try: rl = float(p["repeatLength"])
        except (TypeError, ValueError): raise FieldError("repeatLength", "Repeat length must be a valid number")
        if rl < 100 or rl > 2000:
            raise FieldError("repeatLength", f"Repeat length {rl} mm is out of range (100 - 2000 mm)")
        o["repeatLength"] = int(round(rl))
    else:
        o["repeatLength"] = 740

    # Width (mm): 1 - 1000
    if "width" in p:
        try: w = float(p["width"])
        except (TypeError, ValueError): raise FieldError("width", "Width must be a valid number")
        if w < 1 or w > 1000:
            raise FieldError("width", f"Width {w} mm is out of range (1 - 1000 mm)")
        o["width"] = int(round(w))
    else:
        o["width"] = 495

    # Mark window (mm): 10 - 99
    if "markWindow" in p:
        try: mw = float(p["markWindow"])
        except (TypeError, ValueError): raise FieldError("markWindow", "Mark window must be a valid number")
        if mw < 10 or mw > 99:
            raise FieldError("markWindow", f"Mark window {mw} mm is out of range (10 - 99 mm)")
        o["markWindow"] = int(round(mw))
    else:
        o["markWindow"] = 40

    # Mark offset (mm): -999 - 999
    if "markOffset" in p:
        try: mo = float(p["markOffset"])
        except (TypeError, ValueError): raise FieldError("markOffset", "Mark offset must be a valid number")
        if mo < -999 or mo > 999:
            raise FieldError("markOffset", f"Mark offset {mo} mm is out of range (-999 - 999 mm)")
        o["markOffset"] = int(round(mo))
    else:
        o["markOffset"] = 0

    # S-Tension target (kg): 0.0 - 99.9
    if "sTensionTarget" in p:
        try: st = float(p["sTensionTarget"])
        except (TypeError, ValueError): raise FieldError("sTensionTarget", "S-Tension target must be a valid number")
        if st < 0.0 or st > 99.9:
            raise FieldError("sTensionTarget", f"S-Tension target {st} kg is out of range (0.0 - 99.9 kg)")
        o["sTensionTarget"] = round(st, 1)
    else:
        o["sTensionTarget"] = 5.0

    # Net weight (kg): 1 - 100
    if "netWeight" in p:
        try: nw = float(p["netWeight"])
        except (TypeError, ValueError): raise FieldError("netWeight", "Net weight must be a valid number")
        if nw < 1.0 or nw > 100.0:
            raise FieldError("netWeight", f"Net weight {nw} kg is out of range (1 - 100 kg)")
        o["netWeight"] = round(nw, 1)
    else:
        o["netWeight"] = 25.0

    o["material"] = str(p.get("material") or "BOPP")[:40]
    o["brandTamil"] = str(p.get("brandTamil") or "")[:100]
    o["product"] = str(p.get("product") or "")[:100]
    for k in ("frontSensor", "frontMark", "frontBackground", "backSensor", "backMark", "backBackground"):
        o[k] = int(p.get(k) or 0)
    return o

clean_params = validate_recipe_params

def upsert_operator(c, name, photo_data_url=None):
    name = (name or "").strip()
    if not name: return None
    c.execute("INSERT OR IGNORE INTO operators(name) VALUES(?)", (name,))
    op = one(c, "SELECT * FROM operators WHERE name=?", (name,))
    c.execute("UPDATE operators SET is_active=1 WHERE operator_id=?", (op["operator_id"],))
    if photo_data_url:
        mime, data = decode_data_url(photo_data_url)
        fn = f"images/operator_{slug(name)}.jpg"; (HERE / fn).write_bytes(data)
        c.execute("UPDATE operators SET photo_path=? WHERE operator_id=?", (fn, op["operator_id"]))
    return op["operator_id"]

# ---------- request handler ----------
_CANDS_CACHE = None

def get_all_candidates(c=None):
    global _CANDS_CACHE
    if _CANDS_CACHE is not None:
        return _CANDS_CACHE
    close_c = False
    if c is None:
        c = conn()
        close_c = True
    cands = []
    seen_paths = set()
    def add_cand(cid, cname, rel_p):
        if not rel_p: return
        p = (HERE / rel_p).resolve()
        k = (cid, str(p))
        if k not in seen_paths and p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png'):
            seen_paths.add(k)
            cands.append((cid, cname, str(p)))
    for r in rows(c, "SELECT recipe_id, name, front_image_path, back_image_path FROM recipes"):
        add_cand(r["recipe_id"], r["name"], r.get("front_image_path"))
        add_cand(r["recipe_id"], r["name"], r.get("back_image_path"))
    for r in rows(c, "SELECT r.recipe_id, r.name, i.image_path FROM recipes r JOIN recipe_images i ON i.recipe_id=r.recipe_id"):
        add_cand(r["recipe_id"], r["name"], r.get("image_path"))
    if close_c:
        c.close()
    _CANDS_CACHE = cands
    return cands

def clear_candidates_cache():
    global _CANDS_CACHE
    _CANDS_CACHE = None
    if hasattr(vision, "_cache"):
        vision._cache.clear()

def get_full_state():
    with WLOCK:
        c = conn()
        try:
            m = one(c, "SELECT * FROM machine_state WHERE id=1")
            a = one(c, "SELECT * FROM active_state WHERE id=1") or {}
            rec = one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (a.get("recipe_id"),)) if a.get("recipe_id") else None
            op = one(c, "SELECT name FROM operators WHERE operator_id=?", (a.get("operator_id"),)) if a.get("operator_id") else None
            cam_src = setting(c, "camera_source", "laptop")
        finally:
            c.close()

    fb_snap = fbarx_link.link.state()
    total_cnt = fb_snap.get("counters", {}).get("total", 0)
    cnt_0_7 = fb_snap.get("counters", {}).get("0-7", 0)
    cnt_8_15 = fb_snap.get("counters", {}).get("8-15", 0)
    cnt_16_25 = fb_snap.get("counters", {}).get("16-25", 0)
    cnt_26_w = fb_snap.get("counters", {}).get("26-window", 0)
    cnt_unscored = fb_snap.get("counters", {}).get("unscored", 0)

    pass_pct = round((cnt_0_7 / total_cnt) * 100.0, 1) if total_cnt > 0 else 100.0
    fail_pct = round(((total_cnt - cnt_0_7) / total_cnt) * 100.0, 1) if total_cnt > 0 else 0.0

    stn2_mode = fb_snap.get("mode") or (m["stn2_mode"] if m else "AUTO")
    stn1_mode = m["stn1_mode"] if m else "OFF"
    stn1_is_off = (stn1_mode == "OFF")
    stn2_is_off = (stn2_mode == "OFF")

    val1 = m.get("stn1_output_pct") if m else None
    stn1_out = 0.0 if stn1_is_off else (float(val1) if val1 is not None else 0.0)
    amp1 = m.get("stn1_ammeter") if m else None
    stn1_amp = 0.0 if stn1_is_off else (float(amp1) if amp1 is not None else 0.0)
    aten1 = m.get("stn1_atension") if m else None
    stn1_aten = 0.0 if stn1_is_off else (float(aten1) if aten1 is not None else 0.0)

    val2 = fb_snap.get("outputPct")
    stn2_out = 0.0 if stn2_is_off else (float(val2) if val2 is not None else 0.0)
    amp2 = fb_snap.get("ammeter")
    stn2_amp = 0.0 if stn2_is_off else (float(amp2) if amp2 is not None else 0.0)
    spd2 = fb_snap.get("speedMpm")
    stn2_spd = 0 if stn2_is_off else (int(spd2) if spd2 is not None else 0)

    job_active = bool(m.get("job_active", 0)) if m else False
    start_time_iso = m.get("job_start_time") if m else None
    elapsed_sec = 0
    if job_active and start_time_iso:
        try:
            t_start = time.mktime(time.strptime(start_time_iso, "%Y-%m-%dT%H:%M:%S"))
            elapsed_sec = max(0, int(time.time() - t_start))
        except Exception:
            pass
    mins = elapsed_sec // 60
    secs = elapsed_sec % 60
    duration_str = f"{mins}m {secs}s"

    cur_err = float(fb_snap.get("markError", 0.0))
    mw = int(fb_snap.get("markWindow", 40))
    active_zone = fbarx_link.band_key(cur_err, mw)
    cam_badge = "AUTO LIVE" if stn2_mode == "AUTO" else ("MAN LIVE" if stn2_mode == "MAN" else "STANDBY LIVE")

    cam_latest = camera_service.latest if 'camera_service' in globals() else {}
    return {
        "ok": True,
        "server_start_id": SERVER_START_ID,
        "state_version": STATE_VERSION,
        "connected": fb_snap.get("connected", True),
        "status": fb_snap.get("status", "OK"),
        "simulated": fb_snap.get("simulated", False),
        "server_time": now(),
        "timestamp": time.time(),
        "stn1": {
            "mode": stn1_mode,
            "outputPct": stn1_out,
            "ammeter": stn1_amp,
            "unit": m.get("stn1_unit", "KG") if m else "KG",
            "sTensionTarget": float(m.get("stn1_stension", 5.0)) if m else 5.0,
            "aTension": stn1_aten,
            "brakeType": m.get("stn1_brake_type", "magnetic") if m else "magnetic",
            "isInterlocked": stn1_is_off
        },
        "stn2": {
            "mode": stn2_mode,
            "outputPct": stn2_out,
            "ammeter": stn2_amp,
            "speedMpm": stn2_spd,
            "repeatLength": fb_snap.get("repeatLength", 740),
            "repeatLengthActual": fb_snap.get("repeatLengthActual", 740.6),
            "markWindow": mw,
            "markOffset": fb_snap.get("markOffset", 0),
            "brakeType": m.get("stn2_brake_type", "magnetic") if m else "magnetic",
            "m1": fb_snap.get("m1", {"status": "OK", "marks": 1}),
            "m2": fb_snap.get("m2", {"status": "OK", "marks": 1}),
            "isInterlocked": stn2_is_off
        },
        "job": {
            "active": job_active,
            "jobId": m.get("job_id") if m else None,
            "recipeId": m.get("job_recipe_id") if m else (rec["recipe_id"] if rec else None),
            "recipeName": m.get("job_recipe_name") if (m and m.get("job_recipe_name")) else (rec["name"] if rec else ""),
            "operator": m.get("job_operator") if (m and m.get("job_operator")) else (op["name"] if op else ""),
            "startTime": start_time_iso,
            "elapsedSec": elapsed_sec,
            "durationStr": duration_str
        },
        "counters": {
            "0-7": cnt_0_7,
            "8-15": cnt_8_15,
            "16-25": cnt_16_25,
            "26-window": cnt_26_w,
            "unscored": cnt_unscored,
            "total": total_cnt,
            "passPct": pass_pct,
            "failPct": fail_pct,
            "activeZone": active_zone,
            "counterBands": fb_snap.get("counterBands", [])
        },
        "registration": {
            "errorMm": cur_err,
            "status": "IN SPEC" if abs(cur_err) <= 7.0 else "OUT OF SPEC",
            "regErrMm": round(abs(cur_err), 1),
            "repeatLengthActual": fb_snap.get("repeatLengthActual", 740.6),
            "repeatLengthSet": fb_snap.get("repeatLength", 740),
            "markWindow": mw,
            "valid": fb_snap.get("markErrorValid", True),
            "frontLinePx": 312.4,
            "backLinePx": 312.4 + (cur_err * 4.0),
            "bagId": GLOBAL_BAG_ID,
            "corrMm": round(CLOSED_LOOP_CORR_MM, 1)
        },
        "camera": {
            "running": getattr(camera, "running", False),
            "modeBadge": cam_badge,
            "fps": getattr(camera, "fps", 25.0) or 25.0,
            "confidence": cam_latest.get("confidence", 0.98),
            "latest": cam_latest,
            "info": camera.info()
        },
        "recipe": to_ui(rec) if rec else None,
        "operator": op["name"] if op else "",
        "loaded_at": a.get("loaded_at"),
        "camera_source": "pi",
        "vision": vision.AVAILABLE
    }

def handle_action(c, d, client_ip="127.0.0.1"):
    global STATE_VERSION
    STATE_VERSION += 1
    action = d.get("action")
    action = d.get("action")
    if not action:
        raise ValueError("Missing action parameter")

    if action == "set_mode":
        station = d.get("station")
        mode = str(d.get("mode", "")).upper()
        if station not in ("stn1", "stn2"):
            raise ValueError(f"Invalid station: {station}")
        if mode not in ("AUTO", "MAN", "OFF"):
            raise ValueError(f"Invalid mode: {mode}")

        if station == "stn1":
            if mode == "OFF":
                c.execute("UPDATE machine_state SET stn1_mode=?, stn1_output_pct=0.0, stn1_ammeter=0.0, updated_at=? WHERE id=1", (mode, now()))
            elif mode == "MAN":
                row = one(c, "SELECT stn1_output_pct FROM machine_state WHERE id=1")
                cur_out = float(row.get("stn1_output_pct", 0.0)) if row else 0.0
                out_val = 50.0 if cur_out == 0.0 else cur_out
                amp_val = round((out_val / 100.0) * 3.27, 2)
                c.execute("UPDATE machine_state SET stn1_mode=?, stn1_output_pct=?, stn1_ammeter=?, updated_at=? WHERE id=1", (mode, out_val, amp_val, now()))
            else:
                c.execute("UPDATE machine_state SET stn1_mode=?, stn1_ammeter=1.8, updated_at=? WHERE id=1", (mode, now()))
        elif station == "stn2":
            fbarx_link.link.set_mode(mode)
            if mode == "OFF":
                c.execute("UPDATE machine_state SET stn2_mode=?, stn2_output_pct=0.0, stn2_ammeter=0.0, updated_at=? WHERE id=1", (mode, now()))
                camera.stop()
            elif mode == "MAN":
                cur_out = float(fbarx_link.link.actual_output_pct or 0.0)
                out_val = 55.0 if cur_out == 0.0 else cur_out
                fbarx_link.link.set_output(out_val)
                amp_val = round((out_val / 100.0) * 3.27, 2)
                c.execute("UPDATE machine_state SET stn2_mode=?, stn2_output_pct=?, stn2_ammeter=?, updated_at=? WHERE id=1", (mode, out_val, amp_val, now()))
            else:
                c.execute("UPDATE machine_state SET stn2_mode=?, stn2_ammeter=1.8, updated_at=? WHERE id=1", (mode, now()))
        log_event(c, "MODE_CHANGED", f"{station}={mode}")
        return {"ok": True}

    elif action in ("reset_to_off", "all_off", "init_off", "page_reload"):
        c.execute("""UPDATE machine_state 
                     SET stn1_mode='OFF', stn1_output_pct=0.0, stn1_ammeter=0.0, stn1_atension=0.0,
                         stn2_mode='OFF', stn2_output_pct=0.0, stn2_ammeter=0.0, updated_at=?
                     WHERE id=1""", (now(),))
        fbarx_link.link.set_mode('OFF')
        fbarx_link.link.actual_output_pct = 0.0
        fbarx_link.link.target_output_pct = 0.0
        global STREAM_TOKEN
        STREAM_TOKEN += 1
        camera.stop()
        reset_closed_loop()
        log_event(c, "RESET_ALL_OFF", "All stations and camera reset to OFF state")
        return {"ok": True}

    elif action == "step_output":
        station = d.get("station", "stn1")
        direction = d.get("direction")
        if not direction:
            delta_val = float(d.get("delta", 0))
            direction = "down" if delta_val < 0 else "up"
        direction = str(direction).lower()
        if station not in ("stn1", "stn2"):
            raise ValueError("Invalid station")
        if direction not in ("up", "down"):
            raise ValueError("Direction must be up or down")

        delta = 1.0 if direction == "up" else -1.0
        client_cur = d.get("current")
        if station == "stn1":
            row = one(c, "SELECT stn1_output_pct, stn1_mode FROM machine_state WHERE id=1")
            if row.get("stn1_mode") != "MAN":
                raise ValueError("STN 1 output can only be stepped in MAN mode")
            val = row.get("stn1_output_pct")
            cur = float(client_cur) if client_cur is not None else (float(val) if val is not None else 0.0)
            new_val = max(0.0, min(100.0, round(cur + delta, 1)))
            new_amp = round((new_val / 100.0) * 3.27, 2)
            c.execute("UPDATE machine_state SET stn1_output_pct=?, stn1_ammeter=?, updated_at=? WHERE id=1", (new_val, new_amp, now()))
        elif station == "stn2":
            if client_cur is not None:
                cur = float(client_cur)
                new_val = max(0.0, min(100.0, round(cur + delta, 1)))
                fbarx_link.link.set_output(new_val)
            else:
                new_val = fbarx_link.link.step_output(direction)
            new_amp = round((float(new_val) / 100.0) * 3.27, 2)
            c.execute("UPDATE machine_state SET stn2_output_pct=?, stn2_ammeter=?, updated_at=? WHERE id=1", (round(float(new_val), 1), new_amp, now()))
        return {"ok": True, "station": station, "direction": direction, "outputPct": new_val}

    elif action == "set_output":
        station = d.get("station", "stn1")
        val = max(0.0, min(100.0, float(d.get("value", d.get("pct", d.get("output", 0.0))))))
        val = round(val, 1)
        amp_val = round((val / 100.0) * 3.27, 2)
        if station == "stn1":
            c.execute("UPDATE machine_state SET stn1_output_pct=?, stn1_ammeter=?, updated_at=? WHERE id=1", (val, amp_val, now()))
        else:
            fbarx_link.link.set_output(val)
            c.execute("UPDATE machine_state SET stn2_output_pct=?, stn2_ammeter=?, updated_at=? WHERE id=1", (val, amp_val, now()))
        return {"ok": True, "station": station, "outputPct": val}

    elif action == "set_repeat_length":
        raw_val = float(d.get("value", 0))
        # Accepts 100-2000 mm; refuses 99 and 2001 (M5)
        if raw_val < 100 or raw_val > 2000:
            raise ValueError("Repeat Length must be between 100 and 2000 mm")
        val = int(round(raw_val))
        fbarx_link.link.set_repeat_length(val, remember=True)
        c.execute("UPDATE machine_state SET stn2_repeat_length_set=?, updated_at=? WHERE id=1", (val, now()))
        return {"ok": True, "repeatLength": val}

    elif action == "set_mark_window":
        val = float(d.get("value", 0))
        if val < 10 or val > 99:
            raise ValueError("Mark Window must be between 10 and 99 mm")
        fbarx_link.link.set_mark_window(int(round(val)), remember=True)
        c.execute("UPDATE machine_state SET stn2_mark_window=?, updated_at=? WHERE id=1", (int(round(val)), now()))
        return {"ok": True}

    elif action == "set_stension":
        val = float(d.get("value", 0))
        if val < 0.0 or val > 50.0:
            raise ValueError("S-Tension must be between 0.0 and 50.0")
        try:
            fbarx_link.link.set_tension(round(val, 1), remember=True)
        except Exception:
            fbarx_link.link.want_tension = round(val, 1)
        c.execute("UPDATE machine_state SET stn1_stension=?, updated_at=? WHERE id=1", (round(val, 1), now()))
        return {"ok": True}

    elif action == "set_unit":
        unit = str(d.get("unit", "")).upper()
        if unit not in ("KG", "N"):
            raise ValueError("Unit must be KG or N")
        c.execute("UPDATE machine_state SET stn1_unit=?, updated_at=? WHERE id=1", (unit, now()))
        return {"ok": True}

    elif action == "set_brake_type":
        station = d.get("station")
        btype = str(d.get("type", "")).lower()
        if station not in ("stn1", "stn2"):
            raise ValueError("Invalid station")
        if btype not in ("magnetic", "pneumatic"):
            raise ValueError("Brake type must be magnetic or pneumatic")
        col = "stn1_brake_type" if station == "stn1" else "stn2_brake_type"
        c.execute(f"UPDATE machine_state SET {col}=?, updated_at=? WHERE id=1", (btype, now()))
        return {"ok": True}

    elif action == "set_parameter":
        target = d.get("target")
        raw_val = d.get("value")
        if not target or raw_val is None:
            raise ValueError("Target and value required")

        if target in ("repeat_length", "repeatLength", "repeatLengthSet"):
            val_float = float(raw_val)
            # Accepts 100-2000 mm; refuses 99 and 2001 (M5)
            if val_float < 100 or val_float > 2000:
                raise ValueError("Repeat Length must be between 100 and 2000 mm")
            val = int(round(val_float))
            fbarx_link.link.set_repeat_length(val, remember=True)
            c.execute("UPDATE machine_state SET stn2_repeat_length_set=?, updated_at=? WHERE id=1", (val, now()))
        elif target in ("mark_window", "markWindow"):
            val = float(raw_val)
            if val < 10 or val > 99: raise ValueError("Mark Window must be between 10 and 99 mm")
            fbarx_link.link.set_mark_window(int(round(val)), remember=True)
            c.execute("UPDATE machine_state SET stn2_mark_window=?, updated_at=? WHERE id=1", (int(round(val)), now()))
        elif target in ("stension", "sTensionTarget", "stensionTarget"):
            val = float(raw_val)
            if val < 0.0 or val > 50.0: raise ValueError("S-Tension must be between 0.0 and 50.0")
            try:
                fbarx_link.link.set_tension(round(val, 1), remember=True)
            except Exception:
                fbarx_link.link.want_tension = round(val, 1)
            c.execute("UPDATE machine_state SET stn1_stension=?, updated_at=? WHERE id=1", (round(val, 1), now()))
        elif target in ("outputPct", "output"):
            stn = d.get("station", "stn1")
            val = float(raw_val)
            if val < 0.0 or val > 100.0: raise ValueError("Output % must be between 0.0 and 100.0")
            val = round(val, 1)
            amp_val = round((val / 100.0) * 3.27, 2)
            if stn == "stn1":
                c.execute("UPDATE machine_state SET stn1_output_pct=?, stn1_ammeter=?, updated_at=? WHERE id=1", (val, amp_val, now()))
            else:
                fbarx_link.link.set_output(val)
                c.execute("UPDATE machine_state SET stn2_output_pct=?, stn2_ammeter=?, updated_at=? WHERE id=1", (val, amp_val, now()))
        elif target == "encoderPprSet":
            val = int(raw_val)
            if val < 100 or val > 9999: raise ValueError("Encoder PPR Set must be between 100 and 9999")
            fbarx_link.link.write_cal_numeric("encoderPprSet", val)
            c.execute("INSERT OR REPLACE INTO calibration_store(category, key, value, updated_at) VALUES('stn2', 'encoderPprSet', ?, ?)", (str(val), now()))
        elif target == "cylinderCircumference":
            val = int(raw_val)
            if val < 50 or val > 9999: raise ValueError("Cylinder Circumference must be between 50 and 9999 mm")
            fbarx_link.link.write_cal_numeric("cylinderCircumference", val)
            c.execute("INSERT OR REPLACE INTO calibration_store(category, key, value, updated_at) VALUES('stn2', 'cylinderCircumference', ?, ?)", (str(val), now()))
        elif target == "brakeCurrentCal":
            val = int(raw_val)
            if val < 1000 or val > 30000: raise ValueError("Brake Current Cal must be between 1000 and 30000 mA")
            fbarx_link.link.write_cal_numeric("brakeCurrentCal", val)
            c.execute("INSERT OR REPLACE INTO calibration_store(category, key, value, updated_at) VALUES('stn2', 'brakeCurrentCal', ?, ?)", (str(val), now()))
        else:
            fbarx_link.link.write_cal_numeric(target, float(raw_val))
            c.execute("INSERT OR REPLACE INTO calibration_store(category, key, value, updated_at) VALUES('stn2', ?, ?, ?)", (target, str(raw_val), now()))
        return {"ok": True}

    elif action == "start_job":
        rid = d.get("recipe_id")
        op = (d.get("operator") or "").strip()
        rec = None
        if rid: rec = one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (rid,))
        if not rec and d.get("recipe_name"): rec = one(c, SQL_RECIPES + " WHERE LOWER(r.name)=LOWER(?)", (d.get("recipe_name"),))
        if not rec: raise ValueError("Select a recipe to start job")
        if not op: raise ValueError("Select an operator to start job")

        fbarx_link.link.send_cmd("NEW JOB")
        t_start = now()
        c.execute("""UPDATE machine_state SET job_active=1, job_recipe_id=?, job_recipe_name=?, job_operator=?,
                     job_start_time=?, job_end_time=NULL, cnt_0_7=0, cnt_8_15=0, cnt_16_25=0, cnt_26_w=0,
                     cnt_unscored=0, cnt_total=0, updated_at=? WHERE id=1""",
                  (rec["recipe_id"], rec["name"], op, t_start, t_start))
        oid = upsert_operator(c, op)
        c.execute("UPDATE active_state SET recipe_id=?, operator_id=?, loaded_at=? WHERE id=1", (rec["recipe_id"], oid, t_start))
        log_event(c, "JOB_STARTED", f"recipe={rec['name']}", op, rec["name"])
        return {"ok": True}

    elif action == "end_job":
        row = one(c, "SELECT * FROM machine_state WHERE id=1")
        if not row or not row.get("job_active"): return {"ok": True, "note": "No job active"}
        t_end = now()
        fb_snap = fbarx_link.link.state()
        cnt = fb_snap.get("counters", {})
        c.execute("""INSERT INTO production_records(recipe_id, image_name, operator_id, operator,
                     c_0_7, c_8_15, c_16_25, c_26_w, unscored, window_mm, total, start_time, end_time, logged_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (row.get("job_recipe_id"), row.get("job_recipe_name"),
                   upsert_operator(c, row.get("job_operator")), row.get("job_operator"),
                   cnt.get("0-7", 0), cnt.get("8-15", 0), cnt.get("16-25", 0), cnt.get("26-window", 0),
                   cnt.get("unscored", 0), fb_snap.get("markWindow", 40), cnt.get("total", 0),
                   row.get("job_start_time"), t_end, t_end))
        c.execute("UPDATE machine_state SET job_active=0, job_end_time=?, updated_at=? WHERE id=1", (t_end, t_end))
        log_event(c, "JOB_ENDED", f"total={cnt.get('total', 0)}", row.get("job_operator"), row.get("job_recipe_name"))
        return {"ok": True}

    elif action == "load_recipe":
        rid = d.get("id") or d.get("recipe_id")
        rec = None
        if rid: rec = one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (rid,))
        if not rec and d.get("name"): rec = one(c, SQL_RECIPES + " WHERE LOWER(r.name)=LOWER(?)", (d.get("name"),))
        if not rec: raise ValueError("Recipe not found")

        op = (d.get("operator") or "").strip()
        oid = upsert_operator(c, op) if op else None
        ui = to_ui(rec)
        if op: ui["operator"] = op
        fbarx_link.link.apply_recipe(ui)
        c.execute("UPDATE active_state SET recipe_id=?, operator_id=COALESCE(?, operator_id), loaded_at=? WHERE id=1",
                  (rec["recipe_id"], oid, now()))
        c.execute("UPDATE machine_state SET job_recipe_id=?, job_recipe_name=?, updated_at=? WHERE id=1",
                  (rec["recipe_id"], rec["name"], now()))
        log_event(c, "RECIPE_LOADED", f"name={rec['name']}", op, rec["name"])
        return {"ok": True, "recipe": ui}

    elif action == "delete_recipe":
        rid = d.get("id") or d.get("recipe_id")
        if not rid: raise ValueError("Recipe ID required")
        rec = one(c, "SELECT recipe_id, name FROM recipes WHERE recipe_id=?", (rid,))
        if not rec: return {"ok": True, "deleted": False, "note": "Recipe not found"}
        c.execute("DELETE FROM recipe_images WHERE recipe_id=?", (rid,))
        c.execute("DELETE FROM recipes WHERE recipe_id=?", (rid,))
        c.execute("UPDATE active_state SET recipe_id=NULL WHERE recipe_id=?", (rid,))
        c.execute("UPDATE machine_state SET job_recipe_id=NULL, job_recipe_name=NULL WHERE job_recipe_id=?", (rid,))
        clear_candidates_cache()
        log_event(c, "RECIPE_DELETED", f"id={rid}", None, rec["name"])
        return {"ok": True, "recipe_id": rid, "deleted": True}

    elif action == "camera_start":
        camera.start()
        return {"ok": True}

    elif action == "camera_stop":
        camera.stop()
        reset_closed_loop()
        return {"ok": True}

    elif action == "scan":
        fbarx_link.link.send_cmd("SCAN")
        return {"ok": True}

    elif action == "stop":
        camera.stop()
        reset_closed_loop()
        return {"ok": True}

    raise ValueError(f"Unknown action: {action}")

def handle_report_get(qs):
    c = conn()
    try:
        sql, a = """SELECT record_id, logged_at AS dateTime, image_name AS imageName,
                           operator_id, operator, c_0_7 AS c0_7, c_8_15 AS c8_15,
                           c_16_25 AS c16_25, c_26_w AS c26_w, unscored, window_mm AS windowMm,
                           total, start_time AS startTime, end_time AS endTime
                    FROM production_records WHERE 1=1""", []
        if qs.get("start"): sql += " AND logged_at>=?"; a.append(qs["start"][0])
        if qs.get("end"): sql += " AND logged_at<=?"; a.append(qs["end"][0])
        if qs.get("recipe"): sql += " AND LOWER(image_name)=LOWER(?)"; a.append(qs["recipe"][0])
        if qs.get("operator"): sql += " AND LOWER(operator)=LOWER(?)"; a.append(qs["operator"][0])

        rec_list = rows(c, sql + " ORDER BY logged_at DESC LIMIT 5000", a)
        tot_bags = sum(r.get("total", 0) for r in rec_list)
        tot_0_7 = sum(r.get("c0_7", 0) for r in rec_list)
        tot_8_15 = sum(r.get("c8_15", 0) for r in rec_list)
        tot_16_25 = sum(r.get("c16_25", 0) for r in rec_list)
        tot_26_w = sum(r.get("c26_w", 0) for r in rec_list)
        tot_unsc = sum(r.get("unscored", 0) for r in rec_list)

        # Scored bags: only bags that had registration marks evaluated against tolerance
        # Unscored bags (no-read / blank film) are tracked separately and not counted as tolerance failures
        tot_failed = tot_8_15 + tot_16_25 + tot_26_w
        tot_scored = tot_0_7 + tot_failed

        pass_pct = round((tot_0_7 / tot_scored) * 100.0, 1) if tot_scored > 0 else 100.0
        fail_pct = round((tot_failed / tot_scored) * 100.0, 1) if tot_scored > 0 else 0.0
        unscored_pct = round((tot_unsc / tot_bags) * 100.0, 1) if tot_bags > 0 else 0.0

        return {
            "ok": True,
            "records": rec_list,
            "summary": {
                "total_records": len(rec_list),
                "total_bags": tot_bags,
                "total_scored": tot_scored,
                "c0_7": tot_0_7,
                "c8_15": tot_8_15,
                "c16_25": tot_16_25,
                "c26_w": tot_26_w,
                "unscored": tot_unsc,
                "pass_pct": pass_pct,
                "fail_pct": fail_pct,
                "unscored_pct": unscored_pct
            }
        }
    finally:
        c.close()

def handle_calibration_get():
    c = conn()
    try:
        cal_rows = rows(c, "SELECT category, key, value FROM calibration_store")
        grouped = {"stn1_control": {}, "stn1_loadcell": {}, "stn2": {}}
        for r in cal_rows:
            cat = r["category"]
            if cat not in grouped: grouped[cat] = {}
            grouped[cat][r["key"]] = r["value"]
        camera_cal = load_camera_calibration_from_db(c)
        grouped["camera"] = camera_cal
        if hasattr(fbarx_link.link, "read_calibration"):
            fb_cal = fbarx_link.link.read_calibration()
            grouped["stn2"].update(fb_cal)
        return {"ok": True, "calibration": grouped}
    finally:
        c.close()

def handle_calibration_post(d, client_ip="127.0.0.1", token=None):
    cat = d.get("category", "stn2")
    data = d.get("data") or d
    tok = token or d.get("token") or (data.get("token") if isinstance(data, dict) else None)

    # Protected endpoint: requires valid calibration session token
    if not fbarx_api.verify_cal_token(tok):
        return 403, {"ok": False, "error": "Calibration token required or expired", "field": "password"}

    # Validation per category
    if cat == "stn1_control":
        for k, v in data.items():
            if k in ("category", "data", "token"): continue
            if k == "acErr":
                try: val = float(v)
                except (TypeError, ValueError): raise FieldError("acErr", "acErr must be numeric")
                if val < 0.01 or val > 9.99:
                    raise FieldError("acErr", f"acErr {val} out of range (0.01 - 9.99%)")
            elif k == "dcErr":
                try: val = float(v)
                except (TypeError, ValueError): raise FieldError("dcErr", "dcErr must be numeric")
                if val < 0 or val > 999:
                    raise FieldError("dcErr", f"dcErr {val} out of range (0 - 999)")
            elif k == "displayDamp":
                try: val = float(v)
                except (TypeError, ValueError): raise FieldError("displayDamp", "displayDamp must be numeric")
                if val < 1 or val > 99:
                    raise FieldError("displayDamp", f"displayDamp {val} out of range (1 - 99)")
            elif k == "brakePower":
                try: val = float(v)
                except (TypeError, ValueError): raise FieldError("brakePower", "brakePower must be numeric")
                if val < 0 or val > 100:
                    raise FieldError("brakePower", f"brakePower {val} out of range (0 - 100%)")
            elif k == "brakeType":
                if str(v) not in ("Pneumatic", "Powder Brake", "Powder"):
                    raise FieldError("brakeType", "brakeType must be Pneumatic or Powder Brake")

    elif cat == "stn1_loadcell":
        for k, v in data.items():
            if k in ("category", "data", "token"): continue
            if k == "loadcellCapacity":
                try: val = float(v)
                except (TypeError, ValueError): raise FieldError("loadcellCapacity", "loadcellCapacity must be numeric")
                if val < 1 or val > 999:
                    raise FieldError("loadcellCapacity", f"loadcellCapacity {val} out of range (1 - 999)")
            elif k == "knownWeight":
                try: val = float(v)
                except (TypeError, ValueError): raise FieldError("knownWeight", "knownWeight must be numeric")
                if val < 0 or val > 999:
                    raise FieldError("knownWeight", f"knownWeight {val} out of range (0 - 999 kg)")

    elif cat == "stn2":
        # Validate and write through fbarx_link; propagates FieldError and BoardError
        fbarx_link.link.set_calibration(data)

    with WLOCK:
        c = conn()
        try:
            for k, v in data.items():
                if k in ("category", "data", "token"): continue
                c.execute("INSERT OR REPLACE INTO calibration_store(category, key, value, updated_at) VALUES(?,?,?,?)",
                          (cat, k, str(v), now()))
            c.commit()
            log_audit(f"calibration_{cat}", "batch", json.dumps(data), client_ip=client_ip)
            return 200, {"ok": True, "calibration": handle_calibration_get()["calibration"]}
        finally:
            c.close()

def handle_camera_match(qs, raw_bytes, d):
    t_start = time.time()
    c = conn()
    try: cands = get_all_candidates(c)
    finally: c.close()

    jpg = None
    if raw_bytes and len(raw_bytes) > 100:
        jpg = raw_bytes
    elif d and d.get("dataUrl"):
        _, jpg = decode_data_url(d["dataUrl"])
    elif d and d.get("imageData"):
        _, jpg = decode_data_url(d["imageData"])

    if not jpg:
        try: jpg = camera.still_jpeg()
        except Exception: pass
    if not jpg:
        jpg = get_sim_frame("0mm")

    res = vision.compare(jpg, cands, selected_id=0, min_inliers=6, include_front_back=True)
    matched = (res.get("result") == "MATCH")
    rec_id = res.get("best_recipe_id")
    rec_name = res.get("best")
    score = float(res.get("confidence", 0.0))

    return {
        "ok": True,
        "matched": matched,
        "recipe_id": rec_id,
        "name": rec_name,
        "score": score,
        "result": res.get("result", "NO_READ"),
        "inliers": res.get("inliers", 0),
        "latency_ms": round((time.time() - t_start) * 1000, 1)
    }

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _cors_origin(self):
        hdrs = getattr(self, "headers", None)
        if not hdrs:
            return None
        origin = hdrs.get("Origin")
        if not origin:
            return None
        host = hdrs.get("Host", "").split(":")[0]
        if "localhost" in origin or "127.0.0.1" in origin or (host and host in origin):
            return origin
        return None

    def _check_basic_auth(self):
        hdrs = getattr(self, "headers", None)
        auth_hdr = hdrs.get("Authorization") if hdrs else None
        if not fbarx_api.basic_auth_ok(auth_hdr):
            return False
        proto = hdrs.get("X-Forwarded-Proto") if hdrs else None
        srv = getattr(self, "server", None)
        is_tls = getattr(srv, "is_tls", False) or (proto == "https")
        client_host = self.client_address[0] if hasattr(self, "client_address") else "127.0.0.1"
        if not is_tls and client_host not in ("127.0.0.1", "::1", "localhost"):
            print(f"[SECURITY WARNING] Basic Auth credentials received over unencrypted HTTP from {client_host}. Use TLS (--cert/--key) or Nginx reverse proxy in production.")
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cal-Token, X-Auth-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Connection", "close")
        self.end_headers()

    def _send(self, code, body, ctype="application/json", extra=None, cache_control="no-store, no-cache, must-revalidate, max-age=0"):
        try:
            if not isinstance(body, (bytes, bytearray)): body = json.dumps(body, default=str).encode()
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            if "no-store" in cache_control:
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            self.send_header("Permissions-Policy", "camera=(self)")
            self.send_header("Connection", "close")
            origin = self._cors_origin()
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cal-Token, X-Auth-Token")
                self.send_header("Vary", "Origin")
            for k, v in (extra or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(body)
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_UPLOAD * 2: raise ValueError("request too large")
            return self.rfile.read(n) if n else b""
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return b""
    def _json(self): return json.loads(self._body() or b"{}")

    def do_HEAD(self):
        try:
            if not self._check_basic_auth():
                return self._send(401, {"error": "login required"},
                                  extra={"WWW-Authenticate": 'Basic realm="FBAR 1000"'})
            self.send_response(200)
            self.end_headers()
        except Exception:
            pass

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path); p = u.path; qs = parse_qs(u.query)
        try:
            if not self._check_basic_auth():
                return self._send(401, {"error": "login required"},
                                  extra={"WWW-Authenticate": 'Basic realm="FBAR 1000"'})
            if p == "/api/health": return self._send(200, {"ok": True, "time": now(), "vision": vision.AVAILABLE})
            r = fbarx_api.route_get(fbarx_link.link, p)
            if r: return self._send(*r)
            if p in ("/api/fbarx/auth_status", "/api/auth_status"):
                sess = verify_token(self)
                if sess:
                    rem = sess.get("expires_in", int(SESSION_TIMEOUT_SEC - (time.time() - sess["last_active"])))
                    return self._send(200, {"authenticated": True, "operator": sess["operator"], "role": sess.get("role", "operator"), "expires_in": rem})
                return self._send(200, {"authenticated": False})
            if p == "/api/fbarx/audit_log":
                c = conn()
                try: return self._send(200, rows(c, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 100"))
                finally: c.close()
            if p == "/api/state":
                return self._send(200, get_full_state())
            if p == "/api/operators":
                c = conn()
                try: return self._send(200, rows(c, "SELECT operator_id,name,emp_code,role,photo_path FROM operators WHERE is_active=1 ORDER BY name"))
                finally: c.close()
            if p == "/api/recipes":
                c = conn()
                try: return self._send(200, [to_ui(r) for r in rows(c, SQL_RECIPES + " ORDER BY r.name")])
                finally: c.close()
            if p == "/api/report":
                return self._send(200, handle_report_get(qs))
            if p == "/api/calibration":
                return self._send(200, handle_calibration_get())
            if p == "/api/events":
                c = conn()
                try: return self._send(200, rows(c, "SELECT * FROM event_log ORDER BY event_id DESC LIMIT 200"))
                finally: c.close()
            if p == "/api/camera/calibration":
                c = conn()
                try: return self._send(200, load_camera_calibration_from_db(c))
                finally: c.close()
            if p == "/api/camera/info":
                c = conn()
                try:
                    cal = load_camera_calibration_from_db(c)
                    return self._send(200, {
                        "source": setting(c, "camera_source", "laptop"),
                        "pi": camera.info(),
                        "vision": vision.AVAILABLE,
                        "calibration": cal
                    })
                finally: c.close()
            if p == "/api/camera/sim_error":
                c = conn()
                try: return self._send(200, {"error": setting(c, "camera_sim_error", "live"), "available": ["live", "0mm", "-10mm", "+10mm"]})
                finally: c.close()
            if p == "/api/camera/sim_frame":
                err = qs.get("error", ["0mm"])[0]
                rec_name = qs.get("recipe_name", [""])[0]
                return self._send(200, get_sim_frame(err, recipe_name=rec_name), "image/jpeg")
            if p == "/api/camera/snapshot":
                if getattr(camera, "running", False):
                    try: return self._send(200, camera.still_jpeg(timeout=1.0), "image/jpeg")
                    except Exception: pass
                c = conn()
                try:
                    err = qs.get("error", [setting(c, "camera_sim_error", "live")])[0]
                    rid = int(qs.get("recipe_id", [0])[0])
                    rec = one(c, "SELECT name FROM recipes WHERE recipe_id=?", (rid,)) if rid else None
                    if not rec:
                        active_row = one(c, "SELECT r.name FROM active_state s JOIN recipes r ON s.recipe_id=r.recipe_id WHERE s.id=1")
                        if active_row: rec = active_row
                    rec_name = rec["name"] if rec else ""
                    return self._send(200, get_sim_frame(err, recipe_name=rec_name), "image/jpeg")
                finally:
                    c.close()
            if p == "/api/camera/stop":
                global STREAM_TOKEN
                STREAM_TOKEN += 1
                camera.stop()
                reset_closed_loop()
                return self._send(200, {"ok": True})
            if p in ("/api/camera/compare_front_back", "/api/camera/trigger"):
                return self._handle_compare_front_back(qs, force_trigger=(p == "/api/camera/trigger"))
            if p == "/api/camera/stream":
                c = conn()
                err = qs.get("error", [setting(c, "camera_sim_error", "live")])[0]
                rid = int(qs.get("recipe_id", [0])[0])
                rec = one(c, "SELECT name FROM recipes WHERE recipe_id=?", (rid,)) if rid else None
                if not rec:
                    active_row = one(c, "SELECT r.name FROM active_state s JOIN recipes r ON s.recipe_id=r.recipe_id WHERE s.id=1")
                    if active_row: rec = active_row
                c.close()
                rec_name = rec["name"] if rec else ""
                return self._stream(err, recipe_name=rec_name)
            # static files
            rel = "static/index.html" if p in ("/", "") else p.lstrip("/")
            f = (HERE / rel).resolve()
            if not f.is_file() and (HERE / "static" / rel).is_file():
                f = (HERE / "static" / rel).resolve()
            if HERE in f.parents and f.is_file() and ((HERE / "static") in f.parents or f.parent.name in ("static", "images", "captures")) and f.suffix != ".db":
                content = f.read_bytes()
                etag = f'"{hashlib.md5(content).hexdigest()}"'
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    return
                return self._send(200, content, mimetypes.guess_type(f.name)[0] or "application/octet-stream",
                                  extra={"ETag": etag}, cache_control="no-cache")
            self._send(404, {"error": "not found"})
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
        except Exception as e:
            try: self._send(500, {"error": str(e)})
            except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass

    def _stream(self, err="0mm", recipe_name=""):
        global STREAM_TOKEN
        my_token = STREAM_TOKEN
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Connection", "close")
        self.end_headers()
        # Immediately write first frame so connection starts streaming without delay
        try:
            init_jpg = get_sim_frame(err, recipe_name=recipe_name)
            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(init_jpg) + init_jpg + b"\r\n")
            self.wfile.flush()
        except Exception:
            self.close_connection = True
            return

        # Start camera asynchronously if not running so device probe doesn't block HTTP delivery
        if err == "live" and not getattr(camera, "running", False):
            def _async_start():
                try: camera.start(force=True)
                except Exception: pass
            threading.Thread(target=_async_start, daemon=True).start()

        last = -1
        try:
            while my_token == STREAM_TOKEN:
                if err != "live" or not getattr(camera, "running", False):
                    jpg = get_sim_frame(err, recipe_name=recipe_name)
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                    self.wfile.flush()
                    time.sleep(0.08)
                    continue
                jpg, last_new = camera.preview_if_new(last, 1.0)
                if jpg is None:
                    time.sleep(0.04)
                    continue
                last = last_new
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                self.wfile.flush()
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception:
            pass
        self.close_connection = True

    # ---- POST ----
    def do_POST(self):
        u = urlparse(self.path); p = u.path; qs = parse_qs(u.query)
        try:
            self.raw = self._body()                       # always consume the body (HTTP/1.1 keep-alive)
            if not fbarx_api.basic_auth_ok(self.headers.get("Authorization")):
                return self._send(401, {"error": "login required"},
                                  extra={"WWW-Authenticate": 'Basic realm="FBAR 1000"'})
            if p in ("/api/camera/compare_front_back", "/api/camera/trigger"):
                return self._handle_compare_front_back(qs, body_bytes=self.raw, force_trigger=(p == "/api/camera/trigger"))
            if p in ("/api/camera/zero", "/api/camera/calibrate_zero"):
                return self._handle_zero(qs)
            if p == "/api/camera/compare": return self._compare(qs)
            if p == "/api/camera/stop":
                global STREAM_TOKEN
                STREAM_TOKEN += 1
                camera.stop()
                reset_closed_loop()
                return self._send(200, {"ok": True})
            d = json.loads(self.raw or b"{}")
            if p == "/api/action":
                with WLOCK:
                    c = conn()
                    try:
                        out = handle_action(c, d, self.client_address[0])
                        c.commit()
                        state = get_full_state()
                        out["state"] = state
                        return self._send(200, out)
                    except ValueError as e:
                        c.rollback()
                        return self._send(400, {"ok": False, "error": str(e)})
                    except Exception as e:
                        c.rollback()
                        return self._send(500, {"ok": False, "error": str(e)})
                    finally:
                        c.close()

            if p == "/api/login":
                return self._send(404, {"error": "Endpoint removed. Use POST /api/fbarx/unlock with role-based passcode."})

            if p in ("/api/unlock", "/api/fbarx/unlock"):
                code, res = fbarx_api.route_post(fbarx_link.link, "/api/fbarx/unlock", d, self.headers)
                return self._send(code, res)

            if p == "/api/calibration":
                tok = self.headers.get("X-Cal-Token") or (self.headers.get("Authorization", "").replace("Bearer ", "") if "Bearer" in self.headers.get("Authorization", "") else None)
                if not tok and isinstance(d, dict):
                    tok = d.get("token") or (d.get("data", {}).get("token") if isinstance(d.get("data"), dict) else None)
                try:
                    res_status, res_body = handle_calibration_post(d, self.client_address[0], token=tok)
                    return self._send(res_status, res_body)
                except FieldError as e:
                    return self._send(400, {"error": str(e), "field": e.field})
                except BoardError as e:
                    return self._send(503, {"error": str(e)})

            if p == "/api/camera/match":
                res = handle_camera_match(qs, self.raw, d)
                return self._send(200, res)
            if p == "/api/camera/calibration":
                with WLOCK:
                    c = conn()
                    try:
                        for k, v in d.items():
                            if k in vision.DEFAULT_CALIBRATION:
                                val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                                c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES(?,?,?)", (k, val_str, now()))
                        c.commit()
                        cal = load_camera_calibration_from_db(c)
                        log_audit("camera_calibration", "settings", json.dumps(cal), client_ip=self.client_address[0])
                        return self._send(200, {"ok": True, "calibration": cal})
                    finally: c.close()
            if p == "/api/camera/calibrate_ruler":
                known_mm = float(d.get("known_mm", 0.0))
                dist_px = float(d.get("distance_px", 0.0))
                if dist_px == 0.0 and "p1_px" in d and "p2_px" in d:
                    dist_px = abs(float(d["p2_px"]) - float(d["p1_px"]))
                if known_mm <= 0.0 or dist_px <= 0.0:
                    return self._send(400, {"error": "valid known_mm and distance_px required"})
                scale = vision.calculate_ruler_scale(dist_px, known_mm)
                with WLOCK:
                    c = conn()
                    try:
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm',?,?)", (str(scale), now()))
                        c.commit()
                        cal = load_camera_calibration_from_db(c)
                        log_audit("scale_px_per_mm", "ruler_cal", str(scale), client_ip=self.client_address[0])
                        return self._send(200, {"ok": True, "scale_px_per_mm": scale, "calibration": cal})
                    finally: c.close()
            if p == "/api/camera/calibrate_distance":
                wd = float(d.get("working_distance_m", 1.5))
                hfov = float(d.get("hfov_deg", 62.2))
                scale = vision.calculate_scale_from_distance(wd, hfov_deg=hfov, img_w=1600)
                with WLOCK:
                    c = conn()
                    try:
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('working_distance_m',?,?)", (str(wd), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm',?,?)", (str(scale), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm_x',?,?)", (str(scale), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm_y',?,?)", (str(scale), now()))
                        c.commit()
                        cal = load_camera_calibration_from_db(c)
                        log_audit("working_distance_m", "distance_cal", f"{wd}m -> {scale}px/mm", client_ip=self.client_address[0])
                        return self._send(200, {"ok": True, "working_distance_m": wd, "scale_px_per_mm": scale, "calibration": cal})
                    finally: c.close()
            if p == "/api/camera/calibrate_bag_width":
                w_px = float(d.get("bag_width_px", 0.0))
                known_w_mm = float(d.get("known_width_mm", 535.0))
                if w_px <= 0.0 or known_w_mm <= 0.0:
                    return self._send(400, {"error": "valid bag_width_px and known_width_mm required"})
                scale = vision.calculate_scale_from_bag_width(w_px, known_width_mm=known_w_mm)
                with WLOCK:
                    c = conn()
                    try:
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('bag_width_mm',?,?)", (str(known_w_mm), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm',?,?)", (str(scale), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm_x',?,?)", (str(scale), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm_y',?,?)", (str(scale), now()))
                        c.commit()
                        cal = load_camera_calibration_from_db(c)
                        log_audit("bag_width_mm", "width_cal", f"{w_px}px / {known_w_mm}mm -> {scale}px/mm", client_ip=self.client_address[0])
                        return self._send(200, {"ok": True, "bag_width_px": w_px, "known_width_mm": known_w_mm, "scale_px_per_mm": scale, "calibration": cal})
                    finally: c.close()
            if p == "/api/camera/calibrate_bag_length":
                l_px = float(d.get("bag_length_px", 0.0))
                known_l_mm = float(d.get("known_length_mm", 1860.0))
                if l_px <= 0.0 or known_l_mm <= 0.0:
                    return self._send(400, {"error": "valid bag_length_px and known_length_mm required"})
                scale = vision.calculate_scale_from_bag_length(l_px, known_length_mm=known_l_mm)
                with WLOCK:
                    c = conn()
                    try:
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('bag_length_mm',?,?)", (str(known_l_mm), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('nominal_length_mm',?,?)", (str(known_l_mm), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm',?,?)", (str(scale), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm_x',?,?)", (str(scale), now()))
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('scale_px_per_mm_y',?,?)", (str(scale), now()))
                        c.commit()
                        cal = load_camera_calibration_from_db(c)
                        log_audit("bag_length_mm", "length_cal", f"{l_px}px / {known_l_mm}mm -> {scale}px/mm", client_ip=self.client_address[0])
                        return self._send(200, {"ok": True, "bag_length_px": l_px, "known_length_mm": known_l_mm, "scale_px_per_mm": scale, "calibration": cal})
                    finally: c.close()
            if p.startswith("/api/fbarx/"):
                code, body = fbarx_api.route_post(fbarx_link.link, p, d, self.headers)
                return self._send(code, body)
            if p == "/api/camera/sim_error":
                err = d.get("error", "live")
                if err not in ("0mm", "-10mm", "+10mm", "live"): return self._send(400, {"error": "error must be 0mm, -10mm, +10mm, or live"})
                reset_closed_loop()
                if err == "0mm": fbarx_link.link.set_live_sim_error(0.0)
                elif err == "-10mm": fbarx_link.link.set_live_sim_error(-10.0)
                elif err == "+10mm": fbarx_link.link.set_live_sim_error(10.0)
                with WLOCK:
                    c = conn()
                    try:
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('camera_sim_error',?,?)", (err, now()))
                        log_event(c, "CAMERA_SIM_ERROR", err, d.get("operator"))
                        c.commit()
                    finally: c.close()
                return self._send(200, {"error": err, "ok": True})
            if p == "/api/camera/source":
                s = d.get("source")
                if s not in ("laptop", "pi"): return self._send(400, {"error": "source must be laptop or pi"})
                with WLOCK:
                    c = conn()
                    try:
                        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('camera_source',?,?)", (s, now()))
                        log_event(c, "CAMERA_SOURCE", s, d.get("operator")); c.commit()
                    finally: c.close()
                if s == "laptop": camera.stop()
                return self._send(200, {"source": s})
            with WLOCK:
                c = conn()
                try:
                    out = self._write(c, p, d); c.commit(); return self._send(200, out)
                except FieldError as e: c.rollback(); return self._send(400, {"error": str(e), "field": e.field})
                except ValueError as e: c.rollback(); return self._send(400, {"error": str(e)})
                except sqlite3.IntegrityError as e: c.rollback(); return self._send(409, {"error": "DB constraint: " + str(e)})
                finally: c.close()
        except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
        except Exception as e:
            try: self._send(500, {"error": str(e)})
            except (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass

    def _write(self, c, p, d):
        if p == "/api/operators":
            oid = upsert_operator(c, d.get("name"), d.get("photo"))
            if not oid: raise FieldError("name", "operator name required")
            log_event(c, "OPERATOR_ADDED", d["name"]); return {"operator_id": oid}

        if p == "/api/recipes":       # CALIBRATION: SAVE & EXIT
            r = d.get("recipe") or {}; name = (r.get("name") or "").strip(); op = (d.get("operator") or "").strip()
            if not name: raise FieldError("name", "recipe name required")
            if not op: raise FieldError("operator", "operator name required")
            prm = validate_recipe_params(r); oid = upsert_operator(c, op, d.get("operatorPhoto"))
            rid_arg = r.get("recipeId")
            if rid_arg:
                ex = one(c, "SELECT recipe_id, brand_tamil FROM recipes WHERE recipe_id=?", (rid_arg,))
            else:
                ex = one(c, "SELECT recipe_id, brand_tamil FROM recipes WHERE name=?", (name,))
            if ex and not prm.get("brandTamil") and ex.get("brand_tamil"):
                prm["brandTamil"] = ex["brand_tamil"]
            cols = list(RECIPE_COLS.values()); vals = [prm[k] for k in RECIPE_COLS]
            if ex:
                rid = ex["recipe_id"]
                c.execute("UPDATE recipes SET name=?, " + ",".join(f"{x}=?" for x in cols) + " WHERE recipe_id=?", [name] + vals + [rid])
            else:
                c.execute("INSERT INTO recipes(name,created_by," + ",".join(cols) + ") VALUES(?,?," + ",".join("?" * len(cols)) + ")", [name, oid] + vals)
                rid = one(c, "SELECT recipe_id FROM recipes WHERE name=?", (name,))["recipe_id"]
            img = d.get("image")
            if img and img.get("dataUrl"): save_image(c, rid, name, img.get("name"), img["dataUrl"])
            f_img = d.get("frontImage")
            if f_img and f_img.get("dataUrl"):
                mime, bdata = decode_data_url(f_img["dataUrl"])
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}.get(mime, ".jpg")
                fn = f"{slug(name)}_front_{time.strftime('%Y%m%d%H%M%S')}{ext}"
                (IMG / fn).write_bytes(bdata)
                c.execute("UPDATE recipes SET front_image_path=?, front_image_name=? WHERE recipe_id=?", (f"images/{fn}", f_img.get("name") or fn, rid))
                if not (img and img.get("dataUrl")):
                    save_image(c, rid, name, f_img.get("name") or fn, f_img["dataUrl"])
            b_img = d.get("backImage")
            if b_img and b_img.get("dataUrl"):
                mime, bdata = decode_data_url(b_img["dataUrl"])
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}.get(mime, ".jpg")
                fn = f"{slug(name)}_back_{time.strftime('%Y%m%d%H%M%S')}{ext}"
                (IMG / fn).write_bytes(bdata)
                c.execute("UPDATE recipes SET back_image_path=?, back_image_name=? WHERE recipe_id=?", (f"images/{fn}", b_img.get("name") or fn, rid))
            clear_candidates_cache()
            log_event(c, "RECIPE_SAVED", ("updated" if ex else "created") + (" +image" if (img or f_img or b_img) else ""), op, name)
            return {"recipe": to_ui(one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (rid,)))}

        if p == "/api/recipes/delete":  # CALIBRATION: DELETE RECIPE
            rid = d.get("recipe_id")
            name = (d.get("name") or "").strip()
            op = (d.get("operator") or "").strip()
            if not rid and not name: raise ValueError("recipe_id or name required")
            rec = None
            if rid:
                rec = one(c, "SELECT recipe_id, name FROM recipes WHERE recipe_id=?", (rid,))
            if not rec and name:
                rec = one(c, "SELECT recipe_id, name FROM recipes WHERE LOWER(name)=LOWER(?)", (name,))
            if not rec:
                return {"ok": True, "recipe_id": rid, "name": name, "deleted": False, "note": "not found in sqlite"}
            rid = rec["recipe_id"]; rname = rec["name"]
            c.execute("DELETE FROM recipe_images WHERE recipe_id=?", (rid,))
            c.execute("DELETE FROM recipes WHERE recipe_id=?", (rid,))
            c.execute("UPDATE active_state SET recipe_id=NULL WHERE recipe_id=?", (rid,))
            log_event(c, "RECIPE_DELETED", f"id={rid}", op, rname)
            clear_candidates_cache()
            return {"ok": True, "recipe_id": rid, "name": rname}

        if p == "/api/load":          # RECIPE LOAD: CONFIRM TO LOAD
            rec = one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (d.get("recipe_id"),))
            if not rec: raise ValueError("recipe not found")
            op = (d.get("operator") or "").strip()
            if not op: raise ValueError("select an operator")
            src = d.get("source", "NAME")
            if src not in ("NAME", "IMAGE", "CAMERA"): raise ValueError("bad source")
            oid = upsert_operator(c, op); ui = to_ui(rec); ui["operator"] = op
            c.execute("""INSERT INTO recipe_loads(recipe_id,recipe_name,operator_id,operator,load_source,image_id,verify_id,params_json)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (rec["recipe_id"], rec["name"], oid, op, src, rec.get("image_id"), d.get("verify_id"), json.dumps(ui)))
            c.execute("UPDATE active_state SET recipe_id=?, operator_id=?, loaded_at=? WHERE id=1", (rec["recipe_id"], oid, now()))
            log_event(c, "RECIPE_LOADED", "via " + src, op, rec["name"])
            board = fbarx_link.link.apply_recipe(ui)      # never raises: {"ok": bool, "errors": {...}}
            return {"recipe": ui, "operator": op, "board": board}

        if p == "/api/production":    # counters delta -> production_records (uses ACTIVE recipe/operator)
            a = one(c, "SELECT * FROM active_state WHERE id=1") or {}
            rec = one(c, "SELECT name FROM recipes WHERE recipe_id=?", (a.get("recipe_id"),)) if a.get("recipe_id") else None
            op = one(c, "SELECT name FROM operators WHERE operator_id=?", (a.get("operator_id"),)) if a.get("operator_id") else None
            n = [max(0, int(d.get(k, 0))) for k in ("c0_7", "c8_15", "c16_25")]
            c26 = max(0, int(d.get("c26_w", 0))); uns = max(0, int(d.get("unscored", 0)))
            tot = max(0, int(d.get("total", sum(n) + c26 + uns)))
            if not tot and not sum(n) and not c26 and not d.get("force"): return {"skipped": True}
            c.execute("""INSERT INTO production_records(recipe_id,image_name,operator_id,operator,c_0_7,c_8_15,c_16_25,c_26_w,unscored,window_mm,total,start_time,end_time,logged_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (a.get("recipe_id"), d.get("recipe") or (rec and rec["name"]), a.get("operator_id"), d.get("operator") or (op and op["name"]),
                       *n, c26, uns, d.get("window_mm"), tot, d.get("start_time"), d.get("end_time"), d.get("logged_at") or now()))
            return {"ok": True}

        if p == "/api/event":
            log_event(c, str(d.get("event", ""))[:60], str(d.get("detail", ""))[:300], d.get("operator"), d.get("recipe")); return {"ok": True}
        raise ValueError("unknown endpoint")

    def _handle_compare_front_back(self, qs, body_bytes=None, force_trigger=False):
        global GLOBAL_BAG_ID
        t_start = time.time()
        rid = int(qs.get("recipe_id", [0])[0])
        mode = qs.get("mode", ["AUTO"])[0].upper()
        if qs.get("reset_closed_loop"):
            reset_closed_loop()
        c = conn()
        cal = load_camera_calibration_from_db(c)
        err = qs.get("error", [setting(c, "camera_sim_error", "live")])[0]
        zero_cal = setting(c, "zero_offset_mm", None)
        if zero_cal is None:
            zero_cal = setting(c, "zero_px", None)
        rec = one(c, "SELECT name, repeat_length_mm, mark_offset_mm FROM recipes WHERE recipe_id=?", (rid,)) if rid else None
        if not rec:
            active_row = one(c, "SELECT r.name, r.repeat_length_mm, r.mark_offset_mm FROM active_state s JOIN recipes r ON s.recipe_id=r.recipe_id WHERE s.id=1")
            if active_row: rec = active_row
        c.close()
        rec_name = rec["name"] if rec else ""
        rep_len = float(rec.get("repeat_length_mm") or cal.get("bag_length_mm", 1860.0)) if rec else float(cal.get("bag_length_mm", 1860.0))
        nom_mm = float(rec.get("mark_offset_mm") or cal.get("nominal_mm") or 0.0) if rec else cal.get("nominal_mm", 0.0)

        jpg = body_bytes if (body_bytes and len(body_bytes) > 100) else None
        if not jpg and err == "live":
            try: jpg = camera.still_jpeg()
            except Exception: pass
        if not jpg:
            jpg = get_sim_frame(err, recipe_name=rec_name)

        # Trigger & Bag ID determination (error.md Section 10 & 13.1)
        is_trigger = force_trigger or (qs.get("trigger", ["0"])[0].lower() in ("1", "true", "yes"))
        bag_id_param = qs.get("bag_id", [None])[0]
        if bag_id_param is not None:
            try:
                bag_id = int(bag_id_param)
                GLOBAL_BAG_ID = max(GLOBAL_BAG_ID, bag_id)
            except ValueError:
                GLOBAL_BAG_ID += 1
                bag_id = GLOBAL_BAG_ID
        elif is_trigger:
            GLOBAL_BAG_ID += 1
            bag_id = GLOBAL_BAG_ID
        else:
            bag_id = None

        cal_zero = float(zero_cal) if zero_cal is not None else cal.get("zero_offset_mm", 0.0)
        res = vision.compare_front_back(
            jpg,
            selected_id=rid,
            sim_error=err,
            custom_zero_mm=cal_zero,
            calibration=cal,
            repeat_length_mm=rep_len,
            nominal_mm=nom_mm
        )

        # If simulated closed loop on +10mm in AUTO: apply actuator position to residual (Section 11 & 15)
        is_sim_plus = ("plus" in str(err).lower() or "+10" in str(err) or str(err) in ("10mm", "+10"))
        if is_sim_plus and mode == "AUTO" and SIM_ACTUATOR_CORR_MM != 0.0:
            raw_err = 9.4
            net_err = round(raw_err + SIM_ACTUATOR_CORR_MM, 1)
            res["error_mm"] = net_err
            res["offset_y_mm"] = net_err
            res["reg_err_mm"] = round(abs(net_err), 1)
            reg_err = res["reg_err_mm"]
            res["bin"] = "0-7" if reg_err <= 7.0 else ("8-15" if reg_err <= 15.0 else ("16-25" if reg_err <= 25.0 else "over"))
            res["status"] = "IN SPEC" if reg_err <= 7.0 else "OUT OF SPEC"
            res["result"] = "PASS" if reg_err <= 7.0 else "FAIL"

        if res.get("ok"):
            err_m = res.get("error_mm", 0.0)
            fbarx_link.link.set_live_sim_error(err_m, valid=True)
            if is_trigger:
                fbarx_link.link.record_bag_error(err_m)
            res["corr_mm"] = update_closed_loop_correction(err_m, is_auto=(mode == "AUTO"), is_sim=(err != "live"))
        else:
            fbarx_link.link.set_live_sim_error(0.0, valid=False)
            res["corr_mm"] = round(CLOSED_LOOP_CORR_MM, 1)

        t_end = time.time()
        latency_ms = max(1, int(round((t_end - t_start) * 1000)))
        res["latency_ms"] = latency_ms
        if bag_id is not None:
            res["bag_id"] = bag_id

        return self._send(200, res)

    def _handle_zero(self, qs):
        c = conn()
        if qs.get("action", [""])[0] == "reset":
            c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('zero_offset_mm','0.0',?)", (now(),))
            c.execute("DELETE FROM settings WHERE key='zero_px'")
            c.commit()
            c.close()
            vision.set_zero_calibration(0.0)
            reset_closed_loop()
            return self._send(200, {"ok": True, "zero_offset_mm": 0.0, "zero_px": 0.0, "reset": True})

        cal = load_camera_calibration_from_db(c)
        err = qs.get("error", [setting(c, "camera_sim_error", "live")])[0]
        rid = int(qs.get("recipe_id", [0])[0])
        rec = one(c, "SELECT name, repeat_length_mm, mark_offset_mm FROM recipes WHERE recipe_id=?", (rid,)) if rid else None
        if not rec:
            active_row = one(c, "SELECT r.name, r.repeat_length_mm, r.mark_offset_mm FROM active_state s JOIN recipes r ON s.recipe_id=r.recipe_id WHERE s.id=1")
            if active_row: rec = active_row
        rec_name = rec["name"] if rec else ""
        rep_len = float(rec.get("repeat_length_mm") or cal.get("bag_length_mm", 1860.0)) if rec else float(cal.get("bag_length_mm", 1860.0))
        nom_mm = float(rec.get("mark_offset_mm") or cal.get("nominal_mm") or 0.0) if rec else cal.get("nominal_mm", 0.0)

        body = self.raw
        jpg = body if (body and len(body) > 100) else None
        if not jpg and err == "live":
            try: jpg = camera.still_jpeg()
            except Exception: pass
        if not jpg:
            jpg = get_sim_frame(err, recipe_name=rec_name)

        # Measure with zero_offset = 0 to get raw master bag distance
        res = vision.compare_front_back(
            jpg,
            selected_id=rid,
            sim_error=err,
            custom_zero_mm=0.0,
            calibration=cal,
            repeat_length_mm=rep_len,
            nominal_mm=nom_mm
        )

        if res.get("method") == "four_bar":
            nom_len = float(rep_len or nom_mm or cal.get("nominal_length_mm", 0.0))
            raw_len = float(res.get("length_mm", 0.0))
            zero_offset = round(raw_len - nom_len, 2) if nom_len > 0 else 0.0
            skew_top = float(res.get("raw_skew_top_mm", 0.0))
            skew_bot = float(res.get("raw_skew_bottom_mm", 0.0))
            c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('zero_offset_mm',?,?)", (str(zero_offset), now()))
            c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('nominal_skew_top_mm',?,?)", (str(skew_top), now()))
            c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('nominal_skew_bottom_mm',?,?)", (str(skew_bot), now()))
            if nom_len > 0:
                c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('nominal_length_mm',?,?)", (str(nom_len), now()))
            c.commit()
            c.close()
            vision.set_camera_calibration({
                "zero_offset_mm": zero_offset,
                "nominal_skew_top_mm": skew_top,
                "nominal_skew_bottom_mm": skew_bot,
                "nominal_length_mm": nom_len
            })
            reset_closed_loop()
            return self._send(200, {
                "ok": True,
                "method": "four_bar",
                "zero_offset_mm": zero_offset,
                "nominal_skew_top_mm": skew_top,
                "nominal_skew_bottom_mm": skew_bot,
                "length_mm": raw_len,
                "scale_px_per_mm": res.get("scale_px_per_mm", cal.get("scale_px_per_mm", 4.0)),
                "nominal_length_mm": nom_len,
                "offset_y_mm": 0.0,
                "offset_x_mm": 0.0
            })

        dist_px = float(res.get("distance_px", 0.0))
        scale = float(res.get("scale_px_per_mm", cal.get("scale_px_per_mm", 4.0)) or 4.0)
        raw_mm = dist_px / scale
        zero_offset = round(raw_mm - nom_mm, 2)

        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('zero_offset_mm',?,?)", (str(zero_offset), now()))
        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES('zero_px',?,?)", (str(dist_px), now()))
        c.commit()
        c.close()
        vision.set_camera_calibration({"zero_offset_mm": zero_offset})
        reset_closed_loop()
        return self._send(200, {
            "ok": True,
            "zero_offset_mm": zero_offset,
            "zero_px": dist_px,
            "scale_px_per_mm": scale,
            "nominal_mm": nom_mm,
            "offset_y_mm": 0.0
        })

    def _compare(self, qs):
        t_0 = time.time()
        rid = int(qs.get("recipe_id", [0])[0]); src = qs.get("source", ["laptop"])[0]
        op = qs.get("operator", [""])[0]
        body = self.raw
        jpg = body if (body and len(body) > 100) else None
        c_tmp = conn()
        err = qs.get("error", [setting(c_tmp, "camera_sim_error", "live")])[0]
        c_tmp.close()
        t_1 = time.time()
        if not jpg and err == "live":
            try:
                jpg = camera.still_jpeg()
            except Exception:
                pass
        rec_name = qs.get("recipe_name", [""])[0]
        if not jpg:
            jpg = get_sim_frame(err, recipe_name=rec_name)
        t_2 = time.time()
        with WLOCK:
            t_3 = time.time()
            c = conn()
            try:
                cands = get_all_candidates(c)
                t_4 = time.time()
                inc_fb = qs.get("include_front_back", ["1"])[0] in ("1", "true")
                res = vision.compare(jpg, cands, rid, int(setting(c, "match_min_inliers", 8)), include_front_back=inc_fb, sim_error=err)
                if "front_back" in res:
                    fb = res["front_back"]
                    res["error_mm"] = fb.get("error_mm", 0.0)
                    res["reg_err_mm"] = fb.get("reg_err_mm", 0.0)
                    res["offset_y_mm"] = fb.get("offset_y_mm", 0.0)
                    res["offset_x_mm"] = fb.get("offset_x_mm", 0.0)
                    res["bin"] = fb.get("bin", "0-7")
                    res["status"] = fb.get("status", "IN SPEC")
                    res["corr_mm"] = fb.get("corr_mm", 0.0)
                t_5 = time.time()
                res["timings"] = {
                    "setup_ms": round((t_1 - t_0)*1000, 1),
                    "frame_ms": round((t_2 - t_1)*1000, 1),
                    "wlock_wait_ms": round((t_3 - t_2)*1000, 1),
                    "cands_ms": round((t_4 - t_3)*1000, 1),
                    "vision_ms": round((t_5 - t_4)*1000, 1),
                    "total_ms": round((t_5 - t_0)*1000, 1)
                }
                # If requested from recipe load, return immediately for instant response!
                if "recipe_load" in src:
                    return self._send(200, res)
                fn = f"captures/{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time()*1000)%1000:03d}_{src}.jpg"
                try: (HERE / fn).write_bytes(jpg)
                except Exception: pass
                db_res = res["result"] if res["result"] in ("MATCH", "MISMATCH", "NO_READ") else "NO_READ"
                oid = (one(c, "SELECT operator_id FROM operators WHERE name=?", (op,)) or {}).get("operator_id")
                db_rid = rid if (rid and one(c, "SELECT recipe_id FROM recipes WHERE recipe_id=?", (rid,))) else None
                if not db_rid and res.get("best_recipe_id"):
                    cand_rid = res.get("best_recipe_id")
                    if one(c, "SELECT recipe_id FROM recipes WHERE recipe_id=?", (cand_rid,)):
                        db_rid = cand_rid
                try:
                    cur = c.execute("""INSERT INTO camera_verifications(operator_id,recipe_id,capture_path,confidence,result)
                                       VALUES(?,?,?,?,?)""", (oid, db_rid, fn, res.get("confidence", 0), db_res))
                    log_event(c, "CAMERA_VERIFY", f"{res['result']} src={src} best={res.get('best')} inl={res.get('inliers')}", op)
                    c.commit(); res.update(verify_id=cur.lastrowid, capture_url="/" + fn)
                except Exception: pass
                return self._send(200, res)
            finally: c.close()

class RiceVisionServer(ThreadingHTTPServer):
    daemon_threads = True
    def handle_error(self, request, client_address):
        # Gracefully discard client-side disconnects / aborts (e.g. browser tab closed, WinError 10053/10054)
        cls, val, tb = sys.exc_info()
        if cls and issubclass(cls, (ConnectionError, BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 11111)))
    ap.add_argument("--cert"); ap.add_argument("--key")
    ap.add_argument("--auth", help="Enable Basic Auth as user:password")
    a = ap.parse_args()
    if a.auth:
        os.environ["HMI_AUTH"] = a.auth
    if not fbarx_api.auth_enabled():
        sys.stderr.write("\n[FATAL] Server refused to start: HMI_AUTH is not configured.\n")
        sys.stderr.write("To secure the HMI and APIs, set environment variable HMI_AUTH='user:password'\n")
        sys.stderr.write("or pass --auth user:password on the command line.\n\n")
        sys.exit(1)
    if not DB.exists(): print("creating new DB"); 
    init_db()
    srv = RiceVisionServer(("0.0.0.0", a.port), H)
    srv.is_tls = False
    proto = "http"
    if a.cert and a.key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(a.cert, a.key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True); proto = "https"
        srv.is_tls = True
    print(f"RiceVision Phase 1 on {proto}://0.0.0.0:{a.port}   vision={'on' if vision.AVAILABLE else 'OFF (install python3-opencv)'}")
    try:
        cands_pre = get_all_candidates()
        vision.prewarm_cache(cands_pre)
        print(f"[VISION] Prewarmed {len(cands_pre)} reference template descriptors into memory.")
    except Exception as e: print(f"[VISION] Prewarm error: {e}")
    try:
        c = conn()
        act_row = one(c, """SELECT r.repeat_length_mm AS rl, r.mark_window_mm AS mw, r.mark_offset_mm AS mo, r.s_tension_kg AS st
                      FROM active_state s JOIN recipes r ON s.recipe_id=r.recipe_id WHERE s.id=1""")
        m_state = one(c, "SELECT * FROM machine_state WHERE id=1")
        # Ensure stations and outputs start in OFF state on server boot
        c.execute("""UPDATE machine_state 
                     SET stn1_mode='OFF', stn1_output_pct=0.0, stn1_ammeter=0.0, stn1_atension=0.0,
                         stn2_mode='OFF', stn2_output_pct=0.0, stn2_ammeter=0.0, updated_at=?
                     WHERE id=1""", (now(),))
        fbarx_link.link.set_mode('OFF')
        fbarx_link.link.actual_output_pct = 0.0
        fbarx_link.link.target_output_pct = 0.0
        if m_state:
            if m_state.get("stn2_repeat_length_set"):
                fbarx_link.link.sync_boxes(repeat_len=int(m_state["stn2_repeat_length_set"]))
            if m_state.get("stn2_mark_window"):
                fbarx_link.link.sync_boxes(mark_win=int(m_state["stn2_mark_window"]))
            if m_state.get("stn1_stension"):
                fbarx_link.link.want_tension = float(m_state["stn1_stension"])
            fbarx_link.link.counters["0-7"] = m_state.get("cnt_0_7", 0)
            fbarx_link.link.counters["8-15"] = m_state.get("cnt_8_15", 0)
            fbarx_link.link.counters["16-25"] = m_state.get("cnt_16_25", 0)
            fbarx_link.link.counters["26-window"] = m_state.get("cnt_26_w", 0)
            fbarx_link.link.counters["unscored"] = m_state.get("cnt_unscored", 0)
            fbarx_link.link.counters["total"] = m_state.get("cnt_total", 0)
        c.close()
        if act_row: fbarx_link.link.remember(repeat=act_row["rl"], window=act_row["mw"], offset=act_row["mo"], tension=act_row["st"])
    except Exception as e:
        print("[FBARX] remember:", e)
    fbarx_link.link.start(0.2)       # background poll: counting and reconnect do not need a browser open
    print(f"[FBARX] port={fbarx_link.link.port_name} simulated={fbarx_link.link.simulated}")
    try:
        camera.start()
        camera.stop()   # Stop after probe so camera stays in OFF state until explicitly activated
    except Exception as e:
        print(f"[CAMERA] Startup probe: {e}")
    camera_service.start()
    try: srv.serve_forever()
    except KeyboardInterrupt: camera.stop()
