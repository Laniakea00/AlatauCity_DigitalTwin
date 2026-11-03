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
        // ---- the ground of the redrawn map (Layers/GroundTypes.cs, Resources/Map/map_ground.bytes): three render textures of the data's
        //      pieces, r = type (low 5 bits; 0 = no data: today's ground) + the lot's hash (top 3 bits), g = direction of the lot (0..1 =
        //      0..90°), b = distance to the nearest piece outline (0..1 over _AlatauGtW metres; fine and near only), a = the piece's year
        //      byte (0 the map's own year from map_dev, 1 always, 26..254 = 2000 + v, 255 never; a piece whose earthworks have not begun
        //      is not in the textures, so the ground under it shows). _AlatauGtFine covers the ground just in front of the camera,
        //      _AlatauGtNear a window round the camera, _AlatauGtFar all the data; their rectangles are (x0, z0, 1 / w, 1 / h),
        //      _AlatauGtFineT / _AlatauGtNearT their texels (1 / w, 1 / h, w, h), _AlatauGtW = (W of fine, W of near) in metres.
        //      _AlatauGtHash: 256 × 256 bytes, the yard cells' table (the same bytes as GroundTypes.CellHash on the CPU).
        sampler2D _AlatauGtNear, _AlatauGtFar, _AlatauGtFine, _AlatauGtHash; float4 _AlatauGtNearR, _AlatauGtFarR, _AlatauGtFineR, _AlatauGtNearT, _AlatauGtFineT, _AlatauGtW; float _AlatauGtOn;
        // a texture of pieces read exactly: of the four texels round the point, the piece with the largest signed distance (+ where a
        // texel is that piece, − where it is another, each texel's distance to the nearest outline weighted bilinearly) wins, so the edge
        // between two pieces runs where the data's outline runs, straight between the texel centres, instead of in steps of a texel.
        // e = metres from the point to the nearest outline (bilinear; the lines of fields, tracks and playgrounds)
        float4 GtExact(sampler2D t, float2 u, float4 tx, float W, out float e)
        {
            float2 st = u * tx.zw - 0.5, i0 = floor(st), fr = st - i0;
            float2 c0 = (i0 + 0.5) * tx.xy;
            float4 a = tex2Dlod(t, float4(c0, 0, 0)), b = tex2Dlod(t, float4(c0 + float2(tx.x, 0.0), 0, 0));
            float4 c = tex2Dlod(t, float4(c0 + float2(0.0, tx.y), 0, 0)), d = tex2Dlod(t, float4(c0 + tx.xy, 0, 0));
            float wa = (1.0 - fr.x) * (1.0 - fr.y) * a.b, wb = fr.x * (1.0 - fr.y) * b.b, wc = (1.0 - fr.x) * fr.y * c.b, wd = fr.x * fr.y * d.b;
            // the same piece: type and hash, angle and year bytes all equal; ±1 per pair
            float ab = step(dot(abs(a.rga - b.rga), float3(1, 1, 1)), 0.001) * 2.0 - 1.0, ac = step(dot(abs(a.rga - c.rga), float3(1, 1, 1)), 0.001) * 2.0 - 1.0;
            float ad = step(dot(abs(a.rga - d.rga), float3(1, 1, 1)), 0.001) * 2.0 - 1.0, bc = step(dot(abs(b.rga - c.rga), float3(1, 1, 1)), 0.001) * 2.0 - 1.0;
            float bd = step(dot(abs(b.rga - d.rga), float3(1, 1, 1)), 0.001) * 2.0 - 1.0, cd = step(dot(abs(c.rga - d.rga), float3(1, 1, 1)), 0.001) * 2.0 - 1.0;
            float sa = wa + wb * ab + wc * ac + wd * ad, sb = wb + wa * ab + wc * bc + wd * bd;
            float sc = wc + wa * ac + wb * bc + wd * cd, sd = wd + wa * ad + wb * bd + wc * cd;
            float4 r = a; float m = sa;
            if (sb > m) { r = b; m = sb; }
            if (sc > m) { r = c; m = sc; }
            if (sd > m) { r = d; }
            e = (wa + wb + wc + wd) * W;
            return r;
        }
        float4 GroundTypeAt(float2 xz, out float e)
        {
            float2 u0 = (xz - _AlatauGtFineR.xy) * _AlatauGtFineR.zw, un = (xz - _AlatauGtNearR.xy) * _AlatauGtNearR.zw, uf = (xz - _AlatauGtFarR.xy) * _AlatauGtFarR.zw;
            float in0 = step(0.002, min(u0.x, u0.y)) * step(max(u0.x, u0.y), 0.998);
            float inN = step(0.001, min(un.x, un.y)) * step(max(un.x, un.y), 0.999);
            float inF = step(0.0, min(uf.x, uf.y)) * step(max(uf.x, uf.y), 1.0);
            float4 r = float4(0, 0, 0, 0); e = 1000.0;
            if (in0 > 0.5) r = GtExact(_AlatauGtFine, u0, _AlatauGtFineT, _AlatauGtW.x, e);
            else if (inN > 0.5) r = GtExact(_AlatauGtNear, un, _AlatauGtNearT, _AlatauGtW.y, e);
            else r = tex2Dlod(_AlatauGtFar, float4(saturate(uf), 0, 0)) * inF;
            return r;
        }
        // the byte of a yard cell (0..255) from the table, lh = the lot's hash (0..7): whole numbers all the way, so the CPU
        // (GroundTypes.CellKindAt) gets the same
        float CellByte(float2 id, float lh)
        {
            float2 k = fmod(id + 8192.0 + float2(lh * 7.0, lh * 13.0), 256.0);
            return floor(tex2Dlod(_AlatauGtHash, float4((k + 0.5) / 256.0, 0, 0)).r * 255.0 + 0.5);
        }
        // the calm tone a lot's yard merges into from far away, by its type (see Yard)
        fixed3 YardAvg(float gt, fixed3 grass)
        {
            fixed3 pave = fixed3(0.63, 0.62, 0.59), conc = fixed3(0.57, 0.56, 0.53), asph = fixed3(0.38, 0.38, 0.38);
            return gt < 2.5 ? grass
                 : gt < 3.5 ? pave
                 : gt < 4.5 ? lerp(asph, fixed3(0.5, 0.5, 0.5), 0.35)
                 : gt < 5.5 ? lerp(grass, fixed3(0.42, 0.37, 0.29), 0.30)
                 : gt < 6.5 ? grass
                 : gt < 7.5 ? conc
                 : gt < 8.5 ? grass
                 : gt < 9.5 ? asph
                 : gt < 10.5 ? grass
                 : gt < 11.5 ? conc
                 : gt < 12.5 ? fixed3(0.33, 0.46, 0.30)
                 : gt < 13.5 ? fixed3(0.55, 0.40, 0.33)
                 : gt < 14.5 ? pave
                 : gt < 16.5 ? grass
                 : gt < 17.5 ? fixed3(0.70, 0.66, 0.58)
                 : fixed3(0.62, 0.34, 0.27);
        }
        // A yard inside a city block, as seen from the air: cells of 36 × 30 m along the block, each a lawn, a car park with cars, a paved
        // court or a playground (by land use), paved paths along some cell edges. Details that would be smaller than a pixel fade to
        // their average colour, so nothing shimmers from the whole-city view.
        // gt > 0: the piece's own type from the data (map_ground.bytes) decides the kind (GroundTypes.Kind; lh = the lot's hash 0..7, no cell
        // of the data picks its kind any more: an industrial yard is plain concrete without cell seams): the yards are lawn, and their aprons,
        // paths, playgrounds, sports grounds and tracks are pieces of their own, drawn to their exact edges (ge = metres to the nearest
        // outline: the white line of a field, the kerb of a playground, the lanes of a track); gardens are beds in continuous rows along the
        // block; no loose paths and no planted squares. gt = 0 gives exactly the yards of the old plan.
        fixed3 Yard(float2 p, float ang, float resid, float civic, float indus, float px, float3 pg, float3 pp, float3 pa, fixed3 grass, float gt, float lh, float ge, out float car)
        {
            float ca = cos(ang), sa = sin(ang); float2 q = float2(p.x * ca + p.y * sa, -p.x * sa + p.y * ca);
            float2 cs = float2(36.0, 30.0), id = floor(q / cs), f = q - id * cs;
            float2 idh = id + lh * 37.0;                                         // each lot draws its own cells (lh = 0 without data: as before)
            float h = AHash2(idh + 0.37), h2 = AHash2(idh + 7.9), h3 = AHash2(idh + 21.3);
            float aa = max(px, 0.05);
            // type: 0 lawn, 1 car park, 2 paved court, 3 playground, 4 concrete yard (industry), 5 sports ground, 6 garden beds,
            //       7 loading yard with truck bays, 8 asphalt, 9 park alley, 10 running track
            float t;
            float dat = step(0.5, gt);
            if (gt < 0.5)
            {
                if (indus > 0.5) t = h < 0.50 ? 4.0 : h < 0.78 ? 1.0 : h < 0.90 ? 2.0 : 0.0;
                else if (resid > 0.5) t = h < 0.52 ? 0.0 : h < 0.74 ? 1.0 : h < 0.90 ? 2.0 : 3.0;
                else t = h < 0.34 ? 2.0 : h < 0.66 ? 1.0 : h < 0.92 ? 0.0 : 3.0;
            }
            else
            {
                t = gt < 2.5 ? 0.0                                                // 1 yard green, 2 school / kindergarten plot: lawn
                  : gt < 3.5 ? 2.0                                                // 3 square
                  : gt < 4.5 ? 1.0                                                // 4 surface parking (only where the data has one)
                  : gt < 5.5 ? 6.0                                                // 5 village garden, low-rise plot: beds, orchard rows
                  : gt < 6.5 ? 0.0                                                // 6 park (the caller draws it as grass)
                  : gt < 7.5 ? 4.0                                                // 7 industry, logistics: plain concrete (the film roads draw the truck yards)
                  : gt < 8.5 ? 0.0                                                // 8 reserve (the caller draws steppe)
                  : gt < 9.5 ? 8.0                                                // 9 drive, turnaround pad
                  : gt < 10.5 ? 0.0                                               // 10 public lot: lawn round its aprons
                  : gt < 11.5 ? 4.0                                               // 11 utility with a building: concrete
                  : gt < 12.5 ? 5.0                                               // 12 sports ground
                  : gt < 13.5 ? 3.0                                               // 13 playground
                  : gt < 14.5 ? 2.0                                               // 14 pavement: drives, aprons, yard paths, rest squares
                  : gt < 16.5 ? 0.0                                               // 15 land without a lot, 16 round the houses: lawn
                  : gt < 17.5 ? 9.0                                               // 17 park alley
                  : 10.0;                                                         // 18 running track
            }
            float plain = dat;                                                   // the data's paving has no planted square
            // the data's lawns and asphalt run on without a step at the cells' edges (the cells only vary the old plan's yards)
            fixed3 lawn = grass * lerp(float3(1, 1, 1), pg, 0.8) * (0.95 + 0.08 * lerp(h2, 0.5, dat));
            fixed3 asph = fixed3(0.37, 0.37, 0.37) * lerp(float3(1, 1, 1), pa, 0.6) * (0.94 + 0.1 * lerp(h3, 0.5, dat));
            fixed3 pave = fixed3(0.66, 0.64, 0.60) * lerp(float3(1, 1, 1), pp, 0.7);
            fixed3 c = lawn; car = 0.0;
            if (t < 0.5)
            {
                // a lawn with a darker mown stripe pattern and a footpath across
                c *= 1.0 - 0.04 * step(0.5, frac(f.x / 6.0)) * saturate(1.0 - px * 0.5);
                float diag = abs((f.x - f.y * 1.2 - (h2 - 0.5) * 20.0)) / 1.56;
                c = lerp(c, pave * 0.97, (1.0 - smoothstep(0.9, 0.9 + aa, diag)) * step(0.55, h3) * (1.0 - dat));
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
                c = lerp(c, lawn, (1.0 - smoothstep(0.0, aa, max(m.x, m.y))) * step(0.4, h2) * (1.0 - plain));
            }
            else if (t < 3.5)
            {
                // playground: rubber surface (crumb), a sand pit, a strip of lawn around; the equipment stands on it (GroundProps.cs).
                // A playground lot of the data (13) is rubber to its own edge (no lawn strip, no pit: its sandbox is a model)
                float2 m = abs(f - cs * 0.5) - float2(12.0, 9.0);
                float hr = dat > 0.5 ? frac((lh + 0.5) * 0.37) : h2;                  // one colour per playground of the data
                fixed3 rub = hr < 0.4 ? fixed3(0.60, 0.36, 0.29) : hr < 0.75 ? fixed3(0.40, 0.50, 0.36) : fixed3(0.38, 0.45, 0.55);
                rub *= 0.94 + 0.12 * ANoise(p * 1.7) * saturate(1.5 - px);
                c = lerp(lawn, rub, max(1.0 - smoothstep(0.0, aa, max(m.x, m.y)), dat));
                float sand = length(f - cs * 0.5 - float2(5.0, 2.0)) - 3.5;
                c = lerp(c, fixed3(0.80, 0.73, 0.58), (1.0 - smoothstep(0.0, aa, sand)) * (1.0 - dat));
                // the data's playground: a grey kerb of 0.25 m round the rubber (it lies to its exact edge)
                c = lerp(c, pave * 0.86, (1.0 - smoothstep(0.25, 0.25 + aa, ge)) * dat);
            }
            else if (t < 4.5)
            {
                // concrete yard of a factory: slabs, oil stains, a gravel patch; the data's yards are one even concrete (no patch that
                // changes at a cell's edge, faint stains)
                c = fixed3(0.60, 0.59, 0.56) * lerp(float3(1, 1, 1), pp, 0.5) * (0.92 + 0.1 * lerp(ANoise(p * 0.15), 0.5, dat * 0.6));
                c = lerp(c, fixed3(0.53, 0.50, 0.45), smoothstep(0.6, 0.75, ANoise(p * 0.05 + h * 9.0)) * (1.0 - dat));
                c *= 1.0 - 0.12 * smoothstep(0.75, 0.9, ANoise(p * 0.3 + 3.0)) * (1.0 - 0.6 * dat);
            }
            else if (t < 5.5)
            {
                // sports ground: a pitch of mown turf with white lines, a red running track round it, lawn beyond; the data's sports
                // ground is turf to its own edge (its track is a piece of its own) with a white line 0.5 m inside it
                float2 m = abs(f - cs * 0.5), e = m - float2(14.0, 10.0), e2 = m - float2(16.5, 12.5);
                float inP = 1.0 - smoothstep(0.0, aa, max(e.x, e.y)), inT = 1.0 - smoothstep(0.0, aa, max(e2.x, e2.y));
                inP = max(inP, dat); inT = max(inT, dat);
                fixed3 turf = fixed3(0.31, 0.47, 0.29) * (0.96 + 0.06 * step(0.5, frac((dat > 0.5 ? q.x : f.x) / 4.0)) * saturate(1.5 - px * 0.5));
                c = lerp(lawn, fixed3(0.62, 0.35, 0.28), inT);
                c = lerp(c, turf, inP);
                float lines = (1.0 - smoothstep(0.08, 0.08 + aa, abs(max(e.x, e.y))))
                            + inP * (1.0 - smoothstep(0.08, 0.08 + aa, m.x)) + inP * (1.0 - smoothstep(0.08, 0.08 + aa, abs(length(f - cs * 0.5) - 4.5)));
                lines = dat > 0.5 ? 1.0 - smoothstep(0.08, 0.08 + aa, abs(ge - 0.5)) : lines;
                c = lerp(c, fixed3(0.88, 0.88, 0.85), saturate(lines) * saturate(1.5 - px));
            }
            else if (t < 6.5)
            {
                // garden of a house: beds and orchard rows of 1.6 m (dark soil, green rows), a grass path every 9 m, rows turned per cell;
                // the data's gardens: rows run on along the whole block (no seams at cell edges), a grass path every 22 m, the crops
                // varying in patches of tens of metres (each house has its own lawn round it, a piece of its own)
                float2 fb = dat > 0.5 ? q : (h2 < 0.5 ? f : f.yx);
                float row = frac(fb.y / 1.6), patch = ANoise(p * 0.035 + lh * 3.1);
                fixed3 soil = fixed3(0.43, 0.37, 0.29) * lerp(float3(1, 1, 1), pp, 0.3), crop = lawn * lerp(fixed3(0.86, 1.06, 0.80), fixed3(0.95, 1.0, 0.86), patch * dat);
                float rowK = dat > 0.5 ? lerp(0.45, 1.0, smoothstep(0.3, 0.7, patch)) : 1.0;
                fixed3 bed = lerp(soil, crop, lerp(0.5, smoothstep(0.30, 0.50, row) * (1.0 - smoothstep(0.80, 0.95, row)), rowK));
                bed = lerp(bed, lerp(soil, crop, 0.55), saturate((px - 0.8) / 1.5));
                float pw = dat > 0.5 ? 22.0 : 9.0;
                c = lerp(bed, lawn, 1.0 - smoothstep(0.7, 0.7 + aa, abs(frac(fb.x / pw) - 0.5) * pw));
            }
            else if (t < 7.5)
            {
                // loading yard: concrete, a darker dock apron along the building side, a row of 4 m truck bays with yellow lines, no trucks
                c = fixed3(0.60, 0.59, 0.56) * lerp(float3(1, 1, 1), pp, 0.5) * (0.92 + 0.1 * ANoise(p * 0.15));
                c = lerp(c, c * 0.80, 1.0 - smoothstep(0.0, aa, f.y - 2.5));
                float bl = (1.0 - smoothstep(0.12, 0.12 + aa, frac(f.x / 4.0) * 4.0)) * step(2.5, f.y) * step(f.y, 20.5);
                c = lerp(c, fixed3(0.84, 0.80, 0.55), bl * 0.8 * saturate(1.5 - px));
            }
            else if (t < 8.5)
            {
                // asphalt of a drive or a turnaround pad
                c = asph * (0.97 + 0.05 * ANoise(p * 0.2));
            }
            else if (t < 9.5)
            {
                // park alley: warm granite slabs of 1.2 × 0.6 m laid across the way, joints fading with distance
                c = fixed3(0.70, 0.66, 0.58) * lerp(float3(1, 1, 1), pp, 0.6) * (0.96 + 0.06 * AHash2(floor(p / float2(1.2, 0.6))));
                float j = min(frac(p.x / 1.2) * 1.2, frac(p.y / 0.6) * 0.6);
                c *= 1.0 - 0.07 * (1.0 - smoothstep(0.03, 0.03 + aa, j)) * saturate(1.2 - px);
            }
            else
            {
                // running track round a school's field (3 m of red rubber): white lane lines 1 m from each of its edges
                c = fixed3(0.62, 0.34, 0.27) * (0.95 + 0.08 * ANoise(p * 1.3) * saturate(1.5 - px));
                c = lerp(c, fixed3(0.90, 0.88, 0.84), (1.0 - smoothstep(0.05, 0.05 + aa, abs(ge - 1.0))) * saturate(1.5 - px));
            }
            // paths along some cell edges
            float ex = min(f.x, cs.x - f.x), ey = min(f.y, cs.y - f.y);
            float px1 = (1.0 - smoothstep(1.1, 1.1 + aa, ex)) * step(0.45, AHash2(float2(id.x + step(cs.x * 0.5, f.x), id.y) + 5.5));
            float py1 = (1.0 - smoothstep(1.1, 1.1 + aa, ey)) * step(0.45, AHash2(float2(id.x, id.y + step(cs.y * 0.5, f.y)) + 8.5));
            float pathK = t < 0.5 ? 1.0 : t < 2.5 ? 0.5 : t < 4.5 ? 1.0 : t < 5.5 ? 0.0 : t < 6.5 ? 0.6 : t < 7.5 ? 0.5 : 0.0;
            c = lerp(c, pave, saturate(px1 + py1) * pathK * (1.0 - plain) * (1.0 - dat));      // the data's lots: no loose paths
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
            // ---- the redrawn map: the piece of the data here (GroundTypes.cs); 0 = no data, the plan colours decide as before. A piece
            //      with a year of its own (its street, its first building, its park) is built in that year, to its own outline: the 40 m
            //      pixels of map_dev only decide where the data says nothing (byte 0)
            float gt = 0.0, gAng = 0.0, gLh = 0.0, gYb = 0.0, gEdge = 1000.0;
            if (_AlatauGtOn > 0.5)
            {
                float4 gq = GroundTypeAt(IN.worldPos.xz, gEdge);
                float rb = floor(gq.r * 255.0 + 0.5);
                gt = fmod(rb, 32.0); gLh = floor(rb / 32.0); gAng = gq.g * 1.5707963; gYb = floor(gq.a * 255.0 + 0.5);
            }
            dev = gt > 0.5 && gYb > 0.5 ? (gYb < 1.5 ? 2000.0 : 2000.0 + gYb) : dev;
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
            float2 dTx = fwidth(uv * _DistTex_TexelSize.zw);                     // pixel size in district texels (the focus border, below)
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
                // ---- the redrawn map (gt, read above): once a piece is developed its type decides what is park (grass) and reserve (steppe)
                float gData = step(0.5, gt), gOn = gData * done;
                green = lerp(green, (abs(gt - 6.0) < 0.5 ? 1.0 : 0.0) * (1.0 - water), gOn);
                open = lerp(open, (abs(gt - 8.0) < 0.5 ? 1.0 : 0.0) * (1.0 - water), gOn);
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
                    ang = gData > 0.5 ? gAng : ang;                                         // a lot of the data: the direction of the lot itself
                    float car = 0.0;
                    fixed3 yard = Yard(wp.xz, ang, resid, civic, indus, px, pg, pp, pa, grass, gt, gLh, gEdge, car);
                    // from far away the yards merge into one calm tone of their quarter (no salt-and-pepper mosaic)
                    fixed3 yAvg = resid * lerp(grass, fixed3(0.47, 0.47, 0.45), 0.35) + civic * fixed3(0.58, 0.57, 0.54) + indus * fixed3(0.57, 0.56, 0.53);
                    yAvg = gData > 0.5 ? YardAvg(gt, grass) : yAvg;
                    yard = lerp(yard, yAvg * (0.96 + 0.08 * fd), saturate((px - 2.5) / 7.0) * 0.75);
                    // a quarter only exists between roads: far from any street (special zones, the airfield, empty plots) the land stays land;
                    // where the data has lots, the lots decide
                    // (once the redrawn map's ground is loaded, land without a piece of it is land too: no old plan's random yards)
                    float noBlock = max(smoothstep(50.0, 61.0, sd), step(0.5, _AlatauGtOn)) * (1.0 - gData);
                    f = lerp(f, land, noBlock * built * done);
                    // inside a motorway interchange (FilmRoads.PublishZones) the land between the ramps is a mown verge, never yards; the
                    // data's own pieces (a park, a lot) next to an interchange keep their ground (item 93)
                    float icz = 0.0;
                    for (int iz = 0; iz < 32; iz++)
                    {
                        if (iz >= (int)_AlatauIcCount) break;
                        float4 zz = _AlatauIcZones[iz];
                        icz = max(icz, 1.0 - smoothstep(zz.z * 0.8, zz.z, distance(wp.xz, zz.xy)));
                    }
                    icz *= 1.0 - gData;
                    f = lerp(f, yard, done * (1.0 - water) * inBlock * (1.0 - green) * (1.0 - open) * (1.0 - noBlock) * (1.0 - icz) * 0.92);      // everywhere the city is built
                    f = lerp(f, verge, icz * done * (1.0 - water) * (1.0 - green));
                    f = lerp(f, verge, town * (1.0 - inBlock));                                   // the whole road corridor is a mown verge
                    // ... except where a drive of the data crosses it to its street (asphalt and its pavements reach the road)
                    float drive = gData * (abs(gt - 9.0) < 0.5 || abs(gt - 14.0) < 0.5 || abs(gt - 17.0) < 0.5 ? 1.0 : 0.0);
                    f = lerp(f, yard, drive * done * (1.0 - water) * (1.0 - inBlock) * (1.0 - icz) * 0.92);
                    f = lerp(f, paved, town * walk * 0.9 * (1.0 - icz) * (1.0 - gData));         // no pavements of the plan's old ramp scribbles;
                                                                                                 // none in the data's lots (street profiles carry theirs)
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
                float rip = 0.55 * saturate(1.2 - px * 0.35);                                  // ripples flatten with distance (no shimmer)
                float3 nW = normalize(float3(-hx * rip, 1.0, -hz * rip));
                float3 view = normalize(_WorldSpaceCameraPos - wp);
                float fres = 0.02 + 0.98 * pow(1.0 - saturate(dot(nW, view)), 5.0);
                float3 refl = AlatauSky(reflect(-view, nW));
                // depth: deep water is dark blue, the shallows along the banks lighter and greener, so the shore reads from any height
                float depth = saturate(wdeep * 1.4 - 0.2) * water;
                float shallow = saturate((0.97 - wsum) * 4.0) * water;                         // the first ~20 m from the bank
                fixed3 body = lerp(fixed3(0.13, 0.24, 0.25), fixed3(0.04, 0.10, 0.15), depth);
                body = lerp(body, fixed3(0.17, 0.27, 0.25), shallow * 0.6);
                // sun glint: a sharp sparkle up close; from afar the ripples are below a pixel, so the same light spreads into a broad
                // soft sheen (a rougher surface) instead of vanishing: the river reads as water from the map height too
                float farW = saturate(px / 8.0);
                float gExp = lerp(220.0, 26.0, farW);
                float glint = pow(saturate(dot(reflect(-_AlatauSunDir.xyz, nW), view)), gExp) * lerp(2.0, 0.55, farW) * (1.0 - _AlatauNight);
                float foam = saturate(1.0 - abs(wsum - 0.40) / 0.05) * (0.5 + 0.5 * ANoise(wp.xz * 0.4 + t * 0.3)) * saturate(1.3 - px * 0.3);
                f = lerp(f, body * 0.55, water);
                f = lerp(f, fixed3(0.85, 0.87, 0.86), foam * 0.35 * water);
                // night: never pitch black: a deep blue-grey surface that mirrors the night sky
                float3 nightW = fixed3(0.040, 0.060, 0.085) * (1.0 - 0.35 * depth) * _AlatauNight;
                // wind slicks: calm and rippled patches a few hundred metres across mirror the sky more or less, so open water is never one flat tone
                float slick = 0.80 + 0.40 * ANoise(wp.xz * 0.0045 + t * 0.004);
                c = f; em = c * _Ambient + (refl * lerp(lerp(0.32, 0.50, farW), 0.95, fres) * 0.75 * slick + _AlatauSunColor.rgb * glint + nightW) * water;
                // at night the lit banks of a built quarter show on the water: a few soft, short columns of light next to the bank,
                // drawn towards the viewer and broken by the ripples; from afar (columns below a few pixels) only a faint warm rim
                {
                    float2 fwd = normalize(view.xz + float2(1e-4, 0)), side = float2(-fwd.y, fwd.x);
                    float sx = dot(wp.xz, side) / 5.0, sy = dot(wp.xz, fwd);
                    float col = fmod(floor(sx), 997.0), cx = frac(sx) - 0.5;          // (small hash arguments: precise on every GPU)
                    float pickL = step(0.80, AHash1(col * 1.37 + fmod(floor(sy / 40.0), 97.0) * 7.1));                // one column in five, each its own lamp
                    float lampK = AHash1(col * 3.11 + 0.5);
                    float wide = 0.18 + 0.12 * lampK;
                    float colm = saturate(1.0 - abs(cx + hx * 0.6) / wide);                             // soft column, wobbling with the ripples
                    float brk = saturate(0.35 + 0.65 * cos(frac(sy / 7.0) * 6.2831853 + hz * 4.0 + t * 1.3));             // broken into dashes by the ripples
                    float bank = saturate((0.97 - wsum) * 4.5);                                          // only next to the bank
                    float sharpL = saturate(2.0 - px * 0.5);                                             // fade the columns once below ~2 px
                    float st = lerp(0.05, colm * colm * brk * pickL, sharpL);
                    float3 cityC = lerp(float3(1.0, 0.74, 0.44), float3(0.95, 0.92, 0.85), lampK);
                    em += cityC * st * bank * done * water * _AlatauNight * 0.45;
                }
                // spotlight wave of the presentation: a ring of light runs over the ground in the colour of the category
                float dR = distance(wp.xz, _AlatauHiWave.xy);
                em += _AlatauHiCol.rgb * exp(-abs(_AlatauHiWave.z - dR) / 55.0) * 0.9 * _AlatauHiOn * (1.0 - saturate(_AlatauHiWave.z / max(_AlatauHiWave.w, 1.0)));
            }
            if (_CityOn > 0.5)
            {
                // seen from afar the film look keeps more of the plan's colour inside the city, so the districts read at a glance
                float farK = saturate((_AlatauCamDist - 14000.0) / 26000.0) * step(0.5, _AlatauFilm) * step(_AlatauMode, 1.5);
                c = lerp(c, lerp(c, cYear, 0.55), farK * inside * (1.0 - waterG));          // water stays water
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
                    // the share of the district in focus round the point, read bilinearly from the four texels round it: its border (share
                    // 0.5) runs smoothly between the texel centres and is drawn as a line about 1.5 px wide (at least ~3 m), not as a band
                    // in the 20 m steps of map_districts that read as a stepped water strip from afar
                    float2 dst = uv * _DistTex_TexelSize.zw - 0.5, di0 = floor(dst), dfr = dst - di0;
                    float2 dc0 = (di0 + 0.5) * _DistTex_TexelSize.xy;
                    float f00 = abs(DistAt(dc0) - _AlatauFocusD) < 0.5 ? 1.0 : 0.0;
                    float f10 = abs(DistAt(dc0 + float2(_DistTex_TexelSize.x, 0)) - _AlatauFocusD) < 0.5 ? 1.0 : 0.0;
                    float f01 = abs(DistAt(dc0 + float2(0, _DistTex_TexelSize.y)) - _AlatauFocusD) < 0.5 ? 1.0 : 0.0;
                    float f11 = abs(DistAt(dc0 + _DistTex_TexelSize.xy) - _AlatauFocusD) < 0.5 ? 1.0 : 0.0;
                    float share = lerp(lerp(f00, f10, dfr.x), lerp(f01, f11, dfr.x), dfr.y);
                    float2 dsh = float2(lerp(f10 - f00, f11 - f01, dfr.y), lerp(f01 - f00, f11 - f10, dfr.x));    // d share / d texel
                    float lw2 = max((abs(dsh.x) * dTx.x + abs(dsh.y) * dTx.y) * 1.5, 0.08);                // no derivative in this branch
                    float nb = 1.0 - smoothstep(0.0, lw2, abs(share - 0.5));
                    bool focus = share > 0.5;
                    fixed3 dc = _AlatauFocusD < 0.5 ? fixed3(0.18, 0.39, 0.69) : _AlatauFocusD < 1.5 ? fixed3(0.85, 0.65, 0.13) : _AlatauFocusD < 2.5 ? fixed3(0.95, 0.45, 0.21) : fixed3(0.20, 0.62, 0.36);
                    if (!focus && did > -0.5)
                    {
                        float lf = dot(c, fixed3(0.299, 0.587, 0.114));
                        c = lerp(fixed3(lf, lf, lf), c, 0.35) * 0.62; em *= 0.55;
                    }
                    if (focus) c = lerp(c, dc, 0.06);
                    float edgeF = saturate(nb) * inside;                                 // on both sides of the border
                    c = lerp(c, dc, edgeF * 0.85); em += dc * edgeF * 0.6;
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
