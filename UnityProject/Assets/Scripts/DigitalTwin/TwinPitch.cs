using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
using AlatauCity.DigitalTwin.Data;
using AlatauCity.DigitalTwin.Modules;
using AlatauCity.DigitalTwin.UI;
using AlatauCity.DigitalTwin.Landmarks;

namespace AlatauCity.DigitalTwin
{
    /// <summary>Presentation, mode 3 — two 3-minute pitches that run without a presenter: «Питч инвестору» and «Питч госоргану».
    /// Each is a short list of tour scenes (the tour's own steps and effects, or a scene of its own) with a Russian voice-over
    /// (Gemini TTS, one clip per subtitle line in Resources/Pitch, made by tools/pitch/pitch_tts.py) and one subtitle line at the bottom
    /// that follows the voice. A scene lasts as long as its lines (plus a short tail) and ends with one figure and its source or model
    /// chip. Start: the presentation button / F5 opens the choice «Полный тур · Питч инвестору · Питч госоргану» (keys 1, 2, 3);
    /// Shift+F5 starts the investor pitch at once, Ctrl+F5 the government one. Space — pause, ← → — scenes, Esc — exit, as in the tour.</summary>
    public partial class TwinTour
    {
        class PScene
        {
            public string Title; public string[] Lines; public AudioClip[] Clips; public float[] At, End;
            public Func<(string v, string l, string src)> Fig; public string Css;
        }
        string pitch;                                            // "inv" / "gov" while a pitch runs
        readonly List<PScene> pScenes = new List<PScene>();
        AudioSource pVoice; int pIdx = -1, pLine = -1; float pLastT, pNextFig, pStartedAt, pSceneAt; bool pAudioPaused, pFigOn; string pCss;
        VisualElement pHost, pWrap, pFig, pFigSrc, pMenu; Label pSub, pFigPre, pFigV, pFigPost, pFigL; string pFigSrcId, pFigRaw;
        static readonly System.Text.RegularExpressions.Regex PNum = new System.Text.RegularExpressions.Regex(@"\$?\d+(?:[ \u00a0,.]\d+)*");
        readonly System.Text.StringBuilder pLog = new System.Text.StringBuilder();
        const float PLead = 0.8f, PGap = 0.5f, PTail = 1.3f;

        /// <summary>A pitch is playing.</summary>
        public static bool PitchRunning => Running && Instance.pitch != null;
        public static void PitchInvestor() => Instance?.BeginPitch("inv");
        public static void PitchGov() => Instance?.BeginPitch("gov");

        /// <summary>The presentation button and F5: the choice of the full tour or one of the two pitches.</summary>
        void PitchMenu()
        {
            if (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift)) { BeginPitch("inv"); return; }
            if (Input.GetKey(KeyCode.LeftControl) || Input.GetKey(KeyCode.RightControl)) { BeginPitch("gov"); return; }
            if (pMenu != null && pMenu.panel != null && pMenu.style.display == DisplayStyle.Flex) { HideMenu(); return; }
            var ui = TwinUI.Instance; if (ui == null || ui.Scene == null) { Begin(); return; }
            pMenu?.RemoveFromHierarchy();
            pMenu = new VisualElement(); pMenu.AddToClassList("w26-menu");
            var top = new VisualElement(); top.AddToClassList("w26-menu-top"); pMenu.Add(top);
            var h = new Label("Презентация") { pickingMode = PickingMode.Ignore }; h.AddToClassList("w26-menu-h"); top.Add(h);
            top.Add(Widgets.Btn("✕", HideMenu, "small", "ghost"));
            MenuItem("1", "Полный тур", "все районы и функции · ведёт докладчик", () => { HideMenu(); Begin(); });
            MenuItem("2", "Питч инвестору", "3 минуты · голос и субтитры", () => BeginPitch("inv"));
            MenuItem("3", "Питч госоргану", "3 минуты · голос и субтитры", () => BeginPitch("gov"));
            var hint = new Label("1 · 2 · 3 — выбор · Esc — закрыть") { pickingMode = PickingMode.Ignore }; hint.AddToClassList("w26-menu-hint"); pMenu.Add(hint);
            ui.BlockWhileHovered(pMenu); ui.Scene.Add(pMenu);
        }
        void MenuItem(string key, string name, string sub, Action go)
        {
            var it = new VisualElement(); it.AddToClassList("w26-menu-item");
            var k = new Label(key) { pickingMode = PickingMode.Ignore }; k.AddToClassList("w26-menu-key"); it.Add(k);
            var col = new VisualElement { pickingMode = PickingMode.Ignore }; col.AddToClassList("w26-menu-col"); it.Add(col);
            var n = new Label(name) { pickingMode = PickingMode.Ignore }; n.AddToClassList("w26-menu-name"); col.Add(n);
            var s = new Label(sub) { pickingMode = PickingMode.Ignore }; s.AddToClassList("w26-menu-sub"); col.Add(s);
            it.AddManipulator(new Clickable(go)); pMenu.Add(it);
        }
        void HideMenu() { pMenu?.RemoveFromHierarchy(); pMenu = null; }
        bool MenuOpen => pMenu != null && pMenu.panel != null;

