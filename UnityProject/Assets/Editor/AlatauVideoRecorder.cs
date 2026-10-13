using UnityEditor;
using UnityEditor.Recorder;
using UnityEditor.Recorder.Encoder;
using UnityEditor.Recorder.Input;
using UnityEngine;
using AlatauCity.DigitalTwin;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.EditorTools
{
    /// <summary>Alatau City → Record investor video: enters Play mode, waits until the city is loaded, then starts the video mode (F6:
    /// 12 scenes cut to the ElevenLabs voice-over) and the Unity Recorder at the same frame — Game view 1920×1080, 30 fps constant
    /// (smooth even when the editor renders slower), H.264 MP4 with the voice. Stops by itself after the last scene and leaves
    /// Play mode. Output: UnityProject/Recordings/Alatau_investor_video.mp4.</summary>
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
                    if (TwinData.Ready && CityStats.Ready && TwinTour.Instance != null) { phase = 1; t0 = now; }
                    break;
                case 1:      // a few seconds for the streaming textures and the first camera position
                    if (now - t0 < 4.0) break;
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
            m.EncoderSettings = new CoreEncoderSettings { Codec = CoreEncoderSettings.OutputCodec.MP4, EncodingQuality = CoreEncoderSettings.VideoEncodingQuality.High };
            m.ImageInputSettings = new GameViewInputSettings { OutputWidth = 1920, OutputHeight = 1080 };
            m.CaptureAudio = true;
            m.OutputFile = System.IO.Path.GetFullPath(System.IO.Path.Combine(Application.dataPath, "..", "Recordings", "Alatau_investor_video"));
            cs.AddRecorderSettings(m);
            cs.SetRecordModeToManual();
            cs.FrameRatePlayback = FrameRatePlayback.Constant; cs.FrameRate = 30f; cs.CapFrameRate = true;
            rc = new RecorderController(cs);
            rc.PrepareRecording(); rc.StartRecording();
            Debug.Log("[Alatau] recording → " + m.OutputFile + ".mp4");
        }

        static void Finish()
        {
            SessionState.SetBool(Key, false);
            if (rc != null && rc.IsRecording()) { rc.StopRecording(); Debug.Log("[Alatau] recording saved: UnityProject/Recordings/Alatau_investor_video.mp4"); }
            rc = null; phase = 0;
        }
    }
}
