import sqlite3
c = sqlite3.connect('rice_vision.db')
c.row_factory = sqlite3.Row
print('--- RECIPES ---')
for r in c.execute('SELECT recipe_id, name, repeat_length_mm, width_mm, mark_window_mm, mark_offset_mm FROM recipes').fetchall():
    print(dict(r))

print('\n--- RELEVANT SETTINGS ---')
for r in c.execute('SELECT key, value FROM settings').fetchall():
    k = r['key']
    if any(x in k for x in ['cal', 'scale', 'zero', 'nom', 'dist', 'bag', 'camera']):
        print(f"{r['key']}: {r['value']}")

print('\n--- ACTIVE STATE ---')
for r in c.execute('SELECT * FROM active_state').fetchall():
    print(dict(r))
