using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Visual style of the scene at runtime: the new base map (plan / before development / development year) with the
    /// AlatauCity/Ground shader, no baked 3D legend and titles from the Blender model (the UI shows them instead), calm background,
    /// and the per-building geometry lookup (_AlatauGeoTex: base Y, height) used by the timeline growth animation.</summary>
    public class MapStyle : MonoBehaviour
    {
        public static readonly Color Background = new Color(0.075f, 0.078f, 0.085f);

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { new GameObject("Map style").AddComponent<MapStyle>(); }

        static void Recolor(string name, Color32 c)
        {
            var go = GameObject.Find(name); if (go == null) return; var mf = go.GetComponent<MeshFilter>(); if (mf == null) return;
            var m = mf.mesh; var cols = new Color32[m.vertexCount]; for (int i = 0; i < cols.Length; i++) cols[i] = c; m.colors32 = cols;
        }

        void Start()
        {
            var terrain = GameObject.Find("Terrain (master plan map)");
            var plan = Resources.Load<Texture2D>("Map/map_plan"); var nat = Resources.Load<Texture2D>("Map/map_nature"); var dev = Resources.Load<Texture2D>("Map/map_dev");
            var city = Resources.Load<Texture2D>("Map/map_city"); var dist = Resources.Load<Texture2D>("Map/map_districts");
            var sh = Shader.Find("AlatauCity/Ground");
            if (terrain != null && plan != null && nat != null && dev != null && sh != null)
            {
                var mr = terrain.GetComponent<MeshRenderer>();
                var m = new Material(sh) { name = "Ground (plan by year)" };
                m.mainTexture = plan; m.SetTexture("_NatTex", nat); m.SetTexture("_DevTex", dev);
                // variant C: the city boundary (signed distance) — muted context outside, a warm outline, the map edges dissolve
                if (city != null) { m.SetTexture("_CityTex", city); m.SetFloat("_CityOn", 1f); }
                if (dist != null) m.SetTexture("_DistTex", dist);
                mr.sharedMaterial = m;
            }
            else Debug.LogWarning("[Alatau] base map: missing " + (terrain == null ? "terrain " : "") + (plan == null ? "textures " : "") + (sh == null ? "shader" : ""));
            var labels = GameObject.Find("Labels"); if (labels != null) labels.SetActive(false);

            var cam = Camera.main; if (cam != null) cam.backgroundColor = Background;
            RenderSettings.fogColor = Background;

            var db = CityDatabase.Instance;
            if (db != null)
            {
                var geo = new float[256 * 256 * 4];
                foreach (var b in db.Buildings) if (b != null && b.Bid >= 0 && b.Bid < 65536) { geo[b.Bid * 4] = b.GroundM; geo[b.Bid * 4 + 1] = b.HeightM; }
                var tex = new Texture2D(256, 256, TextureFormat.RGBAFloat, false, true) { name = "Alatau building geo", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
                tex.SetPixelData(geo, 0); tex.Apply(false, false); Shader.SetGlobalTexture("_AlatauGeoTex", tex);
            }
            Shader.SetGlobalFloat("_AlatauGrow", 0f); Shader.SetGlobalFloat("_AlatauBldSat", 0.45f);
            // calmer line colours of the Blender transport layer (instances, the assets stay untouched)
            Recolor("LRT line", new Color32(178, 132, 226, 255)); Recolor("Planned street axes", new Color32(176, 173, 166, 255));
            Recolor("Rivers", new Color32(90, 142, 186, 255)); Recolor("Railways on the plan", new Color32(120, 120, 126, 255));
        }

        static readonly int EdgeId = Shader.PropertyToID("_AlatauEdgeCol"), CamDistId = Shader.PropertyToID("_AlatauCamDist"), FocusId = Shader.PropertyToID("_AlatauFocusD");
        void LateUpdate()
        {
            // the map's edges fade into what is behind them: the fog / background colour (the film look changes it with the time of day)
            Shader.SetGlobalColor(EdgeId, RenderSettings.fogColor);
            var cam = Camera.main; var mc = cam != null ? cam.GetComponent<MapCamera>() : null;
            Shader.SetGlobalFloat(CamDistId, mc != null ? mc.distance : 30000f);
            // the district in focus (picker in the header, presentation zones) is highlighted on the ground
            Shader.SetGlobalFloat(FocusId, TwinState.District);
        }
    }
}
