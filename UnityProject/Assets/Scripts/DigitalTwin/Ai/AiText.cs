using System.Text.RegularExpressions;

namespace AlatauCity.DigitalTwin.Ai
{
    /// <summary>The model's text for a UI Toolkit label: Markdown is not shown raw. **x** / __x__ → bold (rich text, only when the text has
    /// no other angle brackets, else plain), *x* / _x_ / `x` → x, list markers «* », «- », «+ » → «• », «#» headings and links → plain words.</summary>
    public static class AiText
    {
        static readonly Regex Bold = new Regex(@"\*\*(.+?)\*\*|__(.+?)__", RegexOptions.Compiled | RegexOptions.Singleline);
        static readonly Regex Italic = new Regex(@"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])|(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])", RegexOptions.Compiled);
        static readonly Regex Code = new Regex(@"`+([^`\n]*)`+", RegexOptions.Compiled);
        static readonly Regex Link = new Regex(@"\[([^\]\n]+)\]\((?:https?://)?[^)\s]+\)", RegexOptions.Compiled);
        static readonly Regex Heading = new Regex(@"^[ \t]{0,3}#{1,6}[ \t]*", RegexOptions.Compiled | RegexOptions.Multiline);
        static readonly Regex Bullet = new Regex(@"^[ \t]*(?:[*+\-•·])[ \t]+", RegexOptions.Compiled | RegexOptions.Multiline);
        static readonly Regex Rule = new Regex(@"^[ \t]*([-*_])([ \t]*\1){2,}[ \t]*$\n?", RegexOptions.Compiled | RegexOptions.Multiline);
        static readonly Regex Blank = new Regex(@"\n{3,}", RegexOptions.Compiled);

        public static string Clean(string s)
        {
            if (string.IsNullOrEmpty(s)) return s ?? "";
            s = s.Replace("\r\n", "\n");
            bool rich = s.IndexOf('<') < 0 && s.IndexOf('>') < 0;     // a stray "<" would break the rich-text parse: then plain bold
            s = Rule.Replace(s, "");
            s = Heading.Replace(s, "");
            s = Bullet.Replace(s, "• ");
            s = Link.Replace(s, "$1");
            s = Code.Replace(s, "$1");
            s = Bold.Replace(s, m => { var x = m.Groups[1].Success ? m.Groups[1].Value : m.Groups[2].Value; return rich ? "<b>" + x + "</b>" : x; });
            s = Italic.Replace(s, m => m.Groups[1].Success ? m.Groups[1].Value : m.Groups[2].Value);
            s = s.Replace("**", "").Replace("__", "");
            return Blank.Replace(s, "\n\n").Trim();
        }
    }
}
