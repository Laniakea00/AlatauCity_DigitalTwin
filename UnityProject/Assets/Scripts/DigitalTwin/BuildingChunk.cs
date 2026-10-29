using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Merged building mesh. Triangle -> building id is read from uv2.y of the (unwelded) triangle.
    /// It also tells the film look which way each building is turned: the main direction of its walls (modulo 90°), so that roof
    /// membranes, plant, solar rows and metal ribs drawn by AlatauFilm.cginc run along the building and not along the map grid.
    /// One chunk is read per frame after start; the result is the global _AlatauRoofTex (256×256, bid → r = angle / 90° + 0.5,
    /// a = 1 when known) with _AlatauRoofOn = 1 once the first chunk is in.</summary>
    [RequireComponent(typeof(MeshFilter))]
    public class BuildingChunk : MonoBehaviour
    {
        Vector2[] info;
        public int BuildingAt(int triangle)
        {
            if (info == null) { var m = GetComponent<MeshFilter>().sharedMesh; if (m == null || !m.isReadable) return -1; var l = new System.Collections.Generic.List<Vector2>(); m.GetUVs(1, l); info = l.ToArray(); }
            int v = triangle * 3; if (triangle < 0 || v >= info.Length) return -1;
            return Mathf.RoundToInt(info[v].y) - 1;
        }
        public float YearAt(int triangle) { BuildingAt(0); int v = triangle * 3; return info != null && v >= 0 && v < info.Length ? info[v].x : 0; }

        // ---------------- building orientation for the roofs of the film look
        static Texture2D roofTex; static Color32[] roofPx; static float[] accC, accS; static int lastFrame = -1;
        bool oriented;

        void Update()
        {
            if (oriented) { enabled = false; return; }
            if (Time.frameCount == lastFrame) return;                 // one chunk per frame, whoever comes first
            lastFrame = Time.frameCount; oriented = true; enabled = false;
            try { Orient(); } catch (System.Exception e) { Debug.LogWarning("[Alatau] roof orientation: " + e.Message); }
        }

        void Orient()
        {
            var mf = GetComponent<MeshFilter>(); var m = mf != null ? mf.sharedMesh : null;
            if (m == null || !m.isReadable) return;
            var V = m.vertices; var T = m.triangles; var ids = new System.Collections.Generic.List<Vector2>(); m.GetUVs(1, ids);
            if (ids.Count != V.Length) return;
            const int N = 256 * 256;
            if (roofTex == null)
            {
                roofPx = new Color32[N]; accC = new float[N]; accS = new float[N];
                for (int i = 0; i < N; i++) roofPx[i] = new Color32(128, 0, 0, 0);
                roofTex = new Texture2D(256, 256, TextureFormat.RGBA32, false, true) { name = "Alatau roof orientation", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            }
            int lo = int.MaxValue, hi = -1;
            for (int t = 0; t + 2 < T.Length; t += 3)
            {
                int ia = T[t]; Vector3 a = V[ia], b = V[T[t + 1]], c = V[T[t + 2]];
                Vector3 n = Vector3.Cross(b - a, c - a); float len = n.magnitude; if (len < 1e-4f) continue;
                if (Mathf.Abs(n.y) > 0.2f * len) continue;                    // walls only
                int bid = Mathf.RoundToInt(ids[ia].y) - 1; if (bid < 0 || bid >= N) continue;
                float ang = Mathf.Atan2(n.z, n.x) * 4f;                        // modulo 90°: four times the angle on the circle
                accC[bid] += Mathf.Cos(ang) * len; accS[bid] += Mathf.Sin(ang) * len;
                if (bid < lo) lo = bid; if (bid > hi) hi = bid;
            }
            for (int bid = lo; bid <= hi && bid >= 0; bid++)
            {
                float C = accC[bid], S = accS[bid]; if (C * C + S * S < 1e-6f) continue;
                float q = Mathf.Atan2(S, C) * 0.25f / (Mathf.PI * 0.5f) + 0.5f;     // (-45° .. 45°] → 0 .. 1
                roofPx[bid] = new Color32((byte)Mathf.Clamp(Mathf.RoundToInt(q * 255f), 0, 255), 0, 0, 255);
            }
            roofTex.SetPixels32(roofPx); roofTex.Apply(false, false);
            Shader.SetGlobalTexture("_AlatauRoofTex", roofTex); Shader.SetGlobalFloat("_AlatauRoofOn", 1f);
        }
    }
}
