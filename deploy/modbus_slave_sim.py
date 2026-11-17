#!/usr/bin/env python3
"""Standalone Modbus RTU Slave Simulator for FBARX STN 2 (Regismatic).
Listens on a TCP port (default 5020) so pyserial can connect via:
    FBARX_PORT="socket://127.0.0.1:5020" FBARX_SIM=0 python server.py

Supports:
  - Slave address: 1
  - FC 03: Read Holding Registers
  - FC 06: Write Single Register
  - FC 16: Write Multiple Registers
  - Firmware register 19: 2001
  - Password unlock register 30: 1212
  - Mode 14/15: 0=MAN, 1=AUTO, 2=OFF
  - Ammeter register 82: 1.80A in AUTO, proportional in MAN, 0 in OFF
  - Repeat length set 9 (740mm), actual 10 & 11 (32-bit: 74000)
  - Mark window register 20 (40mm)
  - Speed MPM register 8 (100 MPM)
  - Live bag counting & mark error simulation in AUTO mode
"""

import argparse
import random
import socket
import struct
import sys
import threading
import time

def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, byteorder="little")

def verify_crc(frame: bytes) -> bool:
    return len(frame) >= 3 and crc16(frame[:-2]) == frame[-2:]

class ModbusSlave:
    def __init__(self, slave_id=1):
        self.slave_id = slave_id
        self.lock = threading.Lock()
        self.regs = [0] * 128
        self._init_registers()

        # Start live simulation thread (counters, error, etc. in AUTO mode)
        self.running = True
        self.sim_thread = threading.Thread(target=self._sim_loop, daemon=True)
        self.sim_thread.start()

    def _init_registers(self):
        with self.lock:
            self.regs[0] = 0        # mark error * 100
            self.regs[1] = 1        # mark valid
            self.regs[2] = 2        # M1 status (2=OK)
            self.regs[3] = 1        # M1 marks
            self.regs[4] = 2        # M2 status (2=OK)
            self.regs[5] = 1        # M2 marks
            self.regs[6] = 550      # output % * 10 (55.0%)
            self.regs[7] = 48       # tension * 10 (4.8 kg)
            self.regs[8] = 100      # line speed MPM (100 MPM)
            self.regs[9] = 740      # repeat length set (mm)
            self.regs[10] = (74000 >> 16) & 0xFFFF  # repeat length actual high
            self.regs[11] = 74000 & 0xFFFF          # repeat length actual low
            self.regs[14] = 1       # mode actual (0=MAN, 1=AUTO, 2=OFF)
            self.regs[15] = 1       # mode cmd
            self.regs[16] = 0       # command reg
            self.regs[17] = 50      # brake power %
            self.regs[18] = 1       # brake type (1=Powder Brake)
            self.regs[19] = 2001    # firmware version
            self.regs[20] = 40      # mark window (mm)
            self.regs[21] = 0       # mark offset (mm)
            self.regs[22] = 1570    # cylinder circumference
            self.regs[23] = 5000    # encoder PPR set
            self.regs[24] = 5000    # encoder PPR actual
            self.regs[30] = 0       # password unlock register
            self.regs[40] = 1570    # cylinder circ
            self.regs[43] = 15      # b2b alarm
            self.regs[52] = 0       # direction: Forward
            self.regs[66] = 50      # brake power
            self.regs[67] = 0       # brake type
            self.regs[68] = 20      # brake capacity
            self.regs[69] = 18      # brake current
            self.regs[70] = 5000    # encoder PPR
            self.regs[71] = 70      # acErr (7.0)
            self.regs[72] = 1       # dcErr
            self.regs[73] = 20      # spkErr
            self.regs[74] = 50      # set tension * 10 (5.0 kg)
            self.regs[75] = 6       # mark skip alarm
            self.regs[76] = 1       # MODE SRC (1=HMI)
            self.regs[77] = 1       # MAN SRC (1=HMI)
            self.regs[78] = 550     # manual output % * 10 (55.0%)
            self.regs[82] = 180     # ammeter * 100 (1.80 A)
            self.regs[83] = 14160   # brakeCurrentCal
            self.regs[85] = 5000    # encoder PPR cal
            self.regs[100] = 24     # auto bags counter
            self.regs[101] = 24     # job bags counter
            self.regs[102] = 0      # waste pct * 100

    def _sim_loop(self):
        while self.running:
            time.sleep(1.2)
            with self.lock:
                mode = self.regs[14]
                if mode == 1:  # AUTO mode: simulate bag production
                    r = random.random()
                    if r < 0.75:
                        err = round(random.uniform(-1.5, 1.5), 2)
                    elif r < 0.92:
                        err = round(random.choice([-1, 1]) * random.uniform(7.5, 12.0), 2)
                    else:
                        err = round(random.choice([-1, 1]) * random.uniform(16.0, 22.0), 2)

                    self.regs[0] = int(round(err * 100)) & 0xFFFF
                    self.regs[1] = 1
                    self.regs[2] = 2  # M1 status OK
                    self.regs[4] = 2  # M2 status OK
                    self.regs[8] = 100  # Line speed MPM
                    # Live ammeter ~1.80A with subtle jitter
                    self.regs[82] = int(round((1.80 + random.uniform(-0.04, 0.04)) * 100))
                    self.regs[6] = 550  # 55.0% in AUTO
                    self.regs[100] = (self.regs[100] + 1) & 0xFFFF
                    self.regs[101] = (self.regs[101] + 1) & 0xFFFF
                    actual = int(round((self.regs[9] + err) * 100))
                    self.regs[10] = (actual >> 16) & 0xFFFF
                    self.regs[11] = actual & 0xFFFF
                elif mode == 0:  # MAN mode
                    out_pct = self.regs[6] / 10.0
                    self.regs[82] = int(round((out_pct / 100.0) * 327))
                    self.regs[0] = 0
                    self.regs[1] = 0
                    self.regs[2] = 2
                    self.regs[4] = 2
                    self.regs[8] = 100
                    actual = int(round(self.regs[9] * 100))
                    self.regs[10] = (actual >> 16) & 0xFFFF
                    self.regs[11] = actual & 0xFFFF
                else:  # OFF mode
                    self.regs[0] = 0
                    self.regs[1] = 0
                    self.regs[6] = 0
                    self.regs[82] = 0
                    self.regs[10] = 0
                    self.regs[11] = 0

    def _apply_register_write(self, reg_addr: int, val: int):
        """Applies register write and updates dependent simulator state."""
        if reg_addr == 30:  # Password unlock register
            if val == 1212:
                self.regs[30] = 1212
                return True
            else:
                return False

        # Protected registers require password unlock (reg 30 == 1212)
        # Unprotected: 30 (password), 21 (markOffset), 15 (mode), 17 (cmd), 9 (repeat), 20 (window), 78 (output)
        unprotected_regs = (30, 21, 15, 17, 9, 20, 78)
        if reg_addr not in unprotected_regs and self.regs[30] != 1212:
            return False  # Triggers Modbus Exception 4 (locked)
        elif reg_addr == 15:  # Mode command register
            self.regs[15] = val
            self.regs[14] = val
            if val == 2:  # OFF
                self.regs[6] = 0
                self.regs[82] = 0
                self.regs[10] = 0
                self.regs[11] = 0
            elif val == 1:  # AUTO
                self.regs[6] = 550
                self.regs[82] = 180
            elif val == 0:  # MAN
                self.regs[6] = self.regs[78] if self.regs[78] > 0 else 550
                self.regs[82] = int(round((self.regs[6] / 10.0 / 100.0) * 327))
            return True
        elif reg_addr == 78:  # Manual output write
            self.regs[78] = val
            if self.regs[14] == 0:  # In MAN mode, update active output & ammeter
                self.regs[6] = val
                self.regs[82] = int(round((val / 10.0 / 100.0) * 327))
            return True
        elif reg_addr == 9:   # Repeat length set (100-2000 mm, refuses 99 and 2001)
            if val < 100 or val > 2000:
                return False
            self.regs[9] = val
            return True
        elif reg_addr == 20:  # Mark window (10-99 mm, refuses 9 and 100)
            if val < 10 or val > 99:
                return False
            self.regs[20] = val
            return True
        elif reg_addr == 17:  # Command register (1=CLR, 2=SCAN, 3=NEW JOB, 5=LOGOUT)
            if val == 3:      # NEW JOB resets counters
                self.regs[100] = 0
                self.regs[101] = 0
            elif val == 5:    # LOGOUT locks password at once
                self.regs[30] = 0
            self.regs[17] = val
            return True
            return True
        elif reg_addr == 21:  # Mark offset
            self.regs[21] = val
            return True
        elif reg_addr == 74:  # Set tension
            self.regs[74] = val
            return True
        elif reg_addr < len(self.regs):
            self.regs[reg_addr] = val
            return True
        return False

    def handle_request(self, data: bytes) -> bytes:
        if len(data) < 4:
            return b""
        if not verify_crc(data):
            return b""

        slave = data[0]
        if slave != self.slave_id:
            return b""

        fc = data[1]

        with self.lock:
            # FC 03: Read Holding Registers
            if fc == 3:
                start_addr = struct.unpack(">H", data[2:4])[0]
                qty = struct.unpack(">H", data[4:6])[0]
                if start_addr + qty > len(self.regs):
                    # Exception 2: Illegal Data Address
                    err_frame = bytes([slave, fc | 0x80, 2])
                    return err_frame + crc16(err_frame)

                byte_count = qty * 2
                res = bytearray([slave, fc, byte_count])
                for i in range(qty):
                    val = self.regs[start_addr + i] & 0xFFFF
                    res.extend(struct.pack(">H", val))
                return bytes(res) + crc16(bytes(res))

            # FC 06: Write Single Register
            elif fc == 6:
                reg_addr = struct.unpack(">H", data[2:4])[0]
                val = struct.unpack(">H", data[4:6])[0]
                if reg_addr >= len(self.regs):
                    err_frame = bytes([slave, fc | 0x80, 2])
                    return err_frame + crc16(err_frame)

                success = self._apply_register_write(reg_addr, val)
                if not success:
                    # Exception 4: Slave Device Failure / Refusal
                    err_frame = bytes([slave, fc | 0x80, 4])
                    return err_frame + crc16(err_frame)

                # Echo back the request on success
                echo = data[:6]
                return echo + crc16(echo)

            # FC 16 (0x10): Write Multiple Registers
            elif fc == 16:
                start_addr = struct.unpack(">H", data[2:4])[0]
                qty = struct.unpack(">H", data[4:6])[0]
                byte_cnt = data[6]
                values = [struct.unpack(">H", data[7 + i*2 : 9 + i*2])[0] for i in range(qty)]

                for i, v in enumerate(values):
                    addr = start_addr + i
                    if addr < len(self.regs):
                        self._apply_register_write(addr, v)

                resp = bytearray([slave, fc])
                resp.extend(struct.pack(">HH", start_addr, qty))
                return bytes(resp) + crc16(bytes(resp))

            else:
                # Exception 1: Illegal Function
                err_frame = bytes([slave, fc | 0x80, 1])
                return err_frame + crc16(err_frame)

