using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Presentation step «Прогноз: энергия 2034» (Golden). The city grows 2028 → 2034 at dusk; energy runs as light pulses from the
    /// 220/110 kV substation to the 110/10 kV substations and along the 110 kV cables in the streets. The load of ПС «Golden» rises with the
    /// city; in 2034 the evening peak passes its capacity: the lines turn red and flicker, part of the district goes dark. Then the twin's
    /// answer: the forecast was there 8 years ahead, the 2nd stage is built 3 years earlier, the energy runs blue again and the lights return.
    /// Numbers come from the twin data (hv_golden capacity / demand, base scenario).</summary>
    public class TourEnergy
    {
        public const int Y0 = 2028, YBad = 2034, YFixFrom = 2033;
        const float TGrowA = 2.0f, TGrowB = 11.5f, TWarn = 16.5f, TFix = 19.5f;
        readonly TwinData.Facility hv; readonly List<TwinData.Facility> subs = new List<TwinData.Facility>();
        readonly int sc;
        GameObject go; Material cable, trunk; UI.EnergyPanel panel;
        float t; int lastYear = -1, lastStage = -1; bool tinted;
        static readonly int BlackoutId = Shader.PropertyToID("_AlatauBlackout");
        public static readonly Color Blue = new Color(0.35f, 0.78f, 1f), Amber = new Color(1f, 0.70f, 0.20f), Red = new Color(1f, 0.22f, 0.16f), Green = new Color(0.30f, 0.85f, 0.45f);

        public float T => t;
        public bool Fixed => t >= TFix;
        public float YearF => Mathf.Lerp(Y0, YBad, Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(TGrowA, TGrowB, t)));
        public float Cap(int y) => hv == null ? 125f : Fixed && y >= YFixFrom ? Mathf.Max(hv.CapAt(sc, y), hv.CapAt(sc, YFixFrom + 3)) : hv.CapAt(sc, y);
        public float Demand(int y) => hv == null ? 0f : hv.DemandAt(sc, y);

        public TourEnergy()
        {
            sc = (int)TwinState.Scenario;
            hv = TwinData.Facilities.FirstOrDefault(f => f.Id == "hv_golden");
            subs.AddRange(TwinData.Facilities.Where(f => f.Res == "power" && f.District == 1));
            Build();
            var ui = UI.TwinUI.Instance;
            if (ui != null && ui.Scene != null) { panel = new UI.EnergyPanel(this); ui.Scene.Add(panel); }
            TourFx.Instance?.Evening(19.3f, 6f);
        }

        // ------------------------------------------------------------------ geometry: cables along the streets + trunks to the substations
        void Build()
        {
            var sh = Shader.Find("AlatauCity/Glow"); if (sh == null) return;
            go = new GameObject("Tour energy");
            cable = new Material(sh) { name = "Energy cables" }; cable.SetFloat("_Speed", 700f); cable.SetFloat("_Period", 900f);
            trunk = new Material(sh) { name = "Energy trunks" }; trunk.SetFloat("_Speed", 1100f); trunk.SetFloat("_Period", 1400f);
            // 110 kV cables of the Golden substations, each oriented away from its substation so the pulses run outwards
            var V = new List<Vector3>(); var U = new List<Vector2>(); var Y = new List<Vector2>(); var T = new List<int>();
            var seen = new HashSet<int>();
            if (TwinData.Networks.TryGetValue("power", out var segs))
                foreach (var s in segs)
                {
                    if (!seen.Add(s.Edge)) continue;                                  // one street, one cable (no additive pile-up)
                    if (s.Fac < 0 || s.Fac >= TwinData.Facilities.Length) continue;
                    var f = TwinData.Facilities[s.Fac]; if (f.District != 1) continue;
                    int yr = s.Year[sc]; if (yr > 2036) continue;
                    var g = TwinData.Roads[s.Edge].Geom; if (g == null || g.Length < 2) continue;
                    var fp = new Vector2(f.X, f.Z);
                    var pts = (g[0] - fp).sqrMagnitude <= (g[g.Length - 1] - fp).sqrMagnitude ? g : g.Reverse().ToArray();
                    Ribbon(V, U, Y, T, pts, 20f, Vector2.Distance(pts[0], fp), yr);
                }
            Mesh("Energy cables", V, U, Y, T, cable);
            // trunks 220/110 → 110/10: straight bright lines from the big substation (appear with the first stage of each substation)
            V.Clear(); U.Clear(); Y.Clear(); T.Clear();
            if (hv != null)
                foreach (var f in subs)
                {
                    int first = f.Stages != null && f.Stages.Length > sc && f.Stages[sc].Length > 0 ? f.Stages[sc][0] : 9999; if (first > 2036) continue;
                    var a = new Vector2(hv.X, hv.Z); var b = new Vector2(f.X, f.Z); int n = Mathf.Max(2, Mathf.CeilToInt(Vector2.Distance(a, b) / 80f) + 1);
                    var pts = new Vector2[n]; for (int i = 0; i < n; i++) pts[i] = Vector2.Lerp(a, b, i / (n - 1f));
                    Ribbon(V, U, Y, T, pts, 40f, 0f, first);
                }
            Mesh("Energy trunks", V, U, Y, T, trunk);
        }

        static void Ribbon(List<Vector3> V, List<Vector2> U, List<Vector2> Y, List<int> T, Vector2[] src, float w, float acc0, int year)
        {
            // densify so the ribbon follows the relief
            var pts = new List<Vector2> { src[0] };
            for (int i = 1; i < src.Length; i++) { float d = Vector2.Distance(src[i - 1], src[i]); int k = Mathf.Max(1, Mathf.CeilToInt(d / 70f)); for (int j = 1; j <= k; j++) pts.Add(Vector2.Lerp(src[i - 1], src[i], j / (float)k)); }
            float acc = acc0; int v0 = V.Count;
            for (int i = 0; i < pts.Count; i++)
            {
                var a = pts[Mathf.Max(i - 1, 0)]; var b = pts[Mathf.Min(i + 1, pts.Count - 1)]; var d = (b - a).normalized; if (d.sqrMagnitude < 1e-6f) d = Vector2.right;
                var side = new Vector3(-d.y, 0, d.x) * (w * 0.5f);
                if (i > 0) acc += Vector2.Distance(pts[i], pts[i - 1]);
                var c = new Vector3(pts[i].x, CityGround.HeightAt(pts[i].x, pts[i].y) + 5f, pts[i].y);
                V.Add(c - side); U.Add(new Vector2(acc, 0)); Y.Add(new Vector2(year, 0));
                V.Add(c + side); U.Add(new Vector2(acc, 1)); Y.Add(new Vector2(year, 0));
                if (i > 0) { int k = v0 + (i - 1) * 2; T.Add(k); T.Add(k + 2); T.Add(k + 1); T.Add(k + 1); T.Add(k + 2); T.Add(k + 3); }
            }
        }
        void Mesh(string name, List<Vector3> V, List<Vector2> U, List<Vector2> Y, List<int> T, Material mat)
        {
            if (V.Count == 0) return;
            var m = new Mesh { name = name, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
            m.SetVertices(V); m.SetUVs(0, U); m.SetUVs(1, Y); m.SetTriangles(T, 0); m.RecalculateBounds();
            var o = new GameObject(name); o.transform.SetParent(go.transform, false);
            o.AddComponent<MeshFilter>().sharedMesh = m; var mr = o.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat; mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        // ------------------------------------------------------------------ playback
        public void Tick(float dt)
        {
            t += dt;
            float yf = YearF; int y = Mathf.FloorToInt(yf + 0.0001f);
            if (t < TGrowB) { CityTimeline.Growth(yf); if (TwinState.Year != y) TwinState.Year = y; }
            else if (lastYear != YBad) { CityTimeline.StopGrowth(); TwinState.Year = YBad; y = YBad; }
            lastYear = y;

            // load of the 220/110 kV substation (smooth with the fractional year)
            float u = Util(yf);
            Color c = u < 0.85f ? Blue : u <= 1f ? Color.Lerp(Amber, Blue, (1f - u) / 0.15f) : Red;
            bool over = u > 1f && !Fixed;
            float flick = over ? 0.55f + 0.45f * Mathf.PerlinNoise(Time.time * 9f, 0.3f) : 1f;
            float fixA = Mathf.Clamp01((t - TFix) / 1.5f);
            if (Fixed) c = Color.Lerp(c, Blue, fixA);
            foreach (var m in new[] { cable, trunk })
            {
                if (m == null) continue;
                m.SetColor("_Color", c * (m == trunk ? 1.4f : 1.1f)); m.SetFloat("_Year", yf);
                m.SetFloat("_Fade", Mathf.Clamp01(t / 1.2f) * flick);
                m.SetFloat("_Speed", (m == trunk ? 1100f : 700f) * Mathf.Lerp(0.6f, 1.6f, Mathf.Clamp01(u)));
            }
            // outage: the overload trips the transformer, part of the district goes dark (from ~1 s after the peak), back after the fix
            float dark = over ? Mathf.Clamp01((t - TGrowB - 0.8f) / 1.2f) * (0.75f + 0.25f * Mathf.PerlinNoise(Time.time * 5f, 7.1f)) : 0f;
            if (Fixed) dark = Mathf.Max(0f, 1f - fixA) * (lastDark);
            if (dark > 0.001f && !tinted) MarkOutage();
            Shader.SetGlobalFloat(BlackoutId, dark); lastDark = over ? dark : lastDark;

            int stage = t < TGrowB ? 0 : !Fixed ? 1 : 2;
            if (stage != lastStage) { lastStage = stage; Pins(u); }
            panel?.Refresh();
        }
        float lastDark;
        public float Util(float yf)
        {
            int a = Mathf.FloorToInt(yf), b = Mathf.Min(a + 1, 2050); float k = yf - a;
            float d = Mathf.Lerp(Demand(a), Demand(b), k), cp = Cap(a); return cp > 0 ? d / cp : 0f;
        }
        public int OutPeople;

        void MarkOutage()
        {
            tinted = true; if (hv == null) return;
            var c = new Vector2(hv.X, hv.Z); const float R = 2600f; float people = 0;
            TintLayer.Apply(b =>
            {
                if (b.District != "Golden" || b.Year > YBad) return new Color(0, 0, 0, 0);
                if ((new Vector2(b.X, b.Z) - c).sqrMagnitude > R * R) return new Color(0, 0, 0, 0);
                if (b.Kind == "house" || b.Kind.StartsWith("res")) people += b.GfaM2 / 30f;
                return new Color(0, 0, 0, 1);
            });
            OutPeople = Mathf.RoundToInt(people);
        }

        void Pins(float u)
        {
            var pins = new List<MapPins.Pin>();
            if (hv != null)
            {
                string st = lastStage == 1 ? "bad" : lastStage == 2 ? "ok" : "";
                pins.Add(new MapPins.Pin { Id = "hv", Label = "ПС 220 кВ «Golden»", World = new Vector3(hv.X, CityGround.HeightAt(hv.X, hv.Z) + 30f, hv.Z), Fill = lastStage == 1 ? Red : Blue, Status = st, ShowLabel = true, Size = 18f });
            }
            foreach (var f in subs)
            {
                int first = f.Stages != null && f.Stages.Length > sc && f.Stages[sc].Length > 0 ? f.Stages[sc][0] : 9999; if (first > YBad) continue;
                pins.Add(new MapPins.Pin { Id = f.Id, Label = "", World = new Vector3(f.X, CityGround.HeightAt(f.X, f.Z) + 20f, f.Z), Fill = Blue, ShowLabel = false, Size = 10f });
            }
            MapPins.Instance?.Set(pins);
        }

        public void Stop()
        {
            if (go != null) Object.Destroy(go); go = null;
            if (cable != null) Object.Destroy(cable); if (trunk != null) Object.Destroy(trunk);
            Shader.SetGlobalFloat(BlackoutId, 0f); CityTimeline.StopGrowth();
            MapPins.Instance?.Clear();
            panel?.RemoveFromHierarchy(); panel = null;
        }
    }
}
