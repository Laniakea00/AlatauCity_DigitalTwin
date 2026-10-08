using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using UnityEditor;
using UnityEngine;
using CompressionLevel = System.IO.Compression.CompressionLevel;

namespace AlatauCity.EditorTools
{
    /// <summary>
    /// Alatau City → Export ZIP for team: one archive with the Unity project (without Library/Temp/Logs/UserSettings),
    /// the Windows build, the data generators and the docs from the _package folder (context.md, startup.md, docs/).
    /// Output: next to the project folder, AlatauCity_DigitalTwin_yyyy-MM-dd.zip.
    /// </summary>
    public static class AlatauPackage
    {
        const string Root = "AlatauCity_DigitalTwin/";
        static readonly string[] ProjectDirs = { "Assets", "Packages", "ProjectSettings", "Tools" };
        static readonly string[] SkipDirs = { "Library", "Temp", "Logs", "UserSettings", "obj", ".vs", ".idea", "__pycache__", ".venv" };

        [MenuItem("Alatau City/Export ZIP for team", priority = 60)]
        public static void Export()
        {
            if (EditorApplication.isPlaying) { Debug.LogWarning("[Alatau] Stop Play mode before exporting."); return; }
            AssetDatabase.SaveAssets();
            string proj = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string outZip = Path.Combine(Path.GetFullPath(Path.Combine(proj, "..")), $"AlatauCity_DigitalTwin_{DateTime.Now:yyyy-MM-dd}.zip");

            // (source file, entry name)
            var files = new List<(string src, string entry)>();
            string pkg = Path.Combine(proj, "_package");
            if (Directory.Exists(pkg)) Collect(pkg, Root, files);
            foreach (var d in ProjectDirs)
            {
                string p = Path.Combine(proj, d);
                if (Directory.Exists(p)) Collect(p, Root + "UnityProject/" + d + "/", files);
            }
            string build = Path.Combine(proj, "Builds", "Windows");
            if (Directory.Exists(build)) Collect(build, Root + "Build_Windows/", files);

            long total = 0; foreach (var f in files) total += new FileInfo(f.src).Length;
            long done = 0; var t0 = DateTime.Now;
            try
            {
                if (File.Exists(outZip)) File.Delete(outZip);
                using (var fs = new FileStream(outZip, FileMode.CreateNew))
                using (var zip = new ZipArchive(fs, ZipArchiveMode.Create))
                {
                    var buf = new byte[1 << 20];
                    for (int i = 0; i < files.Count; i++)
                    {
                        var (src, entry) = files[i];
                        if (i % 20 == 0 && EditorUtility.DisplayCancelableProgressBar("Alatau City · ZIP", entry, total > 0 ? (float)done / total : 0f))
                            throw new OperationCanceledException();
                        // binary blobs that do not compress well → Fastest, the rest → Optimal
                        string ext = Path.GetExtension(src).ToLowerInvariant();
                        var level = ext == ".png" || ext == ".jpg" || ext == ".ress" || ext == ".dll" ? CompressionLevel.Fastest : CompressionLevel.Optimal;
                        var e = zip.CreateEntry(entry, level);
                        e.LastWriteTime = File.GetLastWriteTime(src);
                        using (var inp = new FileStream(src, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                        using (var o = e.Open())
                        {
                            int n; while ((n = inp.Read(buf, 0, buf.Length)) > 0) { o.Write(buf, 0, n); done += n; }
                        }
                    }
                }
                var size = new FileInfo(outZip).Length;
                Debug.Log($"[Alatau] ZIP OK: {outZip} · {files.Count} files · {total / 1048576f:0} MB → {size / 1048576f:0} MB · {(DateTime.Now - t0).TotalSeconds:0} s");
                EditorUtility.RevealInFinder(outZip);
            }
            catch (OperationCanceledException) { Debug.LogWarning("[Alatau] ZIP cancelled"); TryDelete(outZip); }
            catch (Exception ex) { Debug.LogError("[Alatau] ZIP failed: " + ex); TryDelete(outZip); }
            finally { EditorUtility.ClearProgressBar(); }
        }

        static void Collect(string dir, string prefix, List<(string, string)> files)
        {
            foreach (var f in Directory.GetFiles(dir)) files.Add((f, prefix + Path.GetFileName(f)));
            foreach (var d in Directory.GetDirectories(dir))
            {
                string name = Path.GetFileName(d);
                if (Array.IndexOf(SkipDirs, name) >= 0 || name.EndsWith("_BurstDebugInformation_DoNotShip")) continue;
                Collect(d, prefix + name + "/", files);
            }
        }

        static void TryDelete(string p) { try { if (File.Exists(p)) File.Delete(p); } catch { } }
    }
}
