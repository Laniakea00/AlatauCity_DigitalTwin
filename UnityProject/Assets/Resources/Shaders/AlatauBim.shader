// BIM quarter (Gate Q1): element state by date, from a lookup texture (element → plan day, fact day, class, stage).
// uv2.x = element index. Globals/material: _BimDay (current day), _BimGhost (1 = show not-started elements as a dithered ghost), _BimSel (selected element + 1).
Shader "AlatauCity/Bim"
{
    Properties
    {
        _ElemTex ("Element lookup (RGBAFloat 128x128)", 2D) = "black" {}
        _BimDay ("Day", Float) = 0
        _BimGhost ("Ghost", Float) = 1
        _BimSel ("Selected + 1", Float) = 0
    }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry+5" }
        Cull Off
        CGPROGRAM
        #pragma surface surf Soft fullforwardshadows vertex:vert addshadow
        #pragma target 3.0
        sampler2D _ElemTex; float _BimDay, _BimGhost, _BimSel;
        struct Input { float elem; float4 screenPos; float3 worldPos; float vface : VFACE; };
        void vert(inout appdata_full v, out Input o) { UNITY_INITIALIZE_OUTPUT(Input, o); o.elem = v.texcoord1.x; }
        half4 LightingSoft(SurfaceOutput s, half3 lightDir, half atten)
        {
            half nl = saturate(dot(s.Normal, lightDir) * 0.7 + 0.3);
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten); c.a = s.Alpha; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float e = round(IN.elem);
            float4 t = tex2Dlod(_ElemTex, float4((fmod(e, 128.0) + 0.5) / 128.0, (floor(e / 128.0) + 0.5) / 128.0, 0, 0));
            float plan = t.r, fact = t.g, cls = t.b;
            float day = _BimDay;
            fixed3 col; half em = 0.0;
            bool sel = _BimSel > 0.5 && abs(e + 1 - _BimSel) < 0.5;
            if (fact <= day)
            {
                // built: neutral concrete, glass for curtain walls
                col = cls > 0.5 && cls < 1.5 ? fixed3(0.42, 0.62, 0.78) : fixed3(0.80, 0.81, 0.83);
                col *= cls < 0.5 ? 0.92 : 1.0;
            }
            else if (plan + 14.0 <= day) { col = fixed3(1.0, 0.23, 0.18); em = 0.25; }           // behind: two weeks past the plan
            else if (plan - 12.0 <= day) { col = fixed3(0.96, 0.65, 0.14); em = 0.25; }           // in works (incl. up to 2 weeks late)
            else
            {
                // not started: dithered ghost (no transparency sorting), or hidden
                if (_BimGhost < 0.5) clip(-1);
                float2 sp = IN.screenPos.xy / max(IN.screenPos.w, 1e-5) * _ScreenParams.xy;
                float d = frac(dot(floor(sp), float2(0.5, 0.25)) + floor(sp.y) * 0.5);
                clip(0.3 - d);
                col = fixed3(0.55, 0.62, 0.72); em = 0.15;
            }
            if (sel) { col = fixed3(0.85, 0.27, 0.94); em = 0.4; }
            if (IN.vface < 0) col *= 0.45;
            o.Albedo = col; o.Emission = col * em; o.Alpha = 1;
        }
        ENDCG
    }
    FallBack "Diffuse"
}
