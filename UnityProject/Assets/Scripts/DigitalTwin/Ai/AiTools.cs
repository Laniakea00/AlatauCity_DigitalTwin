using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;
using AlatauCity.DigitalTwin.UI;
using O = System.Collections.Generic.Dictionary<string, object>;
using AiModule = AlatauCity.DigitalTwin.Modules.AiModule;

namespace AlatauCity.DigitalTwin.Ai
{
    /// <summary>The functions the language model may call, run by the twin on its own data. Each result is a small JSON object with
    /// "kind" (open_data / model) and "sources" (ids of Data/Sources); the effects on the map (camera, layers, year, tab) are not run
    /// at once but collected in the turn and applied when the answer is shown (and again on «Показать»).
    /// The test stand-in UnityProject/Tools/ai_proxy/test/twin_stub.js mirrors these shapes.</summary>
    public static class AiTools
    {
        public static readonly string[] Names = { "fly_to", "open_module", "show_layer", "get_city_stats", "get_project", "get_monitoring", "get_sources", "analyze" };
        static readonly string[] Dn = { "Gate", "Golden", "Growing", "Green" };
        static readonly Dictionary<string, string> Modules = new Dictionary<string, string>
        {
            { "overview", "Обзор" }, { "objects", "Объекты" }, { "economy", "Экономика" }, { "infra", "Инфраструктура" }, { "monitoring", "Мониторинг стройки" },
            { "prediction", "Прогноз" }, { "situation", "Ситуационный центр" }, { "smartcity", "Smart City" }, { "construction", "Стройка" },
        };
        static readonly Dictionary<string, string> Layers = new Dictionary<string, string>
        {
            { "traffic", "загрузка дорог в утренний час пик" }, { "roadworks", "дорожные работы" }, { "water", "водопровод" }, { "sewer", "канализация" },
            { "power", "электросети" }, { "heat", "теплосети" }, { "gas", "газопровод" }, { "telecom", "связь" },
        };
        static readonly Dictionary<string, string> CountryAlias = new Dictionary<string, string>
        {
            { "kuwait", "кувейт" }, { "korea", "корея" }, { "south korea", "корея" }, { "кәрея", "корея" }, { "оңтүстік корея", "корея" },
            { "usa", "сша" }, { "us", "сша" }, { "united states", "сша" }, { "america", "сша" }, { "ақш", "сша" },
            { "china", "китай" }, { "қытай", "китай" }, { "germany", "германия" }, { "kazakhstan", "казахстан" }, { "қазақстан", "казахстан" },
        };

        /// <summary>What one answer did: the calls (for the "tools" list), the sources to tag, the effects to apply on the map.</summary>
        public class Turn
        {
            public readonly List<string> Calls = new List<string>();
            public readonly List<string> Src = new List<string>();
            public readonly List<Action> Apply = new List<Action>();
            public bool Flew; public Action FallbackFly;
            /// <summary>The last analysis the model asked for (its facts and chart go under the answer); the tab it offered (a button, not a switch).</summary>
            public AiModule.Answer Analysis; public string OpenTab, OpenTabTitle;
            public void AddSrc(string id) { if (!string.IsNullOrEmpty(id) && !Src.Contains(id)) Src.Add(id); }
            /// <summary>All effects in order; the camera goes to the object of a data function only if the model did not fly itself.</summary>
            public Action Combined()
            {
                var list = Apply.ToList(); if (!Flew && FallbackFly != null) list.Add(FallbackFly);
                if (list.Count == 0) return null;
                return () => { foreach (var a in list) { try { a(); } catch (Exception e) { Debug.LogWarning("[Alatau] AI action: " + e.Message); } } };
            }
        }

