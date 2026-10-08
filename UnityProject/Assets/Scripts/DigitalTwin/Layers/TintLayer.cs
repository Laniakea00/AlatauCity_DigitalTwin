using System;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Analysis colouring of the 57k buildings (heat maps by building): one RGBA32 lookup bid → colour + strength, read by AlatauLit in mode 2.</summary>
    public static class TintLayer
    {
        static Texture2D tex; static Color32[] px = new Color32[0];
        static readonly int TexId = Shader.PropertyToID("_AlatauTintTex"), ModeId = Shader.PropertyToID("_AlatauMode");
        public static bool Active { get; private set; }

        public static void Enable() { Active = true; Ensure(); Shader.SetGlobalTexture(TexId, tex); Shader.SetGlobalFloat(ModeId, 2f); }
        public static void Disable() { Active = false; Shader.SetGlobalFloat(ModeId, 0f); }

        static void Ensure()
        {
            if (tex != null) return;
            tex = new Texture2D(256, 256, TextureFormat.RGBA32, false, false) { name = "Alatau tint", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            px = new Color32[256 * 256];
        }

        /// <summary>Colour every building; return alpha 0 for "no tint" (grey context).</summary>
        public static void Apply(Func<BuildingInfo, Color> colorOf)
        {
            Ensure(); Array.Clear(px, 0, px.Length);
            var db = CityDatabase.Instance; if (db == null) return;
            foreach (var b in db.Buildings) if (b != null && b.Bid >= 0 && b.Bid < px.Length) px[b.Bid] = colorOf(b);
            px[0] = new Color32(0, 0, 0, 0);   // terrain tiles carry uv2.y ≈ 1 (their own UVs) and would read slot 0 — keep it neutral
            tex.SetPixels32(px); tex.Apply(false, false); Shader.SetGlobalTexture(TexId, tex);
        }
    }
}
