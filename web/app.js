'use strict';
// Alatau City, film look, in the browser. The same data and the same rules as the Unity project: buildings from the model's
// geometry, roofs / roads / trees rebuilt by the rules of AlatauRoofs, FilmRoads and FilmTrees, facades from the same generator.
// "Map frame" = x east, y up, z north (the Unity scene). three.js is right-handed, so everything is drawn at (x, y, -z).
(async function () {
const $ = s => document.querySelector(s);
const status = t => { $('#load span').textContent = t; };
const tick = () => new Promise(r => setTimeout(r, 0));
const b64 = s => { const b = atob(s), u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; };
const gunzip = async s => new Uint8Array(await new Response(new Blob([b64(s)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
const loadImg = (s, mime) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error('picture')); i.src = 'data:' + mime + ';base64,' + s; });
const M = DATA.meta, clamp = (v, a, b) => Math.min(Math.max(v, a), b), lerp = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

// ---------------------------------------------------------------- texts
const TXT = {
  ru: { title: 'Alatau City · 3D', demo: 'Демо-сценарий · данные смоделированы · не официальные данные', year: 'Год', hour: 'Время суток', play: 'Рост города', stop: 'Стоп',
        views: 'Виды', overview: 'Весь город', help: 'Левая кнопка — сдвиг, правая — поворот, колесо — масштаб. Клавиши W A S D, Q E, R F.',
        credit: 'Модель и сценарий застройки — набор QTwin; генплан — ПП РК № 388 от 17.05.2024; существующая застройка © участники OpenStreetMap (ODbL); текстуры — Poly Haven (CC0). Деревья, дороги, кровли и фасады достроены по правилам, это не проект.',
        loading: 'Загрузка', ground: 'рельеф и карта', buildings: 'здания', roads: 'дороги', analytics: 'аналитика', done: 'готово', nowebgl: 'Нужен браузер с WebGL 2 (Chrome, Edge, Firefox).', quality: 'Качество', hi: 'высокое', lo: 'обычное' },
  en: { title: 'Alatau City · 3D', demo: 'Demo scenario · simulated data · not official data', year: 'Year', hour: 'Time of day', play: 'City growth', stop: 'Stop',
        views: 'Views', overview: 'Whole city', help: 'Left button: pan, right button: rotate, wheel: zoom. Keys W A S D, Q E, R F.',
        credit: 'Model and development scenario: the QTwin set; master plan: Government Resolution No. 388 of 17.05.2024; existing buildings © OpenStreetMap contributors (ODbL); textures: Poly Haven (CC0). Trees, roads, roofs and facades are added by rule; this is not a design.',
        loading: 'Loading', ground: 'terrain and map', buildings: 'buildings', roads: 'roads', analytics: 'analytics', done: 'ready', nowebgl: 'A browser with WebGL 2 is needed (Chrome, Edge, Firefox).', quality: 'Quality', hi: 'high', lo: 'normal' } };
let lang = 'ru';
const T = k => TXT[lang][k] || k;
function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-t]').forEach(e => { e.textContent = T(e.dataset.t); });
  $('#lang').textContent = lang === 'ru' ? 'EN' : 'RU'; $('#play').textContent = S.playing ? T('stop') : T('play');
  $('#q').textContent = T('quality') + ': ' + (S.hi ? T('hi') : T('lo'));
  if (AN) AN.lang();
}

// ---------------------------------------------------------------- state and renderer
const S = { year: 2050, yearF: 2050, playing: false, hour: 17, hi: true, target: [0, 0, 0], dist: 9000, yaw: 0, pitch: 45, ready: false, scen: 0 };
let AN = null, OBJ = null, SITE = null;      // analytics panels, labels and passports, the bridge site: started when the city is built
const bMeshes = [];                          // the building meshes, for picking a building in the view
const canvas = $('#c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
if (!renderer.capabilities.isWebGL2) { status(T('nowebgl')); return; }
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 10, 200000);
const V3 = (x, y, z) => new THREE.Vector3(x, y, z), C3 = () => new THREE.Color();
const U = { uNight: { value: 0 }, uYear: { value: 2050 }, uYearF: { value: 2050 }, uGrow: { value: 0 }, uSunDir: { value: V3(0, 1, 0) }, uSunCol: { value: C3() }, uZen: { value: C3() },
  uHor: { value: C3() }, uGnd: { value: C3() }, uAmbSky: { value: C3() }, uAmbEq: { value: C3() }, uAmbGnd: { value: C3() }, uCamU: { value: V3(0, 0, 0) },
  tMatA: { value: null }, tMatD: { value: null }, uMatMean: { value: [] }, tGeo: { value: null }, tGeo2: { value: null },
  tPlan: { value: null }, tNat: { value: null }, tDev: { value: null }, tBlocks: { value: null }, uSunInt: { value: 1 }, uScen: { value: 0 }, uDevK: { value: 1 }, uTint: { value: 0 }, tTint: { value: null }, uSel: { value: -1 } };

/** A Phong material with our code spliced in: decl = declarations, color = code that sets diffuseColor.rgb, filmEmit and filmSpec. */
let filmId = 0;
function film(mat, o) {
  const key = 'film' + (++filmId); mat.customProgramCacheKey = () => key;
  mat.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\n' + (o.vsDecl || '')).replace('#include <begin_vertex>', '#include <begin_vertex>\n' + (o.vsMain || ''));
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvec3 filmEmit = vec3(0.0); float filmSpec = 0.0;\n' + GLSL_FILM + (o.fsDecl || ''))
      .replace('#include <color_fragment>', '#include <color_fragment>\n' + (o.color || ''))
      .replace('#include <specularmap_fragment>', 'float specularStrength = filmSpec;')
      .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += filmEmit;');
  };
  return mat;
}
/** The matching shadow material: same vertices, the same "not built yet" test. */
function shadowOf(o) {
  const m = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, side: THREE.DoubleSide });
  const key = 'shadow' + (++filmId); m.customProgramCacheKey = () => key;
  m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\n' + o.vsDecl).replace('#include <begin_vertex>', '#include <begin_vertex>\n' + o.vsMain);
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform float uYear, uYearF, uGrow;\n' + o.fsDecl)
      .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\n' + o.clip);
  };
  return m;
}

// ---------------------------------------------------------------- terrain heights
status(T('ground'));
const hRaw = new Uint16Array((await gunzip(DATA.ter)).buffer);
const Hs = (c, r) => M.lo + hRaw[r * M.nx + c] / 65535 * (M.hi - M.lo);
function Hgt(x, z) {
  const c = clamp((x - M.x0) / M.step, 0, M.nx - 1.001), r = clamp((z - M.z0) / M.step, 0, M.ny - 1.001), c0 = c | 0, r0 = r | 0, a = c - c0, b = r - r0;
  return Hs(c0, r0) * (1 - a) * (1 - b) + Hs(c0 + 1, r0) * a * (1 - b) + Hs(c0, r0 + 1) * (1 - a) * b + Hs(c0 + 1, r0 + 1) * a * b;
}

// ---------------------------------------------------------------- pictures: base map and material photos
const [imPlan, imNat, imDev, imBlocks] = await Promise.all([loadImg(DATA.plan, 'image/jpeg'), loadImg(DATA.nat, 'image/jpeg'), loadImg(DATA.dev, 'image/png'), loadImg(DATA.blocks, 'image/png')]);
function tex(im, mip) {
  const t = new THREE.Texture(im); t.generateMipmaps = mip; t.minFilter = mip ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter; t.magFilter = THREE.LinearFilter;
  t.anisotropy = mip ? 8 : 1; t.needsUpdate = true; return t;
}
U.tPlan.value = tex(imPlan, true); U.tNat.value = tex(imNat, true); U.tDev.value = tex(imDev, false); U.tBlocks.value = tex(imBlocks, true);
// a small readable copy of the plan and of the development year, for placing trees
const mapW = 1024, mapH = Math.round(1024 * imPlan.height / imPlan.width);
function pixelsOf(im, w, h) { const cv = document.createElement('canvas'); cv.width = w; cv.height = h; const g = cv.getContext('2d', { willReadFrequently: true }); g.drawImage(im, 0, 0, w, h); return g.getImageData(0, 0, w, h).data; }
const planPx = pixelsOf(imPlan, mapW, mapH), devPx = pixelsOf(imDev, mapW, mapH);
{ // the usual land colour along the border of the map (water left out): the ground beyond the model continues in it
  let r = 0, g = 0, b = 0, n = 0; const take = (x, y) => { const i = (y * mapW + x) * 4, R = planPx[i], G = planPx[i + 1], B = planPx[i + 2]; if (B - R > 30) return; r += R; g += G; b += B; n++; };
  for (let x = 0; x < mapW; x += 2) { take(x, 3); take(x, mapH - 4); } for (let y = 0; y < mapH; y += 2) { take(3, y); take(mapW - 4, y); }
  U.uEdgeCol = { value: n ? V3(r / n / 255, g / n / 255, b / n / 255) : V3(0.6, 0.6, 0.55) }; }
