# WebGL build check

Run it after every WebGL build, before the zip goes to a GitHub Release.

## Here (Linux, headless Chromium + Playwright)

```
node tools/webgl_check/check_build.js UnityProject/Builds/WebGL --out /tmp/webgl_check
node tools/webgl_check/check_build.js alatau-webgl.zip --out /tmp/webgl_check
```

The last line is `PASS` or `FAIL`. The exit code is 0 for PASS, 1 for FAIL and 2 when the check could not run.
The `--out` folder holds `report.json`, `console.log`, `browser.log` and screenshots: `check_cover.png`, `check_progress50.png`, `check_started.png` and `check_final.png`.

What counts as FAIL:
- the twin did not start before `--timeout`;
- a GPU context loss;
- a GPU process crash, read from Chromium's own log;
- a shader that fails to compile or link;
- a Wasm abort or an uncaught page error.

When the GPU process dies, the script replays the GL programs linked before the crash one by one in fresh pages.
- If one of them crashes the GPU process again, it is saved as `shaders/crash.vert` and `shaders/crash.frag`.
- `shaders/gl_trail.txt` is always saved. It lists the GL calls that allocate or compile, with times relative to the crash.

Options:
- `--template UnityProject/Assets/WebGLTemplates/Alatau` checks an older build with the current loading page. It changes the build folder.
- `--throttle 2` serves the build at 2 MB/s, so the cover and its progress can be watched.
- `--settle 25` sets how many seconds to watch the running twin.
- `--gpu swiftshader|angle-gl|angle-d3d11|default` picks the GL backend. Use `--channel chrome` to run the installed Chrome.

Headless Chromium here draws with SwiftShader, a software GPU, so it is slower than a real GPU and stricter. A FAIL here should still be confirmed on Windows.

## On the Windows laptop (real Chrome, ANGLE on Direct3D 11)

Double-click `tools\webgl_check\check_build_windows.cmd`. It needs no Node, no Python and no install.

You can also run it with arguments:

```
powershell -ExecutionPolicy Bypass -File tools\webgl_check\check_build_windows.ps1 [-Build UnityProject\Builds\WebGL] [-Timeout 900] [-Port 8765] [-NoBench]
```

What it does:
1. It serves the build on `http://localhost:8765/?check=1&bench=1`.
2. It opens Chrome (or Edge) with a throw-away profile and `--use-angle=d3d11`, first on the discrete GPU (`--force_high_performance_gpu`), then again on the integrated one (`--force_low_power_gpu`).
3. Each time it waits for the page's own report. The page posts its state, errors, GPU name, a canvas snapshot and the bench to `/__check` after the last bench view (about 2-4 min after the start), or at once on a failure.
4. It scans `chrome_debug.log` for a GPU process crash.

`-Timeout` is the limit for each Chrome run (default 900 s; a run takes about 3-5 min). The whole check takes about 6-10 min. PASS needs both runs to pass.

