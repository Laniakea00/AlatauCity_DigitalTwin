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
                BakeBegin();
                ReadLayer(Data + "layer_buildings.bytes", pal, bmat, root.transform, "Buildings", true, true, 0.2f);
                BakeWrite();

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

        /// <summary>The files of a layer: the file itself, then its parts name_1.bytes, name_2.bytes … while they exist. The merge
        /// (tools/map/export/merge_districts.py) writes the buildings layer in parts of at most 24 MB; older data is one file.</summary>
        public static List<string> LayerParts(string path)
        {
            var l = new List<string>(); if (!File.Exists(path)) return l;
            l.Add(path); string ext = Path.GetExtension(path), stem = path.Substring(0, path.Length - ext.Length);
            for (int k = 1; File.Exists(stem + "_" + k + ext); k++) l.Add(stem + "_" + k + ext);
            return l;
        }

        class AqlObj { public string Name; public Vector3[] V; public int[] T; public byte[] Col; public ushort[] Yr; public int[] Bid; }
        /// <summary>A layer as one list of chunks, from one file or from its parts in order. A chunk cut across parts (its pieces have the
        /// same name) is joined again, so the chunks are the same as from a single file. A building found in two parts means a stale
        /// part from older data: an error, not a doubled city.</summary>
        static List<AqlObj> ReadAql(string path)
        {
            var files = LayerParts(path); if (files.Count == 0) throw new FileNotFoundException(path + " missing");
            var pieces = new List<AqlObj>(); var owner = files.Count > 1 ? new Dictionary<int, int>() : null;
            for (int f = 0; f < files.Count; f++)
                using (var br = new BinaryReader(File.OpenRead(files[f])))
                {
                    if (Encoding.ASCII.GetString(br.ReadBytes(4)) != "AQL1") throw new System.Exception(files[f] + ": bad header");
                    int count = br.ReadInt32();
                    for (int o = 0; o < count; o++)
                    {
                        var x = new AqlObj { Name = Encoding.UTF8.GetString(br.ReadBytes(br.ReadUInt16())) };
                        br.ReadByte(); int nv = br.ReadInt32(), nt = br.ReadInt32();
                        x.V = new Vector3[nv]; for (int i = 0; i < nv; i++) x.V[i] = new Vector3(br.ReadSingle(), br.ReadSingle(), br.ReadSingle());
                        x.T = new int[nt * 3]; for (int i = 0; i < nt * 3; i++) x.T[i] = (int)br.ReadUInt32();
                        x.Col = br.ReadBytes(nt);
                        x.Yr = new ushort[nt]; for (int i = 0; i < nt; i++) x.Yr[i] = br.ReadUInt16();
                        x.Bid = new int[nt]; for (int i = 0; i < nt; i++) x.Bid[i] = br.ReadInt32();
                        if (owner != null)
                            foreach (int b in x.Bid)
                            {
                                if (b < 0) continue;
                                if (!owner.TryGetValue(b, out int g)) owner[b] = f;
                                else if (g != f) throw new System.Exception($"{files[f]}: building {b} is also in {files[g]}. A part left from older data? " +
                                    "Keep only the parts the current data has (see its manifest.json: layer_parts) and rebuild.");
                            }
                        pieces.Add(x);
                    }
                }
            var res = new List<AqlObj>(); var at = new Dictionary<string, int>();
            foreach (var x in pieces)
            {
                if (!at.TryGetValue(x.Name, out int i)) { at[x.Name] = res.Count; res.Add(x); continue; }
                var a = res[i]; int nv0 = a.V.Length;
                var T = new int[a.T.Length + x.T.Length]; a.T.CopyTo(T, 0); for (int k = 0; k < x.T.Length; k++) T[a.T.Length + k] = x.T[k] + nv0;
                res[i] = new AqlObj { Name = a.Name, V = Cat(a.V, x.V), T = T, Col = Cat(a.Col, x.Col), Yr = Cat(a.Yr, x.Yr), Bid = Cat(a.Bid, x.Bid) };
            }
            if (files.Count > 1) Debug.Log($"[Alatau] {Path.GetFileName(path)}: {files.Count} parts, {pieces.Count} pieces → {res.Count} chunks");
            return res;
        }
        static X[] Cat<X>(X[] a, X[] b) { var r = new X[a.Length + b.Length]; a.CopyTo(r, 0); b.CopyTo(r, a.Length); return r; }

        /// <summary>Square tiles (m) the buildings are cut into: one mesh per tile with every year and kind of building in it (the
        /// shader hides what is not built yet, so a mesh per year bought nothing: 1432 chunks, each drawn in every pass, some 3 000 draw
        /// calls a frame on the wide views). Each building goes whole into the tile of its own centre; a chunk of the data spanning the
        /// whole city (37 × 55 km) could never be culled. A tile denser than MaxTileTris is cut in quarters (the collider of a mesh
        /// over 2 M triangles may miss hits, and the roof details add some 2.3 triangles to each one of the data).</summary>
        const float BuildingTile = 3000f;
        const int MaxTileTris = 400000;
        static List<AqlObj> Tiles(List<AqlObj> objs, float tile)
        {
            var byTile = new Dictionary<Vector2Int, List<(AqlObj x, int t, Vector2 c)>>();
            foreach (var x in objs)
            {
                int nt = x.Bid.Length; if (nt == 0) continue;
                var sum = new Dictionary<int, Vector3>(); var n = new Dictionary<int, int>();
                for (int t = 0; t < nt; t++)
                {
                    var c = (x.V[x.T[t * 3]] + x.V[x.T[t * 3 + 1]] + x.V[x.T[t * 3 + 2]]) / 3f;
                    sum[x.Bid[t]] = sum.TryGetValue(x.Bid[t], out var s) ? s + c : c; n[x.Bid[t]] = n.TryGetValue(x.Bid[t], out int k) ? k + 1 : 1;
                }
                var cen = new Dictionary<int, Vector2>();
                foreach (var kv in sum) { var c = kv.Value / n[kv.Key]; cen[kv.Key] = new Vector2(c.x, c.z); }
                for (int t = 0; t < nt; t++)
                {
                    var c = cen[x.Bid[t]]; var k = new Vector2Int(Mathf.FloorToInt(c.x / tile), Mathf.FloorToInt(c.y / tile));
                    if (!byTile.TryGetValue(k, out var l)) byTile[k] = l = new List<(AqlObj, int, Vector2)>(); l.Add((x, t, c));
                }
            }
            var res = new List<AqlObj>();
            foreach (var kv in byTile) Split(kv.Value, kv.Key.x * tile, kv.Key.y * tile, tile, $"Buildings t{kv.Key.x}_{kv.Key.y}", res);
            res.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
            Debug.Log($"[Alatau] buildings: {objs.Count} chunks of the data → {res.Count} tiles of {tile:0} m and less");
            return res;
        }

        static void Split(List<(AqlObj x, int t, Vector2 c)> tris, float x0, float z0, float size, string name, List<AqlObj> res)
        {
            if (tris.Count > MaxTileTris && size > 400f)
            {
                float h = size * 0.5f; var q = new List<(AqlObj, int, Vector2)>[4];
                for (int i = 0; i < 4; i++) q[i] = new List<(AqlObj, int, Vector2)>();
                foreach (var e in tris) q[(e.c.x >= x0 + h ? 1 : 0) + (e.c.y >= z0 + h ? 2 : 0)].Add(e);
                for (int i = 0; i < 4; i++) if (q[i].Count > 0) Split(q[i], x0 + (i & 1) * h, z0 + (i >> 1) * h, h, name + "_" + i, res);
                return;
            }
            {
                // a building's triangles stay together and in their order (the bake keeps one run per building and year)
                var remap = new Dictionary<(AqlObj, int), int>(); var V = new List<Vector3>();
                var T = new int[tris.Count * 3]; var col = new byte[tris.Count]; var yr = new ushort[tris.Count]; var bid = new int[tris.Count];
                for (int i = 0; i < tris.Count; i++)
                {
                    var (x, t, _) = tris[i];
                    for (int j = 0; j < 3; j++) { int v = x.T[t * 3 + j]; if (!remap.TryGetValue((x, v), out int r)) { r = V.Count; remap[(x, v)] = r; V.Add(x.V[v]); } T[i * 3 + j] = r; }
                    col[i] = x.Col[t]; yr[i] = x.Yr[t]; bid[i] = x.Bid[t];
                }
                res.Add(new AqlObj { Name = name, V = V.ToArray(), T = T, Col = col, Yr = yr, Bid = bid });
            }
        }

        /// record: u16 nameLen, name utf8, u8 kind, i32 nv, i32 nt, f32 verts[nv*3], u32 tris[nt*3], u8 col[nt], u16 year[nt], i32 bid[nt]
        /// (the buildings layer may come in parts: ReadAql)
        static void ReadLayer(string path, Color32[] pal, Material mat, Transform parent, string groupName, bool colliders, bool castShadows, float prog)
        {
            var group = new GameObject(groupName).transform; group.SetParent(parent);
            var objs = ReadAql(path);
            if (colliders) objs = Tiles(objs, BuildingTile);
            {
                int count = objs.Count;
                for (int o = 0; o < count; o++)
                {
                    string name = objs[o].Name;
                    EditorUtility.DisplayProgressBar("Alatau City", $"{groupName}: {name}", prog + 0.75f * o / Mathf.Max(1, count) * (colliders ? 1f : 0.1f));
                    var V = objs[o].V; var T = objs[o].T; var col = objs[o].Col; var yr = objs[o].Yr; var bid = objs[o].Bid; int nt = col.Length;
                    objs[o] = null;                                   // the chunk's arrays are freed once it is meshed
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
                    Mesh mesh, colMesh = null;
                    if (colliders)
                    {
                        // buildings: a compact vertex (normal and colour in 4 bytes each, 36 bytes instead of 44), not readable after the
                        // upload (the city keeps no copy of it in memory: what it needs from it is baked into ChunkBake); the collider is a
                        // positions-only mesh with the same triangle order (RaycastHit.triangleIndex → ChunkBake runs)
                        mesh = CompactMesh(Safe(name), pv, pn, pc, pw, pi, nt);
                        colMesh = ColliderMesh(Safe(name) + " collider", pv);
                        Bake(groupName.Split(',')[0].Replace(" ", "") + "_" + Safe(name), name.Contains("houses"), pv, pw, pi);   // the asset's file name: CreateAsset gives it to the mesh
                    }
                    else
                    {
                        mesh = new Mesh { name = Safe(name), indexFormat = IndexFormat.UInt32 };
                        mesh.vertices = pv; mesh.normals = pn; mesh.colors32 = pc; mesh.SetUVs(0, pw); mesh.SetUVs(1, pi); mesh.triangles = tri; mesh.RecalculateBounds();
                    }
                    string assetPath = Gen + groupName.Split(',')[0].Replace(" ", "") + "_" + Safe(name) + ".asset";
                    AssetDatabase.CreateAsset(mesh, assetPath);
                    if (colMesh != null)
                    {
                        AssetDatabase.AddObjectToAsset(colMesh, assetPath);
                        var so = new SerializedObject(mesh); so.FindProperty("m_IsReadable").boolValue = false; so.ApplyModifiedPropertiesWithoutUndo();
                    }
                    var go = new GameObject(name); go.transform.SetParent(group);
                    go.AddComponent<MeshFilter>().sharedMesh = mesh; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = name.Contains("District boundary") && curtain != null ? curtain : mat;
                    if (mesh.subMeshCount == 2) mr.sharedMaterials = new[] { mat, mat };          // bodies, roof details (BuildingChunk)
                    mr.shadowCastingMode = castShadows ? ShadowCastingMode.On : ShadowCastingMode.Off; mr.receiveShadows = true;
                    if (colliders) { go.AddComponent<MeshCollider>().sharedMesh = colMesh; go.AddComponent<BuildingChunk>(); }
                }
            }
        }
        // ---------------------------------------------------------------- compact building meshes and the chunk bake
        [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
        struct CompactVertex { public Vector3 p; public sbyte nx, ny, nz, nw; public Color32 c; public Vector2 uv0, uv1; }

        /// <summary>nt: the triangles of the buildings themselves; what AlatauRoofs adds after them (parapets, crowns, plant, tile roofs) is
        /// a second submesh, which BuildingChunk stops drawing when the chunk is far (its details are under a pixel there).</summary>
        static Mesh CompactMesh(string name, Vector3[] pv, Vector3[] pn, Color32[] pc, Vector2[] pw, Vector2[] pi, int nt)
        {
            int n = pv.Length; var vx = new CompactVertex[n]; var idx = new int[n];
            static sbyte Sn(float v) => (sbyte)Mathf.Clamp(Mathf.RoundToInt(v * 127f), -127, 127);
            for (int i = 0; i < n; i++) { vx[i] = new CompactVertex { p = pv[i], nx = Sn(pn[i].x), ny = Sn(pn[i].y), nz = Sn(pn[i].z), nw = 0, c = pc[i], uv0 = pw[i], uv1 = pi[i] }; idx[i] = i; }
            var m = new Mesh { name = name };
            m.SetVertexBufferParams(n,
                new VertexAttributeDescriptor(VertexAttribute.Position, VertexAttributeFormat.Float32, 3),
                new VertexAttributeDescriptor(VertexAttribute.Normal, VertexAttributeFormat.SNorm8, 4),
                new VertexAttributeDescriptor(VertexAttribute.Color, VertexAttributeFormat.UNorm8, 4),
                new VertexAttributeDescriptor(VertexAttribute.TexCoord0, VertexAttributeFormat.Float32, 2),
                new VertexAttributeDescriptor(VertexAttribute.TexCoord1, VertexAttributeFormat.Float32, 2));
            m.SetVertexBufferData(vx, 0, 0, n);
            m.SetIndexBufferParams(n, IndexFormat.UInt32); m.SetIndexBufferData(idx, 0, 0, n);
            int nb = Mathf.Min(nt * 3, n); trisBody += nb / 3; trisRoof += (n - nb) / 3;
            if (nb < n) { m.subMeshCount = 2; m.SetSubMesh(0, new SubMeshDescriptor(0, nb)); m.SetSubMesh(1, new SubMeshDescriptor(nb, n - nb)); }
            else { m.subMeshCount = 1; m.SetSubMesh(0, new SubMeshDescriptor(0, n)); }
            m.RecalculateBounds();
            return m;
        }

        /// <summary>Positions only, welded (a corner shared by several flat triangles is one vertex), triangles in the render mesh's order.</summary>
        static Mesh ColliderMesh(string name, Vector3[] pv)
        {
            var at = new Dictionary<Vector3, int>(pv.Length / 3); var v = new List<Vector3>(pv.Length / 3); var t = new int[pv.Length];
            for (int i = 0; i < pv.Length; i++) { if (!at.TryGetValue(pv[i], out int k)) { k = v.Count; v.Add(pv[i]); at[pv[i]] = k; } t[i] = k; }
            var m = new Mesh { name = name, indexFormat = v.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            m.SetVertices(v); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }

        static long trisBody, trisRoof;
        static List<(string name, List<(int start, int bid, float year)> runs)> bakeRuns;
        static float[] bakeC, bakeS;
        static List<(int bid, Vector3[] c)> bakeHouses;
        static void BakeBegin() { bakeRuns = new List<(string, List<(int, int, float)>)>(); bakeC = new float[BidTable.N]; bakeS = new float[BidTable.N]; bakeHouses = new List<(int, Vector3[])>(); }

        /// <summary>What the city used to read from a chunk mesh at run time (BuildingChunk, FilmTrees): the runs of triangles of one
        /// building, the wall directions of each building, the ground corners of the generated houses.</summary>
        static void Bake(string mesh, bool houses, Vector3[] pv, Vector2[] pw, Vector2[] pi)
        {
            int nt = pv.Length / 3; var runs = new List<(int, int, float)>();
            int lastBid = int.MinValue; float lastYear = float.NaN;
            for (int t = 0; t < nt; t++)
            {
                int j = t * 3; int bid = Mathf.RoundToInt(pi[j].y) - 1; float yr = pi[j].x;
                if (bid != lastBid || yr != lastYear) { runs.Add((t, bid, yr)); lastBid = bid; lastYear = yr; }
                // walls only: the main wall direction modulo 90° (four times the angle on the circle), as BuildingChunk did at run time
                Vector3 a = pv[j], b = pv[j + 1], c = pv[j + 2]; var n = Vector3.Cross(b - a, c - a); float len = n.magnitude;
                if (len < 1e-4f || Mathf.Abs(n.y) > 0.2f * len || bid < 0 || bid >= BidTable.N) continue;
                float ang = Mathf.Atan2(n.z, n.x) * 4f; bakeC[bid] += Mathf.Cos(ang) * len; bakeS[bid] += Mathf.Sin(ang) * len;
            }
            bakeRuns.Add((mesh, runs));
            if (!houses) return;
            // the house rectangles: the lowest corners of each house (not what stands on its roof), as FilmTrees did at run time
            var low = new Dictionary<int, float>(); var corner = new Dictionary<int, List<Vector3>>();
            for (int i = 0; i < pv.Length; i++) { if (pw[i].y < -0.5f) continue; int b = Mathf.RoundToInt(pi[i].y) - 1; if (!low.TryGetValue(b, out float y) || pv[i].y < y) low[b] = pv[i].y; }
            for (int i = 0; i < pv.Length; i++)
            {
                if (pw[i].y < -0.5f) continue; int b = Mathf.RoundToInt(pi[i].y) - 1; if (pv[i].y > low[b] + 0.15f) continue;
                if (!corner.TryGetValue(b, out var l)) corner[b] = l = new List<Vector3>();
                bool seen = false; foreach (var q in l) if ((q - pv[i]).sqrMagnitude < 0.01f) { seen = true; break; }
                if (!seen) l.Add(pv[i]);
            }
            foreach (var kv in corner) if (kv.Value.Count == 4) bakeHouses.Add((kv.Key, kv.Value.ToArray()));
        }

        static void BakeWrite()
        {
            const string dir = "Assets/Resources/CityBake";
            Directory.CreateDirectory(dir);
            using (var w = new BinaryWriter(File.Create(dir + "/chunks.bytes")))
            {
                w.Write(0x31424341); w.Write(bakeRuns.Count);
                foreach (var (name, runs) in bakeRuns) { w.Write(name); w.Write(runs.Count); foreach (var (st, bid, yr) in runs) { w.Write(st); w.Write(bid); w.Write(yr); } }
                var r = new byte[BidTable.N]; var a = new byte[BidTable.N];
                for (int i = 0; i < BidTable.N; i++)
                {
                    float C = bakeC[i], S = bakeS[i];
                    if (C * C + S * S < 1e-6f) { r[i] = 128; a[i] = 0; continue; }
                    float q = Mathf.Atan2(S, C) * 0.25f / (Mathf.PI * 0.5f) + 0.5f;      // (-45° .. 45°] → 0 .. 1
                    r[i] = (byte)Mathf.Clamp(Mathf.RoundToInt(q * 255f), 0, 255); a[i] = 255;
                }
                w.Write(BidTable.N); w.Write(r); w.Write(a);
                w.Write(bakeHouses.Count);
                foreach (var (bid, c) in bakeHouses) { w.Write(bid); foreach (var v in c) { w.Write(v.x); w.Write(v.y); w.Write(v.z); } }
            }
            AssetDatabase.ImportAsset(dir + "/chunks.bytes");
            Debug.Log($"[Alatau] chunk bake: {bakeRuns.Count} chunks, {bakeHouses.Count} house plots → {dir}/chunks.bytes; triangles: buildings {trisBody:N0}, roof details {trisRoof:N0}");
            trisBody = trisRoof = 0;
            bakeRuns = null; bakeC = bakeS = null; bakeHouses = null;
        }

        static string Safe(string s) { var sb = new StringBuilder(); foreach (var ch in s) sb.Append(char.IsLetterOrDigit(ch) || ch == '_' || ch == '-' ? ch : '_'); return sb.ToString(); }
    }
}
