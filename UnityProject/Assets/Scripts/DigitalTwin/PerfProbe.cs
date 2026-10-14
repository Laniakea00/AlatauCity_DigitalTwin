using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Unity.Profiling;
using Unity.Profiling.LowLevel.Unsafe;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Performance probe: F11 records 8 seconds of frames and writes a report to Logs/perf_*.txt next to the project —
    /// frame time (CPU main thread, render thread, GPU), draw calls, batches, triangles, shadow casters, garbage per frame, and the
    /// profiler markers (scripts, rendering, UI) that take the most time. Works in the Editor and in development builds.</summary>
    public class PerfProbe : MonoBehaviour
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (FindFirstObjectByType<PerfProbe>() == null) { var g = new GameObject("Perf probe"); DontDestroyOnLoad(g); g.AddComponent<PerfProbe>(); } }

        const float Span = 8f;
        bool rec; float t; int frames;
        readonly List<float> frameMs = new List<float>(), gpuMs = new List<float>(), cpuMs = new List<float>();
        class M { public string Cat, Name; public ProfilerRecorder R; public double Sum; public long Max; }
        readonly List<M> markers = new List<M>();
        ProfilerRecorder mainT, renderT, batches, setPass, draws, tris, verts, gc, shadowCasters;
        double sBatches, sSetPass, sDraws, sTris, sVerts, sGc, sMain, sRender, sShadow;
        readonly FrameTiming[] ft = new FrameTiming[1];
        public static bool Recording { get; private set; }

        void Update()
        {
            if (!rec && Input.GetKeyDown(KeyCode.F11)) Begin();
            if (!rec) return;
            t += Time.unscaledDeltaTime; frames++;
            frameMs.Add(Time.unscaledDeltaTime * 1000f);
            FrameTimingManager.CaptureFrameTimings();
            if (FrameTimingManager.GetLatestTimings(1, ft) > 0) { gpuMs.Add((float)ft[0].gpuFrameTime); cpuMs.Add((float)ft[0].cpuFrameTime); }
            foreach (var m in markers) { long v = m.R.LastValue; m.Sum += v; if (v > m.Max) m.Max = v; }
            sMain += mainT.LastValue; sRender += renderT.LastValue; sBatches += batches.LastValue; sSetPass += setPass.LastValue; sDraws += draws.LastValue;
            sTris += tris.LastValue; sVerts += verts.LastValue; sGc += gc.LastValue; sShadow += shadowCasters.LastValue;
            if (t >= Span) Finish();
        }

        void Begin()
        {
            rec = true; Recording = true; t = 0f; frames = 0; frameMs.Clear(); gpuMs.Clear(); cpuMs.Clear();
            sBatches = sSetPass = sDraws = sTris = sVerts = sGc = sMain = sRender = sShadow = 0;
            mainT = ProfilerRecorder.StartNew(ProfilerCategory.Internal, "Main Thread", 1);
            renderT = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Render Thread", 1);
            batches = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Batches Count");
            setPass = ProfilerRecorder.StartNew(ProfilerCategory.Render, "SetPass Calls Count");
            draws = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Draw Calls Count");
            tris = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Triangles Count");
            verts = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Vertices Count");
            shadowCasters = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Shadow Casters Count");
            gc = ProfilerRecorder.StartNew(ProfilerCategory.Memory, "GC Allocated In Frame");
            markers.Clear();
            var hs = new List<ProfilerRecorderHandle>(); ProfilerRecorderHandle.GetAvailable(hs);
            foreach (var h in hs)
            {
                var d = ProfilerRecorderHandle.GetDescription(h);
                if (d.UnitType != ProfilerMarkerDataUnit.TimeNanoseconds) continue;
                string cat = d.Category.Name;
                markers.Add(new M { Cat = cat, Name = d.Name, R = new ProfilerRecorder(h, 1, ProfilerRecorderOptions.Default) });
            }
            foreach (var m in markers) m.R.Start();
            Debug.Log("[Alatau] замер производительности: 8 с, " + markers.Count + " маркеров");
        }

        void Finish()
        {
            rec = false; Recording = false;
            var sb = new StringBuilder();
            float Avg(List<float> l) => l.Count > 0 ? l.Average() : 0f;
            float P(List<float> l, float q) { if (l.Count == 0) return 0f; var s = l.OrderBy(x => x).ToList(); return s[Mathf.Clamp(Mathf.RoundToInt(q * (s.Count - 1)), 0, s.Count - 1)]; }
            int n = Mathf.Max(frames, 1);
            sb.AppendLine($"Alatau City perf {System.DateTime.Now:yyyy-MM-dd HH:mm:ss}  scene={UnityEngine.SceneManagement.SceneManager.GetActiveScene().name}");
            sb.AppendLine($"screen {Screen.width}x{Screen.height}  quality={QualitySettings.names[QualitySettings.GetQualityLevel()]}  vsync={QualitySettings.vSyncCount}  msaa={QualitySettings.antiAliasing}  shadows={QualitySettings.shadows} res={QualitySettings.shadowResolution} dist={QualitySettings.shadowDistance} cascades={QualitySettings.shadowCascades}  lodBias={QualitySettings.lodBias}  pixelLights={QualitySettings.pixelLightCount}");
            sb.AppendLine($"gpu {SystemInfo.graphicsDeviceName} ({SystemInfo.graphicsDeviceType}, {SystemInfo.graphicsMemorySize} MB)  cpu {SystemInfo.processorType} x{SystemInfo.processorCount}");
            sb.AppendLine($"frames {frames} in {t:F1} s  fps {frames / Mathf.Max(t, 0.01f):F1}  frame avg {Avg(frameMs):F1} ms  p95 {P(frameMs, 0.95f):F1}  max {(frameMs.Count > 0 ? frameMs.Max() : 0):F1}");
            sb.AppendLine($"cpu frame (timing) {Avg(cpuMs):F1} ms  gpu frame {Avg(gpuMs):F1} ms (p95 {P(gpuMs, 0.95f):F1})  main thread {sMain / n * 1e-6:F1} ms  render thread {sRender / n * 1e-6:F1} ms");
            sb.AppendLine($"batches {sBatches / n:F0}  setpass {sSetPass / n:F0}  drawcalls {sDraws / n:F0}  tris {sTris / n / 1e6:F2} M  verts {sVerts / n / 1e6:F2} M  shadow casters {sShadow / n:F0}  gc/frame {sGc / n / 1024:F1} KB");
            // scene contents
            var rs = FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            int act = 0, shad = 0; long triTotal = 0;
            var big = new List<(string, long, bool)>();
            foreach (var r in rs)
            {
                if (!r.enabled || !r.gameObject.activeInHierarchy) continue; act++;
                if (r.shadowCastingMode != UnityEngine.Rendering.ShadowCastingMode.Off) shad++;
                var mf = r.GetComponent<MeshFilter>(); var mesh = mf != null ? mf.sharedMesh : null;
                if (mesh != null) { long tc = 0; for (int s = 0; s < mesh.subMeshCount; s++) tc += mesh.GetIndexCount(s) / 3; triTotal += tc; big.Add((Path(r.transform), tc, r.shadowCastingMode != UnityEngine.Rendering.ShadowCastingMode.Off)); }
            }
            sb.AppendLine($"renderers active {act} (of {rs.Length})  casting shadows {shad}  mesh triangles in scene {triTotal / 1e6:F2} M");
            foreach (var c in Camera.allCameras) sb.AppendLine($"camera {c.name} depth {c.depth} target {(c.targetTexture != null ? c.targetTexture.width + "x" + c.targetTexture.height : "screen")} hdr {c.allowHDR} msaa {c.allowMSAA} far {c.farClipPlane} mask {c.cullingMask}");
            foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None)) if (l.enabled) sb.AppendLine($"light {l.name} {l.type} shadows {l.shadows} res {l.shadowResolution}");
            sb.AppendLine("--- largest meshes (triangles, shadows)");
            foreach (var b in big.OrderByDescending(x => x.Item2).Take(25)) sb.AppendLine($"{b.Item2,10}  {(b.Item3 ? "S" : " ")}  {b.Item1}");
            sb.AppendLine("--- markers by average ms per frame (category, avg, max)");
            foreach (var m in markers.Where(m => m.Sum > 0).OrderByDescending(m => m.Sum).Take(90))
                sb.AppendLine($"{m.Sum / n * 1e-6,8:F2} ms  max {m.Max * 1e-6,7:F2}  [{m.Cat}] {m.Name}");
            foreach (var m in markers) m.R.Dispose(); markers.Clear();
            mainT.Dispose(); renderT.Dispose(); batches.Dispose(); setPass.Dispose(); draws.Dispose(); tris.Dispose(); verts.Dispose(); gc.Dispose(); shadowCasters.Dispose();
            string dir = System.IO.Path.Combine(Application.dataPath, "..", "Logs"); Directory.CreateDirectory(dir);
            string file = System.IO.Path.Combine(dir, $"perf_{System.DateTime.Now:HHmmss}.txt");
            File.WriteAllText(file, sb.ToString());
            Debug.Log("[Alatau] замер записан: " + file);
        }
        static string Path(Transform t) { var s = t.name; for (int i = 0; i < 3 && t.parent != null; i++) { t = t.parent; s = t.name + "/" + s; } return s; }
    }
}
