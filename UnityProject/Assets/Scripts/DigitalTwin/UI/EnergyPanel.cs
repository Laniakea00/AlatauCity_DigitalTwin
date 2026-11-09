using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Card of the presentation step «Прогноз: энергия 2034»: the year, a load gauge of ПС 220 кВ «Golden», peak demand vs capacity,
    /// then one answer line per beat of the story (evening → growth → outage → the twin's answer → lights back) with one muted line under it.
    /// During the outage the 2028–2036 chart gives its place to the consequence (residents, schools, hospitals in the dark); with the
    /// answer the chart comes back and shows the fix (the capacity step moves to TourEnergy.YFixFrom).</summary>
    public class EnergyPanel : VisualElement
    {
        readonly TourEnergy e;
        readonly Label year, pct, dem, cap, status, sub, cPeople, cSchools, cHealth;
        readonly VisualElement gauge, chart, xr, cons, chartBox;
        const int C0 = 2028, C1 = 2036;
        int shownPhase = -1;

        public EnergyPanel(TourEnergy en)
        {
            e = en; AddToClassList("en-card"); AddToClassList("w22-en"); pickingMode = PickingMode.Ignore;
            Add(L("ПРОГНОЗ QTWIN · ЭНЕРГИЯ GOLDEN", "en-h"));
            var row = new VisualElement { pickingMode = PickingMode.Ignore }; row.AddToClassList("en-row"); Add(row);
            year = L("2028", "en-year"); row.Add(year);
            gauge = new VisualElement { pickingMode = PickingMode.Ignore }; gauge.AddToClassList("en-gauge"); gauge.generateVisualContent += DrawGauge; row.Add(gauge);
            pct = L("0 %", "en-pct"); gauge.Add(pct);
            var figs = new VisualElement { pickingMode = PickingMode.Ignore }; figs.AddToClassList("en-figs"); row.Add(figs);
            dem = L("", "en-v"); figs.Add(dem); figs.Add(L("спрос в вечерний пик", "en-l"));
            cap = L("", "en-v"); cap.style.marginTop = 6; figs.Add(cap); figs.Add(L("мощность подстанции", "en-l"));

            // the answer of the moment: the largest line of the card under the gauge, one muted line under it
            status = L("", "w22-en-status"); Add(status);
            sub = L("", "w22-en-sub"); Add(sub);

            // chart (growth, answer, fix) or the consequence (outage): same place, same height
            chartBox = new VisualElement { pickingMode = PickingMode.Ignore }; chartBox.AddToClassList("w22-en-box"); Add(chartBox);
            chart = new VisualElement { pickingMode = PickingMode.Ignore }; chart.AddToClassList("en-chart"); chart.generateVisualContent += DrawChart; chartBox.Add(chart);
            xr = new VisualElement { pickingMode = PickingMode.Ignore }; xr.AddToClassList("en-x"); chartBox.Add(xr);
            for (int y = C0; y <= C1; y++) xr.Add(L(y.ToString(), "en-xl"));
            cons = new VisualElement { pickingMode = PickingMode.Ignore }; cons.AddToClassList("w22-en-cons"); chartBox.Add(cons);
            cPeople = Fig(cons, "жителей без света"); cSchools = Fig(cons, "школ и детсадов"); cHealth = Fig(cons, "больниц и клиник");
            cons.style.display = DisplayStyle.None;

            var src = SourceTags.Line(TwinModels.Loads); src.AddToClassList("w22-en-src"); Add(src);
        }
        static Label L(string t, string cls) { var l = new Label(t) { pickingMode = PickingMode.Ignore }; l.AddToClassList(cls); return l; }
        static Label Fig(VisualElement parent, string label)
        {
            var f = new VisualElement { pickingMode = PickingMode.Ignore }; f.AddToClassList("w22-en-fig"); parent.Add(f);
            var v = L("—", "w22-en-fv"); f.Add(v); f.Add(L(label, "w22-en-fl")); return v;
        }

        public void Refresh()
        {
            float yf = e.YearF; int y = Mathf.FloorToInt(yf + 0.0001f); float u = e.Util(yf); int ph = e.Phase;
            year.text = y.ToString();
            dem.text = string.Format("{0} МВт", Mathf.RoundToInt(e.DemandF(yf))); cap.text = string.Format("{0} МВт", Mathf.RoundToInt(e.Cap(y)));
            pct.text = string.Format("{0} %", Mathf.RoundToInt(u * 100f));
            pct.style.color = Col(u);                         // the gauge is the one red figure; the rest stays white
            EnableInClassList("over", ph == 2 || ph == 3);

            if (ph != shownPhase)
            {
                shownPhase = ph;
                switch (ph)
                {
                    case 0: Say("Вечер. Свет горит у всех", "Энергия идёт от подстанции 220 кВ по районам Golden", Muted); break;
                    case 1: Say("Город растёт — растёт и спрос", "Новые дома, школы и клиники включают свет вечером", Muted); break;
                    case 2: Say(string.Format("Пик {0}: мощности не хватает", TourEnergy.YBad), "Подстанция перегружена — защита отключила часть района", TourEnergy.Red); break;
                    case 3: Say("QTwin увидел это за 8 лет — в 2026 году", string.Format("Решение: 2‑я очередь подстанции в {0}, а не в {1}", TourEnergy.YFixFrom, e.PlannedStage2), TourEnergy.Amber); break;
                    default: Say("Свет снова у всех", "2‑я очередь подстанции введена на 3 года раньше", TourEnergy.Green); break;
                }
            }
            if (ph == 4) status.text = string.Format("Свет снова у всех · запас {0} %", Mathf.RoundToInt((1f - u) * 100f));

            // the consequence takes the chart's place from a moment after the outage until the answer
            bool showCons = ph == 2 && e.T >= TourEnergy.TCons;
            chart.style.display = xr.style.display = showCons ? DisplayStyle.None : DisplayStyle.Flex;
            cons.style.display = showCons ? DisplayStyle.Flex : DisplayStyle.None;
            if (showCons)
            {
                cPeople.text = e.OutPeople >= 1000 ? string.Format("≈ {0} тыс.", Loc.N0(e.OutPeople / 1000f)) : string.Format("≈ {0}", Loc.N0(e.OutPeople));
                cSchools.text = Loc.N0(e.OutSchools); cHealth.text = Loc.N0(e.OutHealth);
            }
            gauge.MarkDirtyRepaint(); chart.MarkDirtyRepaint();
        }
        static readonly Color Muted = new Color(0.86f, 0.88f, 0.91f);
        void Say(string answer, string line, Color c) { status.text = answer; status.style.color = c; sub.text = line; }
        static Color Col(float u) => u < 0.85f ? TourEnergy.Blue : u <= 1f ? TourEnergy.Amber : TourEnergy.Red;

        void DrawGauge(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D; var r = gauge.contentRect; if (r.width <= 0) return;
            var c = new Vector2(r.width * 0.5f, r.height - 6f); float R = Mathf.Min(r.width * 0.5f - 8f, r.height - 14f);
            float u = e.Util(e.YearF), f = Mathf.Clamp01(u / 1.25f);
            p.lineCap = LineCap.Round; p.lineWidth = 11f;
            p.strokeColor = new Color(1, 1, 1, 0.08f); p.BeginPath(); p.Arc(c, R, 180f, 360f); p.Stroke();
            // the 100 % mark
            float a100 = 180f + 180f * (1f / 1.25f);
            p.strokeColor = new Color(1f, 0.3f, 0.25f, 0.35f); p.BeginPath(); p.Arc(c, R, a100, 360f); p.Stroke();
            p.strokeColor = Col(u); p.BeginPath(); p.Arc(c, R, 180f, 180f + 180f * Mathf.Max(f, 0.01f)); p.Stroke();
            var m = c + new Vector2(Mathf.Cos(a100 * Mathf.Deg2Rad), Mathf.Sin(a100 * Mathf.Deg2Rad)) * (R + 10f);
            var m2 = c + new Vector2(Mathf.Cos(a100 * Mathf.Deg2Rad), Mathf.Sin(a100 * Mathf.Deg2Rad)) * (R - 10f);
            p.lineWidth = 2f; p.lineCap = LineCap.Butt; p.strokeColor = new Color(1, 1, 1, 0.6f); p.BeginPath(); p.MoveTo(m2); p.LineTo(m); p.Stroke();
        }

        void DrawChart(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D; var r = chart.contentRect; float w = r.width, h = r.height; if (w <= 0 || h <= 0) return;
            int n = C1 - C0 + 1; float slot = w / n, bw = slot * 0.5f, max = 260f;
            float Y(float v) => h - 2f - (h - 6f) * Mathf.Clamp01(v / max);
            float yf = e.YearF; int yNow = Mathf.FloorToInt(yf);
            for (int i = 0; i < n; i++)
            {
                int y = C0 + i; float d = e.Demand(y); float x = slot * (i + 0.5f);
                bool shown = y <= yNow || e.Phase >= 2;              // from the outage on, the forecast years are shown too
                var c = Col(d / Mathf.Max(e.Cap(y), 1f));
                p.fillColor = new Color(c.r, c.g, c.b, shown ? (y <= yNow ? 0.9f : 0.55f) : 0.14f);
                float top = Y(d);
                p.BeginPath(); p.MoveTo(new Vector2(x - bw / 2, top)); p.LineTo(new Vector2(x + bw / 2, top)); p.LineTo(new Vector2(x + bw / 2, h - 2f)); p.LineTo(new Vector2(x - bw / 2, h - 2f)); p.ClosePath(); p.Fill();
            }
            // capacity: white step line
            p.strokeColor = new Color(1, 1, 1, 0.85f); p.lineWidth = 2f; p.lineJoin = LineJoin.Miter; p.BeginPath();
            for (int i = 0; i < n; i++)
            {
                float cy = Y(e.Cap(C0 + i)); float x0 = slot * i, x1 = slot * (i + 1);
                if (i == 0) p.MoveTo(new Vector2(x0, cy)); else p.LineTo(new Vector2(x0, cy));
                p.LineTo(new Vector2(x1, cy));
            }
            p.Stroke();
            // now
            float xn = slot * (Mathf.Clamp(yf, C0, C1) - C0 + 0.5f);
            p.strokeColor = new Color(1, 1, 1, 0.35f); p.lineWidth = 1f;
            for (float yy = 0; yy < h; yy += 6) { p.BeginPath(); p.MoveTo(new Vector2(xn, yy)); p.LineTo(new Vector2(xn, Mathf.Min(yy + 3, h))); p.Stroke(); }
        }
    }
}