/** Land use from the plan's colour: 0 built-up, 1 park, 2 open land, 3 water; and the year the place is developed. */
function land(x, z) {
  const px = clamp(((M.ua * x + M.ub) * mapW) | 0, 0, mapW - 1), py = clamp(((1 - (M.va * z + M.vb)) * mapH) | 0, 0, mapH - 1), i = (py * mapW + px) * 4;
  const r = planPx[i] / 255, g = planPx[i + 1] / 255, b = planPx[i + 2] / 255, lum = 0.299 * r + 0.587 * g + 0.114 * b, sat = Math.max(r, g, b) - Math.min(r, g, b);
  const year = devPx[i] === 0 ? 0 : 2000 + devPx[i];
  if ((b - r) * 5 - 0.6 > 0.3 && (g - r) * 8 + 0.3 > 0.3) return [3, year];
  if (g - Math.max(r, b) > 0.05) return [1, year];
  if (lum < 0.46 && sat < 0.12) return [2, year];
  return [0, year];
}
{
  const n = DATA.mat.length, size = 512, A = new Uint8Array(size * size * 4 * n), D = new Uint8Array(size * size * 4 * n), mean = [];
  for (let k = 0; k < n; k++) {
    const [ia, id] = await Promise.all([loadImg(DATA.mat[k].a, 'image/jpeg'), loadImg(DATA.mat[k].d, 'image/jpeg')]);
    const pa = pixelsOf(ia, size, size), pd = pixelsOf(id, size, size); let r = 0, g = 0, b = 0;
    for (let y = 0; y < size; y++) {                      // pictures arrive top row first; textures are stored bottom row first
      const src = (size - 1 - y) * size * 4, dst = (k * size + y) * size * 4;
      A.set(pa.subarray(src, src + size * 4), dst); D.set(pd.subarray(src, src + size * 4), dst);
    }
    for (let i = 0; i < pa.length; i += 4) { r += pa[i]; g += pa[i + 1]; b += pa[i + 2]; }
    const px = size * size * 255; mean.push(V3(r / px, g / px, b / px));
  }
  const arr = d => { const t = new THREE.DataTexture2DArray(d, size, size, n); t.format = THREE.RGBAFormat; t.type = THREE.UnsignedByteType; t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; t.generateMipmaps = true; t.anisotropy = 4; t.needsUpdate = true; return t; };
  U.tMatA.value = arr(A); U.tMatD.value = arr(D); while (mean.length < 12) mean.push(V3(0.5, 0.5, 0.5)); U.uMatMean.value = mean;
}

// ---------------------------------------------------------------- the ground
const VS_MAP = { decl: 'varying vec3 vWp; varying vec3 vNu;', main: 'vWp = vec3(position.x, position.y, -position.z); vNu = vec3(normal.x, normal.y, -normal.z);' };
{
  const nx = M.nx, ny = M.ny, nb = 2 * (nx + ny) - 4, pos = new Float32Array((nx * ny + nb) * 3), uv = new Float32Array((nx * ny + nb) * 2), idx = new Uint32Array((nx - 1) * (ny - 1) * 6 + nb * 6);
  for (let r = 0, i = 0; r < ny; r++) for (let c = 0; c < nx; c++, i++) {
    const x = M.x0 + c * M.step, z = M.z0 + r * M.step; pos[i * 3] = x; pos[i * 3 + 1] = Hs(c, r); pos[i * 3 + 2] = -z; uv[i * 2] = M.ua * x + M.ub; uv[i * 2 + 1] = M.va * z + M.vb;
  }
  let k = 0;
  for (let r = 0; r < ny - 1; r++) for (let c = 0; c < nx - 1; c++) { const a = r * nx + c, b = a + 1, d = a + nx, e = d + 1; idx[k++] = a; idx[k++] = b; idx[k++] = d; idx[k++] = b; idx[k++] = e; idx[k++] = d; }
  // a skirt: the edge of the model carried far out at the same height, so the ground reaches the horizon (plain steppe in the shader)
  const ring = []; for (let c = 0; c < nx; c++) ring.push(c); for (let r = 1; r < ny; r++) ring.push(r * nx + nx - 1); for (let c = nx - 2; c >= 0; c--) ring.push((ny - 1) * nx + c); for (let r = ny - 2; r >= 1; r--) ring.push(r * nx);
  const cx = M.x0 + (nx - 1) * M.step / 2, cz = M.z0 + (ny - 1) * M.step / 2, OUT = 30;
  ring.forEach((i, j) => { const o = nx * ny + j, x = cx + (pos[i * 3] - cx) * OUT, z = cz + (-pos[i * 3 + 2] - cz) * OUT; pos[o * 3] = x; pos[o * 3 + 1] = pos[i * 3 + 1]; pos[o * 3 + 2] = -z; uv[o * 2] = M.ua * x + M.ub; uv[o * 2 + 1] = M.va * z + M.vb; });
  for (let j = 0; j < nb; j++) { const a = ring[j], b = ring[(j + 1) % nb], d = nx * ny + j, e = nx * ny + (j + 1) % nb; idx[k++] = a; idx[k++] = d; idx[k++] = b; idx[k++] = b; idx[k++] = d; idx[k++] = e; }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.BufferAttribute(uv, 2)); g.setIndex(new THREE.BufferAttribute(idx, 1)); g.computeVertexNormals();
  const mat = film(new THREE.MeshPhongMaterial({ shininess: 0, specular: 0x000000 }), {
    vsDecl: VS_MAP.decl + ' varying vec2 vUvM;', vsMain: VS_MAP.main + ' vUvM = uv;',
    fsDecl: 'varying vec3 vWp; varying vec3 vNu; varying vec2 vUvM; uniform sampler2D tPlan, tNat, tDev, tBlocks; uniform vec3 uEdgeCol;', color: GLSL_GROUND });
  const mesh = new THREE.Mesh(g, mat); mesh.receiveShadow = true; scene.add(mesh);
}
await tick();

// ---------------------------------------------------------------- buildings
status(T('buildings'));
const tab = await gunzip(DATA.tab), NB = new DataView(tab.buffer).getUint32(0, true);
const bKind = tab.subarray(4, 4 + NB), bFloors = tab.subarray(4 + NB, 4 + 2 * NB), bYear = tab.subarray(4 + 2 * NB, 4 + 3 * NB);
const bHeight = new Uint16Array(tab.buffer.slice(4 + 3 * NB, 4 + 5 * NB)), bGround = new Float32Array(tab.buffer.slice(4 + 5 * NB, 4 + 9 * NB));
const KIND = M.kinds, kindOf = b => KIND[bKind[b]] || 'other';
const STYLE = { house: 1, res_mid: 2, res_high: 2, residential: 2, tower: 3, business: 3, mixed: 3, hotel: 3, public: 4, education: 4, health: 4, culture: 4, other: 4, industry: 5, utility: 5, podium: 6, retail: 6, solar: 7, resort: 8, existing: 9 };
{
  const geo = new Float32Array(256 * 256 * 4), geo2 = new Float32Array(256 * 256 * 4);
  for (let b = 0; b < NB && b < 65536; b++) {
    geo[b * 4] = bGround[b]; geo[b * 4 + 1] = bHeight[b] / 10; geo[b * 4 + 2] = bFloors[b]; geo[b * 4 + 3] = STYLE[kindOf(b)] || 0;
    geo2[b * 4] = ((Math.imul(b, 2654435761 | 0) >>> 24) & 255) / 255; geo2[b * 4 + 1] = 2000 + bYear[b];      // seed, year of completion (changes with the scenario)
  }
  const ft = d => { const t = new THREE.DataTexture(d, 256, 256, THREE.RGBAFormat, THREE.FloatType); t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true; return t; };
  U.tGeo.value = ft(geo); U.tGeo2.value = ft(geo2);
}
const VS_B = { decl: 'attribute vec2 aWall; attribute vec2 aInfo; varying vec2 vWall; varying vec2 vInfo; varying vec3 vWp;', main: 'vWall = aWall; vInfo = aInfo; vWp = vec3(position.x, position.y, -position.z);' };
const bMat = film(new THREE.MeshPhongMaterial({ vertexColors: true, flatShading: true, side: THREE.DoubleSide, specular: 0xffffff, shininess: 180 }), {
  vsDecl: VS_B.decl, vsMain: VS_B.main, fsDecl: 'varying vec2 vWall; varying vec2 vInfo; varying vec3 vWp; uniform highp sampler2D tGeo; uniform highp sampler2D tGeo2; uniform sampler2D tTint; uniform float uSel;\n' + GLSL_FACADE, color: GLSL_BUILDING });
const bShadow = shadowOf({ vsDecl: 'attribute vec2 aInfo; varying vec2 vInfo;', vsMain: 'vInfo = aInfo;', fsDecl: 'varying vec2 vInfo; uniform highp sampler2D tGeo2;',
  clip: '{ float bS = max(floor(vInfo.y + 0.5), 0.0); float yS = texelFetch(tGeo2, ivec2(int(mod(bS, 256.0)), int(bS / 256.0)), 0).g; float yB = (vInfo.y > -0.5 && yS > 0.5) ? yS : vInfo.x;'
    + ' if (yB > (uGrow > 0.5 ? uYearF + 1.0 : uYear + 0.5)) discard; }' });
