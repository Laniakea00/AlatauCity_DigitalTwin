"""Translate a JSON list of Russian strings to EN/KZ with Gemini (parallel batches) and append to strings.json.
usage: python3 loc_list.py <repo root> <list.json>"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
from gemini import ask
root, lst = sys.argv[1], sys.argv[2]
new = json.load(open(lst, encoding='utf-8'))
cat_path = os.path.join(root, 'UnityProject/Assets/Resources/Loc/strings.json')
raw = open(cat_path, encoding='utf-8').read(); cat = json.loads(raw); have = {r['r'] for r in cat['s']}
new = [s for s in new if s not in have]
ph = lambda x: sorted(set(re.findall(r'\{\d+\}', x)))
PROMPT = open(os.path.join(os.path.dirname(__file__), 'loc_add.py'), encoding='utf-8').read().split('PROMPT = """')[1].split('"""')[0]
def tr(batch):
    for attempt in range(3):
        try:
            res = ask('gemini-4-argon', PROMPT + json.dumps(batch, ensure_ascii=False, indent=0), json_out=True, thinking='low')
            rows = json.loads(res); return {r['ru']: r for r in rows if isinstance(r, dict) and 'ru' in r}
        except Exception as e: err = e
    print('batch failed', err); return {}
batches = [new[i:i + 40] for i in range(0, len(new), 40)]
with ThreadPoolExecutor(8) as ex: results = list(ex.map(tr, batches))
out, miss = [], []
for batch, by in zip(batches, results):
    for s in batch:
        r = by.get(s)
        if not r or not r.get('en') or not r.get('kz'): miss.append(s); continue
        if ph(s) != ph(r['en']) or ph(s) != ph(r['kz']): miss.append(s); continue
        out.append({'r': s, 'e': r['en'], 'k': r['kz']})
cat['s'].extend(out)
open(cat_path, 'w', encoding='utf-8', newline='').write(json.dumps(cat, ensure_ascii=False, separators=(',', ':')) + ('\n' if raw.endswith('\n') else ''))
json.dump(miss, open(lst + '.miss.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
print('added', len(out), 'missed', len(miss))
