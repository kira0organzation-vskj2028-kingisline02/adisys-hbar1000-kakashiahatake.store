"""HTTP glue for /api/fbarx/*  (stdlib only).  server.py delegates here.

* Error mapping: FieldError / BoardRefused -> 400 {"error", "field"};  BoardError -> 503 {"error", "status"}
* Login: set env HMI_AUTH="user:password" and every request (page and /api/*) needs HTTP Basic auth.
* STN 2 CALIBRATE passcode is checked here, not in the page. POST /api/fbarx/unlock {"code"} returns a
  token; /api/fbarx/calibration needs it in the X-Cal-Token header. Passcode: env STN2_CAL_PASSCODE.
* The board password (1212) never leaves fbarx_link.py.
"""
import base64
import hmac
import os
import secrets
import time

from fbarx_link import BoardError, FieldError

CAL_PASSCODE = os.environ.get("STN2_CAL_PASSCODE", "3333")
TOKEN_TTL_S = 300
_tokens = {}                 # token -> expiry
_fails = {"n": 0, "until": 0.0}


def auth_enabled():
    return bool(os.environ.get("HMI_AUTH"))


def basic_auth_ok(header):
    expected = os.environ.get("HMI_AUTH", "")
    if not expected:
        return True
    if not header or not header.startswith("Basic "):
        return False
    try:
        given = base64.b64decode(header[6:]).decode()
    except Exception:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def _token_ok(tok):
    exp = _tokens.get(tok or "")
    if exp and exp > time.time():
        _tokens[tok] = time.time() + TOKEN_TTL_S          # sliding window
        return True
    _tokens.pop(tok or "", None)
    return False


def _unlock(d):
    now = time.time()
    if now < _fails["until"]:
        return 429, {"error": "too many wrong codes, wait %d s" % int(_fails["until"] - now), "field": "password"}
    if hmac.compare_digest(str(d.get("code", "")).encode(), CAL_PASSCODE.encode()):
        _fails["n"] = 0
        for t in [t for t, e in _tokens.items() if e < now]:
            _tokens.pop(t, None)
        tok = secrets.token_urlsafe(16)
        _tokens[tok] = now + TOKEN_TTL_S
        return 200, {"ok": True, "token": tok, "ttl": TOKEN_TTL_S}
    _fails["n"] += 1
    if _fails["n"] >= 5:
        _fails["n"], _fails["until"] = 0, now + 30
    return 403, {"error": "wrong passcode", "field": "password"}


def route_get(link, path):
    """Returns (status, body) or None if the path is not ours."""
    if path == "/api/fbarx/state":
        return 200, link.state()
    if path == "/api/fbarx/calibration":
        try:
            return 200, link.get_calibration()
        except BoardError as e:
            return 503, {"error": str(e), "status": link.status()}
    return None


def _first(d, *keys):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def route_post(link, path, d, headers):
    """Returns (status, body) or None if the path is not ours. headers: any mapping with .get()."""
    if not path.startswith("/api/fbarx/"):
        return None
    name = path[len("/api/fbarx/"):]
    d = d or {}
    try:
        if name == "unlock":
            return _unlock(d)
        if name == "calibration":
            is_only_offset = (list(d.keys()) == ["markOffset"])
            if not is_only_offset and not _token_ok(headers.get("X-Cal-Token")):
                return 403, {"error": "STN 2 passcode required", "field": "password"}
            return 200, {"ok": True, "calibration": link.set_calibration(d)}
        if name == "mode":
            link.set_mode(d.get("mode"))
            return 200, {"ok": True, "mode": d.get("mode")}
        if name == "output":
            v = _first(d, "pct", "output")
            link.set_output(v)
            return 200, {"ok": True, "pct": float(v)}
        if name == "repeat_length":
            val = _first(d, "repeatLength", "value")
            link.set_repeat_length(val)
            rep_clamped = link.want_repeat if link.want_repeat is not None else link.regs[9]
            return 200, {"ok": True, "repeatLength": rep_clamped}
        if name == "mark_window":
            link.set_mark_window(_first(d, "markWindow", "value"))
            return 200, {"ok": True, "markWindow": int(float(_first(d, "markWindow", "value")))}
        if name == "mark_offset":
            link.set_mark_offset(_first(d, "markOffset", "value"))
            return 200, {"ok": True, "markOffset": int(float(_first(d, "markOffset", "value")))}
        if name == "cmd":
            link.send_cmd(_first(d, "cmd", "name"))
            return 200, {"ok": True, "cmd": _first(d, "cmd", "name")}
        if name == "tension":
            v = float(_first(d, "kg", "tension", "value"))
            link.set_tension(v)
            return 200, {"ok": True, "kg": v, "setTension": v, "kp": link.kp}
        if name == "second_slave_tension":
            addr = int(_first(d, "slave", "slaveAddress", "address", default=2))
            v = float(_first(d, "kg", "tension", "value"))
            link.set_second_slave_tension(addr, v)
            return 200, {"ok": True, "slave": addr, "kg": v}
        if name == "recipe":
            res = link.apply_recipe(d)
            return (200 if res["ok"] else 207), res
        return 404, {"error": "unknown endpoint"}
    except FieldError as e:
        return 400, {"error": str(e), "field": e.field}
    except BoardError as e:
        return 503, {"error": str(e), "status": link.status()}

