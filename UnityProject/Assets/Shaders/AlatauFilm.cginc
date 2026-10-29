// Shared by the film look: the sky as a function of direction (drawn by AlatauCity/Sky, reflected by glass and water),
// small hash helpers, and the facade generator that turns a plain building box into floors, bays and windows.
// Globals are set by FilmLook.cs. The project is in gamma colour space: every colour here is a display value.
#ifndef ALATAU_FILM_INCLUDED
#define ALATAU_FILM_INCLUDED

float _AlatauFilm;            // 0 = the plain maket look, 1 = film look
float _AlatauNight;           // 0 day .. 1 night: windows light up
float4 _AlatauSunDir;         // direction TO the sun (world)
float4 _AlatauSunColor, _AlatauSkyZenith, _AlatauSkyHorizon, _AlatauSkyGround;

// material photo textures (layer order = file prefix in Assets/Textures/Materials):
// 0 plaster  1 concrete  2 brick  3 profiled metal  4 clay tiles  5 bitumen  6 asphalt  7 paving  8 grass  9 dry grass  10 grey tiles  11 planks
UNITY_DECLARE_TEX2DARRAY(_AlatauMatA);
UNITY_DECLARE_TEX2DARRAY(_AlatauMatD);
float4 _AlatauMatMean[16];
float _AlatauMatOn;           // 1 when the arrays are loaded
static const float AMatSize[12] = { 2.4, 3.0, 1.5, 2.6, 2.2, 3.0, 4.0, 2.4, 2.6, 3.4, 2.2, 2.0 };      // metres one tile covers
static const float AMatStrength[12] = { 0.35, 0.40, 0.95, 0.55, 0.95, 0.60, 0.80, 0.70, 0.80, 0.70, 0.95, 0.90 };   // how much of the photo's pattern shows

struct AMat { float3 pattern; float3 colour; float2 nxy; float ao; };
// pattern = the photo divided by its average colour (1 = average), so it can shade any palette colour; nxy = surface normal x, y
AMat AlatauMat(float2 metres, float layer)
{
    AMat m; float3 uv = float3(metres / AMatSize[(int)layer], layer);
    float4 a = UNITY_SAMPLE_TEX2DARRAY(_AlatauMatA, uv), d = UNITY_SAMPLE_TEX2DARRAY(_AlatauMatD, uv);
    m.colour = a.rgb; m.pattern = lerp(float3(1, 1, 1), a.rgb / max(_AlatauMatMean[(int)layer].rgb, 0.04), _AlatauMatOn);
    m.nxy = (d.rg * 2.0 - 1.0) * _AlatauMatOn; m.ao = lerp(1.0, d.b, _AlatauMatOn);
    return m;
}

float AHash1(float n) { return frac(sin(n * 127.1) * 43758.5453); }
float AHash2(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
float ANoise(float2 p)
{
    float2 i = floor(p), f = frac(p); f = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(AHash2(i), AHash2(i + float2(1, 0)), f.x), lerp(AHash2(i + float2(0, 1)), AHash2(i + float2(1, 1)), f.x), f.y);
}

// The photographed sky (FilmLook: Resources/Film/Gate/AlatauSkyDome, the upper half of a CC0 Poly Haven HDRI, its sun turned to
// the left edge): u = azimuth from the sun, v = elevation (0 horizon .. 1 zenith). _AlatauSkyTexOn = how much of it shows (0 at dusk and
// night, when the gradient alone is right). Read with an explicit level: no derivatives, safe inside branches.
sampler2D _AlatauSkyTex; float _AlatauSkyTexOn;
float3 AlatauSkyPhoto(float3 d, float lod, out float w)
{
    float el = asin(saturate(d.y)) * 0.63661977;
    float az = (atan2(d.x, d.z) - atan2(_AlatauSunDir.x, _AlatauSunDir.z)) * 0.15915494;
    w = _AlatauSkyTexOn * smoothstep(0.0, 0.09, d.y);
    return tex2Dlod(_AlatauSkyTex, float4(az, max(el, 0.004), 0, lod)).rgb;
}

// The sky seen in direction d (unit), lod = level of the photo (0 sharp for the sky itself, higher = rougher reflections).
// No sun disc: that is added by the sky shader only.
float3 AlatauSkyLod(float3 d, float lod)
{
    float up = saturate(d.y);
    // warm haze at the horizon, a pale band above it, blue overhead
    float3 mid = lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.5) + 0.10 * (1.0 - _AlatauNight);
    float3 c = lerp(_AlatauSkyHorizon.rgb, mid, smoothstep(0.0, 0.16, up));
    c = lerp(c, _AlatauSkyZenith.rgb, smoothstep(0.10, 0.85, up));
    // by day the photographed sky with its clouds over the gradient; the haze band at the horizon stays the gradient (= the fog)
    float w; float3 ph = AlatauSkyPhoto(d, lod, w);
    c = lerp(c, ph, w);
    c = lerp(c, _AlatauSkyGround.rgb, saturate(-d.y * 5.0));
    float s = saturate(dot(d, _AlatauSunDir.xyz));
    c += _AlatauSunColor.rgb * (0.22 * pow(s, 6.0) + 0.5 * pow(s, 64.0)) * (1.0 - _AlatauNight) * (1.0 - 0.65 * w) * (lod > 0.5 ? 0.45 : 1.0);     // the photo has its own glow; reflections take less of it (no white-out of a whole facade)
    return c;
}
// what glass and water reflect: a slightly softened sky
float3 AlatauSky(float3 d) { return AlatauSkyLod(d, 1.0); }

