using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

namespace AlatauCity.EditorTools
{
    /// <summary>What the plain boxes of the model lack. Per building and by its kind this adds:
    /// a parapet around every flat roof, a stepped crown on towers, stair and plant boxes on housing and public buildings,
    /// rows of roof lights on industrial sheds, a hipped tile roof on small existing houses, eaves and a chimney on the
    /// generated houses, and a paved plinth around larger buildings so they meet the ground on a slope. From gen_buildings' columns
    /// of buildings.csv (merge_districts, read by name): a building on a slope (plinth_m) gets its plinth dressed in that paving down
    /// below its lowest ground, a class-A shed (dock) its dock doors under a canopy on the dock side, and a canopy (model bus_canopy,
    /// a roof slab on posts from merge) plain sleeves on its posts.
    /// The extra triangles carry the building's id and year like the rest, plus a part code in uv.y (negative):
    /// -1 parapet, crown, chimney, the pilasters that break a wall longer than 60 m (the wall material, no windows), -2 plant or roof
    /// light, -3 tiled roof, -4 paved plinth.
    /// AlatauLit draws them only in the film look, so the plain maket look is exactly what it was.</summary>
    public static class AlatauRoofs
    {
        public struct Tri { public Vector3 a, b, c; public byte col, part; public ushort year; public int bid; }
        public class Info
        {
            public string kind, model = ""; public int floors; public float height, ground;
            public float plinth;                         // metres of plinth under the floor (ground_m) on a slope, 0 = none
            public Vector2 dockA, dockB; public int docks;   // a shed's dock side (world x, z) and its number of doors, 0 = none
        }

