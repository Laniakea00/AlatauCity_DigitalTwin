using System.IO;
using UnityEditor;
using UnityEditor.Media;
using UnityEditor.SceneManagement;
using UnityEngine;
using AlatauCity.DigitalTwin;

namespace AlatauCity.EditorTools
{
    /// <summary>Pictures and films of the running scene without sitting at the editor: plays the scene, moves the camera as a spec
    /// file says, renders the main camera into a texture and saves PNGs and / or an MP4. The interface is not in the picture (it is
    /// drawn over the screen, not by the camera).
    ///   Unity.exe -batchmode -projectPath UnityProject -executeMethod AlatauCity.EditorTools.AlatauShots.Run -logFile shots.log   (no -quit)
    /// Environment: ALATAU_SHOTS = spec file (JSON, see Spec). Stills go to the folder "out"; "moves" make the film "movie".
    /// Entering Play mode reloads the scripts, so the pending job is kept in SessionState and picked up by Resume().</summary>
    public static class AlatauShots
    {
        [System.Serializable] public class Shot
        {
            public string name, view = "";        // view: a saved view of MapCamera ("Gate", "Golden", ... or "Overview"); empty = use x, z
            public float x, z, distance, yaw, pitch;   // with a view: distance / pitch replace the view's when > 0, yaw is added
            public float year = 2050;
            public float hour = -1;               // film look only: time of day, -1 = leave as is
            public int film = -1;                 // -1 = leave as is, 0 = film look off, 1 = on
            public string module = "overview";    // module of the twin to switch to (overview, construction, prediction, ...)
        }
        /// <summary>One camera move of a film: from a to b in so many seconds; grow = buildings rise while the year runs.</summary>
        [System.Serializable] public class Move { public float seconds = 5; public Shot a, b; public bool grow; }
        [System.Serializable] public class Spec
        {
            public string @out; public int width = 1920, height = 1080; public float settle = 6f; public Shot[] shots = new Shot[0];
            public string movie = ""; public int fps = 30; public Move[] moves = new Move[0];
        }

        const string Key = "AlatauShots.spec", ScenePath = "Assets/Scenes/AlatauCity.unity";

        public static void Run()
        {
            string spec = System.Environment.GetEnvironmentVariable("ALATAU_SHOTS");
            if (string.IsNullOrEmpty(spec) || !File.Exists(spec)) { Debug.LogError("[AlatauShots] set ALATAU_SHOTS to a spec file"); EditorApplication.Exit(3); return; }
            EditorSceneManager.OpenScene(ScenePath);
            SessionState.SetString(Key, spec);
            EditorApplication.EnterPlaymode();
        }

        /// <summary>Open the scene and press Play: Unity.exe -projectPath UnityProject -executeMethod AlatauCity.EditorTools.AlatauShots.Play</summary>
        public static void Play() { EditorSceneManager.OpenScene(ScenePath); EditorApplication.EnterPlaymode(); }

