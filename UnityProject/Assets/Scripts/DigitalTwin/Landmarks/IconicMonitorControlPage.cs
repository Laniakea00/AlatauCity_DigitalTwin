using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using DSrc = AlatauCity.DigitalTwin.Data.Sources;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The «Контроль» page of the construction monitoring — the investor's view: is the money on track, when is the building
    /// handed over, what should be done now. Three views: Сводка (readiness by work type, dates and the trend of the delay, the earned value
    /// with SPI / CPI / EAC, the three actions), Недельный отчёт (one sheet of paper for a chosen week), Люди и погода (people and machines
    /// by day, the weather of Almaty and the downtime it causes). The «Дефекты» page pins the defects on the live model.</summary>
    public partial class IconicMonitor
    {
        const int TCtl = 6, TDef = 7;
        VisualElement ctlPage, ctlSumV, ctlRepV, ctlResV, ctlWtRows, ctlEvChart, ctlCrewChart, ctlRepPaper;
        ScrollView ctlRepScroll;
        readonly List<Button> ctlTabs = new List<Button>(), ctlPartBtns = new List<Button>(), ctlWeekBtns = new List<Button>();
        int ctlView, ctlPart = -1, ctlWeek;
        static readonly Color AcC = new Color(0.98f, 0.42f, 0.36f), ColdC = new Color(0.48f, 0.65f, 1f), WindC = new Color(0.66f, 0.55f, 0.98f), WetC = new Color(0.30f, 0.78f, 0.80f);

        // ================================================================== the page
        void BuildControl()
        {
            ctlTabs.Clear(); ctlPartBtns.Clear(); ctlWeekBtns.Clear();
            ctlPage = Box(body, "an-page ctl-page");
            var head = Box(ctlPage, "an-head");
            head.Add(TwinUI.Icon("trending_up", 20));
            var tb = Box(head, "an-titles", false);
            Txt(tb, $"Контроль · {L.Short}", "an-h1");
            Txt(tb, $"по съёмке {Day(Report)}", "w17-sub");
            var seg = Box(head, "mon-seg"); seg.style.marginLeft = 22;
            foreach (var (txt, k) in new[] { ("Сводка", 0), ("Что изменилось", 3), ("Недельный отчёт", 1), ($"Документы · {docs.Count + permits.Count}", 4), ("Люди и погода", 2) })
            { int kk = k; var b = Widgets.Btn(txt, () => CtlView(kk), "small"); b.AddToClassList("an-tab"); b.userData = k; seg.Add(b); ctlTabs.Add(b); }
            Spacer(head);
            head.Add(SourceTags.Line(SrcMon, SrcEv));

            ctlSumV = Box(ctlPage, "an-view"); BuildCtlSummary(ctlSumV);
            ctlRepV = Box(ctlPage, "an-view"); BuildCtlReport(ctlRepV);
            ctlResV = Box(ctlPage, "an-view"); BuildCtlRes(ctlResV);
            ctlChgV = Box(ctlPage, "an-view"); BuildCtlChanges(ctlChgV);
            ctlDocsV = Box(ctlPage, "an-view"); BuildCtlDocs(ctlDocsV);
            CtlView(0, false);
        }
        void CtlView(int v, bool go = true)
        {
            if (go && tab != TCtl && overlay != null) SetTab(TCtl);
            ctlView = v; CloseDoc();
            for (int i = 0; i < ctlTabs.Count; i++) ctlTabs[i].EnableInClassList("active", (int)ctlTabs[i].userData == v);
            Vis(ctlSumV, v == 0); Vis(ctlRepV, v == 1); Vis(ctlResV, v == 2); Vis(ctlChgV, v == 3); Vis(ctlDocsV, v == 4);
            if (v == 1) FillReport();
            if (v == 3) FillChanges();
        }

        // ------------------------------------------------------------------ Сводка
        /// <summary>The only summary of the monitoring, read in three seconds: four numbers (readiness, delay, hand-over, forecast cost),
        /// then the time (readiness by work type, the hand-overs) on the left and what to do, what needs attention and the money on the
        /// right. Every explanation is folded under «Почему так» / «Как считается».</summary>
        void BuildCtlSummary(VisualElement v)
        {
            v = Scroll(v, "ctl-vscroll");                    // the whole view scrolls: nothing is cut at the window's bottom
            float d = Report, rf = Ready(d, true), rp = Ready(d, false);
            int sd = SchedDelay(d), last = LastPart(d);
            float fe = FactDate(last, 1f); int ld = Mathf.RoundToInt((fe - L.Finish) * 365f);
            TrendText(out string tcls);
            float over = evEac - evBac;
            string pm = IconicFloors.MonthYear(L.Finish);

            // ---- the answer: four numbers
            var kr = Box(v, "w17-kpis", false);
            HeroK(kr, "Готовность", Pct(rf), string.Format("по плану {0}", Pct(rp)), rf < rp - 0.01f ? "warn" : "ok", () => SetTab(T4D));
            HeroK(kr, "Отставание", sd > 3 ? $"{sd} дн." : "нет", TrendShort(), sd > 21 && ld > 3 ? "bad" : sd > 3 ? "warn" : "ok", () => SetTab(T4D));       // red only when the delay moves the hand-over
            HeroK(kr, "Ввод комплекса", IconicFloors.MonthYear(fe), ld > 3 ? string.Format("позже плана на {0} дн.", ld) : "в срок по плану", ld > 21 ? "bad" : ld > 3 ? "warn" : "ok", () => SetTab(TInv));
            HeroK(kr, "Прогноз стоимости", Mln(evEac), over > 0f ? string.Format("бюджет {0} · {1}", Mln(evBac), SPc(over / evBac)) : string.Format("бюджет {0}", Mln(evBac)), CostCls, () => AnView(1));

            var row = Box(v, "an-row w17-row");
            // ================= left: time
            var lc = Box(row, "an-colL ctl-col");
            var wc = Box(lc, "w17-card");
            CardHead(wc, "list_checks", "Готовность по видам работ");
            var ps = Box(wc, "mon-seg ctl-parts");
            for (int i = -1; i < L.Parts.Count; i++)
            { int k = i; var b = Widgets.Btn(i < 0 ? "Весь комплекс" : Pt(i).Short, () => { ctlPart = k; FillWt(); }, "small"); ps.Add(b); ctlPartBtns.Add(b); }
            var wl = Box(wc, "w17-legend", false); wl.Add(Widgets.LegendItem(Blue, "сделано")); wl.Add(Widgets.LegendItem(Color.white, "где должны быть по графику"));
            ctlWtRows = Box(wc, "ctl-wt-list");
            ctlPart = obj; FillWt();
            wc.Add(SourceTags.Line(SrcMon));

            var dc = Box(lc, "w17-card");
            CardHead(dc, "calendar", "Сроки ввода");
            var th = Box(dc, "ctl-tr ctl-th", false);
            foreach (var (c, cls) in new[] { ("Объект", "n"), ("План", "m"), ("Прогноз", "m"), ("Отставание", "m") }) Txt(th, c, "ctl-td " + cls);
            for (int i = 0; i < L.Parts.Count; i++)
            {
                var o = Obj(i, d); int k = i;
                var r = new Button(() => { SetTab(T4D); SelectObj(k, true); }) { focusable = false }; r.AddToClassList("ctl-tr"); dc.Add(r);
                Txt(r, Pt(i).Name, "ctl-td n");
                Txt(r, IconicFloors.MonthYear(o.PlanEnd), "ctl-td m");
                var fcl = Txt(r, IconicFloors.MonthYear(o.FactEnd), "ctl-td m"); if (o.EndDays > 3) fcl.AddToClassList(o.EndDays > 21 ? "bad" : "warn");
                var dl = Txt(r, o.Fact >= 0.999f ? "введён" : o.Plan <= 0f && o.Fact <= 0f ? "не начат" : o.Days > 3 ? $"{o.Days} дн." : "в графике", "ctl-td m"); dl.AddToClassList(o.Cls == "muted" ? "muted" : o.Cls);
            }
            var why = Widgets.Details(dc, "Почему так");
            if (sd > 3 && ld <= 3) Txt(why, WhyOnTime(d, sd, last), "w17-note");
            Txt(why, "Отставание по съёмкам:", "w17-note");
            var bars = Box(why, "ctl-trend", false); int mx = 10; foreach (int x in trendD) mx = Mathf.Max(mx, x);
            for (int k = 0; k < trendD.Count; k++)
            {
                var col = Box(bars, "ctl-tcol", false);
                Txt(col, $"{trendD[k]} дн.", "ctl-tv");
                var well = Box(col, "ctl-twell", false);
                var b = Box(well, "ctl-tbar", false); b.style.height = Length.Percent(Mathf.Clamp01(Mathf.Max(trendD[k], 0) / (float)mx) * 100f);
                b.style.backgroundColor = k == trendD.Count - 1 ? ClsColor(tcls == "bad" ? "warn" : tcls) : new Color(1f, 1f, 1f, 0.22f);
                if (k == trendD.Count - 1) col.AddToClassList("cur");
                Txt(col, Day(trendT[k]), "ctl-td-d");
            }
            Txt(why, "Отставание считается по объёму: на какую дату график планировал столько работ, сколько сделано сейчас. Крупные корпуса весят больше, чем газон. Сдвиг ввода — прогноз модели по фактическому темпу.", "w17-note");
            dc.Add(SourceTags.Line(SrcMon));

            // ================= right: what to do, what needs attention, the money
            var rc = Box(row, "an-colR ctl-col");
            var ac = Box(rc, "w17-card");
            CardHead(ac, "sparkles", "Что делать сейчас");
            var acts = Actions(d); int n = 1;
            foreach (var a in acts) ActRow(ac, a, n++);
            if (acts.Count > 0)
            {
                var aw = Widgets.Details(ac, "Почему эти действия");
                n = 1; foreach (var a in acts) Txt(aw, string.Format("{0}. {1}", n++, a.Why), "w17-note");
                Txt(aw, "Действия подбираются правилами по данным двойника: сначала — с наибольшим эффектом на срок ввода. Эффект — оценка модели.", "w17-note");
            }
            ac.Add(SourceTags.Line(SrcActs));

            BuildAttention(rc);

            var ec = Box(rc, "w17-card");
            CardHead(ec, "chart_line", "Деньги");
            var ea = Txt(ec, CpiWords(evCpi), "w17-answer"); ea.AddToClassList(evCpi < 0.9f ? "bad" : evCpi < 0.99f ? "warn" : "ok");
            var lg = Box(ec, "w17-legend", false);
            lg.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.6f), "план")); lg.Add(Widgets.LegendItem(Blue, "сделано")); lg.Add(Widgets.LegendItem(AcC, "затраты"));
            lg.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.3f), "бюджет"));
            ctlEvChart = Box(ec, "ctl-chart ctl-ev w17-ev"); ctlEvChart.generateVisualContent += DrawEv;
            for (int y = (int)T0; y <= (int)T1; y++)
            { var a = new Label(y.ToString()) { pickingMode = PickingMode.Ignore }; a.AddToClassList("mon-tick"); a.style.left = Length.Percent((y - T0) / (T1 - T0) * 100f); ctlEvChart.Add(a); }
            var ym = Txt(ctlEvChart, Mln(Mathf.Max(evEac, evBac + anRes) * 1.06f), "ctl-ymax"); ym.style.position = Position.Absolute;
            var how = Widgets.Details(ec, "Как считается");
            float pvR = Spent(d, false);
            void Line(string k, string val, string words, string cls)
            {
                var r = Box(how, "w17-xrow", false);
                var t = Box(r, "w17-xrow-tx", false); Txt(t, k, "w17-xrow-k"); Txt(t, words, "w17-note");
                var vv = Txt(r, val, "w17-xrow-v"); if (cls.Length > 0) vv.AddToClassList(cls);
            }
            Line("Темп работ · SPI", Ix(evSpi), $"{SpiWords(evSpi)}: сделано работ на {Mln(anTot.Ev)} в ценах сметы, по графику к этой дате — на {Mln(pvR)}. SPI = сделано ÷ план.", evSpi < 0.95f ? "bad" : evSpi < 0.99f ? "warn" : "ok");
            Line("Цена работ · CPI", Ix(evCpi), $"{CpiWords(evCpi)}: за работы на {Mln(anTot.Ev)} по смете заплачено {Mln(evAcR)} — цены выросли с октября 2026. CPI = сделано ÷ затраты.", evCpi < 0.95f ? "bad" : evCpi < 0.99f ? "warn" : "ok");
            Line("Прогноз стоимости · EAC", Mln(evEac), $"Потрачено {Mln(evAcR)} + остаток работ по ценам на {Day(d)} + сроки дольше графика. Бюджет {Mln(evBac)}, резерв {Mln(anRes)} — " +
                (NetOver > 0f ? $"не хватает {Mln(NetOver)}." : over > 0f ? "перерасход покрывается резервом." : "укладываемся в бюджет."), CostCls);
            Txt(how, "На графике: пунктир после оранжевой линии съёмки — прогноз; ромб — прогноз ввода комплекса.", "w17-note");
            var all = Widgets.Btn("Открыть смету", () => AnView(1), "small"); all.AddToClassList("w17-go"); ec.Add(all);
            ec.Add(SourceTags.Line(SrcEv, DSrc.OlxPrices, DSrc.NbrkRate));
        }
        /// <summary>The delay against the previous survey, in a few words.</summary>
        string TrendShort()
        {
            if (trendD.Count < 2) return "первая съёмка";
            int dd = trendD[trendD.Count - 1] - trendD[trendD.Count - 2];
            return dd > 3 ? string.Format("+{0} дн. к прошлой съёмке", dd) : dd < -3 ? string.Format("−{0} дн. к прошлой съёмке", -dd) : "как на прошлой съёмке";
        }
        /// <summary>A number of the answer row: a small label, the big value (its unit small), one muted line; status = the colour of the
        /// value and a thin bar on the left.</summary>
        void HeroK(VisualElement parent, string cap, string val, string sub, string cls, Action click)
        {
            var b = new Button(click) { focusable = false }; b.AddToClassList("w17-k"); if (cls.Length > 0) b.AddToClassList("s-" + cls); parent.Add(b);
            Txt(b, cap, "w17-k-cap");
            var vr = Box(b, "w17-k-vr", false);
            SplitUnit(val, out var num, out var unit);
            var nv = Txt(vr, num, "w17-k-v"); if (cls.Length > 0) nv.AddToClassList(cls);
            if (unit.Length > 0) Txt(vr, unit, "w17-k-u");
            Txt(b, sub, "w17-k-sub");
        }
        /// <summary>«39 дн.» → «39» + «дн.», «$881 млн» → «$881» + «млн», «58 %» → «58» + «%»; a date («сен 2030») stays whole.</summary>
        static void SplitUnit(string s, out string num, out string unit)
        {
            int i = s.LastIndexOfAny(new[] { ' ', ' ' });
            if (i > 0 && i < s.Length - 1 && !char.IsDigit(s[i + 1]) && char.IsDigit(s[i - 1])) { num = s.Substring(0, i); unit = s.Substring(i + 1); }
            else { num = s; unit = ""; }
        }
        static void CardHead(VisualElement card, string icon, string title)
        {
            var h = Box(card, "w17-head", false); var ic = TwinUI.Icon(icon, 15); ic.AddToClassList("w17-head-ic"); h.Add(ic); Txt(h, title, "w17-title");
        }
        /// <summary>«Требует внимания»: the findings of the analytics, most serious first (four shown, the rest behind «Ещё N»); each
        /// with the places in the documents it follows from (a click opens the document there) and a way to see it.</summary>
        void BuildAttention(VisualElement parent)
        {
            var c = Box(parent, "w17-card");
            var h = Box(c, "w17-head", false); var ic = TwinUI.Icon("triangle_alert", 15); ic.AddToClassList("w17-head-ic"); h.Add(ic); Txt(h, "Требует внимания", "w17-title"); Spacer(h);
            int nb = 0, nw = 0; foreach (var f in finds) { if (f.Icon == "clock") continue; if (f.Sev >= 2) nb++; else if (f.Sev == 1) nw++; }
            if (nb > 0) Txt(h, string.Format("{0} критично", nb), "w17-count bad");
            if (nw > 0) Txt(h, string.Format("{0} важно", nw), "w17-count warn");
            // the delays of the buildings are in «Сроки ввода» already: not repeated here
            var list = new List<Finding>(); foreach (var f in finds) if (f.Sev >= 0 && f.Icon != "clock") list.Add(f);
            VisualElement more = null; int shown = 0;
            foreach (var f in list)
            {
                if (shown == 3) { more = Box(c, "w17-more-box"); more.style.display = DisplayStyle.None; }
                AttnRow(more ?? c, f); shown++;
            }
            if (more != null)
            {
                var mb = more; int extra = list.Count - 3;
                Button btn = null; btn = Widgets.Btn(string.Format("Ещё {0} ›", extra), () => { bool on = mb.style.display == DisplayStyle.None; mb.style.display = on ? DisplayStyle.Flex : DisplayStyle.None; btn.text = on ? "Свернуть" : string.Format("Ещё {0} ›", extra); }, "small", "ghost");
                btn.AddToClassList("w17-go"); c.Add(btn);
            }
            if (list.Count == 0) Txt(c, "Всё идёт по плану.", "w17-answer ok");
            c.Add(SourceTags.Line(SrcMon));
        }
        void AttnRow(VisualElement parent, Finding f)
        {
            // one line: what, and where to see it; why (the text and the places in the documents — a click opens the sheet there) folded
            var r = Box(parent, "w17-at " + SevCls[Mathf.Clamp(f.Sev + 1, 0, 3)]);
            var top = Box(r, "w17-at-top", false);
            Txt(top, f.Title, "w17-at-t");
            if (f.Show != null)
            {
                var g = new Button(f.Show) { focusable = false }; g.AddToClassList("an-go"); g.AddToClassList("w17-at-go");
                g.Add(new Label(f.ShowText) { pickingMode = PickingMode.Ignore }); g.Add(TwinUI.Icon("arrow_right", 12)); top.Add(g);
                top.pickingMode = PickingMode.Position;
            }
            var dt = Widgets.Details(r, "Почему так");
            if (!string.IsNullOrEmpty(f.Text)) Txt(dt, f.Text, "w17-note");
            if (f.Src.Count > 0) { var sr = Box(dt, "w17-at-src"); foreach (var s in f.Src) sr.Add(DocChip(s, f)); }
        }
        /// <summary>An action: its number, what to do, the effect on the hand-over, where to see it (the reason is folded below the list).</summary>
        void ActRow(VisualElement parent, Act a, int n)
        {
            var c = Box(parent, "w17-act " + SevCls[Mathf.Clamp(a.Sev + 1, 0, 3)]);
            Txt(c, n.ToString(), "ctl-actn");
            var tx = Box(c, "w17-act-tx", false);
            Txt(tx, a.Title, "w17-act-t");
            var ef = Txt(tx, a.Effect, "w17-act-e"); ef.AddToClassList(a.Days > 0 ? "ok" : "muted");
            if (a.Show != null)
            {
                var g = new Button(a.Show) { focusable = false }; g.AddToClassList("an-go");
                g.Add(new Label(a.ShowText) { pickingMode = PickingMode.Ignore }); g.Add(TwinUI.Icon("arrow_right", 12)); c.Add(g);
            }
        }
        /// <summary>Why the complex is handed over in time although it is behind now: the buildings behind work a second shift from the
        /// survey on (the model closes their gap before their hand-over), or they have room before the hand-over of the complex.</summary>
        string WhyOnTime(float d, int sd, int last)
        {
            var rec = new List<string>(); var slack = new List<string>();
            for (int i = 0; i < L.Parts.Count; i++)
            {
                var o = Obj(i, d); if (!(o.Fact > 0f && o.Fact < 0.999f && o.Days > 3)) continue;
                if (o.EndDays <= 3 && Pt(i).Recover) rec.Add($"{Pt(i).Short} ({o.Days} дн.)"); else if (o.FactEnd <= L.Finish + 0.01f) slack.Add($"{Pt(i).Short} ({o.Days} дн.)");
            }
            var t = new List<string>();
            if (rec.Count > 0) t.Add($"на отстающих корпусах {string.Join(", ", rec)} после съёмки работает вторая смена, и по прогнозу модели отставание закрывается до их ввода");
            if (slack.Count > 0) t.Add($"у {string.Join(", ", slack)} до ввода комплекса есть запас по графику");
            if (t.Count == 0) t.Add("отстают работы, от которых срок ввода не зависит");
            return $"Почему в срок при отставании {sd} дн.: {string.Join("; ", t)}. Последним вводится {Pt(last).Name} — {IconicFloors.MonthYear(FactDate(last, 1f))}.";
        }
        /// <summary>The rows of readiness by work type for the building chosen (the whole complex by default).</summary>
        void FillWt()
        {
            if (ctlWtRows == null) return;
            for (int i = 0; i < ctlPartBtns.Count; i++) ctlPartBtns[i].EnableInClassList("active", i - 1 == ctlPart);
            ctlWtRows.Clear();
            for (int t = 0; t < WtName.Length; t++)
            {
                if (!TypeReady(t, ctlPart, Report, out float p, out float f, out int lag)) continue;
                float dpp = (f - p) * 100f;
                string cls = p <= 0f && f <= 0f ? "muted" : f >= 0.999f ? "ok" : dpp < -5f || lag > 21 ? "bad" : dpp < -1f || lag > 3 ? "warn" : "ok";
                // one line: the name, the percent done, the lag; the bar under it (blue: done, white tick: the plan)
                var r = Box(ctlWtRows, "w17-wt", false);
                var top = Box(r, "w17-wt-top", false);
                Txt(top, WtName[t], "w17-wt-n");
                Txt(top, Pct(f), "w17-wt-p");
                var dv = Txt(top, p <= 0f && f <= 0f ? "не начато" : f >= 0.999f ? "готово" : lag > 3 ? $"−{lag}\u00A0дн." : "в графике", "w17-wt-d"); dv.AddToClassList(cls);
                var bar = Box(r, "mon-bar ctl-wt-bar", false);
                var fl = Box(bar, "mon-fill", false); fl.style.width = Length.Percent(f * 100f);
                var mk = Box(bar, "mon-mark", false); mk.style.left = Length.Percent(p * 100f);
            }
        }
        /// <summary>The earned-value curves: PV dashed white, EV blue (pale dashed after the survey), AC red (dashed after the survey up to
        /// the forecast EAC), the budget line, the survey and the hand-over of the complex.</summary>
        void DrawEv(MeshGenerationContext ctx)
        {
            var r = ctlEvChart.contentRect; if (r.width < 40f || L == null) return; var g = ctx.painter2D;
            float top = 18f, bot = r.height - 16f, Hh = bot - top, mx = Mathf.Max(evEac, evBac + anRes) * 1.06f;
            float X(float t) => (t - T0) / (T1 - T0) * r.width;
            float Y(float v) => bot - v / mx * Hh;
            g.lineWidth = 1f;
            for (int k = 0; k <= 4; k++) { float y = top + Hh * k / 4f; g.strokeColor = new Color(1f, 1f, 1f, 0.06f); g.BeginPath(); g.MoveTo(new Vector2(0f, y)); g.LineTo(new Vector2(r.width, y)); g.Stroke(); }
            g.strokeColor = new Color(1f, 1f, 1f, 0.3f); g.lineWidth = 1f; Dashed(g, new Vector2(0f, Y(evBac)), new Vector2(r.width, Y(evBac)), 6f, 4f);
            g.strokeColor = new Color(1f, 0.35f, 0.31f, 0.35f); Dashed(g, new Vector2(0f, Y(evBac + anRes)), new Vector2(r.width, Y(evBac + anRes)), 2f, 4f);
            g.strokeColor = PlanLine; g.lineWidth = 1.5f;
            for (int j = 0; j < EvN; j++) Dashed(g, new Vector2(X(evT[j]), Y(evPV[j])), new Vector2(X(evT[j + 1]), Y(evPV[j + 1])), 4f, 3f);
            for (int j = 0; j < EvN; j++)
            {
                var a = new Vector2(X(evT[j]), Y(evEV[j])); var b = new Vector2(X(evT[j + 1]), Y(evEV[j + 1]));
                var c = new Vector2(X(evT[j]), Y(evAC[j])); var e = new Vector2(X(evT[j + 1]), Y(evAC[j + 1]));
                bool past = evT[j + 1] <= Report + 1e-4f;
                if (past)
                {
                    g.lineWidth = 2.2f; g.strokeColor = Blue; g.BeginPath(); g.MoveTo(a); g.LineTo(b); g.Stroke();
                    g.strokeColor = AcC; g.BeginPath(); g.MoveTo(c); g.LineTo(e); g.Stroke();
                }
                else
                {
                    g.lineWidth = 1.6f; g.strokeColor = BlueSoft; Dashed(g, a, b, 2f, 3f);
                    g.strokeColor = new Color(AcC.r, AcC.g, AcC.b, 0.5f); Dashed(g, c, e, 2f, 3f);
                }
            }
            VLine(g, X(Report), top, bot, Orange, 1.4f);
            float ev = Spent(Report, true);
            g.fillColor = Blue; g.BeginPath(); g.Arc(new Vector2(X(Report), Y(ev)), 3.5f, 0f, 360f); g.Fill();
            g.fillColor = AcC; g.BeginPath(); g.Arc(new Vector2(X(Report), Y(evAcR)), 3.5f, 0f, 360f); g.Fill();
            float fe = FactDate(LastPart(Report), 1f);
            if (fe <= T1) Diamond(g, new Vector2(X(fe), Y(evEac)), 5f, fe > L.Finish + 0.01f ? Orange : Green);
        }

        // ------------------------------------------------------------------ Недельный отчёт
        void BuildCtlReport(VisualElement v)
        {
            ctlRepScroll = Scroll(v, "ctl-vscroll");
            var row = Box(ctlRepScroll, "an-row");
            var lc = Box(row, "ctl-weeks");
            var c = Box(lc, "mon-card an-card");
            var h = Box(c, "an-sec", false); h.Add(TwinUI.Icon("calendar", 16)); Txt(h, "Неделя отчёта", "mon-title");

            for (int k = 0; k < 8; k++)
            {
                float e = Report - k * 7f / 365f, s = e - 6f / 365f; int kk = k;
                var b = new Button(() => { ctlWeek = kk; FillReport(); }) { focusable = false }; b.AddToClassList("ctl-week"); c.Add(b);
                Txt(b, $"Неделя {WeekNo(e)}", "ctl-week-n");
                Txt(b, $"{Day(s)} – {Day(e)}" + (k == 0 ? " · съёмка" : ""), "mon-src");
                ctlWeekBtns.Add(b);
            }
            c.Add(SourceTags.Line(SrcMon, SrcCrew, SrcDefects));
            var pc = Box(lc, "mon-card an-card");
            var ph = Box(pc, "an-sec", false); ph.Add(TwinUI.Icon("file_text", 16)); Txt(ph, "Отчёт в PDF", "mon-title");
            Txt(pc, "листами А4, как на экране", "w17-sub");
            pdfRep = new Button(() => ExportPdf()) { focusable = false }; pdfRep.AddToClassList("btn"); pdfRep.AddToClassList("w7-pdf"); pdfRep.AddToClassList("w7-pdf-big");
            pdfRep.Add(TwinUI.Icon("file_text", 14)); pdfRep.Add(new Label("Скачать PDF") { pickingMode = PickingMode.Ignore }); pc.Add(pdfRep);
            ctlPdfNote = Txt(pc, "", "mon-src w7-pdf-note"); ctlPdfNote.style.display = DisplayStyle.None;
            var pb = Box(row, "ctl-paperbox");
            ctlRepPaper = Box(pb, "an-paper ctl-paper");
        }
        static int WeekNo(float y)
        {
            var t = new DateTime(Mathf.FloorToInt(y), 1, 1).AddDays(Mathf.Floor((y - Mathf.Floor(y)) * 365f));
            return CultureInfo.InvariantCulture.Calendar.GetWeekOfYear(t, CalendarWeekRule.FirstFourDayWeek, DayOfWeek.Monday);
        }
        /// <summary>The forecast hand-over of building i as it looked at date d: the shift of the survey scaled by the delay then.</summary>
        float EndAt(int i, float d)
        {
            var o = Obj(i, Report); float dr = DelayAt(i, Report), dd = DelayAt(i, d);
            float shift = d >= Report - 1e-4f || dr < 1e-4f ? o.EndDays / 365f : o.EndDays / 365f * Mathf.Clamp01(dd / dr);
            return PlanDate(i, 1f) + shift;
        }
        float ComplexEndAt(float d) { float e = 0f; for (int i = 0; i < L.Parts.Count; i++) e = Mathf.Max(e, EndAt(i, d)); return e; }
        void WeekCrew(float e, out int people, out int machines, out int stops)
        {
            people = machines = stops = 0; int days = 0;
            for (int k = 0; k < 7; k++)
            {
                DayCrew(e - k / 365f, out int p, out _, out int m, out bool w);
                var t = new DateTime(Mathf.FloorToInt(e), 1, 1).AddDays(Mathf.Floor((e - k / 365f - Mathf.Floor(e)) * 365f));
                if (w) stops++;
                if (t.DayOfWeek == DayOfWeek.Sunday) continue;
                people += p; machines += m; days++;
            }
            if (days > 0) { people /= days; machines /= days; }
        }
        /// <summary>The weekly report on paper: the main thing, the numbers against the week before, what changed, the risks, the actions.</summary>
        void FillReport()
        {
            if (ctlRepPaper == null) return;
            for (int i = 0; i < ctlWeekBtns.Count; i++) ctlWeekBtns[i].EnableInClassList("active", i == ctlWeek);
            float e = Report - ctlWeek * 7f / 365f, s = e - 7f / 365f;
            var p = ctlRepPaper; p.Clear();
            Txt(p, "ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ ДЛЯ ИНВЕСТОРА", "an-pk");
            Txt(p, $"{L.Name} · неделя {WeekNo(e)}", "an-ph1");
            Txt(p, $"{Day(s + 1f / 365f)} – {Day(e)} · по аэросъёмке, видеоаналитике и журналу технадзора", "an-pmeta");
            Txt(p, "Демо-сценарий цифрового двойника QTwin: данные смоделированы, это не данные застройщика.", "an-pmeta");
            Box(p, "an-prule", false);

            float rf = Ready(e, true), rp = Ready(e, false), rf0 = Ready(s, true), rp0 = Ready(s, false);
            int sd = SchedDelay(e), sd0 = SchedDelay(s);
            float ce = ComplexEndAt(e), ce0 = ComplexEndAt(s);
            float ev = Spent(e, true), ev0 = Spent(s, true), pv = Spent(e, false), pv0 = Spent(s, false), ac = AcAt(e), ac0 = AcAt(s);
            float spi = pv > 0.01f ? ev / pv : 1f, spi0 = pv0 > 0.01f ? ev0 / pv0 : 1f, cpi = ac > 0.01f ? ev / ac : 1f, cpi0 = ac0 > 0.01f ? ev0 / ac0 : 1f;
            WeekCrew(e, out int ppl, out int mch, out int stops); WeekCrew(s, out int ppl0, out int mch0, out int stops0);
            int open = 0, open0 = 0, crit = 0, nw = 0, cl = 0;
            foreach (var f in defects)
            {
                if (DefOpen(f, e)) { open++; if (f.Sev >= 2) crit++; }
                if (DefOpen(f, s)) open0++;
                if (f.Found > s && f.Found <= e) nw++;
                if (f.Closed > s && f.Closed <= e) cl++;
            }

            // every number is rounded once, as it is shown; the words and the changes are computed from the rounded values
            float r1 = R1(rf * 100f), r0 = R1(rf0 * 100f), q1 = R1(rp * 100f), q0 = R1(rp0 * 100f);
            int dce = (DayDT(ce) - DayDT(ce0)).Days;
            float evr = MR(ev), evr0 = MR(ev0), acr = MR(ac), acr0 = MR(ac0);
            float spr = R2(spi), spr0 = R2(spi0), cpr = R2(cpi), cpr0 = R2(cpi0);
            Txt(p, "1. Главное", "an-ph2");
            string trend = sd > sd0 ? $"за неделю выросло на {sd - sd0} дн." : sd < sd0 ? $"за неделю сократилось на {sd0 - sd} дн." : "за неделю не изменилось.";
            P(p, $"Готовность комплекса {Pc1(r1)} при плане {Pc1(q1)} ({Signed(r1 - r0)} за неделю). Отставание {sd} дн., {trend} Прогноз ввода комплекса — {IconicFloors.MonthYear(ce)} при плане {IconicFloors.MonthYear(L.Finish)}.");
            P(p, $"Деньги: {CpiWords(cpr)}, {SpiWords(spr)}. Прогноз итоговой стоимости на дату съёмки — {Mln(evEac)} при бюджете {Mln(evBac)}.");

            Txt(p, "2. Показатели", "an-ph2");
            float[] wd = { 0.4f, 0.2f, 0.2f, 0.2f };
            Row(p, wd, true, "Показатель", Day(e), Day(s), "Изменение");
            Row(p, wd, false, "Готовность комплекса, факт", Pc1(r1), Pc1(r0), Signed(r1 - r0));
            Row(p, wd, false, "Готовность комплекса, план", Pc1(q1), Pc1(q0), Signed(q1 - q0));
            Row(p, wd, false, "Отставание комплекса", $"{sd} дн.", $"{sd0} дн.", Diff(sd - sd0) + " дн.");
            Row(p, wd, false, "Прогноз ввода комплекса", Day(ce), Day(ce0), Diff(dce) + " дн.");
            Row(p, wd, false, "Сделано работ (EV)", Mln(evr), Mln(evr0), SMln(evr - evr0));
            Row(p, wd, false, "Затраты (AC)", Mln(acr), Mln(acr0), SMln(acr - acr0));
            Row(p, wd, false, "SPI — темп к графику", Ix(spr), Ix(spr0), DIx(spr - spr0));
            Row(p, wd, false, "CPI — цена к смете", Ix(cpr), Ix(cpr0), DIx(cpr - cpr0));
            Row(p, wd, false, "Людей в день, в среднем", Loc.N0(ppl), Loc.N0(ppl0), Diff(ppl - ppl0));
            Row(p, wd, false, "Техники в день, в среднем", Loc.N0(mch), Loc.N0(mch0), Diff(mch - mch0));
            Row(p, wd, false, "Дней с погодным простоем", stops.ToString(), stops0.ToString(), Diff(stops - stops0));
            Row(p, wd, false, "Открытых дефектов", open.ToString(), open0.ToString(), Diff(open - open0));

            Txt(p, "3. Что изменилось за неделю", "an-ph2");
            var gains = new List<(int i, float g)>();
            for (int i = 0; i < L.Parts.Count; i++) { float g = FactP(i, e) - FactP(i, s); if (g > 0.0005f) gains.Add((i, g)); }
            gains.Sort((a, b) => b.g.CompareTo(a.g));
            for (int k = 0; k < gains.Count && k < 3; k++)
            {
                int i = gains[k].i; var o = Obj(i, e);
                P(p, $"• {Pt(i).Name}: +{Loc.N1(gains[k].g * 100f)} п.п., готовность {Pct(o.Fact)} при плане {Pct(o.Plan)}. Сейчас: {NowWork(i, e)}.");
            }
            if (gains.Count == 0) P(p, "• Работы на площадке не велись.");
            P(p, $"• Дефекты: новых {nw}, устранено {cl}, открыто на конец недели {open}" + (crit > 0 ? $", из них критических {crit}." : "."));
            if (stops > 0) P(p, $"• Погода: {stops} {DaysWord(stops)} с простоем по погодным правилам площадки.");

            Txt(p, "4. Риски", "an-ph2");
            int nr = 0;
            for (int i = 0; i < L.Parts.Count; i++)
            {
                var o = Obj(i, e); if (!(o.Fact > 0f && o.Fact < 0.999f && o.Days > 21)) continue;
                int sh = Mathf.RoundToInt((EndAt(i, e) - PlanDate(i, 1f)) * 365f);
                P(p, sh > 3 ? $"• Срок: «{Pt(i).Name}» отстаёт на {o.Days} дн., ввод сдвигается на {sh} дн. — по договору возможна неустойка 0,05 % в день." : $"• Срок: «{Pt(i).Name}» отстаёт на {o.Days} дн.; по прогнозу закрывается к вводу, если сохранить вторую смену."); nr++;
            }
            if (anCrew >= 0) { Sum(trades[anCrew], out int need, out int have); P(p, $"• Люди: на объекте «{Pt(anCrew).Name}» {Loc.N0(have)} из {Loc.N0(need)} человек по графику."); nr++; }
            if (anTot.Over > 0f) { P(p, NetOver > 0f ? $"• Деньги: прогноз выше бюджета на {Mln(anTot.Over)}, резерв не покрывает {Mln(NetOver)}." : $"• Деньги: прогноз выше бюджета на {Mln(anTot.Over)}, пока в пределах резерва."); nr++; }
            int m1 = (MonthOf(e) + 1) % 12;
            if (DownDays(m1) > 4f) { P(p, $"• Погода: в следующем месяце ({MonthName[m1]}) по климатической норме ≈ {Mathf.RoundToInt(DownDays(m1))} дн. простоя."); nr++; }
            if (crit > 0) { P(p, $"• Качество: открыто критических дефектов — {crit}."); nr++; }
            if (nr == 0) P(p, "• Существенных рисков нет.");

            Txt(p, "5. Что делать", "an-ph2");
            int n = 1; foreach (var a in Actions(e)) P(p, $"{n++}. {a.Title} — {a.Effect} (оценка модели). {a.Why}");
            Box(p, "an-prule", false);
            Txt(p, $"Подготовлено цифровым двойником QTwin · {Day(e)}. Цены сметы — рынок Алматы 22–26.10.2026 (olx.kz), курс НБ РК 23.10.2026; климат — Weather Spark; остальное — модель.", "an-pmeta");
            ctlRepScroll.scrollOffset = Vector2.zero;
        }
        static float R1(float v) => Mathf.Round(v * 10f) / 10f;
        static float R2(float v) => Mathf.Round(v * 100f) / 100f;
        static string Pc1(float pct) => Loc.N1(pct) + " %";
        /// <summary>A sum in millions rounded the way Mln shows it, so a difference of two shown sums is the shown difference.</summary>
        static float MR(float m) { float a = Mathf.Abs(m); return a >= 1000f ? Mathf.Round(m / 100f) * 100f : a >= 100f ? Mathf.Round(m) : Mathf.Round(m * 10f) / 10f; }
        static string DIx(float d) => Mathf.Abs(d) < 0.005f ? Ix(0f) : (d > 0f ? "+" : "−") + Ix(Mathf.Abs(d));
        static DateTime DayDT(float y) => new DateTime(Mathf.FloorToInt(y), 1, 1).AddDays((y - Mathf.Floor(y)) * 365f).Date;
        static void P(VisualElement p, string t) { var e = Box(p, "an-pp", false); Txt(e, t, "an-pp-t"); }
        static void Row(VisualElement p, float[] wd, bool head, params string[] c)
        {
            var e = Box(p, "an-ptr2" + (head ? " head" : ""), false);
            for (int i = 0; i < c.Length; i++) { var l = Txt(e, c[i], "an-pc" + (i == 0 ? " first" : "")); l.style.width = Length.Percent(wd[i] * 100f); }
        }
        static string DaysWord(int n) { int m = n % 100, d = n % 10; return m >= 11 && m <= 14 ? "дней" : d == 1 ? "день" : d >= 2 && d <= 4 ? "дня" : "дней"; }
        /// <summary>The work going on in building i at date d (the latest started one), with its progress.</summary>
        string NowWork(int i, float d)
        {
            float best = -1f; string s = null;
            foreach (var w in works) { if (w.Sum || w.Part != i) continue; var st = Stat(w, d); if (st.Fact > 0f && st.Fact < 0.999f && w.A > best) { best = w.A; s = $"{w.Name.ToLowerInvariant()} — {Pct(st.Fact)}"; } }
            return s ?? "идут работы";
        }

        // ------------------------------------------------------------------ Люди и погода
        void BuildCtlRes(VisualElement v)
        {
            v = Scroll(v, "ctl-vscroll");
            var row = Box(v, "an-row");
            var lc = Box(row, "an-colL ctl-col");
            // people and machines by day over the last six weeks
            var c = Box(lc, "mon-card an-card");
            var h = Box(c, "an-sec", false); h.Add(TwinUI.Icon("hard_hat", 16)); Txt(h, "Люди и техника на площадке", "mon-title");
            Txt(c, "за 6 недель · видеоаналитика", "w17-sub");
            DayCrew(Report, out int p0, out int pl0, out int m0, out _);
            int maxP = 0, sumP = 0, nd = 0, ws = 0; for (int k = 0; k < 42; k++) { DayCrew(Report - k / 365f, out int pp, out _, out _, out bool w); maxP = Mathf.Max(maxP, pp); if (pp > 0) { sumP += pp; nd++; } if (w) ws++; }
            var kr = Box(c, "ctl-minik", false);
            MiniK(kr, "Людей в день съёмки", Loc.N0(p0), $"по графику {Loc.N0(pl0)}", p0 < pl0 * 0.9f ? "warn" : "");
            MiniK(kr, "Техники", Loc.N0(m0), "краны, бетононасосы, автотранспорт", "");
            MiniK(kr, "В среднем за 6 недель", Loc.N0(nd > 0 ? sumP / nd : 0), $"пик {Loc.N0(maxP)} чел.", "");
            MiniK(kr, "Погодных простоев", ws.ToString(), $"{DaysWord(ws)} из 42", ws > 6 ? "warn" : "");
            var lg = Box(c, "an-tools ctl-leg", false);
            lg.Add(Widgets.LegendItem(Blue, "люди")); lg.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.6f), "по графику")); lg.Add(Widgets.LegendItem(Orange, "техника, ед."));
            lg.Add(Widgets.LegendItem(ColdC, "погодный простой"));
            ctlCrewChart = Box(c, "ctl-chart ctl-crew"); ctlCrewChart.generateVisualContent += DrawCrew;
            var ym = Txt(ctlCrewChart, $"{Loc.N0(maxP * 1.15f)} чел.", "ctl-ymax"); ym.style.position = Position.Absolute;
            var dr = Box(c, "mon-row ctl-dates", false); Txt(dr, Day(Report - 41f / 365f), "mon-src"); Spacer(dr); Txt(dr, Day(Report), "mon-src");
            c.Add(SourceTags.Line(SrcCrew));
            // the trades on the site: what the schedule asks for against what the cameras count
            var tc = Box(lc, "mon-card an-card");
            var th = Box(tc, "an-sec", false); th.Add(TwinUI.Icon("hard_hat", 16)); Txt(th, "Бригады по профессиям", "mon-title");
            Txt(tc, "есть на площадке из нужных по графику", "w17-sub");
            var agg = new Dictionary<string, Trade>(); var ord = new List<string>();
            for (int i = 0; i < L.Parts.Count; i++) foreach (var t in trades[i]) { if (!agg.ContainsKey(t.Name)) { agg[t.Name] = new Trade { Name = t.Name }; ord.Add(t.Name); } agg[t.Name].Need += t.Need; agg[t.Name].Have += t.Have; }
            ord.Sort((a, b) => (agg[b].Need - agg[b].Have).CompareTo(agg[a].Need - agg[a].Have));
            foreach (var nm in ord)
            {
                var t = agg[nm]; if (t.Need <= 0) continue;
                var r = Box(tc, "ctl-wt", false); var top = Box(r, "mon-row", false);
                Txt(top, t.Name, "ctl-wt-n"); Spacer(top);
                var vv = Txt(top, $"{Loc.N0(t.Have)} из {Loc.N0(t.Need)}", "ctl-wt-p");
                float sh = (t.Need - t.Have) / (float)t.Need; vv.AddToClassList(sh > 0.15f ? "bad" : sh > 0.06f ? "warn" : "ok");
                var bar = Box(r, "mon-bar ctl-wt-bar", false); var fl = Box(bar, "mon-fill", false); fl.style.width = Length.Percent(Mathf.Clamp01(t.Have / (float)t.Need) * 100f);
            }
            tc.Add(SourceTags.Line(SrcCrew));

            // the weather of Almaty and the downtime
            var rc = Box(row, "an-colR ctl-col");
            var wc = Box(rc, "mon-card an-card");
            var wh = Box(wc, "an-sec", false); wh.Add(TwinUI.Icon("cloud_sun", 16)); Txt(wh, "Погода Алматы и простои", "mon-title");
            Txt(wc, "дней простоя в месяц по климатической норме", "w17-sub");
            int mNow = MonthOf(Report); float next3 = 0f; for (int k = 1; k <= 3; k++) next3 += DownDays((mNow + k) % 12);
            float all = DownBetween(L.Begin, L.Finish);
            var kw = Box(wc, "ctl-minik", false);
            MiniK(kw, "Простои за срок стройки", $"≈ {Mathf.RoundToInt(all)} дн.", $"{IconicFloors.MonthYear(L.Begin)} – {IconicFloors.MonthYear(L.Finish)}", "");
            MiniK(kw, "В ближайшие 3 месяца", $"≈ {Mathf.RoundToInt(next3)} дн.", $"{MonthName[(mNow + 1) % 12]} – {MonthName[(mNow + 3) % 12]}", next3 > 15f ? "warn" : "");
            var lg2 = Box(wc, "an-tools ctl-leg", false);
            lg2.Add(Widgets.LegendItem(ColdC, "мороз: бетон")); lg2.Add(Widgets.LegendItem(WindC, "ветер: краны")); lg2.Add(Widgets.LegendItem(WetC, "осадки: фасад, кровля"));
            var ch = Box(wc, "ctl-wx", false); float mx = 0f; for (int m = 0; m < 12; m++) mx = Mathf.Max(mx, DownDays(m));
            for (int m = 0; m < 12; m++)
            {
                var col = Box(ch, "ctl-wcol" + (m == mNow ? " cur" : ""), false);
                Txt(col, Loc.N1(DownDays(m)), "ctl-tv");
                var well = Box(col, "ctl-wwell", false);
                foreach (var (val, cc) in new[] { (WetDays[m] * WetLoss, WetC), (GustDays(m) * CraneLoss, WindC), (ColdDays(m) * ConcreteLoss, ColdC) })
                { var s = Box(well, "ctl-wseg", false); s.style.height = Length.Percent(val / Mathf.Max(mx, 0.1f) * 100f); s.style.backgroundColor = cc; }
                Txt(col, MonthShort[m], "ctl-td-d");
                Txt(col, $"{Mathf.RoundToInt(TempHi[m])}° / {Mathf.RoundToInt(TempLo[m])}°", "ctl-wt-t");
            }
            var rules = Widgets.Details(wc, "Правила площадки");
            Txt(rules, "Под столбиком: средняя температура днём / ночью. Над ним: дней простоя в месяц.", "w17-note");
            foreach (var (ic, t) in new[] { ("layers", "Бетон без прогрева — только при ночной температуре не ниже −5 °C; с прогревом темп падает на четверть"),
                                            ("hard_hat", "Башенные краны — стоп при порывах ветра выше 15 м/с: теряется около половины смены"),
                                            ("cloud_sun", "Фасад и кровля — не монтируются в дождь и снег: около трети рабочего дня") })
            {
                var r = Box(rules, "mon-row ctl-rule", false); var i = TwinUI.Icon(ic, 14); i.style.marginRight = 8; i.style.flexShrink = 0; r.Add(i); Txt(r, t, "ctl-rule-t");
            }
            wc.Add(SourceTags.Line(SrcClimate, SrcDown));
        }
        void MiniK(VisualElement parent, string cap, string val, string sub, string cls)
        {
            var b = Box(parent, "ctl-mk", false); Txt(b, cap, "mon-inv-cap"); var v = Txt(b, val, "ctl-mk-v"); if (cls.Length > 0) v.AddToClassList(cls); Txt(b, sub, "mon-inv-sub");
        }
        void DrawCrew(MeshGenerationContext ctx)
        {
            var r = ctlCrewChart.contentRect; if (r.width < 40f || L == null) return; var g = ctx.painter2D;
            const int n = 42; int maxP = 1, maxM = 1;
            var pp = new int[n]; var pl = new int[n]; var mm = new int[n]; var ww = new bool[n];
            for (int k = 0; k < n; k++) { DayCrew(Report - (n - 1 - k) / 365f, out pp[k], out pl[k], out mm[k], out ww[k]); maxP = Mathf.Max(maxP, Mathf.Max(pp[k], pl[k])); maxM = Mathf.Max(maxM, mm[k]); }
            float top = 18f, bot = r.height - 4f, Hh = bot - top, mx = maxP * 1.15f, bw = r.width / n;
            g.lineWidth = 1f;
            for (int k = 0; k <= 3; k++) { float y = top + Hh * k / 3f; g.strokeColor = new Color(1f, 1f, 1f, 0.06f); g.BeginPath(); g.MoveTo(new Vector2(0f, y)); g.LineTo(new Vector2(r.width, y)); g.Stroke(); }
            for (int k = 0; k < n; k++)
            {
                float h = pp[k] / mx * Hh;
                if (ww[k]) FillR(g, new Rect(k * bw, top, bw, Hh), new Color(ColdC.r, ColdC.g, ColdC.b, 0.13f));
                FillR(g, new Rect(k * bw + bw * 0.15f, bot - h, bw * 0.7f, h), ww[k] ? new Color(Blue.r, Blue.g, Blue.b, 0.55f) : Blue);
            }
            g.strokeColor = PlanLine; g.lineWidth = 1.4f;
            for (int k = 0; k < n - 1; k++) Dashed(g, new Vector2((k + 0.5f) * bw, bot - pl[k] / mx * Hh), new Vector2((k + 1.5f) * bw, bot - pl[k + 1] / mx * Hh), 3f, 2f);
            g.strokeColor = Orange; g.lineWidth = 1.8f; g.BeginPath();
            float mk = Hh * 0.55f / Mathf.Max(maxM, 1);
            for (int k = 0; k < n; k++) { var pt = new Vector2((k + 0.5f) * bw, bot - mm[k] * mk); if (k == 0) g.MoveTo(pt); else g.LineTo(pt); }
            g.Stroke();
        }

        // ================================================================== Дефекты (over the live model)
        VisualElement defL, defR, defList, defCard; readonly List<Button> defFilt = new List<Button>();
        readonly List<VisualElement> defPins = new List<VisualElement>(); readonly List<VisualElement> defRows = new List<VisualElement>();
        int defSel = -1, defMode = 1; bool defAll; Button defMore;
        void BuildDefects()
        {
            defFilt.Clear(); defPins.Clear(); defRows.Clear();
            defL = Col("mon-left"); defR = Col("mon-right");
            var c = Card(defL); c.AddToClassList("def-card");
            Head(c, "triangle_alert", "Дефекты");                                // the object is chosen in the header
            Txt(c, "Нажмите на дефект — камера покажет его на модели", "w17-sub");
            int open = 0, crit = 0, closed30 = 0;
            foreach (var f in defects) { if (DefOpen(f, Report)) { open++; if (f.Sev >= 2) crit++; } else if (f.Closed > Report - 30f / 365f) closed30++; }
            var kr = Box(c, "ctl-minik", false);
            MiniK(kr, "Открыто", open.ToString(), "в работе", open > 0 ? "warn" : "");
            MiniK(kr, "Критических", crit.ToString(), "стоп этапу", crit > 0 ? "bad" : "");
            MiniK(kr, "Устранено", closed30.ToString(), "за 30 дней", "");
            var seg = Box(c, "mon-seg ctl-parts");
            foreach (var (t, m) in new[] { ("Открытые", 1), ("Все", 0), ("Устранённые", 2) })
            { int mm = m; var b = Widgets.Btn(t, () => { defMode = mm; defAll = false; FillDefList(); }, "small"); seg.Add(b); defFilt.Add(b); b.userData = m; }
            defList = Scroll(c, "def-list");
            defMore = Widgets.Btn("", () => { defAll = !defAll; FillDefList(); }, "small", "ghost"); defMore.AddToClassList("w21-more"); c.Add(defMore);
            c.Add(SourceTags.Line(SrcDefects));
            defCard = Card(defR); defCard.AddToClassList("def-card");
            // the pins over the picture
            for (int i = 0; i < defects.Count; i++)
            {
                int k = i; var f = defects[i];
                var pe = new VisualElement(); pe.AddToClassList("mon-pin"); pe.AddToClassList("def-pin"); pe.AddToClassList(DefOpen(f, Report) ? DefCls[f.Sev] : "closed"); pe.style.display = DisplayStyle.None;
                pe.Add(new Label(f.No) { pickingMode = PickingMode.Ignore }); var st = new VisualElement { pickingMode = PickingMode.Ignore }; st.AddToClassList("mon-stem"); pe.Add(st);
                pe.RegisterCallback<ClickEvent>(_ => SelectDef(k, true)); body.Add(pe); defPins.Add(pe);
            }
            defSel = -1; for (int i = 0; i < defects.Count; i++) if (DefOpen(defects[i], Report) && (defSel < 0 || defects[i].Sev > defects[defSel].Sev)) defSel = i;
            FillDefList(); FillDefCard();
        }
        bool DefShown(Defect f) => defMode == 0 || (defMode == 1) == DefOpen(f, Report);
        void FillDefList()
        {
            if (defList == null) return;
            foreach (var b in defFilt) b.EnableInClassList("active", (int)b.userData == defMode);
            defList.Clear(); defRows.Clear();
            // the five most important first (critical, then significant, then minor); the rest behind «Ещё N», the selected one always shown
            int total = 0; foreach (var f0 in defects) if (DefShown(f0)) total++;
            int shown = 0;
            var order = new List<int>(); for (int i = 0; i < defects.Count; i++) order.Add(i);
            order.Sort((x, y) => { int sx = DefOpen(defects[x], Report) ? defects[x].Sev : -1, sy = DefOpen(defects[y], Report) ? defects[y].Sev : -1; return sx != sy ? sy.CompareTo(sx) : x.CompareTo(y); });
            foreach (int i in order)
            {
                var f = defects[i]; if (!DefShown(f)) continue; int k = i; bool op = DefOpen(f, Report);
                if (!defAll && shown >= 5 && k != defSel) continue;
                shown++;
                var r = new Button(() => SelectDef(k, true)) { focusable = false }; r.AddToClassList("def-row"); if (k == defSel) r.AddToClassList("sel"); defList.Add(r); r.userData = k; defRows.Add(r);
                r.Add(Widgets.Dot(op ? SevColor(f.Sev) : new Color(0.55f, 0.55f, 0.55f), true));
                var tx = Box(r, "def-tx", false);
                Txt(tx, $"{f.No} · {f.Type}", "def-t");
                Txt(tx, f.Where, "w17-def-w");
                Txt(r, op ? DefSev[f.Sev] : "устранён", "an-tag " + (op ? (f.Sev >= 2 ? "s-bad" : f.Sev == 1 ? "s-warn" : "s-info") : "s-ok"));
            }
            if (defMore != null) { Vis(defMore, total > 5); defMore.text = defAll ? "Свернуть" : string.Format("Ещё {0} ›", total - shown); if (!defAll && total - shown <= 0) Vis(defMore, false); }
            if (defRows.Count == 0) Txt(defList, defMode == 1 ? "Открытых дефектов нет." : "Устранённых дефектов пока нет.", "mon-para");
        }
        /// <summary>A defect shown from outside (ShotRig, the AI assistant): the defects page, defect k selected, the camera at it.</summary>
        public void ShowDefect(int k) { if (open) { if (tab != TDef) { defSel = Mathf.Clamp(k, 0, defects.Count - 1); SetTab(TDef); } else SelectDef(k, true); } }
        /// <summary>Selects defect k: the row and its pin are marked, the card shows it; fly — the 3D view flies to it (a short pull-back
        /// and a flight in, so the click is seen even when the camera already looks at it) and a pulsing ring marks the place.</summary>
        void SelectDef(int k, bool fly)
        {
            if (k < 0 || k >= defects.Count) return;
            defSel = k; var f = defects[k];
            bool listed = false; foreach (var r in defRows) listed |= (int)r.userData == k;
            if (!listed) FillDefList();                               // a defect behind «Ещё N» (picked on the model): its row joins the list
            foreach (var r in defRows) { bool on = (int)r.userData == k; r.EnableInClassList("sel", on); if (on && defList is ScrollView sv) sv.ScrollTo(r); }
            FillDefCard();
            if (!fly) return;
            if (tab != TDef && overlay != null) { SetTab(TDef); return; }          // SetTab(TDef) flies to defSel itself
            defPulse = 0f; defFly = 0.5f;
            if (obj != f.Part) SelectObj(f.Part, false);
            view = View.Complex; zoomK = 2.4f; focusLocal = f.Pos; focusDist = f.Part == TI ? 95f : 120f; pitch = 20f;
            if (model != null && f.Part == TI)
            {
                // the tower's defects are on its east face: look at it from outside, a little from the south
                var dir = model.TransformDirection(new Vector3(-1f, 0f, 0.3f)); yaw = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;
            }
            dirty = true;
        }
        void FillDefCard()
        {
            if (defCard == null) return;
            defCard.Clear();
            if (defSel < 0 || defSel >= defects.Count)
            {
                Head(defCard, "circle_check", "Открытых дефектов нет"); defCard.Add(Para("Все замечания технадзора на дату съёмки устранены.")); return;
            }
            var f = defects[defSel]; bool op = DefOpen(f, Report);
            var h = Box(defCard, "an-sec", false); var ic = TwinUI.Icon("map_pin", 16); ic.style.unityBackgroundImageTintColor = op ? SevColor(f.Sev) : Green; h.Add(ic);
            Txt(h, $"{f.No} · {f.Type}", "mon-title"); Spacer(h);
            Txt(h, op ? DefSev[f.Sev] : "устранён", "an-tag " + (op ? (f.Sev >= 2 ? "s-bad" : f.Sev == 1 ? "s-warn" : "s-info") : "s-ok"));
            var ans = Txt(defCard, f.Text, "w17-def-text");
            void F(string k, string v, string cls = "") { defCard.Add(FactRow(k, out var l)); l.text = v; if (cls.Length > 0) l.AddToClassList(cls); }
            F("Где", f.Where);
            int left = Mathf.RoundToInt((f.Due - Report) * 365f);
            F("Срок", op ? (left >= 0 ? $"{Day(f.Due)} · {left}\u00A0дн." : $"просрочен на {-left}\u00A0дн.") : $"устранён {Day(f.Closed)}", op && left < 0 ? "bad" : "");
            F("Статус", op ? (left >= 0 ? "в работе у подрядчика" : "просрочен") : "устранён", op ? (left >= 0 ? "" : "bad") : "ok");
            F("Ответственный", f.Who);
            var why = Widgets.Details(defCard, "Почему важно");
            Txt(why, string.Format("Обнаружен {0}.", Day(f.Found)), "w17-note");
            Txt(why, f.Sev >= 2 ? "Критический: влияет на прочность или безопасность — следующий этап на этом участке не начинают, пока дефект не устранён."
                : f.Sev == 1 ? "Значительный: влияет на качество и долговечность — устранить до сдачи этапа, иначе дороже переделывать."
                : "Малозначительный: на прочность и сроки не влияет — устраняется в общем порядке.", "w17-note");
            var sl = SourceTags.Line(SrcDefects); sl.style.marginTop = 8; defCard.Add(sl);
        }
        /// <summary>The pins of the defects over the picture (the page of defects only), placed where the camera sees them.</summary>
        void DefPins()
        {
            bool show = tab == TDef && monRT != null && view != View.Cam && view != View.Plan;
            int n = Mathf.Min(defPins.Count, defects.Count);
            if (defScr == null || defScr.Length < n) { defScr = new Vector2[n]; defOn = new bool[n]; defY0 = new float[n]; }
            for (int i = 0; i < n; i++)
            {
                var f = defects[i]; bool on = show && DefShown(f);
                if (on)
                {
                    var vp = mon.WorldToViewportPoint(model.TransformPoint(f.Pos));
                    on = vp.z > 0f && vp.x > 0.02f && vp.x < 0.98f && vp.y > 0.05f && vp.y < 0.95f;
                    // not under the columns of the page: a pin there would sit on top of the list or the card
                    if (on && body != null && body.layout.width > 10f)
                    {
                        var bp = new Vector2(vp.x * body.layout.width, (1f - vp.y) * body.layout.height);
                        if ((defL != null && defL.layout.Contains(bp)) || (defR != null && defR.layout.Contains(bp))) on = false;
                    }
                    defScr[i] = new Vector2(vp.x, 1f - vp.y); defY0[i] = defScr[i].y;
                }
                defOn[i] = on;
            }
            // badges that would touch: the later one goes up by a badge height, its stem grows so it still points at its place
            float bw = 54f / Mathf.Max(photo != null ? photo.layout.width : 1200f, 200f), bh = 24f / Mathf.Max(photo != null ? photo.layout.height : 700f, 200f);
            for (int i = 0; i < n; i++)
            {
                if (!defOn[i]) continue;
                for (int pass = 0; pass < 6; pass++)
                {
                    bool hit = false;
                    for (int j = 0; j < i; j++)
                        if (defOn[j] && Mathf.Abs(defScr[i].x - defScr[j].x) < bw && Mathf.Abs(defScr[i].y - defScr[j].y) < bh) { defScr[i].y = defScr[j].y - bh; hit = true; }
                    if (!hit) break;
                }
            }
            for (int i = 0; i < n; i++)
            {
                var pe = defPins[i];
                if (defOn[i])
                {
                    // the pin is anchored at its stem's foot: keep the foot at the place, the badge above it
                    pe.style.left = Length.Percent(defScr[i].x * 100f); pe.style.top = Length.Percent(defY0[i] * 100f);
                    float up = (defY0[i] - defScr[i].y) * (photo != null ? photo.layout.height : 700f);
                    if (pe.childCount > 1) pe[1].style.height = 14f + Mathf.Max(up, 0f);
                }
                pe.style.display = defOn[i] ? DisplayStyle.Flex : DisplayStyle.None;
                pe.EnableInClassList("sel", i == defSel);
            }
        }
        Vector2[] defScr; bool[] defOn; float[] defY0;
        // ---- the pulsing mark of the selected defect: a dot at the place and a ring that grows and fades (faster for 2 s after a click)
        VisualElement defMark, defRing; float defPulse = -1f, defFly;
        void BuildDefMark()
        {
            defMark = new VisualElement { pickingMode = PickingMode.Ignore }; defMark.AddToClassList("w17-dmark"); defMark.style.display = DisplayStyle.None;
            defRing = new VisualElement { pickingMode = PickingMode.Ignore }; defRing.AddToClassList("w17-dmark-ring"); defMark.Add(defRing);
            var core = new VisualElement { pickingMode = PickingMode.Ignore }; core.AddToClassList("w17-dmark-core"); defMark.Add(core);
            body.Add(defMark);
        }
        void DefMark(float dt)
        {
            if (defMark == null) return;
            bool on = tab == TDef && defSel >= 0 && defOn != null && defSel < defOn.Length && defOn[defSel];
            if (defFly > 0f) { defFly -= dt; if (defFly <= 0f && tab == TDef) zoomK = 1f; }      // the pull-back is over: fly in
            if (!on) { if (defMark.style.display != DisplayStyle.None) defMark.style.display = DisplayStyle.None; return; }
            defMark.style.display = DisplayStyle.Flex;
            defMark.style.left = Length.Percent(defScr[defSel].x * 100f); defMark.style.top = Length.Percent(defY0[defSel] * 100f);
            var df = defects[defSel]; var c = DefOpen(df, Report) ? SevColor(df.Sev) : new Color(0.20f, 0.78f, 0.35f);
            if (defPulse >= 0f) { defPulse += dt; if (defPulse > 2f) defPulse = -1f; }
            float speed = defPulse >= 0f ? 1.8f : 0.9f, t = (phase * speed) % 1f, sc = 1f + (defPulse >= 0f ? 3.2f : 2.2f) * t;
            defRing.style.scale = new Scale(new Vector3(sc, sc, 1f)); defRing.style.opacity = 1f - t;
            defRing.style.borderTopColor = defRing.style.borderRightColor = defRing.style.borderBottomColor = defRing.style.borderLeftColor = c;
            defMark[1].style.backgroundColor = c;
        }
    }
}
