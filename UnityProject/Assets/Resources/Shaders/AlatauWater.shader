// Water surface of the presentation (flood of Kapshagay, reservoirs): a transparent sheet with moving waves, sky reflection,
// sun glint, depth-based colour (shallow water over land is clear and brownish, deep water teal) and foam along the new shoreline.
// Reads _CameraDepthTexture (FilmPost turns depth on). Globals from AlatauFilm.cginc (sky, sun).
Shader "AlatauCity/Water"
{
    Properties
    {
        _Deep ("Deep colour", Color) = (0.05, 0.19, 0.25, 1)
        _Shallow ("Shallow colour", Color) = (0.34, 0.40, 0.34, 1)
        _Turbid ("Flood water (0 clear .. 1 muddy)", Range(0, 1)) = 0.45
        _Alpha ("Opacity", Range(0, 1)) = 1
    }
    SubShader
    {
        Tags { "Queue" = "Transparent-10" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        ZWrite Off Blend SrcAlpha OneMinusSrcAlpha Cull Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.5
            #include "UnityCG.cginc"
            #include "Assets/Shaders/AlatauFilm.cginc"
            fixed4 _Deep, _Shallow; float _Turbid, _Alpha;
            UNITY_DECLARE_DEPTH_TEXTURE(_CameraDepthTexture);
            struct v2f { float4 pos : SV_POSITION; float3 wpos : TEXCOORD0; float4 scr : TEXCOORD1; float eye : TEXCOORD2; };
            v2f vert(appdata_base v)
            {
                v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.wpos = mul(unity_ObjectToWorld, v.vertex).xyz;
                o.scr = ComputeScreenPos(o.pos); COMPUTE_EYEDEPTH(o.eye); return o;
            }
            float2 Wave(float2 p, float t)
            {
                // gradient of a few travelling waves (metres)
                float2 g = 0;
                float2 d1 = normalize(float2(0.8, 0.6)), d2 = normalize(float2(-0.5, 0.9)), d3 = normalize(float2(0.2, -1.0));
                g += d1 * cos(dot(p, d1) * 0.11 + t * 1.3) * 0.11;
                g += d2 * cos(dot(p, d2) * 0.23 + t * 1.9) * 0.07;
                g += d3 * cos(dot(p, d3) * 0.47 + t * 2.7) * 0.04;
                g += (float2(ANoise(p * 0.9 + t * 0.6), ANoise(p * 0.9 - t * 0.5 + 9.0)) - 0.5) * 0.10;
                return g;
            }
            fixed4 frag(v2f i) : SV_Target
            {
                float t = _Time.y;
                float2 g = Wave(i.wpos.xz, t);
                float3 n = normalize(float3(-g.x, 1.0, -g.y));
                float3 view = normalize(_WorldSpaceCameraPos - i.wpos);
                // depth of water under this pixel (metres along the view ray → roughly vertical for the colour)
                float sceneZ = LinearEyeDepth(SAMPLE_DEPTH_TEXTURE_PROJ(_CameraDepthTexture, UNITY_PROJ_COORD(i.scr)));
                float thick = max(sceneZ - i.eye, 0.0) * saturate(view.y * 1.5 + 0.15);
                float deep = saturate(thick / 6.0);
                float3 shallow = lerp(_Shallow.rgb, float3(0.42, 0.34, 0.22), _Turbid);
                float3 col = lerp(shallow, lerp(_Deep.rgb, float3(0.22, 0.20, 0.14), _Turbid * 0.5), deep);
                float fres = 0.03 + 0.97 * pow(1.0 - saturate(dot(n, view)), 5.0);
                float3 sky = AlatauSky(reflect(-view, n));
                col = lerp(col, sky, fres * 0.85);
                // sun glint
                float3 h = normalize(_AlatauSunDir.xyz + view);
                col += _AlatauSunColor.rgb * pow(saturate(dot(n, h)), 380.0) * 2.2;
                // foam along the moving shoreline and on wave crests
                float shore = 1.0 - saturate(thick / 0.9);
                float crest = smoothstep(0.62, 0.9, ANoise(i.wpos.xz * 0.35 + float2(t * 0.4, -t * 0.3)));
                float foam = saturate(shore * (0.55 + 0.45 * crest) + crest * 0.06);
                col = lerp(col, float3(0.92, 0.93, 0.92), foam * 0.8);
                float a = saturate(lerp(0.55, 0.95, deep) + fres * 0.3 + foam * 0.5) * _Alpha;
                return fixed4(col, a);
            }
            ENDCG
        }
    }
    FallBack Off
}
