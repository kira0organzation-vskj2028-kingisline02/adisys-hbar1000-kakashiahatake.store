"""Comprehensive Test Suite for Main Screen Requirements M1 through M19.
Automates validation for all 19 hardware and UI specifications.
"""
import os
import sys
import unittest
import time
import math
import json
import sqlite3

os.environ["FBARX_SIM"] = "1"
os.environ["FBARX_PORT"] = ""

import fbarx_link
import fbarx_api
import server

class TestMainScreenM1toM19(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.link = fbarx_link.FBarXLink(simulate=True)
        cls.link.connected = True
        cls.link.fw_ok = True

    def setUp(self):
        self.link.connected = True
        self.link.fw_ok = True
        self.link.regs[19] = 2001
        self.link.regs[76] = 1
        self.link.regs[77] = 1

    # -------------------------------------------------------------------------
    # M1: Status bar text and firmware check at connect
    # Bar reads 9600-8O1. Reg 19 = 2001, otherwise "wrong firmware" shows.
    # -------------------------------------------------------------------------
    def test_M1_status_bar_and_firmware_check(self):
        # 1. Check baudrate and format
        self.assertEqual(self.link.baudrate, 9600)
        # Check index.html status bar text
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("9600-8O1", html)

        # 2. Firmware check
        self.link.regs[19] = 2001
        self.link.poll()
        self.assertEqual(self.link.regs[19], 2001)
        self.assertEqual(self.link.status(), "SIMULATED")

        # When connected to real board or simulated board with wrong fw:
        real_link = fbarx_link.FBarXLink(simulate=False)
        real_link.connected = True
        real_link.regs[19] = 1999  # wrong firmware
        real_link.fw_ok = False
        self.assertEqual(real_link.status(), "WRONG FIRMWARE")
        # Check UI banner mapping for wrong firmware
        self.assertIn("'WRONG FIRMWARE'", html)
        self.assertIn("WRONG FIRMWARE (expected 2001)", html)

    # -------------------------------------------------------------------------
    # M2: AUTO / MAN / OFF buttons (15 write, 14 read)
    # Each button sets 1 / 0 / 2 and reg 14 reads back the same. Needs reg 76 = 1.
    # -------------------------------------------------------------------------
    def test_M2_auto_man_off_buttons(self):
        self.assertEqual(self.link.regs[76], 1, "Needs reg 76 = 1 (MODE SRC)")

        # AUTO
        self.link.set_mode("AUTO")
        self.assertEqual(self.link.regs[15], 1, "Reg 15 must be set to 1 for AUTO")
        self.assertEqual(self.link.regs[14], 1, "Reg 14 must read 1 for AUTO")
        self.assertEqual(self.link.state()["mode"], "AUTO")

        # MAN
        self.link.set_mode("MAN")
        self.assertEqual(self.link.regs[15], 0, "Reg 15 must be set to 0 for MAN")
        self.assertEqual(self.link.regs[14], 0, "Reg 14 must read 0 for MAN")
        self.assertEqual(self.link.state()["mode"], "MAN")

        # OFF
        self.link.set_mode("OFF")
        self.assertEqual(self.link.regs[15], 2, "Reg 15 must be set to 2 for OFF")
        self.assertEqual(self.link.regs[14], 2, "Reg 14 must read 2 for OFF")
        self.assertEqual(self.link.state()["mode"], "OFF")

    # -------------------------------------------------------------------------
    # M3: MAN OUTPUT -/+ and numpad (Reg 78 in ‰)
    # Setup done once (regs 76 and 77 = 1). 30.0 % is sent as 300.
    # The OUTPUT bar reaches about 30 % within 10 s (2 s ramp).
    # -------------------------------------------------------------------------
    def test_M3_man_output_stepper_and_numpad(self):
        self.assertEqual(self.link.regs[76], 1)
        self.assertEqual(self.link.regs[77], 1)

        self.link.set_mode("MAN")
        # 30.0% is sent as 300 to reg 78
        self.link.set_output(30.0)
        self.assertEqual(self.link.regs[78], 300, "30.0% must be written as 300 to reg 78")

        # Simulate ramp over 10s (dt=0.5s clamped, 20 steps = 10s with tau=2s)
        self.link.actual_output_pct = 0.0
        for _ in range(20):
            self.link.last_ramp_time -= 0.5
            self.link._update_output_ramp()

        # Within 10s it reaches ~30.0%
        self.assertAlmostEqual(self.link.actual_output_pct, 30.0, delta=0.5)
        self.assertAlmostEqual(self.link.regs[6] / 10.0, 30.0, delta=0.5)

        # Stepper: - and +
        cur = self.link.actual_output_pct
        down = self.link.step_output("down")
        self.assertAlmostEqual(down, cur - 1.0, delta=0.1)
        up = self.link.step_output("up")
        self.assertAlmostEqual(up, cur, delta=0.1)

    # -------------------------------------------------------------------------
    # M4: CLR, SCAN, NEW JOB, LOGOUT (Reg 17)
    # Values 1, 2, 3, 5. NEW JOB also resets the zone counters.
    # LOGOUT locks the board password at once.
    # -------------------------------------------------------------------------
    def test_M4_clr_scan_new_job_logout(self):
        # 1: CLR
        self.link.send_cmd("CLR")
        self.assertEqual(self.link.regs[17], 1)

        # 2: SCAN
        self.link.send_cmd("SCAN")
        self.assertEqual(self.link.regs[17], 2)

        # 3: NEW JOB
        self.link.counters["total"] = 50
        self.link.counters["0-7"] = 40
        self.link.send_cmd("NEW JOB")
        self.assertEqual(self.link.regs[17], 3)
        self.assertEqual(self.link.counters["total"], 0, "NEW JOB must reset counters to 0")
        self.assertEqual(self.link.counters["0-7"], 0)

        # 5: LOGOUT
        self.link.unlocked_until = time.time() + 300.0
        self.link.send_cmd("LOGOUT")
        self.assertEqual(self.link.regs[17], 5)
        self.assertEqual(self.link.unlocked_until, 0.0, "LOGOUT must lock password at once")

    # -------------------------------------------------------------------------
    # M5: REPEAT LENGTH SET box (Reg 9)
    # Accepts 100–2000 mm on the tile numpad and in recipe edit; refuses 99 and 2001.
    # The box changes only after the board accepts.
    # -------------------------------------------------------------------------
    def test_M5_repeat_length_set(self):
        # Accepts 100 mm
        self.link.set_repeat_length(100)
        self.assertEqual(self.link.regs[9], 100)
        self.assertEqual(self.link.want_repeat, 100)

        # Accepts 2000 mm
        self.link.set_repeat_length(2000)
        self.assertEqual(self.link.regs[9], 2000)
        self.assertEqual(self.link.want_repeat, 2000)

        # Accepts 740 mm
        self.link.set_repeat_length(740)
        self.assertEqual(self.link.regs[9], 740)

        # Refuses 99
        with self.assertRaises(fbarx_link.FieldError):
            self.link.set_repeat_length(99)
        # Old value 740 stays!
        self.assertEqual(self.link.regs[9], 740)

        # Refuses 2001
        with self.assertRaises(fbarx_link.FieldError):
            self.link.set_repeat_length(2001)
        # Old value 740 stays!
        self.assertEqual(self.link.regs[9], 740)

    # -------------------------------------------------------------------------
    # M6: MARK WINDOW box (Reg 20)
    # Accepts 10–99 mm on both; refuses 9 and 100. No password needed.
    # -------------------------------------------------------------------------
    def test_M6_mark_window(self):
        # Accepts 10 mm
        self.link.set_mark_window(10)
        self.assertEqual(self.link.regs[20], 10)

        # Accepts 99 mm
        self.link.set_mark_window(99)
        self.assertEqual(self.link.regs[20], 99)

        # Accepts 40 mm
        self.link.set_mark_window(40)
        self.assertEqual(self.link.regs[20], 40)

        # Refuses 9
        with self.assertRaises(fbarx_link.FieldError):
            self.link.set_mark_window(9)
        self.assertEqual(self.link.regs[20], 40)

        # Refuses 100
        with self.assertRaises(fbarx_link.FieldError):
            self.link.set_mark_window(100)
        self.assertEqual(self.link.regs[20], 40)

    # -------------------------------------------------------------------------
    # M7: Refusal and resync (Reg 9, 20)
    # On exception 3 or no reply, the old value stays and a message shows.
    # At connect or after a board reset, sync_boxes writes only the registers that differ.
    # A read-back that differs from the box triggers a resync.
    # -------------------------------------------------------------------------
    def test_M7_refusal_and_resync(self):
        self.link.regs[9] = 740
        self.link.regs[20] = 40
        self.link.want_repeat = 740
        self.link.want_window = 40

        # When board values match want values, sync_boxes writes nothing
        changed = self.link.sync_boxes()
        self.assertEqual(changed, {})

        # When board reset occurs (e.g. board loses registers to defaults 0, 0)
        self.link.regs[9] = 0
        self.link.regs[20] = 0
        changed = self.link.sync_boxes()
        self.assertIn("repeatLength", changed)
        self.assertIn("markWindow", changed)
        self.assertEqual(self.link.regs[9], 740)
        self.assertEqual(self.link.regs[20], 40)

    # -------------------------------------------------------------------------
    # M8: Persistence (Reg 9, 20)
    # After a board power cycle it runs on the last values it received.
    # -------------------------------------------------------------------------
    def test_M8_persistence(self):
        self.link.set_repeat_length(1150)
        self.link.set_mark_window(55)

        # Create new link instance simulating restart / power cycle
        new_link = fbarx_link.FBarXLink(simulate=True)
        self.assertEqual(new_link.want_repeat, 1150, "want_repeat must be loaded from persistent DB")
        self.assertEqual(new_link.want_window, 55, "want_window must be loaded from persistent DB")

    # -------------------------------------------------------------------------
    # M9: Recipe load (Reg 9, 20, 21)
    # All three written. Reg 74 unchanged.
    # -------------------------------------------------------------------------
    def test_M9_recipe_load(self):
        self.link.set_tension(5.5)
        self.assertEqual(self.link.regs[74], 55)

        res = self.link.apply_recipe({
            "repeatLength": 880,
            "markWindow": 50,
            "markOffset": 15,
            "sTensionTarget": 9.9
        })
        self.assertTrue(res["ok"])
        self.assertEqual(self.link.regs[9], 880, "Reg 9 must be written on recipe load")
        self.assertEqual(self.link.regs[20], 50, "Reg 20 must be written on recipe load")
        self.assertEqual(self.link.regs[21], 15, "Reg 21 must be written on recipe load")
        self.assertEqual(self.link.regs[74], 55, "Reg 74 MUST REMAIN UNCHANGED!")

    # -------------------------------------------------------------------------
    # M10: REP box (Reg 10-11, 0)
    # Shows REP: 740.0 mm +1.00 mm: length to 1 decimal, error to 2 decimals,
    # always signed. Regs 10-11 are 32 bit, high word first, / 100.
    # -------------------------------------------------------------------------
    def test_M10_rep_box(self):
        self.link.regs[14] = 1 # AUTO
        self.link.regs[1] = 1  # mark valid
        # 740.0 mm -> 74000
        total_length_c_mm = 74000
        self.link.regs[10] = (total_length_c_mm >> 16) & 0xFFFF
        self.link.regs[11] = total_length_c_mm & 0xFFFF
        # +1.00 mm error -> 100
        self.link.regs[0] = 100

        st = self.link._snapshot()
        self.assertEqual(st["repeatLengthActual"], 740.0)
        self.assertEqual(st["markError"], 1.00)

        # Negative error: -1.00 mm -> 65536 - 100 = 65436
        self.link.regs[0] = 65436
        st = self.link._snapshot()
        self.assertEqual(st["markError"], -1.00)

    # -------------------------------------------------------------------------
    # M11: mm scale pointer (Reg 0)
    # Uses the same markError and sign as the REP box, from the same poll.
    # The two never differ.
    # -------------------------------------------------------------------------
    def test_M11_mm_scale_pointer(self):
        self.link.set_live_sim_error(2.35, valid=True)
        st = self.link.state()
        # The markError and signed value are identical
        self.assertEqual(st["markError"], 2.35)
        self.assertTrue(st["markErrorValid"])

    # -------------------------------------------------------------------------
    # M12: Error not valid (Reg 1)
    # Reg 1 = 0 (mark missing, or error 100 mm or more): REP: 740.0 mm +- --,
    # pointer parked at 0 and greyed.
    # -------------------------------------------------------------------------
    def test_M12_error_not_valid(self):
        # Mark missing -> valid=False
        self.link.set_live_sim_error(0.0, valid=False)
        st = self.link.state()
        self.assertFalse(st["markErrorValid"])

        # Error >= 100 mm invalidates mark error
        self.link.set_live_sim_error(105.0, valid=True)
        st = self.link.state()
        self.assertFalse(st["markErrorValid"])

    # -------------------------------------------------------------------------
    # M13: Length not measured (Reg 10-11)
    # Regs = 0 (OFF mode, or fewer than two marks): REP: --- mm.
    # -------------------------------------------------------------------------
    def test_M13_length_not_measured(self):
        # OFF mode zeroes out registers 10-11
        self.link.set_mode("OFF")
        self.link.poll()
        st = self.link.state()
        self.assertEqual(st["repeatLengthActual"], 0.0)
        self.assertEqual(self.link.regs[10], 0)
        self.assertEqual(self.link.regs[11], 0)

    # -------------------------------------------------------------------------
    # M14: Error bands (Reg 20)
    # The last band ends at MARK WINDOW. Labels come from counterBands and redraw
    # when the window changes.
    # Specification Table:
    # 10 mm -> 0-7, 8-10
    # 20 mm -> 0-7, 8-15, 16-20
    # 25 mm -> 0-7, 8-15, 16-25
    # 40 mm -> 0-7, 8-15, 16-25, 26-40
    # 99 mm -> 0-7, 8-15, 16-25, 26-99
    # -------------------------------------------------------------------------
    def test_M14_error_bands(self):
        # 10 mm -> 0-7, 8-10
        b10 = fbarx_link.compute_counter_bands(10)
        self.assertEqual([b["label"] for b in b10], ["0-7 mm", "8-10 mm"])

        # 20 mm -> 0-7, 8-15, 16-20
        b20 = fbarx_link.compute_counter_bands(20)
        self.assertEqual([b["label"] for b in b20], ["0-7 mm", "8-15 mm", "16-20 mm"])

        # 25 mm -> 0-7, 8-15, 16-25
        b25 = fbarx_link.compute_counter_bands(25)
        self.assertEqual([b["label"] for b in b25], ["0-7 mm", "8-15 mm", "16-25 mm"])

        # 40 mm -> 0-7, 8-15, 16-25, 26-40
        b40 = fbarx_link.compute_counter_bands(40)
        self.assertEqual([b["label"] for b in b40], ["0-7 mm", "8-15 mm", "16-25 mm", "26-40 mm"])

        # 99 mm -> 0-7, 8-15, 16-25, 26-99
        b99 = fbarx_link.compute_counter_bands(99)
        self.assertEqual([b["label"] for b in b99], ["0-7 mm", "8-15 mm", "16-25 mm", "26-99 mm"])

    # -------------------------------------------------------------------------
    # M15: Band counting (Reg 0, 100)
    # Error rounded to whole mm first (7.4 goes to 0-7, 7.5 to 8-15).
    # -10 mm counts in 8-15 like +10. TOTAL = counters.total.
    # Missing marks and bags passing between two polls go to unscored.
    # -------------------------------------------------------------------------
    def test_M15_band_counting(self):
        # 7.4 -> 0-7
        self.assertEqual(fbarx_link.band_key(7.4, 40), "0-7")
        # 7.5 -> 8-15
        self.assertEqual(fbarx_link.band_key(7.5, 40), "8-15")
        # -10 -> 8-15
        self.assertEqual(fbarx_link.band_key(-10.0, 40), "8-15")
        # +10 -> 8-15
        self.assertEqual(fbarx_link.band_key(10.0, 40), "8-15")
        # 15.4 -> 8-15
        self.assertEqual(fbarx_link.band_key(15.4, 40), "8-15")
        # 15.5 -> 16-25
        self.assertEqual(fbarx_link.band_key(15.5, 40), "16-25")

        # Missing marks / gap bags go to unscored
        self.link.counters = {k: 0 for k in self.link.counters}
        self.link.regs[100] = 10
        self.link._prev_total = 5 # 5 bags passed
        self.link.regs[0] = 200   # 2.00 mm
        self.link.regs[1] = 1     # valid
        self.link._count_bags()
        # 4 bags unscored, 1 bag in 0-7, total = 5
        self.assertEqual(self.link.counters["unscored"], 4)
        self.assertEqual(self.link.counters["0-7"], 1)
        self.assertEqual(self.link.counters["total"], 5)

    # -------------------------------------------------------------------------
    # M16: Ammeter (Reg 82)
    # Labelled BRAKE CURRENT ACTUAL, in amps (/ 100), shown as indicative until
    # reg 83 is calibrated.
    # -------------------------------------------------------------------------
    def test_M16_ammeter(self):
        # Reg 82 is in 0.01A units (245 = 2.45 A)
        self.link.regs[82] = 245
        st = self.link._snapshot()
        self.assertEqual(st["ammeter"], 2.45)

        # In index.html, check card title and label
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("BRAKE CURRENT ACTUAL", html)
        self.assertIn("Indicative", html)

    # -------------------------------------------------------------------------
    # M17: Alarms and mark status (Reg 18, 28, 2-5)
    # Bit 2 buzzer, bit 3 M1 error, bit 4 M2 error, bit 7 comm lost;
    # reg 28 brake fault. Mark status: 0 T/P, 1 <W>, 2 OK, 3 BLANK.
    # -------------------------------------------------------------------------
    def test_M17_alarms_and_mark_status(self):
        # Alarms: reg 18
        # bit 2 = 4 (buzzer), bit 3 = 8 (m1_err), bit 4 = 16 (m2_err), bit 7 = 128 (comm_lost)
        self.link.regs[18] = 4 | 8 | 16 | 128
        self.link.regs[28] = 1 # brake fault
        st = self.link._snapshot()
        self.assertTrue(st["alarms"]["buzzer"])
        self.assertTrue(st["alarms"]["m1_err"])
        self.assertTrue(st["alarms"]["m2_err"])
        self.assertTrue(st["alarms"]["comm_lost"])
        self.assertTrue(st["alarms"]["brake_fault"])

        # Mark status: 0=T/P, 1=<W>, 2=OK, 3=BLANK
        self.link.regs[2] = 2; self.link.regs[3] = 12
        self.link.regs[4] = 1; self.link.regs[5] = 9
        st = self.link._snapshot()
        self.assertEqual(st["m1"]["status"], "OK")
        self.assertEqual(st["m1"]["marks"], 12)
        self.assertEqual(st["m2"]["status"], "<W>")
        self.assertEqual(st["m2"]["marks"], 9)

        self.link.regs[2] = 0
        self.link.regs[4] = 3
        st = self.link._snapshot()
        self.assertEqual(st["m1"]["status"], "T/P")
        self.assertEqual(st["m2"]["status"], "BLANK")

    # -------------------------------------------------------------------------
    # M18: Connection dot and link loss
    # Green only while polls return valid replies. Unplug RS-485: "not connected"
    # shows and the STN 2 values grey. The link waits 0.5 s, then retries once,
    # so allow about 1.5 s; 1 s is the minimum, not a safe limit.
    # -------------------------------------------------------------------------
    def test_M18_connection_dot_and_link_loss(self):
        self.assertEqual(fbarx_link.REPLY_TIMEOUT, 0.5)

        # When connected
        self.link.connected = True
        self.link.fw_ok = True
        st = self.link.state()
        self.assertTrue(st["connected"])

        # When disconnected
        self.link.connected = False
        self.assertEqual(self.link.status(), "NOT CONNECTED")
        st = self.link.state()
        self.assertFalse(st["connected"])
        self.assertEqual(st["status"], "NOT CONNECTED")

        # In index.html: grey out STN 2 and show not connected banner
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("col-stn2.link-down", html)
        self.assertIn("STN 2 NOT CONNECTED", html)

    # -------------------------------------------------------------------------
    # M19: Polling
    # R1 (regs 0-30) and R2 every 200 ms through one queue, so polls and writes
    # never overlap. Bus time is about 120 ms per cycle.
    # -------------------------------------------------------------------------
    def test_M19_polling(self):
        self.assertEqual(fbarx_link.R1_START, 0)
        self.assertEqual(fbarx_link.R1_QTY, 31, "Regs 0-30 = 31 registers")
        self.assertEqual(fbarx_link.R2_START, 82)
        self.assertEqual(fbarx_link.R2_QTY, 26, "Regs 82-107 = 26 registers")

        # Polling and writes synchronized by link.lock (one queue)
        self.assertTrue(hasattr(self.link, "lock"))

        # Verify 200 ms interval in index.html for /api/fbarx/state
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("pollFBarXState();", html)
        self.assertIn("200);", html)

if __name__ == "__main__":
    unittest.main(verbosity=2)
