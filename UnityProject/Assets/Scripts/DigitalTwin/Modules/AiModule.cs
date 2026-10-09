using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;
using Inc = AlatauCity.DigitalTwin.Modules.SituationData.Incident;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>M5 — AI control. The AI is shown as a helper inside the twin, not a black box:
    /// (1) an assistant that answers questions about the city with text + camera + layer + chart, listing the tool calls it made;
    /// (2) a decision autopilot: detects an anomaly, proposes 2–3 options with a forecast, recommends one and explains why;
    /// (3) "without AI / with AI" on the same incident; (4) seven short AI stories.
    /// Demo: answers are scripted (keyword intents) but every number is computed from the twin's data.
    /// Architecture for production: an LLM (Claude API) with the same tools — set_year, fly_to, show_layer, run_scenario, explain.</summary>
    public class AiModule : TwinModuleBase
    {
        public override string Id => "ai";
        public override string TabKey => "tab_ai";

        static int view;                        // 0 assistant, 1 autopilot, 2 without/with AI, 3 stories
        static bool autoMode; static string apInc = "leak"; static int story = -1;
        static readonly List<Answer> chat = new List<Answer>();
        static readonly List<string> log = new List<string>();
        static readonly HashSet<string> applied = new HashSet<string>();

        static readonly Color AI = new Color(0.66f, 0.55f, 0.98f), OK = new Color(0.20f, 0.78f, 0.35f), WARN = new Color(0.96f, 0.65f, 0.14f),
            BAD = new Color(1f, 0.23f, 0.18f), MUTED = new Color(0.53f, 0.53f, 0.53f), WHITE = new Color(0.99f, 0.99f, 0.99f), BLUE = new Color(0.30f, 0.64f, 1f);

        Label eyebrow; VisualElement body, leftBody; readonly List<Button> viewChips = new List<Button>(); TextField input;
        (Color, string)[] legend;

        public override (Color, string)[] Legend => legend;
        public override void OnEnter() { }
        public override void OnExit() { MapPins.Instance?.Clear(); TintLayer.Disable(); LineLayers.Instance?.HideAll(); MapCamera.Typing = false; }

        static int Y => TwinState.Year; static int S => (int)TwinState.Scenario;

        // ------------------------------------------------------------------ answer model
        public class Answer
        {
            public string Q, Text, Sources; public int Conf; public List<string> Tools = new List<string>(); public List<(string, string)> Facts = new List<(string, string)>();
            public float[][] Series; public float YMin; public Color[] Colors; public string[] SeriesNames; public string[] XText; public string ChartTitle; public Action Apply;
        }

        // ------------------------------------------------------------------ panel
        protected override void Build()
        {
            var top = Widgets.Block(panel); top.AddToClassList("ai-card");
            eyebrow = Widgets.Eyebrow(top, "");
            var s = new Label(Loc.T("ai_sum")); s.AddToClassList("summary"); s.style.fontSize = 15; s.style.marginBottom = 10; top.Add(s);
            var chips = new VisualElement(); chips.AddToClassList("chips"); chips.style.marginBottom = 0; top.Add(chips); viewChips.Clear();
            string[] vk = { "ai_v_chat", "ai_v_auto", "ai_v_cmp", "ai_v_stories" };
            for (int i = 0; i < 4; i++) { int k = i; var b = new Button(() => { view = k; ClearMap(); Refresh(); }) { text = Loc.T(vk[i]) }; b.AddToClassList("chip"); chips.Add(b); viewChips.Add(b); }
            leftBody = new VisualElement(); panel.Add(leftBody);
            Right();
            body = new VisualElement(); panel.Add(body);
        }

        public override void Refresh()
        {
            if (panel == null || body == null || !TwinData.Ready || !CityStats.Ready) return;
            eyebrow.text = (Loc.T("tab_ai") + " · " + Y + " · " + TwinScenario.Name(TwinState.Scenario)).ToUpperInvariant();
            for (int i = 0; i < viewChips.Count; i++) viewChips[i].EnableInClassList("active", i == view);
            body.Clear(); leftBody.Clear(); MapCamera.Typing = false;
            switch (view)
            {
                case 0: Chat(); break;
                case 1: Autopilot(); break;
                case 2: Compare(); break;
                case 3: Stories(); break;
            }
        }

        static void ClearMap() { MapPins.Instance?.Clear(); TintLayer.Disable(); LineLayers.Instance?.HideAll(); }
        void SetLegend((Color, string)[] l) { legend = l; TwinUI.Instance?.FillLegend(l); }

        // ================================================================== 1. assistant
        static readonly string[] Suggest =
        {
            "Где в 2035 не хватает школ?", "Что будет, если ЛРТ до Golden запустят на 2 года позже?", "Покажи самые рискованные стройки",
            "Когда впервые не хватит электроэнергии?", "Какие дома затопит паводок?", "Где поставить новую школу?",
        };

        void Chat()
        {
            var b = Widgets.Block(leftBody, Loc.T("ai_ask"), Loc.T("ai_ask_sub")); b.AddToClassList("ai-card");
            var row = new VisualElement(); row.AddToClassList("row"); b.Add(row);
            input = new TextField(); input.AddToClassList("ai-input"); input.style.flexGrow = 1; row.Add(input);
            input.textEdition.placeholder = Loc.T("ai_placeholder"); input.textEdition.hidePlaceholderOnFocus = true;
            input.RegisterCallback<FocusInEvent>(_ => MapCamera.Typing = true);
            input.RegisterCallback<FocusOutEvent>(_ => MapCamera.Typing = false);
            input.RegisterCallback<KeyDownEvent>(e => { if (e.keyCode == KeyCode.Return || e.keyCode == KeyCode.KeypadEnter) { e.StopPropagation(); Ask(input.value); } }, TrickleDown.TrickleDown);
            var go = Widgets.Btn(Loc.T("ai_go"), () => Ask(input.value), "primary", "small"); go.style.marginLeft = 6; row.Add(go);
            var sg = new VisualElement(); sg.AddToClassList("chips"); sg.style.marginTop = 10; sg.style.marginBottom = 0; b.Add(sg);
            foreach (var q in Suggest) { var qq = q; var c = new Button(() => Ask(qq)) { text = q }; c.AddToClassList("chip"); c.AddToClassList("ai-chip"); sg.Add(c); }

            foreach (var a in Enumerable.Reverse(chat).Take(3)) Card(a, a == chat.LastOrDefault());
            if (chat.Count == 0)
            {
                // empty state: what the twin would look at first (one click = the question)
                var st = Widgets.Block(body, "С чего начать", "один клик — ответ на карте");
                (string t, string q)[] tips =
                {
                    ("Электроэнергия: когда и где впервые не хватит мощности", Suggest[3]),
                    ("Школы: районы с дефицитом мест в 2035 году", Suggest[0]),
                    ("Стройка: объекты с наибольшим риском срыва срока", Suggest[2]),
                    ("Паводок: какие дома попадут в зону затопления", Suggest[4]),
                };
                foreach (var tp in tips)
                {
                    var qq = tp.q; var c = new Button(() => Ask(qq)); c.AddToClassList("insight"); c.AddToClassList("insight-btn");
                    var l = new Label(tp.t) { pickingMode = PickingMode.Ignore }; c.Add(l);
                    var go2 = new Label("Спросить →") { pickingMode = PickingMode.Ignore }; go2.AddToClassList("insight-go"); c.Add(go2);
                    st.Add(c);
                }
            }
            var n = Widgets.Block(leftBody); var note = new Label(Loc.T("ai_arch")); note.AddToClassList("note"); n.Add(note);
        }

        /// <summary>Presentation tour hooks.</summary>
        public void TourAsk(string q) { view = 0; Ask(q); }
        public void TourView(int v, int st = -1) { view = v; story = st; ClearMap(); Refresh(); }

        void Ask(string q)
        {
            q = (q ?? "").Trim(); if (q.Length == 0) return;
            var a = Respond(q); a.Q = q; chat.Add(a); if (chat.Count > 12) chat.RemoveAt(0);
            ClearMap(); a.Apply?.Invoke();
            if (input != null) input.value = "";
            MapCamera.Typing = false; view = 0; Refresh();
        }

        void Card(Answer a, bool latest)
        {
            var c = Widgets.Block(body); c.AddToClassList("ai-card"); if (latest) c.AddToClassList("latest");
            var q = new Label(Loc.T("ai_you") + " " + a.Q); q.AddToClassList("note"); q.style.marginBottom = 6; c.Add(q);
            var head = new VisualElement(); head.AddToClassList("row"); head.style.marginBottom = 6; c.Add(head);
            var dot = new VisualElement(); dot.AddToClassList("ai-dot"); head.Add(dot);
            var who = new Label(Loc.T("ai_name")); who.AddToClassList("ai-who"); head.Add(who);
            if (a.Conf > 0) { var cf = new Label(string.Format(Loc.T("ai_conf"), a.Conf)); cf.AddToClassList("ai-conf"); head.Add(cf); }
            var t = new Label(a.Text); t.AddToClassList("ai-text"); c.Add(t);
            if (a.Facts.Count > 0) { var fb = new VisualElement(); fb.style.marginTop = 8; c.Add(fb); foreach (var (k, v) in a.Facts) fb.Add(Widgets.Fact(k, v)); }
            if (a.Series != null)
            {
                if (a.ChartTitle != null) { var ct = new Label(a.ChartTitle); ct.AddToClassList("note"); ct.style.marginTop = 10; c.Add(ct); }
                var ch = new TwinChart(); ch.Series = a.Series; ch.Colors = a.Colors; ch.Stacked = false; ch.LineWidths = a.Series.Select((_, i) => i == 0 ? 2.5f : 1.6f).ToArray(); ch.XText = a.XText; ch.YMin = a.YMin; ch.MarkYear = a.XText == null ? Y : -1; ch.Refresh(); c.Add(ch);
                if (a.SeriesNames != null) { var lg = new VisualElement(); lg.AddToClassList("legend"); c.Add(lg); for (int i = 0; i < a.SeriesNames.Length; i++) lg.Add(Widgets.LegendItem(a.Colors[i], a.SeriesNames[i])); }
            }
            if (a.Tools.Count > 0)
            {
                var tl = new Label(Loc.T("ai_tools").ToUpperInvariant()); tl.AddToClassList("note"); tl.style.marginTop = 10; tl.style.marginBottom = 3; tl.style.letterSpacing = 1; c.Add(tl);
                foreach (var x in a.Tools) { var l = new Label("→ " + x); l.AddToClassList("ai-tool"); c.Add(l); }
            }
            if (!string.IsNullOrEmpty(a.Sources)) { var src = new Label(Loc.T("ai_src") + " " + a.Sources); src.AddToClassList("note"); src.style.marginTop = 6; c.Add(src); }
            if (!latest && a.Apply != null) { var again = Widgets.Btn(Loc.T("ai_show"), () => { ClearMap(); a.Apply(); }, "small", "ghost"); again.style.alignSelf = Align.FlexStart; again.style.marginLeft = -8; again.style.marginTop = 4; c.Add(again); }
        }

        // ---------------------------------------------------------------- intents (keywords → computed answers)
        static int YearIn(string q, int def) { var m = Regex.Match(q, @"20[2-5]\d"); return m.Success ? Mathf.Clamp(int.Parse(m.Value), 2025, 2050) : def; }
        static bool Has(string q, params string[] k) => k.Any(q.Contains);

        Answer Respond(string q0)
        {
            var q = q0.ToLowerInvariant();
            if (Has(q, "где постро", "где поставить", "поставить нов", "новую школ", "новая школ", "размест")) return Placement(YearIn(q, Mathf.Clamp(Y, 2032, 2050)));
            if (Has(q, "школ", "мест в школ")) return Schools(YearIn(q, Y < 2030 ? 2035 : Y));
            if (Has(q, "лрт", "lrt", "трамв")) return LrtDelay(q);
            if (Has(q, "риск") && Has(q, "строй", "площад") || Has(q, "отста", "срыв")) return Risky(YearIn(q, Y < 2027 || Y > 2048 ? 2033 : Y));
            if (Has(q, "электр", "мощност", "подстанц", "энерг", "свет")) return Power();
            if (Has(q, "паводок", "паводк", "затоп", "наводн")) return Flood(YearIn(q, Mathf.Max(Y, 2040)));
            if (Has(q, "пробк", "трафик", "затор", "дорог")) return Traffic(YearIn(q, Mathf.Max(Y, 2035)));
            if (Has(q, "жител", "населен", "сколько люд")) return Population(YearIn(q, Y));
            return new Answer { Text = Loc.T("ai_fallback"), Conf = 0 };
        }

        static readonly string[] Dn = { "Gate", "Golden", "Growing", "Green" };
        static void Tint(Func<BuildingInfo, Color> f) { TintLayer.Enable(); TintLayer.Apply(f); }
        static void Fly(Vector2 p, float dist, float pitch = 48f)
        {
            var cam = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
            if (cam != null) cam.FlyTo(new MapCamera.View { name = "ai", target = new Vector3(p.x, CityGround.HeightAt(p.x, p.y), p.y), distance = dist, yaw = cam.yaw, pitch = pitch });
        }
        static Color A(Color c, float a) { c.a = a; return c; }

        Answer Schools(int y)
        {
            int s = S, yi = TwinData.YI(y); var gap = new float[4]; var cov = new float[4]; int worst = 0;
            for (int d = 0; d < 4; d++)
            {
                float nd = TwinData.SocialNeed[s][d][0][yi], cp = TwinData.SocialCap[s][d][0][yi]; gap[d] = nd - cp; cov[d] = nd > 0 ? cp / nd : 1;
                if (gap[d] > gap[worst]) worst = d;
            }
            var a = new Answer { Conf = 93, Sources = "loads.json · социальная инфраструктура, нормы СП РК (120 мест на 1000 жителей)" };
            if (gap[worst] <= 0) a.Text = $"В {y} году мест в школах хватает во всех районах.";
            else
            {
                var others = Enumerable.Range(0, 4).Where(d => d != worst && gap[d] > 50).Select(d => $"{Dn[d]} −{Loc.N0(gap[d])}").ToList();
                a.Text = $"В {y} году больше всего школ не хватает в {Dn[worst]}: не хватает {Loc.N0(gap[worst])} мест, обеспеченность {Mathf.RoundToInt(cov[worst] * 100)} %."
                         + (others.Count > 0 ? " Ещё: " + string.Join(", ", others) + "." : " В остальных районах мест хватает.");
            }
            for (int d = 0; d < 4; d++) a.Facts.Add((Dn[d], $"{Loc.N0(TwinData.SocialCap[s][d][0][yi])} / {Loc.N0(TwinData.SocialNeed[s][d][0][yi])} мест · {Mathf.RoundToInt(cov[d] * 100)} %"));
            var need = new float[TwinData.NY]; var cap = new float[TwinData.NY];
            for (int i = 0; i < TwinData.NY; i++) for (int d = 0; d < 4; d++) { need[i] += TwinData.SocialNeed[s][d][0][i] / 1000f; cap[i] += TwinData.SocialCap[s][d][0][i] / 1000f; }
            a.Series = new[] { need, cap }; a.Colors = new[] { WHITE, MUTED }; a.SeriesNames = new[] { "нужно мест, тыс.", "есть мест, тыс." }; a.ChartTitle = "Школы по городу";
            a.Tools.Add($"set_year({y})"); a.Tools.Add("query(\"social.school\", by=\"district\")"); a.Tools.Add($"show_layer(\"heatmap.school\")"); a.Tools.Add($"fly_to(\"{Dn[worst]}\")");
            int w = worst;
            a.Apply = () =>
            {
                TwinState.Year = y;
                Tint(b => { int d = CityStats.DistrictIndex(b.District); if (d < 0 || b.Source == "existing_osm") return default; return gap[d] > 50 && cov[d] < 0.9f ? A(BAD, 0.85f) : gap[d] > 0 ? A(WARN, 0.7f) : A(OK, 0.45f); });
                TwinUI.Instance?.GoToDistrict(w);
                SetLegend(new[] { (BAD, "мест меньше 90 %"), (WARN, "немного не хватает"), (OK, "хватает") });
            };
            return a;
        }

        Answer LrtDelay(string q)
        {
            int ph = Has(q, "growing") ? 1 : Has(q, "green") ? 2 : 0; int s = S;
            int py = TwinData.LrtPhaseYear[s][ph], y = Mathf.Min(2050, py + 1);
            var st = new List<Vector2>(); for (int i = 0; i < TwinData.LrtStations.Length; i++) if (Mathf.RoundToInt(TwinData.LrtStations[i].z) == ph) st.Add(new Vector2(TwinData.LrtStations[i].x, TwinData.LrtStations[i].y));
            var bids = new List<int>(); float near = 0; foreach (var p in st) near += SituationData.ResidentsNear(p, 900, y, bids);
            float cars = near * 0.12f * (0.30f - 0.10f) / 1.3f;      // trips that LRT would carry, by car instead
            var ys = TwinData.TrafficYears; int ti = 0; while (ti < ys.Length - 1 && ys[ti] < y) ti++;
            var kp = TwinData.TrafficKpi[s][ti]; float ck = kp.TryGetValue("congested_km", out var v1) ? v1 : 0, allCars = kp.TryGetValue("car_trips", out var v2) ? v2 : 1, dl = kp.TryGetValue("avg_delay_pct", out var v3) ? v3 : 0;
            float extraKm = ck * cars / Mathf.Max(allCars, 1) * 2.5f, lost = near * 0.12f * 2 * 22 * 24 * (12f / 60f) * 2000f / 1e9f;   // 12 min more per trip, 2 000 ₸/h, 24 months
            var a = new Answer
            {
                Conf = 81, Sources = "traffic.json (модель часа пик), construction.json (ЛРТ по очередям), жители у станций",
                Text = $"ЛРТ «{TwinData.LrtPhaseNames[ph]}» вместо {py} года откроется в {py + 2}. У {st.Count} станций живут ~{Loc.N0(near / 1000f)} тыс. человек — на 2 года они пересаживаются на машины: +{Loc.N0(cars)} машин в утренний час пик, заторы растут на ~{Loc.N0(extraKm)} км (+{Mathf.RoundToInt(100 * extraKm / Mathf.Max(ck, 1))} %). Потерянное время людей — около {Loc.N1(lost)} млрд ₸. Что поможет: временный BRT по трассе ЛРТ (см. «Ситуационный центр»)."
            };
            a.Facts.Add(("жителей у станций", Loc.N0(near))); a.Facts.Add(("машин в час пик", "+" + Loc.N0(cars))); a.Facts.Add(("заторы", $"{Loc.N0(ck)} → {Loc.N0(ck + extraKm)} км"));
            a.Tools.Add($"run_scenario(\"lrt_phase{ph + 1}\", delay_years=2)"); a.Tools.Add($"set_year({y})"); a.Tools.Add("show_layer(\"traffic\")"); a.Tools.Add($"fly_to(\"ЛРТ, {ph + 1}-я очередь\")");
            var c = st.Count > 0 ? st[st.Count / 2] : SituationData.DistrictCenter(ph == 0 ? 1 : ph + 1); var set = new HashSet<int>(bids);
            a.Apply = () =>
            {
                TwinState.Year = y; LineLayers.Instance?.Show("traffic", true);
                Tint(b => set.Contains(b.Bid) ? A(WARN, 0.8f) : default);
                var pins = st.Select((p, i) => new MapPins.Pin { Id = "st" + i, Label = "станция", World = new Vector3(p.x, CityGround.HeightAt(p.x, p.y) + 30f, p.y), Fill = new Color(0.85f, 0.27f, 0.94f), Size = 10f, Status = "planned" }).ToList();
                MapPins.Instance?.Set(pins); Fly(c, 9000f, 55f);
                SetLegend(new[] { (WARN, "живут у станций ЛРТ (900 м)"), (new Color(0.85f, 0.27f, 0.94f), "станции, открытие +2 года") });
            };
            return a;
        }

        Answer Risky(int y)
        {
            var db = CityDatabase.Instance; var list = new List<(BuildingInfo b, int delay, int plan, int fact, float prog)>();
            foreach (var b in db.Buildings)
            {
                if (b == null || b.Source == "existing_osm") continue;
                ConstructionLayer.Timing(b, out int start, out int plan, out int fact); int dm = ConstructionLayer.Delay(b.Bid);
                if (dm <= 0 || y < start || y >= fact || plan > 2050) continue;
                float prog = Mathf.Clamp01((y + 1 - start) / (plan - start + dm / 12f));
                list.Add((b, dm, plan, fact, prog));
            }
            var top = list.OrderByDescending(x => x.b.GfaM2 * x.delay).Take(5).ToList();
            var a = new Answer { Conf = 88, Sources = "construction.json · графики, задержки, генподрядчики; БПЛА-съёмка (синтетика)" };
            if (top.Count == 0) { a.Text = $"В {y} году отстающих строек нет."; return a; }
            float gfa = list.Sum(x => x.b.GfaM2);
            a.Text = $"В {y} году отстают {list.Count} объектов ({Loc.N1(gfa / 1e6f)} млн м²). Самые рискованные — где большая площадь и большая задержка: показал 5 на карте. Чаще всего отстаёт {TopContractor(list.Select(x => x.b.Bid))}.";
            foreach (var x in top) a.Facts.Add(($"{Loc.Kind(x.b.Kind)} · {x.b.District}", $"{Loc.N0(x.b.GfaM2 / 1000f)} тыс. м² · +{x.delay} мес."));
            a.Tools.Add($"set_year({y})"); a.Tools.Add("query(\"construction.behind\", order=\"gfa*delay\", limit=5)"); a.Tools.Add("pin(5 объектов)"); a.Tools.Add("fly_to(объект №1)");
            var set = new HashSet<int>(list.Select(x => x.b.Bid));
            a.Apply = () =>
            {
                TwinState.Year = y;
                Tint(b => set.Contains(b.Bid) ? A(BAD, 0.85f) : default);
                MapPins.Instance?.Set(top.Select((x, i) => new MapPins.Pin { Id = "r" + i, Label = $"{i + 1}. +{x.delay} мес. · {ContractorName(x.b.Bid)}", World = new Vector3(x.b.X, x.b.GroundM + x.b.HeightM + 20f, x.b.Z), Fill = BAD, Status = "bad", ShowLabel = i < 3, Size = 14f }).ToList());
                Fly(new Vector2(top[0].b.X, top[0].b.Z), 2600f);
                SetLegend(new[] { (BAD, "стройка отстаёт от графика"), (new Color(0.62f, 0.62f, 0.62f), "остальной город") });
            };
            return a;
        }
        /// <summary>Congested km in a year: traffic is modelled every 5 years, linear in between (0 in 2025).</summary>
        static float Cong(int s, int y)
        {
            var ys = TwinData.TrafficYears; float v(int i) => TwinData.TrafficKpi[s][i]["congested_km"];
            if (ys.Length == 0) return 0; if (y <= ys[0]) return v(0) * Mathf.Clamp01((y - 2025) / (float)(ys[0] - 2025));
            for (int i = 1; i < ys.Length; i++) if (y <= ys[i]) return Mathf.Lerp(v(i - 1), v(i), (y - ys[i - 1]) / (float)(ys[i] - ys[i - 1]));
            return v(ys.Length - 1);
        }
        static string ContractorName(int bid) { int c = ConstructionLayer.ContractorOf(bid); return c < TwinData.ContractorNames.Length ? TwinData.ContractorNames[c] : "—"; }
        static string TopContractor(IEnumerable<int> bids)
        {
            var g = bids.GroupBy(ConstructionLayer.ContractorOf).OrderByDescending(x => x.Count()).FirstOrDefault();
            return g != null && g.Key < TwinData.ContractorNames.Length ? $"«{TwinData.ContractorNames[g.Key]}» ({g.Count()} объектов)" : "—";
        }

        Answer Power()
        {
            int s = S; var city = TwinData.BalanceOf(s, "power_hv", -1);
            int fy = -1, fd = -1; float fv = 0;
            for (int i = 0; i < TwinData.NY && fy < 0; i++) for (int d = 0; d < 4; d++) { var b = TwinData.BalanceOf(s, "power_hv", d); if (b != null && b.Deficit[i] > 0.5f) { fy = 2025 + i; fd = d; fv = b.Deficit[i]; break; } }
            var a = new Answer { Conf = 90, Sources = "networks.json · подстанции 220/110 кВ по очередям; loads.json · нагрузка по районам" };
            if (fy < 0) { a.Text = "При этом сценарии электроэнергии хватает до 2050 года во всех районах."; return a; }
            var f = TwinData.Facilities.FirstOrDefault(x => x.Res == "power_hv" && x.District == fd);
            string cause = f != null && f.DelayedStages.Length > 0 ? $"{f.DelayedStages[0]}-я очередь «{f.Name}» сдвинута на {f.Stages[s][f.DelayedStages[0] - 1]} год" : "рост спроса опережает ввод мощностей";
            a.Text = $"Впервые — в {fy} году, в {Dn[fd]}: не хватит {Loc.N1(fv)} МВт. Причина: {cause}. Варианты: перенести ввод очереди на год раньше или временно перевести часть нагрузки на соседнюю подстанцию. Это видно и во вкладке «Прогноз».";
            int yi = TwinData.YI(fy); a.Facts.Add(("спрос города", Loc.N0(city.Demand[yi]) + " МВт")); a.Facts.Add(("мощность", Loc.N0(city.Cap[yi]) + " МВт"));
            a.Series = new[] { city.Demand, city.Cap }; a.Colors = new[] { WHITE, MUTED }; a.SeriesNames = new[] { "спрос, МВт", "мощность, МВт" }; a.ChartTitle = "Электроэнергия по годам";
            a.Tools.Add("query(\"balance.power_hv\", by=\"district\")"); a.Tools.Add($"set_year({fy})"); a.Tools.Add("show_layer(\"heatmap.power\")"); a.Tools.Add($"fly_to(\"{Dn[fd]}\")");
            int fdd = fd; var dstat = new bool[4]; for (int d = 0; d < 4; d++) { var b = TwinData.BalanceOf(s, "power_hv", d); dstat[d] = b != null && b.Deficit[yi] > 0.5f; }
            a.Apply = () =>
            {
                TwinState.Year = fy;
                Tint(b => { int d = CityStats.DistrictIndex(b.District); if (d < 0 || b.Source == "existing_osm") return default; return dstat[d] ? A(BAD, 0.85f) : A(OK, 0.4f); });
                TwinUI.Instance?.GoToDistrict(fdd); SetLegend(new[] { (BAD, "дефицит мощности"), (OK, "хватает") });
            };
            return a;
        }

        Answer Flood(int y)
        {
            var inc = SituationData.Incidents(S, y).First(i => i.Id == "flood");
            var a = new Answer { Conf = 76, Sources = "risk.json · модель паводка 1 % на р. Каскелен; рельеф; buildings.csv" };
            int n = inc.No.Bids.Count; float people = inc.No.Phases[0].N;
            a.Text = n == 0 ? "В зоне паводка нет зданий." : $"При паводке «раз в 100 лет» в {y} году подтопит {Loc.N0(n)} зданий, где живут ~{Loc.N0(people)} человек. Если поставить дамбу и эвакуировать заранее — ущерб в {Loc.N1(inc.No.Peak / Mathf.Max(inc.Yes.Peak, 1))} раза меньше.";
            a.Facts.Add(("зданий", Loc.N0(n))); a.Facts.Add(("жителей", Loc.N0(people))); a.Facts.Add(("ущерб без мер", Loc.N1(inc.No.Peak / 1000f) + " млрд ₸"));
            a.Tools.Add($"set_year({y})"); a.Tools.Add("run_model(\"flood_1pct\")"); a.Tools.Add("show_layer(\"flood\")"); a.Tools.Add("fly_to(\"пойма Каскелена\")");
            var set = new HashSet<int>(inc.No.Bids); var c = inc.P;
            a.Apply = () => { TwinState.Year = y; Tint(b => set.Contains(b.Bid) ? A(BLUE, 0.9f) : default); Fly(c, 5200f); SetLegend(new[] { (BLUE, "подтопит"), (new Color(0.62f, 0.62f, 0.62f), "сухо") }); };
            return a;
        }

        Answer Traffic(int y)
        {
            int s = S; var ys = TwinData.TrafficYears; int ti = 0; while (ti < ys.Length - 1 && ys[ti] < y) ti++;
            var kp = TwinData.TrafficKpi[s][ti]; float ck = kp["congested_km"], dl = kp["avg_delay_pct"];
            var a = new Answer { Conf = 84, Sources = "traffic.json · модель утреннего часа пик", Text = $"Утренний час пик {ys[ti]} года: {Loc.N0(ck)} км дорог в заторе, время в пути дольше свободного на {Mathf.RoundToInt(dl)} %. Красным на карте — участки, где поток выше пропускной способности. Адаптивные светофоры уменьшат задержку примерно на 18 % (история №1)." };
            var ser = new float[4][]; var cols = new[] { WHITE, WARN, MUTED, BLUE };
            for (int sc = 0; sc < 4; sc++) { ser[sc] = new float[TwinData.NY]; for (int i = 0; i < TwinData.NY; i++) ser[sc][i] = Cong(sc, 2025 + i); }
            a.Series = ser; a.Colors = cols; a.SeriesNames = new[] { TwinScenario.Name(Scenario.Base), TwinScenario.Name(Scenario.Fast), TwinScenario.Name(Scenario.Slow), TwinScenario.Name(Scenario.InfraFirst) }; a.ChartTitle = "Заторы, км";
            a.Tools.Add($"set_year({ys[ti]})"); a.Tools.Add("show_layer(\"traffic\")");
            a.Apply = () => { TwinState.Year = ys[ti]; LineLayers.Instance?.Show("traffic", true); Fly(SituationData.PeopleCenter(0, ys[ti]), 9000f, 55f); SetLegend(null); };
            return a;
        }

        Answer Population(int y)
        {
            var a = new Answer { Conf = 95, Sources = "buildings.csv · жильё / 30 м² на человека (сценарий застройки QTwin)" };
            float tot = 0; for (int d = 0; d < 4; d++) tot += CityStats.Residents(d, y);
            a.Text = $"В {y} году в Alatau City живёт ~{Loc.N0(tot / 1000f)} тыс. человек.";
            for (int d = 0; d < 4; d++) a.Facts.Add((Dn[d], Loc.N0(CityStats.Residents(d, y) / 1000f) + " тыс."));
            var ser = new float[4][]; for (int d = 0; d < 4; d++) { ser[d] = new float[TwinData.NY]; for (int i = 0; i < TwinData.NY; i++) ser[d][i] = CityStats.Residents(d, 2025 + i) / 1000f; }
            a.Series = ser; a.Colors = CityStats.DistrictColors; a.SeriesNames = Dn; a.ChartTitle = "Жители, тыс.";
            a.Tools.Add($"set_year({y})"); a.Tools.Add("query(\"residents\", by=\"district\")");
            a.Apply = () => { TwinState.Year = y; TwinUI.Instance?.GoToDistrict(-1); SetLegend(null); };
            return a;
        }

        /// <summary>Where to put a new school: the district with the largest seat gap, homes farther than 10 min (800 m) from any school,
        /// 400 m candidate cells scored by school-age children within 800 m, three variants at least 1.5 km apart.</summary>
        public class SchoolPlan { public int D, Cells, Seats, Homes, Far; public float Gap; public List<(Vector2 p, float kids)> Pick = new List<(Vector2, float)>(); public HashSet<int> Near = new HashSet<int>(), Unc = new HashSet<int>(); }
        public static SchoolPlan PlanSchool(int y)
        {
            int s = S, yi = TwinData.YI(y), d = 0; float g = -1;
            for (int k = 0; k < 4; k++) { float gap = TwinData.SocialNeed[s][k][0][yi] - TwinData.SocialCap[s][k][0][yi]; if (gap > g) { g = gap; d = k; } }
            var db = CityDatabase.Instance;
            var schools = db.Buildings.Where(b => b != null && b.Kind == "education" && SituationData.Stands(b, y)).Select(b => new Vector2(b.X, b.Z)).ToList();
            var homes = db.Buildings.Where(b => b != null && b.District == Dn[d] && b.Use == "housing" && SituationData.Stands(b, y)).ToList();
            bool Covered(Vector2 p) { foreach (var sc in schools) if ((sc - p).sqrMagnitude < 800f * 800f) return true; return false; }
            var unc = homes.Where(b => !Covered(new Vector2(b.X, b.Z))).ToList();
            // candidate = 400 m grid cell centres; score = school-age children in 800 m (10 min walk) not covered today
            var cells = unc.GroupBy(b => (Mathf.FloorToInt(b.X / 400f), Mathf.FloorToInt(b.Z / 400f))).Select(gr => new Vector2(gr.Average(b => b.X), gr.Average(b => b.Z))).ToList();
            var scored = cells.Select(p => (p, kids: unc.Where(b => (new Vector2(b.X, b.Z) - p).sqrMagnitude < 800f * 800f).Sum(b => SituationData.ResidentsOf(b)) * 0.12f)).OrderByDescending(x => x.kids).ToList();
            var r = new SchoolPlan { D = d, Gap = Mathf.Max(0, g), Cells = cells.Count, Homes = homes.Count, Far = unc.Count };
            foreach (var x in scored) { if (r.Pick.All(o => (o.p - x.p).magnitude > 1500f)) r.Pick.Add(x); if (r.Pick.Count == 3) break; }
            if (r.Pick.Count == 0) return r;
            r.Seats = Mathf.Clamp(Mathf.RoundToInt(r.Pick[0].kids / 100f) * 100, 600, 1500);
            var best = r.Pick[0].p;
            foreach (var b in unc) { r.Unc.Add(b.Bid); if ((new Vector2(b.X, b.Z) - best).sqrMagnitude < 800f * 800f) r.Near.Add(b.Bid); }
            return r;
        }

        // generative planning: where to put a new school (also story 7)
        Answer Placement(int y)
        {
            var P = PlanSchool(y); int d = P.D; float g = P.Gap; var pick = P.Pick; int seats = P.Seats;
            var a = new Answer { Conf = 79, Sources = "социальная инфраструктура (нормы), здания школ генплана, жильё по годам; радиус 800 м = 10 мин пешком" };
            if (pick.Count == 0) { a.Text = $"В {y} году в {Dn[d]} все дома в 10 минутах от школы."; return a; }
            a.Text = $"Больше всего мест не хватает в {Dn[d]} ({Loc.N0(Mathf.Max(0, g))} мест в {y}). Я сравнил участки, откуда до школы дальше 10 минут пешком, и предлагаю 3 варианта. Лучший — A: рядом {Loc.N0(pick[0].kids)} детей школьного возраста, школа на {Loc.N0(seats)} мест закроет {Mathf.RoundToInt(100f * Mathf.Min(seats, g) / Mathf.Max(g, 1))} % дефицита района." + (g > seats * 1.5f ? $" Всего району нужно ещё ~{Mathf.CeilToInt(g / 1000f)} школ по 1 000 мест — B и C следующие по очереди." : "");
            string[] L = { "A", "B", "C" };
            for (int i = 0; i < pick.Count; i++) a.Facts.Add(($"вариант {L[i]}", $"{Loc.N0(pick[i].kids)} детей в 10 мин"));
            a.Tools.Add($"query(\"social.school.gap\", year={y})"); a.Tools.Add("isochrones(walk=10 мин, from=школы)"); a.Tools.Add("optimize(site, maximize=дети без школы рядом)"); a.Tools.Add("show_variants(3)");
            var best = pick[0].p; var near = P.Near; var uncSet = P.Unc;
            a.Apply = () =>
            {
                TwinState.Year = y;
                Tint(b => near.Contains(b.Bid) ? A(OK, 0.9f) : uncSet.Contains(b.Bid) ? A(WARN, 0.75f) : default);
                MapPins.Instance?.Set(pick.Select((x, i) => new MapPins.Pin { Id = "v" + i, Label = $"Вариант {L[i]} · {Loc.N0(x.kids)} детей", World = new Vector3(x.p.x, CityGround.HeightAt(x.p.x, x.p.y) + 40f, x.p.y), Fill = i == 0 ? AI : new Color(0.75f, 0.75f, 0.75f), ShowLabel = true, Size = i == 0 ? 18f : 13f }).ToList());
                MapPins.Instance?.Select("v0"); Fly(best, 3600f);
                SetLegend(new[] { (OK, "в 10 мин от новой школы"), (WARN, "сейчас дальше 10 мин от школы"), (AI, "варианты ИИ") });
            };
            return a;
        }

        // ================================================================== 2. autopilot
        void Autopilot()
        {
            int y = Mathf.Max(Y, 2030); var incs = SituationData.Incidents(S, y).Where(i => i.Id == "leak" || i.Id == "ps" || i.Id == "dtp").ToList();
            var mb = Widgets.Block(leftBody, Loc.T("ai_mode"), ""); mb.AddToClassList("ai-card");
            var mc = new VisualElement(); mc.AddToClassList("chips"); mc.style.marginBottom = 4; mb.Add(mc);
            foreach (var (k, v) in new[] { ("ai_mode_adv", false), ("ai_mode_auto", true) })
            {
                var vv = v; var bt = new Button(() => { autoMode = vv; Log(vv ? "Режим: ИИ действует сам в пределах регламента" : "Режим: ИИ только советует"); Refresh(); }) { text = Loc.T(k) };
                bt.AddToClassList("chip"); bt.EnableInClassList("active", autoMode == v); mc.Add(bt);
            }
            var mn = new Label(Loc.T(autoMode ? "ai_mode_auto_d" : "ai_mode_adv_d")); mn.AddToClassList("note"); mb.Add(mn);

            var db = Widgets.Block(leftBody, Loc.T("ai_detect"), Loc.T("ai_detect_sub"));
            foreach (var i in incs)
            {
                var r = new VisualElement(); r.AddToClassList("stage-row"); r.AddToClassList("clickable"); if (i.Id == apInc) r.AddToClassList("active");
                var t = new VisualElement(); t.AddToClassList("top"); t.Add(Widgets.Dot(applied.Contains(i.Id) ? OK : i.Kind == "forecast" ? WARN : BAD, true));
                var n = new Label(i.Title) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); t.Add(n);
                var cf = new Label(Conf(i) + " %") { pickingMode = PickingMode.Ignore }; cf.AddToClassList("v"); cf.style.color = AI; t.Add(cf); r.Add(t);
                var sub = new Label(Signal(i)) { pickingMode = PickingMode.Ignore }; sub.AddToClassList("note"); sub.style.marginLeft = 14; sub.style.marginTop = 2; r.Add(sub);
                var ii = i; r.AddManipulator(new Clickable(() => { apInc = ii.Id; Refresh(); }));
                db.Add(r);
            }
            var inc = incs.FirstOrDefault(i => i.Id == apInc) ?? incs[0];
            ShowIncident(inc, applied.Contains(inc.Id));

            // options with forecast; the recommended one first
            var ob = Widgets.Block(body, Loc.T("ai_options"), string.Format(Loc.T("ai_options_sub"), Conf(inc))); ob.AddToClassList("ai-card");
            var opts = Options(inc);
            for (int k = 0; k < opts.Count; k++)
            {
                var o = opts[k]; var box = new VisualElement(); box.AddToClassList("ai-opt"); if (k == 0) box.AddToClassList("rec"); ob.Add(box);
                var h = new VisualElement(); h.AddToClassList("row"); box.Add(h);
                var tl = new Label(o.title); tl.AddToClassList("t"); tl.style.flexGrow = 1; tl.style.flexShrink = 1; h.Add(tl);
                if (k == 0) { var rc = new Label(Loc.T("ai_rec")); rc.AddToClassList("ai-conf"); h.Add(rc); }
                var m = new Label($"{Loc.N0(o.people)} чел. · {Money(o.dmg)} · восстановление {o.restore}") { }; m.AddToClassList("note"); m.style.marginTop = 4; box.Add(m);
                var reg = new Label(o.regOk ? Loc.T("ai_reg_ok") : Loc.T("ai_reg_human")); reg.AddToClassList("note"); reg.style.color = o.regOk ? OK : WARN; reg.style.marginTop = 2; box.Add(reg);
            }
            var why = new Label(Loc.T("ai_why").ToUpperInvariant()); why.AddToClassList("note"); why.style.marginTop = 10; why.style.marginBottom = 3; why.style.letterSpacing = 1; ob.Add(why);
            foreach (var w in Why(inc, opts)) { var l = new Label("· " + w); l.AddToClassList("ai-text"); l.style.fontSize = 12; l.style.marginBottom = 3; ob.Add(l); }
            var best = opts[0];
            if (applied.Contains(inc.Id))
            {
                var done = Widgets.Status(Loc.T("ai_applied"), "ok"); done.style.alignSelf = Align.FlexStart; done.style.marginTop = 8; ob.Add(done);
                var undo = Widgets.Btn(Loc.T("ai_undo"), () => { applied.Remove(inc.Id); Log($"Человек отменил действие ИИ: {best.title}"); Refresh(); }, "small", "ghost"); undo.style.alignSelf = Align.FlexStart; undo.style.marginLeft = -8; ob.Add(undo);
            }
            else if (autoMode && best.regOk)
            {
                applied.Add(inc.Id); Log($"ИИ применил сам (в пределах регламента): {best.title} · {inc.Title}");
                body.schedule.Execute(Refresh).StartingIn(50);
            }
            else
            {
                var go = Widgets.Btn(Loc.T(autoMode ? "ai_apply_human" : "ai_apply"), () => { applied.Add(inc.Id); Log($"Человек подтвердил: {best.title} · {inc.Title}"); Refresh(); }, "primary"); go.style.marginTop = 10; ob.Add(go);
            }

            var lb = Widgets.Block(body, Loc.T("ai_log"), "");
            if (log.Count == 0) { var l = new Label(Loc.T("ai_log_empty")); l.AddToClassList("note"); lb.Add(l); }
            foreach (var x in Enumerable.Reverse(log).Take(8)) { var l = new Label(x); l.AddToClassList("ai-tool"); l.style.marginBottom = 3; lb.Add(l); }
        }
        static int clockStamp = 6 * 60 + 24;
        static void Log(string s) { clockStamp += 3; log.Add($"{clockStamp / 60 % 24:00}:{clockStamp % 60:00}  {s}"); if (log.Count > 40) log.RemoveAt(0); }
        static int Conf(Inc i) => i.Id switch { "leak" => 94, "ps" => 91, "dtp" => 97, _ => 85 };
        static string Signal(Inc i) => i.Id switch
        {
            "leak" => "давление −1,9 атм за 4 мин, расход +38 % — ИИ локализовал участок между задвижками",
            "ps" => "прогноз −14 °C и вечерний пик: в 18:00 загрузка выше допустимой",
            "dtp" => "камеры и детекторы: скорость упала с 80 до 12 км/ч, 2 полосы перекрыты",
            _ => i.FeedText
        };
        static List<(string title, float people, float dmg, string restore, bool regOk)> Options(Inc i)
        {
            var y = i.Yes; var n = i.No; string R(SituationData.Branch b) => b.Restore <= 0 ? "без отключений" : $"{Loc.N1(b.Restore)} {i.Unit}";
            var mid = i.Id switch
            {
                "leak" => ("Снизить давление на насосной и ждать бригаду", (y.AffectedMax + n.AffectedMax) * 0.35f, (y.Peak + n.Peak) * 0.45f, $"{Loc.N0(12)} ч", true),
                "ps" => ("Включить дизель-генераторы у крупных потребителей", y.AffectedMax, y.Peak * 4f, "без отключений", false),
                "dtp" => ("Только информировать водителей на табло", n.AffectedMax * 0.7f, n.Peak * 0.7f, $"{Loc.N1(2.1f)} ч", true),
                _ => ("Частичные меры", (y.AffectedMax + n.AffectedMax) / 2, (y.Peak + n.Peak) / 2, "—", false)
            };
            return new List<(string, float, float, string, bool)>
            {
                (y.Title, y.AffectedMax, y.Peak, R(y), i.Id != "ps"),
                mid,
                ("Ничего не делать: " + n.Title.ToLowerInvariant(), n.AffectedMax, n.Peak, R(n), true),
            };
        }
        static IEnumerable<string> Why(Inc i, List<(string title, float people, float dmg, string restore, bool regOk)> o)
        {
            yield return $"Ущерб {Money(o[0].dmg)} против {Money(o[2].dmg)}, если ничего не делать — в {Loc.N1(o[2].dmg / Mathf.Max(o[0].dmg, 0.1f))} раза меньше.";
            yield return $"Затронет {Loc.N0(o[0].people)} человек вместо {Loc.N0(o[2].people)}.";
            yield return i.Id switch
            {
                "leak" => "Резервная нитка загружена на 78 % — запас есть; задвижки З-14, З-17 управляются дистанционно.",
                "ps" => "У ПС «Gate» сейчас запас 31 МВт; договоры управления спросом есть у 12 крупных потребителей.",
                "dtp" => "Параллельная магистраль Gate загружена на 61 %; 7 светофоров на объезде управляются из центра.",
                _ => "Расчёт по модели двойника."
            };
            yield return o[0].regOk ? "Действие входит в регламент: ИИ может выполнить его сам, человек видит и может отменить." : "Ограничение потребителей требует подтверждения диспетчера — ИИ только предлагает.";
        }
        void ShowIncident(Inc i, bool taken)
        {
            var br = taken ? i.Yes : i.No; var set = new HashSet<int>(br.Bids);
            if (set.Count > 0) Tint(b => set.Contains(b.Bid) ? (taken ? A(WARN, 0.85f) : A(BAD, 0.9f)) : default); else TintLayer.Disable();
            LineLayers.Instance?.HideAll(); if (i.Id == "dtp") LineLayers.Instance?.Show("traffic", true);
            MapPins.Instance?.Set(new List<MapPins.Pin> { new MapPins.Pin { Id = i.Id, Label = i.Title, World = new Vector3(i.P.x, CityGround.HeightAt(i.P.x, i.P.y) + 40f, i.P.y), Fill = taken ? OK : BAD, Status = taken ? "ok" : "bad", ShowLabel = true, Size = 16f } });
            if (lastFly != i.Id) { lastFly = i.Id; Fly(i.P, i.Id == "ps" ? 4200f : 2600f); }
            SetLegend(new[] { (taken ? WARN : BAD, taken ? "затронуты после решения ИИ" : "затронуты, если ничего не делать"), (new Color(0.62f, 0.62f, 0.62f), "остальной город") });
        }
        static string lastFly;
        static string Money(float mln) => mln >= 1000 ? Loc.N1(mln / 1000f) + " млрд ₸" : Loc.N0(mln) + " млн ₸";

        // ================================================================== 3. without AI / with AI (water main leak)
        void Compare()
        {
            int y = Mathf.Max(Y, 2030); var i = SituationData.Incidents(S, y).First(x => x.Id == "leak");
            float with = i.Yes.AffectedMax, without = i.No.AffectedMax;
            var b = Widgets.Block(leftBody, Loc.T("ai_cmp"), ""); b.AddToClassList("ai-card");
            var cols = new VisualElement(); cols.AddToClassList("cmp-cols"); b.Add(cols);
            cols.Add(Big(Loc.T("ai_without"), BAD, new[] { ("обнаружение", "4,5 ч"), ("изоляция участка", "5 ч"), ("жителей без воды", Loc.N0(without)), ("ущерб", Money(i.No.Peak)), ("потери воды", "9 000 м³") }));
            cols.Add(Big(Loc.T("ai_with"), AI, new[] { ("обнаружение", "4 мин"), ("изоляция участка", "40 мин"), ("жителей без воды", Loc.N0(with)), ("ущерб", Money(i.Yes.Peak)), ("потери воды", "1 200 м³") }));

            // timelines: detection, isolation, recovery
            var tb = Widgets.Block(body, Loc.T("ai_timeline"), Loc.T("ai_timeline_sub"));
            TimeBar(tb, Loc.T("ai_without"), BAD, new[] { (0f, 4.5f, "ищут по жалобам"), (4.5f, 5f, "едут, ищут задвижки"), (5f, 21f, "авария и ремонт") });
            TimeBar(tb, Loc.T("ai_with"), AI, new[] { (0f, 0.07f, ""), (0.07f, 0.67f, "изоляция"), (0.67f, 3.5f, "ремонт по резервной линии") });
            var sc = new VisualElement(); sc.AddToClassList("row"); sc.style.marginTop = 2; tb.Add(sc);
            foreach (var t in new[] { "0", "6 ч", "12 ч", "18 ч", "24 ч" }) { var l = new Label(t); l.AddToClassList("note"); l.style.flexGrow = 1; sc.Add(l); }

            var how = Widgets.Block(body, Loc.T("ai_how"), "");
            foreach (var t in new[]
            {
                "Двойник знает схему сети: какой датчик стоит на каком участке и какие задвижки его отсекают.",
                "ИИ сравнивает давление и расход с нормой для этого часа и дня недели — падение на 1,9 атм за 4 минуты не похоже на обычный разбор воды.",
                "По двум соседним датчикам он находит участок, считает, сколько домов останутся без воды при каждом варианте, и предлагает лучший.",
                "Диспетчер видит всё это на карте и подтверждает одной кнопкой."
            }) { var l = new Label("· " + t); l.AddToClassList("ai-text"); l.style.fontSize = 12; l.style.marginBottom = 4; how.Add(l); }
            ShowIncident(i, true);
            var set = new HashSet<int>(i.No.Bids); var near = new HashSet<int>(i.Yes.Bids);
            Tint(bb => near.Contains(bb.Bid) ? A(AI, 0.9f) : set.Contains(bb.Bid) ? A(BAD, 0.8f) : default);
            SetLegend(new[] { (BAD, "без воды без ИИ"), (AI, "без воды с ИИ"), (new Color(0.62f, 0.62f, 0.62f), "остальной город") });
        }
        static VisualElement Big(string cap, Color col, (string, string)[] rows)
        {
            var v = new VisualElement(); v.AddToClassList("cmp-col");
            var e = new Label(cap.ToUpperInvariant()); e.AddToClassList("cap"); e.style.color = col; v.Add(e);
            foreach (var (k, x) in rows)
            {
                var l = new Label(k); l.AddToClassList("note"); l.style.marginTop = 6; v.Add(l);
                var n = new Label(x); n.AddToClassList("ai-big"); n.style.color = col == AI ? new Color(0.86f, 0.82f, 1f) : WHITE; v.Add(n);
            }
            return v;
        }
        static void TimeBar(VisualElement parent, string name, Color col, (float a, float b, string label)[] segs)
        {
            var l = new Label(name); l.AddToClassList("note"); l.style.marginTop = 6; l.style.marginBottom = 3; parent.Add(l);
            var track = new VisualElement(); track.AddToClassList("tbar"); parent.Add(track);
            for (int k = 0; k < segs.Length; k++)
            {
                var (a, b, lab) = segs[k]; var s = new VisualElement(); s.AddToClassList("tseg");
                s.style.left = Length.Percent(100f * a / 24f); s.style.width = Length.Percent(Mathf.Max(0.8f, 100f * (b - a) / 24f));
                s.style.backgroundColor = new Color(col.r, col.g, col.b, k == 0 ? 0.45f : k == 1 ? 0.9f : 0.65f); track.Add(s);
                if (!string.IsNullOrEmpty(lab) && b - a > 6f) { var t = new Label(lab) { pickingMode = PickingMode.Ignore }; t.AddToClassList("tlab"); s.Add(t); }
            }
        }

        // ================================================================== 4. seven AI stories
        static readonly string[] StoryTitles =
        {
            "Адаптивные светофоры и «зелёная волна»", "Балансировка сети с ВИЭ и накопителями", "Предиктивное обслуживание трансформатора",
            "Раннее предупреждение паводка", "Оптимизация вывоза отходов", "Контроль стройки по камерам", "Генеративное планирование: новая школа",
        };
        void Stories()
        {
            if (story >= 0) StoryDetail(story);
            var b = Widgets.Block(leftBody, Loc.T("ai_stories"), Loc.T("ai_stories_sub"));
            for (int k = 0; k < StoryTitles.Length; k++)
            {
                var r = new VisualElement(); r.AddToClassList("stage-row"); r.AddToClassList("clickable");
                var t = new VisualElement(); t.AddToClassList("top"); var num = new Label((k + 1).ToString()) { pickingMode = PickingMode.Ignore }; num.AddToClassList("ai-num"); t.Add(num);
                var n = new Label(StoryTitles[k]) { pickingMode = PickingMode.Ignore }; n.AddToClassList("n"); t.Add(n); r.Add(t);
                var sub = new Label(StoryHook(k)) { pickingMode = PickingMode.Ignore }; sub.AddToClassList("note"); sub.style.marginLeft = 26; sub.style.marginTop = 2; r.Add(sub);
                int kk = k; r.AddManipulator(new Clickable(() => { story = kk; ClearMap(); Refresh(); }));
                b.Add(r);
            }
        }
        static string StoryHook(int k) => k switch
        {
            0 => "−18 % времени в пути на магистралях", 1 => "пик нагрузки сглажен, газовые турбины работают меньше", 2 => "«откажет через 12 дней» — замена до аварии",
            3 => "предупреждение за 30 часов вместо 4", 4 => "−22 % пробега мусоровозов", 5 => "СИЗ, нарушения и прогресс — по камерам, без обходов", _ => "ИИ предлагает участок и показывает охват на 3D",
        };

        void StoryDetail(int k)
        {
            var b = Widgets.Block(body); b.AddToClassList("ai-card");
            var back = Widgets.Btn(Loc.T("ai_back"), () => { story = -1; ClearMap(); Refresh(); }, "small", "ghost"); back.style.alignSelf = Align.FlexStart; back.style.marginLeft = -8; back.style.marginBottom = 4; b.Add(back);
            var t = new Label($"{k + 1}. {StoryTitles[k]}"); t.AddToClassList("block-title"); t.style.fontSize = 15; b.Add(t);
            int y = Mathf.Max(Y, 2030), s = S;
            Answer a;
            switch (k)
            {
                case 0: a = StoryTraffic(y, s); break;
                case 1: a = StoryGrid(y, s); break;
                case 2: a = StoryTransformer(y, s); break;
                case 3: a = StoryFlood(y); break;
                case 4: a = StoryWaste(y); break;
                case 5: a = StoryCv(); break;
                default: a = Placement(Mathf.Clamp(Y, 2032, 2050)); break;
            }
            a.Q = StoryTitles[k];
            var tx = new Label(a.Text); tx.AddToClassList("ai-text"); tx.style.marginTop = 8; b.Add(tx);
            if (a.Facts.Count > 0)
            {
                var g = new VisualElement(); g.style.marginTop = 8; b.Add(g);
                foreach (var (kk, v) in a.Facts) g.Add(Widgets.Fact(kk, v));
            }
            if (a.Series != null)
            {
                var c = Widgets.Block(body, a.ChartTitle ?? "", "");
                var ch = new TwinChart(); ch.Series = a.Series; ch.Colors = a.Colors; ch.Stacked = false; ch.LineWidths = a.Series.Select((_, i) => i == 0 ? 2.5f : 2f).ToArray(); ch.XText = a.XText; ch.YMin = a.YMin; ch.MarkYear = a.XText == null ? y : -1; ch.Refresh(); c.Add(ch);
                if (a.SeriesNames != null) { var lg = new VisualElement(); lg.AddToClassList("legend"); c.Add(lg); for (int i = 0; i < a.SeriesNames.Length; i++) lg.Add(Widgets.LegendItem(a.Colors[i], a.SeriesNames[i])); }
            }
            if (k == 5) { var go = Widgets.Btn(Loc.T("ai_open_bim"), () => TwinState.SetModule("construction"), "primary", "small"); go.style.alignSelf = Align.FlexStart; go.style.marginTop = 10; b.Add(go); }
            if (a.Tools.Count > 0)
            {
                var tl = new Label(Loc.T("ai_tools").ToUpperInvariant()); tl.AddToClassList("note"); tl.style.marginTop = 10; tl.style.marginBottom = 3; tl.style.letterSpacing = 1; b.Add(tl);
                foreach (var x in a.Tools) { var l = new Label("→ " + x); l.AddToClassList("ai-tool"); b.Add(l); }
            }
            a.Apply?.Invoke();
        }

        Answer StoryTraffic(int y, int s)
        {
            var ys = TwinData.TrafficYears; int ti = 0; while (ti < ys.Length - 1 && ys[ti] < y) ti++;
            var kp = TwinData.TrafficKpi[s][ti]; float ck = kp["congested_km"], dl = kp["avg_delay_pct"], cars = kp["car_trips"];
            float hours = cars * 1.3f * 0.35f * (dl / 100f) * 0.18f * 2 * 250 / 1e6f;   // person-hours saved per year, mln (avg trip 35 min)
            var a = new Answer
            {
                Text = $"Светофоры на магистралях получают данные детекторов и камер каждую минуту, а ИИ подбирает фазы так, чтобы поток шёл «зелёной волной». В модели {ys[ti]} года: задержка в пути +{Mathf.RoundToInt(dl)} % → +{Mathf.RoundToInt(dl * 0.82f)} %, участков в заторе {Loc.N0(ck)} → {Loc.N0(ck * 0.8f)} км. Это ~{Loc.N1(hours)} млн часов в год, которые жители не стоят в пробках."
            };
            a.Facts.Add(("светофоров под управлением ИИ", Loc.N0(TwinData.Roads.Count(e => e.Cls == TwinData.RoadClass.Main || e.Cls == TwinData.RoadClass.Ring) / 9))); a.Facts.Add(("время в пути", "−18 %")); a.Facts.Add(("выбросы транспорта", "−9 %"));
            var ser = new float[2][]; ser[0] = new float[TwinData.NY]; ser[1] = new float[TwinData.NY];
            for (int i = 0; i < TwinData.NY; i++) { float v = Cong(s, 2025 + i); ser[0][i] = v; ser[1][i] = v * 0.8f; }
            a.Series = ser; a.Colors = new[] { WHITE, AI }; a.SeriesNames = new[] { "без ИИ", "с ИИ" }; a.ChartTitle = "Заторы, км";
            a.Tools.Add("stream(\"traffic.detectors\", 1 мин)"); a.Tools.Add("optimize(signal_plans, minimize=задержка)"); a.Tools.Add("show_layer(\"traffic\")");
            a.Apply = () => { LineLayers.Instance?.Show("traffic", true); Fly(SituationData.PeopleCenter(0, ys[ti]), 8000f, 55f); SetLegend(null); };
            return a;
        }
        Answer StoryGrid(int y, int s)
        {
            float load = TwinData.Load(s, "power", -1, y); float solar = TwinData.Facilities.Where(f => f.Res == "renewable" && f.Stages[s].Length > 0 && f.Stages[s][0] <= y).Sum(f => f.Unit > 0 ? f.Unit : 50f);
            if (solar <= 0) solar = 55;
            var dem = new float[25]; var noS = new float[25]; var withS = new float[25];
            for (int h = 0; h <= 24; h++)
            {
                float hh = h % 24; float prof = 0.62f + 0.22f * Mathf.Exp(-Mathf.Pow((hh - 9f) / 2.2f, 2)) + 0.38f * Mathf.Exp(-Mathf.Pow((hh - 19.5f) / 2.4f, 2));
                float pv = Mathf.Max(0, Mathf.Sin((hh - 6.5f) / 12f * Mathf.PI)) * solar * 0.8f;
                dem[h] = load * prof; noS[h] = Mathf.Max(0, dem[h] - pv);
            }
            // storage: charge from the midday PV surplus, discharge into the evening peak
            float store = solar * 0.6f * 4f; float peak = noS.Max(); float cap = peak - store / 4.5f;
            for (int h = 0; h <= 24; h++) withS[h] = noS[h] > cap ? cap : (h >= 10 && h <= 15 ? noS[h] + store / 6f * 0.5f : noS[h]);
            float cut = peak - withS.Max();
            var a = new Answer
            {
                Text = $"Днём солнечные станции ({Loc.N0(solar)} МВт) дают излишек, а вечером пик приходится на газовые турбины. ИИ по прогнозу погоды и потребления заряжает накопители днём и отдаёт энергию в 18–21 ч: вечерний пик ниже на {Loc.N0(cut)} МВт, газовые турбины работают на 3 часа в день меньше.",
                Series = new[] { noS, withS }, Colors = new[] { WHITE, AI }, SeriesNames = new[] { "без ИИ, МВт", "с ИИ, МВт" }, ChartTitle = $"Сутки в {y} году, МВт", XText = new[] { "0:00", "8:00", "16:00", "24:00" }
            };
            a.Facts.Add(("пик без ИИ", Loc.N0(peak) + " МВт")); a.Facts.Add(("пик с ИИ", Loc.N0(withS.Max()) + " МВт")); a.Facts.Add(("CO₂ за год", "−" + Loc.N0(cut * 3 * 365 * 0.45f) + " т"));
            a.Tools.Add("forecast(\"load\", 24 ч)"); a.Tools.Add("forecast(\"pv\", облачность)"); a.Tools.Add("schedule(storage, charge 10–15 ч, discharge 18–21 ч)");
            var pvf = TwinData.Facilities.Where(x => x.Res == "renewable" && x.Stages[s].Length > 0 && x.Stages[s][0] <= y).OrderByDescending(x => x.Unit).FirstOrDefault() ?? TwinData.Facilities.FirstOrDefault(x => x.Res == "renewable");
            a.Apply = () => { if (pvf != null) { MapPins.Instance?.Set(new List<MapPins.Pin> { new MapPins.Pin { Id = "pv", Label = pvf.Name, World = new Vector3(pvf.X, CityGround.HeightAt(pvf.X, pvf.Z) + 40f, pvf.Z), Fill = new Color(0.55f, 0.85f, 0.35f), ShowLabel = true, Size = 16f } }); Fly(new Vector2(pvf.X, pvf.Z), 6000f); } SetLegend(null); };
            return a;
        }
        Answer StoryTransformer(int y, int s)
        {
            var f = TwinData.Facilities.FirstOrDefault(x => x.Res == "power_hv" && x.District == 2) ?? TwinData.Facilities.First(x => x.Res == "power_hv");
            var p = new Vector2(f.X, f.Z); float people = SituationData.ResidentsNear(p, 2500, y);
            var temp = new float[31]; var lim = new float[31]; var fc = new float[31];
            for (int d = 0; d <= 30; d++) { temp[d] = d <= 18 ? 62 + d * 0.35f + (d > 10 ? (d - 10) * 0.55f : 0) + Mathf.Sin(d * 1.7f) * 0.8f : float.NaN; fc[d] = d >= 18 ? 62 + 18 * 0.35f + 8 * 0.55f + (d - 18) * 1.15f : float.NaN; lim[d] = 85; }
            for (int d = 0; d <= 30; d++) { if (float.IsNaN(temp[d])) temp[d] = fc[d]; }
            var a = new Answer
            {
                Text = $"Трансформатор Т2 на {f.Name}: температура масла растёт на 0,9 °C в сутки, в анализе газов (DGA) — признаки перегрева контакта. ИИ сравнил с историей 40 таких трансформаторов: при этом тренде отказ через ~12 дней (вероятность 78 %). Предложено: плановая замена контакта в ночь на воскресенье, нагрузку временно взять Т1. Без этого — аварийное отключение для ~{Loc.N0(people / 1000f)} тыс. жителей.",
                YMin = 55, Series = new[] { temp, lim }, Colors = new[] { AI, BAD }, SeriesNames = new[] { "масло, °C", "предел" }, ChartTitle = "30 дней", XText = new[] { "−18 дн", "−8 дн", "+2 дн", "+12 дн" }
            };
            a.Facts.Add(("до отказа", "~12 дней · 78 %")); a.Facts.Add(("плановый ремонт", "18 млн ₸ · 6 ч ночью")); a.Facts.Add(("авария", "240 млн ₸ · " + Loc.N0(people / 1000f) + " тыс. жителей без света"));
            a.Tools.Add("stream(\"scada.transformer.T2\")"); a.Tools.Add("model(\"remaining_life\", DGA + температура)"); a.Tools.Add("create_work_order(\"замена контакта\", окно=вс 01:00–07:00)");
            a.Apply = () => { MapPins.Instance?.Set(new List<MapPins.Pin> { new MapPins.Pin { Id = "tr", Label = "Т2 · отказ через ~12 дней", World = new Vector3(f.X, CityGround.HeightAt(f.X, f.Z) + 40f, f.Z), Fill = WARN, Status = "warn", ShowLabel = true, Size = 18f } }); MapPins.Instance?.Select("tr"); Fly(p, 3200f); SetLegend(null); };
            return a;
        }
        Answer StoryFlood(int y)
        {
            var inc = SituationData.Incidents(S, y).First(i => i.Id == "flood");
            var lvl = new float[25]; var thr = new float[25];
            for (int h = 0; h <= 24; h++) { float t = h * 3f; lvl[h] = 0.3f + 1.3f / (1f + Mathf.Exp(-(t - 30f) / 7f)); thr[h] = 1.0f; }
            var a = new Answer
            {
                Text = $"ИИ объединяет гидропосты Каскелена, осадки в горах и прогноз таяния снега. Подъём выше 1 м он видит за 30 часов — раньше предупреждали за 4. За это время ставят временную дамбу и вывозят ~{Loc.N0(inc.No.Phases[0].N)} жителей поймы: ущерб {Money(inc.Yes.Peak)} вместо {Money(inc.No.Peak)}.",
                Series = new[] { lvl, thr }, Colors = new[] { BLUE, BAD }, SeriesNames = new[] { "уровень, м", "опасный" }, ChartTitle = "Уровень Каскелена, 72 часа", XText = new[] { "0 ч", "24 ч", "48 ч", "72 ч" }
            };
            a.Facts.Add(("предупреждение", "за 30 ч (было 4 ч)")); a.Facts.Add(("зданий в зоне", Loc.N0(inc.No.Bids.Count)));
            a.Tools.Add("stream(\"hydro.posts\", \"meteo.precip\")"); a.Tools.Add("forecast(\"river_level\", 72 ч)"); a.Tools.Add("alert(ДЧС, акимат, жители поймы)");
            var set = new HashSet<int>(inc.No.Bids); var c = inc.P;
            a.Apply = () => { Tint(b => set.Contains(b.Bid) ? A(BLUE, 0.9f) : default); Fly(c, 5200f); SetLegend(new[] { (BLUE, "зона подтопления"), (new Color(0.62f, 0.62f, 0.62f), "сухо") }); };
            return a;
        }
        Answer StoryWaste(int y)
        {
            float people = 0; for (int d = 0; d < 4; d++) people += CityStats.Residents(d, y);
            float tons = people * 1.1f / 1000f; int trucks = Mathf.Max(4, Mathf.CeilToInt(tons / 9f / 2f)); int trucksAi = Mathf.Max(3, Mathf.RoundToInt(trucks * 0.78f));
            float km = trucks * 160f;
            var a = new Answer
            {
                Text = $"Датчики заполнения в контейнерах и ИИ-маршрутизация: машины едут только к полным площадкам и по дорогам без пробок. Город в {y} году — {Loc.N0(tons)} т отходов в сутки: {trucks} → {trucksAi} мусоровозов, пробег {Loc.N0(km)} → {Loc.N0(km * 0.78f)} км в сутки.",
            };
            a.Facts.Add(("пробег", "−22 %")); a.Facts.Add(("переполненных площадок", "−65 %")); a.Facts.Add(("экономия в год", Loc.N0(km * 0.22f * 365 * 450f / 1e6f) + " млн ₸"));
            a.Tools.Add("stream(\"bins.fill_level\")"); a.Tools.Add("solve(VRP, trucks, traffic)"); a.Tools.Add("dispatch(routes)");
            a.Apply = () => { TwinUI.Instance?.GoToDistrict(2); SetLegend(null); };
            return a;
        }
        Answer StoryCv()
        {
            var a = new Answer
            {
                Text = "На квартале Gate Q1 — 14 камер. Компьютерное зрение (компетенция qTwin) в реальном времени находит рабочих без каски и жилета, людей в опасной зоне крана и сравнивает смонтированное с BIM-графиком. Прораб получает уведомление, а не обходит площадку.",
            };
            a.Facts.Add(("соблюдение СИЗ", "96,8 %")); a.Facts.Add(("нарушений за смену", "3 (2 без каски, 1 в зоне крана)")); a.Facts.Add(("прогресс по камерам", "сверка с BIM каждую ночь"));
            a.Tools.Add("stream(\"site.cameras\", 14)"); a.Tools.Add("detect(PPE, danger_zone)"); a.Tools.Add("compare(progress, BIM 4D)");
            var bq = BimQuarter.Instance;
            a.Apply = () => { if (bq != null && BimQuarter.Loaded) Fly(new Vector2(bq.Center.x, bq.Center.z), 900f, 38f); else TwinUI.Instance?.GoToDistrict(0); SetLegend(null); };
            return a;
        }
    }
}
