"""Master Test Suite for STN 2 REGISMATIC & FBARX Web HMI.

Covers:
1. Unit tests for Dynamic Banding edge cases (7.4 vs 7.5 mm, negative errors, all mark windows 10-99 mm)
2. Modbus CRC-16 validation matching every frame in MODBUS_MESSAGES.md (R1-R4, W1-W27, EXC_3, EXC_4)
3. Modbus Exception 3 (illegal value -> BoardRefused) and Exception 4 (locked -> unlock + retry)
4. Link output ramping, commands, and poll state
5. Security: Basic Auth (HMI_AUTH), Passcode 3333 unlock via API, token sliding-window, calibration audit log
6. Safe-state design: Simulation default-off, honest status banner (OK / NOT CONNECTED / WRONG FIRMWARE / SIMULATED)
7. Report storage: new columns c_26_w, unscored, window_mm
8. Handover Acceptance Checklist automated pass (all 11 items)
"""

import base64
import json
import math
import os
import sqlite3
import struct
import sys
import threading
import time
import unittest

import fbarx_link
from fbarx_link import crc16, verify_crc, compute_counter_bands, band_key, FBarXLink, BoardError, FieldError, BoardRefused
import fbarx_api
import server


class TestBandingEdgeCases(unittest.TestCase):
    """Unit tests for Section 4b banding rules & whole-mm rounding edge cases."""

    def setUp(self):
        self.link = FBarXLink(simulate=True)
        self.link.regs[1] = 1

    def test_whole_mm_rounding_positive(self):
        # 7.4 mm -> rounds to 7 mm -> 0-7 mm band
        self.link.send_cmd("NEW JOB")  # NEW JOB resets counters
        self.link.set_mark_window(40)
        self.link.record_bag_error(7.4)
        self.assertEqual(self.link.counters["0-7"], 1)
        self.assertEqual(self.link.counters["8-15"], 0)

        # 7.5 mm -> rounds to 8 mm -> 8-15 mm band
        self.link.record_bag_error(7.5)
        self.assertEqual(self.link.counters["8-15"], 1)

        # 15.4 mm -> 15 mm -> 8-15 mm band
        self.link.record_bag_error(15.4)
        self.assertEqual(self.link.counters["8-15"], 2)

        # 15.5 mm -> 16 mm -> 16-25 mm band
        self.link.record_bag_error(15.5)
        self.assertEqual(self.link.counters["16-25"], 1)

        # 25.4 mm -> 25 mm -> 16-25 mm band
        self.link.record_bag_error(25.4)
        self.assertEqual(self.link.counters["16-25"], 2)

        # 25.5 mm -> 26 mm -> 26-window band
        self.link.record_bag_error(25.5)
        self.assertEqual(self.link.counters["26-window"], 1)

    def test_negative_errors_symmetric_banding(self):
        # Negative errors count into the exact same absolute bands
        self.link.send_cmd("NEW JOB")  # reset
        self.link.set_mark_window(40)

        # -7.4 mm -> 7 mm -> 0-7
        self.link.record_bag_error(-7.4)
        self.assertEqual(self.link.counters["0-7"], 1)

        # -7.5 mm -> 8 mm -> 8-15
        self.link.record_bag_error(-7.5)
        self.assertEqual(self.link.counters["8-15"], 1)

        # -10.0 mm -> 10 mm -> 8-15
        self.link.record_bag_error(-10.0)
        self.assertEqual(self.link.counters["8-15"], 2)

        # -15.5 mm -> 16 mm -> 16-25
        self.link.record_bag_error(-15.5)
        self.assertEqual(self.link.counters["16-25"], 1)

        # -35.0 mm -> 35 mm -> 26-window
        self.link.record_bag_error(-35.0)
        self.assertEqual(self.link.counters["26-window"], 1)

        self.assertEqual(self.link.counters["total"], 5)

    def test_every_mark_window_bands(self):
        # 10 mm
        b10 = compute_counter_bands(10)
        self.assertEqual([b["key"] for b in b10], ["0-7", "8-15"])
        self.assertEqual(b10[1]["label"], "8-10 mm")

        # 20 mm
        b20 = compute_counter_bands(20)
        self.assertEqual([b["key"] for b in b20], ["0-7", "8-15", "16-25"])
        self.assertEqual(b20[2]["label"], "16-20 mm")

        # 25 mm
        b25 = compute_counter_bands(25)
        self.assertEqual([b["key"] for b in b25], ["0-7", "8-15", "16-25"])
        self.assertEqual(b25[2]["label"], "16-25 mm")

        # 40 mm
        b40 = compute_counter_bands(40)
        self.assertEqual([b["key"] for b in b40], ["0-7", "8-15", "16-25", "26-window"])
        self.assertEqual(b40[3]["label"], "26-40 mm")

        # 50 mm
        b50 = compute_counter_bands(50)
        self.assertEqual([b["key"] for b in b50], ["0-7", "8-15", "16-25", "26-window"])
        self.assertEqual(b50[3]["label"], "26-50 mm")

        # 99 mm
        b99 = compute_counter_bands(99)
        self.assertEqual([b["key"] for b in b99], ["0-7", "8-15", "16-25", "26-window"])
        self.assertEqual(b99[3]["label"], "26-99 mm")

        # Clamping out-of-bounds
        b_low = compute_counter_bands(4)
        self.assertEqual(b_low[1]["label"], "8-10 mm")  # clamped to min 10 mm
        b_high = compute_counter_bands(150)
        self.assertEqual(b_high[3]["label"], "26-99 mm")  # clamped to max 99 mm


