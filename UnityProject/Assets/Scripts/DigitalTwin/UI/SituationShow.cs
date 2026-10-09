using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Modules;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The situational-centre step of the presentation, one incident from alarm to solution:
    /// 1) the incident pulses on the map; 2) data streams run into it from the sources (cameras, sensors, 112, navigators, residents);
    /// 3) a one-card briefing (what, where, forecast); 4) a big red «Решить» (the presenter clicks, or it presses itself);
    /// 5) the solution plays out step by step and the map switches to "decision taken"; a small money line: damage without / with the twin.</summary>
    public class SituationShow : VisualElement
    {
        readonly SituationData.Incident inc; readonly SituationModule mod;
        float t; bool decided; float decT; Vector2 flown;
        readonly VisualElement sources, brief, info, steps, money; readonly Button solve; readonly List<VisualElement> srcRows = new List<VisualElement>(); readonly List<Label> srcCounts = new List<Label>();
        readonly Label status;
        static readonly (string name, Color c, int rate)[] Src =
        {
            ("Камеры · видеоаналитика", new Color(0.45f, 0.70f, 1f), 38), ("Детекторы трафика", new Color(0.36f, 0.86f, 0.74f), 61), ("Вызов 112", new Color(1f, 0.38f, 0.30f), 3),
            ("Навигаторы · GPS-треки", new Color(0.98f, 0.78f, 0.30f), 140), ("Обращения жителей", new Color(0.80f, 0.60f, 1f), 7)
        };
        static readonly string[] Actions = { "Объезд открыт: трасса → ул. Жетыген", "Светофоры: «зелёная волна» на объезде", "ДПС и эвакуатор в пути · 6 мин", "Водители предупреждены: табло и навигаторы" };
        public Action OnSolved;

        public SituationShow(SituationData.Incident i, SituationModule m)
        {
            inc = i; mod = m; flown = i.P; AddToClassList("sit-show"); pickingMode = PickingMode.Ignore;
            style.position = Position.Absolute; style.left = 0; style.right = 0; style.top = 0; style.bottom = 0;
            generateVisualContent += Draw;

            sources = new VisualElement { pickingMode = PickingMode.Ignore }; sources.AddToClassList("sit-sources"); Add(sources);
            var st = new Label("ИСТОЧНИКИ ДАННЫХ · В РЕАЛЬНОМ ВРЕМЕНИ") { pickingMode = PickingMode.Ignore }; st.AddToClassList("sit-h"); sources.Add(st);
            foreach (var (n, c, _) in Src)
            {
                var r = new VisualElement { pickingMode = PickingMode.Ignore }; r.AddToClassList("sit-src");
                var d = new VisualElement { pickingMode = PickingMode.Ignore }; d.AddToClassList("sit-dot"); d.style.backgroundColor = c; r.Add(d);
                r.Add(new Label(n) { pickingMode = PickingMode.Ignore });
                var cnt = new Label("0") { pickingMode = PickingMode.Ignore }; cnt.AddToClassList("sit-cnt"); r.Add(cnt); srcCounts.Add(cnt);
                r.style.opacity = 0; sources.Add(r); srcRows.Add(r);
            }

            brief = new VisualElement { pickingMode = PickingMode.Ignore }; brief.AddToClassList("sit-brief"); brief.style.opacity = 0; Add(brief);
            var bt = new Label("ИНЦИДЕНТ · " + DateTime.Now.ToString("HH:mm")) { pickingMode = PickingMode.Ignore }; bt.AddToClassList("sit-h"); bt.style.color = new Color(1f, 0.45f, 0.38f); brief.Add(bt);
            var title = new Label(i.Title) { pickingMode = PickingMode.Ignore }; title.AddToClassList("sit-title"); brief.Add(title);
            var where = new Label(i.Where) { pickingMode = PickingMode.Ignore }; where.AddToClassList("sit-where"); brief.Add(where);
            info = new VisualElement { pickingMode = PickingMode.Ignore }; brief.Add(info);
            Row(info, "Что видят датчики", i.FeedText);
            Row(info, "Прогноз без решения", Loc.N0(i.No.AffectedMax) + " чел. в заторе · ущерб " + SituationModule.MoneyText(i.No.Peak));
            Row(info, "Предложение двойника", i.Yes.Title);
            status = new Label("ожидает решения") { pickingMode = PickingMode.Ignore }; status.AddToClassList("sit-status"); brief.Add(status);

            solve = new Button(Solve) { text = "РЕШИТЬ", focusable = false }; solve.AddToClassList("sit-solve"); solve.style.opacity = 0; solve.style.display = DisplayStyle.None; brief.Add(solve);
            TwinUI.Instance?.BlockWhileHovered(solve);

            steps = new VisualElement { pickingMode = PickingMode.Ignore }; steps.AddToClassList("sit-steps"); brief.Add(steps);
            money = new VisualElement { pickingMode = PickingMode.Ignore }; money.AddToClassList("sit-money"); money.style.display = DisplayStyle.None; brief.Add(money);

            schedule.Execute(Tick).Every(16);
        }

        static void Row(VisualElement p, string k, string v)
        {
            var r = new VisualElement { pickingMode = PickingMode.Ignore }; r.AddToClassList("sit-row");
            var a = new Label(k) { pickingMode = PickingMode.Ignore }; a.AddToClassList("sit-k"); r.Add(a);
            var b = new Label(v) { pickingMode = PickingMode.Ignore }; b.AddToClassList("sit-v"); r.Add(b); p.Add(r);
        }

        void Solve()
        {
            if (decided) return; decided = true; decT = 0;
            solve.style.display = DisplayStyle.None; info.style.display = DisplayStyle.None; status.text = "решение принято · выполняется"; status.AddToClassList("ok");
            mod?.TourDecide(true);
            OnSolved?.Invoke();
        }

        void Tick()
        {
            if (panel == null) return;
            float dt = Mathf.Min(Time.unscaledDeltaTime, 0.05f); if (TourFx.Paused) dt = 0;
            t += dt; if (decided) decT += dt;
            var cur = SituationModule.Find(inc.Id);
            if (cur != null && (cur.P - flown).sqrMagnitude > 50f * 50f)
            {
                // the module rebuilt its incidents for the year: keep the camera on the live one
                flown = cur.P; var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
                if (cam != null) cam.FlyTo(new MapCamera.View { name = "incident", target = new Vector3(cur.P.x, CityGround.HeightAt(cur.P.x, cur.P.y), cur.P.y), distance = 2600f, yaw = cam.yaw, pitch = 46f });
            }
            for (int k = 0; k < srcRows.Count; k++)
            {
                float a = Mathf.Clamp01((t - 1.2f - k * 0.45f) / 0.5f); srcRows[k].style.opacity = a;
                if (a > 0) srcCounts[k].text = Loc.N0(Mathf.FloorToInt((t - 1.2f - k * 0.45f) * Src[k].rate * (decided ? 0.6f : 1f)));
            }
            brief.style.opacity = Mathf.Clamp01((t - 5.5f) / 0.7f);
            if (t > 8f && !decided) { solve.style.display = DisplayStyle.Flex; solve.style.opacity = Mathf.Clamp01((t - 8f) / 0.5f); float s = 1f + 0.05f * Mathf.Sin(t * 6f); solve.style.scale = new Scale(new Vector3(s, s, 1)); }
            if (t > 14f && !decided) Solve();                                         // the presenter did not click: the twin shows it anyway
            if (decided)
            {
                int n = Mathf.Clamp(Mathf.FloorToInt(decT / 1.1f) + 1, 0, Actions.Length);
                while (steps.childCount < n)
                {
                    var l = new Label("✓  " + Actions[steps.childCount]) { pickingMode = PickingMode.Ignore }; l.AddToClassList("sit-step"); steps.Add(l);
                }
                if (decT > Actions.Length * 1.1f + 0.4f && money.style.display == DisplayStyle.None) BuildMoney();
            }
            MarkDirtyRepaint();
        }

        void BuildMoney()
        {
            money.style.display = DisplayStyle.Flex; money.Clear();
            var h = new Label("Цена вопроса") { pickingMode = PickingMode.Ignore }; h.AddToClassList("sit-k"); money.Add(h);
            float no = inc.No.Peak, yes = inc.Yes.Peak, mx = Mathf.Max(no, 1f);
            Bar("без системы", no / mx, SituationModule.MoneyText(no), new Color(1f, 0.32f, 0.26f));
            Bar("с qTwin", yes / mx, SituationModule.MoneyText(yes), new Color(0.30f, 0.82f, 0.45f));
            var save = new Label("−" + SituationModule.MoneyText(Mathf.Max(0f, no - yes)) + " ущерба за одно ДТП") { pickingMode = PickingMode.Ignore }; save.AddToClassList("sit-save"); money.Add(save);
            void Bar(string k, float f, string v, Color c)
            {
                var r = new VisualElement { pickingMode = PickingMode.Ignore }; r.AddToClassList("sit-bar-row");
                var a = new Label(k) { pickingMode = PickingMode.Ignore }; a.AddToClassList("sit-bar-k"); r.Add(a);
                var tr = new VisualElement { pickingMode = PickingMode.Ignore }; tr.AddToClassList("sit-bar"); var fl = new VisualElement { pickingMode = PickingMode.Ignore }; fl.AddToClassList("sit-bar-f"); fl.style.backgroundColor = c; fl.style.width = Length.Percent(Mathf.Max(f, 0.03f) * 100f); tr.Add(fl); r.Add(tr);
                var b = new Label(v) { pickingMode = PickingMode.Ignore }; b.AddToClassList("sit-bar-v"); r.Add(b);
                money.Add(r);
            }
        }

        Vector2 IncidentPx()
        {
            var cam = Camera.main; if (cam == null || panel == null) return new Vector2(-1, -1);
            var cur = SituationModule.Find(inc.Id) ?? inc;                       // the module may rebuild its incidents for the year: follow its current pin
            var w = new Vector3(cur.P.x, CityGround.HeightAt(cur.P.x, cur.P.y) + 10f, cur.P.y);
            var sp = cam.WorldToScreenPoint(w); if (sp.z < 0) return new Vector2(-1, -1);
            var pp = RuntimePanelUtils.ScreenToPanel(panel, new Vector2(sp.x, Screen.height - sp.y));
            return this.WorldToLocal(pp);
        }

        void Draw(MeshGenerationContext ctx)
        {
            var p = ctx.painter2D; var q = IncidentPx(); if (q.x < 0) return;
            // pulsing alarm (red), turning green once solved
            var col = decided ? Color.Lerp(new Color(1f, 0.25f, 0.2f), new Color(0.3f, 0.85f, 0.45f), Mathf.Clamp01(decT / 2f)) : new Color(1f, 0.25f, 0.2f);
            for (int k = 0; k < 3; k++)
            {
                float ph = (t * 0.7f + k / 3f) % 1f;
                p.strokeColor = new Color(col.r, col.g, col.b, (1f - ph) * 0.9f); p.lineWidth = 2.4f; p.BeginPath(); p.Arc(q, 10f + ph * 70f, 0, 360); p.Stroke();
            }
            p.fillColor = col; p.BeginPath(); p.Arc(q, 8f, 0, 360); p.Fill();
            p.fillColor = Color.white; p.BeginPath(); p.Arc(q, 3f, 0, 360); p.Fill();
            // data streams from the source rows to the incident
            for (int k = 0; k < srcRows.Count; k++)
            {
                float a = Mathf.Clamp01((t - 1.4f - k * 0.45f) / 0.6f); if (a <= 0) continue;
                var r = srcRows[k]; var wb = r.worldBound; if (wb.width <= 0) continue;
                var s0 = this.WorldToLocal(new Vector2(wb.xMax + 4f, wb.center.y));
                var c1 = s0 + new Vector2((q.x - s0.x) * 0.45f, 0); var c2 = q + new Vector2(-(q.x - s0.x) * 0.25f, (s0.y - q.y) * 0.3f);
                var c = Src[k].c;
                p.strokeColor = new Color(c.r, c.g, c.b, 0.6f * a); p.lineWidth = 2.2f; p.BeginPath(); p.MoveTo(s0); p.BezierCurveTo(c1, c2, q); p.Stroke();
                // packets running along the curve
                for (int j = 0; j < 4; j++)
                {
                    float u = ((t * 0.55f + j * 0.25f + k * 0.11f) % 1f);
                    var pt = Bez(s0, c1, c2, q, u);
                    p.fillColor = new Color(c.r, c.g, c.b, a * (decided ? 0.5f : 1f)); p.BeginPath(); p.Arc(pt, 4f, 0, 360); p.Fill();
                }
            }
        }
        static Vector2 Bez(Vector2 a, Vector2 b, Vector2 c, Vector2 d, float u) { float v = 1 - u; return v * v * v * a + 3 * v * v * u * b + 3 * v * u * u * c + u * u * u * d; }
    }
}
