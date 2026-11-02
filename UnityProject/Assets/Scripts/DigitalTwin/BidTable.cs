using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Size of every per-building lookup the city shader reads by building number (bid): _AlatauYearTex, _AlatauStateTex,
    /// _AlatauGeoTex, _AlatauTintTex, _AlatauStyleTex, _AlatauHideTex, _AlatauRoofTex. Texel (bid % W, bid / W); AlatauLit.shader
    /// computes the same uv (tuv: u over W = 256, v over H = 512), so W and H here and there must stay equal.
    /// 256 × 512 = 131,072 buildings (bids 0 … 131,071). The mesh carries bid + 1 in uv2.y as a float (exact up to 2^24).
    /// A base with fewer than 65,536 buildings fills only the lower half and looks exactly as with the old 256 × 256 table.</summary>
    public static class BidTable
    {
        public const int W = 256, H = 512, N = W * H;

        /// <summary>A point-sampled, clamped, mip-less lookup of the table size.</summary>
        public static Texture2D New(TextureFormat format, string name, bool linear = true) =>
            new Texture2D(W, H, format, false, linear) { name = name, filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };

        public static bool Has(int bid) => bid >= 0 && bid < N;
    }
}
