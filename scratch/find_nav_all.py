import glob

for fn in glob.glob('static/*.html') + glob.glob('*.html'):
    with open(fn, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if 'data-target="screen-' in line or 'nav-tabs' in line:
                print(f'{fn}:{i+1}: {line.strip()[:100]}')
