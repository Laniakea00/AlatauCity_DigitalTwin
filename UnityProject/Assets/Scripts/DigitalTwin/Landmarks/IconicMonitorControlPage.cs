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
            Txt(tb, $"Контроль для инвестора · {L.Short}", "an-h1");
            Txt(tb, $"на {Day(Report)} — по последней съёмке · все данные стройки — демо-сценарий цифрового двойника", "mon-src");
            var seg = Box(head, "mon-seg"); seg.style.marginLeft = 22;
            foreach (var (txt, k) in new[] { ("Сводка", 0), ("Что изменилось", 3), ("Недельный отчёт", 1), ("Документы", 4), ("Люди и погода", 2) })
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
            ctlView = v;
            for (int i = 0; i < ctlTabs.Count; i++) ctlTabs[i].EnableInClassList("active", (int)ctlTabs[i].userData == v);
            Vis(ctlSumV, v == 0); Vis(ctlRepV, v == 1); Vis(ctlResV, v == 2); Vis(ctlChgV, v == 3); Vis(ctlDocsV, v == 4);
            if (v == 1) FillReport();
            if (v == 3) FillChanges();
        }

        // ------------------------------------------------------------------ Сводка
        void BuildCtlSummary(VisualElement v)
        {
            v = Scroll(v, "ctl-vscroll");                    // the whole view scrolls: nothing is cut at the window's bottom
            float d = Report, rf = Ready(d, true), rp = Ready(d, false);
            int sd = SchedDelay(d), last = LastPart(d);
            float fe = FactDate(last, 1f); int ld = Mathf.RoundToInt((fe - L.Finish) * 365f);
            string tt = TrendText(out string tcls);
            float over = evEac - evBac;

            string pm = IconicFloors.MonthYear(L.Finish), fm = IconicFloors.MonthYear(fe);
            string endTxt = ld > 3 ? (fm == pm ? $"{fm}, позже плана на {ld} дн." : $"{fm} вместо {pm} — позже на {ld} дн.")
                : ld < -3 && fm != pm ? $"{fm} вместо {pm} — раньше плана" : $"{fm}, в срок";
            var vb = Box(v, "an-verdict " + (sd > 21 || NetOver > 0f ? "s-bad" : sd > 3 || over > 0f ? "s-warn" : "s-ok"));
            Txt(vb, $"Главное для инвестора на {Day(d)}", "an-verdict-k");
            Txt(vb, $"Готовность {Pct(rf)} при плане {Pct(rp)}, отставание {sd} дн. ({tt}). Ввод комплекса — {endTxt}. Деньги: {CpiWords(evCpi)}, прогноз стоимости {Mln(evEac)} при бюджете {Mln(evBac)}.", "an-verdict-t");
            if (sd > 3 && ld <= 3) Txt(vb, WhyOnTime(d, sd, last), "mon-src ctl-why");

            var kr = Box(v, "an-kpis");
            AnK(kr, "Готовность комплекса", Pct(rf), $"по плану {Pct(rp)} · доли бюджета", rf < rp - 0.01f ? "warn" : "ok", () => SetTab(T4D));
            AnK(kr, "Отставание сейчас", $"{sd} дн.", tt, sd > 21 ? "bad" : sd > 3 ? "warn" : "ok", () => SetTab(T4D));
            AnK(kr, "Ввод комплекса · прогноз", IconicFloors.MonthYear(fe), ld > 3 ? $"по плану {pm} · позже на {ld} дн." : sd > 3 ? $"по плану {pm} · в срок: отставание закрывается к вводу" : $"по плану {pm} · в срок", ld > 21 ? "bad" : ld > 3 ? "warn" : "ok", () => SetTab(TInv));
            AnK(kr, "SPI · темп работ", Ix(evSpi), SpiWords(evSpi), evSpi < 0.95f ? "bad" : evSpi < 0.99f ? "warn" : "ok", null);
            AnK(kr, "CPI · цена работ", Ix(evCpi), CpiWords(evCpi), evCpi < 0.95f ? "bad" : evCpi < 0.99f ? "warn" : "ok", null);
            AnK(kr, "EAC · прогноз стоимости", Mln(evEac), over > 0f ? $"бюджет {Mln(evBac)} · {SMln(over)} ({SPc(over / evBac)})" : $"бюджет {Mln(evBac)} · экономия {Mln(-over)}", CostCls, () => { SetTab(TAn); anItem = TopOver(); AnView(1); });

            var row = Box(v, "an-row");
            var lc = Box(row, "an-colL ctl-col");
            // readiness by work type
            var wc = Box(lc, "mon-card an-card");
            var wh = Box(wc, "an-sec", false); wh.Add(TwinUI.Icon("list_checks", 16)); Txt(wh, "Готовность по видам работ", "mon-title");
            Txt(wc, "факт по съёмке против плана · белая риска — где должны быть по графику", "mon-src");
            var ps = Box(wc, "mon-seg ctl-parts");
            for (int i = -1; i < L.Parts.Count; i++)
            { int k = i; var b = Widgets.Btn(i < 0 ? "Весь комплекс" : Pt(i).Short, () => { ctlPart = k; FillWt(); }, "small"); ps.Add(b); ctlPartBtns.Add(b); }
            ctlWtRows = Box(wc, "ctl-wt-list");
            ctlPart = obj; FillWt();
            wc.Add(SourceTags.Line(SrcMon));
            // dates: planned and forecast hand-over, the delay and its trend
            var dc = Box(lc, "mon-card an-card");
            var dh = Box(dc, "an-sec", false); dh.Add(TwinUI.Icon("calendar", 16)); Txt(dh, "Сроки ввода", "mon-title");
            Txt(dc, "плановый и прогнозный ввод по фактическому темпу · отставание — на сколько дней работы позади графика", "mon-src");
            var th = Box(dc, "ctl-tr ctl-th", false);
            foreach (var (c, cls) in new[] { ("Объект", "n"), ("Ввод по плану", "m"), ("Прогноз", "m"), ("Сдвиг ввода", "m"), ("Отставание сейчас", "m") }) Txt(th, c, "ctl-td " + cls);
            for (int i = 0; i < L.Parts.Count; i++)
            {
                var o = Obj(i, d); int k = i;
                var r = new Button(() => { SetTab(T4D); SelectObj(k, true); }) { focusable = false }; r.AddToClassList("ctl-tr"); dc.Add(r);
                Txt(r, Pt(i).Name, "ctl-td n");
                Txt(r, IconicFloors.MonthYear(o.PlanEnd), "ctl-td m");
                Txt(r, IconicFloors.MonthYear(o.FactEnd), "ctl-td m");
                var s = Txt(r, o.EndDays > 3 ? $"+{o.EndDays} дн." : o.EndDays < -3 ? $"−{-o.EndDays} дн." : "в срок", "ctl-td m"); s.AddToClassList(o.EndDays > 21 ? "bad" : o.EndDays > 3 ? "warn" : "ok");
                var dl = Txt(r, o.Fact >= 0.999f ? "введён" : o.Plan <= 0f && o.Fact <= 0f ? "не начат" : o.Days > 3 ? $"{o.Days} дн." : "в графике", "ctl-td m"); dl.AddToClassList(o.Cls == "muted" ? "muted" : o.Cls);
            }
            var tr = Box(dc, "ctl-tr ctl-tot", false);
            Txt(tr, "Комплекс целиком", "ctl-td n"); Txt(tr, IconicFloors.MonthYear(L.Finish), "ctl-td m"); Txt(tr, IconicFloors.MonthYear(fe), "ctl-td m");
            var tl = Txt(tr, ld > 3 ? $"+{ld} дн." : "в срок", "ctl-td m"); tl.AddToClassList(ld > 21 ? "bad" : ld > 3 ? "warn" : "ok");
            var ts = Txt(tr, $"{sd} дн.", "ctl-td m"); ts.AddToClassList(sd > 21 ? "bad" : sd > 3 ? "warn" : "ok");
            // the trend: the delay of the complex at the last surveys
            var trh = Box(dc, "an-sec ctl-sub", false); Txt(trh, "Отставание комплекса по съёмкам", "ctl-k"); Spacer(trh); var tw = Txt(trh, tt, "ctl-k2"); tw.AddToClassList(tcls);
            var bars = Box(dc, "ctl-trend", false); int mx = 10; foreach (int x in trendD) mx = Mathf.Max(mx, x);
            for (int k = 0; k < trendD.Count; k++)
            {
                var col = Box(bars, "ctl-tcol", false);
                Txt(col, $"{trendD[k]} дн.", "ctl-tv");
                var well = Box(col, "ctl-twell", false);
                var b = Box(well, "ctl-tbar", false); b.style.height = Length.Percent(Mathf.Clamp01(Mathf.Max(trendD[k], 0) / (float)mx) * 100f);
                b.style.backgroundColor = trendD[k] > 21 ? new Color(1f, 0.35f, 0.31f, 0.85f) : trendD[k] > 3 ? new Color(0.96f, 0.65f, 0.14f, 0.85f) : new Color(0.20f, 0.78f, 0.35f, 0.85f);
                if (k == trendD.Count - 1) col.AddToClassList("cur");
                Txt(col, Day(trendT[k]), "ctl-td-d");
            }
            Txt(dc, "Отставание комплекса считается по объёму: на какую дату график планировал столько работ, сколько сделано сейчас. Крупные корпуса весят больше, чем газон.", "mon-src ctl-note");

            var rc = Box(row, "an-colR ctl-col");
            // the money: earned value
            var ec = Box(rc, "mon-card an-card");
            var eh = Box(ec, "an-sec", false); eh.Add(TwinUI.Icon("chart_line", 16)); Txt(eh, "Деньги: освоенный объём", "mon-title");
            Txt(ec, "сколько работ должно быть сделано, сколько сделано и сколько это стоило · млн $", "mon-src");
            var lg = Box(ec, "an-tools ctl-leg", false);
            lg.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.6f), "план (PV)")); lg.Add(Widgets.LegendItem(Blue, "сделано (EV)")); lg.Add(Widgets.LegendItem(AcC, "затраты (AC)"));
            lg.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.3f), "бюджет")); lg.Add(Widgets.LegendItem(Orange, "съёмка"));
            ctlEvChart = Box(ec, "ctl-chart ctl-ev"); ctlEvChart.generateVisualContent += DrawEv;
            for (int y = (int)T0; y <= (int)T1; y++)
            { var a = new Label(y.ToString()) { pickingMode = PickingMode.Ignore }; a.AddToClassList("mon-tick"); a.style.left = Length.Percent((y - T0) / (T1 - T0) * 100f); ctlEvChart.Add(a); }
            var ym = Txt(ctlEvChart, Mln(Mathf.Max(evEac, evBac + anRes) * 1.06f), "ctl-ymax"); ym.style.position = Position.Absolute;
            void Line(string k, string val, string words, string cls)
            {
                var r = Box(ec, "an-step", false);
                Txt(r, k, "an-step-n ctl-ix");
                var t = Box(r, "an-step-tx", false); Txt(t, words, "an-step-k");
                var vv = Txt(r, val, "an-step-v"); if (cls.Length > 0) vv.AddToClassList(cls);
            }
            float pvR = Spent(d, false);
            Line("SPI", Ix(evSpi), $"{SpiWords(evSpi)}: сделано работ на {Mln(anTot.Ev)} в ценах сметы, по графику к этой дате — на {Mln(pvR)}. SPI = сделано ÷ план.", evSpi < 0.95f ? "bad" : evSpi < 0.99f ? "warn" : "ok");
            Line("CPI", Ix(evCpi), $"{CpiWords(evCpi)}: за работы на {Mln(anTot.Ev)} по смете заплачено {Mln(evAcR)} — цены выросли с октября 2026. CPI = сделано ÷ затраты.", evCpi < 0.95f ? "bad" : evCpi < 0.99f ? "warn" : "ok");
            Line("EAC", Mln(evEac), $"Прогноз итоговой стоимости: потрачено {Mln(evAcR)} + остаток работ по ценам на {Day(d)} + сроки дольше графика. Бюджет {Mln(evBac)}, резерв {Mln(anRes)} — " +
                (NetOver > 0f ? $"не хватает {Mln(NetOver)}." : over > 0f ? "перерасход покрывается резервом." : "укладываемся в бюджет."), CostCls);
            ec.Add(SourceTags.Line(SrcEv, DSrc.OlxPrices, DSrc.NbrkRate));

            // what to do now
            var ac = Box(rc, "mon-card an-card");
            var ah = Box(ac, "an-sec", false); ah.Add(TwinUI.Icon("sparkles", 16)); Txt(ah, "Что делать сейчас", "mon-title");
            Txt(ac, "три действия с наибольшим эффектом на срок ввода · правила по данным двойника", "mon-src");
            int n = 1;
            foreach (var a in Actions(d)) ActCard(ac, a, n++);
            ac.Add(SourceTags.Line(SrcActs));
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
        void ActCard(VisualElement parent, Act a, int n)
        {
            string sc = SevCls[Mathf.Clamp(a.Sev + 1, 0, 3)];
            var c = Box(parent, "an-f ctl-act " + sc);
            var top = Box(c, "an-f-top", false);
            Txt(top, n.ToString(), "ctl-actn");
            var ic = TwinUI.Icon(a.Icon, 16); ic.style.unityBackgroundImageTintColor = SevColor(a.Sev); ic.style.flexShrink = 0; ic.style.marginLeft = 6; top.Add(ic);
            Txt(top, a.Title, "an-f-t");
            Txt(c, a.Why, "an-f-x");
            var br = Box(c, "an-f-src");
            var ef = Txt(br, a.Effect, "ctl-eff"); ef.AddToClassList(a.Days > 0 ? "ok" : "muted");
            br.Add(SourceTags.ModelTag(SrcActs));
            if (a.Show != null)
            {
                Spacer(br);
                var g = new Button(a.Show) { focusable = false }; g.AddToClassList("an-go");
                g.Add(new Label(a.ShowText) { pickingMode = PickingMode.Ignore }); g.Add(TwinUI.Icon("arrow_right", 12)); br.Add(g);
            }
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
                var r = Box(ctlWtRows, "ctl-wt", false);
                var top = Box(r, "mon-row", false);
                var nm = Box(top, "ctl-wt-tx", false); Txt(nm, WtName[t], "ctl-wt-n"); Txt(nm, WtHint[t], "mon-src");
                Spacer(top);
                var vals = Box(top, "ctl-wt-v", false);
                Txt(vals, $"{Pct(f)} · план {Pct(p)}", "ctl-wt-p");
                float dpp = (f - p) * 100f;
                string cls = p <= 0f && f <= 0f ? "muted" : f >= 0.999f ? "ok" : dpp < -5f || lag > 21 ? "bad" : dpp < -1f || lag > 3 ? "warn" : "ok";
                var dv = Txt(vals, p <= 0f && f <= 0f ? "не начато" : f >= 0.999f ? "выполнено" : lag > 3 ? $"{Signed(dpp)} · отстаёт {lag} дн." : $"{Signed(dpp)} · в графике", "ctl-wt-d"); dv.AddToClassList(cls);
                var bar = Box(r, "mon-bar ctl-wt-bar", false);
                var fl = Box(bar, "mon-fill", false); fl.style.width = Length.Percent(f * 100f);
                if (cls == "bad") fl.style.backgroundColor = new Color(1f, 0.35f, 0.31f); else if (cls == "warn") fl.style.backgroundColor = new Color(0.96f, 0.65f, 0.14f);
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
            Txt(c, "отчёт собирается из данных двойника за выбранные семь дней", "mon-src");
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
            Txt(pc, "отчёт выбранной недели — листами А4, как на экране", "mon-src");
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
            Txt(c, $"по дням за шесть недель до {Day(Report)} · подсчёт видеоаналитикой на КПП и в зонах работ", "mon-src");
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
            Txt(tc, $"весь комплекс на {Day(Report)} · по графику и по камерам", "mon-src");
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
            Txt(wc, "климатическая норма по месяцам и дни, потерянные по правилам площадки", "mon-src");
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
            Txt(wc, "Под столбиком: средняя температура днём / ночью. Над ним: дней простоя в месяц.", "mon-src ctl-note");
            var rules = Box(wc, "ctl-rules", false);
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
        int defSel = -1, defMode = 1;
        void BuildDefects()
        {
            defFilt.Clear(); defPins.Clear(); defRows.Clear();
            defL = Col("mon-left"); defR = Col("mon-right");
            var c = Card(defL); c.AddToClassList("def-card");
            Head(c, "triangle_alert", $"Дефекты · {L.Short}");
            var sub = new Label($"журнал технадзора на {Day(Report)} · нажмите — камера подлетит к месту") { pickingMode = PickingMode.Ignore }; sub.AddToClassList("mon-src"); c.Add(sub);
            int open = 0, crit = 0, closed30 = 0;
            foreach (var f in defects) { if (DefOpen(f, Report)) { open++; if (f.Sev >= 2) crit++; } else if (f.Closed > Report - 30f / 365f) closed30++; }
            var kr = Box(c, "ctl-minik", false);
            MiniK(kr, "Открыто", open.ToString(), "в работе у подрядчиков", open > 0 ? "warn" : "");
            MiniK(kr, "Критических", crit.ToString(), "мешают следующему этапу", crit > 0 ? "bad" : "");
            MiniK(kr, "Устранено", closed30.ToString(), "за 30 дней", "");
            var seg = Box(c, "mon-seg ctl-parts");
            foreach (var (t, m) in new[] { ("Открытые", 1), ("Все", 0), ("Устранённые", 2) })
            { int mm = m; var b = Widgets.Btn(t, () => { defMode = mm; FillDefList(); }, "small"); seg.Add(b); defFilt.Add(b); b.userData = m; }
            defList = Scroll(c, "def-list");
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
            for (int i = 0; i < defects.Count; i++)
            {
                var f = defects[i]; if (!DefShown(f)) continue; int k = i; bool op = DefOpen(f, Report);
                var r = new Button(() => SelectDef(k, true)) { focusable = false }; r.AddToClassList("def-row"); if (k == defSel) r.AddToClassList("sel"); defList.Add(r); r.userData = k; defRows.Add(r);
                r.Add(Widgets.Dot(op ? SevColor(f.Sev) : new Color(0.55f, 0.55f, 0.55f), true));
                var tx = Box(r, "def-tx", false);
                Txt(tx, $"{f.No} · {f.Type} · {f.Where}", "def-t");
                Txt(tx, f.Text, "def-x");
                Txt(tx, op ? $"обнаружен {Day(f.Found)} · {f.Who}" : $"устранён {Day(f.Closed)} · {f.Who}", "mon-src");
                Txt(r, op ? DefSev[f.Sev] : "устранён", "an-tag " + (op ? (f.Sev >= 2 ? "s-bad" : f.Sev == 1 ? "s-warn" : "s-info") : "s-ok"));
            }
            if (defRows.Count == 0) Txt(defList, defMode == 1 ? "Открытых дефектов нет." : "Устранённых дефектов пока нет.", "mon-para");
        }
        void SelectDef(int k, bool fly)
        {
            if (k < 0 || k >= defects.Count) return;
            defSel = k; var f = defects[k];
            foreach (var r in defRows) r.EnableInClassList("sel", (int)r.userData == k);
            FillDefCard();
            if (!fly) return;
            if (obj != f.Part) SelectObj(f.Part, false);
            view = View.Complex; zoomK = 1f; focusLocal = f.Pos; focusDist = f.Part == TI ? 95f : 120f; pitch = 20f;
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
            defCard.Add(Para(f.Text));
            void F(string k, string v, string cls = "") { defCard.Add(FactRow(k, out var l)); l.text = v; if (cls.Length > 0) l.AddToClassList(cls); }
            F("Где", f.Where);
            F("Обнаружен", Day(f.Found));
            int left = Mathf.RoundToInt((f.Due - Report) * 365f);
            F("Срок устранения", op ? (left >= 0 ? $"{Day(f.Due)} · осталось {left} дн." : $"{Day(f.Due)} · просрочен на {-left} дн.") : Day(f.Due), op && left < 0 ? "bad" : "");
            F("Статус", op ? "открыт" : $"устранён {Day(f.Closed)}", op ? "warn" : "");
            F("Ответственный", f.Who);
            defCard.Add(Para(f.Sev >= 2 ? "Критический: влияет на прочность или безопасность — следующий этап на этом участке не начинают, пока дефект не устранён."
                : f.Sev == 1 ? "Значительный: влияет на качество и долговечность — устранить до сдачи этапа, иначе дороже переделывать."
                : "Малозначительный: на прочность и сроки не влияет — устраняется в общем порядке."));
            var b = Widgets.Btn("Показать на модели", () => SelectDef(defSel, true), "small"); b.style.marginTop = 10; b.style.alignSelf = Align.FlexStart; defCard.Add(b);
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
    }
}
