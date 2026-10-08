using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;
using static AlatauCity.DigitalTwin.Data.TwinJson;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>Synthetic operation-stage data for the Situational Center (M4): one accelerated day of the city in year N
    /// (event feed from IoT / 112 / housing / transport / ecology / weather), the data streams, and 8 decision scenarios
    /// with two branches each ("decision taken" / "not taken"). Everything is deterministic (seed = year, scenario) and is
    /// computed from the same city data as the other tabs: residents near a point, facilities, roads, LRT, flood zone.</summary>
    public static class SituationData
    {
        // ------------------------------------------------------------------ common helpers
        public static float ResidentsOf(BuildingInfo b) =>
            b.Use == "housing" ? b.GfaM2 / CityStats.M2PerResident : b.Source == "existing_osm" ? Mathf.Max(3f, b.GfaM2 / 35f) : 0f;
        public static bool Stands(BuildingInfo b, int y) => b.Source == "existing_osm" || CityStats.EffectiveYearOf(b.Bid) <= y;

        /// <summary>Residents living within r metres of p in year y (and the buildings themselves).</summary>
        public static float ResidentsNear(Vector2 p, float r, int y, List<int> bids = null)
        {
            var db = CityDatabase.Instance; if (db == null) return 0; float s = 0, r2 = r * r;
            foreach (var b in db.Buildings)
            {
                if (b == null) continue; float dx = b.X - p.x, dz = b.Z - p.y; if (dx * dx + dz * dz > r2 || !Stands(b, y)) continue;
                s += ResidentsOf(b); bids?.Add(b.Bid);
            }
            return s;
        }
        static string Addr(BuildingInfo b) => $"№{b.Bid % 180 + 1}, квартал {b.Bid / 180 % 60 + 1}";
        public static Vector2 DistrictCenter(int d) { var c = CityStats.DistrictBounds[d].center; return new Vector2(c.x, c.z); }

        /// <summary>Midpoint of the open road of a class nearest to the populated centre of a district.</summary>
        static Vector2 RoadPoint(int d, TwinData.RoadClass cls, int s, int y, float shift = 0)
        {
            var c = PeopleCenter(d, y) + new Vector2(shift, shift * 0.6f); float best = float.MaxValue; var bp = c;
            foreach (var e in TwinData.Roads)
            {
                if (e.Cls != cls || e.Geom == null || e.Geom.Length < 2 || (e.Year != null && e.Year.Length > s && e.Year[s] > y)) continue;
                var m = e.Geom[e.Geom.Length / 2]; float dd = (m - c).sqrMagnitude; if (dd < best) { best = dd; bp = m; }
            }
            return bp;
        }
        /// <summary>Centre of mass of the residents of a district in year y (where the people actually are).</summary>
        public static Vector2 PeopleCenter(int d, int y)
        {
            var db = CityDatabase.Instance; double sx = 0, sz = 0, sw = 0;
            if (db != null) foreach (var b in db.Buildings)
            {
                if (b == null || b.District != CityStats.DistrictIds[d] || !Stands(b, y)) continue; float w = ResidentsOf(b) + 1; sx += b.X * w; sz += b.Z * w; sw += w;
            }
            return sw > 0 ? new Vector2((float)(sx / sw), (float)(sz / sw)) : DistrictCenter(d);
        }

        // ------------------------------------------------------------------ data streams ("Источники данных")
        public class Source { public string Id, Name, Proto, Freq, Unit; public int Points; public string Status; public Func<System.Random, string> Sample; }
        public static List<Source> Sources(int s, int y)
        {
            var db = CityDatabase.Instance; int built = 0; float people = 0;
            if (db != null) foreach (var b in db.Buildings) if (b != null && Stands(b, y)) { built++; people += ResidentsOf(b); }
            int Seg(string k) => TwinData.Networks.TryGetValue(k, out var a) ? a.Count(g => g.Year != null && g.Year.Length > s && g.Year[s] <= y) : 0;
            int fac(string r) => TwinData.Facilities.Count(f => f.Res == r && f.Stages[s].Length > 0 && f.Stages[s][0] <= y);
            int lrt = 0; for (int i = 0; i < TwinData.LrtStations.Length; i++) if (TwinData.LrtPhaseYear[s][Mathf.RoundToInt(TwinData.LrtStations[i].z)] <= y) lrt++;
            int roadsOpen = TwinData.Roads.Count(e => e.Year == null || e.Year.Length <= s || e.Year[s] <= y);
            var L = new List<Source>
            {
                new Source { Id = "scada_power", Name = "SCADA подстанций", Proto = "МЭК 61850 / 104", Freq = "1 с", Points = fac("power_hv") * 120 + fac("power") * 48, Sample = r => $"ПС «Golden»: {Mathf.RoundToInt(70 + (float)r.NextDouble() * 22)} % · 110,{r.Next(2, 9)} кВ" },
                new Source { Id = "askue", Name = "Умные счётчики (АСКУЭ)", Proto = "DLMS / NB-IoT", Freq = "15 мин", Points = built, Sample = r => $"{Loc.N0(people * 0.0011f * (0.9f + (float)r.NextDouble() * 0.2f))} кВт·ч за 15 мин" },
                new Source { Id = "water", Name = "Давление и расход воды", Proto = "OPC UA / LoRaWAN", Freq = "10 с", Points = Seg("water") * 2 + fac("water") * 30, Sample = r => $"{4 + (float)r.NextDouble() * 1.4f:0.0} атм · {Loc.N0(people * 0.0096f * (0.85f + (float)r.NextDouble() * 0.3f))} м³/ч" },
                new Source { Id = "heat", Name = "Теплосети", Proto = "OPC UA", Freq = "30 с", Points = Seg("heat") * 2 + fac("heat") * 24, Sample = r => $"подача {Mathf.RoundToInt(92 + (float)r.NextDouble() * 18)} °C · обратка {Mathf.RoundToInt(48 + (float)r.NextDouble() * 10)} °C" },
                new Source { Id = "sewer", Name = "КНС и очистные", Proto = "Modbus TCP", Freq = "1 мин", Points = Seg("sewer") + fac("sewer") * 40, Sample = r => $"уровень в КНС {Mathf.RoundToInt(35 + (float)r.NextDouble() * 40)} %" },
                new Source { Id = "gas", Name = "Газ: АГРС и ГРП", Proto = "телемеханика", Freq = "1 мин", Points = Seg("gas") + 30, Sample = r => $"{0.55 + r.NextDouble() * 0.05:0.00} МПа" },
                new Source { Id = "traffic", Name = "Детекторы трафика", Proto = "REST / MQTT", Freq = "1 мин", Points = roadsOpen / 6, Sample = r => $"трасса Алматы–Конаев: {Mathf.RoundToInt(48 + (float)r.NextDouble() * 50)} км/ч" },
                new Source { Id = "cams", Name = "Камеры с видеоаналитикой", Proto = "RTSP + CV", Freq = "поток", Points = roadsOpen / 10 + built / 60, Sample = r => $"{r.Next(0, 4)} нарушения ПДД за минуту" },
                new Source { Id = "air", Name = "Качество воздуха", Proto = "MQTT", Freq = "5 мин", Points = 24 + built / 900, Sample = r => $"PM2.5 {r.Next(6, 38)} мкг/м³" },
                new Source { Id = "noise", Name = "Шум", Proto = "MQTT", Freq = "1 мин", Points = 18 + built / 1500, Sample = r => $"{r.Next(42, 71)} дБА" },
                new Source { Id = "112", Name = "Вызовы 112", Proto = "API ЕДДС", Freq = "событие", Points = 1, Sample = r => $"{r.Next(2, 9)} вызовов за час" },
                new Source { Id = "eotinish", Name = "Обращения жителей (ЖКХ)", Proto = "API eOtinish", Freq = "событие", Points = 1, Sample = r => $"{r.Next(3, 14)} обращений за час" },
                new Source { Id = "gtfs", Name = "GPS транспорта, ЛРТ", Proto = "GTFS-RT", Freq = "10 с", Points = Mathf.RoundToInt(people / 2500f) + lrt * 2, Sample = r => $"ЛРТ: интервал {r.Next(4, 7)} мин" },
                new Source { Id = "meteo", Name = "Погода (Казгидромет)", Proto = "API", Freq = "10 мин", Points = 6, Sample = r => $"{r.Next(-8, 6)} °C · ветер {r.Next(1, 9)} м/с" },
                new Source { Id = "hydro", Name = "Гидропосты (Каскелен, Или)", Proto = "GSM-телеметрия", Freq = "15 мин", Points = 9, Sample = r => $"уровень +{0.2 + r.NextDouble() * 0.4:0.00} м к меженному" },
                new Source { Id = "bim", Name = "Стройка: BIM, дроны, ERP", Proto = "IFC / REST", Freq = "сутки", Points = Mathf.Max(1, TwinData.BuildYears.Count(v => v >= y && v <= y + 2)), Sample = r => $"съёмка БПЛА: {r.Next(3, 11)} площадок" },
            };
            // one stream with a delay — a twin should show that data can be late, not pretend everything is perfect
            foreach (var x in L) x.Status = "ok";
            L.First(x => x.Id == "noise").Status = "warn";
            return L.Where(x => x.Points > 0).ToList();
        }

        // ------------------------------------------------------------------ the event feed of one day
        public class Ev { public int Min; public string Src, Text, Level; public Vector2 P; public string Inc; }   // Level: info / warn / bad; Inc = incident id
        public static readonly string[] SrcKeys = { "iot", "112", "zhkh", "transport", "eco", "weather" };

        public static List<Ev> Day(int s, int y, List<Incident> incs)
        {
            var R = new System.Random(y * 31 + s * 7 + 5);
            var db = CityDatabase.Instance; var homes = new List<BuildingInfo>(); float people = 0;
            if (db != null) foreach (var b in db.Buildings) if (b != null && Stands(b, y) && ResidentsOf(b) > 20) { homes.Add(b); people += ResidentsOf(b); }
            var list = new List<Ev>(); if (homes.Count == 0) return list;
            BuildingInfo H() => homes[R.Next(homes.Count)];
            string Dn(BuildingInfo b) => b.District;
            int n = Mathf.Clamp(Mathf.RoundToInt(people / 9000f), 40, 220);
            for (int i = 0; i < n; i++)
            {
                // more events in the morning and evening peaks
                int min = R.Next(0, 1440); if (R.NextDouble() < 0.35) min = (R.NextDouble() < 0.5 ? 7 * 60 : 17 * 60) + R.Next(0, 180);
                var b = H(); var p = new Vector2(b.X, b.Z); double k = R.NextDouble();
                Ev e;
                if (k < 0.24)
                {
                    var t = R.Next(6);
                    e = t switch
                    {
                        0 => new Ev { Src = "zhkh", Text = $"Обращение: нет горячей воды · {Dn(b)}, дом {Addr(b)}", Level = "warn" },
                        1 => new Ev { Src = "zhkh", Text = $"Обращение: не работает лифт · {Dn(b)}, дом {Addr(b)}", Level = "info" },
                        2 => new Ev { Src = "zhkh", Text = $"Обращение: шум стройки ночью · {Dn(b)}", Level = "info" },
                        3 => new Ev { Src = "zhkh", Text = $"Обращение: яма на проезде · {Dn(b)}", Level = "info" },
                        4 => new Ev { Src = "zhkh", Text = $"Обращение закрыто за {R.Next(2, 20)} ч · {Dn(b)}", Level = "info" },
                        _ => new Ev { Src = "zhkh", Text = $"Обращение: не вывезен мусор · {Dn(b)}", Level = "info" },
                    };
                }
                else if (k < 0.40)
                {
                    var t = R.Next(4);
                    e = t switch
                    {
                        0 => new Ev { Src = "112", Text = $"Вызов скорой помощи · {Dn(b)} · бригада через {R.Next(6, 15)} мин", Level = "info" },
                        1 => new Ev { Src = "112", Text = $"ДТП без пострадавших · {Dn(b)}", Level = "warn" },
                        2 => new Ev { Src = "112", Text = $"Возгорание мусора во дворе · {Dn(b)} · локализовано", Level = "warn" },
                        _ => new Ev { Src = "112", Text = $"Вызов полиции · {Dn(b)}", Level = "info" },
                    };
                }
                else if (k < 0.66)
                {
                    var t = R.Next(5);
                    e = t switch
                    {
                        0 => new Ev { Src = "iot", Text = $"Давление в водоводе {4 + R.NextDouble() * 1.5:0.0} атм · {Dn(b)} · норма", Level = "info" },
                        1 => new Ev { Src = "iot", Text = $"Температура теплоносителя {R.Next(88, 112)} °C · {Dn(b)}", Level = "info" },
                        2 => new Ev { Src = "iot", Text = $"Счётчик не на связи 2 ч · {Dn(b)}, дом {Addr(b)}", Level = "warn" },
                        3 => new Ev { Src = "iot", Text = $"КНС: уровень {R.Next(40, 80)} % · {Dn(b)}", Level = "info" },
                        _ => new Ev { Src = "iot", Text = $"ТП 10/0,4 кВ: загрузка {R.Next(55, 92)} % · {Dn(b)}", Level = "info" },
                    };
                }
                else if (k < 0.84)
                {
                    var t = R.Next(3);
                    e = t switch
                    {
                        0 => new Ev { Src = "transport", Text = $"ЛРТ: интервал {R.Next(4, 7)} мин, по графику", Level = "info" },
                        1 => new Ev { Src = "transport", Text = $"Детектор: {R.Next(18, 35)} км/ч на въезде в {Dn(b)}", Level = "warn" },
                        _ => new Ev { Src = "transport", Text = $"Автобус {R.Next(1, 40)}: опоздание {R.Next(3, 9)} мин · {Dn(b)}", Level = "info" },
                    };
                }
                else if (k < 0.94)
                {
                    int pm = R.Next(6, 46);
                    e = R.Next(2) == 0 ? new Ev { Src = "eco", Text = $"PM2.5 {pm} мкг/м³ · {Dn(b)}", Level = pm > 35 ? "warn" : "info" }
                                       : new Ev { Src = "eco", Text = $"Шум {R.Next(52, 78)} дБА у стройплощадки · {Dn(b)}", Level = "info" };
                }
                else e = new Ev { Src = "weather", Text = R.Next(2) == 0 ? $"Ветер {R.Next(3, 15)} м/с, порывы до {R.Next(15, 22)}" : $"Уровень р. Каскелен +{0.2 + R.NextDouble() * 0.5:0.00} м", Level = "info" };
                e.Min = min; e.P = p; list.Add(e);
            }
            // incidents of the day go into the feed at their times
            foreach (var inc in incs) if (inc.Today && inc.Avail) list.Add(new Ev { Min = inc.StartMin, Src = inc.Src, Text = inc.FeedText, Level = inc.Kind == "forecast" ? "warn" : "bad", P = inc.P, Inc = inc.Id });
            return list.OrderBy(x => x.Min).ToList();
        }

        // ------------------------------------------------------------------ decision scenarios
        /// <summary>One phase of a branch: people affected from t0 to t1 (by radius around the point, or a fixed count).</summary>
        public class Phase { public float R, N, T0, T1; }
        public class Branch
        {
            public string Title, Text; public Phase[] Phases; public float Fixed, FixedAt, PerPersonUnit, NbLoad, Co2PerUnit, Restore;
            public float[] Affected, Damage, Co2; public float AffectedMax, Peak; public List<int> Bids = new List<int>();
        }
        public class Incident
        {
            public string Id, Title, Where, Src, Kind, Who, Sla, FeedText, Unit = "ч", Question; public int District, StartMin, MinYear, MaxYear = 2050;
            public Vector2 P; public float H; public Branch Yes, No; public bool Today, Avail, Decided; public int SuggestYear; public string[] History;
            public bool FloodTint, FixedCount;
        }

        public static List<Incident> Incidents(int s, int y)
        {
            var L = new List<Incident>();
            var fac = TwinData.Facilities;
            TwinData.Facility F(string res, int d) => fac.FirstOrDefault(f => f.Res == res && f.District == d);

            // 1. water main leak (today, 06:20) — Golden
            {
                var p = RoadPoint(1, TwinData.RoadClass.Main, s, y, 0);
                L.Add(new Incident
                {
                    Id = "leak", Title = "Утечка на магистральном водоводе", District = 1, P = p, Src = "iot", Kind = "active", Today = true, StartMin = 6 * 60 + 20, H = 24, MinYear = 2030,
                    Where = "Golden, магистральный водовод Ду 800", Who = "Водоканал Alatau · дежурный диспетчер", Sla = "локализация 2 ч",
                    FeedText = "Датчики: падение давления 5,1 → 3,2 атм, расход +38 % · водовод Ду 800, Golden",
                    Question = "Перекрыть участок и пустить воду по резервной нитке?",
                    History = new[] { "06:20 · датчики давления: −1,9 атм за 4 мин", "06:24 · двойник локализовал участок между задвижками З-14 и З-17", "06:31 · бригада выехала, прибытие 06:55" },
                    Yes = new Branch { Title = "Перекрыть и пустить по резервной нитке", Text = "Задвижки З-14, З-17 закрыты дистанционно; резервная нитка берёт нагрузку. Без воды — только ближайшие дома на время переключения.",
                        Phases = new[] { new Phase { R = 450, T0 = 0.5f, T1 = 3.5f } }, Fixed = 22, FixedAt = 1, PerPersonUnit = 400, NbLoad = 78, Co2PerUnit = 0.15f, Restore = 3.5f },
                    No = new Branch { Title = "Продолжать подачу до приезда бригады", Text = "Вода размывает грунт: через 6 ч провал проезжей части, аварийное отключение всего участка, подтопление подвалов.",
                        Phases = new[] { new Phase { R = 450, T0 = 0.5f, T1 = 6 }, new Phase { R = 1700, T0 = 6, T1 = 21 } }, Fixed = 180, FixedAt = 6, PerPersonUnit = 400, NbLoad = 104, Co2PerUnit = 0.45f, Restore = 21 },
                });
            }
            // 2. Golden 220/110 kV substation overload in the winter evening peak (forecast for 18:00 today)
            {
                var f = F("power_hv", 1); var p = f != null ? new Vector2(f.X, f.Z) : DistrictCenter(1);
                float util = f != null && f.CapAt(s, y) > 0 ? f.DemandAt(s, y) / f.CapAt(s, y) : 0.9f; int pct = Mathf.Clamp(Mathf.RoundToInt(util * 100 * 1.14f), 96, 128);
                L.Add(new Incident
                {
                    Id = "ps", Title = "Перегрузка ПС «Golden» в вечерний пик", District = 1, P = p, Src = "iot", Kind = "forecast", Today = true, StartMin = 15 * 60 + 40, H = 12, MinYear = 2028,
                    Where = f != null ? f.Name : "ПС 220/110 кВ Golden", Who = "KEGOC / РЭК Alatau · диспетчер", Sla = "решение до 17:30",
                    FeedText = $"Прогноз двойника: в 18:00 загрузка ПС «Golden» {pct} % (−14 °C, вечерний пик)",
                    Question = "Перевести часть нагрузки на ПС «Gate» и включить управление спросом?",
                    History = new[] { "15:40 · прогноз нагрузки на вечер: −14 °C, пик в 18:00–20:00", $"15:41 · двойник: {pct} % от мощности трансформаторов", "15:45 · уведомлены KEGOC и крупные потребители" },
                    Yes = new Branch { Title = "Перевод на ПС «Gate» + ограничение 12 МВт", Text = "Две линии 110 кВ переведены на ПС «Gate»; ТЦ и офисы снижают нагрузку на 2 часа по договору. Жильё не отключается.",
                        Phases = new[] { new Phase { N = 0, T0 = 2.3f, T1 = 4.5f } }, Fixed = 4, FixedAt = 2.3f, PerPersonUnit = 0, NbLoad = 88, Co2PerUnit = 1.2f, Restore = 0 },
                    No = new Branch { Title = "Работать в обычном режиме", Text = "В 18:20 защита отключает трансформатор, автоматика отключает часть района. Зимой без света — значит и без отопления в домах с электрокотлами.",
                        Phases = new[] { new Phase { R = 2600, T0 = 2.6f, T1 = 7.5f } }, Fixed = 45, FixedAt = 2.6f, PerPersonUnit = 900, NbLoad = 118, Co2PerUnit = 3.5f, Restore = 7.5f },
                });
            }
            // 3. crash on the Almaty–Konaev highway in the morning peak (today, 07:48)
            {
                var p = RoadPoint(0, TwinData.RoadClass.Highway, s, y, 900);
                L.Add(new Incident
                {
                    Id = "dtp", Title = "ДТП на трассе Алматы–Конаев", District = 0, P = p, Src = "112", Kind = "active", Today = true, StartMin = 7 * 60 + 48, H = 4, MinYear = 2025, FixedCount = true,
                    Where = "трасса Алматы–Конаев, съезд на Gate", Who = "Полиция · ДЧС · Центр управления движением", Sla = "освободить полосу 40 мин",
                    FeedText = "112: ДТП, 3 автомобиля, перекрыты 2 полосы на Конаев · трасса у Gate",
                    Question = "Открыть объезд и переключить светофоры на «зелёную волну»?",
                    History = new[] { "07:48 · вызов 112, камеры подтвердили ДТП", "07:50 · скорость на участке упала до 12 км/ч", "07:52 · экипаж полиции и эвакуатор направлены" },
                    Yes = new Branch { Title = "Объезд + «зелёная волна» + табло", Text = "Знаки на табло за 5 км, объезд по магистрали Gate, светофоры в режиме пропуска. Затор не больше 3 км.",
                        Phases = new[] { new Phase { N = 4200, T0 = 0, T1 = 1.3f } }, Fixed = 0, PerPersonUnit = 2500, NbLoad = 92, Co2PerUnit = 1.6f, Restore = 1.3f },
                    No = new Branch { Title = "Ждать эвакуатор", Text = "Затор растёт до 11 км, к 9:00 перекинется на въезды в Gate и Golden; скорая едет вдвое дольше.",
                        Phases = new[] { new Phase { N = 15000, T0 = 0, T1 = 2.6f } }, Fixed = 0, PerPersonUnit = 2500, NbLoad = 135, Co2PerUnit = 4.2f, Restore = 2.6f },
                });
            }
            // 4. spring flood on the Kaskelen (forecast / drill), affected = flood-zone residents of risk.json
            {
                FloodSet(y, out var fp, out var fpeople, out var fdamage, out var fbids);
                var inc = new Incident
                {
                    Id = "flood", Title = "Паводок на Каскелене", District = 2, P = fp, Src = "weather", Kind = "forecast", Today = false, H = 72, MinYear = 2025, FixedCount = true, FloodTint = true,
                    Where = "пойма р. Каскелен", Who = "ДЧС · акимат · Водоканал", Sla = "предупреждение за 24 ч", Unit = "ч",
                    FeedText = "Гидропост: уровень Каскелена +0,9 м за сутки, прогноз +1,6 м через 30 ч",
                    Question = "Эвакуировать пойму и поставить временную дамбу заранее?",
                    History = new[] { "Весна · снеготаяние + ливни в горах", "Гидропосты: подъём +0,9 м за сутки", "Модель: пик через 30 ч, уровень +1,6 м (раз в 100 лет)" },
                    Yes = new Branch { Title = "Дамба из мешков и эвакуация за 24 ч", Text = "Временная дамба 2,4 км и откачка; жители поймы вывезены заранее. Ущерб — в основном подвалы и благоустройство.",
                        Phases = new[] { new Phase { N = fpeople * 0.35f, T0 = 6, T1 = 40 } }, Fixed = fdamage * 1000f * 0.3f, FixedAt = 30, PerPersonUnit = 300, NbLoad = 70, Co2PerUnit = 0.4f, Restore = 40 },
                    No = new Branch { Title = "Реагировать по факту подтопления", Text = "Вода заходит в дома ночью, эвакуация под водой, отключение подстанций в пойме.",
                        Phases = new[] { new Phase { N = fpeople, T0 = 30, T1 = 66 } }, Fixed = fdamage * 1000f, FixedAt = 32, PerPersonUnit = 600, NbLoad = 115, Co2PerUnit = 0.9f, Restore = 66 },
                };
                inc.Yes.Bids = fbids; inc.No.Bids = fbids; L.Add(inc);
            }
            // 5. LRT phase 2 (Growing) delayed by 2 years — a planning decision, unit = months
            {
                int ph2 = TwinData.LrtPhaseYear[s].Length > 1 ? TwinData.LrtPhaseYear[s][1] : 2036;
                var st = new List<Vector2>(); for (int i = 0; i < TwinData.LrtStations.Length; i++) if (Mathf.RoundToInt(TwinData.LrtStations[i].z) == 1) st.Add(new Vector2(TwinData.LrtStations[i].x, TwinData.LrtStations[i].y));
                int yy = Mathf.Max(y, ph2); var bids = new List<int>(); float near = 0; foreach (var q in st) near += ResidentsNear(q, 900, yy, bids);
                var p = st.Count > 0 ? st[st.Count / 2] : DistrictCenter(2);
                L.Add(new Incident
                {
                    Id = "lrt", Title = $"Ввод ЛРТ в Growing сдвигается на 2 года", District = 2, P = p, Src = "transport", Kind = "plan", Today = false, H = 24, Unit = "мес.", MinYear = 2025, MaxYear = ph2, FixedCount = true,
                    Where = $"ЛРТ, 2-я очередь · {TwinData.LrtPhaseNames.ElementAtOrDefault(1)}", Who = "Управление транспорта · подрядчик ЛРТ", Sla = "решение до утверждения бюджета",
                    FeedText = "Подрядчик ЛРТ: срыв поставки подвижного состава, сдвиг ввода 2-й очереди на 24 мес.",
                    Question = "Запустить временный BRT по трассе ЛРТ на 2 года?",
                    History = new[] { $"План: ввод 2-й очереди в {ph2}", "Поставщик вагонов сообщил о сдвиге на 24 мес.", $"У станций 2-й очереди живут ~{Loc.N0(near / 1000f)} тыс. человек" },
                    Yes = new Branch { Title = "Временный BRT на выделенной полосе", Text = "60 электробусов по трассе будущего ЛРТ, интервал 4 мин. Поездка дольше на 9 мин, но без пробок.",
                        Phases = new[] { new Phase { N = near * 0.6f, T0 = 0, T1 = 24 } }, Fixed = 18000, FixedAt = 1, PerPersonUnit = 6600, NbLoad = 84, Co2PerUnit = 160, Restore = 24 },
                    No = new Branch { Title = "Ждать ЛРТ", Text = "Жители Growing пересаживаются на машины: +23 % машин на въездах, заторы на трассе каждое утро.",
                        Phases = new[] { new Phase { N = near, T0 = 0, T1 = 24 } }, Fixed = 0, PerPersonUnit = 15000, NbLoad = 121, Co2PerUnit = 950, Restore = 24 },
                });
                L.Last().Yes.Bids = bids; L.Last().No.Bids = bids;
            }
            // 6. solar plant output drops on a cloudy day — forecast for tomorrow
            {
                var f = fac.Where(x => x.Res == "renewable" && x.Stages[s].Length > 0 && x.Stages[s][0] <= y).OrderByDescending(x => x.Stages[s][0]).FirstOrDefault() ?? fac.FirstOrDefault(x => x.Res == "renewable");
                var p = f != null ? new Vector2(f.X, f.Z) : DistrictCenter(2); int minY = f != null ? f.Stages[s][0] : 2028;
                L.Add(new Incident
                {
                    Id = "ses", Title = $"Облачность: выработка {(f != null ? f.Name.Split('·')[0].Trim() : "СЭС")} падает на 80 %", District = 2, P = p, Src = "weather", Kind = "forecast", Today = false, H = 10, MinYear = minY,
                    Where = f != null ? f.Name : "СЭС", Who = "Диспетчер энергосистемы", Sla = "за 6 ч до события",
                    FeedText = "Прогноз погоды: плотная облачность завтра 10:00–16:00",
                    Question = "Заранее включить газовые турбины и накопители?",
                    History = new[] { "Казгидромет: облачный фронт завтра с 10:00", "Двойник: дефицит до 46 МВт в 12:00–15:00", "Накопители заряжены на 82 %" },
                    Yes = new Branch { Title = "ГТУ и накопители по прогнозу", Text = "Резерв включён за 2 ч до облачности, частота в норме, потребители ничего не замечают.",
                        Phases = new[] { new Phase { N = 0, T0 = 2, T1 = 7 } }, Fixed = 6, FixedAt = 2, PerPersonUnit = 0, NbLoad = 91, Co2PerUnit = 9, Restore = 0 },
                    No = new Branch { Title = "Реагировать по факту", Text = "Частота падает, автоматика отключает 40 МВт потребителей в Growing на 3 часа.",
                        Phases = new[] { new Phase { R = 2200, T0 = 2.2f, T1 = 5.2f } }, Fixed = 14, FixedAt = 2.2f, PerPersonUnit = 700, NbLoad = 112, Co2PerUnit = 3, Restore = 5.2f },
                });
            }
            // 7. warehouse fire in Growing (drill scenario)
            {
                var db = CityDatabase.Instance; BuildingInfo wh = null;
                if (db != null) wh = db.Buildings.Where(b => b != null && b.District == "Growing" && (b.Use == "industry") && Stands(b, y)).OrderByDescending(b => b.GfaM2).FirstOrDefault()
                                 ?? db.Buildings.Where(b => b != null && b.District == "Growing" && b.Use == "industry").OrderBy(b => CityStats.EffectiveYearOf(b.Bid)).FirstOrDefault();
                var p = wh != null ? new Vector2(wh.X, wh.Z) : DistrictCenter(2); int minY = wh != null && wh.Source != "existing_osm" ? Mathf.Max(2025, CityStats.EffectiveYearOf(wh.Bid)) : 2025;
                L.Add(new Incident
                {
                    Id = "fire", Title = "Пожар на складе в Growing", District = 2, P = p, Src = "112", Kind = "drill", Today = false, H = 8, MinYear = minY,
                    Where = wh != null ? $"Growing, логистический склад {Loc.N0(wh.GfaM2)} м²" : "Growing, склад", Who = "ДЧС · газовая служба · акимат", Sla = "прибытие 10 мин",
                    FeedText = "112: дым над складом, срабатывание пожарной сигнализации · Growing",
                    Question = "Эвакуировать дома в радиусе 500 м и перекрыть газ?",
                    History = new[] { "Датчики дыма и тепловизор камеры", "Ветер 9 м/с на жилые кварталы", "На складе — пластик и газовые баллоны" },
                    Yes = new Branch { Title = "Эвакуация 500 м + газ перекрыт", Text = "Газ перекрыт на ГРП дистанционно, жителей вывозят автобусами, дым уходит на пустые кварталы.",
                        Phases = new[] { new Phase { R = 500, T0 = 0.3f, T1 = 4 } }, Fixed = 650, FixedAt = 1, PerPersonUnit = 300, NbLoad = 75, Co2PerUnit = 40, Restore = 4 },
                    No = new Branch { Title = "Обычный выезд без эвакуации", Text = "Через 2 ч взрыв баллонов, пожар переходит на соседние здания, дым накрывает жилые дома в радиусе 1,2 км.",
                        Phases = new[] { new Phase { R = 500, T0 = 0.3f, T1 = 2.5f }, new Phase { R = 1200, T0 = 2.5f, T1 = 8 } }, Fixed = 2800, FixedAt = 2.5f, PerPersonUnit = 600, NbLoad = 109, Co2PerUnit = 85, Restore = 8 },
                });
            }
            // 8. concrete supply failure on the Gate Q1 site (construction, 2031)
            {
                var bq = BimQuarter.Instance; var p = bq != null && BimQuarter.Loaded ? new Vector2(bq.Center.x, bq.Center.z) : RoadPoint(0, TwinData.RoadClass.Street, s, y);
                L.Add(new Incident
                {
                    Id = "concrete", Title = "Срыв поставки бетона на Gate Q1", District = 0, P = p, Src = "iot", Kind = "active", Today = false, H = 30, Unit = "сут.", MinYear = 2031, MaxYear = 2031, FixedCount = true,
                    Where = "Gate Q1, монолит 6–9 этажей", Who = "Генподрядчик · технадзор", Sla = "план поставки 180 м³/сут",
                    FeedText = "Поставщик РБУ «Капшагай»: остановка завода, бетона не будет 12 дней",
                    Question = "Переключиться на резервный РБУ с доплатой 18 %?",
                    History = new[] { "РБУ «Капшагай»: авария смесителя", "Без бетона стоят 4 захватки, 210 рабочих", "Резервный РБУ: 42 км, доплата 18 %" },
                    Yes = new Branch { Title = "Резервный РБУ, доплата 18 %", Text = "Поставка с 3-го дня, график −2 дня, бригады не простаивают.",
                        Phases = new[] { new Phase { N = 210, T0 = 0, T1 = 2 } }, Fixed = 46, FixedAt = 3, PerPersonUnit = 30000, NbLoad = 0, Co2PerUnit = 3.1f, Restore = 2 },
                    No = new Branch { Title = "Ждать основной завод", Text = "12 дней простоя, сдвиг сдачи квартала на 3 недели и штраф по договору.",
                        Phases = new[] { new Phase { N = 210, T0 = 0, T1 = 12 } }, Fixed = 320, FixedAt = 12, PerPersonUnit = 30000, NbLoad = 0, Co2PerUnit = 0.4f, Restore = 12 },
                });
            }

            foreach (var inc in L)
            {
                inc.Avail = y >= inc.MinYear && y <= inc.MaxYear;
                inc.SuggestYear = inc.Avail ? y : Mathf.Clamp(Mathf.Max(inc.MinYear, 2036), inc.MinYear, inc.MaxYear);
                if (inc.Id == "concrete") inc.SuggestYear = 2031;
                Compute(inc, inc.Yes, y); Compute(inc, inc.No, y);
            }
            return L;
        }

        public const int NT = 49;   // samples over the horizon
        static void Compute(Incident inc, Branch b, int y)
        {
            var ph = b.Phases; var n = new float[ph.Length];
            for (int i = 0; i < ph.Length; i++)
            {
                if (ph[i].R > 0) { var bids = new List<int>(); n[i] = ResidentsNear(inc.P, ph[i].R, y, bids); if (i == ph.Length - 1 && !inc.FloodTint && b.Bids.Count == 0) b.Bids = bids; }
                else n[i] = ph[i].N;
            }
            b.Affected = new float[NT]; b.Damage = new float[NT]; b.Co2 = new float[NT]; float dmg = 0, co2 = 0, dt = inc.H / (NT - 1);
            for (int k = 0; k < NT; k++)
            {
                float t = k * dt, a = 0; bool active = false;
                for (int i = 0; i < ph.Length; i++) if (t >= ph[i].T0 && t < ph[i].T1) { a = Mathf.Max(a, n[i]); active = true; }
                if (k > 0) { dmg += a * b.PerPersonUnit * dt / 1e6f; if (active) co2 += b.Co2PerUnit * dt; }
                b.Affected[k] = Mathf.Max(a, k > 0 ? b.Affected[k - 1] : 0); b.Damage[k] = dmg + (t >= b.FixedAt ? b.Fixed : 0); b.Co2[k] = co2;
            }
            b.AffectedMax = n.Length > 0 ? n.Max() : 0; b.Peak = b.Damage[NT - 1];
        }

        // ------------------------------------------------------------------ flood zone (same model as the "Прогноз" tab)
        static int[] flood1;
        static void FloodSet(int y, out Vector2 center, out float people, out float damageBln, out List<int> bids)
        {
            center = DistrictCenter(2); people = 0; damageBln = 0; bids = new List<int>();
            if (flood1 == null)
            {
                try { var j = Parse(File.ReadAllText(Path.Combine(Application.streamingAssetsPath, "twin", "risk.json"))); flood1 = Ints(G(G(G(j, "scenarios"), "flood_1pct"), "depth_cm")); }
                catch (Exception e) { Debug.LogError("[Alatau] risk.json: " + e.Message); flood1 = new int[0]; }
            }
            var db = CityDatabase.Instance; if (db == null) return; double sx = 0, sz = 0, sw = 0;
            foreach (var b in db.Buildings)
            {
                if (b == null || b.Bid >= flood1.Length || flood1[b.Bid] <= 0 || !Stands(b, y)) continue;
                float r = ResidentsOf(b); people += r; bids.Add(b.Bid);
                float share = Mathf.Clamp01(flood1[b.Bid] / 100f / Mathf.Max(3f, b.HeightM)) + 0.05f; damageBln += b.GfaM2 * 300000f * Mathf.Min(0.4f, share) / 1e9f;
                sx += b.X * (r + 1); sz += b.Z * (r + 1); sw += r + 1;
            }
            if (sw > 0) center = new Vector2((float)(sx / sw), (float)(sz / sw));
        }
    }
}
