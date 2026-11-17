import re

with open("static/index.html", "r", encoding="utf-8") as f:
    text = f.read()

# Let's search for objects with methods e.g. const RecipeDB = { ... } or window.RecipeDB = { ... }
objects = re.findall(r'(?:const|let|var|window\.)\s*([a-zA-Z0-9_$]+)\s*=\s*\{([^}]+)\}', text)
print(f"Discovered objects: {[o[0] for o in objects]}")

# Let's search for all keys in RecipeDB, RecipeMatch, etc.
for name in ['RecipeDB', 'RecipeMatch', 'LS', 'FBarX']:
    m = re.search(r'(?:const|let|var|window\.)\s*' + name + r'\s*=\s*\{', text)
    if m:
        start = m.start()
        # Find closing brace
        depth = 0
        found = False
        end = start
        for idx in range(start, len(text)):
            if text[idx] == '{':
                depth += 1
                found = True
            elif text[idx] == '}':
                depth -= 1
                if found and depth == 0:
                    end = idx + 1
                    break
        block = text[start:end]
        print(f"\n--- Methods in {name} ---")
        methods = re.findall(r'([a-zA-Z0-9_$]+)\s*(?:\([^)]*\)|\:\s*(?:async\s+)?function)', block)
        print(methods)
