import subprocess
import time
import sys
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Start modbus_slave_sim on port 5021
sim_proc = subprocess.Popen(
    [sys.executable, os.path.join(ROOT_DIR, "modbus_slave_sim.py"), "--port", "5021"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
time.sleep(1.5)

try:
    from fbarx_link import FBarXLink
    link = FBarXLink(port="socket://127.0.0.1:5021", simulate=False)
    link.start()
    time.sleep(3.0)

    snap = link._snapshot()
    print("Snapshot connected:", snap["connected"])
    print("Snapshot status:", snap["status"])
    print("Snapshot lastError:", repr(snap["lastError"]))
    print("Snapshot speedMpm:", snap["speedMpm"])
    print("Snapshot ammeter:", snap["ammeter"])
    print("Snapshot mode:", snap["mode"])
    print("Snapshot m1:", snap["m1"])
    print("Snapshot m2:", snap["m2"])
    print("Snapshot repAct:", snap["repeatLengthActual"])

    assert snap["connected"] == True, "Failed to connect to modbus slave sim!"
    assert snap["lastError"] == "", f"Unexpected lastError: {snap['lastError']}"
    assert snap["speedMpm"] == 100, f"Expected speed 100, got {snap['speedMpm']}"
    assert snap["ammeter"] >= 1.7, f"Expected ammeter >= 1.7, got {snap['ammeter']}"
    assert snap["m1"]["status"] == "OK", f"Expected m1 OK, got {snap['m1']}"
    assert snap["m2"]["status"] == "OK", f"Expected m2 OK, got {snap['m2']}"

    # Test mode switch to OFF
    print("\nSetting mode to OFF...")
    link.set_mode("OFF")
    time.sleep(2.0)
    snap_off = link._snapshot()
    print("OFF mode snap: mode =", snap_off["mode"], "outputPct =", snap_off["outputPct"], "ammeter =", snap_off["ammeter"], "repAct =", snap_off["repeatLengthActual"])
    assert snap_off["mode"] == "OFF", f"Expected OFF, got {snap_off['mode']}"
    assert snap_off["ammeter"] == 0.0, f"Expected 0.0A in OFF, got {snap_off['ammeter']}"
    assert snap_off["outputPct"] == 0.0, f"Expected 0.0% in OFF, got {snap_off['outputPct']}"

    # Test mode switch back to AUTO
    print("\nSetting mode back to AUTO...")
    link.set_mode("AUTO")
    time.sleep(2.0)
    snap_auto = link._snapshot()
    print("AUTO mode snap: mode =", snap_auto["mode"], "outputPct =", snap_auto["outputPct"], "ammeter =", snap_auto["ammeter"], "repAct =", snap_auto["repeatLengthActual"])
    assert snap_auto["mode"] == "AUTO"
    assert snap_auto["ammeter"] >= 1.7, f"Expected ammeter >= 1.7 in AUTO, got {snap_auto['ammeter']}"

    print("\nALL MODBUS DEPLOYMENT TESTS PASSED PERFECTLY!")

finally:
    try:
        link.stop()
    except Exception:
        pass
    sim_proc.terminate()
    sim_proc.wait(timeout=2)
