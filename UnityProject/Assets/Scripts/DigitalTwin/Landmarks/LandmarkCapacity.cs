using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Production capacity of the large companies and objects on the map: design capacity, what it means a year,
    /// jobs, revenue and export at full load, and the load in the shown year (ramp-up after the start, the 2nd phase adds capacity).
    /// Official figures are marked; the rest is the twin's estimate by analogues (similar plants), shown as «оценка».</summary>
    public static class LandmarkCapacity
    {
        public class Cap
        {
            public string Id, Product;          // what is made / handled
            public float Design; public string Unit;   // design capacity (number + unit, «тыс. т в год»)
            public string Plain;                // one line for a non-specialist: «≈ 2 пачки чипсов на жителя Казахстана в месяц»
            public int Jobs; public float RevenueUsdM, Export;   // at full load: jobs, $ mln a year, export share 0..1
            public float Stage2Gain;            // the 2nd phase adds this share of the design capacity
            public bool Official;               // capacity published by the company / government
            public string Note;
            public bool Industrial;             // a plant or a logistics hub (counted in the city's industrial output)
        }

        static Dictionary<string, Cap> all;
        static Dictionary<string, Cap> All => all ??= Build();

        static Dictionary<string, Cap> Build()
        {
            var L = new List<Cap>
            {
                new Cap { Id = "pepsico", Product = "чипсы и снеки", Design = 63f, Unit = "тыс. т в год", Plain = "переработка 210 тыс. т казахстанского картофеля в год", Jobs = 900, RevenueUsdM = 320f, Export = 0.40f, Stage2Gain = 0.35f, Official = true, Industrial = true, Note = "сырьё 210 тыс. т — официально; выпуск — оценка по выходу 30 %" },
                new Cap { Id = "mars", Product = "корма для животных", Design = 100f, Unit = "тыс. т в год", Plain = "корма для рынка Казахстана и Центральной Азии", Jobs = 400, RevenueUsdM = 260f, Export = 0.50f, Stage2Gain = 0.40f, Industrial = true, Note = "оценка по аналогичным заводам Mars" },
                new Cap { Id = "sunny_paper", Product = "бумага и картон", Design = 120f, Unit = "тыс. т в год", Plain = "замещает импорт тарного картона", Jobs = 450, RevenueUsdM = 110f, Export = 0.25f, Stage2Gain = 0.60f, Industrial = true, Note = "параметры не раскрыты — оценка двойника" },
                new Cap { Id = "danaflex", Product = "гибкая упаковка", Design = 30f, Unit = "тыс. т в год", Plain = "упаковка для пищевых заводов города и региона", Jobs = 300, RevenueUsdM = 120f, Export = 0.30f, Industrial = true, Note = "оценка по заводу DanaFlex-Alabuga" },
                new Cap { Id = "gtrans", Product = "сервис грузовиков", Design = 30f, Unit = "тыс. обслуживаний в год", Plain = "≈ 80 грузовиков в сутки на ТО и ремонт", Jobs = 250, RevenueUsdM = 45f, Export = 0f, Industrial = true, Note = "оценка двойника" },
                new Cap { Id = "tlc", Product = "контейнеры", Design = 250f, Unit = "тыс. TEU в год", Plain = "сухой порт на пути Китай — Европа", Jobs = 700, RevenueUsdM = 90f, Export = 0.80f, Stage2Gain = 0.60f, Industrial = true, Note = "оценка по сухому порту «Хоргос»" },
                new Cap { Id = "griffin", Product = "складская логистика", Design = 120f, Unit = "тыс. м² складов", Plain = "≈ 600 тыс. т грузов в год", Jobs = 600, RevenueUsdM = 18f, Export = 0f, Stage2Gain = 0.50f, Official = true, Industrial = true, Note = "площадь складов — официально (ЕАБР)" },
                new Cap { Id = "gtes", Product = "электроэнергия", Design = 500f, Unit = "МВт", Plain = "≈ 3,7 млрд кВт·ч в год — четверть спроса города в 2030", Jobs = 150, RevenueUsdM = 210f, Export = 0f, Official = true, Industrial = true, Note = "2 × 250 МВт — официально; выработка при КИУМ 85 %" },
                new Cap { Id = "ps_arna", Product = "электроснабжение", Design = 500f, Unit = "МВА", Plain = "питание первой очереди города", Jobs = 40, Note = "оценка двойника" },
                new Cap { Id = "airport", Product = "пассажиры и грузы", Design = 20f, Unit = "млн пассажиров в год", Plain = "и ≈ 250 тыс. т грузов в год", Jobs = 6000, RevenueUsdM = 380f, Export = 0.35f, Industrial = true, Note = "концепция двойника" },
                new Cap { Id = "iconic", Product = "офисы, жильё, отель", Design = 276.8f, Unit = "тыс. м²", Plain = "≈ 8 000 рабочих мест в офисах и отеле", Jobs = 8000, Official = true, Note = "площадь — официально (SOM)" },
                new Cap { Id = "lotte_l7", Product = "гостиница", Design = 180f, Unit = "номеров", Plain = "≈ 50 тыс. гостей в год", Jobs = 220, RevenueUsdM = 22f, Official = true },
                new Cap { Id = "kaist", Product = "образование и наука", Design = 40f, Unit = "тыс. студентов", Plain = "инженеры и IT для компаний города", Jobs = 3500, Official = true, Note = "студенты — официально" },
                new Cap { Id = "medcluster", Product = "медицина", Design = 1200f, Unit = "коек", Plain = "≈ 600 тыс. приёмов в год", Jobs = 2800, Note = "оценка по нормативам на 0,7 млн жителей Golden" },
                new Cap { Id = "kpark", Product = "отдых и туризм", Design = 2f, Unit = "млн посетителей в год", Plain = "парк 10 га", Jobs = 300, Note = "оценка двойника" },
                new Cap { Id = "marina", Product = "яхтенный туризм", Design = 300f, Unit = "яхт-мест", Plain = "≈ 400 тыс. гостей набережной в год", Jobs = 350, Note = "оценка двойника" },
            };
            var d = new Dictionary<string, Cap>(); foreach (var c in L) d[c.Id] = c; return d;
        }

        public static Cap Of(string id) => id != null && All.TryGetValue(id, out var c) ? c : null;
        public static IEnumerable<Cap> Items => All.Values;

        /// <summary>Load of the object in a year, 0..1: nothing before it works, then a ramp-up (55 % → 92 % over three years).</summary>
        public static float Load(Landmark l, float y)
        {
            if (l == null) return 0f;
            float p = LandmarkSystem.Progress(l, y);
            if (p < 0.85f) return 0f;
            if (p < 0.999f) return 0.15f;              // commissioning
            float yrs = y - l.EndYear;
            return Mathf.Clamp(0.55f + 0.13f * yrs, 0.55f, 0.92f);
        }
        /// <summary>Capacity available in a year (design × the 2nd phase once it is built), in the cap's unit.</summary>
        public static float CapacityAt(Landmark l, Cap c, float y) => c == null ? 0f : c.Design * (l != null && l.S2End > 0 && y >= l.S2End ? 1f + c.Stage2Gain : 1f);
        public static float OutputAt(Landmark l, Cap c, float y) => CapacityAt(l, c, y) * Load(l, y);

        /// <summary>«63 тыс. т в год» with a sensible number of decimals.</summary>
        public static string Fmt(float v, string unit) => (v >= 100f || Mathf.Approximately(v, Mathf.Round(v)) ? Loc.N0(v) : Loc.N1(v)) + " " + unit;

        /// <summary>Output and export of all the large plants in a year, $ mln (revenue at the year's load).</summary>
        public static void Totals(int y, out float revenue, out float export)
        {
            revenue = 0f; export = 0f; var sys = LandmarkSystem.Instance;
            foreach (var c in All.Values)
            {
                if (!c.Industrial || c.RevenueUsdM <= 0f) continue;
                var l = sys != null ? sys.Get(c.Id) : null; if (l == null) continue;
                float k = Load(l, y) * (l.S2End > 0 && y >= l.S2End ? 1f + c.Stage2Gain : 1f);
                revenue += c.RevenueUsdM * k; export += c.RevenueUsdM * k * c.Export;
            }
        }
    }
}
