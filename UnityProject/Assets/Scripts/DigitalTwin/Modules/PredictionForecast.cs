using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>Прогноз 2026–2050 inside the Prediction tab: four scenario sliders (housing pace, migration, industry share, network pace)
    /// form a «custom» scenario that lives only in this panel (TwinState.Scenario is never touched), and two scenarios A and B
    /// (any preset of scenarios.json or the sliders) are compared side by side: the answer (first power deficit A → B), one chart with
    /// two lines and a 2030/2040/2050 table. The presets use the twin data as is; the custom one starts from the base (genplan) scenario
    /// and shifts it, so with the sliders at their start values it equals the base scenario.</summary>
    public static class ForecastModel
    {
        public const int NY = TwinData.NY, Y0 = TwinData.Y0, Custom = 4, Slots = 5;
        public const string ModelId = "model_forecast";
        // jobs and value added per job — the same assumptions as CityEconomy (Economy tab)
        static readonly float[] M2PerJob = { 0f, 90f, 50f, 100f, 120f };
        static readonly float[] VaPerJob = { 0f, 26f, 9f, 30f, 12f };
        const float BaseResidents = 70000f, BaseJobs = 22000f, BaseVa = 6f, ProdGrowth = 0.02f;
        // relative load of a m² by use (housing, business, social, industry, leisure): power W/m² as in TwinModels.Loads, water l/day per m²
        static readonly float[] PowW = { 10f, 12f, 15f, 30f, 12f }, WatW = { 7.7f, 2f, 3f, 6f, 3f };
        static readonly string[] Res = { "power_hv", "water" };

        public static bool Ready;
        /// <summary>Slider state: housing pace %, migration %, industry share of jobs %, network pace %.</summary>
        public static int Housing = 100, Migration = 100, Industry = -1, Nets = 100;
        public static int IndustryBase = 15;

        static float[][][][] gfa;                       // [s][d][cat][yi] cumulative m², yi = year − Y0
        public class Run
        {
            public readonly float[] Residents = new float[NY], Jobs = new float[NY], Grp = new float[NY];   // people, people, bln ₸
            public readonly float[][] D = { new float[NY], new float[NY] }, C = { new float[NY], new float[NY] }, Def = { new float[NY], new float[NY] };  // [power, water][yi]
            public readonly float[][] Load = { new float[NY], new float[NY] };   // demand / capacity, %
            public readonly int[] First = new int[2], Where = new int[2];       // first deficit year (−1 none), district (−1 city)
        }
        public static readonly Run[] Runs = { new Run(), new Run(), new Run(), new Run(), new Run() };
        static readonly float[] h = new float[NY], ind = new float[NY];

        public static void Init()
        {
            Sources.RegisterModel(ModelId, "Прогноз 2026–2050: ползунки сценариев",
                "Стартовые точки — базовый сценарий QTwin по генплану (к 2050 году ≈2 млн жителей вместе с сёлами и ≈1 млн рабочих мест). " +
                "Темп ввода жилья растягивает или сжимает график ввода жилья. Миграция — сколько жителей приходится на введённое жильё (100 % = 30 м² на человека). " +
                "Доля промышленности меняет площадь заводов и складов, а с ней рабочие места, ВРП и нагрузку. Темп ввода сетей сдвигает график подстанций и водозаборов. " +
                "Спрос на электричество и воду меняется пропорционально площади с удельными нагрузками (жильё 10 Вт/м², офисы 12, соцобъекты 15, промышленность 30). " +
                "ВРП — выработка на одно рабочее место по отраслям в ценах 2026 года, +2 % в год, без стройки. Это модель, не прогноз госорганов.");
        }

        public static bool Ensure()
        {
            if (Ready) return true;
            var db = CityDatabase.Instance; if (!TwinData.Ready || !CityStats.Ready || db == null || db.Buildings.Length == 0) return false;
            if (!TwinData.Balances[0].ContainsKey(Res[0]) || !TwinData.Balances[0].ContainsKey(Res[1])) return false;
            gfa = new float[4][][][];
            for (int s = 0; s < 4; s++) { gfa[s] = new float[4][][]; for (int d = 0; d < 4; d++) { gfa[s][d] = new float[5][]; for (int c = 0; c < 5; c++) gfa[s][d][c] = new float[NY]; } }
            foreach (var b in db.Buildings)
            {
                if (b == null) continue; int d = CityStats.DistrictIndex(b.District), c = CityStats.Cat(b.Use); if (d < 0 || c < 0) continue;
                for (int s = 0; s < 4; s++)
                {
                    int e = TwinScenario.EffectiveYear(b, (Scenario)s); if (e > Y0 + NY - 1) continue;
                    gfa[s][d][c][Mathf.Max(0, e - Y0)] += b.GfaM2;
                }
            }
            for (int s = 0; s < 4; s++) for (int d = 0; d < 4; d++) for (int c = 0; c < 5; c++) { var a = gfa[s][d][c]; for (int i = 1; i < NY; i++) a[i] += a[i - 1]; }
            // industry share of all jobs in 2050, base scenario: the start value of its slider
            float ij = 0, all = BaseJobs; for (int d = 0; d < 4; d++) for (int c = 1; c < 5; c++) { float n = gfa[0][d][c][NY - 1] / M2PerJob[c]; all += n; if (c == 3) ij += n; }
            IndustryBase = Mathf.Clamp(Mathf.RoundToInt(100f * ij / Mathf.Max(all, 1f)), 5, 40);
            if (Industry < 0) Industry = IndustryBase;
            Ready = true;
            for (int s = 0; s < 4; s++) Compute(s);
            Compute(Custom);
            return true;
        }

        public static bool AtStart => Housing == 100 && Migration == 100 && Industry == IndustryBase && Nets == 100;
        public static void Reset() { Housing = 100; Migration = 100; Industry = IndustryBase; Nets = 100; if (Ready) Compute(Custom); }

        /// <summary>value of a cumulative curve at a fractional year index (clamped to the table)</summary>
        static float At(float[] a, float fi)
        {
            if (fi <= 0) return a[0]; if (fi >= NY - 1) return a[NY - 1];
            int i = (int)fi; return Mathf.Lerp(a[i], a[i + 1], fi - i);
        }

        /// <summary>Recomputes one slot (0..3 presets, 4 custom). No allocations: all arrays are reused.</summary>
        public static void Compute(int slot)
        {
            if (!Ready) return;
            var r = Runs[slot]; int s = slot == Custom ? 0 : slot;
            float ph = Housing / 100f, mg = Migration / 100f, pn = Nets / 100f;
            float fInd = 1f;
            if (slot == Custom)
            {
                float sb = IndustryBase / 100f, sc = Industry / 100f;
                fInd = (sc / (1f - sc)) / (sb / (1f - sb));
            }
            for (int i = 0; i < NY; i++) { r.Residents[i] = BaseResidents; r.Jobs[i] = BaseJobs; r.Grp[i] = BaseJobs * BaseVa * Mathf.Pow(1f + ProdGrowth, Mathf.Max(0, Y0 + i - 2026)) / 1000f; }
            for (int k = 0; k < 2; k++) { System.Array.Clear(r.D[k], 0, NY); System.Array.Clear(r.C[k], 0, NY); System.Array.Clear(r.Def[k], 0, NY); }

            for (int d = 0; d < 4; d++)
            {
                var g = gfa[s][d];
                for (int i = 0; i < NY; i++)
                {
                    float hi = slot == Custom ? At(g[0], 1 + (i - 1) * ph) * mg : g[0][i];   // housing timeline warped around 2026
                    float ii = g[3][i] * fInd;
                    h[i] = hi; ind[i] = ii;
                    float gr = Mathf.Pow(1f + ProdGrowth, Mathf.Max(0, Y0 + i - 2026));
                    r.Residents[i] += hi / CityStats.M2PerResident;
                    for (int c = 1; c < 5; c++)
                    {
                        float n = (c == 3 ? ii : g[c][i]) / M2PerJob[c];
                        r.Jobs[i] += n; r.Grp[i] += n * VaPerJob[c] * gr / 1000f;
                    }
                }
                for (int k = 0; k < 2; k++)
                {
                    var bal = TwinData.BalanceOf(s, Res[k], d); if (bal == null) continue;
                    AddDistrict(r, k, d, bal, g, slot == Custom, pn, k == 0 ? PowW : WatW);
                }
            }
            for (int k = 0; k < 2; k++)
            {
                var city = TwinData.BalanceOf(s, Res[k], -1);
                bool pooled = TwinData.BalanceOf(s, Res[k], 0) == null;
                if (pooled && city != null)
                {
                    // one network for the whole city (water): the same shift on the city totals
                    float[] W0 = tmpW0, Wc = tmpWc; System.Array.Clear(W0, 0, NY); System.Array.Clear(Wc, 0, NY);
                    var w = k == 0 ? PowW : WatW;
                    for (int d = 0; d < 4; d++)
                    {
                        var g = gfa[0][d];
                        for (int i = 0; i < NY; i++)
                        {
                            float hi = slot == Custom ? At(g[0], 1 + (i - 1) * ph) * mg : g[0][i];
                            for (int c = 0; c < 5; c++) { float base0 = g[c][i] * w[c]; W0[i] += base0; Wc[i] += c == 0 ? hi * w[0] : c == 3 ? g[3][i] * fInd * w[3] : base0; }
                        }
                    }
                    float kk = W0[NY - 1] > 0 ? city.Demand[NY - 1] / W0[NY - 1] : 0f;
                    for (int i = 0; i < NY; i++)
                    {
                        float dem = slot == Custom ? Mathf.Max(0f, city.Demand[i] + kk * (Wc[i] - W0[i])) : city.Demand[i];
                        float cap = slot == Custom ? Step(city.Cap, i, pn) : city.Cap[i];
                        r.D[k][i] = dem; r.C[k][i] = cap; r.Def[k][i] = slot == Custom ? Mathf.Max(0f, dem - cap) : city.Deficit[i];
                    }
                }
                // first deficit: a district first, then the city (as in the Prediction metric view)
                r.First[k] = -1; r.Where[k] = -1;
                for (int i = 1; i < NY && r.First[k] < 0; i++)
                {
                    if (!pooled) for (int d = 0; d < 4; d++) { if (dDef[k][d][i] > 0.5f) { r.First[k] = Y0 + i; r.Where[k] = d; break; } }
                    if (r.First[k] < 0 && r.Def[k][i] > 0.5f) { r.First[k] = Y0 + i; r.Where[k] = -1; }
                }
                for (int i = 0; i < NY; i++) r.Load[k][i] = r.C[k][i] > 0 ? Mathf.Min(160f, 100f * r.D[k][i] / r.C[k][i]) : 0f;
                if (!pooled) for (int d = 0; d < 4; d++) System.Array.Clear(dDef[k][d], 0, NY);
            }
        }
        static readonly float[] tmpW0 = new float[NY], tmpWc = new float[NY];
        static readonly float[][][] dDef = { new[] { new float[NY], new float[NY], new float[NY], new float[NY] }, new[] { new float[NY], new float[NY], new float[NY], new float[NY] } };

        static void AddDistrict(Run r, int k, int d, TwinData.Balance bal, float[][] g, bool custom, float pn, float[] w)
        {
            // custom: demand = base demand + k × (weighted floor area of the sliders − weighted floor area of the base); k calibrated on 2050
            float w0End = 0; for (int c = 0; c < 5; c++) w0End += g[c][NY - 1] * w[c];
            float kk = w0End > 0 ? bal.Demand[NY - 1] / w0End : 0f;
            for (int i = 0; i < NY; i++)
            {
                float dem = bal.Demand[i], cap = bal.Cap[i], def = bal.Deficit[i];
                if (custom)
                {
                    float w0 = 0; for (int c = 0; c < 5; c++) w0 += g[c][i] * w[c];
                    float wc = w0 - g[0][i] * w[0] + h[i] * w[0] - g[3][i] * w[3] + ind[i] * w[3];
                    dem = Mathf.Max(0f, dem + kk * (wc - w0)); cap = Step(bal.Cap, i, pn); def = Mathf.Max(0f, dem - cap);
                }
                r.D[k][i] += dem; r.C[k][i] += cap; r.Def[k][i] += def;
                dDef[k][d][i] = def;
            }
        }

        /// <summary>capacity steps on a warped timeline: pace 120 % brings each stage in sooner</summary>
        static float Step(float[] cap, int i, float pace)
        {
            float fi = 1 + (i - 1) * pace; if (i == 0) return cap[0];
            int j = Mathf.Clamp(Mathf.FloorToInt(fi + 1e-4f), 0, NY - 1); return cap[j];
        }
    }
}