const hash = (bid, k) => { let h = (Math.imul(bid, 73856093) ^ Math.imul(k, 19349663)) >>> 0; h ^= h >>> 13; h = Math.imul(h, 0x5bd1e995) >>> 0; h ^= h >>> 15; return (h & 0xFFFFFF) / 16777216; };
const rects = new Map();                    // footprints for tree placement: cell -> [cx, cz, ux, uz, hu, hw]
const houses = [];                          // [cx, cz, ux, uz, hu, hw, bid]
const RC = 128, rkey = (x, z) => Math.floor(x / RC) * 100003 + Math.floor(z / RC);
function addRect(cx, cz, ux, uz, hu, hw) {
  const r = [cx, cz, ux, uz, hu, hw], ext = Math.hypot(hu, hw) + 8;
  for (let gz = Math.floor((cz - ext) / RC); gz <= Math.floor((cz + ext) / RC); gz++) for (let gx = Math.floor((cx - ext) / RC); gx <= Math.floor((cx + ext) / RC); gx++) {
    const k = gx * 100003 + gz; let l = rects.get(k); if (!l) rects.set(k, l = []); l.push(r);
  }
}
let noTrees = null;                          // places kept clear of trees (the bridge site), set by site.js
function blocked(x, z, margin) {
  if (noTrees && noTrees(x, z)) return true;
  const l = rects.get(rkey(x, z)); if (!l) return false;
  for (const r of l) { const dx = x - r[0], dz = z - r[1]; if (Math.abs(dx * r[2] + dz * r[3]) < r[4] + margin && Math.abs(-dx * r[3] + dz * r[2]) < r[5] + margin) return true; }
  return false;
}
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]], mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2], cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const len = a => Math.hypot(a[0], a[1], a[2]), norm = a => { const l = len(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; }, UP = [0, 1, 0];
const pal = M.palette.map(c => [Math.round(c[0] * 255), Math.round(c[1] * 255), Math.round(c[2] * 255)]);
let nTris = 0;
{
  const bld = await gunzip(DATA.bld), dv = new DataView(bld.buffer), count = dv.getInt32(4, true), td = new TextDecoder(); let off = 8;
  for (let o = 0; o < count; o++) {
    const nl = dv.getUint16(off, true); off += 2; const name = td.decode(bld.subarray(off, off + nl)); off += nl + 1;
    const nv = dv.getInt32(off, true), nt = dv.getInt32(off + 4, true); off += 8;
    const V = new Float32Array(bld.buffer.slice(off, off + nv * 12)); off += nv * 12; const Tr = new Uint32Array(bld.buffer.slice(off, off + nt * 12)); off += nt * 12;
    const col = bld.subarray(off, off + nt); off += nt; const yr = new Uint16Array(bld.buffer.slice(off, off + nt * 2)); off += nt * 2; const bid = new Int32Array(bld.buffer.slice(off, off + nt * 4)); off += nt * 4;
    if (!nt) continue;
    const P = i => [V[i * 3], V[i * 3 + 1], V[i * 3 + 2]];
    // ---- the model's own triangles, with the wall coordinates the facade needs (metres along the wall, wall length)
    const pos = new Float32Array(nt * 9), wall = new Float32Array(nt * 6), info = new Float32Array(nt * 6), cl = new Uint8Array(nt * 9), runs = new Map(), rk = new Float64Array(nt), nrm = new Float32Array(nt * 3);
    const roofs = new Map(), pitched = new Map();
    for (let t = 0; t < nt; t++) {
      const a = P(Tr[t * 3]), b = P(Tr[t * 3 + 1]), c = P(Tr[t * 3 + 2]); let n = cross(sub(b, a), sub(c, a)); const l = len(n); rk[t] = -1;
      if (l < 1e-9) continue; n = mul(n, 1 / l); nrm[t * 3] = n[0]; nrm[t * 3 + 1] = n[1]; nrm[t * 3 + 2] = n[2];
      if (n[1] >= 0.3) { const set = n[1] >= 0.95 ? roofs : pitched; let li = set.get(bid[t]); if (!li) set.set(bid[t], li = []); li.push(t); }
      if (Math.abs(n[1]) > 0.35) continue;
      const hl = Math.hypot(n[0], n[2]), hx = n[0] / hl, hz = n[2] / hl, ax = -hz, az = hx;
      const key = (bid[t] + 1) * 17179869184 + (Math.round(hx * 120) + 128) * 67108864 + (Math.round(hz * 120) + 128) * 262144 + (Math.round((hx * a[0] + hz * a[2]) * 4) & 0x3FFFF); rk[t] = key;
      const u0 = ax * a[0] + az * a[2], u1 = ax * b[0] + az * b[2], u2 = ax * c[0] + az * c[2], lo = Math.min(u0, u1, u2), hi = Math.max(u0, u1, u2), r = runs.get(key);
      if (r) { r[0] = Math.min(r[0], lo); r[1] = Math.max(r[1], hi); } else runs.set(key, [lo, hi]);
    }
    for (let t = 0; t < nt; t++) {
      const pc = pal[Math.min(col[t], pal.length - 1)];
      for (let j = 0; j < 3; j++) {
        const vi = Tr[t * 3 + j], k = t * 3 + j; pos[k * 3] = V[vi * 3]; pos[k * 3 + 1] = V[vi * 3 + 1]; pos[k * 3 + 2] = -V[vi * 3 + 2];
        info[k * 2] = yr[t]; info[k * 2 + 1] = bid[t]; cl[k * 3] = pc[0]; cl[k * 3 + 1] = pc[1]; cl[k * 3 + 2] = pc[2];
        if (rk[t] >= 0) { const hl = Math.hypot(nrm[t * 3], nrm[t * 3 + 2]), ax = -nrm[t * 3 + 2] / hl, az = nrm[t * 3] / hl, r = runs.get(rk[t]); wall[k * 2] = ax * V[vi * 3] + az * V[vi * 3 + 2] - r[0]; wall[k * 2 + 1] = Math.max(r[1] - r[0], 0.06); }
      }
    }
    // ---- what stands on the roofs and round the buildings (the rules of AlatauRoofs.cs)
    const xp = [], xw = [], xi = [], xc = [], ix = []; let xn = 0, cur = { col: pal[0], year: 0, bid: 0 };
    const vert = (p, part) => { xp.push(p[0], p[1], -p[2]); xw.push(0, -part); xi.push(cur.year, cur.bid); xc.push(cur.col[0], cur.col[1], cur.col[2]); return xn++; };
    const quad = (a, b, c, d, part) => { const i = vert(a, part); vert(b, part); vert(c, part); vert(d, part); ix.push(i, i + 1, i + 2, i, i + 2, i + 3); };
    const tri3 = (a, b, c, part) => { const i = vert(a, part); vert(b, part); vert(c, part); ix.push(i, i + 1, i + 2); };
    const box = (cen, u, w, hu, hw, h, part) => {
      const c0 = add(add(cen, mul(u, -hu)), mul(w, -hw)), c1 = add(add(cen, mul(u, hu)), mul(w, -hw)), c2 = add(add(cen, mul(u, hu)), mul(w, hw)), c3 = add(add(cen, mul(u, -hu)), mul(w, hw)), up = [0, h, 0];
      const i = vert(c0, part); vert(c1, part); vert(c2, part); vert(c3, part); vert(add(c0, up), part); vert(add(c1, up), part); vert(add(c2, up), part); vert(add(c3, up), part);
      ix.push(i, i + 1, i + 5, i, i + 5, i + 4, i + 1, i + 2, i + 6, i + 1, i + 6, i + 5, i + 2, i + 3, i + 7, i + 2, i + 7, i + 6, i + 3, i, i + 4, i + 3, i + 4, i + 7, i + 4, i + 5, i + 6, i + 4, i + 6, i + 7);
    };
    for (const [id, list] of pitched) {                 // generated houses: eaves over the walls, a chimney
      if (kindOf(id) !== 'house') continue; cur = { col: pal[Math.min(col[list[0]], pal.length - 1)], year: yr[list[0]], bid: id };
      const planes = new Map();
      for (const t of list) { const pk = Math.round(nrm[t * 3] * 20) * 1000 + Math.round(nrm[t * 3 + 2] * 20); let pl = planes.get(pk); if (!pl) planes.set(pk, pl = { n: [nrm[t * 3], nrm[t * 3 + 1], nrm[t * 3 + 2]], pts: [] });
        for (let j = 0; j < 3; j++) { const p = P(Tr[t * 3 + j]); if (!pl.pts.some(q => (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2 < 0.0025)) pl.pts.push(p); } }
      let chimney = false; const eaves = [];
      for (const pl of planes.values()) {
        if (pl.pts.length !== 4) continue; const n = pl.n; pl.pts.sort((p, q) => p[1] - q[1]); let [e0, e1, r0, r1] = pl.pts;
        let r = sub(r1, r0); r[1] = 0; if (len(r) < 0.2) continue; r = norm(r); if (dot(sub(e1, e0), r) < 0) [e0, e1] = [e1, e0];
        const down = norm(sub(mul(add(e0, e1), 0.5), mul(add(r0, r1), 0.5))), og = 0.35, oe = 0.55, lift = mul(n, 0.06); eaves.push(e0, e1);
        quad(add(add(r0, mul(r, -og)), lift), add(add(r1, mul(r, og)), lift), add(add(add(e1, mul(r, og)), mul(down, oe)), lift), add(add(add(e0, mul(r, -og)), mul(down, oe)), lift), 3);
        if (!chimney && hash(id, 80) < 0.7) { chimney = true; const hd = norm([down[0], 0, down[2]]), t = 0.25 + 0.5 * hash(id, 81), at = add([lerp(r0[0], r1[0], t), 0, lerp(r0[2], r1[2], t)], mul(hd, 1.1));
          box([at[0], e0[1], at[2]], r, [-r[2], 0, r[0]], 0.36, 0.36, r0[1] - e0[1] + 0.7, 1); }
      }
      if (eaves.length === 4) {                           // the house rectangle, for its plot and for keeping trees off it
        const cen = mul(eaves.reduce(add), 0.25); let u = sub(eaves[1], eaves[0]); u[1] = 0; u = norm(u); const w = [-u[2], 0, u[0]]; let hu = 0, hw = 0;
        for (const p of eaves) { hu = Math.max(hu, Math.abs(dot(sub(p, cen), u))); hw = Math.max(hw, Math.abs(dot(sub(p, cen), w))); }
        addRect(cen[0], cen[2], u[0], u[2], hu, hw); houses.push([cen[0], cen[2], u[0], u[2], hu, hw, id]);
      }
    }
    for (const [id, list] of roofs) {                   // flat roofs
      const k = kindOf(id), t0 = list[0]; cur = { col: pal[Math.min(col[t0], pal.length - 1)], year: yr[t0], bid: id };
      const edges = new Map(); let area = 0, xmin = 1e9, xmax = -1e9, zmin = 1e9, zmax = -1e9;
      for (const t of list) {
        const p = [P(Tr[t * 3]), P(Tr[t * 3 + 1]), P(Tr[t * 3 + 2])]; area += len(cross(sub(p[1], p[0]), sub(p[2], p[0]))) * 0.5;
        for (let j = 0; j < 3; j++) { const a = p[j], b = p[(j + 1) % 3], c = p[(j + 2) % 3]; xmin = Math.min(xmin, a[0]); xmax = Math.max(xmax, a[0]); zmin = Math.min(zmin, a[2]); zmax = Math.max(zmax, a[2]);
          const ka = Math.round(a[0] * 20) + ',' + Math.round(a[2] * 20) + ',' + Math.round(a[1] * 10), kb = Math.round(b[0] * 20) + ',' + Math.round(b[2] * 20) + ',' + Math.round(b[1] * 10), key = ka < kb ? ka + '|' + kb : kb + '|' + ka, e = edges.get(key);
          if (e) e.n++; else edges.set(key, { a, b, c, n: 1 }); }
      }
      const outline = [];
      for (const e of edges.values()) { if (e.n !== 1) continue; let d = sub(e.b, e.a); d[1] = 0; if (len(d) < 0.05) continue; d = norm(d); let inw = [-d[2], 0, d[0]]; const tc = sub(e.c, e.a); tc[1] = 0; if (dot(inw, tc) < 0) inw = mul(inw, -1); outline.push({ a: e.a, b: e.b, inw }); }
      if (outline.length < 3) continue;
      const quadRoof = outline.length === 4, y = V[Tr[t0 * 3] * 3 + 1]; let cen = [0, 0, 0], Uv = [1, 0, 0], Wv = [0, 0, 1], hu = 0, hw = 0;
      if (quadRoof) {
        let best = 0; for (const e of outline) { cen = add(cen, mul(add(e.a, e.b), 0.5)); const l = len(sub(e.b, e.a)); if (l > best) { best = l; Uv = mul(sub(e.b, e.a), 1 / l); } }
        cen = mul(cen, 0.25); Uv[1] = 0; Uv = norm(Uv); Wv = [-Uv[2], 0, Uv[0]];
        for (const e of outline) { hu = Math.max(hu, Math.abs(dot(sub(e.a, cen), Uv))); hw = Math.max(hw, Math.abs(dot(sub(e.a, cen), Wv))); } cen[1] = y;
        addRect(cen[0], cen[2], Uv[0], Uv[2], hu, hw);
      } else addRect((xmin + xmax) / 2, (zmin + zmax) / 2, 1, 0, (xmax - xmin) / 2, (zmax - zmin) / 2);
      if (k === 'house' || k === 'solar') continue;
      const existing = k === 'existing', tall = k === 'tower' || k === 'business' || k === 'mixed', housing = k === 'res_mid' || k === 'res_high' || k === 'residential' || k === 'resort' || k === 'hotel', shed = k === 'industry' || k === 'utility';
      const fl = bFloors[id], gy = bGround[id];
      if (existing && quadRoof && area < 260 && fl <= 2 && hw > 1.5) {                 // small existing houses: a hipped tile roof with eaves
        const ov = 0.35, rise = Math.min(hw * 0.62, 3.4), ridge = Math.max(hu - hw, 0), E = (su, sw) => add(add(cen, mul(Uv, su * (hu + ov))), mul(Wv, sw * (hw + ov)));
        const e0 = E(-1, -1), e1 = E(1, -1), e2 = E(1, 1), e3 = E(-1, 1), r0 = add(add(cen, mul(Uv, -ridge)), [0, rise, 0]), r1 = add(add(cen, mul(Uv, ridge)), [0, rise, 0]);
        quad(e0, e1, r1, r0, 3); quad(e2, e3, r0, r1, 3); tri3(e1, e2, r1, 3); tri3(e3, e0, r0, 3); continue;
      }
      if (quadRoof && (!existing || area >= 300) && gy > 1 && y - gy > 2.5) box([cen[0], gy - 1.5, cen[2]], Uv, Wv, hu + 2.6, hw + 2.6, 1.85, 4);     // paved plinth
      let ph = existing ? 0.45 : tall ? 1.3 : housing ? 1.0 : shed ? 0.6 : 0.9; const pt = area < 200 ? 0.25 : 0.4; if (existing && area < 110) ph = 0;
      if (ph > 0) for (const e of outline) {             // parapet: outer face and coping (seen from both sides)
        const up = [0, ph, 0], ai = add(e.a, mul(e.inw, pt)), bi = add(e.b, mul(e.inw, pt));
        quad(e.a, e.b, add(e.b, up), add(e.a, up), 1); quad(add(e.a, up), add(e.b, up), add(bi, up), add(ai, up), 1);
      }
      if (!quadRoof || existing || hw < 3) continue;
      const at = (fu, fw) => add(add(cen, mul(Uv, fu)), mul(Wv, fw));
      if (tall || (k === 'res_high' && fl >= 14)) {      // a set-back top for plant, a second step on the tallest
        const s1 = 0.66 + 0.12 * hash(id, 1), h1 = 3.4 + 1.6 * hash(id, 2); box(cen, Uv, Wv, hu * s1, hw * s1, h1, 1);
        if (fl >= 20) box(add(cen, [0, h1, 0]), Uv, Wv, hu * s1 * 0.55, hw * s1 * 0.55, 2.6 + 2.4 * hash(id, 3), 1);
        if (hash(id, 4) < 0.5) box(at(hu * (s1 + 0.14) * (hash(id, 5) < 0.5 ? 1 : -1), 0), Uv, Wv, Math.min(1.6, hu * 0.1), Math.min(2.4, hw * 0.3), 1.5, 2);
      } else if (shed) {                                  // roof lights across the shed
        if (area > 900) { const rows = clamp(Math.floor(hw * 2 / 9), 1, 10); for (let i = 0; i < rows; i++) box(at(0, ((i + 0.5) / rows - 0.5) * 2 * (hw - 3)), Uv, Wv, hu - 3.5, 0.9, 0.85, 2); }
        if (hash(id, 6) < 0.6) box(at((hu - 4) * (hash(id, 7) < 0.5 ? 1 : -1), (hw - 4) * (hash(id, 8) < 0.5 ? 1 : -1)), Uv, Wv, 1.6, 1.6, 2.2, 2);
      } else {                                            // stair heads and plant
        const n = area < 260 ? 0 : area < 800 ? 1 : area < 2400 ? 2 : 3;
        for (let i = 0; i < n; i++) { const fu = n === 1 ? (hash(id, 9) - 0.5) * 0.5 : ((i + 0.5) / n - 0.5) * 1.5, fw = (hash(id, 10 + i) - 0.5) * 0.5; box(at(hu * fu, hw * fw), Uv, Wv, Math.min(2.8, hu * 0.22), Math.min(1.9, hw * 0.3), 2.5 + 0.5 * hash(id, 20 + i), 1); }
        const plant = area < 400 ? 0 : area < 1500 ? 1 : 2;
        for (let i = 0; i < plant; i++) box(at(hu * (hash(id, 30 + i) - 0.5) * 1.3, hw * (hash(id, 40 + i) - 0.5) * 1.1), Uv, Wv, 1.1 + hash(id, 50 + i), 0.9 + 0.6 * hash(id, 60 + i), 1.1 + 0.7 * hash(id, 70 + i), 2);
      }
    }
    const mk = (p, w, i, c, index) => {
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3)); g.setAttribute('aWall', new THREE.BufferAttribute(w, 2)); g.setAttribute('aInfo', new THREE.BufferAttribute(i, 2));
      g.setAttribute('color', new THREE.BufferAttribute(c, 3, true)); if (index) g.setIndex(new THREE.BufferAttribute(index, 1)); g.computeBoundingSphere();
      g.computeBoundingBox(); const m = new THREE.Mesh(g, bMat); m.castShadow = m.receiveShadow = true; m.customDepthMaterial = bShadow; scene.add(m); bMeshes.push(m);
    };
    mk(pos, wall, info, cl, null); nTris += nt;
    if (xn) { mk(new Float32Array(xp), new Float32Array(xw), new Float32Array(xi), new Uint8Array(xc), new Uint32Array(ix)); nTris += ix.length / 3; }
    if (o % 6 === 0) { status(T('buildings') + ' ' + Math.round(100 * o / count) + ' %'); await tick(); }
  }
}

