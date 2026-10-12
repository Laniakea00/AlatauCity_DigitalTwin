using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using AlatauCity.DigitalTwin;

namespace AlatauCity.EditorTools
{
    /// <summary>Builds the Alatau City scene from the QTwin Blender model (Alatau_City_3D.blend), exported to compact binaries:
    /// terrain (50 m grid + master-plan zoning map), 57,690 buildings by year, transport/rivers/district outlines, labels.
    /// Everything is meshed here (UInt32, flat normals) — no FBX/OBJ import.</summary>
    [InitializeOnLoad]
    public static class AlatauCityBuilder
    {
        const string Data = "Assets/CityData/", Gen = "Assets/Generated/", ScenePath = "Assets/Scenes/AlatauCity.unity";

        // the first-open check (city built, scene open, quality, Game view) lives in AlatauProjectSetup
        static AlatauCityBuilder() { }

        [System.Serializable] class PalEntry { public string name; public float[] rgb; }
        [System.Serializable] class CamEntry { public string name; public float[] pos; public float[] fwd; public float lens; }
        [System.Serializable] class TerrainMeta { public int nx, ny; public float step, x0, z0, u_a, u_b, v_a, v_b, zmin, zmax; public string texture; }
        [System.Serializable] class Meta { public TerrainMeta terrain; public PalEntry[] palette; public CamEntry[] cameras; }

