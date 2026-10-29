using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Roads of the film look: the road graph of the twin (TwinData.Roads) drawn as ribbons that lie on the terrain, a wide
    /// pavement ribbon under a carriageway ribbon, so at a junction the carriageways cover the pavements. Width and lanes by road class
    /// (assumed typical cross-sections, not survey). Built once, shown only while the film look is on (FilmLook.Apply / Restore).</summary>
    public class FilmRoads : MonoBehaviour
    {
        GameObject root; bool built;

        /// <summary>Cross-section of a road class: half width of the carriageway, pavement width, lanes per direction, height above the ground.</summary>
        public static void Dims(TwinData.RoadClass c, out float half, out float walk, out int lanes, out float lift)
        {
            switch (c)
            {
                case TwinData.RoadClass.Highway: half = 11f; walk = 0f; lanes = 3; lift = 0.36f; break;
                case TwinData.RoadClass.Ring: half = 9f; walk = 0f; lanes = 2; lift = 0.31f; break;
                case TwinData.RoadClass.Main: half = 7.5f; walk = 3.5f; lanes = 2; lift = 0.26f; break;
                default: half = 4f; walk = 2.4f; lanes = 1; lift = 0.21f; break;
            }
        }

        public void Show(bool on)
        {
            if (on && !built && TwinData.Ready) Build();
            if (root != null && root.activeSelf != on) root.SetActive(on);
        }

        void Build()
        {
            built = true; PublishZones();
            var sh = Shader.Find("AlatauCity/Road"); if (sh == null) { Debug.LogWarning("[Alatau] film roads: shader missing"); return; }
            var mat = new Material(sh) { name = "Film roads" };
            root = new GameObject("Film roads");
            var V = new List<Vector3>(); var U0 = new List<Vector4>(); var U1 = new List<Vector4>(); var U2 = new List<Vector4>(); var U3 = new List<Vector4>(); var T = new List<int>();
            var along = new List<float>(); int meshes = 0; float km = 0;
            void Flush()
            {
                if (V.Count == 0) return;
                var m = new Mesh { name = "Film roads " + meshes, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
                m.SetVertices(V); m.SetUVs(0, U0); m.SetUVs(1, U1); m.SetUVs(2, U2); m.SetUVs(3, U3); m.SetTriangles(T, 0); m.RecalculateNormals(); m.RecalculateBounds();
                var go = new GameObject(m.name); go.transform.SetParent(root.transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = m; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off; mr.receiveShadows = true;
                V.Clear(); U0.Clear(); U1.Clear(); U2.Clear(); U3.Clear(); T.Clear(); meshes++;
            }
            var strokes = Strokes(); drawn = strokes; Lamps.Clear();
            // the junctions first: a crossing is set back from the junction's patch, so its size must be known before the arms are drawn
            foreach (var st in strokes)
            {
                if (st.Ramp || st.P == null || st.P.Count < 2) continue;
                StrokeDims(st, out float h0, out float w0, out _, out float l0); var p0 = st.P;
                Node(st.A, p0[0], (p0[Mathf.Min(1, p0.Count - 1)] - p0[0]).normalized, st.Cls, h0, w0, l0, st.Years);
                Node(st.B, p0[p0.Count - 1], (p0[Mathf.Max(p0.Count - 2, 0)] - p0[p0.Count - 1]).normalized, st.Cls, h0, w0, l0, st.Years);
            }
            // T-junctions the plan draws as a street ending on the middle of another road: crossings on the through road on both
            // sides of the side street, and on the side street set back from the through road's kerb
            var mids = MidJunctions(strokes);
            for (int si = 0; si < strokes.Count; si++)
            {
                var st = strokes[si];
                StrokeDims(st, out float half, out float walk, out int lanes, out float lift);
                var pts = st.P; float len = 0; along.Clear(); along.Add(0);
                for (int i = 1; i < pts.Count; i++) { len += (pts[i] - pts[i - 1]).magnitude; along.Add(len); }
                if (len < 0.5f) continue;
                km += len / 1000f;
                var years = st.Years;
                // street lamps (FilmLamps places the posts, AlatauRoad draws their light on the ground by the same rule) and pedestrian
                // crossings with a stop line on the arms of street junctions
                FilmLamps.Rule(st.Cls, st.Ramp, st.OneWay, out float lampStep, out int lampMode, out int lampCls);
                if (lampMode == 3 && TwinOnRight(strokes, si)) lampMode = 6;     // the other carriageway lies at x < 0: the outer kerb is x > 0
                float cA = st.Ramp ? 0f : CrossAt(st.A, st.Cls), cB = st.Ramp ? 0f : CrossAt(st.B, st.Cls);
                if (cA + cB + 2f * CrossW(st.Cls) + 16f > len) { cA = 0f; cB = 0f; }
                var u3 = new Vector4(lampStep, lampMode + 8 * lampCls, cA, cB);
                mids.TryGetValue(si, out var ml);
                if (lampMode > 0) Lamps.Add(new LampRun { P = pts, Along = along.ToArray(), Half = half, Len = len, Step = lampStep, Mode = lampMode, Cls = lampCls, Years = years, Mids = ml });
                // the crossings in the middle of this road (uv0.zw = along of the junction, set back of its crossings): each segment takes
                // the nearest junction; where that changes, the row of vertices is doubled so the value never blends between two
                Vector2 Mid(int seg)
                {
                    if (ml == null || seg < 1 || seg >= pts.Count) return Vector2.zero;
                    float m = (along[seg - 1] + along[seg]) * 0.5f; Vector2 best = Vector2.zero; float bd = float.MaxValue;
                    foreach (var j in ml) { float dd = Mathf.Abs(j.x - m); if (dd < bd) { bd = dd; best = j; } }
                    return best;
                }
                for (int pass = walk > 0f ? 0 : 1; pass < 2; pass++)
                {
                    float w = pass == 0 ? half + walk : half, up = pass == 0 ? 0.12f : lift; int prev = -1;
                    int Row(int i, Vector2 jm)
                    {
                        int r0 = V.Count;
                        Vector2 d = (pts[Mathf.Min(i + 1, pts.Count - 1)] - pts[Mathf.Max(i - 1, 0)]).normalized, left = new Vector2(-d.y, d.x);
                        for (int sd = -1; sd <= 1; sd++)
                        {
                            Vector2 p = pts[i] + left * (w * sd);
                            V.Add(new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + up, p.y)); U0.Add(new Vector4(w * sd, along[i], jm.x, jm.y));
                            U1.Add(new Vector4(half, pass, len, lanes)); U2.Add(years); U3.Add(u3);
                        }
                        return r0;
                    }
                    for (int i = 0; i < pts.Count; i++)
                    {
                        Vector2 jR = Mid(i + 1), jL = i > 0 ? Mid(i) : jR;
                        int b = Row(i, jL);
                        if (prev >= 0)
                            for (int k = 0; k < 2; k++) { T.Add(prev + k); T.Add(prev + k + 1); T.Add(b + k); T.Add(prev + k + 1); T.Add(b + k + 1); T.Add(b + k); }      // facing up
                        prev = jR != jL && i < pts.Count - 1 ? Row(i, jR) : b;
                    }
                }
                if (V.Count > 180000) Flush();
            }
            // junctions: a round patch of plain asphalt (and of pavement under it) where streets meet, so their ends never show and lines
            // never cross inside a junction. A motorway or ring road that runs straight through keeps its markings (ramps just merge).
            foreach (var kv in nodes)
            {
                var nd = kv.Value; if (nd.Deg < 2) continue;
                if (nd.Fast && nd.Through) continue;
                if (nd.Deg == 2 && nd.Through) continue;
                for (int pass = nd.Walk > 0f ? 0 : 1; pass < 2; pass++)
                {
                    float r = pass == 0 ? nd.Half + nd.Walk : nd.Half * 1.02f, up = pass == 0 ? 0.13f : nd.Lift + 0.025f; int c0 = V.Count; const int N = 20;
                    V.Add(new Vector3(nd.P.x, CityGround.HeightAt(nd.P.x, nd.P.y) + up, nd.P.y)); U0.Add(Vector4.zero); U1.Add(new Vector4(nd.Half, pass, 0f, 1f)); U2.Add(nd.Years); U3.Add(new Vector4(0f, 5f, 0f, 0f));
                    for (int i = 0; i < N; i++)
                    {
                        float a = i * Mathf.PI * 2f / N; var p = nd.P + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r;
                        V.Add(new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + up, p.y)); U0.Add(new Vector4(r, 0f, 0f, 0f)); U1.Add(new Vector4(nd.Half, pass, 0f, 1f)); U2.Add(nd.Years); U3.Add(new Vector4(0f, 5f, 0f, 0f));
                        T.Add(c0); T.Add(c0 + 1 + (i + 1) % N); T.Add(c0 + 1 + i);
                    }
                }
                if (V.Count > 180000) Flush();
            }
            Flush();
            Debug.Log($"[Alatau] film roads: {km:0} km in {meshes} meshes");
        }

        /// <summary>Cross-section of one drawn stroke: its class, or a one-lane ramp, or one carriageway of a dual road.</summary>
        static void StrokeDims(Stroke st, out float half, out float walk, out int lanes, out float lift)
        {
            Dims(st.Cls, out half, out walk, out lanes, out lift);
            if (st.Ramp) { half = 4f; walk = 0f; lanes = -1; lift -= 0.05f; }          // a one-lane ramp, under the main carriageway
            else if (st.OneWay)
            {
                // one carriageway of a dual road (the plan draws each direction as its own line, 8–25 m apart): lanes of one direction only
                switch (st.Cls)
                {
                    case TwinData.RoadClass.Highway: half = 6f; lanes = -3; break;
                    case TwinData.RoadClass.Ring: half = 5.5f; lanes = -3; break;
                    case TwinData.RoadClass.Main: half = 3.8f; lanes = -2; break;
                    default: half = 3.2f; lanes = -1; break;
                }
            }
        }

        /// <summary>Where a pedestrian crossing starts on the arm of a street junction, metres from the junction centre (0 = none): a
        /// junction of three or more streets or main roads (never on the motorway or the ring), set back 1 m from the junction's
        /// pavement patch. Width of the crossing: CrossW; the stop line lies 3 m behind it (AlatauRoad draws both).</summary>
        float CrossAt(int node, TwinData.RoadClass cls)
        {
            if (cls == TwinData.RoadClass.Highway || cls == TwinData.RoadClass.Ring) return 0f;
            if (!nodes.TryGetValue(node, out var nd) || nd.Fast) return 0f;
            float r = nd.Deg >= 3 ? nd.Half + nd.Walk + 1f : 0f;
            return Mathf.Max(r, nd.ThroughOff);                              // a street ending on a through road: behind its kerb
        }
        /// <summary>Junction nodes that lie on the middle of another street or main road (not its ends): per through stroke the along
        /// position of each such junction and the set back of its crossings (the side street's half width and pavement + 1 m). Sets
        /// the node's ThroughOff (the through road's half width and pavement + 1 m) for the side street's own crossing.</summary>
        Dictionary<int, List<Vector2>> MidJunctions(List<Stroke> strokes)
        {
            const float SC = 40f; var res = new Dictionary<int, List<Vector2>>();
            var grid = new Dictionary<long, List<(int s, int k)>>(); var alongs = new float[strokes.Count][];
            long Key(int x, int z) => ((long)x << 32) ^ (uint)z;
            for (int s = 0; s < strokes.Count; s++)
            {
                var q = strokes[s]; if (q.P == null || q.P.Count < 2) continue;
                var al = new float[q.P.Count]; for (int k = 1; k < q.P.Count; k++) al[k] = al[k - 1] + (q.P[k] - q.P[k - 1]).magnitude; alongs[s] = al;
                if (q.Ramp || q.Cls == TwinData.RoadClass.Highway || q.Cls == TwinData.RoadClass.Ring) continue;
                for (int k = 1; k < q.P.Count; k++)
                {
                    var m = (q.P[k] + q.P[k - 1]) * 0.5f; long key = Key(Mathf.FloorToInt(m.x / SC), Mathf.FloorToInt(m.y / SC));
                    if (!grid.TryGetValue(key, out var l)) grid[key] = l = new List<(int, int)>(); l.Add((s, k));
                }
            }
            foreach (var kv in nodes)
            {
                var nd = kv.Value; if (nd.Fast) continue;
                int gx = Mathf.FloorToInt(nd.P.x / SC), gz = Mathf.FloorToInt(nd.P.y / SC); int bs = -1; float bd = float.MaxValue, ba = 0f;
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!grid.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (var (s, k) in l)
                    {
                        var q = strokes[s]; if (q.A == kv.Key || q.B == kv.Key) continue;
                        var a = q.P[k - 1]; var ab = q.P[k] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                        float t = Mathf.Clamp01(Vector2.Dot(nd.P - a, ab) / L2); float d = (a + ab * t - nd.P).magnitude;
                        if (d < bd) { bd = d; bs = s; ba = alongs[s][k - 1] + t * Mathf.Sqrt(L2); }
                    }
                }
                if (bs < 0) continue;
                StrokeDims(strokes[bs], out float th, out float tw, out _, out _);
                var alb = alongs[bs]; float len = alb[alb.Length - 1];
                if (bd > th * 0.7f + 1.5f || ba < 12f || ba > len - 12f) continue;
                nd.ThroughOff = Mathf.Max(nd.ThroughOff, th + tw + 1f);
                if (!res.TryGetValue(bs, out var list)) res[bs] = list = new List<Vector2>();
                list.Add(new Vector2(ba, nd.Half + nd.Walk + 1f));
            }
            int n = 0; foreach (var l in res.Values) n += l.Count;
            Debug.Log("[Alatau] film roads: " + n + " T-junctions on through roads get crossings");
            return res;
        }
        /// <summary>For one carriageway of a dual road: whether its twin (the other direction) lies on its right (x &lt; 0 across the
        /// ribbon), judged from a few points along it; then its lamps stand on the left kerb, away from the median.</summary>
        static Dictionary<long, List<int>> twinGrid;
        static bool TwinOnRight(List<Stroke> strokes, int si)
        {
            const float C = 60f; long Key(int x, int z) => ((long)x << 32) ^ (uint)z;
            if (twinGrid == null)
            {
                twinGrid = new Dictionary<long, List<int>>();
                for (int s = 0; s < strokes.Count; s++)
                {
                    var q = strokes[s]; if (!q.OneWay || q.P == null) continue;
                    for (int k = 0; k < q.P.Count; k += 2)
                    {
                        long key = Key(Mathf.FloorToInt(q.P[k].x / C), Mathf.FloorToInt(q.P[k].y / C));
                        if (!twinGrid.TryGetValue(key, out var l)) twinGrid[key] = l = new List<int>();
                        if (l.Count == 0 || l[l.Count - 1] != s) l.Add(s);
                    }
                }
            }
            var st = strokes[si]; var P = st.P; int right = 0, leftN = 0;
            for (int f = 1; f <= 5; f++)
            {
                int i = Mathf.Clamp(P.Count * f / 6, 1, P.Count - 1); var p = P[i]; var d = (P[i] - P[i - 1]).normalized; var lft = new Vector2(-d.y, d.x);
                float bd = 40f; float sideSign = 0f;
                int gx = Mathf.FloorToInt(p.x / C), gz = Mathf.FloorToInt(p.y / C);
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!twinGrid.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (int s in l)
                    {
                        if (s == si || strokes[s].Cls != st.Cls) continue; var q = strokes[s].P;
                        for (int k = 1; k < q.Count; k++)
                        {
                            var a = q[k - 1]; var ab = q[k] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                            if (Mathf.Abs(Vector2.Dot(ab.normalized, d)) < 0.9f) continue;
                            var c = a + ab * Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2); float dist = (c - p).magnitude;
                            if (dist > 3f && dist < bd) { bd = dist; sideSign = Vector2.Dot(c - p, lft); }
                        }
                    }
                }
                if (sideSign < 0f) right++; else if (sideSign > 0f) leftN++;
            }
            return right > leftN;
        }
        /// <summary>Width of a crossing along the road: 5 m on main roads, 4 m on streets (stripes 0.5 m with 0.5 m gaps).</summary>
        public static float CrossW(TwinData.RoadClass cls) => cls == TwinData.RoadClass.Main ? 5f : 4f;

        /// <summary>A drawn road with street lamps: centre line, metres along it at each point, half width of the carriageway, lamp
        /// spacing and placement (FilmLamps.Rule) and the opening years. Filled when the film roads are built.</summary>
        public class LampRun { public List<Vector2> P; public float[] Along; public float Half, Len, Step; public int Mode, Cls; public Vector4 Years; public List<Vector2> Mids; }
        public static readonly List<LampRun> Lamps = new List<LampRun>();

        class Junction
        {
            public Vector2 P; public int Deg; public float Half, Walk, Lift, ThroughOff; public bool Fast, Through; public Vector4 Years = new Vector4(9999, 9999, 9999, 9999);
            public readonly List<(Vector2 dir, TwinData.RoadClass cls)> Arms = new List<(Vector2, TwinData.RoadClass)>();
        }
        readonly Dictionary<int, Junction> nodes = new Dictionary<int, Junction>();
        void Node(int id, Vector2 p, Vector2 dir, TwinData.RoadClass cls, float half, float walk, float lift, Vector4 years)
        {
            if (!nodes.TryGetValue(id, out var n)) { n = new Junction { P = p }; nodes[id] = n; }
            n.Deg++; n.Half = Mathf.Max(n.Half, half); n.Walk = Mathf.Max(n.Walk, walk); n.Lift = Mathf.Max(n.Lift, lift);
            n.Years = Vector4.Min(n.Years, years);                         // the junction is there as soon as its first road is
            if (cls == TwinData.RoadClass.Highway || cls == TwinData.RoadClass.Ring) n.Fast = true;
            // the widest road passes straight through (two arms of the widest class almost opposite): no patch over its markings
            foreach (var a in n.Arms) if (a.cls == cls && Vector2.Dot(a.dir, dir) < -0.94f && half >= n.Half - 0.01f) n.Through = true;
            n.Arms.Add((dir, cls));
        }

        // ---------------------------------------------------------------- strokes: the road graph as long, smooth lines
        class Stroke { public List<Vector2> P; public TwinData.RoadClass Cls; public Vector4 Years; public int A, B; public float Len; public bool Ramp, OneWay, Fixed; }
        static List<Stroke> drawn; static Dictionary<int, List<int>> drawnAt;

        /// <summary>A road as the film look draws it, for what is placed on the roads (traffic, street lamps): centre line, class, opening
        /// year per scenario (x..w = scenario 0..3), whether it is a ramp or one carriageway of a dual road (then it runs in point order),
        /// its end nodes in TwinData.RoadNodes and its length in metres. Cross-section: Dims. No ways until the film roads are built.</summary>
        public struct Way { public IReadOnlyList<Vector2> P; public TwinData.RoadClass Cls; public Vector4 Years; public bool Ramp, OneWay; public int A, B; public float Len; }
        public static int WayCount => drawn != null ? drawn.Count : 0;
        public static Way GetWay(int i) { var q = drawn[i]; return new Way { P = q.P, Cls = q.Cls, Years = q.Years, Ramp = q.Ramp, OneWay = q.OneWay, A = q.A, B = q.B, Len = q.Len }; }

        /// <summary>The road as it is drawn nearest to p (open in 'year' of scenario 'sc', no ramps), continued at each junction by the
        /// straightest drawn road (turning less than ~55°) until 'reach' metres are added on each side: its centre line, class and
        /// whether it is one carriageway of a dual road (one direction). False until the film roads are built.</summary>
        public static bool DrawnWay(Vector2 p, int year, int sc, float maxD, float reach, out List<Vector2> line, out TwinData.RoadClass cls, out bool oneWay)
        {
            line = null; cls = TwinData.RoadClass.Street; oneWay = false;
            var st = drawn; if (st == null || st.Count == 0) return false;
            bool Open(Stroke q) => !q.Ramp && q.P != null && q.P.Count >= 2 && q.Years[Mathf.Clamp(sc, 0, 3)] <= year;
            int bi = -1; float bd = maxD * maxD;
            for (int i = 0; i < st.Count; i++)
            {
                var q = st[i]; if (!Open(q)) continue;
                for (int j = 0; j + 1 < q.P.Count; j++)
                {
                    var a = q.P[j]; var ab = q.P[j + 1] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-4f) continue;
                    float d = (a + ab * Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2) - p).sqrMagnitude; if (d < bd) { bd = d; bi = i; }
                }
            }
            if (bi < 0) return false;
            if (drawnAt == null)
            {
                drawnAt = new Dictionary<int, List<int>>();
                for (int i = 0; i < st.Count; i++) foreach (int nd in new[] { st[i].A, st[i].B }) { if (nd < 0) continue; if (!drawnAt.TryGetValue(nd, out var l)) drawnAt[nd] = l = new List<int>(); l.Add(i); }
            }
            var nodes = TwinData.RoadNodes;
            int NodeAt(Stroke q, Vector2 end)
            {
                int best = -1; float b2 = 30f * 30f;
                foreach (int nd in new[] { q.A, q.B }) if (nd >= 0 && nd < nodes.Length) { float d = (nodes[nd] - end).sqrMagnitude; if (d < b2) { b2 = d; best = nd; } }
                return best;
            }
            var pts = new List<Vector2>(st[bi].P); cls = st[bi].Cls; oneWay = st[bi].OneWay;
            for (int pass = 0; pass < 2; pass++)
            {
                if (pass == 1) pts.Reverse();
                int cur = bi; float len = 0f;
                for (int guard = 0; guard < 40 && len < reach; guard++)
                {
                    var end = pts[pts.Count - 1]; var dir = (end - pts[pts.Count - 2]).normalized;
                    int node = NodeAt(st[cur], end); if (node < 0 || !drawnAt.TryGetValue(node, out var list)) break;
                    int nb = -1; float bestDot = 0.58f; bool flip = false;
                    foreach (int k in list)
                    {
                        if (k == cur) continue; var q = st[k]; if (!Open(q) || q.OneWay != oneWay) continue;
                        bool fw = (q.P[0] - end).sqrMagnitude <= (q.P[q.P.Count - 1] - end).sqrMagnitude;
                        var a = fw ? q.P[0] : q.P[q.P.Count - 1]; var b = fw ? q.P[Mathf.Min(2, q.P.Count - 1)] : q.P[Mathf.Max(q.P.Count - 3, 0)];
                        float dot = Vector2.Dot(dir, (b - a).normalized) + (q.Cls == cls ? 0.12f : 0f);
                        if (dot > bestDot) { bestDot = dot; nb = k; flip = !fw; }
                    }
                    if (nb < 0) break;
                    var np = st[nb].P; int n = np.Count;
                    for (int i = 1; i < n; i++) { var v = flip ? np[n - 1 - i] : np[i]; len += Vector2.Distance(pts[pts.Count - 1], v); pts.Add(v); }
                    cur = nb;
                }
            }
            pts.Reverse();                                                       // back in the stroke's own order (a one-way carriageway runs that way)
            line = pts; return true;
        }

        /// <summary>Edges of one class and one opening year that meet at a node of degree 2 are one road: chained into a stroke, resampled
        /// every 8 m and smoothed (a few binomial passes, ends fixed), so the ribbon has no kinks from the vectorised plan and corners of
        /// streets get a kerb radius. Short, curving motorway strokes are ramps (cloverleaf loops, slips) and get a one-lane width.</summary>
        static List<Stroke> Strokes()
        {
            var film = FilmStrokes(); if (film != null) return film;
            var R = TwinData.Roads; int n = R.Length;
            var adj = new Dictionary<int, List<int>>();
            for (int i = 0; i < n; i++)
            {
                if (R[i].Geom == null || R[i].Geom.Length < 2) continue;
                if (!adj.TryGetValue(R[i].A, out var la)) adj[R[i].A] = la = new List<int>(); la.Add(i);
                if (!adj.TryGetValue(R[i].B, out var lb)) adj[R[i].B] = lb = new List<int>(); lb.Add(i);
            }
            int Deg(int node) => adj.TryGetValue(node, out var l) ? l.Count : 0;
            bool Same(int a, int b) => R[a].Cls == R[b].Cls && Y(R[a], 0) == Y(R[b], 0) && Y(R[a], 1) == Y(R[b], 1) && Y(R[a], 2) == Y(R[b], 2) && Y(R[a], 3) == Y(R[b], 3);
            // direction of edge i leaving the node
            Vector2 Out(int i, int node)
            {
                var g = R[i].Geom; Vector2 v = R[i].A == node ? g[1] - g[0] : g[g.Length - 2] - g[g.Length - 1];
                return v.sqrMagnitude > 1e-8f ? v.normalized : v;
            }
            var used = new bool[n]; var res = new List<Stroke>();
            // interchanges (Tools/build_interchanges.py): the plan's scribbled ramps are dropped, clean standard ramps are added
            var ic = LoadInterchanges();
            if (ic != null && ic.edges != null) foreach (var k in ic.edges) if (k >= 0 && k < n) used[k] = true;
            // good continuation: at every node the road goes on along the edge of the same class and year that is most nearly straight
            // ahead (within 30°), so a motorway runs straight through an interchange and its ramps become separate strokes
            int Next(int cur, int node)
            {
                if (!adj.TryGetValue(node, out var l)) return -1;
                Vector2 din = -Out(cur, node); int best = -1; float bd = Mathf.Cos(30f * Mathf.Deg2Rad);
                foreach (var j in l)
                {
                    if (used[j] || !Same(cur, j)) continue;
                    // short pieces of a roundabout turn by 45–60° at each node: they still belong to one ring
                    float lim = R[cur].Len < 90f && R[j].Len < 90f ? 0.42f : bd;
                    float d = Vector2.Dot(din, Out(j, node)); if (d > lim && (best < 0 || d > Vector2.Dot(din, Out(best, node)))) best = j;
                }
                return best;
            }
            for (int i = 0; i < n; i++)
            {
                if (used[i] || R[i].Geom == null || R[i].Geom.Length < 2) continue;
                used[i] = true;
                var pts = new List<Vector2>(R[i].Geom);
                int head = R[i].A, tail = R[i].B, eh = i, et = i;
                for (int side = 0; side < 2; side++)
                {
                    int guard = 0;
                    while (guard++ < 100000)
                    {
                        int node = side == 0 ? tail : head;
                        int cur = Next(side == 0 ? et : eh, node); if (cur < 0) break;
                        used[cur] = true; var g = R[cur].Geom; bool fwd = R[cur].A == node;
                        if (side == 0)
                        {
                            if (fwd) for (int k = 1; k < g.Length; k++) pts.Add(g[k]); else for (int k = g.Length - 2; k >= 0; k--) pts.Add(g[k]);
                            tail = fwd ? R[cur].B : R[cur].A; et = cur;
                        }
                        else
                        {
                            var pre = new List<Vector2>();
                            if (fwd) for (int k = g.Length - 1; k >= 1; k--) pre.Add(g[k]); else for (int k = 0; k < g.Length - 1; k++) pre.Add(g[k]);
                            pts.InsertRange(0, pre); head = fwd ? R[cur].B : R[cur].A; eh = cur;
                        }
                        if (head == tail) break;
                    }
                }
                if (head == tail && pts.Count > 4)
                {
                    // a small closed ring (a roundabout drawn as a polygon by the plan): a true circle through the same centre
                    Vector2 cc = Vector2.zero; foreach (var q in pts) cc += q; cc /= pts.Count;
                    float rr = 0; foreach (var q in pts) rr += (q - cc).magnitude; rr /= pts.Count;
                    if (rr < 110f)
                    {
                        int nseg = Mathf.Max(16, Mathf.CeilToInt(2f * Mathf.PI * rr / 8f));
                        float a0 = Mathf.Atan2(pts[0].y - cc.y, pts[0].x - cc.x); pts.Clear();
                        for (int k = 0; k <= nseg; k++) { float a = a0 + k * Mathf.PI * 2f / nseg; pts.Add(cc + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * rr); }
                    }
                }
                var rs = Resample(pts, 8f); if (rs.Count < 2) continue;
                float L = 0; for (int k = 1; k < rs.Count; k++) L += (rs[k] - rs[k - 1]).magnitude;
                var st = new Stroke { Cls = R[i].Cls, Years = new Vector4(Y(R[i], 0), Y(R[i], 1), Y(R[i], 2), Y(R[i], 3)), A = head, B = tail, P = rs, Len = L };
                bool fast = st.Cls == TwinData.RoadClass.Highway || st.Cls == TwinData.RoadClass.Ring;
                // stubs of the vectorised plan: a short dead end, or a short motorway piece that meets nothing straight at either end
                if (L < 30f && (Deg(head) == 1 || Deg(tail) == 1)) continue;
                if (fast && L < 35f)
                {
                    bool Aligned(int node, Vector2 d) { foreach (var j in adj[node]) if (j != eh && j != et && Mathf.Abs(Vector2.Dot(Out(j, node), d)) > 0.7f) return true; return false; }
                    Vector2 dd = (rs[rs.Count - 1] - rs[0]).normalized;
                    if (!Aligned(head, dd) && !Aligned(tail, dd)) continue;
                }
                res.Add(st);
            }
            if (ic != null && ic.paths != null)
                foreach (var pth in ic.paths)
                {
                    if (pth.g == null || pth.g.Length < 4) continue;
                    var pts = new List<Vector2>(); for (int i = 0; i + 1 < pth.g.Length; i += 2) pts.Add(new Vector2(pth.g[i], pth.g[i + 1]));
                    var rs = Smooth(Resample(pts, 8f), 2); float Lr = 0; for (int i = 1; i < rs.Count; i++) Lr += (rs[i] - rs[i - 1]).magnitude;
                    var yv = pth.y != null && pth.y.Length >= 4 ? new Vector4(pth.y[0], pth.y[1], pth.y[2], pth.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                    res.Add(new Stroke { Cls = TwinData.RoadClass.Highway, Years = yv, A = -1, B = -1, P = rs, Len = Lr, Ramp = true, Fixed = true });
                }
            // a parallel twin 3–30 m away (same class, another stroke) along most of the length: one carriageway of a dual road
            const float C = 60f; var grid = new Dictionary<long, List<(int s, Vector2 m, Vector2 d)>>();
            long Key(Vector2 p) => ((long)Mathf.FloorToInt(p.x / C) << 32) ^ (uint)Mathf.FloorToInt(p.y / C);
            for (int k = 0; k < res.Count; k++)
            {
                var p = res[k].P;
                for (int i = 1; i < p.Count; i++)
                {
                    Vector2 m = (p[i] + p[i - 1]) * 0.5f, d = (p[i] - p[i - 1]); if (d.sqrMagnitude < 1f) continue; d.Normalize();
                    long key = Key(m); if (!grid.TryGetValue(key, out var l)) grid[key] = l = new List<(int, Vector2, Vector2)>(); l.Add((k, m, d));
                }
            }
            for (int k = 0; k < res.Count; k++)
            {
                var st = res[k]; var p = st.P; int tw = 0, cnt = 0; float maxD = st.Cls == TwinData.RoadClass.Highway ? 30f : 22f;
                if (st.Fixed) continue;
                for (int i = 1; i < p.Count; i += 2)
                {
                    Vector2 m = (p[i] + p[i - 1]) * 0.5f, d = (p[i] - p[i - 1]); if (d.sqrMagnitude < 1f) continue; d.Normalize(); cnt++;
                    bool hit = false;
                    for (int gx = -1; gx <= 1 && !hit; gx++) for (int gz = -1; gz <= 1 && !hit; gz++)
                    {
                        if (!grid.TryGetValue(Key(m + new Vector2(gx * C, gz * C)), out var l)) continue;
                        foreach (var q in l)
                        {
                            if (q.s == k || res[q.s].Cls != st.Cls || Mathf.Abs(Vector2.Dot(q.d, d)) < 0.96f) continue;
                            Vector2 v = q.m - m; float perp = Mathf.Abs(v.x * d.y - v.y * d.x), par = Mathf.Abs(Vector2.Dot(v, d));
                            if (perp > 3f && perp < maxD && par < 12f) { hit = true; break; }
                        }
                    }
                    if (hit) tw++;
                }
                st.OneWay = cnt > 0 && tw > cnt * 0.5f;
                // how sharply it turns: degrees per metre over the whole stroke
                var sm0 = Smooth(p, 3); float turn = 0;
                for (int i = 1; i < sm0.Count - 1; i++) turn += Mathf.Abs(Vector2.SignedAngle(sm0[i] - sm0[i - 1], sm0[i + 1] - sm0[i]));
                bool fast = st.Cls == TwinData.RoadClass.Highway || st.Cls == TwinData.RoadClass.Ring;
                st.Ramp = fast && ((st.Len < 2500f && turn > 35f && turn / Mathf.Max(st.Len, 1f) > 0.03f) || (st.Len < 600f && !st.OneWay));
                int passes = st.Ramp ? 6 : fast ? 10 : st.Cls == TwinData.RoadClass.Main ? 6 : 3;
                st.P = Smooth(p, passes);
            }
            return res;
        }
        // ---------------------------------------------------------------- clean geometry (Tools/build_film_roads.py)
        // Motorways as one smooth dual carriageway per corridor, the nine interchanges as standard cloverleafs, the plan's doubled
        // lines, ramp scribbles and U-turn hairpins removed. k: 0 two-way road, 1 one carriageway of a dual road, 2 ramp.
        [System.Serializable] class FrStroke { public string c; public int k, a, b; public int[] y; public float[] g; }
        [System.Serializable] class FrData { public FrStroke[] s; public int[] drop; }
        static FrData frCache; static bool frTried; static HashSet<int> frDrop;
        static FrData LoadFilm()
        {
            if (frTried) return frCache; frTried = true;
            var ta = Resources.Load<TextAsset>("Landmarks/film_roads"); if (ta == null) return null;
            try { frCache = JsonUtility.FromJson<FrData>(ta.text); } catch (System.Exception e) { Debug.LogWarning("[Alatau] film roads: " + e.Message); frCache = null; }
            if (frCache != null && (frCache.s == null || frCache.s.Length == 0)) frCache = null;
            if (frCache != null) frDrop = new HashSet<int>(frCache.drop ?? new int[0]);
            return frCache;
        }
        /// <summary>A plan edge that the clean geometry no longer draws (a motorway piece or a ramp scribble): no street trees along it.</summary>
        public static bool Dropped(int edge) { LoadFilm(); return frDrop != null && frDrop.Contains(edge); }
        /// <summary>Motorway carriageways and interchange ramps of the clean geometry with their half widths (empty without it).</summary>
        public static IEnumerable<(List<Vector2> P, float half)> CleanLines()
        {
            var fr = LoadFilm(); if (fr == null) yield break;
            foreach (var f in fr.s)
            {
                if (f.g == null || f.g.Length < 4 || (f.c != "highway" && f.c != "ring" && f.k != 2)) continue;
                var pts = new List<Vector2>(f.g.Length / 2); for (int i = 0; i + 1 < f.g.Length; i += 2) pts.Add(new Vector2(f.g[i], f.g[i + 1]));
                yield return (pts, f.k == 2 ? 4f : 6f);
            }
        }
        static List<Stroke> FilmStrokes()
        {
            var fr = LoadFilm(); if (fr == null) return null;
            var res = new List<Stroke>(fr.s.Length);
            foreach (var f in fr.s)
            {
                if (f.g == null || f.g.Length < 4) continue;
                var pts = new List<Vector2>(f.g.Length / 2); for (int i = 0; i + 1 < f.g.Length; i += 2) pts.Add(new Vector2(f.g[i], f.g[i + 1]));
                var cls = f.c == "highway" ? TwinData.RoadClass.Highway : f.c == "ring" ? TwinData.RoadClass.Ring : f.c == "main" ? TwinData.RoadClass.Main : TwinData.RoadClass.Street;
                var yv = f.y != null && f.y.Length >= 4 ? new Vector4(f.y[0], f.y[1], f.y[2], f.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                float L = 0; for (int i = 1; i < pts.Count; i++) L += (pts[i] - pts[i - 1]).magnitude;
                // junction ids: plan nodes; strokes cut by the cleaning have -1 and get a private id (no patch)
                res.Add(new Stroke { Cls = cls, Years = yv, A = f.a >= 0 ? f.a : -1000000 - res.Count * 2, B = f.b >= 0 ? f.b : -1000001 - res.Count * 2,
                    P = pts, Len = L, Ramp = f.k == 2, OneWay = f.k == 1, Fixed = true });
            }
            DropStubs(res);
            return res;
        }

        /// <summary>Stubs of the vectorised plan: a short piece (under 80 m, not a ramp) with an end that touches no other road within 16 m
        /// ends in a field. Such pieces are not drawn (the survey found ≈55 of them, mostly streets).</summary>
        static void DropStubs(List<Stroke> res)
        {
            const float Cell = 32f, Near = 16f;
            var grid = new Dictionary<long, List<int>>();
            long Key(int gx, int gz) => ((long)gx << 32) ^ (uint)gz;
            for (int k = 0; k < res.Count; k++)
                foreach (var p in res[k].P)
                {
                    long key = Key(Mathf.FloorToInt(p.x / Cell), Mathf.FloorToInt(p.y / Cell));
                    if (!grid.TryGetValue(key, out var l)) grid[key] = l = new List<int>();
                    if (l.Count == 0 || l[l.Count - 1] != k) l.Add(k);
                }
            bool Touches(int self, Vector2 e)
            {
                int gx = Mathf.FloorToInt(e.x / Cell), gz = Mathf.FloorToInt(e.y / Cell);
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!grid.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (int j in l)
                    {
                        if (j == self) continue; var q = res[j].P;
                        for (int i = 0; i + 1 < q.Count; i++)
                        {
                            var a = q[i]; var ab = q[i + 1] - a; float L2 = ab.sqrMagnitude;
                            var c = L2 < 1e-6f ? a : a + ab * Mathf.Clamp01(Vector2.Dot(e - a, ab) / L2);
                            if ((c - e).sqrMagnitude < Near * Near) return true;
                        }
                    }
                }
                return false;
            }
            var drop = new List<int>();
            for (int k = 0; k < res.Count; k++)
            {
                var s = res[k]; if (s.Ramp || s.Len >= 80f || s.P.Count < 2) continue;
                if (!Touches(k, s.P[0]) || !Touches(k, s.P[s.P.Count - 1])) drop.Add(k);
            }
            for (int i = drop.Count - 1; i >= 0; i--) res.RemoveAt(drop[i]);
            if (drop.Count > 0) Debug.Log("[Alatau] film roads: " + drop.Count + " dead-end stubs of the plan not drawn");
        }

        [System.Serializable] class IcPath { public int[] y; public float[] g; }
        [System.Serializable] class IcData { public int[] edges; public IcPath[] paths; }
        static IcData icCache;
        static IcData LoadInterchanges()
        {
            if (icCache != null) return icCache;
            var ta = Resources.Load<TextAsset>("Landmarks/interchanges"); if (ta == null) return null;
            try { icCache = JsonUtility.FromJson<IcData>(ta.text); } catch (System.Exception e) { Debug.LogWarning("[Alatau] interchanges: " + e.Message); }
            return icCache;
        }
        static Vector4[] icZones; static int icCount = -1;
        /// <summary>Inside a motorway interchange: the land between the ramps is a verge with a few trees, not a park or yards.</summary>
        public static bool InInterchange(float x, float z)
        {
            if (icCount < 0) PublishZones();
            for (int i = 0; i < icCount; i++) { var c = icZones[i]; float dx = x - c.x, dz = z - c.y; if (dx * dx + dz * dz < c.z * c.z) return true; }
            return false;
        }
        /// <summary>Interchange zones (x, z, radius): the ground inside is a mown verge, not city yards (AlatauGround reads _AlatauIcZones).</summary>
        public static void PublishZones()
        {
            var ta = Resources.Load<TextAsset>("Landmarks/film_roads"); if (ta == null) ta = Resources.Load<TextAsset>("Landmarks/interchanges");
            var v = new Vector4[32]; int n = 0;
            if (ta != null)
            {
                // "zones":[[x,z,r,y],...] — JsonUtility cannot read nested arrays, so a tiny parse
                int i0 = ta.text.IndexOf("\"zones\":[");
                if (i0 >= 0)
                {
                    int i = i0 + 9;
                    while (n < 32)
                    {
                        int a = ta.text.IndexOf('[', i); if (a < 0) break; int b = ta.text.IndexOf(']', a); if (b < 0) break;
                        var parts = ta.text.Substring(a + 1, b - a - 1).Split(',');
                        if (parts.Length >= 3 && float.TryParse(parts[0], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float x)
                            && float.TryParse(parts[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float z)
                            && float.TryParse(parts[2], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float r))
                            v[n++] = new Vector4(x, z, r, parts.Length > 3 && float.TryParse(parts[3], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float y) ? y : 2025f);
                        i = b + 1; if (i < ta.text.Length && ta.text[i] == ']') break;
                        if (i + 1 < ta.text.Length && ta.text[i] == ',' && ta.text[i + 1] != '[') break;
                    }
                }
            }
            Shader.SetGlobalVectorArray("_AlatauIcZones", v); Shader.SetGlobalFloat("_AlatauIcCount", n);
            icZones = v; icCount = n;
        }

        static List<Vector2> Resample(List<Vector2> p, float step)
        {
            var o = new List<Vector2> { p[0] }; float acc = 0;
            for (int i = 1; i < p.Count; i++)
            {
                Vector2 a = p[i - 1], b = p[i]; float d = (b - a).magnitude; if (d < 1e-4f) continue;
                float t = step - acc;
                while (t <= d) { o.Add(Vector2.Lerp(a, b, t / d)); t += step; }
                acc = d - (t - step);
            }
            if ((o[o.Count - 1] - p[p.Count - 1]).magnitude > 0.5f) o.Add(p[p.Count - 1]); else o[o.Count - 1] = p[p.Count - 1];
            return o;
        }
        static List<Vector2> Smooth(List<Vector2> p, int passes)
        {
            var a = new List<Vector2>(p); var b = new List<Vector2>(p);
            for (int k = 0; k < passes; k++)
            {
                for (int i = 1; i < a.Count - 1; i++) b[i] = (a[i - 1] + 2f * a[i] + a[i + 1]) * 0.25f;
                var t = a; a = b; b = t; b[0] = a[0]; b[b.Count - 1] = a[a.Count - 1];
            }
            return a;
        }

        static float Y(TwinData.RoadEdge e, int s) => e.Year != null && e.Year.Length > 0 ? e.Year[Mathf.Min(s, e.Year.Length - 1)] : 2025;
    }
}
