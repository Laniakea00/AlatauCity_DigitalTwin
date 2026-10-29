using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;
using Inc = AlatauCity.DigitalTwin.Modules.SituationData.Incident;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M4 — Situational Center (operation stage): one accelerated day of the city in year N.
    /// Event feed with filters, incidents with pins and cards, the list of data streams, the morning briefing for the akim,
    /// and the key function — two branches side by side: "decision taken" vs "not taken" (people, damage, recovery, load, CO₂).</summary>
    public class SituationModule : TwinModuleBase
    {
        public override string Id => "situation";
        public override string TabKey => "tab_situation";

        static int view;                         // 0 feed, 1 incidents, 2 sources, 3 briefing
        static string selInc; static bool mapTaken; static int tIdx = SituationData.NT - 1;
        static int clock = 8 * 60; static bool running = true;
        static readonly HashSet<string> srcOff = new HashSet<string>(); static bool onlyImportant;
        static readonly Dictionary<string, int> decided = new Dictionary<string, int>();   // incident id → minute of decision
        static readonly List<SituationData.Ev> extra = new List<SituationData.Ev>();      // operator actions added to the feed

        static string key; static List<Inc> incs = new List<Inc>(); static List<SituationData.Ev> day = new List<SituationData.Ev>(); static List<SituationData.Source> sources = new List<SituationData.Source>();
        static readonly Color OK = new Color(0.20f, 0.78f, 0.35f), WARN = new Color(0.96f, 0.65f, 0.14f), BAD = new Color(1f, 0.23f, 0.18f), MUTED = new Color(0.53f, 0.53f, 0.53f);

        Label eyebrow, summary, clockLbl; readonly Label[] kv = new Label[4], kl = new Label[4]; readonly VisualElement[] kb = new VisualElement[4];
        VisualElement body, notice, topGrid; Button playBtn; readonly List<Button> viewChips = new List<Button>();
        IVisualElementScheduledItem tick; int lastEvCount = -1, tickN;
        readonly List<Label> sampleLabels = new List<Label>();

        public override (Color, string)[] Legend => selInc != null
            ? new[] { (selInc == "flood" ? new Color(0.30f, 0.55f, 1f) : mapTaken ? WARN : BAD, Loc.T(mapTaken ? "s_lg_yes" : "s_lg_no")), (new Color(0.62f, 0.62f, 0.62f), Loc.T("s_lg_ctx")) }
            : new[] { (BAD, Loc.T("s_lg_active")), (WARN, Loc.T("s_lg_forecast")), (MUTED, Loc.T("s_lg_plan")), (OK, Loc.T("s_lg_done")) };

        public override void OnEnter() { }
        public override void OnExit()
        {
            tick?.Pause(); MapPins.Instance?.Clear(); TintLayer.Disable(); LineLayers.Instance?.HideAll(); LineLayers.JamOff();
        }

        static int Y => TwinState.Year; static int S => (int)TwinState.Scenario;
        static bool Operating => Y >= 2030;
        static DateTime Today => new DateTime(Y, 11, 18);

        void Ensure()
        {
            string k = S + ":" + Y; if (k == key || !TwinData.Ready || CityDatabase.Instance == null) return;
            key = k; incs = SituationData.Incidents(S, Y); day = SituationData.Day(S, Y, incs); sources = SituationData.Sources(S, Y);
            decided.Clear(); extra.Clear(); lastEvCount = -1;
            if (selInc != null && incs.All(i => i.Id != selInc)) selInc = null;
        }

        // ------------------------------------------------------------------ status of an incident at the current clock
        static string State(Inc i)
        {
            if (decided.ContainsKey(i.Id)) return "done";
            if (!i.Avail) return "na";
            if (i.Today && clock < i.StartMin) return i.Kind == "forecast" ? "forecast" : "later";
            return i.Kind;   // active / forecast / plan / drill
        }
        static string StatusText(Inc i)
        {
            var st = State(i);
            return st switch
            {
                "done" => string.Format(Loc.T("s_st_done"), Hm(decided[i.Id])), "na" => string.Format(Loc.T("s_st_na"), i.SuggestYear),
                "active" => i.Today ? string.Format(Loc.T("s_st_active"), Hm(i.StartMin)) : Loc.T("s_st_active0"), "forecast" => Loc.T("s_st_forecast"),
                "plan" => Loc.T("s_st_plan"), "drill" => Loc.T("s_st_drill"), "later" => Loc.T("s_st_later"), _ => ""
            };
        }
        static string StatusCls(Inc i) => State(i) switch { "done" => "ok", "active" => "bad", "forecast" => "warn", _ => "muted" };
        static string Hm(int m) => $"{(m / 60) % 24:00}:{m % 60:00}";
        static IEnumerable<Inc> NeedDecision => incs.Where(i => i.Avail && (State(i) == "active" || State(i) == "forecast") && (i.Today || i.Kind == "active"));

        // ------------------------------------------------------------------ panel
        protected override void Build()
        {
            var top = Widgets.Block(panel);
            eyebrow = Widgets.Eyebrow(top, "");
            summary = new Label(); summary.AddToClassList("summary"); summary.style.marginBottom = 10; top.Add(summary);
            notice = new VisualElement(); top.Add(notice);
            topGrid = new VisualElement(); topGrid.AddToClassList("kpi-grid"); top.Add(topGrid); VisualElement r0 = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { r0 = new VisualElement(); r0.AddToClassList("kpi-row"); topGrid.Add(r0); }
                var k = new VisualElement(); k.AddToClassList("kpi");
                kl[i] = new Label(); kl[i].AddToClassList("l"); k.Add(kl[i]); kv[i] = new Label("—"); kv[i].AddToClassList("v"); k.Add(kv[i]);
                kb[i] = k; r0.Add(k);
            }
            top.Add(SourceTags.Line(TwinModels.Ops));
            var cr = new VisualElement(); cr.AddToClassList("row"); cr.style.marginTop = 10; top.Add(cr);
            playBtn = Widgets.Btn(Loc.T("pause"), () => { running = !running; playBtn.text = Loc.T(running ? "pause" : "play"); }, "small"); cr.Add(playBtn);
            clockLbl = new Label(); clockLbl.AddToClassList("note"); clockLbl.style.marginLeft = 10; cr.Add(clockLbl);
            var chips = new VisualElement(); chips.AddToClassList("chips"); chips.style.marginTop = 10; chips.style.marginBottom = 0; top.Add(chips); viewChips.Clear();
            string[] vk = { "s_v_feed", "s_v_inc", "s_v_src", "s_v_brief" };
            for (int i = 0; i < 4; i++) { int k = i; var b = new Button(() => { view = k; if (k != 1) Select(null); Refresh(); }) { text = Loc.T(vk[i]) }; b.AddToClassList("chip"); chips.Add(b); viewChips.Add(b); }
            var lb = Widgets.Block(panel, Loc.T("s_incs"), Loc.T("s_incs_sub")); leftList = new VisualElement(); lb.Add(leftList);
            var n = Widgets.Block(panel); var note = new Label(Loc.T("s_note")); note.AddToClassList("note"); n.Add(note);
            Right();
            body = new VisualElement(); panel.Add(body);

            tick?.Pause();
            tick = panel.schedule.Execute(Tick).Every(250);
        }

        void Tick()
        {
            if (panel == null || panel.panel == null) return;
            tickN++;
            if (running && Operating) { clock += 2; if (clock >= 24 * 60) clock = 0; UpdateTop(); BuildPins(); if (view == 0) { int c = VisibleEvents().Count(); if (c != lastEvCount) RebuildBody(); } }
            if (view == 2 && tickN % 8 == 0) { var r = new System.Random(tickN + clock); for (int i = 0; i < sampleLabels.Count && i < sources.Count; i++) sampleLabels[i].text = sources[i].Sample(r); }
        }

        public override void Refresh()
        {
            if (panel == null || summary == null || !TwinData.Ready || !CityStats.Ready) return;
            Ensure(); UpdateTop(); RebuildBody(); BuildPins(); ApplyMap();
            TwinUI.Instance?.FillLegend(Legend);
        }

        void UpdateTop()
        {
            for (int i = 0; i < viewChips.Count; i++) viewChips[i].EnableInClassList("active", i == view);
            eyebrow.text = (Loc.T("tab_situation") + " · " + Today.ToString("d MMMM yyyy", Loc.Ru) + " · " + Hm(clock)).ToUpperInvariant();
            clockLbl.text = Operating ? string.Format(Loc.T("s_clock"), Hm(clock)) : "";
            notice.Clear();
            if (!Operating)
            {
                summary.text = string.Format(Loc.T("s_sum_early"), Y);
                var b = Widgets.Btn(string.Format(Loc.T("s_goto"), 2036), () => TwinState.Year = 2036, "small", "primary"); b.style.alignSelf = Align.FlexStart; b.style.marginBottom = 8; notice.Add(b);
            }
            else
            {
                var need = NeedDecision.ToList(); var act = need.Where(i => State(i) == "active").ToList(); var fc = need.Where(i => State(i) == "forecast").ToList();
                string Low(string t) => t.Length > 1 && !char.IsUpper(t[1]) ? char.ToLowerInvariant(t[0]) + t.Substring(1) : t;
                summary.text = need.Count == 0 ? Loc.T("s_sum_calm")
                    : act.Count > 0 ? string.Format(Loc.T("s_sum_act"), string.Join("; ", act.Select(i => Low(i.Title)))) + (fc.Count > 0 ? " " + string.Format(Loc.T("s_sum_fc"), string.Join("; ", fc.Select(i => Low(i.Title)))) : "")
                    : string.Format(Loc.T("s_sum_fc0"), string.Join("; ", fc.Select(i => Low(i.Title))));
            }
            int evs = VisibleEvents(false).Count(), zh = VisibleEvents(false).Count(e => e.Src == "zhkh"), on = sources.Count(x => x.Status == "ok");
            int actN = Operating ? NeedDecision.Count(i => State(i) == "active") : 0;
            Set(0, actN.ToString(), Loc.T("s_k_active"), actN > 0 ? "bad" : "ok");
            Set(1, Loc.N0(evs), string.Format(Loc.T("s_k_events"), Hm(clock)), "");
            Set(2, Loc.N0(zh), Loc.T("s_k_zhkh"), "");
            Set(3, on + " / " + sources.Count, Loc.T("s_k_src"), on == sources.Count ? "ok" : "warn");
            bool compact = selInc != null;
            topGrid.style.display = Operating && !compact ? DisplayStyle.Flex : DisplayStyle.None;
            summary.style.display = compact ? DisplayStyle.None : DisplayStyle.Flex;
        }

        IEnumerable<SituationData.Ev> VisibleEvents(bool filtered = true)
        {
            if (!Operating) return Enumerable.Empty<SituationData.Ev>();
            var all = day.Concat(extra).Where(e => e.Min <= clock && (e.Inc == null || incs.First(i => i.Id == e.Inc).Avail));
            if (filtered) all = all.Where(e => !srcOff.Contains(e.Src) && (!onlyImportant || e.Level != "info"));
            return all;
        }

        VisualElement leftList;
        void LeftList()
        {
            if (leftList == null) return; leftList.Clear();
            foreach (var i in incs)
            {
                if (!i.Avail && i.Id == "concrete") continue;
                var r = new VisualElement(); r.AddToClassList("status-row"); if (i.Id == selInc) r.AddToClassList("hl");
                var cls = StatusCls(i);
                r.Add(Widgets.Dot(cls == "bad" ? BAD : cls == "warn" ? WARN : cls == "ok" ? OK : MUTED, true));
                var n = new Label(i.Title) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); r.Add(n);
                var ii = i; r.AddManipulator(new Clickable(() => { view = 1; Select(ii.Id); }));
                leftList.Add(r);
            }
        }
        void RebuildBody()
        {
            LeftList();
            body.Clear(); sampleLabels.Clear();
            if (!Operating && view != 1) { view = 1; for (int i = 0; i < viewChips.Count; i++) viewChips[i].EnableInClassList("active", i == view); }
            switch (view)
            {
                case 0: Feed(); break;
                case 1: if (selInc != null) Detail(incs.First(i => i.Id == selInc)); else IncList(); break;
                case 2: Sources(); break;
                case 3: Brief(); break;
            }
        }

        // ------------------------------------------------------------------ feed
        static readonly (string k, Color c)[] SrcCol = { ("iot", new Color(0.30f, 0.64f, 1f)), ("112", new Color(1f, 0.36f, 0.30f)), ("zhkh", new Color(1f, 0.70f, 0.10f)),
            ("transport", new Color(0.85f, 0.27f, 0.94f)), ("eco", new Color(0.30f, 0.80f, 0.55f)), ("weather", new Color(0.60f, 0.70f, 0.80f)) };
        static Color ColOf(string src) { foreach (var (k, c) in SrcCol) if (k == src) return c; return MUTED; }

        void Feed()
        {
            var b = Widgets.Block(body, Loc.T("s_feed"), Loc.T("s_feed_sub"));
            var ch = new VisualElement(); ch.AddToClassList("chips"); b.Add(ch);
            foreach (var (k, c) in SrcCol)
            {
                var kk = k; var bt = new Button(() => { if (!srcOff.Remove(kk)) srcOff.Add(kk); RebuildBody(); }) { text = Loc.T("s_src_" + k) };
                bt.AddToClassList("chip"); bt.EnableInClassList("active", !srcOff.Contains(k)); ch.Add(bt);
            }
            var imp = new Button(() => { onlyImportant = !onlyImportant; RebuildBody(); }) { text = Loc.T("s_important") }; imp.AddToClassList("chip"); imp.EnableInClassList("active", onlyImportant); ch.Add(imp);
            var evs = VisibleEvents().OrderByDescending(e => e.Min).ToList(); lastEvCount = evs.Count;
            if (evs.Count == 0) { var l = new Label(Loc.T("s_feed_empty")); l.AddToClassList("note"); b.Add(l); return; }
            foreach (var e in evs.Take(40))
            {
                var r = new VisualElement(); r.AddToClassList("feed-row"); r.AddToClassList("clickable");
                var t = new Label(Hm(e.Min)) { pickingMode = PickingMode.Ignore }; t.AddToClassList("feed-time"); r.Add(t);
                var d = Widgets.Dot(e.Level == "bad" ? BAD : e.Level == "warn" ? WARN : ColOf(e.Src), true); d.style.marginTop = 4; r.Add(d);
                var tx = new Label(e.Text) { pickingMode = PickingMode.Ignore }; tx.AddToClassList("feed-text"); if (e.Level == "bad") tx.AddToClassList("bad"); r.Add(tx);
                var ev = e; r.AddManipulator(new Clickable(() => OpenEvent(ev)));
                b.Add(r);
            }
        }
        void OpenEvent(SituationData.Ev e)
        {
            if (e.Inc != null) { view = 1; Select(e.Inc); return; }
            evPin = e; Fly(e.P, 1800f); BuildPins();
        }
        static SituationData.Ev evPin;

        // ------------------------------------------------------------------ incidents
        void IncList()
        {
            var b = Widgets.Block(body, Loc.T("s_incs"), Loc.T("s_incs_sub"));
            foreach (var i in incs)
            {
                var r = new VisualElement(); r.AddToClassList("stage-row"); r.AddToClassList("clickable");
                var t = new VisualElement(); t.AddToClassList("top");
                t.Add(Widgets.Dot(StatusCls(i) == "bad" ? BAD : StatusCls(i) == "warn" ? WARN : StatusCls(i) == "ok" ? OK : MUTED, true));
                var n = new Label(i.Title) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); t.Add(n); r.Add(t);
                var sub = new Label(i.Where + " · " + StatusText(i)) { pickingMode = PickingMode.Ignore }; sub.AddToClassList("note"); sub.style.marginTop = 3; sub.style.marginLeft = 14; r.Add(sub);
                var ii = i; r.AddManipulator(new Clickable(() => Select(ii.Id)));
                b.Add(r);
            }
        }

        /// <summary>Presentation tour hooks.</summary>
        public void TourView(int v) { view = v; Select(null); Refresh(); }
        public void TourOpen(string id, bool taken) { view = 1; Select(id); mapTaken = taken; ApplyMap(); TwinUI.Instance?.FillLegend(Legend); RebuildBody(); }
        public static Inc Find(string id) => incs.FirstOrDefault(i => i.Id == id);
        /// <summary>Presentation: switch the map between "decision not taken" and "taken" without moving the camera.</summary>
        public void TourDecide(bool taken) { mapTaken = taken; ApplyMap(); TwinUI.Instance?.FillLegend(Legend); RebuildBody(); }
        public static string MoneyText(float mln) => Money(mln);

        void Select(string id)
        {
            selInc = id; evPin = null; tIdx = SituationData.NT - 1; mapTaken = false;
            var i = incs.FirstOrDefault(x => x.Id == id);
            if (i != null)
            {
                if (!i.Avail) { TwinState.Year = i.SuggestYear; Ensure(); i = incs.FirstOrDefault(x => x.Id == id); }
                if (i != null) Fly(i.P, i.FloodTint ? 5200f : i.Id == "lrt" ? 6000f : i.Id == "ps" || i.Id == "ses" ? 4200f : 2600f);
            }
            if (panel != null) Refresh();
        }
        static void Fly(Vector2 p, float dist)
        {
            var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
            if (cam != null) cam.FlyTo(new MapCamera.View { name = "incident", target = new Vector3(p.x, CityGround.HeightAt(p.x, p.y), p.y), distance = dist, yaw = cam.yaw, pitch = 46f });
        }

        void Detail(Inc i)
        {
            var b = Widgets.Block(body);
            var back = Widgets.Btn(Loc.T("s_back"), () => Select(null), "small", "ghost"); back.style.alignSelf = Align.FlexStart; back.style.marginLeft = -8; back.style.marginBottom = 4; b.Add(back);
            var t = new Label(i.Title); t.AddToClassList("block-title"); t.style.fontSize = 15; b.Add(t);
            var wl = new Label(i.Where); wl.AddToClassList("note"); wl.style.marginTop = 3; b.Add(wl);
            var st = Widgets.Status(StatusText(i), StatusCls(i)); st.style.alignSelf = Align.FlexStart; st.style.marginTop = 6; b.Add(st);
            // ---- decision comparison
            var c = Widgets.Block(body, Loc.T("s_cmp"), "");
            var q = new Label(i.Question); q.AddToClassList("summary"); q.style.fontSize = 15; q.style.marginBottom = 10; c.Add(q);
            var cols = new VisualElement(); cols.AddToClassList("cmp-cols"); c.Add(cols);
            cols.Add(Col(Loc.T("s_yes"), i.Yes, OK)); cols.Add(Col(Loc.T("s_no"), i.No, BAD));

            var mc = new VisualElement(); mc.AddToClassList("chips"); mc.style.marginTop = 10; c.Add(mc);
            var ml = new Label(Loc.T("s_on_map")); ml.AddToClassList("note"); ml.style.marginRight = 8; ml.style.marginTop = 5; mc.Add(ml);
            foreach (var (lbl, v) in new[] { (Loc.T("s_yes_s"), true), (Loc.T("s_no_s"), false) })
            {
                var vv = v; var bt = new Button(() => { mapTaken = vv; ApplyMap(); TwinUI.Instance?.FillLegend(Legend); RebuildBody(); }) { text = lbl }; bt.AddToClassList("chip"); bt.EnableInClassList("active", mapTaken == v); mc.Add(bt);
            }
            float frac = tIdx / (float)(SituationData.NT - 1), tt = frac * i.H;
            var sl = new TwinSlider(new int[0], null, 0, SituationData.NT - 1) { Value = tIdx }; sl.style.marginLeft = 0; sl.style.marginRight = 0;
            var tl = new Label(string.Format(Loc.T("s_t"), T(tt, i.Unit))); tl.AddToClassList("note"); tl.style.marginTop = 10;
            c.Add(tl); c.Add(sl);
            sl.OnChange = v => { tIdx = v; RebuildBody(); };

            var tab = new VisualElement(); tab.style.marginTop = 4; c.Add(tab);
            var head = new VisualElement(); head.AddToClassList("cmp-row"); head.AddToClassList("head"); tab.Add(head);
            head.Add(Cell("", "k")); head.Add(Cell(Loc.T("s_yes_s"), "y")); head.Add(Cell(Loc.T("s_no_s"), "n"));
            int k = tIdx;
            Row(tab, Loc.T("s_m_people"), Loc.N0(i.Yes.Affected[k]), Loc.N0(i.No.Affected[k]), i.Yes.Affected[k] <= i.No.Affected[k]);
            Row(tab, Loc.T("s_m_damage"), Money(i.Yes.Damage[k]), Money(i.No.Damage[k]), i.Yes.Damage[k] <= i.No.Damage[k]);
            Row(tab, string.Format(Loc.T("s_m_restore"), i.Unit), Restore(i.Yes, i.Unit), Restore(i.No, i.Unit), i.Yes.Restore <= i.No.Restore);
            if (i.Yes.NbLoad > 0 || i.No.NbLoad > 0) Row(tab, Loc.T("s_m_nb"), Mathf.RoundToInt(i.Yes.NbLoad) + " %", Mathf.RoundToInt(i.No.NbLoad) + " %", i.Yes.NbLoad <= i.No.NbLoad, i.No.NbLoad > 100);
            Row(tab, Loc.T("s_m_co2"), Loc.N1(i.Yes.Co2[k]), Loc.N1(i.No.Co2[k]), i.Yes.Co2[k] <= i.No.Co2[k]);

            float dm = i.No.Peak - i.Yes.Peak, dp = i.No.AffectedMax - i.Yes.AffectedMax, dr = i.No.Restore - i.Yes.Restore;
            var res = new Label(dr > 0 ? string.Format(Loc.T("s_effect"), Money(dm), Loc.N0(Mathf.Max(0, dp)), T(dr, i.Unit)) : string.Format(Loc.T("s_effect2"), Money(dm), Loc.N0(Mathf.Max(0, dp))));
            res.AddToClassList("summary"); res.style.fontSize = 14; res.style.marginTop = 8; res.style.color = new Color(0.86f, 0.95f, 0.88f); c.Add(res);
            if (i.Yes.Co2[SituationData.NT - 1] > i.No.Co2[SituationData.NT - 1]) { var w = new Label(Loc.T("s_tradeoff")); w.AddToClassList("note"); w.style.marginTop = 4; c.Add(w); }
            c.Add(SourceTags.Line(TwinModels.Ops, Data.Sources.ModelCity));

            if (!decided.ContainsKey(i.Id) && i.Avail)
            {
                var go = Widgets.Btn(Loc.T("s_decide"), () => Decide(i), "primary"); go.style.marginTop = 6; c.Add(go);
            }
            var cc = Widgets.Block(body, Loc.T("s_dmg_time"), "");
            var chart = new TwinChart(); chart.style.marginTop = 10; cc.Add(chart);
            chart.Series = new[] { i.Yes.Damage, i.No.Damage }; chart.Colors = new[] { OK, BAD }; chart.LineWidths = new[] { 2.5f, 2.5f }; chart.Stacked = false; chart.Bars = false; chart.StepLast = false; chart.Alerts = null;
            chart.XText = new[] { "0", T(i.H / 3f, ""), T(i.H * 2f / 3f, ""), T(i.H, i.Unit) }; chart.MarkFrac = frac; chart.Refresh();
            var lg = new VisualElement(); lg.AddToClassList("legend"); cc.Add(lg);
            lg.Add(Widgets.LegendItem(OK, Loc.T("s_lg_dmg_yes"))); lg.Add(Widgets.LegendItem(BAD, Loc.T("s_lg_dmg_no")));

            var fb = Widgets.Block(body, Loc.T("s_card"), "");
            fb.Add(Widgets.Fact(Loc.T("s_where"), i.Where));
            fb.Add(Widgets.Fact(Loc.T("s_when"), i.Today ? Today.ToString("d MMMM", Loc.Ru) + ", " + Hm(i.StartMin) : Loc.T("s_when_" + i.Kind)));
            fb.Add(Widgets.Fact(Loc.T("s_who"), i.Who));
            var last = Widgets.Fact("SLA", i.Sla); last.style.borderBottomWidth = 0; fb.Add(last);
            var hb = new Label(Loc.T("s_history").ToUpperInvariant()); hb.AddToClassList("note"); hb.style.marginTop = 8; hb.style.marginBottom = 4; hb.style.letterSpacing = 1; fb.Add(hb);
            foreach (var h in i.History) { var l = new Label("· " + h); l.AddToClassList("note"); l.style.color = new Color(0.76f, 0.76f, 0.76f); l.style.marginBottom = 2; fb.Add(l); }

        }
        VisualElement Col(string cap, SituationData.Branch br, Color col)
        {
            var v = new VisualElement(); v.AddToClassList("cmp-col");
            var e = new Label(cap.ToUpperInvariant()); e.AddToClassList("cap"); e.style.color = col; v.Add(e);
            var t = new Label(br.Title); t.AddToClassList("t"); v.Add(t);
            var d = new Label(br.Text); d.AddToClassList("note"); d.style.marginTop = 4; v.Add(d);
            return v;
        }
        static Label Cell(string s, string cls) { var l = new Label(s) { pickingMode = PickingMode.Ignore }; l.AddToClassList(cls); return l; }
        static void Row(VisualElement tab, string k, string y, string n, bool yesBetter, bool noBad = false)
        {
            var r = new VisualElement(); r.AddToClassList("cmp-row"); tab.Add(r);
            r.Add(Cell(k, "k")); var a = Cell(y, "y"); var b = Cell(n, "n"); r.Add(a); r.Add(b);
            if (yesBetter) a.AddToClassList("good"); if (noBad || yesBetter) b.AddToClassList("worse");
        }
        static string Money(float mln) => mln >= 1000 ? Loc.N1(mln / 1000f) + " " + Loc.T("s_bln") : Loc.N0(mln) + " " + Loc.T("s_mln");
        static string T(float v, string unit) => (v >= 10 || Mathf.Approximately(v, Mathf.Round(v)) ? Loc.N0(v) : Loc.N1(v)) + (unit != "" ? " " + unit : "");
        static string Restore(SituationData.Branch b, string unit) => b.Restore <= 0 ? Loc.T("s_no_outage") : T(b.Restore, unit);

        void Decide(Inc i)
        {
            decided[i.Id] = clock;
            extra.Add(new SituationData.Ev { Min = clock, Src = i.Src, Level = "info", P = i.P, Inc = i.Id, Text = string.Format(Loc.T("s_ev_decided"), i.Yes.Title) });
            mapTaken = true; Refresh();
        }

        // ------------------------------------------------------------------ data streams
        void Sources()
        {
            int pts = sources.Sum(x => x.Points);
            var b = Widgets.Block(body, Loc.T("s_src"), string.Format(Loc.T("s_src_sub"), sources.Count, Loc.N0(pts)));
            var intro = new Label(Loc.T("s_src_intro")); intro.AddToClassList("note"); intro.style.marginBottom = 8; b.Add(intro);
            var r0 = new System.Random(clock);
            foreach (var s in sources)
            {
                var r = new VisualElement(); r.AddToClassList("src-row");
                var top = new VisualElement(); top.AddToClassList("row");
                top.Add(Widgets.Dot(s.Status == "ok" ? OK : WARN, true));
                var n = new Label(s.Name); n.AddToClassList("n"); top.Add(n);
                var c = new Label(Loc.N0(s.Points)); c.AddToClassList("c"); top.Add(c); r.Add(top);
                var meta = new Label(s.Proto + " · " + s.Freq + (s.Status == "ok" ? "" : " · " + Loc.T("s_delay"))); meta.AddToClassList("note"); meta.style.marginLeft = 14; r.Add(meta);
                var smp = new Label(s.Sample(r0)); smp.AddToClassList("smp"); r.Add(smp); sampleLabels.Add(smp);
                b.Add(r);
            }
            b.Add(SourceTags.Line(TwinModels.Ops));
        }

        // ------------------------------------------------------------------ morning briefing
        void Brief()
        {
            var b = Widgets.Block(body, string.Format(Loc.T("s_brief"), Today.ToString("d MMMM", Loc.Ru)), Loc.T("s_brief_sub"));
            // yesterday = the whole simulated day before 08:00 today, summarised
            var all = day.Where(e => e.Inc == null).ToList();
            int zh = all.Count(e => e.Src == "zhkh"), c112 = all.Count(e => e.Src == "112"), warn = all.Count(e => e.Level != "info");
            float pw = TwinData.Load(S, "power", -1, Y), wt = TwinData.Load(S, "water", -1, Y) / 1000f;
            var bal = TwinData.BalanceOf(S, "power_hv", -1); int yi = TwinData.YI(Y); float util = bal != null && bal.Cap[yi] > 0 ? bal.Demand[yi] / bal.Cap[yi] : 0;
            Sec(b, Loc.T("s_b_day"));
            Line(b, string.Format(Loc.T("s_b_l1"), Loc.N0(all.Count), Loc.N0(warn)));
            Line(b, string.Format(Loc.T("s_b_l2"), Loc.N0(zh), 92 + (Y % 6)));
            Line(b, string.Format(Loc.T("s_b_l3"), Loc.N0(c112)));
            Line(b, string.Format(Loc.T("s_b_l4"), Loc.N0(pw), Mathf.RoundToInt(util * 100), Loc.N0(wt)));
            Sec(b, Loc.T("s_b_need"));
            var need = incs.Where(i => i.Avail && i.Today && !decided.ContainsKey(i.Id)).ToList();
            if (need.Count == 0) Line(b, Loc.T("s_b_none"));
            foreach (var i in need)
            {
                var r = new VisualElement(); r.AddToClassList("stage-row"); r.AddToClassList("clickable");
                var t = new VisualElement(); t.AddToClassList("top"); t.Add(Widgets.Dot(i.Kind == "forecast" ? WARN : BAD, true));
                var n = new Label(i.Title) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); t.Add(n); r.Add(t);
                var q = new Label(i.Question + " " + string.Format(Loc.T("s_b_save"), Money(i.No.Peak - i.Yes.Peak))) { pickingMode = PickingMode.Ignore };
                q.AddToClassList("note"); q.style.marginTop = 3; q.style.marginLeft = 14; r.Add(q);
                var ii = i; r.AddManipulator(new Clickable(() => { view = 1; Select(ii.Id); }));
                b.Add(r);
            }
            Sec(b, Loc.T("s_b_plan"));
            foreach (var i in incs.Where(x => x.Avail && !x.Today)) Line(b, "· " + i.Title + " — " + StatusText(i).ToLowerInvariant());
            b.Add(SourceTags.Line(TwinModels.Ops, TwinModels.Loads));
        }
        static void Sec(VisualElement b, string t) { var l = new Label(t.ToUpperInvariant()); l.AddToClassList("note"); l.style.marginTop = 10; l.style.marginBottom = 4; l.style.letterSpacing = 1; b.Add(l); }
        static void Line(VisualElement b, string t) { var l = new Label(t); l.style.fontSize = 12; l.style.marginBottom = 4; l.style.color = new Color(0.9f, 0.9f, 0.9f); b.Add(l); }

        // ------------------------------------------------------------------ 3D: pins and tint
        void BuildPins()
        {
            var P = MapPins.Instance; if (P == null) return;
            var list = new List<MapPins.Pin>();
            if (Operating || selInc != null)
                foreach (var i in incs)
                {
                    if (!i.Avail) continue; var st = State(i); if (st == "later") continue;
                    var cls = StatusCls(i); var c = cls == "bad" ? BAD : cls == "warn" ? WARN : cls == "ok" ? OK : new Color(0.75f, 0.75f, 0.75f);
                    var ii = i;
                    list.Add(new MapPins.Pin { Id = i.Id, Label = i.Title, World = new Vector3(i.P.x, CityGround.HeightAt(i.P.x, i.P.y) + 40f, i.P.y), Fill = c, Status = cls == "muted" ? "planned" : cls,
                        ShowLabel = i.Id == selInc || st == "active", Size = 16f, OnClick = () => { view = 1; Select(ii.Id); } });
                }
            if (evPin != null)
                list.Add(new MapPins.Pin { Id = "ev", Label = evPin.Text, World = new Vector3(evPin.P.x, CityGround.HeightAt(evPin.P.x, evPin.P.y) + 30f, evPin.P.y), Fill = ColOf(evPin.Src), ShowLabel = true, Size = 11f });
            // rebuild the pin set only when it changes (pins are re-created on Set)
            string sig = string.Join("|", list.Select(p => p.Id + p.Status + p.ShowLabel));
            if (sig == pinSig && P.All.Count == list.Count) return; pinSig = sig;
            P.Set(list); P.Select(selInc ?? (evPin != null ? "ev" : null));
        }
        static string pinSig;

        void ApplyMap()
        {
            var L = LineLayers.Instance; L?.HideAll();
            var i = selInc != null ? incs.FirstOrDefault(x => x.Id == selInc) : null;
            if (i == null) { TintLayer.Disable(); LineLayers.JamOff(); return; }
            if (i.Id == "dtp" && L != null) { L.Show("traffic", true); LineLayers.Jam(i.P, 1700f, 1f, mapTaken ? 1f : 0f); }
            else LineLayers.JamOff();
            var br = mapTaken ? i.Yes : i.No; var set = new HashSet<int>(br.Bids);
            if (set.Count == 0) { TintLayer.Disable(); return; }
            var col = i.FloodTint ? new Color(0.30f, 0.55f, 1f, 0.9f) : mapTaken ? new Color(WARN.r, WARN.g, WARN.b, 0.85f) : new Color(BAD.r, BAD.g, BAD.b, 0.9f);
            if (i.FloodTint && mapTaken) col = new Color(0.55f, 0.75f, 1f, 0.6f);
            TintLayer.Enable(); TintLayer.Apply(b => set.Contains(b.Bid) ? col : new Color(0, 0, 0, 0));
        }

        void Set(int i, string v, string l, string cls)
        {
            kv[i].text = v; kl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) kb[i].RemoveFromClassList(c);
            if (cls != "") kb[i].AddToClassList(cls);
        }
    }
}
