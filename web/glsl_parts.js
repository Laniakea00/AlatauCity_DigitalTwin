// ---- the ground: the plan appears where and when the city is built; blocks, verges, lawns, water (AlatauGround.shader)
const GLSL_GROUND = `
{
  // beyond the edge of the model the same code runs on the blurred colour of the map's edge
  vec2 uvr = vUvM, uvm = clamp(uvr, 0.003, 0.997);
  float outK = max(max(-uvr.x, uvr.x - 1.0), max(-uvr.y, uvr.y - 1.0)), away = smoothstep(-0.02, 0.004, outK);
  vec3 plan = mix(texture(tPlan, uvm).rgb, textureLod(tPlan, uvm, 7.0).rgb, away), nat = mix(texture(tNat, uvm).rgb, textureLod(tNat, uvm, 6.0).rgb, away);
  float dev = YearEff(texture(tDev, uvm).r * 255.0 * (1.0 - away) + 2000.0);
  float yNow = YearNow();
  float prep = saturate((yNow - (dev - 2.5)) / 1.2), done = saturate((yNow - (dev - 0.6)) / 0.8);
  vec3 c = mix(nat, mix(nat, vec3(0.55, 0.49, 0.40), 0.45), prep * (1.0 - done));
  c = mix(c, plan, done);
  float lakeW = saturate((c.b - c.r) * 5.0 - 0.6) * saturate((c.g - c.r) * 8.0 + 0.3);
  float shore = 1.0 - smoothstep(0.03, 0.12, outK + (ANoise(vWp.xz * 0.00025) - 0.5) * 0.08);
  c = mix(c, uEdgeCol, lakeW * (1.0 - shore) * away);
  vec3 c0 = plan;
  float lum = dot(c, vec3(0.299, 0.587, 0.114)), sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
  float water = saturate((c.b - c.r) * 5.0 - 0.6) * saturate((c.g - c.r) * 8.0 + 0.3);
  float green = saturate((c.g - max(c.r, c.b)) * 6.0) * (1.0 - water);
  float open = saturate((0.50 - lum) * 5.0) * saturate(1.0 - sat * 7.0) * (1.0 - water);
  float n1 = ANoise(vWp.xz * 0.045), n2 = ANoise(vWp.xz * 0.011 + 7.0), n3 = ANoise(vWp.xz * 0.9);
  vec3 f = mix(vec3(lum), c, 0.42);
  f = mix(f, vec3(0.80, 0.78, 0.73), 0.30) + (1.0 - lum) * 0.10;
  f = mix(f, mix(vec3(0.61, 0.61, 0.52), vec3(0.70, 0.68, 0.59), n2) * (0.94 + 0.12 * n1), open * 0.72);
  f = mix(f, mix(vec3(0.36, 0.48, 0.27), vec3(0.48, 0.57, 0.33), n1) * (0.94 + 0.12 * n2), green * 0.85);
  f *= 0.975 + 0.03 * n1 + 0.02 * n3;
  vec3 pg = AlatauMat(vWp.xz, 8.0).pattern, ps = AlatauMat(vWp.xz, 9.0).pattern, pp = AlatauMat(vWp.xz, 7.0).pattern;
  float built = saturate(1.0 - green - open - water);
  f *= mix(vec3(1.0), pg, green * 0.75) * mix(vec3(1.0), ps, open * 0.55) * mix(vec3(1.0), pp, built * 0.45);
  // city blocks: metres from the edge of the nearest road corridor, negative inside the corridor
  float sd = mix((texture(tBlocks, uvm).r * 255.0 - 128.0) * 0.5, 63.5, away), sw = max(fwidth(sd), 0.02);
  float inBlock = saturate(sd / sw + 0.5), walk = inBlock * saturate((3.2 - sd) / sw + 0.5), kerb = saturate(1.0 - abs(sd - 0.15) / max(sw, 0.25));
  float town = done * saturate((48.0 - sd) / 8.0) * (1.0 - water);
  vec3 verge = mix(vec3(0.40, 0.50, 0.30), vec3(0.47, 0.55, 0.33), n1) * mix(vec3(1.0), pg, 0.7);
  vec3 paved = vec3(0.74, 0.72, 0.68) * mix(vec3(1.0), pp, 0.75);
  float resid = saturate((min(c0.r, c0.g) - c0.b) * 6.0), indus = saturate((min(c0.r, c0.b) - c0.g) * 8.0), civic = saturate(1.0 - resid - indus);
  float patch_ = smoothstep(0.45, 0.62, ANoise(vWp.xz * 0.02 + 11.0));
  vec3 lawn = mix(vec3(0.43, 0.52, 0.32), vec3(0.50, 0.57, 0.35), n1) * mix(vec3(1.0), pg, 0.7);
  vec3 yard = vec3(0.62, 0.62, 0.61) * mix(vec3(1.0), pp, 0.6);
  vec3 inside = lawn * resid + mix(paved, lawn, patch_ * 0.8) * civic + yard * indus;
  f = mix(f, inside, done * (1.0 - water) * inBlock * (1.0 - green) * (1.0 - open) * 0.82);
  f = mix(f, verge, town * (1.0 - inBlock) * step(-40.0, sd));
  f = mix(f, paved, town * walk * 0.9);
  f *= 1.0 - 0.30 * kerb * town * saturate(1.6 - sw * 2.0);
  f = mix(f, mix(vec3(dot(f, vec3(0.299, 0.587, 0.114))), f, 0.35) * 0.92, uTint);       // analysis: the ground is muted, the buildings carry the colour
  vec3 viewG = normalize(uCamU - vWp);
  float fresG = 0.04 + 0.96 * pow(1.0 - saturate(viewG.y), 5.0);
  vec3 rdirG = reflect(-viewG, normalize(vec3((n1 - 0.5) * 0.04, 1.0, (n3 - 0.5) * 0.04)));
  f = mix(f, vec3(0.10, 0.19, 0.25), water);
  diffuseColor.rgb = f;
  filmEmit = f * (0.06 + 0.08 * uSunCol * uSunInt) + f * AmbTri(normalize(vNu)) + AlatauSky(rdirG) * (0.18 + 0.75 * fresG) * water;
}
`;

