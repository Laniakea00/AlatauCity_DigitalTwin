using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Passport of a landmark (drawn into TwinUI's floating card): name, investor, district and status, what it is,
    /// readiness in the shown year on a start → completion bar, the published facts, source and date; orbit / back to the city.</summary>
    public static class LandmarkCard
    {
        public static void Fill(VisualElement card, Landmark l)
        {
            card.style.display = DisplayStyle.Flex; card.Clear(); card.AddToClassList("lm-card");
            var sys = LandmarkSystem.Instance;
            var head = new VisualElement(); head.AddToClassList("head");
            var t = new Label(l.Name); t.AddToClassList("t"); head.Add(t);
            head.Add(Widgets.Btn("×", () => sys?.Select(null, false), "small", "ghost"));
            card.Add(head);
            var co = new Label(l.Company); co.AddToClassList("id"); card.Add(co);

            var chips = new VisualElement(); chips.AddToClassList("lm-chips");
            if (l.District >= 0)
            {
                var dc = new VisualElement(); dc.AddToClassList("lm-chip"); var d = Widgets.Dot(CityStats.DistrictColors[l.District], true); dc.Add(d);
                dc.Add(new Label(CityStats.DistrictIds[l.District] + " District")); chips.Add(dc);
            }
            var stc = Widgets.Status(LandmarkCatalog.StatusOf(l), LandmarkCatalog.ClsOf(l)); chips.Add(stc);
            card.Add(chips);
            var pu = new Label(l.Purpose); pu.AddToClassList("lm-purpose"); card.Add(pu);

            if (l.IsLrt) LrtBody(card, l);
            else
            {
                // readiness in the shown year
                int y = TwinState.Year; float pr = LandmarkSystem.Progress(l, y);
                var tl = new VisualElement(); tl.AddToClassList("lm-tl");
                var tlh = new VisualElement(); tlh.AddToClassList("row"); tlh.style.justifyContent = Justify.SpaceBetween;
                tlh.Add(new Label(l.StartYear.ToString()) { pickingMode = PickingMode.Ignore });
                var mid = new Label(pr <= 0f ? $"в {y} году ещё не начат" : pr >= 0.999f ? $"в {y} году работает" : $"в {y} году готов на {Mathf.RoundToInt(pr * 100)} %") { pickingMode = PickingMode.Ignore };
                mid.AddToClassList(pr >= 0.999f ? "ok" : pr > 0 ? "warn" : "muted"); tlh.Add(mid);
                tlh.Add(new Label(l.EndYear + (l.YearOfficial ? "" : "*")) { pickingMode = PickingMode.Ignore });
                tl.Add(tlh);
                var bar = new VisualElement(); bar.AddToClassList("lm-bar"); var fill = new VisualElement(); fill.AddToClassList("lm-fill");
                fill.style.width = Length.Percent(pr * 100f); fill.EnableInClassList("done", pr >= 0.999f); bar.Add(fill); tl.Add(bar);
                card.Add(tl);
                // the 5 figures an investor asks about first; the rest (and the sources) stay behind "Источники"
                var facts = new VisualElement(); facts.AddToClassList("lm-facts"); card.Add(facts);
                foreach (var (k, v) in KeyFacts(l)) facts.Add(Widgets.Fact(k, v));
            }
            if (!TwinTour.Running)
            {
                var more = new VisualElement(); more.AddToClassList("lm-src");
                var mb = Widgets.Btn(srcOpen ? "Скрыть источники" : "Источники и статус ›", () => { srcOpen = !srcOpen; Fill(card, l); }, "small", "ghost"); mb.style.alignSelf = Align.FlexStart; mb.style.marginLeft = -8;
                card.Add(mb);
                if (srcOpen)
                {
                    more.Add(new Label("Статус: " + l.StatusNote));
                    more.Add(new Label("Источник: " + l.Source + " · " + l.SourceDate));
                    if (!l.IsLrt) more.Add(new Label("Расположение условное — по функции района в генплане."));
                    if (!l.IsLrt && !l.YearOfficial) more.Add(new Label("Срок ввода не опубликован — в демо принят ориентир."));
                    card.Add(more);
                }
            }

            var btns = new VisualElement(); btns.AddToClassList("lm-btns");
            if (!l.IsLrt)
            {
                var ob = Widgets.Btn(LandmarkSystem.OrbitOn ? "Облёт: вкл" : "Облёт: выкл", () => { sys?.ToggleOrbit(); Fill(card, l); }, "small");
                if (LandmarkSystem.OrbitOn) ob.AddToClassList("active");
                btns.Add(ob);
            }
            if (!TwinTour.Running) btns.Add(Widgets.Btn("Весь город", () =>
            {
                sys?.Select(null, false);
                var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null; if (cam != null) cam.FlyTo(cam.overview);
            }, "small", "ghost"));
            card.Add(btns);
        }

        static bool srcOpen;
        static readonly string[] Skip = { "Расположение", "Примечание" };
        static readonly string[] Order = { "Инвестиции", "Рабочие места", "Площадь", "Главная башня", "Мощность", "Студенты", "Номера", "Склады", "Параметры", "Сроки" };
        /// <summary>Up to five facts, the ones that matter to an investor first.</summary>
        static System.Collections.Generic.List<(string, string)> KeyFacts(Landmark l)
        {
            var all = new System.Collections.Generic.List<(string, string)>();
            foreach (var f in l.Facts) if (System.Array.IndexOf(Skip, f.Item1) < 0) all.Add(f);
            all.Sort((a, b) => Rank(a.Item1).CompareTo(Rank(b.Item1)));
            if (all.Count > 5) all.RemoveRange(5, all.Count - 5);
            return all;
        }
        static int Rank(string k) { for (int i = 0; i < Order.Length; i++) if (k.StartsWith(Order[i])) return i; return Order.Length; }

        static void LrtBody(VisualElement card, Landmark l)
        {
            int s = (int)TwinState.Scenario, y = TwinState.Year;
            float km = 0; foreach (var k in TwinData.LrtPhaseKm) km += k;
            var lrt = LrtLayer.Instance;
            card.Add(Widgets.Fact("Длина", Loc.N1(km) + " км в 3 очереди"));
            card.Add(Widgets.Fact("Станции", (lrt != null ? lrt.Stations.Count : TwinData.LrtStations.Length) + ""));
            for (int p = 0; p < TwinData.LrtPhaseNames.Length && p < 3; p++)
            {
                int oy = TwinData.LrtPhaseYear[s] != null ? TwinData.LrtPhaseYear[s][p] : 0;
                var f = Widgets.Fact($"{p + 1}-я очередь · {TwinData.LrtPhaseNames[p]}", Loc.N1(TwinData.LrtPhaseKm[p]) + " км · " + oy);
                var v = f.Q<Label>(className: "v"); if (v != null) v.style.color = oy <= y ? new Color(0.20f, 0.78f, 0.35f) : new Color(0.53f, 0.53f, 0.53f);
                card.Add(f);
            }
            card.Add(Widgets.Fact("Годы очередей", "сценарий двойника «" + TwinScenario.Name(TwinState.Scenario) + "»"));
            card.Add(Widgets.Fact("Поезда", "LRV 2 × 28 м; в демо движение ускорено ×6"));
            var b = new VisualElement(); b.AddToClassList("lm-btns");
            b.Add(Widgets.Btn(LrtLayer.TrainsOn ? "Скрыть поезда" : "Показать поезда", () => { LrtLayer.TrainsOn = !LrtLayer.TrainsOn; Fill(card, l); }, "small"));
            card.Add(b);
        }
    }
}
