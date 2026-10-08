'use strict';
// Alatau City twin: the analytics panels of the Unity project, in the page. The same formulas as CityStats.cs, TwinScenario.cs,
// OverviewModule.cs, ConstructionLayer.cs / ConstructionModule.cs and PredictionModule.cs, on the same data files
// (buildings.csv and StreamingAssets/twin/*.json). Everything here is the twin's demo model on synthetic data, not official figures.
async function AlatauAnalytics(api) {
  const { DATA, gunzip, NB, bKind, bYear, bHeight, KIND, S, U, VIEWS, goTo, getLang } = api;
  const W = DATA.twin, $ = s => document.querySelector(s), MINY = 2025, MAXY = 2050, NY = 26, AFTER = 2099;
  const DIST = ['Gate', 'Golden', 'Growing', 'Green'], DCOL = ['#2e63b0', '#d9a621', '#f27336', '#339e5c'], DAREA = [3988, 15660, 36622, 31730], DTARGET = [223, 675, 650, 320];
  const CATCOL = ['#e3b341', '#ef6a6a', '#a371f7', '#8b98a8', '#2dd4bf'], M2JOB = [0, 90, 50, 100, 120], CAT = [0, 1, 2, 3, 4, 3];   // use -> category (energy counts as industry)
  const OK = '#34c759', WARN = '#f5a623', BAD = '#ff3b2f', WHITE = '#fcfcfc', GREY = '#878787';
  const OKc = [0.20, 0.78, 0.35], WARNc = [0.96, 0.65, 0.14], BADc = [1, 0.23, 0.18];

  // ---------------------------------------------------------------- per-building facts
  const t2 = await gunzip(DATA.tab2); let off = 0;
  const u8 = () => { const a = t2.subarray(off, off + NB); off += NB; return a; };
  const cut = (Ty, bytes) => { const a = new Ty(t2.buffer.slice(t2.byteOffset + off, t2.byteOffset + off + NB * bytes)); off += NB * bytes; return a; };
  const bDist = u8(), bUse = u8(), bSrc = u8(), bDur = u8(), bDelay = u8(), bCon = u8();
  const bGfa = cut(Float32Array, 4), bX = cut(Int16Array, 2), bZ = cut(Int16Array, 2), bFlood = [cut(Uint16Array, 2), cut(Uint16Array, 2)];
  const existing = b => bSrc[b] === 2, housing = b => bUse[b] === 0, kindOf = b => KIND[bKind[b]] || 'other';

  // ---------------------------------------------------------------- texts and numbers
  const tx = k => { const l = AN_TEXT[getLang()] || AN_TEXT.ru; return l[k] !== undefined ? l[k] : AN_TEXT.ru[k] !== undefined ? AN_TEXT.ru[k] : k; };
  const f = (s, ...a) => String(s).replace(/\{(\d)\}/g, (m, i) => a[+i] !== undefined ? a[+i] : m);
  const nfs = {}; const nf = d => { const k = getLang() + d; return nfs[k] || (nfs[k] = new Intl.NumberFormat(getLang() === 'ru' ? 'ru-RU' : 'en-US', { minimumFractionDigits: d, maximumFractionDigits: d })); };
  const N0 = v => nf(0).format(Math.abs(v) < 0.5 ? 0 : v), N1 = v => nf(1).format(Math.abs(v) < 0.05 ? 0 : v), K = v => N0(v / 1000), Mln = v => N1(v / 1e6), F1 = v => v >= 100 ? N0(v) : N1(v);
  /** Rounding of the Unity scripts (Mathf.RoundToInt): halves go to the even number. */
  const rint = v => { const fl = Math.floor(v), d = v - fl; return d > 0.5 ? fl + 1 : d < 0.5 ? fl : (fl % 2 === 0 ? fl : fl + 1); };
  const YI = y => Math.min(Math.max(y - MINY, 0), NY - 1), sum = a => a.reduce((x, y) => x + y, 0);
  const scenName = s => getLang() === 'ru' ? W.scen[s].name : tx('sc')[s];

  // ---------------------------------------------------------------- scenario: plan year -> year in the scenario (TwinScenario.EffectiveYear)
  const K13 = Math.fround(1.3);
  function effYear(b, s) {
    const y = 2000 + bYear[b]; if (y <= MINY || existing(b)) return y; const dy = y - MINY;
    if (s === 1) return MINY + Math.max(1, rint(dy * 0.75));
    if (s === 2) { const e = MINY + rint(Math.fround(dy * K13)); return e > MAXY ? AFTER : e; }
    if (s === 3) return housing(b) && y <= 2036 ? y + 2 : y;        // housing waits for the networks and the LRT
    return y;
  }
  // ---------------------------------------------------------------- aggregates (CityStats.Rebuild)
  const stats = [];
  function build(s) {
    if (stats[s]) return stats[s];
    const cum = [], cnt = [], nw = [], planned = [0, 0, 0, 0], eff = new Int16Array(NB); let total = 0;
    for (let d = 0; d < 4; d++) { cum.push([0, 1, 2, 3, 4].map(() => new Float64Array(NY))); cnt.push(new Int32Array(NY)); nw.push(new Int32Array(NY)); }
    for (let b = 0; b < NB; b++) {
      const e = effYear(b, s); eff[b] = e; const d = bDist[b]; if (d > 3) continue; const c = CAT[bUse[b]]; if (c === undefined) continue;   // existing stock is not "new" floor area
      total += bGfa[b]; planned[d] += bGfa[b]; if (e > MAXY) continue; const yi = Math.max(0, e - MINY);
      for (let y = yi; y < NY; y++) { cum[d][c][y] += bGfa[b]; cnt[d][y]++; } nw[d][yi]++;
    }
    return stats[s] = { cum, cnt, nw, planned, total, eff };
  }
  const each = (d, fn) => { let v = 0; for (let k = 0; k < 4; k++) if (d < 0 || k === d) v += fn(k); return v; };
  const gfa = (st, d, c, y) => each(d, k => st.cum[k][c][YI(y)]);
  const gfaAll = (st, d, y) => { let v = 0; for (let c = 0; c < 5; c++) v += gfa(st, d, c, y); return v; };
  const residents = (st, d, y) => gfa(st, d, 0, y) / 30;
  const jobs = (st, d, y) => { let v = 0; for (let c = 1; c < 5; c++) v += gfa(st, d, c, y) / M2JOB[c]; return v; };
  const readiness = (st, d, y) => d < 0 ? (st.total > 0 ? gfaAll(st, -1, y) / st.total : 0) : (gfaAll(st, d, MAXY) > 0 ? gfaAll(st, d, y) / st.planned[d] : 0);
  const count = (st, d, y) => each(d, k => st.cnt[k][YI(y)]), newThisYear = (st, d, y) => each(d, k => st.nw[k][YI(y)]);
  const bal = (s, res, d) => W.bal[res] ? W.bal[res][s][d + 1] : null;                          // d = -1: the city
  const load = (s, key, d, y) => W.loads[key] ? each(d, k => W.loads[key][s][k][YI(y)]) : 0;
  const duration = b => Math.max(1, bDur[b]);

  // ---------------------------------------------------------------- construction of the year (ConstructionLayer.Compute)
  function construction(y, s) {
    const st = build(s), nc = W.contractors.length, byC = new Int32Array(nc), behC = new Int32Array(nc), worst = []; let sites = 0, behind = 0, inWork = 0;
    for (let b = 0; b < NB; b++) {
      if (existing(b) || 2000 + bYear[b] <= MINY) continue;
      const plan = st.eff[b]; if (plan > MAXY) continue; const start = plan - duration(b), delayM = bDelay[b], fact = plan + Math.ceil(delayM / 12), dur = plan - start;
      if (y < start || y >= fact) continue;
      const real = dur + delayM / 12, prog = Math.min(Math.max((y + 1 - start) / real, 0.06), 0.97), late = delayM > 0 && (y >= plan || (y + 1 - start) / dur > prog + 0.12);
      sites++; inWork += bGfa[b]; if (late) behind++;
      const c = bCon[b]; if (c < nc) { byC[c]++; if (late) behC[c]++; }
      if (late) worst.push({ b, gfa: bGfa[b], delayM, prog, plan, fact });
    }
    worst.sort((p, q) => q.gfa * q.delayM - p.gfa * p.delayM);
    return { sites, behind, inWork, byC, behC, worst: worst.slice(0, 8) };
  }

  // ---------------------------------------------------------------- the forecast colouring of the buildings (TintLayer)
  const tint = new Uint8Array(256 * 256 * 4), tintTex = new THREE.DataTexture(tint, 256, 256, THREE.RGBAFormat, THREE.UnsignedByteType);
  tintTex.minFilter = tintTex.magFilter = THREE.NearestFilter; tintTex.generateMipmaps = false; tintTex.needsUpdate = true; U.tTint.value = tintTex;
  function applyTint(fn) {            // fn(b) -> [r, g, b, strength] or null
    tint.fill(0);
    if (fn) for (let b = 0; b < NB && b < 65536; b++) { const c = fn(b); if (!c) continue; tint[b * 4] = c[0] * 255; tint[b * 4 + 1] = c[1] * 255; tint[b * 4 + 2] = c[2] * 255; tint[b * 4 + 3] = c[3] * 255; }
    tintTex.needsUpdate = true;
  }
  const districtTint = dstat => b => { const d = bDist[b]; if (d > 3 || existing(b)) return null; const st = dstat[d]; return st === 'bad' ? [...BADc, 0.85] : st === 'warn' ? [...WARNc, 0.7] : [...OKc, 0.45]; };

  // ---------------------------------------------------------------- small page pieces
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined && text !== null) e.textContent = text; return e; };
  const ui = { on: innerWidth >= 1180, tab: 'overview', district: -1, metric: 0, why: false, floodExt: false, shut: { money: true, contractors: true, about: true } };
  const colL = $('#anL'), colR = $('#anR'); let charts = [], key = '';
  const extra = {}, listeners = [];           // tabs added by other parts of the page; functions called when year, scenario or language change
  function block(col, id, title, sub) {
    const b = el('div', 'blk' + (id && ui.shut[id] ? ' shut' : ''));
    if (title) { const h = el('div', 'bh'); h.append(el('span', 'bt', title)); if (sub) h.append(el('span', 'bs', sub)); b.append(h);
      if (id) h.onclick = () => { ui.shut[id] = !ui.shut[id]; b.classList.toggle('shut'); drawCharts(); }; else h.classList.add('fixed'); }
    col.append(b); return b;
  }
  function kpis(parent, list) { const g = el('div', 'kpis'); for (const [v, l, cls] of list) { const k = el('div', 'kpi' + (cls ? ' ' + cls : '')); k.append(el('div', 'l', l), el('div', 'v', v)); g.append(k); } parent.append(g); }
  function legend(parent, items) { const g = el('div', 'legend'); for (const [c, t] of items) { const s = el('span'), i = el('i'); i.style.background = c; s.append(i, document.createTextNode(t)); g.append(s); } parent.append(g); return g; }
  function fact(parent, a, b) { const r = el('div', 'fact'); r.append(el('span', '', a), el('span', '', b)); parent.append(r); return r; }
  function meter(parent, value) {
    const m = el('div', 'meter'), n = 30, mix = (a, b, t) => 'rgb(' + a.map((v, i) => Math.round((v + (b[i] - v) * t) * 255)).join(',') + ')';
    for (let i = 0; i < n; i++) { const q = i / (n - 1), c = q < 0.5 ? mix([0.93, 0.22, 0.20], [0.96, 0.72, 0.15], q * 2) : mix([0.96, 0.72, 0.15], [0.22, 0.76, 0.36], (q - 0.5) * 2), sg = el('i'); if ((i + 0.5) / n <= value) sg.style.background = c; m.append(sg); }
    const sc = el('div', 'meter-scale'); sc.append(el('span', '', '0%'), el('span', '', '50%'), el('span', '', '100%')); parent.append(m, sc);
  }
  function chips(parent, items, cur, pick) { const g = el('div', 'chips'); items.forEach(([id, text]) => { const b = el('button', 'chip' + (id === cur ? ' on' : ''), text); b.onclick = () => pick(id); g.append(b); }); parent.append(g); }
  function distRow(parent, d, value, cls, subText, subCls) {
    const r = el('div', 'drow click'), top = el('div', 'row'), dot = el('span', 'dot'); dot.style.background = DCOL[d];
    top.append(dot, el('span', 'n', DIST[d]), el('span', 's' + (cls ? ' ' + cls : ''), value)); r.append(top); if (subText) r.append(el('div', 'note sub' + (subCls ? ' ' + subCls : ''), subText));
    r.onclick = () => goDistrict(d); parent.append(r);
  }
  function jcard(parent, source, level, badge, text, time, action, onAction) {
    const c = el('div', 'jcard ' + level), h = el('div', 'jh'); h.append(el('span', 'src', source)); if (badge) h.append(el('span', 'jbadge ' + level, badge)); c.append(h, el('div', 'jt', text));
    const ft = el('div', 'jf'); ft.append(el('span', '', time)); if (action) { const a = el('a', '', action); a.onclick = onAction; ft.append(a); } c.append(ft); parent.append(c);
  }
  /** Chart on a canvas, drawn like the twin's TwinChart: years 2025-2050 along x; stacked areas, lines or stacked columns. */
  function chart(parent, o) { const cv = el('canvas', 'chart'); parent.append(cv); charts.push([cv, o]); return cv; }
  function drawChart(cv, o) {
    const w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return; const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    const PL = 36, PR = 8, PT = 6, PB = 18, pw = w - PL - PR, ph = h - PT - PB, ser = o.series, n = ser.length ? ser[0].length : 0;
    let m = 0; for (let i = 0; i < n; i++) { let v = 0; for (const s of ser) v = (o.stacked || o.bars) ? v + s[i] : Math.max(v, s[i]); m = Math.max(m, v); } if (!(m > 0)) m = 1;
    const p10 = Math.pow(10, Math.floor(Math.log10(m))), fr = m / p10, max = (fr <= 1 ? 1 : fr <= 2 ? 2 : fr <= 2.5 ? 2.5 : fr <= 5 ? 5 : 10) * p10;
    const X = i => PL + pw * i / (n - 1), Y = v => PT + ph * (1 - Math.min(Math.max(v / max, 0), 1));
    g.font = '10px "Segoe UI", system-ui, sans-serif'; g.fillStyle = GREY; g.strokeStyle = '#2a2a2a'; g.lineWidth = 1; g.textBaseline = 'middle'; g.textAlign = 'right';
    for (let i = 0; i < 3; i++) { const y = Math.round(PT + ph * i / 2) + 0.5, v = max * (2 - i) / 2; g.beginPath(); g.moveTo(PL, y); g.lineTo(PL + pw, y); g.stroke(); g.fillText(v >= 100 ? v.toFixed(0) : String(+v.toFixed(1)), PL - 5, y); }
    g.textAlign = 'center'; g.textBaseline = 'top'; for (const yr of [2025, 2030, 2040, 2050]) g.fillText(String(yr), Math.min(PL + pw * (yr - 2025) / 25, w - 14), h - PB + 4);
    if (n < 2) return; const acc = new Float64Array(n);
    if (o.bars) {
      const bw = Math.max(2, pw / n * 0.68);
      ser.forEach((s, k) => { for (let i = 0; i < n; i++) { if (s[i] <= 0) continue; const y0 = Y(acc[i]), y1 = Y(acc[i] + s[i]); acc[i] += s[i]; g.globalAlpha = o.hi === undefined || o.hi < 0 || o.hi === i ? 0.95 : 0.45; g.fillStyle = o.colors[k]; g.fillRect(X(i) - bw / 2, y1, bw, y0 - y1); } });
      g.globalAlpha = 1;
    } else ser.forEach((s, k) => {
      if (o.stacked) {
        g.globalAlpha = 0.85; g.fillStyle = o.colors[k]; g.beginPath(); g.moveTo(X(0), Y(acc[0] + s[0])); for (let i = 1; i < n; i++) g.lineTo(X(i), Y(acc[i] + s[i])); for (let i = n - 1; i >= 0; i--) g.lineTo(X(i), Y(acc[i])); g.closePath(); g.fill(); g.globalAlpha = 1;
        for (let i = 0; i < n; i++) acc[i] += s[i];
      } else {
        g.strokeStyle = o.colors[k]; g.lineWidth = o.widths ? o.widths[k] : 2; g.lineJoin = 'round'; g.beginPath(); g.moveTo(X(0), Y(s[0])); const step = o.stepLast && k === ser.length - 1;
        for (let i = 1; i < n; i++) { if (step) g.lineTo(X(i), Y(s[i - 1])); g.lineTo(X(i), Y(s[i])); } g.stroke();
      }
    });
    if (o.alerts) { g.fillStyle = BAD; const bw = Math.max(2, pw / n * 0.42); for (let i = 0; i < n; i++) if (o.alerts[i]) g.fillRect(X(i) - bw, PT + ph - 4, bw * 2, 4); }
    if (o.mark >= MINY && o.mark <= MAXY) { const x = Math.round(PL + pw * (o.mark - MINY) / 25) + 0.5; g.strokeStyle = 'rgba(253,252,252,.55)'; g.lineWidth = 1; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, PT); g.lineTo(x, PT + ph); g.stroke(); g.setLineDash([]); }
    g.strokeStyle = GREY; g.lineWidth = 1; g.beginPath(); g.moveTo(PL, PT + ph + 0.5); g.lineTo(PL + pw, PT + ph + 0.5); g.stroke();
  }
  function drawCharts() { for (const [cv, o] of charts) if (o.draw) o.draw(cv); else drawChart(cv, o); }

  // ---------------------------------------------------------------- moving about
  function goDistrict(d) { ui.district = d; const v = VIEWS.find(v => v.name === (d < 0 ? 'overview' : DIST[d])); if (v) goTo(v); refresh(true); }
  function goBuilding(b) { goTo({ target: [bX[b] * 2, 0, bZ[b] * 2], dist: Math.max(700, bHeight[b] / 10 * 9), yaw: S.yaw, pitch: 42 }); }
  function setTab(t) { if (t !== ui.tab) { const a = extra[ui.tab], b = extra[t]; ui.tab = t; if (a && a.leave) a.leave(); if (b && b.enter) b.enter(); } refresh(true); }
  function setScenario(s) {
    S.scen = s; U.uScen.value = s; U.uDevK.value = s === 1 ? 0.75 : s === 2 ? 1.3 : 1;
    const st = build(s), g2 = U.tGeo2.value.image.data; for (let b = 0; b < NB && b < 65536; b++) g2[b * 4 + 1] = st.eff[b]; U.tGeo2.value.needsUpdate = true;
    $('#scen').value = String(s); refresh(true);
  }
  function setOn(v) { ui.on = v; $('#an').hidden = !v; $('#side').hidden = v; $('#anb').classList.toggle('main', v); refresh(true); }

  // ---------------------------------------------------------------- M0 overview (OverviewModule)
  function overview(y, s, d) {
    const st = build(s), res = residents(st, d, y), g = gfaAll(st, d, y), jb = jobs(st, d, y), ready = readiness(st, d, y);
    const top = block(colL, null);
    if (d >= 0) {
      const back = el('button', 'ghost', tx('back_city')); back.onclick = () => goDistrict(-1); top.append(back);
      const head = el('div', 'dhead'), dot = el('span', 'dot big'); dot.style.background = DCOL[d]; head.append(dot, el('span', 'big', f(tx('district_of'), DIST[d]))); top.append(head);
      fact(top, tx('role'), tx('roles')[d]); fact(top, tx('area_ha'), N0(DAREA[d]) + ' ' + tx('ha'));
    }
    top.append(el('div', 'eyebrow', (d < 0 ? tx('eyebrow_city') : f(tx('district_of'), DIST[d])) + ' · ' + y + ' · ' + scenName(s)));
    top.append(el('div', 'summary', d < 0 ? (g < 1 ? f(tx('summary_city_0'), y) : f(tx('summary_city'), y, K(res), rint(ready * 100))) : f(tx('summary_district'), y, DIST[d], K(res), rint(100 * res / 1000 / DTARGET[d]))));
    top.append(el('div', 'meter-title', f(tx(d < 0 ? 'o_meter' : 'o_meter_d'), rint(ready * 100)))); meter(top, ready);
    kpis(top, [[K(res), tx('kpi_res_t')], [Mln(g), tx('kpi_gfa_t')], [K(jb), tx('kpi_jobs_t')], [N0(count(st, d, y)), tx('o_k_bld')]]);
    if (d < 0) {
      const t = block(colL, 'districts', tx('districts'), tx('o_dist_sub'));
      for (let i = 0; i < 4; i++) { const r = residents(st, i, y) / 1000, share = DTARGET[i] > 0 ? r / DTARGET[i] : 0; distRow(t, i, N0(r) + ' / ' + N0(DTARGET[i]) + ' · ' + rint(share * 100) + ' %', share >= 0.3 ? 'ok' : 'warn'); }
    }
    const gb = block(colL, 'growth', tx('chart_gfa'), tx('mln_m2'));
    chart(gb, { series: [0, 1, 2, 3, 4].map(c => Array.from({ length: NY }, (v, i) => gfa(st, d, c, MINY + i) / 1e6)), colors: CATCOL, stacked: true, mark: y });
    legend(gb, CATCOL.map((c, i) => [c, tx('cats')[i]]));
    // right: journal of the year and the conclusions
    const jb2 = block(colR, 'journal', f(tx('o_journal_y'), y)); journal(jb2, y, s, d, st);
    const ab = block(colR, 'ai', tx('o_ai'), tx('o_ai_sub')); insights(ab, y, s);
    about();
  }
  function journal(parent, y, s, d, st) {
    const items = [], yi = YI(y);
    ['power_hv', 'heat', 'sewer', 'water'].forEach((res, i) => {              // deficits that start this year
      const b = bal(s, res, d); if (!b) return;
      if (b.deficit[yi] > 0.5 && (yi === 0 || b.deficit[yi - 1] <= 0.5)) items.push([0, [tx('j_res')[i], 'bad', tx('o_crit'), f(tx('j_deficit'), d < 0 ? tx('j_city') : DIST[d], N0(b.deficit[yi]), tx('j_unit')[i]), String(y), tx('o_show'), () => { ui.metric = [0, 2, 3, 1][i]; setTab('prediction'); }]]);
    });
    let behind = 0, sites = 0;                                                // construction behind schedule
    for (let b = 0; b < NB; b++) {
      if (existing(b) || (d >= 0 && bDist[b] !== d)) continue;
      const plan = st.eff[b], start = plan - duration(b), fct = plan + Math.ceil(bDelay[b] / 12); if (y < start || y >= fct || plan > MAXY) continue;
      sites++; if (bDelay[b] > 0 && y >= plan - 1) behind++;
    }
    if (sites > 0) items.push([1, [tx('o_src_build'), behind > sites * 0.1 ? 'warn' : 'info', behind > 0 ? tx('o_mid') : '', f(tx('o_build'), N0(sites), N0(behind)), String(y), tx('o_open'), () => setTab('construction')]]);
    for (let p = 0; p < 3; p++) if (W.lrt.year[s][p] === y) items.push([2, [tx('j_lrt'), 'ok', tx('o_open_b'), f(tx('j_lrt_open'), p + 1, W.lrt.names[p], N1(W.lrt.km[p])), String(y)]]);
    let fc = 0;
    for (const fa of W.fac) { if (d >= 0 && fa.district !== d) continue; const stg = fa.stages[s].indexOf(y); if (stg < 0 || fc >= 3) continue; fc++;
      items.push([3, [tx('o_src_net'), 'ok', tx('o_in'), stg === 0 ? f(tx('j_fac_first'), fa.name) : f(tx('j_fac_stage'), fa.name, stg + 1), String(y)]]); }
    const nb = newThisYear(st, d, y), dg = (gfaAll(st, d, y) - gfaAll(st, d, y - 1)) / 1000;
    if (nb > 0) items.push([4, [tx('o_src_new'), 'info', '', f(tx('o_new'), N0(nb), N0(dg)), String(y)]]);
    if (!items.length) { parent.append(el('div', 'note', tx('o_quiet'))); return; }
    items.sort((a, b) => a[0] - b[0]); for (const it of items.slice(0, 5)) jcard(parent, ...it[1]);
  }
  function insights(parent, y, s) {
    const add = t => parent.append(el('div', 'insight', t));
    let fy = -1, fd = -1, fv = 0;                                             // the first power deficit
    for (let i = 0; i < NY && fy < 0; i++) for (let k = 0; k < 4; k++) { const b = bal(s, 'power_hv', k); if (b && b.deficit[i] > 0.5) { fy = MINY + i; fd = k; fv = b.deficit[i]; break; } }
    add(fy > 0 ? f(tx('in_power'), fy, DIST[fd], N1(fv)) : tx('in_power_ok'));
    const ys = Math.max(y, 2030), yi = YI(ys); let w = -1, wc = 2;             // schools
    for (let k = 0; k < 4; k++) { const nd = W.soc.need[s][k][0][yi], cp = W.soc.cap[s][k][0][yi]; if (nd > 500 && cp / nd < wc) { wc = cp / nd; w = k; } }
    if (w >= 0 && wc < 1) add(f(tx('in_school'), ys, DIST[w], rint(wc * 100), N0(W.soc.need[s][w][0][yi] - W.soc.cap[s][w][0][yi])));
    const ty = W.tr.years; let ti = 0; while (ti < ty.length - 1 && ty[ti] < Math.max(y, 2030)) ti++;   // traffic
    if (ty.length && W.tr.kpi[s][ti].congested_km !== undefined) add(f(tx('in_traffic'), ty[ti], N0(W.tr.kpi[s][ti].congested_km)));
  }
  function about() {
    const n = block(colR, 'about', tx('about')); n.append(el('div', 'note', tx('model_note')), el('div', 'note', tx('about_more')), el('div', 'note', $('#side p:first-child').textContent), el('div', 'note', $('#side p:last-child').textContent));
  }

  // ---------------------------------------------------------------- M1 construction (ConstructionModule, numbers only)
  function constructionTab(y, s, d) {
    const c = construction(y, s), yi = YI(y), behindPct = c.sites > 0 ? 100 * c.behind / c.sites : 0;
    let plan = 0, fct = 0, infra = 0;
    for (let k = 0; k < 4; k++) { for (let q = 0; q < 5; q++) plan += W.fin.bld[s][k][q][yi]; fct += W.fin.fact[s][k][yi]; }
    for (const k in W.fin.infra[s]) infra += W.fin.infra[s][k][yi];
    const planAll = plan + infra, factAll = fct + infra, pct = planAll > 0 ? 100 * factAll / planAll : 100;
    let wcn = -1, wv = 0; for (let k = 0; k < c.behC.length; k++) if (c.behC[k] > wv) { wv = c.behC[k]; wcn = k; }
    const who = wcn >= 0 ? W.contractors[wcn] : '—', top = block(colL, null);
    top.append(el('div', 'eyebrow', tx('tab_construction') + ' · ' + y + ' · ' + scenName(s)));
    top.append(el('div', 'summary', c.sites === 0 ? f(tx('c_sum_none'), y) : c.behind === 0 ? f(tx('c_sum_ok'), y, N0(c.sites), N1(c.inWork / 1e6))
      : behindPct > 97 ? f(tx('c_sum_tail'), y, N0(c.sites), who) : f(tx('c_sum'), y, N0(c.sites), N1(c.inWork / 1e6), rint(behindPct), who)));
    kpis(top, [[N0(c.sites), tx('c_k_sites')], [N1(c.inWork / 1e6), tx('c_k_gfa')], [N0(c.behind), f(tx('c_k_behind'), rint(behindPct)), behindPct > 15 ? 'bad' : behindPct > 5 ? 'warn' : 'ok'],
      [N0(factAll), f(tx('c_k_money'), rint(pct)), pct < 90 ? 'warn' : '']]);
    const sb = block(colL, 'scurve', tx('c_scurve'), tx('c_scurve_u')), pl = new Array(NY).fill(0), fa = new Array(NY).fill(0);
    for (let i = 0; i < NY; i++) for (let k = 0; k < 4; k++) if (d < 0 || k === d) { pl[i] += W.sc.plan[s][k][i]; fa[i] += W.sc.fact[s][k][i]; }
    chart(sb, { series: [pl, fa], colors: [GREY, WHITE], widths: [1.5, 2.5], mark: y }); legend(sb, [[GREY, tx('c_plan')], [WHITE, tx('c_fact')]]);
    const gp = pl[yi], gf = fa[yi]; sb.append(el('div', 'note gap', gp - gf > 0.05 ? f(tx('c_gap'), y, N1(gp - gf), rint(100 * (gp - gf) / Math.max(gp, 0.01)), N1(gp)) : f(tx('c_gap0'), y, N1(gp))));
    const mb = block(colL, 'money', tx('c_money'), tx('c_money_u')), share = [0.60, 0, 0.10, 0.30], ser = [0, 1, 2, 3].map(() => new Array(NY).fill(0));
    for (let i = 0; i < NY; i++) { let inf = 0; for (const k in W.fin.infra[s]) inf += W.fin.infra[s][k][i]; for (let k = 0; k < 4; k++) { let v = inf * share[k]; for (let q = 0; q < 4; q++) v += W.fin.src[s][q][k][i]; ser[k][i] = v; } }
    const SRC = ['#7aa6ff', WHITE, WARN, GREY]; chart(mb, { series: ser, colors: SRC, bars: true, hi: yi }); legend(mb, SRC.map((cl, i) => [cl, tx('src')[i]]));
    mb.append(el('div', 'note gap', f(tx('c_money_note'), y, N0(planAll), N0(factAll), rint(pct), N0(infra))));
    // right: the worst sites and the contractors
    const wb = block(colR, 'worst', tx('c_worst'), tx('c_worst_sub'));
    if (!c.worst.length) wb.append(el('div', 'note', tx('c_worst_none')));
    for (const site of c.worst) {
      const r = el('div', 'drow click'), t1 = el('div', 'row'), dot = el('span', 'dot'); dot.style.background = BAD;
      t1.append(dot, el('span', 'n', (tx('kind')[kindOf(site.b)] || kindOf(site.b)) + ' · ' + (DIST[bDist[site.b]] || '—')), el('span', 's bad', '+' + site.delayM + ' ' + tx('months')));
      const cn = bCon[site.b]; r.append(t1, el('div', 'note sub', f(tx('c_worst_row'), cn < W.contractors.length ? W.contractors[cn] : '—', N0(site.gfa), site.plan, site.fact, rint(site.prog * 100))));
      r.onclick = () => goBuilding(site.b); wb.append(r);
    }
    const cb = block(colR, 'contractors', tx('c_contractors'), tx('c_contractors_sub'));
    const idx = Array.from(c.byC.keys()).filter(i => c.byC[i] > 0).sort((a, b) => c.behC[b] / c.byC[b] - c.behC[a] / c.byC[a]).slice(0, 4);
    if (!idx.length) cb.append(el('div', 'note', tx('c_worst_none')));
    for (const i of idx) { const sh = 100 * c.behC[i] / c.byC[i], r = fact(cb, W.contractors[i] + '  ·  ' + N0(c.byC[i]) + ' ' + tx('c_sites_short'), rint(sh) + ' % ' + tx('c_behind_short')); r.lastChild.className = 's ' + (sh > 15 ? 'bad' : sh > 5 ? 'warn' : 'ok'); }
    const nb = block(colR, null); nb.append(el('div', 'note', tx('c_note')), el('div', 'note', tx('c_whole')));
    about();
  }

  // ---------------------------------------------------------------- M2 forecast (PredictionModule)
  const METRICS = [['net', 'power_hv'], ['net', 'water'], ['net', 'heat'], ['net', 'sewer'], ['net', 'gas'], ['soc', 0], ['soc', 1], ['soc', 2], ['tr'], ['quake'], ['flood']];
  const stOf = (b, yi) => b.deficit[yi] > 0.5 ? 'bad' : b.cap[yi] > 0 && b.demand[yi] > 0.85 * b.cap[yi] ? 'warn' : 'ok';
  const quakeP = b => existing(b) ? (bHeight[b] / 10 > 12 ? 0.22 : 0.35) : (k => k === 'house' ? 0.06 : k === 'res_high' || k === 'tower' ? 0.07 : k === 'solar' ? 0 : 0.03)(kindOf(b));
  const peopleIn = b => housing(b) ? bGfa[b] / 30 : existing(b) ? Math.max(3, bGfa[b] / 35) : 0;
  function predictionTab(y, s) {
    const mi = ui.metric, [kind, arg] = METRICS[mi], name = tx('m')[mi], unit = tx('unit')[mi], st = build(s), yi = YI(y);
    const top = block(colL, null); top.append(el('div', 'eyebrow', tx('tab_prediction') + ' · ' + y + ' · ' + scenName(s)));
    for (const [gk, idx] of [['p_g_nets', [0, 1, 2, 3, 4]], ['p_g_social', [5, 6, 7]], ['p_g_city', [8, 9, 10]]]) { top.append(el('div', 'glabel', tx(gk))); chips(top, idx.map(i => [i, tx('m')[i]]), mi, i => { ui.metric = i; ui.why = false; refresh(true); }); }
    const summary = el('div', 'summary'); top.append(summary);
    const kp = []; const kset = (i, v, l, cls) => { kp[i] = [v, l, cls || '']; };
    const cb = block(colR, 'pchart', ' '), ctitle = cb.querySelector('.bt'), rb = block(colR, 'prows', ' ', ' '), rtitle = rb.querySelector('.bt'), rsub = rb.querySelector('.bs');
    let lg = null, chartNote = '', rowsKey = 'p_districts';
    if (kind === 'net') {
      const city = bal(s, arg, -1), k = arg === 'water' || arg === 'sewer' || arg === 'gas' ? 0.001 : 1, dstat = [];
      for (let d = 0; d < 4; d++) { const b = bal(s, arg, d); dstat.push(stOf(b || city, yi)); }
      applyTint(districtTint(dstat));
      let fy = -1, fd = -1, fv = 0;                                           // the first deficit in any district: the one-line answer
      for (let i = 0; i < NY && fy < 0; i++) { for (let d = 0; d < 4; d++) { const b = bal(s, arg, d); if (b && b.deficit[i] > 0.5) { fy = MINY + i; fd = d; fv = b.deficit[i]; break; } } if (fy < 0 && city.deficit[i] > 0.5) { fy = MINY + i; fd = -1; fv = city.deficit[i]; } }
      const dem = city.demand[yi], cap = city.cap[yi], def = city.deficit[yi];
      let cause; if (s === 1) cause = tx('p_cause_fast'); else { const fa = W.fac.find(x => x.res === arg && (fd < 0 || x.district === fd) && x.delayed.length > 0);
        if (!fa) cause = tx('p_cause_peak'); else { const sg = fa.delayed[0]; cause = f(tx('p_cause_delay'), sg, fa.name, sg - 1 < fa.stages[s].length ? fa.stages[s][sg - 1] : 0); } }
      summary.textContent = fy < 0 ? f(tx('p_sum_net_ok'), getLang() === 'ru' ? name.toLowerCase() : name, scenName(s)) : f(tx('p_sum_net'), fy, fd >= 0 ? DIST[fd] : tx('p_city'), F1(fv * k), unit, cause);
      kset(0, F1(dem * k), f(tx('p_k_dem'), y, unit)); kset(1, F1(cap * k), f(tx('p_k_cap'), unit));
      kset(2, cap > 0 ? rint(100 * dem / cap) + ' %' : '—', tx('p_k_util'), def > 0.5 ? 'bad' : dem > cap * 0.85 ? 'warn' : 'ok'); kset(3, fy < 0 ? '—' : String(fy), tx('p_k_first'), fy < 0 ? 'ok' : 'bad');
      ctitle.textContent = f(tx('p_chart_net'), name);
      const alerts = []; for (let i = 0; i < NY; i++) { let a = city.deficit[i] > 0.5; for (let d = 0; d < 4; d++) { const b = bal(s, arg, d); if (b && b.deficit[i] > 0.5) a = true; } alerts.push(a); }
      chart(cb, { series: [city.demand.map(v => v * k), city.cap.map(v => v * k)], colors: [WHITE, GREY], widths: [2.5, 1.5], stepLast: true, alerts, mark: y });
      legend(cb, [[WHITE, tx('p_demand')], [GREY, tx('p_capacity')], [BAD, tx('p_deficit_years')]]); chartNote = tx('p_chart_net_note');
      for (let d = 0; d < 4; d++) {
        const b = bal(s, arg, d), ld = load(s, arg === 'power_hv' ? 'power' : arg, d, y), sd = b ? stOf(b, yi) : stOf(city, yi);
        let first = -1; if (b) for (let i = 0; i < NY; i++) if (b.deficit[i] > 0.5) { first = MINY + i; break; }
        distRow(rb, d, b ? F1(b.demand[yi] * k) + ' / ' + F1(b.cap[yi] * k) + ' ' + unit : F1(ld * k) + ' ' + unit + ' · ' + tx('p_pooled'), '', first >= 0 ? f(tx('p_row_first'), first) : tx('p_row_none'), sd === 'ok' ? '' : sd);
      }
      lg = [[OK, tx('p_lg_ok')], [WARN, tx('p_lg_warn')], [BAD, tx('p_lg_bad')]];
    } else if (kind === 'soc') {
      const need = W.soc.need[s], cap = W.soc.cap[s], dstat = [], cov = []; let needC = 0, capC = 0;
      for (let d = 0; d < 4; d++) { const nd = need[d][arg][yi], cp = cap[d][arg][yi]; needC += nd; capC += cp; cov.push(nd > 0 ? cp / nd : 1); dstat.push(nd < 1 ? 'ok' : cov[d] < 0.9 ? 'bad' : cov[d] < 1 ? 'warn' : 'ok'); }
      applyTint(districtTint(dstat));
      let worst = -1, wv = 0; for (let d = 0; d < 4; d++) { const gap = need[d][arg][yi] - cap[d][arg][yi]; if (gap > wv) { wv = gap; worst = d; } }
      const covC = needC > 0 ? capC / needC : 1, lname = getLang() === 'ru' ? name.toLowerCase() : name.toLowerCase();
      summary.textContent = worst < 0 ? f(tx('p_sum_soc_ok'), y, lname) : f(tx('p_sum_soc'), y, DIST[worst], N0(wv), unit, lname, rint(cov[worst] * 100));
      kset(0, N0(needC), f(tx('p_k_need'), unit)); kset(1, N0(capC), f(tx('p_k_have'), unit)); kset(2, rint(covC * 100) + ' %', tx('p_k_cov'), covC < 0.9 ? 'bad' : covC < 1 ? 'warn' : 'ok');
      kset(3, N0(Math.max(0, needC - capC)), f(tx('p_k_gap'), unit), needC > capC ? 'warn' : 'ok');
      ctitle.textContent = f(tx('p_chart_soc'), name);
      const sn = new Array(NY).fill(0), sc = new Array(NY).fill(0), alerts = new Array(NY).fill(false);
      for (let i = 0; i < NY; i++) for (let d = 0; d < 4; d++) { sn[i] += need[d][arg][i]; sc[i] += cap[d][arg][i]; if (need[d][arg][i] > cap[d][arg][i] * 1.1 && need[d][arg][i] > 50) alerts[i] = true; }
      chart(cb, { series: [sn.map(v => v / 1000), sc.map(v => v / 1000)], colors: [WHITE, GREY], widths: [2.5, 1.5], alerts, mark: y });
      legend(cb, [[WHITE, tx('p_need')], [GREY, tx('p_have')], [BAD, tx('p_short_years')]]); chartNote = tx('p_chart_soc_note');
      for (let d = 0; d < 4; d++) { const nd = need[d][arg][yi], cp = cap[d][arg][yi]; distRow(rb, d, N0(cp) + ' / ' + N0(nd) + ' ' + unit, '', nd > cp ? f(tx('p_row_short'), N0(nd - cp), rint(cov[d] * 100)) : tx('p_row_enough'), dstat[d] === 'ok' ? '' : dstat[d]); }
      lg = [[OK, tx('p_lg_ok')], [WARN, tx('p_lg_warn')], [BAD, tx('p_lg_bad')]];
    } else if (kind === 'tr') {
      applyTint(null); const ys = W.tr.years; let ti = 0; while (ti < ys.length - 1 && ys[ti] < y) ti++;
      const kpi = W.tr.kpi[s][ti], ck = kpi.congested_km || 0, dl = kpi.avg_delay_pct || 0, car = kpi.car_trips || 0, lrt = kpi.lrt_trips || 0; let ph = -1; for (let i = 0; i < 3; i++) if (W.lrt.year[s][i] <= y) ph = i;
      summary.textContent = f(tx('p_sum_tr'), ys[ti], N0(ck), rint(dl), ph < 0 ? f(tx('p_lrt_none'), W.lrt.year[s][0]) : f(tx('p_lrt_on'), ph + 1, N1(lrt / 1000)));
      kset(0, N0(ck), tx('p_k_cong'), ck > 150 ? 'bad' : ck > 60 ? 'warn' : 'ok'); kset(1, '+' + rint(dl) + ' %', tx('p_k_delay'), dl > 35 ? 'bad' : dl > 15 ? 'warn' : 'ok');
      kset(2, N1(car / 1000), tx('p_k_cars')); kset(3, lrt > 0 ? rint(100 * lrt / Math.max(lrt + car * 1.3, 1)) + ' %' : '—', tx('p_k_lrt'));
      ctitle.textContent = tx('p_chart_tr');
      const v = (sc, i) => W.tr.kpi[sc][i].congested_km || 0, interp = (sc, yr) => { if (yr <= ys[0]) return v(sc, 0) * Math.min(Math.max((yr - MINY) / (ys[0] - MINY), 0), 1);
        for (let i = 1; i < ys.length; i++) if (yr <= ys[i]) return v(sc, i - 1) + (v(sc, i) - v(sc, i - 1)) * (yr - ys[i - 1]) / (ys[i] - ys[i - 1]); return v(sc, ys.length - 1); };
      const cols = [WHITE, WARN, GREY, '#7aa6ff'];
      chart(cb, { series: [0, 1, 2, 3].map(sc => Array.from({ length: NY }, (q, i) => interp(sc, MINY + i))), colors: cols, widths: [0, 1, 2, 3].map(i => i === s ? 3 : 1.2), mark: y });
      legend(cb, cols.map((c, i) => [c, scenName(i)])); chartNote = tx('p_chart_tr_note'); rowsKey = 'p_rows_tr';
      for (let p = 0; p < 3; p++) fact(rb, f(tx('p_lrt_phase'), p + 1, W.lrt.names[p]), W.lrt.year[s][p] + ' · ' + N1(W.lrt.km[p]) + ' ' + tx('km'));
    } else if (kind === 'quake') {
      let heavy = 0, peopleRisk = 0, high = 0; const ser = [new Array(NY).fill(0), new Array(NY).fill(0)];
      for (let b = 0; b < NB; b++) {
        const p = quakeP(b), ex = existing(b), e = st.eff[b];
        if (ex || e <= y) { heavy += p; if (p >= 0.2) high++; peopleRisk += peopleIn(b) * p; }
        const e2 = ex ? MINY : e; if (e2 > MAXY) continue; for (let i = Math.min(Math.max(e2 - MINY, 0), NY - 1); i < NY; i++) ser[p >= 0.2 ? 0 : 1][i] += p;
      }
      applyTint(b => { if (!existing(b) && st.eff[b] > y) return null; const p = quakeP(b); return p >= 0.2 ? [...BADc, 0.9] : p >= 0.06 ? [...WARNc, 0.7] : [...OKc, 0.4]; });
      summary.textContent = f(tx('p_sum_quake'), y, N0(heavy), N0(high), N0(peopleRisk));
      kset(0, N0(high), tx('p_k_q_high'), high > 0 ? 'bad' : 'ok'); kset(1, N0(heavy), tx('p_k_q_heavy'), 'warn'); kset(2, N0(peopleRisk), tx('p_k_q_people')); kset(3, rint(6 + heavy / 400) + ' ' + tx('p_months'), tx('p_k_q_restore'));
      ctitle.textContent = tx('p_chart_q'); chart(cb, { series: ser, colors: [BAD, WARN], stacked: true, mark: y }); legend(cb, [[BAD, tx('p_q_old')], [WARN, tx('p_q_new')]]); chartNote = tx('p_chart_q_note');
      rowsKey = 'p_rows_q'; fact(rb, tx('p_q_scn'), tx('p_q_scn_v')); fact(rb, tx('p_q_norm'), 'СП РК 2.03-30-2017');
      lg = [[BAD, tx('p_lg_q3')], [WARN, tx('p_lg_q2')], [OK, tx('p_lg_q1')]];
    } else {
      const fcm = bFlood[ui.floodExt ? 1 : 0], a1 = new Array(NY).fill(0); let n = 0, deep = 0, people = 0, damage = 0;
      for (let b = 0; b < NB; b++) {
        const cm = fcm[b]; if (cm <= 0) continue; const ex = existing(b), e = st.eff[b];
        if (ex || e <= y) { n++; if (cm > 100) deep++; people += peopleIn(b); damage += bGfa[b] * 300000 * Math.min(0.4, Math.min(Math.max(cm / 100 / Math.max(3, bHeight[b] / 10), 0), 1) + 0.05) / 1e9; }
        const e2 = ex ? MINY : e; if (e2 > MAXY) continue; for (let i = Math.min(Math.max(e2 - MINY, 0), NY - 1); i < NY; i++) a1[i] += 1;
      }
      applyTint(b => { if (!existing(b) && st.eff[b] > y) return null; const cm = fcm[b]; return cm <= 0 ? null : cm > 100 ? [0.15, 0.40, 0.95, 0.95] : [0.55, 0.75, 1, 0.85]; });
      summary.textContent = n === 0 ? tx('p_sum_flood_0') : f(tx('p_sum_flood'), tx(ui.floodExt ? 'p_f_ext' : 'p_f_1'), y, N0(n), N0(people), N0(damage));
      kset(0, N0(n), tx('p_k_f_n'), n > 0 ? 'warn' : 'ok'); kset(1, N0(deep), tx('p_k_f_deep'), deep > 0 ? 'bad' : 'ok'); kset(2, N0(people), tx('p_k_f_people')); kset(3, N0(damage), tx('p_k_f_damage'));
      ctitle.textContent = tx('p_chart_f'); chart(cb, { series: [a1], colors: ['#4da3ff'], stacked: true, mark: y }); legend(cb, [['#4da3ff', tx('p_f_buildings')]]); chartNote = tx('p_chart_f_note');
      rowsKey = 'p_rows_f'; chips(rb, [[false, tx('p_f_1')], [true, tx('p_f_ext')]], ui.floodExt, v => { ui.floodExt = v; refresh(true); });
      lg = [['#8cbfff', tx('p_lg_flood1')], ['#2666f2', tx('p_lg_flood2')], ['#9e9e9e', tx('p_lg_dry')]];
    }
    kpis(top, kp);
    const wbtn = el('button', 'ghost', tx(ui.why ? 'p_why_hide' : 'p_why')); wbtn.onclick = () => { ui.why = !ui.why; refresh(true); }; top.append(wbtn); if (ui.why) top.append(el('div', 'note why', tx('why')[mi]));
    const lb = block(colL, 'plegend', tx('p_lg')); if (lg) legend(lb, lg); else lb.append(el('div', 'note', tx('p_lg_tr')));
    cb.append(el('div', 'note gap', chartNote)); rtitle.textContent = tx(rowsKey); rsub.textContent = rowsKey === 'p_districts' ? tx('p_districts_sub') : '';
    const nb = block(colR, null); nb.append(el('div', 'note', tx('p_note'))); about();
  }

  // ---------------------------------------------------------------- drawing the panels
  function refresh(force) {
    const k = [ui.on, ui.tab, ui.district, ui.metric, ui.why, ui.floodExt, S.year, S.scen, getLang()].join('|'); if (!force && k === key) return; key = k;
    U.uTint.value = ui.on && ui.tab === 'prediction' ? 1 : 0;
    for (const fn of listeners) fn();
    $('#anb').textContent = tx('analytics'); $('#scenl').textContent = tx('scenario');
    const sel = $('#scen'); if (sel.dataset.lang !== getLang()) { sel.replaceChildren(...[0, 1, 2, 3].map(i => { const o = el('option', '', scenName(i)); o.value = String(i); return o; })); sel.dataset.lang = getLang(); sel.value = String(S.scen); }
    sel.title = getLang() === 'ru' ? W.scen[S.scen].desc : '';
    if (!ui.on) return;
    const keepL = colL.scrollTop, keepR = colR.scrollTop; colL.replaceChildren(); colR.replaceChildren(); charts = [];
    const tabs = el('div', 'tabs'); for (const t of ['overview', 'construction', 'prediction', ...Object.keys(extra)]) { const b = el('button', ui.tab === t ? 'on' : '', extra[t] ? extra[t].label() : tx('tab_' + t)); b.onclick = () => setTab(t); tabs.append(b); } colL.append(tabs);
    const y = S.year, s = S.scen;
    if (extra[ui.tab]) { extra[ui.tab].render(colL, colR, y, s); about(); } else if (ui.tab === 'overview') overview(y, s, ui.district); else if (ui.tab === 'construction') constructionTab(y, s, ui.district); else predictionTab(y, s);
    colL.scrollTop = keepL; colR.scrollTop = keepR; drawCharts();
  }
  S.scen = 0; build(0);
  $('#scen').onchange = e => setScenario(+e.target.value); $('#anb').onclick = () => setOn(!ui.on);
  const fit = () => { const r = document.documentElement.style; r.setProperty('--barh', $('#bar').offsetHeight + 'px'); r.setProperty('--toph', $('#top').offsetHeight + 'px'); drawCharts(); };
  new ResizeObserver(fit).observe($('#bar')); new ResizeObserver(fit).observe($('#top')); addEventListener('resize', fit); fit();
  for (const c of [colL, colR]) c.addEventListener('wheel', e => e.stopPropagation(), { passive: true });
  setOn(ui.on);
  return { refresh, lang: () => refresh(true), setScenario, setTab, setOn, ui, build, construction, residents, jobs, readiness, gfaAll, count, effYear, bal, goDistrict, drawCharts,
    addTab: (id, t) => { extra[id] = t; refresh(true); }, onChange: fn => listeners.push(fn), charts: () => charts,
    h: { el, block, kpis, legend, fact, chips, chart, drawChart, tx, f, N0, N1, K, rint, YI, scenName, DIST, DCOL, OK, WARN, BAD, WHITE, GREY },
    b: { bDist, bUse, bSrc, bDur, bDelay, bCon, bGfa, bX, bZ, bFlood, existing, housing, kindOf, duration, quakeP, peopleIn, M2JOB, CAT },
    check: () => {       // the page's own aggregates against the residents and jobs the data generator wrote (same formula, independent code)
      let worst = 0; for (let s = 0; s < 4; s++) { const st = build(s); for (let d = 0; d < 4; d++) for (let i = 0; i < NY; i++) {
        const a = residents(st, d, MINY + i), b = W.loads.res[s][d][i], c = jobs(st, d, MINY + i), e = W.loads.jobs[s][d][i]; worst = Math.max(worst, Math.abs(a - b) / Math.max(b, 1000), Math.abs(c - e) / Math.max(e, 1000)); } }
      return worst; } };
}
