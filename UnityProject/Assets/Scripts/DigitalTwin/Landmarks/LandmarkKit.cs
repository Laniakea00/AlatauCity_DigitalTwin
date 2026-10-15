using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Surface materials of AlatauCity/Landmark (uv1.x of every vertex).</summary>
    public static class LM
    {
        public const int Solid = 0, Glass = 1, Metal = 2, Roof = 3, Paving = 4, Light = 5, Plant = 6, Water = 7, Fins = 8, Steel = 9;
        public static Color32 C(string hex) { ColorUtility.TryParseHtmlString(hex, out var c); return c; }
    }

    /// <summary>A tiny procedural modeller: flat-shaded quads, prisms on any footprint, lofts between footprints of equal vertex count,
    /// cylinders, frames and trees. Vertex layout for AlatauCity/Landmark: colour, uv0 = facade metres (along, up), uv1 = (material, param).
    /// Coordinates are local to the landmark (x east-ish along the long side, y up from the base, z across).</summary>
    public class LandmarkKit
    {
        readonly List<Vector3> v = new List<Vector3>(), n = new List<Vector3>();
        readonly List<Color32> c = new List<Color32>();
        readonly List<Vector2> uv0 = new List<Vector2>(), uv1 = new List<Vector2>();
        readonly List<int> t = new List<int>();
        public int VertexCount => v.Count;
        /// <summary>Sets the colour alpha of the vertices from 'start' to the end (AlatauLandmark: alpha = 1 − landscaping stage).</summary>
        public void AlphaFrom(int start, byte a) { for (int i = start; i < c.Count; i++) { var q = c[i]; q.a = a; c[i] = q; } }

        // ------------------------------------------------------------------ primitives
        /// <summary>Quad a-b-c-d (any winding); it faces along 'outward'. uv = facade metres for each corner.</summary>
        public void Quad(Vector3 a, Vector3 b, Vector3 cc, Vector3 d, Vector3 outward, Color32 col, int mat, float prm, Vector2 ua, Vector2 ub, Vector2 uc, Vector2 ud)
        {
            var nn = Vector3.Cross(b - a, cc - a); if (nn.sqrMagnitude < 1e-10f) nn = Vector3.Cross(cc - a, d - a);
            bool flip = Vector3.Dot(nn, outward) < 0; nn = nn.normalized; if (flip) nn = -nn;
            int i = v.Count;
            v.Add(a); v.Add(b); v.Add(cc); v.Add(d);
            for (int k = 0; k < 4; k++) { n.Add(nn); c.Add(col); uv1.Add(new Vector2(mat, prm)); }
            uv0.Add(ua); uv0.Add(ub); uv0.Add(uc); uv0.Add(ud);
            if (!flip) { t.Add(i); t.Add(i + 1); t.Add(i + 2); t.Add(i); t.Add(i + 2); t.Add(i + 3); }
            else { t.Add(i); t.Add(i + 2); t.Add(i + 1); t.Add(i); t.Add(i + 3); t.Add(i + 2); }
        }
        public void Tri(Vector3 a, Vector3 b, Vector3 cc, Vector3 outward, Color32 col, int mat, float prm, Vector2 ua, Vector2 ub, Vector2 uc)
        {
            var nn = Vector3.Cross(b - a, cc - a); bool flip = Vector3.Dot(nn, outward) < 0; nn = nn.normalized; if (flip) nn = -nn;
            int i = v.Count; v.Add(a); v.Add(b); v.Add(cc);
            for (int k = 0; k < 3; k++) { n.Add(nn); c.Add(col); uv1.Add(new Vector2(mat, prm)); }
            uv0.Add(ua); uv0.Add(ub); uv0.Add(uc);
            if (!flip) { t.Add(i); t.Add(i + 1); t.Add(i + 2); } else { t.Add(i); t.Add(i + 2); t.Add(i + 1); }
        }
        /// <summary>Horizontal polygon (convex or star-shaped around its centroid) at height y, facing up (or down).</summary>
        public void Cap(IList<Vector2> fp, float y, bool up, Color32 col, int mat, float prm = 3f)
        {
            Vector2 ce = Vector2.zero; foreach (var p in fp) ce += p; ce /= fp.Count;
            var o = up ? Vector3.up : Vector3.down; var C = new Vector3(ce.x, y, ce.y);
            for (int i = 0; i < fp.Count; i++)
            {
                var a = fp[i]; var b = fp[(i + 1) % fp.Count];
                Tri(C, new Vector3(a.x, y, a.y), new Vector3(b.x, y, b.y), o, col, mat, prm, ce, a, b);
            }
        }
        /// <summary>Vertical walls of a footprint from y0 to y1 (+ top cap, optional bottom).</summary>
        public void Prism(IList<Vector2> fp, float y0, float y1, Color32 wall, int wallMat, float prm, Color32 top, int topMat, bool bottom = false, float topPrm = 3f)
        {
            Vector2 ce = Vector2.zero; foreach (var p in fp) ce += p; ce /= fp.Count;
            float u = 0;
            for (int i = 0; i < fp.Count; i++)
            {
                var a = fp[i]; var b = fp[(i + 1) % fp.Count]; float L = (b - a).magnitude; if (L < 1e-3f) continue;
                var mid = (a + b) * 0.5f; var o = new Vector3(mid.x - ce.x, 0, mid.y - ce.y);
                var e = new Vector2(b.y - a.y, -(b.x - a.x)); var eo = new Vector3(e.x, 0, e.y); if (Vector3.Dot(eo, o) < 0) eo = -eo;
                Quad(new Vector3(a.x, y0, a.y), new Vector3(b.x, y0, b.y), new Vector3(b.x, y1, b.y), new Vector3(a.x, y1, a.y), eo, wall, wallMat, prm,
                     new Vector2(u, y0), new Vector2(u + L, y0), new Vector2(u + L, y1), new Vector2(u, y1));
                u += L;
            }
            if (topMat >= 0) Cap(fp, y1, true, top, topMat, topPrm);
            if (bottom) Cap(fp, y0, false, wall, wallMat);
        }
        /// <summary>Walls between two footprints with the same number of corners (sloped / tapering faces).</summary>
        public void Loft(IList<Vector2> f0, float y0, IList<Vector2> f1, float y1, Color32 wall, int mat, float prm)
        {
            Vector2 c0 = Vector2.zero, c1 = Vector2.zero; foreach (var p in f0) c0 += p; foreach (var p in f1) c1 += p; c0 /= f0.Count; c1 /= f1.Count;
            float u = 0;
            for (int i = 0; i < f0.Count; i++)
            {
                int j = (i + 1) % f0.Count;
                Vector3 a = new Vector3(f0[i].x, y0, f0[i].y), b = new Vector3(f0[j].x, y0, f0[j].y), d = new Vector3(f1[i].x, y1, f1[i].y), e = new Vector3(f1[j].x, y1, f1[j].y);
                float L0 = (f0[j] - f0[i]).magnitude, L1 = (f1[j] - f1[i]).magnitude; if (L0 < 1e-3f && L1 < 1e-3f) continue;
                var mid = (a + b + d + e) * 0.25f; var ce = new Vector3((c0.x + c1.x) * 0.5f, mid.y, (c0.y + c1.y) * 0.5f);
                var o = mid - ce; o.y = 0;
                float off = (L0 - L1) * 0.5f;
                Quad(a, b, e, d, o, wall, mat, prm, new Vector2(u, y0), new Vector2(u + L0, y0), new Vector2(u + off + L1, y1), new Vector2(u + off, y1));
                u += L0;
            }
        }
        public void Box(Vector3 center, Vector3 size, float yawDeg, Color32 wall, int wallMat, float prm, Color32 top, int topMat)
        {
            var fp = Rect(center.x, center.z, size.x, size.z, yawDeg);
            Prism(fp, center.y - size.y * 0.5f, center.y + size.y * 0.5f, wall, wallMat, prm, top, topMat, center.y - size.y * 0.5f > 0.5f);
        }
        /// <summary>Box between two points (a beam, a rail, a mast) with a square cross-section w × h.</summary>
        public void Beam(Vector3 p0, Vector3 p1, float w, float h, Color32 col, int mat, float prm = 3f)
        {
            var dir = p1 - p0; float L = dir.magnitude; if (L < 1e-3f) return; dir /= L;
            var side = Vector3.Cross(dir, Mathf.Abs(dir.y) > 0.95f ? Vector3.right : Vector3.up).normalized * (w * 0.5f);
            var up = Vector3.Cross(side, dir).normalized * (h * 0.5f);
            Vector3[] q0 = { p0 - side - up, p0 + side - up, p0 + side + up, p0 - side + up }, q1 = { p1 - side - up, p1 + side - up, p1 + side + up, p1 - side + up };
            for (int i = 0; i < 4; i++)
            {
                int j = (i + 1) % 4; var o = (q0[i] + q0[j]) * 0.5f - p0;
                Quad(q0[i], q0[j], q1[j], q1[i], o, col, mat, prm, new Vector2(0, 0), new Vector2(w, 0), new Vector2(w, L), new Vector2(0, L));
            }
            Quad(q0[0], q0[1], q0[2], q0[3], -dir, col, mat, prm, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
            Quad(q1[0], q1[1], q1[2], q1[3], dir, col, mat, prm, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
        }
        /// <summary>Vertical cylinder (smooth sides), optional cone / dome top.</summary>
        public void Cylinder(Vector3 baseC, float r, float h, int seg, Color32 col, int mat, float prm, Color32 top, int topMat, float coneH = 0f)
        {
            int i0 = v.Count;
            float circ = 2 * Mathf.PI * r;
            for (int s = 0; s <= seg; s++)
            {
                float a = s * 2 * Mathf.PI / seg; var dir = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v.Add(baseC + dir * r); v.Add(baseC + dir * r + Vector3.up * h);
                n.Add(dir); n.Add(dir); c.Add(col); c.Add(col);
                uv0.Add(new Vector2(circ * s / seg, baseC.y)); uv0.Add(new Vector2(circ * s / seg, baseC.y + h));
                uv1.Add(new Vector2(mat, prm)); uv1.Add(new Vector2(mat, prm));
            }
            for (int s = 0; s < seg; s++) { int a = i0 + s * 2; t.Add(a); t.Add(a + 1); t.Add(a + 3); t.Add(a); t.Add(a + 3); t.Add(a + 2); }
            if (topMat < 0) return;
            var tc = baseC + Vector3.up * (h + coneH);
            for (int s = 0; s < seg; s++)
            {
                float a0 = s * 2 * Mathf.PI / seg, a1 = (s + 1) * 2 * Mathf.PI / seg;
                var p0 = baseC + new Vector3(Mathf.Cos(a0), 0, Mathf.Sin(a0)) * r + Vector3.up * h; var p1 = baseC + new Vector3(Mathf.Cos(a1), 0, Mathf.Sin(a1)) * r + Vector3.up * h;
                Tri(tc, p0, p1, Vector3.up + (p0 + p1 - 2 * baseC).normalized * (coneH > 0 ? 0.5f : 0f), top, topMat, prm, new Vector2(tc.x, tc.z), new Vector2(p0.x, p0.z), new Vector2(p1.x, p1.z));
            }
        }
        /// <summary>A tube between two points (octagon, radius r0 → r1): fuselages, pipes, masts lying down.</summary>
        public void Tube(Vector3 p0, Vector3 p1, float r0, float r1, int seg, Color32 col, int mat, bool caps = true, float prm = 3f)
        {
            var dir = (p1 - p0).normalized; var a = Vector3.Cross(dir, Mathf.Abs(dir.y) > 0.9f ? Vector3.right : Vector3.up).normalized; var b = Vector3.Cross(dir, a);
            float L = (p1 - p0).magnitude;
            for (int s = 0; s < seg; s++)
            {
                float t0 = s * 2 * Mathf.PI / seg, t1 = (s + 1) * 2 * Mathf.PI / seg;
                Vector3 d0 = a * Mathf.Cos(t0) + b * Mathf.Sin(t0), d1 = a * Mathf.Cos(t1) + b * Mathf.Sin(t1);
                var q0 = p0 + d0 * r0; var q1 = p0 + d1 * r0; var q2 = p1 + d1 * r1; var q3 = p1 + d0 * r1;
                float u0 = r0 * t0, u1 = r0 * t1;
                Quad(q0, q1, q2, q3, (d0 + d1) * 0.5f, col, mat, prm, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, L), new Vector2(u0, L));
                if (caps)
                {
                    if (r0 > 0.01f) Tri(p0, q1, q0, -dir, col, mat, prm, Vector2.zero, Vector2.right, Vector2.up);
                    if (r1 > 0.01f) Tri(p1, q3, q2, dir, col, mat, prm, Vector2.zero, Vector2.right, Vector2.up);
                }
            }
        }
        /// <summary>A flat slab between four points in a plane (wings, tail planes), thickness t along 'up'.</summary>
        public void Slab(Vector3 a, Vector3 b, Vector3 c, Vector3 d, float t, Color32 col, int mat)
        {
            var n = Vector3.Cross(b - a, d - a).normalized; var o = n * (t * 0.5f);
            Quad(a + o, b + o, c + o, d + o, n, col, mat, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
            Quad(d - o, c - o, b - o, a - o, -n, col, mat, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
            Vector3[] q = { a, b, c, d };
            for (int i = 0; i < 4; i++) { var p = q[i]; var r = q[(i + 1) % 4]; var e = ((p + r) * 0.5f - (a + c) * 0.5f).normalized; Quad(p - o, r - o, r + o, p + o, e, col, mat, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up); }
        }
        /// <summary>Material parameter that marks a tree (AlatauLandmark plants it only when the site is landscaped).</summary>
        public const float TreeTag = -7f;
        /// <summary>Early landscape: a lawn, path or pond (GreenTag, pass as the facade / top parameter) or trees (Planted = true → ParkTreeTag)
        /// of a park laid out before the buildings — green from the start of the works (see AlatauLandmark.shader).</summary>
        public const float GreenTag = -5f, ParkTreeTag = -9f;
        public bool Planted;
        /// <summary>A low-poly tree: trunk + faceted crown.</summary>
        public void Tree(Vector3 p, float h, Color32 leaf, float seed)
        {
            float r = h * 0.32f; var trunk = LM.C("#5b4a3a");
            float tag = Planted ? ParkTreeTag : TreeTag;
            Beam(p, p + Vector3.up * (h * 0.45f), 0.35f, 0.35f, trunk, LM.Solid, tag);   // TreeTag: planted at the end of construction
            var cc = p + Vector3.up * (h * 0.62f);
            int seg = 6; float rot = seed * 37f;
            for (int s = 0; s < seg; s++)
            {
                float a0 = (s * 60f + rot) * Mathf.Deg2Rad, a1 = ((s + 1) * 60f + rot) * Mathf.Deg2Rad;
                var e0 = cc + new Vector3(Mathf.Cos(a0) * r, 0, Mathf.Sin(a0) * r); var e1 = cc + new Vector3(Mathf.Cos(a1) * r, 0, Mathf.Sin(a1) * r);
                var top = cc + Vector3.up * (h * 0.40f); var bot = cc - Vector3.up * (h * 0.22f);
                var o = ((e0 + e1) * 0.5f - cc);
                Tri(top, e0, e1, o + Vector3.up * r, leaf, LM.Plant, tag, new Vector2(top.x, top.z), new Vector2(e0.x, e0.z), new Vector2(e1.x, e1.z));
                Tri(bot, e1, e0, o - Vector3.up * r, leaf, LM.Plant, tag, new Vector2(bot.x, bot.z), new Vector2(e1.x, e1.z), new Vector2(e0.x, e0.z));
            }
        }

        // ------------------------------------------------------------------ footprints
        public static List<Vector2> Rect(float cx, float cz, float w, float d, float yawDeg = 0f)
        {
            var l = new List<Vector2> { new Vector2(-w / 2, -d / 2), new Vector2(w / 2, -d / 2), new Vector2(w / 2, d / 2), new Vector2(-w / 2, d / 2) };
            return Move(l, cx, cz, yawDeg);
        }
        /// <summary>Rectangle with rounded corners (radius r, k segments per corner).</summary>
        public static List<Vector2> RoundRect(float cx, float cz, float w, float d, float r, int k = 4, float yawDeg = 0f)
        {
            r = Mathf.Min(r, Mathf.Min(w, d) * 0.5f - 0.01f); var l = new List<Vector2>();
            Vector2[] cs = { new Vector2(w / 2 - r, -d / 2 + r), new Vector2(w / 2 - r, d / 2 - r), new Vector2(-w / 2 + r, d / 2 - r), new Vector2(-w / 2 + r, -d / 2 + r) };
            float[] a0 = { -90f, 0f, 90f, 180f };
            for (int q = 0; q < 4; q++) for (int s = 0; s <= k; s++) { float a = (a0[q] + 90f * s / k) * Mathf.Deg2Rad; l.Add(cs[q] + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r); }
            return Move(l, cx, cz, yawDeg);
        }
        /// <summary>Rectangle with chamfered corners (cut c).</summary>
        public static List<Vector2> Chamfer(float cx, float cz, float w, float d, float cut, float yawDeg = 0f)
        {
            cut = Mathf.Min(cut, Mathf.Min(w, d) * 0.45f);
            var l = new List<Vector2> { new Vector2(-w / 2 + cut, -d / 2), new Vector2(w / 2 - cut, -d / 2), new Vector2(w / 2, -d / 2 + cut), new Vector2(w / 2, d / 2 - cut),
                                        new Vector2(w / 2 - cut, d / 2), new Vector2(-w / 2 + cut, d / 2), new Vector2(-w / 2, d / 2 - cut), new Vector2(-w / 2, -d / 2 + cut) };
            return Move(l, cx, cz, yawDeg);
        }
        public static List<Vector2> Circle(float cx, float cz, float r, int seg)
        {
            var l = new List<Vector2>(); for (int s = 0; s < seg; s++) { float a = s * 2 * Mathf.PI / seg; l.Add(new Vector2(cx + Mathf.Cos(a) * r, cz + Mathf.Sin(a) * r)); }
            return l;
        }
        public static List<Vector2> Move(List<Vector2> l, float cx, float cz, float yawDeg)
        {
            float a = -yawDeg * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
            for (int i = 0; i < l.Count; i++) { var p = l[i]; l[i] = new Vector2(cx + p.x * ca - p.y * sa, cz + p.x * sa + p.y * ca); }
            return l;
        }

        // ------------------------------------------------------------------ output
        public Mesh ToMesh(string name)
        {
            var m = new Mesh { name = name, indexFormat = v.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16 };
            m.SetVertices(v); m.SetNormals(n); m.SetColors(c); m.SetUVs(0, uv0); m.SetUVs(1, uv1); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }
    }
}
