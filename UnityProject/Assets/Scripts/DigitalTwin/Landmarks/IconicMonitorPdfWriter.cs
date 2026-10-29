using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>A minimal PDF writer: every page is one JPEG picture (DCTDecode image XObject) on an A4 sheet. The text of the report is in
    /// the pictures, so no font has to be embedded for the Cyrillic; the title in the document properties is a UTF‑16 string. Pure C# (no
    /// Unity types), so it can be tested outside the engine.</summary>
    public static class MonitorPdf
    {
        public const float PageW = 595.28f, PageH = 841.89f;                 // A4 in points

        /// <summary>The PDF of the pages: jpg[i] is a baseline JPEG of w[i] × h[i] pixels (RGB), scaled to fit the A4 page, centred.</summary>
        public static byte[] Build(IList<byte[]> jpg, IList<int> w, IList<int> h, string title, string producer)
        {
            var ms = new MemoryStream(); var offs = new List<long>();
            void A(string s) { var b = Encoding.ASCII.GetBytes(s); ms.Write(b, 0, b.Length); }
            void Obj(int n) { while (offs.Count < n) offs.Add(0); offs[n - 1] = ms.Position; A(n + " 0 obj\n"); }
            string F(float v) => v.ToString("0.###", CultureInfo.InvariantCulture);
            int pages = jpg.Count;
            A("%PDF-1.4\n"); ms.Write(new byte[] { (byte)'%', 0xE2, 0xE3, 0xCF, 0xD3, (byte)'\n' }, 0, 6);
            // 1 catalog, 2 page tree, 3 info, then per page: the page, its content stream, its picture
            Obj(1); A("<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");
            var kids = new StringBuilder(); for (int i = 0; i < pages; i++) kids.Append(4 + i * 3).Append(" 0 R ");
            Obj(2); A("<< /Type /Pages /Kids [ " + kids + "] /Count " + pages + " >>\nendobj\n");
            Obj(3); A("<< /Title " + Utf16(title) + " /Producer " + Utf16(producer) + " >>\nendobj\n");
            for (int i = 0; i < pages; i++)
            {
                int po = 4 + i * 3, co = po + 1, io = po + 2;
                float s = System.Math.Min(PageW / w[i], PageH / h[i]), dw = w[i] * s, dh = h[i] * s, x = (PageW - dw) * 0.5f, y = (PageH - dh) * 0.5f;
                Obj(po); A("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + F(PageW) + " " + F(PageH) + "] /Resources << /XObject << /Im0 " + io + " 0 R >> >> /Contents " + co + " 0 R >>\nendobj\n");
                var content = "q " + F(dw) + " 0 0 " + F(dh) + " " + F(x) + " " + F(y) + " cm /Im0 Do Q\n";
                Obj(co); A("<< /Length " + content.Length + " >>\nstream\n" + content + "endstream\nendobj\n");
                Obj(io); A("<< /Type /XObject /Subtype /Image /Width " + w[i] + " /Height " + h[i] + " /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length " + jpg[i].Length + " >>\nstream\n");
                ms.Write(jpg[i], 0, jpg[i].Length); A("\nendstream\nendobj\n");
            }
            long xref = ms.Position; int n = offs.Count;
            A("xref\n0 " + (n + 1) + "\n0000000000 65535 f \n");
            for (int i = 0; i < n; i++) A(offs[i].ToString("D10", CultureInfo.InvariantCulture) + " 00000 n \n");
            A("trailer\n<< /Size " + (n + 1) + " /Root 1 0 R /Info 3 0 R >>\nstartxref\n" + xref + "\n%%EOF\n");
            return ms.ToArray();
        }
        /// <summary>A text string of the document properties: UTF‑16BE with the byte order mark, as hex.</summary>
        static string Utf16(string s)
        {
            var b = Encoding.BigEndianUnicode.GetBytes(s ?? ""); var sb = new StringBuilder("<FEFF");
            foreach (var x in b) sb.Append(x.ToString("X2", CultureInfo.InvariantCulture));
            return sb.Append('>').ToString();
        }
    }
}
