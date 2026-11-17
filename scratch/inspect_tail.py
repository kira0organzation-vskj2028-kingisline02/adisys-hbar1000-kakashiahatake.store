import re

with open("static/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i in range(8300, len(lines)):
    line = lines[i]
    m = re.findall(r'(?:(?:const|let|var|function)\s+([a-zA-Z0-9_$]+)|([a-zA-Z0-9_$]+)\s*[:=]\s*(?:async\s+)?function|([a-zA-Z0-9_$]+)\s*\([^)]*\)\s*\{)', line)
    for g in m:
        name = g[0] or g[1] or g[2]
        if name and name not in ['if', 'for', 'while', 'switch', 'catch', 'return']:
            # filter out common single-letter vars
            if len(name) > 2 and ('function' in line or '=>' in line or 'async' in line):
                print(f"Line {i+1:5d}: {name:30s} -> {line.strip()[:90]}")