The results go to `UnityProject\Builds\webgl_check\`:
- discrete GPU: `report.json`, `shot.jpg` and `chrome_debug.log` (the same files as before);
- integrated GPU: `report_igpu.json`, `shot_igpu.jpg` and `chrome_debug_igpu.log`;
- the bench of each run: `bench_dgpu_<yyyyMMdd_HHmm>.json` and `bench_igpu_<yyyyMMdd_HHmm>.json`;
- the baseline of each GPU: `bench_dgpu_baseline.json` and `bench_igpu_baseline.json` (see below).

`-NoBench` gives the old check: one run on the discrete GPU with `?check=1`, the report about 20 s after the start. `-KeepOpen` leaves Chrome open and makes the discrete-GPU run only.

## The bench: speed baseline of the site

The map redraw must not make the site slower: frame time and tab memory on 10 fixed views, in Chrome on the laptop's integrated GPU (Intel) and on its RTX 4050. Level 0 measures the baseline, level 4 must not be worse.

With `bench=1` in the page URL the twin itself runs the bench (`UnityProject/Assets/Scripts/DigitalTwin/Bench/AlatauBench.cs`; without it nothing of the bench exists or runs). It waits until the twin has loaded (data, landmarks, film roads, interface; at most 3 min), lets it settle 5 s, then visits the 10 views of the table at the top of that file, the same every run. At each view it sets the camera, year, module and hour (scenario Base, no district, no selection), waits 4 s, then samples 6 s. At the end it gives the year, module, hour and camera back.

The views: `city_high` (the Home view, 70 km), `gate_wide` (the start view of the site, 3.6 km), `iconic_street` (eye 6 m up on the Iconic plaza: flags, tower), `gate_dusk_street` (low over the Gate trunk road at 18:30), `gate_night` (Gate at 21:00), `golden_uni` (KAIST campus), `growing_industry` (the industrial belt), `green_shore` (Kapchagay shore), `lrt_viaduct` (LRT trunk between Gate and Golden), `construction_2034` (Construction tab, year 2034). Never change their values: the comparison with the baseline is only fair on the same views.

What each number means (per view, over the 6 s):
- `avgMs`, `p50Ms`, `p95Ms`, `p99Ms`, `maxMs`: time between two frames, measured inside Unity at the start of each frame (the PlayerLoop). In the browser a frame waits for the screen refresh, so a GPU that keeps up shows the refresh period (16.7 ms at 60 Hz, 6.9 ms at 144 Hz); higher means the GPU or the main thread could not keep up. `fps` = 1000 / avg; `over33ms` = frames longer than 33 ms (below 30 fps).
- `cpuAvgMs`, `cpuP95Ms`: main-thread work of a frame (scripts, culling, sending the draw calls), from the start of EarlyUpdate to the end of PostLateUpdate. It shows script and draw-call regressions even when the frame time is held at the refresh rate.
- `unityAllocatedMB`, `unityReservedMB`, `monoUsedMB`, `monoHeapMB`: Unity's own memory counters (`Profiler.GetTotalAllocatedMemoryLong`, `GetTotalReservedMemoryLong`, `GetMonoUsedSizeLong`, `GetMonoHeapSizeLong`); `gfxUsedMB`, `systemUsedMB` from the profiler counters; -1 or 0 where the WebGL release player does not expose them.
- `jsHeapUsedMB`, `jsHeapTotalMB`: Chrome's `performance.memory` (exact with `--enable-precise-memory-info`, which the check sets); `wasmHeapMB`: the size of Unity's wasm memory (it only grows).
- `os.rendererMB`, `os.gpuMB`, `os.browserMB`, `os.totalMB` (added by the Windows check): private bytes of Chrome's processes of that run as Windows sees them, read when the view is done: the tab's renderer, the GPU process, the browser process, all together. This is the tab memory of the gate. Dedicated video memory of the RTX is not in it.
- `cars`, `carsAlive`, `people`, `lamps`: vehicles drawn and alive, people drawn, lamp posts drawn, mean per frame.
- `buildingChunksVisible` / `buildingChunks`: building meshes (of 71) in view; `buildingsStanding`: buildings standing in that year.
- `drawCalls`, `batches`, `setPassCalls`, `trianglesK`, `verticesK`: Unity's render counters per frame, -1 where the release player does not expose them.
- `gcCollections`: garbage collections during the 6 s; `pageVisible`: the page was in front (false means the sample is not valid).

The whole bench is also in `window.__alatau.bench` (`views`, `done: true`, `gpu`, `summary`) and printed once to the console as `[Alatau] bench {...}`. In the Windows player use `AlatauCity.exe -bench` (the JSON line goes to Player.log); in the editor call `AlatauCity.DigitalTwin.AlatauBench.Run()` (ShotRig: `invoke AlatauCity.DigitalTwin.AlatauBench Run`).

The output prints one line per view while it runs and a table per GPU at the end: `avg p50 p95 max` (ms), `cpu` (ms), `jsMB wasmMB tabMB gpuMB` (MB), `cars ppl lamps`, and `vs base` (avg frame time against the baseline).

The baseline: the first complete bench of a GPU that passes is saved as `bench_<gpu>_baseline.json`; every later run prints its change against it (mean avg and p95 in %, peak wasm heap and tab memory in MB) and names the views more than 10 % slower. To take a new baseline, delete the file. If both runs report the same GPU, Chrome did not switch GPUs (Windows graphics settings): the igpu numbers are then not the integrated GPU's.

A build made with an older loading page is checked on a copy that gets the current template.

Do not run it while someone else is presenting from the same Chrome profile. It uses its own profile, but it does open a Chrome window.

## Errors on the live site

The template keeps every error in `window.__alatau.errors`, together with the GPU name. The live site sends them nowhere; this check reads them from the page.
