"""Copy translations for literals that differ from an existing strings.json entry only by non-breaking spaces (U+00A0 / U+2011).
usage: python3 loc_nbsp.py <repo root>  — appends rows, then sorts the catalogue by 'r'."""
import json, os, re, sys
root = sys.argv[1]
src = open(os.path.join(root, 'UnityProject/Tools/loc/extract.py'), encoding='utf-8').read()
ns = {}; exec(src.split('res = {}')[0].replace('ROOT = sys.argv[1]; ', ''), ns)
lits, CYR = ns['lits'], ns['CYR']
cat_path = os.path.join(root, 'UnityProject/Assets/Resources/Loc/strings.json')
raw = open(cat_path, encoding='utf-8').read(); cat = json.loads(raw)
have = {r['r']: r for r in cat['s']}
norm = lambda s: s.replace('\u00a0', ' ').replace('\u2011', '-')
by_norm = {}
for r in cat['s']: by_norm.setdefault(norm(r['r']), r)
def carry(ru, tr):
    # put the same no-break characters into the translation: a space before a unit/%/currency, a hyphen in ordinals
    out = tr
    for m in re.finditer(r'\u00a0(\S+)', ru):
        tok = m.group(1).rstrip('.,;:)')
        if tok in ('%', '₸', '$'): out = out.replace(' ' + tok, '\u00a0' + tok)
    out = re.sub(r'(\d) (%|₸)', '\\1\u00a0\\2', out)
    return out
added = 0
for dp, _, fs in os.walk(os.path.join(root, 'UnityProject/Assets/Scripts')):
    if '/Editor' in dp: continue
    for f in fs:
        if not f.endswith('.cs'): continue
        for s, _ in lits(open(os.path.join(dp, f), encoding='utf-8').read()):
            if s in have or ('\u00a0' not in s and '\u2011' not in s) or not CYR.search(s): continue
            b = by_norm.get(norm(s))
            if not b: continue
            row = {'r': s, 'e': carry(s, b['e']), 'k': carry(s, b['k'])}
            have[s] = row; added += 1
rows = sorted(have.values(), key=lambda r: r['r'])
open(cat_path, 'w', encoding='utf-8', newline='').write(json.dumps({'s': rows}, ensure_ascii=False, separators=(',', ':')) + ('\n' if raw.endswith('\n') else ''))
print('added', added, 'total', len(rows))