// ---------------------------------------------------------------- roads (the rules of FilmRoads.cs)
status(T('roads'));
const DIMS = [[11, 0, 3, 0.36], [9, 0, 2, 0.31], [7.5, 3.5, 2, 0.26], [4, 2.4, 1, 0.21]];      // half carriageway, pavement, lanes per direction, height above the ground
const corridors = new Map(), streetTrees = new Map(), CELL = 480, ckey = (x, z) => Math.floor(x / CELL) * 100003 + Math.floor(z / CELL);
{
  const rd = await gunzip(DATA.roads), dv = new DataView(rd.buffer), nE = dv.getUint32(0, true); let off = 4;
  let P = [], R = [], Dm = [], Y = [], I = [], n = 0; const meshes = [];
  const rMat = film(new THREE.MeshPhongMaterial({ shininess: 0, specular: 0x000000, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 }), {
    vsDecl: 'attribute vec2 aRoad; attribute vec4 aDims; attribute vec4 aYears; uniform float uScen; varying vec2 vRoad; varying vec4 vDims; varying float vYearR; varying vec3 vWp;',
    vsMain: 'vRoad = aRoad; vDims = aDims; vYearR = uScen < 0.5 ? aYears.x : uScen < 1.5 ? aYears.y : uScen < 2.5 ? aYears.z : aYears.w; vWp = vec3(position.x, position.y, -position.z);',
    fsDecl: 'varying vec2 vRoad; varying vec4 vDims; varying float vYearR; varying vec3 vWp;', color: GLSL_ROAD });
  const flush = () => { if (!n) return; const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(P), 3)); g.setAttribute('aRoad', new THREE.BufferAttribute(new Float32Array(R), 2));
    g.setAttribute('aDims', new THREE.BufferAttribute(new Float32Array(Dm), 4)); g.setAttribute('aYears', new THREE.BufferAttribute(new Float32Array(Y), 4)); g.setIndex(new THREE.BufferAttribute(new Uint32Array(I), 1)); g.computeVertexNormals(); g.computeBoundingSphere();
    const m = new THREE.Mesh(g, rMat); m.receiveShadow = true; scene.add(m); P = []; R = []; Dm = []; Y = []; I = []; n = 0; };
  let seed = 2050; const rnd = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  for (let e = 0; e < nE; e++) {
    const cls = rd[off], y4 = [2000 + rd[off + 1], 2000 + rd[off + 2], 2000 + rd[off + 3], 2000 + rd[off + 4]], np = dv.getUint16(off + 5, true); off += 7; const g = [];
    for (let i = 0; i < np; i++) { g.push([dv.getInt32(off, true) / 10, dv.getInt32(off + 4, true) / 10]); off += 8; }
    const [half, walk, lanes, lift] = DIMS[cls], pts = [], along = []; let lenE = 0;
    for (let i = 0; i < g.length; i++) {
      if (i > 0) { const d = Math.hypot(g[i][0] - g[i - 1][0], g[i][1] - g[i - 1][1]), k = Math.max(1, Math.ceil(d / 15)); for (let j = 1; j <= k; j++) { pts.push([lerp(g[i - 1][0], g[i][0], j / k), lerp(g[i - 1][1], g[i][1], j / k)]); along.push(lenE + d * j / k); } lenE += d; }
      else { pts.push(g[0]); along.push(0); }
    }
    if (lenE < 0.5) continue;
    for (let pass = walk > 0 ? 0 : 1; pass < 2; pass++) {
      const w = pass === 0 ? half + walk : half, up = pass === 0 ? 0.12 : lift, v0 = n;
      for (let i = 0; i < pts.length; i++) {
        const a = pts[Math.max(i - 1, 0)], b = pts[Math.min(i + 1, pts.length - 1)], dl = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, dx = (b[0] - a[0]) / dl, dz = (b[1] - a[1]) / dl;
        for (let s = -1; s <= 1; s++) { const x = pts[i][0] - dz * w * s, z = pts[i][1] + dx * w * s; P.push(x, Hgt(x, z) + up, -z); R.push(w * s, along[i]); Dm.push(half, pass, lenE, lanes); Y.push(y4[0], y4[1], y4[2], y4[3]); n++; }
        if (i > 0) { const p = v0 + (i - 1) * 3, q = v0 + i * 3; for (let s = 0; s < 2; s++) I.push(p + s, q + s, p + s + 1, p + s + 1, q + s, q + s + 1); }
      }
    }
    // road corridors (no trees on them) and the rows of street trees, sorted into cells
    let next = 13 * rnd(); const offT = half + walk * 0.55, corr = half + walk + 1.2;
    for (let i = 1; i < g.length; i++) {
      const a = g[i - 1], b = g[i], l = Math.hypot(b[0] - a[0], b[1] - a[1]); if (l < 0.01) continue; const dx = (b[0] - a[0]) / l, dz = (b[1] - a[1]) / l;
      for (let gz = Math.floor((Math.min(a[1], b[1]) - corr) / CELL); gz <= Math.floor((Math.max(a[1], b[1]) + corr) / CELL); gz++) for (let gx = Math.floor((Math.min(a[0], b[0]) - corr) / CELL); gx <= Math.floor((Math.max(a[0], b[0]) + corr) / CELL); gx++) {
        const k = gx * 100003 + gz; let li = corridors.get(k); if (!li) corridors.set(k, li = []); li.push([a[0], a[1], b[0], b[1], corr]); }
      if (walk > 0) { for (; next < l; next += 13 * (0.85 + 0.3 * rnd())) for (let side = -1; side <= 1; side += 2) {
        const x = a[0] + dx * next - dz * offT * side, z = a[1] + dz * next + dx * offT * side, k = ckey(x, z); let li = streetTrees.get(k); if (!li) streetTrees.set(k, li = []); li.push([x, z, cls === 2 ? 1 : (e & 3) === 0 ? 1 : 0, 0]); }
        next -= l; }
    }
    if (n > 180000) flush();
  }
  flush();
}
// house plots: a hedge round each generated house with a gap for the gate, and a tree or two in the garden
const hedgeCells = new Map();
for (const h of houses) {
  const [cx, cz, ux, uz, hu, hw, id] = h, wx = -uz, wz = ux, pu = hu + 5.5, pw = hw + 7.5, hh = Math.imul(id, 7919), gate = (hh & 1) === 0 ? 1 : -1;
  const at = (fu, fw) => [cx + ux * fu + wx * fw, cz + uz * fu + wz * fw];
  const hedge = (a, b) => { const mx = (a[0] + b[0]) / 2, mz = (a[1] + b[1]) / 2, k = ckey(mx, mz); let l = hedgeCells.get(k); if (!l) hedgeCells.set(k, l = []); l.push([mx, mz, Math.atan2(b[1] - a[1], b[0] - a[0]), Math.hypot(b[0] - a[0], b[1] - a[1])]); };
  hedge(at(-pu, -pw * gate), at(pu, -pw * gate)); hedge(at(-pu, -pw), at(-pu, pw)); hedge(at(pu, -pw), at(pu, pw)); hedge(at(-pu, pw * gate), at(-1.8, pw * gate)); hedge(at(1.8, pw * gate), at(pu, pw * gate));
  for (let t = 0; t < 2; t++) { const fu = (((hh >> (3 + t * 5)) & 31) / 31 - 0.5) * 1.6 * pu, fw = (hw + 2.2 + (((hh >> (9 + t * 5)) & 15) / 15) * 4) * (t === 0 ? -gate : gate), p = at(fu, fw), k = ckey(p[0], p[1]);
    let l = streetTrees.get(k); if (!l) streetTrees.set(k, l = []); l.push([p[0], p[1], ((hh >> 20) & 7) === 0 ? 2 : 0, 1]); }
}

