"""HTTP glue for /api/fbarx/* and unified authentication (stdlib only). server.py delegates here.

* Error mapping: FieldError / BoardRefused -> 400 {"error", "field"}; BoardError -> 503 {"error", "status"}
* Login: set env HMI_AUTH="user:password" and every request (page and /api/*) needs HTTP Basic auth.
* Station & Calibration passcodes moved to config.py with unified rate limiting / lockout (30s after 5 fails).
* POST /api/fbarx/unlock {"code"} returns a token; calibration writes require X-Cal-Token header.
* The board password (1212) never leaves fbarx_link.py.
"""
import base64
import hmac
import os
import secrets
import time

import config
from fbarx_link import BoardError, FieldError

TOKEN_TTL_S = config.TOKEN_TTL_S
_tokens = {}                 # token -> {"expires": float, "role": str} or float
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


def _token_ok(tok, required_role=None):
    if not tok:
        return False
    data = _tokens.get(tok)
    if not data:
        return False
    now = time.time()
    if isinstance(data, dict):
        exp = data.get("expires", 0.0)
        role = data.get("role")
        if exp > now:
            if required_role and role and role != required_role:
                return False
            data["expires"] = now + TOKEN_TTL_S  # sliding window
            return True
    elif isinstance(data, (int, float)):
        if data > now:
            _tokens[tok] = now + TOKEN_TTL_S
            return True
    _tokens.pop(tok, None)
    return False


def verify_cal_token(tok, required_role=None):
    """Public helper to verify calibration token across endpoints."""
    return _token_ok(tok, required_role=required_role)


def get_token_info(tok):
    """Get active session metadata (role, remaining TTL)."""
    if not tok:
        return None
    data = _tokens.get(tok)
    if not data:
        return None
    now = time.time()
    if isinstance(data, dict):
        exp = data.get("expires", 0.0)
        if exp > now:
            return {"role": data.get("role", "operator"), "expires_in": int(exp - now)}
    elif isinstance(data, (int, float)):
        if data > now:
            return {"role": "stn2_cal", "expires_in": int(data - now)}
    return None


def _unlock(d):
    now = time.time()
    if now < _fails["until"]:
        wait_s = int(_fails["until"] - now)
        return 429, {"ok": False, "error": f"too many wrong codes, wait {wait_s} s", "field": "password", "wait_s": wait_s}

    code = str(d.get("code") if d.get("code") is not None else (d.get("passcode") or "")).strip()
    req_type = str(d.get("type") or "").strip()

    valid_role = None

    # Specific type requested
    if req_type in config.PASSCODES:
        expected = config.PASSCODES[req_type]
        if code and hmac.compare_digest(code.encode(), expected.encode()):
            valid_role = req_type
    elif req_type in ("cal_password", "calibrate_password", "recipecal_password", ""):
        # Check against all configured passcodes in priority order
        for role, pc in (
            ("stn1_control", config.STN1_CONTROL_PASSCODE),
            ("stn1_loadcell", config.STN1_LOADCELL_PASSCODE),
            ("stn2_cal", config.STN2_CAL_PASSCODE),
            ("recipe_cal", config.RECIPE_CAL_PASSCODE),
        ):
            if code and hmac.compare_digest(code.encode(), pc.encode()):
                valid_role = role
                break

    if valid_role:
        _fails["n"] = 0
        # Clean expired tokens
        for t, v in list(_tokens.items()):
            exp = v.get("expires", 0) if isinstance(v, dict) else v
            if exp < now:
                _tokens.pop(t, None)
        tok = secrets.token_urlsafe(16)
        _tokens[tok] = {"expires": now + TOKEN_TTL_S, "role": valid_role}
        return 200, {
            "ok": True,
            "token": tok,
            "role": valid_role,
            "ttl": TOKEN_TTL_S,
            "expires_in": TOKEN_TTL_S,
        }

    _fails["n"] += 1
    if _fails["n"] >= config.LOCKOUT_ATTEMPTS:
        _fails["n"] = 0
        _fails["until"] = now + config.LOCKOUT_DURATION_S
        return 429, {"ok": False, "error": f"too many wrong codes, wait {config.LOCKOUT_DURATION_S} s", "field": "password", "wait_s": config.LOCKOUT_DURATION_S}
    return 403, {"ok": False, "error": "wrong passcode", "field": "password"}


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


def _first(d, *keys, default=None):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return default


def route_post(link, path, d, headers):
    """Returns (status, body) or None if the path is not ours. headers: any mapping with .get()."""
    if path == "/api/unlock":
        return _unlock(d or {})
    if not path.startswith("/api/fbarx/"):
        return None
    name = path[len("/api/fbarx/"):]
    d = d or {}
    try:
        if name == "unlock":
            return _unlock(d)
        if name == "calibration":
            is_only_offset = (list(d.keys()) == ["markOffset"])
            cal_tok = headers.get("X-Cal-Token") or d.get("token")
            if not is_only_offset and not _token_ok(cal_tok):
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
