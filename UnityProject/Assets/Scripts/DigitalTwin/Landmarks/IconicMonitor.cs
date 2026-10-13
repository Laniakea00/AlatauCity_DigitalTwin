using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>«Мониторинг строительства» of Iconic Complex, in the style of the QazTWIN construction pages: the city dims, a window opens
    /// with the aerial survey of one stage — the monolithic frame of the tower in 2028 (the slab being cast, the core formwork, cranes),
    /// shot by a "drone" camera of the twin — and, around it, the zone card, progress plan vs actual with a chart, the plan-fact table of the
    /// works with their deviations, and a site camera (CCTV) with video analytics. The numbers come from the same stage model as the
    /// floors (IconicFloors); the plan runs ≈ 2 months ahead of the actual. Esc or × closes.</summary>
    public class IconicMonitor : MonoBehaviour
    {
        public static IconicMonitor Instance;
        public static bool Open => Instance != null && Instance.open;
        /// <summary>Frame in which the window was closed (its Esc must not also take the camera out of the tower).</summary>
        public static int ClosedFrame = -10;
        /// <summary>The stage shown: the frame of the upper floors in 2028 (between the start of the works and the hand-over).</summary>
        public const int StageYear = 2028;
        const float PlanLead = 0.035f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Iconic Complex · monitoring").AddComponent<IconicMonitor>(); }
        void Awake() { Instance = this; }

        bool open; int prevYear = -1; float t; bool shot; float nextCam;
        Camera drone, site; RenderTexture droneRT, siteRT;
        VisualElement overlay, body, pin; Image photo, feedImg; Label feedClock, hud; VisualElement feedOver; float phase;
        Vector3 deck, siteEye; int work; float camYaw0;

        // ------------------------------------------------------------------ open / close
        public void Show()
        {
            var ii = IconicInterior.Instance; var ls = LandmarkSystem.Instance; if (ii == null || ls == null || !ls.Ready) return;
            if (open) return;
            prevYear = TwinState.Year;
            if (TwinState.Year != StageYear) TwinState.Year = StageYear;
            if (!IconicInterior.Active) ii.Enter();
            if (!IconicInterior.Active) { RestoreYear(); return; }
            var l = ls.Get("iconic"); float p = LandmarkSystem.Progress(l, StageYear);
            work = WorkingFloor(l, p);
            ii.FocusFloor(work);
            open = true; t = 0f; shot = false; nextCam = 0f;
            Build(l, p);
        }
        public void Close()
        {
            if (!open) return;
            open = false; ClosedFrame = Time.frameCount;
            if (overlay != null) overlay.RemoveFromHierarchy();
            MapCamera.BlockInput = TwinUI.Instance != null && TwinUI.Instance.PointerOverChrome;
            RestoreYear();
        }
        void RestoreYear() { if (prevYear > 0 && TwinState.Year != prevYear) TwinState.Year = prevYear; prevYear = -1; }
        void OnDestroy() { if (droneRT != null) droneRT.Release(); if (siteRT != null) siteRT.Release(); }

        static int WorkingFloor(Landmark l, float p)
        {
            for (int i = IconicShape.Levels - 1; i >= 0; i--) if (IconicFloors.Phase(i, p, l.Height, out _) == IconicFloors.PFrame) return i;
            for (int i = IconicShape.Levels - 1; i >= 0; i--) if (IconicFloors.Phase(i, p, l.Height, out _) > IconicFloors.PNone) return i;
            return 0;
        }
        /// <summary>How many of the 56 floors have passed a phase at progress p.</summary>
        static int Count(Landmark l, float p, int phase)
        {
            int n = 0; for (int i = 0; i < 56; i++) if (IconicFloors.Phase(i, Mathf.Min(p, 0.998f), l.Height, out _) >= phase) n++;
            return n;
        }

        void Update()
        {
            if (!open) return;
            if (Input.GetKeyDown(KeyCode.Escape) && !MapCamera.Typing) { Close(); return; }
            if (!IconicInterior.Active) { Close(); return; }
            t += Time.unscaledDeltaTime;
            // the aerial shot is taken once the interior has settled on the working floor (cut and camera transition done)
            if (!shot && t > 1.4f && body != null && body.layout.width > 10f) { Shoot(); shot = true; }
            Feed();
        }

        // ------------------------------------------------------------------ cameras of the twin: the drone (one survey frame) and the site camera (live)
        void Shoot()
        {
            var main = Camera.main; var ls = LandmarkSystem.Instance; var m = ls != null ? ls.ModelOf("iconic") : null;
            if (main == null || m == null) return;
            var c = IconicFloors.Centre(work, out float size);
            deck = m.TransformPoint(c + Vector3.up * 1.2f);
            float w = Mathf.Max(body.layout.width, 64f), h = Mathf.Max(body.layout.height, 64f);
            int W = Mathf.Min(1600, Mathf.RoundToInt(w)), Hh = Mathf.Max(64, Mathf.RoundToInt(W * h / w));
            if (droneRT == null || droneRT.width != W || droneRT.height != Hh)
            {
                if (droneRT != null) droneRT.Release();
                droneRT = new RenderTexture(W, Hh, 24) { name = "iconic_drone", antiAliasing = 4 }; droneRT.Create();
            }
            if (drone == null) { var g = new GameObject("Iconic monitoring · drone"); g.transform.SetParent(transform, false); drone = g.AddComponent<Camera>(); drone.enabled = false; }
            drone.CopyFrom(main); drone.ResetProjectionMatrix(); drone.enabled = false; drone.targetTexture = droneRT;
            drone.fieldOfView = 38f; drone.nearClipPlane = 0.5f; drone.farClipPlane = 30000f;
            camYaw0 = main.transform.eulerAngles.y + 25f;
            var rot = Quaternion.Euler(54f, camYaw0, 0f);
            drone.transform.SetPositionAndRotation(deck - rot * Vector3.forward * (size * 2.3f + 40f), rot);
            try { drone.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] monitoring drone: " + e.Message); }
            photo.image = droneRT;
            // the label of the zone over the deck, where the drone saw it
            var vp = drone.WorldToViewportPoint(deck);
            if (vp.z > 0f) { pin.style.left = Length.Percent(vp.x * 100f); pin.style.top = Length.Percent((1f - vp.y) * 100f); pin.style.display = DisplayStyle.Flex; }
            hud.text = hud.text.Replace("{alt}", Loc.N0(drone.transform.position.y - CityGround.HeightAt(drone.transform.position.x, drone.transform.position.z)));
            // the site camera: on the climbing formwork of the core, looking across the deck being cast
            siteEye = m.TransformPoint(new Vector3(IconicShape.Xr - 4f, IconicShape.FloorY(work) + 9f, IconicShape.Cz + IconicShape.Depth(IconicShape.FloorY(work)) * 0.42f));
        }
        void Feed()
        {
            if (feedImg == null || !shot) return;
            nextCam -= Time.unscaledDeltaTime; phase += Time.unscaledDeltaTime;
            if (feedClock != null) feedClock.text = Date() + "  " + DateTime.Now.ToString("HH:mm:ss");
            feedOver?.MarkDirtyRepaint();
            if (nextCam > 0f) return; nextCam = 0.15f;                    // ≈ 7 frames a second: light on a slow computer
            var main = Camera.main; if (main == null) return;
            if (siteRT == null) { siteRT = new RenderTexture(480, 270, 24) { name = "iconic_cctv", antiAliasing = 2 }; siteRT.Create(); }
            if (site == null) { var g = new GameObject("Iconic monitoring · site camera"); g.transform.SetParent(transform, false); site = g.AddComponent<Camera>(); site.enabled = false; }
            site.CopyFrom(main); site.ResetProjectionMatrix(); site.enabled = false; site.targetTexture = siteRT; site.fieldOfView = 58f; site.nearClipPlane = 0.2f; site.farClipPlane = 20000f;
            var look = deck - siteEye; float yaw = Mathf.Atan2(look.x, look.z) * Mathf.Rad2Deg + Mathf.Sin(Time.unscaledTime * 0.16f) * 22f;
            float pitch = Mathf.Atan2(-look.y, new Vector2(look.x, look.z).magnitude) * Mathf.Rad2Deg;
            site.transform.SetPositionAndRotation(siteEye, Quaternion.Euler(pitch, yaw, 0f));
            try { site.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] monitoring camera: " + e.Message); feedImg = null; return; }
            if (feedImg.image != siteRT) feedImg.image = siteRT;
        }

        // ------------------------------------------------------------------ the window
        string dateStr;
        string Date() => dateStr;
        void Build(Landmark l, float p)
        {
            var ui = TwinUI.Instance; var mid = ui != null ? ui.Middle : null; if (mid == null || mid.panel == null) return;
            float yearF = IconicFloors.YearAt(l, p) + 0.2f;      // the survey of mid-March
            var date = new DateTime(Mathf.FloorToInt(yearF), 1, 1).AddDays((yearF - Mathf.Floor(yearF)) * 365f);
            dateStr = date.ToString("dd.MM.yyyy", Loc.Ru);
            float pp = Mathf.Min(p + PlanLead, 0.998f);
            int frames = Count(l, p, IconicFloors.PFacade), framesPlan = Count(l, pp, IconicFloors.PFacade);
            int facade = Count(l, p, IconicFloors.PServices), facadePlan = Count(l, pp, IconicFloors.PServices);
            int services = Count(l, p, IconicFloors.PPartitions), servicesPlan = Count(l, pp, IconicFloors.PPartitions);
            int parts = Count(l, p, IconicFloors.PFinishes), partsPlan = Count(l, pp, IconicFloors.PFinishes);
            int core = Mathf.Min(56, framesPlan + 1), corePlan = Mathf.Min(56, framesPlan + 2);
            int lag = framesPlan - frames;
            // pace of the frame: days per floor since the frame started, actual vs plan
            float y0 = IconicFloors.YearAt(l, 0.08f), daysNow = (IconicFloors.YearAt(l, p) - y0) * 365f;
            float pace = daysNow / Mathf.Max(frames, 1), pacePlan = daysNow / Mathf.Max(framesPlan, 1);       // the same days: the plan had more floors done
            float catchUp = IconicFloors.YearAt(l, Mathf.Min(p + PlanLead * 2.6f, 0.95f));

            overlay = new VisualElement(); overlay.AddToClassList("mon-dim");
            overlay.RegisterCallback<PointerDownEvent>(e => { if (e.target == overlay) Close(); });
            ui.BlockWhileHovered(overlay);
            var win = new VisualElement(); win.AddToClassList("mon-win"); overlay.Add(win);

            // header: place and date, the module, close
            var head = new VisualElement(); head.AddToClassList("mon-head"); win.Add(head);
            var logo = new VisualElement { pickingMode = PickingMode.Ignore }; logo.AddToClassList("mon-logo"); head.Add(logo);
            var place = new VisualElement { pickingMode = PickingMode.Ignore }; place.AddToClassList("mon-place"); head.Add(place);
            place.Add(new Label("Iconic Complex, Alatau City") { pickingMode = PickingMode.Ignore });
            var dl = new Label(date.ToString("ddd, d MMMM", Loc.Ru) + " • 11:20") { pickingMode = PickingMode.Ignore }; dl.AddToClassList("note"); place.Add(dl);
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; head.Add(sp);
            var pill = new VisualElement { pickingMode = PickingMode.Ignore }; pill.AddToClassList("mon-pill"); pill.Add(TwinUI.Icon("hard_hat", 14)); pill.Add(new Label("Мониторинг строительства") { pickingMode = PickingMode.Ignore }); head.Add(pill);
            var sp2 = new VisualElement { pickingMode = PickingMode.Ignore }; sp2.style.flexGrow = 1; head.Add(sp2);
            head.Add(Widgets.Btn("×", Close, "small", "ghost"));

            // body: the survey photo with the panels over it
            body = new VisualElement(); body.AddToClassList("mon-body"); win.Add(body);
            photo = new Image { scaleMode = ScaleMode.StretchToFill, pickingMode = PickingMode.Ignore }; photo.AddToClassList("mon-photo"); body.Add(photo);
            var shade = new VisualElement { pickingMode = PickingMode.Ignore }; shade.AddToClassList("mon-shade"); body.Add(shade);
            pin = new VisualElement { pickingMode = PickingMode.Ignore }; pin.AddToClassList("mon-pin"); pin.style.display = DisplayStyle.None;
            var pl = new Label($"Перекрытие {work + 1} этажа · армирование и опалубка") { pickingMode = PickingMode.Ignore }; pin.Add(pl);
            var stem = new VisualElement { pickingMode = PickingMode.Ignore }; stem.AddToClassList("mon-stem"); pin.Add(stem);
            body.Add(pin);
            var zone = new VisualElement { pickingMode = PickingMode.Ignore }; zone.AddToClassList("mon-zone"); zone.Add(new Label("Башня T1 · монолитный каркас") { pickingMode = PickingMode.Ignore }); body.Add(zone);
            hud = new Label($"ОБЛЁТ {dateStr} · АЭРОФОТОПЛАН · ВЫСОТА {{alt}} М · ДЕТАЛИЗАЦИЯ 2,1 СМ/ПИКС") { pickingMode = PickingMode.Ignore }; hud.AddToClassList("mon-hud"); body.Add(hud);

            // ---- left: the zone card and its progress
            var left = new VisualElement(); left.AddToClassList("mon-col"); left.AddToClassList("mon-left"); body.Add(left);
            var c1 = Card(left);
            var t1 = new VisualElement(); t1.AddToClassList("mon-row"); t1.Add(TwinUI.Icon("layout_grid", 16)); var tt = new Label("Башня T1 · каркас"); tt.AddToClassList("mon-title"); t1.Add(tt); c1.Add(t1);
            var ds = new Label("Описание:"); ds.AddToClassList("mon-accent"); c1.Add(ds);
            c1.Add(Para($"Монолитный каркас: ядро, колонны и перекрытия {Mathf.Max(1, frames - 3)}–{work + 1} этажей. Бетон В40, захватка — один этаж."));
            var bb = new VisualElement(); bb.AddToClassList("mon-btns"); bb.Add(Widgets.Btn("Облако точек", null, "small")); bb.Add(Widgets.Btn("Инфо", null, "small")); c1.Add(bb);

            var c2 = Card(left);
            var h2 = new VisualElement(); h2.AddToClassList("mon-row"); h2.Add(TwinUI.Icon("chart_line", 16)); var t2 = new Label("Прогресс зоны"); t2.AddToClassList("mon-title"); h2.Add(t2);
            var sp3 = new VisualElement(); sp3.style.flexGrow = 1; h2.Add(sp3); h2.Add(Widgets.Status(lag > 0 ? "Отставание" : "В графике", lag > 0 ? "bad" : "ok")); c2.Add(h2);
            var big = new Label("Монолитный каркас башни"); big.AddToClassList("mon-big"); c2.Add(big);
            var sub = new Label("4.2 · Перекрытия и колонны"); sub.AddToClassList("note"); c2.Add(sub);
            int pf = Mathf.RoundToInt(frames * 100f / 56f), ppl = Mathf.RoundToInt(framesPlan * 100f / 56f);
            var kp = new VisualElement(); kp.AddToClassList("mon-kpi"); c2.Add(kp);
            var kf = new VisualElement(); kf.Add(new Label("Факт на " + dateStr) { pickingMode = PickingMode.Ignore }); var vf = new Label(pf + "%"); vf.AddToClassList("mon-num"); kf.Add(vf); kp.Add(kf);
            var sp4 = new VisualElement(); sp4.style.flexGrow = 1; kp.Add(sp4);
            var kpl = new VisualElement(); kpl.style.alignItems = Align.FlexEnd; kpl.Add(new Label("План") { pickingMode = PickingMode.Ignore }); var vp = new Label(ppl + "%"); vp.AddToClassList("mon-num-s"); kpl.Add(vp); kp.Add(kpl);
            var bar = new VisualElement(); bar.AddToClassList("mon-bar"); var fill = new VisualElement(); fill.AddToClassList("mon-fill"); fill.style.width = Length.Percent(pf); bar.Add(fill);
            var mark = new VisualElement(); mark.AddToClassList("mon-mark"); mark.style.left = Length.Percent(ppl); bar.Add(mark); c2.Add(bar);
            c2.Add(Chart(l, p, pp));
            var foot = new VisualElement(); foot.AddToClassList("mon-row"); foot.style.marginTop = 6; foot.Add(TwinUI.Icon("triangle_alert", 14));
            var fl = new Label(lag > 0 ? $"Каркас отстаёт на {lag} {Floors(lag)} (≈ {Mathf.RoundToInt(lag * pacePlan)} дн.)" : "Исполнение соответствует плану"); fl.AddToClassList("note"); foot.Add(fl); c2.Add(foot);

            // ---- right: plan and fact of the works, the site camera
            var right = new VisualElement(); right.AddToClassList("mon-col"); right.AddToClassList("mon-right"); body.Add(right);
            var c3 = Card(right);
            var e3 = new Label($"ОБЛЁТ {dateStr} · ПЛАН И ФАКТ"); e3.AddToClassList("lm-cap-h"); c3.Add(e3);
            var t3 = new Label("Башня Iconic Complex (T1)"); t3.AddToClassList("mon-big"); c3.Add(t3);
            var id3 = new Label("ACI-T1 · монолит · захватка " + (work + 1)); id3.AddToClassList("note"); c3.Add(id3);
            var st3 = new VisualElement(); st3.AddToClassList("mon-row"); st3.style.marginTop = 6; st3.Add(Widgets.Status(lag > 0 ? $"Отстаёт на {lag} {Floors(lag)}" : "В графике", lag > 0 ? "bad" : "ok")); c3.Add(st3);
            c3.Add(Para($"Перекрытие {frames}-го этажа забетонировано, на {work + 1}-м идут армирование и опалубка; ядро опережает на этаж. По графику к {dateStr} должен быть готов {framesPlan}-й этаж."));
            var tb = new VisualElement(); tb.AddToClassList("mon-table"); c3.Add(tb);
            var th = new VisualElement(); th.AddToClassList("mon-tr"); th.AddToClassList("mon-th"); tb.Add(th);
            foreach (var (s, cls) in new[] { ("Работа по графику", "w"), ("План", "n"), ("Факт", "n"), ("Разница", "d") }) th.Add(Cell(s, cls));
            Row(tb, "4.1 Ядро: самоподъёмная опалубка", corePlan, core, "снимок " + dateStr);
            Row(tb, "4.2 Перекрытия и колонны", framesPlan, frames, "снимок " + dateStr + " · датчики прочности бетона");
            Row(tb, "5.1 Фасад: модульный витраж", facadePlan, facade, "отметка прораба · " + dateStr);
            Row(tb, "6.1 Инженерные сети", servicesPlan, services, "отметка прораба");
            Row(tb, "6.2 Перегородки", partsPlan, parts, "нет снимка — по графику");
            var pr = new VisualElement(); pr.AddToClassList("mon-forecast"); c3.Add(pr);
            var pt = new Label("прогноз") { pickingMode = PickingMode.Ignore }; pt.AddToClassList("mon-tag"); pr.Add(pt);
            pr.Add(Para($"Темп каркаса — {Loc.N1(pace)} дн. на этаж при плановых {Loc.N1(pacePlan)}. Вторая смена на армировании закроет отставание к {IconicFloors.MonthYear(catchUp)}."));

            var c4 = Card(right);
            var h4 = new VisualElement(); h4.AddToClassList("mon-row"); h4.Add(TwinUI.Icon("video", 16)); var t4 = new Label("Видеонаблюдение · CAM-07"); t4.AddToClassList("mon-title"); h4.Add(t4); c4.Add(h4);
            var n4 = new Label($"кран № 2 · вид на перекрытие {work + 1} этажа"); n4.AddToClassList("note"); c4.Add(n4);
            var feed = new VisualElement(); feed.AddToClassList("mon-feed"); c4.Add(feed);
            feedImg = new Image { scaleMode = ScaleMode.ScaleAndCrop, pickingMode = PickingMode.Ignore }; feedImg.AddToClassList("mon-feed-img"); feed.Add(feedImg);
            feedOver = new VisualElement { pickingMode = PickingMode.Ignore }; feedOver.AddToClassList("mon-feed-over"); feedOver.generateVisualContent += DrawFeed; feed.Add(feedOver);
            var ftop = new VisualElement { pickingMode = PickingMode.Ignore }; ftop.AddToClassList("mon-feed-top"); feedOver.Add(ftop);
            var fid = new Label("   CAM-07 · REC") { pickingMode = PickingMode.Ignore }; ftop.Add(fid);
            var fsp = new VisualElement { pickingMode = PickingMode.Ignore }; fsp.style.flexGrow = 1; ftop.Add(fsp);
            feedClock = new Label { pickingMode = PickingMode.Ignore }; ftop.Add(feedClock);
            var ai = new VisualElement(); ai.AddToClassList("mon-row"); ai.AddToClassList("mon-ai"); ai.style.marginTop = 8; ai.Add(Widgets.Dot(new Color(0.20f, 0.78f, 0.35f), true));
            var ail = new Label("ИИ-видеоаналитика: 12 человек в зоне · все в касках и жилетах"); ail.AddToClassList("note"); ail.style.whiteSpace = WhiteSpace.Normal; ai.Add(ail); c4.Add(ai);
            var ai2 = new VisualElement(); ai2.AddToClassList("mon-row"); ai2.AddToClassList("mon-ai"); ai2.style.marginTop = 4; ai2.Add(Widgets.Dot(new Color(0.96f, 0.65f, 0.14f), true));
            var ail2 = new Label("09:42 — работа у края плиты без страховки, прораб уведомлён · закрыто"); ail2.AddToClassList("note"); ail2.style.whiteSpace = WhiteSpace.Normal; ai2.Add(ail2); c4.Add(ai2);

            // tools at the bottom, as on the platform (measure, layers, compare, cameras …)
            var tools = new VisualElement(); tools.AddToClassList("mon-tools"); body.Add(tools);
            foreach (var ic in new[] { "locate_fixed", "layers", "box", "scan_eye", "video", "radar", "compass", "rotate_ccw" })
            { var b = new VisualElement { pickingMode = PickingMode.Ignore }; b.AddToClassList("mon-tool"); if (ic == "scan_eye") b.AddToClassList("on"); b.Add(TwinUI.Icon(ic, 16)); tools.Add(b); }

            (mid.parent ?? mid).Add(overlay);                 // the root of the interface: it carries the style sheet, the window covers the header too
        }
        static string Floors(int n) { int m = n % 100, d = n % 10; return m >= 11 && m <= 14 ? "этажей" : d == 1 ? "этаж" : d >= 2 && d <= 4 ? "этажа" : "этажей"; }
        static VisualElement Card(VisualElement parent) { var c = new VisualElement(); c.AddToClassList("mon-card"); parent.Add(c); return c; }
        static Label Para(string s) { var l = new Label(s) { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-para"); return l; }
        static Label Cell(string s, string cls) { var l = new Label(s) { pickingMode = PickingMode.Ignore }; l.AddToClassList("mon-td"); l.AddToClassList(cls); return l; }
        static void Row(VisualElement tb, string work, int plan, int fact, string src)
        {
            int d = fact - plan; string cls = d >= 0 ? "ok" : d >= -1 ? "warn" : "bad";
            var r = new VisualElement(); r.AddToClassList("mon-tr"); r.AddToClassList(cls); tb.Add(r);
            var w = new VisualElement(); w.AddToClassList("w"); w.AddToClassList("mon-td"); r.Add(w);
            var wl = new Label(work) { pickingMode = PickingMode.Ignore }; wl.AddToClassList("mon-work"); w.Add(wl);
            var sl = new Label(src) { pickingMode = PickingMode.Ignore }; sl.AddToClassList("mon-src"); w.Add(sl);
            r.Add(Cell(plan + " эт.", "n")); r.Add(Cell(fact + " эт.", "n"));
            var dl = Cell(d >= 0 ? "в срок" : d + " эт.", "d"); dl.AddToClassList(cls); r.Add(dl);
        }

        /// <summary>Floors of the frame finished month by month: plan (dashed) and actual (solid) up to the survey date.</summary>
        VisualElement Chart(Landmark l, float p, float pp)
        {
            var box = new VisualElement(); box.AddToClassList("mon-chart");
            var ls = new List<Vector2>(); var lp = new List<Vector2>();
            float p0 = 0.06f; int n = 16;
            for (int i = 0; i <= n; i++) { float q = Mathf.Lerp(p0, p, i / (float)n); ls.Add(new Vector2(i / (float)n, Count(l, q, IconicFloors.PFacade) / 56f)); lp.Add(new Vector2(i / (float)n, Count(l, Mathf.Min(q + (pp - p), 0.998f), IconicFloors.PFacade) / 56f)); }
            box.generateVisualContent += ctx =>
            {
                var r = box.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
                float L = 30f, B = 18f, W = r.width - L - 6f, Hh = r.height - B - 6f;
                Vector2 P(Vector2 v) => new Vector2(L + v.x * W, 6f + (1f - v.y) * Hh);
                g.lineWidth = 1f; g.strokeColor = new Color(1f, 1f, 1f, 0.08f);
                for (int k = 0; k <= 2; k++) { float y = 6f + Hh * k / 2f; g.BeginPath(); g.MoveTo(new Vector2(L, y)); g.LineTo(new Vector2(L + W, y)); g.Stroke(); }
                // plan: dashes
                g.strokeColor = new Color(0.8f, 0.8f, 0.8f, 0.85f); g.lineWidth = 1.4f;
                for (int i = 0; i < lp.Count - 1; i++)
                {
                    var a = P(lp[i]); var b = P(lp[i + 1]); float len = (b - a).magnitude; int dn = Mathf.Max(1, Mathf.RoundToInt(len / 6f));
                    for (int d = 0; d < dn; d += 2) { g.BeginPath(); g.MoveTo(Vector2.Lerp(a, b, d / (float)dn)); g.LineTo(Vector2.Lerp(a, b, Mathf.Min(1f, (d + 1f) / dn))); g.Stroke(); }
                }
                // actual: solid blue, a dot at the survey
                g.strokeColor = new Color(0.36f, 0.55f, 0.94f); g.lineWidth = 2f; g.BeginPath(); g.MoveTo(P(ls[0])); for (int i = 1; i < ls.Count; i++) g.LineTo(P(ls[i])); g.Stroke();
                g.fillColor = new Color(0.36f, 0.55f, 0.94f); g.BeginPath(); g.Arc(P(ls[ls.Count - 1]), 3.5f, 0f, 360f); g.Fill();
            };
            foreach (var (txt, y) in new[] { ("100%", 0f), ("50%", 0.5f), ("0%", 1f) })
            { var a = new Label(txt) { pickingMode = PickingMode.Ignore }; a.AddToClassList("mon-axis"); a.style.top = Length.Percent(y * 78f); a.style.left = 0; box.Add(a); }
            var x0 = new Label(IconicFloors.MonthYear(IconicFloors.YearAt(l, p0))) { pickingMode = PickingMode.Ignore }; x0.AddToClassList("mon-axis"); x0.style.bottom = 0; x0.style.left = 28; box.Add(x0);
            var x1 = new Label(dateStr) { pickingMode = PickingMode.Ignore }; x1.AddToClassList("mon-axis"); x1.style.bottom = 0; x1.style.right = 4; box.Add(x1);
            var wrap = new VisualElement(); wrap.Add(box);
            var leg = new VisualElement(); leg.AddToClassList("mon-legend"); leg.Add(new Label("- - План") { pickingMode = PickingMode.Ignore }); var lf = new Label("— Факт") { pickingMode = PickingMode.Ignore }; lf.style.color = new Color(0.36f, 0.55f, 0.94f); leg.Add(lf); wrap.Add(leg);
            return wrap;
        }

        /// <summary>Over the site camera: scan lines, the blinking REC dot, video-analytics boxes on the crew (green = helmet and vest).</summary>
        void DrawFeed(MeshGenerationContext ctx)
        {
            var r = feedOver.contentRect; if (r.width < 20f) return; var g = ctx.painter2D;
            g.lineWidth = 1f; g.strokeColor = new Color(1f, 1f, 1f, 0.035f);
            for (float y = 0; y < r.height; y += 3f) { g.BeginPath(); g.MoveTo(new Vector2(0, y)); g.LineTo(new Vector2(r.width, y)); g.Stroke(); }
            if (Mathf.Repeat(phase, 1.2f) < 0.7f) { g.fillColor = new Color(1f, 0.23f, 0.18f); g.BeginPath(); g.Arc(new Vector2(12f, 13f), 4f, 0f, 360f); g.Fill(); }
            var rnd = new System.Random(7);
            for (int i = 0; i < 3; i++)
            {
                float bx = 0.15f + (float)rnd.NextDouble() * 0.65f, by = 0.45f + (float)rnd.NextDouble() * 0.3f, bw = 0.05f + (float)rnd.NextDouble() * 0.03f;
                float dx = Mathf.Sin(phase * 0.3f + i * 1.9f) * 0.03f;
                var q = new Rect((bx + dx) * r.width, by * r.height, bw * r.width, bw * r.width * 1.8f);
                g.strokeColor = new Color(0.35f, 0.95f, 0.55f, 0.9f); g.lineWidth = 1.5f;
                g.BeginPath(); g.MoveTo(q.min); g.LineTo(new Vector2(q.xMax, q.yMin)); g.LineTo(q.max); g.LineTo(new Vector2(q.xMin, q.yMax)); g.ClosePath(); g.Stroke();
            }
        }
    }
}
