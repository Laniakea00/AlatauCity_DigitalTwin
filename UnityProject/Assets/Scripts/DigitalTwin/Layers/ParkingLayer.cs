using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Geometry of the new map data that appears by year (parking lots, the ground of solar fields): one combined mesh per
    /// 3 km chunk (1 km chunks made some 750 draw calls a frame on the wide views, for small flat geometry) (AlatauCity/Landmark), its items in the order of their year in the current scenario. The mesh is drawn up to the
    /// last item open in the current year (the index count of its submesh), so a change of year costs nothing and a change of
    /// scenario rebuilds the chunks once.</summary>
    public class YearChunks
    {
        const float Size = 3000f;
        struct Item { public int Id; public int[] Y; }
        class Chunk { public GameObject Go; public MeshFilter F; public Mesh M; public int[] Year = new int[0]; public int[] Idx = new int[0]; public List<Item> Items = new List<Item>(); }
        readonly Dictionary<long, Chunk> chunks = new Dictionary<long, Chunk>();
        readonly Action<int, LandmarkKit> build; readonly Transform parent; readonly Material mat; readonly string name;
        int sc = -1, year = int.MinValue;
        /// <summary>Triangles of all chunks (after the last rebuild).</summary>
        public int Triangles { get; private set; }
        public int Chunks => chunks.Count;

        public YearChunks(Transform parent, Material mat, string name, Action<int, LandmarkKit> build) { this.parent = parent; this.mat = mat; this.name = name; this.build = build; }

        /// <summary>Item 'id' (built by the callback) at 'at', open from y[scenario] (0 or missing = always).</summary>
        public void Add(int id, Vector2 at, int[] y)
        {
            long k = ((long)(Mathf.FloorToInt(at.x / Size) + 100000) << 32) | (uint)(Mathf.FloorToInt(at.y / Size) + 100000);
            if (!chunks.TryGetValue(k, out var c)) chunks[k] = c = new Chunk();
            c.Items.Add(new Item { Id = id, Y = y });
        }
        static int YearOf(int[] y, int s) { int v = MapPolys.Year(y, s); return v <= 0 ? int.MinValue : v; }

        /// <summary>Shows what is open in year y of scenario s; call it every frame (it does nothing unless the year or scenario changed).</summary>
        public void Apply(int y, int s)
        {
            if (s != sc) { Rebuild(s); sc = s; year = int.MinValue; }
            if (y == year) return; year = y;
            foreach (var c in chunks.Values)
            {
                int k = 0; while (k < c.Year.Length && c.Year[k] <= y) k++;
                int count = k == 0 ? 0 : c.Idx[k - 1];
                if (c.Go == null) continue;
                c.Go.SetActive(count > 0);
                if (count > 0 && c.M.GetIndexCount(0) != (uint)count) c.M.SetSubMesh(0, new SubMeshDescriptor(0, count), MeshUpdateFlags.DontRecalculateBounds | MeshUpdateFlags.DontValidateIndices);
            }
        }
        void Rebuild(int s)
        {
            Triangles = 0;
            foreach (var c in chunks.Values)
            {
                c.Items.Sort((a, b) => YearOf(a.Y, s).CompareTo(YearOf(b.Y, s)));
                var kit = new LandmarkKit(); c.Year = new int[c.Items.Count]; c.Idx = new int[c.Items.Count];
                for (int i = 0; i < c.Items.Count; i++) { build(c.Items[i].Id, kit); c.Year[i] = YearOf(c.Items[i].Y, s); c.Idx[i] = kit.IndexCount; }
                if (c.M != null) UnityEngine.Object.Destroy(c.M);
                c.M = kit.ToMesh(name); Triangles += kit.IndexCount / 3;
                if (c.Go == null)
                {
                    c.Go = new GameObject(name); c.Go.transform.SetParent(parent, false);
                    c.F = c.Go.AddComponent<MeshFilter>(); var r = c.Go.AddComponent<MeshRenderer>(); r.sharedMaterial = mat;
                    r.shadowCastingMode = ShadowCastingMode.On;
                }
                c.F.sharedMesh = c.M;
            }
        }
    }

    /// <summary>Parking of the new map data (Resources/Landmarks/parking.json, tools/map CONTRACT §6): surface lots (asphalt draped
    /// on the ground with bay markings), multi-storey garages (a storeyed box with open decks and a round ramp tower) and underground
    /// garages (only their entrance pavilion), each from its year of the scenario. One combined mesh per 3 km chunk. Without the file
    /// nothing is made.</summary>
    public class ParkingLayer : MonoBehaviour
    {
        [Serializable] class LotJ { public int t; public int cap; public int lv; public int[] y; public float[] p; }
        [Serializable] class ParkingJ { public int v; public LotJ[] lots; }
        public static ParkingLayer Instance;
        string json; LotJ[] lots; Vector2[][] rings; YearChunks chunks; bool built;

        static readonly Color32 Asphalt = LM.C("#55585b"), Paint = LM.C("#d9d8d0"), Conc = LM.C("#cfcbc3"), ConcD = LM.C("#a9a59d"), Deck = LM.C("#2c2f33"), Sign = LM.C("#1f5fbf");
        const float StoreyH = 3.0f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (Instance != null) return;
            var txt = MapPolys.Load("parking"); if (txt == null) return;            // no file: today's city, nothing to add
            Instance = new GameObject("Parking (map data)").AddComponent<ParkingLayer>(); Instance.json = txt;
        }
        void Start() { TryBuild(); }

        void TryBuild()
        {
            if (built) return;
            if (!TwinData.Ready || CityGround.HeightAt(0, 0) == 0f) { Invoke(nameof(TryBuild), 0.3f); return; }
            built = true;
            var sh = Shader.Find("AlatauCity/Landmark"); if (sh == null) { Debug.LogWarning("[Alatau] parking: shader missing"); return; }
            ParkingJ j; try { j = JsonUtility.FromJson<ParkingJ>(json); } catch (Exception ex) { Debug.LogWarning("[Alatau] parking.json unreadable: " + ex.Message); return; }
            json = null;
            if (j?.lots == null || j.lots.Length == 0) return;
            lots = j.lots; rings = new Vector2[lots.Length][];
            chunks = new YearChunks(transform, new Material(sh) { name = "Parking" }, "Parking", Build);
            int[] n = new int[3]; int cap = 0, levels = 0; float ha = 0f;
            for (int i = 0; i < lots.Length; i++)
            {
                var r = MapPolys.Ring(lots[i].p); if (r == null) continue;
                rings[i] = r; int t = Mathf.Clamp(lots[i].t, 0, 2); n[t]++; cap += Mathf.Max(0, lots[i].cap); ha += Mathf.Abs(MapPolys.SignedArea(r)) / 10000f;
                if (t == 1) levels += Levels(lots[i]);
                chunks.Add(i, MapPolys.Centre(r), lots[i].y);
            }
            chunks.Apply(TwinState.Year, (int)TwinState.Scenario);
            Debug.Log($"[Alatau] parking.json: {n[0] + n[1] + n[2]} lots, {ha:0.0} ha: {n[0]} surface, {n[1]} multi-storey ({levels} decks), {n[2]} underground (entrances only); {cap} spaces; {chunks.Chunks} chunk meshes, {chunks.Triangles} triangles");
        }
        void Update() { if (chunks != null) chunks.Apply(TwinState.Year, (int)TwinState.Scenario); }

        static int Levels(LotJ l) => Mathf.Clamp(l.lv <= 0 ? 3 : l.lv, 1, 12);
        static float H(Vector2 p) => CityGround.HeightAt(p.x, p.y);

        void Build(int i, LandmarkKit k)
        {
            var r = rings[i]; if (r == null) return;
            switch (Mathf.Clamp(lots[i].t, 0, 2))
            {
                case 0: Surface(k, r); break;
                case 1: Multi(k, r, Levels(lots[i])); break;
                default: Entrance(k, r); break;
            }
        }

        // ------------------------------------------------------------------ surface lot
        static void Surface(LandmarkKit k, Vector2[] r)
        {
            var tri = MapPolys.Triangulate(r);
            for (int q = 0; q + 2 < tri.Count; q += 3) Drape(k, r[tri[q]], r[tri[q + 1]], r[tri[q + 2]], 0);
            // bays: double rows (5 m bays, a 6.5 m aisle) along the longest side, a line every 2.5 m, only where a whole line fits inside
            Axis(r, out var u, out var v);
            float u0 = float.MaxValue, u1 = float.MinValue, v0 = float.MaxValue, v1 = float.MinValue;
            foreach (var p in r) { float a = Vector2.Dot(p, u), b = Vector2.Dot(p, v); u0 = Mathf.Min(u0, a); u1 = Mathf.Max(u1, a); v0 = Mathf.Min(v0, b); v1 = Mathf.Max(v1, b); }
            int lines = 0;
            for (float m = v0 + 1.0f; m + 5f <= v1 && lines < 3000; m += 16.5f)
                foreach (float band in new[] { m, m + 11.5f })
                {
                    if (band + 5f > v1 - 0.5f) continue;
                    for (float a = u0 + 1.5f; a <= u1 - 1.5f && lines < 3000; a += 2.5f)
                    {
                        Vector2 p0 = u * a + v * (band + 0.3f), p1 = u * a + v * (band + 4.9f);
                        if (!MapPolys.Inside(r, p0.x, p0.y) || !MapPolys.Inside(r, p1.x, p1.y) || EdgeDist(r, p0) < 0.8f || EdgeDist(r, p1) < 0.8f) continue;
                        Line(k, p0, p1, 0.12f); lines++;
                    }
                }
        }
        /// <summary>A triangle draped on the ground: split until no side is longer than 24 m (the ground grid is 50 m).</summary>
        static void Drape(LandmarkKit k, Vector2 a, Vector2 b, Vector2 c, int depth)
        {
            float ab = (b - a).sqrMagnitude, bc = (c - b).sqrMagnitude, ca = (a - c).sqrMagnitude, m = Mathf.Max(ab, Mathf.Max(bc, ca));
            if (m > 24f * 24f && depth < 10)
            {
                if (m == ab) { var h = (a + b) * 0.5f; Drape(k, a, h, c, depth + 1); Drape(k, h, b, c, depth + 1); }
                else if (m == bc) { var h = (b + c) * 0.5f; Drape(k, a, b, h, depth + 1); Drape(k, a, h, c, depth + 1); }
                else { var h = (c + a) * 0.5f; Drape(k, a, b, h, depth + 1); Drape(k, h, b, c, depth + 1); }
                return;
            }
            Vector3 A = new Vector3(a.x, H(a) + 0.10f, a.y), B = new Vector3(b.x, H(b) + 0.10f, b.y), C = new Vector3(c.x, H(c) + 0.10f, c.y);
            k.Tri(A, B, C, Vector3.up, Asphalt, LM.Roof, 3f, a, b, c);
        }
        static void Line(LandmarkKit k, Vector2 a, Vector2 b, float w)
        {
            var d = (b - a).normalized; var s = new Vector2(-d.y, d.x) * (w * 0.5f);
            Vector3 P(Vector2 q) => new Vector3(q.x, H(q) + 0.16f, q.y);
            k.Quad(P(a - s), P(a + s), P(b + s), P(b - s), Vector3.up, Paint, LM.Roof, 3f, a - s, a + s, b + s, b - s);
        }
        /// <summary>u along the longest side of the ring, v across it.</summary>
        static void Axis(Vector2[] r, out Vector2 u, out Vector2 v)
        {
            float best = -1f; u = Vector2.right;
            for (int i = 0, j = r.Length - 1; i < r.Length; j = i++) { var e = r[i] - r[j]; if (e.sqrMagnitude > best) { best = e.sqrMagnitude; u = e.normalized; } }
            v = new Vector2(-u.y, u.x);
        }
        static float EdgeDist(Vector2[] r, Vector2 p)
        {
            float d = float.MaxValue; for (int i = 0, j = r.Length - 1; i < r.Length; j = i++) d = Mathf.Min(d, MapPolys.DistToSeg(p, r[j], r[i])); return d;
        }

        // ------------------------------------------------------------------ multi-storey garage
        static void Multi(LandmarkKit k, Vector2[] r, int levels)
        {
            float g0 = float.MaxValue, g1 = float.MinValue; foreach (var p in r) { float h = H(p); g0 = Mathf.Min(g0, h); g1 = Mathf.Max(g1, h); }
            var fp = new List<Vector2>(r); var c = MapPolys.Centre(r);
            var inset = new List<Vector2>(r.Length); foreach (var p in r) { var d = c - p; float L = d.magnitude; inset.Add(L > 1.2f ? p + d / L * 0.45f : p); }
            float y = g1 + 0.3f;
            k.Prism(fp, g0 - 0.5f, y, ConcD, LM.Solid, 3f, Conc, -1);                            // plinth down to the lowest corner
            for (int l = 0; l < levels; l++, y += StoreyH)
            {
                k.Prism(fp, y, y + 0.9f, Conc, LM.Solid, StoreyH, Conc, -1);                    // deck edge with its parapet
                k.Prism(inset, y + 0.9f, y + StoreyH, Deck, LM.Solid, StoreyH, Deck, -1);       // the open storey above it, dark inside
            }
            k.Prism(fp, y, y + 1.1f, Conc, LM.Solid, 3f, Asphalt, LM.Roof);                    // roof deck (parking) behind its parapet
            // the ramp: a round tower in the corner nearest the first point, a storey above the roof
            var cor = r[0]; var into = (c - cor); float dist = into.magnitude;
            if (dist > 12f)
            {
                var rc = cor + into / dist * 9f;
                k.Cylinder(new Vector3(rc.x, g0 - 0.5f, rc.y), 6.5f, y + 2.6f - (g0 - 0.5f), 14, ConcD, LM.Solid, StoreyH, Conc, LM.Roof);
            }
        }

        // ------------------------------------------------------------------ underground garage: its entrance
        static void Entrance(LandmarkKit k, Vector2[] r)
        {
            // on the longest side, the opening facing out: a pavilion 7 × 12 m over the ramp, a dark opening, the blue "P" sign
            float best = -1f; int bi = 0;
            for (int i = 0, j = r.Length - 1; i < r.Length; j = i++) { float L = (r[i] - r[j]).sqrMagnitude; if (L > best) { best = L; bi = i; } }
            Vector2 a = r[(bi + r.Length - 1) % r.Length], b = r[bi], m = (a + b) * 0.5f, u = (b - a).normalized, nIn = new Vector2(-u.y, u.x);
            var c = MapPolys.Centre(r); if (Vector2.Dot(c - m, nIn) < 0f) nIn = -nIn;
            Vector2 f = m + nIn * 1.0f;                                                             // the front, just inside the lot
            float g = H(f);
            var fp = new List<Vector2> { f - u * 3.5f, f + u * 3.5f, f + u * 3.5f + nIn * 12f, f - u * 3.5f + nIn * 12f };
            k.Prism(fp, g - 0.4f, g + 3.4f, Conc, LM.Solid, 3f, ConcD, LM.Roof);
            Vector3 F(Vector2 q, float y) => new Vector3(q.x, y, q.y);
            Vector3 o = F(-nIn * 0.04f, 0f);
            k.Quad(F(f - u * 2.8f, g) + o, F(f + u * 2.8f, g) + o, F(f + u * 2.8f, g + 2.7f) + o, F(f - u * 2.8f, g + 2.7f) + o, F(-nIn, 0f), Deck, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
            k.Beam(F(f - u * 0.6f, g + 3.05f) + o * 4f, F(f + u * 0.6f, g + 3.05f) + o * 4f, 0.12f, 0.6f, Sign, LM.Light);
        }
    }
}
