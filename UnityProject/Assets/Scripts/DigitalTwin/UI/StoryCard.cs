using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>What a presentation step shows on its dashboard: a short headline, up to three big figures, an optional list
    /// (name — value with a bar or a colour chip; legend rows are dim until lit) and a one-line note. Kept short on purpose:
    /// it follows the presenter's text, it does not replace it.</summary>
    public class Story
    {
        public string Eyebrow, Head, Note;
        public (string v, string l, Color c)[] Kpi;
        public List<Row> Rows;
        public class Row { public string Name, Value; public Color C; public float Frac = -1f; public bool Dim; }
        public Story K(string v, string l, Color? c = null) { var a = new List<(string, string, Color)>(Kpi ?? new (string, string, Color)[0]) { (v, l, c ?? Color.white) }; Kpi = a.ToArray(); return this; }
        public Story R(string name, string value, Color c, float frac = -1f, bool dim = false) { (Rows ??= new List<Row>()).Add(new Row { Name = name, Value = value, C = c, Frac = frac, Dim = dim }); return this; }
    }

    /// <summary>The step dashboard of the presentation: a card in the right column above the caption (TwinTour keeps it there).</summary>
    public class StoryCard : VisualElement
    {
        public static StoryCard Instance;
        readonly Label eyebrow, head, note; readonly VisualElement kpis, rows;
        Func<Story> src; float next;
        /// <summary>Legend rows lit by the presentation's spotlight (name → count).</summary>
        readonly Dictionary<string, string> lit = new Dictionary<string, string>();

        public StoryCard()
        {
            Instance = this; AddToClassList("story"); pickingMode = PickingMode.Ignore;
            eyebrow = new Label { pickingMode = PickingMode.Ignore }; eyebrow.AddToClassList("story-eye"); Add(eyebrow);
            head = new Label { pickingMode = PickingMode.Ignore }; head.AddToClassList("story-head"); Add(head);
            kpis = new VisualElement { pickingMode = PickingMode.Ignore }; kpis.AddToClassList("story-kpis"); Add(kpis);
            rows = new VisualElement { pickingMode = PickingMode.Ignore }; rows.AddToClassList("story-rows"); Add(rows);
            note = new Label { pickingMode = PickingMode.Ignore }; note.AddToClassList("story-note"); Add(note);
            style.display = DisplayStyle.None;
        }

        public void Show(Func<Story> f) { src = f; lit.Clear(); next = 0; Refresh(); }
        public void Hide() { src = null; style.display = DisplayStyle.None; }
        public static void Light(string name, int count) { if (Instance == null) return; Instance.lit[name] = Loc.N0(count); Instance.Refresh(); }

        /// <summary>Called every frame by the presentation: live figures (year, progress) are refreshed twice a second.</summary>
        public void Tick() { if (src == null) return; next -= Time.unscaledDeltaTime; if (next <= 0f) Refresh(); }

        void Refresh()
        {
            next = 0.5f;
            Story s = null; try { s = src?.Invoke(); } catch (Exception e) { Debug.LogWarning("[Alatau] story: " + e.Message); }
            if (s == null) { style.display = DisplayStyle.None; return; }
            style.display = DisplayStyle.Flex;
            eyebrow.text = (s.Eyebrow ?? "").ToUpperInvariant(); eyebrow.style.display = string.IsNullOrEmpty(s.Eyebrow) ? DisplayStyle.None : DisplayStyle.Flex;
            head.text = s.Head ?? ""; head.style.display = string.IsNullOrEmpty(s.Head) ? DisplayStyle.None : DisplayStyle.Flex;
            note.text = s.Note ?? ""; note.style.display = string.IsNullOrEmpty(s.Note) ? DisplayStyle.None : DisplayStyle.Flex;
            kpis.Clear(); kpis.style.display = s.Kpi != null && s.Kpi.Length > 0 ? DisplayStyle.Flex : DisplayStyle.None;
            if (s.Kpi != null)
                foreach (var (v, l, c) in s.Kpi)
                {
                    var f = new VisualElement { pickingMode = PickingMode.Ignore }; f.AddToClassList("story-kpi");
                    var vl = new Label(v) { pickingMode = PickingMode.Ignore }; vl.AddToClassList("story-v"); vl.style.color = c; f.Add(vl);
                    var ll = new Label(l) { pickingMode = PickingMode.Ignore }; ll.AddToClassList("story-l"); f.Add(ll);
                    kpis.Add(f);
                }
            rows.Clear(); rows.style.display = s.Rows != null && s.Rows.Count > 0 ? DisplayStyle.Flex : DisplayStyle.None;
            if (s.Rows != null)
                foreach (var r in s.Rows)
                {
                    bool on = !r.Dim || lit.ContainsKey(r.Name);
                    var row = new VisualElement { pickingMode = PickingMode.Ignore }; row.AddToClassList("story-row"); row.EnableInClassList("dim", !on);
                    var top = new VisualElement { pickingMode = PickingMode.Ignore }; top.AddToClassList("story-rtop"); row.Add(top);
                    var chip = new VisualElement { pickingMode = PickingMode.Ignore }; chip.AddToClassList("story-chip"); chip.style.backgroundColor = r.C; top.Add(chip);
                    var n = new Label(r.Name) { pickingMode = PickingMode.Ignore }; n.AddToClassList("story-rn"); top.Add(n);
                    var val = new Label(r.Dim ? (lit.TryGetValue(r.Name, out var cnt) ? cnt : "") : r.Value ?? "") { pickingMode = PickingMode.Ignore }; val.AddToClassList("story-rv"); top.Add(val);
                    if (r.Frac >= 0f)
                    {
                        var tr = new VisualElement { pickingMode = PickingMode.Ignore }; tr.AddToClassList("story-bar");
                        var fl = new VisualElement { pickingMode = PickingMode.Ignore }; fl.AddToClassList("story-fill"); fl.style.backgroundColor = r.C; fl.style.width = Length.Percent(Mathf.Clamp01(r.Frac) * 100f);
                        tr.Add(fl); row.Add(tr);
                    }
                    rows.Add(row);
                }
        }
    }
}
