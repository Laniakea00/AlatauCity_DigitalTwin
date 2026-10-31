using System;
using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>Flood of the Kapshagay shore as a calculation, not an animation (situation centre, presentation tour).
    /// 1) Relief: the twin's own 50 m height grid (CityGround), which is real elevation — checked against Copernicus GLO-30
    ///    (r = 0.9998; the twin is 2 m below GLO-30 at the reservoir surface: 475 vs 477 m, so real mark = twin height + 2 m).
    /// 2) Bathtub with connectivity: a priority flood from the reservoir cells gives every cell the lowest reservoir mark at which
    ///    water reaches it over the relief (spill level). A cell is wet at level L when that mark is below L — low ground behind a
    ///    ridge stays dry until the ridge is overtopped. One pass at start, then any level is instant.
    /// 3) Time: the reservoir rises by (inflow − release) × 1 day / mirror area per day.
    /// 4) Damage: JRC depth-damage curve for housing in Asia × the building's value; evacuation: residents of the wet and at-risk
    ///    buildings go to the nearest large social building on high ground: on foot up to 1.5 km, the rest by bus.</summary>
    public static class FloodModel
    {
        public const string SrcDem = "cop_glo30", SrcGes = "tengri_ges_0726", SrcJrc = "jrc_ddf_2017", Model = "model_flood_relief";
        public const float Datum = 2f;            // real mark (GLO-30) = twin height + Datum, at the reservoir surface
        public const float NowReal = 477f;        // Tengrinews 16.07.2026: «477–478 м» now; 477 m is also the reservoir surface in GLO-30
        public const float LimitReal = 479f;      // the upper operating limit lowered to 479 m
        public const float DesignReal = 485f;     // the design mark of the reservoir
        public const float MirrorKm2 = 1213f;     // water surface of the reservoir in GLO-30 (flat 477 m cells, tiles N43 E077–E078)
        public const float ReleaseM3s = 600f;     // release of the Kapshagay HPP on the day of the article
        public const float InflowM3s = 2500f;     // model: spring high water of the Ili
        public const float CostPerM2 = 300000f;   // ₸ per m² of floor area (model, as in the city's flood risk tab)
        public const int Buses = 120, Seats = 80; // model: city buses and the emergency service
        public const float MeasuresMln = 1500f;   // model: cost of the measures (sandbag dam, pumps, evacuation), mln ₸
        public static readonly float[] Levels = { LimitReal, 481f, 483f, DesignReal };
        public static float Level = 481f;

        static bool reg;
        /// <summary>Source and model entries of the flood (call before a panel shows its chips).</summary>
        public static void Register()
        {
            if (reg) return; reg = true;
            Sources.Register(SrcDem, "Рельеф: Copernicus DEM GLO-30, 30 м", "ESA Copernicus · AWS Open Data", "30.10.2026",
                "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N43_00_E077_00_DEM/Copernicus_DSM_COG_10_N43_00_E077_00_DEM.tif",
                "Тайлы N43 E076–E078 загружены 30.10.2026. Сетка высот двойника (50 м) сверена с ними: корреляция 0,9998, расхождение ±1–3 м. Зеркало Капшагая в GLO-30: 477 м, ≈1 213 км².");
            Sources.Register(SrcGes, "Как устроена Капшагайская ГЭС", "Tengrinews", "16.07.2026",
                "https://tengrinews.kz/article/baklanyi-katamaranyi-milliardyi-kilovatt-energii-ustroena-4245/",
                "Проектная отметка водохранилища 485 м; верхний предел снижен до 479 м; сейчас 477–478 м; сброс ГЭС в день съёмки 600 м³/с.");
            Sources.Register(SrcJrc, "Global flood depth-damage functions", "EC JRC · Huizinga и др.", "2017",
                "https://publications.jrc.ec.europa.eu/repository/handle/JRC105688",
                "Доля ущерба жилью (Азия) от глубины воды: 0,5 м — 33 %, 1 м — 49 %, 2 м — 72 %, 3 м — 87 %, 6 м — 100 %.");
            Sources.RegisterModel(Model, "Паводок по рельефу и эвакуация",
                "Ванна со связностью: вода заходит от водохранилища только туда, куда может дойти по рельефу. Приток Или 2 500 м³/с (сценарий), сброс 600 м³/с. " +
                "Стоимость зданий 300 тыс. ₸/м², страдает нижний этаж. Эвакуация: оповещение 15 мин, пешком до 1,5 км (4,5 км/ч), дальше 120 автобусов по 80 мест (25 км/ч), пути по дорогам ×1,35. Не заменяет гидрологический расчёт.");
        }

        // ------------------------------------------------------------------ spill levels (priority flood), twin metres
        static float[] F; static int nx, ny; static float st, x0, z0;
        const float Cap = 492f;                     // cells above this never take water in any scenario (twin metres)
        public static bool Ready => Build();

        static bool Build()
        {
            if (F != null) return true; if (!CityGround.GridReady) return false;
            nx = CityGround.GridNX; ny = CityGround.GridNY; st = CityGround.GridStep; x0 = CityGround.GridX0; z0 = CityGround.GridZ0;
            int n = nx * ny; var f = new float[n]; for (int i = 0; i < n; i++) f[i] = float.MaxValue;
            var hk = new float[1 << 16]; var hi = new int[1 << 16]; int hn = 0;
            void Push(float k, int id)
            {
                if (hn == hk.Length) { Array.Resize(ref hk, hn * 2); Array.Resize(ref hi, hn * 2); }
                int j = hn++; while (j > 0) { int p = (j - 1) >> 1; if (hk[p] <= k) break; hk[j] = hk[p]; hi[j] = hi[p]; j = p; }
                hk[j] = k; hi[j] = id;
            }
            for (int i = 0; i < n; i++) { float h = CityGround.RawHeight(i); if (Mathf.Abs(h - 475f) < 0.02f) { f[i] = h; Push(h, i); } }
            while (hn > 0)
            {
                float k = hk[0]; int id = hi[0];
                // pop: move the last to the root and sift down
                hn--; if (hn > 0)
                {
                    float lk = hk[hn]; int li = hi[hn]; int j = 0;
                    while (true) { int a = 2 * j + 1; if (a >= hn) break; int b = a + 1 < hn && hk[a + 1] < hk[a] ? a + 1 : a; if (hk[b] >= lk) break; hk[j] = hk[b]; hi[j] = hi[b]; j = b; }
                    hk[j] = lk; hi[j] = li;
                }
                if (k > f[id]) continue;
                int r = id / nx, c = id - r * nx;
                for (int d = 0; d < 4; d++)
                {
                    int rr = r + (d == 0 ? 1 : d == 1 ? -1 : 0), cc = c + (d == 2 ? 1 : d == 3 ? -1 : 0);
                    if (rr < 0 || rr >= ny || cc < 0 || cc >= nx) continue;
                    int q = rr * nx + cc; float h = CityGround.RawHeight(q); if (h >= Cap) continue;
                    float nk = Mathf.Max(k, h); if (nk < f[q]) { f[q] = nk; Push(nk, q); }
                }
            }
            F = f; return true;
        }
        static int Cell(float x, float z)
        {
            int c = Mathf.RoundToInt((x - x0) / st), r = Mathf.RoundToInt((z - z0) / st);
            return c < 0 || r < 0 || c >= nx || r >= ny ? -1 : r * nx + c;
        }
        /// <summary>Spill level of grid cell i, twin metres (Build() must have run).</summary>
        public static float SpillTwin(int i) => F[i];
        /// <summary>Lowest real reservoir mark at which water reaches the point (float.MaxValue: never in these scenarios).</summary>
        public static float SpillReal(float x, float z) { if (!Build()) return float.MaxValue; int i = Cell(x, z); return i < 0 || F[i] == float.MaxValue ? float.MaxValue : F[i] + Datum; }

        // JRC 2017, residential, Asia
        static readonly float[] DD = { 0f, 0.5f, 1f, 1.5f, 2f, 3f, 4f, 5f, 6f }, DF = { 0f, 0.33f, 0.49f, 0.62f, 0.72f, 0.87f, 0.93f, 0.98f, 1f };
        public static float DamageShare(float depth)
        {
            if (depth <= 0) return 0; if (depth >= 6f) return 1f;
            for (int i = 1; i < DD.Length; i++) if (depth <= DD[i]) return Mathf.Lerp(DF[i - 1], DF[i], (depth - DD[i - 1]) / (DD[i] - DD[i - 1]));
            return 1f;
        }
        /// <summary>Cost of inaction at a level, mln ₸: the damage without measures minus what the measures leave (today's mark) and cost.
        /// The same number as the situation centre's «Цена бездействия» of the flood incident.</summary>
        public static float InactionMln(float real, int year) => Mathf.Max(0f, Compute(real, year).DamageMln - Compute(NowReal, year).DamageMln - MeasuresMln);
        /// <summary>Days for the reservoir to rise from today's mark to 'real' at the scenario inflow.</summary>
        public static float DaysTo(float real) => real <= NowReal ? 0f : (real - NowReal) * MirrorKm2 * 1e6f / ((InflowM3s - ReleaseM3s) * 86400f);
        public static float RisePerDayCm => (InflowM3s - ReleaseM3s) * 86400f / (MirrorKm2 * 1e6f) * 100f;

        // ------------------------------------------------------------------ one level
        public class Point { public Vector2 P; public float People; public string Name; }
        public class Result
        {
            public float LevelReal, AreaKm2, People, DamageMln, RiskPeople, EvacPeople, EvacMin, WalkShare, MaxDepth, Days; public int Buildings, RiskBuildings;
            public readonly HashSet<int> Wet = new HashSet<int>(), Risk = new HashSet<int>(); public readonly List<Point> Points = new List<Point>(); public Vector2 Center;
        }
        static readonly Dictionary<string, Result> cache = new Dictionary<string, Result>();

        public static Result Compute(float real, int year)
        {
            string key = real.ToString("0.00") + ":" + year + ":" + (int)TwinState.Scenario;
            if (cache.TryGetValue(key, out var hit)) return hit;
            var R = new Result { LevelReal = real, Days = DaysTo(real) };
            var db = CityDatabase.Instance; if (!Build() || db == null) return R;
            float L = real - Datum; int land = 0;
            for (int i = 0; i < F.Length; i++) if (F[i] < L && CityGround.RawHeight(i) > 475.02f) land++;
            R.AreaKm2 = land * st * st / 1e6f;
            // buildings: wet (water at the building) and at risk (water would reach it one metre higher)
            var shelters = new List<BuildingInfo>(); double sx = 0, sz = 0, sw = 0;
            var evac = new List<(Vector2 p, float n)>();
            foreach (var b in db.Buildings)
            {
                if (b == null || !SituationData.Stands(b, year)) continue;
                int i = Cell(b.X, b.Z); if (i < 0) continue; float sp = F[i];
                if (sp >= L + 3f && b.Use == "social" && b.GfaM2 >= 2000f) { shelters.Add(b); continue; }
                float res = SituationData.ResidentsOf(b);
                if (sp < L && b.GroundM < L)
                {
                    float depth = L - b.GroundM; R.Wet.Add(b.Bid); R.Buildings++; R.People += res; R.MaxDepth = Mathf.Max(R.MaxDepth, depth);
                    R.DamageMln += b.GfaM2 * CostPerM2 * DamageShare(depth) * Mathf.Min(1f, 3.5f / Mathf.Max(3.5f, b.HeightM)) / 1e6f;
                    sx += b.X * (res + 1); sz += b.Z * (res + 1); sw += res + 1; if (res > 0) evac.Add((new Vector2(b.X, b.Z), res));
                }
                else if (sp < L + 1f) { R.Risk.Add(b.Bid); R.RiskBuildings++; R.RiskPeople += res; if (res > 0) evac.Add((new Vector2(b.X, b.Z), res)); }
            }
            R.Center = sw > 0 ? new Vector2((float)(sx / sw), (float)(sz / sw)) : new Vector2(9000f, 19000f);
            // evacuation: 500 m clusters of evacuees → the nearest shelter
            var clusters = new Dictionary<long, (Vector2 s, float n)>();
            foreach (var (p, n) in evac)
            {
                long k = ((long)Mathf.FloorToInt(p.x / 500f) << 32) ^ (uint)Mathf.FloorToInt(p.y / 500f);
                clusters[k] = clusters.TryGetValue(k, out var v) ? (v.s + p * n, v.n + n) : (p * n, n);
            }
            // each shelter takes as many people as its floor area allows (3 m² per person); a cluster fills the nearest ones first
            var dest = new Dictionary<int, Point>(); float walkN = 0, walkMax = 0, busN = 0, busT = 0, busMax = 0;
            var left = new float[shelters.Count]; for (int k = 0; k < left.Length; k++) left[k] = shelters[k].GfaM2 / 3f;
            var order = new int[shelters.Count]; var dist = new float[shelters.Count];
            foreach (var kv in clusters)
            {
                var c = kv.Value.s / kv.Value.n; float n = kv.Value.n;
                for (int k = 0; k < order.Length; k++) { order[k] = k; dist[k] = (new Vector2(shelters[k].X, shelters[k].Z) - c).sqrMagnitude; }
                Array.Sort((float[])dist.Clone(), order);
                for (int j = 0; j < order.Length && n > 0.5f; j++)
                {
                    int k = order[j]; if (left[k] <= 0) continue;
                    float take = Mathf.Min(n, left[k]); left[k] -= take; n -= take; var best = shelters[k];
                    float km = Mathf.Sqrt(dist[k]) * 1.35f / 1000f;
                    if (km <= 1.5f) { walkN += take; walkMax = Mathf.Max(walkMax, km / 4.5f * 60f); }
                    else { float t = km / 25f * 60f; busN += take; busT += t * take; busMax = Mathf.Max(busMax, t); }
                    if (!dest.TryGetValue(best.Bid, out var pt)) dest[best.Bid] = pt = new Point { P = new Vector2(best.X, best.Z), Name = ShelterName(best) };
                    pt.People += take;
                }
            }
            R.EvacPeople = walkN + busN; R.WalkShare = R.EvacPeople > 0 ? walkN / R.EvacPeople : 0;
            float bus = 0;
            if (busN > 0) { float avg = busT / busN; int rounds = Mathf.CeilToInt(busN / (Buses * Seats)); bus = 10f + (rounds - 1) * 2f * avg + busMax; }
            R.EvacMin = R.EvacPeople > 0 ? 15f + Mathf.Max(walkMax, bus) : 0;
            R.Points.AddRange(dest.Values); R.Points.Sort((a, b) => b.People.CompareTo(a.People));
            if (cache.Count > 40) cache.Clear();
            cache[key] = R; return R;
        }
        static string ShelterName(BuildingInfo b) => b.Kind == "education" ? "Школа" : b.Kind == "health" ? "Больница" : "Общественный центр";

        /// <summary>Building colours of a flood result: wet red, at risk amber; 'saved' paints the wet ones green (measures taken).</summary>
        public static Color Tint(Result r, BuildingInfo b, bool saved)
        {
            if (r.Wet.Contains(b.Bid)) return saved ? new Color(0.22f, 0.82f, 0.42f, 0.85f) : new Color(1f, 0.28f, 0.20f, 0.92f);
            if (r.Risk.Contains(b.Bid)) return saved ? new Color(0.22f, 0.82f, 0.42f, 0.55f) : new Color(0.96f, 0.65f, 0.14f, 0.85f);
            return new Color(0, 0, 0, 0);
        }
    }

    /// <summary>The water of a flood result: a sheet over every wet cell at the water level (rows of cells merged into strips), so the
    /// shoreline follows the relief. Rebuilt only when the level changes.</summary>
    public static class FloodWater
    {
        static GameObject go; static Mesh mesh; static float shown = float.NaN;
        public static bool Visible => go != null && go.activeSelf;
        public static void Show(float real)
        {
            if (!FloodModel.Ready) return;
            if (go == null)
            {
                var sh = Shader.Find("AlatauCity/Water"); if (sh == null) { Debug.LogWarning("[Alatau] water shader missing"); return; }
                go = new GameObject("Flood water (model)"); var mf = go.AddComponent<MeshFilter>(); var mr = go.AddComponent<MeshRenderer>();
                var mat = new Material(sh) { name = "Flood water (model)" }; mr.sharedMaterial = mat;
                // flood water over land reads as water, not as wet sand: cool muddy blue, less brown
                mat.SetColor("_Shallow", new Color(0.20f, 0.33f, 0.42f, 1f)); mat.SetFloat("_Turbid", 0.25f); mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                mesh = new Mesh { name = "Flood water", indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 }; mf.sharedMesh = mesh;
            }
            go.SetActive(true);
            var cam = Camera.main; if (cam != null) cam.depthTextureMode |= DepthTextureMode.Depth;   // the water colours by depth
            if (real <= FloodModel.NowReal + 0.3f) { go.SetActive(false); shown = float.NaN; return; }   // today's reservoir: the ground draws it
            if (Mathf.Abs(shown - real) < 0.01f) return;
            shown = real; Rebuild(real - FloodModel.Datum);
        }
        public static void Hide() { if (go != null) { go.SetActive(false); go.transform.position = Vector3.zero; } }
        /// <summary>Raises the sheet by dy metres without rebuilding it (smooth motion between recomputed levels).</summary>
        public static void Lift(float dy) { if (go != null) go.transform.position = new Vector3(0f, dy, 0f); }

        static void Rebuild(float L)
        {
            int nx = CityGround.GridNX, ny = CityGround.GridNY; float s = CityGround.GridStep, x0 = CityGround.GridX0, z0 = CityGround.GridZ0, y = L + 0.05f;
            var v = new List<Vector3>(); var t = new List<int>();
            for (int r = 0; r < ny; r++)
            {
                int c = 0;
                while (c < nx)
                {
                    if (!Wet(r * nx + c, L)) { c++; continue; }
                    int c0 = c; while (c < nx && Wet(r * nx + c, L)) c++;
                    // the strip reaches half a cell beyond its wet cells: the terrain itself cuts the shoreline there
                    float xa = x0 + (c0 - 1f) * s, xb = x0 + c * s, za = z0 + (r - 0.5f) * s, zb = z0 + (r + 0.5f) * s; int k = v.Count;
                    v.Add(new Vector3(xa, y, za)); v.Add(new Vector3(xb, y, za)); v.Add(new Vector3(xb, y, zb)); v.Add(new Vector3(xa, y, zb));
                    t.Add(k); t.Add(k + 2); t.Add(k + 1); t.Add(k); t.Add(k + 3); t.Add(k + 2);
                }
            }
            mesh.Clear(); mesh.SetVertices(v); mesh.SetTriangles(t, 0);
            var n = new Vector3[v.Count]; for (int i = 0; i < n.Length; i++) n[i] = Vector3.up; mesh.normals = n; mesh.RecalculateBounds();
        }
        static bool Wet(int i, float L) => FloodModel.SpillTwin(i) < L && CityGround.RawHeight(i) < L - 0.25f;
    }
}
