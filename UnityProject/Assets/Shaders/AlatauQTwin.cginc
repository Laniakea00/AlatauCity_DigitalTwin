// The surfaces of the QTwin page of Iconic Complex (QTwin_IconicComplex_AlatauCity.html), ported from its three.js shaders: the
// BIM model of the complex (tags 1–14) and the Gate District round it (tags 20–33). Material LM.QTwin of AlatauCity/Landmark,
// param = tag. Colours are worked out in linear light as on the page and turned into display values at the end (the project is
// in gamma colour space). Every derivative is taken by the caller before any branch and passed in.
#ifndef ALATAU_QTWIN_INCLUDED
#define ALATAU_QTWIN_INCLUDED

// a line every 'period' of v, w wide, anti-aliased; far away it fades to its average cover (no moiré)
float QLine(float v, float period, float w, float fwv)
{
    float d = abs(frac(v / period + 0.5) - 0.5) * period; float f = max(fwv, 1e-4);
    float l = 1.0 - smoothstep(w, w + f * 1.2, d);
    return lerp(l, min(2.0 * w / period, 1.0), smoothstep(period * 0.12, period * 0.45, f));
}
float QHash(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
float QNoise(float2 p)
{
    float2 i = floor(p), f = frac(p); f = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(QHash(i), QHash(i + float2(1, 0)), f.x), lerp(QHash(i + float2(0, 1)), QHash(i + float2(1, 1)), f.x), f.y);
}
float QFbm(float2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 4; i++) { s += a * QNoise(p); p = p * 2.03 + 17.1; a *= 0.5; } return s / 0.9375; }
// detail that fades to its mean where it gets smaller than a pixel (fwl = length of the footprint of a pixel in metres)
float QFine(float2 p, float sc, float fwl) { return lerp(QNoise(p * sc), 0.5, smoothstep(0.35, 1.0, fwl * sc)); }
float QMod2(float x) { return x - 2.0 * floor(x * 0.5); }

// a well kept lawn: two greens in broad soft patches, mowing stripes, a little dry grass, blades as fine grain
float3 QGrass(float2 p, float fwl)
{
    float n1 = QFbm(p / 16.0), n2 = QFbm(p / 5.0 + 11.0), g = QFine(p, 2.3, fwl);
    float3 c = lerp(float3(0.050, 0.085, 0.026), float3(0.085, 0.125, 0.038), smoothstep(0.25, 0.75, n1));
    c = lerp(c, float3(0.135, 0.140, 0.065), smoothstep(0.62, 0.86, n2) * 0.40);
    float st = 0.5 + 0.5 * sin(p.x * 0.55 + 0.25 * sin(p.y * 0.05));
    c *= 0.94 + 0.10 * smoothstep(0.3, 0.7, st);
    return c * (0.86 + 0.28 * g);
}
// concrete pavers, a slight tone from slab to slab
float3 QPavers(float2 p, float2 sz, float3 base, float2 fwp, float fwl)
{
    float2 q = p / sz; q.x += 0.5 * step(1.0, QMod2(floor(q.y)));
    float j = max(QLine(q.x, 1.0, 0.025, fwp.x / sz.x), QLine(q.y, 1.0, 0.04, fwp.y / sz.y));
    float h = QHash(floor(q) + 0.37);
    return base * (0.90 + 0.14 * h) * (1.0 - 0.28 * j) * (0.94 + 0.12 * QFine(p, 3.0, fwl));
}
// a light single-ply roof membrane: welded seams, faint stains
float3 QMembrane(float2 p, float2 fwp, float fwl)
{
    float n = QFbm(p / 7.0), s = QLine(p.x, 2.0, 0.025, fwp.x);
    return float3(0.42, 0.42, 0.40) * (0.93 + 0.10 * n) * (1.0 - 0.10 * s) * (0.96 + 0.08 * QFine(p, 1.5, fwl));
}
// a garden (a courtyard or a roof): lawn, soft beds of shrubs and perennials, winding paths, a paved patch here and there
float3 QGarden(float2 p, float2 fwp, float fwl)
{
    float3 c = QGrass(p, fwl);
    float sh = QFbm(p / 3.2 + 4.0);
    float3 shrub = float3(0.030, 0.070, 0.020) * (0.75 + 0.55 * QFine(p, 3.5, fwl));
    c = lerp(c, shrub, smoothstep(0.60, 0.70, sh));
    float2 fq = p * 4.0; float fc = QHash(floor(fq)); float far = smoothstep(0.25, 0.7, fwl * 4.0);
    float dt = 1.0 - smoothstep(0.18, 0.32, length(frac(fq) - 0.5));
    float3 flw = fc > 0.6 ? float3(0.55, 0.20, 0.32) : float3(0.62, 0.50, 0.14);
    c = lerp(c, flw, step(0.85, QHash(floor(fq) + 2.0)) * dt * smoothstep(0.56, 0.62, sh) * (1.0 - smoothstep(0.66, 0.7, sh)) * (1.0 - far) * 0.8);
    float w1 = QLine(p.x + 9.0 * sin(p.y / 27.0), 67.0, 0.75, fwp.x), w2 = QLine(p.y + 8.0 * sin(p.x / 23.0 + 1.3), 53.0, 0.75, fwp.y);
    float pv = smoothstep(0.80, 0.82, QFbm(p / 9.0 + 2.0));
    float3 pav = QPavers(p, float2(0.9, 0.45), float3(0.30, 0.28, 0.25), fwp, fwl);
    return lerp(c, pav, max(max(w1, w2), pv));
}

