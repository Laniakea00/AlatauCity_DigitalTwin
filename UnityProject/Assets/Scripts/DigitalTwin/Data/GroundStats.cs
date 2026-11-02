using System;
using System.Collections.Generic;
using Unity.Collections;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>Figures of the redrawn map's own ground for the panels: Resources/Map/map_ground*.bytes (GRD1, CONTRACT §8; the file
    /// GroundTypes draws), read once when first asked. Its triangles cover exactly the area the plan redrew (every lot, street and keep
    /// piece of the merged districts). The area by district is the area piece's own triangles (ground.py draws the whole area first, type
    /// 15: run 0 of the first chunk of every 2 km tile), so it equals the spec's and the data's hectares; a 10 m mask of all the pieces
    /// tells what lies inside (CityStats counts the people and workplaces there); and
    /// its park land = ground type 6 (ground.py: park and waterfront lots, park, boulevard and buffer greens) — the parks of the plan's
    /// lots. Without the file every figure is absent (0), never estimated.</summary>
    public static class GroundStats
    {
        public const int ParkType = 6, AreaType = 15;
        const float Q = 1f / 32f, Cell = 10f;
        const int MaxCells = 1 << 21;           // a mask of at most 2 M cells (256 kB): a bigger map takes coarser cells
        static float[] parkM2, areaM2;          // by district 0..3, [4] outside every district
        class Mask { public float X0, Z0, Cell; public int Nx, Nz; public int[] Bits; }
        static readonly List<Mask> masks = new List<Mask>();
        static readonly HashSet<long> tiles = new HashSet<long>();      // chunk origins met so far: a tile's first chunk opens with the area piece
        static bool loaded;

        /// <summary>True when the map has a redrawn area at all.</summary>
        public static bool HasPlan { get { Load(); return masks.Count > 0; } }
        /// <summary>The area the plan redrew in district d (−1 = all), hectares; 0 when the map has none there.</summary>
        public static float PlanHa(int d) { Load(); return Sum(areaM2, d) / 10000f; }
        /// <summary>Park land of the plan's lots in district d (−1 = all), hectares; 0 when the map has none there.</summary>
        public static float ParkHa(int d) { Load(); return Sum(parkM2, d) / 10000f; }
        /// <summary>Whether a point lies in the redrawn area (by the cells whose centre the map's triangles cover).</summary>
        public static bool InPlan(float x, float z)
        {
            Load();
            for (int k = 0; k < masks.Count; k++)
            {
                var m = masks[k];
                int i = Mathf.FloorToInt((x - m.X0) / m.Cell), j = Mathf.FloorToInt((z - m.Z0) / m.Cell);
                if (i < 0 || j < 0 || i >= m.Nx || j >= m.Nz) continue;
                int c = j * m.Nx + i; if ((m.Bits[c >> 5] & (1 << (c & 31))) != 0) return true;
            }
            return false;
        }
        static float Sum(float[] a, int d) { if (a == null) return 0f; float v = 0f; for (int k = 0; k < 4; k++) if (d < 0 || k == d) v += a[k]; return v; }

        static void Load()
        {
            if (loaded) return; loaded = true; parkM2 = new float[5]; areaM2 = new float[5];
            int tris = 0, cells = 0; float cell = Cell;
            for (int part = 0; part < 64; part++)
            {
                var ta = Resources.Load<TextAsset>(part == 0 ? "Map/map_ground" : "Map/map_ground_" + part); if (ta == null) break;
                var m = new Mask();
                tris += Read(ta.GetData<byte>(), part, m);          // the asset's own bytes: no managed copy of a part (up to 24 MB)
                Resources.UnloadAsset(ta);
                if (m.Bits == null) break;
                masks.Add(m); cell = m.Cell; for (int i = 0; i < m.Bits.Length; i++) cells += Pop(m.Bits[i]);
            }
            tiles.Clear();
            if (tris > 0) Debug.Log(string.Format("[Alatau] ground figures: {0} triangles; redrawn area (its area piece) Gate {1:0.0} ha, Golden {2:0.0} ha, Growing {3:0.0} ha, Green {4:0.0} ha (mask {5} cells of {6} m); park land Gate {7:0.0} ha, Golden {8:0.0} ha, Growing {9:0.0} ha, Green {10:0.0} ha",
                                                   tris, areaM2[0] / 1e4f, areaM2[1] / 1e4f, areaM2[2] / 1e4f, areaM2[3] / 1e4f, cells, cell,
                                                   parkM2[0] / 1e4f, parkM2[1] / 1e4f, parkM2[2] / 1e4f, parkM2[3] / 1e4f));
        }
        static int Pop(int v) { uint u = (uint)v; int n = 0; while (u != 0) { u &= u - 1; n++; } return n; }
        static int I32(NativeArray<byte> b, int o) => b[o] | b[o + 1] << 8 | b[o + 2] << 16 | b[o + 3] << 24;
        static int U16(NativeArray<byte> b, int o) => b[o] | b[o + 1] << 8;
        static float F32(NativeArray<byte> b, int o) => BitConverter.Int32BitsToSingle(I32(b, o));
        static int Read(NativeArray<byte> b, int part, Mask m)
        {
            if (!b.IsCreated || b.Length < 28 || b[0] != 'G' || b[1] != 'R' || b[2] != 'D' || b[3] != '1') return 0;
            int tris = 0;
            try
            {
                float x0 = F32(b, 8), z0 = F32(b, 12), x1 = F32(b, 16), z1 = F32(b, 20);   // the bounds of the part
                if (!(x1 > x0 && z1 > z0)) return 0;
                m.X0 = x0; m.Z0 = z0; m.Cell = Cell;
                while ((long)(Mathf.CeilToInt((x1 - x0) / m.Cell) + 1) * (Mathf.CeilToInt((z1 - z0) / m.Cell) + 1) > MaxCells) m.Cell *= 2f;
                m.Nx = Mathf.CeilToInt((x1 - x0) / m.Cell) + 1; m.Nz = Mathf.CeilToInt((z1 - z0) / m.Cell) + 1;
                m.Bits = new int[(m.Nx * m.Nz + 31) >> 5];
                int o = 24, n = I32(b, o); o += 4;
                for (int k = 0; k < n; k++)
                {
                    float ox = F32(b, o), oz = F32(b, o + 4);
                    int nv = I32(b, o + 8), ni = I32(b, o + 12), nr = I32(b, o + 16); o += 20;
                    if (nv <= 0 || ni < 0 || nr <= 0 || o + nv * 4 + nr * 8 + ni * 2 > b.Length) break;
                    int vo = o; o += nv * 4;
                    bool opens = tiles.Add(((long)Mathf.RoundToInt(ox) << 32) ^ (uint)Mathf.RoundToInt(oz));   // the tile's first chunk
                    // the run (one piece: a lot, a drive, a green …) and its type for every vertex; a piece's district is found once
                    var run = new int[nv]; var type = new byte[nr]; var dist = new int[nr];
                    for (int r = 0; r < nr; r++)
                    {
                        int first = I32(b, o + r * 8), end = r + 1 < nr ? I32(b, o + (r + 1) * 8) : nv;
                        type[r] = b[o + r * 8 + 4]; dist[r] = -2;
                        for (int i = Mathf.Max(first, 0); i < end && i < nv; i++) run[i] = r;
                    }
                    o += nr * 8;
                    for (int i = 0; i + 2 < ni; i += 3)
                    {
                        int ia = U16(b, o + i * 2), ib = U16(b, o + i * 2 + 2), ic = U16(b, o + i * 2 + 4);
                        if (ia >= nv || ib >= nv || ic >= nv) continue;
                        tris++;
                        float ax = ox + U16(b, vo + ia * 4) * Q, az = oz + U16(b, vo + ia * 4 + 2) * Q;
                        float bx = ox + U16(b, vo + ib * 4) * Q, bz = oz + U16(b, vo + ib * 4 + 2) * Q;
                        float cx = ox + U16(b, vo + ic * 4) * Q, cz = oz + U16(b, vo + ic * 4 + 2) * Q;
                        float a = Mathf.Abs((bx - ax) * (cz - az) - (cx - ax) * (bz - az)) * 0.5f;
                        if (a <= 0f) continue;
                        int r = run[ia];
                        Cover(m, ax, az, bx, bz, cx, cz);                    // the mask: every piece's cells
                        if (opens && r == 0 && type[0] == AreaType)          // the area piece spans districts: each triangle where it lies
                        {
                            int da = CityStats.DistrictAt((ax + bx + cx) / 3f, (az + bz + cz) / 3f);
                            areaM2[da >= 0 && da < 4 ? da : 4] += a;
                            continue;
                        }
                        if (type[r] != ParkType) continue;
                        if (dist[r] == -2) { int dd = CityStats.DistrictAt((ax + bx + cx) / 3f, (az + bz + cz) / 3f); dist[r] = dd >= 0 && dd < 4 ? dd : 4; }
                        parkM2[dist[r]] += a;                                // park pieces never overlap: their sum is the lots' park land
                    }
                    o += ni * 2;
                }
            }
            catch (Exception ex) { Debug.LogWarning("[Alatau] map_ground part " + part + " unreadable for the figures: " + ex.Message); }
            return tris;
        }
        /// <summary>Marks the cells of the mask whose centre lies in the triangle; returns the area of the cells it marked first, m².</summary>
        static float Cover(Mask m, float ax, float az, float bx, float bz, float cx, float cz)
        {
            float cs = m.Cell; int added = 0;
            int i0 = Mathf.Max(0, Mathf.FloorToInt((Mathf.Min(ax, Mathf.Min(bx, cx)) - m.X0) / cs)), i1 = Mathf.Min(m.Nx - 1, Mathf.FloorToInt((Mathf.Max(ax, Mathf.Max(bx, cx)) - m.X0) / cs));
            int j0 = Mathf.Max(0, Mathf.FloorToInt((Mathf.Min(az, Mathf.Min(bz, cz)) - m.Z0) / cs)), j1 = Mathf.Min(m.Nz - 1, Mathf.FloorToInt((Mathf.Max(az, Mathf.Max(bz, cz)) - m.Z0) / cs));
            float s = (bx - ax) * (cz - az) - (cx - ax) * (bz - az);
            for (int j = j0; j <= j1; j++)
                for (int i = i0; i <= i1; i++)
                {
                    float px = m.X0 + (i + 0.5f) * cs, pz = m.Z0 + (j + 0.5f) * cs;
                    float w0 = (bx - ax) * (pz - az) - (px - ax) * (bz - az), w1 = (cx - bx) * (pz - bz) - (px - bx) * (cz - bz), w2 = (ax - cx) * (pz - cz) - (px - cx) * (az - cz);
                    if (!(s > 0f ? w0 >= 0f && w1 >= 0f && w2 >= 0f : w0 <= 0f && w1 <= 0f && w2 <= 0f)) continue;
                    int c = j * m.Nx + i, bit = 1 << (c & 31);
                    if ((m.Bits[c >> 5] & bit) == 0) { m.Bits[c >> 5] |= bit; added++; }
                }
            return added * cs * cs;
        }
    }
}
