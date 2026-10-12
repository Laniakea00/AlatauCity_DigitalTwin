using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;
using AlatauCity.DigitalTwin.Data;
using static AlatauCity.DigitalTwin.Data.TwinJson;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Pilot quarter Gate District Q1 as a BIM model (IFC4 LOD 200 from QTwin, 9 880 elements) with 4D: every element has a planned and an
    /// actual completion day (synthetic drone surveys). Loaded lazily from StreamingAssets/twin/gate_q1.bytes + gate_q1.json on first use.
    /// While shown, the city's master-plan buildings on the same plot are hidden (ConstructionLayer.Hidden).</summary>
    public class BimQuarter : MonoBehaviour
    {
        public static BimQuarter Instance;
        public static bool Loaded => Instance != null && Instance.elements != null;
        public static bool Visible { get; private set; }

        public class Element { public string Guid, Name, Cls, Complex; public int Storey, Stage, Plan, Fact; public float Volume; }
        public class Stage { public string Id, Name; public int Start, End, Workers; public Vector2[] Fact; }
        public Element[] elements; public Stage[] stages; public DateTime Day0; public int StatusDay, EndDay; public int[] EpochDays = new int[0];
        public Vector3 Center; public Bounds Box; public string Note = "";
        public int Day { get; private set; }
        public const int Grace = 14;   // days late before an element counts as "behind"
        public int Selected { get; private set; } = -1;
        public event Action OnChanged;

        MeshRenderer mr; Material mat; Texture2D elemTex; int[] vertElem, tris; MeshCollider col;
        static readonly string[] ClsOrder = { "footing", "curtain", "column", "wall", "slab" };

        public static BimQuarter Ensure()
        {
            if (Instance != null) return Instance;
            var go = new GameObject("BIM Gate Q1"); Instance = go.AddComponent<BimQuarter>(); Instance.Load(); go.SetActive(false); return Instance;
        }

        void Load()
        {
            string dir = Path.Combine(Application.streamingAssetsPath, "twin");
            try
            {
                var j = Parse(TwinFiles.Text("gate_q1.json"));
                Day0 = DateTime.Parse(S(G(j, "day0"))); StatusDay = I(G(j, "status_day")); EndDay = I(G(j, "end_day")); Note = S(G(G(j, "about"), "note"));
                var st = A(G(j, "stages")); stages = new Stage[st.Count];
                for (int i = 0; i < st.Count; i++)
                {
                    var s = st[i]; var f = A(G(s, "fact")); var fv = new Vector2[f.Count];
                    for (int k = 0; k < f.Count; k++) { var p = A(f[k]); fv[k] = new Vector2(F(p[0]), F(p[1])); }
                    stages[i] = new Stage { Id = S(G(s, "id")), Name = S(G(s, "name")), Start = I(G(s, "start")), End = I(G(s, "end")), Workers = I(G(s, "workers")), Fact = fv };
                }
                var ep = A(G(j, "epochs")); EpochDays = new int[ep.Count]; for (int i = 0; i < ep.Count; i++) EpochDays[i] = I(G(ep[i], "day"));
                var el = A(G(j, "elements")); elements = new Element[el.Count];
                for (int i = 0; i < el.Count; i++)
                {
                    var e = A(el[i]);
                    elements[i] = new Element { Guid = S(e[0]), Name = S(e[1]), Cls = S(e[2]), Complex = S(e[3]), Storey = I(e[4]), Stage = I(e[5]), Plan = I(e[6]), Fact = I(e[7]), Volume = F(e[8]) };
                }
                BuildMesh(TwinFiles.Bytes("gate_q1.bytes"));
                Day = StatusDay;
                Debug.Log($"[Alatau] BIM Gate Q1: {elements.Length} elements, {stages.Length} stages, from {Day0:dd.MM.yyyy}");
            }
            catch (Exception ex) { Debug.LogError("[Alatau] BIM Gate Q1: " + ex.Message); elements = null; }
        }

        void BuildMesh(byte[] b)
        {
            int o = 4; int nv = BitConverter.ToInt32(b, o); o += 4; int nt = BitConverter.ToInt32(b, o); o += 4;
            var v = new Vector3[nv]; for (int i = 0; i < nv; i++) { v[i] = new Vector3(BitConverter.ToSingle(b, o), BitConverter.ToSingle(b, o + 4), BitConverter.ToSingle(b, o + 8)); o += 12; }
            tris = new int[nt * 3]; for (int i = 0; i < tris.Length; i++) { tris[i] = (int)BitConverter.ToUInt32(b, o); o += 4; }
            vertElem = new int[nv]; for (int i = 0; i < nv; i++) { vertElem[i] = BitConverter.ToInt32(b, o); o += 4; }
            // flat shading: unweld so every triangle gets its own normal
            var pv = new Vector3[tris.Length]; var uv = new Vector2[tris.Length]; var ti = new int[tris.Length]; var ve = new int[tris.Length];
            for (int i = 0; i < tris.Length; i++) { pv[i] = v[tris[i]]; uv[i] = new Vector2(vertElem[tris[i]], 0); ti[i] = i; ve[i] = vertElem[tris[i]]; }
            vertElem = ve;
            var mesh = new Mesh { name = "Gate Q1 BIM", indexFormat = IndexFormat.UInt32 };
            mesh.vertices = pv; mesh.uv2 = uv; mesh.triangles = ti; mesh.RecalculateNormals(); mesh.RecalculateBounds();
            Box = mesh.bounds; Center = Box.center;
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            mr = gameObject.AddComponent<MeshRenderer>(); mr.shadowCastingMode = ShadowCastingMode.On;
            mat = new Material(Shader.Find("AlatauCity/Bim")) { name = "BIM Gate Q1" }; mr.sharedMaterial = mat;
            col = gameObject.AddComponent<MeshCollider>(); col.sharedMesh = mesh;
            // element lookup: plan day, fact day, class id, stage
            elemTex = new Texture2D(128, 128, TextureFormat.RGBAFloat, false, true) { filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp, name = "BIM elements" };
            var px = new float[128 * 128 * 4];
            for (int i = 0; i < elements.Length && i < 16384; i++)
            {
                var e = elements[i]; px[i * 4] = e.Plan; px[i * 4 + 1] = e.Fact; px[i * 4 + 2] = Mathf.Max(0, Array.IndexOf(ClsOrder, e.Cls)); px[i * 4 + 3] = e.Stage;
            }
            elemTex.SetPixelData(px, 0); elemTex.Apply(false, false); mat.SetTexture("_ElemTex", elemTex);
        }

        // ------------------------------------------------------------------ show / hide, date, selection
        public void Show(bool on)
        {
            if (elements == null) return;
            Visible = on; gameObject.SetActive(on);
            ConstructionLayer.SetHiddenArea(on ? new Rect(Box.min.x - 30, Box.min.z - 30, Box.size.x + 60, Box.size.z + 60) : Rect.zero);
            if (!on) Select(-1);
        }
        public void SetDay(int d) { Day = Mathf.Clamp(d, 0, EndDay + 20); if (mat != null) mat.SetFloat("_BimDay", Day); OnChanged?.Invoke(); }
        public void SetGhost(bool on) { if (mat != null) mat.SetFloat("_BimGhost", on ? 1 : 0); }
        public void Select(int i) { Selected = i; if (mat != null) mat.SetFloat("_BimSel", i + 1); OnChanged?.Invoke(); }
        public DateTime DateOf(int d) => Day0.AddDays(d);
        public int ElementAtTriangle(int tri) => tri >= 0 && tri * 3 < vertElem.Length ? vertElem[tri * 3] : -1;
        public bool Owns(Collider c) => c != null && c == col;

        // ------------------------------------------------------------------ analytics at the current day
        public struct Stat { public float PlanPct, FactPct, Concrete, Workers; public int Built, Behind, InWork; }
        public Stat Compute(int day)
        {
            var s = new Stat(); float tot = 0, pv = 0, fv = 0;
            foreach (var e in elements)
            {
                float v = Mathf.Max(e.Volume, 0.05f); tot += v;
                if (e.Plan <= day) pv += v;
                if (e.Fact <= day) { fv += v; s.Built++; if (e.Cls != "curtain") s.Concrete += e.Volume; }
                else if (e.Plan + Grace <= day) s.Behind++;
                else if (e.Plan - 12 <= day) s.InWork++;
            }
            foreach (var st in stages) if (day >= st.Start && day <= st.End + 10) s.Workers += st.Workers;
            s.PlanPct = tot > 0 ? 100f * pv / tot : 0; s.FactPct = tot > 0 ? 100f * fv / tot : 0; return s;
        }
        /// <summary>Plan and fact completion of one stage (share of its elements) at a day.</summary>
        public void StageProgress(int si, int day, out float plan, out float fact)
        {
            int n = 0, p = 0, f = 0;
            foreach (var e in elements) if (e.Stage == si) { n++; if (e.Plan <= day) p++; if (e.Fact <= day) f++; }
            plan = n > 0 ? 100f * p / n : 0; fact = n > 0 ? 100f * f / n : 0;
        }
    }
}
