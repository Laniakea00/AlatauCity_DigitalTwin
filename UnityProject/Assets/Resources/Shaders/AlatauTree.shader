// Trees of the film look, drawn in instanced batches by FilmTrees.cs. Colours are in the mesh (crown lighter towards the top);
// each tree has a tint and the year its place is developed (from the base map), so trees appear with their quarter.
Shader "AlatauCity/Tree"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        CGPROGRAM
        #pragma surface surf Leaf fullforwardshadows addshadow vertex:vert
        #pragma multi_compile_instancing
        #pragma target 3.5
        float _AlatauYear, _AlatauYearF, _AlatauGrow, _AlatauDevK;
        UNITY_INSTANCING_BUFFER_START(Props)
            UNITY_DEFINE_INSTANCED_PROP(float, _TreeYear)
            UNITY_DEFINE_INSTANCED_PROP(float4, _TreeTint)
        UNITY_INSTANCING_BUFFER_END(Props)
        float4 _AlatauSkyHorizon, _AlatauSkyZenith; float _AlatauFilm;
        struct Input { float4 color : COLOR; float3 lp; float3 viewDir; float3 worldPos; float4 tv; float3 cd; };
        void vert(inout appdata_full v, out Input o)
        {
            UNITY_INITIALIZE_OUTPUT(Input, o);
            // every tree its own: a hash of where it stands gives its height, crown width, a small step out of the row and its hue
            // (the same in the shadow pass, so the shadow fits). Hedges (stretched along one axis) stay as they are.
            float3 op = float3(unity_ObjectToWorld[0].w, unity_ObjectToWorld[1].w, unity_ObjectToWorld[2].w);
            float sx = length(float3(unity_ObjectToWorld[0].x, unity_ObjectToWorld[1].x, unity_ObjectToWorld[2].x));
            float sz = length(float3(unity_ObjectToWorld[0].z, unity_ObjectToWorld[1].z, unity_ObjectToWorld[2].z));
            float2 hp = op.xz * 0.1373;
            float4 h = frac(sin(float4(dot(hp, float2(12.9898, 78.233)), dot(hp, float2(39.3468, 11.135)), dot(hp, float2(73.156, 52.235)), dot(hp, float2(26.651, 94.673)))) * 43758.5453);
            float hedge = step(0.35, abs(sx - sz) / max(max(sx, sz), 1e-3));
            float hs = lerp(0.72 + 0.62 * h.x * h.x + 0.12 * h.y, 1.0, hedge), ws = lerp(0.82 + 0.36 * h.y, 1.0, hedge);
            v.vertex.xyz *= float3(ws, hs, ws);
            v.vertex.xz += (h.zw - 0.5) * 1.4 / max(sx, 0.2) * (1.0 - hedge);
            o.tv = float4(h.xyz, hedge);
            o.lp = v.vertex.xyz;
            o.cd = v.texcoord.xyz;                       // leaf cards of the near crowns: card uv and a seed (vertex alpha 0 marks a card)
            // a crown is lit by the whole sky: its normals lean up, so the underside is a soft shade and not a dark ball
            float leafV = step(v.color.r, v.color.g);
            v.normal = normalize(lerp(v.normal, float3(0, 1, 0), 0.40 * leafV));
            // wind from the west-south-west: the tree leans and sways a little (more towards the top, a shear of a few centimetres
            // per metre at most, so nothing stretches) and the leaves flutter; hedges stand still. The same in the shadow pass.
            float3 wdir = mul((float3x3)unity_WorldToObject, float3(-0.94, 0.0, -0.34));
            float hgt = max(v.vertex.y - 1.2, 0.0), tt = _Time.y;
            float sway = 0.55 + 0.30 * sin(tt * 0.9 + h.x * 6.2832) + 0.15 * sin(tt * 2.3 + h.y * 6.2832);
            float flutter = sin(tt * 5.3 + dot(o.lp, float3(2.1, 1.7, 2.9))) * 0.035 * leafV;
            v.vertex.xyz += (wdir * (hgt * hgt * 0.0016 * sway) + (wdir * 0.5 + float3(0.0, 0.6, 0.0)) * flutter) * (1.0 - hedge);
        }
        // value noise in 3D for the leaf clumps (object space, so every tree has its own)
        float LHash(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
        float LNoise(float3 p)
        {
            float3 i = floor(p), f = frac(p); f = f * f * (3.0 - 2.0 * f);
            return lerp(lerp(lerp(LHash(i), LHash(i + float3(1, 0, 0)), f.x), lerp(LHash(i + float3(0, 1, 0)), LHash(i + float3(1, 1, 0)), f.x), f.y),
                        lerp(lerp(LHash(i + float3(0, 0, 1)), LHash(i + float3(1, 0, 1)), f.x), lerp(LHash(i + float3(0, 1, 1)), LHash(i + float3(1, 1, 1)), f.x), f.y), f.z);
        }
        half4 LightingLeaf(SurfaceOutput s, half3 lightDir, half3 viewDir, half atten)
        {
            // foliage lets some light through: half-wrapped diffuse, and a glow at the edge of a crown seen against the sun
            half nl = saturate(dot(s.Normal, lightDir) * 0.65 + 0.35);
            half back = pow(saturate(dot(-viewDir, lightDir)), 4.0) * (1.0 - saturate(dot(s.Normal, viewDir))) * 0.6;
            half4 c; c.rgb = s.Albedo * _LightColor0.rgb * (nl * atten + back * half3(1.0, 1.1, 0.6)); c.a = s.Alpha; return c;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float dev = UNITY_ACCESS_INSTANCED_PROP(Props, _TreeYear);
            float k = _AlatauDevK > 0.01 ? _AlatauDevK : 1.0;
            float eff = dev <= 2025.5 ? dev : 2025.0 + (dev - 2025.0) * k;
            float now = _AlatauGrow > 0.5 ? _AlatauYearF + 1.0 : (_AlatauYear < 1 ? 2050.0 : _AlatauYear);
            float4 t = UNITY_ACCESS_INSTANCED_PROP(Props, _TreeTint);
            // near / far crowns cross-dissolve (FilmTrees): w <= 1 keeps that share of the surface, w in (1, 2] the rest of it
            float fadeW = t.w < 0.001 ? 1.0 : t.w;
            float dz = LHash(floor(IN.lp * 12.0) + 0.37);          // cells of about a pixel at that distance: reads as a soft fade
            float keep = fadeW <= 1.0 ? fadeW - dz : dz - (fadeW - 1.0);
            // a leaf card: a ragged clump of leaves with holes towards its rim (two noises over a round falloff)
            float card = step(IN.color.a, 0.5);
            float2 cq = IN.cd.xy * 2.0 - 1.0;
            float cn1 = LNoise(float3(IN.cd.xy * 5.0, IN.cd.z * 31.0)), cn2 = LNoise(float3(IN.cd.xy * 13.0, IN.cd.z * 17.0 + 5.0));
            float cardA = (1.0 - dot(cq, cq)) + (cn1 - 0.5) * 1.0 + (cn2 - 0.5) * 0.7 - 0.12;
            // the outer clumps of a near crown (vertex alpha 0.75): leaf-sized holes, more of them towards the outline, so the
            // silhouette breaks into leaves and the shaded inside shows through
            float leafy = step(0.5, IN.color.a) * step(IN.color.a, 0.9);
            float rimL = 1.0 - saturate(dot(normalize(IN.viewDir), o.Normal));
            float ln = LNoise(IN.lp * 9.0 + IN.tv.x * 7.0) * 0.65 + LNoise(IN.lp * 21.0) * 0.35;
            float leafyA = ln - (0.20 + 0.48 * rimL * rimL);
            clip(min(min(now - eff + 0.2, keep), min(lerp(1.0, cardA, card), lerp(1.0, leafyA, leafy))));
            // leaf clumps: lit tops, dark gaps between them; trunks (brown, below the crown) stay plain
            float leaf = step(IN.color.r, IN.color.g);
            float cl = LNoise(IN.lp * 1.35 + t.r * 17.0) * 0.65 + LNoise(IN.lp * 3.4) * 0.35;
            float3 alb = IN.color.rgb * t.rgb * lerp(1.0, lerp(0.70, 1.12, smoothstep(0.25, 0.8, cl)), leaf);
            // up close: leaf-sized flecks (lit leaves and the gaps between them), faded out before they would shimmer
            float nearK = saturate(1.0 - distance(_WorldSpaceCameraPos, IN.worldPos) / 110.0);
            float lf = LNoise(IN.lp * 7.0 + t.g * 11.0) * 0.6 + cn2 * 0.4 * card;
            alb *= lerp(1.0, 0.80 + 0.40 * lf, leaf * max(nearK, max(card, leafy)));
            // natural summer greens, never lime: each tree takes one of a few hues (deep green, olive, a cooler grey-green, a fresh
            // mid green) and its own brightness; the crown's yellow is taken down
            float hk = IN.tv.y;
            float3 hue = hk < 0.34 ? float3(0.80, 0.93, 0.84) : hk < 0.62 ? float3(0.97, 0.95, 0.76) : hk < 0.84 ? float3(0.84, 0.92, 0.88) : float3(0.90, 1.00, 0.80);
            hue *= 0.74 + 0.30 * IN.tv.x * (1.0 - IN.tv.w) + 0.12 * IN.tv.w;
            alb *= lerp(float3(1, 1, 1), hue * float3(0.90, 0.97, 1.0), leaf);
            // sunlit tops a little warmer, the underside cooler
            float up = saturate(o.Normal.y * 0.5 + 0.5);
            alb *= lerp(1.0, lerp(float3(0.88, 0.94, 1.02), float3(1.03, 1.02, 0.93), up), leaf);
            // seen from far away a crown is a few pixels: lift its shade towards the lit colour so groves read as soft green,
            // not as black pepper on the pale ground
            float far = saturate((distance(_WorldSpaceCameraPos, IN.worldPos) - 700.0) / 1800.0);
            alb = lerp(alb, alb * 1.22 + float3(0.020, 0.024, 0.010), far * leaf * 0.6);
            o.Albedo = alb; o.Alpha = 1;
            // the sky on the leaves' edge (sheen) and a little light through the crown
            float rim = pow(1.0 - saturate(dot(normalize(IN.viewDir), o.Normal)), 3.0);
            o.Emission = leaf * _AlatauFilm * (lerp(_AlatauSkyHorizon.rgb, _AlatauSkyZenith.rgb, 0.4) * alb * 0.25 + _AlatauSkyHorizon.rgb * rim * 0.10 * (0.6 + 0.4 * cl));
        }
        ENDCG
    }
    FallBack Off
}
