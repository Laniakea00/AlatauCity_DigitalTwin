using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The time of day of the twin, chosen from the header (the place / weather block): a slider 5:00–22:00, four presets and
    /// "Сутки за 2 минуты" (the day runs on its own until a time is picked). FilmLook moves the sun, the sky, the windows and the street
    /// lamps with the hour.</summary>
    public static class TimeOfDay
    {
        static readonly (string label, float hour)[] Presets = { ("Утро 8:00", 8f), ("День 13:00", 13f), ("Вечер 18:30", 18.5f), ("Ночь 21:30", 21.5f) };

        /// <summary>"18:30" for 18.5.</summary>
        public static string HourText(float h)
        {
            int m = Mathf.RoundToInt(h * 60f); return string.Format("{0}:{1:00}", m / 60, m % 60);
        }

        public static VisualElement BuildPopup()
        {
            var p = new VisualElement(); p.AddToClassList("popup"); p.AddToClassList("time-pop"); p.style.display = DisplayStyle.None; p.style.width = 330;
            var head = new VisualElement(); head.AddToClassList("time-head"); p.Add(head);
            var title = new Label("Время суток в двойнике"); title.AddToClassList("time-title"); head.Add(title);
            var big = new Label(HourText(FilmLook.Hour)); big.AddToClassList("time-big"); head.Add(big);
            var sub = new Label("Солнце, тени, небо, окна и уличные фонари следуют за часом. Это вид, а не расчёт освещённости.");
            sub.AddToClassList("time-sub"); p.Add(sub);

            var slider = new TwinSlider(new[] { 360, 720, 1080 }, m => string.Format("{0}:00", m / 60), 300, 1320);
            slider.AddToClassList("time-slider"); slider.Value = Mathf.RoundToInt(FilmLook.Hour * 60f);
            slider.OnChange = m => { FilmLook.SetHour(m / 60f); FilmLook.ViewerTime = true; };
            p.Add(slider);

            var row = new VisualElement(); row.AddToClassList("time-presets"); p.Add(row);
            var chips = new Label[Presets.Length];
            for (int i = 0; i < Presets.Length; i++)
            {
                var pr = Presets[i];
                var c = new Label(pr.label); c.AddToClassList("chip"); c.AddToClassList("time-chip");
                c.AddManipulator(new Clickable(() => { FilmLook.SetHour(pr.hour); FilmLook.ViewerTime = true; }));
                row.Add(c); chips[i] = c;
            }
            var cycle = new VisualElement(); cycle.AddToClassList("time-cycle"); p.Add(cycle);
            var cyc1 = new Label("Сутки за 2 минуты") { pickingMode = PickingMode.Ignore }; cyc1.AddToClassList("time-cycle-name"); cycle.Add(cyc1);
            var cyc2 = new Label("с 5:00 до 22:00 по кругу; любой выбор останавливает") { pickingMode = PickingMode.Ignore }; cyc2.AddToClassList("time-cycle-desc"); cycle.Add(cyc2);
            cycle.AddManipulator(new Clickable(() => { if (FilmLook.Cycling) FilmLook.Cycling = false; else FilmLook.StartCycle(); }));

            // follows the running day while the popup is open
            p.schedule.Execute(() =>
            {
                if (p.resolvedStyle.display == DisplayStyle.None) return;
                float h = FilmLook.Hour; big.text = HourText(h);
                int mins = Mathf.RoundToInt(h * 60f); if (slider.Value != mins) slider.Value = mins;
                cycle.EnableInClassList("active", FilmLook.Cycling);
                for (int i = 0; i < chips.Length; i++) chips[i].EnableInClassList("active", FilmLook.ViewerTime && !FilmLook.Cycling && Mathf.Abs(h - Presets[i].hour) < 0.02f);
            }).Every(200);
            return p;
        }
    }

    /// <summary>A small sun (day) or crescent moon (night) drawn for the header while the viewer has set the twin's time.</summary>
    public class SkyGlyph : VisualElement
    {
        float hour = 12f;
        static readonly Color Sun = new Color(0.94f, 0.76f, 0.35f), Moon = new Color(0.86f, 0.88f, 0.94f);
        public SkyGlyph()
        {
            pickingMode = PickingMode.Ignore; AddToClassList("sky-glyph"); style.width = 24; style.height = 24;
            generateVisualContent += ctx =>
            {
                var p = ctx.painter2D; var c = new Vector2(12, 12);
                if (IsDay(hour))
                {
                    p.fillColor = Sun; p.BeginPath(); p.Arc(c, 5f, 0f, 360f); p.Fill();
                    p.strokeColor = Sun; p.lineWidth = 1.6f; p.lineCap = LineCap.Round;
                    for (int i = 0; i < 8; i++)
                    {
                        float a = i * Mathf.PI / 4f; var d = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                        p.BeginPath(); p.MoveTo(c + d * 7.5f); p.LineTo(c + d * 10f); p.Stroke();
                    }
                }
                else
                {
                    // a crescent as one closed path: the outer arc of the moon, back along the inner arc of the shadow disc
                    var o = c + new Vector2(4.5f, -3f); const float R = 8f, r = 7f;
                    float dist = (o - c).magnitude, ang = Mathf.Atan2(o.y - c.y, o.x - c.x) * Mathf.Rad2Deg;
                    float a = Mathf.Acos(Mathf.Clamp((dist * dist + R * R - r * r) / (2f * dist * R), -1f, 1f)) * Mathf.Rad2Deg;     // half angle of the cut, at the moon's centre
                    float b = Mathf.Acos(Mathf.Clamp((dist * dist + r * r - R * R) / (2f * dist * r), -1f, 1f)) * Mathf.Rad2Deg;     // the same at the shadow's centre
                    p.fillColor = Moon; p.BeginPath();
                    p.Arc(c, R, Angle.Degrees(ang + a), Angle.Degrees(ang + 360f - a));
                    p.Arc(o, r, Angle.Degrees(ang + 180f + b), Angle.Degrees(ang + 180f - b), ArcDirection.CounterClockwise);
                    p.ClosePath(); p.Fill();
                }
            };
        }
        public static bool IsDay(float h) => h >= 6f && h < 19.5f;
        public void SetHour(float h) { if (IsDay(h) != IsDay(hour)) { hour = h; MarkDirtyRepaint(); } else hour = h; }
    }
}
