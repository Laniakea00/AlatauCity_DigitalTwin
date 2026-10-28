// One shader for the whole city. uv2.x = completion year (0 = always), uv2.y = building id + 1 (0 = none).
// uv = (metres along the wall from its start, wall length; 0 = not a wall): written by AlatauCityBuilder, used by the film look.
// Globals: _AlatauYear (timeline, 0 = all), _AlatauSel (selected id + 1, 0 = none),
//          _AlatauSelColor (selection colour), _AlatauScenario (1 = read the year from _AlatauYearTex: 256x256 RFloat, bid -> visible-from year),
//          _AlatauMode (0 = normal, 1 = construction: _AlatauStateTex RGBA32 r = state, g = progress; _AlatauGeoTex RGBAFloat r = base Y, g = height),
//          _AlatauMode 2 = analysis tint: _AlatauTintTex RGBA32 (bid → colour, a = strength),
//          _AlatauCull (render-state cull mode, 2 = Back; set to 0 = Off while buildings are shown "under construction"),
//          _AlatauFilm (1 = film look in the normal mode: facades from AlatauFilm.cginc; _AlatauStyleTex RGBA32 bid → r = style, g = seed, b = floors).
Shader "AlatauCity/Lit"
{
    Properties
    {
        _MainTex ("Map", 2D) = "white" {}
        _Color ("Tint", Color) = (1,1,1,1)
        _Ambient ("Self light", Range(0,1)) = 0
        _OffsetF ("Depth offset factor", Float) = 0
        _OffsetU ("Depth offset units", Float) = 0
    }
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        Offset [_OffsetF], [_OffsetU]
        Cull [_AlatauCull]
        CGPROGRAM
        #pragma surface surf Soft fullforwardshadows vertex:vert addshadow noambient novertexlights noforwardadd nolightmap nodynlightmap nodirlightmap nometa
        #pragma target 3.5
        // the browser compiles every variant when the shader loads: one sun, the ambient light comes from ShadeSH9 below,
        // so the light probe copies only repeat the same code
        #pragma skip_variants LIGHTPROBE_SH
        #include "Assets/Shaders/AlatauFilm.cginc"
        sampler2D _MainTex; fixed4 _Color, _AlatauSelColor; half _Ambient; float _AlatauYear, _AlatauSel, _AlatauScenario, _AlatauMode, _AlatauYearF, _AlatauGrow, _AlatauBldSat, _AlatauBlackout, _InfraKind, _AlatauHiOn, _AlatauHiCur; float4 _AlatauHiWave;
        sampler2D _AlatauYearTex, _AlatauStateTex, _AlatauGeoTex, _AlatauTintTex, _AlatauStyleTex, _AlatauHideTex; float _AlatauHideOn;
        struct Input { float2 uv_MainTex; float4 color : COLOR; float2 info; float2 wall; float3 worldPos; float3 worldNormal; float vface : VFACE; };
        void vert(inout appdata_full v, out Input o) { UNITY_INITIALIZE_OUTPUT(Input, o); o.info = v.texcoord1.xy; o.wall = v.texcoord.xy; }
        half4 LightingSoft(SurfaceOutput s, half3 lightDir, half3 viewDir, half atten)
        {
            half nl = saturate(dot(s.Normal, lightDir));
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten); c.a = s.Alpha;
            // the sun's glint on glass (Specular is 0 outside the film look)
            half3 hv = normalize(lightDir + viewDir);
            c.rgb += _LightColor0.rgb * (pow(saturate(dot(s.Normal, hv)), 180.0) * s.Specular * atten * 1.5);
            return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float year = IN.info.x;
            float floors = IN.worldPos.y / 3.2, floorsW = fwidth(floors);     // derivatives outside of branches
            float bid = round(IN.info.y) - 1.0;
            float4 tuv = float4((fmod(max(bid, 0), 256.0) + 0.5) / 256.0, (floor(max(bid, 0) / 256.0) + 0.5) / 256.0, 0, 0);
            // film look: the facade of this building at this point (it takes its own derivatives, so it is evaluated before the branches)
            float3 wn = normalize(IN.worldNormal) * (IN.vface < 0 ? -1.0 : 1.0);
            float3 view = normalize(_WorldSpaceCameraPos - IN.worldPos);
            float4 geoF = tex2Dlod(_AlatauGeoTex, tuv), sty = tex2Dlod(_AlatauStyleTex, tuv);
            float part = IN.wall.y < -0.5 ? round(-IN.wall.y) : 0.0;      // 1 parapet / crown, 2 plant, 3 tile roof (AlatauRoofs)
            AFacade F = AlatauFacade(IN.wall, IN.worldPos.y - geoF.r, max(geoF.g, 3.0), max(sty.b * 255.0, 1.0), round(sty.r * 255.0), sty.g, IN.color.rgb, wn, view, IN.worldPos, part);
            // buildings replaced by a landmark (Iconic Complex, plants …) are not drawn
            if (_AlatauHideOn > 0.5 && IN.info.y > 0.5)
            {
                // 1 = never built (generated / planned buildings on a landmark plot); n > 1 = existing building, gone from year 2000 + n
                float hcode = round(tex2Dlod(_AlatauHideTex, tuv).r * 255.0);
                float yNow = _AlatauYear < 1 ? 2050 : max(_AlatauYear, _AlatauGrow > 0.5 ? _AlatauYearF : 0);
                if (hcode > 0.5 && (hcode < 1.5 || yNow >= 2000 + hcode)) clip(-1.0);
            }
            // the film facades stay in every tab: construction and analysis colour them by data but keep floors, windows and glass
            bool filmAny = _AlatauFilm > 0.5 && IN.info.y > 0.5;
            bool film = filmAny && _AlatauMode < 0.5;
            if (part > 0.5 && !filmAny) clip(-1.0);                       // roof parts belong to the film look only

            if (_AlatauScenario > 0.5 && IN.info.y > 0.5) year = tex2Dlod(_AlatauYearTex, tuv).r;
            float limit = _AlatauYear < 1 ? 99999 : _AlatauYear;
            // timeline playback: the buildings of the coming year rise during the year (needs _AlatauGeoTex: r = base Y, g = height)
            bool grow = _AlatauGrow > 0.5 && _AlatauMode < 0.5 && IN.info.y > 0.5 && year > 2025.5;
            float prog = saturate(_AlatauYearF + 1.0 - year);
            if (grow)
            {
                clip(_AlatauYearF + 1.0 - year);
                float4 geo = tex2Dlod(_AlatauGeoTex, tuv);
                clip(geo.r + max(geo.g, 4.0) * prog + 0.3 + step(0.999, prog) * 60.0 - IN.worldPos.y);
            }
            else clip(limit + 0.5 - year);
            fixed3 a = tex2D(_MainTex, IN.uv_MainTex).rgb * IN.color.rgb * _Color.rgb;
            if (filmAny) a = F.albedo;
            else if (_AlatauMode < 0.5 && IN.info.y > 0.5 && _AlatauBldSat > 0.01)
            {
                // calm building colours (the plan colours stay readable, but the city reads as one maket)
                float lb = dot(a, fixed3(0.299, 0.587, 0.114)); a = lerp(fixed3(lb, lb, lb), a, _AlatauBldSat);
            }
            if (_AlatauFilm > 0.5 && IN.info.y < 0.5)
            {
                // film look, the plan's line layers (vertex colour = palette): the LRT corridor is drawn by the viaduct itself,
                // street axes / highways / main roads / the ring road become asphalt (the film road ribbons with markings lie on top),
                // railways a dark ballast bed, rivers and the rest stay in quiet colours
                float3 vc = IN.color.rgb;
                if (distance(vc, float3(0.9357, 0.3492, 0.7977)) < 0.06) clip(-1.0);
                if (AlatauOnPad(IN.worldPos) > 0.5) clip(-1.0);
                // per layer (FilmLook sets _InfraKind): 3 = drawn by something better in the film (river lines → the ground's water,
                // the ring-road axis → the road ribbons), 2 = bridge decks: asphalt on top, concrete at the sides, 5 = runway concrete
                if (_InfraKind > 2.5 && _InfraKind < 3.5) clip(-1.0);
                bool street = min(vc.r, min(vc.g, vc.b)) > 0.965;
                bool road = distance(vc, float3(0.4366, 0.4236, 0.41)) < 0.03 || distance(vc, float3(0.5469, 0.5371, 0.5169)) < 0.03;
                bool rail = distance(vc, float3(0.3133, 0.3133, 0.3492)) < 0.03 || distance(vc, float3(0.4845, 0.4845, 0.5271)) < 0.03;
                float gn = ANoise(IN.worldPos.xz * 0.35) * 0.6 + ANoise(IN.worldPos.xz * 0.05) * 0.4;
                float3 wn0 = normalize(IN.worldNormal);
                if (_InfraKind > 1.5 && _InfraKind < 2.5)
                    a = wn0.y > 0.7 ? float3(0.30, 0.30, 0.31) * lerp(float3(1, 1, 1), AlatauMat(IN.worldPos.xz, 6.0).pattern, 0.8) : float3(0.62, 0.61, 0.58) * lerp(float3(1, 1, 1), AlatauMat(float2(IN.worldPos.x + IN.worldPos.z, IN.worldPos.y), 1.0).pattern, 0.5);
                else if (_InfraKind > 4.5 && _InfraKind < 5.5) a = float3(0.55, 0.55, 0.53) * lerp(float3(1, 1, 1), AlatauMat(IN.worldPos.xz, 7.0).pattern, 0.6);
                else if (street || road) a = float3(0.33, 0.33, 0.335) * (0.90 + 0.16 * gn);
                else if (rail) a = float3(0.36, 0.34, 0.31) * (0.85 + 0.25 * gn);
                else { float lf = dot(a, fixed3(0.299, 0.587, 0.114)); a = lerp(fixed3(lf, lf, lf), a, 0.22) * 0.97; }
            }
            half3 emit = a * _Ambient;
            if (film) emit += F.emit;
            if (film && _AlatauHiOn > 0.5 && IN.info.y > 0.5)
            {
                // presentation spotlight in the film look: buildings of a category (tint lookup: rgb = colour, a = index / 8) take its colour
                // and a soft glow; the newest category arrives with a wave of light running out from the centre of the district
                float4 hi = tex2Dlod(_AlatauTintTex, tuv);
                float idx = round(hi.a * 8.0);
                if (idx > 0.5)
                {
                    float dW = distance(IN.worldPos.xz, _AlatauHiWave.xy);
                    bool cur = abs(idx - _AlatauHiCur) < 0.5;
                    float on = idx < _AlatauHiCur - 0.5 ? 1.0 : cur ? saturate((_AlatauHiWave.z - dW) / 160.0) : 0.0;
                    float front = cur ? exp(-abs(_AlatauHiWave.z - dW) / 60.0) : 0.0;
                    float pulse = 0.85 + 0.15 * sin(_Time.y * 2.4 + idx);
                    float lum0 = dot(a, fixed3(0.299, 0.587, 0.114));
                    a = lerp(a, hi.rgb * (0.65 + 0.6 * lum0), 0.85 * on);
                    emit = lerp(emit, emit * 0.5, on) + hi.rgb * (0.42 * pulse * on + 1.3 * front);
                }
                else { a *= 0.86; emit *= 0.8; }                                // the rest of the city steps back a little
            }
            if (film && _AlatauBlackout > 0.001 && IN.info.y > 0.5)
            {
                // presentation: power outage — the buildings marked in the tint lookup (alpha) lose their lights
                float dk = tex2Dlod(_AlatauTintTex, tuv).a * _AlatauBlackout;
                emit *= 1.0 - 0.94 * dk; a *= 1.0 - 0.45 * dk;
            }
            if (grow)
            {
                // fresh buildings glow warm for about a year, then settle into the city colour
                float fresh = saturate(1.6 - (_AlatauYearF + 1.0 - year));
                a = lerp(a, fixed3(1.0, 0.74, 0.42), 0.6 * saturate(fresh));
                emit += a * 0.25 * saturate(fresh);
            }
            if (_AlatauMode > 1.5 && IN.info.y > 0.5)
            {
                // analysis mode: per-building tint (rgb) with strength (a); untinted buildings fade to grey context
                float4 tn = tex2Dlod(_AlatauTintTex, tuv);
                float g0 = dot(a, fixed3(0.299, 0.587, 0.114));
                fixed3 ctx = lerp(fixed3(g0, g0, g0), a, filmAny ? 0.35 : 0.25) * 0.95;
                fixed3 tc = filmAny ? tn.rgb * (0.55 + 0.75 * g0) : tn.rgb;          // the data colour keeps the facade's light and dark
                a = lerp(ctx, tc, tn.a); emit = a * (0.12 + 0.2 * tn.a) + (filmAny ? F.emit * (0.35 - 0.2 * tn.a) : 0);
            }
            else if (_AlatauMode > 1.5)
            {
                // analysis mode, ground / parcels: muted so only the analysed buildings carry colour
                float g1 = dot(a, fixed3(0.299, 0.587, 0.114));
                a = lerp(fixed3(g1, g1, g1), a, 0.3) * 0.9; emit = a * _Ambient;
            }
            else if (_AlatauMode > 0.5 && IN.info.y > 0.5)
            {
                float4 st = tex2Dlod(_AlatauStateTex, tuv);
                int state = (int)round(st.r * 255.0);
                if (state == 5) clip(-1);
                if (state >= 1 && state <= 3)
                {
                    // building rises with its progress; scaffold bands every ~3.2 m
                    float4 geo = tex2Dlod(_AlatauGeoTex, tuv);
                    float top = geo.r + max(geo.g, 4.0) * st.g + 0.6;
                    clip(top - IN.worldPos.y);
                    fixed3 c = state == 1 ? fixed3(0.96, 0.65, 0.14) : state == 2 ? fixed3(1.0, 0.23, 0.18) : fixed3(0.55, 0.55, 0.58);
                    float lines = frac(floors) < 0.16 ? 1.0 : 0.0;
                    float fade = saturate(1.0 - floorsW * 2.5);        // no moiré when the floors are smaller than a pixel
                    a = c * lerp(1.0, 0.55, lines * fade);
                    emit = a * 0.28;
                }
                else if (state == 4) { a = lerp(a, fixed3(0.20, 0.78, 0.35), filmAny ? 0.6 : 0.75); emit = a * 0.25; }
                else
                {
                    float g = dot(a, fixed3(0.299, 0.587, 0.114));
                    a = lerp(fixed3(g, g, g), a, filmAny ? 0.45 : 0.25) * 0.95;
                    if (filmAny) emit += F.emit * 0.5;
                }
            }
            if (IN.vface < 0) { a *= 0.35; emit *= 0.3; }
            bool sel = _AlatauSel > 0.5 && abs(IN.info.y - _AlatauSel) < 0.5;
            o.Albedo = sel ? _AlatauSelColor.rgb : a;
            // ambient light is added here ("noambient" above): the film look shades it by height and facing, the plain look as before
            half3 amb = ShadeSH9(half4(wn, 1.0));
            if (filmAny) amb = lerp(_AlatauSkyGround.rgb * 0.62, lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.5), wn.y * 0.5 + 0.5) * 0.84 * F.ao;
            o.Emission = (sel ? _AlatauSelColor.rgb * 0.45 : emit) + o.Albedo * amb;
            o.Specular = filmAny && !sel ? F.spec * (film ? 1.0 : 0.5) : 0.0;
            o.Alpha = 1;
        }
        ENDCG
    }
    FallBack "Diffuse"
}
