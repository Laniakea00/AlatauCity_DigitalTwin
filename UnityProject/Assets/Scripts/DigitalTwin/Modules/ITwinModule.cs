using UnityEngine;
using UnityEngine.UIElements;

namespace AlatauCity.DigitalTwin.Modules
{
    /// <summary>A module = one tab of the platform. It switches its 3D layers on/off and fills the right panel.
    /// All modules share the same scene, year, scenario and selection (TwinState).</summary>
    public interface ITwinModule
    {
        string Id { get; }            // "overview", "construction", ...
        string TabKey { get; }        // Loc key of the tab title
        void OnEnter();               // enable 3D layers of the module
        void OnExit();
        void BuildPanel(VisualElement left, VisualElement right);   // (re)build the two floating columns
        void Refresh();               // update values after a year / scenario / district change
        (Color, string)[] Legend { get; }   // legend of the 3D view while the module is active (null = buildings legend)
    }

    public abstract class TwinModuleBase : ITwinModule
    {
        public abstract string Id { get; }
        public abstract string TabKey { get; }
        /// <summary>Where the next blocks go. Build() starts in the left column; call Right() to continue in the right one.</summary>
        protected VisualElement panel;
        protected VisualElement leftCol, rightCol;
        public virtual void OnEnter() { }
        public virtual void OnExit() { }
        public void BuildPanel(VisualElement left, VisualElement right) { leftCol = left; rightCol = right; Rebuild(); Refresh(); }
        protected void Rebuild() { leftCol.Clear(); rightCol.Clear(); panel = leftCol; Build(); panel = leftCol; }
        protected void Right() { panel = rightCol; }
        protected void Left() { panel = leftCol; }
        protected abstract void Build();
        public virtual void Refresh() { }
        public virtual (Color, string)[] Legend => null;
    }

    /// <summary>Placeholder for a module that is still on the work plan — says so explicitly, never pretends to be ready.</summary>
    public class StubModule : TwinModuleBase
    {
        readonly string id, tabKey, wipKey; readonly int stage;
        public StubModule(string id, string tabKey, string wipKey, int stage) { this.id = id; this.tabKey = tabKey; this.wipKey = wipKey; this.stage = stage; }
        public override string Id => id;
        public override string TabKey => tabKey;
        protected override void Build()
        {
            var box = UI.Widgets.Block(panel); box.AddToClassList("wip");
            UI.Widgets.Eyebrow(box, Loc.T("eyebrow_wip"));
            var t = new Label(Loc.T(tabKey)); t.AddToClassList("t"); box.Add(t);
            var s = new Label(string.Format(Loc.T("module_wip"), stage)); s.AddToClassList("muted"); box.Add(s);
            var d = new Label(Loc.T(wipKey)); d.style.marginTop = 8; box.Add(d);
        }
    }
}
