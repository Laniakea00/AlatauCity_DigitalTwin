using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Modules;

namespace AlatauCity.DigitalTwin.UI
{
    /// <summary>Notifications of the platform: the bell in the header opens the list (Smart City video analytics, iKomek 109, 112,
    /// the twin's forecasts), new events slide in as a toast under the header. The events are the demo day of the year (SmartCity.Day)
    /// played in real time: one event every ~35 s. In the presentation toasts appear only when a step asks for them.</summary>
    public class Notifier : MonoBehaviour
    {
        public static Notifier Instance;
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Twin notifications").AddComponent<Notifier>(); }
        void Awake() { Instance = this; }

        readonly List<SmartCity.Notice> feed = new List<SmartCity.Notice>();   // delivered, newest first
        int year = -1, next; float wait = 8f; public int Unread { get; private set; }
        VisualElement toastHost, toast, popup, list; string filter = "";
        float toastLeft; Label badge;
        /// <summary>The presentation lets toasts through (Smart City step).</summary>
        public static bool TourToasts;
        public static event System.Action OnChanged;

        public IReadOnlyList<SmartCity.Notice> Feed => feed;

        void ResetDay(int y)
        {
            year = y; feed.Clear(); next = 0;
            var day = SmartCity.Day(y); if (day.Count == 0) { year = -1; return; }
            // the morning is already in the list when the platform opens: everything up to ~10:30
            while (next < day.Count && day[next].Minute < 10 * 60 + 30) feed.Insert(0, day[next++]);
            Unread = Mathf.Min(3, feed.Count); Changed();
        }

        /// <summary>Delivers the next event of the day now (the presentation calls it on its own beat).</summary>
        public SmartCity.Notice Push(bool toastIt = true)
        {
            if (year != TwinState.Year) ResetDay(TwinState.Year);
            var day = SmartCity.Day(TwinState.Year); if (day.Count == 0) return null;
            if (next >= day.Count) next = 0;
            var n = day[next++]; feed.Insert(0, n); if (feed.Count > 40) feed.RemoveAt(feed.Count - 1);
            Unread++; Changed();
            if (toastIt) Toast(n);
            return n;
        }
        /// <summary>A scripted event (the presentation): shown as a toast and kept in the list.</summary>
        public void Push(SmartCity.Notice n, bool toastIt = true) { if (n == null) return; feed.Insert(0, n); Unread++; Changed(); if (toastIt) Toast(n); }

        void Changed() { if (badge != null) { badge.text = Unread > 9 ? "9+" : Unread.ToString(); badge.style.display = Unread > 0 ? DisplayStyle.Flex : DisplayStyle.None; } if (popup != null && popup.style.display == DisplayStyle.Flex) Fill(); OnChanged?.Invoke(); }

        /// <summary>TwinUI hands over the badge of the bell each time the header is rebuilt.</summary>
        public void BindBadge(Label b) { badge = b; Changed(); }

        void Update()
        {
            if (!Data.TwinData.Ready || !CityStats.Ready || TwinUI.Instance == null) return;
            if (year != TwinState.Year) ResetDay(TwinState.Year);
            Attach();
            if (toast != null && toastLeft > 0f) { toastLeft -= TwinState.RealDelta; if (toastLeft <= 0f) { toast.RemoveFromClassList("show"); toast.style.opacity = 0f; } }
            if (TwinTour.Running) return;                 // the presentation decides when an event comes
            wait -= TwinState.RealDelta;
            if (wait <= 0f) { wait = 30f + Random.value * 15f; Push(true); }
        }

        void Attach()
        {
            var ui = TwinUI.Instance; var scene = ui.Scene; if (scene == null) return;
            if (toastHost != null && toastHost.parent == scene) return;
            badge = ui.BellBadge; Changed();
            toastHost = new VisualElement { pickingMode = PickingMode.Ignore }; toastHost.AddToClassList("toast-host"); scene.Add(toastHost);
            toast = null;
            popup = new VisualElement(); popup.AddToClassList("notif-pop"); popup.style.display = DisplayStyle.None; (ui.Middle ?? scene).Add(popup); ui.BlockWhileHovered(popup);   // in the middle: above the side columns
        }

