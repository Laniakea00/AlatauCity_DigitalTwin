using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Map-style camera for laptop/trackpad use. Orbits around a ground target.
    /// Pan: drag (left button / one-finger trackpad drag) or WASD/arrows. Rotate: Alt+drag, right-drag or Q/E. Tilt: R/F.
    /// Zoom: scroll / pinch or Z/X. Shift = fast. Home/0 = overview. T = top view. 1-6 = saved views (from the Blender model).
    /// BlockInput is set by the UI (pointer over a panel); a press that starts over the UI never becomes a map drag.</summary>
    public class MapCamera : MonoBehaviour
    {
        [System.Serializable] public class View { public string name; public Vector3 target; public float distance, yaw, pitch; }
        public Vector3 target = Vector3.zero;
        public float distance = 9000f, yaw = 0f, pitch = 50f;
        public float minDistance = 120f, maxDistance = 120000f;
        public float keyPanSpeed = 0.9f, zoomSpeed = 0.12f, rotateSpeed = 60f;
        public View[] views = new View[0];
        public View overview;
        public static bool BlockInput;
        /// <summary>Height of the orbit point above the ground (a landmark is framed around its middle, not its foot). Decays to 0 unless held.</summary>
        public float lift; public bool holdLift;
        /// <summary>True in a frame where the user moved the camera (keys, drag, wheel): lets scripted moves (fly-to, orbit) give way.</summary>
        public static bool UserMoved { get; private set; }
        /// <summary>True while a text field of the UI has focus: the keyboard belongs to the field, not to the camera.</summary>
        public static bool Typing;
        static bool Key(KeyCode k) => !Typing && !TwinTour.Running && Input.GetKey(k);
        static bool KeyDown(KeyCode k) => !Typing && !TwinTour.Running && Input.GetKeyDown(k);
        Vector3 dragStart; bool dragging, pressedOnMap; Camera cam;
        // smooth fly-to
        Vector3 goT; float goD, goY, goP; bool flying;
        Vector3 vT; float vD, vY, vP; int flyFrame;      // fly-to speeds of the recorded video (eased moves), the last frame it moved
        public bool IsDragging => dragging;
        public bool IsFlying => flying;
        /// <summary>Drops a fly-to in progress (a landmark fly-in takes over the camera).</summary>
        public void StopFly() { flying = false; }
        public bool PressedOnMap => pressedOnMap;
        void Start() { cam = GetComponent<Camera>(); Apply(); }
        public void FlyTo(View v)
        {
            if (v == null) return; Yield();
            if (!flying && Time.frameCount - flyFrame > 1) { vT = Vector3.zero; vD = vY = vP = 0f; }   // from rest; a move that goes on keeps its speed
            goT = v.target; goD = v.distance; goY = v.yaw; goP = v.pitch; flying = true;
        }
        /// <summary>Someone moves the map camera while the camera is inside Iconic Complex: leave the tower first.</summary>
        static void Yield() { if (Landmarks.IconicInterior.Active && !Landmarks.IconicInterior.Driving) Landmarks.IconicInterior.Instance.ExitNow(); }
        /// <summary>Nearest zoom: a selected landmark can be looked at from close by (facade, cranes, the working level).</summary>
        float MinD => Landmarks.LandmarkSystem.Instance != null && Landmarks.LandmarkSystem.Instance.Selected != null ? 40f : minDistance;
        void Update()
        {
            UserMoved = false;
            if (Landmarks.IconicInterior.Active) return;          // inside the tower the interior drives the camera
            float dt = Time.deltaTime, fast = Key(KeyCode.LeftShift) || Key(KeyCode.RightShift) ? 3f : 1f;
            Vector3 fwd = Quaternion.Euler(0, yaw, 0) * Vector3.forward, right = Quaternion.Euler(0, yaw, 0) * Vector3.right;
            Vector3 pan = Vector3.zero;
            if (Key(KeyCode.W) || Key(KeyCode.UpArrow)) pan += fwd;
            if (Key(KeyCode.S) || Key(KeyCode.DownArrow)) pan -= fwd;
            if (Key(KeyCode.D) || Key(KeyCode.RightArrow)) pan += right;
            if (Key(KeyCode.A) || Key(KeyCode.LeftArrow)) pan -= right;
            if (pan != Vector3.zero) { UserMoved = true; flying = false; target += pan * keyPanSpeed * distance * dt * fast; }
            if (Key(KeyCode.Q)) { UserMoved = true; flying = false; yaw -= rotateSpeed * dt * fast; }
            if (Key(KeyCode.E)) { UserMoved = true; flying = false; yaw += rotateSpeed * dt * fast; }
            if (Key(KeyCode.R) || Key(KeyCode.F)) UserMoved = true;
            if (Key(KeyCode.R)) pitch = Mathf.Clamp(pitch + 40f * dt, 8f, 89f);
            if (Key(KeyCode.F)) pitch = Mathf.Clamp(pitch - 40f * dt, 8f, 89f);
            if (Key(KeyCode.Z) || Key(KeyCode.Equals) || Key(KeyCode.KeypadPlus)) { UserMoved = true; flying = false; distance *= 1f - 1.2f * dt * fast; }
            if (Key(KeyCode.X) || Key(KeyCode.Minus) || Key(KeyCode.KeypadMinus)) { UserMoved = true; flying = false; distance *= 1f + 1.2f * dt * fast; }
            if (!BlockInput) { float scroll = Input.mouseScrollDelta.y; if (Mathf.Abs(scroll) > 0.01f) { UserMoved = true; flying = false; distance *= 1f - Mathf.Clamp(scroll, -3f, 3f) * zoomSpeed; } }
            if (KeyDown(KeyCode.Home) || KeyDown(KeyCode.Alpha0)) { UserMoved = true; FlyTo(overview); }
            if (KeyDown(KeyCode.T)) { flying = false; pitch = pitch > 85f ? 50f : 89f; }
            for (int i = 0; i < views.Length && i < 9; i++) if (KeyDown(KeyCode.Alpha1 + i) || KeyDown(KeyCode.Keypad1 + i)) FlyTo(views[i]);
            if (Input.GetMouseButtonDown(0) || Input.GetMouseButtonDown(1)) { pressedOnMap = !BlockInput; dragStart = Input.mousePosition; dragging = false; }
            if (pressedOnMap)
            {
                if (Input.GetMouseButton(0) || Input.GetMouseButton(1))
                {
                    Vector3 d = Input.mousePosition - dragStart;
                    if (d.magnitude > 4f) { dragging = true; flying = false; }
                    if (dragging) UserMoved = true;
                    if (dragging)
                    {
                        bool rotate = Input.GetMouseButton(1) || Key(KeyCode.LeftAlt) || Key(KeyCode.RightAlt);
                        if (rotate) { yaw += d.x * 0.25f; pitch = Mathf.Clamp(pitch - d.y * 0.2f, 8f, 89f); }
                        else { float k = distance / Screen.height * 1.6f; target -= right * d.x * k + fwd * d.y * k; }
                        dragStart = Input.mousePosition;
                    }
                }
                if (Input.GetMouseButtonUp(0) || Input.GetMouseButtonUp(1)) { /* keep 'dragging' true this frame so the click is not a selection */ }
            }
            else dragging = false;
            if (!Input.GetMouseButton(0) && !Input.GetMouseButton(1) && !Input.GetMouseButtonUp(0) && !Input.GetMouseButtonUp(1)) pressedOnMap = false;
            if (flying && (TwinTour.VideoMode || TwinTour.Running))
            {
                // the recorded video and the presentation: the move starts and ends softly and takes the same time whatever the speed-up of
                // the scene. A long way rises over the city and the ground never runs past faster than 0.8 view distances a second: no low
                // rush across the map; the zoom keeps to about a factor of 3 a second (no snap back from a close-up). The presentation
                // moves a little slower still, so the audience can follow where the camera goes
                float st = TwinTour.VideoMode ? 0.4f : 0.8f; float udt = TwinState.RealDelta; flyFrame = Time.frameCount;
                float way = new Vector2(goT.x - target.x, goT.z - target.z).magnitude;
                target = Vector3.SmoothDamp(target, goT, ref vT, st, 0.8f * distance, udt); distance = Mathf.SmoothDamp(distance, Mathf.Max(goD, way * 0.7f), ref vD, st, 1.2f * distance, udt);
                yaw = Mathf.SmoothDampAngle(yaw, goY, ref vY, st, Mathf.Infinity, udt); pitch = Mathf.SmoothDamp(pitch, goP, ref vP, st, Mathf.Infinity, udt);
                if ((target - goT).magnitude < 1f && Mathf.Abs(distance - goD) < 1f) flying = false;
            }
            else if (flying)
            {
                float k = 1f - Mathf.Exp(-4f * dt);
                target = Vector3.Lerp(target, goT, k); distance = Mathf.Lerp(distance, goD, k); yaw = Mathf.LerpAngle(yaw, goY, k); pitch = Mathf.Lerp(pitch, goP, k);
                if ((target - goT).magnitude < 1f && Mathf.Abs(distance - goD) < 1f) flying = false;
            }
            distance = Mathf.Clamp(distance, MinD, maxDistance);
            if (!holdLift) lift = Mathf.Lerp(lift, 0f, 1f - Mathf.Exp(-1.6f * dt));
            target.y = CityGround.HeightAt(target.x, target.z) + lift;
            Apply();
        }
        /// <summary>Scripted pose (fly-to, orbit): sets and applies immediately; 'lift' raises the orbit point above the ground.</summary>
        public void SetPose(Vector3 t, float d, float y, float p, float liftM)
        {
            Yield();
            flying = false; target = t; distance = Mathf.Clamp(d, MinD, maxDistance); yaw = y; pitch = Mathf.Clamp(p, 8f, 89f); lift = liftM;
            target.y = CityGround.HeightAt(target.x, target.z) + lift; Apply();
        }
        void LateUpdate() { if (!Input.GetMouseButton(0) && !Input.GetMouseButton(1) && !Input.GetMouseButtonUp(0) && !Input.GetMouseButtonUp(1)) dragging = false; }
        void Apply()
        {
            var rot = Quaternion.Euler(pitch, yaw, 0);
            transform.position = target - rot * Vector3.forward * distance; transform.rotation = rot;
            // keep the ground above the camera's near plane: depth precision scales with distance
            float above = transform.position.y - CityGround.HeightAt(transform.position.x, transform.position.z);
            if (above < 30f) { transform.position += Vector3.up * (30f - above); transform.LookAt(target); }
            if (cam != null) { cam.nearClipPlane = Mathf.Clamp(distance * 0.01f, 2f, 300f); cam.farClipPlane = Mathf.Max(60000f, distance * 12f); }
        }
        public static View MakeView(string name, Vector3 pos, Vector3 fwd)
        {
            fwd.Normalize(); float gy = CityGround.HeightAt(pos.x, pos.z);
            float t = fwd.y < -0.05f ? (pos.y - gy) / -fwd.y : 3000f; var tgt = pos + fwd * t; tgt.y = CityGround.HeightAt(tgt.x, tgt.z);
            return new View { name = name, target = tgt, distance = (pos - tgt).magnitude, yaw = Mathf.Atan2(fwd.x, fwd.z) * Mathf.Rad2Deg, pitch = Mathf.Clamp(Mathf.Asin(-fwd.y) * Mathf.Rad2Deg, 8f, 89f) };
        }

    }
}
