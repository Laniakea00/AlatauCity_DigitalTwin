// Roads of the film look: ribbons built by FilmRoads.cs from the road graph of the twin (roads.json).
// uv  = (metres across from the centre line, metres along the edge)
// uv2 = (half width of the carriageway, 0 = pavement ribbon / 1 = carriageway ribbon, length of the edge, lanes per direction;
//        negative = a one-way carriageway with that many lanes: no centre line, lane lines across the whole width)
// uv3 = year of opening in the four scenarios (picked by _AlatauScenIdx); the ribbon appears with the timeline like the buildings.
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
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauScenIdx;
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
                c = float3(0.35, 0.355, 0.36) * lerp(float3(1, 1, 1), pa, 0.7) * (0.94 + 0.10 * ANoise(IN.worldPos.xz * 0.08)) * (0.97 + 0.06 * ANoise(IN.worldPos.xz * 0.011 + 3.0));
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
                c = lerp(c, float3(0.93, 0.93, 0.91), saturate(centre + sep + edge) * fade * 0.9);
            }
            else
            {
                // pavement beside the carriageway, with a kerb line
                c = float3(0.64, 0.63, 0.60) * lerp(float3(1, 1, 1), pp, 0.7);
                // a pale concrete kerb against the carriageway
                c = lerp(c, float3(0.80, 0.79, 0.76), Line(ax - (hw + 0.15), 0.15, xw) * saturate(1.5 - xw * 3.0));
            }
            o.Albedo = c; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack Off
}
