import sqlite3
import json
import time
import vision
import fbarx_link
from pathlib import Path

HERE = Path(".")
DB = HERE / "rice_vision.db"
WLOCK = fbarx_link.threading.Lock()

def now(): return time.strftime("%Y-%m-%dT%H:%M:%S")

def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c

def one(c, sql, a=()):
    r = c.execute(sql, a).fetchone()
    return dict(r) if r else None

def rows(c, sql, a=()):
    return [dict(r) for r in c.execute(sql, a).fetchall()]

RECIPE_COLS = {
    "repeatLength": "repeat_length_mm", "width": "width_mm", "material": "material", "markWindow": "mark_window_mm",
    "markOffset": "mark_offset_mm", "sTensionTarget": "s_tension_kg", "frontSensor": "front_sensor", "frontMark": "front_mark",
    "frontBackground": "front_background", "backSensor": "back_sensor", "backMark": "back_mark", "backBackground": "back_background",
    "brandTamil": "brand_tamil", "product": "product", "netWeight": "bag_weight_kg"
}

SQL_RECIPES = """SELECT r.*, i.image_id, i.image_name, i.image_path, i.mime_type AS image_type
                 FROM recipes r
                 LEFT JOIN (
                     SELECT recipe_id, image_id, image_name, image_path, mime_type
                     FROM recipe_images
                     WHERE is_active = 1
                     GROUP BY recipe_id
                 ) i ON i.recipe_id=r.recipe_id"""

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

def get_full_state():
    with WLOCK:
        c = conn()
        try:
            m = one(c, "SELECT * FROM machine_state WHERE id=1")
            a = one(c, "SELECT * FROM active_state WHERE id=1") or {}
            rec = one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (a.get("recipe_id"),)) if a.get("recipe_id") else None
            op = one(c, "SELECT name FROM operators WHERE operator_id=?", (a.get("operator_id"),)) if a.get("operator_id") else None
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

    stn2_mode = fb_snap.get("mode", m["stn2_mode"] if m else "AUTO")
    stn1_mode = m["stn1_mode"] if m else "OFF"
    stn1_is_off = (stn1_mode == "OFF")
    stn2_is_off = (stn2_mode == "OFF")

    stn1_amp = 0.0 if stn1_is_off else float(m.get("stn1_ammeter") or 1.8)
    stn1_out = 0.0 if stn1_is_off else float(m.get("stn1_output_pct") or 50.0)
    stn1_aten = 0.0 if stn1_is_off else float(m.get("stn1_atension") or 18.2)

    stn2_amp = 0.0 if stn2_is_off else float(fb_snap.get("ammeter") or 1.78)
    stn2_out = 0.0 if stn2_is_off else float(fb_snap.get("outputPct") or 55.0)
    stn2_spd = 0 if stn2_is_off else int(fb_snap.get("speedMpm") or 100)

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

    return {
        "ok": True,
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
            "bagId": 1000,
            "corrMm": 0.0
        },
        "camera": {
            "running": False,
            "modeBadge": cam_badge,
            "fps": 25.0,
            "confidence": 0.98
        },
        "recipe": to_ui(rec) if rec else None,
        "operator": op["name"] if op else ""
    }

state = get_full_state()
print("get_full_state test successful!")
print("stn1:", state["stn1"])
print("stn2:", state["stn2"])
print("job:", state["job"])
print("counters:", state["counters"])
