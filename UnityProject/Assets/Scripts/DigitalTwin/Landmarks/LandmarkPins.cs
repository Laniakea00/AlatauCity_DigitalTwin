using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Labels over the landmarks (name, district colour, status) on a thin stem, and small LRT station tags.
    /// When they show: in the "Инвестпроекты" tab always (planned ones dimmed); in "Обзор" for the objects that stand in the shown year,
    /// once the timeline is not playing; the selected one always. A click flies to the object and opens its passport.</summary>
    public class LandmarkPins : MonoBehaviour
    {
        public static LandmarkPins Instance;
        class Pin { public Landmark L; public LrtLayer.Station St; public VisualElement El, Box; public Label Name, Stat; public VisualElement Dot, Stem; public int Prio; public float X, Y; public int StIdx = -1; }
        readonly List<Pin> pins = new List<Pin>();
        VisualElement host;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Landmark pins").AddComponent<LandmarkPins>(); }
        void Awake() { Instance = this; }

        void EnsurePins()
        {
            var sys = LandmarkSystem.Instance; var lrt = LrtLayer.Instance;
            if (sys == null || !sys.Ready || sys.Items.Count == 0) return;
            int want = sys.Items.Count - 1 + (lrt != null ? lrt.Stations.Count : 0);
            if (pins.Count == want && host == TwinUI.Instance?.Pins && (pins.Count == 0 || pins[0].El.parent == host)) return;
            foreach (var p in pins) p.El?.RemoveFromHierarchy(); pins.Clear();
            host = TwinUI.Instance != null ? TwinUI.Instance.Pins : null; if (host == null) return;
            foreach (var l in sys.Items) if (!l.IsLrt) pins.Add(Make(l, null));
            if (lrt != null) foreach (var st in lrt.Stations) pins.Add(Make(sys.Get("lrt"), st));
        }

        Pin Make(Landmark l, LrtLayer.Station st)
        {
            var p = new Pin { L = l, St = st };
            var w = new VisualElement(); w.AddToClassList("lm-pin-wrap"); if (st != null) w.AddToClassList("station");
            var box = new VisualElement(); box.AddToClassList("lm-pin");
            var dot = new VisualElement { pickingMode = PickingMode.Ignore }; dot.AddToClassList("lm-dot");
            dot.style.backgroundColor = st != null ? new Color(0.70f, 0.52f, 0.89f) : l.District >= 0 ? CityStats.DistrictColors[l.District] : Color.white;
            box.Add(dot); p.Dot = dot;
            var n = new Label(st != null ? "ЛРТ" : l.Short) { pickingMode = PickingMode.Ignore }; n.AddToClassList("lm-name"); box.Add(n); p.Name = n;
            if (st == null)
            {
                var s = new Label(LandmarkCatalog.StatusOf(l)) { pickingMode = PickingMode.Ignore }; s.AddToClassList("lm-st"); box.Add(s); p.Stat = s;
                // the «Мониторинг стройки» mode: the mark is the way into the object's monitoring
                var mo = new Label("Мониторинг") { pickingMode = PickingMode.Ignore }; mo.AddToClassList("lm-mon"); box.Add(mo);
                if (Modules.MonitoringModule.Watched(l)) w.AddToClassList("has-mon");
            }
            w.Add(box);
            var stem = new VisualElement { pickingMode = PickingMode.Ignore }; stem.AddToClassList("lm-stem"); w.Add(stem); p.Stem = stem;
            var foot = new VisualElement { pickingMode = PickingMode.Ignore }; foot.AddToClassList("lm-foot"); w.Add(foot);
            // clicks are hit-tested here (LateUpdate) against the drawn label, so they never fall through to the buildings below
            host.Add(w); p.El = w; p.Box = box; w.style.display = DisplayStyle.None;
            p.Prio = st != null ? 0 : l.Id == "iconic" ? 100 : l.Status == LStatus.Construction ? 60 : l.Status == LStatus.Preparation ? 70 : 40;
            return p;
        }

        void LateUpdate()
        {
            if (TwinUI.Instance == null) return;
            EnsurePins();
            // the status chip follows the year the map shows (in 2050 a finished plant says «Работает», not «Строится»)
            foreach (var p in pins)
            {
                if (p.Stat == null || p.L == null) continue;
                // the monitoring map shows the city as designed; its marks say where each object stands today
                bool now = Modules.MonitoringModule.On;
                int si = now ? LandmarkCatalog.NowIdx(p.L) : LandmarkCatalog.StatusIdx(p.L); string txt = now ? LandmarkCatalog.StatusText[si] : LandmarkCatalog.StatusLabel(p.L);
                if (si == p.StIdx && txt == p.Stat.text) continue;
                if (p.StIdx >= 0) p.Stat.RemoveFromClassList(LandmarkCatalog.StatusCls[p.StIdx]);
                p.StIdx = si; p.Stat.text = txt; p.Stat.AddToClassList(LandmarkCatalog.StatusCls[si]);
            }
            var cam = Camera.main; var sys = LandmarkSystem.Instance; if (cam == null || sys == null || !sys.Ready || host == null || host.panel == null) return;
            string mod = TwinState.Module; bool objectsTab = mod == "objects", overview = mod == "overview", monitoring = mod == "monitoring";
            var mc = cam.GetComponent<MapCamera>(); float camD = mc != null ? mc.distance : 30000f;
            float y = LandmarkSystem.YearNow;
            bool tour = TwinTour.Running; int zone = TwinTour.Zone;
            foreach (var p in pins)
            {
                bool show; Vector3 wp; bool sel = sys.Selected == p.L && p.St == null;
                if (p.St != null)
                {
                    bool open = LrtLayer.Instance != null && LrtLayer.Instance.StationOpen(p.St);
                    show = tour ? sys.Selected == p.L && camD < 14000f
                         : (objectsTab && camD < 26000f) || (overview && open && camD < 9000f && !TwinState.Playing) || (sys.Selected == p.L && camD < 14000f);
                    wp = p.St.P + Vector3.up * 12f;
                    p.El.EnableInClassList("planned", !open);
                }
                else
                {
                    float pr = LandmarkSystem.Progress(p.L, y);
                    // in the presentation: the labels of the zone being shown (its projects), the rest of the city stays clean
                    show = tour ? sel || (zone >= 0 && p.L.District == zone && (pr > 0f || objectsTab))
                                : sel || objectsTab || (overview && (pr > 0f || p.StIdx == 2) && !TwinState.Playing);   // built, being built or being prepared
                    float vis = pr >= 0.999f || (objectsTab && pr <= 0f) ? 1f : Mathf.Clamp01((pr - 0.08f) / 0.62f);
                    var top = p.L.Anchor != Vector3.zero ? p.L.Anchor : p.L.World + Vector3.up * p.L.Height;
                    wp = new Vector3(top.x, p.L.World.y + (top.y - p.L.World.y) * vis + 10f, top.z);
                    p.El.EnableInClassList("planned", pr <= 0f);
                    p.El.EnableInClassList("hover", sys.Hovered == p.L);
                }
                // monitoring mode: only its six marked objects, nothing else on the map
                if (monitoring) show = p.St == null && Modules.MonitoringModule.OnMap(p.L) && !IconicMonitor.Open;
                p.El.EnableInClassList("mon", monitoring);
                p.El.EnableInClassList("selected", sel);
                if (!show || IconicInterior.Active) { p.El.style.display = DisplayStyle.None; continue; }
                var sp = cam.WorldToScreenPoint(wp);
                if (sp.z < 0) { p.El.style.display = DisplayStyle.None; continue; }
                var pp = RuntimePanelUtils.ScreenToPanel(host.panel, new Vector2(sp.x, Screen.height - sp.y));
                var local = host.WorldToLocal(pp);
                if (local.x < -80 || local.y < -10 || local.x > host.layout.width + 80 || local.y > host.layout.height + 60) { p.El.style.display = DisplayStyle.None; continue; }
                p.El.style.display = DisplayStyle.Flex;
                p.El.style.left = local.x; p.El.style.top = local.y; p.X = local.x; p.Y = local.y;
                // nearer objects sit in front of farther ones
                p.El.userData = sp.z;
            }
            if (sys.Selected != null) foreach (var p in pins) if (p.L == sys.Selected && p.St == null) p.El.BringToFront();
            Declutter(sys);
            PointerInput(sys);
        }

        // labels that would overlap a more important one are hidden (Iconic first, then construction, then the rest; stations last)
        readonly List<Rect> placed = new List<Rect>();
        readonly List<Pin> order = new List<Pin>();
        void Declutter(LandmarkSystem sys)
        {
            order.Clear(); foreach (var p in pins) if (p.El.style.display == DisplayStyle.Flex) order.Add(p);
            order.Sort((a, b) => (b.Prio + (sys.Selected == b.L && b.St == null ? 1000 : 0)).CompareTo(a.Prio + (sys.Selected == a.L && a.St == null ? 1000 : 0)));
            placed.Clear();
            bool mon = TwinState.Module == "monitoring";
            foreach (var p in order)
            {
                if (mon && p.St == null)
                {
                    // the monitoring map never hides one of its six marks: a label that would cover another rises on a longer stem
                    float mw = 50f + p.Name.text.Length * 8.4f + (p.Stat != null ? p.Stat.text.Length * 6.2f : 0f) + (Modules.MonitoringModule.Watched(p.L) ? 86f : 0f);
                    float stem = 60f; Rect mr = default;
                    for (int k = 0; k < 6; k++, stem += 42f)
                    {
                        mr = new Rect(p.X - mw * 0.5f, p.Y - stem - 48f, mw, 40f); bool over = false;
                        foreach (var q in placed) if (q.Overlaps(mr)) { over = true; break; }
                        if (!over) break;
                    }
                    p.Stem.style.height = stem; placed.Add(mr); continue;
                }
                if (p.Stem != null && p.St == null) p.Stem.style.height = StyleKeyword.Null;
                float w = (p.St != null ? 46f : 30f + p.Name.text.Length * 7.2f + (p.St == null ? 90f : 0f)), h = p.St != null ? 20f : 26f;
                float x = p.X - w * 0.5f, y = p.Y - (p.St != null ? 34f : 54f);
                var r = new Rect(x, y, w, h); bool hit = false;
                foreach (var q in placed) if (q.Overlaps(r)) { hit = true; break; }
                if (hit && !(sys.Selected == p.L && p.St == null)) { p.El.style.display = DisplayStyle.None; continue; }
                placed.Add(r);
            }
        }

        Pin hoverPin, downPin; bool blocking;
        void PointerInput(LandmarkSystem sys)
        {
            hoverPin = null;
            var panel = host.panel;
            var mp = RuntimePanelUtils.ScreenToPanel(panel, new Vector2(Input.mousePosition.x, Screen.height - Input.mousePosition.y));
            for (int i = pins.Count - 1; i >= 0; i--)
            {
                var p = pins[i];
                if (p.El.style.display != DisplayStyle.Flex || p.Box == null) continue;
                var wb = p.Box.worldBound; wb.xMin -= 3; wb.xMax += 3; wb.yMin -= 3; wb.yMax += 3;
                if (wb.Contains(mp)) { hoverPin = p; break; }
            }
            foreach (var p in pins) p.El.EnableInClassList("pin-hover", p == hoverPin);
            // while the pointer is on a label the map does not take the press (no drag, no building pick)
            if (hoverPin != null) { MapCamera.BlockInput = true; blocking = true; }
            else if (blocking) { MapCamera.BlockInput = TwinUI.Instance != null && TwinUI.Instance.PointerOverChrome; blocking = false; }
            if (Input.GetMouseButtonDown(0)) downPin = hoverPin;
            if (Input.GetMouseButtonUp(0))
            {
                if (downPin != null && downPin == hoverPin)
                {
                    var p = downPin;
                    if (p.St != null) sys.FlyToPoint(p.L, p.St.P, 700f);
                    else if (TwinState.Module == "monitoring") Modules.MonitoringModule.Open(p.L);
                    else sys.Select(p.L);
                }
                downPin = null;
            }
        }
    }
}
