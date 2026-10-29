using System;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>«Калькулятор инвестора»: the investor picks a sector, a district, the size of the investment, the jobs and the horizon and sees
    /// the benefits of the special legal regime (sourced), the taxes saved over the horizon (QTwin model, capped at 10 % by law),
    /// the year the networks reach a plot in the district (twin balance) and the nearest LRT station.</summary>
    public class InvestCalc
    {
        static readonly float[] Amounts = { 10, 50, 100, 250, 500, 1000 };
        static readonly int[] JobsOpt = { 50, 200, 500, 1000, 3000 };
        static readonly int[] Horizons = { 5, 10, 15, 20, 30 };
        static int sector, district = 2, amountI = 2, jobsI = 2, horizonI = 1;

        VisualElement result, benefits;

        public VisualElement Build(VisualElement parent)
        {
            var b = Widgets.Block(parent, "Калькулятор инвестора", "особый правовой режим");
            var intro = new Label("Выберите проект — двойник покажет льготы, сколько налогов останется в проекте и когда к участку подойдут сети.");
            intro.AddToClassList("note"); intro.style.marginBottom = 6; b.Add(intro);

            Group(b, "Отрасль", InvestRegistry.Sectors, () => sector, v => sector = v);
            Group(b, "Район", CityStats.DistrictIds, () => district, v => district = v);
            Group(b, "Инвестиции", Array.ConvertAll(Amounts, a => a >= 1000 ? "$1\u00A0млрд" : string.Format("${0}\u00A0млн", a)), () => amountI, v => amountI = v);
            Group(b, "Рабочие места", Array.ConvertAll(JobsOpt, j => Loc.N0(j)), () => jobsI, v => jobsI = v);
            Group(b, "Горизонт", Array.ConvertAll(Horizons, h => string.Format("{0} лет", h)), () => horizonI, v => horizonI = v);

            result = new VisualElement(); result.AddToClassList("w2-calc-res"); b.Add(result);

            var bb = Widgets.Block(parent, "Что даёт особый правовой режим", "закон от 08.05.2026, действует с 01.07.2026");
            benefits = new VisualElement(); bb.Add(benefits);
            foreach (var x in InvestRegistry.Benefits)
            {
                var r = new VisualElement(); r.AddToClassList("w2-ben");
                var t = new Label(x.Title); t.AddToClassList("w2-ben-t"); r.Add(t);
                var p = new Label(x.Plain); p.AddToClassList("note"); r.Add(p);
                var tag = SourceTags.Tag(x.Src); r.Add(tag);
                benefits.Add(r);
            }
            var warn = new Label("Конкретный размер льгот закон не фиксирует: его задаёт администрация города в бизнес-лицензии резидента.");
            warn.AddToClassList("note"); warn.style.marginTop = 6; bb.Add(warn);
            Widgets.SetCollapsed(bb, true);
            Refresh();
            return b;
        }

        void Group(VisualElement parent, string title, string[] items, Func<int> get, Action<int> set)
        {
            var cap = new Label(title); cap.AddToClassList("w2-cap"); parent.Add(cap);
            var row = new VisualElement(); row.AddToClassList("chips"); row.AddToClassList("w2-chips"); parent.Add(row);
            for (int i = 0; i < items.Length; i++)
            {
                int k = i; Button btn = null;
                btn = new Button(() => { set(k); foreach (var c in row.Children()) c.RemoveFromClassList("active"); btn.AddToClassList("active"); Refresh(); }) { text = items[i], focusable = false };
                btn.AddToClassList("chip"); btn.EnableInClassList("active", get() == i); row.Add(btn);
            }
        }

        public void Refresh()
        {
            if (result == null) return;
            result.Clear();
            float inv = Amounts[amountI]; int jobs = JobsOpt[jobsI], hor = Horizons[horizonI];
            var s = InvestRegistry.Estimate(sector, inv, jobs, hor);

            // ---- taxes saved (model)
            var head = new Label(string.Format("Налоговая экономия за {0} лет", hor)); head.AddToClassList("w2-h"); result.Add(head);
            var big = new Label(string.Format("≈\u00A0${0}\u00A0млн", Loc.N1(s.Result))); big.AddToClassList("w2-big"); result.Add(big);
            var bigSub = new Label(s.Total > s.Cap
                ? string.Format("Без потолка вышло бы ${0} млн, но закон ограничивает льготы ≈ 10 % вложений — ${1} млн.", Loc.N1(s.Total), Loc.N1(s.Cap))
                : string.Format("Это {0} % вложений — в пределах потолка закона (≈ 10 %).", Loc.N1(100f * s.Result / Mathf.Max(inv, 0.01f))));
            bigSub.AddToClassList("note"); result.Add(bigSub);
            result.Add(Widgets.Fact("Налог на прибыль (КПН)", string.Format("${0}\u00A0млн", Loc.N1(s.Cit))));
            result.Add(Widgets.Fact("НДС на ввоз оборудования", string.Format("${0}\u00A0млн", Loc.N1(s.Vat))));
            result.Add(Widgets.Fact("Налог на имущество", string.Format("${0}\u00A0млн", Loc.N1(s.Property))));
            var pf = Widgets.Fact("Соцналог с зарплат", string.Format("${0}\u00A0млн", Loc.N1(s.Payroll))); pf.style.borderBottomWidth = 0; result.Add(pf);
            var how = new Label("Модель: сколько налогов общего режима проект не заплатит при полной льготе. Реальный размер льготы решает администрация города.");
            how.AddToClassList("note"); result.Add(how);
            var ml = SourceTags.Line(InvestRegistry.CalcModel, InvestRegistry.MorganLewis); result.Add(ml);

            // ---- networks
            var nh = new Label(string.Format("Когда сети придут на участок · {0}", CityStats.DistrictIds[district])); nh.AddToClassList("w2-h"); nh.style.marginTop = 10; result.Add(nh);
            result.Add(NetRows(district));

            // ---- LRT
            var lh = new Label("Ближайшая станция ЛРТ"); lh.AddToClassList("w2-h"); lh.style.marginTop = 10; result.Add(lh);
            result.Add(LrtLine(district));
        }

        /// <summary>Five rows: power, heat, gas, water, sewer — from which year the district's capacity covers the demand (twin balance, active scenario).</summary>
        /// <summary>"Today" in the twin: late October 2026. The answer never follows the timeline slider.</summary>
        public const int TodayYear = 2026;

        public static VisualElement NetRows(int d)
        {
            var box = new VisualElement();
            int s = (int)TwinState.Scenario, y0 = TodayYear;
            if (!TwinData.Ready) { var l = new Label("Данные сетей загружаются…"); l.AddToClassList("note"); box.Add(l); return box; }
            bool anyPooled = false;
            foreach (var (key, name, _) in InvestRegistry.NetRes)
            {
                var a = InvestRegistry.When(s, key, d, y0); anyPooled |= a.Pooled;
                var r = new VisualElement(); r.AddToClassList("w2-net");
                var n = new Label(name); n.AddToClassList("w2-net-n"); r.Add(n);
                string v, cls;
                if (a.Year < 0) { v = "не хватает до 2050"; cls = "bad"; }
                else if (a.Year <= y0) { v = string.Format("есть сейчас · запас {0}\u00A0%", Mathf.RoundToInt(a.Spare * 100f)); cls = "ok"; }
                else { v = string.Format("через {0} · ≈\u00A0{1}", Years(a.Year - y0), a.Year); cls = "warn"; }
                var vl = new Label(v); vl.AddToClassList("w2-net-v"); vl.AddToClassList(cls); r.Add(vl);
                box.Add(r);
                if (a.Year > y0 || a.Year < 0)
                {
                    var sub = new Label(a.DefYears == 1
                        ? string.Format("Дефицит мощности в {0} году: новых потребителей подключить нельзя.", a.DefRanges)
                        : string.Format("Дефицит мощности в годы: {0}. В эти годы новых потребителей подключить нельзя.", a.DefRanges));
                    sub.AddToClassList("note"); sub.AddToClassList("w2-net-sub"); box.Add(sub);
                }
            }
            var hint = new Label("Когда мощности района хватит на всех потребителей и дальше до 2050 года дефицита не будет. Отсчёт от сегодня (октябрь 2026), год на шкале не влияет."
                + (anyPooled ? " Вода и газ — общие системы города." : ""));
            hint.AddToClassList("note"); hint.style.marginTop = 4; box.Add(hint);
            box.Add(SourceTags.Line(InvestRegistry.NetModel, Sources.ModelCity));
            return box;
        }

        static string Years(int n)
        {
            int m10 = n % 10, m100 = n % 100;
            string w = m10 == 1 && m100 != 11 ? "год" : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? "года" : "лет";
            return string.Format("{0}\u00A0{1}", n, w);
        }

        static VisualElement LrtLine(int d)
        {
            var box = new VisualElement();
            if (!TwinData.Ready || TwinData.LrtStations.Length == 0 || !CityStats.Ready) { var l = new Label("Данные ЛРТ загружаются…"); l.AddToClassList("note"); box.Add(l); return box; }
            var c = CityStats.DistrictBounds[Mathf.Clamp(d, 0, CityStats.Districts - 1)].center; var p0 = new Vector2(c.x, c.z);
            int best = -1; float bd = float.MaxValue;
            for (int i = 0; i < TwinData.LrtStations.Length; i++)
            {
                var st = TwinData.LrtStations[i]; float dist = Vector2.Distance(p0, new Vector2(st.x, st.y));
                if (dist < bd) { bd = dist; best = i; }
            }
            if (best < 0) return box;
            int s = (int)TwinState.Scenario, ph = Mathf.Clamp(Mathf.RoundToInt(TwinData.LrtStations[best].z), 0, TwinData.LrtPhaseNames.Length - 1);
            int oy = TwinData.LrtPhaseYear[s] != null && ph < TwinData.LrtPhaseYear[s].Length ? TwinData.LrtPhaseYear[s][ph] : 0;
            var f = Widgets.Fact(string.Format("{0}-я очередь · {1}", ph + 1, TwinData.LrtPhaseNames[ph]), string.Format("{0} км · открытие {1}", Loc.N1(bd / 1000f), oy));
            f.style.borderBottomWidth = 0; box.Add(f);
            var n = new Label("Расстояние от центра района. Трасса — по генплану, год открытия — по сценарию двойника."); n.AddToClassList("note"); box.Add(n);
            box.Add(SourceTags.Line(Sources.GenPlan, Sources.ModelCity));
            return box;
        }
    }
}