        public static Dictionary<int, Info> LoadCsv(string path)
        {
            var d = new Dictionary<int, Info>();
            var lines = File.ReadAllLines(path);
            // bid,id,district,kind,use,source,year,floors,height_m,gfa_m2,parcel,x,z,ground_m,easting,northing by index, then by name
            // (merge_districts) model, plinth_m and dock "x0 z0 x1 z1 n"
            var head = lines.Length > 0 ? new List<string>(lines[0].Split(',')) : new List<string>();
            int iModel = head.IndexOf("model"), iPlinth = head.IndexOf("plinth_m"), iDock = head.IndexOf("dock");
            float F(string s) => float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
            for (int i = 1; i < lines.Length; i++)
            {
                var p = lines[i].Split(','); if (p.Length < 14) continue;
                if (!int.TryParse(p[0], out int bid)) continue;
                var inf = new Info { kind = p[3], floors = (int)F(p[7]), height = F(p[8]), ground = F(p[13]) };
                if (iModel >= 0 && iModel < p.Length) inf.model = p[iModel];
                if (iPlinth >= 0 && iPlinth < p.Length) inf.plinth = Mathf.Max(0f, F(p[iPlinth]));
                if (iDock >= 0 && iDock < p.Length && p[iDock].Length > 0)
                {
                    var q = p[iDock].Split(' ');
                    if (q.Length == 5) { inf.dockA = new Vector2(F(q[0]), F(q[1])); inf.dockB = new Vector2(F(q[2]), F(q[3])); inf.docks = (int)F(q[4]); }
                }
                d[bid] = inf;
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
            var canopyTris = new Dictionary<int, List<int>>();       // every triangle of a canopy (the feet of its posts)
            for (int t = 0; t < nt; t++)
            {
                Vector3 a = V[T[t * 3]], b = V[T[t * 3 + 1]], c = V[T[t * 3 + 2]];
                if (info.TryGetValue(bid[t], out var ci) && ci.model == "bus_canopy")
                {
                    if (!canopyTris.TryGetValue(bid[t], out var cl)) canopyTris[bid[t]] = cl = new List<int>();
                    cl.Add(t);
                }
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
                // a house on a slope (plinth_m): a skirt of paving round the walls from under its lowest ground to just above the floor,
                // as other outlines on a slope get below; the walls are the rectangle of the eaves along the ridge
                if (bi.plinth > 0f && bi.ground > 1f)
                {
                    float lowY = float.MaxValue; Vector3 ax = Vector3.zero;
                    foreach (var pk in planes.Keys) foreach (var q in planes[pk]) lowY = Mathf.Min(lowY, q.y);
                    foreach (var pk in planes.Keys) { var nn = normals[pk]; var h = new Vector3(-nn.z, 0, nn.x); if (h.sqrMagnitude > 0.01f) { ax = h.normalized; break; } }
                    if (ax == Vector3.zero) ax = Vector3.right;
                    var aw = new Vector3(-ax.z, 0, ax.x); float u0 = float.MaxValue, u1 = float.MinValue, w0 = float.MaxValue, w1 = float.MinValue;
                    foreach (var pk in planes.Keys) foreach (var q in planes[pk])
                        if (q.y < lowY + 0.3f) { float u = Vector3.Dot(q, ax), w = Vector3.Dot(q, aw); u0 = Mathf.Min(u0, u); u1 = Mathf.Max(u1, u); w0 = Mathf.Min(w0, w); w1 = Mathf.Max(w1, w); }
                    if (u1 - u0 > 1f && w1 - w0 > 1f)
                    {
                        float sb = bi.ground - bi.plinth - 0.6f, st = bi.ground + 0.1f; const float off = 0.06f;
                        Vector3 P(float u, float w, float y) { var v = ax * u + aw * w; v.y = y; return v; }
                        var cs = new[] { (u0 - off, w0 - off), (u1 + off, w0 - off), (u1 + off, w1 + off), (u0 - off, w1 + off) };
                        var mid = P((u0 + u1) * 0.5f, (w0 + w1) * 0.5f, 0f);
                        for (int i = 0; i < 4; i++)
                        {
                            var (ua, wa) = cs[i]; var (ub, wb) = cs[(i + 1) % 4];
                            Vector3 a0 = P(ua, wa, 0f), b0 = P(ub, wb, 0f), o = ((a0 + b0) * 0.5f - mid); o.y = 0; o.Normalize();
                            Quad(a0 + Vector3.up * sb, b0 + Vector3.up * sb, b0 + Vector3.up * st, a0 + Vector3.up * st, o, 4);
                            Quad(a0 + Vector3.up * st, b0 + Vector3.up * st, b0 - o * off + Vector3.up * st, a0 - o * off + Vector3.up * st, Vector3.up, 4);
                        }
                    }
                }
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
            var posts = new List<(Vector3 foot, float h)>();
            var runs = new Dictionary<long, List<(float s0, float s1, Vector3 a, Vector3 inw)>>();   // wall lines of an outline
            foreach (var kv in roofs)
            {
                id = kv.Key; if (!info.TryGetValue(id, out var bi)) continue;
                string k = bi.kind; if (k == "house" || k == "solar") continue;
                var list = kv.Value; int t0 = list[0]; curCol = col[t0]; curYear = yr[t0];
                bool canopy = bi.model == "bus_canopy"; posts.Clear();
                if (canopy)
                {
                    // a canopy: the slab's top is its roof; the tops of its posts (under the slab) mark the posts, which get plain
                    // sleeves (the wall material without windows) from their feet up to the slab
                    float top = float.MinValue; foreach (int t in list) top = Mathf.Max(top, V[T[t * 3]].y);
                    var slab = new List<int>(); var heads = new List<(Vector3 sum, int n, Vector3 first)>();
                    foreach (int t in list)
                    {
                        if (V[T[t * 3]].y > top - 0.1f) { slab.Add(t); continue; }
                        for (int j = 0; j < 3; j++)
                        {
                            var p = V[T[t * 3 + j]]; int g = -1;
                            for (int h = 0; h < heads.Count; h++) if (Mathf.Abs(heads[h].first.x - p.x) < 0.6f && Mathf.Abs(heads[h].first.z - p.z) < 0.6f) { g = h; break; }
                            if (g < 0) heads.Add((p, 1, p)); else heads[g] = (heads[g].sum + p, heads[g].n + 1, heads[g].first);
                        }
                    }
                    if (slab.Count == 0) continue;
                    canopyTris.TryGetValue(id, out var all);
                    foreach (var hd in heads)
                    {
                        var c = hd.sum / hd.n; float foot = c.y;
                        if (all != null)
                            foreach (int t in all)
                                for (int j = 0; j < 3; j++)
                                {
                                    var p = V[T[t * 3 + j]]; if (Mathf.Abs(p.x - c.x) < 0.35f && Mathf.Abs(p.z - c.z) < 0.35f) foot = Mathf.Min(foot, p.y);
                                }
                        if (c.y - foot > 0.5f) posts.Add((new Vector3(c.x, foot, c.z), c.y - foot));
                    }
                    list = slab; t0 = list[0];
                }

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

                // a shed's dock side: the wall it lies on and the way out of it (into the truck yard)
                bool dock = bi.docks > 0 && (bi.dockB - bi.dockA).sqrMagnitude > 1f;
                Vector3 dA = new Vector3(bi.dockA.x, 0, bi.dockA.y), dB = new Vector3(bi.dockB.x, 0, bi.dockB.y), dOut = Vector3.zero;
                if (dock)
                {
                    var dd = (dB - dA).normalized; dOut = new Vector3(-dd.z, 0, dd.x); var rc = new Vector3(cen.x, 0, cen.z);
                    if (!quad) { rc = Vector3.zero; foreach (var e in outline) rc += new Vector3(e.a.x, 0, e.a.z); rc /= outline.Count; }
                    if (Vector3.Dot(dOut, (dA + dB) * 0.5f - rc) < 0) dOut = -dOut;
                }

                // a paved plinth around the building: a level terrace that also hides the gap on sloping ground. A building on a slope
                // (plinth_m) has it reach below its lowest ground; on a dock side the terrace stops at the wall (the yard meets the doors)
                if (quad && (!existing || area >= 300f) && bi.ground > 1f && (y - bi.ground > 2.5f || bi.plinth > 0f))
                {
                    float depth = Mathf.Max(1.5f, bi.plinth + 0.8f); Vector3 tc = new Vector3(cen.x, bi.ground - depth, cen.z); float tu = hu + 2.6f, tw = hw + 2.6f;
                    if (dock)
                    {
                        float su = Vector3.Dot(dOut, U), sw = Vector3.Dot(dOut, W);
                        if (Mathf.Abs(sw) > Mathf.Abs(su)) { tw -= 1.3f; tc -= W * Mathf.Sign(sw) * 1.3f; } else { tu -= 1.3f; tc -= U * Mathf.Sign(su) * 1.3f; }
                    }
                    Box(tc, U, W, tu, tw, depth + 0.35f, 4);
                }
                else if (bi.plinth > 0f && bi.ground > 1f)
                {
                    // any other outline on a slope: a skirt of the same paving just outside the walls, from under the lowest ground up
                    // to just above the floor, with a narrow cap (the walls of the plinth carry no windows or shopfronts then)
                    float sb = bi.ground - bi.plinth - 0.6f, st = bi.ground + 0.1f; const float off = 0.06f;
                    foreach (var e in outline)
                    {
                        var d = e.b - e.a; d.y = 0; d.Normalize(); var o = -e.inw * off;
                        Vector3 a0 = new Vector3(e.a.x, 0, e.a.z), b0 = new Vector3(e.b.x, 0, e.b.z), a1 = a0 + o - d * off, b1 = b0 + o + d * off;
                        Quad(a1 + Vector3.up * sb, b1 + Vector3.up * sb, b1 + Vector3.up * st, a1 + Vector3.up * st, -e.inw, 4);
                        Quad(a1 + Vector3.up * st, b1 + Vector3.up * st, b0 + Vector3.up * st, a0 + Vector3.up * st, Vector3.up, 4);
                    }
                }

                // dock doors: one sectional door per dock along the dock side (pale metal, the louvre lines read as its panels), a dock
                // shelter canopy over them all
                if (dock)
                {
                    var dd = (dB - dA); float L = dd.magnitude; dd /= L; float g = bi.ground;
                    for (int i = 0; i < bi.docks; i++)
                    {
                        var at = dA + dd * (L * (i + 0.5f) / bi.docks) + dOut * 0.07f;
                        Box(new Vector3(at.x, g - 0.2f, at.z), dd, dOut, Mathf.Min(1.4f, L / bi.docks * 0.36f), 0.09f, 3.2f, 2);
                    }
                    var mid = (dA + dB) * 0.5f + dOut * 1.27f; const float cy = 4.0f, ct = 0.3f;
                    Box(new Vector3(mid.x, g + cy, mid.z), dd, dOut, L * 0.5f, 1.25f, ct, 1);
                    Vector3 c0 = mid - dd * L * 0.5f - dOut * 1.25f, c1 = mid + dd * L * 0.5f - dOut * 1.25f, c2 = mid + dd * L * 0.5f + dOut * 1.25f, c3 = mid - dd * L * 0.5f + dOut * 1.25f;
                    Quad(c0 + Vector3.up * (g + cy), c1 + Vector3.up * (g + cy), c2 + Vector3.up * (g + cy), c3 + Vector3.up * (g + cy), Vector3.down, 1);
                }

                // a canopy's posts: plain sleeves a little wider than the post from its foot up to the slab; no parapet, nothing on top
                if (canopy)
                {
                    foreach (var pp in posts) Box(pp.foot, U, W, 0.26f, 0.26f, pp.h, 1);
                    continue;
                }

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
                // no facade runs on unbroken for more than 60 m (rule 18): a wall line longer than that (one face, or collinear faces of an
                // outline) gets a pilaster at every joint of the film facade's sections (AlatauFilm: ceil(L / 48) sections meeting at a
                // 2.4 m blank pier), 2.4 m wide and 0.45 m proud of the wall, from below the ground to over the parapet; a shed's stand
                // 0.6 m over its roof as fire walls do, and on a dock side they start over the dock canopy
                runs.Clear();
                foreach (var e in outline)
                {
                    var dl = new Vector3(e.inw.z, 0, -e.inw.x);
                    long key = ((long)Mathf.RoundToInt(Mathf.Atan2(e.inw.z, e.inw.x) * Mathf.Rad2Deg * 0.5f) & 0xFFF)
                             | (((long)Mathf.RoundToInt(Vector3.Dot(e.a, e.inw) * 2f) & 0xFFFFFF) << 12) | (((long)Mathf.RoundToInt(e.a.y) & 0xFFFF) << 36);
                    float s0 = Vector3.Dot(e.a, dl), s1 = Vector3.Dot(e.b, dl);
                    if (!runs.TryGetValue(key, out var rl)) runs[key] = rl = new List<(float s0, float s1, Vector3 a, Vector3 inw)>();
                    rl.Add((Mathf.Min(s0, s1), Mathf.Max(s0, s1), e.a, e.inw));
                }
                foreach (var rl in runs.Values)
                {
                    rl.Sort((x1, x2) => x1.s0.CompareTo(x2.s0));
                    for (int i = 0; i < rl.Count;)
                    {
                        float r0 = rl[i].s0, r1 = rl[i].s1; int j = i + 1;
                        while (j < rl.Count && rl[j].s0 <= r1 + 0.3f) { r1 = Mathf.Max(r1, rl[j].s1); j++; }
                        float L = r1 - r0; var a0 = rl[i].a; var inw = rl[i].inw; var dl = new Vector3(inw.z, 0, -inw.x);
                        i = j;
                        if (L <= 60f) continue;
                        bool onDock = dock && Mathf.Abs(Vector3.Dot(dOut, inw)) > 0.9f && Mathf.Abs(Vector3.Dot(new Vector3(dA.x, a0.y, dA.z) - a0, inw)) < 2f;
                        float top = a0.y + ph + (shed ? 0.6f : 0.15f);
                        float foot = onDock ? bi.ground + 4.3f : Mathf.Min(bi.ground > 1f ? bi.ground - bi.plinth - 1f : a0.y - Mathf.Max(bi.height, 3f) - 0.5f, a0.y - 2f);
                        if (top - foot < 0.5f) continue;
                        int ns = Mathf.CeilToInt(L / 48f);
                        for (int k2 = 1; k2 < ns; k2++)
                        {
                            float sk = r0 + L * k2 / ns; var at = a0 + dl * (sk - Vector3.Dot(a0, dl)) - inw * 0.2f;
                            Box(new Vector3(at.x, foot, at.z), dl, inw, 1.2f, 0.25f, top - foot, 1);
                        }
                    }
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
