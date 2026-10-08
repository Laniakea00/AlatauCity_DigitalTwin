using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

namespace AlatauCity.EditorTools
{
    /// <summary>What the plain boxes of the model lack. Per building and by its kind this adds:
    /// a parapet around every flat roof, a stepped crown on towers, stair and plant boxes on housing and public buildings,
    /// rows of roof lights on industrial sheds, a hipped tile roof on small existing houses, eaves and a chimney on the
    /// generated houses, and a paved plinth around larger buildings so they meet the ground on a slope.
    /// The extra triangles carry the building's id and year like the rest, plus a part code in uv.y (negative):
    /// -1 parapet, crown, chimney (the wall material, no windows), -2 plant or roof light, -3 tiled roof, -4 paved plinth.
    /// AlatauLit draws them only in the film look, so the plain maket look is exactly what it was.</summary>
    public static class AlatauRoofs
    {
        public struct Tri { public Vector3 a, b, c; public byte col, part; public ushort year; public int bid; }
        public class Info { public string kind; public int floors; public float height, ground; }

        public static Dictionary<int, Info> LoadCsv(string path)
        {
            var d = new Dictionary<int, Info>();
            var lines = File.ReadAllLines(path);
            // bid,id,district,kind,use,source,year,floors,height_m,gfa_m2,parcel,x,z,ground_m,easting,northing
            for (int i = 1; i < lines.Length; i++)
            {
                var p = lines[i].Split(','); if (p.Length < 14) continue;
                float F(string s) => float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
                if (int.TryParse(p[0], out int bid)) d[bid] = new Info { kind = p[3], floors = (int)F(p[7]), height = F(p[8]), ground = F(p[13]) };
            }
            return d;
        }

        static float Hash(int bid, int k) { uint h = (uint)(bid * 73856093) ^ (uint)(k * 19349663); h ^= h >> 13; h *= 0x5bd1e995; h ^= h >> 15; return (h & 0xFFFFFF) / 16777216f; }
        static long Key(Vector3 p) => ((long)Mathf.RoundToInt(p.x * 20f) & 0x1FFFFF) | (((long)Mathf.RoundToInt(p.z * 20f) & 0x1FFFFF) << 21) | (((long)Mathf.RoundToInt(p.y * 10f) & 0xFFFFF) << 42);

