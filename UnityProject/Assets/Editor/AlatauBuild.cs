using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace AlatauCity.EditorTools
{
    /// <summary>Alatau City → Build Windows: a 64-bit Windows player in Builds/Windows (AlatauCity.exe + data + StreamingAssets/twin).</summary>
    public static class AlatauBuild
    {
        const string Scene = "Assets/Scenes/AlatauCity.unity", Out = "Builds/Windows/AlatauCity.exe";

        [MenuItem("Alatau City/Build Windows", priority = 40)]
        public static void BuildWindows()
        {
            PlayerSettings.companyName = "qTwin";
            PlayerSettings.productName = "Alatau City · Digital Twin";
            PlayerSettings.fullScreenMode = FullScreenMode.FullScreenWindow;
            PlayerSettings.defaultScreenWidth = 1920; PlayerSettings.defaultScreenHeight = 1080;
            PlayerSettings.resizableWindow = true; PlayerSettings.runInBackground = true;
            Directory.CreateDirectory(Path.GetDirectoryName(Out));
            var opt = new BuildPlayerOptions { scenes = new[] { Scene }, locationPathName = Out, target = BuildTarget.StandaloneWindows64, options = BuildOptions.None };
            var r = BuildPipeline.BuildPlayer(opt);
            var s = r.summary;
            if (s.result == BuildResult.Succeeded) { Debug.Log($"[Alatau] Windows build OK: {Path.GetFullPath(Out)} · {s.totalSize / 1048576f:0} MB · {s.totalTime.TotalSeconds:0} s"); EditorUtility.RevealInFinder(Out); }
            else Debug.LogError($"[Alatau] Windows build {s.result}: {s.totalErrors} errors");
        }
    }
}
