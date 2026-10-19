using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The pages of the construction monitoring, laid out like the qTwin construction platform (kus.qtwin.io): a rail of sections
    /// on the left of the window —
    /// · Объект: the passport, the planned completion, the state of the monitoring and the latest notifications over the live site;
    /// · Съёмки: the orthophoto history by survey dates, in 2D (straight down) or 3D, two dates compared with a swipe divider, layers
    ///   (city basemap, BIM outlines of the buildings, control points, changes between surveys), the ruler, the progress of a zone;
    /// · 4D: the BIM model on a dark stage (built parts solid, the rest a wire lattice of the design model), building tiles, readiness
    ///   by stages, KPI tiles, plan and actual, the stage columns over the timeline and the work schedule with the crew;
    /// · Видео: the wall of site cameras with video analytics; · Инвестору: the complex in money and hand-overs.</summary>
    public partial class IconicMonitor
    {
        // the sections; the index is what the recorded video asks for (VideoTab 0, 1, 2)
        const int TObj = 0, T4D = 1, TVid = 2, TInv = 3, TSurv = 4;
        static readonly (string icon, string name, int tab)[] Rail =
            { ("house", "Объект", TObj), ("history", "Съёмки", TSurv), ("box", "4D", T4D), ("video", "Видео", TVid), ("presentation", "Инвестору", TInv) };
        static readonly string[] District = { "Gate District", "Golden District", "Growing District", "Green District" };

        VisualElement overlay, body, pin, top, gantt, track, strip, viewSw, dimSw, tools;
        Image photo;
        Label headDate, hud, pinText, stripDate, stripMode, gTitle, gCrew;
        Button playBtn; VisualElement playIcon, glist;
        readonly List<Button> railBtns = new List<Button>(), viewBtns = new List<Button>(), modeBtns = new List<Button>(), dimBtns = new List<Button>();
        // the buildings of the complex: the bar of buttons, their labels over the view
        readonly List<Button> objBtns = new List<Button>(); readonly List<Label> objPct = new List<Label>(); readonly List<VisualElement> objDot = new List<VisualElement>();
        readonly List<VisualElement> opins = new List<VisualElement>(); readonly List<Label> opinText = new List<Label>();
        // gantt
        class GRow { public VisualElement Row, Bars; public Label Plan, Fact, Dev; public int W; }
        readonly List<GRow> grows = new List<GRow>(); readonly List<Label> axisLabels = new List<Label>();
        // investor
        VisualElement inv, invChart, invTable; Label invNote;
        readonly Label[] kCap = new Label[5], kVal = new Label[5], kSub = new Label[5];
        class IRow { public VisualElement Row, Bar, Mark; public Label Done, Due, Dev; public int I; }
        readonly List<IRow> irows = new List<IRow>();
        // the columns of every page, left and right of the picture
        VisualElement objL, objR, svL, svR, d4L, d4R;
        static void Vis(VisualElement e, bool on) { if (e != null) e.style.display = on ? DisplayStyle.Flex : DisplayStyle.None; }

        // ================================================================== the window
        void Build()
        {
            var ui = TwinUI.Instance; var mid = ui != null ? ui.Middle : null; if (mid == null || mid.panel == null) return;
            grows.Clear(); railBtns.Clear(); viewBtns.Clear(); modeBtns.Clear(); dimBtns.Clear(); axisLabels.Clear();
            monCards.Clear(); stRows.Clear(); stgCols.Clear(); tileRows.Clear(); prows.Clear(); vidSide.Clear(); lyBtns.Clear(); toolBtns.Clear();
            overlay = new VisualElement(); overlay.AddToClassList("mon-dim");
            overlay.RegisterCallback<PointerDownEvent>(e => { if (e.target == overlay) Close(); });
            ui.BlockWhileHovered(overlay);
            var win = new VisualElement(); win.AddToClassList("mon-win"); overlay.Add(win);
            BuildHead(win);
            var row = new VisualElement(); row.AddToClassList("mon-main"); win.Add(row);
            var rail = new VisualElement(); rail.AddToClassList("mon-rail"); row.Add(rail);
            foreach (var (icon, name, t) in Rail)
            {
                int k = t; var b = new Button(() => SetTab(k)) { focusable = false }; b.AddToClassList("mon-rail-b");
                b.Add(TwinUI.Icon(icon, 20)); b.Add(new Label(name) { pickingMode = PickingMode.Ignore }); rail.Add(b); railBtns.Add(b);
            }
            body = new VisualElement(); body.AddToClassList("mon-body"); row.Add(body);

            // ---- the live picture of the twin; a second survey date over its left part; the drawings of the plan over both
            photo = new Image { scaleMode = ScaleMode.StretchToFill }; photo.AddToClassList("mon-photo"); body.Add(photo);
            ViewInput(photo);
            BuildCompare();
            // the analytics boxes over the picture while a site camera is shown full size
            bigOver = new VisualElement { pickingMode = PickingMode.Ignore }; bigOver.AddToClassList("mon-photo"); body.Add(bigOver);
            bigOver.generateVisualContent += ctx => { var rr2 = bigOver.contentRect; if (view == View.Cam && rr2.width > 20f) DrawBoxes(ctx.painter2D, bigBox, 0f, 0f, rr2.width, rr2.height, new Rect(0f, 0f, rr2.width, rr2.height), 2f); };
            pin = new VisualElement { pickingMode = PickingMode.Ignore }; pin.AddToClassList("mon-pin"); pin.style.display = DisplayStyle.None;
            pinText = new Label { pickingMode = PickingMode.Ignore }; pin.Add(pinText);
            var stem = new VisualElement { pickingMode = PickingMode.Ignore }; stem.AddToClassList("mon-stem"); pin.Add(stem); body.Add(pin);
            // a label over every building of the complex (click: look at it)
            opins.Clear(); opinText.Clear();
            for (int i = 0; i < L.Parts.Count; i++)
            {
                int k = i; var pe = new VisualElement(); pe.AddToClassList("mon-pin"); pe.AddToClassList("mon-opin"); pe.style.display = DisplayStyle.None;
                var tl = new Label(); pe.Add(tl); var st2 = new VisualElement { pickingMode = PickingMode.Ignore }; st2.AddToClassList("mon-stem"); pe.Add(st2);
                pe.RegisterCallback<ClickEvent>(_ => SelectObj(k, true)); body.Add(pe); opins.Add(pe); opinText.Add(tl);
            }
            BuildMarks();

            // ---- top centre: the buildings, the views of the model, 3D / 2D, what is shown
            top = new VisualElement { pickingMode = PickingMode.Ignore }; top.AddToClassList("mon-top"); body.Add(top);
            BuildObjBar(top);
            var vrow = new VisualElement { pickingMode = PickingMode.Ignore }; vrow.AddToClassList("mon-row"); top.Add(vrow);
            viewSw = new VisualElement(); viewSw.AddToClassList("mon-seg"); vrow.Add(viewSw);
            foreach (var (txt, v) in new[] { ("Комплекс", View.Complex), ("Объект", View.Tower), ("Захватка", View.Floor) })
            { var vv = v; var b = Widgets.Btn(txt, () => SetView(vv), "small"); viewSw.Add(b); viewBtns.Add(b); }
            dimSw = new VisualElement(); dimSw.AddToClassList("mon-seg"); dimSw.style.marginLeft = 8; vrow.Add(dimSw);
            foreach (var (txt, plan) in new[] { ("3D", false), ("2D · план", true) })
            { var pl = plan; var b = Widgets.Btn(txt, () => SetDim(pl), "small"); dimSw.Add(b); dimBtns.Add(b); }
            hud = new Label { pickingMode = PickingMode.Ignore }; hud.AddToClassList("mon-hud"); top.Add(hud);

            // ---- the pages
            objL = Col("mon-left"); objR = Col("mon-right"); BuildObject();
            svL = Col("mon-left"); svR = Col("mon-right"); svR.AddToClassList("mon-right-in"); BuildSurvey();
            d4L = Col("mon-left"); d4R = Col("mon-right"); Build4D();
            gantt = new VisualElement(); gantt.AddToClassList("mon-g"); body.Add(gantt); BuildGantt(gantt);
            inv = new VisualElement(); inv.AddToClassList("mon-g"); inv.AddToClassList("mon-inv"); body.Add(inv); BuildInv(inv);
            BuildStrip();
            BuildSurveyBar();
            BuildVideo();                                       // the camera wall covers the whole page

            (mid.parent ?? mid).Add(overlay);                 // the root of the interface: it carries the style sheet, the window covers the header too
            RebuildLists(); SetTab(tab); Refresh();
        }
        VisualElement Col(string side)
        {
            var c = new VisualElement { pickingMode = PickingMode.Ignore }; c.AddToClassList("mon-col"); c.AddToClassList(side); body.Add(c); return c;
        }

        /// <summary>Header: where we are, the objects followed by the monitoring (switch), the date shown, close.</summary>
        void BuildHead(VisualElement win)
        {
            var head = new VisualElement(); head.AddToClassList("mon-head"); win.Add(head);
            monLogo = new VisualElement { pickingMode = PickingMode.Ignore }; monLogo.AddToClassList("mon-logo"); head.Add(monLogo); LogoColour();
            var crumbs = new VisualElement { pickingMode = PickingMode.Ignore }; crumbs.AddToClassList("mon-crumbs"); head.Add(crumbs);
            crumbs.Add(new Label("Alatau City") { pickingMode = PickingMode.Ignore });
            var sep = new Label("/") { pickingMode = PickingMode.Ignore }; sep.AddToClassList("sep"); crumbs.Add(sep);
            var cur = new Label("Мониторинг строительства") { pickingMode = PickingMode.Ignore }; cur.AddToClassList("cur"); crumbs.Add(cur);
            var seg = new VisualElement(); seg.AddToClassList("mon-seg"); seg.style.marginLeft = 18; head.Add(seg);
            var ls = LandmarkSystem.Instance;
            foreach (var id in new[] { "iconic", "kaist" })
            {
                var l = ls != null ? ls.Get(id) : null; if (l == null) continue;
                var k = id; var b = Widgets.Btn(l.Short, () => { if (k != L.Id) Switch(k); }, "small"); if (id == L.Id) b.AddToClassList("active"); seg.Add(b);
            }
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; head.Add(sp);
            headDate = new Label { pickingMode = PickingMode.Ignore }; headDate.AddToClassList("mon-hdate"); head.Add(headDate);
            var pill = new VisualElement { pickingMode = PickingMode.Ignore }; pill.AddToClassList("mon-pill"); pill.Add(TwinUI.Icon("hard_hat", 14));
            pill.Add(new Label("сценарий двойника") { pickingMode = PickingMode.Ignore }); head.Add(pill);
            head.Add(Widgets.Btn("×", Close, "small", "ghost"));
        }
        /// <summary>The monitoring of the other object, on the same page.</summary>
        void Switch(string id) { int t = tab; Close(); Show(id); if (open) SetTab(t); LogoColour(); }
        /// <summary>The ring before «Alatau City» takes the colour of the district the site is in (Iconic — Gate, blue; KAIST — Golden),
        /// so the monitoring of sites in different districts tells itself apart at a glance.</summary>
        VisualElement monLogo;
        void LogoColour()
        {
            if (monLogo == null || L == null) return;
            var c = CityStats.DistrictColors[Mathf.Clamp(L.District, 0, CityStats.DistrictColors.Length - 1)];
            monLogo.style.borderTopColor = monLogo.style.borderRightColor = monLogo.style.borderBottomColor = monLogo.style.borderLeftColor = c;
        }

        /// <summary>The 4D timeline at the bottom: play, the date, the track (drag), to the survey, actual or plan.</summary>
        void BuildStrip()
        {
            strip = new VisualElement(); strip.AddToClassList("mon-strip"); body.Add(strip);
            playBtn = new Button(TogglePlay); playBtn.AddToClassList("mon-play"); playIcon = TwinUI.Icon("play", 16); playBtn.Add(playIcon); strip.Add(playBtn);
            var dbox = new VisualElement { pickingMode = PickingMode.Ignore }; dbox.AddToClassList("mon-sdate"); strip.Add(dbox);
            stripDate = new Label { pickingMode = PickingMode.Ignore }; stripDate.AddToClassList("mon-sdate-v"); dbox.Add(stripDate);
            stripMode = new Label { pickingMode = PickingMode.Ignore }; stripMode.AddToClassList("note"); dbox.Add(stripMode);
            track = new VisualElement(); track.AddToClassList("mon-track"); track.generateVisualContent += DrawTrack; Scrub(track, x => Mathf.Lerp(T0, T1, x)); strip.Add(track);
            for (int y = (int)T0; y <= (int)T1; y++)
            { var a = new Label(y.ToString()) { pickingMode = PickingMode.Ignore }; a.AddToClassList("mon-tick"); a.style.left = Length.Percent((y - T0) / (T1 - T0) * 100f); track.Add(a); }
            strip.Add(Widgets.Btn("К съёмке", () => { playing = false; SetDate(Report); }, "small"));
            var seg = new VisualElement(); seg.AddToClassList("mon-seg"); strip.Add(seg);
            foreach (var (txt, pm) in new[] { ("Факт", false), ("План", true) })
            { var b = Widgets.Btn(txt, () => { planMode = pm; SetDate(date, true); }, "small"); seg.Add(b); modeBtns.Add(b); }
        }

        // ------------------------------------------------------------------ pages
        void SetTab(int t)
        {
            int was = tab; tab = t;
            for (int i = 0; i < railBtns.Count; i++) railBtns[i].EnableInClassList("on", Rail[i].tab == t);
            Vis(objL, t == TObj); Vis(objR, t == TObj); Vis(tools, t == TObj);
            Vis(svL, t == TSurv); Vis(svR, t == TSurv); Vis(svBar, t == TSurv); Vis(svTools, t == TSurv); Vis(svOver, t == TSurv);
            if (t != TSurv) { Vis(chrono, false); Vis(cmpClip, false); Vis(cmpDiv, false); Vis(chipL, false); Vis(chipR, false); }
            Vis(d4L, t == T4D); Vis(d4R, t == T4D); Vis(gantt, t == T4D && ganttOn); Vis(stg, t == T4D && !ganttOn);
            Vis(strip, t == T4D || t == TInv); Vis(inv, t == TInv);
            Vis(top, t != TVid); Vis(viewSw, t == TObj || t == TInv); Vis(dimSw, t == TSurv || t == T4D);
            Vis(vidPage, t == TVid && view != View.Cam); Vis(camBar, t == TVid && view == View.Cam);
            body?.EnableInClassList("mon-t4d", t == T4D && !ganttOn);
            body?.EnableInClassList("mon-tsurv", t == TSurv);         // the right column stands left of the tool rail: the top bar keeps clear of it
            body?.EnableInClassList("mon-tab-g", t == T4D && ganttOn);
            if (t != was || view == View.Cam && t != TVid || view == View.Plan && t != TSurv && t != T4D)
            {
                // every page has its own picture: the surveys and the 4D their 3D / 2D choice, the camera wall none, the rest the model
                if (t == TSurv) { planMode = false; playing = false; SetDate(surveys.Count > 0 ? surveys[svA] : Report, true); SetView(svPlan ? View.Plan : View.Complex); }
                else if (t == T4D) SetView(d4Plan ? View.Plan : obj >= 0 && obj != TI ? View.Tower : View.Complex);
                else if (t == TVid) { if (view != View.Cam) view = View.Complex; }
                else if (view == View.Plan || view == View.Cam) SetView(obj >= 0 && obj != TI ? View.Tower : View.Complex);
            }
            if (t == TVid) VidGroup(vidGroup);
            dirty = true;
        }
        void SetDim(bool plan)
        {
            if (tab == TSurv) svPlan = plan; else d4Plan = plan;
            SetView(plan ? View.Plan : obj >= 0 && obj != TI ? View.Tower : View.Complex);
        }

        // ------------------------------------------------------------------ the numbers on screen
        void Refresh()
        {
            if (overlay == null || works.Count == 0) return;
            bool fc = date > Report + 0.002f;
            headDate.text = (tab == TSurv ? "съёмка " : fc ? "прогноз на " : planMode ? "план на " : "факт на ") + Day(date);
            stripDate.text = Day(date);
            stripMode.text = planMode ? "показан план" : fc ? "прогноз после съёмки" : "факт по съёмке";
            playIcon.style.backgroundImage = new StyleBackground(Resources.Load<Texture2D>("UI/Icons/i_" + (playing ? "pause" : "play")));
            for (int i = 0; i < viewBtns.Count; i++) viewBtns[i].EnableInClassList("active", (int)view == i);
            if (viewBtns.Count > 2) viewBtns[2].style.display = obj < 0 || obj == TI ? DisplayStyle.Flex : DisplayStyle.None;   // floors: the tower only
            for (int i = 0; i < modeBtns.Count; i++) modeBtns[i].EnableInClassList("active", (i == 1) == planMode);
            for (int i = 0; i < dimBtns.Count; i++) dimBtns[i].EnableInClassList("active", (i == 1) == (view == View.Plan));
            string vs = view == View.Complex ? (obj >= 0 ? "КОМПЛЕКС · " + Pt(obj).Name.ToUpper() : "КОМПЛЕКС") : view == View.Tower ? (obj >= 0 && obj != TI ? Pt(obj).Name.ToUpper() : IconicShape.P.Tower.ToUpper())
                : view == View.Floor ? IconicFloors.Name(Mathf.Max(focusFloor, 0)).ToUpper() : view == View.Plan ? "ПЛАН УЧАСТКА" : CamId[camIx] + " · " + CamName[camIx].ToUpper();
            hud.text = UiTranslator.Tr(tab == TSurv ? (view == View.Plan ? "ОРТОФОТОПЛАН · " : "3D-МОДЕЛЬ ПО СЪЁМКЕ · ") + Day(date) + (svB >= 0 ? " · СРАВНЕНИЕ С " + Day(surveys[svB]) : "")
                : (tab == T4D ? "BIM 4D · " : "4D · ") + (planMode ? "ПЛАН" : fc ? "ПРОГНОЗ" : "ФАКТ") + " НА " + Day(date) + " · " + vs);   // set after the interface was translated
            var os = new OS[L.Parts.Count]; for (int i = 0; i < os.Length; i++) os[i] = Obj(i, date);
            RefreshObjects(os);
            RefreshMonCards();
            if (tab == TObj) RefreshObject(os);
            if (tab == TSurv) RefreshSurvey();
            if (tab == T4D) Refresh4D(os);
            if (camBarTitle != null) camBarTitle.text = CamId[camIx] + " · " + CamName[camIx];
            for (int i = 0; i < grows.Count; i++)
            {
                var g = grows[i]; var s = Stat(works[g.W], date);
                g.Plan.text = Pct(s.Plan); g.Fact.text = Pct(s.Fact); g.Dev.text = Dev(s);
                string c = s.Plan <= 0f && s.Fact <= 0f ? "" : Cls(s.Days);
                foreach (var cc in new[] { "ok", "warn", "bad" }) g.Dev.EnableInClassList(cc, cc == c);
                g.Row.EnableInClassList("sel", g.W == sel);
                g.Bars.MarkDirtyRepaint();
            }
            if (gCrew != null) gCrew.text = "численность на " + Day(date) + ": " + Loc.N0(Crew(date, !planMode)) + " чел · пик " + Loc.N0(CrewPeak()) + " чел";
            track.MarkDirtyRepaint();
            if (tab == TInv) RefreshInv();
        }
        /// <summary>The bar of the buildings, their labels over the view, the tiles of the 4D page, the plan / actual card.</summary>
        void RefreshObjects(OS[] os)
        {
            int n = os.Length, done = 0;
            for (int i = 0; i < n; i++) if (os[i].Fact >= 0.999f) done++;
            for (int b = 0; b < objBtns.Count; b++)
            {
                int i = b - 1; objBtns[b].EnableInClassList("active", i == obj);
                if (i < 0) { objPct[b].text = done + " из " + n; objDot[b].style.backgroundColor = Blue; }
                else { objPct[b].text = os[i].Chip; objDot[b].style.backgroundColor = ClsColor(os[i].Cls); }
            }
            for (int i = 0; i < opinText.Count && i < n; i++) opinText[i].text = Pt(i).Short + " · " + os[i].Chip;
            foreach (var t in tileRows)
            {
                t.B.EnableInClassList("on", t.I == obj);
                if (t.I < 0) { t.P.text = Pct(Ready(date, !planMode)); t.Dot.style.backgroundColor = Blue; }
                else { t.P.text = Pct(planMode ? os[t.I].Plan : os[t.I].Fact); t.Dot.style.backgroundColor = ClsColor(os[t.I].Cls); }
            }
            foreach (var r in prows)
            {
                var o = os[r.I]; float d = (o.Fact - o.Plan) * 100f;
                r.P.text = Pct(o.Plan); r.F.text = Pct(o.Fact); r.D.text = o.Plan <= 0f && o.Fact <= 0f ? "—" : Signed(d);
                string c = o.Plan <= 0f && o.Fact <= 0f ? "" : d < -1f ? "bad" : d < -0.2f ? "warn" : "ok";
                foreach (var cc in new[] { "ok", "warn", "bad" }) { r.Row.EnableInClassList(cc, cc == c); r.D.EnableInClassList(cc, cc == c); }
                r.Row.EnableInClassList("sel", r.I == obj);
            }
            if (pfNote != null) pfNote.text = "состояние на " + Day(date) + (date > Report + 0.002f ? " · прогноз после съёмки " + Day(Report) : " · по съёмке");
        }
        /// <summary>The lists that follow the building looked at: readiness by stages (4D), the stage columns over the timeline.</summary>
        void RebuildLists() { FillStages(); FillStg(); }

        static string Signed(float pp) => (pp >= 0f ? "+" : "−") + Loc.N1(Mathf.Abs(pp)) + " п.п.";
        static string EndDev(int days) => days > 3 ? $"позже на {days} дн." : days < -3 ? $"раньше на {-days} дн." : "в срок";
        /// <summary>Readiness of the complex weighted by the budgets of its buildings (plan or actual).</summary>
        float Ready(float d, bool fact) { float s = 0f, c = 0f; for (int i = 0; i < L.Parts.Count; i++) { s += L.Parts[i].Capex * (fact ? FactP(i, d) : PlanP(i, d)); c += L.Parts[i].Capex; } return c > 0f ? s / c : 0f; }
        string Customer() { var c = L.Company ?? ""; int k = c.IndexOf(" · ", StringComparison.Ordinal); return k > 0 ? c.Substring(0, k) : c; }
        string Members() { var c = L.Company ?? ""; int k = c.IndexOf(" · ", StringComparison.Ordinal); return k > 0 ? c.Substring(k + 3) : "—"; }
        string Site() => District[Mathf.Clamp(L.District, 0, District.Length - 1)] + " · Alatau City";
        /// <summary>The work going on now in building i (the tower if −1), with its progress; or what the building waits for.</summary>
        string StageNow(int i)
        {
            int b = i >= 0 ? i : TI; float best = -1f; string s = null;
            for (int k = 0; k < works.Count; k++)
            {
                var w = works[k]; if (w.Sum || w.Part != b) continue;
                var st = planMode ? new St { Fact = Stat(w, date).Plan } : Stat(w, date);
                if (st.Fact > 0f && st.Fact < 0.999f && w.B > best) { best = w.B; s = w.Name + " · " + Pct(st.Fact); }
            }
            if (s != null) return s;
            float p = ShownP(b, date); return p >= 0.999f ? "введён в эксплуатацию" : p <= 0f ? "подготовка, старт " + IconicFloors.MonthYear(Pt(b).A) : "идут работы";
        }
        /// <summary>The next hand-over of a building after the date (by the forecast), else the completion of the complex.</summary>
        string NextMilestone()
        {
            int next = -1; float ne = float.MaxValue;
            for (int i = 0; i < L.Parts.Count; i++) { float fe = FactDate(i, 1f); if (fe > date + 0.001f && fe < ne) { ne = fe; next = i; } }
            return next < 0 ? "комплекс введён" : "ввод: " + Pt(next).Name + " · " + IconicFloors.MonthYear(ne);
        }

        // ================================================================== Объект
        readonly Label[] pasV = new Label[7]; Label endBig, endSub; VisualElement noteList;
        class MonCard { public Label Last, Stage, Next, NextSv; }
        readonly List<MonCard> monCards = new List<MonCard>();
        readonly List<Button> toolBtns = new List<Button>();
        void BuildObject()
        {
            var c = Card(objL);
            Head(c, "building_2", L.Short);
            var sub = new Label("Паспорт объекта") { pickingMode = PickingMode.Ignore }; sub.AddToClassList("mon-src"); sub.style.marginTop = 2; c.Add(sub);
            string[] keys = { "Проект", "Заказчик", "Участники", "Площадка", "Локация", "Стадия", "Направление" };
            for (int i = 0; i < keys.Length; i++) c.Add(FactRow(keys[i], out pasV[i]));
            pasV[0].text = L.Name; pasV[1].text = Customer(); pasV[2].text = Members(); pasV[3].text = Site();
            pasV[4].text = "Alatau City, Алматинская область"; pasV[6].text = L.Purpose;

            var c2 = Card(objL); Head(c2, "calendar", "Плановый срок завершения");
            endBig = new Label { pickingMode = PickingMode.Ignore }; endBig.AddToClassList("mon-bignum"); c2.Add(endBig);
            endSub = Para(""); c2.Add(endSub);
            MonitorCard(objL);

            // right: the latest notifications of the site
            var r = Card(objR); Head(r, "bell", "Последние уведомления");
            noteList = new VisualElement(); r.Add(noteList); FillNotes();
            var all = Widgets.Btn("Посмотреть все", () => SetTab(TVid), "small"); all.style.marginTop = 10; r.Add(all);

            // the toolbar under the picture
            tools = new VisualElement(); tools.AddToClassList("mon-tools"); body.Add(tools);
            Tool("house", "Комплекс", () => SelectObj(-1, true));
            Tool("building_2", "Объект", () => { if (obj < 0) SelectObj(TI, false); SetView(View.Tower); });
            Tool("layers", "Захватка", () => { if (obj >= 0 && obj != TI) SelectObj(TI, false); SetView(View.Floor); });
            Tool("columns_2", "Сравнить", () => { SetTab(TSurv); if (svB < 0 && svA > 0) SetB(svA - 1); });
            Tool("cctv", "Камеры", () => SetTab(TVid));
            Tool("box", "BIM 4D", () => SetTab(T4D));
            Tool("refresh_cw", "Сброс", () => { yaw = main != null ? main.transform.eulerAngles.y + 25f : yaw; SelectObj(-1, true); });
        }
        void Tool(string icon, string text, Action a)
        {
            var b = new Button(a) { focusable = false }; b.AddToClassList("mon-tool"); b.Add(TwinUI.Icon(icon, 18));
            b.Add(new Label(text) { pickingMode = PickingMode.Ignore }); tools.Add(b); toolBtns.Add(b);
        }
        /// <summary>The latest events of the site, as on the platform: trucks at the gate, works seen by the cameras, the survey, a delay.</summary>
        void FillNotes()
        {
            noteList.Clear(); var now = DateTime.Now;
            void N(DateTime t, string icon, string text, string sub, Color c, Action go)
            {
                var r = new VisualElement(); r.AddToClassList("mon-note"); noteList.Add(r);
                var ic = new VisualElement { pickingMode = PickingMode.Ignore }; ic.AddToClassList("mon-note-ic"); ic.style.backgroundColor = new Color(c.r, c.g, c.b, 0.16f);
                var i2 = TwinUI.Icon(icon, 15); i2.style.unityBackgroundImageTintColor = c; ic.Add(i2); r.Add(ic);
                var tx = new VisualElement { pickingMode = PickingMode.Ignore }; tx.AddToClassList("mon-note-tx"); r.Add(tx);
                tx.Add(new Label(text) { pickingMode = PickingMode.Ignore });
                var s = new Label(t.ToString("HH:mm") + " · " + sub) { pickingMode = PickingMode.Ignore }; s.AddToClassList("mon-src"); tx.Add(s);
                r.Add(Widgets.Btn("Просмотреть", go, "small"));
            }
            N(now.AddMinutes(-4), "truck", "Въехал бетоновоз", "КПП-1 · CAM-05", Blue, () => OpenCam(5));
            N(now.AddMinutes(-17), "truck", "Выехал самосвал с грунтом", "КПП-1 · CAM-05", Green, () => OpenCam(5));
            N(now.AddMinutes(-38), "hard_hat", "Подъём опалубки ядра на этаж", "CAM-07 · кран над захваткой", Orange, () => OpenCam(0));
            N(now.AddMinutes(-56), "truck", "Въехал автокран 50 т", "КПП-1 · CAM-05", Blue, () => OpenCam(5));
            int worst = -1, wd = 3;
            for (int i = 0; i < L.Parts.Count; i++) { var o = Obj(i, Report); if (o.Fact > 0f && o.Fact < 0.999f && o.Days > wd) { wd = o.Days; worst = i; } }
            if (worst >= 0) { int k = worst; N(now.Date.AddHours(8).AddMinutes(25), "triangle_alert", "Отставание " + wd + " дн. · " + Pt(k).Name, "по съёмке " + Day(Report), new Color(0.96f, 0.65f, 0.14f), () => { SetTab(T4D); SelectObj(k, true); }); }
            N(now.Date.AddHours(8).AddMinutes(10), "history", "Загружена съёмка " + Day(Report), "ортофотоплан и 3D-модель площадки", Blue, () => SetTab(TSurv));
        }
        void OpenCam(int i) { SetTab(TVid); camIx = i; camYawOff = camPitchOff = 0f; camFov = 58f; view = View.Cam; crewSeen = -1; SetTab(TVid); }
        void CamBack() { if (tab == TVid) { view = View.Complex; SetTab(TVid); } else SetView(View.Floor); }
        void MonitorCard(VisualElement parent)
        {
            var c = Card(parent); Head(c, "scan_eye", "Мониторинг объекта");
            var m = new MonCard();
            c.Add(FactRow("Последняя съёмка", out m.Last)); c.Add(FactRow("Текущий этап", out m.Stage));
            c.Add(FactRow("Следующая контрольная точка", out m.Next)); c.Add(FactRow("Следующая съёмка", out m.NextSv));
            c.Add(Para("В разделе «Съёмки» можно сравнить объект по датам съёмок, план и факт."));
            monCards.Add(m);
        }
        void RefreshMonCards()
        {
            if (monCards.Count == 0) return;
            float last = LastSurvey(date); string stage = StageNow(obj), next = NextMilestone(), nsv = Day(last + 2f / 12f);
            foreach (var m in monCards) { m.Last.text = Day(last); m.Stage.text = stage; m.Next.text = next; m.NextSv.text = nsv; }
        }
        void RefreshObject(OS[] os)
        {
            pasV[5].text = "Строительство · " + StageNow(obj);
            int last = 0; for (int i = 1; i < os.Length; i++) if (os[i].FactEnd > os[last].FactEnd) last = i;
            int ld = Mathf.RoundToInt((os[last].FactEnd - L.Finish) * 365f);
            endBig.text = Mathf.FloorToInt(L.Finish) + " год";
            endSub.text = "План — " + IconicFloors.MonthYear(L.Finish) + " · прогноз по съёмке — " + IconicFloors.MonthYear(os[last].FactEnd) + " (" + EndDev(ld) + ")";
            endSub.EnableInClassList("warn", ld > 3);
        }

        // ================================================================== Съёмки
        readonly List<float> surveys = new List<float>();
        int svA, svB = -1, svTool; float split = 0.5f;
        bool svPlan = true, lyBase = true, lyBim = true, lyGcp = true, lyDiff = true;
        VisualElement cmpClip, cmpDiv, svOver, svBar, svTools, chrono, chronoList, lyList, zoneChart, chgList;
        Image photoB; Label chipL, chipR, chipA, chipB, attrib, lyText, zoneTitle, zP, zF, zD, chgSub, chronoText;
        readonly List<Button> lyBtns = new List<Button>(); readonly List<Button> svToolBtns = new List<Button>();
        bool pickB;
        Camera mon2; RenderTexture monRT2;
        /// <summary>The surveys of the site: a flight every two months back from the last one (at most eight), not before the works start.</summary>
        void MakeSurveys()
        {
            surveys.Clear();
            for (int k = 0; k < 8; k++) { float d = Report - k * (2f / 12f); if (d < L.Begin + 0.06f) break; surveys.Insert(0, d); }
            if (surveys.Count == 0) surveys.Add(Report);
            svA = surveys.Count - 1; svB = -1; split = 0.5f;
        }
        float LastSurvey(float d) { float s = surveys.Count > 0 ? surveys[0] : Report; foreach (var x in surveys) if (x <= d + 1e-4f) s = x; return s; }
        static float Gsd(int i) => 2.4f + 0.3f * ((i * 7) % 4);
        static int Shots(int i) => 1080 + (i * 137) % 420;

        void BuildCompare()
        {
            cmpClip = new VisualElement { pickingMode = PickingMode.Ignore }; cmpClip.AddToClassList("mon-cmp"); body.Add(cmpClip);
            photoB = new Image { scaleMode = ScaleMode.StretchToFill, pickingMode = PickingMode.Ignore }; photoB.AddToClassList("mon-cmp-img"); cmpClip.Add(photoB);
            svOver = new VisualElement { pickingMode = PickingMode.Ignore }; svOver.AddToClassList("mon-photo"); svOver.generateVisualContent += DrawSurvey; body.Add(svOver);
            // the dividing line: a wide grip around a thin line, so it is easy to catch with a mouse or a touchpad
            cmpDiv = new VisualElement(); cmpDiv.AddToClassList("mon-div"); body.Add(cmpDiv);
            var ln = new VisualElement { pickingMode = PickingMode.Ignore }; ln.AddToClassList("mon-div-line"); cmpDiv.Add(ln);
            var h = new Label("< >") { pickingMode = PickingMode.Ignore }; h.AddToClassList("mon-div-h"); cmpDiv.Add(h);
            cmpDiv.RegisterCallback<PointerDownEvent>(e => { cmpDiv.CapturePointer(e.pointerId); SplitTo(e.position.x); e.StopPropagation(); });
            cmpDiv.RegisterCallback<PointerMoveEvent>(e => { if (cmpDiv.HasPointerCapture(e.pointerId)) { SplitTo(e.position.x); e.StopPropagation(); } });
            cmpDiv.RegisterCallback<PointerUpEvent>(e => { if (cmpDiv.HasPointerCapture(e.pointerId)) cmpDiv.ReleasePointer(e.pointerId); });
            chipL = new Label { pickingMode = PickingMode.Ignore }; chipL.AddToClassList("mon-chip"); body.Add(chipL);
            chipR = new Label { pickingMode = PickingMode.Ignore }; chipR.AddToClassList("mon-chip"); chipR.AddToClassList("cur"); body.Add(chipR);
        }
        void BuildSurvey()
        {
            // left: the layers, the monitoring, the progress of a zone
            var lc = Card(svL);
            var lh = new Button(() => Vis(lyList, lyList.style.display == DisplayStyle.None)) { focusable = false }; lh.AddToClassList("mon-drop");
            lh.Add(TwinUI.Icon("layers", 16)); lyText = new Label { pickingMode = PickingMode.Ignore }; lyText.AddToClassList("mon-title"); lh.Add(lyText);
            var lsp = new VisualElement { pickingMode = PickingMode.Ignore }; lsp.style.flexGrow = 1; lh.Add(lsp); lh.Add(TwinUI.Icon("chevron_down", 14)); lc.Add(lh);
            lyList = new VisualElement(); lyList.style.marginTop = 6; lc.Add(lyList);
            Layer("Ортофотоплан и город", () => lyBase, v => lyBase = v);
            Layer("BIM-контуры зданий", () => lyBim, v => lyBim = v);
            Layer("Контрольные точки (GCP)", () => lyGcp, v => lyGcp = v);
            Layer("Изменения между съёмками", () => lyDiff, v => lyDiff = v);
            MonitorCard(svL);
            var zc = Card(svL);
            zoneTitle = Head(zc, "chart_line", "Прогресс зоны");
            var tiles = new VisualElement(); tiles.AddToClassList("mon-ztiles"); zc.Add(tiles);
            zP = ZTile(tiles, "План"); zF = ZTile(tiles, "Факт"); zD = ZTile(tiles, "Откл.");
            zoneChart = new VisualElement(); zoneChart.AddToClassList("mon-chart"); zoneChart.generateVisualContent += DrawZone; zc.Add(zoneChart);
            var leg = new VisualElement(); leg.AddToClassList("mon-legend");
            leg.Add(new Label("- - План") { pickingMode = PickingMode.Ignore });
            var lf = new Label("— Факт") { pickingMode = PickingMode.Ignore }; lf.style.color = Blue; leg.Add(lf);
            var lo = new Label("● Съёмки") { pickingMode = PickingMode.Ignore }; lo.style.color = Orange; leg.Add(lo);
            zc.Add(leg);

            // right: what changed between the two surveys
            var cc = Card(svR); Head(cc, "activity", "Изменения между съёмками");
            chgSub = new Label { pickingMode = PickingMode.Ignore }; chgSub.AddToClassList("mon-src"); chgSub.style.marginTop = 2; cc.Add(chgSub);
            chgList = new VisualElement(); chgList.AddToClassList("mon-table"); cc.Add(chgList);

            // the tools of the plan, a rail on the right edge
            svTools = new VisualElement(); svTools.AddToClassList("mon-svtools"); body.Add(svTools);
            SvTool("move", () => { svTool = 0; rN = 0; }, true);
            SvTool("ruler", () => { svTool = 1; rN = 0; }, true);
            SvTool("maximize", () => { zoomK = 1f; planPan = Vector2.zero; if (view != View.Plan) SetView(View.Complex); }, false);
            SvTool("plus", () => zoomK = Mathf.Clamp(zoomK * 0.8f, 0.2f, 3f), false);
            SvTool("minus", () => zoomK = Mathf.Clamp(zoomK * 1.25f, 0.2f, 3f), false);
        }
        Label ZTile(VisualElement parent, string cap)
        {
            var t = new VisualElement { pickingMode = PickingMode.Ignore }; t.AddToClassList("mon-ztile"); parent.Add(t);
            t.Add(new Label(cap) { pickingMode = PickingMode.Ignore });
            var v = new Label { pickingMode = PickingMode.Ignore }; v.AddToClassList("v"); t.Add(v); return v;
        }
        void Layer(string name, Func<bool> get, Action<bool> set)
        {
            var b = new Button() { focusable = false }; b.AddToClassList("mon-tgl");
            var box = new VisualElement { pickingMode = PickingMode.Ignore }; box.AddToClassList("mon-tgl-box"); b.Add(box);
            b.Add(new Label(name) { pickingMode = PickingMode.Ignore });
            b.clicked += () => { set(!get()); b.EnableInClassList("on", get()); LayersText(); dirty = true; };
            b.EnableInClassList("on", get()); lyList.Add(b); lyBtns.Add(b);
            LayersText();
        }
        void LayersText() { if (lyText != null) lyText.text = "Слои " + ((lyBase ? 1 : 0) + (lyBim ? 1 : 0) + (lyGcp ? 1 : 0) + (lyDiff ? 1 : 0)) + "/4"; }
        void SvTool(string icon, Action a, bool mode)
        {
            var b = new Button() { focusable = false }; b.AddToClassList("mon-svtool"); b.Add(TwinUI.Icon(icon, 18));
            int k = svToolBtns.Count; b.clicked += () => { a(); if (mode) for (int i = 0; i < 2 && i < svToolBtns.Count; i++) svToolBtns[i].EnableInClassList("on", svTool == i); dirty = true; };
            if (mode) b.EnableInClassList("on", svTool == k);
            svTools.Add(b); svToolBtns.Add(b);
        }
        /// <summary>The bar at the bottom of the surveys: the date shown, the date it is compared with, the attribution, the chronology.</summary>
        void BuildSurveyBar()
        {
            svBar = new VisualElement(); svBar.AddToClassList("mon-svbar"); body.Add(svBar);
            var cl = new Label("Сравнение") { pickingMode = PickingMode.Ignore }; cl.AddToClassList("mon-svbar-k"); svBar.Add(cl);
            var a = new Button(() => OpenChrono(false, true)) { focusable = false }; a.AddToClassList("mon-dchip"); a.AddToClassList("cur");
            a.Add(TwinUI.Icon("calendar", 14)); chipA = new Label { pickingMode = PickingMode.Ignore }; a.Add(chipA); svBar.Add(a);
            var sw = TwinUI.Icon("columns_2", 16); sw.style.marginLeft = 8; sw.style.marginRight = 8; svBar.Add(sw);
            var b = new Button(() => OpenChrono(true, true)) { focusable = false }; b.AddToClassList("mon-dchip");
            b.Add(TwinUI.Icon("calendar", 14)); chipB = new Label { pickingMode = PickingMode.Ignore }; b.Add(chipB); svBar.Add(b);
            svBar.Add(Widgets.Btn("×", () => { svB = -1; dirty = true; }, "small", "ghost"));
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; svBar.Add(sp);
            attrib = new Label { pickingMode = PickingMode.Ignore }; attrib.AddToClassList("mon-attrib"); svBar.Add(attrib);
            var ch = new Button(() => OpenChrono(pickB, false)) { focusable = false }; ch.AddToClassList("mon-dchip"); ch.Add(TwinUI.Icon("history", 14));
            chronoText = new Label { pickingMode = PickingMode.Ignore }; ch.Add(chronoText); svBar.Add(ch);
            // the chronology: every survey, newest first
            chrono = new VisualElement(); chrono.AddToClassList("mon-chrono"); chrono.style.display = DisplayStyle.None; body.Add(chrono);
            var hh = new Label() { pickingMode = PickingMode.Ignore }; hh.AddToClassList("lm-cap-h"); chrono.Add(hh); chrono.userData = hh;
            chronoList = new VisualElement(); chrono.Add(chronoList);
        }
        /// <summary>The list of surveys; opened from a date chip it stands over the chips, from the chronology button at the right.</summary>
        void OpenChrono(bool forB, bool atChips)
        {
            bool same = chrono.style.display == DisplayStyle.Flex && pickB == forB && chrono.ClassListContains("left") == atChips;
            pickB = forB; Vis(chrono, !same); if (same) return;
            chrono.EnableInClassList("left", atChips);
            ((Label)chrono.userData).text = forB ? "ВЫБЕРИТЕ ДАТУ ДЛЯ СРАВНЕНИЯ" : "ХРОНОЛОГИЯ СЪЁМОК · ПОКАЗАТЬ ДАТУ";
            chronoList.Clear();
            for (int i = surveys.Count - 1; i >= 0; i--)
            {
                int k = i; var r = new Button(() => { if (pickB) SetB(k); else SetA(k); Vis(chrono, false); }) { focusable = false }; r.AddToClassList("mon-chrono-r");
                if (k == svA) r.AddToClassList("a"); if (k == svB) r.AddToClassList("b");
                var tx = new VisualElement { pickingMode = PickingMode.Ignore }; tx.style.flexGrow = 1; r.Add(tx);
                var d = new Label(Day(surveys[k])) { pickingMode = PickingMode.Ignore }; d.AddToClassList("mon-work"); tx.Add(d);
                var s = new Label("ортофото " + Loc.N1(Gsd(k)) + " см/пикс · 3D-модель · " + Loc.N0(Shots(k)) + " снимков") { pickingMode = PickingMode.Ignore }; s.AddToClassList("mon-src"); tx.Add(s);
                var tag = new Label(k == svA ? "текущий" : k == svB ? "сравнение" : "") { pickingMode = PickingMode.Ignore }; tag.AddToClassList("mon-tag"); if (tag.text.Length > 0) r.Add(tag);
                chronoList.Add(r);
            }
        }
        void SetA(int i)
        {
            svA = Mathf.Clamp(i, 0, surveys.Count - 1); if (svB == svA) svB = -1;
            planMode = false; playing = false; SetDate(surveys[svA], true);
        }
        void SetB(int i) { svB = i < 0 || i >= surveys.Count || i == svA ? -1 : i; dirty = true; }

        void RefreshSurvey()
        {
            chipA.text = Day(surveys[svA]) + "  текущий";
            chipB.text = svB >= 0 ? Day(surveys[svB]) : "Выберите дату";
            chronoText.text = "Хронология съёмок · " + surveys.Count;
            attrib.text = "Ортофотоплан " + Day(surveys[svA]) + (svB >= 0 ? " и " + Day(surveys[svB]) : "") + " · " + Loc.N1(Gsd(svA)) + " см/пикс · сценарий двойника";
            // the zone: the building looked at, else the tower
            int z = obj >= 0 ? obj : TI; float pp = PlanP(z, date), fp = FactP(z, date), d = (fp - pp) * 100f;
            zoneTitle.text = "Прогресс зоны · " + Pt(z).Name;
            zP.text = Pct(pp); zF.text = Pct(fp); zD.text = Signed(d);
            zD.EnableInClassList("bad", d < -1f); zD.EnableInClassList("ok", d >= -0.2f);
            zoneChart.MarkDirtyRepaint();
            // changes: from the compared survey (or the one before) to the one shown
            float dA = surveys[svA], dB = svB >= 0 ? surveys[svB] : svA > 0 ? surveys[svA - 1] : dA;
            float d0 = Mathf.Min(dA, dB), d1 = Mathf.Max(dA, dB);
            chgSub.text = Day(d0) + " → " + Day(d1) + (svB < 0 ? " · с предыдущей съёмкой" : "");
            chgList.Clear();
            var th = new VisualElement(); th.AddToClassList("mon-tr"); th.AddToClassList("mon-th"); chgList.Add(th);
            foreach (var (c, cls) in new[] { ("Объект", "w"), ("Было", "n"), ("Стало", "n"), ("Прирост", "d") }) th.Add(Cell(c, cls));
            for (int i = 0; i < L.Parts.Count; i++)
            {
                float a = FactP(i, d0), b = FactP(i, d1); if (b <= 0f) continue;
                int k = i; var r = new VisualElement(); r.AddToClassList("mon-tr"); chgList.Add(r); r.RegisterCallback<ClickEvent>(_ => SelectObj(k, true));
                if (k == obj) r.AddToClassList("sel");
                var c0 = new VisualElement(); c0.AddToClassList("w"); c0.AddToClassList("mon-td"); r.Add(c0);
                var nl = new Label(Pt(i).Name) { pickingMode = PickingMode.Ignore }; nl.AddToClassList("mon-work"); c0.Add(nl);
                var sl = new Label(ChangeText(i, a, b)) { pickingMode = PickingMode.Ignore }; sl.AddToClassList("mon-src"); c0.Add(sl);
                r.Add(Cell(Pct(a), "n")); r.Add(Cell(Pct(b), "n"));
                var dl = Cell(b - a > 0.0005f ? "+" + Loc.N1((b - a) * 100f) + " п.п." : "—", "d"); dl.EnableInClassList("ok", b - a > 0.0005f); r.Add(dl);
            }
        }
        /// <summary>What was built on building i between two surveys, in words (the tower: floors of the frame and of the facade).</summary>
        string ChangeText(int i, float a, float b)
        {
            if (b >= 0.999f && a < 0.999f) return "введён в эксплуатацию";
            if (i == TI)
            {
                int f0 = Count(a, IconicFloors.PFacade), f1 = Count(b, IconicFloors.PFacade), g0 = Count(a, IconicFloors.PFacade + 1), g1 = Count(b, IconicFloors.PFacade + 1);
                if (f1 > f0 || g1 > g0) return (f1 > f0 ? "каркас +" + (f1 - f0) + " эт. (" + f1 + " из " + IconicShape.Floors + ")" : "каркас завершён") + (g1 > g0 ? " · фасад +" + (g1 - g0) + " эт." : "");
            }
            string now = null; float best = -1f;
            foreach (var w in works) { if (w.Sum || w.Part != i) continue; float q = Mathf.Clamp01((b - w.A) / (w.B - w.A)); if (q > 0f && q < 0.999f && w.B > best) { best = w.B; now = w.Name.ToLower(); } }
            return a <= 0f ? "начаты работы" + (now != null ? ": " + now : "") : now ?? "без изменений";
        }

        // ---- the second date and the marks of the plan
        /// <summary>A comparison of two surveys: the same view at the other date into a second picture, shown left of the divider.</summary>
        /// <summary>A point of the screen (x) is close enough to the dividing line of the comparison to take it.</summary>
        bool NearSplit(float x)
        {
            if (tab != TSurv || svB < 0 || body == null) return false;
            var b = body.worldBound; return Mathf.Abs(x - (b.xMin + b.width * split)) < 48f;
        }
        void SplitTo(float x) { var b = body.worldBound; split = Mathf.Clamp((x - b.xMin) / Mathf.Max(b.width, 1f), 0.03f, 0.97f); dirty = true; }
        void Compare()
        {
            bool on = tab == TSurv && svB >= 0 && monRT != null;
            Vis(cmpClip, on); Vis(cmpDiv, on); Vis(chipL, on); Vis(chipR, on);
            if (!on) return;
            if (mon2 == null) { var g = new GameObject("Iconic monitoring · second survey"); g.transform.SetParent(transform, false); mon2 = g.AddComponent<Camera>(); mon2.enabled = false; }
            if (monRT2 == null || monRT2.width != monRT.width || monRT2.height != monRT.height)
            {
                if (monRT2 != null) { mon2.targetTexture = null; monRT2.Release(); }
                monRT2 = new RenderTexture(monRT.width, monRT.height, 24) { name = "iconic_monitor_b", antiAliasing = 4 }; monRT2.Create();
            }
            mon2.CopyFrom(mon); mon2.enabled = false; mon2.targetTexture = monRT2; mon2.projectionMatrix = mon.projectionMatrix;
            var ls = LandmarkSystem.Instance;
            if (ls != null)
            {
                ls.ApplyAt(L.Id, surveys[svB]);
                bool fog = RenderSettings.fog; if (mon2.orthographic) RenderSettings.fog = false;          // the plan without haze, like the first
                try { mon2.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] second survey: " + e.Message); }
                RenderSettings.fog = fog;
                ls.ApplyAt(L.Id, LandmarkSystem.YearNow);
            }
            if (photoB.image != monRT2) photoB.image = monRT2;
            var br = body.layout; if (br.width < 10f) return;
            cmpClip.style.width = br.width * split; photoB.style.width = br.width; photoB.style.height = br.height;
            cmpDiv.style.left = br.width * split;
            chipL.text = Day(surveys[svB]); chipR.text = Day(surveys[svA]) + " · текущий";
            chipL.style.left = Mathf.Max(br.width * split - 150f, 330f); chipR.style.left = Mathf.Min(br.width * split + 14f, br.width - 470f);
        }
        // control points of the survey (local plot coordinates), their labels, the labels of the changes and of the ruler
        readonly List<Vector3> gcp = new List<Vector3>(); readonly List<Label> gcpLab = new List<Label>(), diffLab = new List<Label>();
        Label rulerLab; Vector3 rA, rB; int rN; Vector2 planPan;
        bool Measuring => tab == TSurv && svTool == 1;
        void BuildMarks()
        {
            gcp.Clear(); gcpLab.Clear(); diffLab.Clear();
            float x = L.PadW * 0.5f - 10f, z = L.PadD * 0.5f - 10f;
            foreach (var p in new[] { new Vector3(-x, 0.3f, -z), new Vector3(x, 0.3f, -z), new Vector3(x, 0.3f, z), new Vector3(-x, 0.3f, z), new Vector3(0f, 0.3f, -z), new Vector3(0f, 0.3f, z) }) gcp.Add(p);
            for (int i = 0; i < gcp.Count; i++) { var l = new Label("GCP-" + (i + 1)) { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-gcp"); body.Add(l); gcpLab.Add(l); }
            for (int i = 0; i < L.Parts.Count; i++) { var l = new Label { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-diff"); body.Add(l); diffLab.Add(l); }
            rulerLab = new Label { pickingMode = PickingMode.Ignore }; rulerLab.AddToClassList("mon-ruler"); body.Add(rulerLab);
        }
        Vector2 Screen2(Vector3 local, Rect r, out bool ok)
        {
            var vp = mon.WorldToViewportPoint(model.TransformPoint(local)); ok = vp.z > 0f && vp.x > -0.2f && vp.x < 1.2f && vp.y > -0.2f && vp.y < 1.2f;
            return new Vector2(vp.x * r.width, (1f - vp.y) * r.height);
        }
        /// <summary>Places the labels of the control points, of the changes over the buildings and of the ruler (every frame, the view moves).</summary>
        void SurveyMarks()
        {
            bool on = tab == TSurv && monRT != null; var r = body.layout;
            for (int i = 0; i < gcpLab.Count; i++)
            {
                var p = Screen2(gcp[i], r, out bool ok); bool v = on && lyGcp && ok; Vis(gcpLab[i], v);
                if (v) { gcpLab[i].style.left = p.x + 12f; gcpLab[i].style.top = p.y - 22f; }
            }
            float dA = surveys.Count > 0 ? surveys[svA] : date, dB = svB >= 0 ? surveys[svB] : svA > 0 ? surveys[svA - 1] : dA;
            for (int i = 0; i < diffLab.Count; i++)
            {
                var pt = Pt(i); float b = FactP(i, Mathf.Max(dA, dB)), a = FactP(i, Mathf.Min(dA, dB));
                bool v = on && lyDiff && b > 0f;
                Vector2 p = default;
                if (v) { float h = pt.Land ? 2f : Mathf.Max(pt.H * Mathf.Clamp01((b - 0.08f) / 0.62f), 3f); p = Screen2(new Vector3(pt.Focus.x, h + 3f, pt.Focus.z), r, out bool ok); v = ok; }
                Vis(diffLab[i], v);
                if (!v) continue;
                diffLab[i].style.left = p.x; diffLab[i].style.top = p.y;
                string t = pt.Short + "  " + Pct(b) + (b - a > 0.0005f ? "  +" + Loc.N1((b - a) * 100f) + " п.п." : "");
                if (diffLab[i].userData as string != t) { diffLab[i].userData = t; diffLab[i].text = t; }
                diffLab[i].EnableInClassList("up", b - a > 0.0005f);
            }
            bool rv = on && rN >= 2;
            Vis(rulerLab, rv);
            if (rv)
            {
                var a = Screen2(rA, r, out _); var b = Screen2(rB, r, out _); var m = (a + b) * 0.5f;
                rulerLab.style.left = m.x; rulerLab.style.top = m.y - 26f; rulerLab.text = Loc.N1(Vector3.Distance(rA, rB)) + " м";
            }
            if (on) svOver.MarkDirtyRepaint();
        }
        /// <summary>A click with the ruler: the point on the ground of the plot; two points — the distance between them.</summary>
        void Measure(VisualElement e, Vector2 lp)
        {
            var r = e.contentRect; if (r.width < 10f) return;
            var ray = mon.ViewportPointToRay(new Vector3(lp.x / r.width, 1f - lp.y / r.height, 0f));
            var plane = new Plane(Vector3.up, model.position);
            if (!plane.Raycast(ray, out float t)) return;
            var p = model.InverseTransformPoint(ray.GetPoint(t)); p.y = 0.3f;
            if (rN != 1) { rA = p; rN = 1; } else { rB = p; rN = 2; }
        }
        static readonly Color Red = new Color(1f, 0.27f, 0.23f, 0.95f), Purple = new Color(0.74f, 0.42f, 1f);
        /// <summary>Over the surveys: the BIM outlines of the buildings and the plot boundary (red), the control points (purple), the ruler.</summary>
        void DrawSurvey(MeshGenerationContext ctx)
        {
            if (tab != TSurv || mon == null || model == null || monRT == null) return;
            var r = svOver.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
            if (lyBim)
            {
                MakeOutlines();
                g.strokeColor = Red; g.lineWidth = 1.6f; g.lineCap = LineCap.Butt;
                g.BeginPath();
                if (outl != null)
                    foreach (var list in outl)
                        foreach (var s in list)
                        {
                            var a = Screen2(new Vector3(s.x, 0.3f, s.y), r, out bool o1); var b = Screen2(new Vector3(s.z, 0.3f, s.w), r, out bool o2);
                            if (o1 && o2) { g.MoveTo(a); g.LineTo(b); }
                        }
                g.Stroke();
                // the plot, dashed
                float x = L.PadW * 0.5f, z = L.PadD * 0.5f; var c = new[] { new Vector3(-x, 0.3f, -z), new Vector3(x, 0.3f, -z), new Vector3(x, 0.3f, z), new Vector3(-x, 0.3f, z) };
                g.strokeColor = new Color(1f, 0.27f, 0.23f, 0.7f); g.lineWidth = 1.2f;
                for (int i = 0; i < 4; i++) { var a = Screen2(c[i], r, out bool o1); var b = Screen2(c[(i + 1) % 4], r, out bool o2); if (o1 && o2) Dashed(g, a, b, 7f, 5f); }
            }
            if (lyGcp)
                foreach (var p0 in gcp)
                {
                    var p = Screen2(p0, r, out bool ok); if (!ok) continue;
                    g.strokeColor = Purple; g.lineWidth = 1.6f;
                    g.BeginPath(); g.Arc(p, 8f, 0f, 360f); g.Stroke();
                    g.BeginPath(); g.MoveTo(p + new Vector2(-13f, 0f)); g.LineTo(p + new Vector2(-4f, 0f)); g.MoveTo(p + new Vector2(4f, 0f)); g.LineTo(p + new Vector2(13f, 0f));
                    g.MoveTo(p + new Vector2(0f, -13f)); g.LineTo(p + new Vector2(0f, -4f)); g.MoveTo(p + new Vector2(0f, 4f)); g.LineTo(p + new Vector2(0f, 13f)); g.Stroke();
                    g.fillColor = Purple; g.BeginPath(); g.Arc(p, 2f, 0f, 360f); g.Fill();
                }
            if (rN >= 1)
            {
                var a = Screen2(rA, r, out _);
                if (rN >= 2) { var b = Screen2(rB, r, out _); g.strokeColor = Color.white; g.lineWidth = 2f; g.BeginPath(); g.MoveTo(a); g.LineTo(b); g.Stroke(); g.fillColor = Color.white; g.BeginPath(); g.Arc(b, 4f, 0f, 360f); g.Fill(); }
                g.fillColor = Color.white; g.BeginPath(); g.Arc(a, 4f, 0f, 360f); g.Fill();
            }
        }
        // ---- BIM outlines: the footprint of every building of the model, as drawn in plan (computed once per object)
        List<Vector4>[] outl; string outlId;
        /// <summary>The footprints of the buildings from the model itself: every triangle of a building (not trees, not lawns) is drawn into
        /// a 1.5 m grid in plan, small gaps are closed, and the edges between filled and empty cells are joined into straight runs.</summary>
        void MakeOutlines()
        {
            if (outl != null && outlId == L.Id) return;
            outlId = L.Id; int n = L.Parts.Count; outl = new List<Vector4>[n]; for (int i = 0; i < n; i++) outl[i] = new List<Vector4>();
            var mf = model != null ? model.GetComponent<MeshFilter>() : null; var m = mf != null ? mf.sharedMesh : null;
            if (m == null || !m.isReadable) return;
            var v = m.vertices; var u1 = new List<Vector2>(); var u2 = new List<Vector2>(); m.GetUVs(1, u1); m.GetUVs(2, u2); var tri = m.triangles;
            if (u2.Count != v.Length) return;
            const float cs = 1.5f; float x0 = -L.PadW * 0.5f - 30f, z0 = -L.PadD * 0.5f - 30f;
            int nx = Mathf.CeilToInt((L.PadW + 60f) / cs), nz = Mathf.CeilToInt((L.PadD + 60f) / cs);
            var grid = new bool[n][]; for (int i = 0; i < n; i++) grid[i] = new bool[nx * nz];
            void Mark(bool[] gr, float x, float z) { int i = Mathf.FloorToInt((x - x0) / cs), j = Mathf.FloorToInt((z - z0) / cs); if (i >= 0 && j >= 0 && i < nx && j < nz) gr[j * nx + i] = true; }
            void Edge(bool[] gr, Vector3 a, Vector3 b) { float len = new Vector2(b.x - a.x, b.z - a.z).magnitude; int steps = Mathf.Max(1, Mathf.CeilToInt(len / (cs * 0.5f))); for (int s = 0; s <= steps; s++) { var p = Vector3.Lerp(a, b, s / (float)steps); Mark(gr, p.x, p.z); } }
            for (int k = 0; k + 2 < tri.Length; k += 3)
            {
                int ia = tri[k], ib = tri[k + 1], ic = tri[k + 2];
                int pid = Mathf.RoundToInt(u2[ia].x) - 1; if (pid < 0 || pid >= n || L.Parts[pid].Land) continue;
                if (u1.Count == v.Length && u1[ia].y < -4.5f) continue;                 // trees and lawns are not the building
                var gr = grid[pid]; Vector3 A = v[ia], B = v[ib], C = v[ic];
                Edge(gr, A, B); Edge(gr, B, C); Edge(gr, C, A);
                float area = (B.x - A.x) * (C.z - A.z) - (C.x - A.x) * (B.z - A.z);
                if (Mathf.Abs(area) < cs * cs) continue;
                int i0 = Mathf.Max(0, Mathf.FloorToInt((Mathf.Min(A.x, Mathf.Min(B.x, C.x)) - x0) / cs)), i1 = Mathf.Min(nx - 1, Mathf.FloorToInt((Mathf.Max(A.x, Mathf.Max(B.x, C.x)) - x0) / cs));
                int j0 = Mathf.Max(0, Mathf.FloorToInt((Mathf.Min(A.z, Mathf.Min(B.z, C.z)) - z0) / cs)), j1 = Mathf.Min(nz - 1, Mathf.FloorToInt((Mathf.Max(A.z, Mathf.Max(B.z, C.z)) - z0) / cs));
                for (int j = j0; j <= j1; j++)
                    for (int i = i0; i <= i1; i++)
                    {
                        float px = x0 + (i + 0.5f) * cs, pz = z0 + (j + 0.5f) * cs;
                        float w0 = (B.x - A.x) * (pz - A.z) - (px - A.x) * (B.z - A.z), w1 = (C.x - B.x) * (pz - B.z) - (px - B.x) * (C.z - B.z), w2 = (A.x - C.x) * (pz - C.z) - (px - C.x) * (A.z - C.z);
                        if ((w0 >= 0f && w1 >= 0f && w2 >= 0f) || (w0 <= 0f && w1 <= 0f && w2 <= 0f)) gr[j * nx + i] = true;
                    }
            }
            for (int p = 0; p < n; p++)
            {
                var g = Close1(grid[p], nx, nz);
                bool Occ(int i, int j) => i >= 0 && j >= 0 && i < nx && j < nz && g[j * nx + i];
                // runs of edges along x (between rows j−1 and j) and along z (between columns i−1 and i)
                for (int j = 0; j <= nz; j++)
                    for (int i = 0; i < nx; i++)
                    {
                        if (Occ(i, j - 1) == Occ(i, j)) continue;
                        int s = i; while (i + 1 < nx && Occ(i + 1, j - 1) != Occ(i + 1, j) && Occ(i + 1, j) == Occ(s, j)) i++;
                        outl[p].Add(new Vector4(x0 + s * cs, z0 + j * cs, x0 + (i + 1) * cs, z0 + j * cs));
                    }
                for (int i = 0; i <= nx; i++)
                    for (int j = 0; j < nz; j++)
                    {
                        if (Occ(i - 1, j) == Occ(i, j)) continue;
                        int s = j; while (j + 1 < nz && Occ(i - 1, j + 1) != Occ(i, j + 1) && Occ(i, j + 1) == Occ(i, s)) j++;
                        outl[p].Add(new Vector4(x0 + i * cs, z0 + s * cs, x0 + i * cs, z0 + (j + 1) * cs));
                    }
            }
        }
        /// <summary>Morphological closing by one cell (dilate, then erode): seams between pieces of one building are filled.</summary>
        static bool[] Close1(bool[] g, int nx, int nz)
        {
            var d = new bool[g.Length]; var e = new bool[g.Length];
            for (int j = 0; j < nz; j++) for (int i = 0; i < nx; i++)
                {
                    bool any = false;
                    for (int dj = -1; dj <= 1 && !any; dj++) for (int di = -1; di <= 1; di++) { int a = i + di, b = j + dj; if (a >= 0 && b >= 0 && a < nx && b < nz && g[b * nx + a]) { any = true; break; } }
                    d[j * nx + i] = any;
                }
            for (int j = 0; j < nz; j++) for (int i = 0; i < nx; i++)
                {
                    bool all = true;
                    for (int dj = -1; dj <= 1 && all; dj++) for (int di = -1; di <= 1; di++) { int a = i + di, b = j + dj; if (a < 0 || b < 0 || a >= nx || b >= nz || !d[b * nx + a]) { all = false; break; } }
                    e[j * nx + i] = all;
                }
            return e;
        }
        /// <summary>Progress of the zone (the building looked at) over its works: plan dashed, actual up to the survey, forecast dotted,
        /// a dot at every survey, the date shown (white) and the compared one (purple).</summary>
        void DrawZone(MeshGenerationContext ctx)
        {
            var r = zoneChart.contentRect; if (r.width < 20f || L == null) return; var g = ctx.painter2D;
            int z = obj >= 0 ? obj : TI; var pt = Pt(z);
            float a = Mathf.Max(T0, pt.A - 0.1f), b = Mathf.Min(T1, Mathf.Max(pt.B, FactDate(z, 1f)) + 0.1f);
            float L0 = 30f, B0 = 16f, W = r.width - L0 - 6f, Hh = r.height - B0 - 6f;
            Vector2 P(float d, float v) => new Vector2(L0 + (d - a) / (b - a) * W, 6f + (1f - v) * Hh);
            g.lineWidth = 1f; g.strokeColor = new Color(1f, 1f, 1f, 0.08f);
            for (int k = 0; k <= 2; k++) { float y = 6f + Hh * k / 2f; g.BeginPath(); g.MoveTo(new Vector2(L0, y)); g.LineTo(new Vector2(L0 + W, y)); g.Stroke(); }
            const int n = 48;
            g.strokeColor = PlanLine; g.lineWidth = 1.4f;
            for (int i = 0; i < n; i++) { float d0 = Mathf.Lerp(a, b, i / (float)n), d1 = Mathf.Lerp(a, b, (i + 1f) / n); Dashed(g, P(d0, PlanP(z, d0)), P(d1, PlanP(z, d1)), 4f, 3f); }
            g.lineWidth = 2f;
            for (int i = 0; i < n; i++)
            {
                float d0 = Mathf.Lerp(a, b, i / (float)n), d1 = Mathf.Lerp(a, b, (i + 1f) / n);
                if (d0 < Report) { g.strokeColor = Blue; g.BeginPath(); g.MoveTo(P(d0, FactP(z, d0))); float e = Mathf.Min(d1, Report); g.LineTo(P(e, FactP(z, e))); g.Stroke(); }
                if (d1 > Report) { g.strokeColor = BlueSoft; float s = Mathf.Max(d0, Report); Dashed(g, P(s, FactP(z, s)), P(d1, FactP(z, d1)), 2f, 3f); }
            }
            foreach (var s in surveys) if (s >= a && s <= b) { g.fillColor = Orange; g.BeginPath(); g.Arc(P(s, FactP(z, s)), 3f, 0f, 360f); g.Fill(); }
            VLine(g, P(Mathf.Clamp(date, a, b), 0f).x, 6f, 6f + Hh, new Color(1f, 1f, 1f, 0.75f), 1f);
            if (svB >= 0) VLine(g, P(Mathf.Clamp(surveys[svB], a, b), 0f).x, 6f, 6f + Hh, Purple, 1.2f);
        }

        // ================================================================== 4D
        bool d4Plan, d4Base, wireOn = true, ganttOn;
        VisualElement stList, stg, stgRow, optBody; Label stTitle; Button ganttBtn;
        readonly Label[] kpV = new Label[6], kpS = new Label[6], kpC = new Label[6];
        class Tile { public Button B; public Label P; public VisualElement Dot; public int I; }
        readonly List<Tile> tileRows = new List<Tile>();
        class StRow { public VisualElement Row, Fill, Mark; public Label P, Dv; public int W; }
        readonly List<StRow> stRows = new List<StRow>(), stgCols = new List<StRow>();
        class PRow { public VisualElement Row; public Label P, F, D; public int I; }
        readonly List<PRow> prows = new List<PRow>(); Label pfNote;
        void Build4D()
        {
            var c = Card(d4L); Head(c, "box", L.Short + " · BIM 4D");
            c.Add(FactRow("Заказчик", out var a)); a.text = Customer();
            c.Add(FactRow("Площадка", out var b)); b.text = Site();
            c.Add(FactRow("Шифр", out var s)); s.text = "AC-" + District[Mathf.Clamp(L.District, 0, 3)].Substring(0, 2).ToUpper() + "-" + L.Id.ToUpper() + "-4D";
            c.Add(FactRow("Генплан", out var g)); g.text = "мастер-план Alatau City";
            var n = new Label("шифр, график и численность — сценарий цифрового двойника") { pickingMode = PickingMode.Ignore }; n.AddToClassList("mon-src"); n.style.marginTop = 6; c.Add(n);
            // the buildings as tiles
            var tc = Card(d4L); var tg = new VisualElement(); tg.AddToClassList("mon-tiles"); tc.Add(tg);
            for (int i = -1; i < L.Parts.Count; i++)
            {
                int k = i; var t = new Tile { I = i, B = new Button(() => SelectObj(k, true)) { focusable = false } }; t.B.AddToClassList("mon-tile"); tg.Add(t.B);
                var tr = new VisualElement { pickingMode = PickingMode.Ignore }; tr.AddToClassList("mon-row"); t.B.Add(tr);
                t.Dot = Widgets.Dot(Color.gray, true); tr.Add(t.Dot);
                var nm = new Label(i < 0 ? "Весь комплекс" : Pt(i).Short) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("mon-tile-n"); tr.Add(nm);
                t.P = new Label { pickingMode = PickingMode.Ignore }; t.P.AddToClassList("mon-tile-p"); t.B.Add(t.P);
                tileRows.Add(t);
            }
            // how the model is shown (folds)
            var oc = Card(d4L);
            var oh = new Button(() => Vis(optBody, optBody.style.display == DisplayStyle.None)) { focusable = false }; oh.AddToClassList("mon-drop");
            oh.Add(TwinUI.Icon("eye", 16)); var ot = new Label("Отображение") { pickingMode = PickingMode.Ignore }; ot.AddToClassList("mon-title"); oh.Add(ot);
            var osp = new VisualElement { pickingMode = PickingMode.Ignore }; osp.style.flexGrow = 1; oh.Add(osp); oh.Add(TwinUI.Icon("chevron_down", 14)); oc.Add(oh);
            optBody = new VisualElement(); optBody.style.marginTop = 6; optBody.style.display = DisplayStyle.None; oc.Add(optBody);
            Toggle4(optBody, "Проектируемое (каркас BIM)", () => wireOn, v => wireOn = v);
            Toggle4(optBody, "Город вокруг", () => d4Base, v => d4Base = v);
            // readiness by stages of the building looked at
            var sc = Card(d4L); stTitle = Head(sc, "list_checks", "Готовность по этапам");
            stList = new VisualElement(); stList.style.marginTop = 4; sc.Add(stList);

            // right: the schedule with the crew, the KPI tiles, plan and actual by buildings
            ganttBtn = new Button(() => { ganttOn = !ganttOn; SetTab(tab); }) { focusable = false }; ganttBtn.AddToClassList("mon-wide");
            ganttBtn.Add(TwinUI.Icon("gantt_chart", 16)); ganttBtn.Add(new Label("График работ и численность") { pickingMode = PickingMode.Ignore }); d4R.Add(ganttBtn);
            var kg = new VisualElement(); kg.AddToClassList("mon-kgrid"); d4R.Add(kg);
            for (int i = 0; i < 6; i++)
            {
                var t = new VisualElement { pickingMode = PickingMode.Ignore }; t.AddToClassList("mon-kt"); kg.Add(t);
                kpC[i] = new Label { pickingMode = PickingMode.Ignore }; kpC[i].AddToClassList("mon-inv-cap"); t.Add(kpC[i]);
                kpV[i] = new Label { pickingMode = PickingMode.Ignore }; kpV[i].AddToClassList("mon-kt-v"); t.Add(kpV[i]);
                kpS[i] = new Label { pickingMode = PickingMode.Ignore }; kpS[i].AddToClassList("mon-inv-sub"); t.Add(kpS[i]);
            }
            var pc = Card(d4R); Head(pc, "chart_line", "План / факт");
            pfNote = new Label { pickingMode = PickingMode.Ignore }; pfNote.AddToClassList("mon-src"); pfNote.style.marginTop = 2; pc.Add(pfNote);
            var tb = new VisualElement(); tb.AddToClassList("mon-table"); pc.Add(tb);
            var th = new VisualElement(); th.AddToClassList("mon-tr"); th.AddToClassList("mon-th"); tb.Add(th);
            foreach (var (cc, cls) in new[] { ("Объект", "w"), ("План", "n"), ("Факт", "n"), ("Откл.", "d") }) th.Add(Cell(cc, cls));
            for (int i = 0; i < L.Parts.Count; i++)
            {
                int k = i; var pr = new PRow { I = i };
                var r = new VisualElement(); r.AddToClassList("mon-tr"); tb.Add(r); pr.Row = r; r.RegisterCallback<ClickEvent>(_ => SelectObj(k, true));
                var c0 = new VisualElement(); c0.AddToClassList("w"); c0.AddToClassList("mon-td"); r.Add(c0);
                var nl = new Label(Pt(i).Name) { pickingMode = PickingMode.Ignore }; nl.AddToClassList("mon-work"); c0.Add(nl);
                pr.P = Cell("", "n"); pr.F = Cell("", "n"); pr.D = Cell("", "d"); r.Add(pr.P); r.Add(pr.F); r.Add(pr.D); prows.Add(pr);
            }

            // the stage columns over the timeline
            stg = new VisualElement(); stg.AddToClassList("mon-stg"); body.Add(stg);
            var sh = new VisualElement { pickingMode = PickingMode.Ignore }; sh.AddToClassList("mon-row"); stg.Add(sh);
            var stt = new Label("Этапы") { pickingMode = PickingMode.Ignore }; stt.AddToClassList("mon-stg-t"); sh.Add(stt); stg.userData = stt;
            var ssp = new VisualElement { pickingMode = PickingMode.Ignore }; ssp.style.flexGrow = 1; sh.Add(ssp);
            sh.Add(Widgets.LegendItem(Green, "Выполнено")); sh.Add(Widgets.LegendItem(Blue, "В работе")); sh.Add(Widgets.LegendItem(new Color(1f, 1f, 1f, 0.25f), "Не начато"));
            stgRow = new VisualElement(); stgRow.AddToClassList("mon-stg-row"); stg.Add(stgRow);
        }
        void Toggle4(VisualElement parent, string name, Func<bool> get, Action<bool> set)
        {
            var b = new Button() { focusable = false }; b.AddToClassList("mon-tgl");
            var box = new VisualElement { pickingMode = PickingMode.Ignore }; box.AddToClassList("mon-tgl-box"); b.Add(box);
            b.Add(new Label(name) { pickingMode = PickingMode.Ignore });
            b.clicked += () => { set(!get()); b.EnableInClassList("on", get()); dirty = true; };
            b.EnableInClassList("on", get()); parent.Add(b);
        }
        /// <summary>Readiness by stages: the works of the building looked at (the buildings, for the whole complex), plan mark and actual bar.</summary>
        void FillStages()
        {
            if (stList == null) return;
            stList.Clear(); stRows.Clear();
            stTitle.text = obj < 0 ? "Готовность по объектам" : "Готовность по этапам · " + Pt(obj).Short;
            foreach (int k in vis)
            {
                var w = works[k]; var sr = new StRow { W = k };
                var r = new VisualElement(); r.AddToClassList("mon-st"); stList.Add(r); sr.Row = r;
                r.RegisterCallback<ClickEvent>(_ => { if (works[k].Sum) SelectObj(works[k].Part, true); else Select(k, true); });
                var top = new VisualElement { pickingMode = PickingMode.Ignore }; top.AddToClassList("mon-row"); r.Add(top);
                var nm = new Label((w.Sum ? "" : w.Code + "  ") + w.Name) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("mon-st-n"); top.Add(nm);
                sr.Dv = new Label { pickingMode = PickingMode.Ignore }; sr.Dv.AddToClassList("mon-st-d"); top.Add(sr.Dv);
                sr.P = new Label { pickingMode = PickingMode.Ignore }; sr.P.AddToClassList("mon-st-p"); top.Add(sr.P);
                var bar = new VisualElement { pickingMode = PickingMode.Ignore }; bar.AddToClassList("mon-bar"); bar.style.marginTop = 4; r.Add(bar);
                sr.Fill = new VisualElement { pickingMode = PickingMode.Ignore }; sr.Fill.AddToClassList("mon-fill"); bar.Add(sr.Fill);
                sr.Mark = new VisualElement { pickingMode = PickingMode.Ignore }; sr.Mark.AddToClassList("mon-mark"); bar.Add(sr.Mark);
                stRows.Add(sr);
            }
        }
        /// <summary>The stage columns over the timeline: one per work of the building (per building for the complex).</summary>
        void FillStg()
        {
            if (stgRow == null) return;
            stgRow.Clear(); stgCols.Clear();
            ((Label)stg.userData).text = obj < 0 ? "Объекты комплекса" : "Этапы · " + Pt(obj).Name;
            foreach (int k in vis)
            {
                var w = works[k]; var sc = new StRow { W = k };
                var col = new VisualElement(); col.AddToClassList("mon-stg-c"); stgRow.Add(col); sc.Row = col;
                col.RegisterCallback<ClickEvent>(_ => { if (works[k].Sum) SelectObj(works[k].Part, true); else Select(k, true); });
                var nm = new Label(w.Sum ? Pt(w.Part).Short : w.Name) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("mon-stg-n"); col.Add(nm);
                sc.P = new Label { pickingMode = PickingMode.Ignore }; sc.P.AddToClassList("mon-stg-p"); col.Add(sc.P);
                var bar = new VisualElement { pickingMode = PickingMode.Ignore }; bar.AddToClassList("mon-stg-bar"); col.Add(bar);
                sc.Fill = new VisualElement { pickingMode = PickingMode.Ignore }; sc.Fill.AddToClassList("mon-stg-fill"); bar.Add(sc.Fill);
                sc.Mark = new VisualElement { pickingMode = PickingMode.Ignore }; sc.Mark.AddToClassList("mon-mark"); bar.Add(sc.Mark);
                stgCols.Add(sc);
            }
        }
        void Refresh4D(OS[] os)
        {
            foreach (var lst in new[] { stRows, stgCols })
                foreach (var r in lst)
                {
                    var st = Stat(works[r.W], date); float f = planMode ? st.Plan : st.Fact;
                    r.P.text = Pct(f); r.Fill.style.width = Length.Percent(f * 100f); r.Mark.style.left = Length.Percent(st.Plan * 100f);
                    string c = f >= 0.999f ? "done" : f > 0f ? "now" : "wait";
                    foreach (var cc in new[] { "done", "now", "wait" }) r.Row.EnableInClassList(cc, cc == c);
                    r.Row.EnableInClassList("sel", r.W == sel);
                    if (r.Dv != null) { r.Dv.text = st.Plan <= 0f && st.Fact <= 0f ? "" : Dev(st); foreach (var cc in new[] { "ok", "warn", "bad" }) r.Dv.EnableInClassList(cc, st.Plan > 0f && cc == Cls(st.Days)); }
                }
            // the KPI tiles: of the complex, or of the building looked at
            bool fact = !planMode; float rf = Ready(date, true), rp = Ready(date, false);
            int last = 0; for (int i = 1; i < os.Length; i++) if (os[i].FactEnd > os[last].FactEnd) last = i;
            float crew = Crew(date, fact); int machines = Mathf.RoundToInt(crew / 42f) + (crew > 1f ? 2 : 0);
            float conc = 0f, concDone = 0f; for (int i = 0; i < L.Parts.Count; i++) { conc += Concrete(Pt(i)); concDone += Concrete(Pt(i)) * Mathf.Clamp01(((fact ? FactP(i, date) : PlanP(i, date)) - 0.03f) / 0.67f); }
            float dpp = obj >= 0 ? (os[obj].Fact - os[obj].Plan) * 100f : (rf - rp) * 100f;
            KT(0, "Срок СМР", Loc.N0(Mathf.RoundToInt((L.Finish - L.Begin) * 365f)) + " дн.", IconicFloors.MonthYear(L.Begin) + " – " + IconicFloors.MonthYear(L.Finish), "");
            KT(1, "Пиковая численность", Loc.N0(CrewPeak()) + " чел", "по графику работ", "");
            KT(2, "На площадке", Loc.N0(crew) + " чел", machines + " ед. техники · " + Day(date), "");
            KT(3, "Бетон", Loc.N0(concDone) + " м³", "из " + Loc.N0(conc) + " м³ по проекту", "");
            KT(4, "Факт по съёмке", Pct(Ready(Report, true)), "готовность комплекса на " + Day(Report), "");
            KT(5, obj >= 0 ? "Статус · " + Pt(obj).Short : "Статус комплекса", Signed(dpp), dpp < -0.2f ? "отставание от плана" : dpp > 0.2f ? "опережение плана" : "в графике", dpp < -1f ? "bad" : dpp < -0.2f ? "warn" : "ok");
            ganttBtn.EnableInClassList("on", ganttOn);
        }
        void KT(int i, string cap, string val, string sub, string cls)
        {
            kpC[i].text = cap; kpV[i].text = val; kpS[i].text = sub;
            foreach (var c in new[] { "ok", "warn", "bad" }) kpV[i].EnableInClassList(c, c == cls);
            kpV[i].parent.EnableInClassList("bad", cls == "bad");
        }
        /// <summary>People on the site at date d (scenario): every building under construction keeps a crew in proportion to its budget,
        /// growing to the frame and the envelope and thinning out at the finishing.</summary>
        float Crew(float d, bool fact)
        {
            float s = 0f;
            for (int i = 0; i < L.Parts.Count; i++) { float q = fact ? FactP(i, d) : PlanP(i, d); if (q > 0f && q < 1f) s += Pt(i).Capex * 3.4f * Mathf.Pow(Mathf.Sin(q * Mathf.PI), 0.7f); }
            return s;
        }
        float crewPeak = -1f;
        float CrewPeak() { if (crewPeak < 0f) { crewPeak = 0f; for (float d = T0; d <= T1; d += 1f / 24f) crewPeak = Mathf.Max(crewPeak, Crew(d, false)); } return crewPeak; }
        static float Concrete(LPart p) => p.Land ? 0f : p.Capex * 260f;

        // ================================================================== Видео
        VisualElement vidPage, vidGrid, camBar; Label vidInfo, camBarTitle, aiNote;
        int vidGroup; readonly List<Button> vidSide = new List<Button>();
        readonly Image[] tiles = new Image[NCam]; readonly VisualElement[] tileBox = new VisualElement[NCam], tileOver = new VisualElement[NCam];
        // the order on the wall and the groups of cameras: all, the tower, the site, the gate
        static readonly int[] CamOrder = { 4, 0, 1, 2, 3, 5 };
        static readonly int[][] Groups = { new[] { 4, 0, 1, 2, 3, 5 }, new[] { 0, 2 }, new[] { 4, 1, 3 }, new[] { 5 } };
        void BuildVideo()
        {
            vidPage = new VisualElement(); vidPage.AddToClassList("mon-vid"); body.Add(vidPage);
            var side = new VisualElement(); side.AddToClassList("mon-vid-side"); vidPage.Add(side);
            Side(side, "bell", "Все события", () => VidGroup(0), -1);
            var gh = new VisualElement { pickingMode = PickingMode.Ignore }; gh.AddToClassList("mon-vid-gh"); side.Add(gh);
            gh.Add(new Label("ГРУППЫ КАМЕР") { pickingMode = PickingMode.Ignore }); var gs = new VisualElement { pickingMode = PickingMode.Ignore }; gs.style.flexGrow = 1; gh.Add(gs); gh.Add(TwinUI.Icon("plus", 14));
            Side(side, "layout_grid", "Главная", () => VidGroup(0), 0);
            Side(side, "building_2", "Башня", () => VidGroup(1), 1);
            Side(side, "map", "Площадка", () => VidGroup(2), 2);
            Side(side, "truck", "Въезд · КПП", () => VidGroup(3), 3);
            var sep = new VisualElement { pickingMode = PickingMode.Ignore }; sep.AddToClassList("mon-vid-sep"); side.Add(sep);
            Side(side, "archive", "Архив", () => VidInfo("Архив записей: 30 суток по шести камерам, поиск по событиям видеоаналитики."), -2);
            Side(side, "hard_drive", "Хранилище", () => VidInfo("Хранилище: шесть потоков 4K / H.265, занято 14,2 из 48 ТБ."), -3);
            Side(side, "settings", "Настройка", () => VidInfo("Настройка аналитики: зоны контроля касок и жилетов, линии подсчёта техники на КПП, опасные зоны под кранами."), -4);
            var mainV = new VisualElement(); mainV.AddToClassList("mon-vid-main"); vidPage.Add(mainV);
            var ev = new VisualElement(); ev.AddToClassList("mon-vid-ev"); mainV.Add(ev);
            var eh = new VisualElement { pickingMode = PickingMode.Ignore }; eh.AddToClassList("mon-row"); ev.Add(eh);
            eh.Add(TwinUI.Icon("scan_eye", 16)); var et = new Label("Последние события") { pickingMode = PickingMode.Ignore }; et.AddToClassList("mon-title"); eh.Add(et);
            var esp = new VisualElement { pickingMode = PickingMode.Ignore }; esp.style.flexGrow = 1; eh.Add(esp);
            var on = new Label("6 из 6 камер онлайн · ИИ-видеоаналитика") { pickingMode = PickingMode.Ignore }; on.AddToClassList("note"); eh.Add(on);
            var now = DateTime.Now;
            Ev(ev, now.AddMinutes(-4).ToString("HH:mm"), "CAM-05", "Въезд бетоновоза: 6-я машина за смену, разгрузка на площадке Б", Blue);
            Ev(ev, now.AddMinutes(-23).ToString("HH:mm"), "CAM-04", "Монтаж модулей витража: 4 модуля за час, норма — 5", Orange);
            Ev(ev, now.AddMinutes(-49).ToString("HH:mm"), "CAM-07", "Работа у края плиты без страховки — прораб уведомлён, закрыто", Orange);
            Ev(ev, now.AddMinutes(-71).ToString("HH:mm"), "CAM-01", "Все в касках и жилетах, опасных зон под краном не занято", Green);
            vidInfo = new Label { pickingMode = PickingMode.Ignore }; vidInfo.AddToClassList("mon-vid-info"); mainV.Add(vidInfo);
            vidGrid = new VisualElement(); vidGrid.AddToClassList("mon-vid-grid"); mainV.Add(vidGrid);
            foreach (int i in CamOrder)
            {
                int k = i; var box = new VisualElement(); box.AddToClassList("mon-vcam"); vidGrid.Add(box); tileBox[i] = box;
                box.RegisterCallback<ClickEvent>(_ => OpenCam(k));
                tiles[i] = new Image { scaleMode = ScaleMode.ScaleAndCrop, pickingMode = PickingMode.Ignore }; tiles[i].AddToClassList("mon-feed-img"); box.Add(tiles[i]);
                var ov = new VisualElement { pickingMode = PickingMode.Ignore }; ov.AddToClassList("mon-feed-over"); ov.generateVisualContent += ctx => DrawFeed(ctx, tileOver[k], k); box.Add(ov); tileOver[i] = ov;
                var lab = new Label("  " + CamId[i] + " · REC") { pickingMode = PickingMode.Ignore }; lab.AddToClassList("mon-cam-id"); ov.Add(lab);
                var chip = new Label(CamName[i]) { pickingMode = PickingMode.Ignore }; chip.AddToClassList("mon-vchip"); box.Add(chip); camCap[i] = chip; capSet[i] = chip.text;
            }
            // an open camera: the main picture with a bar to go back
            camBar = new VisualElement(); camBar.AddToClassList("mon-cambar"); body.Add(camBar);
            var back = new Button(CamBack) { focusable = false }; back.AddToClassList("btn"); back.AddToClassList("small"); back.AddToClassList("mon-back");
            back.Add(TwinUI.Icon("arrow_left", 14)); back.Add(new Label("Все камеры") { pickingMode = PickingMode.Ignore }); camBar.Add(back);
            camBarTitle = new Label { pickingMode = PickingMode.Ignore }; camBarTitle.AddToClassList("mon-title"); camBar.Add(camBarTitle);
            var csp = new VisualElement { pickingMode = PickingMode.Ignore }; csp.style.flexGrow = 1; camBar.Add(csp);
            camBar.Add(Widgets.Dot(Green, true));
            aiNote = new Label { pickingMode = PickingMode.Ignore }; aiNote.AddToClassList("note"); aiNote.style.marginLeft = 6; camBar.Add(aiNote);
        }
        void Side(VisualElement side, string icon, string name, Action a, int key)
        {
            var b = new Button(() => { a(); foreach (var x in vidSide) x.EnableInClassList("on", (int)x.userData == key || key == -1 && (int)x.userData == 0); }) { focusable = false };
            b.AddToClassList("mon-vid-item"); b.userData = key; b.Add(TwinUI.Icon(icon, 16)); b.Add(new Label(name) { pickingMode = PickingMode.Ignore });
            if (key == 0) b.AddToClassList("on");
            side.Add(b); vidSide.Add(b);
        }
        void VidGroup(int g)
        {
            vidGroup = Mathf.Clamp(g, 0, Groups.Length - 1); rr = 0;
            Vis(vidInfo, false); Vis(vidGrid, true);
            for (int i = 0; i < NCam; i++) Vis(tileBox[i], Array.IndexOf(Groups[vidGroup], i) >= 0);
            vidGrid?.EnableInClassList("few", Groups[vidGroup].Length <= 2);
        }
        void VidInfo(string text) { vidInfo.text = text; Vis(vidInfo, true); Vis(vidGrid, false); }

        // ------------------------------------------------------------------ small builders
        static Label Head(VisualElement card, string icon, string title)
        {
            var h = new VisualElement { pickingMode = PickingMode.Ignore }; h.AddToClassList("mon-row");
            var ic = TwinUI.Icon(icon, 16); ic.style.marginRight = 7; h.Add(ic);
            var t = new Label(title) { pickingMode = PickingMode.Ignore }; t.AddToClassList("mon-title"); t.style.flexShrink = 1; h.Add(t); card.Add(h); return t;
        }
    }
}
