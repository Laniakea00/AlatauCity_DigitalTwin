// Ground of the city: the master plan appears where and when the city is actually built.
// _MainTex = plan (muted zoning), _NatTex = the same ground before development (steppe + faint ghost of the plan),
// _DevTex = 8-bit development year (value + 2000; 0 = always as is), sampled in the same UVs.
// _CityTex = signed distance to the city boundary (Tools: map_city.png, 128 = edge, 1 unit = 25 m, > 128 inside): the land outside the city is a calm,
// muted context, the boundary is a thin warm line, and the rectangle of the map dissolves into the background (_AlatauEdgeCol) at its edges.
// Globals: _AlatauYear (timeline), _AlatauYearF + _AlatauGrow (smooth year while playing), _AlatauDevK (scenario pace: base 1, fast 0.75, slow 1.3),
//          _AlatauMode (2 = analysis: ground muted).
Shader "AlatauCity/Ground"
{
    Properties
    {
        _MainTex ("Plan", 2D) = "white" {}
        _NatTex ("Before development", 2D) = "white" {}
        _DevTex ("Development year", 2D) = "black" {}
        _CityTex ("City boundary distance", 2D) = "white" {}
        _DistTex ("District id", 2D) = "black" {}
        _Ambient ("Self light", Range(0,1)) = 0.12
        _Earth ("Earthworks colour", Color) = (0.55, 0.49, 0.40, 1)
    }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry-10" }
        CGPROGRAM
        // one sun and no point lights: no additive-light copies for the browser to compile (novertexlights would also drop
        // the ambient light probes the ground is lit by)
        #pragma surface surf Soft fullforwardshadows noforwardadd nolightmap nodynlightmap nodirlightmap nometa
        #pragma target 3.5
        #include "Assets/Shaders/AlatauFilm.cginc"
        sampler2D _MainTex, _NatTex, _DevTex; half _Ambient; fixed4 _Earth;
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauDevK, _AlatauMode, _AlatauBlockOn;
        sampler2D _AlatauBlockTex, _CityTex, _DistTex; float _CityOn; fixed4 _AlatauEdgeCol; float _AlatauCamDist, _AlatauFocusD;
        float4 _DistTex_TexelSize; float _AlatauHiOn; float4 _AlatauHiWave, _AlatauHiCol; float4 _AlatauIcZones[32]; float _AlatauIcCount;
        // district id from map_districts.png (point sampled): 30 Gate, 90 Golden, 150 Growing, 210 Green, 0 outside
        float DistAt(float2 uv) { float v = tex2Dlod(_DistTex, float4(uv, 0, 0)).r * 255.0; return v < 15.0 ? -1.0 : floor((v - 30.0) / 60.0 + 0.5); }
        struct Input { float2 uv_MainTex; float3 worldPos; };
        float WaterOf(float3 c) { return saturate((c.b - c.r - 0.10) * 8.0) * saturate((c.b - c.g - 0.03) * 25.0); }
        float FBM(float2 p) { float a = 0.5, r = 0.0; for (int i = 0; i < 4; i++) { r += a * ANoise(p); p = p * 2.03 + 17.1; a *= 0.5; } return r / 0.9375; }
        // A yard inside a city block, as seen from the air: cells of 36 × 30 m along the block, each a lawn, a car park with cars, a paved
        // court or a playground (by land use), paved paths along some cell edges. Details that would be smaller than a pixel fade to
        // their average colour, so nothing shimmers from the whole-city view.
        fixed3 Yard(float2 p, float ang, float resid, float civic, float indus, float px, float3 pg, float3 pp, float3 pa, fixed3 grass, out float car)
        {
            float ca = cos(ang), sa = sin(ang); float2 q = float2(p.x * ca + p.y * sa, -p.x * sa + p.y * ca);
            float2 cs = float2(36.0, 30.0), id = floor(q / cs), f = q - id * cs;
            float h = AHash2(id + 0.37), h2 = AHash2(id + 7.9), h3 = AHash2(id + 21.3);
            float aa = max(px, 0.05);
            // type: 0 lawn, 1 car park, 2 paved court, 3 playground, 4 concrete yard (industry)
            float t;
            if (indus > 0.5) t = h < 0.50 ? 4.0 : h < 0.78 ? 1.0 : h < 0.90 ? 2.0 : 0.0;
            else if (resid > 0.5) t = h < 0.52 ? 0.0 : h < 0.74 ? 1.0 : h < 0.90 ? 2.0 : 3.0;
            else t = h < 0.34 ? 2.0 : h < 0.66 ? 1.0 : h < 0.92 ? 0.0 : 3.0;
            fixed3 lawn = grass * lerp(float3(1, 1, 1), pg, 0.8) * (0.95 + 0.08 * h2);
            fixed3 asph = fixed3(0.37, 0.37, 0.37) * lerp(float3(1, 1, 1), pa, 0.6) * (0.94 + 0.1 * h3);
            fixed3 pave = fixed3(0.66, 0.64, 0.60) * lerp(float3(1, 1, 1), pp, 0.7);
            fixed3 c = lawn; car = 0.0;
            if (t < 0.5)
            {
                // a lawn with a darker mown stripe pattern and a footpath across
                c *= 1.0 - 0.04 * step(0.5, frac(f.x / 6.0)) * saturate(1.0 - px * 0.5);
                float diag = abs((f.x - f.y * 1.2 - (h2 - 0.5) * 20.0)) / 1.56;
                c = lerp(c, pave * 0.97, (1.0 - smoothstep(0.9, 0.9 + aa, diag)) * step(0.55, h3));
            }
            else if (t < 1.5)
            {
                // car park: two rows of stalls facing an aisle, white stall lines, cars in most stalls
                c = asph;
                float yy = fmod(f.y, 16.4), row = yy < 5.2 ? 0.0 : yy > 11.2 ? 1.0 : -1.0;
                float2 st = float2(f.x / 2.6, floor(f.y / 16.4) * 2.0 + row);
                float sx = frac(st.x) * 2.6, sy = row < 0.0 ? 0.0 : (row < 0.5 ? yy : yy - 11.2);
                float stl = row >= 0.0 ? 1.0 - smoothstep(0.06, 0.06 + aa, abs(sx - 0.05)) : 0.0;
                c = lerp(c, fixed3(0.80, 0.80, 0.78), stl * 0.8 * saturate(1.5 - px));
                if (row >= 0.0 && f.x > 1.5 && f.x < cs.x - 1.5)
                {
                    float hc = AHash2(floor(st) + id * 3.1);
                    if (hc > 0.28)
                    {
                        float2 d = abs(float2(sx - 1.3, sy - 2.6)) - float2(0.92, 2.15);
                        float inCar = 1.0 - smoothstep(-aa * 0.5, aa * 0.5, max(d.x, d.y));
                        fixed3 cc = hc < 0.42 ? fixed3(0.88, 0.88, 0.86) : hc < 0.56 ? fixed3(0.12, 0.12, 0.13) : hc < 0.70 ? fixed3(0.56, 0.58, 0.60) : hc < 0.80 ? fixed3(0.74, 0.75, 0.76) : hc < 0.88 ? fixed3(0.55, 0.12, 0.10) : hc < 0.95 ? fixed3(0.16, 0.25, 0.42) : fixed3(0.70, 0.64, 0.52);
                        float glass = step(abs(sy - 2.6 - 0.2), 0.8) * step(abs(sx - 1.3), 0.7);
                        cc = lerp(cc, fixed3(0.10, 0.12, 0.14), glass * 0.65);
                        float far = saturate((px - 1.2) / 2.0);                                    // from afar: a speckle of the mean colour
                        c = lerp(c, lerp(cc, lerp(asph, fixed3(0.5, 0.5, 0.5), 0.55), far), inCar);
                        car = inCar;
                    }
                }
            }
            else if (t < 2.5)
            {
                // paved court: slabs with joints, a planted square in the middle
                c = pave * (0.97 + 0.05 * AHash2(floor(f / 3.0) + id));
                float j = min(frac(f.x / 3.0), frac(f.y / 3.0)) * 3.0;
                c *= 1.0 - 0.08 * (1.0 - smoothstep(0.05, 0.05 + aa, j)) * saturate(1.3 - px);
                float2 m = abs(f - cs * 0.5) - float2(7.0, 5.0);
                c = lerp(c, lawn, (1.0 - smoothstep(0.0, aa, max(m.x, m.y))) * step(0.4, h2));
            }
            else if (t < 3.5)
            {
                // playground: rubber surface, a sand pit, a strip of lawn around
                float2 m = abs(f - cs * 0.5) - float2(12.0, 9.0);
                fixed3 rub = h2 < 0.5 ? fixed3(0.62, 0.36, 0.28) : fixed3(0.34, 0.52, 0.42);
                c = lerp(lawn, rub, 1.0 - smoothstep(0.0, aa, max(m.x, m.y)));
                float sand = length(f - cs * 0.5 - float2(5.0, 2.0)) - 3.5;
                c = lerp(c, fixed3(0.80, 0.73, 0.58), 1.0 - smoothstep(0.0, aa, sand));
            }
            else
            {
                // concrete yard of a factory: slabs, oil stains, a gravel patch
                c = fixed3(0.60, 0.59, 0.56) * lerp(float3(1, 1, 1), pp, 0.5) * (0.92 + 0.1 * ANoise(p * 0.15));
                c = lerp(c, fixed3(0.53, 0.50, 0.45), smoothstep(0.6, 0.75, ANoise(p * 0.05 + h * 9.0)));
                c *= 1.0 - 0.12 * smoothstep(0.75, 0.9, ANoise(p * 0.3 + 3.0));
            }
            // paths along some cell edges
            float ex = min(f.x, cs.x - f.x), ey = min(f.y, cs.y - f.y);
            float px1 = (1.0 - smoothstep(1.1, 1.1 + aa, ex)) * step(0.45, AHash2(float2(id.x + step(cs.x * 0.5, f.x), id.y) + 5.5));
            float py1 = (1.0 - smoothstep(1.1, 1.1 + aa, ey)) * step(0.45, AHash2(float2(id.x, id.y + step(cs.y * 0.5, f.y)) + 8.5));
            c = lerp(c, pave, saturate(px1 + py1) * (t < 0.5 || t > 2.5 ? 1.0 : 0.5));
            return c;
        }

        half4 LightingSoft(SurfaceOutput s, half3 lightDir, half atten)
        {
            half nl = saturate(dot(s.Normal, lightDir));
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten * 0.85 + 0.15); c.a = s.Alpha; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float2 uv = IN.uv_MainTex;
            fixed3 plan = tex2D(_MainTex, uv).rgb, nat = tex2D(_NatTex, uv).rgb;
            float dev = tex2D(_DevTex, uv).r * 255.0 + 2000.0;
            float k = _AlatauDevK > 0.01 ? _AlatauDevK : 1.0;
            float eff = dev <= 2025.5 ? dev : 2025.0 + (dev - 2025.0) * k;
            float y = _AlatauGrow > 0.5 ? _AlatauYearF + 1.0 : (_AlatauYear < 1 ? 2050.0 : _AlatauYear);
            // two years of earthworks before the quarter is built, then the plan colour
            float prep = saturate((y - (eff - 2.5)) / 1.2);
            float done = saturate((y - (eff - 0.6)) / 0.8);
            fixed3 c = lerp(nat, lerp(nat, _Earth.rgb, 0.45), prep * (1 - done));
            c = lerp(c, plan, done);
            if (_AlatauMode > 1.5) { float g = dot(c, fixed3(0.299, 0.587, 0.114)); c = lerp(fixed3(g, g, g), c, 0.3) * 0.9; }
            fixed3 cYear = c;                                                   // the plan by year, before the film look
            // ---- the city and its context (variant C): metres to the boundary, + inside
            float sdm = (tex2D(_CityTex, uv).r * 255.0 - 128.0) * 25.0;
            float sdw = max(fwidth(sdm), 0.5);
            float inside = _CityOn > 0.5 ? saturate(sdm / max(sdw * 1.5, 20.0) + 0.5) : 1.0;
            half3 em = c * _Ambient; float waterG = 0.0;
            if (_AlatauFilm > 0.5 && _AlatauMode < 1.5)
            {
                // film look: the zoning colours become a hint, parks turn green, open land a living steppe, water a real surface
                fixed3 c0 = plan;
                float3 wp = IN.worldPos;
                float lum = dot(c, fixed3(0.299, 0.587, 0.114)), sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
                // ---- water: a smooth mask from the natural map (and the plan's new lakes once built), 7 taps ~22 m around a point that
                //      wanders a little, so the shores are round and natural instead of the raster's steps; a wider ring tells how deep
                float2 mU = float2(2.29357798e-5, 1.62074554e-5);
                float2 warp = (float2(ANoise(wp.xz * 0.021), ANoise(wp.xz * 0.021 + 19.1)) - 0.5) * 16.0;
                float wsum = 0.0, wdeep = 0.0;
                for (int k = 0; k < 7; k++)
                {
                    float a = k * 1.0471976; float2 o = k == 0 ? float2(0, 0) : float2(cos(a), sin(a)) * 22.0;
                    float2 uk = uv + (o + warp) * mU;
                    float3 nk = tex2Dlod(_NatTex, float4(uk, 0, 0)).rgb, pk = tex2Dlod(_MainTex, float4(uk, 0, 0)).rgb;
                    // water is blue (not the teal of the plan's recreation zones); once a quarter is built the plan decides: reclaimed land
                    // and embankments of the master plan replace the old water, so no house ever stands in a lake
                    wsum += lerp(WaterOf(nk), WaterOf(pk), done);
                    float2 ud = uv + (float2(cos(a + 0.5), sin(a + 0.5)) * 70.0 + warp) * mU;
                    float3 dk = tex2Dlod(_NatTex, float4(ud, 0, 0)).rgb;
                    wdeep += WaterOf(dk);
                }
                wsum /= 7.0; wdeep /= 7.0;
                float water = smoothstep(0.34, 0.60, wsum); waterG = water;
                float shore = smoothstep(0.10, 0.34, wsum) * (1.0 - water);                    // wet bank around the water
                float green = saturate((c.g - max(c.r, c.b)) * 6.0) * (1.0 - water);
                float open = saturate((0.50 - lum) * 5.0) * saturate(1.0 - sat * 7.0) * (1.0 - water);     // land the plan leaves alone
                float n1 = ANoise(wp.xz * 0.045), n2 = ANoise(wp.xz * 0.011 + 7.0), n3 = ANoise(wp.xz * 0.9);
                // big soft patches over the land (a few hundred metres): nature is never one flat colour
                float macro = ANoise(wp.xz * 0.0032) * 0.55 + ANoise(wp.xz * 0.0105 + 3.7) * 0.30 + ANoise(wp.xz * 0.037 + 9.2) * 0.15;
                float px = length(fwidth(wp.xz));                                              // metres per pixel
                fixed3 f = lerp(fixed3(lum, lum, lum), c, 0.42);
                f = lerp(f, fixed3(0.80, 0.78, 0.73), 0.30) + (1.0 - lum) * 0.10;                         // lift the dark tones
                // ---- open land, as it looks from a plane over the Ili valley: dry steppe (straw, sage, bare loess with erosion streaks and
                //      shrub specks) and, in wide patches, farmland parcels — stubble, ploughed earth with furrows, green crops, fallow
                float fb = FBM(wp.xz * 0.0021 + float2(FBM(wp.xz * 0.0009) * 3.0, 0.0));               // warped: no round blobs
                float fd = FBM(wp.xz * 0.019 + 5.1);                                                   // tens of metres
                float streak = FBM(float2(wp.x * 0.004 + wp.z * 0.0016, wp.z * 0.011 - wp.x * 0.003) + 9.0); // dry gullies
                fixed3 steppe = lerp(fixed3(0.60, 0.57, 0.44), fixed3(0.53, 0.53, 0.39), smoothstep(0.35, 0.65, fb));
                steppe = lerp(steppe, fixed3(0.66, 0.60, 0.47), smoothstep(0.62, 0.80, streak) * 0.55);
                steppe *= 0.92 + 0.16 * fd;
                float bush = smoothstep(0.78, 0.90, ANoise(wp.xz * 0.11 + 2.3)) * saturate(1.6 - px * 0.3);
                steppe = lerp(steppe, fixed3(0.36, 0.38, 0.27), bush * 0.6);
                // farmland: parcels of a rotated grid, a colour each, furrows along the parcel, a dirt track or a tree line between parcels
                float fieldZone = smoothstep(0.50, 0.58, FBM(wp.xz * 0.00028 + 31.0));
                float2 fq = float2(wp.x * 0.951 - wp.z * 0.309, wp.x * 0.309 + wp.z * 0.951);
                // each square kilometre has its own layout (long strips, squares, narrow strips, turned 90°): straight edges, T-junctions,
                // no chessboard
                float2 kid = floor(fq / 1040.0); float kh = AHash2(kid + 0.71);
                float2 fsz = kh < 0.3 ? float2(208.0, 520.0) : kh < 0.55 ? float2(346.7, 346.7) : kh < 0.8 ? float2(130.0, 1040.0) : float2(520.0, 260.0);
                float2 fid = floor(fq / fsz) + kid * 17.0, ff = fq - floor(fq / fsz) * fsz;
                float fh = AHash2(fid + 3.3);
                fixed3 crop = fh < 0.26 ? fixed3(0.67, 0.60, 0.44) : fh < 0.46 ? fixed3(0.52, 0.45, 0.36) : fh < 0.64 ? fixed3(0.47, 0.51, 0.33) : fh < 0.84 ? fixed3(0.61, 0.58, 0.47) : fixed3(0.56, 0.55, 0.40);
                crop *= 0.95 + 0.1 * AHash2(fid + 1.9);
                float furrow = 0.5 + 0.5 * sin(ff.x * 1.05 + fh * 20.0);
                crop *= 1.0 - (0.05 + 0.07 * step(0.26, fh) * step(fh, 0.46)) * furrow * saturate(1.2 - px * 0.6);
                crop *= 0.93 + 0.14 * fd;
                float fedge = min(min(ff.x, fsz.x - ff.x), min(ff.y, fsz.y - ff.y));
                float track = 1.0 - smoothstep(1.5, 3.5 + px * 0.5, fedge);
                crop = lerp(crop, AHash2(fid + 9.1) > 0.55 ? fixed3(0.30, 0.34, 0.22) : fixed3(0.63, 0.58, 0.48), track * 0.85);
                fixed3 land = lerp(steppe, crop, fieldZone);
                // grass of parks and lawns: a natural olive, mown, never flat
                float gb = FBM(wp.xz * 0.012 + 1.7);
                fixed3 grass = lerp(fixed3(0.35, 0.42, 0.25), fixed3(0.45, 0.48, 0.31), smoothstep(0.3, 0.7, gb));
                grass = lerp(grass, fixed3(0.50, 0.49, 0.33), smoothstep(0.55, 0.85, FBM(wp.xz * 0.0055 + 8.3)) * 0.35);           // drier khaki patches, a few hundred metres
                grass = lerp(grass, fixed3(0.54, 0.53, 0.35), smoothstep(0.66, 0.85, FBM(wp.xz * 0.004 + 4.4)) * 0.6);
                grass *= 0.94 + 0.1 * fd;
                f = lerp(f, land, open * 0.95);
                f = lerp(f, grass, green * 0.92);
                // photo textures at two scales (the second, rotated and 4.6x larger, breaks the repetition): grass in the parks,
                // dry grass on open land, paving in the built-up quarters (pattern only, the hue stays)
                float2 xr = float2(wp.x * 0.8 - wp.z * 0.6, wp.x * 0.6 + wp.z * 0.8) / 4.6;
                float3 pg = AlatauMat(wp.xz, 8.0).pattern, pg2 = AlatauMat(xr, 8.0).pattern;
                float3 ps = AlatauMat(wp.xz, 9.0).pattern, ps2 = AlatauMat(xr, 9.0).pattern;
                float3 pp = AlatauMat(wp.xz, 7.0).pattern, pa = AlatauMat(wp.xz, 6.0).pattern;
                pg = lerp(float3(1, 1, 1), pg, 0.6) * lerp(float3(1, 1, 1), pg2, 0.3);          // the larger copy softer: no dark blotches on the lawns
                ps = lerp(float3(1, 1, 1), ps, 0.55) * lerp(float3(1, 1, 1), ps2, 0.45);
                float built = saturate(1.0 - green - open - water);
                f *= lerp(float3(1, 1, 1), pg, green) * lerp(float3(1, 1, 1), ps, open) * lerp(float3(1, 1, 1), pp, built * 0.45);
                if (_AlatauBlockOn > 0.5)
                {
                    // city blocks: metres from the edge of the nearest road corridor (map_blocks), negative inside the corridor.
                    float sd = (tex2D(_AlatauBlockTex, uv).r * 255.0 - 128.0) * 0.5, sw = max(fwidth(sd), 0.02);
                    float inBlock = saturate(sd / sw + 0.5), walk = inBlock * saturate((3.2 - sd) / sw + 0.5), kerb = saturate(1.0 - abs(sd - 0.15) / max(sw, 0.25));
                    float town = done * saturate((48.0 - sd) / 8.0) * (1.0 - water);          // near a road, and developed by now
                    fixed3 verge = lerp(grass, fixed3(0.55, 0.53, 0.38), 0.35) * pg;
                    fixed3 paved = fixed3(0.63, 0.62, 0.59) * lerp(float3(1, 1, 1), pp, 0.8);
                    float resid = saturate((min(c0.r, c0.g) - c0.b) * 6.0), indus = saturate((min(c0.r, c0.b) - c0.g) * 8.0), civic = saturate(1.0 - resid - indus);
                    // the yards follow the block: its orientation from the gradient of the distance to the roads (rectangular blocks give
                    // the same angle from every side, modulo 90°)
                    // read once per patch of 96 m (its centre, a 40 m baseline): an angle that changed from pixel to pixel bent the
                    // grid of the yards into swirls wherever the nearest road changed (corners, the middle between two streets)
                    float2 pc96 = (floor(wp.xz / 96.0) + 0.5) * 96.0, uvP = uv + (pc96 - wp.xz) * mU;
                    float gx = tex2Dlod(_AlatauBlockTex, float4(uvP + float2(40.0 * mU.x, 0), 0, 0)).r - tex2Dlod(_AlatauBlockTex, float4(uvP - float2(40.0 * mU.x, 0), 0, 0)).r;
                    float gz = tex2Dlod(_AlatauBlockTex, float4(uvP + float2(0, 40.0 * mU.y), 0, 0)).r - tex2Dlod(_AlatauBlockTex, float4(uvP - float2(0, 40.0 * mU.y), 0, 0)).r;
                    float ang = abs(gx) + abs(gz) > 0.004 ? atan2(gz, gx) : 0.35;
                    ang = ang - floor(ang / 1.5707963) * 1.5707963; ang = floor(ang / 0.0872665 + 0.5) * 0.0872665;
                    float car = 0.0;
                    fixed3 yard = Yard(wp.xz, ang, resid, civic, indus, px, pg, pp, pa, grass, car);
                    // from far away the yards merge into one calm tone of their quarter (no salt-and-pepper mosaic)
                    fixed3 yAvg = resid * lerp(grass, fixed3(0.47, 0.47, 0.45), 0.35) + civic * fixed3(0.58, 0.57, 0.54) + indus * fixed3(0.57, 0.56, 0.53);
                    yard = lerp(yard, yAvg * (0.96 + 0.08 * fd), saturate((px - 2.5) / 7.0) * 0.75);
                    // a quarter only exists between roads: far from any street (special zones, the airfield, empty plots) the land stays land
                    float noBlock = smoothstep(50.0, 61.0, sd);
                    f = lerp(f, land, noBlock * built * done);
                    // inside a motorway interchange (FilmRoads.PublishZones) the land between the ramps is a mown verge, never yards
                    float icz = 0.0;
                    for (int iz = 0; iz < 32; iz++)
                    {
                        if (iz >= (int)_AlatauIcCount) break;
                        float4 zz = _AlatauIcZones[iz];
                        icz = max(icz, 1.0 - smoothstep(zz.z * 0.8, zz.z, distance(wp.xz, zz.xy)));
                    }
                    f = lerp(f, yard, done * (1.0 - water) * inBlock * (1.0 - green) * (1.0 - open) * (1.0 - noBlock) * (1.0 - icz) * 0.92);      // everywhere the city is built
                    f = lerp(f, verge, icz * done * (1.0 - water) * (1.0 - green));
                    f = lerp(f, verge, town * (1.0 - inBlock));                                   // the whole road corridor is a mown verge
                    f = lerp(f, paved, town * walk * 0.9 * (1.0 - icz));                         // no pavements of the plan's old ramp scribbles
                    f *= 1.0 - 0.30 * kerb * town * saturate(1.6 - sw * 2.0) * (1.0 - icz);
                }
                // wet, darker bank and a strip of pale sand where the steppe meets the water
                f = lerp(f, f * fixed3(0.70, 0.72, 0.70), shore * 0.8);
                f = lerp(f, fixed3(0.72, 0.68, 0.56) * lerp(float3(1, 1, 1), ps, 0.4), shore * open * smoothstep(0.55, 0.75, ANoise(wp.xz * 0.03 + 5.0)) * 0.6);
                // ---- the water surface: moving ripples, the sky mirrored by the Fresnel law, a sun glint, colour by depth
                float t = _Time.y;
                // wind ripples as a sum of directional waves (analytic slope): no lattice of the value noise, no square tiles up close
                float2 gw = float2(0, 0);
                {
                    float2 pw2 = wp.xz + (float2(ANoise(wp.xz * 0.013), ANoise(wp.xz * 0.013 + 7.7)) - 0.5) * 30.0;
                    const float2 D0 = float2(0.80, 0.60), D1 = float2(-0.45, 0.89), D2 = float2(0.97, -0.24), D3 = float2(-0.86, -0.51), D4 = float2(0.20, 0.98);
                    gw += D0 * 0.80 * cos(dot(D0, pw2) * 0.78 + t * 1.30);
                    gw += D1 * 0.55 * cos(dot(D1, pw2) * 1.21 + t * 1.65);
                    gw += D2 * 0.40 * cos(dot(D2, pw2) * 1.93 + t * 2.10);
                    gw += D3 * 0.28 * cos(dot(D3, pw2) * 3.07 + t * 2.60);
                    gw += D4 * 0.18 * cos(dot(D4, pw2) * 4.70 + t * 3.20);
                }
                float hx = gw.x * 0.22, hz = gw.y * 0.22;
                float rip = 0.55 * saturate(1.4 - px * 0.25);                                  // ripples flatten with distance (no shimmer)
                float3 nW = normalize(float3(-hx * rip, 1.0, -hz * rip));
                float3 view = normalize(_WorldSpaceCameraPos - wp);
                float fres = 0.02 + 0.98 * pow(1.0 - saturate(dot(nW, view)), 5.0);
                float3 refl = AlatauSky(reflect(-view, nW));
                float depth = saturate(wdeep * 1.4 - 0.2) * water;
                fixed3 body = lerp(fixed3(0.11, 0.22, 0.23), fixed3(0.04, 0.10, 0.15), depth);
                float glint = pow(saturate(dot(reflect(-_AlatauSunDir.xyz, nW), view)), 220.0) * (1.0 - _AlatauNight);
                float foam = saturate(1.0 - abs(wsum - 0.40) / 0.05) * (0.5 + 0.5 * ANoise(wp.xz * 0.4 + t * 0.3)) * saturate(1.3 - px * 0.3);
                f = lerp(f, body * 0.55, water);
                f = lerp(f, fixed3(0.85, 0.87, 0.86), foam * 0.35 * water);
                c = f; em = c * _Ambient + (refl * lerp(0.22, 0.95, fres) * 0.7 + _AlatauSunColor.rgb * glint * 2.0) * water;
                // at night the lit city on the banks trembles on the water: warm and white streaks drawn out towards the viewer,
                // near the banks of a built quarter, broken by the ripples
                {
                    float2 fwd = normalize(view.xz + float2(1e-4, 0)), side = float2(-fwd.y, fwd.x);
                    float2 sp = float2(dot(wp.xz, side) * 0.09, dot(wp.xz, fwd) * 0.012 + hx * 0.8);
                    float st = smoothstep(0.62, 0.92, ANoise(sp + float2(0.0, t * 0.05))) * (0.6 + 0.4 * ANoise(wp.xz * 0.5 + t * 0.7));
                    float nearBank = 1.0 - saturate((wdeep - 0.35) * 2.0);
                    float3 cityC = lerp(float3(1.0, 0.72, 0.40), float3(0.95, 0.92, 0.85), ANoise(sp * 3.0));
                    em += cityC * st * nearBank * done * water * _AlatauNight * 0.55;
                }
                // spotlight wave of the presentation: a ring of light runs over the ground in the colour of the category
                float dR = distance(wp.xz, _AlatauHiWave.xy);
                em += _AlatauHiCol.rgb * exp(-abs(_AlatauHiWave.z - dR) / 55.0) * 0.9 * _AlatauHiOn * (1.0 - saturate(_AlatauHiWave.z / max(_AlatauHiWave.w, 1.0)));
            }
            if (_CityOn > 0.5)
            {
                // seen from afar the film look keeps more of the plan's colour inside the city, so the districts read at a glance
                float farK = saturate((_AlatauCamDist - 14000.0) / 26000.0) * step(0.5, _AlatauFilm) * step(_AlatauMode, 1.5);
                c = lerp(c, lerp(c, cYear, 0.55), farK * inside);
                // outside: the same land, desaturated and darker the farther it is from the city; water keeps a cool hint
                float lumO = dot(c, fixed3(0.299, 0.587, 0.114));
                float wat = saturate((nat.b - nat.r) * 5.0 - 0.6) * saturate((nat.g - nat.r) * 8.0 + 0.3);
                fixed3 ctx = lerp(fixed3(lumO, lumO, lumO), c, 0.62) * lerp(0.90, 0.72, saturate(-sdm / 12000.0));        // the same living land, a little calmer: no dark slab around the city
                ctx = lerp(ctx, fixed3(0.16, 0.24, 0.31), wat * 0.75);
                // water keeps its own light outside the city too (the Kapshagay reservoir mirrors the sky at sunset)
                float keep = max(inside, waterG * 0.85);
                c = lerp(ctx, c, keep);
                em = lerp(ctx * _Ambient * 0.6, em, keep);
                // the boundary: a thin warm line (about 1.5 px or 14 m, whichever is wider) and a soft light rim inside it
                float lw = max(sdw * 1.4, 14.0);
                float bline = exp(-abs(sdm) / lw);
                float rim = exp(-max(sdm, 0.0) / 420.0) * inside;
                fixed3 gold = fixed3(0.98, 0.80, 0.45);
                // in the film look the land is real land: no glowing line drawn over the fields, only a faint hint from far away
                float lineK = _AlatauFilm > 0.5 ? 0.35 * saturate((_AlatauCamDist - 9000.0) / 12000.0) : 1.0;
                c = lerp(c, gold, bline * 0.55 * lineK) + rim * 0.035 * lineK;
                em += gold * bline * 0.65 * lineK;
                // one district in focus (district picker, presentation): the others step back, its border glows in its colour
                if (_AlatauFocusD > -0.5)
                {
                    float did = DistAt(uv);
                    float2 o = _DistTex_TexelSize.xy * 1.5;
                    float nb = (DistAt(uv + float2(o.x, 0)) != did ? 1.0 : 0.0) + (DistAt(uv - float2(o.x, 0)) != did ? 1.0 : 0.0) + (DistAt(uv + float2(0, o.y)) != did ? 1.0 : 0.0) + (DistAt(uv - float2(0, o.y)) != did ? 1.0 : 0.0);
                    bool focus = abs(did - _AlatauFocusD) < 0.5;
                    fixed3 dc = _AlatauFocusD < 0.5 ? fixed3(0.18, 0.39, 0.69) : _AlatauFocusD < 1.5 ? fixed3(0.85, 0.65, 0.13) : _AlatauFocusD < 2.5 ? fixed3(0.95, 0.45, 0.21) : fixed3(0.20, 0.62, 0.36);
                    if (!focus && did > -0.5)
                    {
                        float lf = dot(c, fixed3(0.299, 0.587, 0.114));
                        c = lerp(fixed3(lf, lf, lf), c, 0.35) * 0.62; em *= 0.55;
                    }
                    if (focus)
                    {
                        c = lerp(c, dc, 0.06);
                        float edgeF = saturate(nb) * inside;
                        c = lerp(c, dc, edgeF * 0.85); em += dc * edgeF * 0.9;
                    }
                }
                // the map rectangle dissolves into the background at its edges: no slab hanging in the void
                float edge = min(min(uv.x, 1.0 - uv.x) * 43600.0, min(uv.y, 1.0 - uv.y) * 61700.0);
                float fade = smoothstep(0.0, 7500.0, edge);
                fade *= fade;
                // what lies behind the map: the sky below the horizon in the film look (same function as the sky dome), else the background
                float3 rdE = normalize(IN.worldPos - _WorldSpaceCameraPos);
                fixed3 edgeC = _AlatauFilm > 0.5 ? AlatauSky(rdE) : _AlatauEdgeCol.rgb;
                c *= fade; em = em * fade + edgeC * (1.0 - fade);
            }
            o.Albedo = c; o.Emission = em; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack "Diffuse"
}
