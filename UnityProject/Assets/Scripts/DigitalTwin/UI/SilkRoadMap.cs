using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The Silk Road step of the presentation: a stylised map of Eurasia (Natural Earth 1:50m via world-atlas, simplified,
    /// Resources/Tour/eurasia.json) over the scene. Kazakhstan is lit, the four transport corridors draw themselves from China towards
    /// Europe and Iran one after another, cargo pulses run along them and all of them meet in Alatau City. Painter2D, no packages.</summary>
    public class SilkRoadMap : VisualElement
    {
        class Country { public string Name; public Vector2[] P; }
        class Route { public string Name; public Color Col; public List<Vector2> N = new List<Vector2>(); public List<Vector2> Px = new List<Vector2>(); public List<float> Len = new List<float>(); public float Total; }
        readonly List<Country> countries = new List<Country>();
        readonly List<Route> routes = new List<Route>();
        readonly Dictionary<string, Vector2> cities = new Dictionary<string, Vector2>();
        readonly List<(string t, Vector2 p)> regions = new List<(string, Vector2)>();
        readonly Dictionary<string, Label> cityLabels = new Dictionary<string, Label>();
        readonly List<Label> regionLabels = new List<Label>();
        Label alatauLabel, title; VisualElement legend;
        float aspect = 2.2f, t; bool loaded; Rect map;
        static readonly string[] ShownCities = { "Сиань", "Урумчи", "Хоргос", "Актау", "Баку", "Стамбул", "Дуйсбург", "Москва", "Ташкент", "Тегеран", "Бендер-Аббас", "Ляньюньган" };

        public SilkRoadMap()
        {
            AddToClassList("silk"); pickingMode = PickingMode.Ignore;
            style.position = Position.Absolute; style.left = 0; style.right = 0; style.top = 0; style.bottom = 0; style.opacity = 0;
            generateVisualContent += Draw;
            Load();
            foreach (var (txt, _) in regions) { var l = new Label(txt) { pickingMode = PickingMode.Ignore }; l.AddToClassList("silk-region"); Add(l); regionLabels.Add(l); }
            foreach (var c in ShownCities) if (cities.ContainsKey(c)) { var l = new Label(c) { pickingMode = PickingMode.Ignore }; l.AddToClassList("silk-city"); Add(l); cityLabels[c] = l; }
            alatauLabel = new Label("ALATAU CITY") { pickingMode = PickingMode.Ignore }; alatauLabel.AddToClassList("silk-alatau"); Add(alatauLabel);
            title = new Label("Шёлковый путь: четыре коридора сходятся в Алатау") { pickingMode = PickingMode.Ignore }; title.AddToClassList("silk-title"); Add(title);
            legend = new VisualElement { pickingMode = PickingMode.Ignore }; legend.AddToClassList("silk-legend"); Add(legend);
            foreach (var r in routes)
            {
                var row = new VisualElement { pickingMode = PickingMode.Ignore }; row.AddToClassList("silk-leg");
                var sw = new VisualElement { pickingMode = PickingMode.Ignore }; sw.AddToClassList("silk-sw"); sw.style.backgroundColor = r.Col; row.Add(sw);
                row.Add(new Label(r.Name) { pickingMode = PickingMode.Ignore }); legend.Add(row);
            }
            RegisterCallback<GeometryChangedEvent>(_ => Layout());
            schedule.Execute(Tick).Every(16);
        }

        void Load()
        {
            var ta = Resources.Load<TextAsset>("Tour/eurasia"); if (ta == null) { Debug.LogWarning("[Alatau] eurasia.json missing"); return; }
            var root = Data.TwinJson.Parse(ta.text) as Dictionary<string, object>; if (root == null) return;
            aspect = System.Convert.ToSingle(root["aspect"]);
            foreach (var o in (List<object>)root["countries"])
            {
                var d = (Dictionary<string, object>)o; var p = (List<object>)d["p"]; var pts = new Vector2[p.Count / 2];
                for (int i = 0; i < pts.Length; i++) pts[i] = new Vector2(System.Convert.ToSingle(p[2 * i]), System.Convert.ToSingle(p[2 * i + 1]));
                countries.Add(new Country { Name = (string)d["n"], P = pts });
            }
            foreach (var kv in (Dictionary<string, object>)root["cities"]) { var v = (List<object>)kv.Value; cities[kv.Key] = new Vector2(System.Convert.ToSingle(v[0]), System.Convert.ToSingle(v[1])); }
            foreach (var o in (List<object>)root["routes"])
            {
                var d = (Dictionary<string, object>)o; ColorUtility.TryParseHtmlString((string)d["c"], out var col);
                var r = new Route { Name = (string)d["n"], Col = col };
                foreach (var w in (List<object>)d["w"]) if (cities.TryGetValue((string)w, out var p)) r.N.Add(p);
                routes.Add(r);
            }
            foreach (var o in (List<object>)root["labels"]) { var d = (Dictionary<string, object>)o; var v = (List<object>)d["p"]; regions.Add(((string)d["t"], new Vector2(System.Convert.ToSingle(v[0]), System.Convert.ToSingle(v[1])))); }
            loaded = true;
        }

        Vector2 ToPx(Vector2 n) => new Vector2(map.x + n.x * map.width, map.y + n.y * map.height);

        void Layout()
        {
            float w = contentRect.width, h = contentRect.height; if (w <= 0 || h <= 0 || !loaded) return;
            // the map fills the width (left of the caption column) and keeps its aspect
            // the map keeps clear of the left rail (≈ 60 px) and keeps its aspect
            float L0 = 76f, R0 = 16f, aw = w - L0 - R0;
            float mw = aw, mh = mw / aspect; if (mh > h * 0.86f) { mh = h * 0.86f; mw = mh * aspect; }
            map = new Rect(L0 + (aw - mw) * 0.5f, (h - mh) * 0.5f + 10f, mw, mh);
            // routes in pixels: Catmull-Rom through the cities, parallel routes on a shared track are spread a little
            for (int ri = 0; ri < routes.Count; ri++)
            {
                var r = routes[ri]; r.Px.Clear(); r.Len.Clear(); r.Total = 0;
                var nodes = new List<Vector2>(); foreach (var n in r.N) nodes.Add(ToPx(n));
                float off = (ri - (routes.Count - 1) * 0.5f) * 2.6f;
                for (int i = 0; i < nodes.Count - 1; i++)
                {
                    Vector2 p0 = nodes[Mathf.Max(i - 1, 0)], p1 = nodes[i], p2 = nodes[i + 1], p3 = nodes[Mathf.Min(i + 2, nodes.Count - 1)];
                    for (int s = 0; s < 10; s++)
                    {
                        float u = s / 10f, u2 = u * u, u3 = u2 * u;
                        var p = 0.5f * ((2f * p1) + (-p0 + p2) * u + (2f * p0 - 5f * p1 + 4f * p2 - p3) * u2 + (-p0 + 3f * p1 - 3f * p2 + p3) * u3);
                        r.Px.Add(p);
                    }
                }
                r.Px.Add(nodes[nodes.Count - 1]);
                // perpendicular offset
                for (int i = 0; i < r.Px.Count; i++)
                {
                    var a = r.Px[Mathf.Max(i - 1, 0)]; var b = r.Px[Mathf.Min(i + 1, r.Px.Count - 1)]; var d = (b - a).normalized;
                    r.Px[i] += new Vector2(-d.y, d.x) * off;
                }
                r.Len.Add(0); for (int i = 1; i < r.Px.Count; i++) { r.Total += (r.Px[i] - r.Px[i - 1]).magnitude; r.Len.Add(r.Total); }
            }
            for (int i = 0; i < regions.Count; i++) { var p = ToPx(regions[i].p); regionLabels[i].style.left = p.x - 80; regionLabels[i].style.top = p.y - 10; }
            foreach (var kv in cityLabels) { var p = ToPx(cities[kv.Key]); kv.Value.style.left = p.x + 6; kv.Value.style.top = p.y - 16; }
            if (cities.TryGetValue("Алатау", out var al)) { var p = ToPx(al); alatauLabel.style.left = p.x - 60; alatauLabel.style.top = p.y + 14; }
            title.style.left = map.x + 24; title.style.top = map.y + 16;
            legend.style.left = map.x + 24; legend.style.top = map.y + map.height - 112;
        }

        public void Play() { t = 0; style.display = DisplayStyle.Flex; }
        public float Time01 => t;
        bool hiding; float hideT;
        public void Hide() { hiding = true; hideT = 0; }

        void Tick()
        {
            if (panel == null) return;
            float dt = Mathf.Min(UnityEngine.Time.unscaledDeltaTime, 0.05f) * UnityEngine.Time.timeScale;
            if (!TourFx.Paused) t += dt;
            if (hiding) { hideT += dt; style.opacity = Mathf.Clamp01(1f - hideT / 0.8f); if (hideT > 0.85f) RemoveFromHierarchy(); MarkDirtyRepaint(); return; }
            style.opacity = Mathf.Clamp01(t / 1.0f);
            float lab = Mathf.Clamp01((t - 1.6f) / 0.8f);
            foreach (var l in regionLabels) l.style.opacity = lab * 0.85f;
            foreach (var l in cityLabels.Values) l.style.opacity = Mathf.Clamp01((t - 3f) / 1f);
            alatauLabel.style.opacity = Mathf.Clamp01((t - 2.2f) / 0.6f); title.style.opacity = lab; legend.style.opacity = Mathf.Clamp01((t - 2.5f) / 1f);
            MarkDirtyRepaint();
        }

        void Poly(Painter2D p, Vector2[] pts, Color fill, Color stroke, float lw)
        {
            if (pts.Length < 3) return;
            p.BeginPath(); p.MoveTo(ToPx(pts[0])); for (int i = 1; i < pts.Length; i++) p.LineTo(ToPx(pts[i])); p.ClosePath();
            p.fillColor = fill; p.Fill();
            if (lw > 0) { p.strokeColor = stroke; p.lineWidth = lw; p.Stroke(); }
        }

        void Draw(MeshGenerationContext ctx)
        {
            if (!loaded || map.width <= 0) return;
            var p = ctx.painter2D; float w = contentRect.width, h = contentRect.height;
            // sea
            p.fillColor = new Color(0.035f, 0.05f, 0.075f, 0.97f); p.BeginPath(); p.MoveTo(new Vector2(0, 0)); p.LineTo(new Vector2(w, 0)); p.LineTo(new Vector2(w, h)); p.LineTo(new Vector2(0, h)); p.ClosePath(); p.Fill();
            // graticule
            p.strokeColor = new Color(1, 1, 1, 0.035f); p.lineWidth = 1;
            for (int i = 1; i < 12; i++) { float x = map.x + map.width * i / 12f; p.BeginPath(); p.MoveTo(new Vector2(x, map.y)); p.LineTo(new Vector2(x, map.yMax)); p.Stroke(); }
            for (int i = 1; i < 6; i++) { float y = map.y + map.height * i / 6f; p.BeginPath(); p.MoveTo(new Vector2(map.x, y)); p.LineTo(new Vector2(map.xMax, y)); p.Stroke(); }
            // land
            float landA = Mathf.Clamp01((t - 0.3f) / 1.2f);
            foreach (var c in countries)
            {
                bool kz = c.Name == "Kazakhstan";
                var fill = kz ? Color.Lerp(new Color(0.12f, 0.13f, 0.15f), new Color(0.11f, 0.21f, 0.36f), Mathf.Clamp01((t - 1.2f) / 1.2f)) : new Color(0.12f, 0.13f, 0.15f);
                fill.a = landA;
                Poly(p, c.P, fill, new Color(0.30f, 0.32f, 0.36f, 0.55f * landA), 0.8f);
            }
            foreach (var c in countries) if (c.Name == "Kazakhstan") Poly(p, c.P, new Color(0, 0, 0, 0), new Color(0.45f, 0.68f, 1f, 0.9f * Mathf.Clamp01((t - 1.2f) / 1.2f)), 1.6f);

            // corridors: drawn one after another, then cargo pulses flow along them
            for (int ri = 0; ri < routes.Count; ri++)
            {
                var r = routes[ri]; if (r.Px.Count < 2) continue;
                float start = 2.4f + ri * 1.5f, grow = Mathf.Clamp01((t - start) / 2.6f); if (grow <= 0) continue;
                float L = r.Total * (grow * grow * (3f - 2f * grow));
                // glow under the line
                for (int pass = 0; pass < 2; pass++)
                {
                    p.strokeColor = pass == 0 ? new Color(r.Col.r, r.Col.g, r.Col.b, 0.18f) : r.Col; p.lineWidth = pass == 0 ? 8f : 2.4f; p.lineJoin = LineJoin.Round; p.lineCap = LineCap.Round;
                    p.BeginPath(); p.MoveTo(r.Px[0]);
                    for (int i = 1; i < r.Px.Count; i++)
                    {
                        if (r.Len[i] <= L) { p.LineTo(r.Px[i]); continue; }
                        float f = (L - r.Len[i - 1]) / Mathf.Max(r.Len[i] - r.Len[i - 1], 1e-3f); p.LineTo(Vector2.Lerp(r.Px[i - 1], r.Px[i], f)); break;
                    }
                    p.Stroke();
                }
                if (grow >= 1f)
                {
                    // cargo: bright dots running from China to the west every 70 px
                    float speed = 60f, phase = (t * speed + ri * 23f) % 70f;
                    for (float s = phase; s < r.Total; s += 70f)
                    {
                        var q = At(r, s); p.fillColor = new Color(1, 1, 1, 0.9f); p.BeginPath(); p.Arc(q, 2.2f, 0, 360); p.Fill();
                        p.fillColor = new Color(r.Col.r, r.Col.g, r.Col.b, 0.35f); p.BeginPath(); p.Arc(q, 5f, 0, 360); p.Fill();
                    }
                }
            }
            // cities
            float ca = Mathf.Clamp01((t - 3f) / 1f);
            foreach (var kv in cities)
            {
                if (kv.Key == "Алатау") continue;
                var q = ToPx(kv.Value); p.fillColor = new Color(0.85f, 0.88f, 0.92f, 0.85f * ca); p.BeginPath(); p.Arc(q, 2.6f, 0, 360); p.Fill();
            }
            // Alatau: the hub, pulsing
            if (cities.TryGetValue("Алатау", out var al))
            {
                var q = ToPx(al); float a = Mathf.Clamp01((t - 2.0f) / 0.6f);
                for (int k = 0; k < 3; k++)
                {
                    float ph = (t * 0.8f + k / 3f) % 1f;
                    p.strokeColor = new Color(0.88f, 0.15f, 0.11f, (1f - ph) * 0.8f * a); p.lineWidth = 2f; p.BeginPath(); p.Arc(q, 6f + ph * 34f, 0, 360); p.Stroke();
                }
                p.fillColor = new Color(0.88f, 0.15f, 0.11f, a); p.BeginPath(); p.Arc(q, 7f, 0, 360); p.Fill();
                p.fillColor = new Color(1, 1, 1, a); p.BeginPath(); p.Arc(q, 3f, 0, 360); p.Fill();
            }
        }

        static Vector2 At(Route r, float s)
        {
            for (int i = 1; i < r.Px.Count; i++) if (r.Len[i] >= s) { float f = (s - r.Len[i - 1]) / Mathf.Max(r.Len[i] - r.Len[i - 1], 1e-3f); return Vector2.Lerp(r.Px[i - 1], r.Px[i], f); }
            return r.Px[r.Px.Count - 1];
        }
    }
}
