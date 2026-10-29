// Roads of the film look: ribbons built by FilmRoads.cs from the road graph of the twin (roads.json).
// uv  = (metres across from the centre line, metres along the edge, along of a T-junction in the middle of the road, set back of its
//        crossings or 0)
// uv2 = (half width of the carriageway, 0 = pavement ribbon / 1 = carriageway ribbon, length of the edge, lanes per direction;
//        negative = a one-way carriageway with that many lanes: no centre line, lane lines across the whole width)
// uv2 (TEXCOORD2) = year of opening in the four scenarios (picked by _AlatauScenIdx); the ribbon appears with the timeline like the buildings.
// uv3 (TEXCOORD3) = (lamp spacing m, lamp placement mode + 8 * class, crossing set back from the start, from the end; 0 = none):
//        street lamps by FilmLamps.Rule (mode 1 median mast, 2 both sides, 3 right of a one-way carriageway, 4 one side of a street,
//        5 = a junction patch; class 0 street, 1 main, 2 motorway): their light lies on the asphalt at night (_AlatauLampOn);
//        zebra crossings (stripes 0.5 m, 4 m wide on streets, 5 m on main roads) with a stop line 3 m before them.
// _AlatauMaket = (x, z, radius, on): round Iconic Complex the lane lines are strips of cool light, as on its presentation model.
Shader "AlatauCity/Road"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry-5" }
        Offset -1, -2
        CGPROGRAM
        #pragma surface surf Lambert fullforwardshadows vertex:vert
        #pragma target 3.5
        #include "Assets/Shaders/AlatauFilm.cginc"
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauScenIdx, _AlatauLampOn; float4 _AlatauMaket;
        struct Input { float4 road; float4 dims; float4 years; float4 lamp; float3 worldPos; };
        void vert(inout appdata_full v, out Input o) { UNITY_INITIALIZE_OUTPUT(Input, o); o.road = v.texcoord; o.dims = v.texcoord1; o.years = v.texcoord2; o.lamp = v.texcoord3; }
        float Line(float d, float halfW, float aa) { return saturate((halfW - abs(d)) / max(aa, 1e-4) + 0.5); }
        // a band [a, b] along the road, antialiased
        float Band(float v, float a, float b, float aa) { return saturate((v - a) / max(aa, 1e-4) + 0.5) * saturate((b - v) / max(aa, 1e-4) + 0.5); }
        // light of the street lamps on the ground at (x across, v along) of a road of length len (FilmLamps.Rule / Height / At)
        float LampPool(float x, float v, float hw, float len, float4 L)
        {
            // modes (FilmLamps.Rule): 1 median mast, 2 both sides, 3 / 6 one side of a one-way carriageway (x < 0 / x > 0), 4 one side of
            // a street, 5 a junction patch; each compared on its own exact value
            float mode = floor(fmod(L.y + 0.01, 8.0) + 0.5), cls = floor(L.y / 8.0 + 0.01), stepL = max(L.x, 1.0);
            float isMast = step(abs(mode - 1.0), 0.1), isBoth = step(abs(mode - 2.0), 0.1), isOneR = step(abs(mode - 3.0), 0.1);
            float isStreet = step(abs(mode - 4.0), 0.1), isJunction = step(abs(mode - 5.0), 0.1);
            float H = isMast > 0.5 ? 14.0 : isBoth > 0.5 ? 10.0 : isStreet > 0.5 ? 7.0 : (cls > 1.5 ? 12.0 : cls > 0.5 ? 10.0 : 8.0);
            float r2 = (0.65 * H) * (0.65 * H);
            float head = hw - (cls > 1.5 ? 1.1 : cls > 0.5 ? 0.8 : 0.3);         // kerb + set back - arm (FilmLamps.Back / Arm)
            float hx = isMast > 0.5 ? 2.5 : isOneR > 0.5 ? -head : head;   // 2, 4 and 6 at x > 0 (2 also at -x)
            float twoHeads = max(isMast, isBoth);                                // mast (two arms) and both-sides: a head at +hx and -hx
            float k0 = floor(v / stepL - 0.5), sum = 0.0;
            for (int i = 0; i < 2; i++)
            {
                float vk = (k0 + i + 0.5) * stepL, ok = step(14.0, vk) * step(vk, len - 14.0), dv = v - vk;
                float d1 = dv * dv + (x - hx) * (x - hx), d2 = dv * dv + (x + hx) * (x + hx);
                sum += ok * (exp(-d1 / r2) + 0.15 * exp(-d1 / (4.0 * r2)) + twoHeads * (exp(-d2 / r2) + 0.15 * exp(-d2 / (4.0 * r2))));
            }
            float lit = step(0.5, L.x) * (0.05 + sum);                       // a road with lamps glows a little between them too
            return isJunction > 0.5 ? 0.6 : lit;                                     // a junction: lit all over by the lamps round it
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float yr = IN.years[(int)clamp(_AlatauScenIdx, 0.0, 3.0)];
            float now = _AlatauGrow > 0.5 ? _AlatauYearF + 1.0 : (_AlatauYear < 1 ? 2050.0 : _AlatauYear);
            clip(now + 0.5 - yr);
            if (AlatauOnPad(IN.worldPos) > 0.5) clip(-1.0);                  // no road through a landmark's plot
            float x = IN.road.x, v = IN.road.y, hw = IN.dims.x, oneWay = step(IN.dims.w, -0.5), lanes = max(abs(IN.dims.w), 1.0), len = IN.dims.z;
            float ax = abs(x), xw = fwidth(x), vw = fwidth(v);
            float3 pa = AlatauMat(IN.worldPos.xz, 6.0).pattern, pp = AlatauMat(IN.worldPos.xz, 7.0).pattern;
            float3 c; float3 em = 0;
            float cls = floor(IN.lamp.y / 8.0 + 0.01), crW = cls > 0.5 && cls < 1.5 ? 5.0 : 4.0;
            float cA = IN.lamp.z, cB = IN.lamp.w, vA = v - cA, vB = (len - v) - cB;
            if (IN.dims.y > 0.5)
            {
                // carriageway: asphalt, a lighter wheel track, markings that fade where a line is thinner than a pixel and at junctions
                c = float3(0.355, 0.35, 0.345) * lerp(float3(1, 1, 1), pa, 0.7) * (0.94 + 0.10 * ANoise(IN.worldPos.xz * 0.08)) * (0.97 + 0.06 * ANoise(IN.worldPos.xz * 0.011 + 3.0));
                // a slightly paler wheel track in each lane, a darker oily strip between them
                float lwT = hw / lanes; float lp = frac(ax / lwT);
                c *= 1.0 + 0.05 * (smoothstep(0.15, 0.3, lp) - smoothstep(0.7, 0.85, lp)) * saturate(1.5 - xw * 4.0);
                float lw = hw / lanes;
                // lines stop at the stop line before a crossing, or fade out into a junction
                float fa = cA > 0.5 ? step(cA + crW + 3.6, v) : smoothstep(6.0, 14.0, v), fb = cB > 0.5 ? step(cB + crW + 3.6, len - v) : smoothstep(6.0, 14.0, len - v);
                float fade = saturate(1.5 - xw * 5.0) * fa * fb;
                float dash = step(frac(v / 8.0), 0.38);
                float centre = lanes > 1.5 ? Line(ax - 0.20, 0.08, xw) : Line(x, 0.08, xw) * dash;
                float sep = Line((frac(ax / lw + 0.5) - 0.5) * lw, 0.07, xw) * dash * step(lw * 0.5, ax) * step(ax, hw - lw * 0.5);
                if (oneWay > 0.5)
                {
                    // one direction: lanes from kerb to kerb, dashed lines between them, no centre line
                    float lw1 = 2.0 * hw / lanes, xs = x + hw;
                    centre = 0.0;
                    sep = Line((frac(xs / lw1 + 0.5) - 0.5) * lw1, 0.07, xw) * dash * step(lw1 * 0.5, xs) * step(xs, 2.0 * hw - lw1 * 0.5);
                }
                float edge = Line(ax - (hw - 0.30), 0.07, xw);
                // a real street: repaired patches of fresher (darker) asphalt, a few sealed cracks, darker tyre lanes, a dusty gutter
                // along the kerb, and markings worn where the wheels cross them
                float2 wq = IN.worldPos.xz;
                float patchN = ANoise(wq * 0.045 + 11.0);
                c *= lerp(1.0, 0.86, smoothstep(0.70, 0.74, patchN));
                float crack = 1.0 - smoothstep(0.0, 0.035 + xw * 0.5, abs(ANoise(wq * 0.21 + 3.0) - 0.5));
                c *= 1.0 - 0.10 * crack * saturate(1.5 - xw * 4.0) * step(0.55, ANoise(wq * 0.017 + 5.0));
                float tyre = frac(ax / max(hw / lanes, 1.0));
                c *= 1.0 - 0.05 * (exp(-abs(tyre - 0.27) * 14.0) + exp(-abs(tyre - 0.73) * 14.0)) * saturate(1.5 - xw * 3.0);
                c = lerp(c, c * float3(1.10, 1.07, 1.02), saturate(1.0 - (hw - ax) / 0.6) * 0.6);
                float wear = lerp(1.0, 0.55 + 0.45 * ANoise(float2(v * 0.9, x * 2.0)), saturate(1.5 - xw * 4.0));
                c = lerp(c, float3(0.84, 0.84, 0.82), saturate(centre + sep + edge) * fade * 0.80 * wear);
                // pedestrian crossings: white bars 0.5 m wide along the road with 0.5 m gaps (an even grey where a bar is under a pixel),
                // and a 0.4 m stop line 3 m before the crossing across the lanes coming toward the junction
                float bar = abs(frac(x) - 0.5); float bars = lerp(0.5, saturate((0.25 - bar) / max(xw, 1e-4) + 0.5), saturate(1.5 - xw * 2.0));
                float inside = saturate((hw - 0.35 - ax) / max(xw, 1e-4) + 0.5);
                float zebra = (step(0.5, cA) * Band(vA, 0.0, crW, vw) + step(0.5, cB) * Band(vB, 0.0, crW, vw)) * bars * inside;
                float stopA = step(0.5, cA) * Band(vA, crW + 3.0, crW + 3.4, vw) * (1.0 - oneWay) * step(0.0, x);
                float stopB = step(0.5, cB) * Band(vB, crW + 3.0, crW + 3.4, vw) * lerp(step(x, 0.0), 1.0, oneWay);
                // a T-junction in the middle of the road: a crossing on each side of the side street, stop lines before them
                float jd = v - IN.road.z, ja = abs(jd), jOn = step(0.5, IN.road.w);
                zebra += jOn * Band(ja, IN.road.w, IN.road.w + crW, vw) * bars * inside;
                float jIn = jd > 0.0 ? (1.0 - oneWay) * step(0.0, x) : lerp(step(x, 0.0), 1.0, oneWay);
                stopB += jOn * Band(ja, IN.road.w + crW + 3.0, IN.road.w + crW + 3.4, vw) * jIn;
                float wearZ = lerp(1.0, 0.75 + 0.25 * ANoise(IN.worldPos.xz * 1.7), saturate(1.5 - xw * 4.0));
                c = lerp(c, float3(0.88, 0.88, 0.86), saturate(zebra + (stopA + stopB) * inside) * 0.92 * wearZ);
                if (_AlatauMaket.w > 0.5)
                {
                    // the maket's light strips: solid lines along the kerbs and the centre, glowing blue-white, brighter after dark;
                    // where a strip is thinner than a pixel its light is spread over the carriageway
                    float inR = 1.0 - smoothstep(_AlatauMaket.z * 0.85, _AlatauMaket.z, distance(IN.worldPos.xz, _AlatauMaket.xy));
                    float strip = saturate(Line(ax - (hw - 0.55), 0.14, xw) + (lanes > 1.5 ? Line(ax - 0.35, 0.12, xw) : 0.0));
                    float near = saturate(1.5 - xw * 4.0);
                    float glow = lerp(0.16, strip, near) * inR;
                    em = float3(0.62, 0.82, 1.0) * glow * (0.9 + 2.2 * _AlatauNight);
                    c = lerp(c, float3(0.80, 0.90, 1.0), strip * near * inR * 0.8);
                }
            }
            else
            {
                // pavement beside the carriageway, with a kerb line
                c = float3(0.64, 0.63, 0.60) * lerp(float3(1, 1, 1), pp, 0.7);
                // concrete pavers in a half bond along the street, a few a shade different
                float2 pv = float2(v / 0.6, x / 0.3); pv.x += step(0.5, frac(pv.y * 0.5)) * 0.5;
                float2 pf = abs(frac(pv) - 0.5), pfw = float2(vw / 0.6, xw / 0.3);
                float pj = saturate(1.0 - min((0.5 - pf.x) / max(pfw.x, 1e-4), (0.5 - pf.y) / max(pfw.y, 1e-4)) * 0.8);
                float pdet = saturate(1.5 - max(pfw.x, pfw.y) * 2.0);
                c *= (1.0 - 0.10 * pj * pdet) * (1.0 + 0.05 * (AHash2(floor(pv)) - 0.5) * pdet) * (0.95 + 0.08 * ANoise(IN.worldPos.xz * 0.05));
                // a pale concrete kerb against the carriageway
                c = lerp(c, float3(0.80, 0.79, 0.76), Line(ax - (hw + 0.15), 0.15, xw) * saturate(1.5 - xw * 3.0));
            }
            // at night the lamps' light on the asphalt and the pavements, warm white (FilmLamps puts the posts by the same rule)
            float pool = _AlatauLampOn > 0.01 ? LampPool(x, v, hw, len, IN.lamp) : 0.0;
            em += c * float3(1.0, 0.80, 0.58) * pool * (IN.dims.y > 0.5 ? 1.5 : 0.8) * _AlatauLampOn;      // pale pavements take less: no glowing strips
            o.Albedo = c; o.Emission = em; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack Off
}
