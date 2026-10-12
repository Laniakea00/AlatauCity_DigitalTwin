"""Renders the Unity WebGL template (UnityProject/Assets/WebGLTemplates/Alatau/index.html) into pages/index.html with the
file names of our build, so the loading page can be updated on GitHub Pages without a new Unity build.
Run from the repo root: python tools/render_web_template.py"""
import json, re, pathlib, sys
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
src = (root / "UnityProject/Assets/WebGLTemplates/Alatau/index.html").read_text(encoding="utf-8")
v = {"PRODUCT_NAME": "Alatau City · Digital Twin", "COMPANY_NAME": "qTwin", "PRODUCT_VERSION": "1.0",
     "LOADER_FILENAME": "WebGL.loader.js", "DATA_FILENAME": "WebGL.data.unityweb",
     "FRAMEWORK_FILENAME": "WebGL.framework.js.unityweb", "CODE_FILENAME": "WebGL.wasm.unityweb"}
flags = {"USE_WASM": True, "USE_THREADS": False, "MEMORY_FILENAME": False, "SYMBOLS_FILENAME": False}
out, keep = [], [True]
for line in src.splitlines():
    s = line.strip()
    if s.startswith("#if "): keep.append(keep[-1] and flags[s[4:].strip()]); continue
    if s == "#endif": keep.pop(); continue
    if keep[-1]: out.append(line)
html = "\n".join(out) + "\n"
html = re.sub(r"\{\{\{\s*JSON\.stringify\((\w+)\)\s*\}\}\}", lambda m: json.dumps(v[m.group(1)], ensure_ascii=False), html)
html = re.sub(r"\{\{\{\s*(\w+)\s*\}\}\}", lambda m: v[m.group(1)], html)
assert "{{{" not in html and "#if" not in html
(root / "pages").mkdir(exist_ok=True); (root / "pages/index.html").write_text(html, encoding="utf-8")
print("pages/index.html", len(html), "bytes")
