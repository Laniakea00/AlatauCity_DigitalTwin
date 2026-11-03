using System;
using System.Collections.Generic;
using UnityEngine;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The new railway lines of the map data in 3D (Resources/Landmarks/rail.json, merge_districts from the spec `rail` block,
    /// CONTRACT Gate v1.2): each track at its rail head heights (points every ≤ 10 m) with its two rails, concrete sleepers every
    /// 0.6 m and a ballast bed in the colour the film gives the existing railways (the Turksib bed, AlatauLit); under the tracks the
    /// viaduct deck (underside = rail head − 1.8 m) with a parapet on its outer edge, and where that underside stands more than 1 m
    /// over the ground a pier every 30 m (moved along the track off a carriageway or a building, else left out: a longer span);
    /// buffer stops at the line's dead end; the platforms (their ring at their surface height) with an edge strip, the yellow safety
    /// line on the track side, a glass railing on the other sides, a canopy on posts and its lights. Everything shows from the line's
    /// (or the platform's) year in the scenario shown. No file or no lines: nothing.</summary>
    public class RailLayer : MonoBehaviour
    {
        public static RailLayer Instance;

        [Serializable] class TrackJ { public string id, side; public float[] p; }
        [Serializable] class LineJ { public string id, name; public int gauge; public int[] y; public TrackJ[] tracks; public float[] ends, joints; }
        [Serializable] class PlatJ { public string id, line, track; public float y; public int[] yr; public float[] p; }
        [Serializable] class RailJ { public int v; public LineJ[] lines; public PlatJ[] platforms; }

        class Part { public GameObject Go; public int[] Years; }
        readonly List<Part> parts = new List<Part>();
        Material mat; bool built; int lastYear = -1; Scenario lastSc = (Scenario)(-1); float waitFrom = -1f;

        const float Sleeper = 0.6f, DeckBelow = 1.8f, DeckTop = 0.85f, Bed = 0.38f, OuterHalf = 2.6f, PierStep = 30f;
        static readonly Color32 Conc = LM.C("#cfcbc3"), ConcD = LM.C("#aaa59c"), Ballast = LM.C("#5c574f"), SleeperC = LM.C("#8f8b84"),
            RailC = LM.C("#4b5057"), Paving = LM.C("#c9c4ba"), EdgeC = LM.C("#e4e2dc"), Yellow = LM.C("#e3b51c"), Roof = LM.C("#8f9499"),
            Soffit = LM.C("#d8d6d0"), White = LM.C("#ecebe6"), Glass = LM.C("#2a4256"), Lamp = LM.C("#fff1d6"), Red = LM.C("#c8312a");

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Railway (tracks, viaduct, platforms)").AddComponent<RailLayer>(); }
        void Awake() { Instance = this; }
        void Start() { TryBuild(); }

        void TryBuild()
        {
            if (built) return;
            if (!TwinData.Ready || CityGround.HeightAt(0, 0) == 0f) { Invoke(nameof(TryBuild), 0.3f); return; }
            // the piers keep off the carriageways the film roads draw: wait for them (at most 20 s, then without that test)
            if (waitFrom < 0f) waitFrom = Time.realtimeSinceStartup;
            if (!FilmRoads.Ready && Time.realtimeSinceStartup - waitFrom < 20f) { Invoke(nameof(TryBuild), 0.5f); return; }
            built = true;
            var ta = Resources.Load<TextAsset>("Landmarks/rail"); if (ta == null) return;
            RailJ rj = null; try { rj = JsonUtility.FromJson<RailJ>(ta.text); } catch (Exception ex) { Debug.LogWarning("[Alatau] railway: rail.json unreadable: " + ex.Message); }
            if (rj == null || ((rj.lines == null || rj.lines.Length == 0) && (rj.platforms == null || rj.platforms.Length == 0))) return;
            var sh = Shader.Find("AlatauCity/Landmark"); if (sh == null) { Debug.LogWarning("[Alatau] railway: shader AlatauCity/Landmark missing"); return; }
            mat = new Material(sh) { name = "Railway" };
            int nTracks = 0, nPiers = 0, nMoved = 0, nSkipped = 0, nStops = 0; float km = 0f;
            var lineTracks = new Dictionary<string, List<Vector3[]>>();
            if (rj.lines != null)
                foreach (var L in rj.lines)
                {
                    if (L?.tracks == null || L.y == null || L.y.Length < 4) continue;
                    var T = new List<Vector3[]>();
                    foreach (var t in L.tracks) { var P = Pts(t.p); if (P.Length >= 2) T.Add(P); }
                    if (T.Count == 0) continue;
                    lineTracks[L.id ?? ""] = T;
                    var k = new LandmarkKit(); var pk = new LandmarkKit();
                    for (int ti = 0; ti < T.Count; ti++)
                    {
                        var other = T.Count > 1 ? T[ti == 0 ? 1 : 0] : null;
                        Track(k, pk, T[ti], other, ref nPiers, ref nMoved, ref nSkipped); nTracks++;
                        for (int i = 1; i < T[ti].Length; i++) km += Flat(T[ti][i] - T[ti][i - 1]) / 1000f;
                    }
                    if (L.ends != null)
                        for (int e = 0; e + 1 < L.ends.Length; e += 2) nStops += BufferStops(k, T, new Vector2(L.ends[e], L.ends[e + 1]));
                    // the district edge where the line goes on in the plan but the map draws nothing beyond yet: the deck ends on an
                    // abutment down to the ground, with buffer stops, instead of stopping in the air
                    if (L.joints != null)
                        for (int e = 0; e + 1 < L.joints.Length; e += 2)
                        {
                            var j = new Vector2(L.joints[e], L.joints[e + 1]);
                            bool goesOn = false;                                     // another line of the file starts there
                            foreach (var L2 in rj.lines)
                                if (L2 != L && L2?.tracks != null)
                                    foreach (var t2 in L2.tracks)
                                        if (t2?.p != null && t2.p.Length >= 6 && (Mathf.Min((new Vector2(t2.p[0], t2.p[1]) - j).magnitude,
                                            (new Vector2(t2.p[t2.p.Length - 3], t2.p[t2.p.Length - 2]) - j).magnitude) < 30f)) goesOn = true;      // file: x, z, y
                            if (!goesOn && Abutments(pk, T, j) > 0) nStops += BufferStops(k, T, j);
                        }
                    Add(k.ToMesh("Railway " + L.id), L.y, "Railway · " + L.name);
                    Add(pk.ToMesh("Railway piers " + L.id), L.y, "Railway piers · " + L.name);
                }
            int nPlat = 0;
            if (rj.platforms != null)
                foreach (var P in rj.platforms)
                {
                    if (P?.p == null || P.p.Length < 6 || P.yr == null || P.yr.Length < 4) continue;
                    lineTracks.TryGetValue(P.line ?? "", out var T);
                    var k = new LandmarkKit(); Platform(k, P, T); nPlat++;
                    Add(k.ToMesh("Railway platform " + P.id), P.yr, "Railway platform · " + P.id);
                }
            Debug.Log($"[Alatau] railway: {rj.lines?.Length ?? 0} lines, {nTracks} tracks ({km:0.00} km), {nPiers} piers ({nMoved} moved off a road or a building, " +
                      $"{nSkipped} left out: a longer span), {nStops} buffer stops, {nPlat} platforms{(FilmRoads.Ready ? "" : " (film roads not ready: piers placed without the road test)")}");
            lastYear = -1;
        }

        static Vector3[] Pts(float[] p)
        {
            if (p == null) return new Vector3[0];
            var r = new Vector3[p.Length / 3];
            for (int i = 0; i < r.Length; i++) r[i] = new Vector3(p[i * 3], p[i * 3 + 2], p[i * 3 + 1]);       // file: x, z, rail head y
            return r;
        }
        static float Flat(Vector3 d) => Mathf.Sqrt(d.x * d.x + d.z * d.z);
        static Vector3 Side(Vector3[] P, int i)
        {
            int n = P.Length; Vector3 a = i > 0 ? P[i] - P[i - 1] : P[1] - P[0], b = i < n - 1 ? P[i + 1] - P[i] : a; a.y = b.y = 0f;
            return (Vector3.Cross(Vector3.up, a.normalized) + Vector3.Cross(Vector3.up, b.normalized)).normalized;
        }
        /// <summary>The point of polyline Q nearest to p (horizontal).</summary>
        static Vector3 Nearest(Vector3[] Q, Vector3 p)
        {
            Vector3 best = Q[0]; float bd = float.MaxValue; var p2 = new Vector2(p.x, p.z);
            for (int i = 1; i < Q.Length; i++)
            {
                Vector2 a = new Vector2(Q[i - 1].x, Q[i - 1].z), b = new Vector2(Q[i].x, Q[i].z), ab = b - a; float L2 = ab.sqrMagnitude;
                float t = L2 > 1e-6f ? Mathf.Clamp01(Vector2.Dot(p2 - a, ab) / L2) : 0f; var q = a + ab * t; float d = (q - p2).sqrMagnitude;
                if (d < bd) { bd = d; best = Vector3.Lerp(Q[i - 1], Q[i], t); }
            }
            return best;
        }

        // ------------------------------------------------------------------ a track on its viaduct
        static void Track(LandmarkKit k, LandmarkKit pk, Vector3[] P, Vector3[] other, ref int nPiers, ref int nMoved, ref int nSkipped)
        {
            int n = P.Length; var s = new Vector3[n]; var inner = new float[n]; var S = new float[n];
            for (int i = 0; i < n; i++)
            {
                s[i] = Side(P, i);
                if (i > 0) S[i] = S[i - 1] + Flat(P[i] - P[i - 1]);
                if (other != null)
                {
                    // the outward side is away from the other track; the deck halves meet half way between the tracks
                    var q = Nearest(other, P[i]); var d = P[i] - q; d.y = 0f; float dist = d.magnitude;
                    if (Vector3.Dot(s[i], d) < 0f) s[i] = -s[i];
                    inner[i] = Mathf.Clamp(dist * 0.5f, 1.6f, OuterHalf);
                }
                else inner[i] = OuterHalf;
            }
            var up = Vector3.up;
            for (int i = 0; i < n - 1; i++)
            {
                Vector3 p0 = P[i], p1 = P[i + 1], s0 = s[i], s1 = s[i + 1]; float u0 = S[i], u1 = S[i + 1];
                // deck: top (concrete), soffit, outer face; the inner face only on a single track
                Vector3 a = p0 - s0 * inner[i], b = p0 + s0 * OuterHalf, c = p1 + s1 * OuterHalf, d = p1 - s1 * inner[i + 1];
                Vector3 top = up * -DeckTop, bot = up * -DeckBelow;
                k.Quad(a + top, b + top, c + top, d + top, up, Conc, LM.Paving, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
                k.Quad(a + bot, b + bot, c + bot, d + bot, -up, ConcD, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u0, 5f), new Vector2(u1, 5f), new Vector2(u1, 0));
                k.Quad(b + bot, c + bot, c + up * 1.1f + top, b + up * 1.1f + top, s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 2.05f), new Vector2(u0, 2.05f));
                if (other == null) k.Quad(a + bot, d + bot, d + top, a + top, -s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 0.95f), new Vector2(u0, 0.95f));
                // parapet on the outer edge (0.25 m thick, 1.1 m over the deck)
                Vector3 b2 = p0 + s0 * (OuterHalf - 0.25f), c2 = p1 + s1 * (OuterHalf - 0.25f);
                k.Quad(b2 + top, c2 + top, c2 + top + up * 1.1f, b2 + top + up * 1.1f, -s0, Conc, LM.Solid, 3f, new Vector2(u0, 0), new Vector2(u1, 0), new Vector2(u1, 1.1f), new Vector2(u0, 1.1f));
                k.Quad(b2 + top + up * 1.1f, c2 + top + up * 1.1f, c + top + up * 1.1f, b + top + up * 1.1f, up, Conc, LM.Solid, 3f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
                // ballast bed: 3.6 m top at the sleepers' foot, shoulders down to the deck
                Vector3 bed = up * -Bed;
                Strip(k, p0 + bed, p1 + bed, s0, s1, -1.8f, 1.8f, Ballast);
                foreach (float sg in new[] { -1f, 1f })
                {
                    Vector3 e0 = p0 + bed + s0 * (1.8f * sg), e1 = p1 + bed + s1 * (1.8f * sg), f0 = p0 + top + s0 * (2.3f * sg), f1 = p1 + top + s1 * (2.3f * sg);
                    k.Quad(e0, e1, f1, f0, s0 * sg + up, Ballast, LM.Roof, 1f, new Vector2(e0.x, e0.z), new Vector2(e1.x, e1.z), new Vector2(f1.x, f1.z), new Vector2(f0.x, f0.z));
                }
                // rails: two heads on the sleepers (1520 mm gauge: centres 0.797 m off the axis), 0.075 × 0.16 m
                foreach (float sg in new[] { -0.797f, 0.797f })
                    k.Beam(p0 + s0 * sg + up * -0.08f, p1 + s1 * sg + up * -0.08f, 0.075f, 0.16f, RailC, LM.Steel);
            }
            // the deck's ends (the buffer stop end, the area edge where the line goes on): a concrete face over its cross-section
            foreach (int e in new[] { 0, n - 1 })
            {
                Vector3 p = P[e], sd = s[e], fw = e == 0 ? P[0] - P[1] : P[n - 1] - P[n - 2]; fw.y = 0f; fw.Normalize();
                Vector3 a = p - sd * inner[e] + up * -DeckBelow, b = p + sd * OuterHalf + up * -DeckBelow;
                Vector3 h = up * (DeckBelow - DeckTop), b2 = p + sd * (OuterHalf - 0.25f) + up * -DeckTop;
                k.Quad(a, b, b + h, a + h, fw, Conc, LM.Solid, 3f, Vector2.zero, new Vector2(5f, 0f), new Vector2(5f, 0.95f), new Vector2(0f, 0.95f));
                k.Quad(b2, b + h, b + h + up * 1.1f, b2 + up * 1.1f, fw, Conc, LM.Solid, 3f, Vector2.zero, new Vector2(0.25f, 0f), new Vector2(0.25f, 1.1f), new Vector2(0f, 1.1f));
            }
            // concrete sleepers every 0.6 m along the track: 2.7 × 0.28 m, 0.2 m deep, top at the rails' foot
            for (float u = Sleeper * 0.5f; u < S[n - 1]; u += Sleeper)
            {
                int i = Array.BinarySearch(S, u); if (i < 0) i = ~i - 1; i = Mathf.Clamp(i, 0, n - 2);
                float t = (u - S[i]) / Mathf.Max(S[i + 1] - S[i], 1e-3f);
                var c = Vector3.Lerp(P[i], P[i + 1], t) + up * -0.18f; var sd = Vector3.Lerp(s[i], s[i + 1], t).normalized; var fw = Vector3.Cross(sd, up).normalized * 0.14f;
                Vector3 a = c - sd * 1.35f - fw, b = c + sd * 1.35f - fw, cc = c + sd * 1.35f + fw, d = c - sd * 1.35f + fw, dn = up * -0.2f;
                k.Quad(a, b, cc, d, up, SleeperC, LM.Solid, 1f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
                k.Quad(a, b, b + dn, a + dn, -fw, SleeperC, LM.Solid, 1f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
                k.Quad(d, cc, cc + dn, d + dn, fw, SleeperC, LM.Solid, 1f, Vector2.zero, Vector2.right, Vector2.one, Vector2.up);
            }
            // piers: every PierStep m where the underside is more than 1 m over the ground, off the carriageways and the buildings
            bool roads = FilmRoads.Ready;
            for (float u = PierStep * 0.5f; u < S[n - 1] - 4f; u += PierStep)
            {
                bool placed = false;
                for (int tryk = 0; tryk < 9 && !placed; tryk++)
                {
                    float du = (tryk + 1) / 2 * 3f * (tryk % 2 == 0 ? 1f : -1f), w = Mathf.Clamp(u + du, 0f, S[n - 1]);
                    int i = 0; while (i < n - 2 && S[i + 1] < w) i++;
                    float t = (w - S[i]) / Mathf.Max(S[i + 1] - S[i], 1e-3f);
                    var p = Vector3.Lerp(P[i], P[i + 1], t); var sd = Vector3.Lerp(s[i], s[i + 1], t).normalized;
                    float g = CityGround.HeightAt(p.x, p.z), under = p.y - DeckBelow;
                    if (under - g < 1f) { placed = true; break; }                        // on the ground here: no pier wanted
                    var foot = new Vector3(p.x, g, p.z);
                    if (roads && FilmRoads.OnSurface(foot + up * 0.1f, 1.0f, true)) continue;
                    if (BuildingUnder(foot, under)) continue;
                    pk.Beam(new Vector3(p.x, g - 1.0f, p.z), new Vector3(p.x, under - 0.9f, p.z), 1.6f, 1.6f, ConcD, LM.Solid);
                    float inn = Mathf.Lerp(inner[i], inner[i + 1], t);
                    pk.Beam(p - sd * inn + up * (-DeckBelow - 0.45f), p + sd * OuterHalf + up * (-DeckBelow - 0.45f), 1.6f, 0.9f, ConcD, LM.Solid);
                    nPiers++; if (tryk > 0) nMoved++; placed = true;
                }
                if (!placed) nSkipped++;
            }
        }
        /// <summary>A building stands under the deck at the foot (a ray from just under the deck hits a building chunk above the ground).</summary>
        static bool BuildingUnder(Vector3 foot, float under)
        {
            if (!Physics.Raycast(new Vector3(foot.x, under - 0.2f, foot.z), Vector3.down, out var hit, under - foot.y + 2f, ~0, QueryTriggerInteraction.Ignore)) return false;
            return hit.point.y > foot.y + 1.0f && hit.collider.GetComponent<BuildingChunk>() != null;
        }
        static void Strip(LandmarkKit k, Vector3 p0, Vector3 p1, Vector3 s0, Vector3 s1, float o0, float o1, Color32 col)
        {
            Vector3 a = p0 + s0 * o0, b = p0 + s0 * o1, c = p1 + s1 * o1, d = p1 + s1 * o0;
            k.Quad(a, b, c, d, Vector3.up, col, LM.Roof, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));
        }

        /// <summary>At a joint e the line reaches with nothing beyond: under each track end within 30 m whose deck stands over the
        /// ground, a concrete abutment wall from the ground to the deck's underside (6 m wide across, 3 m along). Returns how many.</summary>
        static int Abutments(LandmarkKit k, List<Vector3[]> T, Vector2 e)
        {
            int n = 0;
            foreach (var P in T)
            {
                int m = P.Length; bool first = (new Vector2(P[0].x, P[0].z) - e).sqrMagnitude < (new Vector2(P[m - 1].x, P[m - 1].z) - e).sqrMagnitude;
                var p = first ? P[0] : P[m - 1]; var q = first ? P[1] : P[m - 2];
                if ((new Vector2(p.x, p.z) - e).magnitude > 30f) continue;
                var d = p - q; d.y = 0f; if (d.sqrMagnitude < 1e-4f) continue; d.Normalize();
                var c = p - d * 1.5f; float gy = CityGround.HeightAt(c.x, c.z), top = p.y - DeckBelow;
                if (top - gy < 1f) continue;
                float yaw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg;
                k.Box(new Vector3(c.x, (gy - 1f + top) * 0.5f, c.z), new Vector3(6f, top - gy + 1f, 3f), yaw, ConcD, LM.Solid, 3f, Conc, LM.Solid);
                n++;
            }
            return n;
        }

        /// <summary>Buffer stops at the end of each track nearest to the line's dead end e (within 30 m): a red beam on two struts
        /// over the rails, its red lamp on top.</summary>
        static int BufferStops(LandmarkKit k, List<Vector3[]> T, Vector2 e)
        {
            int n = 0;
            foreach (var P in T)
            {
                int m = P.Length; bool first = (new Vector2(P[0].x, P[0].z) - e).sqrMagnitude < (new Vector2(P[m - 1].x, P[m - 1].z) - e).sqrMagnitude;
                var p = first ? P[0] : P[m - 1]; var q = first ? P[1] : P[m - 2];
                if ((new Vector2(p.x, p.z) - e).magnitude > 30f) continue;
                var d = p - q; d.y = 0f; if (d.sqrMagnitude < 1e-4f) continue; d.Normalize(); var s = Vector3.Cross(Vector3.up, d); var up = Vector3.up;
                var c = p - d * 2.5f;
                k.Beam(c - s * 1.2f + up * 0.75f, c + s * 1.2f + up * 0.75f, 0.5f, 0.7f, Red, LM.Solid);
                foreach (float o in new[] { -0.797f, 0.797f }) k.Beam(c + s * o + up * 0.6f, c - d * 3.0f + s * o + up * 0.05f, 0.2f, 0.22f, RailC, LM.Steel);
                k.Beam(c + up * 1.1f, c + up * 1.4f, 0.28f, 0.28f, LM.C("#ff2a1a"), LM.Light);
                n++;
            }
            return n;
        }

        // ------------------------------------------------------------------ a platform
        void Platform(LandmarkKit k, PlatJ P, List<Vector3[]> T)
        {
            var ring = new List<Vector2>(); for (int i = 0; i + 1 < P.p.Length; i += 2) ring.Add(new Vector2(P.p[i], P.p[i + 1]));
            int m = ring.Count; float y = P.y; var up = Vector3.up;
            k.Prism(ring, y - 0.6f, y, Conc, LM.Solid, 3f, Paving, LM.Paving);
            // the track side: the edge whose middle lies nearest to the platform's track (any track of its line)
            int te = 0; float best = float.MaxValue;
            for (int i = 0; i < m; i++)
            {
                var mid = (ring[i] + ring[(i + 1) % m]) * 0.5f; var mp = new Vector3(mid.x, y, mid.y);
                float dmin = float.MaxValue;
                if (T != null) foreach (var tr in T) dmin = Mathf.Min(dmin, Flat(Nearest(tr, mp) - mp));
                else dmin = i;                                                            // no track: the first edge
                if (dmin < best) { best = dmin; te = i; }
            }
            Vector2 A = ring[te], B = ring[(te + 1) % m], ax = (B - A).normalized, inw = new Vector2(-ax.y, ax.x);
            var cen = Vector2.zero; foreach (var q in ring) cen += q; cen /= m;
            if (Vector2.Dot(cen - A, inw) < 0f) inw = -inw;
            float len = (B - A).magnitude, width = 0f; foreach (var q in ring) width = Mathf.Max(width, Vector2.Dot(q - A, inw));
            Vector3 W(float along, float acr, float h) { var q = A + ax * along + inw * acr; return new Vector3(q.x, y + h, q.y); }
            // the edge strip (0.3 m, pale) and the yellow safety line 0.55–0.75 m in from the edge
            Band(k, W(0f, 0f, 0.01f), W(len, 0f, 0.01f), W(len, 0.3f, 0.01f), W(0f, 0.3f, 0.01f), EdgeC);
            Band(k, W(0f, 0.55f, 0.012f), W(len, 0.55f, 0.012f), W(len, 0.75f, 0.012f), W(0f, 0.75f, 0.012f), Yellow);
            // glass railing 1.1 m on the other edges
            for (int i = 0; i < m; i++)
            {
                if (i == te) continue;
                Vector2 a = ring[i], b = ring[(i + 1) % m]; var mo = (a + b) * 0.5f - cen;
                Vector3 a3 = new Vector3(a.x, y, a.y), b3 = new Vector3(b.x, y, b.y);
                k.Quad(a3, b3, b3 + up * 1.1f, a3 + up * 1.1f, new Vector3(mo.x, 0f, mo.y), Glass, LM.Glass, 1.5f, Vector2.zero, new Vector2((b - a).magnitude, 0f), new Vector2((b - a).magnitude, 1.1f), new Vector2(0f, 1.1f));
                k.Beam(a3 + up * 1.12f, b3 + up * 1.12f, 0.08f, 0.06f, White, LM.Metal);
            }
            // canopy: 2 m in from each end, over the middle 6 m of the width (0.3 m back from the centre), roof 3.6 m up on posts every
            // 12 m, a strip light under it every 6 m
            float c0 = Mathf.Min(2f, len * 0.1f), c1 = len - c0, mid2 = width * 0.5f + 0.3f, hw = Mathf.Min(3f, width * 0.5f - 0.3f);
            if (c1 - c0 > 4f && hw > 1f)
            {
                var fp = new List<Vector2>(); foreach (var q in new[] { W(c0, mid2 - hw, 0), W(c1, mid2 - hw, 0), W(c1, mid2 + hw, 0), W(c0, mid2 + hw, 0) }) fp.Add(new Vector2(q.x, q.z));
                k.Prism(fp, y + 3.6f, y + 3.85f, Soffit, LM.Metal, 3f, Roof, LM.Roof, true);
                int np = Mathf.Max(2, Mathf.RoundToInt((c1 - c0 - 2f) / 12f) + 1);
                for (int i = 0; i < np; i++)
                {
                    float a = Mathf.Lerp(c0 + 1f, c1 - 1f, i / (float)(np - 1));
                    k.Beam(W(a, mid2, 0f), W(a, mid2, 3.6f), 0.3f, 0.3f, White, LM.Metal);
                }
                for (float a = c0 + 3f; a < c1 - 2f; a += 6f)
                    k.Box(W(a, mid2 - hw * 0.45f, 3.5f), new Vector3(0.15f, 0.08f, 1.2f), Mathf.Atan2(ax.x, ax.y) * Mathf.Rad2Deg, Lamp, LM.Light, 1f, Lamp, LM.Light);
            }
            // columns under it to the ground every 12 m along its back half (inside the hall under it, if one stands there)
            for (float a = 1.5f; a < len - 1f; a += 12f)
            {
                var top = W(a, width * 0.65f, -0.6f); float g = CityGround.HeightAt(top.x, top.z);
                if (top.y - g > 1.5f) k.Beam(new Vector3(top.x, g - 0.5f, top.z), top, 0.7f, 0.7f, ConcD, LM.Solid);
            }
        }
        static void Band(LandmarkKit k, Vector3 a, Vector3 b, Vector3 c, Vector3 d, Color32 col)
            => k.Quad(a, b, c, d, Vector3.up, col, LM.Paving, 1f, new Vector2(a.x, a.z), new Vector2(b.x, b.z), new Vector2(c.x, c.z), new Vector2(d.x, d.z));

        void Add(Mesh m, int[] years, string name)
        {
            if (m.vertexCount == 0) { Destroy(m); return; }
            var go = new GameObject(name); go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = m; var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = mat;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On;
            parts.Add(new Part { Go = go, Years = years });
        }

        // ------------------------------------------------------------------ year and scenario
        void Update()
        {
            if (!built || parts.Count == 0) return;
            int y = TwinState.Year < 1 ? 2050 : TwinState.Year;
            if (y == lastYear && TwinState.Scenario == lastSc) return;
            lastYear = y; lastSc = TwinState.Scenario; int sc = Mathf.Clamp((int)TwinState.Scenario, 0, 3);
            foreach (var p in parts) p.Go.SetActive(y >= p.Years[Mathf.Min(sc, p.Years.Length - 1)]);
        }
    }
}