        // ------------------------------------------------------------------ the two scripts
        Step Pick(List<Step> all, Func<Step, bool> p, int fallback)
        {
            foreach (var s in all) { bool ok = false; try { ok = p(s); } catch { } if (ok) return s; }
            return all[Mathf.Clamp(fallback, 0, all.Count - 1)];
        }
        static string TitleOf(Step s) { try { return s.Title != null ? s.Title() : ""; } catch { return ""; } }
        static (Step st, string title, float need, Func<(string, string, string)> fig, string css, float[] at) Sc(Step st, string title, float need, Func<(string, string, string)> fig, string css = null, float[] at = null) => (st, title, need, fig, css, at);
        /// <summary>The energy story (TourEnergy) has its own beats: the city grows, the outage (≈ 13.6 s), the answer (≈ 20.5 s), the light back (≈ 24 s);
        /// the lines wait for them (earliest start of each line, seconds into the scene).</summary>
        static readonly float[] EnergyBeats = { 0f, 4.5f, 19.8f, 24.4f };

        /// <summary>Inside Iconic and its construction monitoring, at the pace of the investor's scene 5.</summary>
        static Step PitchInside() => new Step { Seg = 1, Zone = 0, Module = "construction", Year = 2028, Dur = 24f,
            Enter = () => IconicInterior.Instance?.Enter("iconic"),
            Shots = new[] {
                At(2.4f, () => InsideFloor(IconicFloors.PServices)),
                At(4.4f, () => InsideFloor(IconicFloors.PFrame)),
                At(5.8f, () => IconicMonitor.Instance?.Show("iconic")),
                At(11.2f, () => { IconicMonitor.Instance?.VideoTab(1); IconicMonitor.Instance?.VideoPlay(0.8f); }),
                At(17.0f, () => IconicMonitor.Instance?.VideoTab(0)) } };