        public static O Run(string name, Dictionary<string, object> args, Turn t)
        {
            args ??= new Dictionary<string, object>();
            t.Calls.Add(name + "(" + string.Join(", ", args.Select(kv => kv.Value is string s ? "\"" + s + "\"" : Convert.ToString(kv.Value, System.Globalization.CultureInfo.InvariantCulture))) + ")");
            O r;
            try
            {
                switch (name)
                {
                    case "fly_to": r = FlyTo(Str(args, "target"), t); break;
                    case "open_module": r = OpenModule(Str(args, "id"), t); break;
                    case "show_layer": r = ShowLayer(Str(args, "id"), t); break;
                    case "get_city_stats": r = CityStatsOf(Str(args, "district"), Int(args, "year"), t); break;
                    case "get_project": r = Project(Str(args, "query"), Str(args, "country")); break;
                    case "get_monitoring": r = Monitoring(Str(args, "landmark"), t); break;
                    case "get_sources": r = SourcesOf(Str(args, "topic")); break;
                    case "analyze": r = Analyze(Str(args, "topic"), Int(args, "year"), Int(args, "phase"), t); break;
                    default: r = AiJson.O("ok", false, "error", "unknown function"); break;
                }
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] AI tool " + name + ": " + e.Message); r = AiJson.O("ok", false, "error", "no data in the twin"); }
            if (r.TryGetValue("sources", out var src) && src is List<object> ids && ids.Count > 0)
            {
                // the titles go to the model too, so it can name a source without guessing from its id
                var titles = new List<object>();
                foreach (var id in ids)
                {
                    t.AddSrc(id as string); var s = Sources.Get(id as string); if (s == null) continue;
                    titles.Add(s.Model ? s.Title + " (model QTwin)" : s.Publisher + (string.IsNullOrEmpty(s.Date) ? "" : " · " + s.Date) + " · " + s.Title);
                }
                r["source_titles"] = titles;
            }
            return r;
        }

        static string Str(Dictionary<string, object> a, string k) => a.TryGetValue(k, out var v) && v != null ? Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture) : "";
        static int Int(Dictionary<string, object> a, string k) => a.TryGetValue(k, out var v) && v is double d ? (int)Math.Round(d) : a.TryGetValue(k, out var s) && s is string ss && int.TryParse(ss, out var i) ? i : 0;
        static string Norm(string s) => (s ?? "").ToLowerInvariant().Replace('ё', 'е').Trim();
        static List<string> Tokens(string q) => q.Split(new[] { ' ', ',', '.', '-', '«', '»', '"', '(', ')', '/', '?', '!' }, StringSplitOptions.RemoveEmptyEntries)
                                                 .Where(x => x.Length >= 3).Select(x => x.Length > 5 ? x.Substring(0, 5) : x).ToList();
        static bool Hit(string hay, string q, List<string> toks) => q.Length > 0 && (hay.Contains(q) || toks.Any(hay.Contains));
        static int District(string d) { d = Norm(d); for (int i = 0; i < 4; i++) if (Norm(Dn[i]) == d) return i; return -1; }

        // ------------------------------------------------------------------ map
        static void Fly(Landmark l) { var ls = LandmarkSystem.Instance; if (ls != null && l != null) ls.FlyTo(l); }

        static Landmark FindLandmark(string t)
        {
            var all = LandmarkSystem.Instance != null && LandmarkSystem.Instance.Items.Count > 0 ? LandmarkSystem.Instance.Items : LandmarkCatalog.All();
            return all.FirstOrDefault(l => l.Id == t)
                ?? all.FirstOrDefault(l => Norm(l.Name) == t || Norm(l.Short) == t)
                ?? (t.Length >= 3 ? all.FirstOrDefault(l => Norm(l.Name).Contains(t) || Norm(l.Short).Contains(t) || t.Contains(Norm(l.Short))) : null);
        }

        static O FlyTo(string target, Turn t)
        {
            var q = Norm(target);
            int d = District(q);
            if (d >= 0) { t.Flew = true; t.Apply.Add(() => TwinUI.Instance?.GoToDistrict(d)); return AiJson.O("ok", true, "shown", Dn[d], "type", "district"); }
            if (q == "city" || q == "город" || q == "весь город" || q == "қала")
            { t.Flew = true; t.Apply.Add(() => TwinUI.Instance?.GoToDistrict(-1)); return AiJson.O("ok", true, "shown", "Alatau City", "type", "city"); }
            var l = FindLandmark(q);
            if (l == null)
            {
                InvestRegistry.Init();
                var p = InvestRegistry.Projects.FirstOrDefault(x => x.Landmark != null && (Norm(x.Name).Contains(q) || Norm(x.Investor).Contains(q)));
                if (p != null) l = FindLandmark(p.Landmark);
            }
            if (l == null) return AiJson.O("ok", false, "error", "not on the map", "known", LandmarkCatalog.All().Select(x => (object)x.Id).ToList());
            t.Flew = true; var lm = l; t.Apply.Add(() => Fly(lm));
            return AiJson.O("ok", true, "shown", l.Name, "type", "landmark", "district", l.District >= 0 && l.District < 4 ? Dn[l.District] : null);
        }

        static O OpenModule(string id, Turn t)
        {
            if (!Modules.TryGetValue(id, out var title)) return AiJson.O("ok", false, "error", "unknown module");
            // not switched at once (the answer would disappear with the AI tab): the card shows a button that opens the tab
            t.OpenTab = id; t.OpenTabTitle = title;
            return AiJson.O("ok", true, "offered", title, "note", "The tab is NOT opened automatically: a button «open the tab» is shown under the answer.");
        }

