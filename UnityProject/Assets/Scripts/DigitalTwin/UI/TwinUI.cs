using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Modules;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The platform shell (UI Toolkit), laid out like the qTwin platform: top bar (place, date, site pill, scenario, year, quick actions),
    /// left icon rail with the modules, two floating columns of panels (left — state, right — journal / analytics), bottom dock with the
    /// timeline and view tools, legend chips above it; the 3D city stays free in the middle.
    /// Self-bootstraps at scene load, so the scene asset needs no UI objects.</summary>
    public class TwinUI : MonoBehaviour
    {
        public static TwinUI Instance;
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (FindFirstObjectByType<TwinUI>() == null) new GameObject("Twin UI").AddComponent<TwinUI>(); }

        UIDocument doc; VisualElement root, leftPanel, rightPanel, popup, districtPopup, langPopup, card, scene, scenarioBtn, sitePill, rail, bellBadge;
        Label yearLabel, scenarioName, siteName, clockLabel, dockYear; Button playBtn; VisualElement playIcon; TwinSlider slider;
        readonly Dictionary<string, VisualElement> railBtns = new Dictionary<string, VisualElement>();
        readonly HashSet<VisualElement> hovered = new HashSet<VisualElement>();
        readonly List<ITwinModule> modules = new List<ITwinModule>();
        ITwinModule active; VisualElement legend3d, pins;
        static bool railOpen;
        /// <summary>Overlay container for map pins (facilities, stations, incidents) — drawn under the cards and panels.</summary>
        public VisualElement Pins => pins;
        public ITwinModule Active => active;
        public VisualElement Scene => scene;
        public Label BellBadge => bellBadge as Label;
        public void BlockWhileHovered(VisualElement e) => Chrome(e);
        /// <summary>True while the pointer is over a panel, the dock or another UI element that blocks the map.</summary>
        public bool PointerOverChrome => hovered.Count > 0;

        static readonly Dictionary<string, string> ModuleIcon = new Dictionary<string, string>
        { ["overview"] = "layout_grid", ["objects"] = "map_pin", ["construction"] = "hard_hat", ["prediction"] = "chart_line", ["infra"] = "network", ["situation"] = "radar", ["smartcity"] = "video", ["economy"] = "activity", ["ai"] = "sparkles" };

        /// <summary>A white line icon from Resources/UI/Icons (Lucide), tinted by USS.</summary>
        public static VisualElement Icon(string name, float size = 18f)
        {
            var e = new VisualElement { pickingMode = PickingMode.Ignore }; e.AddToClassList("icon");
            var t = Resources.Load<Texture2D>("UI/Icons/i_" + name); if (t != null) e.style.backgroundImage = new StyleBackground(t);
            e.style.width = size; e.style.height = size; return e;
        }

        void Awake()
        {
            Instance = this;
            doc = gameObject.AddComponent<UIDocument>();
            var ps = Resources.Load<PanelSettings>("UI/TwinPanel");
            if (ps == null) { ps = ScriptableObject.CreateInstance<PanelSettings>(); ps.scaleMode = PanelScaleMode.ConstantPixelSize; ps.themeStyleSheet = Resources.Load<ThemeStyleSheet>("UI/TwinTheme"); }
            doc.panelSettings = ps; doc.sortingOrder = 10;
            modules.Add(new OverviewModule());
            modules.Add(new ObjectsModule());
            modules.Add(new ConstructionModule());
            modules.Add(new PredictionModule());
            modules.Add(new InfraModule());
            modules.Add(new SituationModule());
            modules.Add(new SmartCityModule());
            modules.Add(new EconomyModule());
            modules.Add(new AiModule());
        }
        void OnEnable()
        {
            TwinState.OnYearChanged += OnYear; TwinState.OnScenarioChanged += OnScenario; TwinState.OnModuleChanged += OnModule;
            TwinState.OnDistrictChanged += OnDistrict; TwinState.OnSelectionChanged += OnSelection; TwinState.OnLanguageChanged += _ => Build();
            Data.TwinData.OnReady += Build; TwinState.OnLayersReady += LayersReady;
        }
        void OnDisable()
        {
            TwinState.OnYearChanged -= OnYear; TwinState.OnScenarioChanged -= OnScenario; TwinState.OnModuleChanged -= OnModule;
            TwinState.OnDistrictChanged -= OnDistrict; TwinState.OnSelectionChanged -= OnSelection;
            Data.TwinData.OnReady -= Build; TwinState.OnLayersReady -= LayersReady;
        }
        void Start() { Build(); }

        // ------------------------------------------------------------------ build
        public void Build()
        {
            root = doc.rootVisualElement; root.Clear(); hovered.Clear();
            var uss = Resources.Load<StyleSheet>("UI/Twin"); if (uss != null && !root.styleSheets.Contains(uss)) root.styleSheets.Add(uss);
            root.pickingMode = PickingMode.Ignore; root.AddToClassList("twin-root");
            root.style.position = Position.Absolute; root.style.left = 0; root.style.top = 0; root.style.right = 0; root.style.bottom = 0;
            root.RegisterCallback<GeometryChangedEvent>(_ => root.EnableInClassList("compact", root.resolvedStyle.width < 1560));
            // keyboard belongs to the map and the presentation (Space, arrows), never to a button that happens to have focus
            root.RegisterCallback<NavigationSubmitEvent>(e => { if (root.focusController?.focusedElement is Button b) { e.StopImmediatePropagation(); b.Blur(); } }, TrickleDown.TrickleDown);
            root.RegisterCallback<NavigationMoveEvent>(e => { if (!(root.focusController?.focusedElement is TextField)) e.StopImmediatePropagation(); }, TrickleDown.TrickleDown);
            root.EnableInClassList("rail-open", railOpen);

            root.Add(BuildHeader());
            var middle = new VisualElement { pickingMode = PickingMode.Ignore }; middle.AddToClassList("middle"); root.Add(middle); middleEl = middle;
            scene = new VisualElement { pickingMode = PickingMode.Ignore }; scene.AddToClassList("scene"); middle.Add(scene);
            pins = new VisualElement { pickingMode = PickingMode.Ignore }; pins.AddToClassList("pins"); scene.Add(pins);

            // demo badge under the site pill; legend chips and a fading hint above the dock
            var badge = new VisualElement { pickingMode = PickingMode.Ignore }; badge.AddToClassList("demo-badge");
            var ver = Data.TwinData.Ready ? " · " + Loc.T("data_ver") + " " + (Data.TwinData.Version.Split(' ').Length > 1 ? Data.TwinData.Version.Split(' ')[1] : Data.TwinData.Version) : "";
            badge.Add(new Label(Loc.T("demo_badge") + ver) { pickingMode = PickingMode.Ignore }); scene.Add(badge);
            var over = new VisualElement { pickingMode = PickingMode.Ignore }; over.AddToClassList("over-dock"); scene.Add(over);
            var hint = new Label(Loc.T("hint")) { pickingMode = PickingMode.Ignore }; hint.AddToClassList("hint"); over.Add(hint);
            hint.schedule.Execute(() => hint.AddToClassList("hidden")).StartingIn(12000);
            legend3d = new VisualElement { pickingMode = PickingMode.Ignore }; legend3d.AddToClassList("legend-3d"); over.Add(legend3d);

            card = new VisualElement(); card.AddToClassList("card"); card.style.display = DisplayStyle.None; scene.Add(card); Chrome(card);

            middle.Add(BuildDock());
            leftPanel = Column(middle, "col-left"); rightPanel = Column(middle, "col-right");
            middle.Add(rail = BuildRail());

            popup = BuildPopup(); root.Add(popup); Chrome(popup);
            districtPopup = BuildDistrictPopup(); root.Add(districtPopup); Chrome(districtPopup);
            langPopup = BuildLangPopup(); root.Add(langPopup); Chrome(langPopup);

            active = null; OnModule(TwinState.Module); OnScenario(TwinState.Scenario); OnYear(TwinState.Year); OnSelection(TwinState.Selected); OnDistrict(TwinState.District);
        }

        VisualElement Column(VisualElement parent, string cls)
        {
            var c = new VisualElement(); c.AddToClassList("col"); c.AddToClassList(cls); parent.Add(c); Chrome(c);
            var sv = new ScrollView(ScrollViewMode.Vertical) { horizontalScrollerVisibility = ScrollerVisibility.Hidden, verticalScrollerVisibility = ScrollerVisibility.Auto };
            sv.style.flexGrow = 1; c.Add(sv); return sv.contentContainer;
        }

        VisualElement BuildHeader()
        {
            var h = new VisualElement(); h.AddToClassList("header"); Chrome(h);
            var logo = new VisualElement { pickingMode = PickingMode.Ignore }; logo.AddToClassList("logo");
            var tex = Resources.Load<Texture2D>("UI/qtwin_logo"); if (tex != null) logo.style.backgroundImage = new StyleBackground(tex); h.Add(logo);
            var sep = new VisualElement { pickingMode = PickingMode.Ignore }; sep.AddToClassList("hsep"); h.Add(sep);
            var place = new VisualElement { pickingMode = PickingMode.Ignore }; place.AddToClassList("place2");
            place.Add(Icon("cloud_sun", 24));
            var pc = new VisualElement { pickingMode = PickingMode.Ignore }; pc.AddToClassList("pcol");
            var p1 = new Label(Loc.T("place2")) { pickingMode = PickingMode.Ignore }; p1.AddToClassList("p1"); pc.Add(p1);
            clockLabel = new Label { pickingMode = PickingMode.Ignore }; clockLabel.AddToClassList("p2"); pc.Add(clockLabel); place.Add(pc); h.Add(place);
            var sep2 = new VisualElement { pickingMode = PickingMode.Ignore }; sep2.AddToClassList("hsep"); h.Add(sep2);
            UpdateClock(); h.schedule.Execute(UpdateClock).Every(20000);

            var spacer = new VisualElement { pickingMode = PickingMode.Ignore }; spacer.AddToClassList("grow"); h.Add(spacer);
            scenarioBtn = new VisualElement(); scenarioBtn.AddToClassList("scenario-btn");
            scenarioBtn.Add(Icon("layers", 15));
            scenarioName = new Label { pickingMode = PickingMode.Ignore }; scenarioName.AddToClassList("v"); scenarioBtn.Add(scenarioName);
            var ch = new Chevron(); ch.AddToClassList("chev"); scenarioBtn.Add(ch);
            scenarioBtn.AddManipulator(new Clickable(() => TogglePopup(popup, scenarioBtn))); h.Add(scenarioBtn);
            yearLabel = new Label(); yearLabel.AddToClassList("year-big"); h.Add(yearLabel);
            var sep3 = new VisualElement { pickingMode = PickingMode.Ignore }; sep3.AddToClassList("hsep"); h.Add(sep3);
            h.Add(HeadIcon("sparkles", Loc.T("tab_ai"), () => TwinState.SetModule("ai")));
            VisualElement bell = null; bell = HeadIcon("bell", "Уведомления · Smart City, iKomek 109", () => Notifier.Instance?.TogglePanel(bell));
            bellBadge = new Label("") { pickingMode = PickingMode.Ignore }; bellBadge.AddToClassList("hbadge"); bell.Add(bellBadge); h.Add(bell);
            Notifier.Instance?.BindBadge(bellBadge as Label);
            h.Add(HeadIcon("compass", "Навигатор по презентации · F4", TwinTour.ToggleNav));
            h.Add(HeadIcon("presentation", Loc.T("tour") + " · F5", TwinTour.Toggle));
            // language: one globe button with the current code; the menu lists the three languages (UiTranslator translates the screen)
            var lang = new VisualElement(); lang.AddToClassList("hicon"); lang.AddToClassList("lang-btn"); lang.Add(Icon("globe", 17));
            var lc = new Label(Loc.Language == "kz" ? "KZ" : Loc.Language == "en" ? "EN" : "RU") { pickingMode = PickingMode.Ignore }; lc.AddToClassList("lang-code"); lang.Add(lc);
            lang.tooltip = "Язык интерфейса"; lang.AddManipulator(new Clickable(() => TogglePopup(langPopup, lang))); h.Add(lang);
            var user = new VisualElement { pickingMode = PickingMode.Ignore }; user.AddToClassList("user");
            var av = new Label("QT") { pickingMode = PickingMode.Ignore }; av.AddToClassList("avatar"); user.Add(av);
            var uc = new VisualElement { pickingMode = PickingMode.Ignore }; uc.AddToClassList("pcol");
            var u1 = new Label(Loc.T("user_name")) { pickingMode = PickingMode.Ignore }; u1.AddToClassList("p1"); uc.Add(u1);
            var u2 = new Label(Loc.T("user_role")) { pickingMode = PickingMode.Ignore }; u2.AddToClassList("p2"); uc.Add(u2); user.Add(uc); h.Add(user);

            // centre: site pill (city / district selector)
            sitePill = new VisualElement(); sitePill.AddToClassList("site-pill");
            sitePill.Add(Icon("map_pin", 15));
            siteName = new Label { pickingMode = PickingMode.Ignore }; siteName.AddToClassList("v"); sitePill.Add(siteName);
            var ch2 = new Chevron(); ch2.AddToClassList("chev"); sitePill.Add(ch2);
            sitePill.AddManipulator(new Clickable(() => TogglePopup(districtPopup, sitePill))); h.Add(sitePill);
            return h;
        }
        VisualElement HeadIcon(string icon, string tip, Action click)
        {
            var b = new VisualElement(); b.AddToClassList("hicon"); b.Add(Icon(icon, 18)); b.tooltip = tip;
            b.AddManipulator(new Clickable(click)); return b;
        }
        void UpdateClock()
        {
            if (clockLabel == null) return;
            var n = DateTime.Now; string s = n.ToString("ddd, d MMM", Loc.Ru); s = char.ToUpper(s[0]) + s.Substring(1);
            clockLabel.text = s + " · " + n.ToString("HH:mm");
        }

        VisualElement BuildRail()
        {
            var r = new VisualElement(); r.AddToClassList("rail"); r.EnableInClassList("open", railOpen); Chrome(r);
            var tg = new VisualElement(); tg.AddToClassList("rail-btn"); tg.AddToClassList("toggle");
            tg.Add(Icon(railOpen ? "chevrons_left" : "chevrons_right", 18));
            tg.AddManipulator(new Clickable(() => { railOpen = !railOpen; Build(); })); r.Add(tg);
            var line = new VisualElement { pickingMode = PickingMode.Ignore }; line.AddToClassList("rail-line"); r.Add(line);
            railBtns.Clear();
            foreach (var m in modules)
            {
                var id = m.Id; var b = new VisualElement(); b.AddToClassList("rail-btn");
                b.Add(Icon(ModuleIcon.TryGetValue(id, out var ic) ? ic : "box", 19));
                var l = new Label(Loc.T(m.TabKey)) { pickingMode = PickingMode.Ignore }; l.AddToClassList("rail-label"); b.Add(l);
                var tip = new Label(Loc.T(m.TabKey)) { pickingMode = PickingMode.Ignore }; tip.AddToClassList("rail-tip"); b.Add(tip);
                b.AddManipulator(new Clickable(() => TwinState.SetModule(id)));
                r.Add(b); railBtns[id] = b;
            }
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.AddToClassList("grow"); r.Add(sp);
            var line2 = new VisualElement { pickingMode = PickingMode.Ignore }; line2.AddToClassList("rail-line"); r.Add(line2);
            var tb = new VisualElement(); tb.AddToClassList("rail-btn"); tb.Add(Icon("presentation", 19));
            var tl = new Label(Loc.T("tour")) { pickingMode = PickingMode.Ignore }; tl.AddToClassList("rail-label"); tb.Add(tl);
            var tt = new Label(Loc.T("tour") + " · F5") { pickingMode = PickingMode.Ignore }; tt.AddToClassList("rail-tip"); tb.Add(tt);
            tb.AddManipulator(new Clickable(TwinTour.Toggle)); r.Add(tb);
            var nb = new VisualElement(); nb.AddToClassList("rail-btn"); nb.Add(Icon("compass", 19));
            var nl = new Label("Навигатор") { pickingMode = PickingMode.Ignore }; nl.AddToClassList("rail-label"); nb.Add(nl);
            var nt = new Label("Навигатор по презентации · F4") { pickingMode = PickingMode.Ignore }; nt.AddToClassList("rail-tip"); nb.Add(nt);
            nb.AddManipulator(new Clickable(TwinTour.ToggleNav)); r.Add(nb);
            return r;
        }

        VisualElement BuildDock()
        {
            var b = new VisualElement(); b.AddToClassList("dock"); Chrome(b);
            playBtn = new Button(TogglePlay); playBtn.AddToClassList("dock-play"); playIcon = Icon("play", 16); playBtn.Add(playIcon); b.Add(playBtn);
            var lo = new Label(TwinState.MinYear.ToString()); lo.AddToClassList("bound"); lo.style.marginLeft = 12; b.Add(lo);
            slider = new TwinSlider(new[] { 2030, 2040 }) { Value = TwinState.Year, OnChange = y => { TwinState.Playing = false; TwinState.Year = y; } }; b.Add(slider);
            var hi = new Label(TwinState.MaxYear.ToString()); hi.AddToClassList("bound"); b.Add(hi);
            var sep = new VisualElement { pickingMode = PickingMode.Ignore }; sep.AddToClassList("dsep"); b.Add(sep);
            b.Add(DockTool("house", Loc.T("t_home"), () => { var c = Cam; if (c != null) c.FlyTo(c.overview); TwinState.SetDistrict(-1); }));
            b.Add(DockTool("compass", Loc.T("t_top"), () => { var c = Cam; if (c != null) c.FlyTo(new MapCamera.View { name = "top", target = c.target, distance = c.distance, yaw = 0, pitch = c.pitch > 80 ? 50 : 89 }); }));
            b.Add(DockTool("rotate_ccw", Loc.T("t_north"), () => { var c = Cam; if (c != null) c.FlyTo(new MapCamera.View { name = "n", target = c.target, distance = c.distance, yaw = 0, pitch = c.pitch }); }));
            return b;
        }
        static MapCamera Cam => Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
        VisualElement DockTool(string icon, string tip, Action a)
        {
            var t = new VisualElement(); t.AddToClassList("dock-tool"); t.Add(Icon(icon, 17)); t.tooltip = tip; t.AddManipulator(new Clickable(a)); return t;
        }

        VisualElement BuildPopup()
        {
            var p = new VisualElement(); p.AddToClassList("popup"); p.style.display = DisplayStyle.None;
            foreach (Scenario s in Enum.GetValues(typeof(Scenario)))
            {
                var sc = s; var item = new VisualElement(); item.AddToClassList("popup-item"); if (s == TwinState.Scenario) item.AddToClassList("active");
                var n = new Label(TwinScenario.Name(s)); n.AddToClassList("name"); item.Add(n);
                var d = new Label(TwinScenario.Describe(s)); d.AddToClassList("desc"); item.Add(d);
                item.AddManipulator(new Clickable(() => { TwinState.Scenario = sc; HidePopups(); }));
                p.Add(item);
            }
            return p;
        }
        /// <summary>The language menu: each language under its own name (marked no-tr, so the translator leaves the names as they are).</summary>
        VisualElement BuildLangPopup()
        {
            var p = new VisualElement(); p.AddToClassList("popup"); p.AddToClassList("lang-pop"); p.AddToClassList("no-tr"); p.style.display = DisplayStyle.None; p.style.width = 190;
            foreach (var (code, name, tag) in new[] { ("kz", "Қазақша", "KZ"), ("ru", "Русский", "RU"), ("en", "English", "EN") })
            {
                var c = code; var item = new VisualElement(); item.AddToClassList("popup-item"); item.AddToClassList("row"); item.EnableInClassList("active", Loc.Language == code);
                var n = new Label(name) { pickingMode = PickingMode.Ignore }; n.AddToClassList("name"); item.Add(n);
                var t = new Label(tag) { pickingMode = PickingMode.Ignore }; t.AddToClassList("lang-tag"); item.Add(t);
                item.AddManipulator(new Clickable(() => { HidePopups(); TwinState.SetLanguage(c); }));
                p.Add(item);
            }
            return p;
        }
        VisualElement BuildDistrictPopup()
        {
            var p = new VisualElement(); p.AddToClassList("popup"); p.style.display = DisplayStyle.None; p.style.width = 260;
            for (int d = -1; d < CityStats.Districts; d++)
            {
                int di = d; var item = new VisualElement(); item.AddToClassList("popup-item"); item.AddToClassList("row");
                if (d >= 0) item.Add(Widgets.Dot(CityStats.DistrictColors[d], true));
                var n = new Label(d < 0 ? Loc.T("eyebrow_city") : CityStats.DistrictIds[d] + " District"); n.AddToClassList("name"); item.Add(n);
                item.AddManipulator(new Clickable(() => { GoToDistrict(di); HidePopups(); }));
                p.Add(item);
            }
            return p;
        }

        // ------------------------------------------------------------------ events
        void OnModule(string id)
        {
            foreach (var kv in railBtns) kv.Value.EnableInClassList("active", kv.Key == id);
            var m = modules.Find(x => x.Id == id); if (m == null) return;
            active?.OnExit(); active = m; m.OnEnter(); m.BuildPanel(leftPanel, rightPanel);
            FillLegend(m.Legend); RefreshCard();
        }
        void LayersReady() { if (active == null) return; active.OnEnter(); active.Refresh(); }

        public void FillLegend((Color, string)[] items)
        {
            if (legend3d == null) return; legend3d.Clear();
            items ??= new[] { (new Color(0.98f, 0.90f, 0.68f), Loc.T("lg_plan")), (new Color(0.90f, 0.91f, 0.93f), Loc.T("lg_gen")),
                              (new Color(0.75f, 0.74f, 0.72f), Loc.T("lg_exist")), (new Color(1f, 0.74f, 0.42f), Loc.T("lg_new")) };
            foreach (var (c, t) in items) legend3d.Add(Widgets.LegendItem(c, t));
        }

        void OnYear(int y)
        {
            yearLabel.text = y.ToString(); if (dockYear != null) dockYear.text = y.ToString(); if (slider != null && slider.Value != y) slider.Value = y;
            active?.Refresh(); RefreshCard();
        }
        void OnScenario(Scenario s)
        {
            scenarioName.text = TwinScenario.Name(s);
            int i = 0; foreach (var c in popup.Children()) { c.EnableInClassList("active", i == (int)s); i++; }
            active?.Refresh(); RefreshCard();
        }
        void OnDistrict(int d)
        {
            if (siteName != null) siteName.text = Loc.T("city") + " · " + (d < 0 ? Loc.T("eyebrow_city") : CityStats.DistrictIds[d]);
            active?.Refresh();
        }
        void OnSelection(BuildingInfo b) { RefreshCard(); }

        public void GoToDistrict(int d)
        {
            TwinState.SetDistrict(d);
            var cam = Cam; if (cam == null) return;
            if (d < 0) cam.FlyTo(cam.overview); else if (d < cam.views.Length) cam.FlyTo(cam.views[d]);
        }

        void TogglePlay()
        {
            var tl = FindFirstObjectByType<CityTimeline>(); if (tl != null) tl.TogglePlay(); else TwinState.Playing = !TwinState.Playing;
        }
        void TogglePopup(VisualElement p, VisualElement anchor)
        {
            bool show = p.style.display == DisplayStyle.None; HidePopups();
            if (!show) return;
            p.style.display = DisplayStyle.Flex;
            float w = root.resolvedStyle.width, pw = p.resolvedStyle.width > 10 ? p.resolvedStyle.width : 340;
            p.style.left = Mathf.Clamp(anchor.worldBound.center.x - pw / 2, 8, w - pw - 8);
        }
        /// <summary>The language menu, open under its button (the video shows it).</summary>
        public void OpenLangMenu()
        {
            if (langPopup == null || root == null) return;
            HidePopups(); langPopup.style.display = DisplayStyle.Flex; PlaceLangMenu();
            langPopup.schedule.Execute(PlaceLangMenu).ExecuteLater(1);     // a rebuilt header has its layout one frame later
        }
        void PlaceLangMenu()
        {
            var btn = root?.Q(className: "lang-btn"); if (btn == null || langPopup == null) return;
            float w = root.resolvedStyle.width, pw = 190f, cx = btn.worldBound.width > 1f ? btn.worldBound.center.x : w - 260f;
            langPopup.style.left = Mathf.Clamp(cx - pw / 2, 8, w - pw - 8);
        }
        public void HidePopups() { if (popup != null) popup.style.display = DisplayStyle.None; if (districtPopup != null) districtPopup.style.display = DisplayStyle.None; if (langPopup != null) langPopup.style.display = DisplayStyle.None; }

        // ------------------------------------------------------------------ passport card
        VisualElement middleEl;
        /// <summary>The middle area (scene + columns): carries "lm-open" while a landmark passport is open (it takes the right column's place)
        /// and "tour-on" during the presentation.</summary>
        public VisualElement Middle => middleEl;
        public void RefreshCard()
        {
            if (card == null) return;
            card.RemoveFromClassList("lm-card");
            var lsel = Landmarks.LandmarkSystem.Instance != null ? Landmarks.LandmarkSystem.Instance.Selected : null;
            middleEl?.EnableInClassList("lm-open", lsel != null);
            // a landmark (Iconic Complex, plants, LRT …) has its own passport
            var ls = Landmarks.LandmarkSystem.Instance;
            if (ls != null && ls.Selected != null) { Landmarks.LandmarkCard.Fill(card, ls.Selected); return; }
            var q = BimQuarter.Instance;
            if (q != null && BimQuarter.Visible && q.Selected >= 0) { BimCard(q); return; }
            var b = TwinState.Selected;
            if (b == null) { card.style.display = DisplayStyle.None; return; }
            card.style.display = DisplayStyle.Flex; card.Clear();
            var head = new VisualElement(); head.AddToClassList("head");
            var t = new Label(Loc.T("passport")); t.AddToClassList("t"); head.Add(t);
            head.Add(Widgets.Btn("×", () => { var s = Camera.main != null ? Camera.main.GetComponent<TwinSelector>() : null; if (s != null) s.Select(-1); else TwinState.SetSelected(null); }, "small", "ghost"));
            card.Add(head);
            var id = new Label(b.Id); id.AddToClassList("id"); card.Add(id);
            int eff = CityStats.Ready ? CityStats.EffectiveYearOf(b.Bid) : b.Year, y = TwinState.Year;
            string status, cls;
            if (b.Source == "existing_osm") { status = Loc.T("st_existing"); cls = "muted"; }
            else if (eff > TwinState.MaxYear) { status = Loc.T("st_after"); cls = "bad"; }
            else if (eff <= y) { status = Loc.T("st_built"); cls = "ok"; }
            else if (eff <= y + 2) { status = Loc.T("st_building"); cls = "warn"; }
            else { status = Loc.T("st_planned"); cls = "muted"; }
            int di = CityStats.DistrictIndex(b.District);
            var dRow = Widgets.Fact(Loc.T("p_district"), string.IsNullOrEmpty(b.District) ? "—" : b.District + " District"); if (di >= 0) dRow.Q<Label>(className: "v").style.color = CityStats.DistrictColors[di];
            card.Add(dRow);
            card.Add(Widgets.Fact(Loc.T("p_type"), Loc.Kind(b.Kind)));
            card.Add(Widgets.Fact(Loc.T("p_source"), b.Source == "existing_osm" ? Loc.T("src_osm") : b.Source == "master_plan" ? Loc.T("src_plan") : Loc.T("src_gen")));
            card.Add(Widgets.Fact(Loc.T("p_year"), b.Source == "existing_osm" ? "—" : eff > TwinState.MaxYear ? "> 2050" : eff.ToString() + (eff != b.Year ? "  (" + Loc.T("sc_base").Split(' ')[0].ToLower() + ": " + b.Year + ")" : "")));
            card.Add(Widgets.Fact(Loc.T("p_height"), Loc.N0(b.HeightM) + " m · " + Loc.T("p_floors").ToLower() + ": " + b.Floors));
            card.Add(Widgets.Fact(Loc.T("p_gfa"), b.GfaM2 > 0 ? Loc.N0(b.GfaM2) + " m²" : "—"));
            if (!string.IsNullOrEmpty(b.Parcel)) card.Add(Widgets.Fact(Loc.T("p_parcel"), b.Parcel));
            card.Add(Widgets.Fact("UTM 43N", "E " + b.Easting.ToString("F0") + "  N " + b.Northing.ToString("F0")));
            if (b.Source != "existing_osm" && eff <= TwinState.MaxYear && Data.TwinData.Ready)
            {
                ConstructionLayer.Timing(b, out int start, out int plan, out int fact);
                if (y >= start && y < fact)
                {
                    int stc = ConstructionLayer.Active ? ConstructionLayer.StateOf(b.Bid) : (Data.TwinData.DelayMonths[b.Bid] > 0 && y >= plan ? ConstructionLayer.Behind : ConstructionLayer.OnPlan);
                    status = stc == ConstructionLayer.Behind ? Loc.T("st_behind") : Loc.T("st_building"); cls = stc == ConstructionLayer.Behind ? "bad" : "warn";
                }
                int ci = ConstructionLayer.ContractorOf(b.Bid);
                if (ci < Data.TwinData.ContractorNames.Length) card.Add(Widgets.Fact(Loc.T("p_contractor"), Data.TwinData.ContractorNames[ci]));
                card.Add(Widgets.Fact(Loc.T("p_works"), start + " – " + plan + (fact > plan ? "  ·  " + Loc.T("p_forecast") + " " + fact : "")));
                if (ConstructionLayer.Active && y >= start && y < fact) card.Add(Widgets.Fact(Loc.T("p_progress"), Mathf.RoundToInt(ConstructionLayer.ProgressOf(b.Bid) * 100) + " %"));
            }
            var st = Widgets.Fact(Loc.T("p_status"), ""); st.RemoveAt(1); st.Add(Widgets.Status(status, cls)); st.style.borderBottomWidth = 0; card.Add(st);
        }

        void BimCard(BimQuarter q)
        {
            var e = q.elements[q.Selected]; card.style.display = DisplayStyle.Flex; card.Clear();
            var head = new VisualElement(); head.AddToClassList("head");
            var t = new Label(Loc.T("bim_card")); t.AddToClassList("t"); head.Add(t);
            head.Add(Widgets.Btn("×", () => q.Select(-1), "small", "ghost")); card.Add(head);
            var id = new Label("IFC GUID " + e.Guid); id.AddToClassList("id"); card.Add(id);
            card.Add(Widgets.Fact(Loc.T("bim_c_name"), e.Name));
            card.Add(Widgets.Fact(Loc.T("bim_c_class"), Loc.T("bim_cls_" + e.Cls)));
            card.Add(Widgets.Fact(Loc.T("bim_c_stage"), e.Stage >= 0 ? q.stages[e.Stage].Name : "—"));
            if (e.Volume > 0.05f) card.Add(Widgets.Fact(Loc.T("bim_c_volume"), Loc.N1(e.Volume) + " м³"));
            string D(int d) => d >= 9000 ? "—" : q.DateOf(d).ToString("dd.MM.yyyy", Loc.Ru);
            card.Add(Widgets.Fact(Loc.T("bim_c_plan"), D(e.Plan)));
            card.Add(Widgets.Fact(e.Fact <= q.StatusDay ? Loc.T("bim_c_fact") : Loc.T("bim_c_forecast"), D(e.Fact) + (e.Fact > e.Plan + 3 && e.Fact < 9000 ? "  (+" + (e.Fact - e.Plan) + " " + Loc.T("days") + ")" : "")));
            string status, cls; int day = q.Day;
            if (e.Fact <= day) { status = Loc.T("bim_s_done"); cls = "ok"; }
            else if (e.Plan + BimQuarter.Grace <= day) { status = Loc.T("bim_s_behind"); cls = "bad"; }
            else if (e.Plan - 12 <= day) { status = Loc.T("bim_s_work"); cls = "warn"; }
            else { status = Loc.T("bim_s_wait"); cls = "muted"; }
            var st = Widgets.Fact(Loc.T("p_status"), ""); st.RemoveAt(1); st.Add(Widgets.Status(status, cls)); st.style.borderBottomWidth = 0; card.Add(st);
        }

        // ------------------------------------------------------------------ input blocking
        void Chrome(VisualElement e)
        {
            e.RegisterCallback<PointerEnterEvent>(_ => { hovered.Add(e); MapCamera.BlockInput = true; });
            e.RegisterCallback<PointerLeaveEvent>(_ => { hovered.Remove(e); MapCamera.BlockInput = hovered.Count > 0; });
            // a press anywhere outside an open popup (and its anchor) closes it
            e.RegisterCallback<PointerDownEvent>(ev =>
            {
                var t = ev.target as VisualElement; if (t == null) return;
                bool open = (popup != null && popup.style.display == DisplayStyle.Flex) || (districtPopup != null && districtPopup.style.display == DisplayStyle.Flex);
                if (!open) return;
                if (popup.Contains(t) || districtPopup.Contains(t) || scenarioBtn.Contains(t) || sitePill.Contains(t) || t == popup || t == districtPopup || t == scenarioBtn || t == sitePill) return;
                HidePopups();
            }, TrickleDown.TrickleDown);
        }
        readonly List<VisualElement> stale = new List<VisualElement>();
        /// <summary>A panel that is rebuilt while the pointer is over it never sends "pointer leave": its old elements would keep
        /// the map blocked (no drag, no zoom, no picking). Every frame the hover set keeps only elements that are still on screen and
        /// still under the pointer.</summary>
        void PruneHover()
        {
            if (hovered.Count == 0 || root == null || root.panel == null) return;
            var mp = RuntimePanelUtils.ScreenToPanel(root.panel, new Vector2(Input.mousePosition.x, Screen.height - Input.mousePosition.y));
            stale.Clear();
            foreach (var e in hovered)
                if (e == null || e.panel == null || e.resolvedStyle.display == DisplayStyle.None || !e.worldBound.Contains(mp)) stale.Add(e);
            if (stale.Count == 0) return;
            foreach (var e in stale) hovered.Remove(e);
            MapCamera.BlockInput = hovered.Count > 0;
        }

        void Update()
        {
            PruneHover();
            bool open = (popup != null && popup.style.display == DisplayStyle.Flex) || (districtPopup != null && districtPopup.style.display == DisplayStyle.Flex);
            if (open && Input.GetMouseButtonDown(0) && !MapCamera.BlockInput) HidePopups();
            if (playIcon != null)
            {
                bool p = TwinState.Playing; if (playIcon.userData as string != (p ? "pause" : "play"))
                { playIcon.userData = p ? "pause" : "play"; var t = Resources.Load<Texture2D>("UI/Icons/i_" + (p ? "pause" : "play")); if (t != null) playIcon.style.backgroundImage = new StyleBackground(t); }
            }
        }
    }
}
