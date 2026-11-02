using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Polygons of the new map data (Resources/Landmarks/noplant.json, parking.json, solar.json, districts.json; tools/map
    /// CONTRACT §6): flat [x, z, x, z, …] rings in Unity metres, years [base, fast, slow, infra]. Small geometry helpers for the readers.</summary>
    public static class MapPolys
    {
        /// <summary>A ring from flat x, z pairs (a closing point equal to the first is dropped); null when it has fewer than 3 corners.</summary>
        public static Vector2[] Ring(float[] p)
        {
            if (p == null || p.Length < 6) return null;
            int n = p.Length / 2;
            if (n > 3 && Mathf.Abs(p[0] - p[(n - 1) * 2]) < 1e-3f && Mathf.Abs(p[1] - p[(n - 1) * 2 + 1]) < 1e-3f) n--;
            var r = new Vector2[n]; for (int i = 0; i < n; i++) r[i] = new Vector2(p[i * 2], p[i * 2 + 1]);
            return r;
        }
        /// <summary>The year a thing of the data appears in scenario sc (0 = always there, also when the years are missing).</summary>
        public static int Year(int[] y, int sc)
        {
            if (y == null || y.Length == 0) return 0;
            return y[Mathf.Clamp(sc, 0, y.Length - 1)];
        }
        /// <summary>The earliest year over the scenarios (0 = always).</summary>
        public static int FirstYear(int[] y) { if (y == null || y.Length == 0) return 0; int m = int.MaxValue; foreach (var v in y) m = Mathf.Min(m, v); return m; }

        public static bool Inside(Vector2[] r, float x, float z)
        {
            bool c = false;
            for (int i = 0, j = r.Length - 1; i < r.Length; j = i++)
                if ((r[i].y > z) != (r[j].y > z) && x < (r[j].x - r[i].x) * (z - r[i].y) / (r[j].y - r[i].y) + r[i].x) c = !c;
            return c;
        }
        public static Rect Bounds(Vector2[] r)
        {
            Vector2 lo = r[0], hi = r[0]; foreach (var p in r) { lo = Vector2.Min(lo, p); hi = Vector2.Max(hi, p); }
            return Rect.MinMaxRect(lo.x, lo.y, hi.x, hi.y);
        }
        /// <summary>Signed area (positive counter-clockwise), m².</summary>
        public static float SignedArea(Vector2[] r)
        {
            double a = 0; for (int i = 0, j = r.Length - 1; i < r.Length; j = i++) a += (double)r[j].x * r[i].y - (double)r[i].x * r[j].y;
            return (float)(a * 0.5);
        }
        /// <summary>Area centroid; for a ring whose centroid falls outside (a crescent), the middle of the widest horizontal chord through it.</summary>
        public static Vector2 Centre(Vector2[] r)
        {
            double a = 0, cx = 0, cz = 0;
            for (int i = 0, j = r.Length - 1; i < r.Length; j = i++)
            {
                double f = (double)r[j].x * r[i].y - (double)r[i].x * r[j].y; a += f; cx += (r[j].x + r[i].x) * f; cz += (r[j].y + r[i].y) * f;
            }
            if (System.Math.Abs(a) < 1e-6) return r[0];
            var c = new Vector2((float)(cx / (3 * a)), (float)(cz / (3 * a)));
            if (Inside(r, c.x, c.y)) return c;
            // the chord of the ring at the centroid's z: its longest inside piece
            var xs = new List<float>();
            for (int i = 0, j = r.Length - 1; i < r.Length; j = i++)
                if ((r[i].y > c.y) != (r[j].y > c.y)) xs.Add((r[j].x - r[i].x) * (c.y - r[i].y) / (r[j].y - r[i].y) + r[i].x);
            xs.Sort(); float best = -1f; var m = c;
            for (int k = 0; k + 1 < xs.Count; k += 2) if (xs[k + 1] - xs[k] > best) { best = xs[k + 1] - xs[k]; m = new Vector2((xs[k] + xs[k + 1]) * 0.5f, c.y); }
            return m;
        }
        public static float DistToSeg(Vector2 p, Vector2 a, Vector2 b)
        {
            Vector2 ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-6f)); return (p - (a + ab * t)).magnitude;
        }

        /// <summary>Triangles of a simple polygon (ear clipping; indices into r). A ring that will not clip (self-crossing) falls back to a fan.</summary>
        public static List<int> Triangulate(Vector2[] r)
        {
            var tri = new List<int>(); int n = r.Length; if (n < 3) return tri;
            var idx = new List<int>(n); bool ccw = SignedArea(r) > 0f;
            for (int i = 0; i < n; i++) idx.Add(ccw ? i : n - 1 - i);
            int guard = 0;
            while (idx.Count > 3 && guard++ < n * n)
            {
                bool cut = false;
                for (int k = 0; k < idx.Count; k++)
                {
                    int i0 = idx[(k + idx.Count - 1) % idx.Count], i1 = idx[k], i2 = idx[(k + 1) % idx.Count];
                    Vector2 a = r[i0], b = r[i1], c = r[i2];
                    if ((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) <= 1e-6f) continue;      // reflex corner
                    bool ear = true;
                    foreach (int q in idx) { if (q == i0 || q == i1 || q == i2) continue; if (InTri(r[q], a, b, c)) { ear = false; break; } }
                    if (!ear) continue;
                    tri.Add(i0); tri.Add(i1); tri.Add(i2); idx.RemoveAt(k); cut = true; break;
                }
                if (!cut) break;
            }
            if (idx.Count == 3) { tri.Add(idx[0]); tri.Add(idx[1]); tri.Add(idx[2]); }
            else if (idx.Count > 3) for (int k = 1; k + 1 < idx.Count; k++) { tri.Add(idx[0]); tri.Add(idx[k]); tri.Add(idx[k + 1]); }
            return tri;
        }
        static bool InTri(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
        {
            float d1 = (p.x - b.x) * (a.y - b.y) - (a.x - b.x) * (p.y - b.y), d2 = (p.x - c.x) * (b.y - c.y) - (b.x - c.x) * (p.y - c.y), d3 = (p.x - a.x) * (c.y - a.y) - (c.x - a.x) * (p.y - a.y);
            bool neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0; return !(neg && pos);
        }

        /// <summary>Text of Resources/Landmarks/name (null when the file is not there: the reader keeps today's behaviour).</summary>
        public static string Load(string name)
        {
            var ta = Resources.Load<TextAsset>("Landmarks/" + name);
            return ta != null && ta.text.Length > 2 ? ta.text : null;
        }
    }
}
