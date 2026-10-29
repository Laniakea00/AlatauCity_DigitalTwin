using System;
using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Landmarks;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The "video" of a city camera — a stub: a second Unity camera stands where the CCTV camera is (a traffic or street camera
    /// on its pole by the nearest street, a site camera over the plot), slowly pans like a PTZ camera and renders the twin into a small
    /// texture (10 frames a second, only while a feed is on screen). In front of it live what the camera watches (FeedActors): cars and
    /// buses on the street, people on the pavements, workers, an excavator and a dump truck on a site — seen only by this camera. The
    /// video-analytics boxes are worked out from them every frame the picture is taken: each box sits on a real figure in the picture,
    /// follows it and leaves when it walks out of the frame or behind a building. On top: REC, camera id, clock and the «ДЕМО-ПОТОК» mark —
    /// the real RTSP / Smart City stream replaces the texture later.</summary>
    public class FeedRig : MonoBehaviour
    {
        public static FeedRig Instance;
        public static RenderTexture Texture => Instance != null ? Instance.rt : null;
        /// <summary>The boxes of the last picture: rect in the picture (0..1, y up), the label, the colour.</summary>
        public struct Det { public Rect R; public string Tag; public Color C; }
        public static readonly List<Det> Dets = new List<Det>();
        public const int Layer = 28;                       // what the camera watches is drawn only into its picture
        Camera cam; RenderTexture rt; float next; int users;
        Vector3 pos; float heading, pitch = 14f, span = 28f, fov = 52f; float ptz;
        readonly FeedActors actors = new FeedActors();

        public static FeedRig Ensure()
        {
            if (Instance == null) new GameObject("Twin camera feed").AddComponent<FeedRig>();
            return Instance;
        }
        void Awake()
        {
            Instance = this;
            rt = new RenderTexture(512, 288, 24) { name = "cctv_feed", antiAliasing = 2 }; rt.Create();
            cam = gameObject.AddComponent<Camera>(); cam.enabled = false;
        }
        void OnDestroy() { if (rt != null) rt.Release(); actors.Clear(); }

        /// <summary>Points the rig at a CCTV camera and sets up what it watches.</summary>
        public void Look(SmartCity.Cctv c)
        {
            if (c == null) return;
            pos = c.World; heading = c.Heading; ptz = 0f; span = 28f; fov = 52f;
            // the view looks down at the street in front of the camera, not into the sky
            float g = CityGround.HeightAt(pos.x, pos.z); float h = Mathf.Max(18f, pos.y - g);
            pitch = Mathf.Clamp(Mathf.Atan2(h, 340f) * Mathf.Rad2Deg, 5f, 20f);
            var pose = actors.Stage(c, TwinState.Year);
            if (pose.ok) { pos = pose.eye; heading = pose.yaw; pitch = pose.pitch; span = pose.span; fov = pose.fov; }
            Dets.Clear(); next = 0f;
        }
        public void Use(bool on) { users = Mathf.Max(0, users + (on ? 1 : -1)); if (users == 0) { actors.Clear(); Dets.Clear(); } }

        void LateUpdate()
        {
            var main = Camera.main;
            if (main != null && (main.cullingMask & (1 << Layer)) != 0) main.cullingMask &= ~(1 << Layer);
            if (users <= 0) return;
            float rd = TwinState.RealDelta; ptz += rd; next -= rd;
            actors.Tick(rd);
            if (next > 0f) return; next = 0.1f;
            if (main == null) return;
            cam.CopyFrom(main); cam.enabled = false; cam.targetTexture = rt; cam.fieldOfView = fov; cam.cullingMask = main.cullingMask | (1 << Layer);
            cam.nearClipPlane = 0.5f; cam.farClipPlane = 20000f;
            float yaw = heading + Mathf.Sin(ptz * 0.18f) * span;   // PTZ: slow pan left — right
            cam.transform.SetPositionAndRotation(pos, Quaternion.Euler(pitch, yaw, 0f));
            actors.Detect(cam, rt.height, Dets);
            try { cam.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] feed: " + e.Message); users = 0; }
        }
    }

    /// <summary>What a city camera watches, made for its picture only (layer FeedRig.Layer): traffic on the nearest street (and, in the
    /// presentation, the crash the camera reports), people on the pavements, a construction site with its workers and machines. Each
    /// actor is a small mesh of the landmark material that moves on its own path; Detect projects the ones the camera really sees.</summary>
    public class FeedActors
    {
        enum K { Car, Bus, Person, Worker, Excavator, Truck }
        class A
        {
            public K Kind; public GameObject Go; public Transform Up; public Renderer R; public Vector3 O, D; public float S, L, Speed, Lane, Phase; public bool PingPong, Flag, Static;
            public Vector3 Wander; public float WanderT;
            public Way W; public bool Rev, Walker;                             // on a street: along the way, backwards, on the pavement
        }
        readonly List<A> list = new List<A>(); GameObject root; static Material mat; float t;
        static readonly Dictionary<string, Mesh> meshes = new Dictionary<string, Mesh>();
        Vector3 eye; Vector3 crash; bool hasCrash;

        public void Clear() { if (root != null) UnityEngine.Object.Destroy(root); root = null; list.Clear(); hasCrash = false; }

        /// <summary>Places the camera and its scene. Returns the camera pose (eye, yaw, pitch, pan span, field of view).</summary>
        public (bool ok, Vector3 eye, float yaw, float pitch, float span, float fov) Stage(SmartCity.Cctv c, int year)
        {
            Clear(); t = 0f;
            var rnd = new System.Random(c.Id.GetHashCode());
            if (!c.Online) return (false, Vector3.zero, 0, 0, 0, 0);
            if (c.Type == SmartCity.CamType.Construction || c.Type == SmartCity.CamType.Utility) return Site(c, year, rnd);
            return Street(c, year, rnd);
        }

        // ------------------------------------------------------------------ the street: a pole by the nearest road, traffic, people
        (bool, Vector3, float, float, float, float) Street(SmartCity.Cctv c, int year, System.Random rnd)
        {
            // the street as it is drawn and runs on through the junctions (so traffic follows the bends), a few hundred metres each way;
            // without the film roads, the plan's edge and its straightest continuations
            var cp0 = new Vector2(c.World.x, c.World.z); Way way; Data.TwinData.RoadClass cls; bool oneWay = false;
            if (FilmRoads.DrawnWay(cp0, year, (int)TwinState.Scenario, 450f, 320f, out var line, out cls, out oneWay)) way = new Way(line);
            else
            {
                if (!NearestRoad(cp0, year, 450f, out _, out _, out int edge)) return (false, Vector3.zero, 0, 0, 0, 0);
                cls = Data.TwinData.Roads[edge].Cls; way = BuildWay(edge, year, 320f);
            }
            float sR = way.Project(cp0); way.At(sR, out var R, out var D);
            var N = new Vector2(-D.y, D.x);
            bool traffic = c.Type == SmartCity.CamType.Traffic;
            FilmRoads.Dims(cls, out float half, out float walk, out int lanes, out _);
            if (oneWay) switch (cls)                                             // one carriageway of a dual road: as FilmRoads draws it
            {
                case Data.TwinData.RoadClass.Highway: half = 6f; lanes = 3; break;
                case Data.TwinData.RoadClass.Ring: half = 5.5f; lanes = 3; break;
                case Data.TwinData.RoadClass.Main: half = 3.8f; lanes = 2; break;
                default: half = 3.2f; lanes = 1; break;
            }
            float lw = oneWay ? (2f * half - 0.8f) / lanes : (half - 0.4f) / lanes;
            // a traffic camera hangs on an arm over the outer lane, a street camera on a pole at the kerb: both look down the street
            // past the rows of street trees, not into their crowns
            float poleH = traffic ? 10f : 7.5f, side = traffic ? half - 1.2f : half + 0.6f;
            // the pole on the side of the street where the camera looks along it without a building in the way
            Vector3 best = Vector3.zero; float bestYaw = 0f, look1 = 1f; int bestSeen = -1;
            for (int k = 0; k < 4; k++)
            {
                var n = (k & 1) == 0 ? N : -N; float sg = k < 2 ? 1f : -1f; var d = D * sg;
                var foot = R + n * side - d * 20f; var e = new Vector3(foot.x, CityGround.HeightAt(foot.x, foot.y) + poleH, foot.y);
                int seen = 0; for (int i = 1; i <= 6; i++) { way.At(sR + sg * i * 18f, out var q, out _); if (Visible(e, new Vector3(q.x, CityGround.HeightAt(q.x, q.y) + 1f, q.y), year)) seen++; }
                if (seen > bestSeen) { bestSeen = seen; best = e; bestYaw = Mathf.Atan2(d.x, d.y) * Mathf.Rad2Deg; look1 = sg; }
            }
            eye = best;
            root = new GameObject("Camera feed · scene");
            // the yaw turns a little towards the street ahead (the pole stands at its side)
            way.At(sR + look1 * 55f, out var mid2, out _); var look = new Vector3(mid2.x, 0f, mid2.y) - eye; look.y = 0f; float yaw = Mathf.Atan2(look.x, look.z) * Mathf.Rad2Deg;
            // the crash the camera reports in the presentation: two cars stopped askew in the outer lane, 60 m ahead (the traffic of
            // that lane does not run there)
            hasCrash = traffic && TwinTour.Running;
            if (hasCrash)
            {
                way.At(sR + look1 * 60f, out var cp, out var cd); cd *= look1; var cr = new Vector2(cd.y, -cd.x);
                var c2d = cp + cr * (oneWay ? (lanes - 0.5f) * lw - half + 0.4f : (lanes - 0.5f) * lw); crash = new Vector3(c2d.x, 0f, c2d.y); var dir = new Vector3(cd.x, 0f, cd.y); var right = new Vector3(cr.x, 0f, cr.y);
                var c1 = Car(rnd, K.Car); Place(c1, crash, Quaternion.LookRotation(Quaternion.Euler(0, 24f, 0) * dir)); c1.Static = true;
                var c2 = Car(rnd, K.Car); Place(c2, crash + dir * 4.4f + right * 0.6f, Quaternion.LookRotation(Quaternion.Euler(0, -62f, 0) * dir)); c2.Static = true;
                c1.Flag = c2.Flag = true;
            }
            var taken = new List<(int lane, float s)>();
            int nCars = Mathf.RoundToInt((traffic ? (lanes > 1 ? 14 : 9) : 6) * Mathf.Clamp(way.Len / 460f, 0.6f, 1.8f));
            for (int i = 0; i < nCars; i++)
            {
                int lane = rnd.Next(lanes); bool fwd = oneWay || rnd.NextDouble() < 0.5;
                int crashLane = oneWay && look1 < 0f ? 0 : lanes - 1;               // the lane on the camera's right, ahead (one-way: whichever it is)
                if (hasCrash && (oneWay || fwd == look1 > 0f) && lane == crashLane) { if (lanes == 1) continue; lane = crashLane == 0 ? 1 : lanes - 2; }
                int key = fwd ? lane : -1 - lane; float s0 = 0f; bool ok = false;
                for (int tries = 0; tries < 12 && !ok; tries++) { s0 = (float)rnd.NextDouble() * way.Len; ok = true; foreach (var q in taken) if (q.lane == key && Mathf.Abs(q.s - s0) < 16f) { ok = false; break; } }
                if (!ok) continue; taken.Add((key, s0));
                // one speed per lane: cars of a lane keep their gaps, the outer lanes are slower
                float speed = (traffic ? 13f : 10f) - lane * 2.2f + (fwd ? 0f : 0.6f);
                var a = Car(rnd, traffic && rnd.NextDouble() < 0.12 ? K.Bus : K.Car); a.W = way; a.Rev = !fwd; a.S = s0; a.Speed = speed; a.Lane = oneWay ? (lane + 0.5f) * lw - half + 0.4f : (lane + 0.5f) * lw;
            }
            if (walk > 0f)
                for (int i = 0; i < (traffic ? 5 : 12); i++)
                {
                    var a = Person(rnd, false, false); a.W = way; a.Rev = rnd.NextDouble() < 0.5; a.S = (float)rnd.NextDouble() * way.Len; a.Speed = 1.1f + (float)rnd.NextDouble() * 0.6f;
                    a.Lane = (half + walk * (0.3f + 0.4f * (float)rnd.NextDouble())) * (rnd.NextDouble() < 0.5 ? 1f : -1f); a.Walker = true;
                }
            return (true, eye, yaw, traffic ? 11f : 14f, traffic ? 9f : 14f, traffic ? 44f : 48f);
        }

        /// <summary>A street as a polyline with its length along it.</summary>
        class Way
        {
            public Vector2[] P; public float[] C; public float Len;
            public Way(List<Vector2> pts)
            {
                var l = new List<Vector2>(); foreach (var q in pts) if (l.Count == 0 || (q - l[l.Count - 1]).sqrMagnitude > 0.25f) l.Add(q);
                if (l.Count < 2) l.Add(l[0] + Vector2.up);
                P = l.ToArray(); C = new float[P.Length]; for (int i = 1; i < P.Length; i++) C[i] = C[i - 1] + Vector2.Distance(P[i - 1], P[i]); Len = C[C.Length - 1];
            }
            /// <summary>The point at s metres along the way and the direction there (eased through the joints over 8 m).</summary>
            public void At(float s, out Vector2 p, out Vector2 d)
            {
                s = Mathf.Clamp(s, 0f, Len); int lo = 0, hi = P.Length - 1;
                while (hi - lo > 1) { int m = (lo + hi) >> 1; if (C[m] <= s) lo = m; else hi = m; }
                float L = C[hi] - C[lo]; d = L > 1e-4f ? (P[hi] - P[lo]) / L : Vector2.up; p = P[lo] + d * (s - C[lo]);
                if (hi + 1 < P.Length && C[hi] - s < 4f) { var dn = (P[hi + 1] - P[hi]).normalized; d = Vector2.Lerp(d, dn, 0.5f * (1f - (C[hi] - s) / 4f)).normalized; }
                else if (lo > 0 && s - C[lo] < 4f) { var dp = (P[lo] - P[lo - 1]).normalized; d = Vector2.Lerp(d, dp, 0.5f * (1f - (s - C[lo]) / 4f)).normalized; }
            }
            public float Project(Vector2 q)
            {
                float best = float.MaxValue, at = 0f;
                for (int i = 0; i + 1 < P.Length; i++)
                {
                    var ab = P[i + 1] - P[i]; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                    float u = Mathf.Clamp01(Vector2.Dot(q - P[i], ab) / L2); float dd = (P[i] + ab * u - q).sqrMagnitude;
                    if (dd < best) { best = dd; at = C[i] + u * Mathf.Sqrt(L2); }
                }
                return at;
            }
        }
        static Dictionary<int, List<int>> nodeEdges;
        /// <summary>The way through a road edge: at each end the straightest continuation (built by this year, turning less than ~55°),
        /// until 'reach' metres are added on each side.</summary>
        static Way BuildWay(int ei, int year, float reach)
        {
            var R = Data.TwinData.Roads; var nodes = Data.TwinData.RoadNodes; int sc = (int)TwinState.Scenario;
            if (nodeEdges == null)
            {
                nodeEdges = new Dictionary<int, List<int>>();
                for (int i = 0; i < R.Length; i++) foreach (int nd in new[] { R[i].A, R[i].B }) { if (!nodeEdges.TryGetValue(nd, out var l)) nodeEdges[nd] = l = new List<int>(); l.Add(i); }
            }
            var pts = new List<Vector2>(R[ei].Geom);
            for (int pass = 0; pass < 2; pass++)
            {
                if (pass == 1) pts.Reverse();
                int cur = ei; float len = 0f;
                for (int guard = 0; guard < 40 && len < reach; guard++)
                {
                    var end = pts[pts.Count - 1]; var dir = (end - pts[pts.Count - 2]).normalized;
                    var ce = R[cur]; int node = ce.A >= 0 && ce.A < nodes.Length && ce.B >= 0 && ce.B < nodes.Length
                        ? ((nodes[ce.A] - end).sqrMagnitude <= (nodes[ce.B] - end).sqrMagnitude ? ce.A : ce.B) : -1;
                    if (node < 0 || !nodeEdges.TryGetValue(node, out var list)) break;
                    int bestE = -1; float bestDot = 0.58f; Vector2[] bestG = null;
                    foreach (int k in list)
                    {
                        if (k == cur) continue; var e = R[k]; var g = e.Geom; if (g == null || g.Length < 2) continue;
                        if (e.Year != null && e.Year.Length > 0 && e.Year[Mathf.Min(sc, e.Year.Length - 1)] > year) continue;
                        bool fw = (g[0] - end).sqrMagnitude <= (g[g.Length - 1] - end).sqrMagnitude;
                        var g2 = fw ? g : (Vector2[])g.Clone(); if (!fw) Array.Reverse(g2);
                        int j = 1; while (j < g2.Length - 1 && (g2[j] - g2[0]).sqrMagnitude < 4f) j++;
                        float dot = Vector2.Dot(dir, (g2[j] - g2[0]).normalized) + (e.Cls == ce.Cls ? 0.12f : 0f);
                        if (dot > bestDot) { bestDot = dot; bestE = k; bestG = g2; }
                    }
                    if (bestE < 0) break;
                    for (int i = 1; i < bestG.Length; i++) { len += Vector2.Distance(pts[pts.Count - 1], bestG[i]); pts.Add(bestG[i]); }
                    cur = bestE;
                }
            }
            return new Way(pts);
        }

        // ------------------------------------------------------------------ a site: the camera on a mast at the plot, machines and crew
        (bool, Vector3, float, float, float, float) Site(SmartCity.Cctv c, int year, System.Random rnd)
        {
            var db = CityDatabase.Instance; BuildingInfo b = null; float bd = float.MaxValue;
            if (db != null) foreach (var q in db.Buildings) { if (q == null) continue; float dd = (q.X - c.World.x) * (q.X - c.World.x) + (q.Z - c.World.z) * (q.Z - c.World.z); if (dd < bd) { bd = dd; b = q; } }
            if (b == null || bd > 120f * 120f) return (false, Vector3.zero, 0, 0, 0, 0);
            float r = Mathf.Clamp(Mathf.Sqrt(Mathf.Max(b.GfaM2, 400f) / Mathf.Max(b.Floors, 1)) * 0.6f, 12f, 45f);
            var bc = new Vector3(b.X, 0f, b.Z);
            // the mast on the side of the plot with a clear view of its ground
            Vector3 best = Vector3.zero, bestDir = Vector3.forward; int bestSeen = -1;
            for (int k = 0; k < 8; k++)
            {
                float a = (c.Heading + k * 45f) * Mathf.Deg2Rad; var dir = new Vector3(Mathf.Sin(a), 0f, Mathf.Cos(a));
                var foot = bc + dir * (r + 34f); var e = new Vector3(foot.x, CityGround.HeightAt(foot.x, foot.z) + 14f, foot.z);   // a mast at the fence: the crew big enough to read
                int seen = 0; for (int i = 0; i < 5; i++) { var q = bc + dir * (r + 6f + i * 7f) + Vector3.Cross(dir, Vector3.up) * ((i - 2) * 9f); if (Visible(e, new Vector3(q.x, CityGround.HeightAt(q.x, q.z) + 1f, q.z), year)) seen++; }
                if (seen > bestSeen) { bestSeen = seen; best = e; bestDir = dir; }
            }
            eye = best; root = new GameObject("Camera feed · scene");
            var side = Vector3.Cross(bestDir, Vector3.up);
            var work = bc + bestDir * (r + 14f);                     // the working strip between the building and the camera
            bool site = c.Type == SmartCity.CamType.Construction;
            if (site)
            {
                var ex = Machine(K.Excavator, rnd); Place(ex, work - side * 9f, Quaternion.LookRotation(-bestDir)); ex.Static = true; ex.Phase = (float)rnd.NextDouble() * 6f;
                var tr = Machine(K.Truck, rnd); tr.O = work + side * 6f - bestDir * 4f; tr.D = side; tr.L = 22f; tr.S = 0f; tr.Speed = 3.2f; tr.PingPong = true;
                int nw = 6 + rnd.Next(3);
                for (int i = 0; i < nw; i++)
                {
                    var w = Person(rnd, true, TwinTour.Running && i == 1);       // in the presentation one of them works without a helmet
                    var p = work + side * ((float)rnd.NextDouble() * 30f - 15f) + bestDir * ((float)rnd.NextDouble() * 12f - 6f);
                    Place(w, p, Quaternion.Euler(0f, (float)rnd.NextDouble() * 360f, 0f)); w.Wander = p; w.Static = rnd.NextDouble() < 0.4; w.Speed = 0.9f + (float)rnd.NextDouble() * 0.5f;
                }
            }
            else
            {
                for (int i = 0; i < 2; i++) { var w = Person(rnd, true, false); var p = work + side * (i * 12f - 6f); Place(w, p, Quaternion.identity); w.Wander = p; w.Speed = 1.1f; }
                var van = Car(rnd, K.Car); Place(van, work + side * 14f, Quaternion.LookRotation(side)); van.Static = true;
            }
            var look = work - eye; float yaw = Mathf.Atan2(look.x, look.z) * Mathf.Rad2Deg, pitch = Mathf.Atan2(eye.y - CityGround.HeightAt(work.x, work.z), new Vector2(look.x, look.z).magnitude) * Mathf.Rad2Deg;
            return (true, eye, yaw, Mathf.Clamp(pitch, 8f, 34f), 10f, 42f);
        }

        // ------------------------------------------------------------------ movement
        public void Tick(float dt)
        {
            if (root == null) return; t += dt;
            foreach (var a in list)
            {
                if (a.Go == null) continue;
                if (a.Kind == K.Excavator) { if (a.Up != null) a.Up.localRotation = Quaternion.Euler(0f, Mathf.Sin(t * 0.45f + a.Phase) * 55f, 0f); continue; }
                if (a.Static && (a.Kind != K.Worker || a.Wander == Vector3.zero)) continue;
                if (a.Kind == K.Worker && a.Wander != Vector3.zero)
                {
                    if (a.Static) { a.Go.transform.rotation = Quaternion.Euler(0f, a.Phase + Mathf.Sin(t * 0.7f + a.Phase) * 40f, 0f); continue; }
                    a.WanderT -= dt;
                    var cur = a.Go.transform.position; cur.y = 0f;
                    if (a.WanderT <= 0f || (new Vector3(a.O.x, 0f, a.O.z) - cur).magnitude < 0.4f)
                    { a.WanderT = 4f + Mathf.Repeat(a.Phase * 13.7f + t, 5f); float ang = Mathf.Repeat(a.Phase * 3.1f + t * 0.9f, 6.283f); a.O = a.Wander + new Vector3(Mathf.Cos(ang), 0f, Mathf.Sin(ang)) * (4f + Mathf.Repeat(a.Phase * 7f, 6f)); }
                    var to = new Vector3(a.O.x, 0f, a.O.z) - cur; if (to.magnitude > 0.05f) { var step = to.normalized * Mathf.Min(a.Speed * dt, to.magnitude); cur += step; a.Go.transform.rotation = Quaternion.LookRotation(to.normalized); }
                    a.Go.transform.position = new Vector3(cur.x, CityGround.HeightAt(cur.x, cur.z), cur.z);
                    continue;
                }
                a.S += a.Speed * dt;
                if (a.W != null)
                {
                    float sw = Mathf.Repeat(a.S, a.W.Len); if (a.Rev) sw = a.W.Len - sw;
                    a.W.At(sw, out var p2, out var d2);
                    // a car keeps its lane on the right of the way it drives; a walker keeps to its pavement, whichever way it walks
                    var travel = a.Rev ? -d2 : d2; var off = a.Walker ? new Vector2(-d2.y, d2.x) * a.Lane : new Vector2(travel.y, -travel.x) * a.Lane;
                    var pw = p2 + off; var p3 = new Vector3(pw.x, CityGround.HeightAt(pw.x, pw.y) + (a.Walker ? Mathf.Abs(Mathf.Sin(t * 7f + a.Phase)) * 0.05f : 0f), pw.y);
                    a.Go.transform.SetPositionAndRotation(p3, Quaternion.LookRotation(new Vector3(travel.x, 0f, travel.y)));
                    continue;
                }
                float s = a.PingPong ? Mathf.PingPong(a.S, a.L) : Mathf.Repeat(a.S, a.L * 2f) - a.L;
                var p = a.O + a.D * s + Vector3.Cross(Vector3.up, a.D) * a.Lane;
                p.y = CityGround.HeightAt(p.x, p.z) + (a.Kind == K.Person ? Mathf.Abs(Mathf.Sin(t * 7f + a.Phase)) * 0.05f : 0f);
                a.Go.transform.position = p;
                a.Go.transform.rotation = Quaternion.LookRotation(a.D);           // the dump truck backs up and drives on, nose one way
            }
        }

        // ------------------------------------------------------------------ video analytics: boxes on what the camera really sees
        public void Detect(Camera c, float rtH, List<FeedRig.Det> dets)
        {
            dets.Clear(); if (root == null) return;
            var vp = c.projectionMatrix * c.worldToCameraMatrix; var e = c.transform.position; int year = TwinState.Year;
            bool crashDone = false;
            foreach (var a in list)
            {
                if (a.Go == null || a.R == null) continue;
                if (a.Flag && a.Kind == K.Car) { if (crashDone) continue; }
                var bb = a.R.bounds;
                if (a.Flag && a.Kind == K.Car) foreach (var o in list) if (o != a && o.Flag && o.Kind == K.Car && o.R != null) bb.Encapsulate(o.R.bounds);
                if (!Rect(vp, bb, out var r)) continue;
                if (r.xMax < 0.02f || r.xMin > 0.98f || r.yMax < 0.02f || r.yMin > 0.98f) continue;
                if (r.height * rtH < 5f) continue;                                   // too small in the picture to recognise
                if (!Visible(e, bb.center + Vector3.up * bb.extents.y * 0.3f, year)) continue;
                r = UnityEngine.Rect.MinMaxRect(Mathf.Max(r.xMin, 0f), Mathf.Max(r.yMin, 0f), Mathf.Min(r.xMax, 1f), Mathf.Min(r.yMax, 1f));
                float conf = 0.86f + 0.12f * Mathf.Abs(Mathf.Sin(a.Phase * 11.3f)) - Mathf.Clamp01(5f / (r.height * rtH + 1f)) * 0.08f;
                string tag; Color col = Green;
                switch (a.Kind)
                {
                    case K.Car: tag = a.Flag ? "ДТП" : "авто"; if (a.Flag) { col = Red; conf = 0.97f; crashDone = true; } break;
                    case K.Bus: tag = "автобус"; break;
                    case K.Person: tag = "человек"; break;
                    case K.Worker: tag = a.Flag ? "без каски" : "каска"; if (a.Flag) { col = Red; conf = 0.93f; } break;
                    case K.Excavator: tag = "экскаватор"; col = Amber; break;
                    default: tag = "самосвал"; col = Amber; break;
                }
                dets.Add(new FeedRig.Det { R = r, Tag = tag + " · " + Mathf.RoundToInt(Mathf.Clamp(conf, 0.5f, 0.99f) * 100f) + " %", C = col });
            }
        }
        static readonly Color Green = new Color(0.35f, 0.95f, 0.55f, 0.95f), Red = new Color(1f, 0.30f, 0.24f, 0.98f), Amber = new Color(1f, 0.76f, 0.24f, 0.95f);
        static bool Rect(Matrix4x4 vp, Bounds b, out Rect r)
        {
            float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f; r = default;
            for (int c = 0; c < 8; c++)
            {
                var p = b.center + Vector3.Scale(b.extents, new Vector3((c & 1) == 0 ? -1 : 1, (c & 2) == 0 ? -1 : 1, (c & 4) == 0 ? -1 : 1));
                var cp = vp * new Vector4(p.x, p.y, p.z, 1f); if (cp.w < 0.3f) return false;
                float nx = cp.x / cp.w * 0.5f + 0.5f, ny = cp.y / cp.w * 0.5f + 0.5f;
                x0 = Mathf.Min(x0, nx); x1 = Mathf.Max(x1, nx); y0 = Mathf.Min(y0, ny); y1 = Mathf.Max(y1, ny);
            }
            r = UnityEngine.Rect.MinMaxRect(x0, y0, x1, y1); return true;
        }
        /// <summary>The sight line from the camera to p is not cut by a building that stands in this year (or a hill of the ground).</summary>
        static readonly RaycastHit[] hits = new RaycastHit[32];
        static bool Visible(Vector3 e, Vector3 p, int year)
        {
            var d = p - e; float L = d.magnitude; if (L < 1f) return true;
            int n = Physics.RaycastNonAlloc(new Ray(e, d / L), hits, L - 1.2f, ~(1 << FeedRig.Layer), QueryTriggerInteraction.Ignore);
            for (int i = 0; i < n; i++)
            {
                var h = hits[i]; var ch = h.collider.GetComponent<BuildingChunk>();
                if (ch != null)
                {
                    int bid = ch.BuildingAt(h.triangleIndex);
                    if (Landmarks.LandmarkSystem.IsHiddenBid(bid)) continue;
                    int eff = ConstructionLayer.Active ? ConstructionLayer.VisibleFrom(bid) : CityStats.Ready ? CityStats.EffectiveYearOf(bid) : 0;
                    if (eff > year) continue;
                    return false;
                }
                if (h.collider.GetComponent<Landmarks.LandmarkObject>() != null) return false;
                if (h.distance < L - 6f) return false;                               // the ground rises between
            }
            return true;
        }

        /// <summary>The road nearest to p (built by this year): the nearest point on it, its direction and the edge.</summary>
        static bool NearestRoad(Vector2 p, int year, float maxD, out Vector2 at, out Vector2 dir, out int edge)
        {
            at = p; dir = Vector2.up; edge = -1; float best = maxD * maxD; bool found = false; int s = (int)TwinState.Scenario;
            var roads = Data.TwinData.Roads;
            for (int ei = 0; ei < roads.Length; ei++)
            {
                var e = roads[ei];
                var g = e.Geom; if (g == null || g.Length < 2) continue;
                if (e.Year != null && e.Year.Length > 0 && e.Year[Mathf.Min(s, e.Year.Length - 1)] > year) continue;
                for (int i = 0; i + 1 < g.Length; i++)
                {
                    var a = g[i]; var b = g[i + 1]; var ab = b - a; float L2 = ab.sqrMagnitude; if (L2 < 100f) continue;   // pieces shorter than 10 m: a junction
                    float u = Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2); var q = a + ab * u; float dd = (q - p).sqrMagnitude;
                    if (dd < best) { best = dd; at = q; dir = ab.normalized; edge = ei; found = true; }
                }
            }
            return found;
        }

        // ------------------------------------------------------------------ actors
        A Car(System.Random rnd, K kind)
        {
            string[] cols = { "#e9e9e7", "#2a2c30", "#8a9097", "#9b2a24", "#2f4f7a", "#c9c6bd", "#1d3b2e", "#d8d2c2" };
            string col = kind == K.Bus ? "#e3e1da" : cols[rnd.Next(cols.Length)];
            return New(kind, (kind == K.Bus ? "bus" : "car") + col, k => { if (kind == K.Bus) Bus(k); else CarMesh(k, LM.C(col)); }, rnd);
        }
        A Person(System.Random rnd, bool worker, bool noHelmet)
        {
            string[] tops = { "#2f4f7a", "#9b2a24", "#e9e9e7", "#3a3a3a", "#6b8e3d", "#c48a2c", "#7a4b8c" };
            string top = worker ? "#f07a1a" : tops[rnd.Next(tops.Length)], hat = worker ? (noHelmet ? "" : rnd.NextDouble() < 0.7 ? "#f2c40c" : "#f2f2ee") : "";
            var a = New(worker ? K.Worker : K.Person, "p" + top + hat, k => PersonMesh(k, LM.C(top), hat.Length > 0 ? LM.C(hat) : (Color32?)null), rnd);
            a.Flag = noHelmet; return a;
        }
        A Machine(K kind, System.Random rnd)
        {
            var a = New(kind, kind == K.Excavator ? "exc_base" : "truck", k => { if (kind == K.Excavator) ExcavatorBase(k); else TruckMesh(k); }, rnd);
            if (kind == K.Excavator)
            {
                var up = new GameObject("upper"); up.layer = FeedRig.Layer; up.transform.SetParent(a.Go.transform, false); up.transform.localPosition = new Vector3(0f, 1.1f, 0f);
                up.AddComponent<MeshFilter>().sharedMesh = MeshOf("exc_upper", ExcavatorUpper); up.AddComponent<MeshRenderer>().sharedMaterial = Mat; a.Up = up.transform;
            }
            return a;
        }
        A New(K kind, string key, Action<LandmarkKit> build, System.Random rnd)
        {
            var go = new GameObject(kind.ToString()); go.layer = FeedRig.Layer; go.transform.SetParent(root.transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = MeshOf(key, build); var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = Mat;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            var a = new A { Kind = kind, Go = go, R = r, Phase = (float)rnd.NextDouble() * 6.28f }; list.Add(a); return a;
        }
        static void Place(A a, Vector3 p, Quaternion q) { a.Go.transform.SetPositionAndRotation(new Vector3(p.x, CityGround.HeightAt(p.x, p.z), p.z), q); a.Phase = q.eulerAngles.y; }
        static Material Mat { get { if (mat == null) { var sh = Shader.Find("AlatauCity/Landmark"); if (sh != null) mat = new Material(sh) { name = "Camera feed actors" }; } return mat; } }
        static Mesh MeshOf(string key, Action<LandmarkKit> build)
        {
            if (meshes.TryGetValue(key, out var m) && m != null) return m;
            var k = new LandmarkKit(); build(k); m = k.ToMesh("Feed " + key); meshes[key] = m; return m;
        }

        // meshes: local origin on the ground, +z forward
        static readonly Color32 Tyre = LM.C("#1b1c1e"), GlassC = LM.C("#22303b"), Head = LM.C("#fff4d6"), Tail = LM.C("#ff3b2e"), Skin = LM.C("#c99a7a"), Jeans = LM.C("#2c3a52"),
            Yellow = LM.C("#f2b705"), Dark = LM.C("#2b2d30"), Steel = LM.C("#8c8c88");
        static void CarMesh(LandmarkKit k, Color32 body)
        {
            k.Box(new Vector3(0f, 0.72f, 0f), new Vector3(1.8f, 0.72f, 4.4f), 0f, body, LM.Metal, 3f, body, LM.Metal);
            k.Box(new Vector3(0f, 1.36f, -0.25f), new Vector3(1.6f, 0.56f, 2.3f), 0f, GlassC, LM.Glass, 3f, body, LM.Metal);
            for (int i = 0; i < 4; i++) k.Box(new Vector3(i % 2 == 0 ? -0.82f : 0.82f, 0.34f, i < 2 ? 1.35f : -1.35f), new Vector3(0.26f, 0.66f, 0.66f), 0f, Tyre, LM.Solid, 1f, Tyre, LM.Solid);
            k.Box(new Vector3(0f, 0.86f, 2.21f), new Vector3(1.5f, 0.16f, 0.04f), 0f, Head, LM.Light, 1f, Head, LM.Light);
            k.Box(new Vector3(0f, 0.9f, -2.21f), new Vector3(1.5f, 0.14f, 0.04f), 0f, Tail, LM.Light, 1f, Tail, LM.Light);
        }
        static void Bus(LandmarkKit k)
        {
            var c = LM.C("#e3e1da"); var stripe = LM.C("#2f6db0");
            k.Box(new Vector3(0f, 1.75f, 0f), new Vector3(2.5f, 2.9f, 12f), 0f, c, LM.Metal, 3f, c, LM.Roof);
            k.Box(new Vector3(0f, 2.1f, 0f), new Vector3(2.52f, 1.1f, 11.2f), 0f, GlassC, LM.Glass, 3f, GlassC, LM.Glass);
            k.Box(new Vector3(0f, 0.95f, 0f), new Vector3(2.53f, 0.3f, 11.8f), 0f, stripe, LM.Solid, 3f, stripe, LM.Solid);
            for (int i = 0; i < 4; i++) k.Box(new Vector3(i % 2 == 0 ? -1.1f : 1.1f, 0.5f, i < 2 ? 4.2f : -3.6f), new Vector3(0.3f, 1.0f, 1.0f), 0f, Tyre, LM.Solid, 1f, Tyre, LM.Solid);
            k.Box(new Vector3(0f, 1.0f, 6.01f), new Vector3(2.0f, 0.2f, 0.04f), 0f, Head, LM.Light, 1f, Head, LM.Light);
        }
        static void PersonMesh(LandmarkKit k, Color32 top, Color32? hat)
        {
            k.Box(new Vector3(-0.1f, 0.43f, 0f), new Vector3(0.16f, 0.86f, 0.2f), 0f, Jeans, LM.Solid, 1f, Jeans, LM.Solid);
            k.Box(new Vector3(0.1f, 0.43f, 0f), new Vector3(0.16f, 0.86f, 0.2f), 0f, Jeans, LM.Solid, 1f, Jeans, LM.Solid);
            k.Box(new Vector3(0f, 1.16f, 0f), new Vector3(0.46f, 0.62f, 0.26f), 0f, top, LM.Solid, 1f, top, LM.Solid);
            k.Box(new Vector3(-0.29f, 1.12f, 0f), new Vector3(0.11f, 0.56f, 0.13f), 0f, top, LM.Solid, 1f, top, LM.Solid);
            k.Box(new Vector3(0.29f, 1.12f, 0f), new Vector3(0.11f, 0.56f, 0.13f), 0f, top, LM.Solid, 1f, top, LM.Solid);
            k.Box(new Vector3(0f, 1.6f, 0f), new Vector3(0.22f, 0.25f, 0.24f), 0f, Skin, LM.Solid, 1f, Skin, LM.Solid);
            if (hat.HasValue) k.Box(new Vector3(0f, 1.77f, 0.01f), new Vector3(0.29f, 0.12f, 0.31f), 0f, hat.Value, LM.Solid, 1f, hat.Value, LM.Solid);
        }
        static void ExcavatorBase(LandmarkKit k)
        {
            k.Box(new Vector3(-1.25f, 0.5f, 0f), new Vector3(0.7f, 1.0f, 4.6f), 0f, Dark, LM.Metal, 1f, Dark, LM.Metal);
            k.Box(new Vector3(1.25f, 0.5f, 0f), new Vector3(0.7f, 1.0f, 4.6f), 0f, Dark, LM.Metal, 1f, Dark, LM.Metal);
            k.Box(new Vector3(0f, 0.85f, 0f), new Vector3(1.9f, 0.5f, 2.2f), 0f, Dark, LM.Metal, 1f, Dark, LM.Metal);
        }
        static void ExcavatorUpper(LandmarkKit k)
        {
            k.Box(new Vector3(0f, 0.75f, -0.6f), new Vector3(2.8f, 1.3f, 3.2f), 0f, Yellow, LM.Metal, 1f, Yellow, LM.Metal);
            k.Box(new Vector3(-0.75f, 2.0f, 0.4f), new Vector3(1.0f, 1.3f, 1.3f), 0f, GlassC, LM.Glass, 1f, Yellow, LM.Metal);
            k.Box(new Vector3(0f, 0.9f, -2.4f), new Vector3(2.7f, 1.1f, 0.6f), 0f, Dark, LM.Metal, 1f, Dark, LM.Metal);           // counterweight
            var b0 = new Vector3(0.45f, 1.2f, 0.9f); var b1 = new Vector3(0.45f, 4.6f, 4.0f); var b2 = new Vector3(0.45f, 1.4f, 6.1f);
            k.Beam(b0, b1, 0.45f, 0.6f, Yellow, LM.Metal); k.Beam(b1, b2, 0.35f, 0.45f, Yellow, LM.Metal);
            k.Box(b2 + new Vector3(0f, -0.35f, 0.2f), new Vector3(1.0f, 0.8f, 0.9f), 0f, Dark, LM.Metal, 1f, Dark, LM.Metal);   // bucket
        }
        static void TruckMesh(LandmarkKit k)
        {
            var bed = LM.C("#d9621c"); var cab = LM.C("#e8e6e0");
            k.Box(new Vector3(0f, 1.0f, 0f), new Vector3(2.4f, 0.4f, 7.6f), 0f, Dark, LM.Metal, 1f, Dark, LM.Metal);
            k.Box(new Vector3(0f, 2.2f, 2.9f), new Vector3(2.4f, 2.0f, 1.8f), 0f, cab, LM.Metal, 1f, cab, LM.Metal);
            k.Box(new Vector3(0f, 2.55f, 3.81f), new Vector3(2.0f, 0.8f, 0.04f), 0f, GlassC, LM.Glass, 1f, GlassC, LM.Glass);
            k.Box(new Vector3(0f, 2.1f, -1.0f), new Vector3(2.5f, 1.6f, 5.2f), 0f, bed, LM.Metal, 1f, LM.C("#6b5a44"), LM.Roof);
            for (int i = 0; i < 6; i++) k.Box(new Vector3(i % 2 == 0 ? -1.1f : 1.1f, 0.55f, i < 2 ? 2.8f : i < 4 ? -1.2f : -2.6f), new Vector3(0.4f, 1.1f, 1.1f), 0f, Tyre, LM.Solid, 1f, Tyre, LM.Solid);
        }
    }

    /// <summary>A camera window: the rendered view + the overlay of a CCTV stream.</summary>
    public class CameraFeed : VisualElement
    {
        readonly Image img; readonly Label lId, lClock, lPlace, lStub; readonly VisualElement overlay;
        SmartCity.Cctv cam; bool attached; float phase;
        static readonly Color Rec = new Color(1f, 0.23f, 0.18f);

        public CameraFeed(bool big = false)
        {
            AddToClassList("feed"); if (big) AddToClassList("feed-big");
            img = new Image { scaleMode = ScaleMode.ScaleAndCrop, pickingMode = PickingMode.Ignore }; img.AddToClassList("feed-img"); Add(img);
            overlay = new VisualElement { pickingMode = PickingMode.Ignore }; overlay.AddToClassList("feed-over"); overlay.generateVisualContent += Draw; Add(overlay);
            var top = new VisualElement { pickingMode = PickingMode.Ignore }; top.AddToClassList("feed-top"); overlay.Add(top);
            var rec = new VisualElement { pickingMode = PickingMode.Ignore }; rec.AddToClassList("feed-rec"); top.Add(rec);
            lId = new Label { pickingMode = PickingMode.Ignore }; lId.AddToClassList("feed-id"); top.Add(lId);
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; top.Add(sp);
            lClock = new Label { pickingMode = PickingMode.Ignore }; lClock.AddToClassList("feed-clock"); top.Add(lClock);
            lPlace = new Label { pickingMode = PickingMode.Ignore }; lPlace.AddToClassList("feed-place"); overlay.Add(lPlace);
            lStub = new Label("ДЕМО-ПОТОК · МОДЕЛЬ QTWIN") { pickingMode = PickingMode.Ignore }; lStub.AddToClassList("feed-stub"); overlay.Add(lStub);
            RegisterCallback<AttachToPanelEvent>(_ => { if (!attached) { attached = true; FeedRig.Ensure().Use(true); if (cam != null) FeedRig.Instance.Look(cam); } });
            RegisterCallback<DetachFromPanelEvent>(_ => { if (attached) { attached = false; FeedRig.Instance?.Use(false); } });
            schedule.Execute(Tick).Every(100);
        }

        public SmartCity.Cctv Cam => cam;
        public void Show(SmartCity.Cctv c)
        {
            cam = c; if (c == null) return;
            lId.text = c.Id + " · " + SmartCity.CamTypeShort[(int)c.Type].ToUpperInvariant();
            lPlace.text = c.Place + (c.Online ? "" : " · нет сигнала");
            EnableInClassList("offline", !c.Online);
            FeedRig.Ensure().Look(c);
        }

        void Tick()
        {
            if (panel == null) return;
            var tex = FeedRig.Texture; if (tex != null && img.image != tex) img.image = tex;
            img.style.opacity = cam != null && cam.Online ? 1f : 0.12f;
            lClock.text = new DateTime(TwinState.Year, 11, 18).ToString("dd.MM.yyyy", Loc.Ru) + "  " + DateTime.Now.ToString("HH:mm:ss");
            phase += 0.1f; Boxes(); overlay.MarkDirtyRepaint();
        }

        /// <summary>Scan lines, the blinking REC dot, a few video-analytics boxes drifting over the frame.</summary>
        void Draw(MeshGenerationContext ctx)
        {
            var r = contentRect; if (r.width < 20f) return;
            var p = ctx.painter2D;
            // scan lines
            p.lineWidth = 1f; p.strokeColor = new Color(1f, 1f, 1f, 0.035f);
            for (float y = 0; y < r.height; y += 3f) { p.BeginPath(); p.MoveTo(new Vector2(0, y)); p.LineTo(new Vector2(r.width, y)); p.Stroke(); }
            if (cam == null || !cam.Online) return;
            // REC dot
            if (Mathf.Repeat(phase, 1.2f) < 0.7f) { p.fillColor = Rec; p.BeginPath(); p.Arc(new Vector2(14f, 15f), 4.5f, 0f, 360f); p.Fill(); }
            // the video analytics: a box on every person, car and machine the camera really sees (Boxes, from the last picture)
            foreach (var (q, d) in shown)
            {
                p.strokeColor = d.C; p.lineWidth = 1.5f;
                p.BeginPath(); p.MoveTo(q.min); p.LineTo(new Vector2(q.xMax, q.yMin)); p.LineTo(q.max); p.LineTo(new Vector2(q.xMin, q.yMax)); p.ClosePath(); p.Stroke();
            }
        }
        // the boxes in the window's coordinates (the image is scaled to cover the window and cropped) and their labels: what it is and
        // how sure the analytics is
        readonly System.Collections.Generic.List<(Rect, FeedRig.Det)> shown = new System.Collections.Generic.List<(Rect, FeedRig.Det)>();
        readonly System.Collections.Generic.List<Label> tags = new System.Collections.Generic.List<Label>();
        void Boxes()
        {
            shown.Clear(); var r = contentRect;
            if (r.width >= 20f && cam != null && cam.Online && FeedRig.Instance != null)
            {
                var tex = FeedRig.Texture; float tw = tex != null ? tex.width : 512f, th = tex != null ? tex.height : 288f;
                float k = Mathf.Max(r.width / tw, r.height / th), dw = tw * k, dh = th * k, ox = (r.width - dw) * 0.5f, oy = (r.height - dh) * 0.5f;
                foreach (var d in FeedRig.Dets)
                {
                    var q = Rect.MinMaxRect(ox + d.R.xMin * dw - 1.5f, oy + (1f - d.R.yMax) * dh - 1.5f, ox + d.R.xMax * dw + 1.5f, oy + (1f - d.R.yMin) * dh + 1.5f);
                    if (q.xMax < 2f || q.xMin > r.width - 2f || q.yMax < 2f || q.yMin > r.height - 2f) continue;
                    shown.Add((q, d));
                }
            }
            // labels without overlaps: alarms first, then the larger boxes; a label goes above its box, else below, else inside;
            // one that fits nowhere is left out (its box stays), as a real analytics overlay thins its captions in a crowd
            order.Clear(); for (int i = 0; i < shown.Count; i++) order.Add(i);
            order.Sort((x, y) => { int px = Pri(shown[x].Item2), py = Pri(shown[y].Item2); if (px != py) return px.CompareTo(py); float ax = shown[x].Item1.width * shown[x].Item1.height, ay = shown[y].Item1.width * shown[y].Item1.height; return ay.CompareTo(ax); });
            placed.Clear(); int used = 0;
            foreach (int i in order)
            {
                var (q, d) = shown[i]; float w = d.Tag.Length * 5.1f + 8f, h = 13f; Rect at = default; bool ok = false;
                for (int c = 0; c < 3 && !ok; c++)
                {
                    float y = c == 0 ? q.yMin - h : c == 1 ? q.yMax + 1f : q.yMin + 1f;
                    if (y < 0f || y > r.height - h) continue;
                    at = new Rect(Mathf.Clamp(q.xMin, 0f, Mathf.Max(0f, r.width - w)), y, w, h); ok = true;
                    foreach (var o in placed) if (o.Overlaps(new Rect(at.x - 1f, at.y - 1f, at.width + 2f, at.height + 2f))) { ok = false; break; }
                }
                if (!ok) { if (Pri(d) > 0) continue; at = new Rect(Mathf.Clamp(q.xMin, 0f, Mathf.Max(0f, r.width - w)), Mathf.Max(0f, q.yMin - h), w, h); }
                placed.Add(at);
                if (tags.Count <= used) { var l = new Label { pickingMode = PickingMode.Ignore }; l.AddToClassList("feed-tag"); overlay.Add(l); tags.Add(l); }
                var lb = tags[used++];
                if (lb.userData as string != d.Tag) { lb.userData = d.Tag; lb.text = d.Tag; }
                lb.style.display = DisplayStyle.Flex; lb.style.backgroundColor = d.C; lb.style.left = at.x; lb.style.top = at.y;
            }
            for (int i = used; i < tags.Count; i++) tags[i].style.display = DisplayStyle.None;
        }
        readonly System.Collections.Generic.List<int> order = new System.Collections.Generic.List<int>();
        readonly System.Collections.Generic.List<Rect> placed = new System.Collections.Generic.List<Rect>();
        /// <summary>Label priority: 0 an alarm (red), 1 machines (amber), 2 the rest.</summary>
        static int Pri(FeedRig.Det d) => d.C.g < 0.5f ? 0 : d.C.b < 0.4f ? 1 : 2;
    }
}