        List<(Step, string, float, Func<(string, string, string)>, string, float[])> InvScenes(List<Step> all) => new List<(Step, string, float, Func<(string, string, string)>, string, float[])> {
            Sc(Pick(all, s => s.Seg == 0 && !s.Grow, 0), "Почему Alatau City", 0f, () => ("до 30 лет", "налоговые льготы для новых проектов", InvestRegistry.Np)),
            Sc(Pick(all, s => s.Seg == 3 && s.Story == null && s.Module == "overview", 8), "На перекрёстке коридоров", 0f, () => ("67", "инвестпроектов · ≈ $6,9 млрд", Sources.GovSummary)),
            Sc(Pick(all, s => s.Seg == 1 && s.Module == "construction", 3), "Gate и Iconic Complex", 0f, () => ("> $800 млн", "инвестиции в Iconic Complex", InvestRegistry.AtIconic)),
            Sc(new Step { Seg = 1, Zone = 0, Module = "objects", Year = 2026, Enter = () => { TwinState.SetDistrict(0); Fly(new Vector2(-3170f, -19080f), 4200f, 40f); } },
               "Куда вложить: реестр и калькулятор", 0f, () => ("до 10 %", "стоимости проекта — потолок льготы", InvestRegistry.MorganLewis), "w26-cols"),
            Sc(PitchInside(), "Контроль стройки Iconic", 22f, () => ("конец 2029", "сдача башни по плану", InvestRegistry.AtIconic)),
            Sc(Pick(all, s => TitleOf(s).Contains("нерги"), 16), "Сети без сюрпризов: энергия 2034", 26f, () => ("за 8 лет", "до дефицита энергии — прогноз двойника", TwinModels.Loads), null, EnergyBeats),
            Sc(all[all.Count - 1], "Alatau City ждёт инвесторов", 0f, () => ("≈ 55 тыс.", "рабочих мест в проектах города", Sources.GovSummary)),
        };
        List<(Step, string, float, Func<(string, string, string)>, string, float[])> GovScenes(List<Step> all) => new List<(Step, string, float, Func<(string, string, string)>, string, float[])> {
            Sc(Pick(all, s => s.Grow, 1), "Рост города до 2050 года", 0f, () => (Kk(Res(2050)), "жителей к 2050 году · сценарий", Sources.ModelCity)),
            Sc(new Step { Seg = 0, Module = "infra", Year = 2026, AnimFrom = 2026, AnimTo = 2030, Enter = Overview }, "Сети — раньше домов", 0f,
               () => ("365,1 млрд ₸", "21 проект сетей · 2026–2027", InvestRegistry.KapInfra), "w26-cols"),
            Sc(Pick(all, s => TitleOf(s).Contains("нерги"), 16), "Дефицит энергии виден заранее", 26f, () => ("за 8 лет", "до дефицита энергии — прогноз двойника", TwinModels.Loads), null, EnergyBeats),
            Sc(new Step { Seg = 6, Module = "situation", Year = 2036, Enter = () => TourFx.Instance?.ShowSituation(SituationModule.Find("flood") != null ? "flood" : "dtp") },
               "Ситуационный центр: паводок", 19f, () => ("30 ч", "до пика паводка — прогноз модели", TwinModels.Flood)),
            Sc(Pick(all, s => s.Module == "smartcity", 15), "Smart City и iKomek 109", 23f, () => (Loc.N0(SmartCity.CameraCount(TwinState.Year)), "камер в сети города", TwinModels.SmartCity)),
            Sc(Pick(all, s => s.Seg == 6 && s.Module == "construction", 13), "Контроль стройки", 0f, () => (Loc.N0(ConstructionLayer.SitesBehind), "строек отстают от графика", TwinModels.Build), "w26-nocallout"),
            Sc(Pick(all, s => s.Module == "ai", 17), "Вопрос ИИ-помощнику", 19f, () => (Loc.N0(AiModule.PlanSchool(TwinState.Year).Homes), "домов проверено за секунды", TwinModels.Ai)),
            Sc(all[all.Count - 1], "Один двойник для всего города", 0f, () => ("26", "инфраструктурных проектов города", Sources.GovSummary)),
        };

        void BeginPitch(string id)
        {
            HideMenu();
            if (!TwinData.Ready || !CityStats.Ready) { Debug.LogWarning("[Alatau] pitch: data not ready"); return; }
            if (running) Stop();
            if (navOpen) SetNav(false);
            InvestRegistry.Init(); TwinModels.Init();
            Build(); var all = steps.ToList(); steps.Clear(); pScenes.Clear(); NavReset();
            var lines = id == "inv" ? PitchLines_inv : PitchLines_gov;
            var defs = id == "inv" ? InvScenes(all) : GovScenes(all);
            int n = Mathf.Min(lines.Length, defs.Count); float total = 0f;
            for (int i = 0; i < n; i++)
            {
                var (st, title, need, fig, css, beats) = defs[i];
                var L = lines[i]; var sc = new PScene { Title = title, Lines = L, Clips = new AudioClip[L.Length], At = new float[L.Length], End = new float[L.Length], Fig = fig, Css = css };
                float tt = PLead;
                for (int k = 0; k < L.Length; k++)
                {
                    AudioClip c = null; try { c = Resources.Load<AudioClip>($"Pitch/{id}_{i + 1}_{k + 1}"); } catch (Exception e) { Debug.LogWarning("[Alatau] pitch clip: " + e.Message); }
                    sc.Clips[k] = c; float len = c != null ? c.length : Mathf.Max(2.5f, L[k].Length * 0.075f);   // no clip: the subtitles keep the voice's pace
                    if (beats != null && k < beats.Length) tt = Mathf.Max(tt, beats[k]);
                    sc.At[k] = tt; sc.End[k] = tt + len; tt = sc.End[k] + PGap;
                }
                st.Dur = Mathf.Max(need, sc.End[L.Length - 1] + PTail); st.End = -1f; st.Speed = 1f; st.Story = null;
                string tl = title; st.Title = () => tl;
                steps.Add(st); pScenes.Add(sc); total += st.Dur;
            }
            if (steps.Count == 0) return;
            pitch = id; video = false; free = false; running = true; paused = false; pIdx = -1; pLine = -1; pFigOn = false; pShotDone = -1; pLastShotT = 0f;
            pLog.Clear(); pLog.AppendLine($"pitch {id} planned {total:0.0} s: " + string.Join(" | ", steps.Select((s, i) => $"{i + 1}: {s.Dur:0.0}")));
            Debug.Log("[Alatau] " + pLog.ToString().TrimEnd());
            pStartedAt = Time.unscaledTime;
            AutoShotInit();
            Go(0);
        }

