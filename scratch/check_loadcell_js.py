import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if any(k in line for k in ['cal-zero', 'cal-knownWeight', 'stn1Loadcell', 'stn1-loadcell', '±4.0']):
        print(f'{i+1}: {line.strip()[:120]}')
