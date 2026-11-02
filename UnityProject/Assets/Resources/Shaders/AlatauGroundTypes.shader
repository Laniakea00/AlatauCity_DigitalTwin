// The yard types of the redrawn map (Resources/Map/map_ground.bytes, Layers/GroundTypes.cs) drawn into a render texture, numbers only
// (linear, point sampled): r = type (low 5 bits) + the lot's hash (top 3 bits), g = angle of the lot, b = distance to the nearest piece
// outline (0..1 over _W metres), a = the piece's year byte (0 the map's own year, 1 always, 26..254 = 2000 + v, 255 never).
// Pass 0: the pieces' triangles, later ones over earlier ones, b = 1. Pass 1: a quad round every outline segment that keeps the smaller
// distance in b (BlendOp Min), so AlatauGround.shader can draw the edges between the texels straight (GtExact).
// A piece whose earthworks have not begun by the year _AlatauGtYear (x = year, y = scenario pace _AlatauDevK) is left out (its
// triangles and outline collapse), so what lies under it shows until then. No light, no depth, both faces.
Shader "Hidden/AlatauCity/GroundTypes"
{
    CGINCLUDE
    #include "UnityCG.cginc"
    float4 _AlatauGtYear; float _W;
    // 1 when the piece of year byte yb has begun by the year (earthworks 2.5 years before its year, as AlatauGround.shader draws them)
    float Begun(float yb)
    {
        float y = yb < 0.5 ? 0.0 : yb < 1.5 ? 2000.0 : yb > 254.5 ? 1.0e5 : 2000.0 + yb;
        float eff = y <= 2025.5 ? y : 2025.0 + (y - 2025.0) * _AlatauGtYear.y;
        return _AlatauGtYear.x >= eff - 2.5 ? 1.0 : 0.0;
    }
    ENDCG
    SubShader
    {
        Pass
        {
            Cull Off ZWrite Off ZTest Always Blend Off
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            struct appdata { float4 vertex : POSITION; float4 color : COLOR; };
            struct v2f { float4 pos : SV_POSITION; float4 color : COLOR; };
            v2f vert(appdata v)
            {
                v2f o; o.color = v.color;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.pos = Begun(floor(v.color.a * 255.0 + 0.5)) > 0.5 ? o.pos : float4(2.0, 2.0, 2.0, 1.0);    // not yet: off the target
                return o;
            }
            float4 frag(v2f i) : SV_Target { return i.color; }
            ENDCG
        }
        Pass
        {
            // outline segments: vertex = (A.x, A.z, corner) in the chunk's metres, uv = B; corner bit 0 = end (A or B), bit 1 = side
            Cull Off ZWrite Off ZTest Always ColorMask B BlendOp Min Blend One One
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            struct appdata { float4 vertex : POSITION; float2 uv : TEXCOORD0; float4 color : COLOR; };
            struct v2f { float4 pos : SV_POSITION; float3 st : TEXCOORD0; };
            v2f vert(appdata v)
            {
                float2 a = v.vertex.xy, b = v.uv, d = b - a; float len = length(d);
                d = len > 1e-4 ? d / len : float2(1.0, 0.0);
                float2 n = float2(-d.y, d.x);
                float corner = floor(v.vertex.z + 0.5), atB = fmod(corner, 2.0), side = corner >= 1.5 ? 1.0 : -1.0;
                float along = atB > 0.5 ? len + _W : -_W;
                float2 p = a + d * along + n * side * _W;
                v2f o; o.pos = UnityObjectToClipPos(float4(p, 0.0, 1.0)); o.st = float3(along, side * _W, len);
                o.pos = Begun(floor(v.color.a * 255.0 + 0.5)) > 0.5 ? o.pos : float4(2.0, 2.0, 2.0, 1.0);
                return o;
            }
            float4 frag(v2f i) : SV_Target
            {
                float ds = length(float2(max(max(-i.st.x, i.st.x - i.st.z), 0.0), i.st.y));
                return float4(0.0, 0.0, saturate(ds / max(_W, 1e-3)), 0.0);
            }
            ENDCG
        }
    }
}
