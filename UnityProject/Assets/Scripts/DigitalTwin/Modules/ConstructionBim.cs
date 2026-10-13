using System;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M1 detail level: pilot quarter Gate District Q1 as a 4D BIM model (plan vs fact per element, stages, safety by video analytics).</summary>
    public partial class ConstructionModule
    {
        static bool bimMode, ghost = true;
        Label bEyebrow, bSummary, bDate, bNote; readonly Label[] bkv = new Label[4], bkl = new Label[4]; readonly VisualElement[] bkb = new VisualElement[4];
        TwinSlider bSlider; Button bPlay; VisualElement bStages, bSafety; IVisualElementScheduledItem playTask;

        static string D(DateTime d) => d.ToString("dd.MM.yyyy", Loc.Ru);

        /// <summary>Presentation tour: open / close the Gate Q1 BIM view.</summary>
        public void TourBim(bool on) { if (on && !bimMode) EnterBim(); else if (!on && bimMode) LeaveBim(true); }

        void EnterBim()
        {
            var q = BimQuarter.Ensure(); if (!BimQuarter.Loaded) return;
            bimMode = true; q.Show(true); q.SetGhost(ghost); q.SetDay(q.StatusDay);
            TwinState.Year = q.DateOf(q.Day).Year;
            var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
            if (cam != null) cam.FlyTo(new MapCamera.View { name = "Gate Q1", target = q.Center, distance = 820f, yaw = 205f, pitch = 34f });
            q.OnChanged -= OnBimChanged; q.OnChanged += OnBimChanged;
            Rebuild(); Refresh(); TwinUI.Instance?.FillLegend(Legend);
        }

        void LeaveBim(bool rebuild)
        {
            bimMode = false; playTask?.Pause();
            var q = BimQuarter.Instance; if (q != null) { q.OnChanged -= OnBimChanged; q.Show(false); }
            TwinUI.Instance?.RefreshCard();
            if (rebuild) { Rebuild(); Refresh(); TwinUI.Instance?.FillLegend(Legend); }
        }

        void OnBimChanged() { if (bimMode) { RefreshBim(); TwinUI.Instance?.RefreshCard(); } }

        void BuildBim()
        {
            var q = BimQuarter.Instance; if (q == null) { bimMode = false; Build(); return; }
            var top = Widgets.Block(panel);
            var back = new Button(() => LeaveBim(true)) { text = Loc.T("bim_back") }; back.AddToClassList("btn"); back.AddToClassList("small"); back.AddToClassList("ghost");
            back.style.alignSelf = Align.FlexStart; back.style.marginLeft = -8; back.style.marginBottom = 6; top.Add(back);
            bEyebrow = Widgets.Eyebrow(top, "");
            bSummary = new Label(); bSummary.AddToClassList("summary"); bSummary.style.marginBottom = 10; top.Add(bSummary);
            // date control: day slider with the drone-survey dates as ticks
            var dr = new VisualElement(); dr.AddToClassList("date-row"); top.Add(dr);
            bPlay = Widgets.Btn(Loc.T("play"), TogglePlay, "small"); dr.Add(bPlay);
            bSlider = new TwinSlider(q.EpochDays, d => q.DateOf(d).ToString("dd.MM", Loc.Ru), 0, q.EndDay + 14) { OnChange = d => { StopPlay(); q.SetDay(d); } };
            bSlider.Value = q.Day; bSlider.style.flexGrow = 1; dr.Add(bSlider);
            bDate = new Label(); bDate.AddToClassList("bim-date"); bDate.style.marginBottom = 8; top.Add(bDate);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid); VisualElement row = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { row = new VisualElement(); row.AddToClassList("kpi-row"); grid.Add(row); }
                var k = new VisualElement(); k.AddToClassList("kpi");
                bkl[i] = new Label(); bkl[i].AddToClassList("l"); k.Add(bkl[i]); bkv[i] = new Label("—"); bkv[i].AddToClassList("v"); k.Add(bkv[i]);
                bkb[i] = k; row.Add(k);
            }
            var chips = new VisualElement(); chips.AddToClassList("chips"); chips.style.marginTop = 10; top.Add(chips);
            Chip(chips, Loc.T("bim_ghost"), () => ghost, () => { ghost = !ghost; q.SetGhost(ghost); });

            Right();
            var sb = Widgets.Block(panel, Loc.T("bim_stages"), Loc.T("bim_stages_sub"));
            bStages = new VisualElement(); sb.Add(bStages);

            var cv = Widgets.Block(panel, Loc.T("bim_safety"), Loc.T("bim_safety_sub"));
            bSafety = new VisualElement(); cv.Add(bSafety);

            var nb = Widgets.Block(panel); bNote = new Label(q.Note + " " + Loc.T("bim_click")); bNote.AddToClassList("note"); nb.Add(bNote);
        }

        void RefreshBim()
        {
            var q = BimQuarter.Instance; if (q == null || bSummary == null) return;
            ConstructionLayer.Compute(TwinState.Year, (int)TwinState.Scenario);
            int day = q.Day; var date = q.DateOf(day); var st = q.Compute(day);
            bEyebrow.text = ("Gate Q1 · BIM · " + D(date) + " · " + q.elements.Length.ToString("N0", Loc.Ru) + " " + Loc.T("bim_elements")).ToUpperInvariant();
            bDate.text = D(date) + (day == q.StatusDay ? "  ·  " + Loc.T("bim_status") : "");
            if (bSlider.Value != Mathf.Clamp(day, bSlider.Min, bSlider.Max)) bSlider.Value = day;
            float gap = st.PlanPct - st.FactPct;
            // the stage that is furthest behind gives the one-line conclusion
            int worst = -1; float wg = 0;
            for (int i = 0; i < q.stages.Length; i++) { q.StageProgress(i, day, out float p, out float f); if (p - f > wg) { wg = p - f; worst = i; } }
            if (st.Built == 0 && st.InWork == 0) bSummary.text = string.Format(Loc.T("bim_sum0"), D(q.DateOf(0)));
            else if (gap < 1.5f || worst < 0) bSummary.text = string.Format(Loc.T("bim_sum_ok"), D(date), Mathf.RoundToInt(st.FactPct));
            else bSummary.text = string.Format(Loc.T("bim_sum"), D(date), Mathf.RoundToInt(st.FactPct), Mathf.RoundToInt(st.PlanPct), q.stages[worst].Name, Mathf.RoundToInt(wg));
            SetB(0, Mathf.RoundToInt(st.FactPct) + " %", string.Format(Loc.T("bim_k_ready"), Mathf.RoundToInt(st.PlanPct)), gap > 8 ? "bad" : gap > 2 ? "warn" : "ok");
            SetB(1, st.Built.ToString("N0", Loc.Ru), string.Format(Loc.T("bim_k_built"), st.Behind.ToString("N0", Loc.Ru)), "");
            SetB(2, Loc.N1(st.Concrete / 1000f), Loc.T("bim_k_concrete"), "");
            SetB(3, st.Workers.ToString("N0", Loc.Ru), Loc.T("bim_k_workers"), "");

            bStages.Clear();
            for (int i = 0; i < q.stages.Length; i++)
            {
                var s = q.stages[i]; if (day < s.Start - 20 || day > s.End + 60) continue;      // only what matters around the date
                q.StageProgress(i, day, out float p, out float f);
                var r = new VisualElement(); r.AddToClassList("stage-row");
                var t = new VisualElement(); t.AddToClassList("top");
                var n = new Label(s.Name); n.AddToClassList("n"); t.Add(n);
                var v = new Label(Mathf.RoundToInt(f) + " / " + Mathf.RoundToInt(p) + " %"); v.AddToClassList("v"); if (p - f > 5) v.style.color = new Color(1f, 0.23f, 0.18f); t.Add(v);
                r.Add(t);
                var bar = new VisualElement(); bar.AddToClassList("bar");
                var bp = new VisualElement(); bp.AddToClassList("p"); bp.style.width = Length.Percent(p); bar.Add(bp);
                var bf = new VisualElement(); bf.AddToClassList("f"); bf.style.width = Length.Percent(f); if (p - f > 5) bf.AddToClassList("behind"); bar.Add(bf);
                r.Add(bar); bStages.Add(r);
            }
            if (bStages.childCount == 0) { var l = new Label(Loc.T("bim_no_stage")); l.AddToClassList("note"); bStages.Add(l); }

            // video analytics on site (synthetic, stable for a given day): cameras, PPE compliance, violations of the shift
            bSafety.Clear();
            if (st.Workers > 0)
            {
                float h = Hash(day); int cams = 14, viol = Mathf.FloorToInt(h * 4f), helmet = Mathf.Min(viol, 1 + Mathf.FloorToInt(Hash(day + 7) * 2f));
                float ppe = 100f - (viol * 0.9f + h * 0.8f);
                bSafety.Add(Widgets.Fact(Loc.T("bim_cams"), cams + " · " + Loc.T("bim_online")));
                bSafety.Add(Widgets.Fact(Loc.T("bim_ppe"), Loc.N1(ppe) + " %"));
                var vf = Widgets.Fact(Loc.T("bim_viol"), ""); vf.RemoveAt(1);
                vf.Add(Widgets.Status(viol == 0 ? Loc.T("bim_viol0") : string.Format(Loc.T("bim_viol_n"), viol, helmet, viol - helmet), viol == 0 ? "ok" : viol > 2 ? "bad" : "warn"));
                vf.style.borderBottomWidth = 0; bSafety.Add(vf);
            }
            else { var l = new Label(Loc.T("bim_no_workers")); l.AddToClassList("note"); bSafety.Add(l); }
        }

        static float Hash(int d) { uint x = (uint)(d * 2654435761u) ^ 0x9E3779B9u; x ^= x >> 13; x *= 0x5bd1e995; x ^= x >> 15; return (x & 0xFFFF) / 65535f; }

        void SetB(int i, string v, string l, string cls)
        {
            bkv[i].text = v; bkl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) bkb[i].RemoveFromClassList(c);
            if (cls != "") bkb[i].AddToClassList(cls);
        }

        void TogglePlay()
        {
            var q = BimQuarter.Instance; if (q == null) return;
            if (playTask != null && playTask.isActive) { StopPlay(); return; }
            if (q.Day >= q.EndDay) q.SetDay(0);
            bPlay.text = Loc.T("pause");
            playTask = panel.schedule.Execute(() =>
            {
                if (!bimMode) { StopPlay(); return; }
                q.SetDay(q.Day + 3); if (q.Day >= q.EndDay + 14) StopPlay();
            }).Every(90);
        }
        void StopPlay() { playTask?.Pause(); if (bPlay != null) bPlay.text = Loc.T("play"); }
    }
}
