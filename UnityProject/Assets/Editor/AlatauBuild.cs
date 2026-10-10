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
        public static void BuildWindows() => Build(false);

        /// <summary>Build without the editor UI, for a build server:
        /// Unity.exe -batchmode -quit -projectPath UnityProject -executeMethod AlatauCity.EditorTools.AlatauBuild.BuildWindowsCI -logFile build.log
        /// Builds the city first if Assets/Generated is missing (fresh clone), exits with code 1 on failure.</summary>
        public static void BuildWindowsCI() => Build(true);

        static void Build(bool ci)
        {
            if (ci)
            {
                if (!File.Exists("Assets/Generated/Terrain.asset")) AlatauCityBuilder.Build(); else AlatauProjectSetup.NormalizeGeneratedGuids();
                if (AssetDatabase.LoadAssetAtPath<Texture2DArray>("Assets/Resources/Materials/AlatauMatAlbedo.asset") == null) AlatauMaterials.Build();
            }
            PlayerSettings.companyName = "qTwin";
            PlayerSettings.productName = "Alatau City · Digital Twin";
            PlayerSettings.fullScreenMode = FullScreenMode.FullScreenWindow;
            PlayerSettings.defaultScreenWidth = 1920; PlayerSettings.defaultScreenHeight = 1080;
            PlayerSettings.resizableWindow = true; PlayerSettings.runInBackground = true;
            Directory.CreateDirectory(Path.GetDirectoryName(Out));
            var opt = new BuildPlayerOptions { scenes = new[] { Scene }, locationPathName = Out, target = BuildTarget.StandaloneWindows64, options = BuildOptions.None };
            var r = BuildPipeline.BuildPlayer(opt);
            var s = r.summary;
            if (s.result == BuildResult.Succeeded) { Debug.Log($"[Alatau] Windows build OK: {Path.GetFullPath(Out)} · {s.totalSize / 1048576f:0} MB · {s.totalTime.TotalSeconds:0} s"); if (!ci) EditorUtility.RevealInFinder(Out); }
            else { Debug.LogError($"[Alatau] Windows build {s.result}: {s.totalErrors} errors"); if (ci) EditorApplication.Exit(1); }
        }
    }
}
