using System;
using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The LRT of the master plan in 3D: a double-track viaduct along the planned line (trunk Gate → Green and two branches to
    /// the west), piers, overhead line, stations with canopies and lifts, and trains running between the stations.
    /// Opens by phase and year of the scenario (construction.json → lrt.phase_year): piers 2 years before, the deck 1 year before, trains
    /// from the opening year. The route comes from the plan's LRT layer (Resources/Landmarks/lrt_routes.json).</summary>
    public class LrtLayer : MonoBehaviour
    {
        public static LrtLayer Instance;
        public static bool TrainsOn = true;
        /// <summary>Presentation: the whole line glows with light pulses running from Almaty to Konaev (all phases shown as built).</summary>
        public static bool Showcase;
        GameObject glow; Material glowMat; float glowA;
        [Serializable] class RouteJ { public string name; public float[] pts; }
        [Serializable] class StationJ { public string name; public float x, z; public int phase; }
        [Serializable] class RoutesJ { public RouteJ[] routes; public StationJ[] stations; }
        StationJ[] extraStations = new StationJ[0];

        public class Route { public string Name; public Vector3[] P; public float[] S; public int[] Phase; public int OpenIdx = -1; public List<float> Stops = new List<float>(); }
        public class Station { public Vector3 P; public Vector3 Dir; public int Phase; public string Name; public int Index; }
        public readonly List<Route> Routes = new List<Route>();
        public readonly List<Station> Stations = new List<Station>();

        class Part { public GameObject Go; public MeshRenderer R; public int Phase; public int Kind; }   // kind 0 piers, 1 deck, 2 stations
        readonly List<Part> parts = new List<Part>();
        class Train { public Route R; public float S, Dir = 1, Dwell; public int NextStop; public Transform A, B; }
        readonly List<Train> trains = new List<Train>();
        Material mat; Mesh carMesh, leadNight, tailNight; bool built, nightShown; int lastYear = -1; Scenario lastSc = (Scenario)(-1);
        static readonly int GhostId = Shader.PropertyToID("_Ghost"), BuildId = Shader.PropertyToID("_Build");

        const float DeckW = 9.6f, DeckT = 1.9f, Above = 8.5f;
        static readonly Color32 Conc = LM.C("#cfcbc3"), ConcD = LM.C("#aaa59c"), Ballast = LM.C("#77736c"), Rail = LM.C("#4b5057"), Pole = LM.C("#8d939a");

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
            // phase of each point = the phase of the nearest planned station
            for (int i = 0; i < n; i++)
            {
                float best = float.MaxValue; int ph = 0;
                foreach (var st in TwinData.LrtStations) { float d = (st.x - r.P[i].x) * (st.x - r.P[i].x) + (st.y - r.P[i].z) * (st.y - r.P[i].z); if (d < best) { best = d; ph = Mathf.RoundToInt(st.z); } }
                r.Phase[i] = ph;
            }
            return r;
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
                Stations.Add(new Station { P = br.P[bi], Dir = dir, Phase = ph, Index = k, Name = "Станция ЛРТ · " + (ph < TwinData.LrtPhaseNames.Length ? TwinData.LrtPhaseNames[ph] : "") });
                br.Stops.Add(br.S[bi]);
            }
            foreach (var ex in extraStations)
            {
                Route br = null; int bi = 0; float best = float.MaxValue;
                foreach (var r in Routes) for (int i = 0; i < r.P.Length; i++) { float d = (r.P[i].x - ex.x) * (r.P[i].x - ex.x) + (r.P[i].z - ex.z) * (r.P[i].z - ex.z); if (d < best) { best = d; br = r; bi = i; } }
                if (br == null || best > 400f * 400f) continue;
                var dir = br.P[Mathf.Min(bi + 1, br.P.Length - 1)] - br.P[Mathf.Max(bi - 1, 0)]; dir.y = 0; dir.Normalize();
                Stations.Add(new Station { P = br.P[bi], Dir = dir, Phase = ex.phase, Index = -1, Name = "Станция ЛРТ · " + ex.name });
                br.Stops.Add(br.S[bi]);
            }
            foreach (var r in Routes) r.Stops.Sort();
            // number the stations along the line, south to north
            Stations.Sort((a, b) => a.P.z.CompareTo(b.P.z));
            for (int i = 0; i < Stations.Count; i++) Stations[i].Name += " · ст. " + (i + 1);
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
                    // deck slab: top, soffit, both faces
                    Vector3 a = p0 - s0 * DeckW * 0.5f, b = p0 + s0 * DeckW * 0.5f, c = p1 + s1 * DeckW * 0.5f, d = p1 - s1 * DeckW * 0.5f; var dn = Vector3.down * DeckT;
                    deck.Quad(a, b, c, d, Vector3.up, Conc, LM.Paving, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
                    deck.Quad(a + dn, b + dn, c + dn, d + dn, Vector3.down, ConcD, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u0, DeckW), new Vector2(u1, DeckW), new Vector2(u1, 0));
                    deck.Quad(a, d, d + dn, a + dn, -s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, -DeckT), new Vector2(u0, -DeckT));
                    deck.Quad(b, c, c + dn, b + dn, s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, -DeckT), new Vector2(u0, -DeckT));
                    // parapets
                    foreach (float sg in new[] { -1f, 1f })
                    {
                        Vector3 e0 = p0 + s0 * sg * (DeckW * 0.5f), e1 = p1 + s1 * sg * (DeckW * 0.5f), i0 = p0 + s0 * sg * (DeckW * 0.5f - 0.3f), i1 = p1 + s1 * sg * (DeckW * 0.5f - 0.3f);
                        var up = Vector3.up * 1.1f;
                        deck.Quad(e0, e1, e1 + up, e0 + up, s0 * sg, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 1.1f), new Vector2(u0, 1.1f));
                        deck.Quad(i0, i1, i1 + up, i0 + up, -s0 * sg, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 1.1f), new Vector2(u0, 1.1f));
                        deck.Quad(e0 + up, e1 + up, i1 + up, i0 + up, Vector3.up, Conc, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
                    }
                    // two tracks: ballast bed and rails (lines on the deck)
                    foreach (float tc in new[] { -2.15f, 2.15f })
                    {
                        Strip(deck, p0, p1, s0, s1, tc, 2.8f, 0.06f, Ballast, LM.Roof);
                        Strip(deck, p0, p1, s0, s1, tc - 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                        Strip(deck, p0, p1, s0, s1, tc + 0.72f, 0.14f, 0.2f, Rail, LM.Steel);
                    }
                    // overhead line: mast + cantilevers every other point, contact wires
                    if (i % 2 == 0)
                    {
                        var m0 = p0; deck.Beam(m0, m0 + Vector3.up * 7.2f, 0.35f, 0.35f, Pole, LM.Steel);
                        deck.Beam(m0 + Vector3.up * 6.9f - s0 * 3.2f, m0 + Vector3.up * 6.9f + s0 * 3.2f, 0.18f, 0.18f, Pole, LM.Steel);
                    }
                    foreach (float tc in new[] { -2.15f, 2.15f })
                        deck.Beam(p0 + s0 * tc + Vector3.up * 6.0f, p1 + s1 * tc + Vector3.up * 6.0f, 0.05f, 0.05f, Rail, LM.Steel);
                    // pier every other point: column + cap beam under the deck
                    if (i % 2 == 0)
                    {
                        float gy = CityGround.HeightAt(p0.x, p0.z);
                        piers.Beam(new Vector3(p0.x, gy - 1.5f, p0.z), new Vector3(p0.x, p0.y - DeckT - 1.1f, p0.z), 2.0f, 2.4f, ConcD, LM.Solid);
                        piers.Beam(p0 - s0 * (DeckW * 0.42f) + Vector3.down * (DeckT + 0.55f), p0 + s0 * (DeckW * 0.42f) + Vector3.down * (DeckT + 0.55f), 1.6f, 1.1f, ConcD, LM.Solid);
                    }
                }
                if (!any) continue;
                Add(deck.ToMesh("LRT deck " + r.Name + " " + ph), ph, 1, "LRT deck · " + r.Name + " · phase " + (ph + 1));
                Add(piers.ToMesh("LRT piers " + r.Name + " " + ph), ph, 0, "LRT piers · " + r.Name + " · phase " + (ph + 1));
            }
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
            foreach (var st in Stations)
            {
                var k = kits[Mathf.Clamp(st.Phase, 0, 2)];
                float yaw = Mathf.Atan2(st.Dir.x, st.Dir.z) * Mathf.Rad2Deg - 90f;
                var p = st.P; var r = Quaternion.Euler(0, yaw, 0);
                Vector3 W(float x, float y, float z) => p + r * new Vector3(x, y, z);
                // side platforms widen the deck; the canopy is a shallow glass vault on white ribs
                k.Box(W(0, -0.95f, 0), new Vector3(96f, 1.9f, 17f), yaw, LM.C("#d6d2ca"), LM.Solid, 3f, LM.C("#c9c4ba"), LM.Paving);
                foreach (float sg in new[] { -1f, 1f }) k.Box(W(0, 0.45f, sg * 6.6f), new Vector3(92f, 0.9f, 3.6f), yaw, white, LM.Solid, 1f, LM.C("#bdb8ae"), LM.Paving);
                for (int i = 0; i < 9; i++)
                {
                    float x = -40f + i * 10f;
                    foreach (float sg in new[] { -1f, 1f }) k.Beam(W(x, 0.9f, sg * 7.6f), W(x, 6.4f, sg * 7.6f), 0.35f, 0.35f, white, LM.Solid);
                }
                var c0 = new List<Vector2>(); var c1 = new List<Vector2>();
                // vault: two sloped glass roofs meeting at a white ridge
                foreach (float sg in new[] { -1f, 1f })
                {
                    var a = W(-46f, 6.4f, sg * 8.6f); var b = W(46f, 6.4f, sg * 8.6f); var c = W(46f, 8.4f, 0f); var d = W(-46f, 8.4f, 0f);
                    k.Quad(a, b, c, d, Vector3.up + (W(0, 0, sg) - p).normalized * 0.3f, glass, LM.Glass, 1.5f, new Vector2(0, 0), new Vector2(92f, 0), new Vector2(92f, 8.8f), new Vector2(0, 8.8f));
                }
                k.Beam(W(-46f, 8.45f, 0), W(46f, 8.45f, 0), 0.6f, 0.4f, white, LM.Solid);
                // lift and stair tower to the street, with the red LRT sign
                float gy = CityGround.HeightAt(W(0, 0, 13f).x, W(0, 0, 13f).z);
                var tb = W(0, 0, 13.5f); tb.y = gy;
                k.Box(tb + Vector3.up * ((p.y - gy) * 0.5f + 2f), new Vector3(8f, p.y - gy + 4f, 6f), yaw, glass, LM.Glass, 4f, white, LM.Roof);
                k.Box(W(0, 4.2f, 16.8f), new Vector3(3.2f, 1.6f, 0.4f), yaw, red, LM.Light, 1f, red, LM.Light);
            }
            for (int ph = 0; ph < 3; ph++) if (kits[ph].VertexCount > 0) Add(kits[ph].ToMesh("LRT stations " + ph), ph, 2, "LRT stations · phase " + (ph + 1));
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
                    var c = r.P[i] + Vector3.up * 6f;
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
                t.A.gameObject.SetActive(show); t.B.gameObject.SetActive(show); if (!show) continue;
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
                Place(t.A, r, t.S, t.Dir, 0f); Place(t.B, r, t.S, t.Dir, -28.6f);
            }
        }
        static void Place(Transform tr, Route r, float s, float dir, float back)
        {
            float sc = Mathf.Clamp(s + back * dir, 0f, r.S[Mathf.Max(r.OpenIdx, 1)]);
            var p = At(r, sc, out var fwd);
            // the bogies (0.2 m above the car origin) stand on the rails (0.2 m above the deck)
            tr.SetPositionAndRotation(p + Vector3.up * 0.02f + Vector3.Cross(fwd, Vector3.up).normalized * (dir > 0 ? -2.15f : 2.15f), Quaternion.LookRotation(fwd * dir, Vector3.up) * Quaternion.Euler(0, 90f, 0));
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
