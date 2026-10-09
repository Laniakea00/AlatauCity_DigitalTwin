// Wake of a boat (presentation): additive foam on the water. uv.x = 0 at the stern .. 1 at the end of the wake, uv.y = 0..1 across.
// Two bright foam lines along the arms of the V, a churned strip in the middle near the stern, everything fading with distance.
Shader "AlatauCity/Wake"
{
    Properties { _Color ("Foam", Color) = (0.9, 0.93, 0.95, 1) _Fade ("Intensity", Range(0, 1)) = 1 }
    SubShader
    {
        Tags { "Queue" = "Transparent+10" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        ZWrite Off Blend One One Cull Off Offset -1, -8
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            fixed4 _Color; float _Fade;
            struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float3 wp : TEXCOORD1; };
            v2f vert(appdata_base v) { v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.uv = v.texcoord.xy; o.wp = mul(unity_ObjectToWorld, v.vertex).xyz; return o; }
            float H(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
            float N(float2 p) { float2 i = floor(p), f = frac(p); f = f * f * (3 - 2 * f); return lerp(lerp(H(i), H(i + float2(1, 0)), f.x), lerp(H(i + float2(0, 1)), H(i + float2(1, 1)), f.x), f.y); }
            fixed4 frag(v2f i) : SV_Target
            {
                float u = saturate(i.uv.x), v = saturate(i.uv.y);
                float across = abs(v * 2.0 - 1.0);
                float arms = exp(-pow((1.0 - across) * 7.0, 2.0));                          // the two foam lines at the edges of the V
                float mid = exp(-pow(across * 3.2, 2.0)) * saturate(1.0 - u * 2.2);       // churned water right behind the stern
                float n = N(i.wp.xz * 0.35 + _Time.y * float2(0.6, 0.4)) * 0.6 + 0.4;
                float a = (arms * 0.9 + mid * 0.8) * pow(saturate(1.0 - u), 1.6) * n * _Fade;
                return fixed4(max(_Color.rgb * a, 0.0), 1);
            }
            ENDCG
        }
    }
    FallBack Off
}
