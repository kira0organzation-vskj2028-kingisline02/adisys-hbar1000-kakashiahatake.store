-- RiceRecipeVision HMI database (SQLite 3) - FBAR 1000
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. OPERATORS ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operators (
  operator_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- shown in OPERATOR NAME dropdown
  emp_code      TEXT UNIQUE,
  role          TEXT NOT NULL DEFAULT 'OPERATOR' CHECK (role IN ('OPERATOR','SUPERVISOR','ADMIN')),
  photo_path    TEXT,                                  -- optional operator photo (the 320x240 capture)
  is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
);

-- 2. RECIPES (one row per bag / job) ------------------------------------------
CREATE TABLE IF NOT EXISTS recipes (
  recipe_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name             TEXT NOT NULL UNIQUE COLLATE NOCASE,
  brand_tamil      TEXT,
  product          TEXT,
  bag_weight_kg    REAL,
  repeat_length_mm INTEGER NOT NULL DEFAULT 740 CHECK (repeat_length_mm BETWEEN 100 AND 2000),
  width_mm         INTEGER NOT NULL DEFAULT 495 CHECK (width_mm BETWEEN 1 AND 1000),
  material         TEXT NOT NULL DEFAULT 'BOPP',
  mark_window_mm   INTEGER NOT NULL DEFAULT 40  CHECK (mark_window_mm BETWEEN 10 AND 99),
  mark_offset_mm   INTEGER NOT NULL DEFAULT 0   CHECK (mark_offset_mm BETWEEN -999 AND 999),
  s_tension_kg     REAL    NOT NULL DEFAULT 5.0 CHECK (s_tension_kg BETWEEN 0 AND 99.9),
  front_sensor INTEGER NOT NULL DEFAULT 0, front_mark INTEGER NOT NULL DEFAULT 0, front_background INTEGER NOT NULL DEFAULT 0,
  back_sensor  INTEGER NOT NULL DEFAULT 0, back_mark  INTEGER NOT NULL DEFAULT 0, back_background  INTEGER NOT NULL DEFAULT 0,
  front_image_path TEXT, back_image_path TEXT,
  front_image_name TEXT, back_image_name TEXT,
  created_by       INTEGER REFERENCES operators(operator_id) ON DELETE SET NULL,
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
);

-- 3. REFERENCE BAG IMAGES (JPEG kept on disk; DB keeps path + hash + size) -----
CREATE TABLE IF NOT EXISTS recipe_images (
  image_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  recipe_id    INTEGER NOT NULL REFERENCES recipes(recipe_id) ON DELETE CASCADE,
  image_name   TEXT NOT NULL,
  image_path   TEXT NOT NULL UNIQUE,                   -- relative to the DB folder
  mime_type    TEXT NOT NULL DEFAULT 'image/jpeg',
  width_px     INTEGER, height_px INTEGER, size_bytes INTEGER,
  sha256       TEXT NOT NULL,
  is_active    INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),  -- ACTIVE IMAGE shown on load screen
  template_blob BLOB,                                  -- optional: ORB/feature template for matching
  added_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_img_recipe ON recipe_images(recipe_id);

-- 4. PRODUCTION / INSPECTION REPORT (matches report table in the UI) ---------
CREATE TABLE IF NOT EXISTS production_records (
  record_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  logged_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  recipe_id   INTEGER REFERENCES recipes(recipe_id) ON DELETE SET NULL,
  image_name  TEXT,
  operator_id INTEGER REFERENCES operators(operator_id) ON DELETE SET NULL,
  operator    TEXT,                                    -- snapshot of name at log time
  c_0_7       INTEGER NOT NULL DEFAULT 0 CHECK (c_0_7  >= 0),
  c_8_15      INTEGER NOT NULL DEFAULT 0 CHECK (c_8_15 >= 0),
  c_16_25     INTEGER NOT NULL DEFAULT 0 CHECK (c_16_25 >= 0),
  c_26_w      INTEGER NOT NULL DEFAULT 0 CHECK (c_26_w >= 0),
  unscored    INTEGER NOT NULL DEFAULT 0 CHECK (unscored >= 0),
  window_mm   INTEGER DEFAULT 40,
  start_time  TEXT,
  end_time    TEXT,
  total       INTEGER NOT NULL DEFAULT 0 CHECK (total >= 0)
);
CREATE INDEX IF NOT EXISTS ix_prod_time ON production_records(logged_at);
CREATE INDEX IF NOT EXISTS ix_prod_op   ON production_records(operator_id);

