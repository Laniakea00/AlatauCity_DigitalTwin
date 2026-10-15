using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin.Landmarks
{
    /// <summary>Inside Iconic Complex: the camera dives into the tower, the building above the chosen floor is peeled away (a cut-away
    /// "doll's house" view of the floor plan) and the floor shows how far its construction has gone in the shown year — frame, facade,
    /// services, partitions, finishes, furniture (IconicFloors). Floors up and down, a walk-through at eye level, back out.
    /// Entry: «Внутрь башни» in the passport, double click on the tower, or I while the tower is selected. Esc = one step back.</summary>
    public class IconicInterior : MonoBehaviour
    {
        public static IconicInterior Instance;
        /// <summary>The building whose interior is shown (TowerProfile: Iconic Complex, the KAIST library tower).</summary>
        static string Id => IconicShape.P.Id;
        public static bool Active => Instance != null && Instance.active;
        public static bool Walking => Active && Instance.walk;
        /// <summary>Esc belongs to the interior in this frame (inside, or it has just been used to leave): the passport and the presentation keep it.</summary>
        public static bool EscTaken => Active || (Instance != null && Instance.escFrame >= Time.frameCount - 1);
        /// <summary>Set while the interior itself moves the map camera (it must not take that as "someone else moves the camera").</summary>
        public static bool Driving;
        /// <summary>Set while the monitoring window drives the camera, the cut and the floor shown (IconicMonitor): the interior waits.</summary>
        public static bool Suspended;
        public int Floor => floor;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Iconic Complex · interior").AddComponent<IconicInterior>(); }

        bool active, walk, leaving; int floor = -1, escFrame = -10;
        Landmark L; Transform model; Camera cam; MapCamera mc;
        GameObject floorGo, ceilGo; MeshFilter floorMf, ceilMf; Material mat; MaterialPropertyBlock mpb;
        int bFloor = -1, bPhase = -1, bStep = -1, bAbove = -1;
        IconicFloors.Info info;
        // cut-away orbit around the floor; walk-through (eye in the landmark's local frame)
        float oyaw, opitch = 50f, odist = 60f; Vector3 pivot;
        Vector3 eye; float wyaw, wpitch;
        // transition between two camera poses (and the cut of the building with it)
        float tr = -1f, trDur = 1f, cutFrom, cutTo, cutNow = -1f; Vector3 trPos; Quaternion trRot;
        Vector3 lastMouse; bool dragging, pressed; float lastClick = -10f; Vector3 clickPos;
        float uiT; string uiKey = "";

        void Awake() { Instance = this; mpb = new MaterialPropertyBlock(); }
        void OnEnable() { LandmarkSystem.OnSelected += OnSelected; }
        void OnDisable() { LandmarkSystem.OnSelected -= OnSelected; }
        void OnSelected(Landmark l) { if (active && !leaving && (l == null || l.Id != Id)) ExitNow(); }

        // ------------------------------------------------------------------ state
        static float H(Landmark l) => l != null ? l.Height : 272f;
        static float P(Landmark l) => LandmarkSystem.Progress(l, LandmarkSystem.YearNow);
        /// <summary>The highest floor whose works have started (−1: none yet).</summary>
        static int TopFloor(Landmark l, float p)
        {
            for (int i = IconicShape.Levels - 1; i >= 0; i--) if (IconicFloors.Phase(i, p, H(l), out _) > IconicFloors.PNone) return i;
            return -1;
        }
        /// <summary>The floor worth showing first: where the fit-out is going on, else the highest finished structure; a typical office floor once handed over.</summary>
        static int FirstFloor(Landmark l, float p)
        {
            if (p >= 0.999f) return 12;
            int best = -1;
            for (int i = IconicShape.Levels - 1; i >= 0; i--)
            {
                int ph = IconicFloors.Phase(i, p, H(l), out _);
                if (ph >= IconicFloors.PPartitions && ph < IconicFloors.PReady) return i;
                if (best < 0 && ph >= IconicFloors.PFacade) best = i;
            }
            return best >= 0 ? best : TopFloor(l, p);
        }
        public bool CanEnter(out string why) => CanEnter(Id, out why);
        public bool CanEnter(string id, out string why)
        {
            why = null; var ls = LandmarkSystem.Instance; var l = ls != null ? ls.Get(id) : null;
            var prof = TowerProfile.For(id); if (prof == null) { why = "нет модели этажей"; return false; }
            var keep = IconicShape.P; IconicShape.P = prof;
            try {
            if (l == null || !ls.Ready) { why = "модель ещё загружается"; return false; }
            if (TopFloor(l, P(l)) < 0) { why = "каркас ещё не начат"; return false; }
            return true;
            } finally { IconicShape.P = keep; }
        }

        public void Enter() => Enter(Id);
        /// <summary>Into the tower of landmark id (Iconic Complex, KAIST): its floors, as built in the shown year.</summary>
        public void Enter(string id)
        {
            var ls = LandmarkSystem.Instance; if (ls == null || !ls.Ready) return;
            var prof = TowerProfile.For(id); if (prof == null) return;
            if (active && prof != IconicShape.P) ExitNow();
            if (prof != IconicShape.P) { IconicShape.P = prof; bFloor = -1; }
            L = ls.Get(Id); if (L == null) return;
            // before the frame rises there is nothing to walk into: show the year the floors are going up
            if (TopFloor(L, P(L)) < 0) { TwinState.Year = Mathf.Min(L.StartYear + 1, L.EndYear); }
            float p = P(L); int f0 = FirstFloor(L, p); if (f0 < 0) return;
            model = ls.ModelOf(Id); cam = Camera.main; mc = cam != null ? cam.GetComponent<MapCamera>() : null;
            if (model == null || cam == null || mc == null) return;
            if (ls.Selected != L) ls.Select(L, false);
            active = true; leaving = false; walk = false; floor = f0;
            oyaw = cam.transform.eulerAngles.y; opitch = 50f;
            IconicFloors.Centre(floor, out float size); odist = size * 1.2f + 12f;
            EnsureObjects(); Rebuild(p, true); Pivot();
            Begin(2.6f, H(L) + 30f, CutFor());
            ShowPanel(true); Refresh(true);
            TwinUI.Instance?.RefreshCard();                     // the passport gives its place to the floor panel
        }
        /// <summary>Back out to the city: the camera rises to a view of the whole tower while the cut runs back up.</summary>
        public void Exit()
        {
            if (!active || leaving) return;
            leaving = true; walk = false;
            if (ceilGo != null) ceilGo.SetActive(false);
            // the map camera takes over from a view of the tower (its orbit continues from there)
            var c = model.TransformPoint(new Vector3(IconicShape.Xr - IconicShape.W0 * 0.42f, 0f, IconicShape.Cz));
            Driving = true; mc.SetPose(new Vector3(c.x, 0f, c.z), Mathf.Max(H(L) * 1.9f, 260f), cam.transform.eulerAngles.y, 18f, H(L) * 0.44f); Driving = false;
            Begin(2.0f, cutNow, H(L) + 30f);
            ShowPanel(false);
        }
        /// <summary>Leaves at once (another object or view takes the camera).</summary>
        public void ExitNow()
        {
            if (!active) return;
            RestoreLens(); Suspended = false;
            active = false; leaving = false; walk = false; tr = -1f; cutNow = -1f;
            LandmarkSystem.CutId = null; LandmarkSystem.CutAt = -1f;
            if (floorGo != null) floorGo.SetActive(false); if (ceilGo != null) ceilGo.SetActive(false);
            ShowPanel(false);
            TwinUI.Instance?.RefreshCard();
        }
        public void SetFloor(int i)
        {
            if (!active || leaving || L == null) return;
            float p = P(L); i = Mathf.Clamp(i, 0, IconicShape.Levels - 1);
            if (IconicFloors.Phase(i, p, H(L), out _) == IconicFloors.PNone || i == floor) return;
            floor = i; Rebuild(p, true);
            if (walk)
            {
                // same spot, other floor (moved back to the plate if it is narrower up there)
                if (!IconicFloors.Walkable(floor, eye.x, eye.z)) eye = WalkStart();
                eye.y = IconicShape.FloorY(floor) + 1.62f;
            }
            Pivot();
            Begin(0.7f, cutNow, CutFor());
            Refresh(true);
        }
        /// <summary>For the monitoring window (while Suspended): show floor i as built at the shown date, or hide the floor model.</summary>
        public void Puppet(int i, bool show)
        {
            if (!active || floorGo == null) return;
            i = Mathf.Clamp(i, 0, IconicShape.Levels - 1);
            if (show) { if (i != floor) floor = i; Rebuild(P(L), false); }
            if (floorGo.activeSelf != show) floorGo.SetActive(show);
            if (ceilGo.activeSelf) ceilGo.SetActive(false);
        }
        /// <summary>The panel steps aside while the monitoring window is open.</summary>
        public void HidePanel() { if (panel != null) ShowPanel(false); }
        /// <summary>The monitoring window has closed: the interior takes the camera back on its floor (the date may have moved).</summary>
        public void Resume()
        {
            Suspended = false;
            if (!active || L == null) return;
            float p = P(L);
            if (IconicFloors.Phase(floor, p, H(L), out _) == IconicFloors.PNone) { int t = TopFloor(L, p); if (t < 0) { ExitNow(); return; } floor = t; }
            walk = false; floorGo.SetActive(true); ceilGo.SetActive(false);
            Rebuild(p, true); Pivot(); Begin(0.9f, LandmarkSystem.CutAt >= 0f ? LandmarkSystem.CutAt : H(L) + 30f, CutFor());
            ShowPanel(true); Refresh(true);
        }
        /// <summary>Shows floor i from above (the monitoring window looks at the working floor).</summary>
        public void FocusFloor(int i)
        {
            if (!active || leaving) return;
            if (walk) ToggleWalk();
            if (i != floor) SetFloor(i);
        }
        public void ToggleWalk()
        {
            if (!active || leaving) return;
            walk = !walk;
            if (walk)
            {
                eye = WalkStart();
                var d = model.TransformDirection(Vector3.right); wyaw = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg; wpitch = 6f;
            }
            if (ceilGo != null) ceilGo.SetActive(walk);
            Begin(1.4f, cutNow, CutFor());
            Refresh(true);
        }
        /// <summary>A few steps in from the west windows, on the axis of the core: the whole floor lies ahead.</summary>
        Vector3 WalkStart()
        {
            float yb = IconicShape.FloorY(floor), w = IconicShape.RawWidth(yb + IconicShape.Fh), x0 = IconicShape.Xr - w;
            foreach (float dz in new[] { 2.2f, -2.2f, 5f, -5f, 0f })
                for (float x = x0 + 2.4f; x < IconicShape.Xr - 8f; x += 0.5f)
                    if (IconicFloors.Walkable(floor, x, IconicShape.Cz + dz) && IconicFloors.Walkable(floor, x + 1.5f, IconicShape.Cz + dz)) return new Vector3(x, yb + 1.62f, IconicShape.Cz + dz);
            var c = IconicFloors.Centre(floor, out _); return new Vector3(c.x - 4f, yb + 1.62f, IconicShape.Cz);
        }
        float CutFor() => walk ? IconicShape.FloorY(floor) + IconicShape.Fh + 0.05f : IconicShape.FloorY(floor) + 1.6f;
        void Pivot() { var c = IconicFloors.Centre(floor, out float size); pivot = model.TransformPoint(c + Vector3.up * 1.0f); odist = Mathf.Clamp(odist, 6f, 400f); }
        void Begin(float dur, float from, float to)
        {
            tr = 0f; trDur = dur; trPos = cam.transform.position; trRot = cam.transform.rotation;
            cutFrom = from < 0f ? H(L) + 30f : from; cutTo = to;
        }

        // ------------------------------------------------------------------ geometry of the current floor
        void EnsureObjects()
        {
            if (mat == null) { var sh = Shader.Find("AlatauCity/Landmark"); if (sh != null) mat = new Material(sh) { name = "Iconic interior" }; }
            if (floorGo == null)
            {
                floorGo = new GameObject("Iconic interior · floor"); floorMf = floorGo.AddComponent<MeshFilter>();
                var r = floorGo.AddComponent<MeshRenderer>(); r.sharedMaterial = mat; r.receiveShadows = false; r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                ceilGo = new GameObject("Iconic interior · ceiling"); ceilMf = ceilGo.AddComponent<MeshFilter>();
                var cr = ceilGo.AddComponent<MeshRenderer>(); cr.sharedMaterial = mat; cr.receiveShadows = false; cr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                foreach (var r2 in new[] { r, cr })
                {
                    r2.GetPropertyBlock(mpb);
                    mpb.SetFloat("_Reveal", 100000f); mpb.SetFloat("_Build", 0f); mpb.SetFloat("_Ghost", 0f); mpb.SetFloat("_Hi", 0f); mpb.SetFloat("_Facade", 100000f);
                    mpb.SetFloat("_Land", 1f); mpb.SetFloat("_Glow", -1f); mpb.SetFloat("_H", H(L)); mpb.SetFloat("_Park", 0f);
                    r2.SetPropertyBlock(mpb);
                }
            }
            foreach (var g in new[] { floorGo, ceilGo }) { g.transform.SetParent(model, false); g.transform.localPosition = Vector3.zero; g.transform.localRotation = Quaternion.identity; }
            floorGo.SetActive(true); ceilGo.SetActive(walk);
        }
        void Rebuild(float p, bool force)
        {
            int ph = IconicFloors.Phase(floor, p, H(L), out float f);
            int above = floor + 1 < IconicShape.Levels ? IconicFloors.Phase(floor + 1, p, H(L), out _) : IconicFloors.PReady;
            int step = ph == IconicFloors.PReady ? 8 : Mathf.Clamp(Mathf.FloorToInt(f * 8f), 0, 7);
            if (!force && floor == bFloor && ph == bPhase && step == bStep && above == bAbove) return;
            bFloor = floor; bPhase = ph; bStep = step; bAbove = above;
            Mesh fm, cm;
            try { fm = IconicFloors.Build(floor, ph, ph == IconicFloors.PReady ? 1f : step / 8f, above, out cm, out info); }
            catch (System.Exception e) { Debug.LogWarning("[Alatau] Iconic floor " + (floor + 1) + ": " + e.Message); return; }
            if (floorMf.sharedMesh != null) Destroy(floorMf.sharedMesh); if (ceilMf.sharedMesh != null) Destroy(ceilMf.sharedMesh);
            floorMf.sharedMesh = fm; ceilMf.sharedMesh = cm;
        }

        // ------------------------------------------------------------------ per frame
        void Update()
        {
            if (active || MapCamera.Typing) return;
            var ls = LandmarkSystem.Instance; if (ls == null || !ls.Ready) return;
            var l = ls.Selected; if (l == null || TowerProfile.For(l.Id) == null) { pressed = false; return; }
            // I or a double click on the selected tower: dive in
            if (Input.GetKeyDown(KeyCode.I)) { Enter(l.Id); return; }
            var m = ls.ModelOf(l.Id); var c = Camera.main; if (m == null || c == null) return;
            if (Input.GetMouseButtonDown(0)) { pressed = !MapCamera.BlockInput; clickPos = Input.mousePosition; }
            if (Input.GetMouseButtonUp(0) && pressed)
            {
                pressed = false;
                if ((Input.mousePosition - clickPos).magnitude > 6f) return;
                var col = m.GetComponent<MeshCollider>();
                if (col == null || !col.Raycast(c.ScreenPointToRay(Input.mousePosition), out _, 200000f)) { lastClick = -10f; return; }
                if (Time.unscaledTime - lastClick < 0.4f) { lastClick = -10f; Enter(l.Id); } else lastClick = Time.unscaledTime;
            }
        }

        void LateUpdate()
        {
            if (!active || Suspended) return;
            var ls = LandmarkSystem.Instance;
            if (L == null || model == null || cam == null || mc == null || ls == null) { ExitNow(); return; }
            float p = P(L);
            if (!leaving)
            {
                // the year moved back below this floor: go to the highest floor that exists; nothing left = out
                if (IconicFloors.Phase(floor, p, H(L), out _) == IconicFloors.PNone)
                {
                    int t = TopFloor(L, p); if (t < 0) { ExitNow(); return; }
                    floor = t; if (walk) eye.y = IconicShape.FloorY(floor) + 1.62f; Pivot(); Begin(0.6f, cutNow, CutFor()); Refresh(true);
                }
                Rebuild(p, false);
                HandleInput();
                if (!active) return;
            }
            // pose of the mode, blended from the pose the transition started at
            Vector3 pos; Quaternion rot;
            if (leaving)
            {
                var r = Quaternion.Euler(mc.pitch, mc.yaw, 0f); rot = r; pos = mc.target - r * Vector3.forward * mc.distance;
            }
            else if (walk) { pos = model.TransformPoint(eye); rot = Quaternion.Euler(wpitch, wyaw, 0f); }
            else { rot = Quaternion.Euler(opitch, oyaw, 0f); pos = pivot - rot * Vector3.forward * odist; }
            float cut = cutTo;
            if (tr >= 0f)
            {
                tr += Time.unscaledDeltaTime / Mathf.Max(trDur, 0.01f); float t = Mathf.Clamp01(tr), e = t * t * (3f - 2f * t);
                // the camera falls in along an arc (no straight line through the facade), the cut follows
                var mid = Vector3.Lerp(trPos, pos, e) + Vector3.up * Mathf.Sin(t * Mathf.PI) * Mathf.Min(Vector3.Distance(trPos, pos) * 0.12f, 60f);
                pos = mid; rot = Quaternion.Slerp(trRot, rot, e);
                cut = Mathf.Lerp(cutFrom, cutTo, leaving ? e * e : 1f - (1f - e) * (1f - e));
                if (t >= 1f) { tr = -1f; if (leaving) { FinishLeave(); return; } }
            }
            cutNow = cut; LandmarkSystem.CutId = Id; LandmarkSystem.CutAt = cut;
            cam.transform.SetPositionAndRotation(pos, rot);
            cam.nearClipPlane = walk ? 0.12f : 0.6f; cam.farClipPlane = 60000f;
            // a wider lens at eye level (a room, not a map), back to the map's lens outside
            if (fov0 < 0f) fov0 = cam.fieldOfView;
            cam.fieldOfView = Mathf.MoveTowards(cam.fieldOfView, walk && !leaving ? 64f : fov0, Time.unscaledDeltaTime * 30f);
            if (!leaving) Refresh(false);
        }
        float fov0 = -1f;
        void RestoreLens() { if (cam != null && fov0 > 0f) cam.fieldOfView = fov0; fov0 = -1f; }
        void FinishLeave()
        {
            RestoreLens();
            active = false; leaving = false; cutNow = -1f; LandmarkSystem.CutId = null; LandmarkSystem.CutAt = -1f;
            if (floorGo != null) floorGo.SetActive(false); if (ceilGo != null) ceilGo.SetActive(false);
            TwinUI.Instance?.RefreshCard();
        }

        void HandleInput()
        {
            if (IconicMonitor.Open || IconicMonitor.ClosedFrame >= Time.frameCount - 1) { dragging = false; return; }   // the monitoring window has the input
            bool keys = !MapCamera.Typing; float dt = Time.unscaledDeltaTime;
            if (keys && Input.GetKeyDown(KeyCode.Escape)) { escFrame = Time.frameCount; if (walk) ToggleWalk(); else Exit(); return; }
            if (keys && (Input.GetKeyDown(KeyCode.PageUp) || Input.GetKeyDown(KeyCode.RightBracket))) { SetFloor(NextFloor(+1)); }
            if (keys && (Input.GetKeyDown(KeyCode.PageDown) || Input.GetKeyDown(KeyCode.LeftBracket))) { SetFloor(NextFloor(-1)); }
            if (keys && Input.GetKeyDown(KeyCode.V)) ToggleWalk();
            if (keys && Input.GetKeyDown(KeyCode.M)) { IconicMonitor.Instance?.Show(Id); return; }
            // mouse: drag turns (orbit around the floor / look around), the wheel brings the camera nearer
            bool over = MapCamera.BlockInput;
            if ((Input.GetMouseButtonDown(0) || Input.GetMouseButtonDown(1)) && !over) { dragging = true; lastMouse = Input.mousePosition; clickPos = Input.mousePosition; }
            if (!Input.GetMouseButton(0) && !Input.GetMouseButton(1)) dragging = false;
            Vector3 d = Vector3.zero; if (dragging) { d = Input.mousePosition - lastMouse; lastMouse = Input.mousePosition; }
            bool fast = keys && (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift));
            if (walk)
            {
                wyaw += d.x * 0.16f; wpitch = Mathf.Clamp(wpitch - d.y * 0.12f, -70f, 70f);
                if (keys && Input.GetKey(KeyCode.Q)) wyaw -= 70f * dt; if (keys && Input.GetKey(KeyCode.E)) wyaw += 70f * dt;
                Vector3 mv = Vector3.zero; var fw = Quaternion.Euler(0f, wyaw, 0f) * Vector3.forward; var rt = Quaternion.Euler(0f, wyaw, 0f) * Vector3.right;
                if (keys && (Input.GetKey(KeyCode.W) || (!TwinTour.Running && Input.GetKey(KeyCode.UpArrow)))) mv += fw;
                if (keys && (Input.GetKey(KeyCode.S) || (!TwinTour.Running && Input.GetKey(KeyCode.DownArrow)))) mv -= fw;
                if (keys && (Input.GetKey(KeyCode.D) || (!TwinTour.Running && Input.GetKey(KeyCode.RightArrow)))) mv += rt;
                if (keys && (Input.GetKey(KeyCode.A) || (!TwinTour.Running && Input.GetKey(KeyCode.LeftArrow)))) mv -= rt;
                if (mv.sqrMagnitude > 1e-4f) Walk(model.InverseTransformDirection(mv.normalized) * (fast ? 7f : 2.6f) * dt);
                // the wheel: a step forward or back
                float wheel = over ? 0f : Mathf.Clamp(Input.mouseScrollDelta.y, -3f, 3f);
                if (Mathf.Abs(wheel) > 0.01f) Walk(model.InverseTransformDirection(fw) * wheel * 0.7f);
            }
            else
            {
                oyaw += d.x * 0.25f; opitch = Mathf.Clamp(opitch - d.y * 0.2f, 12f, 88f);
                if (keys && Input.GetKey(KeyCode.Q)) oyaw -= 60f * dt; if (keys && Input.GetKey(KeyCode.E)) oyaw += 60f * dt;
                if (keys && Input.GetKey(KeyCode.R)) opitch = Mathf.Clamp(opitch + 40f * dt, 12f, 88f); if (keys && Input.GetKey(KeyCode.F)) opitch = Mathf.Clamp(opitch - 40f * dt, 12f, 88f);
                float zoom = over ? 0f : Mathf.Clamp(Input.mouseScrollDelta.y, -3f, 3f) * 0.12f;
                if (keys && (Input.GetKey(KeyCode.Z) || Input.GetKey(KeyCode.Equals) || Input.GetKey(KeyCode.KeypadPlus))) zoom += 1.2f * dt;
                if (keys && (Input.GetKey(KeyCode.X) || Input.GetKey(KeyCode.Minus) || Input.GetKey(KeyCode.KeypadMinus))) zoom -= 1.2f * dt;
                odist = Mathf.Clamp(odist * (1f - zoom), 6f, 400f);
                // double click on the floor: stand there
                if (Input.GetMouseButtonUp(0) && !over && (Input.mousePosition - clickPos).magnitude < 6f)
                {
                    if (Time.unscaledTime - lastClick < 0.4f)
                    {
                        lastClick = -10f; var ray = cam.ScreenPointToRay(Input.mousePosition);
                        var pl = new Plane(Vector3.up, model.TransformPoint(new Vector3(0f, IconicShape.FloorY(floor), 0f)));
                        if (pl.Raycast(ray, out float t))
                        {
                            var lp = model.InverseTransformPoint(ray.GetPoint(t));
                            if (IconicFloors.Walkable(floor, lp.x, lp.z))
                            {
                                walk = true; eye = new Vector3(lp.x, IconicShape.FloorY(floor) + 1.62f, lp.z); wyaw = oyaw; wpitch = 4f;
                                if (ceilGo != null) ceilGo.SetActive(true); Begin(1.3f, cutNow, CutFor()); Refresh(true);
                            }
                        }
                    }
                    else lastClick = Time.unscaledTime;
                }
            }
        }
        void Walk(Vector3 dl)
        {
            dl.y = 0f; var n = eye + dl;
            if (IconicFloors.Walkable(floor, n.x, n.z)) { eye = n; return; }
            var nx = eye + new Vector3(dl.x, 0f, 0f); if (IconicFloors.Walkable(floor, nx.x, nx.z)) { eye = nx; return; }
            var nz = eye + new Vector3(0f, 0f, dl.z); if (IconicFloors.Walkable(floor, nz.x, nz.z)) eye = nz;
        }
        int NextFloor(int dir)
        {
            float p = P(L);
            for (int i = floor + dir; i >= 0 && i < IconicShape.Levels; i += dir) if (IconicFloors.Phase(i, p, H(L), out _) > IconicFloors.PNone) return i;
            return floor;
        }

        // ------------------------------------------------------------------ panel (top right, in place of the passport)
        VisualElement panel;
        void ShowPanel(bool on)
        {
            var ui = TwinUI.Instance; var mid = ui != null ? ui.Middle : null;
            if (mid == null) return;
            if (panel == null)
            {
                panel = new VisualElement(); panel.AddToClassList("ii-card"); ui.BlockWhileHovered(panel);
            }
            if (panel.parent != mid) mid.Add(panel);
            panel.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
            mid.EnableInClassList("ii-on", on);
            if (!on) { MapCamera.BlockInput = ui.PointerOverChrome; uiKey = ""; }
        }
        void Refresh(bool force)
        {
            if (panel == null || L == null) return;
            uiT -= Time.unscaledDeltaTime; if (!force && uiT > 0f) return; uiT = 0.25f;
            float p = P(L); int ph = IconicFloors.Phase(floor, p, H(L), out float f);
            string key = floor + "|" + ph + "|" + Mathf.RoundToInt(f * 100f) + "|" + walk + "|" + TwinState.Year + "|" + TopFloor(L, p) + "|" + Loc.Language;
            if (!force && key == uiKey) return; uiKey = key;
            Fill(p, ph, f);
        }
        void Fill(float p, int ph, float f)
        {
            panel.Clear();
            var head = new VisualElement(); head.AddToClassList("head");
            var t = new Label(L.Short + " · внутри"); t.AddToClassList("t"); head.Add(t);
            head.Add(Widgets.Btn("×", Exit, "small", "ghost")); panel.Add(head);
            float yb = IconicShape.FloorY(floor);
            var sub = new Label(IconicFloors.Name(floor) + (floor < IconicShape.Floors ? " из " + IconicShape.Floors : "") + " · отметка +" + Loc.N1(yb) + " м"); sub.AddToClassList("id"); panel.Add(sub);

            var chips = new VisualElement(); chips.AddToClassList("lm-chips");
            var uc = new VisualElement(); uc.AddToClassList("lm-chip"); uc.Add(new Label(info != null ? info.Use : IconicFloors.FloorUse(floor))); chips.Add(uc);
            string cls = ph >= IconicFloors.PReady ? "ok" : ph >= IconicFloors.PPartitions ? "info" : "warn";
            chips.Add(Widgets.Status(IconicFloors.PhaseNow[ph] + (ph > IconicFloors.PNone && ph < IconicFloors.PReady ? " · " + Mathf.RoundToInt(f * 100f) + " %" : ""), cls));
            panel.Add(chips);

            var body = new VisualElement(); body.AddToClassList("ii-body"); panel.Add(body);
            // the tower as a stack of floors coloured by phase (the vertical east face on the right, as on the building)
            var stack = new VisualElement(); stack.AddToClassList("ii-stack"); body.Add(stack);
            for (int i = IconicShape.Levels - 1; i >= 0; i--)
            {
                int ii = i; int pi = IconicFloors.Phase(i, p, H(L), out _);
                var row = new VisualElement(); row.AddToClassList("ii-row"); if (i == floor) row.AddToClassList("cur");
                if (i == floor) { var lb = new Label(IconicFloors.Short(i)) { pickingMode = PickingMode.Ignore }; lb.AddToClassList("ii-cur"); row.Add(lb); }
                var bar = new VisualElement(); bar.AddToClassList("ii-bar");
                bar.style.width = 22f + 64f * Mathf.Clamp01(IconicShape.RawWidth(IconicShape.FloorY(i) + IconicShape.Fh) / IconicShape.W0);
                bar.style.backgroundColor = IconicFloors.PhaseColor[pi];
                row.Add(bar);
                if (pi > IconicFloors.PNone) row.AddManipulator(new Clickable(() => SetFloor(ii)));
                stack.Add(row);
            }
            var right = new VisualElement(); right.AddToClassList("ii-right"); body.Add(right);
            var cap = new Label("ЭТАПЫ ЭТАЖА") { pickingMode = PickingMode.Ignore }; cap.AddToClassList("lm-cap-h"); right.Add(cap);
            var T = new float[7]; IconicFloors.Times(floor, H(L), T);
            for (int s = 1; s <= 6; s++)
            {
                var r = new VisualElement(); r.AddToClassList("ii-step"); right.Add(r);
                bool done = ph > s || p >= 0.999f, now = ph == s;
                var dot = new VisualElement { pickingMode = PickingMode.Ignore }; dot.AddToClassList("ii-dot"); dot.AddToClassList(done ? "done" : now ? "now" : "todo");
                if (done || now) dot.style.backgroundColor = IconicFloors.PhaseColor[s];
                r.Add(dot);
                var n = new Label(Cap(IconicFloors.PhaseName[s])) { pickingMode = PickingMode.Ignore }; n.AddToClassList("ii-sn"); if (!done && !now) n.AddToClassList("muted"); r.Add(n);
                string when = done ? IconicFloors.MonthYear(IconicFloors.YearAt(L, Mathf.Min(T[s], 1f))) : now ? Mathf.RoundToInt(f * 100f) + " %" : "план " + IconicFloors.MonthYear(IconicFloors.YearAt(L, Mathf.Min(T[s], 1f)));
                var w = new Label(when) { pickingMode = PickingMode.Ignore }; w.AddToClassList("ii-sw"); if (now) w.AddToClassList("warn"); r.Add(w);
            }
            if (info != null)
            {
                right.Add(Widgets.Fact("Площадь этажа", "≈ " + Loc.N0(Mathf.Round(info.Area / 10f) * 10f) + " м²"));
                var dl = new Label(info.Detail) { pickingMode = PickingMode.Ignore }; dl.AddToClassList("note"); dl.style.marginTop = 6; dl.style.whiteSpace = WhiteSpace.Normal; right.Add(dl);
            }
            var leg = new VisualElement(); leg.AddToClassList("ii-legend"); panel.Add(leg);
            foreach (int s in new[] { 1, 2, 3, 5, 7 }) leg.Add(Widgets.LegendItem(IconicFloors.PhaseColor[s], IconicFloors.PhaseName[s]));

            var btns = new VisualElement(); btns.AddToClassList("lm-btns"); panel.Add(btns);
            var mon = Widgets.Btn("Мониторинг строительства", () => IconicMonitor.Instance?.Show(Id), "small", "primary"); mon.style.width = Length.Percent(100); btns.Add(mon);
            // only where there is a floor to go to: none above the top of the tower (or of the frame so far), none below the lobby
            if (NextFloor(+1) != floor) btns.Add(Widgets.Btn("Этаж выше", () => SetFloor(NextFloor(+1)), "small"));
            if (NextFloor(-1) != floor) btns.Add(Widgets.Btn("Этаж ниже", () => SetFloor(NextFloor(-1)), "small"));
            var wb = Widgets.Btn(walk ? "Вид сверху" : "Пройтись по этажу", ToggleWalk, "small"); if (walk) wb.AddToClassList("active"); btns.Add(wb);
            btns.Add(Widgets.Btn("Наружу", Exit, "small", "ghost"));
            var hint = new Label(walk ? "W A S D — идти · перетаскивание — оглядеться · PgUp / PgDn — этажи · Esc — вид сверху"
                                      : "перетаскивание — повернуть · колесо — ближе · двойной клик по полу — встать там · PgUp / PgDn — этажи · M — мониторинг · Esc — наружу");
            hint.AddToClassList("note"); hint.style.marginTop = 6; hint.style.whiteSpace = WhiteSpace.Normal; panel.Add(hint);
        }
        static string Cap(string s) => string.IsNullOrEmpty(s) ? s : char.ToUpper(s[0]) + s.Substring(1);
    }
}
