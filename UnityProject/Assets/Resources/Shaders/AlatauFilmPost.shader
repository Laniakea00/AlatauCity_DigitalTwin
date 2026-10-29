// Picture finish of the film look, run by FilmPost.cs on the main camera:
//   0 ambient occlusion from the depth buffer   1 depth-aware blur of it   2 apply it
//   3 depth of field (soft foreground and distance around the focus)       4 bloom: keep the bright parts
//   5 bloom: shrink / blur    6 bloom: grow and add    7 final: exposure, soft highlights, contrast, tone, vignette, grain
// The project is in gamma colour space: the final pass turns the picture to linear light for the filmic curve and back.
Shader "Hidden/AlatauCity/FilmPost"
{
    Properties { _MainTex ("", 2D) = "white" {} }
    CGINCLUDE
    #include "UnityCG.cginc"
    sampler2D _MainTex; float4 _MainTex_TexelSize;
    sampler2D_float _CameraDepthTexture;
    sampler2D _AoTex, _BloomTex, _AddTex;
    float4 _Proj;      // x = 1 / P00, y = 1 / P11, z = AO radius in metres, w = AO strength
    float4 _Fade;      // x = fog density (the occlusion fades with the haze), y = time (grain)
    float4 _Grade;     // exposure, contrast, saturation, vignette
    float4 _BloomP;    // threshold, intensity, filmic curve (0 = the old soft shoulder, 1 = ACES), exposure into the curve
    float4 _Dir;       // blur step in uv
    float4 _Dof;       // focus distance m, sharp range m, largest blur in pixels, 1 = on
    struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float2 uvD : TEXCOORD1; };
    v2f vert(appdata_img v)
    {
        v2f o; o.pos = UnityObjectToClipPos(v.vertex); o.uv = v.texcoord; o.uvD = v.texcoord;
        #if UNITY_UV_STARTS_AT_TOP
        if (_MainTex_TexelSize.y < 0) o.uvD.y = 1 - o.uvD.y;
        #endif
        return o;
    }
    float Eye(float2 uv) { return LinearEyeDepth(SAMPLE_DEPTH_TEXTURE_LOD(_CameraDepthTexture, float4(uv, 0, 0))); }
    float3 VPos(float2 uv) { float z = Eye(uv); return float3((uv * 2 - 1) * _Proj.xy * z, z); }      // x right, y up, z into the screen

    float4 fragAO(v2f i) : SV_Target
    {
        float3 P = VPos(i.uvD);
        if (P.z > _ProjectionParams.z * 0.9) return 1;
        float2 px = 1.0 / _ScreenParams.xy;
        // the surface normal from the depth of the neighbours, taking on each axis the side that is on the same surface
        float3 r = VPos(i.uvD + float2(px.x, 0)) - P, l = P - VPos(i.uvD - float2(px.x, 0));
        float3 u = VPos(i.uvD + float2(0, px.y)) - P, d = P - VPos(i.uvD - float2(0, px.y));
        float3 n = normalize(cross(abs(u.z) < abs(d.z) ? u : d, abs(r.z) < abs(l.z) ? r : l));
        float R = _Proj.z;
        float ry = clamp(R / (_Proj.y * P.z) * 0.5, 2.5 * px.y, 0.09);
        float2 ruv = float2(ry * _ScreenParams.y / _ScreenParams.x, ry);
        float rnd = frac(sin(dot(i.pos.xy, float2(12.9898, 78.233))) * 43758.5453) * 6.2831853;
        float occ = 0;
        for (int k = 0; k < 12; k++)
        {
            float a = rnd + k * 2.39996, s = (k + 0.5) / 12.0;
            float3 v = VPos(i.uvD + float2(cos(a), sin(a)) * s * ruv) - P;
            float vv = dot(v, v) + 1e-4;
            occ += saturate(dot(v, n) / sqrt(vv) - 0.12) * saturate(1.0 - vv / (R * R));
        }
        float fog = exp(-pow(P.z * _Fade.x, 2.0));
        return 1.0 - saturate(occ / 12.0 * _Proj.w) * fog;
    }

    float4 fragBlur(v2f i) : SV_Target
    {
        float z0 = Eye(i.uvD), sum = 0, w = 0;
        for (int k = -3; k <= 3; k++)
        {
            float2 o = _Dir.xy * k;
            float wk = (4.0 - abs(k)) * saturate(1.0 - abs(Eye(i.uvD + o) - z0) / (0.03 * z0 + 0.5));
            sum += tex2Dlod(_MainTex, float4(i.uv + o, 0, 0)).r * wk; w += wk;
        }
        return sum / max(w, 1e-4);
    }

    float4 fragApply(v2f i) : SV_Target
    {
        float4 c = tex2D(_MainTex, i.uv); float ao = tex2D(_AoTex, i.uv).r;
        c = clamp(c, 0.0, 16.0);      // a broken or extreme pixel (a sun glint on glass) must not spread into a white disc by blur and bloom
        // shade a little towards a cool tone instead of plain black
        c.rgb *= lerp(float3(0.52, 0.56, 0.66), float3(1, 1, 1), ao) * lerp(0.86, 1.0, ao);
        return c;
    }

    float4 fragDof(v2f i) : SV_Target
    {
        float4 c0 = tex2D(_MainTex, i.uv);
        float z = Eye(i.uvD);
        float coc = saturate((abs(z - _Dof.x) - _Dof.y) / max(_Dof.y * 2.2, 1.0)) * _Dof.z * _Dof.w;
        if (coc < 0.35) return c0;
        float4 sum = c0; float w = 1;
        for (int k = 0; k < 16; k++)
        {
            float a = k * 2.39996, s = sqrt((k + 0.5) / 16.0);
            float2 o = float2(cos(a), sin(a)) * s * coc * _MainTex_TexelSize.xy;
            float zk = Eye(i.uvD + o);
            float ck = saturate((abs(zk - _Dof.x) - _Dof.y) / max(_Dof.y * 2.2, 1.0)) * _Dof.z;
            float wk = zk < z - 0.02 * z ? saturate(ck / max(coc, 0.01)) : 1.0;      // sharp things in front do not smear over the blur behind
            sum += tex2Dlod(_MainTex, float4(i.uv + o, 0, 0)) * wk; w += wk;
        }
        return sum / w;
    }

    float4 fragBright(v2f i) : SV_Target
    {
        float3 c = clamp(tex2D(_MainTex, i.uv).rgb, 0.0, 16.0);
        float l = max(c.r, max(c.g, c.b));
        return float4(c * saturate((l - _BloomP.x) / max(l, 1e-3)) , 1);
    }

    float4 fragDown(v2f i) : SV_Target
    {
        float4 d = _MainTex_TexelSize.xyxy * float4(-1, -1, 1, 1);
        return (tex2D(_MainTex, i.uv + d.xy) + tex2D(_MainTex, i.uv + d.zy) + tex2D(_MainTex, i.uv + d.xw) + tex2D(_MainTex, i.uv + d.zw)) * 0.25;
    }

    float4 fragUp(v2f i) : SV_Target
    {
        float4 d = _MainTex_TexelSize.xyxy * float4(-0.5, -0.5, 0.5, 0.5);
        float4 s = (tex2D(_MainTex, i.uv + d.xy) + tex2D(_MainTex, i.uv + d.zy) + tex2D(_MainTex, i.uv + d.xw) + tex2D(_MainTex, i.uv + d.zw)) * 0.25;
        return s + tex2D(_AddTex, i.uv);
    }

    float4 fragFinal(v2f i) : SV_Target
    {
        float3 c = tex2D(_MainTex, i.uv).rgb + tex2D(_BloomTex, i.uv).rgb * _BloomP.y;
        c *= _Grade.x;
        // soft highlights: untouched below 0.62, then bending towards 1 instead of clipping
        float3 hi = max(c - 0.62, 0.0) / 0.38;
        float3 soft = min(c, 0.62) + 0.38 * (1.0 - exp(-hi));
        // the filmic curve of a camera: to linear light, the fitted ACES curve (Narkowicz 2015: a toe that deepens the shadows,
        // a long shoulder for the sky and glints), back to display values
        float3 lin = pow(max(c, 0.0), 2.2) * _BloomP.w;
        float3 aces = saturate(lin * (2.51 * lin + 0.03) / (lin * (2.43 * lin + 0.59) + 0.14));
        c = lerp(soft, pow(aces, 0.4545), _BloomP.z);
        c = (c - 0.46) * _Grade.y + 0.46;
        float l = dot(c, float3(0.299, 0.587, 0.114));
        c = lerp(float3(l, l, l), c, _Grade.z);
        // saturated greens (lawns, planted roofs) towards a natural olive: no "game" green
        float gm = saturate((c.g - max(c.r, c.b)) * 5.0);
        c = lerp(c, lerp(float3(l, l, l), c, 0.80) + float3(0.012, 0.0, -0.01), gm * 0.85);
        // warm lights, cool shadows
        c *= lerp(float3(0.955, 0.99, 1.045), float3(1.035, 1.0, 0.955), smoothstep(0.15, 0.85, l));
        float2 q = i.uv - 0.5;
        c *= 1.0 - _Grade.w * smoothstep(0.25, 0.95, dot(q, q) * 2.2);
        c += (frac(sin(dot(i.pos.xy + _Fade.y, float2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.012;
        return float4(saturate(c), 1);
    }
    ENDCG
    SubShader
    {
        Cull Off ZWrite Off ZTest Always
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragAO
            #pragma target 3.5
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragBlur
            #pragma target 3.5
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragApply
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragDof
            #pragma target 3.5
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragBright
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragDown
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragUp
            ENDCG }
        Pass { CGPROGRAM
            #pragma vertex vert
            #pragma fragment fragFinal
            ENDCG }
    }
}
