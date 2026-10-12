using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace AlatauCity.EditorTools
{
    /// <summary>Brings a fresh clone (or any machine) to the reference look on open, with no manual steps:
    /// Unity version check → material photo textures → the generated city (Assets/Generated is not in git, it is built from
    /// Assets/CityData) → stable asset ids of the generated city → the scene → highest quality → Game view Full HD, maximized on Play.
    /// Runs once per editor session; menu "Alatau City/Привести проект к эталону" runs it again.
    ///
    /// Stable ids: Unity gives every new asset a random GUID, so a scene saved on one machine points at meshes another machine
    /// does not have. Here every file in Assets/Generated gets a GUID derived from its file name, and the scene is rewritten to
    /// match: the scene in git then works on every machine that has built the city, and a rebuilt scene is safe to commit.</summary>
    [InitializeOnLoad]
    public static class AlatauProjectSetup
    {
        public const string ScenePath = "Assets/Scenes/AlatauCity.unity", Gen = "Assets/Generated", UnityVersion = "6000.0.84f1";
        const string DoneKey = "Alatau.Setup.Done";

        static AlatauProjectSetup()
        {
            if (Application.isBatchMode) return;
            EditorApplication.delayCall += () => Run(false);
        }

        [MenuItem("Alatau City/Привести проект к эталону", priority = 0)]
        public static void RunFromMenu() => Run(true);

        static void Run(bool force)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode) return;
            if (EditorApplication.isCompiling || EditorApplication.isUpdating) { EditorApplication.delayCall += () => Run(force); return; }
            if (!force && SessionState.GetBool(DoneKey, false)) return;
            SessionState.SetBool(DoneKey, true);
            try
            {
                // 1. the editor version the project is made with (shaders and import settings are checked on it)
                if (Application.unityVersion != UnityVersion)
                {
                    Debug.LogWarning($"[Alatau] проект сделан на Unity {UnityVersion}, открыт в {Application.unityVersion}: картинка может отличаться");
                    if (force || !EditorPrefs.GetBool("Alatau.VersionWarned." + Application.unityVersion, false))
                    {
                        EditorPrefs.SetBool("Alatau.VersionWarned." + Application.unityVersion, true);
                        EditorUtility.DisplayDialog("Alatau City", $"Проект сделан на Unity {UnityVersion}.\nСейчас открыт в {Application.unityVersion}.\n\nПоставьте {UnityVersion} через Unity Hub, иначе шейдеры и текстуры могут выглядеть иначе.", "Понятно");
                    }
                }

                // 2. material photo textures (ground, roofs, facades): rebuilt from Assets/Textures/Materials if missing or unreadable
                if (AssetDatabase.LoadAssetAtPath<Texture2DArray>("Assets/Resources/Materials/AlatauMatAlbedo.asset") == null ||
                    AssetDatabase.LoadAssetAtPath<Texture2DArray>("Assets/Resources/Materials/AlatauMatDetail.asset") == null ||
                    AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/Resources/Materials/AlatauMatMean.asset") == null)
                {
                    Debug.Log("[Alatau] фото-текстуры материалов не найдены — собираю");
                    AlatauMaterials.Build();
                }

                // 3. the generated city
                if (!CityBuilt())
                {
                    Debug.Log("[Alatau] Assets/Generated не собран — собираю город (несколько минут)");
                    AlatauCityBuilder.Build();          // builds Assets/Generated and saves the scene; it normalises the ids itself
                }
                else if (ReadStamp() != DataStamp())
                {
                    // the city data in git changed since this machine built the city (new buildings, moved plants): build it again
                    Debug.Log("[Alatau] данные города (Assets/CityData) обновились — пересобираю город (несколько минут)");
                    AlatauCityBuilder.Build();
                }

                // 4. stable ids (an older build, or a city built before this tool existed)
                NormalizeGeneratedGuids();

                // 5. the scene
                if (File.Exists(ScenePath) && EditorSceneManager.GetActiveScene().path != ScenePath)
                {
                    if (EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
                }
                var list = EditorBuildSettings.scenes;
                if (list.Length == 0 || list[0].path != ScenePath || !list[0].enabled)
                    EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) }.Concat(list.Where(s => s.path != ScenePath)).ToArray();

                // 6. quality: the highest level (Ultra)
                int top = QualitySettings.names.Length - 1;
                if (QualitySettings.GetQualityLevel() != top) QualitySettings.SetQualityLevel(top, true);

                // 7. Game view as on the reference machine: Full HD, full resolution, maximized on Play
                SetupGameView();
                Debug.Log("[Alatau] проект приведён к эталону: город, сцена, качество Ultra, окно Game Full HD (меню Alatau City → Привести проект к эталону)");
            }
            catch (Exception e) { Debug.LogError("[Alatau] настройка проекта: " + e); }
            finally { EditorUtility.ClearProgressBar(); }
        }

        static bool CityBuilt()
        {
            if (!AssetDatabase.IsValidFolder(Gen) || !Directory.Exists(Gen)) return false;
            return File.Exists(Gen + "/Terrain.asset") && File.Exists(Gen + "/Buildings_Existing_buildings.asset") && Directory.GetFiles(Gen, "Buildings_*.asset").Length > 20;
        }

        const string StampPath = Gen + "/city_data.stamp";
        /// <summary>Fingerprint of the city data the generated city is built from (contents, not dates: the same on every clone).</summary>
        public static string DataStamp()
        {
            using (var md5 = MD5.Create())
            {
                foreach (var f in new[] { "Assets/CityData/layer_buildings.bytes", "Assets/CityData/buildings.csv", "Assets/CityData/layer_infrastructure.bytes", "Assets/CityData/terrain_heights.bytes" })
                {
                    if (!File.Exists(f)) continue;
                    var b = File.ReadAllBytes(f); md5.TransformBlock(b, 0, b.Length, null, 0);
                }
                md5.TransformFinalBlock(new byte[0], 0, 0);
                var sb = new StringBuilder(); foreach (var x in md5.Hash) sb.Append(x.ToString("x2")); return sb.ToString();
            }
        }
        static string ReadStamp() => File.Exists(StampPath) ? File.ReadAllText(StampPath).Trim() : "";
        /// <summary>Written by the city builder after a build.</summary>
        public static void WriteStamp() { if (Directory.Exists(Gen)) File.WriteAllText(StampPath, DataStamp()); }

        static void SetupGameView()
        {
            try
            {
                PlayModeWindow.SetViewType(PlayModeWindow.PlayModeViewTypes.GameView);
                PlayModeWindow.SetCustomRenderingResolution(1920u, 1080u, "Full HD (1920x1080)");
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] разрешение окна Game: " + e.Message); }
            try
            {
                var asm = typeof(EditorWindow).Assembly;
                var gameViewType = asm.GetType("UnityEditor.GameView");
                if (gameViewType == null) return;
                var views = Resources.FindObjectsOfTypeAll(gameViewType);
                if (views.Length == 0) views = new UnityEngine.Object[] { EditorWindow.GetWindow(gameViewType, false, "Game", false) };
                foreach (var v in views)
                {
                    // Play Maximized
                    var p = gameViewType.GetProperty("enterPlayModeBehavior", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (p != null && p.PropertyType.IsEnum) p.SetValue(v, Enum.Parse(p.PropertyType, "PlayMaximized"));
                    // full resolution on high-DPI screens
                    var lr = gameViewType.GetProperty("lowResolutionForAspectRatios", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (lr != null && lr.CanWrite) lr.SetValue(v, false);
                    // no "VSync off / stats" surprises: keep gizmos off
                    var gz = gameViewType.GetProperty("drawGizmos", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (gz != null && gz.CanWrite) gz.SetValue(v, false);
                    (v as EditorWindow)?.Repaint();
                }
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] окно Game: " + e.Message); }
        }

        /// <summary>GUID of a generated asset from its file name: the same on every machine.</summary>
        static string StableGuid(string fileName)
        {
            using (var md5 = MD5.Create())
            {
                var h = md5.ComputeHash(Encoding.UTF8.GetBytes("alatau-generated/" + fileName));
                var sb = new StringBuilder(32); foreach (var b in h) sb.Append(b.ToString("x2")); return sb.ToString();
            }
        }

        /// <summary>Every file in Assets/Generated gets its stable GUID; the scene is rewritten to point at them. Returns the number of
        /// ids changed (0 = already stable, nothing touched).</summary>
        public static int NormalizeGeneratedGuids()
        {
            if (!Directory.Exists(Gen)) return 0;
            var map = new Dictionary<string, string>();
            var metas = new List<(string path, string text, string old, string want)>();
            foreach (var file in Directory.GetFiles(Gen))
            {
                if (file.EndsWith(".meta")) continue;
                var meta = file + ".meta"; if (!File.Exists(meta)) continue;
                var text = File.ReadAllText(meta);
                int i = text.IndexOf("\nguid: ", StringComparison.Ordinal); if (i < 0) continue;
                var old = text.Substring(i + 7, 32);
                var want = StableGuid(Path.GetFileName(file));
                if (old == want) continue;
                map[old] = want; metas.Add((meta, text, old, want));
            }
            if (map.Count == 0) return 0;

            // the scene must not be open while its references are rewritten underneath it
            var active = EditorSceneManager.GetActiveScene();
            bool reopen = active.path == ScenePath;
            if (active.isDirty && reopen) EditorSceneManager.SaveScene(active);
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            {
                foreach (var m in metas) File.WriteAllText(m.path, m.text.Replace("guid: " + m.old, "guid: " + m.want));
                if (File.Exists(ScenePath))
                {
                    var scene = File.ReadAllText(ScenePath); int n = 0;
                    foreach (var kv in map) { if (scene.Contains(kv.Key)) { scene = scene.Replace("guid: " + kv.Key, "guid: " + kv.Value); n++; } }
                    if (n > 0) File.WriteAllText(ScenePath, scene);
                }
            }
            AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate);
            Debug.Log($"[Alatau] стабильные id для Assets/Generated: {map.Count} файлов, сцена обновлена");
            if (File.Exists(ScenePath)) EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            return map.Count;
        }
    }
}
