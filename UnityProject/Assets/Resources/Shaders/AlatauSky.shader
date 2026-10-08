// The sky of the film look: a gradient from the horizon haze to the zenith with the sun and its glow.
// Colours and the sun direction are globals set by FilmLook.cs; the same function (AlatauSky) is what glass and water reflect.
Shader "AlatauCity/Sky"
{
    SubShader
    {
        Tags { "Queue" = "Background" "RenderType" = "Background" "PreviewType" = "Skybox" }
        Cull Off ZWrite Off
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            #include "Assets/Shaders/AlatauFilm.cginc"
            struct v2f { float4 pos : SV_POSITION; float3 dir : TEXCOORD0; };
            v2f vert(appdata_base v) { v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.dir = v.vertex.xyz; return o; }
            fixed4 frag(v2f i) : SV_Target
            {
                float3 d = normalize(i.dir);
                float3 c = AlatauSky(d);
                float s = saturate(dot(d, _AlatauSunDir.xyz));
                c += _AlatauSunColor.rgb * (smoothstep(0.99965, 0.99985, s) * 3.0 + pow(s, 900.0) * 0.8) * (1.0 - _AlatauNight) * step(-0.02, d.y);
                // a few soft, high clouds so the sky is not a flat gradient
                float2 p = d.xz / max(d.y + 0.12, 0.05) * 1.3;
                float cl = ANoise(p * 0.9 + 3.1) * 0.55 + ANoise(p * 2.3) * 0.30 + ANoise(p * 5.1) * 0.15;
                cl = smoothstep(0.56, 0.86, cl) * smoothstep(0.02, 0.22, d.y) * 0.45;
                c = lerp(c, lerp(_AlatauSkyHorizon.rgb, float3(1, 1, 1), 0.55) * (1.0 - 0.75 * _AlatauNight) + _AlatauSunColor.rgb * 0.12 * (1.0 - _AlatauNight), cl);
                // the Trans-Ili Alatau to the south of the city: a stylised ridge with snow, standing in the haze (not survey data)
                float az = atan2(d.x, -d.z);                                   // 0 = due south
                float ridge = (0.010 + 0.034 * ANoise(float2(az * 4.0, 1.7)) + 0.016 * ANoise(float2(az * 13.0, 9.2)) + 0.006 * ANoise(float2(az * 47.0, 4.1))) * smoothstep(1.35, 0.45, abs(az));
                float e = d.y, aa = fwidth(e) + 1e-4;
                float m = saturate((ridge - e) / aa + 0.5) * step(-0.01, e);
                float hgt = saturate(e / max(ridge, 1e-3));                    // 0 at the foot, 1 at the crest
                float snowLine = 0.50 + 0.22 * ANoise(float2(az * 31.0, 2.0));
                float snow = saturate((hgt - snowLine) / 0.06) * step(0.022, ridge);
                float3 rock = lerp(_AlatauSkyHorizon.rgb, float3(0.27, 0.34, 0.48), 0.30 + 0.45 * hgt);
                float3 mnt = lerp(rock, lerp(float3(0.90, 0.93, 0.98), _AlatauSunColor.rgb, 0.25), snow) * (1.0 - 0.70 * _AlatauNight);
                c = lerp(c, mnt, m);
                return fixed4(c, 1);
            }
            ENDCG
        }
    }
}
