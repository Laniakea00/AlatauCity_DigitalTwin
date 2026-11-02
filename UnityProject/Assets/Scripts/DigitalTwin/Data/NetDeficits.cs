using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>One reading of the network deficits for every panel that speaks of them (Инфраструктура, Обзор: аналитика and the
    /// journal): the twin balance of loads.json (a deficit = demand above capacity, more than 0.5 of the unit), found where the network
    /// is — in the district that has a balance of its own, in the city for a pooled network — as spells of consecutive years from 2026,
    /// each with its first-year and peak amounts. Every sentence takes its numbers from here and formats them with InvestRegistry.Fmt,
    /// so the panels say the same number and the same conclusion.</summary>
    public static class NetDeficits
    {
        /// <summary>A run of deficit years of one resource in one place (District −1 = the city's pooled network).</summary>
        public struct Spell { public int Res, District, From, To, PeakYear; public float First, Peak; }

        /// <summary>Resources in the order the panels read them: balance key, name (Loc key), name in «Не хватает: …», unit.</summary>
        public static readonly (string key, string name, string gen, string unit)[] Res =
        {
            ("power_hv", "res_power_hv", "электроэнергии, 220 кВ", "МВт"), ("power", "res_power", "электроэнергии, 110 кВ", "МВт"),
            ("heat", "res_heat", "тепла", "Гкал/ч"), ("gas", "res_gas", "газа", "тыс. м³/ч"),
            ("water", "res_water", "воды", "тыс. м³/сут"), ("sewer", "res_sewer", "канализации", "тыс. м³/сут")
        };
        public const float Min = 0.5f;
        public const int FirstYear = 2026;

        static readonly Dictionary<int, List<Spell>> cache = new Dictionary<int, List<Spell>>();
        static string cacheFor;

        /// <summary>The spells of scenario s seen from district d: its own networks and the pooled ones (−1 = the whole city: every
        /// district and the pooled networks), ordered by the first year, then by resource.</summary>
        public static List<Spell> Spells(int s, int d)
        {
            if (cacheFor != TwinData.Version) { cache.Clear(); cacheFor = TwinData.Version; }
            int key = s * 8 + d + 1;
            if (cache.TryGetValue(key, out var have)) return have;
            var list = new List<Spell>();
            if (TwinData.Ready)
                for (int r = 0; r < Res.Length; r++)
                {
                    bool own = TwinData.BalanceOf(s, Res[r].key, 0) != null;
                    if (!own) { Scan(s, r, -1, list); continue; }
                    for (int k = 0; k < 4; k++) if (d < 0 || k == d) Scan(s, r, k, list);
                }
            list.Sort((a, b) => a.From != b.From ? a.From.CompareTo(b.From) : a.Res != b.Res ? a.Res.CompareTo(b.Res) : a.District.CompareTo(b.District));
            cache[key] = list; return list;
        }
        static void Scan(int s, int r, int k, List<Spell> into)
        {
            var b = TwinData.BalanceOf(s, Res[r].key, k); if (b == null || b.Deficit == null) return;
            Spell cur = default; bool on = false;
            for (int y = FirstYear; y <= TwinState.MaxYear; y++)
            {
                float v = b.Deficit[TwinData.YI(y)];
                if (v > Min)
                {
                    if (!on) { cur = new Spell { Res = r, District = k, From = y, To = y, First = v, Peak = v, PeakYear = y }; on = true; }
                    else { cur.To = y; if (v > cur.Peak) { cur.Peak = v; cur.PeakYear = y; } }
                }
                else if (on) { into.Add(cur); on = false; }
            }
            if (on) into.Add(cur);
        }

        /// <summary>The deficit of a spell's network in year y (0 outside the spell).</summary>
        public static float At(int s, Spell sp, int y)
        {
            var b = TwinData.BalanceOf(s, Res[sp.Res].key, sp.District);
            return b == null || b.Deficit == null || y < sp.From || y > sp.To ? 0f : b.Deficit[TwinData.YI(y)];
        }
        public static bool Active(Spell sp, int y) => y >= sp.From && y <= sp.To;
        public static string Name(Spell sp) => Loc.T(Res[sp.Res].name);
        public static string Where(Spell sp) => sp.District < 0 ? "город" : CityStats.DistrictIds[sp.District];
        public static string Amount(Spell sp, float v) => InvestRegistry.Fmt(Res[sp.Res].key, v) + " " + Res[sp.Res].unit;
        static string Place(Spell sp) => sp.District < 0 ? "городской сети" : CityStats.DistrictIds[sp.District];

        /// <summary>The whole spell in one line (Аналитика, and Инфраструктура in the years without a deficit):
        /// «Электроэнергия, 220 кВ: дефицит в Golden в 2034–2035 — 2,8 МВт в 2034, до 24 МВт в 2035».</summary>
        public static string Story(Spell sp)
        {
            if (sp.To == sp.From)
                return string.Format("{0}: дефицит в {1} в {2} году — {3}", Name(sp), Place(sp), sp.From, Amount(sp, sp.First));
            if (sp.PeakYear == sp.From)
                return string.Format("{0}: дефицит в {1} в {2}–{3} — до {4} в {2}", Name(sp), Place(sp), sp.From, sp.To, Amount(sp, sp.Peak));
            return string.Format("{0}: дефицит в {1} в {2}–{3} — {4} в {2}, до {5} в {6}", Name(sp), Place(sp), sp.From, sp.To, Amount(sp, sp.First), Amount(sp, sp.Peak), sp.PeakYear);
        }
        /// <summary>The deficit of a spell in year y (Журнал, Инфраструктура in that year): «Golden: спрос выше мощности на 2,8 МВт».</summary>
        public static string InYear(int s, Spell sp, int y) => string.Format("{0}: спрос выше мощности на {1}", sp.District < 0 ? "Город" : Where(sp), Amount(sp, At(s, sp, y)));
    }
}