        [InitializeOnLoadMethod]
        static void Resume()
        {
            string path = SessionState.GetString(Key, "");
            if (path == "" || !EditorApplication.isPlayingOrWillChangePlaymode) return;
            ShaderUtil.allowAsyncCompilation = false;       // a shader still compiling would be drawn as a cyan stand-in
            double t0 = EditorApplication.timeSinceStartup; int i = -1, frame = 0; Spec spec = null; MapCamera mc = null; Camera cam = null;
            int move = 0, f = -1; MediaEncoder enc = null; Texture2D tex = null; RenderTexture rt = null;
            EditorApplication.CallbackFunction tick = null;
            tick = () =>
            {
                try
                {
                    if (!EditorApplication.isPlaying) return;
                    double el = EditorApplication.timeSinceStartup - t0;
                    if (el > 3000) { Debug.LogError("[AlatauShots] gave up after 50 minutes"); enc?.Dispose(); Finish(tick, 2); return; }
                    if (spec == null)
                    {
                        spec = JsonUtility.FromJson<Spec>(File.ReadAllText(path));
                        if (!string.IsNullOrEmpty(spec.@out)) Directory.CreateDirectory(spec.@out);
                        Application.runInBackground = true;
                    }
                    if (el < spec.settle) return;                     // the twin's data load in the background
                    if (cam == null) { cam = Camera.main; mc = cam != null ? cam.GetComponent<MapCamera>() : null; if (mc == null) return; TwinState.Playing = false; }
                    // ---- stills
                    if (i < spec.shots.Length)
                    {
                        if (i >= 0 && Time.frameCount - frame < 5) return; // a few frames for the camera, the year and the shader tables to settle
                        if (i >= 0) Save(cam, spec, spec.shots[i]);
                        if (++i < spec.shots.Length) { Aim(mc, spec.shots[i], spec.shots[i], 0f, false); frame = Time.frameCount; return; }
                        if (!string.IsNullOrEmpty(spec.@out)) File.WriteAllText(Path.Combine(spec.@out, "done.txt"), spec.shots.Length + " shots");
                    }
                    // ---- the film: one rendered frame per two played frames (the camera and the light settle in between)
                    if (string.IsNullOrEmpty(spec.movie) || move >= spec.moves.Length) { CityTimeline.StopGrowth(); enc?.Dispose(); Finish(tick, 0); return; }
                    if (enc == null)
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(spec.movie));
                        var va = new VideoTrackEncoderAttributes(new H264EncoderAttributes { gopSize = 30, numConsecutiveBFrames = 2, profile = VideoEncodingProfile.H264High })
                        { frameRate = new MediaRational(spec.fps), width = (uint)spec.width, height = (uint)spec.height, targetBitRate = 16000000 };
                        enc = new MediaEncoder(spec.movie, va);
                        tex = new Texture2D(spec.width, spec.height, TextureFormat.RGBA32, false);
                        rt = new RenderTexture(spec.width, spec.height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 8 };
                        Time.captureFramerate = spec.fps; f = -1; frame = Time.frameCount;
                    }
                    if (Time.frameCount - frame < 2) return;
                    var m = spec.moves[move]; int n = Mathf.Max(2, Mathf.RoundToInt(m.seconds * spec.fps));
                    if (f >= 0)
                    {
                        FilmLook.Instance?.Redraw();
                        var before = cam.targetTexture; cam.targetTexture = rt; cam.Render(); cam.targetTexture = before;
                        RenderTexture.active = rt; tex.ReadPixels(new Rect(0, 0, spec.width, spec.height), 0, 0); tex.Apply(false); RenderTexture.active = null;
                        enc.AddFrame(tex);
                    }
                    if (++f >= n) { Debug.Log($"[AlatauShots] move {move + 1} of {spec.moves.Length}: {n} frames"); move++; f = -1; if (move >= spec.moves.Length) return; m = spec.moves[move]; n = Mathf.Max(2, Mathf.RoundToInt(m.seconds * spec.fps)); f = 0; }
                    float t = f / (float)(n - 1);
                    Aim(mc, m.a, m.b, t, m.grow); frame = Time.frameCount;
                }
                catch (System.Exception e) { Debug.LogError("[AlatauShots] " + e); enc?.Dispose(); Finish(tick, 1); }
            };
            EditorApplication.update += tick;
        }

        static void Finish(EditorApplication.CallbackFunction tick, int code)
        {
            EditorApplication.update -= tick; SessionState.EraseString(Key);
            EditorApplication.Exit(code);
        }

        static void Resolve(MapCamera mc, Shot s, out Vector3 target, out float distance, out float yaw, out float pitch)
        {
            MapCamera.View v = null;
            if (!string.IsNullOrEmpty(s.view))
            {
                if (s.view == "Overview") v = mc.overview;
                foreach (var w in mc.views) if (w.name == s.view) v = w;
                if (v == null) Debug.LogWarning("[AlatauShots] no saved view named " + s.view);
            }
            if (v != null) { target = v.target + new Vector3(s.x, 0, s.z); distance = s.distance > 0 ? s.distance : v.distance; yaw = v.yaw + s.yaw; pitch = s.pitch > 0 ? s.pitch : v.pitch; }
            else { target = new Vector3(s.x, 0, s.z); distance = s.distance; yaw = s.yaw; pitch = s.pitch; }
        }

        /// <summary>Camera, year, module and light between two shots; t = 0..1 along the move (linear in time, eased here).</summary>
        static void Aim(MapCamera mc, Shot a, Shot b, float t, bool grow)
        {
            float e = t * t * (3f - 2f * t);
            FilmTrees.Sync = true;                                                          // a picture needs every tree in place, not a few cells per frame
            Resolve(mc, a, out var ta, out float da, out float ya, out float pa); Resolve(mc, b, out var tb, out float db, out float yb, out float pb);
            mc.target = Vector3.Lerp(ta, tb, e); mc.distance = Mathf.Exp(Mathf.Lerp(Mathf.Log(da), Mathf.Log(db), e)); mc.yaw = Mathf.Lerp(ya, yb, e); mc.pitch = Mathf.Lerp(pa, pb, e);
            TwinState.SetModule(string.IsNullOrEmpty(a.module) ? "overview" : a.module);
            float year = Mathf.Lerp(a.year, b.year, t);                                   // the years run evenly
            TwinState.Year = Mathf.FloorToInt(year + 1e-4f);
            if (grow && year < TwinState.MaxYear) CityTimeline.Growth(year); else CityTimeline.StopGrowth();
            var look = Object.FindFirstObjectByType<FilmLook>();
            if (look != null)
            {
                if (a.film >= 0) look.on = a.film > 0;
                if (a.hour >= 0) look.hour = b.hour >= 0 ? Mathf.Lerp(a.hour, b.hour, e) : a.hour;
            }
        }

        static void Save(Camera cam, Spec spec, Shot s)
        {
            var rt = new RenderTexture(spec.width, spec.height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 8 };
            FilmLook.Instance?.Redraw();
            var before = cam.targetTexture; cam.targetTexture = rt; cam.Render(); cam.targetTexture = before;
            RenderTexture.active = rt;
            var tex = new Texture2D(spec.width, spec.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, spec.width, spec.height), 0, 0); tex.Apply();
            RenderTexture.active = null;
            string file = Path.Combine(spec.@out, s.name + ".png");
            File.WriteAllBytes(file, tex.EncodeToPNG());
            Object.DestroyImmediate(tex); rt.Release(); Object.DestroyImmediate(rt);
            Debug.Log($"[AlatauShots] {s.name}: camera {cam.transform.position} year {TwinState.Year} -> {file}");
        }
    }
}
