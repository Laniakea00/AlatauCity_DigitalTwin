# Extract Cyrillic C# string literals as templates: interpolation holes -> {0},{1}...
import re, os, json, sys
ROOT = sys.argv[1]; CYR = re.compile('[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]')
def lits(src):
    i = 0; n = len(src); out = []
    while i < n:
        c = src[i]
        if src.startswith('//', i): j = src.find('\n', i); i = n if j < 0 else j; continue
        if src.startswith('/*', i): j = src.find('*/', i); i = n if j < 0 else j + 2; continue
        if c == "'":  # char literal
            j = i + 1
            while j < n and src[j] != "'": j += 2 if src[j] == '\\' else 1
            i = j + 1; continue
        interp = verb = False; k = i
        if src.startswith('$@', i) or src.startswith('@$', i): interp = verb = True; k = i + 2
        elif c == '$' and i + 1 < n and src[i + 1] == '"': interp = True; k = i + 1
        elif c == '@' and i + 1 < n and src[i + 1] == '"': verb = True; k = i + 1
        if src[k] != '"' : i += 1; continue
        j = k + 1; buf = []; holes = 0; depth = 0
        while j < n:
            ch = src[j]
            if interp and ch == '{':
                if src[j + 1] == '{': buf.append('{'); j += 2; continue
                # skip the hole (balanced, strings inside)
                d = 1; j += 1
                while j < n and d:
                    if src[j] == '"':
                        j += 1
                        while j < n and src[j] != '"': j += 2 if src[j] == '\\' else 1
                    elif src[j] == '{': d += 1
                    elif src[j] == '}': d -= 1
                    j += 1
                buf.append('{%d}' % holes); holes += 1; continue
            if interp and ch == '}' and src[j + 1:j + 2] == '}': buf.append('}'); j += 2; continue
            if verb:
                if ch == '"':
                    if src[j + 1:j + 2] == '"': buf.append('"'); j += 2; continue
                    break
                buf.append(ch); j += 1; continue
            if ch == '\\':
                e = src[j + 1]; buf.append({'n': '\n', 't': '\t', '"': '"', '\\': '\\', '0': '\0'}.get(e, '\\' + e)); j += 2
                if e == 'u': buf[-1] = chr(int(src[j:j + 4], 16)); j += 4
                continue
            if ch == '"': break
            buf.append(ch); j += 1
        s = ''.join(buf); out.append((s, interp)); i = j + 1
    return out
res = {}
for dp, _, fs in os.walk(ROOT):
    for f in fs:
        if not f.endswith('.cs'): continue
        p = os.path.join(dp, f); src = open(p, encoding='utf-8').read()
        for s, interp in lits(src):
            if not CYR.search(s): continue
            if f == 'Loc.cs': continue
            # string.Format templates already use {0}: keep
            res.setdefault(s, set()).add(f)
cat = [{'ru': k, 'files': sorted(v)} for k, v in sorted(res.items())]
json.dump(cat, open(sys.argv[2], 'w'), ensure_ascii=False, indent=0)
print(len(cat), sum(len(c['ru']) for c in cat))