        [MenuItem("Alatau City/Rebuild Scene", priority = 1)]
        public static void Build()
        {
            if (EditorApplication.isPlaying) { EditorApplication.isPlaying = false; EditorApplication.delayCall += Build; return; }
            try
            {
                EditorUtility.DisplayProgressBar("Alatau City", "Preparing", 0f);
                var meta = JsonUtility.FromJson<Meta>(File.ReadAllText(Data + "city_meta.json"));
                var pal = new Color32[meta.palette.Length];
                for (int i = 0; i < pal.Length; i++) { var c = meta.palette[i].rgb; pal[i] = new Color(c[0], c[1], c[2], 1f); }

                if (AssetDatabase.IsValidFolder("Assets/Generated")) AssetDatabase.DeleteAsset("Assets/Generated");
                AssetDatabase.CreateFolder("Assets", "Generated");
                if (!AssetDatabase.IsValidFolder("Assets/Scenes")) AssetDatabase.CreateFolder("Assets", "Scenes");
                QualitySettings.shadowDistance = 9000f; QualitySettings.shadowCascades = 4; QualitySettings.shadowResolution = ShadowResolution.VeryHigh;
                QualitySettings.antiAliasing = 4; QualitySettings.anisotropicFiltering = AnisotropicFiltering.ForceEnable;

                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var root = new GameObject("Alatau City");
                var shader = Shader.Find("AlatauCity/Lit");

                // ---------- services ----------
                var twin = new GameObject("DigitalTwin"); twin.transform.SetParent(root.transform);
                var db = twin.AddComponent<CityDatabase>(); db.buildings = AssetDatabase.LoadAssetAtPath<TextAsset>(Data + "buildings.csv");
                var cg = twin.AddComponent<CityGround>(); cg.heights = AssetDatabase.LoadAssetAtPath<TextAsset>(Data + "terrain_heights.bytes");
                var tm = meta.terrain; cg.nx = tm.nx; cg.ny = tm.ny; cg.step = tm.step; cg.x0 = tm.x0; cg.z0 = tm.z0; cg.Init();
                twin.AddComponent<CityTimeline>();

                // ---------- terrain + master-plan map ----------
                EditorUtility.DisplayProgressBar("Alatau City", "Terrain", 0.05f);
                BuildTerrain(tm, File.ReadAllBytes(Data + "terrain_heights.bytes"), root.transform, shader);

                // ---------- layers ----------
                var bmat = Mat("Buildings", shader, 0f, 0f, 0f);
                var imat = Mat("Infrastructure", shader, 0.20f, -1f, -2f);
                var lmat = Mat("Labels", shader, 0.85f, -2f, -4f);
                var cmat = new Material(Shader.Find("AlatauCity/Curtain")) { name = "District outline" }; cmat.color = new Color(1, 1, 1, 0.16f); AssetDatabase.CreateAsset(cmat, Gen + "DistrictOutline.mat");
                curtain = cmat;
                ReadLayer(Data + "layer_infrastructure.bytes", pal, imat, root.transform, "Transport, rivers, districts", false, false, 0.1f);
                ReadLayer(Data + "layer_labels.bytes", pal, lmat, root.transform, "Labels", false, false, 0.15f);
                roofInfo = AlatauRoofs.LoadCsv(Data + "buildings.csv");
                ReadLayer(Data + "layer_buildings.bytes", pal, bmat, root.transform, "Buildings", true, true, 0.2f);

                // ---------- light & atmosphere ----------
                var sun = new GameObject("Sun").AddComponent<Light>(); sun.type = LightType.Directional; sun.intensity = 0.85f; sun.color = new Color(1f, 0.97f, 0.92f);
                sun.shadows = LightShadows.Soft; sun.shadowStrength = 0.6f; sun.shadowBias = 0.3f; sun.shadowNormalBias = 0.8f; sun.transform.rotation = Quaternion.Euler(42f, 150f, 0f);
                RenderSettings.sun = sun; RenderSettings.skybox = null;
                RenderSettings.ambientMode = AmbientMode.Trilight; RenderSettings.ambientSkyColor = new Color(0.50f, 0.52f, 0.56f);
                RenderSettings.ambientEquatorColor = new Color(0.44f, 0.44f, 0.44f); RenderSettings.ambientGroundColor = new Color(0.30f, 0.30f, 0.30f);
                RenderSettings.fog = true; RenderSettings.fogMode = FogMode.Linear; RenderSettings.fogColor = new Color(0.23f, 0.24f, 0.26f);
                RenderSettings.fogStartDistance = 70000f; RenderSettings.fogEndDistance = 220000f;

                // ---------- camera & saved views (the cameras of the Blender model) ----------
                var camGo = new GameObject("Main Camera"); camGo.tag = "MainCamera";
                var cam = camGo.AddComponent<Camera>(); cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = new Color(0.23f, 0.24f, 0.26f);
                cam.nearClipPlane = 10f; cam.farClipPlane = 200000f; cam.fieldOfView = 40f; cam.allowMSAA = true;
                camGo.AddComponent<AudioListener>();
                var mc = camGo.AddComponent<MapCamera>();
                var views = new List<MapCamera.View>(); MapCamera.View over = null;
                string[] order = { "Gate District 2050", "Golden core 2050", "Growing core 2050", "Green waterfront 2050", "Tallest planned cluster", "Gate District.001" };
                string[] label = { "Gate", "Golden", "Growing", "Green", "Tallest cluster", "Gate wide" };
                foreach (var c in meta.cameras)
                {
                    var v = MapCamera.MakeView(c.name, new Vector3(c.pos[0], c.pos[1], c.pos[2]), new Vector3(c.fwd[0], c.fwd[1], c.fwd[2]));
                    if (c.name.StartsWith("Overview")) { v.name = "Overview"; over = v; }
                }
                for (int i = 0; i < order.Length; i++)
                    foreach (var c in meta.cameras) if (c.name == order[i]) { var v = MapCamera.MakeView(label[i], new Vector3(c.pos[0], c.pos[1], c.pos[2]), new Vector3(c.fwd[0], c.fwd[1], c.fwd[2])); views.Add(v); }
                if (over == null) over = new MapCamera.View { name = "Overview", target = new Vector3(0, 600, 0), distance = 70000, yaw = 0, pitch = 55 };
                mc.views = views.ToArray(); mc.overview = over;
                var start = views.Count > 0 ? views[0] : over;
                mc.target = start.target; mc.distance = start.distance; mc.yaw = start.yaw; mc.pitch = start.pitch;
                camGo.AddComponent<TwinSelector>();
                var rot = Quaternion.Euler(mc.pitch, mc.yaw, 0); camGo.transform.SetPositionAndRotation(mc.target - rot * Vector3.forward * mc.distance, rot);

                EditorUtility.DisplayProgressBar("Alatau City", "Saving scene", 0.98f);
                EditorSceneManager.SaveScene(scene, ScenePath);
                EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
                AssetDatabase.SaveAssets();
                AlatauProjectSetup.WriteStamp();                    // which city data this build is made from (rebuilt automatically when it changes)
                AlatauProjectSetup.NormalizeGeneratedGuids();      // the same asset ids on every machine: the scene in git stays valid
                var sv = SceneView.lastActiveSceneView; if (sv != null) sv.LookAt(mc.target, rot, mc.distance * 0.5f);
                Debug.Log("[Alatau] Scene built from the QTwin model. Press Play.");
            }
            finally { EditorUtility.ClearProgressBar(); }
        }

