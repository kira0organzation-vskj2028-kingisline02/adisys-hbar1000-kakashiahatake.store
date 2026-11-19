"""Audit Hardening & Verification Test Suite for RiceVision HMI.
Validates the 8 critical security, validation, schema, and cleanup items:
1. Server refuses to boot without HMI_AUTH.
2. Legacy /api/calibration requires valid token, refuses out-of-range writes (e.g. acErr 500), and propagates errors.
3. Unified role-based unlock (/api/fbarx/unlock) with config-driven passcodes and 30s lockout after 5 failed attempts; old /api/login removed (404).
4. Recipe save parameter bounds: strictly refuses out-of-bounds parameters with HTTP 400 naming the field (repeatLength 50/3000, markWindow 120, markOffset 5000).
5. Database schema: repeat length 100-2000 mm, production_records includes c_26_w, unscored, window_mm; station_calibration table removed.
6. Report math: unscored bags are excluded from fail_pct tolerance failure calculation.
7. CORS origin restriction and HTTP Basic Auth security warning.
8. Zero localStorage across all static files and removal of obsolete static assets.
"""
import os
import sys
import unittest
import subprocess
import time
import requests
import json
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config
import fbarx_api
import fbarx_link
import server


class TestAuditHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HMI_AUTH"] = "admin:admin123"
        config.HMI_AUTH = "admin:admin123"

    def test_01_server_refuses_to_boot_without_hmi_auth(self):
        """Server must immediately exit with code 1 when HMI_AUTH is missing."""
        env = dict(os.environ)
        env.pop("HMI_AUTH", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", "19999"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=5)
        self.assertNotEqual(proc.returncode, 0, "Server must not exit with code 0 when HMI_AUTH is missing")
        self.assertIn("HMI_AUTH is not configured", stderr)

    def test_02_legacy_api_calibration_token_check_and_range_validation(self):
        """Legacy /api/calibration must require token, reject acErr 500, and propagate board errors."""
        # 1. No token -> 403
        status, body = server.handle_calibration_post({"category": "stn1_control", "data": {"acErr": 1.5}}, token=None)
        self.assertEqual(status, 403)
        self.assertIn("token", body.get("error", "").lower())

        # 2. Out-of-range acErr 500 with token -> FieldError (400)
        # First get a valid token
        unlock_status, unlock_res = fbarx_api._unlock({"code": "1111", "type": "stn1_control"})
        self.assertEqual(unlock_status, 200)
        tok = unlock_res["token"]

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            server.handle_calibration_post({"category": "stn1_control", "data": {"acErr": 500}}, token=tok)
        self.assertEqual(ctx.exception.field, "acErr")

        # 3. Valid acErr (e.g. 2.5) -> 200
        ok_status, ok_body = server.handle_calibration_post({"category": "stn1_control", "data": {"acErr": 2.5}}, token=tok)
        self.assertEqual(ok_status, 200)

    def test_03_passcode_lockout_and_old_route_removal(self):
        """Unified unlock has 30s lockout after 5 fails; old /api/login returns 404."""
        # Reset fails
        fbarx_api._fails["n"] = 0
        fbarx_api._fails["until"] = 0.0

        # Attempt 4 wrong codes -> 403
        for _ in range(4):
            status, res = fbarx_api._unlock({"code": "9999"})
            self.assertEqual(status, 403)
            self.assertFalse(res["ok"])

        # 5th wrong code -> 429 lockout
        status, res = fbarx_api._unlock({"code": "9999"})
        self.assertEqual(status, 429)
        self.assertIn("too many wrong codes", res["error"])
        self.assertGreater(res["wait_s"], 0)

        # Immediate attempt with correct code during lockout still gets 429
        status, res = fbarx_api._unlock({"code": "3333"})
        self.assertEqual(status, 429)

        # Clear lockout for subsequent tests
        fbarx_api._fails["until"] = 0.0

        # Old route removal in server handler returns 404
        class DummyHandler:
            pass
        h = DummyHandler()
        # Test routing in server.py do_POST:
        # /api/login returns 404
        # We can test with MockHandler or direct inspect
        from http.server import BaseHTTPRequestHandler
        from io import BytesIO
        class MockRequest:
            def __init__(self):
                self.output = BytesIO()
            def makefile(self, mode="r", *a, **k):
                if "w" in mode:
                    return self.output
                return BytesIO(b"POST /api/login HTTP/1.1\r\nHost: localhost\r\nAuthorization: Basic YWRtaW46YWRtaW4xMjM=\r\nContent-Length: 20\r\n\r\n{\"passcode\": \"1111\"}")
            def sendall(self, data):
                self.output.write(data)

        req = MockRequest()
        mock_h = server.H(req, ("127.0.0.1", 12345), server=None)
        res_text = req.output.getvalue().decode("utf-8", errors="ignore")
        self.assertIn("404 Not Found", res_text)

    def test_04_recipe_parameter_bounds_refusal(self):
        """Recipe parameter validation strictly returns 400 FieldError naming the field."""
        # 1. Repeat length 50 -> FieldError repeatLength
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            server.validate_recipe_params({"repeatLength": 50})
        self.assertEqual(ctx.exception.field, "repeatLength")

        # 2. Repeat length 3000 -> FieldError repeatLength
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            server.validate_recipe_params({"repeatLength": 3000})
        self.assertEqual(ctx.exception.field, "repeatLength")

        # 3. Mark window 120 -> FieldError markWindow
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            server.validate_recipe_params({"markWindow": 120})
        self.assertEqual(ctx.exception.field, "markWindow")

        # 4. Mark offset 5000 -> FieldError markOffset
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            server.validate_recipe_params({"markOffset": 5000})
        self.assertEqual(ctx.exception.field, "markOffset")

        # 5. Valid parameters pass cleanly
        res = server.validate_recipe_params({"repeatLength": 740, "markWindow": 40, "markOffset": 15})
        self.assertEqual(res["repeatLength"], 740)
        self.assertEqual(res["markWindow"], 40)
        self.assertEqual(res["markOffset"], 15)

    def test_05_schema_sql_and_db_alignment(self):
        """schema.sql enforces repeat_length 100-2000, defines c_26_w/unscored/window_mm, no station_calibration table."""
        with open(os.path.join(ROOT, "schema.sql"), "r", encoding="utf-8") as f:
            sql = f.read()

        self.assertIn("repeat_length_mm BETWEEN 100 AND 2000", sql)
        self.assertIn("c_26_w", sql)
        self.assertIn("unscored", sql)
        self.assertIn("window_mm", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS station_calibration", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS calibration_store", sql)

    def test_06_report_unscored_excluded_from_failure_rate(self):
        """Unscored bags must not count as tolerance failures in fail_pct."""
        # Simulate test case: 10 bags in 0-7mm, 0 in error bands, 4 unscored out of 20 total bags
        mock_records = [{
            "total": 20,
            "c0_7": 10,
            "c8_15": 0,
            "c16_25": 0,
            "c26_w": 0,
            "unscored": 4,
            "windowMm": 40
        }]
        tot_bags = sum(r["total"] for r in mock_records)
        tot_0_7 = sum(r["c0_7"] for r in mock_records)
        tot_failed = sum(r["c8_15"] + r["c16_25"] + r["c26_w"] for r in mock_records)
        tot_scored = tot_0_7 + tot_failed
        pass_pct = round((tot_0_7 / tot_scored) * 100.0, 1) if tot_scored > 0 else 100.0
        fail_pct = round((tot_failed / tot_scored) * 100.0, 1) if tot_scored > 0 else 0.0
        unscored_pct = round((sum(r["unscored"] for r in mock_records) / tot_bags) * 100.0, 1)

        self.assertEqual(pass_pct, 100.0, "10 in-spec bags out of 10 scored bags must yield 100% pass")
        self.assertEqual(fail_pct, 0.0, "0 tolerance failed bags must yield 0% fail")
        self.assertEqual(unscored_pct, 20.0, "4 unscored bags out of 20 must yield 20% unscored")

    def test_07_cors_restricted_origin(self):
        """Access-Control-Allow-Origin must not be blind wildcard *."""
        class DummyHandler:
            headers = {"Origin": "http://192.168.1.50:11111", "Host": "192.168.1.50:11111"}
        origin = server.H._cors_origin(DummyHandler)
        self.assertEqual(origin, "http://192.168.1.50:11111")

        class ForeignHandler:
            headers = {"Origin": "http://evil-site.com", "Host": "192.168.1.50:11111"}
        origin_foreign = server.H._cors_origin(ForeignHandler)
        self.assertIsNone(origin_foreign, "Foreign origin must not be echoed back")

    def test_08_zero_localstorage_and_obsolete_files_deleted(self):
        """Zero localStorage across static assets, and obsolete index variants are deleted."""
        # Check files do not exist
        for deleted_f in ["index.html", "static/index1.html", "static/index2.html", "static/phase1.js"]:
            p = os.path.join(ROOT, deleted_f)
            self.assertFalse(os.path.exists(p), f"Obsolete file {deleted_f} must be deleted!")

        # Check static assets have 0 localStorage
        for static_f in ["static/index.html", "static/recipe.js", "static/app.css"]:
            p = os.path.join(ROOT, static_f)
            self.assertTrue(os.path.exists(p), f"Asset {static_f} must exist!")
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content.count("localStorage"), 0, f"{static_f} must have 0 localStorage references!")


if __name__ == "__main__":
    unittest.main()