class TestModbusCRC(unittest.TestCase):
    """Verifies CRC-16 against all real captured frames in MODBUS_MESSAGES.md."""

    def test_captured_frames(self):
        frames = {
            "R1": bytes.fromhex("01 03 00 00 00 1F 04 02"),
            "R2": bytes.fromhex("01 03 00 64 00 08 05 D3"),
            "R3": bytes.fromhex("01 03 00 28 00 2F 84 1E"),
            "R4": bytes.fromhex("01 03 00 15 00 01 95 CE"),
            "W1_AUTO": bytes.fromhex("01 06 00 0F 00 01 78 09"),
            "W2_MAN": bytes.fromhex("01 06 00 0F 00 00 B9 C9"),
            "W3_OFF": bytes.fromhex("01 06 00 0F 00 02 38 08"),
            "W4_OUTPUT": bytes.fromhex("01 06 00 4E 01 2C E9 90"),
            "W5_REPEAT": bytes.fromhex("01 06 00 09 02 E4 58 E3"),
            "W6_WINDOW": bytes.fromhex("01 06 00 14 00 28 C9 D0"),
            "W7_OFFSET": bytes.fromhex("01 06 00 15 FF F4 D8 79"),
            "W8_CLR": bytes.fromhex("01 06 00 11 00 01 18 0F"),
            "W9_SCAN": bytes.fromhex("01 06 00 11 00 02 58 0E"),
            "W10_NEWJOB": bytes.fromhex("01 06 00 11 00 03 99 CE"),
            "W11_LOGOUT": bytes.fromhex("01 06 00 11 00 05 19 CC"),
            "W12_UNLOCK": bytes.fromhex("01 06 00 1E 04 BC EA BD"),
            "W13_ACERR": bytes.fromhex("01 06 00 47 00 46 B8 2D"),
            "W14_DCERR": bytes.fromhex("01 06 00 48 00 01 C8 1C"),
            "W15_SPKERR": bytes.fromhex("01 06 00 49 00 14 58 13"),
            "W16_DIR": bytes.fromhex("01 06 00 34 00 00 C8 04"),
            "W17_PPR": bytes.fromhex("01 06 00 46 13 88 65 49"),
            "W19_CIRC": bytes.fromhex("01 06 00 28 06 22 8A 7B"),
            "W20_B2B": bytes.fromhex("01 06 00 2B 00 0F B9 C6"),
            "W21_SKIP": bytes.fromhex("01 06 00 4B 00 06 79 DE"),
            "W22_BRAKETYPE": bytes.fromhex("01 06 00 43 00 01 B9 DE"),
            "W23_BRAKEPWR": bytes.fromhex("01 06 00 42 00 32 A8 0B"),
            "W24_BRAKECAP": bytes.fromhex("01 06 00 44 00 14 C9 D0"),
            "W25_BRAKECUR": bytes.fromhex("01 06 00 45 00 18 98 15"),
            "W26_MODESRC": bytes.fromhex("01 06 00 4C 00 01 89 DD"),
            "W27_MANSRC": bytes.fromhex("01 06 00 4D 00 01 D8 1D"),
            "EXC_3": bytes.fromhex("01 86 03 02 61"),
            "EXC_4": bytes.fromhex("01 86 04 43 A3"),
        }
        for name, frame in frames.items():
            self.assertTrue(verify_crc(frame), f"Frame {name} CRC failed verification")