// ---------------------------------------------------------------- trees (the rules of FilmTrees.cs), placed cell by cell round the view
function treeGeo(build) { const v = [], c = [], ix = []; build(v, c, ix); const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(v), 3)); g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(c), 3)); g.setIndex(ix); g.computeVertexNormals(); return g; }
function blob(seg, rings, r, trunkH, trunkR, jitter, low, high, seed) {
  return treeGeo((v, c, ix) => {
    let s = seed; const rnd = () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
    if (trunkR > 0) for (let i = 0; i < 5; i++) { const a0 = i / 5 * 6.2832, a1 = (i + 1) / 5 * 6.2832, b = v.length / 3, top = trunkH + r[1] * 0.4;
      v.push(Math.cos(a0) * trunkR, 0, Math.sin(a0) * trunkR, Math.cos(a1) * trunkR, 0, Math.sin(a1) * trunkR, Math.cos(a1) * trunkR * 0.7, top, Math.sin(a1) * trunkR * 0.7, Math.cos(a0) * trunkR * 0.7, top, Math.sin(a0) * trunkR * 0.7);
      for (let k = 0; k < 4; k++) c.push(0.33, 0.25, 0.19); ix.push(b, b + 2, b + 1, b, b + 3, b + 2); }
    const b0 = v.length / 3, cy = trunkH + r[1] * 0.9;
    for (let j = 0; j <= rings; j++) for (let i = 0; i < seg; i++) { const th = j / rings * Math.PI, ph = i / seg * 6.2832, k = (j === 0 || j === rings) ? 1 : 1 + jitter * (rnd() * 2 - 1), y = Math.cos(th) * r[1] * k, t = clamp(y / r[1] * 0.5 + 0.5, 0, 1);
      v.push(Math.sin(th) * Math.cos(ph) * r[0] * k, y + cy, Math.sin(th) * Math.sin(ph) * r[2] * k); c.push(lerp(low[0], high[0], t), lerp(low[1], high[1], t), lerp(low[2], high[2], t)); }
    for (let j = 0; j < rings; j++) for (let i = 0; i < seg; i++) { const a = b0 + j * seg + i, b = b0 + j * seg + (i + 1) % seg, d = a + seg, e = b + seg; ix.push(a, d, b, b, d, e); }
  });
}
function cones(seg, radius, height, low, high, tiers) {
  return treeGeo((v, c, ix) => { for (let k = 0; k < tiers; k++) { const y0 = 1.2 + (height - 1.2) * k / (tiers + 0.6), y1 = tiers === 1 ? height : y0 + (height - 1.2) / tiers * 1.25, rr = radius * (1 - 0.26 * k), b = v.length / 3, t = k / tiers * 0.6;
    v.push(0, y1, 0); c.push(high[0], high[1], high[2]); for (let i = 0; i < seg; i++) { const a = i / seg * 6.2832; v.push(Math.cos(a) * rr, y0, Math.sin(a) * rr); c.push(lerp(low[0], high[0], t), lerp(low[1], high[1], t), lerp(low[2], high[2], t)); }
    for (let i = 0; i < seg; i++) ix.push(b, b + 1 + (i + 1) % seg, b + 1 + i); } });
}
const hedgeGeo = treeGeo((v, c, ix) => { const p = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], lo = [0.12, 0.21, 0.11], hi = [0.24, 0.36, 0.17];
  for (const q of p) { v.push(q[0], 0, q[1]); c.push(...lo); } for (const q of p) { v.push(q[0], 1, q[1]); c.push(...hi); }
  ix.push(0, 5, 1, 0, 4, 5, 1, 6, 2, 1, 5, 6, 2, 7, 3, 2, 6, 7, 3, 4, 0, 3, 7, 4, 4, 6, 5, 4, 7, 6); });
