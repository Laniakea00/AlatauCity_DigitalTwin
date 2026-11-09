using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The beaches of Green on the Kapchagay shore (Resources/Landmarks/coast.json, tools/map/export/coast.py, модель qTwin):
    /// sand along the water's edge of the shore parks with rows of umbrellas and loungers, a promenade behind it with lamps, benches
    /// and trees, beach pavilions with cafés, lifeguard towers, piers into the water with boats, beach volleyball courts, and at the
    /// marina a Ferris wheel and a floating water park. Everything stands on the terrain, from the beaches' year on (light seasonal
    /// structures: the shore band takes no capital buildings).</summary>
    public class CoastLayer : MonoBehaviour
    {
        public static CoastLayer Instance;
        [System.Serializable] class TriJ { public float[] t; public int y; }
        [System.Serializable] class WalkJ { public float[] p; public float w; public int y; }
        [System.Serializable] class PtJ { public float x, z, yaw; public int y; }
        [System.Serializable] class PierJ { public float x0, z0, x1, z1; public int y; }
        [System.Serializable] class CoastJ { public TriJ[] beaches; public WalkJ[] walks; public PtJ[] pavilions, towers, courts; public PierJ[] piers; }

        static readonly Color32 Sand = LM.C("#e4d3a2"), SandWet = LM.C("#cdb987"), Deck = LM.C("#9c7a52"), DeckD = LM.C("#7d6141"), White = LM.C("#f2f1ec"),
            Glass = LM.C("#3b5a6e"), Red = LM.C("#e0261b"), Pave = LM.C("#cfc8bb"), Leaf = LM.C("#4f7a3a"), Pole = LM.C("#8d939a"), Lamp = LM.C("#ffe2a8"),
            Net = LM.C("#e9e9e4"), Inflate = LM.C("#2f8fd8"), Inflate2 = LM.C("#f2c230");
        static readonly Color32[] Umbrella = { LM.C("#f2f1ec"), LM.C("#e8b923"), LM.C("#d9483b"), LM.C("#2f8fd8"), LM.C("#f08a24") };

        Material mat; readonly List<(GameObject go, int y)> parts = new List<(GameObject, int)>(); int lastYear = -999; bool built;

        // ---- the trees of the beaches, the promenade and the recreation sites: drawn by FilmTrees like every tree of the city (instanced,
        // fine crowns near the camera, light ones further, none beyond 6 km, shadows within 2.6 km), not merged into the meshes of the
        // layer, where some 14 000 crowns were drawn in full from any distance (owner 10.11.2026: speed without losing quality)
        const float TreeCell = 600f;
        readonly Dictionary<long, (List<Matrix4x4> m, List<float> y, List<Vector4> t, int sp, Vector3 c)> treeCells = new Dictionary<long, (List<Matrix4x4>, List<float>, List<Vector4>, int, Vector3)>();
        readonly List<(int s, Matrix4x4[] m, MaterialPropertyBlock p, Bounds b)> treeBatches = new List<(int, Matrix4x4[], MaterialPropertyBlock, Bounds)>();
        readonly Plane[] treePlanes = new Plane[6];
        static float[] treeTop;

        /// <summary>A tree as LandmarkKit.Tree would put it (the same species, size, turn, jitter and tint from the seed), into the instanced cells.</summary>
        void AddTree(Vector3 p, float h, float seed, int year)
        {
            float r = Mathf.Abs(Mathf.Sin(seed * 91.7f + 3.1f) * 43758.5453f) % 1f, r2 = Mathf.Abs(Mathf.Sin(seed * 47.3f + 1.7f) * 24634.6345f) % 1f;
            int sp = r < 0.80f ? 0 : r < 0.97f ? 1 : 2;
            if (treeTop == null) { treeTop = new float[3]; for (int i = 0; i < 3; i++) treeTop[i] = Mathf.Max(FilmTrees.SpeciesMesh(i).bounds.max.y, 1f); }
            float sc = h * (sp == 1 ? 1.2f : 1f) / treeTop[sp], yaw = seed * 137f * Mathf.Rad2Deg;
            float tv = 0.80f + 0.30f * r2, tw = (r * 7.31f) % 1f;
            var hue = tw < 0.34f ? new Vector3(0.78f, 0.92f, 0.84f) : tw < 0.62f ? new Vector3(0.95f, 0.93f, 0.74f) : tw < 0.84f ? new Vector3(0.82f, 0.90f, 0.88f) : new Vector3(0.88f, 0.97f, 0.80f);
            p += LandmarkKit.TreeJitter(seed);
            long key = ((long)Mathf.FloorToInt(p.x / TreeCell) << 32) ^ (long)(uint)Mathf.FloorToInt(p.z / TreeCell) ^ ((long)sp << 60);
            if (!treeCells.TryGetValue(key, out var cell)) treeCells[key] = cell = (new List<Matrix4x4>(), new List<float>(), new List<Vector4>(), sp, p);
            cell.m.Add(Matrix4x4.TRS(p, Quaternion.Euler(0f, -yaw, 0f), new Vector3(sc, sc * (0.92f + 0.16f * r2), sc)));
            cell.y.Add(year); cell.t.Add(new Vector4(hue.x * tv, hue.y * tv, hue.z * tv, 1f));
        }

        void TreeBatches()
        {
            foreach (var cell in treeCells.Values)
                for (int o = 0; o < cell.m.Count; o += 1023)
                {
                    int n = Mathf.Min(1023, cell.m.Count - o); var m = cell.m.GetRange(o, n).ToArray(); var pb = new MaterialPropertyBlock();
                    pb.SetFloatArray("_TreeYear", cell.y.GetRange(o, n)); pb.SetVectorArray("_TreeTint", cell.t.GetRange(o, n));
                    var b = new Bounds(m[0].GetColumn(3), Vector3.one * 16f); foreach (var q in m) b.Encapsulate(new Bounds((Vector3)q.GetColumn(3) + Vector3.up * 6f, Vector3.one * 16f));
                    treeBatches.Add((cell.sp, m, pb, b));
                }
            treeCells.Clear();
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Beaches of Green (coast)").AddComponent<CoastLayer>(); }
        void Awake() { Instance = this; }
        void Start() { TryBuild(); }

        void TryBuild()
        {
            if (!TwinData.Ready || CityGround.HeightAt(0, 0) == 0f) { Invoke(nameof(TryBuild), 0.5f); return; }
            var ta = Resources.Load<TextAsset>("Landmarks/coast"); var sh = Shader.Find("AlatauCity/Landmark");
            if (ta == null || sh == null) return;
            CoastJ c; try { c = JsonUtility.FromJson<CoastJ>(ta.text); } catch { return; }
            if (c == null) return;
            mat = new Material(sh) { name = "Beaches" };
            built = true;
            float H(float x, float z) => CityGround.HeightAt(x, z);
            var rnd = new System.Random(2034);
            float R() => (float)rnd.NextDouble();
            int nUmb = 0, nTree = 0, y0 = 2034;

            // ---- sand, and the umbrellas and loungers in rows on it (a cluster every 13 m where the hash says, not on the wet edge)
            var sand = new LandmarkKit(); var umb = new LandmarkKit();
            if (c.beaches != null)
                foreach (var b in c.beaches)
                {
                    if (b.t == null || b.t.Length < 6) continue; y0 = b.y;
                    Vector2 lo = new Vector2(1e9f, 1e9f), hi = -lo;
                    for (int i = 0; i + 5 < b.t.Length; i += 6)
                    {
                        Vector3 A(int k) => new Vector3(b.t[i + 2 * k], H(b.t[i + 2 * k], b.t[i + 2 * k + 1]) + 0.07f, b.t[i + 2 * k + 1]);
                        Vector3 p0 = A(0), p1 = A(1), p2 = A(2);
                        if (Vector3.Cross(p1 - p0, p2 - p0).y < 0f) { var t = p1; p1 = p2; p2 = t; }
                        sand.Tri(p0, p1, p2, Vector3.up, Sand, LM.Solid, 1f, new Vector2(p0.x, p0.z), new Vector2(p1.x, p1.z), new Vector2(p2.x, p2.z));
                        for (int k = 0; k < 3; k++) { lo = Vector2.Min(lo, new Vector2(b.t[i + 2 * k], b.t[i + 2 * k + 1])); hi = Vector2.Max(hi, new Vector2(b.t[i + 2 * k], b.t[i + 2 * k + 1])); }
                    }
                    // umbrella spots: a 13 m grid over the beach, kept where the point lies in one of its triangles
                    for (float gx = lo.x + 6f; gx < hi.x; gx += 13f)
                        for (float gz = lo.y + 6f; gz < hi.y; gz += 13f)
                        {
                            float jx = gx + (R() - 0.5f) * 4f, jz = gz + (R() - 0.5f) * 4f; if (R() < 0.35f) continue;
                            if (!InTris(b.t, jx, jz)) continue;
                            float gy = H(jx, jz) + 0.07f; var col = Umbrella[rnd.Next(Umbrella.Length)]; float yaw = R() * 360f;
                            umb.Beam(new Vector3(jx, gy, jz), new Vector3(jx, gy + 2.4f, jz), 0.07f, 0.07f, White, LM.Solid);
                            umb.Cylinder(new Vector3(jx, gy + 2.2f, jz), 1.5f, 0.06f, 8, col, LM.Solid, 1f, col, LM.Solid, 0.45f);
                            var r = Quaternion.Euler(0f, yaw, 0f);
                            foreach (float s in new[] { -0.9f, 0.9f })
                            {
                                var q = new Vector3(jx, 0f, jz) + r * new Vector3(s, 0f, 0.4f); q.y = H(q.x, q.z) + 0.07f;
                                umb.Box(q + Vector3.up * 0.2f, new Vector3(0.65f, 0.3f, 1.9f), yaw, White, LM.Solid, 1f, White, LM.Solid);
                            }
                            nUmb++;
                        }
                }
            Add(sand, "Beaches · sand", y0); Add(umb, "Beaches · umbrellas and loungers", y0);

            // ---- the promenade: paving on the terrain, lamps every 32 m, benches and a row of trees on the land side every 14 m
            var walk = new LandmarkKit();
            if (c.walks != null)
                foreach (var w in c.walks)
                {
                    if (w.p == null || w.p.Length < 4) continue;
                    int n = w.p.Length / 2; var P = new Vector2[n]; for (int i = 0; i < n; i++) P[i] = new Vector2(w.p[2 * i], w.p[2 * i + 1]);
                    float hw = w.w * 0.5f, acc = 0f, nextLamp = 0f, nextTree = 7f;
                    for (int i = 0; i + 1 < n; i++)
                    {
                        Vector2 a = P[i], b = P[i + 1], d = (b - a); float L = d.magnitude; if (L < 0.2f) continue; d /= L; var s = new Vector2(-d.y, d.x);
                        Vector3 V(Vector2 q, float o) { var e = q + s * o; return new Vector3(e.x, H(e.x, e.y) + 0.1f, e.y); }
                        Vector3 q0 = V(a, -hw), q1 = V(a, hw), q2 = V(b, hw), q3 = V(b, -hw);
                        walk.Quad(q0, q1, q2, q3, Vector3.up, Pave, LM.Paving, 1f, new Vector2(q0.x, q0.z), new Vector2(q1.x, q1.z), new Vector2(q2.x, q2.z), new Vector2(q3.x, q3.z));
                        while (nextLamp <= acc + L)
                        {
                            var q = a + d * (nextLamp - acc) + s * (hw + 0.6f); float gy = H(q.x, q.y);
                            walk.Beam(new Vector3(q.x, gy, q.y), new Vector3(q.x, gy + 4.5f, q.y), 0.12f, 0.12f, Pole, LM.Steel);
                            walk.Box(new Vector3(q.x, gy + 4.6f, q.y), new Vector3(0.5f, 0.3f, 0.5f), 0f, Lamp, LM.Light, 1f, Lamp, LM.Light);
                            var bq = a + d * (nextLamp - acc + 6f) + s * (hw + 0.8f);
                            walk.Box(new Vector3(bq.x, H(bq.x, bq.y) + 0.25f, bq.y), new Vector3(1.8f, 0.45f, 0.5f), Mathf.Atan2(d.x, d.y) * Mathf.Rad2Deg, Deck, LM.Solid, 1f, Deck, LM.Solid);
                            nextLamp += 32f;
                        }
                        while (nextTree <= acc + L)
                        {
                            foreach (float sg in new[] { -1f, 1f })
                            {
                                var q = a + d * (nextTree - acc) + s * (sg * (hw + 3.5f));
                                AddTree(new Vector3(q.x, H(q.x, q.y), q.y), 7f + R() * 3f, q.x * 0.01f + q.y * 0.013f, y0); nTree++;
                            }
                            nextTree += 14f;
                        }
                        acc += L;
                    }
                }
            Add(walk, "Beaches · promenade", y0);

            // ---- pavilions: a timber deck, a white box with a glass front to the water, a flat roof and an awning; tables on the deck
            var bld = new LandmarkKit();
            if (c.pavilions != null)
                foreach (var p in c.pavilions)
                {
                    float gy = H(p.x, p.z); var r = Quaternion.Euler(0f, p.yaw, 0f); var o = new Vector3(p.x, gy, p.z);
                    Vector3 W(float x, float y, float z) => o + r * new Vector3(x, y, z);
                    bld.Box(W(0f, 0.25f, 3f), new Vector3(22f, 0.5f, 16f), p.yaw, DeckD, LM.Solid, 1f, Deck, LM.Paving);
                    bld.Box(W(0f, 2.3f, -1f), new Vector3(16f, 3.6f, 7f), p.yaw, White, LM.Solid, 2f, White, LM.Roof);
                    bld.Box(W(0f, 2.1f, 2.56f), new Vector3(14f, 2.8f, 0.12f), p.yaw, Glass, LM.Glass, 1f, Glass, LM.Glass);
                    bld.Box(W(0f, 4.2f, 4.5f), new Vector3(18f, 0.15f, 5f), p.yaw, Umbrella[(int)Mathf.Abs(p.x) % Umbrella.Length], LM.Solid, 1f, Umbrella[(int)Mathf.Abs(p.x) % Umbrella.Length], LM.Solid);
                    foreach (float sg in new[] { -1f, 1f }) bld.Beam(W(sg * 8.8f, 0.5f, 6.8f), W(sg * 8.8f, 4.2f, 6.8f), 0.15f, 0.15f, White, LM.Solid);
                    for (int i = 0; i < 6; i++) bld.Box(W(-7.5f + i * 3f, 0.9f, 7.5f), new Vector3(1f, 0.08f, 1f), p.yaw, White, LM.Solid, 1f, White, LM.Solid);
                }
            // ---- lifeguard towers: four legs, a red and white cabin, a flag
            if (c.towers != null)
                foreach (var p in c.towers)
                {
                    float gy = H(p.x, p.z); var o = new Vector3(p.x, gy, p.z);
                    foreach (var (dx, dz) in new[] { (-0.9f, -0.9f), (0.9f, -0.9f), (-0.9f, 0.9f), (0.9f, 0.9f) })
                        bld.Beam(o + new Vector3(dx, 0f, dz), o + new Vector3(dx * 0.7f, 3f, dz * 0.7f), 0.12f, 0.12f, White, LM.Solid);
                    bld.Box(o + Vector3.up * 3.7f, new Vector3(1.8f, 1.4f, 1.8f), p.yaw, Red, LM.Solid, 1f, White, LM.Roof);
                    bld.Beam(o + new Vector3(0f, 4.4f, 0f), o + new Vector3(0f, 6.4f, 0f), 0.05f, 0.05f, Pole, LM.Steel);
                    bld.Box(o + new Vector3(0.45f, 6.1f, 0f), new Vector3(0.9f, 0.5f, 0.03f), p.yaw, Inflate2, LM.Solid, 1f, Inflate2, LM.Solid);
                }
            // ---- beach volleyball: a sand court with its lines, posts and the net
            if (c.courts != null)
                foreach (var p in c.courts)
                {
                    float gy = H(p.x, p.z) + 0.09f; var r = Quaternion.Euler(0f, p.yaw, 0f); var o = new Vector3(p.x, gy, p.z);
                    bld.Box(o + Vector3.up * 0.02f, new Vector3(9f, 0.04f, 18f), p.yaw, SandWet, LM.Solid, 1f, SandWet, LM.Solid);
                    foreach (float sg in new[] { -1f, 1f }) bld.Beam(o + r * new Vector3(sg * 5f, 0f, 0f), o + r * new Vector3(sg * 5f, 2.5f, 0f), 0.1f, 0.1f, White, LM.Solid);
                    bld.Beam(o + r * new Vector3(-5f, 2.2f, 0f), o + r * new Vector3(5f, 2.2f, 0f), 0.02f, 0.9f, Net, LM.Solid);
                }
            Add(bld, "Beaches · pavilions, towers and courts", y0);

            // ---- piers: a timber deck on piles out into the water, a lamp at its end, boats moored along it
            var pk = new LandmarkKit(); int nBoat = 0;
            if (c.piers != null)
                foreach (var p in c.piers)
                {
                    Vector3 a = new Vector3(p.x0, 0f, p.z0), b = new Vector3(p.x1, 0f, p.z1); float wy = H(p.x0, p.z0) + 1.1f; a.y = b.y = wy;
                    var d = (b - a); float L = d.magnitude; if (L < 5f) continue; d /= L; var s = Vector3.Cross(Vector3.up, d); float yaw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg;
                    pk.Box((a + b) * 0.5f, new Vector3(4f, 0.35f, L), yaw, DeckD, LM.Solid, 1f, Deck, LM.Paving);
                    for (float t = 0f; t <= L; t += 8f)
                        foreach (float sg in new[] { -1f, 1f }) { var q = a + d * t + s * (sg * 1.8f); pk.Beam(q + Vector3.down * 3f, q, 0.25f, 0.25f, DeckD, LM.Solid); }
                    pk.Beam(b, b + Vector3.up * 3.5f, 0.1f, 0.1f, Pole, LM.Steel); pk.Box(b + Vector3.up * 3.6f, new Vector3(0.4f, 0.3f, 0.4f), 0f, Lamp, LM.Light, 1f, Lamp, LM.Light);
                    for (float t = 22f; t < L - 6f; t += 16f)
                    {
                        var side = R() < 0.5f ? -1f : 1f; var q = a + d * t + s * (side * 4.6f); q.y = wy - 0.9f;
                        pk.Box(q + Vector3.up * 0.35f, new Vector3(2.2f, 0.7f, 7f), yaw, White, LM.Solid, 1f, White, LM.Solid);
                        pk.Box(q + Vector3.up * 0.95f + d * 0.6f, new Vector3(1.4f, 0.5f, 2f), yaw, Glass, LM.Glass, 1f, White, LM.Roof); nBoat++;
                    }
                }
            Add(pk, "Beaches · piers and boats", y0);

            // ---- at the marina: a Ferris wheel on the shore park and a floating water park off the beach
            var lm = LandmarkCatalog.All().Find(l => l.Id == "marina");
            if (lm != null && c.pavilions != null && c.pavilions.Length > 0)
            {
                PtJ best = c.pavilions[0]; float bd = float.MaxValue;
                foreach (var p in c.pavilions) { float dd = (new Vector2(p.x, p.z) - new Vector2(lm.X, lm.Z)).sqrMagnitude; if (dd > 160f * 160f && dd < bd) { bd = dd; best = p; } }
                var fw = Quaternion.Euler(0f, best.yaw, 0f) * Vector3.forward;                  // toward the water
                var wheelC = new Vector3(best.x, 0f, best.z) - fw * 95f; wheelC.y = H(wheelC.x, wheelC.z);
                var fk = new LandmarkKit(); Wheel(fk, wheelC, best.yaw + 90f, 28f);
                var poolC = new Vector3(best.x, 0f, best.z) + fw * 120f; float wy = H(best.x, best.z) + 0.2f;
                for (int i = 0; i < 9; i++)
                {
                    var q = poolC + Quaternion.Euler(0f, i * 40f, 0f) * Vector3.forward * (i == 0 ? 0f : 16f); q.y = wy;
                    fk.Box(q + Vector3.up * 0.5f, new Vector3(i == 0 ? 14f : 8f, 1f, i == 0 ? 14f : 3f), best.yaw + i * 40f, i % 2 == 0 ? Inflate : Inflate2, LM.Solid, 1f, i % 2 == 0 ? Inflate : Inflate2, LM.Solid);
                }
                fk.Cylinder(poolC + Vector3.up * (wy - poolC.y + 1f), 2.2f, 4f, 10, Inflate2, LM.Solid, 1f, Red, LM.Solid, 2f);
                Add(fk, "Beaches · Ferris wheel and water park", y0);
            }
            BuildRecreation();
            TreeBatches();                                    // the beach and the recreation trees, even when recreation.json is missing
            Debug.Log($"[Alatau] beaches of Green: {c.beaches?.Length ?? 0} beaches, {nUmb} umbrellas, {c.pavilions?.Length ?? 0} pavilions, {c.towers?.Length ?? 0} lifeguard towers, {c.piers?.Length ?? 0} piers ({nBoat} boats), {c.courts?.Length ?? 0} volleyball courts, {nTree} promenade trees");
        }

        // ================================================================== active recreation (recreation.json, tools/map/export/recreation.py)
        [System.Serializable] class LineJ { public float[] p; public float w; public int y; public string k; }
        [System.Serializable] class CircJ { public float x, z, r; public int y; }
        [System.Serializable] class ItemJ { public string k; public float x, z, yaw, w, d; public int y; }
        [System.Serializable] class FwJ { public float[] t; public int y, s; }
        [System.Serializable] class RecJ { public TriJ[] turf, ponds; public FwJ[] fairways; public LineJ[] paths; public CircJ[] greens, bunkers; public ItemJ[] items; public float[] trees, pines; }
        static readonly Color32 Fairway = LM.C("#9fd05a"), Fairway2 = LM.C("#b2dc6e"), Turf = LM.C("#557f38"), GreenC = LM.C("#4fd04a"), Fringe = LM.C("#86c95a"),
            Rough = LM.C("#6a9343"), Court = LM.C("#2f6f9e"), CourtG = LM.C("#3f8a4c"), Clay = LM.C("#c0603a"), Line = LM.C("#f4f4f0"), Rubber = LM.C("#c4473a"),
            Conc = LM.C("#bdb8ae"), Asph = LM.C("#4a4b4d"), Track = LM.C("#b84a35"), Dirt = LM.C("#a8774f"), Fence = LM.C("#2b4a3a"), Water = LM.C("#3d7fa8"),
            Asphalt = LM.C("#37383a"), Kerb = LM.C("#ecebe6"), KerbR = LM.C("#c8342b"), Runoff = LM.C("#c9b48c"), Pool = LM.C("#4fc3e0"), Bike = LM.C("#b46a55"), Cart = LM.C("#d9d2bf"), PlotLawn = LM.C("#78a556"), Seat = LM.C("#2f5f8e"), Seat2 = LM.C("#c9483a"),
            Pine = LM.C("#2f5a35"), Leaf2C = LM.C("#5f8a3c"), RoofRed = LM.C("#9a3b2c"), Steel = LM.C("#c9ccd0");

        /// <summary>A flat surface draped on the terrain: a grid of cells ≤ 12 m, local +z along w, +x along d, lift metres over the ground.</summary>
        static void Pad(LandmarkKit k, Vector3 c, float yaw, float w, float d, float lift, Color32 col, int mat)
        {
            var r = Quaternion.Euler(0f, yaw, 0f); int nz = Mathf.Max(1, Mathf.CeilToInt(w / 12f)), nx = Mathf.Max(1, Mathf.CeilToInt(d / 12f));
            Vector3 P(float fx, float fz) { var q = c + r * new Vector3((fx - 0.5f) * d, 0f, (fz - 0.5f) * w); q.y = CityGround.HeightAt(q.x, q.z) + lift; return q; }
            for (int i = 0; i < nx; i++)
                for (int j = 0; j < nz; j++)
                {
                    Vector3 a = P(i / (float)nx, j / (float)nz), b = P((i + 1) / (float)nx, j / (float)nz), cc = P((i + 1) / (float)nx, (j + 1) / (float)nz), dd = P(i / (float)nx, (j + 1) / (float)nz);
                    k.Quad(a, dd, cc, b, Vector3.up, col, mat, 1f, new Vector2(a.x, a.z), new Vector2(dd.x, dd.z), new Vector2(cc.x, cc.z), new Vector2(b.x, b.z));
                }
        }
        /// <summary>A draped ribbon along a polyline (x, z pairs), half width hw.</summary>
        static void Ribbon(LandmarkKit k, float[] p, float hw, float lift, Color32 col, int mat)
        {
            int n = p.Length / 2;
            for (int i = 0; i + 1 < n; i++)
            {
                Vector2 a = new Vector2(p[2 * i], p[2 * i + 1]), b = new Vector2(p[2 * i + 2], p[2 * i + 3]), d = b - a; float L = d.magnitude; if (L < 0.2f) continue; d /= L;
                var s = new Vector2(-d.y, d.x); int m = Mathf.Max(1, Mathf.CeilToInt(L / 10f));
                for (int q = 0; q < m; q++)
                {
                    Vector2 u = a + d * (L * q / m), v = a + d * (L * (q + 1) / m);
                    Vector3 V(Vector2 e) => new Vector3(e.x, CityGround.HeightAt(e.x, e.y) + lift, e.y);
                    Vector3 q0 = V(u - s * hw), q1 = V(u + s * hw), q2 = V(v + s * hw), q3 = V(v - s * hw);
                    k.Quad(q0, q1, q2, q3, Vector3.up, col, mat, 1f, new Vector2(q0.x, q0.z), new Vector2(q1.x, q1.z), new Vector2(q2.x, q2.z), new Vector2(q3.x, q3.z));
                }
            }
        }
        static void Disc(LandmarkKit k, float x, float z, float rad, float lift, Color32 col, int mat)
        {
            const int N = 16; var c = new Vector3(x, CityGround.HeightAt(x, z) + lift, z);
            for (int i = 0; i < N; i++)
            {
                float a0 = i * Mathf.PI * 2f / N, a1 = (i + 1) * Mathf.PI * 2f / N;
                var p0 = new Vector3(x + Mathf.Cos(a0) * rad, 0f, z + Mathf.Sin(a0) * rad); p0.y = CityGround.HeightAt(p0.x, p0.z) + lift;
                var p1 = new Vector3(x + Mathf.Cos(a1) * rad, 0f, z + Mathf.Sin(a1) * rad); p1.y = CityGround.HeightAt(p1.x, p1.z) + lift;
                k.Tri(c, p1, p0, Vector3.up, col, mat, 1f, new Vector2(c.x, c.z), new Vector2(p1.x, p1.z), new Vector2(p0.x, p0.z));
            }
        }
        /// <summary>Draped triangles (x, z, x, z, x, z, …), lift metres over the ground, wound to face up.</summary>
        static void Tris(LandmarkKit k, float[] t, float lift, Color32 col, int mat)
        {
            if (t == null) return;
            for (int i = 0; i + 5 < t.Length; i += 6)
            {
                Vector3 A(int q) => new Vector3(t[i + 2 * q], CityGround.HeightAt(t[i + 2 * q], t[i + 2 * q + 1]) + lift, t[i + 2 * q + 1]);
                Vector3 p0 = A(0), p1 = A(1), p2 = A(2);
                if (Vector3.Cross(p1 - p0, p2 - p0).y < 0f) { var s = p1; p1 = p2; p2 = s; }
                k.Tri(p0, p1, p2, Vector3.up, col, mat, 1f, new Vector2(p0.x, p0.z), new Vector2(p1.x, p1.z), new Vector2(p2.x, p2.z));
            }
        }
        /// <summary>A draped elliptic ring (or a filled ellipse when r0 = 0): centre o, local semi-axes a (x) and b (z), width w inward.</summary>
        static void Oval(LandmarkKit k, Vector3 o, float yaw, float a, float b, float w, float lift, Color32 col, int mat, bool fill = false)
        {
            int N = Mathf.Clamp(Mathf.CeilToInt(Mathf.PI * (a + b) / 6f), 48, 360); var r = Quaternion.Euler(0f, yaw, 0f);   // ≤ 6 m chords: the ring follows the ground
            Vector3 P(float t, float inset) { var q = o + r * new Vector3(Mathf.Cos(t) * (a - inset), 0f, Mathf.Sin(t) * (b - inset)); q.y = CityGround.HeightAt(q.x, q.z) + lift; return q; }
            var oc = o; oc.y = CityGround.HeightAt(o.x, o.z) + lift;
            for (int i = 0; i < N; i++)
            {
                float t0 = i * Mathf.PI * 2f / N, t1 = (i + 1) * Mathf.PI * 2f / N;
                if (fill) { var p0 = P(t0, 0f); var p1 = P(t1, 0f); k.Tri(oc, p1, p0, Vector3.up, col, mat, 1f, new Vector2(oc.x, oc.z), new Vector2(p1.x, p1.z), new Vector2(p0.x, p0.z)); continue; }
                Vector3 q0 = P(t0, 0f), q1 = P(t1, 0f), q2 = P(t1, w), q3 = P(t0, w);
                k.Quad(q0, q3, q2, q1, Vector3.up, col, mat, 1f, new Vector2(q0.x, q0.z), new Vector2(q3.x, q3.z), new Vector2(q2.x, q2.z), new Vector2(q1.x, q1.z));
            }
        }
        /// <summary>A rail round an ellipse: posts every few metres and a top rail, h high.</summary>
        static void OvalRail(LandmarkKit k, Vector3 o, float yaw, float a, float b, float h, Color32 col)
        {
            const int N = 96; var r = Quaternion.Euler(0f, yaw, 0f);
            Vector3 P(int i) { float t = i * Mathf.PI * 2f / N; var q = o + r * new Vector3(Mathf.Cos(t) * a, 0f, Mathf.Sin(t) * b); q.y = CityGround.HeightAt(q.x, q.z); return q; }
            for (int i = 0; i < N; i++) { var p0 = P(i); var p1 = P(i + 1); k.Beam(p0 + Vector3.up * h, p1 + Vector3.up * h, 0.12f, 0.12f, col, LM.Solid); if (i % 3 == 0) k.Beam(p0, p0 + Vector3.up * h, 0.1f, 0.1f, col, LM.Solid); }
        }
        /// <summary>A grandstand: a stepped seating block rising away from the field (local −z toward the field), a roof canopy on posts.</summary>
        static void Stand(LandmarkKit k, Vector3 c, float yaw, float len, float depth, float h, Color32 seat, bool roof)
        {
            var r = Quaternion.Euler(0f, yaw, 0f); float gy = CityGround.HeightAt(c.x, c.z);
            int steps = Mathf.Max(3, Mathf.RoundToInt(depth / 2.2f));
            for (int s = 0; s < steps; s++)
            {
                float z0 = -depth * 0.5f + s * depth / steps, hh = 0.8f + h * (s + 1f) / steps;
                var q = c + r * new Vector3(0f, 0f, z0 + depth / steps * 0.5f); q.y = gy + hh * 0.5f;
                k.Box(q, new Vector3(len, hh, depth / steps), yaw, Conc, LM.Solid, 2f, s % 2 == 0 ? seat : Conc, LM.Solid);
            }
            if (!roof) return;
            var rc = c + r * new Vector3(0f, 0f, depth * 0.1f); rc.y = gy + h + 6f;
            k.Box(rc, new Vector3(len + 4f, 0.6f, depth * 1.1f), yaw, White, LM.Solid, 1f, White, LM.Roof);
            for (float x = -len * 0.5f; x <= len * 0.5f + 0.1f; x += len / 6f) { var p = c + r * new Vector3(x, 0f, depth * 0.5f); p.y = gy; k.Beam(p, p + Vector3.up * (h + 6f), 0.4f, 0.4f, Steel, LM.Steel); }
        }

        void BuildRecreation()
        {
            var ta = Resources.Load<TextAsset>("Landmarks/recreation"); if (ta == null) return;
            RecJ c; try { c = JsonUtility.FromJson<RecJ>(ta.text); } catch { return; }
            if (c == null) return;
            var rnd = new System.Random(2036); float R() => (float)rnd.NextDouble();
            float H(float x, float z) => CityGround.HeightAt(x, z);
            var byYear = new Dictionary<int, LandmarkKit>();
            LandmarkKit K(int y) { if (!byYear.TryGetValue(y, out var k)) byYear[y] = k = new LandmarkKit(); return k; }
            int y0 = 2035, nCourts = 0, nItems = 0;
            // golf: the turf over the course, mowing stripes on the fairways, the greens with their fringe and flags, the bunkers
            if (c.turf != null) foreach (var t in c.turf) { Tris(K(t.y), t.t, 0.05f, Turf, LM.Plant); y0 = t.y; }
            if (c.fairways != null) foreach (var f in c.fairways) Tris(K(f.y), f.t, 0.09f, f.s == 0 ? Fairway : Fairway2, LM.Plant);
            if (c.greens != null)
                foreach (var g in c.greens)
                {
                    var k = K(g.y); Disc(k, g.x, g.z, g.r + 4f, 0.1f, Fringe, LM.Plant); Disc(k, g.x, g.z, g.r, 0.12f, GreenC, LM.Plant);
                    float gy = H(g.x, g.z); k.Beam(new Vector3(g.x, gy, g.z), new Vector3(g.x, gy + 2.4f, g.z), 0.05f, 0.05f, Line, LM.Solid);
                    k.Box(new Vector3(g.x + 0.35f, gy + 2.15f, g.z), new Vector3(0.7f, 0.45f, 0.03f), 0f, Red, LM.Solid, 1f, Red, LM.Solid);
                }
            if (c.bunkers != null) foreach (var b in c.bunkers) Disc(K(b.y), b.x, b.z, b.r, 0.13f, Sand, LM.Solid);
            if (c.ponds != null) foreach (var p in c.ponds) Tris(K(p.y), p.t, 0.14f, Water, LM.Water);
            if (c.paths != null)
                foreach (var p in c.paths)
                {
                    var col = p.k == "bike" ? Bike : p.k == "cart" ? Cart : p.k == "track" ? Asphalt : p.k == "kerb_r" ? KerbR : p.k == "kerb" ? Kerb : p.k == "runoff" ? Runoff : p.k == "pit" ? Asphalt : Pave;
                    Ribbon(K(p.y), p.p, p.w * 0.5f, p.k == "cart" ? 0.11f : p.k == "runoff" ? 0.09f : p.k == "kerb" || p.k == "kerb_r" ? 0.17f : 0.15f, col, LM.Paving);
                }
            if (c.items != null)
                foreach (var it in c.items)
                {
                    var k = K(it.y); var r = Quaternion.Euler(0f, it.yaw, 0f); var o = new Vector3(it.x, H(it.x, it.z), it.z); nItems++;
                    Vector3 W(float x, float z, float up) { var q = o + r * new Vector3(x, 0f, z); q.y = H(q.x, q.z) + up; return q; }
                    void Courts(float cx0, float cz0, float aw, float ad, float cw, float cl, float gap, Color32 surf, Color32 outer, bool glass)
                    {
                        int nx = Mathf.Max(1, Mathf.FloorToInt((ad - 6f) / (cw + gap))), nz = Mathf.Max(1, Mathf.FloorToInt((aw - 6f) / (cl + gap)));
                        for (int i = 0; i < nx; i++)
                            for (int j = 0; j < nz; j++)
                            {
                                float cx = cx0 + (i - (nx - 1) * 0.5f) * (cw + gap), cz = cz0 + (j - (nz - 1) * 0.5f) * (cl + gap); var cc = W(cx, cz, 0f);
                                Pad(k, cc, it.yaw, cl + 4f, cw + 4f, 0.12f, outer, LM.Solid); Pad(k, cc, it.yaw, cl, cw, 0.15f, surf, LM.Solid);
                                k.Box(W(cx, cz, 0.55f), new Vector3(cw, 0.9f, 0.04f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);               // the net
                                foreach (float sg in new[] { -1f, 1f })
                                {
                                    k.Box(W(cx + sg * cw * 0.5f, cz, 0.17f), new Vector3(0.08f, 0.02f, cl), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                    k.Box(W(cx, cz + sg * cl * 0.5f, 0.17f), new Vector3(cw, 0.02f, 0.08f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                    k.Box(W(cx + sg * (cw * 0.5f + 2f), cz, 1.5f), new Vector3(0.05f, 3f, cl + 4f), it.yaw, glass ? Glass : Fence, glass ? LM.Glass : LM.Solid, 1f, Fence, LM.Solid);
                                    k.Box(W(cx, cz + sg * (cl * 0.5f + 2f), 1.5f), new Vector3(cw + 4f, 3f, 0.05f), it.yaw, glass ? Glass : Fence, glass ? LM.Glass : LM.Solid, 1f, Fence, LM.Solid);
                                }
                                nCourts++;
                            }
                    }
                    void Pitch(float cx, float cz, float pw, float pl)
                    {
                        var cc = W(cx, cz, 0f);
                        Pad(k, cc, it.yaw, pl + 6f, pw + 6f, 0.12f, Rough, LM.Plant); Pad(k, cc, it.yaw, pl, pw, 0.15f, CourtG, LM.Plant);
                        for (int s = 0; s < 8; s++) Pad(k, W(cx, cz - pl * 0.5f + pl * (s + 0.5f) / 8f, 0f), it.yaw, pl / 16f, pw, 0.16f, s % 2 == 0 ? Fairway2 : CourtG, LM.Plant);
                        foreach (float sg in new[] { -1f, 1f })
                        {
                            k.Box(W(cx + sg * pw * 0.5f, cz, 0.18f), new Vector3(0.12f, 0.02f, pl), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                            k.Box(W(cx, cz + sg * pl * 0.5f, 0.18f), new Vector3(pw, 0.02f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                            k.Box(W(cx, cz + sg * pl * 0.5f, 1.2f), new Vector3(7.3f, 2.4f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                            k.Box(W(cx, cz + sg * (pl * 0.5f - 8f), 0.18f), new Vector3(40f, 0.02f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                        }
                        k.Box(W(cx, cz, 0.18f), new Vector3(pw, 0.02f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                    }
                    switch (it.k)
                    {
                        case "plot":
                            {
                                // a landscaped plot of its own: lawn, a low fence with an entrance gate on the −z side, a paved forecourt
                                Pad(k, o, it.yaw, it.w, it.d, 0.07f, PlotLawn, LM.Plant);
                                foreach (float sg in new[] { -1f, 1f })
                                {
                                    k.Box(W(sg * it.d * 0.5f, 0f, 0.9f), new Vector3(0.12f, 1.8f, it.w), it.yaw, Fence, LM.Solid, 1f, Fence, LM.Solid);
                                    k.Box(W(0f, it.w * 0.5f, 0.9f), new Vector3(it.d, 1.8f, 0.12f), it.yaw, Fence, LM.Solid, 1f, Fence, LM.Solid);
                                    k.Box(W(sg * (it.d * 0.25f + 6f), -it.w * 0.5f, 0.9f), new Vector3(it.d * 0.5f - 12f, 1.8f, 0.12f), it.yaw, Fence, LM.Solid, 1f, Fence, LM.Solid);
                                    k.Beam(W(sg * 6f, -it.w * 0.5f, 0f), W(sg * 6f, -it.w * 0.5f, 4.5f), 0.6f, 0.6f, White, LM.Solid);
                                }
                                k.Box(W(0f, -it.w * 0.5f, 4.6f), new Vector3(14f, 0.8f, 1.2f), it.yaw, White, LM.Solid, 1f, White, LM.Solid);
                                Pad(k, W(0f, -it.w * 0.5f + 7f, 0f), it.yaw, 14f, 24f, 0.1f, Pave, LM.Paving);
                                break;
                            }
                        case "tennis": Courts(0f, 0f, it.w, it.d, 11f, 24f, 6f, R() < 0.5f ? Court : Clay, CourtG, false); break;
                        case "padel": Courts(0f, 0f, it.w, it.d, 10f, 20f, 4f, Court, CourtG, true); break;
                        case "basketball":
                            Courts(-it.d * 0.25f, 0f, it.w, it.d * 0.5f, 15f, 28f, 6f, Clay, Conc, false);
                            Courts(it.d * 0.25f, 0f, it.w, it.d * 0.5f, 9f, 18f, 5f, Court, Conc, false);              // volleyball
                            break;
                        case "football":
                            {
                                float pw = Mathf.Min(68f, it.d - 16f), pl = Mathf.Min(105f, it.w - 16f);
                                Pitch(0f, 0f, pw, pl);
                                foreach (float sg in new[] { -1f, 1f }) Stand(k, W(sg * (pw * 0.5f + 8f), 0f, 0f), it.yaw + (sg > 0 ? 90f : -90f), pl * 0.55f, 6f, 3f, Seat, false);
                                for (int q = 0; q < 4; q++) { float sx = q % 2 == 0 ? -1 : 1, sz = q < 2 ? -1 : 1; var m0 = W(sx * (pw * 0.5f + 3f), sz * (pl * 0.5f + 3f), 0f); k.Beam(m0, m0 + Vector3.up * 18f, 0.3f, 0.3f, Pole, LM.Steel); }
                                break;
                            }
                        case "grandstand": Stand(k, W(0f, 0f, 0f), it.yaw, it.w, it.d, 20f, Seat, true); break;
                        case "pits":
                            {
                                // the pit building along the straight, the race control tower at its end
                                k.Box(W(0f, 0f, 5f), new Vector3(it.w, 10f, it.d), it.yaw, White, LM.Solid, 1f, White, LM.Roof);
                                k.Box(W(it.w * 0.5f - 18f, 0f, 16f), new Vector3(30f, 32f, 30f), it.yaw, Seat, LM.Glass, 3.6f, White, LM.Roof);
                                break;
                            }
                        case "stadium":
                            {
                                // football stadium: pitch, an athletics track round it, stands on four sides, roofs over the long stands, floodlights
                                Oval(k, o, it.yaw, 52f, 88f, 9f, 0.3f, Track, LM.Solid);
                                Pitch(0f, 0f, 68f, 105f);
                                foreach (float sg in new[] { -1f, 1f })
                                {
                                    Stand(k, W(sg * 72f, 0f, 0f), it.yaw + (sg > 0 ? 90f : -90f), 150f, 26f, 16f, sg > 0 ? Seat : Seat2, true);
                                    Stand(k, W(0f, sg * 104f, 0f), it.yaw + (sg > 0 ? 0f : 180f), 96f, 22f, 12f, Seat, false);
                                }
                                for (int q = 0; q < 4; q++) { float sx = q % 2 == 0 ? -1 : 1, sz = q < 2 ? -1 : 1; var m0 = W(sx * 72f, sz * 100f, 0f); k.Beam(m0, m0 + Vector3.up * 40f, 0.8f, 0.8f, Pole, LM.Steel); k.Box(m0 + Vector3.up * 40f, new Vector3(6f, 3f, 1f), it.yaw + 45f * sx * sz, Lamp, LM.Light, 1f, Lamp, LM.Light); }
                                break;
                            }
                        case "hippodrome":
                            {
                                // racecourse: a dirt oval with white rails, a turf infield with a pond, the grandstand on +x, stables and the
                                // paddock on −x
                                float A = it.d * 0.5f - 70f, B = it.w * 0.5f - 25f;
                                Oval(k, o, it.yaw, A + 4f, B + 4f, 30f, 0.2f, PlotLawn, LM.Plant);
                                Oval(k, o, it.yaw, A, B, 22f, 0.32f, Dirt, LM.Solid);
                                Oval(k, o, it.yaw, A - 22f, B - 22f, 0f, 0.24f, Fairway, LM.Plant, true);
                                OvalRail(k, o, it.yaw, A, B, 1.2f, White); OvalRail(k, o, it.yaw, A - 22f, B - 22f, 1.2f, White);
                                Disc(k, W(0f, B * 0.25f, 0f).x, W(0f, B * 0.25f, 0f).z, 26f, 0.16f, Water, LM.Water);
                                Stand(k, W(A + 26f, 0f, 0f), it.yaw + 90f, B * 0.9f, 30f, 14f, Seat, true);
                                k.Box(W(A + 50f, 0f, 7f), new Vector3(24f, 14f, B * 0.35f), it.yaw, White, LM.Solid, 3f, LM.C("#3a3d42"), LM.Roof);       // club and tote hall
                                for (int s = 0; s < 4; s++)
                                {
                                    var sc = W(-A - 40f, -B * 0.45f + s * 34f, 3f);
                                    k.Box(sc, new Vector3(16f, 6f, 28f), it.yaw, LM.C("#efe6d6"), LM.Solid, 2f, RoofRed, LM.Roof);                         // stables
                                }
                                Pad(k, W(-A - 40f, B * 0.45f, 0f), it.yaw, 70f, 46f, 0.12f, Dirt, LM.Solid);                                            // paddock
                                k.Box(W(-A - 40f, B * 0.45f, 0.7f), new Vector3(46f, 1.4f, 0.1f), it.yaw, White, LM.Solid, 1f, White, LM.Solid);
                                for (int q = 0; q < 10; q++) { var hp = W(-A + 11f, -B * 0.5f + q * B * 0.11f, 0.9f); k.Box(hp, new Vector3(0.6f, 1.6f, 2.4f), it.yaw + 8f * q, LM.C("#5a3a24"), LM.Solid, 1f, LM.C("#5a3a24"), LM.Solid); }   // horses on the track
                                break;
                            }
                        case "tennis_centre":
                            {
                                // show court in a bowl at +z, a grid of practice courts at −z, the club house between
                                var sc = W(0f, it.w * 0.24f, 0f);
                                Pad(k, sc, it.yaw, 40f, 22f, 0.15f, Court, LM.Solid);
                                k.Box(W(0f, it.w * 0.24f, 0.55f), new Vector3(11f, 0.9f, 0.04f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                foreach (float sg in new[] { -1f, 1f })
                                {
                                    Stand(k, W(sg * 24f, it.w * 0.24f, 0f), it.yaw + (sg > 0 ? 90f : -90f), 44f, 16f, 10f, Seat, false);
                                    Stand(k, W(0f, it.w * 0.24f + sg * 30f, 0f), it.yaw + (sg > 0 ? 0f : 180f), 34f, 16f, 10f, Seat2, false);
                                }
                                Courts(0f, -it.w * 0.22f, it.w * 0.48f, it.d, 11f, 24f, 6f, Clay, CourtG, false);
                                k.Box(W(0f, -2f, 3.5f), new Vector3(it.d * 0.5f, 7f, 14f), it.yaw, White, LM.Solid, 2f, LM.C("#3a3d42"), LM.Roof);
                                break;
                            }
                        case "arena":
                            {
                                // a multi-sport hall (basketball, volleyball, ice) with a curved roof, and outdoor courts beside it
                                var hc = W(0f, it.w * 0.18f, 0f); float hy = H(hc.x, hc.z);
                                k.Box(new Vector3(hc.x, hy + 9f, hc.z), new Vector3(70f, 18f, 96f), it.yaw, LM.C("#dfe3e6"), LM.Solid, 3f, LM.C("#dfe3e6"), LM.Roof);
                                k.Box(W(-35.1f, it.w * 0.18f, 6f), new Vector3(0.2f, 8f, 80f), it.yaw, Glass, LM.Glass, 1f, Glass, LM.Glass);
                                for (int s = 0; s < 6; s++) k.Box(new Vector3(hc.x, hy + 18.5f + Mathf.Sin((s + 0.5f) / 6f * Mathf.PI) * 4f, hc.z) + r * new Vector3(-30f + s * 12f, 0f, 0f), new Vector3(12.2f, 0.5f, 98f), it.yaw, Steel, LM.Metal, 1f, Steel, LM.Roof);
                                Courts(0f, -it.w * 0.3f, it.w * 0.36f, it.d, 15f, 28f, 6f, Clay, Conc, false);
                                break;
                            }
                        case "skate":
                            {
                                Pad(k, W(0f, 0f, 0f), it.yaw, it.w * 0.6f, it.d * 0.65f, 0.15f, Conc, LM.Paving);
                                for (int q = 0; q < 6; q++) k.Box(W((q - 2.5f) * 11f, (q % 2 == 0 ? -1 : 1) * 14f, 0.8f), new Vector3(8f, 1.6f, 6f), it.yaw + q * 25f, Conc, LM.Solid, 1f, LM.C("#9e9a92"), LM.Solid);
                                Oval(k, W(0f, 0f, 0f), it.yaw, 14f, 10f, 4f, 0.2f, LM.C("#a7a39b"), LM.Paving);
                                break;
                            }
                        case "ropes":
                            for (int i = 0; i < 4; i++)
                                for (int j = 0; j < 3; j++)
                                {
                                    var b0 = W((i - 1.5f) * 18f, (j - 1f) * 22f, 0f); k.Beam(b0, b0 + Vector3.up * 11f, 0.45f, 0.45f, Deck, LM.Solid);
                                    k.Box(b0 + Vector3.up * 8f, new Vector3(3f, 0.25f, 3f), it.yaw, Deck, LM.Solid, 1f, Deck, LM.Solid);
                                    if (i < 3) { var b1 = W((i - 0.5f) * 18f, (j - 1f) * 22f, 0f); k.Beam(b0 + Vector3.up * 9f, b1 + Vector3.up * 9f, 0.08f, 0.08f, Inflate2, LM.Solid); }
                                }
                            for (int q = 0; q < 14; q++) AddTree(W((R() - 0.5f) * it.d * 0.9f, (R() - 0.5f) * it.w * 0.9f, 0f), 9f + R() * 4f, q + it.x, it.y);
                            break;
                        case "playground":
                            Pad(k, W(0f, 0f, 0f), it.yaw, it.w * 0.5f, it.d * 0.6f, 0.15f, Rubber, LM.Solid);
                            for (int q = 0; q < 8; q++)
                            {
                                var p0 = W((R() - 0.5f) * it.d * 0.5f, (R() - 0.5f) * it.w * 0.4f, 0f); var col = Umbrella[q % Umbrella.Length];
                                k.Box(p0 + Vector3.up * 1.2f, new Vector3(3f + R() * 3f, 2.4f, 3f + R() * 2f), it.yaw + q * 30f, col, LM.Solid, 1f, col, LM.Solid);
                            }
                            break;
                        case "picnic":
                            for (int q = 0; q < 8; q++)
                            {
                                var p0 = W((R() - 0.5f) * it.d * 0.7f, (R() - 0.5f) * it.w * 0.7f, 0f);
                                k.Box(p0 + Vector3.up * 0.4f, new Vector3(2.2f, 0.08f, 0.9f), it.yaw + q * 40f, Deck, LM.Solid, 1f, Deck, LM.Solid);
                                if (q % 3 == 0)
                                {
                                    for (int s = 0; s < 4; s++) k.Beam(p0 + new Vector3(s % 2 == 0 ? -2f : 2f, 0f, s < 2 ? -2f : 2f), p0 + new Vector3(s % 2 == 0 ? -2f : 2f, 2.6f, s < 2 ? -2f : 2f), 0.12f, 0.12f, Deck, LM.Solid);
                                    k.Cylinder(p0 + Vector3.up * 2.6f, 3.2f, 0.1f, 8, Deck, LM.Solid, 1f, DeckD, LM.Roof, 1.1f);
                                }
                            }
                            break;
                        case "tee": Pad(k, o, it.yaw, it.w, it.d, 0.14f, GreenC, LM.Plant); break;
                        case "clubhouse":
                            k.Box(o + Vector3.up * 0.3f, new Vector3(it.d + 18f, 0.6f, it.w + 18f), it.yaw, Deck, LM.Solid, 1f, Pave, LM.Paving);
                            k.Box(o + Vector3.up * 4.6f, new Vector3(it.d, 8f, it.w), it.yaw, White, LM.Solid, 3f, LM.C("#3a3d42"), LM.Roof);
                            k.Box(W(it.d * 0.5f + 0.05f, 0f, 4f), new Vector3(0.1f, 6f, it.w * 0.85f), it.yaw, Glass, LM.Glass, 1f, Glass, LM.Glass);
                            k.Box(o + Vector3.up * 8.9f, new Vector3(it.d + 8f, 0.4f, it.w + 8f), it.yaw, White, LM.Solid, 1f, White, LM.Roof);
                            for (int q = 0; q < 6; q++) k.Cylinder(W(it.d * 0.5f + 6f, -it.w * 0.35f + q * it.w * 0.14f, 0.6f), 1.6f, 0.08f, 8, White, LM.Solid, 1f, Umbrella[q % Umbrella.Length], LM.Solid, 0.9f);   // terrace umbrellas
                            break;
                        case "parking":
                            Pad(k, o, it.yaw, it.w, it.d, 0.12f, Asph, LM.Paving);
                            for (int q = 0; q < 28; q++) if (R() < 0.7f) { var p0 = W((q % 2 == 0 ? -1 : 1) * it.d * 0.25f, (q / 2 - 6.5f) * 5.5f, 0.85f); k.Box(p0, new Vector3(4.4f, 1.4f, 1.9f), it.yaw + 90f, Umbrella[q % Umbrella.Length], LM.Metal, 1f, Umbrella[q % Umbrella.Length], LM.Metal); }
                            break;
                        case "driving_range":
                            Pad(k, o, it.yaw, it.w, it.d, 0.1f, Fairway, LM.Plant);
                            k.Box(W(0f, -it.w * 0.5f + 5f, 2.5f), new Vector3(it.d, 5f, 10f), it.yaw, White, LM.Solid, 2f, LM.C("#3a3d42"), LM.Roof);
                            for (int q = 1; q <= 5; q++) { var m0 = W((q % 2 == 0 ? -1 : 1) * 12f, -it.w * 0.5f + q * 40f, 0f); Disc(k, m0.x, m0.z, 5f, 0.13f, GreenC, LM.Plant); k.Beam(m0, m0 + Vector3.up * 2f, 0.05f, 0.05f, Line, LM.Solid); }
                            foreach (float sg in new[] { -1f, 1f }) for (int q = 0; q < 4; q++) k.Beam(W(sg * it.d * 0.5f, -it.w * 0.5f + q * it.w / 3f, 0f), W(sg * it.d * 0.5f, -it.w * 0.5f + q * it.w / 3f, 16f), 0.25f, 0.25f, Pole, LM.Steel);
                            break;
                        // ---- theme park and water park of Green
                        case "coaster":
                            {
                                Vector3 Tk(float t) { float a = t * Mathf.PI * 2f; var q = W(Mathf.Sin(a * 2f) * it.d * 0.42f, Mathf.Sin(a) * it.w * 0.45f, 0f); q.y += 5f + 24f * Mathf.Pow(0.5f + 0.5f * Mathf.Sin(a * 3f + 1.2f), 1.6f); return q; }
                                var tc = new[] { LM.C("#e0261b"), LM.C("#f2c230") }[(int)Mathf.Abs(it.x) % 2];
                                const int N = 160;
                                for (int i = 0; i < N; i++)
                                {
                                    var p0 = Tk(i / (float)N); var p1 = Tk((i + 1) / (float)N);
                                    k.Beam(p0, p1, 1.4f, 0.5f, tc, LM.Steel);
                                    if (i % 5 == 0) { var g = p0; g.y = H(p0.x, p0.z); k.Beam(g, p0, 0.35f, 0.35f, Steel, LM.Steel); }
                                }
                                k.Box(W(0f, -it.w * 0.45f, 3f), new Vector3(14f, 6f, 30f), it.yaw, White, LM.Solid, 2f, tc, LM.Roof);
                                break;
                            }
                        case "wheel": Wheel(k, o, it.yaw + 90f, 30f); break;
                        case "drop_tower":
                            k.Tube(o, o + Vector3.up * 70f, 2.2f, 1.6f, 12, Steel, LM.Steel);
                            k.Cylinder(o + Vector3.up * 28f, 6f, 3f, 16, LM.C("#2f8fd8"), LM.Solid, 1f, LM.C("#f2c230"), LM.Solid);
                            k.Cylinder(o + Vector3.up * 70f, 3f, 2f, 12, Red, LM.Solid, 1f, Red, LM.Solid, 3f);
                            Disc(k, o.x, o.z, 14f, 0.15f, Pave, LM.Paving);
                            break;
                        case "carousel":
                            Disc(k, o.x, o.z, 22f, 0.15f, Pave, LM.Paving);
                            k.Cylinder(o + Vector3.up * 0.2f, 13f, 1.2f, 24, LM.C("#f2c230"), LM.Solid, 1f, LM.C("#e8d8b8"), LM.Solid);
                            for (int q = 0; q < 12; q++) { float a = q * Mathf.PI / 6f; var p0 = o + new Vector3(Mathf.Cos(a) * 11f, 1.4f, Mathf.Sin(a) * 11f); k.Beam(p0, p0 + Vector3.up * 5f, 0.15f, 0.15f, LM.C("#d4af37"), LM.Metal); }
                            k.Cylinder(o + Vector3.up * 6.4f, 14f, 0.8f, 24, Red, LM.Solid, 1f, White, LM.Roof, 5f);
                            break;
                        case "swing":
                            Disc(k, o.x, o.z, 20f, 0.15f, Pave, LM.Paving);
                            k.Tube(o, o + Vector3.up * 22f, 1.0f, 0.8f, 12, Steel, LM.Steel);
                            k.Cylinder(o + Vector3.up * 20f, 9f, 1.2f, 20, LM.C("#2f8fd8"), LM.Solid, 1f, LM.C("#f2c230"), LM.Roof, 3f);
                            for (int q = 0; q < 16; q++) { float a = q * Mathf.PI / 8f; var p0 = o + new Vector3(Mathf.Cos(a) * 14f, 9f, Mathf.Sin(a) * 14f); k.Beam(p0, o + new Vector3(Mathf.Cos(a) * 8.5f, 20f, Mathf.Sin(a) * 8.5f), 0.05f, 0.05f, Line, LM.Solid); k.Box(p0, new Vector3(0.8f, 0.6f, 0.8f), q * 22.5f, Umbrella[q % Umbrella.Length], LM.Solid, 1f, Umbrella[q % Umbrella.Length], LM.Solid); }
                            break;
                        case "castle":
                            {
                                var pink = LM.C("#e9b8c9"); var blue = LM.C("#3a64b8");
                                k.Box(W(0f, 0f, 9f), new Vector3(46f, 18f, 30f), it.yaw, pink, LM.Solid, 2f, pink, LM.Solid);
                                foreach (float sx in new[] { -1f, 1f }) foreach (float sz in new[] { -1f, 1f }) { var tp = W(sx * 26f, sz * 17f, 0f); k.Cylinder(tp, 5f, 26f, 14, pink, LM.Solid, 2f, blue, LM.Roof, 10f); }
                                k.Cylinder(W(0f, 0f, 18f), 7f, 18f, 16, pink, LM.Solid, 2f, blue, LM.Roof, 14f);
                                Pad(k, W(0f, -it.w * 0.35f, 0f), it.yaw, 24f, 30f, 0.15f, Pave, LM.Paving);
                                break;
                            }
                        case "boats":
                            for (int q = 0; q < 7; q++) { var bp = W((R() - 0.5f) * 60f, (R() - 0.5f) * 30f, 0.25f); k.Box(bp, new Vector3(2.2f, 0.6f, 4f), it.yaw + R() * 180f, Umbrella[q % Umbrella.Length], LM.Solid, 1f, White, LM.Solid); }
                            break;
                        case "waterpark":
                            {
                                // pools, a lazy river, slide towers with coloured slides, loungers and a pavilion
                                Pad(k, o, it.yaw, it.w - 10f, it.d - 10f, 0.08f, Pave, LM.Paving);
                                Oval(k, W(0f, -it.w * 0.15f, 0f), it.yaw, it.d * 0.32f, it.w * 0.22f, 0f, 0.18f, Pool, LM.Water, true);   // wave pool
                                Oval(k, o, it.yaw, it.d * 0.46f, it.w * 0.46f, 6f, 0.18f, Pool, LM.Water);                                   // lazy river
                                Pad(k, W(it.d * 0.2f, it.w * 0.24f, 0f), it.yaw, 30f, 22f, 0.18f, Pool, LM.Water);
                                var slide = new[] { LM.C("#e0261b"), LM.C("#f2c230"), LM.C("#2f8fd8"), LM.C("#5cbf48") };
                                var tw = W(-it.d * 0.22f, it.w * 0.26f, 0f);
                                k.Box(tw + Vector3.up * 9f, new Vector3(10f, 18f, 10f), it.yaw, White, LM.Solid, 2f, LM.C("#2f8fd8"), LM.Roof);
                                for (int s = 0; s < 4; s++)
                                {
                                    Vector3 prev = tw + Vector3.up * (17f - s * 1.5f);
                                    for (int i = 1; i <= 24; i++)
                                    {
                                        float t = i / 24f, a = t * Mathf.PI * (2.4f + s * 0.5f) + s * 1.57f;
                                        var p = tw + r * new Vector3(Mathf.Cos(a) * (8f + t * 14f), 0f, Mathf.Sin(a) * (8f + t * 14f) - t * 25f); p.y = H(p.x, p.z) + Mathf.Lerp(17f - s * 1.5f, 0.6f, t);
                                        k.Tube(prev, p, 0.9f, 0.9f, 8, slide[s], LM.Solid, false); prev = p;
                                    }
                                }
                                for (int q = 0; q < 30; q++) { var lp = W((R() - 0.5f) * it.d * 0.8f, (R() - 0.5f) * it.w * 0.8f, 0.3f); k.Box(lp, new Vector3(0.7f, 0.3f, 1.9f), it.yaw, White, LM.Solid, 1f, White, LM.Solid); }
                                k.Box(W(it.d * 0.35f, -it.w * 0.4f, 3f), new Vector3(20f, 6f, 34f), it.yaw, White, LM.Solid, 2f, Glass, LM.Roof);
                                break;
                            }
                    }
                }
            if (c.trees != null)
                for (int i = 0; i + 1 < c.trees.Length; i += 2) AddTree(new Vector3(c.trees[i], H(c.trees[i], c.trees[i + 1]), c.trees[i + 1]), 7f + R() * 4f, c.trees[i] * 0.013f + c.trees[i + 1] * 0.007f, y0);
            if (c.pines != null)
                for (int i = 0; i + 1 < c.pines.Length; i += 2) AddTree(new Vector3(c.pines[i], H(c.pines[i], c.pines[i + 1]), c.pines[i + 1]), 10f + R() * 5f, c.pines[i] * 0.011f + c.pines[i + 1] * 0.009f, y0);
            foreach (var kv in byYear) Add(kv.Value, "Active recreation · " + kv.Key, kv.Key);
            Debug.Log($"[Alatau] active recreation: {c.greens?.Length ?? 0} greens, {c.fairways?.Length ?? 0} fairway stripes, {nItems} items, {nCourts} courts, {(c.trees?.Length ?? 0) / 2} trees, {(c.pines?.Length ?? 0) / 2} pines");
        }

        /// <summary>A Ferris wheel of radius r standing on two A-frames: the rim, the spokes and the gondolas; its plane turned to yaw.</summary>
        static void Wheel(LandmarkKit k, Vector3 g, float yaw, float r)
        {
            var rot = Quaternion.Euler(0f, yaw, 0f); var hub = g + Vector3.up * (r + 4f); const int N = 24;
            Vector3 Rim(int i, float off) { float a = i * Mathf.PI * 2f / N; return hub + rot * new Vector3(Mathf.Cos(a) * r, Mathf.Sin(a) * r, off); }
            foreach (float off in new[] { -1.2f, 1.2f })
                for (int i = 0; i < N; i++)
                {
                    k.Beam(Rim(i, off), Rim(i + 1, off), 0.35f, 0.35f, White, LM.Steel);
                    if (i % 2 == 0) k.Beam(hub + rot * new Vector3(0f, 0f, off), Rim(i, off), 0.12f, 0.12f, White, LM.Steel);
                }
            for (int i = 0; i < N; i += 2)
            {
                var c = Rim(i, 0f) + Vector3.down * 1.6f;
                k.Box(c, new Vector3(2f, 2.2f, 2f), yaw, Umbrella[(i / 2) % Umbrella.Length], LM.Solid, 1f, White, LM.Roof);
            }
            foreach (float off in new[] { -3.5f, 3.5f })
                foreach (float sx in new[] { -1f, 1f })
                    k.Beam(g + rot * new Vector3(sx * r * 0.55f, 0f, off), hub + rot * new Vector3(0f, 0f, off * 0.4f), 0.6f, 0.6f, White, LM.Steel);
            k.Box(g + Vector3.up * 1.6f, new Vector3(14f, 3.2f, 8f), yaw, White, LM.Solid, 2f, Glass, LM.Roof);
        }

        static bool InTris(float[] t, float x, float z)
        {
            for (int i = 0; i + 5 < t.Length; i += 6)
            {
                float ax = t[i], az = t[i + 1], bx = t[i + 2], bz = t[i + 3], cx = t[i + 4], cz = t[i + 5];
                if (x < Mathf.Min(ax, Mathf.Min(bx, cx)) || x > Mathf.Max(ax, Mathf.Max(bx, cx)) || z < Mathf.Min(az, Mathf.Min(bz, cz)) || z > Mathf.Max(az, Mathf.Max(bz, cz))) continue;
                float d1 = (x - bx) * (az - bz) - (ax - bx) * (z - bz), d2 = (x - cx) * (bz - cz) - (bx - cx) * (z - cz), d3 = (x - ax) * (cz - az) - (cx - ax) * (z - az);
                bool neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0;
                if (!(neg && pos)) return true;
            }
            return false;
        }

        void Add(LandmarkKit k, string name, int year)
        {
            if (k.VertexCount == 0) return;
            var go = new GameObject(name); go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = k.ToMesh(name); var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = mat;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
            parts.Add((go, year));
        }

        void Update()
        {
            if (!built) return;
            DrawTrees();
            int y = TwinState.Year; if (y == lastYear) return; lastYear = y;
            foreach (var (go, yr) in parts) go.SetActive(y < 1 || y >= yr);
        }

        void DrawTrees()
        {
            var ft = FilmTrees.Instance; var cam = Camera.main; if (ft == null || cam == null || treeBatches.Count == 0) return;
            GeometryUtility.CalculateFrustumPlanes(cam, treePlanes); var cp = cam.transform.position;
            foreach (var b in treeBatches)
            {
                float d = Mathf.Sqrt(b.b.SqrDistance(cp)); if (d > 6000f || !GeometryUtility.TestPlanesAABB(treePlanes, b.b)) continue;
                if (!ft.DrawBatch(b.s, b.m, b.m.Length, b.p, d < 1500f, d < 2600f)) break;
            }
        }
    }
}
