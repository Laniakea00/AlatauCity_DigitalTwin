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

// The sky seen in direction d (unit). No sun disc: that is added by the sky shader only.
float3 AlatauSky(float3 d)
{
    float up = saturate(d.y);
    // warm haze at the horizon, a pale band above it, blue overhead
    float3 mid = lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.5) + 0.10 * (1.0 - _AlatauNight);
    float3 c = lerp(_AlatauSkyHorizon.rgb, mid, smoothstep(0.0, 0.16, up));
    c = lerp(c, _AlatauSkyZenith.rgb, smoothstep(0.10, 0.85, up));
    c = lerp(c, _AlatauSkyGround.rgb, saturate(-d.y * 5.0));
    float s = saturate(dot(d, _AlatauSunDir.xyz));
    c += _AlatauSunColor.rgb * (0.22 * pow(s, 6.0) + 0.5 * pow(s, 64.0)) * (1.0 - _AlatauNight);
    return c;
}

// Anti-aliased box: 1 inside |p| < half, 0 outside, with a soft edge of width aa.
float ABox(float2 p, float2 half_, float2 aa)
{
    float2 d = saturate((half_ - abs(p)) / max(aa, 1e-4) + 0.5);
    return d.x * d.y;
}

struct AFacade { float3 albedo; float3 emit; float spec; float ao; };

