using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>"Экономика": the macro-economy of the city in year N from the twin's own data (CityEconomy) — gross regional product by
    /// sector, the construction industry (ПГС), the city budget (own revenues, spending, transfers), investment, wages and labour,
    /// and the production capacity of the large companies with their load in the year.</summary>
    public class EconomyModule : TwinModuleBase
    {
        public override string Id => "economy";
        public override string TabKey => "tab_economy";
        public override (Color, string)[] Legend => new[]
        {
            (CityEconomy.SectorColors[0], "деловые услуги"), (CityEconomy.SectorColors[1], "социальная сфера"), (CityEconomy.SectorColors[2], "промышленность"),
            (CityEconomy.SectorColors[3], "туризм"), (CityEconomy.SectorColors[4], "строительство (ПГС)")
        };

        Label eyebrow, summary, pgsNote, budgetNote, laborNote; readonly Label[] kv = new Label[4], kl = new Label[4]; readonly VisualElement[] kb = new VisualElement[4];
        TwinChart grpChart, budChart; VisualElement pgsFacts, revRows, expRows, capRows, laborFacts;

        protected override void Build()
        {
            var top = Widgets.Block(panel);
            eyebrow = Widgets.Eyebrow(top, "");
            summary = new Label(); summary.AddToClassList("summary"); summary.style.marginBottom = 10; top.Add(summary);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid); VisualElement row = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { row = new VisualElement(); row.AddToClassList("kpi-row"); grid.Add(row); }
                var k = new VisualElement(); k.AddToClassList("kpi");
                kl[i] = new Label(); kl[i].AddToClassList("l"); k.Add(kl[i]); kv[i] = new Label("—"); kv[i].AddToClassList("v"); k.Add(kv[i]);
                kb[i] = k; row.Add(k);
            }

            var g = Widgets.Block(panel, "ВРП по отраслям", "трлн ₸");
            grpChart = new TwinChart { Colors = CityEconomy.SectorColors, Stacked = true }; g.Add(grpChart);
            var legend = new VisualElement(); legend.AddToClassList("legend"); g.Add(legend);
            for (int c = 0; c < CityEconomy.Sectors.Length; c++) legend.Add(Widgets.LegendItem(CityEconomy.SectorColors[c], CityEconomy.Sectors[c]));

            var pb = Widgets.Block(panel, "ПГС — строительная отрасль", "");
            pgsFacts = new VisualElement(); pb.Add(pgsFacts);
            pgsNote = new Label(); pgsNote.AddToClassList("note"); pgsNote.style.marginTop = 6; pb.Add(pgsNote);

            Right();
            var bb = Widgets.Block(panel, "Бюджет города", "млрд ₸ в год");
            budChart = new TwinChart { Colors = new[] { new Color(0.31f, 0.82f, 0.48f), new Color(1f, 0.45f, 0.38f) }, Stacked = false, LineWidths = new[] { 2.5f, 2f } }; bb.Add(budChart);
            var bl = new VisualElement(); bl.AddToClassList("legend"); bb.Add(bl);
            bl.Add(Widgets.LegendItem(new Color(0.31f, 0.82f, 0.48f), "собственные доходы")); bl.Add(Widgets.LegendItem(new Color(1f, 0.45f, 0.38f), "расходы"));
            var rh = new Label("Доходы"); rh.AddToClassList("eco-h"); rh.style.marginTop = 8; bb.Add(rh);
            revRows = new VisualElement(); bb.Add(revRows);
            var eh = new Label("Расходы"); eh.AddToClassList("eco-h"); eh.style.marginTop = 10; bb.Add(eh);
            expRows = new VisualElement(); bb.Add(expRows);
            budgetNote = new Label(); budgetNote.AddToClassList("note"); budgetNote.style.marginTop = 8; bb.Add(budgetNote);

            var cb = Widgets.Block(panel, "Производственные мощности", "");
            capRows = new VisualElement(); cb.Add(capRows);

            var lb = Widgets.Block(panel, "Рынок труда и доходы", "");
            laborFacts = new VisualElement(); lb.Add(laborFacts);
            laborNote = new Label(); laborNote.AddToClassList("note"); laborNote.style.marginTop = 6; lb.Add(laborNote);
            Widgets.SetCollapsed(lb, true);

            var n = Widgets.Block(panel);
            var note = new Label("Модель двойника, не официальная статистика: ВРП = рабочие места по зданиям × выработка отрасли (Алматы ≈ 23 млн ₸ на занятого) + стройка по деньгам finance.json; бюджет — налоги с фонда оплаты труда, прибыли и имущества. Цены 2026 года, $1 = 500 ₸.");
            note.AddToClassList("note"); n.Add(note);
        }

        public override void Refresh()
        {
            if (panel == null || summary == null || !CityEconomy.Ready) return;
            int y = TwinState.Year; var e = CityEconomy.Of(y);
            eyebrow.text = ("Экономика · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            int big = 0; for (int i = 1; i < 6; i++) if (e.Grp[i] > e.Grp[big]) big = i;
            int self = CityEconomy.SelfSufficientYear();
            summary.text = $"ВРП Alatau City в {y} году — {CityEconomy.Trln(e.GrpTotal)} ({CityEconomy.Usd(e.GrpTotal)}), {Loc.N0(e.GrpPerCapitaUsd)} $ на жителя. Крупнейшая отрасль — {CityEconomy.SectorsInText[big]} ({Mathf.RoundToInt(100f * e.Grp[big] / Mathf.Max(e.GrpTotal, 1f))} %)."
                + (self > 0 ? $" Свои доходы города покрывают все его расходы с {self} года." : "");
            Set(0, CityEconomy.Trln(e.GrpTotal), "ВРП города", "");
            Set(1, "$" + Loc.N0(e.GrpPerCapitaUsd), "ВРП на жителя", "");
            Set(2, (e.GrpGrowth >= 0 ? "+" : "") + Loc.N1(e.GrpGrowth) + " %", "рост ВРП за год, реальный", e.GrpGrowth < 0 ? "warn" : "ok");
            Set(3, CityEconomy.Trln(e.Capex), "инвестиции в стройку · частные " + Mathf.RoundToInt(100f * e.CapexPrivate / Mathf.Max(e.Capex, 1f)) + " %", "");

            // GRP chart, trillions
            var ser = new float[6][]; for (int c = 0; c < 6; c++) ser[c] = new float[CityStats.Years];
            for (int i = 0; i < CityStats.Years; i++) { var ei = CityEconomy.Of(TwinState.MinYear + i); for (int c = 0; c < 6; c++) ser[c][i] = ei.Grp[c] / 1000f; }
            grpChart.Series = ser; grpChart.MarkYear = y; grpChart.Refresh();

            // ПГС
            pgsFacts.Clear();
            pgsFacts.Add(Widgets.Fact("Объём строительных работ", CityEconomy.Trln(e.ConstrOutput) + " · " + CityEconomy.Usd(e.ConstrOutput)));
            pgsFacts.Add(Widgets.Fact("Доля стройки в ВРП", Mathf.RoundToInt(100f * e.Grp[4] / Mathf.Max(e.GrpTotal, 1f)) + " %"));
            pgsFacts.Add(Widgets.Fact("Занято в стройке", "≈ " + Loc.N0(e.ConstrJobs / 1000f) + " тыс. человек"));
            pgsFacts.Add(Widgets.Fact("Ввод жилья за год", Loc.N0(e.HousingM2 / 1000f) + " тыс. м²"));
            var last = Widgets.Fact("Кто платит", "частные и ГЧП " + Mathf.RoundToInt(100f * e.CapexPrivate / Mathf.Max(e.Capex, 1f)) + " % · бюджет и квазигоссектор " + Mathf.RoundToInt(100f * e.CapexBudget / Mathf.Max(e.Capex, 1f)) + " %");
            last.style.borderBottomWidth = 0; pgsFacts.Add(last);
            float sum = 0; for (int i = 0; i < CityStats.Years; i++) sum += CityEconomy.Of(TwinState.MinYear + i).Capex;
            pgsNote.text = $"За 2026–2050 в стройку города вкладывается {CityEconomy.Trln(sum)} ({CityEconomy.Usd(sum)}). В первые годы стройка — основа экономики города, к 2040-м её доля падает: город начинает зарабатывать сам.";

            // budget
            var inc = new float[CityStats.Years]; var exp = new float[CityStats.Years];
            for (int i = 0; i < CityStats.Years; i++) { var ei = CityEconomy.Of(TwinState.MinYear + i); inc[i] = ei.RevOwn; exp[i] = ei.Opex + ei.BudgetCapex; }
            budChart.Series = new[] { inc, exp }; budChart.MarkYear = y; budChart.Refresh();
            revRows.Clear(); float rmax = e.Rev.Max();
            for (int i = 0; i < e.Rev.Length; i++) revRows.Add(Bar(CityEconomy.Revenue[i], e.Rev[i], rmax, new Color(0.31f, 0.82f, 0.48f)));
            expRows.Clear();
            float[] ex = e.Exp.Concat(new[] { e.BudgetCapex }).ToArray(); string[] en = CityEconomy.Spend.Concat(new[] { "Развитие: школы, сети, дороги" }).ToArray(); float emax = ex.Max();
            for (int i = 0; i < ex.Length; i++) expRows.Add(Bar(en[i], ex[i], emax, new Color(1f, 0.45f, 0.38f)));
            budgetNote.text = e.Balance < 0
                ? $"Свои доходы {Loc.N0(e.RevOwn)} млрд ₸ против расходов {Loc.N0(e.Opex + e.BudgetCapex)} млрд ₸: разрыв {Loc.N0(e.Transfers)} млрд ₸ закрывают целевые трансферты республики на инфраструктуру."
                : $"Свои доходы {Loc.N0(e.RevOwn)} млрд ₸ покрывают расходы {Loc.N0(e.Opex + e.BudgetCapex)} млрд ₸; излишек {Loc.N0(e.ToRepublic)} млрд ₸ уходит в республиканский бюджет. Налоговая нагрузка — {Mathf.RoundToInt(e.TaxBurden * 100f)} % ВРП.";

            // production capacity
            capRows.Clear(); var sys = LandmarkSystem.Instance;
            if (sys != null)
                foreach (var c in LandmarkCapacity.Items.Where(c => c.Industrial).OrderByDescending(c => c.RevenueUsdM))
                {
                    var l = sys.Get(c.Id); if (l == null) continue;
                    capRows.Add(CapRow(l, c, y));
                }
            var tot = new Label($"Крупные заводы и хабы в {y} году: выручка ≈ ${Loc.N0(e.IndustryOutputUsdM)} млн, экспорт ≈ ${Loc.N0(e.ExportUsdM)} млн."); tot.AddToClassList("note"); tot.style.marginTop = 6; capRows.Add(tot);

            // labour
            laborFacts.Clear();
            laborFacts.Add(Widgets.Fact("Жителей", Loc.N0(e.Residents / 1000f) + " тыс."));
            laborFacts.Add(Widgets.Fact("Рабочих мест", Loc.N0(e.Jobs / 1000f) + " тыс."));
            laborFacts.Add(Widgets.Fact("Средняя зарплата", Loc.N0(e.AvgWage) + " тыс. ₸ в месяц"));
            var cm = Widgets.Fact("Приезжают на работу", "≈ " + Loc.N0(e.Commuters / 1000f) + " тыс. человек в день"); cm.style.borderBottomWidth = 0; laborFacts.Add(cm);
            laborNote.text = e.Commuters > 1000f ? "Рабочих мест больше, чем работающих жителей: люди едут из Алматы и Конаева — нужна ЛРТ и жильё рядом с работой." : "Рабочих мест хватает жителям города.";
            TwinUI.Instance?.FillLegend(Legend);
        }

        /// <summary>A company: capacity, output in the year, load bar.</summary>
        public static VisualElement CapRow(Landmark l, LandmarkCapacity.Cap c, int y)
        {
            float load = LandmarkCapacity.Load(l, y), cap = LandmarkCapacity.CapacityAt(l, c, y);
            var r = new VisualElement(); r.AddToClassList("story-row"); r.AddToClassList("clickable"); r.style.marginTop = 8;
            var rt = new VisualElement(); rt.AddToClassList("story-rtop"); r.Add(rt);
            var chip = new VisualElement(); chip.AddToClassList("story-chip"); chip.style.backgroundColor = l.District >= 0 ? CityStats.DistrictColors[l.District] : Color.white; rt.Add(chip);
            var nm = new Label(l.Short + " · " + c.Product); nm.AddToClassList("story-rn"); rt.Add(nm);
            var v = new Label(LandmarkCapacity.Fmt(cap, c.Unit)); v.AddToClassList("story-rv"); rt.Add(v);
            var bar = new VisualElement(); bar.AddToClassList("story-bar"); var fill = new VisualElement(); fill.AddToClassList("story-fill");
            fill.style.backgroundColor = load >= 0.8f ? new Color(0.31f, 0.82f, 0.48f) : load > 0f ? new Color(0.96f, 0.65f, 0.14f) : new Color(0.35f, 0.35f, 0.35f);
            fill.style.width = Length.Percent(load * 100f); bar.Add(fill); r.Add(bar);
            var s = new Label(load > 0f ? $"загрузка {Mathf.RoundToInt(load * 100f)} % · выпуск {LandmarkCapacity.Fmt(cap * load, c.Unit)}" + (c.Jobs > 0 ? $" · {Loc.N0(c.Jobs)} мест" : "") : $"запуск в {l.EndYear}" + (c.Jobs > 0 ? $" · {Loc.N0(c.Jobs)} мест" : ""));
            s.AddToClassList("note"); s.style.marginLeft = 17; s.style.marginTop = 2; r.Add(s);
            r.AddManipulator(new Clickable(() => LandmarkSystem.Instance?.Select(l)));
            return r;
        }

        static VisualElement Bar(string name, float v, float max, Color c)
        {
            var r = new VisualElement(); r.AddToClassList("story-row");
            var rt = new VisualElement(); rt.AddToClassList("story-rtop"); r.Add(rt);
            var chip = new VisualElement(); chip.AddToClassList("story-chip"); chip.style.backgroundColor = c; rt.Add(chip);
            var l = new Label(name); l.AddToClassList("story-rn"); rt.Add(l);
            var vl = new Label(Loc.N0(v)); vl.AddToClassList("story-rv"); rt.Add(vl);
            var bar = new VisualElement(); bar.AddToClassList("story-bar"); var fill = new VisualElement(); fill.AddToClassList("story-fill"); fill.style.backgroundColor = c;
            fill.style.width = Length.Percent(max > 0 ? Mathf.Clamp01(v / max) * 100f : 0f); bar.Add(fill); r.Add(bar);
            return r;
        }

        void Set(int i, string v, string l, string cls)
        {
            kv[i].text = v; kl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) kb[i].RemoveFromClassList(c);
            if (cls != "") kb[i].AddToClassList(cls);
        }
    }
}
