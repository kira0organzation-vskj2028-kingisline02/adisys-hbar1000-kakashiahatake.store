import sqlite3
from pathlib import Path

DB = Path("rice_vision.db")
c = sqlite3.connect(DB)

c.execute("""CREATE TABLE IF NOT EXISTS machine_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    stn1_mode TEXT NOT NULL DEFAULT 'OFF',
    stn1_output_pct REAL NOT NULL DEFAULT 0.0,
    stn1_ammeter REAL NOT NULL DEFAULT 0.0,
    stn1_unit TEXT NOT NULL DEFAULT 'KG',
    stn1_brake_type TEXT NOT NULL DEFAULT 'magnetic',
    stn1_stension REAL NOT NULL DEFAULT 5.0,
    stn1_atension REAL NOT NULL DEFAULT 0.0,
    stn2_mode TEXT NOT NULL DEFAULT 'AUTO',
    stn2_output_pct REAL NOT NULL DEFAULT 55.0,
    stn2_ammeter REAL NOT NULL DEFAULT 1.78,
    stn2_speed_mpm INTEGER NOT NULL DEFAULT 100,
    stn2_brake_type TEXT NOT NULL DEFAULT 'magnetic',
    stn2_repeat_length_actual REAL NOT NULL DEFAULT 740.0,
    stn2_repeat_length_set REAL NOT NULL DEFAULT 740.0,
    stn2_mark_window INTEGER NOT NULL DEFAULT 40,
    stn2_mark_offset INTEGER NOT NULL DEFAULT 0,
    job_active INTEGER NOT NULL DEFAULT 0,
    job_id INTEGER,
    job_recipe_id INTEGER,
    job_recipe_name TEXT,
    job_operator TEXT,
    job_start_time TEXT,
    job_end_time TEXT,
    cnt_0_7 INTEGER NOT NULL DEFAULT 0,
    cnt_8_15 INTEGER NOT NULL DEFAULT 0,
    cnt_16_25 INTEGER NOT NULL DEFAULT 0,
    cnt_26_w INTEGER NOT NULL DEFAULT 0,
    cnt_unscored INTEGER NOT NULL DEFAULT 0,
    cnt_total INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)""")
c.execute("INSERT OR IGNORE INTO machine_state(id) VALUES(1)")

c.execute("""CREATE TABLE IF NOT EXISTS calibration_store (
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (category, key)
)""")

# Seed default calibration values if not present
default_cal = [
    ('stn1_control', 'propBand', '20.0'),
    ('stn1_control', 'integTime', '15.0'),
    ('stn1_control', 'derivTime', '2.0'),
    ('stn1_control', 'minOutput', '0.0'),
    ('stn1_control', 'maxOutput', '100.0'),
    ('stn1_loadcell', 'zeroRaw', '1024'),
    ('stn1_loadcell', 'calWeight', '25.0'),
    ('stn1_loadcell', 'spanRaw', '16384'),
    ('stn2', 'encoderPprSet', '1024'),
    ('stn2', 'cylinderCircumference', '740'),
    ('stn2', 'brakeCurrentCal', '2500'),
    ('stn2', 'acErr', '7.0'),
    ('stn2', 'dcErr', '15.0'),
    ('stn2', 'spkErr', '25.0'),
]
for cat, k, v in default_cal:
    c.execute("INSERT OR IGNORE INTO calibration_store(category, key, value) VALUES(?,?,?)", (cat, k, v))

c.commit()

row = c.execute("SELECT * FROM machine_state WHERE id=1").fetchone()
print("machine_state initialized:", row)
c.close()
