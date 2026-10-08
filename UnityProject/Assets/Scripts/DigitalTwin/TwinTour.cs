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
            public int Zone = -1; public string Module = "overview"; public int Year = 2050; public Scenario Sc = Scenario.Base; public float Dur = 20f;
            public Action Enter; public Func<string> Title, Text; public Func<string[]> Bullets;
            public bool Grow; public int AnimFrom, AnimTo;   // year animation within the step (growth / a landmark rising)
        }
        readonly List<Step> steps = new List<Step>();
        bool running, paused; int idx; float t;
        VisualElement box, bar, zoneDot, bulletsBox, segs; Label lZone, lStep, lTitle, lText; Button bPause; VisualElement host;

        static readonly string[] ZoneName = { "GATE · ворота и деловой центр", "GOLDEN · наука, образование, медицина", "GROWING · промышленность и логистика", "GREEN · туризм на Капшагае" };
        static readonly string[] SegName = { "Город", "Gate", "Golden", "Growing", "Green", "Итог" };

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

        void Build()
        {
            steps.Clear();
            var db = CityDatabase.Instance; int all = db != null ? db.Buildings.Length : 0;
            // ---------------- the city
            steps.Add(new Step { Zone = -1, Year = 2025, Dur = 18, Enter = Overview,
                Title = () => "Alatau City",
                Text = () => "Новый город у Капшагая, между Алматы и Конаевом. Конституционный закон об особом режиме действует с 1 июля 2026 года.",
                Bullets = () => new[] { "88 267 га, четыре района: Gate, Golden, Growing, Green", "≈1,8–2 млн жителей и 1 млн рабочих мест к 2050 году", "67 инвестпроектов на ≈ $6,9 млрд (26.08.2026)", $"{Loc.N0(all)} зданий генплана в цифровом двойнике" } });
            steps.Add(new Step { Zone = -1, Year = 2025, Dur = 24, Grow = true, Enter = Overview,
                Title = () => "25 лет за 25 секунд",
                Text = () => $"Город растёт по годам ввода генплана. {TwinState.Year}: ~{K(Res(TwinState.Year))} жителей.",
                Bullets = () => new[] { "Новые здания поднимаются в год ввода и подсвечены", "Земля проходит путь «степь → стройплощадка → квартал»", "Все цифры панелей считаются из тех же данных" } });

            // ---------------- Gate
            steps.Add(new Step { Zone = 0, Year = 2050, Dur = 18, Enter = () => FrameZone(0),
                Title = () => "Gate — ворота города",
                Text = () => $"Финансы, бизнес, торговля и транспортный узел у трассы Алматы–Конаев и БАКАД. В 2050 году — {K(CityStats.Residents(0, 2050))} жителей.",
                Bullets = () => ObjectsOf(0) });
            steps.Add(new Step { Zone = 0, Module = "objects", Year = 2030, Dur = 22, Enter = () => Object("iconic"),
                Title = () => "Iconic Complex · 272 м",
                Text = () => "Самая высокая башня юга Казахстана от SOM: вертикальный район из башни 272 м, отеля 80 м и подиума, который террасами спускается к площади.",
                Bullets = () => new[] { "Площадь — " + Fact("iconic", "Площадь"), "Инвестиции — " + Fact("iconic", "Инвестиции"), "Сейсмостойкий каркас с демпферами", "Сдача — конец 2029 – начало 2030" } });
            steps.Add(new Step { Zone = 0, Module = "construction", Year = 2026, Dur = 22, AnimFrom = 2026, AnimTo = 2030, Enter = () => { TwinState.SetDistrict(0); Object("iconic"); },
                Title = () => "Стройка под контролем двойника",
                Text = () => $"{TwinState.Year}: Iconic поднимается по графику 2027–2030. Площадки района окрашены: по графику — оранжевые, отстают — красные, сданы — зелёные.",
                Bullets = () => new[] { "Съёмка БПЛА → объёмы и готовность «план / факт»", "Прогноз срыва сроков за недели до него", "Деньги по источникам и рейтинг подрядчиков" } });
            steps.Add(new Step { Zone = 0, Module = "overview", Year = 2031, Dur = 20, Enter = () => Station(0),
                Title = () => "ЛРТ: первая очередь Gate – Golden",
                Text = () => $"Лёгкое метро на эстакаде открывается в {LrtYear(0)} году: {Loc.N1(TwinData.LrtPhaseKm.Length > 0 ? TwinData.LrtPhaseKm[0] : 0)} км. Метро до Алатау не рассматривается — ставка на LRT.",
                Bullets = () => new[] { "Станции с навесами и лифтами к улице", "Поезда идут по открытым очередям, движение ускорено ×6", "Очереди 2 и 3 — Growing и Green" } });
            steps.Add(new Step { Zone = 0, Module = "situation", Year = 2036, Dur = 22, Enter = () => { TwinState.SetDistrict(0); Active<SituationModule>()?.TourOpen("dtp", true); },
                Title = () => "Ситуационный центр: ДТП на трассе у Gate",
                Text = () => { var i = SituationModule.Find("dtp"); return i == null ? "Камеры и вызов 112 фиксируют ДТП, центр управления движением открывает объезд." : $"Камеры подтверждают ДТП за минуты. Объезд и «зелёная волна»: в заторе {Loc.N0(i.Yes.AffectedMax)} человек вместо {Loc.N0(i.No.AffectedMax)}."; },
                Bullets = () => new[] { "112, камеры с видеоаналитикой и детекторы трафика в одной ленте", "Сравнение «решение принято / не принято»", "Работает по всей карте — здесь показано у Gate" } });

            // ---------------- Golden
            steps.Add(new Step { Zone = 1, Year = 2050, Dur = 18, Enter = () => FrameZone(1),
                Title = () => "Golden — знания и здоровье",
                Text = () => $"Наука, образование и медицина между Малой Алматинкой и Каскеленом: кампус на 40 тыс. студентов, медкластер, K-Park. В 2050 году — {K(CityStats.Residents(1, 2050))} жителей.",
                Bullets = () => ObjectsOf(1) });
            steps.Add(new Step { Zone = 1, Module = "objects", Year = 2033, Dur = 20, Enter = () => Object("kaist"),
                Title = () => "KAIST Kazakhstan",
                Text = () => "Технологический университет с корейским партнёром: главный корпус под стеклянной кровлей, библиотека-башня, лаборатории вокруг зелёного двора.",
                Bullets = () => new[] { "Кампус Golden — до 40 000 студентов", "Статус: прорабатывается", "Срок в демо — ориентир" } });
            steps.Add(new Step { Zone = 1, Module = "prediction", Year = 2034, Dur = 22, Enter = () => { FrameZone(1); Active<PredictionModule>()?.TourMetric("power"); },
                Title = () => "Двойник видит дефицит заранее", Text = () => Active<PredictionModule>()?.Summary ?? "",
                Bullets = () => new[] { "Спрос по годам ввода зданий против мощности подстанций", "Причина — сдвиг 2-й очереди ПС «Golden»", "Рекомендация — ускорить ввод" } });
            steps.Add(new Step { Zone = 1, Module = "situation", Year = 2036, Dur = 22, Enter = () => { TwinState.SetDistrict(1); Active<SituationModule>()?.TourOpen("leak", true); },
                Title = () => "Утечка на водоводе: решение принято",
                Text = () => { var i = SituationModule.Find("leak"); return i == null ? "" : $"Датчики давления находят утечку, участок перекрыт, вода идёт по резервной нитке: без воды {Loc.N0(i.Yes.AffectedMax)} человек вместо {Loc.N0(i.No.AffectedMax)}, ущерб {Money(i.Yes.Peak)} вместо {Money(i.No.Peak)}."; },
                Bullets = () => new[] { "16 потоков данных: SCADA, счётчики, 112, обращения жителей", "Прогноз последствий по часам", "Брифинг для акима одним экраном" } });

            // ---------------- Growing
            steps.Add(new Step { Zone = 2, Year = 2050, Dur = 18, Enter = () => FrameZone(2),
                Title = () => "Growing — промышленность и логистика",
                Text = () => $"Экспортные производства вдоль трассы и ж/д Жетыген – Казыбек-бек: пищевая, бумажная, упаковка, логистика. В 2050 году — {K(CityStats.Residents(2, 2050))} жителей.",
                Bullets = () => ObjectsOf(2) });
            steps.Add(new Step { Zone = 2, Module = "objects", Year = 2027, Dur = 20, Enter = () => Object("tlc"),
                Title = () => "ТЛЦ «Жетыген»",
                Text = () => "Транспортно-логистический центр Исткомтранса у железной дороги: пути, козловые краны, контейнерная площадка и склад.",
                Bullets = () => new[] { "Инвестиции — " + Fact("tlc", "Инвестиции"), "Связка трассы, ж/д и складов Growing", "Рядом — Sunny Paper, DanaFlex, G-Trans" } });
            steps.Add(new Step { Zone = 2, Module = "infra", Year = 2034, Dur = 22, Enter = () => { TwinState.SetDistrict(2); Object("ps_arna"); },
                Title = () => "Сети и подстанции",
                Text = () => "ПС «Арна» 220/110 кВ строится в первой фазе инфраструктуры. Вода, канализация, электричество, тепло, газ и связь проложены вдоль улиц генплана и вводятся очередями.",
                Bullets = () => new[] { "Фаза 1 — 21 проект, 365,1 млрд ₸", "Нагрузка и мощность по каждому объекту и году", "Однолинейная схема электросети" } });
            steps.Add(new Step { Zone = 2, Module = "prediction", Year = 2050, Dur = 20, Enter = () => { FrameZone(2); Active<PredictionModule>()?.TourMetric("school"); },
                Title = () => "Школы: хватает ли мест", Text = () => Active<PredictionModule>()?.Summary ?? "",
                Bullets = () => new[] { "Нормативы обеспеченности по районам и годам", "Growing — самый быстрый рост населения" } });
            steps.Add(new Step { Zone = 2, Module = "prediction", Year = 2050, Dur = 20, Enter = () => { Active<PredictionModule>()?.TourMetric("flood"); TwinState.SetDistrict(2); var f = SituationData.Incidents((int)TwinState.Scenario, 2050).FirstOrDefault(i => i.Id == "flood"); if (f != null) Fly(f.P, 5200f); },
                Title = () => "Риски: паводок на Каскелене", Text = () => Active<PredictionModule>()?.Summary ?? "",
                Bullets = () => new[] { "Подъём воды 1,6 и 3,0 м — здания в зоне риска", "Сейсмика 8–9 баллов — уязвимость по типу и возрасту" } });

            // ---------------- Green
            steps.Add(new Step { Zone = 3, Year = 2050, Dur = 18, Enter = () => FrameZone(3),
                Title = () => "Green — туризм на Капшагае",
                Text = () => $"Набережная, курорты и отдых на берегу водохранилища: 31 730 га. В 2050 году — {K(CityStats.Residents(3, 2050))} жителей.",
                Bullets = () => ObjectsOf(3) });
            steps.Add(new Step { Zone = 3, Module = "objects", Year = 2035, Dur = 20, Enter = () => Object("marina"),
                Title = () => "Марина Капшагай",
                Text = () => "Яхтенная марина с клубом и набережной — концепция Green District. Причалы уходят в воду, у берега — променад.",
                Bullets = () => new[] { "Статус: концепция, сроков нет", "4 млн туристов в год — цель к 2050" } });
            steps.Add(new Step { Zone = 3, Module = "overview", Year = 2041, Dur = 18, Enter = () => Station(2),
                Title = () => "ЛРТ доходит до Green",
                Text = () => $"Третья очередь открывается в {LrtYear(2)} году: {Loc.N1(TwinData.LrtPhaseKm.Length > 2 ? TwinData.LrtPhaseKm[2] : 0)} км до набережной Капшагая.",
                Bullets = () => new[] { "Вся линия — " + Loc.N1(TwinData.LrtPhaseKm.Sum()) + " км в три очереди", "41 станция" } });

            // ---------------- the whole city again
            steps.Add(new Step { Zone = -1, Module = "ai", Year = 2034, Dur = 22, Enter = () => { LS?.Select(null, false); TwinState.SetDistrict(-1); Active<AiModule>()?.TourAsk("Где поставить новую школу?"); },
                Title = () => "ИИ-ассистент",
                Text = () => "Вопрос своими словами — ИИ сам выставляет год, двигает камеру, красит районы и предлагает три участка для новой школы. Все цифры — из данных двойника.",
                Bullets = () => new[] { "Работает на всей карте и во всех районах", "Показывает, что сделал и насколько уверен" } });
            steps.Add(new Step { Zone = -1, Year = 2050, Dur = 20, Enter = Overview,
                Title = () => "Alatau City 2050",
                Text = () => $"~{K(Res(2050))} жителей. Один цифровой двойник для стройки, прогноза, инфраструктуры, ситуационного центра и ИИ — qTwin.",
                Bullets = () => new[] { "Gate · Golden · Growing · Green — на одной карте", "Реальные проекты, сценарии и риски в одном окне" } });
        }

        // ------------------------------------------------------------------ control
        void Begin()
        {
            if (!TwinData.Ready || !CityStats.Ready) { Debug.LogWarning("[Alatau] tour: data not ready"); return; }
            Build(); running = true; paused = false; Go(0);
        }
        public void Stop()
        {
            running = false; CityTimeline.StopGrowth(); if (box != null) box.style.display = DisplayStyle.None; host?.RemoveFromClassList("tour-on"); ReleaseColumn();
            if (TwinState.Scenario != Scenario.Base) TwinState.Scenario = Scenario.Base;
            TwinState.SetDistrict(-1);
        }
        void Go(int i)
        {
            idx = Mathf.Clamp(i, 0, steps.Count - 1); t = 0; var s = steps[idx]; CityTimeline.StopGrowth();
            TwinState.Playing = false; if (TwinState.Selected != null) TwinState.SetSelected(null);
            if (LS != null && LS.Selected != null) LS.Select(null, false);    // each step opens its own passport, if any
            if (TwinState.Scenario != s.Sc) TwinState.Scenario = s.Sc;
            TwinState.SetModule(s.Module);
            TwinState.Year = s.AnimTo > 0 ? s.AnimFrom : s.Year;
            if (s.Zone < 0 && TwinState.District >= 0 && s.Module != "ai") TwinState.SetDistrict(-1);
            try { s.Enter?.Invoke(); } catch (Exception e) { Debug.LogWarning("[Alatau] tour step " + idx + ": " + e.Message); }
            Caption();
        }
        void Caption()
        {
            Ensure(); if (box == null) return; var s = steps[idx];
            int seg = s.Zone >= 0 ? s.Zone + 1 : idx < 2 ? 0 : 5;
            lZone.text = s.Zone >= 0 ? ZoneName[s.Zone] : idx < 2 ? "ALATAU CITY · ГОРОД ЦЕЛИКОМ" : "ИТОГ";
            zoneDot.style.backgroundColor = s.Zone >= 0 ? CityStats.DistrictColors[s.Zone] : new Color(0.88f, 0.15f, 0.11f);
            lStep.text = $"{idx + 1} / {steps.Count}";
            int k = 0; foreach (var c in segs.Children()) { c.EnableInClassList("on", k == seg); c.EnableInClassList("done", k < seg); k++; }
            try { lTitle.text = s.Title(); lText.text = s.Text(); } catch { }
            bulletsBox.Clear();
            try
            {
                var bl = s.Bullets?.Invoke();
                if (bl != null) foreach (var b in bl.Where(x => !string.IsNullOrWhiteSpace(x)).Take(5))
                    {
                        var r = new VisualElement(); r.AddToClassList("tour-bullet");
                        var d = new VisualElement { pickingMode = PickingMode.Ignore }; d.AddToClassList("tour-bdot"); d.style.backgroundColor = s.Zone >= 0 ? CityStats.DistrictColors[s.Zone] : new Color(0.88f, 0.15f, 0.11f); r.Add(d);
                        r.Add(new Label(b) { pickingMode = PickingMode.Ignore }); bulletsBox.Add(r);
                    }
            }
            catch { }
            bPause.text = paused ? "Продолжить" : "Пауза";
            box.style.display = DisplayStyle.Flex; host?.AddToClassList("tour-on");
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
            lTitle = new Label(); lTitle.AddToClassList("tour-title"); box.Add(lTitle);
            lText = new Label(); lText.AddToClassList("tour-text"); box.Add(lText);
            bulletsBox = new VisualElement(); bulletsBox.AddToClassList("tour-bullets"); box.Add(bulletsBox);
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
        /// <summary>The caption takes the bottom of the right column; the column's panels end above it.</summary>
        void FitColumn()
        {
            if (host == null || box == null) return;
            var col = host.parent?.Q(className: "col-right"); if (col == null) return;
            float h = box.layout.height; if (float.IsNaN(h) || h < 10f) return;
            col.style.bottom = h + 22f;
        }
        void ReleaseColumn() { var col = host?.parent?.Q(className: "col-right"); if (col != null) col.style.bottom = StyleKeyword.Null; }
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
            if (box == null || box.parent == null) Caption();
            var s = steps[idx];
            if (!paused)
            {
                t += Time.deltaTime;
                if (s.Grow)
                {
                    float yf = Mathf.Clamp(2025f + (t - 1.5f) / (s.Dur - 4f) * 25f, 2025f, 2050f);
                    int y = Mathf.Min(2050, Mathf.FloorToInt(yf));
                    if (y != TwinState.Year) { TwinState.Year = y; lText.text = s.Text(); }
                    if (yf < 2050f) CityTimeline.Growth(yf); else CityTimeline.StopGrowth();
                }
                else if (s.AnimTo > 0)
                {
                    // a landmark rising: the year runs from AnimFrom to AnimTo over the step, smoothly
                    float yf = Mathf.Clamp(s.AnimFrom + (t - 1.5f) / (s.Dur - 5f) * (s.AnimTo - s.AnimFrom), s.AnimFrom, s.AnimTo);
                    int y = Mathf.FloorToInt(yf);
                    if (y != TwinState.Year) { TwinState.Year = y; lText.text = s.Text(); }
                    if (yf < s.AnimTo) CityTimeline.Growth(yf); else CityTimeline.StopGrowth();
                }
                if (t > 0.6f && t - Time.deltaTime <= 0.6f) Caption();     // modules refresh their summaries after the first frames
                if (t >= s.Dur) { Next(); return; }
            }
            if (bar != null) bar.style.width = Length.Percent(100f * Mathf.Clamp01(t / s.Dur));
            FitColumn();
        }
    }
}
