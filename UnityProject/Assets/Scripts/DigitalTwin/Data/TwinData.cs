using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;
using static AlatauCity.DigitalTwin.Data.TwinJson;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>Synthetic, deterministic twin data (Tools/twin_gen, seed 2050) loaded from StreamingAssets/twin/*.json.
    /// Scenario index = (int)Scenario: 0 base, 1 fast, 2 slow, 3 infra. Year index = year − Y0 (0..25): the tables start one year before the timeline (2026), with the existing city.
    /// Loading runs on a worker thread at start-up; Ready / OnReady tell modules when they can read it.</summary>
    public static class TwinData
    {
        public const int NY = 26, NS = 4;
        /// <summary>First year of the data tables (the existing city before the project). The timeline itself starts at TwinState.MinYear.</summary>
        public const int Y0 = 2025;
        public static bool Ready { get; private set; }
        public static string Error { get; private set; }
        public static string Version = "";
        public static event Action OnReady;

        // ---------------- roads
        public enum RoadClass : byte { Highway, Ring, Main, Street }
        public struct RoadEdge { public int A, B; public RoadClass Cls; public float Len; public Vector2[] Geom; public int[] Year; }
        public static Vector2[] RoadNodes = new Vector2[0];
        public static RoadEdge[] Roads = new RoadEdge[0];

        // ---------------- facilities and networks
        public class Facility
        {
            public string Id, Name, Kind, Res, Note; public float X, Z, Unit, Head; public int District; public bool Synthetic;
            public int[][] Stages; public float[][] Cap, Demand; public int[] DelayedStages;
            public float CapAt(int s, int year) => Cap == null ? 0 : Cap[s][Mathf.Clamp(year - Y0, 0, NY - 1)];
            public float DemandAt(int s, int year) => Demand == null ? 0 : Demand[s][Mathf.Clamp(year - Y0, 0, NY - 1)];
        }
        public struct NetSeg { public int Edge, Size, Fac; public int[] Year; public float Load; }
        public static Facility[] Facilities = new Facility[0];
        public static readonly Dictionary<string, NetSeg[]> Networks = new Dictionary<string, NetSeg[]>();
        public static readonly Dictionary<string, string> Units = new Dictionary<string, string>();

        // ---------------- loads, balance, social
        public class Balance { public float[] Demand, Cap, Deficit; }
        public class ResBalance { public Balance City; public Balance[] Districts = new Balance[4]; }
        public static readonly Dictionary<string, float[][]>[] Loads = new Dictionary<string, float[][]>[NS];      // [s][key][district][year]
        public static readonly Dictionary<string, ResBalance>[] Balances = new Dictionary<string, ResBalance>[NS];  // [s][res]
        public static float[][][][] SocialNeed = new float[NS][][][], SocialCap = new float[NS][][][];             // [s][d][k][year]
        public static string[] SocialKeys = new string[0];

        // ---------------- construction
        public static int[] BuildYears = new int[0], Contractor = new int[0], DelayMonths = new int[0];
        public static string[] ContractorNames = new string[0];
        public static float[][][] PlanGfa = new float[NS][][], FactGfa = new float[NS][][], WipGfa = new float[NS][][];   // [s][d][year], mln m²
        public static Vector3[] LrtStations = new Vector3[0];   // x, z, phase
        public static float[] LrtPhaseKm = new float[0]; public static int[][] LrtPhaseYear = new int[NS][]; public static string[] LrtPhaseNames = new string[0];

        // ---------------- finance (bln ₸)
        public static float[][][][] CapexBuildings = new float[NS][][][];   // [s][d][cat][year]
        public static float[][][][] CapexSources = new float[NS][][][];     // [s][d][budget, private, ppp, quasi][year]
        public static float[][][] CapexFact = new float[NS][][];            // [s][d][year]
        public static readonly Dictionary<string, float[]>[] CapexInfra = new Dictionary<string, float[]>[NS];

        // ---------------- traffic
        public static int[] TrafficYears = new int[0];
        public static byte[][][] TrafficVc = new byte[NS][][];              // [s][yearIdx][edge] = v/c × 100
        public static readonly Dictionary<string, float>[][] TrafficKpi = new Dictionary<string, float>[NS][];

        // ---------------- scenarios
        public static string[] ScenarioNames = new string[0], ScenarioDesc = new string[0];

        static readonly string[] SKeys = { "base", "fast", "slow", "infra" };

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Boot()
        {
            Ready = false; Error = null;
            string dir = Path.Combine(Application.streamingAssetsPath, "twin");
            if (TwinFiles.NeedsDownload)
            {
                // WebGL: no threads and no file system — download the files, then parse on the main thread
                var host = new GameObject("Twin data (download)"); UnityEngine.Object.DontDestroyOnLoad(host);
                host.AddComponent<Loader>().StartCoroutine(TwinFiles.Download(err =>
                {
                    try { LoadAll(dir); Ready = true; } catch (Exception e) { Error = (err != null ? err + "; " : "") + e.Message; }
                    Finish();
                }));
                return;
            }
            var ctx = System.Threading.SynchronizationContext.Current;
            Task.Run(() =>
            {
                try { LoadAll(dir); Ready = true; }
                catch (Exception e) { Error = e.Message; }
                ctx?.Post(_ => Finish(), null);
            });
        }
        class Loader : MonoBehaviour { }
        static void Finish()
        {
            if (Error != null) Debug.LogError("[Alatau] twin data: " + Error);
            else { Debug.Log($"[Alatau] twin data {Version}: {Roads.Length} road edges, {Facilities.Length} facilities, {Networks.Count} networks"); OnReady?.Invoke(); }
        }

        static object Read(string dir, string name) => Parse(TwinFiles.Text(name + ".json"));

        static void LoadAll(string dir)
        {
            // roads
            var r = Read(dir, "roads"); Version = S(G(r, "version"));
            var nodes = A(G(r, "nodes")); RoadNodes = new Vector2[nodes.Count];
            for (int i = 0; i < nodes.Count; i++) { var p = A(nodes[i]); RoadNodes[i] = new Vector2(F(p[0]), F(p[1])); }
            var edges = A(G(r, "edges")); Roads = new RoadEdge[edges.Count];
            for (int i = 0; i < edges.Count; i++)
            {
                var e = edges[i]; var g = Floats(G(e, "g")); var geom = new Vector2[g.Length / 2];
                for (int k = 0; k < geom.Length; k++) geom[k] = new Vector2(g[2 * k], g[2 * k + 1]);
                var c = S(G(e, "c"));
                Roads[i] = new RoadEdge { A = I(G(e, "a")), B = I(G(e, "b")), Len = F(G(e, "len")), Geom = geom, Year = Ints(G(e, "y")),
                    Cls = c == "highway" ? RoadClass.Highway : c == "ring" ? RoadClass.Ring : c == "main" ? RoadClass.Main : RoadClass.Street };
            }
            // facilities + networks
            var n = Read(dir, "networks");
            var fl = A(G(n, "facilities")); Facilities = new Facility[fl.Count];
            for (int i = 0; i < fl.Count; i++)
            {
                var f = fl[i];
                var fa = new Facility { Id = S(G(f, "id")), Name = S(G(f, "name")), Kind = S(G(f, "kind")), Res = S(G(f, "res")), Note = S(G(f, "note")),
                    X = F(G(f, "x")), Z = F(G(f, "z")), Unit = F(G(f, "unit")), Head = F(G(f, "head")), District = I(G(f, "district")),
                    Synthetic = G(f, "synthetic") is bool b && b, DelayedStages = Ints(G(f, "delayed_stages")) };
                var st = A(G(f, "stages")); fa.Stages = new int[NS][]; for (int s = 0; s < NS; s++) fa.Stages[s] = Ints(st[s]);
                fa.Cap = PerScenario(G(f, "cap")); fa.Demand = PerScenario(G(f, "demand"));
                Facilities[i] = fa;
            }
            Networks.Clear();
            foreach (var kv in O(G(n, "networks")))
            {
                var segs = A(kv.Value); var arr = new NetSeg[segs.Count];
                for (int i = 0; i < arr.Length; i++)
                {
                    var q = A(segs[i]);
                    arr[i] = new NetSeg { Edge = I(q[0]), Size = I(q[1]), Year = new[] { I(q[2]), I(q[3]), I(q[4]), I(q[5]) }, Fac = I(q[6]), Load = F(q[7]) };
                }
                Networks[kv.Key] = arr;
            }
            Units.Clear(); foreach (var kv in O(G(n, "units"))) Units[kv.Key] = S(kv.Value);
            // loads + balance + social
            var l = Read(dir, "loads");
            SocialKeys = Array.ConvertAll(A(G(l, "social_keys")).ToArray(), o => S(o));
            for (int s = 0; s < NS; s++)
            {
                var ls = O(G(G(l, "loads"), SKeys[s])); Loads[s] = new Dictionary<string, float[][]>();
                foreach (var kv in ls) if (kv.Key != "gfa") Loads[s][kv.Key] = Matrix(kv.Value);
                Balances[s] = new Dictionary<string, ResBalance>();
                foreach (var kv in O(G(G(l, "balance"), SKeys[s])))
                {
                    var rb = new ResBalance { City = Bal(G(kv.Value, "city")) };
                    var ds = A(G(kv.Value, "districts")); for (int d = 0; d < 4; d++) rb.Districts[d] = Bal(ds[d]);
                    Balances[s][kv.Key] = rb;
                }
                var so = G(G(l, "social"), SKeys[s]); SocialNeed[s] = Cube(G(so, "need")); SocialCap[s] = Cube(G(so, "cap"));
            }
            // construction
            var c2 = Read(dir, "construction"); var pb = G(c2, "per_building");
            BuildYears = Ints(G(pb, "duration_years")); Contractor = Ints(G(pb, "contractor")); DelayMonths = Ints(G(pb, "delay_months"));
            ContractorNames = Array.ConvertAll(A(G(c2, "contractors")).ToArray(), o => S(G(o, "name")));
            for (int s = 0; s < NS; s++)
            {
                var sc = G(G(c2, "s_curves"), SKeys[s]);
                PlanGfa[s] = Matrix(G(sc, "plan")); FactGfa[s] = Matrix(G(sc, "fact")); WipGfa[s] = Matrix(G(sc, "wip"));
            }
            var lrt = G(c2, "lrt"); var sts = A(G(lrt, "stations")); LrtStations = new Vector3[sts.Count];
            for (int i = 0; i < sts.Count; i++) { var p = A(sts[i]); LrtStations[i] = new Vector3(F(p[0]), F(p[1]), F(p[2])); }
            LrtPhaseKm = Floats(G(lrt, "phase_km")); LrtPhaseNames = Array.ConvertAll(A(G(lrt, "phase_names")).ToArray(), o => S(o));
            for (int s = 0; s < NS; s++) LrtPhaseYear[s] = Ints(G(G(lrt, "phase_year"), SKeys[s]));
            // finance
            var fi = Read(dir, "finance");
            for (int s = 0; s < NS; s++)
            {
                var fs = G(G(fi, "by_scenario"), SKeys[s]);
                CapexBuildings[s] = Cube(G(fs, "buildings")); CapexSources[s] = Cube(G(fs, "sources")); CapexFact[s] = Matrix(G(fs, "fact"));
                CapexInfra[s] = new Dictionary<string, float[]>(); foreach (var kv in O(G(fs, "infra"))) CapexInfra[s][kv.Key] = Floats(kv.Value);
            }
            // traffic
            var t = Read(dir, "traffic"); TrafficYears = Ints(G(t, "years"));
            for (int s = 0; s < NS; s++)
            {
                var ts = G(G(t, "by_scenario"), SKeys[s]); TrafficVc[s] = new byte[TrafficYears.Length][]; TrafficKpi[s] = new Dictionary<string, float>[TrafficYears.Length];
                for (int y = 0; y < TrafficYears.Length; y++)
                {
                    var ty = G(ts, TrafficYears[y].ToString()); var vc = A(G(ty, "vc")); var bytes = new byte[vc.Count];
                    for (int i = 0; i < bytes.Length; i++) bytes[i] = (byte)Mathf.Clamp(I(vc[i]), 0, 255);
                    TrafficVc[s][y] = bytes; TrafficKpi[s][y] = new Dictionary<string, float>();
                    foreach (var kv in O(G(ty, "kpi"))) TrafficKpi[s][y][kv.Key] = F(kv.Value);
                }
            }
            // scenarios
            var sl = A(G(Read(dir, "scenarios"), "scenarios"));
            ScenarioNames = Array.ConvertAll(sl.ToArray(), o => S(G(o, "name"))); ScenarioDesc = Array.ConvertAll(sl.ToArray(), o => S(G(o, "desc")));
        }

        static float[][] PerScenario(object o) { var a = A(o); if (a == null) return null; var r = new float[a.Count][]; for (int i = 0; i < r.Length; i++) r[i] = Floats(a[i]); return r; }
        static float[][] Matrix(object o) => PerScenario(o);
        static float[][][] Cube(object o) { var a = A(o); var r = new float[a.Count][][]; for (int i = 0; i < r.Length; i++) r[i] = Matrix(a[i]); return r; }
        static Balance Bal(object o) => o == null ? null : new Balance { Demand = Floats(G(o, "demand")), Cap = Floats(G(o, "cap")), Deficit = Floats(G(o, "deficit")) };

        // ---------------- convenience
        public static int YI(int year) => Mathf.Clamp(year - Y0, 0, NY - 1);
        public static float Load(int s, string key, int district, int year)
        {
            if (!Ready || !Loads[s].TryGetValue(key, out var m)) return 0;
            int y = YI(year); if (district >= 0) return m[district][y];
            float v = 0; for (int d = 0; d < 4; d++) v += m[d][y]; return v;
        }
        public static Balance BalanceOf(int s, string res, int district)
        {
            if (!Ready || !Balances[s].TryGetValue(res, out var b)) return null;
            return district < 0 ? b.City : b.Districts[district];
        }
    }
}
