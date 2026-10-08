using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.UI;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Screen-space pins over the 3D map (UI Toolkit elements placed every frame from world positions).
    /// A module fills the pin set; pins are clickable, have a status ring and an optional always-on label.</summary>
    public class MapPins : MonoBehaviour
    {
        public static MapPins Instance;
        public class Pin
        {
            public string Id, Label; public Vector3 World; public Color Fill; public string Status = "";   // "", ok, warn, bad, planned
            public bool ShowLabel; public float Size = 12f; public Action OnClick; public object Tag;
            internal VisualElement El; internal Label Lbl;
        }
        readonly List<Pin> pins = new List<Pin>();
        VisualElement host; string selected;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Twin map pins").AddComponent<MapPins>(); }
        void Awake() { Instance = this; }

        public void Clear() { foreach (var p in pins) p.El?.RemoveFromHierarchy(); pins.Clear(); }
        public void Set(IEnumerable<Pin> items) { Clear(); pins.AddRange(items); host = null; }
        public void Select(string id) { selected = id; foreach (var p in pins) if (p.El != null) p.El.EnableInClassList("selected", p.Id == id); }
        public IReadOnlyList<Pin> All => pins;

        void Attach()
        {
            host = TwinUI.Instance != null ? TwinUI.Instance.Pins : null; if (host == null) return;
            foreach (var p in pins)
            {
                p.El?.RemoveFromHierarchy();
                var e = new VisualElement(); e.AddToClassList("pin-wrap");
                var dot = new VisualElement(); dot.AddToClassList("map-pin"); dot.style.backgroundColor = p.Fill;
                dot.style.width = dot.style.height = p.Size; dot.style.borderTopLeftRadius = dot.style.borderTopRightRadius = dot.style.borderBottomLeftRadius = dot.style.borderBottomRightRadius = p.Size / 2f;
                if (!string.IsNullOrEmpty(p.Status)) dot.AddToClassList(p.Status);
                e.Add(dot);
                var l = new Label(p.Label) { pickingMode = PickingMode.Ignore }; l.AddToClassList("pin-label"); e.Add(l); p.Lbl = l;
                l.style.display = p.ShowLabel ? DisplayStyle.Flex : DisplayStyle.None;
                var pin = p;
                e.RegisterCallback<PointerEnterEvent>(_ => { if (!pin.ShowLabel) pin.Lbl.style.display = DisplayStyle.Flex; e.BringToFront(); });
                e.RegisterCallback<PointerLeaveEvent>(_ => { if (!pin.ShowLabel && pin.Id != selected) pin.Lbl.style.display = DisplayStyle.None; });
                e.AddManipulator(new Clickable(() => pin.OnClick?.Invoke()));
                TwinUI.Instance.BlockWhileHovered(e);
                if (p.Id == selected) e.AddToClassList("selected");
                host.Add(e); p.El = e;
            }
        }

        void LateUpdate()
        {
            if (pins.Count == 0) return;
            if (host == null || TwinUI.Instance == null || host != TwinUI.Instance.Pins || (pins.Count > 0 && pins[0].El != null && pins[0].El.parent != host)) Attach();
            var cam = Camera.main; if (cam == null || host == null) return;
            var panel = host.panel; if (panel == null) return;
            foreach (var p in pins)
            {
                if (p.El == null) continue;
                var sp = cam.WorldToScreenPoint(p.World);
                if (sp.z < 0) { p.El.style.display = DisplayStyle.None; continue; }
                var pp = RuntimePanelUtils.ScreenToPanel(panel, new Vector2(sp.x, Screen.height - sp.y));
                var local = host.WorldToLocal(pp);
                if (local.x < -40 || local.y < -40 || local.x > host.layout.width + 40 || local.y > host.layout.height + 40) { p.El.style.display = DisplayStyle.None; continue; }
                p.El.style.display = DisplayStyle.Flex;
                p.El.style.left = local.x - p.Size / 2f; p.El.style.top = local.y - p.Size / 2f;
                if (p.Id == selected) p.Lbl.style.display = DisplayStyle.Flex;
            }
        }
    }
}