// ---- buildings: the year filter and the growth of the timeline, then the facade (AlatauLit.shader, film branch)
const GLSL_BUILDING = `
{
  float bidB = max(floor(vInfo.y + 0.5), 0.0);
  ivec2 tc = ivec2(int(mod(bidB, 256.0)), int(bidB / 256.0));
  vec4 geo = texelFetch(tGeo, tc, 0), g2B = texelFetch(tGeo2, tc, 0); float seedB = g2B.r;
  float yearB = (vInfo.y > -0.5 && g2B.g > 0.5) ? g2B.g : vInfo.x;                       // the year of completion in the chosen scenario
  float partB = vWall.y < -0.5 ? floor(-vWall.y + 0.5) : 0.0;
  vec3 nW = normalize(cross(dFdx(vWp), dFdy(vWp))); vec3 viewB = normalize(uCamU - vWp); if (dot(nW, viewB) < 0.0) nW = -nW;
  AFacade F = AlatauFacade(vWall, vWp.y - geo.x, max(geo.y, 3.0), max(geo.z, 1.0), geo.w, seedB, vColor.rgb, nW, viewB, vWp, partB);
  bool growB = uGrow > 0.5 && yearB > 2025.5;
  if (growB) {
    float prog = saturate(uYearF + 1.0 - yearB);
    if (uYearF + 1.0 - yearB < 0.0) discard;
    if (geo.x + max(geo.y, 4.0) * prog + 0.3 + step(0.999, prog) * 60.0 - vWp.y < 0.0) discard;
  } else if (yearB > uYear + 0.5) discard;
  vec3 aB = F.albedo, emB = F.emit;
  if (growB) { float fresh = saturate(1.6 - (uYearF + 1.0 - yearB)); aB = mix(aB, vec3(1.0, 0.74, 0.42), 0.6 * fresh); emB += aB * 0.25 * fresh; }
  if (uTint > 0.5) {                                                                    // analysis: colour by building, the rest fades to grey
    vec4 tnB = texelFetch(tTint, tc, 0); float g0B = dot(aB, vec3(0.299, 0.587, 0.114));
    aB = mix(mix(vec3(g0B), aB, 0.25) * 0.95, tnB.rgb, tnB.a); emB = emB * (1.0 - tnB.a) + aB * 0.16 * tnB.a;
  }
  if (abs(bidB - uSel) < 0.5 && vInfo.y > -0.5) { aB = mix(aB, vec3(0.85, 0.27, 0.94), 0.5); emB += vec3(0.85, 0.27, 0.94) * 0.22; }       // the selected building
  vec3 ambB = mix(uGnd * 0.62, mix(uHor, uZen, 0.5), nW.y * 0.5 + 0.5) * 0.58 * F.ao;
  diffuseColor.rgb = aB; filmEmit = emB + aB * ambB; filmSpec = F.spec * 0.07;
}
`;

