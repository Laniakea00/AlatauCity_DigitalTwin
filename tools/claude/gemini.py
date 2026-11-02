"""Small Gemini client. The API key is read from the GEMINI_API_KEY environment variable
(or from the file named by GEMINI_KEY_FILE, default ~/.gemini_key) and never printed. Never put the key in the repo.
usage as module: from gemini import ask; ask(model, prompt_text, images=[paths], json_out=True, thinking='high')"""
import json, base64, mimetypes, os, sys, time, urllib.request
KEY_FILE = os.environ.get('GEMINI_KEY_FILE', os.path.join(os.path.expanduser('~'), '.gemini_key'))
def _key():
    k = os.environ.get('GEMINI_API_KEY', '').strip()
    if k: return k
    if os.path.exists(KEY_FILE): return open(KEY_FILE, encoding='utf-8').read().strip()
    raise RuntimeError('no Gemini key: set GEMINI_API_KEY or put the key in ' + KEY_FILE)
def ask(model, text, images=(), json_out=False, thinking='high', temperature=None, schema=None, timeout=600):
    parts = [{'text': text}]
    for p in images:
        mt = mimetypes.guess_type(p)[0] or 'image/png'
        parts.append({'inline_data': {'mime_type': mt, 'data': base64.b64encode(open(p, 'rb').read()).decode()}})
    cfg = {}
    if thinking: cfg['thinkingConfig'] = {'thinkingLevel': thinking}
    if json_out: cfg['responseMimeType'] = 'application/json'
    if schema: cfg['responseSchema'] = schema
    if temperature is not None: cfg['temperature'] = temperature
    body = json.dumps({'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': cfg}).encode()
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', 'x-goog-api-key': _key()})
            with urllib.request.urlopen(req, timeout=timeout) as r: d = json.load(r)
            out = ''.join(p.get('text', '') for p in d['candidates'][0]['content']['parts'] if not p.get('thought'))
            return out
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:500]
            if e.code in (429, 500, 503) and attempt < 3: time.sleep(5 * (attempt + 1)); continue
            raise RuntimeError(f'Gemini HTTP {e.code}: {msg}')
        except Exception as e:
            if attempt < 3: time.sleep(5 * (attempt + 1)); continue
            raise
