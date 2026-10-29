// Moving vehicles of the film look (FilmTraffic.cs), drawn in instanced batches. Vertex colour: rgb = fixed colour or a multiplier of
// the paint, a = what the surface is (1 paint, 0.8 fixed trim / tyres / cargo box, 0.6 glass, 0.4 head lamp, 0.2 tail lamp).
// Per instance: _CarColor (rgb paint, a = braking). Lit like the landmarks: the film sun, the sky in paint and glass, sky ambient.
// Second pass: the glow sprites of the lamps (uv1.x 1 head, 2 tail, 3 light pool on the road), additive, from dusk on (_AlatauNight);
// they keep a few pixels of size at any distance, so a night aerial shows streams of light along the roads.
// Queue after the city's opaque geometry, so nothing opaque is drawn over the glow afterwards.
Shader "AlatauCity/Car"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry+450" }
        CGPROGRAM
        #pragma surface surf Car fullforwardshadows vertex:vert addshadow noforwardadd nolightmap nodynlightmap nodirlightmap nometa novertexlights
        #pragma multi_compile_instancing
        #pragma instancing_options assumeuniformscaling
        #pragma skip_variants LIGHTPROBE_SH
        #pragma target 3.5
        #include "Assets/Shaders/AlatauFilm.cginc"
        UNITY_INSTANCING_BUFFER_START(Props)
            UNITY_DEFINE_INSTANCED_PROP(float4, _CarColor)
        UNITY_INSTANCING_BUFFER_END(Props)
        struct Input { float4 color : COLOR; float3 worldPos; float3 worldNormal; };
        void vert(inout appdata_full v, out Input o)
        {
            UNITY_INITIALIZE_OUTPUT(Input, o);
            // glow sprites belong to the glow pass: collapsed here (also for the shadows)
            v.vertex.xyz *= 1.0 - step(0.5, v.texcoord1.x);
        }
        half4 LightingCar(SurfaceOutput s, half3 lightDir, half3 viewDir, half atten)
        {
            half d = saturate(dot(s.Normal, lightDir));
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (d * atten);
            half3 hv = normalize(lightDir + viewDir);
            // clear coat: a tight sun glint and a soft sheen around it
            float nh = saturate(dot(s.Normal, hv));
            c.rgb += _LightColor0.rgb * (s.Specular * atten) * (pow(nh, 320.0) * 3.0 + pow(nh, 28.0) * 0.20);
            c.a = s.Alpha; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float id = IN.color.a; float4 pc = UNITY_ACCESS_INSTANCED_PROP(Props, _CarColor);
            float3 n = normalize(IN.worldNormal); float3 view = normalize(_WorldSpaceCameraPos - IN.worldPos);
            float film = step(0.5, _AlatauFilm), night = _AlatauNight * film;
            float3 rdir = reflect(-view, n);
            float fres = 0.04 + 0.96 * pow(1.0 - saturate(dot(n, view)), 5.0);
            // every texture read before the branches
            float3 sky = lerp(float3(0.45, 0.50, 0.56), AlatauSky(rdir), film);
            float3 amb = lerp(_AlatauSkyGround.rgb * 0.62, lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.5), n.y * 0.5 + 0.5) * 0.84;
            amb = lerp(ShadeSH9(half4(n, 1.0)), amb, film);
            // seen from far a car is a few pixels: a hint lighter so the stream reads on the asphalt
            float far = saturate((distance(_WorldSpaceCameraPos, IN.worldPos) - 400.0) / 1500.0);
            float3 a = IN.color.rgb; float3 emit = 0; float spec = 0;
            if (id > 0.9)
            {
                // car paint: the clear coat mirrors the sky (the ground below the horizon line, so the flanks darken towards the sill),
                // more at grazing angles; a metallic flake gives back the sky in the paint's own tint
                a = pc.rgb * IN.color.rgb; spec = 0.65;
                float lum = dot(a, float3(0.30, 0.59, 0.11));
                emit = (sky * (0.03 + 0.62 * fres) + sky * a * (0.08 + 0.22 * lum)) * (1.0 - 0.6 * night);
                a *= 0.86;
            }
            else if (id > 0.7) { spec = 0.08; }
            else if (id > 0.5)
            {
                // tinted glass: dark, a mirror of the sky that grows at grazing angles
                a = float3(0.05, 0.06, 0.07); spec = 0.55;
                emit = sky * (0.13 + 0.62 * fres) * (1.0 - 0.5 * night) + float3(0.9, 0.7, 0.45) * 0.05 * night;
            }
            else if (id > 0.3) { emit = float3(1.0, 0.93, 0.80) * (0.15 + 2.6 * night); a *= 0.5; }
            else { emit = float3(1.0, 0.10, 0.06) * (0.12 + (1.3 + 1.8 * pc.a) * night + 0.6 * pc.a); }
            a = lerp(a, a * 1.12 + 0.03, far * (1.0 - night));
            o.Albedo = a; o.Emission = emit + a * (amb + float3(1.0, 0.85, 0.65) * 0.10 * night);   // night: the street lamps on the body
            o.Specular = spec; o.Gloss = 0; o.Alpha = 1;
        }
        ENDCG

        Pass
        {
            Tags { "LightMode" = "Always" }
            ZWrite Off Blend One One Cull Off
            CGPROGRAM
            #pragma vertex gvert
            #pragma fragment gfrag
            #pragma multi_compile_instancing
            #pragma target 3.0
            #include "UnityCG.cginc"
            float _AlatauNight, _AlatauFilm;
            UNITY_INSTANCING_BUFFER_START(Props)
                UNITY_DEFINE_INSTANCED_PROP(float4, _CarColor)
            UNITY_INSTANCING_BUFFER_END(Props)
            struct ga { float4 vertex : POSITION; float4 uv1 : TEXCOORD1; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct gv2f { float4 pos : SV_POSITION; float4 uv : TEXCOORD0; float3 col : TEXCOORD1; };
            gv2f gvert(ga v)
            {
                UNITY_SETUP_INSTANCE_ID(v);
                gv2f o;
                float type = v.uv1.x, lit = _AlatauNight * step(0.5, _AlatauFilm);
                float brake = UNITY_ACCESS_INSTANCED_PROP(Props, _CarColor).a;
                float3 wp = mul(unity_ObjectToWorld, float4(v.vertex.xyz, 1.0)).xyz;
                float3 fwd = normalize(unity_ObjectToWorld._m02_m12_m22), side = normalize(unity_ObjectToWorld._m00_m10_m20);
                float scale = length(unity_ObjectToWorld._m00_m10_m20);
                float3 toCam = _WorldSpaceCameraPos - wp; float dist = length(toCam); toCam /= max(dist, 1e-3);
                // a sprite never smaller than ~3.8 pixels; the bigger it has to be, the dimmer, so a far stream stays a thin line of light
                float px = 2.0 * dist / (unity_CameraProjection._m11 * _ScreenParams.y);
                float r0 = v.uv1.w * scale, r = max(r0, 3.8 * px);
                float dim = max(r0 * r0 / (r * r), 0.55);
                float3 right = UNITY_MATRIX_V[0].xyz, up = UNITY_MATRIX_V[1].xyz;
                float pool = step(2.5, type);
                // the lamps shine forwards (head) or backwards (tail): from the side or from behind a head lamp is much weaker
                float face = dot(toCam, type < 1.5 ? fwd : -fwd);
                float aim = lerp(0.30 + 0.70 * saturate(face * 0.8 + 0.4), 1.0, pool);
                float3 corner = lerp(right * v.uv1.y + up * v.uv1.z, side * v.uv1.y + fwd * v.uv1.z * 1.6, pool) * lerp(r, r0, pool);
                wp += corner + toCam * min(r * 0.6, 1.5) * (1.0 - pool);
                float show = step(0.5, type) * step(0.02, lit);
                o.pos = UnityWorldToClipPos(wp) * show;                              // zero = a collapsed sprite, nothing drawn
                o.uv = float4(v.uv1.y, v.uv1.z, pool, 0);
                float3 c = type < 1.5 ? float3(1.0, 0.85, 0.64) * 2.0 : type < 2.5 ? float3(1.0, 0.10, 0.05) * (1.45 + 1.9 * brake) : float3(1.0, 0.82, 0.58) * 0.16;
                o.col = c * lit * aim * lerp(dim, 1.0, pool) * scale;
                return o;
            }
            fixed4 gfrag(gv2f i) : SV_Target
            {
                float r2 = dot(i.uv.xy, i.uv.xy);
                float core = exp(-r2 * 14.0), halo = exp(-r2 * 3.5) * 0.35;
                float g = lerp(core * 1.6 + halo, exp(-r2 * 2.2), i.uv.z) * saturate(1.0 - r2);
                return fixed4(max(i.col * g, 0.0), 1.0);
            }
            ENDCG
        }
    }
    FallBack Off
}
