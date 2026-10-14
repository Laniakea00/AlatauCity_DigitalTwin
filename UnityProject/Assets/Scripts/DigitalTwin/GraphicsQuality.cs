using System;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Graphics quality of the twin: three levels and «Авто». The level sets how far and how sharp the shadows are, the
    /// antialiasing, the picture finish (ambient occlusion, depth of field, bloom), the level of detail, how far the trees are drawn
    /// and how large the extra views (monitoring, site cameras) are rendered. «Авто» starts from what the computer is (a laptop GPU,
    /// a browser build → lower) and steps down by itself while frames take longer than 26 ms; it never steps up on its own.
    /// F9 or the chip in the header: Авто → Высокое → Среднее → Низкое. The choice is remembered between runs.</summary>
    public class GraphicsQuality : MonoBehaviour
    {
        public enum Tier { Low = 0, Medium = 1, High = 2 }
        public static GraphicsQuality Instance;
        public static Tier Level { get; private set; } = Tier.High;
        public static bool Auto { get; private set; } = true;
        public static event Action OnChanged;

        // ---- what a level means (read by FilmLook, FilmPost, FilmTrees, the monitoring)
        /// <summary>Furthest shadow distance, metres (the film look scales it with the camera distance up to this).</summary>
        public static float MaxShadow => Level == Tier.High ? 6500f : Level == Tier.Medium ? 2600f : 1100f;
        public static bool Ao => Level != Tier.Low;
        public static bool Dof => Level == Tier.High;
        public static bool Bloom => Level != Tier.Low;
        /// <summary>Share of the trees' draw radius; and whether the near trees cast shadows.</summary>
        public static float TreeRange => Level == Tier.High ? 1f : Level == Tier.Medium ? 0.7f : 0.45f;
        public static bool TreeShadows => Level != Tier.Low;
        /// <summary>Scale of the monitoring view's picture and antialiasing of the extra views.</summary>
        public static float ViewScale => Level == Tier.High ? 1f : Level == Tier.Medium ? 0.8f : 0.6f;
        public static int ViewMsaa => Level == Tier.High ? 4 : Level == Tier.Medium ? 2 : 1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) { var g = new GameObject("Graphics quality"); DontDestroyOnLoad(g); g.AddComponent<GraphicsQuality>(); } }

        float window, sum; int n; float since, hold = 12f;

        void Awake()
        {
            Instance = this;
            string saved = PlayerPrefs.GetString("alatau_gfx", "auto");
            if (saved == "auto" || !int.TryParse(saved, out int t) || t < 0 || t > 2) { Auto = true; Level = Guess(); }
            else { Auto = false; Level = (Tier)t; }
            Apply();
        }

        /// <summary>Where «Авто» starts: a browser build or a weak / integrated GPU — lower; a large discrete GPU — high.</summary>
        static Tier Guess()
        {
            if (Application.platform == RuntimePlatform.WebGLPlayer) return Tier.Low;
            int vram = SystemInfo.graphicsMemorySize; string dev = (SystemInfo.graphicsDeviceName ?? "").ToLowerInvariant();
            // graphics built into the processor (Intel UHD / Iris, AMD Radeon Graphics / Vega) — low; a laptop card ("Laptop GPU") or a
            // card with little memory — medium; a large desktop card — high. «Авто» then steps down by itself if it is still too slow.
            bool integrated = dev.Contains("intel") || dev.Contains("uhd") || dev.Contains("iris") || dev.Contains("radeon(tm) graphics") || dev.Contains("radeon graphics") || dev.Contains("vega");
            if (integrated || vram < 3000) return Tier.Low;
            if (dev.Contains("laptop") || dev.Contains("mobile") || dev.Contains("max-q") || vram < 7000) return Tier.Medium;
            return Tier.High;
        }

        public static void Set(Tier t, bool auto)
        {
            Auto = auto; Level = t;
            PlayerPrefs.SetString("alatau_gfx", auto ? "auto" : ((int)t).ToString());
            if (Instance != null) { Instance.hold = 8f; Instance.since = 0f; Instance.sum = 0f; Instance.n = 0; Instance.window = 0f; }
            Apply();
        }
        /// <summary>Авто → Высокое → Среднее → Низкое → Авто.</summary>
        public static void Cycle()
        {
            if (Auto) Set(Tier.High, false);
            else if (Level == Tier.Low) Set(Guess(), true);
            else Set(Level - 1, false);
        }
        public static string Name => (Auto ? "Авто · " : "") + (Level == Tier.High ? "высокое" : Level == Tier.Medium ? "среднее" : "низкое");

        static void Apply()
        {
            QualitySettings.shadows = ShadowQuality.All;
            QualitySettings.shadowResolution = Level == Tier.High ? ShadowResolution.High : Level == Tier.Medium ? ShadowResolution.Medium : ShadowResolution.Low;
            QualitySettings.shadowCascades = Level == Tier.High ? 4 : Level == Tier.Medium ? 2 : 1;
            QualitySettings.antiAliasing = Level == Tier.High ? 4 : Level == Tier.Medium ? 2 : 0;
            QualitySettings.lodBias = Level == Tier.High ? 2f : Level == Tier.Medium ? 1.3f : 0.8f;
            QualitySettings.pixelLightCount = Level == Tier.Low ? 1 : 4;
            QualitySettings.anisotropicFiltering = Level == Tier.Low ? AnisotropicFiltering.Disable : AnisotropicFiltering.Enable;
            QualitySettings.softParticles = Level != Tier.Low;
            QualitySettings.shadowDistance = Mathf.Min(QualitySettings.shadowDistance, MaxShadow);
            TerrainLod.Want(Level == Tier.High ? 1 : Level == Tier.Medium ? 2 : 3);
            OnChanged?.Invoke();
            Debug.Log("[Alatau] графика: " + Name);
        }

        void Update()
        {
            if (!MapCamera.Typing && Input.GetKeyDown(KeyCode.F9)) Cycle();
            // the coarse ground is made from the ground as it is after the plots are levelled and the map is painted
            if (TerrainLod.Pending && Landmarks.LandmarkSystem.Instance != null && Landmarks.LandmarkSystem.Instance.Ready && Time.timeSinceLevelLoad > 3f) TerrainLod.Apply();
            if (!Auto || Level == Tier.Low || PerfProbe.Recording) return;
            // «Авто»: a step down while the frames stay slow (after the start and after each change it waits a few seconds)
            float dt = Time.unscaledDeltaTime; since += dt;
            if (since < hold) return;
            if (dt > 0.5f) return;                               // a hitch (loading, a window opened) is not the steady frame rate
            sum += dt; n++; window += dt;
            if (window < 4f) return;
            float avg = sum / Mathf.Max(n, 1); sum = 0f; n = 0; window = 0f;
            if (avg > 0.026f) { since = 0f; hold = 6f; Level = Level - 1; Apply(); }
        }
    }
}

