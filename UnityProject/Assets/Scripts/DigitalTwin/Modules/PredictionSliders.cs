using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>The «Прогноз 2026–2050» view of the Prediction tab. Left column: the four sliders and the choice of A and B;
    /// right column: the answer (first power deficit A → B), one chart with the two scenarios and a 2030/2040/2050 table.
    /// Moving a slider recomputes only the custom slot (ForecastModel.Compute, no allocations) and rewrites the labels.</summary>
    public class PredictionSliders
    {
        static readonly string[] SlotNames = { "Генплан", "Быстрее", "Медленнее", "Сети раньше", "Свой" };
        static readonly string[] Charts = { "Жители", "Рабочие места", "ВРП", "Электричество", "Вода" };
        static int a = 0, b = 1, chartK = 3;
        static readonly int[] Years = { 2030, 2040, 2050 };
        static readonly Color ColA = new Color(0.99f, 0.99f, 0.99f), ColB = new Color(0.48f, 0.65f, 1f), ColCap = new Color(0.53f, 0.53f, 0.53f);

        class Sl { public string Name; public int Min, Max; public TwinSlider S; public Label V; }
        readonly Sl[] sl = new Sl[4];
        readonly Button[][] pick = new Button[2][];
        readonly Button[] chartChips = new Button[Charts.Length];
        Glance.Hero hero; Label chartTitle, tableNote, resetHint; TwinChart chart; VisualElement legend; Button reset;
        readonly Label[,] cellA = new Label[5, 3], cellB = new Label[5, 3];
        readonly float[][] ser = new float[3][]; readonly float[] capLine = new float[ForecastModel.NY]; readonly bool[] alerts = new bool[ForecastModel.NY];
        bool built;

        public static void Pick(int na, int nb, int chart)
        {
            if (na >= 0 && na < SlotNames.Length) a = na; if (nb >= 0 && nb < SlotNames.Length) b = nb; if (chart >= 0 && chart < Charts.Length) chartK = chart;
        }

        public void BuildLeft(VisualElement col)
        {
            built = true; ForecastModel.Ensure();
            var pb = Widgets.Block(col, "Что сравниваем");
            for (int k = 0; k < 2; k++)
            {
                var r = new VisualElement(); r.AddToClassList("w27-pick"); pb.Add(r);
                var tag = new VisualElement(); tag.AddToClassList("w27-pick-tag"); r.Add(tag);
                tag.Add(Widgets.Dot(k == 0 ? ColA : ColB, true));
                var tl = new Label(k == 0 ? "A" : "B"); tl.AddToClassList("w27-pick-l"); tag.Add(tl);
                var chips = new VisualElement(); chips.AddToClassList("chips"); chips.AddToClassList("w27-chips"); r.Add(chips);
                pick[k] = new Button[SlotNames.Length];
                for (int i = 0; i < SlotNames.Length; i++)
                {
                    int kk = k, ii = i;
                    var bt = new Button(() => { if (kk == 0) a = ii; else b = ii; Update(); }) { text = SlotNames[i] };
                    bt.AddToClassList("chip"); bt.AddToClassList("w27-chip"); chips.Add(bt); pick[k][i] = bt;
                }
            }
            var pd = Widgets.Details(pb, "Что значат сценарии");
            Glance.Prose(pd, "Генплан — годы ввода из сценария застройки QTwin. Быстрее — темп +33 %, сети успевают лишь частично. " +
                "Медленнее — темп −23 %, часть города не успевает к 2050. Сети раньше — подстанции и ЛРТ на 2 года раньше, жильё первой очереди ждёт сети. " +
                "Свой — генплан, сдвинутый ползунками ниже.");
            var blk = Widgets.Block(col, "Свой сценарий", "100 % = генплан");
            sl[0] = Slider(blk, "Темп ввода жилья", 60, 150, 100, "Как быстро сдают жильё", v => ForecastModel.Housing = v);
            sl[1] = Slider(blk, "Миграция", 60, 130, 100, "Сколько людей заселяется в новое жильё", v => ForecastModel.Migration = v);
            sl[2] = Slider(blk, "Доля промышленности", 5, 40, ForecastModel.IndustryBase, "Доля заводов и логистики в рабочих местах", v => ForecastModel.Industry = v);
            sl[3] = Slider(blk, "Темп ввода сетей", 60, 150, 100, "Подстанции и водозаборы раньше или позже", v => ForecastModel.Nets = v);
            var row = new VisualElement(); row.AddToClassList("w27-reset-row"); blk.Add(row);
            reset = Widgets.Btn("Вернуть генплан", () => { ForecastModel.Reset(); SyncSliders(); Update(); }, "small", "ghost"); row.Add(reset);
            resetHint = new Label(); resetHint.AddToClassList("w27-meta"); row.Add(resetHint);

        }

        public void BuildRight(VisualElement col)
        {
            var blk = Widgets.Block(col);
            Widgets.Eyebrow(blk, "ПРОГНОЗ 2026–2050 · A И B РЯДОМ");
            hero = Glance.MakeHero(blk);

            var cc = new VisualElement(); cc.AddToClassList("chips"); cc.AddToClassList("w27-chips"); cc.style.marginTop = 6; blk.Add(cc);
            for (int i = 0; i < Charts.Length; i++)
            {
                int ii = i; var bt = new Button(() => { chartK = ii; Update(); }) { text = Charts[i] };
                bt.AddToClassList("chip"); bt.AddToClassList("w27-chip"); cc.Add(bt); chartChips[i] = bt;
            }
            chartTitle = new Label(); chartTitle.AddToClassList("w27-chart-t"); blk.Add(chartTitle);
            chart = new TwinChart(); chart.AddToClassList("w27-chart"); blk.Add(chart);
            legend = new VisualElement(); legend.AddToClassList("legend"); blk.Add(legend);

            // table: rows = key results, columns = 2030 / 2040 / 2050; each cell A (muted) over B (bright, coloured when it differs)
            var t = new VisualElement(); t.AddToClassList("w27-table"); blk.Add(t);
            var hr = new VisualElement(); hr.AddToClassList("w27-tr"); hr.AddToClassList("w27-th"); t.Add(hr);
            var h0 = new Label(""); h0.AddToClassList("w27-td-l"); hr.Add(h0);
            foreach (var y in Years) { var l = new Label(y.ToString()); l.AddToClassList("w27-td"); hr.Add(l); }
            string[] rowNames = { "Жители, тыс.", "Рабочие места, тыс.", "ВРП, трлн ₸", "Энергосеть, загрузка", "Водопровод, загрузка" };
            for (int r = 0; r < 5; r++)
            {
                var tr = new VisualElement(); tr.AddToClassList("w27-tr"); t.Add(tr);
                var l = new Label(rowNames[r]); l.AddToClassList("w27-td-l"); tr.Add(l);
                for (int c = 0; c < 3; c++)
                {
                    var cell = new VisualElement(); cell.AddToClassList("w27-td"); tr.Add(cell);
                    cellA[r, c] = new Label("—"); cellA[r, c].AddToClassList("w27-a"); cell.Add(cellA[r, c]);
                    cellB[r, c] = new Label("—"); cellB[r, c].AddToClassList("w27-b"); cell.Add(cellB[r, c]);
                }
            }
            tableNote = new Label(); tableNote.AddToClassList("w27-meta"); tableNote.style.marginTop = 6; blk.Add(tableNote);

            var det = Widgets.Details(blk, "Допущения");
            var r0 = ForecastModel.Runs[0]; int y50 = ForecastModel.NY - 1;
            Glance.Prose(det, ForecastModel.Ready
                ? string.Format("Стартовые точки — базовый сценарий QTwin по генплану: {0} млн жителей вместе с сёлами и {1} млн рабочих мест к 2050 году.", Loc.N1(r0.Residents[y50] / 1e6f), Loc.N1(r0.Jobs[y50] / 1e6f))
                : "Стартовые точки — базовый сценарий QTwin по генплану.");
            Glance.Prose(det, "Темп ввода жилья 120 % — жильё сдают в 1,2 раза быстрее графика; 80 % — медленнее, часть не успевает к 2050.");
            Glance.Prose(det, "Миграция 100 % — 30 м² жилья на жителя; 120 % — в то же жильё заселяется на 20 % больше людей.");
            Glance.Prose(det, string.Format("Доля промышленности — доля заводов и логистики в рабочих местах 2050 года (по генплану ≈{0} %). Завод даёт больше ВРП и нагрузки на сеть, чем офис.", ForecastModel.IndustryBase));
            Glance.Prose(det, "Темп ввода сетей — график подстанций и водозаборов сжимается или растягивается во времени.");
            Glance.Prose(det, "Спрос: жильё 10 Вт/м², офисы 12, соцобъекты 15, промышленность 30; вода — 230 л в сутки на жителя. ВРП — без стройки, в ценах 2026 года, +2 % в год.");
            Glance.Prose(det, "Загрузка сети — спрос, делённый на введённую мощность; выше 100 % — дефицит. Всё это модель QTwin, не прогноз госорганов.");
            blk.Add(SourceTags.Line(ForecastModel.ModelId, TwinModels.Loads, Sources.ModelCity, Sources.GenPlan));
        }

        Sl Slider(VisualElement parent, string name, int min, int max, int start, string sub, System.Action<int> set)
        {
            var s = new Sl { Name = name, Min = min, Max = max };
            var top = new VisualElement(); top.AddToClassList("w27-sl-top"); parent.Add(top);
            var n = new Label(name); n.AddToClassList("w27-sl-n"); top.Add(n);
            s.V = new Label(); s.V.AddToClassList("w27-sl-v"); top.Add(s.V);
            s.S = new TwinSlider(new[] { start }, _ => "план", min, max); s.S.AddToClassList("w27-slider"); parent.Add(s.S);
            var l = new Label(sub); l.AddToClassList("w27-sl-sub"); parent.Add(l);
            s.S.OnChange = v => { set(v); if (b != ForecastModel.Custom && a != ForecastModel.Custom) b = ForecastModel.Custom; ForecastModel.Compute(ForecastModel.Custom); Update(); };
            return s;
        }

        void SyncSliders()
        {
            if (sl[0] == null) return;
            sl[0].S.Value = ForecastModel.Housing; sl[1].S.Value = ForecastModel.Migration; sl[2].S.Value = ForecastModel.Industry; sl[3].S.Value = ForecastModel.Nets;
        }

        /// <summary>Called by the module (year change, data ready) and by the controls.</summary>
        public void Update()
        {
            if (!built || hero == null || !ForecastModel.Ensure()) return;
            SyncSliders();
            int[] vals = { ForecastModel.Housing, ForecastModel.Migration, ForecastModel.Industry, ForecastModel.Nets };
            for (int i = 0; i < 4; i++) sl[i].V.text = vals[i] + " %";
            bool atStart = ForecastModel.AtStart;
            reset.SetEnabled(!atStart); resetHint.text = atStart ? "Сдвиньте ползунок — B станет «Свой»" : "";
            for (int k = 0; k < 2; k++) for (int i = 0; i < pick[k].Length; i++) pick[k][i].EnableInClassList("active", i == (k == 0 ? a : b));
            for (int i = 0; i < chartChips.Length; i++) chartChips[i].EnableInClassList("active", i == chartK);

            var A = ForecastModel.Runs[a]; var B = ForecastModel.Runs[b];
            // the answer: when the power network first falls short, A → B
            int fa = A.First[0], fb = B.First[0];
            string ya = fa < 0 ? "2050+" : fa.ToString(), yb = fb < 0 ? "2050+" : fb.ToString();
            string where = fb >= 0 ? Where(B.Where[0]) : fa >= 0 ? Where(A.Where[0]) : "";
            string st = fa == fb ? (fb < 0 ? "ok" : "warn") : (fb < 0 || (fa >= 0 && fb > fa)) ? "ok" : "bad";
            string cap = a == b ? "Выберите разные A и B" : where != "" ? string.Format("Первый дефицит энергии · {0}", where) : "Дефицита энергии нет до 2050";
            int wa = A.First[1], wb = B.First[1];
            string line = wa < 0 && wb < 0 ? "Воды хватает в обоих сценариях" : string.Format("Вода: {0} → {1}", wa < 0 ? "2050+" : wa.ToString(), wb < 0 ? "2050+" : wb.ToString());
            hero.Set(fa == fb ? yb : string.Format("{0} → {1}", ya, yb), "", cap, st, line);

            // chart: two lines (A white, B blue); networks as load %, with the 100 % line = capacity
            int yi50 = ForecastModel.NY - 1;
            legend.Clear();
            switch (chartK)
            {
                case 0: Pair(A.Residents, B.Residents, 0.001f); chartTitle.text = "Жители, тыс."; break;
                case 1: Pair(A.Jobs, B.Jobs, 0.001f); chartTitle.text = "Рабочие места, тыс."; break;
                case 2: Pair(A.Grp, B.Grp, 0.001f); chartTitle.text = "ВРП в год, трлн ₸"; break;
                default:
                {
                    // networks: demand of A and B against the capacity of B (steps); a deficit year of B is marked red
                    int k = chartK - 3; float sc = k == 0 ? 1f : 0.001f; Pair(A.D[k], B.D[k], sc);
                    chartTitle.text = k == 0 ? "Электричество: спрос и мощность, МВт" : "Вода: спрос и мощность, тыс.\u00A0м³/сут"; break;
                }
            }
            bool net = chartK >= 3, anyDef = false;
            if (net) { int k = chartK - 3; float sc = k == 0 ? 1f : 0.001f; for (int i = 0; i < capLine.Length; i++) { capLine[i] = B.C[k][i] * sc; alerts[i] = B.Def[k][i] > 0.5f; anyDef |= alerts[i] && i > 0; } }
            chart.Series = net ? ser : new[] { ser[0], ser[1] };
            if (net) ser[2] = capLine;
            chart.Colors = Cols; chart.LineWidths = Widths;
            chart.Stacked = false; chart.Bars = false; chart.StepLast = net; chart.Alerts = net ? alerts : null; chart.MarkYear = TwinState.Year; chart.Refresh();
            legend.Add(Widgets.LegendItem(ColA, string.Format("A · {0}", SlotNames[a]))); legend.Add(Widgets.LegendItem(ColB, string.Format("B · {0}", SlotNames[b])));
            if (net) legend.Add(Widgets.LegendItem(ColCap, "мощность в B"));
            if (anyDef) legend.Add(Widgets.LegendItem(new Color(1f, 0.23f, 0.18f), "дефицит в B"));

            // table
            for (int c = 0; c < 3; c++)
            {
                int yi = Mathf.Clamp(Years[c] - ForecastModel.Y0, 0, yi50);
                Cell(0, c, A.Residents[yi] / 1000f, B.Residents[yi] / 1000f, false);
                Cell(1, c, A.Jobs[yi] / 1000f, B.Jobs[yi] / 1000f, false);
                Cell(2, c, A.Grp[yi] / 1000f, B.Grp[yi] / 1000f, false, true);
                Cell(3, c, A.Load[0][yi], B.Load[0][yi], true);
                Cell(4, c, A.Load[1][yi], B.Load[1][yi], true);
            }
            tableNote.text = "Верхняя строка — A, нижняя — B";
        }

        void Pair(float[] x, float[] y, float k)
        {
            int n = ForecastModel.NY;
            if (ser[0] == null || ser[0].Length != n) { ser[0] = new float[n]; ser[1] = new float[n]; ser[2] = capLine; }
            for (int i = 0; i < n; i++) { ser[0][i] = x[i] * k; ser[1][i] = y[i] * k; }
        }

        void Cell(int r, int c, float va, float vb, bool load, bool oneDecimal = false)
        {
            string Fmt(float v) => load ? (v <= 0 ? "—" : Mathf.RoundToInt(v) + " %") : oneDecimal ? Loc.N1(v) : Loc.N0(v);
            cellA[r, c].text = Fmt(va); cellB[r, c].text = Fmt(vb);
            string st = "";
            if (load) st = vb > 100.5f ? "bad" : vb > 85f ? "warn" : "";
            else if (va > 0) { float d = vb / va - 1f; st = d > 0.03f ? "ok" : d < -0.03f ? "warn" : ""; }
            for (int i = 0; i < 3; i++) cellB[r, c].EnableInClassList(StCls[i], St[i] == st);
        }

        static readonly string[] St = { "ok", "warn", "bad" }, StCls = { "w27-ok", "w27-warn", "w27-bad" };
        static readonly Color[] Cols = { ColA, ColB, ColCap }; static readonly float[] Widths = { 1.6f, 2.6f, 1.5f };
        static string Where(int d) => d >= 0 && d < 4 ? CityStats.DistrictIds[d] : "весь город";
    }
}