// Anti-aliased box: 1 inside |p| < half, 0 outside, with a soft edge of width aa.
float ABox(float2 p, float2 half_, float2 aa)
{
    float2 d = saturate((half_ - abs(p)) / max(aa, 1e-4) + 0.5);
    return d.x * d.y;
}

struct AFacade { float3 albedo; float3 emit; float spec; float ao; };

// Which way each building is turned (BuildingChunk.cs, bid → r = angle / 90° + 0.5, a = 1 when known): roof membranes, plant,
// solar rows and metal ribs run along the building. Read by AlatauLit and passed to AlatauFacade as roofRot = (cos, sin, known).
sampler2D _AlatauRoofTex; float _AlatauRoofOn;

// Roof plant of one grid cell (metres in the building's frame): a box with a darker top grille or a fan, and its shadow on the roof.
// c = cell size, dens = share of cells with a unit, sz = (smallest, extra) half size, sh = shadow offset in this frame, aa = metres per pixel.
float4 ARoofUnits(float2 p, float2 c, float dens, float2 sz, float2 sh, float aa, float salt)
{
    float2 id = floor(p / c), q = p - (id + 0.5) * c;
    float h0 = AHash2(id + salt), h1 = AHash2(id * 1.31 + salt + 3.7), h2 = AHash2(id * 0.77 + salt + 9.1);
    float2 hs = sz.x + sz.y * float2(h1, h2);
    hs = min(hs, c * 0.5 - 0.6);
    float2 off = (float2(h2, h1) - 0.5) * max(c - 2.0 * hs - 1.2, 0.0);
    float on = step(h0, dens);
    float box = ABox(q - off, hs, float2(aa, aa)) * on;
    float shd = ABox(q + sh - off, hs, float2(aa, aa)) * on * (1.0 - box);
    // a fan on the condensers, a grille on the air handlers
    float fan = step(0.5, h1) * (1.0 - saturate((length(q - off) - min(hs.x, hs.y) * 0.62) / max(aa, 1e-3) + 0.5));
    return float4(box, shd, fan * box, h0 / max(dens, 1e-3));
}