namespace AlatauCity.DigitalTwin
{
    /// <summary>The ground of the master plan is one mesh on the 50 m height grid (873 × 1235 points, 2.15 M triangles). On the lower
    /// graphics levels a coarser copy is drawn — every 2nd (100 m) or 3rd (150 m) point, 4 or 9 times fewer triangles; the picking collider
    /// keeps the full mesh. Only when the mesh is that regular grid and readable; otherwise the ground stays as it is.</summary>
    public static class TerrainLod
    {
        static MeshFilter mf; static Mesh full; static readonly UnityEngine.Mesh[] coarse = new Mesh[4]; static bool tried, ok; static int nx, nz;

        static int want = 1, applied = 1;
        public static bool Pending => want != applied && !(tried && !ok);
        public static void Want(int step) { want = Mathf.Clamp(step, 1, 3); }
        public static void Apply()
        {
            if (!Init()) return;
            int step = want; applied = want;
            var m = step == 1 ? full : coarse[step] != null ? coarse[step] : (coarse[step] = Build(step));
            if (m != null && mf.sharedMesh != m) mf.sharedMesh = m;
        }

        static bool Init()
        {
            if (tried) return ok; tried = true;
            var go = GameObject.Find("Terrain (master plan map)"); mf = go != null ? go.GetComponent<MeshFilter>() : null;
            full = mf != null ? mf.sharedMesh : null;
            if (full == null || !full.isReadable || full.subMeshCount != 1) { Debug.Log("[Alatau] ground: no coarse copy (mesh missing or not readable)"); return ok = false; }
            var v = full.vertices; nx = 873; nz = 1235;
            if (v.Length != nx * nz) { Debug.Log($"[Alatau] ground: {v.Length} points, not the 873 × 1235 grid — no coarse copy"); return ok = false; }
            // row-major along x? the second point is one step east, the next row one step north
            var dx = v[1] - v[0]; var dz = v[nx] - v[0];
            bool rows = Mathf.Abs(dx.z) < 1f && Mathf.Abs(dx.x) > 10f && Mathf.Abs(dz.x) < 1f && Mathf.Abs(dz.z) > 10f;
            if (!rows) { Debug.Log("[Alatau] ground: point order is not row by row — no coarse copy"); return ok = false; }
            return ok = true;
        }

