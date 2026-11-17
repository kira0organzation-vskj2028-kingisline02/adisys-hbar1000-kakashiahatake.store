import sqlite3

def update_db():
    conn = sqlite3.connect('rice_vision.db')
    cur = conn.cursor()
    # Update recipes for rice bags (1860 mm length, 535 mm width)
    cur.execute("UPDATE recipes SET repeat_length_mm = 1860, width_mm = 535 WHERE recipe_id IN (1, 2, 3, 8)")
    
    settings = [
        ("scale_px_per_mm", "1.0"),
        ("scale_px_per_mm_x", "1.0"),
        ("scale_px_per_mm_y", "1.0"),
        ("working_distance_m", "1.5"),
        ("bag_length_mm", "1860.0"),
        ("bag_width_mm", "535.0"),
        ("between_bags_mm", "50.0"),
        ("nominal_length_mm", "1860.0")
    ]
    for k, v in settings:
        cur.execute("INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?, ?, datetime('now'))", (k, v))
        
    cur.execute("UPDATE calibration_store SET value = '1860' WHERE category = 'stn2' AND key = 'cylinderCircumference'")
    conn.commit()
    
    print("UPDATED RECIPES:", cur.execute("SELECT recipe_id, name, repeat_length_mm, width_mm FROM recipes").fetchall())
    print("UPDATED SETTINGS:", cur.execute("SELECT key, value FROM settings WHERE key IN ('scale_px_per_mm', 'working_distance_m', 'bag_length_mm', 'bag_width_mm', 'between_bags_mm', 'nominal_length_mm')").fetchall())
    conn.close()

if __name__ == '__main__':
    update_db()
