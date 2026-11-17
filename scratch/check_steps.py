import json

with open(r'C:\Users\Admin\.gemini\antigravity\brain\c822483c-07f0-4930-a0f0-6eb6fb130cb4\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        step = d.get('step_index', 0)
        if 14450 <= step <= 14525:
            tc_list = d.get('tool_calls', [])
            if tc_list:
                for tc in tc_list:
                    name = tc.get('name')
                    args = tc.get('args', {})
                    target = args.get('Path') or args.get('CommandLine', '')
                    print(f"Step {step}: {name} -> {str(target)[:100]}")
