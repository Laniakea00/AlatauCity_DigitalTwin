using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Street lamps of the film look along the drawn roads (FilmRoads.Lamps), open in the year shown: posts with an arm over the
    /// carriageway and a warm-white LED head (≈ 3500 K) that lights up from dusk (FilmLook.Lamps). Typical city practice, not survey data:
    /// main roads 10 m posts every 32 m on both sides, streets 7 m posts every 25 m on one side, a 14 m mast with two arms every 40 m in
    /// the median of the motorway and the ring, 12 m posts along each carriageway of a dual motorway and along ramps. AlatauRoad draws the
    /// light of the same lamps on the asphalt from the same rule. Drawn with GPU instancing near the camera only; nothing from high up.</summary>
    public class FilmLamps : MonoBehaviour
    {
        // ------------------------------------------------------------------ the rule (shared with AlatauRoad.shader: keep in step)
        /// <summary>Spacing (m) and placement of the lamps of a road: mode 1 median mast, 2 both sides, 3 one side at x &lt; 0 (the outer
        /// kerb of a one-way carriageway; FilmRoads turns it into 6 = x &gt; 0 where the twin carriageway lies on that side), 4 one side of a
        /// street (x &gt; 0); cls 0 street, 1 main road, 2 motorway / ring / ramp.</summary>
        public static void Rule(TwinData.RoadClass c, bool ramp, bool oneWay, out float step, out int mode, out int cls)
        {
            if (ramp) { step = 35f; mode = 3; cls = 2; return; }
            switch (c)
            {
                case TwinData.RoadClass.Highway: case TwinData.RoadClass.Ring: cls = 2; if (oneWay) { step = 38f; mode = 3; } else { step = 40f; mode = 1; } break;
                case TwinData.RoadClass.Main: cls = 1; step = 32f; mode = oneWay ? 3 : 2; break;
                default: cls = 0; if (oneWay) { step = 26f; mode = 3; } else { step = 25f; mode = 4; } break;
            }
        }
        /// <summary>Height of the lamp head above the road (m).</summary>
        public static float Height(int mode, int cls) => mode == 1 ? 14f : mode == 2 ? 10f : mode == 4 ? 7f : cls == 2 ? 12f : cls == 1 ? 10f : 8f;
        /// <summary>Metres along a road of the k-th lamp; lamps stay 14 m clear of the road's ends (the junctions and their crossings).</summary>
        public static float At(int k, float step) => (k + 0.5f) * step;
        public const float EndClear = 14f;
        /// <summary>Post set back behind the kerb (m) and arm length by class; the head hangs at (kerb + back - arm) from the centre line.</summary>
        public static float Back(int cls) => cls == 2 ? 1.4f : cls == 1 ? 1.2f : 0.9f;
        public static float Arm(int cls) => cls == 2 ? 2.5f : cls == 1 ? 2.0f : 1.2f;

        // ------------------------------------------------------------------ placement
        const float Cell = 200f;
        static readonly bool High = Application.platform != RuntimePlatform.WebGLPlayer;
        static FilmLamps instance;
        struct Lamp { public Vector3 P; public float Yaw; public byte Type; public Vector4 Years; }
        readonly List<Lamp> lamps = new List<Lamp>();
        readonly Dictionary<long, List<int>> cells = new Dictionary<long, List<int>>();
        bool built, failed; Material mat; Mesh[] meshes;
        // per mesh type: batches of at most 1023 matrices, allocated once
        const int Types = 4, Batch = 1023;
        Matrix4x4[][][] mats; int[] counts = new int[Types];
        int cap; Vector3 lastFocus = new Vector3(1e9f, 0, 0); float lastR; int lastYear = -1, lastSc = -1, lastFrame = -1;
        readonly List<long> near = new List<long>();
        static readonly int FadeId = Shader.PropertyToID("_AlatauLampFade"), OnId = Shader.PropertyToID("_AlatauLampOn");

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (instance == null) new GameObject("Film lamps").AddComponent<FilmLamps>(); }
        void Awake() { instance = this; }

        void LateUpdate() { Draw(); }
        /// <summary>Queue the lamps for this frame (the capture tool renders by hand: FilmLook.Redraw calls this before it does).</summary>
        public static void DrawNow() { if (instance != null) instance.Draw(); }

        void Draw()
        {
            if (failed || !FilmLook.Active || Time.frameCount == lastFrame) return;
            var cam = Camera.main; if (cam == null) return;
            var mc = cam.GetComponent<MapCamera>(); if (mc == null) return;
            float dist = mc.distance; if (dist > 4200f) return;                         // from high up the lamps are only their light on the roads
            if (!built) { if (FilmRoads.Lamps.Count == 0) return; Build(); if (failed) return; }
            else if (!withTrees && Time.frameCount % 30 == 0 && TreeRows() != null) Place();      // the street trees came later: place again
            lastFrame = Time.frameCount;
            float R = Mathf.Clamp(dist * 1.7f, 500f, High ? 3000f : 1800f);
            Vector3 f = mc.target; int year = TwinState.Year < 1 ? 2050 : TwinState.Year, sc = Mathf.Clamp((int)TwinState.Scenario, 0, 3);
            if (year != lastYear || sc != lastSc || Mathf.Abs(R - lastR) > lastR * 0.2f || (new Vector2(f.x - lastFocus.x, f.z - lastFocus.z)).sqrMagnitude > (R * 0.15f) * (R * 0.15f))
                Collect(f, R, year, sc);
            float on = FilmLook.Lamps;
            Shader.SetGlobalFloat(OnId, on);
            Shader.SetGlobalVector(FadeId, new Vector4(f.x, f.z, R, R * 0.25f));
            var shadows = High && dist < 1200f && on < 0.5f ? UnityEngine.Rendering.ShadowCastingMode.On : UnityEngine.Rendering.ShadowCastingMode.Off;
            for (int t = 0; t < Types; t++)
            {
                int left = counts[t];
                for (int b = 0; left > 0; b++)
                {
                    int n = Mathf.Min(left, Batch);
                    Graphics.DrawMeshInstanced(meshes[t], 0, mat, mats[t][b], n, null, shadows, true, 0, null);
                    left -= n;
                }
            }
        }

        static long Key(int x, int z) => ((long)(x + 100000) << 32) | (uint)(z + 100000);

        void Collect(Vector3 f, float R, int year, int sc)
        {
            lastFocus = f; lastR = R; lastYear = year; lastSc = sc;
            for (int t = 0; t < Types; t++) counts[t] = 0;
            int c0x = Mathf.FloorToInt((f.x - R) / Cell), c1x = Mathf.FloorToInt((f.x + R) / Cell), c0z = Mathf.FloorToInt((f.z - R) / Cell), c1z = Mathf.FloorToInt((f.z + R) / Cell);
            near.Clear();
            for (int cz = c0z; cz <= c1z; cz++) for (int cx = c0x; cx <= c1x; cx++) if (cells.ContainsKey(Key(cx, cz))) near.Add(Key(cx, cz));
            // the nearest cells first, so the cap drops the far lamps
            near.Sort((a, b) => CellD(a, f).CompareTo(CellD(b, f)));
            int total = 0; float R2 = R * R;
            foreach (long k in near)
            {
                foreach (int i in cells[k])
                {
                    var l = lamps[i];
                    if (l.Years[sc] > year) continue;
                    float dx = l.P.x - f.x, dz = l.P.z - f.z; if (dx * dx + dz * dz > R2) continue;
                    int t = l.Type, n = counts[t]; if (n >= cap) continue;
                    mats[t][n / Batch][n % Batch] = Matrix4x4.TRS(l.P, Quaternion.Euler(0f, l.Yaw, 0f), Vector3.one);
                    counts[t] = n + 1; total++;
                }
                if (total >= cap) break;
            }
        }
        static float CellD(long k, Vector3 f)
        {
            float x = ((int)(k >> 32) - 100000 + 0.5f) * Cell - f.x, z = ((int)(uint)(k & 0xFFFFFFFF) - 100000 + 0.5f) * Cell - f.z; return x * x + z * z;
        }

        void Build()
        {
            built = true;
            var sh = Shader.Find("AlatauCity/Lamp");
            if (sh == null) { failed = true; Debug.LogWarning("[Alatau] film lamps: shader missing"); return; }
            mat = new Material(sh) { name = "Film lamps", enableInstancing = true };
            meshes = new[] { MakeLamp(7f, 1.2f, false, 0.16f), MakeLamp(10f, 2.0f, false, 0.2f), MakeLamp(12f, 2.5f, false, 0.24f), MakeLamp(14f, 2.5f, true, 0.32f) };
            cap = High ? 6000 : 1800;
            mats = new Matrix4x4[Types][][];
            for (int t = 0; t < Types; t++) { int nb = (cap + Batch - 1) / Batch; mats[t] = new Matrix4x4[nb][]; for (int b = 0; b < nb; b++) mats[t][b] = new Matrix4x4[Batch]; }
            Place();
        }

        // the street trees of the film look (FilmTrees keeps them by 320 m cells, x / z / species): a post never stands in a crown
        Dictionary<long, List<Vector3>> trees; bool withTrees;
        static Dictionary<long, List<Vector3>> TreeRows()
        {
            try
            {
                var ft = FilmTrees.Instance; if (ft == null) return null;
                var f = typeof(FilmTrees).GetField("street", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                var d = f != null ? f.GetValue(ft) as Dictionary<long, List<Vector3>> : null;
                return d != null && d.Count > 0 ? d : null;
            }
            catch (System.Exception) { return null; }
        }
        bool NearTree(Vector2 p)
        {
            if (trees == null) return false;
            const float TC = 320f, R = 3.4f;
            for (int dx = -1; dx <= 1; dx += 2) for (int dz = -1; dz <= 1; dz += 2)
            {
                int cx = Mathf.FloorToInt((p.x + dx * R) / TC), cz = Mathf.FloorToInt((p.y + dz * R) / TC);
                if (dx > 0 && cx == Mathf.FloorToInt((p.x - R) / TC) || dz > 0 && cz == Mathf.FloorToInt((p.y - R) / TC)) continue;     // each cell once
                if (!trees.TryGetValue(Key(cx, cz), out var l)) continue;
                foreach (var t in l) { float ex = t.x - p.x, ez = t.y - p.y; if (ex * ex + ez * ez < R * R) return true; }
            }
            return false;
        }

        static readonly float[] Nudge = { 0f, 2.5f, -2.5f, 5f, -5f };
        void Place()
        {
            lamps.Clear(); cells.Clear(); trees = TreeRows(); withTrees = trees != null; lastYear = -1;
            int moved = 0, dropped = 0;
            foreach (var run in FilmRoads.Lamps)
            {
                float hw = run.Half; int mode = run.Mode;
                int type = mode == 1 ? 3 : run.Cls == 2 ? 2 : run.Cls == 1 ? 1 : 0;
                float side = hw + Back(run.Cls);
                for (int k = 0; ; k++)
                {
                    float v0 = At(k, run.Step); if (v0 > run.Len - EndClear) break; if (v0 < EndClear) continue;
                    // x across the road (positive = left of the stroke direction), as AlatauRoad's uv.x; both sides of a main road separately
                    int posts = mode == 2 ? 2 : 1;
                    for (int ps = 0; ps < posts; ps++)
                    {
                        float x = mode == 1 ? 0f : mode == 2 ? (ps == 0 ? side : -side) : mode == 3 ? -side : side;
                        float armDir = mode == 1 || mode == 3 || (mode == 2 && ps == 1) ? +1f : -1f;
                        bool done = false;
                        foreach (float dv in Nudge)
                        {
                            float v = v0 + dv; if (v < EndClear || v > run.Len - EndClear) continue;
                            // not in the mouth of a street that joins in the middle of this road
                            bool mouth = false; if (run.Mids != null) foreach (var j in run.Mids) if (Mathf.Abs(v - j.x) < j.y + 1.5f) mouth = true;
                            if (mouth) continue;
                            int seg = 1; while (seg < run.Along.Length - 1 && run.Along[seg] < v) seg++;
                            float a0 = run.Along[seg - 1], a1 = run.Along[seg]; var p0 = run.P[seg - 1]; var p1 = run.P[seg];
                            var c = Vector2.Lerp(p0, p1, a1 > a0 ? (v - a0) / (a1 - a0) : 0f);
                            var d = (p1 - p0); if (d.sqrMagnitude < 1e-6f) continue; d.Normalize();
                            var left = new Vector2(-d.y, d.x);
                            if (NearTree(c + left * x)) continue;
                            Add(c, left, x, armDir, type, run.Years); done = true; if (dv != 0f) moved++; break;
                        }
                        if (!done) dropped++;
                    }
                }
            }
            Debug.Log("[Alatau] film lamps: " + lamps.Count + " street lamps on " + FilmRoads.Lamps.Count + " roads" + (withTrees ? $" ({moved} moved off a tree, {dropped} left out)" : " (street trees not ready yet)"));
        }

        // a post at x across the road; its arm points across the road toward +x (armDir +1) or -x (armDir -1)
        void Add(Vector2 c, Vector2 left, float x, float armDir, int type, Vector4 years)
        {
            var p = c + left * x; var arm = left * armDir;
            float y = CityGround.HeightAt(p.x, p.y) + 0.12f;
            float yaw = Mathf.Atan2(arm.x, arm.y) * Mathf.Rad2Deg;           // local +z = the arm
            lamps.Add(new Lamp { P = new Vector3(p.x, y, p.y), Yaw = yaw, Type = (byte)type, Years = years });
            long k = Key(Mathf.FloorToInt(p.x / Cell), Mathf.FloorToInt(p.y / Cell));
            if (!cells.TryGetValue(k, out var l)) cells[k] = l = new List<int>();
            l.Add(lamps.Count - 1);
        }

        // ------------------------------------------------------------------ the lamp model (metres; base at the origin, arm along +z)
        // vertex colour alpha 1 = the lamp head (glows); uv0 = the centre of the head the vertex belongs to (the head grows into a
        // visible point of light when the camera is far)
        static Mesh MakeLamp(float h, float arm, bool twin, float pole)
        {
            var V = new List<Vector3>(); var N = new List<Vector3>(); var C = new List<Color>(); var U = new List<Vector3>(); var T = new List<int>();
            var metal = new Color(0.30f, 0.31f, 0.33f, 0f);
            // the post: a slim tapered octagon-like box, a base plinth
            Box(V, N, C, U, T, new Vector3(0, 0.25f, 0), new Vector3(pole * 1.8f, 0.5f, pole * 1.8f), metal, Vector3.zero, 0f);
            Box(V, N, C, U, T, new Vector3(0, h * 0.5f, 0), new Vector3(pole, h, pole), metal, Vector3.zero, 0.35f);
            for (int s = 0; s < (twin ? 2 : 1); s++)
            {
                float sg = s == 0 ? 1f : -1f;
                // the arm rises a little toward the road, the head hangs under its end
                var a0 = new Vector3(0, h - 0.35f, 0); var a1 = new Vector3(0, h, sg * arm);
                Beam(V, N, C, U, T, a0, a1, 0.09f, metal);
                var hc = new Vector3(0, h - 0.12f, sg * (arm - 0.15f));
                Box(V, N, C, U, T, hc + new Vector3(0, 0.06f, 0), new Vector3(0.34f, 0.12f, 0.72f), metal, Vector3.zero, 0f);   // housing
                Box(V, N, C, U, T, hc - new Vector3(0, 0.03f, 0), new Vector3(0.28f, 0.05f, 0.60f), new Color(1f, 0.95f, 0.85f, 1f), hc, 0f);  // the lens
            }
            var m = new Mesh { name = "Street lamp " + h };
            m.SetVertices(V); m.SetNormals(N); m.SetColors(C); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateBounds();
            var b = m.bounds; b.Expand(8f); m.bounds = b;                    // the far-away glow grows the head
            return m;
        }
        static void Box(List<Vector3> V, List<Vector3> N, List<Color> C, List<Vector3> U, List<int> T, Vector3 c, Vector3 s, Color col, Vector3 head, float taper)
        {
            var e = s * 0.5f;
            for (int f = 0; f < 6; f++)
            {
                Vector3 n = f == 0 ? Vector3.right : f == 1 ? Vector3.left : f == 2 ? Vector3.up : f == 3 ? Vector3.down : f == 4 ? Vector3.forward : Vector3.back;
                Vector3 u = Mathf.Abs(n.y) > 0.5f ? Vector3.right : Vector3.up, w = Vector3.Cross(n, u);
                int v0 = V.Count;
                for (int i = 0; i < 4; i++)
                {
                    float su = (i == 0 || i == 3) ? -1f : 1f, sw = i < 2 ? -1f : 1f;
                    var p = Vector3.Scale(n + u * su + w * sw, e);
                    if (taper > 0f && p.y > 0f) { p.x *= 1f - taper; p.z *= 1f - taper; }
                    V.Add(c + p); N.Add(n); C.Add(col); U.Add(head);
                }
                // winding: Unity's front face is clockwise, i.e. its cross product points out along n
                if (Vector3.Dot(Vector3.Cross(V[v0 + 1] - V[v0], V[v0 + 2] - V[v0]), n) > 0f) { T.Add(v0); T.Add(v0 + 1); T.Add(v0 + 2); T.Add(v0); T.Add(v0 + 2); T.Add(v0 + 3); }
                else { T.Add(v0); T.Add(v0 + 2); T.Add(v0 + 1); T.Add(v0); T.Add(v0 + 3); T.Add(v0 + 2); }
            }
        }
        static void Beam(List<Vector3> V, List<Vector3> N, List<Color> C, List<Vector3> U, List<int> T, Vector3 a, Vector3 b, float t, Color col)
        {
            // a box along a-b in the y-z plane
            var d = b - a; float L = d.magnitude; var mid = (a + b) * 0.5f; float ang = Mathf.Atan2(d.y, d.z);
            int v0 = V.Count; Box(V, N, C, U, T, Vector3.zero, new Vector3(t, t, L), col, Vector3.zero, 0f);
            var q = Quaternion.AngleAxis(-ang * Mathf.Rad2Deg, Vector3.right);
            for (int i = v0; i < V.Count; i++) { V[i] = mid + q * V[i]; N[i] = q * N[i]; }
        }
    }
}
