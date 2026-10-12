using System;
using System.Collections.Generic;
using UnityEngine;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Effects of the presentation that live longer than one call: a cinematic camera glide over a district, and the "spotlight"
    /// that lights up categories of buildings one after another (universities → schools → hospitals …) with a label per category.
    /// Everything is undone by Reset() at the start of every step and when the presentation ends.</summary>
    public class TourFx : MonoBehaviour
    {
        public static TourFx Instance;
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot() { if (Instance == null) new GameObject("Tour effects").AddComponent<TourFx>(); }
        void Awake() { Instance = this; }

        // ------------------------------------------------------------------ glide
        class Glide { public Vector2 A, B; public float D0, D1, Yaw0, Yaw1, P0, P1, Dur, T; public bool Broken; public Vector3 StartT; public float StartD, StartY, StartP; }
        Glide glide;

        /// <summary>Principal axis of a district (from its buildings): centre, unit direction and length (5–95 % along the axis).</summary>
        public static bool DistrictAxis(int d, out Vector2 c, out Vector2 dir, out float len, out float width, Func<BuildingInfo, bool> only = null)
        {
            c = Vector2.zero; dir = Vector2.up; len = 4000f; width = 2000f;
            var db = CityDatabase.Instance; if (db == null || d < 0) return false;
            var pts = new List<Vector2>(); string id = CityStats.DistrictIds[d];
            foreach (var b in db.Buildings) if (b != null && b.District == id && (only == null || only(b))) pts.Add(new Vector2(b.X, b.Z));
            if (pts.Count < 10) return false;
            foreach (var p in pts) c += p; c /= pts.Count;
            float sxx = 0, sxy = 0, syy = 0; foreach (var p in pts) { var q = p - c; sxx += q.x * q.x; sxy += q.x * q.y; syy += q.y * q.y; }
            float ang = 0.5f * Mathf.Atan2(2f * sxy, sxx - syy); dir = new Vector2(Mathf.Cos(ang), Mathf.Sin(ang));
            var along = new List<float>(); var across = new List<float>();
            var nrm = new Vector2(-dir.y, dir.x);
            foreach (var p in pts) { along.Add(Vector2.Dot(p - c, dir)); across.Add(Vector2.Dot(p - c, nrm)); }
            along.Sort(); across.Sort();
            float a0 = along[along.Count * 5 / 100], a1 = along[along.Count * 95 / 100];
            len = a1 - a0; width = across[across.Count * 95 / 100] - across[across.Count * 5 / 100];
            c += dir * (a0 + a1) * 0.5f;
            return true;
        }

        /// <summary>A slow oblique flight along a district: from 'from' to 'to' (fractions of the axis, -0.5..0.5), the camera looking across
        /// the city at 'pitch', distance easing from d0 to d1, heading turning by 'turn' degrees. Starts from the current pose (blend 3 s).</summary>
        public void GlideDistrict(int d, float dur, float from = -0.32f, float to = 0.30f, float d0 = 3600f, float d1 = 2600f, float pitch = 30f, float turn = 18f, Func<BuildingInfo, bool> only = null)
        {
            if (!DistrictAxis(d, out var c, out var dir, out var len, out var wid, only)) return;
            var cam = Cam; if (cam == null) return;
            float heading = Mathf.Atan2(dir.x, dir.y) * Mathf.Rad2Deg;          // yaw that looks along the axis
            float yaw0 = heading + 35f;                                          // look slightly across the axis: depth and skyline
            glide = new Glide { A = c + dir * (len * from), B = c + dir * (len * to), D0 = d0, D1 = d1, Yaw0 = yaw0, Yaw1 = yaw0 + turn, P0 = pitch + 4f, P1 = pitch, Dur = dur,
                                StartT = cam.target, StartD = cam.distance, StartY = cam.yaw, StartP = cam.pitch };
            cam.StopFly();
        }
        /// <summary>The same kind of flight between two points (world x/z).</summary>
        public void GlideLine(Vector2 a, Vector2 b, float dur, float d0, float d1, float yaw0, float yaw1, float p0, float p1)
        {
            var cam = Cam; if (cam == null) return;
            glide = new Glide { A = a, B = b, D0 = d0, D1 = d1, Yaw0 = yaw0, Yaw1 = yaw1, P0 = p0, P1 = p1, Dur = dur, StartT = cam.target, StartD = cam.distance, StartY = cam.yaw, StartP = cam.pitch };
            cam.StopFly();
        }

        static MapCamera Cam => Camera.main != null ? Camera.main.GetComponent<MapCamera>() : null;
        public static bool Paused;

        void LateUpdate()
        {
            if (glide == null || Paused) return;
            var cam = Cam; if (cam == null) return;
            if (MapCamera.UserMoved || Landmarks.LandmarkSystem.Instance?.Selected != null) { glide = null; return; }          // the presenter takes the camera: the glide gives way
            if (cam.IsFlying) cam.StopFly();                       // a district / module change may start its own flight: the presentation's glide wins
            glide.T += Time.deltaTime;
            float u = Mathf.Clamp01(glide.T / glide.Dur), e = u * u * (3f - 2f * u);
            var p = Vector2.Lerp(glide.A, glide.B, e);
            float d = Mathf.Lerp(glide.D0, glide.D1, e), y = Mathf.Lerp(glide.Yaw0, glide.Yaw1, e), pt = Mathf.Lerp(glide.P0, glide.P1, e);
            // blend in from where the camera was
            float bl = Mathf.Clamp01(glide.T / 3f); bl = bl * bl * (3f - 2f * bl);
            var tgt = Vector3.Lerp(glide.StartT, new Vector3(p.x, 0, p.y), bl);
            cam.SetPose(new Vector3(tgt.x, 0, tgt.z), Mathf.Exp(Mathf.Lerp(Mathf.Log(glide.StartD), Mathf.Log(d), bl)), Mathf.LerpAngle(glide.StartY, y, bl), Mathf.Lerp(glide.StartP, pt, bl), 0f);
            if (u >= 1f) glide = null;
        }

        // ------------------------------------------------------------------ spotlight
        public class Cat { public string Name; public Color Col; public Func<BuildingInfo, bool> Is; public int Count; public BuildingInfo Biggest; }
        readonly List<Cat> shown = new List<Cat>();

        /// <summary>Lights up one more category of buildings in a district (the others stay lit), in the film look: the category takes its
        /// colour with a soft glow, arriving with a wave of light that runs out from the centre of the district; a label with the count.</summary>
        static readonly int HiOnId = Shader.PropertyToID("_AlatauHiOn"), HiCurId = Shader.PropertyToID("_AlatauHiCur"), HiWaveId = Shader.PropertyToID("_AlatauHiWave"), HiColId = Shader.PropertyToID("_AlatauHiCol");
        Vector2 waveC; float waveR = -1f, waveMax;
        public void Spot(int district, Cat cat)
        {
            var db = CityDatabase.Instance; if (db == null) return;
            string id = district >= 0 ? CityStats.DistrictIds[district] : null;
            cat.Count = 0; cat.Biggest = null;
            foreach (var b in db.Buildings)
                if (b != null && (id == null || b.District == id) && cat.Is(b) && !Landmarks.LandmarkSystem.IsHiddenBid(b.Bid))
                { cat.Count++; if (cat.Biggest == null || b.GfaM2 > cat.Biggest.GfaM2) cat.Biggest = b; }
            shown.Add(cat);
            UI.StoryCard.Light(cat.Name, cat.Count);                                  // the legend on the step's dashboard
            TintLayer.Disable();                                                     // film look stays on (no analysis greying)
            TintLayer.Apply(b =>
            {
                if (id != null && b.District != id) return new Color(0, 0, 0, 0);
                for (int i = shown.Count - 1; i >= 0; i--) if (shown[i].Is(b)) return new Color(shown[i].Col.r, shown[i].Col.g, shown[i].Col.b, (i + 1) / 8f);
                return new Color(0, 0, 0, 0);
            });
            if (!DistrictAxis(district, out waveC, out _, out float len, out float wid)) { waveC = cat.Biggest != null ? new Vector2(cat.Biggest.X, cat.Biggest.Z) : Vector2.zero; len = 8000f; }
            waveMax = Mathf.Max(len, 3000f) * 0.75f; waveR = 0f;
            Shader.SetGlobalFloat(HiOnId, 1f); Shader.SetGlobalFloat(HiCurId, shown.Count); Shader.SetGlobalColor(HiColId, cat.Col);
            Beams(id, cat);
            var pins = new List<MapPins.Pin>();
            foreach (var c in shown)
                if (c.Biggest != null)
                    pins.Add(new MapPins.Pin { Id = "spot_" + c.Name, Label = c.Name + " · " + Loc.N0(c.Count), World = new Vector3(c.Biggest.X, CityGround.HeightAt(c.Biggest.X, c.Biggest.Z) + c.Biggest.HeightM + 25f, c.Biggest.Z),
                                               Fill = c.Col, ShowLabel = true, Size = 14f });
            MapPins.Instance?.Set(pins);
        }
        // light beams over the biggest buildings of each category (a constellation that reads from far away)
        readonly List<GameObject> beams = new List<GameObject>(); readonly List<Material> beamMats = new List<Material>();
        void Beams(string id, Cat cat)
        {
            var sh = Shader.Find("AlatauCity/Beam"); var db = CityDatabase.Instance; if (sh == null || db == null) return;
            foreach (var m in beamMats) m.SetFloat("_Done", 1f);                 // earlier categories keep their beams
            var list = new List<BuildingInfo>();
            foreach (var b in db.Buildings) if (b != null && (id == null || b.District == id) && cat.Is(b) && !Landmarks.LandmarkSystem.IsHiddenBid(b.Bid)) list.Add(b);
            list.Sort((x, y) => y.GfaM2.CompareTo(x.GfaM2));
            // a few beams per category, spread out (the biggest first, none closer than 450 m to another): a constellation, not a fence
            var pick = new List<BuildingInfo>();
            foreach (var b in list)
            {
                if (pick.Count >= 10) break;
                bool near = false; foreach (var q in pick) if ((q.X - b.X) * (q.X - b.X) + (q.Z - b.Z) * (q.Z - b.Z) < 450f * 450f) { near = true; break; }
                if (!near) pick.Add(b);
            }
            list = pick;
            var V = new List<Vector3>(); var U = new List<Vector2>(); var U2 = new List<Vector2>(); var T = new List<int>();
            int n = list.Count;
            for (int i = 0; i < n; i++)
            {
                var b = list[i]; float top = b.GroundM + Mathf.Max(b.HeightM, 6f), h = 240f + 140f * (1f - i / (float)n), w = 30f;
                float d = Vector2.Distance(new Vector2(b.X, b.Z), waveC);
                for (int q = 0; q < 2; q++)
                {
                    var ax = q == 0 ? new Vector3(w * 0.5f, 0, 0) : new Vector3(0, 0, w * 0.5f); int k = V.Count; var c = new Vector3(b.X, top, b.Z);
                    V.Add(c - ax); V.Add(c + ax); V.Add(c + ax + Vector3.up * h); V.Add(c - ax + Vector3.up * h);
                    U.Add(new Vector2(0, 0)); U.Add(new Vector2(1, 0)); U.Add(new Vector2(1, 1)); U.Add(new Vector2(0, 1));
                    for (int j = 0; j < 4; j++) U2.Add(new Vector2(d, 0));
                    T.Add(k); T.Add(k + 1); T.Add(k + 2); T.Add(k); T.Add(k + 2); T.Add(k + 3);
                }
            }
            if (V.Count == 0) return;
            var mesh = new Mesh { name = "Beams " + cat.Name }; mesh.SetVertices(V); mesh.SetUVs(0, U); mesh.SetUVs(1, U2); mesh.SetTriangles(T, 0); mesh.RecalculateBounds();
            var go = new GameObject("Beams " + cat.Name); go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mat = new Material(sh) { name = "Beams " + cat.Name }; mat.SetColor("_Color", cat.Col * 0.9f); mat.SetFloat("_Done", 0f);
            var mr = go.AddComponent<MeshRenderer>(); mr.sharedMaterial = mat; mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            beams.Add(go); beamMats.Add(mat);
        }
        void ClearBeams() { foreach (var g in beams) if (g != null) Destroy(g); foreach (var m in beamMats) if (m != null) Destroy(m); beams.Clear(); beamMats.Clear(); }

        void WaveStep(float dt)
        {
            if (waveR < 0f) return;
            waveR += dt * waveMax / 3.2f;
            Shader.SetGlobalVector(HiWaveId, new Vector4(waveC.x, waveC.y, waveR, waveMax));
        }

        // ------------------------------------------------------------------ Silk Road map
        UI.SilkRoadMap silk;
        public void ShowSilkRoad()
        {
            var ui = UI.TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            silk?.RemoveFromHierarchy();
            silk = new UI.SilkRoadMap(); ui.Scene.Insert(0, silk); silk.Play();
            ui.Middle?.AddToClassList("tour-map");
        }

        // ------------------------------------------------------------------ situation centre: one incident from alarm to solution
        UI.SituationShow sit;
        public void ShowSituation(string id)
        {
            var ui = UI.TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            var mod = ui.Active as Modules.SituationModule; if (mod == null) return;
            mod.TourOpen(id, false);
            var inc = Modules.SituationModule.Find(id); if (inc == null) return;
            sit?.RemoveFromHierarchy();
            sit = new UI.SituationShow(inc, mod); ui.Scene.Add(sit);
            ui.Middle?.AddToClassList("tour-clean");
        }
        // ------------------------------------------------------------------ construction control: the year runs, the figures and the late sites follow
        bool cw; int cwYear = -1;
        public void ConstructionWatch() { cw = true; cwYear = -1; }
        void ConstructionStep()
        {
            if (!cw || TwinState.Year == cwYear) return;
            cwYear = TwinState.Year; int s = (int)TwinState.Scenario;
            ConstructionLayer.Compute(cwYear, s);
            float km = LineLayers.RoadKmInWork(cwYear, s); foreach (var k in LineLayers.NetKeys) km += LineLayers.KmInWork(k, cwYear, s);
            Callout("КОНТРОЛЬ СТРОЙКИ · " + cwYear, new[] {
                (Loc.N0(ConstructionLayer.Sites), "строек идёт", new Color(0.45f, 0.75f, 1f)),
                (Loc.N0(ConstructionLayer.SitesBehind), "отстают от графика", new Color(1f, 0.38f, 0.30f)),
                (Loc.N0(km), "км сетей и дорог в работе", new Color(1f, 0.78f, 0.30f)) },
                "Каждая стройка, сеть и дорога — на одной карте: план против факта");
            // the late sites in the frame (Gate and Golden, along the glide): the biggest delays first
            var db = CityDatabase.Instance; var pins = new List<MapPins.Pin>(); int n = 0;
            if (db != null)
            {
                var late = new List<BuildingInfo>();
                foreach (var b in db.Buildings) if (b != null && b.Z < -4000f && ConstructionLayer.StateOf(b.Bid) == ConstructionLayer.Behind) late.Add(b);
                late.Sort((x, y) => (ConstructionLayer.Delay(y.Bid) * y.GfaM2).CompareTo(ConstructionLayer.Delay(x.Bid) * x.GfaM2));
                foreach (var b in late)
                {
                    if (pins.Exists(p => (new Vector2(p.World.x, p.World.z) - new Vector2(b.X, b.Z)).sqrMagnitude < 900f * 900f)) continue;   // spread over the map
                    pins.Add(new MapPins.Pin { Id = "late" + n, Label = "+" + ConstructionLayer.Delay(b.Bid) + " мес. к графику", World = new Vector3(b.X, b.GroundM + b.HeightM + 25f, b.Z), Fill = new Color(1f, 0.25f, 0.2f), Status = "bad", ShowLabel = n < 4, Size = 14f });
                    if (++n == 6) break;
                }
            }
            MapPins.Instance?.Set(pins);
        }

        UI.AiShow ai;
        public void ShowAi()
        {
            var ui = UI.TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            ai?.RemoveFromHierarchy(); ai = new UI.AiShow(TwinState.Year); ui.Scene.Add(ai); Clean(true);
        }
        TourSeaside seaside;
        public void Seaside() { seaside?.Stop(); seaside = new TourSeaside(); }
        TourEnergy energy;
        public void ShowEnergy()
        {
            energy?.Stop(); energy = new TourEnergy(); Clean(true);
            GlideDistrict(1, 30f, -0.30f, 0.22f, 5600f, 4300f, 40f, 16f);
        }
        /// <summary>Hides the side panels for a full-screen WOW step (the overlay tells the story itself).</summary>
        public void Clean(bool on) { var m = UI.TwinUI.Instance?.Middle; if (m == null) return; if (on) m.AddToClassList("tour-clean"); else m.RemoveFromClassList("tour-clean"); }

        // ------------------------------------------------------------------ callout: one card with big figures over the map
        UnityEngine.UIElements.VisualElement callout; UnityEngine.UIElements.Label coTitle, coNote; UnityEngine.UIElements.VisualElement coRow;
        public void Callout(string title, (string v, string l, Color c)[] figs, string note)
        {
            var ui = UI.TwinUI.Instance; if (ui == null || ui.Scene == null) return;
            if (callout == null || callout.parent == null)
            {
                callout = new UnityEngine.UIElements.VisualElement { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; callout.AddToClassList("tour-callout");
                coTitle = new UnityEngine.UIElements.Label { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; coTitle.AddToClassList("co-title"); callout.Add(coTitle);
                coRow = new UnityEngine.UIElements.VisualElement { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; coRow.AddToClassList("co-row"); callout.Add(coRow);
                coNote = new UnityEngine.UIElements.Label { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; coNote.AddToClassList("co-note"); callout.Add(coNote);
                ui.Scene.Add(callout);
            }
            coTitle.text = title; coNote.text = note ?? ""; coNote.style.display = string.IsNullOrEmpty(note) ? UnityEngine.UIElements.DisplayStyle.None : UnityEngine.UIElements.DisplayStyle.Flex;
            coRow.Clear();
            foreach (var (v, l, c) in figs)
            {
                var f = new UnityEngine.UIElements.VisualElement { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; f.AddToClassList("co-fig");
                var vl = new UnityEngine.UIElements.Label(v) { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; vl.AddToClassList("co-v"); vl.style.color = c; f.Add(vl);
                var ll = new UnityEngine.UIElements.Label(l) { pickingMode = UnityEngine.UIElements.PickingMode.Ignore }; ll.AddToClassList("co-l"); f.Add(ll);
                coRow.Add(f);
            }
        }
        void HideCallout() { callout?.RemoveFromHierarchy(); callout = null; }

        // ------------------------------------------------------------------ flood: the reservoir rises over the shore, the twin protects it
        GameObject water; Material waterMat; float fT, fBase, fRise, fRiseT, fProtectAt, fLevel, fTint; int fDistrict; bool flooding;
        /// <summary>Water sheet over 'area' (world x/z) at 'baseLevel' that rises by 'rise' metres in 'riseTime' s; at 'protectAt' s the twin's
        /// measures (dam, regulated release) bring it back down to a safe level. Buildings below the water are outlined live.</summary>
        public void Flood(Rect area, int district, float baseLevel, float rise, float riseTime, float protectAt)
        {
            if (water == null)
            {
                var sh = Shader.Find("AlatauCity/Water"); if (sh == null) { Debug.LogWarning("[Alatau] water shader missing"); return; }
                waterMat = new Material(sh) { name = "Flood water" };
                water = new GameObject("Flood water"); var mf = water.AddComponent<MeshFilter>(); var mr = water.AddComponent<MeshRenderer>(); mr.sharedMaterial = waterMat;
                mr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                var m = new Mesh { name = "Water sheet" };
                m.vertices = new[] { new Vector3(-0.5f, 0, -0.5f), new Vector3(0.5f, 0, -0.5f), new Vector3(0.5f, 0, 0.5f), new Vector3(-0.5f, 0, 0.5f) };
                m.triangles = new[] { 0, 2, 1, 0, 3, 2 }; m.RecalculateNormals(); m.RecalculateBounds(); mf.sharedMesh = m;
            }
            water.SetActive(true);
            water.transform.position = new Vector3(area.center.x, baseLevel, area.center.y); water.transform.localScale = new Vector3(area.width, 1, area.height);
            fT = 0; fBase = baseLevel; fRise = rise; fRiseT = riseTime; fProtectAt = protectAt; fDistrict = district; fLevel = baseLevel; fTint = -1; flooding = true;
        }

        void FloodStep(float dt)
        {
            if (!flooding || water == null) return;
            fT += dt;
            float up = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(fT / fRiseT)), down = fT > fProtectAt ? Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((fT - fProtectAt) / 5f)) : 0f;
            fLevel = fBase + fRise * up - (fRise + 0.6f) * down;            // the measures bring the water back below the old shore line
            water.transform.position = new Vector3(water.transform.position.x, fLevel, water.transform.position.z);
            if (Mathf.Abs(fLevel - fTint) < 0.08f) return;
            fTint = fLevel;
            // buildings standing below the water: red; once protected, the ones the measures saved turn green
            var db = CityDatabase.Instance; if (db == null) return;
            string id = CityStats.DistrictIds[Mathf.Clamp(fDistrict, 0, 3)];
            int wet = 0; float people = 0; bool saved = fT > fProtectAt;
            float peak = fBase + fRise;
            TintLayer.Enable();
            TintLayer.Apply(b =>
            {
                if (b.District != id || b.Source == "existing_osm" && false) return new Color(0, 0, 0, 0);
                // once the twin's measures work, every building of the risk zone is shown saved (green), none is left under water
                if (saved && b.GroundM < peak) return new Color(0.22f, 0.82f, 0.42f, 0.85f);
                if (!saved && b.GroundM < fLevel) { wet++; if (b.Kind == "house" || b.Kind.StartsWith("res")) people += b.GfaM2 / 30f; return new Color(1f, 0.28f, 0.20f, 0.92f); }
                return new Color(0, 0, 0, 0);
            });
            int at = 0; float atP = 0; foreach (var b in db.Buildings) if (b != null && b.District == id && b.GroundM < peak) { at++; if (b.Kind == "house" || b.Kind.StartsWith("res")) atP += b.GfaM2 / 30f; }
            if (!saved)
                Callout("Капшагай: подъём воды", new[] { ("+" + Loc.N1(fLevel - fBase) + " м", "уровень воды", new Color(0.45f, 0.75f, 1f)), (Loc.N0(wet), "зданий в зоне затопления", new Color(1f, 0.38f, 0.30f)), ("≈ " + Loc.N0(people / 1000f) + " тыс.", "жителей под угрозой", new Color(1f, 0.38f, 0.30f)) }, "Модель двойника: рельеф, уровни воды, отметки зданий");
            else
                Callout("Решение двойника принято", new[] { ("норма", "уровень после мер", new Color(0.45f, 0.75f, 1f)), (Loc.N0(at), "зданий спасено", new Color(0.30f, 0.85f, 0.45f)), ("≈ " + Loc.N0(atP / 1000f) + " тыс.", "жителей вне опасности", new Color(0.30f, 0.85f, 0.45f)) }, "Дамба на берегу и регулируемый сброс воды — за 48 часов до пика");
        }

        // ------------------------------------------------------------------ evening: the sun goes down, the resorts light up
        float eveFrom = -1f, eveTo, eveT, eveDur, hour0 = -1f;
        public void Evening(float toHour, float dur)
        {
            var fl = FilmLook.Instance; if (fl == null) return;
            if (hour0 < 0f) hour0 = fl.hour;
            eveFrom = fl.hour; eveTo = toHour; eveT = 0; eveDur = dur;
        }

        void Update()
        {
            if (Application.isEditor && Input.GetKeyDown(KeyCode.F11)) Probe();                     // editor only: what lies under the mouse (Console)
            if (Application.isEditor && Input.GetKeyDown(KeyCode.F10)) { Time.timeScale = Time.timeScale > 0f ? 0f : 1f; Debug.Log("[Alatau] time scale " + Time.timeScale); }   // editor only: freeze to inspect a frame
            float dt = Paused ? 0f : Time.deltaTime;
            FloodStep(dt);
            energy?.Tick(dt);
            seaside?.Tick(dt);
            WaveStep(dt);
            ConstructionStep();
            if (eveFrom >= 0f && FilmLook.Instance != null)
            {
                eveT += dt; float u = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01(eveT / eveDur));
                FilmLook.Instance.hour = Mathf.Lerp(eveFrom, eveTo, u);
            }
        }

        /// <summary>Debug: F9 logs what lies under the mouse (colliders, renderers whose bounds contain the hit point).</summary>
        static void Probe()
        {
            var cam = Camera.main; if (cam == null) return;
            var ray = cam.ScreenPointToRay(Input.mousePosition); var sb = new System.Text.StringBuilder("[Alatau] probe:");
            var hits = Physics.RaycastAll(ray, 200000f); Array.Sort(hits, (a, b) => a.distance.CompareTo(b.distance));
            foreach (var h in hits) { var r = h.collider.GetComponent<Renderer>(); sb.Append($" | {h.collider.name} @{h.point.x:0},{h.point.y:0},{h.point.z:0} {(r != null && r.sharedMaterial != null ? r.sharedMaterial.shader.name : "-")}"); }
            if (hits.Length > 0)
            {
                var p = hits[0].point;
                foreach (var r in FindObjectsByType<Renderer>(FindObjectsSortMode.None))
                    if (r.enabled && r.gameObject.activeInHierarchy && r.bounds.Contains(new Vector3(p.x, r.bounds.center.y, p.z)) && r.bounds.size.x < 30000f)
                        sb.Append($" || {r.name} [{(r.sharedMaterial != null ? r.sharedMaterial.shader.name : "-")}] y{r.bounds.min.y:0}-{r.bounds.max.y:0}");
            }
            sb.Append($" ## Y{Shader.GetGlobalFloat("_AlatauYear")} YF{Shader.GetGlobalFloat("_AlatauYearF"):0.00} G{Shader.GetGlobalFloat("_AlatauGrow")} M{Shader.GetGlobalFloat("_AlatauMode")} F{Shader.GetGlobalFloat("_AlatauFocusD")} K{Shader.GetGlobalFloat("_AlatauDevK")} B{Shader.GetGlobalFloat("_AlatauBlockOn")} N{Shader.GetGlobalFloat("_AlatauNight"):0.00} film{Shader.GetGlobalFloat("_AlatauFilm")}");
            if (hits.Length > 0) sb.Append($" uv{hits[0].textureCoord.x:0.0000},{hits[0].textureCoord.y:0.0000}");
            foreach (var h in hits)
            {
                var mc = h.collider as MeshCollider; if (mc == null || mc.sharedMesh == null || h.triangleIndex < 0) continue;
                var m = mc.sharedMesh; var uv2 = new List<Vector2>(); m.GetUVs(1, uv2); if (uv2.Count == 0) continue;
                var tri = m.triangles; int vi = tri[h.triangleIndex * 3]; var inf = uv2[vi]; int bid = Mathf.RoundToInt(inf.y) - 1;
                sb.Append($" ## {mc.name}: info {inf.x:0.#},{inf.y:0} bid {bid}");
                var b = CityDatabase.Instance?.Get(bid); if (b != null) sb.Append($" {b.Kind} y{b.Year} g{b.GroundM:0} h{b.HeightM:0}");
                foreach (var tn in new[] { "_AlatauGeoTex", "_AlatauStyleTex", "_AlatauHideTex", "_AlatauYearTex" })
                {
                    var tx = Shader.GetGlobalTexture(tn) as Texture2D;
                    if (tx == null) { sb.Append($" {tn}=null"); continue; }
                    try { var c = tx.GetPixel(bid % 256, bid / 256); sb.Append($" {tn}[{tx.name}]=({c.r:0.###},{c.g:0.###},{c.b:0.###},{c.a:0.###})"); } catch { sb.Append($" {tn}[{tx.name}]=?"); }
                }
                break;
            }
            Debug.Log(sb.ToString());
        }

        public void Reset()
        {
            glide = null; Paused = false; LineLayers.JamOff();
            HideCallout();
            if (flooding) { flooding = false; if (water != null) water.SetActive(false); TintLayer.Disable(); }
            if (hour0 >= 0f && FilmLook.Instance != null) { FilmLook.Instance.hour = hour0; hour0 = -1f; }
            eveFrom = -1f;
            if (silk != null) { silk.Hide(); silk = null; UI.TwinUI.Instance?.Middle?.RemoveFromClassList("tour-map"); }
            if (shown.Count > 0) { shown.Clear(); TintLayer.Disable(); MapPins.Instance?.Clear(); }
            waveR = -1f; Shader.SetGlobalFloat(HiOnId, 0f); ClearBeams();
            if (sit != null) { sit.RemoveFromHierarchy(); sit = null; }
            if (energy != null) { energy.Stop(); energy = null; }
            if (seaside != null) { seaside.Stop(); seaside = null; }
            if (cw) { cw = false; MapPins.Instance?.Clear(); }
            if (ai != null) { ai.RemoveFromHierarchy(); ai = null; TintLayer.Disable(); MapPins.Instance?.Clear(); }
            Clean(false);
        }
    }
}
