using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine.Rendering;
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
            NoSplash();
            Directory.CreateDirectory(Path.GetDirectoryName(Out));
            var opt = new BuildPlayerOptions { scenes = new[] { Scene }, locationPathName = Out, target = BuildTarget.StandaloneWindows64, options = BuildOptions.None };
            var r = BuildPipeline.BuildPlayer(opt);
            var s = r.summary;
            if (s.result == BuildResult.Succeeded) { Debug.Log($"[Alatau] Windows build OK: {Path.GetFullPath(Out)} · {s.totalSize / 1048576f:0} MB · {s.totalTime.TotalSeconds:0} s"); if (!ci) EditorUtility.RevealInFinder(Out); }
            else { Debug.LogError($"[Alatau] Windows build {s.result}: {s.totalErrors} errors"); if (ci) EditorApplication.Exit(1); }
        }

        /// <summary>The twin opens straight away: no Unity splash screen («Made with Unity») before the first frame.</summary>
        static void NoSplash() { PlayerSettings.SplashScreen.show = false; PlayerSettings.SplashScreen.showUnityLogo = false; }

        const string WebOut = "Builds/WebGL";

        /// <summary>Alatau City → Build WebGL: a browser build in Builds/WebGL for static hosting (GitHub Pages, any web server).
        /// Gzip with decompression fallback: works on hosts that cannot set Content-Encoding headers (GitHub Pages);
        /// on our own server nginx can serve the .gz files with the header and skip the fallback.</summary>
        [MenuItem("Alatau City/Build WebGL", priority = 41)]
        public static void BuildWebGL() => BuildWeb(false);
        public static void BuildWebGLCI() => BuildWeb(true);

        static void BuildWeb(bool ci)
        {
            if (ci && !File.Exists("Assets/Generated/Terrain.asset")) AlatauCityBuilder.Build();
            PlayerSettings.companyName = "qTwin";
            PlayerSettings.productName = "Alatau City · Digital Twin";
            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
            PlayerSettings.WebGL.decompressionFallback = true;
            PlayerSettings.WebGL.dataCaching = true;
            PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.ExplicitlyThrownExceptionsOnly;
            PlayerSettings.WebGL.memoryGrowthMode = WebGLMemoryGrowthMode.Geometric;
            PlayerSettings.WebGL.initialMemorySize = 512;
            PlayerSettings.WebGL.maximumMemorySize = 4096;
            PlayerSettings.WebGL.nameFilesAsHashes = false;
            PlayerSettings.WebGL.template = "PROJECT:Alatau";                                   // Assets/WebGLTemplates/Alatau: full window, Russian loading card
            PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.WebGL, false);
            PlayerSettings.SetGraphicsAPIs(BuildTarget.WebGL, new[] { GraphicsDeviceType.OpenGLES3 });   // WebGL 2
            PlayerSettings.runInBackground = true;
            NoSplash();
            EditorUserBuildSettings.webGLBuildSubtarget = WebGLTextureSubtarget.DXT;               // desktop browsers
            if (Directory.Exists(WebOut)) Directory.Delete(WebOut, true);
            var opt = new BuildPlayerOptions { scenes = new[] { Scene }, locationPathName = WebOut, target = BuildTarget.WebGL, options = BuildOptions.None };
            var r = BuildPipeline.BuildPlayer(opt); var s = r.summary;
            if (s.result == BuildResult.Succeeded)
            {
                File.WriteAllText(Path.Combine(WebOut, ".nojekyll"), "");                           // GitHub Pages: serve files as they are
                long total = 0; foreach (var f in Directory.GetFiles(WebOut, "*", SearchOption.AllDirectories)) total += new FileInfo(f).Length;
                // one archive for GitHub Pages (uploaded to a Release; .github/workflows/pages.yml publishes it)
                const string Zip = "Builds/alatau-webgl.zip";
                if (File.Exists(Zip)) File.Delete(Zip);
                System.IO.Compression.ZipFile.CreateFromDirectory(WebOut, Zip, System.IO.Compression.CompressionLevel.NoCompression, false);
                Debug.Log($"[Alatau] WebGL build OK: {Path.GetFullPath(WebOut)} · {total / 1048576f:0} MB on disk · {s.totalTime.TotalMinutes:0.0} min · archive {Path.GetFullPath(Zip)}");
                if (!ci) EditorUtility.RevealInFinder(WebOut);
            }
            else { Debug.LogError($"[Alatau] WebGL build {s.result}: {s.totalErrors} errors"); if (ci) EditorApplication.Exit(1); }
        }
    }
}
