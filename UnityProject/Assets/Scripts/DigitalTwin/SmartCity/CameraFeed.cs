using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>The "video" of a city camera — a stub: a second Unity camera stands where the CCTV camera is, slowly pans like a PTZ
    /// camera and renders the twin into a small texture (10 frames a second, only while a feed is on screen). On top: REC, camera id,
    /// clock, video-analytics boxes and the «ЗАГЛУШКА» mark — the real RTSP / Smart City stream replaces the texture later.</summary>
    public class FeedRig : MonoBehaviour
    {
        public static FeedRig Instance;
        public static RenderTexture Texture => Instance != null ? Instance.rt : null;
        Camera cam; RenderTexture rt; float next; int users;
        Vector3 pos; float heading, pitch = 14f, span = 28f; float ptz;

        public static FeedRig Ensure()
        {
            if (Instance == null) new GameObject("Twin camera feed").AddComponent<FeedRig>();
            return Instance;
        }
        void Awake()
        {
            Instance = this;
            rt = new RenderTexture(512, 288, 24) { name = "cctv_feed", antiAliasing = 2 }; rt.Create();
            cam = gameObject.AddComponent<Camera>(); cam.enabled = false;
        }
        void OnDestroy() { if (rt != null) rt.Release(); }

        /// <summary>Points the rig at a CCTV camera (position on a pole / roof, heading of its view).</summary>
        public void Look(SmartCity.Cctv c)
        {
            if (c == null) return;
            pos = c.World; heading = c.Heading; ptz = 0f;
            // the view looks down at the street in front of the camera, not into the sky
            float g = CityGround.HeightAt(pos.x, pos.z); float h = Mathf.Max(18f, pos.y - g);
            pitch = Mathf.Clamp(Mathf.Atan2(h, 340f) * Mathf.Rad2Deg, 5f, 20f);
            next = 0f;
        }
        public void Use(bool on) { users = Mathf.Max(0, users + (on ? 1 : -1)); }

        void LateUpdate()
        {
            if (users <= 0) return;
            float rd = TwinState.RealDelta; ptz += rd; next -= rd; if (next > 0f) return; next = 0.1f;
            var main = Camera.main; if (main == null) return;
            cam.CopyFrom(main); cam.enabled = false; cam.targetTexture = rt; cam.fieldOfView = 52f;
            cam.nearClipPlane = 1f; cam.farClipPlane = 20000f;
            float yaw = heading + Mathf.Sin(ptz * 0.18f) * span;   // PTZ: slow pan left — right
            cam.transform.SetPositionAndRotation(pos, Quaternion.Euler(pitch, yaw, 0f));
            try { cam.Render(); } catch (Exception e) { Debug.LogWarning("[Alatau] feed: " + e.Message); users = 0; }
        }
    }

    /// <summary>A camera window: the rendered view + the overlay of a CCTV stream.</summary>
    public class CameraFeed : VisualElement
    {
        readonly Image img; readonly Label lId, lClock, lPlace, lStub; readonly VisualElement overlay;
        SmartCity.Cctv cam; bool attached; float phase;
        static readonly Color Rec = new Color(1f, 0.23f, 0.18f);

        public CameraFeed(bool big = false)
        {
            AddToClassList("feed"); if (big) AddToClassList("feed-big");
            img = new Image { scaleMode = ScaleMode.ScaleAndCrop, pickingMode = PickingMode.Ignore }; img.AddToClassList("feed-img"); Add(img);
            overlay = new VisualElement { pickingMode = PickingMode.Ignore }; overlay.AddToClassList("feed-over"); overlay.generateVisualContent += Draw; Add(overlay);
            var top = new VisualElement { pickingMode = PickingMode.Ignore }; top.AddToClassList("feed-top"); overlay.Add(top);
            var rec = new VisualElement { pickingMode = PickingMode.Ignore }; rec.AddToClassList("feed-rec"); top.Add(rec);
            lId = new Label { pickingMode = PickingMode.Ignore }; lId.AddToClassList("feed-id"); top.Add(lId);
            var sp = new VisualElement { pickingMode = PickingMode.Ignore }; sp.style.flexGrow = 1; top.Add(sp);
            lClock = new Label { pickingMode = PickingMode.Ignore }; lClock.AddToClassList("feed-clock"); top.Add(lClock);
            lPlace = new Label { pickingMode = PickingMode.Ignore }; lPlace.AddToClassList("feed-place"); overlay.Add(lPlace);
            lStub = new Label("ЗАГЛУШКА · ДЕМО-ПОТОК") { pickingMode = PickingMode.Ignore }; lStub.AddToClassList("feed-stub"); overlay.Add(lStub);
            RegisterCallback<AttachToPanelEvent>(_ => { if (!attached) { attached = true; FeedRig.Ensure().Use(true); if (cam != null) FeedRig.Instance.Look(cam); } });
            RegisterCallback<DetachFromPanelEvent>(_ => { if (attached) { attached = false; FeedRig.Instance?.Use(false); } });
            schedule.Execute(Tick).Every(100);
        }

        public SmartCity.Cctv Cam => cam;
        public void Show(SmartCity.Cctv c)
        {
            cam = c; if (c == null) return;
            lId.text = c.Id + " · " + SmartCity.CamTypeShort[(int)c.Type].ToUpperInvariant();
            lPlace.text = c.Place + (c.Online ? "" : " · нет сигнала");
            EnableInClassList("offline", !c.Online);
            FeedRig.Ensure().Look(c);
        }

        void Tick()
        {
            if (panel == null) return;
            var tex = FeedRig.Texture; if (tex != null && img.image != tex) img.image = tex;
            img.style.opacity = cam != null && cam.Online ? 1f : 0.12f;
            lClock.text = new DateTime(TwinState.Year, 11, 18).ToString("dd.MM.yyyy", Loc.Ru) + "  " + DateTime.Now.ToString("HH:mm:ss");
            phase += 0.1f; overlay.MarkDirtyRepaint();
        }

        /// <summary>Scan lines, the blinking REC dot, a few video-analytics boxes drifting over the frame.</summary>
        void Draw(MeshGenerationContext ctx)
        {
            var r = contentRect; if (r.width < 20f) return;
            var p = ctx.painter2D;
            // scan lines
            p.lineWidth = 1f; p.strokeColor = new Color(1f, 1f, 1f, 0.035f);
            for (float y = 0; y < r.height; y += 3f) { p.BeginPath(); p.MoveTo(new Vector2(0, y)); p.LineTo(new Vector2(r.width, y)); p.Stroke(); }
            if (cam == null || !cam.Online) return;
            // REC dot
            if (Mathf.Repeat(phase, 1.2f) < 0.7f) { p.fillColor = Rec; p.BeginPath(); p.Arc(new Vector2(14f, 15f), 4.5f, 0f, 360f); p.Fill(); }
            // analytics boxes (people / cars) — the stub draws them where the real analytics would
            int seed = cam.Id.GetHashCode(); var rnd = new System.Random(seed);
            int n = 2 + rnd.Next(3);
            for (int i = 0; i < n; i++)
            {
                float bx = (float)rnd.NextDouble() * 0.7f + 0.1f, by = (float)rnd.NextDouble() * 0.35f + 0.45f, bw = 0.06f + (float)rnd.NextDouble() * 0.08f;
                float dx = Mathf.Sin(phase * 0.35f + i * 1.7f) * 0.05f;
                var rect = new Rect((bx + dx) * r.width, by * r.height, bw * r.width, bw * r.width * 0.7f);
                var col = i == 0 && cam.Type == SmartCity.CamType.Traffic ? new Color(1f, 0.75f, 0.2f, 0.9f) : new Color(0.35f, 0.95f, 0.55f, 0.9f);
                p.strokeColor = col; p.lineWidth = 1.5f;
                p.BeginPath(); p.MoveTo(rect.min); p.LineTo(new Vector2(rect.xMax, rect.yMin)); p.LineTo(rect.max); p.LineTo(new Vector2(rect.xMin, rect.yMax)); p.ClosePath(); p.Stroke();
            }
        }
    }
}
