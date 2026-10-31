// Traffic lights and the street lamps of the Gate district in the film look (FilmSignals.cs), drawn with GPU instancing.
// Vertex colour: rgb = surface, a = what it is: 0 metal, 0.2 red lens, 0.35 amber lens, 0.5 green lens, 0.7 the light pool of a lamp
// on the road (second pass only), 1 a lamp's lens. Per instance: _SigData = (phase offset s, signal group, -, -).
// _AlatauSigClock: the lights' clock (s); the cycle is FilmSignals.State: 44 s, group 0 green 0-20 / amber 20-23, group 1 green 25-39 /
// amber 39-42, red otherwise. _AlatauSigFade = (focus x, z, radius, fade width): they shrink away at the edge of the drawn area.
// _AlatauLampOn (FilmLook.Lamps): the lamps are lit; the signals glow brighter at night. uv0.xyz = the centre of the lens of a
// vertex: a lit lens grows from afar into a point of light. _AlatauBlackoutZone = (x, z, radius, strength) of a power outage
// (TourEnergy): the lamps and their pools go dark inside it; the traffic lights (on their own backup supply) stay on.
Shader "AlatauCity/Signal"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        CGPROGRAM
        #pragma surface surf Lambert vertex:vert addshadow nolightmap nodynlightmap nodirlightmap nometa noforwardadd
        #pragma multi_compile_instancing
        #pragma target 3.5
        float _AlatauLampOn, _AlatauSigClock; float4 _AlatauSigFade, _AlatauBlackoutZone;
        float LampOnAt(float2 xz)
        {
            float r = max(_AlatauBlackoutZone.z, 1.0);
            return _AlatauLampOn * (1.0 - _AlatauBlackoutZone.w * (1.0 - smoothstep(r * 0.85, r, distance(xz, _AlatauBlackoutZone.xy))));
        }
        UNITY_INSTANCING_BUFFER_START(Props)
            UNITY_DEFINE_INSTANCED_PROP(float4, _SigData)
        UNITY_INSTANCING_BUFFER_END(Props)
        struct Input { float4 color : COLOR; float3 worldPos; };
        void vert(inout appdata_full v)
        {
            float3 org = mul(unity_ObjectToWorld, float4(0, 0, 0, 1)).xyz;
            float fade = saturate((_AlatauSigFade.z - distance(org.xz, _AlatauSigFade.xy)) / max(_AlatauSigFade.w, 1.0));
            float pool = step(0.65, v.color.a) * step(v.color.a, 0.75);
            // a lit lens grows into a point of light a few pixels wide when the camera is far (as the street lamps do)
            float4 sd = UNITY_ACCESS_INSTANCED_PROP(Props, _SigData);
            float t = fmod(_AlatauSigClock + sd.x, 44.0);
            float s0 = t < 20.0 ? 0.0 : (t < 23.0 ? 1.0 : 2.0);
            float s1 = (t >= 25.0 && t < 39.0) ? 0.0 : ((t >= 39.0 && t < 42.0) ? 1.0 : 2.0);
            float st = sd.y > 0.5 ? s1 : s0, a = v.color.a;
            float lit = step(abs(a - 0.2), 0.05) * step(1.5, st) + step(abs(a - 0.35), 0.05) * step(0.5, st) * step(st, 1.5) + step(abs(a - 0.5), 0.05) * step(st, 0.5);
            float camD = distance(_WorldSpaceCameraPos.xyz, org);
            float grow = 1.0 + lit * min(max(camD * 0.006 - 1.0, 0.0), 5.0) + step(0.9, a) * LampOnAt(org.xz) * max(camD * 0.0026 - 1.0, 0.0);
            float3 p = v.texcoord.xyz + (v.vertex.xyz - v.texcoord.xyz) * grow;
            v.vertex.xyz = p * fade * (1.0 - pool);
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float4 sd = UNITY_ACCESS_INSTANCED_PROP(Props, _SigData);
            float t = fmod(_AlatauSigClock + sd.x, 44.0);
            float s0 = t < 20.0 ? 0.0 : (t < 23.0 ? 1.0 : 2.0);
            float s1 = (t >= 25.0 && t < 39.0) ? 0.0 : ((t >= 39.0 && t < 42.0) ? 1.0 : 2.0);
            float st = sd.y > 0.5 ? s1 : s0;
            float a = IN.color.a;
            float isRed = step(abs(a - 0.2), 0.05), isAmber = step(abs(a - 0.35), 0.05), isGreen = step(abs(a - 0.5), 0.05), isLamp = step(0.9, a);
            float lit = isRed * step(1.5, st) + isAmber * step(0.5, st) * step(st, 1.5) + isGreen * step(st, 0.5);
            float lens = isRed + isAmber + isGreen;
            float3 col = isRed * float3(1.0, 0.07, 0.03) + isAmber * float3(1.0, 0.52, 0.04) + isGreen * float3(0.15, 1.0, 0.55);
            float glow = 3.2 + 3.0 * _AlatauLampOn, on = LampOnAt(IN.worldPos.xz);
            o.Albedo = IN.color.rgb * (1.0 - 0.85 * lens) * (1.0 - 0.6 * isLamp * on);
            o.Emission = col * lit * glow + col * lens * (1.0 - lit) * 0.04
                       + float3(1.0, 0.80, 0.58) * isLamp * on * 5.0;     // warm-white LED, as FilmLamps
            o.Alpha = 1;
        }
        ENDCG

        // the light of the lamps on the road at night: a soft warm pool under each head
        Pass
        {
            Tags { "LightMode" = "Always" }
            ZWrite Off Blend One One Cull Off Offset -2, -2
            CGPROGRAM
            #pragma vertex pvert
            #pragma fragment pfrag
            #pragma multi_compile_instancing
            #pragma target 3.0
            #include "UnityCG.cginc"
            float _AlatauLampOn; float4 _AlatauSigFade, _AlatauBlackoutZone;
            struct pa { float4 vertex : POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct pv2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float k : TEXCOORD1; };
            pv2f pvert(pa v)
            {
                UNITY_SETUP_INSTANCE_ID(v);
                pv2f o;
                float3 org = mul(unity_ObjectToWorld, float4(0, 0, 0, 1)).xyz;
                float fade = saturate((_AlatauSigFade.z - distance(org.xz, _AlatauSigFade.xy)) / max(_AlatauSigFade.w, 1.0));
                float bzR = max(_AlatauBlackoutZone.z, 1.0);
                float on = _AlatauLampOn * (1.0 - _AlatauBlackoutZone.w * (1.0 - smoothstep(bzR * 0.85, bzR, distance(org.xz, _AlatauBlackoutZone.xy))));
                float pool = step(0.65, v.color.a) * step(v.color.a, 0.75) * step(0.02, on);
                o.pos = UnityObjectToClipPos(v.vertex) * pool;                   // zero = collapsed, nothing drawn
                o.uv = v.uv; o.k = on * fade;
                return o;
            }
            fixed4 pfrag(pv2f i) : SV_Target
            {
                float r2 = dot(i.uv, i.uv);
                float g = exp(-r2 * 2.6) * saturate(1.0 - r2);
                return fixed4(float3(1.0, 0.80, 0.58) * 0.45 * g * i.k, 1.0);
            }
            ENDCG
        }
    }
    FallBack Off
}
