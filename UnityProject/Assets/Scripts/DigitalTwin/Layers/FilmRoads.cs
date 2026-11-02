using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Roads of the film look: the road graph of the twin (TwinData.Roads) drawn as ribbons that lie on the terrain, a wide
    /// pavement ribbon under a carriageway ribbon, so at a junction the carriageways cover the pavements. Width and lanes by road class
    /// (assumed typical cross-sections, not survey). Built once, shown only while the film look is on (FilmLook.Apply / Restore).</summary>
    public class FilmRoads : MonoBehaviour
    {
        GameObject root; bool built;

        /// <summary>Cross-section of a road class: half width of the carriageway, pavement width, lanes per direction, height above the ground.</summary>
        public static void Dims(TwinData.RoadClass c, out float half, out float walk, out int lanes, out float lift)
        {
            switch (c)
            {
                case TwinData.RoadClass.Highway: half = 11f; walk = 0f; lanes = 3; lift = 0.36f; break;
                case TwinData.RoadClass.Ring: half = 9f; walk = 0f; lanes = 2; lift = 0.31f; break;
                case TwinData.RoadClass.Main: half = 7.5f; walk = 3.5f; lanes = 2; lift = 0.26f; break;
                default: half = 4f; walk = 2.4f; lanes = 1; lift = 0.21f; break;
            }
        }

        public void Show(bool on)
        {
            if (on && !built && TwinData.Ready) Build();
            if (root != null && root.activeSelf != on) root.SetActive(on);
        }

        void Build()
        {
            built = true; PublishZones();
            var sh = Shader.Find("AlatauCity/Road"); if (sh == null) { Debug.LogWarning("[Alatau] film roads: shader missing"); return; }
            var mat = new Material(sh) { name = "Film roads" };
            root = new GameObject("Film roads");
            var V = new List<Vector3>(); var U0 = new List<Vector4>(); var U1 = new List<Vector4>(); var U2 = new List<Vector4>(); var U3 = new List<Vector4>(); var T = new List<int>();
            var along = new List<float>(); int meshes = 0; float km = 0;
            void Flush()
            {
                if (V.Count == 0) return;
                var m = new Mesh { name = "Film roads " + meshes, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
                m.SetVertices(V); m.SetUVs(0, U0); m.SetUVs(1, U1); m.SetUVs(2, U2); m.SetUVs(3, U3); m.SetTriangles(T, 0); m.RecalculateNormals(); m.RecalculateBounds();
                var go = new GameObject(m.name); go.transform.SetParent(root.transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = m; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off; mr.receiveShadows = true;
                V.Clear(); U0.Clear(); U1.Clear(); U2.Clear(); U3.Clear(); T.Clear(); meshes++;
            }
            var strokes = Strokes(); drawn = strokes; Lamps.Clear();
            foreach (var q in strokes) EnsureDeck(q);
            BuildSegGrid(strokes);
            var rib = new Vector4[4]; int structQuads = 0, piers = 0, columns = 0, caps = 0, spansBare = 0, nStaged = 0;
            // the junctions first: a crossing is set back from the junction's patch, so its size must be known before the arms are drawn
            foreach (var st in strokes)
            {
                if (st.Ramp || st.P == null || st.P.Count < 2) continue;
                StrokeDims(st, out float h0, out float w0, out _, out float l0); var p0 = st.P;
                // a drive's end on its street (private id) is no junction: no patch, no crossings on the street
                if (!st.Drive || st.A >= 0) Node(st.A, p0[0], (p0[Mathf.Min(1, p0.Count - 1)] - p0[0]).normalized, st.Cls, h0, w0, l0, st.Years, EndY(st, 0), st.Drive);
                if (!st.Drive || st.B >= 0) Node(st.B, p0[p0.Count - 1], (p0[Mathf.Max(p0.Count - 2, 0)] - p0[p0.Count - 1]).normalized, st.Cls, h0, w0, l0, st.Years, EndY(st, p0.Count - 1), st.Drive);
            }
            // T-junctions the plan draws as a street ending on the middle of another road: crossings on the through road on both
            // sides of the side street, and on the side street set back from the through road's kerb
            var mids = MidJunctions(strokes);
            // the meshes are laid tile by tile (MeshTile m): a mesh covers one part of the city, so the view and every shadow cascade
            // cull what is out of sight (in data order each of the 53 meshes of the stage-7 map spanned the whole city and all were drawn
            // in every pass); the strokes keep their indices, only the order they are laid in changes
            long tile = long.MinValue;
            void TileBreak(Vector2 p) { long k = TileKey(p); if (k != tile) { Flush(); tile = k; } }
            var order = new List<int>(strokes.Count); for (int i = 0; i < strokes.Count; i++) order.Add(i);
            order.Sort((a, b) => TileKey(TileAt(strokes[a])).CompareTo(TileKey(TileAt(strokes[b]))));
            foreach (int si in order)
            {
                var st = strokes[si];
                TileBreak(TileAt(st));
                // a reconstruction (StageP): the lamps stand by the widest (last) cross-section in every year; the ribbons and the deck or
                // embankment sides are drawn once per cross-section, each shown from its year until the next one's (Until)
                int nv = st.StageP != null ? st.StageP.Length + 1 : 1;
                if (nv > 1) UseProfile(st, st.StageP[nv - 2]);
                StrokeDims(st, out float half, out float walk, out int lanes, out float lift);
                var pts = st.P; float len = 0; along.Clear(); along.Add(0);
                for (int i = 1; i < pts.Count; i++) { len += (pts[i] - pts[i - 1]).magnitude; along.Add(len); }
                if (len < 0.5f) { if (nv > 1) UseProfile(st, st.Prof0); continue; }
                km += len / 1000f;
                var years = st.Years;
                // street lamps (FilmLamps places the posts, AlatauRoad draws their light on the ground by the same rule) and pedestrian
                // crossings with a stop line on the arms of street junctions
                FilmLamps.Rule(st.Cls, st.Ramp, st.OneWay, out float lampStep, out int lampMode, out int lampCls);
                if (lampMode == 3 && TwinOnRight(strokes, si)) lampMode = 6;     // the other carriageway lies at x < 0: the outer kerb is x > 0
                if (st.Drive) { lampStep = 0f; lampMode = 0; lampCls = 0; }      // a drive: no lamps, no lamp light (they come with the plan)
                float cA = st.Ramp || st.Drive ? 0f : CrossAt(st.A, st.Cls), cB = st.Ramp || st.Drive ? 0f : CrossAt(st.B, st.Cls);
                if (cA + cB + 2f * CrossW(st.Cls) + 16f > len) { cA = 0f; cB = 0f; }
                var u3 = new Vector4(lampStep, lampMode + 8 * lampCls, cA, cB);
                mids.TryGetValue(si, out var ml);
                if (st.NoCars) lampMode = 0;                                   // a pedestrian street or a bike path: lamps come with the plan (level 4)
                if (lampMode > 0) Lamps.Add(new LampRun { P = pts, Along = along.ToArray(), Half = half, Walk = walk, Len = len, Step = lampStep, Mode = lampMode, Cls = lampCls, Years = years, Mids = ml,
                    H = st.Deck != null ? st.H : null, Deck = st.Deck });
                // the crossings in the middle of this road (uv0.zw = along of the junction, set back of its crossings): each segment takes
                // the nearest junction; where that changes, the row of vertices is doubled so the value never blends between two
                Vector2 Mid(int seg)
                {
                    if (ml == null || seg < 1 || seg >= pts.Count) return Vector2.zero;
                    float m = (along[seg - 1] + along[seg]) * 0.5f; Vector2 best = Vector2.zero; float bd = float.MaxValue;
                    foreach (var j in ml) { float dd = Mathf.Abs(j.x - m); if (dd < bd) { bd = dd; best = j; } }
                    return best;
                }
                for (int vi = 0; vi < nv; vi++)
                {
                if (nv > 1) { UseProfile(st, vi == 0 ? st.Prof0 : st.StageP[vi - 1]); StrokeDims(st, out half, out walk, out lanes, out lift); nStaged += vi > 0 ? 1 : 0; }
                var yrsV = nv == 1 ? years : Until(vi == 0 ? years : st.StageY[vi - 1], vi + 1 < nv ? st.StageY[vi] : new Vector4(9999, 9999, 9999, 9999));
                // ribbons (uv1.y code): 0 pavement to the outer edge of the pavements, 1 carriageway; a boulevard (median) has two
                // carriageways either side of a green strip (2); a bike path is one bike-coloured ribbon (4); a pedestrian street is all
                // pavement. Old data: pavement + carriageway exactly as before.
                int nr = 0;
                if (walk > 0f) rib[nr++] = new Vector4(half + walk, 0f, 0f, st.Drive ? 0.10f : 0.12f);
                if (st.NoCars && st.PLanes0 && st.Kind != "bike_path") { if (st.PMedian > 0.5f) rib[nr++] = new Vector4(st.PMedian * 0.5f - 0.2f, 0f, 2f, 0.15f); }   // a boulevard's green strip, no carriageway
                else if (st.PMedian > 0.5f && half > st.PMedian * 0.5f + 1f)
                {
                    float cw = (half - st.PMedian * 0.5f) * 0.5f, co = st.PMedian * 0.5f + cw;
                    rib[nr++] = new Vector4(cw, -co, 1f, lift); rib[nr++] = new Vector4(cw, co, 1f, lift); rib[nr++] = new Vector4(st.PMedian * 0.5f - 0.2f, 0f, 2f, 0.15f);
                }
                else if (half >= 0.3f) rib[nr++] = new Vector4(half, 0f, st.Kind == "bike_path" ? 4f : 1f, lift);
                var dk = st.Deck; var hh = st.H; var tun = TunnelSegs(st, along);
                for (int ri = 0; ri < nr; ri++)
                {
                    float w = rib[ri].x, co = rib[ri].y, code = rib[ri].z, up = rib[ri].w; int prev = -1;
                    bool split = code == 1f && co != 0f;
                    float uvHalf = split ? w : half, uvLanes = split ? -Mathf.Max(1, Mathf.Abs(lanes)) : lanes, uvLen = st.Drive ? 0f : len;
                    int Row(int i, Vector2 jm)
                    {
                        int r0 = V.Count;
                        Vector2 d = (pts[Mathf.Min(i + 1, pts.Count - 1)] - pts[Mathf.Max(i - 1, 0)]).normalized, left = new Vector2(-d.y, d.x);
                        for (int sd = -1; sd <= 1; sd++)
                        {
                            Vector2 p = pts[i] + left * (co + w * sd);
                            float y = CityGround.HeightAt(p.x, p.y) + up; if (dk != null && dk[i] > 0f) y = Mathf.Lerp(y, hh[i] + up, dk[i]);
                            V.Add(new Vector3(p.x, y, p.y)); U0.Add(new Vector4(w * sd, along[i], jm.x, jm.y));
                            U1.Add(new Vector4(uvHalf, code, uvLen, uvLanes)); U2.Add(yrsV); U3.Add(code >= 2f ? Vector4.zero : u3);
                        }
                        return r0;
                    }
                    for (int i = 0; i < pts.Count; i++)
                    {
                        Vector2 jR = Mid(i + 1), jL = i > 0 ? Mid(i) : jR;
                        int b = Row(i, jL);
                        if (prev >= 0 && (tun == null || !tun[i]))
                            for (int k = 0; k < 2; k++) { T.Add(prev + k); T.Add(prev + k + 1); T.Add(b + k); T.Add(prev + k + 1); T.Add(b + k + 1); T.Add(b + k); }      // facing up
                        prev = jR != jL && i < pts.Count - 1 ? Row(i, jR) : b;
                    }
                }
                if (dk != null) Structures(si, st, along, half + walk, walk > 0f ? 0.12f : lift, yrsV);
                }
                if (nv > 1) UseProfile(st, st.Prof0);
                if (V.Count > 180000) Flush();
            }
            // junctions: a round patch of plain asphalt (and of pavement under it) where streets meet, so their ends never show and lines
            // never cross inside a junction. A motorway or ring road that runs straight through keeps its markings (ramps just merge).
            var nodeList = new List<Junction>(nodes.Values); nodeList.Sort((a, b) => TileKey(a.P).CompareTo(TileKey(b.P)));
            foreach (var nd in nodeList)
            {
                if (nd.Deg < 2) continue;
                if (nd.Fast && nd.Through) continue;
                TileBreak(nd.P);
                if (nd.Deg == 2 && nd.Through) continue;
                for (int pass = nd.Walk > 0f ? 0 : 1; pass < 2; pass++)
                {
                    float r = pass == 0 ? nd.Half + nd.Walk : nd.Half * 1.02f, up = pass == 0 ? 0.13f : nd.Lift + 0.025f; int c0 = V.Count; const int N = 20;
                    float PY(Vector2 q) => float.IsNaN(nd.Hy) ? CityGround.HeightAt(q.x, q.y) + up : nd.Hy + up;      // a junction on a deck lies flat at its height
                    V.Add(new Vector3(nd.P.x, PY(nd.P), nd.P.y)); U0.Add(Vector4.zero); U1.Add(new Vector4(nd.Half, pass, 0f, 1f)); U2.Add(nd.Years); U3.Add(new Vector4(0f, 5f, 0f, 0f));
                    for (int i = 0; i < N; i++)
                    {
                        float a = i * Mathf.PI * 2f / N; var p = nd.P + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * r;
                        V.Add(new Vector3(p.x, PY(p), p.y)); U0.Add(new Vector4(r, 0f, 0f, 0f)); U1.Add(new Vector4(nd.Half, pass, 0f, 1f)); U2.Add(nd.Years); U3.Add(new Vector4(0f, 5f, 0f, 0f));
                        T.Add(c0); T.Add(c0 + 1 + (i + 1) % N); T.Add(c0 + 1 + i);
                    }
                }
                if (V.Count > 180000) Flush();
            }
            // turnaround pads at the dead ends of drives (film_roads `pads`): plain asphalt over the drive, under every street; a pad on a
            // plaza (pl 1) is left to the ground's paving, one in a paved court of an apartment or public lot (pl 2) is laid in pavers
            int nPads = 0, nPadPl = 0; var fr = LoadFilm(); padRings.Clear();
            if (fr != null && fr.pads != null)
                foreach (var pd in Sorted(fr.pads, q => q.p))
                {
                    if (pd.p == null || pd.p.Length < 6) continue;
                    TileBreak(new Vector2(pd.p[0], pd.p[1]));
                    var yv = pd.y != null && pd.y.Length >= 4 ? new Vector4(pd.y[0], pd.y[1], pd.y[2], pd.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                    int m = pd.p.Length / 2; Vector2 c = Vector2.zero; for (int i = 0; i < m; i++) c += new Vector2(pd.p[2 * i], pd.p[2 * i + 1]); c /= m;
                    if (pd.pl == 1)
                    {
                        nPads++; nPadPl++; var rp = new Vector2[m]; for (int i = 0; i < m; i++) rp[i] = new Vector2(pd.p[2 * i], pd.p[2 * i + 1]); padRings.Add(rp);
                        continue;
                    }
                    float hr = 0f; for (int i = 0; i < m; i++) hr = Mathf.Max(hr, (new Vector2(pd.p[2 * i], pd.p[2 * i + 1]) - c).magnitude);
                    // pavers: the pavement ribbon of the shader with metres across and along in world axes, its kerb line beyond the pad
                    bool pav = pd.pl == 2; if (pav) nPadPl++;
                    var u1 = pav ? new Vector4(hr + 2f, 0f, 0f, 1f) : new Vector4(hr, 5f, 0f, 1f);       // 5: plain asphalt, as the truck yards
                    int c0 = V.Count; void PadV(Vector2 q) { V.Add(new Vector3(q.x, CityGround.HeightAt(q.x, q.y) + 0.17f, q.y)); U0.Add(pav ? new Vector4(q.x - c.x, q.y - c.y, 0f, 0f) : Vector4.zero); U1.Add(u1); U2.Add(yv); U3.Add(Vector4.zero); }
                    PadV(c); int ring = 0;
                    for (int i = 0; i < m; i++)
                    {
                        Vector2 a = new Vector2(pd.p[2 * i], pd.p[2 * i + 1]), b = new Vector2(pd.p[(2 * i + 2) % (2 * m)], pd.p[(2 * i + 3) % (2 * m)]);
                        int k = Mathf.Clamp(Mathf.CeilToInt((b - a).magnitude / 5f), 1, 16);          // the rim every ≤ 5 m follows the terrain
                        for (int j = 0; j < k; j++) { PadV(Vector2.Lerp(a, b, j / (float)k)); ring++; }
                    }
                    for (int i = 0; i < ring; i++) { T.Add(c0); T.Add(c0 + 1 + (i + 1) % ring); T.Add(c0 + 1 + i); }
                    if (Vector3.Cross(V[c0 + 1] - V[c0], V[c0 + 2] - V[c0]).y > 0f)                      // a clockwise outline: flip to face up
                        for (int t = T.Count - 3 * ring; t < T.Count; t += 3) { int x = T[t + 1]; T[t + 1] = T[t + 2]; T[t + 2] = x; }
                    nPads++; var ring2 = new Vector2[m]; for (int i = 0; i < m; i++) ring2[i] = new Vector2(pd.p[2 * i], pd.p[2 * i + 1]); padRings.Add(ring2);
                    if (V.Count > 180000) Flush();
                }
            // truck yards of the class-A sheds (film_roads `yards`, gen_buildings truck_yard): plain asphalt like a pad (ribbon type 5: one
            // world-space surface, no repairs or wheel tracks), over the drives and pads that end in it, under the streets, laid in rings round
            // the centre every ≤ 5 m so it follows the terrain; yard space for the run counters. Markings only where the data has bays: a
            // yard with its shed's dock side (`d`: x0 z0 x1 z1 doors) gets bay lines square to that wall between the doors, out 18 m (uv0 =
            // metres along the dock side, out from it, door pitch, dock length; the shader draws them)
            int nYards = 0, nBays = 0;
            if (fr != null && fr.yards != null)
                foreach (var yd in Sorted(fr.yards, q => q.p))
                {
                    if (yd.p == null || yd.p.Length < 6) continue;
                    TileBreak(new Vector2(yd.p[0], yd.p[1]));
                    var yv = yd.y != null && yd.y.Length >= 4 ? new Vector4(yd.y[0], yd.y[1], yd.y[2], yd.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                    int m = yd.p.Length / 2; var rim = new List<Vector2>(); Vector2 c = Vector2.zero;
                    for (int i = 0; i < m; i++) c += new Vector2(yd.p[2 * i], yd.p[2 * i + 1]); c /= m;
                    float hr = 0f, area = 0f;
                    for (int i = 0; i < m; i++)
                    {
                        Vector2 a = new Vector2(yd.p[2 * i], yd.p[2 * i + 1]), b = new Vector2(yd.p[(2 * i + 2) % (2 * m)], yd.p[(2 * i + 3) % (2 * m)]);
                        hr = Mathf.Max(hr, (a - c).magnitude); area += (a.y - c.y) * (b.x - c.x) - (a.x - c.x) * (b.y - c.y);
                        int k = Mathf.Clamp(Mathf.CeilToInt((b - a).magnitude / 5f), 1, 64);
                        for (int j = 0; j < k; j++) rim.Add(Vector2.Lerp(a, b, j / (float)k));
                    }
                    int ring = rim.Count, nr = Mathf.Clamp(Mathf.CeilToInt(hr / 5f), 1, 32); bool flip = area > 0f;
                    var u1 = new Vector4(hr, 5f, 0f, 1f); int c0 = V.Count;
                    // the bays: along the dock side from its first end (dd), out of the wall toward the yard (dOut)
                    Vector2 dA = Vector2.zero, dd = Vector2.zero, dOut = Vector2.zero; float dL = 0f, pitch = 0f;
                    if (yd.d != null && yd.d.Length >= 5 && yd.d[4] >= 1f)
                    {
                        dA = new Vector2(yd.d[0], yd.d[1]); var dB = new Vector2(yd.d[2], yd.d[3]); dL = (dB - dA).magnitude;
                        if (dL > 1f)
                        {
                            dd = (dB - dA) / dL; dOut = new Vector2(-dd.y, dd.x); if (Vector2.Dot(c - dA, dOut) < 0f) dOut = -dOut;
                            pitch = dL / Mathf.Round(yd.d[4]); nBays++;
                        }
                    }
                    Vector4 Bay(Vector2 q) => pitch > 0f ? new Vector4(Vector2.Dot(q - dA, dd), Vector2.Dot(q - dA, dOut), pitch, dL) : Vector4.zero;
                    V.Add(new Vector3(c.x, CityGround.HeightAt(c.x, c.y) + 0.19f, c.y)); U0.Add(Bay(c)); U1.Add(u1); U2.Add(yv); U3.Add(Vector4.zero);
                    for (int r = 1; r <= nr; r++)
                        for (int i = 0; i < ring; i++)
                        {
                            var q = Vector2.Lerp(c, rim[i], r / (float)nr);
                            V.Add(new Vector3(q.x, CityGround.HeightAt(q.x, q.y) + 0.19f, q.y)); U0.Add(Bay(q)); U1.Add(u1); U2.Add(yv); U3.Add(Vector4.zero);
                        }
                    void Tri(int a, int b, int d) { T.Add(a); if (flip) { T.Add(d); T.Add(b); } else { T.Add(b); T.Add(d); } }
                    for (int i = 0; i < ring; i++) Tri(c0, c0 + 1 + (i + 1) % ring, c0 + 1 + i);
                    for (int r = 1; r < nr; r++)
                    {
                        int i0 = c0 + 1 + (r - 1) * ring, o0 = c0 + 1 + r * ring;
                        for (int i = 0; i < ring; i++)
                        {
                            int i1 = (i + 1) % ring;
                            Tri(i0 + i, o0 + i1, o0 + i); Tri(i0 + i, i0 + i1, o0 + i1);
                        }
                    }
                    nYards++; padRings.Add(rim.ToArray());
                    if (V.Count > 180000) Flush();
                }
            Flush();
            patches.Clear();
            foreach (var kv in nodes)
            {
                var nd = kv.Value; if (nd.Deg < 2) continue;
                long key = SKey(Mathf.FloorToInt(nd.P.x / SG), Mathf.FloorToInt(nd.P.y / SG));
                if (!segGrid.TryGetValue(key, out var l)) segGrid[key] = l = new List<Vector2Int>();
                l.Add(new Vector2Int(-1 - patches.Count, 0)); patches.Add((nd.P, nd.Half, nd.Half + nd.Walk, nd.Hy));       // x < 0: a junction patch
            }
            for (int k = 0; k < padRings.Count; k++)                       // x < 0, y = 1: a turnaround pad (yard space: people only)
            {
                var r = padRings[k]; Vector2 lo = r[0], hi = r[0]; foreach (var q in r) { lo = Vector2.Min(lo, q); hi = Vector2.Max(hi, q); }
                for (int gx = Mathf.FloorToInt(lo.x / SG); gx <= Mathf.FloorToInt(hi.x / SG); gx++)
                    for (int gz = Mathf.FloorToInt(lo.y / SG); gz <= Mathf.FloorToInt(hi.y / SG); gz++)
                    {
                        long key = SKey(gx, gz); if (!segGrid.TryGetValue(key, out var l)) segGrid[key] = l = new List<Vector2Int>();
                        l.Add(new Vector2Int(-1 - k, 1));
                    }
            }
            // the junctions with pedestrian crossings (CrossAt, MidJunctions): the zone out to the far edge of their zebras (FilmTrees)
            crossZones.Clear(); crossGrid.Clear();
            foreach (var kv in nodes)
            {
                var nd = kv.Value; if (nd.Fast || nd.Major == 0) continue;
                float r0 = Mathf.Max(nd.Deg >= 3 ? nd.Half + nd.Walk + 1f : 0f, nd.ThroughOff); if (r0 <= 0f) continue;
                long key = SKey(Mathf.FloorToInt(nd.P.x / SG), Mathf.FloorToInt(nd.P.y / SG));
                if (!crossGrid.TryGetValue(key, out var cl)) crossGrid[key] = cl = new List<int>();
                cl.Add(crossZones.Count); crossZones.Add((nd.P, r0 + 5f));
            }
            BuiltVersion++;
            Debug.Log($"[Alatau] film roads: {km:0} km in {meshes} meshes");
            int nNew = 0, nH = 0, nRamp = 0, nDrive = 0; foreach (var q in strokes) { if (q.Edge >= 0) nNew++; if (q.Deck != null) nH++; if (q.Edge >= 0 && q.Ramp) nRamp++; if (q.Drive) nDrive++; }
            if (nNew > 0)
                Debug.Log($"[Alatau] film roads v2: {nNew} strokes of the redrawn map ({nRamp} ramps, {nDrive} drives, {nPads} turnaround pads, {nPadPl} of them in plaza or court paving; {nYards} truck yards, {nBays} with dock bays), {nH} raised in places, {nStaged} later cross-sections of reconstructions (roads.json ps); structures: {structQuads} wall/deck faces, {piers} piers ({columns} columns, {caps} with a cap beam; {spansBare} spans over {PierSpan:0} m without one)");

            // decks, walls and piers of the raised roads of the redrawn map (code 3, concrete), merged into the road meshes (no extra objects
            // or draw calls): retaining walls down into the ground along an embankment; on a bridge or an overpass a 1.5 m deck edge and the
            // underside; abutments at both ends of a span and piers ≤ 30 m apart (PierSpan), never on a road that passes below
            void Quad2(Vector3 a, Vector3 b, Vector3 c, Vector3 d, float al0, float al1, Vector4 yrs)
            {
                for (int side = 0; side < 2; side++)
                {
                    int q0 = V.Count; V.Add(a); V.Add(b); V.Add(c); V.Add(d);
                    U0.Add(new Vector4(0f, al0, 0f, 0f)); U0.Add(new Vector4(0f, al1, 0f, 0f)); U0.Add(new Vector4(1f, al1, 0f, 0f)); U0.Add(new Vector4(1f, al0, 0f, 0f));
                    for (int k = 0; k < 4; k++) { U1.Add(new Vector4(1f, 3f, 1f, 1f)); U2.Add(yrs); U3.Add(Vector4.zero); }
                    if (side == 0) { T.Add(q0); T.Add(q0 + 1); T.Add(q0 + 2); T.Add(q0); T.Add(q0 + 2); T.Add(q0 + 3); }
                    else { T.Add(q0); T.Add(q0 + 2); T.Add(q0 + 1); T.Add(q0); T.Add(q0 + 3); T.Add(q0 + 2); }
                }
                structQuads++;
            }
            void Structures(int self, Stroke st, List<float> al, float outer, float up, Vector4 yrs)
            {
                var P = st.P; var dk = st.Deck; var H = st.H; int n = P.Count;
                Vector2 Left(int i) { Vector2 d = (P[Mathf.Min(i + 1, n - 1)] - P[Mathf.Max(i - 1, 0)]).normalized; return new Vector2(-d.y, d.x); }
                float Top(int i, Vector2 p) { float g = CityGround.HeightAt(p.x, p.y) + up; return dk[i] > 0f ? Mathf.Lerp(g, H[i] + up, dk[i]) : g; }
                for (int i = 1; i < n; i++)
                {
                    if (dk[i - 1] <= 0.01f && dk[i] <= 0.01f) continue;
                    int code = StAt(st.St, (al[i - 1] + al[i]) * 0.5f); if (code == 5) continue;
                    bool span = code == 3 || code == 4; Vector2 l0 = Left(i - 1), l1 = Left(i);
                    for (int sd = -1; sd <= 1; sd += 2)
                    {
                        Vector2 a = P[i - 1] + l0 * (outer * sd), b = P[i] + l1 * (outer * sd);
                        float ta = Top(i - 1, a), tb = Top(i, b);
                        float ba = span ? ta - 1.5f : CityGround.HeightAt(a.x, a.y) - 0.6f, bb = span ? tb - 1.5f : CityGround.HeightAt(b.x, b.y) - 0.6f;
                        if (ta - ba < 0.05f && tb - bb < 0.05f) continue;
                        Quad2(new Vector3(a.x, ba, a.y), new Vector3(b.x, bb, b.y), new Vector3(b.x, tb, b.y), new Vector3(a.x, ta, a.y), al[i - 1], al[i], yrs);
                    }
                    if (span)
                    {
                        Vector2 a0 = P[i - 1] - l0 * outer, a1 = P[i - 1] + l0 * outer, b0 = P[i] - l1 * outer, b1 = P[i] + l1 * outer;
                        Quad2(new Vector3(a0.x, Top(i - 1, a0) - 1.5f, a0.y), new Vector3(b0.x, Top(i, b0) - 1.5f, b0.y), new Vector3(b1.x, Top(i, b1) - 1.5f, b1.y),
                              new Vector3(a1.x, Top(i - 1, a1) - 1.5f, a1.y), al[i - 1], al[i], yrs);
                    }
                }
                if (st.St == null) return;
                void At(float m, out Vector2 c, out Vector2 left, out float top)
                {
                    int i = 1; while (i < n - 1 && al[i] < m) i++;
                    float t = Mathf.Clamp01(Mathf.InverseLerp(al[i - 1], al[i], m));
                    c = Vector2.Lerp(P[i - 1], P[i], t); left = Vector2.Lerp(Left(i - 1), Left(i), t).normalized;
                    top = Mathf.Lerp(Top(i - 1, P[i - 1]), Top(i, P[i]), t);
                }
                void Wall(Vector2 a, Vector2 b, float y0a, float y0b, float y1, float al0)
                {
                    if (y1 - Mathf.Max(y0a, y0b) < 0.3f) return;
                    Quad2(new Vector3(a.x, y0a, a.y), new Vector3(b.x, y0b, b.y), new Vector3(b.x, y1, b.y), new Vector3(a.x, y1, a.y), al0, al0, yrs);
                }
                for (int k = 0; k + 2 < st.St.Length; k += 3)
                {
                    int code = Mathf.RoundToInt(st.St[k + 2]); if (code != 3 && code != 4) continue;
                    float m0 = Mathf.Max(0f, st.St[k]), m1 = Mathf.Min(al[n - 1], st.St[k + 1]); if (m1 - m0 < 4f) continue;
                    foreach (float m in new[] { m0, m1 })
                    {
                        At(m, out var c, out var left, out float top); Vector2 a = c - left * outer, b = c + left * outer;
                        Wall(a, b, CityGround.HeightAt(a.x, a.y) - 0.6f, CityGround.HeightAt(b.x, b.y) - 0.6f, top - 1.5f, m);          // abutment
                    }
                    // a pier is a row of columns under the whole width of the deck, the outer two under its edges (so that it reads from the
                    // side, under the deck edge), at most PierGap m apart; each column keeps PierClear off the lanes of a road below (their
                    // asphalt, not a median: it may stand in the central reserve of a dual road) and moves along the span on its own (≤ PierSkew)
                    // where the span crosses a road below at a skew. Of the places for a pier the straightest row is taken; a row standing in
                    // one line carries a cap beam under the deck where nothing passes under the beam with less than 4.5 m of headroom
                    float reach = Mathf.Max(1f, outer - ColAcross - 0.3f);
                    int nc = Mathf.Max(2, Mathf.CeilToInt(2f * reach / PierGap) + 1);
                    var colO = new float[nc]; var colD = new float[nc]; var bestD = new float[nc];
                    for (int j = 0; j < nc; j++) colO[j] = -reach + 2f * reach * j / (nc - 1);
                    bool Clear(float m, float o) { if (m <= m0 + 2f || m >= m1 - 2f) return false; At(m, out var c, out var left, out float top); return !RoadBelow(self, c + left * o, top - 3f, PierClear); }
                    // the columns' moves along the span at m (colD) and how far from one line they stand (sum of |move|); < 0: no room
                    float Fits(float m)
                    {
                        float sum = 0f;
                        for (int j = 0; j < nc; j++)
                        {
                            bool ok = false;
                            for (float d = 0f; d <= PierSkew && !ok; d += 0.5f)
                            {
                                if (Clear(m + d, colO[j])) { colD[j] = d; ok = true; }
                                else if (d > 0f && Clear(m - d, colO[j])) { colD[j] = -d; ok = true; }
                            }
                            if (!ok) return -1f;
                            sum += Mathf.Abs(colD[j]);
                        }
                        return sum;
                    }
                    void Column(float m, float o)
                    {
                        At(m, out var c, out var left, out float top); var dir = new Vector2(left.y, -left.x); var q = c + left * o;
                        float g = CityGround.HeightAt(q.x, q.y) - 1.5f, y1 = top - 1.5f;                // into the ground (the terrain mesh is cut on the other diagonal)
                        Vector2 p00 = q - dir * ColAlong - left * ColAcross, p10 = q + dir * ColAlong - left * ColAcross, p11 = q + dir * ColAlong + left * ColAcross, p01 = q - dir * ColAlong + left * ColAcross;
                        Wall(p00, p10, g, g, y1, m); Wall(p10, p11, g, g, y1, m); Wall(p11, p01, g, g, y1, m); Wall(p01, p00, g, g, y1, m);
                        columns++;
                    }
                    bool Cap(float m)
                    {
                        At(m, out var c, out var left, out float top); var dir = new Vector2(left.y, -left.x);
                        float y1 = top - 1.5f, y0 = y1 - CapDepth, co = outer - 0.15f;
                        for (float o = -co; o <= co + 0.01f; o += 2f) if (RoadBelow(self, c + left * o, top - 3f, 0.5f, y0 - 4.5f)) return false;
                        Vector2 a0 = c - dir * CapAlong - left * co, a1 = c + dir * CapAlong - left * co, b1 = c + dir * CapAlong + left * co, b0 = c - dir * CapAlong + left * co;
                        Wall(a0, a1, y0, y0, y1, m); Wall(a1, b1, y0, y0, y1, m); Wall(b1, b0, y0, y0, y1, m); Wall(b0, a0, y0, y0, y1, m);
                        Quad2(new Vector3(a0.x, y0, a0.y), new Vector3(a1.x, y0, a1.y), new Vector3(b1.x, y0, b1.y), new Vector3(b0.x, y0, b0.y), m, m, yrs);
                        return true;
                    }
                    float prevM = m0; int placed = 0;
                    while (m1 - prevM > PierSpan)
                    {
                        // aim at even steps to the far abutment; take the straightest row near that
                        float target = prevM + (m1 - prevM) / Mathf.Ceil((m1 - prevM) / PierSpan);
                        float best = -1f, bestS = float.MaxValue;
                        for (float m = prevM + PierSpan; m >= prevM + 8f; m -= 0.5f)
                        {
                            float f = Fits(m); if (f < 0f) continue;
                            float score = f + 0.05f * Mathf.Abs(m - target);
                            if (score < bestS) { bestS = score; best = m; System.Array.Copy(colD, bestD, nc); }
                            if (f == 0f && m <= target) break;                                // lower down only scores worse
                        }
                        if (best < 0f) for (float m = prevM + PierSpan + 0.5f; m < m1 - 8f; m += 0.5f) if (Fits(m) >= 0f) { best = m; System.Array.Copy(colD, bestD, nc); break; }
                        if (best < 0f) break;
                        bool line = true;
                        for (int j = 0; j < nc; j++) { Column(best + bestD[j], colO[j]); if (bestD[j] != 0f) line = false; }
                        if (line && Cap(best)) caps++;
                        piers++; placed++; prevM = best;
                    }
                    if (placed == 0 && m1 - m0 > PierSpan) spansBare++;
                }
            }
        }

        /// <summary>Cross-section of one drawn stroke: its class, or a one-lane ramp, or one carriageway of a dual road.</summary>
        static void StrokeDims(Stroke st, out float half, out float walk, out int lanes, out float lift)
        {
            Dims(st.Cls, out half, out walk, out lanes, out lift);
            if (st.PHalf >= 0f)
            {
                // the street profile of the redrawn map: carriageway, pavements, lanes (one-way and ramps: lanes of one direction)
                half = st.PHalf; walk = st.PWalk; lanes = st.OneWay || st.Ramp ? -st.PLanes : st.PLanes; if (st.Ramp) lift -= 0.05f;
                if (st.Drive) { lanes = -1; lift = 0.16f; }               // a drive: over the street's pavement, under its carriageway
                if (st.NoCars && st.PLanes0 && st.Kind != "bike_path") { walk = half + walk; half = 0f; }   // a boulevard without lanes: all walk and green, no asphalt
                return;
            }
            if (st.Ramp) { half = 4f; walk = 0f; lanes = -1; lift -= 0.05f; }          // a one-lane ramp, under the main carriageway
            else if (st.OneWay)
            {
                // one carriageway of a dual road (the plan draws each direction as its own line, 8–25 m apart): lanes of one direction only
                switch (st.Cls)
                {
                    case TwinData.RoadClass.Highway: half = 6f; lanes = -3; break;
                    case TwinData.RoadClass.Ring: half = 5.5f; lanes = -3; break;
                    case TwinData.RoadClass.Main: half = 3.8f; lanes = -2; break;
                    default: half = 3.2f; lanes = -1; break;
                }
            }
        }

        /// <summary>Where a pedestrian crossing starts on the arm of a street junction, metres from the junction centre (0 = none): a
        /// junction of three or more streets or main roads (never on the motorway or the ring), set back 1 m from the junction's
        /// pavement patch. Width of the crossing: CrossW; the stop line lies 3 m behind it (AlatauRoad draws both).</summary>
        float CrossAt(int node, TwinData.RoadClass cls)
        {
            if (cls == TwinData.RoadClass.Highway || cls == TwinData.RoadClass.Ring) return 0f;
            if (!nodes.TryGetValue(node, out var nd) || nd.Fast || nd.Major == 0) return 0f;
            float r = nd.Deg >= 3 ? nd.Half + nd.Walk + 1f : 0f;
            return Mathf.Max(r, nd.ThroughOff);                              // a street ending on a through road: behind its kerb
        }
        /// <summary>Junction nodes that lie on the middle of another street or main road (not its ends): per through stroke the along
        /// position of each such junction and the set back of its crossings (the side street's half width and pavement + 1 m). Sets
        /// the node's ThroughOff (the through road's half width and pavement + 1 m) for the side street's own crossing.</summary>
        Dictionary<int, List<Vector2>> MidJunctions(List<Stroke> strokes)
        {
            const float SC = 40f; var res = new Dictionary<int, List<Vector2>>();
            var grid = new Dictionary<long, List<(int s, int k)>>(); var alongs = new float[strokes.Count][];
            long Key(int x, int z) => ((long)x << 32) ^ (uint)z;
            for (int s = 0; s < strokes.Count; s++)
            {
                var q = strokes[s]; if (q.P == null || q.P.Count < 2) continue;
                var al = new float[q.P.Count]; for (int k = 1; k < q.P.Count; k++) al[k] = al[k - 1] + (q.P[k] - q.P[k - 1]).magnitude; alongs[s] = al;
                if (q.Ramp || q.Drive || q.Cls == TwinData.RoadClass.Highway || q.Cls == TwinData.RoadClass.Ring) continue;
                for (int k = 1; k < q.P.Count; k++)
                {
                    var m = (q.P[k] + q.P[k - 1]) * 0.5f; long key = Key(Mathf.FloorToInt(m.x / SC), Mathf.FloorToInt(m.y / SC));
                    if (!grid.TryGetValue(key, out var l)) grid[key] = l = new List<(int, int)>(); l.Add((s, k));
                }
            }
            foreach (var kv in nodes)
            {
                var nd = kv.Value; if (nd.Fast || nd.Major == 0) continue;            // a junction of drives only: no crossings on the street
                int gx = Mathf.FloorToInt(nd.P.x / SC), gz = Mathf.FloorToInt(nd.P.y / SC); int bs = -1; float bd = float.MaxValue, ba = 0f;
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!grid.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (var (s, k) in l)
                    {
                        var q = strokes[s]; if (q.A == kv.Key || q.B == kv.Key) continue;
                        var a = q.P[k - 1]; var ab = q.P[k] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                        float t = Mathf.Clamp01(Vector2.Dot(nd.P - a, ab) / L2); float d = (a + ab * t - nd.P).magnitude;
                        if (d < bd) { bd = d; bs = s; ba = alongs[s][k - 1] + t * Mathf.Sqrt(L2); }
                    }
                }
                if (bs < 0) continue;
                StrokeDims(strokes[bs], out float th, out float tw, out _, out _);
                var alb = alongs[bs]; float len = alb[alb.Length - 1];
                if (bd > th * 0.7f + 1.5f || ba < 12f || ba > len - 12f) continue;
                nd.ThroughOff = Mathf.Max(nd.ThroughOff, th + tw + 1f);
                if (!res.TryGetValue(bs, out var list)) res[bs] = list = new List<Vector2>();
                list.Add(new Vector2(ba, nd.Half + nd.Walk + 1f));
            }
            int n = 0; foreach (var l in res.Values) n += l.Count;
            Debug.Log("[Alatau] film roads: " + n + " T-junctions on through roads get crossings");
            return res;
        }
        /// <summary>For one carriageway of a dual road: whether its twin (the other direction) lies on its right (x &lt; 0 across the
        /// ribbon), judged from a few points along it; then its lamps stand on the left kerb, away from the median.</summary>
        static Dictionary<long, List<int>> twinGrid;
        static bool TwinOnRight(List<Stroke> strokes, int si)
        {
            const float C = 60f; long Key(int x, int z) => ((long)x << 32) ^ (uint)z;
            if (twinGrid == null)
            {
                twinGrid = new Dictionary<long, List<int>>();
                for (int s = 0; s < strokes.Count; s++)
                {
                    var q = strokes[s]; if (!q.OneWay || q.P == null) continue;
                    for (int k = 0; k < q.P.Count; k += 2)
                    {
                        long key = Key(Mathf.FloorToInt(q.P[k].x / C), Mathf.FloorToInt(q.P[k].y / C));
                        if (!twinGrid.TryGetValue(key, out var l)) twinGrid[key] = l = new List<int>();
                        if (l.Count == 0 || l[l.Count - 1] != s) l.Add(s);
                    }
                }
            }
            var st = strokes[si]; var P = st.P; int right = 0, leftN = 0;
            for (int f = 1; f <= 5; f++)
            {
                int i = Mathf.Clamp(P.Count * f / 6, 1, P.Count - 1); var p = P[i]; var d = (P[i] - P[i - 1]).normalized; var lft = new Vector2(-d.y, d.x);
                float bd = 40f; float sideSign = 0f;
                int gx = Mathf.FloorToInt(p.x / C), gz = Mathf.FloorToInt(p.y / C);
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!twinGrid.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (int s in l)
                    {
                        if (s == si || strokes[s].Cls != st.Cls) continue; var q = strokes[s].P;
                        for (int k = 1; k < q.Count; k++)
                        {
                            var a = q[k - 1]; var ab = q[k] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                            if (Mathf.Abs(Vector2.Dot(ab.normalized, d)) < 0.9f) continue;
                            var c = a + ab * Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2); float dist = (c - p).magnitude;
                            if (dist > 3f && dist < bd) { bd = dist; sideSign = Vector2.Dot(c - p, lft); }
                        }
                    }
                }
                if (sideSign < 0f) right++; else if (sideSign > 0f) leftN++;
            }
            return right > leftN;
        }
        /// <summary>Width of a crossing along the road: 5 m on main roads, 4 m on streets (stripes 0.5 m with 0.5 m gaps).</summary>
        public static float CrossW(TwinData.RoadClass cls) => cls == TwinData.RoadClass.Main ? 5f : 4f;

        /// <summary>A drawn road with street lamps: centre line, metres along it at each point, half width of the carriageway and pavement width, lamp
        /// spacing and placement (FilmLamps.Rule) and the opening years. Filled when the film roads are built.</summary>
        public class LampRun
        {
            public List<Vector2> P; public float[] Along; public float Half, Walk, Len, Step; public int Mode, Cls; public Vector4 Years; public List<Vector2> Mids;
            /// <summary>Redrawn map: surface heights and deck weights per point (null: on the terrain).</summary>
            public float[] H, Deck;
            /// <summary>Ground of a lamp foot near point seg..seg+1 (t along): the terrain, or the deck / embankment the road lies on.</summary>
            public float FootY(int seg, float t, Vector2 p)
            {
                float g = CityGround.HeightAt(p.x, p.y); if (Deck == null || H == null) return g;
                int a = Mathf.Clamp(seg, 0, Deck.Length - 1), b = Mathf.Min(a + 1, Deck.Length - 1); float d = Mathf.Lerp(Deck[a], Deck[b], t);
                return d > 0f ? Mathf.Lerp(g, Mathf.Lerp(H[a], H[b], t), d) : g;
            }
            /// <summary>Deck weight near point seg..seg+1 (0 on the terrain, 1 on a deck or an embankment at its own height).</summary>
            public float DeckAt(int seg, float t)
            {
                if (Deck == null) return 0f; int a = Mathf.Clamp(seg, 0, Deck.Length - 1), b = Mathf.Min(a + 1, Deck.Length - 1); return Mathf.Lerp(Deck[a], Deck[b], t);
            }
        }
        public static readonly List<LampRun> Lamps = new List<LampRun>();

        class Junction
        {
            public Vector2 P; public int Deg, Major; public float Half, Walk, Lift, ThroughOff, Hy = float.NaN; public bool Fast, Through; public Vector4 Years = new Vector4(9999, 9999, 9999, 9999);
            public readonly List<(Vector2 dir, TwinData.RoadClass cls)> Arms = new List<(Vector2, TwinData.RoadClass)>();
        }
        readonly Dictionary<int, Junction> nodes = new Dictionary<int, Junction>();
        void Node(int id, Vector2 p, Vector2 dir, TwinData.RoadClass cls, float half, float walk, float lift, Vector4 years, float hy = float.NaN, bool drive = false)
        {
            if (!nodes.TryGetValue(id, out var n)) { n = new Junction { P = p }; nodes[id] = n; }
            if (!float.IsNaN(hy)) n.Hy = float.IsNaN(n.Hy) ? hy : Mathf.Max(n.Hy, hy);
            n.Deg++; if (!drive) n.Major++; n.Half = Mathf.Max(n.Half, half); n.Walk = Mathf.Max(n.Walk, walk); n.Lift = Mathf.Max(n.Lift, lift);
            n.Years = Vector4.Min(n.Years, years);                         // the junction is there as soon as its first road is
            if (cls == TwinData.RoadClass.Highway || cls == TwinData.RoadClass.Ring) n.Fast = true;
            // the widest road passes straight through (two arms of the widest class almost opposite): no patch over its markings
            foreach (var a in n.Arms) if (a.cls == cls && Vector2.Dot(a.dir, dir) < -0.94f && half >= n.Half - 0.01f) n.Through = true;
            n.Arms.Add((dir, cls));
        }

        // ---------------------------------------------------------------- strokes: the road graph as long, smooth lines
        class Stroke
        {
            public List<Vector2> P; public TwinData.RoadClass Cls; public Vector4 Years; public int A, B; public float Len; public bool Ramp, OneWay, Fixed;
            // the redrawn map (film_roads v2): roads edge, norms class, profile, interchange, surface heights, structures; the cross-section
            // from the profile (PHalf < 0: by class as before); Deck[i] 0 = on the terrain … 1 = at H[i] (an embankment or a deck)
            public int Edge = -1, Prof = -1, Ic = -1; public string Kind; public float[] H, St, Deck; public float PHalf = -1f, PWalk, PMedian; public int PLanes; public bool NoCars;
            /// <summary>A drive to buildings or a fire lane (driveways.json): no through traffic, no lamps, no markings. PLanes0: the profile has no lanes.</summary>
            public bool Drive, PLanes0;
            /// <summary>A reconstruction (roads.json `ps`): Prof0 = the opening profile; from StageY[k] (per scenario) the profile StageP[k],
            /// whose carriageway half width, lanes (of one direction on a ramp or a one-way carriageway) and median are StageHalf / StageLanes /
            /// StageMedian. Null without one.</summary>
            public int Prof0 = -1; public int[] StageP, StageLanes; public Vector4[] StageY; public float[] StageHalf, StageMedian;
        }
        static List<Stroke> drawn; static Dictionary<int, List<int>> drawnAt;

        /// <summary>A road as the film look draws it, for what is placed on the roads (traffic, street lamps): centre line, class, opening
        /// year per scenario (x..w = scenario 0..3), whether it is a ramp or one carriageway of a dual road (then it runs in point order),
        /// its end nodes in TwinData.RoadNodes and its length in metres. Cross-section: Dims. No ways until the film roads are built.</summary>
        /// Redrawn map (film_roads v2): Edge = roads.json edge (−1 old data; then the rest is unset), Kind = norms class, Half / Walk / Median =
        /// carriageway half width, pavement width per side and median from the street profile (Half &lt; 0: by class, Dims), Lanes per
        /// direction, NoCars (pedestrian street, bike path), HasHeights (raised somewhere: use SurfaceY).
        public struct Way
        {
            public IReadOnlyList<Vector2> P; public TwinData.RoadClass Cls; public Vector4 Years; public bool Ramp, OneWay; public int A, B; public float Len;
            public int Edge, Lanes, Ic; public string Kind; public float Half, Walk, Median; public bool NoCars, HasHeights;
            /// <summary>A drive to buildings or a fire lane: people walk on it, film traffic never drives it (access only, no through route).</summary>
            public bool Drive;
            /// <summary>A reconstruction (roads.json `ps`): from StageYears[k] (x..w = scenario 0..3) the way has StageLanes[k] lanes per
            /// direction, carriageway half width StageHalf[k] and median StageMedian[k] instead of Lanes / Half / Median; null without one.</summary>
            public Vector4[] StageYears; public float[] StageHalf, StageMedian; public int[] StageLanes;
        }
        public static int WayCount => drawn != null ? drawn.Count : 0;
        public static Way GetWay(int i)
        {
            var q = drawn[i];
            return new Way { P = q.P, Cls = q.Cls, Years = q.Years, Ramp = q.Ramp, OneWay = q.OneWay, A = q.A, B = q.B, Len = q.Len, Edge = q.Edge, Lanes = q.PLanes, Ic = q.Ic,
                Kind = q.Kind, Half = q.PHalf, Walk = q.PWalk, Median = q.PMedian, NoCars = q.NoCars, HasHeights = q.Deck != null, Drive = q.Drive,
                StageYears = q.StageY, StageHalf = q.StageHalf, StageMedian = q.StageMedian, StageLanes = q.StageLanes };
        }
        /// <summary>Surface of way i (as drawn) between its points seg and seg+1 (t along) at p, plus 'up': the terrain, or the embankment /
        /// deck of the redrawn map. Old data and ways without heights: CityGround.HeightAt(p) + up, as before.</summary>
        public static float SurfaceY(int way, int seg, float t, Vector2 p, float up)
        {
            float g = CityGround.HeightAt(p.x, p.y) + up;
            var q = drawn != null && way >= 0 && way < drawn.Count ? drawn[way] : null; if (q == null || q.Deck == null) return g;
            int n = q.Deck.Length, a = Mathf.Clamp(seg, 0, n - 1), b = Mathf.Min(a + 1, n - 1); float d = Mathf.Lerp(q.Deck[a], q.Deck[b], t);
            return d > 0f ? Mathf.Lerp(g, Mathf.Lerp(q.H[a], q.H[b], t) + up, d) : g;
        }

        // ---------------------------------------------------------------- street profiles (public API, FilmTrees and the generators read it)
        /// <summary>Cross-section of a roads.json edge. Has = from its street profile (redrawn map); otherwise from its class (Dims) and the
        /// widths below are the ones the film roads draw for old data. Carriage = half width kerb to kerb, Outer = half width to the outer
        /// edge of pavements, verges and bike lanes (the wider side), RedLineW = full width between red lines. Side values: [left, right]
        /// of the edge's point order.</summary>
        public struct Section
        {
            public bool Has; public string Kind; public int LanesFwd, LanesBack; public float LaneW, MedianW, RedLineW, Carriage, Outer;
            public float SidewalkL, SidewalkR, VergeL, VergeR, BikeL, BikeR, ParkingL, ParkingR;
        }
        static void Halves(TwinData.RoadProfile pr, string kind, out float car, out float outer)
        {
            float lw = pr.LaneW > 0f ? pr.LaneW : 3f;
            car = (Mathf.Max(0, pr.LanesF) + Mathf.Max(0, pr.LanesB)) * lw * 0.5f + pr.MedianW * 0.5f + (pr.Parking[0] + pr.Parking[1]) * 0.5f;
            float side = Mathf.Max(pr.Sidewalk[0] + pr.Verge[0] + pr.Bike[0], pr.Sidewalk[1] + pr.Verge[1] + pr.Bike[1]);
            if (kind == "bike_path") { car = Mathf.Max(0.75f, (pr.Bike[0] + pr.Bike[1]) * 0.5f); side = Mathf.Max(pr.Verge[0], pr.Verge[1]); }
            outer = car + side;
        }
        public static Section Profile(int edge) => Profile(edge, -2);
        /// <summary>The cross-section of an edge with profile 'prof' (−2: its own opening profile; a stage of roads.json `ps`).</summary>
        public static Section Profile(int edge, int prof)
        {
            var sec = new Section(); var R = TwinData.Roads; if (edge < 0 || edge >= R.Length) return sec;
            var e = R[edge]; sec.Kind = e.T; int pi = prof == -2 ? e.P : prof;
            var pr = pi >= 0 && pi < TwinData.RoadProfiles.Length ? TwinData.RoadProfiles[pi] : null;
            if (pr == null)
            {
                Dims(e.Cls, out float h, out float w, out int ln, out _);
                sec.Carriage = h; sec.Outer = h + w; sec.LanesFwd = ln; sec.LanesBack = e.K == 0 ? ln : 0; sec.SidewalkL = sec.SidewalkR = w; sec.RedLineW = 2f * (h + w) + 6f;
                return sec;
            }
            sec.Has = true; sec.LanesFwd = pr.LanesF; sec.LanesBack = pr.LanesB; sec.LaneW = pr.LaneW; sec.MedianW = pr.MedianW; sec.RedLineW = pr.RedLineW;
            sec.SidewalkL = pr.Sidewalk[0]; sec.SidewalkR = pr.Sidewalk[1]; sec.VergeL = pr.Verge[0]; sec.VergeR = pr.Verge[1];
            sec.BikeL = pr.Bike[0]; sec.BikeR = pr.Bike[1]; sec.ParkingL = pr.Parking[0]; sec.ParkingR = pr.Parking[1];
            Halves(pr, e.T, out sec.Carriage, out sec.Outer);
            if (sec.RedLineW < 2f * sec.Outer) sec.RedLineW = 2f * sec.Outer;
            return sec;
        }
        /// <summary>Half widths of an edge's corridor: carriageway, outer edge of its pavements and verges, red line. True when they come
        /// from a street profile (redrawn map), false when from the class.</summary>
        public static bool Corridor(int edge, out float carriage, out float outer, out float red)
        {
            var s = Profile(edge); carriage = s.Carriage; outer = s.Outer; red = Mathf.Max(s.RedLineW * 0.5f, outer); return s.Has;
        }
        /// <summary>A boulevard's green median (trees: FilmTrees): its half width, or false.</summary>
        public static bool MedianGreen(int edge, out float half)
        {
            var s = Profile(edge); half = s.MedianW * 0.5f - 0.2f; return s.Has && s.MedianW > 0.5f && half > 0.3f;
        }
        /// <summary>The corridor of an edge for what grows or stands beside the road (RoadCorridors.Provider, FilmTrees), half widths from
        /// the centre line: carriage to the outer kerb (across a boulevard's median), outer to the red line, row = offset of the street tree
        /// row (0 none: expressways, ramps, bike paths), median = planted strip width, oneSide = one carriageway of a divided road or a ramp.
        /// A street tree stands in the verge, else on the lawn behind the pavement when the red line leaves 2.5 m there, never on the
        /// pavement; a pedestrian street (all of it paved) keeps its rows 3 m off the paving (on the lawn of the park or the yard beside
        /// it) and the groves 1.5 m off. False without a street profile (old data: the caller keeps today's class widths).</summary>
        public static bool CorridorOf(int edge, out float carriage, out float outer, out float row, out float median, out bool oneSide)
        {
            var s = Profile(edge); carriage = s.Carriage; outer = Mathf.Max(s.Outer, s.RedLineW * 0.5f); median = s.MedianW; row = 0f;
            var R = TwinData.Roads; int k = edge >= 0 && edge < R.Length ? R[edge].K : 0; oneSide = k != 0;
            // a reconstruction (roads.json `ps`): nothing grows where the widened carriageway and its pavements will be
            if (s.Has && edge < R.Length && R[edge].PsP != null)
                foreach (int p in R[edge].PsP)
                {
                    var w = Profile(edge, p); if (!w.Has) continue;
                    float grow = Mathf.Max(0f, w.Carriage - s.Carriage); carriage = Mathf.Max(carriage, w.Carriage);
                    outer = Mathf.Max(outer + grow, Mathf.Max(w.Outer, w.RedLineW * 0.5f)); s.Outer = Mathf.Max(s.Outer, w.Outer); s.Carriage = carriage;
                }
            if (!s.Has) return false;
            float walk = Mathf.Max(s.SidewalkL, s.SidewalkR), verge = Mathf.Max(s.VergeL, s.VergeR), bike = Mathf.Max(s.BikeL, s.BikeR);
            if (k == 2 || s.Kind == "expressway" || s.Kind == "ramp" || s.Kind == "bike_path") row = 0f;
            else if (s.Kind == "pedestrian_street")
            {
                float paved = Mathf.Max(carriage, 0f) + walk; row = paved + (verge >= 1.2f ? verge * 0.5f : 3f); outer = Mathf.Max(outer, paved + 1.5f);
                carriage = Mathf.Max(carriage, 1f);
            }
            else row = verge >= 1.2f ? carriage + verge * 0.5f : outer - (carriage + bike + walk) >= 2.5f ? carriage + bike + walk + 1.2f : 0f;
            if (carriage <= 0f) carriage = 0.5f;
            return true;
        }
        /// <summary>Hands the street profiles to the trees (RoadCorridors) without reflection; edges without a profile keep today's widths.</summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        static void WireCorridors()
        {
            RoadCorridors.Provider = (int e, out RoadCorridors.Corridor c) =>
            {
                bool ok = CorridorOf(e, out float k, out float o, out float r, out float m, out bool one);
                c = new RoadCorridors.Corridor { Carriage = k, Outer = o, Row = r, Median = m, OneSide = one, FromProfile = ok };
                return ok;
            };
        }
        /// <summary>Structure at 'metres' along a roads.json edge: 0 ground, 1 embankment, 2 cut, 3 bridge, 4 overpass, 5 tunnel.</summary>
        public static int StructAt(int edge, float metres)
        {
            var R = TwinData.Roads; return edge >= 0 && edge < R.Length ? StAt(R[edge].St, metres) : 0;
        }
        static int StAt(float[] st, float m)
        {
            if (st == null) return 0;
            for (int k = 0; k + 2 < st.Length; k += 3) if (m >= st[k] && m <= st[k + 1]) return Mathf.RoundToInt(st[k + 2]);
            return 0;
        }
        static void ApplyProfile(Stroke s)
        {
            s.NoCars = s.Kind == "pedestrian_street" || s.Kind == "bike_path";
            s.Drive = s.Kind != null && s.Kind.StartsWith("driveway", System.StringComparison.Ordinal);
            var pr = s.Prof >= 0 && s.Prof < TwinData.RoadProfiles.Length ? TwinData.RoadProfiles[s.Prof] : null; if (pr == null) return;
            s.PLanes0 = pr.LanesF + pr.LanesB <= 0; if (s.PLanes0) s.NoCars = true;      // a boulevard's green strip with paths: no cars by design
            Halves(pr, s.Kind, out float car, out float outer);
            s.PHalf = car; s.PWalk = outer - car; s.PMedian = pr.MedianW;
            s.PLanes = s.OneWay || s.Ramp ? Mathf.Max(1, pr.LanesF) : Mathf.Max(1, Mathf.Max(pr.LanesF, pr.LanesB));
        }
        /// <summary>The stroke with profile 'prof' (its cross-section fields as ApplyProfile sets them).</summary>
        static void UseProfile(Stroke s, int prof)
        {
            s.Prof = prof; s.PHalf = -1f; s.PWalk = 0f; s.PMedian = 0f; s.PLanes = 0; s.PLanes0 = false; ApplyProfile(s);
        }
        /// <summary>A reconstruction of the stroke's edge (roads.json `ps`, w43 round 7: a ramp gets more lanes from a year, the geometry
        /// stays): its stages with their years (never before the stroke's own) and cross-sections; the stroke keeps its opening profile.</summary>
        static void Stages(Stroke st, TwinData.RoadEdge e)
        {
            var ps = new List<int>(); var ys = new List<Vector4>();
            for (int k = 0; k < e.PsP.Length; k++)
            {
                if (e.PsP[k] < 0 || e.PsP[k] >= TwinData.RoadProfiles.Length) continue;
                var y = e.PsY[k]; ps.Add(e.PsP[k]);
                ys.Add(new Vector4(Mathf.Max(y[0], st.Years.x), Mathf.Max(y[1], st.Years.y), Mathf.Max(y[2], st.Years.z), Mathf.Max(y[3], st.Years.w)));
            }
            if (ps.Count == 0) return;
            st.StageP = ps.ToArray(); st.StageY = ys.ToArray(); int n = ps.Count;
            st.StageHalf = new float[n]; st.StageLanes = new int[n]; st.StageMedian = new float[n];
            for (int k = 0; k < n; k++) { UseProfile(st, ps[k]); st.StageHalf[k] = st.PHalf; st.StageLanes[k] = st.PLanes; st.StageMedian[k] = st.PMedian; }
            UseProfile(st, st.Prof0);
        }
        /// <summary>The widest cross-section a stroke has in any year (its opening one, or a later stage): what the trees, the piers and
        /// the run counters keep clear of.</summary>
        static void WidestDims(Stroke q, out float half, out float walk, out float lift)
        {
            StrokeDims(q, out half, out walk, out _, out lift);
            if (q.StageP == null) return;
            float outer = half + walk;
            foreach (int p in q.StageP) { UseProfile(q, p); StrokeDims(q, out float h, out float w, out _, out _); half = Mathf.Max(half, h); outer = Mathf.Max(outer, h + w); }
            UseProfile(q, q.Prof0); walk = outer - half;
        }
        /// <summary>Opening years with a closing year packed in for the road shader: year + 10000 × (until − 2000) per scenario (until
        /// ≥ 9000 or absent: never closes). AlatauRoad shows a ribbon from its year until the year before 'until'.</summary>
        static Vector4 Until(Vector4 from, Vector4 until)
        {
            var r = from;
            for (int k = 0; k < 4; k++) if (until[k] > 2000f && until[k] < 9000f) r[k] = from[k] + 10000f * (until[k] - 2000f);
            return r;
        }
        /// <summary>Deck weight per point: 0 on the terrain (|h − ground| &lt; 0.5 m, or a cut), 1 at its own height from 2.5 m up and on every
        /// bridge or overpass span; null when the stroke never leaves the terrain (it is then drawn exactly as a road of the old data).</summary>
        static void EnsureDeck(Stroke st)
        {
            if (st.H == null || st.Deck != null) return;
            int n = st.P.Count; var d = new float[n]; bool any = false; float acc = 0f;
            for (int i = 0; i < n; i++)
            {
                if (i > 0) acc += (st.P[i] - st.P[i - 1]).magnitude;
                float e = st.H[i] - CityGround.HeightAt(st.P[i].x, st.P[i].y);
                d[i] = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.5f, 2.5f, e));
                int c = StAt(st.St, acc); if (c == 3 || c == 4) d[i] = 1f;
                any |= d[i] > 0f;
            }
            st.Deck = any ? d : null;
        }
        static float EndY(Stroke st, int i) => st.Deck != null && st.Deck[i] > 0.5f ? st.H[i] : float.NaN;
        static bool[] TunnelSegs(Stroke st, List<float> al)
        {
            if (st.St == null) return null; bool[] t = null;
            for (int i = 1; i < st.P.Count; i++) if (StAt(st.St, (al[i - 1] + al[i]) * 0.5f) == 5) { if (t == null) t = new bool[st.P.Count]; t[i] = true; }
            return t;
        }

        // ---------------------------------------------------------------- where the drawn roads are (piers, run counters)
        const float SG = 40f;
        static readonly Dictionary<long, List<Vector2Int>> segGrid = new Dictionary<long, List<Vector2Int>>();
        static readonly List<(Vector2 p, float r)> crossZones = new List<(Vector2, float)>();
        static readonly Dictionary<long, List<int>> crossGrid = new Dictionary<long, List<int>>();
        /// <summary>Counts the builds of the drawn roads (FilmTrees places its cells again once they exist: OnSurface, NearCrossing).</summary>
        public static int BuiltVersion;
        /// <summary>The drawn roads exist (OnSurface answers true everywhere before).</summary>
        public static bool Ready => drawn != null && sHalf != null;
        /// <summary>Within 'extra' metres of a junction's pedestrian crossings (from its centre out to the far edge of the zebras that
        /// AlatauRoad draws CrossAt … CrossAt + CrossW from it, on every arm)? FilmTrees keeps street trees off them and the corner.</summary>
        public static bool NearCrossing(Vector2 p, float extra)
        {
            int gx = Mathf.FloorToInt(p.x / SG), gz = Mathf.FloorToInt(p.y / SG);
            for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
            {
                if (!crossGrid.TryGetValue(SKey(gx + dx, gz + dz), out var l)) continue;
                foreach (int i in l) { var z = crossZones[i]; float r = z.r + extra; if ((z.p - p).sqrMagnitude < r * r) return true; }
            }
            return false;
        }
        static float[] sHalf, sWalk, sLift; static Vector2[] sLanes; static readonly List<(Vector2 p, float rc, float ro, float hy)> patches = new List<(Vector2, float, float, float)>();
        static readonly List<Vector2[]> padRings = new List<Vector2[]>();
        static bool InRing(Vector2[] r, Vector2 p, float margin)
        {
            bool inside = false;
            for (int i = 0, j = r.Length - 1; i < r.Length; j = i++)
            {
                if ((r[i].y > p.y) != (r[j].y > p.y) && p.x < (r[j].x - r[i].x) * (p.y - r[i].y) / (r[j].y - r[i].y) + r[i].x) inside = !inside;
                Vector2 a = r[j], ab = r[i] - a; float L2 = ab.sqrMagnitude;
                if (L2 > 1e-6f && (a + ab * Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2) - p).sqrMagnitude <= margin * margin) return true;
            }
            return inside;
        }
        static long SKey(int x, int z) => ((long)x << 32) ^ (uint)z;
        /// <summary>Where the lanes of a stroke lie across it (distances from the centre line, inner .. outer): a road of the redrawn map
        /// with a street profile, its lanes (and parking) only, a two-way road's median free; else the drawn half width.</summary>
        static Vector2 LanesBand(Stroke q, float half)
        {
            var pr = q.Prof >= 0 && q.Prof < TwinData.RoadProfiles.Length ? TwinData.RoadProfiles[q.Prof] : null;
            if (pr == null || q.PHalf < 0f || q.NoCars || q.Drive) return new Vector2(0f, half);
            float lw = pr.LaneW > 0f ? pr.LaneW : 3f;
            if (q.OneWay || q.Ramp) return new Vector2(0f, Mathf.Min(half, Mathf.Max(1, pr.LanesF) * lw * 0.5f + (pr.Parking[0] + pr.Parking[1]) * 0.5f));
            float m = pr.MedianW * 0.5f; return new Vector2(m, Mathf.Min(half, m + Mathf.Max(pr.LanesF, pr.LanesB) * lw + Mathf.Max(pr.Parking[0], pr.Parking[1])));
        }
        static void BuildSegGrid(List<Stroke> strokes)
        {
            segGrid.Clear(); sHalf = new float[strokes.Count]; sWalk = new float[strokes.Count]; sLift = new float[strokes.Count]; sLanes = new Vector2[strokes.Count];
            for (int s = 0; s < strokes.Count; s++)
            {
                var q = strokes[s]; WidestDims(q, out sHalf[s], out sWalk[s], out sLift[s]); sLanes[s] = LanesBand(q, sHalf[s]); if (q.P == null) continue;
                for (int k = 1; k < q.P.Count; k++)
                {
                    Vector2 a = q.P[k - 1], b = q.P[k]; int n = Mathf.Max(1, Mathf.CeilToInt((b - a).magnitude / (SG * 0.5f))); long last = long.MinValue;
                    for (int i = 0; i <= n; i++)
                    {
                        var c = Vector2.Lerp(a, b, i / (float)n); long key = SKey(Mathf.FloorToInt(c.x / SG), Mathf.FloorToInt(c.y / SG)); if (key == last) continue; last = key;
                        if (!segGrid.TryGetValue(key, out var l)) segGrid[key] = l = new List<Vector2Int>();
                        if (l.Count == 0 || l[l.Count - 1] != new Vector2Int(s, k)) l.Add(new Vector2Int(s, k));
                    }
                }
            }
        }
        /// <summary>Piers of a span of the redrawn map stand at most PierSpan m apart, a row of columns (ColAlong × ColAcross half sizes) at
        /// most PierGap m apart across the deck, the outer two under its edges, each PierClear m off the lanes of a road below (its own half
        /// size and 0.4 m); a column moves at most PierSkew m along the span to find the central reserve. A cap beam CapDepth m deep and
        /// 2 × CapAlong m wide joins a row that stands in one line.</summary>
        const float PierSpan = 30f, PierGap = 12f, PierClear = 1.4f, PierSkew = 6f, ColAlong = 1.0f, ColAcross = 0.8f, CapDepth = 1.0f, CapAlong = 1.1f;
        /// <summary>Does a drawn road (not 'self') run with its lanes within margin of p (sLanes: a road of the redrawn map with a median
        /// keeps it free) and its surface below 'below'?</summary>
        static bool RoadBelow(int self, Vector2 p, float below, float margin, float above = float.NegativeInfinity)
        {
            int gx = Mathf.FloorToInt(p.x / SG), gz = Mathf.FloorToInt(p.y / SG);
            for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
            {
                if (!segGrid.TryGetValue(SKey(gx + dx, gz + dz), out var l)) continue;
                foreach (var e in l)
                {
                    if (e.x == self || e.x < 0) continue; var q = drawn[e.x];
                    Vector2 a = q.P[e.y - 1], ab = q.P[e.y] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                    float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2); var c = a + ab * t; var ln = sLanes[e.x]; float d = (c - p).magnitude;
                    if (d > ln.y + margin || (ln.x > 0f && d < ln.x - margin)) continue;
                    float y = SurfaceY(e.x, e.y - 1, t, c, 0f); if (y < below && y > above) return true;
                }
            }
            return false;
        }
        /// <summary>Run counters: is a point on a drawn carriageway or junction patch (carriage = true), or on a pavement, a pedestrian
        /// street or a bike path (carriage = false), at that surface's height (± 0.8 m)? Pedestrian streets and bike paths are never carriageway.
        /// A drive and its turnaround pad are yard space: all of it is walkable (a person crossing a drive's carriageway is on it); a
        /// street's carriageway never is.</summary>
        public static bool OnSurface(Vector3 p, float margin, bool carriage)
        {
            if (drawn == null || sHalf == null) return true;
            var p2 = new Vector2(p.x, p.z); int gx = Mathf.FloorToInt(p.x / SG), gz = Mathf.FloorToInt(p.z / SG);
            for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
            {
                if (!segGrid.TryGetValue(SKey(gx + dx, gz + dz), out var l)) continue;
                foreach (var e in l)
                {
                    if (e.x < 0 && e.y == 1)
                    {
                        if (carriage) continue;
                        if (InRing(padRings[-1 - e.x], p2, margin) && Mathf.Abs(p.y - CityGround.HeightAt(p.x, p.z)) < 1.2f) return true;
                        continue;
                    }
                    if (e.x < 0)
                    {
                        var j = patches[-1 - e.x]; float r = (carriage ? j.rc : j.ro) + margin; if ((j.p - p2).sqrMagnitude > r * r) continue;
                        float yj = float.IsNaN(j.hy) ? CityGround.HeightAt(p.x, p.z) : j.hy; if (Mathf.Abs(p.y - yj) < 1.2f) return true;
                        continue;
                    }
                    var q = drawn[e.x]; Vector2 a = q.P[e.y - 1], ab = q.P[e.y] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-6f) continue;
                    float t = Mathf.Clamp01(Vector2.Dot(p2 - a, ab) / L2); float d = (a + ab * t - p2).magnitude, h = sHalf[e.x], w = sWalk[e.x];
                    bool inBand = carriage ? !q.NoCars && d <= h + margin : (q.NoCars || q.Drive ? d <= h + w + margin : w > 0f && d >= h - margin && d <= h + w + margin);
                    if (!inBand) continue;
                    float y = SurfaceY(e.x, e.y - 1, t, p2, 0f); if (Mathf.Abs(p.y - y) < 0.8f + sLift[e.x]) return true;
                }
            }
            return false;
        }

        /// <summary>The road as it is drawn nearest to p (open in 'year' of scenario 'sc', no ramps), continued at each junction by the
        /// straightest drawn road (turning less than ~55°) until 'reach' metres are added on each side: its centre line, class and
        /// whether it is one carriageway of a dual road (one direction). False until the film roads are built.</summary>
        public static bool DrawnWay(Vector2 p, int year, int sc, float maxD, float reach, out List<Vector2> line, out TwinData.RoadClass cls, out bool oneWay)
        {
            line = null; cls = TwinData.RoadClass.Street; oneWay = false;
            var st = drawn; if (st == null || st.Count == 0) return false;
            bool Open(Stroke q) => !q.Ramp && q.P != null && q.P.Count >= 2 && q.Years[Mathf.Clamp(sc, 0, 3)] <= year;
            int bi = -1; float bd = maxD * maxD;
            for (int i = 0; i < st.Count; i++)
            {
                var q = st[i]; if (!Open(q)) continue;
                for (int j = 0; j + 1 < q.P.Count; j++)
                {
                    var a = q.P[j]; var ab = q.P[j + 1] - a; float L2 = ab.sqrMagnitude; if (L2 < 1e-4f) continue;
                    float d = (a + ab * Mathf.Clamp01(Vector2.Dot(p - a, ab) / L2) - p).sqrMagnitude; if (d < bd) { bd = d; bi = i; }
                }
            }
            if (bi < 0) return false;
            if (drawnAt == null)
            {
                drawnAt = new Dictionary<int, List<int>>();
                for (int i = 0; i < st.Count; i++) foreach (int nd in new[] { st[i].A, st[i].B }) { if (nd < 0) continue; if (!drawnAt.TryGetValue(nd, out var l)) drawnAt[nd] = l = new List<int>(); l.Add(i); }
            }
            var nodes = TwinData.RoadNodes;
            int NodeAt(Stroke q, Vector2 end)
            {
                int best = -1; float b2 = 30f * 30f;
                foreach (int nd in new[] { q.A, q.B }) if (nd >= 0 && nd < nodes.Length) { float d = (nodes[nd] - end).sqrMagnitude; if (d < b2) { b2 = d; best = nd; } }
                return best;
            }
            var pts = new List<Vector2>(st[bi].P); cls = st[bi].Cls; oneWay = st[bi].OneWay;
            for (int pass = 0; pass < 2; pass++)
            {
                if (pass == 1) pts.Reverse();
                int cur = bi; float len = 0f;
                for (int guard = 0; guard < 40 && len < reach; guard++)
                {
                    var end = pts[pts.Count - 1]; var dir = (end - pts[pts.Count - 2]).normalized;
                    int node = NodeAt(st[cur], end); if (node < 0 || !drawnAt.TryGetValue(node, out var list)) break;
                    int nb = -1; float bestDot = 0.58f; bool flip = false;
                    foreach (int k in list)
                    {
                        if (k == cur) continue; var q = st[k]; if (!Open(q) || q.OneWay != oneWay) continue;
                        bool fw = (q.P[0] - end).sqrMagnitude <= (q.P[q.P.Count - 1] - end).sqrMagnitude;
                        var a = fw ? q.P[0] : q.P[q.P.Count - 1]; var b = fw ? q.P[Mathf.Min(2, q.P.Count - 1)] : q.P[Mathf.Max(q.P.Count - 3, 0)];
                        float dot = Vector2.Dot(dir, (b - a).normalized) + (q.Cls == cls ? 0.12f : 0f);
                        if (dot > bestDot) { bestDot = dot; nb = k; flip = !fw; }
                    }
                    if (nb < 0) break;
                    var np = st[nb].P; int n = np.Count;
                    for (int i = 1; i < n; i++) { var v = flip ? np[n - 1 - i] : np[i]; len += Vector2.Distance(pts[pts.Count - 1], v); pts.Add(v); }
                    cur = nb;
                }
            }
            pts.Reverse();                                                       // back in the stroke's own order (a one-way carriageway runs that way)
            line = pts; return true;
        }

        /// <summary>Edges of one class and one opening year that meet at a node of degree 2 are one road: chained into a stroke, resampled
        /// every 8 m and smoothed (a few binomial passes, ends fixed), so the ribbon has no kinks from the vectorised plan and corners of
        /// streets get a kerb radius. Short, curving motorway strokes are ramps (cloverleaf loops, slips) and get a one-lane width.</summary>
        static List<Stroke> Strokes()
        {
            var film = FilmStrokes(); if (film != null) return film;
            var R = TwinData.Roads; int n = R.Length;
            var adj = new Dictionary<int, List<int>>();
            for (int i = 0; i < n; i++)
            {
                if (R[i].Geom == null || R[i].Geom.Length < 2) continue;
                if (!adj.TryGetValue(R[i].A, out var la)) adj[R[i].A] = la = new List<int>(); la.Add(i);
                if (!adj.TryGetValue(R[i].B, out var lb)) adj[R[i].B] = lb = new List<int>(); lb.Add(i);
            }
            int Deg(int node) => adj.TryGetValue(node, out var l) ? l.Count : 0;
            bool Same(int a, int b) => R[a].Cls == R[b].Cls && Y(R[a], 0) == Y(R[b], 0) && Y(R[a], 1) == Y(R[b], 1) && Y(R[a], 2) == Y(R[b], 2) && Y(R[a], 3) == Y(R[b], 3);
            // direction of edge i leaving the node
            Vector2 Out(int i, int node)
            {
                var g = R[i].Geom; Vector2 v = R[i].A == node ? g[1] - g[0] : g[g.Length - 2] - g[g.Length - 1];
                return v.sqrMagnitude > 1e-8f ? v.normalized : v;
            }
            var used = new bool[n]; var res = new List<Stroke>();
            // interchanges (Tools/build_interchanges.py): the plan's scribbled ramps are dropped, clean standard ramps are added
            var ic = LoadInterchanges();
            if (ic != null && ic.edges != null) foreach (var k in ic.edges) if (k >= 0 && k < n) used[k] = true;
            // good continuation: at every node the road goes on along the edge of the same class and year that is most nearly straight
            // ahead (within 30°), so a motorway runs straight through an interchange and its ramps become separate strokes
            int Next(int cur, int node)
            {
                if (!adj.TryGetValue(node, out var l)) return -1;
                Vector2 din = -Out(cur, node); int best = -1; float bd = Mathf.Cos(30f * Mathf.Deg2Rad);
                foreach (var j in l)
                {
                    if (used[j] || !Same(cur, j)) continue;
                    // short pieces of a roundabout turn by 45–60° at each node: they still belong to one ring
                    float lim = R[cur].Len < 90f && R[j].Len < 90f ? 0.42f : bd;
                    float d = Vector2.Dot(din, Out(j, node)); if (d > lim && (best < 0 || d > Vector2.Dot(din, Out(best, node)))) best = j;
                }
                return best;
            }
            for (int i = 0; i < n; i++)
            {
                if (used[i] || R[i].Geom == null || R[i].Geom.Length < 2) continue;
                used[i] = true;
                var pts = new List<Vector2>(R[i].Geom);
                int head = R[i].A, tail = R[i].B, eh = i, et = i;
                for (int side = 0; side < 2; side++)
                {
                    int guard = 0;
                    while (guard++ < 100000)
                    {
                        int node = side == 0 ? tail : head;
                        int cur = Next(side == 0 ? et : eh, node); if (cur < 0) break;
                        used[cur] = true; var g = R[cur].Geom; bool fwd = R[cur].A == node;
                        if (side == 0)
                        {
                            if (fwd) for (int k = 1; k < g.Length; k++) pts.Add(g[k]); else for (int k = g.Length - 2; k >= 0; k--) pts.Add(g[k]);
                            tail = fwd ? R[cur].B : R[cur].A; et = cur;
                        }
                        else
                        {
                            var pre = new List<Vector2>();
                            if (fwd) for (int k = g.Length - 1; k >= 1; k--) pre.Add(g[k]); else for (int k = 0; k < g.Length - 1; k++) pre.Add(g[k]);
                            pts.InsertRange(0, pre); head = fwd ? R[cur].B : R[cur].A; eh = cur;
                        }
                        if (head == tail) break;
                    }
                }
                if (head == tail && pts.Count > 4)
                {
                    // a small closed ring (a roundabout drawn as a polygon by the plan): a true circle through the same centre
                    Vector2 cc = Vector2.zero; foreach (var q in pts) cc += q; cc /= pts.Count;
                    float rr = 0; foreach (var q in pts) rr += (q - cc).magnitude; rr /= pts.Count;
                    if (rr < 110f)
                    {
                        int nseg = Mathf.Max(16, Mathf.CeilToInt(2f * Mathf.PI * rr / 8f));
                        float a0 = Mathf.Atan2(pts[0].y - cc.y, pts[0].x - cc.x); pts.Clear();
                        for (int k = 0; k <= nseg; k++) { float a = a0 + k * Mathf.PI * 2f / nseg; pts.Add(cc + new Vector2(Mathf.Cos(a), Mathf.Sin(a)) * rr); }
                    }
                }
                var rs = Resample(pts, 8f); if (rs.Count < 2) continue;
                float L = 0; for (int k = 1; k < rs.Count; k++) L += (rs[k] - rs[k - 1]).magnitude;
                var st = new Stroke { Cls = R[i].Cls, Years = new Vector4(Y(R[i], 0), Y(R[i], 1), Y(R[i], 2), Y(R[i], 3)), A = head, B = tail, P = rs, Len = L };
                bool fast = st.Cls == TwinData.RoadClass.Highway || st.Cls == TwinData.RoadClass.Ring;
                // stubs of the vectorised plan: a short dead end, or a short motorway piece that meets nothing straight at either end
                if (L < 30f && (Deg(head) == 1 || Deg(tail) == 1)) continue;
                if (fast && L < 35f)
                {
                    bool Aligned(int node, Vector2 d) { foreach (var j in adj[node]) if (j != eh && j != et && Mathf.Abs(Vector2.Dot(Out(j, node), d)) > 0.7f) return true; return false; }
                    Vector2 dd = (rs[rs.Count - 1] - rs[0]).normalized;
                    if (!Aligned(head, dd) && !Aligned(tail, dd)) continue;
                }
                res.Add(st);
            }
            if (ic != null && ic.paths != null)
                foreach (var pth in ic.paths)
                {
                    if (pth.g == null || pth.g.Length < 4) continue;
                    var pts = new List<Vector2>(); for (int i = 0; i + 1 < pth.g.Length; i += 2) pts.Add(new Vector2(pth.g[i], pth.g[i + 1]));
                    var rs = Smooth(Resample(pts, 8f), 2); float Lr = 0; for (int i = 1; i < rs.Count; i++) Lr += (rs[i] - rs[i - 1]).magnitude;
                    var yv = pth.y != null && pth.y.Length >= 4 ? new Vector4(pth.y[0], pth.y[1], pth.y[2], pth.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                    res.Add(new Stroke { Cls = TwinData.RoadClass.Highway, Years = yv, A = -1, B = -1, P = rs, Len = Lr, Ramp = true, Fixed = true });
                }
            // a parallel twin 3–30 m away (same class, another stroke) along most of the length: one carriageway of a dual road
            const float C = 60f; var grid = new Dictionary<long, List<(int s, Vector2 m, Vector2 d)>>();
            long Key(Vector2 p) => ((long)Mathf.FloorToInt(p.x / C) << 32) ^ (uint)Mathf.FloorToInt(p.y / C);
            for (int k = 0; k < res.Count; k++)
            {
                var p = res[k].P;
                for (int i = 1; i < p.Count; i++)
                {
                    Vector2 m = (p[i] + p[i - 1]) * 0.5f, d = (p[i] - p[i - 1]); if (d.sqrMagnitude < 1f) continue; d.Normalize();
                    long key = Key(m); if (!grid.TryGetValue(key, out var l)) grid[key] = l = new List<(int, Vector2, Vector2)>(); l.Add((k, m, d));
                }
            }
            for (int k = 0; k < res.Count; k++)
            {
                var st = res[k]; var p = st.P; int tw = 0, cnt = 0; float maxD = st.Cls == TwinData.RoadClass.Highway ? 30f : 22f;
                if (st.Fixed) continue;
                for (int i = 1; i < p.Count; i += 2)
                {
                    Vector2 m = (p[i] + p[i - 1]) * 0.5f, d = (p[i] - p[i - 1]); if (d.sqrMagnitude < 1f) continue; d.Normalize(); cnt++;
                    bool hit = false;
                    for (int gx = -1; gx <= 1 && !hit; gx++) for (int gz = -1; gz <= 1 && !hit; gz++)
                    {
                        if (!grid.TryGetValue(Key(m + new Vector2(gx * C, gz * C)), out var l)) continue;
                        foreach (var q in l)
                        {
                            if (q.s == k || res[q.s].Cls != st.Cls || Mathf.Abs(Vector2.Dot(q.d, d)) < 0.96f) continue;
                            Vector2 v = q.m - m; float perp = Mathf.Abs(v.x * d.y - v.y * d.x), par = Mathf.Abs(Vector2.Dot(v, d));
                            if (perp > 3f && perp < maxD && par < 12f) { hit = true; break; }
                        }
                    }
                    if (hit) tw++;
                }
                st.OneWay = cnt > 0 && tw > cnt * 0.5f;
                // how sharply it turns: degrees per metre over the whole stroke
                var sm0 = Smooth(p, 3); float turn = 0;
                for (int i = 1; i < sm0.Count - 1; i++) turn += Mathf.Abs(Vector2.SignedAngle(sm0[i] - sm0[i - 1], sm0[i + 1] - sm0[i]));
                bool fast = st.Cls == TwinData.RoadClass.Highway || st.Cls == TwinData.RoadClass.Ring;
                st.Ramp = fast && ((st.Len < 2500f && turn > 35f && turn / Mathf.Max(st.Len, 1f) > 0.03f) || (st.Len < 600f && !st.OneWay));
                int passes = st.Ramp ? 6 : fast ? 10 : st.Cls == TwinData.RoadClass.Main ? 6 : 3;
                st.P = Smooth(p, passes);
            }
            return res;
        }
        // ---------------------------------------------------------------- clean geometry (Tools/build_film_roads.py)
        // Motorways as one smooth dual carriageway per corridor, the nine interchanges as standard cloverleafs, the plan's doubled
        // lines, ramp scribbles and U-turn hairpins removed. k: 0 two-way road, 1 one carriageway of a dual road, 2 ramp.
        // v2 (merge_districts.py): a stroke of the redrawn map carries e = its roads.json edge, t = norms class, h = surface height per point,
        // st = structures [from_m, to_m, code, …], p = profile (roads.json profiles), ic = interchange; strokes of the old data have e = −1.
        [System.Serializable] class FrStroke { public string c; public int k, a, b; public int[] y; public float[] g; public int e = -1, p = -1, ic = -1; public string t; public float[] h, st; }
        [System.Serializable] class FrPad { public int n; public float[] p; public int[] y; public int pl; }
        [System.Serializable] class FrYard { public float[] p; public int[] y; public int b; public float[] d; }        // d: dock side x0 z0 x1 z1 and its doors (none: no bays)
        [System.Serializable] class FrData { public int v; public FrStroke[] s; public int[] drop; public FrPad[] pads; public FrYard[] yards; public int[] sig; public int sigOn; }
        static FrData frCache; static bool frTried; static HashSet<int> frDrop;
        static FrData LoadFilm()
        {
            if (frTried) return frCache; frTried = true;
            var ta = Resources.Load<TextAsset>("Landmarks/film_roads"); if (ta == null) return null;
            try { frCache = JsonUtility.FromJson<FrData>(ta.text); } catch (System.Exception e) { Debug.LogWarning("[Alatau] film roads: " + e.Message); frCache = null; }
            if (frCache != null && (frCache.s == null || frCache.s.Length == 0)) frCache = null;
            if (frCache != null) frDrop = new HashSet<int>(frCache.drop ?? new int[0]);
            return frCache;
        }
        /// <summary>The junctions the redrawn map signals (network nodes of kind crossing_signal: film_roads "sig", roads.json node ids) as
        /// points; null when the data does not say (old data: FilmTraffic keeps its own rule).</summary>
        public static List<Vector2> DataSignals()
        {
            if (dataSig != null || dataSigTried) return dataSig; dataSigTried = true;
            var fr = LoadFilm(); if (fr == null || fr.sigOn == 0) return null;
            var want = new HashSet<int>(fr.sig ?? new int[0]); var at = new Dictionary<int, Vector2>();
            foreach (var f in fr.s)
            {
                if (f.g == null || f.g.Length < 4) continue;
                if (f.a >= 0 && want.Contains(f.a)) at[f.a] = new Vector2(f.g[0], f.g[1]);
                if (f.b >= 0 && want.Contains(f.b)) at[f.b] = new Vector2(f.g[f.g.Length - 2], f.g[f.g.Length - 1]);
            }
            dataSig = new List<Vector2>(at.Values); return dataSig;
        }
        static List<Vector2> dataSig; static bool dataSigTried;
        /// <summary>A plan edge that the clean geometry no longer draws (a motorway piece or a ramp scribble): no street trees along it.</summary>
        public static bool Dropped(int edge) { LoadFilm(); return frDrop != null && frDrop.Contains(edge); }
        /// <summary>Motorway carriageways and interchange ramps of the clean geometry with their half widths (empty without it).</summary>
        public static IEnumerable<(List<Vector2> P, float half)> CleanLines()
        {
            var fr = LoadFilm(); if (fr == null) yield break;
            foreach (var f in fr.s)
            {
                if (f.g == null || f.g.Length < 4 || (f.c != "highway" && f.c != "ring" && f.k != 2)) continue;
                var pts = new List<Vector2>(f.g.Length / 2); for (int i = 0; i + 1 < f.g.Length; i += 2) pts.Add(new Vector2(f.g[i], f.g[i + 1]));
                yield return (pts, f.k == 2 ? 4f : 6f);
            }
        }
        static List<Stroke> FilmStrokes()
        {
            var fr = LoadFilm(); if (fr == null) return null;
            var res = new List<Stroke>(fr.s.Length);
            foreach (var f in fr.s)
            {
                if (f.g == null || f.g.Length < 4) continue;
                var pts = new List<Vector2>(f.g.Length / 2); for (int i = 0; i + 1 < f.g.Length; i += 2) pts.Add(new Vector2(f.g[i], f.g[i + 1]));
                var cls = f.c == "highway" ? TwinData.RoadClass.Highway : f.c == "ring" ? TwinData.RoadClass.Ring : f.c == "main" ? TwinData.RoadClass.Main : TwinData.RoadClass.Street;
                var yv = f.y != null && f.y.Length >= 4 ? new Vector4(f.y[0], f.y[1], f.y[2], f.y[3]) : new Vector4(2025, 2025, 2025, 2025);
                float L = 0; for (int i = 1; i < pts.Count; i++) L += (pts[i] - pts[i - 1]).magnitude;
                // junction ids: plan nodes; strokes cut by the cleaning have -1 and get a private id (no patch)
                var st = new Stroke { Cls = cls, Years = yv, A = f.a >= 0 ? f.a : -1000000 - res.Count * 2, B = f.b >= 0 ? f.b : -1000001 - res.Count * 2,
                    P = pts, Len = L, Ramp = f.k == 2, OneWay = f.k == 1, Fixed = true };
                if (fr.v >= 2 && f.e >= 0)
                {
                    st.Edge = f.e; st.Kind = string.IsNullOrEmpty(f.t) ? null : f.t; st.Prof = f.p; st.Ic = f.ic;
                    st.H = f.h != null && f.h.Length == pts.Count ? f.h : null; st.St = f.st != null && f.st.Length >= 3 ? f.st : null;
                    ApplyProfile(st); st.Prof0 = f.p;
                    if (f.e < TwinData.Roads.Length && TwinData.Roads[f.e].PsP != null && st.PHalf >= 0f) Stages(st, TwinData.Roads[f.e]);
                }
                res.Add(st);
            }
            DropStubs(res);
            return res;
        }

        /// <summary>Stubs of the vectorised plan: a short piece (under 80 m, not a ramp) with an end that touches no other road within 16 m
        /// ends in a field. Such pieces are not drawn (the survey found ≈55 of them, mostly streets).</summary>
        static void DropStubs(List<Stroke> res)
        {
            const float Cell = 32f, Near = 16f;
            var grid = new Dictionary<long, List<int>>();
            long Key(int gx, int gz) => ((long)gx << 32) ^ (uint)gz;
            for (int k = 0; k < res.Count; k++)
                foreach (var p in res[k].P)
                {
                    long key = Key(Mathf.FloorToInt(p.x / Cell), Mathf.FloorToInt(p.y / Cell));
                    if (!grid.TryGetValue(key, out var l)) grid[key] = l = new List<int>();
                    if (l.Count == 0 || l[l.Count - 1] != k) l.Add(k);
                }
            bool Touches(int self, Vector2 e)
            {
                int gx = Mathf.FloorToInt(e.x / Cell), gz = Mathf.FloorToInt(e.y / Cell);
                for (int dx = -1; dx <= 1; dx++) for (int dz = -1; dz <= 1; dz++)
                {
                    if (!grid.TryGetValue(Key(gx + dx, gz + dz), out var l)) continue;
                    foreach (int j in l)
                    {
                        if (j == self) continue; var q = res[j].P;
                        for (int i = 0; i + 1 < q.Count; i++)
                        {
                            var a = q[i]; var ab = q[i + 1] - a; float L2 = ab.sqrMagnitude;
                            var c = L2 < 1e-6f ? a : a + ab * Mathf.Clamp01(Vector2.Dot(e - a, ab) / L2);
                            if ((c - e).sqrMagnitude < Near * Near) return true;
                        }
                    }
                }
                return false;
            }
            var drop = new List<int>();
            for (int k = 0; k < res.Count; k++)
            {
                var s = res[k]; if (s.Ramp || s.Len >= 80f || s.P.Count < 2 || s.Edge >= 0) continue;     // the redrawn map has no stubs
                if (!Touches(k, s.P[0]) || !Touches(k, s.P[s.P.Count - 1])) drop.Add(k);
            }
            for (int i = drop.Count - 1; i >= 0; i--) res.RemoveAt(drop[i]);
            if (drop.Count > 0) Debug.Log("[Alatau] film roads: " + drop.Count + " dead-end stubs of the plan not drawn");
        }

        [System.Serializable] class IcPath { public int[] y; public float[] g; }
        [System.Serializable] class IcData { public int[] edges; public IcPath[] paths; }
        static IcData icCache;
        static IcData LoadInterchanges()
        {
            if (icCache != null) return icCache;
            var ta = Resources.Load<TextAsset>("Landmarks/interchanges"); if (ta == null) return null;
            try { icCache = JsonUtility.FromJson<IcData>(ta.text); } catch (System.Exception e) { Debug.LogWarning("[Alatau] interchanges: " + e.Message); }
            return icCache;
        }
        static Vector4[] icZones; static int icCount = -1;
        /// <summary>Inside a motorway interchange: the land between the ramps is a verge with a few trees, not a park or yards.</summary>
        public static bool InInterchange(float x, float z)
        {
            if (icCount < 0) PublishZones();
            for (int i = 0; i < icCount; i++) { var c = icZones[i]; float dx = x - c.x, dz = z - c.y; if (dx * dx + dz * dz < c.z * c.z) return true; }
            return false;
        }
        /// <summary>Interchange zones (x, z, radius): the ground inside is a mown verge, not city yards (AlatauGround reads _AlatauIcZones).</summary>
        public static void PublishZones()
        {
            var ta = Resources.Load<TextAsset>("Landmarks/film_roads"); if (ta == null) ta = Resources.Load<TextAsset>("Landmarks/interchanges");
            var v = new Vector4[32]; int n = 0;
            if (ta != null)
            {
                // "zones":[[x,z,r,y],...] — JsonUtility cannot read nested arrays, so a tiny parse
                int i0 = ta.text.IndexOf("\"zones\":[");
                if (i0 >= 0)
                {
                    int i = i0 + 9;
                    while (n < 32)
                    {
                        int a = ta.text.IndexOf('[', i); if (a < 0) break; int b = ta.text.IndexOf(']', a); if (b < 0) break;
                        var parts = ta.text.Substring(a + 1, b - a - 1).Split(',');
                        if (parts.Length >= 3 && float.TryParse(parts[0], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float x)
                            && float.TryParse(parts[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float z)
                            && float.TryParse(parts[2], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float r))
                            v[n++] = new Vector4(x, z, r, parts.Length > 3 && float.TryParse(parts[3], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float y) ? y : 2025f);
                        i = b + 1; if (i < ta.text.Length && ta.text[i] == ']') break;
                        if (i + 1 < ta.text.Length && ta.text[i] == ',' && ta.text[i + 1] != '[') break;
                    }
                }
            }
            Shader.SetGlobalVectorArray("_AlatauIcZones", v); Shader.SetGlobalFloat("_AlatauIcCount", n);
            icZones = v; icCount = n;
        }

        /// <summary>Square tiles (m) the road meshes are laid in (Build).</summary>
        const float MeshTile = 3000f;
        static long TileKey(Vector2 p) => ((long)Mathf.FloorToInt(p.x / MeshTile) << 32) ^ (uint)Mathf.FloorToInt(p.y / MeshTile);
        static Vector2 TileAt(Stroke s) => s.P != null && s.P.Count > 0 ? s.P[s.P.Count / 2] : Vector2.zero;
        static List<T> Sorted<T>(T[] items, System.Func<T, float[]> pts)
        {
            var l = new List<T>(items);
            l.Sort((a, b) => Key(a).CompareTo(Key(b)));
            return l;
            long Key(T x) { var p = pts(x); return p != null && p.Length >= 2 ? TileKey(new Vector2(p[0], p[1])) : 0L; }
        }

        static List<Vector2> Resample(List<Vector2> p, float step)
        {
            var o = new List<Vector2> { p[0] }; float acc = 0;
            for (int i = 1; i < p.Count; i++)
            {
                Vector2 a = p[i - 1], b = p[i]; float d = (b - a).magnitude; if (d < 1e-4f) continue;
                float t = step - acc;
                while (t <= d) { o.Add(Vector2.Lerp(a, b, t / d)); t += step; }
                acc = d - (t - step);
            }
            if ((o[o.Count - 1] - p[p.Count - 1]).magnitude > 0.5f) o.Add(p[p.Count - 1]); else o[o.Count - 1] = p[p.Count - 1];
            return o;
        }
        static List<Vector2> Smooth(List<Vector2> p, int passes)
        {
            var a = new List<Vector2>(p); var b = new List<Vector2>(p);
            for (int k = 0; k < passes; k++)
            {
                for (int i = 1; i < a.Count - 1; i++) b[i] = (a[i - 1] + 2f * a[i] + a[i + 1]) * 0.25f;
                var t = a; a = b; b = t; b[0] = a[0]; b[b.Count - 1] = a[a.Count - 1];
            }
            return a;
        }

        static float Y(TwinData.RoadEdge e, int s) => e.Year != null && e.Year.Length > 0 ? e.Year[Mathf.Min(s, e.Year.Length - 1)] : 2025;
    }
}
