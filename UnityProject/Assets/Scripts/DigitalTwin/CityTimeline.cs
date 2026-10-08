using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>4D timeline 2025-2050. The year lives in TwinState; this component only drives playback and keyboard shortcuts.
    /// Space = play/pause, PageUp/PageDown or . , = step. Shader-side filtering: instant for all 57k buildings.</summary>
    public class CityTimeline : MonoBehaviour
    {
        [Range(2025, 2050)] public int year = 2050;
        public float secondsPerYear = 1.0f;
        float t; bool wasPlaying;
        static readonly int YearFId = Shader.PropertyToID("_AlatauYearF"), GrowId = Shader.PropertyToID("_AlatauGrow");
        /// <summary>Smooth year for the growth animation: buildings of year ⌊yf⌋+1 rise while yf goes from ⌊yf⌋ to ⌊yf⌋+1.</summary>
        public static void Growth(float yf) { Shader.SetGlobalFloat(YearFId, yf); Shader.SetGlobalFloat(GrowId, 1f); }
        public static void StopGrowth() { Shader.SetGlobalFloat(GrowId, 0f); }
        void OnEnable() { secondsPerYear = Mathf.Max(secondsPerYear, 1.0f); TwinState.Year = year; TwinState.PushYearToShader(); }
        void OnDisable() { Shader.SetGlobalFloat("_AlatauYear", 0); }
        public void TogglePlay()
        {
            TwinState.Playing = !TwinState.Playing;
            if (TwinState.Playing && TwinState.Year >= TwinState.MaxYear) TwinState.Year = TwinState.MinYear;
            t = 0;
        }
        void Update()
        {
            if (MapCamera.Typing || TwinTour.Running) { } else
            {
            if (Input.GetKeyDown(KeyCode.Space)) TogglePlay();
            if (Input.GetKeyDown(KeyCode.PageUp) || Input.GetKeyDown(KeyCode.Period)) TwinState.Year++;
            if (Input.GetKeyDown(KeyCode.PageDown) || Input.GetKeyDown(KeyCode.Comma)) TwinState.Year--;
            }
            if (TwinState.Playing)
            {
                t += Time.deltaTime;
                if (t > secondsPerYear) { t = 0; TwinState.Year++; if (TwinState.Year >= TwinState.MaxYear) TwinState.Playing = false; }
                if (TwinState.Playing) Growth(TwinState.Year + Mathf.Clamp01(t / secondsPerYear));
            }
            if (wasPlaying && !TwinState.Playing) StopGrowth();
            wasPlaying = TwinState.Playing;
            year = TwinState.Year;
        }
    }
}