        // ------------------------------------------------------------------ toast
        public void Toast(SmartCity.Notice n)
        {
            if (TwinTour.Running && !TourToasts) return;
            Attach(); if (toastHost == null) return;
            toastHost.Clear(); toastHost.BringToFront();
            toast = Card(n, true); toast.AddToClassList("toast"); toastHost.Add(toast); TwinUI.Instance.BlockWhileHovered(toast);
            var tt = toast; tt.schedule.Execute(() => { tt.AddToClassList("show"); tt.style.opacity = 1f; }).StartingIn(30);
            toastLeft = TwinTour.Running ? 6.5f : 7f;
        }

        VisualElement Card(SmartCity.Notice n, bool compact)
        {
            var c = Widgets.JournalCard(n.Icon, n.Source, n.Level, n.Status, n.Title + (compact ? "" : " — " + n.Text), n.Time, n.HasPlace ? "Показать" : null, n.HasPlace ? () => Open(n) : null);
            if (compact) { var t = new Label(n.Text) { pickingMode = PickingMode.Ignore }; t.AddToClassList("note"); t.style.marginTop = 2; c.Insert(2, t); }
            if (n.HasPlace) c.AddManipulator(new Clickable(() => Open(n)));
            return c;
        }

        /// <summary>Flies to the place of the event and opens its camera in the Smart City tab.</summary>
        public static void Open(SmartCity.Notice n)
        {
            if (n == null) return;
            if (Instance != null && Instance.popup != null) Instance.popup.style.display = DisplayStyle.None;
            if (TwinTour.Running) { SmartCityModule.FlyTo(n.World); return; }
            if (TwinState.Module != "smartcity") TwinState.SetModule("smartcity");
            if (n.Cam >= 0) SmartCityModule.Focus(n.Cam); else if (n.HasPlace) SmartCityModule.FlyTo(n.World);
        }

        // ------------------------------------------------------------------ the list under the bell
        public void TogglePanel(VisualElement anchor)
        {
            Attach(); if (popup == null) return;
            bool show = popup.style.display == DisplayStyle.None;
            popup.style.display = show ? DisplayStyle.Flex : DisplayStyle.None; if (show) popup.BringToFront();
            if (!show) return;
            Unread = 0; Changed(); Fill();
            var root = popup.parent; float w = root.layout.width;
            popup.style.left = Mathf.Clamp(anchor.worldBound.center.x - root.worldBound.x - 200f, 8f, Mathf.Max(8f, w - 408f));
        }
        public void HidePanel() { if (popup != null) popup.style.display = DisplayStyle.None; }

        void Fill()
        {
            popup.Clear();
            var h = new VisualElement(); h.AddToClassList("row"); h.style.marginBottom = 8; popup.Add(h);
            var t = new Label("Уведомления"); t.AddToClassList("block-title"); h.Add(t);
            h.Add(Widgets.Btn("×", HidePanel, "small", "ghost"));
            var chips = new VisualElement(); chips.AddToClassList("chips"); popup.Add(chips);
            foreach (var (k, name) in new[] { ("", "Все"), ("Smart City", "Smart City"), ("iKomek", "iKomek 109"), ("Стройка", "Стройка"), ("qTwin", "Прогнозы") })
            {
                var kk = k; var b = new Button(() => { filter = kk; Fill(); }) { text = name }; b.AddToClassList("chip"); b.EnableInClassList("active", filter == k); chips.Add(b);
            }
            var sv = new ScrollView(ScrollViewMode.Vertical); sv.AddToClassList("notif-list"); popup.Add(sv);
            int shown = 0;
            foreach (var n in feed)
            {
                if (filter != "" && !n.Source.StartsWith(filter)) continue;
                sv.Add(Card(n, true)); if (++shown >= 25) break;
            }
            if (shown == 0) { var l = new Label("Событий нет."); l.AddToClassList("note"); sv.Add(l); }
            var go = Widgets.Btn("Открыть Smart City: камеры и обращения", () => { HidePanel(); TwinState.SetModule("smartcity"); }, "primary", "wide"); popup.Add(go);
            var note = new Label("Демо: события смоделированы. Интеграция — API Smart City Alatau, iKomek 109 и 112 (заглушки)."); note.AddToClassList("note"); note.style.marginTop = 6; popup.Add(note);
        }
    }
}
