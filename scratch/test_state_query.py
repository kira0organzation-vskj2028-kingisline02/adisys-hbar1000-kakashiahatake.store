import sqlite3
import json
import time
from pathlib import Path

DB = Path("rice_vision.db")

def now(): return time.strftime("%Y-%m-%dT%H:%M:%S")

def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c

def one(c, sql, a=()):
    r = c.execute(sql, a).fetchone()
    return dict(r) if r else None

def rows(c, sql, a=()):
    return [dict(r) for r in c.execute(sql, a).fetchall()]

# Test query machine_state
c = conn()
m = one(c, "SELECT * FROM machine_state WHERE id=1")
print("m state:", m)
c.close()
