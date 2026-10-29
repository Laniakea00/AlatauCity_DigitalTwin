using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>"Инвестпроекты": the registry of the investment projects of Alatau City from the open press (InvestRegistry). Left: the official
    /// totals with sources, filters by sector / district / status and the compact list. Right: the card of the selected project (with
    /// «Показать на карте» for projects that stand on the map), the investor calculator, the LRT and sources. Planned objects appear as ghosts.</summary>
    public class ObjectsModule : TwinModuleBase
    {
        public override string Id => "objects";
        public override string TabKey => "tab_objects";
        readonly List<(InvestRegistry.Project p, VisualElement row)> rows = new List<(InvestRegistry.Project, VisualElement)>();
        static int fSector = -1, fDistrict = -2, fStatus = -1;      // -1 / -2 = all
        static InvestRegistry.Project selected;
        Label yearLine, countLine; VisualElement list, card, calcBlock; InvestCalc calc; bool cardShown;

        public ObjectsModule() { InvestRegistry.Init(); }

        public override void OnEnter() { LandmarkSystem.ShowPlanned = true; LandmarkSystem.OnSelected -= Sel; LandmarkSystem.OnSelected += Sel; }
        public override void OnExit() { LandmarkSystem.ShowPlanned = false; LandmarkSystem.OnSelected -= Sel; }
        void Sel(Landmark l)
        {
            // a model clicked on the map: its registry card is prepared under the passport and shows again when the passport closes
            if (l != null) foreach (var p in InvestRegistry.Projects) if (p.Landmark == l.Id) { selected = p; break; }
            BuildCard(); Refresh();
        }
        public override (Color, string)[] Legend => new[]
        {
            (new Color(0.20f, 0.78f, 0.35f), "работает / сдан в выбранном году"), (new Color(0.96f, 0.65f, 0.14f), "строится"),
            (new Color(0.48f, 0.65f, 1f), "пусконаладка · расширение · MoU"), (new Color(0.75f, 0.80f, 0.90f), "план — показан «призраком»"),
            (new Color(0.70f, 0.52f, 0.89f), "ЛРТ")
        };

        protected override void Build()
        {
            rows.Clear();
            // ---------------- left: totals
            var top = Widgets.Block(panel);
            Widgets.Eyebrow(top, "ИНВЕСТПРОЕКТЫ ALATAU CITY · ОТКРЫТЫЕ ДАННЫЕ");
            var sum = new Label("В пуле города 67 проектов на ≈ $6,9 млрд и ≈ 55 тыс. рабочих мест, плюс 26 инфраструктурных проектов (сводка правительства, 26.08.2026).");
            sum.AddToClassList("summary"); sum.style.marginBottom = 10; top.Add(sum);
            var grid = new VisualElement(); grid.AddToClassList("kpi-grid"); top.Add(grid);
            void Row(params (string v, string l, string src)[] items)
            {
                var r = new VisualElement(); r.AddToClassList("kpi-row"); grid.Add(r);
                foreach (var (v, l, src) in items)
                {
                    var k = new VisualElement(); k.AddToClassList("kpi"); var a = new Label(l); a.AddToClassList("l"); k.Add(a); var b = new Label(v); b.AddToClassList("v"); k.Add(b); r.Add(k);
                    if (src != null) SourceTags.Attach(k, src);
                }
            }
            int named = InvestRegistry.Projects.Count, withSum = 0; float usd = 0;
            foreach (var p in InvestRegistry.Projects) if (p.UsdM > 0) { withSum++; usd += p.UsdM; }
            Row(("67", "проектов в пуле", Sources.GovSummary), ("$6,9\u00A0млрд", "инвестиций", Sources.GovSummary));
            Row(("≈\u00A055\u00A0тыс.", "рабочих мест", Sources.GovSummary), (named.ToString(), "названы в прессе", null));
            countLine = new Label(string.Format("Поимённо в открытых источниках названы {0} компаний и проектов из 67; сумма раскрыта у {1} из них — ≈ ${2} млрд. Остальные проекты пула не публиковались.",
                named, withSum, Loc.N1(usd / 1000f)));
            countLine.AddToClassList("note"); countLine.style.marginTop = 8; top.Add(countLine);
            var hist = new Label(string.Format("Рост пула: 21.05.2026 — 53 проекта на 2 трлн ₸ (≈ ${0} млрд по курсу НБ РК {1} ₸/$) → 26.08.2026 — 67 проектов на $6,9 млрд.",
                Loc.N1(2e12f / InvestRegistry.KztPerUsd / 1e9f), Loc.N1(InvestRegistry.KztPerUsd)));
            hist.AddToClassList("note"); hist.style.marginTop = 4; top.Add(hist);
            top.Add(SourceTags.Line(InvestRegistry.QzPool, Sources.NbrkRate));
            yearLine = new Label(); yearLine.AddToClassList("muted"); yearLine.style.marginTop = 6; top.Add(yearLine);

            // ---------------- left: filters + list
            var fb = Widgets.Block(panel, "Реестр проектов", "клик — карточка проекта");
            Filter(fb, "Отрасль", InvestRegistry.Sectors, () => fSector, v => fSector = v, -1);
            var dn = new string[CityStats.Districts + 1]; for (int d = 0; d < CityStats.Districts; d++) dn[d] = CityStats.DistrictIds[d]; dn[CityStats.Districts] = "не указан";
            Filter(fb, "Район", dn, () => fDistrict == -1 ? CityStats.Districts : fDistrict, v => fDistrict = v == CityStats.Districts ? -1 : v, -2);
            Filter(fb, "Статус", InvestRegistry.StatusNames, () => fStatus, v => fStatus = v, -1);
            list = new VisualElement(); list.AddToClassList("w2-list"); fb.Add(list);
            FillList();

            // ---------------- right: card, calculator, LRT, sources
            Right();
            card = new VisualElement(); panel.Add(card);
            BuildCard();
            calc = new InvestCalc(); calcBlock = calc.Build(panel); cardShown = false; SyncCalc();

            var sys = LandmarkSystem.Instance;
            var lb = Widgets.Block(panel, "ЛРТ Алматы – Алатау – Конаев", "эстакада, 3 очереди");
            var lrtL = sys?.Get("lrt");
            int s = (int)TwinState.Scenario;
            for (int p = 0; p < TwinData.LrtPhaseNames.Length && p < 3; p++)
            {
                int oy = TwinData.LrtPhaseYear[s] != null ? TwinData.LrtPhaseYear[s][p] : 0;
                var f = Widgets.Fact(string.Format("{0}-я очередь · {1}", p + 1, TwinData.LrtPhaseNames[p]), string.Format("{0} км · {1}", Loc.N1(TwinData.LrtPhaseKm[p]), oy)); lb.Add(f);
            }
            var lr = new VisualElement(); lr.AddToClassList("lm-btns");
            lr.Add(Widgets.Btn("Показать линию", () => { if (lrtL != null) LandmarkSystem.Instance?.Select(lrtL); }, "small"));
            lr.Add(Widgets.Btn(LrtLayer.TrainsOn ? "Скрыть поезда" : "Показать поезда", () => { LrtLayer.TrainsOn = !LrtLayer.TrainsOn; Rebuild(); Refresh(); }, "small"));
            lb.Add(lr);
            var note = new Label("Метро до Алатау не рассматривается, ставка на LRT (Kapital.kz, 21.05.2026). Трасса и станции — по слою ЛРТ генплана, годы очередей — по сценарию двойника.");
            note.AddToClassList("muted"); note.AddToClassList("small"); note.style.marginTop = 8; lb.Add(note);
            lb.Add(SourceTags.Line(Sources.GenPlan, Sources.ModelCity));
            Widgets.SetCollapsed(lb, true);

            var how = Widgets.Block(panel, "Как читать карту", "");
            var h = new Label("Метки над объектами кликабельны: камера подлетит к зданию и откроет паспорт. Объекты, которые ещё не начаты в выбранном году, показаны полупрозрачными. Расположение объектов условное: точные участки не публикуются.");
            h.AddToClassList("small"); how.Add(h);
            Widgets.SetCollapsed(how, true);
        }

        void Filter(VisualElement parent, string title, string[] items, System.Func<int> get, System.Action<int> set, int all)
        {
            var cap = new Label(title); cap.AddToClassList("w2-cap"); parent.Add(cap);
            var row = new VisualElement(); row.AddToClassList("chips"); row.AddToClassList("w2-chips"); parent.Add(row);
            Button allB = null; var bs = new List<Button>();
            void MarkChips() { allB.EnableInClassList("active", get() == all); for (int i = 0; i < bs.Count; i++) bs[i].EnableInClassList("active", get() == i); }
            allB = new Button(() => { set(all); MarkChips(); FillList(); }) { text = "Все", focusable = false };
            allB.AddToClassList("chip"); row.Add(allB);
            for (int i = 0; i < items.Length; i++)
            {
                int k = i;
                var b = new Button(() => { if (get() == k) set(all); else set(k); MarkChips(); FillList(); }) { text = items[i], focusable = false };
                b.AddToClassList("chip"); row.Add(b); bs.Add(b);
            }
            MarkChips();
        }

        bool Pass(InvestRegistry.Project p)
            => (fSector < 0 || p.Sector == fSector) && (fStatus < 0 || p.Status == fStatus) && (fDistrict == -2 || p.District == fDistrict);

        void FillList()
        {
            if (list == null) return;
            list.Clear(); rows.Clear(); int n = 0;
            foreach (var p in InvestRegistry.Projects)
            {
                if (!Pass(p)) continue; n++;
                var row = new VisualElement(); row.AddToClassList("status-row"); row.AddToClassList("lm-row"); row.AddToClassList("w2-row");
                row.Add(Widgets.Dot(p.District >= 0 ? CityStats.DistrictColors[p.District] : new Color(0.45f, 0.45f, 0.45f), true));
                var col = new VisualElement(); col.style.flexGrow = 1; col.style.flexShrink = 1; col.style.marginLeft = 8;
                var nm = new Label(p.Name); nm.AddToClassList("fw-medium"); nm.AddToClassList("w2-row-n"); col.Add(nm);
                var sub = new Label(string.Format("{0} · {1}", p.Investor, InvestRegistry.Sectors[p.Sector])); sub.AddToClassList("muted"); sub.AddToClassList("small"); sub.AddToClassList("w2-row-s"); col.Add(sub);
                row.Add(col);
                var right = new VisualElement(); right.AddToClassList("w2-row-r");
                if (p.UsdM > 0) { var a = new Label(Usd(p.UsdM)); a.AddToClassList("w2-amt"); right.Add(a); }
                right.Add(Widgets.Status(InvestRegistry.StatusNames[p.Status], InvestRegistry.StatusCls[p.Status]));
                row.Add(right);
                var pp = p; row.AddManipulator(new Clickable(() => Open(pp)));
                list.Add(row); rows.Add((p, row));
            }
            if (n == 0) { var l = new Label("Нет проектов с такими фильтрами."); l.AddToClassList("note"); list.Add(l); }
            Mark();
        }

        void Open(InvestRegistry.Project p)
        {
            selected = p;
            // the registry card lives in the right column, which the landmark passport hides: close the passport, only fly the camera
            var sys = LandmarkSystem.Instance;
            if (sys != null)
            {
                if (sys.Selected != null) sys.Select(null, false);
                var l = p.Landmark != null ? sys.Get(p.Landmark) : null;
                if (l != null) sys.FlyTo(l);
            }
            BuildCard(); Mark();
        }

        void Mark() { foreach (var (p, row) in rows) row.EnableInClassList("selected", p == selected); }

        static string Usd(float m) => m >= 1000f ? string.Format("${0}\u00A0млрд", Loc.N1(m / 1000f)) : string.Format("${0}\u00A0млн", Loc.N0(m));

        /// <summary>The calculator folds while a project card is open (both do not fit the column) and unfolds when the card closes.</summary>
        void SyncCalc()
        {
            bool open = selected != null;
            if (calcBlock == null || open == cardShown) return;
            cardShown = open; Widgets.SetCollapsed(calcBlock, open);
        }

        void BuildCard()
        {
            if (card == null) return;
            card.Clear(); SyncCalc();
            var p = selected; if (p == null) return;
            var b = Widgets.Block(card, p.Name, InvestRegistry.Sectors[p.Sector]); b.AddToClassList("w2-card");
            b.Add(Widgets.Fact("Инвестор", p.Investor));
            b.Add(Widgets.Fact("Страна", string.IsNullOrEmpty(p.Country) ? "не указана" : p.Country));
            b.Add(Widgets.Fact("Район", p.District >= 0 ? string.Format("{0} District", CityStats.DistrictIds[p.District]) : "не опубликован"));
            b.Add(Widgets.Fact("Инвестиции", p.AmountNote ?? (p.UsdM > 0 ? Usd(p.UsdM) : "не раскрыты")));
            b.Add(Widgets.Fact("Рабочие места", p.Jobs > 0 ? string.Format("≈ {0}", Loc.N0(p.Jobs)) : "не раскрыты"));
            b.Add(Widgets.Fact("Сроки", string.IsNullOrEmpty(p.Years) ? "не объявлены" : p.Years));
            var stf = Widgets.Fact("Статус на 10.2026", ""); stf.RemoveAt(1);
            stf.Add(Widgets.Status(InvestRegistry.StatusNames[p.Status], InvestRegistry.StatusCls[p.Status])); b.Add(stf);
            var hint = new Label(InvestRegistry.StatusHint[p.Status]); hint.AddToClassList("note"); b.Add(hint);
            if (!string.IsNullOrEmpty(p.Note)) { var n = new Label(p.Note); n.AddToClassList("small"); n.style.marginTop = 6; b.Add(n); }
            b.Add(p.Src2 != null ? SourceTags.Line(p.Src, p.Src2) : SourceTags.Line(p.Src));
            var sys = LandmarkSystem.Instance; var l = p.Landmark != null && sys != null ? sys.Get(p.Landmark) : null;
            var btns = new VisualElement(); btns.AddToClassList("lm-btns"); b.Add(btns);
            if (l != null)
            {
                var ml = new Label(string.Format("На карте в {0} году: {1}. Место на карте условное.", TwinState.Year, LandmarkCatalog.StatusLabel(l).ToLowerInvariant()));
                ml.AddToClassList("note"); ml.style.marginTop = 4; b.Insert(b.IndexOf(btns), ml);
                btns.Add(Widgets.Btn("Показать на карте", () => LandmarkSystem.Instance?.Select(l), "small"));
            }
            btns.Add(Widgets.Btn("Закрыть", () => { selected = null; LandmarkSystem.Instance?.Select(null, false); BuildCard(); Mark(); }, "small", "ghost"));
        }

        public override void Refresh()
        {
            if (yearLine == null) return;
            var sys = LandmarkSystem.Instance; int y = TwinState.Year; int built = 0, building = 0, total = 0;
            if (sys != null) foreach (var l in sys.Items) { if (l.IsLrt) continue; total++; float p = LandmarkSystem.Progress(l, y); if (p >= 0.999f) built++; else if (p > 0) building++; }
            yearLine.text = string.Format("На карте {0} объектов с 3D-моделью. В {1} году работает {2}, строится {3}.", total, y, built, building);
            calc?.Refresh();
            if (selected != null && selected.Landmark != null) BuildCard();
            Mark();
        }
    }
}
