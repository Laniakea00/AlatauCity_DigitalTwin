// The sky of the film look: a gradient from the horizon haze to the zenith with the sun and its glow; at sunset a wide glow along the
// horizon toward the sun, then the blue hour; at night stars (procedural, fading into the city haze), the moon (where FilmLook puts
// the night light) and the warm glow of the lit city low on the horizon (_AlatauDusk, _AlatauDark set by FilmLook).
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
            float _AlatauDusk, _AlatauDark;
            struct v2f { float4 pos : SV_POSITION; float3 dir : TEXCOORD0; };
            float SHash3(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
            v2f vert(appdata_base v) { v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.dir = v.vertex.xyz; return o; }
            fixed4 frag(v2f i) : SV_Target
            {
                float3 d = normalize(i.dir);
                float3 c = AlatauSkyLod(d, 0.0);
                float s = saturate(dot(d, _AlatauSunDir.xyz));
                c += _AlatauSunColor.rgb * (smoothstep(0.99965, 0.99985, s) * 3.0 + pow(s, 900.0) * 0.8) * (1.0 - _AlatauNight) * step(-0.02, d.y);
                // sunset: a wide band of orange and pink along the horizon, strongest toward the sun, purple higher up
                float2 hs = normalize(_AlatauSunDir.xz + 1e-4), hd = normalize(d.xz + 1e-4);
                float toward = saturate(dot(hs, hd) * 0.5 + 0.5), low = exp(-max(d.y, 0.0) * 9.0);
                float glowK = _AlatauDusk * (1.0 - _AlatauDark);
                c += glowK * low * (float3(1.0, 0.42, 0.16) * 0.55 * pow(toward, 3.0) + float3(0.55, 0.30, 0.42) * 0.16 * (1.0 - toward)) * step(-0.02, d.y);
                c += glowK * exp(-max(d.y, 0.0) * 3.0) * float3(0.30, 0.16, 0.30) * 0.10 * toward;
                // night: stars (a few thousand, most faint), sparser and dimmer toward the hazy horizon over the city
                float3 sp = d * 420.0; float3 cell = floor(sp); float h = SHash3(cell);
                float3 jit = float3(SHash3(cell + 17.1), SHash3(cell + 31.7), SHash3(cell + 47.3)) * 0.6 + 0.2;
                float pix = max(length(fwidth(sp)), 1e-3);
                float star = step(0.9955, h) * exp(-dot(sp - cell - jit, sp - cell - jit) / (pix * pix * 0.35));
                float mag = pow(SHash3(cell + 5.3), 6.0) * 1.6 + 0.25;
                c += star * mag * float3(0.92, 0.95, 1.0) * _AlatauDark * smoothstep(0.06, 0.40, d.y) * 0.9;
                // the moon (the night light comes from it): a pale disc with a soft halo
                float sm = dot(d, normalize(_AlatauSunDir.xyz));
                c += _AlatauDark * (smoothstep(0.99990, 0.99994, sm) * float3(0.95, 0.94, 0.88) * 1.4 + pow(saturate(sm), 1800.0) * float3(0.30, 0.34, 0.45) * 0.35 + pow(saturate(sm), 60.0) * float3(0.05, 0.06, 0.09));
                // the glow of the lit city on the haze, low along the whole horizon
                c += _AlatauDark * exp(-max(d.y, 0.0) * 16.0) * float3(0.55, 0.33, 0.17) * 0.22 * step(-0.05, d.y);
                // a few soft, high clouds so the sky is not a flat gradient
                float2 p = d.xz / max(d.y + 0.12, 0.05) * 1.3;
                float cl = ANoise(p * 0.9 + 3.1) * 0.55 + ANoise(p * 2.3) * 0.30 + ANoise(p * 5.1) * 0.15;
                cl = smoothstep(0.56, 0.86, cl) * smoothstep(0.02, 0.22, d.y) * 0.45 * (1.0 - _AlatauSkyTexOn);      // the photo has its own clouds
                c = lerp(c, lerp(_AlatauSkyHorizon.rgb, float3(1, 1, 1), 0.55) * (1.0 - 0.75 * _AlatauNight) + _AlatauSunColor.rgb * 0.12 * (1.0 - _AlatauNight), cl);
                // the Trans-Ili Alatau to the south of the city: a stylised ridge with snow, standing in the haze (not survey data)
                float az = atan2(d.x, -d.z);                                   // 0 = due south
                float ridge = (0.010 + 0.034 * ANoise(float2(az * 4.0, 1.7)) + 0.016 * ANoise(float2(az * 13.0, 9.2)) + 0.006 * ANoise(float2(az * 47.0, 4.1))) * smoothstep(1.35, 0.45, abs(az));
                float e = d.y, aa = fwidth(e) + 1e-4;
                float m = saturate((ridge - e) / aa + 0.5) * step(-0.01, e);
                float hgt = saturate(e / max(ridge, 1e-3));                    // 0 at the foot, 1 at the crest
                float snowLine = 0.50 + 0.22 * ANoise(float2(az * 31.0, 2.0));
                float snow = saturate((hgt - snowLine) / 0.06) * step(0.022, ridge);
                float3 rock = lerp(_AlatauSkyHorizon.rgb, float3(0.27, 0.34, 0.48), 0.22 + 0.33 * hgt);       // far away: mostly haze
                float3 mnt = lerp(rock, lerp(float3(0.90, 0.93, 0.98), _AlatauSunColor.rgb, 0.25), snow) * (1.0 - 0.70 * _AlatauNight);
                c = lerp(c, mnt, m * smoothstep(0.0, 0.006, ridge - 0.004));      // the ends of the range sink into the haze instead of stopping
                return fixed4(c, 1);
            }
            ENDCG
        }
    }
}
