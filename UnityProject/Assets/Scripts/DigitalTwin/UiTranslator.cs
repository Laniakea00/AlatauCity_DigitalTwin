using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin
{
    /// <summary>English and Kazakh for the whole interface. The code writes its texts in Russian; every frame (before the UI is laid out)
    /// each text on screen is translated from the catalogue Resources/Loc/strings.json (Russian → English, Kazakh), and put back to
    /// Russian when the language returns to RU. The catalogue holds every Russian string of the code (Tools/loc/extract.py); a string built
    /// from pieces is matched against templates ({0}, {1} — numbers, names), then against the pieces the code glues it from, then split into
    /// sentences and at separators (a run of parts the catalogue knows as one text stays one), then translated word group by word group;
    /// numbers, names and years pass through, units after numbers are translated (м → m, тыс. → k). Language: the globe menu in the
    /// header, remembered between runs.</summary>
    public class UiTranslator : MonoBehaviour
    {
        public static UiTranslator Instance;
        /// <summary>The language choice is remembered between runs; off while the video plays (it is in English whatever the presenter uses).</summary>
        public static bool Persist = true;
        [System.Serializable] class Row { public string r, e, k; }
        [System.Serializable] class Cat { public Row[] s; }
        class Tpl { public Regex Re, Greedy; public string En, Kz, Anchor; }
        class Seen { public string Orig, Shown, Lang; }

        static Dictionary<string, (string en, string kz)> exact, upper;
        static List<Tpl> tpls;
        static Regex fragEn, fragKz; static Dictionary<string, (string en, string kz)> frag;
        static readonly Dictionary<string, string>[] cache = { new Dictionary<string, string>(), new Dictionary<string, string>() };
        static readonly Regex Cyr = new Regex("[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]", RegexOptions.Compiled);
        static readonly char[] Edge = { ' ', '·', '—', '–', ',', ':', ';', '(', ')', '/', '→', '\n' };
        static readonly Regex SentenceEnd = new Regex(@"(?<=[.!?]) +(?=[А-ЯЁA-Z«""])", RegexOptions.Compiled);
        static readonly Regex Abbrev = new Regex(@"(?:^|[\s(«])(?:ул|пр|просп|пер|обл|г|гг|тыс|млн|млрд|трлн|чел|им|св|мес|руб|т\.е|т\.к|напр|ст|стр|д)\.$", RegexOptions.Compiled);
        // units and small words after numbers (the code writes «121 м», «140 тыс. т в год», «к 2041»): English, Kazakh (null — as in Russian)
        static readonly (Regex re, string en, string kz)[] Units = U(
            (@"(?<=\d)[ \u00a0\u202f]?тыс\.", "k", " мың"), (@"(?<=\d)[ \u00a0\u202f]млн(?!\p{L})", " mln", null), (@"(?<=\d)[ \u00a0\u202f]млрд(?!\p{L})", " bn", null),
            (@"(?<=\d)[ \u00a0\u202f]трлн(?!\p{L})", " tn", null), (@"(?<=\d)[ \u00a0\u202f]км/ч(?!\p{L})", " km/h", " км/сағ"), (@"(?<=\d)[ \u00a0\u202f]км²", " km²", null),
            (@"(?<=\d)[ \u00a0\u202f]км(?!\p{L})", " km", null), (@"(?<=(?:\d|mln|млн))[ \u00a0\u202f]м²", " m²", null), (@"(?<=\d)[ \u00a0\u202f]м³", " m³", null),
            (@"(?<=\d)[ \u00a0\u202f]м(?![\p{L}²³])", " m", null), (@"(?<=\d)[ \u00a0\u202f]га(?!\p{L})", " ha", null), (@"(?<=\d)[ \u00a0\u202f]МВт(?!\p{L})", " MW", null),
            (@"(?<=\d)[ \u00a0\u202f]кВт(?!\p{L})", " kW", null), (@"(?<=\d)[ \u00a0\u202f]ГВт(?!\p{L})", " GW", null), (@"(?<=\d)[ \u00a0\u202f]мин(?!\p{L})", " min", null),
            (@"(?<=\d)[ \u00a0\u202f]ч(?!\p{L})", " h", " сағ"), (@"(?<=\d)[ \u00a0\u202f]сек(?!\p{L})", " s", null), (@"(?<=\d)[ \u00a0\u202f]чел\.", " people", " адам"),
            (@"(?<=\d)[ \u00a0\u202f]т(?!\p{L})", " t", null), (@"(?<=\d)[ \u00a0\u202f]мес\.", " mo", " ай"), (@"(?<=\d)[ \u00a0\u202f]лет(?!\p{L})", " years", " жыл"),
            (@"(?<=\d)[ \u00a0\u202f]дн(?:ей|я)(?!\p{L})", " days", " күн"), (@"(?<=\d)[ \u00a0\u202f]мест(?!\p{L})", " places", " орын"),
            (@"(?<!\p{L})в год(?!\p{L})", "per year", "жылына"), (@"(?<!\p{L})в сутки(?!\p{L})", "per day", "тәулігіне"), (@"(?<!\p{L})в час(?!\p{L})", "per hour", "сағатына"),
            (@"(?<!\p{L})к (\d{4})(?!\d)", "by $1", "$1 жылға қарай"), (@"(?<!\p{L})с (\d{4})(?!\d)", "from $1", "$1 жылдан бастап"),
            (@"(?<!\p{L})до (?=[\d$≈~])", "up to ", null), (@"(?<!\p{L})от (?=\d)", "from ", null));
        static (Regex, string, string)[] U(params (string re, string en, string kz)[] a) => a.Select(x => (new Regex(x.re, RegexOptions.Compiled), x.en, x.kz)).ToArray();
        static readonly string[] Seps = { "\n", " · ", " — ", " – ", "; ", ": ", ". ", ", ", " / ", " (", ") ", " → " };
        readonly Dictionary<TextElement, Seen> seen = new Dictionary<TextElement, Seen>();
        readonly Dictionary<VisualElement, Seen> tips = new Dictionary<VisualElement, Seen>();
        readonly List<UIDocument> docs = new List<UIDocument>();
        float docScan; int sweep, relayoutAt = -1, relayoutLeft;
#if UNITY_EDITOR
        // texts that came out (partly) untranslated, written to UnityProject/Recordings/loc_misses.txt for Tools/loc
        static readonly HashSet<string> misses = new HashSet<string>(); static bool missDirty; float missSave;
        void SaveMisses()
        {
            if (!missDirty || Time.unscaledTime < missSave) return; missSave = Time.unscaledTime + 3f; missDirty = false;
            try
            {
                var dir = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "..", "Recordings")); System.IO.Directory.CreateDirectory(dir);
                System.IO.File.WriteAllLines(System.IO.Path.Combine(dir, "loc_misses.txt"), misses.Select(m => m.Replace("\r", "").Replace("\n", "\\n")).OrderBy(m => m));
            }
            catch (System.Exception e) { Debug.LogWarning("[Alatau] loc misses: " + e.Message); }
        }
