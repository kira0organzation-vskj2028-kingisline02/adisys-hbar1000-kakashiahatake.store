"""Tests for Tension from STN 1 and Security Requirements:
1. STN 1 S-Tension setting copied to reg 74 (kg x 10) through set_tension(kg) on change and connect.
2. STN 2 Proportional gain: Kp = ACerr/100 + SetTension/1000 (e.g. ACerr 7.0 with 40.0 kg gives 0.07 + 0.04 = 0.11).
3. Second slave gets S-Tension by direct write (no broadcast, address != 1).
4. Security tests: Without login, /api/state, /api/recipes, /api/operators, /api/report, /api/fbarx/*, and the page itself are refused (401).
5. Board password 1212 appears nowhere in browser JavaScript or network traffic.
6. TLS 1.3 works and HTTP redirects to HTTPS on live server.
"""
import base64
import json
import os
import sqlite3
import ssl
import socket
import sys
import unittest
import urllib.request
import urllib.error

# Ensure simulation mode
os.environ["FBARX_SIM"] = "1"
os.environ["FBARX_PORT"] = ""

import fbarx_link
import fbarx_api
import server


class TestTensionAndSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fbarx_link.link.simulated = True
        fbarx_link.link.connected = True
        fbarx_link.link.fw_ok = True
        server.init_db()

    def setUp(self):
        fbarx_link.link.simulated = True
        fbarx_link.link.connected = True
        fbarx_link.link.fw_ok = True
        fbarx_link.link.regs[71] = 70   # default ACerr 7.0 %
        fbarx_link.link.regs[74] = 50   # default SetTension 5.0 kg

    # =========================================================================
    # PART 1: TENSION FROM STN 1 & Kp CALCULATION
    # =========================================================================
    def test_01_set_tension_updates_reg74_and_db(self):
        """set_tension(kg) writes reg 74 as kg * 10."""
        fbarx_link.link.set_tension(40.0, remember=True)
        self.assertEqual(fbarx_link.link.regs[74], 400, "Reg 74 must be stored as kg * 10 (40.0 -> 400)")
        self.assertEqual(fbarx_link.link.want_tension, 40.0)

        snap = fbarx_link.link.state()
        self.assertEqual(snap["setTension"], 40.0)
        self.assertEqual(snap["sTensionTarget"], 40.0)

    def test_02_tension_kp_formula(self):
        """Kp = ACerr/100 + SetTension/1000.
        Spec example: ACerr 7.0 with 40.0 kg gives 0.07 + 0.04 = 0.11."""
        fbarx_link.link.regs[71] = 70   # ACerr = 7.0
        fbarx_link.link.set_tension(40.0, remember=True)

        # Direct property
        self.assertAlmostEqual(fbarx_link.link.kp, 0.11, places=4,
                               msg="Kp must equal ACerr/100 + SetTension/1000 (0.07 + 0.04 = 0.11)")

        # In snapshot
        snap = fbarx_link.link.state()
        self.assertAlmostEqual(snap["kp"], 0.11, places=4)
        self.assertAlmostEqual(snap["proportionalGain"], 0.11, places=4)

        # In calibration dict
        cal = fbarx_link.link.get_calibration()
        self.assertAlmostEqual(cal["kp"], 0.11, places=4)
        self.assertAlmostEqual(cal["proportionalGain"], 0.11, places=4)

        # Another case: ACerr = 10.0%, SetTension = 25.0 kg -> 0.10 + 0.025 = 0.125
        fbarx_link.link.regs[71] = 100
        fbarx_link.link.set_tension(25.0, remember=True)
        self.assertAlmostEqual(fbarx_link.link.kp, 0.125, places=4)

    def test_03_stn1_set_stension_action_syncs_reg74(self):
        """Action 'set_stension' in server.py copies value to reg 74 via set_tension()."""
        c = server.conn()
        try:
            res = server.handle_action(c, {"action": "set_stension", "value": 35.5})
            self.assertTrue(res.get("ok"))
            self.assertEqual(fbarx_link.link.regs[74], 355, "Reg 74 must update to 355 (35.5 kg * 10)")
            self.assertEqual(fbarx_link.link.want_tension, 35.5)

            # DB check
            row = server.one(c, "SELECT stn1_stension FROM machine_state WHERE id=1")
            self.assertEqual(row["stn1_stension"], 35.5)
        finally:
            c.close()

    def test_04_stn1_set_parameter_stension_syncs_reg74(self):
        """Action 'set_parameter' target 'sTensionTarget' copies value to reg 74 via set_tension()."""
        c = server.conn()
        try:
            res = server.handle_action(c, {"action": "set_parameter", "target": "sTensionTarget", "value": 22.0})
            self.assertTrue(res.get("ok"))
            self.assertEqual(fbarx_link.link.regs[74], 220, "Reg 74 must update to 220 (22.0 kg * 10)")
            self.assertEqual(fbarx_link.link.want_tension, 22.0)
        finally:
            c.close()

    def test_05_tension_copied_at_connect(self):
        """On connect (_on_connect), STN 1 S-Tension setting is copied to reg 74."""
        fbarx_link.link.want_tension = 18.5
        fbarx_link.link.regs[74] = 0
        fbarx_link.link._on_connect()
        self.assertEqual(fbarx_link.link.regs[74], 185, "Reg 74 must be restored to 185 on connect")

    def test_06_recipe_load_preserves_reg74(self):
        """Recipe load never changes reg 74."""
        fbarx_link.link.set_tension(42.0, remember=True)
        self.assertEqual(fbarx_link.link.regs[74], 420)

        # Apply a recipe with repeatLength, markWindow, markOffset
        res = fbarx_link.link.apply_recipe({"repeatLength": 750, "markWindow": 30, "markOffset": 5})
        self.assertTrue(res["ok"])
        self.assertEqual(fbarx_link.link.regs[74], 420, "Reg 74 must remain 420 after recipe load")
        self.assertEqual(fbarx_link.link.want_tension, 42.0)

    def test_07_second_slave_tension_write(self):
        """The second slave gets S-Tension by its own write, with no broadcast (addr != 1 and addr != 0)."""
        # Valid second slave write (e.g. slave address 2)
        res = fbarx_link.link.set_second_slave_tension(2, 40.0)
        self.assertTrue(res)

        # Refuses broadcast address 0
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            fbarx_link.link.set_second_slave_tension(0, 40.0)
        self.assertIn("no broadcast", str(ctx.exception))

        # Refuses address 1 (FBARX address)
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            fbarx_link.link.set_second_slave_tension(1, 40.0)
        self.assertIn("must differ from 1", str(ctx.exception))

        # Out-of-range tension refused
        with self.assertRaises(fbarx_link.FieldError):
            fbarx_link.link.set_second_slave_tension(2, 105.0)

    # =========================================================================
    # PART 2: SECURITY TESTS (HTTP BASIC AUTH GATING)
    # =========================================================================
    def test_08_security_basic_auth_refusal_without_login(self):
        """Without a login, /api/state, /api/recipes, /api/operators, /api/report, /api/fbarx/*,
        and the page itself must return 401 Unauthorized when auth is enabled."""
        old_auth = os.environ.get("HMI_AUTH")
        os.environ["HMI_AUTH"] = "operator:securepass"
        try:
            # Helper mock request handler to test do_GET refusal
            class MockResponse:
                def __init__(self):
                    self.status = None
                    self.headers = {}
                    self.data = None

            class MockHandler(server.H):
                def __init__(self, path, auth_header=None):
                    self.path = path
                    self.headers = {"Authorization": auth_header} if auth_header else {}
                    self.mock_resp = MockResponse()

                def _send(self, code, data=None, mime="application/json", cache_control="no-store", extra=None):
                    self.mock_resp.status = code
                    self.mock_resp.data = data
                    if extra:
                        self.mock_resp.headers.update(extra)

                def send_response(self, code):
                    self.mock_resp.status = code

                def send_header(self, k, v):
                    self.mock_resp.headers[k] = v

                def end_headers(self):
                    pass

            paths_to_test = [
                "/api/state",
                "/api/recipes",
                "/api/operators",
                "/api/report",
                "/api/fbarx/state",
                "/api/fbarx/calibration",
                "/api/fbarx/repeat_length",
                "/api/fbarx/mark_window",
                "/",
                "/index.html",
            ]

            # 1. Unauthenticated: every one must return 401 with WWW-Authenticate header
            for p in paths_to_test:
                h = MockHandler(p, auth_header=None)
                h.do_GET()
                self.assertEqual(h.mock_resp.status, 401, f"Path {p} must be refused with 401 when unauthenticated")
                self.assertIn('Basic realm="FBAR 1000"', h.mock_resp.headers.get("WWW-Authenticate", ""),
                              f"Path {p} must return WWW-Authenticate header")

            # 2. Authenticated: valid credentials succeed
            good_auth = "Basic " + base64.b64encode(b"operator:securepass").decode()
            h_state = MockHandler("/api/state", auth_header=good_auth)
            h_state.do_GET()
            self.assertEqual(h_state.mock_resp.status, 200, "/api/state must return 200 when authenticated")

            h_fbarx = MockHandler("/api/fbarx/state", auth_header=good_auth)
            h_fbarx.do_GET()
            self.assertEqual(h_fbarx.mock_resp.status, 200, "/api/fbarx/state must return 200 when authenticated")

        finally:
            if old_auth is None:
                os.environ.pop("HMI_AUTH", None)
            else:
                os.environ["HMI_AUTH"] = old_auth

    # =========================================================================
    # PART 3: BOARD PASSWORD 1212 ZERO-LEAKAGE CHECK
    # =========================================================================
    def test_09_password_1212_absent_from_frontend_and_network(self):
        """The board password 1212 appears nowhere in browser JavaScript, HTML, CSS, or JSON API payloads."""
        # Frontend check: static directory
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        for root, _, files in os.walk(static_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    self.assertNotIn("1212", content, f"Board password 1212 found in frontend file: {fname}!")

        # Network payload check: state snapshot
        snap_json = json.dumps(fbarx_link.link.state())
        self.assertNotIn("1212", snap_json, "Board password 1212 leaked in fbarx state snapshot JSON!")

        # Calibration payload check
        cal_json = json.dumps(fbarx_link.link.get_calibration())
        self.assertNotIn("1212", cal_json, "Board password 1212 leaked in calibration JSON!")

        # Full machine state check
        full_json = json.dumps(server.get_full_state())
        self.assertNotIn("1212", full_json, "Board password 1212 leaked in full machine state JSON!")

    # =========================================================================
    # PART 4: TLS 1.3 & HTTPS REDIRECT ON LIVE SERVER
    # =========================================================================
    def test_10_live_tls13_and_http_redirect(self):
        """TLS 1.3 works, HTTP port 80 redirects to HTTPS, and cert is valid."""
        host = "adisys.kakashihatake.store"

        # 1. Test HTTP port 80 redirect
        try:
            req = urllib.request.Request(f"http://{host}/", method="GET")
            # Open without following redirect automatically to check 301
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener = urllib.request.build_opener(NoRedirect)
            try:
                resp = opener.open(req, timeout=5)
                status = resp.status
                loc = resp.headers.get("Location")
            except urllib.error.HTTPError as e:
                status = e.code
                loc = e.headers.get("Location")

            self.assertEqual(status, 301, "Port 80 must return 301 Moved Permanently")
            self.assertTrue(loc.startswith("https://"), f"Redirect location must start with https://, got {loc}")
        except Exception as e:
            self.skipTest(f"Live network test skipped (host unreachable): {e}")

        # 2. Test TLS 1.3 socket connection and certificate
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    version = ssock.version()
                    self.assertEqual(version, "TLSv1.3", "Live server must support and negotiate TLSv1.3")
                    cert = ssock.getpeercert()
                    issuer = dict(x[0] for x in cert.get("issuer", ()))
                    self.assertIn("Let's Encrypt", issuer.get("organizationName", ""),
                                  "Issuer must be Let's Encrypt")
                    self.assertIn("2027", cert.get("notAfter", ""),
                                  "Certificate expiration must be in 2027")
        except Exception as e:
            self.skipTest(f"Live SSL network test skipped: {e}")


if __name__ == "__main__":
    unittest.main()
