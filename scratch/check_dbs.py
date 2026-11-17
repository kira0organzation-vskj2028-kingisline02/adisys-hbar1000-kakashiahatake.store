import sqlite3, glob

for db in glob.glob('*.db') + glob.glob('*.sqlite*'):
    print('DB:', db)
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cur.fetchall()]
        print('  Tables:', tables)
        if 'production_records' in tables:
            cur.execute("SELECT count(*) FROM production_records")
            cnt = cur.fetchone()[0]
            print(f'  production_records count: {cnt}')
            cur.execute("SELECT * FROM production_records LIMIT 3")
            rows = cur.fetchall()
            print('  Sample rows:', rows)
        conn.close()
    except Exception as e:
        print('  Error:', e)
