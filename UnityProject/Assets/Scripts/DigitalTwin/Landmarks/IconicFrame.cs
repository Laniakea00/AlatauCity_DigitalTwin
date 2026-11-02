using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Where Iconic Complex and its Gate District quarter stand, and the rigid move of the quarter (stage 7, approved 31.10.2026).
    /// The place itself is LandmarkCatalog.IconicX / IconicZ / IconicYaw (the Iconic entry of LandmarkData, the one source of truth).
    /// The quarter's data in the landmark's own frame (gate_district.bytes, iconic_bim.bytes, gate_roads.json) follows by itself; data
    /// made in world coordinates for the old place (gate_q1.*) is moved here by Delta at load (Shift); cameras of the
    /// quarter are given relative to Iconic (At) or as old world points that follow the quarter (Follow). Grade levels the ground of the
    /// quarter at its place before anything is draped on the terrain (LandmarkSystem.PrepareGround).</summary>
    public static class IconicFrame
    {
        public const float X = LandmarkCatalog.IconicX, Z = LandmarkCatalog.IconicZ, Yaw = LandmarkCatalog.IconicYaw;
        /// <summary>The move from the place the world-coordinate data files were made for: (−330, −420) m.</summary>
        public const float Dx = LandmarkCatalog.IconicX - LandmarkCatalog.IconicDataX, Dz = LandmarkCatalog.IconicZ - LandmarkCatalog.IconicDataZ;
        public static Vector2 Centre => new Vector2(X, Z);
        public static Vector2 Delta => new Vector2(Dx, Dz);
        public static Vector2 OldCentre => new Vector2(LandmarkCatalog.IconicDataX, LandmarkCatalog.IconicDataZ);
        public static bool Moved => Dx != 0f || Dz != 0f;

        /// <summary>A world point relative to Iconic (world axes, metres east / north of the centre of the complex).</summary>
        public static Vector2 At(float dx, float dz) => new Vector2(X + dx, Z + dz);
        /// <summary>A world point of the quarter's old data (or of an old camera aimed at it) at the quarter's place now.</summary>
        public static Vector2 Shift(Vector2 p) => new Vector2(p.x + Dx, p.y + Dz);
        public static Vector3 Shift(Vector3 p) => new Vector3(p.x + Dx, p.y, p.z + Dz);
        public static void Shift(Vector3[] v) { if (v == null || !Moved) return; for (int i = 0; i < v.Length; i++) { v[i].x += Dx; v[i].z += Dz; } }
        /// <summary>Flat x, z, x, z, … pairs (from index 'from', every 'stride' floats) moved with the quarter.</summary>
        public static void ShiftPairs(float[] a, int from = 0, int stride = 2)
        {
            if (a == null || !Moved || stride < 2) return;
            for (int i = from; i + 1 < a.Length; i += stride) { a[i] += Dx; a[i + 1] += Dz; }
        }
        /// <summary>An old world point (a camera or a mark made for the old place): moved with the quarter when it lies within r metres
        /// of the old centre of the complex, left where it is otherwise (the rest of the city did not move).</summary>
        public static Vector2 Follow(float x, float z, float r = 1600f)
            => (new Vector2(x, z) - OldCentre).sqrMagnitude <= r * r ? new Vector2(x + Dx, z + Dz) : new Vector2(x, z);

        // ------------------------------------------------------------------ the ground of the quarter
        /// <summary>Radius of the quarter's area (its mask in gate_district.bytes; 335 m), metres.</summary>
        public static float AreaR
        {
            get
            {
                if (areaR > 0f) return areaR;
                var d = QTwinData.Gate(); float r = 0f;
                if (d != null && d.Mask != null && d.W > 0)
                {
                    float cell = 2f * d.Half / d.W;
                    for (int iz = 0; iz < d.W; iz++) for (int ix = 0; ix < d.W; ix++)
                        if (d.Mask[iz * d.W + ix] > 127) { float lx = -d.Half + (ix + 0.5f) * cell, lz = -d.Half + (iz + 0.5f) * cell; r = Mathf.Max(r, lx * lx + lz * lz); }
                    r = Mathf.Sqrt(r);
                }
                areaR = r > 50f ? r : 336f; return areaR;
            }
        }
        static float areaR;
        /// <summary>Last grading, for the log and the checks: nodes changed, the level of the plate and its nodes, the deepest cut and
        /// highest fill (m), the nodes moved more than 1.5 m, the steepest step between neighbours after it (m per 50 m), the steepest
        /// 50 m cell inside the area before and after (%).</summary>
        public static int GradedNodes, PlateNodes, OverNodes, PlateOver; public static float PlateLevel = float.NaN, GradeCut, GradeFill, StepMax, SteepBefore, SteepAfter;
        /// <summary>Steepest fall of the graded ground: 3 % = at most 1.5 m between grid nodes 50 m apart (the norm of rule 3 for one step
        /// of earthworks; buildings stand without a plinth up to 5 %).</summary>
        public const float StepSlope = 0.03f;

        /// <summary>Grading of the quarter's ground with the least earthworks: the plate of the complex (every 50 m cell of the terrain grid
        /// that the plot w × d touches) is level at the median of its natural ground; around it every node inside the area moves as little
        /// as it can while no step between neighbours is steeper than StepSlope (1.5 m per 50 m): the ground meets the plate and the
        /// natural terrain at the edge of the area in gentle terraces and slopes, never a cliff. The nodes outside the area keep their
        /// ground (the city's buildings there stand as they are). Solved by relaxation on the nodes of the area (Gauss–Seidel: each node
        /// clamped into the band its neighbours allow, the middle of it where they disagree), then written one grid node at a time through
        /// CityGround.Flatten, before the plot is levelled. Returns the touched grid indices.</summary>
        public static List<int> Grade(float cx, float cz, float yaw, float w, float d)
        {
            var touched = new List<int>(); GradedNodes = PlateNodes = OverNodes = PlateOver = 0; PlateLevel = float.NaN;
            if (!CityGround.GridReady) return touched;
            float S = CityGround.GridStep, X0 = CityGround.GridX0, Z0 = CityGround.GridZ0; int NX = CityGround.GridNX, NY = CityGround.GridNY;
            float R = AreaR;
            // the window: the area and one ring of fixed nodes round it
            int c0 = Mathf.Max(1, Mathf.FloorToInt((cx - R - X0) / S) - 1), c1 = Mathf.Min(NX - 2, Mathf.CeilToInt((cx + R - X0) / S) + 1);
            int r0 = Mathf.Max(1, Mathf.FloorToInt((cz - R - Z0) / S) - 1), r1 = Mathf.Min(NY - 2, Mathf.CeilToInt((cz + R - Z0) / S) + 1);
            int W = c1 - c0 + 1, Hn = r1 - r0 + 1; if (W < 3 || Hn < 3) return touched;
            var T = new float[W * Hn]; var kind = new byte[W * Hn];           // 0 fixed (outside the area), 1 free, 2 plate
            for (int r = 0; r < Hn; r++) for (int c = 0; c < W; c++)
            {
                int k = r * W + c; T[k] = CityGround.RawHeight((r0 + r) * NX + c0 + c);
                float dx = X0 + (c0 + c) * S - cx, dz = Z0 + (r0 + r) * S - cz;
                if (r > 0 && c > 0 && r < Hn - 1 && c < W - 1 && dx * dx + dz * dz < R * R) kind[k] = 1;
            }
            SteepBefore = Steepest(cx, cz, R, c0, c1, r0, r1);
            // the plate: the four nodes of every cell the plot touches
            float a = yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
            var plate = new List<float>();
            for (int r = 0; r < Hn - 1; r++) for (int c = 0; c < W - 1; c++)
            {
                float x0 = X0 + (c0 + c) * S, z0 = Z0 + (r0 + r) * S;
                if (!LandmarkSystem.ObbHitsAabb(cx, cz, ca, sa, w * 0.5f, d * 0.5f, x0, z0, x0 + S, z0 + S)) continue;
                for (int q = 0; q < 4; q++) { int k = (r + (q >> 1)) * W + c + (q & 1); if (kind[k] == 1) { kind[k] = 2; plate.Add(T[k]); } }
            }
            if (plate.Count > 0)
            {
                plate.Sort(); float lvl = plate[plate.Count / 2]; PlateLevel = lvl; PlateNodes = plate.Count;
                for (int k = 0; k < T.Length; k++) if (kind[k] == 2) T[k] = lvl;
            }
            // relaxation: every free node into the band [max(neighbour − step), min(neighbour + step)], as near its own ground as it can
            float st = StepSlope * S, sd = st * 1.41421356f;
            for (int it = 0; it < 400; it++)
            {
                float ch = 0f;
                for (int r = 1; r < Hn - 1; r++) for (int c = 1; c < W - 1; c++)
                {
                    int k = r * W + c; if (kind[k] != 1) continue;
                    float lo = float.MinValue, hi = float.MaxValue;
                    for (int dr = -1; dr <= 1; dr++) for (int dc = -1; dc <= 1; dc++)
                    {
                        if (dr == 0 && dc == 0) continue;
                        float t = T[k + dr * W + dc], m = dr != 0 && dc != 0 ? sd : st;
                        lo = Mathf.Max(lo, t - m); hi = Mathf.Min(hi, t + m);
                    }
                    float v = T[k], nv = lo > hi ? (lo + hi) * 0.5f : Mathf.Clamp(v, lo, hi);
                    ch = Mathf.Max(ch, Mathf.Abs(nv - v)); T[k] = nv;
                }
                if (ch < 0.001f) break;
            }
            // write the nodes that moved; the statistics
            float cut = 0f, fill = 0f, step = 0f;
            for (int r = 1; r < Hn - 1; r++) for (int c = 1; c < W - 1; c++)
            {
                int k = r * W + c; if (kind[k] == 0) continue;
                for (int dr = -1; dr <= 1; dr++) for (int dc = -1; dc <= 1; dc++)
                    if (dr != 0 || dc != 0) step = Mathf.Max(step, Mathf.Abs(T[k] - T[k + dr * W + dc]) / (dr != 0 && dc != 0 ? 1.41421356f : 1f));
                int i = (r0 + r) * NX + c0 + c; float h0 = CityGround.RawHeight(i), dh = T[k] - h0;
                if (Mathf.Abs(dh) > 1.5f) { OverNodes++; if (kind[k] == 2) PlateOver++; }
                if (Mathf.Abs(dh) < 0.01f) continue;
                // a 1 × 1 m site with a 1 m edge on the node itself: Flatten sets exactly this node (its neighbours are 50 m away)
                var tt = CityGround.Flatten(X0 + (c0 + c) * S, Z0 + (r0 + r) * S, 0f, 1f, 1f, T[k], 1f);
                touched.AddRange(tt); GradedNodes += tt.Count;
                cut = Mathf.Min(cut, dh); fill = Mathf.Max(fill, dh);
            }
            GradeCut = cut; GradeFill = fill; StepMax = step; SteepAfter = Steepest(cx, cz, R, c0, c1, r0, r1);
            int area = 0; foreach (var kk in kind) if (kk != 0) area++;
            Debug.Log(string.Format(CultureInfo.InvariantCulture,
                "[Alatau] Iconic quarter at ({0:0}, {1:0}) yaw {2:0}, moved by ({3:0}, {4:0}) from its data place; ground graded inside r {5:0} m: {6} of {7} nodes moved; plate level {8:0.00} m on {9} nodes; terraced to <= {10:0.0} m per 50 m step (steepest step {11:0.00} m): cut {12:0.0} m, fill {13:0.0} m, nodes over 1.5 m {14} ({15} of them under the level plate); steepest cell {16:0.0} % -> {17:0.0} %",
                cx, cz, Yaw, Dx, Dz, R, GradedNodes, area, PlateLevel, PlateNodes, StepSlope * 50f, step * 50f / S, -cut, fill, OverNodes, PlateOver, SteepBefore, SteepAfter));
            return touched;
        }
        static float Steepest(float cx, float cz, float R, int c0, int c1, int r0, int r1)
        {
            float S = CityGround.GridStep, X0 = CityGround.GridX0, Z0 = CityGround.GridZ0; int NX = CityGround.GridNX; float m = 0f;
            for (int r = r0; r < r1; r++) for (int c = c0; c < c1; c++)
            {
                float dx = X0 + (c + 0.5f) * S - cx, dz = Z0 + (r + 0.5f) * S - cz; if (dx * dx + dz * dz > R * R) continue;
                float h00 = CityGround.RawHeight(r * NX + c), h10 = CityGround.RawHeight(r * NX + c + 1), h01 = CityGround.RawHeight((r + 1) * NX + c), h11 = CityGround.RawHeight((r + 1) * NX + c + 1);
                float gx = (h10 + h11 - h00 - h01) / (2f * S), gz = (h01 + h11 - h00 - h10) / (2f * S);
                m = Mathf.Max(m, Mathf.Sqrt(gx * gx + gz * gz) * 100f);
            }
            return m;
        }
        // ------------------------------------------------------------------ cameras for ShotRig (it is never committed; it calls these)
        /// <summary>ShotRig: "invoke AlatauCity.DigitalTwin.Landmarks.IconicFrame View dx,dz,dist,yaw,pitch[,lift]" — the map camera at a
        /// point given relative to Iconic (metres east, north of the complex), as the "view" verb takes it.</summary>
        public static void View(string args) { if (Parse(args, out var v)) Pose(X + v[0], Z + v[1], v); }
        /// <summary>ShotRig: "invoke AlatauCity.DigitalTwin.Landmarks.IconicFrame ViewOld x,z,dist,yaw,pitch[,lift]" — an old fixed camera
        /// (e.g. gate_map "-3170,-19080,1500,30,38"): its point follows the quarter when it lies within 1.6 km of the old centre.</summary>
        public static void ViewOld(string args) { if (Parse(args, out var v)) { var p = Follow(v[0], v[1]); Pose(p.x, p.y, v); } }
        static bool Parse(string s, out float[] v)
        {
            v = null; if (string.IsNullOrEmpty(s)) return false;
            var p = s.Split(','); if (p.Length < 5) { Debug.LogWarning("[Alatau] IconicFrame view: want x,z,dist,yaw,pitch[,lift], got " + s); return false; }
            v = new float[6];
            for (int i = 0; i < p.Length && i < 6; i++) if (!float.TryParse(p[i], NumberStyles.Float, CultureInfo.InvariantCulture, out v[i])) return false;
            return true;
        }
        static void Pose(float x, float z, float[] v)
        {
            var mc = Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null; if (mc == null) return;
            mc.SetPose(new Vector3(x, 0f, z), v[2], v[3], v[4], v[5]);
            Debug.Log(string.Format(CultureInfo.InvariantCulture, "[Alatau] IconicFrame view at ({0:0}, {1:0}) dist {2:0} yaw {3:0} pitch {4:0}", x, z, v[2], v[3], v[4]));
        }
    }
}