const G1 = [0.17, 0.27, 0.13], G2 = [0.31, 0.42, 0.19], P1 = [0.15, 0.25, 0.13], P2 = [0.28, 0.40, 0.19], F1 = [0.09, 0.18, 0.14], F2 = [0.17, 0.29, 0.21];
const SPECIES = [[blob(9, 6, [3.3, 3.5, 3.3], 3.2, 0.28, 0.22, G1, G2, 11), blob(5, 3, [3.3, 3.5, 3.3], 3.2, 0, 0.1, G1, G2, 11)], [blob(8, 7, [1.55, 6.2, 1.55], 2.0, 0.26, 0.12, P1, P2, 23), blob(5, 3, [1.55, 6.2, 1.55], 2.0, 0, 0.05, P1, P2, 23)],
  [cones(8, 2.5, 10.5, F1, F2, 3), cones(5, 2.5, 10.5, F1, F2, 1)], [hedgeGeo, hedgeGeo]];
const tVs = { decl: 'attribute float aYearT; attribute vec3 aTint; varying float vYearT; varying vec3 vTint; varying vec3 vNu;', main: 'vYearT = aYearT; vTint = aTint; vNu = normalize(mat3(instanceMatrix) * vec3(normal.x, normal.y, normal.z)); vNu.z = -vNu.z;' };
const tMat = film(new THREE.MeshPhongMaterial({ vertexColors: true, shininess: 0, specular: 0x000000 }), { vsDecl: tVs.decl, vsMain: tVs.main, fsDecl: 'varying float vYearT; varying vec3 vTint; varying vec3 vNu;', color: GLSL_TREE });
const tShadow = shadowOf({ vsDecl: 'attribute float aYearT; varying float vYearT;', vsMain: 'vYearT = aYearT;', fsDecl: 'varying float vYearT; uniform float uDevK;', clip: 'if ((uGrow > 0.5 ? uYearF + 1.0 : uYear) - (vYearT <= 2025.5 ? vYearT : 2025.0 + (vYearT - 2025.0) * uDevK) + 0.2 < 0.0) discard;' });
const treeCells = new Map(), treeRoot = new THREE.Group(); scene.add(treeRoot);
function genCell(k, gx, gz) {
  let s = (Math.imul(gx, 73856093) ^ Math.imul(gz, 19349663)) >>> 0; const rnd = () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; };
  const inst = [[], [], [], []], segs = corridors.get(k);
  const onRoad = (x, z, slack) => { if (!segs) return false; for (const g of segs) { const abx = g[2] - g[0], abz = g[3] - g[1], t = clamp(((x - g[0]) * abx + (z - g[1]) * abz) / Math.max(abx * abx + abz * abz, 1e-6), 0, 1); if (Math.hypot(x - g[0] - abx * t, z - g[1] - abz * t) < g[4] - slack) return true; } return false; };
  const put = (x, z, sp, year, size) => { if (blocked(x, z, 3.2 * size)) return; inst[sp].push([x, Hgt(x, z) - 0.15, z, rnd() * 6.2832, size, size * (0.9 + 0.25 * rnd()), size, year, 0.86 + 0.26 * rnd(), rnd()]); };
  for (const p of streetTrees.get(k) || []) { const [ld, yr] = land(p[0], p[1]); if (ld !== 3 && !(p[3] && onRoad(p[0], p[1], 0))) put(p[0], p[1], p[2], yr, 0.8 + 0.3 * rnd()); }
  for (const hd of hedgeCells.get(k) || []) { const [ld, yr] = land(hd[0], hd[1]); if (ld === 3 || onRoad(hd[0], hd[1], 1) || blocked(hd[0], hd[1], 0.5)) continue; inst[3].push([hd[0], Hgt(hd[0], hd[1]) - 0.5, hd[1], -hd[2], hd[3], 1.5 + 0.2 * rnd(), 0.6, yr, 0.9 + 0.2 * rnd(), 0.5]); }
  const n = Math.round(CELL / 14);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const x = (gx + (i + rnd()) / n) * CELL, z = (gz + (j + rnd()) / n) * CELL, pick = rnd(), kind = rnd(), size = 0.75 + 0.5 * rnd(), [ld, yr] = land(x, z);
    const p = ld === 1 ? 0.25 + 0.6 * (0.5 + 0.5 * Math.sin(x * 0.012 + 31) * Math.cos(z * 0.012 + 7)) : ld === 0 ? 0.11 : ld === 2 ? 0.004 : 0;
    if (pick > p || onRoad(x, z, 0)) continue; put(x, z, ld === 1 ? (kind < 0.58 ? 0 : kind < 0.82 ? 2 : 1) : (kind < 0.8 ? 0 : 1), yr, size);
  }
  const cell = { meshes: [], near: null, group: new THREE.Group(), box: new THREE.Box3(V3(gx * CELL - 8, M.lo - 10, -(gz + 1) * CELL - 8), V3((gx + 1) * CELL + 8, M.hi + 40, -gz * CELL + 8)), cx: (gx + 0.5) * CELL, cz: (gz + 0.5) * CELL, count: 0 };
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  for (let sp = 0; sp < 4; sp++) {
    const L = inst[sp]; if (!L.length) { cell.meshes.push(null); continue; } cell.count += L.length;
    const years = new Float32Array(L.length), tints = new Float32Array(L.length * 3), pair = [];
    for (let lod = 0; lod < 2; lod++) {
      const base = SPECIES[sp][lod], g = new THREE.BufferGeometry(); g.setAttribute('position', base.attributes.position); g.setAttribute('normal', base.attributes.normal); g.setAttribute('color', base.attributes.color); g.setIndex(base.index);
      g.setAttribute('aYearT', new THREE.InstancedBufferAttribute(years, 1)); g.setAttribute('aTint', new THREE.InstancedBufferAttribute(tints, 3));
      const im = new THREE.InstancedMesh(g, tMat, L.length); im.frustumCulled = false; im.castShadow = true; im.receiveShadow = true; im.customDepthMaterial = tShadow;
      L.forEach((t, i) => { e.set(0, sp === 3 ? t[3] : -t[3], 0); q.setFromEuler(e); m4.compose(V3(t[0], t[1], -t[2]), q, V3(t[4], t[5], t[6])); im.setMatrixAt(i, m4); years[i] = t[7]; const v = t[8], w = t[9]; tints[i * 3] = v * (1 + 0.10 * w); tints[i * 3 + 1] = v; tints[i * 3 + 2] = v * (1 - 0.12 * w); });
      im.instanceMatrix.needsUpdate = true; cell.group.add(im); pair.push(im);
    }
    cell.meshes.push(pair);
  }
  treeRoot.add(cell.group); return cell;
}
const frustum = new THREE.Frustum(), pm = new THREE.Matrix4();
function updateTrees(sync) {
  if (S.dist > 6500) { treeRoot.visible = false; return; } treeRoot.visible = true;
  const R = clamp(S.dist * 2.6, 1500, 4600), fx = S.target[0], fz = S.target[2], t0 = performance.now(); let made = 0;
  pm.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse); frustum.setFromProjectionMatrix(pm);
  const want = [];
  for (let gz = Math.floor((fz - R) / CELL); gz <= Math.floor((fz + R) / CELL); gz++) for (let gx = Math.floor((fx - R) / CELL); gx <= Math.floor((fx + R) / CELL); gx++) { const k = gx * 100003 + gz; if (!treeCells.has(k)) want.push([k, gx, gz, ((gx + 0.5) * CELL - fx) ** 2 + ((gz + 0.5) * CELL - fz) ** 2]); }
  want.sort((a, b) => a[3] - b[3]);
  for (const w of want) { treeCells.set(w[0], genCell(w[0], w[1], w[2])); made++; if (!sync && performance.now() - t0 > 6) break; }
  const cp = camera.position;
  for (const c of treeCells.values()) {
    const far = Math.abs(c.cx - fx) > R + CELL || Math.abs(c.cz - fz) > R + CELL, vis = !far && c.count > 0 && frustum.intersectsBox(c.box); c.group.visible = vis; if (!vis) continue;
    const near = Math.hypot(c.cx - cp.x, c.cz + cp.z) < 1500; for (const p of c.meshes) if (p) { p[0].visible = near; p[1].visible = !near; }
  }
  return want.length - made;
}

