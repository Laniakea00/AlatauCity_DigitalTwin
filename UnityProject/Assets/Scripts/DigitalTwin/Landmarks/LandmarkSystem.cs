using System;
using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Marks a collider as part of a landmark (TwinSelector picks it before ordinary buildings).</summary>
    public class LandmarkObject : MonoBehaviour { public string Id; }

    /// <summary>The real projects of Alatau City as detailed 3D models in their districts:
    /// build at start, rise by year (construction), ghosts of planned objects in the "Инвестпроекты" tab,
    /// hover rim, click → cinematic fly-to + slow orbit + passport card (TwinUI). Esc or ✕ = back.</summary>
    public class LandmarkSystem : MonoBehaviour
    {
        public static LandmarkSystem Instance;
        public static event Action<Landmark> OnSelected;
        /// <summary>All objects, LRT last.</summary>
        public readonly List<Landmark> Items = new List<Landmark>();
        public Landmark Selected { get; private set; }
        public Landmark Hovered { get; private set; }
        /// <summary>Planned objects drawn as ghosts (set by the Investment projects module).</summary>
        public static bool ShowPlanned;
        /// <summary>Cut-away of one object (IconicInterior): everything of it above CutAt metres over its base is not drawn.</summary>
        public static string CutId; public static float CutAt = -1f;

        class Crane { public Transform Mast, Head; public MeshRenderer MastR; public MaterialPropertyBlock B; public float Yaw, Speed; }
        class Node
        {
            public Landmark L; public GameObject Go; public MeshRenderer R; public MeshCollider C; public MaterialPropertyBlock B; public float hi;
            public GameObject Site; public readonly List<Crane> Cranes = new List<Crane>(); public float lastP = -1f, glow = -1f;
            public Transform Flyer; public float FlyT;
            // the buildings of a complex (Landmark.Parts): their stages for the shader (_PartA / _PartB, index = part of the model),
            // the hand-over light sweep of each, and which part every triangle of the model belongs to (picking in the monitoring)
            public readonly Vector4[] PA = new Vector4[8], PB = new Vector4[8]; public readonly float[] LastPP = new float[8], GlowP = new float[8];
            public List<Vector2> PartUv; public int[] Tris;
            // the diff of two surveys (DiffFrom): the site then and now, the hoarding's own block for its colour
            public bool Site0, Site1, Cr0, Cr1; public MeshRenderer FenceR; public MaterialPropertyBlock FenceB;
        }
        readonly Dictionary<string, Node> nodes = new Dictionary<string, Node>();
        Material mat, matIconic, matKaist; bool built;
        static readonly int RevealId = Shader.PropertyToID("_Reveal"), BuildId = Shader.PropertyToID("_Build"), GhostId = Shader.PropertyToID("_Ghost"), HiId = Shader.PropertyToID("_Hi"),
            FacadeId = Shader.PropertyToID("_Facade"), LandId = Shader.PropertyToID("_Land"), GlowId = Shader.PropertyToID("_Glow"), HeightId = Shader.PropertyToID("_H"),
            PartAId = Shader.PropertyToID("_PartA"), PartBId = Shader.PropertyToID("_PartB"),
            DiffOnId = Shader.PropertyToID("_DiffOn"), DiffAId = Shader.PropertyToID("_DiffA"), DiffWId = Shader.PropertyToID("_DiffW"), DiffTintId = Shader.PropertyToID("_DiffTint");

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Landmarks (Alatau City projects)").AddComponent<LandmarkSystem>(); }
        void Awake()
        {
            Instance = this;
            // the catalogue is known at once (the UI lists it); the models are built when the terrain is loaded
            Items.Clear(); Items.AddRange(LandmarkCatalog.All()); Items.Add(LandmarkCatalog.Lrt());
            try { PrepareGround(); } catch (Exception e) { Debug.LogWarning("[Alatau] landmark plots: " + e.Message); }
        }

        // ------------------------------------------------------------------ plots: level ground, replaced buildings, no trees
        static byte[] hidden;
        /// <summary>Generic buildings of the plan that a landmark replaces, or that MapOrder removes (hidden in AlatauLit, not pickable:
        /// pick and line-of-sight rays pass through them).</summary>
        public static bool IsHiddenBid(int bid) => (hidden != null && bid >= 0 && bid < hidden.Length && hidden[bid] != 0 && (hidden[bid] == 1 || TwinState.Year >= 2000 + hidden[bid]))
                                                   || MapOrder.Removed(bid);          // removed from the map (wrong place in the base data)

        /// <summary>Before anything is draped on the terrain (roads, trees, networks, LRT): every plot is levelled to one height with a soft
        /// edge, the terrain mesh follows, the generic buildings standing on the plot are hidden, and an invisible slab keeps the trees off it.</summary>
        void PrepareGround()
        {
            var tgo = GameObject.Find("Terrain (master plan map)");
            Mesh mesh = null; Vector3[] verts = null;
            var mf = tgo != null ? tgo.GetComponent<MeshFilter>() : null;
            if (mf != null && mf.sharedMesh != null && mf.sharedMesh.isReadable) { mesh = mf.mesh; verts = mesh.vertices; }
            hidden = new byte[256 * 256]; int nh = 0;
            LoadBounds();
            var db = CityDatabase.Instance;
            foreach (var l in Items)
            {
                if (l.IsLrt || l.PadW <= 0f) continue;
                float lvl = Ground(l.X, l.Z, Mathf.Max(l.PadW, l.PadD) * 0.5f);
                l.Base = lvl;
                var idx = CityGround.Flatten(l.X, l.Z, l.Yaw, l.PadW + 16f, l.PadD + 16f, lvl - 0.05f, Mathf.Max(80f, Mathf.Min(l.PadW, l.PadD) * 0.15f));
                if (verts != null) foreach (var i in idx) if (i < verts.Length) verts[i].y = CityGround.RawHeight(i);
                float a = l.Yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
                // every building whose real footprint (Resources/Landmarks/bid_bounds) touches the plot is replaced by the landmark:
                // planned and generated ones never appear, existing ones disappear in the year the landmark's construction starts
                if (bounds != null)
                {
                    float hw = l.PadW * 0.5f + 6f, hd = l.PadD * 0.5f + 6f, R = Mathf.Sqrt(hw * hw + hd * hd);
                    for (int bid = 0; bid < boundsN && bid < hidden.Length; bid++)
                    {
                        float x0 = bounds[bid * 4], z0 = bounds[bid * 4 + 1], x1 = bounds[bid * 4 + 2], z1 = bounds[bid * 4 + 3];
                        if (x1 <= x0) continue;
                        // a district round the landmark (Landmark.Ring, the Gate District of Iconic Complex): every building standing in its
                        // area gives way to the district's own blocks the year they stand (existing ones when the works start)
                        bool inGate = l.Ring > 0f && (IconicDistrict.InGate((x0 + x1) * 0.5f, (z0 + z1) * 0.5f) || IconicDistrict.InGate(x0, z0)
                                                      || IconicDistrict.InGate(x1, z0) || IconicDistrict.InGate(x0, z1) || IconicDistrict.InGate(x1, z1));
                        bool onPad = !(x1 < l.X - R || x0 > l.X + R || z1 < l.Z - R || z0 > l.Z + R) && ObbHitsAabb(l.X, l.Z, ca, sa, hw, hd, x0, z0, x1, z1);
                        if (!inGate && !onPad) continue;
                        var bi = db?.Get(bid);
                        bool existing = bi != null && bi.Source == "existing_osm";
                        byte code = existing ? (byte)Mathf.Clamp(l.StartYear - 2000, 2, 254) : onPad ? (byte)1 : (byte)Mathf.Clamp(Mathf.CeilToInt(l.Finish) - 2000, 2, 254);
                        if (hidden[bid] == 0 || code < hidden[bid]) { if (hidden[bid] == 0) nh++; hidden[bid] = code; }
                    }
                }
                // an invisible slab over the plot: the film trees and hedges see "a building stands here" and keep off
                var blk = new GameObject("Plot · " + l.Name); blk.transform.SetParent(transform, false);
                blk.transform.SetPositionAndRotation(new Vector3(l.X, lvl, l.Z), Quaternion.Euler(0, l.Yaw, 0));
                var bc = blk.AddComponent<BoxCollider>(); bc.size = new Vector3(l.PadW, 3f, l.PadD); bc.center = Vector3.zero;
                blk.AddComponent<LandmarkObject>().Id = l.Id;
            }
            if (mesh != null) { mesh.vertices = verts; mesh.RecalculateNormals(); mesh.RecalculateBounds(); }
            // buildings the base data puts on a road carriageway or on open water (Tools/fix_water_roads.py): generated and planned ones never
            // appear, existing ones go in the year the new road opens
            var extra = Resources.Load<TextAsset>("Landmarks/hide_extra");
            if (extra != null && extra.bytes.Length >= 8 && extra.bytes[0] == (byte)'H')
            {
                var eb = extra.bytes; int n = System.BitConverter.ToInt32(eb, 4);
                for (int i = 0; i < n && 16 + i * 8 <= eb.Length; i++)
                {
                    int bid = System.BitConverter.ToInt32(eb, 8 + i * 8); byte code = (byte)Mathf.Clamp(System.BitConverter.ToInt32(eb, 12 + i * 8), 1, 254);
                    if (bid < 0 || bid >= hidden.Length) continue;
                    if (hidden[bid] == 0 || code < hidden[bid]) { if (hidden[bid] == 0) nh++; hidden[bid] = code; }
                }
            }
            BuildPadMask();
            var tex = new Texture2D(256, 256, TextureFormat.R8, false, true) { name = "Alatau hidden buildings", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            tex.SetPixelData(hidden, 0); tex.Apply(false, false);
            Shader.SetGlobalTexture("_AlatauHideTex", tex); Shader.SetGlobalFloat("_AlatauHideOn", 1f);
            Debug.Log("[Alatau] landmark plots levelled; generic buildings replaced: " + nh + (mesh == null ? " (terrain mesh not readable)" : ""));
        }
        /// <summary>Plots of the landmarks as a mask over the map (same UVs as the base map, ≈ 21 m per texel): the line layers of the plan
        /// (street axes, ribbons) and the film roads are not drawn under a landmark (AlatauLit / AlatauRoad read _AlatauPadTex).</summary>
        void BuildPadMask()
        {
            const int W = 2048, H = 2898; var px = new byte[W * H];
            foreach (var l in Items)
            {
                if (l.IsLrt || l.PadW <= 0f) continue;
                float a = l.Yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a), hw = l.PadW * 0.5f + 3f, hd = l.PadD * 0.5f + 3f, R = Mathf.Sqrt(hw * hw + hd * hd);
                int x0 = Mathf.Max(0, (int)(U(l.X - R) * W)), x1 = Mathf.Min(W - 1, (int)(U(l.X + R) * W) + 1);
                int y0 = Mathf.Max(0, (int)(V(l.Z - R) * H)), y1 = Mathf.Min(H - 1, (int)(V(l.Z + R) * H) + 1);
                for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++)
                {
                    float wx = ((x + 0.5f) / W - 0.5f) / 2.29357798e-5f, wz = ((y + 0.5f) / H - 0.491085899f) / 1.62074554e-5f;
                    float dx = wx - l.X, dz = wz - l.Z, u = dx * ca - dz * sa, v = dx * sa + dz * ca;
                    if (Mathf.Abs(u) <= hw && Mathf.Abs(v) <= hd) px[y * W + x] = 255;
                }
            }
            var tex = new Texture2D(W, H, TextureFormat.R8, false, true) { name = "Alatau landmark plots", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            tex.SetPixelData(px, 0); tex.Apply(false, true);
            Shader.SetGlobalTexture("_AlatauPadTex", tex); Shader.SetGlobalFloat("_AlatauPadOn", 1f);
        }
        static float U(float x) => 2.29357798e-5f * x + 0.5f;
        static float V(float z) => 1.62074554e-5f * z + 0.491085899f;
        static float[] bounds; static int boundsN;
        /// <summary>Footprint (x0, z0, x1, z1) of every building of the plan, by bid — generated from CityData/layer_buildings.bytes.</summary>
        static void LoadBounds()
        {
            var ta = Resources.Load<TextAsset>("Landmarks/bid_bounds"); if (ta == null) { Debug.LogWarning("[Alatau] bid_bounds missing"); return; }
            var b = ta.bytes; if (b.Length < 8 || b[0] != 'A' || b[1] != 'B' || b[2] != 'B' || b[3] != '1') return;
            boundsN = System.BitConverter.ToInt32(b, 4); bounds = new float[boundsN * 4];
            System.Buffer.BlockCopy(b, 8, bounds, 0, Mathf.Min(bounds.Length * 4, b.Length - 8));
        }
        /// <summary>Oriented rectangle (centre, cos/sin of yaw, half sizes) against an axis-aligned box: separating axis test.</summary>
        static bool ObbHitsAabb(float cx, float cz, float ca, float sa, float hw, float hd, float x0, float z0, float x1, float z1)
        {
            // rectangle axes in world: u = (ca, -sa)·? — Unity yaw: local (u, v) -> world (u ca + v sa, -u sa + v ca)
            float ux = ca, uz = -sa, vx = sa, vz = ca;
            float ex = Mathf.Abs(ux) * hw + Mathf.Abs(vx) * hd, ez = Mathf.Abs(uz) * hw + Mathf.Abs(vz) * hd;
            if (cx + ex < x0 || cx - ex > x1 || cz + ez < z0 || cz - ez > z1) return false;          // world axes
            float bx = (x0 + x1) * 0.5f - cx, bz = (z0 + z1) * 0.5f - cz, bhx = (x1 - x0) * 0.5f, bhz = (z1 - z0) * 0.5f;
            float pu = bx * ux + bz * uz, ru = bhx * Mathf.Abs(ux) + bhz * Mathf.Abs(uz);
            if (Mathf.Abs(pu) > hw + ru) return false;
            float pv = bx * vx + bz * vz, rv = bhx * Mathf.Abs(vx) + bhz * Mathf.Abs(vz);
            if (Mathf.Abs(pv) > hd + rv) return false;
            return true;
        }
        public bool Ready => built;

        void Start() { TryBuild(); }
        void TryBuild()
        {
            if (built) return;
            if (CityGround.HeightAt(0, 0) == 0f) { Invoke(nameof(TryBuild), 0.25f); return; }   // terrain heights not loaded yet
            var sh = Shader.Find("AlatauCity/Landmark");
            if (sh == null) { Debug.LogWarning("[Alatau] AlatauCity/Landmark shader missing"); return; }
            mat = new Material(sh) { name = "Landmarks", enableInstancing = false };
            // the models with surfaces of their QTwin page get a variant of the shader with just their part (AlatauQTwin.cginc)
            matIconic = new Material(mat) { name = "Landmarks · Iconic (QTwin)" }; matIconic.EnableKeyword("ALATAU_QT_ICONIC");
            matKaist = new Material(mat) { name = "Landmarks · KAIST (QTwin)" }; matKaist.EnableKeyword("ALATAU_QT_KAIST");
            foreach (var l in Items) if (!l.IsLrt) Build(l);
            built = true;
            Debug.Log("[Alatau] landmarks: " + nodes.Count + " models");
        }

        void Build(Landmark l)
        {
            float gy = l.Base != 0f ? l.Base : Ground(l.X, l.Z, l.Radius * 0.5f);
            l.World = new Vector3(l.X, gy, l.Z);
            var go = new GameObject("Landmark · " + l.Name);
            go.transform.SetParent(transform, false);
            go.transform.SetPositionAndRotation(l.World, Quaternion.Euler(0, l.Yaw, 0));
            Mesh m; try { m = LandmarkModels.Build(l.Model, l.X * 0.001f); }
            catch (Exception e) { Debug.LogWarning("[Alatau] model " + l.Model + ": " + e.Message); return; }
            go.AddComponent<MeshFilter>().sharedMesh = m;
            var lm = l.Model == "iconic" && QTwinData.Bim() != null ? matIconic : l.Model == "campus" && QTwinData.Kaist() != null ? matKaist : mat;
            var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = lm; r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On; r.receiveShadows = true;
            var c = go.AddComponent<MeshCollider>(); c.sharedMesh = m;
            go.AddComponent<LandmarkObject>().Id = l.Id;
            var node = new Node { L = l, Go = go, R = r, C = c, B = new MaterialPropertyBlock() };
            for (int k = 0; k < 8; k++) { node.LastPP[k] = -1f; node.GlowP[k] = -1f; node.PA[k] = new Vector4(100000f, 0f, 100000f, 1f); node.PB[k] = new Vector4(-1f, l.Height, 0f, 0f); }
            nodes[l.Id] = node;
            l.Anchor = go.transform.TransformPoint(LandmarkSite.TopAnchor(m));
            try { BuildSite(node, m); } catch (Exception e) { Debug.LogWarning("[Alatau] site " + l.Id + ": " + e.Message); }
            if (l.Model == "airport")
            {
                // one airliner taking off in a loop once the airport works
                var pg = new GameObject("Airliner taking off"); pg.transform.SetParent(go.transform, false);
                pg.AddComponent<MeshFilter>().sharedMesh = LandmarkModels.PlaneMesh(); var pr = pg.AddComponent<MeshRenderer>(); pr.sharedMaterial = mat;
                node.Flyer = pg.transform; pg.SetActive(false);
            }
        }
        /// <summary>Take-off run on the airport's west runway (along +z): roll, rotate, climb out and leave; then again.</summary>
        static void Fly(Node n, float dt)
        {
            n.FlyT = (n.FlyT + dt) % 30f; float t = n.FlyT;
            float z, y = 0.45f, pitch = 0f; const float z0 = LandmarkModels.RwyLZ0 + 60f;
            if (t < 2.5f) z = z0;                                                                  // lined up
            else
            {
                float tr = t - 2.5f; z = z0 + 0.5f * 3.2f * tr * tr;                               // 3.2 m/s² roll
                if (z > 150f) { float tc = Mathf.Sqrt((150f - z0) / 1.6f); float ta = tr - tc; float v = 3.2f * tc; z = 150f + v * ta; y = 0.45f + Mathf.Pow(Mathf.Max(ta, 0f), 1.6f) * 2.6f; pitch = -Mathf.Clamp(ta * 3f, 0f, 9f); }
            }
            bool vis = t < 26f;
            if (n.Flyer.gameObject.activeSelf != vis) n.Flyer.gameObject.SetActive(vis);
            n.Flyer.localPosition = new Vector3(LandmarkModels.RwyLX, y, z); n.Flyer.localRotation = Quaternion.Euler(pitch, 0f, 0f);
        }

        /// <summary>Hoarding and tower cranes of the construction site (shown only while the object is being built).</summary>
        void BuildSite(Node n, Mesh model)
        {
            var l = n.L; if (l.PadW <= 0f) return;
            var site = new GameObject("Site · " + l.Name); site.transform.SetParent(n.Go.transform, false); n.Site = site;
            var f = new GameObject("Hoarding"); f.transform.SetParent(site.transform, false);
            f.AddComponent<MeshFilter>().sharedMesh = LandmarkSite.Fence(l.PadW, l.PadD); n.FenceR = f.AddComponent<MeshRenderer>(); n.FenceR.sharedMaterial = mat; n.FenceB = new MaterialPropertyBlock();
            float mastH = Mathf.Max(l.Height + 18f, 34f), jib = Mathf.Clamp(l.Height * 0.28f + 30f, 34f, 62f);
            var mastMesh = LandmarkSite.Mast(mastH); var headMesh = LandmarkSite.Head(jib);
            int i = 0;
            // KAIST: the three cranes of its page (by B1, the main hall, the laboratories); elsewhere free spots next to the highest part
            var kq = l.Id == "kaist" ? QTwinData.Kaist() : null;
            foreach (var spot in kq != null ? new List<Vector3>(kq.Cranes) : LandmarkSite.CraneSpots(model, l.PadW, l.PadD, l.Height))
            {
                var cr = new Crane { B = new MaterialPropertyBlock(), Yaw = (l.Id.GetHashCode() & 255) + i * 140f, Speed = (i & 1) == 0 ? 5.5f : -4f };
                var mg = new GameObject("Crane mast " + i); mg.transform.SetParent(site.transform, false); mg.transform.localPosition = spot;
                mg.AddComponent<MeshFilter>().sharedMesh = mastMesh; cr.MastR = mg.AddComponent<MeshRenderer>(); cr.MastR.sharedMaterial = mat; cr.Mast = mg.transform;
                var hg = new GameObject("Crane head " + i); hg.transform.SetParent(site.transform, false);
                hg.AddComponent<MeshFilter>().sharedMesh = headMesh; hg.AddComponent<MeshRenderer>().sharedMaterial = mat; cr.Head = hg.transform;
                n.Cranes.Add(cr); i++;
                if (l.Height < 30f) break;          // low plants: one crane is enough
            }
            site.SetActive(false);
        }
        /// <summary>Base of a site on sloping ground: the median of the terrain under it, so the plinth is half buried, never floating.</summary>
        static float Ground(float x, float z, float r)
        {
            var h = new List<float>(); h.Add(CityGround.HeightAt(x, z));
            for (int i = 0; i < 12; i++) { float a = i * Mathf.PI / 6f; for (int k = 1; k <= 2; k++) h.Add(CityGround.HeightAt(x + Mathf.Cos(a) * r * k * 0.5f, z + Mathf.Sin(a) * r * k * 0.5f)); }
            h.Sort(); return h[h.Count / 2];
        }

        public Landmark Get(string id) { foreach (var l in Items) if (l.Id == id) return l; return null; }
        /// <summary>The model of an object (its local frame: x along the long side, y up from the base).</summary>
        public Transform ModelOf(string id) => nodes.TryGetValue(id, out var n) && n.Go != null ? n.Go.transform : null;
        /// <summary>Is the point on a landmark's plot (with a margin)? Film trees and hedges keep off the plots.</summary>
        public static bool OnPlot(float x, float z, float margin = 4f)
        {
            var ls = Instance; if (ls == null) return false;
            foreach (var l in ls.Items)
            {
                if (l.IsLrt || l.PadW <= 0f) continue;
                float dx = x - l.X, dz = z - l.Z, a = l.Yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
                float u = dx * ca - dz * sa, v = dx * sa + dz * ca;                 // local frame of the plot (as CityGround.Flatten)
                if (Mathf.Abs(u) < l.PadW * 0.5f + margin && Mathf.Abs(v) < l.PadD * 0.5f + margin) return true;
                if (l.Ring > 0f && IconicDistrict.InGate(x, z)) return true;                                     // its district's area
            }
            return false;
        }

        /// <summary>Year shown by the city now (fractional while the timeline plays).</summary>
        /// <summary>A date set by the construction monitoring (4D timeline of one object), −1 = none: the landmarks are shown as of it.</summary>
        public static float YearOverride = -1f;
        public static float YearNow => YearOverride >= 0f ? YearOverride : TwinState.Playing || Shader.GetGlobalFloat("_AlatauGrow") > 0.5f ? Mathf.Max(Shader.GetGlobalFloat("_AlatauYearF"), TwinState.Year) : TwinState.Year;
        /// <summary>0 = not started, (0,1) = under construction, 1 = complete in the shown year.</summary>
        public static float Progress(Landmark l, float y)
        {
            if (l == null) return 0f;
            // a complex of several buildings: from the first start to the last hand-over
            if (l.Parts != null) { float a = l.Begin, b = l.Finish; return y <= a ? 0f : Mathf.Clamp01((y - a) / Mathf.Max(b - a, 0.01f)); }
            // works run through the start year: progress grows continuously from the end of the year before (no jump when the year turns)
            float s0 = l.StartYear - 1f;
            if (y <= s0) return 0f;
            return Mathf.Clamp01((y - s0) / (l.EndYear - l.StartYear + 1f));
        }
        /// <summary>Planned progress of building i of a complex (index in Landmark.Parts) at date y.</summary>
        public static float PlanPart(Landmark l, int i, float y)
        {
            if (l?.Parts == null || i < 0 || i >= l.Parts.Count) return Progress(l, y);
            var p = l.Parts[i]; return y <= p.A ? 0f : Mathf.Clamp01((y - p.A) / Mathf.Max(p.B - p.A, 0.01f));
        }
        /// <summary>The actual delay of building i at date y in years (set by the construction monitoring while it shows the actual; null = the plan).</summary>
        public static Func<Landmark, int, float, float> FactShift;
        /// <summary>Progress of building i as shown now: the plan, or the actual while the monitoring shows it.</summary>
        public static float PartP(Landmark l, int i, float y) => PlanPart(l, i, y - (FactShift != null ? FactShift(l, i, y) : 0f));
        /// <summary>Progress of the tower of a complex (the one followed floor by floor), else of the object.</summary>
        public static float TowerP(Landmark l, float y) { int m = l != null && l.Parts != null ? l.Main : -1; return m >= 0 ? PartP(l, m, y) : Progress(l, y); }
        /// <summary>Building of a complex outlined in the monitoring (landmark id, index in Parts; −1 none).</summary>
        public static string HiObj; public static int HiPart = -1;
        public bool IsBuilt(Landmark l) => Progress(l, YearNow) >= 0.999f;
        public bool IsVisible(Landmark l) => l.IsLrt || Progress(l, YearNow) > 0f || ShowPlanned;

        // ------------------------------------------------------------------ per frame
        void Update()
        {
            if (!built) return;
            float y = YearNow;
            HoverPick();
            foreach (var n in nodes.Values) Apply(n, y, Time.deltaTime, false);
            if (Input.GetKeyDown(KeyCode.Escape) && Selected != null && !MapCamera.Typing && !IconicInterior.EscTaken) Select(null, false);
        }
        /// <summary>Shows landmark id as of date y in the next picture taken (the construction monitoring compares two surveys in one
        /// frame: it renders the second date, then calls ApplyAt(id, YearNow) to put the first one back). No hand-over light, nothing moves.</summary>
        public void ApplyAt(string id, float y) { if (built && nodes.TryGetValue(id, out var n)) Apply(n, y, 0f, true); }
        /// <summary>The stages of one landmark at date y for the shader, its site and cranes. probe: a picture of another date (ApplyAt),
        /// the hand-over light and what remembers the last frame are left alone.</summary>
        void Apply(Node n, float y, float dt, bool probe)
        {
            float p = Progress(n.L, y);
            bool ghost = p <= 0f && ShowPlanned;
            bool on = p > 0f || ghost;
            if (n.Go.activeSelf != on) n.Go.SetActive(on);
            // completion: a sweep of light runs up the building once, in the moment it is handed over
            if (!probe)
            {
                if (n.lastP >= 0f && n.lastP < 0.999f && p >= 0.999f) n.glow = 0f;
                n.lastP = p;
                if (n.glow >= 0f) { n.glow += dt / 2.6f; if (n.glow > 1f) n.glow = -1f; }
            }
            if (!on) return;
            float target = (n.L == Selected ? 0.12f : 0f) + (n.L == Hovered ? 0.45f : 0f);
            n.hi = Mathf.MoveTowards(n.hi, Mathf.Min(target, 0.9f), dt * 3f);
            bool building = !ghost && p < 0.999f;
            float H = n.L.Height;
            // stages: site + excavation → frame rises → facade follows bottom-up → paving and planting → handed over
            float frame = H * Mathf.Clamp01((p - 0.08f) / 0.62f), facade = H * Mathf.Clamp01((p - 0.25f) / 0.65f), land = Mathf.Clamp01((p - 0.85f) / 0.13f);
            n.R.GetPropertyBlock(n.B);
            float reveal = ghost || !building ? 100000f : Mathf.Max(frame, 0.6f);
            if (CutAt >= 0f && n.L.Id == CutId) reveal = Mathf.Min(reveal, CutAt);
            n.B.SetFloat(RevealId, reveal);
            n.B.SetFloat(BuildId, building ? 1f : 0f);
            n.B.SetFloat(FacadeId, building ? facade : 100000f);
            n.B.SetFloat(LandId, building ? land : 1f);
            n.B.SetFloat(GlowId, probe ? -1f : n.glow);
            n.B.SetFloat(HeightId, H);
            n.B.SetFloat(GhostId, ghost ? 1f : 0f);
            n.B.SetFloat(HiId, n.hi);
            if (n.L.Parts != null) Parts(n, y, ghost, dt, probe);
            n.R.SetPropertyBlock(n.B);
            if (n.Flyer != null && !probe) { bool f = !ghost && !building; if (!f && n.Flyer.gameObject.activeSelf) n.Flyer.gameObject.SetActive(false); if (f) Fly(n, dt); }
            // site: hoarding and cranes while building (the cranes leave once the facade is closed)
            if (n.Site != null)
            {
                bool siteOn = building && p > 0f;
                if (n.Site.activeSelf != siteOn) n.Site.SetActive(siteOn);
                if (siteOn)
                {
                    // the cranes serve the tallest building (the tower of a complex): they climb with its frame and leave with its facade
                    float tp = n.L.Parts != null ? TowerP(n.L, y) : p, th = n.L.Parts != null && n.L.Main >= 0 ? n.L.Parts[n.L.Main].H : H;
                    bool cranes = tp > 0f && tp < 0.93f;
                    float top = Mathf.Max(th * Mathf.Clamp01((tp - 0.08f) / 0.62f) + 14f, 34f);
                    foreach (var c in n.Cranes)
                    {
                        if (c.Mast.gameObject.activeSelf != cranes) { c.Mast.gameObject.SetActive(cranes); c.Head.gameObject.SetActive(cranes); }
                        if (!cranes) continue;
                        c.MastR.GetPropertyBlock(c.B); c.B.SetFloat(RevealId, top); c.B.SetFloat(BuildId, 0f); c.B.SetFloat(GlowId, -1f); c.B.SetFloat(LandId, 1f); c.B.SetFloat(FacadeId, 100000f); c.MastR.SetPropertyBlock(c.B);
                        c.Yaw += c.Speed * dt * (0.6f + 0.4f * Mathf.Sin(Time.time * 0.21f + c.Speed));
                        c.Head.localPosition = c.Mast.localPosition + Vector3.up * (top - 0.3f);
                        c.Head.localRotation = Quaternion.Euler(0f, c.Yaw, 0f);
                    }
                }
            }
        }
        readonly Vector4[] diffA = new Vector4[8]; readonly float[] diffW = new float[8]; MaterialPropertyBlock headB;
        /// <summary>"Что изменилось" of the construction monitoring: landmark id as of the earlier survey y0 goes to the shader beside
        /// the current date y1 (shown only by a camera that sets _AlatauDiff); the site then and now is remembered for DiffSite.
        /// y0 &lt; 0: off. Called when the dates change, not every frame (it applies both dates).</summary>
        public void DiffFrom(string id, float y0, float y1)
        {
            if (!built || !nodes.TryGetValue(id, out var n)) return;
            if (y0 < 0f)
            {
                if (n.R != null) { n.R.GetPropertyBlock(n.B); n.B.SetFloat(DiffOnId, 0f); n.R.SetPropertyBlock(n.B); }
                return;
            }
            Apply(n, y0, 0f, true);
            bool was = n.Go.activeSelf && Progress(n.L, y0) > 0f;
            n.R.GetPropertyBlock(n.B);
            for (int k = 0; k < 8; k++) { diffA[k] = was ? n.PA[k] : new Vector4(-1000f, 1f, -1000f, 0f); diffW[k] = was ? n.PB[k].w : 0f; }
            diffA[0] = was ? new Vector4(n.B.GetFloat(RevealId), n.B.GetFloat(BuildId), n.B.GetFloat(FacadeId), n.B.GetFloat(LandId)) : new Vector4(-1000f, 1f, -1000f, 0f);
            n.Site0 = n.Site != null && n.Site.activeSelf; n.Cr0 = n.Site0 && n.Cranes.Count > 0 && n.Cranes[0].Mast.gameObject.activeSelf;
            Apply(n, y1, 0f, true);
            n.Site1 = n.Site != null && n.Site.activeSelf; n.Cr1 = n.Site1 && n.Cranes.Count > 0 && n.Cranes[0].Mast.gameObject.activeSelf;
            n.R.GetPropertyBlock(n.B);
            n.B.SetFloat(DiffOnId, 1f); n.B.SetVectorArray(DiffAId, diffA); n.B.SetFloatArray(DiffWId, diffW);
            n.R.SetPropertyBlock(n.B);
        }
        /// <summary>The site in the diff: whether the hoarding and the cranes stood at the earlier survey and stand now.</summary>
        public bool DiffSite(string id, out bool site0, out bool site1, out bool cr0, out bool cr1, out int cranes)
        {
            site0 = site1 = cr0 = cr1 = false; cranes = 0;
            if (!nodes.TryGetValue(id, out var n)) return false;
            site0 = n.Site0; site1 = n.Site1; cr0 = n.Cr0; cr1 = n.Cr1; cranes = n.Cranes.Count; return true;
        }
        /// <summary>Around the render of the monitoring camera: the hoarding and the cranes of both dates are shown and coloured (new
        /// blue, gone red, standing grey); off puts the site back as it is now.</summary>
        public void DiffShow(string id, bool on)
        {
            if (!nodes.TryGetValue(id, out var n) || n.Site == null) return;
            float fence = !on ? 0f : n.Site1 && n.Site0 ? 3f : n.Site1 ? 1f : n.Site0 ? 2f : 0f;
            float crane = !on ? 0f : n.Cr1 && n.Cr0 ? 3f : n.Cr1 ? 1f : n.Cr0 ? 2f : 0f;
            bool siteOn = on ? n.Site0 || n.Site1 : n.Site1, crOn = on ? n.Cr0 || n.Cr1 : n.Cr1;
            if (n.Site.activeSelf != siteOn) n.Site.SetActive(siteOn);
            if (headB == null) headB = new MaterialPropertyBlock();
            if (n.FenceR != null) { if (n.FenceB == null) n.FenceB = new MaterialPropertyBlock(); n.FenceR.GetPropertyBlock(n.FenceB); n.FenceB.SetFloat(DiffTintId, fence); n.FenceR.SetPropertyBlock(n.FenceB); }
            foreach (var c in n.Cranes)
            {
                if (c.Mast.gameObject.activeSelf != crOn) { c.Mast.gameObject.SetActive(crOn); c.Head.gameObject.SetActive(crOn); }
                c.MastR.GetPropertyBlock(c.B); c.B.SetFloat(DiffTintId, crane); c.MastR.SetPropertyBlock(c.B);
                var hr = c.Head.GetComponent<MeshRenderer>();
                if (hr != null) { hr.GetPropertyBlock(headB); headB.SetFloat(DiffTintId, crane); hr.SetPropertyBlock(headB); }
            }
        }
        /// <summary>Stages of every building of a complex for the shader: each rises, gets its facade and its grounds on its own dates
        /// (part 0, the plot, follows the whole complex). Not started → not drawn; handed over → a sweep of light runs up it.</summary>
        void Parts(Node n, float y, bool ghost, float dt, bool probe)
        {
            var l = n.L; int main = l.Main;
            for (int i = 0; i < l.Parts.Count && i < 7; i++)
            {
                var pt = l.Parts[i]; float pp = PartP(l, i, y); int k = i + 1;
                if (!probe)
                {
                    if (n.LastPP[k] >= 0f && n.LastPP[k] < 0.999f && pp >= 0.999f) n.GlowP[k] = 0f;
                    n.LastPP[k] = pp;
                    if (n.GlowP[k] >= 0f) { n.GlowP[k] += dt / 2.6f; if (n.GlowP[k] > 1f) n.GlowP[k] = -1f; }
                }
                bool b = !ghost && pp < 0.999f; float h = pt.H;
                float fr = h * Mathf.Clamp01((pp - 0.08f) / 0.62f), fa = h * Mathf.Clamp01((pp - 0.25f) / 0.65f), la = Mathf.Clamp01((pp - 0.85f) / 0.13f);
                if (pt.Land) { fr = 100000f; fa = 100000f; la = Mathf.Clamp01((pp - 0.05f) / 0.9f); }
                float rv = ghost || !b ? 100000f : pp <= 0f ? 0f : Mathf.Max(fr, 0.6f);
                if (CutAt >= 0f && l.Id == CutId && i == main) rv = Mathf.Min(rv, CutAt);
                n.PA[k] = new Vector4(rv, b ? 1f : 0f, b ? fa : 100000f, b ? la : 1f);
                n.PB[k] = new Vector4(probe ? -1f : n.GlowP[k], h, HiObj == l.Id && HiPart == i ? 1f : 0f, ghost ? 1f : pp);      // w: progress, for the pieces' own windows
            }
            n.PA[0] = new Vector4(-1f, 0f, 0f, 0f);                // slot 0 unused: part 0 takes the object's own values
            n.B.SetVectorArray(PartAId, n.PA); n.B.SetVectorArray(PartBId, n.PB);
        }
        /// <summary>Tower cranes of the site of a landmark: how many, and the top of the mast of crane i (the landmark's local coordinates)
        /// while that crane stands — a site camera can hang on it.</summary>
        public int CraneCount(string id) => nodes.TryGetValue(id, out var n) ? n.Cranes.Count : 0;
        public bool CraneTop(string id, int i, out Vector3 p)
        {
            p = default;
            if (!nodes.TryGetValue(id, out var n) || n.Site == null || !n.Site.activeSelf || i < 0 || i >= n.Cranes.Count) return false;
            var c = n.Cranes[i]; if (c.Head == null || !c.Head.gameObject.activeSelf) return false;
            p = c.Head.localPosition; return true;
        }
        /// <summary>Which building of a complex is under the ray (index in Landmark.Parts; −1 none or the plot).</summary>
        public int PickPart(string id, Ray ray, out Vector3 point)
        {
            point = default;
            if (!nodes.TryGetValue(id, out var n) || n.C == null || n.L.Parts == null) return -1;
            if (!n.C.Raycast(ray, out var hit, 100000f)) return -1;
            point = hit.point;
            var m = n.C.sharedMesh; if (m == null) return -1;
            if (n.PartUv == null) { n.PartUv = new List<Vector2>(); m.GetUVs(2, n.PartUv); n.Tris = m.triangles; }
            int t = hit.triangleIndex * 3; if (n.Tris == null || t < 0 || t >= n.Tris.Length) return -1;
            int v = n.Tris[t]; if (v >= n.PartUv.Count) return -1;
            int part = Mathf.RoundToInt(n.PartUv[v].x) - 1;
            return part >= 0 && part < n.L.Parts.Count ? part : -1;
        }
        void LateUpdate() { if (built) FlyStep(); FrameShift(); }     // after MapCamera.Update: the user's input of this frame is known

        float shift; bool shifted;
        /// <summary>While a passport is open the picture is shifted (off-centre projection) so the building stands in the free part of the
        /// screen between the passport on the left and the panels on the right, not behind the card. Picking and labels use the same matrix.</summary>
        void FrameShift()
        {
            var cam = Camera.main; if (cam == null) return;
            float want = Selected != null && !Selected.IsLrt ? 0.035f : 0f;     // the passport stands on the right now: a nudge to the centre of the free area
            shift = Mathf.MoveTowards(shift, want, Time.unscaledDeltaTime * 0.22f);
            if (shift > 0.0005f) { cam.ResetProjectionMatrix(); var P = cam.projectionMatrix; P.m02 = -shift; cam.projectionMatrix = P; shifted = true; }
            else if (shifted) { cam.ResetProjectionMatrix(); shifted = false; }
        }

        void HoverPick()
        {
            Landmark h = null;
            var cam = Camera.main;
            if (cam != null && !MapCamera.BlockInput && !TwinTour.Running && !IconicInterior.Active && !Input.GetMouseButton(0) && !Input.GetMouseButton(1))
            {
                var ray = cam.ScreenPointToRay(Input.mousePosition); float best = float.MaxValue;
                foreach (var n in nodes.Values)
                {
                    if (!n.Go.activeInHierarchy) continue;
                    if (n.C.Raycast(ray, out var hit, 200000f) && hit.distance < best) { best = hit.distance; h = n.L; }
                }
            }
            Hovered = h;
        }

        // ------------------------------------------------------------------ selection + camera
        public void Select(Landmark l, bool fly = true)
        {
            Selected = l;
            if (l != null)
            {
                // a landmark replaces the building passport
                var ts = Camera.main != null ? Camera.main.GetComponent<TwinSelector>() : null;
                if (TwinState.Selected != null) { if (ts != null) ts.Select(-1); else TwinState.SetSelected(null); }
                if (fly) FlyTo(l);
            }
            else { flyT = -1f; orbitAt = null; orbitLift = -1f; var mc = Cam; if (mc != null) mc.holdLift = false; }
            OnSelected?.Invoke(l);
            if (UI.TwinUI.Instance != null) UI.TwinUI.Instance.RefreshCard();
        }
        public void SelectById(string id, bool fly = true) => Select(Get(id), fly);

        static MapCamera Cam => Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
        /// <summary>The viewer's choice: slow orbit around the selected object (button in the passport).</summary>
        public static bool OrbitOn = true;
        // cinematic fly: log-distance zoom, the target leads a little, ease in/out; then the orbit (paused while the user moves the camera)
        float flyT = -1f, flyDur, idle; Vector3 f0, f1; float d0, d1, y0, y1, p0, p1, l0, l1;
        /// <summary>The camera is on its way to an object (FlyTo).</summary>
        public bool Flying => flyT >= 0f;

        /// <summary>Distance at which the whole object fills about 80 % of the frame.</summary>
        static float FrameDistance(Landmark l)
        {
            var cam = Camera.main; float fov = cam != null ? cam.fieldOfView : 40f;
            float rb = Mathf.Sqrt(l.Radius * l.Radius + l.Height * l.Height * 0.25f);
            return Mathf.Max(rb / Mathf.Sin(fov * 0.5f * Mathf.Deg2Rad) * 1.3f, 300f);
        }
        static float FrameLift(Landmark l) => Mathf.Min(l.Height * 0.5f, 150f);

        public void FlyTo(Landmark l, Vector3? at = null, float? dist = null, float? lift = null, float? pitch = null)
        {
            var mc = Cam; if (mc == null) return; mc.StopFly();
            if (lift == null) { orbitAt = null; orbitLift = -1f; }
            Vector3 c = at ?? l.World;
            float dEnd = dist ?? FrameDistance(l);
            float liftEnd = lift ?? (at.HasValue ? 0f : FrameLift(l));
            if (l.IsLrt && !at.HasValue) { c = new Vector3(-700f, 0f, -1500f); dEnd = 64000f; liftEnd = 0f; }
            f0 = mc.target; f0.y = 0; f1 = new Vector3(c.x, 0, c.z);
            d0 = mc.distance; d1 = dEnd; y0 = mc.yaw; y1 = at.HasValue ? mc.yaw : l.Yaw + l.ViewYaw; p0 = mc.pitch; p1 = pitch ?? (l.IsLrt && !at.HasValue ? 52f : at.HasValue ? 24f : l.ViewPitch);
            l0 = mc.lift; l1 = liftEnd;
            float ratio = Mathf.Abs(Mathf.Log(Mathf.Max(d0, 1f) / Mathf.Max(d1, 1f)));
            flyDur = Mathf.Clamp(1.8f + 0.55f * ratio + Vector3.Distance(f0, f1) / 40000f, 2.0f, 5.0f);
            flyT = 0f; idle = 0f; mc.holdLift = true;
        }

        void FlyStep()
        {
            var mc = Cam; if (mc == null) return;
            if (IconicInterior.Active) { flyT = -1f; return; }                                  // inside the tower: the interior drives the camera
            if (mc.IsFlying) { if (flyT >= 0f) flyT = -1f; mc.holdLift = false; return; }       // someone else (home view, district, tour) moves the camera
            if (MapCamera.UserMoved) { flyT = -1f; idle = 0f; return; }                         // the user takes over; the orbit waits
            float dt = TwinTour.VideoMode ? TwinState.RealDelta : Time.deltaTime;               // the recorded video: the camera keeps its pace whatever the scene's speed-up
            if (flyT >= 0f)
            {
                flyT += dt / flyDur; float t = Mathf.Clamp01(flyT);
                float e = t * t * (3f - 2f * t);                    // ease in/out
                float lead = 1f - Mathf.Pow(1f - t, 2.2f);          // the target centres early, the zoom follows
                float le = lead * lead * (3f - 2f * lead);
                var tg = Vector3.Lerp(f0, f1, le);
                float d = Mathf.Exp(Mathf.Lerp(Mathf.Log(Mathf.Max(d0, 1f)), Mathf.Log(Mathf.Max(d1, 1f)), e));
                mc.SetPose(tg, d, Mathf.LerpAngle(y0, y1, e), Mathf.Lerp(p0, p1, e), Mathf.Lerp(l0, l1, e));
                if (t >= 1f) { flyT = -1f; idle = 10f; }            // arrived: the orbit starts at once
                return;
            }
            var sel = Selected;
            if (sel == null || sel.IsLrt) return;
            var oc = orbitAt ?? sel.World; var site = new Vector3(oc.x, 0f, oc.z); var cur = mc.target; cur.y = 0f;
            bool near = Vector3.Distance(cur, site) < sel.Radius * 4f + 200f;
            mc.holdLift = near;
            idle += dt;
            if (!OrbitOn || !near || idle < 2.5f || TwinTour.Running && TwinTour.HoldCamera) return;
            // orbit: ramps up softly, drifts back to the object's centre and to its mid-height pivot
            float spd = 6f * Mathf.Clamp01((idle - 2.5f) / 1.5f);
            float k = 1f - Mathf.Exp(-1.2f * dt);
            var tgt = Vector3.Lerp(cur, site, k);
            mc.SetPose(tgt, mc.distance, mc.yaw + spd * dt, mc.pitch, Mathf.Lerp(mc.lift, orbitLift >= 0f ? orbitLift : FrameLift(sel), k));
        }
        // close-up: the orbit circles the point looked at, at its height
        Vector3? orbitAt; float orbitLift = -1f;
        /// <summary>The camera comes close to the object: for a building under construction to the working level (fresh frame, cranes),
        /// otherwise to the middle of its height, near enough to read the facade.</summary>
        public void CloseUp(Landmark l)
        {
            if (l == null || l.IsLrt) return;
            if (Selected != l) Select(l, false);
            var model = ModelOf(l.Id);
            Vector3 c = l.World; float h = Mathf.Min(l.Height * 0.5f, 150f);
            float p = TowerP(l, YearNow);
            if (p > 0f && p < 0.999f) h = Mathf.Max(l.Height * Mathf.Clamp01((p - 0.08f) / 0.62f) - 6f, 8f);
            var tp = TowerProfile.For(l.Id);
            if (tp != null && model != null) c = model.TransformPoint(new Vector3(tp.Xr - tp.RawWidth(h) * 0.5f, 0f, tp.Cz));
            float dist = Mathf.Clamp(Mathf.Max(l.Radius, l.Height * 0.25f) * 0.9f, 70f, 260f);
            FlyTo(l, c, dist, h, 10f);
            orbitAt = c; orbitLift = h;
        }
        public bool Orbiting => OrbitOn && Selected != null && !Selected.IsLrt;
        public void ToggleOrbit() { OrbitOn = !OrbitOn; idle = 10f; }
        /// <summary>Look at a point of the LRT (a station) without a model.</summary>
        public void FlyToPoint(Landmark l, Vector3 p, float dist) { Selected = l; OnSelected?.Invoke(l); FlyTo(l, p, dist); if (UI.TwinUI.Instance != null) UI.TwinUI.Instance.RefreshCard(); }
    }
}
