using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The 60-second cinematic film of Alatau City: a director that flies the main camera along seven shots (morning push-in,
    /// Gate glide, avenue tracking, Iconic reveal, construction, golden hour, dusk into night), sets the year and the hour of each shot,
    /// hides the interface and renders the camera into a 1920×1080 texture that the editor recorder (Editor/AlatauFilmRecorder) writes
    /// to an MP4. Every shot is recorded with a lead-in (the city settles: traffic, trees, shadows) and a short tail; the titles and the
    /// cross-dissolves are put on afterwards (Tools: compose in post). Nothing changes for normal users unless Play() is called.</summary>
    [DefaultExecutionOrder(5000)]
    public class FilmReel : MonoBehaviour
    {
        public static FilmReel Instance;
        /// <summary>True while the reel runs (from Play() to the end of the last tail).</summary>
        public static bool Playing => Instance != null && Instance.running;
        /// <summary>True once the reel has played through to its end.</summary>
        public static bool Done { get; private set; }
        /// <summary>The picture of the film (1920×1080): the camera renders into it while the reel runs.</summary>
        public static RenderTexture Target { get; private set; }
        /// <summary>Seconds since the reel started (game time: constant steps under the recorder).</summary>
        public static float Clock => Instance != null ? Instance.clock : 0f;
        public const int Width = 1920, Height = 1080;
        public const float Tail = 0.5f;

        // ---- a camera pose: eye and the point looked at (world), plus the map-camera pose the city systems read
        struct Pose { public Vector3 Eye, Look; }
        delegate Pose PathFn(float s);
        class Shot
        {
            public string Name; public float Pre, Dur; public int Year; public float H0, H1, Fov = 45f;
            public bool EaseIn, EaseOut; public float HourRamp = 1f;   // the hour reaches H1 at this fraction of the shot
            public PathFn Path; public System.Func<PathFn> Build;      // Build: resolved when the shot starts (roads, models exist then)
        }

        readonly List<Shot> shots = new List<Shot>();
        bool running; float clock; int cur = -1, only = -1; float shotStart;
        Camera cam; MapCamera mc;
        // what the scene looked like before
        float hour0, fov0, near0, far0; bool cycling0, viewer0, holdLift0; int year0; Vector3 tgt0; float dist0, yaw0, pitch0;
        readonly List<(VisualElement el, StyleEnum<DisplayStyle> d)> hidden = new List<(VisualElement, StyleEnum<DisplayStyle>)>();
        // the editor may not draw a camera whose picture goes to a texture while its window is not shown: then the reel renders by hand
        int autoRenders, lastFrameAuto = -1; bool manual;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) { var go = new GameObject("Film reel"); DontDestroyOnLoad(go); Instance = go.AddComponent<FilmReel>(); } }

        /// <summary>Starts the film. only ≥ 0 plays that one shot (tests). Returns false when the camera is not there yet.</summary>
        public static bool Play(int onlyShot = -1)
        {
            if (Instance == null) Boot();
            return Instance.Begin(onlyShot);
        }
        /// <summary>Stops the film and gives the camera, the interface, the year and the hour back.</summary>
        public static void Stop() { if (Instance != null && Instance.running) Instance.End(); }

        /// <summary>The shot list (name, lead-in, length) for the composer: lengths include the 0.5 s cross-dissolve overlaps.</summary>
        public static string Timeline()
        {
            if (Instance == null) return "";
            Instance.Define(); var sb = new System.Text.StringBuilder(); float t = 0f;
            foreach (var s in Instance.shots) { sb.AppendFormat(System.Globalization.CultureInfo.InvariantCulture, "{0} start={1:0.00} pre={2:0.00} dur={3:0.00} tail={4:0.00}\n", s.Name, t, s.Pre, s.Dur, Tail); t += s.Pre + s.Dur + Tail; }
            return sb.ToString();
        }

        bool Begin(int onlyShot)
        {
            if (running) return true;
            cam = Camera.main; mc = cam != null ? cam.GetComponent<MapCamera>() : null;
            if (cam == null || mc == null) { Debug.LogWarning("[Alatau] film reel: no main camera yet"); return false; }
            if (TwinTour.Running) TwinTour.Toggle();
            Define(); only = onlyShot; Done = false;
            var look = FilmLook.Instance;
            hour0 = FilmLook.Hour; cycling0 = FilmLook.Cycling; viewer0 = FilmLook.ViewerTime; year0 = TwinState.Year;
            fov0 = cam.fieldOfView; near0 = cam.nearClipPlane; far0 = cam.farClipPlane; holdLift0 = mc.holdLift;
            tgt0 = mc.target; dist0 = mc.distance; yaw0 = mc.yaw; pitch0 = mc.pitch;
            if (look != null) look.on = true;
            if (TwinState.Module != "overview") TwinState.SetModule("overview");
            if (TwinState.Selected != null) TwinState.SetSelected(null);
            // the interface: every document of the UI Toolkit is hidden (the film texture never shows it anyway; this keeps the GPU for the city)
            hidden.Clear();
            foreach (var d in FindObjectsByType<UIDocument>(FindObjectsSortMode.None))
                if (d != null && d.rootVisualElement != null) { hidden.Add((d.rootVisualElement, d.rootVisualElement.style.display)); d.rootVisualElement.style.display = DisplayStyle.None; }
            if (Target == null) { Target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32) { name = "Alatau film", antiAliasing = 1 }; Target.Create(); }
            cam.targetTexture = Target;
            Camera.onPostRender -= Counted; Camera.onPostRender += Counted; autoRenders = 0; lastFrameAuto = -1; manual = false;
            mc.holdLift = true; clock = 0f; cur = -1; shotStart = 0f; running = true;
            Debug.Log("[Alatau] film reel: start" + (only >= 0 ? " (shot " + only + ")" : "") + "\n" + Timeline());
            return true;
        }

        void End()
        {
            running = false; cur = -1;
            Camera.onPostRender -= Counted;
            if (cam != null) { cam.targetTexture = null; cam.fieldOfView = fov0; cam.nearClipPlane = near0; cam.farClipPlane = far0; }
            foreach (var (el, d) in hidden) if (el != null) el.style.display = d;
            hidden.Clear();
            TwinState.Year = year0;
            if (FilmLook.Instance != null) { FilmLook.Instance.hour = hour0; FilmLook.Cycling = cycling0; FilmLook.ViewerTime = viewer0; }
            if (mc != null) { mc.holdLift = holdLift0; mc.SetPose(tgt0, dist0, yaw0, pitch0, 0f); }
            Debug.Log("[Alatau] film reel: end at " + clock.ToString("0.00") + " s");
        }

        void Counted(Camera c) { if (c == cam && running) { autoRenders++; lastFrameAuto = Time.frameCount; } }

        void LateUpdate()
        {
            if (!running) return;
            if (cam == null || mc == null) { End(); return; }
            clock += Time.deltaTime;
            // which shot: shots are laid end to end, each with its lead-in and tail
            float t0 = 0f; int idx = -1;
            for (int i = 0; i < shots.Count; i++)
            {
                if (only >= 0 && i != only) continue;
                var s = shots[i]; float len = s.Pre + s.Dur + Tail;
                if (clock < t0 + len) { idx = i; break; }
                t0 += len;
            }
            if (idx < 0) { Done = true; End(); return; }
            var sh = shots[idx];
            if (idx != cur)
            {
                cur = idx; shotStart = t0;
                if (TwinState.Year != sh.Year) TwinState.Year = sh.Year;
                if (sh.Build != null) sh.Path = sh.Build();
                cam.fieldOfView = sh.Fov;
                Debug.Log($"[Alatau] film reel: shot {idx} {sh.Name} at {clock:0.00} s");
            }
            float u = (clock - shotStart - sh.Pre) / sh.Dur;           // 0..1 over the shot proper; < 0 in the lead-in, > 1 in the tail
            float s01 = Ease(u, sh.EaseIn, sh.EaseOut);
            // the hour of the shot (the dusk shot runs from sunset into the night)
            float hk = Mathf.Clamp01(u / Mathf.Max(0.05f, sh.HourRamp)); if (sh.HourRamp < 0.99f) hk = Mathf.SmoothStep(0f, 1f, hk);
            FilmLook.SetHour(Mathf.Lerp(sh.H0, sh.H1, hk));
            var p = sh.Path != null ? sh.Path(s01) : new Pose { Eye = cam.transform.position, Look = cam.transform.position + cam.transform.forward };
            Place(p);
            // the editor did not draw the camera last frame: draw it by hand from now on
            if (!manual && Time.frameCount > 3 && autoRenders == 0 && clock > 0.2f) { manual = true; Debug.Log("[Alatau] film reel: rendering by hand"); }
            if (manual && lastFrameAuto != Time.frameCount) { FilmLook.Instance?.Redraw(); cam.Render(); }
        }

        /// <summary>Linear motion in the middle of the film (no stop at a cut); a soft start for the first shot and a soft landing for the last.
        /// Outside 0..1 (lead-in, tail) the motion carries on at the speed of the end it continues.</summary>
        static float Ease(float u, bool easeIn, bool easeOut)
        {
            if (easeIn && easeOut) { if (u <= 0f) return 0f; if (u >= 1f) return 1f; return u * u * (3f - 2f * u); }
            if (easeIn) { if (u <= 0f) return 0f; return u < 1f ? 2f * u * u - u * u * u : u; }          // slope 0 at the start, 1 at the end
            if (easeOut) { if (u >= 1f) return 1f; if (u <= 0f) return u; float v = 1f - u; return 1f - (2f * v * v - v * v * v); }
            return u;
        }

        /// <summary>Puts the camera at the pose: the map camera gets the same view (the trees, traffic, people and haze follow its target
        /// and distance), then the exact eye and line of sight are set (lower and flatter than the map camera allows).</summary>
        void Place(Pose p)
        {
            float gEye = CityGround.HeightAt(p.Eye.x, p.Eye.z);
            if (p.Eye.y < gEye + 6f) p.Eye.y = gEye + 6f;
            Vector3 dir = p.Look - p.Eye; float d = dir.magnitude; if (d < 1f) { dir = Vector3.forward; d = 1f; }
            dir /= d;
            float gLook = CityGround.HeightAt(p.Look.x, p.Look.z);
            float yaw = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg, pitch = Mathf.Asin(Mathf.Clamp(-dir.y, -1f, 1f)) * Mathf.Rad2Deg;
            mc.SetPose(new Vector3(p.Look.x, 0f, p.Look.z), d, yaw, pitch, Mathf.Max(0f, p.Look.y - gLook));
            cam.transform.SetPositionAndRotation(p.Eye, Quaternion.LookRotation(dir, Vector3.up));
            cam.nearClipPlane = Mathf.Clamp(d * 0.008f, 0.6f, 120f); cam.farClipPlane = Mathf.Max(60000f, d * 12f);
        }

        // ---------------------------------------------------------------- the shots
        static Vector3 G(float x, float z, float up) => new Vector3(x, CityGround.HeightAt(x, z) + up, z);

        /// <summary>A map-camera move: target, distance, yaw and pitch from a to b (yaw/pitch in degrees, as the map camera).</summary>
        static PathFn MapMove(Vector2 t0, Vector2 t1, float lift0, float lift1, float d0, float d1, float y0, float y1, float p0, float p1)
        {
            return s =>
            {
                var t = Vector2.LerpUnclamped(t0, t1, s); float lift = Mathf.LerpUnclamped(lift0, lift1, s);
                // distance in log space: a push-in looks even
                float d = Mathf.Exp(Mathf.LerpUnclamped(Mathf.Log(d0), Mathf.Log(d1), s)), yw = Mathf.LerpUnclamped(y0, y1, s), pt = Mathf.LerpUnclamped(p0, p1, s);
                var look = G(t.x, t.y, lift); var rot = Quaternion.Euler(pt, yw, 0f);
                return new Pose { Eye = look - rot * Vector3.forward * d, Look = look };
            };
        }

        /// <summary>An orbit in the frame of a landmark model (local metres, heights above its base): the eye on a circle round 'c' at
        /// angle a (degrees, local x = sin, z = cos), radius r and height h, looking at c raised by lookH.</summary>
        static PathFn LocalOrbit(string model, Vector3 c, float a0, float a1, float r0, float r1, float h0, float h1, float l0, float l1, Vector3 lookOff)
        {
            Transform m = Landmarks.LandmarkSystem.Instance != null ? Landmarks.LandmarkSystem.Instance.ModelOf(model) : null;
            return s =>
            {
                float a = Mathf.LerpUnclamped(a0, a1, s) * Mathf.Deg2Rad, r = Mathf.LerpUnclamped(r0, r1, s), h = Mathf.LerpUnclamped(h0, h1, s), lh = Mathf.LerpUnclamped(l0, l1, s);
                Vector3 eye = c + new Vector3(Mathf.Sin(a) * r, h, Mathf.Cos(a) * r), look = c + lookOff + new Vector3(0f, lh, 0f);
                if (m != null) { eye = m.TransformPoint(eye); look = m.TransformPoint(look); }
                else { var o = new Vector3(-3170f, CityGround.HeightAt(-3170f, -19080f), -19080f); eye += o; look += o; }
                return new Pose { Eye = eye, Look = look };
            };
        }

        /// <summary>A low tracking shot along the avenue nearest to p: the eye rides above the carriageway (in its direction of traffic
        /// when it is one carriageway of a dual road), looking ahead along the road. Falls back to a slow map move.</summary>
        static PathFn Avenue(Vector2 p, float travel, float height, float ahead, float side)
        {
            if (!FilmRoads.DrawnWay(p, 2050, (int)TwinState.Scenario, 250f, travel + ahead + 400f, out var line, out var cls, out var oneWay) || line == null || line.Count < 2)
            {
                Debug.LogWarning("[Alatau] film reel: no avenue near " + p + ", map move instead");
                return MapMove(p, p + new Vector2(120f, -60f), 6f, 6f, 160f, 150f, 120f, 124f, 14f, 13f);
            }
            // arc length along the line
            var acc = new float[line.Count]; for (int i = 1; i < line.Count; i++) acc[i] = acc[i - 1] + Vector2.Distance(line[i - 1], line[i]);
            float total = acc[line.Count - 1];
            Vector2 At(float sArc)
            {
                sArc = Mathf.Clamp(sArc, 0f, total);
                int i = 1; while (i < line.Count - 1 && acc[i] < sArc) i++;
                float seg = Mathf.Max(1e-3f, acc[i] - acc[i - 1]); return Vector2.Lerp(line[i - 1], line[i], (sArc - acc[i - 1]) / seg);
            }
            // a smooth curve: the mean of the line over ±45 m (no kinks at the vertices of the centre line)
            Vector2 Smooth(float sArc) { Vector2 m = Vector2.zero; for (int k = -4; k <= 4; k++) m += At(sArc + k * 11.25f); return m / 9f; }
            // where p lies along the line
            float s0 = 0f, best = float.MaxValue; for (float q = 0f; q <= total; q += 5f) { float dd = (At(q) - p).sqrMagnitude; if (dd < best) { best = dd; s0 = q; } }
            // start so that the whole move fits on the line
            float start = Mathf.Clamp(s0 - travel * 0.5f, 60f, Mathf.Max(60f, total - travel - ahead - 60f));
            Debug.Log($"[Alatau] film reel: avenue {cls}{(oneWay ? " (one carriageway)" : "")} {total:0} m, ride {start:0}..{start + travel:0}");
            return s =>
            {
                float a = start + travel * s;
                Vector2 e = Smooth(a), l = Smooth(a + ahead), fwd = (l - e).normalized, right = new Vector2(fwd.y, -fwd.x);
                e += right * side;
                return new Pose { Eye = G(e.x, e.y, height), Look = G(l.x + right.x * side * 0.4f, l.y + right.y * side * 0.4f, 3f) };
            };
        }

        void Define()
        {
            if (shots.Count > 0) return;
            var iconic = new Vector2(-3170f, -19080f);
            // 1. 0–6.5 s: morning, a high slow push-in over the city toward Gate and Iconic (title)
            shots.Add(new Shot { Name = "morning", Pre = 4f, Dur = 6.5f, Year = 2050, H0 = 7.2f, H1 = 7.45f, Fov = 42f, EaseIn = true,
                Path = MapMove(iconic + new Vector2(-250f, -400f), iconic, 120f, 90f, 5600f, 3300f, 18f, 30f, 18f, 20f) });
            // 2. 6–14 s: glide over Gate at 8:30 — traffic, the LRT, roofs
            shots.Add(new Shot { Name = "gate", Pre = 2f, Dur = 7.5f, Year = 2050, H0 = 8.0f, H1 = 8.25f, Fov = 45f,
                Path = MapMove(new Vector2(-2980f, -18760f), new Vector2(-2480f, -18300f), 0f, 0f, 760f, 640f, 28f, 46f, 33f, 30f) });
            // 3. 13.5–21.5 s: low tracking along a main avenue of Gate — cars, people, trees, crossings
            shots.Add(new Shot { Name = "avenue", Pre = 2f, Dur = 7.5f, Year = 2050, H0 = 9.0f, H1 = 9.2f, Fov = 46f,
                Build = () => Avenue(new Vector2(-2110f, -18550f), 190f, 46f, 210f, 0f) });
            // 4. Iconic Complex at midday — rising round the plaza inside the ring of towers (clear of the 32 m pavilions) and looking up the tower
            shots.Add(new Shot { Name = "iconic", Pre = 2f, Dur = 9f, Year = 2050, H0 = 13.6f, H1 = 13.9f, Fov = 50f,
                Build = () => LocalOrbit("iconic", Vector3.zero, 146f, 110f, 205f, 220f, 55f, 105f, 50f, 130f, new Vector3(0f, 0f, -10f)) });
            // 5. 30–37.5 s: the tower under construction (2029): working cranes on the frame (caption «Every site monitored»)
            shots.Add(new Shot { Name = "construction", Pre = 4f, Dur = 7.2f, Year = 2029, H0 = 15.4f, H1 = 15.6f, Fov = 42f,
                Build = () => LocalOrbit("iconic", new Vector3(-84f, 0f, 46f), 198f, 226f, 340f, 320f, 105f, 140f, 135f, 160f, Vector3.zero) });
            // 6. 37–45 s: golden hour over Golden and the KAIST campus
            shots.Add(new Shot { Name = "golden", Pre = 4f, Dur = 8f, Year = 2050, H0 = 17.7f, H1 = 18.0f, Fov = 40f,
                Path = MapMove(new Vector2(-1330f, -12420f), new Vector2(-1430f, -12610f), 20f, 20f, 600f, 470f, 190f, 210f, 21f, 19f) });
            // 7. 44.5–60 s: dusk into the blue hour while the camera rises over Gate — lamps, windows, car lights, Iconic lit; the end card
            shots.Add(new Shot { Name = "night", Pre = 2f, Dur = 15.5f, Year = 2050, H0 = 18.15f, H1 = 19.7f, HourRamp = 0.6f, Fov = 45f, EaseOut = true,
                Path = MapMove(iconic + new Vector2(-60f, -40f), iconic + new Vector2(120f, 160f), 80f, 40f, 950f, 2700f, 12f, 38f, 17f, 33f) });
        }
    }
}