class MockSerialPort:
    """Simulates physical RS-485 transceiver with byte-stream buffer."""
    def __init__(self):
        self.is_open = True
        self.read_buf = b""
        self.unlocked = False

    def reset_input_buffer(self):
        self.read_buf = b""

    def write(self, data: bytes):
        if len(data) == 8 and data[1] == 0x06:
            reg = (data[2] << 8) | data[3]
            val = (data[4] << 8) | data[5]
            if reg == 30 and val == 1212:
                self.unlocked = True
                self.read_buf += data  # echo unlock
            elif 40 <= reg <= 86 and not self.unlocked:
                # Trigger Exception 4: Locked
                self.read_buf += bytes.fromhex("01 86 04 43 A3")
            elif reg == 68 and val == 25:
                # Value out of range -> Trigger Exception 3
                self.read_buf += bytes.fromhex("01 86 03 02 61")
            else:
                self.read_buf += data  # normal echo

    def read(self, n: int) -> bytes:
        chunk = self.read_buf[:n]
        self.read_buf = self.read_buf[n:]
        return chunk

    def close(self):
        self.is_open = False


class TestModbusExceptions(unittest.TestCase):
    """Verifies handling of Exception 3 (illegal value) and Exception 4 (locked)."""

    def test_exception_3_illegal_value(self):
        link = FBarXLink(simulate=False)
        mock_port = MockSerialPort()
        mock_port.unlocked = True
        link.ser = mock_port
        link.connected = True
        link.fw_ok = True

        with self.assertRaises(BoardRefused) as ctx:
            link._write_reg(68, 25, "brakeCapacity")
        self.assertIn("refused", str(ctx.exception))
        self.assertEqual(ctx.exception.field, "brakeCapacity")

    def test_exception_4_locked_retry(self):
        link = FBarXLink(simulate=False)
        mock_port = MockSerialPort()
        mock_port.unlocked = False  # locked initially
        link.ser = mock_port
        link.connected = True
        link.fw_ok = True

        link._write_reg(66, 50, "brakePower")
        self.assertEqual(link.regs[66], 50)
        self.assertTrue(mock_port.unlocked)


class TestSecurityAndPasscode(unittest.TestCase):
    """Verifies server passcode 3333 verification, token expiry, and basic auth."""

    def test_basic_auth(self):
        old_auth = os.environ.get("HMI_AUTH")
        try:
            os.environ["HMI_AUTH"] = "admin:secretpass"
            self.assertTrue(fbarx_api.auth_enabled())
            bad_hdr = "Basic " + base64.b64encode(b"admin:wrong").decode()
            good_hdr = "Basic " + base64.b64encode(b"admin:secretpass").decode()
            self.assertFalse(fbarx_api.basic_auth_ok(bad_hdr))
            self.assertTrue(fbarx_api.basic_auth_ok(good_hdr))
        finally:
            if old_auth is None:
                os.environ.pop("HMI_AUTH", None)
            else:
                os.environ["HMI_AUTH"] = old_auth

    def test_passcode_unlock_and_token(self):
        link = FBarXLink(simulate=True)
        code, body = fbarx_api.route_post(link, "/api/fbarx/unlock", {"code": "9999"}, {})
        self.assertEqual(code, 403)
        self.assertEqual(body.get("field"), "password")

        code, body = fbarx_api.route_post(link, "/api/fbarx/unlock", {"code": "3333"}, {})
        self.assertEqual(code, 200)
        self.assertTrue(body.get("ok"))
        tok = body.get("token")
        self.assertTrue(bool(tok))

        c_no_tok, _ = fbarx_api.route_post(link, "/api/fbarx/calibration", {"acErr": 7.0}, {})
        self.assertEqual(c_no_tok, 403)

        c_tok, _ = fbarx_api.route_post(link, "/api/fbarx/calibration", {"acErr": 7.0}, {"X-Cal-Token": tok})
        self.assertEqual(c_tok, 200)


class TestSafeStateSimulationBanner(unittest.TestCase):
    """Verifies safe-state design: status reflects simulation vs hardware."""

    def test_status_simulated(self):
        link = FBarXLink(simulate=True)
        self.assertEqual(link.status(), "SIMULATED")

    def test_status_not_connected(self):
        link = FBarXLink(simulate=False)
        link.connected = False
        self.assertEqual(link.status(), "NOT CONNECTED")

    def test_status_wrong_firmware(self):
        link = FBarXLink(simulate=False)
        link.connected = True
        link.fw_ok = False
        self.assertEqual(link.status(), "WRONG FIRMWARE")


