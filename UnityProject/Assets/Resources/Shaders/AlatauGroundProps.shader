// Benches and playground equipment of the redrawn map (Layers/GroundProps.cs), drawn with GPU instancing: plain models whose
// colour is in the vertices (wood, painted steel, sand). Lit by the sun like the other film props, casting and receiving shadows.
Shader "AlatauCity/GroundProps"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        CGPROGRAM
        #pragma surface surf Lambert addshadow nolightmap nodynlightmap nodirlightmap nometa noforwardadd
        #pragma multi_compile_instancing
        #pragma target 3.5
        struct Input { float4 color : COLOR; };
        void surf(Input IN, inout SurfaceOutput o)
        {
            o.Albedo = IN.color.rgb;
            o.Emission = IN.color.rgb * 0.08;
            o.Alpha = 1.0;
        }
        ENDCG
    }
    FallBack "Diffuse"
}
