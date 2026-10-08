'use strict';
// The bridge site: a construction stage shown the way site-monitoring tools show it. Annotations on the ground (work zone, live networks and
// street, proposed trial pit), a problem at a pier, and a dashboard with the description of the problem and an engineering proposal.
// The bridge, the street, the networks along it and the river come from the twin's model. The structure on the site, the problem, the
// readings and the proposal are a TRAINING SCENARIO: simulated, scripted, labelled as such on the page.
const GLSL_SITE = `
{
  vec3 nS = normalize(cross(dFdx(vWp), dFdy(vWp))); if (dot(nS, uCamU - vWp) < 0.0) nS = -nS;
  filmEmit = diffuseColor.rgb * AmbTri(nS) * 0.9;
}
`;
async function AlatauSite(api, OBJ) {
  const { DATA, S, goTo, Hgt, scene, film, getLang, AN, setYear, setNoTrees } = api;
  const W = DATA.twin, SD = W.site, H = AN.h, { el, block, kpis, fact, chart, f, N0, N1, K, scenName, DIST, OK, WARN, BAD, WHITE, GREY } = H, ot = OBJ.ot;
  const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
  // ---------------------------------------------------------------- the frame of the bridge: t along the axis (south to north), s across (to the east)
  const cs = SD.corners, d01 = Math.hypot(cs[1][0] - cs[0][0], cs[1][1] - cs[0][1]), d12 = Math.hypot(cs[2][0] - cs[1][0], cs[2][1] - cs[1][1]);
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  let E0 = d01 < d12 ? mid(cs[0], cs[1]) : mid(cs[1], cs[2]), E1 = d01 < d12 ? mid(cs[2], cs[3]) : mid(cs[3], cs[0]); if (E0[1] > E1[1]) [E0, E1] = [E1, E0];
  const L = Math.hypot(E1[0] - E0[0], E1[1] - E0[1]), Wd = Math.min(d01, d12), C = mid(E0, E1), u = [(E1[0] - E0[0]) / L, (E1[1] - E0[1]) / L], p = [u[1], -u[0]], hL = L / 2;
  const PL = (t, s) => [C[0] + u[0] * t + p[0] * s, C[1] + u[1] * t + p[1] * s], gy = (t, s) => { const q = PL(t, s); return Hgt(q[0], q[1]); };
  // the river near the bridge (triangles of the model's river layer)
  const rt = []; { const xz = OBJ.rivers.xz, tr = OBJ.rivers.tri; for (let i = 0; i < tr.length; i += 3) { const a = tr[i] * 2, b = tr[i + 1] * 2, c = tr[i + 2] * 2;
    if (Math.hypot((xz[a] + xz[b] + xz[c]) / 3 - C[0], (xz[a + 1] + xz[b + 1] + xz[c + 1]) / 3 - C[1]) < 450) rt.push([xz[a], xz[a + 1], xz[b], xz[b + 1], xz[c], xz[c + 1]]); } }
  const inRiver = (x, z) => { for (const q of rt) { const d1 = (x - q[2]) * (q[1] - q[3]) - (q[0] - q[2]) * (z - q[3]), d2 = (x - q[4]) * (q[3] - q[5]) - (q[2] - q[4]) * (z - q[5]), d3 = (x - q[0]) * (q[5] - q[1]) - (q[4] - q[0]) * (z - q[1]);
    if (!((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0))) return true; } return false; };
  let tw0 = 1e9, tw1 = -1e9; for (let t = -hL; t <= hL; t += 1) { const q = PL(t, 0); if (inRiver(q[0], q[1])) { tw0 = Math.min(tw0, t); tw1 = Math.max(tw1, t); } }
  const riverW = tw1 > tw0 ? tw1 - tw0 + 1 : 0;
  // no trees on the site (work zone and the approaches) or in the river beside it
  setNoTrees((x, z) => { const dx = x - C[0], dz = z - C[1]; if (Math.abs(dx) > 420 || Math.abs(dz) > 420) return false; const t = dx * u[0] + dz * u[1], s = dx * p[0] + dz * p[1];
    return (t > -132 && t < 160 && s > -82 && s < 50) || inRiver(x, z); });
  const siteYear = s => SD.years[s] - 1, openYear = s => SD.years[s];           // the problem is set in the year before the street opens
  const net = res => SD.nets.find(n => n.res === res), DNW = net('water') ? net('water').size : 1400, DNG = net('gas') ? net('gas').size : 1200;
  const st = { active: false, decided: false, asked: false, ann: null };

  // ---------------------------------------------------------------- building the site out of boxes
  const siteMat = film(new THREE.MeshPhongMaterial({ vertexColors: true, flatShading: true, side: THREE.DoubleSide, shininess: 0, specular: 0x000000 }),
    { vsDecl: 'varying vec3 vWp;', vsMain: 'vWp = vec3(position.x, position.y, -position.z);', fsDecl: 'varying vec3 vWp;', color: GLSL_SITE });
  function builder() {
    const P = [], Cc = [];
    const tri = (a, b, c, col) => { for (const q of [a, b, c]) { P.push(q[0], q[1], -q[2]); Cc.push(col[0] * 255, col[1] * 255, col[2] * 255); } };
    const quad = (a, b, c, d, col) => { tri(a, b, c, col); tri(a, c, d, col); };
    const obox = (o, ax, ay, az, col) => { const v = (i, j, k) => [o[0] + ax[0] * i + ay[0] * j + az[0] * k, o[1] + ax[1] * i + ay[1] * j + az[1] * k, o[2] + ax[2] * i + ay[2] * j + az[2] * k];
      quad(v(0, 0, 0), v(1, 0, 0), v(1, 1, 0), v(0, 1, 0), col); quad(v(0, 0, 1), v(1, 0, 1), v(1, 1, 1), v(0, 1, 1), col); quad(v(0, 0, 0), v(1, 0, 0), v(1, 0, 1), v(0, 0, 1), col);
      quad(v(0, 1, 0), v(1, 1, 0), v(1, 1, 1), v(0, 1, 1), col); quad(v(0, 0, 0), v(0, 1, 0), v(0, 1, 1), v(0, 0, 1), col); quad(v(1, 0, 0), v(1, 1, 0), v(1, 1, 1), v(1, 0, 1), col); };
    /** A box in the frame of the bridge: centre (t, s), bottom y0, size along / across / up, turned by rot degrees. */
    const lbox = (t, s, y0, lt, ls, h, col, rot) => { const r = (rot || 0) * Math.PI / 180, c = Math.cos(r), sn = Math.sin(r), a = [u[0] * c + p[0] * sn, u[1] * c + p[1] * sn], b = [-u[0] * sn + p[0] * c, -u[1] * sn + p[1] * c], q = PL(t, s);
      obox([q[0] - a[0] * lt / 2 - b[0] * ls / 2, y0, q[1] - a[1] * lt / 2 - b[1] * ls / 2], [a[0] * lt, 0, a[1] * lt], [0, h, 0], [b[0] * ls, 0, b[1] * ls], col); };
    const cyl = (t, s, y0, r, h, col, n) => { const q = PL(t, s); n = n || 10; for (let i = 0; i < n; i++) { const a0 = i / n * 6.2832, a1 = (i + 1) / n * 6.2832, p0 = [q[0] + Math.cos(a0) * r, y0, q[1] + Math.sin(a0) * r], p1 = [q[0] + Math.cos(a1) * r, y0, q[1] + Math.sin(a1) * r];
      quad(p0, p1, [p1[0], y0 + h, p1[2]], [p0[0], y0 + h, p0[2]], col); tri([q[0], y0 + h, q[1]], [p0[0], y0 + h, p0[2]], [p1[0], y0 + h, p1[2]], col); } };
    /** A pad lying on the ground (gravel, fill): follows the terrain, lift metres above it. */
    const pad = (t0, t1, s0, s1, lift, col) => { const nt = Math.max(1, Math.round((t1 - t0) / 8)), ns = Math.max(1, Math.round((s1 - s0) / 8)), at = (i, j) => { const t = t0 + (t1 - t0) * i / nt, s = s0 + (s1 - s0) * j / ns, q = PL(t, s); return [q[0], Hgt(q[0], q[1]) + lift, q[1]]; };
      for (let i = 0; i < nt; i++) for (let j = 0; j < ns; j++) quad(at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1), col); };
    const mesh = () => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(P), 3)); g.setAttribute('color', new THREE.BufferAttribute(new Uint8Array(Cc), 3, true)); g.computeBoundingSphere();
      const m = new THREE.Mesh(g, siteMat); m.castShadow = m.receiveShadow = true; return m; };
    return { tri, quad, obox, lbox, cyl, pad, mesh };
  }
  const g0 = gy(0, 0), DK = g0 + 9.8, wt = g0 + 2.9, wb = g0 - 0.6;                 // river bed at the pier, deck level, top and bottom of the sheet piles
  const CON = [0.74, 0.73, 0.70], CON2 = [0.60, 0.60, 0.58], RUST = [0.46, 0.28, 0.19], RUST2 = [0.39, 0.23, 0.16], YEL = [0.93, 0.72, 0.10], DARK = [0.16, 0.16, 0.17], BLUE = [0.18, 0.36, 0.62], WHT = [0.86, 0.86, 0.84],
    ORA = [0.95, 0.47, 0.12], GRAV = [0.64, 0.60, 0.52], EARTH = [0.52, 0.44, 0.34], FORM = [0.80, 0.64, 0.32], PIPE = [0.24, 0.46, 0.78], ROCK = [0.50, 0.49, 0.47], MUD = [0.19, 0.21, 0.21];
  const group = new THREE.Group(), fix = new THREE.Group(); group.visible = false; fix.visible = false; scene.add(group); group.add(fix);
  {
    const b = builder();
    for (const t of [-hL, hL]) {                                                 // abutments with their walls and the approach fill
      const g = gy(t, 0), sg = Math.sign(t), t1 = t + sg * 62, ga = gy(t1, 0), A = PL(t + sg * 1.6, -Wd / 2), Bq = PL(t + sg * 1.6, Wd / 2), Cq = PL(t1, Wd / 2), Dq = PL(t1, -Wd / 2);
      b.lbox(t, 0, g - 1, 3.2, Wd, DK - 2.0 - g + 1, CON); b.lbox(t + sg * 1.0, 0, DK - 2.0, 1.2, Wd, 2.0, CON);
      for (const s of [-Wd / 2 + 0.4, Wd / 2 - 0.4]) b.lbox(t + sg * 7, s, g - 1, 12, 0.8, DK - g + 1, CON2);
      b.quad([A[0], DK - 0.4, A[1]], [Bq[0], DK - 0.4, Bq[1]], [Cq[0], ga + 0.2, Cq[1]], [Dq[0], ga + 0.2, Dq[1]], EARTH);
      b.quad([A[0], DK - 0.4, A[1]], [Dq[0], ga + 0.2, Dq[1]], [Dq[0], ga - 1, Dq[1]], [A[0], g - 1, A[1]], EARTH); b.quad([Bq[0], DK - 0.4, Bq[1]], [Cq[0], ga + 0.2, Cq[1]], [Cq[0], ga - 1, Cq[1]], [Bq[0], g - 1, Bq[1]], EARTH);
    }
    const pier = (t, frac, form) => { const g = gy(t, 0), top = DK - 3.4, hc = (top - g - 1.3) * frac; b.lbox(t, 0, g - 0.3, 7, 20, 1.6, CON2);
      for (const s of [-6, 6]) { b.cyl(t, s, g + 1.3, 1.25, hc, CON, 12); if (form) b.lbox(t, s, g + 1.3 + hc, 3.4, 3.4, 2.6, FORM); } if (frac >= 1) b.lbox(t, 0, top, 2.8, 21, 1.4, CON); };
    pier(-hL / 2, 1, false); pier(hL / 2, 0.6, true);
    for (let k = 0; k < 6; k++) b.lbox(-hL * 0.75 + 0.4, -9 + k * 3.6, DK - 2.0, hL / 2 - 0.6, 1.0, 1.75, CON2);       // span 1: beams and the slab
    b.lbox(-hL * 0.75 + 0.4, 0, DK - 0.25, hL / 2 - 0.6, Wd, 0.25, CON);
    // pier 3 in the river: sheet-pile cofferdam, waling, struts, the pit with the heads of the bored piles, pumps
    b.lbox(-6, 0, wb, 0.5, 22.5, wt - wb, RUST); b.lbox(6, 0, wb, 0.5, 22.5, wt - wb, RUST); b.lbox(0, -11, wb, 12, 0.5, wt - wb, RUST); b.lbox(0, 11, wb, 12, 0.5, wt - wb, RUST);
    for (let k = -10; k <= 10; k++) { b.lbox(-6.3, k, wb, 0.25, 0.5, wt - wb, RUST2); b.lbox(6.3, k, wb, 0.25, 0.5, wt - wb, RUST2); }
    for (let k = -5; k <= 5; k++) { b.lbox(k, -11.3, wb, 0.5, 0.25, wt - wb, RUST2); b.lbox(k, 11.3, wb, 0.5, 0.25, wt - wb, RUST2); }
    b.lbox(-5.5, 0, wt - 0.9, 0.4, 21, 0.4, YEL); b.lbox(5.5, 0, wt - 0.9, 0.4, 21, 0.4, YEL); b.lbox(0, -10.5, wt - 0.9, 11, 0.4, 0.4, YEL); b.lbox(0, 10.5, wt - 0.9, 11, 0.4, 0.4, YEL);
    for (const s of [-6, 0, 6]) b.lbox(0, s, wt - 0.88, 11, 0.45, 0.45, YEL);
    b.lbox(0, 0, g0 + 0.4, 11.4, 21.4, 0.2, MUD); for (const tt of [-3, 3]) for (const s of [-7.5, -2.5, 2.5, 7.5]) b.cyl(tt, s, g0 + 0.6, 0.6, 0.9, CON, 10);
    b.lbox(-6, -9, wt, 1.6, 1.2, 1.0, YEL); b.lbox(-6, 9, wt, 1.6, 1.2, 1.0, YEL);
    // south bank: working platform, crawler crane, excavator
    b.pad(-47, -21, -25, 25, 0.5, GRAV);
    const yp = gy(-30, -15) + 0.5, ct = -30, c0 = -15;
    for (const ds of [-2.1, 2.1]) b.lbox(ct, c0 + ds, yp, 7.5, 1.1, 1.1, DARK);
    b.lbox(ct, c0, yp + 1.1, 5.2, 3.6, 2.2, YEL); b.lbox(ct - 3.5, c0, yp + 1.2, 1.8, 3.4, 1.8, DARK); b.lbox(ct + 1.6, c0 - 1.3, yp + 3.3, 1.8, 1.1, 1.5, WHT);
    const ang = 58 * Math.PI / 180, bl = 36, q = PL(ct + 2.2, c0), d = [u[0] * Math.cos(ang), Math.sin(ang), u[1] * Math.cos(ang)], n = [-u[0] * Math.sin(ang), Math.cos(ang), -u[1] * Math.sin(ang)];
    b.obox([q[0] - p[0] * 0.45, yp + 3.2, q[1] - p[1] * 0.45], [p[0] * 0.9, 0, p[1] * 0.9], [n[0] * 0.9, n[1] * 0.9, n[2] * 0.9], [d[0] * bl, d[1] * bl, d[2] * bl], YEL);
    const tip = [q[0] + d[0] * bl, yp + 3.2 + d[1] * bl, q[1] + d[2] * bl];
    b.obox([tip[0] - 0.06, tip[1] - 15, tip[2] - 0.06], [0.12, 0, 0], [0, 15, 0], [0, 0, 0.12], DARK); b.obox([tip[0] - 0.5, tip[1] - 16, tip[2] - 0.5], [1, 0, 0], [0, 1, 0], [0, 0, 1], YEL);
    const ye = gy(-24, 14) + 0.5; b.lbox(-24, 14, ye, 3.8, 2.8, 0.8, DARK, 25); b.lbox(-24, 14, ye + 0.8, 3.0, 2.4, 1.6, YEL, 25); b.lbox(-21.5, 15.2, ye + 1.6, 4.6, 0.5, 0.5, YEL, 25);
    // the compound: containers, sheet piles, pipes for the struts, reinforcement
    b.pad(-122, -62, -74, -30, 0.3, GRAV);
    const cont = (t, s, col, up) => b.lbox(t, s, gy(t, s) + 0.3 + (up || 0), 6.06, 2.44, 2.6, col);
    cont(-114, -68, BLUE); cont(-114, -65, BLUE); cont(-114, -60, WHT); cont(-106, -68, WHT); cont(-106, -68, BLUE, 2.6); cont(-106, -62, WHT); cont(-97, -68, ORA);
    b.lbox(-82, -66, gy(-82, -66) + 0.3, 12, 2.4, 0.9, RUST); b.lbox(-82, -62.5, gy(-82, -62.5) + 0.3, 12, 2.4, 0.6, RUST2);
    for (let k = 0; k < 5; k++) b.lbox(-82, -54 + k * 0.75, gy(-82, -52) + 0.3, 11, 0.55, 0.55, PIPE);
    for (let k = 0; k < 3; k++) b.lbox(-72, -44 + k * 1.3, gy(-72, -43) + 0.3, 12, 0.7, 0.35, DARK);
    b.lbox(-96, -40, gy(-96, -40) + 0.3, 7.5, 2.5, 1.3, WHT, 80); b.lbox(-96.5, -40, gy(-96, -40) + 1.6, 3.6, 2.3, 1.9, ORA, 80);        // a concrete mixer waiting at the gate
    // north bank: platform by pier 4, formwork panels, a concrete pump
    b.pad(33, 63, -22, 22, 0.5, GRAV); b.lbox(56, 14, gy(56, 14) + 0.5, 6, 2.4, 1.2, FORM); b.lbox(56, 10.5, gy(56, 10.5) + 0.5, 6, 2.4, 0.8, FORM);
    b.lbox(55, -11, gy(55, -11) + 0.5, 8, 2.5, 1.2, WHT, 10); b.lbox(52.5, -11, gy(55, -11) + 1.7, 2.4, 2.3, 1.6, ORA, 10);
    // the fence of the work zone (not across the water)
    const ZT0 = -128, ZT1 = 104, ZS0 = -78, ZS1 = 46, per = [];
    for (let t = ZT0; t < ZT1; t += 5) per.push([t, ZS0]); for (let s = ZS0; s < ZS1; s += 5) per.push([ZT1, s]); for (let t = ZT1; t > ZT0; t -= 5) per.push([t, ZS1]); for (let s = ZS1; s > ZS0; s -= 5) per.push([ZT0, s]);
    const post = per.map(([t, s]) => { const w = PL(t, s); return inRiver(w[0], w[1]) ? null : [w[0], Hgt(w[0], w[1]), w[1]]; });
    post.forEach((a, i) => { if (!a) return; b.obox([a[0] - 0.06, a[1], a[2] - 0.06], [0.12, 0, 0], [0, 1.9, 0], [0, 0, 0.12], ORA); const c = post[(i + 1) % post.length]; if (!c) return;
      for (const hh of [0.8, 1.6]) b.obox([a[0], a[1] + hh, a[2]], [c[0] - a[0], c[1] - a[1], c[2] - a[2]], [0, 0.09, 0], [0.04, 0, 0.04], hh > 1 ? ORA : WHT); });
    group.add(b.mesh());
    // what option B adds: rock fill at the upstream wall, a second frame with pipe struts, the concrete plug
    const x = builder(); let seed = 77; const rnd = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
    for (let i = 0; i < 150; i++) { const s = -11.7 - rnd() * 6.5, t = -10 + rnd() * 20, k = 1 - (-11.7 - s) / 6.5, sz = 0.6 + rnd() * 0.8, v = 0.9 + 0.2 * rnd();
      x.lbox(t, s, g0 + 0.2 + rnd() * 1.5 * k, sz, sz * (0.7 + 0.5 * rnd()), sz * 0.7, [ROCK[0] * v, ROCK[1] * v, ROCK[2] * v], rnd() * 90); }
    x.lbox(-5.4, 0, wt - 2.0, 0.4, 21, 0.4, PIPE); x.lbox(5.4, 0, wt - 2.0, 0.4, 21, 0.4, PIPE); for (const s of [-8.5, -3, 3, 8.5]) x.lbox(0, s, wt - 2.0, 11, 0.53, 0.53, PIPE);
    x.lbox(0, 0, g0 + 0.6, 11.4, 21.4, 0.12, CON2); fix.add(x.mesh());
  }

  // ---------------------------------------------------------------- annotations on the ground: zones, lines, points
  const zones = new THREE.Group(); group.add(zones);
  const zmat = (color, a) => new THREE.MeshBasicMaterial({ color, transparent: true, opacity: a, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -12 });
  const lay = (t, s, lift) => { const q = PL(t, s); return [q[0], Hgt(q[0], q[1]) + (lift || 0.7), -q[1]]; };
  function zmesh(P, color, a, order) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(P), 3)); const m = new THREE.Mesh(g, zmat(color, a)); m.renderOrder = order || 5; zones.add(m); return m; }
  function zrect(t0, t1, s0, s1, color, a) { const P = [], nt = Math.max(1, Math.round((t1 - t0) / 6)), ns = Math.max(1, Math.round((s1 - s0) / 6)), at = (i, j) => lay(t0 + (t1 - t0) * i / nt, s0 + (s1 - s0) * j / ns);
    for (let i = 0; i < nt; i++) for (let j = 0; j < ns; j++) P.push(...at(i, j), ...at(i + 1, j), ...at(i + 1, j + 1), ...at(i, j), ...at(i + 1, j + 1), ...at(i, j + 1)); return zmesh(P, color, a, 4); }
  function zline(pts, width, color, a, dash) { const P = []; let run = 0;                         // pts in the frame of the bridge
    for (let k = 1; k < pts.length; k++) { const a0 = pts[k - 1], a1 = pts[k], l = Math.hypot(a1[0] - a0[0], a1[1] - a0[1]), n = Math.max(1, Math.round(l / 4)), nx = -(a1[1] - a0[1]) / l * width / 2, ny = (a1[0] - a0[0]) / l * width / 2;
      for (let i = 0; i < n; i++, run++) { if (dash && run % 2) continue; const f0 = i / n, f1 = (i + 1) / n, t0 = a0[0] + (a1[0] - a0[0]) * f0, s0 = a0[1] + (a1[1] - a0[1]) * f0, t1 = a0[0] + (a1[0] - a0[0]) * f1, s1 = a0[1] + (a1[1] - a0[1]) * f1;
        P.push(...lay(t0 - nx, s0 - ny, 0.8), ...lay(t0 + nx, s0 + ny, 0.8), ...lay(t1 + nx, s1 + ny, 0.8), ...lay(t0 - nx, s0 - ny, 0.8), ...lay(t1 + nx, s1 + ny, 0.8), ...lay(t1 - nx, s1 - ny, 0.8)); } }
    return zmesh(P, color, a, 6); }
  function zdisc(t, s, r, color, a) { const P = []; for (let i = 0; i < 24; i++) { const a0 = i / 24 * 6.2832, a1 = (i + 1) / 24 * 6.2832; P.push(...lay(t, s, 0.9), ...lay(t + Math.cos(a0) * r, s + Math.sin(a0) * r, 0.9), ...lay(t + Math.cos(a1) * r, s + Math.sin(a1) * r, 0.9)); } return zmesh(P, color, a, 7); }
  const loop = (t0, t1, s0, s1) => [[t0, s0], [t1, s0], [t1, s1], [t0, s1], [t0, s0]];
  zrect(-128, 104, -78, 46, 0xff8a1f, 0.07); zline(loop(-128, 104, -78, 46), 1.4, 0xff8a1f, 0.95);                    // work zone
  zrect(-150, 150, 22, 30, 0xffd21f, 0.16); zline([[-150, 26], [150, 26]], 1.6, 0x3b9cff, 0.95);                        // live water main and its protection strip
  zline([[-150, -35], [150, -35]], 1.2, 0xffd21f, 0.95, true);                                                          // gas main
  const excl = zline(loop(-21, 21, -26, 26), 0.9, 0xff3b2f, 0.95, true);                                                // exclusion zone, 15 m from the cofferdam
  const scour = zdisc(5, -13.5, 4.5, 0xff3b2f, 0.55);
  zrect(-31.5, -28.5, 22.5, 25.5, 0x3b9cff, 0.8); zdisc(-24, -17, 1.6, 0x3b9cff, 0.9); zdisc(24, -9, 1.6, 0x3b9cff, 0.9);     // trial pit, control boreholes
  // the live street: the open road that meets an end of the bridge
  let live = null;
  for (const r of SD.roads) { const g = r.g, n = g.length / 2, a = [g[0], g[1]], b = [g[2 * n - 2], g[2 * n - 1]], da = Math.min(Math.hypot(a[0] - E1[0], a[1] - E1[1]), Math.hypot(a[0] - E0[0], a[1] - E0[1])), db = Math.min(Math.hypot(b[0] - E1[0], b[1] - E1[1]), Math.hypot(b[0] - E0[0], b[1] - E0[1]));
    if (Math.min(da, db) > 8 || r.years[0] >= SD.years[0]) continue; const pts = []; for (let i = 0; i < n; i++) pts.push([g[i * 2], g[i * 2 + 1]]); if (db < da) pts.reverse(); if (!live || r.years[0] < live.years[0]) live = { years: r.years, pts }; }
  let liveAt = null;
  if (live) { const loc = live.pts.map(q => [(q[0] - C[0]) * u[0] + (q[1] - C[1]) * u[1], (q[0] - C[0]) * p[0] + (q[1] - C[1]) * p[1]]), cut = [loc[0]]; let len = 0;
    for (let i = 1; i < loc.length && len < 150; i++) { const l = Math.hypot(loc[i][0] - loc[i - 1][0], loc[i][1] - loc[i - 1][1]), k = Math.min(1, (150 - len) / l); cut.push([loc[i - 1][0] + (loc[i][0] - loc[i - 1][0]) * k, loc[i - 1][1] + (loc[i][1] - loc[i - 1][1]) * k]); len += l; }
    zline(cut, 14, 0xff3b2f, 0.28); let left = 45; liveAt = cut[cut.length - 1];                                              // the label stands 45 m along the street
    for (let i = 1; i < cut.length; i++) { const l = Math.hypot(cut[i][0] - cut[i - 1][0], cut[i][1] - cut[i - 1][1]); if (l >= left) { liveAt = [cut[i - 1][0] + (cut[i][0] - cut[i - 1][0]) * left / l, cut[i - 1][1] + (cut[i][1] - cut[i - 1][1]) * left / l]; break; } left -= l; } }

  // ---------------------------------------------------------------- labels: the marker on the city map and the annotations on the site
  const here = () => st.active && S.year === siteYear(S.scen), near = () => here() && S.dist < 2600;
  const A = { issue: [5, -13.5, 7, '!', '#ff3b2f', 96, 150], zone: [-98, -52, 9, '', '#ff8a1f', 70, 330], water: [-52, 26, 5, '!', '#e0a800', 88, 230], gas: [-70, -35, 5, '!', '#e0a800', 60, 260],
    pit: [-30, 24, 5, '?', '#3b9cff', 86, 150], bh1: [-24, -17, 5, '', '#3b9cff', 58, 150], bh2: [24, -9, 5, '', '#3b9cff', 57, 150], crane: [-30, -15, 14, '', '#8a8f98', 50, 190],
    span: [-63, 0, DK - gy(-63, 0) + 4, '✓', '#34c759', 56, 220], pier4: [42, 0, DK - gy(42, 0) + 2, '', '#ff8a1f', 55, 200], excl: [-21, 16, 4, '', '#ff3b2f', 52, 170] };
  if (liveAt) A.road = [liveAt[0], liveAt[1], 6, '', '#ff3b2f', 62, 300];
  const annText = id => f(ot('a')[id], id === 'water' ? DNW : DNG), annDesc = id => f(ot('ad')[id], id === 'water' ? (net('water') ? net('water').years[S.scen] : '') : id === 'gas' ? (net('gas') ? net('gas').years[S.scen] : '') : id === 'road' && live ? live.years[S.scen] : '');
  const annPos = id => { const a = A[id], q = PL(a[0], a[1]); return [q[0], Hgt(q[0], q[1]) + a[2], q[1]]; };
  function focus(id) { st.ann = id; const a = A[id], q = PL(a[0], a[1]); goTo({ target: [q[0], 0, q[1]], dist: a[6], yaw: S.yaw, pitch: clamp(S.pitch, 32, 50) }); OBJ.touch(); AN.refresh(true); }
  for (const id of Object.keys(A)) OBJ.addLabel({ pos: annPos(id), text: () => annText(id), icon: A[id][3], color: A[id][4], prio: 100 + A[id][5], vis: near,
    cls: () => 'site' + (id === 'issue' ? (st.decided ? ' warn' : ' bad pulse') : '') + (st.ann === id ? ' sel' : ''), click: () => focus(id) });
  OBJ.addLabel({ pos: [C[0], DK + 28, C[1]], text: () => ot(st.decided ? 's_marker_ok' : 's_marker'), icon: '!', color: '#ff3b2f', prio: 300, always: true,
    vis: () => S.year === siteYear(S.scen) && !(st.active && S.dist < 2600), cls: () => 'site ' + (st.decided ? 'warn' : 'bad pulse'), click: () => { AN.setOn(true); if (AN.ui.tab === 'site') enter(); else AN.setTab('site'); } });

  // ---------------------------------------------------------------- the tab
  function enter() { st.active = true; if (S.year !== siteYear(S.scen)) { setYear(siteYear(S.scen)); S.yearF = S.year; } sync(); goTo({ target: [C[0], 0, C[1]], dist: 430, yaw: 52, pitch: 34 }); }
  function leave() { st.active = false; st.ann = null; sync(); }
  function sync() { group.visible = here(); fix.visible = st.decided; scour.visible = !st.decided; excl.material.color.setHex(st.decided ? 0xf5a623 : 0xff3b2f); OBJ.touch(); }
  let lastS = S.scen; AN.onChange(() => { if (st.active && S.scen !== lastS) { lastS = S.scen; setTimeout(() => { setYear(siteYear(S.scen)); S.yearF = S.year; }, 0); } lastS = S.scen; sync(); });
  /** A small monitoring chart: ten days of readings, a limit, and the five-day forecast without action and with option B. */
  function mini(parent, title, data, limit, limitText, fc, fcB) {
    parent.append(el('div', 'mtitle', title));
    chart(parent, { draw: cv => { const w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return; const dpr = Math.min(window.devicePixelRatio || 1, 2); cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
      const PLf = 30, PR = 8, PT = 8, PB = 16, pw = w - PLf - PR, ph = h - PT - PB, n = data.length + fc.length, all = data.concat(fc, fcB || [], [limit]), m0 = Math.max(...all), p10 = Math.pow(10, Math.floor(Math.log10(m0))), fr = m0 / p10, max = (fr <= 1 ? 1 : fr <= 2 ? 2 : fr <= 2.5 ? 2.5 : fr <= 5 ? 5 : 10) * p10;
      const X = i => PLf + pw * i / (n - 1), Y = v => PT + ph * (1 - v / max);
      g.font = '10px "Segoe UI", system-ui, sans-serif'; g.fillStyle = GREY; g.strokeStyle = '#2a2a2a'; g.lineWidth = 1; g.textAlign = 'right'; g.textBaseline = 'middle';
      for (let i = 0; i < 3; i++) { const y = Math.round(PT + ph * i / 2) + 0.5, v = max * (2 - i) / 2; g.beginPath(); g.moveTo(PLf, y); g.lineTo(PLf + pw, y); g.stroke(); g.fillText(String(+v.toFixed(2)), PLf - 4, y); }
      g.textAlign = 'center'; g.textBaseline = 'top'; ot('days_f').forEach((d, i) => g.fillText(d, clamp(X([0, 5, 9, 14][i]), PLf + 12, w - 16), h - PB + 3));
      g.fillStyle = 'rgba(255,255,255,.05)'; g.fillRect(X(data.length - 1), PT, X(n - 1) - X(data.length - 1), ph);                       // the forecast part
      g.strokeStyle = BAD; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(PLf, Y(limit)); g.lineTo(PLf + pw, Y(limit)); g.stroke(); g.setLineDash([]);
      const line = (pts, color, width, dash) => { g.strokeStyle = color; g.lineWidth = width; g.lineJoin = 'round'; g.setLineDash(dash ? [3, 3] : []); g.beginPath(); pts.forEach((q, k) => { if (k) g.lineTo(X(q[0]), Y(q[1])); else g.moveTo(X(q[0]), Y(q[1])); }); g.stroke(); g.setLineDash([]); };
      const ahead = arr => [[data.length - 1, data[data.length - 1]]].concat(arr.map((v, i) => [data.length + i, v]));       // a forecast starts at today's reading
      line(ahead(fc), fcB ? BAD : GREY, 1.6, true); if (fcB) line(ahead(fcB), OK, 1.6, true); line(data.map((v, i) => [i, v]), WHITE, 2.2, false);
      g.fillStyle = WHITE; g.beginPath(); g.arc(X(data.length - 1), Y(data[data.length - 1]), 3, 0, 6.2832); g.fill(); } }).classList.add('mini');
    parent.append(el('div', 'note', limitText));
  }
  function render(colL, colR, y, s) {
    const sy = siteYear(s), date = f(ot('date'), sy), dshort = f(ot('date_s'), sy), top = block(colL, null);
    top.append(el('div', 'eyebrow', f(ot('s_eyebrow'), dshort, scenName(s))), el('div', 'ptitle', ot('s_title')), el('div', 'summary', st.decided ? f(ot('s_sum_ok'), date, openYear(s)) : f(ot('s_sum'), date)));
    if (y !== sy) { const back = el('button', 'main', dshort); back.onclick = enter; top.append(back); }
    kpis(top, [['46 %', ot('s_k_ready')], ['38', ot('s_k_people')], [String(openYear(s)), ot('s_k_open')], [st.decided ? '0' : '1', ot('s_k_issue'), st.decided ? 'ok' : 'bad']]);
    const ob = block(colL, 's_obj', ot('s_obj'));
    fact(ob, ot('dist'), 'Golden'); fact(ob, ot('s_len'), f(ot('s_len_v'), N0(L), N0(Wd))); fact(ob, ot('s_spans'), ot('s_spans_v')); if (riverW) fact(ob, ot('s_river'), f(ot('s_river_v'), N0(riverW)));
    fact(ob, ot('s_street'), f(ot('s_street_v'), SD.edge, openYear(s))); fact(ob, ot('s_flood'), ot('s_flood_v'));
    const nb = block(colL, 's_nets', ot('s_nets')); for (const q of SD.nets) fact(nb, ot('s_net')[q.res] || q.res, q.res === 'telecom' ? f(ot('s_net_tel'), q.years[s]) : q.res === 'power' ? f(ot('s_net_kv'), q.size, q.years[s]) : f(ot('s_net_v'), q.size, q.years[s]));
    const ab = block(colL, 's_ann', ot('s_ann'), ot('s_ann_sub'));
    for (const id of Object.keys(A)) { const r = el('div', 'drow click' + (st.ann === id ? ' on' : '')), t1 = el('div', 'row'), dot = el('span', 'dot sq'); dot.style.background = A[id][4]; t1.append(dot, el('span', 'n', annText(id))); r.append(t1); r.onclick = () => focus(id); ab.append(r); }
    const sb = block(colL, 's_stages', ot('s_stages')), pr = [100, 100, 35, 60, 100, 100, 0];
    ot('s_st').forEach((name, i) => { const r = fact(sb, name, pr[i] + ' %'), m = el('div', 'bar'), b = el('i'); b.style.width = pr[i] + '%'; b.style.background = i === 2 ? (st.decided ? WARN : BAD) : pr[i] === 100 ? OK : WARN; m.append(b); r.lastChild.className = 's ' + (i === 2 ? (st.decided ? 'warn' : 'bad') : ''); sb.append(m); });
    // ---- right: the selected annotation, then the problem and the proposal
    if (st.ann) { const cb = block(colR, null), hd = el('div', 'phead'), x = el('button', 'ghost x', '✕'); x.onclick = () => { st.ann = null; OBJ.touch(); AN.refresh(true); }; hd.append(el('div', 'eyebrow', ot('s_ann')), x); cb.append(hd, el('div', 'ptitle sm', annText(st.ann)), el('div', 'ptext', annDesc(st.ann))); }
    const ib = block(colR, null), hd = el('div', 'phead'); hd.append(el('div', 'eyebrow', dshort + ' · 06:40'), el('span', 'jbadge ' + (st.decided ? 'ok' : 'bad'), st.decided ? ot('i_done') : ot('i_crit') + ' · ' + ot('i_open')));
    ib.append(hd, el('div', 'ptitle sm', ot('i_title')), el('div', 'ptext', ot('i_text'))); fact(ib, ot('i_found'), f(ot('i_found_v'), dshort)); fact(ib, ot('i_cause'), ot('i_cause_v'));
    const mb = block(colR, 's_mon', ot('i_mon'));
    mini(mb, ot('i_m1'), [0.35, 0.38, 0.42, 0.40, 0.47, 0.55, 0.71, 0.96, 1.18, 1.27], 1.10, ot('i_m1l'), [1.33, 1.41, 1.46, 1.44, 1.38], null);
    mini(mb, ot('i_m2'), [12, 12, 13, 13, 14, 15, 19, 27, 38, 46], 40, ot('i_m2l'), [55, 66, 78, 90, 104], [44, 36, 22, 12, 8]);
    mini(mb, ot('i_m3'), [8, 8, 9, 9, 10, 12, 17, 26, 35, 41], 30, ot('i_m3l'), [48, 56, 65, 76, 88], [43, 44, 43, 42, 42]);
    H.legend(mb, [[BAD, ot('i_fc')], [OK, ot('i_fc_b')]]);
    const rb = block(colR, 's_risk', ot('i_risk')), golden = AN.residents(AN.build(s), 1, sy);
    ot('i_r').forEach((name, i) => { const r = fact(rb, f(name, DNW), f(ot('i_rv')[i], i === 1 ? K(golden) : openYear(s))); if (i < 3) r.lastChild.className = 's ' + (i === 0 ? 'ok' : st.decided ? 'warn' : 'bad'); });
    const aib = block(colR, 's_ai', ot('i_ai'), f(ot('i_ai_sub'), 78)); aib.classList.add('ai'); aib.append(el('div', 'ptext strong', ot('i_rec')));
    const ol = el('ol', 'steps'); for (const t of ot('i_steps')) ol.append(el('li', '', t)); aib.append(ol); aib.append(el('div', 'mtitle', ot('i_why')), el('div', 'ptext', ot('i_why_v')), el('div', 'note gap', ot('i_srcs') + ': ' + ot('i_srcs_v')));
    const obk = block(colR, 's_opts', ot('i_opts')), oh = ot('i_oh');
    ot('i_o').forEach((o, i) => { const c = el('div', 'opt' + (i === 1 ? ' rec' : '')), t = el('div', 'row'); t.append(el('span', 'n', o[0]), el('span', 's ' + (i === 0 ? 'bad' : 'ok'), o[3])); c.append(t, el('div', 'note', oh[1] + ': ' + o[1] + ' · ' + oh[2] + ': ' + o[2] + ' · ' + oh[3].toLowerCase() + ': ' + o[3]), el('div', 'note', ot('i_o_note')[i])); obk.append(c); });
    const act = el('div', 'acts'), acc = el('button', st.decided ? '' : 'main', st.decided ? ot('i_undo') : ot('i_accept')), ask = el('button', '', st.asked ? ot('i_asked') : ot('i_ask'));
    acc.onclick = () => { st.decided = !st.decided; sync(); AN.refresh(true); }; ask.onclick = () => { st.asked = true; AN.refresh(true); }; ask.disabled = st.asked; act.append(acc, ask); obk.append(act);
    const chat = block(colR, 's_chat', ot('i_chat')), msgs = ot('i_c').concat(st.decided ? [ot('i_c_done')] : []);
    for (const [who, time, text] of msgs) { const m = el('div', 'msg' + (who.includes('qTwin') ? ' ai' : '')), hd2 = el('div', 'jh'); hd2.append(el('span', 'src', who), el('span', '', time)); const body = el('div', 'jt'), full = f(text, DNW), tag = '@' + ot('a').pit;
      if (full.startsWith(tag)) { body.append(el('span', 'mention', tag), document.createTextNode(full.slice(tag.length))); } else body.textContent = full; m.append(hd2, body); chat.append(m); }
    const nb2 = block(colR, null); nb2.append(el('div', 'note', ot('i_disc')));
  }
  AN.addTab('site', { label: () => ot('tab_site'), render, enter, leave });
  return { st, enter, leave, focus, siteYear, C, L, Wd, riverW, group, A };
}
