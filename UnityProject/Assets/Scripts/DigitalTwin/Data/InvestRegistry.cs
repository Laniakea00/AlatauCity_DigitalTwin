using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>The registry of the investment projects of Alatau City from open press of 2025–2026, the published infrastructure items and
    /// the benefits of the special legal regime. Every row points to a page that was read (Sources). Nothing here is invented: where the
    /// press gives no figure the field stays empty (0 / null) and the UI says «не раскрыто».</summary>
    public static class InvestRegistry
    {
        // ------------------------------------------------------------------ sources read for this registry (29.10.2026)
        public const string AtIconic = "w2_at_1027", AtFastTrack = Sources.FastTrack, QzPm = "w2_qz_0115", QzPool = "w2_qz_0521",
            Kursiv = "w2_kursiv_0626", DigBiz = "w2_digbiz_0220", Forbes = "w2_forbes_1209", BesKorea = "w2_bes_0320", Herald = "w2_herald_0915",
            Tca = "w2_tca_0206", Standard = "w2_standard_0909", KapRoadshow = "w2_kap_0616", KapInfra = "w2_kap_0115", KapLoans = "w2_kap_0602",
            InformInfra = "w2_inform_infra", MorganLewis = "w2_ml_0512", MyBuh = "w2_mybuh_0508", Np = "w2_np_0612", LawArt61 = "w2_law_art61",
            Khabar = "w2_khabar_0521", AtHub = "w2_at_0904", CalcModel = "w2_calc_model", NetModel = "w2_net_model";

        static bool inited;
        /// <summary>Registers the sources of the registry (idempotent). Called from the module constructors.</summary>
        public static void Init()
        {
            if (inited) return; inited = true;
            Sources.Register(AtIconic, "Iconic Complex: начало строительства первого небоскрёба", "The Astana Times", "27.10.2026",
                "https://astanatimes.com/2026/10/alatau-city-breaks-ground-on-first-skyscraper-in-800-million-project/",
                "Закладка 26.10.2026, > $800 млн, генподрядчик CSCEC, архитектор SOM, башни 272 и 78 м, завершение — конец 2029. 28 инфраструктурных проектов на 35,3 млрд ₸ из резерва правительства.");
            Sources.Register(AtHub, "Alatau City: можно ли построить экономический хаб с нуля", "The Astana Times", "04.09.2026",
                "https://astanatimes.com/2026/09/alatau-city-can-kazakhstan-build-regional-economic-hub-from-scratch/",
                "Повторяет сводку 28.08.2026: 67 проектов, ≈ $6,9 млрд; CIMC и Sinomach — китайские партнёры.");
            Sources.Register(QzPm, "Премьер-министр ознакомился с проектами Алатау", "Kazinform", "15.01.2026",
                "https://qazinform.com/news/pm-reviews-major-investment-and-infrastructure-projects-in-alatau-a799b7",
                "PepsiCo — $360 млн, до 900 рабочих мест; Iconic Towers — > $800 млн, 276 800 м²; этапы дорожной карты инфраструктуры.");
            Sources.Register(QzPool, "В Алатау запущен пул инвестпроектов на 2 трлн тенге", "Kazinform", "21.05.2026",
                "https://qazinform.com/news/alatau-city-launches-kzt2tln-worth-of-investment-projects-4e14ea",
                "53 проекта, > 2 трлн ₸, > 51 тыс. рабочих мест. Партнёры: Iconic Complex, Joby, AutoFlight, Mars, PepsiCo, KAIST, Hyundai Green Food, Khan Tengri Biopharma. Акты города — на основе права Англии и Уэльса; споры — суд МФЦА или международный арбитраж.");
            Sources.Register(Kursiv, "Американская компания построит логопарк за $125 млн", "Kursiv", "26.06.2026",
                "https://kz.kursiv.media/en/2026-06-26/engk-tank-americans-to-build-massive-125-million-warehouse-in-kazakhstan/",
                "Griffin Partners (Хьюстон, США) и ЕАБР: $125 млн, 125 400 м², две очереди, завершение — III кв. 2027.");
            Sources.Register(DigBiz, "В Алатау построят завод кормов за $180 млн", "DigitalBusiness.kz", "20.02.2026",
                "https://digitalbusiness.kz/2026-02-20/v-novom-gorode-kazahstana-postroyat-kombikormoviy-zavod-stoimostyu-180-mln-dollarov/",
                "Инвестсоглашение Минсельхоза РК и Mars: ≈ $180 млн.");
            Sources.Register(Forbes, "Город, которого ещё нет: как бизнес обживает Алатау", "Forbes.kz", "09.12.2025",
                "https://forbes.kz/articles/gorod-kotorogo-eshe-net-2ec2c8",
                "Mars Petcare — 77 млрд ₸, ≈ 200 рабочих мест, завершение 2027; ТЛЦ «Жетыген» (Исткомтранс) — ≈ 10 млрд ₸, работает; Алматинский вентиляторный завод — с 2012 года.");
            Sources.Register(BesKorea, "Более 600 корейских компаний проявили интерес к Алатау", "bes.media", "20.03.2026",
                "https://bes.media/news/bolee-600-koreyskih-kompaniy-proyavili-interes-k-investitsiyam-v-alatau-87e1c1/",
                "Hyundai Green Food — предварительное соглашение о заводе; переговоры о корейском технологическом институте.");
            Sources.Register(Herald, "Hyundai Green Food: партнёрство с Alatau City Authority", "Herald Corp", "15.09.2026",
                "https://biz.heraldcorp.com/article/10874246", "Стратегическое партнёрство о строительстве завода K-food в Алатау.");
            Sources.Register(Tca, "Из Алатау в Алматы по воздуху: первое аэротакси", "The Times of Central Asia", "06.02.2026",
                "https://timesca.com/from-alatau-to-almaty-by-air-how-kazakhstans-first-air-taxi-service-will-operate/",
                "Joby Aviation (США) и оператор Alatau Advance Air Group: соглашение о покупке воздушных судов ≈ $300 млн; тестовые полёты — 2026.");
            Sources.Register(Standard, "Alatau City представлен инвесторам Гонконга", "The Standard (HK)", "09.09.2026",
                "https://www.thestandard.com.hk/news/article/342415/Kazakhstan-pitches-ambitious-Alatau-City-project-to-HK-investors-at-Belt-and-Road-Summit",
                "> 50 проектов на $4,2 млрд; бизнес работает по общему (английскому) праву.");
            Sources.Register(KapRoadshow, "Alatau City Roadshow в КНР: соглашения на $6,4 млрд", "Kapital.kz", "16.06.2026",
                "https://kapital.kz/economic/149339/v-alatau-city-roadshow-v-knr-zaklyucheny-soglasheniya-i-memorandumy-na-dollar64-mlrd.html",
                "30 соглашений и меморандумов на $6,4 млрд; поимённый список не опубликован.");
            Sources.Register(KapInfra, "Инфраструктурные проекты на 365,1 млрд тенге до 2028 года", "Kapital.kz", "15.01.2026",
                "https://kapital.kz/economic/144104/infrastrukturnye-proekty-na-3651-mlrd-tenge-planiruyut-realizovat-v-alatau-do-2028-goda.html",
                "Этап 1 (2026–2027): 21 проект, 365,1 млрд ₸ — подстанции, водозаборный узел, газопроводы. Этап 2 (2028–2030): 9 проектов, 312,5 млрд ₸ — 2 ПС, газопровод с АГРС, очистные, 49 км дорог. 11 подстанций ≈ 162 млрд ₸. Спрос: 2 064 МВт к 2030, 4 164 МВт к 2050.");
            Sources.Register(KapLoans, "Алатау разрешат брать госзаймы на инфраструктуру", "Kapital.kz", "02.06.2026",
                "https://kapital.kz/economic/148789/gorodu-alatau-razreshat-brat-goszajmy-dlya-stroitelstva-infrastruktury.html",
                "Базовую инфраструктуру финансирует государство, при необходимости — за счёт госзаймов города.");
            Sources.Register(InformInfra, "Дороги, газ, интернет и жильё: что строят в Алатау", "Kazinform", null,
                "https://www.inform.kz/ru/dorogi-gaz-internet-i-zhile-chto-stroyat-v-novom-gorode-alatau-d2831e",
                "Интервью заместителя акима; дата на странице не указана. Водопроводы Жанадауир и Жанаталап (положительная экспертиза), Жетыген; канализация Даулет — 3 КНС и 15 км; газ мкр. Куйган — ПСД.");
            Sources.Register(MorganLewis, "Kazakhstan introduces special legal regime for Alatau City", "Morgan Lewis", "12.05.2026",
                "https://www.morganlewis.com/pubs/2026/05/kazakhstan-introduces-special-legal-regime-for-alatau-city",
                "Льготы по КПН (вкл. налог у источника), НДС, налогам на имущество и землю, части налогов с зарплаты — до 30 лет; обычно не более 10 % стоимости проекта; стабильность налогов 10 лет; единое окно; суд МФЦА; перерегистрация участников СЭЗ 01.01–01.07.2027.");
            Sources.Register(MyBuh, "Особый налоговый режим в городе Алатау", "MyBuh.kz", "08.05.2026",
                "https://mybuh.kz/news/osobyy-nalogovyy-rezhim-vvedut-v-gorode-alatau/",
                "Полное или частичное освобождение от КПН, ИПН, НДС, налогов на имущество и землю до 30 лет; только новые проекты; не для подакцизных товаров и недропользования; свободная таможенная зона.");
            Sources.Register(Np, "Город особого внимания: что даст спецрежим Алатау", "Новое Поколение", "12.06.2026",
                "https://np.kz/news/ekonomika/biznes/gorod-osobogo-vnimaniya",
                "Старт 01.07.2026; преференции до 30 лет; стабильность 10 лет с выдачи бизнес-лицензии; ИПН для иностранных специалистов; проверки — только администрация города.");
            Sources.Register(LawArt61, "Конституционный закон № 286-VIII, ст. 61 «Миграционный режим»", "prg.kz", "08.05.2026",
                "https://prg.kz/m/amp/document/33779651/6/630000",
                "С 01.01.2027: въезд безвизово или по визе; визы и разрешения на временное проживание выдаются и продлеваются по ходатайству резидента, без выезда из РК.");
            Sources.Register(Khabar, "Город Алатау защитят английским правом", "Хабар", "21.05.2026",
                "https://khabar.kz/ru/news/obshchestvo/186393-gorod-alatau-zashchityat-anglijskim-pravom",
                "Город переводят на английское право; инвестор может идти в арбитраж, а не в казахстанский суд.");
            Sources.RegisterModel(CalcModel, "Калькулятор инвестора: модель налоговой экономии",
                "Оценка QTwin, не налоговая консультация. Ставки общего режима в модели: КПН 20 %, НДС на ввоз оборудования 16 %, налог на имущество 1,5 % в год, соцналог 9,5 % с фонда оплаты труда. " +
                "Выручка и рентабельность — средние по отрасли (допущение). Выход на мощность: 1-й год — 0, 2-й — 30 %, 3-й — 70 %, дальше 100 %. Зарплата — 600 тыс. ₸ в месяц, курс 447,94 ₸/$. " +
                "Льгота считается полной (100 %); размер реальной льготы администрация устанавливает каждому резиденту. Потолок 10 % стоимости проекта — по закону.");
            Sources.RegisterModel(NetModel, "Когда сети придут на участок",
                "По балансу «спрос / мощность» двойника (сценарий застройки QTwin): первый год, начиная с выбранного, после которого мощности района хватает на всех потребителей до 2050 года. Вода и газ — общегородские системы.");
        }

        // ------------------------------------------------------------------ projects
        public static readonly string[] Sectors = { "Промышленность", "Логистика", "Недвижимость и отели", "Наука и образование", "Энергетика", "Мобильность", "Цифра и финансы", "Фарма и медицина" };
        public static readonly string[] StatusNames = { "интерес", "MoU", "соглашение", "проектирование", "стройка", "работает" };
        /// <summary>Plain words for each status (shown under it in the card).</summary>
        public static readonly string[] StatusHint =
        {
            "компания заявила интерес или ведёт переговоры, документов нет",
            "подписан меморандум о намерениях — он не обязывает инвестировать",
            "подписано соглашение или партнёрство, но стройка не начата",
            "готовится проект и документация, площадка определяется",
            "на площадке идут строительно-монтажные работы",
            "предприятие уже работает"
        };
        public static readonly string[] StatusCls = { "muted", "info", "info", "warn", "warn", "ok" };

        public class Project
        {
            public string Name, Investor, Country, Years, Src, Src2, Landmark, Note;
            public int Sector, District = -1, Status;
            /// <summary>Millions of US dollars; 0 = not disclosed.</summary>
            public float UsdM; public string AmountNote;
            public int Jobs;
        }

        static Project P(string name, string inv, string country, int sector, int district, int status, string src, float usd = 0, int jobs = 0, string years = null, string lm = null, string note = null, string amountNote = null, string src2 = null)
            => new Project { Name = name, Investor = inv, Country = country, Sector = sector, District = district, Status = status, Src = src, UsdM = usd, Jobs = jobs, Years = years, Landmark = lm, Note = note, AmountNote = amountNote, Src2 = src2 };

        /// <summary>₸ → $ at the NB RK rate of 23.10.2026.</summary>
        public const float KztPerUsd = 447.94f;

        public static readonly List<Project> Projects = new List<Project>
        {
            // ---- under construction / operating
            P("Iconic Complex", "застройщик в статье не назван · генподрядчик CSCEC · архитектор SOM", "Китай · США", 2, 0, 4, AtIconic, 800, 0, "10.2026 – конец 2029", "iconic",
              "Первый небоскрёб города: башни 272 и 78 м, офисы, резиденции, отель, торговля. Закладка — 26.10.2026.", "> $800 млн"),
            P("Завод снеков PepsiCo", "PepsiCo", "США", 0, 2, 4, QzPm, 360, 900, "стройка с 2024", "pepsico",
              "Переработка картофеля, две очереди.", null, Sources.GovSummary),
            P("Завод кормов Mars Petcare", "Mars Inc.", "США", 0, 2, 4, DigBiz, 180, 200, "2025–2027", "mars",
              "Корма для домашних животных. Рабочие места и сроки — Forbes.kz.", "≈ $180 млн", Forbes),
            P("Griffin Logopark", "Griffin Partners · ЕАБР", "США", 1, 2, 4, Kursiv, 125, 0, "до III кв. 2027", "griffin",
              "Склады класса А, 125 400 м², две очереди, у трассы A3.", null, Sources.GovSummary),
            P("Sunny Paper", "Sunny Paper", null, 0, 2, 4, Sources.GovSummary, 0, 0, null, "sunny_paper", "Бумажное производство, «активная фаза реализации»."),
            P("DanaFlex", "DanaFlex", null, 0, 2, 4, Sources.GovSummary, 0, 0, null, "danaflex", "Гибкая упаковка, работы начаты."),
            P("G-Trans Service", "G-Trans Service", null, 1, 2, 4, Sources.GovSummary, 0, 0, null, "gtrans", "Логистика; вместе с Исткомтрансом развивает логистический кластер (Tengrinews).", null, Sources.Tengri),
            P("ТЛЦ «Жетыген»", "Исткомтранс · Steinhardt Holding", null, 1, 2, 5, Forbes, 10e9f / KztPerUsd / 1e6f, 0, "работает", "tlc",
              "Первый резидент СЭЗ: ж/д терминал, 20 из 51 га освоено.", "≈ 10 млрд ₸"),
            P("Mareven Food", "Mareven Food", null, 0, -1, 5, Sources.Tengri, 0, 0, "работает", null, "Одно из пяти действующих базовых предприятий."),
            P("KNAUF", "KNAUF", "Германия", 0, -1, 5, Sources.Tengri, 0, 0, "работает", null, "Строительные материалы; действующее предприятие."),
            P("Fruit Art", "Fruit Art", null, 0, -1, 5, Sources.Tengri, 0, 0, "работает", null, "Действующее предприятие."),
            P("Dolce Pharm", "Dolce Pharm", null, 7, -1, 5, Sources.Tengri, 0, 0, "работает", null, "Медицинские изделия; действующее предприятие."),
            P("Алматинский вентиляторный завод", "АВЗ", "Казахстан", 0, -1, 5, Sources.Tengri, 0, 0, "работает с 2012", null, "Работает в Коянкусе (Forbes.kz).", null, Forbes),
            // ---- agreements and design
            P("K-Smart Town, 330 га", "KIND (Корея)", "Южная Корея", 2, -1, 3, Sources.GovSummary, 0, 0, "мастер-план и ТЭО — до конца 2026", null,
              "Пилотный «умный» район: 5,3 млн м² застройки по корейским технологиям.", null, AtFastTrack),
            P("Токенизация «Tokenization by Default»", "43 компании Казахстана и мира", null, 6, -1, 3, Sources.GovSummary, 10, 0, "запуск — до конца 2026", null,
              "Alatau Crypto City: проекты токенизации до $10 млн, концепция подготовлена с Нацбанком.", "до $10 млн"),
            P("Отель L7 by Lotte в Iconic Tower", "Lotte Hotels & Resorts", "Южная Корея", 2, 0, 2, Sources.GovSummary, 0, 0, null, "lotte_l7", "Участие в проекте Iconic Tower."),
            P("Энергопроекты Doosan", "Doosan Enerbility", "Южная Корея", 4, 2, 2, Sources.GovSummary, 0, 0, null, "gtes", "Договорённость об энергетических проектах."),
            P("Пищевой комплекс Hyundai Green Food", "Hyundai Green Food", "Южная Корея", 0, -1, 2, Herald, 0, 0, null, null,
              "Завод K-food и логистика: предварительное соглашение (03.2026), стратегическое партнёрство (15.09.2026).", null, BesKorea),
            P("Умная мобильность и водород", "Hyundai Motor Company", "Южная Корея", 5, -1, 2, Sources.GovSummary, 0, 0, null, null, "Договорённость достигнута, параметры не раскрыты."),
            P("Городская аэромобильность", "Korea Airports Corporation", "Южная Корея", 5, -1, 2, Sources.GovSummary, 0, 0, null, null, "Договорённость о воздушной мобильности."),
            P("Казахстанско-корейский инвестфонд", "Казахстан · Корея", "Южная Корея", 6, -1, 2, Sources.GovSummary, 0, 0, null, null, "Совместный инвестиционный фонд."),
            P("Аэротакси Joby S4", "Joby Aviation · Alatau Advance Air Group", "США", 5, -1, 2, Tca, 300, 0, "тестовые полёты — 2026", null,
              "Электрические самолёты вертикального взлёта, маршруты Алатау – Алматы.", "≈ $300 млн (покупка судов)"),
            P("Блокчейн-инфраструктура города", "Solana Company · Solana Foundation", "США", 6, -1, 1, Sources.Crypto, 0, 0, "MoU 06.2026", null, "Консультации и создание крипто-инфраструктуры."),
            // ---- interest / negotiations
            P("Кампус KAIST", "KAIST", "Южная Корея", 3, 1, 0, Sources.GovSummary, 0, 0, null, "kaist", "Филиал исследовательского института; переговоры (bes.media, 03.2026).", null, BesKorea),
            P("Аэротакси AutoFlight", "AutoFlight", "Китай", 5, -1, 0, QzPool, 0, 0, null, null, "В пуле проектов; тип документа не раскрыт.", null, AtFastTrack),
            P("Биофармзавод полного цикла", "Khan Tengri Biopharma", "Казахстан", 7, -1, 0, QzPool, 0, 0, null, null, "Компания рассматривает строительство завода."),
            P("Авиатопливо (SAF) и зелёная энергия", "Full Vision Capital", null, 4, -1, 0, Sources.GovSummary, 0, 0, null, null, "Потенциальный инвестор."),
            P("Логистика и центры обработки данных", "CIMC", "Китай", 1, -1, 0, Sources.GovSummary, 0, 0, null, null, "Потенциальный инвестор.", null, AtHub),
            P("Высокотехнологичный агрокомплекс", "Sinomach", "Китай", 0, -1, 0, Sources.GovSummary, 0, 0, null, null, "Потенциальный инвестор."),
            P("Недвижимость и городская инфраструктура", "National Bank of Kuwait", "Кувейт", 6, -1, 0, Sources.Kuwait, 0, 0, null, null, "Интерес к участию; визит вице-премьера в Кувейт — осенью 2026."),
        };

        // ------------------------------------------------------------------ infrastructure (published items)
        public class InfraItem { public string Name, Kind, What, When, Status, StatusCls, Amount, Src; }
        public static readonly List<InfraItem> Infra = new List<InfraItem>
        {
            new InfraItem { Name = "Дорожная карта, этап 1 — 21 проект", Kind = "сети", What = "подстанции, водозаборный узел, газопроводы", When = "2026–2027", Status = "в работе", StatusCls = "warn", Amount = "365,1 млрд ₸", Src = KapInfra },
            new InfraItem { Name = "Реконструкция ПС «Кокпа-1»", Kind = "электричество", What = "подстанция: начаты строительно-монтажные работы", When = "2026", Status = "стройка", StatusCls = "warn", Src = Sources.GovSummary },
            new InfraItem { Name = "Водоснабжение и водоотведение", Kind = "вода", What = "часть объектов близка к завершению, по остальным выбраны подрядчики", When = "2026", Status = "стройка", StatusCls = "warn", Src = Sources.GovSummary },
            new InfraItem { Name = "Дороги: 61,2 км ремонта и 15 км новых", Kind = "дороги", What = "средний ремонт и строительство новых дорог", When = "2026", Status = "стройка", StatusCls = "warn", Src = Sources.GovSummary },
            new InfraItem { Name = "28 проектов из резерва правительства", Kind = "сети и дороги", What = "ПС «Кокпа-1», водоснабжение, ремонт дорог", When = "2026", Status = "финансирование выделено", StatusCls = "info", Amount = "35,3 млрд ₸", Src = AtIconic },
            new InfraItem { Name = "Водопроводы Жанадауир, Жанаталап, Жетыген", Kind = "вода", What = "реконструкция сетей существующих сёл", When = "—", Status = "экспертиза проекта", StatusCls = "info", Src = InformInfra },
            new InfraItem { Name = "Канализация Даулет", Kind = "канализация", What = "3 насосные станции и 15 км сетей", When = "—", Status = "проектирование", StatusCls = "info", Src = InformInfra },
            new InfraItem { Name = "Газ в мкр. Куйган", Kind = "газ", What = "газоснабжение микрорайона", When = "—", Status = "проектирование", StatusCls = "info", Src = InformInfra },
            new InfraItem { Name = "11 подстанций", Kind = "электричество", What = "строительство и реконструкция по дорожной карте", When = "не объявлено", Status = "план", StatusCls = "muted", Amount = "≈ 162 млрд ₸", Src = KapInfra },
            new InfraItem { Name = "Дорожная карта, этап 2 — 9 проектов", Kind = "сети и дороги", What = "2 подстанции, газопровод с АГРС, очистные сооружения, 49 км дорог", When = "2028–2030", Status = "план", StatusCls = "muted", Amount = "312,5 млрд ₸", Src = KapInfra },
            new InfraItem { Name = "Аэротакси Алатау – Алматы", Kind = "транспорт", What = "тестовые полёты Joby S4, сеть вертипортов проектируется", When = "2026", Status = "испытания", StatusCls = "info", Src = Tca },
        };

        // ------------------------------------------------------------------ benefits of the special legal regime (what the press says the law grants)
        public class Benefit { public string Title, Plain, Src; }
        public static readonly Benefit[] Benefits =
        {
            new Benefit { Title = "Налоговые льготы до 30 лет", Plain = "полное или частичное освобождение от налога на прибыль (КПН), НДС, налогов на имущество и землю; размер льготы администрация города устанавливает каждому резиденту", Src = MorganLewis },
            new Benefit { Title = "Потолок — около 10 % стоимости проекта", Plain = "сумма всех льгот обычно не больше 10 % вложений; больше — только решением на уровне Президента", Src = MorganLewis },
            new Benefit { Title = "Стабильность налогов 10 лет", Plain = "10 лет с выдачи бизнес-лицензии нельзя ввести новый налог или поднять ставку для проекта", Src = Np },
            new Benefit { Title = "Свободная таможенная зона", Plain = "товары и оборудование ввозятся по особым таможенным правилам", Src = MyBuh },
            new Benefit { Title = "Единое окно", Plain = "регистрация, лицензии, разрешения и надзор — в одной цифровой системе администрации; иностранные лицензии могут признаваться", Src = MorganLewis },
            new Benefit { Title = "Визы и проживание по ходатайству резидента", Plain = "с 01.01.2027 визы и разрешения на проживание сотрудникам выдаются и продлеваются без выезда из Казахстана", Src = LawArt61 },
            new Benefit { Title = "Английское право и суд МФЦА", Plain = "правила города могут опираться на право Англии и Уэльса; споры — в суде Международного финансового центра «Астана» или в международном арбитраже", Src = QzPool },
            new Benefit { Title = "Кто получает", Plain = "резидент Алатау с новым инвестпроектом в приоритетной отрасли; не для подакцизных товаров и добычи недр; участники СЭЗ перерегистрируются до 01.07.2027", Src = MyBuh },
        };

        // ------------------------------------------------------------------ investor calculator (model)
        // per sector: equipment share of the investment, revenue per $ invested at full capacity, profit margin (model assumptions)
        static readonly float[] EquipShare = { 0.50f, 0.30f, 0.15f, 0.30f, 0.60f, 0.50f, 0.60f, 0.50f };
        static readonly float[] Turnover = { 1.20f, 0.35f, 0.18f, 0.15f, 0.25f, 0.50f, 0.80f, 1.00f };
        static readonly float[] Margin = { 0.12f, 0.25f, 0.30f, 0.10f, 0.20f, 0.10f, 0.20f, 0.15f };
        const float Cit = 0.20f, ImportVat = 0.16f, PropTax = 0.015f, SocTax = 0.095f, WageKztMonth = 600000f;

        public struct Savings { public float Cit, Vat, Property, Payroll, Total, Cap, Result; }

        /// <summary>Taxes the project would not pay over the horizon with a full exemption (model), $ mln, and the legal cap (10 % of the investment).</summary>
        public static Savings Estimate(int sector, float investUsdM, int jobs, int years)
        {
            sector = Mathf.Clamp(sector, 0, Sectors.Length - 1);
            var s = new Savings();
            s.Vat = investUsdM * EquipShare[sector] * ImportVat;                         // once, when the equipment is imported
            float payrollUsdM = jobs * WageKztMonth * 12f / KztPerUsd / 1e6f;
            for (int y = 1; y <= years; y++)
            {
                float ramp = y == 1 ? 0f : y == 2 ? 0.3f : y == 3 ? 0.7f : 1f;
                s.Cit += investUsdM * Turnover[sector] * ramp * Margin[sector] * Cit;
                if (y >= 2) s.Property += investUsdM * (1f - EquipShare[sector]) * PropTax;
                s.Payroll += payrollUsdM * (y == 1 ? 0.5f : 1f) * SocTax;
            }
            s.Total = s.Cit + s.Vat + s.Property + s.Payroll;
            s.Cap = investUsdM * 0.10f;
            s.Result = Mathf.Min(s.Total, s.Cap);
            return s;
        }

        // ------------------------------------------------------------------ when the networks reach a plot (twin balance)
        public static readonly (string key, string name, string unit)[] NetRes =
        {
            ("power", "Электричество", "МВт"), ("heat", "Тепло", "Гкал/ч"), ("gas", "Газ", "тыс. м³/ч"), ("water", "Вода", "тыс. м³/сут"), ("sewer", "Канализация", "тыс. м³/сут")
        };

        public struct NetAnswer { public int Year; public bool Pooled; public float Spare; public int DefFrom, DefTo, DefYears; public string DefRanges; }

        static TwinData.Balance Bal(int s, string key, int d, out bool pooled)
        {
            pooled = false;
            var b = d >= 0 ? TwinData.BalanceOf(s, key, d) : null;
            if (b == null) { b = TwinData.BalanceOf(s, key, -1); pooled = d >= 0; }
            return b;
        }
        static bool Short(TwinData.Balance b, int yi) => b != null && (b.Cap[yi] <= 0f || b.Deficit[yi] > 0.5f);

        /// <summary>The first year from <paramref name="fromYear"/> after which the district's capacity covers the demand every year to 2050
        /// (power = both the 220/110 kV feed and the 10 kV network). Year = −1: not covered by 2050. DefFrom/DefTo: the shortage years on the way.</summary>
        public static NetAnswer When(int s, string key, int d, int fromYear)
        {
            var a = new NetAnswer { Year = -1, DefFrom = -1, DefTo = -1 };
            if (!TwinData.Ready) return a;
            var b = Bal(s, key, d, out a.Pooled);
            var hv = key == "power" ? Bal(s, "power_hv", d, out _) : null;
            if (b == null) return a;
            int y0 = Mathf.Clamp(fromYear, 2026, TwinState.MaxYear);
            int lastShort = -1, runA = -1; var sb = new System.Text.StringBuilder();
            void Close(int to) { if (runA < 0) return; if (sb.Length > 0) sb.Append(", "); sb.Append(to > runA ? string.Format("{0}–{1}", runA, to) : runA.ToString()); runA = -1; }
            for (int y = y0; y <= TwinState.MaxYear; y++)
            {
                int yi = TwinData.YI(y);
                if (Short(b, yi) || Short(hv, yi)) { lastShort = y; a.DefYears++; if (a.DefFrom < 0) a.DefFrom = y; a.DefTo = y; if (runA < 0) runA = y; }
                else Close(y - 1);
            }
            Close(TwinState.MaxYear);
            a.DefRanges = sb.ToString();
            a.Year = lastShort < 0 ? y0 : lastShort + 1 > TwinState.MaxYear ? -1 : lastShort + 1;
            if (a.Year > 0)
            {
                int yi = TwinData.YI(a.Year);
                float sp = b.Cap[yi] > 0 ? 1f - b.Demand[yi] / b.Cap[yi] : 0f;
                if (hv != null && hv.Cap[yi] > 0) sp = Mathf.Min(sp, 1f - hv.Demand[yi] / hv.Cap[yi]);
                a.Spare = Mathf.Clamp01(sp);
            }
            return a;
        }
    }
}
