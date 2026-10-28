using System.IO;
using System.IO.Compression;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The models of the QTwin page of Iconic Complex (QTwin_IconicComplex_AlatauCity.html), converted by
    /// tools/build_gate_district.py into the local frame of the Iconic landmark: the BIM model of the complex
    /// (Resources/Landmarks/iconic_bim.bytes) and the Gate District round it (gate_district.bytes, gzip: mesh, trees, the mask of its area).
    /// Each vertex carries the page's facade coordinate u, its surface tag (AlatauQTwin.cginc) and, on the complex, its building.</summary>
    public static class QTwinData
    {
        public class QMesh { public Vector3[] P, N; public float[] U; public byte[] Tag, Part; public int[] I; }
        /// <summary>Trees: x, y, z (local) and size (a crown 8.6 × 10.5 m at 1); Kind: 0 round crown … 3 (the page's four).</summary>
        public class District { public QMesh Mesh; public Vector4[] Trees; public byte[] Kind; public int W; public float Half; public byte[] Mask; }

        /// <summary>KAIST Kazakhstan (tools/build_kaist.py, from the campus page): the BIM model (tags 41–62), the park's trees, the crane spots.</summary>
        public class KaistModel { public QMesh Mesh; public Vector4[] Trees; public byte[] Kind; public Vector3[] Cranes; }

        static QMesh bim; static District gate; static KaistModel kaist; static bool bimTried, gateTried, kaistTried;
        static float[] top; static float topX0, topZ0; const float TopCell = 2f; static int topW, topH;

        static QMesh Read(BinaryReader r, bool part)
        {
            int nv = r.ReadInt32(), ni = r.ReadInt32(); var m = new QMesh { P = new Vector3[nv], N = new Vector3[nv], U = new float[nv], I = new int[ni] };
            for (int i = 0; i < nv; i++) m.P[i] = new Vector3(r.ReadSingle(), r.ReadSingle(), r.ReadSingle());
            for (int i = 0; i < nv; i++) m.N[i] = new Vector3((sbyte)r.ReadByte(), (sbyte)r.ReadByte(), (sbyte)r.ReadByte()) / 127f;
            for (int i = 0; i < nv; i++) m.U[i] = r.ReadSingle();
            m.Tag = r.ReadBytes(nv); if (part) m.Part = r.ReadBytes(nv);
            for (int i = 0; i < ni; i++) m.I[i] = (int)r.ReadUInt32();
            return m;
        }

        /// <summary>The BIM model of the complex (null when the file is missing).</summary>
        public static QMesh Bim()
        {
            if (bimTried) return bim; bimTried = true;
            var ta = Resources.Load<TextAsset>("Landmarks/iconic_bim");
            if (ta == null || ta.bytes.Length < 12 || ta.bytes[0] != 'Q' || ta.bytes[1] != 'T' || ta.bytes[2] != 'B') { Debug.LogWarning("[Alatau] iconic_bim missing"); return null; }
            using (var r = new BinaryReader(new MemoryStream(ta.bytes))) { r.ReadBytes(4); bim = Read(r, true); }
            return bim;
        }

        /// <summary>The campus of KAIST (null when the file is missing).</summary>
        public static KaistModel Kaist()
        {
            if (kaistTried) return kaist; kaistTried = true;
            var ta = Resources.Load<TextAsset>("Landmarks/kaist_bim");
            if (ta == null || ta.bytes.Length < 12 || ta.bytes[0] != 'Q' || ta.bytes[1] != 'K' || ta.bytes[2] != 'B') { Debug.LogWarning("[Alatau] kaist_bim missing"); return null; }
            using (var r = new BinaryReader(new MemoryStream(ta.bytes)))
            {
                r.ReadBytes(4); var c = new KaistModel { Mesh = Read(r, true) };
                int nt = r.ReadInt32(); c.Trees = new Vector4[nt]; c.Kind = new byte[nt];
                for (int i = 0; i < nt; i++) { float x = r.ReadSingle(), y = r.ReadSingle(), z = r.ReadSingle(), s = r.ReadSingle(), k = r.ReadSingle(); c.Trees[i] = new Vector4(x, y, z, s); c.Kind[i] = (byte)Mathf.RoundToInt(k); }
                int ns = r.ReadInt32(); c.Cranes = new Vector3[ns];
                for (int i = 0; i < ns; i++) c.Cranes[i] = new Vector3(r.ReadSingle(), r.ReadSingle(), r.ReadSingle());
                kaist = c;
            }
            return kaist;
        }

        /// <summary>The Gate District (null when the file is missing).</summary>
        public static District Gate()
        {
            if (gateTried) return gate; gateTried = true;
            var ta = Resources.Load<TextAsset>("Landmarks/gate_district");
            if (ta == null) { Debug.LogWarning("[Alatau] gate_district missing"); return null; }
            using (var z = new GZipStream(new MemoryStream(ta.bytes), CompressionMode.Decompress))
            using (var ms = new MemoryStream())
            {
                z.CopyTo(ms); ms.Position = 0;
                using (var r = new BinaryReader(ms))
                {
                    if (new string(r.ReadChars(4)) != "QGD1") { Debug.LogWarning("[Alatau] gate_district: unknown format"); return null; }
                    var d = new District { Mesh = Read(r, false) };
                    int nt = r.ReadInt32(); d.Trees = new Vector4[nt]; d.Kind = new byte[nt];
                    for (int i = 0; i < nt; i++) { float x = r.ReadSingle(), y = r.ReadSingle(), zz = r.ReadSingle(), s = r.ReadSingle(), k = r.ReadSingle(); d.Trees[i] = new Vector4(x, y, zz, s); d.Kind[i] = (byte)Mathf.RoundToInt(k); }
                    d.W = r.ReadInt32(); d.Half = r.ReadSingle(); d.Mask = r.ReadBytes(d.W * d.W);
                    gate = d;
                }
            }
            return gate;
        }

        /// <summary>Is a point of the landmark's local frame inside the area of the district?</summary>
        public static bool InArea(float lx, float lz)
        {
            var d = Gate(); if (d == null) return false;
            int ix = Mathf.FloorToInt((lx + d.Half) / (2f * d.Half) * d.W), iz = Mathf.FloorToInt((lz + d.Half) / (2f * d.Half) * d.W);
            return ix >= 0 && iz >= 0 && ix < d.W && iz < d.W && d.Mask[iz * d.W + ix] > 127;
        }

        /// <summary>Height of the top of the complex over a local point of its plot (0 where nothing stands).</summary>
        public static float TopAt(float x, float z)
        {
            if (top == null)
            {
                var m = Bim(); if (m == null) return 0f;
                Vector3 lo = Vector3.one * 1e9f, hi = -lo; foreach (var p in m.P) { lo = Vector3.Min(lo, p); hi = Vector3.Max(hi, p); }
                topX0 = lo.x; topZ0 = lo.z; topW = Mathf.CeilToInt((hi.x - lo.x) / TopCell) + 1; topH = Mathf.CeilToInt((hi.z - lo.z) / TopCell) + 1;
                top = new float[topW * topH];
                for (int t = 0; t + 2 < m.I.Length; t += 3)
                {
                    Vector3 a = m.P[m.I[t]], b = m.P[m.I[t + 1]], c = m.P[m.I[t + 2]];
                    int x0 = Mathf.FloorToInt((Mathf.Min(a.x, Mathf.Min(b.x, c.x)) - topX0) / TopCell), x1 = Mathf.FloorToInt((Mathf.Max(a.x, Mathf.Max(b.x, c.x)) - topX0) / TopCell);
                    int z0 = Mathf.FloorToInt((Mathf.Min(a.z, Mathf.Min(b.z, c.z)) - topZ0) / TopCell), z1 = Mathf.FloorToInt((Mathf.Max(a.z, Mathf.Max(b.z, c.z)) - topZ0) / TopCell);
                    for (int iz = z0; iz <= z1; iz++) for (int ix = x0; ix <= x1; ix++)
                    {
                        // the highest triangle whose plan covers the cell centre
                        var q = new Vector2(topX0 + (ix + 0.5f) * TopCell, topZ0 + (iz + 0.5f) * TopCell);
                        if (!InTri(q, a, b, c, out float yy)) continue;
                        int k = iz * topW + ix; if (yy > top[k]) top[k] = yy;
                    }
                }
            }
            int cx = Mathf.FloorToInt((x - topX0) / TopCell), cz = Mathf.FloorToInt((z - topZ0) / TopCell);
            return cx >= 0 && cz >= 0 && cx < topW && cz < topH ? top[cz * topW + cx] : 0f;
        }
        static bool InTri(Vector2 p, Vector3 a, Vector3 b, Vector3 c, out float y)
        {
            y = 0f;
            float d = (b.z - c.z) * (a.x - c.x) + (c.x - b.x) * (a.z - c.z); if (Mathf.Abs(d) < 1e-6f) return false;
            float l1 = ((b.z - c.z) * (p.x - c.x) + (c.x - b.x) * (p.y - c.z)) / d, l2 = ((c.z - a.z) * (p.x - c.x) + (a.x - c.x) * (p.y - c.z)) / d, l3 = 1f - l1 - l2;
            if (l1 < 0f || l2 < 0f || l3 < 0f) return false;
            y = l1 * a.y + l2 * b.y + l3 * c.y; return true;
        }
    }
}
