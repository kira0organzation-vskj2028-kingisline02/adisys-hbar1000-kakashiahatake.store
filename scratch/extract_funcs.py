import re
import json

with open("static/index.html", "r", encoding="utf-8") as f:
    text = f.read()
    lines = text.splitlines()

# Let's find all script ranges
script_ranges = []
in_script = False
start_idx = 0
for i, line in enumerate(lines, 1):
    if "<script" in line:
        in_script = True
        start_idx = i
    if "</script>" in line and in_script:
        script_ranges.append((start_idx, i))
        in_script = False

print(f"Script ranges: {script_ranges}")

# Let's extract functions inside scripts
functions = []
# Patterns to find:
# 1. function name(...) {
# 2. window.name = function(...) {
# 3. window.name = (...) => {
# 4. const/let/var name = function(...) {
# 5. const/let/var name = (...) => {
# 6. async function name(...) {

func_pattern = re.compile(
    r'(?:'
    r'(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)|'
    r'window\.([a-zA-Z0-9_$]+)\s*=\s*(?:async\s+)?(?:function\s*)?\(([^)]*)\)|'
    r'(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s+)?(?:function\s*)?\(([^)]*)\)\s*=>|'
    r'([a-zA-Z0-9_$]+)\s*:\s*(?:async\s+)?function\s*\(([^)]*)\)|'
    r'([a-zA-Z0-9_$]+)\s*\(([^)]*)\)\s*\{'
    r')'
)

# Let's do a more robust parsing line-by-line of functions
# We can find the start of each function and track brace depth to find the end line.
found_funcs = []

for s_start, s_end in script_ranges:
    for line_num in range(s_start, s_end + 1):
        line = lines[line_num - 1]
        
        # Check standard function
        m = re.search(r'(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)', line)
        if m:
            found_funcs.append({
                'name': m.group(1),
                'params': m.group(2).strip(),
                'type': 'function',
                'line': line_num,
                'decl': line.strip()
            })
            continue
            
        # Check window.name = ...
        m = re.search(r'window\.([a-zA-Z0-9_$]+)\s*=\s*(?:async\s+)?(?:function\s*)?\(([^)]*)\)', line)
        if m:
            found_funcs.append({
                'name': m.group(1),
                'params': m.group(2).strip(),
                'type': 'window_assign',
                'line': line_num,
                'decl': line.strip()
            })
            continue

        # Check const/let/var name = ...
        m = re.search(r'(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s+)?(?:\(([^)]*)\)|[a-zA-Z0-9_$]+)\s*=>', line)
        if m:
            p = m.group(2) if m.group(2) else ""
            found_funcs.append({
                'name': m.group(1),
                'params': p.strip(),
                'type': 'arrow_func',
                'line': line_num,
                'decl': line.strip()
            })
            continue

print(f"Total discovered functions: {len(found_funcs)}")

# For each function, let's find its end line by brace matching
for f_info in found_funcs:
    start_line = f_info['line']
    # start from start_line and count braces
    depth = 0
    found_first_brace = False
    end_line = start_line
    for l_idx in range(start_line - 1, len(lines)):
        l_text = lines[l_idx]
        for ch in l_text:
            if ch == '{':
                depth += 1
                found_first_brace = True
            elif ch == '}':
                depth -= 1
                if found_first_brace and depth == 0:
                    end_line = l_idx + 1
                    break
        if found_first_brace and depth == 0:
            break
    f_info['end_line'] = end_line
    f_info['code'] = "\n".join(lines[start_line - 1 : end_line])

# Now inspect code of each function:
# - localStorage
# - fetch
# - setTimeout / setInterval
# - calculations (percentages, counts, Math.round, banding, averages)
# - passcodes (1111, 2222, 3333, 4444)
# - state mutations (window.HMI_STATE, activeJob, etc.)

for f_info in found_funcs:
    code = f_info['code']
    f_info['has_ls'] = bool(re.search(r'localStorage|sessionStorage', code))
    f_info['has_fetch'] = bool(re.search(r'fetch\s*\(', code))
    f_info['has_timer'] = bool(re.search(r'setInterval|setTimeout', code))
    f_info['has_passcode'] = bool(re.search(r'[\'"](?:1111|2222|3333|4444)[\'"]', code))
    f_info['has_math'] = bool(re.search(r'Math\.(?:round|floor|ceil|abs|sqrt|pow)|(?:sum|total|avg|percent|band|count)', code, re.IGNORECASE))
    f_info['has_dom'] = bool(re.search(r'document\.|classList|\.style|\.textContent|\.innerHTML|\.value', code))

with open("scratch/all_functions.json", "w", encoding="utf-8") as out:
    # Save summary without full code
    summary = [{k: v for k, v in f.items() if k != 'code'} for f in found_funcs]
    json.dump(summary, out, indent=2)

print("Saved function summaries to scratch/all_functions.json")
