"""Bundle core.js + worker.js into one file for Cloudflare (cloudflare/worker.js): python3 build_worker.py"""
import re, os
here = os.path.dirname(os.path.abspath(__file__))
core = open(os.path.join(here, 'core.js'), encoding='utf-8').read()
w = open(os.path.join(here, 'worker.js'), encoding='utf-8').read()
core = re.sub(r'^export (const|function|class|async function)', r'\1', core, flags=re.M)
w = '\n'.join(l for l in w.split('\n') if not l.startswith('import '))
out = '// Alatau City Digital Twin — AI proxy (Cloudflare Worker, single file built from core.js + worker.js by build_worker.py)\n' + core + '\n' + w
open(os.path.join(here, 'cloudflare', 'worker.js'), 'w', encoding='utf-8').write(out)
