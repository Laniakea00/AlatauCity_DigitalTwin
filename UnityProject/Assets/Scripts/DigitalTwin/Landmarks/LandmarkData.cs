using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    public enum LStatus { Working, Construction, Preparation, Agreement, Concept }

    /// <summary>One real project of Alatau City placed in its district. Facts come from open sources (state on 08.10.2026);
    /// sites are chosen by the district's function in the master plan — exact plots are not published.</summary>
    public class Landmark
    {
        public string Id, Name, Short, Company, Purpose, Model;
        public int District;                  // 0 Gate, 1 Golden, 2 Growing, 3 Green
        public LStatus Status; public string StatusNote;
        public int StartYear, EndYear;        // visible from StartYear (rises), complete at EndYear
        public bool YearOfficial;             // false = the date is not published, the demo uses EndYear
        public float X, Z, Yaw;               // site (city metres), heading of the long side
        public float Height, Radius;          // for the camera: top of the model, half-size of the site
        public float PadW, PadD;              // the levelled plot the model stands on (local x × z, metres)
        /// <summary>Metres added to the plot's automatic level (the median of the ground round it): a long plot on rolling ground
        /// (the airport) takes the level that moves the ground under the houses round it least. 0 = the median.</summary>
        public float PadLift;
        /// <summary>The parts of the model past its plot follow the ground there (the airport's access road to the street's end and
        /// the bridge to the rail station): LandmarkSystem moves each vertex outside the plot by the ground's height over the plot.</summary>
        public bool Drape;
        /// <summary>An object without a model of its own (Model null): its lot (x × z, metres, axis-aligned round X, Z), where the plan
        /// site stands while it is built (LandmarkSystem.BuildPlanSite: hoarding and the shells of the plan's buildings on it). 0 = none.</summary>
        public float SiteW, SiteD;
        /// <summary>&gt; 0: the landmark brings the district round it (Iconic: the Gate District of its QTwin page, IconicDistrict) — no
        /// generic buildings, film trees or city roads inside the district's area once it stands. 0 = none.</summary>
        public float Ring;
        public float ViewYaw = 210f, ViewPitch = 20f;
        public List<(string k, string v)> Facts = new List<(string, string)>();
        public string Source, SourceDate;
        public Vector3 World;                 // filled at build time: base on the terrain
        /// <summary>Top of the tallest part of the model (world): the label stands over it.</summary>
        public Vector3 Anchor;
        public float Base;                    // level of the plot after the ground was levelled
        public bool IsLrt;
        public Landmark F(string k, string v) { Facts.Add((k, v)); return this; }
        // the second phase of a working object (scenario of the twin, not announced): «Расширение» on the map in those years
        public int S2Start, S2End; public string S2;
        public Landmark Stage2(string what, int a, int b) { S2 = what; S2Start = a; S2End = b; Facts.Add(("2-я очередь", what + " · " + a + "–" + b + " (сценарий двойника)")); return this; }
        /// <summary>The buildings of a complex, each with its own dates (null = one object). Part i of the list is part i + 1 of the model
        /// (LandmarkKit.Part; part 0 is the plot itself). Main = the tower followed floor by floor (TowerProfile).</summary>
        public List<LPart> Parts;
        public Landmark Part(LPart p) { (Parts ??= new List<LPart>()).Add(p); return this; }
        public int Main { get { if (Parts != null) for (int i = 0; i < Parts.Count; i++) if (Parts[i].Tower) return i; return -1; } }
        /// <summary>First start and last hand-over of the whole complex (dates, fractional years); one object: the start of StartYear
        /// and the end of EndYear.</summary>
        public float Begin { get { if (Parts == null) return StartYear; float a = float.MaxValue; foreach (var p in Parts) a = Mathf.Min(a, p.A); return a; } }
        public float Finish { get { if (Parts == null) return EndYear + 1f; float b = float.MinValue; foreach (var p in Parts) b = Mathf.Max(b, p.B); return b; } }
    }

    /// <summary>One building (or the grounds) of a complex: plan dates A … B (fractional years), height, where the camera looks at it, and
    /// what an investor asks about it — use and size, budget, the commercial side, the delay at the last survey and the risk behind it.
    /// Budgets, commercial figures and delays are a scenario of the twin for the demonstration, not the developer's data.</summary>
    public class LPart
    {
        public string Id, Name, Short, Use, Size, Deal, Risk;
        public float A, B, H;
        /// <summary>Budget, millions of US dollars (scenario).</summary>
        public float Capex;
        /// <summary>Delay of the actual against the plan at the survey, years (negative = ahead); Recover: the forecast closes it.</summary>
        public float Delay; public bool Recover;
        /// <summary>Tower: followed floor by floor (TowerProfile). Land: grounds — paving and planting only, no frame.</summary>
        public bool Tower, Land;
        public Vector3 Focus; public float Dist = 260f, Pitch = 30f;
    }

    public static class LandmarkCatalog
    {
        public static readonly string[] StatusText = { "Работает", "Строится", "Подготовка к стройке", "Соглашение (MoU)", "Концепция", "Пусконаладка", "Расширение" };
        public static readonly string[] StatusCls = { "ok", "warn", "warn", "info", "muted", "info", "info" };
        /// <summary>The status with the share built: «Строится 45 %».</summary>
        public static string StatusLabel(Landmark l)
        {
            int si = StatusIdx(l);
            return si == 1 ? StatusText[1] + " " + Mathf.RoundToInt(LandmarkSystem.InYear(l, TwinState.Year) * 100f) + " %" : StatusText[si];
        }
        public static string StatusOf(Landmark l) => StatusText[StatusIdx(l)];
        /// <summary>Today's status from the sources (the construction monitoring map shows the city as designed, the statuses as of today).</summary>
        public static int NowIdx(Landmark l) => (int)l.Status;
        public static string ClsOf(Landmark l) => StatusCls[StatusIdx(l)];
        /// <summary>Status in the year the map shows: built by then → «Работает», under way → «Строится», otherwise today's status.</summary>
        public static int StatusIdx(Landmark l)
        {
            if (l.IsLrt) return (int)l.Status;
            int y = TwinState.Year; float p = LandmarkSystem.InYear(l, y);
            if (p >= 0.999f) return l.S2End > 0 && y >= l.S2Start && y < l.S2End ? 6 : 0;   // working, or its 2nd phase is being built
            if (p >= 0.85f) return 5;                                                          // the last months: commissioning
            if (p > 0f) return 1;
            if (y >= l.StartYear - 2) return 2;                                                // a year or two before: site preparation
            // further ahead: today's status, but a project that is not started yet is never «Работает» / «Строится»
            return l.Status == LStatus.Working || l.Status == LStatus.Construction ? 2 : (int)l.Status;
        }

        /// <summary>Where Iconic Complex stands with the whole Gate District quarter round it — the one source of truth: everything that
        /// follows Iconic (IconicDistrict, IconicPlaza, flags, monitoring, tour and pitch cameras, the film reel, FilmLook's maquette,
        /// IconicFrame) reads these. Stage 7 (approved by the owner 31.10.2026): moved rigidly to the centre of Gate, yaw unchanged.</summary>
        public const float IconicX = -3500f, IconicZ = -19500f, IconicYaw = 270f;
        /// <summary>The place the quarter's world-coordinate data files were made for (gate_q1.*, old fixed cameras and shot lists):
        /// IconicFrame.Shift moves them by (IconicX − IconicDataX, IconicZ − IconicDataZ) at load. Set equal to IconicX/Z once the data
        /// is regenerated at the new place.</summary>
        public const float IconicDataX = -3170f, IconicDataZ = -19080f;

        public static List<Landmark> All()
        {
            var L = new List<Landmark>();
            // ---------------- Gate: finance, business, trade, the transport gate of the city
            L.Add(new Landmark
            {
                Id = "iconic", Name = "Iconic Complex", Short = "Iconic Complex", Company = "Caspian Group · ТОО «Alatau City Iconic Complex» · архитектор SOM",
                Purpose = "«Вертикальный район»: офисы, премиальные резиденции, отель 5*, ритейл и культурные пространства", Model = "iconic",
                District = 0, Status = LStatus.Construction, StatusNote = "стройка начата 26.10.2026",
                StartYear = 2026, EndYear = 2029, YearOfficial = true, X = IconicX, Z = IconicZ, Yaw = IconicYaw, PadW = 270f, PadD = 200f, Ring = 1f, Height = 272f, Radius = 170f, ViewYaw = 25f, ViewPitch = 14f,
                Source = "SOM, Forbes.kz, primeminister.kz", SourceDate = "05.03.2026 / 23.04.2026 / 26.08.2026"
            }.F("Площадь", "276 800 м²").F("Главная башня", "272 м · 56 этажей — офисы и резиденции").F("Вторая башня", "80 м · 21 этаж — ступенчатая «пирамида» с озеленёнными террасами: отель 5* и брендированные резиденции")
             .F("Подиум", "18 м · 3 этажа · ≈ 58 000 м² — два павильона-клина с садами на кровле, бассейн на террасе, площадь с амфитеатром")
             .F("Офисные корпуса", "6 корпусов · 4 этажа · 17,7 м — с внутренними дворами, в квартале вокруг площади; ≈ 58 100 м² по модели, в составе 276 800 м² комплекса").F("Офисы и жильё", "офисы 57 600 м² · резиденции 40 300 м² · отель 21 806 м²").F("Конструкции", "сейсмостойкий каркас с демпферами").F("Инвестиции", "> $800 млн (по другим данным > $1 млрд), без бюджетных денег")
             .F("Токенизация", "Iconic Tower — до $50 млн на KASE (план до конца 2026)").F("Сроки", "начало стройки — 10.2026, сдача — конец 2029").Stage2("культурный центр на площади", 2037, 2039)
             // the buildings of the complex with their own dates: the hotel opens more than a year before the tower (first revenue), the east
             // retail block a quarter before it, the west one and the grounds with it (scenario of the twin; the complex keeps the published
             // dates of the registry: start 10.2026, completion at the end of 2029 — the last hand-over is in December 2029)
             .Part(new LPart { Id = "t1", Name = "Башня T1", Short = "T1", Use = "офисы и премиальные резиденции", Size = "272 м · 56 этажей · 97 900 м²", Tower = true,
                               A = 2026.82f, B = 2029.92f, H = 272f, Capex = 480f, Delay = 0.14f, Recover = true, Focus = new Vector3(-84f, 110f, 46f), Dist = 560f, Pitch = 16f,
                               Deal = "предпродажи резиденций 38 % · аренда офисов 24 %", Risk = "Каркас отстаёт из-за зимнего бетонирования; вторая смена на армировании закрывает отставание" })
             .Part(new LPart { Id = "t2", Name = "Отель T2", Short = "T2", Use = "отель 5* и брендированные резиденции", Size = "80 м · 21 этаж · террасы · 21 806 м² · 220 номеров",
                               A = 2026.95f, B = 2028.45f, H = 81f, Capex = 150f, Delay = -0.04f, Focus = new Vector3(40f, 28f, 42f), Dist = 270f, Pitch = 24f,
                               Deal = "договор управления с международным оператором; продажи номеров открываются за 3 месяца до ввода", Risk = "Опережение: каркас закончен раньше — отель даёт первую выручку комплекса" })
             .Part(new LPart { Id = "re", Name = "Павильон · восточный", Short = "Павильон В", Use = "торговая галерея, рестораны, бассейн на террасе", Size = "клин до 32 м · 4 уровня · ≈ 30 000 м²",
                               A = 2027.3f, B = 2029.7f, H = 32f, Capex = 95f, Delay = 0.075f, Focus = new Vector3(-66f, 12f, -50f), Dist = 240f, Pitch = 32f,
                               Deal = "предварительная аренда 61 %, якорный арендатор — супермаркет", Risk = "Поставка модулей витража задерживается на 4 недели — ввод сдвигается" })
             .Part(new LPart { Id = "rw", Name = "Павильон · западный", Short = "Павильон З", Use = "магазины, фуд-холл, сад на кровле", Size = "клин до 22 м · 3 уровня · ≈ 28 000 м²",
                               A = 2028.5f, B = 2029.85f, H = 22f, Capex = 70f, Focus = new Vector3(66f, 10f, -50f), Dist = 240f, Pitch = 32f,
                               Deal = "предварительная аренда 35 %", Risk = "Старт после ввода отеля: бригады и краны переходят с T2" })
             .Part(new LPart { Id = "gr", Name = "Площадь, амфитеатр и сад", Short = "Площадь", Use = "общественное пространство, открытое городу", Size = "≈ 5 га · амфитеатр, фонтаны, деревья", Land = true,
                               A = 2029.3f, B = 2029.92f, H = 9f, Capex = 18f, Focus = new Vector3(0f, 0f, -46f), Dist = 380f, Pitch = 46f,
                               Deal = "входит в стоимость комплекса; повышает арендные ставки ритейла", Risk = "Работы идут вместе с фасадом башни; деревья сажают осенью" }));
            L.Add(new Landmark
            {
                Id = "lotte_l7", Name = "L7 by Lotte", Short = "L7 by Lotte", Company = "Lotte Hotels & Resorts (Южная Корея)",
                Purpose = "Городской отель на 180 номеров", Model = "hotel_l7",
                District = 0, Status = LStatus.Agreement, StatusNote = "договорённость 08.2026; 14.09.2026 — окончательных соглашений нет",
                // Gate v1.1 (spec gate.json l7_lotte, move to (−3021.5, −19602.3)): the corner of the Gate avenue and the East street, across
                // from Iconic; the plot is the spec's footprint (x −3075 … −2968, z −19644.6 … −19560: 107 × 84.6 m, axis-aligned), the
                // drop-off faces its access street in the south (−z). One year source: the spec's base year (years[0] = 2031, built
                // 2029–2031); the data's buildings on the lot must carry it too (PrepareGround logs the years of the data it replaces)
                StartYear = 2029, EndYear = 2031, YearOfficial = false, X = -3021.5f, Z = -19602.3f, Yaw = 0f, PadW = 107f, PadD = 84.6f, Height = 100f, Radius = 58f, ViewYaw = 220f, ViewPitch = 16f,
                Source = "Kapital.kz, bes.media", SourceDate = "14.09.2026"
            }.F("Номера", "180").F("Инвестиции", "> $200 млн").F("Сроки", "не объявлены (в демо — 2031, по плану района Gate)"));
            L.Add(new Landmark
            {
                Id = "pepsico", Name = "Завод PepsiCo", Short = "PepsiCo", Company = "PepsiCo Kazakhstan",
                Purpose = "Производство картофельных чипсов и снеков", Model = null,
                District = 0, Status = LStatus.Construction, StatusNote = "активная фаза строительства (сводка правительства 26.08.2026)",
                // Gate v1.1 (spec gate.json pepsico, move to (−3078.5, −22541.2), yaw −74°): the plant in Yntymak is its own hall in OSM
                // (building bid 48572 of the twin, 28 041 m², 347 × 82 m), which stays an existing building — no model, no plot of its own;
                // the entry keeps the card, the label and the monitoring mark on the hall. Years of the registry: works from 2024, first
                // stage and full launch in 2026 (registry.json pepsico years: start 2024, first_stage 2026, completion 2026)
                StartYear = 2024, EndYear = 2026, YearOfficial = true, X = -3078.5f, Z = -22541.2f, Yaw = -74f, PadW = 0f, PadD = 0f, Height = 15f, Radius = 180f, ViewYaw = 200f, ViewPitch = 24f,
                Source = "Tribune.kz, Tengrinews, Kapital.kz", SourceDate = "22.07.2024 / 02.06.2026 / 26.08.2026"
            }.F("Инвестиции", "≈ $360 млн (81 млрд ₸); первый этап $160 млн").F("Сырьё", "210 тыс. т картофеля в год").F("Рабочие места", "≈ 900")
             .F("Сроки", "стройка с 06.2024; техзапуск — весна 2026, полная мощность — лето 2026"));
            L.Add(new Landmark
            {
                Id = "griffin", Name = "Griffin Logopark Almaty", Short = "Griffin Logopark", Company = "Griffin Partners · кредит ЕАБР",
                Purpose = "Логопарк класса А в районе Gate, у дублёра трассы А-3", Model = null,
                District = 0, Status = LStatus.Construction, StatusNote = "стройка с 07.2026, первый камень — 25.09.2026",
                // Stage 7: one Griffin in the city — the sheds are the Gate plan's own buildings on lot L00067 (spec object griffin_logopark,
                // years [2027, …]); no model, no plot of its own: the entry keeps the card, the label and the monitoring mark at the lot, and
                // its lot (the spec's footprint x −2680 … −2365, z −19300 … −18902: 315 × 398 m) has a plan site while it is built
                StartYear = 2026, EndYear = 2027, YearOfficial = true, X = -2522.5f, Z = -19101f, Yaw = 0f, PadW = 0f, PadD = 0f, SiteW = 315f, SiteD = 398f, Height = 15f, Radius = 200f, ViewYaw = 200f, ViewPitch = 26f,
                Source = "ЕАБР, bizmedia.kz", SourceDate = "10.08.2026 / 25.09.2026"
            }.F("Инвестиции", "$125 млн").F("Склады", "≈ 120 тыс. м²").F("Рабочие места", "≈ 600").F("Сроки", "1-я фаза — I кв. 2027"));

            // ---------------- Golden: science, education, medicine
            L.Add(new Landmark
            {
                Id = "kaist", Name = "KAIST Kazakhstan · кампус", Short = "KAIST Kazakhstan", Company = "KAIST (Южная Корея) · ACA",
                Purpose = "Технологический университет и кампус до 40 тыс. студентов (Академгородок)", Model = "campus",
                District = 1, Status = LStatus.Preparation, StatusNote = "подготовка площадки, старт стройки — 12.12.2026",
                // stage 7 (golden.json qaist, owner: «перенести» 31.10): south of the Көктерек space centre on its own 420 × 360 m lot,
                // turned with the quarters round it (the local streets of Golden go round the plot); was (−1457, −12698), yaw 11°
                StartYear = 2026, EndYear = 2030, YearOfficial = false, X = -150f, Z = -11100f, Yaw = -4.5f, PadW = 420f, PadD = 360f, Height = 69f, Radius = 210f, ViewYaw = 190f, ViewPitch = 22f,
                Source = "Kazinform, Kapital.kz", SourceDate = "29.09.2025 / 09.2026"
            }.F("Студенты", "до 40 000 (кампус Golden)").F("Сроки", "в демо — 12.2026 → 06.2030").Stage2("общежития и лаборатории", 2034, 2037)
             // the buildings of the campus with their own dates (scenario of the twin, as on the campus's monitoring page): the park and the
             // lake first, the main hall ready for the September 2029 intake, B1 and the laboratories after it, the north block last; handover 14.06.2030
             .Part(new LPart { Id = "b1", Name = "Библиотечная башня B1", Short = "B1", Use = "библиотека, аудитория, лаборатории", Size = "69 м · 13 этажей · ≈ 19 000 м²", Tower = true,
                               A = 2027.05f, B = 2029.75f, H = 69f, Capex = 95f, Delay = 0.1f, Recover = true, Focus = new Vector3(150f, 30f, 20f), Dist = 240f, Pitch = 18f,
                               Deal = "гранты на оборудование лабораторий; читальные залы открыты району", Risk = "Каркас отстаёт из-за зимнего бетонирования; вторая смена закрывает отставание" })
             .Part(new LPart { Id = "mh", Name = "Главный корпус", Short = "Главный", Use = "аудитории, ректорат, культурный центр", Size = "150 × 56 м · 39 м · ≈ 34 000 м²",
                               A = 2026.95f, B = 2028.95f, H = 40f, Capex = 120f, Delay = -0.03f, Focus = new Vector3(-20f, 14f, -122f), Dist = 280f, Pitch = 26f,
                               Deal = "приём первых 3 000 студентов в сентябре 2029", Risk = "Опережение: витражи смонтированы раньше — корпус готов к набору" })
             .Part(new LPart { Id = "lab", Name = "Лабораторный корпус", Short = "Лаборатории", Use = "лаборатории с чистыми помещениями, мастерские", Size = "до 19 м · ≈ 28 000 м²",
                               A = 2027.45f, B = 2029.55f, H = 19f, Capex = 110f, Delay = 0.07f, Focus = new Vector3(-160f, 9f, 25f), Dist = 270f, Pitch = 32f,
                               Deal = "40 % площадей — партнёрские лаборатории компаний", Risk = "Оборудование чистых помещений поставляется с опозданием — ввод сдвигается" })
             .Part(new LPart { Id = "nb", Name = "Северный учебный корпус", Short = "Северный", Use = "аудитории и классы второй очереди", Size = "до 20 м · ≈ 26 000 м²",
                               A = 2028.7f, B = 2030.45f, H = 20f, Capex = 70f, Focus = new Vector3(-15f, 9f, 128f), Dist = 290f, Pitch = 30f,
                               Deal = "набор до 12 000 студентов", Risk = "Стартует, когда главный корпус закрывает контур: бригады переходят с него" })
             .Part(new LPart { Id = "sp", Name = "Спортивное ядро", Short = "Спорт", Use = "стадион с беговыми дорожками, трибуна", Size = "овал 112 × 68 м · 1 200 мест",
                               A = 2029.1f, B = 2029.85f, H = 10f, Capex = 15f, Focus = new Vector3(140f, 3f, -122f), Dist = 220f, Pitch = 40f,
                               Deal = "открыт для жителей района вечером и в выходные", Risk = "Работы по графику" })
             .Part(new LPart { Id = "pk", Name = "Парк и озеро", Short = "Парк", Use = "парк кампуса: озеро с островом и фонтанами, рощи, аллеи", Size = "≈ 9 га · озеро 1,4 га", Land = true,
                               A = 2026.95f, B = 2027.3f, H = 20f, Capex = 12f, Focus = new Vector3(-15f, 4f, -5f), Dist = 320f, Pitch = 42f,
                               Deal = "зелёный кампус с первого дня: участок не превращается в стройплощадку", Risk = "Выполнен до начала корпусов" }));
            L.Add(new Landmark
            {
                Id = "medcluster", Name = "Медицинский кластер Golden", Short = "Медкластер", Company = "ACA · партнёры не объявлены",
                Purpose = "Клиники, диагностика и медицинские исследования", Model = "hospital",
                District = 1, Status = LStatus.Concept, StatusNote = "в функциональном зонировании генплана",
                // stage 7: the centre of its lot of golden.json (medcluster_golden, 16 ha), its long side along the lot's (was −1075, −10343, 105.2°)
                StartYear = 2030, EndYear = 2033, YearOfficial = false, X = -1175.9f, Z = -10460.9f, Yaw = -80.6f, PadW = 280f, PadD = 210f, Height = 48f, Radius = 140f, ViewYaw = 200f, ViewPitch = 22f,
                Source = "Kazinform", SourceDate = "29.09.2025"
            }.F("Сроки", "не объявлены (в демо — 2033)").Stage2("реабилитационный центр", 2036, 2039));
            L.Add(new Landmark
            {
                Id = "kpark", Name = "K-Park", Short = "K-Park", Company = "Корейские партнёры · ACA",
                Purpose = "Корейский парк: сад, культурно-деловой центр, музей, смотровая башня 65 м · 10 га", Model = "kpark",
                District = 1, Status = LStatus.Construction, StatusNote = "первый камень — 14.09.2025",
                // owner 05.11.2026, second round («всё ещё в воде … передвинь парк к городу и людям»): into the housing of northern
                // Golden (−2300, −7300), no water within 330 m. First round: moved off the Terenkara flood strip (18 % of the old pad was river
                // and its 35 m water belt) to dry land in the city park «Төменгі Тереңқара», 1.5 km west of the Golden centre (golden.json
                // k_park, golden_build KPARK_XZ); was (−465, −8276), before stage 7 (−515, −8826). Height: the 65 m observation tower
                StartYear = 2025, EndYear = 2027, YearOfficial = false, X = -2300f, Z = -7300f, Yaw = 0f, PadW = 360f, PadD = 280f, Height = 65f, Radius = 190f, ViewYaw = 200f, ViewPitch = 30f,
                Source = "Kazinform", SourceDate = "14.09.2025"
            }.F("Площадь", "10 га").F("Сроки", "завершение не объявлено (в демо — 2027)").Stage2("вторая очередь парка", 2031, 2033));
            L.Add(new Landmark
            {
                Id = "mars", Name = "Завод Mars Petcare", Short = "Mars Petcare", Company = "Mars Petcare Kazakhstan",
                Purpose = "Производство кормов для домашних животных", Model = "food_mars",
                District = 2, Status = LStatus.Construction, StatusNote = "работы начаты (сводка 26.08.2026)",
                // owner 02.11.2026 (growing_e.json mars_petcare): moved from the scheme lot at km 40 of the А-3 (−483, −2231; its 300 m gap to
                // the new quarters left 3.7 ha) into the Growing-East industrial belt west of Sunny Paper, ≥ 300 m from housing; was (8806, 1370), −81.7°
                StartYear = 2026, EndYear = 2028, YearOfficial = false, X = 6622f, Z = 1300f, Yaw = -90f, PadW = 430f, PadD = 300f, Height = 42f, Radius = 215f, ViewYaw = 200f, ViewPitch = 24f,
                Source = "DigitalBusiness.kz, 24.kz", SourceDate = "20.02.2026 / 26.08.2026"
            }.F("Инвестиции", "≈ $180–185 млн (в соцсетях — $160 млн)").F("Сроки", "не объявлены (в демо — 2028)").Stage2("второй цех", 2032, 2034));

            // ---------------- Growing: export industry and logistics — in two industrial belts on the sides of the city (east along the
            // railway, west by the airport and BAKAD); PepsiCo and Mars Petcare belong here too (plants, not the business gate); Griffin stands
            // in Gate since Stage 7, as the plan's own sheds
            L.Add(new Landmark
            {
                Id = "sunny_paper", Name = "Sunny Paper", Short = "Sunny Paper", Company = "Sunny Paper",
                Purpose = "Бумажное производство", Model = "paper",
                District = 2, Status = LStatus.Construction, StatusNote = "активная фаза (сводка 26.08.2026)",
                StartYear = 2026, EndYear = 2028, YearOfficial = false, X = 7574.6f, Z = 1488f, Yaw = -81.7f, PadW = 440f, PadD = 280f, Height = 62f, Radius = 210f, ViewYaw = 200f, ViewPitch = 24f,
                Source = "24.kz", SourceDate = "26.08.2026"
            }.F("Параметры", "не раскрыты").F("Сроки", "не объявлены (в демо — 2028)").Stage2("вторая бумагоделательная линия", 2033, 2036));
            L.Add(new Landmark
            {
                Id = "danaflex", Name = "DanaFlex", Short = "DanaFlex", Company = "DanaFlex",
                Purpose = "Гибкая упаковка", Model = "packaging",
                District = 2, Status = LStatus.Construction, StatusNote = "работы начаты (сводка 26.08.2026)",
                StartYear = 2026, EndYear = 2027, YearOfficial = false, X = 6091.1f, Z = 711f, Yaw = -81.7f, PadW = 300f, PadD = 200f, Height = 18f, Radius = 150f, ViewYaw = 200f, ViewPitch = 26f,
                Source = "24.kz", SourceDate = "26.08.2026"
            }.F("Параметры", "не раскрыты").F("Сроки", "не объявлены (в демо — 2027)"));
            L.Add(new Landmark
            {
                Id = "gtrans", Name = "G-Trans Service", Short = "G-Trans", Company = "G-Trans Service",
                Purpose = "Логистика и сервис грузового транспорта", Model = "logistics_gtrans",
                District = 2, Status = LStatus.Construction, StatusNote = "работы начаты (сводка 26.08.2026)",
                StartYear = 2026, EndYear = 2027, YearOfficial = false, X = 7882, Z = 945, Yaw = -81.7f, PadW = 290f, PadD = 220f, Height = 15f, Radius = 150f, ViewYaw = 200f, ViewPitch = 26f,
                Source = "24.kz", SourceDate = "26.08.2026"
            }.F("Параметры", "не раскрыты").F("Сроки", "не объявлены (в демо — 2027)"));
            L.Add(new Landmark
            {
                Id = "tlc", Name = "ТЛЦ «Жетыген»", Short = "ТЛЦ «Жетыген»", Company = "Исткомтранс",
                Purpose = "Транспортно-логистический центр у ж/д Жетыген – Казыбек-бек", Model = "rail_terminal",
                District = 2, Status = LStatus.Construction, StatusNote = "строится",
                StartYear = 2025, EndYear = 2027, YearOfficial = false, X = 7840f, Z = 9941f, Yaw = -77.5f, PadW = 520f, PadD = 220f, Height = 25f, Radius = 260f, ViewYaw = 215f, ViewPitch = 24f,
                Source = "bes.media, Tengrinews", SourceDate = "11.06.2024 / 23.09.2025"
            }.F("Инвестиции", "+$150 млн (2024); 43 млрд ₸").F("Сроки", "не объявлены (в демо — 2027)").Stage2("контейнерный терминал", 2030, 2032));
            L.Add(new Landmark
            {
                Id = "ps_arna", Name = "ПС «Арна» 220/110 кВ", Short = "ПС «Арна»", Company = "Фаза 1 инфраструктуры Алатау",
                Purpose = "Главная понизительная подстанция первой очереди", Model = "substation",
                District = 2, Status = LStatus.Construction, StatusNote = "строится; ещё 6 ПС в проектировании",
                StartYear = 2026, EndYear = 2027, YearOfficial = false, X = 1721, Z = 360, Yaw = 280.9f, PadW = 244f, PadD = 164f, Height = 32f, Radius = 150f, ViewYaw = 210f, ViewPitch = 28f,
                Source = "primeminister.kz, Qazinform", SourceDate = "15.01.2026 / 03.02.2026"
            }.F("Напряжение", "220/110 кВ").F("Фаза 1 (2026–2027/28)", "21 проект, 365,1 млрд ₸").F("Спрос", "2 064 МВт к 2030, 4 164 МВт к 2050")
             .F("Расположение", "в открытых данных не опубликовано"));
            L.Add(new Landmark
            {
                Id = "gtes", Name = "ГТЭС Doosan 2 × 250 МВт", Short = "ГТЭС Doosan", Company = "Doosan Enerbility · KEPCO · GGGI",
                Purpose = "Газотурбинная электростанция с переходом на водород (ГЧП)", Model = "power",
                District = 2, Status = LStatus.Agreement, StatusNote = "14.09.2026 — переговоры, окончательных соглашений нет",
                StartYear = 2028, EndYear = 2031, YearOfficial = false, X = 10100f, Z = 4780f, Yaw = 0f, PadW = 340f, PadD = 240f, Height = 62f, Radius = 175f, ViewYaw = 210f, ViewPitch = 22f,
                Source = "bes.media, Kapital.kz", SourceDate = "14.09.2026"
            }.F("Мощность", "2 × 250 МВт").F("Сроки", "не объявлены (в демо — 2031)").Stage2("перевод турбин на водород", 2035, 2039));

            L.Add(new Landmark
            {
                Id = "airport", Name = "Аэропорт Алатау", Short = "Аэропорт", Company = "Оператор не определён · место выбрано 02.11.2026",
                Purpose = "Международный аэропорт: две ВПП, между ними терминал в форме самолёта носом к городу; вокзал «Алатау» и конечная ЛРТ у въезда", Model = "airport",
                District = 2, Status = LStatus.Concept, StatusNote = "место выбрано 02.11.2026 (схема Growing-запад); стройка 2041–2045",
                // Owner's decision of 02.11.2026 (growing_w.json objects airport_alatau, city.json airport_new): the airport and the plateau
                // industry swapped places — the plot (3 800 × 1 600 m, the twin's concept: two runways 3 400 and 2 650 m on 100°/280°, between
                // them the airliner-shaped terminal, its glazed nose the landside hall toward the city) north of the Аэропортовая
                // магистраль, ≥ 300 m off the 500 kV lines, 5.6 km nearer the city than the site of 31.10 (−16000, 1500; one runway
                // 4 000 m on 095°). Yaw 280: local −z (the nose, the landside gate at (−450, −1900)) toward 100°; the gate road of the
                // map (s_air_access) comes from the Дорога плато, the LRT terminus and the rail station «Алатау» are across the trunk.
                // Moved 09.11.2026 to the master plan drawing (decree 727): centre (−7650, 8900), runways north – south, yaw 0, the nose south. Was (−10350, 4000), yaw 280.
                // A construction site like the other landmarks: works from 2041 to 2045 (city.json airport_new: built 2041–2045, open
                // 2045); the planes fly from 2045. Was (−15955.8, 1867.55), yaw 95, one runway (31.10.2026); before that (−5900, 8300), yaw 30.
                StartYear = 2041, EndYear = 2045, YearOfficial = false, X = -7650f, Z = 8900f, Yaw = 0f, PadW = 1600f, PadD = 3800f, Height = 98f, Radius = 1900f, ViewYaw = 300f, ViewPitch = 30f,
                Source = "чертёж генплана № 727; 15 млн пасс./год, после 2040, у западной границы", SourceDate = "09.09.2025"
            }.F("ВПП", "две: 3 400 и 2 650 м, север – юг").F("Терминал", "в форме самолёта между ВПП, нос — зал прилёта и вылета к городу").F("Стоянки", "32 телетрапа + 6 перронных, грузовой терминал").F("Подъезд", "с юга от Аэропортовой магистрали; ЛРТ и аэроэкспресс — у въезда").F("Пассажиры", "15 млн в год (генплан)").F("Сроки", "после 2040 (генплан); в двойнике — стройка 2041–2045, открытие в 2045"));

            // ---------------- Green: tourism and recreation on Kapshagay
            L.Add(new Landmark
            {
                Id = "marina", Name = "Марина Капшагай", Short = "Марина", Company = "ACA · инвесторы не объявлены",
                Purpose = "Яхтенная марина и набережная туристического района", Model = "marina",
                District = 3, Status = LStatus.Concept, StatusNote = "концепция Green District, сроков нет",
                StartYear = 2033, EndYear = 2037, YearOfficial = false, X = 4825f, Z = 25272f, Yaw = 315f, PadW = 200f, PadD = 140f, Height = 14f, Radius = 180f, ViewYaw = 160f, ViewPitch = 22f,
                Source = "Kazinform, Astana Times", SourceDate = "29.09.2025 / 04.09.2026"
            }.F("Состав", "марина, клуб, набережная").F("Сроки", "не объявлены (в демо — 2037)"));
            // the round complex on the east shore, as drawn on the master plan (decree 727); map zone z_ring
            L.Add(new Landmark
            {
                Id = "ring_resort", Name = "Круглый курорт Green", Short = "Круглый курорт", Company = "инвесторы не объявлены",
                Purpose = "Курортный комплекс на восточном берегу: кольца отелей вокруг лагуны, казино на острове", Model = "ring_resort",
                District = 3, Status = LStatus.Concept, StatusNote = "контур по чертежу генплана, состав — модель qTwin",
                StartYear = 2036, EndYear = 2042, YearOfficial = false, X = 14800f, Z = 20150f, Yaw = 0f, PadW = 1800f, PadD = 1800f, Height = 48f, Radius = 950f, ViewYaw = 200f, ViewPitch = 32f,
                Source = "чертёж генплана № 727", SourceDate = "09.09.2025"
            }.F("Состав", "казино, отели, лагуна, причалы").F("Сроки", "в демо — 2036–2042"));
            return L;
        }

        public static Landmark Lrt() => new Landmark
        {
            Id = "lrt", Name = "ЛРТ Алматы – Алатау – Конаев", Short = "ЛРТ", Company = "Генплан Alatau City · ACA",
            Purpose = "Лёгкое метро на эстакаде: ствол через Gate, Golden, Growing и Green, две ветки на запад", Model = "lrt",
            District = -1, Status = LStatus.Concept, StatusNote = "заложено в генплан; метро не рассматривается (05.2026)", IsLrt = true,
            StartYear = 2029, EndYear = 2041, YearOfficial = false, Height = 12f, Radius = 600f, ViewYaw = 200f, ViewPitch = 18f,
            Source = "Kapital.kz", SourceDate = "21.05.2026"
        };
    }
}
