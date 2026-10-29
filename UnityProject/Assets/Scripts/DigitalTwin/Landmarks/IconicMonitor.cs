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
    public partial class IconicMonitor : MonoBehaviour
    {
        public static IconicMonitor Instance;
        public static bool Open => Instance != null && Instance.open;
        /// <summary>Frame in which the window was closed (its Esc must not also take the camera out of the tower).</summary>
        public static int ClosedFrame = -10;
        /// <summary>Date of the last survey — the "today" of the monitoring: 13 March of the year after the start (13.03.2028 for
        /// Iconic Complex, 13.03.2030 for KAIST). After it the actual is a forecast. T0 … T1: the span of the timeline.</summary>
        float Report = 2028f + 72f / 365f, T0 = 2026f, T1 = 2031f;
        const float Speed = 0.25f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Iconic Complex · monitoring").AddComponent<IconicMonitor>(); }
        void Awake() { Instance = this; }

        // ================================================================== the schedule
        /// <summary>A work of the schedule: its span [A, B] in the progress of its building (Part: index in Landmark.Parts); Phase = floor
        /// phase it follows (tower works); Place: 0 the floor where the work goes on, 1 a part of the site (Focus: local point, distance,
        /// pitch), 5 the whole tower. Sum: the summary row of a building in the schedule of the whole complex. Core: the core of the tower.</summary>
        class Work { public string Code, Name, Zone, Scope, Src; public float A, B; public int Phase, Place, Part; public bool Sum, Core; public Vector3 Focus; public float FDist = 300f, FPitch = 36f; }
        readonly List<Work> works = new List<Work>();
        /// <summary>The rows shown now: the buildings (the whole complex) or the works of the selected building (indices in works).</summary>
        readonly List<int> vis = new List<int>();
        Landmark L; float H = 272f; int curPart;
        /// <summary>The tower of the complex (followed floor by floor) and a building of it by index.</summary>
        int TI => L.Main;
        LPart Pt(int i) => L.Parts[Mathf.Clamp(i, 0, L.Parts.Count - 1)];

        readonly float[] tt = new float[7];
        float PhStart(int k) { IconicFloors.Times(0, H, tt); return k == 2 ? 0.25f : tt[k - 1]; }          // the facade line leaves the ground at 25 %
        float PhEnd(int k) { IconicFloors.Times(IconicShape.Levels - 1, H, tt); return tt[k]; }
        Work W(string code, string name, string zone, float a, float b, int phase, int place, string scope, string src)
        { var w = new Work { Code = code, Name = name, Zone = zone, A = a, B = Mathf.Max(b, a + 0.01f), Phase = phase, Place = place, Scope = scope, Src = src, Part = curPart }; works.Add(w); return w; }
        void At(Work w, float x, float y, float z, float dist, float pitch) { w.Focus = new Vector3(x, y, z); w.FDist = dist; w.FPitch = pitch; }
        Work AtPart(Work w) { var p = Pt(w.Part); At(w, p.Focus.x, p.Focus.y, p.Focus.z, p.Dist, p.Pitch); return w; }
        void MakeWorks()
        {
            works.Clear();
            // the summary row of every building: the master schedule of the complex
            for (int i = 0; i < L.Parts.Count; i++)
            {
                var p = L.Parts[i]; curPart = i;
                var w = AtPart(W((i + 1).ToString(), p.Name, p.Use, 0f, 1f, 0, 1, p.Size + " · " + p.Use, "сводный график объекта")); w.Sum = true;
            }
            if (L.Id == "kaist") MakeKaist(); else MakeIconic();
        }
        // ---- the works of the buildings that are not followed floor by floor: each building is put up in its own real order, and the
        // spans are the stage windows of its pieces in the model (Wbs), so a work in the schedule is exactly what rises on the 3D model
        /// <summary>A work of building `part` over [a, b] of its progress, shown at local point (x, y, z) (NaN x = the building's own view).</summary>
        Work Wk(int part, int n, string name, float a, float b, string scope, string src, float x = float.NaN, float y = 0f, float z = 0f, float dist = 0f, float pitch = 34f)
        {
            curPart = part; var p = Pt(part);
            var w = W((part + 1) + "." + n, name, p.Name, a, b, 0, 1, scope, src);
            if (float.IsNaN(x)) AtPart(w); else At(w, x, y, z, dist > 0f ? dist : p.Dist * 0.7f, pitch);
            return w;
        }
        Work Wk(int part, int n, string name, Vector2 span, string scope, string src, float x = float.NaN, float y = 0f, float z = 0f, float dist = 0f, float pitch = 34f)
            => Wk(part, n, name, span.x, span.y, scope, src, x, y, z, dist, pitch);
        // a piece rises in the first 60 % of its window and gets its skin from 30 to 90 % (as the shader stages it)
        static Vector2 Rise(Vector2 w) => new Vector2(w.x, w.x + 0.6f * (w.y - w.x));
        static Vector2 Skin(Vector2 w) => new Vector2(w.x + 0.3f * (w.y - w.x), w.x + 0.9f * (w.y - w.x));
        const string Fly = "облёт", Geo = "облёт · геодезическая съёмка", Hid = "акты скрытых работ", Conc = "облёт · датчики прочности бетона",
            Fore = "отметка прораба", Plan = "по графику", Scan = "облёт · лазерное сканирование";

        void MakeIconic()
        {
            curPart = TI; string T = Pt(TI).Name;
            // T1: the tower is followed floor by floor; the core leads the slabs by a floor, the facade starts at 25 % from the ground
            At(W("1.1", "Ограждение и котлован", T, 0f, 0.06f, 0, 1, "Ограждение площадки, стена в грунте, котлован под башню и подземный паркинг, водопонижение", Geo), -84f, 2f, 46f, 230f, 42f);
            At(W("1.2", "Сваи и фундаментная плита", T, 0.03f, 0.085f, 0, 1, "Буронабивные сваи, плита башни 4 м, бетон В40, четыре захватки с непрерывным бетонированием", Hid), -84f, 2f, 46f, 200f, 46f);
            W("1.3", "Ядро: самоподъёмная опалубка", T, 0.072f, PhEnd(1) - 0.012f, 1, 0, "Монолитное ядро у вертикальной грани; самоподъёмная опалубка идёт на этаж впереди перекрытий", Scan).Core = true;
            W("1.4", "Перекрытия и колонны", T, PhStart(1), PhEnd(1), 1, 0, "Колонны и плиты 56 этажей и двух технических уровней, бетон В40, захватка — один этаж", Conc);
            W("1.5", "Фасад: витраж с ромбической сеткой", T, PhStart(2), PhEnd(2), 2, 0, "Витраж с ромбической сеткой световых линий и белые плиты-консоли на каждом этаже, монтаж краном и с фасадного подъёмника", "отметка прораба · облёт");
            At(W("1.6", "Вершина-лезвие и шпиль", T, PhEnd(1) - 0.05f, PhEnd(2) - 0.02f, 0, 1, "Сужение башни выше 214 м до лезвия шириной 5 м, стальной шпиль и заградительный огонь на 272 м", Scan), -59f, 250f, 45f, 260f, 10f);
            W("1.7", "Инженерные сети", T, PhStart(3), PhEnd(3), 3, 0, "Вентиляция, спринклеры, холодоснабжение, кабельные лотки", Fore);
            W("1.8", "Перегородки", T, PhStart(4), PhEnd(4), 4, 0, "Каркас из профиля, гипсокартон в два слоя, шпаклёвка", Fore);
            W("1.9", "Отделка", T, PhStart(5), PhEnd(5), 5, 0, "Полы, потолки, окраска, отделка лобби и общественных зон", Fore);
            At(W("1.10", "Демонтаж кранов и входная группа", T, PhEnd(2) - 0.02f, PhEnd(2) + 0.06f, 0, 1, "Разборка башенных кранов сверху вниз, входная группа со стороны площади", Fly), -84f, 12f, 9f, 160f, 24f);
            W("1.11", "Оснащение и мебель", T, PhStart(6), PhEnd(6), 6, 0, "Мебель офисов и резиденций, оборудование ресторанов и спа", Plan);
            W("1.12", "Пусконаладка и сдача", T, 0.90f, 1f, 0, 5, "Пусконаладка инженерных систем, приёмка и ввод в эксплуатацию", Plan);

            // T2: the stepped hotel; its levels step back from the far end, so the lower terraces are sealed while the frame still rises
            Wk(1, 1, "Котлован и водопонижение", 0f, 0.05f, "Котлован отеля, крепление стен, водопонижение", Geo);
            Wk(1, 2, "Фундаментная плита", 0.03f, 0.09f, "Плита на сваях под отель, бетон В35", Hid);
            Wk(1, 3, "Каркас: уровни 1–10", 0.08f, 0.40f, "Монолитный каркас отеля до 37 м, ядро у грани к башне на этаж впереди", Conc, 50f, 20f, 42f);
            Wk(1, 4, "Каркас: уровни 11–21 и вершина", 0.38f, 0.72f, "Уступы до 78 м, вершина у грани к башне", Conc, 12f, 60f, 42f);
            Wk(1, 5, "Витраж за ламелями", 0.25f, 0.90f, "Витражи номеров уровень за уровнем, золотистые ламели, следом за каркасом на 3–4 уровня", "отметка прораба · облёт");
            Wk(1, 6, "Террасы: гидроизоляция и озеленение", Wbs.T2Terr, "Гидроизоляция уступов, плиты-карнизы и кашпо с зеленью по краям террас — нижние раньше верхних", Fly, 55f, 30f, 42f);
            Wk(1, 7, "Золотые рёбра у башни", Wbs.T2Cascade, "Золотистые рёбра буквой V на грани к башне — вторая половина «ворот»", Fly, -12f, 40f, 42f, 160f, 30f);
            Wk(1, 8, "Номера, рестораны и спа", 0.50f, 0.96f, "Инженерия гостиничного стандарта, отделка 220 номеров, оборудование ресторанов и спа", Fore);
            Wk(1, 9, "Пусконаладка и открытие", 0.92f, 1f, "Пусконаладка, сертификация гостиничного оператора, мягкое открытие", Plan);

            // the pavilions: the parking and the pit in one go; their roofs slope up from the plaza in a planted wedge
            foreach (int r in new[] { 2, 3 })
            {
                bool east = r == 2; float fx = east ? -78f : 78f, fz = -58f;
                Wk(r, 1, "Котлован и подземный паркинг", 0f, 0.12f, "Котлован, монолитный паркинг в два уровня под павильоном", Geo);
                Wk(r, 2, "Каркас павильона", Rise(Wbs.RHigh), "Колонны и плиты торговых этажей, наклонные балки кровли с большими пролётами", Conc, fx, 8f, fz);
                Wk(r, 3, "Наклонная зелёная кровля", Rise(Wbs.RLow), east ? "Кровля-клин поднимается от площади до 32 м: гидроизоляция, грунт, газон и кустарник" : "Кровля-клин поднимается от площади до 22 м: гидроизоляция, грунт, газон и кустарник", Fly, fx, 20f, fz);
                Wk(r, 4, "Витрины и деревянный софит", Skin(Wbs.RHigh).x, Skin(Wbs.RLow).y, "Витрины галереи к площади, деревянный подшивной потолок козырька", "отметка прораба · облёт");
                if (east) Wk(r, 5, "Бассейн на террасе", Wbs.RPool, "Бассейн, настил и шезлонги на террасе восточного павильона", Fly, -63f, 6f, -50f, 160f, 44f);
                else Wk(r, 5, "Сад на кровле", Wbs.RGarden, "Дорожки, газон и деревья на кровле западного павильона", Fly, fx, 12f, fz, 160f, 44f);
                Wk(r, 6, east ? "Галерея: эскалаторы и инженерия" : "Фуд-холл и инженерия", 0.45f, 0.95f, east ? "Эскалаторы, вентиляция торговых площадей, пожарная автоматика" : "Вытяжка фуд-холла, вентиляция, пожарная автоматика", Fore);
                Wk(r, 7, "Отделка арендаторов и открытие", 0.85f, 1f, "Отделка помещений арендаторами, приёмка, открытие", Plan);
            }

            // the plot: the networks first, then the paving, the lawn islands with their groves, lamps and benches, the trees along the edge last (spring)
            Wk(4, 1, "Подземные сети и основание", 0f, 0.30f, "Ливнёвка, полив, кабели освещения, щебёночное основание под мощение", Hid);
            Wk(4, 2, "Мощение участка", Wbs.GProm, "Светлый гранит по площади и вокруг павильонов", Fly);
            Wk(4, 3, "Газоны и сад", Wbs.GAllee, "Газоны, цветники и рощи сада у площади", Fly, 0f, 1f, -60f, 160f, 50f);
            Wk(4, 4, "Амфитеатр, фонари и скамьи", Wbs.GSquare, "Ступени амфитеатра площади, зонтики, фонари и скамьи", Fly, 23f, 1f, -44f, 200f, 46f);
            Wk(4, 5, "Деревья по краю участка", Wbs.GTrees, "Деревья в решётках по краю участка — весной", Plan);
        }
        /// <summary>KAIST campus: the library and research tower (its floors are followed like the Iconic tower), the main hall lifted on
        /// columns, the laboratory comb, the curved north block, the sports oval and the park with the lake laid out first.</summary>
        void MakeKaist()
        {
            curPart = TI; string T = Pt(TI).Name;
            At(W("1.1", "Котлован башни", T, 0f, 0.06f, 0, 1, "Ограждение площадки башни, котлован, водопонижение", Geo), 150f, 2f, 20f, 220f, 46f);
            At(W("1.2", "Фундаментная плита", T, 0.035f, 0.09f, 0, 1, "Плита башни, бетон В35, две захватки", Hid), 150f, 2f, 20f, 200f, 50f);
            W("1.3", "Монолитное ядро", T, 0.072f, PhEnd(1) - 0.012f, 1, 0, "Ядро с лифтами и лестницами; скользящая опалубка идёт на этаж впереди перекрытий", Scan).Core = true;
            W("1.4", "Перекрытия и колонны", T, PhStart(1), PhEnd(1), 1, 0, "Колонны и плиты 13 этажей и технического уровня, западный фасад с наклоном (от 40 до 32 м), бетон В35", Conc);
            W("1.5", "Фасад", T, PhStart(2), PhEnd(2), 2, 0, "Бирюзовый витраж с белыми поясами перекрытий, вертикальные ламели на восточном фасаде, монтаж с фасадного подъёмника", "отметка прораба · облёт");
            W("1.6", "Инженерные сети", T, PhStart(3), PhEnd(3), 3, 0, "Вентиляция, спринклеры, слаботочные сети библиотеки и лабораторий", Fore);
            W("1.7", "Перегородки", T, PhStart(4), PhEnd(4), 4, 0, "Лабораторные боксы, читальные залы, аудитория", Fore);
            W("1.8", "Отделка", T, PhStart(5), PhEnd(5), 5, 0, "Полы, акустические потолки, отделка вестибюля и аудитории", Fore);
            W("1.9", "Оснащение, кровельный сад и пирамида", T, PhStart(6), PhEnd(6), 6, 0, "Стеллажи библиотеки, лабораторная мебель, сад на кровле, стеклянная пирамида-фонарь", Plan);
            W("1.10", "Пусконаладка и сдача", T, 0.90f, 1f, 0, 5, "Пусконаладка инженерных систем, приёмка и ввод в эксплуатацию", Plan);

            // the main hall: a glass box lifted on columns — columns, the transfer slab at +10 m, the steel box on it, then skin and roof
            const float mx = -20f, mz = -122f;
            Wk(1, 1, "Сваи и ростверки", 0f, 0.10f, "Буронабивные сваи под колонны, ростверки, плита вестибюля", Hid);
            Wk(1, 2, "Колонны вестибюля", Wbs.MCols, "26 белых колонн высотой 9 м, сталь в бетонной оболочке", Conc, mx, 5f, mz, 200f, 22f);
            Wk(1, 3, "Плита-платформа на +10 м", Wbs.MSlab, "Монолитная плита-платформа с белым софитом — на ней стоит весь объём", Conc, mx, 10f, mz, 220f, 26f);
            Wk(1, 4, "Стальной каркас объёма 150 × 56 м", Rise(Wbs.MBox), "Стальные фермы и колонны объёма от +10 до +28 м", Scan, mx, 20f, mz);
            Wk(1, 5, "Синий витраж и белая сетка", Wbs.MGrid, "Синий витраж, белые стойки и ригели фасадной сетки", "отметка прораба · облёт", mx, 20f, mz);
            Wk(1, 6, "Кровля и три пирамиды", Wbs.MRoof, "Карниз, мембранная кровля, три стеклянные пирамиды-фонаря", Fly, mx, 32f, mz, 220f, 40f);
            Wk(1, 7, "Стеклянный вестибюль", Wbs.MLobby, "Остекление вестибюля под платформой, входные группы", Fore, mx, 5f, mz, 180f, 16f);
            Wk(1, 8, "Аудитории и зал на 1 200 мест", 0.55f, 0.95f, "Инженерия, отделка аудиторий, сцена и кресла зала", Fore);
            Wk(1, 9, "Терраса, лестница и пандус", Wbs.MTerr, "Белая терраса вдоль фасада, парадная лестница и пандус", Fly, mx, 3f, -89f, 180f, 30f);
            Wk(1, 10, "Площадь с бассейном и фонтанами", Wbs.MPlaza, "Мощение площади, бассейн, струи и посадки", Fly, mx, 1f, -62f, 180f, 40f);

            // laboratories: the spine first, then the three wings one after another (south to north), the courts last
            string[] wing = { "А · южное", "Б · среднее", "В · северное" };
            Wk(2, 1, "Фундаменты хребта и крыльев", 0f, 0.10f, "Плита хребта и ленточные фундаменты крыльев, приямки под оборудование", Hid);
            Wk(2, 2, "Корпус-хребет 190 м", Wbs.LSpine, "Каркас и витраж корпуса-хребта с ламелями, технические этажи", Conc, -178f, 9f, 25f);
            for (int i = 0; i < 3; i++)
                Wk(2, 3 + i, "Крыло " + wing[i], Wbs.LWing[i], "Ступенчатое крыло до " + (i == 1 ? "14,5" : "12,5") + " м, каркас, витраж, зелёная кровля", Conc, -140f, 7f, -45f + i * 60f, 180f, 34f);
            Wk(2, 6, "Чистые помещения и лабораторные сети", 0.50f, 0.95f, "Вентиляция чистых помещений, газы, лабораторные сети, монтаж оборудования", Fore);
            Wk(2, 7, "Озеленённые дворы", Wbs.LCourts, "Дорожки и деревья во дворах между крыльями", Fly, -140f, 1f, 0f, 200f, 44f);

            // the north block: the arc is cast in four sectors from the west end, the green roof follows the last one
            Wk(3, 1, "Фундаменты по дуге", 0f, 0.10f, "Плита по дуге радиусом 170 м, четыре захватки", Hid);
            for (int i = 0; i < 4; i++)
            {
                float an = (122f - (i + 0.5f) * 16f) * Mathf.Deg2Rad;
                Wk(3, 2 + i, $"Захватка {i + 1}: каркас и витраж", Wbs.NSector[i], "Каркас, белые ламели и изогнутый витраж — четыре секции дуги" + (i == 0 ? " (с западного конца)" : ""), Conc,
                    -15f + Mathf.Cos(an) * 168f, 9f, -40f + Mathf.Sin(an) * 168f, 170f, 30f);
            }
            Wk(3, 6, "Зелёная кровля", Wbs.NRoof, "Гидроизоляция и озеленение кровли по всей дуге", Fly);
            Wk(3, 7, "Аудитории и классы", 0.55f, 0.97f, "Инженерия и отделка 120 аудиторий", Fore);
            Wk(3, 8, "Дорожки к озеру и сдача", 0.92f, 1f, "Дорожки от корпуса к озеру, приёмка", Plan);

            // sports: drainage first, the stand and its canopy, then the track and the pitch
            Wk(4, 1, "Дренаж и основание поля", 0f, 0.15f, "Дренаж, щебёночное и асфальтовое основание дорожек и поля", Hid);
            Wk(4, 2, "Сборная трибуна", Rise(Wbs.SStand), "Сборная железобетонная трибуна на 1 200 мест", Conc, 140f, 3f, -84f, 150f, 26f);
            Wk(4, 3, "Стальной навес трибуны", Wbs.SCanopy, "Стальные колонны и навес над трибуной", Fly, 140f, 6f, -84f, 150f, 26f);
            Wk(4, 4, "Раздевалки под трибуной", 0.40f, 0.90f, "Раздевалки, душевые, медпункт под трибуной", Fore);
            Wk(4, 5, "Беговые дорожки", Wbs.STrack, "Полиуретановое покрытие восьми беговых дорожек", Fly);
            Wk(4, 6, "Газон поля и мачты освещения", Wbs.SPitch, "Искусственный газон, разметка, мачты освещения", Plan);

            // the park: laid out first, in a few months, so the campus is green before the buildings rise
            Wk(5, 1, "Вертикальная планировка и дренаж", 0f, 0.25f, "Срезка и подсыпка грунта, дренаж, сети полива и освещения", Geo);
            Wk(5, 2, "Чаша озера, остров и фонтаны", Wbs.PLake, "Котлован и гидроизоляция чаши, берега, остров, высокий фонтан", Fly, -15f, 1f, -5f, 220f, 46f);
            Wk(5, 3, "Дорожки и мостик на остров", Wbs.PPaths, "Кольцевая дорожка, дорожки к корпусам, мостик на остров", Fly);
            Wk(5, 4, "Фонари и малые фонтаны", Wbs.PLamps, "Фонари вокруг озера, кольцо малых струй", Fly, -15f, 1f, -5f, 200f, 40f);
            Wk(5, 5, "Газоны, аллеи и рощи", Wbs.PTrees, "Газон по всему кампусу, двойная аллея по периметру, рощи у озера", Plan);
        }

        // plan = the stage model of each building (its own dates); actual = the plan delayed by the building's lag in years: it builds up
        // during the works, at the survey it is the measured delay; after it the forecast closes it (a second shift) or keeps it (a risk)
        float PlanP(int i, float d) => LandmarkSystem.PlanPart(L, i, d);
        float DelayAt(int i, float d)
        {
            var p = Pt(i); if (Mathf.Abs(p.Delay) < 1e-5f) return 0f;
            float up = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((d - (p.A + 0.1f)) / 0.9f));
            float down = d <= Report || !p.Recover ? 1f : Mathf.Clamp01(1f - (d - Report) / 1.4f);
            return p.Delay * up * down;
        }
        float FactP(int i, float d) => PlanP(i, d - DelayAt(i, d));
        float ShownP(int i, float d) => planMode ? PlanP(i, d) : FactP(i, d);
        float PlanDate(int i, float p) { var t = Pt(i); return t.A + p * (t.B - t.A); }
        float FactDate(int i, float p)
        {
            p = Mathf.Max(p, 1e-4f); float a = T0 - 2f, b = T1 + 3f;
            for (int k = 0; k < 30; k++) { float m = (a + b) * 0.5f; if (FactP(i, m) >= p) b = m; else a = m; }
            return b;
        }
        // the tower
        float PlanP(float d) => PlanP(TI, d);
        float FactP(float d) => FactP(TI, d);
        float PlanDate(float p) => PlanDate(TI, p);
        struct St { public float Plan, Fact; public int Days; }
        St Stat(Work w, float d)
        {
            int i = w.Part; float pp = PlanP(i, d), fp = FactP(i, d);
            var s = new St { Plan = Mathf.Clamp01((pp - w.A) / (w.B - w.A)), Fact = Mathf.Clamp01((fp - w.A) / (w.B - w.A)) };
            if (s.Fact >= 0.999f) s.Days = Mathf.RoundToInt((FactDate(i, w.B) - PlanDate(i, w.B)) * 365f);
            else if (s.Plan <= 0f && s.Fact <= 0f) s.Days = 0;
            else s.Days = Mathf.RoundToInt((d - PlanDate(i, w.A + s.Fact * (w.B - w.A))) * 365f);
            return s;
        }
        /// <summary>A building at date d: plan and actual progress, the planned and the forecast hand-over, the delay now in days
        /// (negative = ahead), the class and the words for it.</summary>
        struct OS { public float Plan, Fact, PlanEnd, FactEnd; public int Days, EndDays; public string Cls, Text, Chip; }
        OS Obj(int i, float d)
        {
            var o = new OS { Plan = PlanP(i, d), Fact = FactP(i, d), PlanEnd = PlanDate(i, 1f), FactEnd = FactDate(i, 1f) };
            o.EndDays = Mathf.RoundToInt((o.FactEnd - o.PlanEnd) * 365f);
            if (o.Fact >= 0.999f)
            {
                o.Days = o.EndDays; o.Cls = o.Days > 21 ? "bad" : o.Days > 3 ? "warn" : "ok";
                o.Text = "Введён " + IconicFloors.MonthYear(o.FactEnd) + (o.Days > 3 ? $" · позже на {o.Days} дн." : o.Days < -3 ? $" · раньше на {-o.Days} дн." : " · в срок"); o.Chip = "введён";
            }
            else if (o.Fact <= 0f && o.Plan <= 0f) { o.Days = 0; o.Cls = "muted"; o.Text = "Старт по плану — " + IconicFloors.MonthYear(Pt(i).A); o.Chip = "старт " + IconicFloors.MonthYear(Pt(i).A); }
            else
            {
                o.Days = Mathf.RoundToInt(DelayAt(i, d) * 365f); o.Cls = o.Days > 21 ? "bad" : o.Days > 3 ? "warn" : "ok";
                o.Text = o.Days > 3 ? $"Отстаёт на {o.Days} дн." : o.Days < -3 ? $"Опережает на {-o.Days} дн." : "В графике";
                o.Chip = Pct(o.Fact) + (o.Days > 3 ? " · −" + o.Days + " дн." : o.Days < -3 ? " · +" + (-o.Days) + " дн." : "");
            }
            return o;
        }
        static Color ClsColor(string c) => c == "ok" ? new Color(0.20f, 0.78f, 0.35f) : c == "warn" ? new Color(0.96f, 0.65f, 0.14f) : c == "bad" ? new Color(1f, 0.35f, 0.31f) : new Color(0.55f, 0.55f, 0.55f);
        float Capex() { float s = 0f; foreach (var p in L.Parts) s += p.Capex; return s; }
        /// <summary>The works done in the complex at date d, at the prices of the estimate (Spend: by the cost items of every building).</summary>
        float Spent(float d, bool fact) { float s = 0f; for (int i = 0; i < L.Parts.Count; i++) s += L.Parts[i].Capex * Spend(i, fact ? FactP(i, d) : PlanP(i, d)); return s; }
        static string Usd(float m) => m >= 1000f ? "$" + Loc.N1(m / 1000f) + " млрд" : "$" + Mathf.RoundToInt(m) + " млн";
        static string Cls(int days) => days <= 3 ? "ok" : days <= 21 ? "warn" : "bad";
        static string Dev(St s) => s.Plan <= 0f && s.Fact <= 0f ? "—" : s.Days <= 3 ? "в срок" : "−" + s.Days + " дн.";
        static string Pct(float v) => Mathf.RoundToInt(v * 100f) + "\u00A0%";
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
        enum View { Complex, Tower, Floor, Cam, Plan }
        bool open, wasInside, playing, planMode; int prevYear = -1, tab, sel = 3, camIx;
        float date, shownP, uiT, floorT, phase;
        View view = View.Floor; int focusFloor = -1;
        /// <summary>The building looked at (index in Landmark.Parts), −1 = the whole complex.</summary>
        int obj = -1;
        Func<Landmark, int, float, float> shiftFn;
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
            RegisterSources();
            // the summary of the other object is computed now, while the window is closed (the AI assistant may ask for it)
            foreach (var oid in new[] { "iconic", "kaist" }) if (oid != id && !sumCache.ContainsKey(oid)) Dry(oid);
            L = ls.Get(id); if (L == null || L.Parts == null || L.Main < 0) return; H = L.Height;
            // the survey shown first is the one in the middle of the works (MakeSurveys snaps it to a survey date); the list runs to the handover
            Report = L.Begin + 0.5f * (L.Finish - L.Begin); int stage = Mathf.FloorToInt(Report); T0 = Mathf.Floor(L.Begin); T1 = Mathf.Max(Mathf.Ceil(L.Finish + 0.05f), L.EndYear + 1f);
            var lm = L; shiftFn = (l, i, y) => l == lm ? DelayAt(i, y) : 0f;
            prevYear = TwinState.Year;
            if (TwinState.Year != stage) TwinState.Year = stage;
            wasInside = IconicInterior.Active && IconicShape.P.Id == id;
            if (!wasInside) ii.Enter(id);
            if (!IconicInterior.Active || IconicShape.P.Id != id) { RestoreYear(); return; }
            model = ls.ModelOf(id); main = Camera.main; if (model == null || main == null) { RestoreYear(); return; }
            MakeModel(); sumCache[id] = Collect(); ctlWeek = 0; chgMode = 0; msgMail = false; defMode = 1; crewPeak = -1f; ganttOn = false; d4Plan = false; svPlan = false; svTool = 0; rN = 0; vidGroup = 0;
            open = true; playing = false; planMode = false; scrubbing = false; tab = 0; date = Report; obj = -1;
            focusFloor = -1; floorT = 0f; uiT = 0f; zoomK = 1f; camYawOff = camPitchOff = 0f; camFov = 58f;
            IconicInterior.Suspended = true; ii.HidePanel();
            SetDate(date, true);
            // the monitoring camera starts where the city camera is and flies to the working floor
            if (mon == null) { var g = new GameObject("Iconic monitoring · view"); g.transform.SetParent(transform, false); mon = g.AddComponent<Camera>(); mon.enabled = false; }
            mon.CopyFrom(main); mon.ResetProjectionMatrix(); mon.orthographic = false; mon.fieldOfView = 40f; mon.nearClipPlane = 0.5f; mon.farClipPlane = 40000f; mon.depth = main.depth - 1;
            monMask = mon.cullingMask; monClear = mon.clearFlags; monBg = mon.backgroundColor;
            curPos = main.transform.position; curRot = main.transform.rotation;
            yaw = main.transform.eulerAngles.y + 25f;
            SelectObj(-1, true);
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
            if (mon != null) { mon.enabled = false; mon.targetTexture = null; mon.orthographic = false; }
            Isolate(false); Shader.SetGlobalFloat(BimId, 0f); Shader.SetGlobalFloat(DiffId, 0f);
            if (L != null) LandmarkSystem.Instance?.DiffFrom(L.Id, -1f, -1f); svDiff = false; diffY0 = diffY1 = -2f;
            LandmarkSystem.YearOverride = -1f; LandmarkSystem.FactShift = null; LandmarkSystem.HiObj = null; LandmarkSystem.HiPart = -1;
            HideRigs(); RestoreYear();
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
        // ------------------------------------------------------------------ the recorded video (TwinTour video mode)
        float playStop = -1f;
        public void VideoTab(int t) { if (open) SetTab(t); }
        /// <summary>The 4D schedule plays from <paramref name="back"/> years before the survey date up to it and stops there.</summary>
        public void VideoPlay(float back) { if (!open) return; SetDate(Report - back, true); playStop = Report; playing = true; dirty = true; }
        void RestoreYear() { if (prevYear > 0 && TwinState.Year != prevYear) TwinState.Year = prevYear; prevYear = -1; }
        void OnDestroy() { if (monRT != null) monRT.Release(); if (monRT2 != null) monRT2.Release(); if (bgRT != null) bgRT.Release(); foreach (var rt in camRT) if (rt != null) rt.Release(); }

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
        }
        void Unfreeze()
        {
            if (bgImg != null) { bgImg.RemoveFromHierarchy(); bgImg = null; }
            if (main != null) { main.cullingMask = mainMask; main.clearFlags = mainClear; main.backgroundColor = mainBg; }
        }

        // ------------------------------------------------------------------ the date (4D)
        void SetDate(float d, bool force = false)
        {
            d = Mathf.Clamp(d, T0, T1);
            if (!force && Mathf.Abs(d - date) < 1e-5f) return;
            date = d;
            shownP = planMode ? PlanP(d) : FactP(d);
            // the city as of the date; the buildings of the complex as of the plan, or delayed by their actual lag
            LandmarkSystem.YearOverride = d; LandmarkSystem.FactShift = planMode ? null : shiftFn;
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
        /// <summary>Looks at building i of the complex (−1 = the whole complex): the schedule shows its works (or the buildings), the
        /// building is outlined in the view, the camera flies to it (the tower: to its working floor).</summary>
        void SelectObj(int i, bool focus)
        {
            obj = Mathf.Clamp(i, -1, L.Parts.Count - 1);
            LandmarkSystem.HiObj = obj >= 0 ? L.Id : null; LandmarkSystem.HiPart = obj;
            vis.Clear();
            for (int k = 0; k < works.Count; k++) if (obj < 0 ? works[k].Sum : !works[k].Sum && works[k].Part == obj) vis.Add(k);
            // the work shown first: the tower's floors, the work going on now, else the first one
            int pick = -1;
            if (obj < 0) pick = works.FindIndex(w => w.Sum && w.Part == TI);
            else if (obj == TI) pick = works.FindIndex(w => !w.Sum && w.Part == TI && w.Phase == 1 && w.Place == 0 && !w.Core);
            if (pick >= 0 && obj == TI && Stat(works[pick], date).Fact >= 0.999f) pick = -1;
            if (pick < 0) foreach (int k in vis) { var st = Stat(works[k], date); if (st.Plan > 0f && st.Fact < 0.999f) { pick = k; break; } }
            if (pick < 0 && vis.Count > 0) pick = vis[0];
            sel = Mathf.Max(pick, 0);
            if (overlay != null) { FillGantt(); RebuildLists(); SetTab(tab); }
            if (focus && view == View.Plan) { zoomK = obj >= 0 ? 0.55f : 1f; planPan = obj >= 0 ? new Vector2(Pt(obj).Focus.x, Pt(obj).Focus.z) : Vector2.zero; }
            else if (focus)
            {
                if (obj < 0) SetView(View.Complex);
                else if (obj == TI) { if (works[sel].Place == 0) { view = View.Floor; pitch = 54f; zoomK = 1f; } else Focus(); }
                else { SetView(View.Tower); pitch = Pt(obj).Pitch; }
            }
            dirty = true;
        }
        void Focus()
        {
            var w = works[sel]; zoomK = 1f;
            if (view == View.Plan)
            {
                // on the plan: the place of the work (a work on the floors: its building)
                var f = w.Place == 1 ? w.Focus : Pt(w.Part).Focus; planPan = new Vector2(f.x, f.z); zoomK = 0.55f; return;
            }
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
            else if (v == View.Tower) pitch = obj >= 0 && obj != TI ? Pt(obj).Pitch : 16f;
            else if (v == View.Floor) pitch = 54f;
            else if (v == View.Plan) planPan = obj >= 0 ? new Vector2(Pt(obj).Focus.x, Pt(obj).Focus.z) : Vector2.zero;
            if (v == View.Plan && obj >= 0) zoomK = 0.55f;
            dirty = true;
        }
        /// <summary>The floor the 3D view and the core camera look at: the front of the selected tower work, else the working floor.</summary>
        int FloorFor()
        {
            var w = works[sel];
            if (w.Phase > 0)
            {
                int f = Front(w.Phase, shownP);
                if (f >= 0) return w.Core ? Mathf.Min(f + 1, IconicShape.Levels - 1) : f;
            }
            return WorkFloor(shownP);
        }
        float FrameTop => H * Mathf.Clamp01((shownP - 0.08f) / 0.62f);

        // ------------------------------------------------------------------ per frame
        void Update()
        {
            if (!open) return;
            if (!IconicInterior.Active) { Close(); return; }
            float dt = TwinState.RealDelta; phase += dt;
            if (!MapCamera.Typing)
            {
                if (Input.GetKeyDown(KeyCode.Escape)) { if (tab == TAn && AnDocOpen) CloseDoc(); else if (view == View.Cam) CamBack(); else { Close(); return; } }
                if (Input.GetKeyDown(KeyCode.Space)) TogglePlay();
                if (Input.GetKeyDown(KeyCode.RightArrow)) { playing = false; SetDate(date + 1f / 12f); }
                if (Input.GetKeyDown(KeyCode.LeftArrow)) { playing = false; SetDate(date - 1f / 12f); }
                for (int k = 0; k <= Mathf.Min(L.Parts.Count, 9); k++) if (Input.GetKeyDown(KeyCode.Alpha0 + k)) SelectObj(k - 1, true);   // 0 — all, 1 … — a building
            }
            if (playing)
            {
                SetDate(date + dt * Speed);
                if (playStop > 0f && date >= playStop) { SetDate(playStop); playing = false; playStop = -1f; dirty = true; }
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
            float dt = TwinState.RealDelta;
            Vector3 pos; Quaternion rot; float fov = 40f; bool ortho = view == View.Plan;
            if (TwinTour.VideoMode && view != View.Cam && !ortho) yaw += dt * 3f;        // the recorded video: the model turns slowly
            if (view == View.Cam)
            {
                CamPose(camIx, out pos, out rot, true, camYawOff, camPitchOff); fov = camFov;
            }
            else if (ortho)
            {
                // the plan (orthophoto / 2D): straight down on the plot, its long side across the picture
                rot = Quaternion.LookRotation(Vector3.down, model.forward);
                pos = model.TransformPoint(new Vector3(planPan.x, 0f, planPan.y)) + Vector3.up * 900f;
            }
            else
            {
                Vector3 target; float dist;
                if (view == View.Complex) { target = model.TransformPoint(focusLocal); dist = focusDist; }
                else if (view == View.Tower && obj >= 0 && obj != TI) { var op = Pt(obj); target = model.TransformPoint(op.Focus); dist = op.Dist; }
                else if (view == View.Tower) { float top = Mathf.Max(FrameTop, 30f); target = model.TransformPoint(new Vector3(IconicShape.Xr - IconicShape.W0 * 0.5f, top * 0.5f, IconicShape.Cz)); dist = top * 1.05f + 170f; }
                else { var c = IconicFloors.Centre(Mathf.Max(focusFloor, 0), out float size); target = model.TransformPoint(c + Vector3.up * 1.2f); dist = size * 1.5f + 34f; }
                rot = Quaternion.Euler(pitch, yaw, 0f); pos = target - rot * Vector3.forward * dist * zoomK;
                float g = CityGround.HeightAt(pos.x, pos.z) + 3f; if (pos.y < g) pos.y = g;
            }
            float k = 1f - Mathf.Exp(-5f * dt);
            if (ortho != mon.orthographic) { mon.orthographic = ortho; curPos = pos; curRot = rot; }       // no flight between a perspective and the plan
            curPos = Vector3.Lerp(curPos, pos, k); curRot = Quaternion.Slerp(curRot, rot, k);
            mon.transform.SetPositionAndRotation(curPos, curRot);
            mon.fieldOfView = Mathf.Lerp(mon.fieldOfView, fov, k);
            if (ortho) mon.orthographicSize = Mathf.Lerp(mon.orthographicSize, PlanSize() * zoomK, k);
            mon.nearClipPlane = view == View.Cam ? 0.2f : ortho ? 2f : 0.5f;
            // the 4D page and a plan without the city: the model alone on a dark stage (its own layer); the BIM look is switched on
            // around this camera's render only (PreCam / PostCam)
            Isolate(tab == T4D ? !d4Base : tab == TSurv && !lyBase);
            mon.cullingMask = isolated ? 1 << IsoLayer : monMask;
            mon.clearFlags = isolated ? CameraClearFlags.SolidColor : monClear;
            mon.backgroundColor = !isolated ? monBg : tab == T4D ? new Color(0.043f, 0.052f, 0.067f) : new Color(0.10f, 0.11f, 0.12f);
            // with the schedule open the picture is centred in the free part above it (off-centre projection)
            mon.ResetProjectionMatrix();
            if (tab == T4D && ganttOn && gantt != null && photo != null)
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
                var r = photo.worldBound; float ppp = Screen.height / Mathf.Max(photo.panel.visualTree.layout.height, 1f);
                int W = Mathf.Clamp(Mathf.RoundToInt(r.width * ppp), 64, 2400), Hh = Mathf.Clamp(Mathf.RoundToInt(r.height * ppp), 64, 1600);
                if (r.width > 10f && (monRT == null || Mathf.Abs(monRT.width - W) > 8 || Mathf.Abs(monRT.height - Hh) > 8))
                {
                    if (monRT != null) { mon.targetTexture = null; monRT.Release(); }
                    monRT = new RenderTexture(W, Hh, 24) { name = "iconic_monitor", antiAliasing = 4 }; monRT.Create();
                    mon.targetTexture = monRT; photo.image = monRT;
                }
                // the window is built anew each time it opens: hand the picture to its image every time (not only when the texture is made)
                if (monRT != null)
                {
                    if (mon.targetTexture != monRT) mon.targetTexture = monRT;
                    bool live = !(tab == TVid && view != View.Cam) && tab != TAn && tab != TCtl;          // the camera wall covers the picture: no need to draw it
                    if (mon.enabled != live) mon.enabled = live;
                    if (photo.image != monRT) photo.image = monRT;
                }
                Pin(); ObjPins(); DefPins();
                if (tab == TObj || tab == TVid || tab == TInv) Rigs(); else HideRigs();
                Compare(); SurveyMarks();
            }
            // video analytics on the full-size camera picture (the pose and projection the picture is about to be drawn with)
            if (view == View.Cam) { Detect(mon, monRT != null ? monRT.height : 600f, bigBox); SeenNote(bigBox.Count); } else bigBox.Clear();
            bigOver?.MarkDirtyRepaint();
        }
        /// <summary>Half the height of the plan view that holds the whole plot with a margin (orthographic size at zoom 1).</summary>
        float PlanSize()
        {
            float aspect = monRT != null ? monRT.width / (float)Mathf.Max(monRT.height, 1) : 16f / 9f;
            return Mathf.Max(L.PadD * 0.5f, L.PadW * 0.5f / Mathf.Max(aspect, 0.1f)) * 1.22f;
        }

        // ------------------------------------------------------------------ the model alone (4D, plan without the city) and the BIM look
        const int IsoLayer = 29;
        static readonly int BimId = Shader.PropertyToID("_AlatauBim");
        int monMask = ~0; CameraClearFlags monClear = CameraClearFlags.Skybox; Color monBg = Color.black;
        bool isolated; readonly List<GameObject> isoGos = new List<GameObject>(); readonly List<int> isoLayers = new List<int>();
        /// <summary>Moves the model of the complex (with its site and cranes) to a layer of its own, so the monitoring camera can draw it
        /// without the city; off: every piece back to its own layer.</summary>
        void Isolate(bool on)
        {
            if (on == isolated) return;
            if (on && model == null) return;
            isolated = on;
            if (on)
            {
                isoGos.Clear(); isoLayers.Clear();
                foreach (var t in model.GetComponentsInChildren<Transform>(true)) { isoGos.Add(t.gameObject); isoLayers.Add(t.gameObject.layer); t.gameObject.layer = IsoLayer; }
            }
            else
            {
                for (int i = 0; i < isoGos.Count; i++) if (isoGos[i] != null) isoGos[i].layer = isoLayers[i];
                isoGos.Clear(); isoLayers.Clear();
            }
        }
        static readonly int DiffId = Shader.PropertyToID("_AlatauDiff");
        void OnEnable() { Camera.onPreCull += PreCull; Camera.onPreRender += PreCam; Camera.onPostRender += PostCam; }
        void OnDisable() { Camera.onPreCull -= PreCull; Camera.onPreRender -= PreCam; Camera.onPostRender -= PostCam; Shader.SetGlobalFloat(BimId, 0f); Shader.SetGlobalFloat(DiffId, 0f); }
        // "Что изменилось": the colours of the diff and the site of both dates (cranes, hoarding) for this camera only, before it culls
        bool diffShown;
        void PreCull(Camera c)
        {
            if (c != mon || !DiffOn) return;
            Shader.SetGlobalFloat(DiffId, 1f); LandmarkSystem.Instance?.DiffShow(L.Id, true); diffShown = true;
        }
        // the plan looks straight down from high above: no haze on it (fog off around its render)
        bool fogWas, fogOff;
        void PreCam(Camera c)
        {
            if (c != mon || !open) return;
            Shader.SetGlobalFloat(BimId, tab == T4D ? (wireOn ? 1f : 2f) : 0f);
            fogOff = mon.orthographic; if (fogOff) { fogWas = RenderSettings.fog; RenderSettings.fog = false; }
        }
        void PostCam(Camera c)
        {
            if (c != mon) return;
            Shader.SetGlobalFloat(BimId, 0f);
            if (diffShown) { Shader.SetGlobalFloat(DiffId, 0f); LandmarkSystem.Instance?.DiffShow(L.Id, false); diffShown = false; }
            if (fogOff) { RenderSettings.fog = fogWas; fogOff = false; }
        }

        // ------------------------------------------------------------------ site cameras
        const int NCam = 6;
        static readonly string[] CamId = { "CAM-07", "CAM-02", "CAM-04", "CAM-11", "CAM-01", "CAM-05" };
        // every camera hangs on something real on the site (Mount): the jib-side of a tower crane over the working floor, a lighting mast,
        // the cage of the facade hoist, a mast on the top slab; a small rig is drawn there (Rigs), and the caption says what it is on
        enum Mount { Crane, Tripod, Mast, Hoist, Roof }
        readonly Mount[] camMount = new Mount[NCam];
        readonly Vector3[] camEye = new Vector3[NCam], camLook = new Vector3[NCam], camBase = new Vector3[NCam];
        string[] CamName
        {
            get
            {
                bool k = L != null && L.Id == "kaist";
                return new[]
                {
                    k ? "Мачта у башни B1 · верхние этажи" : camMount[0] == Mount.Crane ? "Кран над захваткой · ядро башни" : "Штатив на захватке · ядро башни",
                    k ? "Мачта освещения · берег озера" : "Мачта освещения · площадь у амфитеатра",
                    k ? "Мачта у восточного фасада B1" : camMount[2] == Mount.Hoist ? "Фасадный подъёмник · восток" : "Мачта у восточного фасада",
                    k ? "Мачта у главного корпуса" : camMount[3] == Mount.Roof ? "Кровля отеля T2" : "Отель T2 · верхнее перекрытие",
                    "PTZ-купол · общий вид площадки",
                    "КПП-1 · въезд и выезд техники",
                };
            }
        }
        readonly RenderTexture[] camRT = new RenderTexture[NCam]; Camera feedCam; int rr; float feedT;
        /// <summary>Where camera i is and what it looks at (model coordinates), and what it is mounted on: base = foot of its support.</summary>
        void CamMount(int i, out Vector3 eye, out Vector3 look)
        {
            int f = Mathf.Max(focusFloor, 0); float yb = IconicShape.FloorY(f), top = Mathf.Max(FrameTop, 20f);
            bool kaist = L.Id == "kaist"; var m = Mount.Mast; var foot = Vector3.zero;
            switch (i)
            {
                case 0:
                    {
                        if (kaist)
                        {
                            // KAIST: the crane stands on the low tower itself and looks straight down at its roof; a mast north-east of it
                            // looks across the top floors at the campus instead
                            eye = new Vector3(IconicShape.Xr + 34f, top + 8f, IconicShape.Cz + 52f); look = new Vector3(IconicShape.Xr - 22f, top - 5f, IconicShape.Cz);
                            foot = new Vector3(eye.x, 0.3f, eye.z); m = Mount.Mast; break;
                        }
                        // over the working floor: on the mast of the crane next to the core, a few metres under its slewing ring;
                        // once the cranes are struck — a tripod on the floor itself
                        look = IconicFloors.Centre(f, out _) + Vector3.up * 1.2f;
                        var ls = LandmarkSystem.Instance; int best = -1; float bd = float.MaxValue; Vector3 bp = default;
                        var tc = new Vector2(IconicShape.Xr - IconicShape.W0 * 0.5f, IconicShape.Cz);
                        for (int c = 0; ls != null && c < ls.CraneCount(L.Id); c++)
                            if (ls.CraneTop(L.Id, c, out var hp)) { float dd = Vector2.Distance(new Vector2(hp.x, hp.z), tc); if (dd < bd) { bd = dd; best = c; bp = hp; } }
                        if (best >= 0 && bp.y > yb + 6f)
                        {
                            var dir = new Vector3(look.x - bp.x, 0f, look.z - bp.z); dir = dir.sqrMagnitude > 1f ? dir.normalized : Vector3.forward;
                            foot = bp + Vector3.down * 3.2f; eye = foot + dir * 1.9f; m = Mount.Crane;
                        }
                        else
                        {
                            eye = new Vector3(IconicShape.Xr - 5f, yb + 2.3f, IconicShape.Cz + IconicShape.Depth(yb) * 0.40f); foot = new Vector3(eye.x, yb, eye.z); m = Mount.Tripod;
                        }
                        break;
                    }
                case 1:
                    // Iconic: a mast on the podium roof in front of the tower, looking up its lamella face
                    {
                        float ry = kaist ? 0.3f : LandmarkModels.RoofAt(-120f, 80f);
                        eye = kaist ? new Vector3(-40f, 14f, -50f) : new Vector3(-120f, ry + 7f, 80f);
                        look = new Vector3(IconicShape.Xr - (kaist ? 20f : 30f), top * 0.55f, IconicShape.Cz); foot = new Vector3(eye.x, ry, eye.z); break;
                    }
                case 2:
                    {
                        // the cage of the facade hoist on the east face, at the floor where the curtain wall goes up; its mast is tied to the frame
                        int ff = Front(IconicFloors.PFacade, shownP); bool hoist = ff >= 0; if (ff < 0) ff = WorkFloor(shownP);
                        if (kaist)
                        {
                            // KAIST: from the hoist cage the dark glass of the low tower filled the picture; a mast south-east of the tower
                            // shows the east face and the floor the curtain wall goes up on, with the campus behind
                            float yk = IconicShape.FloorY(ff);
                            eye = new Vector3(IconicShape.Xr + 24f, Mathf.Min(yk + 7f, 42f), IconicShape.Cz - 36f); look = new Vector3(IconicShape.Xr - 14f, yk - 1f, IconicShape.Cz + 4f);
                            foot = new Vector3(eye.x, 0.3f, eye.z); m = Mount.Mast; break;
                        }
                        float y = IconicShape.FloorY(ff), zh = IconicShape.Cz - IconicShape.Depth(y) * 0.26f;
                        if (!hoist && shownP > 0.5f) y = Mathf.Min(y, 10f);       // the facade is closed and the hoist struck: a mast by the east face
                        // on a short post at the facade-side edge of the cage roof, so the roof stays behind the lens
                        // and looking along the face (straight at it from 1.4 m the frame filled the picture)
                        eye = new Vector3(IconicShape.Xr + 1.8f, y + 4.9f, zh); look = new Vector3(IconicShape.Xr - 4f, y - 2f, zh + 46f);
                        if (hoist || shownP <= 0.5f) { foot = new Vector3(IconicShape.Xr + 2.6f, y, zh); m = Mount.Hoist; }
                        else { eye.x += 4.5f; foot = new Vector3(eye.x, 0.3f, zh); m = Mount.Mast; }
                        break;
                    }
                case 4:
                    // a PTZ dome on a 26 m mast at the south-west corner of the plot: the whole site, slowly sweeping
                    eye = new Vector3(-L.PadW * 0.5f + 9f, 26f, -L.PadD * 0.5f + 9f); look = new Vector3(L.PadW * 0.08f, Mathf.Min(top * 0.35f, 40f), L.PadD * 0.05f);
                    foot = new Vector3(eye.x, 0.3f, eye.z); break;
                case 5:
                    // the gate of the site: trucks in and out; Iconic's is on the square behind the podium, between the tower and
                    // the pyramid, looking in at the gap between them
                    if (kaist) { eye = new Vector3(L.PadW * 0.5f - 6f, 6.5f, -L.PadD * 0.5f + 4f); look = new Vector3(L.PadW * 0.5f - 40f, 1f, -L.PadD * 0.5f + 34f); }
                    else { eye = new Vector3(12f, 24f, -L.PadD * 0.5f + 2f); look = new Vector3(12f, 50f, -40f); }
                    foot = new Vector3(eye.x, 0.3f, eye.z); break;
                default:
                    if (kaist) { eye = new Vector3(62f, 34f, -86f); look = new Vector3(IconicShape.Xr - 20f, Mathf.Max(top - 10f, 8f), IconicShape.Cz); foot = new Vector3(eye.x, 0.3f, eye.z); }
                    else
                    {
                        // on the top slab of the hotel as its frame rises, on its roof once it is topped out
                        float hp = PlanP(1, date); if (!planMode) hp = FactP(1, date);
                        float fr = Mathf.Max(Pt(1).H * 0.95f * Mathf.Clamp01((hp - 0.08f) / 0.62f), 0.3f);
                        var ap = LandmarkModels.T2Apex;                                     // the steps of the hotel rise to its top near the tower
                        eye = new Vector3(ap.x + 5f, fr + 5f, ap.y); look = new Vector3(IconicShape.Xr - 30f, Mathf.Max(top - 12f, 10f), IconicShape.Cz);
                        foot = new Vector3(eye.x, fr, eye.z); m = hp >= 0.72f ? Mount.Roof : Mount.Mast;
                    }
                    break;
            }
            camMount[i] = m; camEye[i] = eye; camLook[i] = look; camBase[i] = foot;
        }
        void CamPose(int i, out Vector3 pos, out Quaternion rot, bool pan, float yawOff = 0f, float pitchOff = 0f)
        {
            CamMount(i, out var eye, out var look);
            pos = model.TransformPoint(eye); var d = model.TransformPoint(look) - pos;
            float yw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg + (pan ? Mathf.Sin(phase * 0.16f + i * 1.7f) * 14f : 0f);
            float pt = Mathf.Atan2(-d.y, new Vector2(d.x, d.z).magnitude) * Mathf.Rad2Deg;
            rot = Quaternion.Euler(Mathf.Clamp(pt + pitchOff, -60f, 85f), yw + yawOff, 0f);
        }
        // ---- the rigs of the cameras: housing, bracket and what carries it, drawn as one small mesh of the landmark material
        GameObject rigGo; MeshFilter rigMf; MeshRenderer rigMr; MaterialPropertyBlock rigB; Material rigMat; int rigKey = int.MinValue; Mesh rigMesh;
        readonly Label[] camCap = new Label[NCam]; readonly string[] capSet = new string[NCam];
        static readonly Color32 RigYellow = LM.C("#f2b705"), RigGrey = LM.C("#8c8c88"), RigWhite = LM.C("#ececea"), RigDark = LM.C("#25282c");
        void Rigs()
        {
            if (model == null) return;
            for (int i = 0; i < NCam; i++) CamMount(i, out _, out _);
            int key = 17;
            for (int i = 0; i < NCam; i++) key = key * 31 + Mathf.RoundToInt(camEye[i].x * 4f) * 7 + Mathf.RoundToInt(camEye[i].y * 4f) * 13 + Mathf.RoundToInt(camEye[i].z * 4f) * 19 + (int)camMount[i];
            key = key * 31 + Mathf.RoundToInt(FrameTop);
            if (rigGo == null)
            {
                var sh = Shader.Find("AlatauCity/Landmark"); if (sh == null) return;
                rigGo = new GameObject("Monitoring · camera rigs"); rigMf = rigGo.AddComponent<MeshFilter>(); rigMr = rigGo.AddComponent<MeshRenderer>();
                rigMat = new Material(sh) { name = "Camera rigs" }; rigMr.sharedMaterial = rigMat; rigB = new MaterialPropertyBlock(); rigKey = int.MinValue;
            }
            if (rigGo.transform.parent != model) { rigGo.transform.SetParent(model, false); rigGo.transform.localPosition = Vector3.zero; rigGo.transform.localRotation = Quaternion.identity; rigGo.transform.localScale = Vector3.one; }
            if (!rigGo.activeSelf) rigGo.SetActive(true);
            rigMr.GetPropertyBlock(rigB);
            rigB.SetFloat("_Reveal", 100000f); rigB.SetFloat("_Build", 0f); rigB.SetFloat("_Facade", 100000f); rigB.SetFloat("_Land", 1f); rigB.SetFloat("_Glow", -1f); rigB.SetFloat("_Ghost", 0f);
            rigMr.SetPropertyBlock(rigB);
            // (compared with what was set, not with the label: the translator puts the English or Kazakh text into it)
            var names = CamName; for (int i = 0; i < NCam; i++) if (camCap[i] != null && capSet[i] != names[i]) { capSet[i] = names[i]; camCap[i].text = names[i]; }
            if (key == rigKey) return; rigKey = key;
            var k = new LandmarkKit();
            for (int i = 0; i < NCam; i++)
            {
                Vector3 e = camEye[i], b = camBase[i], d = camLook[i] - e; d.y = 0f; d = d.sqrMagnitude > 0.01f ? d.normalized : Vector3.forward;
                float yaw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg;
                // the housing sits just behind the lens (the camera's own picture never shows it) with a sun hood and a dark front
                k.Box(e - d * 0.55f + Vector3.down * 0.05f, new Vector3(0.36f, 0.32f, 0.72f), yaw, RigWhite, LM.Solid, 1f, RigWhite, LM.Solid);
                k.Box(e - d * 0.18f + Vector3.down * 0.05f, new Vector3(0.30f, 0.26f, 0.04f), yaw, RigDark, LM.Solid, 1f, RigDark, LM.Solid);
                k.Box(e - d * 0.5f + Vector3.up * 0.14f, new Vector3(0.44f, 0.04f, 0.84f), yaw, RigWhite, LM.Solid, 1f, RigWhite, LM.Solid);
                var under = e - d * 0.55f + Vector3.down * 0.22f;
                switch (camMount[i])
                {
                    case Mount.Crane:                                                       // a bracket bolted to the mast of the crane
                        k.Beam(b, under, 0.14f, 0.14f, RigYellow, LM.Steel); k.Beam(b + Vector3.down * 0.8f, under, 0.1f, 0.1f, RigYellow, LM.Steel);
                        k.Box(b, new Vector3(0.5f, 0.6f, 0.5f), yaw, RigGrey, LM.Steel, 1f, RigGrey, LM.Steel);                       // junction box
                        break;
                    case Mount.Tripod:
                        for (int l = 0; l < 3; l++) { float a = (yaw + l * 120f) * Mathf.Deg2Rad; k.Beam(new Vector3(b.x + Mathf.Sin(a) * 0.8f, b.y, b.z + Mathf.Cos(a) * 0.8f), under, 0.05f, 0.05f, RigDark, LM.Steel); }
                        break;
                    case Mount.Hoist:
                        {
                            // mast from the ground to above the frame, ties to the slab edge every 3 floors, the cage at the facade floor
                            float topM = Mathf.Max(FrameTop + 4f, b.y + 8f); var mast = new Vector3(b.x, 0f, b.z - 2.3f);
                            k.Box(new Vector3(mast.x, topM * 0.5f, mast.z), new Vector3(0.9f, topM, 0.9f), 0f, RigYellow, LM.Steel, 1f, RigYellow, LM.Steel);
                            for (float ty = IconicShape.FloorY(3); ty < topM - 1f; ty += IconicShape.Fh * 3f)
                                k.Beam(new Vector3(mast.x, ty, mast.z), new Vector3(IconicShape.Xr, ty, mast.z), 0.14f, 0.14f, RigGrey, LM.Steel);
                            var cage = new Vector3(b.x, b.y + 0.4f, b.z);
                            k.Box(cage + Vector3.up * 1.3f, new Vector3(3.0f, 2.6f, 3.6f), 0f, RigGrey, LM.Steel, 1f, RigYellow, LM.Steel);
                            k.Box(new Vector3(cage.x, cage.y + 0.02f, cage.z), new Vector3(3.4f, 0.12f, 4.0f), 0f, RigYellow, LM.Steel, 1f, RigYellow, LM.Steel);
                            foreach (float sx in new[] { -1.55f, 1.55f }) k.Beam(new Vector3(cage.x + sx, cage.y + 2.6f, cage.z - 1.8f), new Vector3(cage.x + sx, cage.y + 2.6f, cage.z + 1.8f), 0.06f, 0.5f, RigYellow, LM.Steel);   // roof rail
                            k.Beam(new Vector3(under.x, cage.y + 2.6f, under.z), under, 0.08f, 0.08f, RigDark, LM.Steel);     // the post on the cage roof
                            break;
                        }
                    default:                                                                // a lighting mast (from the ground or from the top slab)
                        {
                            k.Cylinder(b, 0.22f, Mathf.Max(e.y - b.y - 0.2f, 0.5f), 8, RigGrey, LM.Steel, 1f, RigGrey, LM.Steel);
                            k.Box(new Vector3(b.x, b.y + 0.15f, b.z), new Vector3(0.9f, 0.3f, 0.9f), 0f, RigGrey, LM.Solid, 1f, RigGrey, LM.Solid);
                            k.Beam(new Vector3(b.x, e.y - 0.25f, b.z), under, 0.08f, 0.08f, RigGrey, LM.Steel);
                            break;
                        }
                }
            }
            if (rigMesh != null) Destroy(rigMesh);
            rigMesh = k.ToMesh("camera rigs"); rigMf.sharedMesh = rigMesh;
        }
        void HideRigs() { if (rigGo != null) rigGo.SetActive(false); }
        /// <summary>Renders the site cameras into their small screens: the core camera on the overview (≈ 7 frames a second),
        /// all four in turn on the cameras tab.</summary>
        /// <summary>Video analytics of a site camera: every worker on the floor in the cut (IconicFloors.Crew) that this camera really
        /// sees — in front of it, inside its picture, large enough to recognise, not behind the core or below the cut edge of the facade —
        /// gets a box round its figure, in the picture's own coordinates (0..1, y up) at the moment the picture is taken.</summary>
        readonly List<Rect>[] feedBox = { new List<Rect>(), new List<Rect>(), new List<Rect>(), new List<Rect>(), new List<Rect>(), new List<Rect>() };
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
        /// <summary>The line of the video analytics under an open camera: how many people it sees.</summary>
        void SeenNote(int n)
        {
            if (aiNote == null || n == crewSeen) return; crewSeen = n;
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
        /// <summary>Renders the site cameras of the wall in turn (the open group; ≈ 2–3 frames a second each); an open camera is the main picture.</summary>
        void Feeds(float dt)
        {
            feedT -= dt; foreach (var o in tileOver) o?.MarkDirtyRepaint();
            if (feedT > 0f || main == null || tab != TVid || view == View.Cam) return;
            var g = Groups[vidGroup]; rr = (rr + 1) % g.Length; int i = g[rr]; feedT = 0.06f;
            if (camRT[i] == null) { camRT[i] = new RenderTexture(480, 270, 24) { name = "iconic_cctv_" + i, antiAliasing = 2 }; camRT[i].Create(); }
            if (feedCam == null) { var go = new GameObject("Iconic monitoring · site camera"); go.transform.SetParent(transform, false); feedCam = go.AddComponent<Camera>(); feedCam.enabled = false; }
            feedCam.CopyFrom(mon); feedCam.ResetProjectionMatrix(); feedCam.enabled = false; feedCam.orthographic = false; feedCam.cullingMask = monMask; feedCam.clearFlags = monClear;
            feedCam.targetTexture = camRT[i]; feedCam.ResetAspect(); feedCam.fieldOfView = 58f; feedCam.nearClipPlane = 0.2f; feedCam.farClipPlane = 20000f;
            CamPose(i, out var p, out var r, true); feedCam.transform.SetPositionAndRotation(p, r);
            Detect(feedCam, camRT[i].height, feedBox[i]);
            try { feedCam.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] monitoring camera: " + e.Message); return; }
            if (tiles[i] != null && tiles[i].image != camRT[i]) tiles[i].image = camRT[i];
        }

        void BuildGantt(VisualElement g)
        {
            var gh = new VisualElement(); gh.AddToClassList("mon-row"); gh.AddToClassList("mon-g-head"); g.Add(gh);
            gh.Add(TwinUI.Icon("chart_line", 16)); var gt = new Label("График работ · " + L.Short); gt.AddToClassList("mon-title"); gh.Add(gt); gTitle = gt;
            gCrew = new Label { pickingMode = PickingMode.Ignore }; gCrew.AddToClassList("mon-g-crew"); gh.Add(gCrew);
            var gs = new VisualElement(); gs.style.flexGrow = 1; gh.Add(gs);
            gh.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.28f), "план"));
            gh.Add(Widgets.LegendItem(Blue, "факт"));
            gh.Add(Widgets.LegendItem(BlueSoft, "прогноз"));
            gh.Add(Widgets.LegendItem(Orange, "съёмка " + Day(Report)));
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
            glist = new VisualElement(); glist.AddToClassList("mon-g-list"); g.Add(glist);
            FillGantt();
        }
        /// <summary>The rows of the schedule: the buildings of the complex (click: look at the building) or the works of the selected one.</summary>
        void FillGantt()
        {
            if (glist == null) return;
            glist.Clear(); grows.Clear();
            if (gTitle != null) gTitle.text = "График работ · " + (obj < 0 ? L.Short + " · все объекты" : Pt(obj).Name);
            foreach (int i in vis)
            {
                int k = i; var w = works[i]; var gr = new GRow { W = k };
                var r = new VisualElement(); r.AddToClassList("mon-g-row"); if (w.Sum) r.AddToClassList("mon-g-sum"); glist.Add(r); gr.Row = r;
                var nm = new VisualElement(); nm.AddToClassList("mon-g-name"); r.Add(nm);
                var code = new Label(w.Code) { pickingMode = PickingMode.Ignore }; code.AddToClassList("mon-g-code"); nm.Add(code);
                var n = new Label(w.Name) { pickingMode = PickingMode.Ignore }; n.AddToClassList("mon-g-label"); nm.Add(n);
                nm.RegisterCallback<ClickEvent>(_ => { if (works[k].Sum) SelectObj(works[k].Part, true); else Select(k, true); });
                gr.Plan = GCell("", "mon-g-n"); gr.Fact = GCell("", "mon-g-n"); gr.Dev = GCell("", "mon-g-d"); r.Add(gr.Plan); r.Add(gr.Fact); r.Add(gr.Dev);
                var bars = new VisualElement(); bars.AddToClassList("mon-g-bars"); r.Add(bars); gr.Bars = bars;
                bars.generateVisualContent += ctx => DrawBars(ctx, bars, works[k], k == sel);
                bars.RegisterCallback<PointerDownEvent>(_ => { if (sel != k) Select(k, true); }, TrickleDown.TrickleDown);
                Scrub(bars, x => Mathf.Lerp(T0, T1, x));
                grows.Add(gr);
            }
        }

        // ------------------------------------------------------------------ interaction
        void TogglePlay()
        {
            playing = !playing;
            if (playing && date >= T1 - 0.01f) SetDate(T0);
            dirty = true;
        }
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
            Vector2 last = Vector2.zero, down = Vector2.zero;
            bool splitDrag = false;
            e.RegisterCallback<PointerDownEvent>(ev =>
            {
                e.CapturePointer(ev.pointerId); last = ev.position; down = ev.position;
                // comparing two surveys: pressed near the dividing line, the drag moves the line, not the view
                splitDrag = NearSplit(ev.position.x);
            });
            e.RegisterCallback<PointerMoveEvent>(ev =>
            {
                if (!e.HasPointerCapture(ev.pointerId)) return;
                if (splitDrag) { SplitTo(ev.position.x); last = ev.position; return; }
                var d = (Vector2)ev.position - last; last = ev.position;
                if (view == View.Cam) { camYawOff = Mathf.Clamp(camYawOff + d.x * 0.15f, -70f, 70f); camPitchOff = Mathf.Clamp(camPitchOff + d.y * 0.12f, -40f, 40f); }
                else if (Measuring) { }
                else if (view == View.Plan) { float mpp = mon.orthographicSize * 2f / Mathf.Max(e.layout.height, 1f); planPan += new Vector2(-d.x, d.y) * mpp; }
                else { yaw += d.x * 0.25f; pitch = Mathf.Clamp(pitch + d.y * 0.2f, 5f, 88f); }
            });
            e.RegisterCallback<PointerUpEvent>(ev =>
            {
                if (!e.HasPointerCapture(ev.pointerId)) return;
                e.ReleasePointer(ev.pointerId);
                if (splitDrag) { splitDrag = false; return; }
                if (((Vector2)ev.position - down).magnitude < 5f && view != View.Cam) { if (Measuring) Measure(e, ev.localPosition); else PickAt(e, ev.localPosition); }   // a click, not a drag
            });
            e.RegisterCallback<WheelEvent>(ev =>
            {
                float s = Mathf.Sign(ev.delta.y);
                if (view == View.Cam) camFov = Mathf.Clamp(camFov * (1f + 0.08f * s), 22f, 72f);
                else zoomK = Mathf.Clamp(zoomK * (1f + 0.1f * s), 0.25f, 3f);
                ev.StopPropagation();
            });
        }

        /// <summary>The label over the floor being shown (where the camera sees it).</summary>
        void Pin()
        {
            if (pin == null) return;
            if (tab == TDef || tab == TCtl) { pin.style.display = DisplayStyle.None; return; }
            bool on = view == View.Floor && focusFloor >= 0 && monRT != null;
            // a work of a building on the complex view: a label at the place where it goes on, with how far it is
            var wk = sel >= 0 && sel < works.Count ? works[sel] : null;
            if (!on && view == View.Complex && monRT != null && wk != null && wk.Place == 1 && !wk.Sum && obj >= 0)
            {
                var vp = mon.WorldToViewportPoint(model.TransformPoint(wk.Focus));
                bool vis2 = vp.z > 0f && vp.x > 0.02f && vp.x < 0.98f && vp.y > 0.05f && vp.y < 0.95f;
                if (vis2)
                {
                    pin.style.left = Length.Percent(vp.x * 100f); pin.style.top = Length.Percent((1f - vp.y) * 100f);
                    float p = ShownP(wk.Part, date), q = Mathf.Clamp01((p - wk.A) / Mathf.Max(wk.B - wk.A, 1e-4f));
                    pinText.text = wk.Name + " · " + (p < wk.A ? "ещё не начата" : p > wk.B ? "выполнена" : Mathf.RoundToInt(q * 100f) + " %");
                }
                pin.style.display = vis2 ? DisplayStyle.Flex : DisplayStyle.None;
                return;
            }
            if (on)
            {
                var c = IconicFloors.Centre(focusFloor, out _); var wpt = model.TransformPoint(c + Vector3.up * 1.2f);
                var vp = mon.WorldToViewportPoint(wpt); on = vp.z > 0f && vp.x > 0.02f && vp.x < 0.98f && vp.y > 0.05f && vp.y < 0.95f;
                if (on)
                {
                    pin.style.left = Length.Percent(vp.x * 100f); pin.style.top = Length.Percent((1f - vp.y) * 100f);
                    var w = works[sel]; int ph = IconicFloors.Phase(focusFloor, Mathf.Min(shownP, 0.998f), H, out float fr);
                    string what = w.Phase > 0 && ph == w.Phase ? (w.Core ? "Ядро · подъём опалубки" : w.Phase == 1 ? "Армирование и опалубка" : w.Name) : IconicFloors.PhaseNow[ph];
                    pinText.text = UiTranslator.Tr(IconicFloors.Name(focusFloor) + " · " + what + (ph > 0 && ph < IconicFloors.PReady ? " · " + Mathf.RoundToInt(fr * 100f) + " %" : ""));   // set every frame, after the interface was translated
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
            float pa = PlanDate(w.Part, w.A), pb = PlanDate(w.Part, w.B), fa = FactDate(w.Part, w.A), fb = FactDate(w.Part, w.B);
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
            if (w.Sum) Diamond(g, new Vector2(X(fb), h * 0.69f), 4.5f, fb > pb + 0.01f ? Orange : Green);          // the hand-over of the building
            VLine(g, X(Report), 0f, h, Orange, 1.4f);
            VLine(g, X(date), 0f, h, Color.white, 1.6f);
        }
        static void Diamond(Painter2D g, Vector2 c, float r, Color col)
        {
            g.fillColor = col; g.BeginPath(); g.MoveTo(c + new Vector2(0, -r)); g.LineTo(c + new Vector2(r, 0)); g.LineTo(c + new Vector2(0, r)); g.LineTo(c + new Vector2(-r, 0)); g.ClosePath(); g.Fill();
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

        /// <summary>Over a site camera: scan lines, the blinking REC dot, video-analytics boxes on the crew (green = helmet and vest).</summary>
        void DrawFeed(MeshGenerationContext ctx, VisualElement over, int cam)
        {
            if (over == null) return; var r = over.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
            g.lineWidth = 1f; g.strokeColor = new Color(1f, 1f, 1f, 0.035f);
            for (float y = 0; y < r.height; y += 3f) { g.BeginPath(); g.MoveTo(new Vector2(0, y)); g.LineTo(new Vector2(r.width, y)); g.Stroke(); }
            if (Mathf.Repeat(phase + cam * 0.3f, 1.2f) < 0.7f) { g.fillColor = new Color(1f, 0.23f, 0.18f); g.BeginPath(); g.Arc(new Vector2(10f, 11f), 3.5f, 0f, 360f); g.Fill(); }
            // the boxes of the video analytics: the picture fills the screen and is cropped (ScaleAndCrop), so map through the crop
            var rt = camRT[cam]; float iw = rt != null ? rt.width : 480f, ih = rt != null ? rt.height : 270f;
            float s = Mathf.Max(r.width / iw, r.height / ih), dw = iw * s, dh = ih * s, ox = (r.width - dw) * 0.5f, oy = (r.height - dh) * 0.5f;
            DrawBoxes(g, feedBox[cam], ox, oy, dw, dh, new Rect(0f, 0f, r.width, r.height), 1.3f);
        }

        // ------------------------------------------------------------------ the buildings of the complex
        /// <summary>The bar over the view: the whole complex and every building with its state (dot: in time / late / not started).</summary>
        void BuildObjBar(VisualElement parent)
        {
            objBtns.Clear(); objPct.Clear(); objDot.Clear();
            var bar = new VisualElement(); bar.AddToClassList("mon-seg"); bar.AddToClassList("mon-objs"); parent.Add(bar);
            for (int i = -1; i < L.Parts.Count; i++)
            {
                int k = i; var b = new Button(() => SelectObj(k, true)) { focusable = false }; b.AddToClassList("btn"); b.AddToClassList("small"); b.AddToClassList("mon-obj");
                var d = Widgets.Dot(Color.gray, true); b.Add(d); objDot.Add(d);
                b.Add(new Label(k < 0 ? "Все объекты" : Pt(k).Short) { pickingMode = PickingMode.Ignore });
                var pc = new Label { pickingMode = PickingMode.Ignore }; pc.AddToClassList("mon-obj-p"); pc.style.marginLeft = 7; b.Add(pc); objPct.Add(pc);
                bar.Add(b); objBtns.Add(b);
            }
        }
        /// <summary>The labels over the buildings in the view of the complex: what each building is, its readiness and delay. Click: look at it.</summary>
        void ObjPins()
        {
            bool show = (view == View.Complex || view == View.Tower || view == View.Plan) && monRT != null && tab != TVid && tab != TAn && tab != TCtl && tab != TDef && !(tab == TSurv && lyDiff);
            for (int i = 0; i < opins.Count; i++)
            {
                var pe = opins[i]; bool on = show && (view == View.Complex || i == obj);
                if (on)
                {
                    var p = Pt(i); float fp = ShownP(i, date);
                    if (fp <= 0f && i != obj) on = false;                         // not started: no label floating over the others
                }
                if (on)
                {
                    var p = Pt(i); float fp = ShownP(i, date);
                    float h = fp >= 0.999f ? p.H : p.Land || fp <= 0f ? 3f : Mathf.Max(p.H * Mathf.Clamp01((fp - 0.08f) / 0.62f), 3f);
                    if (p.Tower && fp >= 0.999f) h = p.H * 0.92f;
                    var vp = mon.WorldToViewportPoint(model.TransformPoint(new Vector3(p.Focus.x, h + 4f, p.Focus.z)));
                    on = vp.z > 0f && vp.x > 0.03f && vp.x < 0.97f && vp.y > 0.06f && vp.y < 0.94f;
                    if (on) { pe.style.left = Length.Percent(vp.x * 100f); pe.style.top = Length.Percent((1f - vp.y) * 100f); }
                }
                pe.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
                pe.EnableInClassList("sel", i == obj);
            }
        }
        /// <summary>A click on the view picks the building under it (not one that has not started yet).</summary>
        void PickAt(VisualElement e, Vector2 lp)
        {
            var r = e.contentRect; if (r.width < 10f || mon == null || LandmarkSystem.Instance == null) return;
            var ray = mon.ViewportPointToRay(new Vector3(lp.x / r.width, 1f - lp.y / r.height, 0f));
            int part = LandmarkSystem.Instance.PickPart(L.Id, ray, out _);
            if (part >= 0 && part != obj && ShownP(part, date) > 0f) SelectObj(part, true);
        }

        // ------------------------------------------------------------------ for the investor
        readonly List<Label> invMk = new List<Label>();
        void BuildInv(VisualElement g)
        {
            var gh = new VisualElement(); gh.AddToClassList("mon-row"); gh.AddToClassList("mon-g-head"); g.Add(gh);
            gh.Add(TwinUI.Icon("presentation", 16)); var gt = new Label("Инвестору · " + L.Short); gt.AddToClassList("mon-title"); gh.Add(gt);
            var gs = new VisualElement(); gs.style.flexGrow = 1; gh.Add(gs);
            invNote = new Label("бюджеты, коммерция и отклонения — сценарий цифрового двойника, не данные застройщика") { pickingMode = PickingMode.Ignore }; invNote.AddToClassList("note"); gh.Add(invNote); var mt = SourceTags.ModelTag(SrcMon); mt.style.marginLeft = 8; gh.Add(mt);
            var kr = new VisualElement(); kr.AddToClassList("mon-inv-kpis"); g.Add(kr);
            for (int i = 0; i < 5; i++)
            {
                var t = new VisualElement(); t.AddToClassList("mon-inv-k"); kr.Add(t);
                kCap[i] = new Label { pickingMode = PickingMode.Ignore }; kCap[i].AddToClassList("mon-inv-cap"); t.Add(kCap[i]);
                kVal[i] = new Label { pickingMode = PickingMode.Ignore }; kVal[i].AddToClassList("mon-inv-val"); t.Add(kVal[i]);
                kSub[i] = new Label { pickingMode = PickingMode.Ignore }; kSub[i].AddToClassList("mon-inv-sub"); t.Add(kSub[i]);
            }
            var row = new VisualElement(); row.AddToClassList("mon-inv-body"); g.Add(row);
            // the buildings
            invTable = new VisualElement(); invTable.AddToClassList("mon-inv-table"); row.Add(invTable);
            var th = new VisualElement(); th.AddToClassList("mon-inv-tr"); th.AddToClassList("mon-th"); invTable.Add(th);
            foreach (var (c, cls) in new[] { ("Объект", "o"), ("Бюджет", "b"), ("Готовность · факт / план", "r"), ("Ввод · план → прогноз", "e"), (L.Id == "kaist" ? "Использование" : "Коммерция", "c") }) th.Add(Cell(c, cls));
            irows.Clear();
            for (int i = 0; i < L.Parts.Count; i++)
            {
                int k = i; var p = Pt(i); var ir = new IRow { I = i };
                var r = new VisualElement(); r.AddToClassList("mon-inv-tr"); invTable.Add(r); ir.Row = r; r.RegisterCallback<ClickEvent>(_ => SelectObj(k, true));
                var c0 = new VisualElement(); c0.AddToClassList("mon-td"); c0.AddToClassList("o"); r.Add(c0);
                var nl = new Label(p.Name) { pickingMode = PickingMode.Ignore }; nl.AddToClassList("mon-work"); c0.Add(nl);
                var sl = new Label(p.Size) { pickingMode = PickingMode.Ignore }; sl.AddToClassList("mon-src"); c0.Add(sl);
                r.Add(Cell(Usd(p.Capex), "b"));
                var c2 = new VisualElement(); c2.AddToClassList("mon-td"); c2.AddToClassList("r"); r.Add(c2);
                ir.Done = new Label { pickingMode = PickingMode.Ignore }; ir.Done.AddToClassList("mon-inv-n"); c2.Add(ir.Done);
                var bar = new VisualElement { pickingMode = PickingMode.Ignore }; bar.AddToClassList("mon-bar"); c2.Add(bar);
                ir.Bar = new VisualElement { pickingMode = PickingMode.Ignore }; ir.Bar.AddToClassList("mon-fill"); bar.Add(ir.Bar);
                ir.Mark = new VisualElement { pickingMode = PickingMode.Ignore }; ir.Mark.AddToClassList("mon-mark"); bar.Add(ir.Mark);
                var c3 = new VisualElement(); c3.AddToClassList("mon-td"); c3.AddToClassList("e"); r.Add(c3);
                ir.Due = new Label { pickingMode = PickingMode.Ignore }; ir.Due.AddToClassList("mon-inv-n"); c3.Add(ir.Due);
                ir.Dev = new Label { pickingMode = PickingMode.Ignore }; ir.Dev.AddToClassList("mon-src"); c3.Add(ir.Dev);
                var c4 = Cell(p.Deal, "c"); c4.style.whiteSpace = WhiteSpace.Normal; r.Add(c4);
                irows.Add(ir);
            }
            // the budget curve with the hand-overs on it
            var cw = new VisualElement(); cw.AddToClassList("mon-inv-chartbox"); row.Add(cw);
            var ct = new Label("Освоение бюджета и вводы объектов") { pickingMode = PickingMode.Ignore }; ct.AddToClassList("mon-work"); cw.Add(ct);
            invChart = new VisualElement(); invChart.AddToClassList("mon-inv-chart"); invChart.generateVisualContent += DrawCapex; Scrub(invChart, x => Mathf.Lerp(T0, T1, x)); cw.Add(invChart);
            for (int y = (int)T0; y <= (int)T1; y++)
            { var a = new Label(y.ToString()) { pickingMode = PickingMode.Ignore }; a.AddToClassList("mon-tick"); a.style.left = Length.Percent((y - T0) / (T1 - T0) * 100f); invChart.Add(a); }
            invMk.Clear();
            for (int i = 0; i < L.Parts.Count; i++) { var m = new Label(Pt(i).Short) { pickingMode = PickingMode.Ignore }; m.AddToClassList("mon-inv-mk"); invChart.Add(m); invMk.Add(m); }
            var leg = new VisualElement(); leg.AddToClassList("mon-row"); leg.style.marginTop = 4;
            leg.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.5f), "план")); leg.Add(Widgets.LegendItem(Blue, "факт")); leg.Add(Widgets.LegendItem(BlueSoft, "прогноз"));
            leg.Add(Widgets.LegendItem(Green, "ввод в срок")); leg.Add(Widgets.LegendItem(Orange, "ввод позже плана")); cw.Add(leg);
        }
        void K(int i, string cap, string val, string sub, string cls) { kCap[i].text = cap; kVal[i].text = val; kSub[i].text = sub; kVal[i].EnableInClassList("warn", cls == "warn"); kVal[i].EnableInClassList("bad", cls == "bad"); }
        void RefreshInv()
        {
            if (inv == null) return;
            int n = L.Parts.Count; float cap = Capex();
            float rp = Ready(date, false), rf = Ready(date, true), sp = Spent(date, true), spp = Spent(date, false);
            int done = 0, next = -1, last = 0; var os = new OS[n];
            for (int i = 0; i < n; i++)
            {
                os[i] = Obj(i, date);
                if (os[i].Fact >= 0.999f) done++; else if (next < 0 || os[i].FactEnd < os[next].FactEnd) next = i;
                if (os[i].FactEnd > os[last].FactEnd) last = i;
            }
            int ld = Mathf.RoundToInt((os[last].FactEnd - L.Finish) * 365f);
            K(0, "Готовность комплекса", Pct(rf), "по плану " + Pct(rp) + " · взвешено по бюджетам", rf < rp - 0.01f ? "warn" : "");
            K(1, "Освоено", Usd(sp), "из " + Usd(cap) + " · по плану " + Usd(spp), "");
            K(2, "Введено объектов", done + " из " + n, done < n && next >= 0 ? "следующий — " + Pt(next).Name : "комплекс введён", "");
            K(3, "Ближайший ввод", next >= 0 ? IconicFloors.MonthYear(os[next].FactEnd) : "—", next >= 0 ? Pt(next).Name + " · " + EndDev(os[next].EndDays) : "все объекты введены", next >= 0 && os[next].EndDays > 3 ? "warn" : "");
            K(4, "Завершение комплекса", IconicFloors.MonthYear(os[last].FactEnd), ld > 3 ? $"позже плана на {ld} дн. — {Pt(last).Name}" : "в срок по плану", ld > 21 ? "bad" : ld > 3 ? "warn" : "");
            foreach (var ir in irows)
            {
                var o = os[ir.I];
                ir.Done.text = Pct(o.Fact) + " / " + Pct(o.Plan);
                ir.Bar.style.width = Length.Percent(o.Fact * 100f); ir.Mark.style.left = Length.Percent(o.Plan * 100f);
                ir.Due.text = IconicFloors.MonthYear(o.PlanEnd) + " → " + IconicFloors.MonthYear(o.FactEnd);
                ir.Dev.text = o.Text;
                foreach (var c in new[] { "ok", "warn", "bad" }) ir.Row.EnableInClassList(c, c == o.Cls);
                ir.Row.EnableInClassList("sel", ir.I == obj);
            }
            // names of the buildings at their hand-overs on the curve
            var cr = invChart.contentRect;
            if (cr.width > 40f)
            {
                float top = 6f, bot = cr.height - 16f;
                for (int i = 0; i < invMk.Count; i++)
                {
                    float fe = os[i].FactEnd, x = (fe - T0) / (T1 - T0) * cr.width, y = bot - Spent(fe, true) / Mathf.Max(cap, 1f) * (bot - top);
                    invMk[i].style.left = x; invMk[i].style.top = y - 20f - (i % 2) * 11f;
                    invMk[i].style.display = fe >= T0 && fe <= T1 ? DisplayStyle.Flex : DisplayStyle.None;
                }
            }
            invChart.MarkDirtyRepaint();
        }
        /// <summary>Spending of the budget of the complex over time: plan dashed, actual solid up to the survey, forecast after it,
        /// a diamond at every building's hand-over (green in time, orange later than the plan), the survey and the 4D date.</summary>
        void DrawCapex(MeshGenerationContext ctx)
        {
            var r = invChart.contentRect; if (r.width < 40f || L == null) return; var g = ctx.painter2D;
            float cap = Mathf.Max(Capex(), 1f), top = 6f, bot = r.height - 16f, Hh = bot - top;
            float X(float d) => (d - T0) / (T1 - T0) * r.width;
            float Y(float v) => bot - v / cap * Hh;
            g.lineWidth = 1f;
            for (int k = 0; k <= 4; k++) { float y = top + Hh * k / 4f; g.strokeColor = new Color(1f, 1f, 1f, 0.07f); g.BeginPath(); g.MoveTo(new Vector2(0f, y)); g.LineTo(new Vector2(r.width, y)); g.Stroke(); }
            for (int y = (int)T0 + 1; y <= (int)T1; y++) VLine(g, X(y), top, bot, new Color(1f, 1f, 1f, 0.05f), 1f);
            const int n = 90;
            g.strokeColor = PlanLine; g.lineWidth = 1.4f;
            for (int i = 0; i < n; i++) { float d0 = Mathf.Lerp(T0, T1, i / (float)n), d1 = Mathf.Lerp(T0, T1, (i + 1f) / n); Dashed(g, new Vector2(X(d0), Y(Spent(d0, false))), new Vector2(X(d1), Y(Spent(d1, false))), 4f, 3f); }
            g.lineWidth = 2.2f;
            for (int i = 0; i < n; i++)
            {
                float d0 = Mathf.Lerp(T0, T1, i / (float)n), d1 = Mathf.Lerp(T0, T1, (i + 1f) / n);
                if (d0 < Report) { g.strokeColor = Blue; g.BeginPath(); g.MoveTo(new Vector2(X(d0), Y(Spent(d0, true)))); float e = Mathf.Min(d1, Report); g.LineTo(new Vector2(X(e), Y(Spent(e, true)))); g.Stroke(); }
                if (d1 > Report) { g.strokeColor = BlueSoft; float s0 = Mathf.Max(d0, Report); Dashed(g, new Vector2(X(s0), Y(Spent(s0, true))), new Vector2(X(d1), Y(Spent(d1, true))), 2f, 3f); }
            }
            for (int i = 0; i < L.Parts.Count; i++)
            {
                float fe = FactDate(i, 1f); if (fe < T0 || fe > T1) continue;
                Diamond(g, new Vector2(X(fe), Y(Spent(fe, true))), 5f, fe > PlanDate(i, 1f) + 0.01f ? Orange : Green);
            }
            VLine(g, X(Report), top, bot, Orange, 1.4f);
            VLine(g, X(date), top, bot, Color.white, 1.4f);
            g.fillColor = Blue; g.BeginPath(); g.Arc(new Vector2(X(date), Y(Spent(date, true))), 3.5f, 0f, 360f); g.Fill();
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
        static void Ev(VisualElement card, string time, string cam, string text, Color c)
        {
            var r = new VisualElement(); r.AddToClassList("mon-row"); r.AddToClassList("mon-ai"); r.style.marginTop = 8; r.Add(Widgets.Dot(c, true));
            var l = new Label(time + " · " + cam + " — " + text) { pickingMode = PickingMode.Ignore }; l.AddToClassList("note"); l.style.whiteSpace = WhiteSpace.Normal; l.style.flexShrink = 1; r.Add(l);
            card.Add(r);
        }
    }
}
