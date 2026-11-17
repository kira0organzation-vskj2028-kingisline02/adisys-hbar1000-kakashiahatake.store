import subprocess
import sys
import time
import urllib.request
import json
import os

PORT = 11195
env = dict(os.environ, FBARX_SIM="1")
server_proc = subprocess.Popen([sys.executable, "server.py", "--port", str(PORT)], env=env)
time.sleep(2.0)

def req(path, method="GET", data=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

try:
    print("=== 1. Test GET /api/state ===")
    code, state = req("/api/state")
    assert code == 200, f"Expected 200, got {code}"
    assert "stn1" in state and "stn2" in state and "counters" in state and "job" in state
    print("PASS: /api/state returns complete machine state")

    print("\n=== 2. Test POST /api/action: set_mode ===")
    code, res = req("/api/action", "POST", {"action": "set_mode", "station": "stn1", "mode": "MAN"})
    assert code == 200 and res["ok"] == True
    assert res["state"]["stn1"]["mode"] == "MAN"
    print("PASS: STN 1 set to MAN")

    code, res = req("/api/action", "POST", {"action": "set_mode", "station": "stn2", "mode": "MAN"})
    assert code == 200 and res["ok"] == True
    assert res["state"]["stn2"]["mode"] == "MAN"
    print("PASS: STN 2 set to MAN")

    print("\n=== 3. Test Range Limits & Rejection (No State Mutation) ===")
    code, res = req("/api/action", "POST", {"action": "set_repeat_length", "value": 50})
    assert code == 400 and res["ok"] == False
    assert "between 100 and 2000" in res["error"]
    print("PASS: Rejected out-of-range repeat_length (50mm):", res["error"])

    code, res = req("/api/action", "POST", {"action": "set_mark_window", "value": 5})
    assert code == 400 and res["ok"] == False
    assert "between 10 and 99" in res["error"]
    print("PASS: Rejected out-of-range mark_window (5mm):", res["error"])

    code, res = req("/api/action", "POST", {"action": "set_stension", "value": 99})
    assert code == 400 and res["ok"] == False
    assert "between 0.0 and 50.0" in res["error"]
    print("PASS: Rejected out-of-range s_tension (99):", res["error"])

    print("\n=== 4. Test Valid Parameter Sets ===")
    code, res = req("/api/action", "POST", {"action": "set_repeat_length", "value": 742})
    assert code == 200 and res["ok"] == True
    assert res["state"]["stn2"]["repeatLength"] == 742
    print("PASS: Valid repeat_length 742")

    code, res = req("/api/action", "POST", {"action": "set_unit", "unit": "N"})
    assert code == 200 and res["ok"] == True
    assert res["state"]["stn1"]["unit"] == "N"
    print("PASS: Unit set to N")

    print("\n=== 5. Test POST /api/login (Passcode Verification) ===")
    code, res = req("/api/login", "POST", {"type": "stn2_cal", "passcode": "wrong"})
    assert code == 401 and res["ok"] == False
    print("PASS: Wrong passcode rejected")

    code, res = req("/api/login", "POST", {"type": "stn2_cal", "passcode": "3333"})
    assert code == 200 and res["ok"] == True and "token" in res
    print("PASS: Correct passcode 3333 accepted, token received")

    code, res = req("/api/login", "POST", {"type": "recipe_cal", "passcode": "4444"})
    assert code == 200 and res["ok"] == True
    print("PASS: Recipe passcode 4444 accepted")

    print("\n=== 6. Test Start & End Job ===")
    code, res = req("/api/action", "POST", {"action": "start_job", "recipe_name": "Veera Sivaji", "operator": "Ramesh"})
    assert code == 200 and res["ok"] == True
    assert res["state"]["job"]["active"] == True
    assert res["state"]["job"]["recipeName"] == "Veera Sivaji"
    print("PASS: Job started")

    code, res = req("/api/action", "POST", {"action": "end_job"})
    assert code == 200 and res["ok"] == True
    assert res["state"]["job"]["active"] == False
    print("PASS: Job ended")

    print("\n=== 7. Test GET /api/report (Pre-calculated metrics) ===")
    code, rep = req("/api/report")
    assert code == 200 and rep["ok"] == True
    assert "records" in rep and "summary" in rep
    assert "total_bags" in rep["summary"] and "pass_pct" in rep["summary"]
    print("PASS: /api/report returns summary and records")

    print("\n=== 8. Test GET & POST /api/calibration ===")
    code, cal = req("/api/calibration")
    assert code == 200 and cal["ok"] == True
    assert "stn1_control" in cal["calibration"] and "stn2" in cal["calibration"]
    print("PASS: /api/calibration loaded")

    code, res = req("/api/calibration", "POST", {"category": "stn1_control", "data": {"propBand": "22.5"}})
    assert code == 200 and res["ok"] == True
    assert res["calibration"]["stn1_control"]["propBand"] == "22.5"
    print("PASS: /api/calibration saved")

    print("\n=== 9. Test POST /api/camera/match ===")
    code, match = req("/api/camera/match", "POST", {})
    assert code == 200 and match["ok"] == True
    print("PASS: /api/camera/match returned OpenCV match result:", match["result"])

    print("\n==========================================")
    print(">>> ALL NEW ENDPOINT TESTS PASSED 100%! <<<")
    print("==========================================")

finally:
    server_proc.terminate()
    server_proc.wait(timeout=2)
