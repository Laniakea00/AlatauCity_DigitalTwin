using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M1 — Monitoring Construction City: where and what is being built in year N, plan vs fact, money, who is behind.
    /// 3D: buildings under construction rise with their progress (amber = on plan, red = behind, green = handed over this year).</summary>
    public partial class ConstructionModule : TwinModuleBase
    {
        public override string Id => "construction";
        public override string TabKey => "tab_construction";
        public override (Color, string)[] Legend => bimMode ? new[]
        {
            (new Color(0.80f, 0.81f, 0.83f), Loc.T("bim_s_done")), (new Color(0.96f, 0.65f, 0.14f), Loc.T("bim_s_work")),
            (new Color(1f, 0.23f, 0.18f), Loc.T("bim_s_behind")), (new Color(0.55f, 0.62f, 0.72f), Loc.T("bim_s_wait")),
        } : new[]
        {
            (new Color(0.96f, 0.65f, 0.14f), Loc.T("c_lg_onplan")), (new Color(1f, 0.23f, 0.18f), Loc.T("c_lg_behind")),
            (new Color(0.20f, 0.78f, 0.35f), Loc.T("c_lg_done")), (new Color(0.62f, 0.62f, 0.62f), Loc.T("c_lg_built")),
        };
        static readonly Color[] SrcColors = { new Color(0.48f, 0.65f, 1f), new Color(0.99f, 0.99f, 0.99f), new Color(0.96f, 0.65f, 0.14f), new Color(0.53f, 0.53f, 0.53f) };
        static readonly float[] InfraShare = { 0.60f, 0f, 0.10f, 0.30f };   // budget, private, PPP, quasi-state (norms.FUNDING["infra"])

        Label eyebrow, summary, sGap, moneyNote; readonly Label[] kv = new Label[4], kl = new Label[4]; readonly VisualElement[] kb = new VisualElement[4];
        BuildChart bChart; Label bcV1, bcL1, bcV2, bcL2; VisualElement srcBar, srcLeg; VisualElement worstList, contractors;

        static bool showNets = true, showRoads = true, showTraffic;
        VisualElement netRows; Label trafficNote; Button chipNets, chipRoads, chipTraffic;

        public override void OnEnter() { ConstructionLayer.Enable(); ApplyLayers(); }
        public override void OnExit() { if (bimMode) LeaveBim(false); ConstructionLayer.Disable(); LineLayers.Instance?.HideAll(); }

        static void ApplyLayers()
        {
            var L = LineLayers.Instance; if (L == null) return;
            L.Style(0.45f, 0f, 1f);
            // in the presentation the overlays (networks, road works) belong to their own step ("Контроль стройки")
            bool nets = TwinTour.Running ? TourOverlays : showNets, roads = TwinTour.Running ? TourOverlays : showRoads, traffic = !TwinTour.Running && showTraffic;
            foreach (var k in LineLayers.NetKeys) L.Show(k, nets);
            L.Show("roadworks", roads); L.Show("traffic", traffic);
        }
        /// <summary>Presentation: show networks and road works (the "Контроль стройки" step) or keep the city clean (other steps).</summary>
        public static bool TourOverlays;
        public static void ApplyTourLayers() => ApplyLayers();
        Button Chip(VisualElement parent, string text, System.Func<bool> get, System.Action toggle)
        {
            Button b = null; b = new Button(() => { toggle(); ApplyLayers(); b.EnableInClassList("active", get()); Refresh(); }) { text = text };
            b.AddToClassList("chip"); b.EnableInClassList("active", get()); parent.Add(b); return b;
        }

        static string Money(float bln) => bln >= 1000f ? Loc.N1(bln / 1000f) + " трлн ₸" : Loc.N0(bln) + " млрд ₸";

        protected override void Build()
        {
            if (bimMode) { BuildBim(); return; }
            var top = Widgets.Block(panel);
            eyebrow = Widgets.Eyebrow(top, "");
            summary = new Label(); summary.AddToClassList("summary"); summary.style.marginBottom = 12; top.Add(summary);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid); VisualElement row = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { row = new VisualElement(); row.AddToClassList("kpi-row"); grid.Add(row); }
                var k = new VisualElement(); k.AddToClassList("kpi");
                kl[i] = new Label(); kl[i].AddToClassList("l"); k.Add(kl[i]); kv[i] = new Label("—"); kv[i].AddToClassList("v"); k.Add(kv[i]);
                kb[i] = k; row.Add(k);
                SourceTags.Attach(k, i == 1 ? Sources.ModelCity : i == 3 ? TwinModels.Money : TwinModels.Build);
            }


            // one chart: commissioning plan vs fact (lines) over the money spent per year (columns)
            var cbk = Widgets.Block(panel, "Стройка: план, факт и деньги", "");
            var heads = new VisualElement(); heads.AddToClassList("bc-heads"); cbk.Add(heads);
            VisualElement Head(out Label v, out Label l) { var h = new VisualElement(); h.AddToClassList("bc-head"); v = new Label("—"); v.AddToClassList("bc-v"); l = new Label(); l.AddToClassList("bc-l"); h.Add(v); h.Add(l); heads.Add(h); return h; }
            Head(out bcV1, out bcL1); Head(out bcV2, out bcL2);
            bChart = new BuildChart { MoneyColors = SrcColors }; cbk.Add(bChart);
            // the money by source in the shown year: one thin segmented bar instead of four colours inside the chart
            srcBar = new VisualElement(); srcBar.AddToClassList("bc-src"); cbk.Add(srcBar);
            srcLeg = new VisualElement(); srcLeg.AddToClassList("bc-srcleg"); cbk.Add(srcLeg);
            sGap = new Label(); sGap.AddToClassList("note"); sGap.style.marginTop = 6; cbk.Add(sGap);
            moneyNote = new Label(); moneyNote.style.display = DisplayStyle.None; cbk.Add(moneyNote);
            cbk.Add(SourceTags.Line(TwinModels.Build, TwinModels.Money));
            // the year runs smoothly in the presentation: the chart follows it every frame
            bChart.schedule.Execute(() => { if (bChart.panel == null) return; float yf = Landmarks.LandmarkSystem.YearNow; if (Mathf.Abs(yf - bChart.Year) > 0.002f) { bChart.Year = yf; bChart.MarkDirtyRepaint(); } }).Every(33);

            Right();
            var nb = Widgets.Block(panel, Loc.T("c_nets"), Loc.T("c_nets_sub"));
            var chips = new VisualElement(); chips.AddToClassList("chips"); nb.Add(chips);
            chipNets = Chip(chips, Loc.T("c_chip_nets"), () => showNets, () => showNets = !showNets);
            chipRoads = Chip(chips, Loc.T("c_chip_roads"), () => showRoads, () => showRoads = !showRoads);
            chipTraffic = Chip(chips, Loc.T("c_chip_traffic"), () => showTraffic, () => showTraffic = !showTraffic);
            netRows = new VisualElement(); nb.Add(netRows);
            trafficNote = new Label(); trafficNote.AddToClassList("note"); trafficNote.style.marginTop = 6; nb.Add(trafficNote);
            nb.Add(SourceTags.Line(Sources.GenPlan, TwinModels.Build, TwinModels.Traffic));

            var wb = Widgets.Block(panel, Loc.T("c_worst"), Loc.T("c_worst_sub"));
            worstList = new VisualElement(); wb.Add(worstList); wb.Add(SourceTags.Line(TwinModels.Build));

            var cb = Widgets.Block(panel, Loc.T("c_contractors"), Loc.T("c_contractors_sub"));
            contractors = new VisualElement(); cb.Add(contractors); cb.Add(SourceTags.Line(TwinModels.Build));

            var n = Widgets.Block(panel); var note = new Label(Loc.T("c_note")); note.AddToClassList("note"); n.Add(note);
            // secondary blocks start folded: the first screen shows status, plan/fact and the worst sites
            Widgets.SetCollapsed(cb, true);
        }

        public override void Refresh()
        {
            if (bimMode) { RefreshBim(); return; }
            if (panel == null || !CityStats.Ready) return;
            int y = TwinState.Year, s = (int)TwinState.Scenario, d = TwinState.District;
            ConstructionLayer.Compute(y, s);
            eyebrow.text = (Loc.T("tab_construction") + " · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            int sites = ConstructionLayer.Sites, behind = ConstructionLayer.SitesBehind;
            float behindPct = sites > 0 ? 100f * behind / sites : 0;

            // money of the year (bln ₸): buildings + infrastructure, plan vs fact
            float plan = 0, fact = 0, infra = 0;
            if (TwinData.Ready)
            {
                int yi = TwinData.YI(y);
                for (int dd = 0; dd < 4; dd++) { for (int c = 0; c < 5; c++) plan += TwinData.CapexBuildings[s][dd][c][yi]; fact += TwinData.CapexFact[s][dd][yi]; }
                foreach (var kvp in TwinData.CapexInfra[s]) infra += kvp.Value[yi];
            }
            float planAll = plan + infra, factAll = fact + infra, pct = planAll > 0 ? 100f * factAll / planAll : 100f;

            if (sites == 0) summary.text = string.Format(Loc.T("c_sum_none"), y);
            else if (behind == 0) summary.text = string.Format(Loc.T("c_sum_ok"), y, Loc.N0(sites), Loc.N1(ConstructionLayer.GfaInWork / 1e6));
            else
            {
                int wc = -1, wv = 0; for (int c = 0; c < ConstructionLayer.BehindByContractor.Length; c++) if (ConstructionLayer.BehindByContractor[c] > wv) { wv = ConstructionLayer.BehindByContractor[c]; wc = c; }
                string who = wc >= 0 && TwinData.Ready ? TwinData.ContractorNames[wc] : "—";
                summary.text = behindPct > 97f ? string.Format(Loc.T("c_sum_tail"), y, Loc.N0(sites), who) : string.Format(Loc.T("c_sum"), y, Loc.N0(sites), Loc.N1(ConstructionLayer.GfaInWork / 1e6), Mathf.RoundToInt(behindPct), who);
            }
            Set(0, Loc.N0(sites), Loc.T("c_k_sites"), "");
            Set(1, Loc.N1(ConstructionLayer.GfaInWork / 1e6), Loc.T("c_k_gfa"), "");
            Set(2, Loc.N0(behind), string.Format(Loc.T("c_k_behind"), Mathf.RoundToInt(behindPct)), behindPct > 15 ? "bad" : behindPct > 5 ? "warn" : "ok");
            Set(3, Loc.N0(factAll), string.Format(Loc.T("c_k_money"), Mathf.RoundToInt(pct)), pct < 90 ? "warn" : "");

            // S-curve plan vs fact, mln m² cumulative
            if (TwinData.Ready)
            {
                var pl = new float[TwinData.NY]; var fa = new float[TwinData.NY];
                for (int i = 0; i < TwinData.NY; i++) for (int dd = 0; dd < 4; dd++) if (d < 0 || dd == d) { pl[i] += TwinData.PlanGfa[s][dd][i]; fa[i] += TwinData.FactGfa[s][dd][i]; }
                float gp = pl[TwinData.YI(y)], gf = fa[TwinData.YI(y)];
                sGap.text = gp - gf > 0.05f ? string.Format(Loc.T("c_gap"), y, Loc.N1(gp - gf), Mathf.RoundToInt(100f * (gp - gf) / Mathf.Max(gp, 0.01f)), Loc.N1(gp)) : string.Format(Loc.T("c_gap0"), y, Loc.N1(gp));

                var ser = new float[4][]; for (int k = 0; k < 4; k++) ser[k] = new float[TwinData.NY];
                for (int i = 0; i < TwinData.NY; i++)
                {
                    float inf = 0; foreach (var kvp in TwinData.CapexInfra[s]) inf += kvp.Value[i];
                    for (int k = 0; k < 4; k++) { float v = inf * InfraShare[k]; for (int dd = 0; dd < 4; dd++) v += TwinData.CapexSources[s][dd][k][i]; ser[k][i] = v; }
                }
                // the chart starts in the first year of the timeline; the data start in TwinData.Y0
                int k0 = TwinState.MinYear - TwinData.Y0; float[] Cut(float[] a) { var r = new float[a.Length - k0]; System.Array.Copy(a, k0, r, 0, r.Length); return r; }
                bChart.Plan = Cut(pl); bChart.Fact = Cut(fa); bChart.Money = System.Array.ConvertAll(ser, Cut); bChart.Year = Mathf.Max(y, Landmarks.LandmarkSystem.YearNow); bChart.Refresh();
                srcBar.Clear(); srcLeg.Clear(); int yi2 = TwinData.YI(y); float tot = 0; for (int k = 0; k < 4; k++) tot += ser[k][yi2];
                string[] srcK = { "src_budget", "src_private", "src_ppp", "src_quasi" };
                for (int k = 0; k < 4 && tot > 0; k++)
                {
                    float sh = ser[k][yi2] / tot; if (sh <= 0.001f) continue;
                    var seg = new VisualElement(); seg.AddToClassList("bc-seg"); seg.style.flexGrow = sh; seg.style.backgroundColor = SrcColors[k]; srcBar.Add(seg);
                    var it = new VisualElement(); it.AddToClassList("bc-si"); var dot = new VisualElement(); dot.AddToClassList("bc-sdot"); dot.style.backgroundColor = SrcColors[k]; it.Add(dot);
                    it.Add(new Label(Loc.T(srcK[k]) + " " + Mathf.RoundToInt(sh * 100f) + " %")); srcLeg.Add(it);
                }
                bcV1.text = Loc.N1(gf) + " млн м²"; bcL1.text = $"введено к {y} · {Mathf.RoundToInt(100f * gf / Mathf.Max(gp, 0.01f))} % плана";
                bcV2.text = Money(factAll); bcL2.text = $"освоено в {y} · {Mathf.RoundToInt(pct)} % плана года";
                moneyNote.text = string.Format(Loc.T("c_money_note"), y, Loc.N0(planAll), Loc.N0(factAll), Mathf.RoundToInt(pct), Loc.N0(infra));
            }

            // networks and roads being built this year
            netRows.Clear();
            if (TwinData.Ready)
            {
                string[] names = { "net_water", "net_sewer", "net_power", "net_heat", "net_gas", "net_telecom" };
                float total = 0;
                for (int k = 0; k < LineLayers.NetKeys.Length; k++)
                {
                    float w = LineLayers.KmInWork(LineLayers.NetKeys[k], y, s), b = LineLayers.KmBuilt(LineLayers.NetKeys[k], y, s); total += w;
                    var r = new VisualElement(); r.AddToClassList("net-row");
                    var sw = new VisualElement(); sw.AddToClassList("swatch"); sw.style.backgroundColor = LineLayers.NetColors[k]; r.Add(sw);
                    var n1 = new Label(Loc.T(names[k])); n1.AddToClassList("n"); r.Add(n1);
                    var v1 = new Label(Loc.N0(b) + " " + Loc.T("km")); v1.AddToClassList("v"); v1.AddToClassList("muted"); r.Add(v1);
                    var w1 = new Label(w >= 0.5f ? "+" + Loc.N0(w) + " " + Loc.T("km") : "—"); w1.AddToClassList("w"); r.Add(w1);
                    netRows.Add(r);
                }
                float rk = LineLayers.RoadKmInWork(y, s);
                var rr = new VisualElement(); rr.AddToClassList("net-row"); rr.style.borderBottomWidth = 0;
                var sw2 = new VisualElement(); sw2.AddToClassList("swatch"); sw2.style.backgroundColor = LineLayers.RoadWorkColor; rr.Add(sw2);
                var n2 = new Label(Loc.T("net_roads")); n2.AddToClassList("n"); rr.Add(n2);
                var w2 = new Label(rk >= 0.5f ? "+" + Loc.N0(rk) + " " + Loc.T("km") : "—"); w2.AddToClassList("w"); rr.Add(w2);
                netRows.Add(rr);
                int ti = 0; while (ti < TwinData.TrafficYears.Length - 1 && TwinData.TrafficYears[ti] < y) ti++;
                var kpi = TwinData.TrafficKpi[s][ti];
                trafficNote.text = string.Format(Loc.T("c_traffic_note"), Loc.N0(total), Loc.N0(rk), TwinData.TrafficYears[ti],
                    Loc.N0(kpi.TryGetValue("congested_km", out var ck) ? ck : 0), Loc.N0(kpi.TryGetValue("avg_delay_pct", out var dp) ? dp : 0));
            }

            // worst sites
            worstList.Clear();
            var db = CityDatabase.Instance;
            if (ConstructionLayer.Worst.Count == 0) { var l = new Label(Loc.T("c_worst_none")); l.AddToClassList("note"); worstList.Add(l); }
            foreach (var site in ConstructionLayer.Worst)
            {
                var b = db != null ? db.Get(site.Bid) : null; if (b == null) continue;
                var r = new VisualElement(); r.AddToClassList("trow"); r.AddToClassList("clickable"); r.style.flexDirection = FlexDirection.Column; r.style.alignItems = Align.Stretch;
                var top1 = new VisualElement(); top1.AddToClassList("row");
                top1.Add(Widgets.Dot(new Color(1f, 0.23f, 0.18f), true));
                var nm = new Label(Loc.Kind(b.Kind) + " · " + b.District) { pickingMode = PickingMode.Ignore }; nm.style.flexGrow = 1; top1.Add(nm);
                var dl = new Label("+" + site.DelayMonths + " " + Loc.T("months")) { pickingMode = PickingMode.Ignore }; dl.style.color = new Color(1f, 0.23f, 0.18f); top1.Add(dl);
                r.Add(top1);
                int c = ConstructionLayer.ContractorOf(site.Bid);
                var sub = new Label(string.Format(Loc.T("c_worst_row"), c < 255 && TwinData.Ready ? TwinData.ContractorNames[c] : "—", Loc.N0(site.Gfa), site.PlanYear, site.FactYear, Mathf.RoundToInt(site.Progress * 100)))
                { pickingMode = PickingMode.Ignore };
                sub.AddToClassList("note"); sub.style.marginTop = 2; sub.style.marginLeft = 14; r.Add(sub);
                int bid = site.Bid; r.AddManipulator(new Clickable(() => FocusBuilding(bid)));
                worstList.Add(r);
            }

            // contractors ranking
            contractors.Clear();
            if (TwinData.Ready)
            {
                var idx = Enumerable.Range(0, ConstructionLayer.SitesByContractor.Length).Where(i => ConstructionLayer.SitesByContractor[i] > 0)
                    .OrderByDescending(i => ConstructionLayer.BehindByContractor[i] / (float)ConstructionLayer.SitesByContractor[i]).Take(4).ToList();
                if (idx.Count == 0) { var l = new Label(Loc.T("c_worst_none")); l.AddToClassList("note"); contractors.Add(l); }
                foreach (var i in idx)
                {
                    float share = 100f * ConstructionLayer.BehindByContractor[i] / ConstructionLayer.SitesByContractor[i];
                    var f = Widgets.Fact(TwinData.ContractorNames[i] + "  ·  " + Loc.N0(ConstructionLayer.SitesByContractor[i]) + " " + Loc.T("c_sites_short"), "");
                    f.RemoveAt(1); f.Add(Widgets.Status(Mathf.RoundToInt(share) + " % " + Loc.T("c_behind_short"), share > 15 ? "bad" : share > 5 ? "warn" : "ok"));
                    contractors.Add(f);
                }
            }
        }

        void Set(int i, string v, string l, string cls)
        {
            kv[i].text = v; kl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) kb[i].RemoveFromClassList(c);
            if (cls != "") kb[i].AddToClassList(cls);
        }

        static void FocusBuilding(int bid)
        {
            var db = CityDatabase.Instance; var b = db != null ? db.Get(bid) : null; if (b == null) return;
            var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
            if (cam != null) cam.FlyTo(new MapCamera.View { name = b.Id, target = new Vector3(b.X, b.GroundM, b.Z), distance = Mathf.Max(700f, b.HeightM * 9f), yaw = cam.yaw, pitch = 42f });
            var sel = Camera.main != null ? Camera.main.GetComponent<TwinSelector>() : null;
            if (sel != null) sel.Select(bid); else TwinState.SetSelected(b);
        }
    }
}
