"""Join map_inputs.zip.000 … .003 into map_inputs.zip, check sha256, unzip next to this file (folder stage7/).
usage: python tools/map/inputs/join.py"""
import glob, hashlib, os, zipfile
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, 'map_inputs.zip')
with open(out, 'wb') as w:
    for p in sorted(glob.glob(os.path.join(here, 'map_inputs.zip.[0-9][0-9][0-9]'))):
        w.write(open(p, 'rb').read())
want = open(os.path.join(here, 'map_inputs.sha256')).read().strip()
got = hashlib.sha256(open(out, 'rb').read()).hexdigest()
print('sha256', 'ok' if got == want else f'MISMATCH {got} != {want}')
zipfile.ZipFile(out).extractall(here)
print('unzipped to', os.path.join(here, 'stage7'))
