// Roads of the film look: ribbons built by FilmRoads.cs from the road graph of the twin (roads.json).
// uv  = (metres across from the centre line, metres along the edge)
// uv2 = (half width of the carriageway, 0 = pavement ribbon / 1 = carriageway ribbon, length of the edge, lanes per direction)
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
            float x = IN.road.x, v = IN.road.y, hw = IN.dims.x, lanes = max(IN.dims.w, 1.0), len = IN.dims.z;
            float ax = abs(x), xw = fwidth(x), vw = fwidth(v);
            float3 pa = AlatauMat(IN.worldPos.xz, 6.0).pattern, pp = AlatauMat(IN.worldPos.xz, 7.0).pattern;
            float3 c;
            if (IN.dims.y > 0.5)
            {
                // carriageway: asphalt, a lighter wheel track, markings that fade where a line is thinner than a pixel and at junctions
                c = float3(0.43, 0.44, 0.46) * lerp(float3(1, 1, 1), pa, 0.8) * (0.96 + 0.06 * ANoise(IN.worldPos.xz * 0.08));
                float lw = hw / lanes;
                float fade = saturate(1.5 - xw * 5.0) * smoothstep(6.0, 14.0, v) * smoothstep(6.0, 14.0, len - v);
                float dash = step(frac(v / 8.0), 0.38);
                float centre = lanes > 1.5 ? Line(ax - 0.20, 0.08, xw) : Line(x, 0.08, xw) * dash;
                float sep = Line((frac(ax / lw + 0.5) - 0.5) * lw, 0.07, xw) * dash * step(lw * 0.5, ax) * step(ax, hw - lw * 0.5);
                float edge = Line(ax - (hw - 0.30), 0.07, xw);
                c = lerp(c, float3(0.93, 0.93, 0.91), saturate(centre + sep + edge) * fade * 0.9);
            }
            else
            {
                // pavement beside the carriageway, with a kerb line
                c = float3(0.70, 0.68, 0.64) * lerp(float3(1, 1, 1), pp, 0.7);
                c *= 1.0 - 0.25 * Line(ax - (hw + 0.12), 0.12, xw) * saturate(1.5 - xw * 3.0);
            }
            o.Albedo = c; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack Off
}
