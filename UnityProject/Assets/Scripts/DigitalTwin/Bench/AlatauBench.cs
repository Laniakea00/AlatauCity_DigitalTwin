using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Unity.Profiling;
using UnityEngine;
using UnityEngine.LowLevel;
using UnityEngine.Profiling;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace AlatauCity.DigitalTwin
{
    /// <summary>Speed baseline of the site (bench mode, the level 0 / level 4 gate of the map redraw). It exists only with bench=1 in the
    /// page URL (WebGL), -bench on the command line (Windows player) or AlatauBench.Run() (editor, e.g. ShotRig "invoke
    /// AlatauCity.DigitalTwin.AlatauBench Run"); otherwise nothing is created and nothing runs. Once the twin has loaded and settled it
    /// visits the ten fixed views of the table below, the same every run. At each view it sets the camera, year, module and hour, waits
    /// 4 s, then samples 6 s of frames: the time between frames (avg, p50, p95, max), the main-thread work of each frame, memory (Unity,
    /// Mono; in the browser also the JS heap and the wasm heap), what the city draws (cars, people, lamp posts, building chunks) and the
    /// render counters. Results: window.__alatau.bench through AlatauBench.jslib (and one JSON line in the console), read by
    /// tools/webgl_check. At the end the year, scenario, module, hour and camera are given back.</summary>
    [DefaultExecutionOrder(6000)]   // Update after the map camera: a street-level view puts the camera at its exact eye before anything reads it
    public class AlatauBench : MonoBehaviour
    {
        // ------------------------------------------------------------------ the ten views (fixed: never change them, or the baseline is lost)
        /// <summary>The map camera looks at (X, Z), the point Lift metres above the ground, from Dist metres, Yaw clockwise from north,
        /// Pitch down from the horizon (the map camera's own terms). A pitch under 8° or an eye under 30 m above the ground (the map
        /// camera's floor) is a street-level view: the camera is put at the exact eye, as the film reel does.</summary>
        struct View { public string Id, Source, Module; public int Year; public float Hour, X, Z, Lift, Dist, Yaw, Pitch; }
        static View V(string id, string module, int year, float hour, float x, float z, float lift, float dist, float yaw, float pitch, string source)
            => new View { Id = id, Module = module, Year = year, Hour = hour, X = x, Z = z, Lift = lift, Dist = dist, Yaw = yaw, Pitch = pitch, Source = source };
        static readonly View[] Views = {
            //  id                  module          year  hour     X        Z     lift   dist    yaw    pitch  where the values come from
            V("city_high",         "overview",     2050, 13.0f,    13f,  -5628f,  0f, 69914f,   -6f,  42f,   "city_meta.json camera 'Overview from the south' = the Home view (MapCamera.overview)"),
            V("gate_wide",         "overview",     2050, 13.0f, -2309f, -19036f,  0f,  3636f,   25f,  24f,   "city_meta.json camera 'Gate District 2050' = the start view and key 1"),
            V("iconic_street",     "overview",     2050, 15.0f, -3130f + Dx, -19000f + Dz,  8f,   184f, -135f,  -0.6f, "ShotRig ic_street: eye 6 m up at -3000,-18870 to the plaza, flags and tower (Iconic-local 210,6,-170 -> 80,8,-40, yaw 270)"),
            V("gate_dusk_street",  "overview",     2050, 18.5f, -2090f, -18450f,  3f,   215f,    5f,  12f,   "FilmReel 'avenue': eye 46 m over the Gate trunk road at -2110,-18550, 210 m ahead, heading 5 deg; dusk 18.5 as in the stage-3 shots"),
            V("gate_night",        "overview",     2050, 21.0f, -3170f + Dx, -19080f + Dz,  0f,  1500f,   30f,  38f,   "stage-3 fixed camera gate_map (view -3170 -19080 1500 30 38) at night 21:00"),
            V("golden_uni",        "overview",     2050, 13.0f, -1300f, -12300f,  0f,   600f,  200f,  30f,   "stage-3 fixed camera golden_close (view -1300 -12300 600 200 30), KAIST campus"),
            V("growing_industry",  "overview",     2050, 13.0f,  7300f,    500f,  0f,  4300f,   62f,  34f,   "TwinTour step 'Dolina zavodov' (industrial belts): start of its glide"),
            V("green_shore",       "overview",     2050, 13.0f,  9693f,  18671f,  0f,  3696f, -150f,  24f,   "city_meta.json camera 'Green waterfront 2050' = key 4, the Kapchagay shore"),
            V("lrt_viaduct",       "overview",     2050, 13.0f, -2455f, -16115f, 10f,   380f,   40f,  14f,   "lrt_routes.json trunk point 109, between the Gate-Golden stations at z -16864 and -15322; deck about 9 m up"),
            V("construction_2034", "construction", 2034, 13.0f, -3200f, -23500f,  0f,  9500f,    8f,  52f,   "TwinTour step 'Kontrol stroyki' (construction, plan vs actual): start of its glide, year 2034"),
        };
        // the two views of Iconic and its quarter follow the complex (moved rigidly in stage 7 by (Dx, Dz), LandmarkData): they keep
        // showing the same plaza and quarter, so their figures stay comparable with the baseline
        const float Dx = Landmarks.IconicFrame.Dx, Dz = Landmarks.IconicFrame.Dz;
        const float ReadyCap = 180f, Settle = 5f, Wait = 4f, Sample = 6f;
        const int MaxFrames = 8192;                       // 6 s at up to ~1300 fps: allocated once

        // ------------------------------------------------------------------ the browser side (Plugins/WebGL/AlatauBench.jslib)
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void AlatauBenchPush(string kind, string json);
#else
        static void AlatauBenchPush(string kind, string json) { }
#endif
        static bool Web => Application.platform == RuntimePlatform.WebGLPlayer;

        // ------------------------------------------------------------------ start
        public static AlatauBench Instance;
        /// <summary>The bench has run through all views.</summary>
        public static bool Done { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Wanted()) Run(); }
        /// <summary>bench=1 in the page URL (WebGL) or -bench on the command line.</summary>
        static bool Wanted()
        {
            try
            {
                if (Web)
                {
                    string url = Application.absoluteURL ?? ""; int q = url.IndexOf('?'); if (q < 0) return false;
                    int h = url.IndexOf('#', q); string query = h > q ? url.Substring(q + 1, h - q - 1) : url.Substring(q + 1);
                    foreach (var p in query.Split('&')) if (p == "bench=1") return true;
                    return false;
                }
                foreach (var a in Environment.GetCommandLineArgs()) if (a == "-bench") return true;
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] bench: " + e.Message); }
            return false;
        }
        /// <summary>Starts the bench (once at a time).</summary>
        public static void Run() { if (Instance == null) new GameObject("Alatau bench").AddComponent<AlatauBench>(); }

        // ------------------------------------------------------------------ frame clock (two PlayerLoop entries, only while the bench runs)
        struct BenchFrameOpen { } struct BenchFrameClose { }
        static bool sampling; static int frames; static float[] gap, work; static double lastOpen, open;
        static long sDraw, sBatch, sPass, sTris, sVerts, sCars, sAlive, sPeople, sLamps; static int sMoved;
        static ProfilerRecorder rDraw, rBatch, rPass, rTris, rVerts, rGfx, rSys;

        static void FrameOpen()
        {
            double now = Time.realtimeSinceStartupAsDouble;
            if (sampling && lastOpen > 0.0 && frames < MaxFrames) gap[frames] = (float)((now - lastOpen) * 1000.0);
            lastOpen = now; open = now;
        }
        static void FrameClose()
        {
            if (!sampling || frames >= MaxFrames || lastOpen <= 0.0) return;
            if (gap[frames] <= 0f) return;                                         // the first frame of a window has no gap yet
            work[frames] = (float)((Time.realtimeSinceStartupAsDouble - open) * 1000.0);
            sDraw += Last(rDraw); sBatch += Last(rBatch); sPass += Last(rPass); sTris += Last(rTris); sVerts += Last(rVerts);
            sCars += FilmTraffic.Drawn; sAlive += FilmTraffic.Alive; sPeople += FilmLife.ShownNow; sLamps += FilmLamps.DrawnNow;
            if (MapCamera.UserMoved) sMoved++;                                     // someone moved the camera: the sample is not valid
            frames++;
        }
        static long Last(ProfilerRecorder r) => r.Valid ? r.LastValue : 0;
        static ProfilerRecorder Rec(ProfilerCategory c, string name) { try { return ProfilerRecorder.StartNew(c, name); } catch { return default; } }
        static void Drop(ref ProfilerRecorder r) { try { if (r.Valid) r.Dispose(); } catch { } r = default; }

        static bool hooked;
        static void Hook(bool on)
        {
            if (on == hooked) return; hooked = on;
            try
            {
                var loop = PlayerLoop.GetCurrentPlayerLoop(); var top = loop.subSystemList; if (top == null || top.Length == 0) return;
                int first = 0, last = top.Length - 1;
                for (int i = 0; i < top.Length; i++)
                {
                    if (top[i].type == typeof(UnityEngine.PlayerLoop.EarlyUpdate)) first = i;
                    if (top[i].type == typeof(UnityEngine.PlayerLoop.PostLateUpdate)) last = i;
                }
                top[first].subSystemList = Edit(top[first].subSystemList, typeof(BenchFrameOpen), on ? FrameOpen : (PlayerLoopSystem.UpdateFunction)null, true);
                top[last].subSystemList = Edit(top[last].subSystemList, typeof(BenchFrameClose), on ? FrameClose : (PlayerLoopSystem.UpdateFunction)null, false);
                loop.subSystemList = top; PlayerLoop.SetPlayerLoop(loop);
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] bench: frame clock " + e.Message); }
        }
        static PlayerLoopSystem[] Edit(PlayerLoopSystem[] list, Type t, PlayerLoopSystem.UpdateFunction fn, bool atStart)
        {
            var l = new List<PlayerLoopSystem>(); if (list != null) foreach (var s in list) if (s.type != t) l.Add(s);
            if (fn != null) { var me = new PlayerLoopSystem { type = t, updateDelegate = fn }; if (atStart) l.Insert(0, me); else l.Add(me); }
            return l.ToArray();
        }

        // ------------------------------------------------------------------ the run
        MapCamera mc; Camera cam; bool street, posed; View cur; Vector3 eye, look;
        Renderer[] chunks = new Renderer[0];
        readonly List<string> results = new List<string>();
        float[] sorted;
        // the scene before the bench, given back at the end
        int year0; Scenario sc0; string module0; float hour0; bool cycling0, viewer0, film0, holdLift0; Vector3 tgt0; float dist0, yaw0, pitch0;

        void Awake() { Instance = this; Done = false; DontDestroyOnLoad(gameObject); }
        void OnDestroy() { if (Instance == this) Instance = null; sampling = false; Hook(false); DropAll(); }
        static void DropAll() { Drop(ref rDraw); Drop(ref rBatch); Drop(ref rPass); Drop(ref rTris); Drop(ref rVerts); Drop(ref rGfx); Drop(ref rSys); }

        IEnumerator Start()
        {
            var ci = CultureInfo.InvariantCulture; float t0 = Time.realtimeSinceStartup;
            Push("start", string.Format(ci, "{{\"version\":1,\"state\":\"waiting\",\"unity\":\"{0}\",\"platform\":\"{1}\",\"unityGpu\":\"{2}\",\"gfxApi\":\"{3}\",\"quality\":\"{4}\",\"targetFrameRate\":{5},\"settleS\":{6},\"waitS\":{7},\"sampleS\":{8},\"viewCount\":{9}}}",
                Esc(Application.unityVersion), Application.platform, Esc(SystemInfo.graphicsDeviceName), Esc(SystemInfo.graphicsDeviceVersion),
                Esc(QualitySettings.names.Length > 0 ? QualitySettings.names[QualitySettings.GetQualityLevel()] : ""), Application.targetFrameRate, Settle, Wait, Sample, Views.Length));
            // 1. the twin has loaded: data, statistics, landmarks, film roads, interface, camera (at most 3 min)
            string missing = Missing();
            while (missing != null && Time.realtimeSinceStartup - t0 < ReadyCap) { yield return null; missing = Missing(); }
            float ready = Time.realtimeSinceStartup;
            // 2. the first frames settle
            yield return new WaitForSecondsRealtime(Settle);
            cam = Camera.main; mc = cam != null ? cam.GetComponent<MapCamera>() : null;
            if (mc == null) { Push("done", "{\"state\":\"failed\",\"error\":\"no map camera\"}"); Done = true; yield break; }
            foreach (var b in FindObjectsByType<BuildingChunk>(FindObjectsSortMode.None)) { var r = b.GetComponent<Renderer>(); if (r != null) { Array.Resize(ref chunks, chunks.Length + 1); chunks[chunks.Length - 1] = r; } }
            Save();
            gap = new float[MaxFrames]; work = new float[MaxFrames]; sorted = new float[MaxFrames];
            rDraw = Rec(ProfilerCategory.Render, "Draw Calls Count"); rBatch = Rec(ProfilerCategory.Render, "Batches Count"); rPass = Rec(ProfilerCategory.Render, "SetPass Calls Count");
            rTris = Rec(ProfilerCategory.Render, "Triangles Count"); rVerts = Rec(ProfilerCategory.Render, "Vertices Count");
            rGfx = Rec(ProfilerCategory.Memory, "Gfx Used Memory"); rSys = Rec(ProfilerCategory.Memory, "System Used Memory");
            Hook(true);
            Push("state", string.Format(ci, "{{\"state\":\"running\",\"readySeconds\":{0:0.0},\"notReady\":\"{1}\",\"screen\":\"{2}x{3}\",\"buildingChunks\":{4}}}",
                ready, Esc(missing ?? ""), Screen.width, Screen.height, chunks.Length));
            if (missing != null) Debug.LogWarning("[Alatau] bench: not fully loaded after " + ReadyCap + " s (" + missing + "), going on");
            // 3. the views
            float tRun = Time.realtimeSinceStartup;
            for (int i = 0; i < Views.Length; i++)
            {
                var v = Views[i];
                try { Apply(v); } catch (Exception e) { Debug.LogWarning("[Alatau] bench: view " + v.Id + ": " + e.Message); }
                yield return new WaitForSecondsRealtime(Wait);
                int gc0 = GC.CollectionCount(0);
                Begin(); float s0 = Time.realtimeSinceStartup;
                yield return new WaitForSecondsRealtime(Sample);
                sampling = false; float secs = Time.realtimeSinceStartup - s0;
                string json; try { json = Result(i, v, secs, GC.CollectionCount(0) - gc0); } catch (Exception e) { json = string.Format(ci, "{{\"i\":{0},\"id\":\"{1}\",\"error\":\"{2}\"}}", i, v.Id, Esc(e.Message)); }
                results.Add(json); Push("view", json);
            }
            // 4. the end: the scene back as it was, one line with everything
            Hook(false); DropAll(); street = false; posed = false;
            try { Restore(); } catch (Exception e) { Debug.LogWarning("[Alatau] bench: restore " + e.Message); }
            string done = string.Format(ci, "{{\"state\":\"done\",\"runSeconds\":{0:0.0},\"totalSeconds\":{1:0.0},\"summary\":{2}}}", Time.realtimeSinceStartup - tRun, Time.realtimeSinceStartup, Summary());
            Push("done", done);
            if (!Web) Debug.Log("[Alatau] bench " + done.Substring(0, done.Length - 1) + ",\"views\":[" + string.Join(",", results) + "]}");
            Done = true;
            Destroy(gameObject);
        }

        /// <summary>Null when the twin is ready for the bench, else what is still missing.</summary>
        static string Missing()
        {
            var c = Camera.main;
            if (c == null || c.GetComponent<MapCamera>() == null) return "camera";
            if (!Data.TwinData.Ready) return "twin data";
            if (!CityStats.Ready) return "city stats";
            if (Landmarks.LandmarkSystem.Instance == null || !Landmarks.LandmarkSystem.Instance.Ready) return "landmarks";
            if (FilmRoads.WayCount == 0) return "film roads";
            if (UI.TwinUI.Instance == null) return "interface";
            return null;
        }

        void Save()
        {
            year0 = TwinState.Year; sc0 = TwinState.Scenario; module0 = TwinState.Module;
            hour0 = FilmLook.Hour; cycling0 = FilmLook.Cycling; viewer0 = FilmLook.ViewerTime; film0 = FilmLook.Instance == null || FilmLook.Instance.on;
            holdLift0 = mc.holdLift; tgt0 = mc.target; dist0 = mc.distance; yaw0 = mc.yaw; pitch0 = mc.pitch;
        }
        void Restore()
        {
            if (TwinState.Scenario != sc0) TwinState.Scenario = sc0;
            TwinState.Year = year0; TwinState.SetModule(module0);
            if (FilmLook.Instance != null) { FilmLook.Instance.hour = hour0; FilmLook.Instance.on = film0; FilmLook.Cycling = cycling0; FilmLook.ViewerTime = viewer0; }
            if (mc != null) { mc.holdLift = holdLift0; mc.SetPose(tgt0, dist0, yaw0, pitch0, 0f); }
        }

        /// <summary>Sets one view: no tour, film or selection; base scenario, the view's year, module and hour, the camera held still.</summary>
        void Apply(View v)
        {
            if (TwinTour.Running) TwinTour.Instance.Stop();
            if (FilmReel.Playing) FilmReel.Stop();
            if (Landmarks.IconicMonitor.Open) Landmarks.IconicMonitor.Instance.Close();
            if (Landmarks.IconicInterior.Active) Landmarks.IconicInterior.Instance.ExitNow();
            var ls = Landmarks.LandmarkSystem.Instance; if (ls != null && ls.Selected != null) ls.Select(null, false);
            if (TwinState.Selected != null) TwinState.SetSelected(null);
            TwinState.Playing = false;
            if (TwinState.Scenario != Scenario.Base) TwinState.Scenario = Scenario.Base;
            TwinState.SetDistrict(-1);
            TwinState.SetModule(v.Module);
            TwinState.Year = v.Year;
            if (FilmLook.Instance != null) FilmLook.Instance.on = true;
            FilmLook.SetHour(v.Hour);
            // the eye: from the point looked at, back along the view direction
            look = new Vector3(v.X, CityGround.HeightAt(v.X, v.Z) + v.Lift, v.Z);
            eye = look - Quaternion.Euler(v.Pitch, v.Yaw, 0f) * Vector3.forward * v.Dist;
            float gEye = CityGround.HeightAt(eye.x, eye.z);
            if (eye.y < gEye + 2f) eye.y = gEye + 2f;
            street = v.Pitch < 8f || eye.y - gEye < 30f;
            cur = v; posed = true; Pose();
        }
        /// <summary>The map camera held at the view (a fly-to started by something else is undone at once).</summary>
        void Pose() { mc.holdLift = true; mc.SetPose(new Vector3(cur.X, 0f, cur.Z), cur.Dist, cur.Yaw, Mathf.Max(cur.Pitch, 8f), cur.Lift); Place(); }
        void Update() { if (posed && mc != null && mc.IsFlying) Pose(); if (street) Place(); }
        void Place()
        {
            if (!street || cam == null) return;
            var d = look - eye; if (d.sqrMagnitude < 1f) return;
            cam.transform.SetPositionAndRotation(eye, Quaternion.LookRotation(d, Vector3.up));
        }

        static void Begin()
        {
            frames = 0; Array.Clear(gap, 0, gap.Length); Array.Clear(work, 0, work.Length);
            sDraw = sBatch = sPass = sTris = sVerts = sCars = sAlive = sPeople = sLamps = 0; sMoved = 0;
            lastOpen = 0.0; sampling = true;
        }

        // ------------------------------------------------------------------ numbers
        string Result(int i, View v, float secs, int gcs)
        {
            var ci = CultureInfo.InvariantCulture; int n = frames; var sb = new StringBuilder(1024);
            float avg = 0f, mx = 0f, wavg = 0f; int over = 0;
            for (int k = 0; k < n; k++) { avg += gap[k]; wavg += work[k]; if (gap[k] > mx) mx = gap[k]; if (gap[k] > 1000f / 30f) over++; }
            if (n > 0) { avg /= n; wavg /= n; }
            float p50 = Pct(gap, n, 0.50f), p95 = Pct(gap, n, 0.95f), p99 = Pct(gap, n, 0.99f), wp95 = Pct(work, n, 0.95f);
            int visible = 0; foreach (var r in chunks) if (r != null && r.isVisible) visible++;
            const double MB = 1048576.0; double fn = Mathf.Max(n, 1);
            sb.Append('{');
            sb.AppendFormat(ci, "\"i\":{0},\"id\":\"{1}\",\"module\":\"{2}\",\"year\":{3},\"hour\":{4:0.0},\"x\":{5:0},\"z\":{6:0},\"lift\":{7:0.0},\"dist\":{8:0},\"yaw\":{9:0.0},\"pitch\":{10:0.0},\"street\":{11},",
                i, v.Id, v.Module, v.Year, v.Hour, v.X, v.Z, v.Lift, v.Dist, v.Yaw, v.Pitch, street ? "true" : "false");
            sb.AppendFormat(ci, "\"frames\":{0},\"seconds\":{1:0.00},\"fps\":{2:0.0},\"avgMs\":{3:0.00},\"p50Ms\":{4:0.00},\"p95Ms\":{5:0.00},\"p99Ms\":{6:0.00},\"maxMs\":{7:0.00},\"over33ms\":{8},\"cpuAvgMs\":{9:0.00},\"cpuP95Ms\":{10:0.00},\"gcCollections\":{11},\"userMovedFrames\":{12},",
                n, secs, avg > 0f ? 1000f / avg : 0f, avg, p50, p95, p99, mx, over, wavg, wp95, gcs, sMoved);
            sb.AppendFormat(ci, "\"unityAllocatedMB\":{0:0.0},\"unityReservedMB\":{1:0.0},\"monoUsedMB\":{2:0.0},\"monoHeapMB\":{3:0.0},\"gfxUsedMB\":{4:0.0},\"systemUsedMB\":{5:0.0},",
                Profiler.GetTotalAllocatedMemoryLong() / MB, Profiler.GetTotalReservedMemoryLong() / MB, Profiler.GetMonoUsedSizeLong() / MB, Profiler.GetMonoHeapSizeLong() / MB,
                rGfx.Valid ? rGfx.LastValue / MB : -1.0, rSys.Valid ? rSys.LastValue / MB : -1.0);
            sb.AppendFormat(ci, "\"cars\":{0:0},\"carsAlive\":{1:0},\"people\":{2:0},\"lamps\":{3:0},\"buildingChunksVisible\":{4},\"buildingChunks\":{5},\"buildingsStanding\":{6},",
                sCars / fn, sAlive / fn, sPeople / fn, sLamps / fn, visible, chunks.Length, CityStats.Ready ? CityStats.Count(-1, v.Year) : -1);
            sb.AppendFormat(ci, "\"drawCalls\":{0:0},\"batches\":{1:0},\"setPassCalls\":{2:0},\"trianglesK\":{3:0.0},\"verticesK\":{4:0.0},\"source\":\"{5}\"",
                rDraw.Valid ? sDraw / fn : -1, rBatch.Valid ? sBatch / fn : -1, rPass.Valid ? sPass / fn : -1, rTris.Valid ? sTris / fn / 1000.0 : -1, rVerts.Valid ? sVerts / fn / 1000.0 : -1, Esc(v.Source));
            sb.Append('}');
            // for the summary
            sumAvg += avg; sumP95 += p95; if (p95 > worstP95) worstP95 = p95; if (mx > worstMax) worstMax = mx; nViews++;
            float res = Profiler.GetTotalReservedMemoryLong() / (float)MB; if (res > peakReserved) peakReserved = res;
            return sb.ToString();
        }
        float sumAvg, sumP95, worstP95, worstMax, peakReserved; int nViews;
        string Summary() => string.Format(CultureInfo.InvariantCulture, "{{\"views\":{0},\"meanAvgMs\":{1:0.00},\"meanP95Ms\":{2:0.00},\"worstP95Ms\":{3:0.00},\"worstMaxMs\":{4:0.00},\"peakUnityReservedMB\":{5:0.0}}}",
            nViews, nViews > 0 ? sumAvg / nViews : 0f, nViews > 0 ? sumP95 / nViews : 0f, worstP95, worstMax, peakReserved);

        /// <summary>The q-quantile of the first n values (nearest rank), sorted in the scratch buffer.</summary>
        float Pct(float[] a, int n, float q)
        {
            if (n <= 0) return 0f;
            Array.Copy(a, sorted, n); Array.Sort(sorted, 0, n);
            int k = Mathf.Clamp(Mathf.CeilToInt(q * n) - 1, 0, n - 1); return sorted[k];
        }
        static string Esc(string s) => string.IsNullOrEmpty(s) ? "" : s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", " ");
        static void Push(string kind, string json) { if (!Web) return; try { AlatauBenchPush(kind, json); } catch (Exception e) { Debug.LogWarning("[Alatau] bench: " + e.Message); } }
    }
}
