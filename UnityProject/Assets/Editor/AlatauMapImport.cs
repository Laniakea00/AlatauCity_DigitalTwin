using UnityEditor;
using UnityEngine;

namespace AlatauCity.EditorTools
{
    /// <summary>Import settings for the base map (Assets/Resources/Map): full 8K resolution, mipmaps, anisotropic filtering;
    /// the development-year raster is linear and uncompressed (its values are years, not colours).</summary>
    public class AlatauMapImport : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            var path = assetPath.Replace('\\', '/');
            if (path.Contains("Resources/UI/Icons/"))
            {
                var ii = (TextureImporter)assetImporter; ii.textureType = TextureImporterType.Default; ii.mipmapEnabled = false; ii.alphaIsTransparency = true;
                ii.textureCompression = TextureImporterCompression.Uncompressed; ii.filterMode = FilterMode.Bilinear; ii.npotScale = TextureImporterNPOTScale.None; return;
            }
            if (!path.Contains("Resources/Map/")) return;
            var ti = (TextureImporter)assetImporter;
            ti.textureType = TextureImporterType.Default; ti.npotScale = TextureImporterNPOTScale.None;
            ti.maxTextureSize = 8192; ti.wrapMode = TextureWrapMode.Clamp; ti.isReadable = false;
            if (assetPath.EndsWith("map_districts.png"))
            {
                // district ids (30 / 90 / 150 / 210): exact values, never blended
                ti.textureType = TextureImporterType.SingleChannel;
                var sd = new TextureImporterSettings(); ti.ReadTextureSettings(sd); sd.singleChannelComponent = TextureImporterSingleChannelComponent.Red; ti.SetTextureSettings(sd);
                ti.sRGBTexture = false; ti.mipmapEnabled = false; ti.filterMode = FilterMode.Point; ti.textureCompression = TextureImporterCompression.Uncompressed;
            }
            else if (assetPath.EndsWith("map_city.png"))
            {
                // signed distance to the city boundary (128 = edge, 1 unit = 25 m): numbers, not colours — linear, smooth, uncompressed
                ti.textureType = TextureImporterType.SingleChannel;
                var sc = new TextureImporterSettings(); ti.ReadTextureSettings(sc); sc.singleChannelComponent = TextureImporterSingleChannelComponent.Red; ti.SetTextureSettings(sc);
                ti.sRGBTexture = false; ti.mipmapEnabled = true; ti.filterMode = FilterMode.Trilinear; ti.textureCompression = TextureImporterCompression.Uncompressed;
            }
            else if (assetPath.EndsWith("map_blocks.png"))
            {
                // distance to the road corridors (Tools/twin_gen/gen_blocks.py): one channel of numbers, smooth filtering
                ti.textureType = TextureImporterType.SingleChannel;
                var st = new TextureImporterSettings(); ti.ReadTextureSettings(st); st.singleChannelComponent = TextureImporterSingleChannelComponent.Red; ti.SetTextureSettings(st);
                ti.sRGBTexture = false; ti.mipmapEnabled = true; ti.filterMode = FilterMode.Trilinear; ti.textureCompression = TextureImporterCompression.CompressedHQ;
            }
            else if (assetPath.EndsWith("map_dev.png"))
            {
                ti.sRGBTexture = false; ti.mipmapEnabled = false; ti.filterMode = FilterMode.Bilinear;
                ti.textureCompression = TextureImporterCompression.Uncompressed; ti.alphaSource = TextureImporterAlphaSource.None;
            }
            else
            {
                ti.sRGBTexture = true; ti.mipmapEnabled = true; ti.anisoLevel = 8; ti.filterMode = FilterMode.Trilinear;
                ti.textureCompression = TextureImporterCompression.CompressedHQ;
            }
        }
    }
}
