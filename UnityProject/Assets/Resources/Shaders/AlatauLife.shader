// The living city of the film look, drawn in instanced batches by FilmLife.cs: people (walk cycle in the vertex shader), flags
// (cloth waving in the wind) and birds (flapping wings). No skinned meshes, no textures except the flag's own.
// _LifeKind (per material): 0 people, 1 flag cloth (texture), 2 bird, 3 plain coloured parts (poles), 4 flag cloth in two colours.
// Per instance: _LifeA, _LifeB, _LifeC (meaning by kind, see below). The project is in gamma colour space: colours are display values.
Shader "AlatauCity/Life"
{
    Properties { _MainTex ("Flag", 2D) = "white" {} _LifeKind ("Kind", Float) = 0 }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        Cull Off
        CGPROGRAM
        #pragma surface surf Life fullforwardshadows addshadow vertex:vert
        #pragma multi_compile_instancing
        #pragma target 3.5
        sampler2D _MainTex; float _LifeKind; float _AlatauNight;
        UNITY_INSTANCING_BUFFER_START(Props)
            UNITY_DEFINE_INSTANCED_PROP(float4, _LifeA)
            UNITY_DEFINE_INSTANCED_PROP(float4, _LifeB)
            UNITY_DEFINE_INSTANCED_PROP(float4, _LifeC)
        UNITY_INSTANCING_BUFFER_END(Props)
        struct Input { float4 color : COLOR; float2 lifeUV; float4 top; float4 bot; float fade; float4 sPos; };

        // people: colour.r = part (0 skin, 1 hair, 2 top, 3 bottom, 4 shoes, 5 bag); uv.x = limb (0 none, 1/2 left/right leg, 3/4 left/right arm),
        // uv.y = height of its pivot (hip, shoulder). _LifeA = (walk 0..1, phase, steps per second × 2π, fade), _LifeB = top colour + skin tone,
        // _LifeC = bottom colour + hair tone. The figure faces +z.
        void Person(inout appdata_full v, float4 A)
        {
            float limb = v.texcoord.x, piv = v.texcoord.y;
            float ph = _Time.y * A.z + A.y;
            float s = sin(ph);
            // legs swing about the hip, the arms against them about the shoulder; standing people sway a little
            float ang = 0.0;
            if (limb > 0.5 && limb < 2.5) ang = s * 0.42 * A.x * (limb < 1.5 ? 1.0 : -1.0);
            else if (limb > 2.5) ang = -s * 0.30 * A.x * (limb < 3.5 ? 1.0 : -1.0) + 0.04 * (1.0 - A.x) * sin(_Time.y * 0.7 + A.y);
            float ca = cos(ang), sa = sin(ang);
            float y = v.vertex.y - piv, z = v.vertex.z;
            if (limb > 0.5) { v.vertex.y = piv + y * ca - z * sa; v.vertex.z = y * sa + z * ca; }
            // the body bobs twice a stride
            v.vertex.y += A.x * 0.025 * abs(cos(ph));
        }
        // flag: uv.x 0 at the pole .. 1 at the fly end, uv.y 0 bottom .. 1 top; _LifeA = (size, phase, wind 0..1, -)
        void Flag(inout appdata_full v, float4 A)
        {
            float u = v.texcoord.x, t = _Time.y * (2.6 + 1.6 * A.z) + A.y;
            float w = sin(u * 7.0 - t) * 0.6 + sin(u * 13.0 - t * 1.7 + v.texcoord.y * 2.0) * 0.25;
            v.vertex.z += w * u * 0.16 * (0.5 + A.z);
            v.vertex.x -= u * u * 0.05 * (1.0 - A.z);
            v.vertex.y -= u * u * 0.10 * (1.0 - A.z);
            v.normal = normalize(float3(-cos(u * 7.0 - t) * 0.6 * u, 0.0, 1.0));
        }
        // bird: uv.x = side (-1 left wing, +1 right, 0 body), uv.y = distance from the body (0..1); _LifeA = (flap 0..1, phase, rate, -)
        void Bird(inout appdata_full v, float4 A)
        {
            float side = v.texcoord.x, d = v.texcoord.y;
            float f = sin(_Time.y * A.z + A.y);
            float lift = (f * 0.55 * A.x + 0.10) * d;          // wings up and down; a gliding bird holds them a little raised
            v.vertex.y += lift * abs(side) * 0.9;
            v.vertex.x *= 1.0 - 0.12 * abs(f) * A.x * d;
        }
        void vert(inout appdata_full v, out Input o)
        {
            UNITY_INITIALIZE_OUTPUT(Input, o);
            float4 A = UNITY_ACCESS_INSTANCED_PROP(Props, _LifeA);
            o.top = UNITY_ACCESS_INSTANCED_PROP(Props, _LifeB);
            o.bot = UNITY_ACCESS_INSTANCED_PROP(Props, _LifeC);
            o.fade = 1.0;
            if (_LifeKind < 0.5) { Person(v, A); o.fade = A.w; }
            else if (_LifeKind < 1.5 || _LifeKind > 3.5) Flag(v, A);
            else if (_LifeKind < 2.5) Bird(v, A);
            o.lifeUV = v.texcoord.xy;
            o.sPos = ComputeScreenPos(UnityObjectToClipPos(v.vertex));       // not the built-in screenPos: that breaks the generated shadow pass
        }
        half4 LightingLife(SurfaceOutput s, half3 lightDir, half atten)
        {
            // soft wrap: small figures read as figures, not as black specks, on the shady side
            half nl = saturate(dot(s.Normal, lightDir) * 0.6 + 0.4);
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * nl * atten; c.a = 1; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            // fade in and out without blending: an ordered dither (people at the end of their path, at the edge of the drawn range)
            float2 sp = IN.sPos.xy / max(IN.sPos.w, 1e-4) * _ScreenParams.xy;
            float dither = frac(dot(floor(sp), float2(0.0625, 0.25)) + frac(floor(sp.y) * 0.5) * 0.5);
            clip(IN.fade - dither * 0.98 - 0.01);
            float3 c = IN.color.rgb;
            if (_LifeKind < 0.5)
            {
                float part = IN.color.r * 8.0;
                float3 skin = lerp(float3(0.93, 0.76, 0.62), float3(0.55, 0.38, 0.27), IN.top.w);
                float3 hair = lerp(float3(0.08, 0.06, 0.05), float3(0.42, 0.30, 0.20), IN.bot.w);
                c = part < 0.5 ? skin : part < 1.5 ? hair : part < 2.5 ? IN.top.rgb : part < 3.5 ? IN.bot.rgb : part < 4.5 ? float3(0.10, 0.10, 0.11) : part < 5.5 ? IN.bot.rgb * 0.6 : float3(0.16, 0.16, 0.16);
            }
            else if (_LifeKind < 1.5) c = tex2D(_MainTex, IN.lifeUV).rgb;
            else if (_LifeKind > 3.5) c = IN.lifeUV.y > 0.5 ? IN.top.rgb : IN.bot.rgb;
            else if (_LifeKind > 2.5) c = IN.top.rgb;
            else c = float3(0.30, 0.31, 0.33);
            // the patch under the feet takes no light (part 6): a contact shadow, darker at its middle
            if (_LifeKind < 0.5 && IN.color.r * 8.0 > 5.5) { clip(0.55 * (1.0 - IN.lifeUV.y) - dither); c = float3(0.0, 0.0, 0.0); }
            o.Albedo = c; o.Alpha = 1;
            // flags are lit by a floodlight at night
            o.Emission = (_LifeKind > 0.5 && _LifeKind < 1.5) || _LifeKind > 3.5 ? c * 0.30 * _AlatauNight : float3(0, 0, 0);
        }
        ENDCG
    }
    FallBack Off
}