// ---- roads (AlatauRoad.shader)
const GLSL_ROAD = `
{
  float x = vRoad.x, v = vRoad.y, hw = vDims.x, lanes = max(vDims.w, 1.0), lenR = vDims.z;
  float ax = abs(x), xw = fwidth(x);
  vec3 pa = AlatauMat(vWp.xz, 6.0).pattern, pp = AlatauMat(vWp.xz, 7.0).pattern;
  if (vYearR > YearNow() + 0.5) discard;
  vec3 c;
  if (vDims.y > 0.5) {
    c = vec3(0.43, 0.44, 0.46) * mix(vec3(1.0), pa, 0.8) * (0.96 + 0.06 * ANoise(vWp.xz * 0.08));
    float lw = hw / lanes;
    float fade = saturate(1.5 - xw * 5.0) * smoothstep(6.0, 14.0, v) * smoothstep(6.0, 14.0, lenR - v);
    float dash = step(fract(v / 8.0), 0.38);
    float centre = lanes > 1.5 ? ALine(ax - 0.20, 0.08, xw) : ALine(x, 0.08, xw) * dash;
    float sep = ALine((fract(ax / lw + 0.5) - 0.5) * lw, 0.07, xw) * dash * step(lw * 0.5, ax) * step(ax, hw - lw * 0.5);
    float edge = ALine(ax - (hw - 0.30), 0.07, xw);
    c = mix(c, vec3(0.93, 0.93, 0.91), saturate(centre + sep + edge) * fade * 0.9);
  } else {
    c = vec3(0.70, 0.68, 0.64) * mix(vec3(1.0), pp, 0.7);
    c *= 1.0 - 0.25 * ALine(ax - (hw + 0.12), 0.12, xw) * saturate(1.5 - xw * 3.0);
  }
  diffuseColor.rgb = c; filmEmit = c * AmbTri(vec3(0.0, 1.0, 0.0));
}
`;

// ---- trees and hedges (AlatauTree.shader)
const GLSL_TREE = `
{
  if (YearNow() - YearEff(vYearT) + 0.2 < 0.0) discard;
  vec3 aT = vColor.rgb * vTint;
  diffuseColor.rgb = aT * 0.8; filmEmit = aT * AmbTri(normalize(vNu)) + aT * 0.22 * uSunCol * uSunInt;
}
`;

// ---- sky (AlatauSky.shader)
const GLSL_SKY = `
varying vec3 vDir;
void main() {
  vec3 d = normalize(vDir);
  vec3 c = AlatauSky(d);
  float s = saturate(dot(d, uSunDir));
  c += uSunCol * (smoothstep(0.99965, 0.99985, s) * 3.0 + pow(s, 900.0) * 0.8) * (1.0 - uNight) * step(-0.02, d.y);
  vec2 p = d.xz / max(d.y + 0.12, 0.05) * 1.3;
  float cl = ANoise(p * 0.9 + 3.1) * 0.55 + ANoise(p * 2.3) * 0.30 + ANoise(p * 5.1) * 0.15;
  cl = smoothstep(0.56, 0.86, cl) * smoothstep(0.02, 0.22, d.y) * 0.45;
  c = mix(c, mix(uHor, vec3(1.0), 0.55) * (1.0 - 0.75 * uNight) + uSunCol * 0.12 * (1.0 - uNight), cl);
  // the Trans-Ili Alatau to the south: a stylised ridge with snow, standing in the haze (not survey data)
  float az = atan(d.x, -d.z);
  float ridge = (0.010 + 0.034 * ANoise(vec2(az * 4.0, 1.7)) + 0.016 * ANoise(vec2(az * 13.0, 9.2)) + 0.006 * ANoise(vec2(az * 47.0, 4.1))) * (1.0 - smoothstep(0.45, 1.35, abs(az)));
  float e = d.y, aa = fwidth(e) + 1e-4;
  float m = saturate((ridge - e) / aa + 0.5) * step(-0.01, e);
  float hgt = saturate(e / max(ridge, 1e-3));
  float snowLine = 0.50 + 0.22 * ANoise(vec2(az * 31.0, 2.0));
  float snow = saturate((hgt - snowLine) / 0.06) * step(0.022, ridge);
  vec3 rock = mix(uHor, vec3(0.27, 0.34, 0.48), 0.30 + 0.45 * hgt);
  vec3 mnt = mix(rock, mix(vec3(0.90, 0.93, 0.98), uSunCol, 0.25), snow) * (1.0 - 0.70 * uNight);
  c = mix(c, mnt, m);
  gl_FragColor = vec4(c, 1.0);
}
`;

