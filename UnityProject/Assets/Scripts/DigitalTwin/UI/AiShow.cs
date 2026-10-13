using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Modules;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Presentation step «ИИ-ассистент»: a question is typed in a big bubble, the assistant shows what it does in three chips
    /// (children by home, 10-minute walk zones, comparison of sites), the map lights up the homes far from a school, three variants pop up,
    /// a 10-minute ring opens around the best one and a compact answer card gives the result. Minimal text, everything computed from the twin.</summary>
    public class AiShow : VisualElement
    {
        const string Question = "Где построить новую школу?";
        static readonly Color AI = new Color(0.66f, 0.55f, 0.98f), OK = new Color(0.20f, 0.78f, 0.35f), WARN = new Color(0.96f, 0.65f, 0.14f);
        static readonly string[] Dn = { "Gate", "Golden", "Growing", "Green" };
        readonly AiModule.SchoolPlan plan; readonly int year;
        readonly Label q, cursor, legend, ringLbl; readonly VisualElement bubble, chipRow, card; readonly List<(VisualElement el, Label mark)> chips = new List<(VisualElement, Label)>();
        float t; int stage = -1;

        public AiShow(int y)
        {
            year = y; AddToClassList("aiw-show"); pickingMode = PickingMode.Ignore;
            style.position = Position.Absolute; style.left = 0; style.right = 0; style.top = 0; style.bottom = 0;
            generateVisualContent += Draw;
            plan = AiModule.PlanSchool(y);

            bubble = new VisualElement { pickingMode = PickingMode.Ignore }; bubble.AddToClassList("aiw-bubble"); Add(bubble);
            var who = new Label("ВОПРОС ИИ-АССИСТЕНТУ") { pickingMode = PickingMode.Ignore }; who.AddToClassList("aiw-bh"); bubble.Add(who);
            var line = new VisualElement { pickingMode = PickingMode.Ignore }; line.style.flexDirection = FlexDirection.Row; bubble.Add(line);
            q = new Label("") { pickingMode = PickingMode.Ignore }; q.AddToClassList("aiw-q"); line.Add(q);
            cursor = new Label("|") { pickingMode = PickingMode.Ignore }; cursor.AddToClassList("aiw-q"); cursor.AddToClassList("aiw-cursor"); line.Add(cursor);

            chipRow = new VisualElement { pickingMode = PickingMode.Ignore }; chipRow.AddToClassList("aiw-chips"); bubble.Add(chipRow);
            string[] cs = { "Считаю детей в " + Loc.N0(plan.Homes) + " домах", "Строю 10-минутные зоны от школ", "Сравниваю " + Loc.N0(Mathf.Max(plan.Cells, 1)) + " мест под школу" };
            foreach (var c in cs)
            {
                var el = new VisualElement { pickingMode = PickingMode.Ignore }; el.AddToClassList("aiw-chip"); el.style.opacity = 0;
                var mk = new Label("•") { pickingMode = PickingMode.Ignore }; mk.AddToClassList("aiw-mark"); el.Add(mk);
                el.Add(new Label(c) { pickingMode = PickingMode.Ignore }); chipRow.Add(el); chips.Add((el, mk));
            }

            legend = new Label("") { pickingMode = PickingMode.Ignore }; legend.AddToClassList("aiw-legend"); legend.style.display = DisplayStyle.None; bubble.Add(legend);
            ringLbl = new Label("10 минут пешком") { pickingMode = PickingMode.Ignore }; ringLbl.AddToClassList("aiw-ring"); ringLbl.style.display = DisplayStyle.None; Add(ringLbl);
            card = new VisualElement { pickingMode = PickingMode.Ignore }; card.AddToClassList("aiw-result"); card.style.opacity = 0; Add(card);
            BuildCard();
            schedule.Execute(Tick).Every(16);
        }

        void BuildCard()
        {
            var h = new Label("ОТВЕТ ИИ · ЛУЧШЕЕ МЕСТО — ВАРИАНТ A") { pickingMode = PickingMode.Ignore }; h.AddToClassList("aiw-bh"); card.Add(h);
            if (plan.Pick.Count == 0) { card.Add(new Label($"В {year} году все дома в 10 минутах от школы.") { pickingMode = PickingMode.Ignore }); return; }
            var big = new Label(Loc.N0(plan.Pick[0].kids)) { pickingMode = PickingMode.Ignore }; big.AddToClassList("aiw-big"); card.Add(big);
            var sub = new Label("детей получат школу в 10 минутах пешком") { pickingMode = PickingMode.Ignore }; sub.AddToClassList("aiw-sub"); card.Add(sub);
            int pct = Mathf.RoundToInt(100f * Mathf.Min(plan.Seats, plan.Gap) / Mathf.Max(plan.Gap, 1f));
            Fig("Школа", Loc.N0(plan.Seats) + " мест");
            Fig("Дефицит " + Dn[plan.D] + " " + year, "закрыт на " + pct + " %");
            string[] L = { "A", "B", "C" };
            for (int i = 1; i < plan.Pick.Count; i++) Fig("Вариант " + L[i], Loc.N0(plan.Pick[i].kids) + " детей");
            var n = new Label("Проверено " + Loc.N0(plan.Homes) + " домов и " + Loc.N0(plan.Cells) + " мест за секунды · данные двойника") { pickingMode = PickingMode.Ignore }; n.AddToClassList("aiw-note"); card.Add(n);
            void Fig(string k, string v)
            {
                var r = new VisualElement { pickingMode = PickingMode.Ignore }; r.AddToClassList("aiw-fig");
                var a = new Label(k) { pickingMode = PickingMode.Ignore }; a.AddToClassList("aiw-fk"); r.Add(a);
                var b = new Label(v) { pickingMode = PickingMode.Ignore }; b.AddToClassList("aiw-fv"); r.Add(b); card.Add(r);
            }
        }

        void Tick()
        {
            if (panel == null) return;
            float dt = Mathf.Min(Time.unscaledDeltaTime, 0.05f) * Time.timeScale; if (TourFx.Paused) dt = 0; t += dt;   // follows the video mode speed-up
            // 1. typing
            int n = Mathf.Clamp(Mathf.FloorToInt((t - 0.6f) / 0.075f), 0, Question.Length); q.text = Question.Substring(0, n);
            cursor.style.opacity = n < Question.Length || t < 4.5f ? (Mathf.Repeat(t, 0.9f) < 0.5f ? 1f : 0f) : 0f;
            // 2. the assistant works: chips with a spinner, then a check
            for (int i = 0; i < chips.Count; i++)
            {
                float t0 = 3.4f + i * 1.3f; var (el, mk) = chips[i];
                el.style.opacity = Mathf.Clamp01((t - t0) / 0.4f);
                bool done = t > t0 + 1.2f; mk.text = done ? "✓" : "◐◓◑◒"[Mathf.FloorToInt(t * 8f) % 4].ToString(); el.EnableInClassList("done", done);
            }
            // 3. map stages
            int st = t < 4.4f ? 0 : t < 7.6f ? 1 : t < 11.5f ? 2 : 3;
            if (st != stage) { stage = st; Stage(st); }
            card.style.opacity = Mathf.Clamp01((t - 11.8f) / 0.6f);
            if (plan.Pick.Count > 0 && t > 10.8f)
            {
                var b = plan.Pick[0].p; var top = Px(new Vector3(b.x, CityGround.HeightAt(b.x, b.y + 800f) + 8f, b.y + 800f));
                if (!float.IsNaN(top.x)) { ringLbl.style.display = DisplayStyle.Flex; ringLbl.style.left = top.x - 70f; ringLbl.style.top = top.y - 26f; }
            }
            MarkDirtyRepaint();
        }

        void Stage(int s)
        {
            if (plan.Pick.Count == 0) return;
            var best = plan.Pick[0].p;
            if (s == 1)
            {
                // homes farther than 10 minutes from a school
                TintLayer.Enable(); TintLayer.Apply(b => plan.Unc.Contains(b.Bid) ? A(WARN, 0.8f) : default);
                TwinUI.Instance?.FillLegend(new[] { (WARN, "дома дальше 10 мин от школы") });
                legend.style.display = DisplayStyle.Flex; legend.text = "<color=#F5A524>●</color> дома, откуда до школы дальше 10 минут пешком";
                Fly(Centre(), 7200f, 52f);
            }
            else if (s == 2)
            {
                string[] L = { "A", "B", "C" };
                var pins = new List<MapPins.Pin>();
                for (int i = 0; i < plan.Pick.Count; i++)
                {
                    var p = plan.Pick[i].p;
                    pins.Add(new MapPins.Pin { Id = "v" + i, Label = L[i] + " · " + Loc.N0(plan.Pick[i].kids) + " детей", World = new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + 40f, p.y), Fill = i == 0 ? AI : new Color(0.75f, 0.75f, 0.75f), ShowLabel = true, Size = i == 0 ? 20f : 13f });
                }
                MapPins.Instance?.Set(pins); MapPins.Instance?.Select("v0");
            }
            else if (s == 3)
            {
                TintLayer.Enable(); TintLayer.Apply(b => plan.Near.Contains(b.Bid) ? A(OK, 0.95f) : plan.Unc.Contains(b.Bid) ? A(WARN, 0.55f) : default);
                TwinUI.Instance?.FillLegend(new[] { (OK, "в 10 мин от новой школы"), (WARN, "пока дальше 10 мин"), (AI, "варианты ИИ") });
                legend.text = "<color=#33C75A>●</color> получат школу рядом    <color=#F5A524>●</color> пока дальше 10 минут";
                Fly(best, 3400f, 50f);
            }
        }
        Vector2 Centre() { Vector2 c = Vector2.zero; foreach (var x in plan.Pick) c += x.p; return c / Mathf.Max(1, plan.Pick.Count); }
        static Color A(Color c, float a) { c.a = a; return c; }
        static void Fly(Vector2 p, float dist, float pitch)
        {
            var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
            if (cam != null) cam.FlyTo(new MapCamera.View { name = "ai", target = new Vector3(p.x, CityGround.HeightAt(p.x, p.y), p.y), distance = dist, yaw = cam.yaw, pitch = pitch });
        }

        Vector2 Px(Vector3 w)
        {
            var cam = Camera.main; if (cam == null || panel == null) return new Vector2(float.NaN, 0);
            var sp = cam.WorldToScreenPoint(w); if (sp.z < 0) return new Vector2(float.NaN, 0);
            return this.WorldToLocal(RuntimePanelUtils.ScreenToPanel(panel, new Vector2(sp.x, Screen.height - sp.y)));
        }

        void Draw(MeshGenerationContext ctx)
        {
            if (plan.Pick.Count == 0 || t < 7.6f) return;
            var p = ctx.painter2D; var best = plan.Pick[0].p;
            // the 10-minute walk ring opens around variant A, then breathes
            float open = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((t - 8.6f) / 2.2f)); if (open <= 0) return;
            float R = 800f * open; const int N = 72; var pts = new Vector2[N]; float gy = CityGround.HeightAt(best.x, best.y) + 8f;
            for (int i = 0; i < N; i++)
            {
                float a = i * Mathf.PI * 2f / N; float x = best.x + Mathf.Cos(a) * R, z = best.y + Mathf.Sin(a) * R;
                pts[i] = Px(new Vector3(x, Mathf.Max(gy, CityGround.HeightAt(x, z) + 8f), z)); if (float.IsNaN(pts[i].x)) return;
            }
            p.fillColor = new Color(AI.r, AI.g, AI.b, 0.10f); p.BeginPath(); p.MoveTo(pts[0]); for (int i = 1; i < N; i++) p.LineTo(pts[i]); p.ClosePath(); p.Fill();
            float pulse = 0.65f + 0.35f * Mathf.Sin(t * 3f);
            p.strokeColor = new Color(AI.r, AI.g, AI.b, 0.95f * pulse); p.lineWidth = 2.5f; p.BeginPath(); p.MoveTo(pts[0]); for (int i = 1; i < N; i++) p.LineTo(pts[i]); p.ClosePath(); p.Stroke();
        }
    }
}