        static Material curtain;
        static Dictionary<int, AlatauRoofs.Info> roofInfo;
        static Material Mat(string name, Shader sh, float selfLight, float offF, float offU)
        {
            var m = new Material(sh) { name = name };
            m.SetFloat("_Ambient", selfLight); m.SetFloat("_OffsetF", offF); m.SetFloat("_OffsetU", offU);
            AssetDatabase.CreateAsset(m, Gen + name + ".mat"); return m;
        }

        static Texture2D Tex(string file)
        {
            string p = "Assets/Textures/" + file;
            var ti = (TextureImporter)AssetImporter.GetAtPath(p);
            if (ti != null && (ti.maxTextureSize != 8192 || ti.wrapMode != TextureWrapMode.Clamp))
            { ti.maxTextureSize = 8192; ti.anisoLevel = 8; ti.wrapMode = TextureWrapMode.Clamp; ti.mipmapEnabled = true; ti.textureCompression = TextureImporterCompression.CompressedHQ; ti.npotScale = TextureImporterNPOTScale.None; ti.SaveAndReimport(); }
            return AssetDatabase.LoadAssetAtPath<Texture2D>(p);
        }

        static void BuildTerrain(TerrainMeta m, byte[] bytes, Transform parent, Shader sh)
        {
            var h = new float[m.nx * m.ny]; System.Buffer.BlockCopy(bytes, 0, h, 0, h.Length * 4);
            var v = new Vector3[h.Length]; var uv = new Vector2[h.Length]; var col = new Color32[h.Length];
            var white = new Color32(255, 255, 255, 255);
            for (int r = 0; r < m.ny; r++) for (int c = 0; c < m.nx; c++)
            {
                int i = r * m.nx + c; float x = m.x0 + c * m.step, z = m.z0 + r * m.step;
                v[i] = new Vector3(x, h[i], z); uv[i] = new Vector2(m.u_a * x + m.u_b, m.v_a * z + m.v_b); col[i] = white;
            }
            var idx = new int[(m.nx - 1) * (m.ny - 1) * 6]; int k = 0;
            for (int r = 0; r < m.ny - 1; r++) for (int c = 0; c < m.nx - 1; c++)
            { int a = r * m.nx + c, b = a + 1, d = a + m.nx, e = d + 1; idx[k++] = a; idx[k++] = d; idx[k++] = b; idx[k++] = b; idx[k++] = d; idx[k++] = e; }
            var mesh = new Mesh { name = "Terrain", indexFormat = IndexFormat.UInt32 };
            mesh.vertices = v; mesh.uv = uv; mesh.colors32 = col; mesh.triangles = idx; mesh.RecalculateNormals(); mesh.RecalculateBounds();
            AssetDatabase.CreateAsset(mesh, Gen + "Terrain.asset");
            var mat = new Material(sh) { name = "Terrain master plan" }; mat.mainTexture = Tex(m.texture); mat.SetFloat("_Ambient", 0.10f); mat.color = new Color(0.93f, 0.93f, 0.93f);
            AssetDatabase.CreateAsset(mat, Gen + "Terrain.mat");
            var go = new GameObject("Terrain (master plan map)"); go.transform.SetParent(parent);
            go.AddComponent<MeshFilter>().sharedMesh = mesh; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat; mr.shadowCastingMode = ShadowCastingMode.Off;
            go.AddComponent<MeshCollider>().sharedMesh = mesh;
            GameObjectUtility.SetStaticEditorFlags(go, StaticEditorFlags.BatchingStatic);
        }

