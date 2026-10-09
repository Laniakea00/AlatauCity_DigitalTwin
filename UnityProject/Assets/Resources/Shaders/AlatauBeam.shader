// Light beams over buildings in the presentation spotlight: additive, bright at the roof and fading upwards, soft at the sides.
// uv = (across 0..1, up 0..1); uv2.x = distance of the beam from the centre of the wave. The beam rises when the wave of light
// (_AlatauHiWave: xy centre, z radius) reaches it; _Done = 1 keeps the beams of earlier categories on.
Shader "AlatauCity/Beam"
{
    Properties { _Color ("Colour", Color) = (0.6, 0.5, 1, 1) _Done ("Wave passed", Float) = 0 }
    SubShader
    {
        Tags { "Queue" = "Transparent+30" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        ZWrite Off Blend One One Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            fixed4 _Color; float _Done; float4 _AlatauHiWave;
            struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float d : TEXCOORD1; };
            v2f vert(appdata_full v) { v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.uv = v.texcoord.xy; o.d = v.texcoord1.x; return o; }
            fixed4 frag(v2f i) : SV_Target
            {
                float rise = _Done > 0.5 ? 1.0 : saturate((_AlatauHiWave.z - i.d) / 220.0);
                clip(rise - i.uv.y - 0.001);
                float across = saturate(1.0 - abs(i.uv.x * 2.0 - 1.0));          // saturate: pow() of a negative number is NaN (bloom turns it into grey blocks)
                float a = pow(across, 2.2) * pow(saturate(1.0 - i.uv.y), 1.8) * (0.85 + 0.15 * sin(_Time.y * 3.0 + i.d * 0.01));
                return fixed4(max(_Color.rgb * a * 1.3, 0.0), 1);
            }
            ENDCG
        }
    }
    FallBack Off
}
