using System.Collections.Generic;
using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Terrain height lookup (50 m grid from the QTwin Blender model). X = east, Z = north, Y = metres a.s.l.</summary>
    public class CityGround : MonoBehaviour
    {
        public TextAsset heights;      // terrain_heights.bytes, float32, row 0 = south, col 0 = west
        public int nx = 873, ny = 1235; public float step = 50f, x0 = -21800f, z0 = -30300f;
        static float[] h; static int NX, NY; static float S, X0, Z0;
        void Awake() { Init(); }
        public void Init()
        {
            if (heights == null) return;
            var b = heights.bytes; h = new float[nx * ny]; System.Buffer.BlockCopy(b, 0, h, 0, Mathf.Min(b.Length, h.Length * 4));
            NX = nx; NY = ny; S = step; X0 = x0; Z0 = z0;
        }
        /// <summary>Levels the ground under a site (oriented rectangle w × d, yaw as Unity's Euler y) to height 'level', with a smooth
        /// transition 'blend' metres wide around it. Changes the lookup and returns the touched grid indices (row * nx + col).</summary>
        public static List<int> Flatten(float cx, float cz, float yawDeg, float w, float d, float level, float blend)
        {
            var touched = new List<int>(); if (h == null) return touched;
            float a = yawDeg * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a), R = Mathf.Sqrt(w * w + d * d) * 0.5f + blend;
            int c0 = Mathf.Max(0, (int)((cx - R - X0) / S)), c1 = Mathf.Min(NX - 1, (int)((cx + R - X0) / S) + 1);
            int r0 = Mathf.Max(0, (int)((cz - R - Z0) / S)), r1 = Mathf.Min(NY - 1, (int)((cz + R - Z0) / S) + 1);
            for (int r = r0; r <= r1; r++) for (int c = c0; c <= c1; c++)
            {
                float x = X0 + c * S - cx, z = Z0 + r * S - cz;
                float u = x * ca - z * sa, v = x * sa + z * ca;                 // local frame of the site
                float ox = Mathf.Max(Mathf.Abs(u) - w * 0.5f, 0f), oz = Mathf.Max(Mathf.Abs(v) - d * 0.5f, 0f);
                float dist = Mathf.Sqrt(ox * ox + oz * oz);
                if (dist > blend) continue;
                float k = 1f - Mathf.SmoothStep(0f, 1f, dist / blend);
                int i = r * NX + c; h[i] = Mathf.Lerp(h[i], level, k); touched.Add(i);
            }
            return touched;
        }
        public static float RawHeight(int i) => h != null && i >= 0 && i < h.Length ? h[i] : 0f;

        public static float HeightAt(float x, float z)
        {
            if (h == null) return 0f;
            float c = Mathf.Clamp((x - X0) / S, 0, NX - 1.001f), r = Mathf.Clamp((z - Z0) / S, 0, NY - 1.001f);
            int c0 = (int)c, r0 = (int)r; float a = c - c0, bb = r - r0; int i = r0 * NX + c0;
            return h[i] * (1 - a) * (1 - bb) + h[i + 1] * a * (1 - bb) + h[i + NX] * (1 - a) * bb + h[i + NX + 1] * a * bb;
        }
    }
}