        /// <summary>Every frame (TwinTour.Update): the choice menu's keys; the voice, the subtitle and the figure of the current scene.</summary>
        void PitchTick()
        {
            if (MenuOpen && !running)
            {
                if (Input.GetKeyDown(KeyCode.Alpha1) || Input.GetKeyDown(KeyCode.Keypad1)) { HideMenu(); Begin(); return; }
                if (Input.GetKeyDown(KeyCode.Alpha2) || Input.GetKeyDown(KeyCode.Keypad2)) { BeginPitch("inv"); return; }
                if (Input.GetKeyDown(KeyCode.Alpha3) || Input.GetKeyDown(KeyCode.Keypad3)) { BeginPitch("gov"); return; }
                if (Input.GetKeyDown(KeyCode.Escape)) { HideMenu(); return; }
            }
            if (pitch == null) return;
            if (!running || steps.Count != pScenes.Count || idx >= pScenes.Count) { EndPitch(); return; }
            PitchUi(); if (pWrap == null) return;
            var sc = pScenes[idx];
            if (idx != pIdx || t < pLastT - 0.01f)                       // a new scene (or the same one again, from «Назад»)
            {
                if (pIdx >= 0 && idx != pIdx) pLog.AppendLine($"scene {pIdx + 1} lasted {Time.unscaledTime - pSceneAt:0.0} s");
                pIdx = idx; pLine = -1; pSceneAt = Time.unscaledTime; pVoice?.Stop(); pAudioPaused = false; SetFig(false); pSub.text = ""; pWrap.BringToFront();
                SetCss(sc.Css);
            }
            pLastT = t;
            if (pVoice != null)
            {
                if (paused && pVoice.isPlaying) { pVoice.Pause(); pAudioPaused = true; }
                else if (!paused && pAudioPaused) { pVoice.UnPause(); pAudioPaused = false; }
            }
            int k = -1; for (int j = 0; j < sc.At.Length; j++) if (t >= sc.At[j]) k = j;
            if (k != pLine && k >= 0 && !paused)
            {
                pLine = k; pSub.text = sc.Lines[k]; pWrap.BringToFront();             // a window opened by the scene stays under the subtitles
                var c = sc.Clips[k];
                if (c != null)
                {
                    if (pVoice == null) { pVoice = gameObject.AddComponent<AudioSource>(); pVoice.playOnAwake = false; pVoice.spatialBlend = 0f; }
                    pVoice.clip = c; pVoice.Play();
                }
            }
            bool subOn = pLine >= 0 && t <= sc.End[pLine] + 0.9f;
            var disp = subOn ? DisplayStyle.Flex : DisplayStyle.None;
            if (pSub.style.display != disp) pSub.style.display = disp;
            bool figOn = t >= sc.At[sc.At.Length - 1] - 0.2f;               // the last line says the figure: it stays to the end of the scene
            if (figOn != pFigOn) SetFig(figOn);
            if (pFigOn && (pNextFig -= Time.unscaledDeltaTime) <= 0f) FillFig(sc);   // live figures (the year runs) twice a second
            AutoShot(sc);
        }

