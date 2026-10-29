using System;
using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>Where a number on screen comes from: an open publication (press, government, price site) or a QTwin model
    /// (synthetic data "like the real one"). Every KPI that is not plain geometry carries a tag pointing to one of these.</summary>
    public class Src
    {
        public string Id, Title, Publisher, Date, Url, Note;
        /// <summary>True: the number is modelled by QTwin (synthetic), not published by anybody.</summary>
        public bool Model;
        /// <summary>The short text of the tag: "Trend · 26.08.2026" or "модель QTwin".</summary>
        public string Short => Model ? "модель QTwin" : Publisher + (string.IsNullOrEmpty(Date) ? "" : " · " + Date);
    }

    /// <summary>The registry of sources and assumptions. Modules register their own entries (in the constructor, before the first
    /// panel is built); the shell lists all of them in the panel «Источники и допущения» and opens it at an entry on a tag click.</summary>
    public static class Sources
    {
        static readonly Dictionary<string, Src> map = new Dictionary<string, Src>();
        static readonly List<Src> order = new List<Src>();
        public static IReadOnlyList<Src> All => order;
        /// <summary>A tag was clicked: the shell opens the sources panel at this id (null — the whole list).</summary>
        public static event Action<string> OnOpen;

        public static Src Get(string id) => id != null && map.TryGetValue(id, out var s) ? s : null;

        /// <summary>Adds or replaces an entry (same id — the later call wins).</summary>
        public static Src Register(Src s)
        {
            if (s == null || string.IsNullOrEmpty(s.Id)) return s;
            if (map.TryGetValue(s.Id, out var old)) order.Remove(old);
            map[s.Id] = s; order.Add(s); return s;
        }
        public static Src Register(string id, string title, string publisher, string date, string url = null, string note = null)
            => Register(new Src { Id = id, Title = title, Publisher = publisher, Date = date, Url = url, Note = note });
        /// <summary>A QTwin model: what is modelled and on which assumptions.</summary>
        public static Src RegisterModel(string id, string title, string note)
            => Register(new Src { Id = id, Title = title, Publisher = "QTwin", Note = note, Model = true });

        public static void Open(string id = null)
        {
            if (OnOpen != null) { OnOpen(id); return; }
            var s = Get(id); if (s != null && !string.IsNullOrEmpty(s.Url)) Application.OpenURL(s.Url);
        }

        // ------------------------------------------------------------------ open data shared by several modules
        public const string GenPlan = "genplan_388", SpecialRegime = "law_special_regime", GovSummary = "gov_summary_2608",
            FastTrack = "astana_times_0726", Tengri = "tengri_0602", Kuwait = "kaztag_0506", Crypto = "intellinews_0703",
            Osm = "osm", OlxPrices = "olx_almaty_2610", NbrkRate = "nbrk_2310",
            ModelCity = "model_city", ModelSynthetic = "model_synthetic";

        static Sources()
        {
            Register(GenPlan, "Генеральный план Alatau City", "Правительство РК", "17.05.2024", null,
                "Постановление Правительства РК № 388 от 17.05.2024: границы, районы, назначение территорий, горизонт 2050.");
            Register(SpecialRegime, "Закон об особом правовом режиме Alatau City", "Президент РК", "08.05.2026", null,
                "Подписан 08.05.2026, действует с 01.07.2026: налоговые и визовые льготы, особый порядок разрешений для инвесторов.");
            Register(GovSummary, "Сводка правительства по Alatau City", "Trend", "26.08.2026", "https://www.trend.az/casia/kazakhstan/4218050.html",
                "67 инвестпроектов на ≈ $6,9 млрд, ≈ 55 тыс. рабочих мест, 26 инфраструктурных проектов.");
            Register(FastTrack, "Оперативный комитет по ускорению Alatau City", "The Astana Times", "07.2026",
                "https://astanatimes.com/2026/07/kazakhstan-creates-fast-track-committee-to-speed-up-alatau-city-development/",
                "Комитет при премьер-министре снимает барьеры для проектов города.");
            Register(Tengri, "Десятки инвестпроектов на 2 трлн тенге", "Tengrinews", "02.06.2026",
                "https://en.tengrinews.kz/kazakhstan_news/Dozens-of-investment-projects-worth-2-trillion-tenge-Tokayev-271723/", null);
            Register(Kuwait, "Кувейт заинтересован инвестировать в Alatau City", "KazTAG", "06.05.2026",
                "https://www.kt.kz/eng/international_affair/kuwait_has_expressed_interest_in_investing_in_1377991058.html", null);
            Register(Crypto, "Alatau City как криптостолица Центральной Азии", "IntelliNews", "03.07.2026",
                "https://www.intellinews.com/kazakhstan-aims-to-create-central-asia-s-crypto-capital-452509/", null);
            Register(Osm, "Существующая застройка и дороги", "OpenStreetMap", null, "https://www.openstreetmap.org/copyright",
                "© участники OpenStreetMap, лицензия ODbL.");
            Register(OlxPrices, "Цены на материалы в Алматы", "olx.kz", "22–26.10.2026", "https://www.olx.kz/",
                "Медиана объявлений по Алматы за 22–26.10.2026.");
            Register(NbrkRate, "Официальный курс доллара", "НБ РК", "23.10.2026", "https://nationalbank.kz/", "447,94 тенге за доллар.");
            RegisterModel(ModelCity, "Сценарий застройки QTwin",
                "Годы ввода, площади, жители и рабочие места по районам смоделированы QTwin по генплану. Жители = жильё / 30 м² на человека. Не официальные данные.");
            RegisterModel(ModelSynthetic, "Синтетические данные для демонстрации",
                "Числа, которых нет в открытых источниках, сгенерированы QTwin так, чтобы быть правдоподобными. Заменяются реальными после подключения данных заказчика.");
        }
    }
}
