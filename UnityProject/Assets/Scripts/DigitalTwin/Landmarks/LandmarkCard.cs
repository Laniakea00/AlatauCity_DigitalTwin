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
            // inside the tower its own panel (IconicInterior) takes the passport's place
            if (IconicInterior.Active && TowerProfile.For(l.Id) == IconicShape.P) { card.style.display = DisplayStyle.None; return; }
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
            int sNow = Modules.MonitoringModule.On ? LandmarkCatalog.NowIdx(l) : LandmarkCatalog.StatusIdx(l);
            var stc = Widgets.Status(LandmarkCatalog.StatusText[sNow], LandmarkCatalog.StatusCls[sNow]); chips.Add(stc);
            card.Add(chips);
            var pu = new Label(l.Purpose); pu.AddToClassList("lm-purpose"); card.Add(pu);

            if (l.IsLrt) LrtBody(card, l);
            else
            {
                // readiness in the shown year (on the monitoring map: today)
                bool mon = Modules.MonitoringModule.On;
                int y = TwinState.Year; float pr = LandmarkSystem.Progress(l, mon ? Modules.MonitoringModule.Today : y);
                var tl = new VisualElement(); tl.AddToClassList("lm-tl");
                var tlh = new VisualElement(); tlh.AddToClassList("row"); tlh.style.justifyContent = Justify.SpaceBetween;
                tlh.Add(new Label(l.StartYear.ToString()) { pickingMode = PickingMode.Ignore });
                var mid = new Label(mon ? "сейчас: " + l.StatusNote : pr <= 0f ? $"в {y} году ещё не начат" : pr >= 0.999f ? $"в {y} году работает" : $"в {y} году готов на {Mathf.RoundToInt(pr * 100)} %") { pickingMode = PickingMode.Ignore };
                if (mon) { mid.style.whiteSpace = WhiteSpace.Normal; mid.style.flexShrink = 1; mid.style.unityTextAlign = TextAnchor.UpperCenter; mid.style.marginLeft = 8; mid.style.marginRight = 8; }
                mid.AddToClassList(pr >= 0.999f ? "ok" : pr > 0 ? "warn" : "muted"); tlh.Add(mid);
                tlh.Add(new Label(l.EndYear + (l.YearOfficial ? "" : "*")) { pickingMode = PickingMode.Ignore });
                tl.Add(tlh);
                var bar = new VisualElement(); bar.AddToClassList("lm-bar"); var fill = new VisualElement(); fill.AddToClassList("lm-fill");
                fill.style.width = Length.Percent(pr * 100f); fill.EnableInClassList("done", pr >= 0.999f); bar.Add(fill); tl.Add(bar);
                card.Add(tl);
                // the 5 figures an investor asks about first; the rest (and the sources) stay behind "Источники"
                var facts = new VisualElement(); facts.AddToClassList("lm-facts"); card.Add(facts);
                foreach (var (k, v) in KeyFacts(l)) facts.Add(Widgets.Fact(k, v));
                if (!mon) Capacity(card, l, y);
                if (mon) MonitorNote(card, l);
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
            var tp = TowerProfile.For(l.Id);
            if (Modules.MonitoringModule.On)
            {
                // the monitoring map: the way into the monitoring first; the other objects only look and read
                if (Modules.MonitoringModule.Watched(l)) btns.Add(Widgets.Btn("Открыть мониторинг стройки →", () => Modules.MonitoringModule.Monitor(l), "small", "primary"));
                btns.Add(Widgets.Btn("Ближе", () => sys?.CloseUp(l), "small"));
                var ob2 = Widgets.Btn(LandmarkSystem.OrbitOn ? "Облёт: вкл" : "Облёт: выкл", () => { sys?.ToggleOrbit(); Fill(card, l); }, "small");
                if (LandmarkSystem.OrbitOn) ob2.AddToClassList("active");
                btns.Add(ob2);
                btns.Add(Widgets.Btn("К карте", () => sys?.Select(null, false), "small", "ghost"));
                card.Add(btns);
                return;
            }
            if (tp != null && IconicInterior.Instance != null)
            {
                // into the tower: the floor plan as it is being built in the shown year; the construction monitoring of the object
                bool can = IconicInterior.Instance.CanEnter(l.Id, out _);
                btns.Add(Widgets.Btn(can ? tp.Enter : tp.Enter + " · " + (l.StartYear + 1), () => IconicInterior.Instance.Enter(l.Id), "small", "primary"));
                btns.Add(Widgets.Btn("Мониторинг строительства", () => IconicMonitor.Instance?.Show(l.Id), "small"));
            }
            if (!l.IsLrt) btns.Add(Widgets.Btn("Ближе", () => sys?.CloseUp(l), "small"));
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

        /// <summary>On the monitoring map: what the construction monitoring of this object shows, or that it is not connected yet.</summary>
        static void MonitorNote(VisualElement card, Landmark l)
        {
            var box = new VisualElement(); box.AddToClassList("lm-cap"); box.AddToClassList("lm-monnote"); card.Add(box);
            var hr = new VisualElement(); hr.AddToClassList("row"); box.Add(hr);
            var h = new Label("МОНИТОРИНГ СТРОИТЕЛЬСТВА") { pickingMode = PickingMode.Ignore }; h.AddToClassList("lm-cap-h"); hr.Add(h);
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; hr.Add(sp);
            bool w = Modules.MonitoringModule.Watched(l);
            var tag = new Label(w ? "подключён" : "не подключён") { pickingMode = PickingMode.Ignore }; tag.AddToClassList("lm-cap-tag"); tag.EnableInClassList("est", !w); tag.EnableInClassList("on", w);
            hr.Add(tag);
            var t = new Label(w ? "Съёмки дроном 2D и 3D по датам с начала стройки, «Что изменилось» между съёмками, BIM 4D план и факт по корпусам, камеры на площадке."
                                : l.Status == LStatus.Construction ? "Объект строится: мониторинг подключается по запросу застройщика — те же съёмки, BIM 4D и камеры, что у Iconic Complex и KAIST."
                                : "Мониторинг подключается с началом строительства: съёмки дроном, BIM 4D и камеры, как у Iconic Complex и KAIST.") { pickingMode = PickingMode.Ignore };
            t.AddToClassList("note"); t.style.marginTop = 4; t.style.whiteSpace = WhiteSpace.Normal; box.Add(t);
        }

        /// <summary>Production capacity: design, the load and output in the shown year, jobs / revenue / export at full load.</summary>
        static void Capacity(VisualElement card, Landmark l, int y)
        {
            var c = LandmarkCapacity.Of(l.Id); if (c == null) return;
            float cap = LandmarkCapacity.CapacityAt(l, c, y), load = LandmarkCapacity.Load(l, y);
            var box = new VisualElement(); box.AddToClassList("lm-cap"); card.Add(box);
            var h = new VisualElement(); h.AddToClassList("row"); box.Add(h);
            var t = new Label("ПРОИЗВОДСТВЕННАЯ МОЩНОСТЬ") { pickingMode = PickingMode.Ignore }; t.AddToClassList("lm-cap-h"); h.Add(t);
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; h.Add(sp);
            var tag = new Label(c.Official ? "официально" : "оценка") { pickingMode = PickingMode.Ignore }; tag.AddToClassList("lm-cap-tag"); tag.EnableInClassList("est", !c.Official); h.Add(tag);
            var v = new Label(LandmarkCapacity.Fmt(cap, c.Unit)) { pickingMode = PickingMode.Ignore }; v.AddToClassList("lm-cap-v"); box.Add(v);
            var p = new Label(c.Product + (string.IsNullOrEmpty(c.Plain) ? "" : " · " + c.Plain)) { pickingMode = PickingMode.Ignore }; p.AddToClassList("note"); box.Add(p);
            var bar = new VisualElement(); bar.AddToClassList("lm-bar"); bar.style.marginTop = 8; var fill = new VisualElement(); fill.AddToClassList("lm-fill");
            fill.style.width = Length.Percent(load * 100f); fill.EnableInClassList("done", load >= 0.8f); bar.Add(fill); box.Add(bar);
            var ly = new Label(load > 0f ? $"{y}: загрузка {Mathf.RoundToInt(load * 100f)} % · выпуск {LandmarkCapacity.Fmt(cap * load, c.Unit)}" : $"{y}: ещё не работает · запуск в {l.EndYear}") { pickingMode = PickingMode.Ignore };
            ly.AddToClassList("note"); ly.style.marginTop = 4; box.Add(ly);
            var parts = new System.Collections.Generic.List<string>();
            if (c.Jobs > 0) parts.Add(Loc.N0(c.Jobs) + " рабочих мест");
            if (c.RevenueUsdM > 0) parts.Add("выручка ≈ $" + Loc.N0(c.RevenueUsdM) + " млн в год");
            if (c.Export > 0) parts.Add("экспорт " + Mathf.RoundToInt(c.Export * 100f) + " %");
            if (parts.Count > 0) { var f = new Label("При полной загрузке: " + string.Join(" · ", parts)) { pickingMode = PickingMode.Ignore }; f.AddToClassList("note"); f.style.marginTop = 2; box.Add(f); }
            if (l.S2End > 0 && c.Stage2Gain > 0) { var s2 = new Label($"2-я очередь ({l.S2End}): +{Mathf.RoundToInt(c.Stage2Gain * 100f)} % мощности") { pickingMode = PickingMode.Ignore }; s2.AddToClassList("note"); box.Add(s2); }
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