-- 5. CAMERA VERIFY LOG (READ & COMPARE captures) -----------------------------
CREATE TABLE IF NOT EXISTS camera_verifications (
  verify_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  verified_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  operator_id  INTEGER REFERENCES operators(operator_id) ON DELETE SET NULL,
  recipe_id    INTEGER REFERENCES recipes(recipe_id) ON DELETE SET NULL,
  matched_image_id INTEGER REFERENCES recipe_images(image_id) ON DELETE SET NULL,
  capture_path TEXT,
  confidence   REAL CHECK (confidence BETWEEN 0 AND 1),
  result       TEXT NOT NULL CHECK (result IN ('MATCH','MISMATCH','NO_READ'))
);

-- 6. CALIBRATION STORE (STN1 / STN2 / CAMERA key-value store) ----------------
CREATE TABLE IF NOT EXISTS calibration_store (
  category   TEXT NOT NULL,
  key        TEXT NOT NULL,                            -- acErr, dcErr, brakeType, markSkipAlarm ...
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  PRIMARY KEY (category, key)
);

-- 7. ACTIVE RECIPE (single row) ----------------------------------------------
CREATE TABLE IF NOT EXISTS active_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  recipe_id INTEGER REFERENCES recipes(recipe_id) ON DELETE SET NULL,
  operator_id INTEGER REFERENCES operators(operator_id) ON DELETE SET NULL,
  loaded_at TEXT
);
INSERT OR IGNORE INTO active_state(id) VALUES (1);

CREATE TRIGGER IF NOT EXISTS trg_recipe_upd AFTER UPDATE ON recipes
BEGIN UPDATE recipes SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now','localtime') WHERE recipe_id = NEW.recipe_id; END;

-- only one ACTIVE image per recipe
CREATE TRIGGER IF NOT EXISTS trg_one_active_img AFTER UPDATE OF is_active ON recipe_images WHEN NEW.is_active = 1
BEGIN UPDATE recipe_images SET is_active = 0 WHERE recipe_id = NEW.recipe_id AND image_id <> NEW.image_id; END;

-- Report view, same columns as the HMI report table
CREATE VIEW IF NOT EXISTS v_report AS
SELECT logged_at AS "Date Time", image_name AS "Image / Name", operator AS "Operator",
       c_0_7 AS "0-7", c_8_15 AS "8-15", c_16_25 AS "16-25", c_26_w AS "26-w", unscored AS "Unscored", total AS "Total"
FROM production_records ORDER BY logged_at DESC;

-- ============================ PHASE 1 ADDITIONS ==============================
-- 8. SETTINGS (camera source, thresholds, ...)
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime'))
);
INSERT OR IGNORE INTO settings(key,value) VALUES ('camera_source','laptop');   -- laptop | pi
INSERT OR IGNORE INTO settings(key,value) VALUES ('match_min_inliers','12');

-- 9. RECIPE LOAD HISTORY: every CONFIRM TO LOAD, with a full snapshot of the values
CREATE TABLE IF NOT EXISTS recipe_loads (
  load_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  loaded_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  recipe_id   INTEGER REFERENCES recipes(recipe_id) ON DELETE SET NULL,
  recipe_name TEXT NOT NULL,
  operator_id INTEGER REFERENCES operators(operator_id) ON DELETE SET NULL,
  operator    TEXT NOT NULL,
  load_source TEXT NOT NULL CHECK (load_source IN ('NAME','IMAGE','CAMERA')),
  image_id    INTEGER REFERENCES recipe_images(image_id) ON DELETE SET NULL,
  verify_id   INTEGER REFERENCES camera_verifications(verify_id) ON DELETE SET NULL,
  params_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_loads_time ON recipe_loads(loaded_at);

-- 10. EVENT / AUDIT LOG
CREATE TABLE IF NOT EXISTS event_log (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  operator TEXT, recipe_name TEXT,
  event    TEXT NOT NULL,        -- CALIBRATION_LOGIN, RECIPE_SAVED, RECIPE_LOADED, CAMERA_SOURCE ...
  detail   TEXT
);
CREATE INDEX IF NOT EXISTS ix_event_ts ON event_log(ts);
