using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M0 — city overview, laid out like the qTwin platform.
    /// Left: readiness meter + 4 KPI, districts as status rows. Right: journal of the year (what was built, opened, what went wrong),
    /// analytics (3 conclusions from the data) and the growth chart. District mode on row click.</summary>
    public class OverviewModule : TwinModuleBase
    {
        public override string Id => "overview";
        public override string TabKey => "tab_overview";

        Label eyebrow; VisualElement hero, bar; readonly Label[] kpiV = new Label[4];
        Label planPeople, planJobs;                 // the redrawn area of the district (shown when the map has one there)
        TwinChart chart; VisualElement distRows, journal, insights; Label journalTitle;
        int builtFor = -2;

        static readonly Color BAD = new Color(1f, 0.23f, 0.18f), WARN = new Color(0.96f, 0.65f, 0.14f), OK = new Color(0.20f, 0.78f, 0.35f);

        protected override void Build()
        {
            builtFor = TwinState.District;
            // ---------------- left: the city now
            var top = Widgets.Block(panel);
            if (TwinState.District >= 0) BuildDistrictHead(top, TwinState.District);
            // the answer first: how ready the city is in the shown year (one big number, a calm bar), then four figures
            eyebrow = Widgets.Eyebrow(top, "");
            hero = Widgets.Hero(top, "—", "%", "");
            bar = Widgets.Progress(top, 0f, "ok");
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); grid.AddToClassList("kpi-quiet"); top.Add(grid);
            string[] kl = { "Жители", "Рабочие места", "Введено площадей", "Зданий стоит" }, ku = { "тыс.", "тыс.", "млн м²", "" };
            VisualElement kRow = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { kRow = new VisualElement(); kRow.AddToClassList("kpi-row"); grid.Add(kRow); }
                kpiV[i] = Widgets.Kpi(kRow, kl[i], "—", ku[i]).Q<Label>(className: "v");
            }
            top.Add(SourceTags.Line(Sources.ModelCity, Sources.GenPlan));
            if (TwinState.District < 0)
            {
                var t = Widgets.Block(panel, Loc.T("districts"), "жители к цели 2050");
                distRows = new VisualElement(); t.Add(distRows);
            }
            var g = Widgets.Block(panel, Loc.T("chart_gfa"), Loc.T("mln_m2")); g.AddToClassList("gfa-block");
            chart = new TwinChart { Colors = CityStats.CatColors, Stacked = true }; g.Add(chart);
            var legend = new VisualElement(); legend.AddToClassList("legend"); g.Add(legend);
            for (int c = 0; c < CityStats.Cats; c++) legend.Add(Widgets.LegendItem(CityStats.CatColors[c], Loc.T(CityStats.CatKeys[c])));
            g.Add(SourceTags.Line(Sources.ModelCity));

            // ---------------- right: journal of the year + analytics
            Right();
            var j = Widgets.Block(panel, Loc.T("o_journal"), "");
            journalTitle = j.Q<Label>(className: "block-title");
            journal = new VisualElement(); j.Add(journal);
            j.Add(SourceTags.Line(TwinModels.Loads, TwinModels.Build));
            var a = Widgets.Block(panel, Loc.T("o_insights"), "");
            insights = new VisualElement(); a.Add(insights);
            // why and how: folded (the long model note used to be a block of its own)
            var why = Widgets.Details(a, "Как считается");
            var wn = new Label("Выводы — из балансов «спрос / мощность», обеспеченности школами и модели трафика двойника. Вероятная причина дефицита электроэнергии — сдвиг очереди подстанции; адаптивные светофоры снижают задержку на ~18 %.") { pickingMode = PickingMode.Ignore }; wn.AddToClassList("note"); why.Add(wn);
            var note = new Label(Loc.T("model_note")) { pickingMode = PickingMode.Ignore }; note.AddToClassList("note"); note.style.marginTop = 6; why.Add(note);
            a.Add(SourceTags.Line(TwinModels.Loads, TwinModels.Social, TwinModels.Traffic));
        }

        void BuildDistrictHead(VisualElement top, int d)
        {
            var back = new Button(() => TwinUI.Instance.GoToDistrict(-1)) { text = Loc.T("back_city") }; back.AddToClassList("btn"); back.AddToClassList("small"); back.AddToClassList("ghost");
            back.style.alignSelf = Align.FlexStart; back.style.marginBottom = 8; back.style.marginLeft = -8; top.Add(back);
            var head = new VisualElement(); head.AddToClassList("district-head");
            var dot = Widgets.Dot(CityStats.DistrictColors[d], true); dot.style.width = 12; dot.style.height = 12; dot.style.borderTopLeftRadius = dot.style.borderTopRightRadius = dot.style.borderBottomLeftRadius = dot.style.borderBottomRightRadius = 6; dot.style.marginRight = 10; head.Add(dot);
            var t = new Label(CityStats.DistrictIds[d] + " District"); t.AddToClassList("big"); head.Add(t); top.Add(head);
            string[] roles = { "role_gate", "role_golden", "role_growing", "role_green" };
            top.Add(Widgets.Fact(Loc.T("role"), Loc.T(roles[d])));
            var area = Widgets.Fact(Loc.T("area_ha"), Loc.N0(CityStats.DistrictAreaHa[d]) + " " + Loc.T("ha")); top.Add(area);
            planPeople = planJobs = null;
            float plan = GroundStats.PlanHa(d);
            if (plan > 0f)
            {
                // the part of the district the plan redrew: its own figures, counted from the same data by the same rules as the district's
                top.Add(Widgets.Fact("Зона нового плана", string.Format("{0}\u00A0га · {1} зданий", Loc.N1(plan), Loc.N0(CityStats.PlanBuildings[d]))));
                var fp = Widgets.Fact("Жители зоны", "—"); planPeople = fp.Q<Label>(className: "v"); top.Add(fp);
                var fj = Widgets.Fact("Рабочие места зоны", "—"); planJobs = fj.Q<Label>(className: "v"); top.Add(fj);
                area = Widgets.Fact("Парки на участках плана", string.Format("{0}\u00A0га", Loc.N1(GroundStats.ParkHa(d)))); top.Add(area);
            }
            area.style.borderBottomWidth = 0;
            var sp = new VisualElement(); sp.style.height = 12; top.Add(sp);
        }

        public override void Refresh()
        {
            if (panel == null || !CityStats.Ready) return;
            if (builtFor != TwinState.District) Rebuild();
            int y = TwinState.Year, d = TwinState.District, s = (int)TwinState.Scenario;
            float res = CityStats.People(d, y), gfa = CityStats.GfaAll(d, y), jobs = CityStats.Workplaces(d, y), ready = CityStats.Readiness(d, y);
            eyebrow.text = ((d < 0 ? Loc.T("eyebrow_city") : CityStats.DistrictIds[d] + " District") + " · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            int rp = Mathf.RoundToInt(ready * 100);
            string rcls = ready >= 0.95f ? "ok" : ready >= 0.5f ? null : "warn";
            // readiness is the plan's (the buildings due by the year); the sites that run late (the journal's) are not standing yet: with
            // them the city is less ready, and the hero says both, so «100 %» never stands next to sites still behind
            Sites(y, d);
            float planned = CityStats.PlannedGfaOf(d), fact = planned > 0f ? Mathf.Max(0f, ready - siteLateGfa / planned) : ready;
            string cap = d < 0 ? string.Format("город готов в {0} году по плану", y) : string.Format("район готов в {0} году по плану", y);
            if (siteLateGfa > 0f)                            // floored to 0.1 %: a late site never shows as «100,0 %»
                cap = d < 0 ? string.Format("город готов в {0} году по плану; с учётом опозданий строек — {1}\u00A0%", y, Loc.N1(Mathf.Floor(fact * 1000f) / 10f))
                            : string.Format("район готов в {0} году по плану; с учётом опозданий строек — {1}\u00A0%", y, Loc.N1(Mathf.Floor(fact * 1000f) / 10f));
            Widgets.SetHero(hero, rp.ToString(), "%", cap);
            Widgets.SetProgress(bar, ready, rcls);
            kpiV[0].text = Loc.K(res); kpiV[1].text = Loc.K(jobs); kpiV[2].text = Loc.Mln(gfa); kpiV[3].text = Loc.N0(CityStats.Standing(d, y));
            if (planPeople != null && d >= 0)
            {
                planPeople.text = string.Format("{0} в {1} году", Loc.N0(CityStats.PlanPeople(d, y)), y);
                planJobs.text = string.Format("{0} в {1} году", Loc.N0(CityStats.PlanWorkplaces(d, y)), y);
            }

            var series = new float[CityStats.Cats][];
            for (int c = 0; c < CityStats.Cats; c++) { series[c] = new float[CityStats.Years]; for (int i = 0; i < CityStats.Years; i++) series[c][i] = CityStats.Gfa(d, c, TwinState.MinYear + i) / 1e6f; }
            chart.Series = series; chart.MarkYear = y; chart.Refresh();

            if (distRows != null)
            {
                distRows.Clear();
                for (int i = 0; i < CityStats.Districts; i++)
                {
                    int di = i; float r = CityStats.People(i, y) / 1000f, tgt = CityStats.DistrictTarget2050k[i], share = tgt > 0 ? r / tgt : 0;
                    var row = new VisualElement(); row.AddToClassList("status-row"); row.AddToClassList("dist-row");
                    row.Add(Widgets.Dot(CityStats.DistrictColors[i], true));
                    var nm = new Label(CityStats.DistrictIds[i]) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("n"); row.Add(nm);
                    var st = new Label(string.Format("{0} из {1} тыс.", Loc.N0(r), Loc.N0(tgt))) { pickingMode = PickingMode.Ignore }; st.AddToClassList("s"); row.Add(st);
                    var pc = new Label(string.Format("{0}\u00A0%", Mathf.RoundToInt(share * 100))) { pickingMode = PickingMode.Ignore }; pc.AddToClassList("dist-pc");
                    pc.EnableInClassList("warn", share < 0.3f); row.Add(pc);
                    row.AddManipulator(new Clickable(() => TwinUI.Instance.GoToDistrict(di)));
                    distRows.Add(row);
                }
            }
            if (TwinData.Ready) { Journal(y, s, d); Insights(y, s); }
        }

        // ---------------- the year's construction sites (ConstructionLayer's timing): the journal's card and the hero's forecast
        int siteCount, siteHanded, siteBehind; float siteLateGfa;
        /// <summary>Sites of district d (−1 = all) in year y: in work from their start up to the year they are handed over (that year
        /// included, as in ConstructionLayer); handed = handed over this year; behind = late (delayed and at or past its plan year − 1);
        /// late GFA = floor area the plan counts as built by y that is handed over only later (plan ≤ y &lt; forecast).</summary>
        void Sites(int y, int d)
        {
            siteCount = siteHanded = siteBehind = 0; siteLateGfa = 0f;
            var db = CityDatabase.Instance; if (db == null || !TwinData.Ready) return;
            foreach (var bl in db.Buildings)
            {
                if (bl == null || bl.Source == "existing_osm" || (d >= 0 && bl.District != CityStats.DistrictIds[d])) continue;
                ConstructionLayer.Timing(bl, out int st, out int plan, out int fact); if (plan > 2050) continue;
                if (plan <= y && y < fact && CityStats.Cat(bl.Use) >= 0) siteLateGfa += bl.GfaM2;
                if (y < st || y > fact) continue;
                siteCount++; if (y == fact) siteHanded++;
                if (y < fact && ConstructionLayer.Delay(bl.Bid) > 0 && y >= plan - 1) siteBehind++;
            }
        }

        // ---------------- journal of the year, computed from the same data as the other tabs
        void Journal(int y, int s, int d)
        {
            journal.Clear(); journalTitle.text = string.Format(Loc.T("o_journal_y"), y);
            var items = new List<(int prio, VisualElement el)>();
            int yi = TwinData.YI(y);
            // deficits that start this year: the spells of NetDeficits (the district where the network is short, the same number as the
            // analytics and the Infrastructure panel); a district shows its own networks and the pooled ones
            foreach (var sp in NetDeficits.Spells(s, d))
                if (sp.From == y)
                    items.Add((0, Widgets.JournalCard("triangle_alert", NetDeficits.Name(sp), "bad", Loc.T("o_crit"), NetDeficits.InYear(s, sp, y), y.ToString(), Loc.T("o_show"), () => { TwinState.SetModule("prediction"); })));
            // construction: the sites of the year (Sites, counted for the hero): those handed over and those behind schedule
            int sites = siteCount, behind = siteBehind;
            if (sites > 0) items.Add((1, Widgets.JournalCard("hard_hat", Loc.T("o_src_build"), behind > sites * 0.1f ? "warn" : "info", behind > 0 ? Loc.T("o_mid") : "",
                string.Format("{0} площадок в {1} году: {2} сдаются в этом году, {3} отстают от графика", Loc.N0(sites), y, Loc.N0(siteHanded), Loc.N0(behind)),
                y.ToString(), Loc.T("o_open"), () => TwinState.SetModule("construction"))));
            // LRT phases and facility stages coming into service
            for (int p = 0; p < 3; p++) if (TwinData.LrtPhaseYear[s][p] == y)
                    items.Add((2, Widgets.JournalCard("activity", "ЛРТ", "ok", Loc.T("o_open_b"), $"Открыта {p + 1}-я очередь · {TwinData.LrtPhaseNames[p]} · {Loc.N1(TwinData.LrtPhaseKm[p])} км", y.ToString())));
            int fc = 0;
            foreach (var f in TwinData.Facilities)
            {
                if (d >= 0 && f.District != d) continue;
                int st = System.Array.IndexOf(f.Stages[s], y); if (st < 0 || fc >= 3) continue; fc++;
                items.Add((3, Widgets.JournalCard(f.Res.StartsWith("power") || f.Res == "renewable" ? "zap" : f.Res == "water" || f.Res == "sewer" ? "droplets" : "network",
                    Loc.T("o_src_net"), "ok", Loc.T("o_in"), $"{f.Name}: {(st == 0 ? "ввод" : (st + 1) + "-я очередь")}", y.ToString())));
            }
            // new buildings
            int nb = CityStats.NewThisYear(d, y); float dg = (CityStats.GfaAll(d, y) - CityStats.GfaAll(d, y - 1)) / 1000f;
            if (nb > 0) items.Add((4, Widgets.JournalCard("box", Loc.T("o_src_new"), "info", "", string.Format(Loc.T("o_new"), Loc.N0(nb), Loc.N0(dg)), y.ToString())));
            if (items.Count == 0) { var l = new Label(Loc.T("o_quiet")); l.AddToClassList("note"); journal.Add(l); return; }
            // the three most important first, the rest one click away
            var sorted = items.OrderBy(x => x.prio).Take(6).ToList();
            for (int i = 0; i < sorted.Count && i < 3; i++) journal.Add(sorted[i].el);
            if (sorted.Count > 3) { var more = Widgets.Details(journal, string.Format("Ещё {0}", sorted.Count - 3)); for (int i = 3; i < sorted.Count; i++) more.Add(sorted[i].el); }
        }

        void Insights(int y, int s)
        {
            insights.Clear();
            void Add(string t) { var c = new VisualElement(); c.AddToClassList("insight"); c.Add(new Label(t) { pickingMode = PickingMode.Ignore }); insights.Add(c); }
            // the first network deficit of the horizon, in the words of the Infrastructure panel (NetDeficits)
            var sps = NetDeficits.Spells(s, -1);
            Add(sps.Count > 0 ? NetDeficits.Story(sps[0]) : "Дефицитов до 2050 года нет");
            // schools
            int ys = Mathf.Max(y, 2030), yi = TwinData.YI(ys), w = -1; float wc = 2;
            for (int k = 0; k < 4; k++) { float nd = TwinData.SocialNeed[s][k][0][yi], cp = TwinData.SocialCap[s][k][0][yi]; if (nd > 500 && cp / nd < wc) { wc = cp / nd; w = k; } }
            if (w >= 0 && wc < 1) Add(string.Format("Школы: в {0} не хватает {1} мест ({2} год)", CityStats.DistrictIds[w], Loc.N0(TwinData.SocialNeed[s][w][0][yi] - TwinData.SocialCap[s][w][0][yi]), ys));
            // traffic
            var ys2 = TwinData.TrafficYears; int ti = 0; while (ti < ys2.Length - 1 && ys2[ti] < Mathf.Max(y, 2030)) ti++;
            if (ys2.Length > 0 && TwinData.TrafficKpi[s][ti].TryGetValue("congested_km", out var ck))
                Add(string.Format("Транспорт: {0}\u00A0км в заторах в час пик ({1} год)", Loc.N0(ck), ys2[ti]));
        }
    }
}
