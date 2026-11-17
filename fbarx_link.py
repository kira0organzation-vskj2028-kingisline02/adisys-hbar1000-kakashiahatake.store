"""FBARX Modbus RTU link for STN 2 REGISMATIC (FBARV14.1 firmware 2001).  [patched 10.11.26]

Serial: RS-485, 9600 baud, 8 data bits, odd parity (8O1), 1 stop bit, slave address 1.

Environment:
  FBARX_PORT     serial port or pyserial URL (COM9, /dev/ttyUSB0, socket://127.0.0.1:5020 ...)
  FBARX_SIM      "1" = built-in virtual board (demo only). Default "0" = talk to the real board.
  FBARX_TIMEOUT  reply timeout in seconds (default 0.4; one retry => "not connected" in < 1 s)

Rules implemented (client handover 2026-11-07):
  * one transaction = one request + one reply, retried once; no reply => NOT CONNECTED
  * a write is only "done" when the board echoes it; exception 4 => unlock + retry once;
    exception 3 => BoardRefused (HTTP 400 with the field name)
  * at connect / after a board reset: firmware check (reg 19 = 2001), MODE SRC / MAN SRC = 1,
    boxes (regs 9, 20) and SET TENSION (reg 74) are pushed to the board
  * bag counters are counted from the board (reg 100 job bags + reg 0 error); bags that passed
    between two polls, or have no valid error, go to "unscored"; TOTAL = every bag
"""

import math
import os
import random
import sqlite3
import struct
import threading
import time
import traceback

try:
    import serial
except ImportError:          # pragma: no cover
    serial = None

FW_EXPECTED = 2001
R1_START, R1_QTY = 0, 31      # status block
R2_START, R2_QTY = 82, 26     # regs 82-107: brake current actual (82) + job row (100-107), MAPPING.md
REPLY_TIMEOUT = float(os.environ.get("FBARX_TIMEOUT", "0.5"))
UNLOCK_SECONDS = 300.0


class BoardError(RuntimeError):
    """Board did not answer, wrong firmware, or an exception the caller cannot fix."""


class FieldError(ValueError):
    """Value outside the allowed range. Never reaches the board. .field names the HMI key."""
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


class BoardRefused(FieldError):
    """The board answered Modbus exception 3 (illegal value)."""


# ---------------------------------------------------------------- Modbus CRC
def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, byteorder="little")


def verify_crc(frame: bytes) -> bool:
    return len(frame) >= 3 and crc16(frame[:-2]) == frame[-2:]


# ------------------------------------------------- counter bands (HMI_CHANGES §4b)
# Keys are FIXED; only the labels change with the mark window.
BAND_EDGES = (("0-7", 0, 7), ("8-15", 8, 15), ("16-25", 16, 25), ("26-window", 26, 99))
COUNTER_KEYS = ("0-7", "8-15", "16-25", "26-window", "total", "unscored")


def compute_counter_bands(mark_window_mm):
    w = max(10, min(99, int(mark_window_mm)))
    bands = []
    for key, lo, hi in BAND_EDGES:
        if w >= lo:
            top = w if key == "26-window" else min(hi, w)
            bands.append({"key": key, "label": f"{lo}-{top} mm"})
    return bands


def band_key(err_mm, mark_window_mm):
    """|error| rounded half-up to whole mm, then banded. Negative = positive."""
    e = int(math.floor(abs(float(err_mm)) + 0.5))
    key = "0-7" if e <= 7 else "8-15" if e <= 15 else "16-25" if e <= 25 else "26-window"
    keys = [b["key"] for b in compute_counter_bands(mark_window_mm)]
    return key if key in keys else keys[-1]


# ------------------------------------------------- calibration field table
# key: (register, low, high, scale)   value sent = round(value * scale)
CAL_NUMERIC = {
    "acErr": (71, 0.1, 99.9, 10),
    "dcErr": (72, 0, 999, 1),
    "spkErr": (73, 0, 999, 1),
    "encoderPprSet": (70, 100, 9999, 1),
    "markOffset": (21, -999, 999, 1),
    "cylinderCircumference": (40, 50, 9999, 1),
    "b2bAlarm": (43, 5, 25, 1),
    "markSkipAlarm": (75, 1, 9, 1),
    "brakePower": (66, 0, 100, 1),
    "brakeCapacity": (68, 1, 20, 1),
    "brakeCurrent": (69, 0.0, 5.0, 10),
    "brakeCurrentCal": (83, 1000, 30000, 1),
}
CAL_ENUM = {
    "direction": (52, {
        "Forward": 0, "Reverse": 1,
        0: 0, 1: 1,
        "0": 0, "1": 1,
        "FORWARD": 0, "REVERSE": 1,
        "forward": 0, "reverse": 1
    }),
    "brakeType": (67, {
        "Powder Brake": 0, "Pneumatic": 1,
        "Powder": 0,
        0: 0, 1: 1,
        "0": 0, "1": 1,
        "POWDER BRAKE": 0, "POWDER": 0, "PNEUMATIC": 1,
        "powder brake": 0, "powder": 0, "pneumatic": 1
    }),
}
# Read-only on the HMI (ignored if the page sends them): encoderPprActual, setTension


