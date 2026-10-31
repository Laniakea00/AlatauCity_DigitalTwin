using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Answer-first pieces for the analysis panels (design rules, stage 4): one hero number with its unit and a short caption,
    /// one quiet line under it, a strip of small secondary numbers, and «Ещё N» for long lists. Styles: the w19 block of Twin.uss.</summary>
    public static class Glance
    {
        /// <summary>The focal point of a block: a big number (or a short status word), its unit, a caption and at most one line of prose.</summary>
        public class Hero
        {
            public VisualElement Root; public Label Value, Unit, Caption, Line;
            public void Set(string value, string unit, string caption, string status = "", string line = null)
            {
                Value.text = value; Unit.text = unit ?? ""; Unit.style.display = string.IsNullOrEmpty(unit) ? DisplayStyle.None : DisplayStyle.Flex;
                Caption.text = caption ?? ""; Caption.style.display = string.IsNullOrEmpty(caption) ? DisplayStyle.None : DisplayStyle.Flex;
                Line.text = line ?? ""; Line.style.display = string.IsNullOrEmpty(line) ? DisplayStyle.None : DisplayStyle.Flex;
                foreach (var c in new[] { "ok", "warn", "bad" }) Value.EnableInClassList("w19-" + c, c == status);
            }
        }

        public static Hero MakeHero(VisualElement parent)
        {
            var h = new Hero { Root = new VisualElement() }; h.Root.AddToClassList("w19-hero");
            var row = new VisualElement(); row.AddToClassList("w19-hero-row"); h.Root.Add(row);
            h.Value = new Label("—"); h.Value.AddToClassList("w19-hero-v"); row.Add(h.Value);
            h.Unit = new Label(); h.Unit.AddToClassList("w19-hero-u"); row.Add(h.Unit);
            h.Caption = new Label(); h.Caption.AddToClassList("w19-hero-c"); h.Root.Add(h.Caption);
            h.Line = new Label(); h.Line.AddToClassList("w19-hero-l"); h.Root.Add(h.Line);
            parent.Add(h.Root); return h;
        }

        /// <summary>A row of small secondary numbers (value over label), muted next to the hero.</summary>
        public static VisualElement Strip(VisualElement parent)
        {
            var s = new VisualElement(); s.AddToClassList("w19-strip"); parent.Add(s); return s;
        }
        public static (Label v, Label l, VisualElement cell) Stat(VisualElement strip, string v = "—", string l = "")
        {
            var c = new VisualElement(); c.AddToClassList("w19-stat");
            var vl = new Label(v); vl.AddToClassList("w19-stat-v"); c.Add(vl);
            var ll = new Label(l); ll.AddToClassList("w19-stat-l"); c.Add(ll);
            strip.Add(c); return (vl, ll, c);
        }
        public static void SetStat((Label v, Label l, VisualElement cell) s, string v, string l, string status = "")
        {
            s.v.text = v; s.l.text = l;
            foreach (var c in new[] { "ok", "warn", "bad" }) s.v.EnableInClassList("w19-" + c, c == status);
        }

        /// <summary>One quiet line of prose (≈ 60 characters) under an answer.</summary>
        public static Label Line(VisualElement parent, string text = "")
        {
            var l = new Label(text); l.AddToClassList("w19-line"); parent.Add(l); return l;
        }

        /// <summary>Long explanation text inside a Details body.</summary>
        public static Label Prose(VisualElement parent, string text = "")
        {
            var l = new Label(text); l.AddToClassList("w19-prose"); parent.Add(l); return l;
        }

        /// <summary>Keeps the first n children of a list visible and folds the rest behind «Ещё N».</summary>
        public static void More(VisualElement list, int n)
        {
            int extra = list.childCount - n; if (extra <= 0) return;
            var moved = new System.Collections.Generic.List<VisualElement>();
            for (int i = n; i < list.childCount; i++) moved.Add(list[i]);
            foreach (var m in moved) list.Remove(m);
            var body = Widgets.Details(list, string.Format("Ещё {0}", extra));
            foreach (var m in moved) body.Add(m);
        }
    }
}
