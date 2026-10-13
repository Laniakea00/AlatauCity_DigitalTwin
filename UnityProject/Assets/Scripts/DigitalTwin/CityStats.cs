using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Aggregates of buildings.csv per district, per use category and per year (effective year of the active scenario).
    /// Demo model: residents = housing GFA / 30 m² (QTwin assumption), jobs = non-residential GFA / m² per job by use (90 business, 50 social, 100 industry, 120 leisure).</summary>
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
        static readonly float[] M2PerJob = { 0, 90f, 50f, 100f, 120f };   // calibrated: ≈ 1 mln jobs in 2050 (official target), same as Tools/twin_gen/norms.py

        // cumulative GFA [district][cat][yearIndex], m²; built-count [district][yearIndex]; new this year [district][yearIndex]
        public static float[,,] CumGfa = new float[Districts, Cats, Years];
        public static int[,] CumCount = new int[Districts, Years], NewCount = new int[Districts, Years];
        public static float TotalPlannedGfa;            // all planned GFA regardless of scenario (readiness denominator)
        public static int[] EffYear = new int[0];      // bid -> effective year (active scenario)
        public static Bounds[] DistrictBounds = new Bounds[Districts];
        public static bool Ready;

        public static int DistrictIndex(string d) { for (int i = 0; i < Districts; i++) if (DistrictIds[i] == d) return i; return -1; }
        public static int Cat(string use) => use switch { "housing" => 0, "business" => 1, "social" => 2, "industry" => 3, "energy" => 3, "leisure" => 4, _ => -1 };

        public static void Rebuild(Scenario s)
        {
            var db = CityDatabase.Instance; if (db == null || db.Buildings.Length == 0) return;
            CumGfa = new float[Districts, Cats, Years]; CumCount = new int[Districts, Years]; NewCount = new int[Districts, Years];
            TotalPlannedGfa = 0; EffYear = new int[db.Buildings.Length]; plannedByDistrict = new float[Districts];
            var first = new bool[Districts];
            foreach (var b in db.Buildings)
            {
                if (b == null) continue;
                int e = TwinScenario.EffectiveYear(b, s); if (b.Bid >= 0 && b.Bid < EffYear.Length) EffYear[b.Bid] = e;
                int d = DistrictIndex(b.District); if (d < 0) continue;
                var p = new Vector3(b.X, b.GroundM, b.Z);
                if (!first[d]) { DistrictBounds[d] = new Bounds(p, Vector3.zero); first[d] = true; } else DistrictBounds[d].Encapsulate(p);
                int c = Cat(b.Use); if (c < 0) continue;      // existing OSM stock is not "new" floor area
                TotalPlannedGfa += b.GfaM2; plannedByDistrict[d] += b.GfaM2;
                if (e > TwinState.MaxYear) continue;
                int yi = Mathf.Max(0, e - TwinState.MinYear);
                for (int y = yi; y < Years; y++) { CumGfa[d, c, y] += b.GfaM2; CumCount[d, y]++; }
                NewCount[d, yi]++;
            }
            Ready = true;
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
        public static float Residents(int district, int year) => Gfa(district, 0, year) / M2PerResident;
        public static float Jobs(int district, int year) { float v = 0; for (int c = 1; c < Cats; c++) v += Gfa(district, c, year) / M2PerJob[c]; return v; }
        /// <summary>Jobs of one use category (1 business … 4 leisure).</summary>
        public static float Jobs1(int cat, int year, int district = -1) => cat <= 0 || cat >= Cats ? 0f : Gfa(district, cat, year) / M2PerJob[cat];
        public static float Readiness(int district, int year)
        {
            if (district < 0) return TotalPlannedGfa > 0 ? GfaAll(-1, year) / TotalPlannedGfa : 0;
            return GfaAll(district, TwinState.MaxYear) > 0 ? GfaAll(district, year) / PlannedGfa(district) : 0;
        }
        static float[] plannedByDistrict = new float[Districts];
        static float PlannedGfa(int district) => plannedByDistrict[district];
        public static int Count(int district, int year) { int yi = YI(year), v = 0; for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += CumCount[d, yi]; return v; }
        public static int NewThisYear(int district, int year) { int yi = YI(year), v = 0; for (int d = 0; d < Districts; d++) if (district < 0 || d == district) v += NewCount[d, yi]; return v; }

        static Color Hex(string h) => ColorUtility.TryParseHtmlString(h, out var c) ? c : Color.magenta;
    }
}
