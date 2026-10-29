using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using DSrcA = AlatauCity.DigitalTwin.Data.Sources;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The «Аналитика» page of the construction monitoring: one sentence with the main thing first, then the money and the dates in
    /// five tiles, then what needs attention (most serious first) — every finding with the places in the documents it follows from and a way
    /// to see it on the site; three views — Сводка, Смета (the cost items, how the forecast is made, the prices), Документы (by importance).
    /// A document opens as a sheet of paper over the right of the page, scrolled to the place, the place marked.</summary>
    public partial class IconicMonitor
    {
        const int TAn = 5;
        VisualElement anPage, anSumV, anCostV, anDocsV, anViewer, anPaper, anCostRows, anDetail, anCtx;
        ScrollView anPaperScroll;
        Label anVTitle, anVNo, anVKind, anVCtx, anVNav;
        readonly List<Button> anTabs = new List<Button>(), anPartBtns = new List<Button>();
        int anView, anItem = -1, anPart = -1, anDoc = -1, anRefAt = -1;
        readonly List<VisualElement> anRefEls = new List<VisualElement>();
        static readonly string[] SevName = { "В норме", "К сведению", "Важно", "Критично" };
        static readonly string[] SevCls = { "s-ok", "s-info", "s-warn", "s-bad" };
        static Color SevColor(int s) => s >= 2 ? new Color(1f, 0.35f, 0.31f) : s == 1 ? new Color(0.96f, 0.65f, 0.14f) : s == 0 ? new Color(0.48f, 0.65f, 1f) : new Color(0.20f, 0.78f, 0.35f);
        bool AnDocOpen => anViewer != null && anViewer.style.display == DisplayStyle.Flex;

        static VisualElement Box(VisualElement parent, string cls, bool pick = true)
        {
            var e = new VisualElement(); if (!pick) e.pickingMode = PickingMode.Ignore;
            foreach (var c in cls.Split(' ')) if (c.Length > 0) e.AddToClassList(c);
            parent.Add(e); return e;
        }
        static Label Txt(VisualElement parent, string text, string cls)
        {
            var l = new Label(text) { pickingMode = PickingMode.Ignore };
            foreach (var c in cls.Split(' ')) if (c.Length > 0) l.AddToClassList(c);
            parent.Add(l); return l;
        }
        static ScrollView Scroll(VisualElement parent, string cls)
        {
            var s = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden, mouseWheelScrollSize = 60f };
            s.AddToClassList("an-scroll"); foreach (var c in cls.Split(' ')) if (c.Length > 0) s.AddToClassList(c);
            parent.Add(s); return s;
        }
        static void Spacer(VisualElement parent) { var s = new VisualElement { pickingMode = PickingMode.Ignore }; s.style.flexGrow = 1; parent.Add(s); }

        // ================================================================== the page
        void BuildAnalytics()
        {
            anTabs.Clear(); anPartBtns.Clear(); anRefEls.Clear(); anDoc = -1;
            anPage = Box(body, "an-page");
            var head = Box(anPage, "an-head");
            head.Add(TwinUI.Icon("gauge", 20));
            var tb = Box(head, "an-titles", false);
            Txt(tb, "Аналитика строительства · " + L.Short, "an-h1");
            Txt(tb, $"на {Day(Report)} — по последней съёмке, актам и ценам на эту дату · сценарий цифрового двойника", "mon-src");
            var seg = Box(head, "mon-seg"); seg.style.marginLeft = 22;
            foreach (var (txt, k) in new[] { ("Сводка", 0), ("Смета", 1), ($"Документы · {docs.Count}", 2) })
            { int kk = k; var b = Widgets.Btn(txt, () => AnView(kk), "small"); b.AddToClassList("an-tab"); seg.Add(b); anTabs.Add(b); }
            Spacer(head);
            var sl = SourceTags.Line(DSrcA.OlxPrices, DSrcA.NbrkRate, SrcMon); sl.style.marginLeft = 12; sl.style.flexShrink = 0; head.Add(sl);

            // the main thing, in one sentence
            int worstSev = finds.Count > 0 ? finds[0].Sev : -1;
            var vb = Box(anPage, "an-verdict " + SevCls[Mathf.Clamp(worstSev + 1, 0, 3)]);
            Txt(vb, $"Главное на {Day(Report)}", "an-verdict-k");
            Txt(vb, Verdict(), "an-verdict-t");

            anSumV = Box(anPage, "an-view"); BuildAnSummary(anSumV);
            anCostV = Box(anPage, "an-view"); BuildAnCost(anCostV);
            anDocsV = Box(anPage, "an-view"); BuildAnDocs(anDocsV);
            BuildViewer();
            AnView(0);
        }
        /// <summary>The main thing: the money, the dates, the people — what a customer asks first.</summary>
        string Verdict()
        {
            var s = new List<string>();
            float over = anTot.Over;
            s.Add(NetOver > 0f ? $"прогноз стоимости {Mln(anTot.Eac)} — выше бюджета на {Mln(over)} ({SPc(over / anTot.B)}), резерва не хватает"
                : over > 0f ? $"прогноз стоимости {Mln(anTot.Eac)} — выше бюджета на {Mln(over)}, пока покрывается резервом"
                : $"прогноз стоимости {Mln(anTot.Eac)} — в бюджете");
            if (anWorst >= 0) { var o = Obj(anWorst, Report); s.Add(o.EndDays > 3 ? $"{Pt(anWorst).Name} отстаёт на {o.Days} дн., ввод сдвигается на {o.EndDays} дн." : $"{Pt(anWorst).Name} отстаёт на {o.Days} дн., к вводу отставание закрывается"); }
            else s.Add("все объекты в графике");
            if (anCrew >= 0) { Sum(trades[anCrew], out int need, out int have); s.Add($"на площадке не хватает {Loc.N0(need - have)} человек"); }
            var t = string.Join("; ", s); if (!t.EndsWith(".")) t += ".";
            return char.ToUpper(t[0]) + t.Substring(1);
        }
        void AnView(int v)
        {
            anView = v;
            for (int i = 0; i < anTabs.Count; i++) anTabs[i].EnableInClassList("active", i == v);
            Vis(anSumV, v == 0); Vis(anCostV, v == 1); Vis(anDocsV, v == 2);
            if (v == 1) { if (anItem < 0) anItem = TopOver() >= 0 ? TopOver() : 1; FillCost(); }
            CloseDoc();
        }

        // ------------------------------------------------------------------ Сводка
        void BuildAnSummary(VisualElement v)
        {
            // five numbers: the budget, spent, still needed, the forecast, the completion
            var kr = Box(v, "an-kpis");
            var last = 0; for (int i = 1; i < L.Parts.Count; i++) if (Obj(i, Report).FactEnd > Obj(last, Report).FactEnd) last = i;
            int ld = Mathf.RoundToInt((Obj(last, Report).FactEnd - L.Finish) * 365f);
            float over = anTot.Over;
            AnK(kr, "Бюджет", Mln(anTot.B), $"+ резерв 4 % · {Mln(anRes)}", "", () => { anItem = -1; AnView(1); });
            var spent = AnK(kr, "Потрачено", Mln(anTot.Ac), $"{Pct(anTot.Ac / anTot.B)} бюджета · работ на {Mln(anTot.Ev)} в ценах сметы", "", () => OpenDoc(DK, "rTot", null));
            var bar = Box(spent, "mon-bar", false); bar.style.marginTop = 6; var fl = Box(bar, "mon-fill", false); fl.style.width = Length.Percent(Mathf.Clamp01(anTot.Ac / anTot.B) * 100f);
            AnK(kr, "Нужно ещё", Mln(anTot.Etc + anTot.Extra), $"на оставшиеся {Pct(1f - anTot.Q)} работ — по ценам на {Day(Report)}", "", () => OpenDoc(DP, "r0", null));
            AnK(kr, "Прогноз итоговой стоимости", Mln(anTot.Eac), over > 0f ? $"{SMln(over)} к бюджету ({SPc(over / anTot.B)}) · " + (NetOver > 0f ? $"сверх резерва {Mln(NetOver)}" : $"резерв покрывает") : $"экономия {Mln(-over)}", CostCls, () => { anItem = TopOver(); AnView(1); });
            AnK(kr, "Завершение комплекса", IconicFloors.MonthYear(Obj(last, Report).FactEnd), ld > 3 ? $"позже плана на {ld} дн. · {Pt(last).Short}" : $"в срок · план {IconicFloors.MonthYear(L.Finish)}", ld > 21 ? "bad" : ld > 3 ? "warn" : "ok", () => SetTab(TInv));

            var row = Box(v, "an-row");
            // left: what needs attention, the most serious first
            var lc = Box(row, "an-colL");
            var lh = Box(lc, "an-sec", false); lh.Add(TwinUI.Icon("triangle_alert", 16));
            int nb = 0, nw = 0; foreach (var f in finds) { if (f.Sev >= 2) nb++; else if (f.Sev == 1) nw++; }
            Txt(lh, "Требует внимания", "mon-title"); Spacer(lh);
            if (nb > 0) Txt(lh, $"{nb} критично", "an-count s-bad");
            if (nw > 0) Txt(lh, $"{nw} важно", "an-count s-warn");
            Txt(lc, "У каждого вывода — ссылки на места в документах, откуда он следует, и где это видно на площадке.", "mon-src an-hint");
            var fs = Scroll(lc, "an-flist");
            foreach (var f in finds) FindCard(fs, f);

            // right: where the money goes, the key documents
            var rc = Box(row, "an-colR");
            var mc = Box(rc, "mon-card an-card");
            Head(mc, "wallet", "Где меняется стоимость");
            Txt(mc, "прогноз к бюджету по статьям сметы", "mon-src");
            var ord = new List<int>(); for (int k = 0; k < Items.Length; k++) if (ItemCost(k, -1).B > 0f) ord.Add(k);
            ord.Sort((a, b) => Mathf.Abs(ItemCost(b, -1).Over).CompareTo(Mathf.Abs(ItemCost(a, -1).Over)));
            for (int j = 0; j < ord.Count && j < 6; j++) ItemBar(mc, ord[j]);
            var all = Widgets.Btn("Вся смета", () => { anItem = -1; AnView(1); }, "small"); all.style.marginTop = 8; all.style.alignSelf = Align.FlexStart; mc.Add(all);

            var dc = Box(rc, "mon-card an-card");
            Head(dc, "files", "Ключевые документы");
            Txt(dc, "по важности: вес документа и выводы, которые на него ссылаются", "mon-src");
            var ds = new List<Doc>(docs); ds.Sort((a, b) => b.Score.CompareTo(a.Score));
            for (int j = 0; j < ds.Count && j < 5; j++) DocRow(dc, ds[j], true);
            var ad = Widgets.Btn($"Все документы · {docs.Count}", () => AnView(2), "small"); ad.style.marginTop = 8; ad.style.alignSelf = Align.FlexStart; dc.Add(ad);
        }
        VisualElement AnK(VisualElement parent, string cap, string val, string sub, string cls, Action click)
        {
            var b = new Button(click) { focusable = false }; b.AddToClassList("an-k"); if (cls.Length > 0) b.AddToClassList("k-" + cls); parent.Add(b);
            Txt(b, cap, "mon-inv-cap"); var v = Txt(b, val, "an-k-v"); if (cls.Length > 0) v.AddToClassList(cls); Txt(b, sub, "mon-inv-sub");
            return b;
        }
        /// <summary>A finding: what, why, the places in the documents, where to see it.</summary>
        void FindCard(VisualElement parent, Finding f)
        {
            var c = Box(parent, "an-f " + SevCls[Mathf.Clamp(f.Sev + 1, 0, 3)]);
            var top = Box(c, "an-f-top", false);
            var ic = TwinUI.Icon(f.Icon, 16); ic.style.unityBackgroundImageTintColor = SevColor(f.Sev); ic.style.flexShrink = 0; top.Add(ic);
            Txt(top, f.Title, "an-f-t");
            Txt(top, SevName[Mathf.Clamp(f.Sev + 1, 0, 3)], "an-tag " + SevCls[Mathf.Clamp(f.Sev + 1, 0, 3)]);
            if (!string.IsNullOrEmpty(f.Text)) Txt(c, f.Text, "an-f-x");
            var sr = Box(c, "an-f-src");
            Txt(sr, "Почему так:", "an-why");
            foreach (var s in f.Src) sr.Add(DocChip(s, f));
            if (f.Show != null)
            {
                Spacer(sr);
                var g = new Button(f.Show) { focusable = false }; g.AddToClassList("an-go");
                g.Add(new Label(f.ShowText) { pickingMode = PickingMode.Ignore }); g.Add(TwinUI.Icon("arrow_right", 12)); sr.Add(g);
            }
        }
        Button DocChip(Src s, Finding f)
        {
            var b = new Button(() => OpenDoc(s.Doc, s.At, f)) { focusable = false }; b.AddToClassList("an-chip");
            b.Add(TwinUI.Icon(docs[s.Doc].Icon, 12)); b.Add(new Label(s.Label) { pickingMode = PickingMode.Ignore });
            return b;
        }
        /// <summary>An item of the estimate as a bar: spent (blue) and the rest (grey) of its forecast against the budget (the white mark).</summary>
        void ItemBar(VisualElement parent, int k)
        {
            var ic = ItemCost(k, -1);
            var r = new Button(() => { anItem = k; AnView(1); }) { focusable = false }; r.AddToClassList("an-ib"); parent.Add(r);
            var t = Box(r, "an-ib-top", false);
            Txt(t, Items[k].Name, "an-ib-n");
            var dl = Txt(t, SMln(ic.Over), "an-ib-d"); dl.AddToClassList(ic.Over > ic.B * 0.02f ? "bad" : ic.Over > 0f ? "warn" : "ok");
            BudgetBar(r, ic);
        }
        static void BudgetBar(VisualElement parent, Cost ic)
        {
            float mx = Mathf.Max(ic.B, ic.Eac) * 1.02f;
            var bar = Box(parent, "an-bb", false);
            var a = Box(bar, "an-bb-ac", false); a.style.width = Length.Percent(ic.Ac / mx * 100f);
            float mid = Mathf.Max(Mathf.Min(ic.Eac, ic.B), ic.Ac);                     // the rest up to the budget grey, beyond it red
            var e = Box(bar, "an-bb-etc", false); e.style.left = Length.Percent(ic.Ac / mx * 100f); e.style.width = Length.Percent((mid - ic.Ac) / mx * 100f);
            if (ic.Eac > mid) { var o = Box(bar, "an-bb-over", false); o.style.left = Length.Percent(mid / mx * 100f); o.style.width = Length.Percent((ic.Eac - mid) / mx * 100f); }
            var m = Box(bar, "an-bb-b", false); m.style.left = Length.Percent(ic.B / mx * 100f);
        }
        void DocRow(VisualElement parent, Doc d, bool compact)
        {
            var r = new Button(() => OpenDoc(d.Ix, null, null)) { focusable = false }; r.AddToClassList("an-doc"); if (compact) r.AddToClassList("compact"); parent.Add(r);
            var ib = Box(r, "an-doc-ic", false); ib.Add(TwinUI.Icon(d.Icon, compact ? 14 : 16));
            var tx = Box(r, "an-doc-tx", false);
            Txt(tx, d.Title, "an-doc-t");
            Txt(tx, d.Kind + " · " + d.No + " · " + d.Date, "mon-src");
            if (d.Refs > 0) Txt(r, d.Refs + " " + Refs(d.Refs), "an-doc-refs");
            if (!compact)
            {
                var st = Box(r, "an-stars", false);
                int lv = d.Score >= 85 ? 3 : d.Score >= 55 ? 2 : 1;
                for (int i = 0; i < 3; i++) Box(st, "an-star" + (i < lv ? " on" : ""), false);
            }
        }
        static string Refs(int n) { int m = n % 100, d = n % 10; return m >= 11 && m <= 14 ? "ссылок" : d == 1 ? "ссылка" : d >= 2 && d <= 4 ? "ссылки" : "ссылок"; }

        // ------------------------------------------------------------------ Смета
        void BuildAnCost(VisualElement v)
        {
            var tb = Box(v, "an-tools");
            var seg = Box(tb, "mon-seg");
            for (int i = -1; i < L.Parts.Count; i++)
            { int k = i; var b = Widgets.Btn(i < 0 ? "Весь комплекс" : Pt(i).Short, () => { anPart = k; FillCost(); }, "small"); seg.Add(b); anPartBtns.Add(b); }
            Spacer(tb);
            tb.Add(Widgets.LegendItem(Blue, "потрачено")); tb.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.28f), "нужно ещё"));
            tb.Add(Widgets.LegendItem(new Color(1f, 0.35f, 0.31f), "сверх бюджета")); tb.Add(Widgets.LegendItem(Color.white, "бюджет"));

            var row = Box(v, "an-row");
            var lc = Box(row, "an-colL");
            var tab = Box(lc, "an-ctab");
            var th = Box(tab, "an-ctr an-cth", false);
            foreach (var (c, cls) in new[] { ("Статья затрат", "n"), ("Бюджет", "m"), ("Потрачено", "m"), ("Прогноз", "m"), ("Отклонение", "w"), ("", "bar") }) Txt(th, c, "an-ctd " + cls);
            anCostRows = Scroll(tab, "an-crows");
            // the prices of the resources
            var pc = Box(lc, "mon-card an-card an-prices");
            var ph = Box(pc, "an-sec", false); ph.Add(TwinUI.Icon("coins", 16)); Txt(ph, $"Цены на основные ресурсы · {Day(Report)}", "mon-title"); Spacer(ph);
            ph.Add(DocChip(At(DP, "r0", "ведомость"), null));
            var pt = Box(pc, "an-ptab", false);
            var phr = Box(pt, "an-ptr an-cth", false);
            foreach (var (c, cls) in new[] { ("Ресурс", "n"), ("В смете", "m"), ("Сейчас", "m"), ("Изменение", "s"), ("Цена в смете", "w7-src") }) Txt(phr, c, "an-ctd " + cls);
            for (int r = 0; r < Rsc.Length; r++)
            {
                float now = PriceAt(r, Report), dp = now / Rsc[r].Base - 1f;
                var pr = Box(pt, "an-ptr", false);
                Txt(pr, Rsc[r].Name + (Rsc[r].Unit == "индекс" ? "" : ", " + Rsc[r].Unit), "an-ctd n");
                Txt(pr, PriceText(r, Rsc[r].Base), "an-ctd m"); Txt(pr, PriceText(r, now), "an-ctd m");
                var dd = Txt(pr, SPc(dp), "an-ctd s"); dd.AddToClassList(dp > 0.15f ? "bad" : dp > 0.05f ? "warn" : "ok");
                var sc = Box(pr, "an-ctd w7-src", false); sc.Add(SourceTags.Tag(Rsc[r].Open ?? SrcPrices));
            }
            Txt(pc, "Цена в смете: синие метки — открытые данные (объявления olx.kz, курс НБ РК), жёлтые — допущение модели. Рост цен до даты съёмки — всегда допущение модели.", "mon-src w7-pnote");
            // right: how the forecast of the item is made
            anDetail = Scroll(row, "an-colR an-detail");
        }
        void FillCost()
        {
            if (anCostRows == null) return;
            for (int i = 0; i < anPartBtns.Count; i++) anPartBtns[i].EnableInClassList("active", i - 1 == anPart);
            anCostRows.Clear();
            for (int k = 0; k < Items.Length; k++)
            {
                var ic = ItemCost(k, anPart); if (ic.B <= 0f) continue;
                int kk = k; var r = new Button(() => { anItem = kk; FillCost(); }) { focusable = false }; r.AddToClassList("an-ctr"); if (k == anItem) r.AddToClassList("sel"); anCostRows.Add(r);
                CostCells(r, (k + 1) + ". " + Items[k].Name, ic);
            }
            var tot = anPart < 0 ? anTot : PartCost(anPart);
            var tr = Box(anCostRows, "an-ctr an-ctot", false); CostCells(tr, anPart < 0 ? "Итого по статьям" : "Итого · " + Pt(anPart).Name, tot);
            if (anPart < 0)
            {
                var rr = Box(anCostRows, "an-ctr an-cres", false);
                Txt(rr, "Резерв на непредвиденные (4 %)", "an-ctd n"); Txt(rr, Mln(anRes), "an-ctd m"); Txt(rr, "", "an-ctd m"); Txt(rr, "", "an-ctd m");
                var nd = Txt(rr, NetOver > 0f ? $"не хватает {Mln(NetOver)}" : $"останется {Mln(-NetOver)}", "an-ctd w"); nd.AddToClassList(NetOver > 0f ? "bad" : "ok");
                Txt(rr, NetOver > 0f ? "нужно доп. соглашение (п. 5.5 договора)" : "перерасход по статьям покрывается резервом", "an-ctd bar an-note");
            }
            FillDetail();
        }
        void CostCells(VisualElement r, string name, Cost ic)
        {
            Txt(r, name, "an-ctd n"); Txt(r, Mln(ic.B), "an-ctd m"); Txt(r, Mln(ic.Ac), "an-ctd m"); Txt(r, Mln(ic.Eac), "an-ctd m");
            var d = Txt(r, SMln(ic.Over) + "  " + SPc(ic.Over / Mathf.Max(ic.B, 0.01f)), "an-ctd w"); d.AddToClassList(ic.Over > ic.B * 0.02f ? "bad" : ic.Over > 0f ? "warn" : "ok");
            var bc = Box(r, "an-ctd bar", false); BudgetBar(bc, ic);
        }
        /// <summary>How the forecast of the selected item is made: the budget, done, spent, the rest at today's prices, the delays; its prices.</summary>
        void FillDetail()
        {
            if (anDetail == null) return;
            anDetail.Clear();
            int k = anItem; if (k < 0 || ItemCost(k, anPart).B <= 0f) { k = -1; for (int j = 0; j < Items.Length; j++) if (ItemCost(j, anPart).B > 0f && (k < 0 || ItemCost(j, anPart).Over > ItemCost(k, anPart).Over)) k = j; }
            if (k < 0) return;
            var ic = ItemCost(k, anPart); var it = Items[k];
            var c = Box(anDetail, "mon-card an-card");
            var hh = Box(c, "an-sec", false); hh.Add(TwinUI.Icon("receipt", 16)); Txt(hh, it.Name, "mon-title");
            Txt(c, anPart < 0 ? "весь комплекс · как посчитан прогноз" : Pt(anPart).Name + " · как посчитан прогноз", "mon-src");
            var big = Box(c, "an-big", false);
            var bv = Txt(big, SMln(ic.Over), "an-big-v"); bv.AddToClassList(ic.Over > ic.B * 0.02f ? "bad" : ic.Over > 0f ? "warn" : "ok");
            Txt(big, $"{SPc(ic.Over / ic.B)} к бюджету · прогноз {Mln(ic.Eac)} при бюджете {Mln(ic.B)}", "mon-inv-sub");
            BudgetBar(c, ic);
            void Step(string n, string k2, string val, string sub, string cls = "")
            {
                var r = Box(c, "an-step", false);
                Txt(r, n, "an-step-n");
                var t = Box(r, "an-step-tx", false); Txt(t, k2, "an-step-k"); if (sub.Length > 0) Txt(t, sub, "mon-src");
                var v = Txt(r, val, "an-step-v"); if (cls.Length > 0) v.AddToClassList(cls);
            }
            float pf = PriceF(k, Report), pfA = ic.Ev > 0f ? ic.Ac / ic.Ev : 1f;
            Step("1", "Бюджет по смете", Mln(ic.B), "сводный сметный расчёт в ценах на 01.10.2026");
            Step("2", $"Выполнено {Pct(ic.Q)} объёма — потрачено", Mln(ic.Ac), ic.Ev > 0f ? $"по ценам сметы {Mln(ic.Ev)}, рост цен за время работ {SPc(pfA - 1f)}" : "работы ещё не начаты");
            Step("3", $"Остаток {Pct(1f - ic.Q)} по ценам на {Day(Report)}", Mln(ic.Etc), $"{Mln(ic.B * (1f - ic.Q))} × индекс цен {pf.ToString("N3", Loc.Ru)}");
            if (ic.Extra > 0.05f) Step("4", "Сроки дольше графика", "+" + Mln(ic.Extra), it.Time ? "техника, площадка и управление оплачиваются дольше" : "сверхурочные второй смены", "warn");
            Step("=", "Прогноз итоговой стоимости", Mln(ic.Eac), "", ic.Over > ic.B * 0.02f ? "bad" : ic.Over > 0f ? "warn" : "ok");

            var pc = Box(anDetail, "mon-card an-card");
            var ph = Box(pc, "an-sec", false); ph.Add(TwinUI.Icon("coins", 16)); Txt(ph, "Цены ресурсов статьи", "mon-title");
            Txt(pc, $"по фиксированной цене закуплено {Mathf.RoundToInt(FixedOf(k) * 100f)} % объёма — эта доля не дорожает", "mon-src");
            for (int j = 0; j < it.R.Length; j++)
            {
                int r = it.R[j]; float now = PriceAt(r, Report), dp = now / Rsc[r].Base - 1f;
                var pr = Box(pc, "an-res", false);
                var tx = Box(pr, "an-res-tx", false); var rn = Box(tx, "mon-row w7-resn", false); Txt(rn, Rsc[r].Name, "an-res-n"); rn.Add(SourceTags.Tag(Rsc[r].Open ?? SrcPrices));
                Txt(tx, $"доля в статье {Mathf.RoundToInt(it.W[j] * 100f)} % · {Rsc[r].Src} · рост {Loc.N1(Rsc[r].Growth * 100f)} % в год — допущение модели", "mon-src");
                var pv = Box(pr, "an-res-v", false); Txt(pv, PriceText(r, Rsc[r].Base) + " → " + PriceText(r, now), "an-res-p");
                var dd = Txt(pv, SPc(dp), "an-res-d"); dd.AddToClassList(dp > 0.15f ? "bad" : dp > 0.05f ? "warn" : "ok");
            }
            var sc = Box(anDetail, "mon-card an-card");
            var sh = Box(sc, "an-sec", false); sh.Add(TwinUI.Icon("files", 16)); Txt(sh, "Откуда цифры", "mon-title");
            var chips = Box(sc, "an-f-src");
            chips.Add(DocChip(At(DS, "r" + k, $"строка {k + 1}"), null));
            foreach (int r in it.R) chips.Add(DocChip(At(DP, "r" + r, $"поз. {r + 1}"), null));
            if (ic.Ac > 0f) chips.Add(DocChip(At(DK, "r" + k, $"строка {k + 1}"), null));
            chips.Add(DocChip(k == 4 ? At(DF, "p3.1", "п. 3.1") : At(DC, "p5.4", "п. 5.4"), null));
            BuildAssumptions(anDetail);
        }

        /// <summary>The assumptions of the model behind the estimate, each in one line, under one model chip.</summary>
        void BuildAssumptions(VisualElement parent)
        {
            var c = Box(parent, "mon-card an-card w7-assume");
            var h = Box(c, "an-sec", false); h.Add(TwinUI.Icon("sparkles", 16)); Txt(h, "Допущения модели", "mon-title"); Spacer(h); h.Add(SourceTags.ModelTag(SrcPrices));
            Txt(c, "чего нет в открытых данных — принято моделью и заменяется данными заказчика", "mon-src");
            bool kaist = L != null && L.Id == "kaist";
            foreach (var (k, t) in new[]
            {
                ("Фасадные модули", "245 000 ₸/м² — импортный витраж; в смете нет коммерческого предложения поставщика"),
                ("Труд и аренда крана", "2 700 ₸ за человеко-час монтажника, 7,2 млн ₸ в месяц за башенный кран с машинистом"),
                ("Отделка и благоустройство", "индексы цен, 100 = 01.10.2026: точных позиций нет до рабочей документации"),
                ("Рост цен", "от 5 до 10 % в год по ресурсам, курс доллара +5,5 % в год — от даты сметы до даты съёмки"),
                ("Фиксированная цена", kaist ? "от 20 до 90 % объёма по статьям закуплено по договорам с твёрдой ценой (кампус — на 20 п.п. больше): эта доля не дорожает" : "от 0 до 70 % объёма по статьям закуплено по договорам с твёрдой ценой: эта доля не дорожает"),
                ("Резерв", "4 % сметы на непредвиденные работы и затраты"),
                ("Вторая смена", "+25 % к оплате труда в часы второй смены, пока отставание закрывается"),
            })
            {
                var r = Box(c, "w7-as", false); Txt(r, k, "w7-as-k"); Txt(r, t, "w7-as-t");
            }
        }

        // ------------------------------------------------------------------ Документы
        void BuildAnDocs(VisualElement v)
        {
            var row = Box(v, "an-row");
            var lc = Box(row, "an-colW");
            Txt(lc, "Все документы объекта, связанные с аналитикой, — по важности. Важность — вес документа и выводы, которые на него ссылаются. Нажмите, чтобы открыть.", "mon-src an-hint");
            var sv = Scroll(lc, "an-dlist");
            var ds = new List<Doc>(docs); ds.Sort((a, b) => b.Score.CompareTo(a.Score));
            foreach (var (name, lo, hi) in new[] { ("Ключевые", 85, 9999), ("Важные", 55, 84), ("Справочные", 0, 54) })
            {
                bool any = false;
                foreach (var d in ds) if (d.Score >= lo && d.Score <= hi) { if (!any) { var gh = Box(sv, "an-dgroup", false); Txt(gh, name, "an-dgroup-t"); any = true; } DocRow(sv, d, false); }
            }
        }

        // ------------------------------------------------------------------ the document
        void BuildViewer()
        {
            anViewer = Box(anPage, "an-viewer");
            anViewer.style.display = DisplayStyle.None;
            var dim = Box(anViewer, "an-vdim"); dim.RegisterCallback<ClickEvent>(_ => CloseDoc());
            var sheet = Box(anViewer, "an-vsheet");
            var bar = Box(sheet, "an-vbar");
            var ic = Box(bar, "an-doc-ic", false); ic.Add(TwinUI.Icon("file_text", 16));
            var tt = Box(bar, "an-vtitles", false);
            anVKind = Txt(tt, "", "mon-src"); anVTitle = Txt(tt, "", "an-vtitle"); anVNo = Txt(tt, "", "mon-src");
            Spacer(bar);
            anVNav = Txt(bar, "", "an-vnav");
            var prev = new Button(() => StepRef(-1)) { focusable = false }; prev.AddToClassList("an-vbtn"); prev.Add(TwinUI.Icon("chevron_left", 14)); bar.Add(prev);
            var next = new Button(() => StepRef(1)) { focusable = false }; next.AddToClassList("an-vbtn"); next.Add(TwinUI.Icon("chevron_right", 14)); bar.Add(next);
            var x = Widgets.Btn("×", CloseDoc, "small", "ghost"); x.style.marginLeft = 6; bar.Add(x);
            anCtx = Box(sheet, "an-vctx", false);
            anCtx.Add(TwinUI.Icon("triangle_alert", 14));
            anVCtx = Txt(anCtx, "", "an-vctx-t");
            anPaperScroll = Scroll(sheet, "an-vscroll");
            anPaper = Box(anPaperScroll, "an-paper");
        }
        /// <summary>Opens document d at place `at` (marked; the other places the analytics cites are marked lightly), from finding f.</summary>
        void OpenDoc(int d, string at, Finding f)
        {
            if (anViewer == null || d < 0 || d >= docs.Count) return;
            var doc = docs[d]; anDoc = d; anRefEls.Clear(); anRefAt = -1;
            anVKind.text = doc.Kind.ToUpper(); anVTitle.text = doc.Title; anVNo.text = doc.No + " · " + doc.Date;
            var cited = new HashSet<string>(); foreach (var fi in finds) foreach (var s in fi.Src) if (s.Doc == d && s.At != null) cited.Add(s.At);
            if (at != null) cited.Add(at);
            anPaper.Clear();
            Txt(anPaper, doc.Kind.ToUpper(), "an-pk");
            Txt(anPaper, doc.Title, "an-ph1");
            Txt(anPaper, doc.No + " · " + doc.Date, "an-pmeta");
            if (!string.IsNullOrEmpty(doc.Meta)) Txt(anPaper, doc.Meta, "an-pmeta");
            Box(anPaper, "an-prule", false);
            VisualElement target = null;
            foreach (var b in doc.B)
            {
                VisualElement e;
                if (b.Kind == "h") e = Txt(anPaper, b.Text, "an-ph2");
                else if (b.Kind == "p") { e = Box(anPaper, "an-pp an-blk", false); Txt(e, b.Text, "an-pp-t"); }
                else if (b.Kind == "sign") e = Txt(anPaper, b.Text, "an-psign");
                else
                {
                    e = Box(anPaper, "an-ptr2 an-blk" + (b.Kind == "th" ? " head" : ""), false);
                    for (int i = 0; i < b.Cells.Length; i++)
                    {
                        var l = Txt(e, b.Cells[i], "an-pc" + (i == 0 ? " first" : ""));
                        l.style.width = Length.Percent((b.Wd != null && i < b.Wd.Length ? b.Wd[i] : 1f / b.Cells.Length) * 100f);
                    }
                }
                if (b.Id != null && cited.Contains(b.Id))
                {
                    e.AddToClassList(b.Id == at ? "hl" : "ref"); anRefEls.Add(e);
                    if (b.Id == at) { target = e; anRefAt = anRefEls.Count - 1; var tag = Txt(e, "сюда ссылается аналитика", "an-hltag"); tag.style.position = Position.Absolute; }
                }
            }
            anCtx.style.display = f != null ? DisplayStyle.Flex : DisplayStyle.None;
            if (f != null) anVCtx.text = "Ссылка из вывода: " + f.Title;
            anVNav.text = anRefEls.Count > 0 ? $"связано с аналитикой: {anRefEls.Count}" : "";
            anViewer.style.display = DisplayStyle.Flex;
            anPaperScroll.scrollOffset = Vector2.zero;
            if (target != null) GoTo(target, true);
        }
        void CloseDoc() { if (anViewer != null) anViewer.style.display = DisplayStyle.None; anDoc = -1; }
        /// <summary>The next / previous place the analytics cites in the open document.</summary>
        void StepRef(int dir)
        {
            if (anRefEls.Count == 0) return;
            anRefAt = ((anRefAt < 0 ? (dir > 0 ? -1 : 0) : anRefAt) + dir + anRefEls.Count) % anRefEls.Count;
            foreach (var e in anRefEls) { e.EnableInClassList("hl", false); e.EnableInClassList("ref", true); }
            var t = anRefEls[anRefAt]; t.EnableInClassList("ref", false); t.EnableInClassList("hl", true);
            GoTo(t, true);
        }
        /// <summary>Scrolls the sheet so the place stands in the upper third, smoothly, and makes it flash once.</summary>
        void GoTo(VisualElement e, bool flash)
        {
            int tries = 0; float from = -1f;
            anPaperScroll.schedule.Execute(st =>
            {
                tries++;
                if (anPaper.layout.height < 10f || float.IsNaN(e.layout.y)) return;
                float vh = anPaperScroll.contentViewport.layout.height;
                float want = Mathf.Max(0f, anPaper.layout.y + e.layout.y - vh * 0.28f);
                if (from < 0f) { from = anPaperScroll.scrollOffset.y; if (flash) { e.AddToClassList("flash"); e.schedule.Execute(() => e.RemoveFromClassList("flash")).ExecuteLater(900); } }
                float cur = anPaperScroll.scrollOffset.y; cur += (want - cur) * 0.25f; if (Mathf.Abs(want - cur) < 1f) cur = want;
                anPaperScroll.scrollOffset = new Vector2(0f, cur);
            }).Every(16).Until(() => tries > 70 || from >= 0f && Mathf.Abs(anPaperScroll.scrollOffset.y - Mathf.Max(0f, anPaper.layout.y + e.layout.y - anPaperScroll.contentViewport.layout.height * 0.28f)) < 1f);
        }
    }
}
