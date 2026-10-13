using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Macro-economy of the city in year N (demo model of the twin, prices of 2026, ₸): gross regional product by sector,
    /// the construction industry (ПГС: industrial and civil construction), the city budget, investment, wages and labour.
    /// Inputs are the twin's own data: jobs and residents from the floor area (CityStats), construction money from finance.json
    /// (TwinData.Capex*). The coefficients below are the model's assumptions, not official statistics.</summary>
    public static class CityEconomy
    {
        public const float UsdKzt = 500f;                     // display rate, ₸ per $ (fixed in the demo)
        // value added per job, mln ₸ a year in 2026 (Almaty ≈ 23 mln ₸ per employed): business/finance/IT, social, industry, leisure/tourism
        static readonly float[] VaPerJob = { 0f, 26f, 9f, 30f, 12f };
        static readonly float[] Wage = { 0f, 650f, 400f, 480f, 350f };   // average monthly wage, thousand ₸, 2026
        const float ProdGrowth = 0.02f;                       // real productivity and wage growth a year
        const float BaseResidents = 70000f, BaseJobs = 22000f, BaseVa = 6f, BaseWage = 280f;   // the villages and Kapshagay before the new city
        const float ConstrShare = 0.85f;                      // construction and installation works in the money of a building
        const float ConstrVa = 0.40f;                         // value added in the works (ПГС)
        const float ConstrOutPerWorker = 25f;                 // mln ₸ of works per construction worker a year
        const float ConstrWage = 450f;
        const float OpexPerResident = 0.52f;                  // mln ₸ a year: schools, clinics, upkeep, transport, administration
        public static readonly string[] Sectors = { "Торговля, деловые услуги, финансы, IT", "Социальная сфера", "Промышленность и логистика", "Туризм и отдых", "Строительство (ПГС)", "Прочее (сёла, Капшагай)" };
        /// <summary>Sector names inside a sentence (lower case, IT kept).</summary>
        public static readonly string[] SectorsInText = { "торговля, деловые услуги, финансы и IT", "социальная сфера", "промышленность и логистика", "туризм и отдых", "строительство (ПГС)", "сёла и Капшагай" };
        public static readonly Color[] SectorColors = { new Color(0.94f, 0.42f, 0.42f), new Color(0.64f, 0.44f, 0.97f), new Color(0.55f, 0.60f, 0.66f), new Color(0.18f, 0.83f, 0.75f), new Color(0.98f, 0.62f, 0.20f), new Color(0.45f, 0.45f, 0.45f) };
        public static readonly string[] Revenue = { "ИПН", "Социальный налог", "КПН (с льготами спецрежима)", "Налог на имущество и землю", "Прочие поступления" };
        public static readonly string[] Spend = { "Образование", "Здравоохранение", "ЖКХ и благоустройство", "Транспорт и ЛРТ", "Соцзащита", "Управление" };
        static readonly float[] SpendShare = { 0.38f, 0.12f, 0.22f, 0.14f, 0.08f, 0.06f };

        public class Year
        {
            public int Y;
            public float Residents, Jobs, ConstrJobs;          // people
            public float[] Grp = new float[6];                 // bln ₸ by sector (Sectors)
            public float GrpTotal, GrpPerCapitaUsd, GrpGrowth;  // bln ₸, $, % real y/y
            public float Capex, CapexPrivate, CapexBudget;      // bln ₸: all construction money of the year, private + PPP, budget
            public float ConstrOutput, HousingM2;              // bln ₸ of works (ПГС), m² of housing handed over in the year
            public float Payroll, AvgWage;                     // bln ₸ a year, thousand ₸ a month
            public float[] Rev = new float[5];                 // bln ₸ (Revenue)
            public float RevOwn, Transfers, ToRepublic, Opex, BudgetCapex, Balance;   // bln ₸: Balance = own − upkeep − public construction
            public float[] Exp = new float[6];                 // bln ₸ (Spend): current spending
            public float LabourForce, Commuters;               // people; commuters = jobs the residents cannot fill (come from Almaty / Konaev)
            public float TaxBurden;                            // tax revenue / GRP
            public float IndustryOutputUsdM, ExportUsdM;       // the large plants (LandmarkCapacity), $ mln a year
        }

        static Year[] cache; static int cacheS = -1, cacheLm = -1; static float cacheKey;
        static float Key => CityStats.Ready ? CityStats.GfaAll(-1, TwinState.MaxYear) + CityStats.TotalPlannedGfa * 0.001f : 0f;

        /// <summary>The economy of the city in a year of the active scenario.</summary>
        public static Year Of(int y)
        {
            Ensure();
            return cache[Mathf.Clamp(y - TwinState.MinYear, 0, cache.Length - 1)];
        }
        public static bool Ready => CityStats.Ready && TwinData.Ready;

        static void Ensure()
        {
            int s = (int)TwinState.Scenario; float k = Key; var ls = Landmarks.LandmarkSystem.Instance; int lm = ls != null ? ls.Items.Count : 0;
            if (cache != null && cacheS == s && cacheLm == lm && Mathf.Approximately(cacheKey, k)) return;
            cacheS = s; cacheKey = k; cacheLm = lm; cache = new Year[CityStats.Years];
            for (int i = 0; i < cache.Length; i++) cache[i] = Compute(TwinState.MinYear + i, s);
            for (int i = 1; i < cache.Length; i++) cache[i].GrpGrowth = cache[i - 1].GrpTotal > 1f ? 100f * (cache[i].GrpTotal / cache[i - 1].GrpTotal - 1f) : 0f;
        }

        static Year Compute(int y, int s)
        {
            var e = new Year { Y = y };
            float g = Mathf.Pow(1f + ProdGrowth, Mathf.Max(0, y - 2026));
            bool cs = CityStats.Ready, td = TwinData.Ready;
            int yi = td ? TwinData.YI(y) : 0;

            // construction money of the year (bln ₸): buildings (fact) + infrastructure; who pays
            float bld = 0f, infra = 0f, budget = 0f, priv = 0f;
            if (td)
            {
                for (int d = 0; d < 4; d++)
                {
                    bld += TwinData.CapexFact[s][d][yi];
                    var src = TwinData.CapexSources[s][d];
                    budget += src[0][yi]; priv += src[1][yi] + src[2][yi] * 0.5f; budget += src[3][yi] * 0.5f + src[2][yi] * 0.5f;   // quasi-state and half of PPP count as public money
                }
                foreach (var kv in TwinData.CapexInfra[s]) infra += kv.Value[yi];
            }
            e.Capex = bld + infra; e.CapexBudget = budget + infra * 0.6f; e.CapexPrivate = Mathf.Max(0f, e.Capex - e.CapexBudget);
            e.ConstrOutput = e.Capex * ConstrShare;
            e.ConstrJobs = e.ConstrOutput * 1000f / ConstrOutPerWorker;
            e.HousingM2 = cs ? CityStats.Gfa(-1, 0, y) - (y > TwinState.MinYear ? CityStats.Gfa(-1, 0, y - 1) : 0f) : 0f;

            // jobs and value added by sector
            float payroll = 0f, jobs = 0f;
            for (int c = 1; c < 5; c++)
            {
                float n = cs ? CityStats.Jobs1(c, y) : 0f; jobs += n;
                e.Grp[c - 1] = n * VaPerJob[c] * g / 1000f;                 // bln ₸
                payroll += n * Wage[c] * g * 12f / 1e6f;                    // bln ₸
            }
            e.Grp[4] = e.ConstrOutput * ConstrVa;
            e.Grp[5] = BaseJobs * BaseVa * g / 1000f;
            payroll += e.ConstrJobs * ConstrWage * g * 12f / 1e6f + BaseJobs * BaseWage * g * 12f / 1e6f;
            float total = 0f; foreach (var v in e.Grp) total += v; e.GrpTotal = total;
            e.Residents = BaseResidents + (cs ? CityStats.Residents(-1, y) : 0f);
            e.Jobs = jobs + BaseJobs + e.ConstrJobs;
            e.GrpPerCapitaUsd = e.Residents > 0 ? total * 1e9f / e.Residents / UsdKzt : 0f;
            e.Payroll = payroll; e.AvgWage = e.Jobs > 0 ? payroll * 1e6f / e.Jobs / 12f : 0f;
            e.LabourForce = e.Residents * 0.52f; e.Commuters = Mathf.Max(0f, e.Jobs - e.LabourForce * 0.94f);

            // the city budget: own taxes (Alatau's special regime halves the corporate tax until 2035), transfers for its infrastructure
            float profit = (total - payroll) * 0.35f;
            e.Rev[0] = payroll * 0.10f;
            e.Rev[1] = payroll * 0.095f * 0.9f;
            e.Rev[2] = Mathf.Max(0f, profit) * 0.20f * (y < 2035 ? 0.5f : 1f) * 0.5f;    // half of CIT stays in the city
            e.Rev[3] = StockValue(y, s) * 0.006f;
            e.Rev[4] = total * 0.004f;
            float own = 0f; foreach (var v in e.Rev) own += v; e.RevOwn = own;
            e.Opex = e.Residents * OpexPerResident * g / 1000f;
            for (int i = 0; i < 6; i++) e.Exp[i] = e.Opex * SpendShare[i];
            e.BudgetCapex = e.CapexBudget;
            // own revenues against all spending (upkeep + the public part of the construction): a gap is covered by targeted transfers
            // from the republic, a surplus goes to the republican budget
            e.Balance = own - e.Opex - e.BudgetCapex;
            e.Transfers = Mathf.Max(0f, -e.Balance); e.ToRepublic = Mathf.Max(0f, e.Balance);
            e.TaxBurden = total > 0 ? (payroll * 0.195f + Mathf.Max(0f, profit) * 0.20f + e.Rev[3] + e.Rev[4]) / total : 0f;

            // the large plants
            Landmarks.LandmarkCapacity.Totals(y, out e.IndustryOutputUsdM, out e.ExportUsdM);
            return e;
        }

        /// <summary>Value of the buildings standing in the year (bln ₸): the construction money spent so far.</summary>
        static float StockValue(int y, int s)
        {
            if (!TwinData.Ready) return 0f;
            float v = 0f; int yi = TwinData.YI(y);
            for (int i = 0; i <= yi; i++) for (int d = 0; d < 4; d++) v += TwinData.CapexFact[s][d][i];
            return v;
        }

        /// <summary>The first year own revenues cover all the city's spending, upkeep and its part of the construction (no transfers needed).</summary>
        public static int SelfSufficientYear()
        {
            Ensure();
            foreach (var e in cache) if (e.Y >= 2027 && e.RevOwn >= e.Opex + e.BudgetCapex) return e.Y;
            return -1;
        }

        public static string Trln(float bln) => bln >= 1000f ? Loc.N1(bln / 1000f) + " трлн ₸" : Loc.N0(bln) + " млрд ₸";
        public static string Usd(float bln) { float b = bln / UsdKzt; return b >= 1f ? "$" + Loc.N1(b) + " млрд" : "$" + Loc.N0(b * 1000f) + " млн"; }
    }
}
