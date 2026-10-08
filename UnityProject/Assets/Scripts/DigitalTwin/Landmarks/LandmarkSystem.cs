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

        class Node { public Landmark L; public GameObject Go; public MeshRenderer R; public MeshCollider C; public MaterialPropertyBlock B; public float hi; }
        readonly Dictionary<string, Node> nodes = new Dictionary<string, Node>();
        Material mat; bool built;
        static readonly int RevealId = Shader.PropertyToID("_Reveal"), BuildId = Shader.PropertyToID("_Build"), GhostId = Shader.PropertyToID("_Ghost"), HiId = Shader.PropertyToID("_Hi");

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
        public static bool IsHiddenBid(int bid) => hidden != null && bid >= 0 && bid < hidden.Length && hidden[bid] != 0;

        /// <summary>Before anything is draped on the terrain (roads, trees, networks, LRT): every plot is levelled to one height with a soft
        /// edge, the terrain mesh follows, the generic buildings standing on the plot are hidden, and an invisible slab keeps the trees off it.</summary>
        void PrepareGround()
        {
            var tgo = GameObject.Find("Terrain (master plan map)");
            Mesh mesh = null; Vector3[] verts = null;
            var mf = tgo != null ? tgo.GetComponent<MeshFilter>() : null;
            if (mf != null && mf.sharedMesh != null && mf.sharedMesh.isReadable) { mesh = mf.mesh; verts = mesh.vertices; }
            hidden = new byte[256 * 256]; int nh = 0;
            var db = CityDatabase.Instance;
            foreach (var l in Items)
            {
                if (l.IsLrt || l.PadW <= 0f) continue;
                float lvl = Ground(l.X, l.Z, Mathf.Max(l.PadW, l.PadD) * 0.5f);
                l.Base = lvl;
                var idx = CityGround.Flatten(l.X, l.Z, l.Yaw, l.PadW + 16f, l.PadD + 16f, lvl - 0.05f, 80f);
                if (verts != null) foreach (var i in idx) if (i < verts.Length) verts[i].y = CityGround.RawHeight(i);
                float a = l.Yaw * Mathf.Deg2Rad, ca = Mathf.Cos(a), sa = Mathf.Sin(a);
                if (db != null)
                    foreach (var b in db.Buildings)
                    {
                        if (b == null || b.Source == "existing_osm" || b.Bid < 0 || b.Bid >= hidden.Length) continue;
                        float x = b.X - l.X, z = b.Z - l.Z; if (x * x + z * z > (l.PadW + l.PadD) * (l.PadW + l.PadD)) continue;
                        float u = x * ca - z * sa, v = x * sa + z * ca, br = Mathf.Sqrt(Mathf.Max(b.GfaM2 / Mathf.Max(b.Floors, 1), 25f)) * 0.5f + 8f;
                        if (Mathf.Abs(u) <= l.PadW * 0.5f + br && Mathf.Abs(v) <= l.PadD * 0.5f + br) { hidden[b.Bid] = 1; nh++; }
                    }
                // an invisible slab over the plot: the film trees and hedges see "a building stands here" and keep off
                var blk = new GameObject("Plot · " + l.Name); blk.transform.SetParent(transform, false);
                blk.transform.SetPositionAndRotation(new Vector3(l.X, lvl, l.Z), Quaternion.Euler(0, l.Yaw, 0));
                var bc = blk.AddComponent<BoxCollider>(); bc.size = new Vector3(l.PadW, 3f, l.PadD); bc.center = Vector3.zero;
                blk.AddComponent<LandmarkObject>().Id = l.Id;
            }
            if (mesh != null) { mesh.vertices = verts; mesh.RecalculateNormals(); mesh.RecalculateBounds(); }
            var tex = new Texture2D(256, 256, TextureFormat.R8, false, true) { name = "Alatau hidden buildings", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
            tex.SetPixelData(hidden, 0); tex.Apply(false, false);
            Shader.SetGlobalTexture("_AlatauHideTex", tex); Shader.SetGlobalFloat("_AlatauHideOn", 1f);
            Debug.Log("[Alatau] landmark plots levelled; generic buildings replaced: " + nh + (mesh == null ? " (terrain mesh not readable)" : ""));
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
            nodes[l.Id] = new Node { L = l, Go = go, R = r, C = c, B = new MaterialPropertyBlock() };
        }
        /// <summary>Base of a site on sloping ground: the median of the terrain under it, so the plinth is half buried, never floating.</summary>
        static float Ground(float x, float z, float r)
        {
            var h = new List<float>(); h.Add(CityGround.HeightAt(x, z));
            for (int i = 0; i < 12; i++) { float a = i * Mathf.PI / 6f; for (int k = 1; k <= 2; k++) h.Add(CityGround.HeightAt(x + Mathf.Cos(a) * r * k * 0.5f, z + Mathf.Sin(a) * r * k * 0.5f)); }
            h.Sort(); return h[h.Count / 2];
        }

        public Landmark Get(string id) { foreach (var l in Items) if (l.Id == id) return l; return null; }

        /// <summary>Year shown by the city now (fractional while the timeline plays).</summary>
        public static float YearNow => TwinState.Playing || Shader.GetGlobalFloat("_AlatauGrow") > 0.5f ? Mathf.Max(Shader.GetGlobalFloat("_AlatauYearF"), TwinState.Year) : TwinState.Year;
        /// <summary>0 = not started, (0,1) = under construction, 1 = complete in the shown year.</summary>
        public static float Progress(Landmark l, float y)
        {
            if (y < l.StartYear) return 0f;
            return Mathf.Clamp01((y - l.StartYear + 1f) / (l.EndYear - l.StartYear + 1f));
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
                if (!on) continue;
                float target = (n.L == Selected ? 0.12f : 0f) + (n.L == Hovered ? 0.45f : 0f);
                n.hi = Mathf.MoveTowards(n.hi, Mathf.Min(target, 0.9f), Time.deltaTime * 3f);
                n.R.GetPropertyBlock(n.B);
                n.B.SetFloat(RevealId, ghost || p >= 0.999f ? 100000f : Mathf.Max(n.L.Height * p, 2f));
                n.B.SetFloat(BuildId, !ghost && p < 0.999f ? 1f : 0f);
                n.B.SetFloat(GhostId, ghost ? 1f : 0f);
                n.B.SetFloat(HiId, n.hi);
                n.R.SetPropertyBlock(n.B);
            }
            if (Input.GetKeyDown(KeyCode.Escape) && Selected != null && !MapCamera.Typing) Select(null, false);
        }
        void LateUpdate() { if (built) FlyStep(); FrameShift(); }     // after MapCamera.Update: the user's input of this frame is known

        float shift; bool shifted;
        /// <summary>While a passport is open the picture is shifted (off-centre projection) so the building stands in the free part of the
        /// screen between the passport on the left and the panels on the right, not behind the card. Picking and labels use the same matrix.</summary>
        void FrameShift()
        {
            var cam = Camera.main; if (cam == null) return;
            float want = Selected != null && !Selected.IsLrt ? 0.21f : 0f;
            shift = Mathf.MoveTowards(shift, want, Time.unscaledDeltaTime * 0.22f);
            if (shift > 0.0005f) { cam.ResetProjectionMatrix(); var P = cam.projectionMatrix; P.m02 = -shift; cam.projectionMatrix = P; shifted = true; }
            else if (shifted) { cam.ResetProjectionMatrix(); shifted = false; }
        }

        void HoverPick()
        {
            Landmark h = null;
            var cam = Camera.main;
            if (cam != null && !MapCamera.BlockInput && !TwinTour.Running && !Input.GetMouseButton(0) && !Input.GetMouseButton(1))
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
            else { flyT = -1f; var mc = Cam; if (mc != null) mc.holdLift = false; }
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

        public void FlyTo(Landmark l, Vector3? at = null, float? dist = null)
        {
            var mc = Cam; if (mc == null) return; mc.StopFly();
            Vector3 c = at ?? l.World;
            float dEnd = dist ?? FrameDistance(l);
            float liftEnd = at.HasValue ? 0f : FrameLift(l);
            if (l.IsLrt && !at.HasValue) { c = new Vector3(-700f, 0f, -1500f); dEnd = 64000f; liftEnd = 0f; }
            f0 = mc.target; f0.y = 0; f1 = new Vector3(c.x, 0, c.z);
            d0 = mc.distance; d1 = dEnd; y0 = mc.yaw; y1 = at.HasValue ? mc.yaw : l.Yaw + l.ViewYaw; p0 = mc.pitch; p1 = l.IsLrt && !at.HasValue ? 52f : at.HasValue ? 24f : l.ViewPitch;
            l0 = mc.lift; l1 = liftEnd;
            float ratio = Mathf.Abs(Mathf.Log(Mathf.Max(d0, 1f) / Mathf.Max(d1, 1f)));
            flyDur = Mathf.Clamp(1.8f + 0.55f * ratio + Vector3.Distance(f0, f1) / 40000f, 2.0f, 5.0f);
            flyT = 0f; idle = 0f; mc.holdLift = true;
        }

        void FlyStep()
        {
            var mc = Cam; if (mc == null) return;
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
            var site = new Vector3(sel.World.x, 0f, sel.World.z); var cur = mc.target; cur.y = 0f;
            bool near = Vector3.Distance(cur, site) < sel.Radius * 4f + 200f;
            mc.holdLift = near;
            idle += Time.deltaTime;
            if (!OrbitOn || !near || idle < 2.5f || TwinTour.Running && TwinTour.HoldCamera) return;
            // orbit: ramps up softly, drifts back to the object's centre and to its mid-height pivot
            float spd = 6f * Mathf.Clamp01((idle - 2.5f) / 1.5f);
            float k = 1f - Mathf.Exp(-1.2f * Time.deltaTime);
            var tgt = Vector3.Lerp(cur, site, k);
            mc.SetPose(tgt, mc.distance, mc.yaw + spd * Time.deltaTime, mc.pitch, Mathf.Lerp(mc.lift, FrameLift(sel), k));
        }
        public bool Orbiting => OrbitOn && Selected != null && !Selected.IsLrt;
        public void ToggleOrbit() { OrbitOn = !OrbitOn; idle = 10f; }
        /// <summary>Look at a point of the LRT (a station) without a model.</summary>
        public void FlyToPoint(Landmark l, Vector3 p, float dist) { Selected = l; OnSelected?.Invoke(l); FlyTo(l, p, dist); if (UI.TwinUI.Instance != null) UI.TwinUI.Instance.RefreshCard(); }
    }
}
