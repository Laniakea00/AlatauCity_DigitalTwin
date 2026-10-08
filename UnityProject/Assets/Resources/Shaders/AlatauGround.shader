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
        #pragma surface surf Soft fullforwardshadows
        #pragma target 3.5
        #include "Assets/Shaders/AlatauFilm.cginc"
        sampler2D _MainTex, _NatTex, _DevTex; half _Ambient; fixed4 _Earth;
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauDevK, _AlatauMode, _AlatauBlockOn;
        sampler2D _AlatauBlockTex, _CityTex, _DistTex; float _CityOn; fixed4 _AlatauEdgeCol; float _AlatauCamDist, _AlatauFocusD;
        float4 _DistTex_TexelSize;
        // district id from map_districts.png (point sampled): 30 Gate, 90 Golden, 150 Growing, 210 Green, 0 outside
        float DistAt(float2 uv) { float v = tex2Dlod(_DistTex, float4(uv, 0, 0)).r * 255.0; return v < 15.0 ? -1.0 : floor((v - 30.0) / 60.0 + 0.5); }
        struct Input { float2 uv_MainTex; float3 worldPos; };
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
            half3 em = c * _Ambient;
            if (_AlatauFilm > 0.5 && _AlatauMode < 1.5)
            {
                // film look: the zoning colours become a hint, parks turn green, open land a pale steppe, water mirrors the sky
                fixed3 c0 = plan;
                float lum = dot(c, fixed3(0.299, 0.587, 0.114)), sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
                float water = saturate((c.b - c.r) * 5.0 - 0.6) * saturate((c.g - c.r) * 8.0 + 0.3);
                float green = saturate((c.g - max(c.r, c.b)) * 6.0) * (1.0 - water);
                float open = saturate((0.50 - lum) * 5.0) * saturate(1.0 - sat * 7.0) * (1.0 - water);     // land the plan leaves alone
                float n1 = ANoise(IN.worldPos.xz * 0.045), n2 = ANoise(IN.worldPos.xz * 0.011 + 7.0), n3 = ANoise(IN.worldPos.xz * 0.9);
                fixed3 f = lerp(fixed3(lum, lum, lum), c, 0.42);
                f = lerp(f, fixed3(0.80, 0.78, 0.73), 0.30) + (1.0 - lum) * 0.10;                         // lift the dark tones
                f = lerp(f, lerp(fixed3(0.61, 0.61, 0.52), fixed3(0.70, 0.68, 0.59), n2) * (0.94 + 0.12 * n1), open * 0.72);
                f = lerp(f, lerp(fixed3(0.36, 0.48, 0.27), fixed3(0.48, 0.57, 0.33), n1) * (0.94 + 0.12 * n2), green * 0.85);
                f *= 0.975 + 0.03 * n1 + 0.02 * n3;
                // photo textures: grass in the parks, dry grass on open land, paving in the built-up quarters (pattern only, the hue stays)
                float3 pg = AlatauMat(IN.worldPos.xz, 8.0).pattern, ps = AlatauMat(IN.worldPos.xz, 9.0).pattern, pp = AlatauMat(IN.worldPos.xz, 7.0).pattern;
                float built = saturate(1.0 - green - open - water);
                f *= lerp(float3(1, 1, 1), pg, green * 0.75) * lerp(float3(1, 1, 1), ps, open * 0.55) * lerp(float3(1, 1, 1), pp, built * 0.45);
                if (_AlatauBlockOn > 0.5)
                {
                    // city blocks: metres from the edge of the nearest road corridor (map_blocks), negative inside the corridor.
                    // A verge of grass beside the road, a kerb line, a paved walk around the block: sharp at any zoom, and only where the city is built.
                    float sd = (tex2D(_AlatauBlockTex, uv).r * 255.0 - 128.0) * 0.5, sw = max(fwidth(sd), 0.02);
                    float inBlock = saturate(sd / sw + 0.5), walk = inBlock * saturate((3.2 - sd) / sw + 0.5), kerb = saturate(1.0 - abs(sd - 0.15) / max(sw, 0.25));
                    float town = done * saturate((48.0 - sd) / 8.0) * (1.0 - water);          // near a road, and developed by now
                    fixed3 verge = lerp(fixed3(0.40, 0.50, 0.30), fixed3(0.47, 0.55, 0.33), n1) * lerp(float3(1, 1, 1), pg, 0.7);
                    fixed3 paved = fixed3(0.74, 0.72, 0.68) * lerp(float3(1, 1, 1), pp, 0.75);
                    // inside the block, by the land use the plan gives it (read from the plan's colour): lawns between the houses of a
                    // housing quarter, a paved square with planted patches in civic and commercial quarters, a concrete yard in industry
                    float resid = saturate((min(c0.r, c0.g) - c0.b) * 6.0), indus = saturate((min(c0.r, c0.b) - c0.g) * 8.0), civic = saturate(1.0 - resid - indus);
                    float patch = smoothstep(0.45, 0.62, ANoise(IN.worldPos.xz * 0.02 + 11.0));
                    fixed3 lawn = lerp(fixed3(0.43, 0.52, 0.32), fixed3(0.50, 0.57, 0.35), n1) * lerp(float3(1, 1, 1), pg, 0.7);
                    fixed3 yard = fixed3(0.62, 0.62, 0.61) * lerp(float3(1, 1, 1), pp, 0.6);
                    fixed3 inside = lawn * resid + lerp(paved, lawn, patch * 0.8) * civic + yard * indus;
                    f = lerp(f, inside, done * (1.0 - water) * inBlock * (1.0 - green) * (1.0 - open) * 0.82);      // everywhere the city is built, not only beside a road
                    f = lerp(f, verge, town * (1.0 - inBlock) * step(-40.0, sd));
                    f = lerp(f, paved, town * walk * 0.9);
                    f *= 1.0 - 0.30 * kerb * town * saturate(1.6 - sw * 2.0);
                }
                float3 view = normalize(_WorldSpaceCameraPos - IN.worldPos);
                float fres = 0.04 + 0.96 * pow(1.0 - saturate(view.y), 5.0);
                float3 rdir = reflect(-view, normalize(float3((n1 - 0.5) * 0.04, 1.0, (n3 - 0.5) * 0.04)));
                f = lerp(f, fixed3(0.10, 0.19, 0.25), water);
                c = f; em = c * _Ambient + AlatauSky(rdir) * (0.18 + 0.75 * fres) * water;
            }
            if (_CityOn > 0.5)
            {
                // seen from afar the film look keeps more of the plan's colour inside the city, so the districts read at a glance
                float farK = saturate((_AlatauCamDist - 14000.0) / 26000.0) * step(0.5, _AlatauFilm) * step(_AlatauMode, 1.5);
                c = lerp(c, lerp(c, cYear, 0.55), farK * inside);
                // outside: the same land, desaturated and darker the farther it is from the city; water keeps a cool hint
                float lumO = dot(c, fixed3(0.299, 0.587, 0.114));
                float wat = saturate((nat.b - nat.r) * 5.0 - 0.6) * saturate((nat.g - nat.r) * 8.0 + 0.3);
                fixed3 ctx = lerp(fixed3(lumO, lumO, lumO), c, 0.20) * lerp(0.66, 0.48, saturate(-sdm / 9000.0));
                ctx = lerp(ctx, fixed3(0.16, 0.24, 0.31), wat * 0.75);
                c = lerp(ctx, c, inside);
                em = lerp(ctx * _Ambient * 0.6, em, inside);
                // the boundary: a thin warm line (about 1.5 px or 14 m, whichever is wider) and a soft light rim inside it
                float lw = max(sdw * 1.4, 14.0);
                float bline = exp(-abs(sdm) / lw);
                float rim = exp(-max(sdm, 0.0) / 420.0) * inside;
                fixed3 gold = fixed3(0.98, 0.80, 0.45);
                c = lerp(c, gold, bline * 0.55) + rim * 0.035;
                em += gold * bline * 0.65;
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