#endif

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Boot()
        {
            var l = PlayerPrefs.GetString("alatau_lang", "ru"); if (l != "ru" && l != "en" && l != "kz") l = "ru";
            if (l != "ru") TwinState.SetLanguage(l);
            TwinState.OnLanguageChanged += x => { if (Persist) PlayerPrefs.SetString("alatau_lang", x); };
        }
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Spawn() { if (Instance == null) new GameObject("UI translator").AddComponent<UiTranslator>(); }
        void Awake() { Instance = this; TwinState.OnLanguageChanged += OnLang; if (Loc.Language != "ru") { relayoutAt = 30; relayoutLeft = 3; } }
        void OnDestroy() { TwinState.OnLanguageChanged -= OnLang; }
        void OnLang(string l) { relayoutAt = Time.frameCount + 2; relayoutLeft = 3; }

        // ------------------------------------------------------------------ catalogue
        static void Load()
        {
            if (exact != null) return;
            exact = new Dictionary<string, (string, string)>(); tpls = new List<Tpl>(); frag = new Dictionary<string, (string, string)>();
            var ta = Resources.Load<TextAsset>("Loc/strings"); if (ta == null) { Debug.LogWarning("[Alatau] translations missing (Resources/Loc/strings.json)"); return; }
            Cat cat = null; try { cat = JsonUtility.FromJson<Cat>(ta.text); } catch (System.Exception e) { Debug.LogWarning("[Alatau] translations: " + e.Message); }
            if (cat?.s == null) return;
            var hole = new Regex(@"\{(\d+)\}");
            foreach (var row in cat.s)
            {
                if (string.IsNullOrEmpty(row.r)) continue;
                string en = string.IsNullOrEmpty(row.e) ? row.r : row.e, kz = string.IsNullOrEmpty(row.k) ? row.r : row.k;
                if (hole.IsMatch(row.r))
                {
                    // a template («{0} мест», « Свои доходы … с {0} года.»): held without the spaces and separators the code put around it
                    var rt = row.r.Trim(); AddTpl(rt, en.Trim(), kz.Trim());
                    var rb = rt.Trim(Edge); if (rb != rt && hole.IsMatch(rb)) AddTpl(rb, en.Trim().Trim(Edge), kz.Trim().Trim(Edge));
                    continue;
                }
                exact[row.r] = (en, kz);
                var t = row.r.Trim(); if (t.Length > 0 && !exact.ContainsKey(t)) exact[t] = (en.Trim(), kz.Trim());
                // « · камера », «, уведомлён прораб»: pieces the code glues to others; held without their separators too
                var b = row.r.Trim(Edge); if (b.Length > 0 && b != t && !exact.ContainsKey(b)) exact[b] = (en.Trim(Edge), kz.Trim(Edge));
                if (b.Length >= 3 && Cyr.IsMatch(b) && !frag.ContainsKey(b)) frag[b] = (en.Trim(Edge), kz.Trim(Edge));
                if (t.Length >= 3 && Cyr.IsMatch(t)) frag[t] = (en.Trim(), kz.Trim());
            }
            var have = new HashSet<string>(); tpls.RemoveAll(x => !have.Add(x.Re.ToString()));
            upper = new Dictionary<string, (string, string)>();
            foreach (var kv in exact) { var u = kv.Key.Trim().ToUpperInvariant(); if (!upper.ContainsKey(u)) upper[u] = (kv.Value.en.Trim().ToUpperInvariant(), kv.Value.kz.Trim().ToUpperInvariant()); }
            tpls.Sort((a, b) => b.Anchor.Length.CompareTo(a.Anchor.Length));
            // word groups inside a longer text, longest first, whole words only
            var keys = frag.Keys.OrderByDescending(k => k.Length).Select(Regex.Escape).ToArray();
            if (keys.Length > 0)
            {
                var pat = @"(?<!\p{L})(" + string.Join("|", keys) + @")(?!\p{L})";
                fragEn = fragKz = new Regex(pat, RegexOptions.Compiled);
            }
            Debug.Log($"[Alatau] translations: {exact.Count} phrases, {tpls.Count} templates");
        }
        static void AddTpl(string r, string en, string kz)
        {
            // literal parts must match, holes take anything (numbers, names, other phrases)
            var parts = Regex.Split(r, @"\{(\d+)\}"); var sb = new StringBuilder("^"); string anchor = "";
            for (int i = 0; i < parts.Length; i++)
            {
                if (i % 2 == 0) { sb.Append(Regex.Escape(parts[i])); if (parts[i].Trim().Length > anchor.Length) anchor = parts[i].Trim(); }
                else sb.Append("(?<h" + parts[i] + ">.+?)");
            }
            sb.Append("$");
            if (anchor.Length < 2 || !Cyr.IsMatch(anchor)) return;                           // «{0} {1}» and the like: nothing to hold on to
            // holes take as little as they can; the greedy twin is for «{4} ({5} %)» with «строительство (ПГС) (84 %)»
            try { var re = sb.ToString(); tpls.Add(new Tpl { Re = new Regex(re, RegexOptions.Singleline), Greedy = new Regex(re.Replace(".+?)", ".+)"), RegexOptions.Singleline), En = en, Kz = kz, Anchor = anchor }); } catch { }
        }

        /// <summary>The text in the current language (Russian is returned as it is).</summary>
        public static string Tr(string s) => Tr(s, Loc.Language);
        public static string Tr(string s, string lang)
        {
            if (string.IsNullOrEmpty(s) || lang == "ru" || !Cyr.IsMatch(s)) return s;
            Load(); int li = lang == "en" ? 0 : 1; var c = cache[li];
            if (c.TryGetValue(s, out var r)) return r;
            r = Core(s, li, 0);
#if UNITY_EDITOR
            if (li == 0 && Cyr.IsMatch(r) && misses.Add(s)) missDirty = true;          // English still has Cyrillic: listed for the catalogue
#endif
            if (c.Count > 30000) c.Clear();
            c[s] = r; return r;
        }
        static string Pick((string en, string kz) p, int li) => li == 0 ? p.en : p.kz;

        static string Core(string s, int li, int depth)
        {
            if (!Cyr.IsMatch(s)) return li == 0 ? EnNumbers(s) : s;
            if (exact.TryGetValue(s, out var p)) return Pick(p, li);
            // spaces and marks around the words (✓, ≈, +, →) stay as they are
            int a = 0, b = s.Length;
            while (a < b && Mark(s[a])) a++;
            while (b > a && Mark(s[b - 1])) b--;
            if (a == b) return s;
            string lead = s.Substring(0, a), trail = s.Substring(b), t = s.Substring(a, b - a);
            // the choices below are made on the English result (Kazakh is Cyrillic too), the text is then given in the language asked
            if (Whole(t, li, depth, out var w, out var loose)) return lead + w + trail;
            if (depth > 6) return loose != null ? lead + loose + trail : s;
            // the pieces the code glues the text from («ВВОД ПЛОЩАДЕЙ · до » + 20 + « млн м²»), units after numbers
            var g = Groups(t, li);
            if (!Cyr.IsMatch(li == 0 ? g : Groups(t, 0))) return lead + g + trail;
            if (loose != null) return lead + loose + trail;                             // a template with a name it does not know
            // sentences, then the parts between separators
            var ss = Sentences(t);
            if (ss.Count > 1) { var o = Join(ss, " ", li, depth); if (o != null) return lead + o + trail; }
            foreach (var sep in Seps)
            {
                if (t.IndexOf(sep, System.StringComparison.Ordinal) < 0) continue;
                var o = Join(t.Split(new[] { sep }, System.StringSplitOptions.None), sep, li, depth);
                if (o != null) return lead + o + trail;
            }
            return g != t ? lead + g + trail : s;
        }
        static bool Mark(char c)
        {
            if (char.IsWhiteSpace(c) || "•·—–→←↑↓…|".IndexOf(c) >= 0) return true;
            var u = char.GetUnicodeCategory(c); return u == UnicodeCategory.OtherSymbol || u == UnicodeCategory.MathSymbol;
        }
        /// <summary>The text as a whole: a phrase of the catalogue (also in capitals) or a template whose holes come out translated;
        /// <paramref name="loose"/> — the first template that matched but left a hole untranslated (a name the catalogue does not know).</summary>
        static bool Whole(string t, int li, int depth, out string r, out string loose)
        {
            r = loose = null;
            if (exact.TryGetValue(t, out var p)) { r = Pick(p, li); return true; }
            if (t == t.ToUpperInvariant() && upper.TryGetValue(t, out p)) { r = Pick(p, li); return true; }
            foreach (var tp in tpls)
            {
                if (!t.Contains(tp.Anchor)) continue;
                var m = tp.Re.Match(t); if (!m.Success) continue;
                bool clean = Clean(m, depth);
                if (!clean) { var mg = tp.Greedy.Match(t); if (mg.Success && Clean(mg, depth)) { m = mg; clean = true; } }
                var o = Fill(tp, m, li, depth);
                if (clean) { r = o; return true; }
                if (loose == null) loose = o;
            }
            return false;
        }
        static string Fill(Tpl tp, Match m, int li, int depth) =>
            Regex.Replace(li == 0 ? tp.En : tp.Kz, @"\{(\d+)\}", h => { var g = m.Groups["h" + h.Groups[1].Value]; return g.Success ? Core(g.Value, li, depth + 1) : h.Value; });
        /// <summary>Every hole of the match comes out in English without Cyrillic (the way the text was cut is right).</summary>
        static bool Clean(Match m, int depth)
        {
            for (int i = 1; i < m.Groups.Count; i++) if (Cyr.IsMatch(m.Groups[i].Value) && Cyr.IsMatch(Core(m.Groups[i].Value, 0, depth + 1))) return false;
            return true;
        }
        /// <summary>Word groups of the catalogue anywhere in the text, then units after numbers.</summary>
        static string Groups(string t, int li)
        {
            var re = li == 0 ? fragEn : fragKz;
            var o = re == null ? t : re.Replace(t, m => frag.TryGetValue(m.Value, out var q) ? Pick(q, li) : m.Value);
            foreach (var (ure, en, kz) in Units) { var to = li == 0 ? en : kz; if (to != null && Cyr.IsMatch(o)) o = ure.Replace(o, to); }
            return li == 0 ? EnNumbers(o) : o;
        }
        static List<string> Sentences(string t)
        {
            var o = new List<string>();
            foreach (var x in SentenceEnd.Split(t))
            {
                if (o.Count > 0 && (o[o.Count - 1].Length < 12 || Abbrev.IsMatch(o[o.Count - 1]))) o[o.Count - 1] += " " + x;  // «ул. Финансовая»
                else o.Add(x);
            }
            return o;
        }
        /// <summary>Parts translated one by one; the longest run of parts the catalogue knows as one text («уведомлён прораб · подрядчику —
        /// замечание» after a street name) is translated as one. Null when nothing changed.</summary>
        static string Join(IList<string> parts, string sep, int li, int depth)
        {
            var sb = new StringBuilder(); bool changed = false;
            for (int i = 0; i < parts.Count;)
            {
                string tr = null; int take = 1;
                for (int j = parts.Count - (i == 0 ? 2 : 1); j > i && tr == null; j--)
                    if (Whole(string.Join(sep, parts.Skip(i).Take(j - i + 1)), li, depth + 1, out var w, out _)) { tr = w; take = j - i + 1; }
                if (tr == null) tr = Core(parts[i], li, depth + 1);
                if (i > 0) sb.Append(sep);
                if (take > 1 || tr != parts[i]) changed = true;
                sb.Append(tr); i += take;
            }
            return changed ? sb.ToString() : null;
        }
        /// <summary>«1 962,5» → «1,962.5» in English texts (numbers that the code formatted the Russian way).</summary>
        static string EnNumbers(string s)
        {
            s = Regex.Replace(s, @"(?<=\d)[   ](?=\d{3}(?!\d))", ",");
            return Regex.Replace(s, @"(?<=\d),(?=\d{1,2}(?!\d))", ".");
        }

        // ------------------------------------------------------------------ the texts on screen
        void LateUpdate()
        {
            if (Time.unscaledTime > docScan) { docScan = Time.unscaledTime + 2f; docs.Clear(); docs.AddRange(FindObjectsByType<UIDocument>(FindObjectsSortMode.None)); }
            string lang = Loc.Language;
            foreach (var d in docs)
            {
                if (d == null || d.rootVisualElement == null) continue;
                Walk(d.rootVisualElement, lang);
            }
            // the first time a language is shown its letters are added to the font atlas while the texts are being measured, and a
            // label can stay measured without them («Typ», «Ope n»): a few frames later every text is measured again
            if (relayoutAt >= 0 && Time.frameCount >= relayoutAt)
            {
                foreach (var d in docs) if (d != null && d.rootVisualElement != null) Remeasure(d.rootVisualElement);
                relayoutAt = --relayoutLeft > 0 ? Time.frameCount + 20 : -1;
            }
#if UNITY_EDITOR
            SaveMisses();
#endif
            if (++sweep % 300 == 0)
            {
                foreach (var k in seen.Keys.Where(e => e.panel == null).ToList()) seen.Remove(k);
                foreach (var k in tips.Keys.Where(e => e.panel == null).ToList()) tips.Remove(k);
            }
        }
        void Walk(VisualElement e, string lang)
        {
            if (e.resolvedStyle.display == DisplayStyle.None) return;
            if (e is TextField) return;                                          // what the user types stays as typed
            if (e.ClassListContains("no-tr")) return;                            // names that stay as written (the language menu)
            if (e is TextElement te) Text(te, lang);
            if (!string.IsNullOrEmpty(e.tooltip)) Tip(e, lang);
            int n = e.hierarchy.childCount;
            for (int i = 0; i < n; i++) Walk(e.hierarchy[i], lang);
        }
        static void Remeasure(VisualElement e)
        {
            if (e is TextElement te && !(e is TextField) && !string.IsNullOrEmpty(te.text)) { var t = te.text; te.text = t + " "; te.text = t; }
            int n = e.hierarchy.childCount;
            for (int i = 0; i < n; i++) Remeasure(e.hierarchy[i]);
        }
        void Text(TextElement te, string lang)
        {
            var cur = te.text; if (string.IsNullOrEmpty(cur)) return;
            seen.TryGetValue(te, out var s);
            if (s != null && s.Lang == lang && (ReferenceEquals(cur, s.Shown) || cur == s.Shown)) return;
            if (s != null && cur == s.Shown) cur = s.Orig;                       // the language changed: start again from the original
            if (lang == "ru") { if (s != null) { s.Orig = cur; s.Shown = cur; s.Lang = lang; } if (te.text != cur) te.text = cur; return; }
            if (!Cyr.IsMatch(cur)) { if (s != null) seen.Remove(te); return; }
            var tr = Tr(cur, lang);
            if (s == null) seen[te] = s = new Seen();
            s.Orig = cur; s.Shown = tr; s.Lang = lang;
            if (te.text != tr) te.text = tr;
        }
        void Tip(VisualElement e, string lang)
        {
            var cur = e.tooltip; tips.TryGetValue(e, out var s);
            if (s != null && cur == s.Shown && s.Lang == lang) return;
            if (s != null && cur == s.Shown) cur = s.Orig;
            if (lang == "ru") { if (s != null) { s.Orig = cur; s.Shown = cur; s.Lang = lang; } e.tooltip = cur; return; }
            if (!Cyr.IsMatch(cur)) return;
            var tr = Tr(cur, lang); if (s == null) tips[e] = s = new Seen();
            s.Orig = cur; s.Shown = tr; s.Lang = lang; e.tooltip = tr;
        }
    }
}
