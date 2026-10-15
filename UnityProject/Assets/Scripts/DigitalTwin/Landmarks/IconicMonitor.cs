using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>«Мониторинг строительства» of Iconic Complex: a small construction platform inside the platform, in the style of the QazTWIN
    /// 4D pages. The city dims and a window opens with a live 3D view of the complex (its own camera: drag to turn, wheel to zoom;
    /// complex / tower / working floor), the work schedule as a Gantt chart (plan, actual, forecast after the last survey), a 4D timeline
    /// (drag the date or press play — the model, the floors, the numbers and the cameras follow; plan or actual), the card of the
    /// selected work with its progress curve, the plan-fact table of the tower by floors, and four site cameras with video analytics.
    /// The schedule comes from the same stage model as the floors (IconicFloors): the actual runs behind the plan by up to ≈ 2 months
    /// at the survey of 13.03.2028, the forecast after it closes the gap. Esc or × closes; Space plays, ← → step a month.</summary>
    [DefaultExecutionOrder(200)]
    public class IconicMonitor : MonoBehaviour
    {
        public static IconicMonitor Instance;
        public static bool Open => Instance != null && Instance.open;
        /// <summary>Frame in which the window was closed (its Esc must not also take the camera out of the tower).</summary>
        public static int ClosedFrame = -10;
        /// <summary>Date of the last survey — the "today" of the monitoring: 13 March of the year after the start (13.03.2028 for
        /// Iconic Complex, 13.03.2030 for KAIST). After it the actual is a forecast. T0 … T1: the span of the timeline.</summary>
        float Report = 2028f + 72f / 365f, T0 = 2026f, T1 = 2031f;
        const float Lag = 0.035f, Speed = 0.25f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Iconic Complex · monitoring").AddComponent<IconicMonitor>(); }
        void Awake() { Instance = this; }

        // ================================================================== the schedule
        /// <summary>A work of the schedule: its span [A, B] in the progress of the landmark; Phase = floor phase it follows (tower works);
        /// Place: 0 the floor where the work goes on, 1 a part of the site (Focus: local point, distance, pitch), 5 the whole tower.</summary>
        class Work { public string Code, Name, Zone, Scope, Src; public float A, B; public int Phase, Place; public Vector3 Focus; public float FDist = 300f, FPitch = 36f; }
        readonly List<Work> works = new List<Work>();
        Landmark L; float H = 272f;

        readonly float[] tt = new float[7];
        float PhStart(int k) { IconicFloors.Times(0, H, tt); return k == 2 ? 0.25f : tt[k - 1]; }          // the facade line leaves the ground at 25 %
        float PhEnd(int k) { IconicFloors.Times(IconicShape.Levels - 1, H, tt); return tt[k]; }
        Work W(string code, string name, string zone, float a, float b, int phase, int place, string scope, string src)
        { var w = new Work { Code = code, Name = name, Zone = zone, A = a, B = Mathf.Max(b, a + 0.01f), Phase = phase, Place = place, Scope = scope, Src = src }; works.Add(w); return w; }
        void At(Work w, float x, float y, float z, float dist, float pitch) { w.Focus = new Vector3(x, y, z); w.FDist = dist; w.FPitch = pitch; }
        void MakeWorks() { works.Clear(); if (L.Id == "kaist") MakeKaist(); else MakeIconic(); }
        void MakeIconic()
        {
            At(W("1.1", "Ограждение и котлован", "Площадка", 0f, 0.06f, 0, 1, "Ограждение площадки, котлован под башню и подземный паркинг, водопонижение", "облёт · геодезическая съёмка"), 36f, 2f, 34f, 230f, 42f);
            At(W("1.2", "Фундаментная плита", "Башня T1", 0.035f, 0.085f, 0, 1, "Плита башни на буронабивных сваях, бетон В40, четыре захватки", "акты скрытых работ"), 36f, 2f, 34f, 200f, 46f);
            W("2.1", "Ядро: самоподъёмная опалубка", "Башня T1", 0.072f, PhEnd(1) - 0.012f, 1, 0, "Монолитное ядро с лифтовыми шахтами; самоподъёмная опалубка идёт на этаж впереди перекрытий", "облёт · лазерное сканирование");
            W("2.2", "Перекрытия и колонны", "Башня T1", PhStart(1), PhEnd(1), 1, 0, "Колонны и плиты 56 этажей и двух уровней короны, бетон В40, захватка — один этаж", "облёт · датчики прочности бетона");
            W("3.1", "Фасад: модульный витраж", "Башня T1", PhStart(2), PhEnd(2), 2, 0, "Модульный витраж с золотыми поясами на каждом этаже, монтаж краном и с фасадного подъёмника", "отметка прораба · облёт");
            W("4.1", "Инженерные сети", "Башня T1", PhStart(3), PhEnd(3), 3, 0, "Вентиляция, спринклеры, холодоснабжение, кабельные лотки", "отметка прораба");
            W("4.2", "Перегородки", "Башня T1", PhStart(4), PhEnd(4), 4, 0, "Каркас из профиля, гипсокартон в два слоя, шпаклёвка", "отметка прораба");
            W("4.3", "Отделка", "Башня T1", PhStart(5), PhEnd(5), 5, 0, "Полы, потолки, окраска, отделка лобби и общественных зон", "отметка прораба");
            W("4.4", "Оснащение и мебель", "Башня T1", PhStart(6), PhEnd(6), 6, 0, "Мебель офисов и резиденций, оборудование ресторанов и спа", "по графику");
            At(W("5.1", "Отель T2: каркас", "Отель T2", 0.08f, 0.08f + 0.62f * 80f / H, 0, 1, "Монолитный каркас отеля высотой 80 м с каскадом террас", "облёт"), -80f, 30f, 44f, 260f, 30f);
            At(W("5.2", "Отель T2: фасад и террасы", "Отель T2", 0.25f, 0.25f + 0.65f * 80f / H, 0, 1, "Витражи, деревянные ламели, озеленение террас", "облёт"), -80f, 30f, 44f, 260f, 30f);
            At(W("6.1", "Ритейл: два корпуса", "Ритейл", 0.08f, 0.29f + 0.65f * 32f / H, 0, 1, "Два корпуса до 32 м с террасами и бассейнами на кровлях", "облёт"), 0f, 12f, -50f, 300f, 38f);
            At(W("7.1", "Благоустройство и озеленение", "Сад и площадь", 0.85f, 0.98f, 0, 1, "Аллеи вокруг участка, сад с фонтаном между башней и отелем, амфитеатр, газоны, посадка деревьев", "по графику"), 0f, 0f, 30f, 330f, 46f);
            W("8.1", "Пусконаладка и сдача", "Башня T1", 0.90f, 1f, 0, 5, "Пусконаладка инженерных систем, приёмка и ввод в эксплуатацию", "по графику");
        }
        /// <summary>KAIST campus: the park laid out first (lawns, the lake with fountains), the library and research tower (its floors are
        /// followed like the Iconic tower), the main hall lifted on columns, the laboratory comb, the curved north block, the sports oval.</summary>
        void MakeKaist()
        {
            string T = "Башня B1";
            At(W("1.1", "Подготовка территории и котлованы", "Кампус", 0f, 0.06f, 0, 1, "Ограждение площадок корпусов, котлованы, временные дороги и городок строителей", "облёт · геодезическая съёмка"), 0f, 2f, 0f, 520f, 52f);
            At(W("1.2", "Парк первой очереди", "Парк", 0.01f, 0.07f, 0, 1, "Газоны по всему кампусу, озеро с островом, мостиком и фонтанами, кольцевая дорожка с фонарями, аллея по периметру — до начала корпусов", "облёт · по графику"), -15f, 4f, -5f, 260f, 42f);
            At(W("1.3", "Фундаменты корпусов", "Кампус", 0.035f, 0.09f, 0, 1, "Плита башни, ленточные и столбчатые фундаменты корпусов, бетон В30–В35", "акты скрытых работ"), 60f, 2f, 0f, 420f, 50f);
            W("2.1", "Башня: монолитное ядро", T, 0.072f, PhEnd(1) - 0.012f, 1, 0, "Ядро с лифтами и лестницами; скользящая опалубка идёт на этаж впереди перекрытий", "облёт · лазерное сканирование");
            W("2.2", "Башня: перекрытия и колонны", T, PhStart(1), PhEnd(1), 1, 0, "Колонны и плиты 13 этажей и технического уровня, западный фасад с наклоном (от 40 до 32 м), бетон В35", "облёт · датчики прочности бетона");
            W("2.3", "Башня: фасад", T, PhStart(2), PhEnd(2), 2, 0, "Бирюзовый витраж с белыми поясами перекрытий, вертикальные ламели на восточном фасаде, монтаж с фасадного подъёмника", "отметка прораба · облёт");
            W("2.4", "Башня: инженерные сети", T, PhStart(3), PhEnd(3), 3, 0, "Вентиляция, спринклеры, слаботочные сети библиотеки и лабораторий", "отметка прораба");
            W("2.5", "Башня: перегородки", T, PhStart(4), PhEnd(4), 4, 0, "Лабораторные боксы, читальные залы, аудитория", "отметка прораба");
            W("2.6", "Башня: отделка", T, PhStart(5), PhEnd(5), 5, 0, "Полы, акустические потолки, отделка вестибюля и аудитории", "отметка прораба");
            W("2.7", "Башня: оснащение, кровельный сад и стеклянная пирамида", T, PhStart(6), PhEnd(6), 6, 0, "Стеллажи библиотеки, лабораторная мебель, сад на кровле, стеклянная пирамида-фонарь", "по графику");
            At(W("3.1", "Главный корпус: колонны и каркас", "Главный корпус", 0.08f, 0.08f + 0.62f * 29f / H, 0, 1, "Белые колонны вестибюля, стеклянный объём 150 × 56 м поднят на отметку 10 м, белая терраса с лестницей и пандусом", "облёт"), -20f, 14f, -122f, 270f, 30f);
            At(W("3.2", "Главный корпус: витражи и пирамиды", "Главный корпус", 0.25f, 0.25f + 0.65f * 40f / H, 0, 1, "Синий витраж с белой сеткой стоек и ригелей, три стеклянные пирамиды-фонаря на кровле", "облёт"), -20f, 14f, -122f, 270f, 30f);
            At(W("4.1", "Лабораторные корпуса", "Лаборатории", 0.08f, 0.25f + 0.65f * 19f / H, 0, 1, "Корпус-хребет и три ступенчатых крыла с бирюзовым остеклением и зелёными кровлями вокруг озеленённых дворов", "облёт"), -160f, 10f, 20f, 260f, 34f);
            At(W("4.2", "Северный учебный корпус", "Учебный корпус", 0.08f, 0.25f + 0.65f * 20f / H, 0, 1, "Изогнутый стеклянный корпус с белыми ламелями и зелёной кровлей, обращён к озеру", "облёт"), -15f, 9f, 125f, 260f, 34f);
            At(W("5.1", "Спортивное ядро", "Спорт", 0.6f, 0.8f, 0, 1, "Футбольное поле в овале беговых дорожек, трибуна с навесом", "по графику"), 140f, 0f, -122f, 210f, 46f);
            At(W("6.1", "Благоустройство у корпусов", "Кампус", 0.85f, 0.98f, 0, 1, "Площадь перед главным корпусом с бассейном и фонтанами, мощение у корпусов, живые изгороди, посадка деревьев во дворах", "по графику"), -20f, 0f, -60f, 330f, 46f);
            W("7.1", "Пусконаладка и сдача", T, 0.90f, 1f, 0, 5, "Пусконаладка инженерных систем, приёмка и ввод в эксплуатацию", "по графику");
        }

        // plan = the stage model of the landmark; actual = the plan minus a delay that built up during the frame (≈ 2 months at the survey)
        // and is closed after it by a second shift (forecast)
        float PlanP(float d) => LandmarkSystem.Progress(L, d);
        float LagAt(float d)
        {
            float up = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((d - (L.StartYear + 0.15f)) / 1.0f));
            float down = d <= Report ? 1f : Mathf.Clamp01(1f - (d - Report) / 1.4f);
            return Lag * up * down;
        }
        float FactP(float d) => Mathf.Clamp01(PlanP(d) - LagAt(d));
        float PlanDate(float p) => IconicFloors.YearAt(L, p);
        float FactDate(float p)
        {
            float a = T0, b = T1 + 1f;
            for (int i = 0; i < 28; i++) { float m = (a + b) * 0.5f; if (FactP(m) >= p) b = m; else a = m; }
            return b;
        }
        struct St { public float Plan, Fact; public int Days; }
        St Stat(Work w, float d)
        {
            float pp = PlanP(d), fp = FactP(d);
            var s = new St { Plan = Mathf.Clamp01((pp - w.A) / (w.B - w.A)), Fact = Mathf.Clamp01((fp - w.A) / (w.B - w.A)) };
            if (s.Fact >= 0.999f) s.Days = Mathf.RoundToInt((FactDate(w.B) - PlanDate(w.B)) * 365f);
            else if (s.Plan <= 0f) s.Days = 0;
            else s.Days = Mathf.RoundToInt((d - PlanDate(w.A + s.Fact * (w.B - w.A))) * 365f);
            return s;
        }
        static string Cls(int days) => days <= 3 ? "ok" : days <= 21 ? "warn" : "bad";
        static string Dev(St s) => s.Plan <= 0f && s.Fact <= 0f ? "—" : s.Days <= 3 ? "в срок" : "−" + s.Days + " дн.";
        static string Pct(float v) => Mathf.RoundToInt(v * 100f) + " %";
        static string Day(float y) { var t = new DateTime(Mathf.FloorToInt(y), 1, 1).AddDays((y - Mathf.Floor(y)) * 365f); return t.ToString("dd.MM.yyyy"); }
        static string Floors(int n) { int m = n % 100, d = n % 10; return m >= 11 && m <= 14 ? "этажей" : d == 1 ? "этаж" : d >= 2 && d <= 4 ? "этажа" : "этажей"; }

        /// <summary>The floor where a phase is going on at progress p (the highest one); −1 = not started on any floor, −2 = done everywhere.</summary>
        int Front(int k, float p)
        {
            bool any = false;
            for (int i = IconicShape.Levels - 1; i >= 0; i--)
            {
                int ph = IconicFloors.Phase(i, Mathf.Min(p, 0.998f), H, out _);
                if (ph == k) return i;
                if (ph < k) any = true;
            }
            return any ? -1 : -2;
        }
        int WorkFloor(float p)
        {
            int f = Front(IconicFloors.PFrame, p); if (f >= 0) return f;
            for (int i = IconicShape.Levels - 1; i >= 0; i--) if (IconicFloors.Phase(i, Mathf.Min(p, 0.998f), H, out _) > IconicFloors.PNone) return i;
            return 0;
        }
        int Count(float p, int phase)
        {
            int n = 0; for (int i = 0; i < IconicShape.Floors; i++) if (IconicFloors.Phase(i, Mathf.Min(p, 0.998f), H, out _) >= phase) n++;
            return n;
        }

        // ================================================================== state
        enum View { Complex, Tower, Floor, Cam }
        bool open, wasInside, playing, planMode; int prevYear = -1, tab, sel = 3, camIx;
        float date, shownP, uiT, floorT, phase;
        View view = View.Floor; int focusFloor = -1;
        Vector3 focusLocal; float focusDist = 430f;
        float yaw, pitch = 54f, zoomK = 1f, camYawOff, camPitchOff, camFov = 58f;
        Transform model; Camera main, mon; RenderTexture monRT, bgRT;
        int mainMask; CameraClearFlags mainClear; Color mainBg;
        Vector3 curPos; Quaternion curRot;
        Image bgImg;

        // ------------------------------------------------------------------ open / close
        public void Show() => Show(IconicInterior.Active ? IconicShape.P.Id : "iconic");
        /// <summary>Opens the monitoring of landmark id (one with a TowerProfile: Iconic Complex, KAIST) on the stage of the year after its start.</summary>
        public void Show(string id)
        {
            var ii = IconicInterior.Instance; var ls = LandmarkSystem.Instance; if (ii == null || ls == null || !ls.Ready || open) return;
            if (TowerProfile.For(id) == null) return;
            L = ls.Get(id); if (L == null) return; H = L.Height;
            int stage = L.StartYear + 1; Report = stage + 72f / 365f; T0 = L.StartYear - 1f; T1 = L.EndYear + 1f;
            prevYear = TwinState.Year;
            if (TwinState.Year != stage) TwinState.Year = stage;
            wasInside = IconicInterior.Active && IconicShape.P.Id == id;
            if (!wasInside) ii.Enter(id);
            if (!IconicInterior.Active || IconicShape.P.Id != id) { RestoreYear(); return; }
            model = ls.ModelOf(id); main = Camera.main; if (model == null || main == null) { RestoreYear(); return; }
            MakeWorks();
            open = true; playing = false; planMode = false; scrubbing = false; tab = 0; date = Report;
            sel = works.FindIndex(w => w.Phase == 1 && w.Place == 0 && w.Code.EndsWith(".2")); if (sel < 0) sel = 0;
            focusFloor = -1; floorT = 0f; uiT = 0f; zoomK = 1f; camYawOff = camPitchOff = 0f; camFov = 58f;
            IconicInterior.Suspended = true; ii.HidePanel();
            SetDate(date, true);
            // the monitoring camera starts where the city camera is and flies to the working floor
            if (mon == null) { var g = new GameObject("Iconic monitoring · view"); g.transform.SetParent(transform, false); mon = g.AddComponent<Camera>(); mon.enabled = false; }
            mon.CopyFrom(main); mon.ResetProjectionMatrix(); mon.allowHDR = false; mon.fieldOfView = 40f; mon.nearClipPlane = 0.5f; mon.farClipPlane = 40000f; mon.depth = main.depth - 1;
            curPos = main.transform.position; curRot = main.transform.rotation;
            yaw = main.transform.eulerAngles.y + 25f;
            Select(sel, true);
            // the city behind the window: one still frame under the platform's panels; the city camera rests while the window is open
            Freeze();
            Build();
        }
        public void Close()
        {
            if (!open) return;
            open = false; playing = false; ClosedFrame = Time.frameCount;
            var ui = TwinUI.Instance;
            if (overlay != null) { ui?.ForgetChrome(overlay); overlay.RemoveFromHierarchy(); overlay = null; }
            Unfreeze();
            if (mon != null) { mon.enabled = false; mon.targetTexture = null; }
            LandmarkSystem.YearOverride = -1f;
            RestoreYear();
            var ii = IconicInterior.Instance;
            if (ii != null && IconicInterior.Active)
            {
                if (focusFloor >= 0) ii.Puppet(focusFloor, true);
                ii.Resume();
                if (!wasInside) ii.Exit();
            }
            IconicInterior.Suspended = false;
            if (ui != null) MapCamera.BlockInput = ui.PointerOverChrome;
        }
        void RestoreYear() { if (prevYear > 0 && TwinState.Year != prevYear) TwinState.Year = prevYear; prevYear = -1; }
        void OnDestroy() { if (monRT != null) monRT.Release(); if (bgRT != null) bgRT.Release(); foreach (var rt in camRT) if (rt != null) rt.Release(); }

        void Freeze()
        {
            var root = TwinUI.Instance?.Middle; root = root?.parent ?? root; if (root == null) return;
            int w = Mathf.Max(64, Screen.width), h = Mathf.Max(64, Screen.height);
            if (bgRT == null || bgRT.width != w || bgRT.height != h) { if (bgRT != null) bgRT.Release(); bgRT = new RenderTexture(w, h, 24) { name = "iconic_city_still" }; bgRT.Create(); }
            var t = main.targetTexture; main.targetTexture = bgRT;
            try { main.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] monitoring still: " + e.Message); }
            main.targetTexture = t;
            bgImg = new Image { image = bgRT, scaleMode = ScaleMode.StretchToFill, pickingMode = PickingMode.Ignore };
            bgImg.style.position = Position.Absolute; bgImg.style.left = 0; bgImg.style.top = 0; bgImg.style.right = 0; bgImg.style.bottom = 0;
            root.Insert(0, bgImg);
            mainMask = main.cullingMask; mainClear = main.clearFlags; mainBg = main.backgroundColor;
            main.cullingMask = 0; main.clearFlags = CameraClearFlags.SolidColor; main.backgroundColor = Color.black;
            FilmLook.MainIdle = true; FilmLook.ShadowOverride = 1600f;          // no picture finish on the idle map camera; near shadows for the views
        }
        void Unfreeze()
        {
            if (bgImg != null) { bgImg.RemoveFromHierarchy(); bgImg = null; }
            if (main != null) { main.cullingMask = mainMask; main.clearFlags = mainClear; main.backgroundColor = mainBg; }
            FilmLook.MainIdle = false; FilmLook.ShadowOverride = -1f;
        }

        // ------------------------------------------------------------------ the date (4D)
        void SetDate(float d, bool force = false)
        {
            d = Mathf.Clamp(d, T0, T1);
            if (!force && Mathf.Abs(d - date) < 1e-5f) return;
            date = d;
            shownP = planMode ? PlanP(d) : FactP(d);
            LandmarkSystem.YearOverride = IconicFloors.YearAt(L, shownP);
            dirty = true;
        }
        bool dirty, scrubbing;
        void SyncCityYear()
        {
            int y = Mathf.Clamp(Mathf.FloorToInt(date), TwinState.MinYear, TwinState.MaxYear);
            if (!scrubbing && TwinState.Year != y) TwinState.Year = y;
        }

        // ------------------------------------------------------------------ selection and views
        void Select(int i, bool focus)
        {
            sel = Mathf.Clamp(i, 0, works.Count - 1);
            if (focus) Focus();
            dirty = true;
        }
        void Focus()
        {
            var w = works[sel]; zoomK = 1f;
            switch (w.Place)
            {
                case 0: view = View.Floor; pitch = 54f; break;
                case 1: view = View.Complex; focusLocal = w.Focus; focusDist = w.FDist; pitch = w.FPitch; break;
                default: view = View.Tower; pitch = 16f; break;
            }
        }
        void SetView(View v)
        {
            view = v; zoomK = 1f;
            if (v == View.Complex) { focusLocal = L.Id == "kaist" ? new Vector3(0f, 10f, 0f) : new Vector3(-10f, 20f, 0f); focusDist = L.Id == "kaist" ? 560f : 440f; pitch = 36f; }
            else if (v == View.Tower) pitch = 16f;
            else if (v == View.Floor) pitch = 54f;
            dirty = true;
        }
        /// <summary>The floor the 3D view and the core camera look at: the front of the selected tower work, else the working floor.</summary>
        int FloorFor()
        {
            var w = works[sel];
            if (w.Phase > 0)
            {
                int f = Front(w.Phase, shownP);
                if (f >= 0) return w.Code == "2.1" ? Mathf.Min(f + 1, IconicShape.Levels - 1) : f;
            }
            return WorkFloor(shownP);
        }
        float FrameTop => H * Mathf.Clamp01((shownP - 0.08f) / 0.62f);

        // ------------------------------------------------------------------ per frame
        void Update()
        {
            if (!open) return;
            if (!IconicInterior.Active) { Close(); return; }
            float dt = Time.unscaledDeltaTime; phase += dt;
            if (!MapCamera.Typing)
            {
                if (Input.GetKeyDown(KeyCode.Escape)) { if (view == View.Cam) SetView(View.Floor); else { Close(); return; } }
                if (Input.GetKeyDown(KeyCode.Space)) TogglePlay();
                if (Input.GetKeyDown(KeyCode.RightArrow)) { playing = false; SetDate(date + 1f / 12f); }
                if (Input.GetKeyDown(KeyCode.LeftArrow)) { playing = false; SetDate(date - 1f / 12f); }
            }
            if (playing)
            {
                SetDate(date + dt * Speed);
                if (date >= T1 - 1e-4f) playing = false;
            }
            if (!scrubbing) SyncCityYear();
            // the floor shown in the cut follows the front of the work (rebuilt at most a few times a second while the date moves)
            floorT -= dt;
            bool cut = view == View.Floor || (view == View.Cam && camIx == 0);
            if (floorT <= 0f)
            {
                floorT = 0.15f;
                int f = FloorFor();
                if (f != focusFloor || dirty) { focusFloor = f; }
                IconicInterior.Instance?.Puppet(focusFloor, cut);
            }
            LandmarkSystem.CutId = cut ? L.Id : null;
            LandmarkSystem.CutAt = cut ? IconicShape.FloorY(focusFloor) + 1.6f : -1f;
            uiT -= dt;
            if (dirty && uiT <= 0f) { uiT = 0.06f; dirty = false; Refresh(); }
            Feeds(dt);
        }

        void LateUpdate()
        {
            if (!open || mon == null || model == null) return;
            float dt = Time.unscaledDeltaTime;
            Vector3 pos; Quaternion rot; float fov = 40f;
            if (view == View.Cam)
            {
                CamPose(camIx, out pos, out rot, true, camYawOff, camPitchOff); fov = camFov;
            }
            else
            {
                Vector3 target; float dist;
                if (view == View.Complex) { target = model.TransformPoint(focusLocal); dist = focusDist; }
                else if (view == View.Tower) { float top = Mathf.Max(FrameTop, 30f); target = model.TransformPoint(new Vector3(IconicShape.Xr - IconicShape.W0 * 0.5f, top * 0.5f, IconicShape.Cz)); dist = top * 1.05f + 170f; }
                else { var c = IconicFloors.Centre(Mathf.Max(focusFloor, 0), out float size); target = model.TransformPoint(c + Vector3.up * 1.2f); dist = size * 1.5f + 34f; }
                rot = Quaternion.Euler(pitch, yaw, 0f); pos = target - rot * Vector3.forward * dist * zoomK;
                float g = CityGround.HeightAt(pos.x, pos.z) + 3f; if (pos.y < g) pos.y = g;
            }
            float k = 1f - Mathf.Exp(-5f * dt);
            curPos = Vector3.Lerp(curPos, pos, k); curRot = Quaternion.Slerp(curRot, rot, k);
            mon.transform.SetPositionAndRotation(curPos, curRot);
            mon.fieldOfView = Mathf.Lerp(mon.fieldOfView, fov, k);
            mon.nearClipPlane = view == View.Cam ? 0.2f : 0.5f;
            // on the schedule tab the picture is centred in the free part above the Gantt chart (off-centre projection)
            mon.ResetProjectionMatrix();
            if (tab == 1 && gantt != null && photo != null)
            {
                var pb = photo.worldBound; var gb = gantt.worldBound;
                if (pb.height > 10f && gb.height > 10f)
                {
                    float c = Mathf.Clamp01(((pb.yMin + gb.yMin) * 0.5f - pb.yMin) / pb.height);
                    var m = mon.projectionMatrix; m[1, 2] = -(1f - 2f * c); mon.projectionMatrix = m;
                }
            }
            // the picture: as large as the viewport, in screen pixels
            if (photo != null && photo.panel != null)
            {
                var r = photo.worldBound; float ppp = Screen.height / Mathf.Max(photo.panel.visualTree.layout.height, 1f) * GraphicsQuality.ViewScale;
                int W = Mathf.Clamp(Mathf.RoundToInt(r.width * ppp), 64, 2400), Hh = Mathf.Clamp(Mathf.RoundToInt(r.height * ppp), 64, 1600);
                if (r.width > 10f && (monRT == null || Mathf.Abs(monRT.width - W) > 8 || Mathf.Abs(monRT.height - Hh) > 8 || monRT.antiAliasing != GraphicsQuality.ViewMsaa))
                {
                    if (monRT != null) { mon.targetTexture = null; monRT.Release(); }
                    monRT = new RenderTexture(W, Hh, 24) { name = "iconic_monitor", antiAliasing = GraphicsQuality.ViewMsaa }; monRT.Create();
                    mon.targetTexture = monRT; photo.image = monRT;
                }
                // the window is built anew each time it opens: hand the picture to its image every time (not only when the texture is made)
                if (monRT != null)
                {
                    if (mon.targetTexture != monRT) mon.targetTexture = monRT;
                    if (!mon.enabled) mon.enabled = true;
                    if (photo.image != monRT) photo.image = monRT;
                }
                Pin();
            }
            // video analytics on the full-size camera picture (the pose and projection the picture is about to be drawn with)
            if (view == View.Cam) Detect(mon, monRT != null ? monRT.height : 600f, bigBox); else bigBox.Clear();
            bigOver?.MarkDirtyRepaint();
        }

        // ------------------------------------------------------------------ site cameras
        static readonly string[] CamId = { "CAM-07", "CAM-02", "CAM-04", "CAM-11" };
        string[] CamName => L != null && L.Id == "kaist"
            ? new[] { "Ядро башни · захватка", "Берег озера", "Фасадный подъёмник · восток", "Кровля главного корпуса" }
            : new[] { "Ядро башни · захватка", "Площадь · амфитеатр", "Фасадный подъёмник · восток", "Кровля отеля T2" };
        readonly RenderTexture[] camRT = new RenderTexture[4]; Camera feedCam; int rr; float feedT;
        void CamPose(int i, out Vector3 pos, out Quaternion rot, bool pan, float yawOff = 0f, float pitchOff = 0f)
        {
            int f = Mathf.Max(focusFloor, 0); float yb = IconicShape.FloorY(f), top = Mathf.Max(FrameTop, 20f);
            Vector3 eye, look;
            switch (i)
            {
                case 0: eye = new Vector3(IconicShape.Xr - 4f, yb + 9f, IconicShape.Cz + IconicShape.Depth(yb) * 0.42f); look = IconicFloors.Centre(f, out _) + Vector3.up * 1.2f; break;
                case 1:
                    if (L.Id == "kaist") { eye = new Vector3(-40f, 14f, -50f); look = new Vector3(IconicShape.Xr - 20f, top * 0.55f, IconicShape.Cz); }
                    else { eye = new Vector3(-14f, 14f, -40f); look = new Vector3(IconicShape.Xr - 30f, top * 0.55f, IconicShape.Cz); }
                    break;
                case 2:
                    {
                        int ff = Front(IconicFloors.PFacade, shownP); if (ff < 0) ff = WorkFloor(shownP);
                        float y = IconicShape.FloorY(ff); eye = new Vector3(IconicShape.Xr + 16f, y + 5f, IconicShape.Cz - 20f); look = new Vector3(IconicShape.Xr - 6f, y, IconicShape.Cz + 2f); break;
                    }
                default:
                    if (L.Id == "kaist") { eye = new Vector3(40f, 34f, -100f); look = new Vector3(IconicShape.Xr - 20f, Mathf.Max(top - 10f, 8f), IconicShape.Cz); }
                    else { eye = new Vector3(-34f, 86f, 22f); look = new Vector3(IconicShape.Xr - 30f, Mathf.Max(top - 12f, 10f), IconicShape.Cz); }
                    break;
            }
            pos = model.TransformPoint(eye); var d = model.TransformPoint(look) - pos;
            float yw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg + (pan ? Mathf.Sin(phase * 0.16f + i * 1.7f) * 14f : 0f);
            float pt = Mathf.Atan2(-d.y, new Vector2(d.x, d.z).magnitude) * Mathf.Rad2Deg;
            rot = Quaternion.Euler(Mathf.Clamp(pt + pitchOff, -60f, 85f), yw + yawOff, 0f);
        }
        /// <summary>Renders the site cameras into their small screens: the core camera on the overview (≈ 7 frames a second),
        /// all four in turn on the cameras tab.</summary>
        /// <summary>Video analytics of a site camera: every worker on the floor in the cut (IconicFloors.Crew) that this camera really
        /// sees — in front of it, inside its picture, large enough to recognise, not behind the core or below the cut edge of the facade —
        /// gets a box round its figure, in the picture's own coordinates (0..1, y up) at the moment the picture is taken.</summary>
        readonly List<Rect>[] feedBox = { new List<Rect>(), new List<Rect>(), new List<Rect>(), new List<Rect>() };
        readonly List<Rect> bigBox = new List<Rect>(); VisualElement bigOver;
        int crewSeen = -1;
        void Detect(Camera cam, float rtH, List<Rect> list)
        {
            list.Clear();
            var ii = IconicInterior.Instance;
            if (cam == null || ii == null || !ii.FloorShown || IconicFloors.CrewFloor != focusFloor || IconicFloors.CrewTower != IconicShape.P.Id) return;
            var vp = cam.projectionMatrix * cam.worldToCameraMatrix;
            Vector3 eye = model.InverseTransformPoint(cam.transform.position);
            float cutY = LandmarkSystem.CutAt >= 0f ? LandmarkSystem.CutAt : float.MaxValue;
            var plate = IconicFloors.CrewPlate; var core = IconicFloors.CrewCore;
            core = Rect.MinMaxRect(core.xMin - 1.05f, core.yMin - 1.05f, core.xMax + 0.55f, core.yMax + 1.05f);   // with the climbing formwork round it
            float coreTop = IconicFloors.CrewYt + IconicShape.Fh + 2.5f;             // the core and its formwork run a floor ahead
            foreach (var w in IconicFloors.Crew)
            {
                var head = w + Vector3.up * 1.6f; var chest = w + Vector3.up * 1.1f;
                if (eye.y < w.y + 0.4f) continue;                                      // a camera below the floor sees its soffit
                if (Blocked(eye, head, core, w.y, coreTop) && Blocked(eye, chest, core, w.y, coreTop)) continue;
                if (!plate.Contains(new Vector2(eye.x, eye.z)) && EdgeHeight(eye, head, plate) < cutY - 0.05f) continue;   // the facade below the cut
                float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f; bool ok = true;
                for (int c = 0; c < 8; c++)
                {
                    var lp = w + new Vector3((c & 1) == 0 ? -0.28f : 0.28f, (c & 2) == 0 ? 0f : 1.84f, (c & 4) == 0 ? -0.24f : 0.24f);
                    var wp = model.TransformPoint(lp); var cp = vp * new Vector4(wp.x, wp.y, wp.z, 1f);
                    if (cp.w < 0.25f) { ok = false; break; }
                    float nx = cp.x / cp.w * 0.5f + 0.5f, ny = cp.y / cp.w * 0.5f + 0.5f;
                    x0 = Mathf.Min(x0, nx); x1 = Mathf.Max(x1, nx); y0 = Mathf.Min(y0, ny); y1 = Mathf.Max(y1, ny);
                }
                if (!ok || x1 < 0.01f || x0 > 0.99f || y1 < 0.01f || y0 > 0.99f) continue;
                if ((y1 - y0) * rtH < 6f) continue;                                    // too small in the picture to recognise
                float px = (x1 - x0) * 0.18f, py = (y1 - y0) * 0.08f;
                list.Add(Rect.MinMaxRect(x0 - px, y0 - py, x1 + px, y1 + py));
            }
        }
        static readonly Color BoxC = new Color(0.35f, 0.95f, 0.55f, 0.95f);
        /// <summary>The analytics boxes over a picture of size w × h whose top-left corner is at (ox, oy), drawn w × h large.</summary>
        static void DrawBoxes(Painter2D g, List<Rect> boxes, float ox, float oy, float dw, float dh, Rect clip, float line)
        {
            foreach (var b in boxes)
            {
                var q = Rect.MinMaxRect(ox + b.xMin * dw, oy + (1f - b.yMax) * dh, ox + b.xMax * dw, oy + (1f - b.yMin) * dh);
                if (q.xMax < clip.xMin || q.xMin > clip.xMax || q.yMax < clip.yMin || q.yMin > clip.yMax) continue;
                Frame(g, q, BoxC, line);
                float tw = Mathf.Min(q.width, 10f * line), th = 2.4f * line;
                g.fillColor = BoxC; g.BeginPath(); g.MoveTo(new Vector2(q.xMin, q.yMin - th)); g.LineTo(new Vector2(q.xMin + tw, q.yMin - th));
                g.LineTo(new Vector2(q.xMin + tw, q.yMin)); g.LineTo(new Vector2(q.xMin, q.yMin)); g.ClosePath(); g.Fill();
            }
        }
        void SeenNote(int i)
        {
            if (i != 0 || aiNote == null) return;
            int n = feedBox[0].Count; if (n == crewSeen) return; crewSeen = n;
            aiNote.text = n == 0 ? "ИИ-видеоаналитика: в кадре нет людей" : "ИИ-видеоаналитика: " + n + " " + People(n) + " в кадре · все в касках и жилетах";
        }
        static string People(int n) { int m = n % 100, d = n % 10; return m >= 12 && m <= 14 ? "человек" : d >= 2 && d <= 4 ? "человека" : "человек"; }
        /// <summary>The sight line eye → p passes through the core (a box over the core plan from the floor to coreTop).</summary>
        static bool Blocked(Vector3 eye, Vector3 p, Rect core, float yb, float coreTop)
        {
            Vector3 d = p - eye; float t0 = 0f, t1 = 0.98f;
            if (!Slab1(eye.x, d.x, core.xMin, core.xMax, ref t0, ref t1)) return false;
            if (!Slab1(eye.z, d.z, core.yMin, core.yMax, ref t0, ref t1)) return false;
            if (!Slab1(eye.y, d.y, yb, coreTop, ref t0, ref t1)) return false;
            return t0 <= t1;
        }
        static bool Slab1(float o, float d, float lo, float hi, ref float t0, ref float t1)
        {
            if (Mathf.Abs(d) < 1e-6f) return o >= lo && o <= hi;
            float a = (lo - o) / d, b = (hi - o) / d; if (a > b) { var s = a; a = b; b = s; }
            t0 = Mathf.Max(t0, a); t1 = Mathf.Min(t1, b); return t0 <= t1;
        }
        /// <summary>Height at which the sight line from an eye outside the plate crosses the plate's edge on its way to p.</summary>
        static float EdgeHeight(Vector3 eye, Vector3 p, Rect plate)
        {
            Vector3 d = p - eye; float t0 = 0f, t1 = 1f;
            if (!Slab1(eye.x, d.x, plate.xMin, plate.xMax, ref t0, ref t1) || !Slab1(eye.z, d.z, plate.yMin, plate.yMax, ref t0, ref t1)) return float.MaxValue;
            return eye.y + d.y * t0;
        }
        void Feeds(float dt)
        {
            feedT -= dt; feedOver?.MarkDirtyRepaint(); foreach (var o in tileOver) o?.MarkDirtyRepaint();
            if (feedClock != null) feedClock.text = Day(Mathf.Min(date, Report)) + "  " + DateTime.Now.ToString("HH:mm:ss");
            if (feedT > 0f || main == null) return;
            int i; if (tab == 2) { i = rr = (rr + 1) % 4; feedT = 0.08f; } else if (tab == 0) { i = 0; feedT = 0.15f; } else return;
            if (camRT[i] == null) { camRT[i] = new RenderTexture(400, 225, 24) { name = "iconic_cctv_" + i, antiAliasing = Mathf.Min(2, GraphicsQuality.ViewMsaa) }; camRT[i].Create(); }
            if (feedCam == null) { var g = new GameObject("Iconic monitoring · site camera"); g.transform.SetParent(transform, false); feedCam = g.AddComponent<Camera>(); feedCam.enabled = false; }
            feedCam.CopyFrom(mon); feedCam.ResetProjectionMatrix(); feedCam.enabled = false; feedCam.targetTexture = camRT[i]; feedCam.ResetAspect(); feedCam.fieldOfView = 58f; feedCam.nearClipPlane = 0.2f; feedCam.farClipPlane = 20000f;
            CamPose(i, out var p, out var r, true); feedCam.transform.SetPositionAndRotation(p, r);
            Detect(feedCam, camRT[i] != null ? camRT[i].height : 225f, feedBox[i]); SeenNote(i);
            // a site camera is a small picture: no shadow maps for it (each extra view would draw the city into its own cascades)
            var sq = QualitySettings.shadows; QualitySettings.shadows = ShadowQuality.Disable;
            try { feedCam.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] monitoring camera: " + e.Message); return; }
            finally { QualitySettings.shadows = sq; }
            if (i == 0 && feedImg != null && feedImg.image != camRT[0]) feedImg.image = camRT[0];
            if (tiles[i] != null && tiles[i].image != camRT[i]) tiles[i].image = camRT[i];
        }

        // ================================================================== the window
        VisualElement overlay, body, pin, left, right, gantt, cardB, cardT, cardF, camsCard, evCard, viewSw, track, chart, feedOver; Image photo, feedImg;
        Label headDate, hud, pinText, stripDate, stripMode, feedClock, feedNote, aiNote;
        Button playBtn; VisualElement playIcon;
        readonly List<Button> tabBtns = new List<Button>(), viewBtns = new List<Button>(), modeBtns = new List<Button>();
        readonly Image[] tiles = new Image[4]; readonly VisualElement[] tileBox = new VisualElement[4], tileOver = new VisualElement[4];
        // card of the selected work
        Label aTitle, aZone, aPlan, aFact, aDone, aDev, aScope, aSrc; VisualElement aStatusBox;
        // progress card
        Label bTitle, bFact, bPlan, bFoot, chartX0, chartX1; VisualElement bFill, bMark;
        // gantt
        class GRow { public VisualElement Row, Bars; public Label Plan, Fact, Dev; }
        readonly List<GRow> grows = new List<GRow>(); readonly List<Label> axisLabels = new List<Label>();
        // floor table
        class TRow { public VisualElement Row; public Label Plan, Fact, Dev; }
        readonly List<TRow> trows = new List<TRow>(); readonly List<int> tableWorks = new List<int>(); Label tNote, tForecast;

        void Build()
        {
            var ui = TwinUI.Instance; var mid = ui != null ? ui.Middle : null; if (mid == null || mid.panel == null) return;
            grows.Clear(); trows.Clear(); tabBtns.Clear(); viewBtns.Clear(); modeBtns.Clear(); axisLabels.Clear();
            overlay = new VisualElement(); overlay.AddToClassList("mon-dim");
            overlay.RegisterCallback<PointerDownEvent>(e => { if (e.target == overlay) Close(); });
            ui.BlockWhileHovered(overlay);
            var win = new VisualElement(); win.AddToClassList("mon-win"); overlay.Add(win);

            // ---- header: place and date, the tabs of the module, close
            var head = new VisualElement(); head.AddToClassList("mon-head"); win.Add(head);
            var logo = new VisualElement { pickingMode = PickingMode.Ignore }; logo.AddToClassList("mon-logo"); head.Add(logo);
            var place = new VisualElement { pickingMode = PickingMode.Ignore }; place.AddToClassList("mon-place"); head.Add(place);
            place.Add(new Label(L.Short + ", Alatau City") { pickingMode = PickingMode.Ignore });
            headDate = new Label { pickingMode = PickingMode.Ignore }; headDate.AddToClassList("note"); place.Add(headDate);
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; head.Add(sp);
            var tabs = new VisualElement(); tabs.AddToClassList("mon-tabs"); head.Add(tabs);
            string[] tn = { "Обзор", "График работ · 4D", "Камеры" }; string[] ti = { "layout_grid", "chart_line", "video" };
            for (int i = 0; i < tn.Length; i++)
            {
                int k = i; var b = new Button(() => SetTab(k)); b.AddToClassList("mon-tab"); b.Add(TwinUI.Icon(ti[i], 14)); var bl = new Label(tn[i]) { pickingMode = PickingMode.Ignore }; b.Add(bl);
                tabs.Add(b); tabBtns.Add(b);
            }
            var sp2 = new VisualElement { pickingMode = PickingMode.Ignore }; sp2.style.flexGrow = 1; head.Add(sp2);
            var pill = new VisualElement { pickingMode = PickingMode.Ignore }; pill.AddToClassList("mon-pill"); pill.Add(TwinUI.Icon("hard_hat", 14)); pill.Add(new Label("Мониторинг строительства") { pickingMode = PickingMode.Ignore }); head.Add(pill);
            head.Add(Widgets.Btn("×", Close, "small", "ghost"));

            // ---- body: the live view of the twin with the panels over it
            body = new VisualElement(); body.AddToClassList("mon-body"); win.Add(body);
            photo = new Image { scaleMode = ScaleMode.StretchToFill }; photo.AddToClassList("mon-photo"); body.Add(photo);
            // the analytics boxes over the picture while a site camera is shown full size
            bigOver = new VisualElement { pickingMode = PickingMode.Ignore }; bigOver.AddToClassList("mon-photo"); body.Add(bigOver);
            bigOver.generateVisualContent += ctx => { var rr2 = bigOver.contentRect; if (view == View.Cam && rr2.width > 20f) DrawBoxes(ctx.painter2D, bigBox, 0f, 0f, rr2.width, rr2.height, new Rect(0f, 0f, rr2.width, rr2.height), 2f); };
            ViewInput(photo);
            pin = new VisualElement { pickingMode = PickingMode.Ignore }; pin.AddToClassList("mon-pin"); pin.style.display = DisplayStyle.None;
            pinText = new Label { pickingMode = PickingMode.Ignore }; pin.Add(pinText);
            var stem = new VisualElement { pickingMode = PickingMode.Ignore }; stem.AddToClassList("mon-stem"); pin.Add(stem); body.Add(pin);

            // views of the 3D model (top centre) and what it shows
            var top = new VisualElement { pickingMode = PickingMode.Ignore }; top.AddToClassList("mon-top"); body.Add(top);
            viewSw = new VisualElement(); viewSw.AddToClassList("mon-seg"); top.Add(viewSw);
            foreach (var (txt, v) in new[] { ("Комплекс", View.Complex), ("Башня", View.Tower), ("Захватка", View.Floor) })
            { var vv = v; var b = Widgets.Btn(txt, () => SetView(vv), "small"); viewSw.Add(b); viewBtns.Add(b); }
            hud = new Label { pickingMode = PickingMode.Ignore }; hud.AddToClassList("mon-hud"); top.Add(hud);

            // ---- left: the selected work and its progress
            left = new VisualElement { pickingMode = PickingMode.Ignore }; left.AddToClassList("mon-col"); left.AddToClassList("mon-left"); body.Add(left);
            var ca = Card(left);
            var at = new VisualElement(); at.AddToClassList("mon-row"); at.Add(TwinUI.Icon("hard_hat", 16)); aTitle = new Label(); aTitle.AddToClassList("mon-title"); aTitle.style.whiteSpace = WhiteSpace.Normal; aTitle.style.flexShrink = 1; at.Add(aTitle); ca.Add(at);
            var az = new VisualElement(); az.AddToClassList("mon-row"); az.style.marginTop = 6; aZone = new Label(); aZone.AddToClassList("note"); az.Add(aZone);
            var azs = new VisualElement(); azs.style.flexGrow = 1; az.Add(azs); aStatusBox = new VisualElement(); az.Add(aStatusBox); ca.Add(az);
            ca.Add(FactRow("План", out aPlan)); ca.Add(FactRow("Факт / прогноз", out aFact)); ca.Add(FactRow("Выполнено", out aDone)); ca.Add(FactRow("Отклонение", out aDev));
            aScope = Para(""); ca.Add(aScope);
            aSrc = new Label(); aSrc.AddToClassList("mon-src"); aSrc.style.marginTop = 4; ca.Add(aSrc);
            var ab = new VisualElement(); ab.AddToClassList("mon-btns");
            ab.Add(Widgets.Btn("Показать в 3D", () => { Focus(); dirty = true; }, "small"));
            ab.Add(Widgets.Btn("На графике", () => SetTab(1), "small"));
            ca.Add(ab);

            cardB = Card(left);
            var h2 = new VisualElement(); h2.AddToClassList("mon-row"); h2.Add(TwinUI.Icon("chart_line", 16)); bTitle = new Label("Прогресс работы"); bTitle.AddToClassList("mon-title"); h2.Add(bTitle); cardB.Add(h2);
            var kp = new VisualElement(); kp.AddToClassList("mon-kpi"); cardB.Add(kp);
            var kf = new VisualElement(); kf.Add(new Label("Факт") { pickingMode = PickingMode.Ignore }); bFact = new Label(); bFact.AddToClassList("mon-num"); kf.Add(bFact); kp.Add(kf);
            var sp4 = new VisualElement(); sp4.style.flexGrow = 1; kp.Add(sp4);
            var kpl = new VisualElement(); kpl.style.alignItems = Align.FlexEnd; kpl.Add(new Label("План") { pickingMode = PickingMode.Ignore }); bPlan = new Label(); bPlan.AddToClassList("mon-num-s"); kpl.Add(bPlan); kp.Add(kpl);
            var bar = new VisualElement(); bar.AddToClassList("mon-bar"); bFill = new VisualElement(); bFill.AddToClassList("mon-fill"); bar.Add(bFill);
            bMark = new VisualElement(); bMark.AddToClassList("mon-mark"); bar.Add(bMark); cardB.Add(bar);
            chart = new VisualElement(); chart.AddToClassList("mon-chart"); chart.generateVisualContent += DrawChart; Scrub(chart, ChartDate); cardB.Add(chart);
            foreach (var (txt, y) in new[] { ("100%", 0f), ("50%", 0.5f), ("0%", 1f) })
            { var l = new Label(txt) { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-axis"); l.style.top = Length.Percent(y * 78f); l.style.left = 0; chart.Add(l); }
            chartX0 = new Label { pickingMode = PickingMode.Ignore }; chartX0.AddToClassList("mon-axis"); chartX0.style.bottom = 0; chartX0.style.left = 28; chart.Add(chartX0);
            chartX1 = new Label { pickingMode = PickingMode.Ignore }; chartX1.AddToClassList("mon-axis"); chartX1.style.bottom = 0; chartX1.style.right = 4; chart.Add(chartX1);
            var leg = new VisualElement(); leg.AddToClassList("mon-legend");
            leg.Add(new Label("- - План") { pickingMode = PickingMode.Ignore });
            var lf = new Label("— Факт") { pickingMode = PickingMode.Ignore }; lf.style.color = Blue; leg.Add(lf);
            var lp = new Label("··· Прогноз") { pickingMode = PickingMode.Ignore }; lp.style.color = BlueSoft; leg.Add(lp);
            var lo = new Label("| Облёт") { pickingMode = PickingMode.Ignore }; lo.style.color = Orange; leg.Add(lo);
            cardB.Add(leg);
            var foot = new VisualElement(); foot.AddToClassList("mon-row"); foot.style.marginTop = 6; foot.Add(TwinUI.Icon("triangle_alert", 14)); bFoot = new Label(); bFoot.AddToClassList("note"); bFoot.style.whiteSpace = WhiteSpace.Normal; bFoot.style.flexShrink = 1; foot.Add(bFoot); cardB.Add(foot);

            // ---- right: the tower by floors, the core camera / the four cameras
            right = new VisualElement { pickingMode = PickingMode.Ignore }; right.AddToClassList("mon-col"); right.AddToClassList("mon-right"); body.Add(right);
            cardT = Card(right);
            var e3 = new Label("ПЛАН И ФАКТ ПО ЭТАЖАМ"); e3.AddToClassList("lm-cap-h"); cardT.Add(e3);
            var t3 = new Label(IconicShape.P.Title); t3.AddToClassList("mon-big"); cardT.Add(t3);
            tNote = Para(""); cardT.Add(tNote);
            var tb = new VisualElement(); tb.AddToClassList("mon-table"); cardT.Add(tb);
            var th = new VisualElement(); th.AddToClassList("mon-tr"); th.AddToClassList("mon-th"); tb.Add(th);
            foreach (var (s, cls) in new[] { ("Работа", "w"), ("План", "n"), ("Факт", "n"), ("Разница", "d") }) th.Add(Cell(s, cls));
            tableWorks.Clear();
            for (int wi = 0; wi < works.Count && tableWorks.Count < 5; wi++) if (works[wi].Place == 0 && works[wi].Phase > 0 && works[wi].Phase <= 4) { tableWorks.Add(wi); trows.Add(TableRow(tb, wi)); }
            var pr = new VisualElement(); pr.AddToClassList("mon-forecast"); cardT.Add(pr);
            var pt = new Label("прогноз") { pickingMode = PickingMode.Ignore }; pt.AddToClassList("mon-tag"); pr.Add(pt);
            tForecast = Para(""); pr.Add(tForecast);

            cardF = Card(right);
            var h4 = new VisualElement(); h4.AddToClassList("mon-row"); h4.Add(TwinUI.Icon("video", 16)); var t4 = new Label("Видеонаблюдение · CAM-07"); t4.AddToClassList("mon-title"); h4.Add(t4);
            var sp5 = new VisualElement(); sp5.style.flexGrow = 1; h4.Add(sp5); h4.Add(Widgets.Btn("Все камеры", () => SetTab(2), "small", "ghost")); cardF.Add(h4);
            feedNote = new Label(); feedNote.AddToClassList("note"); cardF.Add(feedNote);
            var feed = new VisualElement(); feed.AddToClassList("mon-feed"); cardF.Add(feed);
            feed.RegisterCallback<ClickEvent>(_ => { camIx = 0; camYawOff = camPitchOff = 0f; view = View.Cam; dirty = true; });
            feedImg = new Image { scaleMode = ScaleMode.ScaleAndCrop, pickingMode = PickingMode.Ignore }; feedImg.AddToClassList("mon-feed-img"); feed.Add(feedImg);
            feedOver = new VisualElement { pickingMode = PickingMode.Ignore }; feedOver.AddToClassList("mon-feed-over"); feedOver.generateVisualContent += ctx => DrawFeed(ctx, feedOver, 0); feed.Add(feedOver);
            var ftop = new VisualElement { pickingMode = PickingMode.Ignore }; ftop.AddToClassList("mon-feed-top"); feedOver.Add(ftop);
            ftop.Add(new Label("   CAM-07 · REC") { pickingMode = PickingMode.Ignore });
            var fsp = new VisualElement { pickingMode = PickingMode.Ignore }; fsp.style.flexGrow = 1; ftop.Add(fsp);
            feedClock = new Label { pickingMode = PickingMode.Ignore }; ftop.Add(feedClock);
            var ai = new VisualElement(); ai.AddToClassList("mon-row"); ai.AddToClassList("mon-ai"); ai.style.marginTop = 8; ai.Add(Widgets.Dot(new Color(0.20f, 0.78f, 0.35f), true));
            aiNote = new Label(); aiNote.AddToClassList("note"); aiNote.style.whiteSpace = WhiteSpace.Normal; aiNote.style.flexShrink = 1; ai.Add(aiNote); cardF.Add(ai);

            // cameras tab: four screens and the analytics journal
            camsCard = Card(right);
            var hc = new VisualElement(); hc.AddToClassList("mon-row"); hc.Add(TwinUI.Icon("video", 16)); var tc = new Label("Камеры площадки"); tc.AddToClassList("mon-title"); hc.Add(tc); camsCard.Add(hc);
            var cn = new Label("нажмите на камеру — она откроется в главном окне"); cn.AddToClassList("note"); camsCard.Add(cn);
            var grid = new VisualElement(); grid.AddToClassList("mon-cams"); camsCard.Add(grid);
            for (int i = 0; i < 4; i++)
            {
                int k = i; var box = new VisualElement(); box.AddToClassList("mon-cam"); grid.Add(box); tileBox[i] = box;
                box.RegisterCallback<ClickEvent>(_ => { camIx = k; camYawOff = camPitchOff = 0f; camFov = 58f; view = View.Cam; dirty = true; });
                var scr = new VisualElement { pickingMode = PickingMode.Ignore }; scr.AddToClassList("mon-cam-scr"); box.Add(scr);
                tiles[i] = new Image { scaleMode = ScaleMode.ScaleAndCrop, pickingMode = PickingMode.Ignore }; tiles[i].AddToClassList("mon-feed-img"); scr.Add(tiles[i]);
                var ov = new VisualElement { pickingMode = PickingMode.Ignore }; ov.AddToClassList("mon-feed-over"); ov.generateVisualContent += ctx => DrawFeed(ctx, tileOver[k], k); scr.Add(ov); tileOver[i] = ov;
                var lab = new Label("  " + CamId[i] + " · REC") { pickingMode = PickingMode.Ignore }; lab.AddToClassList("mon-cam-id"); ov.Add(lab);
                var nm = new Label(CamName[i]) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("mon-cam-cap"); box.Add(nm);
            }
            evCard = Card(right);
            var he = new VisualElement(); he.AddToClassList("mon-row"); he.Add(TwinUI.Icon("scan_eye", 16)); var te = new Label("ИИ-видеоаналитика"); te.AddToClassList("mon-title"); he.Add(te); evCard.Add(he);
            Ev(evCard, "09:42", "CAM-07", "Работа у края плиты без страховки — прораб уведомлён, закрыто", Orange);
            Ev(evCard, "10:15", "CAM-02", "Въезд бетоновоза: 6-я машина за смену, разгрузка на площадке Б", Blue);
            Ev(evCard, "10:58", "CAM-04", "Монтаж модулей витража: 4 модуля за час, норма — 5", Orange);
            Ev(evCard, "11:20", "CAM-11", "Все в касках и жилетах, опасных зон под краном не занято", Green);

            // ---- the work schedule (Gantt) above the timeline
            gantt = new VisualElement(); gantt.AddToClassList("mon-g"); body.Add(gantt); BuildGantt(gantt);

            // ---- the 4D timeline at the bottom
            var strip = new VisualElement(); strip.AddToClassList("mon-strip"); body.Add(strip);
            playBtn = new Button(TogglePlay); playBtn.AddToClassList("mon-play"); playIcon = TwinUI.Icon("play", 16); playBtn.Add(playIcon); strip.Add(playBtn);
            var dbox = new VisualElement { pickingMode = PickingMode.Ignore }; dbox.AddToClassList("mon-sdate"); strip.Add(dbox);
            stripDate = new Label { pickingMode = PickingMode.Ignore }; stripDate.AddToClassList("mon-sdate-v"); dbox.Add(stripDate);
            stripMode = new Label { pickingMode = PickingMode.Ignore }; stripMode.AddToClassList("note"); dbox.Add(stripMode);
            track = new VisualElement(); track.AddToClassList("mon-track"); track.generateVisualContent += DrawTrack; Scrub(track, x => Mathf.Lerp(T0, T1, x)); strip.Add(track);
            for (int y = (int)T0; y <= (int)T1; y++)
            { var a = new Label(y.ToString()) { pickingMode = PickingMode.Ignore }; a.AddToClassList("mon-tick"); a.style.left = Length.Percent((y - T0) / (T1 - T0) * 100f); track.Add(a); }
            strip.Add(Widgets.Btn("К облёту", () => { playing = false; SetDate(Report); }, "small"));
            var seg = new VisualElement(); seg.AddToClassList("mon-seg"); strip.Add(seg);
            foreach (var (txt, pm) in new[] { ("Факт", false), ("План", true) })
            { var b = Widgets.Btn(txt, () => { planMode = pm; SetDate(date, true); }, "small"); seg.Add(b); modeBtns.Add(b); }

            (mid.parent ?? mid).Add(overlay);                 // the root of the interface: it carries the style sheet, the window covers the header too
            SetTab(0); Refresh();
        }

        void BuildGantt(VisualElement g)
        {
            var gh = new VisualElement(); gh.AddToClassList("mon-row"); gh.AddToClassList("mon-g-head"); g.Add(gh);
            gh.Add(TwinUI.Icon("chart_line", 16)); var gt = new Label("График работ · " + L.Short); gt.AddToClassList("mon-title"); gh.Add(gt);
            var gs = new VisualElement(); gs.style.flexGrow = 1; gh.Add(gs);
            gh.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.28f), "план"));
            gh.Add(Widgets.LegendItem(Blue, "факт"));
            gh.Add(Widgets.LegendItem(BlueSoft, "прогноз"));
            gh.Add(Widgets.LegendItem(Orange, "облёт " + Day(Report)));
            gh.Add(Widgets.LegendItem(Color.white, "дата 4D"));
            // column heads and the time axis
            var ch = new VisualElement(); ch.AddToClassList("mon-g-row"); ch.AddToClassList("mon-g-th"); g.Add(ch);
            ch.Add(GCell("Работа", "mon-g-name")); ch.Add(GCell("План", "mon-g-n")); ch.Add(GCell("Факт", "mon-g-n")); ch.Add(GCell("Откл.", "mon-g-d"));
            var axis = new VisualElement(); axis.AddToClassList("mon-g-bars"); ch.Add(axis);
            for (int y = (int)T0; y < (int)T1; y++)
                for (int q = 0; q < 4; q++)
                {
                    var a = new Label(q == 0 ? y.ToString() : "Q" + (q + 1)) { pickingMode = PickingMode.Ignore }; a.AddToClassList(q == 0 ? "mon-g-year" : "mon-g-q");
                    a.style.left = Length.Percent((y + q * 0.25f - T0) / (T1 - T0) * 100f); axis.Add(a);
                }
            Scrub(axis, x => Mathf.Lerp(T0, T1, x));
            var list = new VisualElement(); list.AddToClassList("mon-g-list"); g.Add(list);
            for (int i = 0; i < works.Count; i++)
            {
                int k = i; var w = works[i]; var gr = new GRow();
                var r = new VisualElement(); r.AddToClassList("mon-g-row"); list.Add(r); gr.Row = r;
                var nm = new VisualElement(); nm.AddToClassList("mon-g-name"); r.Add(nm);
                var code = new Label(w.Code) { pickingMode = PickingMode.Ignore }; code.AddToClassList("mon-g-code"); nm.Add(code);
                var n = new Label(w.Name) { pickingMode = PickingMode.Ignore }; n.AddToClassList("mon-g-label"); nm.Add(n);
                nm.RegisterCallback<ClickEvent>(_ => Select(k, true));
                gr.Plan = GCell("", "mon-g-n"); gr.Fact = GCell("", "mon-g-n"); gr.Dev = GCell("", "mon-g-d"); r.Add(gr.Plan); r.Add(gr.Fact); r.Add(gr.Dev);
                var bars = new VisualElement(); bars.AddToClassList("mon-g-bars"); r.Add(bars); gr.Bars = bars;
                bars.generateVisualContent += ctx => DrawBars(ctx, bars, works[k], k == sel);
                bars.RegisterCallback<PointerDownEvent>(_ => { if (sel != k) Select(k, true); }, TrickleDown.TrickleDown);
                Scrub(bars, x => Mathf.Lerp(T0, T1, x));
                grows.Add(gr);
            }
        }

        // ------------------------------------------------------------------ interaction
        void SetTab(int t)
        {
            tab = t;
            for (int i = 0; i < tabBtns.Count; i++) tabBtns[i].EnableInClassList("on", i == t);
            void D(VisualElement e, bool on) { if (e != null) e.style.display = on ? DisplayStyle.Flex : DisplayStyle.None; }
            D(cardB, t == 0); D(cardT, t == 0); D(cardF, t == 0); D(camsCard, t == 2); D(evCard, t == 2); D(gantt, t == 1);
            D(left, t != 2); D(right, t != 1);
            body?.EnableInClassList("mon-tab-g", t == 1);
            if (t == 2 && view != View.Cam) { camIx = 0; camYawOff = camPitchOff = 0f; view = View.Cam; }
            if (t != 2 && view == View.Cam) SetView(View.Floor);
            dirty = true;
        }
        void TogglePlay()
        {
            playing = !playing;
            if (playing && date >= T1 - 0.01f) SetDate(T0);
            dirty = true;
        }
        float ChartDate(float x) { ChartSpan(out float a, out float b); return Mathf.Lerp(a, b, x); }

        /// <summary>Press and drag on a time scale: the date follows the pointer (x from 0 to 1 across the element).</summary>
        void Scrub(VisualElement e, Func<float, float> toDate)
        {
            e.RegisterCallback<PointerDownEvent>(ev =>
            {
                if (ev.button != 0) return;
                e.CapturePointer(ev.pointerId); scrubbing = true; playing = false;
                SetDate(toDate(Mathf.Clamp01(ev.localPosition.x / Mathf.Max(e.layout.width, 1f)))); ev.StopPropagation();
            });
            e.RegisterCallback<PointerMoveEvent>(ev =>
            {
                if (!e.HasPointerCapture(ev.pointerId)) return;
                SetDate(toDate(Mathf.Clamp01(ev.localPosition.x / Mathf.Max(e.layout.width, 1f))));
            });
            e.RegisterCallback<PointerUpEvent>(ev => { if (e.HasPointerCapture(ev.pointerId)) { e.ReleasePointer(ev.pointerId); scrubbing = false; dirty = true; } });
            e.RegisterCallback<PointerCaptureOutEvent>(_ => { scrubbing = false; });
        }
        /// <summary>Mouse on the 3D view: drag turns it (in a camera view: looks around), the wheel brings it nearer.</summary>
        void ViewInput(VisualElement e)
        {
            Vector2 last = Vector2.zero;
            e.RegisterCallback<PointerDownEvent>(ev => { e.CapturePointer(ev.pointerId); last = ev.position; });
            e.RegisterCallback<PointerMoveEvent>(ev =>
            {
                if (!e.HasPointerCapture(ev.pointerId)) return;
                var d = (Vector2)ev.position - last; last = ev.position;
                if (view == View.Cam) { camYawOff = Mathf.Clamp(camYawOff + d.x * 0.15f, -70f, 70f); camPitchOff = Mathf.Clamp(camPitchOff + d.y * 0.12f, -40f, 40f); }
                else { yaw += d.x * 0.25f; pitch = Mathf.Clamp(pitch + d.y * 0.2f, 5f, 88f); }
            });
            e.RegisterCallback<PointerUpEvent>(ev => { if (e.HasPointerCapture(ev.pointerId)) e.ReleasePointer(ev.pointerId); });
            e.RegisterCallback<WheelEvent>(ev =>
            {
                float s = Mathf.Sign(ev.delta.y);
                if (view == View.Cam) camFov = Mathf.Clamp(camFov * (1f + 0.08f * s), 22f, 72f);
                else zoomK = Mathf.Clamp(zoomK * (1f + 0.1f * s), 0.25f, 3f);
                ev.StopPropagation();
            });
        }

        // ------------------------------------------------------------------ the numbers on screen
        void Refresh()
        {
            if (overlay == null || works.Count == 0) return;
            var w = works[sel]; var st = Stat(w, date);
            bool fc = date > Report + 0.002f;
            string when = (fc ? "прогноз на " : planMode ? "план на " : "факт на ") + Day(date);
            headDate.text = when;
            stripDate.text = Day(date);
            stripMode.text = planMode ? "показан план" : fc ? "прогноз после облёта" : "факт по облёту";
            playIcon.style.backgroundImage = new StyleBackground(Resources.Load<Texture2D>("UI/Icons/i_" + (playing ? "pause" : "play")));
            for (int i = 0; i < viewBtns.Count; i++) viewBtns[i].EnableInClassList("active", (int)view == i);
            for (int i = 0; i < modeBtns.Count; i++) modeBtns[i].EnableInClassList("active", (i == 1) == planMode);
            for (int i = 0; i < 4; i++) tileBox[i]?.EnableInClassList("on", view == View.Cam && camIx == i);
            int wf = WorkFloor(shownP);
            string vs = view == View.Complex ? "КОМПЛЕКС" : view == View.Tower ? IconicShape.P.Tower.ToUpper() : view == View.Floor ? IconicFloors.Name(Mathf.Max(focusFloor, 0)).ToUpper() : CamId[camIx] + " · " + CamName[camIx].ToUpper();
            hud.text = "4D · " + (planMode ? "ПЛАН" : fc ? "ПРОГНОЗ" : "ФАКТ") + " НА " + Day(date) + " · " + vs;

            // the selected work
            aTitle.text = w.Code + " " + w.Name;
            aZone.text = w.Zone;
            aStatusBox.Clear();
            aStatusBox.Add(st.Fact >= 0.999f ? Widgets.Status("Завершено", st.Days > 3 ? "warn" : "ok") : st.Plan <= 0f && st.Fact <= 0f ? Widgets.Status("Не начата", "info")
                : Widgets.Status(st.Days > 3 ? "Отстаёт на " + st.Days + " дн." : "В графике", Cls(st.Days)));
            aPlan.text = IconicFloors.MonthYear(PlanDate(w.A)) + " – " + IconicFloors.MonthYear(PlanDate(w.B));
            float fa = FactDate(w.A), fb = FactDate(w.B);
            aFact.text = IconicFloors.MonthYear(fa) + (fa > Report ? " (прогноз)" : "") + " – " + IconicFloors.MonthYear(fb) + (fb > Report ? " (прогноз)" : "");
            aDone.text = Pct(st.Fact) + " из " + Pct(st.Plan) + " по плану";
            aDev.text = Dev(st); aDev.EnableInClassList("bad", st.Days > 21); aDev.EnableInClassList("warn", st.Days > 3 && st.Days <= 21);
            aScope.text = w.Scope; aSrc.text = "источник факта: " + w.Src;

            // its progress
            bTitle.text = "Прогресс · " + w.Name;
            bFact.text = Pct(st.Fact); bPlan.text = Pct(st.Plan);
            bFill.style.width = Length.Percent(st.Fact * 100f); bMark.style.left = Length.Percent(st.Plan * 100f);
            bFoot.text = st.Plan <= 0f && st.Fact <= 0f ? "Работа начнётся по плану в " + IconicFloors.MonthYear(PlanDate(w.A))
                : st.Days <= 3 ? "Исполнение соответствует плану"
                : (fc ? "Прогноз: отставание " : "Отставание ") + st.Days + " дн.; " + (fb > PlanDate(w.B) + 0.01f ? "окончание сдвигается на " + IconicFloors.MonthYear(fb) : "окончание в срок");
            ChartSpan(out float ca, out float cb); chartX0.text = IconicFloors.MonthYear(ca); chartX1.text = IconicFloors.MonthYear(cb);
            chart.MarkDirtyRepaint();

            // the tower by floors (as many as the plan / the actual have passed)
            float pp = PlanP(date), fp = FactP(date);
            int nF = IconicShape.Floors;
            int framesF = Count(fp, IconicFloors.PFacade), framesP = Count(pp, IconicFloors.PFacade);
            for (int i = 0; i < trows.Count; i++)
            {
                var tw = works[tableWorks[i]]; int ph = tw.Phase + 1;                 // floors that have passed the work's phase
                int pl = Count(pp, ph), fa2 = Count(fp, ph);
                if (i == 0) { pl = Mathf.Min(nF, pl + (pl > 0 && pl < nF ? 1 : 0)); fa2 = Mathf.Min(nF, fa2 + (fa2 > 0 && fa2 < nF ? 1 : 0)); }   // the core runs a floor ahead
                int d = fa2 - pl; string cls = d >= 0 ? "ok" : d >= -1 ? "warn" : "bad";
                var r = trows[i]; r.Plan.text = pl + " эт."; r.Fact.text = fa2 + " эт."; r.Dev.text = d >= 0 ? "в срок" : d + " эт.";
                foreach (var c in new[] { "ok", "warn", "bad" }) { r.Row.EnableInClassList(c, c == cls); r.Dev.EnableInClassList(c, c == cls); }
            }
            int lag = framesP - framesF;
            tNote.text = framesF <= 0 ? "Каркас башни ещё не поднялся над фундаментом." : framesF >= nF ? "Каркас башни завершён, идут фасад и внутренние работы."
                : $"Перекрытие {framesF}-го этажа забетонировано, на {wf + 1}-м идут армирование и опалубка. По графику к {Day(date)} — {framesP}-й этаж" + (lag > 0 ? $", отставание {lag} {Floors(lag)}." : ".");
            float y0 = PlanDate(0.08f), days = (date - y0) * 365f;
            float pace = days / Mathf.Max(framesF, 1), pacePlan = days / Mathf.Max(framesP, 1);
            tForecast.text = framesF <= 0 || framesF >= nF ? "Отклонений по каркасу нет." : $"Темп каркаса — {Loc.N1(pace)} дн. на этаж при плановых {Loc.N1(pacePlan)}. Вторая смена на армировании закроет отставание к {IconicFloors.MonthYear(Report + 1.4f)}.";

            // the core camera
            int f = Mathf.Max(focusFloor, 0);
            feedNote.text = "кран № 2 · вид на " + IconicFloors.Name(f).ToLower();
            crewSeen = -1; SeenNote(0);

            // the schedule
            for (int i = 0; i < grows.Count; i++)
            {
                var s = Stat(works[i], date); var g = grows[i];
                g.Plan.text = Pct(s.Plan); g.Fact.text = Pct(s.Fact); g.Dev.text = Dev(s);
                string c = s.Plan <= 0f && s.Fact <= 0f ? "" : Cls(s.Days);
                foreach (var cc in new[] { "ok", "warn", "bad" }) g.Dev.EnableInClassList(cc, cc == c);
                g.Row.EnableInClassList("sel", i == sel);
                g.Bars.MarkDirtyRepaint();
            }
            track.MarkDirtyRepaint();
        }

        /// <summary>The label over the floor being shown (where the camera sees it).</summary>
        void Pin()
        {
            if (pin == null) return;
            bool on = view == View.Floor && focusFloor >= 0 && monRT != null;
            if (on)
            {
                var c = IconicFloors.Centre(focusFloor, out _); var wpt = model.TransformPoint(c + Vector3.up * 1.2f);
                var vp = mon.WorldToViewportPoint(wpt); on = vp.z > 0f && vp.x > 0.02f && vp.x < 0.98f && vp.y > 0.05f && vp.y < 0.95f;
                if (on)
                {
                    pin.style.left = Length.Percent(vp.x * 100f); pin.style.top = Length.Percent((1f - vp.y) * 100f);
                    var w = works[sel]; int ph = IconicFloors.Phase(focusFloor, Mathf.Min(shownP, 0.998f), H, out float fr);
                    string what = w.Phase > 0 && ph == w.Phase ? (w.Code == "2.1" ? "Ядро · подъём опалубки" : w.Phase == 1 ? "Армирование и опалубка" : w.Name) : IconicFloors.PhaseNow[ph];
                    pinText.text = IconicFloors.Name(focusFloor) + " · " + what + (ph > 0 && ph < IconicFloors.PReady ? " · " + Mathf.RoundToInt(fr * 100f) + " %" : "");
                }
            }
            pin.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
        }

        // ------------------------------------------------------------------ drawing
        static readonly Color Blue = new Color(0.36f, 0.55f, 0.94f), BlueSoft = new Color(0.36f, 0.55f, 0.94f, 0.45f), Orange = new Color(0.96f, 0.55f, 0.16f),
            Green = new Color(0.20f, 0.78f, 0.35f), PlanC = new Color(1f, 1f, 1f, 0.16f), PlanLine = new Color(1f, 1f, 1f, 0.38f);
        static void FillR(Painter2D g, Rect r, Color c)
        {
            g.fillColor = c; g.BeginPath(); g.MoveTo(r.min); g.LineTo(new Vector2(r.xMax, r.yMin)); g.LineTo(r.max); g.LineTo(new Vector2(r.xMin, r.yMax)); g.ClosePath(); g.Fill();
        }
        static void Frame(Painter2D g, Rect r, Color c, float w)
        {
            g.strokeColor = c; g.lineWidth = w; g.BeginPath(); g.MoveTo(r.min); g.LineTo(new Vector2(r.xMax, r.yMin)); g.LineTo(r.max); g.LineTo(new Vector2(r.xMin, r.yMax)); g.ClosePath(); g.Stroke();
        }
        static void VLine(Painter2D g, float x, float y0, float y1, Color c, float w) { g.strokeColor = c; g.lineWidth = w; g.BeginPath(); g.MoveTo(new Vector2(x, y0)); g.LineTo(new Vector2(x, y1)); g.Stroke(); }
        static void Dashed(Painter2D g, Vector2 a, Vector2 b, float on, float off)
        {
            float len = (b - a).magnitude; if (len < 0.5f) return; var dir = (b - a) / len;
            for (float s = 0f; s < len; s += on + off) { g.BeginPath(); g.MoveTo(a + dir * s); g.LineTo(a + dir * Mathf.Min(s + on, len)); g.Stroke(); }
        }

        /// <summary>A row of the Gantt chart: the plan (light bar), the actual up to the survey (blue), the forecast after it (pale),
        /// the survey (orange line) and the 4D date (white line).</summary>
        void DrawBars(MeshGenerationContext ctx, VisualElement e, Work w, bool selected)
        {
            var r = e.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
            float X(float d) => (d - T0) / (T1 - T0) * r.width;
            g.lineWidth = 1f;
            for (int y = (int)T0 + 1; y < (int)T1; y++) VLine(g, X(y), 0f, r.height, new Color(1f, 1f, 1f, 0.06f), 1f);
            float pa = PlanDate(w.A), pb = PlanDate(w.B), fa = FactDate(w.A), fb = FactDate(w.B);
            float h = r.height;
            FillR(g, new Rect(X(pa), h * 0.18f, Mathf.Max(X(pb) - X(pa), 2f), h * 0.3f), selected ? new Color(1f, 1f, 1f, 0.3f) : PlanC);
            float rep = Mathf.Min(fb, Report);
            if (rep > fa) FillR(g, new Rect(X(fa), h * 0.54f, Mathf.Max(X(rep) - X(fa), 2f), h * 0.3f), Blue);
            if (fb > Report)
            {
                float s = Mathf.Max(fa, Report);
                var fr = new Rect(X(s), h * 0.54f, Mathf.Max(X(fb) - X(s), 2f), h * 0.3f);
                FillR(g, fr, new Color(Blue.r, Blue.g, Blue.b, 0.18f)); Frame(g, fr, BlueSoft, 1f);
            }
            VLine(g, X(Report), 0f, h, Orange, 1.4f);
            VLine(g, X(date), 0f, h, Color.white, 1.6f);
        }

        /// <summary>The 4D timeline: years, the survey, what has been passed, the handle at the date.</summary>
        void DrawTrack(MeshGenerationContext ctx)
        {
            var r = track.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
            float X(float d) => (d - T0) / (T1 - T0) * r.width;
            float cy = r.height * 0.42f;
            g.lineWidth = 4f; g.lineCap = LineCap.Round;
            g.strokeColor = new Color(1f, 1f, 1f, 0.14f); g.BeginPath(); g.MoveTo(new Vector2(0, cy)); g.LineTo(new Vector2(r.width, cy)); g.Stroke();
            g.strokeColor = planMode ? new Color(1f, 1f, 1f, 0.6f) : Blue; g.BeginPath(); g.MoveTo(new Vector2(0, cy)); g.LineTo(new Vector2(X(date), cy)); g.Stroke();
            g.lineCap = LineCap.Butt;
            for (int y = (int)T0; y <= (int)T1; y++) VLine(g, X(y), cy + 5f, cy + 9f, new Color(1f, 1f, 1f, 0.35f), 1f);
            for (float q = T0 + 0.25f; q < T1; q += 0.25f) if (Mathf.Abs(q - Mathf.Round(q)) > 0.01f) VLine(g, X(q), cy + 5f, cy + 7f, new Color(1f, 1f, 1f, 0.18f), 1f);
            VLine(g, X(Report), cy - 9f, cy + 9f, Orange, 2f);
            g.fillColor = Color.white; g.BeginPath(); g.Arc(new Vector2(X(date), cy), 7f, 0f, 360f); g.Fill();
            g.fillColor = planMode ? new Color(0.5f, 0.5f, 0.5f) : Blue; g.BeginPath(); g.Arc(new Vector2(X(date), cy), 4f, 0f, 360f); g.Fill();
        }

        void ChartSpan(out float a, out float b)
        {
            var w = works[sel];
            a = Mathf.Min(PlanDate(w.A), FactDate(w.A)); b = Mathf.Max(PlanDate(w.B), FactDate(w.B));
            float pad = Mathf.Max((b - a) * 0.08f, 0.08f); a = Mathf.Max(T0, a - pad); b = Mathf.Min(T1, b + pad);
        }
        /// <summary>Progress of the selected work over time: plan dashed, actual solid up to the survey, forecast dotted, the 4D date.</summary>
        void DrawChart(MeshGenerationContext ctx)
        {
            var r = chart.contentRect; if (r.width < 20f || works.Count == 0) return; var g = ctx.painter2D;
            var w = works[sel]; ChartSpan(out float a, out float b);
            float L0 = 30f, B0 = 16f, W = r.width - L0 - 6f, Hh = r.height - B0 - 6f;
            Vector2 P(float d, float v) => new Vector2(L0 + (d - a) / (b - a) * W, 6f + (1f - v) * Hh);
            g.lineWidth = 1f; g.strokeColor = new Color(1f, 1f, 1f, 0.08f);
            for (int k = 0; k <= 2; k++) { float y = 6f + Hh * k / 2f; g.BeginPath(); g.MoveTo(new Vector2(L0, y)); g.LineTo(new Vector2(L0 + W, y)); g.Stroke(); }
            const int n = 48;
            float Pv(float d) => Mathf.Clamp01((PlanP(d) - w.A) / (w.B - w.A));
            float Fv(float d) => Mathf.Clamp01((FactP(d) - w.A) / (w.B - w.A));
            g.strokeColor = PlanLine; g.lineWidth = 1.4f;
            for (int i = 0; i < n; i++) { float d0 = Mathf.Lerp(a, b, i / (float)n), d1 = Mathf.Lerp(a, b, (i + 1f) / n); Dashed(g, P(d0, Pv(d0)), P(d1, Pv(d1)), 4f, 3f); }
            // actual, then forecast
            g.lineWidth = 2f;
            for (int i = 0; i < n; i++)
            {
                float d0 = Mathf.Lerp(a, b, i / (float)n), d1 = Mathf.Lerp(a, b, (i + 1f) / n);
                if (d0 < Report) { g.strokeColor = Blue; g.BeginPath(); g.MoveTo(P(d0, Fv(d0))); float e = Mathf.Min(d1, Report); g.LineTo(P(e, Fv(e))); g.Stroke(); }
                if (d1 > Report) { g.strokeColor = BlueSoft; float s = Mathf.Max(d0, Report); Dashed(g, P(s, Fv(s)), P(d1, Fv(d1)), 2f, 3f); }
            }
            if (Report > a && Report < b) VLine(g, P(Report, 0f).x, 6f, 6f + Hh, Orange, 1.4f);
            float dd = Mathf.Clamp(date, a, b); VLine(g, P(dd, 0f).x, 6f, 6f + Hh, new Color(1f, 1f, 1f, 0.7f), 1f);
            g.fillColor = Blue; g.BeginPath(); g.Arc(P(dd, Fv(dd)), 3.5f, 0f, 360f); g.Fill();
            g.fillColor = Color.white; g.BeginPath(); g.Arc(P(dd, Pv(dd)), 2.5f, 0f, 360f); g.Fill();
        }

        /// <summary>Over a site camera: scan lines, the blinking REC dot, video-analytics boxes on the crew (green = helmet and vest).</summary>
        void DrawFeed(MeshGenerationContext ctx, VisualElement over, int cam)
        {
            if (over == null) return; var r = over.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
            g.lineWidth = 1f; g.strokeColor = new Color(1f, 1f, 1f, 0.035f);
            for (float y = 0; y < r.height; y += 3f) { g.BeginPath(); g.MoveTo(new Vector2(0, y)); g.LineTo(new Vector2(r.width, y)); g.Stroke(); }
            if (Mathf.Repeat(phase + cam * 0.3f, 1.2f) < 0.7f) { g.fillColor = new Color(1f, 0.23f, 0.18f); g.BeginPath(); g.Arc(new Vector2(10f, 11f), 3.5f, 0f, 360f); g.Fill(); }
            // the boxes of the video analytics: the picture fills the screen and is cropped (ScaleAndCrop), so map through the crop
            var rt = camRT[cam]; float iw = rt != null ? rt.width : 400f, ih = rt != null ? rt.height : 225f;
            float s = Mathf.Max(r.width / iw, r.height / ih), dw = iw * s, dh = ih * s, ox = (r.width - dw) * 0.5f, oy = (r.height - dh) * 0.5f;
            DrawBoxes(g, feedBox[cam], ox, oy, dw, dh, new Rect(0f, 0f, r.width, r.height), 1.3f);
        }

        // ------------------------------------------------------------------ small builders
        static VisualElement Card(VisualElement parent) { var c = new VisualElement(); c.AddToClassList("mon-card"); parent.Add(c); return c; }
        static Label Para(string s) { var l = new Label(s) { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-para"); return l; }
        static Label Cell(string s, string cls) { var l = new Label(s) { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-td"); l.AddToClassList(cls); return l; }
        static Label GCell(string s, string cls) { var l = new Label(s) { pickingMode = PickingMode.Ignore }; l.AddToClassList(cls); return l; }
        static VisualElement FactRow(string k, out Label v)
        {
            var r = new VisualElement(); r.AddToClassList("mon-fact");
            var kl = new Label(k) { pickingMode = PickingMode.Ignore }; kl.AddToClassList("k"); r.Add(kl);
            v = new Label { pickingMode = PickingMode.Ignore }; v.AddToClassList("v"); r.Add(v); return r;
        }
        TRow TableRow(VisualElement tb, int wi)
        {
            var w = works[wi]; var t = new TRow();
            var r = new VisualElement(); r.AddToClassList("mon-tr"); tb.Add(r); t.Row = r;
            r.RegisterCallback<ClickEvent>(_ => Select(wi, true));
            var c = new VisualElement(); c.AddToClassList("w"); c.AddToClassList("mon-td"); r.Add(c);
            var wl = new Label(w.Code + " " + w.Name) { pickingMode = PickingMode.Ignore }; wl.AddToClassList("mon-work"); c.Add(wl);
            var sl = new Label(w.Src) { pickingMode = PickingMode.Ignore }; sl.AddToClassList("mon-src"); c.Add(sl);
            t.Plan = Cell("", "n"); t.Fact = Cell("", "n"); t.Dev = Cell("", "d"); r.Add(t.Plan); r.Add(t.Fact); r.Add(t.Dev);
            return t;
        }
        static void Ev(VisualElement card, string time, string cam, string text, Color c)
        {
            var r = new VisualElement(); r.AddToClassList("mon-row"); r.AddToClassList("mon-ai"); r.style.marginTop = 8; r.Add(Widgets.Dot(c, true));
            var l = new Label(time + " · " + cam + " — " + text) { pickingMode = PickingMode.Ignore }; l.AddToClassList("note"); l.style.whiteSpace = WhiteSpace.Normal; l.style.flexShrink = 1; r.Add(l);
            card.Add(r);
        }
    }
}
