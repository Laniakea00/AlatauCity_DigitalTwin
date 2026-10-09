// Glowing line over the map (presentation): additive ribbon, soft across its width (uv.y 0..1), light pulses running along it
// (uv.x = metres from the start). uv1.x = year the segment appears (0 = always); _Year hides later ones. _Color, _Speed (m/s), _Period (m between pulses), _Fade (0..1 global intensity).
Shader "AlatauCity/Glow"
{
    Properties { _Color ("Colour", Color) = (0.75, 0.55, 1, 1) _Speed ("Pulse speed", Float) = 900 _Period ("Pulse period", Float) = 6000 _Fade ("Intensity", Range(0, 1)) = 1 _Year ("Show segments built by year (uv1.x)", Float) = 99999 _OffF ("Depth offset factor", Float) = -2 _OffU ("Depth offset units", Float) = -20 }
    SubShader
    {
        Tags { "Queue" = "Transparent+20" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        ZWrite Off Blend One One Cull Off Offset [_OffF], [_OffU]
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            fixed4 _Color; float _Speed, _Period, _Fade, _Year;
            struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float yr : TEXCOORD1; };
            v2f vert(appdata_full v) { v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.uv = v.texcoord.xy; o.yr = v.texcoord1.x; return o; }
            fixed4 frag(v2f i) : SV_Target
            {
                clip(_Year + 0.5 - i.yr);
                float across = saturate(1.0 - abs(i.uv.y * 2.0 - 1.0));      // saturate: pow() of a slightly negative value is NaN, and bloom spreads a NaN into big blocks
                float core = pow(across, 6.0), halo = pow(across, 1.6) * 0.35;
                float ph = frac(i.uv.x / max(_Period, 1.0) - _Time.y * _Speed / max(_Period, 1.0));
                float pulse = exp(-ph * 9.0) * 1.6 + 0.35;
                float3 c = _Color.rgb * (core * 1.4 + halo) * pulse * _Fade;
                return fixed4(max(c, 0.0), 1);
            }
            ENDCG
        }
    }
    FallBack Off
}
