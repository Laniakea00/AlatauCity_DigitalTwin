using System;
using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The LRT of the master plan in 3D: a double-track viaduct along the planned line (trunk Gate → Green and two branches to
    /// the west), piers, overhead line, stations with canopies and lifts, and trains running between the stations.
    /// Opens by phase and year of the scenario (construction.json → lrt.phase_year): piers 2 years before, the deck 1 year before, trains
    /// from the opening year. The route comes from the plan's LRT layer (Resources/Landmarks/lrt_routes.json).
    /// The new map data (tools/map CONTRACT §6) adds per route "sec" [from_m, to_m, code, …] (0 ground, 1 elevated, 2 tunnel, chainage
    /// along pts), optional "h" (rail level per point) and "ends" [start, end] (0 terminus, 1 depot, 2 continues into a neighbour: nothing drawn): a ground section is a fenced track
    /// bed on the ground (a ramp between retaining walls where it climbs to a viaduct), a tunnel is not drawn (a portal at each mouth,
    /// trains hidden inside), stations stand only on ground and elevated sections. Without "sec" the whole route is the viaduct of today.</summary>
    public class LrtLayer : MonoBehaviour
    {
        public static LrtLayer Instance;
        public static bool TrainsOn = true;
        /// <summary>Presentation: the whole line glows with light pulses running from Almaty to Konaev (all phases shown as built).</summary>
        public static bool Showcase;
        GameObject glow; Material glowMat; float glowA;
        [Serializable] class RouteJ { public string name; public float[] pts; public float[] sec; public float[] h; public int[] ends; }
        [Serializable] class StationJ { public string name; public float x, z; public int phase; }
        [Serializable] class RoutesJ { public RouteJ[] routes; public StationJ[] stations; }
        StationJ[] extraStations = new StationJ[0];

        public class Route
        {
            public string Name; public Vector3[] P; public float[] S; public int[] Phase; public int OpenIdx = -1; public List<float> Stops = new List<float>();
            /// <summary>Section of each span (point i → i+1): Ground, Elevated or Tunnel; null = the whole route elevated (data without "sec").</summary>
            public byte[] Sec;
            /// <summary>What the start and the end of the route are: 0 terminus, 1 depot; null = not given (nothing drawn there).</summary>
            public int[] Ends;
            /// <summary>Metres into a tunnel at each point (0 outside a tunnel; null without sections).</summary>
            public float[] Deep;
        }
        public class Station
        {
            public Vector3 P; public Vector3 Dir; public int Phase; public string Name; public int Index;
            /// <summary>Section it stands on: Ground, Elevated or Tunnel (underground: no structure drawn, P at the street).</summary>
            public int Kind = Elevated;
        }
        public const byte Ground = 0, Elevated = 1, Tunnel = 2;
        /// <summary>True once the routes, stations and their meshes are made.</summary>
        public bool Built => built;
        public readonly List<Route> Routes = new List<Route>();
        public readonly List<Station> Stations = new List<Station>();

        class Part { public GameObject Go; public MeshRenderer R; public int Phase; public int Kind; }   // kind 0 piers, 1 deck, 2 stations
        readonly List<Part> parts = new List<Part>();
        class Train { public Route R; public float S, Dir = 1, Dwell; public int NextStop; public Transform A, B; }
        readonly List<Train> trains = new List<Train>();
        Material mat; Mesh carMesh, leadNight, tailNight; bool built, nightShown; int lastYear = -1; Scenario lastSc = (Scenario)(-1);
        static readonly int GhostId = Shader.PropertyToID("_Ghost"), BuildId = Shader.PropertyToID("_Build");

        // the deck 1 m deep (the data's rail stands 1.2 m over the underside, its clearance 5 m), a pier every PierStep m of the
        // line and a mast every MastStep m (the Astana viaduct: tall single columns, spans of 30 m)
        const float DeckW = 9.6f, DeckT = 1.0f, Above = 8.5f, PierStep = 30f, MastStep = 50f, LowDeck = 2.5f;
        static readonly Color32 Conc = LM.C("#cfcbc3"), ConcD = LM.C("#aaa59c"), Ballast = LM.C("#77736c"), Rail = LM.C("#4b5057"), Pole = LM.C("#8d939a");
        // the Astana LRT (opened 16.05.2026) as the reference: a light concrete box girder with a white balustrade and a yellow edge, single
        // columns with a Y head, the line on a concrete median with kerbs; at street level a green track bed between kerbs, no fences
        static readonly Color32 Balustrade = LM.C("#f1f0eb"), Yellow = LM.C("#f2c230"), Kerb = LM.C("#d9d5cc"), TrackGrass = LM.C("#6d8f4a");
        /// <summary>Concrete median under a viaduct: half width (m) and kerb height over the ground.</summary>
        const float MedianHalf = 2.6f, MedianUp = 0.2f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("LRT (viaduct, stations, trains)").AddComponent<LrtLayer>(); }
        void Awake() { Instance = this; }
        void Start() { TryBuild(); }

        void TryBuild()
        {
            if (built) return;
            if (!TwinData.Ready || CityGround.HeightAt(0, 0) == 0f) { Invoke(nameof(TryBuild), 0.3f); return; }
            var ta = Resources.Load<TextAsset>("Landmarks/lrt_routes"); var sh = Shader.Find("AlatauCity/Landmark");
            if (ta == null || sh == null) { Debug.LogWarning("[Alatau] LRT: routes or shader missing"); return; }
            mat = new Material(sh) { name = "LRT" };
            var rj = JsonUtility.FromJson<RoutesJ>(ta.text);
            foreach (var r in rj.routes) Routes.Add(MakeRoute(r));
            if (rj.stations != null) extraStations = rj.stations;          // stations of the concept extensions (airport), not in the plan's list
            MakeStations();
            for (int ri = 0; ri < Routes.Count; ri++) BuildRoute(Routes[ri]);
            BuildStations();
            carMesh = BuildCar(0); leadNight = BuildCar(1); tailNight = BuildCar(2);
            built = true; lastYear = -1;
            Debug.Log("[Alatau] LRT: " + Routes.Count + " routes, " + Stations.Count + " stations");
        }

        Route MakeRoute(RouteJ j)
        {
            if (j.sec != null && j.sec.Length >= 3 && j.pts != null && j.pts.Length >= 4) return MakeTyped(j);
            int n = j.pts.Length / 2; var r = new Route { Name = j.name, P = new Vector3[n], S = new float[n], Phase = new int[n] };
            var g = new float[n];
            for (int i = 0; i < n; i++) { float x = j.pts[i * 2], z = j.pts[i * 2 + 1]; g[i] = CityGround.HeightAt(x, z); r.P[i] = new Vector3(x, 0, z); }
            // the highest ground along each span (sampled every 8 m, 6 m to each side): the deck must clear it everywhere, not only at the piers
            var gmax = new float[n];
            for (int i = 0; i < n; i++) gmax[i] = g[i];
            for (int i = 0; i < n - 1; i++)
            {
                var a = r.P[i]; var b = r.P[i + 1]; var dir = b - a; float L = dir.magnitude; if (L < 1f) continue;
                var side = Vector3.Cross(Vector3.up, dir / L) * 6f; int k = Mathf.CeilToInt(L / 8f); float m = 0f;
                for (int q = 0; q <= k; q++) { var p = Vector3.Lerp(a, b, q / (float)k); m = Mathf.Max(m, CityGround.HeightAt(p.x, p.z), CityGround.HeightAt(p.x + side.x, p.z + side.z), CityGround.HeightAt(p.x - side.x, p.z - side.z)); }
                gmax[i] = Mathf.Max(gmax[i], m); gmax[i + 1] = Mathf.Max(gmax[i + 1], m);
            }
            // a smooth grade line over the ground, never lower than the clearance
            for (int i = 0; i < n; i++)
            {
                float s = 0, w = 0; for (int k = -6; k <= 6; k++) { int q = Mathf.Clamp(i + k, 0, n - 1); float ww = 7 - Mathf.Abs(k); s += g[q] * ww; w += ww; }
                r.P[i].y = Mathf.Max(s / w + Above, gmax[i] + 7.0f);
            }
            for (int i = 1; i < n; i++) r.S[i] = r.S[i - 1] + Vector3.Distance(new Vector3(r.P[i].x, 0, r.P[i].z), new Vector3(r.P[i - 1].x, 0, r.P[i - 1].z));
            Phases(r);
            return r;
        }
        // phase of each point = the phase of the nearest planned station
        static void Phases(Route r)
        {
            for (int i = 0; i < r.P.Length; i++)
            {
                float best = float.MaxValue; int ph = 0;
                foreach (var st in TwinData.LrtStations) { float d = (st.x - r.P[i].x) * (st.x - r.P[i].x) + (st.y - r.P[i].z) * (st.y - r.P[i].z); if (d < best) { best = d; ph = Mathf.RoundToInt(st.z); } }
                r.Phase[i] = ph;
            }
        }

        // ------------------------------------------------------------------ sections of the new map data
        /// <summary>A route with sections: points are added at every section end (so each span is of one kind) and every 26 m on the
        /// ground (the track follows the ground); rail levels from "h" when given, else computed: the viaduct as today, the ground
        /// track on the ground, ramps of 4 % on the ground side up to a viaduct, tunnels down from their mouths at 4 % to 14 m.</summary>
        Route MakeTyped(RouteJ j)
        {
            int n0 = j.pts.Length / 2;
            var xz = new List<Vector2>(n0); for (int i = 0; i < n0; i++) xz.Add(new Vector2(j.pts[i * 2], j.pts[i * 2 + 1]));
            var hh = j.h != null && j.h.Length == n0 ? new List<float>(j.h) : null;
            if (j.h != null && j.h.Length > 0 && hh == null) Debug.LogWarning($"[Alatau] LRT {j.name}: \"h\" has {j.h.Length} values for {n0} points: rail levels computed instead");
            var kinds = Sections(j.sec, xz, hh);
            int n = xz.Count;
            var r = new Route { Name = j.name, P = new Vector3[n], S = new float[n], Phase = new int[n], Sec = kinds.ToArray(), Deep = new float[n] };
            if (j.ends != null && j.ends.Length >= 2) r.Ends = new[] { Mathf.Clamp(j.ends[0], 0, 2), Mathf.Clamp(j.ends[1], 0, 2) };
            var g = new float[n];
            for (int i = 0; i < n; i++) { g[i] = CityGround.HeightAt(xz[i].x, xz[i].y); r.P[i] = new Vector3(xz[i].x, 0, xz[i].y); }
            for (int i = 1; i < n; i++) r.S[i] = r.S[i - 1] + (xz[i] - xz[i - 1]).magnitude;
            // metres into a tunnel: from the nearer mouth
            var fw = new float[n]; var bw = new float[n];
            bool Inside(int i) => (i == 0 || r.Sec[i - 1] == Tunnel) && (i == n - 1 || r.Sec[i] == Tunnel);
            for (int i = 0; i < n; i++) fw[i] = !Inside(i) ? 0f : i > 0 ? fw[i - 1] + r.S[i] - r.S[i - 1] : 1e5f;
            for (int i = n - 1; i >= 0; i--) bw[i] = !Inside(i) ? 0f : i < n - 1 ? bw[i + 1] + r.S[i + 1] - r.S[i] : 1e5f;
            for (int i = 0; i < n; i++) r.Deep[i] = Mathf.Min(fw[i], bw[i]);
            // the kind of each point: on a viaduct span → elevated; at a tunnel mouth → on the ground; between two tunnel spans → tunnel
            var pk = new byte[n];
            for (int i = 0; i < n; i++)
            {
                byte a = i > 0 ? r.Sec[i - 1] : r.Sec[0], b = i < n - 1 ? r.Sec[i] : r.Sec[n - 2];
                pk[i] = a == Tunnel && b == Tunnel ? Tunnel : a == Tunnel || b == Tunnel ? Ground : a == Elevated || b == Elevated ? Elevated : Ground;
            }
            string hFrom;
            if (hh != null) { for (int i = 0; i < n; i++) r.P[i].y = hh[i] - 0.2f; hFrom = "rail levels from the data"; }          // P = the deck / bed top, rails 0.2 m above
            else
            {
                hFrom = "rail levels computed";
                var gmax = (float[])g.Clone();
                for (int i = 0; i < n - 1; i++)
                {
                    var a = r.P[i]; var b = r.P[i + 1]; var dir = b - a; float L = dir.magnitude; if (L < 1f) continue;
                    var side = Vector3.Cross(Vector3.up, dir / L) * (r.Sec[i] == Elevated ? 6f : 4.5f); int k = Mathf.CeilToInt(L / 8f); float m = float.MinValue;
                    for (int q = 0; q <= k; q++) { var p = Vector3.Lerp(a, b, q / (float)k); m = Mathf.Max(m, Mathf.Max(CityGround.HeightAt(p.x, p.z), Mathf.Max(CityGround.HeightAt(p.x + side.x, p.z + side.z), CityGround.HeightAt(p.x - side.x, p.z - side.z)))); }
                    gmax[i] = Mathf.Max(gmax[i], m); gmax[i + 1] = Mathf.Max(gmax[i + 1], m);
                }
                for (int i = 0; i < n; i++)
                {
                    if (pk[i] == Elevated)
                    {
                        float s = 0, w = 0; for (int k = -6; k <= 6; k++) { int q = Mathf.Clamp(i + k, 0, n - 1); float ww = 7 - Mathf.Abs(k); s += g[q] * ww; w += ww; }
                        r.P[i].y = Mathf.Max(s / w + Above, gmax[i] + 7.0f);
                    }
                    else if (pk[i] == Tunnel) r.P[i].y = g[i] + 0.35f - Mathf.Min(r.Deep[i] * 0.04f, 14f);
                    else r.P[i].y = gmax[i] + 0.35f;
                }
                // ramps: a ground point climbs towards a higher neighbour at no more than 4 % (fill between walls)
                for (int pass = 0; pass < 2; pass++)
                    for (int q = 1; q < n; q++)
                    {
                        int i = pass == 0 ? q : n - 1 - q, nb = pass == 0 ? i - 1 : i + 1;
                        if (pk[i] != Ground) continue;
                        r.P[i].y = Mathf.Max(r.P[i].y, r.P[nb].y - 0.04f * Mathf.Abs(r.S[i] - r.S[nb]));
                    }
                // a viaduct that runs straight into a tunnel: its deck comes down to the mouth at no more than 4 %
                var low = new bool[n];
                for (int i = 0; i < n; i++) low[i] = pk[i] == Ground && ((i > 0 && r.Sec[i - 1] == Tunnel) || (i < n - 1 && r.Sec[i] == Tunnel));
                for (int pass = 0; pass < 2; pass++)
                    for (int q = 1; q < n; q++)
                    {
                        int i = pass == 0 ? q : n - 1 - q, nb = pass == 0 ? i - 1 : i + 1;
                        if (pk[i] != Elevated || !low[nb]) continue;
                        float cap = r.P[nb].y + 0.04f * Mathf.Abs(r.S[i] - r.S[nb]);
                        if (cap < r.P[i].y) { r.P[i].y = cap; low[i] = true; }
                    }
            }
            Phases(r);
            float[] km = new float[3]; for (int i = 0; i < n - 1; i++) km[r.Sec[i]] += (r.S[i + 1] - r.S[i]) / 1000f;
            string End(int e) => r.Ends == null ? "-" : r.Ends[e] == 1 ? "depot" : r.Ends[e] == 2 ? "continues" : "terminus";
            Debug.Log($"[Alatau] LRT {j.name}: sections ground {km[0]:0.0} km, elevated {km[1]:0.0} km, tunnel {km[2]:0.0} km; {n0} -> {n} points; {hFrom}; ends {End(0)} / {End(1)}");
            return r;
        }

        /// <summary>Splits the route at every section end and every 26 m of ground section; returns the kind of each span. Chainage
        /// is measured along the points as given; spans outside every section stay elevated (the viaduct of today).</summary>
        static List<byte> Sections(float[] sec, List<Vector2> xz, List<float> hh)
        {
            var from = new List<float>(); var to = new List<float>(); var code = new List<byte>();
            for (int i = 0; i + 2 < sec.Length; i += 3) { float a = Mathf.Min(sec[i], sec[i + 1]), b = Mathf.Max(sec[i], sec[i + 1]); from.Add(a); to.Add(b); code.Add((byte)Mathf.Clamp(Mathf.RoundToInt(sec[i + 2]), 0, 2)); }
            byte KindAt(float m) { byte k = Elevated; for (int q = 0; q < from.Count; q++) if (m >= from[q] && m < to[q]) k = code[q]; return k; }
            var c = new List<float>(xz.Count) { 0f }; for (int i = 1; i < xz.Count; i++) c.Add(c[i - 1] + (xz[i] - xz[i - 1]).magnitude);
            var cuts = new List<float>(from); cuts.AddRange(to); cuts.Sort();
            var X = new List<Vector2>(); var H = hh != null ? new List<float>() : null; var C = new List<float>(); int ci = 0;
            for (int i = 0; i < xz.Count; i++)
            {
                if (i > 0)
                    for (; ci < cuts.Count && cuts[ci] < c[i]; ci++)
                    {
                        float m = cuts[ci]; if (m <= c[i - 1] + 1f || m >= c[i] - 1f) continue;
                        float t = (m - c[i - 1]) / (c[i] - c[i - 1]); X.Add(Vector2.Lerp(xz[i - 1], xz[i], t)); H?.Add(Mathf.Lerp(hh[i - 1], hh[i], t)); C.Add(m);
                    }
                X.Add(xz[i]); H?.Add(hh[i]); C.Add(c[i]);
            }
            var kinds = new List<byte>(); var X2 = new List<Vector2>(); var H2 = H != null ? new List<float>() : null;
            for (int i = 0; i < X.Count; i++)
            {
                if (i > 0)
                {
                    byte k = KindAt((C[i - 1] + C[i]) * 0.5f); float L = C[i] - C[i - 1];
                    int parts = k == Ground && L > 30f ? Mathf.CeilToInt(L / 26f) : 1;
                    for (int q = 1; q < parts; q++) { float t = q / (float)parts; kinds.Add(k); X2.Add(Vector2.Lerp(X[i - 1], X[i], t)); H2?.Add(Mathf.Lerp(H[i - 1], H[i], t)); }
                    kinds.Add(k);
                }
                X2.Add(X[i]); H2?.Add(H[i]);
            }
            xz.Clear(); xz.AddRange(X2); if (hh != null) { hh.Clear(); hh.AddRange(H2); }
            return kinds;
        }
        /// <summary>The section kind at point i (the kinds of the spans on both sides).</summary>
        static int PointKind(Route r, int i)
        {
            if (r.Sec == null || r.Sec.Length == 0) return Elevated;
            int n = r.P.Length; byte a = i > 0 ? r.Sec[i - 1] : r.Sec[0], b = i < n - 1 ? r.Sec[i] : r.Sec[n - 2];
            return a == Tunnel && b == Tunnel ? Tunnel : a == Elevated || b == Elevated ? Elevated : Ground;
        }
        /// <summary>Metres into a tunnel at chainage s (0 outside).</summary>
        static float DeepAt(Route r, float s)
        {
            if (r.Deep == null) return 0f;
            int lo = 0, hi = r.S.Length - 1;
            while (hi - lo > 1) { int m = (lo + hi) / 2; if (r.S[m] <= s) lo = m; else hi = m; }
            return Mathf.Lerp(r.Deep[lo], r.Deep[hi], Mathf.InverseLerp(r.S[lo], r.S[hi], s));
        }

        void MakeStations()
        {
            for (int k = 0; k < TwinData.LrtStations.Length; k++)
            {
                var st = TwinData.LrtStations[k]; Route br = null; int bi = 0; float best = float.MaxValue;
                foreach (var r in Routes) for (int i = 0; i < r.P.Length; i++) { float d = (r.P[i].x - st.x) * (r.P[i].x - st.x) + (r.P[i].z - st.y) * (r.P[i].z - st.y); if (d < best) { best = d; br = r; bi = i; } }
                if (br == null || best > 400f * 400f) continue;
                var dir = br.P[Mathf.Min(bi + 1, br.P.Length - 1)] - br.P[Mathf.Max(bi - 1, 0)]; dir.y = 0; dir.Normalize();
                int ph = Mathf.RoundToInt(st.z);
                Stations.Add(new Station { P = br.P[bi], Dir = dir, Phase = ph, Index = k, Name = "Станция ЛРТ · " + (ph < TwinData.LrtPhaseNames.Length ? TwinData.LrtPhaseNames[ph] : ""), Kind = StationKind(br, bi) });
                br.Stops.Add(br.S[bi]);
            }
            foreach (var ex in extraStations)
            {
                Route br = null; int bi = 0; float best = float.MaxValue;
                foreach (var r in Routes) for (int i = 0; i < r.P.Length; i++) { float d = (r.P[i].x - ex.x) * (r.P[i].x - ex.x) + (r.P[i].z - ex.z) * (r.P[i].z - ex.z); if (d < best) { best = d; br = r; bi = i; } }
                if (br == null || best > 400f * 400f) continue;
                var dir = br.P[Mathf.Min(bi + 1, br.P.Length - 1)] - br.P[Mathf.Max(bi - 1, 0)]; dir.y = 0; dir.Normalize();
                Stations.Add(new Station { P = br.P[bi], Dir = dir, Phase = ex.phase, Index = -1, Name = "Станция ЛРТ · " + ex.name, Kind = StationKind(br, bi) });
                br.Stops.Add(br.S[bi]);
            }
            foreach (var r in Routes) r.Stops.Sort();
            // an underground station: its pin and camera at the street above
            foreach (var st in Stations) if (st.Kind == Tunnel) st.P.y = CityGround.HeightAt(st.P.x, st.P.z) + 0.2f;
            // number the stations along the line, south to north
            Stations.Sort((a, b) => a.P.z.CompareTo(b.P.z));
            for (int i = 0; i < Stations.Count; i++) Stations[i].Name += " · ст. " + (i + 1);
        }

        /// <summary>Ground for a station on a ground section near the ground (a ramp point counts as elevated: platforms on a deck).</summary>
        static int StationKind(Route r, int i)
        {
            int k = PointKind(r, i);
            if (k == Ground && r.P[i].y - CityGround.HeightAt(r.P[i].x, r.P[i].z) > 1.2f) k = Elevated;
            return k;
        }

        // ------------------------------------------------------------------ geometry
        void BuildRoute(Route r)
        {
            int n = r.P.Length;
            var side = new Vector3[n];
            for (int i = 0; i < n; i++)
            {
                Vector3 a = i > 0 ? r.P[i] - r.P[i - 1] : r.P[1] - r.P[0], b = i < n - 1 ? r.P[i + 1] - r.P[i] : a; a.y = b.y = 0;
                var s = Vector3.Cross(Vector3.up, a.normalized) + Vector3.Cross(Vector3.up, b.normalized); side[i] = s.normalized;
            }
            for (int ph = 0; ph < 3; ph++)
            {
                var deck = new LandmarkKit(); var piers = new LandmarkKit(); bool any = false;
                for (int i = 0; i < n - 1; i++)
                {
                    if (r.Phase[i] != ph && r.Phase[i + 1] != ph) continue;
                    if (r.Phase[i] != ph) continue;
                    any = true;
                    Vector3 p0 = r.P[i], p1 = r.P[i + 1], s0 = side[i], s1 = side[i + 1];
                    Vector3 fwd = (p1 - p0).normalized;
                    float L = Vector3.Distance(p0, p1), u0 = r.S[i], u1 = r.S[i + 1];
                    int kind = r.Sec != null ? r.Sec[i] : Elevated;
                    if (kind == Tunnel)
                    {
                        // nothing of a tunnel is seen but its mouths
                        Vector3 h = fwd; h.y = 0; h.Normalize(); float hood = Mathf.Min(36f, L * 0.5f);
                        if (i > 0 && r.Sec[i - 1] != Tunnel) Portal(deck, p0, h, hood);
                        if (i < n - 2 && r.Sec[i + 1] != Tunnel) Portal(deck, p1, -h, hood);
                        continue;
                    }
                    // a ramp's low end (the underside under LowDeck m over the ground) is a fill between retaining walls, no piers
                    if (kind == Ground || Mathf.Min(p0.y - CityGround.HeightAt(p0.x, p0.z), p1.y - CityGround.HeightAt(p1.x, p1.z)) - DeckT < LowDeck)
                    { GroundSpan(deck, i, p0, p1, s0, s1, u0, u1); continue; }
                    // deck slab: top, soffit, both faces
                    Vector3 a = p0 - s0 * DeckW * 0.5f, b = p0 + s0 * DeckW * 0.5f, c = p1 + s1 * DeckW * 0.5f, d = p1 - s1 * DeckW * 0.5f; var dn = Vector3.down * DeckT;
                    deck.Quad(a, b, c, d, Vector3.up, Conc, LM.Paving, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
                    deck.Quad(a + dn, b + dn, c + dn, d + dn, Vector3.down, ConcD, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u0, DeckW), new Vector2(u1, DeckW), new Vector2(u1, 0));
                    deck.Quad(a, d, d + dn, a + dn, -s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, -DeckT), new Vector2(u0, -DeckT));
                    deck.Quad(b, c, c + dn, b + dn, s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, -DeckT), new Vector2(u0, -DeckT));
                    // parapets: a white balustrade with a yellow edge along its top (the Astana viaduct)
                    foreach (float sg in new[] { -1f, 1f })
                    {
                        Vector3 e0 = p0 + s0 * sg * (DeckW * 0.5f), e1 = p1 + s1 * sg * (DeckW * 0.5f), i0 = p0 + s0 * sg * (DeckW * 0.5f - 0.3f), i1 = p1 + s1 * sg * (DeckW * 0.5f - 0.3f);
                        var up = Vector3.up * 1.1f;
                        deck.Quad(e0, e1, e1 + up, e0 + up, s0 * sg, Balustrade, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 1.1f), new Vector2(u0, 1.1f));
                        deck.Quad(i0, i1, i1 + up, i0 + up, -s0 * sg, Balustrade, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 1.1f), new Vector2(u0, 1.1f));
                        deck.Quad(e0 + up, e1 + up, i1 + up, i0 + up, Vector3.up, Balustrade, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
                        deck.Beam(e0 + up * 0.93f + s0 * sg * 0.03f, e1 + up * 0.93f + s1 * sg * 0.03f, 0.08f, 0.16f, Yellow, LM.Solid);
                    }
                    // two tracks: ballast bed and rails (lines on the deck)
                    foreach (float tc in new[] { -2.15f, 2.15f })
                    {
                        Strip(deck, p0, p1, s0, s1, tc, 2.8f, 0.06f, Ballast, LM.Roof);
                        Strip(deck, p0, p1, s0, s1, tc - 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                        Strip(deck, p0, p1, s0, s1, tc + 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                    }
                    // overhead line: mast + cantilevers every MastStep m, contact wires
                    if (Mathf.Floor(u0 / MastStep) != Mathf.Floor(u1 / MastStep))
                    {
                        var m0 = p0; deck.Beam(m0, m0 + Vector3.up * 7.2f, 0.35f, 0.35f, Pole, LM.Steel);
                        deck.Beam(m0 + Vector3.up * 6.9f - s0 * 3.2f, m0 + Vector3.up * 6.9f + s0 * 3.2f, 0.18f, 0.18f, Pole, LM.Steel);
                    }
                    foreach (float tc in new[] { -2.15f, 2.15f })
                        deck.Beam(p0 + s0 * tc + Vector3.up * 6.0f, p1 + s1 * tc + Vector3.up * 6.0f, 0.05f, 0.05f, Rail, LM.Steel);
                    // the piers come with the medians, once the film roads tell where the carriageways are (BuildMedians)
                }
                if (r.Ends != null && EndsOf(r, ph, deck)) any = true;
                if (!any) continue;
                Add(deck.ToMesh("LRT deck " + r.Name + " " + ph), ph, 1, "LRT deck · " + r.Name + " · phase " + (ph + 1));
                if (piers.VertexCount > 0) Add(piers.ToMesh("LRT piers " + r.Name + " " + ph), ph, 0, "LRT piers · " + r.Name + " · phase " + (ph + 1));
            }
        }
        bool mediansBuilt;
        /// <summary>Under the viaducts, once the film roads are drawn: a concrete median with kerbs the piers stand on — along a street
        /// it is the median between its carriageways, over open ground a strip under the deck. A span that crosses a street (one end on a
        /// carriageway, the other off it) gets none, so no kerb runs across the lanes.</summary>
        void BuildMedians()
        {
            int spans = 0, piersN = 0;
            foreach (var r in Routes)
            {
                if (r.Sec == null) continue;
                int n = r.P.Length; var side = new Vector3[n];
                for (int i = 0; i < n; i++)
                {
                    Vector3 a = i > 0 ? r.P[i] - r.P[i - 1] : r.P[1] - r.P[0], b = i < n - 1 ? r.P[i + 1] - r.P[i] : a; a.y = b.y = 0;
                    side[i] = (Vector3.Cross(Vector3.up, a.normalized) + Vector3.Cross(Vector3.up, b.normalized)).normalized;
                }
                for (int ph = 0; ph < 3; ph++)
                {
                    var k = new LandmarkKit(); var pk = new LandmarkKit();
                    for (int i = 0; i < n - 1; i++)
                    {
                        if (r.Phase[i] != ph || r.Sec[i] != Elevated) continue;
                        Vector3 p0 = r.P[i], p1 = r.P[i + 1];
                        float g0 = CityGround.HeightAt(p0.x, p0.z), g1 = CityGround.HeightAt(p1.x, p1.z);
                        if (Mathf.Floor(r.S[i] / PierStep) != Mathf.Floor(r.S[i + 1] / PierStep) && Pier(pk, r, i, side)) piersN++;
                        if (p0.y - g0 < 4f || p1.y - g1 < 4f) continue;                          // a ramp end: the deck is too low for a median
                        bool on0 = FilmRoads.OnSurface(new Vector3(p0.x, g0, p0.z), 0f, true), on1 = FilmRoads.OnSurface(new Vector3(p1.x, g1, p1.z), 0f, true);
                        if (on0 != on1) continue;
                        Vector3 s0 = side[i], s1 = side[i + 1]; float u0 = r.S[i], u1 = r.S[i + 1];
                        Vector3 G(Vector3 q, float y) => new Vector3(q.x, y, q.z);
                        Vector3 a = G(p0 - s0 * MedianHalf, g0 + MedianUp), b = G(p0 + s0 * MedianHalf, g0 + MedianUp), c = G(p1 + s1 * MedianHalf, g1 + MedianUp), d = G(p1 - s1 * MedianHalf, g1 + MedianUp);
                        k.Quad(a, b, c, d, Vector3.up, Kerb, LM.Paving, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
                        foreach (float sg in new[] { -1f, 1f })
                        {
                            Vector3 e0 = sg < 0 ? a : b, e1 = sg < 0 ? d : c;
                            k.Quad(e0, e1, G(e1, g1 - 0.3f), G(e0, g0 - 0.3f), s0 * sg, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, -0.5f), new Vector2(u0, -0.5f));
                        }
                        spans++;
                    }
                    if (k.VertexCount > 0) Add(k.ToMesh("LRT median " + r.Name + " " + ph), ph, 0, "LRT median · " + r.Name + " · phase " + (ph + 1));
                    if (pk.VertexCount > 0) Add(pk.ToMesh("LRT piers " + r.Name + " " + ph), ph, 0, "LRT piers · " + r.Name + " · phase " + (ph + 1));
                }
            }
            Debug.Log($"[Alatau] LRT: concrete median under {spans} viaduct spans, {piersN} piers (one per {PierStep:0} m, off the carriageways)");
        }

        /// <summary>A pier for span i (the PierStep mark in it): a single column with a Y head under the deck, its two arms out to the
        /// deck's bearings. On a carriageway it moves along the line up to two points either way to the nearest spot off it, else none
        /// (a longer span); none where the deck is a ramp's low end (drawn as a fill).</summary>
        static bool Pier(LandmarkKit k, Route r, int i, Vector3[] side)
        {
            int n = r.P.Length;
            foreach (int o in new[] { 0, 1, -1, 2, -2 })
            {
                int j = Mathf.Clamp(i + o, 0, n - 1); if (r.Sec[Mathf.Min(j, n - 2)] != Elevated) continue;
                Vector3 p = r.P[j]; float gy = CityGround.HeightAt(p.x, p.z);
                if (p.y - DeckT - gy < LowDeck) return false;
                if (FilmRoads.OnSurface(new Vector3(p.x, gy, p.z), 0.8f, true)) continue;
                float fork = Mathf.Max(gy + 1.5f, p.y - DeckT - 1.5f);
                k.Beam(new Vector3(p.x, gy - 1.5f, p.z), new Vector3(p.x, fork, p.z), 1.9f, 1.9f, Conc, LM.Solid);
                foreach (float sg in new[] { -1f, 1f })
                    k.Beam(new Vector3(p.x, fork - 0.4f, p.z), p + side[j] * sg * (DeckW * 0.32f) + Vector3.down * (DeckT + 0.05f), 1.3f, 1.5f, Conc, LM.Solid);
                return true;
            }
            return false;
        }

        /// <summary>A span on the ground: a green track bed between low concrete kerbs (no fences); where the bed stands more than
        /// 1.2 m above the ground (a ramp up to a viaduct), a fill between retaining walls with parapets. Two tracks, overhead line.</summary>
        static void GroundSpan(LandmarkKit k, int i, Vector3 p0, Vector3 p1, Vector3 s0, Vector3 s1, float u0, float u1)
        {
            float g0 = CityGround.HeightAt(p0.x, p0.z), g1 = CityGround.HeightAt(p1.x, p1.z); var up = Vector3.up;
            Vector3 G(Vector3 p, float y) => new Vector3(p.x, y, p.z);
            if (Mathf.Max(p0.y - g0, p1.y - g1) > 1.2f)
            {
                float hw = DeckW * 0.5f;
                Top(k, p0, p1, s0, s1, hw, Conc, LM.Paving);
                foreach (float sg in new[] { -1f, 1f })
                {
                    Vector3 e0 = p0 + s0 * sg * hw, e1 = p1 + s1 * sg * hw, i0 = p0 + s0 * sg * (hw - 0.3f), i1 = p1 + s1 * sg * (hw - 0.3f);
                    k.Quad(G(e0, g0 - 0.8f), G(e1, g1 - 0.8f), e1 + up * 1.1f, e0 + up * 1.1f, s0 * sg, ConcD, LM.Solid, 3f, new Vector2(u0, g0 - 0.8f), new Vector2(u1, g1 - 0.8f), new Vector2(u1, p1.y + 1.1f), new Vector2(u0, p0.y + 1.1f));
                    k.Quad(i0, i1, i1 + up * 1.1f, i0 + up * 1.1f, -s0 * sg, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 1.1f), new Vector2(u0, 1.1f));
                    k.Quad(e0 + up * 1.1f, e1 + up * 1.1f, i1 + up * 1.1f, i0 + up * 1.1f, up, Conc, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
                }
            }
            else
            {
                // at street level: a green track bed between low concrete kerbs, no fences (the line runs in the median of its street)
                const float hw = 4.6f;
                Top(k, p0, p1, s0, s1, hw, TrackGrass, LM.Plant);
                foreach (float sg in new[] { -1f, 1f })
                {
                    Vector3 a = p0 + s0 * sg * hw, b = p1 + s1 * sg * hw, c = G(b, g1 - 0.3f), d = G(a, g0 - 0.3f);
                    k.Quad(a, b, c, d, s0 * sg, Kerb, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, -0.3f), new Vector2(u0, -0.3f));
                    k.Beam(a + up * 0.05f - s0 * sg * 0.15f, b + up * 0.05f - s1 * sg * 0.15f, 0.3f, 0.16f, Kerb, LM.Solid);
                }
            }
            foreach (float tc in new[] { -2.15f, 2.15f })
            {
                Strip(k, p0, p1, s0, s1, tc, 2.8f, 0.06f, Ballast, LM.Roof);
                Strip(k, p0, p1, s0, s1, tc - 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                Strip(k, p0, p1, s0, s1, tc + 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                k.Beam(p0 + s0 * tc + up * 6.0f, p1 + s1 * tc + up * 6.0f, 0.05f, 0.05f, Rail, LM.Steel);
            }
            if (Mathf.Floor(u0 / MastStep) != Mathf.Floor(u1 / MastStep))
            {
                k.Beam(p0 + up * -0.6f, p0 + up * 7.2f, 0.35f, 0.35f, Pole, LM.Steel);
                k.Beam(p0 + up * 6.9f - s0 * 3.2f, p0 + up * 6.9f + s0 * 3.2f, 0.18f, 0.18f, Pole, LM.Steel);
            }
        }
        static void Top(LandmarkKit k, Vector3 p0, Vector3 p1, Vector3 s0, Vector3 s1, float hw, Color32 col, int mat)
        {
            Vector3 a = p0 - s0 * hw, b = p0 + s0 * hw, c = p1 + s1 * hw, d = p1 - s1 * hw;
            k.Quad(a, b, c, d, Vector3.up, col, mat, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
        }
        /// <summary>A tunnel mouth at p, the tunnel running along 'into': a cut-and-cover hood (side walls, roof, headwall, dark inside)
        /// the trains run into; they are hidden once 26 m inside.</summary>
        static void Portal(LandmarkKit k, Vector3 p, Vector3 into, float len)
        {
            var s = Vector3.Cross(Vector3.up, into).normalized; var up = Vector3.up; Color32 dark = LM.C("#121417");
            float g = Mathf.Min(p.y, CityGround.HeightAt(p.x, p.z));
            foreach (float sg in new[] { -1f, 1f })
            {
                k.Beam(p + s * sg * 5.3f + up * 3.2f, p + into * len + s * sg * 5.3f + up * 3.2f, 0.9f, 8.6f, Conc, LM.Solid);
                // wing walls, splayed back from the mouth
                k.Beam(p + s * sg * 5.3f + up * 1.6f, p - into * 9f + s * sg * 8.6f + up * 1.0f, 0.7f, 4.4f, ConcD, LM.Solid);
            }
            k.Beam(p + up * 7.5f, p + into * len + up * 7.5f, 11.5f, 0.9f, ConcD, LM.Solid);                      // roof
            k.Beam(p - s * 6.2f + up * 8.3f, p + s * 6.2f + up * 8.3f, 1.0f, 1.8f, Conc, LM.Solid);               // headwall over the opening
            Vector3 b = p + into * (len - 1f);
            k.Quad(b - s * 4.9f + up * (g - p.y), b + s * 4.9f + up * (g - p.y), b + s * 4.9f + up * 7.0f, b - s * 4.9f + up * 7.0f, -into, dark, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
            k.Quad(p - s * 4.9f + up * 0.05f, p + s * 4.9f + up * 0.05f, b + s * 4.9f + up * 0.05f, b - s * 4.9f + up * 0.05f, up, dark, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
        }
        /// <summary>The route's ends of phase ph: buffer stops at a terminus, a fan of sidings and a shed at a depot (on the ground
        /// beyond the end). An end inside a tunnel shows nothing.</summary>
        bool EndsOf(Route r, int ph, LandmarkKit k)
        {
            int n = r.P.Length; bool any = false;
            for (int e = 0; e < 2; e++)
            {
                int i0 = e == 0 ? 0 : n - 1, i1 = e == 0 ? 1 : n - 2;
                if (r.Phase[i0] != ph || r.Sec[e == 0 ? 0 : n - 2] == Tunnel || r.Ends[e] == 2) continue;   // 2: the line continues in a neighbouring district
                var p = r.P[i0]; var d = p - r.P[i1]; d.y = 0; if (d.sqrMagnitude < 1e-4f) continue; d.Normalize();
                var s = Vector3.Cross(Vector3.up, d); any = true;
                if (r.Ends[e] == 1) Depot(k, p, d, s, r.Sec[e == 0 ? 0 : n - 2] == Elevated, r.Name);
                else
                    foreach (float tc in new[] { -2.15f, 2.15f })
                    {
                        var c = p - d * 3f + s * tc;
                        k.Beam(c - s * 1.3f + Vector3.up * 0.9f, c + s * 1.3f + Vector3.up * 0.9f, 0.6f, 0.9f, LM.C("#c8312a"), LM.Solid);
                        foreach (float q in new[] { -0.8f, 0.8f }) k.Beam(c + s * q + Vector3.up * 0.8f, c - d * 3.2f + s * q + Vector3.up * 0.25f, 0.25f, 0.25f, Rail, LM.Steel);
                        k.Beam(c + Vector3.up * 1.5f, c + Vector3.up * 1.8f, 0.3f, 0.3f, LM.C("#ff2a1a"), LM.Light);
                    }
            }
            return any;
        }
        static void Depot(LandmarkKit k, Vector3 p, Vector3 d, Vector3 s, bool elevatedEnd, string route)
        {
            Vector3 Gr(Vector3 q) => new Vector3(q.x, CityGround.HeightAt(q.x, q.z) + 0.35f, q.z);
            var up = Vector3.up; const int Tracks = 6;
            void Track(Vector3 a, Vector3 b)
            {
                for (int q = 0; q < 4; q++)
                {
                    Vector3 a0 = Gr(Vector3.Lerp(a, b, q / 4f)), a1 = Gr(Vector3.Lerp(a, b, (q + 1) / 4f)); var sd = Vector3.Cross(Vector3.up, (a1 - a0).normalized);
                    Strip(k, a0, a1, sd, sd, 0f, 3.2f, 0.06f, Ballast, LM.Roof);
                    Strip(k, a0, a1, sd, sd, -0.72f, 0.14f, 0.2f, Rail, LM.Steel); Strip(k, a0, a1, sd, sd, 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                }
            }
            var throat = p + d * 25f;
            foreach (float tc in new[] { -2.15f, 2.15f }) Track(p + s * tc, throat + s * tc * 0.3f);
            for (int t = 0; t < Tracks; t++)
            {
                float off = (t - (Tracks - 1) * 0.5f) * 4.6f;
                Track(throat, p + d * 95f + s * off); Track(p + d * 95f + s * off, p + d * 240f + s * off);
            }
            // the shed over the inner four sidings
            float w = 4 * 4.6f + 6f; var c0 = Gr(p + d * 185f);
            var fp = new List<Vector2>();
            foreach (var q in new[] { p + d * 130f - s * w * 0.5f, p + d * 240f - s * w * 0.5f, p + d * 240f + s * w * 0.5f, p + d * 130f + s * w * 0.5f }) fp.Add(new Vector2(q.x, q.z));
            k.Prism(fp, c0.y - 1.5f, c0.y + 9f, LM.C("#b9bcbf"), LM.Metal, 3f, LM.C("#8f9499"), LM.Roof);
            if (elevatedEnd) Debug.Log($"[Alatau] LRT {route}: the depot is drawn on the ground beyond the end of the viaduct");
        }
        static void Strip(LandmarkKit k, Vector3 p0, Vector3 p1, Vector3 s0, Vector3 s1, float off, float w, float h, Color32 col, int mat)
        {
            Vector3 a = p0 + s0 * (off - w * 0.5f), b = p0 + s0 * (off + w * 0.5f), c = p1 + s1 * (off + w * 0.5f), d = p1 + s1 * (off - w * 0.5f); var up = Vector3.up * h;
            k.Quad(a + up, b + up, c + up, d + up, Vector3.up, col, mat, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
        }

        void BuildStations()
        {
            var kits = new[] { new LandmarkKit(), new LandmarkKit(), new LandmarkKit() };
            Color32 glass = LM.C("#2a4256"), white = LM.C("#ecebe6"), red = LM.C("#e0261b");
            int under = 0, onGround = 0;
            foreach (var st in Stations)
            {
                if (st.Kind == Tunnel) { under++; continue; }                          // underground: no structure (the stop stays)
                var k = kits[Mathf.Clamp(st.Phase, 0, 2)];
                float yaw = Mathf.Atan2(st.Dir.x, st.Dir.z) * Mathf.Rad2Deg - 90f;
                var p = st.P; var r = Quaternion.Euler(0, yaw, 0);
                Vector3 W(float x, float y, float z) => p + r * new Vector3(x, y, z);
                // as the Astana LRT stations (2026): 70 m side platforms under a glazed vault of white triangular panels, a thick white
                // arch at each end, glass screens along the platforms; elevated, a glass ticket hall under the deck and a stair and lift
                // tower to the platform level
                const float Plat = 70f, Half = 37f, Eave = 3.6f, Rise = 5.6f, Span = 8.8f; const int Nc = 10, Nl = 12;
                k.Box(W(0, -0.95f, 0), new Vector3(Half * 2f + 4f, 1.9f, 17.6f), yaw, LM.C("#d6d2ca"), LM.Solid, 3f, LM.C("#c9c4ba"), LM.Paving);
                foreach (float sg in new[] { -1f, 1f })
                {
                    k.Box(W(0, 0.45f, sg * 6.6f), new Vector3(Plat, 0.9f, 3.6f), yaw, white, LM.Solid, 1f, LM.C("#bdb8ae"), LM.Paving);
                    k.Box(W(0, 0.92f, sg * 4.95f), new Vector3(Plat, 0.04f, 0.3f), yaw, Yellow, LM.Solid, 1f, Yellow, LM.Solid);   // the yellow edge line
                    k.Quad(W(-Half, 0.9f, sg * 8.5f), W(Half, 0.9f, sg * 8.5f), W(Half, Eave, sg * 8.5f), W(-Half, Eave, sg * 8.5f), r * new Vector3(0, 0, sg),
                           glass, LM.Glass, 1.5f, new Vector2(0, 0), new Vector2(Half * 2f, 0), new Vector2(Half * 2f, Eave), new Vector2(0, Eave));
                    for (int i = 0; i <= 6; i++) k.Beam(W(-Half + i * Half / 3f, 0.9f, sg * 8.5f), W(-Half + i * Half / 3f, Eave, sg * 8.5f), 0.22f, 0.22f, white, LM.Solid);
                }
                // the vault: a half ellipse across the station (Span m each side, Rise m high over the eaves), each bay cut into two
                // triangles, white panel and glass in turn
                Vector3 Arc(float x, int j, float grow = 0f) { float t = Mathf.PI * j / Nc; return W(x, Eave + Mathf.Sin(t) * (Rise + grow), -Mathf.Cos(t) * (Span + grow)); }
                for (int i = 0; i < Nl; i++)
                    for (int j = 0; j < Nc; j++)
                    {
                        float x0 = -Half + 2f * Half * i / Nl, x1 = -Half + 2f * Half * (i + 1) / Nl;
                        Vector3 a = Arc(x0, j), b = Arc(x1, j), c = Arc(x1, j + 1), d = Arc(x0, j + 1);
                        var o = ((a + c) * 0.5f - W((x0 + x1) * 0.5f, Eave, 0f)).normalized; bool even = ((i + j) & 1) == 0;
                        k.Tri(a, b, c, o, even ? white : glass, even ? LM.Solid : LM.Glass, 1.5f, Vector2.zero, Vector2.right, Vector2.one);
                        k.Tri(a, c, d, o, even ? glass : white, even ? LM.Glass : LM.Solid, 1.5f, Vector2.zero, Vector2.one, Vector2.up);
                    }
                // the end arches: thick white ribs a little proud of the vault, down to the platforms
                foreach (float x in new[] { -Half - 0.4f, Half + 0.4f })
                {
                    for (int j = 0; j < Nc; j++) k.Beam(Arc(x, j, 0.5f), Arc(x, j + 1, 0.5f), 1.4f, 1.1f, white, LM.Solid);
                    foreach (int j in new[] { 0, Nc }) { var top = Arc(x, j, 0.5f); k.Beam(new Vector3(top.x, p.y + 0.9f, top.z), top, 1.4f, 1.1f, white, LM.Solid); }
                }
                if (st.Kind == Ground)
                {
                    // at street level: no hall or tower; the red LRT sign on a post at the platform end
                    onGround++;
                    k.Beam(W(Half + 2f, 0f, 10.2f), W(Half + 2f, 4.6f, 10.2f), 0.3f, 0.3f, white, LM.Solid);
                    k.Box(W(Half + 2f, 4.2f, 10.2f), new Vector3(0.4f, 1.6f, 3.2f), yaw, red, LM.Light, 1f, red, LM.Light);
                    continue;
                }
                // the ticket hall under the deck (glass, a white roof) and the stair and lift tower beside it, with the red LRT sign
                var hc = W(0, 0, 0); float gy = CityGround.HeightAt(hc.x, hc.z);
                // the ticket hall under the deck where it fits (its roof 0.3 m under the deck's underside)
                float hallH = Mathf.Min(5.2f, p.y - 1.9f - 0.3f - gy);
                if (hallH > 3.2f) k.Box(new Vector3(hc.x, gy + hallH * 0.5f, hc.z), new Vector3(26f, hallH, 9f), yaw, glass, LM.Glass, 4f, white, LM.Roof);
                // the tower at a platform end, on the first side of the four clear of buildings (else where it always stood)
                float tx = Half - 8f, tz = 13.5f;
                foreach (var (cx, cz) in new[] { (Half - 8f, 13.5f), (Half - 8f, -13.5f), (8f - Half, 13.5f), (8f - Half, -13.5f) })
                    if (Clear(W(cx, 0, cz), yaw)) { tx = cx; tz = cz; break; }
                var tb = W(tx, 0, tz); tb.y = CityGround.HeightAt(tb.x, tb.z);
                k.Box(tb + Vector3.up * ((p.y - tb.y) * 0.5f + 2f), new Vector3(9f, p.y - tb.y + 4f, 6f), yaw, glass, LM.Glass, 4f, white, LM.Roof);
                foreach (float dx in new[] { -4.6f, 4.6f }) k.Beam(W(tx + dx, 0f, tz) + Vector3.up * (tb.y - p.y), W(tx + dx, 0f, tz) + Vector3.up * 4f, 0.3f, 0.3f, white, LM.Solid);
                k.Box(W(tx, 4.2f, tz + Mathf.Sign(tz) * 3.1f), new Vector3(3.2f, 1.6f, 0.4f), yaw, red, LM.Light, 1f, red, LM.Light);
            }
            for (int ph = 0; ph < 3; ph++) if (kits[ph].VertexCount > 0) Add(kits[ph].ToMesh("LRT stations " + ph), ph, 2, "LRT stations · phase " + (ph + 1));
            if (under > 0 || onGround > 0) Debug.Log($"[Alatau] LRT stations: {onGround} at street level (no lift), {under} underground (no structure, trains still stop)");
        }

        /// <summary>No building (a collider other than the terrain, risen 1.5 m over the ground) under the 10 × 7 m tower footprint at c.</summary>
        static bool Clear(Vector3 c, float yaw)
        {
            var r = Quaternion.Euler(0, yaw, 0);
            for (int i = -1; i <= 1; i++)
                for (int j = -1; j <= 1; j++)
                {
                    var q = c + r * new Vector3(i * 5f, 0f, j * 3.5f);
                    if (Physics.Raycast(new Vector3(q.x, 6000f, q.z), Vector3.down, out var hit, 9000f, ~0, QueryTriggerInteraction.Ignore)
                        && !hit.collider.name.StartsWith("Terrain") && hit.point.y > CityGround.HeightAt(q.x, q.z) + 1.5f) return false;
                }
            return true;
        }

        void Add(Mesh m, int phase, int kind, string name)
        {
            var go = new GameObject(name); go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = m; var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = mat;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
            parts.Add(new Part { Go = go, R = r, Phase = phase, Kind = kind });
        }

        /// <summary>variant 0: by day. At night (FilmLook.Lamps) 1: the leading car, lit windows and white head lamps at its front
        /// (local −x, the direction of travel); 2: the last car, lit windows and red tail lamps at its back (local +x).</summary>
        Mesh BuildCar(int variant)
        {
            // one car of a low-floor LRV: 28 m, white with a dark window band and the qTwin red stripe; the nose is raked
            var k = new LandmarkKit(); Color32 white = LM.C("#f2f1ee"), red = LM.C("#e0261b"), dark = LM.C("#1a222b"), bog = LM.C("#3a3d42");
            float L = 28f, W = 2.65f;
            k.Box(new Vector3(0, 0.55f, 0), new Vector3(L - 3f, 0.7f, W - 0.3f), 0, bog, LM.Steel, 1f, bog, LM.Steel);
            var body = LandmarkKit.Chamfer(0, 0, L, W, 0.25f);
            var nose = LandmarkKit.Chamfer(0, 0, L - 1.6f, W - 0.2f, 0.6f);
            k.Prism(body, 0.9f, 1.25f, red, LM.Solid, 1f, red, -1);
            k.Prism(body, 1.25f, 2.15f, white, LM.Solid, 5f, white, -1);
            if (variant == 0) k.Prism(body, 2.15f, 3.25f, dark, LM.Glass, 6f, white, -1);
            else
            {
                // the window band lit from inside (warm), with the dark pillars between the windows
                k.Prism(body, 2.15f, 3.25f, LM.C("#b09662"), LM.Light, 6f, white, -1);
                for (float x = -L * 0.5f + 2.2f; x < L * 0.5f - 2f; x += 1.85f)
                    foreach (float sg in new[] { -1f, 1f }) k.Box(new Vector3(x, 2.7f, sg * (W * 0.5f - 0.03f)), new Vector3(0.24f, 1.1f, 0.12f), 0, dark, LM.Solid, 1f, dark, LM.Solid);
            }
            k.Loft(body, 3.25f, nose, 3.7f, white, LM.Solid, 5f); k.Cap(nose, 3.7f, true, LM.C("#d9dcdf"), LM.Roof);
            k.Box(new Vector3(0, 3.95f, 0), new Vector3(5f, 0.5f, 1.4f), 0, LM.C("#9aa0a6"), LM.Metal, 1f, LM.C("#9aa0a6"), LM.Metal);
            if (variant == 0) foreach (float sg in new[] { -1f, 1f }) k.Box(new Vector3(sg * (L * 0.5f + 0.02f), 1.6f, 0), new Vector3(0.1f, 0.35f, 1.8f), 0, LM.C("#fff6dd"), LM.Light, 1f, LM.C("#fff6dd"), LM.Light);
            else
            {
                // night: two head lamps at the front of the train, two red tail lamps at its back
                float ex = variant == 1 ? -(L * 0.5f + 0.03f) : L * 0.5f + 0.03f; var lc = variant == 1 ? LM.C("#ffffff") : LM.C("#ff2a1a");
                foreach (float sg in new[] { -1f, 1f }) k.Box(new Vector3(ex, 1.15f, sg * 0.85f), new Vector3(0.12f, 0.26f, 0.48f), 0, lc, LM.Light, 1f, lc, LM.Light);
                if (variant == 1) k.Box(new Vector3(ex, 3.0f, 0), new Vector3(0.1f, 0.22f, 1.4f), 0, LM.C("#ffb347"), LM.Light, 1f, LM.C("#ffb347"), LM.Light);   // route display
            }
            return k.ToMesh("LRT car");
        }

        // ------------------------------------------------------------------ year, phases, trains
        void Update()
        {
            if (!built) return;
            if (!mediansBuilt && FilmRoads.Ready) { mediansBuilt = true; BuildMedians(); lastYear = -1; }
            int y = TwinState.Year, s = (int)TwinState.Scenario;
            if (y != lastYear || TwinState.Scenario != lastSc) { ApplyYear(y, s); lastYear = y; lastSc = TwinState.Scenario; }
            MoveTrains(Time.deltaTime);
            // showcase glow: fades in and out
            glowA = Mathf.MoveTowards(glowA, Showcase ? 1f : 0f, Time.deltaTime * 0.8f);
            if (glowA > 0.001f && glow == null) BuildGlow();
            if (glow != null) { glow.SetActive(glowA > 0.001f); glowMat.SetFloat("_Fade", glowA); }
            UpdateEnds();
        }
        void BuildGlow()
        {
            var sh = Shader.Find("AlatauCity/Glow"); if (sh == null) return;
            glowMat = new Material(sh) { name = "LRT glow" }; glowMat.SetColor("_Color", new Color(0.62f, 0.30f, 1f) * 0.85f);   // additive over the light ground: strong enough to read from the whole-city view, still violet
            glow = new GameObject("LRT glow"); glow.transform.SetParent(transform, false);
            var V = new List<Vector3>(); var U = new List<Vector2>(); var T = new List<int>();
            const float W = 220f;
            foreach (var r in Routes)
            {
                float acc = 0; int v0 = V.Count;
                for (int i = 0; i < r.P.Length; i++)
                {
                    var a = r.P[Mathf.Max(i - 1, 0)]; var b = r.P[Mathf.Min(i + 1, r.P.Length - 1)]; var d = (b - a); d.y = 0; d.Normalize();
                    var side = new Vector3(-d.z, 0, d.x) * (W * 0.5f);
                    if (i > 0) acc += Vector3.Distance(r.P[i], r.P[i - 1]);
                    var c = r.P[i]; c.y = Mathf.Max(c.y, CityGround.HeightAt(c.x, c.z)) + 6f;      // over a tunnel: above the ground
                    V.Add(c - side); U.Add(new Vector2(acc, 0)); V.Add(c + side); U.Add(new Vector2(acc, 1));
                    if (i > 0) { int k = v0 + (i - 1) * 2; T.Add(k); T.Add(k + 2); T.Add(k + 1); T.Add(k + 1); T.Add(k + 2); T.Add(k + 3); }
                }
            }
            var m = new Mesh { name = "LRT glow", indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 }; m.SetVertices(V); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateBounds();
            glow.AddComponent<MeshFilter>().sharedMesh = m; var mr = glow.AddComponent<MeshRenderer>(); mr.sharedMaterial = glowMat; mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }
        /// <summary>Labels at the ends of the trunk while the line is showcased: the line continues to Almaty (south) and Konaev (north).</summary>
        bool endsShown;
        void UpdateEnds()
        {
            bool want = Showcase && Routes.Count > 0;
            if (want == endsShown) return; endsShown = want;
            if (!want) { MapPins.Instance?.Clear(); return; }
            var tr = Routes[0]; var s0 = tr.P[0]; var s1 = tr.P[tr.P.Length - 1];
            bool southFirst = s0.z < s1.z; var south = southFirst ? s0 : s1; var north = southFirst ? s1 : s0;
            MapPins.Instance?.Set(new List<MapPins.Pin> {
                new MapPins.Pin { Id = "lrt_almaty", Label = "↓ в Алматы", World = south + Vector3.up * 20f, Fill = new Color(0.72f, 0.50f, 1f), ShowLabel = true, Size = 16f },
                new MapPins.Pin { Id = "lrt_konaev", Label = "в Конаев ↑", World = north + Vector3.up * 20f, Fill = new Color(0.72f, 0.50f, 1f), ShowLabel = true, Size = 16f } });
        }
        public int OpenYear(int phase) { int s = (int)TwinState.Scenario; return TwinData.LrtPhaseYear[s] != null && phase < TwinData.LrtPhaseYear[s].Length ? TwinData.LrtPhaseYear[s][phase] : 2040; }

        void ApplyYear(int y, int s)
        {
            var mpb = new MaterialPropertyBlock();
            foreach (var p in parts)
            {
                int open = OpenYear(p.Phase);
                bool on = p.Kind == 0 ? y >= open - 2 : p.Kind == 1 ? y >= open - 1 : y >= open;
                p.Go.SetActive(on);
                if (!on) continue;
                p.R.GetPropertyBlock(mpb); mpb.SetFloat(BuildId, y < open ? 1f : 0f); p.R.SetPropertyBlock(mpb);
            }
            // trains run on the open part of each route (phases open south → north; branches as a whole)
            foreach (var r in Routes)
            {
                int idx = -1; for (int i = 0; i < r.P.Length; i++) { if (OpenYear(r.Phase[i]) <= y) idx = i; else break; }
                r.OpenIdx = idx;
            }
            SpawnTrains();
        }

        void SpawnTrains()
        {
            foreach (var t in trains) { if (t.A != null) Destroy(t.A.gameObject); if (t.B != null) Destroy(t.B.gameObject); }
            trains.Clear();
            foreach (var r in Routes)
            {
                if (r.OpenIdx < 4) continue;
                float len = r.S[r.OpenIdx]; int count = Mathf.Clamp(Mathf.RoundToInt(len / 9000f), 1, 6);
                for (int i = 0; i < count; i++)
                {
                    var t = new Train { R = r, S = len * (i + 0.5f) / count, Dir = i % 2 == 0 ? 1 : -1 };
                    t.A = Car("LRT train " + r.Name + " " + i + " a"); t.B = Car("LRT train " + r.Name + " " + i + " b");
                    if (nightShown) { SetMesh(t.A, leadNight); SetMesh(t.B, tailNight); }
                    t.NextStop = NextStop(r, t.S, t.Dir);
                    trains.Add(t);
                }
            }
        }
        Transform Car(string name)
        {
            var go = new GameObject(name); go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = carMesh; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat;
            return go.transform;
        }
        static void SetMesh(Transform t, Mesh m) { if (t == null) return; var mf = t.GetComponent<MeshFilter>(); if (mf != null && m != null) mf.sharedMesh = m; }
        static int NextStop(Route r, float s, float dir)
        {
            if (dir > 0) { for (int i = 0; i < r.Stops.Count; i++) if (r.Stops[i] > s + 1f) return i; return -1; }
            for (int i = r.Stops.Count - 1; i >= 0; i--) if (r.Stops[i] < s - 1f) return i; return -1;
        }

        void MoveTrains(float dt)
        {
            bool show = TrainsOn;
            // lit windows and lamps from dusk on
            bool night = FilmLook.Active && FilmLook.Lamps > 0.35f;
            if (night != nightShown)
            {
                nightShown = night;
                foreach (var t in trains) { SetMesh(t.A, night ? leadNight : carMesh); SetMesh(t.B, night ? tailNight : carMesh); }
            }
            foreach (var t in trains)
            {
                if (!show) { t.A.gameObject.SetActive(false); t.B.gameObject.SetActive(false); continue; }
                var r = t.R; float end = r.S[r.OpenIdx];
                if (t.Dwell > 0) t.Dwell -= dt;
                else
                {
                    float stop = t.NextStop >= 0 && t.NextStop < r.Stops.Count ? r.Stops[t.NextStop] : (t.Dir > 0 ? end : 0f);
                    stop = Mathf.Clamp(stop, 0f, end);
                    float dist = Mathf.Abs(stop - t.S);
                    float v = Mathf.Lerp(16f, 110f, Mathf.Clamp01(dist / 420f));      // fast between stations (the demo runs ×6), slows to a stop
                    float step = Mathf.Min(v * dt, dist);
                    t.S += step * t.Dir;
                    if (dist - step < 0.5f)
                    {
                        t.Dwell = 3.5f;
                        if ((t.Dir > 0 && t.S >= end - 1f) || (t.Dir < 0 && t.S <= 1f)) t.Dir = -t.Dir;
                        t.NextStop = NextStop(r, t.S, t.Dir);
                    }
                }
                float sa = Place(t.A, r, t.S, t.Dir, 0f), sb = Place(t.B, r, t.S, t.Dir, -28.6f);
                // in a tunnel a car is hidden once it is inside the portal's hood
                t.A.gameObject.SetActive(r.Deep == null || DeepAt(r, sa) < 26f); t.B.gameObject.SetActive(r.Deep == null || DeepAt(r, sb) < 26f);
            }
        }
        static float Place(Transform tr, Route r, float s, float dir, float back)
        {
            float sc = Mathf.Clamp(s + back * dir, 0f, r.S[Mathf.Max(r.OpenIdx, 1)]);
            var p = At(r, sc, out var fwd);
            // the bogies (0.2 m above the car origin) stand on the rails (0.2 m above the deck)
            tr.SetPositionAndRotation(p + Vector3.up * 0.02f + Vector3.Cross(fwd, Vector3.up).normalized * (dir > 0 ? -2.15f : 2.15f), Quaternion.LookRotation(fwd * dir, Vector3.up) * Quaternion.Euler(0, 90f, 0));
            return sc;
        }
        public static Vector3 At(Route r, float s, out Vector3 fwd)
        {
            int lo = 0, hi = r.S.Length - 1;
            while (hi - lo > 1) { int m = (lo + hi) / 2; if (r.S[m] <= s) lo = m; else hi = m; }
            float t = Mathf.InverseLerp(r.S[lo], r.S[hi], s);
            fwd = r.P[hi] - r.P[lo]; if (fwd.sqrMagnitude < 1e-6f) fwd = Vector3.forward; fwd.Normalize();
            return Vector3.Lerp(r.P[lo], r.P[hi], t);
        }
        public bool StationOpen(Station st) => OpenYear(st.Phase) <= TwinState.Year;
    }
}