        static O ShowLayer(string id, Turn t)
        {
            if (!Layers.TryGetValue(id, out var what)) return AiJson.O("ok", false, "error", "unknown layer");
            t.Apply.Add(() => LineLayers.Instance?.Show(id, true));
            return AiJson.O("ok", true, "shown", what);
        }

        // ------------------------------------------------------------------ data
        /// <summary>The twin's own computed analyses (AiModule.Analysis — the same computation as the scripted answers): numbers and names
        /// for the model, and the scripted map action (tint, pins, camera, legend) and chart for the card.</summary>
        static O Analyze(string topic, int year, int phase, Turn t)
        {
            topic = Norm(topic);
            if (Array.IndexOf(AiModule.Topics, topic) < 0)
                return AiJson.O("kind", "model", "error", "unknown topic", "topics", AiModule.Topics.Select(x => (object)x).ToList(), "sources", AiJson.A());
            var a = AiModule.Analysis(topic, year, phase > 0 ? phase : 1);
            if (a == null || a.Data == null) return AiJson.O("kind", "model", "error", "twin data not loaded", "sources", AiJson.A());
            t.Analysis = a;
            if (a.Apply != null) { t.Apply.Add(a.Apply); t.Flew = true; }
            var r = new O(a.Data);
            r["sources"] = (a.Src ?? new string[0]).Select(x => (object)x).ToList();
            return r;
        }

        static O CityStatsOf(string district, int year, Turn t)
        {
            int y = Mathf.Clamp(year > 0 ? year : TwinState.Year, TwinState.MinYear, TwinState.MaxYear), s = (int)TwinState.Scenario, d = District(district);
            if (!TwinData.Ready) return AiJson.O("kind", "model", "error", "twin data not loaded", "sources", AiJson.A());
            float area = 0; for (int i = 0; i < 4; i++) if (d < 0 || i == d) area += CityStats.DistrictAreaHa[i];
            var r = AiJson.O("kind", "model", "scope", d >= 0 ? Dn[d] : "city", "year", y, "scenario", TwinScenario.Name(TwinState.Scenario),
                "residents", Mathf.RoundToInt(TwinData.Load(s, "res", d, y)), "jobs", Mathf.RoundToInt(TwinData.Load(s, "jobs", d, y)),
                "buildings", CityStats.Ready ? (object)CityStats.Count(d, y) : null,
                "area_ha", Mathf.RoundToInt(area), "area_kind", "open_data (master plan)",
                "note", "Twin scenario of the master-plan build-out: residents = housing floor area / 30 m² per person. Not official statistics.",
                "sources", AiJson.A(Sources.ModelCity, Sources.GenPlan));
            if (d < 0) r["by_district"] = Enumerable.Range(0, 4).Select(i => (object)AiJson.O("district", Dn[i], "residents", Mathf.RoundToInt(TwinData.Load(s, "res", i, y)))).ToList();
            if (year > 0) t.Apply.Add(() => TwinState.Year = y);
            if (d >= 0) t.FallbackFly ??= () => TwinUI.Instance?.GoToDistrict(d);
            return r;
        }

        static O Row(InvestRegistry.Project p)
        {
            const string nd = "не раскрыто";
            return AiJson.O("name", p.Name, "investor", p.Investor, "country", p.Country ?? nd, "sector", InvestRegistry.Sectors[Mathf.Clamp(p.Sector, 0, InvestRegistry.Sectors.Length - 1)],
                "status", InvestRegistry.StatusNames[p.Status], "status_meaning", InvestRegistry.StatusHint[p.Status],
                "amount_usd_m", p.UsdM > 0 ? (object)(Mathf.Round(p.UsdM * 10f) / 10f) : nd, "amount_note", p.AmountNote,
                "jobs", p.Jobs > 0 ? (object)p.Jobs : nd, "years", p.Years ?? nd, "district", p.District >= 0 && p.District < 4 ? Dn[p.District] : "не указан",
                "on_map", p.Landmark != null, "note", p.Note, "sources", new List<object> { p.Src, p.Src2 }.Where(x => x != null).ToList());
        }