        public static List<Tri> Build(Vector3[] V, int[] T, byte[] col, ushort[] yr, int[] bid, Dictionary<int, Info> info)
        {
            var outT = new List<Tri>();
            int nt = T.Length / 3;
            byte curCol = 0; ushort curYear = 0; int id = 0;
            void Add(Vector3 a, Vector3 b, Vector3 c, Vector3 want, byte part)
            {
                if (Vector3.Dot(Vector3.Cross(b - a, c - a), want) < 0) { var s = b; b = c; c = s; }
                outT.Add(new Tri { a = a, b = b, c = c, col = curCol, year = curYear, bid = id, part = part });
            }
            void Quad(Vector3 p0, Vector3 p1, Vector3 p2, Vector3 p3, Vector3 want, byte part) { Add(p0, p1, p2, want, part); Add(p0, p2, p3, want, part); }
            void Box(Vector3 centre, Vector3 u, Vector3 v, float hu, float hv, float h, byte part)
            {
                Vector3 p0 = centre - u * hu - v * hv, p1 = centre + u * hu - v * hv, p2 = centre + u * hu + v * hv, p3 = centre - u * hu + v * hv, up = Vector3.up * h;
                Quad(p0, p1, p1 + up, p0 + up, -v, part); Quad(p1, p2, p2 + up, p1 + up, u, part); Quad(p2, p3, p3 + up, p2 + up, v, part); Quad(p3, p0, p0 + up, p3 + up, -u, part);
                Quad(p0 + up, p1 + up, p2 + up, p3 + up, Vector3.up, part);
            }

            // roof triangles of every building: flat ones, and the pitched ones of the generated houses
            var roofs = new Dictionary<int, List<int>>(); var pitched = new Dictionary<int, List<int>>();
            for (int t = 0; t < nt; t++)
            {
                Vector3 a = V[T[t * 3]], b = V[T[t * 3 + 1]], c = V[T[t * 3 + 2]];
                var n = Vector3.Cross(b - a, c - a); float len = n.magnitude; if (len < 1e-6f) continue; float ny = n.y / len;
                if (ny < 0.3f) continue;
                var set = ny >= 0.95f ? roofs : pitched;
                if (!set.TryGetValue(bid[t], out var l)) set[bid[t]] = l = new List<int>();
                l.Add(t);
            }

            // ---------------- generated houses: eaves over the walls and a chimney
            foreach (var kv in pitched)
            {
                id = kv.Key; if (!info.TryGetValue(id, out var bi) || bi.kind != "house") continue;
                curCol = col[kv.Value[0]]; curYear = yr[kv.Value[0]];
                var planes = new Dictionary<int, List<Vector3>>(); var normals = new Dictionary<int, Vector3>();
                foreach (int t in kv.Value)
                {
                    Vector3 a = V[T[t * 3]], b = V[T[t * 3 + 1]], c = V[T[t * 3 + 2]]; var n = Vector3.Cross(b - a, c - a).normalized;
                    int pk = Mathf.RoundToInt(n.x * 20f) * 1000 + Mathf.RoundToInt(n.z * 20f);
                    if (!planes.TryGetValue(pk, out var pts)) { planes[pk] = pts = new List<Vector3>(); normals[pk] = n; }
                    foreach (var p in new[] { a, b, c }) { bool seen = false; foreach (var q in pts) if ((q - p).sqrMagnitude < 0.0025f) { seen = true; break; } if (!seen) pts.Add(p); }
                }
                bool chimney = false;
                foreach (var pk in planes.Keys)
                {
                    var pts = planes[pk]; if (pts.Count != 4) continue; var n = normals[pk];
                    pts.Sort((p, q) => p.y.CompareTo(q.y));
                    Vector3 e0 = pts[0], e1 = pts[1], r0 = pts[2], r1 = pts[3];
                    var r = r1 - r0; r.y = 0; if (r.magnitude < 0.2f) continue; r.Normalize();
                    if (Vector3.Dot(e1 - e0, r) < 0) { var s = e0; e0 = e1; e1 = s; }
                    var down = ((e0 + e1) * 0.5f - (r0 + r1) * 0.5f).normalized;
                    const float og = 0.35f, oe = 0.55f, lift = 0.06f;
                    Quad(r0 - r * og + n * lift, r1 + r * og + n * lift, e1 + r * og + down * oe + n * lift, e0 - r * og + down * oe + n * lift, n, 3);
                    if (!chimney && Hash(id, 80) < 0.7f)
                    {
                        chimney = true; var hd = new Vector3(down.x, 0, down.z).normalized; var at = Vector3.Lerp(r0, r1, 0.25f + 0.5f * Hash(id, 81)) + hd * 1.1f;
                        Box(new Vector3(at.x, e0.y, at.z), r, new Vector3(-r.z, 0, r.x), 0.36f, 0.36f, r0.y - e0.y + 0.7f, 1);
                    }
                }
            }

            // ---------------- flat roofs
            var edges = new Dictionary<(long, long), (Vector3 a, Vector3 b, Vector3 c, int n)>();
            foreach (var kv in roofs)
            {
                id = kv.Key; if (!info.TryGetValue(id, out var bi)) continue;
                string k = bi.kind; if (k == "house" || k == "solar") continue;
                var list = kv.Value; int t0 = list[0]; curCol = col[t0]; curYear = yr[t0];

                // outline of the roof: edges that belong to one roof triangle only
                edges.Clear(); float area = 0;
                foreach (int t in list)
                {
                    Vector3 a = V[T[t * 3]], b = V[T[t * 3 + 1]], c = V[T[t * 3 + 2]];
                    area += Vector3.Cross(b - a, c - a).magnitude * 0.5f;
                    for (int j = 0; j < 3; j++)
                    {
                        Vector3 p = j == 0 ? a : j == 1 ? b : c, q = j == 0 ? b : j == 1 ? c : a, r = j == 0 ? c : j == 1 ? a : b;
                        long kp = Key(p), kq = Key(q); var key = kp < kq ? (kp, kq) : (kq, kp);
                        if (edges.TryGetValue(key, out var e)) edges[key] = (e.a, e.b, e.c, e.n + 1); else edges[key] = (p, q, r, 1);
                    }
                }
                var outline = new List<(Vector3 a, Vector3 b, Vector3 inw)>();
                foreach (var e in edges.Values)
                {
                    if (e.n != 1) continue;
                    var d = e.b - e.a; d.y = 0; if (d.magnitude < 0.05f) continue; d.Normalize();
                    var inw = new Vector3(-d.z, 0, d.x); var toC = e.c - e.a; toC.y = 0; if (Vector3.Dot(inw, toC) < 0) inw = -inw;
                    outline.Add((e.a, e.b, inw));
                }
                if (outline.Count < 3) continue;
                bool existing = k == "existing", tall = k == "tower" || k == "business" || k == "mixed", housing = k == "res_mid" || k == "res_high" || k == "residential" || k == "resort" || k == "hotel";
                bool shed = k == "industry" || k == "utility";

                // rectangle-like roofs: centre and the two axes
                bool quad = outline.Count == 4; Vector3 cen = Vector3.zero, U = Vector3.right, W = Vector3.forward; float hu = 0, hw = 0, y = V[T[t0 * 3]].y;
                if (quad)
                {
                    float best = 0; foreach (var e in outline) { cen += (e.a + e.b) * 0.5f; float l = (e.b - e.a).magnitude; if (l > best) { best = l; U = (e.b - e.a) / l; } }
                    cen /= 4f; U.y = 0; U.Normalize(); W = new Vector3(-U.z, 0, U.x);
                    foreach (var e in outline) { hu = Mathf.Max(hu, Mathf.Abs(Vector3.Dot(e.a - cen, U))); hw = Mathf.Max(hw, Mathf.Abs(Vector3.Dot(e.a - cen, W))); }
                    cen.y = y;
                }

                // small existing houses: a hipped tile roof with eaves
                if (existing && quad && area < 260f && bi.floors <= 2 && hw > 1.5f)
                {
                    float ov = 0.35f, rise = Mathf.Min(hw * 0.62f, 3.4f), ridge = Mathf.Max(hu - hw, 0f);
                    Vector3 e0 = cen - U * (hu + ov) - W * (hw + ov), e1 = cen + U * (hu + ov) - W * (hw + ov), e2 = cen + U * (hu + ov) + W * (hw + ov), e3 = cen - U * (hu + ov) + W * (hw + ov);
                    Vector3 r0 = cen - U * ridge + Vector3.up * rise, r1 = cen + U * ridge + Vector3.up * rise;
                    Quad(e0, e1, r1, r0, -W + Vector3.up, 3); Quad(e2, e3, r0, r1, W + Vector3.up, 3);
                    Add(e1, e2, r1, U + Vector3.up, 3); Add(e3, e0, r0, -U + Vector3.up, 3);
                    continue;
                }

                // a paved plinth around the building: a level terrace that also hides the gap on sloping ground
                if (quad && (!existing || area >= 300f) && bi.ground > 1f && y - bi.ground > 2.5f)
                    Box(new Vector3(cen.x, bi.ground - 1.5f, cen.z), U, W, hu + 2.6f, hw + 2.6f, 1.85f, 4);

                // parapet: outer face in the plane of the wall, a cap, an inner face
                float ph = existing ? 0.45f : tall ? 1.3f : housing ? 1.0f : shed ? 0.6f : 0.9f, pt = area < 200f ? 0.25f : 0.4f;
                if (existing && area < 110f) ph = 0f;
                if (ph > 0f) foreach (var e in outline)
                {
                    Vector3 up = Vector3.up * ph, ai = e.a + e.inw * pt, bi2 = e.b + e.inw * pt;
                    Quad(e.a, e.b, e.b + up, e.a + up, -e.inw, 1);
                    Quad(e.a + up, e.b + up, bi2 + up, ai + up, Vector3.up, 1);
                    Quad(ai, bi2, bi2 + up, ai + up, e.inw, 1);
                }
                if (!quad || existing || hw < 3f) continue;

                if (tall || (k == "res_high" && bi.floors >= 14))
                {
                    // a set-back top storey for plant, and on the tallest a second step
                    float s1 = 0.66f + 0.12f * Hash(id, 1), h1 = 3.4f + 1.6f * Hash(id, 2);
                    Box(cen, U, W, hu * s1, hw * s1, h1, 1);
                    if (bi.floors >= 20) Box(cen + Vector3.up * h1, U, W, hu * s1 * 0.55f, hw * s1 * 0.55f, 2.6f + 2.4f * Hash(id, 3), 1);
                    if (Hash(id, 4) < 0.5f) Box(cen + U * hu * (s1 + 0.14f) * (Hash(id, 5) < 0.5f ? 1 : -1), U, W, Mathf.Min(1.6f, hu * 0.1f), Mathf.Min(2.4f, hw * 0.3f), 1.5f, 2);
                }
                else if (shed)
                {
                    // long roof lights across the shed
                    if (area > 900f)
                    {
                        int rows = Mathf.Clamp(Mathf.FloorToInt(hw * 2f / 9f), 1, 10);
                        for (int i = 0; i < rows; i++) Box(cen + W * ((i + 0.5f) / rows - 0.5f) * 2f * (hw - 3f), U, W, hu - 3.5f, 0.9f, 0.85f, 2);
                    }
                    if (Hash(id, 6) < 0.6f) Box(cen + U * (hu - 4f) * (Hash(id, 7) < 0.5f ? 1 : -1) + W * (hw - 4f) * (Hash(id, 8) < 0.5f ? 1 : -1), U, W, 1.6f, 1.6f, 2.2f, 2);
                }
                else
                {
                    // stair and lift heads along the building, and some plant
                    int n = area < 260f ? 0 : area < 800f ? 1 : area < 2400f ? 2 : 3;
                    for (int i = 0; i < n; i++)
                    {
                        float fu = n == 1 ? (Hash(id, 9) - 0.5f) * 0.5f : ((i + 0.5f) / n - 0.5f) * 1.5f, fw = (Hash(id, 10 + i) - 0.5f) * 0.5f;
                        Box(cen + U * hu * fu + W * hw * fw, U, W, Mathf.Min(2.8f, hu * 0.22f), Mathf.Min(1.9f, hw * 0.3f), 2.5f + 0.5f * Hash(id, 20 + i), 1);
                    }
                    int plant = area < 400f ? 0 : area < 1500f ? 1 : 2;
                    for (int i = 0; i < plant; i++)
                        Box(cen + U * hu * (Hash(id, 30 + i) - 0.5f) * 1.3f + W * hw * (Hash(id, 40 + i) - 0.5f) * 1.1f, U, W, 1.1f + Hash(id, 50 + i), 0.9f + 0.6f * Hash(id, 60 + i), 1.1f + 0.7f * Hash(id, 70 + i), 2);
                }
            }
            return outT;
        }
    }
}
