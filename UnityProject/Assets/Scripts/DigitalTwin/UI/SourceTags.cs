using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Small chips that say where a number comes from. A source chip shows "Trend · 26.08.2026", a model chip shows
    /// "модель QTwin" in amber; a click opens the panel «Источники и допущения» at that entry.</summary>
    public static class SourceTags
    {
        /// <summary>A chip for a registered source or model (unknown id — a plain "модель QTwin" chip).</summary>
        public static VisualElement Tag(string id)
        {
            var s = Sources.Get(id) ?? Sources.Get(Sources.ModelSynthetic);
            var t = new Label(s != null ? s.Short : "модель QTwin"); t.AddToClassList("src-tag");
            if (s == null || s.Model) t.AddToClassList("model");
            t.tooltip = s == null ? "" : s.Title + (string.IsNullOrEmpty(s.Note) ? "" : "\n" + s.Note);
            var sid = s?.Id; t.AddManipulator(new Clickable(() => Sources.Open(sid)));
            return t;
        }
        /// <summary>The "модель QTwin" chip (the default model: synthetic demo data).</summary>
        public static VisualElement ModelTag(string id = null) => Tag(id ?? Sources.ModelSynthetic);

        /// <summary>A row of chips under a block: "Источники:" + one chip per id.</summary>
        public static VisualElement Line(params string[] ids)
        {
            var r = new VisualElement(); r.AddToClassList("src-line");
            var l = new Label("Источники:") { pickingMode = PickingMode.Ignore }; l.AddToClassList("src-cap"); r.Add(l);
            // two models read the same ("модель QTwin"): one chip, its tooltip names both
            var shown = new System.Collections.Generic.Dictionary<string, VisualElement>();
            foreach (var id in ids)
            {
                var s = Sources.Get(id); var key = s != null ? s.Short : id;
                if (shown.TryGetValue(key, out var first)) { if (s != null) first.tooltip += "\n\n" + s.Title + (string.IsNullOrEmpty(s.Note) ? "" : "\n" + s.Note); continue; }
                var t = Tag(id); shown[key] = t; r.Add(t);
            }
            return r;
        }
        /// <summary>Adds a chip to a KPI cell (an element with class "kpi"), under its value.</summary>
        public static VisualElement Attach(VisualElement kpi, string id) { var t = Tag(id); t.AddToClassList("in-kpi"); kpi.Add(t); return t; }
    }
}
