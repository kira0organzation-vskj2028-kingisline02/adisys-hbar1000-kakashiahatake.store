import sys
sys.path.insert(0, '.')
import sqlite3
import json
import time
import fbarx_link
from scratch.test_server_logic import get_full_state, conn, one, now, SQL_RECIPES

def upsert_operator(c, name):
    name = (name or "").strip()
    if not name: return None
    c.execute("INSERT OR IGNORE INTO operators(name) VALUES(?)", (name,))
    op = one(c, "SELECT * FROM operators WHERE name=?", (name,))
    return op["operator_id"]

def handle_action(c, d, client_ip="127.0.0.1"):
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
            c.execute("UPDATE machine_state SET stn1_mode=?, updated_at=? WHERE id=1", (mode, now()))
        elif station == "stn2":
            fbarx_link.link.set_mode(mode)
            c.execute("UPDATE machine_state SET stn2_mode=?, updated_at=? WHERE id=1", (mode, now()))
        return {"ok": True}

    elif action == "step_output":
        station = d.get("station")
        direction = d.get("direction", "up").lower()
        if station not in ("stn1", "stn2"):
            raise ValueError("Invalid station")
        if direction not in ("up", "down"):
            raise ValueError("Direction must be up or down")

        delta = 1.0 if direction == "up" else -1.0
        if station == "stn1":
            row = one(c, "SELECT stn1_output_pct, stn1_mode FROM machine_state WHERE id=1")
            if row.get("stn1_mode") != "MAN":
                raise ValueError("STN 1 output can only be stepped in MAN mode")
            cur = float(row.get("stn1_output_pct") or 50.0)
            new_val = max(0.0, min(100.0, round(cur + delta, 1)))
            c.execute("UPDATE machine_state SET stn1_output_pct=?, updated_at=? WHERE id=1", (new_val, now()))
        elif station == "stn2":
            fbarx_link.link.step_output(direction)
        return {"ok": True}

    elif action == "set_repeat_length":
        val = float(d.get("value", 0))
        if val < 100 or val > 1500:
            raise ValueError("Repeat Length must be between 100 and 1500 mm")
        fbarx_link.link.sync_boxes(repeat_len=int(round(val)))
        c.execute("UPDATE machine_state SET stn2_repeat_length_set=?, updated_at=? WHERE id=1", (int(round(val)), now()))
        return {"ok": True}

    elif action == "set_mark_window":
        val = float(d.get("value", 0))
        if val < 10 or val > 99:
            raise ValueError("Mark Window must be between 10 and 99 mm")
        fbarx_link.link.sync_boxes(mark_win=int(round(val)))
        c.execute("UPDATE machine_state SET stn2_mark_window=?, updated_at=? WHERE id=1", (int(round(val)), now()))
        return {"ok": True}

    elif action == "set_stension":
        val = float(d.get("value", 0))
        if val < 0.0 or val > 50.0:
            raise ValueError("S-Tension must be between 0.0 and 50.0")
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
            val = float(raw_val)
            if val < 100 or val > 1500: raise ValueError("Repeat Length must be between 100 and 1500 mm")
            fbarx_link.link.sync_boxes(repeat_len=int(round(val)))
            c.execute("UPDATE machine_state SET stn2_repeat_length_set=?, updated_at=? WHERE id=1", (int(round(val)), now()))
        elif target in ("mark_window", "markWindow"):
            val = float(raw_val)
            if val < 10 or val > 99: raise ValueError("Mark Window must be between 10 and 99 mm")
            fbarx_link.link.sync_boxes(mark_win=int(round(val)))
            c.execute("UPDATE machine_state SET stn2_mark_window=?, updated_at=? WHERE id=1", (int(round(val)), now()))
        elif target in ("stension", "sTensionTarget", "stensionTarget"):
            val = float(raw_val)
            if val < 0.0 or val > 50.0: raise ValueError("S-Tension must be between 0.0 and 50.0")
            fbarx_link.link.want_tension = round(val, 1)
            c.execute("UPDATE machine_state SET stn1_stension=?, updated_at=? WHERE id=1", (round(val, 1), now()))
        elif target in ("outputPct", "output"):
            stn = d.get("station", "stn1")
            val = float(raw_val)
            if val < 0.0 or val > 100.0: raise ValueError("Output % must be between 0.0 and 100.0")
            if stn == "stn1":
                c.execute("UPDATE machine_state SET stn1_output_pct=?, updated_at=? WHERE id=1", (round(val, 1), now()))
            else:
                fbarx_link.link.set_output(round(val, 1))
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
        return {"ok": True}

    elif action == "start_job":
        rid = d.get("recipe_id")
        op = (d.get("operator") or "").strip()
        rec = None
        if rid: rec = one(c, SQL_RECIPES + " WHERE r.recipe_id=?", (rid,))
        if not rec and d.get("recipe_name"): rec = one(c, SQL_RECIPES + " WHERE LOWER(r.name)=LOWER(?)", (d.get("recipe_name"),))
        if not rec: raise ValueError("Select a recipe to start job")
        if not op: raise ValueError("Select an operator to start job")

        t_start = now()
        c.execute("""UPDATE machine_state SET job_active=1, job_recipe_id=?, job_recipe_name=?, job_operator=?,
                     job_start_time=?, job_end_time=NULL, cnt_0_7=0, cnt_8_15=0, cnt_16_25=0, cnt_26_w=0,
                     cnt_unscored=0, cnt_total=0, updated_at=? WHERE id=1""",
                  (rec["recipe_id"], rec["name"], op, t_start, t_start))
        oid = upsert_operator(c, op)
        c.execute("UPDATE active_state SET recipe_id=?, operator_id=?, loaded_at=? WHERE id=1", (rec["recipe_id"], oid, t_start))
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
        return {"ok": True}

    raise ValueError(f"Unknown action: {action}")

# Test suite for actions
c = conn()
try:
    # 1. Test set_mode
    res = handle_action(c, {"action": "set_mode", "station": "stn1", "mode": "MAN"})
    assert res["ok"] == True
    assert one(c, "SELECT stn1_mode FROM machine_state WHERE id=1")["stn1_mode"] == "MAN"
    print("PASS: set_mode stn1 MAN")

    # 2. Test out-of-range rejection
    try:
        handle_action(c, {"action": "set_repeat_length", "value": 50})
        assert False, "Should have thrown ValueError"
    except ValueError as e:
        print("PASS: set_repeat_length out-of-range rejection:", e)

    try:
        handle_action(c, {"action": "set_mark_window", "value": 150})
        assert False, "Should have thrown ValueError"
    except ValueError as e:
        print("PASS: set_mark_window out-of-range rejection:", e)

    # 3. Test valid repeat length
    res = handle_action(c, {"action": "set_repeat_length", "value": 745})
    assert res["ok"] == True
    print("PASS: set_repeat_length 745")

    # 4. Test start_job and end_job
    res = handle_action(c, {"action": "start_job", "recipe_name": "Veera Sivaji", "operator": "Ramesh"})
    assert res["ok"] == True
    m_job = one(c, "SELECT job_active, job_recipe_name, job_operator FROM machine_state WHERE id=1")
    assert m_job["job_active"] == 1
    assert m_job["job_operator"] == "Ramesh"
    print("PASS: start_job")

    res = handle_action(c, {"action": "end_job"})
    assert res["ok"] == True
    assert one(c, "SELECT job_active FROM machine_state WHERE id=1")["job_active"] == 0
    print("PASS: end_job")

    c.commit()
finally:
    c.close()

print("\nALL ACTION TESTS PASSED 100%!")
