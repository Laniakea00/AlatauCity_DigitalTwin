using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>"Smart City": the city's CCTV cameras on the map (by purpose, online / no signal), the live view of the chosen camera
    /// (a stub rendered from the twin), the stream of notifications and the requests of residents to iKomek 109 by topic.
    /// All feeds are demo stubs with the same structure as the real APIs (Smart City Alatau, iKomek 109, 112).</summary>
    public class SmartCityModule : TwinModuleBase
    {
        public override string Id => "smartcity";
        public override string TabKey => "tab_smart";
        public static SmartCityModule Instance;
        public SmartCityModule() { Instance = this; }

        static int sel = -1; static readonly bool[] typeOn = { true, true, true, true };
        Label eyebrow, summary, camTitle; readonly Label[] kv = new Label[4], kl = new Label[4]; readonly VisualElement[] kb = new VisualElement[4];
        VisualElement typeRows, reqRows, feedList, camFacts; CameraFeed feed;
        static VisualElement tourBox; static CameraFeed tourFeed; static Label tourCap;

        public override (Color, string)[] Legend => new[]
        {
            (SmartCity.CamTypeColor[0], SmartCity.CamTypeShort[0]), (SmartCity.CamTypeColor[1], SmartCity.CamTypeShort[1]),
            (SmartCity.CamTypeColor[2], SmartCity.CamTypeShort[2]), (SmartCity.CamTypeColor[3], SmartCity.CamTypeShort[3]),
            (new Color(0.45f, 0.45f, 0.45f), "нет сигнала")
        };

        public override void OnEnter() { Notifier.OnChanged -= FeedChanged; Notifier.OnChanged += FeedChanged; Pins(); }
        public override void OnExit() { Notifier.OnChanged -= FeedChanged; MapPins.Instance?.Clear(); TourHide(); }
        void FeedChanged() { if (feedList != null && feedList.panel != null) FillFeed(); }

        static List<SmartCity.Cctv> Cams => SmartCity.Cameras(TwinState.Year);

        // ------------------------------------------------------------------ map
        static void Pins()
        {
            var mp = MapPins.Instance; if (mp == null) return;
            var cams = Cams; var pins = new List<MapPins.Pin>();
            for (int i = 0; i < cams.Count; i++)
            {
                var c = cams[i]; if (!typeOn[(int)c.Type]) continue;
                if (TwinTour.Running && TwinTour.Zone >= 0 && c.District != TwinTour.Zone) continue;
                int ii = i;
                pins.Add(new MapPins.Pin { Id = "cam" + i, Label = c.Id + " · " + SmartCity.CamTypeShort[(int)c.Type], World = c.World, Fill = c.Online ? SmartCity.CamTypeColor[(int)c.Type] : new Color(0.45f, 0.45f, 0.45f), Status = c.Online ? "" : "planned", Size = i == sel ? 15f : 11f, OnClick = () => Focus(ii) });
            }
            mp.Set(pins); if (sel >= 0) mp.Select("cam" + sel);
        }

        /// <summary>Selects a camera: its pin, its view in the feed window, the camera flies to it.</summary>
        public static void Focus(int i, bool fly = true)
        {
            var cams = Cams; if (i < 0 || i >= cams.Count) return;
            sel = i; var c = cams[i];
            if (fly) FlyTo(c.World);
            MapPins.Instance?.Select("cam" + i);
            Instance?.ShowCam(); tourFeed?.Show(c); if (tourCap != null) tourCap.text = c.Place + " · " + SmartCity.CamTypeName[(int)c.Type];
        }
        public static void FlyTo(Vector3 w)
        {
            var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null; if (cam == null) return;
            cam.FlyTo(new MapCamera.View { name = "cctv", target = new Vector3(w.x, CityGround.HeightAt(w.x, w.z), w.z), distance = 1500f, yaw = cam.yaw, pitch = 44f });
        }

        // ------------------------------------------------------------------ panel
        protected override void Build()
        {
            var top = Widgets.Block(panel);
            eyebrow = Widgets.Eyebrow(top, "");
            summary = new Label(); summary.AddToClassList("summary"); summary.style.marginBottom = 10; top.Add(summary);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid); VisualElement row = null;
            for (int i = 0; i < 4; i++)
            {
                if (i % 2 == 0) { row = new VisualElement(); row.AddToClassList("kpi-row"); grid.Add(row); }
                var k = new VisualElement(); k.AddToClassList("kpi");
                kl[i] = new Label(); kl[i].AddToClassList("l"); k.Add(kl[i]); kv[i] = new Label("—"); kv[i].AddToClassList("v"); k.Add(kv[i]);
                kb[i] = k; row.Add(k);
            }
            top.Add(SourceTags.Line(Data.TwinModels.SmartCity));

            var tb = Widgets.Block(panel, "Камеры по назначению", "клик — фильтр");
            typeRows = new VisualElement(); tb.Add(typeRows);

            var rb = Widgets.Block(panel, "Обращения iKomek 109", "темы за сутки");
            reqRows = new VisualElement(); rb.Add(reqRows); rb.Add(SourceTags.Line(Data.TwinModels.SmartCity));

            var n = Widgets.Block(panel);
            var note = new Label("Демо-данные: видео — вид из цифрового двойника с места камеры, события и обращения смоделированы QTwin. Интерфейс готов к подключению Smart City Alatau, iKomek 109 и 112 — живые потоки встанут на место модели без переделки экранов.");
            note.AddToClassList("note"); n.Add(note);

            Right();
            var fb = Widgets.Block(panel, "Камера · прямой эфир", "демо-поток");
            camTitle = fb.Q<Label>(className: "block-title");
            feed = new CameraFeed(); fb.Add(feed);
            camFacts = new VisualElement(); camFacts.style.marginTop = 8; fb.Add(camFacts);
            var br = new VisualElement(); br.AddToClassList("lm-btns"); fb.Add(br);
            br.Add(Widgets.Btn("← Предыдущая", () => Step(-1), "small", "ghost"));
            br.Add(Widgets.Btn("Следующая →", () => Step(1), "small", "ghost"));
            br.Add(Widgets.Btn("На карте", () => { var cs = Cams; if (sel >= 0 && sel < cs.Count) FlyTo(cs[sel].World); }, "small"));

            var eb = Widgets.Block(panel, "Лента событий", "за сутки");
            feedList = new VisualElement(); eb.Add(feedList); eb.Add(SourceTags.Line(Data.TwinModels.SmartCity, Data.TwinModels.Ops));

            var ib = Widgets.Block(panel, "Интеграции", "");
            ib.Add(Widgets.Fact("Smart City Alatau", "видеопотоки RTSP · демо-поток"));
            ib.Add(Widgets.Fact("iKomek 109", "обращения жителей · модель QTwin"));
            ib.Add(Widgets.Fact("ЕДДС 112", "вызовы и инциденты · модель QTwin"));
            var last = Widgets.Fact("Статус", "готово к подключению по API"); last.style.borderBottomWidth = 0; ib.Add(last);
            Widgets.SetCollapsed(ib, true);
        }

        void Step(int d)
        {
            var cs = Cams; if (cs.Count == 0) return;
            int i = sel < 0 ? 0 : (sel + d + cs.Count) % cs.Count;
            for (int k = 0; k < cs.Count && !typeOn[(int)cs[i].Type]; k++) i = (i + d + cs.Count) % cs.Count;
            Focus(i);
        }

        public override void Refresh()
        {
            if (panel == null || summary == null || !CityStats.Ready) return;
            int y = TwinState.Year; var cs = Cams;
            int total = SmartCity.CameraCount(y), ev = SmartCity.EventsPerDay(y), req = SmartCity.RequestsPerDay(y);
            float on = SmartCity.OnlineShare(y), solved = SmartCity.SolvedInTime(y);
            eyebrow.text = ("Smart City · " + y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            summary.text = $"В {y} году в городе {Loc.N0(total)} камер, на связи {Mathf.RoundToInt(on * 100)} %. Видеоаналитика даёт ≈ {Loc.N0(ev)} событий в сутки, жители подают ≈ {Loc.N0(req)} обращений в iKomek 109; {Mathf.RoundToInt(solved * 100)} % решаются в срок, реакция — {SmartCity.ReactionMin(y)} мин.";
            Set(0, Loc.N0(total), "камер в сети", ""); Set(1, Mathf.RoundToInt(on * 100) + " %", "на связи", on < 0.95f ? "warn" : "ok");
            Set(2, Loc.N0(req), "обращений iKomek 109 в сутки", ""); Set(3, Mathf.RoundToInt(solved * 100) + " %", "решено в срок", solved < 0.85f ? "warn" : "ok");

            float[] share = { 0.46f, 0.30f, 0.09f, 0.15f };
            typeRows.Clear();
            for (int t = 0; t < 4; t++)
            {
                int tt = t; var r = new VisualElement(); r.AddToClassList("status-row"); r.AddToClassList("clickable"); r.style.opacity = typeOn[t] ? 1f : 0.4f;
                var dot = Widgets.Dot(SmartCity.CamTypeColor[t], true); dot.style.flexShrink = 0; dot.style.marginRight = 8; r.Add(dot);
                var nm = new Label(SmartCity.CamTypeName[t]) { pickingMode = PickingMode.Ignore }; nm.AddToClassList("n");
                nm.style.flexShrink = 1; nm.style.minWidth = 0; nm.style.marginRight = 12; nm.style.whiteSpace = WhiteSpace.Normal; r.Add(nm);
                var st = new Label(Loc.N0(total * share[t]) + " · на карте " + cs.Count(c => (int)c.Type == t)) { pickingMode = PickingMode.Ignore }; st.AddToClassList("s"); st.style.flexShrink = 0; r.Add(st);
                r.AddManipulator(new Clickable(() => { typeOn[tt] = !typeOn[tt]; Pins(); Refresh(); }));
                typeRows.Add(r);
            }

            reqRows.Clear();
            foreach (var (nmR, sh) in SmartCity.RequestTypes)
            {
                var r = new VisualElement(); r.AddToClassList("story-row");
                var rt = new VisualElement(); rt.AddToClassList("story-rtop"); r.Add(rt);
                var chip = new VisualElement(); chip.AddToClassList("story-chip"); chip.style.backgroundColor = new Color(0.80f, 0.60f, 1f); rt.Add(chip);
                var l = new Label(nmR); l.AddToClassList("story-rn"); rt.Add(l);
                var v = new Label(Loc.N0(req * sh)); v.AddToClassList("story-rv"); rt.Add(v);
                var bar = new VisualElement(); bar.AddToClassList("story-bar"); var fill = new VisualElement(); fill.AddToClassList("story-fill"); fill.style.backgroundColor = new Color(0.80f, 0.60f, 1f); fill.style.width = Length.Percent(sh / 0.22f * 100f); bar.Add(fill); r.Add(bar);
                reqRows.Add(r);
            }

            if (sel < 0 || sel >= cs.Count) sel = cs.FindIndex(c => c.Online && c.Type == SmartCity.CamType.Traffic);
            ShowCam(); FillFeed(); Pins();
            TwinUI.Instance?.FillLegend(Legend);
        }

        void ShowCam()
        {
            if (feed == null || camFacts == null) return;
            var cs = Cams; camFacts.Clear();
            if (sel < 0 || sel >= cs.Count) { var l = new Label("В этом году камер ещё нет: город только начинает строиться."); l.AddToClassList("note"); camFacts.Add(l); return; }
            var c = cs[sel]; feed.Show(c);
            if (camTitle != null) camTitle.text = "Камера " + c.Id;
            camFacts.Add(Widgets.Fact("Назначение", SmartCity.CamTypeName[(int)c.Type]));
            camFacts.Add(Widgets.Fact("Место", c.Place + " · " + CityStats.DistrictIds[c.District]));
            camFacts.Add(Widgets.Fact("Видеоаналитика", c.Analytics));
            var st = Widgets.Fact("Статус", ""); st.RemoveAt(1); st.Add(Widgets.Status(c.Online ? "на связи" : "нет сигнала · заявка в сервис", c.Online ? "ok" : "bad")); st.style.borderBottomWidth = 0; camFacts.Add(st);
        }

        void FillFeed()
        {
            feedList.Clear(); var nf = Notifier.Instance;
            var items = nf != null && nf.Feed.Count > 0 ? nf.Feed.Take(6).ToList() : SmartCity.Day(TwinState.Year).Take(6).ToList();
            if (items.Count == 0) { var l = new Label("Событий нет."); l.AddToClassList("note"); feedList.Add(l); return; }
            foreach (var n in items)
            {
                var nn = n;
                feedList.Add(Widgets.JournalCard(n.Icon, n.Source, n.Level, n.Status, n.Title + " — " + n.Text, n.Time, n.HasPlace ? "Показать" : null, n.HasPlace ? () => Notifier.Open(nn) : null));
            }
        }

        void Set(int i, string v, string l, string cls)
        {
            kv[i].text = v; kl[i].text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) kb[i].RemoveFromClassList(c);
            if (cls != "") kb[i].AddToClassList(cls);
        }

        // ------------------------------------------------------------------ presentation: a big camera window over the map
        public static void TourShow(SmartCity.CamType type, int district)
        {
            var ui = TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            TourHide();
            tourBox = new VisualElement { pickingMode = PickingMode.Ignore }; tourBox.AddToClassList("feed-tour");
            var h = new Label("SMART CITY · КАМЕРА В ПРЯМОМ ЭФИРЕ") { pickingMode = PickingMode.Ignore }; h.AddToClassList("story-eye"); tourBox.Add(h);
            tourFeed = new CameraFeed(true); tourBox.Add(tourFeed);
            tourCap = new Label { pickingMode = PickingMode.Ignore }; tourCap.AddToClassList("note"); tourCap.style.marginTop = 6; tourBox.Add(tourCap);
            ui.Scene.Add(tourBox);
            TourCam(type, district);
        }
        /// <summary>Switches the presentation's camera window to a camera of the type in the district.</summary>
        public static void TourCam(SmartCity.CamType type, int district)
        {
            var cs = Cams; int i = cs.FindIndex(c => c.Online && c.Type == type && (district < 0 || c.District == district));
            if (i < 0) i = cs.FindIndex(c => c.Online && c.Type == type);
            if (i < 0) i = cs.FindIndex(c => c.Online);
            if (i >= 0) Focus(i);
        }
        public static SmartCity.Cctv Selected { get { var cs = Cams; return sel >= 0 && sel < cs.Count ? cs[sel] : null; } }
        public static void TourHide() { tourBox?.RemoveFromHierarchy(); tourBox = null; tourFeed = null; tourCap = null; }
    }
}