        static O Project(string query, string country)
        {
            InvestRegistry.Init();
            string q = Norm(query), c = Norm(country); if (CountryAlias.TryGetValue(c, out var ca)) c = ca;
            var toks = Tokens(q);
            bool ByCountry(InvestRegistry.Project p) => c.Length == 0 || Norm(p.Country).Contains(c) || Norm(p.Investor).Contains(c) || Norm(p.Note).Contains(c);
            string Hay(InvestRegistry.Project p) => Norm(string.Join(" ", p.Name, p.Investor, p.Country, InvestRegistry.Sectors[Mathf.Clamp(p.Sector, 0, InvestRegistry.Sectors.Length - 1)], p.Landmark));
            // names, investors, countries and sectors first; the free-text notes only when nothing else matches
            var found = InvestRegistry.Projects.Where(p => ByCountry(p) && (q.Length == 0 || Hit(Hay(p), q, toks))).ToList();
            var infra = q.Length == 0 ? new List<object>() : InvestRegistry.Infra.Where(i => Hit(Norm(string.Join(" ", i.Name, i.Kind, i.What)), q, toks)).Take(5)
                .Select(i => (object)AiJson.O("name", i.Name, "kind", i.Kind, "what", i.What, "when", i.When, "status", i.Status, "amount", i.Amount ?? "не раскрыто", "sources", AiJson.A(i.Src))).ToList();
            if (found.Count == 0 && infra.Count == 0 && q.Length > 0) found = InvestRegistry.Projects.Where(p => ByCountry(p) && Hit(Norm(p.Note), q, toks)).ToList();
            var rows = found.Take(8).Select(p => (object)Row(p)).ToList();
            var ids = new List<object>();
            foreach (var x in rows.Concat(infra)) foreach (var s in (List<object>)((O)x)["sources"]) if (!ids.Contains(s)) ids.Add(s);
            if ((rows.Count > 0 || q.Length == 0) && !ids.Contains(Sources.GovSummary)) ids.Add(Sources.GovSummary);
            return AiJson.O("kind", "open_data", "registry_size", InvestRegistry.Projects.Count, "found", rows.Count, "projects", rows, "infrastructure", infra,
                "government_summary", "Government summary 26.08.2026: 67 investment projects ≈ $6.9 bn, ≈ 55 000 jobs, 26 infrastructure projects (the registry lists the ones named in the press).",
                "note", rows.Count + infra.Count == 0 ? "Nothing in the registry matches." : "Amounts and jobs as published; \"не раскрыто\" = not disclosed in the press.",
                "sources", ids);
        }

