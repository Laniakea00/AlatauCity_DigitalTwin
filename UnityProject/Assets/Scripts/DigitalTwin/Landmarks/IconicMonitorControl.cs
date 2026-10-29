using System;
using System.Collections.Generic;
using UnityEngine;
using DSources = AlatauCity.DigitalTwin.Data.Sources;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The investor control of the construction monitoring, built on the same model as the schedule and the analytics (no
    /// parallel numbers): readiness by work type from the works of the schedule (Stat), the schedule delay of the complex from the earned
    /// value (the date the plan reached what is done now), the earned-value curves PV / EV / AC from the cost items of the estimate
    /// (Spend, PriceF) scaled to the actual cost of the analytics, the forecast cost EAC of the analytics, the top actions by rules, the
    /// defects pinned on the model, the people and machines by day, the weather of Almaty by month (open climate normals) and the
    /// downtime it causes by the rules of the site. All construction figures are the scenario of the twin; the climate is open data.</summary>
    public partial class IconicMonitor
    {
        // ================================================================== sources
        public const string SrcClimate = "weatherspark_almaty", SrcMon = "mon_schedule", SrcEv = "mon_ev", SrcActs = "mon_actions",
            SrcDefects = "mon_defects", SrcCrew = "mon_crew", SrcDown = "mon_downtime";
        static bool srcDone;
        /// <summary>Registers the open climate source and the models of the monitoring (once; MonitoringModule calls it when it is made).</summary>
        public static void RegisterSources()
        {
            if (srcDone) return; srcDone = true;
            RegisterInvestorSources();
            DSources.Register(SrcClimate, "Климат Алматы: средние по месяцам", "Weather Spark", "", "https://weatherspark.com/y/108859/Average-Weather-in-Almaty-Kazakhstan-Year-Round",
                "Средние дневные максимум и минимум, дни с осадками, снег и средний ветер по месяцам. Пересчёт °F → °C и миль/ч → м/с — QTwin. Открыто 29.10.2026.");
            DSources.RegisterModel(SrcMon, "Мониторинг стройки Iconic Complex и KAIST",
                "График работ, факт по съёмкам, отставание и прогноз ввода — сценарий цифрового двойника. Договоров и данных застройщика нет.");
            DSources.RegisterModel(SrcEv, "Освоенный объём (Earned Value)",
                "PV — работы по графику в ценах сметы, EV — выполненные работы в ценах сметы, AC — фактические затраты с ростом цен. Сметные цены — рынок Алматы 10.2026, курс НБ РК 23.10.2026; затраты и график — модель.");
            DSources.RegisterModel(SrcActs, "Рекомендации «Что делать сейчас»",
                "Правила по данным двойника: отстающая работа критического пути, нехватка людей, погодное окно, дефекты. Эффект на срок ввода — оценка модели.");
            DSources.RegisterModel(SrcDefects, "Дефекты стройки", "Синтетический журнал дефектов технадзора для демонстрации: места, даты и ответственные условные.");
            DSources.RegisterModel(SrcCrew, "Люди и техника на площадке", "Численность по графику работ, нехватка по видеоаналитике, выходные и погодные простои — синтетические данные.");
            DSources.RegisterModel(SrcDown, "Погодные простои",
                "Правила: бетон без прогрева — не ниже −5 °C, башенные краны — ветер не выше 15 м/с, фасад и кровля — без осадков. Разброс суточного минимума ±5 °C и дни с порывами — допущения модели.");
        }

        // ================================================================== readiness by work type
        static readonly string[] WtName = { "Котлован и фундаменты", "Каркас", "Фасад и кровля", "Инженерные системы", "Отделка и оснащение", "Благоустройство", "Пусконаладка и сдача" };
        static readonly string[] WtHint = { "земляные работы, сваи, плиты", "колонны, перекрытия, ядро, металл", "витражи, ламели, кровли, террасы",
            "вентиляция, электрика, лифты, лабораторные сети", "перегородки, полы, потолки, мебель", "мощение, газоны, деревья, фонари", "проверка систем, приёмка, ввод" };
        int WorkType(Work w)
        {
            var n = w.Name.ToLowerInvariant();
            bool Any(params string[] k) { foreach (var x in k) if (n.Contains(x)) return true; return false; }
            if (Any("пусконалад")) return 6;
            if (Any("отделк", "оснащ", "мебел", "перегород", "номера", "аудитор", "раздевал", "классы")) return 4;
            if (Any("инженер", "сети", "эскалатор", "чистые", "фуд-холл")) return Pt(w.Part).Land ? 5 : 3;
            if (Pt(w.Part).Land) return 5;
            if (Any("котлован", "сва", "фундамент", "ограждени", "дренаж", "планировк", "ростверк")) return 0;
            if (Any("бассейн", "сад ", "газон", "дерев", "мощени", "дорожк", "фонар", "фонтан", "площадь", "амфитеатр", "двор", "беговые", "озер", "сдача")) return 5;
            if (Any("фасад", "витраж", "витрин", "ламел", "кровл", "террас", "рёбр", "стеклян", "софит")) return 2;
            return 1;
        }
        /// <summary>Plan and actual readiness of work type t in building part (−1: the whole complex) at date d, weighted by the budget of the
        /// building and the length of the work. False when the type has no works there.</summary>
        bool TypeReady(int t, int part, float d, out float plan, out float fact, out int lagDays)
        {
            float w8 = 0f, p = 0f, f = 0f; lagDays = 0; plan = fact = 0f;
            for (int k = 0; k < works.Count; k++)
            {
                var w = works[k]; if (w.Sum || part >= 0 && w.Part != part || WorkType(w) != t) continue;
                float wt = Pt(w.Part).Capex * Mathf.Max(w.B - w.A, 0.02f); var s = Stat(w, d);
                w8 += wt; p += wt * s.Plan; f += wt * s.Fact;
                if (s.Plan > 0f && s.Fact < 0.999f) lagDays = Mathf.Max(lagDays, s.Days);
            }
            if (w8 <= 0f) return false;
            plan = p / w8; fact = f / w8; return true;
        }

        // ================================================================== the schedule delay of the complex (earned schedule)
        /// <summary>How many days behind the plan the complex is at date d: the plan reached the value done at d that many days earlier
        /// (earned schedule — the same weights as the budget, so a late big building counts more than a late lawn).</summary>
        int SchedDelay(float d)
        {
            float ev = Spent(d, true); if (ev <= 0.01f) return 0;
            float a = T0 - 1f, b = d + 1f;
            for (int k = 0; k < 26; k++) { float m = (a + b) * 0.5f; if (Spent(m, false) >= ev) b = m; else a = m; }
            return Mathf.RoundToInt((d - b) * 365f);
        }
        /// <summary>The delay at the surveys up to the date of the monitoring (the last few), oldest first.</summary>
        readonly List<float> trendT = new List<float>(); readonly List<int> trendD = new List<int>();
        void MakeTrend()
        {
            trendT.Clear(); trendD.Clear();
            int from = Mathf.Max(0, svA - 4);
            for (int k = from; k <= svA && k < surveys.Count; k++) { if (Spent(surveys[k], true) <= 0.01f) continue; trendT.Add(surveys[k]); trendD.Add(SchedDelay(surveys[k])); }
        }
        /// <summary>The words of the trend of the delay: growing, shrinking or steady, against the previous survey.</summary>
        string TrendText(out string cls)
        {
            cls = "ok";
            if (trendD.Count < 2) return "первая съёмка с начала работ — тренда пока нет";
            int a = trendD[trendD.Count - 2], b = trendD[trendD.Count - 1], dd = b - a;
            if (dd > 3) { cls = "bad"; return $"растёт: +{dd} дн. с прошлой съёмки {Day(trendT[trendT.Count - 2])}"; }
            if (dd < -3) { cls = "ok"; return $"сокращается: −{-dd} дн. с прошлой съёмки {Day(trendT[trendT.Count - 2])}"; }
            cls = b > 3 ? "warn" : "ok"; return $"не меняется с прошлой съёмки {Day(trendT[trendT.Count - 2])}";
        }
        /// <summary>The building handed over last by the forecast (the completion of the complex).</summary>
        int LastPart(float d) { int last = 0; for (int i = 1; i < L.Parts.Count; i++) if (FactDate(i, 1f) > FactDate(last, 1f)) last = i; return last; }

        // ================================================================== earned value
        const int EvN = 96;
        readonly float[] evT = new float[EvN + 1], evPV = new float[EvN + 1], evEV = new float[EvN + 1], evAC = new float[EvN + 1];
        float evBac, evEac, evAcR, evCpi = 1f, evSpi = 1f;
        /// <summary>The curves over the timeline: planned value and earned value from the progress (Spent), the actual cost by integrating
        /// the work done at the prices of its time (PriceF), scaled so it meets the actual cost of the analytics on the survey date; after the
        /// survey the cost runs from there to the forecast EAC along the earned value.</summary>
        void MakeEv()
        {
            int n = L.Parts.Count, ni = Items.Length;
            var q = new float[n, ni]; float acRaw = 0f, acRawR = -1f; var acs = new float[EvN + 1];
            const int sub = 4; float step = (T1 - T0) / (EvN * sub);
            for (int j = 0; j <= EvN; j++)
            {
                float t = T0 + (T1 - T0) * j / EvN; evT[j] = t; evPV[j] = Spent(t, false); evEV[j] = Spent(t, true);
            }
            for (int s = 0; s <= EvN * sub; s++)
            {
                float t = T0 + s * step, tt = Mathf.Min(t, Report);
                for (int i = 0; i < n; i++)
                {
                    float fp = FactP(i, tt);
                    for (int k = 0; k < ni; k++)
                    {
                        float sh = ShareOf(i, k); if (sh <= 0f) continue;
                        float nq = ItemQ(Items[k], fp); if (nq > q[i, k]) { acRaw += Pt(i).Capex * sh * (nq - q[i, k]) * PriceF(k, tt); q[i, k] = nq; }
                    }
                }
                if (acRawR < 0f && t >= Report) acRawR = acRaw;
                if (s % sub == 0) acs[s / sub] = acRaw;
            }
            if (acRawR < 0f) acRawR = acRaw;
            float k0 = acRawR > 0.01f ? anTot.Ac / acRawR : 1f;
            evBac = anTot.B; evEac = anTot.Eac; evAcR = anTot.Ac;
            float evR = anTot.Ev, rest = Mathf.Max(evBac - evR, 0.01f);
            for (int j = 0; j <= EvN; j++)
                evAC[j] = evT[j] <= Report ? acs[j] * k0 : evAcR + (evEac - evAcR) * Mathf.Clamp01((evEV[j] - evR) / rest);
            float pvR = Spent(Report, false);
            evCpi = anTot.Ac > 0.01f ? anTot.Ev / anTot.Ac : 1f;
            evSpi = pvR > 0.01f ? anTot.Ev / pvR : 1f;
        }
        /// <summary>The actual cost at date d up to the survey (interpolated on the curve).</summary>
        float AcAt(float d)
        {
            if (Mathf.Abs(d - Report) < 1e-4f) return evAcR;                       // the survey date: exactly the actual cost of the analytics
            float x = Mathf.Clamp((d - T0) / (T1 - T0) * EvN, 0f, EvN); int j = Mathf.Min(Mathf.FloorToInt(x), EvN - 1);
            return Mathf.Lerp(evAC[j], evAC[j + 1], x - j);
        }
        static string Ix(float v) => v.ToString("0.00", Loc.Ru);
        /// <summary>SPI in plain words: "работы идут на 8 % медленнее плана".</summary>
        static string SpiWords(float spi)
        {
            int p = Mathf.RoundToInt(Mathf.Abs(1f - spi) * 100f);
            return p < 1 ? "работы идут точно по плану" : spi < 1f ? $"работы идут на {p} % медленнее плана" : $"работы идут на {p} % быстрее плана";
        }
        /// <summary>CPI in plain words: "каждый доллар даёт работ на 0,96 $".</summary>
        static string CpiWords(float cpi)
        {
            int p = Mathf.RoundToInt(Mathf.Abs(1f - cpi) * 100f);
            return p < 1 ? "работы стоят столько, сколько в смете" : cpi < 1f ? $"работы обходятся на {p} % дороже сметы" : $"работы обходятся на {p} % дешевле сметы";
        }

        // ================================================================== what to do now
        class Act { public string Icon, Title, Why, Effect; public int Days, Sev; public Action Show; public string ShowText; }
        /// <summary>The actions at date d, by rules over the data of the twin, the largest effect on the hand-over first (three at most).</summary>
        List<Act> Actions(float d)
        {
            var list = new List<Act>(); int n = L.Parts.Count;
            // 1. the work most behind on the building most behind: a second shift on it
            int wb = -1, wd = 3;
            for (int i = 0; i < n; i++) { var o = Obj(i, d); if (o.Fact > 0f && o.Fact < 0.999f && o.Days > wd) { wd = o.Days; wb = i; } }
            if (wb >= 0)
            {
                int lw = LagWork(wb, d);
                if (lw >= 0)
                {
                    var w = works[lw]; var st = Stat(w, d); var o = Obj(wb, d);
                    float rem = Mathf.Max(PlanDate(wb, w.B) - d, 0.05f) * 365f;
                    int eff = Mathf.Clamp(Mathf.RoundToInt(Mathf.Min(o.Days * 0.6f, rem * 0.2f)), 3, Mathf.Max(o.Days, 3));
                    int b = wb;
                    list.Add(new Act { Icon = "clock", Sev = o.Days > 21 ? 2 : 1, Days = eff,
                        Title = $"Вторая смена на работе «{w.Name}» · {Pt(wb).Short}",
                        Why = $"Факт {Pct(st.Fact)} при плане {Pct(st.Plan)}, отставание {st.Days} дн. От этой работы зависит ввод «{Pt(wb).Name}».",
                        ShowText = "Показать в 4D", Show = () => { SetTab(T4D); SelectObj(b, true); } });
                }
            }
            // 2. people short: the trade most short on the building most short
            int cb = -1; float cs = 0.08f; List<Trade> ct = null;
            for (int i = 0; i < n; i++)
            {
                var tr = Trades(i, d); Sum(tr, out int need, out int have); if (need < 20) continue;
                float sh = (need - have) / (float)need; if (sh > cs) { cs = sh; cb = i; ct = tr; }
            }
            if (cb >= 0 && ct != null && ct.Count > 0)
            {
                var t0 = ct[0]; int lw = LagWork(cb, d);
                float rem = lw >= 0 ? Mathf.Max(PlanDate(cb, works[lw].B) - d, 0.05f) * 365f : 60f;
                int eff = Mathf.Max(2, Mathf.RoundToInt(cs * rem * 0.35f));
                list.Add(new Act { Icon = "hard_hat", Sev = cs >= 0.2f ? 2 : 1, Days = eff,
                    Title = $"Добрать {Mathf.Max(t0.Need - t0.Have, 5)} чел.: {t0.Name.ToLowerInvariant()} · {Pt(cb).Short}",
                    Why = $"На площадке {t0.Have} из {t0.Need} человек этой профессии по графику. По договору генподрядчик восполняет нехватку больше 10 % за 5 дней.",
                    ShowText = "Камеры", Show = () => SetTab(TVid) });
            }
            // 3. the weather of the next three months: a cold spell ahead of the frame, or a dry window for the envelope
            bool frame = false, skin = false;
            foreach (var w in works)
            {
                if (w.Sum) continue; var s = Stat(w, d); if (!(s.Fact < 0.999f && PlanDate(w.Part, w.A) < d + 0.3f)) continue;
                int t = WorkType(w); if (t == 0 || t == 1) frame = true; if (t == 2) skin = true;
            }
            int m0 = MonthOf(d); float cold = 0f, wet = 0f; int coldM = -1;
            for (int k = 1; k <= 3; k++) { int m = (m0 + k) % 12; cold += ColdDays(m); wet += WetDays[m]; if (coldM < 0 && ColdDays(m) > 8f) coldM = m; }
            if (frame && coldM >= 0)
            {
                int eff = Mathf.Max(2, Mathf.RoundToInt(cold * ConcreteLoss * 0.6f));
                list.Add(new Act { Icon = "cloud_sun", Sev = 1, Days = eff,
                    Title = $"Подготовить прогрев бетона и тепляки до холодов ({MonthName[coldM]})",
                    Why = $"В ближайшие три месяца ≈ {Mathf.RoundToInt(cold)} дн. с морозом ниже −5 °C: без прогрева бетонирование встаёт. По климатической норме Алматы.",
                    ShowText = "Погода", Show = () => CtlView(2) });
            }
            else if (skin)
            {
                int eff = Mathf.Max(2, Mathf.RoundToInt(wet * WetLoss * 0.5f));
                list.Add(new Act { Icon = "cloud_sun", Sev = 0, Days = eff,
                    Title = $"Уплотнить монтаж фасада в сухие месяцы ({MonthName[(m0 + 1) % 12]}–{MonthName[(m0 + 3) % 12]})",
                    Why = $"Впереди ≈ {Mathf.RoundToInt(wet)} дн. с осадками за три месяца: в эти дни фасад и кровля не монтируются. Дополнительный подъёмник забирает сухие дни.",
                    ShowText = "Погода", Show = () => CtlView(2) });
            }
            // 4. critical defects open at the date
            int crit = 0, open = 0; foreach (var f in defects) if (f.Found <= d && !(f.Closed > 0f && f.Closed <= d)) { open++; if (f.Sev >= 2) crit++; }
            if (crit > 0)
                list.Add(new Act { Icon = "triangle_alert", Sev = 2, Days = 2 + crit * 2,
                    Title = $"Закрыть {crit} {Crit(crit)} до следующего этапа",
                    Why = $"Открыто {open} дефектов, из них критических — {crit}. Если их не устранить до монтажа следующего этапа, придётся разбирать уже смонтированное.",
                    ShowText = "Дефекты", Show = () => SetTab(TDef) });
            // 5. the cost item that grows most: fix the price (no days, money)
            int top = TopOver();
            if (top >= 0 && list.Count < 3)
            {
                int r = MainRes(top); var ic = ItemCost(top, -1);
                list.Add(new Act { Icon = "coins", Sev = 0, Days = 0,
                    Title = $"Зафиксировать цену: {Rsc[r].Name.ToLowerInvariant()}",
                    Why = $"Статья «{Items[top].Name}» дорожает на {Mln(ic.Over)}. Договор на оставшийся объём по фиксированной цене остановит рост.",
                    ShowText = "Смета", Show = () => { SetTab(TAn); anItem = top; AnView(1); } });
            }
            list.Sort((a, b) => b.Days != a.Days ? b.Days.CompareTo(a.Days) : b.Sev.CompareTo(a.Sev));
            if (list.Count > 3) list.RemoveRange(3, list.Count - 3);
            foreach (var a in list) a.Effect = a.Days > 0 ? $"эффект: ввод раньше на ≈ {a.Days} дн." : "эффект на срок ввода нет — экономия бюджета";
            return list;
        }
        static string Crit(int n) { int m = n % 100, d = n % 10; return m >= 11 && m <= 14 ? "критических дефектов" : d == 1 ? "критический дефект" : d >= 2 && d <= 4 ? "критических дефекта" : "критических дефектов"; }

        // ================================================================== defects
        class Defect { public string No, Type, Text, Who, Where; public int Part, Sev; public float Found, Due, Closed; public Vector3 Pos; }
        readonly List<Defect> defects = new List<Defect>();
        static readonly string[] DefSev = { "малозначительный", "значительный", "критический" };
        static readonly string[] DefCls = { "info", "warn", "bad" };
        /// <summary>The defects found by the technical supervision up to the survey: plausible points of the buildings that stand by then (the
        /// tower: on its floors below the working one, on the east face; the other buildings: on their built part).</summary>
        void MakeDefects()
        {
            defects.Clear(); float d = Report; int no = 1;
            void Add(int part, float daysAgo, float closedAgo, int sev, string type, string text, string who, string where, Vector3 pos)
            {
                float found = d - daysAgo / 365f; if (FactP(part, found) <= 0.04f) return;
                defects.Add(new Defect { No = $"Д-{no++:00}", Part = part, Sev = sev, Type = type, Text = text, Who = who, Where = where, Pos = pos,
                    Found = found, Due = found + (sev >= 2 ? 7f : sev == 1 ? 14f : 30f) / 365f, Closed = closedAgo >= 0f ? d - closedAgo / 365f : -1f });
            }
            // the tower: floors that stand at the survey, on the east face
            float tp = FactP(TI, d);
            if (tp > 0.1f)
            {
                int wf = WorkFloor(tp), top = Mathf.Max(wf - 1, 2);
                Vector3 F(int f, float dz) { f = Mathf.Clamp(f, 1, IconicShape.Levels - 1); float y = IconicShape.FloorY(f) + 1.4f; return new Vector3(IconicShape.Xr + 0.5f, y, IconicShape.Cz + IconicShape.Depth(y) * dz); }
                string T = Pt(TI).Short;
                int fs = anFloor >= 0 ? anFloor : Mathf.Max(top - 2, 1);
                Add(TI, 9f, -1f, 1, "Геометрия", $"Отметка плиты {fs + 1}‑го этажа +14 мм при допуске ±10 мм (точка 4 исполнительной съёмки)", "Генподрядчик · монолит", $"{T} · {fs + 1}‑й этаж", F(fs, 0.18f));
                Add(TI, 4f, -1f, 2, "Армирование", $"Защитный слой арматуры колонн {top + 1}‑го этажа 18 мм при проекте 30 мм", "Генподрядчик · монолит", $"{T} · {top + 1}‑й этаж", F(top, -0.2f));
                Add(TI, 34f, 21f, 1, "Бетон", $"Раковины и непроливы бетона на колонне {Mathf.Max(top - 6, 1) + 1}‑го этажа — заделаны ремонтным составом", "Генподрядчик · монолит", $"{T} · {Mathf.Max(top - 6, 1) + 1}‑й этаж", F(top - 6, 0.32f));
                int ff = Front(IconicFloors.PFacade, tp);
                if (ff > 2) Add(TI, 12f, -1f, 1, "Фасад", $"Зазор в примыкании модуля витража к плите {ff + 1}‑го этажа 12 мм при норме 6 мм", "Субподрядчик · фасад", $"{T} · {ff + 1}‑й этаж", F(ff, 0.05f));
                if (ff > 6) Add(TI, 48f, 30f, 0, "Фасад", $"Царапины на стекле модуля {Mathf.Max(ff - 5, 1) + 1}‑го этажа — модуль заменён", "Субподрядчик · фасад", $"{T} · {Mathf.Max(ff - 5, 1) + 1}‑й этаж", F(ff - 5, -0.3f));
                int mf = Front(IconicFloors.PServices, tp);
                if (mf > 2) Add(TI, 6f, -1f, 0, "Инженерия", $"Кабельные лотки {mf + 1}‑го этажа не закреплены на подвесах", "Субподрядчик · инженерия", $"{T} · {mf + 1}‑й этаж", F(mf, -0.05f));
                if (tp > 0.14f) Add(TI, 70f, 52f, 2, "Фундамент", "Трещина в защитной стяжке фундаментной плиты у приямка лифтов — инъектирование выполнено", "Генподрядчик · монолит", $"{T} · фундаментная плита", new Vector3(IconicShape.Xr - IconicShape.W0 * 0.5f, 2f, IconicShape.Cz));
            }
            // the other buildings: on their built part
            string[] typ = { "Геометрия", "Гидроизоляция", "Бетон", "Металл", "Кровля" };
            string[] txt = { "Отклонение колонны от вертикали 18 мм при допуске 12 мм", "Протечка гидроизоляции в узле примыкания к стене", "Трещины усадки в плите перекрытия шириной до 0,3 мм",
                "Не затянуты высокопрочные болты в узле фермы", "Повреждение мембраны кровли у воронки водостока" };
            string[] who = { "Генподрядчик · монолит", "Субподрядчик · кровля", "Генподрядчик · монолит", "Субподрядчик · металлоконструкции", "Субподрядчик · кровля" };
            for (int i = 0; i < L.Parts.Count; i++)
            {
                if (i == TI) continue; var p = Pt(i); float fp = FactP(i, d); if (fp < 0.12f) continue;
                float h = p.Land ? 0.6f : Mathf.Max(p.H * Mathf.Clamp01((fp - 0.08f) / 0.62f), 3f);
                if (p.Land)
                {
                    Add(i, 15f, -1f, 0, "Благоустройство", "Просадка щебёночного основания под мощением до 25 мм", "Генподрядчик · благоустройство", p.Short, new Vector3(p.Focus.x + 8f, 0.6f, p.Focus.z - 6f));
                    continue;
                }
                int a = (i * 3 + L.Id.Length) % txt.Length, b = (a + 2) % txt.Length;
                Add(i, 5f + i * 3f, -1f, i % 3 == 1 ? 2 : 1, typ[a], txt[a], who[a], p.Short, new Vector3(p.Focus.x - 6f + i * 2f, h * 0.55f, p.Focus.z + 4f));
                Add(i, 40f + i * 5f, 18f + i * 2f, 1, typ[b], txt[b] + " — устранено", who[b], p.Short, new Vector3(p.Focus.x + 7f, h * 0.85f, p.Focus.z - 5f));
            }
            defects.Sort((x, y) => y.Found.CompareTo(x.Found));
        }
        bool DefOpen(Defect f, float d) => f.Found <= d && !(f.Closed > 0f && f.Closed <= d);

        // ================================================================== people and machines by day
        /// <summary>People on the site on the day of date d: the crew of the schedule less the people short (Crew), fewer on Saturdays,
        /// a duty shift on Sundays, fewer on a day stopped by the weather; machines follow the people, the cranes stop in the wind.</summary>
        void DayCrew(float d, out int people, out int plan, out int machines, out bool weather)
        {
            var t = new DateTime(Mathf.FloorToInt(d), 1, 1).AddDays(Mathf.Floor((d - Mathf.Floor(d)) * 365f));
            int key = t.Year * 400 + t.DayOfYear;
            float dow = t.DayOfWeek == DayOfWeek.Sunday ? 0.3f : t.DayOfWeek == DayOfWeek.Saturday ? 0.7f : 1f;
            float pd = Mathf.Clamp01(DownDays(t.Month - 1) / 30.4f);
            weather = Hash(key * 7 + 3) < pd && t.DayOfWeek != DayOfWeek.Sunday;
            float c = Crew(d, true), cp = Crew(d, false);
            people = Mathf.RoundToInt(c * dow * (weather ? 0.6f : 1f) * (0.95f + 0.1f * Hash(key)));
            plan = Mathf.RoundToInt(cp * dow);
            machines = c < 1f ? 0 : Mathf.RoundToInt((c / 42f + 2f) * (dow < 0.5f ? 0.3f : 1f) * (weather ? 0.55f : 1f) * (0.9f + 0.2f * Hash(key * 13 + 1)));
        }
        static float Hash(int k) { float s = Mathf.Sin(k * 12.9898f + 78.233f) * 43758.5453f; return s - Mathf.Floor(s); }

        // ================================================================== weather of Almaty and downtime
        // Weather Spark, Almaty: average daily high / low (°F → °C), days with precipitation, average wind (mph → m/s)
        static readonly float[] TempHi = { -1.7f, 0.6f, 8.3f, 16.7f, 22.2f, 26.7f, 29.4f, 28.3f, 23.3f, 15.6f, 6.7f, 0.6f };
        static readonly float[] TempLo = { -10.6f, -8.9f, -2.2f, 5.0f, 10.0f, 13.9f, 16.1f, 13.9f, 8.9f, 2.8f, -3.3f, -8.3f };
        static readonly float[] WetDays = { 3.2f, 3.2f, 5.9f, 6.9f, 7.7f, 5.4f, 4.6f, 3.2f, 2.9f, 4.9f, 4.9f, 3.8f };
        static readonly float[] WindMs = { 2.4f, 2.5f, 2.6f, 2.7f, 2.7f, 2.7f, 2.7f, 2.7f, 2.6f, 2.5f, 2.5f, 2.4f };
        static readonly string[] MonthName = { "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь" };
        static readonly string[] MonthShort = { "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек" };
        /// <summary>The share of the day lost: concreting slowed by heating, cranes stopped for half a shift in a gust, facade and roofing
        /// stopped on a day with rain or snow (a third of the working time on average).</summary>
        const float ConcreteLoss = 0.25f, CraneLoss = 0.6f, WetLoss = 0.35f;
        static int MonthOf(float d) => Mathf.Clamp(Mathf.FloorToInt((d - Mathf.Floor(d)) * 12f), 0, 11);
        /// <summary>Days of month m with the night below −5 °C: the daily minimum spread ±5 °C around the normal (model).</summary>
        static float ColdDays(int m) => 30.4f * Phi((-5f - TempLo[m]) / 5f);
        /// <summary>Days of month m with gusts over 15 m/s, when the tower cranes stop (model: more in the windier months).</summary>
        static float GustDays(int m) => 0.5f + (WindMs[m] - 2.4f) * 4f;
        static float DownDays(int m) => ColdDays(m) * ConcreteLoss + GustDays(m) * CraneLoss + WetDays[m] * WetLoss;
        static float Phi(float x) => 1f / (1f + Mathf.Exp(-1.702f * x));
        /// <summary>The downtime over the months from a to b (years), by the month normals.</summary>
        static float DownBetween(float a, float b)
        {
            float s = 0f; for (float t = a; t < b; t += 1f / 12f) s += DownDays(MonthOf(t)) * Mathf.Clamp01((b - t) * 12f); return s;
        }
    }
}
