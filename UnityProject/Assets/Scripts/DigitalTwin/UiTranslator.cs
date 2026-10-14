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
    /// from pieces is matched against templates ({0}, {1} — numbers, names), then split at separators, then translated word group by word
    /// group, so numbers, names and years in it pass through. Language: the RU · EN · KZ switch in the header, remembered between runs.</summary>
    public class UiTranslator : MonoBehaviour
    {
        public static UiTranslator Instance;
        [System.Serializable] class Row { public string r, e, k; }
        [System.Serializable] class Cat { public Row[] s; }
        class Tpl { public Regex Re; public string En, Kz, Anchor; }
        class Seen { public string Orig, Shown, Lang; }

        static Dictionary<string, (string en, string kz)> exact, upper;
        static List<Tpl> tpls;
        static Regex fragEn, fragKz; static Dictionary<string, (string en, string kz)> frag;
        static readonly Dictionary<string, string>[] cache = { new Dictionary<string, string>(), new Dictionary<string, string>() };
        static readonly Regex Cyr = new Regex("[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]", RegexOptions.Compiled);
        static readonly char[] Edge = { ' ', '·', '—', '–', ',', ':', ';', '(', ')', '/', '→', '\n' };
        static readonly string[] Seps = { "\n", " · ", " — ", " – ", "; ", ": ", ". ", ", ", " / ", " (", ") ", " → " };
        readonly Dictionary<TextElement, Seen> seen = new Dictionary<TextElement, Seen>();
        readonly Dictionary<VisualElement, Seen> tips = new Dictionary<VisualElement, Seen>();
        readonly List<UIDocument> docs = new List<UIDocument>();
        float docScan; int sweep, relayoutAt = -1, relayoutLeft;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void Boot()
        {
            var l = PlayerPrefs.GetString("alatau_lang", "ru"); if (l != "ru" && l != "en" && l != "kz") l = "ru";
            if (l != "ru") TwinState.SetLanguage(l);
            TwinState.OnLanguageChanged += x => PlayerPrefs.SetString("alatau_lang", x);
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
                    // a template: literal parts must match, holes take anything (numbers, names, other phrases)
                    var parts = hole.Split(row.r); var sb = new StringBuilder("^"); string anchor = "";
                    for (int i = 0; i < parts.Length; i++)
                    {
                        if (i % 2 == 0) { sb.Append(Regex.Escape(parts[i])); if (parts[i].Trim().Length > anchor.Length) anchor = parts[i].Trim(); }
                        else sb.Append("(?<h" + parts[i] + ">.+?)");
                    }
                    sb.Append("$");
                    if (anchor.Length < 2 || !Cyr.IsMatch(anchor)) continue;                     // «{0} {1}» and the like: nothing to hold on to
                    try { tpls.Add(new Tpl { Re = new Regex(sb.ToString(), RegexOptions.Singleline), En = en, Kz = kz, Anchor = anchor }); } catch { }
                    continue;
                }
                exact[row.r] = (en, kz);
                var t = row.r.Trim(); if (t.Length > 0 && !exact.ContainsKey(t)) exact[t] = (en.Trim(), kz.Trim());
                // « · камера », «, уведомлён прораб»: pieces the code glues to others; held without their separators too
                var b = row.r.Trim(Edge); if (b.Length > 0 && b != t && !exact.ContainsKey(b)) exact[b] = (en.Trim(Edge), kz.Trim(Edge));
                if (b.Length >= 3 && Cyr.IsMatch(b) && !frag.ContainsKey(b)) frag[b] = (en.Trim(Edge), kz.Trim(Edge));
                if (t.Length >= 3 && Cyr.IsMatch(t)) frag[t] = (en.Trim(), kz.Trim());
            }
            upper = new Dictionary<string, (string, string)>();
            foreach (var kv in exact) { var u = kv.Key.Trim().ToUpperInvariant(); if (!upper.ContainsKey(u)) upper[u] = (kv.Value.en.Trim().ToUpperInvariant(), kv.Value.kz.Trim().ToUpperInvariant()); }
            tpls.Sort((a, b) => b.Anchor.Length.CompareTo(a.Anchor.Length));
            // word groups inside a longer text, longest first, whole words only
            var keys = frag.Keys.OrderByDescending(k => k.Length).Select(Regex.Escape).ToArray();
            if (keys.Length > 0)
            {
                var pat = "(?<![А-Яа-яЁёA-Za-z])(" + string.Join("|", keys) + ")(?![А-Яа-яЁёA-Za-z])";
                fragEn = fragKz = new Regex(pat, RegexOptions.Compiled);
            }
            Debug.Log($"[Alatau] translations: {exact.Count} phrases, {tpls.Count} templates");
        }

        /// <summary>The text in the current language (Russian is returned as it is).</summary>
        public static string Tr(string s) => Tr(s, Loc.Language);
        public static string Tr(string s, string lang)
        {
            if (string.IsNullOrEmpty(s) || lang == "ru" || !Cyr.IsMatch(s)) return s;
            Load(); int li = lang == "en" ? 0 : 1; var c = cache[li];
            if (c.TryGetValue(s, out var r)) return r;
            r = Core(s, li, 0);
            if (c.Count > 30000) c.Clear();
            c[s] = r; return r;
        }
        static string Pick((string en, string kz) p, int li) => li == 0 ? p.en : p.kz;

        static string Core(string s, int li, int depth)
        {
            if (!Cyr.IsMatch(s)) return li == 0 ? EnNumbers(s) : s;
            if (exact.TryGetValue(s, out var p)) return Pick(p, li);
            string lead = s.Substring(0, s.Length - s.TrimStart().Length), trail = s.Substring(s.TrimEnd().Length), t = s.Trim();
            if (t.Length == 0) return s;
            if (exact.TryGetValue(t, out p)) return lead + Pick(p, li) + trail;
            // upper-case captions (the code upper-cases some headings)
            if (t == t.ToUpperInvariant() && upper.TryGetValue(t, out p)) return lead + Pick(p, li) + trail;
            if (depth > 6) return s;
            // templates
            foreach (var tp in tpls)
            {
                if (!t.Contains(tp.Anchor)) continue;
                var m = tp.Re.Match(t); if (!m.Success) continue;
                var outp = li == 0 ? tp.En : tp.Kz;
                outp = Regex.Replace(outp, @"\{(\d+)\}", h => { var g = m.Groups["h" + h.Groups[1].Value]; return g.Success ? Core(g.Value, li, depth + 1) : h.Value; });
                return lead + outp + trail;
            }
            // pieces between separators
            foreach (var sep in Seps)
            {
                int i = t.IndexOf(sep, System.StringComparison.Ordinal); if (i < 0) continue;
                var parts = t.Split(new[] { sep }, System.StringSplitOptions.None);
                var sb = new StringBuilder(); bool changed = false;
                for (int k = 0; k < parts.Length; k++)
                {
                    if (k > 0) sb.Append(sep);
                    var tr = Core(parts[k], li, depth + 1); if (tr != parts[k]) changed = true; sb.Append(tr);
                }
                if (changed) return lead + sb + trail;
            }
            // word groups
            var re = li == 0 ? fragEn : fragKz;
            if (re != null)
            {
                var o = re.Replace(t, m => frag.TryGetValue(m.Value, out var q) ? Pick(q, li) : m.Value);
                if (o != t) return lead + (li == 0 ? EnNumbers(o) : o) + trail;
            }
            return s;
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
            // in Russian there is nothing to translate: walk the texts only while some still show another language
            if (lang == "ru" && seen.Count == 0 && tips.Count == 0 && relayoutAt < 0) return;
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
            if (lang == "ru") { if (s != null) seen.Remove(te); if (te.text != cur) te.text = cur; return; }
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
            if (lang == "ru") { if (s != null) tips.Remove(e); if (e.tooltip != cur) e.tooltip = cur; return; }
            if (!Cyr.IsMatch(cur)) return;
            var tr = Tr(cur, lang); if (s == null) tips[e] = s = new Seen();
            s.Orig = cur; s.Shown = tr; s.Lang = lang; e.tooltip = tr;
        }
    }
}
