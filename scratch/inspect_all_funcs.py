import json
import re

with open("scratch/all_functions.json", "r", encoding="utf-8") as f:
    funcs = json.load(f)

with open("static/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

def get_code(start, end):
    return "\n".join(lines[start - 1 : end])

for fn in funcs:
    code = get_code(fn['line'], fn['end_line'])
    fn['code_snippet'] = code[:300]
    fn['code_full'] = code

with open("scratch/funcs_with_code.json", "w", encoding="utf-8") as f:
    json.dump(funcs, f, indent=2)

print(f"Loaded {len(funcs)} functions with code.")
