import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r'<div class=[\'"]cal-(?:zero-row|info)[\s\S]*?</div>\s*</div>', text)
for m in matches[:5]:
    print('--- MATCH ---')
    print(m)
