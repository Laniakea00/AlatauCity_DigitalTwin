// Translucent district outlines (vertical curtains), vertex colour * _Color, both faces.
Shader "AlatauCity/Curtain"
{
    Properties { _Color ("Tint / alpha", Color) = (1,1,1,0.35) }
    SubShader
    {
        Tags { "Queue" = "Transparent" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        Blend SrcAlpha OneMinusSrcAlpha ZWrite Off Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "UnityCG.cginc"
            fixed4 _Color;
            struct v2f { float4 pos : SV_POSITION; fixed4 col : COLOR; float h : TEXCOORD1; UNITY_FOG_COORDS(0) };
            v2f vert(appdata_full v) { v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.col = v.color * _Color; o.h = v.vertex.y; UNITY_TRANSFER_FOG(o, o.pos); return o; }
            fixed4 frag(v2f i) : SV_Target { fixed4 c = i.col; UNITY_APPLY_FOG(unity_FogColor, c); return c; }
            ENDCG
        }
    }
}