// style: 0 other, 1 house, 2 housing, 3 glass tower / office, 4 public, 5 industry, 6 podium / retail, 7 solar field, 8 resort, 9 existing,
// 10 the presentation model around Iconic (light stone and white panel, real glazing, a darker plinth with shopfronts, planted roofs)
// wall = (metres along the wall from its start, wall length); hy = metres above the building's base; H = building height;
// roofRot = (cos, sin, 1 when known) of the building's turn.
AFacade AlatauFacade(float2 wall, float hy, float H, float floorsN, float style, float seed, float3 tint, float3 n, float3 view, float3 wpos, float part, float3 roofRot)
{
    AFacade o;
    float r1 = AHash1(seed * 255.0 + 1.0), r2 = AHash1(seed * 255.0 + 7.0), r3 = AHash1(seed * 255.0 + 13.0), r4 = AHash1(seed * 255.0 + 19.0);
    bool maket = style > 9.5;
    bool tallM = maket && H >= 42.0;
    // ---- what the building is made of
    float3 wallC = float3(0.86, 0.85, 0.82); float3 glassC = float3(0.10, 0.14, 0.17);
    float bw = 3.4, ww = 0.52, wh = 0.50, sill = 0.30, spandrel = 0.0, mull = 0.0, gf = 1.0;      // bay width m, window share, sill share
    float wallL = 0.0, roofL = 5.0;                                                              // material layers of the wall and of the flat roof
    float occ = 0.42;                                                                            // share of windows lit at night
    if (style < 1.5 && style > 0.5)       { wallL = r1 < 0.75 ? 0.0 : 2.0; roofL = r2 < 0.45 ? 4.0 : 10.0; bw = 3.8; ww = 0.34; wh = 0.42; sill = 0.34; gf = 0.0; occ = 0.5; wallC = r1 < 0.45 ? float3(0.90, 0.87, 0.80) : r1 < 0.75 ? float3(0.83, 0.74, 0.62) : float3(0.74, 0.50, 0.40); }
    else if (style < 2.5 && style > 1.5)  { wallL = r1 < 0.62 ? 0.0 : r1 < 0.80 ? 1.0 : r1 < 0.92 ? 2.0 : 1.0; bw = 3.3; ww = 0.50; wh = 0.52; sill = 0.28; occ = 0.46; wallC = r1 < 0.26 ? float3(0.91, 0.90, 0.87) : r1 < 0.46 ? float3(0.86, 0.79, 0.66) : r1 < 0.60 ? float3(0.78, 0.71, 0.60) : r1 < 0.74 ? float3(0.70, 0.71, 0.72) : r1 < 0.86 ? float3(0.72, 0.47, 0.35) : r1 < 0.94 ? float3(0.38, 0.40, 0.43) : float3(0.60, 0.66, 0.70); }
    else if (style < 3.5 && style > 2.5)
    {
        wallL = 1.0; occ = 0.30;
        glassC = r2 < 0.35 ? float3(0.10, 0.17, 0.24) : r2 < 0.60 ? float3(0.09, 0.19, 0.20) : r2 < 0.82 ? float3(0.15, 0.17, 0.19) : float3(0.22, 0.17, 0.11);
        if (r3 < 0.50)      { bw = 1.6; ww = 0.90; wh = 0.74; sill = 0.0; spandrel = 0.24; mull = 0.06; wallC = r1 < 0.78 ? float3(0.72, 0.76, 0.80) : float3(0.32, 0.35, 0.38); }     // glass curtain wall
        else if (r3 < 0.76) { bw = 3.0; ww = 0.76; wh = 0.70; sill = 0.15; wallC = r1 < 0.6 ? float3(0.92, 0.91, 0.88) : float3(0.80, 0.76, 0.69); }                                  // pale stone grid
        else                { bw = 1.2; ww = 0.90; wh = 0.80; sill = 0.0; spandrel = 0.18; mull = 0.17; wallC = r1 < 0.5 ? float3(0.90, 0.90, 0.89) : float3(0.60, 0.50, 0.40); }      // vertical fins
    }
    else if (style < 4.5 && style > 3.5)  { wallL = r1 < 0.5 ? 0.0 : r1 < 0.8 ? 1.0 : 2.0; bw = 4.8; ww = 0.72; wh = 0.64; sill = 0.20; occ = 0.22; wallC = r1 < 0.5 ? float3(0.89, 0.87, 0.82) : r1 < 0.8 ? float3(0.78, 0.76, 0.72) : float3(0.62, 0.48, 0.38); }
    else if (style < 5.5 && style > 4.5)  { wallL = 3.0; bw = 6.0; ww = 0.86; wh = 0.10; sill = 0.72; gf = 0.0; occ = 0.12; wallC = r1 < 0.5 ? float3(0.74, 0.76, 0.78) : r1 < 0.8 ? float3(0.83, 0.82, 0.79) : float3(0.45, 0.52, 0.60); }
    else if (style < 6.5 && style > 5.5)  { wallL = 1.0; bw = 6.0; ww = 0.86; wh = 0.66; sill = 0.08; occ = 0.5; wallC = float3(0.32, 0.33, 0.35); }
    else if (style < 8.5 && style > 7.5)  { wallL = r1 < 0.5 ? 0.0 : 11.0; bw = 3.6; ww = 0.56; wh = 0.56; sill = 0.26; occ = 0.5; wallC = r1 < 0.5 ? float3(0.92, 0.90, 0.85) : float3(0.66, 0.50, 0.36); }
    else if (maket)
    {
        // the presentation model's district, finished: towers of glass in a white frame or a light stone grid with tall windows,
        // mid-rise housing of light stone and white panel with loggias; all of it on a darker stone plinth with shopfronts
        wallL = 0.0; gf = 1.0; occ = 0.40;
        if (tallM && r1 < 0.55)      { bw = 1.5; ww = 0.90; wh = 0.78; sill = 0.0; spandrel = 0.20; mull = 0.075; occ = 0.32; wallL = 1.0; glassC = r2 < 0.5 ? float3(0.09, 0.14, 0.19) : float3(0.11, 0.16, 0.17); wallC = float3(0.90, 0.90, 0.88); }
        else if (tallM)              { bw = 3.0; ww = 0.68; wh = 0.76; sill = 0.12; occ = 0.38; wallL = 1.0; glassC = float3(0.11, 0.15, 0.19); wallC = r2 < 0.5 ? float3(0.91, 0.90, 0.87) : float3(0.87, 0.84, 0.78); }
        else                         { bw = 3.2; ww = 0.50 + 0.08 * r2; wh = 0.58; sill = 0.26; glassC = float3(0.13, 0.17, 0.21); wallC = r1 < 0.40 ? float3(0.92, 0.91, 0.88) : r1 < 0.75 ? float3(0.88, 0.85, 0.78) : float3(0.84, 0.85, 0.85); }
    }
    else if (style > 8.5)                 { wallL = r1 < 0.8 ? 0.0 : 2.0; roofL = r2 < 0.5 ? 4.0 : 10.0; bw = 3.4; ww = 0.40; wh = 0.44; sill = 0.32; gf = 0.0; occ = 0.45; wallC = r1 < 0.5 ? float3(0.74, 0.73, 0.70) : r1 < 0.8 ? float3(0.80, 0.76, 0.68) : float3(0.63, 0.52, 0.46); }
    wallC = lerp(wallC, tint, maket ? 0.0 : 0.14);
    bool housing = (style > 1.5 && style < 2.5) || (style > 7.5 && style < 8.5) || (maket && !tallM);

    o.spec = 0; o.emit = 0; o.ao = 1; o.albedo = wallC;
    // every screen-space derivative is taken here, before the first branch
    float2 pc = wpos.xz / float2(1.1, 1.8), pw = fwidth(pc);
    float grainFade = saturate(1.25 - (pw.x + pw.y) * 1.1);          // surface grain only where a pixel is smaller than about a metre
    float2 rl = float2(dot(wpos.xz, roofRot.xy), dot(wpos.xz, float2(-roofRot.y, roofRot.x)));     // metres in the building's own frame
    float mpp = max(length(fwidth(wpos.xz)) * 0.75, 1e-3);           // metres per pixel on a roof
    float fh = H / max(floorsN, 1.0);
    float L = wall.y, m = min(0.55, L * 0.12);
    float nb = max(1.0, floor((L - 2.0 * m) / bw + 0.5));
    float ub = (wall.x - m) / max(L - 2.0 * m, 0.01) * nb;            // bay coordinate: integer = a bay line
    float vf = hy / fh;
    float2 cell = float2(ub, vf), cw = fwidth(cell);
    float mppW = max(cw.x * (L - 2.0 * m) / nb, 1e-3);                // metres per pixel along the wall

    float rowW = fwidth(wpos.y / 0.24);                                // tile courses, for sloped roofs
    // the material photo of this face: walls are mapped along the wall and up, flat roofs from above (along the building), pitched roofs along the slope
    bool sloped = n.y > 0.45 && n.y < 0.985, flat = n.y >= 0.985;
    float3 tng = float3(-n.z, 0.0, n.x); tng = dot(tng, tng) > 1e-4 ? normalize(tng) : float3(1, 0, 0);
    float3 btn = cross(n, tng);
    float2 metres = flat ? rl : float2(dot(wpos, tng), sloped ? wpos.y / max(sqrt(1.0 - n.y * n.y), 0.25) : wpos.y);
    // ---- the kind of flat roof: 0 pale membrane, 1 gravel, 2 dark bitumen, 3 planted, 4 metal sheet
    float planted = maket ? step(floorsN, 14.5) * step(r3, 0.45) : step(r3, 0.14) * step(style, 4.5) * step(1.5, style);
    float rk = planted > 0.5 ? 3.0 : (style > 4.5 && style < 5.5) ? (r2 < 0.7 ? 4.0 : 0.0) : r2 < 0.38 ? 0.0 : r2 < 0.70 ? 1.0 : 2.0;
    float flatL = rk > 3.5 ? 3.0 : rk > 2.5 ? 8.0 : rk > 0.5 && rk < 1.5 ? 1.0 : 5.0;
    float layer = part > 3.5 ? 7.0 : part > 2.5 || (sloped && style < 1.5 && style > 0.5) ? roofL : part > 1.5 ? 3.0 : part > 0.5 ? wallL : (n.y > 0.45 || wall.y < 0.05) ? flatL : wallL;
    AMat M = AlatauMat(metres, layer);
    float3 np = normalize(n + (M.nxy.x * tng + M.nxy.y * btn) * 0.85);
    float strength = AMatStrength[(int)layer];
    float relief = saturate(1.0 + (0.5 + strength) * (dot(np, _AlatauSunDir.xyz) - dot(n, _AlatauSunDir.xyz))) * lerp(1.0, M.ao, 0.3 + 0.4 * strength);
    float3 surf = lerp(float3(1, 1, 1), M.pattern, strength) * relief;      // multiply a palette colour by this
    // aviation obstruction lights: red, on the top corners of everything taller than 75 m, from dusk on (slow pulse)
    float avR = max(0.55, 1.8 * mppW);
    float avC = (1.0 - saturate((min(wall.x, L - wall.x) - avR) / max(mppW, 1e-3) + 0.5));
    float aviation = step(75.0, H) * _AlatauNight * (0.65 + 0.35 * sin(_Time.y * 2.1 + seed * 40.0)) * avC * step(6.0, L);
    float3 avE = float3(1.0, 0.07, 0.03) * 5.0 * aviation;
    // ---- what AlatauRoofs put on the roof
    if (part > 3.5)
    {
        // paved plinth around the building
        o.albedo = float3(0.74, 0.72, 0.68) * surf * (n.y > 0.45 ? 1.0 : 0.82);
        o.ao = n.y > 0.45 ? lerp(0.78, 1.0, saturate(abs(hy) * 4.0)) : 0.9; return o;
    }
    if (part > 0.5 && part < 1.5)
    {
        // parapet, crown, stair head: the wall material without windows, a paler coping on top
        o.albedo = (n.y > 0.45 ? wallC * 0.90 + 0.07 : wallC * 0.97) * surf;
        o.emit = avE * step(H - 0.5, hy) * step(hy, H + 4.0) * step(n.y, 0.45);
        o.ao = n.y > 0.45 ? 1.0 : 0.92; return o;
    }
    if (part > 1.5 && part < 2.5)
    {
        // plant and roof lights: pale metal with louvre lines, glassy tops on the long roof lights
        float lou = step(0.5, frac(wpos.y / 0.28)) * grainFade;
        o.albedo = n.y > 0.45 ? float3(0.74, 0.77, 0.80) : float3(0.66, 0.68, 0.70) * (0.94 + 0.06 * lou) * lerp(1.0, relief, 0.5);
        o.spec = n.y > 0.45 ? 0.35 : 0.1; o.ao = 0.95; return o;
    }
    // ---- roofs and other faces that are not walls
    if (n.y > 0.45 || wall.y < 0.05)
    {
        // flat roofs seen from above, by kind: pale membranes with welded seams, grey gravel, dark bitumen, planted roofs with paths,
        // metal sheet on sheds; on top the plant of a real roof (condensers, air handlers) with their shadows, solar rows on public
        // and industrial roofs, water stains
        float3 roof = rk < 0.5 ? (r4 < 0.5 ? float3(0.78, 0.78, 0.76) : float3(0.70, 0.71, 0.71))
                    : rk < 1.5 ? float3(0.60, 0.58, 0.54) * (0.94 + 0.12 * r4)
                    : rk < 2.5 ? float3(0.36, 0.36, 0.38) * (0.92 + 0.16 * r4)
                    : rk < 3.5 ? float3(0.36, 0.44, 0.27) * (0.85 + 0.3 * ANoise(rl * 0.21))
                    : (r4 < 0.6 ? float3(0.64, 0.66, 0.68) : float3(0.50, 0.53, 0.56));
        if (style < 1.5 && style > 0.5) roof = r2 < 0.45 ? float3(0.52, 0.30, 0.24) : r2 < 0.8 ? float3(0.33, 0.33, 0.35) : float3(0.44, 0.36, 0.30);
        else if (style < 3.5 && style > 2.5 && rk < 2.5) roof = r2 < 0.5 ? float3(0.62, 0.63, 0.64) : float3(0.44, 0.45, 0.47);
        float nearR = saturate(1.6 - mpp * 0.9);                                   // roof detail where a pixel is under about a metre and a half
        float midR = saturate(2.2 - mpp * 0.35);                                   // plant boxes stay readable up to ~5 m per pixel
        float knownR = roofRot.z;
        roof *= 1.0 + 0.07 * grainFade * (ANoise(rl * 0.35) * 0.5 + ANoise(rl * 1.7) * 0.5 - 0.5);
        // membrane seams every 1.9 m, gravel stops at the edges of the sheets, ribs of metal sheet every 0.9 m
        float seam = rk < 0.5 ? 1.0 - saturate(abs(frac(rl.y / 1.9) - 0.5) * 1.9 / max(mpp, 1e-3) - 0.06 / max(mpp, 1e-3)) : 0.0;
        float rib = rk > 3.5 ? 0.5 + 0.5 * cos(rl.y * 6.98) : 0.5;
        roof *= 1.0 - 0.10 * seam * nearR * knownR;
        roof *= lerp(1.0, 0.90 + 0.2 * rib, nearR * knownR * step(3.5, rk));
        // planted roof: beds of sedum in several greens and a russet, gravel paths between them
        if (rk > 2.5 && rk < 3.5)
        {
            float2 bc = rl / float2(11.0, 8.0), bq = frac(bc) - 0.5; float bh = AHash2(floor(bc) + seed * 17.0);
            float bed = ABox(bq, float2(0.41, 0.38), float2(mpp / 11.0, mpp / 8.0));
            float3 sedum = bh < 0.5 ? float3(0.34, 0.43, 0.26) : bh < 0.8 ? float3(0.42, 0.46, 0.30) : float3(0.47, 0.37, 0.28);
            roof = lerp(roof, lerp(lerp(sedum * 1.15, float3(0.66, 0.65, 0.61), nearR), sedum * (0.85 + 0.3 * ANoise(rl * 0.6)), bed), knownR * midR);      // paths read only up close
        }
        roof *= surf;
        if ((part > 2.5 && part < 3.5) || (style < 1.5 && style > 0.5))
        {
            // tiles on pitched roofs: courses along the slope, each a little different
            if (part > 2.5) roof = r2 < 0.5 ? float3(0.55, 0.31, 0.24) : r2 < 0.8 ? float3(0.36, 0.36, 0.38) : float3(0.47, 0.38, 0.31);
            float course = frac(wpos.y / 0.24), tfade = saturate(1.3 - rowW * 2.0) * step(n.y, 0.985);
            roof *= 1.0 - (1.0 - _AlatauMatOn) * tfade * (0.16 * smoothstep(0.75, 1.0, course) - 0.05 * AHash1(floor(wpos.y / 0.24) + seed * 31.0));
        }
        else if (flat && knownR > 0.5 && !(style > 6.5 && style < 7.5))
        {
            // the sun's shadow of a 1.3 m box, in the building's frame
            float2 sd = float2(dot(_AlatauSunDir.xz, roofRot.xy), dot(_AlatauSunDir.xz, float2(-roofRot.y, roofRot.x))) / max(_AlatauSunDir.y, 0.3);
            float big = (style > 2.5 && style < 6.5) || maket ? 1.0 : 0.6;
            float densS = (rk > 2.5 && rk < 3.5) ? 0.10 : housing ? 0.22 : 0.40;
            float4 u1 = ARoofUnits(rl, float2(7.0, 6.0), densS, float2(0.55, 0.9), sd * 1.1, mpp, seed * 41.0);
            float4 u2 = ARoofUnits(rl + float2(3.1, 2.3), float2(23.0, 17.0), 0.55 * big, float2(1.3, 1.9), sd * 1.9, mpp, seed * 57.0 + 5.0);
            float3 unitC = float3(0.80, 0.81, 0.82) * (0.92 + 0.12 * u1.w);
            float3 ahuC = float3(0.72, 0.74, 0.75);
            float sdk = lerp(0.62, 0.80, saturate(1.0 - _AlatauSunDir.y));                 // the shadows soften as the sun gets low (and long)
            roof *= lerp(1.0, sdk, saturate(u1.y + u2.y) * midR);
            roof = lerp(roof, unitC * (1.0 - 0.55 * u1.z), u1.x * midR);
            roof = lerp(roof, ahuC * (1.0 - 0.10 * step(0.5, frac(rl.x / 0.6)) * nearR), u2.x * midR);
            // solar rows on public, retail and some industrial and office roofs: blocks of panels with walkways
            float pv = (style > 3.5 && style < 4.5 && r3 < 0.45) || (style > 5.5 && style < 6.5 && r3 < 0.55) || (style > 4.5 && style < 5.5 && r3 < 0.45) || (style > 2.5 && style < 3.5 && r3 > 0.8) ? 1.0 : 0.0;
            float2 pb = rl / float2(19.0, 14.0), pbq = frac(pb) - 0.5; float pbh = AHash2(floor(pb) + seed * 23.0);
            float block = ABox(pbq, float2(0.42, 0.40), float2(mpp / 19.0, mpp / 14.0)) * step(pbh, 0.8) * (1.0 - saturate(u2.x + u1.x));
            float rowp = frac(rl.y / 2.3), panel = saturate((0.72 - rowp) / max(mpp / 2.3, 1e-3) + 0.5) * saturate(rowp / max(mpp / 2.3, 1e-3) + 0.5);
            float3 pvC = lerp(float3(0.13, 0.17, 0.26), float3(0.10, 0.13, 0.22) + 0.06 * step(0.5, frac(rl.x / 1.05)), nearR);
            float pvMix = block * pv * lerp(0.72, panel, saturate(2.0 - mpp));
            roof = lerp(roof, pvC, pvMix);
            o.spec = 0.45 * pvMix;
            // water stains and patched repairs, tens of metres across
            roof *= 1.0 - 0.06 * smoothstep(0.55, 0.85, ANoise(rl * 0.07 + seed * 13.0)) * (1.0 - pvMix);
        }
        if ((style > 6.5 && style < 7.5) || (style > 4.5 && style < 5.5 && r3 < 0.35 && knownR < 0.5))
        {
            // photovoltaic fields (and sheds before the building frame is known): dark blue cells with a pale grid
            float2 pq = knownR > 0.5 ? rl / float2(1.1, 1.8) : pc;
            float pcell = ABox(frac(pq) - 0.5, float2(0.46, 0.46), pw);
            float pfade = saturate(1.3 - max(pw.x, pw.y) * 2.2);
            roof = lerp(float3(0.13, 0.17, 0.26), lerp(float3(0.62, 0.64, 0.66), float3(0.06, 0.10, 0.20), pcell), pfade);
            o.spec = 0.5;
        }
        o.albedo = roof; return o;
    }

    // ---- the wall: floors and bays
    float2 id = floor(cell), q = frac(cell);
    float inWall = step(0.0, ub) * step(ub, nb);
    float top = H - hy;
    float ground = step(vf, 1.0) * gf;                                   // street level of buildings that have one
    // long housing blocks are built in sections: each its own shade, some in a second colour of the scheme
    float secL = 16.0 + 10.0 * r3, sec = floor(wall.x / secL), sh = AHash1(sec * 7.3 + seed * 113.0);
    float3 alt = r4 < 0.5 ? float3(0.80, 0.72, 0.60) : r4 < 0.8 ? float3(0.66, 0.67, 0.68) : float3(0.74, 0.55, 0.45);
    if (housing && L > 34.0)
    {
        wallC *= 0.95 + 0.10 * sh;
        if (sh > 0.78 && !maket) wallC = lerp(wallC, alt, 0.75);
    }
    // window opening
    float2 wc = float2(0.5, sill + wh * 0.5), ws = float2(ww, wh) * 0.5;
    if (ground > 0.5) { wc = float2(0.5, 0.44); ws = float2(0.46, 0.38); }          // shopfronts and lobbies
    float win = ABox(q - wc, ws, cw) * inWall * step(0.9, top);
    // curtain wall: glass from slab to slab with a spandrel band and thin mullions
    if (spandrel > 0.0 && ground < 0.5)
    {
        float band = saturate((q.y - spandrel) / max(cw.y, 1e-4) + 0.5);
        float bar = saturate((abs(q.x - 0.5) - (0.5 - mull)) / max(cw.x, 1e-4) + 0.5);
        win = band * (1.0 - bar) * inWall * step(1.2, top);
    }
    float h = AHash2(id + seed * 91.0);
    // wall surface: slab lines, bay joints, a little unevenness, a darker plinth
    float joint = (1.0 - saturate(q.y / max(cw.y * 1.5, 0.035))) * (maket ? 0.16 : 0.10) + (1.0 - saturate(min(q.x, 1.0 - q.x) / max(cw.x * 1.5, 0.012))) * 0.05 * inWall;
    float3 wallS = wallC * (1.0 - joint) * (1.0 + 0.07 * grainFade * (ANoise(float2(wall.x * 0.7, hy * 0.7) + seed * 40.0) - 0.5)) * surf;
    if (style > 4.5 && style < 5.5) wallS *= 0.96 + 0.04 * step(0.5, frac(wall.x / 0.9));               // cladding sheets
    // street level: shopfronts in a dark frame under a canopy band (the darker stone plinth of the model district)
    float3 plinthC = maket ? float3(0.34, 0.33, 0.32) : wallC * 0.6;
    wallS = lerp(wallS, plinthC * surf, (maket ? 0.92 : 0.5) * ground);
    float canopy = ground * saturate((q.y - 0.86) / max(cw.y, 1e-4) + 0.5) * saturate((0.95 - q.y) / max(cw.y, 1e-4) + 0.5) * step(1.5, style) * step(style, 2.5 + 8.0 * step(9.5, style));
    wallS = lerp(wallS, float3(0.20, 0.21, 0.22), canopy * 0.85);
    wallS *= lerp(0.80, 1.0, saturate(hy / 0.7));                                                      // plinth
    // housing, offices of stone and public buildings stand on a socle of darker stone; housing has a pale cornice band under the roof
    float hyW = max(cw.y * fh, 0.01);
    float soc = (1.0 - saturate((hy - 0.75) / hyW + 0.5)) * step(1.5, style) * step(style, 4.5) * step(spandrel, 0.0);
    float cor = saturate((hy - (H - 0.55)) / hyW + 0.5) * (step(1.5, style) * step(style, 2.5) + step(9.5, style)) * step(6.0, H);
    wallS = lerp(wallS, wallC * float3(0.50, 0.49, 0.48) * surf, soc);
    wallS = lerp(wallS, wallC * 0.90 + 0.08, cor);
    win *= 1.0 - max(soc, max(cor, canopy));
    // balconies and loggias on housing: a pale slab edge, a glass or metal rail and the shade of the recess around the window
    if (housing && ground < 0.5)
    {
        float bay = step(maket ? 0.30 : 0.45, AHash1(id.x * 3.7 + seed * 57.0));
        float rail = ABox(q - float2(0.5, sill * 0.55), float2(ww * 0.5 + 0.08, sill * 0.42), cw) * inWall * bay * step(0.9, top);
        float recess = ABox(q - wc, ws + float2(0.06, 0.05), cw) * inWall * bay * step(0.9, top) * (1.0 - win);
        wallS = lerp(wallS, wallS * 0.72, recess * 0.6);
        wallS = lerp(wallS, wallC * 0.80 + 0.06, rail * 0.75);
    }
    // glass: tinted, some panes with blinds, reflecting the sky; no two panes lie in quite the same plane, so their reflections differ
    float3 glass = glassC * (0.75 + 0.5 * h);
    float blind = step(0.78, AHash2(id * 1.7 + seed * 13.0));
    glass = lerp(glass, float3(0.62, 0.60, 0.55), blind * 0.55);
    float2 tilt = (float2(h, AHash2(id * 3.1 + seed * 7.0)) - 0.5) * (spandrel > 0.0 ? 0.035 : 0.06);
    float3 nG = normalize(n + tng * tilt.x + float3(0, tilt.y, 0));
    float3 rdir = reflect(-view, nG);
    float fres = 0.05 + 0.95 * pow(1.0 - saturate(dot(nG, view)), 5.0);
    // glass mirrors the sky; low down it mirrors the street and the buildings opposite, which are darker
    float3 env = AlatauSky(rdir) * lerp(0.50, 1.0, saturate(hy / 28.0));
    float mirror = spandrel > 0.0 ? 0.44 + 0.52 * fres : 0.24 + 0.68 * fres;
    mirror *= maket ? 1.12 : 1.0;
    float3 refl = env * mirror * (1.0 - blind * 0.6);
    // ---- windows at night: not every one and not all alike. Homes warm, offices a cooler white floor by floor, some rooms with
    // only a television's blue or a lamp behind curtains, shops at street level bright; each building its own share
    // each building its own share but never a dark block: homes about 40-60 % of the windows, offices 15-30 % (whole floors),
    // public and industrial buildings fewer but never none
    float bOcc = max(occ, 0.30) * 1.08 * (0.80 + 0.40 * r4);
    float floorOn = step(AHash2(float2(id.y, seed * 61.0)), 0.55);                                    // offices: whole floors lit or dark
    float pick = AHash2(id * 2.3 + seed * 29.0);
    float office = (style > 2.5 && style < 3.5) || (tallM && r1 < 0.55) ? 1.0 : 0.0;
    float litP = lerp(bOcc, bOcc * 1.5 * floorOn, office);
    litP = ground > 0.5 ? 0.88 : litP;
    float lit = step(pick, litP * saturate(_AlatauNight * 1.6)) * _AlatauNight;
    float kind = AHash2(id * 5.1 + seed);
    float3 lampC = kind < 0.55 ? float3(1.0, 0.74, 0.42) : kind < 0.80 ? float3(1.0, 0.88, 0.70) : kind < 0.93 ? float3(0.82, 0.90, 1.0) : float3(0.55, 0.62, 0.95);
    lampC = lerp(lampC, float3(0.88, 0.94, 1.0), office * 0.7);
    lampC = lerp(lampC, float3(1.0, 0.86, 0.62), ground);
    float bright = (0.55 + 0.8 * AHash2(id * 7.7 + seed * 3.0)) * (kind > 0.93 ? 0.45 : 1.0) * (ground > 0.5 ? 1.6 : 1.0);
    float3 lamp = lampC * lit * bright * 1.3;

    // when a window is smaller than about a pixel and a half, show the average of wall and glass instead of noise
    float detail = saturate(1.35 - max(cw.x, cw.y) * 1.9);
    float share = saturate(spandrel > 0.0 ? (1.0 - spandrel) * (1.0 - 2.0 * mull) : 4.0 * ws.x * ws.y) * inWall;
    float3 avgGlass = glassC + env * mirror * 0.85;
    // punched windows get a frame, a centre bar and a shadow under the lintel, so they sit in the wall instead of on it
    if (spandrel <= 0.0)
    {
        float2 fw = float2(0.07 / bw, 0.07 / fh);
        float inner = ABox(q - wc, max(ws - fw, 0.001), cw) * inWall * step(0.9, top);
        float bar = ws.x * bw > 0.7 ? 1.0 - saturate((abs(q.x - wc.x) - 0.025 / bw) / max(cw.x, 1e-4) + 0.5) : 0.0;
        float3 frameC = maket ? (r2 < 0.6 ? float3(0.30, 0.31, 0.33) : float3(0.86, 0.86, 0.85)) : r2 < 0.55 ? float3(0.93, 0.93, 0.92) : r2 < 0.8 ? float3(0.24, 0.25, 0.27) : float3(0.45, 0.33, 0.24);
        float head = saturate(1.0 - (wc.y + ws.y - q.y) / (0.16 * saturate(_AlatauSunDir.y * 2.0 + 0.3)));          // deeper shadow with a higher sun
        glass *= 1.0 - 0.45 * head * inner;
        glass = lerp(glass, frameC, bar * inner * 0.9);
        glass = lerp(frameC, glass, saturate(inner / max(win, 1e-3)));
        refl *= saturate(inner / max(win, 1e-3)) * (1.0 - bar) * (1.0 - 0.4 * head);
    }
    float3 nearA = lerp(wallS, glass, win), farA = lerp(wallC * 0.96, glassC, share);
    // middle distance: the bays are too small to draw but the floors are not, so the window rows show as bands — a building reads
    // as a building from a kilometre away instead of a plain box
    float rowDetail = saturate(1.35 - cw.y * 1.9);
    float bandY = (spandrel > 0.0 ? saturate((q.y - spandrel) / max(cw.y, 1e-4) + 0.5) : saturate((ws.y - abs(q.y - wc.y)) / max(cw.y, 1e-4) + 0.5)) * inWall * step(0.9, top);
    float hsh = spandrel > 0.0 ? 1.0 - 2.0 * mull : saturate(2.0 * ws.x);
    float3 rowA = lerp(wallS, lerp(wallS, glassC * (0.85 + 0.3 * h), hsh), bandY);
    // from afar the lit windows of a floor merge: a glow per floor that varies from floor to floor (and is brighter at street level)
    float floorGlow = (0.55 + 0.9 * AHash2(float2(id.y * 1.7, seed * 37.0))) * lerp(1.0, 2.0 * floorOn, office) * (ground > 0.5 ? 2.2 : 1.0);
    float3 glowE = avgGlass - glassC + lerp(float3(1.0, 0.80, 0.55), float3(0.92, 0.94, 1.0), office * 0.6) * 0.55 * _AlatauNight * bOcc * 1.3 * saturate(_AlatauNight * 1.6);
    float3 glowRow = avgGlass - glassC + (glowE - (avgGlass - glassC)) * floorGlow;
    o.albedo = lerp(lerp(farA, rowA, rowDetail), nearA, detail);
    o.emit = lerp(lerp(share * glowE, bandY * hsh * glowRow, rowDetail), win * (refl + lamp), detail);
    o.emit += avE * step(H - avR * 1.3, hy) * step(hy, H + 0.5) * step(H - 2.0 * fh, hy);      // only the top corners, never down a wall
    o.spec = lerp(share, win, detail) * (1.0 - blind * detail);
    o.ao = lerp(0.58, 1.0, smoothstep(0.0, 1.0, saturate(hy / 8.0)));                                   // walls darken towards the ground
    return o;
}
#endif