        static Mesh Build(int s)
        {
            var src = full; int cx = (nx - 1) / s + 1, cz = (nz - 1) / s + 1;
            var map = new int[cx * cz];
            for (int j = 0; j < cz; j++) for (int i = 0; i < cx; i++) map[j * cx + i] = Mathf.Min(j * s, nz - 1) * nx + Mathf.Min(i * s, nx - 1);
            var vs = src.vertices; var ns = src.normals; var cs = src.colors32;
            var nv = new Vector3[map.Length]; var nn = ns.Length == vs.Length ? new Vector3[map.Length] : null; var nc = cs.Length == vs.Length ? new Color32[map.Length] : null;
            var uvs = new System.Collections.Generic.List<Vector4>[4];
            for (int c = 0; c < 4; c++) { var l = new System.Collections.Generic.List<Vector4>(); src.GetUVs(c, l); uvs[c] = l.Count == vs.Length ? l : null; }
            var nuv = new System.Collections.Generic.List<Vector4>[4];
            for (int c = 0; c < 4; c++) if (uvs[c] != null) nuv[c] = new System.Collections.Generic.List<Vector4>(map.Length);
            for (int k = 0; k < map.Length; k++)
            {
                int o = map[k]; nv[k] = vs[o]; if (nn != null) nn[k] = ns[o]; if (nc != null) nc[k] = cs[o];
                for (int c = 0; c < 4; c++) if (nuv[c] != null) nuv[c].Add(uvs[c][o]);
            }
            var tri = new int[(cx - 1) * (cz - 1) * 6]; int t = 0;
            // keep the winding of the original grid (its first triangle tells which way round)
            var it = src.GetIndices(0); bool flip = it.Length >= 3 && Vector3.Cross(vs[it[1]] - vs[it[0]], vs[it[2]] - vs[it[0]]).y < 0f;
            for (int j = 0; j < cz - 1; j++) for (int i = 0; i < cx - 1; i++)
            {
                int a = j * cx + i, b = a + 1, c = a + cx, d = c + 1;
                if (!flip) { tri[t++] = a; tri[t++] = c; tri[t++] = b; tri[t++] = b; tri[t++] = c; tri[t++] = d; }
                else { tri[t++] = a; tri[t++] = b; tri[t++] = c; tri[t++] = b; tri[t++] = d; tri[t++] = c; }
            }
            var m = new Mesh { name = src.name + " · 1/" + s, indexFormat = map.Length > 65000 ? UnityEngine.Rendering.IndexFormat.UInt32 : UnityEngine.Rendering.IndexFormat.UInt16 };
            m.SetVertices(nv); if (nn != null) m.SetNormals(nn); if (nc != null) m.SetColors(nc);
            for (int c = 0; c < 4; c++) if (nuv[c] != null) m.SetUVs(c, nuv[c]);
            m.SetTriangles(tri, 0); m.bounds = src.bounds; if (nn == null) m.RecalculateNormals();
            m.UploadMeshData(true);
            Debug.Log($"[Alatau] ground: coarse copy 1/{s} — {tri.Length / 3:N0} triangles instead of {src.GetIndexCount(0) / 3:N0}");
            return m;
        }
    }
}
