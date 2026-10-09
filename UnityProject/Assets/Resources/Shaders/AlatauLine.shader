// Screen-space-width lines over the city (networks, road works, traffic). Geometry = ribbons along road polylines;
// the vertex shader widens them with camera distance so a trunk main stays visible from the whole-city view.
// Vertex data: POSITION = centre (world), NORMAL = side direction (xz), COLOR = colour, TEXCOORD0 = (metres along, side −1/+1),
// TEXCOORD1 = in-service year per scenario (base, fast, slow, infra), TEXCOORD2 = (edge index, lane).
// Globals: _AlatauYear, _AlatauScenIdx (0..3), _AlatauPx (2·tan(fov/2) / screen height), _AlatauTrafficTex (R8, edge → v/c×100, 0 = none).
Shader "AlatauCity/Line"
{
    Properties
    {
        _PixelWidth ("Half width, px", Float) = 1.4
        _MinWidth ("Min half width, m", Float) = 3
        _BuiltAlpha ("Built alpha", Range(0,1)) = 0.35
        _PlannedAlpha ("Planned alpha", Range(0,1)) = 0
        _WorkAlpha ("Works alpha", Range(0,1)) = 1
        _Mode ("0 = status by year, 1 = traffic", Float) = 0
        _LaneGap ("Lane gap, px", Float) = 7.5
    }
    SubShader
    {
        Tags { "Queue" = "Transparent+10" "RenderType" = "Transparent" "IgnoreProjector" = "True" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        ZTest LEqual
        Cull Off
        Offset -2, -8
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0
            #include "UnityCG.cginc"
            float _PixelWidth, _MinWidth, _BuiltAlpha, _PlannedAlpha, _WorkAlpha, _Mode, _LaneGap;
            float _AlatauYear, _AlatauScenIdx, _AlatauPx; float4 _AlatauJam; float _AlatauJamClear;
            sampler2D _AlatauTrafficTex;
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float4 color : COLOR; float2 uv : TEXCOORD0; float4 years : TEXCOORD1; float2 extra : TEXCOORD2; };
            struct v2f { float4 pos : SV_POSITION; float4 color : COLOR; float2 uv : TEXCOORD0; float year : TEXCOORD1; float vc : TEXCOORD2; float hw : TEXCOORD3; };

            v2f vert(appdata v)
            {
                v2f o;
                float3 c = v.vertex.xyz;
                float d = distance(_WorldSpaceCameraPos, c);
                int si = (int)round(_AlatauScenIdx);
                float yr = si == 0 ? v.years.x : si == 1 ? v.years.y : si == 2 ? v.years.z : v.years.w;
                float Yn = _AlatauYear < 1 ? 2050 : _AlatauYear;
                float widthK = (_Mode < 0.5 && yr <= Yn) ? 0.45 : 1.0;          // built networks: thin context; works: full width
                float hw = max(_MinWidth, _PixelWidth * widthK * d * max(_AlatauPx, 1e-5));
                float gap = _LaneGap * d * max(_AlatauPx, 1e-5);
                float3 p = c + v.normal * (v.uv.y * hw + v.extra.y * max(gap, hw * 2.2));
                p.y += max(4.0, d * 0.004);          // stay above the terrain between samples
                o.pos = UnityWorldToClipPos(p);
                o.color = v.color; o.uv = float2(v.uv.x, v.uv.y); o.hw = hw;
                int s = (int)round(_AlatauScenIdx);
                o.year = s == 0 ? v.years.x : s == 1 ? v.years.y : s == 2 ? v.years.z : v.years.w;
                float e = v.extra.x;
                float2 tuv = float2((fmod(e, 256.0) + 0.5) / 256.0, (floor(e / 256.0) + 0.5) / 128.0);
                o.vc = _Mode > 0.5 ? tex2Dlod(_AlatauTrafficTex, float4(tuv, 0, 0)).r * 255.0 / 100.0 : 0;
                if (_Mode > 0.5 && o.vc > 0.005)
                {
                    // situational centre: a queue around the incident (red), then green once the detour is open
                    float jf = 1.0 - smoothstep(_AlatauJam.z * 0.35, _AlatauJam.z, distance(c.xz, _AlatauJam.xy));
                    o.vc = lerp(o.vc, max(o.vc, 1.35), saturate(_AlatauJam.w) * jf);
                    o.vc = lerp(o.vc, min(o.vc, 0.22), saturate(_AlatauJamClear) * jf);
                }
                return o;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                float Y = _AlatauYear < 1 ? 2050 : _AlatauYear;
                float edge = 1 - smoothstep(0.85, 1.0, abs(i.uv.y));            // soft edges
                float dash = i.uv.x / max(i.hw * 7.0, 1.0);
                if (_Mode > 0.5)
                {
                    if (i.vc <= 0.005) discard;
                    float v = i.vc;
                    fixed3 c = v < 0.6 ? lerp(fixed3(0.20, 0.78, 0.35), fixed3(0.96, 0.82, 0.25), saturate(v / 0.6)) : lerp(fixed3(0.96, 0.65, 0.14), fixed3(1.0, 0.23, 0.18), saturate((v - 0.6) / 0.4));
                    float flow = frac(dash * 0.5 - _Time.y * (1.6 - min(v, 1.4)));
                    float a = (0.55 + 0.45 * step(flow, 0.5)) * edge;
                    c = lerp(c, c * 0.3, smoothstep(0.62, 0.8, abs(i.uv.y)));
                    return fixed4(c, a * 0.95);
                }
                if (i.year > 2098) discard;
                float alpha;
                fixed3 col = i.color.rgb;
                if (i.year <= Y) alpha = _BuiltAlpha;
                else if (i.year <= Y + 1)
                {
                    float m = frac(dash - _Time.y * 0.8);
                    alpha = _WorkAlpha * (m < 0.55 ? 1.0 : 0.25);
                    col = lerp(col, fixed3(1, 1, 1), 0.15);
                }
                else alpha = _PlannedAlpha;
                if (alpha <= 0.001) discard;
                // dark outline keeps thin colour lines readable over the bright master-plan map
                float rim = smoothstep(0.62, 0.8, abs(i.uv.y));
                col = lerp(col, col * 0.3, rim);
                return fixed4(col, alpha * edge * i.color.a);
            }
            ENDCG
        }
    }
}
