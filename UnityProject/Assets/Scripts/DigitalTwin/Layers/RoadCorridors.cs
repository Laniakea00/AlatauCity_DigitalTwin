using System;
using System.Collections;
using System.Reflection;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The cross-section of a road edge (TwinData.Roads index) as the things beside the road need it: trees, hedges, props.
    /// The source is the street profile of the new map data (norms.street_profiles, roads.json "p" → "profiles", read by the road
    /// reader as FilmRoads.Profile(edge)) when the road reader offers it; otherwise the four class widths of today (FilmRoads.Dims),
    /// so with today's data nothing changes. To wire another source, set Provider (one line in any file); without it the road
    /// reader's public static FilmRoads.Profile(int) is found by name and read by field name (lanes, lane_w, median_w,
    /// sidewalk_w, verge_w, bike_w, parking_w, red_line_w, oneway / k, t / class).</summary>
    public static class RoadCorridors
    {
        /// <summary>Half widths from the centre line of the edge, metres.</summary>
        public struct Corridor
        {
            /// <summary>To the outer kerb: nothing grows on the carriageway (a two-way road with a median: across the median too).</summary>
            public float Carriage;
            /// <summary>To the red line (outer edge of pavement and verge): no groves or yard trees inside.</summary>
            public float Outer;
            /// <summary>Offset of the street tree row on each pavement or verge (0: no row).</summary>
            public float Row;
            /// <summary>Width of a planted central strip (boulevard, divided road), metres; 0 = none.</summary>
            public float Median;
            /// <summary>One carriageway of a divided road (runs in point order): its median lies on its left, outside Carriage.</summary>
            public bool OneSide;
            /// <summary>From the street profile of the new data (false: today's class widths).</summary>
            public bool FromProfile;
        }
        public delegate bool Source(int edge, out Corridor c);
        /// <summary>Optional source of profiles; null = look for FilmRoads.Profile(int), then the class widths.</summary>
        public static Source Provider;
        /// <summary>How many edges got their corridor from a profile (for the log).</summary>
        public static int FromProfiles;

        /// <summary>The corridor of edge 'edge' of class 'cls' (today's class widths when there is no profile).</summary>
        public static Corridor Get(int edge, TwinData.RoadClass cls)
        {
            if (Provider != null) { try { if (Provider(edge, out var c) && c.Carriage > 0f) { FromProfiles++; return Sane(c); } } catch (Exception) { } }
            if (Probe() && Reflect(edge, out var r)) { FromProfiles++; return Sane(r); }
            FilmRoads.Dims(cls, out float half, out float walk, out _, out _);
            return new Corridor { Carriage = half, Outer = half + walk, Row = walk > 0f && !FilmRoads.Dropped(edge) ? half + walk * 0.55f : 0f };
        }
        static Corridor Sane(Corridor c)
        {
            c.Outer = Mathf.Max(c.Outer, c.Carriage);
            if (c.Row > 0f) c.Row = Mathf.Clamp(c.Row, c.Carriage + 1.0f, Mathf.Max(c.Outer - 0.6f, c.Carriage + 1.0f));
            c.Median = Mathf.Max(0f, c.Median);
            return c;
        }

        // ------------------------------------------------------------------ the road reader's own profiles, found by name
        static bool probed; static MethodInfo profile;
        static bool Probe()
        {
            if (probed) return profile != null; probed = true;
            try
            {
                var t = typeof(FilmRoads);
                foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Static))
                    if (m.Name == "Profile" && m.ReturnType != typeof(void) && m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType == typeof(int)) { profile = m; break; }
            }
            catch (Exception) { profile = null; }
            Debug.Log("[Alatau] road corridors: " + (profile != null ? "street profiles from FilmRoads.Profile(edge)" : "no FilmRoads.Profile: today's class widths"));
            return profile != null;
        }
        static bool Reflect(int edge, out Corridor c)
        {
            c = default;
            object p; try { p = profile.Invoke(null, new object[] { edge }); } catch (Exception) { return false; }
            if (p == null) return false;
            float laneW = Num(p, "lanew", 0, 0f), median = Num(p, "medianw", 0, 0f), red = Num(p, "redlinew", 0, 0f);
            float lanes = Mathf.Max(Num(p, "lanes", 0, 0f), Num(p, "lanes", 1, 0f));
            float park = Mathf.Max(Num(p, "parkingw", 0, 0f), Num(p, "parkingw", 1, 0f)), walk = Mathf.Max(Num(p, "sidewalkw", 0, 0f), Num(p, "sidewalkw", 1, 0f));
            float verge = Mathf.Max(Num(p, "vergew", 0, 0f), Num(p, "vergew", 1, 0f)), bike = Mathf.Max(Num(p, "bikew", 0, 0f), Num(p, "bikew", 1, 0f));
            float half = Num(p, "half", 0, 0f);                                      // a reader that gives half widths directly
            bool one = Num(p, "oneway", 0, 0f) > 0.5f || Mathf.RoundToInt(Num(p, "k", 0, 0f)) == 1;
            string cls = Str(p, "t") ?? Str(p, "class") ?? Str(p, "cls");
            if (half <= 0f)
            {
                if (laneW <= 0f || lanes <= 0f) return false;
                float l0 = Num(p, "lanes", 0, 0f), l1 = Num(p, "lanes", 1, 0f);
                half = one ? Mathf.Max(l0 + l1, 1f) * laneW * 0.5f + park * 0.5f : lanes * laneW + park + median * 0.5f;
            }
            if (cls == "boulevard" && median < 4f) median = 8f;
            float outer = red > 0f ? red * 0.5f : half + verge + bike + walk;
            float row = verge >= 1.2f ? half + verge * 0.5f : walk >= 1.5f ? half + bike + walk * 0.55f : 0f;
            c = new Corridor { Carriage = half, Outer = Mathf.Max(outer, half), Row = row, Median = median, OneSide = one, FromProfile = true };
            return true;
        }
        static string Norm(string s) => s.Replace("_", "").ToLowerInvariant();
        // the members of the profile type by normalised name, looked up once per type (thousands of edges are read at start-up)
        static Type memberType; static System.Collections.Generic.Dictionary<string, MemberInfo> members;
        static object Member(object o, string key)
        {
            var t = o.GetType();
            if (t != memberType)
            {
                memberType = t; members = new System.Collections.Generic.Dictionary<string, MemberInfo>(); const BindingFlags f = BindingFlags.Public | BindingFlags.Instance;
                foreach (var fi in t.GetFields(f)) members[Norm(fi.Name)] = fi;
                foreach (var pi in t.GetProperties(f)) if (pi.GetIndexParameters().Length == 0 && !members.ContainsKey(Norm(pi.Name))) members[Norm(pi.Name)] = pi;
            }
            if (!members.TryGetValue(key, out var m)) return null;
            return m is FieldInfo fi2 ? fi2.GetValue(o) : ((PropertyInfo)m).GetValue(o);
        }
        static float Num(object o, string key, int side, float def)
        {
            try
            {
                var v = Member(o, key); if (v == null) return def;
                if (v is IList l) { if (l.Count == 0) return def; v = l[Mathf.Clamp(side, 0, l.Count - 1)]; }
                if (v is Vector2 v2) return side == 0 ? v2.x : v2.y;
                return v is IConvertible ? Convert.ToSingle(v, System.Globalization.CultureInfo.InvariantCulture) : def;
            }
            catch (Exception) { return def; }
        }
        static string Str(object o, string key) { try { return Member(o, key) as string; } catch (Exception) { return null; } }
    }
}
