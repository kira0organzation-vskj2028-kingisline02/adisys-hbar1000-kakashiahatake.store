import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'stn1-cal-screen' in l:
        print(f'{i+1}: {l.strip()[:100]}')
