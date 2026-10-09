using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>"Инвестпроекты": the real projects of Alatau City on the map. Left: the official totals and the projects by district
    /// (click → fly + passport). Right: the LRT (phases, stations, trains) and sources. Planned objects appear as ghosts; labels show for all.</summary>
    public class ObjectsModule : TwinModuleBase
    {
        public override string Id => "objects";
        public override string TabKey => "tab_objects";
        readonly List<(Landmark l, VisualElement row, Label st)> rows = new List<(Landmark, VisualElement, Label)>();
        Label yearLine;

        public override void OnEnter() { LandmarkSystem.ShowPlanned = true; LandmarkSystem.OnSelected -= Sel; LandmarkSystem.OnSelected += Sel; }
        public override void OnExit() { LandmarkSystem.ShowPlanned = false; LandmarkSystem.OnSelected -= Sel; }
        void Sel(Landmark l) => Refresh();
        public override (Color, string)[] Legend => new[]
        {
            (new Color(0.20f, 0.78f, 0.35f), "работает / сдан в выбранном году"), (new Color(0.96f, 0.65f, 0.14f), "строится"),
            (new Color(0.48f, 0.65f, 1f), "пусконаладка · расширение · MoU"), (new Color(0.75f, 0.80f, 0.90f), "план — показан «призраком»"),
            (new Color(0.70f, 0.52f, 0.89f), "ЛРТ")
        };

        protected override void Build()
        {
            rows.Clear();
            var sys = LandmarkSystem.Instance;
            // ---------------- left: totals + projects by district
            var top = Widgets.Block(panel);
            Widgets.Eyebrow(top, "ИНВЕСТПРОЕКТЫ ALATAU CITY · ОТКРЫТЫЕ ДАННЫЕ");
            var sum = new Label("В пуле города 67 проектов на ≈ $6,9 млрд и ≈ 55 тыс. рабочих мест (сводка правительства, 26.08.2026). На карте — объекты, о которых есть публичные данные.");
            sum.AddToClassList("summary"); sum.style.marginBottom = 10; top.Add(sum);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid);
            void Row(params (string v, string l)[] items)
            {
                var r = new VisualElement(); r.AddToClassList("kpi-row"); grid.Add(r);
                foreach (var (v, l) in items) { var k = new VisualElement(); k.AddToClassList("kpi"); var a = new Label(l); a.AddToClassList("l"); k.Add(a); var b = new Label(v); b.AddToClassList("v"); k.Add(b); r.Add(k); }
            }
            Row(("67", "проектов в пуле"), ("$6,9 млрд", "инвестиций"));
            Row(("≈55 тыс.", "рабочих мест"), (sys != null ? (sys.Items.Count - 1).ToString() : "—", "объектов на карте"));
            yearLine = new Label(); yearLine.AddToClassList("muted"); yearLine.style.marginTop = 8; top.Add(yearLine);

            if (sys != null)
                for (int d = 0; d < CityStats.Districts; d++)
                {
                    if (TwinTour.Running && TwinTour.Zone >= 0 && d != TwinTour.Zone) continue;     // the presentation tells one district at a time
                    var b = Widgets.Block(panel, CityStats.DistrictIds[d] + " District", DistrictRole(d));
                    foreach (var l in sys.Items)
                    {
                        if (l.District != d || l.IsLrt) continue;
                        var row = new VisualElement(); row.AddToClassList("status-row"); row.AddToClassList("lm-row");
                        row.Add(Widgets.Dot(CityStats.DistrictColors[d], true));
                        var col = new VisualElement(); col.style.flexGrow = 1; col.style.marginLeft = 8;
                        var n = new Label(l.Name); n.AddToClassList("fw-medium"); col.Add(n);
                        var c = new Label(l.Purpose); c.AddToClassList("muted"); c.AddToClassList("small"); col.Add(c);
                        row.Add(col);
                        var st = Widgets.Status(LandmarkCatalog.StatusOf(l), LandmarkCatalog.ClsOf(l)); row.Add(st);
                        var ll = l; row.AddManipulator(new Clickable(() => LandmarkSystem.Instance?.Select(ll)));
                        b.Add(row); rows.Add((l, row, st));
                    }
                }

            // ---------------- right: LRT + sources
            Right();
            var lb = Widgets.Block(panel, "ЛРТ Алматы – Алатау – Конаев", "эстакада, 3 очереди");
            var lrtL = sys?.Get("lrt");
            int s = (int)TwinState.Scenario;
            for (int p = 0; p < TwinData.LrtPhaseNames.Length && p < 3; p++)
            {
                int oy = TwinData.LrtPhaseYear[s] != null ? TwinData.LrtPhaseYear[s][p] : 0;
                var f = Widgets.Fact($"{p + 1}-я очередь · {TwinData.LrtPhaseNames[p]}", Loc.N1(TwinData.LrtPhaseKm[p]) + " км · " + oy); lb.Add(f);
            }
            var lr = new VisualElement(); lr.AddToClassList("lm-btns");
            lr.Add(Widgets.Btn("Показать линию", () => { if (lrtL != null) LandmarkSystem.Instance?.Select(lrtL); }, "small"));
            lr.Add(Widgets.Btn(LrtLayer.TrainsOn ? "Скрыть поезда" : "Показать поезда", () => { LrtLayer.TrainsOn = !LrtLayer.TrainsOn; Rebuild(); Refresh(); }, "small"));
            lb.Add(lr);
            var note = new Label("Метро до Алатау не рассматривается, ставка на LRT (Kapital.kz, 21.05.2026). Трасса и станции — по слою ЛРТ генплана, годы очередей — по сценарию двойника.");
            note.AddToClassList("muted"); note.AddToClassList("small"); note.style.marginTop = 8; lb.Add(note);

            var how = Widgets.Block(panel, "Как читать карту", "");
            var h = new Label("Метки над объектами кликабельны: камера подлетит к зданию и откроет паспорт. Объекты, которые ещё не начаты в выбранном году, показаны полупрозрачными. В «Обзоре» метки появляются, когда объект построен.");
            h.AddToClassList("small"); how.Add(h);
            var src = Widgets.Block(panel, "Источники", "");
            foreach (var t in new[] { "Правительство РК, сводка по Alatau City — 26.08.2026", "SOM — Iconic Complex, 05.03.2026", "Kapital.kz, Forbes.kz, Kazinform, bes.media, 24.kz — 2024–2026",
                                      "ЕАБР — Griffin Logopark, 10.08.2026", "Расположение объектов условное: точные участки не публикуются" })
            { var l2 = new Label("· " + t); l2.AddToClassList("small"); l2.AddToClassList("muted"); l2.style.marginBottom = 3; src.Add(l2); }
            Widgets.SetCollapsed(src, true);
        }

        static string DistrictRole(int d) => d == 0 ? "финансы, бизнес, ворота города" : d == 1 ? "наука, образование, медицина" : d == 2 ? "промышленность и логистика" : "туризм и отдых на Капшагае";

        public override void Refresh()
        {
            if (yearLine == null) return;
            var sys = LandmarkSystem.Instance; int y = TwinState.Year; int built = 0, building = 0, total = 0;
            int ext = 0;
            if (sys != null) foreach (var l in sys.Items) { if (l.IsLrt) continue; total++; float p = LandmarkSystem.Progress(l, y); if (p >= 0.999f) { built++; if (LandmarkCatalog.StatusIdx(l) == 6) ext++; } else if (p > 0) building++; }
            yearLine.text = $"В {y} году: работает {built} из {total}" + (ext > 0 ? $" (расширяются {ext})" : "") + $", строится {building}.";
            foreach (var (l, row, st) in rows)
            {
                row.EnableInClassList("selected", sys != null && sys.Selected == l);
                if (st == null) continue;
                // the status follows the year on the timeline, like the passport card: «Строится 67 %» in 2032, «Работает» once it is done
                int si = LandmarkCatalog.StatusIdx(l);
                st.text = LandmarkCatalog.StatusLabel(l);
                foreach (var c in LandmarkCatalog.StatusCls) st.RemoveFromClassList(c);
                st.AddToClassList(LandmarkCatalog.StatusCls[si]);
            }
        }
    }
}
