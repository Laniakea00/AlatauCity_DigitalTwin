using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Small reusable UI pieces in the QazTWIN style.</summary>
    public static class Widgets
    {
        /// <summary>A floating card of the right column (title + optional subtitle). Returns the card; add content to it.</summary>
        public static VisualElement Block(VisualElement parent, string title = null, string sub = null)
        {
            var b = new VisualElement(); b.AddToClassList("block");
            if (!string.IsNullOrEmpty(title) || !string.IsNullOrEmpty(sub))
            {
                var h = new VisualElement(); h.AddToClassList("block-head");
                var t = new Label(title ?? ""); t.AddToClassList("block-title"); h.Add(t);
                if (!string.IsNullOrEmpty(sub)) { var s = new Label(sub); s.AddToClassList("block-sub"); h.Add(s); }
                b.Add(h);
                if (!string.IsNullOrWhiteSpace(title))
                {
                    // click on the title folds the block (less on screen at once)
                    var ch = new Chevron(); ch.AddToClassList("chev"); h.Add(ch);
                    h.AddManipulator(new Clickable(() => SetCollapsed(b, !b.ClassListContains("collapsed"))));
                }
            }
            parent.Add(b); return b;
        }
        public static void SetCollapsed(VisualElement block, bool on)
        {
            block.EnableInClassList("collapsed", on);
            foreach (var c in block.Children()) if (!c.ClassListContains("block-head")) c.style.display = on ? DisplayStyle.None : DisplayStyle.Flex;
            var ch = block.Q<Chevron>(); if (ch != null) ch.style.rotate = new Rotate(new Angle(on ? -90f : 0f));
        }

        /// <summary>Journal card like the qTwin "Оперативный журнал": source icon + title, severity badge, text, action and time.</summary>
        public static VisualElement JournalCard(string icon, string source, string level, string badge, string text, string time, string action = null, System.Action onAction = null)
        {
            var c = new VisualElement(); c.AddToClassList("jcard"); if (!string.IsNullOrEmpty(level)) c.AddToClassList(level);
            var h = new VisualElement(); h.AddToClassList("jh"); c.Add(h);
            var ic = TwinUI.Icon(icon, 16); ic.style.unityBackgroundImageTintColor = level == "bad" ? new Color(1f, 0.36f, 0.31f) : level == "warn" ? new Color(0.96f, 0.65f, 0.14f) : level == "ok" ? new Color(0.20f, 0.78f, 0.35f) : new Color(0.61f, 0.74f, 1f);
            h.Add(ic);
            var s = new Label(source) { pickingMode = PickingMode.Ignore }; s.AddToClassList("src"); h.Add(s);
            if (!string.IsNullOrEmpty(badge)) { var bd = new Label(badge) { pickingMode = PickingMode.Ignore }; bd.AddToClassList("jbadge"); bd.AddToClassList(level); h.Add(bd); }
            var t = new Label(text) { pickingMode = PickingMode.Ignore }; t.AddToClassList("jt"); c.Add(t);
            if (!string.IsNullOrEmpty(action) || !string.IsNullOrEmpty(time))
            {
                var f = new VisualElement(); f.AddToClassList("jf"); c.Add(f);
                if (!string.IsNullOrEmpty(action))
                {
                    var b = new VisualElement(); b.AddToClassList("jbtn"); b.Add(TwinUI.Icon("play", 10));
                    b.Add(new Label(action) { pickingMode = PickingMode.Ignore }); if (onAction != null) b.AddManipulator(new Clickable(onAction)); f.Add(b);
                }
                var tm = new Label(time ?? "") { pickingMode = PickingMode.Ignore }; tm.AddToClassList("jtime"); f.Add(tm);
            }
            return c;
        }

        /// <summary>Segmented meter red → amber → green (load, readiness), filled up to value 0..1.</summary>
        public static VisualElement Meter(VisualElement parent, float value, bool goodIsHigh = true, int n = 30)
        {
            var m = new VisualElement(); m.AddToClassList("meter"); parent.Add(m);
            for (int i = 0; i < n; i++)
            {
                float f = i / (n - 1f); float q = goodIsHigh ? f : 1 - f;
                var c = q < 0.5f ? Color.Lerp(new Color(0.93f, 0.22f, 0.20f), new Color(0.96f, 0.72f, 0.15f), q * 2) : Color.Lerp(new Color(0.96f, 0.72f, 0.15f), new Color(0.22f, 0.76f, 0.36f), (q - 0.5f) * 2);
                bool on = (i + 0.5f) / n <= value; if (!on) c = new Color(0.16f, 0.16f, 0.16f);
                var sg = new VisualElement { pickingMode = PickingMode.Ignore }; sg.AddToClassList("seg"); sg.style.backgroundColor = c; m.Add(sg);
            }
            var sc = new VisualElement { pickingMode = PickingMode.Ignore }; sc.AddToClassList("meter-scale"); parent.Add(sc);
            sc.Add(new Label("0%")); sc.Add(new Label("50%")); sc.Add(new Label("100%"));
            return m;
        }
        public static void SetMeter(VisualElement m, float value, bool goodIsHigh = true)
        {
            int n = m.childCount, i = 0;
            foreach (var sg in m.Children())
            {
                float f = i / (n - 1f); float q = goodIsHigh ? f : 1 - f;
                var c = q < 0.5f ? Color.Lerp(new Color(0.93f, 0.22f, 0.20f), new Color(0.96f, 0.72f, 0.15f), q * 2) : Color.Lerp(new Color(0.96f, 0.72f, 0.15f), new Color(0.22f, 0.76f, 0.36f), (q - 0.5f) * 2);
                sg.style.backgroundColor = (i + 0.5f) / n <= value ? c : new Color(0.16f, 0.16f, 0.16f); i++;
            }
        }

        /// <summary>Small uppercase caption with the red qTwin pin (as on qtwin.io).</summary>
        public static Label Eyebrow(VisualElement parent, string text)
        {
            var e = new VisualElement { pickingMode = PickingMode.Ignore }; e.AddToClassList("eyebrow");
            var pin = new VisualElement { pickingMode = PickingMode.Ignore }; pin.AddToClassList("pin"); e.Add(pin);
            var l = new Label(text.ToUpperInvariant()) { pickingMode = PickingMode.Ignore }; e.Add(l); parent.Add(e); return l;
        }
        public static VisualElement Dot(Color c, bool round = false)
        {
            var d = new VisualElement { pickingMode = PickingMode.Ignore }; d.AddToClassList("dot"); if (round) d.AddToClassList("round"); d.style.backgroundColor = c; return d;
        }
        public static VisualElement LegendItem(Color c, string text)
        {
            var li = new VisualElement { pickingMode = PickingMode.Ignore }; li.AddToClassList("legend-item"); li.Add(Dot(c));
            var l = new Label(text) { pickingMode = PickingMode.Ignore }; l.AddToClassList("small"); l.AddToClassList("muted"); li.Add(l); return li;
        }
        public static Label Cell(string text, string cls) { var l = new Label(text); l.AddToClassList(cls); l.pickingMode = PickingMode.Ignore; return l; }
        public static VisualElement Fact(string k, string v)
        {
            var f = new VisualElement(); f.AddToClassList("fact");
            var kl = new Label(k); kl.AddToClassList("k"); f.Add(kl);
            var vl = new Label(v); vl.AddToClassList("v"); f.Add(vl); return f;
        }
        public static Button Btn(string text, System.Action onClick, params string[] classes)
        {
            var b = new Button(onClick) { text = text, focusable = false }; b.AddToClassList("btn"); foreach (var c in classes) b.AddToClassList(c); return b;
        }
        public static Label Status(string text, string cls) { var l = new Label(text); l.AddToClassList("status"); l.AddToClassList(cls); return l; }
    }

    /// <summary>Small "v" chevron drawn with Painter2D (the brand font has no arrow-head glyphs).</summary>
    public class Chevron : VisualElement
    {
        public Color Color = new Color(0.53f, 0.53f, 0.53f);
        public Chevron()
        {
            pickingMode = PickingMode.Ignore; style.width = 10; style.height = 10;
            generateVisualContent += ctx =>
            {
                var p = ctx.painter2D; p.strokeColor = Color; p.lineWidth = 1.5f; p.lineCap = LineCap.Round; p.lineJoin = LineJoin.Round;
                p.BeginPath(); p.MoveTo(new Vector2(2, 3.5f)); p.LineTo(new Vector2(5, 6.5f)); p.LineTo(new Vector2(8, 3.5f)); p.Stroke();
            };
        }
    }
}
