using System;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Global state of the digital twin: one year, one scenario, one active module, one selection.
    /// Every module and UI element subscribes to the events; nothing else owns these values.</summary>
    public static class TwinState
    {
        public const int MinYear = 2026, MaxYear = 2050;          // Alatau City gathers pace from 2026; the data tables start in 2025
        static readonly int YearId = Shader.PropertyToID("_AlatauYear");

        static int year = 2050;
        public static int Year
        {
            get => year;
            set { value = Mathf.Clamp(value, MinYear, MaxYear); if (value == year) return; year = value; Shader.SetGlobalFloat(YearId, year); OnYearChanged?.Invoke(year); }
        }
        public static void PushYearToShader() => Shader.SetGlobalFloat(YearId, year);

        static Scenario scenario = Scenario.Base;
        public static Scenario Scenario
        {
            get => scenario;
            set { if (value == scenario) return; scenario = value; TwinScenario.Apply(scenario); CityStats.Rebuild(scenario); OnScenarioChanged?.Invoke(scenario); }
        }

        public static string Module { get; private set; } = "overview";
        public static void SetModule(string id) { if (id == Module) return; Module = id; OnModuleChanged?.Invoke(id); }

        /// <summary>-1 = whole city, 0..3 = Gate, Golden, Growing, Green.</summary>
        public static int District { get; private set; } = -1;
        public static void SetDistrict(int d) { if (d == District) return; District = d; OnDistrictChanged?.Invoke(d); }

        public static BuildingInfo Selected { get; private set; }
        public static void SetSelected(BuildingInfo b) { Selected = b; OnSelectionChanged?.Invoke(b); }

        public static string Language { get; private set; } = "ru";
        public static void SetLanguage(string l) { if (l == Language) return; Language = l; Loc.Language = l; OnLanguageChanged?.Invoke(l); }

        public static bool Playing;
        /// <summary>Seconds of this frame that do not follow the tour speed-up (Time.timeScale), taken from the game clock: when the video is
        /// recorded the Unity Recorder advances it by a fixed step per frame while Time.unscaledDeltaTime is the wall clock, uneven.</summary>
        public static float RealDelta => Time.timeScale > 1e-4f ? Time.deltaTime / Time.timeScale : Time.unscaledDeltaTime;

        public static event Action<int> OnYearChanged;
        public static event Action<Scenario> OnScenarioChanged;
        public static event Action<string> OnModuleChanged;
        public static event Action<int> OnDistrictChanged;
        public static event Action<BuildingInfo> OnSelectionChanged;
        public static event Action<string> OnLanguageChanged;
        /// <summary>Raised when run-time layers (LineLayers) have been (re)built, so the active module can switch its layers on.</summary>
        public static event Action OnLayersReady;
        public static void NotifyLayersReady() => OnLayersReady?.Invoke();
    }
}