        // Editor proof only: when Downloads/alatau_maket/w26_autoshot.txt holds a prefix, every scene is captured on the scene's own clock
        // (its first subtitle and its figure), so the shots land right however slowly the editor runs. Nothing of this is in a build.
        string pShotPrefix; int pShotDone;
        void AutoShotInit()
        {
            pShotPrefix = null;
#if UNITY_EDITOR
            try
            {
                var f = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "alatau_maket", "w26_autoshot.txt");
                if (System.IO.File.Exists(f)) { var s = System.IO.File.ReadAllText(f).Trim(); if (s.Length > 0) pShotPrefix = s; }
            }
            catch { }
#endif
        }
        void AutoShot(PScene sc)
        {
#if UNITY_EDITOR
            if (pShotPrefix == null || idx >= steps.Count) return;
            int key = pIdx * 2;
            if (t < pLastShotT) pShotDone = -1;
            pLastShotT = t;
            string tag = null;
            if (pShotDone < key && pLine >= 0 && t >= sc.At[0] + 1.6f) { pShotDone = key; tag = "a"; }
            else if (pShotDone < key + 1 && t >= steps[idx].Dur - 0.7f) { pShotDone = key + 1; tag = "b"; }
            if (tag == null) return;
            var dir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "alatau_maket", "shots");
            StartCoroutine(ShotAtFrameEnd(System.IO.Path.Combine(dir, $"{pShotPrefix}_{pitch}_s{pIdx + 1}{tag}.jpg")));
            pLog.AppendLine($"shot s{pIdx + 1}{tag} at t {t:0.0}");
#endif
        }
#if UNITY_EDITOR
        System.Collections.IEnumerator ShotAtFrameEnd(string path)   // the screen as drawn, interface included (no ScreenCapture module in this project)
        {
            yield return new WaitForEndOfFrame();
            Texture2D tex = null;
            try
            {
                tex = new Texture2D(Screen.width, Screen.height, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, Screen.width, Screen.height), 0, 0); tex.Apply();
                System.IO.File.WriteAllBytes(path, tex.EncodeToJPG(88));
            }
            catch (Exception e) { Debug.LogWarning("[Alatau] pitch shot: " + e.Message); }
            if (tex != null) Destroy(tex);
        }
