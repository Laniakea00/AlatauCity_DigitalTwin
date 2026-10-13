using System;
using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Footprint of the Iconic Complex main tower (local frame of the landmark): one vertical face (east, +x), the other leans in.
    /// Shared by the exterior model (LandmarkModels.Iconic) and the interior floors (IconicFloors), so the floors always fit the facade.</summary>
    public static class IconicShape
    {
        public const float Xr = 66f, Cz = 34f, W0 = 60f, D0 = 44f, Roof = 252f, Fh = 4.3f, Base = 0.3f;
        /// <summary>56 floors and 2 levels inside the crown.</summary>
        public const int Levels = 58;
        public static float RawWidth(float y) { float f = Mathf.Clamp01(y / Roof); return W0 * (1f - 0.74f * Mathf.Pow(f, 1.25f)); }
        public static float Depth(float y) { float f = Mathf.Clamp01(y / Roof); return D0 * (1f - 0.28f * f); }
        public static List<Vector2> Ring(float y)
        {
            float w = RawWidth(y), d = Depth(y);
            return LandmarkKit.Chamfer(Xr - w * 0.5f, Cz, Mathf.Max(w, 5f), d, Mathf.Min(5f, w * 0.18f));
        }
        /// <summary>The footprint at height y, moved inward by t metres.</summary>
        public static List<Vector2> Inset(float y, float t)
        {
            float w = RawWidth(y), d = Depth(y);
            return LandmarkKit.Chamfer(Xr - w * 0.5f, Cz, Mathf.Max(w, 5f) - 2f * t, d - 2f * t, Mathf.Max(Mathf.Min(5f, w * 0.18f) - t * 0.41f, 0.2f));
        }
        public static float FloorY(int i) => Base + i * Fh;
    }

    /// <summary>What a floor of the tower is used for, how far its construction has gone in the shown year, and its 3D model:
    /// structure, core, columns, facade frames, building services, partitions, finishes and furniture, built procedurally
    /// for one floor at a time. Illustrative layout (a typical SOM-style supertall plan), not design documentation.</summary>
    public static class IconicFloors
    {
        public enum Use { Lobby, Retail, FoodHall, Conference, Office, Technical, Residence, Restaurant, Lounge, Crown }

        public static Use UseOf(int i)
        {
            if (i == 0) return Use.Lobby;
            if (i <= 2) return Use.Retail;
            if (i == 3) return Use.FoodHall;
            if (i == 4) return Use.Conference;
            if (i == 19 || i == 38) return Use.Technical;
            if (i <= 37) return Use.Office;
            if (i <= 53) return Use.Residence;
            if (i == 54) return Use.Restaurant;
            if (i == 55) return Use.Lounge;
            return Use.Crown;
        }
        public static string Name(int i) => i >= 56 ? "Корона, уровень " + (i - 55) : "Этаж " + (i + 1);
        public static string Short(int i) => i >= 56 ? "К" + (i - 55) : (i + 1).ToString();
        public static string UseName(Use u)
        {
            switch (u)
            {
                case Use.Lobby: return "Главное лобби";
                case Use.Retail: return "Торговая галерея";
                case Use.FoodHall: return "Фуд-холл";
                case Use.Conference: return "Конгресс-зал";
                case Use.Office: return "Офисы класса А";
                case Use.Technical: return "Технический этаж и зона безопасности";
                case Use.Residence: return "Премиальные резиденции";
                case Use.Restaurant: return "Ресторан на высоте";
                case Use.Lounge: return "Смотровой лаунж";
                default: return "Техническое пространство короны";
            }
        }

        // ------------------------------------------------------------------ construction phases of one floor
        public const int PNone = 0, PFrame = 1, PFacade = 2, PServices = 3, PPartitions = 4, PFinishes = 5, PFitOut = 6, PReady = 7;
        public static readonly string[] PhaseName = { "не начат", "каркас", "фасад", "инженерные сети", "перегородки", "отделка", "мебель и оборудование", "готов" };
        /// <summary>Short status of a floor in a phase (for the passport chip).</summary>
        public static readonly string[] PhaseNow = { "этаж ещё не начат", "бетонируют каркас", "монтируют фасад", "прокладывают инженерные сети", "ставят перегородки", "идёт отделка", "завозят мебель и оборудование", "этаж готов" };
        public static readonly Color[] PhaseColor =
        {
            new Color(0.17f, 0.17f, 0.17f), new Color(0.98f, 0.52f, 0.10f), new Color(0.48f, 0.65f, 1.00f), new Color(0.96f, 0.65f, 0.14f),
            new Color(0.85f, 0.65f, 0.13f), new Color(0.62f, 0.80f, 0.36f), new Color(0.36f, 0.74f, 0.45f), new Color(0.20f, 0.78f, 0.35f)
        };

        /// <summary>Moments (overall progress 0..1 of the landmark) when the phases of floor i end: T[0] = works on the floor start,
        /// T[1] slab and columns done (the frame passes the floor), T[2] facade closed (the facade line passes it, as in AlatauLandmark),
        /// T[3..6] services, partitions, finishes, fit-out — they follow the facade bottom-up and get shorter toward the hand-over.</summary>
        public static void Times(int i, float H, float[] T)
        {
            float yb = IconicShape.FloorY(i), yt = yb + IconicShape.Fh;
            T[0] = 0.08f + 0.62f * yb / H; T[1] = 0.08f + 0.62f * yt / H; T[2] = 0.25f + 0.65f * yt / H;
            float k = (1f - T[2]) / 0.75f;
            T[3] = T[2] + 0.05f * k; T[4] = T[2] + 0.10f * k; T[5] = T[2] + 0.16f * k; T[6] = T[2] + 0.22f * k;
        }
        static readonly float[] tmp = new float[7];
        /// <summary>Phase of floor i at landmark progress p; f = how far the phase has gone (0..1).</summary>
        public static int Phase(int i, float p, float H, out float f)
        {
            if (p >= 0.999f) { f = 1f; return PReady; }
            Times(i, H, tmp);
            if (p < tmp[0]) { f = 0f; return PNone; }
            for (int k = 1; k <= 6; k++) if (p < tmp[k]) { f = Mathf.Clamp01((p - tmp[k - 1]) / Mathf.Max(tmp[k] - tmp[k - 1], 1e-5f)); return k; }
            f = 1f; return PReady;
        }
        /// <summary>Calendar year (fractional) at landmark progress p — the inverse of LandmarkSystem.Progress.</summary>
        public static float YearAt(Landmark l, float p) => (l.StartYear - 1f) + p * (l.EndYear - l.StartYear + 1f);
        static readonly string[] Mon = { "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек" };
        public static string MonthYear(float y) { int yi = Mathf.FloorToInt(y); int m = Mathf.Clamp(Mathf.FloorToInt((y - yi) * 12f), 0, 11); return Mon[m] + " " + yi; }

        // ------------------------------------------------------------------ palette
        static readonly Color32 Concrete = LM.C("#a9a69f"), ConcreteDark = LM.C("#8f8c86"), Screed = LM.C("#c3beb4"), Ply = LM.C("#b98a4c"), Rebar = LM.C("#8a4b2a"),
            Yellow = LM.C("#f2c230"), Orange = LM.C("#f08a24"), SafetyGreen = LM.C("#3f8f4f"), Gypsum = LM.C("#d9d6cf"), Stud = LM.C("#b9bec4"),
            White = LM.C("#eeede8"), Warm = LM.C("#f4ead8"), Duct = LM.C("#c9cdd1"), Sprinkler = LM.C("#d0302a"), PipeBlue = LM.C("#2f6db5"), PipeGreen = LM.C("#3a8a5a"),
            Tray = LM.C("#b5a46a"), Steel = LM.C("#4d535a"), Metal = LM.C("#b9bdc2"), Dark = LM.C("#1c1f23"), Void = LM.C("#121417"),
            Carpet = LM.C("#596472"), Oak = LM.C("#a67c52"), OakDark = LM.C("#6b4a33"), Stone = LM.C("#d8d2c6"), StoneDark = LM.C("#a69f92"), Epoxy = LM.C("#7d8a80"),
            GlassTint = LM.C("#9fbac8"), Fabric = LM.C("#3d4a5c"), FabricWarm = LM.C("#b45a3c"), Leather = LM.C("#2b2b2b"), SofaGrey = LM.C("#8c8f94"), SofaWarm = LM.C("#c9b79c"),
            Desk = LM.C("#e7e3dc"), Leg = LM.C("#3a3d42"), Screen = LM.C("#15181c"), Plant = LM.C("#4f7a3a"), Plant2 = LM.C("#6a8a45"), Soil = LM.C("#5a4630"),
            Skin = LM.C("#d0a07a"), Jeans = LM.C("#2f3b52"), Hat = LM.C("#f7f7f2"), Vest = LM.C("#f39a2b"), Vest2 = LM.C("#c7e03a"), Wood = LM.C("#9b7048"),
            Red = LM.C("#c0392b"), Porcelain = LM.C("#f6f6f4"), Rug = LM.C("#b9a88f"), Bed = LM.C("#f1efe9"), Plaid = LM.C("#4e6a8a");
        const float FP = 20f;            // facade param for furniture: no visible panel joints

        // ------------------------------------------------------------------ the plan of one floor
        public class Info { public string Use, Detail; public float Area; }
        struct Part { public Vector2 A, B; public bool Glass; public float H, T; public Color32 Paint; }

        class Plan
        {
            public int I; public Use U; public float yb, yt, X0, X1, Z0, Z1, cx0, cx1, cz0, cz1, W, D;
            public List<Vector2> inner, slab;
            public readonly List<Part> Parts = new List<Part>();
            public readonly List<Action<LandmarkKit>> Fixtures = new List<Action<LandmarkKit>>(), Furniture = new List<Action<LandmarkKit>>();
            public readonly List<Rect> Reserved = new List<Rect>();
            public Color32 Finish; public int FinishMat = LM.Solid;
            public int Desks, Units, Seats, Rooms; public string Detail = "";
            public System.Random R;
            public float Rnd() => (float)R.NextDouble();

            /// <summary>Point inside the floor plate, at least m metres from its edges.</summary>
            public bool In(float x, float z, float m = 0f)
            {
                int n = inner.Count; Vector2 c = Vector2.zero; foreach (var q in inner) c += q; c /= n;
                for (int i = 0; i < n; i++)
                {
                    var a = inner[i]; var b = inner[(i + 1) % n]; var e = b - a; float L = e.magnitude; if (L < 1e-4f) continue;
                    float sc = (e.x * (c.y - a.y) - e.y * (c.x - a.x)) / L, sp = (e.x * (z - a.y) - e.y * (x - a.x)) / L;
                    if (sc > 0 ? sp < m : sp > -m) return false;
                }
                return true;
            }
            public bool InCore(float x0, float z0, float x1, float z1, float m) => x1 > cx0 - m && x0 < cx1 + m && z1 > cz0 - m && z0 < cz1 + m;
            /// <summary>A rectangle that stands free: inside the plate, off the core and its corridor, off reserved areas.</summary>
            public bool Free(float x0, float z0, float x1, float z1, float m = 0.4f, float corridor = 1.6f)
            {
                if (!In(x0, z0, m) || !In(x1, z0, m) || !In(x0, z1, m) || !In(x1, z1, m)) return false;
                if (InCore(x0, z0, x1, z1, corridor)) return false;
                var r = Rect.MinMaxRect(x0, z0, x1, z1);
                foreach (var q in Reserved) if (q.Overlaps(r)) return false;
                return true;
            }
            public void Reserve(float x0, float z0, float x1, float z1) => Reserved.Add(Rect.MinMaxRect(Mathf.Min(x0, x1), Mathf.Min(z0, z1), Mathf.Max(x0, x1), Mathf.Max(z0, z1)));
            public void Wall(float x0, float z0, float x1, float z1, bool glass = false, Color32? paint = null, float t = 0.12f, float h = -1f)
                => Parts.Add(new Part { A = new Vector2(x0, z0), B = new Vector2(x1, z1), Glass = glass, H = h > 0 ? h : yt - yb - 0.75f, T = glass ? 0.06f : t, Paint = paint ?? White });
            /// <summary>Walks from p along dir until it leaves the plate (margin m); returns the last point inside.</summary>
            public Vector2 ToEdge(Vector2 p, Vector2 dir, float m = 0.2f, float max = 80f)
            {
                var q = p; for (float s = 0f; s < max; s += 0.25f) { var t = p + dir * s; if (!In(t.x, t.y, m)) break; q = t; }
                return q;
            }
        }

        // ------------------------------------------------------------------ public entry: one floor at one moment
        /// <summary>Builds floor i in phase 'phase' (f = progress inside it); 'above' = phase of the floor above (props under a fresh slab).
        /// Returns the floor (seen from above) and, in 'ceiling', what is overhead for the walk-through view.</summary>
        public static Mesh Build(int i, int phase, float f, int above, out Mesh ceiling, out Info info)
        {
            var P = MakePlan(i);
            Layout(P);
            var k = new LandmarkKit();
            Slab(k, P, phase, f);
            Core(k, P, phase, f);
            Columns(k, P, phase, f);
            Perimeter(k, P, phase, f);
            bool plant = P.U == Use.Technical || P.U == Use.Crown;
            if (phase == PServices || phase == PPartitions || (plant && phase > PServices)) Services(k, P, phase == PServices ? f : 1f);
            Partitions(k, P, phase, f);
            if (phase >= PFitOut || (phase == PFinishes && f > 0.5f)) foreach (var a in P.Fixtures) a(k);
            else if (phase == PFinishes) { int n = Mathf.RoundToInt(P.Fixtures.Count * f * 2f); for (int j = 0; j < n && j < P.Fixtures.Count; j++) P.Fixtures[j](k); }
            if (phase >= PReady) foreach (var a in P.Furniture) a(k);
            else if (phase == PFitOut) { int n = Mathf.RoundToInt(P.Furniture.Count * f); for (int j = 0; j < n; j++) P.Furniture[j](k); }
            Site(k, P, phase, f, above);
            ceiling = Ceiling(P, phase, f, above);
            info = new Info { Use = UseName(P.U), Detail = P.Detail, Area = Area(P) };
            return k.ToMesh("Iconic floor " + (i + 1));
        }
        /// <summary>Centre of the floor plate (local frame) and its size — for the camera.</summary>
        public static Vector3 Centre(int i, out float size)
        {
            float yt = IconicShape.FloorY(i) + IconicShape.Fh; float w = IconicShape.RawWidth(yt), d = IconicShape.Depth(yt);
            size = Mathf.Max(w, d);
            return new Vector3(IconicShape.Xr - w * 0.5f, IconicShape.FloorY(i), IconicShape.Cz);
        }
        /// <summary>Is the local point (x, z) on the walkable part of floor i (inside the plate, outside the core)?</summary>
        public static bool Walkable(int i, float x, float z)
        {
            var P = MakePlan(i);
            return P.In(x, z, 0.6f) && !P.InCore(x, z, x, z, 0.3f);
        }

        static Plan MakePlan(int i)
        {
            var P = new Plan { I = i, U = UseOf(i), R = new System.Random(7919 * (i + 3)) };
            P.yb = IconicShape.FloorY(i); P.yt = P.yb + IconicShape.Fh;
            P.inner = IconicShape.Inset(P.yt, 0.45f); P.slab = IconicShape.Inset(P.yb, 0.05f);
            float w = Mathf.Max(IconicShape.RawWidth(P.yt), 5f) - 0.9f, d = IconicShape.Depth(P.yt) - 0.9f;
            P.W = w; P.D = d; P.X1 = IconicShape.Xr - 0.45f; P.X0 = P.X1 - w; P.Z0 = IconicShape.Cz - d * 0.5f; P.Z1 = IconicShape.Cz + d * 0.5f;
            // the core stands against the vertical east face (the white spine): lifts, stairs, risers, toilets
            float cw = Mathf.Clamp(w * 0.3f, 8.6f, 14f), cd = Mathf.Clamp(d * 0.42f, 12f, 17f);
            P.cx1 = P.X1 - 1.1f; P.cx0 = P.cx1 - cw; P.cz0 = IconicShape.Cz - cd * 0.5f; P.cz1 = IconicShape.Cz + cd * 0.5f;
            return P;
        }
        static float Area(Plan P)
        {
            float a = 0f; var p = P.inner; for (int i = 0; i < p.Count; i++) { var u = p[i]; var v = p[(i + 1) % p.Count]; a += u.x * v.y - v.x * u.y; }
            return Mathf.Abs(a) * 0.5f - (P.cx1 - P.cx0) * (P.cz1 - P.cz0);
        }

        // ------------------------------------------------------------------ drawing helpers (local frame of the landmark)
        static void B(LandmarkKit k, float cx, float cz, float sx, float sz, float y0, float y1, Color32 c, int mat = LM.Solid, float prm = FP)
            => k.Box(new Vector3(cx, (y0 + y1) * 0.5f, cz), new Vector3(sx, Mathf.Max(y1 - y0, 0.01f), sz), 0f, c, mat, prm, c, mat);
        static void BR(LandmarkKit k, float cx, float cz, float sx, float sz, float y0, float y1, float yaw, Color32 c, int mat = LM.Solid, float prm = FP)
            => k.Box(new Vector3(cx, (y0 + y1) * 0.5f, cz), new Vector3(sx, Mathf.Max(y1 - y0, 0.01f), sz), yaw, c, mat, prm, c, mat);
        /// <summary>A wall (or rail, beam on the floor) along a segment, t thick.</summary>
        static void Seg(LandmarkKit k, Vector2 a, Vector2 b, float y0, float y1, float t, Color32 c, int mat = LM.Solid, float prm = FP)
        {
            var d = b - a; float L = d.magnitude; if (L < 0.05f) return;
            float yaw = -Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg; var m = (a + b) * 0.5f;
            k.Box(new Vector3(m.x, (y0 + y1) * 0.5f, m.y), new Vector3(L, y1 - y0, t), yaw, c, mat, prm, c, mat);
        }
        static void Pipe(LandmarkKit k, Vector3 a, Vector3 b, float s, Color32 c, int mat = LM.Steel) => k.Beam(a, b, s, s, c, mat, FP);
        /// <summary>Convex polygon clipped to x ≤ xmax (Sutherland–Hodgman, one plane).</summary>
        static List<Vector2> ClipX(List<Vector2> poly, float xmax)
        {
            var o = new List<Vector2>();
            for (int i = 0; i < poly.Count; i++)
            {
                var a = poly[i]; var b = poly[(i + 1) % poly.Count]; bool ia = a.x <= xmax, ib = b.x <= xmax;
                if (ia) o.Add(a);
                if (ia != ib) { float t = (xmax - a.x) / (b.x - a.x); o.Add(new Vector2(xmax, Mathf.Lerp(a.y, b.y, t))); }
            }
            return o;
        }
        static void Chair(LandmarkKit k, float x, float z, float yb, float yawDeg, Color32 c)
        {
            var r = Quaternion.Euler(0f, yawDeg, 0f); var back = r * new Vector3(0f, 0f, -0.24f);
            BR(k, x, z, 0.48f, 0.46f, yb + 0.42f, yb + 0.50f, yawDeg, c);
            BR(k, x + back.x, z + back.z, 0.48f, 0.06f, yb + 0.50f, yb + 0.95f, yawDeg, c);
            BR(k, x, z, 0.06f, 0.06f, yb, yb + 0.42f, yawDeg, Leg, LM.Steel);
        }
        static void RoundTable(LandmarkKit k, float x, float z, float yb, float r, float h, Color32 top)
        {
            k.Cylinder(new Vector3(x, yb + h - 0.04f, z), r, 0.04f, 14, top, LM.Solid, FP, top, LM.Solid);
            k.Cylinder(new Vector3(x, yb, z), 0.05f, h - 0.04f, 6, Leg, LM.Steel, FP, Leg, LM.Steel);
        }
        static void Planter(LandmarkKit k, float x, float z, float yb, float s, float treeH, float seed)
        {
            B(k, x, z, s, s, yb, yb + 0.55f, StoneDark); B(k, x, z, s - 0.12f, s - 0.12f, yb + 0.55f, yb + 0.58f, Soil, LM.Plant);
            if (treeH > 0f) k.Tree(new Vector3(x, yb + 0.58f, z), treeH, (int)(seed * 10) % 2 == 0 ? Plant : Plant2, seed);
            else k.Cylinder(new Vector3(x, yb + 0.58f, z), s * 0.38f, 0.7f, 8, Plant, LM.Plant, FP, Plant2, LM.Plant, 0.3f);
        }
        static void Sofa(LandmarkKit k, float x, float z, float yb, float len, float yawDeg, Color32 c)
        {
            var r = Quaternion.Euler(0f, yawDeg, 0f); var bk = r * new Vector3(0f, 0f, -0.38f);
            BR(k, x, z, len, 0.9f, yb + 0.12f, yb + 0.44f, yawDeg, c);
            BR(k, x + bk.x, z + bk.z, len, 0.16f, yb + 0.44f, yb + 0.82f, yawDeg, c);
            var e = r * new Vector3(len * 0.5f - 0.08f, 0f, 0f);
            BR(k, x + e.x, z + e.z, 0.16f, 0.9f, yb + 0.44f, yb + 0.64f, yawDeg, c); BR(k, x - e.x, z - e.z, 0.16f, 0.9f, yb + 0.44f, yb + 0.64f, yawDeg, c);
        }
        static void Person(LandmarkKit k, float x, float z, float yb, float yaw, Color32 vest, bool helmet = true)
        {
            BR(k, x, z, 0.36f, 0.22f, yb, yb + 0.86f, yaw, Jeans);
            BR(k, x, z, 0.44f, 0.27f, yb + 0.86f, yb + 1.46f, yaw, vest);
            BR(k, x, z, 0.21f, 0.23f, yb + 1.48f, yb + 1.72f, yaw, Skin);
            if (helmet) BR(k, x, z, 0.27f, 0.29f, yb + 1.70f, yb + 1.82f, yaw, Hat);
        }
        static void Pallet(LandmarkKit k, float x, float z, float yb, Color32 load, float h, float yaw = 0f, float sx = 1.2f, float sz = 1.0f)
        {
            BR(k, x, z, sx, sz, yb, yb + 0.14f, yaw, Wood);
            BR(k, x, z, sx - 0.06f, sz - 0.06f, yb + 0.14f, yb + 0.14f + h, yaw, load);
        }

        // ------------------------------------------------------------------ structure
        static void Slab(LandmarkKit k, Plan P, int phase, float f)
        {
            float y = P.yb;
            if (phase == PFrame)
            {
                // formwork deck over the whole plate, reinforcement mesh, and the concrete poured so far (from the core westward)
                k.Prism(P.slab, y - 0.30f, y - 0.06f, Ply, LM.Solid, 1.22f, Ply, LM.Solid);
                float xs = P.X1 - (P.X1 - P.X0 + 2f) * Mathf.Clamp01(f * 1.25f);
                for (float x = P.X0; x <= P.X1; x += 1.2f) { var a = new Vector2(x, P.Z0 - 1f); var b = new Vector2(x, P.Z1 + 1f); ClipSeg(P, ref a, ref b); if (x < xs) Seg(k, a, b, y - 0.06f, y + 0.02f, 0.05f, Rebar, LM.Steel); }
                for (float z = P.Z0; z <= P.Z1; z += 1.2f) { var a = new Vector2(P.X0 - 1f, z); var b = new Vector2(Mathf.Min(xs, P.X1 + 1f), z); ClipSeg(P, ref a, ref b); if (b.x > a.x) Seg(k, a, b, y - 0.06f, y + 0.02f, 0.05f, Rebar, LM.Steel); }
                var poured = ClipXMin(P.slab, xs);
                if (poured.Count >= 3) k.Prism(poured, y - 0.30f, y, Concrete, LM.Solid, 0.3f, LM.C("#9d9a93"), LM.Solid);
                return;
            }
            Color32 top = phase >= PPartitions ? Screed : Concrete;
            k.Prism(P.slab, y - 0.30f, y, ConcreteDark, LM.Solid, 0.3f, top, LM.Solid);
            if (phase >= PFinishes)
            {
                var fin = phase == PFinishes ? ClipX(P.inner, P.X0 + (P.X1 - P.X0) * f) : P.inner;
                if (fin.Count >= 3) k.Prism(fin, y, y + 0.03f, P.Finish, LM.Solid, 0.03f, P.Finish, P.FinishMat);
            }
        }
        /// <summary>Polygon clipped to x ≥ xmin.</summary>
        static List<Vector2> ClipXMin(List<Vector2> poly, float xmin)
        {
            var m = new List<Vector2>(); foreach (var p in poly) m.Add(new Vector2(-p.x, p.y));
            var c = ClipX(m, -xmin); for (int i = 0; i < c.Count; i++) c[i] = new Vector2(-c[i].x, c[i].y);
            return c;
        }
        /// <summary>Trims a segment to the floor plate.</summary>
        static void ClipSeg(Plan P, ref Vector2 a, ref Vector2 b)
        {
            var d = b - a; float L = d.magnitude; if (L < 1e-3f) return; d /= L;
            float s0 = 0f, s1 = L;
            while (s0 < L && !P.In(a.x + d.x * s0, a.y + d.y * s0, 0.1f)) s0 += 0.2f;
            while (s1 > s0 && !P.In(a.x + d.x * s1, a.y + d.y * s1, 0.1f)) s1 -= 0.2f;
            var a2 = a + d * s0; b = a + d * s1; a = a2;
        }

        static void Core(LandmarkKit k, Plan P, int phase, float f)
        {
            float y0 = P.yb, y1 = P.yt - 0.30f, t = 0.35f;
            bool done = phase >= PFinishes;
            Color32 wall = done ? Warm : Concrete;
            float cx0 = P.cx0, cx1 = P.cx1, cz0 = P.cz0, cz1 = P.cz1;
            // lift bank on the west side of the core, doors open to the floor; stairs north and south; risers and toilets east
            int lifts = P.I < 20 ? 4 : P.I < 39 ? 3 : 2; if (P.I >= 56) lifts = 1;
            float lw = 2.5f, bank = lifts * lw, bz0 = (cz0 + cz1) * 0.5f - bank * 0.5f;
            // outer walls: north, south, east full; west with the lift openings
            Seg(k, new Vector2(cx0, cz1), new Vector2(cx1, cz1), y0, y1, t, wall, LM.Solid, IconicShape.Fh);
            Seg(k, new Vector2(cx0, cz0), new Vector2(cx1, cz0), y0, y1, t, wall, LM.Solid, IconicShape.Fh);
            Seg(k, new Vector2(cx1, cz0), new Vector2(cx1, cz1), y0, y1, t, wall, LM.Solid, IconicShape.Fh);
            Seg(k, new Vector2(cx0, cz0), new Vector2(cx0, bz0), y0, y1, t, wall, LM.Solid, IconicShape.Fh);
            Seg(k, new Vector2(cx0, bz0 + bank), new Vector2(cx0, cz1), y0, y1, t, wall, LM.Solid, IconicShape.Fh);
            for (int j = 0; j < lifts; j++)
            {
                float z0 = bz0 + j * lw, zc = z0 + lw * 0.5f;
                // shaft: dark void, partition to the next shaft, lintel and the doors (protected by a barrier until fitted)
                B(k, cx0 + 1.4f, zc, 2.4f, lw - 0.2f, y0 - 0.25f, y0 + 0.01f, Void);
                if (j > 0) Seg(k, new Vector2(cx0, z0), new Vector2(cx0 + 2.7f, z0), y0, y1, 0.2f, ConcreteDark);
                Seg(k, new Vector2(cx0, z0), new Vector2(cx0, z0 + 0.35f), y0, y1, t, wall); Seg(k, new Vector2(cx0, z0 + lw - 0.35f), new Vector2(cx0, z0 + lw), y0, y1, t, wall);
                Seg(k, new Vector2(cx0, z0 + 0.35f), new Vector2(cx0, z0 + lw - 0.35f), y0 + 2.4f, y1, t, wall);
                if (phase >= PFitOut) { B(k, cx0 - 0.02f, zc - 0.45f, 0.06f, 0.88f, y0, y0 + 2.38f, Metal, LM.Metal, 0.8f); B(k, cx0 - 0.02f, zc + 0.45f, 0.06f, 0.88f, y0, y0 + 2.38f, Metal, LM.Metal, 0.8f); }
                else { B(k, cx0 - 0.25f, zc, 0.08f, lw - 0.6f, y0 + 0.5f, y0 + 0.62f, Yellow); B(k, cx0 - 0.25f, zc, 0.08f, lw - 0.6f, y0 + 1.0f, y0 + 1.12f, Yellow); }
            }
            Seg(k, new Vector2(cx0 + 2.7f, bz0), new Vector2(cx0 + 2.7f, bz0 + bank), y0, y1, 0.25f, ConcreteDark);
            // two scissor stairs
            float sx0 = cx0 + 0.4f, sx1 = Mathf.Min(cx0 + 3.4f, cx1 - 0.6f), sl = Mathf.Min(6.0f, (cz1 - cz0 - bank) * 0.5f - 0.3f);
            if (sl > 3.4f)
            {
                Stair(k, P, sx0, sx1, cz1 - 0.2f - sl, cz1 - 0.2f, wall);
                Stair(k, P, sx0, sx1, cz0 + 0.2f, cz0 + 0.2f + sl, wall);
            }
            // east band: risers (pipes and ducts going up) and toilets
            float ex0 = cx0 + 3.6f;
            if (cx1 - ex0 > 2.6f)
            {
                float zm = (cz0 + cz1) * 0.5f;
                Seg(k, new Vector2(ex0, cz0), new Vector2(ex0, cz1), y0, y1, 0.2f, wall);
                Seg(k, new Vector2(ex0, zm), new Vector2(cx1, zm), y0, y1, 0.15f, wall);
                for (int s = -1; s <= 1; s += 2)
                {
                    float zc = zm + s * (cz1 - cz0) * 0.25f;
                    // riser shaft against the east wall
                    B(k, cx1 - 0.9f, zc, 1.2f, 2.0f, y0, y0 + 0.02f, Void);
                    k.Cylinder(new Vector3(cx1 - 1.1f, y0, zc - 0.5f), 0.14f, y1 - y0, 8, PipeBlue, LM.Steel, FP, PipeBlue, LM.Steel);
                    k.Cylinder(new Vector3(cx1 - 0.7f, y0, zc - 0.5f), 0.12f, y1 - y0, 8, PipeGreen, LM.Steel, FP, PipeGreen, LM.Steel);
                    k.Cylinder(new Vector3(cx1 - 1.0f, y0, zc + 0.5f), 0.1f, y1 - y0, 8, Sprinkler, LM.Steel, FP, Sprinkler, LM.Steel);
                    Seg(k, new Vector2(cx1 - 1.6f, zc - 1.1f), new Vector2(cx1 - 1.6f, zc + 1.1f), y0, y1, 0.12f, wall);
                    // toilets: fixtures arrive with the finishes
                    if (phase >= PFinishes && P.U != Use.Crown)
                    {
                        float tx0 = ex0 + 0.3f, tx1 = cx1 - 1.8f; int n = Mathf.Max(1, Mathf.FloorToInt((tx1 - tx0) / 1.0f));
                        for (int q = 0; q < n; q++)
                        {
                            float x = tx0 + (q + 0.5f) * (tx1 - tx0) / n, zw = s > 0 ? cz1 - 0.6f : cz0 + 0.6f;
                            B(k, x, zw, 0.38f, 0.55f, y0, y0 + 0.42f, Porcelain); B(k, x, zw + s * 0.3f, 0.4f, 0.15f, y0 + 0.42f, y0 + 0.8f, Porcelain);
                            if (q < n - 1) B(k, x + (tx1 - tx0) / n * 0.5f, zw, 0.04f, 1.4f, y0 + 0.1f, y0 + 2.0f, Fabric);
                        }
                        B(k, (tx0 + tx1) * 0.5f, zm + s * 0.45f, tx1 - tx0, 0.5f, y0 + 0.82f, y0 + 0.88f, Stone);
                    }
                }
            }
            if (phase == PFrame)
            {
                // self-climbing formwork around the core, a storey ahead of the slab
                float h0 = y1 - 0.5f, h1 = P.yt + 2.4f;
                Seg(k, new Vector2(cx0 - 0.9f, cz1 + 0.9f), new Vector2(cx1 + 0.4f, cz1 + 0.9f), h0, h1, 0.12f, Yellow, LM.Metal, 0.8f);
                Seg(k, new Vector2(cx0 - 0.9f, cz0 - 0.9f), new Vector2(cx1 + 0.4f, cz0 - 0.9f), h0, h1, 0.12f, Yellow, LM.Metal, 0.8f);
                Seg(k, new Vector2(cx0 - 0.9f, cz0 - 0.9f), new Vector2(cx0 - 0.9f, cz1 + 0.9f), h0, h1, 0.12f, Yellow, LM.Metal, 0.8f);
                Seg(k, new Vector2(cx0 - 0.9f, cz1 + 0.9f), new Vector2(cx1 + 0.4f, cz1 + 0.9f), h1 - 0.1f, h1, 0.9f, Steel, LM.Steel);
                Seg(k, new Vector2(cx0 - 0.9f, cz0 - 0.9f), new Vector2(cx1 + 0.4f, cz0 - 0.9f), h1 - 0.1f, h1, 0.9f, Steel, LM.Steel);
                // concrete placing boom on the core
                var bp = new Vector3(cx0 + 2f, h1, cz1 - 2f);
                k.Beam(bp, bp + Vector3.up * 3f, 0.5f, 0.5f, Red, LM.Metal);
                k.Beam(bp + Vector3.up * 3f, new Vector3(P.X0 + (P.X1 - P.X0) * 0.45f, h1 + 4.5f, (P.Z1 + cz1) * 0.5f), 0.32f, 0.32f, Red, LM.Metal);
            }
        }
        static void Stair(LandmarkKit k, Plan P, float x0, float x1, float z0, float z1, Color32 wall)
        {
            float y0 = P.yb, h = P.yt - P.yb, half = (x1 - x0) * 0.5f, land = 1.3f, run = (z1 - z0) - 2f * land; int n = 13;
            Seg(k, new Vector2(x0, z0), new Vector2(x1, z0), y0, P.yt - 0.3f, 0.2f, wall);
            Seg(k, new Vector2(x0, z1), new Vector2(x1, z1), y0, P.yt - 0.3f, 0.2f, wall);
            B(k, (x0 + x1) * 0.5f, z0 + run + land + land * 0.5f, x1 - x0, land, y0 + h * 0.5f - 0.15f, y0 + h * 0.5f, Concrete);
            for (int s = 0; s < n; s++)
            {
                float a = (s + 1f) / n; float st = run / n;
                B(k, x0 + half * 0.5f, z0 + land + s * st + st * 0.5f, half - 0.08f, st, y0 + a * h * 0.5f - 0.17f, y0 + a * h * 0.5f, Concrete);
                B(k, x0 + half * 1.5f, z0 + land + run - s * st - st * 0.5f, half - 0.08f, st, y0 + h * 0.5f + a * h * 0.5f - 0.17f, y0 + h * 0.5f + a * h * 0.5f, Concrete);
            }
            B(k, x0 + half, z0 + land + run * 0.5f, 0.12f, run, y0, y0 + h - 0.3f, ConcreteDark);
        }

        static void Columns(LandmarkKit k, Plan P, int phase, float f)
        {
            float s = Mathf.Lerp(1.1f, 0.6f, P.I / 57f), y0 = P.yb, y1 = P.yt - 0.30f;
            Color32 c = phase >= PFinishes ? White : Concrete;
            foreach (var p in ColumnSpots(P))
            {
                if (phase == PFrame)
                {
                    // cages first, concrete once the pour has passed the column line
                    bool poured = p.x > P.X1 - (P.X1 - P.X0 + 2f) * Mathf.Clamp01(f * 1.25f) + 1.5f;
                    if (poured) B(k, p.x, p.y, s, s, y0, y1, c, LM.Solid, IconicShape.Fh);
                    else for (int q = 0; q < 4; q++) { float dx = (q & 1) == 0 ? -s * 0.4f : s * 0.4f, dz = (q & 2) == 0 ? -s * 0.4f : s * 0.4f; B(k, p.x + dx, p.y + dz, 0.05f, 0.05f, y0, y1 + 1.2f, Rebar, LM.Steel); }
                }
                else B(k, p.x, p.y, s, s, y0, y1, c, LM.Solid, IconicShape.Fh);
            }
        }
        static List<Vector2> ColumnSpots(Plan P)
        {
            var l = new List<Vector2>(); var ring = IconicShape.Inset(P.yt, 1.25f);
            for (int e = 0; e < ring.Count; e++)
            {
                var a = ring[e]; var b = ring[(e + 1) % ring.Count]; float L = (b - a).magnitude; if (L < 3f) continue;
                int n = Mathf.Max(1, Mathf.RoundToInt(L / 8.4f));
                for (int j = 0; j < n; j++) { var p = Vector2.Lerp(a, b, j / (float)n); if (!P.InCore(p.x, p.y, p.x, p.y, 0.8f)) l.Add(p); }
            }
            // an inner line between the west face and the core where the span would be too long
            float span = P.cx0 - P.X0;
            if (span > 22f)
            {
                float x = P.X0 + span * 0.5f;
                for (float z = P.cz0; z <= P.cz1 + 0.01f; z += (P.cz1 - P.cz0) / 2f) if (P.In(x, z, 1f)) l.Add(new Vector2(x, z));
            }
            return l;
        }

        /// <summary>Edge of the slab: guardrail while open, then the inner side of the curtain wall (mullions, sill and transom).</summary>
        static void Perimeter(LandmarkKit k, Plan P, int phase, float f)
        {
            if (phase < PFrame) return;
            float closed = phase == PFacade ? f : phase > PFacade ? 1f : 0f;
            var ring = IconicShape.Inset(P.yt, 0.32f); float total = 0f;
            for (int e = 0; e < ring.Count; e++) total += (ring[(e + 1) % ring.Count] - ring[e]).magnitude;
            float run = 0f, y0 = P.yb, y1 = P.yt - 0.3f;
            for (int e = 0; e < ring.Count; e++)
            {
                var a = ring[e]; var b = ring[(e + 1) % ring.Count]; float L = (b - a).magnitude; if (L < 0.05f) continue;
                int n = Mathf.Max(1, Mathf.RoundToInt(L / 1.5f));
                for (int j = 0; j < n; j++)
                {
                    var p = Vector2.Lerp(a, b, j / (float)n); var q = Vector2.Lerp(a, b, (j + 1f) / n);
                    float at = (run + L * (j + 0.5f) / n) / total;
                    if (at < closed)
                    {
                        B(k, p.x, p.y, 0.09f, 0.09f, y0, y1, Steel, LM.Steel);
                        Seg(k, p, q, y0, y0 + 0.12f, 0.12f, Steel, LM.Steel); Seg(k, p, q, y1 - 0.12f, y1, 0.12f, Steel, LM.Steel);
                        Seg(k, p, q, y0 + 2.9f, y0 + 2.98f, 0.08f, Steel, LM.Steel);
                    }
                    else
                    {
                        B(k, p.x, p.y, 0.06f, 0.06f, y0, y0 + 1.1f, Yellow);
                        Seg(k, p, q, y0 + 1.04f, y0 + 1.1f, 0.05f, Yellow); Seg(k, p, q, y0 + 0.5f, y0 + 0.55f, 0.04f, Yellow); Seg(k, p, q, y0, y0 + 0.15f, 0.03f, Yellow);
                        if (phase == PFacade || phase == PFrame) Seg(k, p, q, y0 + 0.15f, y0 + 1.04f, 0.02f, SafetyGreen);
                    }
                }
                run += L;
            }
        }

        /// <summary>Building services under the slab above: ventilation ducts, sprinkler mains, chilled water, cable trays.
        /// 'f' = share installed. Hidden above the suspended ceiling once the finishes start.</summary>
        static void Services(LandmarkKit k, Plan P, float f)
        {
            var items = new List<Action>();
            float yD = P.yt - 0.95f, yS = P.yt - 0.55f, yW = P.yt - 1.35f, yT = P.yt - 0.62f;
            float r = 1.0f, ax0 = P.cx0 - r, az0 = P.cz0 - r, az1 = P.cz1 + r;
            // supply duct ring in the corridor around the core
            items.Add(() => Pipe3(k, new Vector3(ax0, yD, az0), new Vector3(ax0, yD, az1), 1.0f, 0.45f, Duct));
            items.Add(() => Pipe3(k, new Vector3(ax0, yD, az1), new Vector3(P.cx1, yD, az1), 1.0f, 0.45f, Duct));
            items.Add(() => Pipe3(k, new Vector3(ax0, yD, az0), new Vector3(P.cx1, yD, az0), 1.0f, 0.45f, Duct));
            // branches to the facade
            for (float z = P.Z0 + 3f; z < P.Z1 - 2f; z += 6f)
            {
                float zz = z; var a = new Vector2(ax0, zz); var e = P.ToEdge(a, Vector2.left, 1.4f);
                if (e.x < ax0 - 2f) items.Add(() => Pipe3(k, new Vector3(ax0, yD, zz), new Vector3(e.x, yD, zz), 0.6f, 0.35f, Duct));
            }
            for (float x = P.X0 + 3f; x < P.cx1 - 1f; x += 6f)
            {
                float xx = x;
                var n0 = new Vector2(xx, az1); var n1 = P.ToEdge(n0, Vector2.up, 1.4f); if (n1.y > az1 + 2f && xx > ax0) items.Add(() => Pipe3(k, new Vector3(xx, yD, az1), new Vector3(xx, yD, n1.y), 0.6f, 0.35f, Duct));
                var s0 = new Vector2(xx, az0); var s1 = P.ToEdge(s0, Vector2.down, 1.4f); if (s1.y < az0 - 2f && xx > ax0) items.Add(() => Pipe3(k, new Vector3(xx, yD, az0), new Vector3(xx, yD, s1.y), 0.6f, 0.35f, Duct));
            }
            // sprinkler mains: a grid of red lines
            for (float z = P.Z0 + 1.8f; z < P.Z1 - 1f; z += 3.6f)
            {
                var a = new Vector2(P.X0, z); var b = new Vector2(P.X1, z); ClipSeg(P, ref a, ref b);
                float zz = z; var aa = a; var bb = b;
                if (bb.x - aa.x > 2f) items.Add(() =>
                {
                    if (zz > P.cz0 - 1.2f && zz < P.cz1 + 1.2f) { if (P.cx0 - 1.2f > aa.x) Pipe(k, new Vector3(aa.x, yS, zz), new Vector3(P.cx0 - 1.2f, yS, zz), 0.09f, Sprinkler); }
                    else Pipe(k, new Vector3(aa.x, yS, zz), new Vector3(bb.x, yS, zz), 0.09f, Sprinkler);
                });
            }
            // chilled water and cable trays along the core
            items.Add(() => { Pipe(k, new Vector3(ax0 - 0.6f, yW, az0 - 0.6f), new Vector3(ax0 - 0.6f, yW, az1 + 0.6f), 0.22f, PipeBlue); Pipe(k, new Vector3(ax0 - 1.0f, yW, az0 - 0.6f), new Vector3(ax0 - 1.0f, yW, az1 + 0.6f), 0.22f, PipeGreen); });
            items.Add(() => { k.Box(new Vector3(ax0 + 0.55f, yT, (az0 + az1) * 0.5f), new Vector3(0.45f, 0.08f, az1 - az0 + 1f), 0f, Tray, LM.Metal, 0.3f, Tray, LM.Metal); });
            int m = Mathf.RoundToInt(items.Count * Mathf.Clamp01(f)); for (int j = 0; j < m; j++) items[j]();
        }
        static void Pipe3(LandmarkKit k, Vector3 a, Vector3 b, float w, float h, Color32 c) => k.Beam(a, b, w, h, c, LM.Metal, 0.8f);

        static void Partitions(LandmarkKit k, Plan P, int phase, float f)
        {
            if (phase < PPartitions) return;
            int n = P.Parts.Count, boarded = phase == PPartitions ? Mathf.RoundToInt(n * f) : n, painted = phase == PFinishes ? Mathf.RoundToInt(n * f) : phase > PFinishes ? n : 0;
            for (int j = 0; j < n; j++)
            {
                var w = P.Parts[j]; float y0 = P.yb, y1 = P.yb + w.H;
                if (w.Glass)
                {
                    if (phase < PFinishes) { StudFrame(k, w.A, w.B, y0, y1); continue; }
                    Seg(k, w.A, w.B, y0, y1, w.T, GlassTint, LM.Glass, 3.0f);
                    Seg(k, w.A, w.B, y1 - 0.06f, y1, 0.09f, Steel, LM.Steel); Seg(k, w.A, w.B, y0, y0 + 0.08f, 0.09f, Steel, LM.Steel);
                    continue;
                }
                if (j >= boarded) { StudFrame(k, w.A, w.B, y0, y1); continue; }
                Seg(k, w.A, w.B, y0, y1, w.T, j < painted ? w.Paint : Gypsum, LM.Solid, 1.2f);
            }
        }
        static void StudFrame(LandmarkKit k, Vector2 a, Vector2 b, float y0, float y1)
        {
            Seg(k, a, b, y0, y0 + 0.05f, 0.08f, Stud, LM.Metal); Seg(k, a, b, y1 - 0.05f, y1, 0.08f, Stud, LM.Metal);
            float L = (b - a).magnitude; int n = Mathf.Max(1, Mathf.RoundToInt(L / 0.6f));
            for (int j = 0; j <= n; j++) { var p = Vector2.Lerp(a, b, j / (float)n); B(k, p.x, p.y, 0.06f, 0.06f, y0, y1, Stud, LM.Metal); }
        }

        /// <summary>Workers, materials and temporary works of the phase.</summary>
        static void Site(LandmarkKit k, Plan P, int phase, float f, int above)
        {
            if (phase <= PNone || phase >= PReady) return;
            var R = new System.Random(P.I * 131 + phase * 17);
            float y = P.yb;
            int crew = phase == PFrame ? 14 : phase == PFacade ? 7 : phase == PServices ? 9 : phase == PPartitions ? 9 : phase == PFinishes ? 7 : 5;
            Color32 load = phase == PFrame ? Rebar : phase == PFacade ? GlassTint : phase == PServices ? Duct : phase == PPartitions ? Gypsum : phase == PFinishes ? Stone : LM.C("#c8b28a");
            int pallets = phase == PFitOut ? 6 : 8;
            for (int j = 0, tries = 0; j < crew + pallets && tries < 400; tries++)
            {
                float x = Mathf.Lerp(P.X0, P.X1, (float)R.NextDouble()), z = Mathf.Lerp(P.Z0, P.Z1, (float)R.NextDouble());
                if (!P.In(x, z, 1.5f) || P.InCore(x, z, x, z, 1.2f)) continue;
                if (j < crew) Person(k, x, z, y, (float)R.NextDouble() * 360f, (j & 1) == 0 ? Vest : Vest2);
                else if (phase == PFrame && (j & 1) == 0) for (int q = 0; q < 6; q++) Seg(k, new Vector2(x - 3f, z + q * 0.08f), new Vector2(x + 3f, z + q * 0.08f), y + 0.02f, y + 0.08f + (q % 2) * 0.06f, 0.05f, Rebar, LM.Steel);
                else if (phase == PFacade) { BR(k, x, z, 2.6f, 0.9f, y, y + 0.12f, 0f, Steel, LM.Steel); for (int q = 0; q < 5; q++) BR(k, x, z - 0.3f + q * 0.14f, 2.4f, 0.04f, y + 0.12f, y + 2.8f, 0f, GlassTint, LM.Glass, 3f); }
                else if (phase == PFitOut) { B(k, x, z, 0.9f, 0.7f, y, y + 0.6f, LM.C("#c8a77a")); B(k, x + 0.2f, z + 0.1f, 0.6f, 0.5f, y + 0.6f, y + 1.0f, LM.C("#b9956a")); }
                else Pallet(k, x, z, y, load, phase == PPartitions ? 0.5f : 0.7f, 0f, phase == PPartitions ? 2.4f : 1.2f, 1.0f);
                j++;
            }
            // scissor lifts for the work overhead
            if (phase == PServices || phase == PPartitions)
                for (int q = 0; q < 2; q++)
                {
                    float x = P.X0 + (P.cx0 - P.X0) * (0.3f + 0.4f * q), z = q == 0 ? P.cz1 + 3f : P.cz0 - 3f;
                    if (!P.In(x, z, 2f)) continue;
                    B(k, x, z, 2.3f, 1.2f, y, y + 0.9f, Orange); B(k, x, z, 2.3f, 1.2f, y + 2.3f, y + 2.4f, Steel, LM.Steel);
                    for (int s = 0; s < 3; s++) BR(k, x, z, 2.2f, 0.06f, y + 0.9f + s * 0.48f, y + 1.0f + s * 0.48f, (s & 1) == 0 ? 18f : -18f, Steel, LM.Steel);
                    Person(k, x, z, y + 2.4f, 90f, Vest);
                }
            // props under a slab that was cast a moment ago (the floor above is still in its frame phase)
            if (above == PFrame && phase <= PFacade)
                for (float x = P.X0 + 1f; x < P.X1 - 1f; x += 1.8f)
                    for (float z = P.Z0 + 1f; z < P.Z1 - 1f; z += 1.8f)
                        if (P.In(x, z, 0.8f) && !P.InCore(x, z, x, z, 0.9f)) B(k, x, z, 0.07f, 0.07f, y, P.yt - 0.30f, Steel, LM.Steel);
        }

        /// <summary>What is overhead (walk-through view): the slab above once it exists, a suspended ceiling with light panels after the finishes.</summary>
        static Mesh Ceiling(Plan P, int phase, float f, int above)
        {
            var k = new LandmarkKit();
            float y = P.yt - 0.30f;
            if (above >= PFrame || P.I >= IconicShape.Levels - 1) k.Cap(P.slab, y, false, ConcreteDark, LM.Solid, 1.2f);
            bool tech = P.U == Use.Technical || P.U == Use.Crown;
            if (!tech && (phase >= PFitOut || (phase == PFinishes && f > 0.3f)))
            {
                float yc = P.yt - 0.75f; k.Cap(P.inner, yc, false, White, LM.Solid, 0.6f);
                for (float x = P.X0 + 1.2f; x < P.X1 - 1f; x += 2.4f)
                    for (float z = P.Z0 + 1.2f; z < P.Z1 - 1f; z += 2.4f)
                        if (P.In(x, z, 0.8f) && !P.InCore(x, z, x, z, 0.2f)) B(k, x, z, 1.2f, 0.6f, yc - 0.03f, yc, LM.C("#fff3dc"), phase >= PReady ? LM.Light : LM.Solid, 1f);
            }
            return k.ToMesh("Iconic ceiling " + (P.I + 1));
        }

        // ------------------------------------------------------------------ layouts by use
        static void Layout(Plan P)
        {
            switch (P.U)
            {
                case Use.Lobby: Lobby(P); break;
                case Use.Retail: Retail(P); break;
                case Use.FoodHall: FoodHall(P); break;
                case Use.Conference: Conference(P); break;
                case Use.Office: Office(P); break;
                case Use.Technical: Technical(P); break;
                case Use.Residence: Residences(P); break;
                case Use.Restaurant: Restaurant(P); break;
                case Use.Lounge: Lounge(P); break;
                default: Crown(P); break;
            }
        }

        static void Office(Plan P)
        {
            P.Finish = Carpet; float y = P.yb;
            float bandX1 = P.cx0 - 1.8f, bandX0 = bandX1 - 6.2f;
            bool rooms = bandX0 - P.X0 > 9f;
            if (rooms)
            {
                // meeting rooms along the core: glass to the floor, solid between rooms
                int n = Mathf.Max(1, Mathf.FloorToInt((P.cz1 - P.cz0) / 4.2f)); float rw = (P.cz1 - P.cz0) / n;
                P.Reserve(bandX0 - 0.6f, P.cz0 - 0.6f, bandX1 + 0.3f, P.cz1 + 0.6f);
                P.Wall(bandX0, P.cz0, bandX0, P.cz1, true);
                P.Wall(bandX0, P.cz0, bandX1, P.cz0); P.Wall(bandX0, P.cz1, bandX1, P.cz1);
                for (int j = 0; j < n; j++)
                {
                    float z0 = P.cz0 + j * rw, z1 = z0 + rw, zc = (z0 + z1) * 0.5f, xc = (bandX0 + bandX1) * 0.5f;
                    if (j > 0) P.Wall(bandX0, z0, bandX1, z0);
                    P.Wall(bandX1, z0, bandX1, z1 - 1.1f, true);
                    int seats = Mathf.Max(2, Mathf.FloorToInt((bandX1 - bandX0 - 2.2f) / 0.75f));
                    P.Furniture.Add(k =>
                    {
                        B(k, xc, zc, bandX1 - bandX0 - 2.4f, 1.2f, y + 0.72f, y + 0.76f, Oak); B(k, xc, zc, 0.5f, 0.5f, y, y + 0.72f, Leg, LM.Steel);
                        for (int s = 0; s < seats; s++) { float x = bandX0 + 1.5f + s * 0.75f; Chair(k, x, zc - 0.95f, y, 0f, Fabric); Chair(k, x, zc + 0.95f, y, 180f, Fabric); }
                        B(k, bandX0 + 0.12f, zc, 0.06f, rw * 0.5f, y + 1.0f, y + 1.9f, Screen);
                    });
                    P.Rooms++; P.Seats += seats * 2;
                }
            }
            // a kitchen and a corner to sit together north-east of the core
            float kx1 = P.X1 - 1.4f, kx0 = kx1 - 7f, kz0 = P.cz1 + 2.2f, kz1 = Mathf.Min(kz0 + 6.5f, P.Z1 - 1.4f);
            if (kz1 - kz0 > 4f && P.Free(kx0, kz0, kx1, kz1, 0.3f, 1.4f))
            {
                P.Reserve(kx0, kz0, kx1, kz1);
                P.Fixtures.Add(k => { B(k, kx1 - 0.35f, (kz0 + kz1) * 0.5f, 0.65f, kz1 - kz0 - 0.6f, y, y + 0.92f, Desk); B(k, kx1 - 0.35f, (kz0 + kz1) * 0.5f, 0.66f, kz1 - kz0 - 0.6f, y + 0.92f, y + 0.96f, Stone); B(k, kx1 - 0.2f, (kz0 + kz1) * 0.5f, 0.35f, kz1 - kz0 - 0.6f, y + 1.5f, y + 2.2f, Desk); });
                P.Furniture.Add(k => { for (int q = 0; q < 2; q++) { float x = kx0 + 1.4f + q * 2.6f, z = (kz0 + kz1) * 0.5f; RoundTable(k, x, z, y, 0.55f, 0.74f, Desk); for (int c = 0; c < 4; c++) { float a = c * 90f; var o = Quaternion.Euler(0, a, 0) * new Vector3(0, 0, 0.9f); Chair(k, x + o.x, z + o.z, y, a + 180f, FabricWarm); } } });
            }
            // open plan: benches of desks facing each other, rows across the floor, aisles every six desks
            float x0 = P.X0 + 1.6f, xEnd = P.X1 - 1.6f;
            for (float zc = P.Z0 + 2.6f; zc < P.Z1 - 2f; zc += 4.3f)
            {
                int run = 0;
                for (float x = x0; x + 1.6f < xEnd; x += 1.6f)
                {
                    if (run == 6) { run = 0; continue; }
                    if (!P.Free(x, zc - 1.6f, x + 1.6f, zc + 1.6f, 0.5f, 1.8f)) { run = 0; continue; }
                    float xx = x, zz = zc; P.Desks += 2; run++;
                    P.Furniture.Add(k => DeskPair(k, xx, zz, y));
                }
            }
            // planters in the chamfered corners
            foreach (var c in Corners(P, 2.2f)) { var cc = c; if (P.Free(cc.x - 0.6f, cc.y - 0.6f, cc.x + 0.6f, cc.y + 0.6f, 0.2f, 1f)) P.Furniture.Add(k => Planter(k, cc.x, cc.y, y, 1.1f, 2.6f, cc.x * 0.13f)); }
            P.Detail = $"≈ {P.Desks} рабочих мест · {P.Rooms} переговорных на {P.Seats} мест · кухня";
        }
        static void DeskPair(LandmarkKit k, float x, float zc, float y)
        {
            for (int s = -1; s <= 1; s += 2)
            {
                float z = zc + s * 0.4f;
                B(k, x + 0.8f, z, 1.56f, 0.78f, y + 0.70f, y + 0.74f, Desk);
                B(k, x + 0.06f, z, 0.04f, 0.7f, y, y + 0.70f, Leg, LM.Steel); B(k, x + 1.54f, z, 0.04f, 0.7f, y, y + 0.70f, Leg, LM.Steel);
                B(k, x + 0.8f, zc + s * 0.1f, 0.58f, 0.03f, y + 0.92f, y + 1.26f, Screen); B(k, x + 0.8f, zc + s * 0.18f, 0.08f, 0.12f, y + 0.74f, y + 0.92f, Leg, LM.Steel);
                Chair(k, x + 0.8f, zc + s * 1.15f, y, s > 0 ? 180f : 0f, Leather);
            }
            B(k, x + 0.8f, zc, 1.56f, 0.03f, y + 0.74f, y + 1.12f, Fabric);
        }
        static IEnumerable<Vector2> Corners(Plan P, float inset)
        {
            var c = IconicShape.Inset(P.yt, inset);
            for (int i = 0; i < c.Count; i += 2) { var m = (c[i] + c[(i + c.Count - 1) % c.Count]) * 0.5f; yield return m; }
        }

        static void Residences(Plan P)
        {
            P.Finish = Oak; float y = P.yb;
            float cn = P.cz1 + 1.8f, cs = P.cz0 - 1.8f, cw = P.cx0 - 1.8f;
            // corridor walls around the core (a ring corridor 1.8 m wide)
            P.Wall(cw, cs, cw, cn); P.Wall(cw, cn, P.X1, cn); P.Wall(cw, cs, P.X1, cs);
            // north and south rows of apartments (facade ±z), a west row between the two corridors (facade −x)
            Row(P, new Vector2(cw, cn), new Vector2(P.X1, cn), Vector2.up);
            Row(P, new Vector2(cw, cs), new Vector2(P.X1, cs), Vector2.down);
            var wa = new Vector2(cw, cs); var wb = new Vector2(cw, cn);
            Row(P, wa, wb, Vector2.left);
            // north-west and south-west corners: one more apartment each where the plate is deep enough
            Row(P, new Vector2(P.ToEdge(new Vector2(cw, cn), Vector2.left, 0.4f).x, cn), new Vector2(cw, cn), Vector2.up);
            Row(P, new Vector2(P.ToEdge(new Vector2(cw, cs), Vector2.left, 0.4f).x, cs), new Vector2(cw, cs), Vector2.down);
            // party walls between the corner apartments and the first ones of the north and south rows
            var en = P.ToEdge(new Vector2(cw, cn), Vector2.up, 0.3f); P.Wall(cw, cn, en.x, en.y, false, Warm, 0.2f);
            var es = P.ToEdge(new Vector2(cw, cs), Vector2.down, 0.3f); P.Wall(cw, cs, es.x, es.y, false, Warm, 0.2f);
            P.Detail = $"{P.Units} квартир · вид на Капшагай и Илейский Алатау";
        }
        /// <summary>A row of apartments along the corridor line a → b, the facade in direction 'out'.</summary>
        static void Row(Plan P, Vector2 a, Vector2 b, Vector2 out_)
        {
            float L = (b - a).magnitude; if (L < 6f) return;
            var eu = (b - a) / L;
            float depth = (P.ToEdge((a + b) * 0.5f, out_, 0.4f) - (a + b) * 0.5f).magnitude;
            if (depth < 5.5f) return;
            int n = Mathf.Max(1, Mathf.RoundToInt(L / 10.5f)); float uw = L / n;
            for (int j = 0; j < n; j++)
            {
                var u0 = a + eu * (j * uw); var u1 = a + eu * ((j + 1) * uw);
                if (j > 0) { var e = P.ToEdge(u0, out_, 0.3f); P.Wall(u0.x, u0.y, e.x, e.y, false, Warm, 0.2f); }
                Apartment(P, u0, eu, out_, uw, depth);
                P.Units++;
            }
        }
        static void Apartment(Plan P, Vector2 o, Vector2 eu, Vector2 ev, float L, float D)
        {
            float y = P.yb;
            Vector2 At(float u, float v) => o + eu * u + ev * v;
            void Box2(LandmarkKit k, float u0, float u1, float v0, float v1, float y0, float y1, Color32 c, int mat = LM.Solid)
            {
                var p = At(u0, v0); var q = At(u1, v1);
                B(k, (p.x + q.x) * 0.5f, (p.y + q.y) * 0.5f, Mathf.Abs(q.x - p.x), Mathf.Abs(q.y - p.y), y0, y1, c, mat);
            }
            bool ok(float u, float v) { var p = At(u, v); return P.In(p.x, p.y, 0.5f); }
            // bathroom by the entrance, bedroom on one side of the facade, living room with the kitchen on the other
            float bu = Mathf.Min(2.6f, L * 0.3f), bv = 2.5f, bedU = L * 0.45f, bedV = D * 0.5f;
            { var p = At(0.15f, bv); var q = At(bu, bv); P.Wall(p.x, p.y, q.x, q.y, false, LM.C("#e9e4da")); var r = At(bu, 0.3f); var s = At(bu, bv); P.Wall(r.x, r.y, s.x, s.y, false, LM.C("#e9e4da")); }
            if (D > 7f && L > 7f)
            {
                var p = At(0.15f, bedV); var q = At(bedU - 1.0f, bedV); P.Wall(p.x, p.y, q.x, q.y, false, LM.C("#ece8df"));
                var r = At(bedU, bedV); var s = At(bedU, D - 0.3f); P.Wall(r.x, r.y, s.x, s.y, false, LM.C("#ece8df"));
            }
            P.Fixtures.Add(k =>
            {
                Box2(k, 0.25f, 0.25f + 1.7f, 0.3f, 1.05f, y, y + 0.55f, Porcelain);                     // bath
                Box2(k, bu - 0.75f, bu - 0.25f, 1.4f, 1.95f, y, y + 0.42f, Porcelain);                    // toilet
                Box2(k, 0.3f, 0.9f, bv - 0.55f, bv - 0.1f, y + 0.8f, y + 0.92f, Porcelain);              // basin
                if (L > 6.5f) { Box2(k, L - 0.75f, L - 0.15f, 0.6f, Mathf.Min(4.4f, D - 1f), y, y + 0.9f, Desk); Box2(k, L - 0.76f, L - 0.14f, 0.6f, Mathf.Min(4.4f, D - 1f), y + 0.9f, y + 0.94f, Stone); }
            });
            P.Furniture.Add(k =>
            {
                if (D > 7f && L > 7f)
                {
                    float bc = bedU * 0.5f, vv = bedV + (D - bedV) * 0.55f;
                    if (ok(bc, vv)) { Box2(k, bc - 0.85f, bc + 0.85f, vv - 1.05f, vv + 1.05f, y, y + 0.5f, Bed); Box2(k, bc - 0.85f, bc + 0.85f, vv - 0.2f, vv + 1.05f, y + 0.5f, y + 0.56f, Plaid); Box2(k, bc - 0.9f, bc + 0.9f, vv - 1.15f, vv - 1.05f, y, y + 1.0f, OakDark); }
                    if (ok(bc - 1.3f, vv - 0.9f)) Box2(k, bc - 1.5f, bc - 1.0f, vv - 1.05f, vv - 0.6f, y, y + 0.5f, OakDark);
                    if (ok(0.4f, bedV + 0.8f)) Box2(k, 0.2f, 0.8f, bedV + 0.4f, bedV + 2.4f, y, y + 2.2f, Desk);
                }
                float lu = D > 7f && L > 7f ? (bedU + L) * 0.5f : L * 0.5f, lv = D * 0.72f;
                if (ok(lu, lv))
                {
                    Box2(k, lu - 1.5f, lu + 1.5f, lv - 1.2f, lv + 1.2f, y + 0.03f, y + 0.045f, Rug);
                    var c = At(lu, lv - 0.95f); float yaw = Mathf.Atan2(ev.x, ev.y) * Mathf.Rad2Deg;
                    Sofa(k, c.x, c.y, y, 2.2f, yaw, SofaWarm);
                    Box2(k, lu - 0.5f, lu + 0.5f, lv - 0.1f, lv + 0.4f, y, y + 0.38f, OakDark);
                    var t = At(lu, D - 0.6f); B(k, t.x, t.y, Mathf.Abs(eu.x) > 0.5f ? 1.8f : 0.4f, Mathf.Abs(eu.x) > 0.5f ? 0.4f : 1.8f, y, y + 0.5f, OakDark);
                }
                float du = L - 1.9f, dv = Mathf.Min(D * 0.45f, 5.6f);
                if (ok(du, dv) && L > 6.5f)
                {
                    var dc = At(du, dv); RoundTable(k, dc.x, dc.y, y, 0.6f, 0.75f, Desk);
                    for (int s = 0; s < 4; s++) { float a = s * 90f + 45f; var oo = Quaternion.Euler(0, a, 0) * new Vector3(0, 0, 0.85f); Chair(k, dc.x + oo.x, dc.y + oo.z, y, a + 180f, OakDark); }
                }
                var pl = At(L - 0.6f, D - 0.6f); if (P.In(pl.x, pl.y, 0.3f)) Planter(k, pl.x, pl.y, y, 0.6f, 1.6f, pl.x * 0.31f);
            });
        }

        static void Lobby(Plan P)
        {
            P.Finish = Stone; P.FinishMat = LM.Paving; float y = P.yb, zc = IconicShape.Cz;
            // security line (turnstiles) in front of the lifts, the reception, seating, planted trees, the revolving door
            float tx = P.cx0 - 3.4f;
            P.Reserve(tx - 7.5f, P.cz0 - 1f, P.cx0, P.cz1 + 1f);
            P.Fixtures.Add(k =>
            {
                for (float z = P.cz0 + 0.6f; z < P.cz1 - 0.5f; z += 1.1f) { B(k, tx, z, 1.2f, 0.22f, y, y + 1.0f, Metal, LM.Metal, 0.8f); B(k, tx, z + 0.45f, 0.04f, 0.6f, y + 0.5f, y + 1.0f, GlassTint, LM.Glass, 3f); }
                B(k, tx - 5.5f, zc, 1.1f, 7f, y, y + 1.1f, OakDark); B(k, tx - 5.5f, zc, 1.3f, 7.2f, y + 1.1f, y + 1.16f, Stone);
                B(k, tx - 5.5f + 1.2f, zc, 0.12f, 9f, y, y + 3.6f, StoneDark);
                var door = new Vector3(P.X0 + 2.2f, y, zc);
                if (P.In(door.x, door.z, 0.5f)) { k.Cylinder(door, 1.8f, 2.8f, 16, GlassTint, LM.Glass, 3f, Metal, LM.Metal); k.Cylinder(door + Vector3.up * 2.8f, 1.9f, 0.3f, 16, Metal, LM.Metal, 1f, Metal, LM.Metal); }
            });
            P.Furniture.Add(k =>
            {
                for (int g = 0; g < 3; g++)
                {
                    float x = P.X0 + 7f + g * 7.5f, z = zc + ((g & 1) == 0 ? 8f : -8f); if (!P.Free(x - 2f, z - 2f, x + 2f, z + 2f, 0.3f, 1f)) continue;
                    Sofa(k, x, z - 1.3f, y, 2.4f, 0f, Leather); Sofa(k, x, z + 1.3f, y, 2.4f, 180f, Leather); B(k, x, z, 1.2f, 0.7f, y, y + 0.4f, StoneDark);
                }
                foreach (var c in Corners(P, 3f)) if (P.Free(c.x - 1.2f, c.y - 1.2f, c.x + 1.2f, c.y + 1.2f, 0.1f, 1f)) Planter(k, c.x, c.y, y, 2.4f, 6f, c.x * 0.2f);
                k.Cylinder(new Vector3(P.X0 + (tx - 7.5f - P.X0) * 0.55f, y, zc), 0.35f, 4.2f, 10, Metal, LM.Metal, 1f, Red, LM.Light, 0.6f);
                var cof = new Vector2(P.X0 + 6f, P.Z1 - 4f); if (P.Free(cof.x - 2f, cof.y - 1f, cof.x + 2f, cof.y + 1f, 0.3f, 1f)) { B(k, cof.x, cof.y, 3.6f, 0.8f, y, y + 1.05f, OakDark); B(k, cof.x, cof.y + 0.8f, 3.6f, 0.4f, y, y + 2.2f, Desk); }
            });
            P.Wall(tx - 7.5f, P.cz0 - 1f, tx - 7.5f, P.cz0 - 4f, true); P.Wall(tx - 7.5f, P.cz1 + 1f, tx - 7.5f, P.cz1 + 4f, true);
            P.Detail = "ресепшн · турникеты к лифтам · кофейня · вход с площади";
        }

        static void Retail(Plan P)
        {
            P.Finish = Stone; P.FinishMat = LM.Paving; float y = P.yb;
            float cn = P.cz1 + 2.6f, cs = P.cz0 - 2.6f, gx = P.cx0 - 2.6f;
            ShopRow(P, new Vector2(P.X0, cn), new Vector2(P.X1, cn), Vector2.up);
            ShopRow(P, new Vector2(P.X0, cs), new Vector2(P.X1, cs), Vector2.down);
            // the gallery: escalators to the next level, benches, planters
            float ex = (P.X0 + gx) * 0.5f, ez = IconicShape.Cz;
            if (gx - P.X0 > 14f)
            {
                P.Reserve(ex - 6f, ez - 2.5f, ex + 6f, ez + 2.5f);
                P.Fixtures.Add(k =>
                {
                    for (int s = -1; s <= 1; s += 2)
                    {
                        float z = ez + s * 1.1f, xa = s < 0 ? ex - 5.5f : ex + 5.5f, xb = s < 0 ? ex + 5.5f : ex - 5.5f;
                        k.Slab(new Vector3(xa, y + 0.05f, z - 0.55f), new Vector3(xb, P.yt, z - 0.55f), new Vector3(xb, P.yt, z + 0.55f), new Vector3(xa, y + 0.05f, z + 0.55f), 0.3f, Steel, LM.Metal);
                        for (int q = -1; q <= 1; q += 2) k.Slab(new Vector3(xa, y + 0.95f, z + q * 0.62f), new Vector3(xb, P.yt + 0.95f, z + q * 0.62f), new Vector3(xb, P.yt, z + q * 0.62f), new Vector3(xa, y, z + q * 0.62f), 0.04f, GlassTint, LM.Glass);
                    }
                });
            }
            P.Furniture.Add(k =>
            {
                for (float x = P.X0 + 4f; x < gx - 3f; x += 7f) foreach (float z in new[] { ez - 5f, ez + 5f }) if (P.Free(x - 1.2f, z - 0.4f, x + 1.2f, z + 0.4f, 0.3f, 1f)) { B(k, x, z, 2.4f, 0.5f, y, y + 0.45f, OakDark); Planter(k, x + 2f, z, y, 1f, 2.4f, x * 0.1f + z); }
            });
            P.Detail = $"{P.Units} магазинов и бутиков · эскалаторы на следующий уровень";
        }
        static void ShopRow(Plan P, Vector2 a, Vector2 b, Vector2 out_)
        {
            ClipSeg(P, ref a, ref b);
            float L = (b - a).magnitude; if (L < 8f) return; var eu = (b - a) / L; float y = P.yb;
            float depth = (P.ToEdge((a + b) * 0.5f, out_, 0.4f) - (a + b) * 0.5f).magnitude; if (depth < 5f) return;
            int n = Mathf.Max(1, Mathf.RoundToInt(L / 9f)); float uw = L / n;
            for (int j = 0; j < n; j++)
            {
                var u0 = a + eu * (j * uw); var u1 = a + eu * ((j + 1) * uw);
                if (j > 0) { var e = P.ToEdge(u0, out_, 0.3f); P.Wall(u0.x, u0.y, e.x, e.y, false, White, 0.2f); }
                var g0 = u0 + eu * 0.6f; var g1 = u1 - eu * 2.2f; P.Wall(g0.x, g0.y, g1.x, g1.y, true);
                var m = (u0 + u1) * 0.5f; int jj = j;
                P.Fixtures.Add(k =>
                {
                    for (int r = 0; r < 3; r++)
                    {
                        var c = m + out_ * (1.8f + r * 1.6f); if (!P.In(c.x, c.y, 0.8f)) continue;
                        B(k, c.x, c.y, Mathf.Abs(eu.x) > 0.5f ? uw - 3f : 0.5f, Mathf.Abs(eu.x) > 0.5f ? 0.5f : uw - 3f, y, y + 1.8f, (jj & 1) == 0 ? Desk : OakDark);
                    }
                    var t = m + out_ * 1.0f + eu * (uw * 0.3f); B(k, t.x, t.y, 1.4f, 1.4f, y, y + 1.0f, Stone);
                });
                P.Units++;
            }
        }

        static void FoodHall(Plan P)
        {
            P.Finish = StoneDark; P.FinishMat = LM.Paving; float y = P.yb;
            float cn = P.cz1 + 2.4f, cs = P.cz0 - 2.4f;
            ShopRow(P, new Vector2(P.X0, cn), new Vector2(P.X1, cn), Vector2.up);
            ShopRow(P, new Vector2(P.X0, cs), new Vector2(P.X1, cs), Vector2.down);
            int tables = 0;
            for (float x = P.X0 + 3f; x < P.cx0 - 4f; x += 3.4f)
                for (float z = P.cz0 + 1.2f; z < P.cz1 - 0.6f; z += 3.2f)
                {
                    if (!P.Free(x - 1.3f, z - 1.3f, x + 1.3f, z + 1.3f, 0.3f, 2f)) continue;
                    float xx = x, zz = z; tables++;
                    P.Furniture.Add(k => { RoundTable(k, xx, zz, y, 0.55f, 0.75f, Oak); for (int c = 0; c < 4; c++) { float a = c * 90f + 45f; var o = Quaternion.Euler(0, a, 0) * new Vector3(0, 0, 0.85f); Chair(k, xx + o.x, zz + o.z, y, a + 180f, FabricWarm); } });
                }
            P.Detail = $"{P.Units} точек питания · {tables * 4} посадочных мест";
        }

        static void Conference(Plan P)
        {
            P.Finish = Carpet; float y = P.yb;
            float hx0 = P.X0 + 1.2f, hx1 = P.cx0 - 4f, hz0 = P.cz0 - 3f, hz1 = P.cz1 + 3f;
            if (hx1 - hx0 > 12f)
            {
                P.Reserve(hx0, hz0, hx1, hz1);
                P.Wall(hx1, hz0, hx1, IconicShape.Cz - 1.2f); P.Wall(hx1, IconicShape.Cz + 1.2f, hx1, hz1);
                P.Wall(hx0, hz0, hx1, hz0); P.Wall(hx0, hz1, hx1, hz1);
                P.Fixtures.Add(k => { B(k, hx0 + 1.6f, (hz0 + hz1) * 0.5f, 3f, hz1 - hz0 - 1f, y, y + 0.6f, OakDark); B(k, hx0 + 0.3f, (hz0 + hz1) * 0.5f, 0.1f, (hz1 - hz0) * 0.6f, y + 1.4f, y + 3.4f, LM.C("#cfe3ff"), LM.Light, 1f); });
                int seats = 0;
                for (float x = hx0 + 5f; x < hx1 - 1f; x += 1.0f)
                    for (float z = hz0 + 1f; z < hz1 - 0.8f; z += 0.6f) { if (Mathf.Abs(z - IconicShape.Cz) < 0.7f) continue; float xx = x, zz = z; seats++; P.Furniture.Add(k => Chair(k, xx, zz, y, -90f, FabricWarm)); }
                P.Seats = seats;
            }
            P.Furniture.Add(k => { for (float x = P.X0 + 4f; x < P.X1 - 4f; x += 4.5f) foreach (float z in new[] { P.Z0 + 3f, P.Z1 - 3f }) if (P.Free(x - 0.5f, z - 0.5f, x + 0.5f, z + 0.5f, 0.3f, 1f)) RoundTable(k, x, z, y, 0.4f, 1.08f, Desk); });
            P.Detail = $"зал на {P.Seats} мест · фойе для кофе-брейков";
        }

        static void Technical(Plan P)
        {
            P.Finish = Epoxy; float y = P.yb;
            // plant rooms (blockwork), the refuge area painted on the floor, chillers, air handlers, pumps, tanks, switchboards
            float wx = P.cx0 - 1.8f;
            P.Wall(wx, P.cz0 - 1.8f, wx, P.cz1 + 1.8f, false, LM.C("#cfccc4"), 0.25f);
            P.Wall(P.X0, P.cz1 + 1.8f, wx, P.cz1 + 1.8f, false, LM.C("#cfccc4"), 0.25f);
            P.Fixtures.Add(k =>
            {
                float ch = 0;
                for (float x = P.X0 + 4.5f; x < wx - 4f; x += 8f)
                {
                    float z = P.cz0 + 1.5f; if (!P.Free(x - 3f, z - 1.4f, x + 3f, z + 1.4f, 0.4f, 0.2f)) continue;
                    B(k, x, z, 6f, 2.4f, y + 0.2f, y + 2.4f, LM.C("#5f7d96"), LM.Metal, 0.8f); B(k, x, z, 6.4f, 2.8f, y, y + 0.2f, Concrete);
                    for (int q = 0; q < 3; q++) k.Cylinder(new Vector3(x - 2f + q * 2f, y + 2.4f, z), 0.7f, 0.3f, 12, Dark, LM.Metal, 1f, Steel, LM.Steel);
                    Pipe(k, new Vector3(x + 3f, y + 1.2f, z - 0.6f), new Vector3(wx - 0.5f, y + 1.2f, z - 0.6f), 0.3f, PipeBlue);
                    Pipe(k, new Vector3(x + 3f, y + 1.6f, z + 0.6f), new Vector3(wx - 0.5f, y + 1.6f, z + 0.6f), 0.3f, PipeGreen);
                    ch++;
                }
                for (float x = P.X0 + 5f; x < P.X1 - 4f; x += 9.5f)
                    foreach (float z in new[] { P.Z0 + 3.2f })
                        if (P.Free(x - 4f, z - 1.3f, x + 4f, z + 1.3f, 0.4f, 0.6f)) { B(k, x, z, 8f, 2.4f, y + 0.15f, y + 2.6f, LM.C("#b9c0c7"), LM.Metal, 0.8f); B(k, x + 4.2f, z, 0.6f, 1.2f, y + 2f, y + 3.6f, Duct, LM.Metal, 0.8f); }
                for (int q = 0; q < 6; q++) { float x = wx - 1.2f, z = P.cz0 + 1f + q * 1.6f; if (z > P.cz1) break; k.Cylinder(new Vector3(x, y + 0.3f, z), 0.35f, 0.8f, 10, PipeBlue, LM.Metal, 1f, Steel, LM.Steel); }
                for (int q = 0; q < 2; q++) { float x = P.X0 + 4f + q * 3.2f, z = P.Z1 - 3.4f; if (P.In(x, z, 1.8f)) k.Cylinder(new Vector3(x, y, z), 1.4f, 3.2f, 16, LM.C("#d7dbe0"), LM.Metal, 1f, Metal, LM.Metal, 0.4f); }
                for (int q = 0; q < 8; q++) { float x = P.cx0 + 1f + q * 0.9f, z = P.cz1 + 1.0f; if (x < P.X1 - 1f) B(k, x, z, 0.8f, 0.6f, y, y + 2.1f, LM.C("#9aa3ab"), LM.Metal, 0.8f); }
                var rf = new Vector2(P.X1 - 6f, P.Z0 + 4f);
                if (P.In(rf.x, rf.y, 3f)) { B(k, rf.x, rf.y, 8f, 5f, y + 0.03f, y + 0.045f, SafetyGreen); B(k, rf.x, rf.y - 2.6f, 1.2f, 0.05f, y + 1.8f, y + 2.3f, LM.C("#2fd36a"), LM.Light, 1f); }
            });
            P.Detail = "чиллеры, вентиляция, насосные · зона безопасности при эвакуации · демпферы колебаний";
        }

        static void Restaurant(Plan P)
        {
            P.Finish = OakDark; float y = P.yb;
            float kz1 = P.cz0 - 1.8f;
            P.Wall(P.X0, kz1, P.cx0 - 1.8f, kz1, true); P.Reserve(P.X0, P.Z0, P.cx0, kz1);
            P.Fixtures.Add(k =>
            {
                for (float x = P.X0 + 2f; x < P.cx0 - 2.5f; x += 3.2f) { float z = kz1 - 1.2f; if (P.In(x, z, 0.8f)) B(k, x, z, 2.6f, 0.8f, y, y + 0.92f, Metal, LM.Metal, 0.8f); }
                float bx = P.cx0 - 3.2f; B(k, bx, IconicShape.Cz, 0.9f, P.cz1 - P.cz0 - 1f, y, y + 1.1f, OakDark); B(k, bx, IconicShape.Cz, 1.1f, P.cz1 - P.cz0 - 0.8f, y + 1.1f, y + 1.16f, Stone);
            });
            int tables = 0;
            for (float x = P.X0 + 2.6f; x < P.cx0 - 5f; x += 3.0f)
                for (float z = kz1 + 2f; z < P.Z1 - 1.5f; z += 3.0f)
                {
                    if (!P.Free(x - 1.2f, z - 1.2f, x + 1.2f, z + 1.2f, 0.4f, 1.5f)) continue; float xx = x, zz = z; tables++;
                    P.Furniture.Add(k => { RoundTable(k, xx, zz, y, 0.5f, 0.75f, Porcelain); for (int c = 0; c < 3; c++) { float a = c * 120f; var o = Quaternion.Euler(0, a, 0) * new Vector3(0, 0, 0.82f); Chair(k, xx + o.x, zz + o.z, y, a + 180f, Leather); } });
                }
            P.Detail = $"{tables * 3} мест · открытая кухня · бар у лифтов";
        }
        static void Lounge(Plan P)
        {
            P.Finish = Carpet; float y = P.yb;
            var ring = IconicShape.Inset(P.yt, 2.2f); int n = 0;
            for (int e = 0; e < ring.Count; e++)
            {
                var a = ring[e]; var b = ring[(e + 1) % ring.Count]; float L = (b - a).magnitude; if (L < 4f) continue;
                for (float s = 1.6f; s < L - 1.6f; s += 3.6f)
                {
                    var p = Vector2.Lerp(a, b, s / L); if (P.InCore(p.x, p.y, p.x, p.y, 1.6f)) continue;
                    var d = (b - a) / L; var pp = p; n++;
                    var inward = new Vector2(-d.y, d.x); Vector2 cen = Vector2.zero; foreach (var q in ring) cen += q; cen /= ring.Count; if (Vector2.Dot(inward, cen - p) < 0) inward = -inward;
                    float face = Mathf.Atan2(-inward.x, -inward.y) * Mathf.Rad2Deg;
                    P.Furniture.Add(k => { Sofa(k, pp.x + inward.x * 1.1f, pp.y + inward.y * 1.1f, y, 2.2f, face, SofaGrey); B(k, pp.x + inward.x * 0.1f, pp.y + inward.y * 0.1f, 0.8f, 0.8f, y, y + 0.36f, OakDark); });
                }
            }
            P.Fixtures.Add(k => { var t = new Vector3(P.X0 + 2.4f, y, IconicShape.Cz); if (P.In(t.x, t.z, 0.8f)) { k.Cylinder(t, 0.08f, 1.2f, 6, Steel, LM.Steel, 1f, Steel, LM.Steel); k.Beam(t + Vector3.up * 1.25f, t + new Vector3(-0.5f, 1.45f, 0f), 0.16f, 0.16f, Metal, LM.Metal); } });
            P.Detail = $"смотровая площадка на высоте {Mathf.RoundToInt(P.yb)} м · {n * 3} мест";
        }
        static void Crown(Plan P)
        {
            P.Finish = Epoxy; float y = P.yb;
            P.Fixtures.Add(k =>
            {
                var r = IconicShape.Inset(P.yt, 1.4f);
                for (int e = 0; e < r.Count; e++) Seg(k, r[e], r[(e + 1) % r.Count], y, y + 0.18f, 0.18f, Steel, LM.Steel);
                var m = new Vector3(P.X0 + (P.cx0 - P.X0) * 0.5f, y, IconicShape.Cz - 3f);
                if (P.In(m.x, m.z, 1.5f)) { B(k, m.x, m.z, 2.4f, 3.2f, y + 0.2f, y + 2.2f, LM.C("#e7e9eb"), LM.Metal, 0.8f); k.Beam(m + Vector3.up * 2.2f, m + new Vector3(-(m.x - P.X0) + 0.5f, 3.4f, 0f), 0.35f, 0.35f, Orange, LM.Metal); }
                for (int q = 0; q < 3; q++) { var c = new Vector3(P.X0 + 2.5f + q * 2.6f, y, IconicShape.Cz + 5f); if (P.In(c.x, c.z, 1.2f)) k.Cylinder(c, 0.9f, 1.4f, 12, Metal, LM.Metal, 1f, Dark, LM.Metal); }
            });
            P.Detail = "машина для мойки фасада · вытяжные вентиляторы · авиационные огни";
        }
    }
}
