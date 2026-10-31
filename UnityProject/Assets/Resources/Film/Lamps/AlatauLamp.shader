// Street lamps of the film look (FilmLamps.cs), drawn with GPU instancing. Vertex colour: rgb = surface, a = 1 on the lamp's lens.
// uv0.xyz = the centre of the lens the vertex belongs to: far from the camera, at night, the lens grows into a point of light a few
// pixels wide (a real lamp reads as a bright dot in an aerial); by day it keeps its size.
// _AlatauLampOn (0..1): how far the lamps are lit (FilmLook.Lamps). _AlatauLampFade = (focus x, z, radius, fade width): lamps shrink
// away toward the edge of the drawn area instead of popping. A lamp standing on a landmark's plot is not drawn (AlatauOnPad).
// _AlatauBlackoutZone = (x, z, radius, strength) of a power outage (TourEnergy): the lamps inside it go dark, the rest stay lit.
Shader "AlatauCity/Lamp"
{
    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry" }
        CGPROGRAM
        #pragma surface surf Lambert vertex:vert addshadow nolightmap nodynlightmap nodirlightmap nometa noforwardadd
        #pragma multi_compile_instancing
        #pragma target 3.5
        #include "Assets/Shaders/AlatauFilm.cginc"
        float _AlatauLampOn; float4 _AlatauLampFade, _AlatauBlackoutZone;
        struct Input { float4 color : COLOR; float3 worldPos; };
        // how far the lamps are lit at a point: out inside the outage zone
        float LampOnAt(float2 xz)
        {
            float r = max(_AlatauBlackoutZone.z, 1.0);
            return _AlatauLampOn * (1.0 - _AlatauBlackoutZone.w * (1.0 - smoothstep(r * 0.85, r, distance(xz, _AlatauBlackoutZone.xy))));
        }
        void vert(inout appdata_full v)
        {
            float3 org = mul(unity_ObjectToWorld, float4(0, 0, 0, 1)).xyz;
            float fade = saturate((_AlatauLampFade.z - distance(org.xz, _AlatauLampFade.xy)) / max(_AlatauLampFade.w, 1.0));
            float pad = AlatauOnPad(org);
            float keep = fade * (1.0 - pad);
            // the lens: a point of light that stays visible from afar at night
            float camD = distance(_WorldSpaceCameraPos.xyz, org);
            float grow = 1.0 + v.color.a * LampOnAt(org.xz) * max(camD * 0.0026 - 1.0, 0.0);
            float3 p = v.texcoord.xyz + (v.vertex.xyz - v.texcoord.xyz) * grow;
            v.vertex.xyz = p * keep;
        }
        void surf(Input IN, inout SurfaceOutput o)
        {
            float lens = IN.color.a, on = LampOnAt(IN.worldPos.xz);
            o.Albedo = IN.color.rgb * (1.0 - 0.6 * lens * on);
            // warm-white LED (≈ 3500 K); bright enough to bloom
            o.Emission = float3(1.0, 0.80, 0.58) * lens * on * 5.0;
            o.Alpha = 1;
        }
        ENDCG
    }
    FallBack Off
}
