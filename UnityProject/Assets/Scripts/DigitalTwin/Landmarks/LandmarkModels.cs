using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Procedural models of the landmarks. Local frame: x = long side, z = across, y = up from the base (0 = ground).
    /// Proportions follow the published figures (heights, areas, capacities); details are illustrative, not design documentation.</summary>
    /// <summary>The order in which each building of a complex is put up: stage windows in the progress of the building (0 … 1), shared
    /// by the model (LandmarkKit.Win: what rises when) and by the construction monitoring (the works of the schedule).</summary>
    public static class Wbs
    {
        static Vector2 V(float a, float b) => new Vector2(a, b);
        // Iconic Complex · hotel T2: excavation and raft, frame stepping up with the core, terraces (waterproofing and gardens), cascade
        public static readonly Vector2 T2Pit = V(0f, 0.08f), T2Frame = V(0.06f, 0.92f), T2Terr = V(0.55f, 0.88f), T2Cascade = V(0.62f, 0.90f);
        // retail blocks: the high block first, the low one a little later, the roof pool, the roof garden
        public static readonly Vector2 RHigh = V(0.08f, 0.85f), RLow = V(0.15f, 0.88f), RPool = V(0.70f, 0.92f), RGarden = V(0.75f, 0.95f);
        // grounds: the promenade, the allée with the fountain, the parterre and the square, trees and lamps
        public static readonly Vector2 GProm = V(0.15f, 0.65f), GAllee = V(0.30f, 0.80f), GSquare = V(0.35f, 0.85f), GTrees = V(0.65f, 1f);
        // KAIST · main hall: apron, columns of the lobby, transfer slab at +10 m, the steel box, its white grid, roof and pyramids,
        // the glazed lobby, terrace with stair and ramp, the plaza with the pool
        public static readonly Vector2 MApron = V(0f, 1f), MCols = V(0.10f, 0.30f), MSlab = V(0.26f, 0.40f), MBox = V(0.36f, 0.86f), MGrid = V(0.50f, 0.84f),
            MRoof = V(0.60f, 0.78f), MLobby = V(0.62f, 0.90f), MTerr = V(0.70f, 0.90f), MPlaza = V(0.86f, 1f);
        // laboratories: the spine, then wings A, B, C one after another, the courts last
        public static readonly Vector2 LSpine = V(0.06f, 0.42f), LCourts = V(0.85f, 1f);
        public static readonly Vector2[] LWing = { V(0.22f, 0.55f), V(0.34f, 0.68f), V(0.46f, 0.80f) };
        // north block: four sectors (захватки) along the arc from the west, then the green roof
        public static readonly Vector2[] NSector = { V(0.06f, 0.56f), V(0.16f, 0.66f), V(0.26f, 0.76f), V(0.36f, 0.86f) };
        public static readonly Vector2 NRoof = V(0.78f, 0.94f);
        // sports: the stand, its canopy, the running track, the pitch
        public static readonly Vector2 SStand = V(0.15f, 0.55f), SCanopy = V(0.45f, 0.70f), STrack = V(0.50f, 0.85f), SPitch = V(0.70f, 1f);
        // the park: ground and lawn, the lake and the island, paths and the bridge, lamps and fountains, the trees
        public static readonly Vector2 PGround = V(-0.02f, 1f), PLake = V(0.10f, 0.55f), PPaths = V(0.35f, 0.80f), PLamps = V(0.60f, 0.95f), PTrees = V(0.70f, 1f);
        public static readonly Vector2 Apron = V(0f, 1f);
    }

    public static partial class LandmarkModels
    {
        static void W(LandmarkKit k, Vector2 w, float y0, float y1) => k.Win(w.x, w.y, y0, y1);
        // palette
        static readonly Color32 White = LM.C("#ecebe6"), Stone = LM.C("#d9d4ca"), Pave = LM.C("#c8c2b6"), PaveDark = LM.C("#a9a397"), Concrete = LM.C("#bcb7ae"),
            GlassBlue = LM.C("#1f3549"), GlassTeal = LM.C("#1d3b3d"), GlassWarm = LM.C("#2b2f33"), GlassDark = LM.C("#151d26"),
            MetalW = LM.C("#e3e5e7"), MetalG = LM.C("#b9bdc2"), MetalD = LM.C("#6c7279"), Steel = LM.C("#4d535a"), Roof = LM.C("#9c9c98"),
            Grass = LM.C("#5f7f47"), GrassDark = LM.C("#4b6a39"), Leaf = LM.C("#557a3e"), Leaf2 = LM.C("#6a8a45"), Water = LM.C("#1e3446"),
            Warm = LM.C("#ffd9a0"), Red = LM.C("#e0261b"), Orange = LM.C("#f39a2b"), Asph = LM.C("#5d5d5c"), Gravel = LM.C("#9b958a");

        public static Mesh Build(string model, float seed)
        {
            var k = new LandmarkKit();
            switch (model)
            {
                case "iconic": Iconic(k); break;
                case "hotel_l7": HotelL7(k); break;
                case "food_pepsico": FoodPlant(k, LM.C("#0a4fa3"), true); break;
                case "food_mars": FoodPlant(k, LM.C("#1d3f8f"), false); break;
                case "paper": PaperMill(k); break;
                case "packaging": Packaging(k); break;
                case "logistics_griffin": Logistics(k, 2, 300f, 110f); break;
                case "logistics_gtrans": Logistics(k, 1, 210f, 90f); break;
                case "rail_terminal": RailTerminal(k); break;
                case "substation": Substation(k, seed); break;
                case "power": PowerPlant(k); break;
                case "campus": if (QTwinData.Kaist() != null) KaistCampus(k); else Campus(k); break;
                case "hospital": Hospital(k); break;
                case "kpark": KPark(k); break;
                case "marina": Marina(k); break;
                case "airport": Airport(k); break;
                default: k.Box(new Vector3(0, 10, 0), new Vector3(40, 20, 40), 0, White, LM.Solid, 3.5f, Roof, LM.Roof); break;
            }
            return k.ToMesh("Landmark " + model);
        }

        // ------------------------------------------------------------------ helpers
        static void Pad(LandmarkKit k, float w, float d, float r, Color32 top, int mat = LM.Paving)
        {
            // a plinth that is buried in the slope: the model always stands on level ground
            k.Prism(LandmarkKit.RoundRect(0, 0, w, d, r, 3), -16f, 0.3f, PaveDark, LM.Solid, 3f, top, mat);
        }
        static void Lawn(LandmarkKit k, float cx, float cz, float w, float d, float r = 4f) => k.Prism(LandmarkKit.RoundRect(cx, cz, w, d, r, 3), 0.3f, 0.55f, GrassDark, LM.Solid, 3f, Grass, LM.Plant);
        static void Trees(LandmarkKit k, float x0, float z0, float x1, float z1, float step, float h, float seed)
        {
            int i = 0;
            for (float x = x0; x <= x1 + 0.01f; x += step) for (float z = z0; z <= z1 + 0.01f; z += step)
            { float j = Mathf.Sin((x * 12.9898f + z * 78.233f + seed) * 0.1f) * 0.5f + 0.5f; k.Tree(new Vector3(x, 0.4f, z), h * (0.8f + 0.4f * j), (i++ & 1) == 0 ? Leaf : Leaf2, j + seed); }
        }
        static void Gable(LandmarkKit k, float cx, float cz, float w, float d, float eave, float rise, Color32 wall, int wallMat, Color32 roof, float yaw = 0f)
        {
            var fp = LandmarkKit.Rect(cx, cz, w, d, yaw);
            k.Prism(fp, 0.3f, eave, wall, wallMat, 4f, roof, -1);
            var ridge = LandmarkKit.Rect(cx, cz, w, 0.6f, yaw);
            k.Loft(fp, eave, ridge, eave + rise, roof, LM.Metal, 4f);
            k.Cap(ridge, eave + rise, true, roof, LM.Metal);
        }
        static void Truck(LandmarkKit k, Vector3 p, float yaw, Color32 trailer)
        {
            var r = Quaternion.Euler(0, yaw, 0);
            k.Box(p + r * new Vector3(-1.6f, 2.3f, 0), new Vector3(13.6f, 3.0f, 2.5f), yaw, trailer, LM.Metal, 3f, trailer, LM.Roof);
            k.Box(p + r * new Vector3(6.2f, 1.9f, 0), new Vector3(2.4f, 2.6f, 2.4f), yaw, White, LM.Solid, 3f, White, LM.Roof);
        }
        static void Cars(LandmarkKit k, float x0, float z0, int nx, int nz, float seed)
        {
            Color32[] cols = { LM.C("#e7e7e7"), LM.C("#2b2b2b"), LM.C("#7d8590"), LM.C("#9b2a24"), LM.C("#2f4f7a"), LM.C("#c9c9c9") };
            for (int i = 0; i < nx; i++) for (int j = 0; j < nz; j++)
            {
                float h = Mathf.Abs(Mathf.Sin((i * 7.1f + j * 13.3f + seed) * 1.7f)); if (h < 0.25f) continue;
                k.Box(new Vector3(x0 + i * 2.7f, 1.0f, z0 + j * 6.5f), new Vector3(1.9f, 1.4f, 4.4f), 0, cols[(int)(h * 97) % cols.Length], LM.Solid, 3f, cols[(int)(h * 53) % cols.Length], LM.Roof);
            }
        }
        static void Silos(LandmarkKit k, float x0, float z0, int n, float r, float h, Color32 col)
        {
            for (int i = 0; i < n; i++) k.Cylinder(new Vector3(x0 + i * (r * 2.3f), 0.3f, z0), r, h, 16, col, LM.Metal, 4f, col, LM.Metal, r * 0.5f);
        }

        // ------------------------------------------------------------------ Iconic Complex: the BIM model of its QTwin page
        // (QTwinData.Bim, tools/build_gate_district.py) — T1, 272 m: a tapering tower of warm glass under a diamond lattice with
        // champagne slab edges, golden fins in a V on its face toward the hotel and a lit crown, on a stepped podium; T2, 80 m: the stepped
        // "pyramid" of the hotel with planted terraces and its own golden V on the face toward the tower — the two make the "gate";
        // two wedge pavilions whose planted roofs slope up to 32 and 22 m over shop fronts and a timber soffit, a pool on the east
        // terrace, the plaza with its amphitheatre steps, parasols and gardens. Every surface keeps the page's tag (LM.QTwin).
        static readonly Color32 Gold = LM.C("#cf9f45"), CrownGlass = LM.C("#c99c55"), Fascia = LM.C("#efe9dc"), PoolWater = LM.C("#2f8fb0"),
            LatticeGold = LM.C("#e0b06a"), PlateWhite = LM.C("#f1e9d8"), Sand = LM.C("#e3d6bf"), SandDark = LM.C("#cbbda4"),
            GoldLight = LM.C("#f2cf7f"), WarmGlass = LM.C("#4d3d2a"), Timber = LM.C("#b9853f"), PoolTile = LM.C("#7fb8c4");
        const float PodiumTop = 18f;
        /// <summary>The top of T1 (its crown) and of the hotel T2.</summary>
        public const float IconicApex = 271f, PyramidTop = 80.8f;
        /// <summary>The top of the hotel T2 (local x, z): the camera of the monitoring looks down from it.</summary>
        public static Vector2 T2Apex => new Vector2(-4f, 42f);
        /// <summary>Height of the top of the complex over a local point (a roof, a terrace, the ground of the plot).</summary>
        public static float RoofAt(float x, float z) => Mathf.Max(QTwinData.TopAt(x, z), 0.3f);
        static void Iconic(LandmarkKit k)
        {
            var m = QTwinData.Bim();
            if (m == null) { k.Prism(LandmarkKit.Rect(0f, 0f, 270f, 200f), -2f, 0.3f, SandDark, LM.Solid, 3f, Sand, LM.Paving); return; }
            // parts of the model = the buildings of LandmarkData's Iconic Complex, each staged on its own dates:
            // 1 T1, 2 T2, 3 the east pavilion, 4 the west pavilion, 5 the plaza (0 the plot); the plaza is laid on its own works
            // (IconicPlaza: an earth site first, paving, lawns and the square in their windows, cut by the buildings' footprints)
            IconicPlaza.Add(k, m);
            // the trees of the plaza on the page, planted with it (last of its works)
            var d = QTwinData.Gate();
            if (d != null)
            {
                k.Part = 5; W(k, Wbs.GTrees, 0f, 12f);
                IconicPlaza.Trees(k, d.Trees, Leaf, Leaf2);          // each fitted to the model (crowns clear of roofs and walls), grates on stone
                k.Part = 0; k.NoWin();
            }
        }
        /// <summary>KAIST Kazakhstan as on its QTwin monitoring page (QTwinData.Kaist, tools/build_kaist.py): B1, the library tower of teal
        /// glass with white bands and a glass pyramid; the main hall, a blue glass box with a white grid lifted on columns over a glazed lobby,
        /// three pyramids on its roof; the laboratories, a spine and three stepped wings with green roofs; the north block in an arc; the sports
        /// core with its track and stand; the park with the lake, the island, the alleys and the lawns. Parts as LandmarkData's KAIST.</summary>
        static void KaistCampus(LandmarkKit k)
        {
            var c = QTwinData.Kaist(); var m = c.Mesh;
            k.Indexed(m.P, m.N, m.U, m.Tag, m.Part, m.I, LM.QTwin, new Color32(255, 255, 255, 255));
            // the trees of the park, planted with it (before the buildings, so the campus is green from the start)
            k.Part = 6;
            for (int i = 0; i < c.Trees.Length; i++)
            {
                var t = c.Trees[i];
                k.Tree(new Vector3(t.x, t.y, t.z), 10.5f * t.w, (i & 1) == 0 ? Leaf : Leaf2, i * 0.37f);
            }
            k.Part = 0;
        }
        /// <summary>A stone path on the podium roof from a to b.</summary>
        static void RoofPath(LandmarkKit k, Vector2 a, Vector2 b, float w)
        {
            var d = (b - a); float L = d.magnitude; if (L < 1f) return;
            float yaw = -Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg; var m = (a + b) * 0.5f;
            k.Prism(LandmarkKit.Rect(m.x, m.y, L, w, yaw), PodiumTop + 0.3f, PodiumTop + 0.5f, SandDark, LM.Solid, 1f, Sand, LM.Paving);
        }
        /// <summary>A point on a stadium outline (w × d, corner radius r) at angle a from its centre.</summary>
        static Vector2 Stadium(float a, float w, float d, float r)
        {
            var dir = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
            float lo = 0f, hi = Mathf.Max(w, d);
            for (int it = 0; it < 24; it++) { float m = (lo + hi) * 0.5f; if (InStadium(dir * m, w, d, r)) lo = m; else hi = m; }
            return dir * lo;
        }
        static bool InStadium(Vector2 p, float w, float d, float r)
        {
            float hx = w * 0.5f - r, hz = d * 0.5f - r;
            float qx = Mathf.Max(Mathf.Abs(p.x) - hx, 0f), qz = Mathf.Max(Mathf.Abs(p.y) - hz, 0f);
            return qx * qx + qz * qz <= r * r;
        }
        /// <summary>A convex polygon moved outward (d &gt; 0) or inward (d &lt; 0) by d metres (counter-clockwise or clockwise alike).</summary>
        static List<Vector2> Offset(List<Vector2> poly, float d)
        {
            int n = poly.Count; float area = 0f;
            for (int i = 0; i < n; i++) { var u = poly[i]; var v = poly[(i + 1) % n]; area += u.x * v.y - v.x * u.y; }
            float s = area > 0f ? 1f : -1f;                      // outward normal of edge (u→v) = (dy, −dx) for clockwise, (−dy, dx)·… for ccw
            var o = new List<Vector2>(n);
            for (int i = 0; i < n; i++)
            {
                var p = poly[(i + n - 1) % n]; var c = poly[i]; var q = poly[(i + 1) % n];
                var e0 = (c - p).normalized; var e1 = (q - c).normalized;
                var n0 = new Vector2(e0.y, -e0.x) * s; var n1 = new Vector2(e1.y, -e1.x) * s;
                var bis = (n0 + n1); float cos = Vector2.Dot(bis.normalized, n0);
                o.Add(c + bis.normalized * (d / Mathf.Max(cos, 0.2f)));
            }
            return o;
        }
        /// <summary>The part of a convex polygon east (keepEast) or west of the line x = c.</summary>
        static List<Vector2> ClipX(List<Vector2> poly, float c, bool keepEast)
        {
            var o = new List<Vector2>();
            for (int i = 0; i < poly.Count; i++)
            {
                var a = poly[i]; var b = poly[(i + 1) % poly.Count];
                bool ia = keepEast ? a.x >= c : a.x <= c, ib = keepEast ? b.x >= c : b.x <= c;
                if (ia) o.Add(a);
                if (ia != ib) { float t = (c - a.x) / (b.x - a.x); o.Add(new Vector2(c, a.y + (b.y - a.y) * t)); }
            }
            return o;
        }
        static bool Inside(List<Vector2> poly, Vector2 p, float margin)
        {
            int n = poly.Count; float area = 0f;
            for (int i = 0; i < n; i++) { var u = poly[i]; var v = poly[(i + 1) % n]; area += u.x * v.y - v.x * u.y; }
            float s = area > 0f ? 1f : -1f;
            for (int i = 0; i < n; i++)
            {
                var a = poly[i]; var b = poly[(i + 1) % n]; var e = (b - a).normalized;
                float side = (e.x * (p.y - a.y) - e.y * (p.x - a.x)) * s;     // > 0 inside for both windings
                if (side < margin) return false;
            }
            return true;
        }
        /// <summary>A podium block on the rectangle (x0, z0)–(x1, z1): glass walls, a golden fascia, a flat paved roof terrace with a glass parapet.</summary>
        static void Podium(LandmarkKit k, float x0, float z0, float x1, float z1, float h)
        {
            var r = LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, x1 - x0, z1 - z0);
            k.Prism(r, 0.3f, h - 1.6f, WarmGlass, LM.Glass, 4.3f, Fascia, -1);
            k.Prism(LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, x1 - x0 + 0.8f, z1 - z0 + 0.8f), h - 1.6f, h, Gold, LM.Solid, 1.6f, Stone, LM.Paving);
            float cx = (x0 + x1) * 0.5f, cz = (z0 + z1) * 0.5f, w = x1 - x0, d = z1 - z0;
            foreach (var (c, sz) in new[] { (new Vector3(cx, h + 0.55f, z0 + 0.3f), new Vector3(w, 1.1f, 0.12f)), (new Vector3(cx, h + 0.55f, z1 - 0.3f), new Vector3(w, 1.1f, 0.12f)),
                                           (new Vector3(x0 + 0.3f, h + 0.55f, cz), new Vector3(0.12f, 1.1f, d)), (new Vector3(x1 - 0.3f, h + 0.55f, cz), new Vector3(0.12f, 1.1f, d)) })
                k.Box(c, sz, 0f, GlassBlue, LM.Glass, 1.1f, Fascia, LM.Solid);
        }
        /// <summary>A pool on a roof at height y: timber deck, stone coping, the water, sun loungers with parasols along the long sides, planters at the ends.
        /// yaw 0: the pool runs along x; 90: along z.</summary>
        static void RoofPool(LandmarkKit k, float cx, float cz, float lx, float lz, float y, float yaw)
        {
            k.Prism(LandmarkKit.Rect(cx, cz, lx + 16f, lz + 14f), y, y + 0.14f, Timber, LM.Solid, 1f, Timber, LM.Paving);
            k.Prism(LandmarkKit.Rect(cx, cz, lx, lz), y + 0.14f, y + 0.42f, PoolTile, LM.Solid, 1f, PoolWater, LM.Water);
            foreach (var (c, sz) in new[] { (new Vector3(cx, y + 0.3f, cz - lz * 0.5f - 0.5f), new Vector3(lx + 2f, 0.32f, 1f)), (new Vector3(cx, y + 0.3f, cz + lz * 0.5f + 0.5f), new Vector3(lx + 2f, 0.32f, 1f)),
                                           (new Vector3(cx - lx * 0.5f - 0.5f, y + 0.3f, cz), new Vector3(1f, 0.32f, lz)), (new Vector3(cx + lx * 0.5f + 0.5f, y + 0.3f, cz), new Vector3(1f, 0.32f, lz)) })
                k.Box(c, sz, 0f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            bool alongX = yaw < 45f; float len = alongX ? lx : lz, side = (alongX ? lz : lx) * 0.5f + 3.6f;
            for (float t = -len * 0.5f + 3f; t <= len * 0.5f - 3f; t += 4.2f)
                foreach (float sgn in new[] { -1f, 1f })
                {
                    var p = alongX ? new Vector3(cx + t, y, cz + sgn * side) : new Vector3(cx + sgn * side, y, cz + t);
                    var sz = alongX ? new Vector3(0.75f, 0.32f, 1.9f) : new Vector3(1.9f, 0.32f, 0.75f);
                    k.Box(p + Vector3.up * 0.3f, sz, 0f, White, LM.Solid, 1f, White, LM.Solid);
                    k.Box(p + Vector3.up * 0.3f + (alongX ? new Vector3(0.95f, 0f, 0f) : new Vector3(0f, 0f, 0.95f)), sz, 0f, White, LM.Solid, 1f, White, LM.Solid);
                    var u = p + (alongX ? new Vector3(0.47f, 0f, sgn * 1.6f) : new Vector3(sgn * 1.6f, 0f, 0.47f));
                    k.Beam(u + Vector3.up * 0.14f, u + Vector3.up * 2.4f, 0.08f, 0.08f, MetalG, LM.Metal);
                    k.Cylinder(u + Vector3.up * 2.3f, 1.5f, 0.1f, 10, Fascia, LM.Solid, 1f, Fascia, LM.Solid, 0.35f);
                }
            foreach (float e in new[] { -1f, 1f })
                for (int i = -1; i <= 1; i++)
                {
                    var c = alongX ? new Vector3(cx + e * (lx * 0.5f + 5.5f), y, cz + i * lz * 0.32f) : new Vector3(cx + i * lx * 0.32f, y, cz + e * (lz * 0.5f + 5.5f));
                    k.Box(c + Vector3.up * 0.5f, new Vector3(2.2f, 0.8f, 2.2f), 0f, Stone, LM.Solid, 1f, Grass, LM.Plant);
                    k.Tree(c + Vector3.up * 0.9f, 4.2f, Leaf2, c.x * 0.13f + c.z * 0.07f);
                }
        }
        /// <summary>A planted roof terrace: lawn beds in timber edging, paths between them, small trees in rows.</summary>
        static void RoofGarden(LandmarkKit k, float cx, float cz, float lx, float lz, float y)
        {
            for (int i = -1; i <= 1; i += 2)
                for (int j = -1; j <= 1; j += 2)
                {
                    float bx = cx + i * lx * 0.24f, bz = cz + j * lz * 0.24f;
                    k.Prism(LandmarkKit.RoundRect(bx, bz, lx * 0.38f, lz * 0.38f, 1.5f, 2), y, y + 0.55f, Timber, LM.Solid, 1f, Grass, LM.Plant);
                    for (float t = -lz * 0.15f; t <= lz * 0.15f + 0.01f; t += lz * 0.15f) k.Tree(new Vector3(bx, y + 0.55f, bz + t), 4.6f, Leaf, bx * 0.11f + t);
                }
            for (int i = -1; i <= 1; i += 2) Bench(k, cx, cz + i * 3f, 0f, y);
        }
        /// <summary>A tree in a square grate (the clipped trees of the alleys): same height and shape along a row.</summary>
        static void Planted(LandmarkKit k, float x, float z, float h, int row)
        {
            k.Box(new Vector3(x, 0.34f, z), new Vector3(1.8f, 0.08f, 1.8f), 0f, Steel, LM.Solid, 1f, Steel, LM.Paving);
            k.Tree(new Vector3(x, 0.38f, z), h, (row & 1) == 0 ? Leaf : Leaf2, row * 1.7f);
        }
        static void Bench(LandmarkKit k, float x, float z, float yaw, float y = 0.3f)
        {
            k.Box(new Vector3(x, y + 0.42f, z), new Vector3(2.2f, 0.12f, 0.6f), yaw, Timber, LM.Solid, 1f, Timber, LM.Solid);
            k.Box(new Vector3(x, y + 0.2f, z), new Vector3(1.8f, 0.4f, 0.4f), yaw, Steel, LM.Solid, 1f, Steel, LM.Solid);
        }
        /// <summary>The promenade around the plot: a 12 m paved band along the edge with two rows of clipped trees in grates, lamps between
        /// the outer trees, benches, and a clipped hedge on the inner side with openings at the entrances. Trees and hedges keep off the buildings.</summary>
        static void Promenade(LandmarkKit k, float w, float d, List<Rect> keepOff)
        {
            float hw = w * 0.5f, hd = d * 0.5f, i0 = 4f, i1 = 16f;
            bool Free(float x, float z, float m) { foreach (var r in keepOff) if (x > r.xMin - m && x < r.xMax + m && z > r.yMin - m && z < r.yMax + m) return false; return true; }
            // the paving band (four strips) with a lighter centre line — laid first, then trees, lamps and benches, the hedge last (Wbs.G*)
            W(k, Wbs.GProm, 0.3f, 0.4f);
            k.Prism(LandmarkKit.Rect(0f, -hd + (i0 + i1) * 0.5f, w - 2f * i0, i1 - i0), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(0f, hd - (i0 + i1) * 0.5f, w - 2f * i0, i1 - i0), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(-hw + (i0 + i1) * 0.5f, 0f, i1 - i0, d - 2f * i1), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(hw - (i0 + i1) * 0.5f, 0f, i1 - i0, d - 2f * i1), 0.3f, 0.36f, Stone, LM.Solid, 1f, Stone, LM.Paving);
            // walk the ring at a given inset: f(x, z, along-direction)
            void Ring(float inset, float step, System.Action<float, float, Vector2> f)
            {
                float ax = hw - inset, az = hd - inset;
                for (float x = -ax; x <= ax + 0.01f; x += step) { f(x, -az, Vector2.right); f(x, az, Vector2.right); }
                for (float z = -az + step; z <= az - step + 0.01f; z += step) { f(-ax, z, Vector2.up); f(ax, z, Vector2.up); }
            }
            int n = 0;
            W(k, Wbs.GTrees, 0.3f, 9f);
            Ring(6.5f, 9f, (x, z, dir) => { if (Free(x, z, 2.5f)) Planted(k, x, z, 8f, 0); });
            Ring(13.5f, 9f, (x, z, dir) => { if (Free(x, z, 2.5f)) Planted(k, x, z, 8f, 1); });
            W(k, Wbs.GSquare, 0.3f, 6.5f);
            Ring(6.5f, 9f, (x, z, dir) =>
            {
                float lx = x + dir.x * 4.5f, lz = z + dir.y * 4.5f; if (!Free(lx, lz, 1.5f) || Mathf.Abs(lx) > hw - 6f || Mathf.Abs(lz) > hd - 6f) return;
                k.Box(new Vector3(lx, 3.3f, lz), new Vector3(0.22f, 6f, 0.22f), 0f, Steel, LM.Steel, 1f, Warm, LM.Light);
                if ((n++ % 3) == 0) { float bx = x + dir.x * 4.5f + dir.y * 3.5f, bz = z + dir.y * 4.5f + dir.x * 3.5f; if (Free(bx, bz, 1.5f)) Bench(k, bx, bz, dir.x != 0f ? 0f : 90f); }
            });
            // clipped hedge on the inner edge, open at the middle of each side (entrances)
            void Hedge(Vector2 a, Vector2 b)
            {
                var dl = b - a; float L = dl.magnitude; var u = dl / L;
                for (float t = 0f; t < L - 0.1f; t += 6f)
                {
                    var p = a + u * (t + 2.5f); if (t + 5f > L) break;
                    if (!Free(p.x, p.y, 3f)) continue;
                    if (Mathf.Abs(u.x) > 0.5f ? Mathf.Abs(p.x) < 14f : Mathf.Abs(p.y) < 14f) continue;
                    k.Box(new Vector3(p.x, 0.75f, p.y), Mathf.Abs(u.x) > 0.5f ? new Vector3(5f, 0.9f, 1.2f) : new Vector3(1.2f, 0.9f, 5f), 0f, GrassDark, LM.Plant, 1f, Grass, LM.Plant);
                }
            }
            float hx = hw - i1 - 1f, hz = hd - i1 - 1f;
            W(k, Wbs.GTrees, 0.3f, 1.3f);
            Hedge(new Vector2(-hx, hz), new Vector2(hx, hz)); Hedge(new Vector2(-hx, -hz), new Vector2(hx, -hz));
            Hedge(new Vector2(-hx, -hz), new Vector2(-hx, hz)); Hedge(new Vector2(hx, -hz), new Vector2(hx, hz));
        }
        /// <summary>A golden floor plate: a ring between the glass line and a footprint 1.4 m larger, turned a little (the "sliced" facade).</summary>
        static void Plate(LandmarkKit k, List<Vector2> glass, float y, int fl, bool crown)
        {
            float th = 1.4f * Mathf.Sin(y / 34f) + ((fl & 1) == 0 ? 0.35f : -0.35f);
            Vector2 c = Vector2.zero; foreach (var p in glass) c += p; c /= glass.Count;
            var outer = new List<Vector2>(glass.Count);
            float a = th * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
            foreach (var p in glass)
            {
                var d = p - c; float L = d.magnitude; var g = L > 0.01f ? d * ((L + 1.4f) / L) : d;
                outer.Add(c + new Vector2(g.x * ca - g.y * sa, g.x * sa + g.y * ca));
            }
            float y0 = y - 0.42f, y1 = y + 0.12f;
            var col = crown ? GoldLight : Gold; int mat = crown ? LM.Light : LM.Solid;
            k.Prism(outer, y0, y1, col, mat, 0.6f, col, -1);
            for (int i = 0; i < glass.Count; i++)
            {
                int j = (i + 1) % glass.Count;
                Vector3 gi = new Vector3(glass[i].x, y1, glass[i].y), gj = new Vector3(glass[j].x, y1, glass[j].y), oi = new Vector3(outer[i].x, y1, outer[i].y), oj = new Vector3(outer[j].x, y1, outer[j].y);
                k.Quad(gi, gj, oj, oi, Vector3.up, Gold, LM.Solid, 0.6f, glass[i], glass[j], outer[j], outer[i]);
                gi.y = gj.y = oi.y = oj.y = y0;
                k.Quad(gi, gj, oj, oi, Vector3.down, Gold, LM.Solid, 0.6f, glass[i], glass[j], outer[j], outer[i]);
            }
        }
        /// <summary>A low block on the rectangle (x0, z0)–(x1, z1) whose roof follows H(x, z): glass walls under a golden fascia, a planted roof with paths.</summary>
        static void Wedge(LandmarkKit k, float x0, float z0, float x1, float z1, System.Func<float, float, float> Hf, int nx, int nz)
        {
            var corners = new[] { new Vector2(x0, z0), new Vector2(x1, z0), new Vector2(x1, z1), new Vector2(x0, z1) };
            var ce = new Vector2((x0 + x1) * 0.5f, (z0 + z1) * 0.5f);
            for (int e = 0; e < 4; e++)
            {
                var a = corners[e]; var b = corners[(e + 1) % 4]; int n = e % 2 == 0 ? nx : nz;
                var mid = (a + b) * 0.5f; var o = new Vector3(mid.x - ce.x, 0f, mid.y - ce.y);
                for (int i = 0; i < n; i++)
                {
                    var p = Vector2.Lerp(a, b, i / (float)n); var q = Vector2.Lerp(a, b, (i + 1f) / n);
                    float hp = Hf(p.x, p.y), hq = Hf(q.x, q.y), u0 = (p - a).magnitude, u1 = (q - a).magnitude;
                    k.Quad(new Vector3(p.x, 0.3f, p.y), new Vector3(q.x, 0.3f, q.y), new Vector3(q.x, hq - 1.4f, q.y), new Vector3(p.x, hp - 1.4f, p.y), o, WarmGlass, LM.Glass, 4.3f,
                           new Vector2(u0, 0.3f), new Vector2(u1, 0.3f), new Vector2(u1, hq - 1.4f), new Vector2(u0, hp - 1.4f));
                    k.Quad(new Vector3(p.x, hp - 1.4f, p.y), new Vector3(q.x, hq - 1.4f, q.y), new Vector3(q.x, hq, q.y), new Vector3(p.x, hp, p.y), o, Gold, LM.Solid, 1.4f,
                           new Vector2(u0, hp - 1.4f), new Vector2(u1, hq - 1.4f), new Vector2(u1, hq), new Vector2(u0, hp));
                }
            }
            for (int i = 0; i < nx; i++)
                for (int j = 0; j < nz; j++)
                {
                    float xa = Mathf.Lerp(x0, x1, i / (float)nx), xb = Mathf.Lerp(x0, x1, (i + 1f) / nx), za = Mathf.Lerp(z0, z1, j / (float)nz), zb = Mathf.Lerp(z0, z1, (j + 1f) / nz);
                    bool path = (i + j) % 4 == 0;
                    k.Quad(new Vector3(xa, Hf(xa, za), za), new Vector3(xb, Hf(xb, za), za), new Vector3(xb, Hf(xb, zb), zb), new Vector3(xa, Hf(xa, zb), zb), Vector3.up,
                           path ? Pave : Grass, path ? LM.Paving : LM.Plant, 1f, new Vector2(xa, za), new Vector2(xb, za), new Vector2(xb, zb), new Vector2(xa, zb));
                }
        }

        // ------------------------------------------------------------------ airliner (≈ A320): fuselage along +z, nose at +z
        public static void Plane(LandmarkKit k, Vector3 o, float yaw, float scale = 1f)
        {
            var r = Quaternion.Euler(0, yaw, 0);
            Vector3 P(float x, float y, float z) => o + r * (new Vector3(x, y, z) * scale);
            var body = LM.C("#f4f5f6"); var belly = LM.C("#dfe3e8"); var tail = LM.C("#e0261b"); var eng = LM.C("#8a9097"); var win = LM.C("#1d2a36");
            k.Tube(P(0, 4.2f, -16f), P(0, 4.2f, 14f), 2.0f, 2.0f, 10, body, LM.Solid, false);
            k.Tube(P(0, 4.2f, 14f), P(0, 4.0f, 19.5f), 2.0f, 0.25f, 10, body, LM.Solid);            // nose
            k.Tube(P(0, 4.2f, -16f), P(0, 5.0f, -23f), 2.0f, 0.35f, 10, body, LM.Solid);           // tail cone
            k.Tube(P(0, 4.9f, 15.6f), P(0, 4.9f, 17.4f), 1.2f, 0.9f, 8, win, LM.Glass, false);     // cockpit glazing band
            // wings (swept), with engines underneath
            k.Slab(P(1.6f, 3.4f, 3f), P(17f, 4.6f, -5.5f), P(17f, 4.6f, -8f), P(1.6f, 3.4f, -4f), 0.35f, belly, LM.Solid);
            k.Slab(P(-1.6f, 3.4f, -4f), P(-17f, 4.6f, -8f), P(-17f, 4.6f, -5.5f), P(-1.6f, 3.4f, 3f), 0.35f, belly, LM.Solid);
            k.Tube(P(5.8f, 2.4f, 1.8f), P(5.8f, 2.4f, -2.6f), 1.05f, 0.85f, 10, eng, LM.Metal);
            k.Tube(P(-5.8f, 2.4f, 1.8f), P(-5.8f, 2.4f, -2.6f), 1.05f, 0.85f, 10, eng, LM.Metal);
            // tail: fin + stabilisers
            k.Slab(P(0, 5.6f, -15f), P(0, 12.2f, -20.5f), P(0, 12.2f, -23f), P(0, 5.6f, -21.5f), 0.3f, tail, LM.Solid);
            k.Slab(P(0.5f, 5.2f, -18.5f), P(6.2f, 5.6f, -21.5f), P(6.2f, 5.6f, -22.8f), P(0.5f, 5.2f, -22f), 0.25f, body, LM.Solid);
            k.Slab(P(-0.5f, 5.2f, -22f), P(-6.2f, 5.6f, -22.8f), P(-6.2f, 5.6f, -21.5f), P(-0.5f, 5.2f, -18.5f), 0.25f, body, LM.Solid);
            // gear
            k.Box(P(0, 1.1f, 13f), new Vector3(0.5f, 2.2f, 0.5f) * scale, yaw, eng, LM.Steel, 1f, eng, LM.Steel);
            k.Box(P(2.6f, 1.1f, -1f), new Vector3(0.8f, 2.2f, 1.2f) * scale, yaw, eng, LM.Steel, 1f, eng, LM.Steel);
            k.Box(P(-2.6f, 1.1f, -1f), new Vector3(0.8f, 2.2f, 1.2f) * scale, yaw, eng, LM.Steel, 1f, eng, LM.Steel);
        }
        public static Mesh PlaneMesh() { var k = new LandmarkKit(); Plane(k, Vector3.zero, 0f); return k.ToMesh("Airliner"); }

        // ------------------------------------------------------------------ Airport «Алатау» (the owner's site of 31.10.2026, Growing-West scheme): one
        // runway 4 000 × 45 m on 095°/275° with its parallel taxiway and rapid exits; north of it the apron, a glazed concourse with the
        // contact stands and the terminal hall, its forecourt and the glazed bridge to the rail station «Алатау» on the lot's north edge
        // (growing_w.json airport_rail_station); cargo east of the terminal; maintenance, the fire station and the fuel farm west; the tower
        // at the landside. Local frame (yaw 95°): +z along the runway toward 095°, +x across it toward the south (185°). The origin is the
        // centre of the levelled plot (PlotW × PlotD = LandmarkData PadW × PadD): the runway axis runs RwyX = 370 m south of it and the
        // runway centre (−16000, 1500) is 12 m west of it (AZ). Everything is placed by (c, a): metres north of the runway axis, metres
        // east of the runway centre (AP, AP3).
        public const float RwyX = 370f, RwyZ0 = -2012f, RwyZ1 = 1988f, RwyW = 45f;
        const float AZ = -12f, PlotW = 1040f, PlotD = 4040f;
        static Vector2 AP(float c, float a) => new Vector2(RwyX - c, a + AZ);
        static Vector3 AP3(float c, float y, float a) => new Vector3(RwyX - c, y, a + AZ);
        static readonly Color32 Tarmac = LM.C("#4a4b4d"), Shoulder = LM.C("#77766f"), ApronC = LM.C("#a3a19a"), Line = LM.C("#f2f2ef"), Yellow = LM.C("#e8b923"),
            GreenL = LM.C("#40e070"), RedL = LM.C("#ff3a2a"), BlueL = LM.C("#3a7bff"), Turf = LM.C("#8c925e"), Turf2 = LM.C("#848a57");

        /// <summary>An open cross-section (ground → over the top → ground): superelliptic, so the walls stand up near the ground and the roof is full.</summary>
        static List<Vector3> Section(Vector3 c, Vector3 across, float halfW, float h, int m)
        {
            var l = new List<Vector3>(m + 1);
            for (int j = 0; j <= m; j++)
            {
                float th = Mathf.PI * j / m, cs = Mathf.Cos(th), sn = Mathf.Sin(th);
                l.Add(c - across * (Mathf.Sign(cs) * Mathf.Pow(Mathf.Abs(cs), 0.5f) * halfW) + Vector3.up * (Mathf.Pow(Mathf.Max(sn, 0f), 0.62f) * h));
            }
            return l;
        }
        /// <summary>A vaulted shell lofted through sections; mat(ring, f) picks glass or metal for each strip (f = 0 on the ridge … 1 at the foot of the wall).</summary>
        static void Shell(LandmarkKit k, List<List<Vector3>> rings, System.Func<int, float, int> mat, Color32 roof, Color32 glass, bool capA, bool capB)
        {
            int m = rings[0].Count - 1; float s = 0f;
            for (int i = 0; i + 1 < rings.Count; i++)
            {
                var A = rings[i]; var B = rings[i + 1];
                Vector3 cen = (A[0] + A[m] + B[0] + B[m]) * 0.25f; float ds = Vector3.Distance((A[0] + A[m]) * 0.5f, (B[0] + B[m]) * 0.5f);
                Vector3 acr = (A[m] - A[0] + B[m] - B[0]) * 0.5f; float hw = Mathf.Max(acr.magnitude * 0.5f, 0.01f); acr.Normalize();
                float v = 0f;
                for (int j = 0; j < m; j++)
                {
                    Vector3 a = A[j], b = A[j + 1], c = B[j + 1], d = B[j]; float L = (b - a).magnitude;
                    int mm = mat(i, Mathf.Abs(Vector3.Dot((a + b + c + d) * 0.25f - cen, acr)) / hw); bool g = mm == LM.Glass;
                    k.Quad(a, b, c, d, (a + b + c + d) * 0.25f - cen, g ? glass : roof, mm, g ? 4.5f : 3f,
                           new Vector2(s, v), new Vector2(s, v + L), new Vector2(s + ds, v + L), new Vector2(s + ds, v));
                    v += L;
                }
                s += ds;
            }
            void Cap(List<Vector3> R, Vector3 outward)
            {
                var c0 = (R[0] + R[m]) * 0.5f;
                for (int j = 0; j < m; j++) k.Tri(c0, R[j], R[j + 1], outward, roof, LM.Metal, 3f, new Vector2(c0.x, c0.z), new Vector2(R[j].x, R[j].z), new Vector2(R[j + 1].x, R[j + 1].z));
            }
            Vector3 Mid(List<Vector3> R) => (R[0] + R[m]) * 0.5f;
            if (capA) Cap(rings[0], Mid(rings[0]) - Mid(rings[1]));
            if (capB) Cap(rings[rings.Count - 1], Mid(rings[rings.Count - 1]) - Mid(rings[rings.Count - 2]));
        }
        /// <summary>A contact stand: guide line, a jet bridge from the facade point e (outward normal n) to the front door, and the aircraft nose-in.</summary>
        static void Stand(LandmarkKit k, Vector3 e, Vector3 n, float scale, bool plane)
        {
            n.y = 0; n.Normalize(); e.y = 0f;
            float yaw = Mathf.Atan2(-n.x, -n.z) * Mathf.Rad2Deg; var r = Quaternion.Euler(0, yaw, 0);
            var o = e + n * (19.5f * scale + 13f); o.y = 0.45f;
            k.Beam(e + n * 3f + Vector3.up * 0.47f, e + n * (46f * scale + 22f) + Vector3.up * 0.47f, 0.35f, 0.04f, Yellow, LM.Light);
            k.Beam(o + r * new Vector3(-9f, 0.02f, 0f), o + r * new Vector3(9f, 0.02f, 0f), 0.3f, 0.04f, Yellow, LM.Light);       // stop bar
            var door = o + r * (new Vector3(-2.3f, 4.0f, 14.5f) * scale);
            var root = e + n * 1.5f + Vector3.up * 5.2f;
            k.Beam(root, door, 3.2f, 3.0f, MetalG, LM.Metal);
            var leg = Vector3.Lerp(root, door, 0.72f);
            k.Beam(new Vector3(leg.x, 0.45f, leg.z), leg - Vector3.up * 1.5f, 0.7f, 0.7f, MetalD, LM.Steel);
            k.Box(new Vector3(leg.x, 0.9f, leg.z), new Vector3(3.4f, 0.9f, 1.4f), yaw, MetalD, LM.Steel, 1f, MetalD, LM.Steel);
            if (plane) Plane(k, o, yaw, scale);
            else k.Box(o + r * new Vector3(6f, 1.2f, -6f), new Vector3(2.4f, 2.0f, 5.5f), yaw, Yellow, LM.Solid, 2f, Yellow, LM.Roof);  // tug waiting
        }
        /// <summary>A runway of width w along local z: tarmac with 7.5 m shoulders, the ICAO markings (threshold stripes and bar, aiming
        /// points, touchdown zone, centre line, side stripes), threshold (green) and end (red) lights, edge lights every 60 m.</summary>
        static void Runway(LandmarkKit k, float x, float z0, float z1, float w)
        {
            float L = z1 - z0, zc = (z0 + z1) * 0.5f, hw = w * 0.5f;
            k.Prism(LandmarkKit.Rect(x, zc, w + 15f, L + 12f), 0.25f, 0.40f, Shoulder, LM.Solid, 1f, Shoulder, LM.Paving);
            k.Prism(LandmarkKit.Rect(x, zc, w, L), 0.25f, 0.45f, Tarmac, LM.Solid, 1f, Tarmac, LM.Paving);
            void Mark(float cx, float cz, float mw, float md, Color32 c) => k.Box(new Vector3(cx, 0.47f, cz), new Vector3(mw, 0.04f, md), 0, c, LM.Solid, 1f, c, LM.Light);
            void Lamp(float cx, float cz, Color32 c) => k.Box(new Vector3(cx, 0.7f, cz), new Vector3(0.6f, 0.5f, 0.6f), 0, c, LM.Light, 1f, c, LM.Light);
            for (float z = z0 + 330f; z + 30f < z1 - 330f; z += 50f) Mark(x, z + 15f, 0.9f, 30f, Line);          // centre line: 30 m dashes, 20 m gaps
            Mark(x - hw + 1f, zc, 0.9f, L - 20f, Line); Mark(x + hw - 1f, zc, 0.9f, L - 20f, Line);           // side stripes
            foreach (float sg in new[] { -1f, 1f })
            {
                float zt = sg < 0 ? z0 + 26f : z1 - 26f, inw = -sg, ze = sg < 0 ? z0 : z1;      // middle of the threshold stripes, into the runway, the end
                for (int i = 0; i < 6; i++) { float xo = 3.4f + i * 3.6f; Mark(x - xo, zt, 1.8f, 30f, Line); Mark(x + xo, zt, 1.8f, 30f, Line); }
                Mark(x, zt + inw * 24f, w - 4f, 1.6f, Line);
                Mark(x - 9.5f, zt + inw * 400f, 8f, 45f, Line); Mark(x + 9.5f, zt + inw * 400f, 8f, 45f, Line);          // aiming point
                foreach (float d in new[] { 150f, 300f, 600f, 750f, 900f })                                           // touchdown zone
                    foreach (float xo in new[] { -12f, -7.5f, 7.5f, 12f }) Mark(x + xo, zt + inw * d, 3f, 22.5f, Line);
                for (int i = 0; i < 12; i++) { float xo = -hw + 1.2f + i * (w - 2.4f) / 11f; Lamp(x + xo, ze + inw * 1.5f, GreenL); Lamp(x + xo, ze - inw * 1.5f, RedL); }
            }
            for (float z = z0; z <= z1 + 0.1f; z += 60f) { Lamp(x - hw - 1.5f, z, Warm); Lamp(x + hw + 1.5f, z, Warm); }
        }
        /// <summary>A taxiway strip between two points: tarmac, yellow centre line, blue edge lights.</summary>
        static void Taxi(LandmarkKit k, Vector2 a, Vector2 b, float w = 23f)
        {
            var d = b - a; float L = d.magnitude; if (L < 1f) return; var m = (a + b) * 0.5f; float yaw = Mathf.Atan2(d.x, d.y) * Mathf.Rad2Deg; var dn = d / L; var side = new Vector2(dn.y, -dn.x);
            k.Prism(LandmarkKit.Rect(m.x, m.y, w + 8f, L, yaw), 0.25f, 0.40f, Shoulder, LM.Solid, 1f, Shoulder, LM.Paving);
            k.Prism(LandmarkKit.Rect(m.x, m.y, w, L, yaw), 0.25f, 0.43f, Tarmac, LM.Solid, 1f, Tarmac, LM.Paving);
            k.Box(new Vector3(m.x, 0.45f, m.y), new Vector3(0.45f, 0.04f, L - 6f), yaw, Yellow, LM.Solid, 1f, Yellow, LM.Light);
            for (float s = 0f; s <= L; s += 60f) foreach (float sg in new[] { -1f, 1f })
                { var p = a + dn * s + side * (sg * (w * 0.5f + 1.5f)); k.Box(new Vector3(p.x, 0.65f, p.y), new Vector3(0.45f, 0.45f, 0.45f), 0, BlueL, LM.Light, 1f, BlueL, LM.Light); }
        }
        /// <summary>A road ribbon along a polyline (or a closed loop): asphalt, kerbs implied by the paving around, dashed lane line.</summary>
        static void Road(LandmarkKit k, IList<Vector2> p, float half, bool closed, bool centreLine = true)
        {
            int n = p.Count, segs = closed ? n : n - 1; float s = 0f;
            Vector2 Side(int i)
            {
                Vector2 a = closed ? p[(i - 1 + n) % n] : p[Mathf.Max(i - 1, 0)], b = closed ? p[(i + 1) % n] : p[Mathf.Min(i + 1, n - 1)];
                var d = (b - a).normalized; return new Vector2(d.y, -d.x);
            }
            for (int i = 0; i < segs; i++)
            {
                int j = (i + 1) % n; Vector2 sa = Side(i) * half, sb = Side(j) * half; float L = (p[j] - p[i]).magnitude;
                Vector3 A(Vector2 q) => new Vector3(q.x, 0.47f, q.y);
                k.Quad(A(p[i] - sa), A(p[i] + sa), A(p[j] + sb), A(p[j] - sb), Vector3.up, Asph, LM.Paving, 1f, new Vector2(p[i].x, p[i].y), new Vector2(p[i].x + 1, p[i].y), new Vector2(p[j].x + 1, p[j].y), new Vector2(p[j].x, p[j].y));
                if (centreLine)
                    for (float t = 2f; t < L - 4f; t += 12f)
                    {
                        var d = (p[j] - p[i]) / L; var q = p[i] + d * (t + 2.5f);
                        k.Box(new Vector3(q.x, 0.5f, q.y), new Vector3(0.18f, 0.04f, 5f), Mathf.Atan2(d.x, d.y) * Mathf.Rad2Deg, Line, LM.Solid, 1f, Line, LM.Light);
                    }
                s += L;
            }
        }
        static List<Vector2> Bez(Vector2 a, Vector2 b, Vector2 c, Vector2 d, int n)
        {
            var l = new List<Vector2>(); for (int i = 0; i <= n; i++) { float t = i / (float)n, u = 1 - t; l.Add(u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d); } return l;
        }
        /// <summary>Surface car park: bays in double rows with aisles, most of them taken.</summary>
        static void CarPark(LandmarkKit k, float x0, float x1, float z0, float z1, float seed)
        {
            k.Prism(LandmarkKit.Rect((x0 + x1) * 0.5f, (z0 + z1) * 0.5f, x1 - x0, z1 - z0), 0.25f, 0.44f, PaveDark, LM.Solid, 1f, LM.C("#6b6b69"), LM.Paving);
            for (float z = z0 + 4f; z + 13f < z1; z += 21f)
            {
                Cars(k, x0 + 3f, z + 2.6f, Mathf.FloorToInt((x1 - x0 - 6f) / 2.7f), 2, seed + z);
                k.Box(new Vector3((x0 + x1) * 0.5f, 0.46f, z + 5.85f), new Vector3(x1 - x0 - 6f, 0.04f, 0.15f), 0, Line, LM.Solid, 1f, Line, LM.Light);
            }
        }

        static void Airport(LandmarkKit k)
        {
            // ---- airfield: mown grass over the whole plot, in long stripes along the runway
            k.Prism(LandmarkKit.RoundRect(0, 0, PlotW, PlotD, 40f, 4), -2f, 0.22f, LM.C("#6f7550"), LM.Plant, 3f, Turf, LM.Plant);
            for (int i = 0; i < 13; i++) { float x = -PlotW * 0.5f + 40f + i * 80f; k.Prism(LandmarkKit.Rect(x, 0, 40f, PlotD - 140f), 0.22f, 0.24f, Turf2, LM.Plant, 1f, Turf2, LM.Plant); }

            // ---- the runway; the parallel taxiway 190 m north of it, the end links, two links and two rapid exits (landing 095° and 275°)
            Runway(k, RwyX, RwyZ0, RwyZ1, RwyW);
            const float TC = 190f;
            Taxi(k, AP(TC, -1975f), AP(TC, 1975f));
            foreach (float a in new[] { -1975f, -900f, 1100f, 1975f }) Taxi(k, AP(22f, a), AP(TC, a));
            Taxi(k, AP(22f, -560f), AP(TC, -230f)); Taxi(k, AP(22f, 760f), AP(TC, 430f));

            // ---- aprons: the terminal apron in front of the concourse, maintenance west, cargo east; taxilanes from the taxiway
            void Apron(float c0, float c1, float a0, float a1) { var m = AP((c0 + c1) * 0.5f, (a0 + a1) * 0.5f); k.Prism(LandmarkKit.Rect(m.x, m.y, c1 - c0, a1 - a0), 0.25f, 0.44f, ApronC, LM.Solid, 1f, ApronC, LM.Paving); }
            Apron(260f, 560f, -260f, 1300f); Apron(260f, 500f, -900f, -320f); Apron(260f, 520f, 1360f, 1800f);
            foreach (float a in new[] { -610f, 0f, 1000f, 1580f }) Taxi(k, AP(TC, a), AP(262f, a));
            k.Box(AP3(330f, 0.47f, 520f), new Vector3(0.45f, 0.04f, 1540f), 0, Yellow, LM.Solid, 1f, Yellow, LM.Light);          // apron taxilane
            for (float a = -200f; a <= 1801f; a += 250f)
            {
                var p = AP3(272f, 0.4f, a); k.Beam(p, p + Vector3.up * 27.6f, 0.8f, 0.8f, MetalG, LM.Steel);                       // flood-light masts
                k.Box(p + Vector3.up * 28.2f, new Vector3(1.6f, 1.2f, 4.5f), 0, Warm, LM.Light, 1f, Steel, LM.Steel);
            }

            // ---- the concourse: a glazed pier 1 060 m along the apron; 14 contact stands on its south face (three for wide-bodies)
            const float CS = 560f, CN = 605f;
            var cm = AP((CS + CN) * 0.5f, 650f);
            k.Prism(LandmarkKit.Rect(cm.x, cm.y, CN - CS, 1060f), 0.3f, 14f, GlassBlue, LM.Glass, 4.5f, Roof, LM.Roof);
            k.Prism(LandmarkKit.Rect(cm.x, cm.y, CN - CS + 8f, 1068f), 14f, 15.4f, MetalW, LM.Metal, 1.4f, MetalW, LM.Roof);
            int sn = 0;
            bool Busy() { sn++; return (sn * 7 % 10) < 8; }
            for (int i = 0; i < 14; i++) Stand(k, AP3(CS, 0f, 170f + i * 75f), Vector3.right, i >= 5 && i <= 7 ? 1.3f : 1f, Busy());
            // remote stands west of the concourse, a bus at each
            foreach (float a in new[] { -220f, -150f, -80f, -10f })
            {
                Plane(k, AP3(430f, 0.45f, a), -90f, 1f);
                k.Box(AP3(380f, 1.6f, a + 22f), new Vector3(12f, 2.9f, 2.6f), 0, White, LM.Solid, 2f, White, LM.Roof);
            }

            // ---- the terminal hall behind the concourse: glass walls under one roof rising toward the apron, its eave over the kerb
            const float TS = 605f, TN = 745f, TA0 = 420f, TA1 = 900f;
            var tm = AP((TS + TN) * 0.5f, (TA0 + TA1) * 0.5f);
            k.Prism(LandmarkKit.Rect(tm.x, tm.y, TN - TS, TA1 - TA0), 0.3f, 21f, GlassBlue, LM.Glass, 4.5f, Roof, LM.Roof);
            k.Slab(AP3(TN + 22f, 23.5f, TA0 - 14f), AP3(TN + 22f, 23.5f, TA1 + 14f), AP3(TS - 8f, 28.5f, TA1 + 14f), AP3(TS - 8f, 28.5f, TA0 - 14f), 1.6f, MetalW, LM.Metal);
            k.Box(AP3(680f, 26.9f, (TA0 + TA1) * 0.5f), new Vector3(5f, 0.6f, TA1 - TA0 - 40f), 0, GlassBlue, LM.Glass, 1f, GlassBlue, LM.Glass);    // roof light
            for (float a = TA0 + 10f; a <= TA1 - 9f; a += 40f) k.Beam(AP3(TN + 15f, 0.5f, a), AP3(TN + 15f, 23f, a), 1.2f, 1.2f, White, LM.Solid);
            var kerb = AP(757f, (TA0 + TA1) * 0.5f);
            k.Prism(LandmarkKit.Rect(kerb.x, kerb.y, 18f, TA1 - TA0), 0.25f, 0.5f, PaveDark, LM.Solid, 1f, Pave, LM.Paving);         // departures kerb

            // ---- landside: the Аэропортовая магистраль ends at the lot's north edge (c 1 000, a 14); the access road runs to the forecourt
            // loop in front of the hall; car parks, a multi-storey car park and the hotel north of the loop
            var acc = new List<Vector2> { AP(1000f, 14f), AP(860f, 14f) }; acc.AddRange(Bez(AP(860f, 14f), AP(800f, 14f), AP(800f, 14f), AP(800f, 80f), 6)); acc.Add(AP(800f, 330f));
            Road(k, acc, 8f, false);
            { var lc = AP(800f, 650f); Road(k, LandmarkKit.RoundRect(lc.x, lc.y, 50f, 640f, 25f, 6), 7.5f, true); }
            Trees(k, AP(990f, 0f).x, 40f + AZ, AP(870f, 0f).x, 40f + AZ, 20f, 8f, 3f);
            CarPark(k, AP(885f, 0f).x, AP(835f, 0f).x, 340f + AZ, 620f + AZ, 11f);
            Trees(k, AP(889f, 0f).x, 340f + AZ, AP(889f, 0f).x, 620f + AZ, 20f, 8f, 5f);
            var ms = AP(857.5f, 720f);
            for (int lv = 0; lv < 5; lv++)
            {
                float y0 = 0.3f + lv * 3.4f;
                k.Prism(LandmarkKit.Rect(ms.x, ms.y, 55f, 160f), y0, y0 + 2.2f, GlassDark, LM.Solid, 2.2f, Concrete, -1);
                k.Prism(LandmarkKit.Rect(ms.x, ms.y, 57f, 162f), y0 + 2.2f, y0 + 3.4f, Concrete, LM.Solid, 1.2f, Concrete, LM.Paving);
            }
            for (int i = 0; i < 6; i++) k.Box(AP3(857.5f, 18.6f, 655f + i * 26f), new Vector3(46f, 0.5f, 9f), 0, LM.C("#1d2d4a"), LM.Glass, 1f, LM.C("#24375a"), LM.Glass);      // solar canopies
            var ho = AP(860f, 938f);
            k.Prism(LandmarkKit.RoundRect(ho.x, ho.y, 30f, 76f, 6f, 3), 0.3f, 8f, GlassWarm, LM.Glass, 4f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Chamfer(ho.x, ho.y, 24f, 66f, 4f), 8f, 52f, GlassTeal, LM.Fins, 3.6f, Roof, LM.Roof);
            k.Box(new Vector3(ho.x, 53f, ho.y), new Vector3(14f, 2f, 40f), 0, MetalG, LM.Metal, 2f, Roof, LM.Roof);
            // the glazed bridge from the hall over the forecourt to the station «Алатау» (its piers reach down to the ground past the plot)
            const float WA = 860f, WC = 1105f;
            k.Beam(AP3(TN, 10f, WA), AP3(WC, 10f, WA), 7f, 4.2f, GlassBlue, LM.Glass);
            k.Beam(AP3(TN, 12.3f, WA), AP3(WC, 12.3f, WA), 7.6f, 0.4f, White, LM.Roof);
            for (float c = TN + 40f; c < WC - 5f; c += 45f) k.Beam(AP3(c, -12f, WA), AP3(c, 7.9f, WA), 1.2f, 1.2f, White, LM.Solid);

            // ---- control tower at the landside west of the forecourt: a slim tapering shaft, the glazed cab, the radar mast
            var tw = AP(835f, -150f); float twx = tw.x, twz = tw.y;
            k.Prism(LandmarkKit.RoundRect(twx, twz, 56f, 30f, 8f, 3), 0.3f, 9f, GlassBlue, LM.Glass, 4.5f, White, LM.Roof);
            k.Loft(LandmarkKit.Circle(twx, twz, 9f, 16), 9f, LandmarkKit.Circle(twx, twz, 5.5f, 16), 76f, White, LM.Solid, 4f);
            k.Prism(LandmarkKit.Circle(twx, twz, 10.5f, 16), 76f, 78f, White, LM.Solid, 2f, White, LM.Roof);
            k.Loft(LandmarkKit.Circle(twx, twz, 10.5f, 16), 78f, LandmarkKit.Circle(twx, twz, 13f, 16), 87f, GlassDark, LM.Glass, 3f);
            k.Prism(LandmarkKit.Circle(twx, twz, 13.6f, 16), 87f, 88.4f, White, LM.Solid, 1.4f, MetalG, LM.Metal);
            k.Beam(new Vector3(twx, 88.4f, twz), new Vector3(twx, 98f, twz), 0.5f, 0.5f, MetalG, LM.Steel);
            k.Box(new Vector3(twx, 98.3f, twz), new Vector3(0.9f, 0.6f, 0.9f), 0, RedL, LM.Light, 1f, RedL, LM.Light);
            k.Box(new Vector3(twx, 81f, twz), new Vector3(27f, 0.4f, 27f), 0, Warm, LM.Light, 1f, Warm, -1);

            // ---- cargo terminal east of the concourse, two freighters on its apron
            var cg = AP(580f, 1570f);
            k.Prism(LandmarkKit.Rect(cg.x, cg.y, 120f, 380f), 0.3f, 17f, MetalG, LM.Metal, 4f, Roof, LM.Roof);
            for (int i = 0; i < 12; i++) { var d = AP3(519.6f, 4.5f, 1400f + i * 30f); k.Box(d, new Vector3(0.8f, 8f, 12f), 0, MetalD, LM.Metal, 2f, MetalD, LM.Metal); }   // dock doors
            Plane(k, AP3(440f, 0.45f, 1470f), -90f, 1.5f); Plane(k, AP3(440f, 0.45f, 1660f), -90f, 1.5f);

            // ---- maintenance: two hangars facing their apron, an airliner in front of one; the fire station; the fuel farm in its bund
            foreach (float ah in new[] { -780f, -560f })
            {
                var hrng = new List<List<Vector3>>();
                for (int i = 0; i <= 6; i++) hrng.Add(Section(AP3(500f + i * 25f, 0f, ah), Vector3.forward, 70f, 32f, 12));
                Shell(k, hrng, (i, t) => t < 0.06f ? LM.Glass : LM.Metal, MetalW, GlassBlue, false, true);
                var door = Section(AP3(500f, 0f, ah), Vector3.forward, 66f, 30f, 12);
                var c0 = AP3(499.5f, 0f, ah);
                for (int j = 0; j < 12; j++) k.Tri(c0, door[j] + Vector3.right * 0.5f, door[j + 1] + Vector3.right * 0.5f, Vector3.right, (j & 1) == 0 ? MetalG : MetalD, LM.Metal, 3f, Vector2.zero, Vector2.right, Vector2.up);
            }
            Plane(k, AP3(440f, 0.45f, -780f), -90f, 1.2f);
            var fs = AP(300f, -1100f);
            k.Prism(LandmarkKit.Rect(fs.x, fs.y, 34f, 80f), 0.3f, 9f, White, LM.Solid, 4.5f, Roof, LM.Roof);
            for (int i = 0; i < 5; i++) k.Box(AP3(282.6f, 3.5f, -1132f + i * 16f), new Vector3(0.6f, 6f, 10f), 0, Red, LM.Solid, 2f, Red, LM.Solid);
            { var ft = AP(300f, -1052f); k.Prism(LandmarkKit.Rect(ft.x, ft.y, 12f, 12f), 0.3f, 22f, White, LM.Solid, 4.5f, Roof, LM.Roof); }
            var fb = AP(660f, -1235f);
            k.Prism(LandmarkKit.Rect(fb.x, fb.y, 120f, 170f), 0.25f, 1.6f, Concrete, LM.Solid, 1f, Gravel, LM.Paving);
            for (int i = 0; i < 3; i++) for (int j = 0; j < 2; j++) k.Cylinder(AP3(630f + j * 60f, 1.6f, -1290f + i * 55f), 15f, 14f, 20, White, LM.Metal, 3f, MetalW, LM.Metal, 1.5f);
        }

        // ------------------------------------------------------------------ food plant (PepsiCo snacks / Mars petfood)
        static void FoodPlant(LandmarkKit k, Color32 brand, bool potato)
        {
            Pad(k, 430f, 300f, 10f, PaveDark);
            // production hall with roof lights and a brand band along the front
            k.Prism(LandmarkKit.Rect(-40f, 10f, 230f, 112f), 0.3f, 15f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            for (int i = 0; i < 9; i++) k.Box(new Vector3(-140f + 25f + i * 25f, 15.6f, 10f), new Vector3(4f, 1.2f, 90f), 0, GlassBlue, LM.Glass, 1.2f, GlassBlue, LM.Glass);
            k.Box(new Vector3(-40f, 12.5f, 10f - 56.4f), new Vector3(230f, 2.6f, 0.8f), 0, brand, LM.Solid, 3f, brand, LM.Roof);
            k.Box(new Vector3(40f, 9f, 10f - 56.6f), new Vector3(9f, 9f, 0.6f), 0, brand, LM.Light, 1f, brand, LM.Light);
            // office and staff block, glazed
            k.Prism(LandmarkKit.RoundRect(-110f, -95f, 70f, 22f, 4f, 2), 0.3f, 13f, GlassBlue, LM.Glass, 4.2f, Roof, LM.Roof);
            k.Box(new Vector3(-110f, 13.8f, -95f), new Vector3(72f, 1.6f, 24f), 0, White, LM.Solid, 1.6f, White, LM.Roof);
            if (potato)
            {
                // raw potato stores: four long gabled halls
                for (int i = 0; i < 4; i++) Gable(k, 145f, -60f + i * 38f, 110f, 30f, 8f, 5f, MetalG, LM.Metal, LM.C("#8f9399"));
                Silos(k, 110f, 110f, 6, 4.5f, 24f, MetalW);
            }
            else
            {
                // feed mill tower and ingredient silos
                k.Box(new Vector3(120f, 21f, 30f), new Vector3(30f, 42f, 24f), 0, Concrete, LM.Solid, 4f, Roof, LM.Roof);
                Silos(k, 150f, -20f, 4, 6f, 32f, MetalW); Silos(k, 150f, 10f, 4, 6f, 32f, MetalW);
                k.Prism(LandmarkKit.Rect(120f, -95f, 90f, 50f), 0.3f, 12f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            }
            k.Cylinder(new Vector3(60f, 0.3f, 75f), 1.6f, 40f, 12, Concrete, LM.Solid, 4f, Steel, LM.Steel);
            // utilities: tanks and the truck yard
            for (int i = 0; i < 3; i++) k.Cylinder(new Vector3(-185f + i * 17f, 0.3f, 100f), 7f, 11f, 18, MetalW, LM.Metal, 3f, MetalG, LM.Metal, 1.2f);
            k.Prism(LandmarkKit.Rect(40f, -100f, 120f, 50f), 0.3f, 0.36f, Asph, LM.Paving, 3f, Asph, LM.Paving);
            for (int i = 0; i < 7; i++) Truck(k, new Vector3(-12f + i * 16f, 0.3f, -112f), 90f, i % 3 == 0 ? brand : White);
            Lot(k, -205f, -90f, -146f, -112f, 0.75f, 3f);
            Trees(k, -80f, -142f, 205f, -142f, 12f, 7f, 7f);
        }

        // ------------------------------------------------------------------ paper mill (tissue / paper machines)
        static void PaperMill(LandmarkKit k)
        {
            Pad(k, 440f, 280f, 10f, PaveDark);
            k.Prism(LandmarkKit.Rect(-20f, 20f, 280f, 50f), 0.3f, 24f, MetalW, LM.Metal, 4f, Roof, LM.Roof);           // machine hall
            k.Prism(LandmarkKit.Rect(-20f, -40f, 200f, 70f), 0.3f, 14f, MetalG, LM.Metal, 4f, Roof, LM.Roof);          // finished goods
            k.Box(new Vector3(-20f, 21f, 20f - 25.4f), new Vector3(280f, 2.4f, 0.6f), 0, LM.C("#2e7d4f"), LM.Solid, 3f, LM.C("#2e7d4f"), LM.Roof);
            for (int i = 0; i < 4; i++) k.Cylinder(new Vector3(150f + (i % 2) * 22f, 0.3f, 60f + (i / 2) * 22f), 9f, 18f, 20, Concrete, LM.Solid, 4f, MetalG, LM.Metal, 1.5f);
            k.Cylinder(new Vector3(160f, 0.3f, -40f), 2.4f, 62f, 14, LM.C("#d8d4cc"), LM.Solid, 4f, Steel, LM.Steel);
            k.Box(new Vector3(160f, 56f, -40f), new Vector3(5.2f, 3f, 5.2f), 0, Red, LM.Solid, 3f, Red, LM.Roof);
            k.Prism(LandmarkKit.Rect(-140f, 90f, 120f, 40f), 0.3f, 10f, MetalG, LM.Metal, 4f, Roof, LM.Roof);            // pulp / bale store
            k.Prism(LandmarkKit.RoundRect(-170f, -100f, 60f, 20f, 3f, 2), 0.3f, 11f, GlassBlue, LM.Glass, 3.6f, Roof, LM.Roof);
            for (int i = 0; i < 8; i++) Truck(k, new Vector3(-100f + i * 17f, 0.3f, -96f), 90f, White);
            Lot(k, 40f, 130f, -136f, -112f, 0.7f, 11f);
        }

        // ------------------------------------------------------------------ flexible packaging plant
        static void Packaging(LandmarkKit k)
        {
            Pad(k, 300f, 200f, 10f, PaveDark);
            k.Prism(LandmarkKit.Rect(-10f, 15f, 170f, 86f), 0.3f, 13f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            for (int i = 0; i < 6; i++) k.Box(new Vector3(-80f + i * 28f, 13.5f, 15f), new Vector3(3.5f, 1f, 70f), 0, GlassBlue, LM.Glass, 1f, GlassBlue, LM.Glass);
            k.Box(new Vector3(-10f, 10.8f, 15f - 43.4f), new Vector3(170f, 2f, 0.6f), 0, LM.C("#7a2d8c"), LM.Solid, 3f, LM.C("#7a2d8c"), LM.Roof);
            k.Prism(LandmarkKit.RoundRect(-95f, -62f, 48f, 18f, 3f, 2), 0.3f, 10f, GlassBlue, LM.Glass, 3.4f, Roof, LM.Roof);
            Silos(k, 95f, 60f, 3, 3.2f, 16f, MetalW);
            for (int i = 0; i < 5; i++) Truck(k, new Vector3(20f + i * 15f, 0.3f, -60f), 90f, White);
            Lot(k, -140f, -60f, -96f, -76f, 0.7f, 21f);
        }

        // ------------------------------------------------------------------ rail-road terminal (TLC Zhetygen): sidings, gantry cranes, container stacks
        static void RailTerminal(LandmarkKit k)
        {
            Pad(k, 520f, 220f, 8f, Gravel, LM.Roof);
            for (int r = 0; r < 4; r++)
            {
                float z = -60f + r * 6f;
                k.Beam(new Vector3(-250f, 0.55f, z - 0.75f), new Vector3(250f, 0.55f, z - 0.75f), 0.15f, 0.18f, Steel, LM.Steel);
                k.Beam(new Vector3(-250f, 0.55f, z + 0.75f), new Vector3(250f, 0.55f, z + 0.75f), 0.15f, 0.18f, Steel, LM.Steel);
                // a train of flat wagons with containers on two of the sidings
                if (r % 2 == 0) for (int w = 0; w < 16; w++)
                {
                    float x = -200f + w * 15.5f;
                    k.Box(new Vector3(x, 1.3f, z), new Vector3(14.5f, 0.9f, 2.6f), 0, Steel, LM.Steel, 1f, Steel, LM.Steel);
                    Color32 cc = (w * 5 + r) % 4 == 0 ? LM.C("#b5442c") : (w * 5 + r) % 4 == 1 ? LM.C("#2f5d8a") : (w * 5 + r) % 4 == 2 ? LM.C("#d9d4c7") : LM.C("#3f7a4f");
                    k.Box(new Vector3(x, 3.05f, z), new Vector3(12.2f, 2.6f, 2.44f), 0, cc, LM.Metal, 3f, cc, LM.Metal);
                }
            }
            // container stacks
            for (int i = 0; i < 14; i++) for (int j = 0; j < 6; j++)
            {
                int hgt = 1 + (i * 3 + j * 7) % 3;
                Color32 cc = (i + j * 3) % 5 == 0 ? LM.C("#b5442c") : (i + j * 3) % 5 == 1 ? LM.C("#2f5d8a") : (i + j * 3) % 5 == 2 ? LM.C("#d9d4c7") : (i + j * 3) % 5 == 3 ? LM.C("#3f7a4f") : LM.C("#c58b2a");
                k.Box(new Vector3(-160f + i * 13.5f, 0.3f + hgt * 1.3f, -12f + j * 3.1f), new Vector3(12.2f, hgt * 2.6f, 2.44f), 0, cc, LM.Metal, 2.6f, cc, LM.Metal);
            }
            // two rail-mounted gantry cranes over sidings and stacks
            for (int g = 0; g < 2; g++)
            {
                float x = -60f + g * 110f; var col = LM.C("#e8b52a");
                for (int s = -1; s <= 1; s += 2)
                {
                    k.Beam(new Vector3(x + s * 9f, 0.3f, -66f), new Vector3(x + s * 9f, 24f, -66f), 1.1f, 1.1f, col, LM.Metal);
                    k.Beam(new Vector3(x + s * 9f, 0.3f, 10f), new Vector3(x + s * 9f, 24f, 10f), 1.1f, 1.1f, col, LM.Metal);
                    k.Beam(new Vector3(x + s * 9f, 24f, -70f), new Vector3(x + s * 9f, 24f, 14f), 1.4f, 1.8f, col, LM.Metal);
                }
                k.Box(new Vector3(x, 22f, -40f), new Vector3(20f, 2.2f, 5f), 0, col, LM.Metal, 2f, col, LM.Metal);
            }
            k.Prism(LandmarkKit.Rect(120f, 60f, 180f, 60f), 0.3f, 13f, MetalW, LM.Metal, 4f, Roof, LM.Roof);
            k.Prism(LandmarkKit.RoundRect(-200f, 70f, 46f, 16f, 3f, 2), 0.3f, 10f, GlassBlue, LM.Glass, 3.4f, Roof, LM.Roof);
            for (int i = 0; i < 8; i++) Truck(k, new Vector3(40f + i * 16f, 0.3f, 22f), 90f, i % 2 == 0 ? White : LM.C("#2f5d8a"));
        }

        // ------------------------------------------------------------------ 220/110 kV substation: the same model as the presentation step
        // «Прогноз: энергия 2034» (SubstationModel) — gravel yard, switchyards, transformers, control building, masts — on the landmark's
        // levelled plot; the 220 kV line and the access road are a separate object outside the plot (SubstationModel.AttachOutside).
        static void Substation(LandmarkKit k, float seed)
        {
            Landmark l = null;
            var ls = LandmarkSystem.Instance;
            if (ls != null) foreach (var x in ls.Items) if (x.Model == "substation" && Mathf.Abs(x.X * 0.001f - seed) < 1e-4f) { l = x; break; }
            if (l == null) { Debug.LogWarning("[Alatau] substation landmark not found"); return; }
            float level = l.Base != 0f ? l.Base : CityGround.HeightAt(l.X, l.Z);
            var site = new Vector2(l.X, l.Z);
            SubstationModel.FillYard(k, site, l.Yaw, level);
            SubstationModel.AttachOutside(l.Id, site, l.Yaw, level);
        }

        // ------------------------------------------------------------------ gas-turbine power plant 2 × 250 MW (H2-ready)
        static void PowerPlant(LandmarkKit k)
        {
            Pad(k, 340f, 240f, 8f, PaveDark);
            for (int u = 0; u < 2; u++)
            {
                float z = -45f + u * 80f;
                k.Prism(LandmarkKit.Rect(-70f, z, 90f, 38f), 0.3f, 28f, MetalW, LM.Metal, 4f, Roof, LM.Roof);           // turbine hall
                k.Prism(LandmarkKit.Rect(10f, z, 60f, 26f), 0.3f, 32f, MetalG, LM.Metal, 4f, Roof, LM.Roof);            // HRSG
                k.Cylinder(new Vector3(52f, 0.3f, z), 4f, 60f, 16, LM.C("#cfd2d4"), LM.Metal, 4f, Steel, LM.Steel);
                k.Box(new Vector3(52f, 57f, z), new Vector3(8.6f, 2.4f, 8.6f), 0, Red, LM.Solid, 2f, Red, LM.Roof);
            }
            // air-cooled condenser: a deck of fans on legs
            k.Box(new Vector3(115f, 18f, -5f), new Vector3(70f, 4f, 120f), 0, MetalG, LM.Metal, 2f, Steel, LM.Steel);
            for (int i = 0; i < 4; i++) for (int j = 0; j < 7; j++) k.Cylinder(new Vector3(92f + i * 15f, 20f, -55f + j * 16.5f), 5.5f, 1.4f, 16, MetalW, LM.Metal, 1f, Steel, LM.Steel);
            for (int i = 0; i < 4; i++) for (int j = 0; j < 4; j++) k.Beam(new Vector3(85f + i * 20f, 0.3f, -60f + j * 36f), new Vector3(85f + i * 20f, 16f, -60f + j * 36f), 1.2f, 1.2f, Concrete, LM.Solid);
            for (int i = 0; i < 2; i++) k.Cylinder(new Vector3(-140f, 0.3f, -60f + i * 30f), 10f, 14f, 20, MetalW, LM.Metal, 3f, MetalG, LM.Metal, 1.5f);
            k.Prism(LandmarkKit.Rect(-120f, 85f, 50f, 20f), 0.3f, 10f, GlassBlue, LM.Glass, 3.6f, Roof, LM.Roof);
        }

        // ------------------------------------------------------------------ university campus (KAIST Kazakhstan), after the KAIST campus in Daejeon:
        // a park campus — lawns, alleys and a lake with an island and fountains laid out first (green from the start of the works), the
        // main hall in the manner of the Academic Cultural Complex (a blue glass box with a white grid of mullions lifted on white columns
        // over a recessed lobby, a white terrace with a stair and a ramp, glass pyramid roof lights, a reflecting pool with jets in front),
        // the library and research tower B1 with a sloping west face, white floor bands, vertical fins and a glass pyramid on a roof garden,
        // the laboratories as a comb of teal-glass wings with green roofs around planted courts, the curved north teaching block, the
        // athletics oval with a stand. Only the aprons of the buildings are an earth site while they are built.
        static readonly Color32 CampusBlue = LM.C("#25557e"), SkyGlass = LM.C("#4f86ad"), Pond = LM.C("#2c5d63"), Track = LM.C("#b3573f"),
            CampusTurf = LM.C("#4f8a43"), Spray = LM.C("#eef7fc"), HedgeG = LM.C("#46683a"), Rim = LM.C("#d8d3c8");
        const float GT = LandmarkKit.GreenTag;

        static List<Vector2> Ellipse(float cx, float cz, float rx, float rz, int seg, float wob = 0f, float ph = 0f)
        {
            var l = new List<Vector2>();
            for (int s = 0; s < seg; s++)
            {
                float a = s * 2f * Mathf.PI / seg, f = 1f + wob * Mathf.Sin(a * 3f + ph) + wob * 0.6f * Mathf.Sin(a * 5f + ph * 1.7f);
                l.Add(new Vector2(cx + Mathf.Cos(a) * rx * f, cz + Mathf.Sin(a) * rz * f));
            }
            return l;
        }
        /// <summary>A band between two outlines with the same number of corners (a rim, a ring path, a walk along the edge).</summary>
        static void Band(LandmarkKit k, List<Vector2> inner, List<Vector2> outer, float y0, float y1, Color32 side, Color32 top, int topMat, float prm)
        {
            for (int i = 0; i < inner.Count; i++)
            {
                int j = (i + 1) % inner.Count;
                k.Prism(new List<Vector2> { inner[i], inner[j], outer[j], outer[i] }, y0, y1, side, LM.Solid, prm, top, topMat, false, prm);
            }
        }
        /// <summary>A straight path a → b, w wide, paving on a low stone kerb.</summary>
        static void Walk(LandmarkKit k, Vector2 a, Vector2 b, float w, float prm = GT, float y1 = 0.45f)
        {
            var d = (b - a).normalized; var n = new Vector2(-d.y, d.x) * (w * 0.5f);
            k.Prism(new List<Vector2> { a - n, b - n, b + n, a + n }, 0.3f, y1, Rim, LM.Solid, prm, Pave, LM.Paving, false, prm);
        }
        /// <summary>A fountain jet from (x, y, z), h high; tall ones drop a crown of spray around them.</summary>
        static void Jet(LandmarkKit k, float x, float z, float y, float h, float prm)
        {
            float r = Mathf.Clamp(h * 0.045f, 0.12f, 0.75f);
            k.Tube(new Vector3(x, y, z), new Vector3(x, y + h, z), r, r * 0.3f, 6, Spray, LM.Light, true, prm);
            if (h < 6f) return;
            var top = new Vector3(x, y + h * 0.82f, z);
            for (int i = 0; i < 6; i++)
            {
                float a = (i * 60f + 15f) * Mathf.Deg2Rad; var dir = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                var mid = new Vector3(x, y + h * 0.62f, z) + dir * (h * 0.2f); var end = new Vector3(x, y + 0.1f, z) + dir * (h * 0.3f);
                k.Tube(top, mid, r * 0.45f, r * 0.35f, 5, Spray, LM.Light, false, prm);
                k.Tube(mid, end, r * 0.35f, r * 0.12f, 5, Spray, LM.Light, false, prm);
            }
        }
        static void Lamp(LandmarkKit k, float x, float z)
        {
            k.Prism(LandmarkKit.Rect(x, z, 0.22f, 0.22f), 0.3f, 4.3f, Steel, LM.Steel, GT, Steel, -1);
            k.Prism(LandmarkKit.Rect(x, z, 0.7f, 0.7f), 4.3f, 4.7f, Warm, LM.Light, GT, Warm, LM.Light, false, GT);
        }
        static void ParkTree(LandmarkKit k, float x, float z, float h, float seed)
        {
            k.Planted = true; k.Tree(new Vector3(x, 0.4f, z), h, (Mathf.FloorToInt(seed * 7f) & 1) == 0 ? Leaf : Leaf2, seed); k.Planted = false;
        }
        static float Hash(float x, float z) => Mathf.Repeat(Mathf.Sin(x * 12.9898f + z * 78.233f) * 43758.5453f, 1f);
        /// <summary>A sector of a ring (centre c, radii r0..r1, angles a0..a1 in degrees) as a four-corner footprint.</summary>
        static List<Vector2> Sector(Vector2 c, float r0, float r1, float a0, float a1)
        {
            float b0 = a0 * Mathf.Deg2Rad, b1 = a1 * Mathf.Deg2Rad;
            Vector2 d0 = new Vector2(Mathf.Cos(b0), Mathf.Sin(b0)), d1 = new Vector2(Mathf.Cos(b1), Mathf.Sin(b1));
            return new List<Vector2> { c + d0 * r0, c + d1 * r0, c + d1 * r1, c + d0 * r1 };
        }

        static void Campus(LandmarkKit k)
        {
            // ---- the ground: one lawn over the whole plot (a plinth buried in the slope), a walk and a double alley round the edge
            // (part 6 = the park of LandmarkData's KAIST campus: built first, in a few months, on its own windows — Wbs.P*)
            k.Part = 6; W(k, Wbs.PGround, 0f, 0.4f);
            k.Prism(LandmarkKit.RoundRect(0, 0, 420f, 360f, 30f, 5), -16f, 0.3f, PaveDark, LM.Solid, GT, Grass, LM.Plant, false, GT);
            W(k, Wbs.PPaths, 0f, 0.5f);
            Band(k, LandmarkKit.RoundRect(0, 0, 392f, 332f, 20f, 5), LandmarkKit.RoundRect(0, 0, 402f, 342f, 25f, 5), 0.3f, 0.45f, Rim, Pave, LM.Paving, GT);

            // ---- the lake with an island, a footbridge and fountains; a ring path with lamps round it
            Vector2 lc = new Vector2(-15f, -5f); float lrx = 64f, lrz = 36f;
            var shore = Ellipse(lc.x, lc.y, lrx, lrz, 40, 0.05f, 0.7f);
            W(k, Wbs.PLake, 0f, 0.6f);
            k.Prism(shore, 0.15f, 0.34f, Rim, LM.Solid, GT, Pond, LM.Water, false, GT);
            Band(k, shore, Ellipse(lc.x, lc.y, lrx + 1.8f, lrz + 1.8f, 40, 0.05f, 0.7f), 0.3f, 0.55f, Rim, Rim, LM.Paving, GT);
            W(k, Wbs.PPaths, 0f, 0.5f);
            Band(k, Ellipse(lc.x, lc.y, lrx + 10f, lrz + 10f, 48), Ellipse(lc.x, lc.y, lrx + 14f, lrz + 14f, 48), 0.3f, 0.45f, Rim, Pave, LM.Paving, GT);
            W(k, Wbs.PLamps, 0f, 5f);
            for (int i = 0; i < 18; i++) { float a = (i + 0.5f) * 20f * Mathf.Deg2Rad; Lamp(k, lc.x + Mathf.Cos(a) * (lrx + 16f), lc.y + Mathf.Sin(a) * (lrz + 16f)); }
            W(k, Wbs.PLake, 0f, 0.9f);
            k.Prism(Ellipse(8f, 10f, 13f, 8.5f, 18, 0.08f, 2.1f), 0.2f, 0.85f, GrassDark, LM.Solid, GT, Grass, LM.Plant, false, GT);
            W(k, Wbs.PTrees, 0f, 12f);
            ParkTree(k, 4f, 10f, 11f, 0.31f); ParkTree(k, 12f, 13f, 9.5f, 0.57f); ParkTree(k, 10f, 6f, 8f, 0.83f);
            W(k, Wbs.PPaths, 0f, 2.2f);
            k.Prism(LandmarkKit.Rect(8f, 26f, 3.2f, 18f), 0.3f, 1.05f, White, LM.Solid, GT, Stone, LM.Paving, false, GT);            // footbridge to the island
            k.Beam(new Vector3(6.4f, 2.0f, 17f), new Vector3(6.4f, 2.0f, 35f), 0.12f, 0.12f, White, LM.Solid, GT);
            k.Beam(new Vector3(9.6f, 2.0f, 17f), new Vector3(9.6f, 2.0f, 35f), 0.12f, 0.12f, White, LM.Solid, GT);
            W(k, Wbs.PLamps, 0f, 18.5f);
            Jet(k, -44f, -6f, 0.34f, 18f, GT);
            for (int i = 0; i < 5; i++) Jet(k, 14f + i * 6f, -12f + (i % 2) * 3f, 0.34f, 5.5f + (i == 2 ? 2.5f : 0f), GT);
            for (int i = 0; i < 6; i++) { float a = i * 60f * Mathf.Deg2Rad; Jet(k, -44f + Mathf.Cos(a) * 9f, -6f + Mathf.Sin(a) * 6f, 0.34f, 4f, GT); }

            // ---- main hall: a blue glass box with a white grid, lifted on white columns over a recessed lobby
            // (parts of the model = the buildings of LandmarkData's KAIST campus: 1 tower B1, 2 main hall, 3 laboratories, 4 north block, 5 sports)
            k.Part = 2;
            float mx = -20f, mz = -122f, mw = 150f, md = 56f;
            W(k, Wbs.MApron, 0f, 0.4f);
            k.Prism(LandmarkKit.RoundRect(mx, mz, mw + 22f, md + 22f, 6f, 3), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);   // apron (an earth site while built)
            W(k, Wbs.MLobby, 0.3f, 9f);
            k.Prism(LandmarkKit.RoundRect(mx, mz - 2f, mw - 30f, md - 16f, 4f, 3), 0.3f, 9f, GlassDark, LM.Glass, 4.4f, Roof, -1);    // lobby
            W(k, Wbs.MCols, 0.38f, 9.1f);
            for (int i = 0; i <= 12; i++) for (int s = 0; s < 2; s++)
                k.Cylinder(new Vector3(mx - mw * 0.5f + 4f + i * (mw - 8f) / 12f, 0.38f, mz + (s == 0 ? -1 : 1) * (md * 0.5f - 3f)), 0.75f, 8.7f, 10, White, LM.Solid, 3f, White, -1);
            W(k, Wbs.MSlab, 9f, 10.2f);
            k.Prism(LandmarkKit.Rect(mx, mz, mw + 2f, md + 2f), 9f, 10.2f, White, LM.Solid, 1.2f, Pave, LM.Paving, true);             // soffit and deck of the transfer slab
            W(k, Wbs.MBox, 10.2f, 28f);
            k.Prism(LandmarkKit.Rect(mx, mz, mw, md), 10.2f, 28f, CampusBlue, LM.Glass, 4.45f, Roof, LM.Roof);
            W(k, Wbs.MRoof, 28f, 29.2f);
            k.Prism(LandmarkKit.Rect(mx, mz, mw + 2f, md + 2f), 28f, 29.2f, White, LM.Solid, 1.2f, White, LM.Roof);                    // cornice
            W(k, Wbs.MGrid, 10.2f, 28f);
            float hx = mw * 0.5f + 0.3f, hz = md * 0.5f + 0.3f;
            for (int i = 0; i <= 20; i++)
            {
                float x = mx - mw * 0.5f + i * mw / 20f;
                k.Beam(new Vector3(x, 10.2f, mz - hz), new Vector3(x, 28f, mz - hz), 0.55f, 0.5f, White, LM.Solid, 1f);
                k.Beam(new Vector3(x, 10.2f, mz + hz), new Vector3(x, 28f, mz + hz), 0.55f, 0.5f, White, LM.Solid, 1f);
            }
            for (int i = 1; i < 8; i++)
            {
                float z = mz - md * 0.5f + i * md / 8f;
                k.Beam(new Vector3(mx - hx, 10.2f, z), new Vector3(mx - hx, 28f, z), 0.5f, 0.55f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx + hx, 10.2f, z), new Vector3(mx + hx, 28f, z), 0.5f, 0.55f, White, LM.Solid, 1f);
            }
            for (int f = 1; f < 4; f++)
            {
                float y = 10.2f + f * 4.45f;
                k.Beam(new Vector3(mx - hx, y, mz - hz), new Vector3(mx + hx, y, mz - hz), 0.5f, 0.45f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx - hx, y, mz + hz), new Vector3(mx + hx, y, mz + hz), 0.5f, 0.45f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx - hx, y, mz - hz), new Vector3(mx - hx, y, mz + hz), 0.5f, 0.45f, White, LM.Solid, 1f);
                k.Beam(new Vector3(mx + hx, y, mz - hz), new Vector3(mx + hx, y, mz + hz), 0.5f, 0.45f, White, LM.Solid, 1f);
            }
            // glass pyramid roof lights: a large one over the atrium, two small ones
            float[,] pyr = { { 0f, 44f, 26f, 10f }, { -46f, 16f, 16f, 6f }, { 44f, 16f, 16f, 6f } };
            W(k, Wbs.MRoof, 29.2f, 39.8f);
            for (int i = 0; i < 3; i++)
            {
                float px = mx + pyr[i, 0], w = pyr[i, 1], d = pyr[i, 2], h = pyr[i, 3], y0 = 29.2f;
                k.Prism(LandmarkKit.Rect(px, mz, w + 2f, d + 2f), y0, y0 + 0.6f, White, LM.Solid, 1f, White, LM.Roof);
                k.Loft(LandmarkKit.Rect(px, mz, w, d), y0 + 0.6f, LandmarkKit.Rect(px, mz, w * 0.02f, d * 0.02f), y0 + 0.6f + h, SkyGlass, LM.Glass, 2.2f);
                var ap = new Vector3(px, y0 + 0.6f + h, mz);
                for (int c = 0; c < 4; c++) k.Beam(new Vector3(px + (c % 2 == 0 ? -1 : 1) * w * 0.5f, y0 + 0.6f, mz + (c < 2 ? -1 : 1) * d * 0.5f), ap, 0.35f, 0.35f, White, LM.Solid, 1f);
            }
            // the white terrace along the front, a broad stair down to the plaza, a ramp at the west end
            float tz = mz + md * 0.5f + 5f;
            W(k, Wbs.MTerr, 0.3f, 5.5f);
            k.Prism(LandmarkKit.Rect(mx, tz, 124f, 10f), 0.3f, 4.2f, White, LM.Solid, 1.3f, Stone, LM.Paving);
            for (int i = 0; i < 8; i++)
                k.Prism(LandmarkKit.Rect(mx, tz + 5f + 0.75f + i * 1.5f, 32f, 1.5f), 0.3f, 4.2f - (i + 1) * 0.49f, White, LM.Solid, 0.5f, Stone, LM.Paving);
            float rx0 = mx - 62f, rz = tz;
            k.Slab(new Vector3(rx0, 4.0f, rz - 3f), new Vector3(rx0 - 34f, 0.5f, rz - 3f), new Vector3(rx0 - 34f, 0.5f, rz + 3f), new Vector3(rx0, 4.0f, rz + 3f), 0.5f, White, LM.Solid);
            k.Beam(new Vector3(rx0, 5.2f, rz - 3f), new Vector3(rx0 - 34f, 1.7f, rz - 3f), 0.25f, 0.25f, White, LM.Solid);
            k.Beam(new Vector3(rx0, 5.2f, rz + 3f), new Vector3(rx0 - 34f, 1.7f, rz + 3f), 0.25f, 0.25f, White, LM.Solid);
            k.Beam(new Vector3(mx - 62f, 5.2f, tz + 5f), new Vector3(mx - 16f, 5.2f, tz + 5f), 0.2f, 0.25f, White, LM.Solid);   // terrace rail
            k.Beam(new Vector3(mx + 16f, 5.2f, tz + 5f), new Vector3(mx + 62f, 5.2f, tz + 5f), 0.2f, 0.25f, White, LM.Solid);
            // the plaza with a reflecting pool and a row of jets, hedges and trees on its sides (finished with the landscaping)
            float pz = tz + 5f + 12f + 10f;
            W(k, Wbs.MPlaza, 0.3f, 9f);
            k.Prism(LandmarkKit.Rect(mx, pz, 150f, 20f), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Stone, LM.Paving);
            k.Prism(LandmarkKit.Rect(mx, pz, 96f, 10f), 0.3f, 0.75f, Rim, LM.Solid, 1f, Rim, LM.Paving);
            k.Prism(LandmarkKit.Rect(mx, pz, 93f, 7f), 0.3f, 0.62f, Rim, LM.Solid, 1f, Pond, LM.Water);
            for (int i = 0; i < 12; i++) Jet(k, mx - 41.25f + i * 7.5f, pz, 0.62f, 3.2f, LandmarkKit.TreeTag);
            for (int s = -1; s <= 1; s += 2)
            {
                k.Prism(LandmarkKit.Rect(mx + s * 64f, pz, 16f, 1.4f), 0.38f, 1.4f, HedgeG, LM.Plant, LandmarkKit.TreeTag, HedgeG, LM.Plant, false, LandmarkKit.TreeTag);
                for (int i = 0; i < 3; i++) k.Tree(new Vector3(mx + s * (58f + i * 6f), 0.4f, pz + 5.5f), 8.5f, Leaf2, 0.2f + i * 0.17f + s);
            }

            // ---- library and research tower B1: the floors follow the tower profile (the interior and the monitoring use the same plates)
            k.Part = 1; k.NoWin();
            var keepP = IconicShape.P; IconicShape.P = TowerProfile.Kaist;
            try
            {
                float Xr = IconicShape.Xr, Cz = IconicShape.Cz, top = IconicShape.Roof, cx = Xr - IconicShape.RawWidth(top) * 0.5f;
                k.Prism(LandmarkKit.RoundRect(Xr - 22f, Cz, 84f, 74f, 6f, 3), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);   // apron
                for (int i = 0; i < IconicShape.Levels; i++)
                {
                    float y0 = IconicShape.FloorY(i), y1 = i == IconicShape.Levels - 1 ? top : IconicShape.FloorY(i + 1);
                    k.Loft(IconicShape.Ring(y0), y0, IconicShape.Ring(y1), y1, i == 0 ? GlassDark : GlassTeal, LM.Glass, IconicShape.Fh);
                    if (i > 0) k.Prism(IconicShape.Inset(y0, -0.45f), y0 - 0.3f, y0 + 0.35f, White, LM.Solid, 0.65f, White, -1);   // white floor band
                }
                k.Prism(IconicShape.Inset(top, -0.45f), top - 0.3f, top + 1.3f, White, LM.Solid, 1.6f, White, LM.Roof);            // parapet and roof
                k.Prism(IconicShape.Inset(top, 3.5f), top + 1.3f, top + 1.75f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);           // roof garden
                k.Prism(LandmarkKit.Rect(cx, Cz, 15f, 15f), top + 1.3f, top + 2f, White, LM.Solid, 1f, White, LM.Roof);
                k.Loft(LandmarkKit.Rect(cx, Cz, 14f, 14f), top + 2f, LandmarkKit.Rect(cx, Cz, 0.3f, 0.3f), top + 11f, SkyGlass, LM.Glass, 2.2f);
                for (int c = 0; c < 4; c++) k.Beam(new Vector3(cx + (c % 2 == 0 ? -7f : 7f), top + 2f, Cz + (c < 2 ? -7f : 7f)), new Vector3(cx, top + 11f, Cz), 0.3f, 0.3f, White, LM.Solid, 1f);
                // vertical white fins on the straight east face, a canopy over the west entrance
                float d0 = IconicShape.D0 * 0.5f - IconicShape.P.Chamfer - 0.5f;
                for (float z = -d0; z <= d0 + 0.01f; z += 2.5f) k.Beam(new Vector3(Xr + 0.45f, 0.3f, Cz + z), new Vector3(Xr + 0.45f, top + 1.3f, Cz + z), 0.25f, 0.9f, White, LM.Solid, 1f);
                float wx = Xr - IconicShape.RawWidth(5f);
                k.Prism(LandmarkKit.Rect(wx - 8.5f, Cz, 18f, 14f), 5.2f, 5.8f, White, LM.Solid, 1f, White, LM.Roof, true);
                k.Beam(new Vector3(wx - 16f, 0.38f, Cz - 6f), new Vector3(wx - 16f, 5.2f, Cz - 6f), 0.5f, 0.5f, White, LM.Solid);
                k.Beam(new Vector3(wx - 16f, 0.38f, Cz + 6f), new Vector3(wx - 16f, 5.2f, Cz + 6f), 0.5f, 0.5f, White, LM.Solid);
                foreach (float x in new[] { 120f, 132f, 168f, 180f }) k.Tree(new Vector3(x, 0.4f, Cz - 30f), 9f, Leaf, x * 0.013f);
            }
            finally { IconicShape.P = keepP; }

            // ---- laboratories: a spine with three teal-glass wings (stepped, with green roofs) around planted courts
            k.Part = 3;
            W(k, Wbs.Apron, 0f, 0.4f);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 32f, 204f), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
            W(k, Wbs.LSpine, 0.3f, 18.6f);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 22f, 190f), 0.3f, 17f, GlassTeal, LM.Fins, 4.2f, White, LM.Roof);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 23.5f, 191.5f), 17f, 18.2f, White, LM.Solid, 1.2f, White, LM.Roof);
            k.Prism(LandmarkKit.Rect(-178f, 25f, 16f, 182f), 18.2f, 18.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            for (int i = 0; i < 3; i++)
            {
                float z = -45f + i * 60f, hi = 14.5f - (i == 1 ? 0f : 2f);
                W(k, Wbs.Apron, 0f, 0.4f);
                k.Prism(LandmarkKit.Rect(-140f, z, 60f, 28f), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
                W(k, Wbs.LWing[i], 0.3f, hi + 0.4f);
                k.Prism(LandmarkKit.Rect(-153f, z, 28f, 18f), 0.3f, hi, GlassTeal, LM.Fins, 3.6f, White, LM.Roof);
                k.Prism(LandmarkKit.Rect(-125f, z, 28f, 18f), 0.3f, hi - 4f, GlassTeal, LM.Fins, 3.6f, White, LM.Roof);
                k.Prism(LandmarkKit.Rect(-153f, z, 25f, 15f), hi, hi + 0.4f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
                k.Prism(LandmarkKit.Rect(-125f, z, 25f, 15f), hi - 4f, hi - 3.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
                k.Box(new Vector3(-111.3f, (hi - 4f) * 0.5f + 0.15f, z), new Vector3(0.6f, hi - 4.3f, 18.6f), 0, White, LM.Solid, 1f, White, LM.Roof);
                if (i < 2)
                {
                    float cz = z + 30f;                                                           // the court between two wings
                    W(k, Wbs.LCourts, 0f, 9f);
                    Walk(k, new Vector2(-166f, cz), new Vector2(-104f, cz), 3.5f);
                    for (int t = 0; t < 4; t++) { k.Tree(new Vector3(-158f + t * 14f, 0.4f, cz - 9f), 8f, Leaf2, t * 0.21f + i); k.Tree(new Vector3(-158f + t * 14f, 0.4f, cz + 9f), 8f, Leaf, t * 0.37f + i); }
                }
            }

            // ---- north teaching block: a curved glass block with white fins and a green roof, facing the lake
            k.Part = 4;
            var ac = new Vector2(-15f, -40f); const float A0 = 58f, A1 = 122f; const int NS = 16;
            for (int s = 0; s < NS; s++)
            {
                float a0 = A0 + (A1 - A0) * s / NS, a1 = A0 + (A1 - A0) * (s + 1) / NS;
                // sectors (захватки) from the west end: the arc is cast four segments at a time, the green roof goes on last
                var sec = Wbs.NSector[Mathf.Min(3, (NS - 1 - s) * 4 / NS)];
                W(k, Wbs.Apron, 0f, 0.4f);
                k.Prism(Sector(ac, 153f, 183f, a0, a1), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
                W(k, sec, 0.3f, 19.2f);
                k.Prism(Sector(ac, 160f, 176f, a0, a1), 0.3f, 18f, CampusBlue, LM.Glass, 4.2f, Roof, -1);
                k.Prism(Sector(ac, 158.5f, 177.5f, a0, a1), 18f, 19.2f, White, LM.Solid, 1.2f, White, LM.Roof, true);
                for (int f = 1; f < 3; f++) k.Prism(Sector(ac, 159.6f, 176.4f, a0, a1), f * 6f - 0.2f, f * 6f + 0.35f, White, LM.Solid, 0.55f, White, -1);
                W(k, Wbs.NRoof, 19.2f, 19.6f);
                k.Prism(Sector(ac, 163f, 173f, a0, a1), 19.2f, 19.6f, GrassDark, LM.Solid, 1f, Grass, LM.Plant);
            }
            for (int s = 0; s <= NS * 2; s++)
            {
                float a = (A0 + (A1 - A0) * s / (NS * 2)) * Mathf.Deg2Rad; var dir = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                var pi = ac + dir * 159.5f; var po = ac + dir * 176.5f;
                W(k, Wbs.NSector[Mathf.Min(3, (NS * 2 - s) * 4 / (NS * 2 + 1))], 0.3f, 18f);
                k.Beam(new Vector3(pi.x, 0.3f, pi.y), new Vector3(pi.x, 18f, pi.y), 0.35f, 0.35f, White, LM.Solid, 1f);
                k.Beam(new Vector3(po.x, 0.3f, po.y), new Vector3(po.x, 18f, po.y), 0.35f, 0.35f, White, LM.Solid, 1f);
            }

            // ---- athletics: an oval track round a pitch, a stand with a canopy
            k.Part = 5;
            float sx = 140f, sz = -122f;
            W(k, Wbs.Apron, 0f, 0.4f);
            k.Prism(LandmarkKit.RoundRect(sx, sz, 124f, 80f, 38f, 6), 0.3f, 0.38f, PaveDark, LM.Solid, 3f, Pave, LM.Paving);
            W(k, Wbs.STrack, 0.38f, 0.5f);
            k.Prism(LandmarkKit.RoundRect(sx, sz, 112f, 68f, 34f, 6), 0.38f, 0.5f, Track, LM.Solid, 1f, Track, LM.Roof);
            W(k, Wbs.SPitch, 0.5f, 0.56f);
            k.Prism(LandmarkKit.RoundRect(sx, sz, 86f, 42f, 21f, 6), 0.5f, 0.56f, CampusTurf, LM.Solid, 1f, CampusTurf, LM.Plant);
            W(k, Wbs.SStand, 0.38f, 4.6f);
            for (int i = 0; i < 5; i++) k.Prism(LandmarkKit.Rect(sx, sz + 36f + i * 1.6f, 64f, 1.6f), 0.38f, 1.0f + i * 0.9f, Concrete, LM.Solid, 0.9f, White, LM.Paving);
            W(k, Wbs.SCanopy, 0.38f, 9.1f);
            k.Prism(LandmarkKit.Rect(sx, sz + 39f, 68f, 10f), 8.6f, 9.1f, White, LM.Solid, 1f, White, LM.Roof, true);
            for (int i = 0; i < 5; i++) k.Beam(new Vector3(sx - 32f + i * 16f, 0.38f, sz + 44f), new Vector3(sx - 32f + i * 16f, 8.6f, sz + 44f), 0.5f, 0.5f, White, LM.Solid);

            // ---- paths linking the lake, the halls, the tower and the sports ground
            k.Part = 6; W(k, Wbs.PPaths, 0f, 0.5f);
            Walk(k, new Vector2(lc.x + lrx + 12f, lc.y + 4f), new Vector2(112f, 20f), 5f);
            Walk(k, new Vector2(85f, 9f), new Vector2(112f, sz + 47f), 5f);          // to the sports ground: branches off the path to the tower, west of its apron
            Walk(k, new Vector2(lc.x, lc.y + lrz + 12f), new Vector2(lc.x, 118f), 6f);
            Walk(k, new Vector2(lc.x - lrx - 12f, lc.y - 4f), new Vector2(-104f, -15f), 5f);
            Walk(k, new Vector2(lc.x + 40f, lc.y + lrz + 6f), new Vector2(92f, 88f), 4f);
            Walk(k, new Vector2(lc.x - 40f, lc.y + lrz + 6f), new Vector2(-104f, 86f), 4f);

            // ---- the park trees: a double alley along the edge walk and groves on the lawns, kept off the buildings, paths and the lake
            bool Busy(float x, float z) => Mathf.Abs(x) > 196f || Mathf.Abs(z) > 166f || Bld(x, z);
            bool Bld(float x, float z)
            {
                if (x > mx - 92f && x < mx + 92f && z > mz - 39f && z < pz + 14f) return true;                                  // main hall, terrace, plaza
                if (x > 100f && x < 196f && z > -22f && z < 62f) return true;                                                     // tower apron
                if (x > -200f && x < -102f && z > -82f && z < 132f) return true;                                                   // laboratories
                if (x > 72f && x < 203f && z > -168f && z < -74f) return true;                                                     // sports
                if (x > -112f && x < -68f && z > tz - 9f && z < tz + 9f) return true;                                              // ramp
                float r = Vector2.Distance(new Vector2(x, z), ac), an = Mathf.Atan2(z - ac.y, x - ac.x) * Mathf.Rad2Deg;
                if (r > 146f && r < 190f && an > A0 - 4f && an < A1 + 4f) return true;                                             // north block
                float ex = (x - lc.x) / (lrx + 18f), ez = (z - lc.y) / (lrz + 18f); if (ex * ex + ez * ez < 1f) return true;     // lake, ring path
                return false;
            }
            float DistSeg(Vector2 p, Vector2 a, Vector2 b) { var ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude); return Vector2.Distance(p, a + ab * t); }
            Vector2[] paths =
            {
                new Vector2(lc.x + lrx + 12f, lc.y + 4f), new Vector2(112f, 20f),
                new Vector2(85f, 9f), new Vector2(112f, sz + 47f), new Vector2(lc.x, lc.y + lrz + 12f), new Vector2(lc.x, 118f),
                new Vector2(lc.x - lrx - 12f, lc.y - 4f), new Vector2(-104f, -15f), new Vector2(lc.x + 40f, lc.y + lrz + 6f), new Vector2(92f, 88f),
                new Vector2(lc.x - 40f, lc.y + lrz + 6f), new Vector2(-104f, 86f)
            };
            bool OnPath(float x, float z, float m) { var p = new Vector2(x, z); for (int i = 0; i < paths.Length; i += 2) if (DistSeg(p, paths[i], paths[i + 1]) < m) return true; return false; }
            // the alley: two rows along the edge walk (the park's last stage: planting)
            W(k, Wbs.PTrees, 0.3f, 14f);
            foreach (float off in new[] { 192f, 205f })
            {
                float hw = off, hd = off - 30f;
                for (float x = -hw + 14f; x <= hw - 14f; x += 12f) foreach (float z in new[] { -hd, hd }) { if (!OnPath(x, z, 4f) && !Bld(x, z)) ParkTree(k, x, z, 10f + 2f * Hash(x, z), Hash(z, x)); }
                for (float z = -hd + 12f; z <= hd - 12f; z += 12f) foreach (float x in new[] { -hw, hw }) { if (!OnPath(x, z, 4f) && !Bld(x, z)) ParkTree(k, x, z, 10f + 2f * Hash(x, z), Hash(z, x)); }
            }
            // groves: jittered grid, denser near the lake
            for (float x = -184f; x <= 184f; x += 11f) for (float z = -156f; z <= 156f; z += 11f)
            {
                float h = Hash(x * 0.37f, z * 0.71f), jx = (Hash(x, z + 3f) - 0.5f) * 7f, jz = (Hash(x + 5f, z) - 0.5f) * 7f;
                float px = x + jx, qz = z + jz;
                float ex = (px - lc.x) / (lrx + 60f), ez = (qz - lc.y) / (lrz + 60f); float near = ex * ex + ez * ez < 1f ? 0.45f : 0.62f;
                if (h < near || Busy(px, qz) || OnPath(px, qz, 5f)) continue;
                if (Mathf.Abs(px) > 178f || Mathf.Abs(qz) > 148f) continue;                                                      // the alley is there
                ParkTree(k, px, qz, 8f + 5f * Hash(qz, px), h);
            }
            k.Part = 0; k.NoWin();
        }

        // ------------------------------------------------------------------ marina and waterfront club on Kapshagay (Green District concept)
        static void Marina(LandmarkKit k)
        {
            Pad(k, 200f, 140f, 20f, Pave);
            k.Prism(LandmarkKit.RoundRect(-20f, 0, 90f, 34f, 14f, 5), 0.3f, 9.5f, GlassTeal, LM.Glass, 4.6f, White, -1);
            var r0 = LandmarkKit.RoundRect(-20f, 0, 104f, 46f, 20f, 5); var r1 = LandmarkKit.RoundRect(-20f, 0, 86f, 30f, 12f, 5);
            k.Loft(r0, 9.5f, r1, 12f, White, LM.Solid, 1f); k.Cap(r1, 12f, true, White, LM.Roof);
            k.Prism(LandmarkKit.Rect(80f, 0, 40f, 120f), 0.3f, 0.6f, Stone, LM.Solid, 1f, Pave, LM.Paving);        // quay
            // piers out over the water (+x) with moored yachts
            for (int p = 0; p < 4; p++)
            {
                float z = -54f + p * 36f;
                k.Prism(LandmarkKit.Rect(200f, z, 240f, 3.2f), -0.6f, 0.9f, LM.C("#8a7a64"), LM.Solid, 1f, LM.C("#a8977c"), LM.Paving);
                for (int b = 0; b < 9; b++)
                {
                    if ((b + p) % 3 == 1) continue;
                    float x = 110f + b * 25f, side = (b % 2 == 0) ? 7f : -7f; float L = 14f + (b * 3 + p) % 4 * 3f;
                    var hull0 = LandmarkKit.Chamfer(x, z + side, L, 4.2f, 1.6f); var hull1 = LandmarkKit.Chamfer(x + 0.6f, z + side, L - 3f, 2.8f, 1.0f);
                    k.Loft(hull1, -0.3f, hull0, 1.4f, White, LM.Solid, 1f); k.Cap(hull0, 1.4f, true, LM.C("#cdbb98"), LM.Paving);
                    k.Box(new Vector3(x - 1f, 2.4f, z + side), new Vector3(L * 0.45f, 2f, 3f), 0, White, LM.Glass, 1f, White, LM.Roof);
                    if (b % 3 == 0) k.Beam(new Vector3(x, 1.4f, z + side), new Vector3(x, 1.4f + L * 1.3f, z + side), 0.25f, 0.25f, MetalG, LM.Steel);
                }
            }
            Trees(k, -95f, -60f, 60f, -60f, 12f, 8f, 31f); Trees(k, -95f, 60f, 60f, 60f, 12f, 8f, 32f);
            for (int i = 0; i < 8; i++) k.Box(new Vector3(-80f + i * 20f, 3.2f, -36f), new Vector3(0.3f, 6f, 0.3f), 0, Steel, LM.Steel, 1f, Warm, LM.Light);
        }
    }
}
