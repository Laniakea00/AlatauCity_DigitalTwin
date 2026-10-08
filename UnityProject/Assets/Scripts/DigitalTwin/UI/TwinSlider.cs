using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Year slider 2025–2050 with milestone ticks. Own element: styled by Twin.uss, no theme dependency.</summary>
    public class TwinSlider : VisualElement
    {
        public int Min = TwinState.MinYear, Max = TwinState.MaxYear;
        public Action<int> OnChange;
        readonly VisualElement track, fill, handle; int value = 2050; bool drag;
        const float Half = 8f;
        public TwinSlider(int[] ticks, Func<int, string> format = null, int min = TwinState.MinYear, int max = TwinState.MaxYear)
        {
            Min = min; Max = max; value = max;
            AddToClassList("slider");
            track = new VisualElement { pickingMode = PickingMode.Ignore }; track.AddToClassList("track"); Add(track);
            fill = new VisualElement { pickingMode = PickingMode.Ignore }; fill.AddToClassList("fill"); Add(fill);
            foreach (var t in ticks)
            {
                var tk = new VisualElement { pickingMode = PickingMode.Ignore, userData = t }; tk.AddToClassList("tick"); Add(tk);
                var tl = new Label(format != null ? format(t) : t.ToString()) { pickingMode = PickingMode.Ignore, userData = t }; tl.AddToClassList("tick-label"); Add(tl);
            }
            handle = new VisualElement { pickingMode = PickingMode.Ignore }; handle.AddToClassList("handle"); Add(handle);
            RegisterCallback<PointerDownEvent>(e => { drag = true; this.CapturePointer(e.pointerId); Set(e.localPosition.x); e.StopPropagation(); });
            RegisterCallback<PointerMoveEvent>(e => { if (drag) Set(e.localPosition.x); });
            RegisterCallback<PointerUpEvent>(e => { drag = false; this.ReleasePointer(e.pointerId); });
            RegisterCallback<PointerCaptureOutEvent>(_ => drag = false);
            RegisterCallback<GeometryChangedEvent>(_ => Place());
        }
        public int Value { get => this.value; set { this.value = Mathf.Clamp(value, Min, Max); Place(); } }
        void Set(float x)
        {
            float w = resolvedStyle.width - 2 * Half; if (w <= 0) return;
            int v = Mathf.RoundToInt(Mathf.Lerp(Min, Max, Mathf.Clamp01((x - Half) / w)));
            if (v != value) { value = v; Place(); OnChange?.Invoke(v); }
        }
        void Place()
        {
            float w = resolvedStyle.width - 2 * Half; if (w <= 0) return;
            float X(int y) => Half + w * (y - Min) / (float)(Max - Min);
            handle.style.left = X(value) - Half; fill.style.left = Half; fill.style.width = X(value) - Half;
            foreach (var c in Children())
            {
                if (c.userData is int y) { if (c is Label) c.style.left = X(y) - 20; else c.style.left = X(y); }
            }
        }
    }
}
