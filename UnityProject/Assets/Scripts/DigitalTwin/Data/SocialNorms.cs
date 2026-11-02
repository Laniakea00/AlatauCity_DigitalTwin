using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

namespace AlatauCity.DigitalTwin.Data
{
    /// <summary>Norms of schools and kindergartens for the panels and the analytics: StreamingAssets/twin/norms_social.json of the new
    /// map data (tools/map CONTRACT §6, from spec/norms.json): places per 1000 residents and service radii, with their source.
    /// loads.json holds the need already computed by gen_twin with its own norms (120 school and 60 kindergarten places per 1000,
    /// norms.py), so once the twin data is read the need for school and kindergarten places is scaled by new / basis. The basis is
    /// the file's optional "loads_basis" {school_places_per_1000, kindergarten_places_per_1000} (a loads.json recomputed with the new
    /// norms says so with the same values: factor 1), else 120 / 60. Without the file nothing changes.</summary>
    public static class SocialNorms
    {
        [Serializable] class Basis { public float school_places_per_1000, kindergarten_places_per_1000; }
        [Serializable] class J
        {
            public float school_places_per_1000, kindergarten_places_per_1000, school_radius_m, kindergarten_radius_m, polyclinic_radius_m;
            public string source_ru; public Basis loads_basis;
        }
        public const string File = "norms_social.json";
        /// <summary>The norms gen_twin computes loads.json with today (Tools/twin_gen/norms.py).</summary>
        public const float TodaySchool = 120f, TodayKindergarten = 60f;

        public static float SchoolPer1000 = TodaySchool, KindergartenPer1000 = TodayKindergarten;
        /// <summary>Service radii, metres (0 = not given).</summary>
        public static float SchoolRadiusM, KindergartenRadiusM, PolyclinicRadiusM;
        public static string SourceRu = "";
        /// <summary>True when norms_social.json was read.</summary>
        public static bool Loaded { get; private set; }
        static float basisS = TodaySchool, basisK = TodayKindergarten;
        static bool started, read, applied;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (started) return; started = true;
            if (TwinFiles.NeedsDownload)
            {
                var host = new GameObject("Social norms (download)"); UnityEngine.Object.DontDestroyOnLoad(host);
                host.AddComponent<Loader>().StartCoroutine(Download(host));
            }
            else
            {
                string txt = null; try { txt = TwinFiles.Text(File); } catch (Exception) { }          // no file: today's norms
                Parse(txt);
            }
            if (TwinData.Ready) Apply(); else TwinData.OnReady += Apply;
        }
        class Loader : MonoBehaviour { }
        static IEnumerator Download(GameObject host)
        {
            string txt = null;
            using (var rq = UnityWebRequest.Get(Application.streamingAssetsPath + "/twin/" + File))
            {
                yield return rq.SendWebRequest();
                if (rq.result == UnityWebRequest.Result.Success) txt = rq.downloadHandler.text;
            }
            Parse(txt); Apply();
            UnityEngine.Object.Destroy(host);
        }
        static void Parse(string txt)
        {
            read = true;
            if (string.IsNullOrEmpty(txt)) return;
            J j; try { j = JsonUtility.FromJson<J>(txt); } catch (Exception ex) { Debug.LogWarning("[Alatau] " + File + " unreadable: " + ex.Message); return; }
            if (j == null || j.school_places_per_1000 <= 0f || j.kindergarten_places_per_1000 <= 0f) { Debug.LogWarning("[Alatau] " + File + ": no places per 1000, today's norms kept"); return; }
            SchoolPer1000 = j.school_places_per_1000; KindergartenPer1000 = j.kindergarten_places_per_1000;
            SchoolRadiusM = Mathf.Max(0f, j.school_radius_m); KindergartenRadiusM = Mathf.Max(0f, j.kindergarten_radius_m); PolyclinicRadiusM = Mathf.Max(0f, j.polyclinic_radius_m);
            SourceRu = j.source_ru ?? "";
            if (j.loads_basis != null && j.loads_basis.school_places_per_1000 > 0f && j.loads_basis.kindergarten_places_per_1000 > 0f) { basisS = j.loads_basis.school_places_per_1000; basisK = j.loads_basis.kindergarten_places_per_1000; }
            Loaded = true;
        }
        /// <summary>Once the file is read (or found missing) and the twin data is ready: the need for school and kindergarten places
        /// of loads.json scaled to the norms, and the note of the social model rewritten.</summary>
        static void Apply()
        {
            if (applied || !read || !TwinData.Ready) return; applied = true;
            if (!Loaded) { Debug.Log($"[Alatau] social norms: no {File}, today's {TodaySchool:0} school and {TodayKindergarten:0} kindergarten places per 1000"); return; }
            float fs = SchoolPer1000 / basisS, fk = KindergartenPer1000 / basisK; double before = 0, after = 0;
            foreach (var sc in TwinData.SocialNeed)
            {
                if (sc == null) continue;
                foreach (var d in sc)
                {
                    if (d == null) continue;
                    for (int k = 0; k < 2 && k < d.Length; k++)
                    {
                        var y = d[k]; if (y == null) continue; float f = k == 0 ? fs : fk;
                        for (int i = 0; i < y.Length; i++) { before += y[i]; y[i] *= f; after += y[i]; }
                    }
                }
            }
            var src = Sources.Get(TwinModels.Social); if (src != null) src.Note = ModelNote();
            Debug.Log($"[Alatau] social norms from {File}: {SchoolPer1000:0.#} school and {KindergartenPer1000:0.#} kindergarten places per 1000 (loads.json basis {basisS:0.#} / {basisK:0.#}: need x{fs:0.###} / x{fk:0.###}, all years {before:0} -> {after:0}); radii school {SchoolRadiusM:0} m, kindergarten {KindergartenRadiusM:0} m, polyclinic {PolyclinicRadiusM:0} m; source: {SourceRu}");
        }

