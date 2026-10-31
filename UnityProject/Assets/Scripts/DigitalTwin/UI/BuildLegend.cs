using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Legend of what the construction view draws on the map: the utility networks and new streets (colour per network; a thin
    /// faint line = already built, a bright running dash = being laid this year) and the buildings (amber = on plan, red = behind,
    /// green = handed over this year). Used as a card over the map in the presentation step «Контроль стройки» and as the key at the
    /// top of the networks block of the Construction tab.</summary>
    public static class BuildLegend
    {
        public static readonly string[] NetNames = { "Вода", "Канализация", "Электросети", "Тепло", "Газ", "Связь" };

        /// <summary>The card over the map (presentation): networks + line pattern + buildings.</summary>
        public static VisualElement Card()
        {
            var card = new VisualElement { pickingMode = PickingMode.Ignore }; card.AddToClassList("w22-leg");
            card.Add(Lbl("НА КАРТЕ", "w22-leg-h"));
            card.Add(Patterns());
            var grid = new VisualElement { pickingMode = PickingMode.Ignore }; grid.AddToClassList("w22-leg-grid"); card.Add(grid);
            for (int k = 0; k < LineLayers.NetKeys.Length && k < NetNames.Length; k++) grid.Add(Item(Dash(LineLayers.NetColors[k]), NetNames[k]));
            grid.Add(Item(Dash(LineLayers.RoadWorkColor), "Новые улицы"));
            card.Add(Lbl("ЗДАНИЯ", "w22-leg-h2"));
            var bg = new VisualElement { pickingMode = PickingMode.Ignore }; bg.AddToClassList("w22-leg-grid"); bg.AddToClassList("w22-leg-wide"); card.Add(bg);
            bg.Add(Item(Box(new Color(0.96f, 0.65f, 0.14f)), "Строится в срок"));
            bg.Add(Item(Box(new Color(1f, 0.23f, 0.18f)), "Отстаёт"));
            bg.Add(Item(Box(new Color(0.20f, 0.78f, 0.35f)), "Сдано в этом году"));
            return card;
        }

        /// <summary>One row: thin line = built, running dash = being laid this year.</summary>
        public static VisualElement Patterns()
        {
            var r = new VisualElement { pickingMode = PickingMode.Ignore }; r.AddToClassList("w22-leg-pat");
            var c = new Color(0.85f, 0.87f, 0.90f);
            r.Add(Item(Thin(c), "построено"));
            r.Add(Item(Dash(c), "строится сейчас"));
            return r;
        }

        static VisualElement Item(VisualElement sw, string text)
        {
            var it = new VisualElement { pickingMode = PickingMode.Ignore }; it.AddToClassList("w22-leg-it");
            var holder = new VisualElement { pickingMode = PickingMode.Ignore }; holder.AddToClassList("w22-leg-sw"); holder.Add(sw); it.Add(holder);
            it.Add(Lbl(text, "w22-leg-t")); return it;
        }
        /// <summary>A bright running dash (three segments), as the line shader draws a network being laid.</summary>
        public static VisualElement Dash(Color c)
        {
            var d = new VisualElement { pickingMode = PickingMode.Ignore }; d.AddToClassList("w22-leg-dash");
            for (int i = 0; i < 3; i++) { var s = new VisualElement { pickingMode = PickingMode.Ignore }; s.AddToClassList("w22-leg-seg"); s.style.backgroundColor = c; d.Add(s); }
            return d;
        }
        /// <summary>The thin faint line of a built network.</summary>
        public static VisualElement Thin(Color c)
        {
            var d = new VisualElement { pickingMode = PickingMode.Ignore }; d.AddToClassList("w22-leg-thin"); d.style.backgroundColor = new Color(c.r, c.g, c.b, 0.55f); return d;
        }
        static VisualElement Box(Color c)
        {
            var d = new VisualElement { pickingMode = PickingMode.Ignore }; d.AddToClassList("w22-leg-box"); d.style.backgroundColor = c; return d;
        }
        static Label Lbl(string t, string cls) { var l = new Label(t) { pickingMode = PickingMode.Ignore }; l.AddToClassList(cls); return l; }
    }
}
