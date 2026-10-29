using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    public enum Scenario { Base = 0, Fast = 1, Slow = 2, InfraFirst = 3 }

    /// <summary>Build-out scenario = a deterministic function year_plan -> year_effective.
    /// The result is pushed to the shader as a 256x256 RFloat lookup (bid -> year), so the 3D city switches instantly.</summary>
    public static class TwinScenario
    {
        public const int AfterHorizon = 2099;
        static Texture2D yearTex;
        static readonly int TexId = Shader.PropertyToID("_AlatauYearTex"), OnId = Shader.PropertyToID("_AlatauScenario");

        public static string Name(Scenario s) => s switch
        {
            Scenario.Fast => Loc.T("sc_fast"), Scenario.Slow => Loc.T("sc_slow"), Scenario.InfraFirst => Loc.T("sc_infra"), _ => Loc.T("sc_base")
        };
        public static string Describe(Scenario s) => s switch
        {
            Scenario.Fast => Loc.T("sc_fast_d"), Scenario.Slow => Loc.T("sc_slow_d"), Scenario.InfraFirst => Loc.T("sc_infra_d"), _ => Loc.T("sc_base_d")
        };

        /// <summary>Effective completion year of a building under a scenario. Existing buildings (year ≤ TwinState.MinYear) never move.</summary>
        public static int EffectiveYear(BuildingInfo b, Scenario s)
        {
            int y = b.Year; if (y <= TwinState.MinYear || b.Source == "existing_osm") return y;
            int dy = y - TwinState.MinYear;
            switch (s)
            {
                case Scenario.Fast: return TwinState.MinYear + Mathf.Max(1, Mathf.RoundToInt(dy * 0.75f));
                case Scenario.Slow: { int e = TwinState.MinYear + Mathf.RoundToInt(dy * 1.3f); return e > TwinState.MaxYear ? AfterHorizon : e; }
                case Scenario.InfraFirst: return b.Use == "housing" && y <= 2036 ? y + 2 : y;   // housing waits for the networks and the LRT
                default: return y;
            }
        }

        public static void Apply(Scenario s)
        {
            var db = CityDatabase.Instance; if (db == null) return;
            Shader.SetGlobalFloat("_AlatauDevK", s == Scenario.Fast ? 0.75f : s == Scenario.Slow ? 1.3f : 1f);   // pace of the ground development (AlatauGround)
            if (s == Scenario.Base) { Shader.SetGlobalFloat(OnId, 0f); return; }
            if (yearTex == null)
            {
                yearTex = new Texture2D(256, 256, TextureFormat.RFloat, false, true) { name = "Alatau scenario years", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            }
            var data = new float[256 * 256];
            foreach (var b in db.Buildings) if (b != null && b.Bid >= 0 && b.Bid < data.Length) data[b.Bid] = EffectiveYear(b, s);
            yearTex.SetPixelData(data, 0); yearTex.Apply(false, false);
            Shader.SetGlobalTexture(TexId, yearTex); Shader.SetGlobalFloat(OnId, 1f);
        }
    }
}
