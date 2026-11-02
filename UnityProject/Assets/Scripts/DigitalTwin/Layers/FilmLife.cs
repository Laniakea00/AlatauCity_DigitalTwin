using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The living city of the film look: people on the pavements and on the squares of the landmarks, flags at their entrances,
    /// small flocks of birds by day, and the tower cranes of the landmark sites at work (LandmarkSite.CraneMotion).
    /// People walk along the pavements of the film roads (FilmRoads ways, open in the year shown), never on a carriageway, a landmark plot
    /// or under a building; on the squares, campus alleys and forecourts they stand in small groups or stroll, never on a cell next to a
    /// wall or a height step (each cell's corners must land on the same level floor). How many there are follows
    /// the floor area built round them in the year shown and the hour (busy at midday and in the evening, few at night).
    /// Everything is drawn instanced near the camera (Windows/film: up to 3 000 people, WebGL: up to 600) and nothing above 1.5 km.
    /// The crowd, its clothes and its places are a model, not data.</summary>
    public class FilmLife : MonoBehaviour
    {
        const float Cell = 320f, Step = 4f;
        static bool High => Application.platform != RuntimePlatform.WebGLPlayer;
        public static FilmLife Instance;
        /// <summary>People drawn this frame, 0 when none were (read by the bench mode, AlatauBench).</summary>
        public static int ShownNow => shownFrame == Time.frameCount ? shownLast : 0;
        static int shownLast, shownFrame = -1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Film life").AddComponent<FilmLife>(); }

        class Run { public Vector3[] P; public float Len, St = Step; public Vector4 Years; public bool Main, Park; }       // St: metres between points
        struct Person { public int Run; public float S0, Speed, Lat, Rank, Scale, Phase, Yaw; public bool Rev; public Vector3 Pos; public int Mesh; public Vector4 Top, Bot; }
        class Crowd { public Run[] Runs; public Person[] People; public Vector3 Centre; public float Radius; public int ActYear = -1, ActSc = -1; public float Act; public List<BuildingInfo> Blds; }
        class Site { public string Id; public Landmark L; public bool Gate, Tried; public Crowd C; public Vector3 Centre; public float Radius; public Matrix4x4[] Poles, Cloth; public Vector4[] ClothA, ClothB, ClothC; public int[] Tex; }

        readonly Dictionary<long, Crowd> cells = new Dictionary<long, Crowd>();
        readonly Dictionary<long, List<Vector2Int>> waySegs = new Dictionary<long, List<Vector2Int>>();      // (way, segment index ≥ 1)
        readonly Dictionary<long, List<BuildingInfo>> blds = new Dictionary<long, List<BuildingInfo>>();
        readonly Dictionary<Collider, bool> isGround = new Dictionary<Collider, bool>();
        readonly List<Site> sites = new List<Site>();
        // the alleys and loops of the parks (Resources/Map/map_walks.json, ground.py): points every WalkStep m (a bend's chord stays
        // within 0.35 m of the line), cut by cell; W = the walk's width
        const float WalkStep = 1f, Body = 0.3f;
        class Walk { public Vector2[] P; public Vector4 Years; public bool Alley; public float W; }
        [System.Serializable] class WalkJ { public int[] y; public float w; public int k; public float[] p; }
        [System.Serializable] class WalksJ { public int v; public WalkJ[] walks; }
        readonly Dictionary<long, List<Walk>> parkWalks = new Dictionary<long, List<Walk>>();
        FilmRoads.Way[] ways; float[] wayHalf, wayWalk;
        bool ready, cranesHooked; Camera mainCam; MapCamera mc;
        Material matPerson, matFlag, matBird, matPole, matBanner; Mesh[] people = new Mesh[3]; Mesh cloth, pole, bird;
        static readonly int AId = Shader.PropertyToID("_LifeA"), BId = Shader.PropertyToID("_LifeB"), CId = Shader.PropertyToID("_LifeC");

        // draw batches: per person mesh, a few arrays of 1023, filled each frame for the camera that renders (no allocation)
        class Batch { public Matrix4x4[] M = new Matrix4x4[1023]; public Vector4[] A = new Vector4[1023], B = new Vector4[1023], C = new Vector4[1023]; public bool[] Site = new bool[1023], Park = new bool[1023]; public MaterialPropertyBlock P = new MaterialPropertyBlock(); public int N; }
        Batch[][] batches; Batch flagBatch, poleBatch, bannerBatch, birdBatch;
        readonly List<long> near = new List<long>(); readonly List<long> wanted = new List<long>();

        static long Key(int cx, int cz) => ((long)(cx + 100000) << 32) | (uint)(cz + 100000);
        static int C(float v) => Mathf.FloorToInt(v / Cell);

        void Awake() { Instance = this; }
        void OnEnable() { Camera.onPreCull += Draw; }
        void OnDisable() { Camera.onPreCull -= Draw; }

        void LateUpdate()
        {
            if (!ready) { TryInit(); return; }
            if (!cranesHooked) HookCranes();
            if (!FilmLook.Active || mainCam == null) return;
            // fill in the crowds round what the camera looks at, a few milliseconds a frame
            Vector3 f = mc != null ? mc.target : mainCam.transform.position;
            float R = mc != null ? Mathf.Clamp(mc.distance * 1.2f, 500f, 1200f) : 700f;
            if (mc != null && mc.distance > 2500f) return;
            wanted.Clear();
            for (int cz = C(f.z - R); cz <= C(f.z + R); cz++) for (int cx = C(f.x - R); cx <= C(f.x + R); cx++) { long k = Key(cx, cz); if (!cells.ContainsKey(k)) wanted.Add(k); }
            if (wanted.Count > 0)
            {
                wanted.Sort((a, b) => D2(a, f).CompareTo(D2(b, f)));
                float t0 = Time.realtimeSinceStartup;
                foreach (long k in wanted) { Street(k); if (Time.realtimeSinceStartup - t0 > 0.004f) break; }
            }
            // the squares of the landmarks: made once, when the camera first comes near a finished one
            foreach (var s in sites)
                if (!s.Tried && (new Vector2(s.Centre.x - f.x, s.Centre.z - f.z)).magnitude < 1500f + s.Radius && Done(s)) { MakeSite(s); break; }
        }

        static float D2(long k, Vector3 f)
        {
            float x = ((int)(k >> 32) - 100000 + 0.5f) * Cell - f.x, z = ((int)(uint)(k & 0xFFFFFFFF) - 100000 + 0.5f) * Cell - f.z; return x * x + z * z;
        }

        // ------------------------------------------------------------------ setting up
        void TryInit()
        {
            if (!TwinData.Ready || FilmRoads.WayCount == 0) return;
            var ls = LandmarkSystem.Instance; if (ls == null || !ls.Ready) return;
            var sh = Shader.Find("AlatauCity/Life");
            if (sh == null) { Debug.LogWarning("[Alatau] film life: shader AlatauCity/Life missing"); enabled = false; return; }
            ready = true;
            mainCam = Camera.main; mc = mainCam != null ? mainCam.GetComponent<MapCamera>() : null;
            Material M(int kind, string name) { var m = new Material(sh) { name = name, enableInstancing = true }; m.SetFloat("_LifeKind", kind); return m; }
            matPerson = M(0, "Film people"); matFlag = M(1, "Film flags"); matBird = M(2, "Film birds"); matPole = M(3, "Film flag poles"); matBanner = M(4, "Film banners");
            matFlag.SetTexture("_MainTex", FlagAtlas());
            people[0] = PersonMesh(0); people[1] = PersonMesh(1); people[2] = PersonMesh(2);
            cloth = ClothMesh(); pole = PoleMesh(); bird = BirdMesh();
            int nb = High ? 3 : 1; batches = new Batch[3][];
            for (int m = 0; m < 3; m++) { batches[m] = new Batch[nb]; for (int b = 0; b < nb; b++) batches[m][b] = new Batch(); }
            flagBatch = new Batch(); poleBatch = new Batch(); bannerBatch = new Batch(); birdBatch = new Batch();

            // the ways and their cross-sections (as FilmRoads draws them), sorted into cells with a margin
            int n = FilmRoads.WayCount; ways = new FilmRoads.Way[n]; wayHalf = new float[n]; wayWalk = new float[n];
            for (int w = 0; w < n; w++)
            {
                var W = ways[w] = FilmRoads.GetWay(w);
                FilmRoads.Dims(W.Cls, out float half, out float walk, out _, out _);
                if (W.Edge >= 0 && W.Half >= 0f)
                {
                    // the redrawn map: the street profile's carriageway and pavements; a pedestrian street or a bike path is walked across its
                    // width (half 0); ramps and roads without sidewalks (expressways: verges only) have nobody on them
                    half = W.Half; walk = W.Walk;
                    var sec = FilmRoads.Profile(W.Edge);
                    if (W.Ramp || (!W.NoCars && sec.Has && sec.SidewalkL + sec.SidewalkR <= 0f)) walk = 0f;
                }
                else if (W.Ramp) { half = 4f; walk = 0f; }
                else if (W.OneWay) half = W.Cls == TwinData.RoadClass.Highway ? 6f : W.Cls == TwinData.RoadClass.Ring ? 5.5f : W.Cls == TwinData.RoadClass.Main ? 3.8f : 3.2f;
                wayHalf[w] = half; wayWalk[w] = walk;
                if (W.P == null) continue;
                float mg = half + walk + 4f;
                for (int i = 1; i < W.P.Count; i++)
                {
                    Vector2 a = W.P[i - 1], b = W.P[i];
                    for (int cz = C(Mathf.Min(a.y, b.y) - mg); cz <= C(Mathf.Max(a.y, b.y) + mg); cz++)
                        for (int cx = C(Mathf.Min(a.x, b.x) - mg); cx <= C(Mathf.Max(a.x, b.x) + mg); cx++)
                        { long k = Key(cx, cz); if (!waySegs.TryGetValue(k, out var l)) waySegs[k] = l = new List<Vector2Int>(); l.Add(new Vector2Int(w, i)); }
                }
            }
            var db = CityDatabase.Instance;
            if (db != null) foreach (var b in db.Counted) if (b != null) { long k = Key(C(b.X), C(b.Z)); if (!blds.TryGetValue(k, out var l)) blds[k] = l = new List<BuildingInfo>(); l.Add(b); }     // with the landmark lots' own floor area

            // the squares: the plaza and gardens of Iconic Complex, the Gate District round it, the KAIST campus, the forecourts of the
            // medical cluster, K-Park and L7
            foreach (var id in new[] { "iconic", "kaist", "medcluster", "kpark", "lotte_l7" })
            {
                var l = ls.Get(id); if (l == null) continue;
                sites.Add(new Site { Id = id, L = l, Centre = new Vector3(l.X, 0f, l.Z), Radius = Mathf.Max(l.PadW, l.PadD) * 0.5f });
            }
            var ic = ls.Get("iconic");
            if (ic != null && QTwinData.Gate() != null) sites.Add(new Site { Id = "gate", L = ic, Gate = true, Centre = new Vector3(ic.X, 0f, ic.Z), Radius = QTwinData.Gate().Half });
            Debug.Log($"[Alatau] film life: {n} ways, {sites.Count} squares, quality {(High ? "high" : "light")}");
            ParkWalks();
        }

        /// <summary>The walks of the parks (map_walks.json: alleys k 0, loops k 1, `y` per scenario, `w` width) resampled every WalkStep m
        /// and cut by cell; people walk them like pavements (Street), within w/2 of the line. No file: none.</summary>
        void ParkWalks()
        {
            var ta = Resources.Load<TextAsset>("Map/map_walks"); if (ta == null) return;
            WalksJ j = null; try { j = JsonUtility.FromJson<WalksJ>(ta.text); } catch (System.Exception ex) { Debug.LogWarning("[Alatau] film life: map_walks.json unreadable: " + ex.Message); }
            if (j?.walks == null) return;
            int nw = 0, np = 0; float km = 0f; var pts = new List<Vector2>(); long cur = 0; Vector4 yv = Vector4.zero; bool alley = false; float ww = 0f;
            void Flush()
            {
                if (pts.Count >= 3)
                {
                    if (!parkWalks.TryGetValue(cur, out var l)) parkWalks[cur] = l = new List<Walk>();
                    l.Add(new Walk { P = pts.ToArray(), Years = yv, Alley = alley, W = ww }); np++;
                }
                pts.Clear();
            }
            foreach (var w in j.walks)
            {
                if (w.p == null || w.p.Length < 4) continue;
                yv = w.y != null && w.y.Length >= 4 ? new Vector4(w.y[0], w.y[1], w.y[2], w.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                alley = w.k == 0; ww = w.w > 0f ? w.w : 3.5f; nw++; pts.Clear(); float carry = 0f;
                for (int i = 2; i + 1 < w.p.Length; i += 2)
                {
                    Vector2 a = new Vector2(w.p[i - 2], w.p[i - 1]), b = new Vector2(w.p[i], w.p[i + 1]); float len = (b - a).magnitude; if (len < 0.01f) continue;
                    km += len / 1000f;
                    for (float t = carry; t < len; t += WalkStep)
                    {
                        var q = Vector2.Lerp(a, b, t / len); long k = Key(C(q.x), C(q.y));
                        if (pts.Count > 0 && k != cur) Flush();
                        cur = k; pts.Add(q); carry = t + WalkStep - len;
                    }
                }
                Flush();
            }
            Debug.Log($"[Alatau] film life: {nw} park walks ({km:0.0} km, map_walks.json) in {np} paths for people");
        }

        /// <summary>Every tower crane of the landmark sites gets its work cycle (slewing, trolley, hook).</summary>
        void HookCranes()
        {
            cranesHooked = true; int n = 0;
            foreach (var t in LandmarkSystem.Instance.GetComponentsInChildren<Transform>(true))
                if (t.name.StartsWith("Crane head") && t.GetComponent<LandmarkSite.CraneMotion>() == null) { t.gameObject.AddComponent<LandmarkSite.CraneMotion>(); n++; }
            Debug.Log($"[Alatau] film life: {n} cranes at work");
        }

        static bool Done(Site s) => s.Gate ? IconicDistrict.On : LandmarkSystem.Progress(s.L, LandmarkSystem.YearNow) >= 0.999f;

        // ------------------------------------------------------------------ the crowd of a street cell
        bool Ground(float x, float z)
        {
            if (!Physics.Raycast(new Vector3(x, 6000f, z), Vector3.down, out var hit, 9000f, ~0, QueryTriggerInteraction.Ignore)) return false;
            if (!isGround.TryGetValue(hit.collider, out bool g)) isGround[hit.collider] = g = hit.collider.name.StartsWith("Terrain");
            return g;
        }

        /// <summary>Paving at q: hard ground of the data (GroundTypes: a park alley, a court, a playground …) or a drawn film road surface.</summary>
        static bool Paved(GroundTypes gt, Vector2 q) => gt.HardAt(q.x, q.y) || FilmRoads.OnSurface(new Vector3(q.x, CityGround.HeightAt(q.x, q.y), q.y), 0f, false);

        bool Walkable(Vector2 q, int self, List<Vector2Int> segs)
        {
            if (LandmarkSystem.OnPlot(q.x, q.y, 2f)) return false;
            if (FilmRoads.InInterchange(q.x, q.y)) return false;
            if (segs != null)
                foreach (var s in segs)
                {
                    if (s.x == self) continue;
                    var P = ways[s.x].P; if (Dist(q, P[s.y - 1], P[s.y]) < wayHalf[s.x] + 0.6f) return false;
                }
            return Ground(q.x, q.y);
        }

        void Street(long key)
        {
            int cx = (int)(key >> 32) - 100000, cz = (int)(uint)(key & 0xFFFFFFFF) - 100000;
            float x0 = cx * Cell, z0 = cz * Cell;
            var rng = new System.Random(cx * 73856093 ^ cz * 19349663);
            var runs = new List<Run>(); var crowd = new List<Person>();
            waySegs.TryGetValue(key, out var segs);
            if (segs != null)
            {
                // the ways of this cell, each with its segments in order
                var byWay = new SortedDictionary<int, List<int>>();
                foreach (var s in segs) { if (!byWay.TryGetValue(s.x, out var l)) byWay[s.x] = l = new List<int>(); l.Add(s.y); }
                var pts = new List<Vector3>();
                foreach (var kv in byWay)
                {
                    int w = kv.Key; var W = ways[w]; float walk = wayWalk[w]; if (walk <= 0f || W.Ramp || W.P == null) continue;
                    float off = wayHalf[w] + walk * 0.5f; kv.Value.Sort();
                    for (int side = -1; side <= 1; side += 2)
                    {
                        pts.Clear(); float carry = 0f; int prev = -10;
                        void Flush()
                        {
                            if (pts.Count >= 3) runs.Add(new Run { P = pts.ToArray(), Len = (pts.Count - 1) * Step, Years = W.Years, Main = W.Cls != TwinData.RoadClass.Street });
                            pts.Clear();
                        }
                        foreach (int i in kv.Value)
                        {
                            if (i != prev + 1) { Flush(); carry = 0f; }
                            int seg = i - 1;
                            prev = i;
                            Vector2 a = W.P[i - 1], b = W.P[i]; float len = (b - a).magnitude; if (len < 0.01f) continue;
                            Vector2 d = (b - a) / len, left = new Vector2(-d.y, d.x) * side;
                            for (float t = carry; t < len; t += Step)
                            {
                                var q = a + d * t + left * off;
                                bool inCell = q.x >= x0 && q.x < x0 + Cell && q.y >= z0 && q.y < z0 + Cell;
                                if (inCell && Walkable(q, w, segs)) pts.Add(new Vector3(q.x, FilmRoads.SurfaceY(w, seg, t / len, q, 0.14f), q.y));     // the terrain, or the deck / embankment of the redrawn map
                                else Flush();
                                carry = t + Step - len;
                            }
                        }
                        Flush();
                    }
                }
                // people on each run: one every 8 m on main roads, every 13 m on streets (at the busiest), fewer on the light quality
                for (int ri = 0; ri < runs.Count; ri++)
                {
                    var r = runs[ri]; float spacing = (r.Main ? 8f : 13f) * (High ? 1f : 1.7f);
                    int np = Mathf.Max(1, Mathf.RoundToInt(r.Len / spacing));
                    for (int i = 0; i < np; i++) crowd.Add(NewPerson(rng, ri, r.Len * (float)rng.NextDouble(), 0.9f));
                }
            }
            // the parks' alleys and loops: someone every 11 m of an alley and 16 m of a loop at the busiest (Fill: a share of their own)
            if (parkWalks.TryGetValue(key, out var pw))
            {
                // a walker keeps within w/2 of the line, a body's width inside the edge (the chord of a bend: 0.35 m more); the run is
                // cut where the ground drawn there is not paved at the line or at the walker's reach on either side (a walk the drawing
                // breaks for a tree or a building, its link over the verge where nothing is drawn): nobody on the grass beside a walk
                int r0 = runs.Count; var gt = GroundTypes.Instance; var wp = new List<Vector3>(); var wh = new List<float>();
                foreach (var w in pw)
                {
                    float lat = Mathf.Max(0f, w.W * 0.5f - Body - 0.35f), reach = lat + Body; wp.Clear();
                    void Cut() { if (wp.Count >= 4) { runs.Add(new Run { P = wp.ToArray(), St = WalkStep, Len = (wp.Count - 1) * WalkStep, Years = w.Years, Main = w.Alley, Park = true }); wh.Add(lat); } wp.Clear(); }
                    for (int i = 0; i < w.P.Length; i++)
                    {
                        var q = w.P[i];
                        var d = w.P[Mathf.Min(i + 1, w.P.Length - 1)] - w.P[Mathf.Max(i - 1, 0)]; var n = new Vector2(-d.y, d.x).normalized * reach;
                        if (gt != null && !(Paved(gt, q) && Paved(gt, q + n) && Paved(gt, q - n))) { Cut(); continue; }
                        wp.Add(new Vector3(q.x, CityGround.HeightAt(q.x, q.y) + 0.03f, q.y));
                    }
                    Cut();
                }
                for (int ri = r0; ri < runs.Count; ri++)
                {
                    var r = runs[ri]; float spacing = (r.Main ? 11f : 16f) * (High ? 1f : 1.7f), lat = wh[ri - r0];
                    int np = Mathf.Max(1, Mathf.RoundToInt(r.Len / spacing));
                    for (int i = 0; i < np; i++) { var p = NewPerson(rng, ri, r.Len * (float)rng.NextDouble(), 0.8f); p.Lat = Mathf.Clamp(p.Lat, -lat, lat); crowd.Add(p); }
                }
            }
            blds.TryGetValue(key, out var bl);
            cells[key] = new Crowd { Runs = runs.ToArray(), People = crowd.ToArray(), Centre = new Vector3(x0 + Cell * 0.5f, 0f, z0 + Cell * 0.5f), Radius = Cell * 0.75f, Blds = bl };
        }

        // a crowd of late October: dark and neutral coats and jackets, some colour
        static readonly Color[] Tops = {
            new Color(0.10f, 0.10f, 0.11f), new Color(0.18f, 0.18f, 0.20f), new Color(0.14f, 0.17f, 0.26f), new Color(0.30f, 0.31f, 0.33f), new Color(0.55f, 0.50f, 0.42f),
            new Color(0.52f, 0.38f, 0.24f), new Color(0.20f, 0.25f, 0.18f), new Color(0.40f, 0.14f, 0.15f), new Color(0.80f, 0.79f, 0.76f), new Color(0.34f, 0.33f, 0.24f),
            new Color(0.62f, 0.60f, 0.57f), new Color(0.07f, 0.08f, 0.10f), new Color(0.70f, 0.20f, 0.16f), new Color(0.78f, 0.60f, 0.20f), new Color(0.15f, 0.42f, 0.45f), new Color(0.25f, 0.35f, 0.60f) };
        static readonly Color[] Bottoms = {
            new Color(0.14f, 0.18f, 0.27f), new Color(0.09f, 0.09f, 0.10f), new Color(0.22f, 0.22f, 0.24f), new Color(0.48f, 0.44f, 0.36f), new Color(0.32f, 0.29f, 0.25f), new Color(0.24f, 0.30f, 0.42f) };

        static Person NewPerson(System.Random rng, int run, float s0, float walkShare)
        {
            float r = (float)rng.NextDouble();
            var p = new Person { Run = run, S0 = s0, Rev = rng.Next(2) == 0, Rank = (float)rng.NextDouble(), Phase = (float)rng.NextDouble() * 6.283f };
            p.Speed = (float)rng.NextDouble() < walkShare ? 1.05f + 0.45f * (float)rng.NextDouble() : 0f;       // some stand: waiting, talking
            p.Scale = (float)rng.NextDouble() < 0.05f ? 0.66f + 0.1f * (float)rng.NextDouble() : 0.93f + 0.13f * (float)rng.NextDouble();
            p.Mesh = r < 0.42f ? 0 : r < 0.66f ? 1 : 2;
            p.Lat = ((float)rng.NextDouble() - 0.5f) * 1.0f;
            int ti = (float)rng.NextDouble() < 0.82f ? rng.Next(12) : 12 + rng.Next(4);
            var tc = Tops[ti] * (0.9f + 0.2f * (float)rng.NextDouble()); var bc = Bottoms[rng.Next(Bottoms.Length)] * (0.9f + 0.2f * (float)rng.NextDouble());
            p.Top = new Vector4(tc.r, tc.g, tc.b, Mathf.Pow((float)rng.NextDouble(), 1.6f) * 0.8f);
            p.Bot = new Vector4(bc.r, bc.g, bc.b, (float)rng.NextDouble() < 0.8f ? 0.1f * (float)rng.NextDouble() : 0.5f + 0.5f * (float)rng.NextDouble());
            p.Yaw = (float)rng.NextDouble() * 360f;
            return p;
        }

        /// <summary>How busy the cell is in the year shown: the floor area standing round it (cached per year and scenario).</summary>
        static float Activity(Crowd c)
        {
            int y = TwinState.Year < 1 ? 2050 : TwinState.Year, sc = (int)TwinState.Scenario;
            if (c.ActYear == y && c.ActSc == sc) return c.Act;
            c.ActYear = y; c.ActSc = sc; float gfa = 0f;
            if (c.Blds != null) foreach (var b in c.Blds) if (TwinScenario.EffectiveYear(b, TwinState.Scenario) <= y) gfa += Mathf.Max(b.GfaM2, 200f);
            c.Act = Mathf.Clamp01(0.06f + gfa / 90000f);
            return c.Act;
        }

        /// <summary>Share of people out at an hour (busiest in the evening, few at night).</summary>
        static readonly float[] hx = { 4f, 6f, 7.5f, 8.5f, 10f, 13f, 15f, 17.5f, 19f, 20.5f, 21.5f, 22f };
        static readonly float[] hv = { 0.03f, 0.08f, 0.40f, 0.70f, 0.55f, 0.85f, 0.65f, 0.90f, 1.0f, 0.75f, 0.42f, 0.30f };
        static float HourShare(float h)
        {
            if (h <= hx[0]) return hv[0];
            for (int i = 1; i < hx.Length; i++) if (h <= hx[i]) return Mathf.Lerp(hv[i - 1], hv[i], (h - hx[i - 1]) / (hx[i] - hx[i - 1]));
            return hv[hv.Length - 1];
        }

        // ------------------------------------------------------------------ the squares of the landmarks
        static readonly HashSet<int> WalkTags = new HashSet<int> { 5, 9, 30, 45, 49, 60, 62 };      // paving only: no lawns, gardens or roofs

        void MakeSite(Site s)
        {
            s.Tried = true;
            // the Gate district's paving is the narrow pavements of its streets and round the ring (2.5–5 m wide, the blocks are gardens):
            // a 2.5 m grid, people stand where a cell and its four neighbours are paving and walk the way the pavement runs
            float step = s.Gate ? 2.5f : 3f;
            Collider col = null; Mesh cm = null; GameObject tmp = null; int[] tris = null; List<Vector2> uv1 = null; byte[] tags = null;
            Transform frame = LandmarkSystem.Instance.ModelOf(s.L.Id); if (frame == null) return;
            float halfW, halfD;
            if (s.Gate)
            {
                // the district has no collider: a temporary one on its mesh, put on the terrain as IconicDistrict does, removed after
                var d = QTwinData.Gate(); var m = d.Mesh; float baseY = s.L.Base != 0f ? s.L.Base : CityGround.HeightAt(s.L.X, s.L.Z);
                var rot = Quaternion.Euler(0f, s.L.Yaw, 0f); var org = new Vector3(s.L.X, baseY, s.L.Z);
                var pos = new Vector3[m.P.Length];
                for (int i = 0; i < pos.Length; i++) { var p = m.P[i]; var w = org + rot * new Vector3(p.x, 0f, p.z); pos[i] = new Vector3(p.x, CityGround.HeightAt(w.x, w.z) - baseY + p.y + 0.12f, p.z); }
                cm = new Mesh { indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 }; cm.vertices = pos; cm.triangles = m.I;
                tmp = new GameObject("Film life probe") { layer = 2 }; tmp.transform.SetPositionAndRotation(org, rot);
                var mcol = tmp.AddComponent<MeshCollider>(); mcol.sharedMesh = cm; col = mcol; Physics.SyncTransforms(); tags = m.Tag; tris = m.I; halfW = halfD = d.Half;
            }
            else
            {
                col = frame.GetComponent<MeshCollider>(); var mesh = col != null ? ((MeshCollider)col).sharedMesh : null;
                if (mesh == null || !mesh.isReadable) return;
                tris = mesh.triangles; uv1 = new List<Vector2>(); mesh.GetUVs(1, uv1); halfW = s.L.PadW * 0.5f; halfD = s.L.PadD * 0.5f;
            }
            int gw = Mathf.CeilToInt(2f * halfW / step), gd = Mathf.CeilToInt(2f * halfD / step);
            var ok = new bool[gw * gd]; var hy = new float[gw * gd]; int nOk = 0, nWall = 0;
            float pr = step * 0.5f + 0.3f;      // a cell's corners and a body's width beyond them
            for (int j = 0; j < gd; j++) for (int i = 0; i < gw; i++)
            {
                float lx = -halfW + (i + 0.5f) * step, lz = -halfD + (j + 0.5f) * step;
                if (s.Gate && (!QTwinData.InArea(lx, lz) || (Mathf.Abs(lx) < 140f && Mathf.Abs(lz) < 104f))) continue;
                var top = (s.Gate ? tmp.transform : frame).TransformPoint(new Vector3(lx, 0f, lz)); top.y += 600f;
                if (!col.Raycast(new Ray(top, Vector3.down), out var hit, 2000f) || hit.normal.y < 0.92f || hit.triangleIndex < 0) continue;
                int vi = tris[hit.triangleIndex * 3]; bool walk;
                if (s.Gate) walk = WalkTags.Contains(tags[vi]) && hit.point.y - CityGround.HeightAt(hit.point.x, hit.point.z) < 0.8f;
                else { var u = uv1[vi]; int mat = Mathf.RoundToInt(u.x), tg = Mathf.RoundToInt(u.y); walk = (mat == LM.Paving || (mat == LM.QTwin && WalkTags.Contains(tg))) && hit.point.y - frame.position.y < 2f; }     // the ground of the plot, not a roof
                if (!walk) continue;
                // nobody next to a wall or a height step (a retaining wall, a sloped roof's foot, a terrace edge, a building): the four
                // corners of the cell, a body's width beyond it, land on a level floor too (an upward face within 0.25 m of the centre's
                // height; lawn or paving alike, a kerb passes)
                bool clear = true;
                for (int c = 0; c < 4 && clear; c++)
                {
                    var pt = (s.Gate ? tmp.transform : frame).TransformPoint(new Vector3(lx + ((c & 1) == 0 ? -pr : pr), 0f, lz + ((c & 2) == 0 ? -pr : pr))); pt.y = top.y;
                    clear = col.Raycast(new Ray(pt, Vector3.down), out var ph, 2000f) && ph.normal.y >= 0.92f && Mathf.Abs(ph.point.y - hit.point.y) < 0.25f;
                }
                if (!clear) { nWall++; continue; }
                ok[j * gw + i] = true; hy[j * gw + i] = hit.point.y + 0.02f; nOk++;
            }
            if (tmp != null) { Destroy(tmp); Destroy(cm); }
            Transform fr = frame;
            Vector3 W(float lx, float lz, float y) { var p = fr.TransformPoint(new Vector3(lx, 0f, lz)); p.y = y; return p; }
            bool Inner(int i, int j) { for (int b = -1; b <= 1; b++) for (int a = -1; a <= 1; a++) { int x = i + a, z = j + b; if (x < 0 || z < 0 || x >= gw || z >= gd || !ok[z * gw + x]) return false; } return true; }
            bool OkAt(int i, int j) => i >= 0 && j >= 0 && i < gw && j < gd && ok[j * gw + i];
            bool Room(int i, int j) => s.Gate ? OkAt(i, j) && OkAt(i - 1, j) && OkAt(i + 1, j) && OkAt(i, j - 1) && OkAt(i, j + 1) : Inner(i, j);
            bool Path(int i, int j) => s.Gate ? OkAt(i, j) : Inner(i, j);
            var rng = new System.Random(s.Id.GetHashCode());
            var runs = new List<Run>(); var crowd = new List<Person>();
            if (nOk > 0)
            {
                float cell2 = step * step;
                int groups = Mathf.Min(High ? 260 : 90, Mathf.RoundToInt(nOk * cell2 / (s.Gate ? 420f : 160f)));
                int strolls = Mathf.Min(High ? 320 : 110, Mathf.RoundToInt(nOk * cell2 / (s.Gate ? 300f : 120f)));
                for (int g = 0, tries = 0; g < groups && tries < groups * 20; tries++)
                {
                    int i = rng.Next(gw), j = rng.Next(gd); if (!Room(i, j)) continue;
                    float lx = -halfW + (i + 0.5f) * step + ((float)rng.NextDouble() - 0.5f) * step, lz = -halfD + (j + 0.5f) * step + ((float)rng.NextDouble() - 0.5f) * step;
                    var c = W(lx, lz, hy[j * gw + i]); float rr = (float)rng.NextDouble(); int n = rr < 0.3f ? 1 : rr < 0.65f ? 2 : rr < 0.85f ? 3 : 4;
                    float a0 = (float)rng.NextDouble() * 360f;
                    for (int k = 0; k < n; k++)
                    {
                        var p = NewPerson(rng, -1, 0f, 0f);
                        float a = (a0 + k * 360f / n) * Mathf.Deg2Rad, rad = n == 1 ? 0f : 0.55f + 0.16f * n;
                        p.Pos = c + new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a)) * rad;
                        p.Yaw = n == 1 ? (float)rng.NextDouble() * 360f : Mathf.Atan2(-Mathf.Cos(a), -Mathf.Sin(a)) * Mathf.Rad2Deg;     // facing each other
                        crowd.Add(p);
                    }
                    g++;
                }
                var pts = new List<Vector3>(); var best = new List<Vector3>();
                for (int g = 0, tries = 0; g < strolls && tries < strolls * 20; tries++)
                {
                    int i = rng.Next(gw), j = rng.Next(gd); if (!Path(i, j)) continue;
                    float ang0 = (float)rng.NextDouble() * Mathf.PI * 2f, L = 15f + 55f * (float)rng.NextDouble();
                    Vector2 a = new Vector2(-halfW + (i + 0.5f) * step, -halfD + (j + 0.5f) * step);
                    best.Clear();
                    for (int hd = 0, nh = s.Gate ? 16 : 1; hd < nh; hd++)       // the Gate: the longest of 16 headings (along its pavement)
                    {
                        float ang = ang0 + hd * Mathf.PI / 8f; var d = new Vector2(Mathf.Cos(ang), Mathf.Sin(ang));
                        pts.Clear(); float lastY = hy[j * gw + i];
                        for (float t = 0f; t <= L; t += Step)
                        {
                            var q = a + d * t; int qi = Mathf.FloorToInt((q.x + halfW) / step), qj = Mathf.FloorToInt((q.y + halfD) / step);
                            var h = a + d * Mathf.Max(0f, t - Step * 0.5f); int hi = Mathf.FloorToInt((h.x + halfW) / step), hj = Mathf.FloorToInt((h.y + halfD) / step);     // and half way from the last point (no corner cut)
                            if (!Path(qi, qj) || !Path(hi, hj) || Mathf.Abs(hy[qj * gw + qi] - lastY) > 0.6f) break;
                            lastY = hy[qj * gw + qi]; pts.Add(W(q.x, q.y, lastY));
                        }
                        if (pts.Count > best.Count) { best.Clear(); best.AddRange(pts); }
                    }
                    pts.Clear(); pts.AddRange(best);
                    if (pts.Count < 4) continue;
                    var r = new Run { P = pts.ToArray(), Len = (pts.Count - 1) * Step, Years = Vector4.zero }; runs.Add(r);
                    int np = 1 + (rng.Next(3) == 0 ? 1 : 0);
                    for (int k = 0; k < np; k++) { var p = NewPerson(rng, runs.Count - 1, r.Len * (float)rng.NextDouble(), 1f); p.Speed *= 0.8f; p.Lat = (k - 0.5f * (np - 1)) * 0.7f; crowd.Add(p); }
                    g++;
                }
            }
            s.C = new Crowd { Runs = runs.ToArray(), People = crowd.ToArray(), Centre = s.Centre, Radius = s.Radius, Act = 1f, ActYear = int.MaxValue };
            if (!s.Gate) Flags(s, fr, ok, hy, gw, gd, step, halfW, halfD, Inner);
            Debug.Log($"[Alatau] film life: {s.Id}: {nOk} walkable cells ({nWall} next to a wall or step left out), {crowd.Count} people, {runs.Count} paths");
        }

        // ------------------------------------------------------------------ flags at the entrance
        static readonly Vector3 Wind = new Vector3(-0.94f, 0f, -0.34f);       // the wind blows the flags to the west-south-west
        void Flags(Site s, Transform fr, bool[] ok, float[] hy, int gw, int gd, float step, float halfW, float halfD, System.Func<int, int, bool> inner)
        {
            if (s.Id != "iconic" && s.Id != "kaist" && s.Id != "medcluster") return;
            // Iconic Complex flies the flags of the countries behind it: China, Kazakhstan in the middle (the host), the Republic of Korea,
            // and a little apart at the end of the row the qTwin logo (an easter egg); the others Kazakhstan between two banners
            int[] tex = s.Id == "iconic" ? new[] { FlagCn, FlagKz, FlagKr, FlagLogo } : new[] { -1, FlagKz, -1 };
            int n = tex.Length; var off = new float[n]; var reach = new int[n];
            // the free paved spot nearest to the middle of the near side of the plot (where the hoarding had its gate)
            int bi = -1, bj = -1; float best = float.MaxValue; var want = new Vector2(0f, -halfD + 14f);
            for (int pass = 0; pass < 2 && bi < 0; pass++)
            {
                float gap = pass == 0 ? 7.0f : n > 3 ? 6.0f : 5.2f;                        // between the poles: room for the cloth
                for (int k = 0; k < n; k++)
                {
                    off[k] = (k - 1) * gap + (k == 3 ? 0.4f * gap : 0f);
                    reach[k] = (int)Mathf.Sign(off[k]) * Mathf.CeilToInt(Mathf.Abs(off[k]) / step - 1e-3f);     // grid cells to the pole, free round it
                }
                for (int j = 0; j < gd; j++) for (int i = 0; i < gw; i++)
                {
                    bool fits = true; for (int k = 0; k < n && fits; k++) fits = inner(i + reach[k], j);
                    if (!fits) continue;
                    float dd = (new Vector2(-halfW + (i + 0.5f) * step, -halfD + (j + 0.5f) * step) - want).sqrMagnitude; if (dd < best) { best = dd; bi = i; bj = j; }
                }
            }
            if (bi < 0) return;
            s.Poles = new Matrix4x4[n]; s.Cloth = new Matrix4x4[n]; s.ClothA = new Vector4[n]; s.ClothB = new Vector4[n]; s.ClothC = new Vector4[n]; s.Tex = tex;
            // the cloth runs along local +x. At Iconic the wind blows along the front of the plot, so the four cloths fly along the row
            // side by side, each readable face on from the entrance and the usual view of the plaza (hoist on the left)
            var wind = s.Id == "iconic" ? fr.TransformDirection(Vector3.right) : Wind;
            float yaw = Mathf.Atan2(wind.x, wind.z) * Mathf.Rad2Deg - 90f;
            for (int k = 0; k < n; k++)
            {
                var lp = fr.TransformPoint(new Vector3(-halfW + (bi + 0.5f) * step + off[k], 0f, -halfD + (bj + 0.5f) * step));
                lp.y = hy[bj * gw + bi] - 0.05f;
                s.Poles[k] = Matrix4x4.TRS(lp, Quaternion.identity, Vector3.one);
                // each cloth in its own proportions, its top 0.3 m under the finial: Kazakhstan and the banners 2:1, China, Korea and the
                // logo 3:2 of the same area
                bool wide = tex[k] < 0 || tex[k] == FlagKz; float cw = wide ? 5.2f : 4.5f, ch = wide ? 2.6f : 3.0f;
                s.Cloth[k] = Matrix4x4.TRS(lp + Vector3.up * (14.35f - ch) + wind * 0.10f, Quaternion.Euler(0f, yaw, 0f), new Vector3(cw, ch, 2.8f));
                s.ClothA[k] = new Vector4(1f, k * 1.7f, 0.55f, tex[k] == FlagLogo ? 1f : 0f);    // w 1: a two-ply cloth, the logo reads from both sides
            }
            Color a, b;
            switch (s.Id)
            {
                case "kaist": a = new Color(0.05f, 0.22f, 0.50f); b = new Color(0.93f, 0.93f, 0.92f); break;
                case "medcluster": a = new Color(0.94f, 0.94f, 0.93f); b = new Color(0.10f, 0.52f, 0.50f); break;
                default: a = new Color(0.78f, 0.64f, 0.36f); b = new Color(0.16f, 0.16f, 0.17f); break;
            }
            for (int k = 0; k < n; k++) { s.ClothB[k] = a; s.ClothC[k] = b; }
        }

        // ------------------------------------------------------------------ drawing (for whichever main camera renders: the map view and the capture renders)
        float lastBirdT = -1f;
        void Draw(Camera cam)
        {
            if (!ready || cam != mainCam || !FilmLook.Active) return;
            Vector3 cp = cam.transform.position; float above = cp.y - CityGround.HeightAt(cp.x, cp.z);
            if (above > 1500f) return;
            float Rd = High ? 650f : 380f, t = Time.timeSinceLevelLoad;
            float hour = FilmLook.Instance != null ? FilmLook.Instance.hour : 13f, hs = HourShare(hour);
            int year = TwinState.Year < 1 ? 2050 : TwinState.Year, sc = Mathf.Clamp((int)TwinState.Scenario, 0, 3);
            int cap = High ? 3000 : 600, shown = 0;
            for (int m = 0; m < 3; m++) foreach (var b in batches[m]) b.N = 0;
            // the street cells round the camera, the nearest first; the ones right by it are made at once (a capture jumps there)
            near.Clear();
            for (int cz = C(cp.z - Rd); cz <= C(cp.z + Rd); cz++) for (int cx = C(cp.x - Rd); cx <= C(cp.x + Rd); cx++)
            {
                long k = Key(cx, cz);
                if (!cells.ContainsKey(k)) { if (D2(k, cp) < 300f * 300f && wantedNow++ < 4) Street(k); else continue; }
                near.Add(k);
            }
            wantedNow = 0;
            for (int i = 1; i < near.Count; i++)          // nearest first (insertion sort: no allocation)
            {
                long k = near[i]; float dk = D2(k, cp); int j = i - 1;
                while (j >= 0 && D2(near[j], cp) > dk) { near[j + 1] = near[j]; j--; }
                near[j + 1] = k;
            }
            foreach (var s in sites) if (s.C != null && Done(s) && Flat(s.Centre - cp) < Rd + s.Radius) shown = Fill(s.C, cp, Rd, t, hs * 0.85f, hs * 0.6f, year, sc, cap, shown, true);
            foreach (var k in near) { if (shown >= cap) break; var c = cells[k]; shown = Fill(c, cp, Rd, t, hs * Activity(c), hs * 0.6f, year, sc, cap, shown, false); }
            shownLast = shown; shownFrame = Time.frameCount;
            for (int m = 0; m < 3; m++)
                foreach (var b in batches[m])
                {
                    if (b.N == 0) continue;
                    b.P.SetVectorArray(AId, b.A); b.P.SetVectorArray(BId, b.B); b.P.SetVectorArray(CId, b.C);
                    Graphics.DrawMeshInstanced(people[m], 0, matPerson, b.M, b.N, b.P, UnityEngine.Rendering.ShadowCastingMode.Off, true, 0, cam);     // the patch under the feet stands in for the shadow (a 1.7 m figure's map shadow drifts off its feet at city scale)
                }
            DrawFlags(cam, cp);
            DrawBirds(cam, cp, t, hour);
        }
        int wantedNow;

        /// <summary>Run counters (RoadCounters, every 10 s): the street people drawn in the last frame, and how many of them stand off every
        /// pavement, pedestrian street and bike path (FilmRoads.OnSurface; the people of the landmark squares and of the park walks are not
        /// counted). No allocation.</summary>
        public void Counters(out int alive, out int off) => Counters(out alive, out off, out _, out _);
        /// <summary>The same, and the people of the park walks drawn in the last frame with how many of them stand where the ground drawn
        /// under their feet is not paved (GroundTypes.HardAt, or a film road surface): on the grass beside a walk.</summary>
        public void Counters(out int alive, out int off, out int parkAlive, out int parkOff)
        {
            alive = 0; off = 0; parkAlive = 0; parkOff = 0;
            if (!ready || batches == null || Time.frameCount - shownFrame > 2) return;
            var gt = GroundTypes.Instance;
            for (int m = 0; m < 3; m++)
                foreach (var b in batches[m])
                    for (int i = 0; i < b.N; i++)
                    {
                        var c = b.M[i].GetColumn(3);
                        if (b.Park[i]) { parkAlive++; if (gt != null && !Paved(gt, new Vector2(c.x, c.z))) parkOff++; continue; }
                        if (b.Site[i]) continue;
                        alive++;
                        if (!FilmRoads.OnSurface(new Vector3(c.x, c.y, c.z), 0.6f, false)) off++;
                    }
        }
        static float Flat(Vector3 d) => Mathf.Sqrt(d.x * d.x + d.z * d.z);

        int Fill(Crowd c, Vector3 cp, float Rd, float t, float share, float parkShare, int year, int sc, int cap, int shown, bool site)
        {
            if (Flat(c.Centre - cp) > Rd + c.Radius) return shown;
            var runs = c.Runs; var ppl = c.People;
            for (int i = 0; i < ppl.Length && shown < cap; i++)
            {
                ref var p = ref ppl[i];
                bool park = p.Run >= 0 && runs[p.Run].Park;            // a park's walk: busy by the hour, not by the floor area round it
                if (p.Rank > (park ? parkShare : share)) continue;
                Vector3 pos; float yaw, fade = 1f, walk = p.Speed > 0f ? 1f : 0f;
                if (p.Run >= 0)
                {
                    var r = runs[p.Run]; if (!site && r.Years[sc] > year) continue;
                    // walk to the end of the path, turn round and walk back (no one appears or vanishes on the way)
                    float u2 = p.Speed > 0f ? Mathf.Repeat(p.S0 + p.Speed * t, 2f * r.Len) : p.S0; bool back = u2 > r.Len;
                    float s = back ? 2f * r.Len - u2 : u2; if (p.Rev) s = r.Len - s; bool rev = p.Rev ^ back;
                    float fi = s / r.St; int k = Mathf.Min((int)fi, r.P.Length - 2); float u = fi - k;
                    Vector3 a = r.P[k], b = r.P[k + 1], dir = b - a; if (rev) dir = -dir;
                    pos = Vector3.Lerp(a, b, u); var side = new Vector3(b.z - a.z, 0f, a.x - b.x).normalized; pos += side * p.Lat;     // keeps its side of the path both ways
                    yaw = p.Speed > 0f ? Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg : p.Yaw;
                }
                else { pos = p.Pos; yaw = p.Yaw; }
                float dist = (pos - cp).magnitude; if (dist > Rd) continue;
                fade *= Mathf.Clamp01((Rd - dist) / 60f);
                if (fade <= 0.01f) continue;
                var bs = batches[p.Mesh]; Batch bt = null; foreach (var x in bs) if (x.N < 1023) { bt = x; break; }
                if (bt == null) continue;
                int n = bt.N++;
                bt.M[n] = Matrix4x4.TRS(pos, Quaternion.Euler(0f, yaw, 0f), new Vector3(p.Scale, p.Scale, p.Scale));
                bt.A[n] = new Vector4(walk, p.Phase, 6.283f * p.Speed / 1.45f / Mathf.Max(p.Scale, 0.5f), fade);
                bt.B[n] = p.Top; bt.C[n] = p.Bot; bt.Site[n] = site || park; bt.Park[n] = park; shown++;
            }
            return shown;
        }

        void DrawFlags(Camera cam, Vector3 cp)
        {
            int nf = 0, nb = 0, np = 0;
            foreach (var s in sites)
            {
                if (s.Poles == null || !Done(s) || Flat(s.Centre - cp) > 2500f) continue;
                for (int k = 0; k < s.Poles.Length; k++)
                {
                    poleBatch.M[np] = s.Poles[k]; poleBatch.B[np] = new Vector4(0.80f, 0.81f, 0.82f, 0f); poleBatch.A[np] = Vector4.zero; poleBatch.C[np] = Vector4.zero; np++;
                    if (s.Tex[k] >= 0) { flagBatch.M[nf] = s.Cloth[k]; flagBatch.A[nf] = s.ClothA[k]; flagBatch.B[nf] = FlagRect[s.Tex[k]]; flagBatch.C[nf] = Vector4.zero; nf++; }     // B: its cell of the atlas
                    else { bannerBatch.M[nb] = s.Cloth[k]; bannerBatch.A[nb] = s.ClothA[k]; bannerBatch.B[nb] = s.ClothB[k]; bannerBatch.C[nb] = s.ClothC[k]; nb++; }
                }
            }
            void Go(Batch b, int n, Mesh m, Material mat)
            {
                if (n == 0) return;
                b.P.SetVectorArray(AId, b.A); b.P.SetVectorArray(BId, b.B); b.P.SetVectorArray(CId, b.C);
                Graphics.DrawMeshInstanced(m, 0, mat, b.M, n, b.P, UnityEngine.Rendering.ShadowCastingMode.On, true, 0, cam);
            }
            Go(poleBatch, np, pole, matPole); Go(flagBatch, nf, cloth, matFlag); Go(bannerBatch, nb, cloth, matBanner);
        }

        // ------------------------------------------------------------------ birds: a few loose flocks circling by day
        class Flock { public Vector3 C; public float R, Alt, W, A0; public int N; public bool On; public Vector3[] Off; public float[] Ph; }
        Flock[] flocks;
        void DrawBirds(Camera cam, Vector3 cp, float t, float hour)
        {
            if (FilmLook.Night > 0.3f || hour < 6.5f || hour > 19.5f) return;
            Vector3 f = cp, fwd = cam.transform.forward;
            if (flocks == null)
            {
                int nfk = High ? 4 : 3; flocks = new Flock[nfk]; var rng = new System.Random(77);
                for (int i = 0; i < nfk; i++)
                {
                    var fl = flocks[i] = new Flock { N = High ? 7 + rng.Next(6) : 5 + rng.Next(3) };
                    fl.Off = new Vector3[fl.N]; fl.Ph = new float[fl.N];
                    for (int k = 0; k < fl.N; k++) { fl.Off[k] = new Vector3(((float)rng.NextDouble() - 0.5f) * 14f, ((float)rng.NextDouble() - 0.5f) * 4f, ((float)rng.NextDouble() - 0.5f) * 10f - k * 1.2f); fl.Ph[k] = (float)rng.NextDouble() * 6.28f; }
                }
            }
            if (Time.time - lastBirdT > 1f)
            {
                lastBirdT = Time.time;
                for (int i = 0; i < flocks.Length; i++) { var fl = flocks[i]; if (!fl.On || Flat(fl.C - f) > 1300f) PlaceFlock(fl, f, fwd, i); }
            }
            int n = 0;
            foreach (var fl in flocks)
            {
                if (!fl.On) continue;
                float ang = fl.A0 + fl.W * t; var c = fl.C + new Vector3(Mathf.Cos(ang), 0f, Mathf.Sin(ang)) * fl.R;
                var tan = new Vector3(-Mathf.Sin(ang), 0f, Mathf.Cos(ang)) * Mathf.Sign(fl.W);
                var rot = Quaternion.LookRotation(tan) * Quaternion.Euler(0f, 0f, -Mathf.Sign(fl.W) * 12f);
                float flap = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(Mathf.Sin(t * 0.7f + fl.A0) * 1.5f + 0.3f));       // spells of flapping and gliding
                for (int k = 0; k < fl.N && n < 1023; k++)
                {
                    var o = fl.Off[k] + new Vector3(Mathf.Sin(t * 0.5f + fl.Ph[k]) * 1.5f, Mathf.Sin(t * 0.8f + fl.Ph[k] * 2f) * 0.8f, 0f);
                    var p = c + rot * o; p.y = fl.Alt + CityGround.HeightAt(c.x, c.z) + o.y;
                    if ((p - cp).magnitude > 2500f) continue;
                    birdBatch.M[n] = Matrix4x4.TRS(p, rot, Vector3.one * 1.7f);
                    birdBatch.A[n] = new Vector4(flap, fl.Ph[k], 22f + 4f * Mathf.Sin(fl.Ph[k]), 1f); birdBatch.B[n] = Vector4.zero; birdBatch.C[n] = Vector4.zero; n++;
                }
            }
            if (n == 0) return;
            birdBatch.P.SetVectorArray(AId, birdBatch.A); birdBatch.P.SetVectorArray(BId, birdBatch.B); birdBatch.P.SetVectorArray(CId, birdBatch.C);
            Graphics.DrawMeshInstanced(bird, 0, matBird, birdBatch.M, n, birdBatch.P, UnityEngine.Rendering.ShadowCastingMode.Off, false, 0, cam);
        }

        /// <summary>A circle for a flock near the focus, 30–90 m up, clear of every building and tower on the way round.</summary>
        void PlaceFlock(Flock fl, Vector3 f, Vector3 fwd, int i)
        {
            var rng = new System.Random(i * 911 + (int)Time.time);
            fl.On = false;
            for (int tr = 0; tr < 24; tr++)
            {
                // most flocks in front of the camera (where they can be seen), the others anywhere round it
                float head = Mathf.Atan2(fwd.z, fwd.x), a = i < flocks.Length - 1 ? head + ((float)rng.NextDouble() - 0.5f) * 1.2f : (float)rng.NextDouble() * 6.283f, d = 120f + 300f * (float)rng.NextDouble();
                var c = f + new Vector3(Mathf.Cos(a), 0f, Mathf.Sin(a)) * d; float R = 50f + 90f * (float)rng.NextDouble(), alt = 30f + 60f * (float)rng.NextDouble();
                bool clear = true;
                foreach (var l in LandmarkSystem.Instance.Items)
                    if (!l.IsLrt && l.Height + 25f > alt && Flat(new Vector3(l.X, 0f, l.Z) - c) < R + 0.7f * l.Radius + 40f) { clear = false; break; }
                for (int k = 0; k < 16 && clear; k++)
                {
                    float b = k * 6.283f / 16f; var q = c + new Vector3(Mathf.Cos(b), 0f, Mathf.Sin(b)) * R; float g = CityGround.HeightAt(q.x, q.z);
                    if (IconicDistrict.InGate(q.x, q.z) || IconicDistrict.InGate(c.x, c.z)) { clear = false; break; }   // its towers have no colliders
                    if (Physics.Raycast(new Vector3(q.x, g + alt + 400f, q.z), Vector3.down, out var hit, 2000f, ~0, QueryTriggerInteraction.Ignore) && hit.point.y > g + alt - 25f) clear = false;
                }
                if (!clear) continue;
                fl.C = c; fl.R = R; fl.Alt = alt; fl.W = (rng.Next(2) == 0 ? 1f : -1f) * 11f / R; fl.A0 = (float)rng.NextDouble() * 6.283f; fl.On = true; return;
            }
        }

        // ------------------------------------------------------------------ meshes (built here; the shader moves them)
        class MB
        {
            public readonly List<Vector3> V = new List<Vector3>(), N = new List<Vector3>(); public readonly List<Color> Col = new List<Color>(); public readonly List<Vector2> U = new List<Vector2>(); public readonly List<int> T = new List<int>();
            public void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 n, Color col, Vector2 uv)
            {
                int k = V.Count; V.Add(a); V.Add(b); V.Add(c); V.Add(d); for (int i = 0; i < 4; i++) { N.Add(n); Col.Add(col); U.Add(uv); }
                T.Add(k); T.Add(k + 1); T.Add(k + 2); T.Add(k); T.Add(k + 2); T.Add(k + 3);
            }
            /// <summary>A box from lo to hi (top narrower by 'taper' on x), one part colour and limb.</summary>
            public void Box(Vector3 lo, Vector3 hi, int part, int limb, float pivot, float taper = 0f)
            {
                var col = new Color(part / 8f, 0f, 0f, 1f); var uv = new Vector2(limb, pivot);
                float x0 = lo.x, x1 = hi.x, y0 = lo.y, y1 = hi.y, z0 = lo.z, z1 = hi.z, tx0 = x0 + taper, tx1 = x1 - taper;
                Vector3 a = new Vector3(x0, y0, z0), b = new Vector3(x1, y0, z0), c = new Vector3(x1, y0, z1), d = new Vector3(x0, y0, z1);
                Vector3 e = new Vector3(tx0, y1, z0), f = new Vector3(tx1, y1, z0), g = new Vector3(tx1, y1, z1), h = new Vector3(tx0, y1, z1);
                Quad(a, e, f, b, Vector3.back, col, uv); Quad(c, g, h, d, Vector3.forward, col, uv);
                Quad(d, h, e, a, Vector3.left, col, uv); Quad(b, f, g, c, Vector3.right, col, uv);
                Quad(e, h, g, f, Vector3.up, col, uv); Quad(a, b, c, d, Vector3.down, col, uv);
            }
            public Mesh Make(string name)
            {
                var m = new Mesh { name = name }; m.SetVertices(V); m.SetNormals(N); m.SetColors(Col); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateBounds();
                var bb = m.bounds; bb.Expand(1.2f); m.bounds = bb; return m;          // room for the animated limbs
            }
        }

        /// <summary>A person 1.75 m tall facing +z: 0 trousers and a jacket, 1 a skirt or dress and a jacket, 2 a long coat.
        /// Parts: 0 skin, 1 hair, 2 top, 3 bottom, 4 shoes; limbs 1/2 legs (pivot at the hip), 3/4 arms (pivot at the shoulder).</summary>
        static Mesh PersonMesh(int kind)
        {
            var b = new MB(); const float hip = 0.90f, sh = 1.42f;
            float tw = kind == 0 ? 0.21f : 0.18f, td = 0.12f, lx = kind == 0 ? 0.095f : 0.085f;
            for (int s = -1; s <= 1; s += 2)
            {
                int leg = s < 0 ? 1 : 2, arm = s < 0 ? 3 : 4; float x = lx * s;
                b.Box(new Vector3(x - 0.055f, 0f, -0.06f), new Vector3(x + 0.055f, 0.08f, 0.16f), 4, leg, hip);                                  // shoe
                b.Box(new Vector3(x - 0.065f, 0.08f, -0.07f), new Vector3(x + 0.065f, hip + 0.02f, 0.07f), kind == 1 ? 4 : 3, leg, hip, 0f);         // leg (tights under a skirt)
                float ax = (tw + 0.05f) * s;
                b.Box(new Vector3(ax - 0.045f, 0.83f, -0.05f), new Vector3(ax + 0.045f, sh + 0.02f, 0.05f), 2, arm, sh);                          // sleeve
                b.Box(new Vector3(ax - 0.04f, 0.73f, -0.04f), new Vector3(ax + 0.04f, 0.83f, 0.04f), 0, arm, sh);                                // hand
            }
            if (kind == 1) b.Box(new Vector3(-tw - 0.05f, 0.52f, -td - 0.03f), new Vector3(tw + 0.05f, hip + 0.04f, td + 0.03f), 3, 0, 0f, 0.06f);       // skirt
            float t0 = kind == 2 ? 0.60f : hip - 0.02f;
            b.Box(new Vector3(-tw, t0, -td), new Vector3(tw, sh + 0.04f, td), 2, 0, 0f, 0.02f);                                                       // torso
            b.Box(new Vector3(-0.045f, sh + 0.04f, -0.045f), new Vector3(0.045f, 1.52f, 0.045f), 0, 0, 0f);                                         // neck
            b.Box(new Vector3(-0.085f, 1.51f, -0.10f), new Vector3(0.085f, 1.71f, 0.10f), 0, 0, 0f, 0.01f);                                        // head
            b.Box(new Vector3(-0.092f, 1.64f, -0.108f), new Vector3(0.092f, 1.75f, 0.09f), 1, 0, 0f, 0.015f);                                     // hair
            if (kind == 1) b.Box(new Vector3(-0.09f, 1.50f, -0.115f), new Vector3(0.09f, 1.66f, -0.06f), 1, 0, 0f);                                // longer hair at the back
            // a soft dark patch under the feet (part 6): the figure stands on the ground at any distance, whatever the shadow map does
            var sc = new Color(6f / 8f, 0f, 0f, 1f); const int segs = 10;
            for (int i = 0; i < segs; i++)
            {
                float a0 = i * Mathf.PI * 2f / segs, a1 = (i + 1) * Mathf.PI * 2f / segs; int k = b.V.Count;
                b.V.Add(new Vector3(0f, 0.012f, 0.03f)); b.V.Add(new Vector3(Mathf.Cos(a1) * 0.30f, 0.012f, 0.03f + Mathf.Sin(a1) * 0.24f)); b.V.Add(new Vector3(Mathf.Cos(a0) * 0.30f, 0.012f, 0.03f + Mathf.Sin(a0) * 0.24f));
                for (int q = 0; q < 3; q++) { b.N.Add(Vector3.up); b.Col.Add(sc); b.U.Add(new Vector2(0f, q == 0 ? 0f : 1f)); }     // uv.y: 0 middle .. 1 rim
                b.T.Add(k); b.T.Add(k + 1); b.T.Add(k + 2);
            }
            return b.Make(kind == 0 ? "Person trousers" : kind == 1 ? "Person skirt" : "Person coat");
        }

        /// <summary>The cloth of a flag: a 1 × 1 grid from the pole (x 0) to the fly end (x 1), bottom to top, seen from both sides.</summary>
        static Mesh ClothMesh()
        {
            var V = new List<Vector3>(); var U = new List<Vector2>(); var N = new List<Vector3>(); var T = new List<int>(); const int nx = 12, ny = 5;
            for (int j = 0; j <= ny; j++) for (int i = 0; i <= nx; i++) { V.Add(new Vector3(i / (float)nx, j / (float)ny, 0f)); U.Add(new Vector2(i / (float)nx, j / (float)ny)); N.Add(Vector3.forward); }
            for (int j = 0; j < ny; j++) for (int i = 0; i < nx; i++) { int a = j * (nx + 1) + i, b = a + 1, c = a + nx + 1, d = c + 1; T.Add(a); T.Add(c); T.Add(b); T.Add(b); T.Add(c); T.Add(d); }
            var m = new Mesh { name = "Flag cloth" }; m.SetVertices(V); m.SetUVs(0, U); m.SetNormals(N); m.SetTriangles(T, 0); m.RecalculateBounds();
            var bb = m.bounds; bb.Expand(0.6f); m.bounds = bb; return m;
        }

        /// <summary>A flagpole 14.6 m tall with a finial on top.</summary>
        static Mesh PoleMesh()
        {
            var b = new MB();
            b.Box(new Vector3(-0.075f, 0f, -0.075f), new Vector3(0.075f, 14.45f, 0.075f), 0, 0, 0f, 0.02f);
            b.Box(new Vector3(-0.11f, 14.45f, -0.11f), new Vector3(0.11f, 14.65f, 0.11f), 0, 0, 0f, 0.03f);
            b.Box(new Vector3(-0.22f, 0f, -0.22f), new Vector3(0.22f, 0.32f, 0.22f), 0, 0, 0f, 0.04f);
            for (int i = 0; i < b.Col.Count; i++) b.Col[i] = Color.white;
            return b.Make("Flag pole");
        }

        /// <summary>A small bird seen from below or the side: a slim body along +z and two wings (uv.x side, uv.y distance from the body).</summary>
        static Mesh BirdMesh()
        {
            var V = new List<Vector3>(); var U = new List<Vector2>(); var T = new List<int>();
            void Tri(Vector3 a, Vector2 ua, Vector3 b, Vector2 ub, Vector3 c, Vector2 uc) { int k = V.Count; V.Add(a); V.Add(b); V.Add(c); U.Add(ua); U.Add(ub); U.Add(uc); T.Add(k); T.Add(k + 1); T.Add(k + 2); }
            Vector3 nose = new Vector3(0f, 0f, 0.20f), tail = new Vector3(0f, 0f, -0.20f), l = new Vector3(-0.04f, 0f, 0f), r = new Vector3(0.04f, 0f, 0f), up = new Vector3(0f, 0.04f, 0f);
            Tri(nose, Vector2.zero, l, Vector2.zero, up, Vector2.zero); Tri(nose, Vector2.zero, up, Vector2.zero, r, Vector2.zero);
            Tri(tail, Vector2.zero, up, Vector2.zero, l, Vector2.zero); Tri(tail, Vector2.zero, r, Vector2.zero, up, Vector2.zero);
            Tri(tail, Vector2.zero, l + new Vector3(-0.04f, 0f, -0.24f), Vector2.zero, r + new Vector3(0.04f, 0f, -0.24f), Vector2.zero);          // tail fan
            for (int s = -1; s <= 1; s += 2)
            {
                Vector3 root0 = new Vector3(0.03f * s, 0f, 0.07f), root1 = new Vector3(0.03f * s, 0f, -0.06f), mid0 = new Vector3(0.26f * s, 0.02f, 0.05f), mid1 = new Vector3(0.26f * s, 0.02f, -0.09f), tip = new Vector3(0.50f * s, 0f, -0.10f);
                Vector2 u0 = new Vector2(s, 0f), um = new Vector2(s, 0.5f), ut = new Vector2(s, 1f);
                Tri(root0, u0, mid0, um, root1, u0); Tri(root1, u0, mid0, um, mid1, um); Tri(mid0, um, tip, ut, mid1, um);
            }
            var m = new Mesh { name = "Bird" }; m.SetVertices(V); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateNormals();
            var bb = new Bounds(Vector3.zero, new Vector3(1.4f, 1.0f, 1.0f)); m.bounds = bb; return m;
        }

        // ------------------------------------------------------------------ the cloths of the flags: one atlas, one instanced draw
        /// <summary>The flags of the atlas: Kazakhstan, China, the Republic of Korea, the qTwin logo.</summary>
        const int FlagKz = 0, FlagCn = 1, FlagKr = 2, FlagLogo = 3, AtlasW = 1024, AtlasH = 512;
        /// <summary>Where each flag lies in the atlas: uv offset (xy) and size (zw), the _LifeB of its cloth (AlatauLife, kind 1).</summary>
        static readonly Vector4[] FlagRect = new Vector4[4];

        /// <summary>The cloths of the flags in one atlas of 1024 × 512, a cell of 512 × 256 each with the flag in its middle and its edge
        /// colours carried out to the border of the cell (nothing of a neighbour bleeds in at a distance): Kazakhstan 2:1 (480 × 240),
        /// China, the Republic of Korea and the qTwin logo 3:2 (360 × 240). Drawn with 2 × 2 samples a pixel.</summary>
        static Texture2D FlagAtlas()
        {
            var px = new Color32[AtlasW * AtlasH];
            for (int f = 0; f < 4; f++)
            {
                int w = f == FlagKz ? 480 : 360, h = 240, cx = (f & 1) * 512, cy = (f >> 1) * 256, x0 = cx + (512 - w) / 2, y0 = cy + (256 - h) / 2;
                FlagRect[f] = new Vector4(x0 / (float)AtlasW, y0 / (float)AtlasH, w / (float)AtlasW, h / (float)AtlasH);
                if (f == FlagLogo) Logo(px, x0, y0, w, h);
                else
                    for (int y = 0; y < h; y++) for (int x = 0; x < w; x++)
                    {
                        int r = 0, g = 0, b = 0;
                        for (int q = 0; q < 4; q++)
                        {
                            float u = (x + 0.25f + 0.5f * (q & 1)) / h, v = (y + 0.25f + 0.5f * (q >> 1)) / h;      // in heights of the flag
                            var c = f == FlagKz ? Kz(u, v) : f == FlagCn ? Cn(u, v) : Kr(u, v);
                            r += c.r; g += c.g; b += c.b;
                        }
                        px[(y0 + y) * AtlasW + x0 + x] = new Color32((byte)((r + 2) >> 2), (byte)((g + 2) >> 2), (byte)((b + 2) >> 2), 255);
                    }
                for (int y = cy; y < cy + 256; y++) for (int x = cx; x < cx + 512; x++)
                {
                    int qx = Mathf.Clamp(x, x0, x0 + w - 1), qy = Mathf.Clamp(y, y0, y0 + h - 1);
                    if (qx != x || qy != y) px[y * AtlasW + x] = px[qy * AtlasW + qx];
                }
            }
            var t = new Texture2D(AtlasW, AtlasH, TextureFormat.RGBA32, true) { name = "Flags", wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Trilinear, anisoLevel = 2 };
            t.SetPixels32(px); t.Apply(true, true); return t;
        }

        static readonly Color32 KzBlue = new Color32(0, 175, 202, 255), KzGold = new Color32(254, 197, 0, 255);
        /// <summary>The flag of Kazakhstan (2:1) at (u, v) in heights of the flag from the lower hoist corner: sky blue, the golden sun
        /// with its 32 rays and the steppe eagle under it, the national ornament along the hoist.</summary>
        static Color32 Kz(float u, float v)
        {
            // the sun and its 32 rays
            float dx = u - 1.0f, dy = v - 0.60f, r2 = dx * dx + dy * dy;
            if (r2 < 0.125f * 0.125f) return KzGold;
            if (r2 > 0.145f * 0.145f && r2 < 0.245f * 0.245f)
            {
                float r = Mathf.Sqrt(r2), a = Mathf.Atan2(dy, dx);
                if (Mathf.Repeat(a / (Mathf.PI * 2f) * 32f, 1f) < 0.42f * (1f - (r - 0.145f) / 0.13f) + 0.12f) return KzGold;
            }
            // the eagle: spread wings in an arc under the sun, thinner towards the tips, a small body and head in the middle
            float ax = Mathf.Abs(dx);
            if (ax < 0.36f)
            {
                float wy = 0.30f + 0.32f * ax - 0.55f * ax * ax, th = 0.055f * (1f - ax / 0.40f) + 0.012f;
                if (Mathf.Abs(v - wy) < th && ax > 0.02f) return KzGold;
                if (ax < 0.03f && v > 0.25f && v < 0.36f) return KzGold;
            }
            // the ornament along the hoist: a column of linked curls
            if (u > 0.05f && u < 0.16f)
            {
                float cy = Mathf.Repeat(v * 5f, 1f) - 0.5f, cx = (u - 0.105f) / 0.055f;
                float rr = Mathf.Sqrt(cx * cx + cy * cy * 4f);
                if ((rr > 0.55f && rr < 0.85f && Mathf.Abs(cx) > 0.15f) || Mathf.Abs(cx) < 0.12f) return KzGold;
            }
            return KzBlue;
        }

        static readonly Color32 CnRed = new Color32(238, 28, 37, 255), CnYellow = new Color32(255, 255, 0, 255);
        static readonly Vector2[] CnSmall = { new Vector2(10f, 2f), new Vector2(12f, 4f), new Vector2(12f, 7f), new Vector2(10f, 9f) };
        /// <summary>The flag of the People's Republic of China (3:2, GB 12982-2004) at (u, v): red, in the upper hoist quarter (a grid of
        /// 15 × 10 cells from the upper hoist corner) the large yellow star at (5, 5), radius 3, a point straight up, and the four small
        /// stars, radius 1, at (10, 2), (12, 4), (12, 7), (10, 9), each with a point towards the centre of the large one.</summary>
        static Color32 Cn(float u, float v)
        {
            float gx = u * 20f, gy = (1f - v) * 20f;                  // cells of the standard's grid (30 × 20 on the whole flag), y down
            if (gx > 13.5f || gy > 10.5f) return CnRed;
            if (Star(gx, gy, 5f, 5f, 3f, -90f)) return CnYellow;
            foreach (var c in CnSmall) if (Star(gx, gy, c.x, c.y, 1f, Mathf.Atan2(5f - c.y, 5f - c.x) * Mathf.Rad2Deg)) return CnYellow;
            return CnRed;
        }
        /// <summary>Whether (x, y) is inside the regular five-pointed star at (cx, cy) of outer radius R with a point at angle a0 (degrees).</summary>
        static bool Star(float x, float y, float cx, float cy, float R, float a0)
        {
            float dx = x - cx, dy = y - cy, r2 = dx * dx + dy * dy; if (r2 > R * R) return false;
            float ri = R * 0.381966f;                                 // the inner corners (1/φ² of the points)
            if (r2 < ri * ri * 0.65f) return true;
            float f = Mathf.Repeat(Mathf.Atan2(dy, dx) * Mathf.Rad2Deg - a0, 72f); f = Mathf.Min(f, 72f - f) * Mathf.Deg2Rad;     // from the nearest point
            float rb = R * ri * 0.5877853f / (ri * Mathf.Sin(0.6283185f - f) + R * Mathf.Sin(f));                               // the edge from the point to the inner corner
            return r2 <= rb * rb;
        }

        static readonly Color32 KrRed = new Color32(205, 46, 58, 255), KrBlue = new Color32(0, 71, 160, 255), KrBlack = new Color32(0, 0, 0, 255), FlagWhite = new Color32(255, 255, 255, 255);
        /// <summary>The flag of the Republic of Korea (3:2) at (u, v), in the units of its standard (the flag 72 × 48, the taegeuk of
        /// diameter 24 in the middle): white; the taegeuk red above and blue below the diagonal from the upper hoist corner, divided by an S
        /// of two half circles on that diagonal (the red one on the hoist half); the four black trigrams on the diagonals, 6 from the
        /// taegeuk, bars 12 × 2 one apart, broken by a gap of 1: ☰ geon upper hoist, ☵ gam upper fly, ☲ ri lower hoist, ☷ gon lower fly.</summary>
        static Color32 Kr(float u, float v)
        {
            float x = (u - 0.75f) * 48f, y = (v - 0.5f) * 48f;
            const float ex = 0.8320503f, ey = 0.5547002f;             // (3, 2) / √13: along the diagonals
            float r2 = x * x + y * y;
            if (r2 <= 144f)
            {
                float ux = x + 6f * ex, uy = y - 6f * ey, lx = x - 6f * ex, ly = y + 6f * ey;      // from the middles of the two half circles
                if (ux * ux + uy * uy <= 36f) return KrRed;
                if (lx * lx + ly * ly <= 36f) return KrBlue;
                return x * ey + y * ex > 0f ? KrRed : KrBlue;
            }
            for (int k = 0; k < 2; k++)
            {
                float ax = k == 0 ? -ex : ex, t = x * ax + y * ey, sd = Mathf.Abs(-x * ey + y * ax), at = Mathf.Abs(t);
                if (at < 18f || at > 26f || sd > 6f) continue;
                int bar = at <= 20f ? 0 : at < 21f ? -1 : at <= 23f ? 1 : at < 24f ? -1 : 2;          // inner, middle, outer
                if (bar < 0) return FlagWhite;
                int broken = k == 0 ? (t > 0f ? 0 : 7) : (t > 0f ? 5 : 2);                          // bit per bar: ☰ none, ☷ all, ☵ inner and outer, ☲ middle
                return ((broken >> bar) & 1) != 0 && sd < 0.5f ? FlagWhite : KrBlack;
            }
            return FlagWhite;
        }

        static readonly Color32 LogoCloth = new Color32(24, 26, 31, 255);
        /// <summary>The easter egg: the qTwin logo of the header (Resources UI/qtwin_logo) in the middle of a dark cloth, as on the header.
        /// The logo is not readable on the CPU: it is drawn into a small render texture once and read back. A drawn gear if it is missing.</summary>
        static void Logo(Color32[] px, int x0, int y0, int w, int h)
        {
            var src = Resources.Load<Texture2D>("UI/qtwin_logo");
            int lh = Mathf.RoundToInt(h * 0.70f), lw = src != null ? Mathf.RoundToInt(lh * src.width / (float)src.height) : lh;
            Color32[] lp = null;
            if (src != null)
            {
                var rt = RenderTexture.GetTemporary(lw, lh, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Default); var was = RenderTexture.active;
                Graphics.Blit(src, rt); RenderTexture.active = rt;
                var rd = new Texture2D(lw, lh, TextureFormat.RGBA32, false); rd.ReadPixels(new Rect(0, 0, lw, lh), 0, 0); rd.Apply(false);
                RenderTexture.active = was; RenderTexture.ReleaseTemporary(rt);
                lp = rd.GetPixels32(); Destroy(rd);
            }
            int ox = (w - lw) / 2, oy = (h - lh) / 2;
            for (int y = 0; y < h; y++) for (int x = 0; x < w; x++)
            {
                int lx = x - ox, ly = y - oy; Color32 c = LogoCloth; float a = 0f;
                if (lx >= 0 && ly >= 0 && lx < lw && ly < lh)
                {
                    if (lp != null) { c = lp[ly * lw + lx]; a = c.a / 255f; }
                    else
                    {
                        // a white gear round a red and a green arc open to the right, as the logo
                        float fx = (lx + 0.5f) / lh - 0.5f, fy = (ly + 0.5f) / lh - 0.5f, r = Mathf.Sqrt(fx * fx + fy * fy), an = Mathf.Atan2(fy, fx) * Mathf.Rad2Deg;
                        bool open = Mathf.Abs(an) < 40f, tooth = Mathf.Repeat(an + 11.25f, 45f) < 22.5f;
                        if ((r > 0.36f && r < 0.43f) || (r >= 0.43f && r < 0.5f && tooth)) { c = FlagWhite; a = 1f; }
                        else if (!open && r > 0.24f && r < 0.31f) { c = new Color32(226, 36, 41, 255); a = 1f; }
                        else if (!open && r > 0.14f && r < 0.20f) { c = new Color32(48, 214, 64, 255); a = 1f; }
                    }
                }
                var o = Color32.Lerp(LogoCloth, c, a); o.a = 255;
                px[(y0 + y) * AtlasW + x0 + x] = o;
            }
        }

        static float Dist(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-6f)); return (p - (a + ab * t)).magnitude;
        }
    }
}
