using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>Minimal JSON reader (no package dependency): objects → Dictionary&lt;string, object&gt;, arrays → List&lt;object&gt;,
    /// numbers → double, plus string / bool / null. Enough for the generated StreamingAssets/twin/*.json.</summary>
    public static class TwinJson
    {
        public static object Parse(string s) { int i = 0; var v = Value(s, ref i); return v; }

        static void Ws(string s, ref int i) { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }

        static object Value(string s, ref int i)
        {
            Ws(s, ref i); if (i >= s.Length) throw new FormatException("unexpected end of JSON");
            char c = s[i];
            if (c == '{') return Obj(s, ref i);
            if (c == '[') return Arr(s, ref i);
            if (c == '"') return Str(s, ref i);
            if (c == 't') { i += 4; return true; }
            if (c == 'f') { i += 5; return false; }
            if (c == 'n') { i += 4; return null; }
            return Num(s, ref i);
        }

        static Dictionary<string, object> Obj(string s, ref int i)
        {
            var d = new Dictionary<string, object>(); i++;
            Ws(s, ref i); if (s[i] == '}') { i++; return d; }
            while (true)
            {
                Ws(s, ref i); var k = Str(s, ref i); Ws(s, ref i); i++;   // ':'
                d[k] = Value(s, ref i); Ws(s, ref i);
                if (s[i] == ',') { i++; continue; }
                i++; return d;                                          // '}'
            }
        }

        static List<object> Arr(string s, ref int i)
        {
            var a = new List<object>(); i++;
            Ws(s, ref i); if (s[i] == ']') { i++; return a; }
            while (true)
            {
                a.Add(Value(s, ref i)); Ws(s, ref i);
                if (s[i] == ',') { i++; continue; }
                i++; return a;                                          // ']'
            }
        }

        static string Str(string s, ref int i)
        {
            i++; var sb = new StringBuilder();
            while (s[i] != '"')
            {
                char c = s[i++];
                if (c != '\\') { sb.Append(c); continue; }
                char e = s[i++];
                switch (e)
                {
                    case 'n': sb.Append('\n'); break;
                    case 't': sb.Append('\t'); break;
                    case 'r': sb.Append('\r'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'u': sb.Append((char)Convert.ToInt32(s.Substring(i, 4), 16)); i += 4; break;
                    default: sb.Append(e); break;
                }
            }
            i++; return sb.ToString();
        }

        static double Num(string s, ref int i)
        {
            int st = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            return double.Parse(s.Substring(st, i - st), NumberStyles.Float, CultureInfo.InvariantCulture);
        }

        // ---------- helpers for typed access ----------
        public static Dictionary<string, object> O(object o) => o as Dictionary<string, object>;
        public static List<object> A(object o) => o as List<object>;
        public static object G(object o, string key) { var d = O(o); return d != null && d.TryGetValue(key, out var v) ? v : null; }
        public static float F(object o) => o == null ? 0f : (float)(double)o;
        public static int I(object o) => o == null ? 0 : (int)Math.Round((double)o);
        public static string S(object o) => o as string ?? "";
        public static float[] Floats(object o) { var a = A(o); if (a == null) return new float[0]; var r = new float[a.Count]; for (int i = 0; i < r.Length; i++) r[i] = F(a[i]); return r; }
        public static int[] Ints(object o) { var a = A(o); if (a == null) return new int[0]; var r = new int[a.Count]; for (int i = 0; i < r.Length; i++) r[i] = I(a[i]); return r; }
    }
}