        /// <summary>The monitoring of Iconic / KAIST: the exact figures of the monitoring window (IconicMonitor.Summary, its last survey);
        /// when it cannot be computed (the window is open on another object, the landmarks are not built yet) the AiMonitor adapter gives
        /// an estimate, marked as such. Per-building rows always come from the adapter (same schedule formula as the window).</summary>
        static O Monitoring(string id, Turn t)
        {
            IconicMonitor.RegisterSources();
            id = Norm(id);
            var m = AiMonitor.Of(id);
            if (m == null) return AiJson.O("kind", "model", "error", "no monitoring for this object", "available", AiJson.A("iconic", "kaist"), "sources", AiJson.A());
            var L = m.L;
            var parts = m.Parts.Select(p => (object)AiJson.O("name", p.Name, "plan_handover", AiMonitor.Day(p.PlanEnd), "forecast_handover", AiMonitor.Day(p.FactEnd),
                "delay_days_at_survey", p.DelayDays, "plan_ready_pct", Mathf.RoundToInt(p.PlanReady * 100f), "fact_ready_pct", Mathf.RoundToInt(p.FactReady * 100f), "budget_usd_m", Mathf.RoundToInt(p.Capex))).ToList();
            t.FallbackFly ??= () => Fly(L);
            var today = AiJson.O("date", "27.10.2026", "status", L.StatusNote, "kind", "open_data", "publishers", L.Source, "published", L.SourceDate);
            var src = AiJson.A(IconicMonitor.SrcMon, IconicMonitor.SrcEv, IconicMonitor.SrcActs, IconicMonitor.SrcDefects, IconicMonitor.SrcDocs);
            var x = IconicMonitor.Summary(id);
            if (x.Ok)
            {
                return AiJson.O("kind", "model", "object", x.Name ?? L.Name, "figures", "exact figures of the monitoring window", "today", today,
                    "survey_date", x.SurveyDate,
                    "survey_note", "Simulated drone survey on " + x.SurveyDate + ", in the middle of the works and in the future relative to today (27.10.2026). Everything at that date is a twin scenario, not developer data.",
                    "on_track_answer", x.OnTrack, "spending_answer", x.Spending, "todo_answer", x.ToDo,
                    "readiness_pct", Mathf.RoundToInt(x.Readiness * 100f), "plan_readiness_pct", Mathf.RoundToInt(x.PlanReadiness * 100f),
                    "behind_schedule_days", x.DelayDays, "handover_shift_days", x.HandoverShiftDays, "plan_handover", x.PlanHandover, "forecast_handover", x.ForecastHandover,
                    "spi", Mathf.Round(x.Spi * 100f) / 100f, "cpi", Mathf.Round(x.Cpi * 100f) / 100f,
                    "spi_cpi_meaning", "SPI: pace of work against the schedule (1 = on schedule); CPI: value of work per dollar spent (1 = on budget)",
                    "budget_usd_m", Mathf.RoundToInt(x.BudgetMln), "reserve_usd_m", Mathf.RoundToInt(x.ReserveMln), "spent_usd_m", Mathf.RoundToInt(x.SpentMln),
                    "planned_value_usd_m", Mathf.RoundToInt(x.PlannedMln), "earned_value_usd_m", Mathf.RoundToInt(x.EarnedMln), "forecast_at_completion_usd_m", Mathf.RoundToInt(x.EacMln),
                    "top_action", x.TopAction, "top_action_effect_days", x.TopActionDays, "actions", x.Actions?.Select(a => (object)a).ToList(),
                    "open_defects", x.OpenDefects, "critical_defects", x.CriticalDefects,
                    "documents_waiting", x.DocsWaiting, "documents_overdue", x.DocsOverdue, "overdue_documents", x.OverdueDocs?.Select(a => (object)a).ToList(),
                    "parts", parts, "parts_note", "per-building schedule rows of the same scenario",
                    "sources", src);
            }
            return AiJson.O("kind", "model", "object", L.Name,
                "figures", "ESTIMATE: the monitoring model could not be computed now; these figures are an approximation and may differ from the monitoring window — say they are an estimate",
                "today", today,
                "survey_date", AiMonitor.Day(m.Survey),
                "survey_note", "Simulated drone survey on " + AiMonitor.Day(m.Survey) + ", in the middle of the works and in the future relative to today (27.10.2026). Delays, readiness, forecast and money at that date are a twin scenario, not developer data.",
                "plan_handover", AiMonitor.Day(m.PlanEnd), "forecast_handover", AiMonitor.Day(m.FactEnd), "forecast_vs_plan_days", m.EndDays,
                "budget_usd_m", Mathf.RoundToInt(m.Budget), "spent_usd_m_estimate", Mathf.RoundToInt(m.Spent), "planned_spent_usd_m_estimate", Mathf.RoundToInt(m.PlanSpent),
                "spent_method", "estimate: budget × actual readiness of each building",
                "main_risk", m.Worst == null ? null : AiJson.O("building", m.Worst.Name, "delay_days", m.Worst.DelayDays, "risk_and_action", m.Worst.Risk),
                "parts", parts, "sources", src);
        }

        /// <summary>Topic words in RU/EN/KZ → the stem the source notes are written with.</summary>
        static readonly (string[] keys, string stem)[] TopicSyn =
        {
            (new[] { "насел", "жител", "халық", "тұрғын", "popul", "resident", "people" }, "жител"), (new[] { "invest", "инвест" }, "инвест"),
            (new[] { "monitor", "монитор" }, "монитор"), (new[] { "стройк", "құрылыс", "construct" }, "стройк"),
            (new[] { "электр", "power", "electric", "energy", "энерг" }, "электр"), (new[] { "tax", "налог", "салық", "regime", "режим" }, "налог"),
            (new[] { "сет", "network", "grid", "желі" }, "сет"), (new[] { "traffic", "трафик", "пробк", "затор", "транспорт" }, "транспорт"),
        };

        static O SourcesOf(string topic)
        {
            InvestRegistry.Init(); IconicMonitor.RegisterSources();
            string q = Norm(topic);
            foreach (var (keys, stem) in TopicSyn) if (keys.Any(q.Contains)) { q = stem; break; }
            var toks = Tokens(q);
            // titles first, the notes only when no title matches
            var list = Sources.All.Where(s => Hit(Norm(s.Title + " " + s.Publisher), q, toks)).Take(8).ToList();
            if (list.Count == 0) list = Sources.All.Where(s => Hit(Norm(s.Note), q, toks)).Take(8).ToList();
            return AiJson.O("kind", "open_data", "found", list.Count,
                "sources_list", list.Select(s => (object)AiJson.O("title", s.Title, "publisher", s.Publisher, "date", string.IsNullOrEmpty(s.Date) ? null : s.Date, "url", s.Url, "model", s.Model)).ToList(),
                "sources", list.Select(s => (object)s.Id).ToList());
        }
    }
}
