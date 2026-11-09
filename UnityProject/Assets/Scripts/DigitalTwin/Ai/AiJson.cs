using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace AlatauCity.DigitalTwin.Ai
{
    /// <summary>A small JSON writer for the AI requests (the reader is Data/TwinJson). Objects are ordered dictionaries
    /// (Dictionary keeps insertion order when nothing is removed), arrays are lists; numbers are written invariantly.</summary>
    public static class AiJson
    {
        /// <summary>An object literal: AiJson.O("a", 1, "b", "x").</summary>
        public static Dictionary<string, object> O(params object[] kv)
        {
            var d = new Dictionary<string, object>();
            for (int i = 0; i + 1 < kv.Length; i += 2) if (kv[i + 1] != null) d[(string)kv[i]] = kv[i + 1];
            return d;
        }
        public static List<object> A(params object[] items) => new List<object>(items);

        public static string Write(object v) { var sb = new StringBuilder(256); W(sb, v); return sb.ToString(); }

        static void W(StringBuilder sb, object v)
        {
            switch (v)
            {
                case null: sb.Append("null"); return;
                case string s: Str(sb, s); return;
                case bool b: sb.Append(b ? "true" : "false"); return;
                case int i: sb.Append(i.ToString(CultureInfo.InvariantCulture)); return;
                case long l: sb.Append(l.ToString(CultureInfo.InvariantCulture)); return;
                case float f: sb.Append(float.IsNaN(f) || float.IsInfinity(f) ? "null" : Math.Round(f, 3).ToString(CultureInfo.InvariantCulture)); return;
                case double d: sb.Append(double.IsNaN(d) || double.IsInfinity(d) ? "null" : Math.Round(d, 3).ToString(CultureInfo.InvariantCulture)); return;
                case Raw r: sb.Append(r.Json); return;
                case IDictionary<string, object> o:
                {
                    sb.Append('{'); bool first = true;
                    foreach (var kv in o) { if (!first) sb.Append(','); first = false; Str(sb, kv.Key); sb.Append(':'); W(sb, kv.Value); }
                    sb.Append('}'); return;
                }
                case IEnumerable e:
                {
                    sb.Append('['); bool first = true;
                    foreach (var x in e) { if (!first) sb.Append(','); first = false; W(sb, x); }
                    sb.Append(']'); return;
                }
                default: Str(sb, Convert.ToString(v, CultureInfo.InvariantCulture)); return;
            }
        }

        static void Str(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4")); else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }

        /// <summary>Already serialized JSON, written as is (the model's own turn, sent back unchanged).</summary>
        public sealed class Raw { public readonly string Json; public Raw(string json) { Json = json; } }
    }
}
