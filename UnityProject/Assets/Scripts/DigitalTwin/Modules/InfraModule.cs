using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M3 — Infrastructure: every network and facility of the master plan and the model, capacity vs load in year N,
    /// staging (what comes into service when), facility cards, and a single-line diagram of the power grid (220 → 110 kV).</summary>
    public class InfraModule : TwinModuleBase
    {
        public override string Id => "infra";
        public override string TabKey => "tab_infra";

        // resource = balance key; network layers that belong to it; facility "res" values
        static readonly (string key, string name, string unit, string[] nets, string[] fac, Color color)[] Res =
        {
            ("power_hv", "res_power_hv", "МВт", new[] { "power" }, new[] { "power_hv" }, new Color(1f, 0.84f, 0.04f)),
            ("power", "res_power", "МВт", new[] { "power" }, new[] { "power", "renewable" }, new Color(1f, 0.70f, 0.10f)),
            ("heat", "res_heat", "Гкал/ч", new[] { "heat" }, new[] { "heat" }, new Color(1f, 0.48f, 0.27f)),
            ("gas", "res_gas", "тыс. м³/ч", new[] { "gas" }, new[] { "gas" }, new Color(0.75f, 0.52f, 0.99f)),
            ("water", "res_water", "тыс. м³/сут", new[] { "water" }, new[] { "water" }, new Color(0.30f, 0.64f, 1f)),
            ("sewer", "res_sewer", "тыс. м³/сут", new[] { "sewer" }, new[] { "sewer" }, new Color(0.66f, 0.50f, 0.33f)),
        };
        static int focus = -1;                 // -1 = all networks, else index in Res
        static bool showLrt = true, showPlanned = true;
        static string selectedFac;

        Label eyebrow, summary; readonly Label[] kv = new Label[4], kl = new Label[4]; readonly VisualElement[] kb = new VisualElement[4];
        VisualElement rows, card, next, scheme; SchemeView schemeView;
        VisualElement netBox, netChips; static int netDistrict = 2, lastHeader = -1;

        public InfraModule() { InvestRegistry.Init(); }

        public override (Color, string)[] Legend => new[]
        {
            (LineLayers.NetColors[0], Loc.T("net_water")), (LineLayers.NetColors[1], Loc.T("net_sewer")), (LineLayers.NetColors[2], Loc.T("net_power")),
            (LineLayers.NetColors[3], Loc.T("net_heat")), (LineLayers.NetColors[4], Loc.T("net_gas")), (LineLayers.NetColors[5], Loc.T("net_telecom")),
        };

        public override void OnEnter() { ApplyLayers(); BuildPins(); }
        public override void OnExit() { LineLayers.Instance?.HideAll(); MapPins.Instance?.Clear(); }

        void ApplyLayers()
        {
            var L = LineLayers.Instance; if (L == null) return;
            L.Style(0.95f, showPlanned ? 0.16f : 0f, 1f);
            var on = focus < 0 ? LineLayers.NetKeys : Res[focus].nets;
            foreach (var k in LineLayers.NetKeys) L.Show(k, on.Contains(k));
            L.Show("roadworks", false); L.Show("traffic", false);
        }

        // ------------------------------------------------------------------ facility status in the current year
        public static string Status(TwinData.Facility f, int s, int y, out float util)
        {
            util = 0;
            if (f.Res == "renewable") return f.Stages[s][0] <= y ? "ok" : "planned";
            if (f.Res == "telecom") return f.Stages[s][0] <= y ? "ok" : "planned";
            float cap = f.CapAt(s, y), dem = f.DemandAt(s, y);
            if (f.Stages[s].Length > 0 && f.Stages[s][0] > y && dem <= 0.01f) return "planned";
            if (f.Res == "water" || f.Res == "gas")
            {
                // pooled city systems: intakes / AGRS share the load, so the status is the system's
                var b = TwinData.BalanceOf(s, f.Res, -1); int yi = TwinData.YI(y);
                if (b != null) { util = b.Cap[yi] > 0 ? b.Demand[yi] / b.Cap[yi] : 0; return b.Deficit[yi] > 0.5f ? "bad" : util > 0.85f ? "warn" : "ok"; }
            }
            util = cap > 0 ? dem / cap : (dem > 0 ? 9f : 0f);
            return util > 1.0f ? "bad" : util > 0.85f ? "warn" : "ok";
        }
        static Color ResColor(string res) => res switch
        {
            "power_hv" => new Color(1f, 0.84f, 0.04f), "power" => new Color(1f, 0.70f, 0.10f), "renewable" => new Color(0.55f, 0.85f, 0.35f), "heat" => new Color(1f, 0.48f, 0.27f),
            "gas" => new Color(0.75f, 0.52f, 0.99f), "water" => new Color(0.30f, 0.64f, 1f), "sewer" => new Color(0.66f, 0.50f, 0.33f), "telecom" => new Color(0.18f, 0.83f, 0.75f),
            _ => Color.white
        };

        void BuildPins()
        {
            var P = MapPins.Instance; if (P == null || !TwinData.Ready) return;
            int s = (int)TwinState.Scenario, y = TwinState.Year;
            var list = new List<MapPins.Pin>();
            var resSet = focus < 0 ? null : Res[focus].fac;
            foreach (var f in TwinData.Facilities)
            {
                if (resSet != null && !resSet.Contains(f.Res)) continue;
                string st = Status(f, s, y, out _);
                if (st == "planned" && !showPlanned) continue;
                var c = ResColor(f.Res); if (st == "planned") c.a = 0.35f;
                var fac = f;
                list.Add(new MapPins.Pin
                {
                    Id = f.Id, Label = f.Name, World = new Vector3(f.X, CityGround.HeightAt(f.X, f.Z) + 40f, f.Z), Fill = c, Status = st == "ok" ? "" : st,
                    ShowLabel = st == "bad" || f.Res == "power_hv", Size = f.Res == "power_hv" || f.Res == "water" || f.Res == "sewer" || f.Res == "gas" ? 16f : 12f,
                    OnClick = () => SelectFacility(fac.Id)
                });
            }
            if (showLrt && focus < 0)
            {
                for (int i = 0; i < TwinData.LrtStations.Length; i++)
                {
                    var p = TwinData.LrtStations[i]; int ph = Mathf.RoundToInt(p.z); bool open = TwinData.LrtPhaseYear[s][ph] <= y;
                    if (!open && !showPlanned) continue;
                    var col = new Color(0.85f, 0.27f, 0.94f, open ? 1f : 0.35f);
                    list.Add(new MapPins.Pin { Id = "lrt" + i, Label = string.Format(Loc.T("lrt_station"), TwinData.LrtPhaseNames[ph], TwinData.LrtPhaseYear[s][ph]),
                        World = new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + 30f, p.y), Fill = col, Size = 9f, Status = open ? "" : "planned" });
                }
            }
            P.Set(list); P.Select(selectedFac);
        }

        void SelectFacility(string id)
        {
            selectedFac = id; MapPins.Instance?.Select(id);
            var f = TwinData.Facilities.FirstOrDefault(x => x.Id == id);
            if (f != null)
            {
                var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
                if (cam != null) cam.FlyTo(new MapCamera.View { name = f.Name, target = new Vector3(f.X, CityGround.HeightAt(f.X, f.Z), f.Z), distance = 3200f, yaw = cam.yaw, pitch = 48f });
            }
            Refresh();
        }

        // ------------------------------------------------------------------ panel
        protected override void Build()
        {
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
            }
            var chips = new VisualElement(); chips.AddToClassList("chips"); chips.style.marginTop = 10; top.Add(chips);
            Chip(chips, Loc.T("i_chip_lrt"), () => showLrt, () => showLrt = !showLrt);
            Chip(chips, Loc.T("i_chip_planned"), () => showPlanned, () => showPlanned = !showPlanned);

            BuildPublished();

            var rb = Widgets.Block(panel, Loc.T("i_balance"), Loc.T("i_balance_sub"));
            rows = new VisualElement(); rb.Add(rows);

            Right();
            card = new VisualElement(); panel.Add(card);

            var wb = Widgets.Block(panel, "Когда сети придут на участок", "по району и сценарию");
            var wi = new Label("Для инвестора: с какого года мощности района хватит, чтобы подключить новый объект, — по каждому ресурсу.");
            wi.AddToClassList("note"); wi.style.marginBottom = 6; wb.Add(wi);
            netChips = new VisualElement(); netChips.AddToClassList("chips"); netChips.AddToClassList("w2-chips"); wb.Add(netChips);
            for (int d = 0; d < CityStats.Districts; d++)
            {
                int dd = d; var btn = new Button(() => { netDistrict = dd; RefreshNet(); }) { text = CityStats.DistrictIds[d], focusable = false };
                btn.AddToClassList("chip"); netChips.Add(btn);
            }
            netBox = new VisualElement(); wb.Add(netBox);

            var sb = Widgets.Block(panel, Loc.T("i_scheme"), Loc.T("i_scheme_sub"));
            schemeView = new SchemeView(); sb.Add(schemeView);
            scheme = new VisualElement(); sb.Add(scheme);

            var nb = Widgets.Block(panel, Loc.T("i_next"), Loc.T("i_next_sub"));
            next = new VisualElement(); nb.Add(next);

            var n = Widgets.Block(panel); var note = new Label(Loc.T("i_note")); note.AddToClassList("note"); n.Add(note);
            Widgets.SetCollapsed(nb, true);
        }

        void Chip(VisualElement parent, string text, System.Func<bool> get, System.Action toggle)
        {
            Button b = null; b = new Button(() => { toggle(); ApplyLayers(); BuildPins(); b.EnableInClassList("active", get()); }) { text = text };
            b.AddToClassList("chip"); b.EnableInClassList("active", get()); parent.Add(b);
        }

        public override void Refresh()
        {
            if (panel == null || !TwinData.Ready || summary == null) return;
            int s = (int)TwinState.Scenario, y = TwinState.Year;
            BuildPins();
            eyebrow.text = (Loc.T("tab_infra") + " · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();

            // KPIs
            int inService = 0, total = 0, over = 0, warn = 0; string worstName = null; float worstUtil = 0;
            foreach (var f in TwinData.Facilities)
            {
                if (f.Res == "telecom") continue; total++;
                var st = Status(f, s, y, out float u);
                if (st != "planned") inService++;
                if (st == "bad") { over++; if (u > worstUtil) { worstUtil = u; worstName = f.Name; } }
                if (st == "warn") warn++;
            }
            float km = 0; foreach (var k in LineLayers.NetKeys) km += LineLayers.KmBuilt(k, y, s);
            // deficits by resource (unserved load)
            var deficits = new List<string>();
            for (int i = 0; i < Res.Length; i++)
            {
                var b = TwinData.BalanceOf(s, Res[i].key, -1); if (b == null) continue;
                float d = b.Deficit[TwinData.YI(y)]; if (d > 0.5f) deficits.Add(Loc.T(Res[i].name).ToLower() + " " + Fmt(Res[i].key, d) + " " + Res[i].unit);
            }
            if (deficits.Count == 0) summary.text = string.Format(Loc.T("i_sum_ok"), y, inService, total);
            else summary.text = string.Format(Loc.T("i_sum_def"), y, string.Join(", ", deficits), worstName ?? "—");
            Set(0, inService + " / " + total, Loc.T("i_k_fac"), "");
            Set(1, Loc.N0(km), Loc.T("i_k_km"), "");
            Set(2, over.ToString(), Loc.T("i_k_over"), over > 0 ? "bad" : "ok");
            Set(3, warn.ToString(), Loc.T("i_k_warn"), warn > 0 ? "warn" : "ok");

            // balance rows: demand vs capacity per resource, click = focus that network
            rows.Clear();
            for (int i = 0; i < Res.Length; i++)
            {
                var b = TwinData.BalanceOf(s, Res[i].key, -1); if (b == null) continue;
                int yi = TwinData.YI(y); float dem = b.Demand[yi], cap = b.Cap[yi], def = b.Deficit[yi];
                float u = cap > 0 ? dem / cap : 0;
                var r = new VisualElement(); r.AddToClassList("stage-row"); r.AddToClassList("clickable"); if (focus == i) r.AddToClassList("active");
                r.style.paddingLeft = 6; r.style.paddingRight = 6; r.style.borderTopLeftRadius = r.style.borderTopRightRadius = r.style.borderBottomLeftRadius = r.style.borderBottomRightRadius = 6;
                var t = new VisualElement(); t.AddToClassList("top");
                var sw = new VisualElement(); sw.AddToClassList("swatch"); sw.style.backgroundColor = Res[i].color; sw.style.alignSelf = Align.Center; t.Add(sw);
                var n = new Label(Loc.T(Res[i].name)) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); t.Add(n);
                var v = new Label(Fmt(Res[i].key, dem) + " / " + Fmt(Res[i].key, cap) + " " + Res[i].unit) { pickingMode = PickingMode.Ignore }; v.AddToClassList("v"); t.Add(v);
                r.Add(t);
                var bar = new VisualElement { pickingMode = PickingMode.Ignore }; bar.AddToClassList("bar");
                var bf = new VisualElement { pickingMode = PickingMode.Ignore }; bf.AddToClassList("f"); bf.style.width = Length.Percent(Mathf.Clamp01(u) * 100);
                bf.style.backgroundColor = def > 0.5f ? new Color(1f, 0.23f, 0.18f) : u > 0.85f ? new Color(0.96f, 0.65f, 0.14f) : new Color(0.20f, 0.78f, 0.35f); bar.Add(bf);
                r.Add(bar);
                var sub = new Label(def > 0.5f ? string.Format(Loc.T("i_row_def"), Fmt(Res[i].key, def), Res[i].unit) : string.Format(Loc.T("i_row_ok"), Mathf.RoundToInt(u * 100))) { pickingMode = PickingMode.Ignore };
                sub.AddToClassList("note"); sub.style.marginTop = 3; if (def > 0.5f) sub.style.color = new Color(1f, 0.23f, 0.18f); r.Add(sub);
                int idx = i; r.AddManipulator(new Clickable(() => { focus = focus == idx ? -1 : idx; ApplyLayers(); Refresh(); }));
                rows.Add(r);
            }
            var hint = new Label(Loc.T(focus < 0 ? "i_focus_hint" : "i_focus_all")); hint.AddToClassList("note"); hint.style.marginTop = 6; rows.Add(hint);

            // facility card
            card.Clear();
            var fsel = selectedFac != null ? TwinData.Facilities.FirstOrDefault(x => x.Id == selectedFac) : null;
            if (fsel != null) BuildCard(fsel, s, y);

            // single-line power scheme 220 → 110 kV
            schemeView.Set(s, y);
            scheme.Clear();
            var sn = new Label(Loc.T("i_scheme_note")); sn.AddToClassList("note"); sn.style.marginTop = 4; scheme.Add(sn);

            // staging: what comes into service in the next 3 years
            next.Clear(); int cnt = 0;
            foreach (var f in TwinData.Facilities.OrderBy(f => f.Stages[s].Length > 0 ? f.Stages[s].Where(v => v > y).DefaultIfEmpty(9999).Min() : 9999))
            {
                if (f.Stages[s].Length == 0) continue;
                int ny = f.Stages[s].Where(v => v > y).DefaultIfEmpty(9999).Min(); if (ny > y + 3) continue;
                int stageNo = System.Array.IndexOf(f.Stages[s], ny) + 1;
                bool late = f.DelayedStages.Contains(stageNo) && TwinState.Scenario != Scenario.InfraFirst;
                var fct = Widgets.Fact(f.Name, ny + (f.Stages[s].Length > 1 ? " · " + string.Format(Loc.T("i_stage"), stageNo) : ""));
                if (late) fct.Q<Label>(className: "v").style.color = new Color(1f, 0.23f, 0.18f);
                var fid = f.Id; fct.AddManipulator(new Clickable(() => SelectFacility(fid))); fct.AddToClassList("clickable");
                next.Add(fct); if (++cnt >= 7) break;
            }
            if (cnt == 0) { var l = new Label(Loc.T("i_next_none")); l.AddToClassList("note"); next.Add(l); }
            RefreshNet();
        }

        /// <summary>The published infrastructure items: of the 26 projects of the government summary only some are named in the press.</summary>
        void BuildPublished()
        {
            var b = Widgets.Block(panel, "Инфраструктурные проекты", "что опубликовано в прессе");
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); b.Add(grid);
            var r = new VisualElement(); r.AddToClassList("kpi-row"); grid.Add(r);
            void K(string v, string l, string src) { var k = new VisualElement(); k.AddToClassList("kpi"); var a = new Label(l); a.AddToClassList("l"); k.Add(a); var c = new Label(v); c.AddToClassList("v"); c.AddToClassList("w2-kpi-long"); k.Add(c); SourceTags.Attach(k, src); r.Add(k); }
            K("26", "проектов в программе", Sources.GovSummary);
            K("365,1\u00A0млрд\u00A0₸", "этап 1, 2026–2027", InvestRegistry.KapInfra);
            foreach (var it in InvestRegistry.Infra)
            {
                var row = new VisualElement(); row.AddToClassList("w2-inf");
                var top = new VisualElement(); top.AddToClassList("w2-inf-top");
                var n = new Label(it.Name); n.AddToClassList("w2-inf-n"); top.Add(n);
                top.Add(Widgets.Status(it.Status, it.StatusCls)); row.Add(top);
                string meta = it.Amount != null ? string.Format("{0} · {1} · {2}", it.What, it.When, it.Amount) : string.Format("{0} · {1}", it.What, it.When);
                var m = new Label(meta); m.AddToClassList("note"); row.Add(m);
                var tagRow = new VisualElement(); tagRow.AddToClassList("w2-inf-tags");
                var kind = new Label(it.Kind); kind.AddToClassList("w2-kind"); tagRow.Add(kind);
                tagRow.Add(SourceTags.Tag(it.Src)); row.Add(tagRow);
                b.Add(row);
            }
            var honest = new Label(string.Format("Названо в прессе: {0} позиций (часть — пакеты проектов). Полный список 26 проектов не публиковался. Базовые сети финансирует государство, городу разрешены госзаймы.", InvestRegistry.Infra.Count));
            honest.AddToClassList("note"); honest.style.marginTop = 6; b.Add(honest);
            b.Add(SourceTags.Line(InvestRegistry.KapLoans));
        }

        void RefreshNet()
        {
            if (netBox == null) return;
            if (TwinState.District != lastHeader) { lastHeader = TwinState.District; if (lastHeader >= 0) netDistrict = lastHeader; }   // the header district wins once, chips after it
            int d = netDistrict;
            int i = 0; foreach (var c in netChips.Children()) { c.EnableInClassList("active", i == d); i++; }
            netBox.Clear();
            var h = new Label(string.Format("{0} District · {1} · отсчёт от октября 2026", CityStats.DistrictIds[d], TwinScenario.Name(TwinState.Scenario)));
            h.AddToClassList("w2-h"); netBox.Add(h);
            netBox.Add(InvestCalc.NetRows(d));
        }

        void BuildCard(TwinData.Facility f, int s, int y)
        {
            var b = Widgets.Block(card, f.Name, f.Synthetic ? Loc.T("i_model") : Loc.T("i_plan"));
            var st = Status(f, s, y, out float u);
            string unit = TwinData.Units.TryGetValue(f.Res, out var un) ? un : "";
            b.Add(Widgets.Fact(Loc.T("p_district"), CityStats.DistrictIds[Mathf.Clamp(f.District, 0, 3)] + " District"));
            if (f.Cap != null && f.Res != "renewable")
            {
                b.Add(Widgets.Fact(Loc.T("i_c_cap"), Fmt(f.Res, f.CapAt(s, y)) + " " + unit));
                b.Add(Widgets.Fact(Loc.T("i_c_load"), Fmt(f.Res, f.DemandAt(s, y)) + " " + unit + (u > 0 ? "  ·  " + Mathf.RoundToInt(u * 100) + " %" : "")));
            }
            else if (f.Res == "renewable") b.Add(Widgets.Fact(Loc.T("i_c_cap"), Loc.N0(f.Unit) + " МВт"));
            if (f.Stages[s].Length > 0) b.Add(Widgets.Fact(Loc.T("i_c_stages"), string.Join(", ", f.Stages[s].Select(v => v.ToString()))));
            if (f.DelayedStages.Length > 0 && TwinState.Scenario != Scenario.InfraFirst)
                b.Add(Widgets.Fact(Loc.T("i_c_delay"), string.Format(Loc.T("i_c_delay_v"), string.Join(", ", f.DelayedStages))));
            var stf = Widgets.Fact(Loc.T("p_status"), ""); stf.RemoveAt(1);
            stf.Add(Widgets.Status(Loc.T("i_st_" + st), st == "planned" ? "muted" : st)); stf.style.borderBottomWidth = 0; b.Add(stf);
            if (!string.IsNullOrEmpty(f.Note)) { var n = new Label(f.Note); n.AddToClassList("note"); n.style.marginTop = 6; b.Add(n); }
            var close = Widgets.Btn(Loc.T("i_close"), () => { selectedFac = null; MapPins.Instance?.Select(null); Refresh(); }, "small", "ghost");
            close.style.alignSelf = Align.FlexEnd; close.style.marginTop = 4; b.Add(close);
        }

        static string Fmt(string res, float v) => res == "water" || res == "sewer" || res == "gas" ? Loc.N1(v / 1000f) : Loc.N0(v);

        void Set(int i, string v, string l, string cls)
        {
            kv[i].text = v; kl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) kb[i].RemoveFromClassList(c);
            if (cls != "") kb[i].AddToClassList(cls);
        }

        /// <summary>Single-line diagram: 4 feeding substations 220/110 kV, each with its 110/10 kV substations; colour = loading.</summary>
        class SchemeView : VisualElement
        {
            int s, y;
            public SchemeView() { style.height = 190; pickingMode = PickingMode.Ignore; generateVisualContent += Draw; }
            public void Set(int scen, int year) { s = scen; y = year; Clear(); MarkDirtyRepaint(); schedule.Execute(Labels); }
            static Color C(string st) => st == "bad" ? new Color(1f, 0.23f, 0.18f) : st == "warn" ? new Color(0.96f, 0.65f, 0.14f) : st == "planned" ? new Color(0.35f, 0.35f, 0.35f) : new Color(0.20f, 0.78f, 0.35f);
            void Labels()
            {
                // placed in percent of the width: before the first layout contentRect is NaN, which stacked all four labels at the left edge
                Clear();
                for (int d = 0; d < 4; d++)
                {
                    var l = new Label(CityStats.DistrictIds[d]) { pickingMode = PickingMode.Ignore };
                    l.style.position = Position.Absolute; l.style.left = Length.Percent(d * 25f); l.style.width = Length.Percent(25f); l.style.top = 0; l.style.fontSize = 10;
                    l.style.unityTextAlign = TextAnchor.UpperCenter; l.style.color = new Color(0.76f, 0.76f, 0.76f); Add(l);
                }
                var k = new Label("220 кВ → 110 кВ") { pickingMode = PickingMode.Ignore }; k.style.position = Position.Absolute; k.style.right = 0; k.style.bottom = 0; k.style.fontSize = 10; k.style.color = new Color(0.53f, 0.53f, 0.53f); Add(k);
            }
            void Draw(MeshGenerationContext ctx)
            {
                if (!TwinData.Ready) return;
                var p = ctx.painter2D; float w = contentRect.width; if (w <= 0) return;
                p.lineWidth = 1.5f;
                for (int d = 0; d < 4; d++)
                {
                    float cx = w * (d + 0.5f) / 4f, hy = 30;
                    var hv = TwinData.Facilities.FirstOrDefault(f => f.Res == "power_hv" && f.District == d);
                    var subs = TwinData.Facilities.Where(f => f.Res == "power" && f.District == d).ToList();
                    string hs = hv != null ? Status(hv, s, y, out _) : "planned";
                    // bus bar of the district
                    p.strokeColor = new Color(0.35f, 0.35f, 0.35f); p.BeginPath(); p.MoveTo(new Vector2(cx, hy + 9)); p.LineTo(new Vector2(cx, hy + 26)); p.Stroke();
                    float bw = Mathf.Min(w / 4f - 14, 70); p.BeginPath(); p.MoveTo(new Vector2(cx - bw / 2, hy + 26)); p.LineTo(new Vector2(cx + bw / 2, hy + 26)); p.Stroke();
                    // HV substation: square
                    p.fillColor = C(hs); p.BeginPath(); p.MoveTo(new Vector2(cx - 8, hy - 8)); p.LineTo(new Vector2(cx + 8, hy - 8)); p.LineTo(new Vector2(cx + 8, hy + 8)); p.LineTo(new Vector2(cx - 8, hy + 8)); p.ClosePath(); p.Fill();
                    // 110 kV substations: a column of circles hanging off the bus
                    int n = subs.Count; int cols = Mathf.Max(1, Mathf.Min(3, n)); int rowsN = Mathf.CeilToInt(n / (float)cols);
                    for (int i = 0; i < n; i++)
                    {
                        int c = i % cols, r = i / cols;
                        float x = cx - bw / 2 + bw * (c + 0.5f) / cols, yy = hy + 44 + r * 30;
                        p.strokeColor = new Color(0.35f, 0.35f, 0.35f); p.BeginPath(); p.MoveTo(new Vector2(x, hy + 26)); p.LineTo(new Vector2(x, yy - 7)); p.Stroke();
                        p.fillColor = C(Status(subs[i], s, y, out _)); p.BeginPath(); p.Arc(new Vector2(x, yy), 7, 0, 360); p.Fill();
                    }
                    if (rowsN > 4) { }
                }
            }
        }
    }
}
