using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Presentation step «Прогноз: энергия 2034» (Golden), one story played once:
    /// 1) evening falls, the district is lit, energy runs as blue pulses from the 220/110 kV substation along the 110 kV cables;
    /// 2) the city grows 2028 → 2034, the evening peak rises towards the substation's capacity (the lines warm to amber);
    /// 3) 2034: the peak is above the capacity — one decisive outage: the lights go out over the part of Golden it feeds, the lines turn red
    ///    and stall; 4) the consequence in plain words (residents, schools, hospitals in the dark, counted from the buildings);
    /// 5) the twin's answer: QTwin saw it 8 years ahead, in 2026 — the 2nd stage of the substation is built in YFixFrom instead of the plan's year (data: 2035);
    /// 6) the lights come back, the energy runs blue again. No flicker: every change is one smooth transition.
    /// Numbers come from the twin data (hv_golden capacity / demand, base scenario).</summary>
    public class TourEnergy
    {
        public const int Y0 = 2028, YBad = 2034, YFixFrom = 2032;   // the plan of the data: 2nd stage of ПС «Golden» in 2035 (3 years late)
        /// <summary>Story beats (step seconds): growth starts, growth ends (2034), the outage, its consequence, the twin's answer, the fix.</summary>
        public const float TGrowA = 3.5f, TGrowB = 13f, TOut = 13.6f, TCons = 15.2f, TAnswer = 20.5f, TFix = 22.8f;
        /// <summary>Phase of the story: 0 evening, 1 growth, 2 outage, 3 the twin's answer (still dark), 4 fixed (lights back).</summary>
        public int Phase => t < TGrowA ? 0 : t < TOut ? 1 : t < TAnswer ? 2 : t < TFix ? 3 : 4;
        readonly TwinData.Facility hv; readonly List<TwinData.Facility> subs = new List<TwinData.Facility>();
        readonly int sc;
        GameObject go; Material cable, trunk; UI.EnergyPanel panel;
        float t, distC, distT; int lastYear = -1, lastStage = -1; bool tinted, flewIn, flewOut;
        /// <summary>Where ПС 220/110 кВ «Golden» stands (as networks.json hv_golden): the free plot of the plan in the middle of the district's
        /// load (Golden's floor area is centred about 400 m away), 0.9 km from the motorway and 1 km from the LRT; the 220 kV line comes
        /// in from the open land west of the city, the 110 kV side and the gate face the district.</summary>
        public static readonly Vector2 SitePos = new Vector2(SiteX, SiteZ); public const float SiteX = -2045f, SiteZ = -8325f, SiteYaw = 0f;
        Vector2 site, darkC; float lookYaw, darkYaw;
        static readonly int BlackoutId = Shader.PropertyToID("_AlatauBlackout"), ZoneId = Shader.PropertyToID("_AlatauBlackoutZone");
        /// <summary>Radius of the outage round the substation (m): the part of Golden its overloaded transformer feeds.</summary>
        const float OutR = 2600f;
        public static readonly Color Blue = new Color(0.35f, 0.78f, 1f), Amber = new Color(1f, 0.70f, 0.20f), Red = new Color(1f, 0.22f, 0.16f), Green = new Color(0.30f, 0.85f, 0.45f);

        public float T => t;
        public bool Fixed => t >= TFix;
        public float YearF => Mathf.Lerp(Y0, YBad, Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(TGrowA, TGrowB, t)));
        /// <summary>The year the plan of the data builds the substation's second stage (the one the twin moves up to YFixFrom).</summary>
        public int PlannedStage2 => hv != null && hv.Stages != null && hv.Stages.Length > sc && hv.Stages[sc].Length > 1 ? hv.Stages[sc][1] : YFixFrom + 3;
        /// <summary>The capacity in a year; once the twin's answer is taken, the second stage stands from YFixFrom instead of PlannedStage2.</summary>
        public float Cap(int y) => hv == null ? 125f : Fixed && y >= YFixFrom && y < PlannedStage2 ? hv.CapAt(sc, y) + hv.Unit : hv.CapAt(sc, y);
        public float Demand(int y) => hv == null ? 0f : hv.DemandAt(sc, y);

        public TourEnergy()
        {
            sc = (int)TwinState.Scenario;
            hv = TwinData.Facilities.FirstOrDefault(f => f.Id == "hv_golden");
            // the story says the evening peak outgrows the substation in YBad: the data must say the same (gen_twin HV_UNIT, DESIGNED_DELAYS)
            if (hv != null)
            {
                int first = -1; for (int y = Y0; y <= 2050 && first < 0; y++) if (hv.DemandAt(sc, y) > hv.CapAt(sc, y)) first = y;
                if (first != YBad) Debug.LogWarning($"[Alatau] energy story: the data put the first shortage of ПС «Golden» in {first}, the story in {YBad}");
            }
            subs.AddRange(TwinData.Facilities.Where(f => f.Res == "power" && f.District == 1));
            site = SitePos;
            // the camera comes to the substation from outside the district: the yard in front, the district it feeds behind it
            Vector2 dc = Vector2.zero; foreach (var f in subs) dc += new Vector2(f.X, f.Z); dc = subs.Count > 0 ? dc / subs.Count - site : Vector2.up;
            lookYaw = dc.sqrMagnitude > 250000f ? Mathf.Atan2(dc.x, dc.y) * Mathf.Rad2Deg : SiteYaw + 35f;
            // where the outage will be seen: the floor-area centre of the Golden buildings standing in 2034 within its radius
            var db = CityDatabase.Instance; Vector2 acc = Vector2.zero; float wsum = 0f;
            if (db != null)
                foreach (var b in db.Buildings)
                {
                    if (b == null || b.District != "Golden") continue;
                    if (b.Source != "existing_osm" && CityStats.EffectiveYearOf(b.Bid) > YBad) continue;
                    var p = new Vector2(b.X, b.Z); if ((p - site).sqrMagnitude > OutR * OutR) continue;
                    acc += p * b.GfaM2; wsum += b.GfaM2;
                }
            darkC = wsum > 0f ? acc / wsum : site + (Vector2)(Quaternion.Euler(0f, 0f, -lookYaw) * Vector2.up) * 800f;
            var dd = darkC - site; if (dd.sqrMagnitude > 1f) darkYaw = Mathf.Atan2(dd.x, dd.y) * Mathf.Rad2Deg; else darkYaw = lookYaw;
            Build();
            var ui = UI.TwinUI.Instance;
            if (ui != null && ui.Scene != null) { panel = new UI.EnergyPanel(this); ui.Scene.Add(panel); }
            TourFx.Instance?.Evening(19.4f, 3.2f);                 // evening falls in the first seconds, then the hour holds
        }

        // ------------------------------------------------------------------ geometry: cables along the streets + trunks to the substations
        void Build()
        {
            var sh = Shader.Find("AlatauCity/Glow"); if (sh == null) return;
            go = new GameObject("Tour energy");
            var model = SubstationModel.Build(site, SiteYaw, out _); model.transform.SetParent(go.transform, true);
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
            // trunks 220/110 → 110/10: straight bright lines from the big substation's fence (appear with the first stage of each
            // substation), and the ring of light round its yard that shows its load
            V.Clear(); U.Clear(); Y.Clear(); T.Clear();
            if (hv != null)
                foreach (var f in subs)
                {
                    int first = f.Stages != null && f.Stages.Length > sc && f.Stages[sc].Length > 0 ? f.Stages[sc][0] : 9999; if (first > 2036) continue;
                    var b = new Vector2(f.X, f.Z); var a = site + (b - site).normalized * (SubstationModel.HalfZ + 25f); int n = Mathf.Max(2, Mathf.CeilToInt(Vector2.Distance(a, b) / 80f) + 1);
                    var pts = new Vector2[n]; for (int i = 0; i < n; i++) pts[i] = Vector2.Lerp(a, b, i / (n - 1f));
                    Ribbon(V, U, Y, T, pts, 40f, 0f, first);
                }
            {
                var rot = Quaternion.Euler(0f, SiteYaw, 0f); float hx = SubstationModel.HalfX + 9f, hz = SubstationModel.HalfZ + 9f;
                var ring = new List<Vector2>();
                foreach (var c in new[] { new Vector2(-hx, -hz), new Vector2(hx, -hz), new Vector2(hx, hz), new Vector2(-hx, hz), new Vector2(-hx, -hz) })
                { var w = rot * new Vector3(c.x, 0f, c.y); ring.Add(site + new Vector2(w.x, w.z)); }
                Ribbon(V, U, Y, T, ring.ToArray(), 7f, 0f, 2026);
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

            // the story drives the look, not the noise of the load: blue → amber while the peak nears the capacity, red at the outage,
            // blue again after the fix. Each change happens once and smoothly (the old version flickered the lines and the dark area
            // with Perlin noise, which read as the lights going off and on again and again).
            float u = Util(yf); int ph = Phase;
            float outA = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((t - TOut) / 1.1f));          // 0 → 1 at the outage
            float fixA = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((t - TFix) / 2.2f));           // 0 → 1 as the lights come back
            Color c = Color.Lerp(Blue, Amber, Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.80f, 1.0f, u)));
            c = Color.Lerp(c, Red, outA); c = Color.Lerp(c, Blue, fixA);
            float run = Mathf.Lerp(0.6f, 1.6f, Mathf.Clamp01(u));                                  // the energy runs faster with the load
            run = Mathf.Lerp(run, 0.12f, outA * (1f - fixA));                                       // and stalls while the power is off
            if (ph == 4) run = Mathf.Lerp(run, 1.0f, fixA);
            // the glow shader places its pulses at metres − _Time.y × _Speed: changing _Speed directly makes every pulse jump by
            // (time since load × change), which strobed the lines whenever the load changed. The distance the energy has run is
            // integrated here instead and handed over as the speed that gives exactly that distance at the current time.
            distC += 700f * run * dt; distT += 1100f * run * dt;
            float ty = Mathf.Max(Time.timeSinceLevelLoad, 0.5f);
            for (int i = 0; i < 2; i++)
            {
                var m = i == 0 ? cable : trunk; if (m == null) continue;
                m.SetColor("_Color", c * (m == trunk ? 1.4f : 1.1f)); m.SetFloat("_Year", yf);
                m.SetFloat("_Fade", Mathf.Clamp01(t / 1.2f));
                m.SetFloat("_Speed", (m == trunk ? distT : distC) / ty);
            }
            // one decisive outage: the overload trips the transformer, the part of the district it feeds goes dark and stays dark
            // until the twin's fix is in
            float dark = outA * (1f - fixA);
            if (dark > 0.001f && !tinted) MarkOutage();
            Shader.SetGlobalFloat(BlackoutId, dark);
            Shader.SetGlobalVector(ZoneId, new Vector4(site.x, site.y, OutR, dark));            // the street lamps and their light on the roads go out inside it

            // the camera: over the district while it grows, then down to the substation for the outage (the yard in front, the dark
            // district behind it), back up over the district once the 2nd stage is in
            // the outage frame: the substation in the foreground and the district that goes dark behind it, both in view
            if (!flewIn && t >= TGrowB - 1.4f) { flewIn = true; TourFx.Instance?.GlideTo(Vector2.Lerp(site, darkC, 0.55f), 2300f, darkYaw, 33f, 4.2f); }
            if (!flewOut && t >= TFix + 1.4f) { flewOut = true; TourFx.Instance?.GlideTo(Vector2.Lerp(site, darkC, 0.8f), 3400f, darkYaw + 16f, 38f, 7f); }

            int stage = ph < 2 ? 0 : ph < 4 ? 1 : 2;
            if (stage != lastStage) { lastStage = stage; Pins(u); }
            panel?.Refresh();
        }
        /// <summary>Evening peak (MW) at a fractional year: it holds the year's value for most of the year and moves to the next one in
        /// its last quarter, so the figure always belongs to the year shown next to it.</summary>
        public float DemandF(float yf)
        {
            int a = Mathf.FloorToInt(yf), b = Mathf.Min(a + 1, 2050);
            return Mathf.Lerp(Demand(a), Demand(b), Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.75f, 1f, yf - a)));
        }
        public float Util(float yf)
        {
            float cp = Cap(Mathf.FloorToInt(yf)); return cp > 0 ? DemandF(yf) / cp : 0f;
        }
        /// <summary>In the dark area at the outage: residents (floor area / 30 m²), schools and kindergartens, hospitals and clinics.</summary>
        public int OutPeople, OutSchools, OutHealth;

        void MarkOutage()
        {
            tinted = true; if (hv == null) return;
            var c = site; float people = 0; int sch = 0, hos = 0;
            TintLayer.Apply(b =>
            {
                if (b.District != "Golden") return new Color(0, 0, 0, 0);
                if (b.Source != "existing_osm" && CityStats.EffectiveYearOf(b.Bid) > YBad) return new Color(0, 0, 0, 0);
                if ((new Vector2(b.X, b.Z) - c).sqrMagnitude > OutR * OutR) return new Color(0, 0, 0, 0);
                if (b.Kind == "house" || b.Kind.StartsWith("res")) people += b.GfaM2 / CityStats.M2PerResident;
                else if (b.Kind == "education") sch++;
                else if (b.Kind == "health") hos++;
                return new Color(0, 0, 0, 1);
            });
            OutPeople = Mathf.RoundToInt(people); OutSchools = sch; OutHealth = hos;
        }

        void Pins(float u)
        {
            var pins = new List<MapPins.Pin>();
            if (hv != null)
            {
                string st = lastStage == 1 ? "bad" : lastStage == 2 ? "ok" : "";
                pins.Add(new MapPins.Pin { Id = "hv", Label = "ПС 220 кВ «Golden»", World = new Vector3(site.x, CityGround.HeightAt(site.x, site.y) + SubstationModel.TowerH + 30f, site.y), Fill = lastStage == 1 ? Red : Blue, Status = st, ShowLabel = true, Size = 18f });
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
            Shader.SetGlobalFloat(BlackoutId, 0f); Shader.SetGlobalVector(ZoneId, Vector4.zero); CityTimeline.StopGrowth();
            MapPins.Instance?.Clear();
            panel?.RemoveFromHierarchy(); panel = null;
        }
    }
}
