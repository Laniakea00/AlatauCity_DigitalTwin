using UnityEditor;
using UnityEditor.Recorder;
using UnityEditor.Recorder.Encoder;
using UnityEditor.Recorder.Input;
using UnityEngine;
using AlatauCity.DigitalTwin;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.EditorTools
{
    /// <summary>Alatau City → Record film 60 s: enters Play mode, waits until the city is loaded, then starts the film reel (FilmReel) and
    /// the Unity Recorder on the same frame. The reel renders the main camera into its own 1920×1080 texture (no interface, works with the
    /// editor window hidden); the recorder writes that texture at a constant 60 fps (the scene steps 1/60 s per frame however slowly the
    /// editor renders) as H.264 MP4 at 60 fps (two frames per film frame: motion blur in post). Stops by itself after the last shot and leaves Play mode.
    /// Output: UnityProject/Recordings/Alatau_film_60s_raw.mp4 (all shots with their lead-ins; titles and cuts are put on afterwards).
    /// «Record film test» records one shot only, to check the chain.</summary>
    public static class AlatauFilmRecorder
    {
        const string Key = "Alatau.RecordFilm", ShotKey = "Alatau.RecordFilmShot";
        static RecorderController rc; static int phase; static double t0; static string outName;

        [MenuItem("Alatau City/Record film 60 s")]
        static void Record() => Start(-1);
        [MenuItem("Alatau City/Record film test (one shot)")]
        static void RecordTest() => Start(3);
        [MenuItem("Alatau City/Stop film recording")]
        static void StopNow() { FilmReel.Stop(); Finish(); }

        static void Start(int shot)
        {
            SessionState.SetBool(Key, true); SessionState.SetInt(ShotKey, shot); phase = 0;
            Debug.Log("[Alatau] film: recording requested" + (shot >= 0 ? " (test, shot " + shot + ")" : ""));
            if (!EditorApplication.isPlaying) EditorApplication.isPlaying = true;
        }

        [InitializeOnLoadMethod]
        static void Hook() { EditorApplication.update -= Tick; EditorApplication.update += Tick; }

        static void Tick()
        {
            if (!SessionState.GetBool(Key, false)) return;
            if (!EditorApplication.isPlaying) { if (phase >= 2) Finish(); return; }
            double now = EditorApplication.timeSinceStartup;
            switch (phase)
            {
                case 0:      // the city loads (data, buildings, landmarks)
                    if (TwinData.Ready && CityStats.Ready && Camera.main != null && FilmLook.Instance != null && FilmRoads.WayCount > 0) { phase = 1; t0 = now; }
                    else if (now - t0 > 0 && t0 == 0) t0 = now;
                    break;
                case 1:      // a few seconds for the streaming textures and the landmarks
                    if (now - t0 < 8.0) break;
                    int shot = SessionState.GetInt(ShotKey, -1);
                    if (!FilmReel.Play(shot)) break;
                    StartRecorder(shot >= 0 ? "Alatau_film_test" : "Alatau_film_60s_raw"); phase = 2; t0 = now;
                    break;
                case 2:
                    if (!FilmReel.Playing) { phase = 3; t0 = now; }
                    break;
                case 3:      // the last frame is written, then stop
                    if (now - t0 > 1.0) { Finish(); EditorApplication.isPlaying = false; }
                    break;
            }
        }

        static void StartRecorder(string name)
        {
            var cs = ScriptableObject.CreateInstance<RecorderControllerSettings>();
            var m = ScriptableObject.CreateInstance<MovieRecorderSettings>();
            m.name = "Alatau film"; m.Enabled = true;
            var enc = new CoreEncoderSettings { Codec = CoreEncoderSettings.OutputCodec.MP4, EncodingQuality = CoreEncoderSettings.VideoEncodingQuality.High };
            m.EncoderSettings = (IEncoderSettings)HighBitRate(enc, 30f);
            m.ImageInputSettings = new RenderTextureInputSettings { RenderTexture = FilmReel.Target };
            m.CaptureAudio = false;
            outName = name;
            m.OutputFile = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "..", "Recordings", name));
            cs.AddRecorderSettings(m);
            cs.SetRecordModeToManual();
            cs.FrameRatePlayback = FrameRatePlayback.Constant; cs.FrameRate = 60f; cs.CapFrameRate = true;   // 60 fps: the composer blends frame pairs into 30 fps with a 180° shutter (motion blur)
            rc = new RecorderController(cs);
            rc.PrepareRecording(); rc.StartRecording();
            Debug.Log("[Alatau] film: recording → " + m.OutputFile + ".mp4");
        }

        /// <summary>H.264 at a fixed high bit rate (Mbps) instead of the «High» preset; set by name, so a Recorder without these options
        /// records with the preset.</summary>
        static object HighBitRate(CoreEncoderSettings enc, float mbps)
        {
            const System.Reflection.BindingFlags F = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
            object boxed = enc; var t = typeof(CoreEncoderSettings);
            bool Set(string n, object v)
            {
                try
                {
                    var p = t.GetProperty(n, F); if (p != null && p.CanWrite) { p.SetValue(boxed, Conv(v, p.PropertyType)); return true; }
                    var f = t.GetField(n, F); if (f != null) { f.SetValue(boxed, Conv(v, f.FieldType)); return true; }
                }
                catch (System.Exception e) { Debug.LogWarning($"[Alatau] film encoder: {n}: {e.Message}"); }
                return false;
            }
            static object Conv(object v, System.Type to) => to.IsInstanceOfType(v) || to.IsEnum ? v : System.Convert.ChangeType(v, to);
            object custom = null; try { custom = System.Enum.Parse(typeof(CoreEncoderSettings.VideoEncodingQuality), "Custom"); } catch { }
            bool ok = custom != null && Set("EncodingQuality", custom) && Set("TargetBitRate", mbps);
            if (ok) { Set("GopSize", 30); Set("NumConsecutiveBFrames", 2); }
            Debug.Log(ok ? $"[Alatau] film encoder: H.264 {mbps} Mbps" : "[Alatau] film encoder: «High» preset");
            return boxed;
        }

        static void Finish()
        {
            SessionState.SetBool(Key, false);
            if (rc != null && rc.IsRecording()) { rc.StopRecording(); Debug.Log("[Alatau] film saved: UnityProject/Recordings/" + outName + ".mp4"); }
            if (FilmReel.Playing) FilmReel.Stop();
            rc = null; phase = 0; t0 = 0;
        }
    }
}
