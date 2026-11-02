using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Solar fields of the new map data (Resources/Landmarks/solar.json, tools/map CONTRACT §6): rows of panel tables facing
    /// south (30°, 4 m deep, a row every 7.5 m, east-west) inside each field, from the field's year of the scenario. A row piece (up to
    /// 40 m) is one instance of a 12-triangle unit (AlatauCity/Life, plain colour), drawn within a few kilometres of the camera; the
    /// ground of every field is one flat gravel polygon (one mesh per 1 km chunk), which is what is seen from further away.
    /// Without the file nothing is made.</summary>
    public class SolarLayer : MonoBehaviour
    {
        [Serializable] class FieldJ { public int[] y; public float[] p; }
        [Serializable] class SolarJ { public int v; public FieldJ[] f; }
        public static SolarLayer Instance;

        const float Pitch = 7.5f, Depth = 4.0f, Tilt = 30f, Piece = 40f, ChunkSize = 1000f;
        static float Range => Application.platform == RuntimePlatform.WebGLPlayer ? 2600f : 4200f;
        static readonly Color32 Gravel = LM.C("#6b6e72");
        static readonly Vector4 PanelC = new Vector4(0.12f, 0.17f, 0.27f, 1f), FrameC = new Vector4(0.60f, 0.62f, 0.64f, 1f);

        string json; FieldJ[] fields; Vector2[][] rings; YearChunks ground; bool built;
        Mesh panel, frame; Material mat; MaterialPropertyBlock panelP, frameP;
        class Chunk { public Bounds B; public Matrix4x4[] All; public int[] Field; public Matrix4x4[][] Vis; public int[] VisN; }
        readonly List<Chunk> chunks = new List<Chunk>();
        readonly Plane[] planes = new Plane[6];
        int year = int.MinValue, sc = -1;
        public int Rows { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (Instance != null) return;
            var txt = MapPolys.Load("solar"); if (txt == null) return;              // no file: today's city (its panels are buildings)
            Instance = new GameObject("Solar fields (map data)").AddComponent<SolarLayer>(); Instance.json = txt;
        }
        /// <summary>The field outlines of solar.json (empty without the file), for the layers that keep things off them (trees).</summary>
        public static List<Vector2[]> FieldRings()
        {
            var l = new List<Vector2[]>(); var txt = MapPolys.Load("solar"); if (txt == null) return l;
            try { var j = JsonUtility.FromJson<SolarJ>(txt); if (j?.f != null) foreach (var f in j.f) { var r = MapPolys.Ring(f.p); if (r != null && MapPolys.FirstYear(f.y) <= 2050) l.Add(r); } }
            catch (Exception) { }
            return l;
        }
        void Start() { TryBuild(); }

        void TryBuild()
        {
            if (built) return;
            if (!TwinData.Ready || CityGround.HeightAt(0, 0) == 0f) { Invoke(nameof(TryBuild), 0.3f); return; }
            built = true;
            var lsh = Shader.Find("AlatauCity/Landmark"); var fsh = Shader.Find("AlatauCity/Life");
            if (lsh == null || fsh == null) { Debug.LogWarning("[Alatau] solar fields: shader missing"); return; }
            SolarJ j; try { j = JsonUtility.FromJson<SolarJ>(json); } catch (Exception ex) { Debug.LogWarning("[Alatau] solar.json unreadable: " + ex.Message); return; }
            json = null;
            if (j?.f == null || j.f.Length == 0) return;
            fields = j.f; rings = new Vector2[fields.Length][];
            ground = new YearChunks(transform, new Material(lsh) { name = "Solar field ground" }, "Solar field ground", BuildGround);
            mat = new Material(fsh) { name = "Solar panels", enableInstancing = true }; mat.SetFloat("_LifeKind", 3f);
            panel = PanelMesh(); frame = FrameMesh();
            panelP = new MaterialPropertyBlock(); frameP = new MaterialPropertyBlock();
            var pc = new Vector4[1023]; var fc = new Vector4[1023];
            var rng = new System.Random(77);
            for (int i = 0; i < 1023; i++) { float t = 0.92f + 0.16f * (float)rng.NextDouble(); pc[i] = new Vector4(PanelC.x * t, PanelC.y * t, PanelC.z * t, 1f); fc[i] = FrameC; }
            panelP.SetVectorArray("_LifeB", pc); frameP.SetVectorArray("_LifeB", fc);
            // the rows, sorted into 1 km chunks
            var byChunk = new Dictionary<long, (List<Matrix4x4> m, List<int> f)>(); float ha = 0f;
            for (int i = 0; i < fields.Length; i++)
            {
                var r = MapPolys.Ring(fields[i].p); if (r == null) continue;
                rings[i] = r; ha += Mathf.Abs(MapPolys.SignedArea(r)) / 10000f;
                ground.Add(i, MapPolys.Centre(r), fields[i].y);
                var b = MapPolys.Bounds(r); var xs = new List<float>();
                for (float z = b.yMin + Pitch * 0.5f; z < b.yMax; z += Pitch)
                {
                    xs.Clear();
                    for (int a = 0, c = r.Length - 1; a < r.Length; c = a++)
                        if ((r[a].y > z) != (r[c].y > z)) xs.Add((r[c].x - r[a].x) * (z - r[a].y) / (r[c].y - r[a].y) + r[a].x);
                    xs.Sort();
                    for (int q = 0; q + 1 < xs.Count; q += 2)
                    {
                        float x0 = xs[q] + 2f, x1 = xs[q + 1] - 2f; if (x1 - x0 < 6f) continue;
                        int pieces = Mathf.CeilToInt((x1 - x0) / Piece); float len = (x1 - x0) / pieces;
                        for (int k = 0; k < pieces; k++)
                        {
                            float cx = x0 + len * (k + 0.5f);
                            float y = Mathf.Min(CityGround.HeightAt(cx - len * 0.5f, z), Mathf.Min(CityGround.HeightAt(cx, z), CityGround.HeightAt(cx + len * 0.5f, z)));
                            long key = ((long)(Mathf.FloorToInt(cx / ChunkSize) + 100000) << 32) | (uint)(Mathf.FloorToInt(z / ChunkSize) + 100000);
                            if (!byChunk.TryGetValue(key, out var l)) byChunk[key] = l = (new List<Matrix4x4>(), new List<int>());
                            l.m.Add(Matrix4x4.TRS(new Vector3(cx, y, z), Quaternion.identity, new Vector3(len - 0.6f, 1f, 1f))); l.f.Add(i);
                        }
                    }
                }
            }
            foreach (var kv in byChunk)
            {
                var ch = new Chunk { All = kv.Value.m.ToArray(), Field = kv.Value.f.ToArray() };
                int blocks = (ch.All.Length + 1022) / 1023; ch.Vis = new Matrix4x4[blocks][]; ch.VisN = new int[blocks];
                for (int q = 0; q < blocks; q++) ch.Vis[q] = new Matrix4x4[1023];
                Vector3 lo = new Vector3(float.MaxValue, float.MaxValue, float.MaxValue), hi = -lo;
                foreach (var m in ch.All) { var p = m.GetColumn(3); float hx = m.m00 * 0.5f + 1f; lo = Vector3.Min(lo, new Vector3(p.x - hx, p.y, p.z - 2.5f)); hi = Vector3.Max(hi, new Vector3(p.x + hx, p.y + 3.2f, p.z + 2.5f)); }
                ch.B = new Bounds((lo + hi) * 0.5f, hi - lo);
                chunks.Add(ch); Rows += ch.All.Length;
            }
            ground.Apply(TwinState.Year, (int)TwinState.Scenario);
            int tri = (panel.triangles.Length + frame.triangles.Length) / 3;
            Debug.Log($"[Alatau] solar.json: {fields.Length} fields, {ha:0.0} ha, {Rows} panel row pieces in {chunks.Count} chunks ({Rows * tri} triangles instanced, {tri} per piece; ground {ground.Triangles} triangles), drawn within {Range:0} m");
        }

        void Update()
        {
            if (chunks.Count == 0 && ground == null) return;
            int y = TwinState.Year, s = (int)TwinState.Scenario;
            ground?.Apply(y, s);
            if (y != year || s != sc) { year = y; sc = s; Visible(); }
            var cam = Camera.main; if (cam == null || chunks.Count == 0) return;
            GeometryUtility.CalculateFrustumPlanes(cam, planes);
            Vector3 cp = cam.transform.position; float r2 = Range * Range;
            foreach (var ch in chunks)
            {
                if (ch.B.SqrDistance(cp) > r2 || !GeometryUtility.TestPlanesAABB(planes, ch.B)) continue;
                var shadow = ch.B.SqrDistance(cp) < 1800f * 1800f ? ShadowCastingMode.On : ShadowCastingMode.Off;
                for (int q = 0; q < ch.Vis.Length; q++)
                {
                    int n = ch.VisN[q]; if (n == 0) continue;
                    Graphics.DrawMeshInstanced(panel, 0, mat, ch.Vis[q], n, panelP, shadow, true, 0, null);
                    Graphics.DrawMeshInstanced(frame, 0, mat, ch.Vis[q], n, frameP, ShadowCastingMode.Off, true, 0, null);
                }
            }
        }
        /// <summary>Fills the drawn arrays with the rows of the fields open in the current year (no allocation).</summary>
        void Visible()
        {
            foreach (var ch in chunks)
            {
                for (int q = 0; q < ch.VisN.Length; q++) ch.VisN[q] = 0;
                int b = 0;
                for (int i = 0; i < ch.All.Length; i++)
                {
                    int open = MapPolys.Year(fields[ch.Field[i]].y, sc); if (open > 0 && open > year) continue;
                    if (ch.VisN[b] == 1023) b++;
                    ch.Vis[b][ch.VisN[b]++] = ch.All[i];
                }
            }
        }

        void BuildGround(int i, LandmarkKit k)
        {
            var r = rings[i]; if (r == null) return;
            var tri = MapPolys.Triangulate(r);
            for (int q = 0; q + 2 < tri.Count; q += 3) Drape(k, r[tri[q]], r[tri[q + 1]], r[tri[q + 2]], 0);
        }
        static void Drape(LandmarkKit k, Vector2 a, Vector2 b, Vector2 c, int depth)
        {
            float ab = (b - a).sqrMagnitude, bc = (c - b).sqrMagnitude, ca = (a - c).sqrMagnitude, m = Mathf.Max(ab, Mathf.Max(bc, ca));
            if (m > 30f * 30f && depth < 10)
            {
                if (m == ab) { var h = (a + b) * 0.5f; Drape(k, a, h, c, depth + 1); Drape(k, h, b, c, depth + 1); }
                else if (m == bc) { var h = (b + c) * 0.5f; Drape(k, a, b, h, depth + 1); Drape(k, a, h, c, depth + 1); }
                else { var h = (c + a) * 0.5f; Drape(k, a, b, h, depth + 1); Drape(k, h, b, c, depth + 1); }
                return;
            }
            Vector3 P(Vector2 q) => new Vector3(q.x, CityGround.HeightAt(q.x, q.y) + 0.08f, q.y);
            k.Tri(P(a), P(b), P(c), Vector3.up, Gravel, LM.Roof, 3f, a, b, c);
        }

        // ------------------------------------------------------------------ the unit (1 m of row along x; Life draws both sides)
        /// <summary>The panel table: a slab 4 m deep tilted 30° to the south (−z), its low edge 0.7 m above the ground.</summary>
        static Mesh PanelMesh()
        {
            float zc = Depth * Mathf.Cos(Tilt * Mathf.Deg2Rad) * 0.5f, y0 = 0.7f, y1 = y0 + Depth * Mathf.Sin(Tilt * Mathf.Deg2Rad), t = 0.07f;
            var v = new List<Vector3>(); var nr = new List<Vector3>(); var tr = new List<int>();
            var up = new Vector3(0f, Mathf.Cos(Tilt * Mathf.Deg2Rad), -Mathf.Sin(Tilt * Mathf.Deg2Rad));
            void Q(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 n) { int i = v.Count; v.Add(a); v.Add(b); v.Add(c); v.Add(d); for (int k = 0; k < 4; k++) nr.Add(n); tr.Add(i); tr.Add(i + 1); tr.Add(i + 2); tr.Add(i); tr.Add(i + 2); tr.Add(i + 3); }
            Vector3 S0 = new Vector3(-0.5f, y0, -zc), S1 = new Vector3(0.5f, y0, -zc), N1 = new Vector3(0.5f, y1, zc), N0 = new Vector3(-0.5f, y1, zc), dn = Vector3.down * t;
            Q(S0, S1, N1, N0, up);                                                            // the glass
            Q(S0 + dn, S1 + dn, S1, S0, new Vector3(0f, 0f, -1f));                          // low edge
            Q(N0, N1, N1 + dn, N0 + dn, new Vector3(0f, 0f, 1f));                           // high edge
            Q(S0 + dn, S0, N0, N0 + dn, Vector3.left);                                       // row ends
            Q(S1, S1 + dn, N1 + dn, N1, Vector3.right);
            var m = new Mesh { name = "Solar panel row" }; m.SetVertices(v); m.SetNormals(nr); m.SetTriangles(tr, 0); m.RecalculateBounds(); return m;
        }
        /// <summary>The support under the middle of the table (one sheet: Life draws it from both sides).</summary>
        static Mesh FrameMesh()
        {
            float y = 0.7f + Depth * Mathf.Sin(Tilt * Mathf.Deg2Rad) * 0.5f - 0.05f;
            var v = new List<Vector3> { new Vector3(-0.5f, 0f, 0f), new Vector3(0.5f, 0f, 0f), new Vector3(0.5f, y, 0f), new Vector3(-0.5f, y, 0f) };
            var m = new Mesh { name = "Solar row support" }; m.SetVertices(v); m.SetNormals(new List<Vector3> { Vector3.back, Vector3.back, Vector3.back, Vector3.back }); m.SetTriangles(new[] { 0, 2, 1, 0, 3, 2 }, 0); m.RecalculateBounds(); return m;
        }
    }
}