#endif
        float pLastShotT;

        void SetFig(bool on)
        {
            pFigOn = on; if (pFig == null) return;
            if (on && pIdx >= 0 && pIdx < pScenes.Count) FillFig(pScenes[pIdx]);
            pFig.style.display = on ? DisplayStyle.Flex : DisplayStyle.None;
        }
        void FillFig(PScene sc)
        {
            pNextFig = 0.5f;
            (string v, string l, string src) f; try { f = sc.Fig(); } catch (Exception e) { Debug.LogWarning("[Alatau] pitch figure: " + e.Message); f = ("", "", null); }
            if (pFigRaw != f.v)
            {
                pFigRaw = f.v; var v = f.v ?? ""; var m = PNum.Match(v);
                string pre = m.Success ? v.Substring(0, m.Index).Trim() : "", num = m.Success ? m.Value : v, post = m.Success ? v.Substring(m.Index + m.Length).Trim() : "";
                pFigPre.text = pre; pFigPre.style.display = pre.Length > 0 ? DisplayStyle.Flex : DisplayStyle.None;
                pFigV.text = num;
                pFigPost.text = post; pFigPost.style.display = post.Length > 0 ? DisplayStyle.Flex : DisplayStyle.None;
            }
            if (pFigL.text != f.l) pFigL.text = f.l;
            if (f.src != pFigSrcId) { pFigSrcId = f.src; pFigSrc.Clear(); if (!string.IsNullOrEmpty(f.src)) pFigSrc.Add(SourceTags.Tag(f.src)); }
        }
        void SetCss(string css)
        {
            var mid = TwinUI.Instance?.Middle; var scn = TwinUI.Instance?.Scene;
            if (pCss != null) { mid?.RemoveFromClassList(pCss); scn?.RemoveFromClassList(pCss); }
            pCss = css;
            if (css != null) { mid?.AddToClassList(css); scn?.AddToClassList(css); }
        }

        /// <summary>The subtitle line and the figure card at the bottom of the map, above every window (built again when the interface is rebuilt).
        /// While a pitch runs the root carries «w26-on»: the time dock gives its place to the subtitles.</summary>
        void PitchUi()
        {
            var ui = TwinUI.Instance; var root = ui != null && ui.Middle != null ? ui.Middle.parent : null; if (root == null) return;   // the interface root: above the monitor window too
            if (pWrap != null && pHost == root && pWrap.parent == pHost) { if (!pHost.ClassListContains("w26-on")) pHost.AddToClassList("w26-on"); return; }
            pWrap?.RemoveFromHierarchy(); pHost = root; pFigSrcId = null; pFigRaw = null; pHost.AddToClassList("w26-on");
            pWrap = new VisualElement { pickingMode = PickingMode.Ignore }; pWrap.AddToClassList("w26-wrap");
            pFig = new VisualElement(); pFig.AddToClassList("w26-fig"); pFig.style.display = DisplayStyle.None; pWrap.Add(pFig);
            var hero = new VisualElement { pickingMode = PickingMode.Ignore }; hero.AddToClassList("w26-fig-hero"); pFig.Add(hero);   // «до» 30 «лет»: the number leads, the words around it are smaller
            pFigPre = new Label { pickingMode = PickingMode.Ignore }; pFigPre.AddToClassList("w26-fig-u"); hero.Add(pFigPre);
            pFigV = new Label { pickingMode = PickingMode.Ignore }; pFigV.AddToClassList("w26-fig-v"); hero.Add(pFigV);
            pFigPost = new Label { pickingMode = PickingMode.Ignore }; pFigPost.AddToClassList("w26-fig-u"); hero.Add(pFigPost);
            var col = new VisualElement { pickingMode = PickingMode.Ignore }; col.AddToClassList("w26-fig-col"); pFig.Add(col);
            pFigL = new Label { pickingMode = PickingMode.Ignore }; pFigL.AddToClassList("w26-fig-l"); col.Add(pFigL);
            pFigSrc = new VisualElement(); pFigSrc.AddToClassList("w26-fig-src"); col.Add(pFigSrc);
            pSub = new Label { pickingMode = PickingMode.Ignore }; pSub.AddToClassList("w26-sub"); pSub.style.display = DisplayStyle.None; pWrap.Add(pSub);
            pHost.Add(pWrap);
            if (pFigOn) SetFig(true);
            if (pLine >= 0 && pIdx >= 0 && pIdx < pScenes.Count) pSub.text = pScenes[pIdx].Lines[pLine];
        }

        /// <summary>The caption of the tour box in a pitch: its name instead of the tour's parts (TwinTour.Caption).</summary>
        void PitchCaption()
        {
            if (box == null) return;
            bool on = pitch != null;
            var d = on ? DisplayStyle.None : DisplayStyle.Flex;
            if (segs != null && segs.style.display != d) segs.style.display = d;
            var zr = box.Q(className: "tour-zones"); if (zr != null && zr.style.display != d) zr.style.display = d;
            if (!on) return;
            lZone.text = (pitch == "inv" ? "Питч инвестору · 3 минуты" : "Питч госоргану · 3 минуты").ToUpperInvariant();
            zoneDot.style.backgroundColor = Brand;
        }

        void EndPitch()
        {
            if (pIdx >= 0) pLog.AppendLine($"scene {pIdx + 1} lasted {Time.unscaledTime - pSceneAt:0.0} s");
            pLog.AppendLine($"pitch {pitch} ended after {Time.unscaledTime - pStartedAt:0.0} s ({pScenes.Count} scenes, reached {pIdx + 1})");
            Debug.Log("[Alatau] " + pLog.ToString().TrimEnd());
#if UNITY_EDITOR
            try { System.IO.File.AppendAllText(System.IO.Path.Combine(Application.dataPath, "..", "Logs", "pitch_timing.txt"), DateTime.UtcNow.ToString("u") + "\n" + pLog + "\n"); } catch { }   // editor proof of the timing; no file is written in a build
#endif
            pitch = null; pIdx = -1; pLine = -1;
            if (pVoice != null) pVoice.Stop();
            SetCss(null); SetFig(false);
            pHost?.RemoveFromClassList("w26-on"); pWrap?.RemoveFromHierarchy(); pWrap = null;
            pScenes.Clear(); NavReset();
            PitchCaption();
        }
    }
}
