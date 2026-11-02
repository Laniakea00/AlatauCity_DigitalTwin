using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The six low-rise office buildings of Iconic Complex (registry iconic_offices_6, S35: «шесть малоэтажных офисных корпусов с
    /// внутренними дворами»; tools/map/spec/gate.json v1.2, objects[iconic_offices_6].parts). The plot of the complex is its plaza, so
    /// they stand in the Gate District quarter round it, on the courtyards of the blocks the quarter's model gave up, at least 12 m from
    /// the blocks it keeps. Each is a ring 15 m deep round its courtyard, 4 storeys × 4.43 m = 17.7 m, in the look of the quarter's own
    /// model (AlatauQTwin.cginc, ALATAU_QT_GATE: light stone with deep windows, glazed ground floor, a parapet with a coping, a membrane
    /// roof with plant on it) and a garden in the courtyard.
    /// They are added to the quarter's data when it is read (QTwinData.Gate), so they stand with the quarter, from 2029 (the year of the
    /// object in gate.json and the hand-over of the complex), and what reads the quarter (IconicDistrict, the film's walkers and asphalt)
    /// sees them. The quarter's trees whose crowns would grow into their walls are left out there and then; a courtyard left without a
    /// tree gets young ones of its own. Merge gives them no buildings.json rows, so the panels count their floor area once: inside the
    /// 276 800 m² of the complex (its passport and LandmarkCapacity), never in the city's stock.</summary>
    public static class IconicOffices
    {
        public struct Block { public string Id, Side; public Rect Foot, Court; public int Gfa; }
        static Block B(string id, string side, float x0, float x1, float z0, float z1, float cx0, float cx1, float cz0, float cz1, int gfa) =>
            new Block { Id = id, Side = side, Foot = Rect.MinMaxRect(x0, z0, x1, z1), Court = Rect.MinMaxRect(cx0, cz0, cx1, cz1), Gfa = gfa };
        /// <summary>World rectangles (x, z) of the footprints and their courtyards, as in gate.json.</summary>
        public static readonly Block[] Blocks =
        {
            B("iconic_office_1", "NE", -3342f, -3282f, -19318f, -19258f, -3327f, -3297f, -19303f, -19273f, 10800),
            B("iconic_office_2", "E",  -3262f, -3206f, -19415f, -19359f, -3247f, -3221f, -19400f, -19374f, 9840),
            B("iconic_office_3", "SE", -3338f, -3290f, -19750f, -19702f, -3323f, -3305f, -19735f, -19717f, 7920),
            B("iconic_office_4", "SW", -3715f, -3659f, -19746f, -19690f, -3700f, -3674f, -19731f, -19705f, 9840),
            B("iconic_office_5", "W",  -3825f, -3765f, -19529f, -19469f, -3810f, -3780f, -19514f, -19484f, 10800),
            B("iconic_office_6", "NW", -3715f, -3663f, -19314f, -19262f, -3700f, -3678f, -19299f, -19277f, 8880),
        };
        public const int Floors = 4, Year = 2029;
        public const float Height = 17.7f, Storey = Height / Floors, Parapet = 0.9f, Coping = 0.35f;
        /// <summary>Floor area of the six (the model's estimate: ring × 4 storeys), m².</summary>
        public static int TotalGfa { get { int s = 0; foreach (var b in Blocks) s += b.Gfa; return s; } }

        // the quarter's surfaces (AlatauQTwin.cginc): warm stone with 3 m bays, membrane (an upward face of any other tag), garden,
        // precast coping, rooftop plant
        const byte Wall = 21, Roof = 25, Garden = 26, Stone = 32, Plant = 33;
        const float Bay = 3.0f;
        // IconicDistrict draws a tree of size s with a crown 6.6 m × 1.35 s wide: its radius
        const float CrownPerSize = 4.46f, CrownMargin = 0.3f;
        // The surfaces draw a 3.3 m storey over a 4.6 m shop floor from the facade height they are given; these storeys are 4.43 m.
        // Each storey of the walls is its own quad and gets the facade heights of one storey of the shader, so the four read as four
        // (not as five of 3.3 m): the ground floor 0 … 4.6 (shopfronts: the lobbies), the others 6.6 … 9.9, 9.9 … 13.2, 13.2 … 16.5.
        static readonly float[] FloorF0 = { 0f, 6.6f, 9.9f, 13.2f }, FloorF1 = { 4.59f, 9.9f, 13.2f, 16.5f };

        static float ca, sa, ox, oz;
        static List<Vector3> P, N; static List<float> U, F; static List<byte> T; static List<int> I;

        /// <summary>Adds the six to the quarter as read from gate_district.bytes (its local frame: the Iconic landmark's) and leaves out
        /// the quarter's trees that clash with them.</summary>
        public static void AddTo(QTwinData.District d)
        {
            if (d == null || d.Mesh == null || d.Trees == null) return;
            float a = LandmarkCatalog.IconicYaw * Mathf.Deg2Rad; ca = Mathf.Cos(a); sa = Mathf.Sin(a); ox = LandmarkCatalog.IconicX; oz = LandmarkCatalog.IconicZ;
            var m = d.Mesh;

            // the trees: none whose crown reaches a wall (trunks inside the rings, crowns from the courtyards and the street rows)
            var trees = new List<Vector4>(d.Trees.Length); var kinds = new List<byte>(d.Trees.Length); int dropped = 0;
            for (int i = 0; i < d.Trees.Length; i++)
            {
                var t = d.Trees[i]; var w = World(t.x, t.z); float r = CrownPerSize * t.w + CrownMargin; bool clash = false;
                foreach (var b in Blocks) if (RingDist(b, w) < r) { clash = true; break; }
                if (clash) { dropped++; continue; }
                trees.Add(t); kinds.Add(d.Kind[i]);
            }

            P = new List<Vector3>(m.P); N = new List<Vector3>(m.N); U = new List<float>(m.U); T = new List<byte>(m.Tag); I = new List<int>(m.I);
            F = new List<float>(m.P.Length + 2400);
            if (m.Fy != null) F.AddRange(m.Fy); else foreach (var p in m.P) F.Add(p.y);
            int t0 = I.Count, planted = 0;
            foreach (var b in Blocks)
            {
                float court = CourtLevel(m, b);
                Build(b, court);
                // a courtyard the quarter left without a tree: young ones, crowns clear of its walls
                int inCourt = 0; foreach (var t in trees) if (b.Court.Contains(World(t.x, t.z))) inCourt++;
                if (inCourt > 0) continue;
                float c = Mathf.Min(b.Court.width, b.Court.height); var cc = b.Court.center;
                if (c >= 22f)
                {
                    float o = 0.22f * c, s = Mathf.Min(0.85f, (c * 0.5f - o - 0.8f) / CrownPerSize);
                    for (int k = 0; k < 4; k++) { trees.Add(Tree(cc + new Vector2((k & 1) == 0 ? -o : o, (k & 2) == 0 ? -o : o), court, s)); kinds.Add(0); planted++; }
                }
                else { trees.Add(Tree(cc, court, Mathf.Min(0.9f, (c * 0.5f - 1.2f) / CrownPerSize))); kinds.Add(0); planted++; }
            }
            int tris = (I.Count - t0) / 3;
            d.Mesh = new QTwinData.QMesh { P = P.ToArray(), N = N.ToArray(), U = U.ToArray(), Fy = F.ToArray(), Tag = T.ToArray(), Part = m.Part, I = I.ToArray() };
            d.Trees = trees.ToArray(); d.Kind = kinds.ToArray();
            P = N = null; U = F = null; T = null; I = null;
            Debug.Log(string.Format("[Alatau] Iconic offices: {0} buildings, {1} m², {2} storeys × {3:0.00} m, {4} triangles in the Gate District; {5} of its trees left out (crowns into their walls), {6} planted in their courtyards",
                Blocks.Length, TotalGfa, Floors, Storey, tris, dropped, planted));
        }

        // ------------------------------------------------------------------ frames
        static Vector2 World(float lx, float lz) => new Vector2(ox + lx * ca + lz * sa, oz - lx * sa + lz * ca);
        static Vector2 Local(Vector2 w) => Rot(new Vector2(w.x - ox, w.y - oz));
        static Vector2 Rot(Vector2 v) => new Vector2(v.x * ca - v.y * sa, v.x * sa + v.y * ca);
        static Vector4 Tree(Vector2 w, float y, float size) { var l = Local(w); return new Vector4(l.x, y, l.y, size); }
        /// <summary>Distance of a world point from the walls of block b (0 inside the ring).</summary>
        static float RingDist(Block b, Vector2 p)
        {
            var f = b.Foot; var c = b.Court;
            if (!f.Contains(p))
            {
                float dx = Mathf.Max(Mathf.Max(f.xMin - p.x, p.x - f.xMax), 0f), dz = Mathf.Max(Mathf.Max(f.yMin - p.y, p.y - f.yMax), 0f);
                return Mathf.Sqrt(dx * dx + dz * dz);
            }
            if (!c.Contains(p)) return 0f;
            return Mathf.Min(Mathf.Min(p.x - c.xMin, c.xMax - p.x), Mathf.Min(p.y - c.yMin, c.yMax - p.y));
        }
        /// <summary>The courtyard's garden a little above the quarter's highest ground piece under it (lawn, paving, kerbs: under 1 m).</summary>
        static float CourtLevel(QTwinData.QMesh m, Block b)
        {
            float x0 = float.MaxValue, x1 = float.MinValue, z0 = float.MaxValue, z1 = float.MinValue, top = 0f;
            for (int k = 0; k < 4; k++)
            {
                var q = Local(new Vector2((k & 1) == 0 ? b.Court.xMin : b.Court.xMax, (k & 2) == 0 ? b.Court.yMin : b.Court.yMax));
                x0 = Mathf.Min(x0, q.x); x1 = Mathf.Max(x1, q.x); z0 = Mathf.Min(z0, q.y); z1 = Mathf.Max(z1, q.y);
            }
            for (int t = 0; t + 2 < m.I.Length; t += 3)
            {
                Vector3 p = m.P[m.I[t]], q = m.P[m.I[t + 1]], r = m.P[m.I[t + 2]];
                float hy = Mathf.Max(p.y, Mathf.Max(q.y, r.y)); if (hy >= 1f) continue;
                if (Mathf.Max(p.x, Mathf.Max(q.x, r.x)) < x0 || Mathf.Min(p.x, Mathf.Min(q.x, r.x)) > x1) continue;
                if (Mathf.Max(p.z, Mathf.Max(q.z, r.z)) < z0 || Mathf.Min(p.z, Mathf.Min(q.z, r.z)) > z1) continue;
                top = Mathf.Max(top, hy);
            }
            return Mathf.Max(0.3f, top + 0.15f);
        }

        // ------------------------------------------------------------------ the model
        static void Build(Block b, float courtY)
        {
            float hw = Height - Parapet;
            var f = b.Foot; var c = b.Court;
            var fi = Inset(f, Coping); var co = Inset(c, -Coping);
            // the walls: the street side faces out, the courtyard side faces into the courtyard
            Ring(f, 1f, (A, Bv, n) => Facade(A, Bv, n, hw));
            Ring(c, -1f, (A, Bv, n) => Facade(A, Bv, n, hw));
            // the parapets (both faces) and their copings
            Ring(f, 1f, (A, Bv, n) => Face(A, Bv, n, hw, Height, Stone));
            Ring(fi, -1f, (A, Bv, n) => Face(A, Bv, n, hw, Height, Stone));
            Ring(c, -1f, (A, Bv, n) => Face(A, Bv, n, hw, Height, Stone));
            Ring(co, 1f, (A, Bv, n) => Face(A, Bv, n, hw, Height, Stone));
            Frame(f, fi, Height, Stone); Frame(co, c, Height, Stone);
            // the roof between the parapets, two plant units on it (one on each long run of the ring)
            Frame(fi, co, hw, Roof);
            float sx = Mathf.Min(8f, f.width * 0.18f);
            Box(new Vector2(f.center.x - sx, (fi.yMin + co.yMin) * 0.5f), new Vector2(6f, 3f), hw, hw + 1.8f);
            Box(new Vector2(f.center.x + sx, (co.yMax + fi.yMax) * 0.5f), new Vector2(6f, 3f), hw, hw + 1.8f);
            // the courtyard's garden, wall to wall
            Quad(V(c.xMin, courtY, c.yMin), V(c.xMax, courtY, c.yMin), V(c.xMax, courtY, c.yMax), V(c.xMin, courtY, c.yMax), Vector3.up, 0f, 0f, 0f, 0f, courtY, courtY, Garden);
        }
        static Rect Inset(Rect r, float d) => Rect.MinMaxRect(r.xMin + d, r.yMin + d, r.xMax - d, r.yMax - d);
        static Vector3 V(float x, float y, float z) => new Vector3(x, y, z);
        /// <summary>The four sides of a rectangle with their outward normals (side = 1) or the normals into it (side = −1).</summary>
        static void Ring(Rect r, float side, System.Action<Vector2, Vector2, Vector2> edge)
        {
            Vector2 a = new Vector2(r.xMin, r.yMin), b = new Vector2(r.xMax, r.yMin), c = new Vector2(r.xMax, r.yMax), d = new Vector2(r.xMin, r.yMax);
            edge(a, b, new Vector2(0f, -side)); edge(b, c, new Vector2(side, 0f)); edge(c, d, new Vector2(0f, side)); edge(d, a, new Vector2(-side, 0f));
        }
        /// <summary>A wall from A to B, a quad per storey; its bays fitted to the run so no window is cut at a corner.</summary>
        static void Facade(Vector2 A, Vector2 B, Vector2 n, float top)
        {
            float L = (B - A).magnitude, uL = Mathf.Max(1, Mathf.Round(L / Bay)) * Bay;
            for (int k = 0; k < Floors; k++)
            {
                float y0 = k * Storey, y1 = k == Floors - 1 ? top : (k + 1) * Storey;
                Quad(V(A.x, y0, A.y), V(B.x, y0, B.y), V(B.x, y1, B.y), V(A.x, y1, A.y), new Vector3(n.x, 0f, n.y), 0f, uL, uL, 0f, FloorF0[k], FloorF1[k], Wall);
            }
        }
        static void Face(Vector2 A, Vector2 B, Vector2 n, float y0, float y1, byte tag)
        {
            float L = (B - A).magnitude;
            Quad(V(A.x, y0, A.y), V(B.x, y0, B.y), V(B.x, y1, B.y), V(A.x, y1, A.y), new Vector3(n.x, 0f, n.y), 0f, L, L, 0f, y0, y1, tag);
        }
        /// <summary>The flat band between rectangle o and the rectangle i inside it (mitred at the corners), facing up.</summary>
        static void Frame(Rect o, Rect i, float y, byte tag)
        {
            Vector3 o0 = V(o.xMin, y, o.yMin), o1 = V(o.xMax, y, o.yMin), o2 = V(o.xMax, y, o.yMax), o3 = V(o.xMin, y, o.yMax);
            Vector3 i0 = V(i.xMin, y, i.yMin), i1 = V(i.xMax, y, i.yMin), i2 = V(i.xMax, y, i.yMax), i3 = V(i.xMin, y, i.yMax);
            Quad(o0, o1, i1, i0, Vector3.up, 0f, 0f, 0f, 0f, y, y, tag); Quad(o1, o2, i2, i1, Vector3.up, 0f, 0f, 0f, 0f, y, y, tag);
            Quad(o2, o3, i3, i2, Vector3.up, 0f, 0f, 0f, 0f, y, y, tag); Quad(o3, o0, i0, i3, Vector3.up, 0f, 0f, 0f, 0f, y, y, tag);
        }
        static void Box(Vector2 c, Vector2 size, float y0, float y1)
        {
            var r = new Rect(c - size * 0.5f, size);
            Ring(r, 1f, (A, Bv, n) => Face(A, Bv, n, y0, y1, Plant));
            Quad(V(r.xMin, y1, r.yMin), V(r.xMax, y1, r.yMin), V(r.xMax, y1, r.yMax), V(r.xMin, y1, r.yMax), Vector3.up, 0f, 0f, 0f, 0f, y1, y1, Plant);
        }
        /// <summary>A quad of world corners a b c d (x, page height, z) with its world normal: u along its bottom and top edges
        /// (u0 at a and d, u1 at b and c), facade heights f0 at the bottom (a, b) and f1 at the top (c, d). Wound to face along n.</summary>
        static void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 n, float ua, float ub, float uc, float ud, float f0, float f1, byte tag)
        {
            var ln = Rot(new Vector2(n.x, n.z)); var nl = new Vector3(ln.x, n.y, ln.y);
            int v0 = P.Count;
            Vtx(a, nl, ua, f0, tag); Vtx(b, nl, ub, f0, tag); Vtx(c, nl, uc, f1, tag); Vtx(d, nl, ud, f1, tag);
            // the quarter's mesh faces along cross(b − a, c − a) (the shader culls the back)
            bool flip = Vector3.Dot(Vector3.Cross(P[v0 + 1] - P[v0], P[v0 + 2] - P[v0]), nl) < 0f;
            if (!flip) { I.Add(v0); I.Add(v0 + 1); I.Add(v0 + 2); I.Add(v0); I.Add(v0 + 2); I.Add(v0 + 3); }
            else { I.Add(v0); I.Add(v0 + 2); I.Add(v0 + 1); I.Add(v0); I.Add(v0 + 3); I.Add(v0 + 2); }
        }
        static void Vtx(Vector3 w, Vector3 nl, float u, float fy, byte tag)
        {
            var l = Local(new Vector2(w.x, w.z)); P.Add(new Vector3(l.x, w.y, l.y)); N.Add(nl); U.Add(u); F.Add(fy); T.Add(tag);
        }
    }
}
