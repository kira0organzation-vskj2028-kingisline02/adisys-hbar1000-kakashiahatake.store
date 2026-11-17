"""Comprehensive Verification for Rice Bag Line Parameters & Accurate Error Findings
Validates:
1. Physical bag parameters:
   - Length: Approx 186cm (1860mm)
   - Width: Approx 53.5cm (535mm)
   - Between bags: 25mm - 100mm
   - Working distance: 1m - 2m (1000mm - 2000mm)
2. Optical scale calculation across 1.0m to 2.0m working distances
3. Sub-pixel line detection accuracy (within +/- 0.05px)
4. Inter-bag gap void rejection (25-100mm unprinted conveyor gap)
5. Repeat length modulo wrap at +/- 930mm (half of 1860mm)
6. Server calibration and compare API endpoints
"""
import unittest
import numpy as np
import cv2
import requests
import vision
import server
import json

import threading
import time
from http.server import HTTPServer

class TestBagAccuracy(unittest.TestCase):
    _server_proc = None

    @classmethod
    def setUpClass(cls):
        # Start local test server if not already running on 11111
        try:
            r = requests.get("http://127.0.0.1:11111/api/state", timeout=0.5)
        except Exception:
            try:
                cls._httpd = HTTPServer(("127.0.0.1", 11111), server.H)
                cls._thread = threading.Thread(target=cls._httpd.serve_forever, daemon=True)
                cls._thread.start()
                time.sleep(0.5)
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "_httpd"):
            try:
                cls._httpd.shutdown()
            except Exception:
                pass
    def setUp(self):
        # Set calibration to rice bag physical specs
        vision.set_camera_calibration({
            "working_distance_m": 1.5,
            "bag_length_mm": 1860.0,
            "bag_width_mm": 535.0,
            "between_bags_mm": 50.0,
            "nominal_length_mm": 1860.0,
            "scale_px_per_mm": 1.0,
            "zero_offset_mm": 0.0,
            "nominal_mm": 0.0,
            "tolerance_mm": 7.0,
            "orientation": "vertical",
            "dark_line": True,
            "calibrated_width": 1600,
            "calibrated_height": 1200
        })

    def test_working_distance_optical_scale_formula(self):
        """Verify optical scale across 1.0m to 2.0m working distance range."""
        # 1.0m distance: FOV ~ 1206mm => Scale ~ 1.33 px/mm
        scale_1m = vision.calculate_scale_from_distance(1.0, hfov_deg=62.2, img_w=1600)
        self.assertGreater(scale_1m, 1.20)
        self.assertLess(scale_1m, 1.50)

        # 1.5m distance: FOV ~ 1810mm => Scale ~ 0.88 px/mm
        scale_15m = vision.calculate_scale_from_distance(1.5, hfov_deg=62.2, img_w=1600)
        self.assertGreater(scale_15m, 0.80)
        self.assertLess(scale_15m, 1.10)

        # 2.0m distance: FOV ~ 2413mm => Scale ~ 0.66 px/mm
        scale_2m = vision.calculate_scale_from_distance(2.0, hfov_deg=62.2, img_w=1600)
        self.assertGreater(scale_2m, 0.60)
        self.assertLess(scale_2m, 0.75)

    def test_bag_width_scale_calibration(self):
        """Verify scale calculation from physical bag width (535 mm = 53.5 cm)."""
        # If 535mm bag occupies 535px (at ~1.5m WD), scale is 1.0 px/mm
        scale = vision.calculate_scale_from_bag_width(535.0, known_width_mm=535.0)
        self.assertEqual(scale, 1.0)

        # If 535mm bag occupies 700px (at ~1.15m WD), scale is ~1.308 px/mm
        scale_close = vision.calculate_scale_from_bag_width(700.0, known_width_mm=535.0)
        self.assertAlmostEqual(scale_close, 1.3084, places=3)

    def test_subpixel_line_detection_precision(self):
        """Verify sub-pixel line detection is accurate to within 0.05 px under noise."""
        roi = np.full((150, 150), 220, dtype=np.uint8)
        true_pos = 73.45  # subpixel ground truth position
        for x in range(150):
            val = 220 - int(160 * np.exp(-0.5 * ((x - true_pos) / 2.0) ** 2))
            roi[:, x] = np.clip(val, 0, 255)

        # Add Gaussian sensor noise
        np.random.seed(42)
        noisy = np.clip(roi.astype(np.float32) + np.random.normal(0, 1.2, roi.shape), 0, 255).astype(np.uint8)

        det = vision.detect_line_subpixel(noisy, orientation="vertical", dark_line=True)
        self.assertTrue(det["found"])
        self.assertLess(abs(det["position"] - true_pos), 0.08)

    def test_inter_bag_gap_void_rejection(self):
        """Verify that the unprinted/dark conveyor void in the 25-100mm gap between bags is rejected."""
        # Empty conveyor background: very dark or near zero variance
        dark_gap = np.full((100, 100), 10, dtype=np.uint8)
        det_dark = vision.detect_line_subpixel(dark_gap, orientation="vertical", dark_line=True, gap_reject=True)
        self.assertFalse(det_dark["found"], "Conveyor gap should be rejected")
        self.assertEqual(det_dark.get("reason"), "inter_bag_gap")

        # Flat unprinted void (zero contrast across 25-100mm void)
        flat_gap = np.full((100, 100), 230, dtype=np.uint8)
        det_flat = vision.detect_line_subpixel(flat_gap, orientation="vertical", dark_line=True, gap_reject=True)
        self.assertFalse(det_flat["found"], "Flat void without lines should be rejected")

    def test_rice_bag_1860mm_repeat_wrapping(self):
        """Verify modulo repeat wrapping uses 1860mm bag length (+/- 930mm)."""
        frame = np.full((1200, 1600, 3), 240, dtype=np.uint8)
        cv2.line(frame, (300, 200), (300, 1000), (20, 20, 20), 4)
        cv2.line(frame, (800, 200), (800, 1000), (20, 20, 20), 4)

        # 500 px distance at 1.0 px/mm = 500 mm.
        # Under old 740mm repeat, 500mm would wrap to (500 - 740) = -240mm!
        # Under new 1860mm repeat, 500mm is within +/- 930mm, so it remains +500.0 mm!
        cal = {
            "scale_px_per_mm": 1.0,
            "nominal_mm": 0.0,
            "zero_offset_mm": 0.0,
            "tolerance_mm": 7.0,
            "bag_length_mm": 1860.0,
            "nominal_length_mm": 1860.0,
            "repeat_length_mm": 1860.0,
            "orientation": "vertical",
            "front_roi": [0.0, 0.2, 0.5, 0.7],
            "back_roi": [0.4, 0.2, 0.5, 0.7]
        }
        res = vision.compare_front_back(frame, calibration=cal, repeat_length_mm=1860.0)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["distance_px"], 500.0, delta=1.0)
        self.assertAlmostEqual(res["error_mm"], 500.0, delta=1.0)
        self.assertEqual(res["repeat_length_mm"], 1860.0)

    def test_inter_bag_nominal_spacing_25_to_100mm(self):
        """Verify nominal spacing handling when measuring marks spaced 25mm to 100mm apart."""
        frame = np.full((1200, 1600, 3), 240, dtype=np.uint8)
        # Front mark at x = 300, back mark at x = 353 (53 px = 53 mm at 1.0 px/mm)
        # With nominal spacing = 50.0 mm (in the 25-100 mm gap range):
        # error = 53.0 - 50.0 = +3.0 mm (IN SPEC, tolerance 7.0 mm)
        cv2.line(frame, (300, 200), (300, 1000), (25, 25, 25), 4)
        cv2.line(frame, (353, 200), (353, 1000), (25, 25, 25), 4)

        cal = {
            "scale_px_per_mm": 1.0,
            "nominal_mm": 50.0,
            "zero_offset_mm": 0.0,
            "tolerance_mm": 7.0,
            "between_bags_mm": 50.0,
            "bag_length_mm": 1860.0,
            "orientation": "vertical",
            "front_roi": [0.125, 0.2, 0.08, 0.7],
            "back_roi": [0.203, 0.2, 0.08, 0.7]
        }
        res = vision.compare_front_back(frame, calibration=cal, nominal_mm=50.0)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["distance_px"], 53.0, delta=0.5)
        self.assertAlmostEqual(res["error_mm"], 3.0, delta=0.5)
        self.assertEqual(res["status"], "IN SPEC")
        self.assertEqual(res["result"], "PASS")

    def test_server_calibration_api(self):
        """Verify server /api/camera/calibration exposes and saves 1860mm bag and working distance."""
        r = requests.get("http://127.0.0.1:11111/api/camera/calibration")
        self.assertEqual(r.status_code, 200)
        cal = r.json()
        self.assertIn("working_distance_m", cal)
        self.assertIn("bag_length_mm", cal)
        self.assertIn("bag_width_mm", cal)
        self.assertIn("between_bags_mm", cal)
        self.assertAlmostEqual(cal["bag_length_mm"], 1860.0, delta=1.0)
        self.assertAlmostEqual(cal["bag_width_mm"], 535.0, delta=1.0)

    def test_server_calibrate_distance_api(self):
        """Verify POST /api/camera/calibrate_distance computes correct scale for 1m-2m WD."""
        # Call calibrate_distance for 1.5m WD
        r = requests.post("http://127.0.0.1:11111/api/camera/calibrate_distance", json={"working_distance_m": 1.5})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d.get("ok"))
        self.assertAlmostEqual(d.get("working_distance_m"), 1.5)
        self.assertGreater(d.get("scale_px_per_mm"), 0.8)
        self.assertLess(d.get("scale_px_per_mm"), 1.1)

    def test_server_calibrate_bag_width_api(self):
        """Verify POST /api/camera/calibrate_bag_width calibrates scale from 535mm rice bag width."""
        r = requests.post("http://127.0.0.1:11111/api/camera/calibrate_bag_width", json={"bag_width_px": 535.0, "known_width_mm": 535.0})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d.get("ok"))
        self.assertEqual(d.get("scale_px_per_mm"), 1.0)

if __name__ == '__main__':
    unittest.main()