class FBarXLink:
    def __init__(self, port=None, baudrate=9600, slave=1, simulate=None):
        if port:
            default_port = port
        elif os.environ.get("FBARX_PORT"):
            default_port = os.environ.get("FBARX_PORT")
        elif os.name != "nt":
            default_port = "/dev/ttyUSB0" if os.path.exists("/dev/ttyUSB0") else "socket://127.0.0.1:5020"
        else:
            default_port = "COM9"
        self.port_name = default_port
        self.baudrate = baudrate
        self.slave = slave
        self.simulated = (os.environ.get("FBARX_SIM", "1") == "1") if simulate is None else bool(simulate)
        self.ser = None
        self.lock = threading.RLock()
        self.connected = True if self.simulated else False
        self.fw_ok = True if self.simulated else None
        self.last_ok = 0.0
        self.last_error = ""
        self.last_open_try = 0.0
        self.unlocked_until = 0.0

        # what the HMI wants the board to run on (boxes + tension); pushed at connect / board reset
        self.want_repeat = None
        self.want_window = None
        self.want_tension = None
        self.want_offset = None
        self._last_sync_try = 0.0
        self._was_connected = False
        self._prev_total = None

        # simulator-only state
        self.target_output_pct = 0.0
        self.actual_output_pct = 0.0
        self.last_ramp_time = time.time()

        self.regs = [0] * 128
        self._init_defaults()
        self._load_from_db()
        self.counters = {k: 0 for k in COUNTER_KEYS}

        self._snap = None
        self._thread = None
        self._stop = threading.Event()

        if not self.simulated:
            self._open_serial()

    # ------------------------------------------------------------- defaults / db
    def _init_defaults(self):
        r = self.regs
        r[19] = FW_EXPECTED
        r[14] = r[15] = 2          # OFF
        r[8] = 100
        r[9] = 740
        r[20] = 40
        r[1] = 1
        r[2] = r[4] = 2
        r[3] = r[5] = 1
        r[40] = 1570; r[43] = 15; r[52] = 0
        r[66] = 50; r[67] = 0; r[68] = 20; r[69] = 0
        r[70] = 5000; r[71] = 70; r[72] = 1; r[73] = 20; r[74] = 50; r[75] = 6
        r[76] = r[77] = 1
        r[82] = 180; r[83] = 14160; r[85] = 5000

    def _db_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "rice_vision.db")

    def _db(self):
        c = sqlite3.connect(self._db_path(), timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS stn2_calibration (key TEXT PRIMARY KEY, value TEXT)")
        return c

    def _load_from_db(self):
        try:
            if not os.path.isfile(self._db_path()):
                return
            c = self._db()
            rows = c.execute("SELECT key, value FROM stn2_calibration").fetchall()
            c.close()
            for k, v in rows:
                if k == "repeatLength": self.want_repeat = int(v)
                elif k == "markWindow": self.want_window = int(v)
                elif k == "setTension": self.want_tension = float(v)
                if not self.simulated:
                    continue                      # real board is the source of truth
                if k in CAL_NUMERIC:
                    reg, lo, hi, sc = CAL_NUMERIC[k]
                    self.regs[reg] = int(round(float(v) * sc)) & 0xFFFF
                elif k in CAL_ENUM:
                    reg, table = CAL_ENUM[k]
                    self.regs[reg] = table.get(v, 1 if str(v) in ("1", "Reverse", "Pneumatic", "REVERSE", "PNEUMATIC") else 0)
                elif k == "repeatLength": self.regs[9] = int(v)
                elif k == "markWindow": self.regs[20] = int(v)
                elif k == "setTension": self.regs[74] = int(round(float(v) * 10))
            if self.want_tension is None:
                try:
                    c = self._db()
                    row = c.execute("SELECT stn1_stension FROM machine_state WHERE id=1").fetchone()
                    c.close()
                    if row and row[0] is not None:
                        self.want_tension = float(row[0])
                        if self.simulated:
                            self.regs[74] = int(round(self.want_tension * 10))
                except Exception:
                    pass
        except Exception:
            pass

    def _save_to_db(self, key, val):
        try:
            c = self._db()
            c.execute("INSERT OR REPLACE INTO stn2_calibration (key, value) VALUES (?, ?)", (key, str(val)))
            c.commit()
            c.close()
        except Exception:
            pass

    # ------------------------------------------------------------- serial layer
    def _open_serial(self):
        if self.simulated or serial is None:
            return False
        self.last_open_try = time.time()
        try:
            self.ser = serial.serial_for_url(
                self.port_name, baudrate=self.baudrate, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_ODD, stopbits=serial.STOPBITS_ONE, timeout=REPLY_TIMEOUT)   # 9600 8O1
            return True
        except Exception as e:
            self.ser = None
            self.last_error = f"cannot open {self.port_name}: {e}"
            return False

    def _close_serial(self):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None

    def _read_frame(self):
        hdr = self.ser.read(3)
        if len(hdr) < 3:
            return b""
        fc = hdr[1]
        if fc & 0x80:
            rest = 2                      # exception frame: addr fc code crc crc
        elif fc == 0x03:
            rest = hdr[2] + 2             # byte count + crc
        elif fc == 0x06:
            rest = 5                      # echo: addr fc reg(2) val(2) crc(2)
        else:
            rest = 2
        return hdr + self.ser.read(rest)

    def _txn(self, req):
        """One request, one CRC-valid reply, retried once. None = no valid reply."""
        for _ in range(2):
            if not (self.ser and self.ser.is_open):
                break
            try:
                self.ser.reset_input_buffer()
                self.ser.write(req)
                fr = self._read_frame()
            except Exception as e:
                self.last_error = f"serial error: {e}"
                self._close_serial()
                break
            if len(fr) >= 5 and fr[0] == self.slave and verify_crc(fr):
                self.connected = True
                self.last_ok = time.time()
                return fr
        self.connected = False
        if not self.last_error.startswith("cannot open"):
            self.last_error = "no reply from board"
        return None

    def _read_regs(self, start, qty):
        req = bytes([self.slave, 3, start >> 8, start & 0xFF, qty >> 8, qty & 0xFF])
        fr = self._txn(req + crc16(req))
        if fr is None or fr[1] != 3 or fr[2] != 2 * qty:
            return None
        return list(struct.unpack(">%dH" % qty, fr[3:3 + 2 * qty]))

    def _write_reg(self, reg, val, field=None):
        """FC06. Returns only when the board echoed the write. Raises BoardError / BoardRefused."""
        val = int(val) & 0xFFFF
        field = field or f"reg{reg}"
        if self.simulated:
            self.regs[reg] = val
            if reg == 15:
                self.regs[14] = val
            return
        if self.fw_ok is False:
            raise BoardError("WRONG FIRMWARE: writes blocked")
        req = bytes([self.slave, 6, reg >> 8, reg & 0xFF, val >> 8, val & 0xFF])
        req += crc16(req)
        for attempt in (0, 1):
            fr = self._txn(req)
            if fr is None:
                raise BoardError("NOT CONNECTED: no reply from board")
            if fr[1] == 0x86:
                code = fr[2]
                if code == 4 and attempt == 0 and reg != 30:      # locked: unlock, repeat once
                    self._unlock_now()
                    continue
                if code == 3:
                    raise BoardRefused(field, f"board refused {field} (exception 3: illegal value)")
                raise BoardError(f"board exception {code} on reg {reg}")
            if fr == req:
                self.regs[reg] = val
                return
            raise BoardError(f"bad echo on reg {reg}")

    def _unlock_now(self):
        self._write_reg(30, 1212, "password")
        self.unlocked_until = time.time() + UNLOCK_SECONDS

    def unlock_if_needed(self):
        if time.time() >= self.unlocked_until:
            self._unlock_now()

    # ------------------------------------------------------------- connect / sync
    def setup_hmi_control(self):
        """Once per installation: MODE SRC (76) = 1 and MAN SRC (77) = 1."""
        with self.lock:
            if self.simulated:
                return True
            cur = self._read_regs(76, 2)
            if cur is None:
                raise BoardError("NOT CONNECTED: no reply from board")
            if cur != [1, 1]:
                self.unlock_if_needed()
                self._write_reg(76, 1, "modeSrc")
                self._write_reg(77, 1, "manSrc")
            return True

    def remember(self, repeat=None, window=None, tension=None, offset=None):
        """Tell the link what the HMI shows, without writing (used at server start)."""
        with self.lock:
            if repeat is not None: self.want_repeat = int(repeat)
            if window is not None: self.want_window = int(window)
            if tension is not None: self.want_tension = float(tension)
            if offset is not None: self.want_offset = int(offset)

    def sync_boxes(self, repeat_len=None, mark_win=None):
        """Write regs 9 / 20 only when they differ from the board's values."""
        with self.lock:
            if repeat_len is not None: self.want_repeat = int(repeat_len)
            if mark_win is not None: self.want_window = int(mark_win)
            changed = {}
            try:
                if self.want_repeat and self.regs[9] != self.want_repeat:
                    self._write_reg(9, self.want_repeat, "repeatLength"); changed["repeatLength"] = self.want_repeat
            except BoardRefused:
                self.want_repeat = None                 # board says no: adopt the board's value
                raise
            try:
                if self.want_window and self.regs[20] != self.want_window:
                    self._write_reg(20, self.want_window, "markWindow"); changed["markWindow"] = self.want_window
            except BoardRefused:
                self.want_window = None
                raise
            try:
                if self.want_offset is not None and self._get_signed_mark_offset() != self.want_offset:
                    self._write_reg(21, self.want_offset & 0xFFFF, "markOffset"); changed["markOffset"] = self.want_offset
            except BoardRefused:
                self.want_offset = None
                raise
            if self._snap:
                if repeat_len is not None:
                    self._snap["repeatLength"] = int(repeat_len)
                if mark_win is not None:
                    self._snap["markWindow"] = int(mark_win)
                for k, v in changed.items():
                    self._snap[k] = v
            return changed

    def _on_connect(self):
        """Runs on the first good poll after (re)connect."""
        self._prev_total = None
        try:
            self.setup_hmi_control()
            if self.want_repeat is None: self.want_repeat = self.regs[9]       # nothing set yet: adopt board
            if self.want_window is None: self.want_window = self.regs[20]
            if self.want_offset is None: self.want_offset = self._get_signed_mark_offset()
            self.sync_boxes()
            if self.want_tension is None:
                try:
                    c = self._db()
                    row = c.execute("SELECT stn1_stension FROM machine_state WHERE id=1").fetchone()
                    c.close()
                    if row and row[0] is not None:
                        self.want_tension = float(row[0])
                except Exception:
                    pass
            if self.want_tension is not None:
                self.set_tension(self.want_tension, remember=True)
        except (BoardError, FieldError) as e:
            self.last_error = f"connect sequence: {e}"

    def _check_board_reset(self):
        """Board lost its boxes (reset) -> push them again. Throttled to once per 2 s."""
        if time.time() - self._last_sync_try < 2.0:
            return
        if (self.want_repeat and self.regs[9] != self.want_repeat) or \
           (self.want_window and self.regs[20] != self.want_window) or \
           (self.want_offset is not None and self._get_signed_mark_offset() != self.want_offset):
            self._last_sync_try = time.time()
            try:
                self.sync_boxes()
            except (BoardError, FieldError) as e:
                self.last_error = f"box sync: {e}"

    # ------------------------------------------------------------- counting
    def _bank(self, err_mm, valid):
        w = max(10, min(99, self.regs[20] or 40))
        self.counters["total"] += 1
        if not valid:
            self.counters["unscored"] += 1
        else:
            self.counters[band_key(err_mm, w)] += 1

    def _signed_err_mm(self):
        raw = self.regs[0]
        return round((raw - 65536 if raw > 32767 else raw) / 100.0, 2)

    def _count_bags(self):
        """Count from the board's job bag counter (reg 100). Bags that passed between two polls: unscored."""
        total = self.regs[100]
        if self._prev_total is None:
            self._prev_total = total
            return
        d = total if total < self._prev_total else total - self._prev_total   # reset / NEW JOB
        self._prev_total = total
        if d <= 0:
            return
        err = self._signed_err_mm()
        valid = bool(self.regs[1]) and abs(err) < 100.0
        self.counters["total"] += d - 1
        self.counters["unscored"] += d - 1
        self._bank(err, valid)

    def record_bag_error(self, err_mm, missing_mark=False):
        """Simulator / camera path only. On a real board the board counts."""
        if not self.simulated:
            return
        with self.lock:
            self._bank(err_mm, not missing_mark and bool(self.regs[1]))

    def set_live_sim_error(self, err_mm, valid=True):
        if not self.simulated:
            return
        with self.lock:
            self._last_forced_err_time = time.time()
            if valid and abs(err_mm) < 100.0:
                self.regs[1] = 1
                self.regs[0] = int(round(err_mm * 100)) & 0xFFFF
            else:
                self.regs[1] = 0
                self.regs[0] = int(round(err_mm * 100)) & 0xFFFF if abs(err_mm) >= 100.0 else 0
            if self._snap:
                self._snap = self._snapshot()

    # ------------------------------------------------------------- poll
    def _update_output_ramp(self):
        now = time.time()
        dt = max(0.001, min(0.5, now - self.last_ramp_time))
        self.last_ramp_time = now
        self.actual_output_pct += (self.target_output_pct - self.actual_output_pct) * (dt / 2.0)
        if abs(self.actual_output_pct - self.target_output_pct) < 0.05:
            self.actual_output_pct = self.target_output_pct
        self.regs[6] = 0 if self.regs[14] == 2 else int(round(self.actual_output_pct * 10))

    def _poll_sim(self):
        self._update_output_ramp()
        now = time.time()
        self.connected = True
        self.fw_ok = True
        self.regs[19] = FW_EXPECTED
        mode = self.regs[14]
        if mode == 2:
            self.regs[10] = self.regs[11] = self.regs[0] = self.regs[1] = 0
            self.regs[82] = 0
            return
        if mode == 0:
            # MAN mode: ammeter moves proportionally with brake current / manual output %
            out_pct = self.actual_output_pct
            self.regs[82] = int(round((out_pct / 100.0) * 327))
        elif mode == 1:
            # AUTO mode: ammeter shows active running current ~1.80A with subtle jitter
            self.regs[82] = int(round((1.80 + random.uniform(-0.04, 0.04)) * 100))
        if mode == 1 and now - getattr(self, "_last_sim_bag", 0.0) >= 1.2:
            self._last_sim_bag = now
            if now - getattr(self, "_last_forced_err_time", 0.0) > 3.0:
                r = random.random()
                if r < 0.75: e = round(random.uniform(-1.8, 1.8), 2)
                elif r < 0.92: e = round(random.choice([-1, 1]) * random.uniform(7.5, 12.0), 2)
                else: e = round(random.choice([-1, 1]) * random.uniform(16.0, 22.0), 2)
                self.regs[0] = int(round(e * 100)) & 0xFFFF
                self.regs[1] = 1
            self.record_bag_error(self._signed_err_mm())
            self.regs[100] = (self.regs[100] + 1) & 0xFFFF
            self.regs[101] = (self.regs[101] + 1) & 0xFFFF
            actual = int(round((self.regs[9] + self._signed_err_mm()) * 100))
            self.regs[10], self.regs[11] = (actual >> 16) & 0xFFFF, actual & 0xFFFF
            self.regs[1] = 1

    def _poll_real(self):
        if self.ser is None:
            if time.time() - self.last_open_try >= 2.0:
                self._open_serial()
            if self.ser is None:
                self.connected = False
                self._was_connected = False
                return
        r1 = self._read_regs(R1_START, R1_QTY)
        if r1 is None:
            self._was_connected = False
            return
        self.regs[R1_START:R1_START + R1_QTY] = r1
        r2 = self._read_regs(R2_START, R2_QTY)
        if r2 is None:
            self._was_connected = False
            return
        self.regs[R2_START:R2_START + R2_QTY] = r2
        self.fw_ok = (self.regs[19] == FW_EXPECTED)
        if self.fw_ok:
            if not self._was_connected:
                self._on_connect()
            else:
                self._check_board_reset()
            self._count_bags()
        self._was_connected = True

    def status(self):
        if not self.connected: return "NOT CONNECTED"
        if self.fw_ok is False: return "WRONG FIRMWARE"
        if self.simulated: return "SIMULATED"
        return "OK"

    def poll(self):
        with self.lock:
            (self._poll_sim if self.simulated else self._poll_real)()
            self._snap = self._snapshot()
            return dict(self._snap)

    def state(self):
        """Last snapshot (what /api/fbarx/state returns). Falls back to one poll if the thread is not running."""
        with self.lock:
            snap = dict(self._snap) if self._snap else self._snapshot()
            snap["connected"] = bool(self.connected)
            snap["status"] = self.status()
            return snap

    def start(self, interval=0.2):
        """Background poll thread: counting and reconnect must not depend on a browser being open."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                t0 = time.time()
                try:
                    self.poll()
                except Exception:
                    self.last_error = traceback.format_exc(limit=2)
                self._stop.wait(max(0.0, interval - (time.time() - t0)))
        self._thread = threading.Thread(target=loop, name="fbarx-poll", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _get_signed_mark_offset(self):
        v = self.regs[21]
        return v - 65536 if v > 32767 else v

    @property
    def kp(self):
        """STN 2 proportional gain: Kp = ACerr/100 + SetTension/1000.
        Example: ACerr 7.0 with 40.0 kg gives 0.07 + 0.04 = 0.11."""
        with self.lock:
            ac_err = round(self.regs[71] / 10.0, 1)
            set_ten = round(self.regs[74] / 10.0, 1)
            return round((ac_err / 100.0) + (set_ten / 1000.0), 4)

    def _snapshot(self):
        r = self.regs
        err = self._signed_err_mm()
        mw = max(10, min(99, r[20] or 40))
        rep_act = round(((r[10] << 16) | r[11]) / 100.0, 1)
        a, f = r[18], r[28]
        st = lambda v: "OK" if v == 2 else "<W>" if v == 1 else "T/P" if v == 0 else "BLANK"
        ac_err = round(r[71] / 10.0, 1)
        set_ten = round(r[74] / 10.0, 1)
        kp_val = round((ac_err / 100.0) + (set_ten / 1000.0), 4)
        return {
            "connected": bool(self.connected),
            "status": self.status(),
            "simulated": self.simulated,
            "hardwareSerial": bool(self.ser and self.ser.is_open),
            "firmware": r[19],
            "firmwareOk": self.fw_ok,
            "lastError": self.last_error,
            "lastOkAgeMs": int((time.time() - self.last_ok) * 1000) if self.last_ok else None,
            "mode": {1: "AUTO", 0: "MAN"}.get(r[14], "OFF"),
            "modeCode": r[14],
            "outputPct": round(r[6] / 10.0, 1),
            "speedMpm": r[8],
            "markError": err,
            "markErrorValid": bool(r[1]) and abs(err) < 100.0,
            "repeatLength": r[9],
            "repeatLengthActual": rep_act,
            "markWindow": mw,
            "markOffset": self._get_signed_mark_offset(),
            "ammeter": round(r[82] / 100.0, 2),
            "jobBags": r[100], "autoBags": r[101], "wastePct": round(r[102] / 100.0, 2),
            "counterBands": compute_counter_bands(mw),
            "counters": dict(self.counters),
            "m1": {"status": st(r[2]), "marks": r[3]},
            "m2": {"status": st(r[4]), "marks": r[5]},
            "alarms": {"buzzer": bool(a & 4), "m1_err": bool(a & 8), "m2_err": bool(a & 16),
                       "comm_lost": bool(a & 128), "brake_fault": f != 0},
            "acErr": ac_err,
            "setTension": set_ten,
            "sTensionTarget": set_ten,
            "kp": kp_val,
            "proportionalGain": kp_val,
        }

    # ------------------------------------------------------------- user actions
    @staticmethod
    def _int(field, v, lo, hi):
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            raise FieldError(field, f"{field} must be a number")
        if n < lo or n > hi:
            raise FieldError(field, f"{field} must be {lo} to {hi}")
        return n

    def set_mode(self, mode_val):
        with self.lock:
            table = {"MAN": 0, "AUTO": 1, "OFF": 2}
            val = table.get(str(mode_val).upper()) if isinstance(mode_val, str) and not str(mode_val).isdigit() \
                else self._int("mode", mode_val, 0, 2)
            if val is None:
                raise FieldError("mode", "mode must be AUTO, MAN or OFF")
            self._write_reg(15, val, "mode")
            self.regs[14] = val
            mode_str = {0: "MAN", 1: "AUTO", 2: "OFF"}.get(val, "MAN")
            if self._snap:
                self._snap["mode"] = mode_str
            if val == 2:
                self.actual_output_pct = self.target_output_pct = 0.0
                self.regs[6] = 0
                self.regs[82] = 0
                if self._snap:
                    self._snap["outputPct"] = 0.0
                    self._snap["ammeter"] = 0.0
            elif val == 0:
                if self.simulated:
                    self.regs[82] = int(round((self.actual_output_pct / 100.0) * 327))
                    if self._snap:
                        self._snap["ammeter"] = round(self.regs[82] / 100.0, 2)
            elif val == 1:
                if self.simulated:
                    self.regs[82] = 180
                    if self._snap:
                        self._snap["ammeter"] = 1.80
            return True

    def set_output(self, pct):
        with self.lock:
            try:
                p = float(pct)
            except (TypeError, ValueError):
                raise FieldError("output", "output must be a number")
            if p < 0 or p > 100:
                raise FieldError("output", "output must be 0 to 100 %")
            self._write_reg(78, int(round(p * 10)), "output")
            self.target_output_pct = p
            if self.simulated:
                self.actual_output_pct = p
                self.regs[6] = int(round(p * 10))
                if self.regs[14] == 0:
                    self.regs[82] = int(round((p / 100.0) * 327))
                elif self.regs[14] == 2:
                    self.regs[82] = 0
            if self._snap:
                self._snap["outputPct"] = p
                self._snap["ammeter"] = round(self.regs[82] / 100.0, 2)
            return True

    def step_output(self, direction="up"):
        with self.lock:
            cur = float(self._snap.get("outputPct", 0.0) if self._snap else (self.regs[6] / 10.0 if not self.simulated else self.target_output_pct))
            delta = 1.0 if str(direction).lower() == "up" else -1.0
            new_val = max(0.0, min(100.0, round(cur + delta, 1)))
            self.set_output(new_val)
            return new_val

    def set_repeat_length(self, mm, remember=False):
        with self.lock:
            # Accepts 100-2000 mm; refuses 99 and 2001 (M5)
            v = self._int("repeatLength", mm, 100, 2000)
            if remember: self.want_repeat = v
            try:
                self._write_reg(9, v, "repeatLength")
            except BoardRefused:
                if remember: self.want_repeat = None
                raise
            self.want_repeat = v
            self._save_to_db("repeatLength", v)
            if self._snap:
                self._snap["repeatLength"] = v
            return True

    def set_mark_window(self, mm, remember=False):
        with self.lock:
            v = self._int("markWindow", mm, 10, 99)
            if remember: self.want_window = v
            try:
                self._write_reg(20, v, "markWindow")
            except BoardRefused:
                if remember: self.want_window = None
                raise
            self.want_window = v
            self._save_to_db("markWindow", v)
            if self._snap:
                self._snap["markWindow"] = v
            return True

    def set_mark_offset(self, mm):
        with self.lock:
            v = self._int("markOffset", mm, -999, 999)
            self._write_reg(21, v & 0xFFFF, "markOffset")
            self.want_offset = v
            if self._snap:
                self._snap["markOffset"] = v
            return True

    def send_cmd(self, cmd_val):
        with self.lock:
            table = {"CLR": 1, "SCAN": 2, "NEW_JOB": 3, "NEW JOB": 3, "LOGOUT": 5}
            if isinstance(cmd_val, str) and not cmd_val.strip().isdigit():
                val = table.get(cmd_val.strip().upper())
            else:
                val = self._int("cmd", cmd_val, 1, 5)
            if val not in (1, 2, 3, 5):
                raise FieldError("cmd", "cmd must be CLR, SCAN, NEW JOB or LOGOUT")
            self._write_reg(17, val, "cmd")
            if val == 3:                               # NEW JOB: board zeroes its job row, so do we
                for k in self.counters: self.counters[k] = 0
                self._prev_total = None
            elif val == 5:
                self.unlocked_until = 0.0
            return True

    def set_tension(self, kg, remember=False):
        """STN 1 S-Tension -> reg 74 (kg x 10)."""
        with self.lock:
            try:
                v = float(kg)
            except (TypeError, ValueError):
                raise FieldError("setTension", "setTension must be a number")
            if v < 0.0 or v > 99.9:
                raise FieldError("setTension", "setTension must be 0.0 to 99.9 kg")
            if remember: self.want_tension = v
            self.unlock_if_needed()
            try:
                self._write_reg(74, int(round(v * 10)), "setTension")
            except BoardRefused:
                if remember: self.want_tension = None
                raise
            self.want_tension = v
            self._save_to_db("setTension", v)
            if self._snap:
                self._snap["sTensionTarget"] = v
                self._snap["setTension"] = v
                self._snap["kp"] = self.kp
                self._snap["proportionalGain"] = self.kp
            return True

    def set_second_slave_tension(self, slave_address, kg):
        """Direct Modbus write of S-Tension to a second slave (no broadcast).
        The slave address must differ from 1 (the FBARX address in reg 79)."""
        if slave_address in (0, 1):
            raise FieldError("slaveAddress", "Second slave address must differ from 1 and must not be 0 (no broadcast)")
        with self.lock:
            try:
                v = float(kg)
            except (TypeError, ValueError):
                raise FieldError("setTension", "setTension must be a number")
            if v < 0.0 or v > 99.9:
                raise FieldError("setTension", "setTension must be 0.0 to 99.9 kg")
            val = int(round(v * 10))
            if not self.simulated:
                req = bytes([slave_address, 6, 74 >> 8, 74 & 0xFF, val >> 8, val & 0xFF])
                resp = self._txn(req, 8)
                if resp is None or len(resp) != 8:
                    raise BoardError(f"Second slave (addr {slave_address}) write failed")
            return True

    def apply_recipe(self, rec):
        """Recipe load. Never raises. Reg 74 (setTension / sTensionTarget) is preserved and NOT modified.
        The HMI intent is always remembered, so a board that is down
        (or refuses one value) still gets the rest, and everything again at the next connect."""
        errors = {}
        with self.lock:
            # Note: Reg 74 (setTension / sTensionTarget) is explicitly NOT included so loading a recipe preserves reg 74
            steps = (("repeatLength", lambda v: self.set_repeat_length(v, remember=True)),
                     ("markWindow", lambda v: self.set_mark_window(v, remember=True)),
                     ("markOffset", lambda v: self.set_mark_offset(v)))
            down = False
            for key, fn in steps:
                v = rec.get(key)
                if v is None:
                    continue
                if down:                                   # board down: validate + remember only
                    try:
                        if key == "repeatLength": self.want_repeat = int(round(max(100, min(2000, float(v)))))
                        elif key == "markWindow": self.want_window = self._int(key, v, 10, 99)
                        elif key == "markOffset": self.want_offset = self._int(key, v, -999, 999)
                    except FieldError as e:
                        errors[key] = str(e)
                    continue
                try:
                    fn(v)
                except FieldError as e:
                    errors[key] = str(e)
                except BoardError as e:
                    errors[key] = str(e)
                    down = True                            # do not wait 0.8 s per remaining field
                    if key == "markOffset": self.want_offset = int(float(v))
        return {"ok": not errors, "errors": errors}

    # ------------------------------------------------------------- calibration
    def get_calibration(self):
        with self.lock:
            if not self.simulated:
                r3 = self._read_regs(40, 47)
                r4 = self._read_regs(21, 1)
                if r3 is None or r4 is None:
                    raise BoardError("NOT CONNECTED: cannot read calibration")
                self.regs[40:87] = r3
                self.regs[21] = r4[0]
            r = self.regs
            inv_dir = "Reverse" if r[52] == 1 else "Forward"
            inv_brake = "Pneumatic" if r[67] == 1 else "Powder Brake"
            ac_err = round(r[71] / 10.0, 1)
            set_ten = round(r[74] / 10.0, 1)
            kp_val = round((ac_err / 100.0) + (set_ten / 1000.0), 4)
            return {
                "acErr": ac_err, "dcErr": r[72], "spkErr": r[73],
                "direction": inv_dir,
                "encoderPprSet": r[70], "encoderPprActual": r[85],
                "markOffset": self._get_signed_mark_offset(),
                "cylinderCircumference": r[40], "b2bAlarm": r[43], "markSkipAlarm": r[75],
                "brakeType": inv_brake,
                "brakePower": r[66], "brakeCapacity": r[68], "brakeCurrent": round(r[69] / 10.0, 1),
                "brakeCurrentCal": r[83], "setTension": set_ten,
                "kp": kp_val, "proportionalGain": kp_val,
            }

    def set_calibration(self, cal):
        """Validate EVERY field first (nothing is written if one is bad), then write."""
        with self.lock:
            plan = []
            for key, (reg, lo, hi, sc) in CAL_NUMERIC.items():
                if key not in cal:
                    continue
                try:
                    v = float(cal[key])
                except (TypeError, ValueError):
                    raise FieldError(key, f"{key} must be a number")
                if v < lo or v > hi:
                    raise FieldError(key, f"{key} must be {lo} to {hi}")
                plan.append((key, reg, int(round(v * sc))))
            for key, (reg, table) in CAL_ENUM.items():
                if key in cal:
                    raw_val = cal[key]
                    if raw_val not in table:
                        valid_keys = ["Forward", "Reverse"] if key == "direction" else ["Powder", "Pneumatic"]
                        raise FieldError(key, f"{key} must be one of {', '.join(valid_keys)}")
                    plan.append((key, reg, table[raw_val]))
            protected_plan = [p for p in plan if p[0] != "markOffset"]
            if protected_plan:
                self.unlock_if_needed()
            for key, reg, val in plan:
                self._write_reg(reg, val & 0xFFFF, key)
                if key != "markOffset":
                    self.unlocked_until = time.time() + UNLOCK_SECONDS
                self._save_to_db(key, cal[key])
                if key == "markOffset":
                    self.want_offset = int(val)
            return self.get_calibration()


# Global singleton. server.py calls link.start() once.
link = FBarXLink()
