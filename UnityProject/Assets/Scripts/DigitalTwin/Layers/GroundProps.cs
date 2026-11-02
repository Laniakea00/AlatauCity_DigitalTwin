using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>What stands on the ground of the redrawn map: benches and playground equipment (swings, a slide tower, a climbing frame,
    /// spring riders, a sandbox), all from Resources/Map/map_walks.json (tools/map/export/ground.py, CONTRACT §8): the benches of the
    /// parks' walks and of the yards' rest squares, and a set on every playground the data lays out — in the parks, in the yards and
    /// school plots, and on the playground lots — fitted to its rubber (one set per 26 m of its long side, scaled to its size). Drawn with
    /// GPU instancing in the film look, within about 2 km of the camera, in the scenario year their place is built.
    /// Without map_walks.json nothing is made.</summary>
    public class GroundProps : MonoBehaviour
    {
        const float Tile = 500f, Range = 2000f;
        const int Kinds = 6;                                          // 0 bench, 1 swings, 2 slide tower, 3 climbing frame, 4 spring rider, 5 sandbox
        [System.Serializable] class WalkJ { public int[] y; public float w; public int k; public float[] p; }
        [System.Serializable] class BenchJ { public int[] y; public int k; public float[] b; }
        [System.Serializable] class PlayJ { public int[] y; public int k; public float a; public float[] p; }
        [System.Serializable] class WalksJ { public int v; public WalkJ[] walks; public BenchJ[] benches; public PlayJ[] play; }

        struct Item { public int kind; public Matrix4x4 m; public int[] y; }
        class TileData
        {
            public readonly List<Item> items = new List<Item>(); public int sorted = -1;
            public Matrix4x4[][] m = new Matrix4x4[Kinds][]; public int[][] yr = new int[Kinds][]; public Bounds b;
        }
        readonly Dictionary<long, TileData> tiles = new Dictionary<long, TileData>();
        readonly Mesh[] meshes = new Mesh[Kinds]; Material mat; bool ready;
        readonly Matrix4x4[] batch = new Matrix4x4[1023];
        readonly Plane[] planes = new Plane[6];
        readonly int[] nBench = new int[3], nSets = new int[3]; int scen = -1;

        static long Key(int x, int z) => ((long)(x + 100000) << 32) | (uint)(z + 100000);
        static int T(float v) => Mathf.FloorToInt(v / Tile);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (Resources.Load<TextAsset>("Map/map_walks") == null) return;
            new GameObject("Ground props (map data)").AddComponent<GroundProps>();
        }

        void Start()
        {
            var sh = Shader.Find("AlatauCity/GroundProps");
            if (sh == null) { Debug.LogWarning("[Alatau] ground props: shader AlatauCity/GroundProps missing"); enabled = false; return; }
            mat = new Material(sh) { name = "Ground props", enableInstancing = true };
            meshes[0] = Bench(); meshes[1] = Swings(); meshes[2] = Slide(); meshes[3] = Climber(); meshes[4] = Rider(); meshes[5] = Sandbox();
            var ta = Resources.Load<TextAsset>("Map/map_walks");
            if (ta != null)
            {
                WalksJ j = null; try { j = JsonUtility.FromJson<WalksJ>(ta.text); } catch (System.Exception ex) { Debug.LogWarning("[Alatau] map_walks.json unreadable: " + ex.Message); }
                Resources.UnloadAsset(ta);
                if (j?.benches != null)
                    foreach (var b in j.benches)
                        for (int i = 0; b.b != null && i + 2 < b.b.Length; i += 3) { Add(0, b.b[i], b.b[i + 1], 90f - b.b[i + 2], b.y); nBench[Mathf.Clamp(b.k, 0, 2)]++; }
                if (j?.play != null)
                    foreach (var p in j.play)
                    {
                        var r = MapPolys.Ring(p.p); if (r == null) continue;
                        Vector2 c = Vector2.zero; foreach (var v in r) c += v; c /= r.Length;
                        float a = p.a * Mathf.Deg2Rad; Vector2 ax = new Vector2(Mathf.Cos(a), Mathf.Sin(a)), ay = new Vector2(-ax.y, ax.x);
                        float lo = float.MaxValue, hi = float.MinValue, wlo = float.MaxValue, whi = float.MinValue;
                        foreach (var v in r) { float t = Vector2.Dot(v - c, ax), u = Vector2.Dot(v - c, ay); lo = Mathf.Min(lo, t); hi = Mathf.Max(hi, t); wlo = Mathf.Min(wlo, u); whi = Mathf.Max(whi, u); }
                        int sets = Mathf.Clamp(Mathf.FloorToInt((hi - lo) / 26f), 1, 3);
                        float sl = Mathf.Clamp((hi - lo) / sets / 26f, 0.45f, 1f), sw = Mathf.Clamp((whi - wlo) / 18f, 0.45f, 1f);   // the set fits the rubber
                        for (int s = 0; s < sets; s++)
                        {
                            var sc = c + ax * (lo + (hi - lo) * (s + 0.5f) / sets) + ay * ((wlo + whi) * 0.5f);
                            Set(sc.x, sc.y, -p.a, p.y, sl, sw); nSets[Mathf.Clamp(p.k, 0, 2)]++;
                        }
                    }
            }
            ready = true;
        }

        // ---------------- items
        void Add(int kind, float x, float z, float yawDeg, int[] y)
        {
            long k = Key(T(x), T(z));
            if (!tiles.TryGetValue(k, out var td)) tiles[k] = td = new TileData();
            var m = Matrix4x4.TRS(new Vector3(x, CityGround.HeightAt(x, z), z), Quaternion.Euler(0f, yawDeg, 0f), Vector3.one);
            td.items.Add(new Item { kind = kind, m = m, y = y }); td.sorted = -1;
        }
        /// <summary>A playground set round (x, z), its long side turned yaw degrees (Unity yaw: local +x goes to (cos, -sin)); the layout of
        /// a 26 × 18 m playground squeezed by sl along and sw across to the rubber it stands on (the pieces keep their size).</summary>
        void Set(float x, float z, float yawDeg, int[] y, float sl, float sw)
        {
            float a = -yawDeg * Mathf.Deg2Rad; Vector2 ax = new Vector2(Mathf.Cos(a), Mathf.Sin(a)), az = new Vector2(-ax.y, ax.x);
            void P(int kind, float lx, float lz, float turn) { var w = new Vector2(x, z) + ax * (lx * sl) + az * (lz * sw); Add(kind, w.x, w.y, yawDeg + turn, y); }
            P(1, -7f, 3f, 0f); P(3, -6f, -4f, 0f); P(2, 1.5f, -4f, 0f); P(4, 9f, -5f, 30f); P(4, 9f, -2f, -20f); P(5, 5f, 2f, 0f);
            P(0, -1f, 7.5f, 180f); P(0, 3f, 7.5f, 180f);
        }

        // the year an item appears in the current scenario (the data's years per scenario)
        static int YearOf(Item it, int sc) => it.y != null ? MapPolys.Year(it.y, sc) : 0;
        void Sort(TileData td, int sc)
        {
            var lm = new List<Matrix4x4>(); var ly = new List<int>(); var idx = new List<int>();
            Vector3 lo = Vector3.one * float.MaxValue, hi = Vector3.one * float.MinValue;
            for (int k = 0; k < Kinds; k++)
            {
                idx.Clear();
                for (int i = 0; i < td.items.Count; i++) if (td.items[i].kind == k) idx.Add(i);
                idx.Sort((a, b) => YearOf(td.items[a], sc).CompareTo(YearOf(td.items[b], sc)));
                lm.Clear(); ly.Clear();
                foreach (int i in idx) { var m = td.items[i].m; lm.Add(m); ly.Add(YearOf(td.items[i], sc)); Vector3 p = m.GetColumn(3); lo = Vector3.Min(lo, p); hi = Vector3.Max(hi, p); }
                td.m[k] = lm.ToArray(); td.yr[k] = ly.ToArray();
            }
            td.b = new Bounds((lo + hi) * 0.5f, hi - lo + new Vector3(12f, 12f, 12f)); td.sorted = sc;
        }

        void LateUpdate()
        {
            if (!ready) return;
            if (!logged)
            {
                logged = true;
                Debug.Log($"[Alatau] ground props: {nBench[0]} benches of the parks, {nBench[1]} of the yards; playground sets: {nSets[0]} in the parks, "
                    + $"{nSets[1]} in the yards and school plots, {nSets[2]} on the playground lots (map_walks.json)");
            }
            if (!FilmLook.Active) return;
            var cam = Camera.main; if (cam == null) return;
            int sc = (int)TwinState.Scenario, year = TwinState.Year;
            if (sc != scen) { scen = sc; foreach (var td in tiles.Values) td.sorted = -1; }
            Vector3 cp = cam.transform.position; float gy = CityGround.HeightAt(cp.x, cp.z);
            if (cp.y - gy > 1500f) return;                                       // too high: a bench is below a pixel
            GeometryUtility.CalculateFrustumPlanes(cam, planes);
            for (int tz = T(cp.z - Range); tz <= T(cp.z + Range); tz++)
                for (int tx = T(cp.x - Range); tx <= T(cp.x + Range); tx++)
                {
                    if (!tiles.TryGetValue(Key(tx, tz), out var td) || td.items.Count == 0) continue;
                    if (td.sorted != sc) Sort(td, sc);
                    if (!GeometryUtility.TestPlanesAABB(planes, td.b)) continue;
                    bool shadows = (td.b.center - cp).sqrMagnitude < 900f * 900f;
                    for (int kd = 0; kd < Kinds; kd++)
                    {
                        var ys = td.yr[kd]; if (ys == null || ys.Length == 0) continue;
                        int lo = 0, hi = ys.Length;                                     // items built by this year (sorted by year)
                        while (lo < hi) { int mid = (lo + hi) >> 1; if (ys[mid] <= year) lo = mid + 1; else hi = mid; }
                        for (int s = 0; s < lo; s += 1023)
                        {
                            int n = Mathf.Min(1023, lo - s);
                            System.Array.Copy(td.m[kd], s, batch, 0, n);
                            Graphics.DrawMeshInstanced(meshes[kd], 0, mat, batch, n, null, shadows ? UnityEngine.Rendering.ShadowCastingMode.On : UnityEngine.Rendering.ShadowCastingMode.Off, true, 0, null);
                        }
                    }
                }
        }
        bool logged;

        // ---------------- the models: plain boxes with vertex colours (local +z = the way a bench faces, +x = a set's long side)
        static readonly List<Vector3> V = new List<Vector3>(); static readonly List<Color> Cl = new List<Color>(); static readonly List<int> Tr = new List<int>();
        static void Box(Vector3 c, Vector3 size, Color col, float rotX = 0f, float rotY = 0f, float rotZ = 0f)
        {
            var q = Quaternion.Euler(rotX, rotY, rotZ); var h = size * 0.5f; int b = V.Count;
            for (int i = 0; i < 8; i++) { V.Add(c + q * new Vector3((i & 1) == 0 ? -h.x : h.x, (i & 2) == 0 ? -h.y : h.y, (i & 4) == 0 ? -h.z : h.z)); Cl.Add(col); }
            int[] f = { 0, 2, 3, 1, 4, 5, 7, 6, 0, 1, 5, 4, 2, 6, 7, 3, 0, 4, 6, 2, 1, 3, 7, 5 };
            for (int i = 0; i < 24; i += 4) { Tr.Add(b + f[i]); Tr.Add(b + f[i + 1]); Tr.Add(b + f[i + 2]); Tr.Add(b + f[i]); Tr.Add(b + f[i + 2]); Tr.Add(b + f[i + 3]); }
        }
        // a bar from a to b of thickness t
        static void Bar(Vector3 a, Vector3 b, float t, Color col)
        {
            var d = b - a; float len = d.magnitude; if (len < 1e-4f) return;
            var rot = Quaternion.FromToRotation(Vector3.up, d / len);
            var e = rot.eulerAngles; Box((a + b) * 0.5f, new Vector3(t, len, t), col, e.x, e.y, e.z);
        }
        static Mesh Done(string name)
        {
            // flat-shaded faces: split every triangle so the normals are the faces' own
            var v = new List<Vector3>(); var c = new List<Color>(); var t = new List<int>();
            for (int i = 0; i < Tr.Count; i++) { v.Add(V[Tr[i]]); c.Add(Cl[Tr[i]]); t.Add(i); }
            var m = new Mesh { name = name }; m.SetVertices(v); m.SetColors(c); m.SetTriangles(t, 0); m.RecalculateNormals(); m.RecalculateBounds(); m.UploadMeshData(true);
            V.Clear(); Cl.Clear(); Tr.Clear(); return m;
        }
        static readonly Color Wood = new Color(0.50f, 0.34f, 0.20f), Steel = new Color(0.20f, 0.21f, 0.22f), Red = new Color(0.78f, 0.20f, 0.16f),
            Yellow = new Color(0.92f, 0.72f, 0.16f), Blue = new Color(0.16f, 0.38f, 0.70f), Green = new Color(0.22f, 0.56f, 0.28f), Sand = new Color(0.84f, 0.76f, 0.58f);

        static Mesh Bench()
        {
            for (int i = 0; i < 4; i++) Box(new Vector3(0f, 0.45f, -0.16f + i * 0.11f), new Vector3(1.8f, 0.04f, 0.09f), Wood);           // seat slats
            for (int i = 0; i < 3; i++) Box(new Vector3(0f, 0.62f + i * 0.13f, -0.25f), new Vector3(1.8f, 0.09f, 0.035f), Wood, -12f);    // back slats
            foreach (float x in new[] { -0.75f, 0.75f }) { Box(new Vector3(x, 0.22f, 0f), new Vector3(0.06f, 0.44f, 0.42f), Steel); Box(new Vector3(x, 0.66f, -0.26f), new Vector3(0.05f, 0.46f, 0.05f), Steel, -12f); }
            return Done("Park bench");
        }
        static Mesh Swings()
        {
            foreach (float x in new[] { -1.9f, 1.9f }) { Bar(new Vector3(x, 0f, -0.9f), new Vector3(x, 2.3f, 0f), 0.09f, Red); Bar(new Vector3(x, 0f, 0.9f), new Vector3(x, 2.3f, 0f), 0.09f, Red); }
            Bar(new Vector3(-2.0f, 2.3f, 0f), new Vector3(2.0f, 2.3f, 0f), 0.1f, Blue);
            foreach (float x in new[] { -0.8f, 0.8f })
            {
                Bar(new Vector3(x - 0.22f, 2.3f, 0f), new Vector3(x - 0.22f, 0.48f, 0f), 0.025f, Steel); Bar(new Vector3(x + 0.22f, 2.3f, 0f), new Vector3(x + 0.22f, 0.48f, 0f), 0.025f, Steel);
                Box(new Vector3(x, 0.46f, 0f), new Vector3(0.5f, 0.05f, 0.22f), Steel);
            }
            return Done("Playground swings");
        }
        static Mesh Slide()
        {
            foreach (var p in new[] { new Vector2(-0.6f, -0.6f), new Vector2(0.6f, -0.6f), new Vector2(-0.6f, 0.6f), new Vector2(0.6f, 0.6f) })
                Box(new Vector3(p.x, 1.25f, p.y), new Vector3(0.1f, 2.5f, 0.1f), Blue);
            Box(new Vector3(0f, 1.2f, 0f), new Vector3(1.3f, 0.08f, 1.3f), Wood);                                               // platform
            Box(new Vector3(0f, 2.55f, 0f), new Vector3(1.6f, 0.1f, 1.6f), Red); Box(new Vector3(0f, 2.75f, 0f), new Vector3(1.0f, 0.3f, 1.0f), Red);   // roof
            Box(new Vector3(0f, 1.55f, 0.65f), new Vector3(1.3f, 0.6f, 0.04f), Yellow); Box(new Vector3(0f, 1.55f, -0.65f), new Vector3(1.3f, 0.6f, 0.04f), Yellow);  // panels
            Bar(new Vector3(-0.95f, 0f, -0.25f), new Vector3(-0.65f, 1.2f, -0.25f), 0.06f, Steel); Bar(new Vector3(-0.95f, 0f, 0.25f), new Vector3(-0.65f, 1.2f, 0.25f), 0.06f, Steel);
            for (int i = 1; i < 5; i++) { float y = i * 0.24f, x = -0.95f + 0.3f * y / 1.2f; Box(new Vector3(x, y, 0f), new Vector3(0.05f, 0.04f, 0.5f), Steel); }   // ladder
            Box(new Vector3(1.9f, 0.72f, 0f), new Vector3(2.9f, 0.06f, 0.6f), Yellow, 0f, 0f, -21f);                             // slide
            Box(new Vector3(1.9f, 0.82f, 0.31f), new Vector3(2.9f, 0.2f, 0.04f), Yellow, 0f, 0f, -21f); Box(new Vector3(1.9f, 0.82f, -0.31f), new Vector3(2.9f, 0.2f, 0.04f), Yellow, 0f, 0f, -21f);
            return Done("Playground slide tower");
        }
        static Mesh Climber()
        {
            float[] xs = { -1.5f, 0f, 1.5f }, zs = { -1f, 1f };
            foreach (float x in xs) foreach (float z in zs) Bar(new Vector3(x, 0f, z), new Vector3(x, 2f, z), 0.07f, Green);
            foreach (float y in new[] { 0.7f, 1.35f, 2f })
            {
                foreach (float z in zs) Bar(new Vector3(-1.5f, y, z), new Vector3(1.5f, y, z), 0.05f, Yellow);
                foreach (float x in xs) Bar(new Vector3(x, y, -1f), new Vector3(x, y, 1f), 0.05f, Yellow);
            }
            return Done("Playground climbing frame");
        }
        static Mesh Rider()
        {
            Bar(new Vector3(0f, 0f, 0f), new Vector3(0f, 0.35f, 0f), 0.08f, Steel);
            Box(new Vector3(0f, 0.5f, 0f), new Vector3(0.7f, 0.3f, 0.25f), Red); Box(new Vector3(0.3f, 0.75f, 0f), new Vector3(0.22f, 0.3f, 0.2f), Red);
            Box(new Vector3(0.05f, 0.7f, 0f), new Vector3(0.08f, 0.15f, 0.35f), Steel);
            return Done("Playground spring rider");
        }
        static Mesh Sandbox()
        {
            Box(new Vector3(0f, 0.04f, 0f), new Vector3(2.8f, 0.08f, 2.8f), Sand);
            Box(new Vector3(0f, 0.15f, 1.45f), new Vector3(3.0f, 0.3f, 0.12f), Wood); Box(new Vector3(0f, 0.15f, -1.45f), new Vector3(3.0f, 0.3f, 0.12f), Wood);
            Box(new Vector3(1.45f, 0.15f, 0f), new Vector3(0.12f, 0.3f, 2.8f), Wood); Box(new Vector3(-1.45f, 0.15f, 0f), new Vector3(0.12f, 0.3f, 2.8f), Wood);
            return Done("Playground sandbox");
        }
    }
}
