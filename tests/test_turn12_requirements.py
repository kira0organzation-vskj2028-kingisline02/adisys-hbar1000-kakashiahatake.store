import os
import sys
import unittest
import json
import sqlite3
import time

# Ensure simulated environment
os.environ["FBARX_SIM"] = "1"
os.environ["FBARX_PORT"] = ""

import fbarx_link
import fbarx_api
import server

class TestTurn12Requirements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize link in simulation mode
        fbarx_link.link.simulated = True
        fbarx_link.link.connected = True
        fbarx_link.link.fw_ok = True

    def test_01_repeat_length_clamping_fbarx_link(self):
        """M5: Accepts 100-2000 mm; refuses 99 and 2001."""
        # Test boundary values
        fbarx_link.link.set_repeat_length(100)
        self.assertEqual(fbarx_link.link.want_repeat, 100)
        self.assertEqual(fbarx_link.link.regs[9], 100)
        snap = fbarx_link.link.state()
        self.assertEqual(snap["repeatLength"], 100)

        fbarx_link.link.set_repeat_length(2000)
        self.assertEqual(fbarx_link.link.want_repeat, 2000)
        self.assertEqual(fbarx_link.link.regs[9], 2000)
        snap = fbarx_link.link.state()
        self.assertEqual(snap["repeatLength"], 2000)

        # Test nominal value
        fbarx_link.link.set_repeat_length(740)
        self.assertEqual(fbarx_link.link.want_repeat, 740)
        self.assertEqual(fbarx_link.link.regs[9], 740)

        # Refuses 99
        with self.assertRaises(fbarx_link.FieldError):
            fbarx_link.link.set_repeat_length(99)

        # Refuses 2001
        with self.assertRaises(fbarx_link.FieldError):
            fbarx_link.link.set_repeat_length(2001)

    def test_02_repeat_length_clamping_fbarx_api(self):
        """API /api/fbarx/repeat_length accepts 100-2000, refuses 99 and 2001."""
        code, resp = fbarx_api.route_post(fbarx_link.link, "/api/fbarx/repeat_length", {"value": 100}, {})
        self.assertEqual(code, 200)
        self.assertTrue(resp.get("ok"))
        self.assertEqual(resp.get("repeatLength"), 100)

        code, resp = fbarx_api.route_post(fbarx_link.link, "/api/fbarx/repeat_length", {"value": 2000}, {})
        self.assertEqual(code, 200)
        self.assertTrue(resp.get("ok"))
        self.assertEqual(resp.get("repeatLength"), 2000)

        # Refuses 99
        code, resp = fbarx_api.route_post(fbarx_link.link, "/api/fbarx/repeat_length", {"value": 99}, {})
        self.assertEqual(code, 400)
        self.assertIn("must be 100 to 2000", resp.get("error", ""))

        # Refuses 2001
        code, resp = fbarx_api.route_post(fbarx_link.link, "/api/fbarx/repeat_length", {"value": 2001}, {})
        self.assertEqual(code, 400)
        self.assertIn("must be 100 to 2000", resp.get("error", ""))

    def test_03_repeat_length_clamping_server_actions(self):
        """server.py handle_action accepts 100-2000 mm, refuses 99 and 2001 (M5)."""
        # 1. action: set_repeat_length
        with server.WLOCK:
            c = server.conn()
            try:
                res = server.handle_action(c, {"action": "set_repeat_length", "value": 100})
                c.commit()
                self.assertTrue(res.get("ok"))
                self.assertEqual(res.get("repeatLength"), 100)
                self.assertEqual(fbarx_link.link.regs[9], 100)
            finally:
                c.close()

        with server.WLOCK:
            c = server.conn()
            try:
                res = server.handle_action(c, {"action": "set_repeat_length", "value": 2000})
                c.commit()
                self.assertTrue(res.get("ok"))
                self.assertEqual(res.get("repeatLength"), 2000)
                self.assertEqual(fbarx_link.link.regs[9], 2000)
            finally:
                c.close()

        # Refusal on 99
        with server.WLOCK:
            c = server.conn()
            try:
                with self.assertRaises(ValueError):
                    server.handle_action(c, {"action": "set_repeat_length", "value": 99})
            finally:
                c.close()

        # Refusal on 2001
        with server.WLOCK:
            c = server.conn()
            try:
                with self.assertRaises(ValueError):
                    server.handle_action(c, {"action": "set_repeat_length", "value": 2001})
            finally:
                c.close()

        # 2. action: set_parameter
        with server.WLOCK:
            c = server.conn()
            try:
                res = server.handle_action(c, {"action": "set_parameter", "target": "repeat_length", "value": 1500})
                c.commit()
                self.assertTrue(res.get("ok"))
                self.assertEqual(fbarx_link.link.regs[9], 1500)
            finally:
                c.close()

    def test_04_r2_start_82_and_ammeter_moves_with_brake_current(self):
        """R2 must start at 82 (26 registers) and ammeter moves with brake current."""
        # Confirm R2 start and quantity
        self.assertEqual(fbarx_link.R2_START, 82)
        self.assertEqual(fbarx_link.R2_QTY, 26)

        # In OFF mode, ammeter is 0.0
        fbarx_link.link.set_mode("OFF")
        fbarx_link.link.poll()
        snap = fbarx_link.link.state()
        self.assertEqual(fbarx_link.link.regs[82], 0)
        self.assertEqual(snap["ammeter"], 0.0)

        # In MAN mode, ammeter moves with output %
        fbarx_link.link.set_mode("MAN")
        fbarx_link.link.set_output(0.0)
        fbarx_link.link.poll()
        snap = fbarx_link.link.state()
        self.assertEqual(snap["ammeter"], 0.0)

        fbarx_link.link.set_output(50.0)
        fbarx_link.link.poll()
        snap = fbarx_link.link.state()
        # 50% of 3.27A is ~1.64A
        self.assertAlmostEqual(snap["ammeter"], 1.64, delta=0.05)
        self.assertEqual(fbarx_link.link.regs[82], int(round((50.0 / 100.0) * 327)))

        fbarx_link.link.set_output(100.0)
        fbarx_link.link.poll()
        snap = fbarx_link.link.state()
        self.assertAlmostEqual(snap["ammeter"], 3.27, delta=0.05)
        self.assertEqual(fbarx_link.link.regs[82], 327)

        # Stepping output moves ammeter
        fbarx_link.link.step_output("down")
        fbarx_link.link.poll()
        snap = fbarx_link.link.state()
        self.assertAlmostEqual(snap["outputPct"], 99.0, delta=0.1)
        self.assertAlmostEqual(snap["ammeter"], round(327 * 0.99) / 100.0, delta=0.05)

        # In AUTO mode, ammeter shows active running current ~1.80A
        fbarx_link.link.set_mode("AUTO")
        fbarx_link.link.poll()
        snap = fbarx_link.link.state()
        self.assertAlmostEqual(snap["ammeter"], 1.80, delta=0.1)

    def test_05_recipe_load_preserves_reg_74(self):
        """Loading a recipe must confirm reg 74 does NOT change."""
        # Set reg 74 to a known distinctive tension value (e.g. 6.8 kg -> 68 in reg 74)
        fbarx_link.link.set_tension(6.8)
        self.assertEqual(fbarx_link.link.regs[74], 68)
        self.assertEqual(fbarx_link.link.want_tension, 6.8)

        # Also update server machine_state stn1_stension to 6.8
        c = server.conn()
        try:
            c.execute("UPDATE machine_state SET stn1_stension=6.8 WHERE id=1")
            c.commit()
        finally:
            c.close()

        # Create a recipe with a DIFFERENT sTensionTarget (e.g. 3.2 kg)
        recipe_data = {
            "name": "Test Preservation Recipe",
            "repeatLength": 850,
            "markWindow": 45,
            "markOffset": 2,
            "sTensionTarget": 3.2
        }

        # Apply recipe via fbarx_link
        res = fbarx_link.link.apply_recipe(recipe_data)
        self.assertTrue(res["ok"])

        # CONFIRM: reg 74 did NOT change to 32! It must remain 68 (6.8 kg)!
        self.assertEqual(fbarx_link.link.regs[74], 68, "Reg 74 MUST NOT change when loading a recipe!")
        self.assertEqual(fbarx_link.link.want_tension, 6.8, "want_tension MUST NOT change when loading a recipe!")

        # Other fields DID change as expected:
        self.assertEqual(fbarx_link.link.regs[9], 850)
        self.assertEqual(fbarx_link.link.regs[20], 45)

        # Now test recipe load via server action
        # Ensure a recipe exists in database
        c = server.conn()
        try:
            c.execute("INSERT OR REPLACE INTO recipes(recipe_id, name, repeat_length_mm, mark_window_mm, s_tension_kg) VALUES(999, 'TestDBRec', 920, 50, 4.0)")
            c.commit()
        finally:
            c.close()

        # Load recipe through server action
        c = server.conn()
        try:
            srv_res = server.handle_action(c, {"action": "load_recipe", "recipe_id": 999})
            self.assertTrue(srv_res.get("ok"))
        finally:
            c.close()

        # CONFIRM: Reg 74 and stn1_stension still preserved at 68 (6.8 kg)!
        self.assertEqual(fbarx_link.link.regs[74], 68, "Reg 74 MUST NOT change after server load_recipe!")

        c = server.conn()
        try:
            stn1_ten = server.one(c, "SELECT stn1_stension FROM machine_state WHERE id=1")["stn1_stension"]
            self.assertEqual(stn1_ten, 6.8, "STN 1 set tension in machine_state MUST NOT change!")
        finally:
            c.close()

    def test_06_index_html_uses_200ms_poll_and_no_localstorage(self):
        """index.html must poll /api/fbarx/state at 200 ms and have 0 localStorage references."""
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()

        # 0 localStorage
        self.assertEqual(html.count("localStorage"), 0, "localStorage count must be exactly 0!")

        # 200 ms interval for pollFBarXState
        self.assertIn("pollFBarXState();", html)
        self.assertIn("200);", html)
        self.assertIn("startSimulatedSensors", html)

if __name__ == "__main__":
    unittest.main(verbosity=2)
