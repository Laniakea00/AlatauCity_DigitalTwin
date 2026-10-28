using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>A 220/110 kV substation as it is built: a fenced gravel yard (≈ 230 × 150 m) with the 220 kV switchyard (line portals,
    /// breakers and disconnectors on their insulator columns, the bus portals and busbars), two power transformers T1 / T2 with their
    /// radiators, conservators and bushings behind a fire wall, the 110 kV switchyard, the control building, lightning and floodlight masts,
    /// and the 220 kV overhead line coming in on lattice towers. One mesh of the landmark material, local x along the yard (220 kV at −x,
    /// 110 kV at +x), the line leaves at −x. Used by the presentation step «Прогноз: энергия 2034».</summary>
    public static class SubstationModel
    {
        public const float HalfX = 115f, HalfZ = 75f, TowerH = 42f;
        static readonly Color32 Gravel = LM.C("#8d8a82"), Concrete = LM.C("#b9b6ae"), SteelC = LM.C("#9aa1a8"), SteelDark = LM.C("#6c7278"),
            Porcelain = LM.C("#d9d4c8"), PorcelainBrown = LM.C("#8a5a3c"), Tank = LM.C("#5d6b62"), TankDark = LM.C("#46524a"), Wire = LM.C("#3b3f44"),
            White = LM.C("#ecebe6"), Blue = LM.C("#2f5d8a"), Glass = LM.C("#3c5a73"), Lamp = LM.C("#ffe2a8"), LitGravel = LM.C("#4f4a42"), Yellow = LM.C("#e8b21c"), Fence = LM.C("#7d8388");

        /// <summary>Builds the substation at 'site' (world x/z), its long side turned by 'yawDeg'. Returns the object (landmark material,
        /// property block set as a finished building); 'lineEnd' is where the overhead line leaves the frame (world x/z).
        /// The yard stands on a graded gravel platform at the level of its highest corner; the line towers stand on their own ground;
        /// an access road runs from the gate (+x side) to the nearest street.</summary>
        public static GameObject Build(Vector2 site, float yawDeg, out Vector2 lineEnd)
        {
            var rot = Quaternion.Euler(0f, yawDeg, 0f); bSite = site; bRot = rot;
            baseY = float.MinValue;
            foreach (var c in new[] { new Vector2(-1f, -1f), new Vector2(1f, -1f), new Vector2(1f, 1f), new Vector2(-1f, 1f), Vector2.zero })
                baseY = Mathf.Max(baseY, Ground(c.x * (HalfX + 6f), c.y * (HalfZ + 6f)));
            var k = new LandmarkKit();
            Yard(k); Switchyard220(k); Transformers(k); Switchyard110(k); Building(k); Masts(k);
            var line = Line(k); Access(k);
            var le = rot * line; lineEnd = site + new Vector2(le.x, le.z);
            FilmTrees.KeepClear(site, site, Mathf.Sqrt(HalfX * HalfX + HalfZ * HalfZ) + 14f);          // no trees in the yard, under the line
            FilmTrees.KeepClear(World(-HalfX, 0f), World(line.x + 240f, 0f), 12f);
            var sh = Shader.Find("AlatauCity/Landmark");
            var go = new GameObject("Substation 220/110 kV");
            go.transform.SetPositionAndRotation(new Vector3(site.x, baseY, site.y), rot);
            go.AddComponent<MeshFilter>().sharedMesh = k.ToMesh("Substation 220/110 kV");
            var mr = go.AddComponent<MeshRenderer>();
            if (sh != null) mr.sharedMaterial = new Material(sh) { name = "Substation" };
            var pb = new MaterialPropertyBlock();
            pb.SetFloat("_Reveal", 100000f); pb.SetFloat("_Build", 0f); pb.SetFloat("_Facade", 100000f); pb.SetFloat("_Land", 1f); pb.SetFloat("_Glow", -1f); pb.SetFloat("_Ghost", 0f); pb.SetFloat("_H", TowerH);
            mr.SetPropertyBlock(pb);
            return go;
        }

        static Vector2 bSite; static Quaternion bRot = Quaternion.identity; static float baseY;
        /// <summary>World position (x/z) of a point of the model's frame.</summary>
        static Vector2 World(float x, float z) { var w = bRot * new Vector3(x, 0f, z); return bSite + new Vector2(w.x, w.z); }
        static Vector2 Local(Vector2 w) { var l = Quaternion.Inverse(bRot) * new Vector3(w.x - bSite.x, 0f, w.y - bSite.y); return new Vector2(l.x, l.z); }
        /// <summary>Ground height (absolute) under a point of the model's frame.</summary>
        static float Ground(float x, float z) { var w = World(x, z); return CityGround.HeightAt(w.x, w.y); }
        /// <summary>The nearest street or main road (not a motorway) to a world point, within maxD.</summary>
        public static bool RoadNear(Vector2 p, float maxD, out Vector2 at)
        {
            at = p; float best = maxD * maxD; bool found = false;
            foreach (var e in Data.TwinData.Roads)
            {
                if (e.Cls == Data.TwinData.RoadClass.Highway) continue;
                var g = e.Geom; if (g == null || g.Length < 2) continue;
                for (int i = 0; i + 1 < g.Length; i++)
                {
                    var a = g[i]; var ab = g[i + 1] - a; float L2 = ab.sqrMagnitude; if (L2 < 1f) continue;
                    var q = a + ab * Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2); float d = (q - p).sqrMagnitude;
                    if (d < best) { best = d; at = q; found = true; }
                }
            }
            return found;
        }
        /// <summary>The access road: out of the gate, a short straight, then to the nearest street; asphalt following the ground.</summary>
        static void Access(LandmarkKit k)
        {
            var gate = new Vector2(HalfX + 2f, -48f); var out1 = gate + new Vector2(30f, 0f);
            if (!RoadNear(World(out1.x, out1.y), 900f, out var at)) return;
            var end = Local(at); var pts = new List<Vector2> { gate, out1 };
            // a gentle bend: the road leaves along +x, then heads for the street
            var dir = (end - out1).normalized; pts.Add(out1 + new Vector2(18f, 0f) + dir * 18f); pts.Add(end);
            for (int i = 1; i < pts.Count; i++) FilmTrees.KeepClear(World(pts[i - 1].x, pts[i - 1].y), World(pts[i].x, pts[i].y), 9f);
            var dense = new List<Vector2> { pts[0] };
            for (int i = 1; i < pts.Count; i++) { float d = Vector2.Distance(pts[i - 1], pts[i]); int n = Mathf.Max(1, Mathf.CeilToInt(d / 12f)); for (int j = 1; j <= n; j++) dense.Add(Vector2.Lerp(pts[i - 1], pts[i], j / (float)n)); }
            Color32 asphalt = LM.C("#55575a"), verge = LM.C("#9a978e");
            for (int i = 1; i < dense.Count; i++)
            {
                Vector2 a = dense[i - 1], b = dense[i]; var d = (b - a).normalized; var nn = new Vector2(-d.y, d.x);
                float ya = Ground(a.x, a.y) - baseY + 0.18f, yb = Ground(b.x, b.y) - baseY + 0.18f;
                if (i <= 2) { ya = Mathf.Max(ya, 0.42f); yb = Mathf.Max(yb, 0.42f); }
                Vector3 A(Vector2 p, float side, float y) => new Vector3(p.x + nn.x * side, y, p.y + nn.y * side);
                k.Slab(A(a, -4.5f, ya - 0.1f), A(b, -4.5f, yb - 0.1f), A(b, 4.5f, yb - 0.1f), A(a, 4.5f, ya - 0.1f), 0.3f, verge, LM.Paving);
                k.Slab(A(a, -3.5f, ya), A(b, -3.5f, yb), A(b, 3.5f, yb), A(a, 3.5f, ya), 0.3f, asphalt, LM.Paving);
            }
        }

        // ------------------------------------------------------------------ parts
        static void Yard(LandmarkKit k)
        {
            // the graded platform: gravel on top, its sides an embankment down to the lowest corner
            float drop = 0.4f; foreach (var q in new[] { new Vector2(-1f, -1f), new Vector2(1f, -1f), new Vector2(1f, 1f), new Vector2(-1f, 1f) }) drop = Mathf.Max(drop, baseY - Ground(q.x * HalfX, q.y * HalfZ) + 1.5f);
            k.Box(new Vector3(0f, 0.4f - drop * 0.5f, 0f), new Vector3(HalfX * 2f, drop, HalfZ * 2f), 0f, Gravel, LM.Roof, 3f, Gravel, LM.Roof);
            // the gravel under the floodlights: a faint warm glow, so the yard reads at dusk as a lit site, not a dark slab
            k.Box(new Vector3(0f, 0.41f, 0f), new Vector3(HalfX * 2f - 3f, 0.02f, HalfZ * 2f - 3f), 0f, LitGravel, LM.Light, 3f, LitGravel, LM.Light);
            // the inner road along the yard to the gate (+x), and the crossing between the switchyards
            k.Box(new Vector3(0f, 0.45f, -48f), new Vector3(HalfX * 2f - 4f, 0.1f, 6f), 0f, Concrete, LM.Paving, 3f, Concrete, LM.Paving);
            k.Box(new Vector3(-4f, 0.45f, 0f), new Vector3(6f, 0.1f, HalfZ * 2f - 8f), 0f, Concrete, LM.Paving, 3f, Concrete, LM.Paving);
            // the fence: a 2.5 m mesh panel on posts every 6 m, a gate on the road
            var c = new[] { new Vector2(-HalfX, -HalfZ), new Vector2(HalfX, -HalfZ), new Vector2(HalfX, HalfZ), new Vector2(-HalfX, HalfZ) };
            for (int i = 0; i < 4; i++)
            {
                Vector2 a = c[i], b = c[(i + 1) % 4]; float L = (b - a).magnitude; int n = Mathf.CeilToInt(L / 6f);
                for (int j = 0; j < n; j++)
                {
                    Vector2 p = Vector2.Lerp(a, b, j / (float)n), q = Vector2.Lerp(a, b, (j + 1) / (float)n);
                    if (i == 1 && Mathf.Abs(Vector2.Lerp(p, q, 0.5f).y + 48f) < 5f) continue;         // the gate opening
                    k.Beam(new Vector3(p.x, 0.4f, p.y), new Vector3(p.x, 2.9f, p.y), 0.14f, 0.14f, SteelDark, LM.Steel);
                    Wall(k, p, q, 0.5f, 2.8f, 0.05f, Fence, LM.Steel);
                }
            }
            k.Box(new Vector3(HalfX + 4f, 1.8f, -44f), new Vector3(3f, 3.6f, 3f), 0f, White, LM.Solid, 3f, Blue, LM.Roof);   // the guard post at the gate
        }

        // 220 kV: four bays across the yard (two lines, two transformers), line portals at the west edge, bus portals near the middle
        static readonly float[] Bays220 = { -54f, -20f, 20f, 54f };
        static void Switchyard220(LandmarkKit k)
        {
            Portal(k, -104f, -HalfZ + 6f, HalfZ - 6f, 20f, 1.0f);                                     // line portals
            Portal(k, -40f, -HalfZ + 6f, HalfZ - 6f, 16f, 0.9f);                                      // bus portals
            for (int w = 0; w < 2; w++) Wire3(k, new Vector3(-40f, 13.5f - w * 3f, -HalfZ + 6f), new Vector3(-40f, 13.5f - w * 3f, HalfZ - 6f), 1.6f, 0f);
            foreach (float z in Bays220)
            {
                // three phases of the bay: disconnector, current transformer, breaker, disconnector — insulator columns on steel stands
                for (int ph = -1; ph <= 1; ph++)
                {
                    float pz = z + ph * 4.2f;
                    Apparatus(k, -94f, pz, 2.6f, 3.6f, Porcelain);      // line disconnector
                    Apparatus(k, -84f, pz, 2.4f, 4.2f, PorcelainBrown);  // current transformer
                    Breaker(k, -72f, pz);
                    Apparatus(k, -58f, pz, 2.6f, 3.6f, Porcelain);      // bus disconnector
                    // the flexible connections between the apparatus, sagging a little
                    Sag(k, new Vector3(-104f, 17.5f, pz), new Vector3(-94f, 6.6f, pz), 1.2f);
                    Sag(k, new Vector3(-94f, 6.6f, pz), new Vector3(-84f, 7.0f, pz), 0.4f);
                    Sag(k, new Vector3(-84f, 7.0f, pz), new Vector3(-72f, 7.6f, pz), 0.4f);
                    Sag(k, new Vector3(-72f, 7.6f, pz), new Vector3(-58f, 6.6f, pz), 0.4f);
                    Sag(k, new Vector3(-58f, 6.6f, pz), new Vector3(-40f, 13.5f, pz), 1.0f);
                }
            }
        }
        static void Transformers(LandmarkKit k)
        {
            foreach (float z in new[] { -22f, 22f })
            {
                float x = -8f;
                k.Box(new Vector3(x, 0.6f, z), new Vector3(16f, 0.4f, 12f), 0f, Concrete, LM.Solid, 3f, Concrete, LM.Solid);     // oil pit edge
                k.Box(new Vector3(x, 0.55f, z), new Vector3(15f, 0.2f, 11f), 0f, LM.C("#5a5a56"), LM.Roof, 3f, LM.C("#5a5a56"), LM.Roof);   // gravel of the pit
                k.Box(new Vector3(x, 3.8f, z), new Vector3(9f, 5.8f, 5.6f), 0f, Tank, LM.Metal, 3f, Tank, LM.Metal);              // tank
                k.Box(new Vector3(x, 6.9f, z), new Vector3(9.4f, 0.4f, 6f), 0f, TankDark, LM.Metal, 3f, TankDark, LM.Metal);     // cover
                for (int s = -1; s <= 1; s += 2)                                                                                // radiators
                    for (int i = 0; i < 6; i++) k.Box(new Vector3(x - 3.6f + i * 1.45f, 3.6f, z + s * 3.6f), new Vector3(0.9f, 4.6f, 1.6f), 0f, TankDark, LM.Metal, 3f, TankDark, LM.Metal);
                k.Tube(new Vector3(x + 3.6f, 9.2f, z - 2.4f), new Vector3(x + 3.6f, 9.2f, z + 2.4f), 0.75f, 0.75f, 10, Tank, LM.Metal);   // conservator
                k.Beam(new Vector3(x + 3.6f, 7.1f, z), new Vector3(x + 3.6f, 8.5f, z), 0.3f, 0.3f, TankDark, LM.Metal);
                for (int ph = -1; ph <= 1; ph++)
                {
                    k.Cylinder(new Vector3(x - 2.6f, 7.1f, z + ph * 1.7f), 0.32f, 4.6f, 8, PorcelainBrown, LM.Solid, 1f, SteelC, LM.Metal, 0.2f);    // 220 kV bushings
                    k.Cylinder(new Vector3(x + 1.2f, 7.1f, z + ph * 1.5f), 0.24f, 2.6f, 8, PorcelainBrown, LM.Solid, 1f, SteelC, LM.Metal, 0.15f);   // 110 kV bushings
                    Sag(k, new Vector3(x - 2.6f, 11.8f, z + ph * 1.7f), new Vector3(-40f, 10.5f, z + ph * 4.2f), 1.4f);
                    Sag(k, new Vector3(x + 1.2f, 9.8f, z + ph * 1.5f), new Vector3(36f, 9.5f, z + ph * 3.2f), 1.2f);
                }
                Number(k, x - 4.6f, z, 4.4f);
            }
            k.Box(new Vector3(-8f, 4.6f, 0f), new Vector3(14f, 8.4f, 0.6f), 0f, Concrete, LM.Solid, 3f, Concrete, LM.Solid);     // fire wall between T1 and T2
        }
        static void Switchyard110(LandmarkKit k)
        {
            Portal(k, 36f, -HalfZ + 6f, HalfZ - 6f, 12f, 0.7f);                                       // bus portals
            Portal(k, 104f, -HalfZ + 6f, HalfZ - 6f, 13f, 0.7f);                                      // the portals of the outgoing 110 kV lines and cables
            for (int w = 0; w < 2; w++) Wire3(k, new Vector3(36f, 10.2f - w * 2.4f, -HalfZ + 6f), new Vector3(36f, 10.2f - w * 2.4f, HalfZ - 6f), 1.2f, 0f);
            for (int b = 0; b < 6; b++)
            {
                float z = -55f + b * 22f;
                for (int ph = -1; ph <= 1; ph++)
                {
                    float pz = z + ph * 3.2f;
                    Apparatus(k, 50f, pz, 2.2f, 2.8f, Porcelain);
                    Breaker(k, 66f, pz, 0.8f);
                    Apparatus(k, 82f, pz, 2.2f, 2.8f, PorcelainBrown);
                    Apparatus(k, 94f, pz, 2.2f, 2.8f, Porcelain);
                    Sag(k, new Vector3(36f, 10.2f, pz), new Vector3(50f, 5.0f, pz), 0.6f);
                    Sag(k, new Vector3(50f, 5.0f, pz), new Vector3(66f, 6.0f, pz), 0.3f);
                    Sag(k, new Vector3(66f, 6.0f, pz), new Vector3(82f, 5.0f, pz), 0.3f);
                    Sag(k, new Vector3(82f, 5.0f, pz), new Vector3(94f, 5.0f, pz), 0.2f);
                    Sag(k, new Vector3(94f, 5.0f, pz), new Vector3(104f, 11.5f, pz), 0.6f);
                }
            }
        }
        static void Building(LandmarkKit k)
        {
            // the control building (ОПУ): white with a blue band, windows lit at night, a cable gallery to the switchyards
            float x = -6f, z = -64f;
            k.Box(new Vector3(x, 4.2f, z), new Vector3(34f, 7.6f, 12f), 0f, White, LM.Solid, 3.6f, LM.C("#9ea3a6"), LM.Roof);
            k.Box(new Vector3(x, 7.4f, z), new Vector3(34.2f, 1.0f, 12.2f), 0f, Blue, LM.Solid, 3f, Blue, LM.Solid);
            for (int i = 0; i < 9; i++)
            {
                float wx = x - 15f + i * 3.75f;
                k.Box(new Vector3(wx, 4.6f, z + 6.02f), new Vector3(2.0f, 1.6f, 0.06f), 0f, i % 3 == 1 ? Lamp : Glass, i % 3 == 1 ? LM.Light : LM.Glass, 3f, Glass, LM.Glass);
            }
            k.Box(new Vector3(x - 21f, 2.0f, z + 2f), new Vector3(8f, 3.6f, 6f), 0f, White, LM.Solid, 3f, LM.C("#9ea3a6"), LM.Roof);   // the auxiliary block
        }
        static void Masts(LandmarkKit k)
        {
            // lightning masts over the switchyards and floodlight masts in the corners
            foreach (var p in new[] { new Vector2(-104f, -HalfZ + 2f), new Vector2(-104f, HalfZ - 2f), new Vector2(-40f, 0f), new Vector2(36f, -HalfZ + 2f), new Vector2(36f, HalfZ - 2f), new Vector2(104f, 0f) })
                k.Tube(new Vector3(p.x, 0.4f, p.y), new Vector3(p.x, 32f, p.y), 0.55f, 0.12f, 6, SteelC, LM.Steel, false);
            foreach (var p in new[] { new Vector2(-HalfX + 3f, -HalfZ + 3f), new Vector2(HalfX - 3f, -HalfZ + 3f), new Vector2(HalfX - 3f, HalfZ - 3f), new Vector2(-HalfX + 3f, HalfZ - 3f) })
            {
                k.Tube(new Vector3(p.x, 0.4f, p.y), new Vector3(p.x, 24f, p.y), 0.35f, 0.18f, 6, SteelC, LM.Steel, false);
                k.Box(new Vector3(p.x, 24.3f, p.y), new Vector3(2.4f, 0.6f, 1.0f), 0f, SteelDark, LM.Metal, 3f, SteelDark, LM.Metal);
                k.Box(new Vector3(p.x, 23.9f, p.y), new Vector3(2.2f, 0.25f, 0.9f), 0f, Lamp, LM.Light, 3f, Lamp, LM.Light);
            }
        }
        /// <summary>The 220 kV double-circuit line: the dead-end tower at the yard and four lattice towers going out (−x). Returns the far end (local).</summary>
        static Vector3 Line(LandmarkKit k)
        {
            float[] xs = { -150f, -390f, -630f, -870f, -1110f };
            // the line portals' attachment points (six phases: two circuits)
            var start = new List<Vector3>(); foreach (float z in new[] { Bays220[0], Bays220[3] }) for (int ph = -1; ph <= 1; ph++) start.Add(new Vector3(-104f, 19.5f, z + ph * 4.2f));
            var prev = start.ToArray(); bool first = true;
            foreach (float x in xs)
            {
                int v0 = k.VertexCount; var arms = Tower(k, x, 0f);
                float dy = Ground(x, 0f) - baseY; k.LiftFrom(v0, dy); for (int i = 0; i < 6; i++) arms[i].y += dy;   // the tower on its own ground
                for (int i = 0; i < 6; i++) Sag(k, prev[i], arms[i], first ? 2.5f : 7f);
                prev = arms; first = false;
            }
            return new Vector3(xs[xs.Length - 1] - 240f, 0f, 0f);
        }
        /// <summary>A lattice tower (≈ 42 m) with three cross-arms; returns the six insulator ends (two circuits).</summary>
        static Vector3[] Tower(LandmarkKit k, float x, float z)
        {
            float H = TowerH, b = 4.2f, w = 1.1f;
            Vector3 P(float sx, float sz, float y, float half) => new Vector3(x + sx * half, y, z + sz * half);
            // four legs tapering to the waist, then the top mast; diagonal bracing on every face
            float waist = 30f;
            for (int c = 0; c < 4; c++)
            {
                float sx = c == 0 || c == 3 ? -1f : 1f, sz = c < 2 ? -1f : 1f;
                k.Beam(P(sx, sz, -2.5f, b * 1.08f), P(sx, sz, waist, w), 0.35f, 0.35f, SteelC, LM.Steel);
                k.Beam(P(sx, sz, waist, w), P(sx, sz, H, w * 0.6f), 0.25f, 0.25f, SteelC, LM.Steel);
            }
            for (int lv = 0; lv < 5; lv++)
            {
                float y0 = 0.4f + lv * (waist - 0.4f) / 5f, y1 = 0.4f + (lv + 1) * (waist - 0.4f) / 5f;
                float h0 = Mathf.Lerp(b, w, (y0 - 0.4f) / (waist - 0.4f)), h1 = Mathf.Lerp(b, w, (y1 - 0.4f) / (waist - 0.4f));
                for (int f = 0; f < 4; f++)
                {
                    float ax = f == 0 ? -1 : f == 1 ? 1 : f == 2 ? 1 : -1, az = f == 0 ? -1 : f == 1 ? -1 : f == 2 ? 1 : 1;
                    float bx = f == 0 ? 1 : f == 1 ? 1 : f == 2 ? -1 : -1, bz = f == 0 ? -1 : f == 1 ? 1 : f == 2 ? 1 : -1;
                    k.Beam(P(ax, az, y0, h0), P(bx, bz, y1, h1), 0.14f, 0.14f, SteelC, LM.Steel);
                    k.Beam(P(bx, bz, y0, h0), P(ax, az, y1, h1), 0.14f, 0.14f, SteelC, LM.Steel);
                }
            }
            var ends = new Vector3[6]; float[] armY = { 31f, 35.5f, 40f }, armL = { 7.5f, 9.5f, 6.5f };
            for (int a = 0; a < 3; a++)
            {
                k.Beam(new Vector3(x, armY[a], z - armL[a]), new Vector3(x, armY[a], z + armL[a]), 0.5f, 0.6f, SteelC, LM.Steel);
                for (int s = 0; s < 2; s++)
                {
                    float zz = z + (s == 0 ? -armL[a] : armL[a]) * 0.92f;
                    var top = new Vector3(x, armY[a], zz); var bot = top + Vector3.down * 2.6f;
                    k.Beam(top, bot, 0.22f, 0.22f, Porcelain, LM.Solid, 1f);                  // insulator string
                    ends[s * 3 + a] = bot;
                }
            }
            k.Beam(new Vector3(x, H, z - 3f), new Vector3(x, H, z + 3f), 0.3f, 0.3f, SteelC, LM.Steel);   // earth wire peak
            return ends;
        }

        // ------------------------------------------------------------------ pieces
        /// <summary>A row of gantry portals across the yard (along z) at x: lattice columns every 'bay' metres with a beam on top.</summary>
        static void Portal(LandmarkKit k, float x, float z0, float z1, float h, float s)
        {
            int n = Mathf.Max(1, Mathf.RoundToInt((z1 - z0) / 17f));
            for (int i = 0; i <= n; i++)
            {
                float z = Mathf.Lerp(z0, z1, i / (float)n);
                // an A-frame column: two legs leaning together, braced
                k.Beam(new Vector3(x - 1.6f * s, 0.4f, z), new Vector3(x - 0.3f, h, z), 0.4f * s, 0.4f * s, SteelC, LM.Steel);
                k.Beam(new Vector3(x + 1.6f * s, 0.4f, z), new Vector3(x + 0.3f, h, z), 0.4f * s, 0.4f * s, SteelC, LM.Steel);
                for (int j = 1; j < 4; j++) { float y = h * j / 4f, hw = Mathf.Lerp(1.6f * s, 0.3f, y / h); k.Beam(new Vector3(x - hw, y, z), new Vector3(x + hw, y, z), 0.12f, 0.12f, SteelC, LM.Steel); }
                k.Box(new Vector3(x, 0.7f, z), new Vector3(4.2f * s, 0.6f, 1.6f), 0f, Concrete, LM.Solid, 3f, Concrete, LM.Solid);
            }
            // the cross beam: a lattice girder (two chords and diagonals)
            k.Beam(new Vector3(x, h, z0), new Vector3(x, h, z1), 0.7f * s, 0.5f, SteelC, LM.Steel);
            k.Beam(new Vector3(x, h - 1.4f, z0), new Vector3(x, h - 1.4f, z1), 0.35f * s, 0.3f, SteelC, LM.Steel);
            int m = Mathf.RoundToInt((z1 - z0) / 3f);
            for (int i = 0; i < m; i++) k.Beam(new Vector3(x, i % 2 == 0 ? h : h - 1.4f, Mathf.Lerp(z0, z1, i / (float)m)), new Vector3(x, i % 2 == 0 ? h - 1.4f : h, Mathf.Lerp(z0, z1, (i + 1) / (float)m)), 0.1f, 0.1f, SteelC, LM.Steel);
        }
        /// <summary>An apparatus on its stand: a steel post and an insulator column with a cap (disconnector, current transformer).</summary>
        static void Apparatus(LandmarkKit k, float x, float z, float stand, float col, Color32 ins)
        {
            k.Box(new Vector3(x, stand * 0.5f + 0.4f, z), new Vector3(0.45f, stand, 0.45f), 0f, SteelDark, LM.Steel, 3f, SteelDark, LM.Steel);
            k.Cylinder(new Vector3(x, stand + 0.4f, z), 0.22f, col, 8, ins, LM.Solid, 0.6f, SteelC, LM.Metal, 0.1f);
            k.Box(new Vector3(x, stand + col + 0.55f, z), new Vector3(0.9f, 0.3f, 0.5f), 0f, SteelC, LM.Metal, 3f, SteelC, LM.Metal);
        }
        /// <summary>A live-tank circuit breaker: a tall insulator with the interrupter head and a yellow drive cabinet.</summary>
        static void Breaker(LandmarkKit k, float x, float z, float s = 1f)
        {
            k.Box(new Vector3(x, 1.6f * s + 0.4f, z), new Vector3(0.6f, 3.2f * s, 0.6f), 0f, SteelDark, LM.Steel, 3f, SteelDark, LM.Steel);
            k.Box(new Vector3(x + 0.8f, 1.4f, z), new Vector3(0.8f, 1.6f, 0.9f), 0f, LM.C("#9da3a8"), LM.Metal, 3f, LM.C("#9da3a8"), LM.Metal);
            k.Cylinder(new Vector3(x, 3.2f * s + 0.4f, z), 0.3f, 3.6f * s, 8, Porcelain, LM.Solid, 0.6f, SteelC, LM.Metal);
            k.Box(new Vector3(x, 7.4f * s + 0.4f, z), new Vector3(1.6f * s, 0.6f, 0.6f), 0f, SteelC, LM.Metal, 3f, SteelC, LM.Metal);
        }
        /// <summary>A conductor between two points, sagging by 'sag' metres in the middle (four straight pieces).</summary>
        static void Sag(LandmarkKit k, Vector3 a, Vector3 b, float sag)
        {
            const int n = 4; var prev = a;
            for (int i = 1; i <= n; i++)
            {
                float t = i / (float)n; var p = Vector3.Lerp(a, b, t) + Vector3.down * (sag * 4f * t * (1f - t));
                k.Beam(prev, p, 0.12f, 0.12f, Wire, LM.Metal); prev = p;
            }
        }
        /// <summary>Three busbars side by side (spacing along x) between two points.</summary>
        static void Wire3(LandmarkKit k, Vector3 a, Vector3 b, float spacing, float sag)
        {
            for (int ph = -1; ph <= 1; ph++) Sag(k, a + Vector3.right * (ph * spacing), b + Vector3.right * (ph * spacing), sag);
        }
        static void Wall(LandmarkKit k, Vector2 a, Vector2 b, float y0, float y1, float t, Color32 c, int mat)
        {
            var d = b - a; float L = d.magnitude; if (L < 0.05f) return;
            float yaw = -Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg; var m = (a + b) * 0.5f;
            k.Box(new Vector3(m.x, (y0 + y1) * 0.5f, m.y), new Vector3(L, y1 - y0, t), yaw, c, mat, 3f, c, mat);
        }
        /// <summary>The yellow warning plate on the transformer.</summary>
        static void Number(LandmarkKit k, float x, float z, float y) => k.Box(new Vector3(x - 0.02f, y, z), new Vector3(0.06f, 1.0f, 1.6f), 0f, Yellow, LM.Solid, 3f, Yellow, LM.Solid);
    }
}
