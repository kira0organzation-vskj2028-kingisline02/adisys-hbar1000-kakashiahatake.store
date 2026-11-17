with open('static/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'data-target' in line or 'class="nav-tab' in line:
        print(f'{i+1}: {line.strip()[:100]}')