// ---------------------------------------------------------------- sky
const sky = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, depthTest: false, fog: false, uniforms: U,
  vertexShader: 'varying vec3 vDir; void main() { vDir = vec3(position.x, position.y, -position.z); vec4 p = projectionMatrix * mat4(mat3(modelViewMatrix)) * vec4(position, 1.0); gl_Position = p.xyww; }', fragmentShader: GLSL_FILM + GLSL_SKY }));
sky.frustumCulled = false; sky.renderOrder = -10; scene.add(sky);

// ---------------------------------------------------------------- light by the hour (the rules of FilmLook.cs)
const sun = new THREE.DirectionalLight(0xffffff, 1); sun.castShadow = true; sun.shadow.mapSize.set(4096, 4096); scene.add(sun); scene.add(sun.target);
scene.fog = new THREE.FogExp2(0xffffff, 0.00002);
const mix3 = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
function setLight() {
  const hour = S.hour, day = (hour - 5.5) / 13, el = day >= 0 && day <= 1 ? Math.sin(day * Math.PI) * 58 : -Math.min(12, (day < 0 ? -day : day - 1) * 13 * 8);
  const az = lerp(75, 285, clamp(day, 0, 1)) * Math.PI / 180, e = Math.max(el, 4) * Math.PI / 180, toSun = [Math.sin(az) * Math.cos(e), Math.sin(e), Math.cos(az) * Math.cos(e)];
  const sm = (a, b) => { const t = clamp((el - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const gold = 1 - sm(6, 30), dusk = sm(7, -2), night = sm(-3, -11), lamps = sm(9, -5);
  const sunC = mix3(mix3(mix3([1, 0.96, 0.90], [1, 0.74, 0.47], gold), [1, 0.56, 0.40], dusk), [0.34, 0.42, 0.62], night);
  const zen = mix3(mix3(mix3([0.27, 0.48, 0.80], [0.30, 0.44, 0.70], gold), [0.15, 0.22, 0.44], dusk), [0.025, 0.04, 0.10], night);
  const hor = mix3(mix3(mix3([0.76, 0.85, 0.93], [0.97, 0.78, 0.58], gold), [0.93, 0.56, 0.40], dusk), [0.10, 0.12, 0.22], night);
  const gnd = mix3(hor, [0.5, 0.5, 0.5], 0.35).map(v => v * 0.85), inten = lerp(lerp(lerp(1.0, 0.95, gold), 0.50, dusk), 0.20, night), skyL = lerp(1, 1.35, dusk) * lerp(1, 0.9, night);
  U.uSunDir.value.set(toSun[0], toSun[1], toSun[2]); U.uSunCol.value.setRGB(sunC[0], sunC[1], sunC[2]); U.uZen.value.setRGB(zen[0], zen[1], zen[2]); U.uHor.value.setRGB(hor[0], hor[1], hor[2]); U.uGnd.value.setRGB(gnd[0], gnd[1], gnd[2]);
  const as = mix3(zen, hor, 0.45).map(v => v * 0.52 * skyL), ae = mix3(hor, zen, 0.5 * dusk).map(v => v * 0.44 * skyL), ag = gnd.map(v => v * 0.32);
  U.uAmbSky.value.setRGB(as[0], as[1], as[2]); U.uAmbEq.value.setRGB(ae[0], ae[1], ae[2]); U.uAmbGnd.value.setRGB(ag[0], ag[1], ag[2]); U.uNight.value = lamps; U.uSunInt.value = inten;
  sun.color.setRGB(sunC[0] * inten * 1.2, sunC[1] * inten * 1.2, sunC[2] * inten * 1.2); S.toSun = toSun; S.shadow = lerp(0.86, 0.55, dusk); S.exp = Math.min(1, Math.pow(0.92 / (1.2 * inten * Math.sin(e) + 0.5), 0.7));
  const fc = mix3(hor, zen, 0.12 + 0.3 * dusk); scene.fog.color.setRGB(fc[0], fc[1], fc[2]);
}

// ---------------------------------------------------------------- picture finish: occlusion, depth of field, grade
const rt = new THREE.WebGLRenderTarget(4, 4, { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, type: THREE.HalfFloatType });
rt.depthTexture = new THREE.DepthTexture(4, 4); rt.depthTexture.type = THREE.UnsignedIntType;
const aoRT = new THREE.WebGLRenderTarget(4, 4, { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
const PU = { tColor: { value: rt.texture }, tDepth: { value: rt.depthTexture }, tAO: { value: aoRT.texture }, uProj: { value: new THREE.Vector4() }, uNF: { value: new THREE.Vector2() }, uPx: { value: new THREE.Vector2() },
  uDof: { value: new THREE.Vector4() }, uFog: { value: 0 }, uTime: { value: 0 }, uExp: { value: 1 } }, PV = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }';
const post = new THREE.ShaderMaterial({ depthTest: false, depthWrite: false, uniforms: PU, vertexShader: PV, fragmentShader: GLSL_POST });
const postAO = new THREE.ShaderMaterial({ depthTest: false, depthWrite: false, uniforms: PU, vertexShader: PV, fragmentShader: GLSL_POST_AO });
const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1), quadGeo = new THREE.PlaneGeometry(2, 2);
const postScene = new THREE.Scene(), aoScene = new THREE.Scene(); postScene.add(new THREE.Mesh(quadGeo, post)); aoScene.add(new THREE.Mesh(quadGeo, postAO));

// ---------------------------------------------------------------- camera
function placeCamera() {
  const yaw = S.yaw * Math.PI / 180, pitch = S.pitch * Math.PI / 180, f = [Math.sin(yaw) * Math.cos(pitch), -Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch)];
  S.target[1] = Hgt(S.target[0], S.target[2]); let p = [S.target[0] - f[0] * S.dist, S.target[1] - f[1] * S.dist, S.target[2] - f[2] * S.dist];
  const above = p[1] - Hgt(p[0], p[2]); if (above < 30) p[1] += 30 - above;
  camera.position.set(p[0], p[1], -p[2]); camera.lookAt(S.target[0], S.target[1], -S.target[2]); camera.near = clamp(S.dist * 0.01, 2, 300); camera.far = clamp(S.dist * 40, 60000, 1500000); camera.updateProjectionMatrix(); camera.updateMatrixWorld();
  U.uCamU.value.set(p[0], p[1], p[2]);
}
function view(pos, fwd) {             // a camera of the model (position and direction in the map frame) as target, distance, yaw, pitch
  const l = Math.hypot(fwd[0], fwd[1], fwd[2]), f = fwd.map(v => v / l), gy = Hgt(pos[0], pos[2]), t = f[1] < -0.05 ? (pos[1] - gy) / -f[1] : 3000, tg = [pos[0] + f[0] * t, 0, pos[2] + f[2] * t];
  return { target: tg, dist: Math.hypot(pos[0] - tg[0], pos[1] - Hgt(tg[0], tg[2]), pos[2] - tg[2]), yaw: Math.atan2(f[0], f[2]) * 180 / Math.PI, pitch: clamp(Math.asin(-f[1]) * 180 / Math.PI, 8, 89) };
}
const VIEWS = []; { const order = ['Gate District 2050', 'Golden core 2050', 'Growing core 2050', 'Green waterfront 2050', 'Tallest planned cluster'], label = ['Gate', 'Golden', 'Growing', 'Green', 'Tallest'];
  for (const c of M.cameras) if (c.name.startsWith('Overview')) VIEWS.push(Object.assign(view(c.pos, c.fwd), { name: 'overview' }));
  order.forEach((nm, i) => { const c = M.cameras.find(c => c.name === nm); if (c) { const v = view(c.pos, c.fwd); VIEWS.push(Object.assign({}, v, { name: label[i] })); VIEWS.push({ name: label[i] + ' ↓', target: v.target, dist: i === 4 ? 650 : 1500, yaw: v.yaw + 25, pitch: 14 }); } });
  if (!VIEWS.length) VIEWS.push({ name: 'overview', target: [0, 0, 0], dist: 70000, yaw: 0, pitch: 55 }); }
let fly = null;
function goTo(v, now) { if (now) { S.target = v.target.slice(); S.dist = v.dist; S.yaw = v.yaw; S.pitch = v.pitch; fly = null; } else fly = v; }

// ---------------------------------------------------------------- interface
const fill = () => { $('#views').replaceChildren(...VIEWS.map((v, i) => { const b = document.createElement('button'); b.textContent = v.name === 'overview' ? T('overview') : v.name; b.onclick = () => goTo(VIEWS[i]); return b; })); };
function setYear(y) { S.year = clamp(Math.round(y), 2025, 2050); $('#year').value = S.year; $('#yv').textContent = S.year; if (AN) AN.refresh(); }
function setHour(h) { S.hour = h; $('#hour').value = h; const hh = Math.floor(h), mm = Math.round((h - hh) * 60); $('#hv').textContent = hh + ':' + String(mm).padStart(2, '0'); setLight(); }
$('#year').oninput = e => { S.playing = false; applyLang(); setYear(+e.target.value); S.yearF = S.year; };
$('#hour').oninput = e => setHour(+e.target.value);
$('#play').onclick = () => { S.playing = !S.playing; if (S.playing && S.year >= 2050) { setYear(2025); } S.yearF = S.year; applyLang(); };
$('#lang').onclick = () => { lang = lang === 'ru' ? 'en' : 'ru'; applyLang(); fill(); };
$('#q').onclick = () => { S.hi = !S.hi; applyLang(); resize(); };
let drag = null;
canvas.addEventListener('contextmenu', e => e.preventDefault());
let down = null;                             // where the button went down: a press that hardly moves is a click on a building
canvas.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, rot: e.button === 2 || e.altKey }; down = { x: e.clientX, y: e.clientY, b: e.button, t: performance.now() }; canvas.setPointerCapture(e.pointerId); fly = null; });
canvas.addEventListener('pointerup', e => { drag = null; if (OBJ && down && down.b === 0 && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 5 && performance.now() - down.t < 600) OBJ.click(e.clientX, e.clientY); down = null; });
canvas.addEventListener('pointermove', e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
  if (drag.rot) { S.yaw += dx * 0.25; S.pitch = clamp(S.pitch + dy * 0.2, 8, 89); }
  else { const yaw = S.yaw * Math.PI / 180, k = S.dist / canvas.clientHeight * 1.6, fx = Math.sin(yaw), fz = Math.cos(yaw), rx = Math.cos(yaw), rz = -Math.sin(yaw); S.target[0] -= rx * dx * k - fx * dy * k; S.target[2] -= rz * dx * k - fz * dy * k; } });
