using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Traffic lights and the street lamps of the Gate district in the film look. FilmTraffic finds the junctions of the roads open
    /// in the year shown (main roads, crossroads of streets, the junctions of the ring round Iconic Complex), puts a signal post at the
    /// right kerb of every approach (right-hand traffic) and tells its cars to stop at the stop line while their light is red. This
    /// class keeps the common clock of the lights and draws the posts and the lamps with GPU instancing (AlatauCity/Signal) near the
    /// camera only. Two signal groups per junction: the main road (group 0), then the side roads (group 1), with amber and a short
    /// all-red between them. Typical city practice, not survey data.</summary>
    public class FilmSignals : MonoBehaviour
    {
        public static FilmSignals Instance;
        /// <summary>A signal post (Type 0 a post by a street, 1 a mast with an arm over a main road) or a lamp (Type 2): position on the
        /// ground, yaw of its local +z (a signal faces the drivers that approach, a lamp's arm points over the road), phase offset and group.</summary>
        public struct Item { public Vector3 P; public float Yaw, Off; public byte Type, Grp; }
        public static readonly List<Item> Items = new List<Item>();
        static int version;
        /// <summary>FilmTraffic filled Items anew.</summary>
        public static void Changed() { version++; }

        // ------------------------------------------------------------------ the cycle (AlatauSignal.shader computes the same: keep in step)
        public const float Cycle = 44f;
        /// <summary>Seconds of the lights' clock (game time, so a paused tour also pauses them).</summary>
        public static float Clock;
        /// <summary>State of a signal group: 0 green, 1 amber, 2 red. Group 0: green 0–20 s, amber 20–23; group 1: green 25–39, amber 39–42.</summary>
        public static int State(float off, int grp)
        {
            float t = Mathf.Repeat(Clock + off, Cycle);
            if (grp == 0) return t < 20f ? 0 : t < 23f ? 1 : 2;
            return t >= 25f && t < 39f ? 0 : t >= 39f && t < 42f ? 1 : 2;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Film signals").AddComponent<FilmSignals>(); }
        void Awake() { Instance = this; }

        static readonly bool High = Application.platform != RuntimePlatform.WebGLPlayer;
        const int Types = 3, Batch = 1023;
        Mesh[] meshes; Material mat; bool failed;
        Matrix4x4[][][] mats; Vector4[][][] data; MaterialPropertyBlock[][] mpbs; readonly int[] counts = new int[Types]; int cap;
        int drawnVersion = -1; Vector2 lastFocus = new Vector2(1e9f, 1e9f); float lastR;
        static readonly int DataId = Shader.PropertyToID("_SigData"), ClockId = Shader.PropertyToID("_AlatauSigClock"), FadeId = Shader.PropertyToID("_AlatauSigFade");

        void Start()
        {
            var sh = Shader.Find("AlatauCity/Signal");
            if (sh == null) { failed = true; Debug.LogWarning("[Alatau] film signals: shader AlatauCity/Signal missing"); return; }
            mat = new Material(sh) { name = "Film signals", enableInstancing = true };
            meshes = new[] { SignalMesh(false), SignalMesh(true), LampMesh() };
            cap = High ? 3000 : 900;
            int nb = (cap + Batch - 1) / Batch;
            mats = new Matrix4x4[Types][][]; data = new Vector4[Types][][]; mpbs = new MaterialPropertyBlock[Types][];
            for (int t = 0; t < Types; t++)
            {
                mats[t] = new Matrix4x4[nb][]; data[t] = new Vector4[nb][]; mpbs[t] = new MaterialPropertyBlock[nb];
                for (int b = 0; b < nb; b++) { mats[t][b] = new Matrix4x4[Batch]; data[t][b] = new Vector4[Batch]; mpbs[t][b] = new MaterialPropertyBlock(); }
            }
            Camera.onPreCull += PreCull;
        }
        void OnDestroy() { Camera.onPreCull -= PreCull; }

        void Update()
        {
            Clock += Time.deltaTime;
            Shader.SetGlobalFloat(ClockId, Mathf.Repeat(Clock, Cycle * 1000f));
        }

        // drawn for each render of the main camera (also the capture tool's hand-made renders), only what lies near what it looks at
        void PreCull(Camera c)
        {
            if (failed || mat == null || c == null || c != Camera.main || !FilmLook.Active || !FilmTraffic.On || Items.Count == 0) return;
            var t = c.transform; Vector3 p = t.position, f = t.forward;
            float h = p.y - CityGround.HeightAt(p.x, p.z);
            if (h > 2600f) return;                                              // from high up they are too small to see
            float d = f.y < -0.02f ? Mathf.Max(h, 2f) / -f.y : 1e6f; d = Mathf.Min(d, 400f + 3f * Mathf.Max(h, 0f));
            var fp = p + f * d; var focus = new Vector2(fp.x, fp.z);
            float R = Mathf.Clamp(Mathf.Max(d, h) * 1.5f, 400f, High ? 2600f : 1400f);
            if (drawnVersion != version || Mathf.Abs(R - lastR) > lastR * 0.2f || (focus - lastFocus).sqrMagnitude > (R * 0.15f) * (R * 0.15f)) Collect(focus, R);
            Shader.SetGlobalVector(FadeId, new Vector4(lastFocus.x, lastFocus.y, lastR, lastR * 0.2f));
            var shadows = High && h < 900f && FilmLook.Lamps < 0.5f ? ShadowCastingMode.On : ShadowCastingMode.Off;
            for (int k = 0; k < Types; k++)
            {
                int left = counts[k];
                for (int b = 0; left > 0; b++) { int n = Mathf.Min(left, Batch); Graphics.DrawMeshInstanced(meshes[k], 0, mat, mats[k][b], n, mpbs[k][b], shadows, true, 0, c); left -= n; }
            }
        }

        void Collect(Vector2 focus, float R)
        {
            drawnVersion = version; lastFocus = focus; lastR = R;
            for (int k = 0; k < Types; k++) counts[k] = 0;
            float R2 = R * R;
            for (int i = 0; i < Items.Count; i++)
            {
                var it = Items[i]; float dx = it.P.x - focus.x, dz = it.P.z - focus.y; if (dx * dx + dz * dz > R2) continue;
                int k = it.Type, n = counts[k]; if (n >= cap) continue;
                mats[k][n / Batch][n % Batch] = Matrix4x4.TRS(it.P, Quaternion.Euler(0f, it.Yaw, 0f), Vector3.one);
                data[k][n / Batch][n % Batch] = new Vector4(it.Off, it.Grp, 0f, 0f);
                counts[k] = n + 1;
            }
            for (int k = 0; k < Types; k++) for (int b = 0; b * Batch < counts[k]; b++) mpbs[k][b].SetVectorArray(DataId, data[k][b]);
        }

        // ------------------------------------------------------------------ models (metres; base at the origin, the lights face +z, the arm along +x)
        // vertex colour: rgb = surface, a = what it is: 0 metal, 0.2 red lens, 0.35 amber lens, 0.5 green lens, 0.7 the lamp's light pool on
        // the ground (glow pass only), 1 the lamp's lens; uv0 = the centre of the lens a vertex belongs to (a lit lens grows from afar)
        static readonly Color Pole = new Color(0.40f, 0.42f, 0.44f, 0f), Housing = new Color(0.10f, 0.11f, 0.12f, 0f), Plate = new Color(0.06f, 0.06f, 0.07f, 0f);
        static Mesh SignalMesh(bool mast)
        {
            var b = new Builder();
            float ph = mast ? 6.6f : 3.6f, pw = mast ? 0.22f : 0.14f;
            b.Box(new Vector3(0, 0.2f, 0), new Vector3(pw * 2f, 0.4f, pw * 2f), Pole);
            b.Box(new Vector3(0, ph * 0.5f, 0), new Vector3(pw, ph, pw), Pole);
            if (mast)
            {
                b.Box(new Vector3(2.4f, 6.35f, 0), new Vector3(4.9f, 0.16f, 0.16f), Pole);                 // the arm over the lanes
                b.Box(new Vector3(1.0f, 5.9f, 0), new Vector3(2.0f, 0.08f, 0.08f), Pole);                  // its brace
                Head(b, new Vector3(4.1f, 5.55f, 0.05f));                                                // over the lanes
                Head(b, new Vector3(0f, 3.0f, 0.2f));                                                    // on the post, at the stop line
            }
            else
            {
                Head(b, new Vector3(0f, 2.95f, 0.18f));
                b.Box(new Vector3(0, ph + 0.05f, 0), new Vector3(pw * 1.3f, 0.1f, pw * 1.3f), Pole);
            }
            return b.Mesh(mast ? "Signal mast" : "Signal post");
        }
        static void Head(Builder b, Vector3 c)
        {
            b.Box(c + new Vector3(0, 0, -0.06f), new Vector3(0.62f, 1.30f, 0.04f), Plate);          // contrast plate
            b.Box(c, new Vector3(0.38f, 1.08f, 0.26f), Housing);
            float[] ys = { 0.33f, 0f, -0.33f }; float[] code = { 0.2f, 0.35f, 0.5f };
            Color[] tint = { new Color(0.9f, 0.1f, 0.06f), new Color(0.95f, 0.6f, 0.05f), new Color(0.1f, 0.85f, 0.45f) };
            for (int i = 0; i < 3; i++)
            {
                var l = c + new Vector3(0, ys[i], 0.14f);
                b.Box(l, new Vector3(0.25f, 0.25f, 0.03f), new Color(tint[i].r, tint[i].g, tint[i].b, code[i]));
                b.Box(l + new Vector3(0, 0.15f, 0.08f), new Vector3(0.3f, 0.03f, 0.16f), Housing);      // visor
            }
        }
        /// <summary>The street lamp of the main streets (FilmLamps' 10 m post with a 2 m arm) with the pool of its light on the road.</summary>
        static Mesh LampMesh()
        {
            var src = FilmLamps.MakeLamp(10f, 2.0f, false, 0.2f);
            var b = new Builder(); b.V.AddRange(src.vertices); b.N.AddRange(src.normals); b.C.AddRange(src.colors); b.T.AddRange(src.triangles);
            var su = new List<Vector3>(); src.GetUVs(0, su); b.U.AddRange(su);             // uv0 = the centre of the lens (it grows from afar)
            // the pool: a flat square under the head, glow pass only (uv0 = position in the pool, -1..1)
            int v0 = b.V.Count; const float r = 13f; var pc = new Vector3(0f, 0.18f, 1.6f);
            for (int i = 0; i < 4; i++)
            {
                float u = i == 0 || i == 3 ? -1f : 1f, v = i < 2 ? -1f : 1f;
                b.V.Add(pc + new Vector3(u * r, 0f, v * r)); b.N.Add(Vector3.up); b.C.Add(new Color(1f, 1f, 1f, 0.7f)); b.U.Add(new Vector3(u, v, 0f));
            }
            b.T.Add(v0); b.T.Add(v0 + 2); b.T.Add(v0 + 1); b.T.Add(v0); b.T.Add(v0 + 3); b.T.Add(v0 + 2);
            var m = b.Mesh("Gate street lamp"); var bb = m.bounds; bb.Expand(4f); m.bounds = bb; return m;
        }

        class Builder
        {
            public readonly List<Vector3> V = new List<Vector3>(), N = new List<Vector3>(); public readonly List<Color> C = new List<Color>();
            public readonly List<Vector3> U = new List<Vector3>(); public readonly List<int> T = new List<int>();
            public void Box(Vector3 c, Vector3 s, Color col)
            {
                var e = s * 0.5f;
                for (int f = 0; f < 6; f++)
                {
                    Vector3 n = f == 0 ? Vector3.right : f == 1 ? Vector3.left : f == 2 ? Vector3.up : f == 3 ? Vector3.down : f == 4 ? Vector3.forward : Vector3.back;
                    Vector3 u = Mathf.Abs(n.y) > 0.5f ? Vector3.right : Vector3.up, w = Vector3.Cross(n, u);
                    int v0 = V.Count;
                    for (int i = 0; i < 4; i++)
                    {
                        float su = (i == 0 || i == 3) ? -1f : 1f, sw = i < 2 ? -1f : 1f;
                        V.Add(c + Vector3.Scale(n + u * su + w * sw, e)); N.Add(n); C.Add(col); U.Add(col.a > 0.1f ? c : Vector3.zero);
                    }
                    if (Vector3.Dot(Vector3.Cross(V[v0 + 1] - V[v0], V[v0 + 2] - V[v0]), n) > 0f) { T.Add(v0); T.Add(v0 + 1); T.Add(v0 + 2); T.Add(v0); T.Add(v0 + 2); T.Add(v0 + 3); }
                    else { T.Add(v0); T.Add(v0 + 2); T.Add(v0 + 1); T.Add(v0); T.Add(v0 + 3); T.Add(v0 + 2); }
                }
            }
            public Mesh Mesh(string name)
            {
                var m = new Mesh { name = name }; m.SetVertices(V); m.SetNormals(N); m.SetColors(C); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateBounds(); return m;
            }
        }
    }
}
