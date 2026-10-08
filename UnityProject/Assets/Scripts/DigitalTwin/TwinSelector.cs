using UnityEngine;
namespace AlatauCity.DigitalTwin
{
    /// <summary>Click a building (Play mode) -> highlight + TwinState.Selected (the passport card is drawn by TwinUI). Esc = clear.</summary>
    public class TwinSelector : MonoBehaviour
    {
        static readonly int SelId = Shader.PropertyToID("_AlatauSel");
        RaycastHit[] hits = new RaycastHit[64];
        public Color selectionColor = new Color(0.851f, 0.275f, 0.937f);   // --sel #d946ef
        void OnEnable() { Shader.SetGlobalFloat(SelId, 0); Shader.SetGlobalColor("_AlatauSelColor", selectionColor); }
        bool downOnMap;
        void Update()
        {
            if (Input.GetKeyDown(KeyCode.Escape)) { Select(-1); if (BimQuarter.Instance != null) BimQuarter.Instance.Select(-1); }
            if (Input.GetMouseButtonDown(0)) downOnMap = !MapCamera.BlockInput;   // a press that starts over the UI never selects
            if (!Input.GetMouseButtonUp(0) || !downOnMap) return;
            downOnMap = false;
            var mc = GetComponent<MapCamera>(); if (mc != null && mc.IsDragging) return;
            var cam = GetComponent<Camera>(); if (cam == null) cam = Camera.main; if (cam == null) return;
            int n = Physics.RaycastNonAlloc(cam.ScreenPointToRay(Input.mousePosition), hits, 500000f);
            System.Array.Sort(hits, 0, n, HitOrder.I);
            int year = TwinState.Year;
            for (int i = 0; i < n; i++)
            {
                var bim = BimQuarter.Instance;
                if (bim != null && BimQuarter.Visible && bim.Owns(hits[i].collider)) { Select(-1); bim.Select(bim.ElementAtTriangle(hits[i].triangleIndex)); return; }
                // a landmark (Iconic Complex, plants, campus …) in front of everything else: fly to it and open its passport
                var lo = hits[i].collider.GetComponent<Landmarks.LandmarkObject>();
                if (lo != null)
                {
                    var ls = Landmarks.LandmarkSystem.Instance; var lm = ls != null ? ls.Get(lo.Id) : null;
                    if (lm != null && ls.IsVisible(lm)) { ls.Select(lm); return; }
                    continue;                                                      // an empty plot (the object is not built in this year)
                }
                var ch = hits[i].collider.GetComponent<BuildingChunk>();
                if (ch == null) { Select(-1); return; }                       // ground hit first
                int bid = ch.BuildingAt(hits[i].triangleIndex);
                if (Landmarks.LandmarkSystem.IsHiddenBid(bid)) continue;          // replaced by a landmark
                int eff = ConstructionLayer.Active ? ConstructionLayer.VisibleFrom(bid) : CityStats.Ready ? CityStats.EffectiveYearOf(bid) : Mathf.RoundToInt(ch.YearAt(hits[i].triangleIndex));
                if (eff > year) continue;                                      // hidden by the timeline / scenario
                Select(bid); return;
            }
            Select(-1);
        }
        public void Select(int bid)
        {
            if (bid >= 0 && BimQuarter.Instance != null && BimQuarter.Instance.Selected >= 0) BimQuarter.Instance.Select(-1);
            if (bid >= 0 && Landmarks.LandmarkSystem.Instance != null && Landmarks.LandmarkSystem.Instance.Selected != null) Landmarks.LandmarkSystem.Instance.Select(null, false);
            var db = CityDatabase.Instance;
            var selected = db != null ? db.Get(bid) : null;
            Shader.SetGlobalFloat(SelId, selected != null ? bid + 1 : 0);
            TwinState.SetSelected(selected);
        }
        class HitOrder : System.Collections.Generic.IComparer<RaycastHit> { public static HitOrder I = new HitOrder(); public int Compare(RaycastHit a, RaycastHit b) => a.distance.CompareTo(b.distance); }
    }
}