canvas.addEventListener('wheel', e => { e.preventDefault(); fly = null; S.dist = clamp(S.dist * (1 + clamp(e.deltaY, -300, 300) * 0.0012), 120, 120000); }, { passive: false });
const keys = {}; addEventListener('keydown', e => { keys[e.code] = true; }); addEventListener('keyup', e => { keys[e.code] = false; });
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight, k = (S.hi ? 1.5 : 1.0) * Math.min(devicePixelRatio || 1, 1.5);
  renderer.setPixelRatio(1); renderer.setSize(w, h, false); rt.setSize(Math.round(w * k), Math.round(h * k)); aoRT.setSize(Math.round(w * k / 2), Math.round(h * k / 2)); camera.aspect = w / h; camera.updateProjectionMatrix();
}
addEventListener('resize', resize);

// ---------------------------------------------------------------- frame
let last = performance.now(), frames = 0;
function frame(sync) {
  const now = performance.now(), dt = Math.min((now - last) / 1000, 0.1); last = now;
  const fast = keys.ShiftLeft || keys.ShiftRight ? 3 : 1, yaw = S.yaw * Math.PI / 180, fx = Math.sin(yaw), fz = Math.cos(yaw);
  let mx = 0, mz = 0; if (keys.KeyW || keys.ArrowUp) mz += 1; if (keys.KeyS || keys.ArrowDown) mz -= 1; if (keys.KeyD || keys.ArrowRight) mx += 1; if (keys.KeyA || keys.ArrowLeft) mx -= 1;
  if (mx || mz) { fly = null; const k = 0.9 * S.dist * dt * fast; S.target[0] += (fx * mz + fz * mx) * k; S.target[2] += (fz * mz - fx * mx) * k; }
  if (keys.KeyQ) S.yaw -= 60 * dt * fast; if (keys.KeyE) S.yaw += 60 * dt * fast; if (keys.KeyR) S.pitch = clamp(S.pitch + 40 * dt, 8, 89); if (keys.KeyF) S.pitch = clamp(S.pitch - 40 * dt, 8, 89);
  if (keys.KeyZ) S.dist = Math.max(120, S.dist * (1 - 1.2 * dt * fast)); if (keys.KeyX) S.dist = Math.min(120000, S.dist * (1 + 1.2 * dt * fast));
  if (fly) { const k = 1 - Math.exp(-4 * dt); S.target[0] = lerp(S.target[0], fly.target[0], k); S.target[2] = lerp(S.target[2], fly.target[2], k); S.dist = lerp(S.dist, fly.dist, k); S.yaw += (((fly.yaw - S.yaw) % 360 + 540) % 360 - 180) * k; S.pitch = lerp(S.pitch, fly.pitch, k);
    if (Math.hypot(S.target[0] - fly.target[0], S.target[2] - fly.target[2]) < 1 && Math.abs(S.dist - fly.dist) < 1) fly = null; }
  if (S.playing) { S.yearF += dt / 1.0; if (S.yearF >= 2050) { S.yearF = 2050; S.playing = false; applyLang(); } setYear(Math.floor(S.yearF + 1e-4)); }
  U.uYear.value = S.year; U.uYearF.value = S.yearF; U.uGrow.value = S.playing ? 1 : 0;
  placeCamera();
  const vis = clamp(S.dist * 7, 22000, 320000); scene.fog.density = 0.83 / vis;
  const cover = clamp(S.dist * 1.5, 500, 14000), sc = sun.shadow.camera; sc.left = -cover; sc.right = cover; sc.top = cover; sc.bottom = -cover; sc.near = 100; sc.far = 60000; sc.updateProjectionMatrix();
  sun.target.position.set(S.target[0], S.target[1], -S.target[2]); sun.position.set(S.target[0] + S.toSun[0] * 30000, S.target[1] + S.toSun[1] * 30000, -S.target[2] - S.toSun[2] * 30000);
  sun.shadow.bias = -0.00008; sun.shadow.normalBias = cover / 4096 * 3.0; sun.shadow.radius = 2;
  sky.position.copy(camera.position); sky.scale.setScalar(camera.far * 0.5);
  const left = updateTrees(sync);
  const P = camera.projectionMatrix.elements, k = rt.height / 1080;
  post.uniforms.uProj.value.set(1 / P[0], 1 / P[5], clamp(S.dist * 0.012, 5, 60), 1.25); post.uniforms.uNF.value.set(camera.near, camera.far); post.uniforms.uPx.value.set(1 / rt.width, 1 / rt.height);
  post.uniforms.uDof.value.set(S.dist, S.dist * 0.42, 5 * (1 - smooth(3500, 9000, S.dist)) * k, 1); post.uniforms.uFog.value = scene.fog.density; post.uniforms.uTime.value = frames % 64; post.uniforms.uExp.value = S.exp || 1;
  renderer.setRenderTarget(rt); renderer.render(scene, camera); renderer.setRenderTarget(aoRT); renderer.render(aoScene, postCam); renderer.setRenderTarget(null); renderer.render(postScene, postCam); frames++; if (OBJ) OBJ.frame();
  return left;
}
status(T('analytics'));
AN = await AlatauAnalytics({ DATA, gunzip, NB, bKind, bYear, bHeight, KIND, S, U, VIEWS, goTo, getLang: () => lang });
OBJ = await AlatauObjects({ DATA, gunzip, S, U, goTo, Hgt, scene, camera, canvas, film, bMeshes, getLang: () => lang, AN, NB, bYear, bHeight, bFloors });
SITE = await AlatauSite({ DATA, S, goTo, Hgt, scene, film, getLang: () => lang, AN, setYear, setNoTrees: fn => { noTrees = fn; } }, OBJ);
setHour(17); const start = VIEWS.find(v => v.name === 'Gate ↓') || VIEWS[0]; goTo(start, true); resize(); placeCamera(); fill(); applyLang(); setYear(2050);
$('#load').hidden = true; S.ready = true;
(function loop() { frame(false); requestAnimationFrame(loop); })();
// hooks for tests and screenshots
window.__alatau = { S, VIEWS, goTo, setYear, setHour, frame, U, renderer, sun, scene, camera, film, AN, Hgt, land, objects: () => OBJ, site: () => SITE, nTris: () => nTris, trees: () => { let n = 0; for (const c of treeCells.values()) n += c.count; return n; }, houses: () => houses.length };
})().catch(e => { document.querySelector('#load span').textContent = 'Error: ' + (e && e.message || e); console.error(e); });
