import re

with open("static/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i in range(7600, 8300):
    line = lines[i]
    if re.search(r'(?:const|let|var|function|window\.)\s*([a-zA-Z0-9_$]+)', line):
        m = re.findall(r'(?:(?:const|let|var|function)\s+([a-zA-Z0-9_$]+)|([a-zA-Z0-9_$]+)\s*[:=]\s*(?:async\s+)?function|([a-zA-Z0-9_$]+)\s*\([^)]*\)\s*\{)', line)
        for g in m:
            name = g[0] or g[1] or g[2]
            if name and name not in ['if', 'for', 'while', 'switch', 'catch', 'return']:
                print(f"Line {i+1}: {name} -> {line.strip()[:100]}")
