using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>"Construction" view of the 57k buildings, all in the city shader (no GameObjects per building):
    /// per-bid state + progress in a 256×512 RGBA32 lookup (BidTable) (_AlatauStateTex), base height + height in _AlatauGeoTex,
    /// visible-from year in _AlatauYearTex (a building appears when its works start, not when it is finished).
    /// States: 0 context (built / not ours), 1 under construction on plan, 2 behind plan / overdue, 3 paused, 4 completed this year.</summary>
    public static class ConstructionLayer
    {
        public const byte Context = 0, OnPlan = 1, Behind = 2, Paused = 3, Done = 4, Hidden = 5;
        static Rect hiddenArea = Rect.zero;
        /// <summary>Buildings whose centre is inside the rectangle (x, z) are not drawn — e.g. under the detailed BIM model.</summary>
        public static void SetHiddenArea(Rect r) { hiddenArea = r; computedYear = -1; if (Active) Compute(TwinState.Year, (int)TwinState.Scenario); }
        public static bool Active { get; private set; }
        static Texture2D stateTex, geoTex, yearTex; static byte[] state = new byte[0]; static float[] visible = new float[0];
        static readonly int StateId = Shader.PropertyToID("_AlatauStateTex"), GeoId = Shader.PropertyToID("_AlatauGeoTex"), ModeId = Shader.PropertyToID("_AlatauMode"),
            YearTexId = Shader.PropertyToID("_AlatauYearTex"), ScenId = Shader.PropertyToID("_AlatauScenario"), CullId = Shader.PropertyToID("_AlatauCull");

        // ---- statistics of the current year (filled by Compute) ----
        public struct Site { public int Bid; public float Gfa; public int DelayMonths; public float Progress; public int PlanYear, FactYear; }
        public static int Sites, SitesBehind, SitesPaused; public static float GfaInWork, GfaDonePlan, GfaDoneFact;
        public static readonly List<Site> Worst = new List<Site>();
        public static int[] BehindByContractor = new int[0], SitesByContractor = new int[0];
        static int computedYear = -1, computedScenario = -1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Init()
        {
            Shader.SetGlobalFloat(CullId, 2f); Shader.SetGlobalFloat(ModeId, 0f); Active = false; computedYear = -1;
            Application.quitting += () => { Shader.SetGlobalFloat(ModeId, 0f); Shader.SetGlobalFloat(CullId, 2f); Shader.SetGlobalFloat(ScenId, 0f); Shader.SetGlobalFloat("_AlatauYear", 0f); };
        }

        public static void Enable()
        {
            Active = true; computedYear = -1; Ensure();
            Shader.SetGlobalFloat(ModeId, 1f); Shader.SetGlobalFloat(CullId, 0f);
            Compute(TwinState.Year, (int)TwinState.Scenario);
        }
        public static void Disable()
        {
            Active = false; Shader.SetGlobalFloat(ModeId, 0f); Shader.SetGlobalFloat(CullId, 2f);
            TwinScenario.Apply(TwinState.Scenario);         // give the year lookup back to the scenario
            if (TwinState.Scenario == Scenario.Base) Shader.SetGlobalFloat(ScenId, 0f);
        }

        static void Ensure()
        {
            if (stateTex != null) return;
            stateTex = BidTable.New(TextureFormat.RGBA32, "Alatau construction state");
            geoTex = BidTable.New(TextureFormat.RGBAFloat, "Alatau building geo");
            yearTex = BidTable.New(TextureFormat.RFloat, "Alatau visible-from year");
            state = new byte[BidTable.N * 4]; visible = new float[BidTable.N];
            var geo = new float[BidTable.N * 4]; var db = CityDatabase.Instance;
            if (db != null) foreach (var b in db.Buildings) if (b != null && BidTable.Has(b.Bid)) { geo[b.Bid * 4] = b.GroundM; geo[b.Bid * 4 + 1] = b.HeightM; }
            geoTex.SetPixelData(geo, 0); geoTex.Apply(false, false);
        }

        public static int Duration(int bid) => TwinData.Ready && bid < TwinData.BuildYears.Length ? Mathf.Max(1, TwinData.BuildYears[bid]) : 2;
        public static int Delay(int bid) => TwinData.Ready && bid < TwinData.DelayMonths.Length ? TwinData.DelayMonths[bid] : 0;
        public static int ContractorOf(int bid) => TwinData.Ready && bid < TwinData.Contractor.Length ? TwinData.Contractor[bid] : 255;
        public static int VisibleFrom(int bid) => bid >= 0 && bid < visible.Length && Active ? Mathf.RoundToInt(visible[bid]) : CityStats.EffectiveYearOf(bid);
        public static int StateOf(int bid) => bid >= 0 && bid * 4 < state.Length ? state[bid * 4] : 0;
        public static float ProgressOf(int bid) => bid >= 0 && bid * 4 < state.Length ? state[bid * 4 + 1] / 255f : 1f;

        /// <summary>Per-building construction timing under the active scenario: start, plan completion, forecast completion (with delay).</summary>
        public static void Timing(BuildingInfo b, out int start, out int plan, out int fact)
        {
            plan = CityStats.EffectiveYearOf(b.Bid); start = plan - Duration(b.Bid); fact = plan + Mathf.CeilToInt(Delay(b.Bid) / 12f);
        }

        public static void Compute(int year, int scenario)
        {
            if (!Active || (year == computedYear && scenario == computedScenario)) return;
            var db = CityDatabase.Instance; if (db == null) return; Ensure();
            computedYear = year; computedScenario = scenario;
            System.Array.Clear(state, 0, state.Length);
            Sites = SitesBehind = SitesPaused = 0; GfaInWork = GfaDonePlan = GfaDoneFact = 0; Worst.Clear();
            int nc = TwinData.Ready ? TwinData.ContractorNames.Length : 12;
            BehindByContractor = new int[nc]; SitesByContractor = new int[nc];
            var worst = new List<Site>();
            foreach (var b in db.Buildings)
            {
                if (b == null || !BidTable.Has(b.Bid)) continue;
                int i = b.Bid;
                if (b.Source == "existing_osm" || b.Year <= TwinState.MinYear) { visible[i] = b.Year; continue; }
                Timing(b, out int start, out int plan, out int fact);
                if (plan > TwinState.MaxYear) { visible[i] = 9999; continue; }
                int dur = plan - start, delayM = Delay(i); visible[i] = start;
                byte st = Context; float prog = 1f;
                // a site is "in work" in every year from its start up to and including the year it is handed over: a site due this year
                // is still a site of this year, on plan or late. (Before: sites finishing on time this year were left out, so in 2050,
                // the last year of the plan, only the late ones remained and "all 105 of 105" were behind.)
                // Late = still being built although its own planned year has come (its forecast hand-over is later), or earlier
                // when the works already lag the plan's pace; a site handed over this year no longer lags.
                if (year >= start && year <= fact)
                {
                    float real = dur + delayM / 12f;
                    bool handed = year == fact;
                    // progress at the end of the year; delayed works crawl over the longer real duration
                    prog = handed ? 1f : Mathf.Clamp((year + 1 - start) / real, 0.06f, 0.97f);
                    bool behind = !handed && delayM > 0 && (year >= plan || (year + 1 - start) / (float)dur > prog + 0.12f);
                    st = handed ? Done : behind ? Behind : OnPlan;
                    Sites++; GfaInWork += b.GfaM2; if (behind) SitesBehind++;
                    int c = ContractorOf(i); if (c < nc) { SitesByContractor[c]++; if (behind) BehindByContractor[c]++; }
                    if (behind) worst.Add(new Site { Bid = i, Gfa = b.GfaM2, DelayMonths = delayM, Progress = prog, PlanYear = plan, FactYear = fact });
                }
                if (plan == year) GfaDonePlan += b.GfaM2;
                if (fact == year) GfaDoneFact += b.GfaM2;
                if (hiddenArea.width > 0 && hiddenArea.Contains(new Vector2(b.X, b.Z))) st = Hidden;
                state[i * 4] = st; state[i * 4 + 1] = (byte)Mathf.RoundToInt(prog * 255f);
            }
            worst.Sort((x, y) => (y.Gfa * y.DelayMonths).CompareTo(x.Gfa * x.DelayMonths));
            for (int k = 0; k < Mathf.Min(8, worst.Count); k++) Worst.Add(worst[k]);
            stateTex.SetPixelData(state, 0); stateTex.Apply(false, false);
            yearTex.SetPixelData(visible, 0); yearTex.Apply(false, false);
            Shader.SetGlobalTexture(StateId, stateTex); Shader.SetGlobalTexture(GeoId, geoTex);
            Shader.SetGlobalTexture(YearTexId, yearTex); Shader.SetGlobalFloat(ScenId, 1f);
        }
    }
}
