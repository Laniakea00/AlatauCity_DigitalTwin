'use strict';
// Labels over the city and object passports: a label lights up, a click flies the camera to the object and opens its passport.
// Also: picking a building in the 3D view, and the rivers of the model laid on the page's ground.
// All facts come from the twin's data (buildings.csv, networks.json, construction.json, risk.json); see analytics.js for the formulas.
const GLSL_WATER = `
{
  float n1W = ANoise(vWp.xz * 0.045), n3W = ANoise(vWp.xz * 0.9);
  vec3 viewW = normalize(uCamU - vWp);
  float fresW = 0.04 + 0.96 * pow(1.0 - saturate(viewW.y), 5.0);
  vec3 rdirW = reflect(-viewW, normalize(vec3((n1W - 0.5) * 0.04, 1.0, (n3W - 0.5) * 0.04)));
  vec3 fW = vec3(0.10, 0.19, 0.25);
  diffuseColor.rgb = fW;
  filmEmit = fW * (0.06 + 0.08 * uSunCol * uSunInt) + fW * AmbTri(vec3(0.0, 1.0, 0.0)) + AlatauSky(rdirW) * (0.18 + 0.75 * fresW);
}
`;
async function AlatauObjects(api) {
  const { DATA, gunzip, S, U, goTo, Hgt, scene, camera, canvas, film, bMeshes, getLang, AN, NB, bYear, bHeight, bFloors } = api;
  const W = DATA.twin, $ = s => document.querySelector(s), H = AN.h, B = AN.b, { el, block, kpis, legend, fact, f, N0, N1, rint, YI, DIST, DCOL, OK, WARN, BAD, WHITE, GREY } = H;
  const ot = k => { const l = OBJ_TEXT[getLang()] || OBJ_TEXT.ru; return l[k] !== undefined ? l[k] : OBJ_TEXT.ru[k] !== undefined ? OBJ_TEXT.ru[k] : k; };
  const MAXY = 2050, clamp = (v, a, b) => Math.min(Math.max(v, a), b);
  const UNIT_EN = { 'МВт': 'MW', 'Гкал/ч': 'Gcal/h', 'м³/ч': 'm³/h', 'м³/сут': 'm³/day', 'м³/сут (макс. сутки)': 'm³/day (peak day)' };
  const unitOf = res => { const u = W.units[res] || ''; return getLang() === 'ru' ? u : (UNIT_EN[u] || u); };

  // ---------------------------------------------------------------- rivers of the model, laid on the page's ground
  const rivers = { xz: null, tri: null };
  {
    const r = await gunzip(DATA.rivers), dv = new DataView(r.buffer), nv = dv.getUint32(0, true), nt = dv.getUint32(4, true);
    const q = new Int32Array(r.buffer.slice(8, 8 + nv * 8)), tri = new Uint16Array(r.buffer.slice(8 + nv * 8, 8 + nv * 8 + nt * 6)), pos = new Float32Array(nv * 3), xz = new Float32Array(nv * 2);
    for (let i = 0; i < nv; i++) { const x = q[i * 2] / 10, z = q[i * 2 + 1] / 10; xz[i * 2] = x; xz[i * 2 + 1] = z; pos[i * 3] = x; pos[i * 3 + 1] = Hgt(x, z) + 0.15; pos[i * 3 + 2] = -z; }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setIndex(new THREE.BufferAttribute(tri, 1)); g.computeVertexNormals(); g.computeBoundingSphere();
    const m = new THREE.Mesh(g, film(new THREE.MeshPhongMaterial({ shininess: 0, specular: 0x000000, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2 }),
      { vsDecl: 'varying vec3 vWp;', vsMain: 'vWp = vec3(position.x, position.y, -position.z);', fsDecl: 'varying vec3 vWp;', color: GLSL_WATER }));
    m.receiveShadow = true; scene.add(m); rivers.xz = xz; rivers.tri = tri; rivers.mesh = m;
  }

  // ---------------------------------------------------------------- labels
  const layer = $('#lab'), labels = [], lab = { on: true }; let textKey = '', stamp = 0;
  /** o: pos [x, y, z] in the map frame, text(), icon, color, cls (string or function), prio, vis(), click(); far / near = limits of the distance from the camera. */
  function addLabel(o) {
    const e = el('div', 'lb'), i = el('i', '', o.icon || ''), t = el('span'); i.style.background = o.color || '#888'; e.append(i, t); e.style.display = 'none';
    e.onclick = ev => { ev.stopPropagation(); if (o.click) o.click(); }; e.onpointerdown = ev => ev.stopPropagation();
    layer.append(e); o.el = e; o.t = t; o.w = 0; o.shown = false; labels.push(o); labels.sort((a, b) => (b.prio || 0) - (a.prio || 0)); return o;
  }
  const v3 = new THREE.Vector3(); let bars = [70, 120], tickN = 0;      // height of the top and bottom bars: labels stay between them
  const measure = () => { bars = [$('#top').getBoundingClientRect().bottom + 6, canvas.clientHeight - $('#bar').getBoundingClientRect().top + 4]; }; addEventListener('resize', measure);
  function frame() {
    if (tickN++ % 90 === 0) measure();
    const cp = camera.position, w = canvas.clientWidth, h = canvas.clientHeight, key = getLang() + '|' + S.year + '|' + S.scen + '|' + (sel ? sel.type + sel.id : '') + '|' + stamp, taken = []; textKey = key;
    for (const o of labels) {
      let show = lab.on && o.vis();
      if (show && (o.far || o.near)) { const dc = Math.hypot(cp.x - o.pos[0], cp.y - o.pos[1], cp.z + o.pos[2]); show = !(o.far && dc > o.far) && !(o.near && dc < o.near); }
      if (show) { v3.set(o.pos[0], o.pos[1], -o.pos[2]).project(camera); show = v3.z < 1 && v3.z > -1 && Math.abs(v3.x) < 1.02 && Math.abs(v3.y) < 1.02; }
      if (show) {
        if (o.key !== key || !o.w) { o.key = key; const t = o.text(); if (o.t.textContent !== t) o.t.textContent = t; o.el.className = 'lb ' + (typeof o.cls === 'function' ? o.cls() : o.cls || ''); o.el.style.display = ''; o.shown = true; o.w = o.el.offsetWidth; }
        const sx = (v3.x * 0.5 + 0.5) * w, sy = (-v3.y * 0.5 + 0.5) * h, x0 = sx - o.w / 2, y0 = sy - 36;
        if (y0 < bars[0] || sy > h - bars[1]) show = false;
        if (show && !o.always) for (const r of taken) if (x0 < r[0] + r[2] + 4 && x0 + o.w + 4 > r[0] && y0 < r[1] + 25 && y0 + 25 > r[1]) { show = false; break; }
        if (show) { taken.push([x0, y0, o.w]); o.el.style.transform = 'translate(' + Math.round(x0) + 'px,' + Math.round(y0) + 'px)'; }
      }
      if (show !== o.shown) { o.el.style.display = show ? '' : 'none'; o.shown = show; }
    }
  }
  const fly = (x, z, dist) => goTo({ target: [x, 0, z], dist, yaw: S.yaw, pitch: clamp(S.pitch, 30, 48) });

  // ---------------------------------------------------------------- what gets a label
  const RESCOL = { power_hv: '#f5c518', power: '#e0b020', heat: '#ff6b4a', water: '#3b9cff', sewer: '#8a6bd1', gas: '#ff9f1c', renewable: '#34c759', telecom: '#9aa5b1' };
  const facState = i => { const fa = W.fac[i], s = S.scen, yi = YI(S.year), done = fa.stages[s].filter(v => v <= S.year).length; if (!done) return 'plan';
    if (!fa.cap || !fa.demand) return 'ok'; const c = fa.cap[s][yi], d = fa.demand[s][yi]; return d > c + 1e-6 ? 'bad' : c > 0 && d > 0.85 * c ? 'warn' : 'ok'; };
  W.fac.forEach((fa, i) => { const big = fa.kind !== 'substation' && fa.kind !== 'boiler';
    addLabel({ pos: [fa.x, Hgt(fa.x, fa.z) + 30, fa.z], text: () => fa.name, color: RESCOL[fa.res] || '#888', prio: big ? 60 : 45, far: big ? 42000 : 12000, vis: () => true,
      cls: () => { const st = facState(i); return (st === 'plan' ? 'dim' : st) + (sel && sel.type === 'f' && sel.id === i ? ' sel' : ''); }, icon: '', click: () => { fly(fa.x, fa.z, 1500); select('f', i); } }); });
  W.lrt.stations.forEach((st, i) => addLabel({ pos: [st[0], Hgt(st[0], st[1]) + 14, st[1]], text: () => ot('l_lab'), color: '#e0261b', prio: 30, far: 7000, vis: () => true,
    cls: () => (W.lrt.year[S.scen][st[2]] > S.year ? 'dim' : '') + (sel && sel.type === 'l' && sel.id === i ? ' sel' : ''), click: () => { fly(st[0], st[1], 900); select('l', i); } }));
  {
    const cen = [0, 1, 2, 3].map(() => [0, 0, 0]), tall = [-1, -1, -1, -1];
    for (let b = 0; b < NB; b++) { const d = B.bDist[b]; if (d > 3) continue; cen[d][0] += B.bX[b] * 2; cen[d][1] += B.bZ[b] * 2; cen[d][2]++; if (B.kindOf(b) === 'tower' && (tall[d] < 0 || bHeight[b] > bHeight[tall[d]])) tall[d] = b; }
    cen.forEach((c, d) => { const x = c[0] / c[2], z = c[1] / c[2]; addLabel({ pos: [x, Hgt(x, z) + 300, z], text: () => DIST[d] + ' District', cls: 'dist', color: DCOL[d], prio: 80, near: 8000, vis: () => true,
      click: () => { AN.goDistrict(d); if (AN.ui.tab !== 'overview') AN.setTab('overview'); } }); });
    tall.forEach((b, d) => { if (b < 0) return; const x = B.bX[b] * 2, z = B.bZ[b] * 2;
      addLabel({ pos: [x, Hgt(x, z) + bHeight[b] / 10 + 12, z], text: () => f(ot('lm_tall'), DIST[d]) + ' · ' + f(ot('lm_tall_s'), N0(bHeight[b] / 10)), color: '#d946ef', prio: 55, far: 18000, vis: () => true,
        cls: () => (AN.build(S.scen).eff[b] > S.year ? 'dim' : '') + (sel && sel.type === 'b' && sel.id === b ? ' sel' : ''), click: () => { fly(x, z, Math.max(600, bHeight[b] / 10 * 6)); select('b', b, { landmark: d }); } }); });
  }

  // ---------------------------------------------------------------- the passport
  const pass = $('#pass'); let sel = null, pcharts = [];
  function select(type, id, opt) { sel = Object.assign({ type, id }, opt || {}); U.uSel.value = type === 'b' ? id : -1; renderPass(); }
  function closePass() { if (!sel) return; sel = null; U.uSel.value = -1; renderPass(); }
  function head(eyebrow, title, statusText, statusCls) {
    const b = block(pass, null), top = el('div', 'phead'), x = el('button', 'ghost x', '✕'); x.title = ot('close'); x.onclick = closePass;
    top.append(el('div', 'eyebrow', ot('pass') + ' · ' + eyebrow), x); b.append(top, el('div', 'ptitle', title)); if (statusText) b.append(el('div', 'pstatus ' + (statusCls || ''), statusText)); return b;
  }
  const utm = (x, z) => 'E ' + N0(663000 + x) + ' · N ' + N0(4830000 + z);
  function passFacility(i) {
    const fa = W.fac[i], s = S.scen, y = S.year, yi = YI(y), stg = fa.stages[s], done = stg.filter(v => v <= y).length, st = facState(i), unit = unitOf(fa.res);
    const cap = fa.cap ? fa.cap[s][yi] : null, dem = fa.demand ? fa.demand[s][yi] : null, kindName = ot('kind')[fa.kind] || fa.kind;
    const b = head(kindName, fa.name, st === 'plan' ? f(ot('f_st_planned'), stg[0]) : ot('f_st_on') + (cap !== null && dem !== null ? ' · ' + ot('f_st_' + st) : ''), st === 'plan' ? 'dim' : st);
    kpis(b, [[cap !== null ? (cap >= 100 ? N0(cap) : N1(cap)) : fa.unit ? N0(fa.unit) : '—', f(ot('f_cap'), unit)], [dem !== null ? (dem >= 100 ? N0(dem) : N1(dem)) : '—', f(ot('f_load'), unit)],
      [cap > 0 && dem !== null ? rint(100 * dem / cap) + ' %' : '—', ot('f_util'), st === 'plan' ? '' : st], [f(ot('f_stage_v'), done, stg.length), ot('f_stage')]]);
    if (fa.cap && fa.demand) { const cb = block(pass, 'pf_chart', ot('f_chart'), unit), cv = el('canvas', 'chart'); cb.append(cv); pcharts.push([cv, { series: [fa.demand[s], fa.cap[s]], colors: [WHITE, GREY], widths: [2.5, 1.5], stepLast: true, mark: y }]);
      legend(cb, [[WHITE, ot('f_load_l')], [GREY, ot('f_cap_l')]]); }
    const sb = block(pass, 'pf_stages', ot('f_stages'));
    stg.forEach((yr, k) => { const r = fact(sb, f(ot('f_stage_n'), k + 1), yr + ' · ' + (yr <= y ? ot('f_in') : ot('f_plan')) + (fa.delayed.includes(k + 1) ? ' · ' + ot('f_late') : '')); if (fa.delayed.includes(k + 1)) r.lastChild.className = 's warn'; else if (yr <= y) r.lastChild.className = 's ok'; });
    const fb = block(pass, 'pf_facts', ot('pass'));
    fact(fb, ot('dist'), DIST[fa.district] || ot('outside')); fact(fb, ot('src'), fa.synthetic ? ot('src_model') : ot('src_plan')); if (fa.note && fa.note !== 'модель') fact(fb, ot('note'), fa.note); fact(fb, ot('utm'), utm(fa.x, fa.z));
    fb.append(el('div', 'note gap', ot('f_note')));
  }
  function passBuilding(b) {
    const s = S.scen, y = S.year, st = AN.build(s), eff = st.eff[b], planY = 2000 + bYear[b], ex = B.existing(b), kind = B.kindOf(b), gfa = B.bGfa[b], hgt = bHeight[b] / 10;
    const dur = B.duration(b), delayM = B.bDelay[b], start = eff - dur, factY = eff + Math.ceil(delayM / 12), x = B.bX[b] * 2, z = B.bZ[b] * 2;
    const status = ex ? 'st_existing' : eff > MAXY ? 'st_after' : y >= factY ? 'st_built' : y >= start ? (delayM > 0 && y >= eff - 1 ? 'st_behind' : 'st_building') : 'st_planned';
    const cls = status === 'st_behind' ? 'bad' : status === 'st_building' ? 'warn' : status === 'st_built' || status === 'st_existing' ? 'ok' : 'dim';
    const hb = head(f(ot('b_title'), b), H.tx('kind')[kind] || kind, ot(status), cls);
    kpis(hb, [[N1(hgt), ot('b_h')], [String(bFloors[b]), ot('b_fl')], [N0(gfa), ot('b_gfa')], [ex ? '≤ 2025' : eff > MAXY ? '—' : String(eff), ot('b_year')]]);
    if (sel.landmark === 0) hb.append(el('div', 'note gap', ot('lm_gate')));
    const fb = block(pass, 'pb_facts', ot('pass'));
    fact(fb, ot('dist'), DIST[B.bDist[b]] || ot('outside')); fact(fb, ot('b_type'), H.tx('kind')[kind] || kind); fact(fb, ot('src'), ot(['src_gen', 'src_plan', 'src_osm'][B.bSrc[b]] || 'src_gen'));
    if (!ex && eff <= MAXY && eff !== planY) fact(fb, ot('b_year'), f(ot('b_year_s'), eff, planY));
    const c = B.CAT[B.bUse[b]]; if (B.housing(b)) fact(fb, ot('b_res'), N0(gfa / 30)); else if (c >= 1) fact(fb, ot('b_jobs'), N0(gfa / B.M2JOB[c]));
    fact(fb, ot('utm'), utm(x, z));
    if (!ex && eff <= MAXY) {
      const wb = block(pass, 'pb_works', ot('b_works')), cn = B.bCon[b];
      fact(wb, ot('b_contr'), cn < W.contractors.length ? W.contractors[cn] : '—'); fact(wb, ot('b_time'), f(ot('b_time_v'), start, eff));
      const r = fact(wb, ot('b_fore'), factY + (delayM > 0 ? ' · ' + f(ot('b_delay'), delayM) : '')); if (delayM > 0) r.lastChild.className = 's bad';
      if (y >= start && y < factY) { const prog = clamp((y + 1 - start) / (dur + delayM / 12), 0.06, 0.97); fact(wb, f(ot('b_ready'), y), rint(prog * 100) + ' %'); const m = el('div', 'bar'), i = el('i'); i.style.width = rint(prog * 100) + '%'; i.style.background = delayM > 0 ? BAD : WARN; m.append(i); wb.append(m); }
    }
    const rb = block(pass, 'pb_risk', ot('b_risk')), p = B.quakeP(b), f1 = B.bFlood[0][b], f2 = B.bFlood[1][b];
    let r = fact(rb, ot('b_flood1'), f1 > 0 ? f(ot('b_cm'), f1) : ot('b_dry')); r.lastChild.className = 's ' + (f1 > 100 ? 'bad' : f1 > 0 ? 'warn' : 'ok');
    r = fact(rb, ot('b_flood2'), f2 > 0 ? f(ot('b_cm'), f2) : ot('b_dry')); r.lastChild.className = 's ' + (f2 > 100 ? 'bad' : f2 > 0 ? 'warn' : 'ok');
    r = fact(rb, ot('b_quake'), ot('b_q')[p >= 0.2 ? 2 : p >= 0.06 ? 1 : 0] + ' · ' + f(ot('b_qp'), rint(p * 100))); r.lastChild.className = 's ' + (p >= 0.2 ? 'bad' : p >= 0.06 ? 'warn' : 'ok');
    rb.append(el('div', 'note gap', ot('b_note')));
  }
  function passStation(i) {
    const st = W.lrt.stations[i], p = st[2], s = S.scen, yr = W.lrt.year[s][p], on = yr <= S.year;
    const b = head(ot('l_lab'), ot('l_title'), on ? ot('l_on') : ot('l_off') + ' · ' + yr, on ? 'ok' : 'dim');
    fact(b, ot('l_phase'), f(ot('l_phase_v'), p + 1, W.lrt.names[p])); fact(b, ot('l_open'), String(yr)); fact(b, ot('l_km'), N1(W.lrt.km[p]) + ' ' + H.tx('km')); fact(b, ot('utm'), utm(st[0], st[1]));
    const sb = block(pass, 'pl_sc', ot('l_sc')); for (let k = 0; k < 4; k++) fact(sb, H.scenName(k), String(W.lrt.year[k][p]));
  }
  function renderPass() {
    pass.replaceChildren(); pcharts = []; pass.hidden = !sel; stamp++; if (!sel) return;
    if (sel.type === 'f') passFacility(sel.id); else if (sel.type === 'b') passBuilding(sel.id); else passStation(sel.id);
    for (const [cv, o] of pcharts) H.drawChart(cv, o);
  }
  AN.onChange(renderPass); addEventListener('resize', () => { for (const [cv, o] of pcharts) H.drawChart(cv, o); });

  // ---------------------------------------------------------------- picking a building in the view
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function pick(cx, cy) {
    const r = canvas.getBoundingClientRect(); ndc.set((cx - r.left) / r.width * 2 - 1, -((cy - r.top) / r.height) * 2 + 1); ray.setFromCamera(ndc, camera);
    const st = AN.build(S.scen), hits = ray.intersectObjects(bMeshes.filter(m => ray.ray.intersectsBox(m.geometry.boundingBox)), false);
    for (const h of hits) { if (!h.face) continue; const bid = Math.round(h.object.geometry.attributes.aInfo.getY(h.face.a)); if (bid < 0 || bid >= NB) continue; if (!B.existing(bid) && st.eff[bid] > S.year) continue; return bid; }
    return -1;
  }
  function click(cx, cy) { const b = pick(cx, cy); if (b >= 0) select('b', b); else closePass(); return b; }

  const btn = $('#labb'), setLabels = v => { lab.on = v; btn.classList.toggle('main', v); }; btn.onclick = () => setLabels(!lab.on);
  AN.onChange(() => { btn.textContent = ot('labels'); }); btn.textContent = ot('labels'); setLabels(true);
  return { addLabel, frame, click, pick, select, closePass, fly, ot, rivers, lab, setLabels, sel: () => sel, touch: () => { stamp++; }, labels };
}
