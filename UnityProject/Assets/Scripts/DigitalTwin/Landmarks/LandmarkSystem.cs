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
        }
        readonly Dictionary<string, Node> nodes = new Dictionary<string, Node>();
        Material mat; bool built;
        static readonly int RevealId = Shader.PropertyToID("_Reveal"), BuildId = Shader.PropertyToID("_Build"), GhostId = Shader.PropertyToID("_Ghost"), HiId = Shader.PropertyToID("_Hi"),
            FacadeId = Shader.PropertyToID("_Facade"), LandId = Shader.PropertyToID("_Land"), GlowId = Shader.PropertyToID("_Glow"), HeightId = Shader.PropertyToID("_H");

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
        /// <summary>Generic buildings of the plan that a landmark replaces (hidden in AlatauLit, not pickable).</summary>
        public static bool IsHiddenBid(int bid) => hidden != null && bid >= 0 && bid < hidden.Length && hidden[bid] != 0 && (hidden[bid] == 1 || TwinState.Year >= 2000 + hidden[bid]);

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
                        if (x1 <= x0 || x1 < l.X - R || x0 > l.X + R || z1 < l.Z - R || z0 > l.Z + R) continue;
                        if (!ObbHitsAabb(l.X, l.Z, ca, sa, hw, hd, x0, z0, x1, z1)) continue;
                        var bi = db?.Get(bid);
                        byte code = bi != null && bi.Source == "existing_osm" ? (byte)Mathf.Clamp(l.StartYear - 2000, 2, 254) : (byte)1;
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
            var r = go.AddComponent<MeshRenderer>(); r.sharedMaterial = mat; r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.On; r.receiveShadows = true;
            var c = go.AddComponent<MeshCollider>(); c.sharedMesh = m;
            go.AddComponent<LandmarkObject>().Id = l.Id;
            var node = new Node { L = l, Go = go, R = r, C = c, B = new MaterialPropertyBlock() };
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
            f.AddComponent<MeshFilter>().sharedMesh = LandmarkSite.Fence(l.PadW, l.PadD); f.AddComponent<MeshRenderer>().sharedMaterial = mat;
            float mastH = Mathf.Max(l.Height + 18f, 34f), jib = Mathf.Clamp(l.Height * 0.28f + 30f, 34f, 62f);
            var mastMesh = LandmarkSite.Mast(mastH); var headMesh = LandmarkSite.Head(jib);
            int i = 0;
            foreach (var spot in LandmarkSite.CraneSpots(model, l.PadW, l.PadD, l.Height))
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
            // works run through the start year: progress grows continuously from the end of the year before (no jump when the year turns)
            float s0 = l.StartYear - 1f;
            if (y <= s0) return 0f;
            return Mathf.Clamp01((y - s0) / (l.EndYear - l.StartYear + 1f));
        }
        public bool IsBuilt(Landmark l) => Progress(l, YearNow) >= 0.999f;
        public bool IsVisible(Landmark l) => l.IsLrt || Progress(l, YearNow) > 0f || ShowPlanned;

        // ------------------------------------------------------------------ per frame
        void Update()
        {
            if (!built) return;
            float y = YearNow;
            HoverPick();
            foreach (var n in nodes.Values)
            {
                float p = Progress(n.L, y);
                bool ghost = p <= 0f && ShowPlanned;
                bool on = p > 0f || ghost;
                if (n.Go.activeSelf != on) n.Go.SetActive(on);
                // completion: a sweep of light runs up the building once, in the moment it is handed over
                if (n.lastP >= 0f && n.lastP < 0.999f && p >= 0.999f) n.glow = 0f;
                n.lastP = p;
                if (n.glow >= 0f) { n.glow += Time.deltaTime / 2.6f; if (n.glow > 1f) n.glow = -1f; }
                if (!on) continue;
                float target = (n.L == Selected ? 0.12f : 0f) + (n.L == Hovered ? 0.45f : 0f);
                n.hi = Mathf.MoveTowards(n.hi, Mathf.Min(target, 0.9f), Time.deltaTime * 3f);
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
                n.B.SetFloat(GlowId, n.glow);
                n.B.SetFloat(HeightId, H);
                n.B.SetFloat(GhostId, ghost ? 1f : 0f);
                n.B.SetFloat(HiId, n.hi);
                n.R.SetPropertyBlock(n.B);
                if (n.Flyer != null) { bool f = !ghost && !building; if (!f && n.Flyer.gameObject.activeSelf) n.Flyer.gameObject.SetActive(false); if (f) Fly(n, Time.deltaTime); }
                // site: hoarding and cranes while building (the cranes leave once the facade is closed)
                if (n.Site != null)
                {
                    bool siteOn = building && p > 0f;
                    if (n.Site.activeSelf != siteOn) n.Site.SetActive(siteOn);
                    if (siteOn)
                    {
                        bool cranes = p < 0.93f;
                        float top = Mathf.Max(frame + 14f, 34f);
                        foreach (var c in n.Cranes)
                        {
                            if (c.Mast.gameObject.activeSelf != cranes) { c.Mast.gameObject.SetActive(cranes); c.Head.gameObject.SetActive(cranes); }
                            if (!cranes) continue;
                            c.MastR.GetPropertyBlock(c.B); c.B.SetFloat(RevealId, top); c.B.SetFloat(BuildId, 0f); c.B.SetFloat(GlowId, -1f); c.B.SetFloat(LandId, 1f); c.B.SetFloat(FacadeId, 100000f); c.MastR.SetPropertyBlock(c.B);
                            c.Yaw += c.Speed * Time.deltaTime * (0.6f + 0.4f * Mathf.Sin(Time.time * 0.21f + c.Speed));
                            c.Head.localPosition = c.Mast.localPosition + Vector3.up * (top - 0.3f);
                            c.Head.localRotation = Quaternion.Euler(0f, c.Yaw, 0f);
                        }
                    }
                }
            }
            if (Input.GetKeyDown(KeyCode.Escape) && Selected != null && !MapCamera.Typing && !IconicInterior.EscTaken) Select(null, false);
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
            if (flyT >= 0f)
            {
                flyT += Time.deltaTime / flyDur; float t = Mathf.Clamp01(flyT);
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
            idle += Time.deltaTime;
            if (!OrbitOn || !near || idle < 2.5f || TwinTour.Running && TwinTour.HoldCamera) return;
            // orbit: ramps up softly, drifts back to the object's centre and to its mid-height pivot
            float spd = 6f * Mathf.Clamp01((idle - 2.5f) / 1.5f);
            float k = 1f - Mathf.Exp(-1.2f * Time.deltaTime);
            var tgt = Vector3.Lerp(cur, site, k);
            mc.SetPose(tgt, mc.distance, mc.yaw + spd * Time.deltaTime, mc.pitch, Mathf.Lerp(mc.lift, orbitLift >= 0f ? orbitLift : FrameLift(sel), k));
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
            float p = Progress(l, YearNow);
            if (p > 0f && p < 0.999f) h = Mathf.Max(l.Height * Mathf.Clamp01((p - 0.08f) / 0.62f) - 6f, 8f);
            if (l.Id == "iconic" && model != null) c = model.TransformPoint(new Vector3(IconicShape.Xr - IconicShape.RawWidth(h) * 0.5f, 0f, IconicShape.Cz));
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
