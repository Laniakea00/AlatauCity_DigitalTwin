using System;
using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Smart City layer of the twin: CCTV cameras of the city (public safety, traffic, construction sites, utilities) and the
    /// stream of notifications — video analytics, residents' requests to iKomek 109, 112 and the twin's own forecasts.
    /// Everything here is a stub with deterministic demo data (seed = year): the real feeds (Smart City Alatau, iKomek 109, 112)
    /// connect to the same structures through their APIs later.</summary>
    public static class SmartCity
    {
        public enum CamType { Safety, Traffic, Construction, Utility }
        public static readonly string[] CamTypeName = { "Общественная безопасность", "Дороги и ПДД", "Стройплощадки", "ЖКХ и экология" };
        public static readonly string[] CamTypeShort = { "Безопасность", "ПДД", "Стройка", "ЖКХ" };
        public static readonly Color[] CamTypeColor = { new Color(0.48f, 0.66f, 1f), new Color(0.96f, 0.72f, 0.20f), new Color(1f, 0.55f, 0.22f), new Color(0.24f, 0.86f, 0.74f) };
        static readonly string[] DistrictCode = { "GT", "GD", "GR", "GN" };

        public class Cctv
        {
            public string Id, Place; public CamType Type; public int District; public Vector3 World; public float Heading;
            public bool Online = true; public string Analytics;   // what the video analytics looks for
        }

        public class Notice
        {
            public string Source, Icon, Level, Title, Text, Status;   // level: bad / warn / info / ok
            public int Minute;                                     // minute of the day (00:00 = 0)
            public int Cam = -1;                                   // index of the camera that sees it (−1 = none)
            public Vector3 World; public bool HasPlace;
            public int District = -1;
            public string Time => $"{(Minute / 60) % 24:00}:{Minute % 60:00}";
        }

        // ------------------------------------------------------------------ totals (the whole network, not only the cameras on the map)
        /// <summary>Cameras of the city in the year: ≈ 1 per 120 residents (Astana ≈ 1 per 100) + 1 per km of main roads.</summary>
        public static int CameraCount(int y)
        {
            if (!CityStats.Ready) return 0;
            float res = CityStats.Residents(-1, y);
            return Mathf.RoundToInt(res / 120f + Mathf.Clamp01((y - 2026) / 6f) * 900f + 180f);
        }
        public static float OnlineShare(int y) => y < 2028 ? 0.93f : 0.975f;
        /// <summary>Requests of residents to iKomek 109 a day: ≈ 1.6 per 1 000 residents.</summary>
        public static int RequestsPerDay(int y) => Mathf.RoundToInt((CityStats.Ready ? CityStats.Residents(-1, y) + 70000f : 70000f) * 0.0016f);
        public static float SolvedInTime(int y) => Mathf.Clamp(0.78f + (y - 2026) * 0.012f, 0.78f, 0.96f);
        public static int ReactionMin(int y) => Mathf.RoundToInt(Mathf.Lerp(42f, 18f, Mathf.Clamp01((y - 2026) / 14f)));
        public static int EventsPerDay(int y) => Mathf.RoundToInt(CameraCount(y) * 0.11f);   // video-analytics alerts

        public static readonly (string name, float share)[] RequestTypes =
        {
            ("Дороги, ямы, разметка", 0.22f), ("Уличное освещение", 0.14f), ("Вывоз мусора", 0.17f), ("Вода и канализация", 0.13f),
            ("Благоустройство, дворы", 0.12f), ("Шум и парковка", 0.10f), ("Общественный транспорт", 0.07f), ("Прочее", 0.05f)
        };

        // ------------------------------------------------------------------ cameras on the map (a sample of the network, ≈ 90)
        static List<Cctv> cams = new List<Cctv>(); static int camYear = -1, camScenario = -1;
        public static List<Cctv> Cameras(int y)
        {
            int s = (int)TwinState.Scenario;
            if (y == camYear && s == camScenario && cams.Count > 0) return cams;
            camYear = y; camScenario = s; cams = new List<Cctv>();
            var db = CityDatabase.Instance; if (db == null || !CityStats.Ready) return cams;
            var rnd = new System.Random(7700 + y);
            // candidates: buildings of the new city standing in the year, by kind of camera
            var pool = new List<BuildingInfo>[4]; for (int t = 0; t < 4; t++) pool[t] = new List<BuildingInfo>();
            var recent = new List<BuildingInfo>();
            foreach (var b in db.Buildings)
            {
                if (b == null || b.Source == "existing_osm" || CityStats.DistrictIndex(b.District) < 0) continue;
                if (Landmarks.LandmarkSystem.IsHiddenBid(b.Bid)) continue;
                int e = CityStats.EffectiveYearOf(b.Bid);
                bool built = e <= y, building = !built && e <= y + 2;
                if (building && b.GfaM2 > 4000f) pool[(int)CamType.Construction].Add(b);
                if (built && e >= y - 3 && b.GfaM2 > 4000f) recent.Add(b);   // finishing works, landscaping
                if (!built) continue;
                switch (b.Kind)
                {
                    case "res_high": case "res_mid": case "mixed": case "public": case "education": case "health": case "culture": case "retail": pool[(int)CamType.Safety].Add(b); break;
                    case "tower": case "business": case "podium": case "hotel": pool[(int)CamType.Traffic].Add(b); break;
                    case "utility": case "industry": pool[(int)CamType.Utility].Add(b); break;
                }
            }
            if (pool[(int)CamType.Construction].Count < 14) pool[(int)CamType.Construction].AddRange(recent);
            int[] want = { 42, 26, 14, 10 };
            for (int t = 0; t < 4; t++)
            {
                var p = pool[t]; int n = 0;
                for (int tries = 0; tries < 900 && n < want[t] && p.Count > 0; tries++)
                {
                    var b = p[rnd.Next(p.Count)]; var w = new Vector3(b.X, b.GroundM + Mathf.Min(b.HeightM, 40f) + 8f, b.Z);
                    bool near = false; foreach (var c in cams) if ((new Vector2(c.World.x, c.World.z) - new Vector2(w.x, w.z)).sqrMagnitude < 650f * 650f) { near = true; break; }
                    if (near) continue;
                    int d = CityStats.DistrictIndex(b.District);
                    var cam = new Cctv
                    {
                        Id = "AC-" + DistrictCode[d] + "-" + (1000 + rnd.Next(9000)), Type = (CamType)t, District = d, World = w, Heading = (float)rnd.NextDouble() * 360f,
                        Place = Place(d, (CamType)t, rnd), Online = rnd.NextDouble() > (1f - OnlineShare(y)) * 1.4f,
                        Analytics = Analytics((CamType)t)
                    };
                    cams.Add(cam); n++;
                }
            }
            return cams;
        }
        static string Analytics(CamType t) => t switch
        {
            CamType.Safety => "оставленные предметы · скопление людей · драка",
            CamType.Traffic => "ДТП · скорость · выезд на встречную · пробки",
            CamType.Construction => "каски и жилеты · посторонние · пыль",
            _ => "свалки · дым · подтопления · утечки"
        };
        static readonly string[][] Streets =
        {
            new[] { "пр. Алатау", "Деловой бульвар", "пл. Iconic", "ул. Жетыген", "Транспортный узел Gate", "ул. Финансовая" },
            new[] { "Академический пр.", "кампус KAIST", "ул. Университетская", "Медицинский кластер", "K-Park", "ул. Наукоград" },
            new[] { "Промышленный пр.", "ул. Логистическая", "станция ЛРТ «Заводская»", "БАКАД, развязка", "ул. Мастеров", "пр. Шёлкового пути" },
            new[] { "Набережная Капшагая", "ул. Курортная", "Марина", "пляж «Алтын Құм»", "ул. Прибрежная", "Яхт-клуб" }
        };
        static string Place(int d, CamType t, System.Random r) => Streets[d][r.Next(Streets[d].Length)] + (t == CamType.Construction ? " · стройплощадка" : "");

        // ------------------------------------------------------------------ notifications of the day
        static List<Notice> day = new List<Notice>(); static int dayYear = -1;
        /// <summary>The notifications of a working day in the year, sorted by time (repeatable: seed = year).</summary>
        public static List<Notice> Day(int y)
        {
            if (y == dayYear && day.Count > 0) return day;
            dayYear = y; day = new List<Notice>();
            var cs = Cameras(y); var rnd = new System.Random(1090 + y);
            Cctv Cam(CamType t) { var l = cs.FindAll(c => c.Type == t && c.Online); return l.Count > 0 ? l[rnd.Next(l.Count)] : null; }
            void Add(string src, string icon, string lvl, string title, string text, string status, int min, Cctv c, int d = -1)
            {
                var n = new Notice { Source = src, Icon = icon, Level = lvl, Title = title, Text = text, Status = status, Minute = min, District = c != null ? c.District : d };
                if (c != null) { n.Cam = cs.IndexOf(c); n.World = c.World; n.HasPlace = true; }
                day.Add(n);
            }
            int m = 6 * 60 + 40;
            for (int i = 0; i < 26; i++)
            {
                m += 18 + rnd.Next(30);
                switch (rnd.Next(7))
                {
                    case 0: { var c = Cam(CamType.Traffic); if (c == null) break; Add("Smart City · видео", "video", "bad", "ДТП: столкновение двух машин", c.Place + " · камера " + c.Id + " · вызваны ДПС и скорая", "в 112 · " + (3 + rnd.Next(4)) + " мин", m, c); break; }
                    case 1: { var c = Cam(CamType.Traffic); if (c == null) break; Add("Smart City · ПДД", "video", "warn", "Затор " + (300 + rnd.Next(900)) + " м", c.Place + " · светофоры переведены на адаптивный режим", "в работе", m, c); break; }
                    case 2: { var c = Cam(CamType.Safety); var rt = RequestTypes[Pick(rnd)]; Add("iKomek 109", "bell", "info", "Обращение: " + rt.name.ToLowerInvariant(), (c != null ? c.Place : "Alatau City") + " · житель через приложение iKomek", rnd.Next(3) == 0 ? "решено за " + (25 + rnd.Next(90)) + " мин" : "передано в службу", m, c); break; }
                    case 3: { var c = Cam(CamType.Construction); if (c == null) break; Add("Стройка · видео", "hard_hat", "warn", "Рабочий без каски", c.Place + " · камера " + c.Id + " · уведомлён прораб подрядчика", "штраф подрядчику", m, c); break; }
                    case 4: { var c = Cam(CamType.Utility); if (c == null) break; Add("Smart City · экология", "droplets", "warn", rnd.Next(2) == 0 ? "Несанкционированная свалка" : "Подтопление после полива", c.Place + " · камера " + c.Id, "выехала бригада", m, c); break; }
                    case 5: { var c = Cam(CamType.Safety); if (c == null) break; Add("Smart City · безопасность", "video", "info", "Оставленный предмет", c.Place + " · камера " + c.Id + " · проверено патрулём", "ложная тревога", m, c); break; }
                    default: { int d = rnd.Next(4); Add("qTwin · прогноз", "sparkles", "info", "Пик нагрузки на сети в 19:00", CityStats.DistrictIds[d] + " · электроэнергия +" + (6 + rnd.Next(9)) + " % к среднему, резерв есть", "мониторинг", m, null, d); break; }
                }
            }
            day.Sort((a, b) => a.Minute.CompareTo(b.Minute));
            return day;
        }
        static int Pick(System.Random r)
        {
            double x = r.NextDouble(), a = 0; for (int i = 0; i < RequestTypes.Length; i++) { a += RequestTypes[i].share; if (x <= a) return i; }
            return RequestTypes.Length - 1;
        }
    }
}
