// Landmarks (Iconic Complex, plants, campus, LRT …): hand-built procedural models with a small set of surface materials.
// Vertex data (LandmarkKit): COLOR = base colour, uv0 = facade metres (along, up), uv1.x = material id, uv1.y = its parameter.
// Materials: 0 solid (plaster / concrete), 1 glass curtain wall (param = floor height), 2 profiled metal, 3 flat roof, 4 paving,
//            5 light (emissive), 6 planting, 7 water, 8 horizontal fins over glass (param = fin spacing), 9 dark steel / rails,
//            10-14 retired (the old Iconic presentation model: lattice glass, white housing, lamellas, copper, lit roads; plain vertex
//            colour if met), 15 the surfaces of the QTwin page of Iconic Complex
//            (its BIM model and the Gate District round it, param = the page's surface tag; AlatauQTwin.cginc) and of the campus page
//            of KAIST (param = its tag + 40).
// Per object (MaterialPropertyBlock): _Reveal = metres above the object's base still visible (construction rises), _Build = 1 while
// under construction (bare frame near the top, orange edge), _Ghost = screen-door "planned" look, _Hi = hover / selection rim.
// Works in the plain maket look and in the film look (_AlatauFilm: sky reflections, night windows) like AlatauCity/Lit.
Shader "AlatauCity/Landmark"
{
    Properties
    {
        _Reveal ("Reveal height (m)", Float) = 100000
        _Build ("Under construction", Range(0, 1)) = 0
        _Ghost ("Planned (ghost)", Range(0, 1)) = 0
        _Hi ("Highlight", Range(0, 1)) = 0
        _Facade ("Facade closed up to (m)", Float) = 100000
        _Land ("Landscaping done", Range(0, 1)) = 1
        _Glow ("Hand-over light sweep (0..1, <0 off)", Float) = -1
        _H ("Object height (m)", Float) = 100
        _Park ("Landscaped grounds (staged by vertex alpha)", Range(0, 1)) = 0
    }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        // drawn a hair in front: the ground ribbons of the plan (roads, the LRT line, rivers) carry a depth offset of their own,
        // and must not show through the plots, the viaduct or the platforms
        Offset -1, -6
        CGPROGRAM
        #pragma surface surf Soft fullforwardshadows vertex:vert addshadow noambient novertexlights noforwardadd nolightmap nodynlightmap nodirlightmap nometa
        #pragma target 3.5
        // the browser compiles every variant when the shader loads: the city has one sun and no ambient light, so the
        // light probe copies only repeat the same code
        #pragma skip_variants LIGHTPROBE_SH
        // the QTwin surfaces (id 15) only in the materials of the models that have them, each with its own part: the Iconic BIM
        // model, the Gate District round it, KAIST. Together and in every landmark they made a shader too big for browsers to compile
        #pragma multi_compile_local __ ALATAU_QT_ICONIC ALATAU_QT_GATE ALATAU_QT_KAIST
        #include "Assets/Shaders/AlatauFilm.cginc"
        #if defined(ALATAU_QT_ICONIC) || defined(ALATAU_QT_GATE) || defined(ALATAU_QT_KAIST)
        #define ALATAU_QTWIN 1
        #include "Assets/Shaders/AlatauQTwin.cginc"
        #endif
        float _Reveal, _Build, _Ghost, _Hi, _Facade, _Land, _Glow, _H, _Park;
        // night (FilmLook): _AlatauDark 0..1 how dark it is (a cool sky fill keeps the models legible), _AlatauLampOn the city's lights
        float _AlatauDark, _AlatauLampOn;
        // buildings of a complex (LandmarkSystem.Parts): x reveal, y build, z facade, w landscaping · x glow, y height, z outline, w progress
        float4 _PartA[8], _PartB[8];
        // BIM look of the construction monitoring (4D page), set only around its own camera: 0 off, 1 built parts as flat slate
        // solids and what is not built yet as a light wire lattice of the design model, 2 the same without the lattice
        float _AlatauBim;
        // "Что изменилось" of the surveys (git-like diff of two dates), drawn only by the monitoring camera (_AlatauDiff around its
        // render). On the monitored object (_DiffOn): _DiffA[k] the stages of building k at the earlier survey (x reveal, y build,
        // z facade, w landscaping; [0] the object's own), _DiffW[k] its progress then. Site pieces carry _DiffTint: 1 new, 2 gone, 3 same.
        float _AlatauDiff, _DiffOn, _DiffTint; float4 _DiffA[8]; float _DiffW[8];
        // fm = facade metres (xy) and material (zw); lp = local height, building of the complex; win = stage window inside the building
        struct Input { float4 color : COLOR; float4 fm; float2 lp; float4 win; float3 worldPos; float3 worldNormal; float4 screenPos; };
        void vert(inout appdata_full v, out Input o)
        {
            UNITY_INITIALIZE_OUTPUT(Input, o); o.fm = float4(v.texcoord.xy, v.texcoord1.xy); o.lp = float2(v.vertex.y, v.texcoord2.x); o.win = v.texcoord3;
            // tree crowns (planting with a tree tag): normals lean up as in AlatauTree, a soft underside instead of a dark ball
            float crownV = step(abs(v.texcoord1.x - 6.0), 0.5) * step(v.texcoord1.y, -6.5);
            v.normal = normalize(lerp(v.normal, float3(0, 1, 0), 0.40 * crownV));
        }
        half4 LightingSoft(SurfaceOutput s, half3 lightDir, half3 viewDir, half atten)
        {
            // Gloss = 1 on tree crowns: foliage lets light through, a half-wrapped diffuse as the film trees (AlatauTree)
            half d = dot(s.Normal, lightDir);
            half nl = lerp(saturate(d), saturate(d * 0.65 + 0.35), s.Gloss);
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten); c.a = s.Alpha;
            half3 hv = normalize(lightDir + viewDir);
            c.rgb += _LightColor0.rgb * (pow(saturate(dot(s.Normal, hv)), 140.0) * s.Specular * atten * 1.6);
            return c;
        }
        // a piece with its own stage window (LandmarkKit.Win): columns, a transfer slab, a wing, a sector of an arc … rises from y0 to y1
        // while the building goes from a to b (progress pw), then gets its facade and its grounds; finished after its window
        void AWin(float4 win, float pw, bool treeTag, inout float rev, inout float bld, inout float fcd, inout float lnd)
        {
            if (win.y <= win.x + 1e-4) return;
            float q = saturate((pw - win.x) / (win.y - win.x));
            float h0 = win.z, h1 = win.w;
            if (q <= 0.0) { rev = -1000.0; bld = 1.0; lnd = 0.0; }
            else if (q >= 0.999) { rev = 100000.0; bld = 0.0; fcd = 100000.0; lnd = 1.0; }
            else if (treeTag) { rev = 100000.0; bld = 1.0; lnd = q; }       // trees: planted one by one over the window
            else { rev = max(h0 + (h1 - h0) * saturate(q / 0.6), h0 + 0.6); bld = 1.0; fcd = h0 + (h1 - h0) * saturate((q - 0.3) / 0.6); lnd = saturate((q - 0.8) / 0.2); }
        }
        // value noise in 3D for the leaf clumps of the crowns (as AlatauTree)
        float LHash3(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
        float LNoise3(float3 p)
        {
            float3 i = floor(p), f = frac(p); f = f * f * (3.0 - 2.0 * f);
            return lerp(lerp(lerp(LHash3(i), LHash3(i + float3(1, 0, 0)), f.x), lerp(LHash3(i + float3(0, 1, 0)), LHash3(i + float3(1, 1, 0)), f.x), f.y),
                        lerp(lerp(LHash3(i + float3(0, 0, 1)), LHash3(i + float3(1, 0, 1)), f.x), lerp(LHash3(i + float3(0, 1, 1)), LHash3(i + float3(1, 1, 1)), f.x), f.y), f.z);
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            // every derivative first, before any branch
            float2 uv = IN.fm.xy, fw = fwidth(uv); float lyW = fwidth(IN.lp.x);
            float2 qfw = fwidth(IN.worldPos.xz); float qfl = length(qfw);
            float2 kxz = mul(unity_WorldToObject, float4(IN.worldPos, 1.0)).xz, kfw = fwidth(kxz);     // plan metres of the object (KAIST)
            float3 n = normalize(IN.worldNormal), view = normalize(_WorldSpaceCameraPos - IN.worldPos);
            // the building of a complex this fragment belongs to (uv2.x, LandmarkKit.Part): its own stages, 0 = the object's values
            float rev = _Reveal, bld = _Build, fcd = _Facade, lnd = _Land, glw = _Glow, hgt = _H, hiP = _Hi;
            // the same at the earlier survey of the diff
            float4 dE0 = _DiffA[0];
            float revE = dE0.x, bldE = dE0.y, fcdE = dE0.z, lndE = dE0.w;
            int pid = (int)round(IN.lp.y);
            if (pid > 0 && pid < 8)
            {
                float4 pa = _PartA[pid], pb = _PartB[pid], de = _DiffA[pid];
                rev = pa.x; bld = pa.y; fcd = pa.z; lnd = pa.w; glw = pb.x; hgt = pb.y; hiP = max(hiP, pb.z * 0.4);
                revE = de.x; bldE = de.y; fcdE = de.z; lndE = de.w;
                bool treeTag = IN.fm.zw.y < -6.5;
                AWin(IN.win, pb.w, treeTag, rev, bld, fcd, lnd);
                AWin(IN.win, _DiffW[pid], treeTag, revE, bldE, fcdE, lndE);
            }
            // early landscape (LandmarkKit.GreenTag / ParkTreeTag) of the plot itself (part 0): lawns, paths, water and trees laid out
            // before the buildings — not cut by the rising frame and not an earth site. Inside a building of a complex they follow it.
            bool green = IN.fm.zw.y < -4.5 && IN.fm.zw.y > -5.5;
            bool parkTree = IN.fm.zw.y < -8.5;
            bool keep = pid <= 0 && (parkTree || green);
            bool bim = _AlatauBim > 0.5;
            bool wire = bim && _AlatauBim < 1.5 && pid > 0 && !keep && rev - IN.lp.x < 0.0;
            if (bim && IN.fm.zw.y < -6.5) clip(-1.0);                         // BIM: no trees
            // the diff: what stands now and stood at the earlier survey; what stood then and is gone now is kept, as a red ghost
            bool dOn = _AlatauDiff > 0.5 && (_DiffOn > 0.5 || _DiffTint > 0.5) && !bim;
            bool dSite = _DiffTint > 0.5;
            bool wasV = (keep && dE0.x > -999.0) || revE - IN.lp.x >= 0.0;
            bool gone = dOn && (dSite ? _DiffTint > 1.5 && _DiffTint < 2.5 : !keep && rev - IN.lp.x < 0.0 && wasV);
            if (!keep && !wire && !(gone && !dSite)) clip(rev - IN.lp.x);
            // BIM lines: a floor every 4 m and a grid line every 6 m along the facade (on walls), screen-width thin
            float bimWall = 1.0 - saturate(abs(n.y) * 3.0);
            float bimFloor = 1.0 - saturate(abs(frac(IN.lp.x / 4.0 + 0.5) - 0.5) * 4.0 / max(lyW * 1.2, 1e-4));
            float bimGrid = 1.0 - saturate(abs(frac(uv.x / 6.0 + 0.5) - 0.5) * 6.0 / max(fw.x * 1.2, 1e-4));
            float bimLine = max(bimFloor, bimGrid) * bimWall;
            if (wire) clip(bimLine - 0.3);
            if (_Ghost > 0.01)
            {
                float2 sp = IN.screenPos.xy / max(IN.screenPos.w, 1e-4) * _ScreenParams.xy;
                float ign = frac(52.9829189 * frac(dot(floor(sp), float2(0.06711056, 0.00583715))));
                clip((1.0 - 0.72 * _Ghost) - ign);
            }
            int id = (int)round(IN.fm.zw.x);
            bool tree = IN.fm.zw.y < -6.5;                                   // LandmarkKit.TreeTag: planted at the end of construction
            float prm = tree || keep || green ? 3.0 : max(IN.fm.zw.y, 0.05);
            // staged landscaping: vertex alpha = 1 - stage; a part with a later stage starts later and finishes by lnd = 1.
            // (objects without stages carry alpha 1 → stage 0 → exactly lnd as before)
            float stg = 1.0 - IN.color.a, st0 = stg * 0.75;
            float land = saturate((lnd - st0) / max(1.0 - st0, 0.05));
            if (_Park > 0.5) clip(lnd - st0 + 0.015);                    // grounds not started yet: the old terrain shows through
            if (tree && (!parkTree || pid > 0) && bld > 0.5) clip(land * 1.15 - AHash2(floor(IN.worldPos.xz / 4.0)));
            // photo materials (film look): paving slabs and lawn grass, sampled before any branch
            AMat mPave = AlatauMat(IN.worldPos.xz, 7.0), mGrass = AlatauMat(IN.worldPos.xz, 8.0), mAsph = AlatauMat(IN.worldPos.xz, 6.0);
            // the same photos once more at a coarse scale (a few tens of metres): breaks the repeat of the tiles from the air
            float macro = ANoise(IN.worldPos.xz * 0.021) * 0.6 + ANoise(IN.worldPos.xz * 0.083) * 0.4;
            float3 a = IN.color.rgb; float3 emit = 0; float spec = 0;
            float film = step(0.5, _AlatauFilm);
            float3 rdir = reflect(-view, n);
            float fres = 0.04 + 0.96 * pow(1.0 - saturate(dot(n, view)), 5.0);
            float3 plainSky = lerp(float3(0.42, 0.45, 0.50), float3(0.62, 0.68, 0.76), saturate(rdir.y * 2.0 + 0.3));
            float3 sky = lerp(plainSky, AlatauSky(rdir), film);
            float night = _AlatauNight * film;
            float grain = ANoise(IN.worldPos.xz * 0.37 + IN.worldPos.y * 0.21);

            bool qSoft = false;
            #ifdef ALATAU_QTWIN
            if (id == 15)
            {
                // the QTwin page's own surfaces, worked out in linear light; metals put their colour into the reflection of the sky
                int qt = (int)round(prm); QSurf q;
                #if defined(ALATAU_QT_KAIST)
                q = KaistSurface(qt - 40, pid, uv.x, uv.y, fw.x, fw.y, kxz, kfw, qfl, n, night);
                #else
                q = QTwinSurface(qt, pid, uv.x, uv.y, fw.x, fw.y, IN.worldPos.xz, qfw, qfl, n, night);
                #endif
                QResolve(q, qfl);
                // photo detail on the ground of the page: lawns (grass), plazas and paths (paving), streets (asphalt), with a
                // broad variation so large areas do not look printed
                if (n.y > 0.6 && (q.soft || qt == 31))
                {
                    bool isGrass = q.pat == QP_GRASS || q.pat == QP_GARDEN || q.pat == QP_SLOPE;
                    bool isAsph = qt == 31;
                    float3 pp = isGrass ? mGrass.pattern : isAsph ? mAsph.pattern : mPave.pattern;
                    float pao = isGrass ? mGrass.ao : isAsph ? mAsph.ao : mPave.ao;
                    float k = (isGrass ? 0.70 : isAsph ? 0.45 : 0.55) * film;
                    q.col *= lerp(float3(1, 1, 1), pp * lerp(1.0, pao, 0.5), k) * lerp(1.0, 0.86 + 0.28 * macro, film);
                    // lawns as the city's grass: a natural olive instead of the page's bright green, with broad mown patches
                    if (isGrass) q.col = lerp(q.col, q.col.ggg * float3(0.80, 1.0, 0.55), 0.30 * film) * lerp(1.0, 0.84 + 0.32 * ANoise(IN.worldPos.xz * 0.0065 + 2.0), film);
                }
                float3 f0 = lerp(float3(0.04, 0.04, 0.04), q.col, q.metal);
                float gloss = (1.0 - q.rough) * (1.0 - q.rough);
                a = pow(max(q.col * (1.0 - 0.8 * q.metal), 1e-5), 0.4545);
                // the reflection in linear light, so gold reflects gold (not a grey sky over it); a fill as the page's hemisphere light
                float3 refl = sky * sky * (f0 + (1.0 - f0) * fres) * gloss;
                emit = pow(max(q.emis + refl, 1e-5), 0.4545) + a * 0.16;
                spec = gloss * 0.6; qSoft = q.soft;
            }
            #endif
            if (id == 1 || id == 8)
            {
                // glass curtain wall: slab bands per floor, thin mullions; (8) white horizontal fins in front of the glass
                float fh = id == 1 ? prm : prm;
                float2 cell = float2(uv.x / 1.5, uv.y / fh), cw = fw / float2(1.5, fh);
                float2 q = frac(cell); float2 idc = floor(cell);
                float detail = saturate(1.4 - max(cw.x, cw.y) * 2.0);
                float slab = id == 1 ? 1.0 - saturate((q.y - 0.16) / max(cw.y, 1e-4) + 0.5) : 0.0;
                float fin = id == 8 ? 1.0 - saturate((q.y - 0.30) / max(cw.y, 1e-4) + 0.5) : 0.0;
                float mull = 1.0 - saturate((min(q.x, 1.0 - q.x) - 0.035) / max(cw.x, 1e-4) + 0.5);
                float h = AHash2(idc + 17.0);
                float3 glass = a * (0.80 + 0.40 * h);
                float mirror = 0.42 + 0.55 * fres;
                float lit = step(1.0 - (0.12 + 0.55 * night), AHash2(idc * 1.7 + 3.1)) * night;
                float3 lamp = lerp(float3(1.0, 0.80, 0.50), float3(1.0, 0.93, 0.78), h) * lit * 1.3;
                float3 frameC = id == 8 ? float3(0.93, 0.93, 0.91) : a * 0.6 + float3(0.30, 0.31, 0.33);
                float solidPart = saturate(max(max(slab, fin), mull * 0.85));
                float3 nearA = lerp(glass, frameC, solidPart);
                float3 nearE = (sky * mirror + lamp) * (1.0 - solidPart);
                float share = id == 8 ? 0.62 : 0.80;
                float3 farA = lerp(frameC, glass, share);
                float3 farE = (sky * mirror * share) + float3(1.0, 0.85, 0.6) * night * 0.25 * share;
                a = lerp(farA, nearA, detail); emit = lerp(farE, nearE, detail);
                spec = (1.0 - solidPart * detail) * 0.9;
            }
            // (materials 10-14, the lattice, housing, lamellas, copper and roads of the old Iconic presentation model, are gone with it:
            // Iconic is drawn from QTwin, and every material here is compiled by the browser whether used or not)
            // (two chains: one long else-if chain overflows the parser of the surface shader analysis)
            if (id == 2)
            {
                // profiled metal: vertical ribs every 0.8 m
                float rib = 1.0 - saturate((abs(frac(uv.x / 0.8) - 0.5) - 0.18) / max(fw.x / 0.8, 1e-4) + 0.5);
                float det = saturate(1.3 - fw.x / 0.8 * 2.0);
                a *= lerp(1.0, 0.86 + 0.14 * rib, det) * (0.97 + 0.06 * grain);
                spec = 0.25; emit = sky * 0.05 * fres;
            }
            else if (id == 3)
            {
                a *= 0.93 + 0.10 * grain;
            }
            else if (id == 4)
            {
                // paving: 1.2 m slabs
                float2 t = abs(frac(uv / 1.2) - 0.5); float2 tw = fw / 1.2;
                float joint = 1.0 - saturate((0.47 - max(t.x, t.y)) / max(max(tw.x, tw.y), 1e-4) + 0.5);
                a *= (1.0 - 0.10 * joint * saturate(1.3 - max(tw.x, tw.y) * 3.0)) * (0.95 + 0.08 * grain);
                if (n.y > 0.6) a *= lerp(float3(1, 1, 1), mPave.pattern * lerp(1.0, mPave.ao, 0.5), 0.75 * film);
            }
            else if (id == 5)
            {
                emit = a * (0.9 + 0.8 * film * _AlatauNight); a *= 0.35;
            }
            else if (id == 6)
            {
                float g2 = ANoise(IN.worldPos.xz * 0.11 + 4.0);
                if (tree)
                {
                    // a crown of the film trees: leaf clumps, warmer sunlit tops, the sky on the edge of the leaves
                    float cl = LNoise3(IN.worldPos * 1.35) * 0.65 + LNoise3(IN.worldPos * 3.4 + 7.0) * 0.35;
                    a *= lerp(0.74, 1.12, smoothstep(0.25, 0.8, cl));
                    a *= lerp(float3(0.90, 0.95, 1.05), float3(1.07, 1.04, 0.90), saturate(n.y * 0.5 + 0.5));
                    float rimT = pow(1.0 - saturate(dot(view, n)), 3.0);
                    emit += film * (lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.4) * a * 0.25 + _AlatauSkyHorizon.rgb * rimT * 0.10 * (0.6 + 0.4 * cl));
                }
                else
                {
                    a *= 0.78 + 0.30 * grain + 0.12 * g2;
                    if (n.y > 0.6) a *= lerp(float3(1, 1, 1), mGrass.pattern * lerp(1.0, mGrass.ao, 0.6), 0.85 * film);
                }
            }
            else if (id == 7)
            {
                a = lerp(a, a * 0.6, grain * 0.3); emit = sky * (0.20 + 0.70 * fres); spec = 1.0;
            }
            else if (id == 9)
            {
                spec = 0.35; emit = sky * 0.08 * fres;
            }
            else if (id == 0 || id > 15)
            {
                // solid: plaster / precast panels with faint joints every floor height (param) and 3 m
                float2 t = float2(frac(uv.x / 3.0), frac(uv.y / prm));
                float2 tw = fw / float2(3.0, prm);
                float joint = (1.0 - saturate(min(t.y, 1.0 - t.y) / max(tw.y * 1.2, 0.02))) * 0.07 + (1.0 - saturate(min(t.x, 1.0 - t.x) / max(tw.x * 1.2, 0.01))) * 0.04;
                a *= (1.0 - joint * saturate(1.3 - max(tw.x, tw.y) * 2.5)) * (0.96 + 0.07 * grain);
            }

            // under construction (stages driven by LandmarkSystem):
            //  · above the closed facade and below the working level: the bare frame — concrete slabs every floor, dark open floors
            //    with columns between them, an orange safety edge on the working level;
            //  · the ground of the plot stays an earth site with tyre tracks until paving and planting (lnd)
            if (bld > 0.5 && !keep)
            {
                bool ground = (IN.lp.x < 1.2 || _Park > 0.5) && n.y > 0.6 && !tree;
                bool raised = !ground && IN.lp.x >= 1.2 && (id == 4 || (id == 6 && !tree) || id == 7 || qSoft);
                if (raised)
                {
                    // terraces and roof gardens above the ground: a bare concrete slab until they are paved and planted (never soil in the air)
                    float l2 = saturate(land * 1.5 - 0.5);
                    float3 slabC = float3(0.64, 0.63, 0.60) * (0.92 + 0.10 * grain);
                    a = lerp(slabC, a, l2); emit *= l2; spec *= l2;
                }
                else if (ground || id == 4 || (id == 6 && !tree) || id == 7 || qSoft)
                {
                    float tracks = smoothstep(0.35, 0.5, abs(frac(dot(IN.worldPos.xz, float2(0.083, 0.052))) - 0.5)) * 0.08;
                    float3 soil = float3(0.50, 0.42, 0.32) * (0.82 + 0.30 * grain + 0.10 * ANoise(IN.worldPos.xz * 0.05)) - tracks;
                    float l = ground || id == 4 || qSoft ? land : saturate(land * 1.5 - 0.5);
                    a = lerp(soil, a, l); emit *= l; spec *= l;
                }
                else if (!tree && IN.lp.x > fcd && IN.lp.x > 1.2)
                {
                    float fh = (id == 1 || id == 8 || id == 0) ? max(prm, 3.0) : 4.0;
                    float q = frac(IN.lp.x / fh), qw = max(lyW / fh, 1e-4);
                    float slab = 1.0 - saturate((q - 0.16) / qw + 0.5);
                    float colm = 1.0 - saturate((abs(frac(uv.x / 7.5) - 0.5) - 0.44) / max(fw.x / 7.5, 1e-4) + 0.5);
                    float3 concrete = float3(0.66, 0.65, 0.62) * (0.92 + 0.10 * grain);
                    float3 inside = float3(0.09, 0.09, 0.10) + concrete * 0.08;
                    float wall = 1.0 - saturate(abs(n.y) * 3.0);
                    float3 frameA = lerp(concrete, lerp(inside, concrete, saturate(slab + colm)), wall);
                    // the facade crew works a few metres above the closed part: a band of scaffold mesh
                    float net = saturate(1.0 - (IN.lp.x - fcd) / 6.0) * wall;
                    frameA = lerp(frameA, float3(0.20, 0.42, 0.30) * (0.9 + 0.2 * grain), net * 0.85);
                    a = frameA; emit = 0; spec = 0.05;
                    float edge = saturate(1.0 - (rev - IN.lp.x) / 2.2) * wall;          // the safety edge on the walls (not over a whole roof that happens to be there)
                    a = lerp(a, float3(0.98, 0.52, 0.10), edge); emit += float3(0.98, 0.52, 0.10) * edge * 0.35;
                }
            }
            // hand-over: a warm band of light runs up the building once
            if (glw >= 0.0)
            {
                float band = exp(-abs(IN.lp.x - glw * hgt * 1.15) / max(hgt * 0.04, 3.0));
                emit += float3(1.0, 0.86, 0.58) * band * 1.4 + a * (1.0 - glw) * 0.18;
            }
            if (_Ghost > 0.01) { a = lerp(a, float3(0.70, 0.78, 0.92), 0.55 * _Ghost); emit += float3(0.10, 0.16, 0.26) * _Ghost; spec = 0; }

            // ambient: in the film look shaded by facing and height like the city (AlatauLit), else spherical harmonics
            half3 amb = ShadeSH9(half4(n, 1.0));
            if (film > 0.5) amb = lerp(_AlatauSkyGround.rgb * 0.62, lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.5), n.y * 0.5 + 0.5) * 0.84 * lerp(0.75, 1.0, saturate(IN.lp.x / 12.0));
            // at night: the sky glow over a lit city as fill, and warm floodlights at the foot of the facades washing up the walls;
            // Iconic, the hero of the night, gets a stronger wash that carries up to the top of the tower
            float darkF = _AlatauDark * film, lampF = _AlatauLampOn * film;
            amb += darkF * half3(0.03, 0.04, 0.065);
            float wallU = (1.0 - saturate(abs(n.y) * 2.0)) * (tree ? 0.0 : 1.0);
            float upl = exp(-max(IN.lp.x, 0.0) / max(hgt * 0.22, 12.0)) * wallU;
            #if defined(ALATAU_QT_ICONIC)
            emit += a * float3(1.0, 0.80, 0.56) * lampF * (upl * 0.9 + wallU * (0.04 + 0.10 * saturate(IN.lp.x / max(hgt, 1.0))));
            #else
            emit += a * float3(1.0, 0.80, 0.56) * lampF * upl * 0.45;
            #endif
            float rim = pow(1.0 - saturate(dot(n, view)), 4.0);
            emit += hiP * (rim * 0.7 + 0.03) * float3(0.85, 0.30, 0.95);
            o.Albedo = a; o.Emission = emit + a * amb; o.Specular = spec; o.Alpha = 1; o.Gloss = tree && id == 6 ? 1.0 : 0.0;
            if (dOn)
            {
                // like a diff before a push: new in blue (the structure deep blue, the facade and the grounds light blue), gone in red,
                // the rest grey and quiet so the change reads at a glance
                float stE = st0, landE = saturate((lndE - stE) / max(1.0 - stE, 0.05));
                bool flat = IN.lp.x < 1.2 && n.y > 0.6;
                bool newS = dSite ? _DiffTint < 1.5 : !keep && !tree && IN.lp.x > revE + 0.05;
                bool newF = !dSite && !newS && (((bld < 0.5 || IN.lp.x < fcd) && bldE > 0.5 && IN.lp.x > fcdE + 0.05 && !tree)
                            || ((tree || flat || keep) && land > landE + 0.04));
                if (tree && !dSite && !newS && landE * 1.15 < AHash2(floor(IN.worldPos.xz / 4.0))) newF = true;
                float lum = dot(a, float3(0.30, 0.59, 0.11));
                float3 grey = lerp(float3(0.50, 0.52, 0.55), lum.xxx, 0.30);        // a clay model: what did not change
                float dLine = bimLine * 0.55;
                if (gone)
                {
                    float2 sp = IN.screenPos.xy / max(IN.screenPos.w, 1e-4) * _ScreenParams.xy;
                    float ign = frac(52.9829189 * frac(dot(floor(sp), float2(0.06711056, 0.00583715))));
                    clip(0.62 - ign);
                    o.Albedo = float3(0.95, 0.20, 0.18) * 0.35; o.Specular = 0;
                    o.Emission = float3(1.0, 0.24, 0.20) * (0.62 + dLine);
                }
                else if (newS)
                {
                    float3 b = float3(0.16, 0.46, 1.0);
                    o.Albedo = lerp(grey, b, 0.78); o.Specular = 0.2;
                    o.Emission = b * (0.30 + dLine) + o.Albedo * amb;
                }
                else if (newF)
                {
                    float3 b = float3(0.50, 0.80, 1.0);
                    o.Albedo = lerp(grey, b, 0.62); o.Specular = 0.15;
                    o.Emission = b * (0.14 + dLine * 0.6) + o.Albedo * amb;
                }
                else { o.Albedo = grey; o.Specular = 0; o.Emission = grey * (amb * 1.05 + 0.06) * (1.0 - 0.18 * dLine); }
            }
            if (bim)
            {
                // flat slate solids shaded by facing; the ground of the plot dark; a frame without its facade concrete-light; the
                // working level keeps its orange edge; the design model not built yet glows as a thin blue lattice
                float3 sl = float3(0.40, 0.45, 0.53);
                if (IN.lp.x < 1.2 && n.y > 0.6) sl = float3(0.17, 0.19, 0.23);
                else if (bld > 0.5 && IN.lp.x > fcd && IN.lp.x > 1.2) sl = float3(0.63, 0.65, 0.68);
                float bsh = 0.58 + 0.30 * saturate(n.y * 0.5 + 0.5) + 0.14 * saturate(dot(n, normalize(float3(0.45, 0.25, -0.35))));
                float3 bc = sl * bsh * (1.0 - 0.22 * bimLine);
                float edgeB = bld > 0.5 ? saturate(1.0 - (rev - IN.lp.x) / 1.6) * bimWall : 0.0;
                bc = lerp(bc, float3(0.98, 0.52, 0.10), edgeB);
                float rimB = pow(1.0 - saturate(dot(n, view)), 3.0);
                o.Albedo = bc * 0.22; o.Specular = 0;
                o.Emission = bc * 0.82 + float3(0.55, 0.70, 0.95) * rimB * 0.12 + hiP * (rimB * 0.7 + 0.03) * float3(0.85, 0.30, 0.95);
                if (wire) { o.Albedo = 0; o.Emission = float3(0.42, 0.62, 0.92) * (0.45 + 0.4 * bimLine); }
            }
        }
        ENDCG
    }
    FallBack "Diffuse"
}
