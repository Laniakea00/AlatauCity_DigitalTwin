# Merge translated batches into Assets/Resources/Loc/strings.json.
# usage: python Tools/loc/merge.py <dir with out_*.json> Assets/Resources/Loc/strings.json
# each batch: [{"ru": "...", "en": "...", "kz": "..."}]; {0}, {1} holes must match in all three
import json, glob, re, sys, os
src, dst = sys.argv[1], sys.argv[2]
rows = {}; bad = []
ph = lambda x: sorted(set(re.findall(r'\{\d+\}', x)))
for f in sorted(glob.glob(os.path.join(src, 'out_*.json'))):
    for e in json.load(open(f, encoding='utf-8')):
        r, en, kz = e['ru'], e.get('en') or '', e.get('kz') or ''
        if ph(r) != ph(en) or ph(r) != ph(kz): bad.append((f, r, en, kz))
        rows[r] = (en, kz)
print(len(rows), 'rows, bad', len(bad))
for b in bad[:20]: print(b)
json.dump({'s': [{'r': r, 'e': e, 'k': k} for r, (e, k) in rows.items()]}, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
