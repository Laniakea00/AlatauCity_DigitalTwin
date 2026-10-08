// Trees of the film look, drawn in instanced batches by FilmTrees.cs. Colours are in the mesh (crown lighter towards the top);
// each tree has a tint and the year its place is developed (from the base map), so trees appear with their quarter.
Shader "AlatauCity/Tree"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        CGPROGRAM
        #pragma surface surf Leaf fullforwardshadows addshadow
        #pragma multi_compile_instancing
        #pragma target 3.5
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauDevK;
        UNITY_INSTANCING_BUFFER_START(Props)
            UNITY_DEFINE_INSTANCED_PROP(float, _TreeYear)
            UNITY_DEFINE_INSTANCED_PROP(float4, _TreeTint)
        UNITY_INSTANCING_BUFFER_END(Props)
        struct Input { float4 color : COLOR; };
        half4 LightingLeaf(SurfaceOutput s, half3 lightDir, half atten)
        {
            // foliage lets some light through: half-wrapped diffuse
            half nl = saturate(dot(s.Normal, lightDir) * 0.65 + 0.35);
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten); c.a = s.Alpha; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float dev = UNITY_ACCESS_INSTANCED_PROP(Props, _TreeYear);
            float k = _AlatauDevK > 0.01 ? _AlatauDevK : 1.0;
            float eff = dev <= 2025.5 ? dev : 2025.0 + (dev - 2025.0) * k;
            float now = _AlatauGrow > 0.5 ? _AlatauYearF + 1.0 : (_AlatauYear < 1 ? 2050.0 : _AlatauYear);
            clip(now - eff + 0.2);
            float4 t = UNITY_ACCESS_INSTANCED_PROP(Props, _TreeTint);
            o.Albedo = IN.color.rgb * t.rgb; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack Off
}