        /// record: u16 nameLen, name utf8, u8 kind, i32 nv, i32 nt, f32 verts[nv*3], u32 tris[nt*3], u8 col[nt], u16 year[nt], i32 bid[nt]
        static void ReadLayer(string path, Color32[] pal, Material mat, Transform parent, string groupName, bool colliders, bool castShadows, float prog)
        {
            var group = new GameObject(groupName).transform; group.SetParent(parent);
            var subGroups = new Dictionary<string, Transform>();
            using (var br = new BinaryReader(File.OpenRead(path)))
            {
                if (Encoding.ASCII.GetString(br.ReadBytes(4)) != "AQL1") throw new System.Exception(path + ": bad header");
                int count = br.ReadInt32();
                for (int o = 0; o < count; o++)
                {
                    string name = Encoding.UTF8.GetString(br.ReadBytes(br.ReadUInt16()));
                    EditorUtility.DisplayProgressBar("Alatau City", $"{groupName}: {name}", prog + 0.75f * o / Mathf.Max(1, count) * (colliders ? 1f : 0.1f));
                    br.ReadByte(); int nv = br.ReadInt32(), nt = br.ReadInt32();
                    var V = new Vector3[nv]; for (int i = 0; i < nv; i++) V[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle());
                    var T = new int[nt * 3]; for (int i = 0; i < nt * 3; i++) T[i] = (int)br.ReadUInt32();
                    var col = br.ReadBytes(nt);
                    var yr = new ushort[nt]; for (int i = 0; i < nt; i++) yr[i] = br.ReadUInt16();
                    var bid = new int[nt]; for (int i = 0; i < nt; i++) bid[i] = br.ReadInt32();
                    if (nt == 0) continue;
                    // walls of one building that lie in one plane are measured together: where the wall starts and how long it is.
                    // The film look fits whole window bays into that length (uv = metres from the start, length; 0 = not a wall).
                    var runs = new Dictionary<long, Vector2>(); var runKey = new long[nt];
                    for (int t = 0; t < nt; t++)
                    {
                        Vector3 a = V[T[t * 3]], b = V[T[t * 3 + 1]], c = V[T[t * 3 + 2]];
                        var n = Vector3.Cross(b - a, c - a); float len = n.magnitude; if (len < 1e-9f) { runKey[t] = long.MinValue; continue; }
                        n /= len; if (Mathf.Abs(n.y) > 0.35f) { runKey[t] = long.MinValue; continue; }
                        var h = new Vector3(n.x, 0, n.z).normalized; var along = new Vector3(-h.z, 0, h.x);
                        long key = ((long)(bid[t] + 1) << 34) ^ ((long)(Mathf.RoundToInt(h.x * 120f) + 128) << 26) ^ ((long)(Mathf.RoundToInt(h.z * 120f) + 128) << 18) ^ (long)(Mathf.RoundToInt(Vector3.Dot(h, a) * 4f) & 0x3FFFF);
                        runKey[t] = key;
                        float u0 = Vector3.Dot(along, a), u1 = Vector3.Dot(along, b), u2 = Vector3.Dot(along, c);
                        float lo = Mathf.Min(u0, Mathf.Min(u1, u2)), hi = Mathf.Max(u0, Mathf.Max(u1, u2));
                        if (runs.TryGetValue(key, out var r)) runs[key] = new Vector2(Mathf.Min(r.x, lo), Mathf.Max(r.y, hi)); else runs[key] = new Vector2(lo, hi);
                    }
                    // unweld -> flat normals; uv2 = (year, bid+1)
                    // buildings also get what stands on their roofs (parapets, crowns, plant, tile roofs): see AlatauRoofs
                    var extra = colliders && roofInfo != null ? AlatauRoofs.Build(V, T, col, yr, bid, roofInfo) : null; int ne = extra != null ? extra.Count : 0, na = nt + ne;
                    var pv = new Vector3[na * 3]; var pn = new Vector3[na * 3]; var pc = new Color32[na * 3]; var pi = new Vector2[na * 3]; var tri = new int[na * 3];
                    var pw = new Vector2[na * 3];
                    for (int t = 0; t < nt; t++)
                    {
                        Vector3 a = V[T[t * 3]], b = V[T[t * 3 + 1]], c = V[T[t * 3 + 2]];
                        var n = Vector3.Cross(b - a, c - a); float len = n.magnitude; n = len > 1e-9f ? n / len : Vector3.up;
                        var cc = pal[Mathf.Min(col[t], pal.Length - 1)]; var inf = new Vector2(yr[t], bid[t] + 1);
                        int j = t * 3; pv[j] = a; pv[j + 1] = b; pv[j + 2] = c;
                        pn[j] = pn[j + 1] = pn[j + 2] = n; pc[j] = pc[j + 1] = pc[j + 2] = cc; pi[j] = pi[j + 1] = pi[j + 2] = inf;
                        tri[j] = j; tri[j + 1] = j + 1; tri[j + 2] = j + 2;
                        if (runKey[t] != long.MinValue)
                        {
                            var h = new Vector3(n.x, 0, n.z).normalized; var along = new Vector3(-h.z, 0, h.x); var r = runs[runKey[t]]; float wl = Mathf.Max(r.y - r.x, 0.06f);
                            pw[j] = new Vector2(Vector3.Dot(along, a) - r.x, wl); pw[j + 1] = new Vector2(Vector3.Dot(along, b) - r.x, wl); pw[j + 2] = new Vector2(Vector3.Dot(along, c) - r.x, wl);
                        }
                    }
                    for (int t = 0; t < ne; t++)
                    {
                        var x = extra[t]; var n = Vector3.Cross(x.b - x.a, x.c - x.a).normalized;
                        var cc = pal[Mathf.Min(x.col, pal.Length - 1)]; var inf = new Vector2(x.year, x.bid + 1); var part = new Vector2(0, -x.part);
                        int j = (nt + t) * 3; pv[j] = x.a; pv[j + 1] = x.b; pv[j + 2] = x.c;
                        pn[j] = pn[j + 1] = pn[j + 2] = n; pc[j] = pc[j + 1] = pc[j + 2] = cc; pi[j] = pi[j + 1] = pi[j + 2] = inf; pw[j] = pw[j + 1] = pw[j + 2] = part;
                        tri[j] = j; tri[j + 1] = j + 1; tri[j + 2] = j + 2;
                    }
                    var mesh = new Mesh { name = Safe(name), indexFormat = IndexFormat.UInt32 };
                    mesh.vertices = pv; mesh.normals = pn; mesh.colors32 = pc; mesh.SetUVs(0, pw); mesh.SetUVs(1, pi); mesh.triangles = tri; mesh.RecalculateBounds();
                    AssetDatabase.CreateAsset(mesh, Gen + groupName.Split(',')[0].Replace(" ", "") + "_" + Safe(name) + ".asset");
                    // group buildings by year band, like the Blender collections
                    Transform g = group;
                    if (colliders)
                    {
                        string band = name.StartsWith("Existing") ? "Existing today (OpenStreetMap)" : int.TryParse(name.Split(' ')[0], out int y) ? (y <= 2030 ? "Built 2026-2030" : y <= 2040 ? "Built 2031-2040" : "Built 2041-2050") : "Other";
                        if (!subGroups.TryGetValue(band, out g)) { g = new GameObject(band).transform; g.SetParent(group); subGroups[band] = g; }
                    }
                    var go = new GameObject(name); go.transform.SetParent(g);
                    go.AddComponent<MeshFilter>().sharedMesh = mesh; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = name.Contains("District boundary") && curtain != null ? curtain : mat;
                    mr.shadowCastingMode = castShadows ? ShadowCastingMode.On : ShadowCastingMode.Off; mr.receiveShadows = true;
                    if (colliders) { go.AddComponent<MeshCollider>().sharedMesh = mesh; go.AddComponent<BuildingChunk>(); }
                }
            }
        }
        static string Safe(string s) { var sb = new StringBuilder(); foreach (var ch in s) sb.Append(char.IsLetterOrDigit(ch) || ch == '_' || ch == '-' ? ch : '_'); return sb.ToString(); }
    }
}
