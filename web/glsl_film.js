// Shaders of the film look, ported from the Unity project (Assets/Shaders/AlatauFilm.cginc, AlatauGround, AlatauRoad, AlatauSky,
// AlatauFilmPost). Positions and directions named "map frame" are x east, y up, z north, as in the Unity scene.
const GLSL_FILM = `
uniform float uNight, uYear, uYearF, uGrow, uSunInt, uDevK, uTint;
uniform vec3 uSunDir, uSunCol, uZen, uHor, uGnd, uAmbSky, uAmbEq, uAmbGnd, uCamU;
uniform mediump sampler2DArray tMatA;
uniform mediump sampler2DArray tMatD;
uniform vec3 uMatMean[12];
#ifndef saturate
#define saturate(a) clamp(a, 0.0, 1.0)
#endif
const float AMatSize[12] = float[12](2.4, 3.0, 1.5, 2.6, 2.2, 3.0, 4.0, 2.4, 2.6, 3.4, 2.2, 2.0);
const float AMatStrength[12] = float[12](0.35, 0.40, 0.95, 0.55, 0.95, 0.60, 0.80, 0.70, 0.80, 0.70, 0.95, 0.90);
struct AMat { vec3 pattern; vec3 colour; vec2 nxy; float ao; };
AMat AlatauMat(vec2 metres, float layer) {
  AMat m; int li = int(layer + 0.5); vec3 uv = vec3(metres / AMatSize[li], float(li));
  vec4 a = texture(tMatA, uv), d = texture(tMatD, uv);
  m.colour = a.rgb; m.pattern = a.rgb / max(uMatMean[li], vec3(0.04));
  m.nxy = d.rg * 2.0 - 1.0; m.ao = d.b; return m;
}
float AHash1(float n) { return fract(sin(n * 127.1) * 43758.5453); }
float AHash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float ANoise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(AHash2(i), AHash2(i + vec2(1.0, 0.0)), f.x), mix(AHash2(i + vec2(0.0, 1.0)), AHash2(i + vec2(1.0, 1.0)), f.x), f.y);
}
vec3 AlatauSky(vec3 d) {
  float up = saturate(d.y);
  vec3 mid = mix(uHor, uZen, 0.5) + 0.10 * (1.0 - uNight);
  vec3 c = mix(uHor, mid, smoothstep(0.0, 0.16, up));
  c = mix(c, uZen, smoothstep(0.10, 0.85, up));
  c = mix(c, uGnd, saturate(-d.y * 5.0));
  float s = saturate(dot(d, uSunDir));
  c += uSunCol * (0.22 * pow(s, 6.0) + 0.5 * pow(s, 64.0)) * (1.0 - uNight);
  return c;
}
float ABox(vec2 p, vec2 half_, vec2 aa) { vec2 d = saturate((half_ - abs(p)) / max(aa, vec2(1e-4)) + 0.5); return d.x * d.y; }
// ambient light as Unity's three-colour ambient: sky from above, equator from the side, ground from below
vec3 AmbTri(vec3 n) { return uAmbSky * max(n.y, 0.0) + uAmbEq * (1.0 - abs(n.y)) + uAmbGnd * max(-n.y, 0.0); }
float YearNow() { return uGrow > 0.5 ? uYearF + 1.0 : uYear; }
float YearEff(float y) { return y <= 2025.5 ? y : 2025.0 + (y - 2025.0) * uDevK; }      // pace of the scenario: base 1, fast 0.75, slow 1.3
float ALine(float d, float halfW, float aa) { return saturate((halfW - abs(d)) / max(aa, 1e-4) + 0.5); }
`;

