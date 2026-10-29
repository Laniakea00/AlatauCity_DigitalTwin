using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>The "architectural film" look of the scene: a sun that follows the hour, a sky, haze, shadows that fit the camera
    /// height, and facades on the buildings (AlatauLit reads _AlatauFilm and the per-building table _AlatauStyleTex made here).
    /// Switching it off gives back the plain maket look exactly as it was. F6 = on/off, F7 / F8 = earlier / later in the day.
    /// The look only changes the normal view: the construction and analysis modes keep their flat colours.</summary>
    public class FilmLook : MonoBehaviour
    {
        public bool on = true;
        [Range(4, 22)] public float hour = 17.0f;
        public static FilmLook Instance;
        /// <summary>The light of the moment for the systems that change with it (traffic, people, lamps): 0..1 how dark it is, how far the
        /// lamps and windows are lit, how much of the dusk glow there is; Active while the film look is applied.</summary>
        public static float Night, Lamps, Dusk; public static bool Active;
        /// <summary>The hour of the film look (4..22), for the capture tools and the interface. Stops the accelerated day; the header then shows the twin's time.</summary>
        public static void SetHour(float h) { if (Instance != null) { Instance.hour = Mathf.Clamp(h, 4f, 22f); Cycling = false; ViewerTime = true; } }
        /// <summary>The hour shown now (4..22).</summary>
        public static float Hour => Instance != null ? Instance.hour : 17f;
        /// <summary>The viewer has picked a time of day in the header (the header then shows the twin's time instead of the clock).</summary>
        public static bool ViewerTime;
        /// <summary>"Сутки за 2 минуты": the day runs from 5:00 to 22:00 in two minutes, over and over, until a time is picked.</summary>
        public static bool Cycling;
        public const float CycleFrom = 5f, CycleTo = 22f, CycleSeconds = 120f;
        public static void StartCycle() { if (Instance != null && (Instance.hour < CycleFrom || Instance.hour >= CycleTo - 0.05f)) Instance.hour = CycleFrom; Cycling = true; ViewerTime = true; }

        Light sun; Camera cam; MapCamera mc; Material sky; bool applied; FilmPost post; Renderer[] curtains = new Renderer[0]; FilmRoads roads; FilmTrees trees;
        // what the scene looked like before, to give it back
        Quaternion sunRot0; Color sunCol0, ambSky0, ambEq0, ambGr0, fogCol0; float sunInt0, sunStr0, fogStart0, fogEnd0, shadowDist0; FogMode fogMode0;

        static readonly int FilmId = Shader.PropertyToID("_AlatauFilm"), NightId = Shader.PropertyToID("_AlatauNight"), SunDirId = Shader.PropertyToID("_AlatauSunDir"),
            SunColId = Shader.PropertyToID("_AlatauSunColor"), ZenId = Shader.PropertyToID("_AlatauSkyZenith"), HorId = Shader.PropertyToID("_AlatauSkyHorizon"),
            GndId = Shader.PropertyToID("_AlatauSkyGround"), StyleId = Shader.PropertyToID("_AlatauStyleTex"),
            DuskId = Shader.PropertyToID("_AlatauDusk"), DarkId = Shader.PropertyToID("_AlatauDark"), LampOnId = Shader.PropertyToID("_AlatauLampOn"),
            SkyTexId = Shader.PropertyToID("_AlatauSkyTex"), SkyTexOnId = Shader.PropertyToID("_AlatauSkyTexOn");
        Texture2D skyPhoto;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { new GameObject("Film look").AddComponent<FilmLook>(); }

        /// <summary>Facade family of a building kind (see AlatauFilm.cginc).</summary>
        /// <summary>Radius around Iconic Complex drawn like its presentation model (white buildings, planted roofs), metres.</summary>
        public const float MaketR = 750f;
        public static int StyleOf(string kind)
        {
            switch (kind)
            {
                case "house": return 1;
                case "res_mid": case "res_high": case "residential": return 2;
                case "tower": case "business": case "mixed": case "hotel": return 3;
                case "public": case "education": case "health": case "culture": case "other": return 4;
                case "industry": case "utility": return 5;
                case "podium": case "retail": return 6;
                case "solar": return 7;
                case "resort": return 8;
                case "existing": return 9;
                default: return 0;
            }
        }

        void Start()
        {
            Instance = this;
            cam = Camera.main; mc = cam != null ? cam.GetComponent<MapCamera>() : null; sun = RenderSettings.sun;
            var sh = Shader.Find("AlatauCity/Sky"); if (sh != null) sky = new Material(sh) { name = "Film sky" };
            if (sun != null) { sunRot0 = sun.transform.rotation; sunCol0 = sun.color; sunInt0 = sun.intensity; sunStr0 = sun.shadowStrength; }
            ambSky0 = RenderSettings.ambientSkyColor; ambEq0 = RenderSettings.ambientEquatorColor; ambGr0 = RenderSettings.ambientGroundColor;
            fogCol0 = MapStyle.Background; fogMode0 = RenderSettings.fogMode; fogStart0 = RenderSettings.fogStartDistance; fogEnd0 = RenderSettings.fogEndDistance;
            shadowDist0 = QualitySettings.shadowDistance;
            if (cam != null) { post = cam.GetComponent<FilmPost>(); if (post == null) post = cam.gameObject.AddComponent<FilmPost>(); post.enabled = false; }
            // the translucent walls along the district boundaries belong to the map view, not to the film
            var list = new System.Collections.Generic.List<Renderer>();
            // ... and so do the plan's own road lines once real road ribbons are drawn
            foreach (var r in FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
                if (r.name.Contains("District boundary") || r.name == "Main roads" || r.name == "Highways" || r.name == "Planned street axes") list.Add(r);
            roads = gameObject.AddComponent<FilmRoads>(); trees = gameObject.AddComponent<FilmTrees>();
            // how the plan's line layers look in the film (AlatauLit reads _InfraKind): rivers are drawn by the ground's water, the ring-road
            // axis by the road ribbons, bridges get a deck, runways concrete
            foreach (var r in FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
            {
                float kind = r.name == "Rivers" || r.name.StartsWith("BAKAD") || r.name.Contains("bridges") ? 3f : r.name == "Runways" ? 5f : 0f;     // the plan's bridge slabs are wider than the roads: the film roads carry on over them
                if (kind == 0f) continue;
                var mpb = new MaterialPropertyBlock(); r.GetPropertyBlock(mpb); mpb.SetFloat("_InfraKind", kind); r.SetPropertyBlock(mpb);
            }
            curtains = list.ToArray();

            // material photo textures (built by Alatau City > Build material textures); without them the look falls back to flat colours
            var matA = Resources.Load<Texture2DArray>("Materials/AlatauMatAlbedo"); var matD = Resources.Load<Texture2DArray>("Materials/AlatauMatDetail"); var matM = Resources.Load<Texture2D>("Materials/AlatauMatMean");
            if (matA != null && matD != null && matM != null)
            {
                var mean = new Vector4[16]; var mp = matM.GetPixels(); for (int i = 0; i < 16 && i < mp.Length; i++) mean[i] = mp[i];
                Shader.SetGlobalTexture("_AlatauMatA", matA); Shader.SetGlobalTexture("_AlatauMatD", matD); Shader.SetGlobalVectorArray("_AlatauMatMean", mean); Shader.SetGlobalFloat("_AlatauMatOn", 1f);
            }
            else { Shader.SetGlobalFloat("_AlatauMatOn", 0f); Debug.LogWarning("[Alatau] film look: material textures not found in Resources/Materials"); }

            // the photographed day sky (upper half of a CC0 Poly Haven HDRI, its sun on the left edge): seen in the sky and in every
            // reflection; without it the gradient alone is drawn
            skyPhoto = Resources.Load<Texture2D>("Film/Gate/AlatauSkyDome");
            if (skyPhoto != null) { skyPhoto.wrapModeU = TextureWrapMode.Repeat; skyPhoto.wrapModeV = TextureWrapMode.Clamp; Shader.SetGlobalTexture(SkyTexId, skyPhoto); }
            Shader.SetGlobalFloat(SkyTexOnId, 0f);

            var blocks = Resources.Load<Texture2D>("Map/map_blocks");
            if (blocks != null) Shader.SetGlobalTexture("_AlatauBlockTex", blocks);
            Shader.SetGlobalFloat("_AlatauBlockOn", blocks != null ? 1f : 0f);

            var db = CityDatabase.Instance;
            if (db != null)
            {
                var px = new Color32[256 * 256];
                // around Iconic the district looks as on the presentation model shown with it: white buildings, planted roofs (style 10)
                Landmarks.Landmark icl = null; foreach (var q in Landmarks.LandmarkCatalog.All()) if (q.Id == "iconic") icl = q; var ic = icl != null ? new Vector2(icl.X, icl.Z) : new Vector2(-3170f, -19080f);
                foreach (var b in db.Buildings) if (b != null && b.Bid >= 0 && b.Bid < px.Length)
                {
                    int st = (new Vector2(b.X, b.Z) - ic).sqrMagnitude < MaketR * MaketR && b.Source != "existing_osm" ? 10 : StyleOf(b.Kind);
                    px[b.Bid] = new Color32((byte)st, (byte)((uint)(b.Bid * 2654435761u) >> 24), (byte)Mathf.Clamp(b.Floors, 1, 255), 255);
                }
                var tex = new Texture2D(256, 256, TextureFormat.RGBA32, false, true) { name = "Alatau building style", filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
                tex.SetPixels32(px); tex.Apply(false, false); Shader.SetGlobalTexture(StyleId, tex);
            }
        }

        void Update()
        {
            LateCycle();
            if (MapCamera.Typing) return;
            if (Input.GetKeyDown(KeyCode.F6)) on = !on;
            if (Input.GetKey(KeyCode.F7)) { hour = Mathf.Max(4f, hour - 2f * Time.deltaTime); Cycling = false; }
            if (Input.GetKey(KeyCode.F8)) { hour = Mathf.Min(22f, hour + 2f * Time.deltaTime); Cycling = false; }
        }

        void LateCycle()
        {
            if (!Cycling) return;
            hour += (CycleTo - CycleFrom) / CycleSeconds * Time.unscaledDeltaTime;
            if (hour >= CycleTo) hour = CycleFrom;
        }

        void LateUpdate()
        {
            // the film look stays on in every tab: the other modules colour the buildings by data over the same facades and light
            if (on) Apply(); else if (applied) Restore();
        }

        void OnDisable() { if (applied) Restore(); }

        void Apply()
        {
            applied = true;
            // the sun: up at 5:30 in the east, highest in the south, down at 18:30 in the west
            float day = (hour - 5.5f) / 13f, el = day >= 0f && day <= 1f ? Mathf.Sin(day * Mathf.PI) * 58f : -Mathf.Min(12f, (day < 0f ? -day : day - 1f) * 13f * 8f);
            float az = Mathf.Lerp(75f, 285f, Mathf.Clamp01(day)) * Mathf.Deg2Rad, e = Mathf.Max(el, 4f) * Mathf.Deg2Rad;
            // after dark the light comes from the moon, high in the south-east (the sky draws its disc there): grazing light from a
            // sun under the horizon would leave the ground black
            float nightK = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(-3f, -11f, el));
            e = Mathf.Lerp(e, 38f * Mathf.Deg2Rad, nightK); az = Mathf.Lerp(az, (day < 0.5f ? 120f : 150f) * Mathf.Deg2Rad, nightK);
            var toSun = new Vector3(Mathf.Sin(az) * Mathf.Cos(e), Mathf.Sin(e), Mathf.Cos(az) * Mathf.Cos(e));
            float gold = 1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(6f, 30f, el));              // low sun
            float dusk = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(7f, -2f, el));                    // the sun is going, the horizon glows
            float night = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(-3f, -11f, el));                 // dark
            float lamps = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(9f, -5f, el));                   // windows light up from dusk on
            Color sunC = Color.Lerp(Color.Lerp(Color.Lerp(new Color(1f, 0.96f, 0.90f), new Color(1f, 0.74f, 0.47f), gold), new Color(1f, 0.56f, 0.40f), dusk), new Color(0.34f, 0.42f, 0.62f), night);
            Color zen = Color.Lerp(Color.Lerp(Color.Lerp(new Color(0.27f, 0.48f, 0.80f), new Color(0.30f, 0.44f, 0.70f), gold), new Color(0.15f, 0.22f, 0.44f), dusk), new Color(0.025f, 0.04f, 0.10f), night);
            Color hor = Color.Lerp(Color.Lerp(Color.Lerp(new Color(0.75f, 0.80f, 0.87f), new Color(0.97f, 0.78f, 0.58f), gold), new Color(0.93f, 0.56f, 0.40f), dusk), new Color(0.10f, 0.12f, 0.22f), night);
            Color gnd = Color.Lerp(hor, new Color(0.5f, 0.5f, 0.5f), 0.35f) * 0.85f;
            if (sun != null)
            {
                sun.transform.rotation = Quaternion.LookRotation(-toSun);
                // after dark the "sun" is the moon: a cool, soft light that keeps the city legible
                sun.color = sunC; sun.intensity = Mathf.Lerp(Mathf.Lerp(Mathf.Lerp(1.0f, 0.95f, gold), 0.50f, dusk), 0.27f, night); sun.shadowStrength = Mathf.Lerp(Mathf.Lerp(0.86f, 0.55f, dusk), 0.40f, night);
            }
            float skyLight = Mathf.Lerp(1f, 1.35f, dusk) * Mathf.Lerp(1f, 0.9f, night);                    // after sunset the sky is most of the light
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = Color.Lerp(zen, hor, 0.45f) * 0.80f * skyLight; RenderSettings.ambientEquatorColor = Color.Lerp(hor, zen, 0.5f * dusk) * 0.62f * skyLight; RenderSettings.ambientGroundColor = gnd * 0.45f;
            // night fill: the sky glow over a lit city (cool from above, warm from the streets below), so a night aerial still reads
            RenderSettings.ambientSkyColor += new Color(0.035f, 0.045f, 0.075f) * night; RenderSettings.ambientEquatorColor += new Color(0.03f, 0.035f, 0.055f) * night;
            RenderSettings.ambientGroundColor += new Color(0.04f, 0.03f, 0.02f) * night;
            // haze: the further the camera is from what it looks at, the further it sees
            float dist = mc != null ? mc.distance : 3000f, vis = Mathf.Clamp(dist * 7f, 22000f, 320000f);
            RenderSettings.fog = true; RenderSettings.fogMode = FogMode.ExponentialSquared; RenderSettings.fogDensity = 0.83f / vis; RenderSettings.fogColor = Color.Lerp(hor, zen, 0.12f + 0.3f * dusk) + new Color(0.025f, 0.015f, 0.008f) * night;
            QualitySettings.shadowDistance = Mathf.Clamp(dist * 3.2f, 900f, 40000f);
            if (cam != null && sky != null) { RenderSettings.skybox = sky; cam.clearFlags = CameraClearFlags.Skybox; }
            if (post != null)
            {
                post.enabled = true; post.aoRadius = Mathf.Clamp(dist * 0.012f, 5f, 60f);
                post.focus = dist; post.focusRange = dist * 0.75f; post.depthOfField = true; post.maxBlur = 2f * (1f - Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(3500f, 9000f, dist)));   // a hint of depth only: blur reads as low quality
            }
            foreach (var r in curtains) if (r != null && r.enabled) r.enabled = false;
            Shader.SetGlobalFloat("_AlatauScenIdx", (int)TwinState.Scenario);
            if (roads != null) roads.Show(true);
            Redraw();
            Active = true; Night = night; Lamps = lamps; Dusk = dusk;
            Shader.SetGlobalFloat(FilmId, 1f); Shader.SetGlobalFloat(NightId, lamps); Shader.SetGlobalVector(SunDirId, toSun);
            Shader.SetGlobalFloat(DuskId, dusk); Shader.SetGlobalFloat(DarkId, night); Shader.SetGlobalFloat(LampOnId, lamps);
            Shader.SetGlobalFloat(SkyTexOnId, skyPhoto != null ? (1f - dusk) * (1f - night) * (1f - 0.35f * gold) : 0f);
            Shader.SetGlobalColor(SunColId, sunC); Shader.SetGlobalColor(ZenId, zen); Shader.SetGlobalColor(HorId, hor); Shader.SetGlobalColor(GndId, gnd);
        }

        /// <summary>Things drawn frame by frame (the trees). The capture tool calls this right before it renders by hand.</summary>
        public void Redraw() { if (applied && trees != null && cam != null && mc != null) trees.Draw(cam, mc.target, mc.distance); if (applied) FilmLamps.DrawNow(); }

        void Restore()
        {
            applied = false;
            if (sun != null) { sun.transform.rotation = sunRot0; sun.color = sunCol0; sun.intensity = sunInt0; sun.shadowStrength = sunStr0; }
            RenderSettings.ambientSkyColor = ambSky0; RenderSettings.ambientEquatorColor = ambEq0; RenderSettings.ambientGroundColor = ambGr0;
            RenderSettings.fogMode = fogMode0; RenderSettings.fogStartDistance = fogStart0; RenderSettings.fogEndDistance = fogEnd0; RenderSettings.fogColor = fogCol0;
            QualitySettings.shadowDistance = shadowDist0;
            if (cam != null) { cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = MapStyle.Background; }
            RenderSettings.skybox = null;
            if (post != null) post.enabled = false;
            foreach (var r in curtains) if (r != null) r.enabled = true;
            if (roads != null) roads.Show(false);
            Active = false; Night = 0f; Lamps = 0f; Dusk = 0f;
            Shader.SetGlobalFloat(FilmId, 0f); Shader.SetGlobalFloat(SkyTexOnId, 0f);
            Shader.SetGlobalFloat(DuskId, 0f); Shader.SetGlobalFloat(DarkId, 0f); Shader.SetGlobalFloat(LampOnId, 0f);
        }
    }
}
