"""Open the page in a real browser (Edge, on the GPU), wait until the city is built, take pictures of several views, report errors.

    python test_page.py <page.html> <out_dir> [swiftshader]

Needs playwright (PYTHONPATH=...\\_pylibs). Exits with 1 on a console error, a page error or a blank picture.
"""
import json
import os
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

page_path, out = sys.argv[1], sys.argv[2]
soft = len(sys.argv) > 3 and sys.argv[3] == 'swiftshader'
os.makedirs(out, exist_ok=True)
args = ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'] if soft else ['--ignore-gpu-blocklist', '--use-angle=d3d11', '--enable-gpu']
errors, logs = [], []
with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge', headless=True, args=args)
    pg = b.new_page(viewport=dict(width=1600, height=900))
    pg.on('console', lambda m: (errors if m.type == 'error' else logs).append(m.type + ': ' + m.text[:600]))
    pg.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)[:600]))
    t0 = time.time()
    pg.goto(pathlib.Path(page_path).resolve().as_uri())
    try:
        pg.wait_for_function('window.__alatau && window.__alatau.S.ready', timeout=240000)
    except Exception as e:      # noqa: BLE001
        errors.append('not ready: ' + str(e)[:200] + ' | status: ' + pg.inner_text('#load'))
    ready = time.time() - t0
    info = {}
    if not errors:
        info = pg.evaluate("""() => { const a = window.__alatau, gl = a.renderer.getContext(), d = gl.getExtension('WEBGL_debug_renderer_info');
            return { views: a.VIEWS.map(v => v.name), tris: a.nTris(), houses: a.houses(), gpu: d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : '?', programs: a.renderer.info.programs.length }; }""")
        # ---- the analytics panels: numbers against the data generator, then every tab with a picture
        info['analytics_vs_generator_worst_relative_gap'] = pg.evaluate('() => window.__alatau.AN.check()')
        steps = [('a1_overview_2032', "a.AN.setScenario(0); a.AN.ui.district = -1; a.AN.setTab('overview'); a.setYear(2032);", 'Gate'),
                 ('a2_district_golden_2040', "a.AN.ui.district = 1; a.AN.setTab('overview'); a.setYear(2040);", 'Golden'),
                 ('a3_construction_2033', "a.AN.ui.district = -1; a.AN.ui.shut.money = false; a.AN.ui.shut.contractors = false; a.AN.setTab('construction'); a.setYear(2033);", 'Growing'),
                 ('a4_forecast_power_2036', "a.AN.ui.metric = 0; a.AN.setTab('prediction'); a.setYear(2036);", 'Golden'),
                 ('a5_forecast_schools_2040', "a.AN.ui.metric = 5; a.AN.setTab('prediction'); a.setYear(2040);", 'Growing'),
                 ('a6_forecast_quake_2050', "a.AN.ui.metric = 9; a.AN.setTab('prediction'); a.setYear(2050);", 'Gate'),
                 ('a7_forecast_flood_2050', "a.AN.ui.metric = 10; a.AN.ui.floodExt = true; a.AN.setTab('prediction'); a.setYear(2050);", 'Green'),
                 ('a8_forecast_transport_2040', "a.AN.ui.metric = 8; a.AN.setTab('prediction'); a.setYear(2040);", 'Golden'),
                 ('a9_scenario_slow_2050_en', "document.querySelector('#lang').click(); a.AN.setScenario(2); a.AN.setTab('overview'); a.setYear(2050);", 'Growing')]
        info['analytics'] = []
        for name, code, view in steps:
            txt = pg.evaluate("""([code, view]) => { const a = window.__alatau; (new Function('a', code))(a); const v = a.VIEWS.find(v => v.name === view); a.goTo(v, true); a.S.yearF = a.S.year; a.setHour(17);
                for (let k = 0; k < 4; k++) a.frame(true); return [...document.querySelectorAll('#an .summary, #an .insight')].map(e => e.textContent).slice(0, 4); }""", [code, view])
            pg.wait_for_timeout(300)
            pg.screenshot(path=os.path.join(out, name + '.png'))
            info['analytics'].append({name: txt})
        pg.evaluate("() => { const a = window.__alatau; document.querySelector('#lang').click(); a.AN.setScenario(0); a.AN.ui.floodExt = false; a.AN.ui.metric = 0; a.AN.setTab('overview'); a.AN.setOn(false); }")
        shots = [('Gate ↓', 2050, 17), ('Growing ↓', 2050, 17), ('Tallest ↓', 2050, 17), ('Golden', 2040, 17), ('overview', 2050, 12), ('Growing ↓', 2050, 18.75)]
        for i, (name, year, hour) in enumerate(shots):
            dt = pg.evaluate("""([name, year, hour]) => { const a = window.__alatau, v = a.VIEWS.find(v => v.name === name) || a.VIEWS[0]; a.goTo(v, true); a.setYear(year); a.S.yearF = year; a.setHour(hour);
                const t = performance.now(); for (let k = 0; k < 4; k++) a.frame(true); return [performance.now() - t, a.trees(), a.renderer.info.render.triangles, a.renderer.info.render.calls]; }""", [name, year, hour])
            pg.wait_for_timeout(400)
            f = os.path.join(out, f'{i + 1}_{name.replace(" ↓", "_low")}_{year}_{str(hour).replace(".", "")}.png')
            pg.screenshot(path=f)
            info.setdefault('shots', []).append(dict(file=os.path.basename(f), build_ms=round(dt[0]), trees=dt[1], triangles=dt[2], calls=dt[3]))
        # a blank or single-colour canvas is a failure
        # (drawn and read in the same task: the WebGL picture is not kept after it has been shown)
        flat = pg.evaluate("""() => { const c = document.createElement('canvas'); c.width = 64; c.height = 36; const g = c.getContext('2d'); window.__alatau.frame(true); g.drawImage(document.querySelector('#c'), 0, 0, 64, 36);
            const d = g.getImageData(0, 0, 64, 36).data; let lo = 255, hi = 0; for (let i = 0; i < d.length; i += 4) { lo = Math.min(lo, d[i]); hi = Math.max(hi, d[i]); } return hi - lo; }""")
        info['canvas_contrast'] = flat
        fps = pg.evaluate("""() => new Promise(r => { let n = 0; const t = performance.now(); (function f() { n++; if (performance.now() - t < 2000) requestAnimationFrame(f); else r(n / 2); })(); })""")
        info['frames_per_second_headless'] = round(fps)
    b.close()
print(json.dumps(dict(ready_s=round(ready, 1), info=info, errors=errors[:12], warnings=[x for x in logs if x.startswith('warning')][:6]), ensure_ascii=False, indent=1))
sys.exit(1 if errors or not info or info.get('canvas_contrast', 0) < 20 else 0)