const GLSL_FACADE = `
struct AFacade { vec3 albedo; vec3 emit; float spec; float ao; };
// style: 0 other, 1 house, 2 housing, 3 glass tower / office, 4 public, 5 industry, 6 podium / retail, 7 solar field, 8 resort, 9 existing
AFacade AlatauFacade(vec2 wall, float hy, float H, float floorsN, float style, float seed, vec3 tint, vec3 n, vec3 view, vec3 wpos, float part) {
  AFacade o;
  float r1 = AHash1(seed * 255.0 + 1.0), r2 = AHash1(seed * 255.0 + 7.0), r3 = AHash1(seed * 255.0 + 13.0);
  vec3 wallC = vec3(0.86, 0.85, 0.82); vec3 glassC = vec3(0.10, 0.14, 0.17);
  float bw = 3.4, ww = 0.52, wh = 0.50, sill = 0.30, spandrel = 0.0, mull = 0.0, gf = 1.0;
  float wallL = 0.0, roofL = 5.0;
  if (style < 1.5 && style > 0.5)       { wallL = r1 < 0.75 ? 0.0 : 2.0; roofL = r2 < 0.45 ? 4.0 : 10.0; bw = 3.8; ww = 0.34; wh = 0.42; sill = 0.34; gf = 0.0; wallC = r1 < 0.45 ? vec3(0.90, 0.87, 0.80) : r1 < 0.75 ? vec3(0.83, 0.74, 0.62) : vec3(0.74, 0.50, 0.40); }
  else if (style < 2.5 && style > 1.5)  { wallL = r1 < 0.62 ? 0.0 : r1 < 0.80 ? 1.0 : r1 < 0.92 ? 2.0 : 1.0; bw = 3.3; ww = 0.50; wh = 0.52; sill = 0.28; wallC = r1 < 0.40 ? vec3(0.90, 0.89, 0.86) : r1 < 0.62 ? vec3(0.82, 0.78, 0.70) : r1 < 0.80 ? vec3(0.70, 0.71, 0.72) : r1 < 0.92 ? vec3(0.69, 0.44, 0.34) : vec3(0.36, 0.38, 0.41); }
  else if (style < 3.5 && style > 2.5) {
    wallL = 1.0;
    glassC = r2 < 0.35 ? vec3(0.10, 0.17, 0.24) : r2 < 0.60 ? vec3(0.09, 0.19, 0.20) : r2 < 0.82 ? vec3(0.15, 0.17, 0.19) : vec3(0.22, 0.17, 0.11);
    if (r3 < 0.50)      { bw = 1.6; ww = 0.90; wh = 0.74; sill = 0.0; spandrel = 0.24; mull = 0.06; wallC = r1 < 0.78 ? vec3(0.72, 0.76, 0.80) : vec3(0.32, 0.35, 0.38); }
    else if (r3 < 0.76) { bw = 3.0; ww = 0.76; wh = 0.70; sill = 0.15; wallC = r1 < 0.6 ? vec3(0.92, 0.91, 0.88) : vec3(0.80, 0.76, 0.69); }
    else                { bw = 1.2; ww = 0.90; wh = 0.80; sill = 0.0; spandrel = 0.18; mull = 0.17; wallC = r1 < 0.5 ? vec3(0.90, 0.90, 0.89) : vec3(0.60, 0.50, 0.40); }
  }
  else if (style < 4.5 && style > 3.5)  { wallL = r1 < 0.5 ? 0.0 : r1 < 0.8 ? 1.0 : 2.0; bw = 4.8; ww = 0.72; wh = 0.64; sill = 0.20; wallC = r1 < 0.5 ? vec3(0.89, 0.87, 0.82) : r1 < 0.8 ? vec3(0.78, 0.76, 0.72) : vec3(0.62, 0.48, 0.38); }
  else if (style < 5.5 && style > 4.5)  { wallL = 3.0; bw = 6.0; ww = 0.86; wh = 0.10; sill = 0.72; gf = 0.0; wallC = r1 < 0.5 ? vec3(0.74, 0.76, 0.78) : r1 < 0.8 ? vec3(0.83, 0.82, 0.79) : vec3(0.45, 0.52, 0.60); }
  else if (style < 6.5 && style > 5.5)  { wallL = 1.0; bw = 6.0; ww = 0.86; wh = 0.66; sill = 0.08; wallC = vec3(0.32, 0.33, 0.35); }
  else if (style < 8.5 && style > 7.5)  { wallL = r1 < 0.5 ? 0.0 : 11.0; bw = 3.6; ww = 0.56; wh = 0.56; sill = 0.26; wallC = r1 < 0.5 ? vec3(0.92, 0.90, 0.85) : vec3(0.66, 0.50, 0.36); }
  else if (style > 8.5)                 { wallL = r1 < 0.8 ? 0.0 : 2.0; roofL = r2 < 0.5 ? 4.0 : 10.0; bw = 3.4; ww = 0.40; wh = 0.44; sill = 0.32; gf = 0.0; wallC = r1 < 0.5 ? vec3(0.74, 0.73, 0.70) : r1 < 0.8 ? vec3(0.80, 0.76, 0.68) : vec3(0.63, 0.52, 0.46); }
  wallC = mix(wallC, tint, 0.14);
  o.spec = 0.0; o.emit = vec3(0.0); o.ao = 1.0; o.albedo = wallC;
  // every screen-space derivative and the texture sample are taken here, before the first branch
  vec2 pc = wpos.xz / vec2(1.1, 1.8), pw = fwidth(pc);
  float grainFade = saturate(1.25 - (pw.x + pw.y) * 1.1);
  float fh = H / max(floorsN, 1.0);
  float L = wall.y, m = min(0.55, L * 0.12);
  float nb = max(1.0, floor((L - 2.0 * m) / bw + 0.5));
  float ub = (wall.x - m) / max(L - 2.0 * m, 0.01) * nb;
  float vf = hy / fh;
  vec2 cell = vec2(ub, vf), cw = fwidth(cell);
  float rowW = fwidth(wpos.y / 0.24);
  bool sloped = n.y > 0.45 && n.y < 0.985, level = n.y >= 0.985;
  vec3 tng = vec3(-n.z, 0.0, n.x); tng = dot(tng, tng) > 1e-4 ? normalize(tng) : vec3(1.0, 0.0, 0.0);
  vec3 btn = cross(n, tng);
  vec2 metres = level ? wpos.xz : vec2(dot(wpos, tng), sloped ? wpos.y / max(sqrt(1.0 - n.y * n.y), 0.25) : wpos.y);
  float planted = step(r3, 0.14) * step(style, 4.5) * step(1.5, style);
  float layer = part > 3.5 ? 7.0 : (part > 2.5 || (sloped && style < 1.5 && style > 0.5)) ? roofL : part > 1.5 ? 3.0 : part > 0.5 ? wallL : (n.y > 0.45 || wall.y < 0.05) ? mix(5.0, 8.0, planted) : wallL;
  AMat M = AlatauMat(metres, layer);
  vec3 np = normalize(n + (M.nxy.x * tng + M.nxy.y * btn) * 0.85);
  float strength = AMatStrength[int(layer + 0.5)];
  float relief = saturate(1.0 + (0.5 + strength) * (dot(np, uSunDir) - dot(n, uSunDir))) * mix(1.0, M.ao, 0.3 + 0.4 * strength);
  vec3 surf = mix(vec3(1.0), M.pattern, strength) * relief;
  if (part > 3.5) {
    o.albedo = vec3(0.74, 0.72, 0.68) * surf * (n.y > 0.45 ? 1.0 : 0.82);
    o.ao = n.y > 0.45 ? mix(0.78, 1.0, saturate(abs(hy) * 4.0)) : 0.9; return o;
  }
  if (part > 0.5 && part < 1.5) {
    o.albedo = (n.y > 0.45 ? wallC * 0.90 + 0.07 : wallC * 0.97) * surf;
    o.ao = n.y > 0.45 ? 1.0 : 0.92; return o;
  }
  if (part > 1.5 && part < 2.5) {
    float lou = step(0.5, fract(wpos.y / 0.28)) * grainFade;
    o.albedo = n.y > 0.45 ? vec3(0.74, 0.77, 0.80) : vec3(0.66, 0.68, 0.70) * (0.94 + 0.06 * lou) * mix(1.0, relief, 0.5);
    o.spec = n.y > 0.45 ? 0.35 : 0.1; o.ao = 0.95; return o;
  }
  if (n.y > 0.45 || wall.y < 0.05) {
    vec3 roof = vec3(0.80, 0.80, 0.78);
    if (style < 1.5 && style > 0.5) roof = r2 < 0.45 ? vec3(0.52, 0.30, 0.24) : r2 < 0.8 ? vec3(0.33, 0.33, 0.35) : vec3(0.44, 0.36, 0.30);
    else if (style < 3.5 && style > 2.5) roof = vec3(0.72, 0.73, 0.74);
    else if (r3 < 0.14 && style < 4.5) roof = vec3(0.42, 0.52, 0.34);
    roof *= 1.0 + 0.07 * grainFade * (ANoise(wpos.xz * 0.35) * 0.5 + ANoise(wpos.xz * 1.7) * 0.5 - 0.5);
    roof *= surf;
    if (part > 2.5 && part < 3.5) roof = (r2 < 0.5 ? vec3(0.55, 0.31, 0.24) : r2 < 0.8 ? vec3(0.36, 0.36, 0.38) : vec3(0.47, 0.38, 0.31)) * surf;
    if ((style > 6.5 && style < 7.5) || (style > 4.5 && style < 5.5 && r3 < 0.35)) {
      float pcell = ABox(fract(pc) - 0.5, vec2(0.46, 0.46), pw);
      float pfade = saturate(1.3 - max(pw.x, pw.y) * 2.2);
      roof = mix(vec3(0.13, 0.17, 0.26), mix(vec3(0.62, 0.64, 0.66), vec3(0.06, 0.10, 0.20), pcell), pfade);
      o.spec = 0.5;
    }
    o.albedo = roof; return o;
  }
  vec2 id = floor(cell), q = fract(cell);
  float inWall = step(0.0, ub) * step(ub, nb);
  float top = H - hy;
  float ground = step(vf, 1.0) * gf;
  vec2 wc = vec2(0.5, sill + wh * 0.5), ws = vec2(ww, wh) * 0.5;
  if (ground > 0.5) { wc = vec2(0.5, 0.42); ws = vec2(0.44, 0.36); }
  float win = ABox(q - wc, ws, cw) * inWall * step(0.9, top);
  if (spandrel > 0.0 && ground < 0.5) {
    float band = saturate((q.y - spandrel) / max(cw.y, 1e-4) + 0.5);
    float bar0 = saturate((abs(q.x - 0.5) - (0.5 - mull)) / max(cw.x, 1e-4) + 0.5);
    win = band * (1.0 - bar0) * inWall * step(1.2, top);
  }
  float h = AHash2(id + seed * 91.0);
  float joint = (1.0 - saturate(q.y / max(cw.y * 1.5, 0.035))) * 0.10 + (1.0 - saturate(min(q.x, 1.0 - q.x) / max(cw.x * 1.5, 0.012))) * 0.05 * inWall;
  vec3 wallS = wallC * (1.0 - joint) * (1.0 + 0.07 * grainFade * (ANoise(vec2(wall.x * 0.7, hy * 0.7) + seed * 40.0) - 0.5)) * surf;
  if (style > 4.5 && style < 5.5) wallS *= 0.96 + 0.04 * step(0.5, fract(wall.x / 0.9));
  wallS = mix(wallS, wallC * 0.6, 0.5 * ground);
  wallS *= mix(0.80, 1.0, saturate(hy / 0.7));
  if (((style > 1.5 && style < 2.5) || (style > 7.5 && style < 8.5)) && ground < 0.5) {
    float bay = step(0.45, AHash1(id.x * 3.7 + seed * 57.0));
    float rail = ABox(q - vec2(0.5, sill * 0.55), vec2(ww * 0.5 + 0.08, sill * 0.42), cw) * inWall * bay * step(0.9, top);
    wallS = mix(wallS, wallC * 0.80 + 0.06, rail * 0.75);
  }
  vec3 glass = glassC * (0.75 + 0.5 * h);
  float blind = step(0.78, AHash2(id * 1.7 + seed * 13.0));
  glass = mix(glass, vec3(0.62, 0.60, 0.55), blind * 0.55);
  vec3 rdir = reflect(-view, n);
  float fres = 0.05 + 0.95 * pow(1.0 - saturate(dot(n, view)), 5.0);
  vec3 env = AlatauSky(rdir) * mix(0.50, 1.0, saturate(hy / 28.0));
  float mirror = spandrel > 0.0 ? 0.44 + 0.52 * fres : 0.24 + 0.68 * fres;
  vec3 refl = env * mirror * (1.0 - blind * 0.6);
  float lit = step(1.0 - (0.10 + 0.50 * uNight), AHash2(id * 2.3 + seed * 29.0)) * uNight;
  vec3 lamp = mix(vec3(1.0, 0.78, 0.46), vec3(1.0, 0.92, 0.74), AHash2(id * 5.1 + seed)) * lit * 1.35;
  float detail = saturate(1.35 - max(cw.x, cw.y) * 1.9);
  float share = saturate(spandrel > 0.0 ? (1.0 - spandrel) * (1.0 - 2.0 * mull) : 4.0 * ws.x * ws.y) * inWall;
  vec3 avgGlass = glassC + env * mirror * 0.85;
  if (spandrel <= 0.0) {
    vec2 fw = vec2(0.07 / bw, 0.07 / fh);
    float inner = ABox(q - wc, max(ws - fw, vec2(0.001)), cw) * inWall * step(0.9, top);
    float bar = ws.x * bw > 0.7 ? 1.0 - saturate((abs(q.x - wc.x) - 0.025 / bw) / max(cw.x, 1e-4) + 0.5) : 0.0;
    vec3 frameC = r2 < 0.55 ? vec3(0.93, 0.93, 0.92) : r2 < 0.8 ? vec3(0.24, 0.25, 0.27) : vec3(0.45, 0.33, 0.24);
    float head = saturate(1.0 - (wc.y + ws.y - q.y) / (0.16 * saturate(uSunDir.y * 2.0 + 0.3) + 1e-4));
    glass *= 1.0 - 0.45 * head * inner;
    glass = mix(glass, frameC, bar * inner * 0.9);
    glass = mix(frameC, glass, saturate(inner / max(win, 1e-3)));
    refl *= saturate(inner / max(win, 1e-3)) * (1.0 - bar) * (1.0 - 0.4 * head);
  }
  vec3 nearA = mix(wallS, glass, win), farA = mix(wallC * 0.96, glassC, share);
  o.albedo = mix(farA, nearA, detail);
  o.emit = mix(share * (avgGlass - glassC + vec3(1.0, 0.82, 0.55) * 0.42 * uNight * (0.10 + 0.50 * uNight)), win * (refl + lamp), detail);
  o.spec = mix(share, win, detail) * (1.0 - blind * detail);
  o.ao = mix(0.70, 1.0, smoothstep(0.0, 1.0, saturate(hy / 10.0)));
  return o;
}
`;