def run_server(host="0.0.0.0", port=5020, slave_id=1):
    slave = ModbusSlave(slave_id=slave_id)
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass

    # Resilient bind with retry backoff (resolves transient "Address already in use" on rapid restarts)
    max_retries = 15
    for attempt in range(1, max_retries + 1):
        try:
            server_sock.bind((host, port))
            break
        except OSError as e:
            if attempt == max_retries:
                print(f"[MODBUS-SIM] Fatal: Could not bind to {host}:{port} after {max_retries} attempts: {e}", file=sys.stderr)
                try:
                    server_sock.close()
                except Exception:
                    pass
                raise
            print(f"[MODBUS-SIM] Port {port} busy, waiting to bind ({attempt}/{max_retries})...")
            time.sleep(0.5)

    server_sock.listen(5)
    print(f"[MODBUS-SIM] Slave ID {slave_id} listening on {host}:{port} (socket://127.0.0.1:{port})")
    print(f"[MODBUS-SIM] Firmware=2001, Passcode=1212, Speed=100MPM, Line=OK")

    is_running = True

    def _shutdown(signum=None, frame=None):
        nonlocal is_running
        if not is_running:
            return
        is_running = False
        print("\n[MODBUS-SIM] Shutting down cleanly...")
        slave.running = False
        try:
            server_sock.close()
        except Exception:
            pass

    import signal
    try:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    except Exception:
        pass

    try:
        while is_running:
            try:
                server_sock.settimeout(1.0)
                client_sock, addr = server_sock.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                break

            print(f"[MODBUS-SIM] Connection accepted from {addr}")
            client_sock.settimeout(1.0)
            try:
                buf = bytearray()
                while is_running:
                    try:
                        chunk = client_sock.recv(256)
                    except (socket.timeout, TimeoutError):
                        continue
                    except OSError:
                        break

                    if not chunk:
                        # Client disconnected cleanly
                        break
                    buf.extend(chunk)

                    # Frame processing loop
                    while len(buf) >= 4:
                        if buf[0] != slave_id:
                            # Advance past non-matching slave id
                            del buf[0]
                            continue

                        fc = buf[1]
                        if fc in (3, 6):
                            expected_len = 8
                        elif fc == 16:
                            if len(buf) < 7:
                                break  # Need byte count
                            expected_len = 7 + buf[6] + 2
                        else:
                            expected_len = 8

                        if len(buf) < expected_len:
                            break

                        frame = bytes(buf[:expected_len])
                        del buf[:expected_len]

                        reply = slave.handle_request(frame)
                        if reply:
                            try:
                                client_sock.sendall(reply)
                            except OSError:
                                break
            except Exception:
                pass
            finally:
                try:
                    client_sock.close()
                except Exception:
                    pass
                print(f"[MODBUS-SIM] Connection closed for {addr}")
    except KeyboardInterrupt:
        _shutdown()
    finally:
        _shutdown()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Modbus RTU Slave Simulator for FBARX")
    parser.add_argument("--port", type=int, default=5020, help="TCP port to listen on (default: 5020)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP to bind (default: 0.0.0.0)")
    parser.add_argument("--slave", type=int, default=1, help="Modbus slave ID (default: 1)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, slave_id=args.slave)
