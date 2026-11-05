using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The districts of the whole city seen from afar (owner 05.11.2026: «разделение на районы, когда отдаляешь и видишь всю
    /// карту, по их цветам»): the ground shader tints every district in its colour and outlines it (_AlatauDistOv, AlatauGround.shader),
    /// and a large name with the district's role stands over each part of it (Growing has two: west and east). Both fade in between
    /// 12 and 19 km of camera distance, only for the whole city (no district picked in the header), not in the analysis colouring,
    /// the monitoring map or a building interior. A click on a name picks that district, as the header picker does.</summary>
    public class DistrictMap : MonoBehaviour
    {
        public static DistrictMap Instance;
        static readonly int OvId = Shader.PropertyToID("_AlatauDistOv");
        const float Near = 12000f, Far = 19000f, MinRingHa = 1500f;
        static readonly string[] RoleKey = { "role_gate", "role_golden", "role_growing", "role_green" };

        class Tag { public int D; public Vector3 W; public VisualElement El; public Label Name, Role; }
        readonly List<Tag> tags = new List<Tag>();
        VisualElement host; string lang; float ov;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("District map (far view)").AddComponent<DistrictMap>(); }
        void Awake() { Instance = this; Shader.SetGlobalFloat(OvId, 0f); }
        void OnDestroy() { Shader.SetGlobalFloat(OvId, 0f); }

        void Ensure()
        {
            var h = TwinUI.Instance != null ? TwinUI.Instance.Pins : null;
            if (h == null) return;
            if (host == h && tags.Count > 0 && tags[0].El.parent == host && lang == TwinState.Language) return;
            foreach (var t in tags) t.El?.RemoveFromHierarchy(); tags.Clear();
            host = h; lang = TwinState.Language;
            if (!CityStats.HasOutlines) return;
            var sys = Landmarks.LandmarkSystem.Instance;
            if (sys == null || !sys.Ready) { host = null; return; }                // wait for the landmarks: the names keep clear of their labels
            var marks = new List<Vector2>();
            foreach (var l in sys.Items) if (!l.IsLrt) marks.Add(new Vector2(l.World.x, l.World.z));
            for (int d = 0; d < CityStats.Districts; d++)
            {
                var ps = CityStats.DistrictPolys(d); if (ps == null) continue;
                foreach (var r in ps)
                {
                    if (Mathf.Abs(MapPolys.SignedArea(r)) / 10000f < MinRingHa) continue;
                    var c = PlaceIn(r, marks);
                    tags.Add(Make(d, new Vector3(c.x, CityGround.HeightAt(c.x, c.y) + 30f, c.y)));
                }
            }
        }

        /// <summary>Where the district's name stands: a point of the ring on a 400 m grid, at least 1.2 km inside its edge where it can,
        /// as far as possible from the landmark labels (they stand over their objects) and not far from the ring's middle.</summary>
        static Vector2 PlaceIn(Vector2[] r, List<Vector2> marks)
        {
            var mid = MapPolys.Centre(r); var b = MapPolys.Bounds(r);
            Vector2 best = mid; float bestS = float.MinValue;
            for (float x = b.xMin; x <= b.xMax; x += 400f)
                for (float z = b.yMin; z <= b.yMax; z += 400f)
                {
                    if (!MapPolys.Inside(r, x, z)) continue;
                    float edge = float.MaxValue;
                    for (int i = 0, j = r.Length - 1; i < r.Length; j = i++) edge = Mathf.Min(edge, SegDist(new Vector2(x, z), r[j], r[i]));
                    float clear = 6000f; foreach (var m in marks) clear = Mathf.Min(clear, Vector2.Distance(m, new Vector2(x, z)));
                    float s = Mathf.Min(clear, 5000f) * 1.5f + Mathf.Min(edge, 900f) - Vector2.Distance(mid, new Vector2(x, z)) * 0.1f;
                    if (s > bestS) { bestS = s; best = new Vector2(x, z); }
                }
            return best;
        }
        static float SegDist(Vector2 p, Vector2 a, Vector2 b)
        {
            var ab = b - a; float t = ab.sqrMagnitude > 1e-6f ? Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude) : 0f;
            return Vector2.Distance(p, a + ab * t);
        }

        Tag Make(int d, Vector3 w)
        {
            var col = CityStats.DistrictColors[d];
            var el = new VisualElement(); el.style.position = Position.Absolute; el.style.alignItems = Align.Center; el.style.translate = new Translate(Length.Percent(-50), Length.Percent(-50));
            el.style.paddingLeft = el.style.paddingRight = 14; el.style.paddingTop = 6; el.style.paddingBottom = 7;
            el.style.borderTopLeftRadius = el.style.borderTopRightRadius = el.style.borderBottomLeftRadius = el.style.borderBottomRightRadius = 8;
            el.style.backgroundColor = new Color(0.055f, 0.055f, 0.055f, 0.80f);
            el.style.borderLeftWidth = el.style.borderRightWidth = el.style.borderTopWidth = el.style.borderBottomWidth = 1;
            el.style.borderLeftColor = el.style.borderRightColor = el.style.borderTopColor = el.style.borderBottomColor = new Color(col.r, col.g, col.b, 0.9f);
            var row = new VisualElement { pickingMode = PickingMode.Ignore }; row.style.flexDirection = FlexDirection.Row; row.style.alignItems = Align.Center;
            var dot = new VisualElement { pickingMode = PickingMode.Ignore }; dot.style.width = dot.style.height = 12; dot.style.marginRight = 8; dot.style.backgroundColor = col;
            dot.style.borderTopLeftRadius = dot.style.borderTopRightRadius = dot.style.borderBottomLeftRadius = dot.style.borderBottomRightRadius = 6;
            row.Add(dot);
            var n = new Label(CityStats.DistrictIds[d]) { pickingMode = PickingMode.Ignore }; n.style.fontSize = 22; n.style.color = new Color(0.99f, 0.99f, 0.98f);
            n.style.unityFontStyleAndWeight = FontStyle.Bold; n.style.marginLeft = n.style.marginRight = 0; n.style.paddingLeft = n.style.paddingRight = 0;
            row.Add(n); el.Add(row);
            var role = new Label(Loc.T(RoleKey[d])) { pickingMode = PickingMode.Ignore }; role.style.fontSize = 12; role.style.color = new Color(col.r * 0.5f + 0.5f, col.g * 0.5f + 0.5f, col.b * 0.5f + 0.5f);
            role.style.marginTop = 1; role.style.whiteSpace = WhiteSpace.NoWrap; el.Add(role);
            int dd = d;
            el.RegisterCallback<ClickEvent>(_ => TwinState.SetDistrict(dd));
            el.style.display = DisplayStyle.None;
            host.Add(el);
            return new Tag { D = d, W = w, El = el, Name = n, Role = role };
        }

        void LateUpdate()
        {
            var cam = Camera.main; var mc = cam != null ? cam.GetComponent<MapCamera>() : null;
            float camD = mc != null ? mc.distance : 0f;
            bool allowed = TwinState.District < 0 && TwinState.Module != "monitoring" && TwinState.Module != "prediction"
                           && !Landmarks.IconicInterior.Active && Shader.GetGlobalFloat("_AlatauMode") < 1.5f;
            float want = allowed ? Mathf.Clamp01((camD - Near) / (Far - Near)) : 0f;
            ov = Mathf.MoveTowards(ov, want, TwinState.RealDelta * 2.5f);
            Shader.SetGlobalFloat(OvId, ov);

            Ensure();
            if (host == null || host.panel == null || cam == null) return;
            foreach (var t in tags)
            {
                if (ov < 0.02f) { t.El.style.display = DisplayStyle.None; continue; }
                var sp = cam.WorldToScreenPoint(t.W);
                if (sp.z < 0) { t.El.style.display = DisplayStyle.None; continue; }
                var local = host.WorldToLocal(RuntimePanelUtils.ScreenToPanel(host.panel, new Vector2(sp.x, Screen.height - sp.y)));
                if (local.x < -100 || local.y < -40 || local.x > host.layout.width + 100 || local.y > host.layout.height + 40) { t.El.style.display = DisplayStyle.None; continue; }
                t.El.style.display = DisplayStyle.Flex; t.El.style.left = local.x; t.El.style.top = local.y; t.El.style.opacity = ov;
                t.El.BringToFront();                                           // from afar the district names read first, over the landmark labels
            }
        }
    }
}
