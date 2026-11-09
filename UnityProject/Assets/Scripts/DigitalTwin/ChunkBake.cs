using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>What the city once read from the building meshes at run time, computed when the scene is built (AlatauCityBuilder)
    /// into Resources/CityBake/chunks.bytes, so the building meshes need no copy in memory besides the one on the graphics card:
    /// for each chunk the runs of triangles of one building (first triangle, bid, opening year), the main wall direction of each
    /// building for the film look's roofs (_AlatauRoofTex), and the four ground corners of each generated house (its hedge plot).</summary>
    public static class ChunkBake
    {
        public class Runs { public int[] Start, Bid; public float[] Year; }
        static Dictionary<string, Runs> runs;
        static byte[] roofR, roofA;
        static List<(int bid, Vector3[] c)> houses;
        static bool tried;
        public static bool Ready { get { Load(); return runs != null; } }

        static void Load()
        {
            if (tried) return; tried = true;
            var ta = Resources.Load<TextAsset>("CityBake/chunks");
            if (ta == null) { Debug.LogWarning("[Alatau] CityBake/chunks.bytes is missing: rebuild the scene (Alatau City → Rebuild Scene)"); return; }
            try
            {
                using var r = new BinaryReader(new MemoryStream(ta.bytes));
                if (r.ReadInt32() != 0x31424341) throw new IOException("not a chunk bake");
                int nc = r.ReadInt32(); var d = new Dictionary<string, Runs>(nc);
                for (int c = 0; c < nc; c++)
                {
                    string name = r.ReadString(); int n = r.ReadInt32(); var x = new Runs { Start = new int[n], Bid = new int[n], Year = new float[n] };
                    for (int i = 0; i < n; i++) { x.Start[i] = r.ReadInt32(); x.Bid[i] = r.ReadInt32(); x.Year[i] = r.ReadSingle(); }
                    d[name] = x;
                }
                int nb = r.ReadInt32(); roofR = r.ReadBytes(nb); roofA = r.ReadBytes(nb);
                int nh = r.ReadInt32(); houses = new List<(int, Vector3[])>(nh);
                for (int h = 0; h < nh; h++)
                {
                    int bid = r.ReadInt32(); var c4 = new Vector3[4];
                    for (int k = 0; k < 4; k++) c4[k] = new Vector3(r.ReadSingle(), r.ReadSingle(), r.ReadSingle());
                    houses.Add((bid, c4));
                }
                runs = d;
                Resources.UnloadAsset(ta);
            }
            catch (System.Exception e) { Debug.LogWarning("[Alatau] chunk bake: " + e.Message); runs = null; }
        }

        /// <summary>The run of triangle t of the chunk mesh named mesh; -1 when unknown.</summary>
        static int RunOf(string mesh, int t, out Runs x)
        {
            x = null; Load(); if (runs == null || t < 0 || !runs.TryGetValue(mesh, out x) || x.Start.Length == 0) return -1;
            int lo = 0, hi = x.Start.Length - 1;
            while (lo < hi) { int mid = (lo + hi + 1) >> 1; if (x.Start[mid] <= t) lo = mid; else hi = mid - 1; }
            return x.Start[lo] <= t ? lo : -1;
        }
        public static int BuildingAt(string mesh, int t) { int i = RunOf(mesh, t, out var x); return i < 0 ? -1 : x.Bid[i]; }
        public static float YearAt(string mesh, int t) { int i = RunOf(mesh, t, out var x); return i < 0 ? 0f : x.Year[i]; }

        static bool roofDone;
        /// <summary>Sets the film look's roof orientation table (_AlatauRoofTex, _AlatauRoofOn) once.</summary>
        public static void ApplyRoofs()
        {
            if (roofDone) return; roofDone = true; Load(); if (roofR == null) return;
            var px = new Color32[BidTable.N]; int n = Mathf.Min(BidTable.N, roofR.Length);
            for (int i = 0; i < BidTable.N; i++) px[i] = i < n ? new Color32(roofR[i], 0, 0, roofA[i]) : new Color32(128, 0, 0, 0);
            var tex = BidTable.New(TextureFormat.RGBA32, "Alatau roof orientation"); tex.SetPixels32(px); tex.Apply(false, true);
            Shader.SetGlobalTexture("_AlatauRoofTex", tex); Shader.SetGlobalFloat("_AlatauRoofOn", 1f);
        }

        /// <summary>The generated houses with their four ground corners (bid, corners).</summary>
        public static List<(int bid, Vector3[] c)> Houses { get { Load(); return houses ?? new List<(int, Vector3[])>(); } }
    }
}
