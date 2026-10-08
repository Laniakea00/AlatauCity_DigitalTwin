using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.EditorTools
{
    /// <summary>Creates the UI Toolkit runtime assets the shell needs (default runtime theme + PanelSettings) in Assets/Resources/UI.
    /// Runs once automatically after import; also available as Alatau City → Setup UI assets.</summary>
    [InitializeOnLoad]
    public static class AlatauUISetup
    {
        const string Dir = "Assets/Resources/UI", Tss = Dir + "/TwinTheme.tss", Panel = Dir + "/TwinPanel.asset";
        static AlatauUISetup() { EditorApplication.delayCall += () => { if (!File.Exists(Panel) || !File.Exists(Tss)) Setup(); }; }

        [MenuItem("Alatau City/Setup UI assets", priority = 20)]
        public static void Setup()
        {
            Directory.CreateDirectory(Dir);
            if (!File.Exists(Tss)) { File.WriteAllText(Tss, "@import url(\"unity-theme://default\");\n"); AssetDatabase.ImportAsset(Tss); }
            var theme = AssetDatabase.LoadAssetAtPath<ThemeStyleSheet>(Tss);
            var ps = AssetDatabase.LoadAssetAtPath<PanelSettings>(Panel);
            if (ps == null) { ps = ScriptableObject.CreateInstance<PanelSettings>(); AssetDatabase.CreateAsset(ps, Panel); }
            ps.themeStyleSheet = theme; ps.scaleMode = PanelScaleMode.ConstantPixelSize; ps.scale = 1f; ps.sortingOrder = 10;
            EditorUtility.SetDirty(ps); AssetDatabase.SaveAssets();
            Debug.Log("[Alatau] UI assets ready: " + Panel + (theme == null ? " (theme missing!)" : ""));
        }
    }
}
