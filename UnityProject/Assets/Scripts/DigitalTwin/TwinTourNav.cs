using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Presentation, mode 2 — the navigator (F4 or the compass in the header). For people who have already seen the tour: any
    /// step of the scenario, a district or an object is one click away, in any order. A step plays as in the tour (camera, dashboard,
    /// caption) but does not move on by itself; «Назад» returns to where you were before the last jump (a step or the map). The bar
    /// sits at the top of the map; the list opens under it and closes after a pick. The step-by-step tour (F5) is unchanged.</summary>
    public partial class TwinTour
    {
        bool free, navOpen;
        /// <summary>A step was opened from the navigator: it holds on its last frame instead of moving on.</summary>
        public static bool Free => Running && Instance.free;
        readonly List<int> hist = new List<int>();              // where to go back to: a step index, or -1 for the map
        VisualElement navBar, navPop, navHost; Label navNow; Button navBack, navList;
        readonly List<(int i, VisualElement el)> navItems = new List<(int, VisualElement)>();

        public static void ToggleNav() { if (Instance != null) Instance.SetNav(!Instance.navOpen); }

        void SetNav(bool on)
        {
            if (on && (!TwinData.Ready || !CityStats.Ready)) { Debug.LogWarning("[Alatau] navigator: data not ready"); return; }
            if (on && video) return;                                        // the recorded video keeps its own order
            navOpen = on; hist.Clear();
            if (on)
            {
                if (!running) Build();
                else free = true;                                          // the tour running: it stops moving on, the presenter picks
                NavEnsure(); navBar.style.display = DisplayStyle.Flex; ShowList(!running);
            }
            else
            {
                if (navBar != null) navBar.style.display = DisplayStyle.None;
                if (navPop != null) navPop.style.display = DisplayStyle.None;
                if (running && free) Stop();
            }
            TwinUI.Instance?.Middle?.EnableInClassList("tnav-on", on);
            NavRefresh();
        }

        /// <summary>Open a step of the scenario from the navigator.</summary>
        void NavStep(int i, bool remember = true)
        {
            if (i < 0 || i >= steps.Count) return;
            if (running && i == idx) { ShowList(false); return; }
            if (remember) hist.Add(running ? idx : -1);
            if (!running) { running = true; video = false; }
            free = true; paused = false; Go(i); ShowList(false); NavRefresh();
        }
        /// <summary>Leave the scenario for the map: the whole city, a district or an object with its passport.</summary>
        void NavMap(Action then, bool remember = true)
        {
            if (remember && running) hist.Add(idx);
            if (running) Stop();
            try { then?.Invoke(); } catch (Exception e) { Debug.LogWarning("[Alatau] navigator: " + e.Message); }
            ShowList(false); NavRefresh();
        }
        void NavBack()
        {
            if (hist.Count == 0) return;
            int j = hist[hist.Count - 1]; hist.RemoveAt(hist.Count - 1);
            if (j < 0) NavMap(Overview, false); else NavStep(j, false);
        }
        void ShowList(bool on)
        {
            if (navPop == null) return;
            navPop.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
            if (navList != null) navList.text = on ? "Скрыть шаги" : "Шаги";
        }

        void NavEnsure()
        {
            var ui = TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            if (navBar != null && navHost == ui.Scene && navBar.parent == navHost) return;
            navHost = ui.Scene; navItems.Clear();
            // the bar: where we are, the list, back, the whole map, close
            navBar = new VisualElement(); navBar.AddToClassList("tnav"); navBar.style.display = DisplayStyle.None;
            var ic = TwinUI.Icon("compass", 16); ic.AddToClassList("tnav-ic"); navBar.Add(ic);
            navNow = new Label { pickingMode = PickingMode.Ignore }; navNow.AddToClassList("tnav-now"); navBar.Add(navNow);
            navList = Widgets.Btn("Шаги", () => ShowList(navPop.style.display == DisplayStyle.None), "small"); navBar.Add(navList);
            navBack = Widgets.Btn("← Назад", NavBack, "small", "ghost"); navBar.Add(navBack);
            navBar.Add(Widgets.Btn("Вся карта", () => NavMap(Overview), "small", "ghost"));
            navBar.Add(Widgets.Btn("✕", () => SetNav(false), "small", "ghost"));
            ui.BlockWhileHovered(navBar); navHost.Add(navBar);
            // the list: the map, the scenario part by part, the objects
            navPop = new VisualElement(); navPop.AddToClassList("tnav-pop"); navPop.style.display = DisplayStyle.None;
            var sv = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden, verticalScrollerVisibility = ScrollerVisibility.Auto };
            sv.AddToClassList("tnav-scroll"); navPop.Add(sv); var c = sv.contentContainer;
            Head(c, "Карта", null);
            var mr = new VisualElement(); mr.AddToClassList("tnav-chips"); c.Add(mr);
            mr.Add(Widgets.Btn("Весь город", () => NavMap(Overview), "small", "ghost"));
            for (int d = 0; d < 4; d++) { int dd = d; var b = Widgets.Btn(CityStats.DistrictIds[d], () => NavMap(() => FrameZone(dd)), "small", "ghost"); b.style.color = CityStats.DistrictColors[d]; mr.Add(b); }
            int seg = -1; var list = video && tourSteps != null ? tourSteps : steps;      // the video shows the whole tour, not its own scenes
            for (int i = 0; i < list.Count; i++)
            {
                var s = list[i];
                if (s.Seg != seg) { seg = s.Seg; Head(c, SegName[seg], seg >= 1 && seg <= 4 ? CityStats.DistrictColors[seg - 1] : seg == 5 ? LrtC : (Color?)null); }
                string title; try { title = s.Title != null ? s.Title() : ""; } catch { title = ""; }
                int ii = i; var it = new VisualElement(); it.AddToClassList("tnav-item");
                var n = new Label((i + 1).ToString()) { pickingMode = PickingMode.Ignore }; n.AddToClassList("tnav-n"); it.Add(n);
                var t = new Label(title) { pickingMode = PickingMode.Ignore }; t.AddToClassList("tnav-t"); it.Add(t);
                it.AddManipulator(new Clickable(() => NavStep(ii))); c.Add(it); navItems.Add((i, it));
            }
            // objects: any landmark with its passport, outside the scenario
            var ls = LandmarkSystem.Instance;
            if (ls != null && ls.Items.Count > 0)
            {
                Head(c, "Объекты", null);
                var items = new List<Landmark>(); foreach (var l in ls.Items) if (!l.IsLrt) items.Add(l);
                items.Sort((a, b) => a.District != b.District ? a.District.CompareTo(b.District) : string.Compare(a.Name, b.Name, StringComparison.Ordinal));
                foreach (var l in items)
                {
                    var ll = l; var it = new VisualElement(); it.AddToClassList("tnav-item");
                    var dot = new VisualElement { pickingMode = PickingMode.Ignore }; dot.AddToClassList("tnav-dot");
                    if (l.District >= 0 && l.District < 4) dot.style.backgroundColor = CityStats.DistrictColors[l.District]; it.Add(dot);
                    var t = new Label(string.IsNullOrEmpty(l.Short) ? l.Name : l.Short) { pickingMode = PickingMode.Ignore }; t.AddToClassList("tnav-t"); it.Add(t);
                    it.AddManipulator(new Clickable(() => NavMap(() => LandmarkSystem.Instance?.Select(ll)))); c.Add(it);
                }
            }
            ui.BlockWhileHovered(navPop); navHost.Add(navPop);
        }
        /// <summary>The video's navigator scene: the bar (and the list, while «list» is on) without the navigator's own state.</summary>
        void VideoNav(bool on, string now = null, bool list = true)
        {
            if (!on) { if (navBar != null && !navOpen) { navBar.style.display = DisplayStyle.None; if (navPop != null) navPop.style.display = DisplayStyle.None; TwinUI.Instance?.Middle?.RemoveFromClassList("tnav-on"); } return; }
            NavEnsure(); if (navBar == null) return;
            navBar.style.display = DisplayStyle.Flex; ShowList(list); TwinUI.Instance?.Middle?.AddToClassList("tnav-on");
            if (navNow != null && now != null) navNow.text = now;
            navBack?.SetEnabled(!list);
        }
        /// <summary>The bar and the list are built again next time (the video lists the whole tour, the navigator its steps).</summary>
        void NavReset() { navBar?.RemoveFromHierarchy(); navPop?.RemoveFromHierarchy(); navBar = null; navPop = null; navItems.Clear(); }
        static void Head(VisualElement c, string text, Color? col)
        {
            var h = new VisualElement { pickingMode = PickingMode.Ignore }; h.AddToClassList("tnav-head");
            var dot = new VisualElement { pickingMode = PickingMode.Ignore }; dot.AddToClassList("tnav-dot"); if (col.HasValue) dot.style.backgroundColor = col.Value; else dot.style.backgroundColor = Brand; h.Add(dot);
            h.Add(new Label(text.ToUpperInvariant()) { pickingMode = PickingMode.Ignore }); c.Add(h);
        }
        void NavRefresh()
        {
            if (navBar == null || video) return;
            if (navNow != null)
            {
                string now = "Карта";
                if (running && idx >= 0 && idx < steps.Count) { try { now = $"{idx + 1}. " + (steps[idx].Title != null ? steps[idx].Title() : ""); } catch { now = $"Шаг {idx + 1}"; } }
                navNow.text = now;
            }
            navBack?.SetEnabled(hist.Count > 0);
            foreach (var (i, el) in navItems) el.EnableInClassList("on", running && i == idx);
        }
        /// <summary>Every frame: F4, and the bar comes back if the interface was rebuilt.</summary>
        void NavTick()
        {
            if (Input.GetKeyDown(KeyCode.F4) && !MapCamera.Typing) { ToggleNav(); return; }
            if (!navOpen) return;
            var ui = TwinUI.Instance;
            if (ui != null && ui.Scene != null && (navBar == null || navBar.parent != ui.Scene))
            {
                navBar = null; NavEnsure(); if (navBar != null) navBar.style.display = DisplayStyle.Flex; ShowList(false); NavRefresh();
                ui.Middle?.AddToClassList("tnav-on");                       // the rebuilt interface (a new language, say) keeps the room for the bar
            }
            if (!running && Input.GetKeyDown(KeyCode.Escape) && navPop != null && navPop.style.display == DisplayStyle.Flex) ShowList(false);
        }
    }
}
