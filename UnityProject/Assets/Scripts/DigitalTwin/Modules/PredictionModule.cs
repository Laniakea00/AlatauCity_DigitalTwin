using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;
using static AlatauCity.DigitalTwin.Data.TwinJson;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M2 — Prediction &amp; analysis: "will the city carry itself in year N under scenario S?"
    /// Networks (demand vs capacity), social infrastructure (need vs places), transport, risks (earthquake, flood).
    /// 3D: buildings tinted by the district result (heat map), or by their own risk.</summary>
    public class PredictionModule : TwinModuleBase
    {
        public override string Id => "prediction";
        public override string TabKey => "tab_prediction";

        enum Kind { Net, Social, Transport, Quake, Flood }
        class Metric { public string Id, Name, Unit, Res; public Kind Kind; public int Social; public string Why; }
        static readonly Metric[] Metrics =
        {
            new Metric { Id = "power", Name = "m_power", Unit = "МВт", Res = "power_hv", Kind = Kind.Net, Why = "why_power" },
            new Metric { Id = "water", Name = "m_water", Unit = "тыс. м³/сут", Res = "water", Kind = Kind.Net, Why = "why_water" },
            new Metric { Id = "heat", Name = "m_heat", Unit = "Гкал/ч", Res = "heat", Kind = Kind.Net, Why = "why_heat" },
            new Metric { Id = "sewer", Name = "m_sewer", Unit = "тыс. м³/сут", Res = "sewer", Kind = Kind.Net, Why = "why_sewer" },
            new Metric { Id = "gas", Name = "m_gas", Unit = "тыс. м³/ч", Res = "gas", Kind = Kind.Net, Why = "why_gas" },
            new Metric { Id = "school", Name = "m_school", Unit = "мест", Kind = Kind.Social, Social = 0, Why = "why_social" },
            new Metric { Id = "kg", Name = "m_kg", Unit = "мест", Kind = Kind.Social, Social = 1, Why = "why_social" },
            new Metric { Id = "beds", Name = "m_beds", Unit = "коек", Kind = Kind.Social, Social = 2, Why = "why_social" },
            new Metric { Id = "transport", Name = "m_transport", Unit = "км", Kind = Kind.Transport, Why = "why_transport" },
            new Metric { Id = "quake", Name = "m_quake", Unit = "", Kind = Kind.Quake, Why = "why_quake" },
            new Metric { Id = "flood", Name = "m_flood", Unit = "", Kind = Kind.Flood, Why = "why_flood" },
        };
        static int cur;                 // selected metric
        static bool why, floodExt;
        static int[][] floodCm;         // [scenario 0 = 1 %, 1 = extreme][bid]

        static readonly Color OK = new Color(0.20f, 0.78f, 0.35f), WARN = new Color(0.96f, 0.65f, 0.14f), BAD = new Color(1f, 0.23f, 0.18f);

        Label eyebrow, summary, whyLabel, chartTitle, chartNote, rowsTitle, rowsSub; readonly Label[] kv = new Label[4], kl = new Label[4]; readonly VisualElement[] kb = new VisualElement[4];
        TwinChart chart; VisualElement legend, rows, srcTop, srcChart, srcRows; int srcFor = -1; Button whyBtn; readonly List<Button> chips = new List<Button>();

        public override (Color, string)[] Legend => Metrics[cur].Kind == Kind.Flood
            ? new[] { (new Color(0.55f, 0.75f, 1f), Loc.T("p_lg_flood1")), (new Color(0.15f, 0.40f, 0.95f), Loc.T("p_lg_flood2")), (new Color(0.62f, 0.62f, 0.62f), Loc.T("p_lg_dry")) }
            : Metrics[cur].Kind == Kind.Quake
            ? new[] { (BAD, Loc.T("p_lg_q3")), (WARN, Loc.T("p_lg_q2")), (OK, Loc.T("p_lg_q1")) }
            : new[] { (OK, Loc.T("p_lg_ok")), (WARN, Loc.T("p_lg_warn")), (BAD, Loc.T("p_lg_bad")) };

        /// <summary>Presentation tour: switch to a metric (power, school, flood, ...).</summary>
        public void TourMetric(string id)
        {
            int i = System.Array.FindIndex(Metrics, m => m.Id == id); if (i < 0) return;
            cur = i; why = false; TwinUI.Instance?.FillLegend(Legend); LayerFor(); Refresh();
        }
        public string Summary => summary != null ? summary.text : "";

        public override void OnEnter() { TintLayer.Enable(); LayerFor(); }
        public override void OnExit() { TintLayer.Disable(); LineLayers.Instance?.HideAll(); }

        void LayerFor()
        {
            var L = LineLayers.Instance; if (L == null) return;
            L.HideAll(); if (Metrics[cur].Kind == Kind.Transport) L.Show("traffic", true);
        }

        // ------------------------------------------------------------------ panel
        protected override void Build()
        {
            var top = Widgets.Block(panel);
            eyebrow = Widgets.Eyebrow(top, "");
            var groups = new[] { ("p_g_nets", new[] { 0, 1, 2, 3, 4 }), ("p_g_social", new[] { 5, 6, 7 }), ("p_g_city", new[] { 8, 9, 10 }) };
            chips.Clear();
            foreach (var (g, idx) in groups)
            {
                var gl = new Label(Loc.T(g).ToUpperInvariant()); gl.AddToClassList("note"); gl.style.marginTop = 2; gl.style.marginBottom = 4; gl.style.letterSpacing = 1; top.Add(gl);
                var row = new VisualElement(); row.AddToClassList("chips"); top.Add(row);
                foreach (var i in idx)
                {
                    int k = i; var b = new Button(() => { cur = k; TwinUI.Instance?.FillLegend(Legend); LayerFor(); Refresh(); }) { text = Loc.T(Metrics[i].Name) };
                    b.AddToClassList("chip"); row.Add(b); chips.Add(b);
                }
            }
            summary = new Label(); summary.AddToClassList("summary"); summary.style.marginTop = 6; summary.style.marginBottom = 12; top.Add(summary);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid); VisualElement r0 = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { r0 = new VisualElement(); r0.AddToClassList("kpi-row"); grid.Add(r0); }
                var k = new VisualElement(); k.AddToClassList("kpi");
                kl[i] = new Label(); kl[i].AddToClassList("l"); k.Add(kl[i]); kv[i] = new Label("—"); kv[i].AddToClassList("v"); k.Add(kv[i]);
                kb[i] = k; r0.Add(k);
            }
            whyBtn = Widgets.Btn(Loc.T("p_why"), () => { why = !why; Refresh(); }, "small", "ghost"); whyBtn.style.alignSelf = Align.FlexStart; whyBtn.style.marginTop = 8; whyBtn.style.marginLeft = -8; top.Add(whyBtn);
            whyLabel = new Label(); whyLabel.AddToClassList("note"); whyLabel.style.color = new Color(0.76f, 0.76f, 0.76f); top.Add(whyLabel);
            srcTop = new VisualElement(); top.Add(srcTop); srcFor = -1;

            Right();
            var cb = Widgets.Block(panel, " ");
            chartTitle = cb.Q<Label>(className: "block-title");
            chart = new TwinChart(); cb.Add(chart);
            legend = new VisualElement(); legend.AddToClassList("legend"); cb.Add(legend);
            chartNote = new Label(); chartNote.AddToClassList("note"); chartNote.style.marginTop = 6; cb.Add(chartNote);
            srcChart = new VisualElement(); cb.Add(srcChart);

            var rb = Widgets.Block(panel, Loc.T("p_districts"), Loc.T("p_districts_sub"));
            rowsTitle = rb.Q<Label>(className: "block-title"); rowsSub = rb.Q<Label>(className: "block-sub");
            rows = new VisualElement(); rb.Add(rows); srcRows = new VisualElement(); rb.Add(srcRows);

            var n = Widgets.Block(panel); var note = new Label(Loc.T("p_note")); note.AddToClassList("note"); n.Add(note);
        }

        public override void Refresh()
        {
            if (panel == null || summary == null || !TwinData.Ready || !CityStats.Ready) return;
            for (int i = 0; i < chips.Count; i++) chips[i].EnableInClassList("active", i == cur);
            var m = Metrics[cur]; int s = (int)TwinState.Scenario, y = TwinState.Year;
            eyebrow.text = (Loc.T("tab_prediction") + " · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            whyBtn.text = Loc.T(why ? "p_why_hide" : "p_why"); whyLabel.text = why ? Loc.T(m.Why) : ""; whyLabel.style.display = why ? DisplayStyle.Flex : DisplayStyle.None;
            rows.Clear(); legend.Clear();
            var rk = m.Kind == Kind.Transport ? "p_rows_tr" : m.Kind == Kind.Quake ? "p_rows_q" : m.Kind == Kind.Flood ? "p_rows_f" : "p_districts";
            rowsTitle.text = Loc.T(rk); rowsSub.text = rk == "p_districts" ? Loc.T("p_districts_sub") : "";
            if (srcFor != cur) { srcFor = cur; var ids = SourceIds(m.Kind); srcTop.Clear(); srcTop.Add(SourceTags.Line(ids)); srcChart.Clear(); srcChart.Add(SourceTags.Line(ids)); srcRows.Clear(); srcRows.Add(SourceTags.Line(ids)); }
            switch (m.Kind)
            {
                case Kind.Net: RefreshNet(m, s, y); break;
                case Kind.Social: RefreshSocial(m, s, y); break;
                case Kind.Transport: RefreshTransport(s, y); break;
                case Kind.Quake: RefreshQuake(s, y); break;
                case Kind.Flood: RefreshFlood(s, y); break;
            }
        }

        /// <summary>Where the numbers of a metric come from: the QTwin model with its assumptions, on the build-out scenario and the genplan.</summary>
        static string[] SourceIds(Kind k) => k switch
        {
            Kind.Net => new[] { TwinModels.Loads, Sources.ModelCity, Sources.GenPlan },
            Kind.Social => new[] { TwinModels.Social, Sources.ModelCity, Sources.GenPlan },
            Kind.Transport => new[] { TwinModels.Traffic, Sources.ModelCity },
            Kind.Quake => new[] { TwinModels.Quake, Sources.ModelCity, Sources.Osm },
            _ => new[] { TwinModels.Flood, Sources.ModelCity },
        };

        // ------------------------------------------------------------------ networks
        static float Scale(Metric m) => m.Res == "water" || m.Res == "sewer" || m.Res == "gas" ? 0.001f : 1f;

        void RefreshNet(Metric m, int s, int y)
        {
            var city = TwinData.BalanceOf(s, m.Res, -1); if (city == null) return;
            float k = Scale(m); int yi = TwinData.YI(y);
            var dstat = new string[4];
            for (int d = 0; d < 4; d++)
            {
                var b = TwinData.BalanceOf(s, m.Res, d);
                dstat[d] = b != null ? St(b, yi) : St(city, yi);
            }
            TintLayer.Apply(b => DistrictTint(b, dstat, y));

            // first deficit (any district) — the one-line answer
            int fy = -1, fd = -1; float fv = 0;
            for (int i = 0; i < TwinData.NY && fy < 0; i++)
            {
                for (int d = 0; d < 4; d++) { var b = TwinData.BalanceOf(s, m.Res, d); if (b != null && b.Deficit[i] > 0.5f) { fy = TwinData.Y0 + i; fd = d; fv = b.Deficit[i]; break; } }
                if (fy < 0 && city.Deficit[i] > 0.5f) { fy = TwinData.Y0 + i; fd = -1; fv = city.Deficit[i]; }
            }
            float dem = city.Demand[yi], cap = city.Cap[yi], def = city.Deficit[yi];
            string where = fd >= 0 ? CityStats.DistrictIds[fd] : Loc.T("p_city");
            string cause = Cause(m.Res, fd, s);
            if (fy < 0) summary.text = string.Format(Loc.T("p_sum_net_ok"), Loc.T(m.Name).ToLower(), TwinScenario.Name(TwinState.Scenario));
            else summary.text = string.Format(Loc.T("p_sum_net"), fy, where, F(fv * k), m.Unit, cause);
            Set(0, F(dem * k), string.Format(Loc.T("p_k_dem"), y, m.Unit), "");
            Set(1, F(cap * k), string.Format(Loc.T("p_k_cap"), m.Unit), "");
            Set(2, cap > 0 ? Mathf.RoundToInt(100 * dem / cap) + " %" : "—", Loc.T("p_k_util"), def > 0.5f ? "bad" : dem > cap * 0.85f ? "warn" : "ok");
            Set(3, fy < 0 ? "—" : fy.ToString(), Loc.T("p_k_first"), fy < 0 ? "ok" : "bad");

            chartTitle.text = string.Format(Loc.T("p_chart_net"), Loc.T(m.Name));
            var ser = new[] { Mul(city.Demand, k), Mul(city.Cap, k) };
            var alerts = new bool[TwinData.NY]; for (int i = 0; i < TwinData.NY; i++) { alerts[i] = city.Deficit[i] > 0.5f; for (int d = 0; d < 4; d++) { var b = TwinData.BalanceOf(s, m.Res, d); if (b != null && b.Deficit[i] > 0.5f) alerts[i] = true; } }
            chart.Series = ser; chart.Colors = new[] { new Color(0.99f, 0.99f, 0.99f), new Color(0.53f, 0.53f, 0.53f) }; chart.LineWidths = new[] { 2.5f, 1.5f };
            chart.Stacked = false; chart.Bars = false; chart.StepLast = true; chart.Alerts = alerts; chart.MarkYear = y; chart.Refresh();
            legend.Add(Widgets.LegendItem(new Color(0.99f, 0.99f, 0.99f), Loc.T("p_demand"))); legend.Add(Widgets.LegendItem(new Color(0.53f, 0.53f, 0.53f), Loc.T("p_capacity")));
            legend.Add(Widgets.LegendItem(BAD, Loc.T("p_deficit_years")));
            chartNote.text = Loc.T("p_chart_net_note");

            for (int d = 0; d < 4; d++)
            {
                var b = TwinData.BalanceOf(s, m.Res, d);
                float ld = TwinData.Load(s, m.Res == "power_hv" ? "power" : m.Res, d, y);
                string val = b != null ? F(b.Demand[yi] * k) + " / " + F(b.Cap[yi] * k) + " " + m.Unit : F(ld * k) + " " + m.Unit + " · " + Loc.T("p_pooled");
                string st = b != null ? St(b, yi) : St(city, yi);
                int first = -1; if (b != null) for (int i = 0; i < TwinData.NY; i++) if (b.Deficit[i] > 0.5f) { first = TwinData.Y0 + i; break; }
                AddRow(d, val, st, first >= 0 ? string.Format(Loc.T("p_row_first"), first) : Loc.T("p_row_none"));
            }
        }

        static string Cause(string res, int district, int s)
        {
            if (TwinState.Scenario == Scenario.Fast) return Loc.T("p_cause_fast");
            var f = TwinData.Facilities.FirstOrDefault(x => (x.Res == res || (res == "power_hv" && x.Res == "power_hv")) && (district < 0 || x.District == district) && x.DelayedStages.Length > 0);
            if (f == null) return Loc.T("p_cause_peak");
            int st = f.DelayedStages[0]; int yr = st - 1 < f.Stages[s].Length ? f.Stages[s][st - 1] : 0;
            return string.Format(Loc.T("p_cause_delay"), st, f.Name, yr);
        }

        static string St(TwinData.Balance b, int yi) => b.Deficit[yi] > 0.5f ? "bad" : b.Cap[yi] > 0 && b.Demand[yi] > 0.85f * b.Cap[yi] ? "warn" : "ok";
        static Color DistrictTint(BuildingInfo b, string[] dstat, int y)
        {
            int d = CityStats.DistrictIndex(b.District); if (d < 0 || b.Source == "existing_osm") return new Color(0, 0, 0, 0);
            var st = dstat[d]; var c = st == "bad" ? BAD : st == "warn" ? WARN : OK; c.a = st == "bad" ? 0.85f : st == "warn" ? 0.7f : 0.45f; return c;
        }

        // ------------------------------------------------------------------ social
        void RefreshSocial(Metric m, int s, int y)
        {
            int yi = TwinData.YI(y), k = m.Social;
            float needC = 0, capC = 0; var dstat = new string[4]; var cov = new float[4];
            for (int d = 0; d < 4; d++)
            {
                float nd = TwinData.SocialNeed[s][d][k][yi], cp = TwinData.SocialCap[s][d][k][yi]; needC += nd; capC += cp;
                cov[d] = nd > 0 ? cp / nd : 1f; dstat[d] = nd < 1 ? "ok" : cov[d] < 0.9f ? "bad" : cov[d] < 1.0f ? "warn" : "ok";
            }
            TintLayer.Apply(b => DistrictTint(b, dstat, y));
            int worst = -1; float wv = 0; for (int d = 0; d < 4; d++) { float gap = TwinData.SocialNeed[s][d][k][yi] - TwinData.SocialCap[s][d][k][yi]; if (gap > wv) { wv = gap; worst = d; } }
            float covC = needC > 0 ? capC / needC : 1;
            summary.text = worst < 0 ? string.Format(Loc.T("p_sum_soc_ok"), y, Loc.T(m.Name).ToLower())
                : string.Format(Loc.T("p_sum_soc"), y, CityStats.DistrictIds[worst], Loc.N0(wv), m.Unit, Loc.T(m.Name).ToLower(), Mathf.RoundToInt(cov[worst] * 100));
            Set(0, Loc.N0(needC), string.Format(Loc.T("p_k_need"), m.Unit), "");
            Set(1, Loc.N0(capC), string.Format(Loc.T("p_k_have"), m.Unit), "");
            Set(2, Mathf.RoundToInt(covC * 100) + " %", Loc.T("p_k_cov"), covC < 0.9f ? "bad" : covC < 1f ? "warn" : "ok");
            Set(3, Loc.N0(Mathf.Max(0, needC - capC)), string.Format(Loc.T("p_k_gap"), m.Unit), needC > capC ? "warn" : "ok");
            chartTitle.text = string.Format(Loc.T("p_chart_soc"), Loc.T(m.Name));
            var need = new float[TwinData.NY]; var cap = new float[TwinData.NY]; var alerts = new bool[TwinData.NY];
            for (int i = 0; i < TwinData.NY; i++) { for (int d = 0; d < 4; d++) { need[i] += TwinData.SocialNeed[s][d][k][i]; cap[i] += TwinData.SocialCap[s][d][k][i]; if (TwinData.SocialNeed[s][d][k][i] > TwinData.SocialCap[s][d][k][i] * 1.1f && TwinData.SocialNeed[s][d][k][i] > 50) alerts[i] = true; } }
            chart.Series = new[] { Mul(need, 0.001f), Mul(cap, 0.001f) }; chart.Colors = new[] { new Color(0.99f, 0.99f, 0.99f), new Color(0.53f, 0.53f, 0.53f) }; chart.LineWidths = new[] { 2.5f, 1.5f };
            chart.Stacked = false; chart.Bars = false; chart.StepLast = false; chart.Alerts = alerts; chart.MarkYear = y; chart.Refresh();
            legend.Add(Widgets.LegendItem(new Color(0.99f, 0.99f, 0.99f), Loc.T("p_need"))); legend.Add(Widgets.LegendItem(new Color(0.53f, 0.53f, 0.53f), Loc.T("p_have"))); legend.Add(Widgets.LegendItem(BAD, Loc.T("p_short_years")));
            chartNote.text = Loc.T("p_chart_soc_note");
            for (int d = 0; d < 4; d++)
            {
                float nd = TwinData.SocialNeed[s][d][k][yi], cp = TwinData.SocialCap[s][d][k][yi];
                AddRow(d, Loc.N0(cp) + " / " + Loc.N0(nd) + " " + m.Unit, dstat[d], nd > cp ? string.Format(Loc.T("p_row_short"), Loc.N0(nd - cp), Mathf.RoundToInt(cov[d] * 100)) : Loc.T("p_row_enough"));
            }
        }

        // ------------------------------------------------------------------ transport
        void RefreshTransport(int s, int y)
        {
            TintLayer.Apply(b => new Color(0, 0, 0, 0));
            var ys = TwinData.TrafficYears; int ti = 0; while (ti < ys.Length - 1 && ys[ti] < y) ti++;
            var kp = TwinData.TrafficKpi[s][ti];
            float ck = kp.TryGetValue("congested_km", out var a) ? a : 0, dl = kp.TryGetValue("avg_delay_pct", out var b2) ? b2 : 0;
            float car = kp.TryGetValue("car_trips", out var c) ? c : 0, lrt = kp.TryGetValue("lrt_trips", out var e) ? e : 0;
            int ph = -1; for (int i = 0; i < 3; i++) if (TwinData.LrtPhaseYear[s][i] <= y) ph = i;
            summary.text = string.Format(Loc.T("p_sum_tr"), ys[ti], Loc.N0(ck), Mathf.RoundToInt(dl),
                ph < 0 ? string.Format(Loc.T("p_lrt_none"), TwinData.LrtPhaseYear[s][0]) : string.Format(Loc.T("p_lrt_on"), ph + 1, Loc.N1(lrt / 1000f)));
            Set(0, Loc.N0(ck), Loc.T("p_k_cong"), ck > 150 ? "bad" : ck > 60 ? "warn" : "ok");
            Set(1, "+" + Mathf.RoundToInt(dl) + " %", Loc.T("p_k_delay"), dl > 35 ? "bad" : dl > 15 ? "warn" : "ok");
            Set(2, Loc.N1(car / 1000f), Loc.T("p_k_cars"), "");
            Set(3, lrt > 0 ? Mathf.RoundToInt(100f * lrt / Mathf.Max(lrt + car * 1.3f, 1)) + " %" : "—", Loc.T("p_k_lrt"), "");
            chartTitle.text = Loc.T("p_chart_tr");
            // congested km by modelled year, all four scenarios (current one bold)
            var ser = new float[4][]; for (int sc = 0; sc < 4; sc++) { ser[sc] = new float[TwinData.NY]; for (int i = 0; i < TwinData.NY; i++) ser[sc][i] = Interp(sc, TwinData.Y0 + i); }
            var cols = new[] { new Color(0.99f, 0.99f, 0.99f), WARN, new Color(0.53f, 0.53f, 0.53f), new Color(0.48f, 0.65f, 1f) };
            var widths = new float[4]; for (int i = 0; i < 4; i++) widths[i] = i == s ? 3f : 1.2f;
            chart.Series = ser; chart.Colors = cols; chart.LineWidths = widths; chart.Stacked = false; chart.Bars = false; chart.StepLast = false; chart.Alerts = null; chart.MarkYear = y; chart.Refresh();
            for (int i = 0; i < 4; i++) legend.Add(Widgets.LegendItem(cols[i], TwinScenario.Name((Scenario)i)));
            chartNote.text = Loc.T("p_chart_tr_note");
            for (int p = 0; p < 3; p++)
                rows.Add(Widgets.Fact(string.Format(Loc.T("p_lrt_phase"), p + 1, TwinData.LrtPhaseNames[p]), TwinData.LrtPhaseYear[s][p] + " · " + Loc.N1(TwinData.LrtPhaseKm[p]) + " км"));
        }
        static float Interp(int s, int y)
        {
            var ys = TwinData.TrafficYears; float v(int i) => TwinData.TrafficKpi[s][i].TryGetValue("congested_km", out var a) ? a : 0;
            if (y <= ys[0]) return v(0) * Mathf.Clamp01((y - TwinData.Y0) / (float)(ys[0] - TwinData.Y0));
            for (int i = 1; i < ys.Length; i++) if (y <= ys[i]) return Mathf.Lerp(v(i - 1), v(i), (y - ys[i - 1]) / (float)(ys[i] - ys[i - 1]));
            return v(ys.Length - 1);
        }

        // ------------------------------------------------------------------ earthquake (model): vulnerability by type and age
        static float QuakeP(BuildingInfo b)
        {
            if (b.Source == "existing_osm") return b.HeightM > 12 ? 0.22f : 0.35f;     // older stock, not designed for 9 points
            switch (b.Kind)
            {
                case "house": return 0.06f;
                case "res_high": case "tower": return 0.07f;
                case "solar": return 0f;
                default: return 0.03f;                                                 // new RC / steel to СП РК 2.03-30-2017
            }
        }
        void RefreshQuake(int s, int y)
        {
            var db = CityDatabase.Instance; if (db == null) return;
            float heavy = 0, people = 0, peopleRisk = 0; int high = 0, all = 0;
            foreach (var b in db.Buildings)
            {
                if (b == null) continue; int e = CityStats.EffectiveYearOf(b.Bid); if (b.Source != "existing_osm" && e > y) continue;
                float p = QuakeP(b); all++; heavy += p; if (p >= 0.2f) high++;
                float res = b.Use == "housing" ? b.GfaM2 / 30f : b.Source == "existing_osm" ? Mathf.Max(3f, b.GfaM2 / 35f) : 0;
                people += res; peopleRisk += res * p;
            }
            TintLayer.Apply(b =>
            {
                int e = CityStats.EffectiveYearOf(b.Bid); if (b.Source != "existing_osm" && e > y) return new Color(0, 0, 0, 0);
                float p = QuakeP(b); var c = p >= 0.2f ? BAD : p >= 0.06f ? WARN : OK; c.a = p >= 0.2f ? 0.9f : p >= 0.06f ? 0.7f : 0.4f; return c;
            });
            summary.text = string.Format(Loc.T("p_sum_quake"), y, Loc.N0(heavy), Loc.N0(high), Loc.N0(peopleRisk / 1000f * 1000f));
            Set(0, Loc.N0(high), Loc.T("p_k_q_high"), high > 0 ? "bad" : "ok");
            Set(1, Loc.N0(heavy), Loc.T("p_k_q_heavy"), "warn");
            Set(2, Loc.N0(peopleRisk), Loc.T("p_k_q_people"), "");
            Set(3, Mathf.RoundToInt(6 + heavy / 400f) + " " + Loc.T("p_months"), Loc.T("p_k_q_restore"), "");
            chartTitle.text = Loc.T("p_chart_q");
            var ser = new float[2][]; ser[0] = new float[TwinData.NY]; ser[1] = new float[TwinData.NY];
            foreach (var b in db.Buildings)
            {
                if (b == null) continue; float p = QuakeP(b); int e = b.Source == "existing_osm" ? TwinData.Y0 : CityStats.EffectiveYearOf(b.Bid);
                if (e > 2050) continue; int i0 = Mathf.Clamp(e - TwinData.Y0, 0, TwinData.NY - 1);
                for (int i = i0; i < TwinData.NY; i++) ser[p >= 0.2f ? 0 : 1][i] += p;   // expected heavily damaged buildings
            }
            chart.Series = new[] { ser[0], ser[1] }; chart.Colors = new[] { BAD, WARN }; chart.Stacked = true; chart.Bars = false; chart.StepLast = false; chart.Alerts = null; chart.MarkYear = y; chart.Refresh();
            legend.Add(Widgets.LegendItem(BAD, Loc.T("p_q_old"))); legend.Add(Widgets.LegendItem(WARN, Loc.T("p_q_new")));
            chartNote.text = Loc.T("p_chart_q_note");
            rows.Add(Widgets.Fact(Loc.T("p_q_scn"), Loc.T("p_q_scn_v"))); rows.Add(Widgets.Fact(Loc.T("p_q_norm"), "СП РК 2.03-30-2017"));
        }

        // ------------------------------------------------------------------ flood (model): depth at each building from risk.json
        void RefreshFlood(int s, int y)
        {
            if (floodCm == null) LoadFlood();
            var db = CityDatabase.Instance; if (db == null || floodCm == null) return;
            var fc = floodCm[floodExt ? 1 : 0];
            int n = 0, deep = 0; float people = 0, damage = 0;
            foreach (var b in db.Buildings)
            {
                if (b == null || b.Bid >= fc.Length) continue; int e = CityStats.EffectiveYearOf(b.Bid); if (b.Source != "existing_osm" && e > y) continue;
                int cm = fc[b.Bid]; if (cm <= 0) continue; n++; if (cm > 100) deep++;
                people += b.Use == "housing" ? b.GfaM2 / 30f : b.Source == "existing_osm" ? Mathf.Max(3f, b.GfaM2 / 35f) : 0;
                float floorsShare = Mathf.Clamp01(cm / 100f / Mathf.Max(3f, b.HeightM)) + 0.05f;
                damage += b.GfaM2 * 300000f * Mathf.Min(0.4f, floorsShare) / 1e9f;
            }
            TintLayer.Apply(b =>
            {
                if (b.Bid >= fc.Length) return new Color(0, 0, 0, 0);
                int e = CityStats.EffectiveYearOf(b.Bid); if (b.Source != "existing_osm" && e > y) return new Color(0, 0, 0, 0);
                int cm = fc[b.Bid]; if (cm <= 0) return new Color(0, 0, 0, 0);
                return cm > 100 ? new Color(0.15f, 0.40f, 0.95f, 0.95f) : new Color(0.55f, 0.75f, 1f, 0.85f);
            });
            summary.text = n == 0 ? Loc.T("p_sum_flood_0") : string.Format(Loc.T("p_sum_flood"), Loc.T(floodExt ? "p_f_ext" : "p_f_1"), y, Loc.N0(n), Loc.N0(people), Loc.N0(damage));
            Set(0, Loc.N0(n), Loc.T("p_k_f_n"), n > 0 ? "warn" : "ok");
            Set(1, Loc.N0(deep), Loc.T("p_k_f_deep"), deep > 0 ? "bad" : "ok");
            Set(2, Loc.N0(people), Loc.T("p_k_f_people"), "");
            Set(3, Loc.N0(damage), Loc.T("p_k_f_damage"), "");
            chartTitle.text = Loc.T("p_chart_f");
            var a1 = new float[TwinData.NY];
            foreach (var b in db.Buildings)
            {
                if (b == null || b.Bid >= fc.Length || fc[b.Bid] <= 0) continue; int e = b.Source == "existing_osm" ? TwinData.Y0 : CityStats.EffectiveYearOf(b.Bid);
                if (e > 2050) continue; for (int i = Mathf.Clamp(e - TwinData.Y0, 0, TwinData.NY - 1); i < TwinData.NY; i++) a1[i] += 1;
            }
            chart.Series = new[] { a1 }; chart.Colors = new[] { new Color(0.30f, 0.64f, 1f) }; chart.Stacked = true; chart.Bars = false; chart.StepLast = false; chart.Alerts = null; chart.MarkYear = y; chart.Refresh();
            legend.Add(Widgets.LegendItem(new Color(0.30f, 0.64f, 1f), Loc.T("p_f_buildings")));
            chartNote.text = Loc.T("p_chart_f_note");
            var sw = new VisualElement(); sw.AddToClassList("chips"); sw.style.marginTop = 4;
            foreach (var (key, ext) in new[] { ("p_f_1", false), ("p_f_ext", true) })
            {
                var e2 = ext; var bt = new Button(() => { floodExt = e2; Refresh(); }) { text = Loc.T(key) }; bt.AddToClassList("chip"); bt.EnableInClassList("active", floodExt == ext); sw.Add(bt);
            }
            rows.Add(sw);
        }
        static void LoadFlood()
        {
            try
            {
                var j = Parse(TwinFiles.Text("risk.json"));
                var sc = G(j, "scenarios"); floodCm = new[] { Ints(G(G(sc, "flood_1pct"), "depth_cm")), Ints(G(G(sc, "flood_ext"), "depth_cm")) };
            }
            catch (System.Exception e) { Debug.LogError("[Alatau] risk.json: " + e.Message); }
        }

        // ------------------------------------------------------------------ helpers
        void AddRow(int d, string val, string st, string sub)
        {
            var r = new VisualElement(); r.AddToClassList("stage-row"); r.AddToClassList("clickable");
            var t = new VisualElement(); t.AddToClassList("top");
            t.Add(Widgets.Dot(CityStats.DistrictColors[d], true));
            var n = new Label(CityStats.DistrictIds[d]) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); t.Add(n);
            var v = new Label(val) { pickingMode = PickingMode.Ignore }; v.AddToClassList("v"); t.Add(v); r.Add(t);
            var sl = new Label(sub) { pickingMode = PickingMode.Ignore }; sl.AddToClassList("note"); sl.style.marginTop = 3; sl.style.marginLeft = 14;
            sl.style.color = st == "bad" ? BAD : st == "warn" ? WARN : new Color(0.53f, 0.53f, 0.53f); r.Add(sl);
            int di = d; r.AddManipulator(new Clickable(() => TwinUI.Instance?.GoToDistrict(di)));
            rows.Add(r);
        }
        void Set(int i, string v, string l, string cls)
        {
            kv[i].text = v; kl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) kb[i].RemoveFromClassList(c);
            if (cls != "") kb[i].AddToClassList(cls);
        }
        static float[] Mul(float[] a, float k) { var r = new float[a.Length]; for (int i = 0; i < a.Length; i++) r[i] = a[i] * k; return r; }
        static string F(float v) => v >= 100 ? Loc.N0(v) : Loc.N1(v);
    }
}
