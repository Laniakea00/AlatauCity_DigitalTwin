"""Add EN/KZ translations for new Russian C# literals to Assets/Resources/Loc/strings.json (append-only).
usage: python3 loc_add.py <repo root> [--files a.cs b.cs ...] [--dry]
Without --files: every .cs under UnityProject/Assets/Scripts. Translates only literals missing from strings.json, via Gemini."""
import json, os, re, sys, importlib.util
sys.path.insert(0, os.path.dirname(__file__))
from gemini import ask

args = sys.argv[1:]
root = args[0]; dry = '--dry' in args
files = args[args.index('--files') + 1:] if '--files' in args else None
if files: files = [f for f in files if not f.startswith('--')]
spec = importlib.util.spec_from_file_location('ex', os.path.join(root, 'UnityProject/Tools/loc/extract.py'))
src = open(os.path.join(root, 'UnityProject/Tools/loc/extract.py'), encoding='utf-8').read()
ns = {}; exec(src.split('res = {}')[0].replace('ROOT = sys.argv[1]; ', ''), ns)
lits, CYR = ns['lits'], ns['CYR']

if not files:
    files = []
    for dp, _, fs in os.walk(os.path.join(root, 'UnityProject/Assets/Scripts')):
        files += [os.path.join(dp, f) for f in fs if f.endswith('.cs') and '/Editor/' not in dp]
cat_path = os.path.join(root, 'UnityProject/Assets/Resources/Loc/strings.json')
raw = open(cat_path, encoding='utf-8').read()
cat = json.loads(raw); have = {r['r'] for r in cat['s']}
KZ = re.compile('[ӘәҒғҚқҢңӨөҰұҮүҺһІі]')  # already Kazakh (fallback dictionaries)
new = []
for f in files:
    for s, _ in lits(open(f, encoding='utf-8').read()):
        if CYR.search(s) and not KZ.search(s) and s not in have and s not in new and s.strip(): new.append(s)
print(len(new), 'new literals')
if dry:
    for s in new: print(repr(s))
    sys.exit()
ph = lambda x: sorted(set(re.findall(r'\{\d+\}', x)))
PROMPT = """You translate UI strings of a city digital twin platform (Alatau City, Kazakhstan; investors, construction, infrastructure) from Russian to English and Kazakh.
Rules: keep every placeholder like {0} {1} exactly; keep leading/trailing spaces and punctuation, separators (·, —, :) and line breaks; keep numbers, units in the target language style (м → m, тыс. → k only when it follows a number); proper names (Alatau City, Gate, Golden, Growing, Green, Iconic, KAIST, QTwin, olx.kz, Trend) stay as is; НБ РК = National Bank of Kazakhstan (EN) / ҚР Ұлттық банкі (KZ). Short, natural UI wording. Kazakh in Cyrillic.
Return JSON: [{"ru": original exactly, "en": ..., "kz": ...}] in the same order.
Strings:
"""
out = []
for i in range(0, len(new), 60):
    batch = new[i:i + 60]
    res = ask('gemini-4-argon', PROMPT + json.dumps(batch, ensure_ascii=False, indent=0), json_out=True, thinking='low')
    rows = json.loads(res) if isinstance(res, str) else res
    by = {r['ru']: r for r in rows if isinstance(r, dict) and 'ru' in r}
    for s in batch:
        r = by.get(s)
        if not r: print('MISSING', repr(s)); continue
        if ph(s) != ph(r.get('en', '')) or ph(s) != ph(r.get('kz', '')): print('PLACEHOLDER MISMATCH', repr(s)); continue
        out.append({'r': s, 'e': r['en'], 'k': r['kz']})
cat['s'].extend(out)
open(cat_path, 'w', encoding='utf-8', newline='').write(json.dumps(cat, ensure_ascii=False, separators=(',', ':')) + ('\n' if raw.endswith('\n') else ''))
print('added', len(out))