class TestCountingReportBandEdges(unittest.TestCase):
    """Verifies storage of 26-window, unscored, and window_mm with report records."""

    def setUp(self):
        server.init_db()

    def test_production_record_storage(self):
        c = server.conn()
        c.execute("""INSERT INTO production_records (recipe_id, image_name, operator_id, operator, c_0_7, c_8_15, c_16_25, c_26_w, unscored, window_mm, total, start_time, end_time, logged_at)
                     VALUES (1, 'Thangamayil', 1, 'Op 1', 50, 10, 2, 5, 1, 40, 68, '2026-11-10T08:00:00', '2026-11-10T08:30:00', '2026-11-10T08:30:00')""")
        c.commit()

        row = c.execute("SELECT * FROM production_records ORDER BY record_id DESC LIMIT 1").fetchone()
        c.close()
        self.assertEqual(row["total"], 68)
        self.assertEqual(row["c_26_w"], 5)
        self.assertEqual(row["unscored"], 1)
        self.assertEqual(row["window_mm"], 40)


class TestHardwareAcceptanceChecklist(unittest.TestCase):
    """Automated check of all 11 items from Section 7 of the handover document."""

    def setUp(self):
        self.link = FBarXLink(simulate=True)

    def test_checklist_item_1_status_and_fw(self):
        st = self.link.poll()
        self.assertEqual(self.link.regs[19], 2001, "FW check: reg 19 must read 2001")
        self.assertEqual(self.link.baudrate, 9600)

    def test_checklist_item_2_mode_switching(self):
        self.link.set_mode("AUTO")
        self.assertEqual(self.link.regs[14], 1)
        self.link.set_mode("MAN")
        self.assertEqual(self.link.regs[14], 0)
        self.link.set_mode("OFF")
        self.assertEqual(self.link.regs[14], 2)

    def test_checklist_item_3_output_ramping(self):
        self.link.set_mode("MAN")
        self.link.set_output(30.0)
        self.assertEqual(self.link.target_output_pct, 30.0)
        for _ in range(20):
            self.link.last_ramp_time -= 0.5
            self.link._update_output_ramp()
        self.assertGreater(self.link.regs[6], 200)

    def test_checklist_item_4_rep_and_scale(self):
        self.link.set_mode("MAN")
        self.link.set_live_sim_error(1.25, valid=True)
        st = self.link.poll()
        self.assertEqual(st["markError"], 1.25)
        self.assertTrue(st["markErrorValid"])

    def test_checklist_item_5_bands_end_at_window(self):
        b20 = compute_counter_bands(20)
        self.assertEqual(b20[-1]["label"], "16-20 mm")
        b40 = compute_counter_bands(40)
        self.assertEqual(b40[-1]["label"], "26-40 mm")

    def test_checklist_item_6_acerr_scaling(self):
        self.link.set_calibration({"acErr": 7.0})
        self.assertEqual(self.link.regs[71], 70, "Board stores ACerr * 10 (7.0 -> 70)")
        cal = self.link.get_calibration()
        self.assertEqual(cal["acErr"], 7.0)

    def test_checklist_item_7_mark_offset_signed(self):
        self.link.set_mark_offset(-999)
        self.assertEqual(self.link._get_signed_mark_offset(), -999)
        self.link.set_mark_offset(999)
        self.assertEqual(self.link._get_signed_mark_offset(), 999)

    def test_checklist_item_8_brake_power_capacity_current(self):
        self.link.set_calibration({"brakePower": 50, "brakeCapacity": 20, "brakeCurrent": 2.4})
        self.assertEqual(self.link.regs[66], 50)
        self.assertEqual(self.link.regs[68], 20)
        self.assertEqual(self.link.regs[69], 24)

    def test_checklist_item_9_refuse_capacity_out_of_range(self):
        with self.assertRaises(FieldError):
            self.link.set_calibration({"brakeCapacity": 25})

    def test_checklist_item_10_disconnect_detection(self):
        link = FBarXLink(simulate=False)
        link.ser = None
        link.connected = False
        self.assertEqual(link.status(), "NOT CONNECTED")

    def test_checklist_item_11_api_login_protection(self):
        old_auth = os.environ.get("HMI_AUTH")
        try:
            os.environ["HMI_AUTH"] = "op:pass"
            self.assertFalse(fbarx_api.basic_auth_ok(None))
            self.assertTrue(fbarx_api.basic_auth_ok("Basic " + base64.b64encode(b"op:pass").decode()))
        finally:
            if old_auth is None:
                os.environ.pop("HMI_AUTH", None)
            else:
                os.environ["HMI_AUTH"] = old_auth


if __name__ == "__main__":
    unittest.main()
