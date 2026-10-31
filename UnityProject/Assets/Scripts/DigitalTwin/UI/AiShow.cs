using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Modules;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Presentation step «ИИ-ассистент»: the question is typed in a big bubble, the assistant shows three short steps,
    /// the map lights up the homes far from a school and the schools that exist, three numbered sites appear, then the best one opens
    /// with its 10-minute ring and an answer card. The card's ‹ › (or a click on a pin) flips to the 2nd and 3rd site, each with its own
    /// number, school size, reason for its rank and its own homes in green; while nobody clicks, the step shows them in turn.
    /// Everything is computed from the twin (AiModule.PlanSchool).</summary>
    public class AiShow : VisualElement
    {
        const string Question = "Где построить новую школу?", QuestionIn = "Где построить новую школу в {0}?";
        static readonly Color AI = new Color(0.66f, 0.55f, 0.98f), OK = new Color(0.20f, 0.78f, 0.35f), WARN = new Color(0.96f, 0.65f, 0.14f), SCHOOL = new Color(0.36f, 0.68f, 1f);
        static readonly string[] Dn = { "Gate", "Golden", "Growing", "Green" };
        const float TPins = 6.4f, TFirst = 8.4f, TAuto2 = 15.5f, TAuto3 = 21.5f;
        readonly AiModule.SchoolPlan plan; readonly int year; readonly string question;
        readonly Label q, cursor, ringLbl, step, big, why, seats, homes; readonly VisualElement bubble, chipRow, legend, card, cardBody;
        readonly List<(VisualElement el, Label mark)> chips = new List<(VisualElement, Label)>();
        readonly Vector2[] ring = new Vector2[72];
        float t, selT = -10f; int stage = -1, sel = -1; bool manual;

        /// <summary>district ≥ 0: the question names the district and the sites are searched there; −1: the district with the largest seat gap.</summary>
        public AiShow(int y, int district = -1)
        {
            year = y; AddToClassList("aiw-show"); pickingMode = PickingMode.Ignore;
            style.position = Position.Absolute; style.left = 0; style.right = 0; style.top = 0; style.bottom = 0;
            generateVisualContent += Draw;
            plan = AiModule.PlanSchool(y, district);
            question = district >= 0 && district < 4 ? string.Format(QuestionIn, Dn[district]) : Question;

            bubble = El(this, "aiw-bubble");
            var who = new Label("ВОПРОС ИИ-АССИСТЕНТУ") { pickingMode = PickingMode.Ignore }; who.AddToClassList("aiw-bh"); bubble.Add(who);
            var line = El(bubble, null); line.style.flexDirection = FlexDirection.Row;
            q = new Label("") { pickingMode = PickingMode.Ignore }; q.AddToClassList("aiw-q"); q.AddToClassList("no-tr"); line.Add(q);   // typed already translated
            cursor = new Label("|") { pickingMode = PickingMode.Ignore }; cursor.AddToClassList("aiw-q"); cursor.AddToClassList("aiw-cursor"); line.Add(cursor);

            // the assistant's work in three short steps
            chipRow = El(bubble, "aiw-chips");
            string[] cs = { string.Format("{0} домов", Loc.N0(plan.Homes)), "10 минут пешком", string.Format("{0} участков", Loc.N0(Mathf.Max(plan.Cells, 1))) };
            foreach (var c in cs)
            {
                var el = El(chipRow, "aiw-chip"); el.style.opacity = 0;
                var mk = new Label("•") { pickingMode = PickingMode.Ignore }; mk.AddToClassList("aiw-mark"); el.Add(mk);
                el.Add(new Label(c) { pickingMode = PickingMode.Ignore }); chips.Add((el, mk));
            }
            // the map key, once the map speaks
            legend = El(bubble, "w23-legend"); legend.style.display = DisplayStyle.None;
            Key(legend, WARN, "дальше 10 мин от школы"); Key(legend, SCHOOL, "школы"); Key(legend, OK, "получат школу рядом");

            ringLbl = new Label("10 минут пешком") { pickingMode = PickingMode.Ignore }; ringLbl.AddToClassList("aiw-ring"); ringLbl.style.display = DisplayStyle.None; Add(ringLbl);

            // the answer card: rank and arrows, the big number, one line why, two figures, the method folded
            card = new VisualElement(); card.AddToClassList("aiw-result"); card.AddToClassList("w23-card"); card.style.opacity = 0; card.style.display = DisplayStyle.None; Add(card);
            var head = El(card, "w23-head");
            var hl = new Label("ОТВЕТ ИИ") { pickingMode = PickingMode.Ignore }; hl.AddToClassList("aiw-bh"); hl.AddToClassList("w23-eyebrow"); head.Add(hl);
            if (plan.Sites.Count == 0)
            {
                var none = new Label(string.Format("В {0} году все дома в 10 минутах от школы.", year)) { pickingMode = PickingMode.Ignore }; none.AddToClassList("w23-why"); card.Add(none);
            }
            else
            {
                var nav = El(head, "w23-nav");
                nav.Add(Arrow(true, () => Pick((sel + plan.Sites.Count - 1) % plan.Sites.Count, true)));
                step = new Label("") { pickingMode = PickingMode.Ignore }; step.AddToClassList("w23-step"); nav.Add(step);
                nav.Add(Arrow(false, () => Pick((sel + 1) % plan.Sites.Count, true)));
                cardBody = El(card, "w23-body");
                big = new Label("") { pickingMode = PickingMode.Ignore }; big.AddToClassList("aiw-big"); cardBody.Add(big);
                var sub = new Label("детей получат школу в 10 минутах пешком") { pickingMode = PickingMode.Ignore }; sub.AddToClassList("aiw-sub"); cardBody.Add(sub);
                why = new Label("") { pickingMode = PickingMode.Ignore }; why.AddToClassList("w23-why"); cardBody.Add(why);
                seats = Fig(cardBody, "Школа"); homes = Fig(cardBody, "До школы сейчас");
                var how = Widgets.Details(card, "Как считается");
                var m = new Label(string.Format("Не хватает мест в школах {0}: {1} в {2} году. 10 минут пешком = 800 м. ИИ проверил {3} домов, {4} из них дальше 10 минут от школы, и сравнил {5} участков по 400 м. Дети школьного возраста — 12 % жителей. Варианты — не ближе 1,5 км друг к другу.",
                    Dn[plan.D], Loc.N0(plan.Gap), year, Loc.N0(plan.Homes), Loc.N0(plan.Far), Loc.N0(plan.Cells))); m.AddToClassList("w23-how"); how.Add(m);
                card.Add(SourceTags.Line(Data.TwinModels.Social, Data.Sources.ModelCity));
            }
            schedule.Execute(Tick).Every(16);
        }

        static VisualElement El(VisualElement parent, string cls) { var e = new VisualElement { pickingMode = PickingMode.Ignore }; if (cls != null) e.AddToClassList(cls); parent.Add(e); return e; }
        static void Key(VisualElement parent, Color c, string text)
        {
            var k = El(parent, "w23-key"); var d = El(k, "w23-kdot"); d.style.backgroundColor = c;
            k.Add(new Label(text) { pickingMode = PickingMode.Ignore });
        }
        static Label Fig(VisualElement parent, string k)
        {
            var r = El(parent, "aiw-fig");
            var a = new Label(k) { pickingMode = PickingMode.Ignore }; a.AddToClassList("aiw-fk"); r.Add(a);
            var b = new Label("") { pickingMode = PickingMode.Ignore }; b.AddToClassList("aiw-fv"); r.Add(b); return b;
        }
        static VisualElement Arrow(bool left, System.Action a)
        {
            var b = new VisualElement(); b.AddToClassList("w23-arrow");
            var ch = new Chevron { Color = new Color(0.92f, 0.90f, 1f) }; ch.style.rotate = new Rotate(new Angle(left ? 90f : -90f)); b.Add(ch);
            b.AddManipulator(new Clickable(a)); return b;
        }

        /// <summary>Shows site i: the map (its homes green, its pin selected, the camera on it), the ring opens again, the card changes.</summary>
        void Pick(int i, bool byHand)
        {
            if (plan.Sites.Count == 0) return;
            if (byHand) manual = true;
            sel = i; selT = t;
            AiModule.ShowSchoolSite(plan, i, 3400f, k => Pick(k, true));
            var s = plan.Sites[i];
            step.text = string.Format("№{0} из {1}", i + 1, plan.Sites.Count);
            big.text = Loc.N0(s.Kids);
            why.text = AiModule.SchoolWhy(plan, i); why.EnableInClassList("best", i == 0);
            seats.text = string.Format("{0} мест", Loc.N0(s.Seats));
            homes.text = s.Nearest < 1e6f ? string.Format("{0} км", Loc.N1(s.Nearest / 1000f)) : "—";
            if (cardBody != null) { cardBody.style.opacity = 0.35f; cardBody.schedule.Execute(() => cardBody.style.opacity = 1f).StartingIn(120); }
        }

        void Tick()
        {
            if (panel == null) return;
            float dt = Mathf.Min(TwinState.RealDelta, 0.05f) * Time.timeScale; if (TourFx.Paused) dt = 0; t += dt;   // follows the video mode speed-up
            // 1. typing: the question in the language of the screen, typed in the same time whatever its length
            var qs = UiTranslator.Tr(question);
            int n = Mathf.Clamp(Mathf.FloorToInt((t - 0.5f) / (0.09f * question.Length / Mathf.Max(qs.Length, 1))), 0, qs.Length); q.text = qs.Substring(0, n);
            cursor.style.opacity = n < qs.Length || t < 3.6f ? (Mathf.Repeat(t, 0.9f) < 0.5f ? 1f : 0f) : 0f;
            // 2. the assistant works: three short chips with a spinner, then a check; they give way to the map key with the answer
            for (int i = 0; i < chips.Count; i++)
            {
                float t0 = 2.9f + i * 0.9f; var (el, mk) = chips[i];
                el.style.opacity = Mathf.Clamp01((t - t0) / 0.3f);
                bool done = t > t0 + 0.8f; mk.text = done ? "✓" : "◐◓◑◒"[Mathf.FloorToInt(t * 8f) % 4].ToString(); el.EnableInClassList("done", done);
            }
            chipRow.style.display = t < TPins ? DisplayStyle.Flex : DisplayStyle.None;
            legend.style.display = t >= TPins ? DisplayStyle.Flex : DisplayStyle.None;
            // 3. the map
            int st = t < 3.6f ? 0 : t < TPins ? 1 : t < TFirst ? 2 : 3;
            if (st != stage) { stage = st; Stage(st); }
            if (!manual && plan.Sites.Count > 1 && sel == 0 && t > TAuto2) Pick(1, false);
            if (!manual && plan.Sites.Count > 2 && sel == 1 && t > TAuto3) Pick(2, false);
            float co = Mathf.Clamp01((t - TFirst - 0.6f) / 0.5f); card.style.opacity = co; card.style.display = co > 0 ? DisplayStyle.Flex : DisplayStyle.None;
            ringLbl.style.display = DisplayStyle.None;
            if (sel >= 0 && t - selT > 1.6f)
            {
                var b = plan.Sites[sel].P; var top = Px(new Vector3(b.x, CityGround.HeightAt(b.x, b.y + 800f) + 8f, b.y + 800f));
                if (!float.IsNaN(top.x)) { ringLbl.style.display = DisplayStyle.Flex; ringLbl.style.left = top.x - 70f; ringLbl.style.top = top.y - 26f; }
            }
            MarkDirtyRepaint();
        }

        void Stage(int s)
        {
            if (plan.Sites.Count == 0) return;
            if (s == 1)
            {
                // homes farther than 10 minutes from a school, amber; the schools of that year are drawn as blue dots; camera on all sites
                var unc = plan.Unc;
                TintLayer.Enable(); TintLayer.Apply(b => unc.Contains(b.Bid) ? A(WARN, 0.75f) : default);
                TwinUI.Instance?.FillLegend(new[] { (WARN, "дальше 10 мин от школы"), (SCHOOL, "школы"), (OK, "получат школу рядом"), (AI, "варианты ИИ") });
                Vector2 c = Vector2.zero; foreach (var x in plan.Sites) c += x.P; c /= plan.Sites.Count;
                float spread = 0; foreach (var x in plan.Sites) spread = Mathf.Max(spread, (x.P - c).magnitude);
                Fly(c, Mathf.Clamp(spread * 2.1f + 2600f, 4200f, 15000f), 56f);
            }
            else if (s == 2)
            {
                // the three sites appear, numbered by rank
                var pins = new List<MapPins.Pin>();
                for (int i = 0; i < plan.Sites.Count; i++)
                {
                    var p = plan.Sites[i].P; int k = i;
                    pins.Add(new MapPins.Pin { Id = "v" + i, Label = string.Format("№{0} · {1} детей", i + 1, Loc.N0(plan.Sites[i].Kids)), World = new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + 40f, p.y),
                        Fill = AI, ShowLabel = true, Size = 14f, OnClick = () => Pick(k, true) });
                }
                MapPins.Instance?.Set(pins);
            }
            else if (s == 3 && sel < 0) Pick(0, false);
        }
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

        /// <summary>Projects the 10-minute circle (800 m) around p onto the screen, following the ground; false when it leaves the view.</summary>
        bool Ring(Vector2 c, float R)
        {
            int N = ring.Length; float gy = CityGround.HeightAt(c.x, c.y) + 8f;
            for (int i = 0; i < N; i++)
            {
                float a = i * Mathf.PI * 2f / N; float x = c.x + Mathf.Cos(a) * R, z = c.y + Mathf.Sin(a) * R;
                ring[i] = Px(new Vector3(x, Mathf.Max(gy, CityGround.HeightAt(x, z) + 8f), z)); if (float.IsNaN(ring[i].x)) return false;
            }
            return true;
        }
        void Path(Painter2D p) { p.BeginPath(); p.MoveTo(ring[0]); for (int i = 1; i < ring.Length; i++) p.LineTo(ring[i]); p.ClosePath(); }

        void Draw(MeshGenerationContext ctx)
        {
            if (plan.Sites.Count == 0 || stage < 1) return;
            var p = ctx.painter2D; float w = contentRect.width, h = contentRect.height;
            // the schools that exist that year: small blue dots with a dark rim (the reason the amber homes are amber)
            float fade = Mathf.Clamp01((t - 3.8f) / 0.8f);
            foreach (var s in plan.Schools)
            {
                var v = Px(new Vector3(s.x, CityGround.HeightAt(s.x, s.y) + 6f, s.y));
                if (float.IsNaN(v.x) || v.x < -10 || v.y < 0 || v.x > w + 10 || v.y > h + 10 || this.LocalToWorld(v).y < 70f) continue;   // not over the header
                p.fillColor = new Color(0.04f, 0.06f, 0.10f, 0.75f * fade); p.BeginPath(); p.Arc(v, 6f, 0f, 360f); p.Fill();
                p.fillColor = new Color(SCHOOL.r, SCHOOL.g, SCHOOL.b, fade); p.BeginPath(); p.Arc(v, 4f, 0f, 360f); p.Fill();
            }
            if (stage < 2) return;
            // the other sites: a quiet dashed 10-minute circle each
            float app = Mathf.Clamp01((t - TPins) / 0.8f);
            for (int k = 0; k < plan.Sites.Count; k++)
            {
                if (k == sel || !Ring(plan.Sites[k].P, 800f)) continue;
                p.strokeColor = new Color(0.86f, 0.84f, 0.95f, 0.55f * app); p.lineWidth = 1.6f;
                for (int i = 0; i < ring.Length; i += 2) { p.BeginPath(); p.MoveTo(ring[i]); p.LineTo(ring[(i + 1) % ring.Length]); p.Stroke(); }
            }
            if (sel < 0) return;
            // the chosen site: the circle opens, a soft glow and a crisp edge that breathes
            float open = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((t - selT) / 1.4f));
            if (open <= 0 || !Ring(plan.Sites[sel].P, 800f * open)) return;
            p.fillColor = new Color(AI.r, AI.g, AI.b, 0.13f); Path(p); p.Fill();
            p.strokeColor = new Color(AI.r, AI.g, AI.b, 0.18f); p.lineWidth = 9f; Path(p); p.Stroke();
            float pulse = 0.75f + 0.25f * Mathf.Sin(t * 3f);
            p.strokeColor = new Color(0.80f, 0.72f, 1f, 0.95f * pulse); p.lineWidth = 2.5f; Path(p); p.Stroke();
        }
    }
}
