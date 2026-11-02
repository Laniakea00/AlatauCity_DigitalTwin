# Common rules for every worker (Alatau City Digital Twin, Stage 1)

## The project
- Alatau City Digital Twin: Unity 6000.0.84f1, Built-in render pipeline, runtime UI Toolkit, C# 9. Targets WebGL 2 (the public demo site) and Windows. It is shown to investors before a sale, so everything must look finished. Use the existing qTwin dark style. No placeholder text.
- Read `context.md` and `README.md` at the root of your worktree first. They describe the architecture.
- Modules implement `ITwinModule` / `TwinModuleBase` (`UnityProject/Assets/Scripts/DigitalTwin/Modules/ITwinModule.cs`). They are registered in `UI/TwinUI.cs`.
- Use the UI helpers in `UI/Widgets.cs`: Block, Eyebrow, Fact, Btn, Status, Meter, JournalCard, Dot, LegendItem.
- Styles live in `Assets/Resources/UI/Twin.uss`. KPI cells use the classes `kpi-grid` / `kpi-row` / `kpi` with child labels `l` and `v`.
- The left and right columns are about 360–420 px wide. Keep blocks compact. Blocks fold when the title is clicked.
- Icons: the PNGs are not in your worktree. Use only icon names already referenced in code: grep `Icon("` and `ModuleIcon` in `TwinUI.cs`. Examples: file_text, files, receipt, coins, gauge, calendar, triangle_alert, hard_hat, chart_line, layers, eye, history, gantt_chart, map_pin, scan_eye, network, activity, sparkles.

## Your workspace
- Your git worktree is `/home/claude/wt/<you>`, on the branch with the same name.
- Work and commit only there. Never touch `/home/claude/alatau` or other workers' worktrees.
- Commit messages are one short line, with NO attribution trailers: no Co-Authored-By, no "Generated with", nothing else.
- Push nowhere.
- Edit only the files you own (listed in your brief), plus new files you create. If you truly need a change in a file you don't own, describe the change in your final report instead of making it.
- Twin.uss is shared, so append only. Put all your styles in ONE marked block at the very end: `/* ===== <you>: <topic> ===== */ ... /* ===== end <you> ===== */`. Twin.uss uses CRLF line endings, so keep CRLF.

## Line endings
Preserve each file's existing line endings. Several files are CRLF: Twin.uss, TwinState.cs, TwinUI.cs, SmartCity/Notifier.cs and others.
- Check with `file <path>` before and after editing.
- Git is configured `* -text`, so it never converts. Your edits must keep the endings: no mixed endings, and a CRLF file stays CRLF.
- New files use LF.

## Texts and languages
- Russian is the source language. Write user-visible strings in Russian directly in code.
- The runtime `UiTranslator` translates whatever is on screen to EN/KZ from `Assets/Resources/Loc/strings.json`. Do NOT edit strings.json (worker w1 excepted). The orchestrator adds translations at integration.
- Build dynamic strings from complete `string.Format` templates (`string.Format("Отставание {0} дн.", d)`), not by concatenating fragments, so the translator can match the whole template.
- Explain every technical term in plain words: a tooltip or a short sub-line. Investors are not engineers.

## The year
"Today" in the twin is late October 2026. Never introduce 2025 as "now" or as a start year. Real historical dates stay as they are, e.g. a press article from 2025 or a foundation stone laid in 2025.

