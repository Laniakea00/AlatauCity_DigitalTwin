using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>The BIM model of Iconic Complex (QTwinData.Bim) put into the order of its works, so the plaza is built as the 4D
    /// schedule of the monitoring says (IconicMonitor.MakeIconic, Wbs.G*): the whole plot is an earth site from the first day of the
    /// works; the granite is laid section by section from the towers to the entrance (Wbs.GProm), the lawns and the planter follow
    /// (GAllee), the amphitheatre steps, the parasols and their benches rise last (GSquare), the trees are planted at the end (GTrees,
    /// LandmarkModels.Iconic). Before, the page's plaza was one slab of granite under the whole plot and it appeared at once.
    /// Where the plaza met the buildings it is cut: no granite under the towers, the pavilions or the lawns (each has its own floor or
    /// grass), and the amphitheatre of the page, which ran under both pavilion canopies, is drawn in round its stage to stay clear of
    /// the parasols and the colonnades.</summary>
    public static class IconicPlaza
    {
        const byte PlazaPart = 5, TagGranite = 9, TagSteps = 10, TagLawn = 12, TagCanopy = 13, TagPole = 2, TagPave = 5, TagFins = 3;
        /// <summary>Centre of the amphitheatre's rings on the page (local x, z) and the share it is drawn in by.</summary>
        public static readonly Vector2 AmphCentre = new Vector2(0f, -45f);
        public const float AmphScale = 0.6f;
        const float AmphReach = 33f, PlotHW = 133f, PlotHD = 98f, Cell = 8f, GroundY = 0.06f;

        /// <summary>Adds the model to the kit: what is not on the plaza as it is (staged with its building), the plaza in its order.</summary>
        public static void Add(LandmarkKit k, QTwinData.QMesh m)
        {
            int nt = m.I.Length / 3; var P = m.P;
            // the parasols of the plaza: square canopies 2.6 m wide on a pole, with a stone bench at its foot
            var shades = new List<Rect>();
            for (int t = 0; t < nt; t++)
            {
                int a = m.I[t * 3]; if (m.Part[a] != PlazaPart || m.Tag[a] != TagCanopy) continue;
                var r = Bounds(P, m.I, t); int hit = -1;
                for (int s = 0; s < shades.Count && hit < 0; s++) if (shades[s].Overlaps(new Rect(r.x - 0.5f, r.y - 0.5f, r.width + 1f, r.height + 1f))) hit = s;
                if (hit < 0) shades.Add(r); else { var q = shades[hit]; shades[hit] = Rect.MinMaxRect(Mathf.Min(q.xMin, r.xMin), Mathf.Min(q.yMin, r.yMin), Mathf.Max(q.xMax, r.xMax), Mathf.Max(q.yMax, r.yMax)); }
            }
            bool UnderShade(Vector3 p) { foreach (var s in shades) if (Mathf.Abs(p.x - s.center.x) <= 1.35f && Mathf.Abs(p.z - s.center.y) <= 1.35f) return true; return false; }

            // 0 as it is · 1 the granite slab of the page (replaced) · 2 the amphitheatre · 3 a parasol and its bench · 4 a lawn ·
            // 5 the rest of the garden (the round planter) · 6 the floor of a pavilion
            var cls = new byte[nt];
            Vector2 t1Lo = Vector2.one * 1e6f, t1Hi = -t1Lo, t2Lo = t1Lo, t2Hi = t1Hi;
            for (int t = 0; t < nt; t++)
            {
                int a = m.I[t * 3], b = m.I[t * 3 + 1], c = m.I[t * 3 + 2]; byte part = m.Part[a], tag = m.Tag[a];
                Vector3 pa = P[a], pb = P[b], pc = P[c], ce = (pa + pb + pc) / 3f;
                float y0 = Mathf.Min(pa.y, Mathf.Min(pb.y, pc.y)), y1 = Mathf.Max(pa.y, Mathf.Max(pb.y, pc.y));
                bool floor = y1 - y0 < 0.01f && y1 < 0.2f && m.N[a].y > 0.9f;
                if (part == PlazaPart)
                {
                    if (tag == TagGranite) cls[t] = 1;
                    else if (tag == TagLawn && floor) cls[t] = 4;
                    else if ((tag == TagCanopy || tag == TagPole || tag == TagSteps) && UnderShade(pa) && UnderShade(pb) && UnderShade(pc)) cls[t] = 3;
                    else if (tag == TagSteps && (new Vector2(ce.x, ce.z) - AmphCentre).magnitude < AmphReach && ce.z > AmphCentre.y - 15f) cls[t] = 2;
                    else cls[t] = 5;
                }
                else if ((part == 3 || part == 4) && tag == TagPave && floor) cls[t] = 6;
                // the footprints of the towers: where their walls stand on the ground (T2's golden fins stand in front of it, on the plaza)
                if ((part == 1 || part == 2) && tag != TagFins)
                    foreach (var p in new[] { pa, pb, pc })
                    {
                        if (p.y > 0.05f) continue;
                        if (part == 1) { t1Lo = Vector2.Min(t1Lo, new Vector2(p.x, p.z)); t1Hi = Vector2.Max(t1Hi, new Vector2(p.x, p.z)); }
                        else { t2Lo = Vector2.Min(t2Lo, new Vector2(p.x, p.z)); t2Hi = Vector2.Max(t2Hi, new Vector2(p.x, p.z)); }
                    }
            }

            var white = new Color32(255, 255, 255, 255);
            lastMesh = m; lastCls = cls;                    // Trees fits the plaza's trees to the model as drawn
            Emit(k, m, cls, 0, Vector4.zero, false);
            Emit(k, m, cls, 2, Win(Wbs.GSquare, 0f, 3.8f), true);
            Emit(k, m, cls, 3, Win(Wbs.GSquare, 0f, 2.6f), false);
            Emit(k, m, cls, 4, Ground(Wbs.GAllee), false);
            Emit(k, m, cls, 5, Win(Wbs.GAllee, 0f, 0.6f), false);
            Emit(k, m, cls, 6, Ground(new Vector2(0.02f, 0.98f)), false);

            // what the granite must not run under: the floors of the pavilions, the lawns, the towers
            var cuts = new List<Vector2[]>();
            for (int t = 0; t < nt; t++)
                if (cls[t] == 4 || cls[t] == 6) cuts.Add(Ccw(new[] { XZ(P[m.I[t * 3]]), XZ(P[m.I[t * 3 + 1]]), XZ(P[m.I[t * 3 + 2]]) }));
            var towers = new List<(int part, Vector2 lo, Vector2 hi)>();
            if (t1Hi.x > t1Lo.x) towers.Add((1, t1Lo, t1Hi));
            if (t2Hi.x > t2Lo.x) towers.Add((2, t2Lo, t2Hi));
            foreach (var tw in towers) cuts.Add(Box(tw.lo, tw.hi));

            // the granite in sections of 8 m, cut round all that; each section is laid in its own window of the paving, from the
            // towers at the back to the entrance at the front, a little out of line as crews work
            k.Part = PlazaPart; var up = Vector3.up; var uv = new Vector2(0f, GroundY);
            var pieces = new List<List<Vector2>>(); var next = new List<List<Vector2>>();
            for (float z0 = -PlotHD; z0 < PlotHD - 0.01f; z0 += Cell)
                for (float x0 = -PlotHW; x0 < PlotHW - 0.01f; x0 += Cell)
                {
                    float x1 = Mathf.Min(x0 + Cell, PlotHW), z1 = Mathf.Min(z0 + Cell, PlotHD);
                    pieces.Clear(); pieces.Add(new List<Vector2> { new Vector2(x0, z0), new Vector2(x1, z0), new Vector2(x1, z1), new Vector2(x0, z1) });
                    foreach (var cut in cuts)
                    {
                        if (!Touches(cut, x0, z0, x1, z1)) continue;
                        next.Clear(); foreach (var pc in pieces) Subtract(pc, cut, next);
                        pieces.Clear(); pieces.AddRange(next);
                        if (pieces.Count == 0) break;
                    }
                    if (pieces.Count == 0) continue;
                    float xc = (x0 + x1) * 0.5f, zc = (z0 + z1) * 0.5f, jit = Mathf.Repeat(Mathf.Sin(xc * 12.9898f + zc * 78.233f) * 43758.5453f, 1f);
                    float s = Mathf.Clamp01((60f - zc) / 158f + (jit - 0.5f) * 0.16f), a = Wbs.GProm.x + (Wbs.GProm.y - Wbs.GProm.x - 0.10f) * s;
                    k.Window = new Vector4(a, a + 0.10f, 1f, 0f);
                    foreach (var pc in pieces)
                        for (int i = 1; i + 1 < pc.Count; i++)
                            k.Tri(V3(pc[0]), V3(pc[i]), V3(pc[i + 1]), up, white, LM.QTwin, TagGranite, uv, uv, uv);
                }
            // under each tower its foundation, an earth pit while it rises (seen through the open frame), finished with the building
            foreach (var tw in towers)
            {
                k.Part = tw.part; k.Window = new Vector4(0.02f, 1f, 1f, 0f);
                Vector3 a = new Vector3(tw.lo.x, GroundY, tw.lo.y), b = new Vector3(tw.hi.x, GroundY, tw.lo.y), c = new Vector3(tw.hi.x, GroundY, tw.hi.y), d = new Vector3(tw.lo.x, GroundY, tw.hi.y);
                k.Quad(a, b, c, d, up, white, LM.QTwin, TagGranite, uv, uv, uv, uv);
            }
            k.Part = 0; k.NoWin();
        }

        // ------------------------------------------------------------------ the trees of the plaza, fitted to the model
        // The page's trees (QTwinData.Gate().Trees on the plot) were placed on its own drawing: along the low edges of both pavilions
        // their crowns ran into the sloped roofs and the retaining wall under them, and beside T2 into its terraces; on the stone they
        // stood without a pit. Each tree is now checked against the model as it is drawn (the amphitheatre drawn in, the plaza's granite
        // at its own level): its trunk (0.45 m round it) and its crown (the film tree's: an ellipsoid CrownK · h wide, 0.40 h high round
        // 0.64 h, with Margin; LandmarkKit.Tree) must stay clear of every surface. The trunk stands exactly where the page puts it (the
        // kit's half-metre jitter is taken back: a row on the plaza is planted on its line, a tree in a terrace's opening in the middle
        // of it). If it does not fit, it is lowered (down to MinTree), else moved a few metres along the same floor, else left out; on
        // stone or paving it stands in a steel grate over a pit of soil (on lawns and planted terraces in the ground).
        const float CrownK = 0.48f, CrownH = 0.40f, CrownC = 0.64f, Margin = 0.3f, Trunk = 0.45f, MinTree = 4.5f, GCell = 4f, GX0 = -144f, GZ0 = -108f;
        const byte TagPlanted = 6;
        static QTwinData.QMesh lastMesh; static byte[] lastCls;
        static Vector3[] ta, tb, tc; static float[] ty0, ty1; static bool[] twall; static byte[] ttag; static int[] cellStart, cellTris, stamp; static int query, gw, gh;
        static readonly Color32 GrateSteel = LM.C("#4d535a"), PitSoil = LM.C("#3d362d");

        /// <summary>Plants the plaza's trees (local x, base y, z, size w; height 10.5 w) on the plot, each fitted to the model; the kit's
        /// Part and Window are the caller's (the plaza, planted last). Logs what was kept, lowered, moved and left out.</summary>
        public static void Trees(LandmarkKit k, Vector4[] trees, Color32 leafA, Color32 leafB)
        {
            if (lastMesh == null || lastCls == null) return;
            IndexModel(lastMesh, lastCls);
            int kept = 0, lowered = 0, moved = 0, dropped = 0, grates = 0, all = 0; float minH = float.MaxValue;
            var placed = new List<Vector2>();
            var dirs = new Vector2[12]; for (int a = 0; a < 12; a++) dirs[a] = new Vector2(Mathf.Cos(a * Mathf.PI / 6f), Mathf.Sin(a * Mathf.PI / 6f));
            for (int i = 0; i < trees.Length; i++)
            {
                var t = trees[i]; if (Mathf.Abs(t.x) >= 136f || Mathf.Abs(t.z) >= 100f) continue;
                all++;
                float seed = i * 0.37f, h0 = 10.5f * t.w; var jit = LandmarkKit.TreeJitter(seed);
                var p = new Vector3(t.x, t.y, t.z);
                bool onFloor = FloorAt(p.x, p.z, p.y, out float fy, out byte ftag);
                float h = Fit(p, h0);
                if (h < 0f)
                {
                    // move it along the same floor (or onto a lawn or a planted bed), the nearest spot that takes it first
                    bool done = false;
                    for (float r = 1.5f; r <= 6.01f && !done; r += 1.5f)
                        for (int a = 0; a < 12 && !done; a++)
                        {
                            var q = p + new Vector3(dirs[a].x * r, 0f, dirs[a].y * r);
                            if (Mathf.Abs(q.x) > PlotHW - 2f || Mathf.Abs(q.z) > PlotHD - 2f) continue;
                            if (!FloorAt(q.x, q.z, p.y, out float qy, out byte qtag) || !(qtag == ftag || qtag == TagLawn || qtag == TagPlanted) || !onFloor) continue;
                            bool near = false; foreach (var o in placed) if ((o - new Vector2(q.x, q.z)).sqrMagnitude < 9f) { near = true; break; }
                            if (near) continue;
                            q.y = ftag == TagGranite && qtag == TagGranite ? p.y : qy;
                            float hq = Fit(q, h0); if (hq < 0f) continue;
                            p = q; h = hq; fy = qy; ftag = qtag; done = true;
                        }
                    if (!done) { dropped++; continue; }
                    moved++;
                }
                else if (h < h0 - 0.01f) lowered++; else kept++;
                minH = Mathf.Min(minH, h); placed.Add(new Vector2(p.x, p.z));
                k.Tree(p - jit, h, (i & 1) == 0 ? leafA : leafB, seed);
                if (onFloor && ftag != TagLawn && ftag != TagPlanted)
                {
                    // a steel grate 1.8 m square over a pit of dark soil, flush with the stone (the plaza's granite is laid at GroundY)
                    float g = Mathf.Max(fy, ftag == TagGranite ? GroundY : fy);
                    k.Box(new Vector3(p.x, g + 0.015f, p.z), new Vector3(1.8f, 0.05f, 1.8f), 0f, GrateSteel, LM.Solid, 1f, GrateSteel, LM.Paving);
                    k.Box(new Vector3(p.x, g + 0.025f, p.z), new Vector3(1.3f, 0.05f, 1.3f), 0f, PitSoil, LM.Solid, 1f, PitSoil, LM.Paving);
                    grates++;
                }
            }
            Debug.Log(string.Format("[Alatau] Iconic plaza trees: {0} on the plot — {1} as on the page, {2} lowered (lowest {3:0.0} m), {4} moved up to 6 m, {5} left out (no room for a crown); {6} in grates on stone or paving",
                                    all, kept, lowered, minH < float.MaxValue ? minH : 0f, moved, dropped, grates));
            ta = tb = tc = null; ty0 = ty1 = null; twall = null; ttag = null; cellStart = cellTris = stamp = null;    // the index is not kept
        }

        /// <summary>The tallest height (≤ h0, ≥ MinTree or h0 if smaller, in 0.5 m steps) a tree at p can have clear of the model; −1 = none.</summary>
        static float Fit(Vector3 p, float h0)
        {
            for (float h = h0; h >= Mathf.Min(MinTree, h0) - 0.01f; h -= 0.5f) if (Clear(p, h)) return h;
            return -1f;
        }
        /// <summary>Is a tree of height h at p clear of the model: nothing within Trunk of its trunk between 0.3 m over its foot and its top,
        /// nothing inside its crown's ellipsoid (CrownK · h + Margin across, CrownH · h + Margin high, centred CrownC · h up)?</summary>
        static bool Clear(Vector3 p, float h)
        {
            float rx = CrownK * h + Margin, ry = CrownH * h + Margin, cy = p.y + CrownC * h, top = p.y + h, foot = p.y + 0.3f;
            int i0 = Mathf.Max(0, (int)((p.x - rx - GX0) / GCell)), i1 = Mathf.Min(gw - 1, (int)((p.x + rx - GX0) / GCell));
            int j0 = Mathf.Max(0, (int)((p.z - rx - GZ0) / GCell)), j1 = Mathf.Min(gh - 1, (int)((p.z + rx - GZ0) / GCell));
            if (i1 < i0 || j1 < j0) return true;
            query++;
            bool Hit(float d, float y0, float y1)
            {
                if (d < Trunk && y1 > foot && y0 < top) return true;
                float yy = Mathf.Clamp(cy, y0, y1), u = d / rx, w = (yy - cy) / ry; return u * u + w * w < 1f;
            }
            for (int j = j0; j <= j1; j++)
                for (int i = i0; i <= i1; i++)
                {
                    int c = j * gw + i;
                    for (int e = cellStart[c]; e < cellStart[c + 1]; e++)
                    {
                        int t = cellTris[e]; if (stamp[t] == query) continue; stamp[t] = query;
                        if (ty1[t] <= foot || ty0[t] >= cy + ry) continue;               // wholly under the foot or over the crown
                        if (twall[t])
                        {
                            // a wall: how near its foot line comes to the trunk; it stands through its whole height there
                            float d = Mathf.Min(SegDist(p, ta[t], tb[t]), Mathf.Min(SegDist(p, tb[t], tc[t]), SegDist(p, tc[t], ta[t])));
                            if (d < rx && Hit(d, ty0[t], ty1[t])) return false;
                            continue;
                        }
                        // a floor, roof or slope: sampled every metre where it lies within reach
                        Vector3 a = ta[t], b = tb[t], cc = tc[t];
                        float x0 = Mathf.Max(Mathf.Min(a.x, Mathf.Min(b.x, cc.x)), p.x - rx), x1 = Mathf.Min(Mathf.Max(a.x, Mathf.Max(b.x, cc.x)), p.x + rx);
                        float z0 = Mathf.Max(Mathf.Min(a.z, Mathf.Min(b.z, cc.z)), p.z - rx), z1 = Mathf.Min(Mathf.Max(a.z, Mathf.Max(b.z, cc.z)), p.z + rx);
                        if (x1 < x0 || z1 < z0) continue;
                        float det = (b.z - cc.z) * (a.x - cc.x) + (cc.x - b.x) * (a.z - cc.z); if (Mathf.Abs(det) < 1e-6f) continue;
                        for (float sz = Mathf.Floor(z0) + 0.5f; sz <= z1 + 0.5f; sz += 1f)
                            for (float sx = Mathf.Floor(x0) + 0.5f; sx <= x1 + 0.5f; sx += 1f)
                            {
                                float qx = Mathf.Clamp(sx, x0, x1), qz = Mathf.Clamp(sz, z0, z1);
                                float l1 = ((b.z - cc.z) * (qx - cc.x) + (cc.x - b.x) * (qz - cc.z)) / det, l2 = ((cc.z - a.z) * (qx - cc.x) + (a.x - cc.x) * (qz - cc.z)) / det, l3 = 1f - l1 - l2;
                                if (l1 < -1e-4f || l2 < -1e-4f || l3 < -1e-4f) continue;
                                float yy = l1 * a.y + l2 * b.y + l3 * cc.y, dx = qx - p.x, dz = qz - p.z;
                                if (yy > foot && Hit(Mathf.Sqrt(dx * dx + dz * dz), yy, yy)) return false;
                            }
                    }
                }
            return true;
        }
        /// <summary>The floor under (x, z) at about level y (within 0.3 m): the stone slab of the page lies under everything, so any other
        /// floor there (a lawn, a planted bed, a terrace, a pavilion's floor) wins over it.</summary>
        static bool FloorAt(float x, float z, float y, out float fy, out byte tag)
        {
            fy = y; tag = 0; float bo = float.MaxValue, bs = float.MaxValue, yo = y, ys = y; byte to = 0;
            int i = (int)((x - GX0) / GCell), j = (int)((z - GZ0) / GCell); if (x < GX0 || z < GZ0 || i >= gw || j >= gh) return false;
            int c = j * gw + i;
            for (int e = cellStart[c]; e < cellStart[c + 1]; e++)
            {
                int t = cellTris[e]; if (twall[t] || ty1[t] < y - 0.3f || ty0[t] > y + 0.3f) continue;
                Vector3 a = ta[t], b = tb[t], cc = tc[t];
                float det = (b.z - cc.z) * (a.x - cc.x) + (cc.x - b.x) * (a.z - cc.z); if (Mathf.Abs(det) < 1e-6f) continue;
                float l1 = ((b.z - cc.z) * (x - cc.x) + (cc.x - b.x) * (z - cc.z)) / det, l2 = ((cc.z - a.z) * (x - cc.x) + (a.x - cc.x) * (z - cc.z)) / det, l3 = 1f - l1 - l2;
                if (l1 < -1e-4f || l2 < -1e-4f || l3 < -1e-4f) continue;
                float yy = l1 * a.y + l2 * b.y + l3 * cc.y, d = Mathf.Abs(yy - y); if (d > 0.3f) continue;
                if (ttag[t] == TagGranite) { if (d < bs) { bs = d; ys = yy; } }
                else if (d < bo) { bo = d; yo = yy; to = ttag[t]; }
            }
            if (bo < float.MaxValue) { fy = yo; tag = to; return true; }
            if (bs < float.MaxValue) { fy = ys; tag = TagGranite; return true; }
            return false;
        }
        static float SegDist(Vector3 p, Vector3 a, Vector3 b)
        {
            float ex = b.x - a.x, ez = b.z - a.z, L = ex * ex + ez * ez;
            float u = L > 1e-8f ? Mathf.Clamp01(((p.x - a.x) * ex + (p.z - a.z) * ez) / L) : 0f;
            float dx = a.x + ex * u - p.x, dz = a.z + ez * u - p.z; return Mathf.Sqrt(dx * dx + dz * dz);
        }
        /// <summary>The model's triangles as drawn (the amphitheatre drawn in round its stage) in 4 m cells of the plot.</summary>
        static void IndexModel(QTwinData.QMesh m, byte[] cls)
        {
            int nt = m.I.Length / 3; ta = new Vector3[nt]; tb = new Vector3[nt]; tc = new Vector3[nt]; ty0 = new float[nt]; ty1 = new float[nt]; twall = new bool[nt]; ttag = new byte[nt]; stamp = new int[nt]; query = 0;
            gw = Mathf.CeilToInt(-2f * GX0 / GCell); gh = Mathf.CeilToInt(-2f * GZ0 / GCell);
            var count = new int[gw * gh + 1];
            for (int pass = 0; pass < 2; pass++)
            {
                var fill = pass == 1 ? new int[gw * gh] : null;
                for (int t = 0; t < nt; t++)
                {
                    if (pass == 0)
                    {
                        Vector3 a = m.P[m.I[t * 3]], b = m.P[m.I[t * 3 + 1]], c = m.P[m.I[t * 3 + 2]];
                        if (cls[t] == 2) { a = Amph(a); b = Amph(b); c = Amph(c); }
                        ta[t] = a; tb[t] = b; tc[t] = c; ttag[t] = m.Tag[m.I[t * 3]];
                        ty0[t] = Mathf.Min(a.y, Mathf.Min(b.y, c.y)); ty1[t] = Mathf.Max(a.y, Mathf.Max(b.y, c.y));
                        var n = Vector3.Cross(b - a, c - a); float nl = n.magnitude;
                        twall[t] = nl < 1e-6f || Mathf.Abs(n.y) < 0.25f * nl;
                    }
                    int i0 = Mathf.Max(0, (int)((Mathf.Min(ta[t].x, Mathf.Min(tb[t].x, tc[t].x)) - GX0) / GCell)), i1 = Mathf.Min(gw - 1, (int)((Mathf.Max(ta[t].x, Mathf.Max(tb[t].x, tc[t].x)) - GX0) / GCell));
                    int j0 = Mathf.Max(0, (int)((Mathf.Min(ta[t].z, Mathf.Min(tb[t].z, tc[t].z)) - GZ0) / GCell)), j1 = Mathf.Min(gh - 1, (int)((Mathf.Max(ta[t].z, Mathf.Max(tb[t].z, tc[t].z)) - GZ0) / GCell));
                    for (int j = j0; j <= j1; j++) for (int i = i0; i <= i1; i++)
                        { int c = j * gw + i; if (pass == 0) count[c + 1]++; else cellTris[cellStart[c] + fill[c]++] = t; }
                }
                if (pass == 0) { for (int c = 0; c < gw * gh; c++) count[c + 1] += count[c]; cellStart = count; cellTris = new int[count[gw * gh]]; }
            }
        }
        static Vector3 Amph(Vector3 q) => new Vector3(AmphCentre.x + (q.x - AmphCentre.x) * AmphScale, q.y, AmphCentre.y + (q.z - AmphCentre.y) * AmphScale);

        /// <summary>A piece rising from y0 to y1 over window w of the plaza's progress (AlatauLandmark AWin).</summary>
        static Vector4 Win(Vector2 w, float y0, float y1) => new Vector4(w.x, w.y, y0, y1);
        /// <summary>A ground piece (y1 &lt; y0): an earth site until the end of window w, then paved or grassed.</summary>
        static Vector4 Ground(Vector2 w) => new Vector4(w.x, w.y, 1f, 0f);

        /// <summary>The triangles of one class as an indexed piece of the kit (the amphitheatre drawn in round its stage).</summary>
        static void Emit(LandmarkKit k, QTwinData.QMesh m, byte[] cls, byte want, Vector4 win, bool amph)
        {
            var map = new int[m.P.Length]; for (int i = 0; i < map.Length; i++) map[i] = -1;
            var p = new List<Vector3>(); var n = new List<Vector3>(); var u = new List<float>(); var tg = new List<byte>(); var pa = new List<byte>(); var tri = new List<int>();
            for (int t = 0; t < cls.Length; t++)
            {
                if (cls[t] != want) continue;
                for (int j = 0; j < 3; j++)
                {
                    int v = m.I[t * 3 + j];
                    if (map[v] < 0)
                    {
                        map[v] = p.Count; var q = m.P[v]; float uu = m.U[v];
                        if (amph) { q = new Vector3(AmphCentre.x + (q.x - AmphCentre.x) * AmphScale, q.y, AmphCentre.y + (q.z - AmphCentre.y) * AmphScale); uu *= AmphScale; }
                        p.Add(q); n.Add(m.N[v]); u.Add(uu); tg.Add(m.Tag[v]); pa.Add(m.Part[v]);
                    }
                    tri.Add(map[v]);
                }
            }
            if (tri.Count == 0) return;
            k.Window = win;
            k.Indexed(p.ToArray(), n.ToArray(), u.ToArray(), tg.ToArray(), pa.ToArray(), tri.ToArray(), LM.QTwin, new Color32(255, 255, 255, 255));
            k.NoWin();
        }

        // ------------------------------------------------------------------ plan geometry (x, z of the landmark's frame)
        static Vector2 XZ(Vector3 p) => new Vector2(p.x, p.z);
        static Vector3 V3(Vector2 p) => new Vector3(p.x, GroundY, p.y);
        static Rect Bounds(Vector3[] P, int[] I, int t)
        {
            Vector3 a = P[I[t * 3]], b = P[I[t * 3 + 1]], c = P[I[t * 3 + 2]];
            return Rect.MinMaxRect(Mathf.Min(a.x, Mathf.Min(b.x, c.x)), Mathf.Min(a.z, Mathf.Min(b.z, c.z)), Mathf.Max(a.x, Mathf.Max(b.x, c.x)), Mathf.Max(a.z, Mathf.Max(b.z, c.z)));
        }
        static Vector2[] Box(Vector2 lo, Vector2 hi) => new[] { lo, new Vector2(hi.x, lo.y), hi, new Vector2(lo.x, hi.y) };
        static float Side(Vector2 a, Vector2 b, Vector2 p) => (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
        static float Area(List<Vector2> q) { float s = 0f; for (int i = 0; i < q.Count; i++) { var a = q[i]; var b = q[(i + 1) % q.Count]; s += a.x * b.y - b.x * a.y; } return s * 0.5f; }
        /// <summary>The polygon counter-clockwise (its inside on the left of every edge).</summary>
        static Vector2[] Ccw(Vector2[] q) { var l = new List<Vector2>(q); if (Area(l) < 0f) System.Array.Reverse(q); return q; }
        static bool Touches(Vector2[] cut, float x0, float z0, float x1, float z1)
        {
            float a = float.MaxValue, b = float.MinValue, c = float.MaxValue, d = float.MinValue;
            foreach (var p in cut) { a = Mathf.Min(a, p.x); b = Mathf.Max(b, p.x); c = Mathf.Min(c, p.y); d = Mathf.Max(d, p.y); }
            return b > x0 && a < x1 && d > z0 && c < z1;
        }
        /// <summary>The part of convex polygon q on the inside (left) or the outside of the line a → b (Sutherland–Hodgman).</summary>
        static List<Vector2> Clip(List<Vector2> q, Vector2 a, Vector2 b, bool inside)
        {
            var r = new List<Vector2>(q.Count + 2);
            for (int i = 0; i < q.Count; i++)
            {
                Vector2 p = q[i], o = q[(i + 1) % q.Count];
                float dp = Side(a, b, p), dq = Side(a, b, o); if (!inside) { dp = -dp; dq = -dq; }
                if (dp >= 0f) r.Add(p);
                if ((dp >= 0f) != (dq >= 0f)) r.Add(p + (o - p) * (dp / (dp - dq)));
            }
            return r;
        }
        /// <summary>Convex polygon q minus convex polygon cut (counter-clockwise): the convex pieces left over are added to 'into'.</summary>
        static void Subtract(List<Vector2> q, Vector2[] cut, List<List<Vector2>> into)
        {
            var rest = q;
            for (int i = 0; i < cut.Length; i++)
            {
                Vector2 a = cut[i], b = cut[(i + 1) % cut.Length];
                var outside = Clip(rest, a, b, false);
                if (outside.Count >= 3 && Area(outside) > 0.01f) into.Add(outside);
                rest = Clip(rest, a, b, true);
                if (rest.Count < 3 || Area(rest) <= 0.01f) return;
            }
            // what is left lies inside the cut: dropped
        }
    }
}
