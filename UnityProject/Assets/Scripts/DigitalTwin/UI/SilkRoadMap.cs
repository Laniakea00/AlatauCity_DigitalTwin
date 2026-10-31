using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The Silk Road step of the presentation: a stylised map of Eurasia (Natural Earth 1:50m via world-atlas, simplified,
    /// Resources/Tour/eurasia.json, plate carrée) over the scene. Kazakhstan is lit, the four transport corridors draw themselves one
    /// after another like on the official alatau.city logistics map: straight segments from station to station, passing exactly
    /// through every station. Where corridors share a stretch they run side by side between the stations and pinch together at each
    /// station. Every station is labelled (labels are placed so they do not collide), cargo pulses run along the lines and all four
    /// corridors meet at Alatau City (the Zhetygen junction, where the Khorgos line joins the Turksib). Painter2D, no packages.</summary>
    public class SilkRoadMap : VisualElement
    {
        class Country { public string Name; public Vector2[] P; }
        class Route
        {
            public string Name; public Color Col;
            public readonly List<int> Nodes = new List<int>();            // city indices in drawing order
            public float[] SlotOff;                                        // per segment: sideways slot on a shared stretch (px)
            public readonly List<Vector2> Px = new List<Vector2>();
            public readonly List<float> Len = new List<float>();
            public float[] NodeLen; public float Total;
        }
        readonly List<Country> countries = new List<Country>();
        readonly List<Route> routes = new List<Route>();
        readonly List<string> cname = new List<string>();
        readonly List<Vector2> cpos = new List<Vector2>();
        readonly Dictionary<string, int> cidx = new Dictionary<string, int>();
        readonly List<(string t, Vector2 p)> regions = new List<(string, Vector2)>();
        readonly List<Label> regionLabels = new List<Label>();
        Label[] cityLab; string[] labText; bool[] used, hidden, major; float[] reveal; Rect[] labRect; int[] placeOrder;
        int alatau = -1;
        VisualElement alatauBox, legend; Label title;
        float aspect = 2.2f, t; bool loaded; Rect map; int frame;
        readonly List<Rect> placed = new List<Rect>(), hard = new List<Rect>(), soft = new List<Rect>();

        const float Gap = 3.4f;        // px between parallel corridors on a shared stretch
        const float DotR = 3.6f;       // station marker radius
        // stations whose label is never hidden (ends of the corridors and the big hubs); the others give way when crowded
        static readonly HashSet<string> Major = new HashSet<string> { "Хоргос", "Урумчи", "Сиань", "Ляньюньган", "Шымкент", "Актау", "Баку", "Стамбул",
            "Дуйсбург", "Москва", "Санкт-Петербург", "Тегеран", "Бендер-Аббас" };

        public const string SrcNelb = "wiki_new_eurasian_land_bridge", SrcTitr = "wiki_titr", SrcWewc = "wiki_we_wc_highway",
            SrcKti = "wiki_kz_tm_iran_railway", SrcZhetygen = "wiki_zhetygen";

        static SilkRoadMap()
        {
            Sources.Register(SrcNelb, "Новый Евразийский сухопутный мост (Китай — Европа по железной дороге)", "Wikipedia", "", "https://en.wikipedia.org/wiki/New_Eurasian_Land_Bridge",
                "Маршрут Ляньюньган — Ланьчжоу — Синьцзян, переход границы в Достыке и Хоргосе, далее через Казахстан и Россию к Европе. На карте — схема по основным узлам.");
            Sources.Register(SrcTitr, "Транскаспийский международный транспортный маршрут (Средний коридор)", "Wikipedia", "", "https://en.wikipedia.org/wiki/Trans-Caspian_International_Transport_Route",
                "Китай — Казахстан — паромы через Каспий — Азербайджан — Грузия — Турция; железная дорога Баку — Тбилиси — Карс работает с 2017 года.");
            Sources.Register(SrcWewc, "Автодорога «Западная Европа — Западный Китай»", "Wikipedia", "", "https://en.wikipedia.org/wiki/Western_Europe-Western_China_Highway",
                "8 445 км: Санкт-Петербург, Москва, Нижний Новгород, Казань, Оренбург, Актобе, Кызылорда, Шымкент, Тараз, Кордай, Алматы, Хоргос, Урумчи, Ланьчжоу, Чжэнчжоу, Ляньюньган.");
            Sources.Register(SrcKti, "Железная дорога Казахстан — Туркменистан — Иран (Север — Юг, восточная ветка)", "Wikipedia", "", "https://en.wikipedia.org/wiki/International_North–South_Transport_Corridor",
                "Узень (Казахстан) — Берекет (Туркменистан) — Горган (Иран), 677 км, открыта в декабре 2014 года; далее по сети Ирана к портам Персидского залива.");
            Sources.Register(SrcZhetygen, "Жетыген: стык Турксиба и линии Жетыген — Алтынколь (Хоргос)", "Wikipedia", "", "https://en.wikipedia.org/wiki/Zhetigen",
                "Станция Жетыген на Турксибе, отсюда идёт ветка Жетыген — Алтынколь к китайской границе у Хоргоса. Поэтому коридоры из Китая сходятся у Алатау.");
        }

        public SilkRoadMap()
        {
            AddToClassList("silk"); pickingMode = PickingMode.Ignore;
            style.position = Position.Absolute; style.left = 0; style.right = 0; style.top = 0; style.bottom = 0; style.opacity = 0;
            generateVisualContent += Draw;
            Load();
            foreach (var (txt, _) in regions)
            {
                var l = new Label(txt) { pickingMode = PickingMode.Ignore }; l.AddToClassList("silk-region"); Add(l); regionLabels.Add(l);
                if (txt.StartsWith("Каспий")) { l.style.fontSize = 11; l.style.letterSpacing = 1.5f; l.style.whiteSpace = WhiteSpace.Normal; l.style.width = 90; l.style.color = new Color(0.55f, 0.68f, 0.85f, 0.55f); }
            }
            int n = cname.Count; cityLab = new Label[n]; labText = new string[n]; hidden = new bool[n]; reveal = new float[n]; labRect = new Rect[n]; major = new bool[n];
            var order = new List<int>();
            for (int i = 0; i < n; i++)
            {
                reveal[i] = -1f; major[i] = Major.Contains(cname[i]);
                if (!used[i] || i == alatau) continue;
                var l = new Label(cname[i]) { pickingMode = PickingMode.Ignore }; l.AddToClassList("silk-city");
                l.style.position = Position.Absolute; l.style.fontSize = 11; l.style.whiteSpace = WhiteSpace.NoWrap; l.style.opacity = 0;
                l.style.color = major[i] ? new Color(0.93f, 0.95f, 0.97f, 0.95f) : new Color(0.80f, 0.83f, 0.88f, 0.9f);
                l.style.textShadow = new TextShadow { offset = new Vector2(0, 1), blurRadius = 3, color = new Color(0, 0, 0, 0.95f) };
                Add(l); cityLab[i] = l;
            }
            for (int pass = 0; pass < 2; pass++) for (int i = 0; i < n; i++) if (cityLab[i] != null && major[i] == (pass == 0)) order.Add(i);
            placeOrder = order.ToArray();

            // Alatau City: the hub label sits above the junction (the corridors leave it to the west and east, below is the bundle to Shymkent)
            alatauBox = new VisualElement { pickingMode = PickingMode.Ignore }; alatauBox.style.position = Position.Absolute; alatauBox.style.width = 200; alatauBox.style.alignItems = Align.Center;
            var an = new Label("ALATAU CITY") { pickingMode = PickingMode.Ignore }; an.AddToClassList("silk-alatau"); an.style.position = Position.Relative; an.style.width = 200;
            an.style.textShadow = new TextShadow { offset = new Vector2(0, 1), blurRadius = 4, color = new Color(0, 0, 0, 0.95f) };
            var sub = new Label("ж/д узел Жетыген") { pickingMode = PickingMode.Ignore };
            sub.style.fontSize = 11; sub.style.color = new Color(1f, 0.78f, 0.74f, 0.9f); sub.style.whiteSpace = WhiteSpace.NoWrap; sub.style.unityTextAlign = TextAnchor.UpperCenter;
            sub.style.textShadow = new TextShadow { offset = new Vector2(0, 1), blurRadius = 3, color = new Color(0, 0, 0, 0.95f) };
            alatauBox.Add(an); alatauBox.Add(sub); Add(alatauBox);

            title = new Label("Шёлковый путь: четыре коридора сходятся в Алатау") { pickingMode = PickingMode.Ignore }; title.AddToClassList("silk-title"); Add(title);
            legend = new VisualElement { pickingMode = PickingMode.Ignore }; legend.AddToClassList("silk-legend"); Add(legend);
            foreach (var r in routes)
            {
                var row = new VisualElement { pickingMode = PickingMode.Ignore }; row.AddToClassList("silk-leg");
                var sw = new VisualElement { pickingMode = PickingMode.Ignore }; sw.AddToClassList("silk-sw"); sw.style.backgroundColor = r.Col; row.Add(sw);
                row.Add(new Label(r.Name) { pickingMode = PickingMode.Ignore }); legend.Add(row);
            }
            legend.Add(SourceTags.Line(SrcNelb, SrcTitr, SrcWewc, SrcKti, SrcZhetygen));
            RegisterCallback<GeometryChangedEvent>(_ => Layout());
            legend.RegisterCallback<GeometryChangedEvent>(_ => PlaceLabels());
            alatauBox.RegisterCallback<GeometryChangedEvent>(_ => PlaceLabels());
            schedule.Execute(Tick).Every(16);
        }

        void Load()
        {
            var ta = Resources.Load<TextAsset>("Tour/eurasia"); if (ta == null) { Debug.LogWarning("[Alatau] eurasia.json missing"); used = new bool[0]; return; }
            var root = Data.TwinJson.Parse(ta.text) as Dictionary<string, object>; if (root == null) { used = new bool[0]; return; }
            aspect = System.Convert.ToSingle(root["aspect"]);
            foreach (var o in (List<object>)root["countries"])
            {
                var d = (Dictionary<string, object>)o; var p = (List<object>)d["p"]; var pts = new Vector2[p.Count / 2];
                for (int i = 0; i < pts.Length; i++) pts[i] = new Vector2(System.Convert.ToSingle(p[2 * i]), System.Convert.ToSingle(p[2 * i + 1]));
                countries.Add(new Country { Name = (string)d["n"], P = pts });
            }
            foreach (var kv in (Dictionary<string, object>)root["cities"])
            {
                var v = (List<object>)kv.Value; cidx[kv.Key] = cname.Count; cname.Add(kv.Key);
                cpos.Add(new Vector2(System.Convert.ToSingle(v[0]), System.Convert.ToSingle(v[1])));
            }
            cidx.TryGetValue("Алатау", out alatau); if (!cidx.ContainsKey("Алатау")) alatau = -1;
            used = new bool[cname.Count];
            foreach (var o in (List<object>)root["routes"])
            {
                var d = (Dictionary<string, object>)o; ColorUtility.TryParseHtmlString((string)d["c"], out var col);
                var r = new Route { Name = (string)d["n"], Col = col };
                foreach (var w in (List<object>)d["w"]) if (cidx.TryGetValue((string)w, out var ci)) { r.Nodes.Add(ci); used[ci] = true; }
                r.SlotOff = new float[Mathf.Max(r.Nodes.Count - 1, 0)]; r.NodeLen = new float[r.Nodes.Count];
                routes.Add(r);
            }
            // shared stretches: the corridors on one station-to-station segment get side-by-side slots (in legend order)
            var segs = new Dictionary<long, List<int>>();
            for (int ri = 0; ri < routes.Count; ri++)
            {
                var nd = routes[ri].Nodes;
                for (int k = 0; k < nd.Count - 1; k++) { long key = SegKey(nd[k], nd[k + 1]); if (!segs.TryGetValue(key, out var l)) segs[key] = l = new List<int>(); if (!l.Contains(ri)) l.Add(ri); }
            }
            for (int ri = 0; ri < routes.Count; ri++)
            {
                var nd = routes[ri].Nodes;
                for (int k = 0; k < nd.Count - 1; k++) { var l = segs[SegKey(nd[k], nd[k + 1])]; routes[ri].SlotOff[k] = (l.IndexOf(ri) - (l.Count - 1) * 0.5f) * Gap; }
            }
            foreach (var o in (List<object>)root["labels"]) { var d = (Dictionary<string, object>)o; var v = (List<object>)d["p"]; regions.Add(((string)d["t"], new Vector2(System.Convert.ToSingle(v[0]), System.Convert.ToSingle(v[1])))); }
            loaded = true;
        }

        static long SegKey(int a, int b) => a < b ? (long)a * 4096 + b : (long)b * 4096 + a;

        Vector2 ToPx(Vector2 n) => new Vector2(map.x + n.x * map.width, map.y + n.y * map.height);
        Vector2 CityPx(int i) => ToPx(cpos[i]);

        void Layout()
        {
            float w = contentRect.width, h = contentRect.height; if (w <= 0 || h <= 0 || !loaded) return;
            // the map keeps clear of the left rail (≈ 60 px) and keeps its aspect
            float L0 = 76f, R0 = 16f, aw = w - L0 - R0;
            float mw = aw, mh = mw / aspect; if (mh > h * 0.86f) { mh = h * 0.86f; mw = mh * aspect; }
            map = new Rect(L0 + (aw - mw) * 0.5f, (h - mh) * 0.5f + 10f, mw, mh);
            // corridors in pixels: straight segments station to station; on a shared stretch each corridor eases into its slot and
            // back, so every line passes exactly through the centre of every station
            foreach (var r in routes)
            {
                r.Px.Clear(); r.Len.Clear(); r.Total = 0; if (r.Nodes.Count < 2) continue;
                var nodeAt = new int[r.Nodes.Count];
                for (int k = 0; k < r.Nodes.Count - 1; k++)
                {
                    int a = r.Nodes[k], b = r.Nodes[k + 1]; Vector2 pa = CityPx(a), pb = CityPx(b);
                    nodeAt[k] = r.Px.Count; r.Px.Add(pa);
                    float off = r.SlotOff[k], L = (pb - pa).magnitude; if (Mathf.Abs(off) < 0.01f || L < 1f) continue;
                    Vector2 cd = (CityPx(Mathf.Max(a, b)) - CityPx(Mathf.Min(a, b))).normalized, nrm = new Vector2(-cd.y, cd.x), dir = (pb - pa) / L;
                    float ramp = Mathf.Min(20f, 0.35f * L);
                    for (int j = 1; j <= 6; j++) { float u = j / 6f, e = u * u * (3f - 2f * u); r.Px.Add(pa + dir * (ramp * u) + nrm * (off * e)); }
                    for (int j = 6; j >= 1; j--) { float u = j / 6f, e = u * u * (3f - 2f * u); r.Px.Add(pb - dir * (ramp * u) + nrm * (off * e)); }
                }
                nodeAt[r.Nodes.Count - 1] = r.Px.Count; r.Px.Add(CityPx(r.Nodes[r.Nodes.Count - 1]));
                r.Len.Add(0); for (int i = 1; i < r.Px.Count; i++) { r.Total += (r.Px[i] - r.Px[i - 1]).magnitude; r.Len.Add(r.Total); }
                for (int k = 0; k < r.Nodes.Count; k++) r.NodeLen[k] = r.Len[nodeAt[k]];
            }
            for (int i = 0; i < regions.Count; i++)
            {
                var p = ToPx(regions[i].p); float lw = regionLabels[i].resolvedStyle.width; if (float.IsNaN(lw) || lw <= 0) lw = 160;
                regionLabels[i].style.left = p.x - lw * 0.5f; regionLabels[i].style.top = p.y - 10;
            }
            if (alatau >= 0) { var p = CityPx(alatau); alatauBox.style.left = p.x - 100; alatauBox.style.top = p.y - 52; }
            title.style.left = map.x + 24; title.style.top = map.y + 16;
            legend.style.left = map.x + 24; legend.style.top = StyleKeyword.Auto; legend.style.bottom = Mathf.Max(8f, h - map.yMax + 12f);
            PlaceLabels();
            MarkDirtyRepaint();
        }

        // ------------------------------------------------------------------ station labels: best free spot around each dot
        static readonly Vector2[] CandDir = { new Vector2(1, 0), new Vector2(-1, 0), new Vector2(1, -1), new Vector2(1, 1), new Vector2(0, -1), new Vector2(0, 1), new Vector2(-1, -1), new Vector2(-1, 1) };
        static readonly float[] CandPref = { 0f, 4f, 6f, 7f, 8f, 9f, 10f, 11f };

        Vector2 Measure(Label l)
        {
            Vector2 s = Vector2.zero;
            try { s = l.MeasureTextSize(l.text, 0, MeasureMode.Undefined, 0, MeasureMode.Undefined); } catch { }
            if (float.IsNaN(s.x) || s.x <= 1f) s = new Vector2(l.text.Length * 6.4f + 2f, 14f);
            return s;
        }

        void PlaceLabels()
        {
            if (!loaded || map.width <= 0 || cityLab == null) return;
            float w = contentRect.width, h = contentRect.height;
            placed.Clear(); hard.Clear(); soft.Clear();
            hard.Add(new Rect(map.x + 16, map.y + 8, 620, 44));                                   // title
            var lg = legend.layout; if (lg.width > 1 && !float.IsNaN(lg.width)) hard.Add(new Rect(lg.x - 4, lg.y - 4, lg.width + 8, lg.height + 8));
            if (alatau >= 0)
            {
                var p = CityPx(alatau); var ab = alatauBox.layout; float bw = 190f;
                foreach (var ch in alatauBox.Children()) { float cw = ch is Label cl ? Measure(cl).x : 0f; if (cw + 8f > bw) bw = cw + 8f; }
                if (ab.height > 1 && !float.IsNaN(ab.height)) hard.Add(new Rect(p.x - bw * 0.5f, p.y - 52, bw, ab.height + 2)); else hard.Add(new Rect(p.x - bw * 0.5f, p.y - 52, bw, 40));
                hard.Add(new Rect(p.x - 10, p.y - 10, 20, 20));
            }
            for (int i = 0; i < regions.Count; i++)
            {
                var l = regionLabels[i]; var s = Measure(l); float lw = Mathf.Min(s.x, l.text.StartsWith("Каспий") ? 90 : 160);
                var p = ToPx(regions[i].p); soft.Add(new Rect(p.x - lw * 0.5f, p.y - 8, lw, s.y > 20 && lw >= 90 ? s.y : 18));
            }
            foreach (int i in placeOrder)
            {
                var l = cityLab[i]; labText[i] = l.text; var s = Measure(l); var p = CityPx(i);
                float best = float.MaxValue; Rect bestR = default;
                for (int c = 0; c < CandDir.Length; c++)
                {
                    var d = CandDir[c]; const float g = 6f;
                    float x = d.x > 0 ? p.x + g : d.x < 0 ? p.x - g - s.x : p.x - s.x * 0.5f;
                    float y = d.y > 0 ? p.y + g - 3f : d.y < 0 ? p.y - g - s.y + 3f : p.y - s.y * 0.5f;
                    if (d.x != 0 && d.y != 0) x -= d.x * 3f;
                    var rc = new Rect(x, y, s.x, s.y);
                    float cost = CandPref[c] + Cost(rc, i, w, h);
                    if (cost < best) { best = cost; bestR = rc; }
                }
                hidden[i] = best >= 1000f && !major[i];
                l.style.display = hidden[i] ? DisplayStyle.None : DisplayStyle.Flex;
                if (hidden[i]) continue;
                l.style.left = bestR.x; l.style.top = bestR.y; labRect[i] = bestR; placed.Add(bestR);
            }
        }

        float Cost(Rect rc, int self, float w, float h)
        {
            float cost = 0;
            if (rc.xMin < 2 || rc.yMin < 2 || rc.xMax > w - 2 || rc.yMax > h - 2) cost += 2000;
            var grown = new Rect(rc.x - 2, rc.y - 1, rc.width + 4, rc.height + 2);
            foreach (var o in placed) if (o.Overlaps(grown)) cost += 1000 + Area(o, grown);
            foreach (var o in hard) if (o.Overlaps(rc)) cost += 1000;
            foreach (var o in soft) if (o.Overlaps(rc)) cost += 60;
            for (int j = 0; j < cpos.Count; j++) if (j != self && used[j] && RectCircle(rc, CityPx(j), DotR + 2f)) cost += j == alatau ? 1000 : 700;
            foreach (var r in routes)
                for (int k = 1; k < r.Px.Count; k++) if (SegRect(r.Px[k - 1], r.Px[k], rc)) { cost += 30; break; }
            return cost;
        }

        static float Area(Rect a, Rect b) { float x = Mathf.Min(a.xMax, b.xMax) - Mathf.Max(a.xMin, b.xMin), y = Mathf.Min(a.yMax, b.yMax) - Mathf.Max(a.yMin, b.yMin); return x > 0 && y > 0 ? x * y * 0.05f : 0; }
        static bool RectCircle(Rect r, Vector2 c, float rad) { float x = Mathf.Clamp(c.x, r.xMin, r.xMax), y = Mathf.Clamp(c.y, r.yMin, r.yMax); return (new Vector2(x, y) - c).sqrMagnitude < rad * rad; }
        static bool SegRect(Vector2 a, Vector2 b, Rect r)
        {
            // Liang–Barsky clip of segment ab against r
            float t0 = 0, t1 = 1, dx = b.x - a.x, dy = b.y - a.y;
            if (!Clip(-dx, a.x - r.xMin, ref t0, ref t1)) return false;
            if (!Clip(dx, r.xMax - a.x, ref t0, ref t1)) return false;
            if (!Clip(-dy, a.y - r.yMin, ref t0, ref t1)) return false;
            if (!Clip(dy, r.yMax - a.y, ref t0, ref t1)) return false;
            return true;
        }
        static bool Clip(float p, float q, ref float t0, ref float t1)
        {
            if (Mathf.Abs(p) < 1e-6f) return q >= 0;
            float u = q / p;
            if (p < 0) { if (u > t1) return false; if (u > t0) t0 = u; }
            else { if (u < t0) return false; if (u < t1) t1 = u; }
            return true;
        }

        public void Play() { t = 0; style.display = DisplayStyle.Flex; }
        public float Time01 => t;
        bool hiding; float hideT;
        public void Hide() { hiding = true; hideT = 0; }

        float Grow(int ri) { float g = Mathf.Clamp01((t - (2.4f + ri * 1.5f)) / 2.6f); return g * g * (3f - 2f * g); }

        void Tick()
        {
            if (panel == null) return;
            float dt = Mathf.Min(UnityEngine.Time.unscaledDeltaTime, 0.5f) * UnityEngine.Time.timeScale;
            if (!TourFx.Paused) t += dt;
            if (hiding) { hideT += dt; style.opacity = Mathf.Clamp01(1f - hideT / 0.8f); if (hideT > 0.85f) RemoveFromHierarchy(); MarkDirtyRepaint(); return; }
            style.opacity = Mathf.Clamp01(t / 1.0f);
            float lab = Mathf.Clamp01((t - 1.6f) / 0.8f);
            foreach (var l in regionLabels) l.style.opacity = lab * 0.85f;
            // a station appears when the first corridor reaches it
            for (int ri = 0; ri < routes.Count; ri++)
            {
                var r = routes[ri]; if (r.Total <= 0) continue; float L = r.Total * Grow(ri);
                for (int k = 0; k < r.Nodes.Count; k++) { int c = r.Nodes[k]; if (reveal[c] < 0 && L >= r.NodeLen[k] - 0.5f && L > 0) reveal[c] = t; }
            }
            for (int i = 0; i < cityLab.Length; i++) if (cityLab[i] != null) cityLab[i].style.opacity = reveal[i] < 0 ? 0 : Mathf.Clamp01((t - reveal[i] - 0.1f) / 0.5f);
            alatauBox.style.opacity = Mathf.Clamp01((t - 2.2f) / 0.6f); title.style.opacity = lab; legend.style.opacity = Mathf.Clamp01((t - 2.5f) / 1f);
            // the translator may have switched the language: place the labels again for the new widths
            if (++frame % 30 == 0)
                for (int i = 0; i < cityLab.Length; i++) if (cityLab[i] != null && labText[i] != null && cityLab[i].text != labText[i]) { PlaceLabels(); break; }
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

            // corridors: drawn one after another (soft glow, then the line)
            p.lineJoin = LineJoin.Round; p.lineCap = LineCap.Round;
            for (int pass = 0; pass < 2; pass++)
                for (int ri = 0; ri < routes.Count; ri++)
                {
                    var r = routes[ri]; if (r.Px.Count < 2) continue;
                    float g = Grow(ri); if (g <= 0) continue; float L = r.Total * g;
                    p.strokeColor = pass == 0 ? new Color(r.Col.r, r.Col.g, r.Col.b, 0.13f) : r.Col; p.lineWidth = pass == 0 ? 7f : 2.2f;
                    p.BeginPath(); p.MoveTo(r.Px[0]);
                    for (int i = 1; i < r.Px.Count; i++)
                    {
                        if (r.Len[i] <= L) { p.LineTo(r.Px[i]); continue; }
                        float f = (L - r.Len[i - 1]) / Mathf.Max(r.Len[i] - r.Len[i - 1], 1e-3f); p.LineTo(Vector2.Lerp(r.Px[i - 1], r.Px[i], f)); break;
                    }
                    p.Stroke();
                }
            // cargo: small dots in the line's own (lighter) colour, running from China westwards / from Alatau southwards
            for (int ri = 0; ri < routes.Count; ri++)
            {
                var r = routes[ri]; if (r.Px.Count < 2 || Grow(ri) < 1f) continue;
                float ca = Mathf.Clamp01((t - (2.4f + ri * 1.5f + 2.6f)) / 0.6f);
                var core = Color.Lerp(r.Col, Color.white, 0.35f); core.a = ca;
                float phase = (t * 52f + ri * 19f) % 64f;
                for (float s = phase; s < r.Total; s += 64f)
                {
                    var q = At(r, s);
                    p.fillColor = new Color(r.Col.r, r.Col.g, r.Col.b, 0.28f * ca); p.BeginPath(); p.Arc(q, 3.4f, 0, 360); p.Fill();
                    p.fillColor = core; p.BeginPath(); p.Arc(q, 1.6f, 0, 360); p.Fill();
                }
            }
            // stations: one marker style — white dot with a dark ring, on top of the lines
            for (int i = 0; i < cpos.Count; i++)
            {
                if (i == alatau || !used[i] || reveal[i] < 0) continue;
                float a = Mathf.Clamp01((t - reveal[i]) / 0.3f); var q = CityPx(i);
                p.fillColor = new Color(0.04f, 0.05f, 0.07f, a); p.BeginPath(); p.Arc(q, DotR + 1.4f, 0, 360); p.Fill();
                p.fillColor = new Color(0.94f, 0.96f, 0.98f, a); p.BeginPath(); p.Arc(q, DotR, 0, 360); p.Fill();
            }
            // Alatau: the hub, pulsing
            if (alatau >= 0)
            {
                var q = CityPx(alatau); float a = Mathf.Clamp01((t - 2.0f) / 0.6f);
                for (int k = 0; k < 3; k++)
                {
                    float ph = (t * 0.8f + k / 3f) % 1f;
                    p.strokeColor = new Color(0.88f, 0.15f, 0.11f, (1f - ph) * 0.7f * a); p.lineWidth = 2f; p.BeginPath(); p.Arc(q, 8f + ph * 30f, 0, 360); p.Stroke();
                }
                p.fillColor = new Color(0.04f, 0.05f, 0.07f, a); p.BeginPath(); p.Arc(q, 8.5f, 0, 360); p.Fill();
                p.fillColor = new Color(0.88f, 0.15f, 0.11f, a); p.BeginPath(); p.Arc(q, 7f, 0, 360); p.Fill();
                p.fillColor = new Color(1, 1, 1, a); p.BeginPath(); p.Arc(q, 2.8f, 0, 360); p.Fill();
            }
        }

        static Vector2 At(Route r, float s)
        {
            for (int i = 1; i < r.Px.Count; i++) if (r.Len[i] >= s) { float f = (s - r.Len[i - 1]) / Mathf.Max(r.Len[i] - r.Len[i - 1], 1e-3f); return Vector2.Lerp(r.Px[i - 1], r.Px[i], f); }
            return r.Px[r.Px.Count - 1];
        }
    }
}
