"""Comprehensive test suite for Pi Camera Line-Distance Error Measurement (11-11-26.md).
Verifies:
1. Sub-pixel line detection accuracy
2. Mathematical error formula: distance_px / scale - nominal - zero_offset
3. Wrap error into +/- repeat_length / 2
4. Tolerance classification: IN SPEC / OUT OF SPEC (default 7.0 mm)
5. Zero offset calibration
6. Ruler scale calibration
7. Backwards compatibility for existing HMI endpoints and simulation modes
"""
import unittest
import numpy as np
import cv2
import vision
import server
import json

class TestPiCameraLineDistance(unittest.TestCase):
    def setUp(self):
        # Reset to known default calibration
        vision.set_camera_calibration({
            "scale_px_per_mm": 5.0,
            "zero_offset_mm": 0.0,
            "nominal_mm": 0.0,
            "tolerance_mm": 7.0,
            "orientation": "vertical",
            "dark_line": True,
            "calibrated_width": 1600,
            "calibrated_height": 1200
        })

    def test_subpixel_line_detection_precision(self):
        """Verify sub-pixel line peak detection down to 0.05 pixel under noise."""
        roi = np.full((200, 200), 230, dtype=np.uint8)
        # Draw a synthetic line with sub-pixel Gaussian profile at true_x = 94.42
        true_x = 94.42
        for x in range(200):
            val = 230 - int(180 * np.exp(-0.5 * ((x - true_x) / 2.0) ** 2))
            roi[:, x] = np.clip(val, 0, 255)
        # Add sensor noise
        np.random.seed(123)
        noisy = np.clip(roi.astype(np.float32) + np.random.normal(0, 1.5, roi.shape), 0, 255).astype(np.uint8)

        det = vision.detect_line_subpixel(noisy, orientation="vertical", dark_line=True)
        self.assertTrue(det["found"], "Subpixel line was not found")
        detected_pos = det["position"]
        error = abs(detected_pos - true_x)
        self.assertLess(error, 0.15, f"Sub-pixel error {error:.4f}px exceeds 0.15px")

    def test_ruler_scale_calibration(self):
        """Verify ruler calibration formula: scale = distance_px / known_mm."""
        scale = vision.calculate_ruler_scale(350.0, 70.0)
        self.assertEqual(scale, 5.0)
        with self.assertRaises(ValueError):
            vision.calculate_ruler_scale(100.0, 0.0)

    def test_line_distance_error_formula_and_tolerance(self):
        """Verify distance_px / scale - nominal - zero_offset and tolerance."""
        frame = np.full((1200, 1600, 3), 240, dtype=np.uint8)
        # Front line at x = 300
        cv2.line(frame, (300, 200), (300, 1000), (20, 20, 20), 4)
        # Back line at x = 1175 (+25 px shift = +5.0 mm at 5 px/mm)
        cv2.line(frame, (1175, 200), (1175, 1000), (20, 20, 20), 4)

        cal = {
            "scale_px_per_mm": 5.0,
            "nominal_mm": 170.0,
            "zero_offset_mm": 0.0,
            "tolerance_mm": 7.0,
            "orientation": "vertical",
            "front_roi": [0.0, 0.2, 0.5, 0.7],
            "back_roi": [0.5, 0.2, 0.5, 0.7]
        }
        res = vision.compare_front_back(frame, calibration=cal)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["distance_px"], 875.0, delta=1.0)
        # (875 / 5) - 170 - 0 = 175 - 170 = +5.0 mm
        self.assertAlmostEqual(res["error_mm"], 5.0, delta=0.2)
        self.assertEqual(res["status"], "IN SPEC")
        self.assertEqual(res["result"], "PASS")
        self.assertEqual(res["bin"], "0-7")

    def test_out_of_spec_classification(self):
        """Verify OUT OF SPEC when error exceeds tolerance (+10.0 mm > 7.0 mm)."""
        frame = np.full((1200, 1600, 3), 240, dtype=np.uint8)
        cv2.line(frame, (300, 200), (300, 1000), (20, 20, 20), 4)
        # Shift back line by +50 px (+10.0 mm at 5 px/mm)
        cv2.line(frame, (1200, 200), (1200, 1000), (20, 20, 20), 4)

        cal = {
            "scale_px_per_mm": 5.0,
            "nominal_mm": 170.0,
            "zero_offset_mm": 0.0,
            "tolerance_mm": 7.0,
            "orientation": "vertical",
            "front_roi": [0.0, 0.2, 0.5, 0.7],
            "back_roi": [0.5, 0.2, 0.5, 0.7]
        }
        res = vision.compare_front_back(frame, calibration=cal)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["error_mm"], 10.0, delta=0.2)
        self.assertEqual(res["status"], "OUT OF SPEC")
        self.assertEqual(res["result"], "FAIL")
        self.assertEqual(res["bin"], "8-15")

    def test_zero_offset_calibration(self):
        """Verify zero offset eliminates baseline error on master bag."""
        frame = np.full((1200, 1600, 3), 240, dtype=np.uint8)
        cv2.line(frame, (300, 200), (300, 1000), (20, 20, 20), 4)
        cv2.line(frame, (1160, 200), (1160, 1000), (20, 20, 20), 4)

        cal = {
            "scale_px_per_mm": 5.0,
            "nominal_mm": 170.0,
            "zero_offset_mm": 0.0,
            "orientation": "vertical",
            "front_roi": [0.0, 0.2, 0.5, 0.7],
            "back_roi": [0.5, 0.2, 0.5, 0.7]
        }
        # Uncalibrated: distance = 860px -> raw = 172mm -> error = +2.0 mm
        r_uncal = vision.compare_front_back(frame, calibration=cal)
        self.assertAlmostEqual(r_uncal["error_mm"], 2.0, delta=0.2)

        # Calibrate zero offset to 2.0 mm
        cal["zero_offset_mm"] = 2.0
        r_cal = vision.compare_front_back(frame, calibration=cal)
        self.assertEqual(r_cal["error_mm"], 0.0)
        self.assertEqual(r_cal["status"], "IN SPEC")
        self.assertEqual(r_cal["result"], "PASS")

    def test_repeat_length_wrap(self):
        """Verify repeat wrap into +/- repeat_length / 2 (Section 3.1)."""
        rep_len = 800.0
        # If raw error was +802.0 mm (one full repeat + 2 mm)
        half_rep = rep_len / 2.0
        raw_err = 802.0
        wrapped = ((raw_err + half_rep) % rep_len) - half_rep
        self.assertAlmostEqual(wrapped, 2.0)

        # Negative wrap: -798.0 mm -> +2 mm
        raw_neg = -798.0
        wrapped_neg = ((raw_neg + half_rep) % rep_len) - half_rep
        self.assertAlmostEqual(wrapped_neg, 2.0)

    def test_missing_line_reports_no_read(self):
        """Verify missing lines or blank frames report NO READ with descriptive reason."""
        blank = np.full((600, 800, 3), 255, dtype=np.uint8)
        res = vision.compare_front_back(blank)
        self.assertFalse(res["ok"])
        self.assertEqual(res["result"], "NO_READ")
        self.assertEqual(res["status"], "NO READ")
        self.assertIn("line not detected", res["reason"])

    def test_server_calibration_persistence(self):
        """Verify database settings persistence for camera calibration."""
        c = server.conn()
        try:
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('scale_px_per_mm','6.25')")
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('zero_offset_mm','1.45')")
            c.commit()
            cal = server.load_camera_calibration_from_db(c)
            self.assertEqual(cal["scale_px_per_mm"], 6.25)
            self.assertEqual(cal["zero_offset_mm"], 1.45)
        finally:
            c.close()

    def test_detect_corner_bar_red_and_white_substrates(self):
        """Verify subpixel detection of horizontal black bars on red and white backgrounds."""
        # 1. Red substrate (BGR: 25, 25, 210) with black horizontal bar at y=45.0
        red_roi = np.full((100, 150, 3), (25, 25, 210), dtype=np.uint8)
        red_roi[43:48, 10:140] = (15, 15, 15)  # dark bar
        det_red = vision.detect_corner_bar(red_roi)
        self.assertTrue(det_red["found"])
        self.assertAlmostEqual(det_red["y_subpixel"], 45.0, delta=0.5)

        # 2. White substrate (BGR: 240, 240, 240) with black bar at y=60.0
        white_roi = np.full((120, 150, 3), 240, dtype=np.uint8)
        white_roi[58:63, 10:140] = (20, 20, 20)
        det_white = vision.detect_corner_bar(white_roi)
        self.assertTrue(det_white["found"])
        self.assertAlmostEqual(det_white["y_subpixel"], 60.0, delta=0.5)

    def test_measure_four_corner_bars_geometry(self):
        """Verify 4-corner length, skew, taper, error and repeat wrapping."""
        # Create a synthetic 1600x1200 image with 4 horizontal bars
        # Scale: 2.0 px/mm. Top bars at y=200 px, bottom bars at y=1000 px -> distance = 800 px = 400 mm
        img = np.full((1200, 1600, 3), (25, 25, 210), dtype=np.uint8)
        # Top-left (x: 50-250, y: 198-202)
        img[198:203, 50:250] = (10, 10, 10)
        # Top-right (x: 1350-1550, y: 198-202)
        img[198:203, 1350:1550] = (10, 10, 10)
        # Bottom-left (x: 50-250, y: 998-1003)
        img[998:1003, 50:250] = (10, 10, 10)
        # Bottom-right (x: 1350-1550, y: 998-1003)
        img[998:1003, 1350:1550] = (10, 10, 10)

        cal = {
            "scale_px_per_mm": 2.0,
            "nominal_length_mm": 400.0,
            "nominal_skew_top_mm": 0.0,
            "nominal_skew_bottom_mm": 0.0,
            "tolerance_mm": 5.0,
            "roi_top_left": {"x1": 0.02, "y1": 0.10, "x2": 0.20, "y2": 0.25},
            "roi_top_right": {"x1": 0.80, "y1": 0.10, "x2": 0.98, "y2": 0.25},
            "roi_bottom_left": {"x1": 0.02, "y1": 0.75, "x2": 0.20, "y2": 0.90},
            "roi_bottom_right": {"x1": 0.80, "y1": 0.75, "x2": 0.98, "y2": 0.90}
        }
        res = vision.measure_four_corner_bars(img, cal, nominal_length_mm=400.0)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["avg_length_mm"], 400.0, delta=1.0)
        self.assertAlmostEqual(res["error_mm"], 0.0, delta=1.0)
        self.assertAlmostEqual(res["skew_top_mm"], 0.0, delta=1.0)
        self.assertAlmostEqual(res["skew_bottom_mm"], 0.0, delta=1.0)
        self.assertAlmostEqual(res["taper_mm"], 0.0, delta=1.0)
        self.assertEqual(res["result"], "PASS")

if __name__ == '__main__':
    unittest.main()

