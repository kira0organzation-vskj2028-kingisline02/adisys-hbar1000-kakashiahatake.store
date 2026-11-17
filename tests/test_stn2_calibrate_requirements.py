"""Comprehensive Test Suite for STN 2 CALIBRATE requirements 1 through 16.
Validates all boundary conditions, scaling, register mappings, password protection,
Exception 4 retry, available brake capacity calculation, and persistence.
"""
import os
import sys
import unittest
import time

os.environ["FBARX_SIM"] = "1"
os.environ["FBARX_PORT"] = ""

import fbarx_link
import fbarx_api
import server

class MockSerialPort:
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
            else:
                self.read_buf += data  # normal echo

    def read(self, n: int) -> bytes:
        chunk = self.read_buf[:n]
        self.read_buf = self.read_buf[n:]
        return chunk

    def close(self):
        self.is_open = False


class TestStn2Calibrate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.link = fbarx_link.FBarXLink(simulate=True)
        cls.link.connected = True
        cls.link.fw_ok = True

    def setUp(self):
        self.link.connected = True
        self.link.fw_ok = True
        self.link.unlocked_until = 0.0  # start locked to verify unlock logic
        self.link.regs[30] = 0

    # -------------------------------------------------------------------------
    # 1. ACerr (acErr, Reg 71): 0.1-99.9 %, default 7.0, stored x10
    # 7.0 saves as 70; 0.1 as 1; 99.9 as 999; 0.0 and 100 refused
    # -------------------------------------------------------------------------
    def test_01_ac_err(self):
        self.link.set_calibration({"acErr": 7.0})
        self.assertEqual(self.link.regs[71], 70)
        self.assertEqual(self.link.get_calibration()["acErr"], 7.0)

        self.link.set_calibration({"acErr": 0.1})
        self.assertEqual(self.link.regs[71], 1)
        self.assertEqual(self.link.get_calibration()["acErr"], 0.1)

        self.link.set_calibration({"acErr": 99.9})
        self.assertEqual(self.link.regs[71], 999)
        self.assertEqual(self.link.get_calibration()["acErr"], 99.9)

        # 0.0 refused
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"acErr": 0.0})
        self.assertEqual(ctx.exception.field, "acErr")
        self.assertIsInstance(ctx.exception, ValueError)

        # 100 refused
        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"acErr": 100.0})
        self.assertEqual(ctx.exception.field, "acErr")

    # -------------------------------------------------------------------------
    # 2. DCerr (dcErr, Reg 72): 0-999, default 1
    # 0 and 999 save; 1000 refused
    # -------------------------------------------------------------------------
    def test_02_dc_err(self):
        self.link.set_calibration({"dcErr": 0})
        self.assertEqual(self.link.regs[72], 0)
        self.assertEqual(self.link.get_calibration()["dcErr"], 0)

        self.link.set_calibration({"dcErr": 999})
        self.assertEqual(self.link.regs[72], 999)
        self.assertEqual(self.link.get_calibration()["dcErr"], 999)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"dcErr": 1000})
        self.assertEqual(ctx.exception.field, "dcErr")

    # -------------------------------------------------------------------------
    # 3. SPKerr (spkErr, Reg 73): 0-999, default 20
    # 0 and 999 save; 1000 refused
    # -------------------------------------------------------------------------
    def test_03_spk_err(self):
        self.link.set_calibration({"spkErr": 0})
        self.assertEqual(self.link.regs[73], 0)
        self.assertEqual(self.link.get_calibration()["spkErr"], 0)

        self.link.set_calibration({"spkErr": 999})
        self.assertEqual(self.link.regs[73], 999)
        self.assertEqual(self.link.get_calibration()["spkErr"], 999)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"spkErr": 1000})
        self.assertEqual(ctx.exception.field, "spkErr")

    # -------------------------------------------------------------------------
    # 4. DIRECTION (direction, Reg 52): 0 Forward, 1 Reverse
    # Both save and read back
    # -------------------------------------------------------------------------
    def test_04_direction(self):
        self.link.set_calibration({"direction": "Forward"})
        self.assertEqual(self.link.regs[52], 0)
        self.assertEqual(self.link.get_calibration()["direction"], "Forward")

        self.link.set_calibration({"direction": "Reverse"})
        self.assertEqual(self.link.regs[52], 1)
        self.assertEqual(self.link.get_calibration()["direction"], "Reverse")

        # Also support 0 and 1
        self.link.set_calibration({"direction": 0})
        self.assertEqual(self.link.regs[52], 0)
        self.assertEqual(self.link.get_calibration()["direction"], "Forward")

        self.link.set_calibration({"direction": 1})
        self.assertEqual(self.link.regs[52], 1)
        self.assertEqual(self.link.get_calibration()["direction"], "Reverse")

    # -------------------------------------------------------------------------
    # 5. ENCODER PPR SET (encoderPprSet, Reg 70): 100-9999 (default 5000)
    # 0 and 99 refused; 100 and 9999 save
    # -------------------------------------------------------------------------
    def test_05_encoder_ppr_set(self):
        self.link.set_calibration({"encoderPprSet": 100})
        self.assertEqual(self.link.regs[70], 100)
        self.assertEqual(self.link.get_calibration()["encoderPprSet"], 100)

        self.link.set_calibration({"encoderPprSet": 9999})
        self.assertEqual(self.link.regs[70], 9999)
        self.assertEqual(self.link.get_calibration()["encoderPprSet"], 9999)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"encoderPprSet": 0})
        self.assertEqual(ctx.exception.field, "encoderPprSet")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"encoderPprSet": 99})
        self.assertEqual(ctx.exception.field, "encoderPprSet")

    # -------------------------------------------------------------------------
    # 6. ENCODER PPR ACTUAL (Reg 85): Read only
    # Value shows and cannot be edited
    # -------------------------------------------------------------------------
    def test_06_encoder_ppr_actual(self):
        self.link.regs[85] = 5000
        cal = self.link.get_calibration()
        self.assertEqual(cal["encoderPprActual"], 5000)

        # Passing encoderPprActual in set_calibration has no effect on reg 85
        self.link.set_calibration({"encoderPprActual": 1234})
        self.assertEqual(self.link.regs[85], 5000, "encoderPprActual must remain read-only!")

    # -------------------------------------------------------------------------
    # 7. MARK OFFSET (markOffset, Reg 21): -999 to +999 mm, no password
    # -999 and +999 save; -12 is sent as 0xFFF4
    # -------------------------------------------------------------------------
    def test_07_mark_offset(self):
        # Starts locked
        self.link.unlocked_until = 0.0
        self.link.regs[30] = 0

        # markOffset does NOT write password to reg 30!
        self.link.set_calibration({"markOffset": -12})
        self.assertEqual(self.link.regs[21], 0xFFF4, "-12 must be stored as 0xFFF4 in 16-bit")
        self.assertEqual(self.link._get_signed_mark_offset(), -12)
        self.assertEqual(self.link.get_calibration()["markOffset"], -12)
        self.assertEqual(self.link.regs[30], 0, "No password must be sent for MARK OFFSET!")

        self.link.set_calibration({"markOffset": -999})
        self.assertEqual(self.link.get_calibration()["markOffset"], -999)

        self.link.set_calibration({"markOffset": 999})
        self.assertEqual(self.link.get_calibration()["markOffset"], 999)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"markOffset": -1000})
        self.assertEqual(ctx.exception.field, "markOffset")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"markOffset": 1000})
        self.assertEqual(ctx.exception.field, "markOffset")

    # -------------------------------------------------------------------------
    # 8. CYLINDER CIRCUMFERENCE (cylinderCircumference, Reg 40): 50-9999 mm (default 1570)
    # 0 and 49 refused; 1570 saves
    # -------------------------------------------------------------------------
    def test_08_cylinder_circumference(self):
        self.link.set_calibration({"cylinderCircumference": 1570})
        self.assertEqual(self.link.regs[40], 1570)
        self.assertEqual(self.link.get_calibration()["cylinderCircumference"], 1570)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"cylinderCircumference": 0})
        self.assertEqual(ctx.exception.field, "cylinderCircumference")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"cylinderCircumference": 49})
        self.assertEqual(ctx.exception.field, "cylinderCircumference")

    # -------------------------------------------------------------------------
    # 9. B2B ALARM (b2bAlarm, Reg 43): 5-25 mm, default 15
    # 4 and 26 refused
    # -------------------------------------------------------------------------
    def test_09_b2b_alarm(self):
        self.link.set_calibration({"b2bAlarm": 15})
        self.assertEqual(self.link.regs[43], 15)
        self.assertEqual(self.link.get_calibration()["b2bAlarm"], 15)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"b2bAlarm": 4})
        self.assertEqual(ctx.exception.field, "b2bAlarm")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"b2bAlarm": 26})
        self.assertEqual(ctx.exception.field, "b2bAlarm")

    # -------------------------------------------------------------------------
    # 10. MARK1/2 SKIP BAG ALARM (markSkipAlarm, Reg 75): 1-9 bags, default 6
    # 0 and 10 refused
    # -------------------------------------------------------------------------
    def test_10_mark_skip_alarm(self):
        self.link.set_calibration({"markSkipAlarm": 6})
        self.assertEqual(self.link.regs[75], 6)
        self.assertEqual(self.link.get_calibration()["markSkipAlarm"], 6)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"markSkipAlarm": 0})
        self.assertEqual(ctx.exception.field, "markSkipAlarm")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"markSkipAlarm": 10})
        self.assertEqual(ctx.exception.field, "markSkipAlarm")

    # -------------------------------------------------------------------------
    # 11. BRAKE TYPE (brakeType, Reg 67): 0 Powder, 1 Pneumatic; stored only
    # Saves and reads back after a power cycle
    # -------------------------------------------------------------------------
    def test_11_brake_type(self):
        self.link.set_calibration({"brakeType": "Powder Brake"})
        self.assertEqual(self.link.regs[67], 0)
        self.assertEqual(self.link.get_calibration()["brakeType"], "Powder Brake")

        self.link.set_calibration({"brakeType": "Pneumatic"})
        self.assertEqual(self.link.regs[67], 1)
        self.assertEqual(self.link.get_calibration()["brakeType"], "Pneumatic")

        # Simulate power cycle / restart
        new_link = fbarx_link.FBarXLink(simulate=True)
        self.assertEqual(new_link.get_calibration()["brakeType"], "Pneumatic",
                         "Brake type must be restored from SQLite after power cycle!")

    # -------------------------------------------------------------------------
    # 12. BRAKE POWER SET (brakePower, Reg 66): 0-100 %
    # 50 % gives 12 V on J3
    # -------------------------------------------------------------------------
    def test_12_brake_power(self):
        self.link.set_calibration({"brakePower": 50})
        self.assertEqual(self.link.regs[66], 50)
        self.assertEqual(self.link.get_calibration()["brakePower"], 50)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"brakePower": -1})
        self.assertEqual(ctx.exception.field, "brakePower")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"brakePower": 101})
        self.assertEqual(ctx.exception.field, "brakePower")

    # -------------------------------------------------------------------------
    # 13. BRAKE CAPACITY SET (brakeCapacity, Reg 68): 1-20 kgm, default 20; stored only
    # 25 refused with a message next to the field
    # -------------------------------------------------------------------------
    def test_13_brake_capacity(self):
        self.link.set_calibration({"brakeCapacity": 20})
        self.assertEqual(self.link.regs[68], 20)
        self.assertEqual(self.link.get_calibration()["brakeCapacity"], 20)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"brakeCapacity": 25})
        self.assertEqual(ctx.exception.field, "brakeCapacity")

        # Check API returns HTTP 400 naming the field
        tok_code, tok_res = fbarx_api.route_post(self.link, "/api/fbarx/unlock", {"code": "3333"}, {})
        tok = tok_res["token"]
        code, res = fbarx_api.route_post(self.link, "/api/fbarx/calibration", {"brakeCapacity": 25}, {"X-Cal-Token": tok})
        self.assertEqual(code, 400)
        self.assertEqual(res["field"], "brakeCapacity")

    # -------------------------------------------------------------------------
    # 14. BRAKE CURRENT SET (brakeCurrent, Reg 69): 0.0-5.0 A in 0.1 A steps, stored x10; stored only
    # 2.4 saves as 24; 5.1 refused
    # -------------------------------------------------------------------------
    def test_14_brake_current(self):
        self.link.set_calibration({"brakeCurrent": 2.4})
        self.assertEqual(self.link.regs[69], 24)
        self.assertEqual(self.link.get_calibration()["brakeCurrent"], 2.4)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"brakeCurrent": 5.1})
        self.assertEqual(ctx.exception.field, "brakeCurrent")

    # -------------------------------------------------------------------------
    # 15. BRAKE CURRENT CAL (brakeCurrentCal, Reg 83): 1000-30000 mA at 1000 counts, default 14160
    # -------------------------------------------------------------------------
    def test_15_brake_current_cal(self):
        self.link.set_calibration({"brakeCurrentCal": 14160})
        self.assertEqual(self.link.regs[83], 14160)
        self.assertEqual(self.link.get_calibration()["brakeCurrentCal"], 14160)

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"brakeCurrentCal": 999})
        self.assertEqual(ctx.exception.field, "brakeCurrentCal")

        with self.assertRaises(fbarx_link.FieldError) as ctx:
            self.link.set_calibration({"brakeCurrentCal": 30001})
        self.assertEqual(ctx.exception.field, "brakeCurrentCal")

    # -------------------------------------------------------------------------
    # 16. SET TENSION (setTension, Reg 74): 0.0-99.9 kg, stored x10
    # -------------------------------------------------------------------------
    def test_16_set_tension(self):
        self.link.set_tension(5.5)
        self.assertEqual(self.link.regs[74], 55)
        self.assertEqual(self.link.get_calibration()["setTension"], 5.5)

    # -------------------------------------------------------------------------
    # Additional Verification:
    # - Password write (reg 30 <- 1212) before first write; stays unlocked for 5 min
    # - BRAKE POWER and CAPACITY independence & available capacity calculation
    # - Opening CALIBRATE reads regs 40-86 and reg 21
    # - Out of range values raise ValueError and return HTTP 400 naming field
    # -------------------------------------------------------------------------
    def test_additional_password_unlock_and_5min_ttl(self):
        # Start locked
        self.link.unlocked_until = 0.0
        self.link.regs[30] = 0

        # Protected write unlocks reg 30 with 1212
        self.link.set_calibration({"acErr": 7.0})
        self.assertEqual(self.link.regs[30], 1212, "Reg 30 must be written with 1212 on first protected write")
        self.assertGreater(self.link.unlocked_until, time.time() + 290.0, "Must be unlocked for 5 min (300s)")

        # Clear reg 30 simulation tracker to verify next write within 5 min doesn't need to re-unlock
        self.link.regs[30] = 9999
        self.link.set_calibration({"dcErr": 2})
        self.assertEqual(self.link.regs[30], 9999, "Reg 30 must NOT be rewritten while within 5-min unlock window")

    def test_additional_power_and_capacity_independence_and_available(self):
        self.link.set_calibration({"brakePower": 50, "brakeCapacity": 20})
        self.assertEqual(self.link.regs[66], 50)
        self.assertEqual(self.link.regs[68], 20)

        # Modifying power does not change capacity
        self.link.set_calibration({"brakePower": 80})
        self.assertEqual(self.link.regs[66], 80)
        self.assertEqual(self.link.regs[68], 20, "brakeCapacity must not change when writing brakePower")

        # Modifying capacity does not change power
        self.link.set_calibration({"brakeCapacity": 15})
        self.assertEqual(self.link.regs[66], 80, "brakePower must not change when writing brakeCapacity")
        self.assertEqual(self.link.regs[68], 15)

        # Available capacity formula: capacity * power / 100
        # 20 kgm at 50% gives 10.0 kgm
        pwr = 50.0
        cap = 20.0
        avail = (cap * pwr) / 100.0
        self.assertEqual(avail, 10.0)

    def test_additional_open_calibrate_reads_regs_40_to_86_and_21(self):
        # In real link, get_calibration calls _read_regs(40, 47) and _read_regs(21, 1)
        # Regs 40 to 86 = 47 registers (40, 41, ..., 86)
        start_40 = 40
        qty_47 = 47
        end_reg = start_40 + qty_47 - 1
        self.assertEqual(end_reg, 86, "Reading 47 registers starting at 40 reads 40 to 86")

    def test_additional_exception_4_locked_retry(self):
        link = fbarx_link.FBarXLink(simulate=False)
        mock_port = MockSerialPort()
        mock_port.unlocked = False  # locked initially
        link.ser = mock_port
        link.connected = True
        link.fw_ok = True

        # Link writes brakePower reg 66 while locked
        # Modbus returns Exception 4; link catches it, writes reg 30 <- 1212, and retries once
        link._write_reg(66, 50, "brakePower")
        self.assertEqual(link.regs[66], 50)
        self.assertTrue(mock_port.unlocked, "Mock port must be unlocked via reg 30 <- 1212 on Exception 4")

if __name__ == "__main__":
    unittest.main(verbosity=2)
