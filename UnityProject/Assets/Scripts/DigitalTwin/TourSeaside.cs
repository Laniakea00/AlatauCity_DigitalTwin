using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Presentation step «Вечер на Капшагае»: the sun goes down over the reservoir, the promenade along the shore lights up as a
    /// warm line, yachts and an excursion boat cross the water with white wakes, the resorts' windows come on. The camera glides along the
    /// shore looking out to the water. The shoreline is traced from the base map (map_nature, water ≥ 150 m) and smoothed.</summary>
    public class TourSeaside
    {
        // shoreline of the Kapshagay reservoir in front of the Green resorts (x, z in metres), west → east
        static readonly Vector2[] Shore =
        {
            new Vector2(9400, 20420), new Vector2(9600, 20680), new Vector2(9800, 20920), new Vector2(10000, 21100), new Vector2(10200, 21050), new Vector2(10400, 20920),
            new Vector2(10600, 20860), new Vector2(10800, 20760), new Vector2(11000, 20600), new Vector2(11200, 20540), new Vector2(11400, 20560), new Vector2(11600, 20500),
            new Vector2(11800, 20410), new Vector2(12000, 20380), new Vector2(12200, 20430), new Vector2(12400, 20400), new Vector2(12600, 20350), new Vector2(12800, 20380),
            new Vector2(13000, 20290), new Vector2(13200, 20220), new Vector2(13400, 20170), new Vector2(13600, 20200), new Vector2(13800, 20290), new Vector2(14000, 20310),
            new Vector2(14200, 20360), new Vector2(14400, 20400), new Vector2(14600, 20440), new Vector2(14800, 20480), new Vector2(15000, 20450), new Vector2(15200, 20460),
            new Vector2(15400, 20560), new Vector2(15600, 20760), new Vector2(15800, 20880), new Vector2(16000, 20900), new Vector2(16200, 20890), new Vector2(16400, 20860),
        };
        class Boat { public Transform T; public float X0, X1, Z, Speed, Pos; public int Dir; }
        readonly List<Boat> boats = new List<Boat>();
        GameObject root; Material glowMat, wakeMat, hullMat, deckMat; float t;

        public TourSeaside()
        {
            root = new GameObject("Tour seaside");
            BuildPromenade();
            BuildBoats();
            TourFx.Instance?.Evening(18.45f, 7f);           // the sun touches the horizon: orange sky, first lights
        }

        // ------------------------------------------------------------------ the promenade: a warm line of lights along the shore
        void BuildPromenade()
        {
            var sh = Shader.Find("AlatauCity/Glow"); if (sh == null) return;
            glowMat = new Material(sh) { name = "Promenade lights" };
            glowMat.SetColor("_Color", new Color(1f, 0.42f, 0.14f) * 0.85f); glowMat.SetFloat("_Speed", 60f); glowMat.SetFloat("_Period", 240f); glowMat.SetFloat("_Fade", 0f);
            var V = new List<Vector3>(); var U = new List<Vector2>(); var T = new List<int>();
            const float W = 22f, inland = 12f; float acc = 0;
            for (int i = 0; i < Shore.Length; i++)
            {
                var a = Shore[Mathf.Max(i - 1, 0)]; var b = Shore[Mathf.Min(i + 1, Shore.Length - 1)]; var d = (b - a).normalized; var side = new Vector2(-d.y, d.x);   // side points north (to the water)
                var p = Shore[i] - side * inland; if (i > 0) acc += Vector2.Distance(Shore[i], Shore[i - 1]);
                float y = CityGround.HeightAt(p.x, p.y) + 2.5f; var s3 = new Vector3(side.x, 0, side.y) * (W * 0.5f);
                var c = new Vector3(p.x, y, p.y);
                V.Add(c - s3); U.Add(new Vector2(acc, 0)); V.Add(c + s3); U.Add(new Vector2(acc, 1));
                if (i > 0) { int k = (i - 1) * 2; T.Add(k); T.Add(k + 2); T.Add(k + 1); T.Add(k + 1); T.Add(k + 2); T.Add(k + 3); }
            }
            var m = new Mesh { name = "Promenade lights" }; m.SetVertices(V); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateBounds();
            var go = new GameObject("Promenade lights"); go.transform.SetParent(root.transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = m; var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = glowMat; mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        // ------------------------------------------------------------------ boats with wakes
        void BuildBoats()
        {
            var std = Shader.Find("Standard"); var ws = Shader.Find("AlatauCity/Wake");
            hullMat = new Material(std) { name = "Boat hull" }; hullMat.color = new Color(0.95f, 0.95f, 0.93f); hullMat.SetFloat("_Glossiness", 0.6f);
            deckMat = new Material(std) { name = "Boat deck" }; deckMat.color = new Color(0.18f, 0.22f, 0.27f); deckMat.SetFloat("_Glossiness", 0.8f);
            if (ws != null) wakeMat = new Material(ws) { name = "Wake" };
            var rng = new System.Random(2050);
            for (int i = 0; i < 13; i++)
            {
                float lane = 280f + 900f * (float)rng.NextDouble();                    // metres off the shore
                float x0 = 9600f + 1200f * (float)rng.NextDouble(), x1 = 15600f - 1200f * (float)rng.NextDouble();
                float len = i == 0 ? 80f : i < 4 ? 46f : 28f + 12f * (float)rng.NextDouble();      // a little larger than life: they must read from 2 km
                var b = new Boat { X0 = x0, X1 = x1, Z = lane, Speed = (i == 0 ? 9f : 16f + 14f * (float)rng.NextDouble()) * 2.2f, Pos = (float)rng.NextDouble(), Dir = rng.NextDouble() < 0.5 ? 1 : -1 };
                var go = new GameObject("Boat " + i); go.transform.SetParent(root.transform, false); b.T = go.transform;
                AddPart(go, "hull", HullMesh(len), hullMat); AddPart(go, "cabin", Box(new Vector3(0, len * 0.06f + 0.6f, -len * 0.05f), new Vector3(len * 0.22f, len * 0.07f, len * 0.42f)), deckMat);
                if (i == 0) AddPart(go, "deck2", Box(new Vector3(0, len * 0.11f + 1.2f, -len * 0.08f), new Vector3(len * 0.2f, len * 0.05f, len * 0.5f)), hullMat);
                if (wakeMat != null) AddPart(go, "wake", WakeMesh(len), wakeMat);
                boats.Add(b);
            }
        }
        static void AddPart(GameObject go, string name, Mesh m, Material mat)
        {
            var p = new GameObject(name); p.transform.SetParent(go.transform, false);
            p.AddComponent<MeshFilter>().sharedMesh = m; var r = p.AddComponent<MeshRenderer>(); r.sharedMaterial = mat;
            r.shadowCastingMode = mat.shader.name == "AlatauCity/Wake" ? UnityEngine.Rendering.ShadowCastingMode.Off : UnityEngine.Rendering.ShadowCastingMode.On;
        }
        /// <summary>A pointed hull along +z, length L.</summary>
        static Mesh HullMesh(float L)
        {
            float w = L * 0.17f, h = L * 0.06f;
            var top = new[] { new Vector3(0, h, L * 0.5f), new Vector3(w * 0.5f, h, L * 0.18f), new Vector3(w * 0.5f, h, -L * 0.5f), new Vector3(-w * 0.5f, h, -L * 0.5f), new Vector3(-w * 0.5f, h, L * 0.18f) };
            var bot = new[] { new Vector3(0, -h * 0.2f, L * 0.42f), new Vector3(w * 0.32f, -h * 0.4f, L * 0.12f), new Vector3(w * 0.4f, -h * 0.4f, -L * 0.48f), new Vector3(-w * 0.4f, -h * 0.4f, -L * 0.48f), new Vector3(-w * 0.32f, -h * 0.4f, L * 0.12f) };
            var V = new List<Vector3>(); var T = new List<int>();
            void Q(Vector3 a, Vector3 b, Vector3 c, Vector3 d) { int k = V.Count; V.Add(a); V.Add(b); V.Add(c); V.Add(d); T.Add(k); T.Add(k + 1); T.Add(k + 2); T.Add(k); T.Add(k + 2); T.Add(k + 3); }
            for (int i = 0; i < 5; i++) { int j = (i + 1) % 5; Q(top[i], top[j], bot[j], bot[i]); }
            int c0 = V.Count; foreach (var p in top) V.Add(p); T.Add(c0); T.Add(c0 + 1); T.Add(c0 + 4); T.Add(c0 + 1); T.Add(c0 + 2); T.Add(c0 + 4); T.Add(c0 + 2); T.Add(c0 + 3); T.Add(c0 + 4);
            var m = new Mesh { name = "Hull" }; m.SetVertices(V); m.SetTriangles(T, 0); m.RecalculateNormals(); m.RecalculateBounds(); return m;
        }
        static Mesh Box(Vector3 c, Vector3 s)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Cube); var src = g.GetComponent<MeshFilter>().sharedMesh; Object.Destroy(g);
            var v = src.vertices; for (int i = 0; i < v.Length; i++) v[i] = c + Vector3.Scale(v[i], s);
            var m = new Mesh { name = "Box" }; m.vertices = v; m.triangles = src.triangles; m.normals = src.normals; m.RecalculateBounds(); return m;
        }
        /// <summary>A V of foam behind the stern (−z), opening to ~50 m over ~10 boat lengths.</summary>
        static Mesh WakeMesh(float L)
        {
            var V = new List<Vector3>(); var U = new List<Vector2>(); var T = new List<int>(); int n = 16; float len = Mathf.Max(L * 9f, 160f);
            for (int i = 0; i <= n; i++)
            {
                float u = i / (float)n, z = -L * 0.45f - u * len, half = L * 0.1f + u * len * 0.18f;
                V.Add(new Vector3(-half, 0.15f, z)); U.Add(new Vector2(u, 0)); V.Add(new Vector3(half, 0.15f, z)); U.Add(new Vector2(u, 1));
                if (i > 0) { int k = (i - 1) * 2; T.Add(k); T.Add(k + 2); T.Add(k + 1); T.Add(k + 1); T.Add(k + 2); T.Add(k + 3); }
            }
            var m = new Mesh { name = "Wake" }; m.SetVertices(V); m.SetUVs(0, U); m.SetTriangles(T, 0); m.RecalculateBounds(); return m;
        }

        public void Tick(float dt)
        {
            t += dt;
            if (glowMat != null) glowMat.SetFloat("_Fade", Mathf.Clamp01((t - 2.5f) / 3f));          // the lights come on as the sun goes
            if (wakeMat != null) wakeMat.SetFloat("_Fade", 0.95f);
            foreach (var b in boats)
            {
                float span = b.X1 - b.X0; b.Pos = Mathf.Repeat(b.Pos + dt * b.Speed / Mathf.Max(span, 1f), 1f);
                float x = b.Dir > 0 ? Mathf.Lerp(b.X0, b.X1, b.Pos) : Mathf.Lerp(b.X1, b.X0, b.Pos);
                float zs = ShoreZ(x), z = zs + b.Z;
                float y = CityGround.HeightAt(x, z) + 0.05f;
                b.T.position = new Vector3(x, y, z);
                float slope = (ShoreZ(x + 40f) - ShoreZ(x - 40f)) / 80f;
                b.T.rotation = Quaternion.LookRotation(new Vector3(b.Dir, 0, slope * b.Dir));
                // fade in and out at the ends of the run so no boat pops
                float edge = Mathf.Min(b.Pos, 1f - b.Pos) * 8f; b.T.localScale = Vector3.one * Mathf.Clamp01(edge);
            }
        }
        static float ShoreZ(float x)
        {
            if (x <= Shore[0].x) return Shore[0].y; if (x >= Shore[Shore.Length - 1].x) return Shore[Shore.Length - 1].y;
            for (int i = 1; i < Shore.Length; i++) if (x <= Shore[i].x) return Mathf.Lerp(Shore[i - 1].y, Shore[i].y, (x - Shore[i - 1].x) / (Shore[i].x - Shore[i - 1].x));
            return Shore[Shore.Length - 1].y;
        }

        public void Stop()
        {
            if (root != null) Object.Destroy(root); root = null;
            foreach (var m in new[] { glowMat, wakeMat, hullMat, deckMat }) if (m != null) Object.Destroy(m);
        }
    }
}