        static string N(float v) => v.ToString("0.#", Loc.Ru);
        /// <summary>The «why» line of the school, kindergarten and bed metrics (Prediction) with the norms of the file.</summary>
        public static string Why()
        {
            // the source (often long) is in the model note of «Источники и допущения», not on the panel
            if (SchoolRadiusM > 0f && KindergartenRadiusM > 0f)
                return string.Format("Норматив: {0} мест в школах, {1} в детсадах и 5 больничных коек на 1000 жителей; радиус обслуживания школы {2} м, детсада {3} м. Места — объекты генплана по годам ввода.",
                    N(SchoolPer1000), N(KindergartenPer1000), N(SchoolRadiusM), N(KindergartenRadiusM));
            return string.Format("Норматив: {0} мест в школах, {1} в детсадах и 5 больничных коек на 1000 жителей. Места — объекты генплана по годам ввода.",
                N(SchoolPer1000), N(KindergartenPer1000));
        }
        /// <summary>The note of the social model (Sources, «Источники и допущения») with the norms of the file.</summary>
        public static string ModelNote()
        {
            if (SchoolRadiusM > 0f && KindergartenRadiusM > 0f && PolyclinicRadiusM > 0f)
                return string.Format("Потребность = {0} мест в школах, {1} в детсадах и 5 больничных коек на 1000 жителей; радиус обслуживания: школа {2} м, детсад {3} м, поликлиника {4} м ({5}). Места — объекты генплана по годам ввода в сценарии QTwin.",
                    N(SchoolPer1000), N(KindergartenPer1000), N(SchoolRadiusM), N(KindergartenRadiusM), N(PolyclinicRadiusM), SourceRu);
            return string.Format("Потребность = {0} мест в школах, {1} в детсадах и 5 больничных коек на 1000 жителей ({2}). Места — объекты генплана по годам ввода в сценарии QTwin.",
                N(SchoolPer1000), N(KindergartenPer1000), SourceRu);
        }
    }
}
