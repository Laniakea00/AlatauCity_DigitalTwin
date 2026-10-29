using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The construction site of a landmark: a hoarding around the plot and tower cranes whose masts climb with the frame.
    /// Stages (by the object's progress p, see LandmarkSystem): 0–8 % site and excavation, 8–70 % the frame rises, 25–90 % the facade
    /// follows from the bottom up, 85–100 % paving and planting, at 100 % the site is struck and a light sweep runs up the building.</summary>
    public static class LandmarkSite
    {
        static readonly Color32 Hoarding = LM.C("#1f5fa8"), HoardingTop = LM.C("#f2f2f2"), CraneYellow = LM.C("#f2b705"), Ballast = LM.C("#8c8c88"), Cab = LM.C("#3b3f45"), Cable = LM.C("#2a2a2a");

        /// <summary>Blue hoarding 2.4 m high along the edge of the plot, a gate on the near side.</summary>
        public static Mesh Fence(float w, float d)
        {
            var k = new LandmarkKit(); float hw = w * 0.5f - 3f, hd = d * 0.5f - 3f, h = 2.4f, t = 0.18f, gate = Mathf.Min(16f, w * 0.2f);
            void Side(Vector3 a, Vector3 b)
            {
                var c = (a + b) * 0.5f; float L = (b - a).magnitude; if (L < 0.5f) return;
                float yaw = -Mathf.Atan2(b.z - a.z, b.x - a.x) * Mathf.Rad2Deg;
                k.Box(new Vector3(c.x, 0.3f + h * 0.5f, c.z), new Vector3(L, h, t), yaw, Hoarding, LM.Solid, h, HoardingTop, LM.Solid);
                k.Box(new Vector3(c.x, 0.3f + h + 0.12f, c.z), new Vector3(L, 0.24f, t + 0.04f), yaw, HoardingTop, LM.Solid, 1f, HoardingTop, LM.Solid);
            }
            Side(new Vector3(-hw, 0, -hd), new Vector3(-gate * 0.5f, 0, -hd));
            Side(new Vector3(gate * 0.5f, 0, -hd), new Vector3(hw, 0, -hd));
            Side(new Vector3(hw, 0, -hd), new Vector3(hw, 0, hd));
            Side(new Vector3(hw, 0, hd), new Vector3(-hw, 0, hd));
            Side(new Vector3(-hw, 0, hd), new Vector3(-hw, 0, -hd));
            return k.ToMesh("Hoarding");
        }

        /// <summary>Lattice mast of a tower crane, 2 m square, from the ground to 'h' (clipped by _Reveal as it climbs).</summary>
        public static Mesh Mast(float h)
        {
            var k = new LandmarkKit(); float s = 1.0f, step = 4f;
            Vector3[] c = { new Vector3(-s, 0, -s), new Vector3(s, 0, -s), new Vector3(s, 0, s), new Vector3(-s, 0, s) };
            for (int i = 0; i < 4; i++) k.Beam(c[i], c[i] + Vector3.up * h, 0.28f, 0.28f, CraneYellow, LM.Steel);
            for (float y = 0; y < h - 0.1f; y += step)
                for (int i = 0; i < 4; i++)
                {
                    var a = c[i] + Vector3.up * y; var b = c[(i + 1) % 4] + Vector3.up * (y + step);
                    k.Beam(a, b, 0.12f, 0.12f, CraneYellow, LM.Steel);
                    k.Beam(c[i] + Vector3.up * y, c[(i + 1) % 4] + Vector3.up * y, 0.14f, 0.14f, CraneYellow, LM.Steel);
                }
            // base ballast
            k.Box(new Vector3(0, 0.3f + 0.8f, 0), new Vector3(5f, 1.6f, 5f), 0, Ballast, LM.Solid, 1.6f, Ballast, LM.Solid);
            return k.ToMesh("Crane mast");
        }

        /// <summary>Slewing part of a tower crane at the mast top: jib (length j), counter-jib with ballast, cab and A-frame. The trolley and the
        /// hook are separate pieces moved by CraneMotion.</summary>
        public static Mesh Head(float j)
        {
            var k = new LandmarkKit(); float cj = j * 0.32f;
            // turntable + cab
            k.Box(new Vector3(0, 0.8f, 0), new Vector3(2.6f, 1.6f, 2.6f), 0, CraneYellow, LM.Steel, 2f, CraneYellow, LM.Steel);
            k.Box(new Vector3(1.6f, 2.2f, 1.4f), new Vector3(1.8f, 2.0f, 1.8f), 0, Cab, LM.Glass, 2f, Cab, LM.Steel);
            // jib: triangular lattice (two bottom chords, one top chord) with diagonals
            float y0 = 1.8f, jh = 1.8f;
            Vector3 b0 = new Vector3(0, y0, -0.8f), b1 = new Vector3(0, y0, 0.8f), t0 = new Vector3(0, y0 + jh, 0);
            Vector3 dx = Vector3.right;
            k.Beam(b0 - dx * cj, b0 + dx * j, 0.22f, 0.22f, CraneYellow, LM.Steel);
            k.Beam(b1 - dx * cj, b1 + dx * j, 0.22f, 0.22f, CraneYellow, LM.Steel);
            k.Beam(t0, t0 + dx * (j - 2f), 0.2f, 0.2f, CraneYellow, LM.Steel);
            for (float x = 0; x < j - 2.5f; x += 3f)
            {
                k.Beam(b0 + dx * x, t0 + dx * (x + 1.5f), 0.09f, 0.09f, CraneYellow, LM.Steel);
                k.Beam(b1 + dx * x, t0 + dx * (x + 1.5f), 0.09f, 0.09f, CraneYellow, LM.Steel);
                k.Beam(b0 + dx * x, b1 + dx * x, 0.09f, 0.09f, CraneYellow, LM.Steel);
            }
            // A-frame and pendants
            var apex = new Vector3(0, y0 + 9f, 0);
            k.Beam(b0, apex, 0.25f, 0.25f, CraneYellow, LM.Steel); k.Beam(b1, apex, 0.25f, 0.25f, CraneYellow, LM.Steel);
            k.Beam(apex, t0 + dx * (j * 0.62f), 0.07f, 0.07f, Cable, LM.Steel);
            k.Beam(apex, new Vector3(-cj, y0 + 0.3f, 0), 0.07f, 0.07f, Cable, LM.Steel);
            // counterweight blocks
            k.Box(new Vector3(-cj + 2.2f, y0 - 0.9f, 0), new Vector3(4f, 2.6f, 2.4f), 0, Ballast, LM.Solid, 1.3f, Ballast, LM.Solid);
            // the trolley, the hook line and the load move on their own (CraneMotion)
            return k.ToMesh("Crane head");
        }

        /// <summary>Where the cranes stand: beside the tallest part of the model (local plot coordinates), never inside the building —
        /// the plan of everything above 2.5 m (walls, slabs, roofs, trees) is drawn into a 1 m grid, the closed outlines are filled
        /// (a tower whose floors are open rings still counts as solid), and the mast goes to the nearest free spot around the top;
        /// for wide or tall plots a second crane stands on the other side.</summary>
        public static List<Vector3> CraneSpots(Mesh model, float padW, float padD, float height)
        {
            var spots = new List<Vector3>(); var vs = model.vertices; if (vs.Length == 0) return spots;
            float maxY = 0f; foreach (var v in vs) maxY = Mathf.Max(maxY, v.y);
            Vector2 c = Vector2.zero; int nTop = 0;
            foreach (var v in vs) if (v.y > maxY * 0.8f) { c += new Vector2(v.x, v.z); nTop++; }
            if (nTop > 0) c /= nTop;
            var busy = Occupancy(model, padW, padD, out int gw, out int gd, out float ox, out float oz);
            bool Free(Vector2 q, float r)
            {
                if (Mathf.Abs(q.x) > padW * 0.5f - 8f || Mathf.Abs(q.y) > padD * 0.5f - 8f) return false;
                int x0 = Mathf.FloorToInt(q.x - r - ox), x1 = Mathf.FloorToInt(q.x + r - ox), z0 = Mathf.FloorToInt(q.y - r - oz), z1 = Mathf.FloorToInt(q.y + r - oz);
                for (int z = z0; z <= z1; z++) for (int x = x0; x <= x1; x++)
                {
                    if (x < 0 || z < 0 || x >= gw || z >= gd) return false;
                    if (busy[z * gw + x]) return false;
                }
                return true;
            }
            // nearest free ring around the top; on a ring, the side towards the plot centre first
            Vector2? Near(Vector2 from, Vector2 pref, float rMin, System.Func<Vector2, bool> ok)
            {
                float a0 = Mathf.Atan2(pref.y, pref.x);
                for (float r = rMin; r < 170f; r += 1.5f)
                    for (int k = 0; k <= 36; k++)
                        foreach (int sgn in new[] { 1, -1 })
                        {
                            if (k == 0 && sgn < 0) continue;
                            float a = a0 + sgn * k * 5f * Mathf.Deg2Rad; var q = from + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r;
                            if (Free(q, 3.4f) && ok(q)) return q;
                        }
                return null;
            }
            var dir = c.sqrMagnitude > 1f ? -c.normalized : new Vector2(1f, 0.4f).normalized;
            var p = Near(c, dir, 3f, _ => true);
            if (p == null) return spots;
            spots.Add(new Vector3(p.Value.x, 0.3f, p.Value.y));
            if (padW * padD > 60000f || height > 120f)
            {
                var q0 = new Vector2(-p.Value.x * 0.55f, -p.Value.y * 0.55f + padD * 0.18f);
                var q = Near(q0, (c - q0).sqrMagnitude > 1f ? (c - q0).normalized : Vector2.right, 0f, x => (x - p.Value).magnitude > 40f);
                if (q != null) spots.Add(new Vector3(q.Value.x, 0.3f, q.Value.y));
            }
            return spots;
        }

        /// <summary>Plan of the model above 2.5 m in 1 m cells (true = built), with the areas closed by outlines filled.</summary>
        static bool[] Occupancy(Mesh model, float padW, float padD, out int gw, out int gd, out float ox, out float oz)
        {
            ox = -padW * 0.5f - 4f; oz = -padD * 0.5f - 4f; gw = Mathf.CeilToInt(padW + 8f); gd = Mathf.CeilToInt(padD + 8f);
            var busy = new bool[gw * gd]; var vs = model.vertices; var tris = model.triangles; const float R = 0.75f;
            for (int t = 0; t + 2 < tris.Length; t += 3)
            {
                Vector3 A = vs[tris[t]], B = vs[tris[t + 1]], C = vs[tris[t + 2]];
                if (Mathf.Max(A.y, Mathf.Max(B.y, C.y)) < 2.5f) continue;
                Vector2 a = new Vector2(A.x, A.z), b = new Vector2(B.x, B.z), cc = new Vector2(C.x, C.z);
                int x0 = Mathf.Max(0, Mathf.FloorToInt(Mathf.Min(a.x, Mathf.Min(b.x, cc.x)) - R - ox)), x1 = Mathf.Min(gw - 1, Mathf.FloorToInt(Mathf.Max(a.x, Mathf.Max(b.x, cc.x)) + R - ox));
                int z0 = Mathf.Max(0, Mathf.FloorToInt(Mathf.Min(a.y, Mathf.Min(b.y, cc.y)) - R - oz)), z1 = Mathf.Min(gd - 1, Mathf.FloorToInt(Mathf.Max(a.y, Mathf.Max(b.y, cc.y)) + R - oz));
                for (int z = z0; z <= z1; z++) for (int x = x0; x <= x1; x++)
                {
                    int i = z * gw + x; if (busy[i]) continue;
                    var q = new Vector2(ox + x + 0.5f, oz + z + 0.5f);
                    if (InTri(q, a, b, cc) || SegD(q, a, b) <= R || SegD(q, b, cc) <= R || SegD(q, cc, a) <= R) busy[i] = true;
                }
            }
            // fill what the outlines enclose: flood the free cells from the border, the free cells left over are inside a building
            var seen = new bool[gw * gd]; var st = new Stack<int>();
            for (int x = 0; x < gw; x++) { st.Push(x); st.Push((gd - 1) * gw + x); }
            for (int z = 0; z < gd; z++) { st.Push(z * gw); st.Push(z * gw + gw - 1); }
            while (st.Count > 0)
            {
                int i = st.Pop(); if (seen[i] || busy[i]) continue; seen[i] = true;
                int x = i % gw, z = i / gw;
                if (x > 0) st.Push(i - 1); if (x < gw - 1) st.Push(i + 1); if (z > 0) st.Push(i - gw); if (z < gd - 1) st.Push(i + gw);
            }
            for (int i = 0; i < busy.Length; i++) if (!seen[i]) busy[i] = true;
            return busy;
        }
        static bool InTri(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
        {
            float d1 = (p.x - b.x) * (a.y - b.y) - (a.x - b.x) * (p.y - b.y), d2 = (p.x - c.x) * (b.y - c.y) - (b.x - c.x) * (p.y - c.y), d3 = (p.x - a.x) * (c.y - a.y) - (c.x - a.x) * (p.y - a.y);
            bool neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0;
            return !(neg && pos);
        }
        static float SegD(Vector2 p, Vector2 a, Vector2 b)
        {
            var ab = b - a; float l2 = ab.sqrMagnitude; if (l2 < 1e-6f) return (p - a).magnitude;
            float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / l2); return (p - (a + ab * t)).magnitude;
        }

        /// <summary>Top of the tallest part of the model (local plot coordinates): where its label is anchored.</summary>
        public static Vector3 TopAnchor(Mesh model)
        {
            var vs = model.vertices; if (vs.Length == 0) return Vector3.zero;
            float maxY = 0f; foreach (var v in vs) maxY = Mathf.Max(maxY, v.y);
            Vector3 c = Vector3.zero; int n = 0;
            foreach (var v in vs) if (v.y > maxY * 0.92f) { c += v; n++; }
            c /= Mathf.Max(n, 1); c.y = maxY; return c;
        }

        // ------------------------------------------------------------------ the crane at work
        static Mesh trolleyM, cableM, hookM;
        /// <summary>The trolley under the jib (origin at its running rail, 1.8 m above the slewing ring).</summary>
        public static Mesh Trolley()
        {
            if (trolleyM != null) return trolleyM;
            var k = new LandmarkKit();
            k.Box(new Vector3(0, -0.35f, 0), new Vector3(1.6f, 0.5f, 2.0f), 0, Cab, LM.Steel, 1f, Cab, LM.Steel);
            k.Box(new Vector3(0, -0.75f, 0), new Vector3(0.7f, 0.35f, 0.7f), 0, Cab, LM.Steel, 1f, Cab, LM.Steel);
            return trolleyM = k.ToMesh("Crane trolley");
        }
        /// <summary>The hoist ropes: 1 m long downwards from the origin (scaled in y to the hook depth).</summary>
        public static Mesh HoistRope()
        {
            if (cableM != null) return cableM;
            var k = new LandmarkKit();
            k.Beam(new Vector3(-0.18f, 0f, 0f), new Vector3(-0.18f, -1f, 0f), 0.05f, 0.05f, Cable, LM.Steel);
            k.Beam(new Vector3(0.18f, 0f, 0f), new Vector3(0.18f, -1f, 0f), 0.05f, 0.05f, Cable, LM.Steel);
            return cableM = k.ToMesh("Crane hoist rope");
        }
        /// <summary>The hook block with its load (a bundle of rebar on slings, or a concrete skip): origin at the top of the block.</summary>
        public static Mesh Hook()
        {
            if (hookM != null) return hookM;
            var k = new LandmarkKit();
            k.Box(new Vector3(0, -0.45f, 0), new Vector3(0.7f, 0.9f, 0.45f), 0, CraneYellow, LM.Steel, 1f, CraneYellow, LM.Steel);
            k.Beam(new Vector3(0, -0.9f, 0), new Vector3(-1.4f, -3.0f, 0), 0.04f, 0.04f, Cable, LM.Steel);
            k.Beam(new Vector3(0, -0.9f, 0), new Vector3(1.4f, -3.0f, 0), 0.04f, 0.04f, Cable, LM.Steel);
            k.Box(new Vector3(0, -3.3f, 0), new Vector3(4.2f, 0.6f, 0.9f), 0, Rebar, LM.Steel, 1f, Rebar, LM.Steel);
            return hookM = k.ToMesh("Crane hook and load");
        }
        static readonly Color32 Rebar = LM.C("#6b5446");

        /// <summary>A tower crane at work, added to every crane head (FilmLife does it once the landmarks stand): it slews slowly to a
        /// new heading (about 1.5° a second, a full turn in four minutes, easing in and out), runs the trolley along the jib to a new
        /// radius (0.5 m/s), lowers the hook (0.8 m/s), waits while the load is slung, lifts it and moves on. The heading it takes
        /// overrides the plain spin LandmarkSystem gives the head; the hook never goes below the roof or the ground under it.</summary>
        public class CraneMotion : MonoBehaviour
        {
            Transform trolley, cable, hook; float jib, yaw, yaw0, yawT, slewT, slewDur, rad, radT, drop, dropT, wait; int stage; System.Random rnd;
            const float Rail = 1.8f;

            void Start()
            {
                var mf = GetComponent<MeshFilter>(); var mr = GetComponent<MeshRenderer>();
                if (mf == null || mf.sharedMesh == null || mr == null) { enabled = false; return; }
                jib = Mathf.Max(20f, mf.sharedMesh.bounds.max.x);
                rnd = new System.Random(GetInstanceID() * 7919 + Mathf.RoundToInt(transform.position.x));
                yaw = transform.localEulerAngles.y; yawT = yaw; rad = jib * (0.35f + 0.4f * (float)rnd.NextDouble()); radT = rad; drop = 6f; dropT = drop;
                stage = rnd.Next(4); wait = (float)rnd.NextDouble() * 6f; yaw0 = yaw; yawT = yaw + 50f; slewDur = 40f;
                trolley = Piece("Crane trolley", Trolley(), mr.sharedMaterial, transform);
                cable = Piece("Crane hoist rope", HoistRope(), mr.sharedMaterial, trolley);
                hook = Piece("Crane hook", Hook(), mr.sharedMaterial, trolley);
                Place();
            }
            static Transform Piece(string name, Mesh m, Material mat, Transform parent)
            {
                var go = new GameObject(name); go.transform.SetParent(parent, false);
                go.AddComponent<MeshFilter>().sharedMesh = m; var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = mat;
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On; return go.transform;
            }
            /// <summary>How deep the hook may go from the jib: down to 3 m above whatever is under the trolley (the building, the plot, the ground).</summary>
            float MaxDrop()
            {
                var p = transform.TransformPoint(new Vector3(rad, Rail - 1f, 0f));
                float ground = CityGround.HeightAt(p.x, p.z), lim = p.y - ground - 3f;
                if (Physics.Raycast(p, Vector3.down, out var hit, 600f, ~0, QueryTriggerInteraction.Ignore)) lim = Mathf.Min(lim, hit.distance - 3f);
                return Mathf.Max(lim, 2f);
            }
            void LateUpdate()
            {
                if (trolley == null) return;
                float dt = Mathf.Min(Time.deltaTime, 0.1f);
                switch (stage)
                {
                    case 0:     // slew to a new heading and run the trolley out or in at the same time
                        slewT += dt; float k = Mathf.Clamp01(slewT / slewDur); yaw = Mathf.LerpAngle(yaw0, yawT, k * k * (3f - 2f * k));
                        rad = Mathf.MoveTowards(rad, radT, 0.5f * dt);
                        if (k >= 1f && Mathf.Abs(rad - radT) < 0.01f) { stage = 1; dropT = Mathf.Min(MaxDrop(), 12f + 30f * (float)rnd.NextDouble()); }
                        break;
                    case 1:     // lower the hook
                        drop = Mathf.MoveTowards(drop, dropT, 0.8f * dt); if (Mathf.Abs(drop - dropT) < 0.01f) { stage = 2; wait = 8f + 10f * (float)rnd.NextDouble(); }
                        break;
                    case 2:     // the load is slung or set down
                        wait -= dt; if (wait <= 0f) { stage = 3; dropT = 4f + 3f * (float)rnd.NextDouble(); }
                        break;
                    default:    // lift, then pick the next move
                        drop = Mathf.MoveTowards(drop, dropT, 0.8f * dt);
                        if (Mathf.Abs(drop - dropT) < 0.01f)
                        {
                            float turn = (40f + 120f * (float)rnd.NextDouble()) * (rnd.Next(2) == 0 ? 1f : -1f);
                            yaw0 = yaw; yawT = yaw + turn; slewT = 0f; slewDur = Mathf.Abs(turn) / 1.5f + 6f;
                            radT = jib * (0.25f + 0.67f * (float)rnd.NextDouble()); stage = 0;
                        }
                        break;
                }
                drop = Mathf.Min(drop, MaxDropCached());
                transform.localRotation = Quaternion.Euler(0f, yaw, 0f);
                Place();
            }
            float cachedDrop = 1000f, cacheT;
            float MaxDropCached() { if (Time.time - cacheT > 0.5f || cachedDrop > 999f) { cachedDrop = MaxDrop(); cacheT = Time.time; } return cachedDrop; }
            void Place()
            {
                trolley.localPosition = new Vector3(rad, Rail, 0f);
                cable.localPosition = new Vector3(0f, -0.6f, 0f); cable.localScale = new Vector3(1f, Mathf.Max(drop - 0.6f, 0.1f), 1f);
                hook.localPosition = new Vector3(0f, -drop, 0f);
            }
        }
    }
}
