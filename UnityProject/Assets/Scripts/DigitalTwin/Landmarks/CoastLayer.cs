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
            var walk = new LandmarkKit(); var trees = new LandmarkKit();
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
                                trees.Tree(new Vector3(q.x, H(q.x, q.y), q.y), 7f + R() * 3f, Leaf, q.x * 0.01f + q.y * 0.013f); nTree++;
                            }
                            nextTree += 14f;
                        }
                        acc += L;
                    }
                }
            Add(walk, "Beaches · promenade", y0); Add(trees, "Beaches · promenade trees", y0);

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
            Debug.Log($"[Alatau] beaches of Green: {c.beaches?.Length ?? 0} beaches, {nUmb} umbrellas, {c.pavilions?.Length ?? 0} pavilions, {c.towers?.Length ?? 0} lifeguard towers, {c.piers?.Length ?? 0} piers ({nBoat} boats), {c.courts?.Length ?? 0} volleyball courts, {nTree} promenade trees");
        }

        // ================================================================== active recreation (recreation.json, tools/map/export/recreation.py)
        [System.Serializable] class LineJ { public float[] p; public float w; public int y; public string k; }
        [System.Serializable] class CircJ { public float x, z, r; public int y; }
        [System.Serializable] class ItemJ { public string k; public float x, z, yaw, w, d; public int y; }
        [System.Serializable] class RecJ { public LineJ[] fairways, paths; public CircJ[] greens, bunkers; public TriJ[] ponds; public ItemJ[] items; public float[] trees; }
        static readonly Color32 Fairway = LM.C("#7fae4f"), GreenC = LM.C("#5cbf48"), Rough = LM.C("#6a9343"), Court = LM.C("#2f6f9e"), CourtG = LM.C("#3f8a4c"),
            Clay = LM.C("#c0603a"), Line = LM.C("#f4f4f0"), Rubber = LM.C("#c4473a"), Conc = LM.C("#bdb8ae"), Asph = LM.C("#4a4b4d"), Track = LM.C("#b84a35"),
            Fence = LM.C("#2b4a3a"), Water = LM.C("#3d7fa8"), Bike = LM.C("#b46a55");

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

        void BuildRecreation()
        {
            var ta = Resources.Load<TextAsset>("Landmarks/recreation"); if (ta == null) return;
            RecJ c; try { c = JsonUtility.FromJson<RecJ>(ta.text); } catch { return; }
            if (c == null) return;
            var rnd = new System.Random(2036); float R() => (float)rnd.NextDouble();
            float H(float x, float z) => CityGround.HeightAt(x, z);
            var byYear = new Dictionary<int, LandmarkKit>(); var treesK = new Dictionary<int, LandmarkKit>();
            LandmarkKit K(int y) { if (!byYear.TryGetValue(y, out var k)) byYear[y] = k = new LandmarkKit(); return k; }
            LandmarkKit T(int y) { if (!treesK.TryGetValue(y, out var k)) treesK[y] = k = new LandmarkKit(); return k; }
            int y0 = 2035, nCourts = 0;
            if (c.fairways != null) foreach (var f in c.fairways) { Ribbon(K(f.y), f.p, f.w * 0.5f, 0.08f, Fairway, LM.Plant); y0 = f.y; }
            if (c.greens != null)
                foreach (var g in c.greens)
                {
                    var k = K(g.y); Disc(k, g.x, g.z, g.r, 0.1f, GreenC, LM.Plant);
                    float gy = H(g.x, g.z); k.Beam(new Vector3(g.x, gy, g.z), new Vector3(g.x, gy + 2.4f, g.z), 0.05f, 0.05f, Line, LM.Solid);
                    k.Box(new Vector3(g.x + 0.35f, gy + 2.15f, g.z), new Vector3(0.7f, 0.45f, 0.03f), 0f, Red, LM.Solid, 1f, Red, LM.Solid);
                }
            if (c.bunkers != null) foreach (var b in c.bunkers) Disc(K(b.y), b.x, b.z, b.r, 0.11f, Sand, LM.Solid);
            if (c.ponds != null)
                foreach (var p in c.ponds)
                {
                    if (p.t == null) continue; var k = K(p.y);
                    for (int i = 0; i + 5 < p.t.Length; i += 6)
                    {
                        Vector3 A(int q) => new Vector3(p.t[i + 2 * q], H(p.t[i + 2 * q], p.t[i + 2 * q + 1]) + 0.12f, p.t[i + 2 * q + 1]);
                        Vector3 p0 = A(0), p1 = A(1), p2 = A(2);
                        if (Vector3.Cross(p1 - p0, p2 - p0).y < 0f) { var t = p1; p1 = p2; p2 = t; }
                        k.Tri(p0, p1, p2, Vector3.up, Water, LM.Water, 1f, new Vector2(p0.x, p0.z), new Vector2(p1.x, p1.z), new Vector2(p2.x, p2.z));
                    }
                }
            if (c.paths != null) foreach (var p in c.paths) Ribbon(K(p.y), p.p, p.w * 0.5f, 0.1f, p.k == "bike" ? Bike : Pave, LM.Paving);
            if (c.items != null)
                foreach (var it in c.items)
                {
                    var k = K(it.y); var r = Quaternion.Euler(0f, it.yaw, 0f); var o = new Vector3(it.x, H(it.x, it.z), it.z);
                    Vector3 W(float x, float z, float up) { var q = o + r * new Vector3(x, 0f, z); q.y = H(q.x, q.z) + up; return q; }
                    void Courts(float cw, float cl, float gap, Color32 surf, Color32 outer, bool glass)
                    {
                        int nx = Mathf.Max(1, Mathf.FloorToInt((it.d - 10f) / (cw + gap))), nz = Mathf.Max(1, Mathf.FloorToInt((it.w - 10f) / (cl + gap)));
                        for (int i = 0; i < nx; i++)
                            for (int j = 0; j < nz; j++)
                            {
                                float cx = (i - (nx - 1) * 0.5f) * (cw + gap), cz = (j - (nz - 1) * 0.5f) * (cl + gap); var cc = W(cx, cz, 0f);
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
                    switch (it.k)
                    {
                        case "tennis": Courts(11f, 24f, 6f, R() < 0.5f ? Court : Clay, CourtG, false); k.Box(W(0f, -it.w * 0.5f + 8f, 3f), new Vector3(30f, 6f, 10f), it.yaw, White, LM.Solid, 2f, White, LM.Roof); break;
                        case "padel": Courts(10f, 20f, 4f, Court, CourtG, true); break;
                        case "basketball": Courts(15f, 28f, 6f, Clay, Conc, false); break;
                        case "football":
                            {
                                float pw = Mathf.Min(68f, it.d - 16f), pl = Mathf.Min(105f, it.w - 16f); var cc = W(0f, 0f, 0f);
                                Pad(k, cc, it.yaw, pl + 6f, pw + 6f, 0.12f, Rough, LM.Plant); Pad(k, cc, it.yaw, pl, pw, 0.15f, CourtG, LM.Plant);
                                foreach (float sg in new[] { -1f, 1f })
                                {
                                    k.Box(W(sg * pw * 0.5f, 0f, 0.17f), new Vector3(0.12f, 0.02f, pl), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                    k.Box(W(0f, sg * pl * 0.5f, 0.17f), new Vector3(pw, 0.02f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                    k.Box(W(0f, sg * pl * 0.5f, 1.2f), new Vector3(7.3f, 2.4f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                    k.Box(W(sg * (pw * 0.5f + 9f), 0f, 1.5f), new Vector3(5f, 3f, pl * 0.6f), it.yaw, Conc, LM.Solid, 1f, LM.C("#2f5f8e"), LM.Solid);   // stands
                                }
                                k.Box(W(0f, 0f, 0.17f), new Vector3(pw, 0.02f, 0.12f), it.yaw, Line, LM.Solid, 1f, Line, LM.Solid);
                                for (int q = 0; q < 4; q++) { float sx = q % 2 == 0 ? -1 : 1, sz = q < 2 ? -1 : 1; var m0 = W(sx * (pw * 0.5f + 3f), sz * (pl * 0.5f + 3f), 0f); k.Beam(m0, m0 + Vector3.up * 18f, 0.3f, 0.3f, Pole, LM.Steel); }
                                break;
                            }
                        case "stadium":
                            {
                                var cc = W(0f, 0f, 0f); float tw = it.d - 12f, tl = it.w - 12f;
                                Pad(k, cc, it.yaw, tl, tw, 0.12f, Track, LM.Solid); Pad(k, cc, it.yaw, tl - 18f, tw - 18f, 0.15f, CourtG, LM.Plant);
                                foreach (float sg in new[] { -1f, 1f }) k.Box(W(sg * (tw * 0.5f + 5f), 0f, 4f), new Vector3(8f, 8f, tl * 0.7f), it.yaw, Conc, LM.Solid, 2f, White, LM.Roof);
                                break;
                            }
                        case "skate":
                            {
                                Pad(k, W(0f, 0f, 0f), it.yaw, it.w * 0.55f, it.d * 0.6f, 0.15f, Conc, LM.Paving);
                                for (int q = 0; q < 5; q++) k.Box(W((q - 2) * 12f, (q % 2 == 0 ? -1 : 1) * 14f, 0.8f), new Vector3(8f, 1.6f, 6f), it.yaw + q * 25f, Conc, LM.Solid, 1f, LM.C("#9e9a92"), LM.Solid);
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
                            for (int q = 0; q < 14; q++) T(it.y).Tree(W((R() - 0.5f) * it.d * 0.9f, (R() - 0.5f) * it.w * 0.9f, 0f), 9f + R() * 4f, Leaf, q + it.x);
                            break;
                        case "playground":
                            Pad(k, W(0f, 0f, 0f), it.yaw, it.w * 0.45f, it.d * 0.55f, 0.15f, Rubber, LM.Solid);
                            for (int q = 0; q < 8; q++)
                            {
                                var p0 = W((R() - 0.5f) * it.d * 0.45f, (R() - 0.5f) * it.w * 0.35f, 0f); var col = Umbrella[q % Umbrella.Length];
                                k.Box(p0 + Vector3.up * 1.2f, new Vector3(3f + R() * 3f, 2.4f, 3f + R() * 2f), it.yaw + q * 30f, col, LM.Solid, 1f, col, LM.Solid);
                            }
                            break;
                        case "picnic":
                            for (int q = 0; q < 6; q++)
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
                        case "tee": Pad(k, o, it.yaw, it.w, it.d, 0.12f, GreenC, LM.Plant); break;
                        case "clubhouse":
                            k.Box(o + Vector3.up * 0.3f, new Vector3(it.d + 16f, 0.6f, it.w + 16f), it.yaw, Deck, LM.Solid, 1f, Pave, LM.Paving);
                            k.Box(o + Vector3.up * 4.6f, new Vector3(it.d, 8f, it.w), it.yaw, White, LM.Solid, 3f, LM.C("#3a3d42"), LM.Roof);
                            k.Box(W(it.d * 0.5f + 0.05f, 0f, 4f), new Vector3(0.1f, 6f, it.w * 0.85f), it.yaw, Glass, LM.Glass, 1f, Glass, LM.Glass);
                            k.Box(o + Vector3.up * 8.9f, new Vector3(it.d + 6f, 0.4f, it.w + 6f), it.yaw, White, LM.Solid, 1f, White, LM.Roof);
                            break;
                        case "parking":
                            Pad(k, o, it.yaw, it.w, it.d, 0.12f, Asph, LM.Paving);
                            for (int q = 0; q < 24; q++) if (R() < 0.7f) { var p0 = W((q % 2 == 0 ? -1 : 1) * it.d * 0.25f, (q / 2 - 5.5f) * 5.5f, 0.85f); k.Box(p0, new Vector3(4.4f, 1.4f, 1.9f), it.yaw + 90f, Umbrella[q % Umbrella.Length], LM.Metal, 1f, Umbrella[q % Umbrella.Length], LM.Metal); }
                            break;
                        case "driving_range":
                            Pad(k, o, it.yaw, it.w, it.d, 0.1f, Fairway, LM.Plant);
                            k.Box(W(0f, -it.w * 0.5f + 5f, 2.5f), new Vector3(it.d, 5f, 10f), it.yaw, White, LM.Solid, 2f, LM.C("#3a3d42"), LM.Roof);
                            for (int q = 1; q <= 4; q++) { var m0 = W(0f, -it.w * 0.5f + q * 38f, 0f); Disc(k, m0.x, m0.z, 4f, 0.13f, Line, LM.Solid); }
                            break;
                    }
                }
            if (c.trees != null)
                for (int i = 0; i + 1 < c.trees.Length; i += 2) T(y0).Tree(new Vector3(c.trees[i], H(c.trees[i], c.trees[i + 1]), c.trees[i + 1]), 7f + R() * 4f, Leaf, c.trees[i] * 0.013f + c.trees[i + 1] * 0.007f);
            foreach (var kv in byYear) Add(kv.Value, "Active recreation · " + kv.Key, kv.Key);
            foreach (var kv in treesK) Add(kv.Value, "Active recreation · trees " + kv.Key, kv.Key);
            Debug.Log($"[Alatau] active recreation: {c.fairways?.Length ?? 0} golf holes, {c.items?.Length ?? 0} sites, {nCourts} courts, {(c.trees?.Length ?? 0) / 2} trees");
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
            int y = TwinState.Year; if (y == lastYear) return; lastYear = y;
            foreach (var (go, yr) in parts) go.SetActive(y < 1 || y >= yr);
        }
    }
}