// ---- picture finish (AlatauFilmPost.shader): occlusion from depth, then depth of field and the grade
const GLSL_POST_COMMON = `
uniform sampler2D tColor; uniform sampler2D tDepth; uniform sampler2D tAO;
uniform vec4 uProj; uniform vec2 uNF; uniform vec2 uPx; uniform vec4 uDof; uniform float uFog, uTime, uExp;
varying vec2 vUv;
#define saturate(a) clamp(a, 0.0, 1.0)
float Eye(vec2 uv) { float ndc = textureLod(tDepth, uv, 0.0).x * 2.0 - 1.0; return 2.0 * uNF.x * uNF.y / (uNF.y + uNF.x - ndc * (uNF.y - uNF.x)); }
vec3 VPos(vec2 uv) { float z = Eye(uv); return vec3((uv * 2.0 - 1.0) * uProj.xy * z, z); }
`;
const GLSL_POST_AO = GLSL_POST_COMMON + `
void main() {
  vec3 P = VPos(vUv);
  if (P.z > uNF.y * 0.9) { gl_FragColor = vec4(1.0); return; }
  vec3 r = VPos(vUv + vec2(uPx.x, 0.0)) - P, l = P - VPos(vUv - vec2(uPx.x, 0.0)), u = VPos(vUv + vec2(0.0, uPx.y)) - P, d = P - VPos(vUv - vec2(0.0, uPx.y));
  vec3 n = normalize(cross(abs(u.z) < abs(d.z) ? u : d, abs(r.z) < abs(l.z) ? r : l));
  float R = uProj.z, ry = clamp(R / (uProj.y * P.z) * 0.5, 2.5 * uPx.y, 0.09);
  vec2 ruv = vec2(ry * uPx.x / uPx.y, ry);
  float rnd = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) * 6.2831853, occ = 0.0;
  for (int k = 0; k < 12; k++) {
    float a = rnd + float(k) * 2.39996, s = (float(k) + 0.5) / 12.0;
    vec3 v = VPos(vUv + vec2(cos(a), sin(a)) * s * ruv) - P;
    float vv = dot(v, v) + 1e-4;
    occ += saturate(dot(v, n) / sqrt(vv) - 0.12) * saturate(1.0 - vv / (R * R));
  }
  float fog = exp(-pow(P.z * uFog, 2.0));
  gl_FragColor = vec4(vec3(1.0 - saturate(occ / 12.0 * uProj.w) * fog), 1.0);
}
`;
const GLSL_POST = GLSL_POST_COMMON + `
void main() {
  vec4 c0 = texture2D(tColor, vUv);
  float z = Eye(vUv);
  float coc = saturate((abs(z - uDof.x) - uDof.y) / max(uDof.y * 2.2, 1.0)) * uDof.z * uDof.w;
  vec3 c = c0.rgb;
  if (coc >= 0.35) {
    vec4 sum = c0; float w = 1.0;
    for (int k = 0; k < 16; k++) {
      float a = float(k) * 2.39996, s = sqrt((float(k) + 0.5) / 16.0);
      vec2 o = vec2(cos(a), sin(a)) * s * coc * uPx;
      float zk = Eye(vUv + o);
      float ck = saturate((abs(zk - uDof.x) - uDof.y) / max(uDof.y * 2.2, 1.0)) * uDof.z;
      float wk = zk < z - 0.02 * z ? saturate(ck / max(coc, 0.01)) : 1.0;
      sum += textureLod(tColor, vUv + o, 0.0) * wk; w += wk;
    }
    c = sum.rgb / w;
  }
  vec2 a2 = uPx * 3.0;
  float ao = (texture2D(tAO, vUv).r * 2.0 + texture2D(tAO, vUv + vec2(a2.x, 0.0)).r + texture2D(tAO, vUv - vec2(a2.x, 0.0)).r + texture2D(tAO, vUv + vec2(0.0, a2.y)).r + texture2D(tAO, vUv - vec2(0.0, a2.y)).r) / 6.0;
  c *= mix(vec3(0.52, 0.56, 0.66), vec3(1.0), ao) * mix(0.86, 1.0, ao);
  c *= 1.06 * mix(uExp, 1.0, max(step(uNF.y * 0.98, z), 1.0 - exp(-pow(z * uFog, 2.0))));
  vec3 hi = max(c - 0.62, 0.0) / 0.38;
  c = min(c, 0.62) + 0.38 * (1.0 - exp(-hi));
  c = (c - 0.46) * 1.10 + 0.46;
  float lum = dot(c, vec3(0.299, 0.587, 0.114));
  c = mix(vec3(lum), c, 1.04);
  c *= mix(vec3(0.955, 0.99, 1.045), vec3(1.035, 1.0, 0.955), smoothstep(0.15, 0.85, lum));
  vec2 q = vUv - 0.5;
  c *= 1.0 - 0.30 * smoothstep(0.25, 0.95, dot(q, q) * 2.2);
  c += (fract(sin(dot(gl_FragCoord.xy + uTime, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.012;
  gl_FragColor = vec4(saturate(c), 1.0);
}
`;
