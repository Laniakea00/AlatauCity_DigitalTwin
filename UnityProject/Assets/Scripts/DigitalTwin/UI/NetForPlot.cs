using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;
using NetSt = AlatauCity.DigitalTwin.Data.InvestRegistry.NetSt;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>«Хватит ли сетей на участке»: for a district, the timeline year and the scenario — one answer line, then one row per resource
    /// (power, heat, gas, water, sewer) with the spare (+) or the deficit (−) in that year and a 2026–2050 strip with the shortage years in
    /// red. A click on the strip moves the timeline to that year. Numbers: InvestRegistry.At (the twin balance), the same as the
    /// Infrastructure balance rows, the facility cards and the presentation step «Прогноз: энергия 2034». Used by Инфраструктура and by
    /// the investor calculator in Объекты.</summary>
    public static class NetForPlot
    {
        static bool detailsOpen;
        public static readonly Color Ok = new Color(0.20f, 0.78f, 0.35f), Warn = new Color(0.96f, 0.65f, 0.14f), Bad = new Color(1f, 0.30f, 0.25f), None = new Color(0.42f, 0.44f, 0.47f);

        public static VisualElement Build(int d)
        {
            var box = new VisualElement(); box.AddToClassList("w20-net");
            if (!TwinData.Ready) { var l = new Label("Данные сетей загружаются…"); l.AddToClassList("note"); box.Add(l); return box; }
            int s = (int)TwinState.Scenario, y = TwinState.Year;
            var res = InvestRegistry.NetRes;
            var now = new InvestRegistry.NetYear[res.Length]; var all = new InvestRegistry.NetYear[res.Length][];
            for (int i = 0; i < res.Length; i++) { all[i] = InvestRegistry.Years(s, res[i].key, d); now[i] = all[i][y - InvestRegistry.FirstYear]; }

            // ---- the answer
            var shortNow = new List<string>(); var noneNow = new List<string>(); int fixYear = 0; bool neverFixed = false;
            for (int i = 0; i < res.Length; i++)
            {
                if (now[i].St == NetSt.Short)
                {
                    shortNow.Add(res[i].name.ToLowerInvariant());
                    InvestRegistry.NextShort(all[i], y, out int end); if (end < 0) neverFixed = true; else fixYear = Mathf.Max(fixYear, end);
                }
                else if (now[i].St == NetSt.None) noneNow.Add(res[i].name.ToLowerInvariant());
            }
            string ans, sub; string cls;
            if (shortNow.Count > 0)
            {
                ans = string.Format("Не хватает: {0}", Join(shortNow)); cls = "bad";
                sub = neverFixed ? "Дефицит не снят до 2050 года" : string.Format("Новые подключения — с {0} года", fixYear);
            }
            else if (noneNow.Count > 0)
            {
                ans = string.Format("Сетей ещё нет: {0}", Join(noneNow)); cls = "warn";
                sub = NextLine(res, all, y + 1);
            }
            else { ans = "Сетей хватает"; cls = "ok"; sub = NextLine(res, all, y + 1); }
            var a = new Label(ans); a.AddToClassList("w20-net-ans"); a.AddToClassList(cls); box.Add(a);
            var sl = new Label(sub); sl.AddToClassList("w20-net-sub"); box.Add(sl);

            // ---- header of the table: the strip's span and the value column
            var hdr = new VisualElement(); hdr.AddToClassList("w20-net-row"); hdr.AddToClassList("w20-net-hdr");
            var h0 = new Label(""); h0.AddToClassList("w20-net-n"); hdr.Add(h0);
            var hs = new VisualElement(); hs.AddToClassList("w20-net-span");
            var hl = new Label(InvestRegistry.FirstYear.ToString()); hl.AddToClassList("w20-net-ax"); hs.Add(hl);
            var hr = new Label(TwinState.MaxYear.ToString()); hr.AddToClassList("w20-net-ax"); hs.Add(hr);
            hdr.Add(hs);
            var hv = new Label(string.Format("в {0}", y)); hv.AddToClassList("w20-net-ax"); hv.AddToClassList("w20-net-vh"); hdr.Add(hv);
            box.Add(hdr);

            for (int i = 0; i < res.Length; i++)
            {
                var r = new VisualElement(); r.AddToClassList("w20-net-row");
                var n = new Label(res[i].name); n.AddToClassList("w20-net-n"); r.Add(n);
                r.Add(new Strip(all[i], y));
                var v = new VisualElement(); v.AddToClassList("w20-net-v");
                var x = now[i]; string num, c;
                switch (x.St)
                {
                    case NetSt.Short: num = "−" + InvestRegistry.Fmt(res[i].key, x.Deficit); c = "bad"; break;
                    case NetSt.None: num = "нет"; c = "warn"; break;
                    default: num = "+" + InvestRegistry.Fmt(res[i].key, x.Free); c = x.St == NetSt.Tight ? "warn" : "ok"; break;
                }
                var nl = new Label(num); nl.AddToClassList("w20-net-num"); nl.AddToClassList(c); v.Add(nl);
                if (x.St != NetSt.None) { var ul = new Label(res[i].unit); ul.AddToClassList("w20-net-unit"); v.Add(ul); }
                r.Add(v);
                box.Add(r);
            }
            var leg = new Label("+ свободно · − не хватает · клик по полосе — год"); leg.AddToClassList("w20-net-leg"); box.Add(leg);

            // ---- why: the numbers behind every row and how they are counted
            var det = Widgets.Details(box, "Как считается");
            KeepOpen(det);
            for (int i = 0; i < res.Length; i++)
            {
                var x = now[i]; string where = res[i].key == "power" ? string.Format("{0} · {1}", res[i].name, x.Level) : x.Pooled ? string.Format("{0} · город", res[i].name) : res[i].name;
                string val = x.St == NetSt.None ? "мощности нет" : string.Format("спрос {0} из {1} {2}", InvestRegistry.Fmt(res[i].key, x.Demand), InvestRegistry.Fmt(res[i].key, x.Cap), res[i].unit);
                det.Add(Widgets.Fact(where, val));
                string rg = InvestRegistry.Ranges(all[i]);
                if (rg.Length > 0) { var f = Widgets.Fact("  дефицит в годы", rg); f.AddToClassList("w20-net-fy"); det.Add(f); }
            }
            var how = new Label("Спрос и мощность — баланс двойника по району, году на шкале и сценарию. Электричество — худший из двух уровней: питающая ПС 220/110 кВ района и сеть ПС 110/10 кВ. Вода и газ — общие системы города. Красный год — спрос выше мощности: новых потребителей не подключить. Оранжевый — загрузка выше 90 % или мощности ещё нет.");
            how.AddToClassList("note"); how.style.marginTop = 6; det.Add(how);
            box.Add(SourceTags.Line(InvestRegistry.NetModel, Sources.ModelCity));
            return box;
        }

        /// <summary>Sets the scenario by index (0 base, 1 fast, 2 slow, 3 infra first): for scripted screenshots.</summary>
        public static void SetScenario(int s) { TwinState.Scenario = (Scenario)Mathf.Clamp(s, 0, 3); }

        static string Join(List<string> l) => l.Count == 1 ? l[0] : l.Count == 2 ? string.Format("{0} и {1}", l[0], l[1]) : string.Join(", ", l);

        static string NextLine((string key, string name, string unit)[] res, InvestRegistry.NetYear[][] all, int from)
        {
            int best = -1, bi = -1;
            for (int i = 0; i < res.Length; i++) { int y = InvestRegistry.NextShort(all[i], from, out _); if (y > 0 && (best < 0 || y < best)) { best = y; bi = i; } }
            return best < 0 ? "Дефицитов до 2050 года нет" : string.Format("Следующий дефицит: {0}, {1}", res[bi].name.ToLowerInvariant(), best);
        }

        /// <summary>The Details section stays open across rebuilds (year and scenario changes rebuild the block).</summary>
        static void KeepOpen(VisualElement body)
        {
            var d = body.parent; if (d == null) return; var head = d.Q(className: "details-head");
            if (detailsOpen)
            {
                body.style.display = DisplayStyle.Flex; d.AddToClassList("open");
                var ch = d.Q<Chevron>(); if (ch != null) ch.style.rotate = new Rotate(new Angle(0f));
            }
            head?.RegisterCallback<ClickEvent>(_ => detailsOpen = body.style.display == DisplayStyle.Flex);
        }

        public static Color Col(NetSt st) => st == NetSt.Short ? Bad : st == NetSt.Tight ? Warn : st == NetSt.None ? None : Ok;

        /// <summary>2026–2050, one cell per year: green — enough, amber — tight or no network yet, red — deficit. The shown year is outlined.
        /// A click moves the timeline to the year under the pointer.</summary>
        class Strip : VisualElement
        {
            readonly InvestRegistry.NetYear[] ys; readonly int sel; int hover = -1;
            public Strip(InvestRegistry.NetYear[] years, int year)
            {
                ys = years; sel = year; AddToClassList("w20-net-strip");
                generateVisualContent += Draw;
                RegisterCallback<PointerMoveEvent>(e => { int h = At(e.localPosition.x); if (h != hover) { hover = h; MarkDirtyRepaint(); } });
                RegisterCallback<PointerLeaveEvent>(_ => { hover = -1; MarkDirtyRepaint(); });
                RegisterCallback<PointerDownEvent>(e => { int h = At(e.localPosition.x); if (h >= 0) TwinState.Year = InvestRegistry.FirstYear + h; e.StopPropagation(); });
            }
            int At(float x) { float w = contentRect.width; if (w <= 0 || ys.Length == 0) return -1; return Mathf.Clamp((int)(x / (w / ys.Length)), 0, ys.Length - 1); }
            void Draw(MeshGenerationContext ctx)
            {
                var p = ctx.painter2D; var r = contentRect; float w = r.width, h = r.height; if (w <= 0 || h <= 0 || ys.Length == 0) return;
                float cw = w / ys.Length; int si = sel - InvestRegistry.FirstYear;
                for (int i = 0; i < ys.Length; i++)
                {
                    var c = Col(ys[i].St); float al = ys[i].St == NetSt.Ok ? 0.45f : 0.95f; if (i == hover) al = 1f;
                    p.fillColor = new Color(c.r, c.g, c.b, al);
                    float x0 = i * cw + 0.5f, x1 = (i + 1) * cw - 0.5f, y0 = 3f, y1 = h - 3f;
                    p.BeginPath(); p.MoveTo(new Vector2(x0, y0)); p.LineTo(new Vector2(x1, y0)); p.LineTo(new Vector2(x1, y1)); p.LineTo(new Vector2(x0, y1)); p.ClosePath(); p.Fill();
                }
                if (si >= 0 && si < ys.Length)
                {
                    float x0 = si * cw - 0.5f, x1 = (si + 1) * cw + 0.5f;
                    p.strokeColor = Color.white; p.lineWidth = 1.5f;
                    p.BeginPath(); p.MoveTo(new Vector2(x0, 0.75f)); p.LineTo(new Vector2(x1, 0.75f)); p.LineTo(new Vector2(x1, h - 0.75f)); p.LineTo(new Vector2(x0, h - 0.75f)); p.ClosePath(); p.Stroke();
                }
            }
        }
    }
}
