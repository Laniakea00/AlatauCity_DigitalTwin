using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Trees of the film look. Nothing is stored: trees are placed by rule, cell by cell (320 m), around what the camera
    /// looks at, and drawn in instanced batches.
    ///   along streets and main roads: a row on each pavement, about every 13 m (poplars and round crowns);
    ///   in the parks of the plan (green on the base map): dense groves; in built-up quarters: a few in the yards; on open land: rare.
    /// A tree never stands in a building (a ray from above must reach the ground, with room for the crown) or on a road, and it appears
    /// in the year its place is developed (the base map's development year), like the ground under it. The placement is a model.</summary>
    public class FilmTrees : MonoBehaviour
    {
        const float Cell = 320f, Spacing = 13f;
        const int Species = 4;                                    // 0 round crown, 1 poplar, 2 spruce, 3 a metre of hedge (stretched along a plot edge)
        /// <summary>Set by the capture tool: place every tree in range at once instead of a few cells per frame.</summary>
        public static bool Sync;

        class CellData { public Matrix4x4[][] m = new Matrix4x4[Species][]; public MaterialPropertyBlock[] props = new MaterialPropertyBlock[Species]; public Bounds bounds; public int count; }
        struct Seg { public Vector2 a, b; public float half; }

        readonly Dictionary<long, CellData> cells = new Dictionary<long, CellData>();
        readonly Dictionary<long, List<Vector3>> street = new Dictionary<long, List<Vector3>>();     // x, z, species
        readonly Dictionary<long, List<Seg>> corridors = new Dictionary<long, List<Seg>>();
        readonly Dictionary<long, List<Vector4>> hedges = new Dictionary<long, List<Vector4>>();     // x, z, direction in degrees, length
        readonly Dictionary<Collider, bool> isGround = new Dictionary<Collider, bool>();
        readonly List<long> wanted = new List<long>();
        Color32[] plan; byte[] dev; int mw, mh; float ua, ub, va, vb;
        Mesh[] hi = new Mesh[Species], lo = new Mesh[Species]; Material mat; bool ready, failed;
        readonly Plane[] planes = new Plane[6];
        readonly List<Matrix4x4>[] tmpM = { new List<Matrix4x4>(), new List<Matrix4x4>(), new List<Matrix4x4>(), new List<Matrix4x4>() };
        readonly List<float>[] tmpY = { new List<float>(), new List<float>(), new List<float>(), new List<float>() };
        readonly List<Vector4>[] tmpT = { new List<Vector4>(), new List<Vector4>(), new List<Vector4>(), new List<Vector4>() };

        static long Key(int cx, int cz) => ((long)(cx + 100000) << 32) | (uint)(cz + 100000);
        static int C(float v) => Mathf.FloorToInt(v / Cell);

        /// <summary>The trees of the film look (null until they are made): other layers draw their own plantings with them.</summary>
        public static FilmTrees Instance;
        void Awake() { Instance = this; }

        struct Clearing { public Vector2 a, b; public float r; }
        static readonly List<Clearing> clearings = new List<Clearing>();
        /// <summary>Keeps a strip free of trees (a capsule a–b of radius r): a model put on open land (the presentation's substation,
        /// its line and road). Cells already placed there are placed again.</summary>
        public static void KeepClear(Vector2 a, Vector2 b, float r)
        {
            clearings.Add(new Clearing { a = a, b = b, r = r });
            var inst = Instance; if (inst == null) return;
            for (int cz = C(Mathf.Min(a.y, b.y) - r); cz <= C(Mathf.Max(a.y, b.y) + r); cz++)
                for (int cx = C(Mathf.Min(a.x, b.x) - r); cx <= C(Mathf.Max(a.x, b.x) + r); cx++) inst.cells.Remove(Key(cx, cz));
        }
        static bool Cleared(float x, float z) { var p = new Vector2(x, z); foreach (var c in clearings) if (DistToSeg(p, c.a, c.b) < c.r) return true; return false; }
        /// <summary>Draws a batch of up to 1023 trees of species s (0 round crown, 1 poplar, 2 spruce) with their per-tree props
        /// (_TreeYear, _TreeTint); false while the meshes are not made yet.</summary>
        public bool DrawBatch(int s, Matrix4x4[] m, int count, MaterialPropertyBlock props, bool near, bool shadows)
        {
            // the trees of other layers (the Gate District round Iconic) stand in every look: make the meshes even if the film is off
            if (!ready && !failed && TwinData.Ready) Init();
            if (!ready || failed || hi[s] == null) return false;
            Graphics.DrawMeshInstanced(near ? hi[s] : lo[s], 0, mat, m, count, props,
                shadows ? UnityEngine.Rendering.ShadowCastingMode.On : UnityEngine.Rendering.ShadowCastingMode.Off, true, 0, null);
            return true;
        }

        /// <summary>Called every frame by FilmLook while the film look is on.</summary>
        public void Draw(Camera cam, Vector3 focus, float distance)
        {
            if (failed || distance > 6500f) return;
            if (!ready) { if (!TwinData.Ready) return; Init(); if (failed) return; }
            float R = Mathf.Clamp(distance * 2.6f, 1500f, 4600f);
            GeometryUtility.CalculateFrustumPlanes(cam, planes);
            Vector3 cp = cam.transform.position;
            int c0x = C(focus.x - R), c1x = C(focus.x + R), c0z = C(focus.z - R), c1z = C(focus.z + R);
            wanted.Clear();
            for (int cz = c0z; cz <= c1z; cz++) for (int cx = c0x; cx <= c1x; cx++)
            {
                long k = Key(cx, cz);
                if (!cells.TryGetValue(k, out var cd)) { wanted.Add(k); continue; }
                if (cd.count == 0 || !GeometryUtility.TestPlanesAABB(planes, cd.bounds)) continue;
                float d = (cd.bounds.center - cp).magnitude; bool near = d < 1500f;
                for (int s = 0; s < Species; s++)
                    if (cd.m[s] != null && cd.m[s].Length > 0)
                        Graphics.DrawMeshInstanced(near ? hi[s] : lo[s], 0, mat, cd.m[s], cd.m[s].Length, cd.props[s],
                            d < 2600f ? UnityEngine.Rendering.ShadowCastingMode.On : UnityEngine.Rendering.ShadowCastingMode.Off, true, 0, null);
            }
            if (wanted.Count == 0) { Sync = false; return; }
            // place the missing cells, the nearest to the focus first; a few milliseconds per frame unless a capture asks for all
            wanted.Sort((a, b) => Dist2(a, focus).CompareTo(Dist2(b, focus)));
            float t0 = Time.realtimeSinceStartup;
            foreach (long k in wanted) { Generate(k); if (!Sync && Time.realtimeSinceStartup - t0 > 0.004f) break; }
        }

        static float Dist2(long k, Vector3 f)
        {
            float x = ((int)(k >> 32) - 100000 + 0.5f) * Cell - f.x, z = ((int)(uint)(k & 0xFFFFFFFF) - 100000 + 0.5f) * Cell - f.z; return x * x + z * z;
        }

        void Init()
        {
            ready = true;
            var sh = Shader.Find("AlatauCity/Tree"); var planTex = Resources.Load<Texture2D>("Map/map_plan"); var devTex = Resources.Load<Texture2D>("Map/map_dev");
            var terrain = GameObject.Find("Terrain (master plan map)");
            if (sh == null || planTex == null || devTex == null || terrain == null) { failed = true; Debug.LogWarning("[Alatau] film trees: shader, base map or terrain missing"); return; }
            mat = new Material(sh) { name = "Film trees", enableInstancing = true };
            // the base map at about 20 m per pixel, readable: land use from its colour, and the year each place is developed
            mw = 2048; mh = Mathf.RoundToInt(2048f * planTex.height / planTex.width);
            plan = Read(planTex, mw, mh).GetPixels32(); var d32 = Read(devTex, mw, mh).GetPixels32(); dev = new byte[d32.Length]; for (int i = 0; i < dev.Length; i++) dev[i] = d32[i].r;
            // how the map lies on the ground: the terrain mesh carries map coordinates in its uv
            var mesh = terrain.GetComponent<MeshFilter>().sharedMesh; var vs = mesh.vertices; var uvs = mesh.uv; int last = vs.Length - 1;
            ua = (uvs[last].x - uvs[0].x) / (vs[last].x - vs[0].x); ub = uvs[0].x - ua * vs[0].x; va = (uvs[last].y - uvs[0].y) / (vs[last].z - vs[0].z); vb = uvs[0].y - va * vs[0].z;
            // the light-rail line, rivers and railways are drawn as ribbons without colliders: give them one on the "ignore raycast" layer,
            // so that a tree is never placed on them while clicks on the map still pass through
            foreach (var mf in FindObjectsByType<MeshFilter>(FindObjectsSortMode.None))
                if (mf.sharedMesh != null && (mf.name == "LRT line" || mf.name == "Rivers" || mf.name.StartsWith("Railways")) && mf.GetComponent<Collider>() == null)
                {
                    var go = new GameObject(mf.name + " (no trees here)") { layer = 2 }; go.transform.SetParent(mf.transform, false);
                    go.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
                }
            Physics.SyncTransforms();
            // street trees and road corridors, sorted into cells
            var rng = new System.Random(2050); int rows = 0;
            for (int ei = 0; ei < TwinData.Roads.Length; ei++)
            {
                var e = TwinData.Roads[ei];
                if (e.Geom == null || e.Geom.Length < 2) continue;
                FilmRoads.Dims(e.Cls, out float half, out float walk, out _, out _);
                bool planted = walk > 0f && !FilmRoads.Dropped(ei); float next = Spacing * (float)rng.NextDouble(), off = half + walk * 0.55f;
                for (int i = 1; i < e.Geom.Length; i++)
                {
                    Vector2 a = e.Geom[i - 1], b = e.Geom[i]; float len = (b - a).magnitude; if (len < 0.01f) continue;
                    Vector2 d = (b - a) / len, left = new Vector2(-d.y, d.x);
                    for (float t = 0; t < len; t += 60f)
                    {
                        Vector2 p = a + d * t, q = a + d * Mathf.Min(t + 60f, len); var sg = new Seg { a = p, b = q, half = half + walk + 1.2f };
                        for (int cz = C(Mathf.Min(p.y, q.y) - sg.half); cz <= C(Mathf.Max(p.y, q.y) + sg.half); cz++) for (int cx = C(Mathf.Min(p.x, q.x) - sg.half); cx <= C(Mathf.Max(p.x, q.x) + sg.half); cx++)
                        { long k = Key(cx, cz); if (!corridors.TryGetValue(k, out var l)) corridors[k] = l = new List<Seg>(); l.Add(sg); }
                    }
                    if (!planted) continue;
                    for (; next < len; next += Spacing * (0.85f + 0.3f * (float)rng.NextDouble()))
                        for (int side = -1; side <= 1; side += 2)
                        {
                            Vector2 p = a + d * next + left * (off * side); long k = Key(C(p.x), C(p.y));
                            if (!street.TryGetValue(k, out var l)) street[k] = l = new List<Vector3>();
                            l.Add(new Vector3(p.x, p.y, e.Cls == TwinData.RoadClass.Main ? 1 : (rows & 3) == 0 ? 1 : 0));
                        }
                    next -= len; rows++;
                }
            }
            // the clean road geometry (rebuilt motorways, interchange ramps) keeps trees off its ribbons too
            foreach (var (P, half) in FilmRoads.CleanLines())
                for (int i = 1; i < P.Count; i++)
                {
                    var sg = new Seg { a = P[i - 1], b = P[i], half = half + 2f };
                    for (int cz = C(Mathf.Min(sg.a.y, sg.b.y) - sg.half); cz <= C(Mathf.Max(sg.a.y, sg.b.y) + sg.half); cz++) for (int cx = C(Mathf.Min(sg.a.x, sg.b.x) - sg.half); cx <= C(Mathf.Max(sg.a.x, sg.b.x) + sg.half); cx++)
                    { long k = Key(cx, cz); if (!corridors.TryGetValue(k, out var l)) corridors[k] = l = new List<Seg>(); l.Add(sg); }
                }
            // house plots: every generated house gets a hedge round a plot a little larger than itself, with a gap for the gate,
            // and a tree or two in the garden. The house rectangles are read from the building meshes (the lowest corners of each house).
            int plots = 0; var uv2 = new List<Vector2>(); var corner = new Dictionary<int, List<Vector3>>();
            foreach (var ch in FindObjectsByType<BuildingChunk>(FindObjectsSortMode.None))
            {
                if (!ch.name.Contains("houses")) continue;
                var bm = ch.GetComponent<MeshFilter>().sharedMesh; if (bm == null || !bm.isReadable) continue;
                var bv = bm.vertices; uv2.Clear(); bm.GetUVs(1, uv2); var buv = bm.uv; corner.Clear();
                var low = new Dictionary<int, float>();
                for (int i = 0; i < bv.Length; i++) { if (buv[i].y < -0.5f) continue; int b = Mathf.RoundToInt(uv2[i].y) - 1; if (!low.TryGetValue(b, out float y) || bv[i].y < y) low[b] = bv[i].y; }
                for (int i = 0; i < bv.Length; i++)
                {
                    if (buv[i].y < -0.5f) continue; int b = Mathf.RoundToInt(uv2[i].y) - 1; if (bv[i].y > low[b] + 0.15f) continue;
                    if (!corner.TryGetValue(b, out var l)) corner[b] = l = new List<Vector3>();
                    bool seen = false; foreach (var q in l) if ((q - bv[i]).sqrMagnitude < 0.01f) { seen = true; break; }
                    if (!seen) l.Add(bv[i]);
                }
                foreach (var kv in corner)
                {
                    var c4 = kv.Value; if (c4.Count != 4) continue;
                    Vector3 cen = (c4[0] + c4[1] + c4[2] + c4[3]) * 0.25f, U = Vector3.right; float best = 0;
                    for (int i = 1; i < 4; i++) { var d = c4[i] - c4[0]; d.y = 0; float l = d.magnitude; if (l > best && l < 0.9f * MaxDist(c4)) { best = l; U = d / l; } }
                    var Wd = new Vector3(-U.z, 0, U.x); float hu = 0, hw = 0;
                    foreach (var q in c4) { hu = Mathf.Max(hu, Mathf.Abs(Vector3.Dot(q - cen, U))); hw = Mathf.Max(hw, Mathf.Abs(Vector3.Dot(q - cen, Wd))); }
                    float pu = hu + 5.5f, pw = hw + 7.5f, yaw = Mathf.Atan2(U.z, U.x) * Mathf.Rad2Deg; int h = kv.Key * 7919; float gate = (h & 1) == 0 ? 1f : -1f;
                    void Hedge(Vector3 a, Vector3 b)
                    {
                        Vector3 m = (a + b) * 0.5f; long k = Key(C(m.x), C(m.z)); if (!hedges.TryGetValue(k, out var hl)) hedges[k] = hl = new List<Vector4>();
                        hl.Add(new Vector4(m.x, m.z, Mathf.Atan2(b.z - a.z, b.x - a.x) * Mathf.Rad2Deg, (b - a).magnitude));
                    }
                    Hedge(cen - U * pu - Wd * pw * gate, cen + U * pu - Wd * pw * gate);                               // back
                    Hedge(cen - U * pu - Wd * pw, cen - U * pu + Wd * pw); Hedge(cen + U * pu - Wd * pw, cen + U * pu + Wd * pw);   // sides
                    Hedge(cen - U * pu + Wd * pw * gate, cen - U * 1.8f + Wd * pw * gate); Hedge(cen + U * 1.8f + Wd * pw * gate, cen + U * pu + Wd * pw * gate);   // front, with the gate
                    for (int t = 0; t < 2; t++)
                    {
                        float fu = ((h >> (3 + t * 5) & 31) / 31f - 0.5f) * 1.6f * pu, fw = (hw + 2.2f + ((h >> (9 + t * 5) & 15) / 15f) * 4f) * (t == 0 ? -gate : gate);
                        Vector3 g = cen + U * fu + Wd * fw; long k = Key(C(g.x), C(g.z)); if (!street.TryGetValue(k, out var gl)) street[k] = gl = new List<Vector3>();
                        gl.Add(new Vector3(g.x, g.z, (h >> 20 & 7) == 0 ? 2 : 0));
                    }
                    plots++;
                }
            }
            // villages that stand today (the existing low houses): orchards and shade trees round every house, as in any aul of the
            // Almaty region, so a village reads as green gardens and not as boxes scattered over the steppe
            int village = 0; var dbv = CityDatabase.Instance;
            if (dbv != null)
                foreach (var b in dbv.Buildings)
                {
                    if (b == null || b.Source != "existing_osm" || b.HeightM > 10f) continue;
                    int hb = (int)(unchecked((uint)b.Bid * 2654435761u) >> 8); int nt = 2 + (hb & 1) + ((hb >> 1) & 1);
                    for (int t = 0; t < nt; t++)
                    {
                        float a = ((hb >> (2 + t * 4)) & 15) / 16f * Mathf.PI * 2f, r = 9f + ((hb >> (5 + t * 3)) & 7);
                        float gx = b.X + Mathf.Cos(a) * r, gz = b.Z + Mathf.Sin(a) * r; long k = Key(C(gx), C(gz));
                        if (!street.TryGetValue(k, out var gl)) street[k] = gl = new List<Vector3>();
                        gl.Add(new Vector3(gx, gz, ((hb >> (12 + t)) & 7) == 0 ? 1 : 0)); village++;
                    }
                }
            Debug.Log($"[Alatau] film trees: {village} trees in the gardens of existing villages");
            hi[3] = lo[3] = HedgeMesh();
            Debug.Log($"[Alatau] film trees: {plots} house plots");
            hi[0] = Blob("Tree round", 16, 11, new Vector3(3.3f, 3.5f, 3.3f), 3.2f, 0.28f, 0.30f, new Color(0.17f, 0.27f, 0.13f), new Color(0.31f, 0.42f, 0.19f), 11);
            hi[1] = Blob("Tree poplar", 12, 12, new Vector3(1.55f, 6.2f, 1.55f), 2.0f, 0.26f, 0.22f, new Color(0.15f, 0.25f, 0.13f), new Color(0.28f, 0.40f, 0.19f), 23);
            hi[2] = Cones("Tree spruce", 12, 2.5f, 10.5f, new Color(0.09f, 0.18f, 0.14f), new Color(0.17f, 0.29f, 0.21f));
            lo[0] = Blob("Tree round far", 8, 5, new Vector3(3.3f, 3.5f, 3.3f), 3.2f, 0f, 0.18f, new Color(0.17f, 0.27f, 0.13f), new Color(0.31f, 0.42f, 0.19f), 11);
            lo[1] = Blob("Tree poplar far", 6, 5, new Vector3(1.55f, 6.2f, 1.55f), 2.0f, 0f, 0.12f, new Color(0.15f, 0.25f, 0.13f), new Color(0.28f, 0.40f, 0.19f), 23);
            lo[2] = Cones("Tree spruce far", 5, 2.5f, 10.5f, new Color(0.09f, 0.18f, 0.14f), new Color(0.17f, 0.29f, 0.21f), 1);
            Debug.Log($"[Alatau] film trees: base map {mw}x{mh}, street rows in {street.Count} cells");
        }

        static Texture2D Read(Texture2D src, int w, int h)
        {
            var rt = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear); Graphics.Blit(src, rt);
            var prev = RenderTexture.active; RenderTexture.active = rt;
            var t = new Texture2D(w, h, TextureFormat.RGBA32, false, true); t.ReadPixels(new Rect(0, 0, w, h), 0, 0); t.Apply(false);
            RenderTexture.active = prev; RenderTexture.ReleaseTemporary(rt); return t;
        }

        /// <summary>Land use at a place, from the colour of the base map: 0 other built-up, 1 park, 2 open land, 3 water; and the development year.</summary>
        int Land(float x, float z, out float year)
        {
            int px = Mathf.Clamp((int)((ua * x + ub) * mw), 0, mw - 1), py = Mathf.Clamp((int)((va * z + vb) * mh), 0, mh - 1); int i = py * mw + px;
            year = dev[i] == 0 ? 0f : 2000f + dev[i];
            Color32 c = plan[i]; float r = c.r / 255f, g = c.g / 255f, b = c.b / 255f, lum = 0.299f * r + 0.587f * g + 0.114f * b, sat = Mathf.Max(r, Mathf.Max(g, b)) - Mathf.Min(r, Mathf.Min(g, b));
            if ((b - r) * 5f - 0.6f > 0.3f && (g - r) * 8f + 0.3f > 0.3f) return 3;
            if (g - Mathf.Max(r, b) > 0.05f) return 1;
            if (lum < 0.46f && sat < 0.12f) return 2;
            return 0;
        }

        void Generate(long key)
        {
            int cx = (int)(key >> 32) - 100000, cz = (int)(uint)(key & 0xFFFFFFFF) - 100000;
            var rng = new System.Random(cx * 73856093 ^ cz * 19349663);
            for (int s = 0; s < Species; s++) { tmpM[s].Clear(); tmpY[s].Clear(); tmpT[s].Clear(); }
            corridors.TryGetValue(key, out var segs);
            float ymin = float.MaxValue, ymax = float.MinValue;
            void Try(float x, float z, int sp, float year, float size)
            {
                if (tmpM[sp].Count >= 1023) return;
                if (Landmarks.LandmarkSystem.OnPlot(x, z)) return;                        // a landmark's plot (airfield, campus…): its own planting
                if (clearings.Count > 0 && Cleared(x, z)) return;
                if (!Physics.Raycast(new Vector3(x, 6000f, z), Vector3.down, out var hit, 9000f, ~0, QueryTriggerInteraction.Ignore)) return;
                if (!isGround.TryGetValue(hit.collider, out bool ground)) isGround[hit.collider] = ground = hit.collider.name.StartsWith("Terrain");
                if (!ground) return;                                                       // a building stands here (in some year)
                if (Physics.CheckSphere(hit.point + Vector3.up * (3.2f * size + 2.5f), 3.2f * size, ~0, QueryTriggerInteraction.Ignore)) return;   // no room for the crown
                float y = CityGround.HeightAt(x, z) - 0.15f; ymin = Mathf.Min(ymin, y); ymax = Mathf.Max(ymax, y);
                tmpM[sp].Add(Matrix4x4.TRS(new Vector3(x, y, z), Quaternion.Euler(0, (float)rng.NextDouble() * 360f, 0), new Vector3(size, size * (0.9f + 0.25f * (float)rng.NextDouble()), size)));
                tmpY[sp].Add(year); float v = 0.86f + 0.26f * (float)rng.NextDouble(), w = (float)rng.NextDouble();
                tmpT[sp].Add(new Vector4(v * (1f + 0.10f * w), v, v * (1f - 0.12f * w), 1f));
            }
            if (street.TryGetValue(key, out var rows))
                foreach (var p in rows) { int land = Land(p.x, p.y, out float yr); if (land != 3) Try(p.x, p.y, (int)p.z, yr, 0.8f + 0.3f * (float)rng.NextDouble()); }
            if (hedges.TryGetValue(key, out var hs))
                foreach (var hd in hs)
                {
                    if (tmpM[3].Count >= 1023) break;
                    if (Land(hd.x, hd.y, out float yr) == 3) continue;
                    if (Landmarks.LandmarkSystem.OnPlot(hd.x, hd.y) || FilmRoads.InInterchange(hd.x, hd.y) || (clearings.Count > 0 && Cleared(hd.x, hd.y))) continue;
                    if (segs != null) { bool onRoad = false; var q = new Vector2(hd.x, hd.y); foreach (var sg in segs) if (DistToSeg(q, sg.a, sg.b) < sg.half - 1f) { onRoad = true; break; } if (onRoad) continue; }
                    if (!Physics.Raycast(new Vector3(hd.x, 6000f, hd.y), Vector3.down, out var hit, 9000f, ~0, QueryTriggerInteraction.Ignore)) continue;
                    if (!isGround.TryGetValue(hit.collider, out bool ground)) isGround[hit.collider] = ground = hit.collider.name.StartsWith("Terrain");
                    if (!ground) continue;
                    float y = CityGround.HeightAt(hd.x, hd.y) - 0.5f; ymin = Mathf.Min(ymin, y); ymax = Mathf.Max(ymax, y);
                    tmpM[3].Add(Matrix4x4.TRS(new Vector3(hd.x, y, hd.y), Quaternion.Euler(0, -hd.z, 0), new Vector3(hd.w, 1.5f + 0.2f * (float)rng.NextDouble(), 0.6f)));
                    tmpY[3].Add(yr); float v = 0.9f + 0.2f * (float)rng.NextDouble(); tmpT[3].Add(new Vector4(v, v, v, 1f));
                }
            const float step = 14f; int n = Mathf.RoundToInt(Cell / step);
            for (int j = 0; j < n; j++) for (int i = 0; i < n; i++)
            {
                float x = (cx + (i + (float)rng.NextDouble()) / n) * Cell, z = (cz + (j + (float)rng.NextDouble()) / n) * Cell, pick = (float)rng.NextDouble(), kind = (float)rng.NextDouble(), size = 0.75f + 0.5f * (float)rng.NextDouble();
                int land = Land(x, z, out float yr);
                // groves in the parks (denser where the noise is high), a few trees in the yards, a rare one in the steppe
                float p = land == 1 ? 0.25f + 0.6f * Mathf.PerlinNoise(x * 0.012f + 31f, z * 0.012f + 7f) : land == 0 ? 0.11f : land == 2 ? 0.004f : 0f;
                if (land != 3 && FilmRoads.InInterchange(x, z)) p = 0.02f;                  // the verge between the ramps: a rare tree
                if (pick > p) continue;
                if (segs != null) { bool onRoad = false; var q = new Vector2(x, z); foreach (var sg in segs) if (DistToSeg(q, sg.a, sg.b) < sg.half) { onRoad = true; break; } if (onRoad) continue; }
                Try(x, z, land == 1 ? (kind < 0.58f ? 0 : kind < 0.82f ? 2 : 1) : (kind < 0.8f ? 0 : 1), yr, size);
            }
            var cd = new CellData();
            for (int s = 0; s < Species; s++)
            {
                cd.m[s] = tmpM[s].ToArray(); cd.count += cd.m[s].Length;
                if (cd.m[s].Length > 0) { cd.props[s] = new MaterialPropertyBlock(); cd.props[s].SetFloatArray("_TreeYear", tmpY[s]); cd.props[s].SetVectorArray("_TreeTint", tmpT[s]); }
            }
            if (cd.count > 0) cd.bounds = new Bounds(new Vector3((cx + 0.5f) * Cell, (ymin + ymax) * 0.5f + 8f, (cz + 0.5f) * Cell), new Vector3(Cell + 12f, ymax - ymin + 30f, Cell + 12f));
            cells[key] = cd;
        }

        static float DistToSeg(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-6f)); return (p - (a + ab * t)).magnitude;
        }

        // ---------------- tree shapes: plain model trees, colours in the vertices
        static Mesh Blob(string name, int seg, int rings, Vector3 r, float trunkH, float trunkR, float jitter, Color low, Color high, int seed)
        {
            var v = new List<Vector3>(); var c = new List<Color>(); var t = new List<int>(); var brown = new Color(0.33f, 0.25f, 0.19f);
            if (trunkR > 0f)
                for (int i = 0; i < 5; i++)
                {
                    float a0 = i / 5f * Mathf.PI * 2f, a1 = (i + 1) / 5f * Mathf.PI * 2f; int b = v.Count;
                    v.Add(new Vector3(Mathf.Cos(a0) * trunkR, 0, Mathf.Sin(a0) * trunkR)); v.Add(new Vector3(Mathf.Cos(a1) * trunkR, 0, Mathf.Sin(a1) * trunkR));
                    v.Add(new Vector3(Mathf.Cos(a1) * trunkR * 0.7f, trunkH + r.y * 0.4f, Mathf.Sin(a1) * trunkR * 0.7f)); v.Add(new Vector3(Mathf.Cos(a0) * trunkR * 0.7f, trunkH + r.y * 0.4f, Mathf.Sin(a0) * trunkR * 0.7f));
                    for (int k = 0; k < 4; k++) c.Add(brown);
                    t.Add(b); t.Add(b + 2); t.Add(b + 1); t.Add(b); t.Add(b + 3); t.Add(b + 2);
                }
            int b0 = v.Count; var rng = new System.Random(seed); float cy = trunkH + r.y * 0.9f;
            // the crown is a cluster of leaf clumps: a dozen soft bumps on the sphere, so the outline is lumpy, not a polygon
            var bumps = new Vector3[12]; for (int q = 0; q < bumps.Length; q++) bumps[q] = new Vector3((float)rng.NextDouble() * 2f - 1f, (float)rng.NextDouble() * 1.6f - 0.6f, (float)rng.NextDouble() * 2f - 1f).normalized;
            for (int j = 0; j <= rings; j++) for (int i = 0; i < seg; i++)
            {
                float th = j / (float)rings * Mathf.PI, ph = i / (float)seg * Mathf.PI * 2f;
                var dir = new Vector3(Mathf.Sin(th) * Mathf.Cos(ph), Mathf.Cos(th), Mathf.Sin(th) * Mathf.Sin(ph)); float lump = 0f;
                foreach (var bq in bumps) lump = Mathf.Max(lump, Mathf.Pow(Mathf.Max(0f, Vector3.Dot(dir, bq)), 6f));
                float k = 1f + jitter * (lump - 0.45f) + jitter * 0.25f * ((float)rng.NextDouble() * 2f - 1f);
                if (j == 0 || j == rings) k = 1f - jitter * 0.3f;
                var p = new Vector3(Mathf.Sin(th) * Mathf.Cos(ph) * r.x * k, Mathf.Cos(th) * r.y * k, Mathf.Sin(th) * Mathf.Sin(ph) * r.z * k);
                v.Add(p + Vector3.up * cy); c.Add(Color.Lerp(low, high, Mathf.Clamp01(p.y / r.y * 0.5f + 0.5f)));
            }
            for (int j = 0; j < rings; j++) for (int i = 0; i < seg; i++)
            {
                int a = b0 + j * seg + i, b = b0 + j * seg + (i + 1) % seg, d = a + seg, e = b + seg;
                t.Add(a); t.Add(b); t.Add(d); t.Add(b); t.Add(e); t.Add(d);
            }
            var m = Finish(name, v, c, t);
            // light the crown as one soft volume: its normals mostly point away from the crown's centre
            var nr = m.normals; var vv = m.vertices; var ctr = new Vector3(0f, cy, 0f);
            for (int q = b0; q < vv.Length; q++)
            {
                var d = vv[q] - ctr; d = new Vector3(d.x / r.x, d.y / r.y, d.z / r.z);
                nr[q] = Vector3.Lerp(nr[q], d.normalized, 0.65f).normalized;
            }
            m.normals = nr; return m;
        }

        /// <summary>The crown shapes of the film trees at a middle level of detail, for models that build their own trees into
        /// one mesh (LandmarkKit.Tree): 0 round crown, 1 poplar, 2 spruce. Made once, readable.</summary>
        public static Mesh SpeciesMesh(int s)
        {
            s = Mathf.Clamp(s, 0, 2);
            if (mid[s] != null) return mid[s];
            mid[s] = s == 0 ? Blob("Tree round mid", 11, 7, new Vector3(3.3f, 3.5f, 3.3f), 3.2f, 0.28f, 0.26f, new Color(0.17f, 0.27f, 0.13f), new Color(0.31f, 0.42f, 0.19f), 11)
                   : s == 1 ? Blob("Tree poplar mid", 8, 8, new Vector3(1.55f, 6.2f, 1.55f), 2.0f, 0.26f, 0.20f, new Color(0.15f, 0.25f, 0.13f), new Color(0.28f, 0.40f, 0.19f), 23)
                   : Cones("Tree spruce mid", 8, 2.5f, 10.5f, new Color(0.09f, 0.18f, 0.14f), new Color(0.17f, 0.29f, 0.21f));
            return mid[s];
        }
        static readonly Mesh[] mid = new Mesh[3];

        static float MaxDist(List<Vector3> c) { float m = 0; for (int i = 1; i < c.Count; i++) { var d = c[i] - c[0]; d.y = 0; m = Mathf.Max(m, d.magnitude); } return m; }

        /// <summary>One metre of clipped hedge along x (0.6 m wide once scaled), darker at the foot.</summary>
        static Mesh HedgeMesh()
        {
            var v = new List<Vector3>(); var c = new List<Color>(); var t = new List<int>(); Color low = new Color(0.12f, 0.21f, 0.11f), high = new Color(0.24f, 0.36f, 0.17f);
            Vector3[] p = { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(0.5f, 0, 0.5f), new Vector3(-0.5f, 0, 0.5f) };
            void Face(Vector3 a, Vector3 b, Vector3 d, Vector3 e) { int k = v.Count; v.Add(a); v.Add(b); v.Add(d); v.Add(e); foreach (var q in new[] { a, b, d, e }) c.Add(Color.Lerp(low, high, q.y)); t.Add(k); t.Add(k + 1); t.Add(k + 2); t.Add(k); t.Add(k + 2); t.Add(k + 3); }
            for (int i = 0; i < 4; i++) Face(p[i], p[(i + 1) % 4], p[(i + 1) % 4] + Vector3.up, p[i] + Vector3.up);
            Face(p[0] + Vector3.up, p[1] + Vector3.up, p[2] + Vector3.up, p[3] + Vector3.up);
            return Finish("Hedge", v, c, t);
        }

        static Mesh Cones(string name, int seg, float radius, float height, Color low, Color high, int tiers = 3)
        {
            var v = new List<Vector3>(); var c = new List<Color>(); var t = new List<int>();
            for (int k = 0; k < tiers; k++)
            {
                float y0 = 1.2f + (height - 1.2f) * k / (tiers + 0.6f), y1 = tiers == 1 ? height : y0 + (height - 1.2f) / tiers * 1.25f, rr = radius * (1f - 0.26f * k); int b = v.Count;
                v.Add(new Vector3(0, y1, 0)); c.Add(high);
                for (int i = 0; i < seg; i++) { float a = i / (float)seg * Mathf.PI * 2f; v.Add(new Vector3(Mathf.Cos(a) * rr, y0, Mathf.Sin(a) * rr)); c.Add(Color.Lerp(low, high, k / (float)tiers * 0.6f)); }
                for (int i = 0; i < seg; i++) { t.Add(b); t.Add(b + 1 + (i + 1) % seg); t.Add(b + 1 + i); }
            }
            return Finish(name, v, c, t);
        }

        static Mesh Finish(string name, List<Vector3> v, List<Color> c, List<int> t)
        {
            var m = new Mesh { name = name }; m.SetVertices(v); m.SetColors(c); m.SetTriangles(t, 0); m.RecalculateNormals(); m.RecalculateBounds();
            // make every face look outwards whatever the order above
            var nrm = m.normals; var tri = m.triangles; var vs = m.vertices; Vector3 centre = m.bounds.center;
            for (int i = 0; i < tri.Length; i += 3)
            {
                Vector3 a = vs[tri[i]], b = vs[tri[i + 1]], d = vs[tri[i + 2]]; var fc = (a + b + d) / 3f - new Vector3(centre.x * 0f, centre.y, centre.z * 0f); fc.y *= 0.3f;
                if (Vector3.Dot(Vector3.Cross(b - a, d - a), fc) < 0) { int s = tri[i + 1]; tri[i + 1] = tri[i + 2]; tri[i + 2] = s; }
            }
            m.triangles = tri; m.RecalculateNormals(); return m;
        }
    }
}
