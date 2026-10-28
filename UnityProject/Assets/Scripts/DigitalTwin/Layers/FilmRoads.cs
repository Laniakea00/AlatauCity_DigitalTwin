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
            var V = new List<Vector3>(); var U0 = new List<Vector2>(); var U1 = new List<Vector4>(); var U2 = new List<Vector4>(); var T = new List<int>();
            var along = new List<float>(); int meshes = 0; float km = 0;
            void Flush()
            {
                if (V.Count == 0) return;
                var m = new Mesh { name = "Film roads " + meshes, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
                m.SetVertices(V); m.SetUVs(0, U0); m.SetUVs(1, U1); m.SetUVs(2, U2); m.SetTriangles(T, 0); m.RecalculateNormals(); m.RecalculateBounds();
                var go = new GameObject(m.name); go.transform.SetParent(root.transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = m; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off; mr.receiveShadows = true;
                V.Clear(); U0.Clear(); U1.Clear(); U2.Clear(); T.Clear(); meshes++;
            }
            var strokes = Strokes(); drawn = strokes;
            foreach (var st in strokes)
            {
                Dims(st.Cls, out float half, out float walk, out int lanes, out float lift);
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
                var pts = st.P; float len = 0; along.Clear(); along.Add(0);
                for (int i = 1; i < pts.Count; i++) { len += (pts[i] - pts[i - 1]).magnitude; along.Add(len); }
                if (len < 0.5f) continue;
                km += len / 1000f;
                var years = st.Years;
                for (int pass = walk > 0f ? 0 : 1; pass < 2; pass++)
                {
                    float w = pass == 0 ? half + walk : half, up = pass == 0 ? 0.12f : lift; int v0 = V.Count;
                    for (int i = 0; i < pts.Count; i++)
                    {
                        Vector2 d = (pts[Mathf.Min(i + 1, pts.Count - 1)] - pts[Mathf.Max(i - 1, 0)]).normalized, left = new Vector2(-d.y, d.x);
                        for (int sd = -1; sd <= 1; sd++)
                        {
                            Vector2 p = pts[i] + left * (w * sd);
                            V.Add(new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + up, p.y)); U0.Add(new Vector2(w * sd, along[i]));
                            U1.Add(new Vector4(half, pass, len, lanes)); U2.Add(years);
                        }
                        if (i > 0)
                        {
                            int a = v0 + (i - 1) * 3, b = v0 + i * 3;
                            for (int k = 0; k < 2; k++) { T.Add(a + k); T.Add(a + k + 1); T.Add(b + k); T.Add(a + k + 1); T.Add(b + k + 1); T.Add(b + k); }      // facing up
                        }
                    }
                }
                if (V.Count > 180000) Flush();
                if (!st.Ramp)
                {
                    Node(st.A, pts[0], (pts[Mathf.Min(1, pts.Count - 1)] - pts[0]).normalized, st.Cls, half, walk, lift, years);
                    Node(st.B, pts[pts.Count - 1], (pts[Mathf.Max(pts.Count - 2, 0)] - pts[pts.Count - 1]).normalized, st.Cls, half, walk, lift, years);
                }
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
                    V.Add(new Vector3(nd.P.x, CityGround.HeightAt(nd.P.x, nd.P.y) + up, nd.P.y)); U0.Add(new Vector2(0f, 0f)); U1.Add(new Vector4(nd.Half, pass, 0f, 1f)); U2.Add(nd.Years);
                    for (int i = 0; i < N; i++)
                    {
                        float a = i * Mathf.PI * 2f / N; var p = nd.P + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r;
                        V.Add(new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + up, p.y)); U0.Add(new Vector2(r, 0f)); U1.Add(new Vector4(nd.Half, pass, 0f, 1f)); U2.Add(nd.Years);
                        T.Add(c0); T.Add(c0 + 1 + (i + 1) % N); T.Add(c0 + 1 + i);
                    }
                }
                if (V.Count > 180000) Flush();
            }
            Flush();
            Debug.Log($"[Alatau] film roads: {km:0} km in {meshes} meshes");
        }

        class Junction
        {
            public Vector2 P; public int Deg; public float Half, Walk, Lift; public bool Fast, Through; public Vector4 Years = new Vector4(9999, 9999, 9999, 9999);
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
            return res;
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
