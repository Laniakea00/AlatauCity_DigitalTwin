using System;
using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin.Ai
{
    /// <summary>Thin read-only adapter over the construction monitoring of Iconic Complex and KAIST for the AI assistant. It repeats the
    /// public schedule model of IconicMonitor (plan dates A…B of every building, the delay at the survey that builds up during the works and
    /// is closed after the survey when Recover is set) from the landmark data, without opening the monitoring window. The survey date is
    /// the one the monitoring shows first: the middle of the works. Money spent = budget × actual readiness of each building (estimate).
    /// Used for the per-building rows and as the fallback (an estimate) when IconicMonitor.Summary(id) returns Ok = false.</summary>
    public static class AiMonitor
    {
        public class PartRow { public string Name; public float PlanEnd, FactEnd, Capex; public int DelayDays; public float PlanReady, FactReady; public string Risk; }
        public class Summary
        {
            public Landmark L; public float Survey, PlanEnd, FactEnd, Budget, Spent, PlanSpent; public int EndDays;
            public PartRow Worst; public readonly List<PartRow> Parts = new List<PartRow>();
        }

        public static Landmark Find(string id)
        {
            var ls = LandmarkSystem.Instance;
            if (ls != null) { var l = ls.Get(id); if (l != null) return l; }
            foreach (var l in LandmarkCatalog.All()) if (l.Id == id) return l;
            return null;
        }

        public static Summary Of(string id)
        {
            var L = Find(id); if (L == null || L.Parts == null || L.Parts.Count == 0) return null;
            float report = L.Begin + 0.5f * (L.Finish - L.Begin), t0 = Mathf.Floor(L.Begin), t1 = Mathf.Max(Mathf.Ceil(L.Finish + 0.05f), L.EndYear + 1f);
            float DelayAt(LPart p, float d)
            {
                if (Mathf.Abs(p.Delay) < 1e-5f) return 0f;
                float up = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((d - (p.A + 0.1f)) / 0.9f));
                float down = d <= report || !p.Recover ? 1f : Mathf.Clamp01(1f - (d - report) / 1.4f);
                return p.Delay * up * down;
            }
            float PlanP(LPart p, float d) => d <= p.A ? 0f : Mathf.Clamp01((d - p.A) / Mathf.Max(p.B - p.A, 0.01f));
            float FactP(LPart p, float d) => PlanP(p, d - DelayAt(p, d));
            float FactDate(LPart p)
            {
                float a = t0 - 2f, b = t1 + 3f;
                for (int k = 0; k < 30; k++) { float m = (a + b) * 0.5f; if (FactP(p, m) >= 1f) b = m; else a = m; }
                return b;
            }
            var s = new Summary { L = L, Survey = report, PlanEnd = L.Finish };
            float worstV = -1f;
            foreach (var p in L.Parts)
            {
                var r = new PartRow { Name = p.Name, PlanEnd = p.B, FactEnd = FactDate(p), Capex = p.Capex, DelayDays = Mathf.RoundToInt(DelayAt(p, report) * 365f),
                                      PlanReady = PlanP(p, report), FactReady = FactP(p, report), Risk = p.Risk };
                s.Parts.Add(r); s.Budget += p.Capex; s.Spent += p.Capex * r.FactReady; s.PlanSpent += p.Capex * r.PlanReady;
                s.FactEnd = Mathf.Max(s.FactEnd, r.FactEnd);
                float v = DelayAt(p, report) * p.Capex; if (v > worstV) { worstV = v; s.Worst = r; }
            }
            s.EndDays = Mathf.RoundToInt((s.FactEnd - s.PlanEnd) * 365f);
            return s;
        }

        /// <summary>dd.MM.yyyy of a fractional year (as the monitoring writes dates).</summary>
        public static string Day(float y) { var t = new DateTime(Mathf.FloorToInt(y), 1, 1).AddDays((y - Mathf.Floor(y)) * 365f); return t.ToString("dd.MM.yyyy"); }
    }
}
