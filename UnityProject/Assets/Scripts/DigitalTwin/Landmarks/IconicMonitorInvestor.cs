using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using DSrcI = AlatauCity.DigitalTwin.Data.Sources;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The state of the construction monitoring of one object in plain numbers and words, for other parts of the twin (the AI
    /// assistant): the same model and the same date (the last survey) as the «Контроль» page. Ok = false when it could not be computed.</summary>
    public struct MonitorSummary
    {
        public bool Ok;
        public string Id, Name, SurveyDate;
        /// <summary>Readiness of the complex (0…1, weighted by budgets): actual and planned at the survey date.</summary>
        public float Readiness, PlanReadiness;
        /// <summary>Days of work behind the plan now (earned schedule), and how far the forecast hand-over moves against the plan.</summary>
        public int DelayDays, HandoverShiftDays;
        public string PlanHandover, ForecastHandover;
        /// <summary>Earned value: SPI (pace against the schedule), CPI (value of the work per dollar spent).</summary>
        public float Spi, Cpi;
        /// <summary>Millions of US dollars: budget, reserve, actual cost to date, planned value and earned value at the date, forecast at completion.</summary>
        public float BudgetMln, ReserveMln, SpentMln, PlannedMln, EarnedMln, EacMln;
        /// <summary>The three actions of «Что делать сейчас» (title — effect), the first one with its effect on the hand-over in days.</summary>
        public string TopAction; public int TopActionDays; public string[] Actions;
        public int OpenDefects, CriticalDefects;
        /// <summary>Permits and acts: waited for (not yet due) and overdue, with the names of the overdue ones.</summary>
        public int DocsWaiting, DocsOverdue; public string[] OverdueDocs;
        /// <summary>The three answers of the strip in words: «Успеваем?», «Сколько потрачено?», «Что делать?».</summary>
        public string OnTrack, Spending, ToDo;
    }

    /// <summary>The investor layer of the construction monitoring: the strip with three answers over every page («Успеваем?»,
    /// «Сколько потрачено?», «Что делать?»), the permits and acts of the object with their statuses, the digest «Что изменилось»
    /// with a preview of the notification it would be, and a static read-only summary for the rest of the twin.</summary>
    public partial class IconicMonitor
    {
        public const string SrcDocs = "mon_docs", SrcDigest = "mon_digest", SrcPrices = "mon_price_assume";
        static void RegisterInvestorSources()
        {
            DSrcI.RegisterModel(SrcDocs, "Разрешительная и исполнительная документация",
                "Перечень по порядку строительства в РК (АПЗ, технические условия, экспертиза, уведомление о начале СМР, акты скрытых работ, приёмка). Даты, статусы и ответственные — синтетический сценарий двойника.");
            DSrcI.RegisterModel(SrcDigest, "Сводка «Что изменилось»",
                "Разница модели двойника между двумя датами: готовность по видам работ, деньги, дефекты, документы, люди и погода. Уведомление — демонстрация, ничего не отправляется.");
            DSrcI.RegisterModel(SrcPrices, "Допущения цен сметы",
                "Из открытых данных: цены бетона, арматуры и металлопроката — объявления olx.kz по Алматы 22–26.10.2026, курс доллара — НБ РК 23.10.2026. Остальное — допущения модели: цены фасадных модулей, труда и аренды крана, индексы отделки и благоустройства, рост цен в год, доля закупок по фиксированной цене, резерв 4 %, надбавка 25 % за вторую смену.");
        }

        // ================================================================== the summary for the rest of the twin
        static readonly Dictionary<string, MonitorSummary> sumCache = new Dictionary<string, MonitorSummary>();
        /// <summary>The state of the monitoring of landmark id ("iconic", "kaist") at its last survey. Computed once and kept; while the window
        /// is open on another object, an object not computed yet returns Ok = false.</summary>
        public static MonitorSummary Summary(string landmarkId)
        {
            if (string.IsNullOrEmpty(landmarkId)) return default;
            if (sumCache.TryGetValue(landmarkId, out var s)) return s;
            var m = Instance; if (m == null || m.open) return default;
            return m.Dry(landmarkId) && sumCache.TryGetValue(landmarkId, out s) ? s : default;
        }
        /// <summary>Computes the model of object id without opening the window (the tower profile is swapped for the time of the call).</summary>
        bool Dry(string id)
        {
            var ls = LandmarkSystem.Instance; var prof = TowerProfile.For(id);
            if (open || ls == null || !ls.Ready || prof == null) return false;
            var l = ls.Get(id); if (l == null || l.Parts == null || l.Main < 0) return false;
            var keep = IconicShape.P;
            try
            {
                IconicShape.P = prof; RegisterSources();
                L = l; H = l.Height; Report = l.Begin + 0.5f * (l.Finish - l.Begin); T0 = Mathf.Floor(l.Begin); T1 = Mathf.Max(Mathf.Ceil(l.Finish + 0.05f), l.EndYear + 1f);
                MakeModel(); sumCache[id] = Collect();
                return true;
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] monitoring summary " + id + ": " + e.Message); return false; }
            finally { IconicShape.P = keep; }
        }
        /// <summary>The whole model of the object at its survey date: schedule, surveys, estimate, earned value, trend, defects, documents.</summary>
        void MakeModel() { MakeWorks(); MakeSurveys(); MakeAnalytics(); MakeEv(); MakeTrend(); MakeDefects(); MakePermits(); }
        MonitorSummary Collect()
        {
            float d = Report; var s = new MonitorSummary { Ok = true, Id = L.Id, Name = L.Name, SurveyDate = Day(d) };
            s.Readiness = Ready(d, true); s.PlanReadiness = Ready(d, false); s.DelayDays = SchedDelay(d);
            int last = LastPart(d); float fe = FactDate(last, 1f);
            s.HandoverShiftDays = Mathf.RoundToInt((fe - L.Finish) * 365f); s.PlanHandover = IconicFloors.MonthYear(L.Finish); s.ForecastHandover = IconicFloors.MonthYear(fe);
            s.Spi = evSpi; s.Cpi = evCpi; s.BudgetMln = evBac; s.ReserveMln = anRes; s.SpentMln = evAcR; s.PlannedMln = Spent(d, false); s.EarnedMln = anTot.Ev; s.EacMln = evEac;
            var acts = Actions(d); topActs = acts; s.Actions = new string[acts.Count];
            for (int i = 0; i < acts.Count; i++) s.Actions[i] = acts[i].Title + " — " + acts[i].Effect;
            if (acts.Count > 0) { s.TopAction = acts[0].Title; s.TopActionDays = acts[0].Days; }
            foreach (var f in defects) if (DefOpen(f, d)) { s.OpenDefects++; if (f.Sev >= 2) s.CriticalDefects++; }
            var od = new List<string>();
            foreach (var p in permits) { int st = PermitState(p, d); if (st == 1) s.DocsWaiting++; else if (st == 2) { s.DocsOverdue++; od.Add(p.Name); } }
            s.OverdueDocs = od.ToArray();
            Answers(out s.OnTrack, out _, out _, out s.Spending, out _, out _, out s.ToDo, out _, out _);
            return s;
        }

        // ================================================================== the three answers
        /// <summary>«Успеваем?», «Сколько потрачено?», «Что делать?» at the survey date: the answer, the line under it, its class.</summary>
        void Answers(out string a1, out string s1, out string c1, out string a2, out string s2, out string c2, out string a3, out string s3, out string c3)
        {
            float d = Report; int sd = SchedDelay(d), last = LastPart(d); float fe = FactDate(last, 1f);
            int ld = Mathf.RoundToInt((fe - L.Finish) * 365f); string fm = IconicFloors.MonthYear(fe), pm = IconicFloors.MonthYear(L.Finish);
            if (ld > 3) { a1 = $"Нет: ввод {fm} — позже плана на {ld} дн."; c1 = ld > 21 ? "bad" : "warn"; }
            else if (sd > 3) { a1 = $"Да, ввод {fm} по плану"; c1 = "warn"; }
            else { a1 = $"Да, ввод {fm} по плану"; c1 = "ok"; }
            s1 = sd > 3 ? $"сейчас позади графика на {sd} дн. · {SpiWords(evSpi)}" : $"работы в графике · план ввода {pm}";
            float pv = Spent(d, false), share = evBac > 0.01f ? evAcR / evBac : 0f;
            a2 = $"{Mln(evAcR)} — {Pct(share)} бюджета {Mln(evBac)}";
            s2 = $"по графику к этой дате — работ на {Mln(pv)} · {CpiWords(evCpi)}";
            c2 = NetOver > 0f ? "bad" : evCpi < 0.99f || anTot.Over > 0f ? "warn" : "ok";
            if (topActs == null) topActs = Actions(d);
            if (topActs.Count > 0) { var a = topActs[0]; a3 = a.Title; s3 = a.Effect; c3 = a.Days > 0 ? "ok" : "muted"; }
            else { a3 = "Действий не требуется"; s3 = "все объекты идут по графику"; c3 = "ok"; }
        }
        List<Act> topActs;
        VisualElement ansBar;
        /// <summary>The strip under the header of the window: the three answers of the investor, the same on every page.</summary>
        void BuildAnswers(VisualElement win)
        {
            topActs = Actions(Report);
            Answers(out var a1, out var s1, out var c1, out var a2, out var s2, out var c2, out var a3, out var s3, out var c3);
            ansBar = Box(win, "w7-ans");
            var when = Box(ansBar, "w7-ans-when", false);
            Txt(when, "на дату съёмки", "w7-ans-q"); Txt(when, Day(Report), "w7-ans-d");
            AnsCell("Успеваем?", "calendar", a1, s1, c1, () => CtlView(0));
            AnsCell("Сколько потрачено?", "coins", a2, s2, c2, () => { SetTab(TAn); AnView(0); });
            AnsCell("Что делать?", "sparkles", a3, s3, c3, () => CtlView(0)).AddToClassList("todo");
            var mt = SourceTags.ModelTag(SrcMon); mt.AddToClassList("w7-ans-tag"); ansBar.Add(mt);
        }
        VisualElement AnsCell(string q, string icon, string ans, string sub, string cls, Action click)
        {
            var b = new Button(click) { focusable = false }; b.AddToClassList("w7-ans-c"); b.AddToClassList(cls); ansBar.Add(b);
            var top = Box(b, "w7-ans-top", false);
            var ic = TwinUI.Icon(icon, 13); ic.AddToClassList("w7-ans-ic"); top.Add(ic);
            Txt(top, q, "w7-ans-q");
            var dot = Box(top, "w7-ans-dot " + cls, false);
            Txt(b, ans, "w7-ans-a " + cls);
            Txt(b, sub, "w7-ans-s");
            return b;
        }

        // ================================================================== permits and acts
        /// <summary>A document of the object: what, the stage it belongs to, who is responsible, when it is due and when it was received
        /// (−1 not yet); Note — one line of what it is, for an investor.</summary>
        class Permit { public string Name, Note, Who; public int Stage; public float Due, Got = -1f; }
        readonly List<Permit> permits = new List<Permit>();
        static readonly string[] PermitStage = { "Земля и проект", "Стройка: исполнительная документация", "Ввод в эксплуатацию" };
        static readonly string[] PermitWord = { "есть", "ждём", "просрочено" };
        static readonly string[] PermitCls = { "ok", "warn", "bad" };
        /// <summary>0 — received, 1 — waited for (not due yet), 2 — overdue, at date d.</summary>
        static int PermitState(Permit p, float d) => p.Got >= 0f && p.Got <= d + 1e-5f ? 0 : p.Due < d - 1e-5f ? 2 : 1;
        void MakePermits()
        {
            permits.Clear(); float B = Mathf.Max(L.Begin, 2026.5f), R = Report, F = L.Finish; const float D = 1f / 365f;
            bool kaist = L.Id == "kaist"; string tw = Pt(TI).Short;
            Permit P(int stage, string name, string note, string who, float due, float got)
            { var p = new Permit { Stage = stage, Name = name, Note = note, Who = who, Due = due, Got = got }; permits.Add(p); return p; }
            // land and design: everything before the works start
            P(0, "Акт на право землепользования", "участок в Alatau City под объект", "Заказчик", B - 0.42f, B - 0.44f);
            P(0, "Архитектурно-планировочное задание (АПЗ)", "условия застройки участка: высота, отступы, подъезды", "местный исполнительный орган", B - 0.38f, B - 0.4f);
            P(0, "Технические условия на подключение к сетям", "электричество, вода, канализация, тепло", "сетевые организации", B - 0.34f, B - 0.33f);
            if (kaist) P(0, "Санитарно-эпидемиологическое заключение на лаборатории", "вентиляция и газы чистых помещений", "органы санитарно-эпидемиологического контроля", B - 0.3f, B - 0.31f);
            else P(0, "Согласование высотного объекта с гражданской авиацией", "башня 272 м: заградительные огни и маркировка", "уполномоченный орган гражданской авиации", B - 0.32f, B - 0.29f);
            P(0, "Заключение комплексной вневедомственной экспертизы", "проект и смета соответствуют нормам РК", "государственная экспертиза", B - 0.2f, B - 0.2f);
            P(0, "Уведомление о начале строительно-монтажных работ", "подано до начала работ, назначены технадзор и авторский надзор", "Заказчик · органы архитектурно-строительного контроля", B - 0.02f, B - 0.025f);
            // the works: acts of hidden works and as-built schemes follow the progress of the buildings
            float fnd = FactDate(TI, 0.085f);
            P(1, $"Акт скрытых работ: сваи и фундаментная плита · {tw}", "армирование и бетон плиты перед засыпкой", "технический надзор", fnd + 7f * D, fnd < R - 5f * D ? fnd + 4f * D : -1f);
            float tp = FactP(TI, R);
            if (tp > 0.1f && tp < 0.999f)
            {
                int wf = WorkFloor(tp), f1 = Mathf.Max(wf - 1, 1), f2 = Mathf.Max(wf - 2, 1);
                P(1, $"Акт скрытых работ: армирование плиты {f2 + 1}‑го этажа · {tw}", "подписан до бетонирования", "технический надзор", R - 16f * D, R - 18f * D);
                P(1, $"Акт скрытых работ: армирование плиты {f1 + 1}‑го этажа · {tw}", "плита забетонирована, акт не подписан", "Генподрядчик · технический надзор", R - 4f * D, -1f);
            }
            if (anFloor >= 0) P(1, $"Исполнительная геодезическая схема плиты {anFloor + 1}‑го этажа", "отклонение +14 мм в точке 4 — повторная съёмка после шлифовки", "Генподрядчик · геодезист", R + 9f * D, -1f);
            for (int i = 0; i < L.Parts.Count; i++)
            {
                if (i == TI) continue; var p = Pt(i); float fp = FactP(i, R);
                if (p.Land || fp <= 0.12f) continue;
                float fd = FactDate(i, 0.1f);
                P(1, $"Акт скрытых работ: фундаменты · {p.Short}", "ростверки и гидроизоляция перед обратной засыпкой", "технический надзор", fd + 7f * D, fd + 5f * D < R ? fd + 5f * D : -1f);
                if (fp >= 0.999f) P(2, $"Акт приёмки в эксплуатацию · {p.Short}", "объект принят приёмочной комиссией", "Заказчик · приёмочная комиссия", FactDate(i, 1f) + 10f * D, FactDate(i, 1f) + 8f * D);
            }
            P(1, "Акт ответственных конструкций: каркас верхних этажей", "освидетельствование до монтажа фасада", "технический надзор · авторский надзор", R + 12f * D, -1f);
            P(1, "Корректировка проекта: изменения фасадных узлов", "повторное заключение экспертизы по изменённым разделам", "Генпроектировщик · государственная экспертиза", R - 9f * D, -1f);
            if (NetOver > 0f) P(1, "Дополнительное соглашение о цене (п. 5.5 договора)", $"перерасход сверх резерва {Mln(NetOver)}", "Заказчик · Генподрядчик", R + 30f * D, -1f);
            // the hand-over of the complex
            P(2, "Технические условия: постоянное подключение электроснабжения", "перевод с временной схемы до пусконаладки", "сетевая организация", F - 0.45f, -1f);
            P(2, "Заключения технического и авторского надзора о качестве", "основание для декларации о соответствии", "технический надзор · авторский надзор", F - 20f * D, -1f);
            P(2, "Декларация о соответствии и акт приёмки объекта в эксплуатацию", "подписывает приёмочная комиссия заказчика", "Заказчик · приёмочная комиссия", F, -1f);
            P(2, "Технический паспорт и регистрация права собственности", "после акта приёмки", "Заказчик", F + 30f * D, -1f);
        }

        VisualElement ctlDocsV, ctlChgV, chgFeed, chgMsg; int chgMode; bool msgMail;
        readonly List<Button> chgModeBtns = new List<Button>(), msgBtns = new List<Button>();
        /// <summary>Контроль → Документы: the permits and acts with their statuses at the survey date, by stage.</summary>
        void BuildCtlDocs(VisualElement v)
        {
            v = Scroll(v, "ctl-vscroll");
            float d = Report; int n0 = 0, n1 = 0, n2 = 0; foreach (var p in permits) { int s = PermitState(p, d); if (s == 0) n0++; else if (s == 1) n1++; else n2++; }
            var vb = Box(v, "an-verdict " + (n2 > 0 ? "s-warn" : "s-ok"));
            Txt(vb, $"Документы на {Day(d)}", "an-verdict-k");
            Txt(vb, n2 > 0 ? $"Получено {n0} из {permits.Count}, ждём {n1}, просрочено {n2} — без них следующий этап или приёмку не подписать." : $"Получено {n0} из {permits.Count}, ждём {n1}, просроченных нет.", "an-verdict-t");
            var kr = Box(v, "ctl-minik", false);
            MiniK(kr, "Есть", n0.ToString(), "получены и подписаны", "ok");
            MiniK(kr, "Ждём", n1.ToString(), "срок ещё не наступил", "");
            MiniK(kr, "Просрочено", n2.ToString(), "срок прошёл, документа нет", n2 > 0 ? "bad" : "");
            var c = Box(v, "mon-card an-card w7-docs");
            var h = Box(c, "an-sec", false); h.Add(TwinUI.Icon("files", 16)); Txt(h, "Разрешения и акты", "mon-title");
            Txt(c, "что нужно по порядку строительства в РК · статус, дата и кто отвечает", "mon-src");
            var th = Box(c, "w7-dr w7-dh", false);
            Txt(th, "Документ", "w7-dc n"); Txt(th, "Ответственный", "w7-dc w"); Txt(th, "Дата", "w7-dc t"); Txt(th, "Статус", "w7-dc s");
            for (int st = 0; st < PermitStage.Length; st++)
            {
                Txt(c, PermitStage[st], "w7-dgroup");
                foreach (var p in permits)
                {
                    if (p.Stage != st) continue; int s = PermitState(p, d);
                    var r = Box(c, "w7-dr " + PermitCls[s], false);
                    var nm = Box(r, "w7-dc n", false); Txt(nm, p.Name, "w7-dn"); Txt(nm, p.Note, "mon-src");
                    Txt(r, p.Who, "w7-dc w");
                    int late = Mathf.RoundToInt((d - p.Due) * 365f), left = -late;
                    Txt(r, s == 0 ? $"получен {Day(p.Got)}" : s == 2 ? $"срок {Day(p.Due)} · просрочен на {late} дн." : left <= 60 ? $"срок {Day(p.Due)} · через {left} дн." : $"срок {IconicFloors.MonthYear(p.Due)}", "w7-dc t");
                    var sc = Box(r, "w7-dc s", false); Txt(sc, PermitWord[s], "an-tag " + (s == 0 ? "s-ok" : s == 1 ? "s-info" : "s-bad"));
                }
            }
            c.Add(SourceTags.Line(SrcDocs));
        }

        // ================================================================== what changed
        /// <summary>A topic of the digest: its icon, heading and class; Lines — whole sentences, each its own label (Name — the line is
        /// the name of a document, shown indented under the sentence before it).</summary>
        class Dg { public string Icon, Head, Cls; public readonly List<(string T, bool Name)> Lines = new List<(string, bool)>(); }
        /// <summary>The period of the digest: the week up to the survey, or from the survey before the one chosen on «Съёмки» to it.</summary>
        void ChgPeriod(out float d0, out float d1)
        {
            if (chgMode == 0) { d1 = Report; d0 = Report - 7f / 365f; return; }
            int a = Mathf.Clamp(svA, 0, surveys.Count - 1); d1 = surveys[a]; d0 = a > 0 ? surveys[a - 1] : d1 - 0.33f;
        }
        /// <summary>What changed in the model of the twin from d0 to d1: dates, works by type, money, defects, documents, people and weather.</summary>
        List<Dg> Digest(float d0, float d1)
        {
            var list = new List<Dg>();
            Dg Add(string icon, string head, string cls) { var g = new Dg { Icon = icon, Head = head, Cls = cls }; list.Add(g); return g; }
            int sd1 = SchedDelay(d1), sd0 = SchedDelay(d0); float ce1 = ComplexEndAt(Mathf.Min(d1, Report)), ce0 = ComplexEndAt(Mathf.Min(d0, Report));
            int dce = Mathf.RoundToInt((ce1 - ce0) * 365f); string cm = IconicFloors.MonthYear(ce1);
            var g1 = Add("calendar", "Сроки", sd1 > sd0 ? "bad" : sd1 > 3 ? "warn" : "ok");
            g1.Lines.Add((string.Format("Отставание от графика — {0} дн.", sd1), false));
            g1.Lines.Add((sd1 > sd0 ? string.Format("За период отставание выросло на {0} дн.", sd1 - sd0) : sd1 < sd0 ? string.Format("За период отставание сократилось на {0} дн.", sd0 - sd1) : "За период отставание не изменилось.", false));
            g1.Lines.Add((dce > 3 ? string.Format("Прогноз ввода комплекса — {0}, на {1} дн. позже.", cm, dce) : dce < -3 ? string.Format("Прогноз ввода комплекса — {0}, на {1} дн. раньше.", cm, -dce) : string.Format("Прогноз ввода комплекса — {0}, без изменений.", cm), false));
            var g2 = Add("list_checks", "Работы", "ok");
            for (int t = 0; t < WtName.Length; t++)
            {
                if (!TypeReady(t, -1, d1, out float p1, out float f1, out _)) continue; TypeReady(t, -1, d0, out _, out float f0, out _);
                float g = (f1 - f0) * 100f; if (g < 0.05f) continue;
                g2.Lines.Add((string.Format("{0}: +{1} п.п. за период, готово {2}, план {3}", WtName[t], Loc.N1(g), Pct(f1), Pct(p1)), false));
            }
            if (g2.Lines.Count == 0) { g2.Lines.Add(("Работы на площадке не велись.", false)); g2.Cls = "muted"; }
            float ev = Spent(d1, true) - Spent(d0, true), pv = Spent(d1, false) - Spent(d0, false), ac = AcAt(d1) - AcAt(d0);
            var g3 = Add("coins", "Деньги", ev < pv * 0.95f || ac > ev * 1.05f ? "warn" : "ok");
            g3.Lines.Add((string.Format("Выполнено работ на {0} в ценах сметы при плане {1}.", Mln(ev), Mln(pv)), false));
            g3.Lines.Add((string.Format("Затраты за период — {0}.", Mln(ac)), false));
            g3.Lines.Add((string.Format("Всего потрачено {0} из {1}.", Mln(AcAt(d1)), Mln(evBac)), false));
            int nw = 0, cl = 0, op = 0, cr = 0;
            foreach (var f in defects) { if (f.Found > d0 && f.Found <= d1) nw++; if (f.Closed > d0 && f.Closed <= d1) cl++; if (DefOpen(f, d1)) { op++; if (f.Sev >= 2) cr++; } }
            var g4 = Add("triangle_alert", "Дефекты", cr > 0 ? "bad" : nw > cl ? "warn" : "ok");
            g4.Lines.Add((string.Format("Новых дефектов за период — {0}, устранено — {1}.", nw, cl), false));
            g4.Lines.Add((cr > 0 ? string.Format("Открыто дефектов — {0}, критических среди них — {1}.", op, cr) : string.Format("Открыто дефектов — {0}, критических нет.", op), false));
            var got = new List<string>(); var late = new List<string>();
            foreach (var p in permits)
            {
                if (p.Got > d0 && p.Got <= d1) got.Add(p.Name);
                else if (p.Due > d0 && p.Due <= d1 && !(p.Got >= 0f && p.Got <= d1)) late.Add(p.Name);
            }
            var g5 = Add("files", "Документы", late.Count > 0 ? "bad" : got.Count > 0 ? "ok" : "muted");
            if (got.Count == 0 && late.Count == 0) g5.Lines.Add(("Новых документов и просрочек нет.", false));
            if (got.Count > 0) { g5.Lines.Add((string.Format("Получено документов — {0}:", got.Count), false)); foreach (var n in got) g5.Lines.Add((n, true)); }
            if (late.Count > 0) { g5.Lines.Add((string.Format("Просрочено документов — {0}:", late.Count), false)); foreach (var n in late) g5.Lines.Add((n, true)); }
            int days = Mathf.Clamp(Mathf.RoundToInt((d1 - d0) * 365f), 1, 150), ppl = 0, wd = 0, stops = 0, plan = 0;
            for (int k = 0; k < days; k++)
            {
                float t = d1 - k / 365f; DayCrew(t, out int p, out int pl, out _, out bool w); if (w) stops++;
                if (DayDT(t).DayOfWeek == DayOfWeek.Sunday) continue; ppl += p; plan += pl; wd++;
            }
            if (wd > 0) { ppl /= wd; plan /= wd; }
            var g6 = Add("hard_hat", "Люди и погода", ppl < plan * 0.9f ? "warn" : "ok");
            g6.Lines.Add((string.Format("В среднем {0} чел. в рабочий день при графике {1}.", Loc.N0(ppl), Loc.N0(plan)), false));
            g6.Lines.Add((string.Format("Дней с погодным простоем — {0}.", stops), false));
            return list;
        }
        /// <summary>Контроль → Что изменилось: the feed of the period and the same digest as the message a subscriber would get.</summary>
        void BuildCtlChanges(VisualElement v)
        {
            chgModeBtns.Clear(); msgBtns.Clear();
            v = Scroll(v, "ctl-vscroll");
            var row = Box(v, "an-row");
            var lc = Box(row, "an-colL ctl-col");
            var c = Box(lc, "mon-card an-card");
            var h = Box(c, "an-sec", false); h.Add(TwinUI.Icon("activity", 16)); Txt(h, "Что изменилось", "mon-title"); Spacer(h);
            var seg = Box(h, "mon-seg");
            foreach (var (t, m) in new[] { ("За неделю", 0), ("С прошлой съёмки", 1) })
            { int mm = m; var b = Widgets.Btn(t, () => { chgMode = mm; FillChanges(); }, "small"); seg.Add(b); chgModeBtns.Add(b); }
            chgFeed = Box(c, "w7-feed");
            c.Add(SourceTags.Line(SrcDigest, SrcMon, SrcDefects, SrcDocs));
            var rc = Box(row, "an-colR ctl-col");
            var mc = Box(rc, "mon-card an-card");
            var mh = Box(mc, "an-sec", false); mh.Add(TwinUI.Icon("bell", 16)); Txt(mh, "Так придёт уведомление", "mon-title"); Spacer(mh);
            var ms = Box(mh, "mon-seg");
            foreach (var (t, m) in new[] { ("Telegram", false), ("Почта", true) })
            { bool mm = m; var b = Widgets.Btn(t, () => { msgMail = mm; FillChanges(); }, "small"); ms.Add(b); msgBtns.Add(b); }
            Txt(mc, "демонстрация: двойник не подключён к Telegram и почте, ничего не отправляется", "mon-src");
            chgMsg = Box(mc, "w7-msgbox");
            FillChanges();
        }
        void FillChanges()
        {
            if (chgFeed == null) return;
            for (int i = 0; i < chgModeBtns.Count; i++) chgModeBtns[i].EnableInClassList("active", i == chgMode);
            for (int i = 0; i < msgBtns.Count; i++) msgBtns[i].EnableInClassList("active", (i == 1) == msgMail);
            ChgPeriod(out float d0, out float d1);
            var dg = Digest(d0, d1);
            chgFeed.Clear();
            Txt(chgFeed, string.Format(d1 > Report + 0.002f ? "{0} → {1} · прогноз после съёмки" : chgMode == 1 ? "{0} → {1} · съёмка, выбранная в разделе «Съёмки», и предыдущая" : "{0} → {1} · неделя до съёмки", Day(d0), Day(d1)), "mon-src w7-feed-when");
            foreach (var g in dg)
            {
                var r = Box(chgFeed, "w7-fi", false);
                var ic = Box(r, "w7-fi-ic " + g.Cls, false); ic.Add(TwinUI.Icon(g.Icon, 14));
                var tx = Box(r, "w7-fi-tx", false); Txt(tx, g.Head, "w7-fi-h");
                foreach (var (t, nm) in g.Lines) Txt(tx, t, nm ? "w7-fi-t w7-fi-n" : "w7-fi-t");
            }
            // the same digest as a message
            chgMsg.Clear();
            var bub = Box(chgMsg, msgMail ? "w7-mail" : "w7-tg", false);
            if (msgMail)
            {
                Txt(bub, "От: QTwin · мониторинг строительства", "w7-msg-meta");
                Txt(bub, string.Format("Тема: что изменилось {0} – {1}", Day(d0), Day(d1)), "w7-msg-subj");
                Txt(bub, L.Short, "w7-msg-subj");
                Box(bub, "w7-msg-rule", false);
            }
            else
            {
                var hb = Box(bub, "w7-tg-head", false); Txt(hb, "QT", "w7-tg-av"); var hn = Box(hb, "w7-tg-hn", false); Txt(hn, "QTwin Monitor", "w7-tg-name"); Txt(hn, "бот · демо", "w7-msg-meta");
                Txt(bub, L.Short, "w7-msg-subj");
                Txt(bub, string.Format("{0} – {1}", Day(d0), Day(d1)), "w7-msg-meta");
            }
            foreach (var g in dg)
            {
                Txt(bub, g.Head, "w7-msg-h");
                foreach (var (t, nm) in g.Lines) Txt(bub, t, nm ? "w7-msg-t w7-msg-l w7-msg-n" : "w7-msg-t w7-msg-l");
            }
            var acts = topActs ?? Actions(Report);
            if (acts.Count > 0)
            {
                Txt(bub, "Что делать", "w7-msg-h");
                Txt(bub, acts[0].Title, "w7-msg-t w7-msg-l w7-msg-act");
                Txt(bub, acts[0].Effect, "w7-msg-t w7-msg-l");
            }
            Txt(bub, msgMail ? "Полный недельный отчёт — во вложении PDF." : "Открыть мониторинг · Недельный отчёт PDF", msgMail ? "w7-msg-meta" : "w7-tg-btn");
            if (!msgMail) Txt(bub, "09:00", "w7-tg-time");
        }
    }
}
