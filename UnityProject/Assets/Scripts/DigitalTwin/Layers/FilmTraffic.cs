using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Moving traffic of the film look: cars, SUVs, minibuses, city buses and trucks driving along the film roads
    /// (FilmRoads.GetWay) in their lanes, right-hand traffic, on to a connected road at each junction. Only roads open in the year
    /// and scenario shown carry traffic; none crosses a landmark plot or the Gate district once it stands. How many cars there are
    /// follows the traffic model of the twin (car trips of the year, TwinData.TrafficKpi) and the hour of the film look (rush at
    /// 8–9 and 18–19, quiet at night). Lights glow from dusk on. Cars live only around what the camera looks at: they are drawn in
    /// instanced batches (AlatauCity/Car), and none at all while the camera is far up or the film look is off.
    /// Windows / editor / film: up to 7000 cars within ≈3.5 km; WebGL: up to 800 within ≈1.2 km. Two levels of detail: the cars within
    /// 110 m of the camera (at most 320; WebGL 70 m, 40) get the fine mesh (rounded body, arches, glasshouse, round wheels), the rest the light one.</summary>
    public class FilmTraffic : MonoBehaviour
    {
        public static FilmTraffic Instance;
        /// <summary>Traffic shown at all (with the film look).</summary>
        public static bool On = true;
        /// <summary>Cars alive and drawn last frame (for diagnostics).</summary>
        public static int Alive, Drawn;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Film traffic").AddComponent<FilmTraffic>(); }
        void Awake() { Instance = this; }
        /// <summary>Traffic on (1) or off (0), for the capture tools and frame-rate checks.</summary>
        public static void SetOn(int on) { On = on != 0; }

        // ------------------------------------------------------------------ vehicles
        const int Sedan = 0, Suv = 1, Van = 2, Bus = 3, Truck = 4, Kinds = 5;
        static readonly float[] KLen = { 4.5f, 4.6f, 5.6f, 12f, 9.5f };
        static readonly Color[] CarPal = { C("#e9e9e7"), C("#e2e3e1"), C("#b9bcbf"), C("#a9adb1"), C("#202225"), C("#2a2c30"), C("#6d7278"), C("#55595e"),
                                          C("#24385a"), C("#8e2420"), C("#cbbfa6"), C("#2f4a3c"), C("#5a4536"), C("#7f97ad") };
        static readonly float[] CarPalW = { 0.15f, 0.11f, 0.10f, 0.08f, 0.10f, 0.07f, 0.08f, 0.06f, 0.07f, 0.05f, 0.04f, 0.03f, 0.03f, 0.03f };
        static readonly Color[] VanPal = { C("#efefec"), C("#e6e7e5"), C("#b9bcbf"), C("#d9c99a"), C("#6d7278") };
        static readonly Color[] BusPal = { C("#1d8a63"), C("#1f6fae"), C("#1d8a63") };
        static readonly Color[] TruckPal = { C("#eeeeec"), C("#2d5c9a"), C("#a52a22"), C("#d7d8d6"), C("#3d4045") };
        static Color C(string hex) { ColorUtility.TryParseHtmlString(hex, out var c); return c; }

        Mesh[] meshes; Material mat; bool high;
        /// <summary>Cars nearer than fineR to the camera get the fine mesh: up to 110 m and 320 cars on Windows, 70 m and 40 cars on
        /// WebGL. When more than fineMax are that near, the radius shrinks from frame to frame, so the nearest ones keep it.</summary>
        float fineDist, fineR; int fineMax;
        /// <summary>Fine meshes near the camera on (1) or off (0), for frame-rate checks.</summary>
        public static bool FineOn = true;
        public static void SetFine(int on) { FineOn = on != 0; }
        int pool;
        struct Car
        {
            public int lane, next, leader, kind, k; public float s, v, vMax, wait, scale, life; public bool dying, alive, brake;
            public Vector3 carry; public Color col;
        }
        Car[] cars;

        // ------------------------------------------------------------------ roads (static part, built once from FilmRoads)
        class WayD
        {
            public Vector2[] P, R, T; public float[] Cum, YC, YL, YR; public bool[] Plot, Gate; public float Half; public int Lanes; public bool OneWay, GateRoad;
            public TwinData.RoadClass Cls; public Vector4 Years; public float Len, Speed, Weight, Lift; public int A, B;
        }
        WayD[] ways;
        class Lane
        {
            public int W; public bool Rev; public int I0, I1; public float Off, Len; public int Idx, Count;
            public Vector2 SP, EP, SD, ED; public bool EndJ; public int Tail = -1, Reverse = -1;
            public List<int> Next = new List<int>(); public List<float> Turn = new List<float>();
        }
        readonly List<Lane> lanes = new List<Lane>();
        // lane samples on a grid, for placing cars near the camera
        struct Sample { public int Lane; public float S, W; public Vector2 P; }
        readonly List<Sample> samples = new List<Sample>();
        readonly Dictionary<long, List<int>> grid = new Dictionary<long, List<int>>();
        const float Cell = 250f;
        static long Key(int gx, int gz) => ((long)gx << 32) ^ (uint)gz;

        int builtYear = -1, builtSc = -1; bool builtGate; bool staticBuilt;
        // region round the camera's focus
        Vector2 focus = new Vector2(1e9f, 1e9f); float radius = 1000f, regionWeight; bool regionValid;
        readonly List<int> cand = new List<int>(); float[] candCum = new float[1024];
        float camDist = 1e9f; Vector3 camPos; Camera cam; Plane[] frustum = new Plane[6];

        // draw batches: per kind, batches of 1023
        Matrix4x4[][][] mats; Vector4[][][] cols; int[][] counts; MaterialPropertyBlock[][] mpbs;
        static readonly int ColId = Shader.PropertyToID("_CarColor");
        int drawFrame = -1;

        void Start()
        {
            high = Application.platform != RuntimePlatform.WebGLPlayer;
            pool = high ? 7000 : 800;
            cars = new Car[pool];
            var sh = Shader.Find("AlatauCity/Car");
            if (sh == null) { Debug.LogWarning("[Alatau] film traffic: shader AlatauCity/Car missing"); enabled = false; return; }
            mat = new Material(sh) { name = "Film traffic", enableInstancing = true };
            // two levels of detail: [0, Kinds) the light mesh, [Kinds, 2·Kinds) the fine one for the cars near the camera
            meshes = new Mesh[Kinds * 2];
            for (int k = 0; k < Kinds; k++) { meshes[k] = VehicleMesh(k); meshes[Kinds + k] = FineMesh(k); }
            fineMax = high ? 320 : 40; fineDist = high ? 110f : 70f; fineR = fineDist;
            int nb = (pool + 1022) / 1023 + 1;
            mats = new Matrix4x4[Kinds * 2][][]; cols = new Vector4[Kinds * 2][][]; counts = new int[Kinds * 2][]; mpbs = new MaterialPropertyBlock[Kinds * 2][];
            for (int k = 0; k < Kinds * 2; k++)
            {
                int n = k >= Kinds ? 1 : k == Sedan || k == Suv ? nb : Mathf.Max(1, nb / 2);
                mats[k] = new Matrix4x4[n][]; cols[k] = new Vector4[n][]; counts[k] = new int[n]; mpbs[k] = new MaterialPropertyBlock[n];
                for (int b = 0; b < n; b++) { mats[k][b] = new Matrix4x4[1023]; cols[k][b] = new Vector4[1023]; mpbs[k][b] = new MaterialPropertyBlock(); }
            }
            Camera.onPreCull += PreCull;
        }
        void OnDestroy() { Camera.onPreCull -= PreCull; }

        // ------------------------------------------------------------------ building the lanes
        void BuildStatic()
        {
            int n = FilmRoads.WayCount; ways = new WayD[n];
            var ls = Landmarks.LandmarkSystem.Instance;
            for (int i = 0; i < n; i++)
            {
                var w = FilmRoads.GetWay(i);
                if (w.Ramp || w.P == null || w.P.Count < 2) continue;
                FilmRoads.Dims(w.Cls, out float half, out _, out int lanesN, out float lift);
                if (w.OneWay)
                    switch (w.Cls)
                    {
                        case TwinData.RoadClass.Highway: half = 6f; lanesN = 3; break;
                        case TwinData.RoadClass.Ring: half = 5.5f; lanesN = 3; break;
                        case TwinData.RoadClass.Main: half = 3.8f; lanesN = 2; break;
                        default: half = 3.2f; lanesN = 1; break;
                    }
                int m = w.P.Count; var d = new WayD { P = new Vector2[m], R = new Vector2[m], T = new Vector2[m], Cum = new float[m], YC = new float[m], YL = new float[m], YR = new float[m],
                    Plot = new bool[m], Gate = new bool[m], Half = half, Lanes = lanesN, OneWay = w.OneWay, Cls = w.Cls, Years = w.Years, A = w.A, B = w.B };
                for (int j = 0; j < m; j++) d.P[j] = w.P[j];
                d.Lift = lift; ways[i] = d;
            }
            OrientOneWays();
            for (int i = 0; i < n; i++)
            {
                var d = ways[i]; if (d == null) continue;
                int m = d.P.Length; float half = d.Half, lift = d.Lift;
                for (int j = 0; j < m; j++)
                {
                    Vector2 t = (d.P[Mathf.Min(j + 1, m - 1)] - d.P[Mathf.Max(j - 1, 0)]); t = t.sqrMagnitude > 1e-6f ? t.normalized : Vector2.up;
                    d.T[j] = t; d.R[j] = new Vector2(t.y, -t.x);                    // right of the point order
                    if (j > 0) d.Cum[j] = d.Cum[j - 1] + (d.P[j] - d.P[j - 1]).magnitude;
                    Vector2 p = d.P[j], r = d.R[j] * half;
                    // the ribbon: centre and both edges lie on the ground + lift, flat in between
                    d.YC[j] = CityGround.HeightAt(p.x, p.y) + lift; d.YR[j] = CityGround.HeightAt(p.x + r.x, p.y + r.y) + lift; d.YL[j] = CityGround.HeightAt(p.x - r.x, p.y - r.y) + lift;
                    d.Plot[j] = OnLandmarkPlot(ls, p.x, p.y) || (d.Cls != TwinData.RoadClass.Highway && d.Cls != TwinData.RoadClass.Ring && FilmRoads.InInterchange(p.x, p.y));
                    d.Gate[j] = Landmarks.IconicDistrict.InGate(p.x, p.y);
                }
                d.Len = d.Cum[m - 1];
                switch (d.Cls)
                {
                    case TwinData.RoadClass.Highway: d.Speed = 25f; d.Weight = 1f / 28f; break;      // 90 km/h, cars per metre of lane at the peak
                    case TwinData.RoadClass.Ring: d.Speed = 19.5f; d.Weight = 1f / 30f; break;      // 70 km/h
                    case TwinData.RoadClass.Main: d.Speed = 14f; d.Weight = 1f / 32f; break;        // 50 km/h
                    default: d.Speed = 8.5f; d.Weight = 1f / 60f; break;                           // 30 km/h
                }
            }
            FindTwins();
            staticBuilt = true;
        }

        /// <summary>The point order of a one-way carriageway in the film roads is the order it was traced in, not the way it runs (about half
        /// of them run against the traffic). Right-hand traffic: the other carriageway of the pair lies on the left of the travel direction,
        /// so a carriageway whose parallel twin (same class, 3–30 m aside) lies mostly on its right is reversed.</summary>
        void OrientOneWays()
        {
            const float GC = 40f; var g = new Dictionary<long, List<(int w, int k)>>();
            for (int i = 0; i < ways.Length; i++)
            {
                var w = ways[i]; if (w == null || !w.OneWay) continue;
                for (int k = 0; k + 1 < w.P.Length; k++)
                {
                    var m = (w.P[k] + w.P[k + 1]) * 0.5f; long key = Key(Mathf.FloorToInt(m.x / GC), Mathf.FloorToInt(m.y / GC));
                    if (!g.TryGetValue(key, out var l)) g[key] = l = new List<(int, int)>(); l.Add((i, k));
                }
            }
            for (int i = 0; i < ways.Length; i++)
            {
                var w = ways[i]; if (w == null || !w.OneWay) continue;
                int left = 0, right = 0;
                for (int k = 0; k + 1 < w.P.Length; k++)
                {
                    Vector2 m = (w.P[k] + w.P[k + 1]) * 0.5f, t = w.P[k + 1] - w.P[k]; if (t.sqrMagnitude < 1f) continue; t.Normalize();
                    int gx = Mathf.FloorToInt(m.x / GC), gz = Mathf.FloorToInt(m.y / GC); float best = 1e9f, side = 0f;
                    for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                    {
                        if (!g.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                        foreach (var e in l)
                        {
                            var o = ways[e.w]; if (e.w == i || o.Cls != w.Cls) continue;
                            Vector2 q = (o.P[e.k] + o.P[e.k + 1]) * 0.5f, u = o.P[e.k + 1] - o.P[e.k]; if (u.sqrMagnitude < 1f) continue;
                            if (Mathf.Abs(Vector2.Dot(u.normalized, t)) < 0.95f) continue;
                            Vector2 v = q - m; float cr = t.x * v.y - t.y * v.x, perp = Mathf.Abs(cr);
                            if (perp < 3f || perp > 30f || Mathf.Abs(Vector2.Dot(v, t)) > 12f || perp >= best) continue;
                            best = perp; side = cr;                                   // > 0: on the left of the point order
                        }
                    }
                    if (side > 0f) left++; else if (side < 0f) right++;
                }
                if (right > left) { System.Array.Reverse(w.P); int a = w.A; w.A = w.B; w.B = a; }
            }
        }

        /// <summary>The plan sometimes draws one street twice (two strokes with other opening years, or a short piece over a long one):
        /// a way that lies on another for most of its length carries no traffic of its own while that other one is open.</summary>
        void FindTwins()
        {
            twins = new List<int>[ways.Length];
            const float GC = 20f; var g = new Dictionary<long, List<(int w, int k)>>();
            for (int i = 0; i < ways.Length; i++)
            {
                var w = ways[i]; if (w == null) continue;
                for (int k = 0; k < w.P.Length; k++)
                {
                    long key = Key(Mathf.FloorToInt(w.P[k].x / GC), Mathf.FloorToInt(w.P[k].y / GC));
                    if (!g.TryGetValue(key, out var l)) g[key] = l = new List<(int, int)>(); l.Add((i, k));
                }
            }
            var stamp = new Dictionary<int, int>(); var hits = new Dictionary<int, int>();
            for (int i = 0; i < ways.Length; i++)
            {
                var w = ways[i]; if (w == null || w.P.Length < 3) continue;
                stamp.Clear(); hits.Clear();
                for (int k = 0; k < w.P.Length; k++)
                {
                    var p = w.P[k]; int gx = Mathf.FloorToInt(p.x / GC), gz = Mathf.FloorToInt(p.y / GC);
                    for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                    {
                        if (!g.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                        foreach (var e in l)
                        {
                            if (e.w == i || (stamp.TryGetValue(e.w, out int st) && st == k)) continue;
                            if ((ways[e.w].P[e.k] - p).sqrMagnitude > 5f * 5f) continue;
                            stamp[e.w] = k; hits[e.w] = hits.TryGetValue(e.w, out int h) ? h + 1 : 1;
                        }
                    }
                }
                foreach (var kv in hits) if (kv.Value > w.P.Length * 0.7f) { if (twins[i] == null) twins[i] = new List<int>(); twins[i].Add(kv.Key); }
            }
        }
        List<int>[] twins;
        bool Shadowed(int i, int year, int sc)
        {
            var t = twins != null ? twins[i] : null; if (t == null) return false;
            foreach (int j in t)
            {
                var o = ways[j]; if (o == null || o.Years[sc] > year) continue;
                bool mutual = twins[j] != null && twins[j].Contains(i);
                if (!mutual || j < i) return true;
            }
            return false;
        }

        // ------------------------------------------------------------------ the streets of the Gate district (not film roads: its own model)
        [System.Serializable] class GateRoadJ { public int o; public float[] p; }
        [System.Serializable] class GateRoadsJ { public GateRoadJ[] roads; }
        bool gateAdded;
        /// <summary>The centre lines of the district's asphalt (Resources/Film/Traffic/gate_roads.json, the district's local frame, traced from
        /// gate_district.bytes): two-way streets with a lane each side, the two small roundabouts one-way counterclockwise. Only while the
        /// district stands (IconicDistrict.On), when the film roads inside it are hidden.</summary>
        void AddGateWays()
        {
            gateAdded = true;
            var ls = Landmarks.LandmarkSystem.Instance; var host = ls != null ? ls.Get("iconic") : null;
            var ta = Resources.Load<TextAsset>("Film/Traffic/gate_roads");
            if (host == null || ta == null) return;
            GateRoadsJ data; try { data = JsonUtility.FromJson<GateRoadsJ>(ta.text); } catch { return; }
            if (data == null || data.roads == null) return;
            float a = host.Yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
            const float Lift = 0.12f;
            var list = new List<WayD>(ways);
            foreach (var r in data.roads)
            {
                if (r.p == null || r.p.Length < 6) continue;
                int m = r.p.Length / 3; bool one = r.o == 1; float half = one ? 2.5f : 3.6f;
                var d = new WayD { P = new Vector2[m], R = new Vector2[m], T = new Vector2[m], Cum = new float[m], YC = new float[m], YL = new float[m], YR = new float[m],
                    Plot = new bool[m], Gate = new bool[m], Half = half, Lanes = 1, OneWay = one, GateRoad = true, Cls = TwinData.RoadClass.Main,
                    Years = Vector4.zero, A = -1, B = -1, Speed = one ? 7f : 11f, Weight = 1f / 30f };
                var ly = new float[m];
                for (int j = 0; j < m; j++)
                {
                    float x = r.p[3 * j], z = r.p[3 * j + 2]; ly[j] = r.p[3 * j + 1];
                    d.P[j] = new Vector2(host.X + x * ca + z * sa, host.Z - x * sa + z * ca);   // Euler(0, Yaw) of the local point
                }
                for (int j = 0; j < m; j++)
                {
                    Vector2 t = d.P[Mathf.Min(j + 1, m - 1)] - d.P[Mathf.Max(j - 1, 0)]; t = t.sqrMagnitude > 1e-6f ? t.normalized : Vector2.up;
                    d.T[j] = t; d.R[j] = new Vector2(t.y, -t.x);
                    if (j > 0) d.Cum[j] = d.Cum[j - 1] + (d.P[j] - d.P[j - 1]).magnitude;
                    Vector2 p = d.P[j], rr = d.R[j] * half; float off = ly[j] + Lift;
                    d.YC[j] = CityGround.HeightAt(p.x, p.y) + off; d.YR[j] = CityGround.HeightAt(p.x + rr.x, p.y + rr.y) + off; d.YL[j] = CityGround.HeightAt(p.x - rr.x, p.y - rr.y) + off;
                }
                d.Len = d.Cum[m - 1];
                if (d.Len > 4f) list.Add(d);
            }
            ways = list.ToArray();
            if (twins != null && twins.Length < ways.Length) System.Array.Resize(ref twins, ways.Length);
        }

        static bool OnLandmarkPlot(Landmarks.LandmarkSystem ls, float x, float z)
        {
            if (ls == null) return false;
            foreach (var l in ls.Items)
            {
                if (l.IsLrt || l.PadW <= 0f) continue;
                float dx = x - l.X, dz = z - l.Z, a = l.Yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
                float u = dx * ca - dz * sa, v = dx * sa + dz * ca;
                if (Mathf.Abs(u) < l.PadW * 0.5f + 1.5f && Mathf.Abs(v) < l.PadD * 0.5f + 1.5f) return true;
            }
            return false;
        }

        void BuildLanes(int year, int sc, bool gate)
        {
            for (int i = 0; i < pool; i++) cars[i].alive = false;
            lanes.Clear(); samples.Clear(); grid.Clear(); regionValid = false;
            builtYear = year; builtSc = sc; builtGate = gate;
            if (gate && !gateAdded) AddGateWays();
            for (int wi = 0; wi < ways.Length; wi++)
            {
                var w = ways[wi]; if (w == null) continue;
                if (w.GateRoad) { if (gate) AddRun(wi, 0, w.P.Length - 1, true, true); continue; }
                if (w.Years[Mathf.Clamp(sc, 0, 3)] > year || Shadowed(wi, year, Mathf.Clamp(sc, 0, 3))) continue;
                int m = w.P.Length, j = 0;
                while (j < m)
                {
                    while (j < m && (w.Plot[j] || (gate && w.Gate[j]))) j++;
                    int a = j; while (j < m && !(w.Plot[j] || (gate && w.Gate[j]))) j++;
                    int b = j - 1; if (b - a < 1 || w.Cum[b] - w.Cum[a] < 30f) continue;
                    // a run cut by the Gate district may go on into the district's own streets
                    AddRun(wi, a, b, a == 0 || (gate && w.Gate[a - 1]), b == m - 1 || (gate && w.Gate[b + 1]));
                }
            }
            // junctions: a lane goes on into any lane that starts where it ends (within 14 m) and does not turn back
            const float JC = 16f; var starts = new Dictionary<long, List<int>>();
            for (int i = 0; i < lanes.Count; i++)
            {
                var L = lanes[i]; long k = Key(Mathf.FloorToInt(L.SP.x / JC), Mathf.FloorToInt(L.SP.y / JC));
                if (!starts.TryGetValue(k, out var l)) starts[k] = l = new List<int>(); l.Add(i);
            }
            for (int i = 0; i < lanes.Count; i++)
            {
                var L = lanes[i]; if (!L.EndJ) continue;
                int gx = Mathf.FloorToInt(L.EP.x / JC), gz = Mathf.FloorToInt(L.EP.y / JC);
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!starts.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (int j in l)
                    {
                        var M = lanes[j]; if (M.W == L.W) continue;
                        if ((M.SP - L.EP).sqrMagnitude > 14f * 14f) continue;
                        float turn = Vector2.SignedAngle(L.ED, M.SD); if (Mathf.Abs(turn) > 125f) continue;
                        L.Next.Add(j); L.Turn.Add(turn);
                    }
                }
            }
            // samples every 20 m for placing cars, weighted by how busy the road class is
            for (int i = 0; i < lanes.Count; i++)
            {
                var L = lanes[i]; var w = ways[L.W];
                for (float s = 6f; s < L.Len - 6f; s += 20f)
                {
                    var p = PointAt(L, s); int si = samples.Count;
                    samples.Add(new Sample { Lane = i, S = s, W = w.Weight * 20f, P = p });
                    long k = Key(Mathf.FloorToInt(p.x / Cell), Mathf.FloorToInt(p.y / Cell));
                    if (!grid.TryGetValue(k, out var l)) grid[k] = l = new List<int>(); l.Add(si);
                }
            }
        }

        void AddRun(int wi, int a, int b, bool startIsEnd, bool endIsEnd)
        {
            var w = ways[wi]; int n = w.Lanes; float len = w.Cum[b] - w.Cum[a];
            for (int dir = 0; dir < (w.OneWay ? 1 : 2); dir++)
            {
                bool rev = dir == 1; int first = lanes.Count;
                for (int i = 0; i < n; i++)
                {
                    float off = w.OneWay ? -w.Half + (i + 0.5f) * 2f * w.Half / n : (i + 0.5f) * w.Half / n;   // right of the travel direction
                    var L = new Lane { W = wi, Rev = rev, I0 = a, I1 = b, Off = off, Len = len, Idx = i, Count = n };
                    L.SP = rev ? w.P[b] : w.P[a]; L.EP = rev ? w.P[a] : w.P[b];
                    L.SD = rev ? -w.T[b] : w.T[a]; L.ED = rev ? -w.T[a] : w.T[b];
                    L.EndJ = rev ? startIsEnd : endIsEnd;
                    lanes.Add(L);
                }
                if (rev) for (int i = 0; i < n; i++) { lanes[first + i].Reverse = first - n + i; lanes[first - n + i].Reverse = first + i; }
            }
        }

        Vector2 PointAt(Lane L, float s)
        {
            var w = ways[L.W]; float d = L.Rev ? w.Cum[L.I1] - s : w.Cum[L.I0] + s; int k = L.I0;
            while (k < L.I1 - 1 && w.Cum[k + 1] < d) k++;
            float t = Mathf.InverseLerp(w.Cum[k], w.Cum[k + 1], d);
            Vector2 c = Vector2.LerpUnclamped(w.P[k], w.P[k + 1], t), r = Vector2.LerpUnclamped(w.R[k], w.R[k + 1], t);
            return c + r * (L.Rev ? -L.Off : L.Off);
        }

        /// <summary>World position and heading of a car on a lane: the point on the centre line, offset into the lane, on the ribbon's surface.</summary>
        void Pose(Lane L, float s, ref int k, out Vector3 pos, out Vector3 fwd)
        {
            var w = ways[L.W]; float d = L.Rev ? w.Cum[L.I1] - s : w.Cum[L.I0] + s;
            if (k < L.I0 || k >= L.I1) k = L.I0;
            while (k < L.I1 - 1 && w.Cum[k + 1] < d) k++;
            while (k > L.I0 && w.Cum[k] > d) k--;
            float seg = w.Cum[k + 1] - w.Cum[k], t = seg > 1e-4f ? Mathf.Clamp01((d - w.Cum[k]) / seg) : 0f;
            Vector2 c = Vector2.LerpUnclamped(w.P[k], w.P[k + 1], t), r = Vector2.LerpUnclamped(w.R[k], w.R[k + 1], t), tg = Vector2.LerpUnclamped(w.T[k], w.T[k + 1], t);
            float off = L.Rev ? -L.Off : L.Off, f = Mathf.Abs(off) / Mathf.Max(w.Half, 0.1f);
            float yc = Mathf.LerpUnclamped(w.YC[k], w.YC[k + 1], t), ye = off >= 0f ? Mathf.LerpUnclamped(w.YR[k], w.YR[k + 1], t) : Mathf.LerpUnclamped(w.YL[k], w.YL[k + 1], t);
            var p = c + r * off;
            pos = new Vector3(p.x, yc + (ye - yc) * f, p.y);
            float slope = seg > 1e-4f ? (w.YC[k + 1] - w.YC[k]) / seg : 0f;
            if (L.Rev) { tg = -tg; slope = -slope; }
            fwd = new Vector3(tg.x, slope, tg.y);
        }

        // ------------------------------------------------------------------ how busy
        float Density()
        {
            int y = TwinState.Year < 1 ? 2050 : TwinState.Year, s = (int)TwinState.Scenario; float yearF;
            var ys = TwinData.TrafficYears; var kp = s >= 0 && s < TwinData.TrafficKpi.Length ? TwinData.TrafficKpi[s] : null;
            if (ys != null && ys.Length > 0 && kp != null && kp.Length == ys.Length)
            {
                float At(int yy)
                {
                    int i = 0; while (i < ys.Length - 1 && ys[i + 1] <= yy) i++;
                    float a = kp[i] != null && kp[i].TryGetValue("car_trips", out var v) ? v : 0f;
                    if (i + 1 < ys.Length && yy > ys[i])
                    {
                        float b = kp[i + 1] != null && kp[i + 1].TryGetValue("car_trips", out var v2) ? v2 : a;
                        a = Mathf.Lerp(a, b, Mathf.InverseLerp(ys[i], ys[i + 1], yy));
                    }
                    return a;
                }
                float top = 1f; for (int i = 0; i < ys.Length; i++) if (kp[i] != null && kp[i].TryGetValue("car_trips", out var v)) top = Mathf.Max(top, v);
                yearF = At(y) / top;
            }
            else yearF = Mathf.InverseLerp(2024f, 2050f, y);
            yearF = Mathf.Clamp(yearF, 0.12f, 1f);
            float h = FilmLook.Instance != null ? FilmLook.Instance.hour : 12f;
            // daily profile of a city: quiet at night, a morning and an evening rush, busy middle of the day
            float hourF = 0.10f + 0.50f * Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(5f, 8f, h)) * (1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(20f, 23.5f, h)))
                          + 0.40f * Mathf.Exp(-(h - 8.5f) * (h - 8.5f) / 1.4f) + 0.40f * Mathf.Exp(-(h - 18.5f) * (h - 18.5f) / 1.8f) + 0.12f * Mathf.Exp(-(h - 13f) * (h - 13f) / 6f);
            return yearF * Mathf.Clamp(hourF, 0.08f, 1f);
        }
        float HourSpeed()
        {
            float h = FilmLook.Instance != null ? FilmLook.Instance.hour : 12f;
            // rush hours: the main roads move slower
            return 1f - 0.25f * Mathf.Exp(-(h - 8.5f) * (h - 8.5f) / 1.2f) - 0.25f * Mathf.Exp(-(h - 18.5f) * (h - 18.5f) / 1.5f);
        }

        // ------------------------------------------------------------------ frame
        /// <summary>How far the system got last frame (self-check for the capture tools): 1 running, 2 film look on, 3 film roads built,
        /// 4 lanes open, 5 roads near the camera, 6 cars wanted, 7 cars alive, 8 cars drawn.</summary>
        public static int Stage;
        /// <summary>Throws when the system did not get as far as stage n (the capture tool logs "invoke failed").</summary>
        public static void Expect(int n) { if (Stage < n) throw new System.Exception("film traffic stage " + Stage); }
        /// <summary>Frame rate of the last ~2 s and the same kind of self-check: throws below f fps, or with fewer than n vehicles drawn.</summary>
        public static float Fps;
        public static void ExpectFps(float f) { if (Fps < f) throw new System.Exception("fps " + Fps.ToString("0.0")); }
        public static void ExpectDrawn(int n) { if (Drawn < n) throw new System.Exception("drawn " + Drawn); }
        float fpsT; int fpsN;

        bool drawnLate;
        // the simulation runs in LateUpdate, after the map camera has moved, so the cars are placed for the camera of this frame
        void LateUpdate()
        {
            fpsT += Time.unscaledDeltaTime; fpsN++; if (fpsT >= 2f) { Fps = fpsN / fpsT; fpsT = 0f; fpsN = 0; }
            Alive = 0; Stage = 1; drawnLate = false;
            if (!FilmLook.Active || !On) { Drawn = 0; return; }
            Stage = 2;
            if (!TwinData.Ready || FilmRoads.WayCount == 0) { Drawn = 0; return; }
            Stage = 3;
            if (!staticBuilt) BuildStatic();
            int year = TwinState.Year < 1 ? 2050 : TwinState.Year, sc = (int)TwinState.Scenario; bool gate = Landmarks.IconicDistrict.On;
            if (year != builtYear || sc != builtSc || gate != builtGate) BuildLanes(year, sc, gate);
            if (lanes.Count == 0) return;
            Stage = 4;
            cam = Camera.main; if (cam == null) return;
            Focus(cam);
            if (camDist > 9000f) { Drawn = 0; return; }
            Region(false);
            if (cand.Count > 0) Stage = 5;
            if (Target() > 0) Stage = 6;
            Simulate(Mathf.Min(Time.deltaTime, 0.1f));
            Populate(false);
            if (Alive > 0) Stage = 7;
            Collect();
            if (Drawn > 0) Stage = 8;
            Draw(cam);
            drawnLate = true;
        }

        void Draw(Camera c)
        {
            bool shadows = high && camDist < 1800f;
            for (int k = 0; k < counts.Length; k++)
                for (int b = 0; b < counts[k].Length; b++)
                    if (counts[k][b] > 0)
                        Graphics.DrawMeshInstanced(meshes[k], 0, mat, mats[k][b], counts[k][b], mpbs[k][b], shadows ? ShadowCastingMode.On : ShadowCastingMode.Off, true, 0, c);
        }

        void Focus(Camera c)
        {
            var t = c.transform; camPos = t.position; Vector3 f = t.forward;
            float h = camPos.y - CityGround.HeightAt(camPos.x, camPos.z), d = f.y < -0.02f ? Mathf.Max(h, 2f) / -f.y : 1e6f;
            // a view along the ground (street level, the horizon in the picture): the cars that matter are the near ones
            d = Mathf.Min(d, 400f + 4f * Mathf.Max(h, 0f), 12000f);
            var fp = camPos + f * d; camDist = d; nowFocus = new Vector2(fp.x, fp.z);
            nowR = Mathf.Clamp(Mathf.Max(d, h) * 1.4f, high ? 700f : 450f, high ? 3500f : 1200f);
            GeometryUtility.CalculateFrustumPlanes(c, frustum);
        }
        Vector2 nowFocus; float nowR;

        /// <summary>The cars live in a circle round the focus; moved far → a fresh set.</summary>
        void Region(bool force)
        {
            float moved = (nowFocus - focus).magnitude;
            bool jump = moved > radius * 0.9f || nowR > radius * 1.6f || nowR < radius * 0.5f;
            if (!force && regionValid && moved < radius * 0.2f && Mathf.Abs(nowR - radius) < radius * 0.2f) return;
            focus = nowFocus; radius = nowR; regionValid = true;
            cand.Clear(); regionWeight = 0f;
            int g0x = Mathf.FloorToInt((focus.x - radius) / Cell), g1x = Mathf.FloorToInt((focus.x + radius) / Cell);
            int g0z = Mathf.FloorToInt((focus.y - radius) / Cell), g1z = Mathf.FloorToInt((focus.y + radius) / Cell);
            float r2 = radius * radius;
            for (int gx = g0x; gx <= g1x; gx++) for (int gz = g0z; gz <= g1z; gz++)
            {
                if (!grid.TryGetValue(Key(gx, gz), out var l)) continue;
                foreach (int si in l)
                {
                    if ((samples[si].P - focus).sqrMagnitude > r2) continue;
                    if (cand.Count >= candCum.Length) System.Array.Resize(ref candCum, candCum.Length * 2);
                    regionWeight += samples[si].W; candCum[cand.Count] = regionWeight; cand.Add(si);
                }
            }
            if (jump || force) { for (int i = 0; i < pool; i++) cars[i].alive = false; for (int i = 0; i < lanes.Count; i++) lanes[i].Tail = -1; Populate(true); }
        }

        int Target() => regionValid ? Mathf.Min(pool, Mathf.RoundToInt(regionWeight * Density())) : 0;

        /// <summary>Bring the number of cars to what the model asks for; new cars appear out of sight where possible.</summary>
        void Populate(bool all)
        {
            int want = Target(), alive = 0;
            for (int i = 0; i < pool; i++) if (cars[i].alive) alive++;
            if (all) { Seed(want); return; }
            int budget = high ? 24 : 12;
            for (int i = 0; i < pool && alive < want && budget > 0; i++) if (!cars[i].alive) { if (Spawn(i, true)) { alive++; budget--; } else budget--; }
            // too many (the hour or the year changed): the extra ones leave out of sight
            for (int i = 0; i < pool && alive > want + want / 10 + 2 && budget > 0; i++)
                if (cars[i].alive && !cars[i].dying && !Visible(cars[i])) { Remove(i); alive--; budget--; }
            Alive = alive;
        }

        bool Visible(in Car c)
        {
            var L = lanes[c.lane]; var p = PointAt(L, c.s); var w = ways[L.W];
            var b = new Bounds(new Vector3(p.x, w.YC[L.I0], p.y), new Vector3(6f, 200f, 6f));
            return GeometryUtility.TestPlanesAABB(frustum, b) && (new Vector2(camPos.x, camPos.z) - p).magnitude < radius * 0.75f;
        }

        int PickSample()
        {
            if (cand.Count == 0 || regionWeight <= 0f) return -1;
            float r = Random.value * regionWeight; int lo = 0, hi = cand.Count - 1;
            while (lo < hi) { int m = (lo + hi) >> 1; if (candCum[m] < r) lo = m + 1; else hi = m; }
            return cand[lo];
        }

        /// <summary>Initial set: cars spread over the lanes of the region, each lane's cars chained front to back.</summary>
        void Seed(int want)
        {
            int n = 0;
            for (int i = 0; i < want && n < pool; i++)
            {
                int si = PickSample(); if (si < 0) break;
                var sm = samples[si]; float s = sm.S + Random.Range(-9f, 9f); var L = lanes[sm.Lane]; s = Mathf.Clamp(s, 0f, L.Len - 1f);
                Init(n, sm.Lane, s, 1f); n++;
            }
            // order per lane and drop cars that would overlap
            var idx = new List<int>(n); for (int i = 0; i < n; i++) idx.Add(i);
            idx.Sort((a, b) => cars[a].lane != cars[b].lane ? cars[a].lane.CompareTo(cars[b].lane) : cars[a].s.CompareTo(cars[b].s));
            for (int q = 0; q < idx.Count; q++)
            {
                int i = idx[q]; int lane = cars[i].lane;
                int j = q + 1 < idx.Count && cars[idx[q + 1]].lane == lane ? idx[q + 1] : -1;
                if (j >= 0 && cars[j].s - cars[i].s < (KLen[cars[i].kind] + KLen[cars[j].kind]) * 0.5f + 4f) { cars[i].alive = false; continue; }
            }
            int prevLane = -1, prevCar = -1;
            for (int q = idx.Count - 1; q >= 0; q--)
            {
                int i = idx[q]; if (!cars[i].alive) continue;
                if (cars[i].lane != prevLane) { prevLane = cars[i].lane; prevCar = -1; }
                cars[i].leader = prevCar; prevCar = i; lanes[prevLane].Tail = i;
                // start at the speed of the road
                cars[i].v = cars[i].vMax * 0.8f;
            }
        }

        void Init(int i, int lane, float s, float scale)
        {
            var L = lanes[lane]; var w = ways[L.W]; ref var c = ref cars[i];
            c.alive = true; c.dying = false; c.lane = lane; c.s = s; c.next = -1; c.leader = -1; c.k = L.I0; c.wait = 0f; c.carry = Vector3.zero; c.scale = scale; c.brake = false;
            c.life = Random.value * 100f;
            var P = L.EP; float r = Random.value;
            // what drives here: buses on the main roads, trucks on the motorways and near the industrial zone (PepsiCo plant)
            bool ind = (P - new Vector2(8500f, 940f)).sqrMagnitude < 4000f * 4000f;
            float pBus = w.Cls == TwinData.RoadClass.Main ? 0.05f : w.Cls == TwinData.RoadClass.Ring ? 0.03f : 0f;
            float pTruck = w.Cls == TwinData.RoadClass.Highway ? (ind ? 0.22f : 0.08f) : w.Cls == TwinData.RoadClass.Ring ? 0.05f : ind ? 0.10f : 0.01f;
            if (L.Count > 1 && L.Idx == L.Count - 1 && pBus > 0f) pBus *= 2.2f;          // buses keep to the outer lane
            int kind = r < pBus ? Bus : r < pBus + pTruck ? Truck : r < pBus + pTruck + 0.07f ? Van : r < pBus + pTruck + 0.07f + 0.30f ? Suv : Sedan;
            if (kind == Bus && L.Count > 1 && L.Idx != L.Count - 1) kind = Van;
            c.kind = kind;
            c.col = kind == Bus ? BusPal[Random.Range(0, BusPal.Length)] : kind == Truck ? TruckPal[Random.Range(0, TruckPal.Length)] : kind == Van ? VanPal[Random.Range(0, VanPal.Length)] : PickCarColour();
            float vf = kind == Bus ? 0.78f : kind == Truck ? 0.82f : Random.Range(0.9f, 1.1f);
            c.vMax = w.Speed * vf; c.v = c.vMax * 0.7f;
        }
        static Color PickCarColour()
        {
            float r = Random.value, acc = 0f;
            for (int i = 0; i < CarPal.Length; i++) { acc += CarPalW[i]; if (r <= acc) return CarPal[i]; }
            return CarPal[0];
        }

        /// <summary>A new car in a gap of a lane, if possible out of sight.</summary>
        bool Spawn(int i, bool hidden)
        {
            for (int attempt = 0; attempt < 4; attempt++)
            {
                int si = PickSample(); if (si < 0) return false;
                var sm = samples[si]; var L = lanes[sm.Lane];
                Init(i, sm.Lane, sm.S, 1f);
                if (hidden && attempt < 3 && Visible(cars[i])) { cars[i].alive = false; continue; }
                // the cars in front of and behind this point
                int ahead = -1, behind = -1; float sa = float.MaxValue, sb = -float.MaxValue;
                for (int j = 0; j < pool; j++)
                {
                    if (j == i || !cars[j].alive || cars[j].lane != sm.Lane) continue;
                    float s = cars[j].s; if (s >= sm.S && s < sa) { sa = s; ahead = j; } else if (s < sm.S && s > sb) { sb = s; behind = j; }
                }
                float need = KLen[cars[i].kind] + 8f;
                if ((ahead >= 0 && sa - sm.S < need) || (behind >= 0 && sm.S - sb < need)) { cars[i].alive = false; continue; }
                cars[i].leader = ahead;
                if (behind >= 0) cars[behind].leader = i; else L.Tail = i;
                if (ahead >= 0) cars[i].v = Mathf.Min(cars[i].v, cars[ahead].v);
                return true;
            }
            return false;
        }

        /// <summary>A car leaves its lane (respawn or end of the road): whoever followed it now follows the car in front of it.</summary>
        void Remove(int i)
        {
            ref var c = ref cars[i]; if (!c.alive) return;
            int lane = c.lane, lead = c.leader;
            for (int j = 0; j < pool; j++) if (cars[j].alive && cars[j].leader == i) cars[j].leader = cars[j].lane == lane ? lead : -1;
            if (lanes[lane].Tail == i) lanes[lane].Tail = -1;
            c.alive = false;
        }

        int ChooseNext(int lane, int kind)
        {
            var L = lanes[lane]; if (L.Next.Count == 0) return -2;
            float tot = 0f;
            for (int q = 0; q < L.Next.Count; q++) tot += NextW(L, q, kind);
            if (tot <= 0f) return -2;
            float r = Random.value * tot;
            for (int q = 0; q < L.Next.Count; q++) { r -= NextW(L, q, kind); if (r <= 0f) return L.Next[q]; }
            return L.Next[L.Next.Count - 1];
        }
        float NextW(Lane L, int q, int kind)
        {
            var M = lanes[L.Next[q]]; float turn = Mathf.Abs(L.Turn[q]);
            float w = turn < 30f ? 3f : 1f;
            // keep the lane: the same position from the right
            int fromRight = L.Count - 1 - L.Idx, mr = M.Count - 1 - M.Idx;
            w *= mr == Mathf.Min(fromRight, M.Count - 1) ? 3f : 0.4f;
            var mc = ways[M.W].Cls;
            if (kind == Bus && mc != TwinData.RoadClass.Main && mc != TwinData.RoadClass.Ring) w *= 0.05f;
            if ((kind == Truck || kind == Bus) && mc == TwinData.RoadClass.Street) w *= 0.1f;
            if (mc == TwinData.RoadClass.Street && ways[L.W].Cls != TwinData.RoadClass.Street) w *= 0.35f;
            return w;
        }

        void Simulate(float dt)
        {
            float hs = HourSpeed(); float r2 = radius * 1.15f; r2 *= r2;
            int respawns = high ? 24 : 12;
            for (int i = 0; i < pool; i++)
            {
                ref var c = ref cars[i]; if (!c.alive) continue;
                c.carry = Vector3.MoveTowards(c.carry, Vector3.zero, dt * 6f);
                if (c.dying)
                {
                    c.scale -= dt * 2.5f; if (c.scale <= 0f) Remove(i);
                    continue;
                }
                if (c.scale < 1f) c.scale = Mathf.Min(1f, c.scale + dt * 2.5f);
                var L = lanes[c.lane];
                float target = c.vMax * (ways[L.W].Cls == TwinData.RoadClass.Street ? 1f : hs);
                float rem = L.Len - c.s;
                if (c.next == -1 && rem < 90f) c.next = ChooseNext(c.lane, c.kind);
                float vEnd = target;
                if (c.next >= 0)
                {
                    int q = L.Next.IndexOf(c.next); float turn = q >= 0 ? Mathf.Abs(L.Turn[q]) : 0f;
                    vEnd = target * Mathf.Lerp(ways[L.W].Cls == TwinData.RoadClass.Highway ? 1f : 0.85f, 0.32f, Mathf.Clamp01(turn / 90f));
                    vEnd = Mathf.Max(vEnd, 4f);
                }
                float vAllowed = Mathf.Sqrt(vEnd * vEnd + 2f * 2.2f * Mathf.Max(rem, 0f));
                // following: a gap of ~1.4 s plus 3 m behind the car in front (also across the junction ahead)
                float vFollow = float.MaxValue;
                if (c.leader >= 0)
                {
                    ref var ld = ref cars[c.leader];
                    float gap = -1f;
                    if (ld.alive && ld.lane == c.lane && ld.s >= c.s) gap = ld.s - c.s;
                    else if (ld.alive && c.next >= 0 && ld.lane == c.next) gap = rem + ld.s;
                    else c.leader = -1;
                    if (gap >= 0f)
                    {
                        gap -= (KLen[ld.kind] + KLen[c.kind]) * 0.5f;
                        float want = 3f + c.v * 1.4f;
                        vFollow = Mathf.Max(0f, ld.v + (gap - want) * 0.5f);
                        if (gap < 1.5f) vFollow = 0f;
                    }
                }
                float vT = Mathf.Min(target, Mathf.Min(vAllowed, vFollow));
                c.brake = vT < c.v - 0.3f || c.v < 0.5f;
                c.v = vT > c.v ? Mathf.Min(vT, c.v + 2.0f * dt) : Mathf.Max(vT, c.v - 7f * dt);
                c.s += c.v * dt;
                if (c.s >= L.Len)
                {
                    if (c.next >= 0)
                    {
                        var M = lanes[c.next]; int tail = M.Tail;
                        bool blocked = tail >= 0 && tail != c.leader && cars[tail].alive && cars[tail].lane == c.next && cars[tail].s < (KLen[cars[tail].kind] + KLen[c.kind]) * 0.5f + 1.5f;
                        if (blocked && c.wait < 6f) { c.s = L.Len; c.v = 0f; c.wait += dt; continue; }
                        Pose(L, L.Len, ref c.k, out var p0, out _);
                        float over = c.s - L.Len; int old = c.lane;
                        if (lanes[old].Tail == i) lanes[old].Tail = -1;
                        c.lane = c.next; c.next = -1; c.s = Mathf.Min(over, M.Len * 0.5f); c.k = M.I0; c.wait = 0f;
                        if (c.leader >= 0 && !(cars[c.leader].alive && cars[c.leader].lane == c.lane)) c.leader = -1;
                        if (c.leader < 0 && tail >= 0 && cars[tail].alive && cars[tail].lane == c.lane && cars[tail].s >= c.s) c.leader = tail;
                        M.Tail = i;
                        Pose(M, c.s, ref c.k, out var p1, out _);
                        c.carry += p0 - p1; if (c.carry.sqrMagnitude > 25f * 25f) c.carry = Vector3.zero;
                    }
                    else { c.s = L.Len; c.dying = true; continue; }
                }
                // left the region round the camera: a new car somewhere else in it
                if (respawns > 0 && (i + Time.frameCount) % 8 == 0)
                {
                    var p = PointAt(lanes[c.lane], c.s);
                    if ((p - focus).sqrMagnitude > r2) { Remove(i); respawns--; Spawn(i, true); }
                }
            }
        }

        // ------------------------------------------------------------------ drawing
        void Collect()
        {
            for (int k = 0; k < counts.Length; k++) System.Array.Clear(counts[k], 0, counts[k].Length);
            int drawn = 0, fine = 0; float fadeR = radius, fade0 = radius * 0.8f;
            for (int i = 0; i < pool; i++)
            {
                ref var c = ref cars[i]; if (!c.alive) continue;
                var L = lanes[c.lane];
                Pose(L, c.s, ref c.k, out var pos, out var fwd);
                pos += c.carry;
                float d = new Vector2(pos.x - focus.x, pos.z - focus.y).magnitude; if (d > fadeR) continue;
                float sc = c.scale * (1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(fade0, fadeR, d)));
                if (sc < 0.02f) continue;
                int kind = c.kind, b = 0;
                if (FineOn && fine < fineMax && (pos - camPos).sqrMagnitude < fineR * fineR) { kind += Kinds; fine++; }
                var cnt = counts[kind];
                while (b < cnt.Length && cnt[b] >= 1023) b++;
                if (b >= cnt.Length) continue;
                var rot = fwd.sqrMagnitude > 1e-6f ? Quaternion.LookRotation(fwd, Vector3.up) : Quaternion.identity;
                mats[kind][b][cnt[b]] = Matrix4x4.TRS(pos, rot, new Vector3(sc, sc, sc));
                cols[kind][b][cnt[b]] = new Vector4(c.col.r, c.col.g, c.col.b, c.brake ? 1f : 0f);
                cnt[b]++; drawn++;
            }
            Drawn = drawn;
            fineR = fine >= fineMax ? Mathf.Max(fineR * 0.85f, 12f) : fine < fineMax * 0.7f ? Mathf.Min(fineR * 1.05f, fineDist) : fineR;
            for (int k = 0; k < counts.Length; k++) for (int b = 0; b < counts[k].Length; b++) if (counts[k][b] > 0) mpbs[k][b].SetVectorArray(ColId, cols[k][b]);
            drawFrame = Time.frameCount;
        }

        void PreCull(Camera c)
        {
            if (c == null || mat == null || !enabled || !On || !FilmLook.Active || ways == null || cam == null) return;
            if (c != cam || drawFrame < 0 || lanes.Count == 0) return;
            // the frame's own render already has the cars (LateUpdate); only a camera moved by hand for one picture (the capture tool
            // renders after the end of the frame) gets them here, brought to where it looks first
            var t = c.transform;
            if (drawnLate && (t.position - camPos).sqrMagnitude < 1f) return;
            Focus(c);
            if (camDist > 9000f) return;
            if ((nowFocus - focus).magnitude > radius * 0.5f || nowR > radius * 1.6f || nowR < radius * 0.5f) Region(true);
            Collect();
            Draw(c);
        }

        // ------------------------------------------------------------------ meshes
        // vertex colour: rgb = fixed colour (or a multiplier of the paint), a = what it is: 1 paint, 0.8 fixed (trim, tyres, cargo box),
        // 0.6 glass, 0.4 head lamp, 0.2 tail lamp. uv1 = glow sprites (x: 1 head, 2 tail, 3 light pool on the road; yz corner; w radius).
        class MB
        {
            public readonly List<Vector3> V = new List<Vector3>(); public readonly List<Vector3> N = new List<Vector3>(); public readonly List<Color> Cl = new List<Color>();
            public readonly List<Vector4> U1 = new List<Vector4>(); public readonly List<int> T = new List<int>();
            public void Tri(Vector3 a, Vector3 b, Vector3 c, Color col, Vector3 outward)
            {
                var n = Vector3.Cross(b - a, c - a); if (n.sqrMagnitude < 1e-10f) return; n.Normalize();
                if (Vector3.Dot(n, outward) < 0f) { var t = b; b = c; c = t; n = -n; }
                int i = V.Count; V.Add(a); V.Add(b); V.Add(c);
                for (int k = 0; k < 3; k++) { N.Add(n); Cl.Add(col); U1.Add(Vector4.zero); }
                T.Add(i); T.Add(i + 1); T.Add(i + 2);
            }
            public void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Color col, Vector3 outward) { Tri(a, b, c, col, outward); Tri(a, c, d, col, outward); }
            /// <summary>A side profile (z, y), convex, extruded across x: half width at the bottom wb and at the top wt (tumblehome).
            /// edge(i) colours the face from point i to i+1; side colours both flanks.</summary>
            public void Extrude(Vector2[] prof, float wb, float wt, System.Func<int, Color> edge, Color side)
            {
                float y0 = float.MaxValue, y1 = float.MinValue; foreach (var p in prof) { y0 = Mathf.Min(y0, p.y); y1 = Mathf.Max(y1, p.y); }
                float W(float y) => Mathf.Lerp(wb, wt, Mathf.InverseLerp(y0, y1, y));
                Vector2 cen = Vector2.zero; foreach (var p in prof) cen += p; cen /= prof.Length;
                int n = prof.Length;
                for (int i = 0; i < n; i++)
                {
                    var p = prof[i]; var q = prof[(i + 1) % n];
                    Vector3 a = new Vector3(-W(p.y), p.y, p.x), b = new Vector3(W(p.y), p.y, p.x), c = new Vector3(W(q.y), q.y, q.x), d = new Vector3(-W(q.y), q.y, q.x);
                    var mid = (p + q) * 0.5f; var o = new Vector3(0f, mid.y - cen.y, mid.x - cen.x);
                    Quad(a, b, c, d, edge(i), o);
                }
                for (int sgn = -1; sgn <= 1; sgn += 2)
                    for (int i = 1; i < n - 1; i++)
                    {
                        Vector3 a = new Vector3(sgn * W(prof[0].y), prof[0].y, prof[0].x), b = new Vector3(sgn * W(prof[i].y), prof[i].y, prof[i].x), c = new Vector3(sgn * W(prof[i + 1].y), prof[i + 1].y, prof[i + 1].x);
                        Tri(a, b, c, side, new Vector3(sgn, 0f, 0f));
                    }
            }
            public void Box(Vector3 c, Vector3 s, Color col)
            {
                Vector3 h = s * 0.5f;
                Vector3 P(float x, float y, float z) => c + new Vector3(x * h.x, y * h.y, z * h.z);
                Quad(P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1), col, Vector3.up);
                Quad(P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1), col, Vector3.down);
                Quad(P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1), col, Vector3.forward);
                Quad(P(-1, -1, -1), P(1, -1, -1), P(1, 1, -1), P(-1, 1, -1), col, Vector3.back);
                Quad(P(1, -1, -1), P(1, 1, -1), P(1, 1, 1), P(1, -1, 1), col, Vector3.right);
                Quad(P(-1, -1, -1), P(-1, 1, -1), P(-1, 1, 1), P(-1, -1, 1), col, Vector3.left);
            }
            /// <summary>A wheel of the light mesh: an octagonal tyre across x with a paler hub face outside.</summary>
            public void Wheel(float x, float z, float r, float w)
            {
                var tyre = new Color(0.07f, 0.07f, 0.075f, 0.8f); var hub = new Color(0.42f, 0.43f, 0.45f, 0.8f);
                const int S = 8; float sg = Mathf.Sign(x), xi = x - sg * w * 0.5f, xo = x + sg * w * 0.5f;
                for (int i = 0; i < S; i++)
                {
                    float a0 = (i + 0.5f) * Mathf.PI * 2f / S, a1 = (i + 1.5f) * Mathf.PI * 2f / S;
                    Vector3 p0 = new Vector3(0f, r + Mathf.Sin(a0) * r, z + Mathf.Cos(a0) * r), p1 = new Vector3(0f, r + Mathf.Sin(a1) * r, z + Mathf.Cos(a1) * r);
                    var o = new Vector3(0f, Mathf.Sin((a0 + a1) * 0.5f), Mathf.Cos((a0 + a1) * 0.5f));
                    Quad(new Vector3(xi, p0.y, p0.z), new Vector3(xo, p0.y, p0.z), new Vector3(xo, p1.y, p1.z), new Vector3(xi, p1.y, p1.z), tyre, o);
                    Tri(new Vector3(xo, r, z), new Vector3(xo, p0.y, p0.z), new Vector3(xo, p1.y, p1.z), hub, new Vector3(sg, 0f, 0f));
                }
            }
            public void Lamp(float x0, float x1, float y0, float y1, float z, bool front, bool tail)
            {
                var col = tail ? new Color(0.5f, 0.05f, 0.04f, 0.2f) : new Color(0.9f, 0.9f, 0.86f, 0.4f);
                var o = front ? Vector3.forward : Vector3.back; float dz = front ? 0.012f : -0.012f;
                foreach (float sg in new[] { -1f, 1f })
                    Quad(new Vector3(sg * x0, y0, z + dz), new Vector3(sg * x1, y0, z + dz), new Vector3(sg * x1, y1, z + dz), new Vector3(sg * x0, y1, z + dz), col, o);
            }
            /// <summary>Glow sprites of the lamps (the glow pass draws them, the body pass hides them).</summary>
            public void Glow(Vector3 c, float type, float r)
            {
                int i = V.Count;
                for (int k = 0; k < 4; k++)
                {
                    float cx = k == 1 || k == 2 ? 1f : -1f, cy = k >= 2 ? 1f : -1f;
                    V.Add(c); N.Add(Vector3.up); Cl.Add(new Color(1f, 1f, 1f, 0f)); U1.Add(new Vector4(type, cx, cy, r));
                }
                T.Add(i); T.Add(i + 1); T.Add(i + 2); T.Add(i); T.Add(i + 2); T.Add(i + 3);
            }
            public void Glows(float xh, float yh, float zf, float xt, float yt, float zb, float pool)
            {
                foreach (float sg in new[] { -1f, 1f }) { Glow(new Vector3(sg * xh, yh, zf + 0.1f), 1f, 0.45f); Glow(new Vector3(sg * xt, yt, zb - 0.1f), 2f, 0.32f); }
                Glow(new Vector3(0f, 0.12f, zf + pool), 3f, 4.2f);
            }
            // ---------------------------------------------------------- the fine mesh (cars near the camera)
            public void TriN(Vector3 a, Vector3 b, Vector3 c, Vector3 na, Vector3 nb, Vector3 nc, Color col, Vector3 outward)
            {
                var n = Vector3.Cross(b - a, c - a); if (n.sqrMagnitude < 1e-12f) return;
                if (Vector3.Dot(n, outward) < 0f) { var t = b; b = c; c = t; var tn = nb; nb = nc; nc = tn; }
                int i = V.Count; V.Add(a); V.Add(b); V.Add(c); N.Add(na); N.Add(nb); N.Add(nc);
                for (int k = 0; k < 3; k++) { Cl.Add(col); U1.Add(Vector4.zero); }
                T.Add(i); T.Add(i + 1); T.Add(i + 2);
            }
            /// <summary>A lofted shell: one closed cross-section (x, y) per station z (front to back, every section the same number of points,
            /// running up the right side and down the left). Normals are smoothed over the shell, so bevel rows read as rounded edges;
            /// col(segment, interval) colours each face. Caps close the first and last section when given.</summary>
            public void Loft(float[] zs, Vector2[][] sec, System.Func<int, int, Color> col, Color? capF, Color? capB)
            {
                int S = zs.Length, n = sec[0].Length;
                var G = new Vector3[S, n]; for (int i = 0; i < S; i++) for (int j = 0; j < n; j++) G[i, j] = new Vector3(sec[i][j].x, sec[i][j].y, zs[i]);
                var F = new Vector3[S - 1, n];
                for (int i = 0; i < S - 1; i++) for (int j = 0; j < n; j++)
                {
                    int j1 = (j + 1) % n; F[i, j] = -Vector3.Cross(G[i + 1, j1] - G[i, j], G[i + 1, j] - G[i, j1]);
                }
                var VN = new Vector3[S, n];
                for (int i = 0; i < S; i++) for (int j = 0; j < n; j++)
                {
                    Vector3 sum = Vector3.zero; int jm = (j + n - 1) % n;
                    if (i > 0) sum += F[i - 1, j] + F[i - 1, jm];
                    if (i < S - 1) sum += F[i, j] + F[i, jm];
                    VN[i, j] = sum.sqrMagnitude > 1e-14f ? sum.normalized : Vector3.up;
                }
                for (int i = 0; i < S - 1; i++) for (int j = 0; j < n; j++)
                {
                    var o = F[i, j]; if (o.sqrMagnitude < 1e-12f) continue;
                    int j1 = (j + 1) % n; var c = col(j, i);
                    Vector3 a = G[i, j], b = G[i, j1], cc = G[i + 1, j1], d = G[i + 1, j];
                    TriN(a, b, cc, VN[i, j], VN[i, j1], VN[i + 1, j1], c, o);
                    TriN(a, cc, d, VN[i, j], VN[i + 1, j1], VN[i + 1, j], c, o);
                }
                for (int e = 0; e < 2; e++)
                {
                    var cap = e == 0 ? capF : capB; if (cap == null) continue;
                    int i = e == 0 ? 0 : S - 1; Vector3 cen = Vector3.zero; for (int j = 0; j < n; j++) cen += G[i, j]; cen /= n;
                    for (int j = 0; j < n; j++) Tri(cen, G[i, j], G[i, (j + 1) % n], cap.Value, e == 0 ? Vector3.forward : Vector3.back);
                }
            }
            /// <summary>A flat panel on a front (+z) or back face at z: lamps, grille, number plate, windscreen of a bus or truck.</summary>
            public void Panel(float x0, float x1, float y0, float y1, float z, bool front, Color col)
            {
                Quad(new Vector3(x0, y0, z), new Vector3(x1, y0, z), new Vector3(x1, y1, z), new Vector3(x0, y1, z), col, front ? Vector3.forward : Vector3.back);
            }
            /// <summary>A dark sheet just above the road under the body: the contact shadow seen between and around the wheels.</summary>
            public void Under(float hw, float z0, float z1)
            {
                var c = new Color(0.025f, 0.025f, 0.028f, 0.8f);
                Quad(new Vector3(-hw, 0.02f, z0), new Vector3(hw, 0.02f, z0), new Vector3(hw, 0.02f, z1), new Vector3(-hw, 0.02f, z1), c, Vector3.up);
            }
            /// <summary>A flat panel on a flank at x (doors of a bus).</summary>
            public void SidePanel(float x, float z0, float z1, float y0, float y1, Color col)
            {
                Quad(new Vector3(x, y0, z0), new Vector3(x, y0, z1), new Vector3(x, y1, z1), new Vector3(x, y1, z0), col, new Vector3(Mathf.Sign(x), 0f, 0f));
            }
            /// <summary>A wheel of the fine mesh: a round tyre (S sides, smooth tread), its dark sidewall and a pale rim disc set in a little.</summary>
            public void WheelFine(float x, float z, float r, float w, int S)
            {
                var tyre = new Color(0.055f, 0.055f, 0.06f, 0.8f); var wall = new Color(0.09f, 0.09f, 0.095f, 0.8f);
                var rim = new Color(0.60f, 0.61f, 0.63f, 0.8f); var lip = new Color(0.26f, 0.27f, 0.28f, 0.8f); var hub = new Color(0.36f, 0.37f, 0.39f, 0.8f);
                float sg = Mathf.Sign(x), xi = x - sg * w * 0.5f, xo = x + sg * w * 0.5f, xr = xo - sg * 0.03f, rr = r * 0.66f;
                var side = new Vector3(sg, 0f, 0f); var c = new Vector3(xr, r, z);
                for (int i = 0; i < S; i++)
                {
                    float a0 = i * Mathf.PI * 2f / S, a1 = (i + 1) * Mathf.PI * 2f / S;
                    Vector3 d0 = new Vector3(0f, Mathf.Sin(a0), Mathf.Cos(a0)), d1 = new Vector3(0f, Mathf.Sin(a1), Mathf.Cos(a1)), dm = (d0 + d1).normalized;
                    Vector3 o0 = new Vector3(0f, r, z) + d0 * r, o1 = new Vector3(0f, r, z) + d1 * r, i0 = new Vector3(0f, r, z) + d0 * rr, i1 = new Vector3(0f, r, z) + d1 * rr;
                    // tread
                    TriN(new Vector3(xi, o0.y, o0.z), new Vector3(xo, o0.y, o0.z), new Vector3(xo, o1.y, o1.z), d0, d0, d1, tyre, dm);
                    TriN(new Vector3(xi, o0.y, o0.z), new Vector3(xo, o1.y, o1.z), new Vector3(xi, o1.y, o1.z), d0, d1, d1, tyre, dm);
                    // sidewall ring, a little rounded towards the tread
                    Vector3 n0 = (side * 0.8f + d0 * 0.6f).normalized, n1 = (side * 0.8f + d1 * 0.6f).normalized;
                    TriN(new Vector3(xo, o0.y, o0.z), new Vector3(xo, o1.y, o1.z), new Vector3(xo, i1.y, i1.z), n0, n1, side, wall, side);
                    TriN(new Vector3(xo, o0.y, o0.z), new Vector3(xo, i1.y, i1.z), new Vector3(xo, i0.y, i0.z), n0, side, side, wall, side);
                    // the rim's lip from the sidewall down to the disc, then the disc with its hub
                    Quad(new Vector3(xo, i0.y, i0.z), new Vector3(xr, i0.y, i0.z), new Vector3(xr, i1.y, i1.z), new Vector3(xo, i1.y, i1.z), lip, -dm);
                    Vector3 h0 = c + d0 * rr * 0.28f, h1 = c + d1 * rr * 0.28f;
                    Quad(new Vector3(xr, h0.y, h0.z), new Vector3(xr, i0.y, i0.z), new Vector3(xr, i1.y, i1.z), new Vector3(xr, h1.y, h1.z), rim, side);
                    Tri(c + side * 0.012f, new Vector3(xr, h0.y, h0.z) + side * 0.006f, new Vector3(xr, h1.y, h1.z) + side * 0.006f, hub, side);
                }
            }
            public Mesh ToMesh(string name)
            {
                var m = new Mesh { name = name }; m.SetVertices(V); m.SetNormals(N); m.SetColors(Cl); m.SetUVs(1, U1); m.SetTriangles(T, 0);
                m.bounds = new Bounds(new Vector3(0f, 2f, 0f), new Vector3(16f, 8f, 24f));        // glow sprites grow in the shader
                return m;
            }
        }
        static readonly Color Paint = new Color(1f, 1f, 1f, 1f), PaintD = new Color(0.82f, 0.82f, 0.82f, 1f), Glass = new Color(0.05f, 0.06f, 0.07f, 0.6f),
            Trim = new Color(0.13f, 0.135f, 0.14f, 0.8f);
        static Vector2[] Pr(params float[] zy) { var r = new Vector2[zy.Length / 2]; for (int i = 0; i < r.Length; i++) r[i] = new Vector2(zy[i * 2], zy[i * 2 + 1]); return r; }

        static Mesh VehicleMesh(int kind)
        {
            var b = new MB();
            switch (kind)
            {
                case Sedan:
                {
                    // 4.5 × 1.8 × 1.45 m: body with a sloped bonnet and boot, glasshouse narrower at the roof
                    var body = Pr(-2.25f, 0.30f, 2.25f, 0.30f, 2.29f, 0.62f, 2.15f, 0.80f, 1.05f, 0.92f, -1.62f, 0.95f, -2.22f, 0.88f, -2.30f, 0.55f);
                    b.Extrude(body, 0.9f, 0.88f, i => i == 0 ? Trim : i == 1 || i == 7 ? PaintD : Paint, Paint);
                    var gh = Pr(1.05f, 0.91f, 0.22f, 1.44f, -1.02f, 1.42f, -1.60f, 0.94f);
                    b.Extrude(gh, 0.84f, 0.66f, i => i == 1 ? Paint : i == 3 ? Paint : Glass, Glass);
                    foreach (float x in new[] { -0.80f, 0.80f }) foreach (float z in new[] { 1.38f, -1.38f }) b.Wheel(x, z, 0.32f, 0.22f);
                    b.Lamp(0.42f, 0.80f, 0.60f, 0.72f, 2.25f, true, false); b.Lamp(0.48f, 0.86f, 0.66f, 0.80f, -2.27f, false, true);
                    b.Glows(0.62f, 0.66f, 2.25f, 0.68f, 0.73f, -2.27f, 6.5f);
                    break;
                }
                case Suv:
                {
                    // 4.6 × 1.85 × 1.7 m crossover
                    var body = Pr(-2.28f, 0.38f, 2.28f, 0.38f, 2.32f, 0.78f, 2.18f, 1.00f, 1.25f, 1.08f, -2.22f, 1.12f, -2.32f, 0.78f);
                    b.Extrude(body, 0.93f, 0.92f, i => i == 0 ? Trim : i == 1 || i == 6 ? PaintD : Paint, Paint);
                    var gh = Pr(1.22f, 1.07f, 0.40f, 1.68f, -2.02f, 1.66f, -2.20f, 1.10f);
                    b.Extrude(gh, 0.88f, 0.74f, i => i == 1 || i == 3 ? Paint : Glass, Glass);
                    b.Box(new Vector3(0f, 0.30f, 0f), new Vector3(1.7f, 0.16f, 3.0f), Trim);
                    foreach (float x in new[] { -0.82f, 0.82f }) foreach (float z in new[] { 1.42f, -1.42f }) b.Wheel(x, z, 0.36f, 0.24f);
                    b.Lamp(0.45f, 0.84f, 0.80f, 0.92f, 2.30f, true, false); b.Lamp(0.52f, 0.90f, 0.86f, 1.00f, -2.31f, false, true);
                    b.Glows(0.64f, 0.86f, 2.30f, 0.71f, 0.93f, -2.31f, 6.5f);
                    break;
                }
                case Van:
                {
                    // 5.6 × 2.0 × 2.3 m minibus / delivery van
                    var low = Pr(-2.8f, 0.38f, 2.8f, 0.38f, 2.82f, 0.95f, 2.35f, 1.12f, -2.8f, 1.12f);
                    b.Extrude(low, 1.0f, 1.0f, i => i == 0 ? Trim : Paint, Paint);
                    var band = Pr(2.35f, 1.10f, -2.8f, 1.10f, -2.8f, 1.86f, 1.55f, 1.86f);
                    b.Extrude(band, 1.0f, 0.97f, i => i == 0 ? Paint : Glass, Glass);
                    var roof = Pr(1.55f, 1.84f, -2.8f, 1.84f, -2.78f, 2.30f, 1.30f, 2.30f);
                    b.Extrude(roof, 0.97f, 0.95f, i => Paint, Paint);
                    foreach (float x in new[] { -0.86f, 0.86f }) foreach (float z in new[] { 1.85f, -1.75f }) b.Wheel(x, z, 0.36f, 0.24f);
                    b.Lamp(0.55f, 0.92f, 0.80f, 0.94f, 2.81f, true, false); b.Lamp(0.70f, 0.96f, 0.70f, 1.05f, -2.81f, false, true);
                    b.Glows(0.74f, 0.87f, 2.81f, 0.83f, 0.88f, -2.81f, 7f);
                    break;
                }
                case Bus:
                {
                    // 12 × 2.55 × 3.2 m low-floor city bus: livery below, a long glass band, white roof with its climate unit
                    var low = Pr(-6f, 0.32f, 6f, 0.32f, 6.02f, 1.10f, -6f, 1.10f);
                    b.Extrude(low, 1.27f, 1.27f, i => i == 0 ? Trim : Paint, Paint);
                    var band = Pr(6.02f, 1.08f, -6f, 1.08f, -6f, 2.62f, 5.92f, 2.80f);
                    b.Extrude(band, 1.27f, 1.27f, i => Glass, Glass);
                    var white = new Color(0.93f, 0.93f, 0.92f, 0.8f);
                    var roof = Pr(5.92f, 2.62f, -6f, 2.60f, -6f, 3.02f, 5.85f, 3.02f);
                    b.Extrude(roof, 1.27f, 1.24f, i => white, white);
                    b.Box(new Vector3(0f, 3.12f, 0.8f), new Vector3(1.9f, 0.22f, 3.4f), new Color(0.80f, 0.81f, 0.82f, 0.8f));
                    b.Box(new Vector3(0f, 2.90f, 6.03f), new Vector3(1.6f, 0.22f, 0.04f), new Color(0.95f, 0.62f, 0.12f, 0.4f));     // route display
                    foreach (float x in new[] { -1.06f, 1.06f }) foreach (float z in new[] { 3.65f, -2.45f }) b.Wheel(x, z, 0.50f, 0.30f);
                    b.Lamp(0.70f, 1.15f, 0.55f, 0.72f, 6.02f, true, false); b.Lamp(0.85f, 1.18f, 0.55f, 1.05f, -6.0f, false, true);
                    b.Glows(0.92f, 0.63f, 6.02f, 1.02f, 0.8f, -6.0f, 8f);
                    break;
                }
                default:
                {
                    // 9.5 m rigid truck: cab in the paint, white box body, dark chassis
                    b.Box(new Vector3(0f, 0.72f, 0f), new Vector3(2.0f, 0.40f, 9.3f), Trim);
                    var cabL = Pr(2.55f, 0.90f, 4.75f, 0.90f, 4.75f, 1.95f, 2.55f, 1.95f);
                    b.Extrude(cabL, 1.2f, 1.2f, i => Paint, Paint);
                    var cabG = Pr(2.55f, 1.93f, 4.75f, 1.93f, 4.55f, 2.70f, 2.55f, 2.70f);
                    b.Extrude(cabG, 1.2f, 1.14f, i => i == 1 ? Glass : Paint, Glass);
                    var cabR = Pr(2.55f, 2.68f, 4.55f, 2.68f, 4.45f, 2.98f, 2.55f, 2.98f);
                    b.Extrude(cabR, 1.14f, 1.1f, i => Paint, Paint);
                    b.Box(new Vector3(0f, 2.35f, -1.15f), new Vector3(2.5f, 2.80f, 7.1f), new Color(0.88f, 0.88f, 0.87f, 0.8f));
                    foreach (float x in new[] { -1.02f, 1.02f }) foreach (float z in new[] { 3.65f, -2.55f, -3.70f }) b.Wheel(x, z, 0.50f, 0.32f);
                    b.Lamp(0.70f, 1.10f, 1.00f, 1.18f, 4.75f, true, false); b.Lamp(0.85f, 1.18f, 0.80f, 1.00f, -4.71f, false, true);
                    b.Glows(0.90f, 1.09f, 4.75f, 1.02f, 0.9f, -4.71f, 8f);
                    break;
                }
            }
            return b.ToMesh("Film traffic " + kind);
        }

        // ------------------------------------------------------------------ the fine mesh
        static float Lin(float[] zk, float[] v, float z)
        {
            // zk runs front to back (descending)
            if (z >= zk[0]) return v[0];
            for (int i = 0; i + 1 < zk.Length; i++) if (z >= zk[i + 1]) return Mathf.Lerp(v[i], v[i + 1], Mathf.InverseLerp(zk[i], zk[i + 1], z));
            return v[v.Length - 1];
        }
        /// <summary>Stations of a loft: the key stations, the wheel arches (7 per arch and one each side) and any extra ones, front to back.</summary>
        static float[] Stations(float[] keys, float[] wheels, float R, params float[] extra)
        {
            var l = new List<float>(keys); l.AddRange(extra);
            if (wheels != null)
                foreach (float zw in wheels)
                {
                    for (int t = 0; t <= 6; t++) l.Add(zw + R * Mathf.Cos(Mathf.PI * t / 6f));
                    l.Add(zw + R + 0.02f); l.Add(zw - R - 0.02f);
                }
            l.Sort((a, b) => b.CompareTo(a));
            var r = new List<float>(); foreach (float z in l) if (z <= keys[0] + 1e-4f && z >= keys[keys.Length - 1] - 1e-4f && (r.Count == 0 || r[r.Count - 1] - z > 0.004f)) r.Add(z);
            return r.ToArray();
        }
        /// <summary>Height of the wheel arch's top edge at z (no arch: -1).</summary>
        static float ArchY(float z, float[] wheels, float r, float R)
        {
            float y = -1f;
            if (wheels != null) foreach (float zw in wheels) { float d = z - zw; if (Mathf.Abs(d) <= R + 1e-3f) y = Mathf.Max(y, r + Mathf.Sqrt(Mathf.Max(R * R - d * d, 0f))); }
            return y;
        }
        /// <summary>A body cross-section: the underside, the wheel well (an inner wall and a roof over the tyre, collapsed where there is no
        /// wheel), the sill, then the flank and shoulder points (dx from the half width w, y), the crown on the centre line.
        /// Half segments: 0 underside, 1 well wall, 2 well roof, 3 sill / arch lip, 4.. flank and shoulder, last = top to the centre.</summary>
        static Vector2[] BodySec(float w, float yb, float arch, float tw, float[] dx, float[] y, float crown)
        {
            bool well = arch > 0f; float ys = well ? Mathf.Max(arch, yb + 0.005f) : yb, ysA = well ? ys : yb + 0.01f;
            int S = dx.Length; var R = new Vector2[4 + S];
            R[0] = new Vector2(w - tw - 0.07f, yb); R[1] = new Vector2(w - tw - 0.05f, ysA); R[2] = new Vector2(w - 0.08f, ys);
            float y4 = ys + 0.05f; R[3] = new Vector2(w - 0.01f, y4);
            float prev = y4;
            for (int k = 0; k < S; k++) { float yy = Mathf.Max(y[k], prev + (k == S - 1 ? 0.01f : 0.025f)); R[4 + k] = new Vector2(w + dx[k], yy); prev = yy; }
            var s = new Vector2[2 + 2 * R.Length]; int m = 0;
            s[m++] = new Vector2(0f, yb);
            for (int k = 0; k < R.Length; k++) s[m++] = R[k];
            s[m++] = new Vector2(0f, prev + crown);
            for (int k = R.Length - 1; k >= 0; k--) s[m++] = new Vector2(-R[k].x, R[k].y);
            return s;
        }
        static int Half(int seg, int n) { int h = n / 2; return seg < h ? seg : n - 1 - seg; }
        /// <summary>A glasshouse cross-section: bottom on the body (half width wB at yB), the side glass up to the roof edge (wT, yT),
        /// a bevel, the roof crown. ymid > 0 adds a point where the glass band ends below a painted roof band (vans).
        /// Half segments: 0 underside (hidden), 1 side glass, [2 roof band], then bevel, top.</summary>
        static Vector2[] CabSec(float wB, float yB, float wT, float yT, float ymid)
        {
            float y2 = Mathf.Max(yT - 0.07f, yB + 0.004f), y3 = Mathf.Max(yT, y2 + 0.003f);
            var R = new List<Vector2> { new Vector2(wB, yB) };
            if (ymid > 0f) R.Add(new Vector2(wB - 0.015f, Mathf.Clamp(ymid, yB + 0.002f, y2 - 0.002f)));
            R.Add(new Vector2(wT, y2)); R.Add(new Vector2(wT - 0.08f, y3));
            var s = new List<Vector2> { new Vector2(0f, yB) }; s.AddRange(R); s.Add(new Vector2(0f, y3 + 0.02f));
            for (int k = R.Count - 1; k >= 0; k--) s.Add(new Vector2(-R[k].x, R[k].y));
            return s.ToArray();
        }

        static readonly Color PlateC = new Color(0.90f, 0.90f, 0.88f, 0.8f), Grille = new Color(0.06f, 0.06f, 0.065f, 0.8f), Mirror = new Color(1f, 1f, 1f, 1f);

        /// <summary>The fine mesh of a vehicle kind: a lofted body with a shaped bonnet and rounded edges, wheel arches, a glasshouse with
        /// sloped windscreen and rear glass and pillars, round tyres with rims, lamps, grille, plates and mirrors.</summary>
        static Mesh FineMesh(int kind)
        {
            var b = new MB();
            switch (kind)
            {
                case Sedan: case Suv:
                {
                    bool suv = kind == Suv;
                    // body: front to back, the bumper face, the bonnet rising to the windscreen, the flank, the boot
                    float[] zk = suv ? new[] { 2.30f, 2.25f, 2.12f, 1.80f, 1.30f, 1.08f, -1.00f, -1.95f, -2.20f, -2.30f }
                                     : new[] { 2.27f, 2.22f, 2.10f, 1.80f, 1.30f, 0.95f, -1.00f, -1.70f, -2.05f, -2.22f, -2.29f };
                    float[] ybk = suv ? new[] { 0.44f, 0.38f, 0.36f, 0.36f, 0.37f, 0.38f, 0.38f, 0.38f, 0.40f, 0.46f }
                                      : new[] { 0.36f, 0.30f, 0.27f, 0.27f, 0.27f, 0.28f, 0.28f, 0.28f, 0.28f, 0.31f, 0.38f };
                    float[] ytk = suv ? new[] { 0.80f, 0.88f, 0.93f, 0.97f, 1.02f, 1.05f, 1.08f, 1.10f, 1.08f, 1.00f }
                                      : new[] { 0.64f, 0.71f, 0.76f, 0.80f, 0.86f, 0.91f, 0.93f, 0.95f, 0.95f, 0.90f, 0.82f };
                    float[] wk = suv ? new[] { 0.80f, 0.88f, 0.91f, 0.92f, 0.925f, 0.925f, 0.925f, 0.925f, 0.91f, 0.84f }
                                     : new[] { 0.76f, 0.84f, 0.88f, 0.895f, 0.90f, 0.90f, 0.90f, 0.90f, 0.89f, 0.86f, 0.78f };
                    float r = suv ? 0.36f : 0.32f, tw = suv ? 0.23f : 0.21f, R = r + 0.07f;
                    float[] wh = suv ? new[] { 1.42f, -1.38f } : new[] { 1.38f, -1.33f };
                    var zs = Stations(zk, wh, R); var sec = new Vector2[zs.Length][];
                    for (int i = 0; i < zs.Length; i++)
                    {
                        float z = zs[i], yb = Lin(zk, ybk, z), yt = Lin(zk, ytk, z), w = Lin(zk, wk, z);
                        sec[i] = BodySec(w, yb, ArchY(z, wh, r, R), tw, new[] { 0f, -0.02f, -0.10f }, new[] { Mathf.Lerp(yb, yt, 0.45f), yt - 0.07f, yt }, 0.015f);
                    }
                    int n = sec[0].Length;
                    b.Loft(zs, sec, (s, iv) => { int h = Half(s, n); return h <= 2 ? Trim : h == 3 ? (suv ? Trim : PaintD) : Paint; }, Paint, Paint);
                    // glasshouse: windscreen, front door glass, B pillar, rear door glass, (SUV: C pillar, quarter glass), rear glass
                    float[] cz = suv ? new[] { 1.08f, 0.20f, -0.42f, -0.54f, -1.25f, -1.36f, -1.95f, -2.18f } : new[] { 0.97f, 0.05f, -0.50f, -0.61f, -1.10f, -1.72f };
                    float[] cyT = suv ? new[] { 1.05f, 1.66f, 1.68f, 1.68f, 1.67f, 1.67f, 1.65f, 1.10f } : new[] { 0.90f, 1.42f, 1.44f, 1.44f, 1.42f, 0.95f };
                    float wB = suv ? 0.88f : 0.86f, wT = suv ? 0.77f : 0.68f; var cs = new Vector2[cz.Length][];
                    for (int i = 0; i < cz.Length; i++)
                    {
                        float yB = Lin(zk, ytk, cz[i]) - 0.025f, end = i == 0 || i == cz.Length - 1 ? 1f : 0f;
                        cs[i] = CabSec(wB - 0.02f * end, yB, Mathf.Lerp(wT, wB - 0.06f, end), cyT[i], 0f);
                    }
                    int cn = cs[0].Length, last = cz.Length - 2;
                    b.Loft(cz, cs, (s, iv) =>
                    {
                        int h = Half(s, cn);
                        if (h == 0) return Trim;
                        if (h == 1) return iv == 0 || iv == 1 || iv == 3 || (suv && iv == 5) ? Glass : Paint;      // side glass, pillars
                        if (h == 2) return Paint;                                                                     // roof edge, A and C pillars
                        return iv == 0 || iv == last ? Glass : Paint;                                                 // windscreen, rear glass, roof
                    }, null, null);
                    if (suv) foreach (float sg in new[] { -1f, 1f }) b.Box(new Vector3(sg * 0.60f, 1.71f, -0.55f), new Vector3(0.05f, 0.05f, 2.0f), Trim);   // roof rails
                    // mirrors at the foot of the A pillars
                    float mz = suv ? 0.95f : 0.84f, my = (suv ? 1.12f : 0.98f);
                    foreach (float sg in new[] { -1f, 1f }) { b.Box(new Vector3(sg * (wB + 0.08f), my, mz), new Vector3(0.12f, 0.09f, 0.08f), Mirror); b.Box(new Vector3(sg * (wB + 0.005f), my - 0.02f, mz + 0.01f), new Vector3(0.06f, 0.04f, 0.05f), Trim); }
                    // front: lamps, grille, plate; back: tail lamps, plate
                    float zf = zk[0] + 0.006f, zb = zk[zk.Length - 1] - 0.006f;
                    if (suv)
                    {
                        b.Lamp(0.40f, 0.72f, 0.64f, 0.73f, zf - 0.012f, true, false); b.Panel(-0.34f, 0.34f, 0.56f, 0.74f, zf, true, Grille); b.Panel(-0.26f, 0.26f, 0.46f, 0.55f, zf, true, PlateC);
                        b.Lamp(0.50f, 0.80f, 0.80f, 0.92f, zb + 0.012f, false, true); b.Panel(-0.26f, 0.26f, 0.56f, 0.66f, zb, false, PlateC);
                        b.Glows(0.56f, 0.68f, zk[0], 0.65f, 0.86f, zk[zk.Length - 1], 6.5f);
                    }
                    else
                    {
                        b.Lamp(0.36f, 0.68f, 0.50f, 0.60f, zf - 0.012f, true, false); b.Panel(-0.30f, 0.30f, 0.49f, 0.60f, zf, true, Grille); b.Panel(-0.26f, 0.26f, 0.37f, 0.47f, zf, true, PlateC);
                        b.Lamp(0.44f, 0.72f, 0.62f, 0.72f, zb + 0.012f, false, true); b.Panel(-0.26f, 0.26f, 0.45f, 0.56f, zb, false, PlateC);
                        b.Glows(0.52f, 0.55f, zk[0], 0.58f, 0.67f, zk[zk.Length - 1], 6.5f);
                    }
                    foreach (float sg in new[] { -1f, 1f }) foreach (float z in wh) b.WheelFine(sg * (0.90f - 0.01f - tw * 0.5f), z, r, tw, 14);
                    b.Under(0.86f, zk[0] - 0.12f, zk[zk.Length - 1] + 0.12f);
                    break;
                }
                case Van:
                {
                    // 5.6 × 2.0 × 2.3 m minibus: a short bonnet, a raked windscreen, a tall body with a row of windows
                    float[] zk = { 2.82f, 2.76f, 2.55f, 2.20f, 1.90f, -2.70f, -2.80f };
                    float[] ybk = { 0.44f, 0.38f, 0.36f, 0.36f, 0.36f, 0.38f, 0.44f };
                    float[] ytk = { 0.95f, 1.02f, 1.10f, 1.15f, 1.16f, 1.16f, 1.12f };
                    float[] wk = { 0.90f, 0.97f, 1.00f, 1.00f, 1.00f, 1.00f, 0.96f };
                    float r = 0.36f, tw = 0.23f, R = r + 0.07f; float[] wh = { 1.85f, -1.75f };
                    var zs = Stations(zk, wh, R); var sec = new Vector2[zs.Length][];
                    for (int i = 0; i < zs.Length; i++)
                    {
                        float z = zs[i], yb = Lin(zk, ybk, z), yt = Lin(zk, ytk, z), w = Lin(zk, wk, z);
                        sec[i] = BodySec(w, yb, ArchY(z, wh, r, R), tw, new[] { 0f, -0.02f, -0.10f }, new[] { Mathf.Lerp(yb, yt, 0.45f), yt - 0.07f, yt }, 0.01f);
                    }
                    int n = sec[0].Length;
                    b.Loft(zs, sec, (s, iv) => { int h = Half(s, n); return h <= 2 ? Trim : h == 3 ? PaintD : Paint; }, Paint, Paint);
                    float[] cz = { 2.20f, 1.55f, 1.45f, 0.95f, 0.85f, -0.45f, -0.55f, -1.75f, -1.85f, -2.70f, -2.78f };
                    var cs = new Vector2[cz.Length][];
                    for (int i = 0; i < cz.Length; i++) cs[i] = CabSec(i == 0 ? 0.97f : 0.99f, 1.13f, i == 0 ? 0.95f : 0.97f, i == 0 ? 1.15f : 2.30f, 1.98f);
                    int cn = cs[0].Length;
                    b.Loft(cz, cs, (s, iv) =>
                    {
                        int h = Half(s, cn);
                        if (h == 0) return Trim;
                        if (h == 1) return iv % 2 == 0 && iv < 9 ? Glass : Paint;     // the row of windows between the pillars
                        if (h == 4) return iv == 0 ? Glass : Paint;                  // windscreen
                        return Paint;
                    }, null, Paint);
                    float zf = zk[0] + 0.006f, zb = -2.806f;
                    b.Lamp(0.50f, 0.82f, 0.74f, 0.86f, zf - 0.012f, true, false); b.Panel(-0.42f, 0.42f, 0.62f, 0.84f, zf, true, Grille); b.Panel(-0.26f, 0.26f, 0.46f, 0.56f, zf, true, PlateC);
                    b.Lamp(0.70f, 0.90f, 0.70f, 1.05f, zb + 0.012f, false, true); b.Panel(-0.26f, 0.26f, 0.50f, 0.60f, zb, false, PlateC);
                    foreach (float sg in new[] { -1f, 1f }) b.Panel(sg * 0.06f, sg * 0.86f, 1.40f, 2.00f, -2.786f, false, Glass);                  // rear door windows
                    b.Panel(-0.012f, 0.012f, 1.16f, 2.24f, -2.787f, false, Trim);
                    foreach (float sg in new[] { -1f, 1f }) { b.Box(new Vector3(sg * 1.10f, 1.30f, 2.05f), new Vector3(0.05f, 0.30f, 0.16f), Trim); b.Box(new Vector3(sg * 1.03f, 1.38f, 2.08f), new Vector3(0.10f, 0.04f, 0.04f), Trim); }
                    b.Glows(0.66f, 0.80f, zk[0], 0.80f, 0.88f, -2.80f, 7f);
                    foreach (float sg in new[] { -1f, 1f }) foreach (float z in wh) b.WheelFine(sg * (1.0f - 0.01f - tw * 0.5f), z, r, tw, 14);
                    b.Under(0.96f, 2.70f, -2.70f);
                    break;
                }
                case Bus:
                {
                    // 12 × 2.55 × 3.2 m low-floor city bus: livery below, a band of windows with pillars, a white roof with its climate unit,
                    // a tall windscreen, two doors on the right (pavement) side
                    float[] zk = { 6.00f, 5.93f, 5.80f, -5.88f, -6.00f };
                    float[] wk = { 1.18f, 1.26f, 1.275f, 1.275f, 1.20f };
                    float[] ybk = { 0.40f, 0.34f, 0.32f, 0.34f, 0.40f };
                    float[] ytk = { 2.98f, 3.04f, 3.05f, 3.05f, 2.98f };
                    float r = 0.50f, tw = 0.30f, R = r + 0.07f; float[] wh = { 3.65f, -2.45f };
                    var ex = new List<float> { 5.70f, 5.60f, -5.62f, -5.72f };
                    var pil = new List<float> { 5.70f, -5.62f };
                    for (int k = 0; k < 7; k++) { float zp = 4.20f - k * 1.45f; ex.Add(zp + 0.06f); ex.Add(zp - 0.06f); pil.Add(zp + 0.06f); }
                    var zs = Stations(zk, wh, R, ex.ToArray()); var sec = new Vector2[zs.Length][];
                    for (int i = 0; i < zs.Length; i++)
                    {
                        float z = zs[i], yb = Lin(zk, ybk, z), yt = Lin(zk, ytk, z), w = Lin(zk, wk, z);
                        sec[i] = BodySec(w, yb, ArchY(z, wh, r, R), tw, new[] { 0f, 0f, -0.04f, -0.14f }, new[] { 1.15f, 2.68f, yt - 0.10f, yt }, 0.02f);
                    }
                    int n = sec[0].Length; var white = new Color(0.93f, 0.93f, 0.92f, 0.8f);
                    // a pillar interval starts at one of the pillar stations; the first and last intervals are the bevels of the ends
                    b.Loft(zs, sec, (s, iv) =>
                    {
                        int h = Half(s, n);
                        if (h <= 2) return Trim;
                        if (h <= 4) return Paint;
                        if (h == 5)
                        {
                            float z0 = zs[iv]; bool pillar = iv == 0 || iv >= zs.Length - 2 || z0 > 5.69f || z0 < -5.61f;
                            foreach (float p in pil) if (Mathf.Abs(z0 - p) < 0.003f) pillar = true;
                            return pillar ? Paint : Glass;
                        }
                        return white;
                    }, Paint, Paint);
                    float zf = 6.006f, zb = -6.006f;
                    b.Panel(-1.08f, 1.08f, 1.10f, 2.74f, zf, true, Glass);                                       // windscreen
                    b.Box(new Vector3(0f, 2.86f, 6.0f), new Vector3(1.6f, 0.18f, 0.03f), new Color(0.95f, 0.62f, 0.12f, 0.4f));     // route display
                    b.Panel(-1.12f, 1.12f, 0.40f, 0.56f, zf, true, Grille);                                       // bumper
                    b.Lamp(0.74f, 1.06f, 0.62f, 0.80f, zf - 0.012f, true, false);
                    b.Panel(-0.95f, 0.95f, 2.05f, 2.74f, zb, false, Glass); b.Panel(-0.80f, 0.80f, 0.60f, 1.10f, zb, false, Grille); b.Panel(-1.12f, 1.12f, 0.40f, 0.54f, zb, false, Grille);
                    b.Lamp(0.86f, 1.10f, 0.62f, 1.10f, zb + 0.012f, false, true);
                    // doors on the right side: glass leaves with a dark seam
                    foreach (var d in new[] { new Vector2(4.40f, 5.52f), new Vector2(-0.02f, 1.16f) })
                    {
                        b.SidePanel(1.284f, d.x, d.y, 0.38f, 2.64f, Glass);
                        b.SidePanel(1.288f, (d.x + d.y) * 0.5f - 0.015f, (d.x + d.y) * 0.5f + 0.015f, 0.38f, 2.64f, Trim);
                    }
                    // climate unit on the roof, its edges rounded
                    float[] az = { 2.50f, 2.42f, -0.82f, -0.90f }, aw = { 0.88f, 0.95f, 0.95f, 0.88f }, at = { 3.22f, 3.27f, 3.27f, 3.22f };
                    var acs = new Vector2[az.Length][];
                    for (int i = 0; i < az.Length; i++) acs[i] = BodySec(aw[i], 3.02f, -1f, 0.02f, new[] { 0f, -0.04f, -0.10f }, new[] { 3.12f, at[i] - 0.05f, at[i] }, 0.01f);
                    var acc = new Color(0.80f, 0.81f, 0.82f, 0.8f);
                    b.Loft(az, acs, (s, iv) => acc, acc, acc);
                    foreach (float sg in new[] { -1f, 1f }) { b.Box(new Vector3(sg * 1.42f, 2.25f, 5.85f), new Vector3(0.07f, 0.40f, 0.14f), Trim); b.Box(new Vector3(sg * 1.34f, 2.56f, 5.88f), new Vector3(0.18f, 0.04f, 0.04f), Trim); }
                    b.Glows(0.92f, 0.71f, 6.0f, 0.98f, 0.86f, -6.0f, 8f);
                    foreach (float sg in new[] { -1f, 1f }) foreach (float z in wh) b.WheelFine(sg * (1.275f - 0.01f - tw * 0.5f), z, r, tw, 16);
                    b.Under(1.22f, 5.85f, -5.85f);
                    break;
                }
                default:
                {
                    // 9.5 m rigid truck: a cab in the paint (windscreen, grille, side windows), a dark chassis, a white box body
                    float[] zk = { 4.78f, 4.72f, 2.60f, 2.52f };
                    float[] wk = { 1.14f, 1.22f, 1.22f, 1.18f };
                    float[] ybk = { 0.62f, 0.55f, 0.55f, 0.60f };
                    float[] ytk = { 2.92f, 3.00f, 3.00f, 2.94f };
                    float r = 0.50f, tw = 0.30f, R = r + 0.08f; float[] wf = { 3.65f };
                    var zs = Stations(zk, wf, R, 4.62f, 3.45f); var sec = new Vector2[zs.Length][];
                    for (int i = 0; i < zs.Length; i++)
                    {
                        float z = zs[i], yb = Lin(zk, ybk, z), yt = Lin(zk, ytk, z), w = Lin(zk, wk, z);
                        sec[i] = BodySec(w, yb, ArchY(z, wf, r, R), tw, new[] { 0f, -0.05f, -0.14f }, new[] { 1.90f, yt - 0.10f, yt }, 0.02f);
                    }
                    int n = sec[0].Length;
                    b.Loft(zs, sec, (s, iv) =>
                    {
                        int h = Half(s, n);
                        if (h <= 2) return Trim;
                        if (h == 5) return zs[iv] <= 4.621f && zs[iv] > 3.451f ? Glass : Paint;     // the door's window
                        return Paint;
                    }, Paint, Paint);
                    float zf = 4.786f;
                    b.Panel(-1.05f, 1.05f, 1.95f, 2.78f, zf, true, Glass); b.Panel(-0.75f, 0.75f, 1.05f, 1.70f, zf, true, Grille); b.Panel(-1.18f, 1.18f, 0.58f, 0.86f, zf, true, Grille);
                    b.Panel(-0.26f, 0.26f, 0.88f, 0.99f, zf + 0.004f, true, PlateC);
                    b.Lamp(0.80f, 1.08f, 0.95f, 1.12f, zf - 0.012f, true, false);
                    foreach (float sg in new[] { -1f, 1f }) { b.Box(new Vector3(sg * 1.38f, 2.30f, 4.55f), new Vector3(0.07f, 0.45f, 0.15f), Trim); b.Box(new Vector3(sg * 1.29f, 2.60f, 4.58f), new Vector3(0.16f, 0.04f, 0.04f), Trim); }
                    // chassis, side guards, fuel tank, rear bumper
                    b.Box(new Vector3(0f, 0.80f, -1.05f), new Vector3(1.6f, 0.30f, 7.4f), Trim);
                    foreach (float sg in new[] { -1f, 1f }) b.Box(new Vector3(sg * 1.05f, 0.72f, 0.25f), new Vector3(0.04f, 0.22f, 4.1f), new Color(0.35f, 0.36f, 0.37f, 0.8f));
                    b.Box(new Vector3(0.80f, 0.78f, 1.6f), new Vector3(0.40f, 0.45f, 1.0f), new Color(0.62f, 0.63f, 0.64f, 0.8f));
                    b.Box(new Vector3(0f, 0.62f, -4.62f), new Vector3(2.3f, 0.14f, 0.12f), Trim);
                    // the box body, rounded at its edges, with the seam of its rear doors
                    float[] bz = { 2.40f, 2.36f, -4.66f, -4.72f }, bw = { 1.20f, 1.25f, 1.25f, 1.20f }, bt = { 3.70f, 3.75f, 3.75f, 3.70f };
                    var bs = new Vector2[bz.Length][];
                    for (int i = 0; i < bz.Length; i++) bs[i] = BodySec(bw[i], 1.10f, -1f, 0.02f, new[] { 0f, -0.05f, -0.12f }, new[] { 1.50f, bt[i] - 0.07f, bt[i] }, 0.0f);
                    var box = new Color(0.90f, 0.90f, 0.89f, 0.8f);
                    b.Loft(bz, bs, (s, iv) => box, box, box);
                    b.Panel(-0.015f, 0.015f, 1.16f, 3.64f, -4.726f, false, Trim);
                    b.Panel(-1.15f, 1.15f, 1.12f, 1.20f, -4.726f, false, Trim);
                    b.Lamp(0.86f, 1.12f, 1.24f, 1.40f, -4.714f, false, true);
                    foreach (float sg in new[] { -1f, 1f }) b.Box(new Vector3(sg * 1.02f, 1.06f, -3.12f), new Vector3(0.36f, 0.05f, 2.3f), Trim);     // mudguards
                    b.Glows(0.93f, 1.03f, 4.78f, 1.0f, 1.32f, -4.72f, 8f);
                    b.Under(1.18f, 4.65f, -4.60f);
                    foreach (float sg in new[] { -1f, 1f }) { b.WheelFine(sg * (1.22f - 0.01f - tw * 0.5f), 3.65f, r, tw, 16); foreach (float z in new[] { -2.55f, -3.70f }) b.WheelFine(sg * (1.05f - tw * 0.5f), z, r, tw, 16); }
                    break;
                }
            }
            return b.ToMesh("Film traffic fine " + kind);
        }
    }
}
