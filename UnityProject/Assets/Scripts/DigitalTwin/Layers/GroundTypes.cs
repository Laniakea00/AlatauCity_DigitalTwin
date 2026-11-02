using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The ground of the redrawn map: the yard type of every lot of the merged districts (Resources/Map/map_ground.bytes, made by
    /// tools/map/export/ground.py; tools/map CONTRACT §8). Its triangles are drawn into three small render textures that AlatauGround.shader
    /// reads: one over all the data (at most 1024 px on its long side), one of 2048 px round the point the camera looks at (1 to 32 km
    /// across, by the camera's distance) and a fine one of 1024 px (256 m to 2 km) over the ground just in front of the camera, so a lot's
    /// own yard is sharp up close. In those lots the ground draws the yard of its type (lawn round the houses, the aprons, paths,
    /// playgrounds, sports grounds and tracks the data lays out, a village garden, a car park only where the data has one …) instead of the
    /// random yards it paints from the old plan colours. Without the file nothing is made and _AlatauGtOn stays 0: the ground is exactly today's.
    /// Texels: r = type + the hash's top 3 bits, g = angle, b = distance to the nearest piece outline (an outline pass with BlendOp Min over
    /// _W metres, fine and near only: the ground shader draws the edges between the texels straight), a = the piece's year byte. A piece
    /// whose earthworks have not begun by the year of the timeline is left out of the textures (the vertex shader collapses it), so the
    /// ground under it shows until then; the textures are drawn again when the year (in quarters) or the scenario's pace changes.
    /// The triangles are also kept on the CPU (TypeAt, HardAt): the trees and the props ask what ground lies at a point, down to the
    /// 36 × 30 m yard cell the shader draws there (its kind comes from the table CellHash, the same bytes on both sides).
    /// GRD1: 'GRD1', i32 version, f32 x0, z0, x1, z1, i32 chunks; per chunk f32 ox, oz, i32 nv, i32 ni, i32 nr, u16 (qx, qz)[nv]
    /// (metres = o + q / 32), nr runs (i32 first vertex, u8 type, angle, hash, year) up to the next run's first vertex, u16 idx[ni] in
    /// drawing order (later triangles lie on top). Year byte: 0 = the map's own year (map_dev), 1 = always, 26..254 = 2000 + v (base
    /// scenario), 255 = never. A map over the 24 MB part limit continues in map_ground_1.bytes, map_ground_2.bytes …</summary>
    public class GroundTypes : MonoBehaviour
    {
        public static GroundTypes Instance;
        static readonly int OnId = Shader.PropertyToID("_AlatauGtOn"), NearId = Shader.PropertyToID("_AlatauGtNear"), FarId = Shader.PropertyToID("_AlatauGtFar"),
            NearRId = Shader.PropertyToID("_AlatauGtNearR"), FarRId = Shader.PropertyToID("_AlatauGtFarR"), FineId = Shader.PropertyToID("_AlatauGtFine"),
            FineRId = Shader.PropertyToID("_AlatauGtFineR"), NearTId = Shader.PropertyToID("_AlatauGtNearT"), FineTId = Shader.PropertyToID("_AlatauGtFineT"),
            HashId = Shader.PropertyToID("_AlatauGtHash"), WId = Shader.PropertyToID("_AlatauGtW"), YearId = Shader.PropertyToID("_AlatauGtYear"),
            MatWId = Shader.PropertyToID("_W"), TlYearId = Shader.PropertyToID("_AlatauYear"), TlYearFId = Shader.PropertyToID("_AlatauYearF"),
            TlGrowId = Shader.PropertyToID("_AlatauGrow"), TlDevKId = Shader.PropertyToID("_AlatauDevK");
        const int NearPx = 2048, FarPx = 1024, FinePx = 1024;
        const float MinWin = 1024f, MaxWin = 32768f, Q = 1f / 32f, Bucket = 32f, TileQ = 2000f * 32f;

        /// <summary>A chunk of triangles: its mesh for the render textures and a CPU copy for the point queries (buckets made on first use).</summary>
        class Chunk
        {
            public Mesh M; public Rect R; public float ox, oz; public ushort[] q, idx; public int[] runFirst; public byte[] runT, runA, runH, runY;
            public readonly List<Mesh> outline = new List<Mesh>();
            public int[][] buckets; public int bw, bh;
        }
        readonly List<Chunk> chunks = new List<Chunk>();
        Rect data; Material mat; RenderTexture near, far, fine; Rect farWin; Vector3 nearKey = new Vector3(float.NaN, 0f, 0f), fineKey = new Vector3(float.NaN, 0f, 0f);
        int vertices, triangles, segments; long outlineBytes; bool farDrawn; Vector2 yearKey = new Vector2(float.NaN, 0f);
        Texture2D hashTex; float fineW = 2f, nearW = 2f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (Instance != null) return;
            var ta = Resources.Load<TextAsset>("Map/map_ground"); if (ta == null) return;          // no file: today's ground, nothing to add
            var sh = Shader.Find("Hidden/AlatauCity/GroundTypes");
            if (sh == null) { Debug.LogWarning("[Alatau] ground types: shader Hidden/AlatauCity/GroundTypes missing"); Resources.UnloadAsset(ta); return; }
            var go = new GameObject("Ground types (map data)"); var g = go.AddComponent<GroundTypes>(); g.mat = new Material(sh) { name = "Ground types" };
            // a big map comes in parts: map_ground, map_ground_1, map_ground_2 … (each a whole GRD1 file), read in order until one is missing
            bool ok = true;
            for (int part = 0; ta != null && ok; part++)
            {
                ok = g.Load(ta.bytes, part); Resources.UnloadAsset(ta);
                ta = ok ? Resources.Load<TextAsset>("Map/map_ground_" + (part + 1)) : null;
            }
            if (!ok || g.chunks.Count == 0) { Destroy(go); return; }
            Instance = g;
        }

        static int I32(byte[] b, ref int o) { int v = BitConverter.ToInt32(b, o); o += 4; return v; }
        static float F32(byte[] b, ref int o) { float v = BitConverter.ToSingle(b, o); o += 4; return v; }

        bool Load(byte[] b, int part)
        {
            string file = part == 0 ? "map_ground.bytes" : "map_ground_" + part + ".bytes";
            try
            {
                if (b == null || b.Length < 32 || b[0] != 'G' || b[1] != 'R' || b[2] != 'D' || b[3] != '1') { Debug.LogWarning("[Alatau] " + file + ": not GRD1"); return false; }
                int o = 4; I32(b, ref o);
                float x0 = F32(b, ref o), z0 = F32(b, ref o), x1 = F32(b, ref o), z1 = F32(b, ref o); int n = I32(b, ref o);
                var hb = Rect.MinMaxRect(x0, z0, x1, z1);
                data = part == 0 ? hb : Rect.MinMaxRect(Mathf.Min(data.xMin, hb.xMin), Mathf.Min(data.yMin, hb.yMin), Mathf.Max(data.xMax, hb.xMax), Mathf.Max(data.yMax, hb.yMax));
                for (int k = 0; k < n; k++)
                {
                    float ox = F32(b, ref o), oz = F32(b, ref o); int nv = I32(b, ref o), ni = I32(b, ref o), nr = I32(b, ref o);
                    if (nv <= 0 || ni <= 0 || nr <= 0 || nv > 65535 || o + nv * 4 + nr * 8 + ni * 2 > b.Length) { Debug.LogWarning("[Alatau] " + file + ": bad chunk " + k); return false; }
                    var ch = new Chunk { ox = ox, oz = oz, q = new ushort[nv * 2], idx = new ushort[ni], runFirst = new int[nr], runT = new byte[nr], runA = new byte[nr], runH = new byte[nr], runY = new byte[nr] };
                    var v = new Vector3[nv]; var c = new Color32[nv]; var t = new int[ni];
                    float lx = float.MaxValue, lz = float.MaxValue, hx = float.MinValue, hz = float.MinValue;
                    for (int i = 0; i < nv; i++)
                    {
                        ushort qx = BitConverter.ToUInt16(b, o + i * 4), qz = BitConverter.ToUInt16(b, o + i * 4 + 2); ch.q[i * 2] = qx; ch.q[i * 2 + 1] = qz;
                        float x = ox + qx * Q, z = oz + qz * Q;
                        v[i] = new Vector3(x, z, 0f);
                        if (x < lx) lx = x; if (x > hx) hx = x; if (z < lz) lz = z; if (z > hz) hz = z;
                    }
                    o += nv * 4;
                    for (int r = 0; r < nr; r++)
                    {
                        int first = BitConverter.ToInt32(b, o + r * 8), end = r + 1 < nr ? BitConverter.ToInt32(b, o + (r + 1) * 8) : nv;
                        byte rt = b[o + r * 8 + 4], ra = b[o + r * 8 + 5], rh = b[o + r * 8 + 6], ry = b[o + r * 8 + 7];
                        // the texel: type and the hash's top 3 bits, angle, b = far from any outline (the outline pass lowers it), year
                        var col = new Color32((byte)((rt & 31) | (rh & 0xE0)), ra, 255, ry);
                        ch.runFirst[r] = first; ch.runT[r] = rt; ch.runA[r] = ra; ch.runH[r] = rh; ch.runY[r] = ry;
                        for (int i = Mathf.Max(first, 0); i < end && i < nv; i++) c[i] = col;
                    }
                    o += nr * 8;
                    for (int i = 0; i < ni; i++) { ushort ix = BitConverter.ToUInt16(b, o + i * 2); if (ix >= nv) { Debug.LogWarning("[Alatau] " + file + ": bad index in chunk " + k); return false; } t[i] = ix; ch.idx[i] = ix; }
                    o += ni * 2;
                    var m = new Mesh { name = "Ground types " + part + "." + k, indexFormat = IndexFormat.UInt16 };
                    m.vertices = v; m.colors32 = c; m.triangles = t; m.UploadMeshData(true);
                    ch.M = m; ch.R = Rect.MinMaxRect(lx, lz, hx, hz);
                    Outline(ch, part, k);
                    chunks.Add(ch); chunkGrid = null;
                    vertices += nv; triangles += ni / 3;
                }
            }
            catch (Exception ex) { Debug.LogWarning("[Alatau] " + file + " unreadable: " + ex.Message); return false; }
            return true;
        }

        /// <summary>The outline of every piece of a chunk (the edges of its triangles that no other triangle of the same piece shares; not
        /// the 2 km tile lines, where a piece only continues in the next chunk), as quads for the outline pass: vertex = (A.x, A.z, corner)
        /// in the chunk's own metres, uv = B, colour a = the piece's year byte. At most 16 383 segments per mesh (16-bit indices).</summary>
        void Outline(Chunk ch, int part, int k)
        {
            var open = new HashSet<long>(); var segs = new List<long>(); var segRun = new List<int>();
            int nr = ch.runFirst.Length, run = 0;
            void Flush()
            {
                foreach (long e in open)
                {
                    int a = (int)(e >> 20), b = (int)(e & 0xFFFFF);
                    int ax = ch.q[a * 2], az = ch.q[a * 2 + 1], bx = ch.q[b * 2], bz = ch.q[b * 2 + 1];
                    bool tileX = ax == bx && (ax == 0 || ax >= TileQ), tileZ = az == bz && (az == 0 || az >= TileQ);
                    if (tileX || tileZ) continue;
                    segs.Add(e); segRun.Add(run);
                }
                open.Clear();
            }
            for (int t = 0; t + 2 < ch.idx.Length; t += 3)
            {
                int v0 = ch.idx[t];
                if (run + 1 < nr && ch.runFirst[run + 1] <= v0) { Flush(); while (run + 1 < nr && ch.runFirst[run + 1] <= v0) run++; }
                for (int j = 0; j < 3; j++)
                {
                    int a = ch.idx[t + j], b = ch.idx[t + (j + 1) % 3];
                    long e = a < b ? ((long)a << 20) | (uint)b : ((long)b << 20) | (uint)a;
                    if (!open.Remove(e)) open.Add(e);
                }
            }
            Flush();
            const int PerMesh = 16383;
            for (int s0 = 0; s0 < segs.Count; s0 += PerMesh)
            {
                int n = Mathf.Min(PerMesh, segs.Count - s0);
                var v = new Vector3[n * 4]; var uv = new Vector2[n * 4]; var c = new Color32[n * 4]; var tri = new int[n * 6];
                for (int i = 0; i < n; i++)
                {
                    long e = segs[s0 + i]; int a = (int)(e >> 20), b = (int)(e & 0xFFFFF);
                    var pa = new Vector2(ch.q[a * 2] * Q, ch.q[a * 2 + 1] * Q); var pb = new Vector2(ch.q[b * 2] * Q, ch.q[b * 2 + 1] * Q);
                    var col = new Color32(0, 0, 0, ch.runY[segRun[s0 + i]]);
                    for (int j = 0; j < 4; j++) { v[i * 4 + j] = new Vector3(pa.x, pa.y, j); uv[i * 4 + j] = pb; c[i * 4 + j] = col; }
                    // corners: 0 = A right, 1 = B right, 2 = A left, 3 = B left
                    tri[i * 6] = i * 4; tri[i * 6 + 1] = i * 4 + 1; tri[i * 6 + 2] = i * 4 + 3; tri[i * 6 + 3] = i * 4; tri[i * 6 + 4] = i * 4 + 3; tri[i * 6 + 5] = i * 4 + 2;
                }
                var m = new Mesh { name = "Ground outlines " + part + "." + k + "." + s0 / PerMesh, indexFormat = IndexFormat.UInt16 };
                m.vertices = v; m.uv = uv; m.colors32 = c; m.triangles = tri; m.UploadMeshData(true);
                ch.outline.Add(m); segments += n; outlineBytes += n * (4L * (12 + 8 + 4) + 12);
            }
        }

        void Start()
        {
            // the texture over all the data: square texels, at most FarPx on the long side
            float tex = Mathf.Max(data.width, data.height) / (FarPx - 2);
            int w = Mathf.Clamp(Mathf.CeilToInt(data.width / tex) + 2, 8, FarPx), h = Mathf.Clamp(Mathf.CeilToInt(data.height / tex) + 2, 8, FarPx);
            farWin = new Rect(data.center.x - w * tex * 0.5f, data.center.y - h * tex * 0.5f, w * tex, h * tex);
            far = MakeRT(w, h, "Ground types (all)");
            Shader.SetGlobalTexture(NearId, Texture2D.blackTexture); Shader.SetGlobalVector(NearRId, Vector4.zero);
            Shader.SetGlobalTexture(FineId, Texture2D.blackTexture); Shader.SetGlobalVector(FineRId, Vector4.zero);
            Shader.SetGlobalVector(NearTId, new Vector4(1f / NearPx, 1f / NearPx, NearPx, NearPx)); Shader.SetGlobalVector(FineTId, new Vector4(1f / FinePx, 1f / FinePx, FinePx, FinePx));
            // the yard cells' table: the shader and the CPU (CellKindAt) read the same bytes, so a tree knows the cell it stands in
            hashTex = new Texture2D(256, 256, TextureFormat.R8, false, true) { name = "Ground types cell hash", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Repeat, anisoLevel = 0 };
            hashTex.LoadRawTextureData(CellHash); hashTex.Apply(false, true);
            Shader.SetGlobalTexture(HashId, hashTex);
            Debug.Log($"[Alatau] ground types: {chunks.Count} chunks, {vertices} vertices, {triangles} triangles over {data.width / 1000f:0.0} × {data.height / 1000f:0.0} km; "
                + $"render textures {w}×{h} ({tex:0.0} m per px), {NearPx}×{NearPx} round the camera and {FinePx}×{FinePx} in front of it; "
                + $"{segments} outline segments ({outlineBytes / 1048576f:0.0} MB of meshes) for the exact edges");
        }

        static RenderTexture MakeRT(int w, int h, string name)
        {
            var rt = new RenderTexture(w, h, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear)
            { name = name, filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp, useMipMap = false, autoGenerateMips = false, anisoLevel = 0 };
            rt.Create(); return rt;
        }

        /// <summary>Draws the triangles that fall in 'win' (world x, z) into rt: (0, 0) of the texture = the window's south-west corner; with
        /// w > 0 also the outlines, as the distance to them over w metres in b.</summary>
        void Draw(RenderTexture rt, Rect win, float w)
        {
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            GL.PushMatrix(); GL.LoadOrtho(); GL.LoadIdentity();
            GL.Clear(false, true, new Color(0f, 0f, 1f, 0f));
            var m = Matrix4x4.TRS(new Vector3(-win.xMin / win.width, -win.yMin / win.height, 0f), Quaternion.identity, new Vector3(1f / win.width, 1f / win.height, 1f));
            mat.SetPass(0);
            foreach (var c in chunks) if (c.R.Overlaps(win)) Graphics.DrawMeshNow(c.M, m);
            if (w > 0f)
            {
                mat.SetFloat(MatWId, w); mat.SetPass(1);
                var grown = new Rect(win.xMin - w, win.yMin - w, win.width + 2f * w, win.height + 2f * w);
                foreach (var c in chunks)
                    if (c.R.Overlaps(grown))
                    {
                        var mc = m * Matrix4x4.Translate(new Vector3(c.ox, c.oz, 0f));
                        for (int i = 0; i < c.outline.Count; i++) Graphics.DrawMeshNow(c.outline[i], mc);
                    }
            }
            GL.PopMatrix();
            RenderTexture.active = prev;
        }
        /// <summary>W of a texture: the reach of its outline distances, 2.5 texels and at least 2 m.</summary>
        static float WOf(float texel) => Mathf.Max(2.5f * texel, 2f);

        void OnEnable() { Camera.onPreCull += PreCull; }
        void OnDisable() { Camera.onPreCull -= PreCull; Shader.SetGlobalFloat(OnId, 0f); farDrawn = false; }
        void OnDestroy()
        {
            if (Instance == this) Instance = null;
            if (near != null) near.Release(); if (far != null) far.Release(); if (fine != null) fine.Release();
            if (hashTex != null) Destroy(hashTex);
            foreach (var c in chunks) { if (c.M != null) Destroy(c.M); foreach (var o in c.outline) if (o != null) Destroy(o); }
        }
        void LateUpdate() { Refresh(Camera.main); }
        // also right before the main camera renders: a capture that moves the camera and renders in the same frame sees the right yards
        void PreCull(Camera c) { if (c != null && c == Camera.main) Refresh(c); }

        void Refresh(Camera cam)
        {
            if (far == null) return;
            // the year of the timeline as the ground shader takes it (quarters) and the scenario's pace: a piece is in the textures from its
            // earthworks on; a change draws all three again
            float yr = Shader.GetGlobalFloat(TlGrowId) > 0.5f ? Shader.GetGlobalFloat(TlYearFId) + 1f : Shader.GetGlobalFloat(TlYearId);
            if (yr < 1f) yr = 2050f;
            float dk = Shader.GetGlobalFloat(TlDevKId); if (dk < 0.01f) dk = 1f;
            var yk = new Vector2(Mathf.Floor(yr * 4f) / 4f, dk);
            if (yk != yearKey)
            {
                yearKey = yk; Shader.SetGlobalVector(YearId, new Vector4(yk.x, yk.y, 0f, 0f));
                farDrawn = false;
            }
            if (!farDrawn || !far.IsCreated())
            {
                if (!far.IsCreated()) far.Create();
                Draw(far, farWin, 0f);
                Shader.SetGlobalTexture(FarId, far); Shader.SetGlobalVector(FarRId, new Vector4(farWin.xMin, farWin.yMin, 1f / farWin.width, 1f / farWin.height));
                Shader.SetGlobalFloat(OnId, 1f); farDrawn = true; nearKey = fineKey = new Vector3(float.NaN, 0f, 0f);
            }
            if (cam == null) return;
            // the window round the camera: from the ground under it to the ground it looks at, plus its distance to that point on every side
            Vector3 p = cam.transform.position, f = cam.transform.forward;
            float gy = CityGround.HeightAt(p.x, p.z), hgt = Mathf.Max(p.y - gy, 2f);
            Vector2 a = new Vector2(p.x, p.z), dir = new Vector2(f.x, f.z);
            float reach = f.y < -0.02f ? Mathf.Min(hgt / -f.y, 8000f) : 8000f;
            Vector2 b = a + dir * reach;
            float dist = Mathf.Sqrt(hgt * hgt + (b - a).sqrMagnitude);
            float want = Mathf.Max(MinWin, Mathf.NextPowerOfTwo(Mathf.CeilToInt(((b - a).magnitude * 0.5f + dist) * 2f)));
            Vector2 cc = (a + b) * 0.5f; float g = want / 8f;
            cc = new Vector2(Mathf.Round(cc.x / g) * g, Mathf.Round(cc.y / g) * g);
            var win = new Rect(cc.x - want * 0.5f, cc.y - want * 0.5f, want, want);
            bool use = want <= MaxWin && win.Overlaps(data);
            var key = use ? new Vector3(cc.x, cc.y, want) : new Vector3(0f, 0f, -1f);
            if (key != nearKey || (use && (near == null || !near.IsCreated())))
            {
                nearKey = key;
                if (!use) Shader.SetGlobalVector(NearRId, Vector4.zero);
                else
                {
                    if (near == null) near = MakeRT(NearPx, NearPx, "Ground types (near)"); else if (!near.IsCreated()) near.Create();
                    float nw = WOf(want / NearPx); Draw(near, win, nw);
                    Shader.SetGlobalVector(WId, new Vector4(fineW, nw, 0f, 0f)); nearW = nw;
                    Shader.SetGlobalTexture(NearId, near); Shader.SetGlobalVector(NearRId, new Vector4(win.xMin, win.yMin, 1f / want, 1f / want));
                }
            }
            // the fine window: the first few hundred metres of ground in front of the camera (0.25–2 m per texel), only when it is low
            float fw = Mathf.Max(256f, Mathf.NextPowerOfTwo(Mathf.CeilToInt(hgt * 2.5f + 150f)));
            Vector2 fc = a + (dir.sqrMagnitude > 1e-6f ? dir.normalized : Vector2.zero) * Mathf.Min(reach, fw * 0.35f); float fg = fw / 8f;
            fc = new Vector2(Mathf.Round(fc.x / fg) * fg, Mathf.Round(fc.y / fg) * fg);
            var fwin = new Rect(fc.x - fw * 0.5f, fc.y - fw * 0.5f, fw, fw);
            bool fuse = fw <= 2048f && fwin.Overlaps(data);
            var fkey = fuse ? new Vector3(fc.x, fc.y, fw) : new Vector3(0f, 0f, -1f);
            if (fkey == fineKey && (!fuse || (fine != null && fine.IsCreated()))) return;
            fineKey = fkey;
            if (!fuse) { Shader.SetGlobalVector(FineRId, Vector4.zero); return; }
            if (fine == null) fine = MakeRT(FinePx, FinePx, "Ground types (fine)"); else if (!fine.IsCreated()) fine.Create();
            fineW = WOf(fw / FinePx); Draw(fine, fwin, fineW);
            Shader.SetGlobalVector(WId, new Vector4(fineW, nearW, 0f, 0f));
            Shader.SetGlobalTexture(FineId, fine); Shader.SetGlobalVector(FineRId, new Vector4(fwin.xMin, fwin.yMin, 1f / fw, 1f / fw));
        }

        // ---------------- what lies at a point (CPU): for the trees and the props
        /// <summary>The cells' table of the data's yards (256 × 256 bytes, row = z): AlatauGround.shader reads it as _AlatauGtHash.</summary>
        public static readonly byte[] CellHash = MakeHash();
        static byte[] MakeHash()
        {
            var t = new byte[65536];
            for (int j = 0; j < 256; j++)
                for (int i = 0; i < 256; i++)
                {
                    uint h = (uint)i * 374761393u + (uint)j * 668265263u + 0x9E3779B9u;
                    h = (h ^ (h >> 15)) * 2246822519u; h = (h ^ (h >> 13)) * 3266489917u; h ^= h >> 16;
                    t[j * 256 + i] = (byte)(h >> 24);
                }
            return t;
        }

        /// <summary>The kind of ground the shader draws for type gt and cell byte hb (AlatauGround.shader, Yard, gt > 0): 0 lawn, 1 car park,
        /// 2 paved court, 3 playground, 4 concrete yard, 5 sports ground, 6 garden beds, 7 loading yard, 8 asphalt, 9 park alley,
        /// 10 running track. The yards of the data are lawn: their aprons, paths, playgrounds and fields are pieces of their own. No type
        /// picks by the cell byte hb any more (kept for the callers).</summary>
        public static int Kind(int gt, int hb)
        {
            switch (gt)
            {
                case 3: return 2;
                case 4: return 1;
                case 5: return 6;
                case 7: return 4;                                    // industry, logistics: plain concrete
                case 9: return 8;
                case 11: return 4;
                case 12: return 5;
                case 13: return 3;
                case 14: return 2;
                case 17: return 9;
                case 18: return 10;
                default: return 0;                                   // 1 yard green, 2 school plot, 6 park, 8 reserve, 10 public lot, 15, 16 lawn
            }
        }
        /// <summary>Cell kinds with no tree: everything but lawn (0) and garden beds (6).</summary>
        public static bool HardKind(int k) => k != 0 && k != 6;

        /// <summary>The cell (36 × 30 m, turned by the lot's angle) a point falls in, as the shader computes it, and the kind drawn there
        /// (the texture keeps the hash's top 3 bits: lh = hash >> 5).</summary>
        public static int CellKindAt(float x, float z, int gt, byte angB, byte hashB)
        {
            float ang = angB / 255f * 1.5707963f, ca = Mathf.Cos(ang), sa = Mathf.Sin(ang);
            float qx = x * ca + z * sa, qz = -x * sa + z * ca;
            int ix = Mathf.FloorToInt(qx / 36f), iz = Mathf.FloorToInt(qz / 30f), lh = hashB >> 5;
            int kx = (ix + 8192 + lh * 7) & 255, kz = (iz + 8192 + lh * 13) & 255;
            return Kind(gt, CellHash[kz * 256 + kx]);
        }

        /// <summary>The type of the data's ground at (x, z) (the top piece of the final year), 0 where the data has none; ang and hash of its piece.</summary>
        // the chunks by cell of ChunkCell m, the later (top) ones first: a point query looks at the few chunks of its cell, not all of
        // them (the stage-7 map has 295, and the trees ask five points per candidate)
        const float ChunkCell = 2000f;
        Dictionary<long, int[]> chunkGrid;
        static long CKey(int cx, int cz) => ((long)cx << 32) ^ (uint)cz;
        void MakeChunkGrid()
        {
            var g = new Dictionary<long, List<int>>();
            for (int ci = chunks.Count - 1; ci >= 0; ci--)
            {
                var r = chunks[ci].R;
                for (int cz = Mathf.FloorToInt(r.yMin / ChunkCell); cz <= Mathf.FloorToInt(r.yMax / ChunkCell); cz++)
                    for (int cx = Mathf.FloorToInt(r.xMin / ChunkCell); cx <= Mathf.FloorToInt(r.xMax / ChunkCell); cx++)
                    { long k = CKey(cx, cz); if (!g.TryGetValue(k, out var l)) g[k] = l = new List<int>(); l.Add(ci); }
            }
            chunkGrid = new Dictionary<long, int[]>();
            foreach (var kv in g) chunkGrid[kv.Key] = kv.Value.ToArray();
        }

        public int TypeAt(float x, float z, out byte ang, out byte hash)
        {
            ang = 0; hash = 0;
            if (!data.Contains(new Vector2(x, z))) return 0;
            if (chunkGrid == null) MakeChunkGrid();
            if (!chunkGrid.TryGetValue(CKey(Mathf.FloorToInt(x / ChunkCell), Mathf.FloorToInt(z / ChunkCell)), out var cell)) return 0;
            foreach (int ci in cell)
            {
                var c = chunks[ci];
                if (x < c.R.xMin || x > c.R.xMax || z < c.R.yMin || z > c.R.yMax) continue;
                int tri = Hit(c, x, z); if (tri < 0) continue;
                int v0 = c.idx[tri * 3], lo = 0, hi = c.runFirst.Length - 1;
                while (lo < hi) { int mid = (lo + hi + 1) >> 1; if (c.runFirst[mid] <= v0) lo = mid; else hi = mid - 1; }
                ang = c.runA[lo]; hash = c.runH[lo]; return c.runT[lo];
            }
            return 0;
        }

        /// <summary>Hard ground at the point: paving, asphalt, courts, car parks, sports grounds, playgrounds, tracks, concrete, park alleys.</summary>
        public bool HardAt(float x, float z)
        {
            int t = TypeAt(x, z, out byte a, out byte h);
            return t != 0 && HardKind(CellKindAt(x, z, t, a, h));
        }
        /// <summary>Hard ground at the point or r metres from it on any side (a crown's reach; the shader's cell edges and texels).</summary>
        public bool HardNear(float x, float z, float r)
        {
            return HardAt(x, z) || HardAt(x + r, z) || HardAt(x - r, z) || HardAt(x, z + r) || HardAt(x, z - r);
        }
        /// <summary>The data covers the point (a type other than 0).</summary>
        public bool Covers(float x, float z) => TypeAt(x, z, out _, out _) != 0;

        /// <summary>The pieces of the data (one per run): type, angle and hash bytes and the bounds of their triangles, for the props.</summary>
        public void Pieces(List<(int type, byte ang, byte hash, Rect bounds)> outList)
        {
            outList.Clear();
            foreach (var c in chunks)
            {
                int nr = c.runFirst.Length;
                var lx = new float[nr]; var lz = new float[nr]; var hx = new float[nr]; var hz = new float[nr];
                for (int r = 0; r < nr; r++) { lx[r] = lz[r] = float.MaxValue; hx[r] = hz[r] = float.MinValue; }
                int run = 0;
                for (int v = 0; v < c.q.Length / 2; v++)
                {
                    while (run + 1 < nr && c.runFirst[run + 1] <= v) run++;
                    float x = c.ox + c.q[v * 2] * Q, z = c.oz + c.q[v * 2 + 1] * Q;
                    if (x < lx[run]) lx[run] = x; if (x > hx[run]) hx[run] = x; if (z < lz[run]) lz[run] = z; if (z > hz[run]) hz[run] = z;
                }
                for (int r = 0; r < nr; r++) if (hx[r] >= lx[r]) outList.Add((c.runT[r], c.runA[r], c.runH[r], Rect.MinMaxRect(lx[r], lz[r], hx[r], hz[r])));
            }
        }

        // the top-most triangle of a chunk at a point (-1: none); the chunk's buckets of 32 m are made on the first query
        int Hit(Chunk c, float x, float z)
        {
            if (c.buckets == null) MakeBuckets(c);
            int bx = Mathf.Clamp((int)((x - c.R.xMin) / Bucket), 0, c.bw - 1), bz = Mathf.Clamp((int)((z - c.R.yMin) / Bucket), 0, c.bh - 1);
            var l = c.buckets[bz * c.bw + bx]; if (l == null) return -1;
            for (int k = l.Length - 1; k >= 0; k--)
            {
                int t = l[k], i0 = c.idx[t * 3] * 2, i1 = c.idx[t * 3 + 1] * 2, i2 = c.idx[t * 3 + 2] * 2;
                float ax = c.ox + c.q[i0] * Q, az = c.oz + c.q[i0 + 1] * Q, bx2 = c.ox + c.q[i1] * Q, bz2 = c.oz + c.q[i1 + 1] * Q, cx = c.ox + c.q[i2] * Q, cz = c.oz + c.q[i2 + 1] * Q;
                float d1 = (x - bx2) * (az - bz2) - (ax - bx2) * (z - bz2), d2 = (x - cx) * (bz2 - cz) - (bx2 - cx) * (z - cz), d3 = (x - ax) * (cz - az) - (cx - ax) * (z - az);
                bool neg = d1 < 0f || d2 < 0f || d3 < 0f, pos = d1 > 0f || d2 > 0f || d3 > 0f;
                if (!(neg && pos)) return t;
            }
            return -1;
        }
        void MakeBuckets(Chunk c)
        {
            c.bw = Mathf.Max(1, Mathf.CeilToInt(c.R.width / Bucket)); c.bh = Mathf.Max(1, Mathf.CeilToInt(c.R.height / Bucket));
            var tmp = new List<int>[c.bw * c.bh];
            for (int t = 0; t < c.idx.Length / 3; t++)
            {
                float lx = float.MaxValue, lz = float.MaxValue, hx = float.MinValue, hz = float.MinValue;
                for (int k = 0; k < 3; k++)
                {
                    int i = c.idx[t * 3 + k] * 2; float x = c.ox + c.q[i] * Q, z = c.oz + c.q[i + 1] * Q;
                    lx = Mathf.Min(lx, x); hx = Mathf.Max(hx, x); lz = Mathf.Min(lz, z); hz = Mathf.Max(hz, z);
                }
                int bx0 = Mathf.Clamp((int)((lx - c.R.xMin) / Bucket), 0, c.bw - 1), bx1 = Mathf.Clamp((int)((hx - c.R.xMin) / Bucket), 0, c.bw - 1);
                int bz0 = Mathf.Clamp((int)((lz - c.R.yMin) / Bucket), 0, c.bh - 1), bz1 = Mathf.Clamp((int)((hz - c.R.yMin) / Bucket), 0, c.bh - 1);
                for (int bz = bz0; bz <= bz1; bz++) for (int bx = bx0; bx <= bx1; bx++) { ref var l = ref tmp[bz * c.bw + bx]; if (l == null) l = new List<int>(); l.Add(t); }
            }
            c.buckets = new int[tmp.Length][];
            for (int i = 0; i < tmp.Length; i++) if (tmp[i] != null) c.buckets[i] = tmp[i].ToArray();
        }
    }
}
