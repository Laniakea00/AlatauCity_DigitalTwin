// Roads of the film look: ribbons built by FilmRoads.cs from the road graph of the twin (roads.json).
// uv  = (metres across from the centre line, metres along the edge)
// uv2 = (half width of the carriageway, 0 = pavement ribbon / 1 = carriageway ribbon, length of the edge, lanes per direction;
//        negative = a one-way carriageway with that many lanes: no centre line, lane lines across the whole width)
// uv3 = year of opening in the four scenarios (picked by _AlatauScenIdx); the ribbon appears with the timeline like the buildings.
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
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauScenIdx; float4 _AlatauMaket;
        struct Input { float2 road; float4 dims; float4 years; float3 worldPos; };
        void vert(inout appdata_full v, out Input o) { UNITY_INITIALIZE_OUTPUT(Input, o); o.road = v.texcoord.xy; o.dims = v.texcoord1; o.years = v.texcoord2; }
        float Line(float d, float halfW, float aa) { return saturate((halfW - abs(d)) / max(aa, 1e-4) + 0.5); }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float yr = IN.years[(int)clamp(_AlatauScenIdx, 0.0, 3.0)];
            float now = _AlatauGrow > 0.5 ? _AlatauYearF + 1.0 : (_AlatauYear < 1 ? 2050.0 : _AlatauYear);
            clip(now + 0.5 - yr);
            if (AlatauOnPad(IN.worldPos) > 0.5) clip(-1.0);                  // no road through a landmark's plot
            float x = IN.road.x, v = IN.road.y, hw = IN.dims.x, oneWay = step(IN.dims.w, -0.5), lanes = max(abs(IN.dims.w), 1.0), len = IN.dims.z;
            float ax = abs(x), xw = fwidth(x), vw = fwidth(v);
            float3 pa = AlatauMat(IN.worldPos.xz, 6.0).pattern, pp = AlatauMat(IN.worldPos.xz, 7.0).pattern;
            float3 c;
            if (IN.dims.y > 0.5)
            {
                // carriageway: asphalt, a lighter wheel track, markings that fade where a line is thinner than a pixel and at junctions
                c = float3(0.355, 0.35, 0.345) * lerp(float3(1, 1, 1), pa, 0.7) * (0.94 + 0.10 * ANoise(IN.worldPos.xz * 0.08)) * (0.97 + 0.06 * ANoise(IN.worldPos.xz * 0.011 + 3.0));
                // a slightly paler wheel track in each lane, a darker oily strip between them
                float lwT = hw / lanes; float lp = frac(ax / lwT);
                c *= 1.0 + 0.05 * (smoothstep(0.15, 0.3, lp) - smoothstep(0.7, 0.85, lp)) * saturate(1.5 - xw * 4.0);
                float lw = hw / lanes;
                float fade = saturate(1.5 - xw * 5.0) * smoothstep(6.0, 14.0, v) * smoothstep(6.0, 14.0, len - v);
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
                if (_AlatauMaket.w > 0.5)
                {
                    // the maket's light strips: solid lines along the kerbs and the centre, glowing blue-white, brighter after dark;
                    // where a strip is thinner than a pixel its light is spread over the carriageway
                    float inR = 1.0 - smoothstep(_AlatauMaket.z * 0.85, _AlatauMaket.z, distance(IN.worldPos.xz, _AlatauMaket.xy));
                    float strip = saturate(Line(ax - (hw - 0.55), 0.14, xw) + (lanes > 1.5 ? Line(ax - 0.35, 0.12, xw) : 0.0));
                    float near = saturate(1.5 - xw * 4.0);
                    float glow = lerp(0.16, strip, near) * inR;
                    o.Emission = float3(0.62, 0.82, 1.0) * glow * (0.9 + 2.2 * _AlatauNight);
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
            o.Albedo = c; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack Off
}
