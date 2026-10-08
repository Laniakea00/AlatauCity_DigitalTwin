"""Labels, object passports, picking and the bridge site, in a real browser.  python test_objects.py <page.html> <out_dir>

Takes pictures (c1 ... c9) and prints what the passports and the site dashboard say. Exits with 1 on a console or page error.
"""
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

page_path, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
errors, res = [], {}
with sync_playwright() as p:
    b = p.chromium.launch(channel='msedge', headless=True, args=['--ignore-gpu-blocklist', '--use-angle=d3d11', '--enable-gpu'])
    pg = b.new_page(viewport=dict(width=1600, height=900))
    pg.on('console', lambda m: errors.append(m.type + ': ' + m.text[:500]) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)[:500]))
    pg.goto(pathlib.Path(page_path).resolve().as_uri())
    pg.wait_for_function('window.__alatau && window.__alatau.S.ready', timeout=240000)

    def shot(name, wait=2600):
        pg.wait_for_timeout(wait)
        pg.screenshot(path=os.path.join(out, name + '.png'))

    def texts(sel, n=6):
        return pg.evaluate("([s, n]) => [...document.querySelectorAll(s)].map(e => e.textContent).slice(0, n)", [sel, n])

    # 1. labels over the city
    res['labels_total'] = pg.evaluate("() => window.__alatau.objects().labels.length")
    pg.evaluate("() => { const a = window.__alatau; a.AN.setOn(false); a.setYear(2040); a.goTo(a.VIEWS.find(v => v.name === 'Golden'), true); }")
    shot('c1_labels_golden_2040', 1200)
    res['labels_shown_golden'] = pg.evaluate("() => window.__alatau.objects().labels.filter(l => l.shown).map(l => l.t.textContent).slice(0, 14)")
    pg.evaluate("() => { const a = window.__alatau; a.goTo(a.VIEWS.find(v => v.name === 'overview'), true); }")
    shot('c2_labels_city', 1200)
    # 2. a facility label: click it, the camera flies there, the passport opens
    pg.evaluate("() => { const a = window.__alatau; a.setYear(2034); a.goTo(a.VIEWS.find(v => v.name === 'Golden'), true); }")
    pg.wait_for_timeout(600)
    res['facility_clicked'] = pg.evaluate("""() => { const a = window.__alatau, l = a.objects().labels.find(l => l.t.textContent.includes('220/110') && l.t.textContent.includes('Golden')); if (!l) return null; l.el.click(); return l.t.textContent + ' | ' + l.el.className; }""")
    shot('c3_passport_substation_2034')
    res['facility_passport'] = texts('#pass .ptitle, #pass .pstatus, #pass .kpi .v, #pass .fact', 14)
    # 3. a building: a real mouse click in the view
    pg.evaluate("() => { const a = window.__alatau; a.objects().closePass(); a.setYear(2050); a.goTo(a.VIEWS.find(v => v.name === 'Tallest ↓'), true); for (let k = 0; k < 3; k++) a.frame(true); }")
    pg.wait_for_timeout(800)
    hit = None
    for dx, dy in ((0, 0), (40, 30), (-60, 40), (80, -20), (-100, -40), (0, 90), (140, 60)):
        pg.mouse.click(800 + dx, 470 + dy)
        pg.wait_for_timeout(250)
        hit = pg.evaluate("() => { const s = window.__alatau.objects().sel(); return s ? [s.type, s.id] : null; }")
        if hit:
            break
    res['building_picked'] = hit
    res['pick_ms'] = pg.evaluate("() => { const a = window.__alatau, t = performance.now(); a.objects().pick(800, 470); return Math.round(performance.now() - t); }")
    shot('c4_passport_building', 600)
    res['building_passport'] = texts('#pass .ptitle, #pass .pstatus, #pass .kpi .v, #pass .fact', 16)
    # 4. the landmark label of Gate and an LRT station
    res['landmark'] = pg.evaluate("""() => { const a = window.__alatau, l = a.objects().labels.find(l => l.t.textContent.includes('Gate ·') || (l.text && l.text().includes('Gate') && l.color === '#d946ef')); if (!l) return null; l.click(); return l.text(); }""")
    shot('c5_passport_landmark_gate')
    res['landmark_note'] = texts('#pass .note', 2)
    res['lrt'] = pg.evaluate("""() => { const a = window.__alatau, l = a.objects().labels.find(l => l.color === '#e0261b' && l.prio === 30); l.click(); return [...document.querySelectorAll('#pass .ptitle, #pass .pstatus, #pass .fact')].map(e => e.textContent).slice(0, 5); }""")
    pg.evaluate("() => window.__alatau.objects().closePass()")
    # 5. the marker of the bridge on the city map in the year of the problem, then the site
    pg.evaluate("() => { const a = window.__alatau; a.AN.setOn(true); a.AN.setTab('overview'); a.setYear(2032); a.goTo(a.VIEWS.find(v => v.name === 'Golden'), true); }")
    shot('c6_marker_2032', 1200)
    res['marker'] = pg.evaluate("""() => { const a = window.__alatau, l = a.objects().labels.find(l => l.prio === 300); const r = [l.shown, l.t.textContent]; l.el.click(); return r; }""")
    shot('c7_site', 3200)
    res['site_state'] = pg.evaluate("() => { const a = window.__alatau, s = a.site(); return { tab: a.AN.ui.tab, year: a.S.year, visible: s.group.visible, river_m: s.riverW, length: Math.round(s.L), width: Math.round(s.Wd), dist: Math.round(a.S.dist) }; }")
    res['site_left'] = texts('#anL .ptitle, #anL .summary, #anL .kpi .v, #anL .fact', 16)
    res['site_right'] = texts('#anR .ptitle, #anR .jbadge, #anR .ptext', 6)
    res['site_labels'] = pg.evaluate("() => window.__alatau.objects().labels.filter(l => l.shown).map(l => l.t.textContent)")
    pg.evaluate("() => { const a = window.__alatau; a.goTo({ target: [a.site().C[0], 0, a.site().C[1]], dist: 150, yaw: 70, pitch: 30 }, true); }")
    shot('c8_site_close', 1500)
    res['annotation'] = pg.evaluate("""() => { const a = window.__alatau, l = a.objects().labels.find(l => l.t.textContent.includes('DN1400')); l.el.click(); return [...document.querySelectorAll('#anR .blk:first-child .ptitle, #anR .blk:first-child .ptext')].map(e => e.textContent); }""")
    shot('c9_site_annotation')
    pg.evaluate("() => { const a = window.__alatau; document.querySelector('#anR').scrollTop = 0; a.site().st.ann = null; a.AN.refresh(true); }")
    pg.evaluate("""() => { const b = [...document.querySelectorAll('#anR .acts button')][0]; b.click(); }""")
    pg.evaluate("() => { const a = window.__alatau; a.goTo({ target: [a.site().C[0], 0, a.site().C[1]], dist: 120, yaw: 110, pitch: 36 }, true); document.querySelector('#anR').scrollTop = 600; }")
    shot('c10_site_decided', 1500)
    res['decided'] = pg.evaluate("() => { const s = window.__alatau.site(); return [s.st.decided, document.querySelector('#anL .summary').textContent]; }")
    pg.evaluate("() => { document.querySelector('#anR').scrollTop = 1500; }")
    shot('c11_site_options_chat', 400)
    # 6. English, another scenario
    pg.evaluate("() => { document.querySelector('#lang').click(); const a = window.__alatau; a.AN.setScenario(2); }")
    pg.wait_for_timeout(500)
    res['slow_en'] = pg.evaluate("() => { const a = window.__alatau; return [a.S.year, a.site().group.visible, document.querySelector('#anL .summary').textContent, document.querySelector('#anL .eyebrow').textContent]; }")
    pg.evaluate("() => { const a = window.__alatau; document.querySelector('#anR').scrollTop = 0; a.goTo({ target: [a.site().C[0], 0, a.site().C[1]], dist: 430, yaw: 52, pitch: 34 }, true); }")
    shot('c12_site_en_slow', 1500)
    fps = pg.evaluate("() => new Promise(r => { let n = 0; const t = performance.now(); (function f() { n++; if (performance.now() - t < 2000) requestAnimationFrame(f); else r(n / 2); })(); })")
    res['fps_headless'] = round(fps)
    b.close()
print(json.dumps(res, ensure_ascii=False, indent=1))
print('errors:', json.dumps(errors[:10], ensure_ascii=False, indent=1))
sys.exit(1 if errors else 0)
