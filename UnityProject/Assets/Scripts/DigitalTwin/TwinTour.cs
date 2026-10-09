using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Modules;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Presentation for investors, zone by zone: the city and its growth, then Gate, Golden, Growing and Green — each district
    /// is framed and highlighted on the map, its real projects are shown close up (fly-in, orbit, passport) and the twin's functions are
    /// shown where they matter for that district (construction, LRT, forecast, situational centre, networks, risks). The functions keep
    /// working on the whole map; the tour only picks the context. Space — pause, ← → — steps, Esc — exit.</summary>
    public class TwinTour : MonoBehaviour
    {
        public static TwinTour Instance;
        public static bool Running => Instance != null && Instance.running;
        /// <summary>Kept for the landmark orbit: the tour never freezes the camera, the orbit runs during object steps.</summary>
        public static bool HoldCamera => false;
        /// <summary>Zone of the current step: -1 = whole city, 0..3 = district (its labels are shown).</summary>
        public static int Zone => Running ? Instance.steps[Instance.idx].Zone : -2;

        class Step
        {
            public int Seg, Zone = -1; public string Module = "overview"; public int Year = 2050; public Scenario Sc = Scenario.Base; public float Dur = 20f;
            public Action Enter; public Func<string> Title; public (float, Action)[] Shots;
            public bool Grow; public int AnimFrom, AnimTo;   // year animation within the step (growth / a landmark rising)
            public bool Gfa;                                  // the «growth by use» chart is shown only in the steps about the whole city's growth
        }
        readonly List<Step> steps = new List<Step>();
        bool running, paused; int idx; float t;
        VisualElement box, bar, zoneDot, segs; Label lZone, lStep, lStepName; Button bPause; VisualElement host;

        static readonly string[] SegTitle = { "ALATAU CITY · ГОРОД ЦЕЛИКОМ", "GATE · ворота и деловой центр", "GOLDEN · наука, образование, медицина", "GROWING · промышленность и логистика", "GREEN · туризм на Капшагае", "ЛРТ · Алматы — Алатау — Конаев", "ЦИФРОВОЙ ДВОЙНИК · ВОЗМОЖНОСТИ", "ИТОГ" };
        static readonly string[] SegName = { "Город", "Gate", "Golden", "Growing", "Green", "ЛРТ", "Двойник", "Итог" };
        static readonly Color Brand = new Color(0.88f, 0.15f, 0.11f), LrtC = new Color(0.70f, 0.52f, 0.89f);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Twin tour").AddComponent<TwinTour>(); }
        void Awake() { Instance = this; }

        public static void Toggle() { if (Instance == null) return; if (Instance.running) Instance.Stop(); else Instance.Begin(); }

        // ------------------------------------------------------------------ helpers
        static MapCamera Cam => Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
        static LandmarkSystem LS => LandmarkSystem.Instance;
        static void Overview() { LS?.Select(null, false); var c = Cam; if (c != null) c.FlyTo(c.overview); TwinState.SetDistrict(-1); }
        static void Fly(Vector2 p, float dist, float pitch = 46f, float? yaw = null)
        {
            var c = Cam; if (c != null) c.FlyTo(new MapCamera.View { name = "tour", target = new Vector3(p.x, CityGround.HeightAt(p.x, p.y), p.y), distance = dist, yaw = yaw ?? c.yaw, pitch = pitch });
        }
        /// <summary>The whole district in the frame (from the extent of its buildings), highlighted on the ground.</summary>
        static void FrameZone(int d)
        {
            LS?.Select(null, false); TwinState.SetDistrict(d);
            var db = CityDatabase.Instance; if (db == null) return;
            var xs = new List<float>(); var zs = new List<float>();
            foreach (var b in db.Buildings) if (b != null && b.District == CityStats.DistrictIds[d]) { xs.Add(b.X); zs.Add(b.Z); }
            if (xs.Count == 0) return;
            xs.Sort(); zs.Sort();
            float x0 = xs[xs.Count * 4 / 100], x1 = xs[xs.Count * 96 / 100], z0 = zs[zs.Count * 4 / 100], z1 = zs[zs.Count * 96 / 100];
            float ext = Mathf.Max(x1 - x0, z1 - z0);
            Fly(new Vector2((x0 + x1) * 0.5f, (z0 + z1) * 0.5f - ext * 0.12f), Mathf.Clamp(ext * 1.35f, 9000f, 45000f), 52f, 0f);
        }
        /// <summary>A district in 2050: highlighted on the ground, the camera glides low along it (buildings read in 3D, not a plan).</summary>
        static void ZoneGlide(int d, float dur) { LS?.Select(null, false); TwinState.SetDistrict(d); TourFx.Instance?.GlideDistrict(d, dur, only: b => b.Source != "existing_osm" && b.Kind != "house" && b.Kind != "solar"); }   // over the new city, not over the old villages
        static void Spot(int d, string name, Color c, Func<BuildingInfo, bool> pred) => TourFx.Instance?.Spot(d, new TourFx.Cat { Name = name, Col = c, Is = pred });
        static void Object(string id) { var l = LS?.Get(id); if (l != null) LS.Select(l); }
        static void Station(int phase)
        {
            var lrt = LrtLayer.Instance; var l = LS?.Get("lrt"); if (lrt == null || l == null) return;
            var st = lrt.Stations.Where(s => s.Phase == phase).OrderBy(s => s.P.z).ToList(); if (st.Count == 0) return;
            var s0 = st[st.Count / 2]; LS.FlyToPoint(l, s0.P, 760f);
        }
        static T Active<T>() where T : class => TwinUI.Instance != null ? TwinUI.Instance.Active as T : null;
        static string Money(float mln) => mln >= 1000 ? Loc.N1(mln / 1000f) + " млрд ₸" : Loc.N0(mln) + " млн ₸";
        static float Res(int y) { float r = 0; for (int d = 0; d < 4; d++) r += CityStats.Residents(d, y); return r; }
        static string K(float v) => Loc.N0(v / 1000f) + " тыс.";
        static string[] ObjectsOf(int d) => LS == null ? new string[0] : LS.Items.Where(l => l.District == d).Select(l => l.Name + " — " + LandmarkCatalog.StatusOf(l).ToLower()).ToArray();
        static int LrtYear(int p) { int s = (int)TwinState.Scenario; return TwinData.LrtPhaseYear[s] != null && p < TwinData.LrtPhaseYear[s].Length ? TwinData.LrtPhaseYear[s][p] : 2031; }
        static string Fact(string id, string key) { var l = LS?.Get(id); if (l == null) return ""; foreach (var (k, v) in l.Facts) if (k == key) return v; return ""; }

        /// <summary>A camera move or an action at a moment of the step (seconds from its start).</summary>
        static (float, Action) At(float t, Action a) => (t, a);

        void Build()
        {
            steps.Clear();
            // ================= the city (segment 0)
            steps.Add(new Step { Seg = 0, Zone = -1, Year = 2025, Dur = 14, Enter = Overview, Title = () => "Alatau City сегодня" });
            steps.Add(new Step { Seg = 0, Zone = -1, Year = 2025, Dur = 24, Grow = true, Gfa = true, Enter = Overview, Title = () => "Город растёт: 2025 → 2050" });

            // ================= Gate: business centre (segment 1)
            steps.Add(new Step { Seg = 1, Zone = 0, Year = 2050, Dur = 14, Enter = () => ZoneGlide(0, 16f), Title = () => "Район Gate в 2050 году" });
            steps.Add(new Step { Seg = 1, Zone = 0, Module = "objects", Year = 2030, Dur = 20, Enter = () => Object("iconic"), Title = () => "Iconic Complex · 272 м" });
            steps.Add(new Step { Seg = 1, Zone = 0, Module = "construction", Year = 2026, Dur = 24, AnimFrom = 2026, AnimTo = 2030, Enter = () => { TwinState.SetDistrict(0); Object("iconic"); }, Title = () => "Стройка Iconic: 2026 → 2030" });
            steps.Add(new Step { Seg = 1, Zone = 0, Module = "objects", Year = 2030, Dur = 18, Enter = () => Object("lotte_l7"), Title = () => "L7 by Lotte · PepsiCo · Griffin Logopark",
                Shots = new[] { At(6f, () => Object("pepsico")), At(12f, () => Object("griffin")) } });

            // ================= Golden: science, education, health (segment 2)
            steps.Add(new Step { Seg = 2, Zone = 1, Year = 2050, Dur = 16, Enter = () => ZoneGlide(1, 16f), Title = () => "Район Golden в 2050 году" });
            steps.Add(new Step { Seg = 2, Zone = 1, Year = 2050, Dur = 20, Enter = () => { TwinState.SetDistrict(1); TourFx.Instance?.GlideDistrict(1, 20f, 0.28f, -0.22f, 5200f, 4300f, 38f, -22f); },
                Title = () => "Университеты, школы, больницы",
                Shots = new[] {
                    At(0.6f, () => Spot(1, "Вузы и кампусы", new Color(0.62f, 0.48f, 1f), b => b.Kind == "education" && b.GfaM2 >= 12000f)),
                    At(5f, () => Spot(1, "Школы и сады", new Color(0.30f, 0.66f, 1f), b => b.Kind == "education" && b.GfaM2 < 12000f)),
                    At(9.5f, () => Spot(1, "Больницы и клиники", new Color(1f, 0.38f, 0.56f), b => b.Kind == "health")),
                    At(14f, () => Spot(1, "Наука и технопарки", new Color(0.24f, 0.86f, 0.74f), b => b.Kind == "public")) } });

            // ================= Growing: industry and logistics (segment 3)
            steps.Add(new Step { Seg = 3, Zone = 2, Year = 2050, Dur = 14, Enter = () => ZoneGlide(2, 16f), Title = () => "Район Growing в 2050 году" });
            steps.Add(new Step { Seg = 3, Zone = 2, Year = 2050, Dur = 20, Enter = () => { TwinState.SetDistrict(2); TourFx.Instance?.GlideDistrict(2, 20f, -0.35f, 0.35f, 4200f, 3000f, 32f, 24f, b => b.Kind == "industry" || b.Kind == "utility"); },
                Title = () => "Долина заводов",
                Shots = new[] {
                    At(0.6f, () => Spot(2, "Заводы", new Color(1f, 0.62f, 0.22f), b => b.Kind == "industry")),
                    At(6f, () => Spot(2, "Энергетика и сети", new Color(1f, 0.86f, 0.25f), b => b.Kind == "utility" || b.Kind == "solar")) } });
            steps.Add(new Step { Seg = 3, Zone = 2, Year = 2050, Dur = 24, Enter = () => { LS?.Select(null, false); var c = Cam; if (c != null) c.FlyTo(c.overview); TourFx.Instance?.ShowSilkRoad(); }, Title = () => "Шёлковый путь через Алатау" });
            steps.Add(new Step { Seg = 3, Zone = 2, Module = "objects", Year = 2050, Dur = 22, Enter = () => Object("airport"), Title = () => "Новый аэропорт · концепция" });

            // ================= Green: tourism on Kapshagay (segment 4)
            steps.Add(new Step { Seg = 4, Zone = 3, Year = 2050, Dur = 16, Title = () => "Район Green в 2050 году",
                Enter = () => { ZoneGlide(3, 16f); TourFx.Instance?.Callout("Green District · туризм", new[] { ("4 млн", "туристов в год к 2050", new Color(1f, 0.82f, 0.45f)), ("31 730 га", "курортов, пляжей и набережных", new Color(0.55f, 0.85f, 0.65f)) }, null); } });
            steps.Add(new Step { Seg = 4, Zone = 3, Year = 2050, Dur = 26, Title = () => "Паводок на Капшагае: модель и решение",
                Enter = () => { TourFx.Instance?.GlideDistrict(3, 26f, -0.10f, 0.22f, 3400f, 2600f, 34f, 16f, b => b.GroundM < 479f); TourFx.Instance?.Flood(new Rect(-1500f, 11000f, 19500f, 17000f), 3, 475.0f, 3.2f, 10f, 16f); } });

            // ================= LRT (segment 5)
            steps.Add(new Step { Seg = 5, Zone = -1, Year = 2050, Dur = 20, Title = () => "ЛРТ соединит Алматы и Конаев",
                Enter = () => { LS?.Select(null, false); LrtLayer.Showcase = true; TourFx.Instance?.GlideLine(new Vector2(-3000f, -22000f), new Vector2(0f, 6000f), 20f, 16000f, 15000f, 6f, -4f, 50f, 46f);
                                 TourFx.Instance?.Callout("ЛРТ Алматы — Алатау — Конаев", new[] { (Loc.N1(TwinData.LrtPhaseKm.Sum()) + " км", "лёгкого метро на эстакаде", new Color(0.78f, 0.62f, 1f)), ("41", "станция", new Color(0.78f, 0.62f, 1f)), ("к 2050", "линия соединит два города", new Color(1f, 1f, 1f)) }, null); } });

            // ================= what the twin does (segment 6)
            steps.Add(new Step { Seg = 6, Zone = -1, Module = "construction", Year = 2027, AnimFrom = 2027, AnimTo = 2032, Dur = 24, Enter = () => { LS?.Select(null, false); TwinState.SetDistrict(-1); ConstructionModule.TourOverlays = true; ConstructionModule.ApplyTourLayers(); TourFx.Instance?.ConstructionWatch(); TourFx.Instance?.GlideLine(new Vector2(-3200f, -23500f), new Vector2(-1800f, -9000f), 24f, 9500f, 8500f, 8f, -6f, 52f, 46f); }, Title = () => "Контроль стройки: план против факта" });
            steps.Add(new Step { Seg = 6, Zone = -1, Module = "situation", Year = 2036, Dur = 26, Enter = () => TourFx.Instance?.ShowSituation("dtp"), Title = () => "Ситуационный центр" });
            steps.Add(new Step { Seg = 6, Zone = 1, Module = "overview", Year = TourEnergy.Y0, Dur = 28, Enter = () => { LS?.Select(null, false); TourFx.Instance?.ShowEnergy(); }, Title = () => "Прогноз: энергия 2034" });
            steps.Add(new Step { Seg = 6, Zone = -1, Module = "ai", Year = 2034, Dur = 26, Enter = () => { LS?.Select(null, false); TwinState.SetDistrict(-1); TourFx.Instance?.ShowAi(); }, Title = () => "ИИ-ассистент" });

            // ================= finale (segment 7)
            steps.Add(new Step { Seg = 7, Zone = -1, Year = 2050, Dur = 18, Gfa = true, Enter = Overview, Title = () => "Alatau City 2050 · qTwin" });
        }

        // ------------------------------------------------------------------ control
        void Begin()
        {
            if (!TwinData.Ready || !CityStats.Ready) { Debug.LogWarning("[Alatau] tour: data not ready"); return; }
            Build(); running = true; paused = false; Go(0);
        }
        public void Stop()
        {
            running = false; CityTimeline.StopGrowth(); if (box != null) box.style.display = DisplayStyle.None; host?.RemoveFromClassList("tour-on"); TwinUI.Instance?.Middle?.RemoveFromClassList("tour-on"); TwinUI.Instance?.Middle?.RemoveFromClassList("tour-gfa"); ReleaseCard();
            if (TwinState.Scenario != Scenario.Base) TwinState.Scenario = Scenario.Base;
            TwinState.SetDistrict(-1);
            TourFx.Instance?.Reset(); LrtLayer.Showcase = false;
            TwinState.SetModule("overview");             // panels built for the presentation (one district only) are rebuilt for normal work
        }
        void Go(int i)
        {
            idx = Mathf.Clamp(i, 0, steps.Count - 1); t = 0; var s = steps[idx]; CityTimeline.StopGrowth();
            TwinState.Playing = false; ConstructionModule.TourOverlays = false; LrtLayer.Showcase = false; TourFx.Instance?.Reset(); if (TwinState.Selected != null) TwinState.SetSelected(null);
            if (LS != null && LS.Selected != null) LS.Select(null, false);    // each step opens its own passport, if any
            if (TwinState.Scenario != s.Sc) TwinState.Scenario = s.Sc;
            TwinState.SetModule(s.Module);
            TwinState.Year = s.AnimTo > 0 ? s.AnimFrom : s.Year;
            if (s.Zone < 0 && TwinState.District >= 0 && s.Module != "ai") TwinState.SetDistrict(-1);
            if (s.Zone >= 0) TwinState.SetDistrict(s.Zone);              // the step's district is lit on the ground and named in the header
            TwinUI.Instance?.Middle?.EnableInClassList("tour-gfa", s.Gfa);
            try { s.Enter?.Invoke(); } catch (Exception e) { Debug.LogWarning("[Alatau] tour step " + idx + ": " + e.Message); }
            Caption();
        }
        void Caption()
        {
            Ensure(); if (box == null) return; var s = steps[idx];
            int seg = s.Seg;
            lZone.text = SegTitle[seg].ToUpperInvariant();
            zoneDot.style.backgroundColor = s.Zone >= 0 ? CityStats.DistrictColors[s.Zone] : seg == 5 ? LrtC : Brand;
            lStep.text = $"{idx + 1} / {steps.Count}";
            int k = 0; foreach (var c in segs.Children()) { c.EnableInClassList("on", k == seg); c.EnableInClassList("done", k < seg); k++; }
            try { lStepName.text = s.Title != null ? s.Title() : ""; } catch { lStepName.text = ""; }
            bPause.text = paused ? "Продолжить" : "Пауза";
            box.style.display = DisplayStyle.Flex; host?.AddToClassList("tour-on"); TwinUI.Instance?.Middle?.AddToClassList("tour-on");
        }

        void Ensure()
        {
            var ui = TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            if (box != null && host == ui.Scene && box.parent == host) return;
            host = ui.Scene;
            box = new VisualElement(); box.AddToClassList("tour"); box.AddToClassList("tour2");
            var top = new VisualElement(); top.AddToClassList("tour-top"); box.Add(top);
            zoneDot = new VisualElement { pickingMode = PickingMode.Ignore }; zoneDot.AddToClassList("tour-zdot"); top.Add(zoneDot);
            lZone = new Label { pickingMode = PickingMode.Ignore }; lZone.AddToClassList("tour-zone"); top.Add(lZone);
            var sp0 = new VisualElement { pickingMode = PickingMode.Ignore }; sp0.style.flexGrow = 1; top.Add(sp0);
            lStep = new Label { pickingMode = PickingMode.Ignore }; lStep.AddToClassList("tour-count"); top.Add(lStep);
            segs = new VisualElement(); segs.AddToClassList("tour-segs"); box.Add(segs);
            foreach (var n in SegName) { var sg = new VisualElement(); sg.AddToClassList("tour-seg"); sg.Add(new Label(n) { pickingMode = PickingMode.Ignore }); segs.Add(sg); }
            lStepName = new Label { pickingMode = PickingMode.Ignore }; lStepName.AddToClassList("tour-stepname"); box.Add(lStepName);
            var track = new VisualElement(); track.AddToClassList("tour-track"); box.Add(track);
            bar = new VisualElement(); bar.AddToClassList("tour-bar"); track.Add(bar);
            var row = new VisualElement(); row.AddToClassList("row"); row.style.marginTop = 10; box.Add(row);
            row.Add(Widgets.Btn("← Назад", () => Go(idx - 1), "small", "ghost"));
            bPause = Widgets.Btn("Пауза", () => { paused = !paused; Caption(); }, "small"); row.Add(bPause);
            row.Add(Widgets.Btn("Далее →", () => Next(), "small", "ghost"));
            var sp = new VisualElement(); sp.style.flexGrow = 1; row.Add(sp);
            row.Add(Widgets.Btn("Закончить", Stop, "small", "ghost"));
            // jump to a zone
            var zr = new VisualElement(); zr.AddToClassList("row"); zr.AddToClassList("tour-zones"); box.Add(zr);
            var zl = new Label("Перейти к зоне:") { pickingMode = PickingMode.Ignore }; zl.AddToClassList("note"); zl.style.marginRight = 4; zr.Add(zl);
            for (int z = 0; z < 4; z++) { int zz = z; var zb = Widgets.Btn(CityStats.DistrictIds[z], () => JumpZone(zz), "small", "ghost"); zb.style.color = CityStats.DistrictColors[z]; zr.Add(zb); }
            var hint = new Label("пробел — пауза · ← → — шаги · Esc — выход"); hint.AddToClassList("note"); hint.style.marginTop = 6; box.Add(hint);
            ui.BlockWhileHovered(box);
            host.Add(box);
        }
        /// <summary>The passport (top right) ends above the caption (bottom right).</summary>
        void FitCard()
        {
            var mid = TwinUI.Instance?.Middle; if (mid == null || box == null) return;
            var card = mid.Q(className: "card"); if (card == null) return;
            float h = box.layout.height, H = mid.layout.height; if (float.IsNaN(h) || h < 10f || float.IsNaN(H) || H < 100f) return;
            card.style.maxHeight = Mathf.Max(160f, H - h - 40f);
        }
        void ReleaseCard() { var card = TwinUI.Instance?.Middle?.Q(className: "card"); if (card != null) card.style.maxHeight = StyleKeyword.Null; }
        void JumpZone(int z) { int i = steps.FindIndex(s => s.Zone == z); if (i >= 0) Go(i); }
        void Next() { if (idx >= steps.Count - 1) Stop(); else Go(idx + 1); }

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.F5) && !MapCamera.Typing) { Toggle(); return; }
            if (!running) return;
            if (Input.GetKeyDown(KeyCode.Escape)) { Stop(); return; }
            if (Input.GetKeyDown(KeyCode.Space)) { paused = !paused; Caption(); }
            if (Input.GetKeyDown(KeyCode.RightArrow)) { Next(); return; }
            if (Input.GetKeyDown(KeyCode.LeftArrow)) { Go(idx - 1); return; }
            // presenter shortcut: Shift + 1..8 jumps to the start of a part (Город, Gate, Golden, Growing, Green, ЛРТ, Двойник, Итог)
            if (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift))
                for (int d = 0; d < 8; d++) if (Input.GetKeyDown(KeyCode.Alpha1 + d)) { int j = steps.FindIndex(x => x.Seg == d); if (j >= 0) { Go(j); return; } }
            if (box == null || box.parent == null) Caption();
            var s = steps[idx];
            TourFx.Paused = paused;
            if (!paused)
            {
                t += Time.deltaTime;
                if (s.Grow)
                {
                    float yf = Mathf.Clamp(2025f + (t - 1.5f) / (s.Dur - 4f) * 25f, 2025f, 2050f);
                    int y = Mathf.Min(2050, Mathf.FloorToInt(yf));
                    if (y != TwinState.Year) TwinState.Year = y;
                    if (yf < 2050f) CityTimeline.Growth(yf); else CityTimeline.StopGrowth();
                }
                else if (s.AnimTo > 0)
                {
                    // a landmark rising: the year runs from AnimFrom to AnimTo over the step, smoothly
                    float yf = Mathf.Clamp(s.AnimFrom + (t - 1.5f) / (s.Dur - 5f) * (s.AnimTo - s.AnimFrom), s.AnimFrom, s.AnimTo);
                    int y = Mathf.FloorToInt(yf);
                    if (y != TwinState.Year) TwinState.Year = y;
                    if (yf < s.AnimTo) CityTimeline.Growth(yf); else CityTimeline.StopGrowth();
                }
                if (t > 0.6f && t - Time.deltaTime <= 0.6f) Caption();     // modules refresh their summaries after the first frames
                if (s.Shots != null) foreach (var (st, act) in s.Shots) if (t >= st && t - Time.deltaTime < st) { try { act(); } catch (Exception e) { Debug.LogWarning("[Alatau] tour shot: " + e.Message); } }
                if (t >= s.Dur) { Next(); return; }
            }
            if (bar != null) bar.style.width = Length.Percent(100f * Mathf.Clamp01(t / s.Dur));
            FitCard();
        }
    }
}