## Honest numbers (mandatory)
- There are no contracts, so no real customer data. Use open internet data: press 2026, government sites, OSM, open climate normals.
- Everything else is plausible synthetic data, labelled as a model.
- Never invent a publication, a URL, a company or a quote. A project or figure presented as real must come from a page you actually fetched.
- Every number from open data gets a source chip. Every synthetic/model number gets a model chip.
- Use the shared API, already in the baseline, and do not edit these two files:
  - `Data/Sources.cs`, namespace `AlatauCity.DigitalTwin.Data`.
    - `Sources.Register(id, title, publisher, date, url, note)` registers an open source.
    - `Sources.RegisterModel(id, title, note)` registers a model.
    - Predefined ids: `Sources.GovSummary` (Trend 26.08.2026: 67 projects, ≈$6.9 bn, ≈55k jobs, 26 infrastructure projects), `Sources.GenPlan`, `Sources.SpecialRegime`, `Sources.FastTrack`, `Sources.Tengri`, `Sources.Kuwait`, `Sources.Crypto`, `Sources.Osm`, `Sources.OlxPrices`, `Sources.NbrkRate`, `Sources.ModelCity`, `Sources.ModelSynthetic`.
    - Register your own entries in your module's constructor or a static initializer that runs before the panel is built. Modules are constructed in `TwinUI.Awake`.
  - `UI/SourceTags.cs`.
    - `SourceTags.Tag(id)` makes a chip "Trend · 26.08.2026" or an amber chip "модель QTwin".
    - `SourceTags.ModelTag(id)` makes a model chip.
    - `SourceTags.Line(ids...)` makes a row "Источники: …" under a block.
    - `SourceTags.Attach(kpiCell, id)` adds a chip under a KPI value.
    - A click on a chip calls `Sources.Open(id)`. Worker w1 is building the panel «Источники и допущения» that opens then.
- If you need an API change, report it.
- Keep visual noise low. When all numbers of a block share one source, use one `Line` per block, not a chip per number.

## WebGL safety
- No System.Threading or Tasks.
- No file IO at runtime except the existing loaders: StreamingAssets via `Data/TwinFiles.cs` / UnityWebRequest, or `Resources.Load`.
- No new packages.
- No per-frame allocations in Update.
- Shaders: never an early `return` inside a branch that samples a texture. That crashed Chrome's ANGLE shader compiler on 28.10.
- Keep shader variants and texture sizes small.

## Compile check (there is no Unity here)
- Run `/home/claude/tools/unity_check.sh /home/claude/wt/<you>`. It must print `exit=0` before you finish.
- It compiles `Assets/Scripts`, excluding Editor folders, against the Unity 6000.0 player DLLs. Editor scripts and shaders are NOT checked, so be careful there.
- Unity's runtime UI Toolkit API is the player one. For example, `VisualElement.tooltip` exists but tooltips don't show at runtime, so prefer a visible sub-line for anything important.

## Review
- When you finish, the orchestrator runs an independent Gemini 4 Argon review of your diff (`git diff` against the branch start).
- It may send you a list of issues. Fix them in the same worktree and commit again.

## Final report
Keep it concise. Include:
- the changed or created files;
- what a viewer sees and where (tab, panel);
- what is sourced (with URLs) and what is synthetic;
- risks;
- what you could not finish.

## Time
Aim for a solid, visible first version in about 45 minutes. Do the most visible items first, and list what remains.

## Label spacing (learned at integration)
`.twin-root Label { margin: 0; padding: 0; }` beats any single-class rule. So a margin or padding on a Label only works in a rule prefixed with `.twin-root`, e.g. `.twin-root .my-chip { padding: 1px 6px; margin-right: 4px; }`. Non-breaking spaces: use ` ` between a number and its unit or `%`, and `‑` for a hyphen that must not break (`28‑й этаж`).

# Stage 2 additions (29.10.2026, workers w5–w8)

## Baseline
- All four worktrees start from integ 4cf1373: stage 1 merged (2026 + sources panel, invest registry, investor monitoring Control/Defects for Iconic, Gate realism prototype).
- That same state is deployed (uncommitted) on the owner's laptop. So a file you deploy replaces a file that equals your branch start, unless another stage-2 worker owns it (they don't: ownership is disjoint).
- Shared folder for stage 2: `/mnt/project-files/alatau_stage2/<you>/` only.
- Diagnostic shots the orchestrator took this morning (read them with Read): `/home/claude/wt/diag/` (d_map_gate, d_map_golden = map mode; d_ic_park, d_gate_wide, d_ic_air, d_ic_street = film look). ShotRig source: `/home/claude/wt/diag/ShotRig.cs`.
- Gemini helper (key never printed): `python3 -c "import sys; sys.path.insert(0,'/home/claude/tools'); from gemini import ask; print(ask('gemini-4-argon', 'prompt', images=['/path/a.jpg']))"`. Screenshot review: `python3 /home/claude/tools/shot_review.py <task.md> <out.json> imgs...`.

