import re
import json

with open("static/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()
content = "".join(lines)

print("=== 1. LOCALSTORAGE & SESSIONSTORAGE KEYS ===")
ls_patterns = [
    r'localStorage\.getItem\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
    r'localStorage\.setItem\(\s*[\'"]([^\'"]+)[\'"]\s*,',
    r'localStorage\.removeItem\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
    r'localStorage\[[\'"]([^\'"]+)[\'"]\]',
    r'sessionStorage\.getItem\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
    r'sessionStorage\.setItem\(\s*[\'"]([^\'"]+)[\'"]\s*,',
]
ls_keys = set()
for pat in ls_patterns:
    for m in re.finditer(pat, content):
        ls_keys.add(m.group(1))

# Also search for direct variable usage e.g. localStorage.getItem(LS_KEY)
ls_dynamic = re.findall(r'localStorage\.(?:getItem|setItem|removeItem)\(\s*([a-zA-Z0-9_]+)\s*[,)]', content)
print("Static keys found:", sorted(list(ls_keys)))
print("Dynamic variables passed to localStorage:", sorted(list(set(ls_dynamic))))

# Print lines where localStorage or sessionStorage appears
print("\nAll lines with localStorage / sessionStorage:")
for i, line in enumerate(lines, 1):
    if "localStorage" in line or "sessionStorage" in line:
        print(f"  Line {i}: {line.strip()[:100]}")

print("\n=== 2. FUNCTIONS IN INDEX.HTML ===")
# Match:
# function name(...)
# window.name = function(...)
# window.name = (...) =>
# async function name(...)
# const/let/var name = function(...) or (...) =>
func_defs = []
for i, line in enumerate(lines, 1):
    # standard function
    m1 = re.match(r'^\s*(async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)', line)
    if m1:
        func_defs.append((i, m1.group(2), m1.group(3).strip(), "function"))
        continue
    # window.name = function or arrow
    m2 = re.match(r'^\s*window\.([a-zA-Z0-9_$]+)\s*=\s*(async\s+)?(?:function\s*)?\(([^)]*)\)\s*(?:=>)?', line)
    if m2:
        func_defs.append((i, m2.group(1), m2.group(3).strip(), "window"))
        continue
    # const/let/var name = ...
    m3 = re.match(r'^\s*(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(async\s+)?(?:function\s*)?\(([^)]*)\)\s*=>', line)
    if m3:
        func_defs.append((i, m3.group(1), m3.group(3).strip(), "var_arrow"))
        continue

print(f"Total function definitions matched: {len(func_defs)}")
for i, name, params, ftype in func_defs:
    print(f"  Line {i:5d}: {name}({params}) [{ftype}]")

print("\n=== 3. SETINTERVAL & SETTIMEOUT ===")
timers = []
for i, line in enumerate(lines, 1):
    if "setInterval" in line or "setTimeout" in line:
        timers.append((i, line.strip()))
print(f"Total timers matched: {len(timers)}")
for i, line in timers:
    print(f"  Line {i:5d}: {line[:120]}")

print("\n=== 4. FETCH CALLS ===")
fetches = []
for i, line in enumerate(lines, 1):
    if "fetch(" in line or "fetch (" in line:
        fetches.append((i, line.strip()))
print(f"Total fetch calls: {len(fetches)}")
for i, line in fetches:
    print(f"  Line {i:5d}: {line[:120]}")

print("\n=== 5. PASSCODE MATCHES ===")
for i, line in enumerate(lines, 1):
    for code in ['3333', '4444', '1234', '0000', '9999', '1111']:
        if code in line and not line.strip().startswith('<!--'):
            print(f"  Line {i:5d} [{code}]: {line.strip()[:100]}")
