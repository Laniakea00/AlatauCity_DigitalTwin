using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Light stacked-area / line chart on Painter2D (no package dependency). X axis = years TwinState.MinYear..MaxYear (series that start earlier, from 2025, are cut to it).
    /// Series[s][i] are raw values per year; they are stacked bottom-up. A vertical marker shows the current year.</summary>
    public class TwinChart : VisualElement
    {
        public float[][] Series = new float[0][];
        public Color[] Colors = new Color[0];
        public bool Stacked = true;
        public bool Bars;                 // stacked columns per year instead of areas
        public float[] LineWidths;        // optional per-series line width (line mode)
        public int HighlightIndex = -1;   // bar to emphasise (current year)
        public bool[] Alerts;             // years to flag (red marks under the plot), index = year - (MaxYear - length + 1)
        public bool StepLast;             // draw the last series as steps (capacity comes in stages)
        public int MarkYear = -1;
        public string Unit = "";
        public string[] XText;            // optional x labels (evenly spaced) instead of years — e.g. hours of an incident
        public float MarkFrac = -1;
        public float YMin = 0;            // optional lower bound of the value axis (e.g. temperatures)       // optional marker position 0..1 (used with XText)
        const float PadL = 34f, PadR = 6f, PadT = 6f, PadB = 18f;
        readonly Label[] yLabels = new Label[3]; readonly Label[] xLabels = new Label[4];
        static readonly int[] XYears = { TwinState.MinYear, 2030, 2040, 2050 };
        const float Span = TwinState.MaxYear - TwinState.MinYear;
        /// <summary>The series as drawn: year series end in MaxYear; the years before MinYear are left out.</summary>
        float[][] View()
        {
            if (Series == null || Series.Length == 0 || XText != null) return Series ?? new float[0][];
            int n = Series[0].Length, k0 = Mathf.Max(0, n - (TwinState.MaxYear - TwinState.MinYear + 1)); if (k0 == 0) return Series;
            var v = new float[Series.Length][]; for (int s = 0; s < v.Length; s++) { v[s] = new float[Series[s].Length - k0]; System.Array.Copy(Series[s], k0, v[s], 0, v[s].Length); }
            return v;
        }
        bool[] AlertsView(int n)
        {
            if (Alerts == null || XText != null || Series == null || Series.Length == 0) return Alerts;
            int k0 = Series[0].Length - n; if (k0 <= 0) return Alerts;
            var a = new bool[Mathf.Max(0, Alerts.Length - k0)]; System.Array.Copy(Alerts, k0, a, 0, a.Length); return a;
        }
        Color line = new Color(0.165f, 0.165f, 0.165f), muted = new Color(0.53f, 0.53f, 0.53f), text = new Color(0.99f, 0.988f, 0.988f);

        public TwinChart()
        {
            AddToClassList("chart"); pickingMode = PickingMode.Ignore;
            generateVisualContent += Draw;
            for (int i = 0; i < 3; i++) { yLabels[i] = Mk(); yLabels[i].style.width = PadL - 4; yLabels[i].style.unityTextAlign = TextAnchor.MiddleRight; }
            for (int i = 0; i < 4; i++) { xLabels[i] = Mk(); xLabels[i].style.width = 40; xLabels[i].style.unityTextAlign = TextAnchor.UpperCenter; }
            RegisterCallback<GeometryChangedEvent>(_ => Layout());
        }
        Label Mk() { var l = new Label { pickingMode = PickingMode.Ignore }; l.style.position = Position.Absolute; l.style.fontSize = 10; l.style.color = muted; Add(l); return l; }

        public void Refresh() { Layout(); MarkDirtyRepaint(); }

        float MaxValue()
        {
            var Ser = View(); float m = 0; int n = Ser.Length > 0 ? Ser[0].Length : 0;
            for (int i = 0; i < n; i++) { float sum = 0; foreach (var s in Ser) { if (Stacked || Bars) sum += s[i]; else sum = Mathf.Max(sum, s[i]); } m = Mathf.Max(m, sum); }
            return m <= 0 ? 1 : m;
        }
        static float Nice(float v) { if (v <= 0) return 1; float p = Mathf.Pow(10, Mathf.Floor(Mathf.Log10(v))); float f = v / p; float n = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5f ? 2.5f : f <= 5 ? 5 : 10; return n * p; }

        void Layout()
        {
            float w = resolvedStyle.width, h = resolvedStyle.height; if (w <= 0 || h <= 0) return;
            float max = Nice(MaxValue()); float ph = h - PadT - PadB;
            for (int i = 0; i < 3; i++) { float v = YMin + (max - YMin) * (2 - i) / 2f; yLabels[i].text = v >= 100 ? v.ToString("0") : v.ToString("0.#"); yLabels[i].style.left = 0; yLabels[i].style.top = PadT + ph * i / 2f - 7; }
            float pw = w - PadL - PadR;
            for (int i = 0; i < 4; i++)
            {
                float f = XText != null ? i / 3f : (XYears[i] - TwinState.MinYear) / Span; float x = PadL + pw * f;
                xLabels[i].text = XText != null ? (i < XText.Length ? XText[i] : "") : XYears[i].ToString(); xLabels[i].style.left = x - 20; xLabels[i].style.top = h - PadB + 3;
            }
        }

        void Draw(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D; float w = contentRect.width, h = contentRect.height; if (w <= 0 || h <= 0) return;
            float pw = w - PadL - PadR, ph = h - PadT - PadB; float max = Nice(MaxValue());
            var Ser = View(); int n = Ser.Length > 0 ? Ser[0].Length : 0; var Al = AlertsView(n);
            // grid
            p.strokeColor = line; p.lineWidth = 1;
            for (int i = 0; i < 3; i++) { float y = PadT + ph * i / 2f; p.BeginPath(); p.MoveTo(new Vector2(PadL, y)); p.LineTo(new Vector2(PadL + pw, y)); p.Stroke(); }
            if (n < 2) return;
            float X(int i) => PadL + pw * i / (n - 1f); float Y(float v) => PadT + ph * (1 - Mathf.Clamp01((v - YMin) / Mathf.Max(max - YMin, 1e-3f)));
            var acc = new float[n];
            if (Bars)
            {
                float bw = Mathf.Max(2f, pw / n * 0.68f);
                for (int s = 0; s < Ser.Length; s++)
                {
                    var c = s < Colors.Length ? Colors[s] : Color.gray; var ser = Ser[s];
                    for (int i = 0; i < n; i++)
                    {
                        if (ser[i] <= 0) continue;
                        float x = X(i) - bw / 2, y0 = Y(acc[i]), y1 = Y(acc[i] + ser[i]); acc[i] += ser[i];
                        p.fillColor = new Color(c.r, c.g, c.b, HighlightIndex < 0 || HighlightIndex == i ? 0.95f : 0.45f);
                        p.BeginPath(); p.MoveTo(new Vector2(x, y1)); p.LineTo(new Vector2(x + bw, y1)); p.LineTo(new Vector2(x + bw, y0)); p.LineTo(new Vector2(x, y0)); p.ClosePath(); p.Fill();
                    }
                }
            }
            else
            for (int s = 0; s < Ser.Length; s++)
            {
                var c = s < Colors.Length ? Colors[s] : Color.gray; var ser = Ser[s];
                if (Stacked)
                {
                    p.fillColor = new Color(c.r, c.g, c.b, 0.85f); p.BeginPath();
                    p.MoveTo(new Vector2(X(0), Y(acc[0] + ser[0])));
                    for (int i = 1; i < n; i++) p.LineTo(new Vector2(X(i), Y(acc[i] + ser[i])));
                    for (int i = n - 1; i >= 0; i--) p.LineTo(new Vector2(X(i), Y(acc[i])));
                    p.ClosePath(); p.Fill();
                    for (int i = 0; i < n; i++) acc[i] += ser[i];
                }
                else
                {
                    p.strokeColor = c; p.lineWidth = LineWidths != null && s < LineWidths.Length ? LineWidths[s] : 2; p.lineJoin = LineJoin.Round; p.BeginPath(); p.MoveTo(new Vector2(X(0), Y(ser[0])));
                    bool step = StepLast && s == Ser.Length - 1;
                    for (int i = 1; i < n; i++) { if (step) p.LineTo(new Vector2(X(i), Y(ser[i - 1]))); p.LineTo(new Vector2(X(i), Y(ser[i]))); }
                    p.Stroke();
                }
            }
            if (Al != null)
            {
                p.fillColor = new Color(1f, 0.23f, 0.18f, 0.9f);
                for (int i = 0; i < Al.Length && i < n; i++)
                {
                    if (!Al[i]) continue; float x = X(i), bw2 = Mathf.Max(2f, pw / n * 0.42f);
                    p.BeginPath(); p.MoveTo(new Vector2(x - bw2, PadT + ph - 4)); p.LineTo(new Vector2(x + bw2, PadT + ph - 4)); p.LineTo(new Vector2(x + bw2, PadT + ph)); p.LineTo(new Vector2(x - bw2, PadT + ph)); p.ClosePath(); p.Fill();
                }
            }
            // current-year marker (dashed)
            if ((XText == null && MarkYear >= TwinState.MinYear && MarkYear <= TwinState.MaxYear) || (XText != null && MarkFrac >= 0))
            {
                float x = PadL + pw * (XText != null ? Mathf.Clamp01(MarkFrac) : (MarkYear - TwinState.MinYear) / Span); p.strokeColor = new Color(text.r, text.g, text.b, 0.55f); p.lineWidth = 1;
                for (float y = PadT; y < PadT + ph; y += 6) { p.BeginPath(); p.MoveTo(new Vector2(x, y)); p.LineTo(new Vector2(x, Mathf.Min(y + 3, PadT + ph))); p.Stroke(); }
            }
            // axis
            p.strokeColor = muted; p.BeginPath(); p.MoveTo(new Vector2(PadL, PadT + ph)); p.LineTo(new Vector2(PadL + pw, PadT + ph)); p.Stroke();
        }
    }
}
