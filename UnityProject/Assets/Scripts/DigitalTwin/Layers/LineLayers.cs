using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Line layers over the city built at run time from TwinData (no assets): utility networks along the streets,
    /// road works, traffic. One mesh per layer, screen-space width (AlatauCity/Line shader), status by year and scenario in the shader.</summary>
    public class LineLayers : MonoBehaviour
    {
        public static LineLayers Instance;
        public static readonly string[] NetKeys = { "water", "sewer", "power", "heat", "gas", "telecom" };
        public static readonly Color[] NetColors =
        {
            new Color(0.30f, 0.64f, 1.00f), new Color(0.66f, 0.50f, 0.33f), new Color(1.00f, 0.84f, 0.04f),
            new Color(1.00f, 0.48f, 0.27f), new Color(0.75f, 0.52f, 0.99f), new Color(0.18f, 0.83f, 0.75f),
        };
        static readonly float[] NetLane = { -2f, -1f, 1f, 2f, 3f, -3f };
        public static readonly Color RoadWorkColor = new Color(0.96f, 0.65f, 0.14f);

        readonly Dictionary<string, MeshRenderer> layers = new Dictionary<string, MeshRenderer>();
        Texture2D trafficTex; byte[] traffic = new byte[256 * 128];
        int trafficYear = -1, trafficScen = -1;
        static readonly int PxId = Shader.PropertyToID("_AlatauPx"), ScenIdx = Shader.PropertyToID("_AlatauScenIdx"), TrafficId = Shader.PropertyToID("_AlatauTrafficTex");

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Twin line layers").AddComponent<LineLayers>(); }

        void Awake() { Instance = this; }
        void OnEnable() { TwinData.OnReady += BuildAll; if (TwinData.Ready) BuildAll(); }
        void OnDisable() { TwinData.OnReady -= BuildAll; }

        void Update()
        {
            var cam = Camera.main;
            if (cam != null) Shader.SetGlobalFloat(PxId, 2f * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad) / Mathf.Max(1, Screen.height));
            Shader.SetGlobalFloat(ScenIdx, (int)TwinState.Scenario);
            if (layers.TryGetValue("traffic", out var t) && t.enabled) UpdateTraffic();
            // a local jam over the traffic layer (situational centre): red builds up around the incident, turns green after the decision
            float dt = Mathf.Min(TwinState.RealDelta, 0.1f);
            jamNow = Mathf.MoveTowards(jamNow, jamTarget, dt * 0.7f); clearNow = Mathf.MoveTowards(clearNow, clearTarget, dt * 0.22f);
            Shader.SetGlobalVector(JamId, new Vector4(jamC.x, jamC.y, jamR, jamNow * (1f - clearNow)));
            Shader.SetGlobalFloat(JamClearId, clearNow);
        }

        static Vector2 jamC; static float jamR = 1f, jamTarget, clearTarget, jamNow, clearNow;
        static readonly int JamId = Shader.PropertyToID("_AlatauJam"), JamClearId = Shader.PropertyToID("_AlatauJamClear");
        /// <summary>Traffic around a point: jam 1 = a red queue builds up (v/c pushed over capacity), clear 1 = the roads there turn green
        /// (detour open). Both move smoothly; the clearing takes about five seconds.</summary>
        public static void Jam(Vector2 centre, float radius, float jam, float clear)
        {
            if ((centre - jamC).sqrMagnitude > 1f) { jamNow = 0; clearNow = 0; }
            jamC = centre; jamR = Mathf.Max(radius, 1f); jamTarget = jam; clearTarget = clear;
        }
        public static void JamOff() { jamTarget = clearTarget = jamNow = clearNow = 0; Shader.SetGlobalVector(JamId, Vector4.zero); Shader.SetGlobalFloat(JamClearId, 0); }

        // ------------------------------------------------------------------ public API
        public void Show(string layer, bool on) { if (layers.TryGetValue(layer, out var r)) r.enabled = on; else if (on) Debug.LogWarning("[Alatau] no line layer " + layer); }
        public bool IsShown(string layer) => layers.TryGetValue(layer, out var r) && r.enabled;
        public void HideAll() { foreach (var r in layers.Values) r.enabled = false; }
        /// <summary>Alpha of built / planned / in-works segments of every network layer (module look).</summary>
        public void Style(float built, float planned, float works = 1f)
        {
            foreach (var k in NetKeys) if (layers.TryGetValue(k, out var r)) { var m = r.sharedMaterial; m.SetFloat("_BuiltAlpha", built); m.SetFloat("_PlannedAlpha", planned); m.SetFloat("_WorkAlpha", works); }
        }

        /// <summary>Kilometres of a network that go into service in the given year (laid during that year).</summary>
        public static float KmInWork(string net, int year, int scenario)
        {
            if (!TwinData.Ready || !TwinData.Networks.TryGetValue(net, out var segs)) return 0;
            float m = 0; foreach (var s in segs) if (s.Year[scenario] == year + 1) m += TwinData.Roads[s.Edge].Len; return m / 1000f;
        }
        public static float KmBuilt(string net, int year, int scenario)
        {
            if (!TwinData.Ready || !TwinData.Networks.TryGetValue(net, out var segs)) return 0;
            float m = 0; foreach (var s in segs) if (s.Year[scenario] <= year) m += TwinData.Roads[s.Edge].Len; return m / 1000f;
        }
        public static float RoadKmInWork(int year, int scenario)
        {
            if (!TwinData.Ready) return 0; float m = 0;
            foreach (var e in TwinData.Roads) if (e.Cls == TwinData.RoadClass.Street && e.Year[scenario] == year + 1) m += e.Len; return m / 1000f;
        }

        // ------------------------------------------------------------------ build
        void BuildAll()
        {
            foreach (var r in layers.Values) if (r != null) Destroy(r.gameObject);
            layers.Clear();
            var shader = Shader.Find("AlatauCity/Line"); if (shader == null) { Debug.LogError("[Alatau] AlatauCity/Line shader missing"); return; }
            for (int n = 0; n < NetKeys.Length; n++)
            {
                if (!TwinData.Networks.TryGetValue(NetKeys[n], out var segs)) continue;
                var edges = new List<int>(); var years = new List<Vector4>();
                foreach (var s in segs) { edges.Add(s.Edge); years.Add(new Vector4(s.Year[0], s.Year[1], s.Year[2], s.Year[3])); }
                Make(NetKeys[n], edges, years, NetColors[n], NetLane[n], shader, 0, 3.6f);
            }
            {   // road works: planned streets (they appear in the base map already; the layer marks the year they are built)
                var edges = new List<int>(); var years = new List<Vector4>();
                for (int i = 0; i < TwinData.Roads.Length; i++) { var e = TwinData.Roads[i]; if (e.Cls != TwinData.RoadClass.Street || e.Year[0] <= TwinData.Y0) continue; edges.Add(i); years.Add(new Vector4(e.Year[0], e.Year[1], e.Year[2], e.Year[3])); }
                var r = Make("roadworks", edges, years, RoadWorkColor, 0, shader, 0, 4.4f);
                r.sharedMaterial.SetFloat("_BuiltAlpha", 0f); r.sharedMaterial.SetFloat("_PlannedAlpha", 0f);
            }
            {   // traffic: all roads, colour from v/c
                var edges = new List<int>(); var years = new List<Vector4>();
                for (int i = 0; i < TwinData.Roads.Length; i++) { edges.Add(i); years.Add(Vector4.zero); }
                var r = Make("traffic", edges, years, Color.white, 0, shader, 1, 3.4f);
                trafficTex = new Texture2D(256, 128, TextureFormat.R8, false, true) { name = "Alatau traffic v/c", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
                Shader.SetGlobalTexture(TrafficId, trafficTex); trafficYear = -1;
            }
            HideAll();
            Debug.Log($"[Alatau] line layers built: {layers.Count}");
            // the active module may want its layers now
            TwinState.NotifyLayersReady();
        }

        MeshRenderer Make(string name, List<int> edges, List<Vector4> years, Color color, float lane, Shader shader, int mode, float pixelHalfWidth)
        {
            var pos = new List<Vector3>(); var nrm = new List<Vector3>(); var col = new List<Color>(); var uv0 = new List<Vector2>(); var uv1 = new List<Vector4>(); var uv2 = new List<Vector2>();
            var idx = new List<int>();
            for (int k = 0; k < edges.Count; k++)
            {
                var e = TwinData.Roads[edges[k]]; var g = Densify(e.Geom, 40f); if (g.Count < 2) continue;
                float along = 0; int baseV = pos.Count;
                for (int i = 0; i < g.Count; i++)
                {
                    Vector2 dir = i == 0 ? g[1] - g[0] : i == g.Count - 1 ? g[i] - g[i - 1] : (g[i + 1] - g[i - 1]);
                    if (dir.sqrMagnitude < 1e-6f) dir = Vector2.right; dir.Normalize();
                    var side = new Vector3(-dir.y, 0, dir.x);
                    if (i > 0) along += (g[i] - g[i - 1]).magnitude;
                    var c = new Vector3(g[i].x, CityGround.HeightAt(g[i].x, g[i].y), g[i].y);
                    for (int sgn = -1; sgn <= 1; sgn += 2)
                    {
                        pos.Add(c); nrm.Add(side); col.Add(color); uv0.Add(new Vector2(along, sgn)); uv1.Add(years[k]); uv2.Add(new Vector2(edges[k], lane));
                    }
                    if (i > 0) { int a = baseV + (i - 1) * 2; idx.Add(a); idx.Add(a + 2); idx.Add(a + 1); idx.Add(a + 1); idx.Add(a + 2); idx.Add(a + 3); }
                }
            }
            var mesh = new Mesh { name = "Line " + name, indexFormat = IndexFormat.UInt32 };
            mesh.SetVertices(pos); mesh.SetNormals(nrm); mesh.SetColors(col); mesh.SetUVs(0, uv0); mesh.SetUVs(1, uv1); mesh.SetUVs(2, uv2);
            mesh.SetTriangles(idx, 0, false);
            mesh.bounds = new Bounds(new Vector3(0, 800, 0), new Vector3(90000, 4000, 120000));
            var go = new GameObject("Layer " + name); go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>(); mr.shadowCastingMode = ShadowCastingMode.Off; mr.receiveShadows = false;
            var mat = new Material(shader) { name = "Line " + name }; mat.SetFloat("_Mode", mode); mat.SetFloat("_PixelWidth", pixelHalfWidth);
            mr.sharedMaterial = mat; layers[name] = mr;
            Debug.Log($"[Alatau] line layer {name}: {edges.Count} edges, {pos.Count} vertices");
            return mr;
        }

        static List<Vector2> Densify(Vector2[] g, float step)
        {
            var o = new List<Vector2>(g.Length * 2);
            for (int i = 0; i < g.Length; i++)
            {
                if (i > 0)
                {
                    float L = (g[i] - g[i - 1]).magnitude; int n = Mathf.FloorToInt(L / step);
                    for (int k = 1; k <= n; k++) { float t = k / (n + 1f); o.Add(Vector2.Lerp(g[i - 1], g[i], t)); }
                }
                o.Add(g[i]);
            }
            return o;
        }

        void UpdateTraffic()
        {
            int y = TwinState.Year, s = (int)TwinState.Scenario;
            if (y == trafficYear && s == trafficScen || trafficTex == null || !TwinData.Ready) return;
            trafficYear = y; trafficScen = s;
            var ys = TwinData.TrafficYears; int n = TwinData.Roads.Length;
            int i1 = 0; while (i1 < ys.Length - 1 && ys[i1] < y) i1++;
            int i0 = Mathf.Max(0, i1 - 1); float t = ys[i1] == ys[i0] ? 1f : Mathf.Clamp01((y - ys[i0]) / (float)(ys[i1] - ys[i0]));
            float scale = 1f;
            if (y < ys[0])   // before the first modelled year: scale by population
            {
                float p0 = TwinData.Load(s, "res", -1, ys[0]), py = TwinData.Load(s, "res", -1, y); scale = p0 > 0 ? py / p0 : 0; t = 0; i1 = i0 = 0;
            }
            var a = TwinData.TrafficVc[s][i0]; var b = TwinData.TrafficVc[s][i1];
            for (int i = 0; i < n && i < traffic.Length; i++)
            {
                if (TwinData.Roads[i].Year[s] > y) { traffic[i] = 0; continue; }
                float v = i < a.Length && i < b.Length ? Mathf.Lerp(a[i], b[i], t) * scale : 0f;     // edges added after the traffic model (airport road): no counts
                traffic[i] = (byte)(v < 3 ? 0 : Mathf.Clamp(Mathf.RoundToInt(v), 1, 255));
            }
            trafficTex.SetPixelData(traffic, 0); trafficTex.Apply(false, false);
        }
    }
}
