import re

with open("static/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

print("==================== LOCALSTORAGE AUDIT ====================")
for i, line in enumerate(lines, 1):
    if "localStorage" in line or "sessionStorage" in line:
        print(f"Line {i:5d}: {line.strip()}")

print("\n==================== TIMERS (setInterval / setTimeout) ====================")
for i, line in enumerate(lines, 1):
    if "setInterval" in line or "setTimeout" in line:
        print(f"Line {i:5d}: {line.strip()[:140]}")

print("\n==================== FETCH CALLS ====================")
for i, line in enumerate(lines, 1):
    if "fetch(" in line or "fetch (" in line:
        print(f"Line {i:5d}: {line.strip()[:140]}")

print("\n==================== SENSORS & SIMULATION ====================")
for i, line in enumerate(lines, 1):
    if any(k in line.lower() for k in ["simulat", "startsimulated", "sim_error", "sim_frame", "score(", "loadimage("]):
        if not line.strip().startswith("//") and not line.strip().startswith("/*"):
            print(f"Line {i:5d}: {line.strip()[:140]}")