// style: 0 other, 1 house, 2 housing, 3 glass tower / office, 4 public, 5 industry, 6 podium / retail, 7 solar field, 8 resort, 9 existing
// wall = (metres along the wall from its start, wall length); hy = metres above the building's base; H = building height.
AFacade AlatauFacade(float2 wall, float hy, float H, float floorsN, float style, float seed, float3 tint, float3 n, float3 view, float3 wpos, float part)
{
    AFacade o;
    float r1 = AHash1(seed * 255.0 + 1.0), r2 = AHash1(seed * 255.0 + 7.0), r3 = AHash1(seed * 255.0 + 13.0);
    // ---- what the building is made of
    float3 wallC = float3(0.86, 0.85, 0.82); float3 glassC = float3(0.10, 0.14, 0.17);
    float bw = 3.4, ww = 0.52, wh = 0.50, sill = 0.30, spandrel = 0.0, mull = 0.0, gf = 1.0;      // bay width m, window share, sill share
    float wallL = 0.0, roofL = 5.0;                                                              // material layers of the wall and of the flat roof
    if (style < 1.5 && style > 0.5)       { wallL = r1 < 0.75 ? 0.0 : 2.0; roofL = r2 < 0.45 ? 4.0 : 10.0; bw = 3.8; ww = 0.34; wh = 0.42; sill = 0.34; gf = 0.0; wallC = r1 < 0.45 ? float3(0.90, 0.87, 0.80) : r1 < 0.75 ? float3(0.83, 0.74, 0.62) : float3(0.74, 0.50, 0.40); }
    else if (style < 2.5 && style > 1.5)  { wallL = r1 < 0.62 ? 0.0 : r1 < 0.80 ? 1.0 : r1 < 0.92 ? 2.0 : 1.0; bw = 3.3; ww = 0.50; wh = 0.52; sill = 0.28; wallC = r1 < 0.26 ? float3(0.91, 0.90, 0.87) : r1 < 0.46 ? float3(0.86, 0.79, 0.66) : r1 < 0.60 ? float3(0.78, 0.71, 0.60) : r1 < 0.74 ? float3(0.70, 0.71, 0.72) : r1 < 0.86 ? float3(0.72, 0.47, 0.35) : r1 < 0.94 ? float3(0.38, 0.40, 0.43) : float3(0.60, 0.66, 0.70); }
    else if (style < 3.5 && style > 2.5)
    {
        wallL = 1.0;
        glassC = r2 < 0.35 ? float3(0.10, 0.17, 0.24) : r2 < 0.60 ? float3(0.09, 0.19, 0.20) : r2 < 0.82 ? float3(0.15, 0.17, 0.19) : float3(0.22, 0.17, 0.11);
        if (r3 < 0.50)      { bw = 1.6; ww = 0.90; wh = 0.74; sill = 0.0; spandrel = 0.24; mull = 0.06; wallC = r1 < 0.78 ? float3(0.72, 0.76, 0.80) : float3(0.32, 0.35, 0.38); }     // glass curtain wall
        else if (r3 < 0.76) { bw = 3.0; ww = 0.76; wh = 0.70; sill = 0.15; wallC = r1 < 0.6 ? float3(0.92, 0.91, 0.88) : float3(0.80, 0.76, 0.69); }                                  // pale stone grid
        else                { bw = 1.2; ww = 0.90; wh = 0.80; sill = 0.0; spandrel = 0.18; mull = 0.17; wallC = r1 < 0.5 ? float3(0.90, 0.90, 0.89) : float3(0.60, 0.50, 0.40); }      // vertical fins
    }
    else if (style < 4.5 && style > 3.5)  { wallL = r1 < 0.5 ? 0.0 : r1 < 0.8 ? 1.0 : 2.0; bw = 4.8; ww = 0.72; wh = 0.64; sill = 0.20; wallC = r1 < 0.5 ? float3(0.89, 0.87, 0.82) : r1 < 0.8 ? float3(0.78, 0.76, 0.72) : float3(0.62, 0.48, 0.38); }
    else if (style < 5.5 && style > 4.5)  { wallL = 3.0; bw = 6.0; ww = 0.86; wh = 0.10; sill = 0.72; gf = 0.0; wallC = r1 < 0.5 ? float3(0.74, 0.76, 0.78) : r1 < 0.8 ? float3(0.83, 0.82, 0.79) : float3(0.45, 0.52, 0.60); }
    else if (style < 6.5 && style > 5.5)  { wallL = 1.0; bw = 6.0; ww = 0.86; wh = 0.66; sill = 0.08; wallC = float3(0.32, 0.33, 0.35); }
    else if (style < 8.5 && style > 7.5)  { wallL = r1 < 0.5 ? 0.0 : 11.0; bw = 3.6; ww = 0.56; wh = 0.56; sill = 0.26; wallC = r1 < 0.5 ? float3(0.92, 0.90, 0.85) : float3(0.66, 0.50, 0.36); }
    else if (style > 8.5)                 { wallL = r1 < 0.8 ? 0.0 : 2.0; roofL = r2 < 0.5 ? 4.0 : 10.0; bw = 3.4; ww = 0.40; wh = 0.44; sill = 0.32; gf = 0.0; wallC = r1 < 0.5 ? float3(0.74, 0.73, 0.70) : r1 < 0.8 ? float3(0.80, 0.76, 0.68) : float3(0.63, 0.52, 0.46); }
    wallC = lerp(wallC, tint, 0.14);

    o.spec = 0; o.emit = 0; o.ao = 1; o.albedo = wallC;
    // every screen-space derivative is taken here, before the first branch
    float2 pc = wpos.xz / float2(1.1, 1.8), pw = fwidth(pc);
    float grainFade = saturate(1.25 - (pw.x + pw.y) * 1.1);          // surface grain only where a pixel is smaller than about a metre
    float fh = H / max(floorsN, 1.0);
    float L = wall.y, m = min(0.55, L * 0.12);
    float nb = max(1.0, floor((L - 2.0 * m) / bw + 0.5));
    float ub = (wall.x - m) / max(L - 2.0 * m, 0.01) * nb;            // bay coordinate: integer = a bay line
    float vf = hy / fh;
    float2 cell = float2(ub, vf), cw = fwidth(cell);

    float rowW = fwidth(wpos.y / 0.24);                                // tile courses, for sloped roofs
    // the material photo of this face: walls are mapped along the wall and up, flat roofs from above, pitched roofs along the slope
    bool sloped = n.y > 0.45 && n.y < 0.985, flat = n.y >= 0.985;
    float3 tng = float3(-n.z, 0.0, n.x); tng = dot(tng, tng) > 1e-4 ? normalize(tng) : float3(1, 0, 0);
    float3 btn = cross(n, tng);
    float2 metres = flat ? wpos.xz : float2(dot(wpos, tng), sloped ? wpos.y / max(sqrt(1.0 - n.y * n.y), 0.25) : wpos.y);
    float planted = step(r3, 0.14) * step(style, 4.5) * step(1.5, style);
    float layer = part > 3.5 ? 7.0 : part > 2.5 || (sloped && style < 1.5 && style > 0.5) ? roofL : part > 1.5 ? 3.0 : part > 0.5 ? wallL : (n.y > 0.45 || wall.y < 0.05) ? lerp(5.0, 8.0, planted) : wallL;
    AMat M = AlatauMat(metres, layer);
    float3 np = normalize(n + (M.nxy.x * tng + M.nxy.y * btn) * 0.85);
    float strength = AMatStrength[(int)layer];
    float relief = saturate(1.0 + (0.5 + strength) * (dot(np, _AlatauSunDir.xyz) - dot(n, _AlatauSunDir.xyz))) * lerp(1.0, M.ao, 0.3 + 0.4 * strength);
    float3 surf = lerp(float3(1, 1, 1), M.pattern, strength) * relief;      // multiply a palette colour by this
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
        // flat roofs seen from above: dark membranes, grey gravel and a few pale ones, as on any real city from the air
        float3 roof = r2 < 0.30 ? float3(0.46, 0.47, 0.48) : r2 < 0.62 ? float3(0.62, 0.62, 0.60) : r2 < 0.88 ? float3(0.76, 0.76, 0.74) : float3(0.38, 0.39, 0.41);
        if (style < 1.5 && style > 0.5) roof = r2 < 0.45 ? float3(0.52, 0.30, 0.24) : r2 < 0.8 ? float3(0.33, 0.33, 0.35) : float3(0.44, 0.36, 0.30);
        else if (style < 3.5 && style > 2.5) roof = r2 < 0.5 ? float3(0.56, 0.57, 0.58) : float3(0.40, 0.41, 0.43);
        else if (style > 4.5 && style < 5.5) roof = r2 < 0.5 ? float3(0.62, 0.64, 0.66) : float3(0.48, 0.50, 0.52);      // metal roofs of plants and warehouses
        else if (r3 < 0.14 && style < 4.5) roof = float3(0.42, 0.52, 0.34);                                    // planted roof
        roof *= 1.0 + 0.07 * grainFade * (ANoise(wpos.xz * 0.35) * 0.5 + ANoise(wpos.xz * 1.7) * 0.5 - 0.5);
        roof *= surf;
        if ((part > 2.5 && part < 3.5) || (style < 1.5 && style > 0.5))
        {
            // tiles on pitched roofs: courses along the slope, each a little different
            if (part > 2.5) roof = r2 < 0.5 ? float3(0.55, 0.31, 0.24) : r2 < 0.8 ? float3(0.36, 0.36, 0.38) : float3(0.47, 0.38, 0.31);
            float course = frac(wpos.y / 0.24), tfade = saturate(1.3 - rowW * 2.0) * step(n.y, 0.985);
            roof *= 1.0 - (1.0 - _AlatauMatOn) * tfade * (0.16 * smoothstep(0.75, 1.0, course) - 0.05 * AHash1(floor(wpos.y / 0.24) + seed * 31.0));
        }
        if ((style > 6.5 && style < 7.5) || (style > 4.5 && style < 5.5 && r3 < 0.35))
        {
            // photovoltaic panels: dark blue cells with a pale grid
            float pcell = ABox(frac(pc) - 0.5, float2(0.46, 0.46), pw);
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
    // window opening
    float2 wc = float2(0.5, sill + wh * 0.5), ws = float2(ww, wh) * 0.5;
    if (ground > 0.5) { wc = float2(0.5, 0.42); ws = float2(0.44, 0.36); }
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
    float joint = (1.0 - saturate(q.y / max(cw.y * 1.5, 0.035))) * 0.10 + (1.0 - saturate(min(q.x, 1.0 - q.x) / max(cw.x * 1.5, 0.012))) * 0.05 * inWall;
    float3 wallS = wallC * (1.0 - joint) * (1.0 + 0.07 * grainFade * (ANoise(float2(wall.x * 0.7, hy * 0.7) + seed * 40.0) - 0.5)) * surf;
    if (style > 4.5 && style < 5.5) wallS *= 0.96 + 0.04 * step(0.5, frac(wall.x / 0.9));               // cladding sheets
    wallS = lerp(wallS, wallC * 0.6, 0.5 * ground);                                                    // darker frame at street level
    wallS *= lerp(0.80, 1.0, saturate(hy / 0.7));                                                      // plinth
    // balconies on housing: a pale slab edge and a glass rail under some windows
    if ((style > 1.5 && style < 2.5 || style > 7.5 && style < 8.5) && ground < 0.5)
    {
        float bay = step(0.45, AHash1(id.x * 3.7 + seed * 57.0));
        float rail = ABox(q - float2(0.5, sill * 0.55), float2(ww * 0.5 + 0.08, sill * 0.42), cw) * inWall * bay * step(0.9, top);
        wallS = lerp(wallS, wallC * 0.80 + 0.06, rail * 0.75);
    }
    // glass: tinted, some panes with blinds, reflecting the sky
    float3 glass = glassC * (0.75 + 0.5 * h);
    float blind = step(0.78, AHash2(id * 1.7 + seed * 13.0));
    glass = lerp(glass, float3(0.62, 0.60, 0.55), blind * 0.55);
    float3 rdir = reflect(-view, n);
    float fres = 0.05 + 0.95 * pow(1.0 - saturate(dot(n, view)), 5.0);
    // glass mirrors the sky; low down it mirrors the street and the buildings opposite, which are darker
    float3 env = AlatauSky(rdir) * lerp(0.50, 1.0, saturate(hy / 28.0));
    float mirror = spandrel > 0.0 ? 0.44 + 0.52 * fres : 0.24 + 0.68 * fres;
    float3 refl = env * mirror * (1.0 - blind * 0.6);
    float lit = step(1.0 - (0.10 + 0.50 * _AlatauNight), AHash2(id * 2.3 + seed * 29.0)) * _AlatauNight;
    float3 lamp = lerp(float3(1.0, 0.78, 0.46), float3(1.0, 0.92, 0.74), AHash2(id * 5.1 + seed)) * lit * 1.35;

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
        float3 frameC = r2 < 0.55 ? float3(0.93, 0.93, 0.92) : r2 < 0.8 ? float3(0.24, 0.25, 0.27) : float3(0.45, 0.33, 0.24);
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
    float3 glowE = avgGlass - glassC + float3(1.0, 0.82, 0.55) * 0.42 * _AlatauNight * (0.10 + 0.50 * _AlatauNight);
    o.albedo = lerp(lerp(farA, rowA, rowDetail), nearA, detail);
    o.emit = lerp(lerp(share * glowE, bandY * hsh * glowE, rowDetail), win * (refl + lamp), detail);
    o.spec = lerp(share, win, detail) * (1.0 - blind * detail);
    o.ao = lerp(0.70, 1.0, smoothstep(0.0, 1.0, saturate(hy / 10.0)));                                  // walls darken towards the ground
    return o;
}
#endif

// ---- landmark plots (LandmarkSystem.BuildPadMask): 1 where a landmark stands — line layers and film roads are not drawn there
sampler2D _AlatauPadTex; float _AlatauPadOn;
float AlatauOnPad(float3 wpos)
{
    if (_AlatauPadOn < 0.5) return 0.0;
    float2 uv = float2(2.29357798e-5 * wpos.x + 0.5, 1.62074554e-5 * wpos.z + 0.491085899);
    return tex2Dlod(_AlatauPadTex, float4(uv, 0, 0)).r;
}
