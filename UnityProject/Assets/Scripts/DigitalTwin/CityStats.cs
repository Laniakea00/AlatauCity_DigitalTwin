using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Aggregates of buildings.csv per district, per use category and per year (effective year of the active scenario).
    /// Demo model: residents = housing GFA / 30 m² (QTwin assumption), jobs = non-residential GFA / m² per job by use (90 business, 50 social, 100 industry, 120 leisure),
    /// rounded per building as the data counts them (buildings.json totals.jobs, the validator): a panel's workplaces equal the data's to the unit.</summary>
    public static class CityStats
    {
        public const int Years = TwinState.MaxYear - TwinState.MinYear + 1, Districts = 4, Cats = 5;
        public static readonly string[] DistrictIds = { "Gate", "Golden", "Growing", "Green" };
        public static readonly Color[] DistrictColors = { Hex("#2e63b0"), Hex("#d9a621"), Hex("#f27336"), Hex("#339e5c") };
        public static readonly float[] DistrictAreaHa = { 3988, 15660, 36622, 31730 };
        public static readonly float[] DistrictTarget2050k = { 223, 675, 650, 320 };   // residents, thousands (QTwin demo scenario)
        public static readonly string[] CatKeys = { "cat_housing", "cat_business", "cat_social", "cat_industry", "cat_leisure" };
        public static readonly Color[] CatColors = { Hex("#e3b341"), Hex("#ef6a6a"), Hex("#a371f7"), Hex("#8b98a8"), Hex("#2dd4bf") };
        public const float M2PerResident = 30f;
        /// <summary>The existing (OSM) stock by the data's own rule (CONTRACT §8: the traffic model, the land tools and the validator count it
        /// so): a building up to 600 m² is a home at M2PerResident, a larger one is workplaces at 100 m² per job. Counted in every year,
        /// never as new floor area (readiness and the growth charts stay the plan's). Workplaces are rounded per building, as the data rounds them.</summary>
        public const float ExistingHomeM2 = 600f, ExistingM2PerJob = 100f;
        public static float[] ExistingRes = new float[Districts], ExistingJobs = new float[Districts];
        static readonly float[] M2PerJob = { 0, 90f, 50f, 100f, 120f };   // calibrated: ≈ 1 mln jobs in 2050 (official target), same as Tools/twin_gen/norms.py

        // cumulative GFA [district][cat][yearIndex], m²; built-count [district][yearIndex]; new this year [district][yearIndex]
        public static float[,,] CumGfa = new float[Districts, Cats, Years];
        public static int[,] CumCount = new int[Districts, Years], NewCount = new int[Districts, Years];
        /// <summary>Cumulative workplaces of the new stock [district][yearIndex]: each building's own round(GFA / m² per job), summed (the data's rule).</summary>
        public static int[,] CumJobs = new int[Districts, Years];
        public static float TotalPlannedGfa;            // all planned GFA regardless of scenario (readiness denominator)
        public static int[] EffYear = new int[0];      // bid -> effective year (active scenario)
        public static Bounds[] DistrictBounds = new Bounds[Districts];
        public static bool Ready;

        public static int DistrictIndex(string d) { for (int i = 0; i < Districts; i++) if (DistrictIds[i] == d) return i; return -1; }
        public static int Cat(string use) => use switch { "housing" => 0, "business" => 1, "social" => 2, "industry" => 3, "energy" => 3, "leisure" => 4, _ => -1 };

        public static void Rebuild(Scenario s)
        {
            var db = CityDatabase.Instance; if (db == null || db.Buildings.Length == 0) return;
            CumGfa = new float[Districts, Cats, Years]; CumCount = new int[Districts, Years]; NewCount = new int[Districts, Years]; CumJobs = new int[Districts, Years]; stand = null;
            TotalPlannedGfa = 0; EffYear = new int[db.Buildings.Length]; plannedByDistrict = new float[Districts];
            ExistingRes = new float[Districts]; ExistingJobs = new float[Districts];
            var first = new bool[Districts];
            foreach (var b in db.Counted)                   // with the mesh-less rows of landmark lots (their own homes and jobs)
            {
                if (b == null) continue;
                int e = TwinScenario.EffectiveYear(b, s); if (b.Bid >= 0 && b.Bid < EffYear.Length) EffYear[b.Bid] = e;
                int d = DistrictIndex(b.District); if (d < 0) continue;
                var p = new Vector3(b.X, b.GroundM, b.Z);
                if (!first[d]) { DistrictBounds[d] = new Bounds(p, Vector3.zero); first[d] = true; } else DistrictBounds[d].Encapsulate(p);
                int c = Cat(b.Use);
                if (c < 0)                                      // existing OSM stock is not "new" floor area: its people and jobs only
                {
                    if (b.Source == "existing_osm" && b.GfaM2 > 0f) { if (b.GfaM2 <= ExistingHomeM2) ExistingRes[d] += b.GfaM2 / M2PerResident; else ExistingJobs[d] += JobsOf(b.GfaM2, ExistingM2PerJob); }
                    continue;
                }
                TotalPlannedGfa += b.GfaM2; plannedByDistrict[d] += b.GfaM2;
                if (e > TwinState.MaxYear) continue;
                int yi = Mathf.Max(0, e - TwinState.MinYear);
                int one = b.Kind == CityDatabase.LotKind ? 0 : 1;          // a lot row is floor area, not a building
                int jobs = c > 0 ? JobsOf(b.GfaM2, M2PerJob[c]) : 0;
                for (int y = yi; y < Years; y++) { CumGfa[d, c, y] += b.GfaM2; CumCount[d, y] += one; CumJobs[d, y] += jobs; }
                NewCount[d, yi] += one;
            }
            LoadPolys();                                    // the outlines of districts.json, if there (logged once)
            RebuildPlan(s, db);
            Ready = true;
        }
        /// <summary>One building's workplaces as the data counts them: round(GFA / m² per job), half to even (Python's round).</summary>
        static int JobsOf(float gfa, float m2PerJob) => (int)System.Math.Round(gfa / (double)m2PerJob, System.MidpointRounding.ToEven);

        // ---- the area the plan redrew (Data.GroundStats: the cells of map_ground): the same figures for that part of a district ----
        /// <summary>Cumulative GFA [district][cat][yearIndex] of the buildings inside the redrawn area; its existing houses' people and jobs.</summary>
        public static float[,,] PlanGfa = new float[Districts, Cats, Years];
        static int[,] planJobs = new int[Districts, Years];
        public static float[] PlanExistingRes = new float[Districts], PlanExistingJobs = new float[Districts];
        public static int[] PlanBuildings = new int[Districts];
        static void RebuildPlan(Scenario s, CityDatabase db)
        {
            PlanGfa = new float[Districts, Cats, Years]; planJobs = new int[Districts, Years]; PlanExistingRes = new float[Districts]; PlanExistingJobs = new float[Districts]; PlanBuildings = new int[Districts];
            if (!Data.GroundStats.HasPlan) return;
            foreach (var b in db.Counted)
            {
                if (b == null || !Data.GroundStats.InPlan(b.X, b.Z)) continue;
                int d = DistrictIndex(b.District); if (d < 0) continue;
                int c = Cat(b.Use);
                if (c < 0)
                {
                    if (b.Source != "existing_osm" || b.GfaM2 <= 0f) continue;
                    PlanBuildings[d]++;
                    if (b.GfaM2 <= ExistingHomeM2) PlanExistingRes[d] += b.GfaM2 / M2PerResident; else PlanExistingJobs[d] += JobsOf(b.GfaM2, ExistingM2PerJob);
                    continue;
                }
                if (b.Kind != CityDatabase.LotKind) PlanBuildings[d]++;
                int e = TwinScenario.EffectiveYear(b, s); if (e > TwinState.MaxYear) continue;
                int jobs = c > 0 ? JobsOf(b.GfaM2, M2PerJob[c]) : 0;
                for (int y = Mathf.Max(0, e - TwinState.MinYear); y < Years; y++) { PlanGfa[d, c, y] += b.GfaM2; planJobs[d, y] += jobs; }
            }
        }
        /// <summary>People in the redrawn area of district d (−1 = all) in a year, by the same rules as People.</summary>
        public static float PlanPeople(int district, int year)
        {
            int yi = YI(year); float v = 0;
            for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += PlanGfa[d, 0, yi] / M2PerResident + PlanExistingRes[d];
            return v;
        }
        /// <summary>Workplaces in the redrawn area of district d (−1 = all) in a year, by the same rules as Workplaces.</summary>
        public static float PlanWorkplaces(int district, int year)
        {
            int yi = YI(year); float v = 0;
            for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += PlanExistingJobs[d] + planJobs[d, yi];
            return v;
        }

        public static int EffectiveYearOf(int bid) => bid >= 0 && bid < EffYear.Length ? EffYear[bid] : 0;

        // ---- queries (district = -1 → whole city) ----
        static int YI(int year) => Mathf.Clamp(year - TwinState.MinYear, 0, Years - 1);
        public static float Gfa(int district, int cat, int year)
        {
            int yi = YI(year); float v = 0;
            for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += CumGfa[d, cat, yi];
            return v;
        }
        public static float GfaAll(int district, int year) { float v = 0; for (int c = 0; c < Cats; c++) v += Gfa(district, c, year); return v; }
        /// <summary>Residents of the new stock (housing floor area / M2PerResident).</summary>
        public static float Residents(int district, int year) => Gfa(district, 0, year) / M2PerResident;
        /// <summary>Workplaces of the new stock, each building rounded as the data rounds it.</summary>
        public static float Jobs(int district, int year) { int yi = YI(year), v = 0; for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += CumJobs[d, yi]; return v; }
        /// <summary>Everybody who lives there in the year, as the data counts them: the new stock and the existing houses (the panels).</summary>
        public static float People(int district, int year) => Residents(district, year) + Existing(ExistingRes, district);
        /// <summary>Every workplace in the year, as the data counts them: the new stock and the large existing buildings (the panels).</summary>
        public static float Workplaces(int district, int year) => Jobs(district, year) + Existing(ExistingJobs, district);
        static float Existing(float[] a, int district) { float v = 0; for (int d = 0; d < Districts && d < a.Length; d++) if (district < 0 || d == district) v += a[d]; return v; }
        /// <summary>Jobs of one use category (1 business … 4 leisure).</summary>
        public static float Jobs1(int cat, int year, int district = -1) => cat <= 0 || cat >= Cats ? 0f : Gfa(district, cat, year) / M2PerJob[cat];
        public static float Readiness(int district, int year)
        {
            if (district < 0) return TotalPlannedGfa > 0 ? GfaAll(-1, year) / TotalPlannedGfa : 0;
            return GfaAll(district, TwinState.MaxYear) > 0 ? GfaAll(district, year) / PlannedGfa(district) : 0;
        }
        static float[] plannedByDistrict = new float[Districts];
        static float PlannedGfa(int district) => plannedByDistrict[district];
        /// <summary>The readiness denominator of district d (−1 = the city): all its planned floor area.</summary>
        public static float PlannedGfaOf(int district) => district < 0 ? TotalPlannedGfa : district < Districts ? plannedByDistrict[district] : 0f;
        public static int Count(int district, int year) { int yi = YI(year), v = 0; for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += CumCount[d, yi]; return v; }
        /// <summary>Buildings standing on the map in the year: the new ones built by then and the existing ones (the village, the town),
        /// less those the map takes away by then (a landmark's plot, MapOrder: LandmarkSystem.GoneYear). Count is the new stock only.</summary>
        public static int Standing(int district, int year)
        {
            if (stand == null || standFor != Landmarks.LandmarkSystem.HiddenVersion) BuildStanding();
            int yi = YI(year), v = 0; for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += stand[d, yi]; return v;
        }
        static int[,] stand; static int standFor = -1;
        static void BuildStanding()
        {
            standFor = Landmarks.LandmarkSystem.HiddenVersion; stand = new int[Districts, Years + 1];
            var db = CityDatabase.Instance; if (db == null) return;
            foreach (var b in db.Buildings)                 // drawn buildings only (a lot row is floor area, not a building)
            {
                if (b == null || b.Kind == "removed") continue;
                int d = DistrictIndex(b.District); if (d < 0) continue;
                bool existing = b.Source == "existing_osm"; if (!existing && Cat(b.Use) < 0) continue;
                int from = existing ? TwinState.MinYear : TwinScenario.EffectiveYear(b, TwinState.Scenario), to = Mathf.Min(Landmarks.LandmarkSystem.GoneYear(b.Bid), TwinState.MaxYear + 1);
                int a = Mathf.Max(0, from - TwinState.MinYear), z = Mathf.Clamp(to - TwinState.MinYear, 0, Years); if (z <= a) continue;
                stand[d, a]++; stand[d, z]--;
            }
            for (int d = 0; d < Districts; d++) for (int y = 1; y <= Years; y++) stand[d, y] += stand[d, y - 1];
        }
        public static int NewThisYear(int district, int year) { int yi = YI(year), v = 0; for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += NewCount[d, yi]; return v; }

        static Color Hex(string h) => ColorUtility.TryParseHtmlString(h, out var c) ? c : Color.magenta;

        // ---- district outlines: Resources/Landmarks/districts.json of the new map data (tools/map CONTRACT §6), from city.json ----
        [System.Serializable] class DistrictJ { public int id; public string name; public float[] p; }
        [System.Serializable] class DistrictsJ { public int v; public DistrictJ[] d; }
        static System.Collections.Generic.List<Vector2[]>[] polys; static bool polysLoaded;
        /// <summary>The outline(s) of district d (null without districts.json: then the box round the district's buildings stands in).</summary>
        public static System.Collections.Generic.IReadOnlyList<Vector2[]> DistrictPolys(int d) { LoadPolys(); return polys != null && d >= 0 && d < Districts && polys[d].Count > 0 ? polys[d] : null; }
        public static bool HasOutlines { get { LoadPolys(); return polys != null; } }
        static void LoadPolys()
        {
            if (polysLoaded) return; polysLoaded = true;
            var txt = MapPolys.Load("districts"); if (txt == null) return;
            DistrictsJ j; try { j = JsonUtility.FromJson<DistrictsJ>(txt); } catch (System.Exception ex) { Debug.LogWarning("[Alatau] districts.json unreadable: " + ex.Message); return; }
            if (j?.d == null) return;
            var ps = new System.Collections.Generic.List<Vector2[]>[Districts]; for (int i = 0; i < Districts; i++) ps[i] = new System.Collections.Generic.List<Vector2[]>();
            int n = 0;
            foreach (var e in j.d)
            {
                int d = !string.IsNullOrEmpty(e.name) ? DistrictIndex(e.name) : -1; if (d < 0) d = e.id;     // the name wins over the number
                var r = MapPolys.Ring(e.p); if (r == null || d < 0 || d >= Districts) continue;
                ps[d].Add(r); n++;
            }
            if (n == 0) return;
            polys = ps;
            var sb = new System.Text.StringBuilder("[Alatau] districts.json: ");
            for (int d = 0; d < Districts; d++) { float a = 0f; foreach (var r in ps[d]) a += Mathf.Abs(MapPolys.SignedArea(r)); sb.Append($"{DistrictIds[d]} {ps[d].Count} ring(s) {a / 10000f:0} ha (stated {DistrictAreaHa[d]:0} ha){(d < Districts - 1 ? "; " : "")}"); }
            Debug.Log(sb.ToString());
        }
        /// <summary>The district (0..3) a point lies in, by the outlines of districts.json; without them by the boxes round each
        /// district's buildings (the smallest box that holds it); -1 = outside every district.</summary>
        public static int DistrictAt(float x, float z)
        {
            LoadPolys();
            if (polys != null)
            {
                for (int d = 0; d < Districts; d++) foreach (var r in polys[d]) if (MapPolys.Inside(r, x, z)) return d;
                return -1;
            }
            int best = -1; float area = float.MaxValue;
            for (int d = 0; d < Districts; d++)
            {
                var b = DistrictBounds[d]; if (b.size.x <= 0f) continue;
                if (x < b.min.x || x > b.max.x || z < b.min.z || z > b.max.z) continue;
                float a = b.size.x * b.size.z; if (a < area) { area = a; best = d; }
            }
            return best;
        }
        /// <summary>Middle of district d: of its outline (the largest ring when the area centre falls outside), else of the box round its buildings.</summary>
        public static Vector2 DistrictCentre(int d)
        {
            d = Mathf.Clamp(d, 0, Districts - 1);
            var ps = DistrictPolys(d);
            if (ps != null)
            {
                double ax = 0, az = 0, aw = 0; Vector2[] big = ps[0]; float bigA = 0f;
                foreach (var r in ps) { float a = Mathf.Abs(MapPolys.SignedArea(r)); var c = MapPolys.Centre(r); ax += c.x * a; az += c.y * a; aw += a; if (a > bigA) { bigA = a; big = r; } }
                var m = aw > 0 ? new Vector2((float)(ax / aw), (float)(az / aw)) : MapPolys.Centre(big);
                foreach (var r in ps) if (MapPolys.Inside(r, m.x, m.y)) return m;
                return MapPolys.Centre(big);
            }
            var bc = DistrictBounds[d].center; return new Vector2(bc.x, bc.z);
        }
    }
}
