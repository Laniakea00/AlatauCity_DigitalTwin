using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The construction of the city in one card, two panels on one time axis: commissioning plan vs fact (mln m², cumulative) on
    /// top, money spent per year (bln ₸) as calm columns below. The fact line is drawn up to the shown year (smoothly while the
    /// year animates), the shortfall between plan and fact is shaded red, a dot and a dashed line mark "now". Painter2D, no packages.</summary>
    public class BuildChart : VisualElement
    {
        public float[] Plan = new float[0], Fact = new float[0];
        public float[][] Money = new float[0][];
        public Color[] MoneyColors = new Color[0];
        /// <summary>Shown year (fractional while animating), 2025..2050.</summary>
        public float Year { get => year; set { year = value; PlaceTags(); } }
        float year = 2050f;

        // two panels on one time axis: commissioning (cumulative, mln m²) on top, money per year (bln ₸) below, a gap between them
        const float PadL = 6f, PadR = 6f, PadT = 16f, PadB = 18f, Gap = 22f, TopK = 0.64f;
        static readonly Color Grid = new Color(1f, 1f, 1f, 0.06f), Muted = new Color(0.56f, 0.56f, 0.56f), White = new Color(0.98f, 0.98f, 0.98f),
                              PlanC = new Color(0.70f, 0.70f, 0.70f), GapC = new Color(1f, 0.33f, 0.27f), Bar = new Color(0.36f, 0.62f, 0.98f);
        readonly Label topT, botT, planL, factL; readonly Label[] xl = new Label[4];
        static readonly int[] XYears = { 2025, 2030, 2040, 2050 };

        public BuildChart()
        {
            AddToClassList("bchart"); pickingMode = PickingMode.Ignore; style.height = 214;
            generateVisualContent += Draw;
            topT = Mk(TextAnchor.UpperLeft, 300); botT = Mk(TextAnchor.UpperLeft, 300); topT.style.whiteSpace = WhiteSpace.NoWrap; botT.style.whiteSpace = WhiteSpace.NoWrap;
            planL = Mk(TextAnchor.MiddleRight, 60); factL = Mk(TextAnchor.MiddleLeft, 60); planL.text = "план"; factL.text = "факт"; factL.style.color = White;
            for (int i = 0; i < 4; i++) xl[i] = Mk(TextAnchor.UpperCenter, 40);
            RegisterCallback<GeometryChangedEvent>(_ => Layout());
        }
        Label Mk(TextAnchor a, float w) { var l = new Label { pickingMode = PickingMode.Ignore }; l.style.position = Position.Absolute; l.style.fontSize = 10; l.style.color = Muted; l.style.unityTextAlign = a; l.style.width = w; l.style.paddingLeft = l.style.paddingRight = 0; l.style.marginLeft = l.style.marginRight = 0; Add(l); return l; }

        public void Refresh() { Layout(); MarkDirtyRepaint(); }

        static float Nice(float v) { if (v <= 0) return 1; float p = Mathf.Pow(10, Mathf.Floor(Mathf.Log10(v))); float f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5f ? 2.5f : f <= 5 ? 5 : 10) * p; }
        float MaxM2() { float m = 0; foreach (var v in Plan) m = Mathf.Max(m, v); foreach (var v in Fact) m = Mathf.Max(m, v); return Nice(m); }
        float Total(int i) { float s = 0; foreach (var a in Money) if (i < a.Length) s += a[i]; return s; }
        float MaxMoney() { float m = 0; int n = Money.Length > 0 ? Money[0].Length : 0; for (int i = 0; i < n; i++) m = Mathf.Max(m, Total(i)); return Nice(m); }
        void Panels(float h, out float t0, out float t1, out float b0, out float b1)
        {
            float ph = h - PadT - PadB - Gap; t0 = PadT; t1 = PadT + ph * TopK; b0 = t1 + Gap; b1 = h - PadB;
        }

        void Layout()
        {
            float w = resolvedStyle.width, h = resolvedStyle.height; if (!(w > 0) || !(h > 0)) return;
            Panels(h, out float t0, out float t1, out float b0, out float b1);
            float mM = MaxM2(), mR = MaxMoney();
            topT.text = "ВВОД ПЛОЩАДЕЙ · до " + mM.ToString(mM >= 10 ? "0" : "0.#") + " млн м²"; topT.style.left = PadL; topT.style.top = t0 - 15;
            botT.text = "ДЕНЬГИ В ГОД · до " + (mR >= 1000 ? (mR / 1000f).ToString("0.#") + " трлн ₸" : mR.ToString("0") + " млрд ₸"); botT.style.left = PadL; botT.style.top = b0 - 15;
            float pw = w - PadL - PadR;
            for (int i = 0; i < 4; i++) { float x = PadL + pw * (XYears[i] - 2025) / 25f; xl[i].text = XYears[i].ToString(); xl[i].style.left = Mathf.Clamp(x - 20, -4, w - 36); xl[i].style.top = h - PadB + 3; }
            PlaceTags();
        }

        void PlaceTags()
        {
            float w = resolvedStyle.width, h = resolvedStyle.height; int n = Plan.Length; if (!(w > 0) || !(h > 0) || n < 2 || Fact.Length != n) { planL.text = factL.text = ""; return; }
            planL.text = "план"; factL.text = "факт";
            Panels(h, out float t0, out float t1, out _, out _); float pw = w - PadL - PadR, mM = MaxM2();
            float yi = Mathf.Clamp(Year - 2025f, 0f, n - 1f), xn = PadL + pw * yi / (n - 1f);
            int a = Mathf.FloorToInt(yi), b = Mathf.Min(a + 1, n - 1);
            float fy = t0 + (t1 - t0) * (1 - Mathf.Clamp01(Mathf.Lerp(Fact[a], Fact[b], yi - a) / mM));
            float py = t0 + (t1 - t0) * (1 - Mathf.Clamp01(Plan[n - 1] / mM));
            planL.style.left = w - PadR - 62; planL.style.top = py - 16;
            factL.style.left = Mathf.Min(xn + 10, w - 60); factL.style.top = fy - 8;
        }

        void Draw(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D; float w = contentRect.width, h = contentRect.height; if (w <= 0 || h <= 0) return;
            int n = Plan.Length; if (n < 2 || Fact.Length != n) return;
            Panels(h, out float t0, out float t1, out float b0, out float b1);
            float pw = w - PadL - PadR, mM = MaxM2(), mR = MaxMoney();
            float X(float i) => PadL + pw * i / (n - 1f);
            float Y(float v) => t0 + (t1 - t0) * (1 - Mathf.Clamp01(v / mM));
            float yi = Mathf.Clamp(Year - 2025f, 0f, n - 1f);
            float FactAt(float t) { int a = Mathf.FloorToInt(t), b = Mathf.Min(a + 1, n - 1); return Mathf.Lerp(Fact[a], Fact[b], t - a); }
            float PlanAt(float t) { int a = Mathf.FloorToInt(t), b = Mathf.Min(a + 1, n - 1); return Mathf.Lerp(Plan[a], Plan[b], t - a); }

            // ---- top: commissioning. faint grid, plan as a thin dashed line, fact as a white line with a soft area, the shortfall in red
            p.strokeColor = Grid; p.lineWidth = 1;
            for (int i = 0; i < 3; i++) { float y = t0 + (t1 - t0) * i * 0.5f; p.BeginPath(); p.MoveTo(new Vector2(PadL, y)); p.LineTo(new Vector2(PadL + pw, y)); p.Stroke(); }
            p.fillColor = new Color(GapC.r, GapC.g, GapC.b, 0.24f); p.BeginPath();
            p.MoveTo(new Vector2(X(0), Y(Plan[0])));
            for (int i = 1; i <= Mathf.FloorToInt(yi); i++) p.LineTo(new Vector2(X(i), Y(Plan[i])));
            p.LineTo(new Vector2(X(yi), Y(PlanAt(yi)))); p.LineTo(new Vector2(X(yi), Y(FactAt(yi))));
            for (int i = Mathf.FloorToInt(yi); i >= 0; i--) p.LineTo(new Vector2(X(i), Y(Fact[i])));
            p.ClosePath(); p.Fill();
            p.fillColor = new Color(1f, 1f, 1f, 0.06f); p.BeginPath(); p.MoveTo(new Vector2(X(0), t1));
            for (int i = 0; i <= Mathf.FloorToInt(yi); i++) p.LineTo(new Vector2(X(i), Y(Fact[i])));
            p.LineTo(new Vector2(X(yi), Y(FactAt(yi)))); p.LineTo(new Vector2(X(yi), t1)); p.ClosePath(); p.Fill();
            // plan: dashes along the whole horizon
            p.strokeColor = PlanC; p.lineWidth = 1.3f; float dashAcc = 0; bool on = true;
            for (int i = 1; i < n; i++)
            {
                Vector2 a0 = new Vector2(X(i - 1), Y(Plan[i - 1])), a1 = new Vector2(X(i), Y(Plan[i])); float L = (a1 - a0).magnitude, t = 0;
                while (t < L)
                {
                    float seg = Mathf.Min((on ? 5f : 3.5f) - dashAcc, L - t);
                    if (on) { p.BeginPath(); p.MoveTo(Vector2.Lerp(a0, a1, t / L)); p.LineTo(Vector2.Lerp(a0, a1, (t + seg) / L)); p.Stroke(); }
                    t += seg; dashAcc += seg; if (dashAcc >= (on ? 5f : 3.5f) - 1e-3f) { dashAcc = 0; on = !on; }
                }
            }
            p.strokeColor = White; p.lineWidth = 2.4f; p.lineJoin = LineJoin.Round; p.lineCap = LineCap.Round; p.BeginPath(); p.MoveTo(new Vector2(X(0), Y(Fact[0])));
            for (int i = 1; i <= Mathf.FloorToInt(yi); i++) p.LineTo(new Vector2(X(i), Y(Fact[i])));
            p.LineTo(new Vector2(X(yi), Y(FactAt(yi)))); p.Stroke();
            p.lineCap = LineCap.Butt;
            float xn = X(yi);
            p.fillColor = new Color(1, 1, 1, 0.16f); p.BeginPath(); p.Arc(new Vector2(xn, Y(FactAt(yi))), 8f, 0, 360); p.Fill();
            p.fillColor = White; p.BeginPath(); p.Arc(new Vector2(xn, Y(FactAt(yi))), 3.8f, 0, 360); p.Fill();

            // ---- bottom: money per year, one calm colour; the years passed are solid, the current one bright, the future a faint outline
            if (Money.Length > 0)
            {
                float slot = pw / n, bw = Mathf.Max(2f, slot * 0.62f), mh = b1 - b0;
                for (int i = 0; i < n; i++)
                {
                    float v = Total(i); if (v <= 0) continue;
                    bool now = Mathf.Abs(i - Mathf.Floor(yi)) < 0.5f, past = i < Mathf.Floor(yi);
                    float x = X(i) - bw * 0.5f, y = b1 - mh * Mathf.Clamp01(v / mR);
                    p.fillColor = now ? Bar : past ? new Color(Bar.r, Bar.g, Bar.b, 0.42f) : new Color(1f, 1f, 1f, 0.07f);
                    p.BeginPath(); p.MoveTo(new Vector2(x, y)); p.LineTo(new Vector2(x + bw, y)); p.LineTo(new Vector2(x + bw, b1)); p.LineTo(new Vector2(x, b1)); p.ClosePath(); p.Fill();
                }
                p.strokeColor = new Color(1, 1, 1, 0.12f); p.lineWidth = 1; p.BeginPath(); p.MoveTo(new Vector2(PadL, b1)); p.LineTo(new Vector2(PadL + pw, b1)); p.Stroke();
            }
            // "now" crosses both panels as one thin line: the same moment in the commissioning and in the money
            p.strokeColor = new Color(1, 1, 1, 0.30f); p.lineWidth = 1;
            for (float y = t0; y < b1; y += 6) { p.BeginPath(); p.MoveTo(new Vector2(xn, y)); p.LineTo(new Vector2(xn, Mathf.Min(y + 3, b1))); p.Stroke(); }
            p.strokeColor = new Color(1, 1, 1, 0.12f); p.BeginPath(); p.MoveTo(new Vector2(PadL, t1)); p.LineTo(new Vector2(PadL + pw, t1)); p.Stroke();
        }
    }
}
