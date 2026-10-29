using System;
using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The construction analytics behind the «Аналитика» page, computed once when the window opens, at the date of the last survey:
    /// · the estimate: the budget of every building split into cost items (the summary estimate, ССР), what is spent (the works done, paid at
    ///   the prices of their time), what the rest will cost at the prices on the survey date (the share bought at a fixed price is not
    ///   indexed), what the delays add (cranes and the site kept longer, overtime of a second shift); the overrun against the budget and the
    ///   reserve for unforeseen costs;
    /// · the people: the crew the schedule asks for, by trades, against the crew the site cameras count;
    /// · the documents of the object (contract, estimate, schedule, price list, acts, reports, letters, minutes …) with numbered places, and
    ///   the findings that need attention — overrun, delays, missing people, a penalty risk, quality, safety — each pointing at the places in
    ///   the documents it follows from; the documents are ranked by importance: their weight plus the findings that cite them.
    /// The base prices are the Almaty market of October 2026 (ads and price lists, the dollar of the National Bank), the prices on the survey
    /// date a forecast by indices; all the figures are the scenario of the digital twin, not the developer's data.</summary>
    public partial class IconicMonitor
    {
        // ================================================================== prices
        /// <summary>A resource whose price drives the cost: its price in the estimate (Almaty, October 2026) and its growth a year.</summary>
        /// <summary>Open: the id of the open source of the base price (null — the base price is an assumption of the model).</summary>
        class Rs { public string Name, Unit, Src, Open; public float Base, Growth; public int Dec; }
        static readonly Rs[] Rsc =
        {
            new Rs { Name = "Бетон товарный В40 (М550)", Unit = "м³", Base = 42000f, Growth = 0.06f, Src = "olx.kz · Алматы, 22–26.10.2026", Open = AlatauCity.DigitalTwin.Data.Sources.OlxPrices },
            new Rs { Name = "Арматура А500С", Unit = "т", Base = 320000f, Growth = 0.08f, Src = "olx.kz · Алматы, 22–26.10.2026", Open = AlatauCity.DigitalTwin.Data.Sources.OlxPrices },
            new Rs { Name = "Металлопрокат С345 (балки, фермы)", Unit = "т", Base = 430000f, Growth = 0.10f, Src = "olx.kz · Алматы, 22–26.10.2026", Open = AlatauCity.DigitalTwin.Data.Sources.OlxPrices },
            new Rs { Name = "Фасадные модули (витраж, импорт)", Unit = "м²", Base = 245000f, Growth = 0.07f, Src = "импорт, цена в $" },
            new Rs { Name = "Курс доллара для импортного оборудования", Unit = "₸/$", Base = 447.94f, Growth = 0.055f, Src = "НБ РК, 23.10.2026", Dec = 2, Open = AlatauCity.DigitalTwin.Data.Sources.NbrkRate },
            new Rs { Name = "Труд: ставка монтажника", Unit = "чел.-ч", Base = 2700f, Growth = 0.10f, Src = "ставка по Алматы" },
            new Rs { Name = "Башенный кран с машинистом", Unit = "мес.", Base = 7200000f, Growth = 0.06f, Src = "аренда с машинистом" },
            new Rs { Name = "Отделочные материалы", Unit = "индекс", Base = 100f, Growth = 0.06f, Src = "индекс модели, 100 = 01.10.2026" },
            new Rs { Name = "Озеленение и мощение", Unit = "индекс", Base = 100f, Growth = 0.05f, Src = "индекс модели, 100 = 01.10.2026" },
        };
        /// <summary>The date of the prices of the estimate: 01.10.2026.</summary>
        const float PriceBase = 2026.75f;
        static float PriceAt(int r, float t) => Rsc[r].Base * Mathf.Pow(1f + Rsc[r].Growth, Mathf.Max(t - PriceBase, 0f));
        static string PriceText(int r, float v) => (Rsc[r].Dec > 0 ? v.ToString("N" + Rsc[r].Dec, Loc.Ru) : Loc.N0(v)) + (Rsc[r].Unit == "индекс" ? "" : " ₸");

        // ================================================================== the estimate
        /// <summary>A cost item of the estimate: its share of a building's budget (Land: of the grounds), the window of the building's progress
        /// in which it is done, the share bought at a fixed price, its resources with their weights; Time: it costs as long as the site works.</summary>
        class It { public string Name; public float Share, Land, A, B, Fixed; public int[] R; public float[] W; public bool Time; }
        static readonly It[] Items =
        {
            new It { Name = "Подготовка, котлован и фундаменты", Share = 0.085f, Land = 0.26f, A = 0f, B = 0.12f, Fixed = 0.6f, R = new[] { 0, 5, 6 }, W = new[] { 0.4f, 0.35f, 0.25f } },
            new It { Name = "Монолитный каркас: бетон", Share = 0.125f, A = 0.05f, B = 0.62f, Fixed = 0.3f, R = new[] { 0, 5 }, W = new[] { 0.7f, 0.3f } },
            new It { Name = "Монолитный каркас: арматура", Share = 0.095f, A = 0.05f, B = 0.62f, Fixed = 0.4f, R = new[] { 1, 5 }, W = new[] { 0.8f, 0.2f } },
            new It { Name = "Металлоконструкции", Share = 0.065f, A = 0.3f, B = 0.75f, Fixed = 0.35f, R = new[] { 2, 5 }, W = new[] { 0.85f, 0.15f } },
            new It { Name = "Фасадные системы", Share = 0.16f, A = 0.25f, B = 0.9f, Fixed = 0.7f, R = new[] { 3, 5 }, W = new[] { 0.85f, 0.15f } },
            new It { Name = "Инженерные системы и лифты", Share = 0.145f, A = 0.45f, B = 0.97f, Fixed = 0.5f, R = new[] { 4, 5 }, W = new[] { 0.8f, 0.2f } },
            new It { Name = "Отделочные работы", Share = 0.125f, A = 0.55f, B = 1f, Fixed = 0.2f, R = new[] { 7, 5 }, W = new[] { 0.5f, 0.5f } },
            new It { Name = "Содержание площадки и управление стройкой", Share = 0.14f, Land = 0.21f, A = 0f, B = 1f, Fixed = 0f, R = new[] { 5 }, W = new[] { 1f }, Time = true },
            new It { Name = "Машины и механизмы", Share = 0.06f, Land = 0.10f, A = 0f, B = 0.85f, Fixed = 0.5f, R = new[] { 6 }, W = new[] { 1f }, Time = true },
            new It { Name = "Благоустройство и озеленение", Share = 0f, Land = 0.43f, A = 0.3f, B = 1f, Fixed = 0.3f, R = new[] { 8, 5 }, W = new[] { 0.6f, 0.4f } },
        };
        const float ReserveShare = 0.04f;
        /// <summary>The share bought at a fixed price: the campus is bought under fixed-price contracts for more of its volume.</summary>
        float FixedOf(int k) => Mathf.Min(0.9f, Items[k].Fixed + (L != null && L.Id == "kaist" ? 0.2f : 0f));
        /// <summary>The price of item k at date t against the estimate (1 = the prices of the estimate).</summary>
        float PriceF(int k, float t)
        {
            var it = Items[k]; float s = 0f, fx = FixedOf(k);
            for (int j = 0; j < it.R.Length; j++) s += it.W[j] * (1f + (PriceAt(it.R[j], t) / Rsc[it.R[j]].Base - 1f) * (1f - fx));
            return s;
        }
        float ShareOf(int i, int k) => Pt(i).Land ? Items[k].Land : Items[k].Share;
        static float ItemQ(It it, float p) => Mathf.Clamp01((p - it.A) / Mathf.Max(it.B - it.A, 1e-4f));
        /// <summary>Share of a building's budget done at progress p (the works done, at the prices of the estimate).</summary>
        float Spend(int i, float p) { float s = 0f; bool land = Pt(i).Land; foreach (var it in Items) s += (land ? it.Land : it.Share) * ItemQ(it, p); return s; }

        /// <summary>An item of a building (or a sum): budget, done (0…1), earned at the prices of the estimate, spent, the rest at the prices of
        /// the survey date, what the delay adds; at completion, its deviation.</summary>
        struct Cost
        {
            public float B, Q, Ev, Ac, Etc, Extra;
            public float Eac => Ac + Etc + Extra; public float Over => Eac - B;
            public static Cost operator +(Cost a, Cost b) => new Cost { B = a.B + b.B, Ev = a.Ev + b.Ev, Ac = a.Ac + b.Ac, Etc = a.Etc + b.Etc, Extra = a.Extra + b.Extra, Q = a.B + b.B > 0f ? (a.Ev + b.Ev) / (a.B + b.B) : 0f };
        }
        Cost[,] cost;
        Cost anTot; float anRes;
        void MakeCost(float d)
        {
            int n = L.Parts.Count; cost = new Cost[n, Items.Length]; anTot = new Cost();
            for (int i = 0; i < n; i++)
            {
                var p = Pt(i); float fp = FactP(i, d), dur = Mathf.Max(p.B - p.A, 0.3f);
                float lateY = Mathf.Max(Obj(i, d).EndDays, 0) / 365f;
                bool push = p.Recover && DelayAt(i, d) > 0.02f;                       // the delay is being closed by a second shift: overtime
                for (int k = 0; k < Items.Length; k++)
                {
                    var it = Items[k]; float sh = ShareOf(i, k); if (sh <= 0f) continue;
                    var c = new Cost { B = p.Capex * sh, Q = ItemQ(it, fp) };
                    c.Ev = c.B * c.Q;
                    if (c.Q > 0f)
                    {
                        float ta = FactDate(i, Mathf.Max(it.A, 1e-3f)), te = c.Q >= 0.999f ? FactDate(i, it.B) : d;
                        c.Ac = c.Ev * PriceF(k, Mathf.Min((ta + te) * 0.5f, d));
                    }
                    c.Etc = c.B * (1f - c.Q) * PriceF(k, d);
                    if (it.Time && c.Q < 0.999f && lateY > 0f) c.Extra += c.B * lateY / (dur * Mathf.Max(it.B - it.A, 0.1f)) * PriceF(k, d);
                    if (push && c.Q < 0.999f)
                    {
                        float lw = 0f; for (int j = 0; j < it.R.Length; j++) if (it.R[j] == 5) lw += it.W[j];
                        c.Extra += c.B * (1f - c.Q) * lw * 0.25f * 0.25f * PriceF(k, d);  // 25 % for the hours of the second shift, over the months it takes
                    }
                    cost[i, k] = c; anTot += c;
                }
            }
            anRes = anTot.B * ReserveShare;
        }
        /// <summary>Item k over the buildings (part −1) or of one building.</summary>
        Cost ItemCost(int k, int part)
        {
            var s = new Cost(); if (cost == null) return s;
            for (int i = 0; i < L.Parts.Count; i++) if (part < 0 || part == i) s += cost[i, k];
            return s;
        }
        Cost PartCost(int part) { var s = new Cost(); for (int k = 0; k < Items.Length; k++) s += ItemCost(k, part); return s; }
        /// <summary>The overrun after the reserve: positive — the reserve does not cover it.</summary>
        float NetOver => anTot.Over - anRes;
        string CostCls => NetOver > 0f ? "bad" : anTot.Over > 0f ? "warn" : "ok";
        /// <summary>The resource of item k that drives its price most (the largest weight).</summary>
        static int MainRes(int k) { var it = Items[k]; int r = it.R[0]; float w = -1f; for (int j = 0; j < it.R.Length; j++) if (it.W[j] > w) { w = it.W[j]; r = it.R[j]; } return r; }

        static string Mln(float m) { float a = Mathf.Abs(m); return a >= 1000f ? "$" + Loc.N1(a / 1000f) + " млрд" : a >= 100f ? "$" + Loc.N0(a) + " млн" : "$" + Loc.N1(a) + " млн"; }
        static string SMln(float m) => (m >= 0f ? "+" : "−") + Mln(m);
        static string SPc(float v) => (v >= 0f ? "+" : "−") + Loc.N1(Mathf.Abs(v) * 100f) + " %";

        // ================================================================== people
        class Trade { public string Name; public int Need, Have; public bool Lag; }
        List<Trade>[] trades;
        /// <summary>The share of the crew missing on a building: where the work is behind, people are short.</summary>
        float Short(int i, float d) { float dl = DelayAt(i, d); return dl > 0.05f ? Mathf.Clamp(0.12f + dl * 0.8f, 0f, 0.3f) : dl > 0.01f ? 0.07f : 0.02f; }
        float CrewOf(int i, float q) => q > 0f && q < 1f ? Pt(i).Capex * 3.4f * Mathf.Pow(Mathf.Sin(q * Mathf.PI), 0.7f) : 0f;
        static string TradeOf(string work)
        {
            var w = work.ToLowerInvariant();
            bool Any(params string[] k) { foreach (var x in k) if (w.Contains(x)) return true; return false; }
            if (Any("оснащ", "мебел", "отделк", "перегород", "номера", "аудитор", "раздевал")) return "Отделочники";
            if (Any("фасад", "витраж", "витрин", "стеклян", "ламел")) return "Монтажники фасада";
            if (Any("стальн", "металл", "шпил", "рёбр", "демонтаж кран")) return "Монтажники металлоконструкций";
            if (Any("инженер", "сети", "пусконалад", "эскалатор", "чистые")) return "Монтажники инженерных систем";
            if (Any("кровл", "террас")) return "Кровельщики";
            if (Any("котлован", "ограждени", "дренаж", "планировк")) return "Земляные работы и техника";
            if (Any("сад", "газон", "дерев", "мощени", "дорожк", "озер", "фонар", "фонтан", "площад", "амфитеатр", "двор", "озелен")) return "Благоустройство";
            if (Any("каркас", "перекрыт", "ядро", "колонн", "плит", "сва", "фундамент", "корпус", "крыл", "трибун", "захватк")) return "Бетонщики и арматурщики";
            return "Разнорабочие";
        }
        /// <summary>The work of building i most behind at date d (index in works), −1 if none.</summary>
        int LagWork(int i, float d)
        {
            int best = -1, bd = int.MinValue;
            for (int k = 0; k < works.Count; k++)
            {
                var w = works[k]; if (w.Sum || w.Part != i) continue;
                var s = Stat(w, d); if (s.Plan <= 0f || s.Fact >= 0.999f) continue;
                if (s.Days > bd) { bd = s.Days; best = k; }
            }
            return best;
        }
        /// <summary>The crew of building i at date d by trades: what the schedule asks for (the works going on by the plan) and what the cameras
        /// count; the trade of the work most behind is the one most short.</summary>
        List<Trade> Trades(int i, float d)
        {
            var list = new List<Trade>(); float need = CrewOf(i, PlanP(i, d)), have = CrewOf(i, FactP(i, d)) * (1f - Short(i, d));
            if (need < 1f && have < 1f) return list;
            int lag = LagWork(i, d); string lagT = lag >= 0 ? TradeOf(works[lag].Name) : null;
            var w8 = new Dictionary<string, float>(); var order = new List<string>();
            foreach (var w in works)
            {
                if (w.Sum || w.Part != i) continue;
                var s = Stat(w, d); if (!(s.Plan > 0f && s.Fact < 0.999f || s.Fact > 0f && s.Fact < 0.999f)) continue;
                string t = TradeOf(w.Name); if (!w8.ContainsKey(t)) { w8[t] = 0f; order.Add(t); }
                w8[t] += 1f / Mathf.Sqrt(Mathf.Max(w.B - w.A, 0.02f));
            }
            if (w8.Count == 0) { w8["Разнорабочие"] = 1f; order.Add("Разнорабочие"); }
            float tot = 0f; foreach (var v in w8.Values) tot += v;
            float sh = Short(i, d), hs = 0f; var nd = new float[order.Count]; var hv = new float[order.Count];
            for (int k = 0; k < order.Count; k++)
            {
                nd[k] = need * w8[order[k]] / tot; hv[k] = nd[k] * Mathf.Max(0.4f, 1f - sh * (order[k] == lagT ? 1.8f : 0.55f)); hs += hv[k];
            }
            float kh = hs > 0f ? have / hs : 0f;                                          // the trades add up to the people the cameras count
            for (int k = 0; k < order.Count; k++) list.Add(new Trade { Name = order[k], Need = Mathf.RoundToInt(nd[k]), Have = Mathf.RoundToInt(hv[k] * kh), Lag = order[k] == lagT });
            list.Sort((a, b) => (b.Need - b.Have).CompareTo(a.Need - a.Have));
            return list;
        }
        static void Sum(List<Trade> t, out int need, out int have) { need = have = 0; foreach (var x in t) { need += x.Need; have += x.Have; } }

        // ================================================================== documents
        /// <summary>A piece of a document: a heading, a paragraph, a table head or row, a signature; Id — the place the analytics points at.</summary>
        class Blk { public string Id, Kind, Text; public string[] Cells; public float[] Wd; }
        class Doc
        {
            public int Ix, Base, Score, Refs; public string Key, Short, Kind, Icon, Title, No, Date, Meta;
            public readonly List<Blk> B = new List<Blk>();
            public Doc H(string t) { B.Add(new Blk { Kind = "h", Text = t }); return this; }
            public Doc P(string id, string t) { B.Add(new Blk { Id = id, Kind = "p", Text = t }); return this; }
            public Doc Th(float[] wd, params string[] c) { B.Add(new Blk { Kind = "th", Cells = c, Wd = wd }); return this; }
            public Doc R(string id, float[] wd, params string[] c) { B.Add(new Blk { Id = id, Kind = "tr", Cells = c, Wd = wd }); return this; }
            public Doc S(string t) { B.Add(new Blk { Kind = "sign", Text = t }); return this; }
        }
        /// <summary>A place in a document a finding follows from.</summary>
        class Src { public int Doc; public string At, Label; }
        /// <summary>A finding: severity (2 critical, 1 important, 0 for information, −1 all right), what, why, where it follows from, where to see it.</summary>
        class Finding { public int Sev; public float Score; public string Icon, Title, Text, ShowText; public Action Show; public readonly List<Src> Src = new List<Src>(); }
        readonly List<Doc> docs = new List<Doc>(); readonly List<Finding> finds = new List<Finding>();
        const int DC = 0, DS = 1, DG = 2, DP = 3, DK = 4, DR = 5, DV = 6, DL = 7, DM = 8, DF = 9, DQ = 10, DJ = 11, DE = 12, DA = 13;
        Doc NewDoc(string key, string shortName, string kind, string icon, int imp, string title, string no, string date)
        {
            var d = new Doc { Ix = docs.Count, Key = key, Short = shortName, Kind = kind, Icon = icon, Base = imp, Title = title, No = no, Date = date }; docs.Add(d); return d;
        }
        Src At(int doc, string at, string where) => new Src { Doc = doc, At = at, Label = docs[doc].Short + " · " + where };

        // the facts the documents and the findings share
        int anWorst = -1, anLag = -1, anCrew = -1, anFloor = -1, anSurveyNo = 1, anKs = 1;
        float anNextSurvey;
        const string Gc = "Генподрядчик (условно)";
        string Code => "AC-" + District[Mathf.Clamp(L.District, 0, 3)].Substring(0, 2).ToUpper() + "-" + L.Id.ToUpper();

        /// <summary>The whole analytics at the date of the last survey (once per opening of the window).</summary>
        void MakeAnalytics()
        {
            float d = Report; int n = L.Parts.Count;
            MakeCost(d);
            trades = new List<Trade>[n]; for (int i = 0; i < n; i++) trades[i] = Trades(i, d);
            anWorst = -1; int wd = 3;
            for (int i = 0; i < n; i++) { var o = Obj(i, d); if (o.Fact > 0f && o.Fact < 0.999f && o.Days > wd) { wd = o.Days; anWorst = i; } }
            anLag = anWorst >= 0 ? LagWork(anWorst, d) : -1;
            anCrew = -1; float ws = 0.08f;
            for (int i = 0; i < n; i++) { Sum(trades[i], out int need, out int have); if (need > 20 && (need - have) / (float)need > ws) { ws = (need - have) / (float)need; anCrew = i; } }
            float tp = FactP(TI, d); anFloor = tp > 0.12f && tp < 0.999f ? Mathf.Max(WorkFloor(tp) - 2, 2) : -1;
            anSurveyNo = svA + 1; anNextSurvey = svA + 1 < surveys.Count ? surveys[svA + 1] : Report + 0.33f;
            anKs = Mathf.Max(1, Mathf.RoundToInt((d - L.Begin) * 12f));
            docs.Clear(); finds.Clear();
            MakeDocs(d); MakeFindings(d);
            // importance: the weight of the document plus the findings that cite it
            foreach (var doc in docs) { doc.Refs = 0; doc.Score = doc.Base; }
            foreach (var f in finds)
            {
                var seen = new HashSet<int>();
                foreach (var s in f.Src) { var doc = docs[s.Doc]; doc.Refs++; if (seen.Add(s.Doc)) doc.Score += f.Sev >= 2 ? 15 : f.Sev == 1 ? 8 : f.Sev == 0 ? 3 : 1; }
            }
        }

        static readonly float[] W2 = { 0.62f, 0.38f }, W3 = { 0.5f, 0.25f, 0.25f }, W4 = { 0.46f, 0.18f, 0.18f, 0.18f }, W5 = { 0.36f, 0.12f, 0.17f, 0.17f, 0.18f };
        void MakeDocs(float d)
        {
            int n = L.Parts.Count; string code = Code, cust = Customer(), sign = Day(L.Begin - 0.06f);
            var names = new List<string>(); for (int i = 0; i < n; i++) names.Add(Pt(i).Name);
            float price = anTot.B + anRes;

            // ---- 0: the general contract
            var c = NewDoc("contract", "Договор ГП", "Договор", "file_pen_line", 100, "Договор генерального подряда", $"№ {code}-ГП/01", sign);
            c.Meta = $"{cust} (Заказчик) и {Gc} (Генподрядчик) · г. Алматы";
            c.H("1. Предмет договора")
             .P("p1.1", $"1.1. Генподрядчик обязуется построить и ввести в эксплуатацию объект «{L.Name}» в составе: {string.Join(", ", names)}, а Заказчик — принять и оплатить работы.")
             .P("p1.2", "1.2. Объём работ определяется проектной документацией с положительным заключением экспертизы и сводным сметным расчётом (приложение 1).")
             .H("2. Цена договора")
             .P("p2.1", $"2.1. Цена договора — {Mln(price)}, в том числе резерв на непредвиденные работы и затраты {Mln(anRes)} (4 %). Расчёты — в тенге по курсу НБ РК на дату платежа.")
             .P("p2.2", "2.2. Цена определена в ценах на 01.10.2026. Материалы и оборудование, законтрактованные по фиксированной цене, не индексируются.")
             .H("3. Сроки")
             .P("p3.1", $"3.1. Начало работ — {Day(L.Begin)}, ввод комплекса — {IconicFloors.MonthYear(L.Finish)}. Сроки ввода отдельных объектов — по календарному графику (приложение 2).")
             .P("p3.2", "3.2. Генподрядчик еженедельно передаёт Заказчику фактическую численность персонала и выполнение графика. Данные аэросъёмок и видеоаналитики цифрового двойника признаются сторонами.")
             .H("4. Персонал и техника")
             .P("p4.2", "4.2. Генподрядчик обеспечивает численность персонала по профессиям не ниже графика движения рабочей силы. При нехватке более 10 % дольше двух недель Генподрядчик в течение 5 дней представляет план восполнения.")
             .H("5. Изменение цены")
             .P("p5.4", "5.4. Стоимость невыполненных объёмов, не закреплённых фиксированной ценой, ежеквартально пересчитывается по ведомости мониторинга цен на основные ресурсы.")
             .P("p5.5", "5.5. Затраты сверх резерва на непредвиденные работы оплачиваются только по дополнительному соглашению, утверждённому Заказчиком.")
             .H("9. Ответственность")
             .P("p9.3", "9.3. За нарушение срока ввода объекта Генподрядчик уплачивает неустойку 0,05 % стоимости объекта за каждый день просрочки, но не более 10 % его стоимости.")
             .S("Заказчик ____________          Генподрядчик ____________");

            // ---- 1: the summary estimate
            var s = NewDoc("estimate", "ССР", "Смета", "receipt", 95, "Сводный сметный расчёт стоимости строительства", $"{code}-ССР, ред. 2", Day(L.Begin - 0.1f));
            s.Meta = "в ценах на 01.10.2026 · млн $ по курсу 447,94 ₸/$";
            var wd = new float[n + 2]; wd[0] = 0.3f; for (int i = 0; i <= n; i++) wd[i + 1] = 0.7f / (n + 1);
            var head = new string[n + 2]; head[0] = "Статья затрат"; for (int i = 0; i < n; i++) head[i + 1] = Pt(i).Short; head[n + 1] = "Итого";
            s.H("Затраты по объектам и статьям, млн $").Th(wd, head);
            for (int k = 0; k < Items.Length; k++)
            {
                var row = new string[n + 2]; row[0] = (k + 1) + ". " + Items[k].Name; bool any = false;
                for (int i = 0; i < n; i++) { float b = cost[i, k].B; row[i + 1] = b > 0f ? Loc.N1(b) : "—"; any |= b > 0f; }
                row[n + 1] = Loc.N1(ItemCost(k, -1).B); if (any) s.R("r" + k, wd, row);
            }
            var tr = new string[n + 2]; tr[0] = "Итого по статьям"; for (int i = 0; i < n; i++) tr[i + 1] = Loc.N1(Pt(i).Capex); tr[n + 1] = Loc.N1(anTot.B); s.R("rTot", wd, tr);
            var rr = new string[n + 2]; rr[0] = "Резерв на непредвиденные работы и затраты (4 %)"; for (int i = 0; i < n; i++) rr[i + 1] = ""; rr[n + 1] = Loc.N1(anRes); s.R("rRes", wd, rr);
            var ra = new string[n + 2]; ra[0] = "Всего по сводному расчёту"; for (int i = 0; i < n; i++) ra[i + 1] = ""; ra[n + 1] = Loc.N1(price); s.R("rAll", wd, ra);
            s.P("pNote", "Стоимость бетона, арматуры и металлопроката принята по рынку Алматы на октябрь 2026 года, импортного оборудования — по курсу НБ РК 447,94 ₸/$ на 23.10.2026.");

            // ---- 2: the schedule and the crew
            var g = NewDoc("schedule", "ГПР", "График", "gantt_chart", 90, "Календарный график производства работ и движения рабочей силы", $"{code}-ГПР, ред. 3", Day(L.Begin - 0.08f));
            g.Meta = "приложение 2 к договору генподряда";
            g.H("1. Сроки ввода объектов").Th(W3, "Объект", "Начало", "Ввод");
            for (int i = 0; i < n; i++) g.R("o" + i, W3, Pt(i).Name, IconicFloors.MonthYear(Pt(i).A), IconicFloors.MonthYear(Pt(i).B));
            g.H("2. Работы").Th(W3, "Работа", "Начало", "Окончание");
            for (int k = 0; k < works.Count; k++)
            {
                var w = works[k]; if (w.Sum) continue;
                g.R("w" + k, W3, w.Code + "  " + w.Name, Day(PlanDate(w.Part, w.A)), Day(PlanDate(w.Part, w.B)));
            }
            g.H($"3. Численность по графику на {IconicFloors.MonthYear(d)}").Th(W2, "Объект, профессия", "Человек");
            for (int i = 0; i < n; i++)
            {
                Sum(trades[i], out int need, out _); if (need <= 0) continue;
                g.R("c" + i, W2, Pt(i).Name, Loc.N0(need));
                foreach (var t in trades[i]) g.R("c" + i + "_" + t.Name, W2, "   " + t.Name, Loc.N0(t.Need));
            }

            // ---- 3: the prices of the resources
            var p = NewDoc("prices", "Цены", "Цены", "coins", 80, "Ведомость мониторинга цен на основные ресурсы", $"№ {Mathf.Max(1, Mathf.RoundToInt((d - PriceBase) * 4f))}", Day(d));
            p.Meta = $"к пересчёту по п. 5.4 договора генподряда · цены сметы — 01.10.2026, текущие — на {Day(d)}";
            p.Th(W5, "Ресурс", "Ед.", "В смете", $"На {Day(d)}", "Изменение");
            for (int r = 0; r < Rsc.Length; r++)
            {
                float now = PriceAt(r, d);
                p.R("r" + r, W5, Rsc[r].Name, Rsc[r].Unit, PriceText(r, Rsc[r].Base), PriceText(r, now), SPc(now / Rsc[r].Base - 1f));
            }
            p.P("pRule", "Стоимость оставшихся объёмов = остаток объёма по смете × цена на дату × доля, не закреплённая фиксированной ценой; закреплённая доля — по цене договора поставки.");
            p.P("pSrc", "Цены сметы: бетон, арматура и металлопрокат — объявления olx.kz по Алматы 22–26.10.2026, курс — НБ РК на 23.10.2026; фасадные модули, труд, аренда крана и индексы — допущения модели. Цены на дату — прогноз цифрового двойника по индексам.");

            // ---- 4: what is done and paid (KS-3)
            var ks = NewDoc("ks3", "КС-3", "Акт", "file_check", 75, "Справка о стоимости выполненных работ и затрат (КС-3)", $"№ {anKs}", Day(d - 0.02f));
            ks.Meta = $"с начала строительства по {Day(d)} · {Gc} → {cust} · млн $";
            ks.Th(W4, "Статья", "Бюджет", "Выполнено", "В т. ч. рост цен");
            for (int k = 0; k < Items.Length; k++)
            {
                var ic = ItemCost(k, -1); if (ic.B <= 0f) continue;
                ks.R("r" + k, W4, (k + 1) + ". " + Items[k].Name, Loc.N1(ic.B), Loc.N1(ic.Ac), Loc.N1(ic.Ac - ic.Ev));
            }
            ks.R("rTot", W4, "Итого с начала строительства", Loc.N1(anTot.B), Loc.N1(anTot.Ac), Loc.N1(anTot.Ac - anTot.Ev));
            ks.P("pNote", "Выполненные объёмы подтверждены аэросъёмкой, исполнительной документацией и актами скрытых работ.");

            // ---- 5: the survey report
            var rp = NewDoc("survey", "Отчёт о съёмке", "Отчёт", "history", 70, "Отчёт о мониторинге строительства по аэросъёмке", $"№ {anSurveyNo}", Day(d));
            rp.Meta = "ортофотоплан и 3D-модель площадки · сравнение с BIM-моделью и графиком";
            rp.P("p1", $"Съёмка {Day(d)}: ортофотоплан с разрешением {Loc.N1(Gsd(svA))} см, 3D-модель площадки по {Loc.N0(Shots(svA))} снимкам.");
            rp.H("1. Готовность объектов").Th(W4, "Объект", "План", "Факт", "Отклонение");
            int behind = 0;
            for (int i = 0; i < n; i++)
            {
                var o = Obj(i, d); if (o.Days > 3 && o.Fact < 0.999f) behind++;
                rp.R("o" + i, W4, Pt(i).Name, Pct(o.Plan), Pct(o.Fact), o.Plan <= 0f && o.Fact <= 0f ? "—" : o.Days > 3 ? $"−{o.Days} дн." : o.Days < -3 ? $"+{-o.Days} дн." : "в графике");
            }
            rp.H("2. Отстающие работы").Th(W4, "Работа", "План", "Факт", "Отставание");
            var lag = new List<int>();
            for (int k = 0; k < works.Count; k++) { var w = works[k]; if (w.Sum) continue; var st = Stat(w, d); if (st.Plan > 0f && st.Fact < 0.999f && st.Days > 3) lag.Add(k); }
            lag.Sort((a, b) => Stat(works[b], d).Days.CompareTo(Stat(works[a], d).Days));
            for (int j = 0; j < lag.Count && j < 8; j++) { var w = works[lag[j]]; var st = Stat(w, d); rp.R("w" + lag[j], W4, w.Code + "  " + w.Name, Pct(st.Plan), Pct(st.Fact), $"{st.Days} дн."); }
            if (anWorst >= 0) rp.P("pConc", $"Вывод: отстают {behind} из {n} объектов, больше всего — {Pt(anWorst).Name}, {Obj(anWorst, d).Days} дн.");
            else rp.P("pConc", "Вывод: все объекты идут по графику.");

            // ---- 6: video analytics
            var v = NewDoc("video", "Видеоаналитика", "Отчёт", "cctv", 60, "Отчёт видеоаналитики: численность и охрана труда", $"неделя {Mathf.Clamp(Mathf.FloorToInt((d - Mathf.Floor(d)) * 52f) + 1, 1, 52)}", Day(d - 0.003f));
            v.Meta = "6 камер · подсчёт людей по зонам работ и на КПП · среднее за дневную смену";
            v.H("1. Численность по объектам").Th(W4, "Объект", "По графику", "На площадке", "Разница");
            for (int i = 0; i < n; i++)
            {
                Sum(trades[i], out int need, out int have); if (need <= 0 && have <= 0) continue;
                v.R("c" + i, W4, Pt(i).Name, Loc.N0(need), Loc.N0(have), Diff(have - need));
            }
            int cp = anCrew >= 0 ? anCrew : anWorst;
            if (cp >= 0 && trades[cp].Count > 0)
            {
                v.H($"2. По профессиям · {Pt(cp).Name}").Th(W4, "Профессия", "По графику", "На площадке", "Разница");
                foreach (var t in trades[cp]) v.R("t" + t.Name, W4, t.Name, Loc.N0(t.Need), Loc.N0(t.Have), Diff(t.Have - t.Need));
            }
            v.H("3. Охрана труда").Th(W3, "Событие", "Камера", "Случаев");
            v.R("s1", W3, "Работа у края плиты без страховки — прораб уведомлён", "CAM-07", "2");
            v.R("s2", W3, "Без каски в зоне работы крана — устранено", "CAM-01", "1");
            v.R("s3", W3, "Опасные зоны под кранами — нарушений нет", "CAM-02", "0");

            // ---- 7: the contractor's letter on the delay
            int wp = anWorst >= 0 ? anWorst : TI; var wpo = Obj(wp, d);
            var lt = NewDoc("letter", "Письмо ГП", "Письмо", "mail", 65, "Письмо генподрядчика о причинах отставания", $"исх. № {120 + anKs * 3}", Day(d - 0.04f));
            lt.Meta = $"{Gc} → {cust}";
            Trade lt0 = null; if (trades[wp].Count > 0) { lt0 = trades[wp][0]; foreach (var t in trades[wp]) if (t.Lag) { lt0 = t; break; } }
            int top = TopOver();
            lt.P("p1", wpo.Days > 3 ? $"По объекту «{Pt(wp).Name}» на {Day(d)} отставание от графика составляет {wpo.Days} дн." : $"По объекту «{Pt(wp).Name}» работы идут по графику.");
            if (lt0 != null) lt.P("p2", $"Основная причина — нехватка персонала: {lt0.Name.ToLowerInvariant()} — {lt0.Have} из {lt0.Need} человек по графику. Часть бригад ушла на объекты с более высокой оплатой; набор идёт, но потребность не закрывает.");
            lt.P("p3", $"Дополнительно: {Pt(wp).Risk}.");
            if (top >= 0)
            {
                int r = MainRes(top); float dp = PriceAt(r, d) / Rsc[r].Base - 1f;
                lt.P("p4", $"Стоимость статьи «{Items[top].Name}» растёт: {Rsc[r].Name.ToLowerInvariant()} — {SPc(dp)} к цене сметы. Просим пересчитать оставшиеся объёмы по п. 5.4 договора.");
            }
            int add = lt0 != null ? Mathf.Max(lt0.Need - lt0.Have, 5) : 20;
            lt.P("p5", $"Предлагаем вторую смену и {add} человек от субподрядчика до {Day(d + 0.06f)}; отставание закрываем к {IconicFloors.MonthYear(d + 0.5f)}.");
            lt.S("Директор проекта ____________");

            // ---- 8: the minutes of the site meeting
            var m = NewDoc("minutes", "Протокол", "Протокол", "clipboard_check", 60, "Протокол производственного совещания", $"№ {40 + anKs}", Day(d - 0.01f));
            m.Meta = "Заказчик, генподрядчик, технический надзор, проектировщик";
            m.H("Решили:");
            m.P("d1", lt0 != null ? $"1. Генподрядчику до {Day(d + 0.06f)} довести численность на объекте «{Pt(wp).Name}» до графика: +{add} человек ({lt0.Name.ToLowerInvariant()}), вторая смена." : "1. Сохранить численность по графику.");
            m.P("d2", $"2. Технадзору проверить пересчёт стоимости по ведомости цен; рост статьи «{(top >= 0 ? Items[top].Name : Items[2].Name)}» рассмотреть в дополнительном соглашении.");
            m.P("d3", $"3. До подписания дополнительного соглашения расходовать резерв на непредвиденные затраты не более {Mln(anRes * 0.5f)}.");
            if (anFloor >= 0) m.P("d4", $"4. Отклонение отметки плиты {anFloor + 1}-го этажа ({Pt(TI).Short}) +14 мм — устранить шлифовкой до монтажа фасада.");
            m.P("d5", $"5. Следующая аэросъёмка — {Day(anNextSurvey)}.");

            // ---- 9: the facade supply contract
            var f = NewDoc("facade", "Поставка фасада", "Договор", "file_pen_line", 50, "Договор поставки фасадных модулей", $"№ {code}-ФС/07", Day(L.Begin + 0.15f));
            f.Meta = $"{Gc} и поставщик фасадных систем";
            f.P("p3.1", $"3.1. Цена {Mathf.RoundToInt(FixedOf(4) * 100f)} % объёма модулей зафиксирована в долларах на весь срок поставки; остальной объём — по цене на дату заказа партии.");
            f.P("p4.2", "4.2. Срок изготовления партии — 10 недель с даты заказа. Задержка поставки более двух недель — неустойка 0,1 % стоимости партии за день.");

            // ---- 10: the as-built survey of a slab
            int fl = anFloor >= 0 ? anFloor : 2; float y0 = IconicShape.FloorY(fl);
            var q = NewDoc("asbuilt", "ИГС", "Исп. документация", "ruler", 45, $"Исполнительная геодезическая схема: плита {fl + 1}-го этажа · {Pt(TI).Short}", $"ИГС-{fl + 1:00}", Day(d - 0.02f));
            q.Meta = "тахеометр, 6 точек по контуру плиты · допуск отметки ±10 мм";
            float[] wq = { 0.2f, 0.2f, 0.2f, 0.2f, 0.2f };
            q.Th(wq, "Точка", "Проект, м", "Факт, м", "Отклонение, мм", "Допуск, мм");
            int[] dev = { 3, -4, 6, 14, 8, -2 };
            for (int k = 0; k < dev.Length; k++) q.R("g" + (k + 1), wq, (k + 1).ToString(), (y0).ToString("N3", Loc.Ru), (y0 + dev[k] / 1000f).ToString("N3", Loc.Ru), (dev[k] > 0 ? "+" : dev[k] < 0 ? "−" : "") + Mathf.Abs(dev[k]), "±10");
            q.P("pConc", "Отклонение в точке 4 превышает допуск. До монтажа фасада — шлифовка и повторная съёмка.");

            // ---- 11: the site log
            var j1 = NewDoc("log", "Журнал работ", "Журнал", "book_open", 40, "Общий журнал работ (выписка)", $"том {1 + anKs / 12}", Day(d));
            j1.Th(W2, "Запись", "Дата");
            if (anFloor >= 0) j1.R("j1", W2, $"Бетонирование плиты {anFloor + 3}-го этажа {Pt(TI).Short}, 2 захватки", Day(d - 0.004f));
            if (lt0 != null) j1.R("j2", W2, $"{Pt(wp).Short}: на смене {lt0.Have} из {lt0.Need} человек ({lt0.Name.ToLowerInvariant()})", Day(d - 0.008f));
            j1.R("j3", W2, "Поставка фасадных модулей, партия 14 — принята, замечаний нет", Day(d - 0.011f));
            j1.R("j4", W2, "Простой башенного крана К-2 — 6 ч, ветер 15 м/с", Day(d - 0.015f));
            j1.R("j5", W2, "Нарушение охраны труда: работа у края плиты без страховки, CAM-07 — прораб уведомлён", Day(d - 0.017f));
            if (anFloor >= 0) j1.R("j6", W2, $"Исполнительная съёмка плиты {anFloor + 1}-го этажа: отклонение +14 мм в точке 4", Day(d - 0.02f));

            // ---- 12, 13: the expertise and the permit
            var e = NewDoc("expertise", "Экспертиза", "Заключение", "badge_check", 35, "Положительное заключение комплексной вневедомственной экспертизы", $"№ 01-{(int)(L.Begin * 7) % 1000:000}/{Mathf.FloorToInt(L.Begin)}", Day(L.Begin - 0.2f));
            e.P("p1", $"Проект «{L.Name}» и сметная документация соответствуют нормам РК; сметная стоимость подтверждена в ценах на 01.10.2026.");
            e.P("p2", "Сейсмичность площадки — 9 баллов; конструктивные решения с демпферами признаны достаточными.");
            var a = NewDoc("permit", "Уведомление о начале СМР", "Разрешение", "landmark", 30, "Уведомление о начале строительно-монтажных работ", $"№ KZ{(int)(L.Begin * 13) % 100:00}UCA{(int)(L.Begin * 911) % 100000:00000}", Day(L.Begin - 0.02f));
            a.P("p1", $"Объект «{L.Name}», Alatau City. Начало работ — {Day(L.Begin)}. Технический надзор и авторский надзор назначены.");
        }
        static string Diff(int v) => v > 0 ? "+" + Loc.N0(v) : v < 0 ? "−" + Loc.N0(-v) : "0";
        /// <summary>The cost item with the largest overrun (−1 if none).</summary>
        int TopOver() { int b = -1; float bo = 0f; for (int k = 0; k < Items.Length; k++) { float o = ItemCost(k, -1).Over; if (o > bo) { bo = o; b = k; } } return b; }

        // ================================================================== findings
        void MakeFindings(float d)
        {
            int n = L.Parts.Count;
            Finding F(int sev, float score, string icon, string title, string text) { var f = new Finding { Sev = sev, Score = score, Icon = icon, Title = title, Text = text }; finds.Add(f); return f; }

            // ---- money: the whole estimate
            float over = anTot.Over, rest = anTot.Etc + anTot.Extra;
            if (over > 0f)
            {
                var f = F(NetOver > 0f ? 2 : 1, over, "wallet",
                    NetOver > 0f ? $"Перерасход: прогноз стоимости выше бюджета на {Mln(over)} ({SPc(over / anTot.B)})" : $"Стоимость растёт на {Mln(over)} — пока в пределах резерва",
                    $"Потрачено {Mln(anTot.Ac)}, на оставшиеся работы по ценам на {Day(d)} нужно ещё {Mln(rest)}. Резерв {Mln(anRes)} " +
                    (NetOver > 0f ? $"не покрывает {Mln(NetOver)} — нужно дополнительное соглашение." : $"израсходуется на {Pct(over / Mathf.Max(anRes, 0.01f))}."));
                f.Src.Add(At(DS, "rTot", "итог")); f.Src.Add(At(DS, "rRes", "резерв")); f.Src.Add(At(DK, "rTot", "итог")); f.Src.Add(At(DC, "p5.5", "п. 5.5"));
                f.ShowText = "Открыть смету"; f.Show = () => { anItem = TopOver(); AnView(1); };
            }
            // ---- money: the items that grow most
            var ks = new List<int>(); for (int k = 0; k < Items.Length; k++) { var ic = ItemCost(k, -1); if (ic.Over > 0.5f && ic.Over > ic.B * 0.01f) ks.Add(k); }
            ks.Sort((a, b) => ItemCost(b, -1).Over.CompareTo(ItemCost(a, -1).Over));
            for (int j = 0; j < ks.Count && j < 3; j++)
            {
                int k = ks[j]; var ic = ItemCost(k, -1); int r = MainRes(k); float dp = PriceAt(r, d) / Rsc[r].Base - 1f;
                int sev = ic.Over / ic.B > 0.15f && NetOver > 0f ? 2 : 1;
                string why = Items[k].Time && ic.Extra > ic.Over * 0.4f
                    ? $"Объекты строятся дольше графика: техника и площадка оплачиваются дольше (+{Mln(ic.Extra)}). {Rsc[r].Name}: {PriceText(r, Rsc[r].Base)} → {PriceText(r, PriceAt(r, d))} ({SPc(dp)})."
                    : $"{Rsc[r].Name}: {PriceText(r, Rsc[r].Base)} → {PriceText(r, PriceAt(r, d))} ({SPc(dp)}). " + (FixedOf(k) > 0f ? $"По фиксированной цене закуплено {Mathf.RoundToInt(FixedOf(k) * 100f)} % объёма, выполнено {Pct(ic.Q)}." : $"Цена не фиксирована, выполнено {Pct(ic.Q)}.");
                var f = F(sev, ic.Over, "trending_up", $"{Items[k].Name}: прогноз {SMln(ic.Over)} ({SPc(ic.Over / ic.B)})", why);
                f.Src.Add(At(DS, "r" + k, $"строка {k + 1}")); f.Src.Add(At(DP, "r" + r, $"поз. {r + 1}"));
                if (ic.Ac > 0f) f.Src.Add(At(DK, "r" + k, $"строка {k + 1}"));
                f.Src.Add(k == 4 ? At(DF, "p3.1", "п. 3.1") : At(DC, "p5.4", "п. 5.4"));
                int kk = k; f.ShowText = "Расчёт статьи"; f.Show = () => { anItem = kk; AnView(1); };
            }
            // ---- time: the buildings behind the plan
            for (int i = 0; i < n; i++)
            {
                var o = Obj(i, d); if (!(o.Fact > 0f && o.Fact < 0.999f && o.Days > 3)) continue;
                int w = LagWork(i, d); var st = w >= 0 ? Stat(works[w], d) : new St();
                bool late = o.EndDays > 3;
                var f = F(o.Days > 21 && late ? 2 : 1, o.Days * Pt(i).Capex / 100f, "clock", $"{Pt(i).Name} отстаёт от графика на {o.Days} дн.",
                    (w >= 0 ? $"{works[w].Name}: факт {Pct(st.Fact)} при плане {Pct(st.Plan)}. " : "") +
                    (late ? $"Ввод сдвигается на {o.EndDays} дн. — на {IconicFloors.MonthYear(o.FactEnd)}." : "По прогнозу отставание закрывается к вводу — вторая смена."));
                if (w >= 0) { f.Src.Add(At(DG, "w" + w, $"работа {works[w].Code}")); f.Src.Add(At(DR, "w" + w, $"работа {works[w].Code}")); }
                f.Src.Add(At(DR, "o" + i, "табл. 1"));
                if (i == wp()) { f.Src.Add(At(DL, "p1", "абзац 1")); if (docs[DL].B.Exists(b => b.Id == "p3")) f.Src.Add(At(DL, "p3", "абзац 3")); }
                int ii = i; f.ShowText = "Показать в 4D"; f.Show = () => { SetTab(T4D); SelectObj(ii, true); };
                // the hand-over later than the contract: the penalty of the contract
                if (late)
                {
                    float pen = Mathf.Min(0.0005f * Pt(i).Capex * o.EndDays, 0.1f * Pt(i).Capex);
                    var g = F(o.EndDays > 45 ? 2 : 1, pen * 10f, "scale", $"Риск неустойки: ввод «{Pt(i).Name}» позже договорного на {o.EndDays} дн.",
                        $"По договору — 0,05 % стоимости объекта в день: до {Mln(pen)}. Плановый ввод {IconicFloors.MonthYear(o.PlanEnd)}, прогноз {IconicFloors.MonthYear(o.FactEnd)}.");
                    g.Src.Add(At(DC, "p9.3", "п. 9.3")); g.Src.Add(At(DG, "o" + i, "табл. 1"));
                    g.ShowText = "Вводы объектов"; g.Show = () => SetTab(TInv);
                }
            }
            // ---- people: where the cameras count fewer than the schedule asks for
            for (int i = 0; i < n; i++)
            {
                Sum(trades[i], out int need, out int have); if (need < 20) continue;
                float sh = (need - have) / (float)need; if (sh < 0.08f) continue;
                Trade t0 = trades[i][0];
                var f = F(sh >= 0.2f ? 2 : 1, (need - have) / 10f, "user_x", $"Не хватает людей: {Pt(i).Name} — {Loc.N0(have)} из {Loc.N0(need)} человек ({SPc(-sh)})",
                    $"Сильнее всего — {t0.Name.ToLowerInvariant()}: {t0.Have} из {t0.Need}. " + (Obj(i, d).Days > 3 ? "Это главная причина отставания объекта." : "Пока без отставания, но запаса нет."));
                f.Src.Add(At(DV, "c" + i, "табл. 1")); if (i == (anCrew >= 0 ? anCrew : anWorst)) f.Src.Add(At(DV, "t" + t0.Name, "табл. 2"));
                f.Src.Add(At(DG, "c" + i, "табл. 3")); f.Src.Add(At(DC, "p4.2", "п. 4.2"));
                if (i == wp() && docs[DL].B.Exists(b => b.Id == "p2")) f.Src.Add(At(DL, "p2", "абзац 2"));
                if (i == wp()) f.Src.Add(At(DM, "d1", "решение 1"));
                f.ShowText = "Камеры"; f.Show = () => OpenCam(Array.IndexOf(CamId, "CAM-04") >= 0 ? Array.IndexOf(CamId, "CAM-04") : 0);
            }
            // ---- quality: the as-built survey
            if (anFloor >= 0)
            {
                var f = F(1, 3f, "ruler", $"Плита {anFloor + 1}-го этажа {Pt(TI).Short}: отклонение +14 мм при допуске ±10 мм",
                    "Исполнительная съёмка, точка 4. Устранить шлифовкой до монтажа фасада, иначе модули витража не встанут в проектное положение.");
                f.Src.Add(At(DQ, "g4", "точка 4")); f.Src.Add(At(DM, "d4", "решение 4")); f.Src.Add(At(DJ, "j6", "запись"));
                f.ShowText = "Захватка"; f.Show = () => { SetTab(TObj); SelectObj(TI, false); SetView(View.Floor); };
            }
            // ---- safety: the cameras
            {
                var f = F(0, 2f, "hard_hat", "2 нарушения охраны труда за неделю: работа у края плиты без страховки",
                    "Видеоаналитика CAM-07 зафиксировала два случая, прораб уведомлён, нарушения закрыты. Опасные зоны под кранами — без нарушений.");
                f.Src.Add(At(DV, "s1", "табл. 3")); f.Src.Add(At(DJ, "j5", "запись"));
                f.ShowText = "Камера CAM-07"; f.Show = () => OpenCam(Mathf.Max(Array.IndexOf(CamId, "CAM-07"), 0));
            }
            // ---- all right: the buildings ahead of the plan
            for (int i = 0; i < n; i++)
            {
                var o = Obj(i, d); if (!(o.Fact > 0f && o.Days < -3)) continue;
                var f = F(-1, -o.Days, "circle_check", o.Fact >= 0.999f ? $"{Pt(i).Name} введён раньше графика на {-o.Days} дн." : $"{Pt(i).Name} опережает график на {-o.Days} дн.", Pt(i).Risk);
                f.Src.Add(At(DR, "o" + i, "табл. 1"));
                int ii = i; f.ShowText = "Показать в 4D"; f.Show = () => { SetTab(T4D); SelectObj(ii, true); };
            }
            finds.Sort((a, b) => a.Sev != b.Sev ? b.Sev.CompareTo(a.Sev) : b.Score.CompareTo(a.Score));
        }
        /// <summary>The building of the contractor's letter: the one most behind (the tower if none).</summary>
        int wp() => anWorst >= 0 ? anWorst : TI;
    }
}
