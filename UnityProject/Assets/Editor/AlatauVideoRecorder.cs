using UnityEditor;
using UnityEditor.Recorder;
using UnityEditor.Recorder.Encoder;
using UnityEditor.Recorder.Input;
using UnityEngine;
using AlatauCity.DigitalTwin;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.EditorTools
{
    /// <summary>Alatau City → Record investor video: enters Play mode, waits until the city is loaded, switches the interface to English,
    /// then starts the video mode (F6: 15 scenes cut to the ElevenLabs voice-over) and the Unity Recorder at the same frame — Game view
    /// 1920×1080, 30 fps constant (smooth even when the editor renders slower), H.264 MP4 at a high bit rate with the voice. Stops by
    /// itself after the last scene and leaves Play mode. Output: UnityProject/Recordings/Alatau_investor_video_EN.mp4.</summary>
    public static class AlatauVideoRecorder
    {
        const string Key = "Alatau.RecordVideo";
        static RecorderController rc; static int phase; static double t0;

        [MenuItem("Alatau City/Record investor video (1080p, voice)")]
        static void Record()
        {
            SessionState.SetBool(Key, true); phase = 0;
            if (!EditorApplication.isPlaying) EditorApplication.isPlaying = true;
        }
        // the language the app starts with (remembered between runs; also switched in the header while playing)
        [MenuItem("Alatau City/Interface language/Русский")] static void LangRu() => SetLang("ru");
        [MenuItem("Alatau City/Interface language/English")] static void LangEn() => SetLang("en");
        [MenuItem("Alatau City/Interface language/Қазақша")] static void LangKz() => SetLang("kz");
        static void SetLang(string l) { PlayerPrefs.SetString("alatau_lang", l); PlayerPrefs.Save(); if (EditorApplication.isPlaying) TwinState.SetLanguage(l); Debug.Log("[Alatau] interface language: " + l); }

        [MenuItem("Alatau City/Stop video recording")]
        static void StopNow() { Finish(); }

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
                    if (TwinData.Ready && CityStats.Ready && TwinTour.Instance != null) { TwinTour.VideoLanguage(); phase = 1; t0 = now; }
                    break;
                case 1:      // a few seconds for the streaming textures, the first camera position and the English interface
                    if (now - t0 < 6.0) break;
                    StartRecorder(); TwinTour.ToggleVideo(); phase = 2; t0 = now;
                    break;
                case 2:
                    if (!TwinTour.Running || TwinTour.VideoDone) { phase = 3; t0 = now; }
                    break;
                case 3:      // hold the last frame a moment, then stop
                    if (now - t0 > 1.0) { Finish(); EditorApplication.isPlaying = false; }
                    break;
            }
        }

        static void StartRecorder()
        {
            var cs = ScriptableObject.CreateInstance<RecorderControllerSettings>();
            var m = ScriptableObject.CreateInstance<MovieRecorderSettings>();
            m.name = "Alatau investor video"; m.Enabled = true;
            var enc = new CoreEncoderSettings { Codec = CoreEncoderSettings.OutputCodec.MP4, EncodingQuality = CoreEncoderSettings.VideoEncodingQuality.High };
            m.EncoderSettings = (IEncoderSettings)HighBitRate(enc, 16f);
            m.ImageInputSettings = new GameViewInputSettings { OutputWidth = 1920, OutputHeight = 1080 };
            m.CaptureAudio = true;
            m.OutputFile = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "..", "Recordings", "Alatau_investor_video_EN"));
            cs.AddRecorderSettings(m);
            cs.SetRecordModeToManual();
            cs.FrameRatePlayback = FrameRatePlayback.Constant; cs.FrameRate = 30f; cs.CapFrameRate = true;
            rc = new RecorderController(cs);
            rc.PrepareRecording(); rc.StartRecording();
            Debug.Log("[Alatau] recording → " + m.OutputFile + ".mp4");
        }

        /// <summary>H.264 at a fixed high bit rate (Mbps) instead of the «High» preset: crisp interface text and map lines. Set by name, so
        /// a Recorder version without these options records with the preset.</summary>
        static object HighBitRate(CoreEncoderSettings enc, float mbps)
        {
            const System.Reflection.BindingFlags F = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
            object boxed = enc; var t = typeof(CoreEncoderSettings);
            bool Set(string name, object v)
            {
                try
                {
                    var p = t.GetProperty(name, F); if (p != null && p.CanWrite) { p.SetValue(boxed, Conv(v, p.PropertyType)); return true; }
                    var f = t.GetField(name, F); if (f != null) { f.SetValue(boxed, Conv(v, f.FieldType)); return true; }
                }
                catch (System.Exception e) { Debug.LogWarning($"[Alatau] video encoder: {name}: {e.Message}"); }
                return false;
            }
            static object Conv(object v, System.Type to) => to.IsInstanceOfType(v) || to.IsEnum ? v : System.Convert.ChangeType(v, to);
            object custom = null; try { custom = System.Enum.Parse(typeof(CoreEncoderSettings.VideoEncodingQuality), "Custom"); } catch { }
            bool ok = custom != null && Set("EncodingQuality", custom) && Set("TargetBitRate", mbps);
            if (ok) { Set("GopSize", 30); Set("NumConsecutiveBFrames", 2); }
            Debug.Log(ok ? $"[Alatau] video encoder: H.264 {mbps} Mbps" : "[Alatau] video encoder: «High» preset (no custom bit rate in this Recorder)");
            return boxed;
        }

        static void Finish()
        {
            SessionState.SetBool(Key, false);
            if (rc != null && rc.IsRecording()) { rc.StopRecording(); Debug.Log("[Alatau] recording saved: UnityProject/Recordings/Alatau_investor_video_EN.mp4"); }
            rc = null; phase = 0;
        }
    }
}
