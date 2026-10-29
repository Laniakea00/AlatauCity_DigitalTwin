// Trees of the film look, drawn in instanced batches by FilmTrees.cs. Colours are in the mesh (crown lighter towards the top);
// each tree has a tint and the year its place is developed (from the base map), so trees appear with their quarter.
Shader "AlatauCity/Tree"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        CGPROGRAM
        #pragma surface surf Leaf fullforwardshadows addshadow vertex:vert
        #pragma multi_compile_instancing
        #pragma target 3.5
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauDevK;
        UNITY_INSTANCING_BUFFER_START(Props)
            UNITY_DEFINE_INSTANCED_PROP(float, _TreeYear)
            UNITY_DEFINE_INSTANCED_PROP(float4, _TreeTint)
        UNITY_INSTANCING_BUFFER_END(Props)
        float4 _AlatauSkyHorizon, _AlatauSkyZenith; float _AlatauFilm;
        struct Input { float4 color : COLOR; float3 lp; float3 viewDir; float3 worldPos; };
        void vert(inout appdata_full v, out Input o)
        {
            UNITY_INITIALIZE_OUTPUT(Input, o); o.lp = v.vertex.xyz;
            // a crown is lit by the whole sky: its normals lean up, so the underside is a soft shade and not a dark ball
            float leafV = step(v.color.r, v.color.g);
            v.normal = normalize(lerp(v.normal, float3(0, 1, 0), 0.40 * leafV));
        }
        // value noise in 3D for the leaf clumps (object space, so every tree has its own)
        float LHash(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
        float LNoise(float3 p)
        {
            float3 i = floor(p), f = frac(p); f = f * f * (3.0 - 2.0 * f);
            return lerp(lerp(lerp(LHash(i), LHash(i + float3(1, 0, 0)), f.x), lerp(LHash(i + float3(0, 1, 0)), LHash(i + float3(1, 1, 0)), f.x), f.y),
                        lerp(lerp(LHash(i + float3(0, 0, 1)), LHash(i + float3(1, 0, 1)), f.x), lerp(LHash(i + float3(0, 1, 1)), LHash(i + float3(1, 1, 1)), f.x), f.y), f.z);
        }
        half4 LightingLeaf(SurfaceOutput s, half3 lightDir, half3 viewDir, half atten)
        {
            // foliage lets some light through: half-wrapped diffuse, and a glow at the edge of a crown seen against the sun
            half nl = saturate(dot(s.Normal, lightDir) * 0.65 + 0.35);
            half back = pow(saturate(dot(-viewDir, lightDir)), 4.0) * (1.0 - saturate(dot(s.Normal, viewDir))) * 0.6;
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten + back * half3(1.0, 1.1, 0.6)); c.a = s.Alpha; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float dev = UNITY_ACCESS_INSTANCED_PROP(Props, _TreeYear);
            float k = _AlatauDevK > 0.01 ? _AlatauDevK : 1.0;
            float eff = dev <= 2025.5 ? dev : 2025.0 + (dev - 2025.0) * k;
            float now = _AlatauGrow > 0.5 ? _AlatauYearF + 1.0 : (_AlatauYear < 1 ? 2050.0 : _AlatauYear);
            clip(now - eff + 0.2);
            float4 t = UNITY_ACCESS_INSTANCED_PROP(Props, _TreeTint);
            // leaf clumps: lit tops, dark gaps between them; trunks (brown, below the crown) stay plain
            float leaf = step(IN.color.r, IN.color.g);
            float cl = LNoise(IN.lp * 1.35 + t.r * 17.0) * 0.65 + LNoise(IN.lp * 3.4) * 0.35;
            float3 alb = IN.color.rgb * t.rgb * lerp(1.0, lerp(0.74, 1.12, smoothstep(0.25, 0.8, cl)), leaf);
            // sunlit tops a warmer yellow-green, the underside cooler
            float up = saturate(o.Normal.y * 0.5 + 0.5);
            alb *= lerp(1.0, lerp(float3(0.90, 0.95, 1.05), float3(1.07, 1.04, 0.90), up), leaf);
            // seen from far away a crown is a few pixels: lift its shade towards the lit colour so groves read as soft green,
            // not as black pepper on the pale ground
            float far = saturate((distance(_WorldSpaceCameraPos, IN.worldPos) - 700.0) / 1800.0);
            alb = lerp(alb, alb * 1.22 + float3(0.020, 0.024, 0.010), far * leaf * 0.6);
            o.Albedo = alb; o.Alpha = 1;
            // the sky on the leaves' edge (sheen) and a little light through the crown
            float rim = pow(1.0 - saturate(dot(normalize(IN.viewDir), o.Normal)), 3.0);
            o.Emission = leaf * _AlatauFilm * (lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.4) * alb * 0.25 + _AlatauSkyHorizon.rgb * rim * 0.10 * (0.6 + 0.4 * cl));
        }
        ENDCG
    }
    FallBack Off
}
