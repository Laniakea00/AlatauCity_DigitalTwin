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
    /// AI analytics (3 conclusions from the data) and the growth chart. District mode on row click.</summary>
    public class OverviewModule : TwinModuleBase
    {
        public override string Id => "overview";
        public override string TabKey => "tab_overview";

        Label summary, meterLabel, eyebrow; VisualElement meter; readonly Label[] kpiV = new Label[4]; readonly Label[] kpiL = new Label[4];
        TwinChart chart; VisualElement distRows, journal, insights; Label journalTitle;
        int builtFor = -2;

        static readonly Color BAD = new Color(1f, 0.23f, 0.18f), WARN = new Color(0.96f, 0.65f, 0.14f), OK = new Color(0.20f, 0.78f, 0.35f);

        protected override void Build()
        {
            builtFor = TwinState.District;
            // ---------------- left: the city now
            var top = Widgets.Block(panel);
            if (TwinState.District >= 0) BuildDistrictHead(top, TwinState.District);
            eyebrow = Widgets.Eyebrow(top, "");
            summary = new Label(); summary.AddToClassList("summary"); summary.style.marginBottom = 10; top.Add(summary);
            meterLabel = new Label(); meterLabel.AddToClassList("meter-title"); top.Add(meterLabel);
            meter = Widgets.Meter(top, 0f);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); grid.style.marginTop = 10; top.Add(grid);
            VisualElement kRow = null;
            for (int i = 0; i < 4; i++)
            {
                var k = new VisualElement(); k.AddToClassList("kpi");
                kpiL[i] = new Label(); kpiL[i].AddToClassList("l"); k.Add(kpiL[i]);
                kpiV[i] = new Label("—"); kpiV[i].AddToClassList("v"); k.Add(kpiV[i]);
                if (i % 2 == 0) { kRow = new VisualElement(); kRow.AddToClassList("kpi-row"); grid.Add(kRow); } kRow.Add(k);
            }
            if (TwinState.District < 0)
            {
                var t = Widgets.Block(panel, Loc.T("districts"), Loc.T("o_dist_sub"));
                distRows = new VisualElement(); t.Add(distRows);
            }
            var g = Widgets.Block(panel, Loc.T("chart_gfa"), Loc.T("mln_m2")); g.AddToClassList("gfa-block");
            chart = new TwinChart { Colors = CityStats.CatColors, Stacked = true }; g.Add(chart);
            var legend = new VisualElement(); legend.AddToClassList("legend"); g.Add(legend);
            for (int c = 0; c < CityStats.Cats; c++) legend.Add(Widgets.LegendItem(CityStats.CatColors[c], Loc.T(CityStats.CatKeys[c])));

            // ---------------- right: journal of the year + AI analytics
            Right();
            var j = Widgets.Block(panel, Loc.T("o_journal"), "");
            journalTitle = j.Q<Label>(className: "block-title");
            journal = new VisualElement(); j.Add(journal);
            var a = Widgets.Block(panel, Loc.T("o_ai"), "");
            insights = new VisualElement(); a.Add(insights);
            var rec = new VisualElement(); rec.AddToClassList("wide-btn"); rec.Add(new Label(Loc.T("o_recs")) { pickingMode = PickingMode.Ignore }); rec.Add(TwinUI.Icon("sparkles", 16));
            rec.AddManipulator(new Clickable(() => TwinState.SetModule("ai"))); a.Add(rec);
            var n = Widgets.Block(panel); var note = new Label(Loc.T("model_note")); note.AddToClassList("note"); n.Add(note);
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
            var area = Widgets.Fact(Loc.T("area_ha"), Loc.N0(CityStats.DistrictAreaHa[d]) + " " + Loc.T("ha")); area.style.borderBottomWidth = 0; top.Add(area);
            var sp = new VisualElement(); sp.style.height = 12; top.Add(sp);
        }

        public override void Refresh()
        {
            if (panel == null || !CityStats.Ready) return;
            if (builtFor != TwinState.District) Rebuild();
            int y = TwinState.Year, d = TwinState.District, s = (int)TwinState.Scenario;
            float res = CityStats.Residents(d, y), gfa = CityStats.GfaAll(d, y), jobs = CityStats.Jobs(d, y), ready = CityStats.Readiness(d, y);
            eyebrow.text = ((d < 0 ? Loc.T("eyebrow_city") : CityStats.DistrictIds[d] + " District") + " · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            if (d < 0) summary.text = gfa < 1 ? string.Format(Loc.T("summary_city_0"), y) : string.Format(Loc.T("summary_city"), y, Loc.K(res), Mathf.RoundToInt(ready * 100));
            else summary.text = string.Format(Loc.T("summary_district"), y, CityStats.DistrictIds[d], Loc.K(res), Mathf.RoundToInt(100f * res / 1000f / CityStats.DistrictTarget2050k[d]));
            meterLabel.text = string.Format(Loc.T(d < 0 ? "o_meter" : "o_meter_d"), Mathf.RoundToInt(ready * 100));
            Widgets.SetMeter(meter, ready);
            Set(0, Loc.K(res), Loc.T("kpi_res_t"));
            Set(1, Loc.Mln(gfa), Loc.T("kpi_gfa_t"));
            Set(2, Loc.K(jobs), Loc.T("kpi_jobs_t"));
            Set(3, Loc.N0(CityStats.Count(d, y)), Loc.T("o_k_bld"));

            var series = new float[CityStats.Cats][];
            for (int c = 0; c < CityStats.Cats; c++) { series[c] = new float[CityStats.Years]; for (int i = 0; i < CityStats.Years; i++) series[c][i] = CityStats.Gfa(d, c, TwinState.MinYear + i) / 1e6f; }
            chart.Series = series; chart.MarkYear = y; chart.Refresh();

            if (distRows != null)
            {
                distRows.Clear();
                for (int i = 0; i < CityStats.Districts; i++)
                {
                    int di = i; float r = CityStats.Residents(i, y) / 1000f, tgt = CityStats.DistrictTarget2050k[i], share = tgt > 0 ? r / tgt : 0;
                    var row = new VisualElement(); row.AddToClassList("status-row");
                    row.Add(Widgets.Dot(CityStats.DistrictColors[i], true));
                    var nm = new Label(CityStats.DistrictIds[i]) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("n"); row.Add(nm);
                    var st = new Label($"{Loc.N0(r)} / {Loc.N0(tgt)} · {Mathf.RoundToInt(share * 100)} %") { pickingMode = PickingMode.Ignore }; st.AddToClassList("s");
                    st.AddToClassList(share >= 0.95f ? "ok" : share >= 0.3f ? "ok" : "warn"); row.Add(st);
                    row.AddManipulator(new Clickable(() => TwinUI.Instance.GoToDistrict(di)));
                    distRows.Add(row);
                }
            }
            if (TwinData.Ready) { Journal(y, s, d); Insights(y, s); }
        }

        // ---------------- journal of the year, computed from the same data as the other tabs
        void Journal(int y, int s, int d)
        {
            journal.Clear(); journalTitle.text = string.Format(Loc.T("o_journal_y"), y);
            var items = new List<(int prio, VisualElement el)>();
            int yi = TwinData.YI(y);
            // deficits that start this year
            foreach (var (res, name, unit) in new[] { ("power_hv", "Электроэнергия", "МВт"), ("heat", "Тепло", "Гкал/ч"), ("sewer", "Канализация", "м³/сут"), ("water", "Вода", "м³/сут") })
                {
                    int k = d;   // whole city → city balance, district → only its own (no duplicate cards)
                    var b = TwinData.BalanceOf(s, res, k); if (b == null) continue;
                    if (b.Deficit[yi] > 0.5f && (yi == 0 || b.Deficit[yi - 1] <= 0.5f))
                        items.Add((0, Widgets.JournalCard("triangle_alert", name, "bad", Loc.T("o_crit"), $"{(k < 0 ? "Город" : CityStats.DistrictIds[k])}: спрос выше мощности на {Loc.N0(b.Deficit[yi])} {unit}", y.ToString(), Loc.T("o_show"), () => { TwinState.SetModule("prediction"); })));
                }
            // construction behind schedule
            int behind = 0, sites = 0; var db = CityDatabase.Instance;
            if (db != null) foreach (var bl in db.Buildings)
                {
                    if (bl == null || bl.Source == "existing_osm" || (d >= 0 && bl.District != CityStats.DistrictIds[d])) continue;
                    ConstructionLayer.Timing(bl, out int st, out int plan, out int fact); if (y < st || y >= fact || plan > 2050) continue;
                    sites++; if (ConstructionLayer.Delay(bl.Bid) > 0 && y >= plan - 1) behind++;
                }
            if (sites > 0) items.Add((1, Widgets.JournalCard("hard_hat", Loc.T("o_src_build"), behind > sites * 0.1f ? "warn" : "info", behind > 0 ? Loc.T("o_mid") : "",
                string.Format(Loc.T("o_build"), Loc.N0(sites), Loc.N0(behind)), y.ToString(), Loc.T("o_open"), () => TwinState.SetModule("construction"))));
            // LRT phases and facility stages coming into service
            for (int p = 0; p < 3; p++) if (TwinData.LrtPhaseYear[s][p] == y)
                    items.Add((2, Widgets.JournalCard("activity", "ЛРТ", "ok", Loc.T("o_open_b"), $"Открыта {p + 1}-я очередь · {TwinData.LrtPhaseNames[p]} · {Loc.N1(TwinData.LrtPhaseKm[p])} км", y.ToString())));
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
            foreach (var it in items.OrderBy(x => x.prio).Take(5)) journal.Add(it.el);
        }

        void Insights(int y, int s)
        {
            insights.Clear();
            void Add(string t) { var c = new VisualElement(); c.AddToClassList("insight"); c.Add(new Label(t) { pickingMode = PickingMode.Ignore }); insights.Add(c); }
            // first power deficit
            int fy = -1, fd = -1; float fv = 0;
            for (int i = 0; i < TwinData.NY && fy < 0; i++) for (int k = 0; k < 4; k++) { var b = TwinData.BalanceOf(s, "power_hv", k); if (b != null && b.Deficit[i] > 0.5f) { fy = 2025 + i; fd = k; fv = b.Deficit[i]; break; } }
            if (fy > 0) Add($"Электроэнергия — первый дефицит в {fy} году в {CityStats.DistrictIds[fd]} ({Loc.N1(fv)} МВт). Вероятная причина: сдвиг очереди подстанции; рекомендуется ускорить ввод.");
            else Add("Электроэнергии хватает до 2050 года во всех районах при этом сценарии.");
            // schools
            int ys = Mathf.Max(y, 2030), yi = TwinData.YI(ys), w = -1; float wc = 2;
            for (int k = 0; k < 4; k++) { float nd = TwinData.SocialNeed[s][k][0][yi], cp = TwinData.SocialCap[s][k][0][yi]; if (nd > 500 && cp / nd < wc) { wc = cp / nd; w = k; } }
            if (w >= 0 && wc < 1) Add($"Школы — в {ys} году в {CityStats.DistrictIds[w]} обеспеченность {Mathf.RoundToInt(wc * 100)} %: не хватает {Loc.N0(TwinData.SocialNeed[s][w][0][yi] - TwinData.SocialCap[s][w][0][yi])} мест.");
            // traffic
            var ys2 = TwinData.TrafficYears; int ti = 0; while (ti < ys2.Length - 1 && ys2[ti] < Mathf.Max(y, 2030)) ti++;
            if (ys2.Length > 0 && TwinData.TrafficKpi[s][ti].TryGetValue("congested_km", out var ck))
                Add($"Транспорт — в {ys2[ti]} году {Loc.N0(ck)} км дорог в заторе в утренний час пик; адаптивные светофоры снизят задержку на ~18 %.");
        }
        void Set(int i, string v, string l) { kpiV[i].text = v; kpiL[i].text = l; }
    }
}
