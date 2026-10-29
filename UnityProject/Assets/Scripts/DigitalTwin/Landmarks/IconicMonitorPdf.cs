using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.UIElements;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The weekly report as a PDF with one button: the paper of «Недельный отчёт» is photographed from the screen piece by piece
    /// while it scrolls (only the paper, cropped to its bounds: the rest of the window stays out), the pieces are joined, cut into A4
    /// sheets at blank lines and written as JPEG pages (MonitorPdf). WebGL: the browser downloads the file; Windows and the editor: it is
    /// saved to Documents\AlatauTwin and opened.</summary>
    public partial class IconicMonitor
    {
        Button pdfHead, pdfRep; Label ctlPdfNote; bool pdfBusy;
        static readonly Color32 PaperC = new Color32(246, 244, 239, 255);           // .an-paper background

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void AlatauDownloadFile(string name, byte[] data, int length, string mime);
#endif

        /// <summary>Makes the PDF of the weekly report of the week chosen (opens Контроль → Недельный отчёт first).</summary>
        public void ExportPdf() { if (!pdfBusy && open && isActiveAndEnabled) StartCoroutine(PdfRun()); }
        void PdfButtons(string text, bool busy)
        {
            foreach (var b in new[] { pdfHead, pdfRep })
            {
                if (b == null) continue; b.SetEnabled(!busy);
                var l = b.Q<Label>(); if (l != null) l.text = text ?? (b == pdfHead ? "Отчёт PDF" : "Скачать PDF");
            }
        }
        void PdfNote(string t)
        {
            if (ctlPdfNote == null) return;
            ctlPdfNote.text = t ?? ""; ctlPdfNote.style.display = string.IsNullOrEmpty(t) ? DisplayStyle.None : DisplayStyle.Flex;
        }
        IEnumerator PdfRun()
        {
            pdfBusy = true; PdfButtons("Готовлю PDF…", true); PdfNote(null);
            if (tab != TCtl || ctlView != 1) CtlView(1);
            yield return null; yield return null;
            var rows = new List<Color32[]>(); int W = 0; bool done = false;
            var sv = ctlRepScroll; var paper = ctlRepPaper;
            float e = Report - ctlWeek * 7f / 365f;
            if (sv != null && paper != null && paper.panel != null)
            {
                sv.scrollOffset = Vector2.zero;
                yield return null; yield return null;
                float covered = 0f;
                for (int it = 0; it < 40 && open && paper.panel != null; it++)
                {
                    yield return new WaitForEndOfFrame();
                    var tex = new Texture2D(Mathf.Max(Screen.width, 8), Mathf.Max(Screen.height, 8), TextureFormat.RGB24, false);       // the screen at the end of the frame
                    tex.ReadPixels(new Rect(0f, 0f, tex.width, tex.height), 0, 0, false); tex.Apply(false);
                    if (tex == null) break;
                    float k = tex.height / Mathf.Max(paper.panel.visualTree.layout.height, 1f);
                    var pb = paper.worldBound; var vb = sv.contentViewport.worldBound;
                    float from = Mathf.Max(pb.yMin + covered, vb.yMin), bot = Mathf.Min(pb.yMax, vb.yMax);
                    int x0 = Mathf.Clamp(Mathf.RoundToInt(pb.xMin * k), 0, tex.width - 1), x1 = Mathf.Clamp(Mathf.RoundToInt(pb.xMax * k), x0 + 1, tex.width);
                    if (W == 0) W = x1 - x0;
                    int y0 = Mathf.RoundToInt(from * k), y1 = Mathf.RoundToInt(bot * k), n = Mathf.Min(W, tex.width - x0);
                    float was = covered;
                    if (y1 > y0)
                    {
                        var px = tex.GetPixels32();
                        for (int y = y0; y < y1; y++)
                        {
                            int ty = tex.height - 1 - y; if (ty < 0 || ty >= tex.height) continue;     // the screen picture is bottom-up
                            var row = new Color32[W]; Array.Copy(px, ty * tex.width + x0, row, 0, n); rows.Add(row);
                        }
                        covered = bot - pb.yMin;
                    }
                    Destroy(tex);
                    if (covered >= pb.height - 1f) { done = true; break; }
                    if (covered <= was + 0.5f) break;                                           // no progress: the paper cannot scroll further
                    // the first line not taken yet goes to the top of the viewport
                    sv.scrollOffset = new Vector2(0f, sv.scrollOffset.y + (pb.yMin + covered - vb.yMin));
                    yield return null;
                }
                sv.scrollOffset = Vector2.zero;
            }
            string msg;
            if (rows.Count < 20 || W < 50) msg = "Не удалось снять отчёт с экрана — попробуйте ещё раз.";
            else
            {
                if (!done) Debug.LogWarning("[Alatau] weekly report PDF: the paper was taken only in part");
                var bytes = PdfPages(rows, W, $"Еженедельный отчёт · {L.Name} · неделя {WeekNo(e)}");
                string name = $"Отчёт_{L.Short.Replace(' ', '_')}_{Day(e)}.pdf";
                try { msg = SavePdf(bytes, name); }
                catch (Exception ex) { Debug.LogWarning("[Alatau] weekly report PDF: " + ex.Message); msg = "Не удалось сохранить PDF: " + ex.Message; }
            }
            PdfButtons(null, false); PdfNote(msg); pdfBusy = false;
        }
        /// <summary>The rows of the paper (top first, W pixels each) on A4 sheets: a sheet ends at a blank line near its bottom, the sheets after
        /// the first get a top margin; every sheet a JPEG; then the PDF.</summary>
        static byte[] PdfPages(List<Color32[]> rows, int W, string title)
        {
            int ph = Mathf.RoundToInt(W * MonitorPdf.PageH / MonitorPdf.PageW), m = Mathf.RoundToInt(W * 0.05f);
            var jpg = new List<byte[]>(); var ws = new List<int>(); var hs = new List<int>();
            var buf = new Color32[W * ph];
            int start = 0, total = rows.Count;
            while (start < total && jpg.Count < 40)
            {
                int tm = jpg.Count == 0 ? 0 : m, cap = ph - tm - m, end = Mathf.Min(start + cap, total);
                if (end < total) for (int r = end; r > start + cap * 0.75f; r--) if (Blank(rows[r])) { end = r; break; }
                for (int i = 0; i < buf.Length; i++) buf[i] = PaperC;
                for (int r = start; r < end; r++) Array.Copy(rows[r], 0, buf, (ph - 1 - tm - (r - start)) * W, W);
                var t = new Texture2D(W, ph, TextureFormat.RGB24, false);
                t.SetPixels32(buf); t.Apply(false);
                jpg.Add(t.EncodeToJPG(90)); ws.Add(W); hs.Add(ph);
                Destroy(t);
                start = end; while (start < total && Blank(rows[start])) start++;                 // no blank band at the top of a sheet
            }
            return MonitorPdf.Build(jpg, ws, hs, title, "QTwin · Alatau City Digital Twin");
        }
        static bool Blank(Color32[] row)
        {
            for (int i = 0; i < row.Length; i += 2)
            {
                var c = row[i];
                if (Mathf.Abs(c.r - PaperC.r) > 14 || Mathf.Abs(c.g - PaperC.g) > 14 || Mathf.Abs(c.b - PaperC.b) > 14) return false;
            }
            return true;
        }
        /// <summary>The file to the person: a download in the browser; on Windows and in the editor Documents\AlatauTwin, then opened.</summary>
        static string SavePdf(byte[] bytes, string name)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            AlatauDownloadFile(name, bytes, bytes.Length, "application/pdf");
            return $"PDF скачан: {name}";
#else
            var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "AlatauTwin");
            Directory.CreateDirectory(dir);
            var path = Path.Combine(dir, name);
            File.WriteAllBytes(path, bytes);
            Application.OpenURL("file:///" + path.Replace('\\', '/'));
            return $"PDF сохранён: {path}";
#endif
        }
    }
}
