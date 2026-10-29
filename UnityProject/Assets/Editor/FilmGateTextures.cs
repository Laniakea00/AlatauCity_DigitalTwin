#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

/// <summary>Import settings of the film look's photo textures in Assets/Resources/Film (CC0: AlatauSkyDome = upper half of Poly Haven
/// "Kloofendal 48d Partly Cloudy (Pure Sky)", tone-mapped to display values, sun turned to the left edge):
/// at most 2048 px, mipmaps, repeat, high-quality compression (no banding in the sky), normal maps marked as such. Editor only.</summary>
class FilmGateTextures : AssetPostprocessor
{
    void OnPreprocessTexture()
    {
        if (!assetPath.Replace('\\', '/').StartsWith("Assets/Resources/Film/")) return;
        var ti = (TextureImporter)assetImporter;
        string name = System.IO.Path.GetFileNameWithoutExtension(assetPath);
        bool normal = name.EndsWith("_nor") || name.EndsWith("_Normal");
        ti.textureType = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
        ti.textureShape = TextureImporterShape.Texture2D;
        ti.mipmapEnabled = true;
        ti.wrapMode = TextureWrapMode.Repeat;
        ti.filterMode = FilterMode.Trilinear;
        ti.anisoLevel = name.StartsWith("AlatauSky") ? 0 : 4;
        ti.maxTextureSize = 2048;
        ti.textureCompression = TextureImporterCompression.CompressedHQ;
        ti.isReadable = false;
    }
}
#endif