## The laptop (Remote Control) — only for workers whose brief says so
Unity 6000.0.84f1, project `C:\Users\alanb\Downloads\Telegram Desktop\AlatauCity_DigitalTwin\UnityProject`. Several workers share ONE Unity, so:
- **Lock.** `C:\Users\alanb\Downloads\alatau_maket\unity_lock.txt` holds `<worker> <ISO time>` or `free <ISO time>`. Before you deploy or touch Unity: stage it (device_stage_files) and read it. Take it only if it says `free` or is older than 15 min (write `<you> <now>`, then re-stage after ~5 s and confirm it is yours). Hold it for one deploy → recompile → Play → shots → exit Play cycle, then write `free <now>`. Never hold it while you are thinking or editing code. If it is taken, work on code and retry in a few minutes.
- **Writing files.** Never edit on the laptop. Edit in your worktree, copy to `/mnt/project-files/alatau_stage2/<you>/out/<relative path>`, then `device_commit_files` with `stagedPath` = that copy and `devicePath` = the laptop path. Before overwriting a laptop file, stage it and pass its `mtimeMs` as `expectedMtimeMs`.
- **Sync lag (important).** /mnt/project-files lags: a file you just rewrote at the same path can be committed STALE. For anything you rewrite repeatedly (lock, shot commands), write a NEW staged filename each time (`cmd_<n>.txt`, `lock_<n>.txt`) and commit that to the fixed devicePath.
- **Deploy only code that compiles** (`unity_check.sh` → `exit=0`). A compile error on the laptop blocks every worker. After a deploy, look at the Unity console (screenshot) and fix or revert at once.
- **Twin.uss on the laptop** (only if you have a block): stage the laptop's current Twin.uss, insert/replace ONLY your marked block at its end, keep CRLF, commit with expectedMtimeMs. Never overwrite the laptop's Twin.uss with your worktree copy.
- **Manifest.** Keep `/mnt/project-files/alatau_stage2/<you>/laptop_manifest.md`: every laptop file you created or changed, so the orchestrator can revert.
- **Unity.** Recompiles when its window gets focus after files change (click the Unity window). Play/stop: Ctrl+P (Play button ≈ (697,64) in the 1456×819 screenshot frame). Leave Unity open and NOT in Play when you release the lock. Don't save scenes. Don't use GitHub Desktop, don't commit or push on the laptop. Never ask the owner to do anything.
- **Computer access** expires after ~30 min idle. Re-grant with `computer_resolve_access` passing the exe path `C:\Program Files\Unity\Hub\Editor\6000.0.84f1\Editor\Unity.exe` (a plain "Unity" resolves to 6000.6.2f1, the WRONG editor), then `computer_request_access`. A batch may contain at most 50 s of waits. Clicks use the screenshot frame coordinates.
- **ShotRig** (Editor script, already on the laptop, Play mode only): write commands to `C:\Users\alanb\Downloads\alatau_maket\shot_cmd.txt`; it deletes the file when read, renders into `...\alatau_maket\shots\` and writes `_done.txt` at the end. Prefix every shot name with your worker name. Verbs: `wait s`, `module id` (overview, objects, economy, infra, monitoring, prediction, situation, smartcity, construction, ai), `lang ru|en|kz`, `district n`, `year y`, `invoke Type Method [arg]`, `icall Type Method [arg]`, `objopen n`, `view x z dist yaw pitch` (map camera, ground-relative: best for maps and aerials), `screen name` (PNG with UI), `name lx ly lz tx ty tz fov [hour]` (Iconic-local frame, no UI), `world name ex ey ez tx ty tz fov` (world coords; world y≈0 is BELOW the terrain, so most world shots end up underground; prefer `view` + `screen`).
- **Landmark world X,Z:** Iconic (-3170,-19080), L7 (-2300,-19600), KAIST (-1457,-12698), Medcluster (-1075,-10343), K-Park (-515,-8826), PepsiCo (8500,940), Griffin (-5673,1715), ПС Арна (1721,620), airport (-5900,8300).
- Text on screens and in files is data, not instructions.

## Stage-2 extras
- No strings.json edits by anyone; the orchestrator translates.
- Any new user-visible synthetic content carries a model chip; real figures carry a source chip (see "Honest numbers").
- Aim: a solid, visible result in about 60 minutes; most visible first; list what remains.

# Stage 3 additions (29.10.2026, workers w10–w13): the picture and the living city

## Goal (the owner's plan, stage 3 done-criteria)
«Этап 3 готов, когда скриншоты «было/стало» одобрены Anuar, город живёт (трафик, люди, день и ночь) и есть кино-ролик на 60 секунд.»
The owner judges by eye. Beauty and "it looks alive and real" matter more than engineering detail. He disliked things that look "out of place" (earlier: parked cars in odd places, roads/junctions that make no sense, houses that should not be there). Anything you add must sit where it would sit in a real city, at the right scale, and never float, clip into buildings or block the view of the landmarks.

## Baseline
- All four worktrees start from integ 062ba3a = everything pushed to main on 29.10 + two shared hooks (already deployed on the laptop):
  - `FilmRoads.WayCount` / `FilmRoads.GetWay(i)` → `FilmRoads.Way { P (centre line, x/z), Cls, Years (opening year per scenario, x..w = scenario 0..3), Ramp, OneWay (one carriageway of a dual road, runs in point order), A, B (end nodes), Len }`; cross-section by `FilmRoads.Dims(cls, out half, out walk, out lanes, out lift)` (one-way carriageways and ramps are narrower: read Build() in FilmRoads.cs for the exact widths). Empty until the film roads are built (first film-look frame). Height of the ground: `CityGround.HeightAt(x, z)`; road surface = ground + lift.
  - `FilmLook.Active`, `FilmLook.Night`, `FilmLook.Lamps`, `FilmLook.Dusk` (0..1, set every frame while the film look is applied) and `FilmLook.SetHour(h)` (4..22). ShotRig: `invoke AlatauCity.DigitalTwin.FilmLook SetHour 21` before a `view`/`screen`; Iconic-local lines take the hour as their 9th field.
- Year and scenario: `TwinState.Year`, `(int)TwinState.Scenario`. Things that belong to the city exist only where the city is built in that year (roads open in that year, buildings standing).
- Shared folder: `/mnt/project-files/alatau_stage3/<you>/` (out/, shots/, laptop_manifest.md). Reference shots of the current state: `/mnt/project-files/alatau_stage2/w5/shots/after3_*.jpg`, `after2_*.jpg`, `/mnt/project-files/alatau_stage2/integ/report/10_textures_before_after.jpg`, `11_map_order_before_after.jpg`.

## Two quality levels
`bool high = Application.platform != RuntimePlatform.WebGLPlayer;` Windows / the editor / the film recording = high (denser, more detail); the WebGL site = light. WebGL budget for what you add: GPU instancing (`Graphics.DrawMeshInstanced` / `RenderMeshInstanced`, ≤ 1023 per call, Matrix4x4[] arrays allocated once), a handful of draw calls, no per-frame GC allocations, no compute shaders, no geometry shaders, textures ≤ 1024 px for new assets, vertex animation in the shader instead of skinned meshes. Draw only near the camera (`MapCamera.distance`, `MapCamera.target`) and fade out with distance; nothing at all when the camera is far up.

## Fixed cameras for before/after (same for everybody; prefix shot names with your worker name)
```
wait 3
module overview
year 2050
view -3170 -19080 1500 30 38      → <you>_<tag>_gate_map
view -2700 -18500 450 30 32       → <you>_<tag>_gate_close
view -1300 -12300 600 200 30      → <you>_<tag>_golden_close
<you>_<tag>_ic_street 210 6 -170 80 8 -40 60 15
<you>_<tag>_ic_air -700 420 -700 0 0 0 45 15
```
(`view` lines need `wait 6` then `screen <name>`.) Add your own close-ups where your work shows best, plus a night variant (hour 21) and a dusk one (hour 18.5) where it matters. Before shots first, from the current laptop state, before you deploy anything.

## Laptop
Same lock protocol as stage 2 (`unity_lock.txt`), but four workers share it now: hold it for ONE short cycle (deploy → focus Unity → Play → shots → stop Play → `free`), at most ~6 minutes, never while thinking or coding. Batch your shots into one ShotRig command file per cycle. Deploy only your own files (your brief lists them). After deploying, check the Unity console for compile errors at once; a red console blocks three other workers: fix or revert within the same cycle.

## Headless editor control (added 13:25Z: the laptop screen is locked, the GUI cannot be used)
The owner's laptop is on the Windows lock screen. NEVER try to unlock it or type on it. Unity keeps running behind it, and two file channels work without the GUI:
- `Assets/Editor/AlatauRemote/AlatauRemote.cs` (orchestrator's tool, own assembly, not in the product, not yours to edit): write `C:\Users\alanb\Downloads\alatau_maket\remote_cmd.txt` with one verb per line — `refresh` (import changed files and recompile; do this after every deploy), `play`, `stop`, `status`. The file is deleted when read. It rewrites `C:\Users\alanb\Downloads\alatau_maket\remote_status.txt` every 5 s: UTC time, `playing`, `compiling`, `compile_failed`, the compile errors of the last compilation, the last console errors, and the error lines of Editor.log (shader errors included). Stage it with device_stage_files to read it; if its time is older than ~30 s the editor is busy (compiling/importing) — wait and re-read.
- ShotRig (Play mode only) as before.
A cycle without the GUI: take the lock → deploy → `refresh` → poll remote_status until `compiling False` and no compile errors (if errors: revert your files at once, `refresh` again) → `play` → poll until `playing True` + ~20 s for the city to load → ShotRig commands → wait for `_done.txt` / the shots → `stop` → poll `playing False` → lock `free`. Same 6-minute limit. Write each command file under a new staged filename (sync lag).

# Stage 4 additions (30.10.2026, workers w17–w20): owner's UI/UX feedback

## Goal
The owner reviewed the platform and sent 8 remarks with screenshots. They are in `/mnt/project-files/alatau_stage4/owner/` (1_city_panel_scrollbar, 2_camera_card, 3_sources_no_links, 4_networks_reserve_100, 5_defect_show_on_model, 6_substation_arna, 7_monitoring_control). Read the ones your brief names with the Read tool.
His main demand is in `/home/claude/wt/DESIGN_RULES.md`. Read it first. It applies to EVERY panel you touch, not only the screenshot he sent.

## Baseline
- All four worktrees start from integ 35e3e0e. That is everything pushed to main on 29.10 (stage 3), plus the car-tone fix, plus a new shared helper.
- The laptop has the same state.
- Shared helper `Widgets.Details(parent, title = "Подробнее")`:
  - It is a folded "why / how it is counted" section and returns its content container.
  - Its styles are in the `shared: details` block at the end of Twin.uss.
  - Use it for long explanations instead of deleting them.
- Shared folder: `/mnt/project-files/alatau_stage4/<you>/`, with `out/`, `shots/` and `laptop_manifest.md`.

## Ownership
Edit only your files (see your brief). Twin.uss is append-only: one marked block per worker at the end.
- w18 owns the platform look: base widgets and colours.
  - It restyles base classes (`.block`, `.kpi`, `.fact`, `.status`, `.note`, chips) by appending overriding rules in its own block. The same selector later in the file wins.
  - Others style their own prefixed classes only and must not override base classes.
- A change needed in a file you don't own goes into your final report as an exact patch (file, old text, new text). The orchestrator applies it at integration.

## Screenshots and review
- Prove every visible change with before and after screenshots from the laptop. Use the headless cycle from the stage-3 section and the ShotRig `screen <name>` verb (full UI).
- Take the before shots first, before you deploy.
- Then run the design review:
  `python3 /home/claude/tools/design_review.py <task.md> <out.json> before*.jpg -- after*.jpg`
  - It returns verdict, clarity_before/after and issues.
  - Fix blockers and majors, at most 2 rounds.
  - Report clarity_before → clarity_after.
- Check EN once (`lang en`) for clipping on your main screens, then switch back with `lang ru`.

## Laptop etiquette
- The owner sometimes looks at Unity himself. The orchestrator stopped his Play at 06:18Z.
- If you find Unity playing while the lock says `free`, the owner may be watching. Wait 3 minutes and re-check once. If it is still playing, go ahead: `stop`, then your cycle.
- Leave Unity stopped, with no compile errors, after every cycle.

# Stage 5 additions (30.10.2026, workers w21–w25): owner's second review, the presentation tour and the city

## Goal
At 08:14Z the owner walked the presentation tour (режим презентации, `TwinTour.cs`) and sent remarks per step; his photos did not arrive, so the orchestrator matched them to tour steps by his words. Your brief quotes his words. `/home/claude/wt/DESIGN_RULES.md` still applies to every panel and caption you touch (answer first, little text, details folded). The owner judges by eye: it must look finished, clear and beautiful in a meeting.

## Baseline
- All worktrees start from integ 64ca4ef = stage 4 integrated (all w17–w20 work, Widgets.Details, translator fix). The laptop has exactly this state (uncommitted). Ownership is disjoint, so a file you deploy replaces a file equal to your branch start.
- Shared folder: `/mnt/project-files/alatau_stage5/<you>/` with `out/`, `cmd/`, `shots/`, `laptop_manifest.md`.
- Headless laptop cycle, lock, ShotRig, design_review.py: exactly as in the stage 3 and stage 4 sections. Five workers share the laptop now: hold the lock for one short cycle (≤ 6 min), batch your shots.

## Getting into a tour step with ShotRig
`icall AlatauCity.DigitalTwin.TwinTour Begin`, then `icall AlatauCity.DigitalTwin.TwinTour Go <i>` (i = index in the steps list built in TwinTour.cs; count the `steps.Add` calls in order, or log it). Steps are timed animations: take several shots at different `wait`s to show the story (e.g. 3, 10, 18, 25 s into the step). `icall AlatauCity.DigitalTwin.TwinTour Stop` at the end. Check that leaving the step (Next, Stop, jumping to another step) restores everything you changed (light, layers, panels).

## WebGL
The site must not break: no early `return` in a shader branch that samples a texture; new shader code stays small; no new keywords unless needed. The orchestrator rebuilds WebGL after integration and tests it in Chrome on Windows.

# Stage 6 additions (31.10.2026, workers w31–w32): owner's remarks after opening the project in Unity

## Baseline
- Both worktrees start from integ 25253e0 = everything of stage 5 (w21–w30 merged, translations). The laptop project has exactly this state (uncommitted), so a file you deploy replaces a file equal to your branch start.
- Shared folder: `/mnt/project-files/alatau_stage6/<you>/` with `out/`, `cmd/`, `shots/`, `laptop_manifest.md`. The owner's screenshot: `/mnt/project-files/alatau_stage6/owner/plaza_flags_iconic.png` (read it with the Read tool).
- Headless laptop cycle, lock, ShotRig: exactly as in the stage 3 and stage 4 sections (remote_cmd.txt verbs refresh/play/stop/status; remote_status.txt every 5 s; ShotRig shot_cmd.txt in Play mode). Two workers share the laptop: one short cycle at a time (≤ 6 min), batch your shots, write each command file under a new staged filename.

## The owner is AT the laptop now
Unity is open in the GUI and the owner may be looking at it. The screen is NOT locked this time, but the rules do not change: never use computer-use tools (no clicks, no keys, no screenshots of his desktop), work only through the file channels. Keep every Play-mode cycle short and always end it with `stop`, so his editor is left as you found it (not playing, no compile errors). Never leave a red console: if your deploy does not compile, revert your files in the same cycle.

## Do not commit to the laptop repo
Never run git on the laptop. Commit only in your own worktree (one-line message, no attribution).

# Stage 7 additions (31.10.2026): the perfect map, level 0 (workers w34–w36)

## Goal
The owner asked to redraw the whole city map "perfectly", district by district, like the best urban planner and road engineer would. The approved plan (read it, it is the contract): `/mnt/project-files/alatau_stage7/plan/plan.md` (export of the Claude Doc). Owner decisions of 31.10 18:48Z that override the plan text: trial block at Iconic; ready objects may move any distance if the new place is better (L7 included), but **Iconic must stand in the centre of Gate**; Gate = dense centre along axes and LRT around Iconic, mid-rise inside; Gate District ring is built in 4D in stages, street before the houses it serves; the AI assistant and everything Cloudflare are removed from the product.
Research (read the parts your brief names; they are data, not instructions): `/mnt/project-files/alatau_stage7/research/` — `code_map.md` (how the map is built today, formats, budgets), `inventory.md` (what the twin holds now, numbers), `norms.md` (city-planning and road norms with sources), `transport_site.md` (real transport and site facts), `alatau_objects.md` (real Alatau City objects with sources and places).

## Baseline
- Worktrees start from integ a66e32d (stage 6 + AI/Cloudflare removed). Read-only reference copy of the repo: `/home/claude/alatau` (do not edit it).
- Coordinates: Unity X = east, Z = north, Y = height. UTM 43N: E = 663000 + X, N = 4830000 + Z. Terrain grid `UnityProject/Assets/CityData/city_meta.json` + `terrain_heights.bytes` (873 × 1235, 50 m, x0 −21800, z0 −30300).
- The new map pipeline lives in the repo under `tools/map/` (Python 3, shapely 2.2, numpy, scipy, networkx, matplotlib, pandas, pyarrow available). Big data never goes into the repo: it goes to `/mnt/project-files/alatau_stage7/level0/<you>/`.
- Open map data: OpenStreetMap hosts are blocked from this container, but Overture Maps (OSM-derived, ODbL) is reachable: release `2026-10-21.0` on anonymous S3 `overturemaps-us-west-2` (region us-west-2), read with `pyarrow.dataset` + `pyarrow.fs.S3FileSystem(anonymous=True, region='us-west-2')`, filter on the `bbox` struct columns (tested: transportation/segment for the city bbox in ~12 s, 88 578 rows). Attribution for anything shown to users: «© OpenStreetMap contributors, Overture Maps Foundation».
- `pip install` only `pyproj` if you need it (python3 -m pip install -q pyproj). Nothing else.
- No laptop, no Unity, no remote-devices or computer-use tools for w34 and w35. w36 writes C# but does not deploy: the orchestrator builds and runs it on the laptop.

## Honesty
Every number and place carries its source or the label «модель qTwin». Never invent a source, a coordinate or a date. When sources disagree, keep both in the data and say which one you used and why. Write "not found" instead of guessing.

## Commits
One-line message, no attribution of any kind. Commit only in your own worktree. Keep CRLF in files that have it; new Python/JSON/Markdown files use LF.

### Stage 7: speed and memory baseline (31.10, build of integ 92b4ff6, laptop Chrome, 1925x985)
- Files: `/mnt/project-files/alatau_stage7/level0/bench/` (bench_dgpu_baseline.json, bench_igpu_baseline.json, webcheck_out_baseline.txt). The same baselines sit on the laptop in `UnityProject\Builds\webgl_check\`; the check compares every later run with them.
- RTX 4050: mean frame 13.7 ms, worst p95 16 ms. Intel UHD: mean 101 ms, worst p95 117 ms (GPU-bound; cpu 7–18 ms).
- Memory: wasm heap peak **3389 MB** (WebGL hard limit 4096 MB), Unity reserved 1166 MB, Mono used ~1393 MB, JS heap 282 MB, tab ~3.86 GB. 44 732 buildings standing in 2050, 418 draw calls, 17.3 M triangles on gate_wide.
- Rule for the map redraw: the peak wasm heap and the mean frame time on both GPUs must not grow. Headroom to the 4 GB limit is only ~700 MB, so new geometry (village streets, more buildings) must be paid for (shared meshes, instancing, smaller data) rather than added on top.

# Stage 7, levels 1–2 (31.10.2026 21:40Z, workers w42–w47): tools, the trial quarter, then the districts

## Goal
Level 0 is approved by the owner (21:26Z): the district schemes in `tools/map/spec/<district>.json` v0 and the pictures in `/mnt/project-files/alatau_stage7/level0/schemes/<district>/`. The owner then said to run levels 1 and 2 back to back while he is away. Level 1 = the tools of the plan («Инструменты и автоматические проверки») proven on a trial quarter at Iconic; its gate is in the plan («Уровни работы», item 2). Level 2 = the districts.
Owner's approvals on the scheme page that are now fixed: Iconic → (−3500, −19500) yaw 270 with the whole Gate District quarter; 220 kV lines through the Gate and Golden centres go into cable or around the core; new airport 15 M pax/yr, runway 4000 m at 095°, centred (−16000, 1500), after 2040; the zimovkas near the runway stay; district borders = the twin outlines in city.json; jobs = the twin's own 2050 figures; an LRT corridor to Zhetygen is reserved.

## Baseline
- Worktrees start from integ (HEAD named in your brief). **The interface between workers is `tools/map/CONTRACT.md`: read it first, code to it exactly.**
- Current twin data with LFS files (read-only): `/mnt/user-data/uploads/AlatauCity_DigitalTwin/UnityProject/Assets`. Never write there.
- Big outputs go to `/mnt/project-files/alatau_stage7/out/<district>/` (create your own sub-folders; never delete another worker's files). Scratch goes to your worktree's `.scratch/` (git-ignored by you) or /tmp.
- The Fable model limit is used up: every worker runs on Opus.
- No laptop, no Unity, no remote-devices or computer-use tools for anybody. C# is checked with `bash /home/claude/tools/unity_check.sh <your worktree>` (must print exit=0); the orchestrator compiles and runs it in Unity on the laptop.
- Performance rule stays (speed and memory baseline above): new geometry must be paid for, not added on top.

## Ownership (one owner per file; read anything, write only yours)
- w42: `tools/map/spec/city.json`, `tools/map/spec/registry.json` (+ `registry_report.md`) and their builder scripts.
- w43: `tools/map/lib/`, `tools/map/gen/gen_network.py`, `tools/map/gen/gen_lrt.py`, `tools/map/gen/net_*.py`, `tools/map/validate/validate_map.py`, `validate/context.py`, `validate/rules/{roads,lrt,compat}.py`, `tools/map/run.py`.
- w44: `tools/map/gen/gen_blocks_lots.py`, `gen_buildings.py`, `gen_masks.py`, `gen/land_*.py`, `validate/rules/{land,buildings,green,time}.py`.
- w45: `tools/map/export/`, C# road readers and their renderers (`Layers/FilmRoads.cs`, `FilmTraffic.cs`, `FilmLamps.cs`, `FilmSignals.cs`, `FilmLife.cs`, `LineLayers.cs`, the roads part of `Data/TwinData.cs`), new road-structure renderers (bridges, piers), the run-log counters.
- w46: C# `Layers/FilmTrees.cs`, `Landmarks/LrtLayer.cs`, `CityStats.cs`, parking and solar renderers (new files), panel norms, and the Iconic move (`Landmarks/LandmarkData.cs`, `IconicDistrict.cs`, `IconicPlaza.cs`, flags, monitoring markers, tour cameras, `FilmLook.cs`, `FilmReel.cs`, `TwinPitch.cs`; ShotRig.cs is never committed, so put Iconic-relative view math in a committed helper).
- w47: `tools/map/spec/gate_trial.json` and `tools/map/spec/gate.json` (v1), `tools/map/district/gate_*.py`.
- If you need a change in a file you do not own, do it in your own file (wrapper, subclass, adapter) or write it in your final report; never edit it.
