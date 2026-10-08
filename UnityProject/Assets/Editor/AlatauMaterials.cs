using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace AlatauCity.EditorTools
{
    /// <summary>Alatau City → Build material textures: packs the CC0 material photos of Assets/Textures/Materials (Poly Haven, see
    /// SOURCES.txt there; fetched by shots/tex/get_textures.py) into two texture arrays the film look samples:
    ///   Resources/Materials/AlatauMatAlbedo  colour
    ///   Resources/Materials/AlatauMatDetail  r, g = surface normal x, y   b = ambient occlusion   a = roughness
    /// and AlatauMatMean (one pixel per layer: its average colour, so a shader can use a texture as pattern and keep its own hue).
    /// The layer order is the two-digit prefix of the file names; the shaders know the layers by number (AlatauFilm.cginc).</summary>
    public static class AlatauMaterials
    {
        const string Src = "Assets/Textures/Materials", Dst = "Assets/Resources/Materials";
        const int Size = 1024;

        [MenuItem("Alatau City/Build material textures", priority = 20)]
        public static void Build()
        {
            var diffs = Directory.GetFiles(Src, "*_diff.jpg").OrderBy(f => f).ToArray();
            if (diffs.Length == 0) { Debug.LogError("[Alatau] no material textures in " + Src); return; }
            Directory.CreateDirectory(Dst);
            int n = diffs.Length;
            var albedo = new Texture2DArray(Size, Size, n, TextureFormat.DXT1, true, false) { name = "AlatauMatAlbedo", wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 8 };
            var detail = new Texture2DArray(Size, Size, n, TextureFormat.BC7, true, true) { name = "AlatauMatDetail", wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 8 };
            var mean = new Texture2D(16, 1, TextureFormat.RGBA32, false, false) { name = "AlatauMatMean", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            var means = new Color[16];
            for (int i = 0; i < n; i++)
            {
                string stem = diffs[i].Substring(0, diffs[i].Length - "_diff.jpg".Length);
                var d = Load(diffs[i]); var nor = Load(stem + "_nor.jpg"); var arm = Load(stem + "_arm.jpg");
                var dp = d.GetPixels32(); var np = nor.GetPixels32(); var ap = arm.GetPixels32();
                double r = 0, g = 0, b = 0; foreach (var p in dp) { r += p.r; g += p.g; b += p.b; }
                means[i] = new Color((float)(r / dp.Length / 255.0), (float)(g / dp.Length / 255.0), (float)(b / dp.Length / 255.0), 1f);
                var packed = new Color32[dp.Length];
                for (int k = 0; k < packed.Length; k++) packed[k] = new Color32(np[k].r, np[k].g, ap[k].r, ap[k].g);     // arm = AO, roughness, metal
                Put(albedo, i, dp, TextureFormat.DXT1); Put(detail, i, packed, TextureFormat.BC7);
                Object.DestroyImmediate(d); Object.DestroyImmediate(nor); Object.DestroyImmediate(arm);
                Debug.Log($"[Alatau] material {i}: {Path.GetFileName(stem)} mean colour {means[i]}");
            }
            mean.SetPixels(means); mean.Apply(false, false);
            albedo.Apply(false, false); detail.Apply(false, false);
            foreach (var (o, file) in new (Object, string)[] { (albedo, "AlatauMatAlbedo.asset"), (detail, "AlatauMatDetail.asset"), (mean, "AlatauMatMean.asset") })
            {
                string p = Dst + "/" + file; AssetDatabase.DeleteAsset(p); AssetDatabase.CreateAsset(o, p);
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[Alatau] material textures built: {n} layers of {Size} px");
        }

        static Texture2D Load(string file)
        {
            var t = new Texture2D(2, 2, TextureFormat.RGBA32, false, false); t.LoadImage(File.ReadAllBytes(file));
            if (t.width == Size && t.height == Size) return t;
            var rt = RenderTexture.GetTemporary(Size, Size, 0, RenderTextureFormat.ARGB32); Graphics.Blit(t, rt);
            var o = new Texture2D(Size, Size, TextureFormat.RGBA32, false, false); RenderTexture.active = rt; o.ReadPixels(new Rect(0, 0, Size, Size), 0, 0); o.Apply();
            RenderTexture.active = null; RenderTexture.ReleaseTemporary(rt); Object.DestroyImmediate(t); return o;
        }

        static void Put(Texture2DArray arr, int layer, Color32[] px, TextureFormat fmt)
        {
            var t = new Texture2D(Size, Size, TextureFormat.RGBA32, true, fmt == TextureFormat.BC7);
            t.SetPixels32(px); t.Apply(true, false);
            EditorUtility.CompressTexture(t, fmt, TextureCompressionQuality.Normal);
            for (int m = 0; m < t.mipmapCount; m++) arr.SetPixelData(t.GetPixelData<byte>(m), m, layer);
            Object.DestroyImmediate(t);
        }
    }
}