// ---- landmark plots (LandmarkSystem.BuildPadMask): 1 where a landmark stands — line layers and film roads are not drawn there
// _AlatauGate = (x, z, cos, sin of the yaw) of the Gate District round Iconic Complex (IconicDistrict), _AlatauGateOn = 1 while it
// stands, _AlatauGateTex its area (local frame, ± _AlatauGateHalf metres): inside it the district's own streets replace the city's
sampler2D _AlatauPadTex; float _AlatauPadOn; float4 _AlatauGate; float _AlatauGateOn, _AlatauGateHalf; sampler2D _AlatauGateTex;
// No early return inside the Gate test: compiled to WebGL that shape (a sampled branch whose result decides
// whether the pad texture is read) crashes Chrome's shader compiler on Windows (D3D11 GPU process stack overflow).
float AlatauOnPad(float3 wpos)
{
    float pad = 0.0;
    if (_AlatauPadOn > 0.5)
    {
        float2 uv = float2(2.29357798e-5 * wpos.x + 0.5, 1.62074554e-5 * wpos.z + 0.491085899);
        pad = tex2Dlod(_AlatauPadTex, float4(uv, 0, 0)).r;
    }
    if (_AlatauGateOn > 0.5)
    {
        float2 d = wpos.xz - _AlatauGate.xy;
        float2 l = float2(d.x * _AlatauGate.z - d.y * _AlatauGate.w, d.x * _AlatauGate.w + d.y * _AlatauGate.z);
        float2 g = l / (2.0 * _AlatauGateHalf) + 0.5;
        float inside = all(g > 0.0) && all(g < 1.0) ? 1.0 : 0.0;
        pad = max(pad, inside * step(0.5, tex2Dlod(_AlatauGateTex, float4(saturate(g), 0, 0)).r));
    }
    return pad;
}
