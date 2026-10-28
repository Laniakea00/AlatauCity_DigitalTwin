using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The round of Iconic Complex as on the QTwin page of the complex (QTwinData.Gate, made by tools/build_gate_district.py
    /// from its model of the Gate District): the oval square round the complex with its gardens and trees, the ring road, the crescent
    /// of buildings round it and the courtyards beyond. The complex stands in the heart of Gate, beside the roundabout its radial streets
    /// meet at, west of the LRT trunk and its station (the line and the hotels east of it are left clear).
    /// Its ground lies on the terrain of the twin. It stands once the complex is finished; while it does, the city's own buildings,
    /// roads and line layers give way inside its area (_AlatauGateTex).</summary>
    public class IconicDistrict : MonoBehaviour
    {
        public static IconicDistrict Instance;
        /// <summary>The district stands in the year shown.</summary>
        public static bool On { get; private set; }
        GameObject root; Landmark host; bool built;
        readonly List<(int s, Matrix4x4[] m, MaterialPropertyBlock p, Vector3 c)> treeBatches = new List<(int, Matrix4x4[], MaterialPropertyBlock, Vector3)>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Gate District (QTwin)").AddComponent<IconicDistrict>(); }
        void Awake() { Instance = this; }

        static readonly int GateId = Shader.PropertyToID("_AlatauGate"), GateOnId = Shader.PropertyToID("_AlatauGateOn"),
            GateTexId = Shader.PropertyToID("_AlatauGateTex"), GateHalfId = Shader.PropertyToID("_AlatauGateHalf");
        const int Tiles = 4;                                       // the district is cut into 4 × 4 renderers, so the camera culls them
        const float Lift = 0.12f;                                  // the ground of the district a hair above the terrain

        // ------------------------------------------------------------------ the area (static: the landmark plots ask before it is built)
        static bool frame; static Vector2 fc; static float fca, fsa;
        static bool Frame()
        {
            if (frame) return true;
            var l = LandmarkSystem.Instance != null ? LandmarkSystem.Instance.Get("iconic") : null;
            if (l == null) foreach (var q in LandmarkCatalog.All()) if (q.Id == "iconic") l = q;
            if (l == null) return false;
            fc = new Vector2(l.X, l.Z); float a = l.Yaw * Mathf.Deg2Rad; fca = Mathf.Cos(a); fsa = Mathf.Sin(a); frame = true; return true;
        }
        /// <summary>The landmark's local frame of a world point (as CityGround.Flatten / LandmarkSystem.OnPlot).</summary>
        static Vector2 Local(float x, float z) { float dx = x - fc.x, dz = z - fc.y; return new Vector2(dx * fca - dz * fsa, dx * fsa + dz * fca); }
        /// <summary>Is a world point inside the area of the district (its blocks and streets)?</summary>
        public static bool InGate(float x, float z) { if (!Frame()) return false; var p = Local(x, z); return QTwinData.InArea(p.x, p.y); }
        /// <summary>Is a world point on the plot of the complex (its BIM model: towers, pavilions, plaza)?</summary>
        public static bool InPlot(float x, float z, float margin = 0f) { if (!Frame()) return false; var p = Local(x, z); return Mathf.Abs(p.x) < 136f + margin && Mathf.Abs(p.y) < 100f + margin; }
        /// <summary>Kept for the layers that asked about the old round site: the area of the district.</summary>
        public static bool InSite(float x, float z, float margin = 0f) => InGate(x, z);
        public static bool Covers(float x, float z, float margin = 3f) => InGate(x, z);

        void Update()
        {
            if (!built) { TryBuild(); return; }
            bool on = TwinState.Year < 1 || LandmarkSystem.Progress(host, LandmarkSystem.YearNow) >= 0.999f;
            if (root.activeSelf != on) { root.SetActive(on); Shader.SetGlobalFloat(GateOnId, on ? 1f : 0f); }
            On = on;
            if (!on) return;
            var ft = AlatauCity.DigitalTwin.FilmTrees.Instance; var cam = Camera.main;
            if (ft == null || cam == null) return;
            var cp = cam.transform.position;
            foreach (var b in treeBatches)
            {
                float d = (b.c - cp).magnitude; if (d > 6000f) continue;
                if (!ft.DrawBatch(b.s, b.m, b.m.Length, b.p, d < 1500f, d < 2600f)) break;
            }
        }

        // ------------------------------------------------------------------ building
        void TryBuild()
        {
            var ls = LandmarkSystem.Instance; if (ls == null || !ls.Ready) return;
            built = true;
            host = ls.Get("iconic"); var sh = Shader.Find("AlatauCity/Landmark"); var d = QTwinData.Gate();
            if (host == null || sh == null || d == null) { Debug.LogWarning("[Alatau] Gate District: data, model or shader missing"); enabled = false; return; }
            Frame();
            float baseY = host.Base != 0f ? host.Base : CityGround.HeightAt(host.X, host.Z);
            var rot = Quaternion.Euler(0f, host.Yaw, 0f); var org = new Vector3(host.X, baseY, host.Z);
            root = new GameObject("Gate District · квартал по генплану (QTwin)"); root.transform.SetParent(transform, false);
            root.transform.SetPositionAndRotation(org, rot);
            var mat = new Material(sh) { name = "Gate District" }; mat.EnableKeyword("ALATAU_QT_GATE");      // its part of AlatauQTwin.cginc

            // every vertex on the terrain (the page's ground is flat at 0): walls keep their plan, so a building stays upright
            var m = d.Mesh; int nv = m.P.Length;
            var pos = new Vector3[nv];
            for (int i = 0; i < nv; i++)
            {
                var p = m.P[i]; var w = org + rot * new Vector3(p.x, 0f, p.z);
                pos[i] = new Vector3(p.x, CityGround.HeightAt(w.x, w.z) - baseY + p.y + Lift, p.z);
            }
            // cut into tiles by the centre of each triangle
            float tileW = 2f * d.Half / Tiles; var lists = new List<int>[Tiles * Tiles];
            for (int t = 0; t < lists.Length; t++) lists[t] = new List<int>();
            for (int t = 0; t + 2 < m.I.Length; t += 3)
            {
                var c = (m.P[m.I[t]] + m.P[m.I[t + 1]] + m.P[m.I[t + 2]]) / 3f;
                int tx = Mathf.Clamp(Mathf.FloorToInt((c.x + d.Half) / tileW), 0, Tiles - 1), tz = Mathf.Clamp(Mathf.FloorToInt((c.z + d.Half) / tileW), 0, Tiles - 1);
                var l = lists[tz * Tiles + tx]; l.Add(m.I[t]); l.Add(m.I[t + 1]); l.Add(m.I[t + 2]);
            }
            var map = new int[nv]; int tris = 0;
            for (int ti = 0; ti < lists.Length; ti++)
            {
                var L = lists[ti]; if (L.Count == 0) continue;
                for (int i = 0; i < nv; i++) map[i] = -1;
                var V = new List<Vector3>(); var N = new List<Vector3>(); var C = new List<Color32>(); var U0 = new List<Vector2>(); var U1 = new List<Vector2>();
                var idx = new int[L.Count];
                for (int k = 0; k < L.Count; k++)
                {
                    int i = L[k];
                    if (map[i] < 0)
                    {
                        map[i] = V.Count; V.Add(pos[i]); N.Add(m.N[i]); C.Add(new Color32(255, 255, 255, 255));
                        U0.Add(new Vector2(m.U[i], m.P[i].y)); U1.Add(new Vector2(LM.QTwin, m.Tag[i]));
                    }
                    idx[k] = map[i];
                }
                var mesh = new Mesh { name = "Gate District " + ti, indexFormat = V.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
                mesh.SetVertices(V); mesh.SetNormals(N); mesh.SetColors(C); mesh.SetUVs(0, U0); mesh.SetUVs(1, U1);
                mesh.SetUVs(2, new List<Vector2>(new Vector2[V.Count])); mesh.SetUVs(3, new List<Vector4>(new Vector4[V.Count]));
                mesh.SetTriangles(idx, 0); mesh.RecalculateBounds();
                var go = new GameObject("Tile " + ti); go.transform.SetParent(root.transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat; mr.shadowCastingMode = ShadowCastingMode.On; mr.receiveShadows = true;
                tris += L.Count / 3;
            }
            // the trees (outside the plot of the complex; the plot plants its own): batches of up to 1023 per species and tile
            var byKey = new Dictionary<int, (List<Matrix4x4> m, List<float> y, List<Vector4> t, Vector3 c)>();
            var rnd = new System.Random(2031);
            for (int i = 0; i < d.Trees.Length; i++)
            {
                var t = d.Trees[i]; if (Mathf.Abs(t.x) < 136f && Mathf.Abs(t.z) < 100f) continue;
                var w = org + rot * new Vector3(t.x, 0f, t.z);
                int sp = d.Kind[i] == 2 ? 1 : d.Kind[i] == 3 ? 2 : 0;
                int tx = Mathf.Clamp(Mathf.FloorToInt((t.x + d.Half) / tileW), 0, Tiles - 1), tz = Mathf.Clamp(Mathf.FloorToInt((t.z + d.Half) / tileW), 0, Tiles - 1);
                int key = (tz * Tiles + tx) * 4 + sp;
                if (!byKey.TryGetValue(key, out var b)) byKey[key] = b = (new List<Matrix4x4>(), new List<float>(), new List<Vector4>(), w);
                // the page's crown is 8.6 m wide and 10.5 m tall at size 1; the film trees are about 6.6 × 7 m
                float s = t.w * 1.35f, gy = CityGround.HeightAt(w.x, w.z) + Mathf.Max(t.y - 0.3f, 0f) - 0.1f;
                b.m.Add(Matrix4x4.TRS(new Vector3(w.x, gy, w.z), Quaternion.Euler(0f, (float)rnd.NextDouble() * 360f, 0f), new Vector3(s, s * (0.9f + 0.25f * (float)rnd.NextDouble()), s)));
                b.y.Add(2025f); float v = 0.86f + 0.26f * (float)rnd.NextDouble(), k = (float)rnd.NextDouble();
                b.t.Add(new Vector4(v * (1f + 0.10f * k), v, v * (1f - 0.12f * k), 1f));
            }
            int nt = 0;
            foreach (var kv in byKey)
            {
                var b = kv.Value;
                for (int o = 0; o < b.m.Count; o += 1023)
                {
                    int n = Mathf.Min(1023, b.m.Count - o); var p = new MaterialPropertyBlock();
                    p.SetFloatArray("_TreeYear", b.y.GetRange(o, n)); p.SetVectorArray("_TreeTint", b.t.GetRange(o, n));
                    treeBatches.Add((kv.Key % 4, b.m.GetRange(o, n).ToArray(), p, b.c)); nt += n;
                }
            }
            // the area for the shaders of the city (roads, line layers): the mask in the landmark's frame
            var tex = new Texture2D(d.W, d.W, TextureFormat.R8, false, true) { name = "Gate District area", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            tex.SetPixelData(d.Mask, 0); tex.Apply(false, true);
            Shader.SetGlobalTexture(GateTexId, tex); Shader.SetGlobalFloat(GateHalfId, d.Half);
            Shader.SetGlobalVector(GateId, new Vector4(host.X, host.Z, fca, fsa)); Shader.SetGlobalFloat(GateOnId, 0f);
            root.SetActive(false);                                               // Update switches it on and clears the city out of its area
            Debug.Log($"[Alatau] Gate District (QTwin): {tris} triangles in {lists.Length} tiles, {nt} trees");
        }
    }
}
