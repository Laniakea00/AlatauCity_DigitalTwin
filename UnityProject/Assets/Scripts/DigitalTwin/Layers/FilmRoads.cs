using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Roads of the film look: the road graph of the twin (TwinData.Roads) drawn as ribbons that lie on the terrain, a wide
    /// pavement ribbon under a carriageway ribbon, so at a junction the carriageways cover the pavements. Width and lanes by road class
    /// (assumed typical cross-sections, not survey). Built once, shown only while the film look is on (FilmLook.Apply / Restore).</summary>
    public class FilmRoads : MonoBehaviour
    {
        GameObject root; bool built;

        /// <summary>Cross-section of a road class: half width of the carriageway, pavement width, lanes per direction, height above the ground.</summary>
        public static void Dims(TwinData.RoadClass c, out float half, out float walk, out int lanes, out float lift)
        {
            switch (c)
            {
                case TwinData.RoadClass.Highway: half = 11f; walk = 0f; lanes = 3; lift = 0.36f; break;
                case TwinData.RoadClass.Ring: half = 9f; walk = 0f; lanes = 2; lift = 0.31f; break;
                case TwinData.RoadClass.Main: half = 7.5f; walk = 3.5f; lanes = 2; lift = 0.26f; break;
                default: half = 4f; walk = 2.4f; lanes = 1; lift = 0.21f; break;
            }
        }

        public void Show(bool on)
        {
            if (on && !built && TwinData.Ready) Build();
            if (root != null && root.activeSelf != on) root.SetActive(on);
        }

        void Build()
        {
            built = true;
            var sh = Shader.Find("AlatauCity/Road"); if (sh == null) { Debug.LogWarning("[Alatau] film roads: shader missing"); return; }
            var mat = new Material(sh) { name = "Film roads" };
            root = new GameObject("Film roads");
            var V = new List<Vector3>(); var U0 = new List<Vector2>(); var U1 = new List<Vector4>(); var U2 = new List<Vector4>(); var T = new List<int>();
            var pts = new List<Vector2>(); var along = new List<float>(); int meshes = 0; float km = 0;
            void Flush()
            {
                if (V.Count == 0) return;
                var m = new Mesh { name = "Film roads " + meshes, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
                m.SetVertices(V); m.SetUVs(0, U0); m.SetUVs(1, U1); m.SetUVs(2, U2); m.SetTriangles(T, 0); m.RecalculateNormals(); m.RecalculateBounds();
                var go = new GameObject(m.name); go.transform.SetParent(root.transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = m; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off; mr.receiveShadows = true;
                V.Clear(); U0.Clear(); U1.Clear(); U2.Clear(); T.Clear(); meshes++;
            }
            foreach (var e in TwinData.Roads)
            {
                if (e.Geom == null || e.Geom.Length < 2) continue;
                Dims(e.Cls, out float half, out float walk, out int lanes, out float lift);
                // the polyline, with no step longer than 15 m so the ribbon follows the ground
                pts.Clear(); along.Clear(); float len = 0;
                for (int i = 0; i < e.Geom.Length; i++)
                {
                    if (i > 0)
                    {
                        float d = (e.Geom[i] - e.Geom[i - 1]).magnitude; int n = Mathf.Max(1, Mathf.CeilToInt(d / 15f));
                        for (int k = 1; k <= n; k++) { pts.Add(Vector2.Lerp(e.Geom[i - 1], e.Geom[i], k / (float)n)); along.Add(len + d * k / n); }
                        len += d;
                    }
                    else { pts.Add(e.Geom[0]); along.Add(0); }
                }
                if (len < 0.5f) continue;
                km += len / 1000f;
                var years = new Vector4(Y(e, 0), Y(e, 1), Y(e, 2), Y(e, 3));
                for (int pass = walk > 0f ? 0 : 1; pass < 2; pass++)
                {
                    float w = pass == 0 ? half + walk : half, up = pass == 0 ? 0.12f : lift; int v0 = V.Count;
                    for (int i = 0; i < pts.Count; i++)
                    {
                        Vector2 d = (pts[Mathf.Min(i + 1, pts.Count - 1)] - pts[Mathf.Max(i - 1, 0)]).normalized, left = new Vector2(-d.y, d.x);
                        for (int s = -1; s <= 1; s++)
                        {
                            Vector2 p = pts[i] + left * (w * s);
                            V.Add(new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + up, p.y)); U0.Add(new Vector2(w * s, along[i]));
                            U1.Add(new Vector4(half, pass, len, lanes)); U2.Add(years);
                        }
                        if (i > 0)
                        {
                            int a = v0 + (i - 1) * 3, b = v0 + i * 3;
                            for (int s = 0; s < 2; s++) { T.Add(a + s); T.Add(a + s + 1); T.Add(b + s); T.Add(a + s + 1); T.Add(b + s + 1); T.Add(b + s); }      // facing up
                        }
                    }
                }
                if (V.Count > 180000) Flush();
            }
            Flush();
            Debug.Log($"[Alatau] film roads: {km:0} km in {meshes} meshes");
        }

        static float Y(TwinData.RoadEdge e, int s) => e.Year != null && e.Year.Length > 0 ? e.Year[Mathf.Min(s, e.Year.Length - 1)] : 2025;
    }
}
