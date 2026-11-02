"""Image generator and editor on Gemini (Nano Banana Pro = gemini-3-pro-image).
usage: python gemini_image.py "<prompt>" out.png [--ref a.png b.jpg ...] [--model gemini-3-pro-image] [--aspect 16:9]
With --ref the model edits or follows the reference images (textures, facades, sky, a frame to restyle).
The key comes from GEMINI_API_KEY (see gemini.py). Generated pictures are synthetic: label them «модель qTwin» in the product."""
import argparse, base64, json, mimetypes, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini import _key

ap = argparse.ArgumentParser()
ap.add_argument('prompt'); ap.add_argument('out')
ap.add_argument('--ref', nargs='*', default=[])
ap.add_argument('--model', default='gemini-3-pro-image')
ap.add_argument('--aspect', default=None, help='e.g. 1:1, 16:9, 9:16, 4:3')
a = ap.parse_args()

parts = [{'text': a.prompt}]
for p in a.ref:
    mt = mimetypes.guess_type(p)[0] or 'image/png'
    parts.append({'inline_data': {'mime_type': mt, 'data': base64.b64encode(open(p, 'rb').read()).decode()}})
cfg = {'responseModalities': ['TEXT', 'IMAGE']}
if a.aspect: cfg['imageConfig'] = {'aspectRatio': a.aspect}
body = json.dumps({'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': cfg}).encode()
url = f'https://generativelanguage.googleapis.com/v1beta/models/{a.model}:generateContent'
for attempt in range(4):
    try:
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', 'x-goog-api-key': _key()})
        with urllib.request.urlopen(req, timeout=600) as r: d = json.load(r)
        break
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:500]
        if e.code in (429, 500, 503) and attempt < 3: time.sleep(5 * (attempt + 1)); continue
        sys.exit(f'Gemini HTTP {e.code}: {msg}')
n = 0
base, ext = os.path.splitext(a.out)
for p in d['candidates'][0]['content']['parts']:
    blob = p.get('inline_data') or p.get('inlineData')
    if blob:
        path = a.out if n == 0 else f'{base}_{n}{ext}'
        open(path, 'wb').write(base64.b64decode(blob['data'])); print('saved', path); n += 1
    elif p.get('text') and not p.get('thought'):
        print(p['text'][:500])
if not n: sys.exit('no image in the answer')
