"""The full package for another computer: the Windows build, the page for the browser, the Unity project, the documents.

    python make_full_zip.py <out.zip>

Laid out like the project's own export (Alatau City > Export ZIP for team): one folder AlatauCity_DigitalTwin with context.md, startup.md,
docs, UnityProject (Assets, Packages, ProjectSettings, Tools; no Library) and Build_Windows; plus web (the page and its source)
and README_RU.md. Paths are taken from where this file lies, so it works wherever the folder is.
"""
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../AlatauCity_DigitalTwin
TOP = 'AlatauCity_DigitalTwin/'
SKIP_DIRS = {'Library', 'Temp', 'Logs', 'UserSettings', 'obj', '.vs', '.idea', '__pycache__', '.venv', 'Builds'}
PACKED = ('.png', '.jpg', '.jpeg', '.mp4', '.zip', '.7z', '.ttf', '.otf')       # already compressed: stored quickly
out = sys.argv[1]
items = []                                                                  # (file on disk, name in the archive)


def collect(folder, prefix, keep=None):
    for base, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith('_BurstDebugInformation_DoNotShip'))
        rel = os.path.relpath(base, folder).replace('\\', '/')
        for f in sorted(files):
            if keep is None or keep(f):
                items.append((os.path.join(base, f), prefix + ('' if rel == '.' else rel + '/') + f))


for f in ('README_RU.md', 'context.md', 'startup.md'):
    items.append((os.path.join(ROOT, f), TOP + f))
collect(os.path.join(ROOT, 'docs'), TOP + 'docs/')
for d in ('Assets', 'Packages', 'ProjectSettings', 'Tools'):
    collect(os.path.join(ROOT, 'UnityProject', d), TOP + 'UnityProject/' + d + '/')
collect(os.path.join(ROOT, 'UnityProject', 'Builds', 'Windows'), TOP + 'Build_Windows/')
WEB = ('AlatauCity_Film_3D.html', 'page.html', 'app.js', 'glsl_film.js', 'glsl_parts.js', 'analytics.js', 'analytics_text.js', 'objects.js', 'objects_text.js', 'site.js',
       'build_web.py', 'build.sh', 'test_page.py', 'test_objects.py', 'make_zip.py', 'make_full_zip.py')
for f in WEB:
    items.append((os.path.join(ROOT, 'web', f), TOP + 'web/' + f))
items.append((os.path.join(ROOT, 'web', 'lib', 'three.min.js'), TOP + 'web/lib/three.min.js'))

missing = [s for s, _ in items if not os.path.isfile(s)]
assert not missing, 'missing: ' + ', '.join(missing[:5])
total = sum(os.path.getsize(s) for s, _ in items)
print(f'{len(items)} files, {total / 1e6:.0f} MB to pack', flush=True)
t0, done, step = time.time(), 0, 0
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
    for src, name in items:
        z.write(src, name, compress_type=zipfile.ZIP_DEFLATED, compresslevel=1 if src.lower().endswith(PACKED) else 5)
        done += os.path.getsize(src)
        if done * 10 // total > step:
            step = done * 10 // total
            print(f'  {step * 10} %  {time.time() - t0:.0f} s', flush=True)
size = os.path.getsize(out)
by = {}
for s, n in items:
    k = n[len(TOP):].split('/')[0] if '/' in n[len(TOP):] else '(documents)'
    by[k] = by.get(k, 0) + os.path.getsize(s)
print(f'{out}: {size / 1e6:.0f} MB from {total / 1e6:.0f} MB, {len(items)} files, {time.time() - t0:.0f} s')
print('unpacked size by part, MB:', {k: round(v / 1e6) for k, v in by.items()})
with zipfile.ZipFile(out) as z:
    bad = z.testzip()
    print('archive check:', 'ok' if bad is None else 'broken: ' + bad)
