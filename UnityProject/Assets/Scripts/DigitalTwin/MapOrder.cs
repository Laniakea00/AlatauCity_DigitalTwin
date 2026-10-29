using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Buildings of the base data that must not stand on the map (Resources/Landmarks/map_order.json, made by the w6 survey):
    /// 1 — the footprint lies on a road carriageway (more than a quarter of it, or over 150 m²);
    /// 2 — an existing building within 6 m of a new one of the plan: it is cleared the year before the new one rises;
    /// 3 — a generated filler building that doubles a master-plan building;
    /// 4 — a low existing shed standing alone in a field the plan builds up (under 8 existing buildings within 150 m, 3+ new ones within
    ///     300 m): cleared the year before the first new one rises (whole villages are kept).
    /// Code per building as in the landmark plots: 1 never shown, n &gt; 1 gone from the year 2000 + n. They are clipped by AlatauLit
    /// (merged into _AlatauHideTex) and count as hidden in LandmarkSystem.IsHiddenBid, so pick and camera rays pass through them.</summary>
    public static class MapOrder
    {
        [System.Serializable] class Data { public int[] b; public int[] c; public int[] r; }
        static byte[] code; static bool tried;
        public static int Count { get; private set; }
        public static int OnRoad { get; private set; }
        public static int Cleared { get; private set; }
        public static int Doubles { get; private set; }
        public static int Sheds { get; private set; }

        static void Load()
        {
            if (tried) return; tried = true;
            var ta = Resources.Load<TextAsset>("Landmarks/map_order"); if (ta == null) return;
            Data d = null; try { d = JsonUtility.FromJson<Data>(ta.text); } catch (System.Exception e) { Debug.LogWarning("[Alatau] map order: " + e.Message); }
            if (d == null || d.b == null || d.c == null || d.c.Length != d.b.Length) return;
            code = new byte[256 * 256];
            for (int i = 0; i < d.b.Length; i++)
            {
                int bid = d.b[i]; if (bid < 0 || bid >= code.Length) continue;
                code[bid] = (byte)Mathf.Clamp(d.c[i], 1, 254); Count++;
                int r = d.r != null && i < d.r.Length ? d.r[i] : 0;
                if (r == 1) OnRoad++; else if (r == 2) Cleared++; else if (r == 3) Doubles++; else if (r == 4) Sheds++;
            }
        }

        /// <summary>Is the building removed from the map in the year shown?</summary>
        public static bool Removed(int bid)
        {
            Load(); if (code == null || bid < 0 || bid >= code.Length) return false;
            byte c = code[bid]; return c != 0 && (c == 1 || TwinState.Year >= 2000 + c);
        }

        /// <summary>Merge into the hidden-buildings table of the landmark plots (a smaller code wins: hidden earlier).</summary>
        static bool Merge()
        {
            Load(); if (code == null) return true;
            var tex = Shader.GetGlobalTexture("_AlatauHideTex") as Texture2D;
            if (tex == null || tex.width != 256 || tex.height != 256 || !tex.isReadable) return false;
            var px = tex.GetPixelData<byte>(0);
            if (px.Length < code.Length) return false;
            int n = 0;
            for (int i = 0; i < code.Length; i++)
            {
                byte c = code[i]; if (c == 0) continue;
                if (px[i] == 0 || c < px[i]) { px[i] = c; n++; }
            }
            tex.Apply(false, false);
            Debug.Log(string.Format("[Alatau] map order: {0} buildings removed ({1} on a road, {2} cleared for a new building, {3} doubles, {4} lone sheds in built-up fields); {5} added to the hidden table",
                Count, OnRoad, Cleared, Doubles, Sheds, n));
            return true;
        }

        class Runner : MonoBehaviour
        {
            int tries;
            void Update()
            {
                if (Merge() || ++tries > 600) Destroy(gameObject);
            }
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { var go = new GameObject("Map order (removed buildings)"); go.AddComponent<Runner>(); }
    }
}
