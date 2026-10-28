using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The grounds of the Gate centre around Iconic Complex (Resources/Landmarks/iconic_park.json, made by tools/build_iconic_park.py):
    /// pavements along the streets, forecourts at the buildings, lawns with paths, a pool, tree rows and groves. They are built while the
    /// tower rises: the works start next to it and spread block by block to the edge of the area (stage per block, vertex alpha);
    /// a block goes earth works → finished paving and grass with photo materials → trees planted. Before its turn the old ground shows.</summary>
    public class IconicPark : MonoBehaviour
    {
        public static IconicPark Instance;
        GameObject go; MeshRenderer mr; MaterialPropertyBlock mpb; Landmark host; bool built;
        /// <summary>Share of the grounds finished in the year shown (0 … 1).</summary>
        public static float Done { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        // not booted: the grounds were laid round the first site of the complex; the complex now stands in the heart of Gate with the
        // square, the ring and the gardens of its QTwin page round it (IconicDistrict)
        static void Boot() { }
        void Awake() { Instance = this; }

        static readonly Color32 PaveC = LM.C("#d2cbbd"), LawnC = LM.C("#86a95c"), WaterC = LM.C("#2f6f8f"), RimC = LM.C("#bdb6a8");
        static readonly Color32[] Leaf = { LM.C("#4f7d3a"), LM.C("#5d8a41"), LM.C("#6b9448"), LM.C("#45703a") };

        void Update()
        {
            if (!built) { TryBuild(); return; }
            float p = LandmarkSystem.Progress(host, LandmarkSystem.YearNow);
            float L = Mathf.Clamp01((p - 0.08f) / 0.90f); Done = L;
            bool on = L > 0f && !IconicDistrict.On;                             // the finished district brings its own streets and gardens
            if (go.activeSelf != on) go.SetActive(on);
            if (!on) return;
            mr.GetPropertyBlock(mpb);
            mpb.SetFloat("_Build", L < 0.999f ? 1f : 0f); mpb.SetFloat("_Land", L); mpb.SetFloat("_Park", 1f);
            mpb.SetFloat("_Reveal", 100000f); mpb.SetFloat("_Facade", 100000f); mpb.SetFloat("_Glow", -1f); mpb.SetFloat("_Ghost", 0f); mpb.SetFloat("_Hi", 0f); mpb.SetFloat("_H", 10f);
            mr.SetPropertyBlock(mpb);
        }

        void TryBuild()
        {
            var ls = LandmarkSystem.Instance; if (ls == null || !ls.Ready) return;
            host = ls.Get("iconic"); if (host == null) { enabled = false; return; }
            built = true;
            var ta = Resources.Load<TextAsset>("Landmarks/iconic_park"); var sh = Shader.Find("AlatauCity/Landmark");
            if (ta == null || sh == null) { Debug.LogWarning("[Alatau] Iconic grounds: data or shader missing"); enabled = false; return; }
            var d = JsonUtility.FromJson<Data>(ta.text);
            float cx = d.cx, cz = d.cz, baseY = host.Base != 0f ? host.Base : CityGround.HeightAt(cx, cz);
            var k = new LandmarkKit();
            Vector3 P(float x, float z) => new Vector3(x - cx, CityGround.HeightAt(x, z) + 0.14f - baseY, z - cz);
            for (int i = 0; i + 7 < d.tris.Length; i += 8)
            {
                // the plot of the complex has its own plaza and gardens (the BIM model)
                if (IconicDistrict.InPlot((d.tris[i] + d.tris[i + 2] + d.tris[i + 4]) / 3f, (d.tris[i + 1] + d.tris[i + 3] + d.tris[i + 5]) / 3f)) continue;
                int mat = Mathf.RoundToInt(d.tris[i + 6]); float st = d.tris[i + 7];
                var col = mat == LM.Water ? WaterC : mat == LM.Plant ? LawnC : PaveC;
                int v0 = k.VertexCount;
                var a = P(d.tris[i], d.tris[i + 1]); var b = P(d.tris[i + 2], d.tris[i + 3]); var c = P(d.tris[i + 4], d.tris[i + 5]);
                if (mat == LM.Water) { a.y -= 0.05f; b.y -= 0.05f; c.y -= 0.05f; }
                k.Tri(a, b, c, Vector3.up, col, mat, 1f, new Vector2(d.tris[i], d.tris[i + 1]), new Vector2(d.tris[i + 2], d.tris[i + 3]), new Vector2(d.tris[i + 4], d.tris[i + 5]));
                k.AlphaFrom(v0, (byte)Mathf.RoundToInt((1f - st) * 255f));
            }
            for (int i = 0; i + 3 < d.trees.Length; i += 4)
            {
                float x = d.trees[i], z = d.trees[i + 1], h = d.trees[i + 2], st = d.trees[i + 3];
                if (IconicDistrict.InPlot(x, z, 4f)) continue;                     // the plot of the complex
                int v0 = k.VertexCount;
                k.Tree(P(x, z) - Vector3.up * 0.14f, h, Leaf[(i / 4) % Leaf.Length], (i % 97) * 0.13f);
                k.AlphaFrom(v0, (byte)Mathf.RoundToInt((1f - st) * 255f));
            }
            var mesh = k.ToMesh("Iconic grounds");
            go = new GameObject("Iconic grounds · благоустройство"); go.transform.SetParent(transform, false);
            go.transform.position = new Vector3(cx, baseY, cz);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = new Material(sh) { name = "Iconic grounds" };
            mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On; mr.receiveShadows = true;
            mpb = new MaterialPropertyBlock(); go.SetActive(false);
            Debug.Log($"[Alatau] Iconic grounds: {d.tris.Length / 8} ground triangles, {d.trees.Length / 4} trees");
        }

        [System.Serializable] class Data { public float cx, cz; public float[] tris; public float[] trees; }
    }
}
