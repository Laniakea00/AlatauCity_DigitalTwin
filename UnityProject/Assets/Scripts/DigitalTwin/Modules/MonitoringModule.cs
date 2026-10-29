using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>"Мониторинг стройки": the planned city with six marked objects (Iconic Complex, KAIST, K-Park, PepsiCo, Griffin
    /// Logopark, the airport). A click on a mark (or a row of the list) flies close to the object and opens its passport; the objects
    /// with a construction monitoring (Iconic, KAIST) open it from there: drone surveys 2D/3D by dates, BIM 4D, cameras on the site.
    /// Closing either brings the whole map back. The map shows the city as designed, so every object is seen whole, never as a ghost;
    /// statuses are today's.</summary>
    public class MonitoringModule : TwinModuleBase
    {
        public override string Id => "monitoring";
        public override string TabKey => "tab_monitoring";
        public override (Color, string)[] Legend => new (Color, string)[0];
        public static bool On => TwinState.Module == "monitoring";
        /// <summary>The objects with a monitoring (the ones with a TowerProfile).</summary>
        public static readonly string[] Ids = { "iconic", "kaist" };
        /// <summary>The objects marked on the map: the two with a monitoring first, then the ones to look at and read about.</summary>
        public static readonly string[] Pinned = { "iconic", "kaist", "kpark", "pepsico", "griffin", "airport" };
        public static bool Watched(Landmark l) => l != null && !l.IsLrt && TowerProfile.For(l.Id) != null;
        public static bool OnMap(Landmark l) => l != null && System.Array.IndexOf(Pinned, l.Id) >= 0;
        /// <summary>Today (27.10.2026): the statuses and the readiness in the passports of this mode.</summary>
        public const float Today = 2026f + 299f / 365f;
        /// <summary>The year the map shows: the city as designed, every object whole.</summary>
        static int MapYear => TwinState.MaxYear;

        /// <summary>Registers the open climate source and the models of the monitoring before any panel is built.</summary>
        public MonitoringModule() { IconicMonitor.RegisterSources(); }

        static bool wasOpen; static Landmark wasSel;
        readonly List<(Landmark l, VisualElement row)> rows = new List<(Landmark, VisualElement)>();
        IVisualElementScheduledItem tick;

        public override void OnEnter()
        {
            var sys = LandmarkSystem.Instance;
            if (sys != null && sys.Selected != null) sys.Select(null, false);
            if (TwinState.Selected != null)
            {
                var ts = Camera.main != null ? Camera.main.GetComponent<TwinSelector>() : null;
                if (ts != null) ts.Select(-1); else TwinState.SetSelected(null);
            }
            LandmarkSystem.ShowPlanned = false;
            if (!IconicMonitor.Open && TwinState.Year != MapYear) { TwinState.Playing = false; TwinState.Year = MapYear; }
            wasOpen = IconicMonitor.Open; wasSel = null;
            Overview();
        }
        public override void OnExit() { tick?.Pause(); }

        /// <summary>The camera frames all the marked objects.</summary>
        static void Overview()
        {
            var sys = LandmarkSystem.Instance; var mc = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
            if (sys == null || mc == null || !sys.Ready) return;
            Vector3 lo = Vector3.one * 1e9f, hi = -Vector3.one * 1e9f; int n = 0;
            foreach (var id in Pinned) { var l = sys.Get(id); if (l == null) continue; lo = Vector3.Min(lo, l.World); hi = Vector3.Max(hi, l.World); n++; }
            if (n == 0) return;
            var c = (lo + hi) * 0.5f; c.y = 0f;
            // the long side of the spread across the wide screen; the marks (a dot with its label to the right and above) fill the part of
            // the screen right of the left panel and above the timeline: solved on the camera's own projection, far marks being smaller
            float dx = hi.x - lo.x, dz = hi.z - lo.z;
            float yaw = dz > dx ? -90f : 0f, pitch = 58f;
            var cam = Camera.main; float tv = Mathf.Tan((cam != null ? cam.fieldOfView : 40f) * 0.5f * Mathf.Deg2Rad), th = tv * (cam != null ? cam.aspect : 1.78f);
            var rot = Quaternion.Euler(pitch, yaw, 0f); var inv = Quaternion.Inverse(rot);
            Vector3 right = Quaternion.Euler(0f, yaw, 0f) * Vector3.right, fwd = Quaternion.Euler(0f, yaw, 0f) * Vector3.forward;
            const float X0 = 0.34f, X1 = 0.88f, Y0 = 0.15f, Y1 = 0.72f;
            float dist = Mathf.Max(dx, dz) * 1.2f + 3000f;
            for (int it = 0; it < 40; it++)
            {
                var pos = c - rot * Vector3.forward * dist; float mx = 1f, Mx = 0f, my = 1f, My = 0f;
                foreach (var id in Pinned)
                {
                    var l = sys.Get(id); if (l == null) continue;
                    var v = inv * (l.World + Vector3.up * Mathf.Min(l.Height, 150f) - pos); if (v.z < 1f) continue;
                    float x = 0.5f + 0.5f * v.x / (v.z * th), y = 0.5f + 0.5f * v.y / (v.z * tv);
                    mx = Mathf.Min(mx, x); Mx = Mathf.Max(Mx, x); my = Mathf.Min(my, y); My = Mathf.Max(My, y);
                }
                float ox = (mx + Mx) * 0.5f - (X0 + X1) * 0.5f, oy = (my + My) * 0.5f - (Y0 + Y1) * 0.5f;
                c += right * (ox * 2f * dist * th) + fwd * (oy * 2f * dist * tv / Mathf.Sin(pitch * Mathf.Deg2Rad));
                dist *= Mathf.Lerp(1f, Mathf.Max((Mx - mx) / (X1 - X0), (My - my) / (Y1 - Y0)), 0.6f);
            }
            mc.FlyTo(new MapCamera.View { name = "monitoring", target = c, distance = dist, yaw = yaw, pitch = pitch });
        }

        /// <summary>A mark or a row was clicked: fly close to the object and open its passport (the monitoring opens from there).</summary>
        public static void Open(Landmark l)
        {
            var sys = LandmarkSystem.Instance;
            if (sys == null || l == null || IconicMonitor.Open || !OnMap(l)) return;
            sys.Select(l);
        }
        /// <summary>From the passport: the construction monitoring of the object.</summary>
        public static void Monitor(Landmark l)
        {
            if (l == null || IconicMonitor.Instance == null || IconicMonitor.Open || !Watched(l)) return;
            IconicMonitor.Instance.Show(l.Id);
        }

        void Tick()
        {
            if (!On) return;
            bool open = IconicMonitor.Open;
            var sys = LandmarkSystem.Instance; var sel = sys != null ? sys.Selected : null;
            // back from the monitoring or from a passport: the whole map with its marks
            if (wasOpen && !open) { if (sys != null && sys.Selected != null) sys.Select(null, false); Overview(); sel = null; }
            else if (wasSel != null && sel == null && !open) Overview();
            wasOpen = open; wasSel = sel;
            foreach (var (l, row) in rows) row.EnableInClassList("selected", l == sel);
        }

        protected override void Build()
        {
            rows.Clear();
            tick?.Pause(); tick = leftCol.schedule.Execute(Tick).Every(100);
            var sys = LandmarkSystem.Instance;
            var top = Widgets.Block(panel);
            Widgets.Eyebrow(top, "МОНИТОРИНГ СТРОИТЕЛЬСТВА");
            var sum = new Label("Город по генплану. Выберите объект на карте: камера подлетит к нему и откроется паспорт. У Iconic Complex и KAIST из паспорта открывается мониторинг стройки.");
            sum.AddToClassList("summary"); sum.style.marginBottom = 4; top.Add(sum);
            if (sys != null)
            {
                Group(top, sys, "С мониторингом стройки", true);
                Group(top, sys, "Объекты на карте", false);
            }

            var gain = Widgets.Block(panel, "Что видно в мониторинге", "");
            foreach (var (ic, t) in new[] { ("scan", "Съёмки дроном с начала стройки до сдачи: ортофото 2D и модель 3D, сравнение двух дат шторкой"),
                                            ("eye", "«Что изменилось»: новое между съёмками синим, убранное красным"),
                                            ("layers", "BIM 4D: план и факт по этажам, отставание и опережение по каждому корпусу"),
                                            ("cctv", "Камеры на площадке: люди, техника, нарушения ТБ"),
                                            ("gantt_chart", "График работ и прогноз сдачи по фактическому темпу"),
                                            ("trending_up", "Контроль для инвестора: готовность по видам работ, отставание и его тренд, освоенный объём (SPI, CPI, EAC), три главных действия, недельный отчёт"),
                                            ("triangle_alert", "Дефекты на 3D-модели: место, важность, срок и ответственный"),
                                            ("cloud_sun", "Люди и техника по дням, погода Алматы и простои по правилам площадки") })
            {
                var r = new VisualElement(); r.AddToClassList("monmap-gain"); r.style.flexDirection = FlexDirection.Row; r.style.alignItems = Align.FlexStart; r.style.marginBottom = 7;
                var i = TwinUI.Icon(ic, 15); i.style.marginRight = 8; i.style.marginTop = 1; i.style.flexShrink = 0; r.Add(i);
                var l2 = new Label(t); l2.AddToClassList("small"); l2.style.flexShrink = 1; l2.style.whiteSpace = WhiteSpace.Normal; r.Add(l2);
                gain.Add(r);
            }
            gain.Add(SourceTags.Line(IconicMonitor.SrcMon, IconicMonitor.SrcClimate));
        }

        void Group(VisualElement parent, LandmarkSystem sys, string title, bool watched)
        {
            var h = new Label(title); h.AddToClassList("monmap-group"); parent.Add(h);
            foreach (var id in Pinned)
            {
                var l = sys.Get(id); if (l == null || Watched(l) != watched) continue;
                var row = new VisualElement(); row.AddToClassList("status-row"); row.AddToClassList("lm-row"); row.AddToClassList("monmap-row");
                row.Add(Widgets.Dot(l.District >= 0 ? CityStats.DistrictColors[l.District] : Color.white, true));
                var col = new VisualElement(); col.style.flexGrow = 1; col.style.flexShrink = 1; col.style.marginLeft = 8;
                var n = new Label(l.Short); n.AddToClassList("fw-medium"); col.Add(n);
                string sub = watched ? (l.Parts != null ? l.Parts.Count + " " + Corpus(l.Parts.Count) : "") + " · съёмки 2D/3D · BIM 4D · камеры"
                                     : l.StartYear + "–" + l.EndYear + (l.YearOfficial ? "" : "*") + " · " + (l.District >= 0 ? CityStats.DistrictIds[l.District] + " District" : "");
                var c = new Label(sub); c.AddToClassList("muted"); c.AddToClassList("small"); col.Add(c);
                row.Add(col);
                int si = LandmarkCatalog.NowIdx(l);
                row.Add(Widgets.Status(LandmarkCatalog.StatusText[si], LandmarkCatalog.StatusCls[si]));
                var ll = l; row.AddManipulator(new Clickable(() => Open(ll)));
                parent.Add(row); rows.Add((l, row));
            }
        }

        static string Corpus(int n) => n % 10 == 1 && n % 100 != 11 ? "корпус" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "корпуса" : "корпусов";

        public override void Refresh() { }
    }
}