struct QSurf { float3 col; float rough; float metal; float3 emis; bool soft; };

// tag: the page's surface; pid: the building of the complex (1 T1, 2 T2, 3–4 pavilions, 5 plaza; 0 the district);
// u, y: facade metres along and up (y from the ground of the page); fu, fy: their screen derivatives; wp, fwp, fwl: plan metres and
// their footprint; no: normal; night 0 … 1; clad: the facade is on at this height (else the bare frame shows, drawn by the caller)
QSurf QTwinSurface(int tg, int pid, float u, float y, float fu, float fy, float2 wp, float2 fwp, float fwl, float3 no, float night)
{
    QSurf o; o.col = float3(0.40, 0.395, 0.38); o.rough = 0.85; o.metal = 0.0; o.emis = 0; o.soft = false;
    if (tg < 20)
    {
        // ---------------- the complex
        if (tg == 1 || tg == 8 || tg == 4)
        {
            if (tg == 4)
            {
                // the crown: frosted gold glass lit from inside, a little brighter towards the tip
                o.col = float3(0.92, 0.80, 0.58); o.rough = 0.3; o.metal = 0.2;
                o.emis = float3(1.0, 0.66, 0.30) * (0.5 + 1.3 * night) * (0.8 + 0.4 * smoothstep(240.0, 272.0, y));
            }
            else if (tg == 8)
            {
                // a shop front: bronze mullions every 2.4 m, a transom, the lit room behind
                float mul = max(QLine(u, 2.4, 0.05, fu), QLine(y - 0.2, 4.6, 0.12, fy));
                float bay = floor(u / 2.4), lv = floor((y - 0.2) / 4.6), fyy = frac((y - 0.2) / 4.6);
                float hb = QHash(float2(bay, lv + pid * 3.0));
                float3 room = lerp(float3(0.20, 0.13, 0.08), float3(0.42, 0.30, 0.18), hb) * (0.6 + 0.6 * smoothstep(0.55, 0.95, fyy));
                room *= 0.75 + 0.5 * step(0.5, frac(u / 0.8 + hb)) * step(fyy, 0.35);
                float3 refl = lerp(float3(0.05, 0.06, 0.07), float3(0.20, 0.23, 0.26), smoothstep(0.2, 1.0, fyy));
                o.col = lerp(lerp(refl, room * 0.5, 0.5), float3(0.34, 0.25, 0.15), mul);
                o.rough = lerp(0.04, 0.35, mul); o.metal = lerp(0.05, 0.8, mul);
                o.emis = room * float3(1.0, 0.80, 0.55) * (0.55 + 2.2 * night) * (1.0 - mul);
            }
            else
            {
                // the towers: warm low-iron glass, the rooms behind it lit gold, the diamond lattice of the physical model
                float mul = QLine(u, 1.5, 0.025, fu);
                float fh = pid == 1 ? 4.3 : 3.8;
                float cellF = floor((y - 0.3) / fh), cellU = floor(u / 4.5);
                float warm = 0.7 + 0.6 * QHash(float2(cellU, cellF * 1.3 + pid * 7.0));
                float s = pid == 1 ? 0.62 : 0.9, per = pid == 1 ? 15.0 : 9.0;
                float lat = max(QLine(u + y * s, per, 0.18, fu + fy * s), QLine(u - y * s, per, 0.18, fu + fy * s));
                o.col = lerp(float3(0.10, 0.07, 0.035), float3(0.86, 0.56, 0.20), max(mul * 0.7, lat));
                o.rough = lerp(0.08, 0.3, max(mul, lat)); o.metal = lerp(0.75, 0.95, lat);
                o.emis = float3(1.0, 0.58, 0.22) * ((0.035 + 0.65 * night) * warm * (1.0 - mul) + lat * (0.06 + 1.1 * night));
            }
        }
        if (tg == 2)
        {
            if (pid <= 2)
            {
                // the slab edges of the towers: champagne-gold anodised aluminium, a lit soffit under every slab
                o.col = no.y > 0.5 ? float3(0.60, 0.44, 0.24) : no.y < -0.5 ? float3(0.90, 0.68, 0.38) : float3(0.82, 0.54, 0.20);
                o.rough = no.y < -0.5 ? 0.6 : 0.28; o.metal = no.y < -0.5 ? 0.0 : 0.85;
                if (no.y < -0.5) o.emis = float3(1.0, 0.66, 0.32) * (0.16 + 0.75 * night);
                else if (abs(no.y) < 0.5) o.emis = float3(1.0, 0.64, 0.30) * (0.05 + 0.22 * night);
            }
            else
            {
                o.col = no.y > 0.5 ? float3(0.55, 0.52, 0.47) : float3(0.82, 0.72, 0.56); o.rough = 0.40; o.metal = 0.35;
                if (no.y < -0.5) o.emis = float3(1.0, 0.80, 0.55) * night * 1.1;
            }
        }
        if (tg == 3)
        {
            // the golden fins: every fin darker at its edges, so the zigzag reads
            float rib = 0.55 + 0.45 * sin(saturate(u) * 3.14159);
            o.col = float3(0.92, 0.68, 0.32) * rib; o.rough = 0.25; o.metal = 0.9;
            o.emis = float3(1.0, 0.62, 0.24) * (0.22 + 0.9 * night) * rib;
        }
        if (tg == 6)
        {
            // the planted slope: lawn in bands along the contour, low clipped hedges between them, flowers in the beds
            float3 c = QGrass(wp, fwl);
            float band = frac(y / 2.6), hedge = smoothstep(0.80, 0.86, band) - smoothstep(0.94, 0.99, band);
            float bed = smoothstep(0.55, 0.62, band) * (1.0 - smoothstep(0.78, 0.80, band));
            float2 fq = wp * 4.0; float fc = QHash(floor(fq)), far = smoothstep(0.25, 0.7, fwl * 4.0);
            float dt = 1.0 - smoothstep(0.18, 0.32, length(frac(fq) - 0.5));
            float3 flw = fc > 0.66 ? float3(0.55, 0.16, 0.30) : fc > 0.33 ? float3(0.62, 0.48, 0.10) : float3(0.36, 0.20, 0.50);
            float3 bedc = float3(0.040, 0.080, 0.024) * (0.75 + 0.5 * QFine(wp, 2.5, fwl));
            bedc = lerp(bedc, flw, step(0.80, QHash(floor(fq) + 7.0)) * dt * (1.0 - far) * 0.8 + far * 0.06);
            c = lerp(c, bedc, bed);
            c = lerp(c, float3(0.035, 0.085, 0.022) * (0.8 + 0.4 * QFine(wp, 3.0, fwl)), hedge);
            o.col = c; o.rough = 0.95; o.soft = true;
        }
        if (tg == 7)
        {
            float rp = 0.5 + 0.5 * sin(wp.x * 0.9 + wp.y * 0.7) * sin(wp.y * 1.3 - wp.x * 0.4);
            o.col = lerp(float3(0.02, 0.22, 0.36), float3(0.06, 0.42, 0.60), rp); o.rough = 0.04; o.metal = 0.15;
            o.emis = float3(0.05, 0.45, 0.85) * (0.10 + night * 0.9); o.soft = true;
        }
        if (tg == 5) { o.col = QPavers(wp, float2(1.2, 0.6), float3(0.56, 0.52, 0.46), fwp, fwl); o.rough = 0.8; o.soft = true; }
        if (tg == 14)
        {
            // the underside of the pavilion roof: timber slats, a grid of downlights
            float sv = wp.x * 0.8 + wp.y * 0.6;
            float sl = QLine(sv, 0.45, 0.05, fwp.x * 0.8 + fwp.y * 0.6);
            o.col = float3(0.42, 0.26, 0.13) * (0.85 + 0.25 * QHash(float2(floor(sv / 0.45), 1.0))) * (1.0 - 0.35 * sl); o.rough = 0.7;
            float2 g = frac(wp / 4.0) - 0.5; float dl = 1.0 - smoothstep(0.03, 0.07, length(g));
            o.emis = float3(1.0, 0.82, 0.58) * (dl * (0.8 + 2.5 * night) + 0.10 + 0.25 * night) * o.col * 3.0;
        }
        if (tg == 13)
        {
            // the parasols and awnings: cream canvas, lit from below in the evening
            o.col = float3(0.80, 0.76, 0.68) * (0.92 + 0.08 * QFine(wp, 2.0, fwl)); o.rough = 0.9;
            o.emis = float3(1.0, 0.75, 0.45) * night * 0.45;
        }
        if (tg == 9) { o.col = QPavers(wp, float2(1.6, 0.8), float3(0.42, 0.40, 0.37), fwp, fwl); o.rough = 0.8; o.soft = true; }
        if (tg == 10)
        {
            bool top = no.y > 0.5;
            o.col = QPavers(top ? wp : float2(u, y), float2(1.2, 0.6), float3(0.50, 0.47, 0.43), top ? fwp : float2(fu, fy), fwl) * (top ? 1.0 : 0.78); o.rough = 0.75;
            if (!top) o.emis = float3(1.0, 0.8, 0.55) * night * 0.35;
            o.soft = true;
        }
        if (tg == 12) { o.col = QGrass(wp, fwl); o.rough = 0.95; o.soft = true; }
        return o;
    }
    // ---------------- the district
    if (tg == 32)
    {
        // the coping and the parapet: light precast stone
        o.col = float3(0.62, 0.60, 0.56) * (0.95 + 0.08 * QFine(wp + y, 1.0, fwl)); o.rough = 0.7;
    }
    else if (tg == 33)
    {
        // rooftop plant: galvanised units, a fan grille on the top
        o.col = float3(0.46, 0.47, 0.48); o.rough = 0.45; o.metal = 0.6;
        if (no.y > 0.5) o.col *= 1.0 - 0.45 * QLine(wp.x, 0.25, 0.04, fwp.x);
    }
    else if (no.y > 0.5)
    {
        if (tg == 26) { o.col = QGarden(wp, fwp, fwl); o.rough = 0.92; o.soft = true; }
        else if (tg == 28) { float rp = QFine(wp * 0.6, 1.0, fwl * 0.6); o.col = float3(0.012, 0.045, 0.055) * (0.9 + 0.2 * rp); o.rough = 0.12; o.soft = true; }
        else if (tg == 31)
        {
            // asphalt, the lane lines (u runs across the road, ± its half width)
            float n = QHash(floor(wp * 0.7)) * 0.03;
            o.col = float3(0.030, 0.032, 0.035) + n * 0.5; o.rough = 0.9;
            float lane = QLine(u, 3.6, 0.07, fu);
            float dash = step(0.5, frac((wp.x + wp.y) / 9.0));
            o.col *= 0.9 + 0.2 * QFine(wp, 2.0, fwl);
            o.col = lerp(o.col, float3(0.45, 0.45, 0.45), lane * dash * 0.35);
            o.emis = float3(1.0, 0.75, 0.45) * night * 0.05;
        }
        else if (tg == 29) { o.col = QGrass(wp, fwl); o.rough = 0.95; o.soft = true; }
        else if (tg == 30) { o.col = QPavers(wp, float2(1.0, 0.5), float3(0.40, 0.385, 0.36), fwp, fwl); o.rough = 0.9; o.soft = true; }
        else if (tg == 27) { o.col = float3(0.10, 0.14, 0.17); o.rough = 0.08; o.metal = 0.9; o.emis = float3(1.0, 0.8, 0.6) * night * 0.5; }
        else { o.col = QMembrane(wp, fwp, fwl); o.rough = 0.85; }
    }
    else if (tg == 27)
    {
        float mul = max(QLine(u, 3.0, 0.08, fu), QLine(y, 3.0, 0.08, fy));
        o.col = lerp(float3(0.09, 0.13, 0.16), float3(0.8, 0.8, 0.8), mul); o.rough = 0.08; o.metal = 0.9; o.emis = float3(1.0, 0.8, 0.6) * night * 0.6 * (1.0 - mul);
    }
    else if (tg == 24)
    {
        // an office tower: unitised curtain wall, blue-grey glass, aluminium mullions every 1.5 m and a spandrel at every floor
        float mul = QLine(u, 1.5, 0.045, fu), spd = QLine(y - 0.2, 3.6, 0.42, fy), fr2 = max(mul, spd);
        float cellF = floor(y / 3.6), cellU = floor(u / 1.5);
        float3 gl = float3(0.10, 0.13, 0.16) * (0.85 + 0.3 * QHash(float2(cellU * 0.37, cellF)));
        o.col = lerp(gl, float3(0.74, 0.75, 0.76), fr2);
        o.rough = lerp(0.04, 0.35, fr2); o.metal = lerp(0.95, 0.6, fr2);
        float on = step(0.55, QHash(float2(floor(u / 6.0), cellF)));
        o.emis = float3(1.0, 0.86, 0.66) * night * (0.03 + 0.4 * on) * (1.0 - fr2);
        o.col *= lerp(0.72, 1.0, smoothstep(0.0, 6.0, y));
    }
    else
    {
        // a residential or office block: light precast stone with deep windows in a regular grid, as on the physical model;
        // the window grid fades to its average colour where it gets smaller than a pixel
        float bw = tg == 21 ? 3.0 : tg == 22 ? 1.9 : tg == 23 ? 2.7 : 2.4, fh2 = 3.3;
        float3 wall = tg == 21 ? float3(0.70, 0.64, 0.55) : tg == 22 ? float3(0.76, 0.76, 0.75) : tg == 23 ? float3(0.58, 0.45, 0.35) : float3(0.82, 0.79, 0.73);
        float uu = u / bw, f = y / fh2, du = fu / bw, df = fy / fh2;
        float fuu = frac(uu), ff = frac(f);
        float ww = tg == 22 ? 0.30 : 0.18, wb = 0.24, wt = 0.88;
        float shop = 1.0 - step(4.6, y);
        if (shop > 0.5) { wb = 0.10; wt = 0.80; ww = 0.06; ff = y / 4.6; df = fy / 4.6; }
        float wx = smoothstep(ww - du, ww + du, fuu) - smoothstep(1.0 - ww - du, 1.0 - ww + du, fuu);
        float wy = smoothstep(wb - df, wb + df, ff) - smoothstep(wt - df, wt + df, ff);
        float win = wx * wy;
        float far = smoothstep(0.22, 0.55, max(du, df));
        float avg = (1.0 - 2.0 * ww) * (wt - wb);
        win = lerp(win, avg, far);
        float rev = (smoothstep(wt - 0.08, wt, ff) * step(ff, wt)) * wx * (1.0 - far);
        float2 cell = float2(floor(uu), floor(y / (shop > 0.5 ? 4.6 : fh2))) + floor(wp / 60.0) * 13.0;
        float h1 = QHash(cell), h2 = QHash(cell.yx + 3.1);
        float3 glass = h1 > 0.78 ? float3(0.34, 0.31, 0.26) : lerp(float3(0.11, 0.14, 0.17), float3(0.20, 0.24, 0.28), h2);    // some with curtains
        if (shop > 0.5) glass = float3(0.08, 0.075, 0.07);
        float band = QLine(y, fh2, 0.08, fy) * 0.06 * (1.0 - shop);
        float3 wc = wall * (1.0 - band) * (1.0 - 0.06 * QHash(floor(wp / 24.0)));
        o.col = lerp(wc, glass, win) * (1.0 - 0.35 * rev);
        o.rough = lerp(0.82, h1 > 0.78 ? 0.55 : 0.12, win); o.metal = lerp(0.0, h1 > 0.78 ? 0.0 : 0.45, win);
        float lit = step(0.70, h2);
        o.emis = float3(1.0, 0.72, 0.42) * night * win * (0.015 + (shop > 0.5 ? 0.6 : 0.42 * lit) * (1.0 - far * 0.6));
        o.col *= lerp(0.70, 1.0, smoothstep(0.0, 5.0, y));            // the base darker: the street in shadow
    }
    return o;
}
// KAIST Kazakhstan (QTwin_AlatauCity_Monitoring.html, its campus page), tags 41–62 = the page's tag + 40: k = the page's tag.
// lp, lfw: plan metres in the frame of the campus (its paving and lines run with its buildings) and their footprint
QSurf KaistSurface(int k, int pid, float u, float y, float fu, float fy, float2 lp, float2 lfw, float fwl, float3 no, float night)
{
    QSurf o; o.col = float3(0.40, 0.395, 0.38); o.rough = 0.9; o.metal = 0.0; o.emis = 0; o.soft = false;
    if (k == 1 || k == 15)
    {
        // the curtain walls: deep blue glass under a white grid (main hall, north block) or teal glass with white mullions every 1.2 m (B1, labs)
        bool teal = k == 15;
        float per = teal ? 1.2 : 1.5, fl = teal ? 4.1 : 4.45;
        float mul = QLine(u, per, teal ? 0.09 : 0.03, fu), tr = QLine(y - 0.3, fl, 0.12, fy);
        float cellF = floor((y - 0.3) / fl), cellU = floor(u / (per * 2.0));
        float h1 = QHash(float2(cellU, cellF + pid * 5.0));
        float3 gl = teal ? lerp(float3(0.05, 0.14, 0.15), float3(0.10, 0.22, 0.22), h1) : lerp(float3(0.04, 0.10, 0.19), float3(0.09, 0.18, 0.30), h1);
        float fr = max(mul, tr);
        o.col = lerp(gl, float3(0.86, 0.87, 0.86), fr); o.rough = lerp(0.05, 0.45, fr); o.metal = lerp(0.85, 0.1, fr);
        float lit = step(0.45, QHash(float2(cellU * 1.7, cellF * 0.9 + pid)));
        o.emis = float3(1.0, 0.90, 0.72) * (1.0 - fr) * (0.02 + night * (0.12 + 0.75 * lit));
    }
    if (k == 4)
    {
        // the glass pyramids and lamps: clear sky glass on a white frame, lit from inside in the evening
        float fr = max(QLine(u, 3.0, 0.06, fu), QLine(y, 1.6, 0.05, fy));
        o.col = lerp(float3(0.22, 0.36, 0.46), float3(0.86, 0.86, 0.84), fr); o.rough = lerp(0.05, 0.5, fr); o.metal = lerp(0.7, 0.0, fr);
        o.emis = float3(1.0, 0.86, 0.62) * (0.04 + night * 1.1) * (1.0 - fr);
    }
    if (k == 8)
    {
        // the glazed lobby and the ground floors: tall panes, the lit hall behind
        float mul = max(QLine(u, 2.4, 0.05, fu), QLine(y - 0.4, 4.3, 0.10, fy));
        float hb = QHash(float2(floor(u / 2.4), pid));
        float3 room = lerp(float3(0.30, 0.26, 0.20), float3(0.52, 0.46, 0.36), hb);
        o.col = lerp(lerp(float3(0.06, 0.08, 0.10), room * 0.5, 0.45), float3(0.85, 0.85, 0.83), mul);
        o.rough = lerp(0.04, 0.5, mul); o.metal = lerp(0.4, 0.0, mul);
        o.emis = room * float3(1.0, 0.88, 0.70) * (0.35 + 2.0 * night) * (1.0 - mul);
    }
    if (k == 2)
    {
        // white: slab bands, the grid, columns, the soffit of the lifted hall (lit at night)
        o.col = float3(0.84, 0.84, 0.82) * (0.96 + 0.06 * QFine(lp + y, 1.0, fwl)); o.rough = 0.55;
        if (no.y < -0.5) o.emis = float3(1.0, 0.86, 0.62) * night * 0.55;
    }
    if (k == 18) { o.col = QMembrane(lp, lfw, fwl) * 1.25; o.rough = 0.85; }
    if (k == 6) { o.col = QGarden(lp, lfw, fwl); o.rough = 0.95; o.soft = true; }
    if (k == 12) { o.col = QGrass(lp, fwl); o.rough = 0.95; o.soft = true; }
    if (k == 21) { o.col = float3(0.035, 0.08, 0.025) * (0.75 + 0.5 * QFine(lp + y * 1.3, 2.5, fwl)); o.rough = 0.95; o.soft = true; }
    if (k == 7)
    {
        // the lake: deep blue-green, a soft ripple; matt enough that the sky does not wash it white from above
        float rp = 0.5 + 0.5 * sin(lp.x * 0.9 + lp.y * 0.7) * sin(lp.y * 1.3 - lp.x * 0.4);
        o.col = lerp(float3(0.015, 0.13, 0.22), float3(0.03, 0.24, 0.36), rp); o.rough = 0.22; o.metal = 0.1;
        o.emis = float3(0.03, 0.22, 0.42) * (0.06 + night * 0.6); o.soft = true;
    }
    if (k == 5) { o.col = QPavers(lp, float2(1.2, 0.6), float3(0.62, 0.60, 0.56), lfw, fwl); o.rough = 0.8; o.soft = true; }
    if (k == 9) { o.col = QPavers(lp, float2(1.6, 0.8), float3(0.50, 0.48, 0.45), lfw, fwl); o.rough = 0.8; o.soft = true; }
    if (k == 22) { o.col = QPavers(lp, float2(0.9, 0.45), float3(0.55, 0.53, 0.49), lfw, fwl); o.rough = 0.85; o.soft = true; }
    if (k == 20) { o.col = QPavers(lp, float2(1.6, 0.8), float3(0.52, 0.50, 0.46), lfw, fwl); o.rough = 0.8; o.soft = true; }
    if (k == 10)
    {
        bool top = no.y > 0.5;
        o.col = QPavers(top ? lp : float2(u, y), float2(1.2, 0.6), float3(0.70, 0.68, 0.64), top ? lfw : float2(fu, fy), fwl) * (top ? 1.0 : 0.85); o.rough = 0.7; o.soft = true;
    }
    if (k == 16) { o.col = float3(0.42, 0.12, 0.07) * (0.9 + 0.2 * saturate(QFbm(lp * 1.3))); o.rough = 0.9; o.soft = true; }
    if (k == 17)
    {
        // the pitch: mowing stripes, its lines (halfway, the boxes as on the page, the centre circle)
        float st = step(0.5, frac(lp.x / 7.0));
        float2 q = lp - float2(140.0, -122.0);
        float ln = max(max(QLine(q.x, 1000.0, 0.08, lfw.x), QLine(abs(q.x) - 40.0, 1000.0, 0.08, lfw.x)),
                       max(QLine(abs(q.y) - 18.5, 1000.0, 0.08, lfw.y), QLine(length(q) - 9.15, 1000.0, 0.09, length(lfw))));
        o.col = lerp(float3(0.07, 0.17, 0.05) * (0.92 + 0.12 * st), float3(0.85, 0.85, 0.85), saturate(ln)); o.rough = 0.9; o.soft = true;
    }
    return o;
}
#endif
