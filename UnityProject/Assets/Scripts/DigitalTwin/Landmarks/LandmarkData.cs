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
    }

    public static class LandmarkCatalog
    {
        public static readonly string[] StatusText = { "Работает", "Строится", "Подготовка к стройке", "Соглашение (MoU)", "Концепция", "Пусконаладка", "Расширение" };
        public static readonly string[] StatusCls = { "ok", "warn", "warn", "info", "muted", "info", "info" };
        /// <summary>The status with the share built: «Строится 45 %».</summary>
        public static string StatusLabel(Landmark l)
        {
            int si = StatusIdx(l);
            return si == 1 ? StatusText[1] + " " + Mathf.RoundToInt(LandmarkSystem.Progress(l, TwinState.Year) * 100f) + " %" : StatusText[si];
        }
        public static string StatusOf(Landmark l) => StatusText[StatusIdx(l)];
        public static string ClsOf(Landmark l) => StatusCls[StatusIdx(l)];
        /// <summary>Status in the year the map shows: built by then → «Работает», under way → «Строится», otherwise today's status.</summary>
        public static int StatusIdx(Landmark l)
        {
            if (l.IsLrt) return (int)l.Status;
            int y = TwinState.Year; float p = LandmarkSystem.Progress(l, y);
            if (p >= 0.999f) return l.S2End > 0 && y >= l.S2Start && y < l.S2End ? 6 : 0;   // working, or its 2nd phase is being built
            if (p >= 0.85f) return 5;                                                          // the last months: commissioning
            if (p > 0f) return 1;
            if (y >= l.StartYear - 2) return 2;                                                // a year or two before: site preparation
            // further ahead: today's status, but a project that is not started yet is never «Работает» / «Строится»
            return l.Status == LStatus.Working || l.Status == LStatus.Construction ? 2 : (int)l.Status;
        }

        public static List<Landmark> All()
        {
            var L = new List<Landmark>();
            // ---------------- Gate: finance, business, trade, the transport gate of the city
            L.Add(new Landmark
            {
                Id = "iconic", Name = "Iconic Complex", Short = "Iconic Complex", Company = "Caspian Group · ТОО «Alatau City Iconic Complex» · архитектор SOM",
                Purpose = "«Вертикальный район»: офисы, премиальные резиденции, отель 5*, ритейл и культурные пространства", Model = "iconic",
                District = 0, Status = LStatus.Preparation, StatusNote = "на 26.08.2026 — подготовка к строительству; старт заявлялся на май 2026",
                StartYear = 2027, EndYear = 2030, YearOfficial = true, X = -2567, Z = -20654, Yaw = 105.2f, PadW = 270f, PadD = 200f, Height = 272f, Radius = 135f, ViewYaw = 205f, ViewPitch = 14f,
                Source = "SOM, Forbes.kz, primeminister.kz", SourceDate = "05.03.2026 / 23.04.2026 / 26.08.2026"
            }.F("Площадь", "276 800 м²").F("Главная башня", "272 м · 56 этажей — офисы и резиденции").F("Вторая башня", "80 м — отель 5* и брендированные резиденции")
             .F("Ритейл", "51 890 м² — два низких корпуса до 32 м с зелёными кровлями").F("Офисы и жильё", "офисы 57 600 м² · резиденции 40 300 м² · отель 21 806 м²").F("Конструкции", "сейсмостойкий каркас с демпферами").F("Инвестиции", "> $800 млн (по другим данным > $1 млрд), без бюджетных денег")
             .F("Токенизация", "Iconic Tower — до $50 млн на KASE (план до конца 2026)").F("Сроки", "сдача конец 2029 – начало 2030").Stage2("культурный центр на площади", 2037, 2039));
            L.Add(new Landmark
            {
                Id = "lotte_l7", Name = "L7 by Lotte", Short = "L7 by Lotte", Company = "Lotte Hotels & Resorts (Южная Корея)",
                Purpose = "Городской отель на 180 номеров", Model = "hotel_l7",
                District = 0, Status = LStatus.Agreement, StatusNote = "договорённость 08.2026; 14.09.2026 — окончательных соглашений нет",
                StartYear = 2028, EndYear = 2030, YearOfficial = false, X = -2300, Z = -19600, Yaw = 4.2f, PadW = 90f, PadD = 70f, Height = 100f, Radius = 45f, ViewYaw = 220f, ViewPitch = 16f,
                Source = "Kapital.kz, bes.media", SourceDate = "14.09.2026"
            }.F("Номера", "180").F("Инвестиции", "> $200 млн").F("Сроки", "не объявлены (в демо — 2030)"));
            L.Add(new Landmark
            {
                Id = "pepsico", Name = "Завод PepsiCo", Short = "PepsiCo", Company = "PepsiCo Kazakhstan",
                Purpose = "Производство картофельных чипсов и снеков", Model = "food_pepsico",
                District = 2, Status = LStatus.Construction, StatusNote = "активная фаза строительства (сводка правительства 26.08.2026)",
                StartYear = 2025, EndYear = 2027, YearOfficial = true, X = 8500, Z = 940, Yaw = -81.7f, PadW = 430f, PadD = 300f, Height = 40f, Radius = 215f, ViewYaw = 200f, ViewPitch = 24f,
                Source = "Kapital.kz, 24.kz", SourceDate = "20.05.2025 / 26.08.2026"
            }.F("Инвестиции", "≈ $360 млн (81 млрд ₸); первый этап $160 млн").F("Сырьё", "210 тыс. т картофеля в год").F("Рабочие места", "≈ 900")
             .F("Сроки", "1-я очередь — 03.2026, полная мощность — 09.2027").Stage2("новые линии", 2030, 2032));
            L.Add(new Landmark
            {
                Id = "griffin", Name = "Griffin Logopark Almaty", Short = "Griffin Logopark", Company = "Griffin Partners · кредит ЕАБР",
                Purpose = "Логопарк класса А в западном промышленном поясе, у БАКАД", Model = "logistics_griffin",
                District = 2, Status = LStatus.Construction, StatusNote = "стройка с 07.2026, первый камень — 25.09.2026",
                StartYear = 2026, EndYear = 2027, YearOfficial = true, X = -5673, Z = 1715, Yaw = 16.6f, PadW = 380f, PadD = 420f, Height = 15f, Radius = 210f, ViewYaw = 200f, ViewPitch = 26f,
                Source = "ЕАБР, bizmedia.kz", SourceDate = "10.08.2026 / 25.09.2026"
            }.F("Инвестиции", "$125 млн").F("Склады", "≈ 120 тыс. м²").F("Рабочие места", "≈ 600").F("Сроки", "1-я фаза — I кв. 2027").Stage2("третий склад", 2031, 2033));

            // ---------------- Golden: science, education, medicine
            L.Add(new Landmark
            {
                Id = "kaist", Name = "KAIST Kazakhstan · кампус", Short = "KAIST Kazakhstan", Company = "KAIST (Южная Корея) · ACA",
                Purpose = "Технологический университет и кампус до 40 тыс. студентов (Академгородок)", Model = "campus",
                District = 1, Status = LStatus.Concept, StatusNote = "прорабатывается",
                StartYear = 2029, EndYear = 2032, YearOfficial = false, X = -1457, Z = -12698, Yaw = 45.6f, PadW = 420f, PadD = 360f, Height = 58f, Radius = 210f, ViewYaw = 190f, ViewPitch = 22f,
                Source = "Kazinform, Kapital.kz", SourceDate = "29.09.2025 / 09.2026"
            }.F("Студенты", "до 40 000 (кампус Golden)").F("Сроки", "не объявлены (в демо — 2032)").Stage2("общежития и лаборатории", 2034, 2037));
            L.Add(new Landmark
            {
                Id = "medcluster", Name = "Медицинский кластер Golden", Short = "Медкластер", Company = "ACA · партнёры не объявлены",
                Purpose = "Клиники, диагностика и медицинские исследования", Model = "hospital",
                District = 1, Status = LStatus.Concept, StatusNote = "в функциональном зонировании генплана",
                StartYear = 2030, EndYear = 2033, YearOfficial = false, X = -1075, Z = -10343, Yaw = 105.2f, PadW = 280f, PadD = 210f, Height = 48f, Radius = 140f, ViewYaw = 200f, ViewPitch = 22f,
                Source = "Kazinform", SourceDate = "29.09.2025"
            }.F("Сроки", "не объявлены (в демо — 2033)").Stage2("реабилитационный центр", 2036, 2039));
            L.Add(new Landmark
            {
                Id = "kpark", Name = "K-Park", Short = "K-Park", Company = "Корейские партнёры · ACA",
                Purpose = "Корейский парк и павильоны, 10 га", Model = "kpark",
                District = 1, Status = LStatus.Construction, StatusNote = "первый камень — 14.09.2025",
                StartYear = 2025, EndYear = 2027, YearOfficial = false, X = -515, Z = -8826, Yaw = 128f, PadW = 360f, PadD = 280f, Height = 14f, Radius = 180f, ViewYaw = 200f, ViewPitch = 28f,
                Source = "Kazinform", SourceDate = "14.09.2025"
            }.F("Площадь", "10 га").F("Сроки", "завершение не объявлено (в демо — 2027)").Stage2("вторая очередь парка", 2031, 2033));
            L.Add(new Landmark
            {
                Id = "mars", Name = "Завод Mars Petcare", Short = "Mars Petcare", Company = "Mars Petcare Kazakhstan",
                Purpose = "Производство кормов для домашних животных", Model = "food_mars",
                District = 2, Status = LStatus.Construction, StatusNote = "работы начаты (сводка 26.08.2026)",
                StartYear = 2026, EndYear = 2028, YearOfficial = false, X = 8806, Z = 1370, Yaw = -81.7f, PadW = 430f, PadD = 300f, Height = 42f, Radius = 215f, ViewYaw = 200f, ViewPitch = 24f,
                Source = "DigitalBusiness.kz, 24.kz", SourceDate = "20.02.2026 / 26.08.2026"
            }.F("Инвестиции", "≈ $180–185 млн (в соцсетях — $160 млн)").F("Сроки", "не объявлены (в демо — 2028)").Stage2("второй цех", 2032, 2034));

            // ---------------- Growing: export industry and logistics — in two industrial belts on the sides of the city (east along the
            // railway, west by the airport and BAKAD); PepsiCo, Mars Petcare and Griffin belong here too (plants and warehouses, not the business gate)
            L.Add(new Landmark
            {
                Id = "sunny_paper", Name = "Sunny Paper", Short = "Sunny Paper", Company = "Sunny Paper",
                Purpose = "Бумажное производство", Model = "paper",
                District = 2, Status = LStatus.Construction, StatusNote = "активная фаза (сводка 26.08.2026)",
                StartYear = 2026, EndYear = 2028, YearOfficial = false, X = 7540, Z = 1468, Yaw = -81.7f, PadW = 440f, PadD = 280f, Height = 62f, Radius = 210f, ViewYaw = 200f, ViewPitch = 24f,
                Source = "24.kz", SourceDate = "26.08.2026"
            }.F("Параметры", "не раскрыты").F("Сроки", "не объявлены (в демо — 2028)").Stage2("вторая бумагоделательная линия", 2033, 2036));
            L.Add(new Landmark
            {
                Id = "danaflex", Name = "DanaFlex", Short = "DanaFlex", Company = "DanaFlex",
                Purpose = "Гибкая упаковка", Model = "packaging",
                District = 2, Status = LStatus.Construction, StatusNote = "работы начаты (сводка 26.08.2026)",
                StartYear = 2026, EndYear = 2027, YearOfficial = false, X = 6668, Z = 651, Yaw = -81.7f, PadW = 300f, PadD = 200f, Height = 18f, Radius = 150f, ViewYaw = 200f, ViewPitch = 26f,
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
                StartYear = 2025, EndYear = 2027, YearOfficial = false, X = 7870, Z = 9941, Yaw = -29.0f, PadW = 520f, PadD = 220f, Height = 25f, Radius = 260f, ViewYaw = 215f, ViewPitch = 24f,
                Source = "bes.media, Tengrinews", SourceDate = "11.06.2024 / 23.09.2025"
            }.F("Инвестиции", "+$150 млн (2024); 43 млрд ₸").F("Сроки", "не объявлены (в демо — 2027)").Stage2("контейнерный терминал", 2030, 2032));
            L.Add(new Landmark
            {
                Id = "ps_arna", Name = "ПС «Арна» 220/110 кВ", Short = "ПС «Арна»", Company = "Фаза 1 инфраструктуры Алатау",
                Purpose = "Главная понизительная подстанция первой очереди", Model = "substation",
                District = 2, Status = LStatus.Construction, StatusNote = "строится; ещё 6 ПС в проектировании",
                StartYear = 2026, EndYear = 2027, YearOfficial = false, X = 1721, Z = 620, Yaw = 10.9f, PadW = 180f, PadD = 140f, Height = 18f, Radius = 95f, ViewYaw = 210f, ViewPitch = 28f,
                Source = "primeminister.kz, Qazinform", SourceDate = "15.01.2026 / 03.02.2026"
            }.F("Напряжение", "220/110 кВ").F("Фаза 1 (2026–2027/28)", "21 проект, 365,1 млрд ₸").F("Спрос", "2 064 МВт к 2030, 4 164 МВт к 2050")
             .F("Расположение", "в открытых данных не опубликовано"));
            L.Add(new Landmark
            {
                Id = "gtes", Name = "ГТЭС Doosan 2 × 250 МВт", Short = "ГТЭС Doosan", Company = "Doosan Enerbility · KEPCO · GGGI",
                Purpose = "Газотурбинная электростанция с переходом на водород (ГЧП)", Model = "power",
                District = 2, Status = LStatus.Agreement, StatusNote = "14.09.2026 — переговоры, окончательных соглашений нет",
                StartYear = 2028, EndYear = 2031, YearOfficial = false, X = 8185, Z = 979, Yaw = -81.7f, PadW = 340f, PadD = 240f, Height = 62f, Radius = 175f, ViewYaw = 210f, ViewPitch = 22f,
                Source = "bes.media, Kapital.kz", SourceDate = "14.09.2026"
            }.F("Мощность", "2 × 250 МВт").F("Сроки", "не объявлены (в демо — 2031)").Stage2("перевод турбин на водород", 2035, 2039));

            L.Add(new Landmark
            {
                Id = "airport", Name = "Аэропорт Алатау", Short = "Аэропорт", Company = "Концепция цифрового двойника · оператор не определён",
                Purpose = "Пассажирский и грузовой аэропорт: две параллельные ВПП, терминал в форме самолёта, карго, ТОиР, ЛРТ до терминала", Model = "airport",
                District = 2, Status = LStatus.Concept, StatusNote = "концепция: аэродром → пассажирский аэропорт, сроков нет",
                StartYear = 2032, EndYear = 2036, YearOfficial = false, X = -5900, Z = 8300, Yaw = 30f, PadW = 1600f, PadD = 3800f, Height = 98f, Radius = 1000f, ViewYaw = 300f, ViewPitch = 34f,
                Source = "генплан (аэродром), Astana Times — замысел пассажирского аэропорта", SourceDate = "04.09.2026"
            }.F("ВПП", "3 400 × 60 м и 2 650 × 60 м, параллельные").F("Терминал", "в форме самолёта: 985 × 776 м, ≈ 350 000 м²").F("Стоянки", "32 телетрапа + 6 перронных").F("Подъезд", "шоссе от трассы Алматы–Конаев ≈ 9 км, ветка ЛРТ до терминала").F("Пассажиры", "до 20 млн в год (оценка)").F("Сроки", "не объявлены (в демо — 2036)"));

            // ---------------- Green: tourism and recreation on Kapshagay
            L.Add(new Landmark
            {
                Id = "marina", Name = "Марина Капшагай", Short = "Марина", Company = "ACA · инвесторы не объявлены",
                Purpose = "Яхтенная марина и набережная туристического района", Model = "marina",
                District = 3, Status = LStatus.Concept, StatusNote = "концепция Green District, сроков нет",
                StartYear = 2033, EndYear = 2037, YearOfficial = false, X = 5177, Z = 23845, Yaw = -30f, PadW = 200f, PadD = 140f, Height = 14f, Radius = 180f, ViewYaw = 160f, ViewPitch = 22f,
                Source = "Kazinform, Astana Times", SourceDate = "29.09.2025 / 04.09.2026"
            }.F("Состав", "марина, клуб, набережная").F("Сроки", "не объявлены (в демо — 2037)"));
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
