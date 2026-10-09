using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Card of the presentation step «Прогноз: энергия 2034»: the year, a load gauge of ПС 220 кВ «Golden», peak demand vs capacity,
    /// a small 2028–2036 chart (demand bars, capacity step) and one status line that tells the story: growth → overload → forecast → solution.</summary>
    public class EnergyPanel : VisualElement
    {
        readonly TourEnergy e;
        readonly Label year, pct, dem, cap, status, warn, fix;
        readonly VisualElement gauge, chart;
        const int C0 = 2028, C1 = 2036;

        public EnergyPanel(TourEnergy en)
        {
            e = en; AddToClassList("en-card"); pickingMode = PickingMode.Ignore;
            var h = L("ПРОГНОЗ ДВОЙНИКА · ЭНЕРГОСИСТЕМА GOLDEN", "en-h"); Add(h);
            var row = new VisualElement { pickingMode = PickingMode.Ignore }; row.AddToClassList("en-row"); Add(row);
            year = L("2028", "en-year"); row.Add(year);
            gauge = new VisualElement { pickingMode = PickingMode.Ignore }; gauge.AddToClassList("en-gauge"); gauge.generateVisualContent += DrawGauge; row.Add(gauge);
            pct = L("0 %", "en-pct"); gauge.Add(pct);
            var figs = new VisualElement { pickingMode = PickingMode.Ignore }; figs.AddToClassList("en-figs"); row.Add(figs);
            dem = L("", "en-v"); figs.Add(dem); figs.Add(L("спрос в вечерний пик", "en-l"));
            cap = L("", "en-v"); cap.style.marginTop = 6; figs.Add(cap); figs.Add(L("мощность ПС 220 кВ", "en-l"));
            chart = new VisualElement { pickingMode = PickingMode.Ignore }; chart.AddToClassList("en-chart"); chart.generateVisualContent += DrawChart; Add(chart);
            var xr = new VisualElement { pickingMode = PickingMode.Ignore }; xr.AddToClassList("en-x"); Add(xr);
            for (int y = C0; y <= C1; y++) { var l = L(y.ToString(), "en-xl"); xr.Add(l); }
            status = L("", "en-status"); Add(status);
            warn = L("Двойник видит это уже сегодня — за 8 лет до дефицита", "en-warn"); warn.style.display = DisplayStyle.None; Add(warn);
            fix = L("Решение: 2-я очередь ПС «Golden» на 3 года раньше — 2033 вместо 2036", "en-fix"); fix.style.display = DisplayStyle.None; Add(fix);
        }
        static Label L(string t, string cls) { var l = new Label(t) { pickingMode = PickingMode.Ignore }; l.AddToClassList(cls); return l; }

        public void Refresh()
        {
            float yf = e.YearF; int y = Mathf.FloorToInt(yf + 0.0001f); float u = e.Util(yf);
            year.text = y.ToString();
            int a = Mathf.FloorToInt(yf), b = Mathf.Min(a + 1, 2050);
            float d = Mathf.Lerp(e.Demand(a), e.Demand(b), yf - a);
            dem.text = Mathf.RoundToInt(d) + " МВт"; cap.text = Mathf.RoundToInt(e.Cap(y)) + " МВт";
            pct.text = Mathf.RoundToInt(u * 100f) + " %";
            var c = Col(u); pct.style.color = c; dem.style.color = u > 1f ? TourEnergy.Red : Color.white;
            bool over = u > 1f && !e.Fixed;
            if (e.T < 11.5f) { status.text = "Город растёт — растёт и спрос на электричество"; status.style.color = new Color(0.75f, 0.77f, 0.8f); }
            else if (!e.Fixed) { status.text = "Вечерний пик 2034: перегрузка " + Mathf.RoundToInt(u * 100f) + " %" + (e.OutPeople > 1000 ? " · ≈ " + Loc.N0(e.OutPeople / 1000f) + " тыс. жителей без света" : " · отключения"); status.style.color = TourEnergy.Red; }
            else { status.text = "Свет у всех · запас мощности " + Mathf.RoundToInt((1f - u) * 100f) + " %"; status.style.color = TourEnergy.Green; }
            warn.style.display = e.T >= 16.5f ? DisplayStyle.Flex : DisplayStyle.None;
            fix.style.display = e.Fixed ? DisplayStyle.Flex : DisplayStyle.None;
            EnableInClassList("over", over);
            gauge.MarkDirtyRepaint(); chart.MarkDirtyRepaint();
        }
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
            float yf = e.YearF;
            for (int i = 0; i < n; i++)
            {
                int y = C0 + i; float d = e.Demand(y); float x = slot * (i + 0.5f);
                float shown = y < Mathf.FloorToInt(yf) ? 1f : y == Mathf.FloorToInt(yf) ? 1f : y - yf < 1f ? Mathf.Clamp01(1f - (y - yf)) : 0f;
                var c = Col(d / Mathf.Max(e.Cap(y), 1f));
                p.fillColor = new Color(c.r, c.g, c.b, shown > 0.99f ? 0.9f : 0.18f);
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
